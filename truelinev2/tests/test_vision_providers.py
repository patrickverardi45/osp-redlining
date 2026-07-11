"""Offline tests for the runtime-configured vision-provider layer (Phase 1.5, W6): the
extract/handwritten_borelog.py factory (dotted-module-path loading), the fixture-driven fake provider
(extract/vision_providers/fake.py), and the one real vendor messages-API adapter shipped in this repo
(extract/vision_providers/anthropic_messages.py).

ZERO network calls anywhere in this file. The ``anthropic`` SDK is NEVER required for this file to pass:
every adapter test that needs SDK-shaped exception/client types injects a FAKE ``anthropic`` module into
``sys.modules`` (a standard offline-test technique -- Python's import machinery consults ``sys.modules``
before touching the filesystem, so ``import anthropic`` inside the adapter picks up the fake). A dedicated
test also blocks the SDK entirely (``sys.modules["anthropic"] = None``) to prove the ImportError path.
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import sys
import types
from typing import Any, Dict

import pytest

from truelinev2.contracts.handwritten_extraction import EXTRACTED, VISION_OCR
from truelinev2.extract.handwritten_borelog import (
    HANDWRITTEN_PROVIDER_ERROR,
    HANDWRITTEN_PROVIDER_OUTPUT_INVALID,
    HANDWRITTEN_VISION_PROVIDER_NOT_CONFIGURED,
    ProviderConfig,
    extract_handwritten,
)
from truelinev2.extract.vision_providers import ProviderOutputInvalid, ProviderUnavailable
from truelinev2.extract.vision_providers import anthropic_messages
from truelinev2.extract.vision_providers import fake as fake_provider

_FAKE_MODULE_PATH = "truelinev2.extract.vision_providers.fake"
_ANTHROPIC_MODULE_PATH = "truelinev2.extract.vision_providers.anthropic_messages"


# --------------------------------------------------------------------------- #
# Shared fixture builders (generic ids/values only -- no customer/person/project/location strings).
# --------------------------------------------------------------------------- #
def _jpeg_bytes() -> bytes:
    from PIL import Image

    img = Image.new("RGB", (12, 12), color=(40, 40, 40))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _blank_cell() -> Dict[str, Any]:
    return {"value": None, "verbatim": None, "status": "NOT_PRESENT", "confidence": None, "region": None}


def _read_cell(value) -> Dict[str, Any]:
    return {"value": value, "verbatim": str(value), "status": "READ", "confidence": "MEDIUM", "region": None}


def _reading(station, depth, boc, *, column_index: int = 0, row_index: int = 0) -> Dict[str, Any]:
    return {"station": _read_cell(station), "depth_ft": _read_cell(depth), "boc_ft": _read_cell(boc),
           "column_index": column_index, "row_index": row_index}


def _blank_header() -> Dict[str, Any]:
    return {"date": _blank_cell(), "crew": _blank_cell(), "job_name": _blank_cell(), "print_raw": _blank_cell()}


def _valid_tool_input() -> Dict[str, Any]:
    """A schema-valid extraction the model's forced tool_use is expected to return (minus source/method/
    extractor/record_format/audit, which the adapter fills)."""
    return {
        "header": _blank_header(),
        "readings": [_reading("0+00", 3.5, 5.0, row_index=0), _reading("0+50", 3.5, 5.0, row_index=1)],
        "page_status": "EXTRACTED",
        "refusal": None,
        "warnings": [],
    }


# --------------------------------------------------------------------------- #
# Factory (dotted-module-path loading) -- unknown module path.
# --------------------------------------------------------------------------- #
def test_unknown_module_path_refuses_not_configured_with_sanitized_reason():
    out = extract_handwritten(_jpeg_bytes(), "photo.jpg", upload_id="up-1",
                              provider_name="truelinev2.extract.vision_providers.does_not_exist")
    refusal = out["pages"][0]["refusal"]
    assert refusal["code"] == HANDWRITTEN_VISION_PROVIDER_NOT_CONFIGURED
    assert "does_not_exist" in refusal["reason"]
    # Sanitized: no traceback, no raised exception message leaked through.
    assert "Traceback" not in refusal["reason"]
    assert "File \"" not in refusal["reason"]


# --------------------------------------------------------------------------- #
# Fake fixture provider -- loaded via the real dotted-path factory (end-to-end through extract_handwritten).
# --------------------------------------------------------------------------- #
def test_fake_provider_no_fixtures_env_refuses_not_configured(monkeypatch):
    monkeypatch.delenv("TL2_HANDWRITTEN_FAKE_FIXTURES", raising=False)
    out = extract_handwritten(_jpeg_bytes(), "photo.jpg", upload_id="up-1", provider_name=_FAKE_MODULE_PATH)
    assert out["pages"][0]["refusal"]["code"] == HANDWRITTEN_VISION_PROVIDER_NOT_CONFIGURED


def test_fake_build_provider_raises_unavailable_without_env(monkeypatch):
    monkeypatch.delenv("TL2_HANDWRITTEN_FAKE_FIXTURES", raising=False)
    with pytest.raises(ProviderUnavailable):
        fake_provider.build_provider(ProviderConfig(timeout_seconds=5))


def test_fake_provider_happy_path_produces_vision_ocr_rows(tmp_path, monkeypatch):
    """Factory loads fake by dotted path -> fixture read -> VISION_OCR rows flow through
    extract_handwritten exactly like an injected test callable would."""
    monkeypatch.setenv("TL2_HANDWRITTEN_FAKE_FIXTURES", str(tmp_path))
    data = _jpeg_bytes()
    sha = hashlib.sha256(data).hexdigest()
    fixture = {
        "record_format": "trueline-handwritten-page-extraction-1",
        "source": {"upload_id": "up-1", "sha256": sha, "file_name": "photo.jpg",
                  "page_index": 0, "page_count": 1},
        "method": "VISION_OCR",
        "extractor": "fake_vision_fixture",
        "header": _blank_header(),
        "readings": [_reading("0+00", 3.5, 5.0, row_index=0), _reading("0+50", 3.5, 5.0, row_index=1)],
        "page_status": "EXTRACTED", "refusal": None, "warnings": [], "audit": [],
    }
    (tmp_path / ("%s-p0.json" % sha)).write_text(json.dumps(fixture), encoding="utf-8")

    out = extract_handwritten(data, "photo.jpg", upload_id="up-1", provider_name=_FAKE_MODULE_PATH)
    page = out["pages"][0]
    assert page["page_status"] == EXTRACTED
    assert page["method"] == VISION_OCR
    assert len(out["proposals"]) == 1
    assert out["page_ledger"][0]["status"] == EXTRACTED


def test_fake_provider_missing_fixture_refuses_output_invalid(tmp_path, monkeypatch):
    """No fixture matches this page's sha256/page_index -- an honest refusal, never an invented reading.
    The reason is a FIXED literal, never the raised ProviderOutputInvalid's own message ("no fixture for
    this page") -- that message is untrusted provider-authored text and must never reach the refusal."""
    monkeypatch.setenv("TL2_HANDWRITTEN_FAKE_FIXTURES", str(tmp_path))
    out = extract_handwritten(_jpeg_bytes(), "photo.jpg", upload_id="up-1", provider_name=_FAKE_MODULE_PATH)
    refusal = out["pages"][0]["refusal"]
    assert refusal["code"] == HANDWRITTEN_PROVIDER_OUTPUT_INVALID
    assert refusal["reason"] == "provider returned output that failed validation"
    assert "fixture" not in refusal["reason"]


