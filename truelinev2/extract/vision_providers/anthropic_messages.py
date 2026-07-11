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
  * RETRIES: up to 2 additional attempts (3 total) ONLY on 429 / 5xx / connection-timeout, short jittered
    backoff, all inside the seam's own overall per-page timeout. A 4xx auth/permission error -- or any
    other non-retryable failure -- is never retried; it propagates unchanged, and the seam reduces it to
    the new ``HANDWRITTEN_PROVIDER_ERROR`` refusal (exception CLASS NAME only, never the message).
  * A refused/malformed/missing tool-use response raises ``ProviderOutputInvalid`` (seam maps this to the
    existing ``HANDWRITTEN_PROVIDER_OUTPUT_INVALID`` refusal) -- this adapter never guesses or invents a
    reading that was not visibly present in the model's structured output.

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

_MAX_ATTEMPTS = 3          # 1 initial call + up to 2 retries
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
                       report_attempts: Callable[[int], None]) -> Any:
    """Up to ``_MAX_ATTEMPTS`` calls to ``client.messages.create(**request_kwargs)``. Retries ONLY on
    429/5xx/connection-timeout (per ``_is_retryable``); any other exception -- including 4xx auth/
    permission errors -- propagates on the FIRST attempt, unretried. ``report_attempts`` is called once
    per attempt so the seam can log the real attempt count (observability only; never affects control flow)."""
    last_exc: Optional[BaseException] = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        report_attempts(attempt)
        try:
            return client.messages.create(**request_kwargs)
        except Exception as exc:  # noqa: BLE001 - classified below; non-retryable/exhausted re-raises as-is
            if attempt == _MAX_ATTEMPTS or not _is_retryable(anthropic_module, exc):
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


def build_provider(config: Any, *, client_factory: Optional[Callable[[], Any]] = None
                   ) -> Callable[[bytes, dict], dict]:
    """``config`` is the seam's small read-only view (``timeout_seconds`` + ``get_env``). The seam always
    calls ``build_provider(config)`` with ONE positional argument; ``client_factory`` exists solely for
    offline test injection (production never passes it -- the default constructs ``anthropic.Anthropic()``
    with the SDK's own credential resolution, and ``max_retries=0`` so this adapter's own retry loop, not
    a second SDK-internal retry loop, controls attempt count and timing)."""
    try:
        import anthropic  # lazy: this module stays importable, and the suite stays green, SDK-absent
    except ImportError as exc:
        raise ProviderUnavailable("the 'anthropic' package is not installed") from exc

    model_id = config.get_env(_MODEL_ENV)
    if not model_id:
        raise ProviderUnavailable("%s is not set" % _MODEL_ENV)

    resolved_client_factory = client_factory or (lambda: anthropic.Anthropic(max_retries=0))

    def _call(page_png_bytes: bytes, context: Dict[str, Any]) -> dict:
        client = resolved_client_factory()
        image_b64 = base64.standard_b64encode(bytes(page_png_bytes)).decode("ascii")
        request_kwargs = _build_request_kwargs(model_id, image_b64)
        report_attempts = context.get("report_attempts") or (lambda attempt: None)
        response = _call_with_retries(client, anthropic, request_kwargs, report_attempts=report_attempts)
        tool_input = _extract_tool_input(response)
        return _build_record(tool_input, context)

    return _call
