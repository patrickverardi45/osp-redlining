"""Vendor adapter: Anthropic Messages API vision provider for Phase-1 handwritten bore-log extraction.

THIS IS THE ISOLATION BOUNDARY -- the ONE file in this repo where the vendor name "anthropic" and the
model-id ENV VAR NAME are allowed to appear. ``truelinev2/extract/handwritten_borelog.py`` (the seam) and
``truelinev2/config.py`` name nothing vendor-specific: they load this module by its DOTTED PATH (the
``TL2_HANDWRITTEN_BORELOG_PROVIDER`` env value) and call ``build_provider(config) -> provider_callable``.

Design points (mirrors ``truelinev2/api/observability.py``'s optional-dependency pattern):
  * The ``anthropic`` SDK is imported LAZILY, inside ``build_provider`` -- this module stays importable
    (and the full test suite stays green) with the SDK absent. Import failure raises ``ProviderUnavailable``.
  * The model id comes ONLY from env (``TL2_HANDWRITTEN_VISION_MODEL``, read via ``config.get_env`` --
    this module reads its OWN env var; the seam never names it). No default/hardcoded model literal.
  * The API key is NEVER touched by this code -- the client is constructed with the SDK's own standard
    credential resolution (``anthropic.Anthropic()``), which reads ``ANTHROPIC_API_KEY`` internally.
  * ``client_factory`` is an injectable keyword on ``build_provider`` for offline tests (production/the
    seam never passes it; the SDK is never required for the test suite to pass).
  * The page image + a fixed system instruction are sent as ONE forced tool-use request whose input
    schema matches ``HandwrittenPageExtraction`` minus ``source``/``method``/``extractor``/``record_format``/
    ``audit`` (this adapter fills those four from ``context`` + fixed constants; the seam re-validates the
    full record via ``validate_page_extraction`` regardless of what this adapter returns).
  * RETRIES: up to a FEW additional attempts ONLY on 429 / 5xx / connection-timeout, short jittered
    backoff. A 4xx auth/permission error -- or any other non-retryable failure -- is never retried; it
    propagates unchanged, and the seam reduces it to the new ``HANDWRITTEN_PROVIDER_ERROR`` refusal
    (exception CLASS NAME only, never the message).
  * A refused/malformed/missing tool-use response raises ``ProviderOutputInvalid`` (seam maps this to the
    existing ``HANDWRITTEN_PROVIDER_OUTPUT_INVALID`` refusal) -- this adapter never guesses or invents a
    reading that was not visibly present in the model's structured output.
  * TIMEOUT BUDGETING: the seam's own hard timeout around a provider call
    (``handwritten_borelog.py``'s ``_run_provider_with_timeout``) is a ``threading.Thread.join(timeout)``
    -- on timeout it merely ABANDONS the still-running daemon thread and reports
    ``HANDWRITTEN_EXTRACTION_TIMEOUT``; Python has no safe way to forcibly kill a thread, so that join()
    is a REPORTING deadline, not an enforcement mechanism, and a provider call with no timeout of its own
    could keep the network call running in the background indefinitely after the seam has already moved
    on. This adapter therefore derives an explicit SDK-level request timeout from ``config.timeout_seconds``
    (the seam's own per-page budget) and hands it to the client -- the SDK timeout, not the seam's join(),
    is what actually terminates a hung request. Retry attempts are recomputed DOWN (never up, never below
    1) so the worst case (every attempt using the full per-attempt timeout) still fits inside the seam's
    overall budget -- see ``_derive_sdk_timeout``/``_derive_max_attempts``.

No streaming. No network call happens anywhere at IMPORT time -- only inside the returned callable, and
only when a caller actually invokes it (an unconfigured/absent provider never touches the network).
"""
from __future__ import annotations

import base64
import random
import time
from typing import Any, Callable, Dict, Optional, Tuple

from truelinev2.contracts.handwritten_extraction import PAGE_RECORD_FORMAT, VISION_OCR
from truelinev2.extract.vision_providers import ProviderOutputInvalid, ProviderUnavailable