def test_fake_fixture_may_omit_source_seam_fills_it(tmp_path, monkeypatch):
    """A fixture with NO ``source`` key at all is valid -- the seam force-assigns the real identity."""
    monkeypatch.setenv("TL2_HANDWRITTEN_FAKE_FIXTURES", str(tmp_path))
    data = _jpeg_bytes()
    sha = hashlib.sha256(data).hexdigest()
    fixture = {
        "record_format": "trueline-handwritten-page-extraction-1",
        "method": "VISION_OCR",
        "extractor": "fake_vision_fixture",
        "header": _blank_header(),
        "readings": [_reading("0+00", 3.5, 5.0, row_index=0), _reading("0+50", 3.5, 5.0, row_index=1)],
        "page_status": "EXTRACTED", "refusal": None, "warnings": [], "audit": [],
    }
    assert "source" not in fixture
    (tmp_path / ("%s-p0.json" % sha)).write_text(json.dumps(fixture), encoding="utf-8")

    out = extract_handwritten(data, "photo.jpg", upload_id="up-1", provider_name=_FAKE_MODULE_PATH)
    page = out["pages"][0]
    assert page["page_status"] == EXTRACTED
    assert page["source"] == {"upload_id": "up-1", "sha256": sha, "file_name": "photo.jpg",
                              "page_index": 0, "page_count": 1}


# --------------------------------------------------------------------------- #
# Trust boundary -- the seam NEVER trusts a provider's own source/method/extractor claims. It force-
# assigns all three from its OWN known-good values; a provider-claimed sha256/upload_id/page_index that
# DISAGREES refuses LOUDLY rather than being silently "fixed"; a provider that simply omits ``source``
# is not spoofing anything and gets seam-assigned identity with no refusal.
# --------------------------------------------------------------------------- #
def _full_page_record(source: Dict[str, Any], *, readings=None) -> Dict[str, Any]:
    """A full (test-injection-shaped) HandwrittenPageExtraction a raw provider callable would return."""
    return {
        "record_format": "trueline-handwritten-page-extraction-1",
        "source": dict(source),
        "method": "VISION_OCR",
        "extractor": "provider-claimed-name-must-be-overwritten",
        "header": _blank_header(),
        "readings": readings or [],
        "page_status": "EXTRACTED",
        "refusal": None,
        "warnings": [],
        "audit": [],
    }


def test_provider_omitting_source_entirely_gets_seam_assigned_identity():
    def _fake(png_bytes, context):
        record = _full_page_record(
            {"upload_id": "wrong", "sha256": "wrong", "file_name": "wrong", "page_index": 9, "page_count": 9},
            readings=[_reading("0+00", 3.5, 5.0, row_index=0), _reading("0+50", 3.5, 5.0, row_index=1)])
        del record["source"]  # simulate a provider that returns no source claim at all
        return record

    data = _jpeg_bytes()
    out = extract_handwritten(data, "photo.jpg", upload_id="up-1",
                              provider_name="fake", providers={"fake": _fake})
    page = out["pages"][0]
    assert page["page_status"] == EXTRACTED
    assert page["source"] == {"upload_id": "up-1", "sha256": hashlib.sha256(data).hexdigest(),
                              "file_name": "photo.jpg", "page_index": 0, "page_count": 1}
    assert page["method"] == VISION_OCR
    assert page["extractor"] == "fake"


@pytest.mark.parametrize("field,bad_value", [
    ("sha256", "0" * 64),
    ("upload_id", "someone-elses-upload"),
    ("page_index", 7),
])
def test_provider_spoofed_identity_field_refuses_loudly(field, bad_value):
    def _fake(png_bytes, context):
        source = {"upload_id": context["upload_id"], "sha256": context["sha256"],
                 "file_name": context["file_name"], "page_index": context["page_index"],
                 "page_count": context["page_count"]}
        source[field] = bad_value  # a claim that disagrees with the real, seam-known value
        return _full_page_record(source, readings=[_reading("0+00", 3.5, 5.0, row_index=0),
                                                    _reading("0+50", 3.5, 5.0, row_index=1)])

    out = extract_handwritten(_jpeg_bytes(), "photo.jpg", upload_id="up-1",
                              provider_name="fake", providers={"fake": _fake})
    refusal = out["pages"][0]["refusal"]
    assert refusal["code"] == HANDWRITTEN_PROVIDER_OUTPUT_INVALID
    assert refusal["reason"] == "provider output did not match the requested page"


def test_poisoned_provider_output_invalid_message_never_surfaces_anywhere(caplog):
    """A ProviderOutputInvalid raised with a poisoned message (a fake URL+token) must NEVER appear in the
    extract result, the page ledger, or any captured log record -- only the FIXED literal reason."""
    poisoned = "leaked at https://internal.example/secret?token=SHOULD-NEVER-APPEAR-ANYWHERE"

    def _fake(png_bytes, context):
        raise ProviderOutputInvalid(poisoned)

    with caplog.at_level(logging.INFO, logger="truelinev2.extract.vision_providers"):
        out = extract_handwritten(_jpeg_bytes(), "photo.jpg", upload_id="up-1",
                                  provider_name="fake", providers={"fake": _fake})

    refusal = out["pages"][0]["refusal"]
    assert refusal["code"] == HANDWRITTEN_PROVIDER_OUTPUT_INVALID
    assert refusal["reason"] == "provider returned output that failed validation"
    assert poisoned not in refusal["reason"]
    assert poisoned not in json.dumps(out)  # never anywhere in the extract result (pages/proposals/ledger)
    log_text = "\n".join(record.getMessage() for record in caplog.records)
    assert poisoned not in log_text
    assert "SHOULD-NEVER-APPEAR-ANYWHERE" not in log_text