# This adapter's OWN env var -- the model id. Read only through ``config.get_env``; never named by the
# seam or by config.py. NO default/hardcoded model-id literal anywhere in this file.
_MODEL_ENV = "TL2_HANDWRITTEN_VISION_MODEL"
_EXTRACTOR_NAME = "anthropic_messages"
_TOOL_NAME = "record_bore_log_page_extraction"

# Timeout budgeting (see module docstring, "TIMEOUT BUDGETING"). The SDK-level request timeout -- not the
# seam's thread-join, which only ABANDONS an overrun thread -- is what actually stops a hung request.
# ``_DESIRED_MAX_ATTEMPTS`` is a CEILING; ``_derive_max_attempts`` recomputes DOWN (never up, never below
# 1) so the worst case (every attempt using the full per-attempt timeout) still fits the seam's own budget.
_TIMEOUT_MARGIN_SECONDS = 5.0
_MIN_SDK_TIMEOUT_SECONDS = 5.0
_DESIRED_MAX_ATTEMPTS = 3
_BACKOFF_BASE_SECONDS = 0.05

# --------------------------------------------------------------------------- #
# Fixed extraction instruction -- transcription rules only, never a guess-permission.
# --------------------------------------------------------------------------- #
_SYSTEM_PROMPT = (
    "You transcribe ONE page of a printed \"BORE LOG\" field form (handwritten or photographed). "
    "The form has four header fields (date, crew, job name, print/sheet number) and a ladder of "
    "STATION | DEPTH | BOC readings printed in up to 4 side-by-side column groups. "
    "For every header field and every reading cell, report BOTH a normalized `value` and the raw "
    "`verbatim` text exactly as printed or written. Set `status` to READ only when you can confidently "
    "read the cell; UNREADABLE when something is written but illegible; NOT_PRESENT when the cell is "
    "blank. NEVER guess or infer a value that is not visibly written on the page -- an UNREADABLE or "
    "NOT_PRESENT cell must never carry a fabricated value. Set `region` to the normalized [x0,y0,x1,y1] "
    "bounding box (0..1 of the page image) when you can locate the cell, else null. Set `confidence` to "
    "LOW or MEDIUM only -- never HIGH, even when you are certain. If the page as a whole cannot be read "
    "(blank, unrelated content, or fully illegible), set page_status to REFUSED and fill `refusal` with a "
    "short code and reason; otherwise set page_status to EXTRACTED and leave `refusal` null."
)

# --------------------------------------------------------------------------- #
# Forced-tool-use structured-output schema -- HandwrittenPageExtraction minus source/method/extractor/
# record_format/audit (this adapter fills those four; the seam re-validates the assembled record).
# --------------------------------------------------------------------------- #
_CELL_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "value": {"type": ["string", "number", "null"]},
        "verbatim": {"type": ["string", "null"]},
        "status": {"type": "string", "enum": ["READ", "UNREADABLE", "NOT_PRESENT"]},
        "confidence": {"type": ["string", "null"], "enum": ["LOW", "MEDIUM", None]},
        "region": {
            "type": ["array", "null"],
            "items": {"type": "number"},
            "description": "Exactly 4 numbers [x0,y0,x1,y1] normalized 0..1, or null if not locatable.",
        },
    },
    "required": ["value", "verbatim", "status", "confidence", "region"],
    "additionalProperties": False,
}
_HEADER_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "date": _CELL_SCHEMA, "crew": _CELL_SCHEMA, "job_name": _CELL_SCHEMA, "print_raw": _CELL_SCHEMA,
    },
    "required": ["date", "crew", "job_name", "print_raw"],
    "additionalProperties": False,
}
_READING_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "station": _CELL_SCHEMA,
        "depth_ft": _CELL_SCHEMA,
        "boc_ft": _CELL_SCHEMA,
        "column_index": {"type": "integer"},
        "row_index": {"type": "integer"},
    },
    "required": ["station", "depth_ft", "boc_ft", "column_index", "row_index"],
    "additionalProperties": False,
}
_REFUSAL_SCHEMA: Dict[str, Any] = {
    "type": ["object", "null"],
    "properties": {"code": {"type": "string"}, "reason": {"type": "string"}},
    "required": ["code", "reason"],
    "additionalProperties": False,
}
_EXTRACTION_INPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "header": _HEADER_SCHEMA,
        "readings": {"type": "array", "items": _READING_SCHEMA},
        "page_status": {"type": "string", "enum": ["EXTRACTED", "REFUSED"]},
        "refusal": _REFUSAL_SCHEMA,
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["header", "readings", "page_status", "refusal", "warnings"],
    "additionalProperties": False,
}
_TOOL: Dict[str, Any] = {
    "name": _TOOL_NAME,
    "description": "Record the transcription of ONE printed BORE LOG form page.",
    "input_schema": _EXTRACTION_INPUT_SCHEMA,
    "strict": True,
}


def _build_request_kwargs(model_id: str, image_b64: str) -> Dict[str, Any]:
    return {
        "model": model_id,
        "max_tokens": 4096,
        "system": _SYSTEM_PROMPT,
        "tools": [_TOOL],
        "tool_choice": {"type": "tool", "name": _TOOL_NAME},
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": image_b64}},
                {"type": "text", "text": "Transcribe this bore log page."},
            ],
        }],
    }


def _derive_sdk_timeout(seam_timeout_seconds: float) -> float:
    """The per-request SDK timeout this adapter gives the Anthropic client, derived from the SEAM's own
    per-page timeout budget (``config.timeout_seconds`` == ``TL2_HANDWRITTEN_BORELOG_TIMEOUT_SECONDS``):
    the seam timeout minus a small safety margin, floored so a tight configured budget never produces an
    unusably small (or negative/zero) request timeout. See the module docstring's "TIMEOUT BUDGETING"
    section for WHY: the seam's own ``threading.Thread.join(timeout)`` only ABANDONS an overrun thread --
    it cannot forcibly terminate it -- so this SDK-level timeout is what actually stops a hung request."""
    return max(seam_timeout_seconds - _TIMEOUT_MARGIN_SECONDS, _MIN_SDK_TIMEOUT_SECONDS)