# --------------------------------------------------------------------------- #
# Anthropic adapter -- offline via a FAKE anthropic module injected into sys.modules.
# --------------------------------------------------------------------------- #
def _make_fake_anthropic_module(*, client_cls=None) -> types.ModuleType:
    """A minimal stand-in for the real ``anthropic`` package: exception classes the adapter's retry
    classifier checks by isinstance, plus an ``Anthropic`` client constructor. Never touches a network."""
    mod = types.ModuleType("anthropic")

    class RateLimitError(Exception):
        pass

    class InternalServerError(Exception):
        pass

    class APIConnectionError(Exception):
        pass

    class AuthenticationError(Exception):
        pass

    mod.RateLimitError = RateLimitError
    mod.InternalServerError = InternalServerError
    mod.APIConnectionError = APIConnectionError
    mod.AuthenticationError = AuthenticationError
    mod.Anthropic = client_cls or (lambda **kwargs: types.SimpleNamespace(messages=None))
    return mod


def _tool_use_block(tool_input: dict) -> types.SimpleNamespace:
    return types.SimpleNamespace(type="tool_use", name="record_bore_log_page_extraction", input=tool_input)


def _fake_response(content, stop_reason: str = "tool_use") -> types.SimpleNamespace:
    return types.SimpleNamespace(content=content, stop_reason=stop_reason)


def test_anthropic_adapter_missing_sdk_raises_unavailable(monkeypatch):
    monkeypatch.setitem(sys.modules, "anthropic", None)  # forces ImportError on `import anthropic`
    with pytest.raises(ProviderUnavailable):
        anthropic_messages.build_provider(ProviderConfig(timeout_seconds=5))


def test_anthropic_adapter_missing_model_env_raises_unavailable(monkeypatch):
    monkeypatch.setitem(sys.modules, "anthropic", _make_fake_anthropic_module())
    monkeypatch.delenv("TL2_HANDWRITTEN_VISION_MODEL", raising=False)
    with pytest.raises(ProviderUnavailable):
        anthropic_messages.build_provider(ProviderConfig(timeout_seconds=5))


def test_anthropic_adapter_missing_model_env_refuses_not_configured_via_seam(monkeypatch):
    monkeypatch.setitem(sys.modules, "anthropic", _make_fake_anthropic_module())
    monkeypatch.delenv("TL2_HANDWRITTEN_VISION_MODEL", raising=False)
    out = extract_handwritten(_jpeg_bytes(), "photo.jpg", upload_id="up-1",
                              provider_name=_ANTHROPIC_MODULE_PATH)
    assert out["pages"][0]["refusal"]["code"] == HANDWRITTEN_VISION_PROVIDER_NOT_CONFIGURED


def test_anthropic_adapter_happy_path_via_injected_client(monkeypatch):
    monkeypatch.setitem(sys.modules, "anthropic", _make_fake_anthropic_module())
    monkeypatch.setenv("TL2_HANDWRITTEN_VISION_MODEL", "test-model-id")

    calls = []

    class _Messages:
        def create(self, **kwargs):
            calls.append(kwargs)
            return _fake_response([_tool_use_block(_valid_tool_input())])

    class _Client:
        def __init__(self, timeout=None):
            self.messages = _Messages()

    fn = anthropic_messages.build_provider(ProviderConfig(timeout_seconds=5), client_factory=_Client)
    context = {"upload_id": "up-1", "sha256": "a" * 64, "file_name": "photo.jpg",
              "page_index": 0, "page_count": 1}
    record = fn(b"\x89PNG-not-real-bytes", context)

    assert record["page_status"] == "EXTRACTED"
    assert record["method"] == VISION_OCR
    assert record["extractor"] == "anthropic_messages"
    assert record["source"] == {"upload_id": "up-1", "sha256": "a" * 64, "file_name": "photo.jpg",
                                "page_index": 0, "page_count": 1}
    assert len(calls) == 1
    assert calls[0]["model"] == "test-model-id"       # model id came straight from env, never hardcoded


def test_anthropic_adapter_client_factory_receives_derived_sdk_timeout(monkeypatch):
    """The adapter's client_factory is called with ONE positional arg -- the SDK request timeout derived
    from config.timeout_seconds (seam budget minus margin, floored) -- since that timeout, not the seam's
    abandon-only thread-join, is what actually bounds a hung request."""
    monkeypatch.setitem(sys.modules, "anthropic", _make_fake_anthropic_module())
    monkeypatch.setenv("TL2_HANDWRITTEN_VISION_MODEL", "test-model-id")

    received = []

    def _client_factory(timeout):
        received.append(timeout)
        messages = types.SimpleNamespace(create=lambda **kw: _fake_response([_tool_use_block(_valid_tool_input())]))
        return types.SimpleNamespace(messages=messages)

    fn = anthropic_messages.build_provider(ProviderConfig(timeout_seconds=90), client_factory=_client_factory)
    context = {"upload_id": "up-1", "sha256": "a" * 64, "file_name": "photo.jpg",
              "page_index": 0, "page_count": 1}
    fn(b"png-bytes", context)

    assert received == [85.0]  # max(90 - margin(5), floor(5)) == 85


def test_anthropic_adapter_retries_429_then_succeeds(monkeypatch):
    fake_mod = _make_fake_anthropic_module()
    monkeypatch.setitem(sys.modules, "anthropic", fake_mod)
    monkeypatch.setenv("TL2_HANDWRITTEN_VISION_MODEL", "test-model-id")

    class _Messages:
        def __init__(self):
            self.calls = 0

        def create(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise fake_mod.RateLimitError("rate limited")
            return _fake_response([_tool_use_block(_valid_tool_input())])

    class _Client:
        def __init__(self):
            self.messages = _Messages()

    client = _Client()
    # timeout_seconds=10 -> sdk_timeout=max(10-5,5)=5 -> max_attempts=max(1,min(3,10//5))=2: exactly
    # enough budget-bounded attempts to prove a retry-then-succeed, per _derive_max_attempts.
    fn = anthropic_messages.build_provider(ProviderConfig(timeout_seconds=10),
                                           client_factory=lambda timeout: client)
    attempts_seen = []
    context = {"upload_id": "up-1", "sha256": "a" * 64, "file_name": "photo.jpg",
              "page_index": 0, "page_count": 1, "report_attempts": attempts_seen.append}

    record = fn(b"png-bytes", context)

    assert record["page_status"] == "EXTRACTED"
    assert client.messages.calls == 2
    assert attempts_seen == [1, 2]


def test_anthropic_adapter_auth_4xx_no_retry_maps_to_provider_error_via_seam(monkeypatch):
    fake_mod = _make_fake_anthropic_module()

    class _Messages:
        def __init__(self):
            self.calls = 0

        def create(self, **kwargs):
            self.calls += 1
            raise fake_mod.AuthenticationError("invalid api key -- must never appear in the refusal reason")

    class _Client:
        def __init__(self, **kwargs):
            self.messages = _Messages()

    fake_mod.Anthropic = _Client
    monkeypatch.setitem(sys.modules, "anthropic", fake_mod)
    monkeypatch.setenv("TL2_HANDWRITTEN_VISION_MODEL", "test-model-id")

    out = extract_handwritten(_jpeg_bytes(), "photo.jpg", upload_id="up-1",
                              provider_name=_ANTHROPIC_MODULE_PATH)
    refusal = out["pages"][0]["refusal"]
    assert refusal["code"] == HANDWRITTEN_PROVIDER_ERROR
    assert "AuthenticationError" in refusal["reason"]
    assert "invalid api key" not in refusal["reason"]
    assert "leak" not in refusal["reason"]


def test_anthropic_adapter_generic_raise_maps_to_provider_error_class_name_only(monkeypatch):
    fake_mod = _make_fake_anthropic_module()

    class _Messages:
        def create(self, **kwargs):
            raise RuntimeError("boom -- must never leak into the refusal reason")

    class _Client:
        def __init__(self, **kwargs):
            self.messages = _Messages()

    fake_mod.Anthropic = _Client
    monkeypatch.setitem(sys.modules, "anthropic", fake_mod)
    monkeypatch.setenv("TL2_HANDWRITTEN_VISION_MODEL", "test-model-id")

    out = extract_handwritten(_jpeg_bytes(), "photo.jpg", upload_id="up-1",
                              provider_name=_ANTHROPIC_MODULE_PATH)
    refusal = out["pages"][0]["refusal"]
    assert refusal["code"] == HANDWRITTEN_PROVIDER_ERROR
    assert refusal["reason"].endswith("RuntimeError")
    assert "boom" not in refusal["reason"]


def test_anthropic_adapter_malformed_output_refuses_output_invalid(monkeypatch):
    monkeypatch.setitem(sys.modules, "anthropic", _make_fake_anthropic_module())
    monkeypatch.setenv("TL2_HANDWRITTEN_VISION_MODEL", "test-model-id")

    class _Messages:
        def create(self, **kwargs):
            # No tool_use block -- the model ignored the forced tool_choice (should not happen, but the
            # adapter must refuse honestly rather than guess).
            return _fake_response([types.SimpleNamespace(type="text", text="oops")])

    class _Client:
        def __init__(self, timeout=None):
            self.messages = _Messages()

    fn = anthropic_messages.build_provider(ProviderConfig(timeout_seconds=5), client_factory=_Client)
    context = {"upload_id": "up-1", "sha256": "a" * 64, "file_name": "photo.jpg",
              "page_index": 0, "page_count": 1}
    with pytest.raises(ProviderOutputInvalid):
        fn(b"png-bytes", context)


def test_anthropic_adapter_model_refusal_stop_reason_refuses_output_invalid(monkeypatch):
    monkeypatch.setitem(sys.modules, "anthropic", _make_fake_anthropic_module())
    monkeypatch.setenv("TL2_HANDWRITTEN_VISION_MODEL", "test-model-id")

    class _Messages:
        def create(self, **kwargs):
            return _fake_response([], stop_reason="refusal")

    class _Client:
        def __init__(self, timeout=None):
            self.messages = _Messages()

    fn = anthropic_messages.build_provider(ProviderConfig(timeout_seconds=5), client_factory=_Client)
    context = {"upload_id": "up-1", "sha256": "a" * 64, "file_name": "photo.jpg",
              "page_index": 0, "page_count": 1}
    with pytest.raises(ProviderOutputInvalid):
        fn(b"png-bytes", context)


# --------------------------------------------------------------------------- #
# Log hygiene -- neither the API key env value nor image bytes ever appear in a log record.
# --------------------------------------------------------------------------- #
def test_log_hygiene_no_secret_or_image_bytes_in_log_records(monkeypatch, caplog):
    secret_value = "sk-super-secret-value-must-never-appear-in-logs"
    monkeypatch.setenv("ANTHROPIC_API_KEY", secret_value)
    monkeypatch.setenv("TL2_HANDWRITTEN_VISION_MODEL", "test-model-id")
    fake_mod = _make_fake_anthropic_module()

    class _Messages:
        def create(self, **kwargs):
            return _fake_response([_tool_use_block(_valid_tool_input())])

    class _Client:
        def __init__(self, **kwargs):
            self.messages = _Messages()

    fake_mod.Anthropic = _Client
    monkeypatch.setitem(sys.modules, "anthropic", fake_mod)

    image_bytes = _jpeg_bytes()
    with caplog.at_level(logging.INFO, logger="truelinev2.extract.vision_providers"):
        out = extract_handwritten(image_bytes, "photo.jpg", upload_id="up-1",
                                  provider_name=_ANTHROPIC_MODULE_PATH)

    assert out["pages"][0]["page_status"] == "EXTRACTED"
    log_text = "\n".join(record.getMessage() for record in caplog.records)
    assert secret_value not in log_text
    assert image_bytes.decode("latin-1") not in log_text
    assert "vision provider call" in log_text
    assert "attempts=1" in log_text
    assert "outcome=EXTRACTED" in log_text