def _derive_max_attempts(seam_timeout_seconds: float, sdk_timeout: float) -> int:
    """How many attempts (each up to ``sdk_timeout`` long, worst case) fit inside the seam's own overall
    per-page budget -- capped at ``_DESIRED_MAX_ATTEMPTS``, never below 1. Recomputed DOWN from the
    desired retry count when the derived per-attempt timeout leaves little or no room for a retry (e.g.
    at the default 90s seam timeout, ``sdk_timeout`` already consumes nearly the whole budget, so a
    single attempt is all that reliably fits) -- a deployment that wants retry headroom configures a
    larger ``TL2_HANDWRITTEN_BORELOG_TIMEOUT_SECONDS``."""
    if sdk_timeout <= 0:
        return 1
    return max(1, min(_DESIRED_MAX_ATTEMPTS, int(seam_timeout_seconds // sdk_timeout)))


def _is_retryable(anthropic_module: Any, exc: BaseException) -> bool:
    retryable_types = tuple(
        t for t in (
            getattr(anthropic_module, "RateLimitError", None),
            getattr(anthropic_module, "InternalServerError", None),
            getattr(anthropic_module, "APIConnectionError", None),
        ) if t is not None
    )
    return bool(retryable_types) and isinstance(exc, retryable_types)


def _call_with_retries(client: Any, anthropic_module: Any, request_kwargs: Dict[str, Any], *,
                       report_attempts: Callable[[int], None], max_attempts: int) -> Any:
    """Up to ``max_attempts`` calls to ``client.messages.create(**request_kwargs)`` (``max_attempts`` is
    ``_derive_max_attempts``'s BUDGET-BOUNDED value, not the module-level ceiling directly). Retries ONLY
    on 429/5xx/connection-timeout (per ``_is_retryable``); any other exception -- including 4xx auth/
    permission errors -- propagates on the FIRST attempt, unretried. ``report_attempts`` is called once
    per attempt so the seam can log the real attempt count (observability only; never affects control flow)."""
    last_exc: Optional[BaseException] = None
    for attempt in range(1, max_attempts + 1):
        report_attempts(attempt)
        try:
            return client.messages.create(**request_kwargs)
        except Exception as exc:  # noqa: BLE001 - classified below; non-retryable/exhausted re-raises as-is
            if attempt == max_attempts or not _is_retryable(anthropic_module, exc):
                raise
            last_exc = exc
            time.sleep(_BACKOFF_BASE_SECONDS * attempt + random.uniform(0.0, _BACKOFF_BASE_SECONDS))
    raise last_exc  # pragma: no cover - unreachable: the loop above always returns or raises


def _block_get(block: Any, key: str, default: Any = None) -> Any:
    if isinstance(block, dict):
        return block.get(key, default)
    return getattr(block, key, default)


def _extract_tool_input(response: Any) -> Dict[str, Any]:
    if getattr(response, "stop_reason", None) == "refusal":
        raise ProviderOutputInvalid("the model declined to transcribe this page")
    for block in getattr(response, "content", None) or []:
        if _block_get(block, "type") == "tool_use" and _block_get(block, "name") == _TOOL_NAME:
            tool_input = _block_get(block, "input")
            if not isinstance(tool_input, dict):
                raise ProviderOutputInvalid("tool_use block has a non-dict input")
            return tool_input
    raise ProviderOutputInvalid("no matching tool_use block in the response")


def _build_record(tool_input: Dict[str, Any], context: Dict[str, Any]) -> dict:
    try:
        header = tool_input["header"]
        readings = tool_input["readings"]
        page_status = tool_input["page_status"]
        refusal = tool_input["refusal"]
        warnings = tool_input["warnings"]
    except KeyError as exc:
        raise ProviderOutputInvalid("tool_use input is missing a required field: %s" % exc) from exc
    source = {
        "upload_id": context["upload_id"],
        "sha256": context["sha256"],
        "file_name": context["file_name"],
        "page_index": context["page_index"],
        "page_count": context["page_count"],
    }
    return {
        "record_format": PAGE_RECORD_FORMAT,
        "source": source,
        "method": VISION_OCR,
        "extractor": _EXTRACTOR_NAME,
        "header": header,
        "readings": readings,
        "page_status": page_status,
        "refusal": refusal,
        "warnings": warnings,
        "audit": [],
    }


def build_provider(config: Any, *, client_factory: Optional[Callable[[float], Any]] = None
                   ) -> Callable[[bytes, dict], dict]:
    """``config`` is the seam's small read-only view (``timeout_seconds`` + ``get_env``). The seam always
    calls ``build_provider(config)`` with ONE positional argument; ``client_factory`` exists solely for
    offline test injection (production never passes it) and is called with ONE positional argument --
    the derived SDK request timeout (seconds, see ``_derive_sdk_timeout``) -- so a test can assert what
    timeout the adapter computed. The default factory constructs ``anthropic.Anthropic(max_retries=0,
    timeout=<that value>)`` with the SDK's own credential resolution -- ``max_retries=0`` so this
    adapter's own retry loop, not a second SDK-internal retry loop, controls attempt count and timing,
    and an explicit ``timeout`` so the SDK -- not the seam's abandon-only thread-join -- is what actually
    bounds a hung request (see the module docstring's "TIMEOUT BUDGETING" section)."""
    try:
        import anthropic  # lazy: this module stays importable, and the suite stays green, SDK-absent
    except ImportError as exc:
        raise ProviderUnavailable("the 'anthropic' package is not installed") from exc

    model_id = config.get_env(_MODEL_ENV)
    if not model_id:
        raise ProviderUnavailable("%s is not set" % _MODEL_ENV)

    sdk_timeout = _derive_sdk_timeout(config.timeout_seconds)
    max_attempts = _derive_max_attempts(config.timeout_seconds, sdk_timeout)
    resolved_client_factory = client_factory or (
        lambda timeout: anthropic.Anthropic(max_retries=0, timeout=timeout))

    def _call(page_png_bytes: bytes, context: Dict[str, Any]) -> dict:
        client = resolved_client_factory(sdk_timeout)
        image_b64 = base64.standard_b64encode(bytes(page_png_bytes)).decode("ascii")
        request_kwargs = _build_request_kwargs(model_id, image_b64)
        report_attempts = context.get("report_attempts") or (lambda attempt: None)
        response = _call_with_retries(client, anthropic, request_kwargs,
                                      report_attempts=report_attempts, max_attempts=max_attempts)
        tool_input = _extract_tool_input(response)
        return _build_record(tool_input, context)

    return _call
