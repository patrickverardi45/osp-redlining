"""Unit tests for the PDF-first Match Review evidence cache.

Targets ``backend/app/core/pdf_first_evidence_cache.py`` (the pure cache module)
plus the endpoint flag helper ``_trueline_mrq_evidence_cache_enabled`` in
backend/main.py.

Proves:
  * compute_signature determinism (same inputs -> same sig) AND sensitivity
    (changed committed_rows OR changed flag stack -> different sig; new plan set
    -> different sig).
  * cache_read returns None on: file absent, schema mismatch, signature
    mismatch, and a referenced PNG basename missing on disk. Hit returns the
    cached envelope.
  * On a HIT the generator is NOT called; on a MISS it IS called (mirrors the
    endpoint's skip-regeneration wrapper with a stub generator).
  * The kill switch (TRUELINE_MRQ_EVIDENCE_CACHE_DISABLE) forces a read miss
    and a write no-op.
  * Flag-OFF path: the endpoint helper defaults False, so the endpoint never
    consults the cache.

COMMAND (from repo root):
    venv\\Scripts\\python.exe -m pytest backend/tests/test_pdf_first_evidence_cache.py -q
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

# Auth env defaults so importing backend.main (for the flag-helper test) is safe.
os.environ.setdefault("TRUELINE_JWT_SECRET", "pf-evcache-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "pf-evcache-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend.app.core import pdf_first_evidence_cache as C  # noqa: E402


SID = "sess-evcache-1"
PSS = "plan-set-sig-abc"


def _rows():
    return [
        {"source_file": "bore_log58.xlsx", "station": "10+00", "print": "P1",
         "depth_ft": 5.0, "notes": "", "id": "vol-1", "score": 0.9},
        {"source_file": "bore_log58.xlsx", "station": "13+50", "print": "P1",
         "depth_ft": 6.0, "notes": "deep", "id": "vol-2", "score": 0.4},
    ]


def _flags(**over):
    base = {name: "" for name in C.FLAG_STACK_ENV_VARS}
    base.update(over)
    return base


def _envelope(png_names):
    """A minimal evidence-envelope-shaped dict that references PNG basenames the
    same way the adapter does (card render_artifact_ref + overlay artifact_refs)."""
    return {
        "schema_version": "x",
        "status": "OK",
        "placements": [
            {"segment_id": "s1", "render_artifact_ref": png_names[0]},
        ],
        "review_items": [
            {"segment_id": "s2",
             "pdf_path_trace": {"artifact_refs": list(png_names[1:]),
                                "artifact_name": png_names[1] if len(png_names) > 1 else None}},
        ],
        "fail_safe": [],
    }


@pytest.fixture(autouse=True)
def _clear_kill_switch(monkeypatch):
    """Default every test to kill-switch OFF unless it sets it explicitly."""
    monkeypatch.delenv(C.KILL_SWITCH_ENV, raising=False)
    # Also clear the flag stack so compute_signature's live read is deterministic
    # for tests that do not pass an explicit flag_stack.
    for name in C.FLAG_STACK_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    yield


# ── compute_signature ───────────────────────────────────────────────────────

def test_signature_deterministic():
    a = C.compute_signature(SID, PSS, _rows(), _flags())
    b = C.compute_signature(SID, PSS, _rows(), _flags())
    assert a == b
    assert isinstance(a, str) and len(a) == 64  # sha256 hexdigest


def test_signature_changes_on_committed_rows():
    base = C.compute_signature(SID, PSS, _rows(), _flags())
    rows2 = _rows()
    rows2[0]["station"] = "11+00"  # an evidence-affecting field
    assert C.compute_signature(SID, PSS, rows2, _flags()) != base


def test_signature_ignores_volatile_row_fields():
    """Changing a NON-evidence field (id/score) must NOT change the signature."""
    base = C.compute_signature(SID, PSS, _rows(), _flags())
    rows2 = _rows()
    rows2[0]["id"] = "vol-999"
    rows2[1]["score"] = 0.01
    assert C.compute_signature(SID, PSS, rows2, _flags()) == base


def test_signature_changes_on_flag_stack():
    base = C.compute_signature(SID, PSS, _rows(), _flags())
    flipped = _flags(TRUELINE_MATCHLINE_FRAME_RESOLVER="1")
    assert C.compute_signature(SID, PSS, _rows(), flipped) != base


def test_signature_changes_on_plan_set():
    base = C.compute_signature(SID, PSS, _rows(), _flags())
    assert C.compute_signature(SID, "plan-set-sig-DIFFERENT", _rows(), _flags()) != base


def test_signature_reads_live_flag_stack_when_not_passed(monkeypatch):
    """A new upload OR flag change invalidates: prove the live env flag stack is
    folded into the signature when no explicit flag_stack is given."""
    sig_off = C.compute_signature(SID, PSS, _rows(), None)
    monkeypatch.setenv("TRUELINE_PDF_PATH_TRACE_DASH_CHAIN", "1")
    sig_on = C.compute_signature(SID, PSS, _rows(), None)
    assert sig_off != sig_on


# ── cache_path ──────────────────────────────────────────────────────────────

def test_cache_path_layout(tmp_path):
    p = C.cache_path(tmp_path, SID)
    assert p == tmp_path / "pdf_first_cards" / SID / "_evidence_cache.json"


# ── cache_read / cache_write round trip + miss reasons ──────────────────────

def test_read_miss_when_absent(tmp_path):
    p = C.cache_path(tmp_path, SID)
    assert C.cache_read(p, "sig") is None


def test_write_then_read_hit(tmp_path):
    p = C.cache_path(tmp_path, SID)
    cards = p.parent
    cards.mkdir(parents=True, exist_ok=True)
    pngs = ["card_s1.png", "trace_s2.png"]
    for n in pngs:
        (cards / n).write_bytes(b"\x89PNG\r\n\x1a\n")
    env = _envelope(pngs)
    assert C.cache_write(p, "sig-1", env) is True
    got = C.cache_read(p, "sig-1")
    assert got == env


def test_read_miss_on_signature_mismatch(tmp_path):
    p = C.cache_path(tmp_path, SID)
    p.parent.mkdir(parents=True, exist_ok=True)
    (p.parent / "card_s1.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (p.parent / "trace_s2.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    C.cache_write(p, "sig-1", _envelope(["card_s1.png", "trace_s2.png"]))
    assert C.cache_read(p, "sig-DIFFERENT") is None


def test_read_miss_on_schema_mismatch(tmp_path):
    p = C.cache_path(tmp_path, SID)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "schema_version": "WRONG-SCHEMA",
        "signature": "sig-1",
        "envelope": _envelope(["card_s1.png"]),
    }), encoding="utf-8")
    assert C.cache_read(p, "sig-1") is None


def test_read_miss_when_referenced_png_missing(tmp_path):
    p = C.cache_path(tmp_path, SID)
    cards = p.parent
    cards.mkdir(parents=True, exist_ok=True)
    # Write only ONE of the two referenced PNGs -> the missing one forces a miss.
    (cards / "card_s1.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    env = _envelope(["card_s1.png", "trace_s2.png"])  # trace_s2.png intentionally absent
    C.cache_write(p, "sig-1", env)
    assert C.cache_read(p, "sig-1") is None


def test_read_miss_on_corrupt_json(tmp_path):
    p = C.cache_path(tmp_path, SID)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{ not valid json", encoding="utf-8")
    assert C.cache_read(p, "sig-1") is None


# ── kill switch ─────────────────────────────────────────────────────────────

def test_kill_switch_forces_read_miss_and_write_noop(tmp_path, monkeypatch):
    p = C.cache_path(tmp_path, SID)
    cards = p.parent
    cards.mkdir(parents=True, exist_ok=True)
    (cards / "card_s1.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    env = _envelope(["card_s1.png"])
    # Write a valid cache while the switch is OFF, prove it is a hit.
    assert C.cache_write(p, "sig-1", env) is True
    assert C.cache_read(p, "sig-1") == env
    # Now flip the kill switch: read misses and write no-ops.
    monkeypatch.setenv(C.KILL_SWITCH_ENV, "1")
    assert C.cache_read(p, "sig-1") is None
    assert C.cache_write(p, "sig-1", env) is False


# ── generator skipped on hit, called on miss (endpoint wrapper semantics) ────

class _StubGenerator:
    """Stands in for build_session_evidence_from_committed_rows."""

    def __init__(self, envelope):
        self.calls = 0
        self._envelope = envelope

    def __call__(self, *args, **kwargs):
        self.calls += 1
        return self._envelope


def _resolve_evidence_like_endpoint(cache_file, signature, generator):
    """Mirror the endpoint's cache-ON wrapper: read -> on miss call generator +
    write -> return envelope. Lets us assert the generator call-count contract
    without standing up the full FastAPI app."""
    ev = C.cache_read(cache_file, signature)
    if ev is None:
        ev = generator()
        if ev:
            C.cache_write(cache_file, signature, ev)
    return ev


def test_generator_called_on_miss_then_skipped_on_hit(tmp_path):
    p = C.cache_path(tmp_path, SID)
    cards = p.parent
    cards.mkdir(parents=True, exist_ok=True)
    pngs = ["card_s1.png", "trace_s2.png"]
    for n in pngs:
        (cards / n).write_bytes(b"\x89PNG\r\n\x1a\n")
    gen = _StubGenerator(_envelope(pngs))

    # First load: miss -> generator runs once, result cached.
    out1 = _resolve_evidence_like_endpoint(p, "sig-1", gen)
    assert out1 == _envelope(pngs)
    assert gen.calls == 1

    # Second load (same signature): hit -> generator NOT called again.
    out2 = _resolve_evidence_like_endpoint(p, "sig-1", gen)
    assert out2 == _envelope(pngs)
    assert gen.calls == 1  # unchanged -> regeneration was skipped

    # Signature change (new upload / flag change): miss -> generator runs again.
    out3 = _resolve_evidence_like_endpoint(p, "sig-2", gen)
    assert out3 == _envelope(pngs)
    assert gen.calls == 2


# ── flag-OFF endpoint helper: default OFF, cache untouched ──────────────────

def test_endpoint_flag_defaults_off_and_cache_untouched(monkeypatch):
    """The endpoint gate defaults OFF; when OFF the endpoint must not consult the
    cache. We assert the helper is False by default and that compute_signature is
    never invoked on the flag-OFF path (sentinel guard)."""
    monkeypatch.delenv("TRUELINE_MRQ_EVIDENCE_CACHE", raising=False)
    from backend import main as M
    assert M._trueline_mrq_evidence_cache_enabled() is False

    # Truthy values flip it on; everything else stays off.
    for val in ("1", "true", "yes", "on", "TRUE", "On"):
        monkeypatch.setenv("TRUELINE_MRQ_EVIDENCE_CACHE", val)
        assert M._trueline_mrq_evidence_cache_enabled() is True
    for val in ("", "0", "false", "no", "off", "nope"):
        monkeypatch.setenv("TRUELINE_MRQ_EVIDENCE_CACHE", val)
        assert M._trueline_mrq_evidence_cache_enabled() is False


def test_flag_off_path_does_not_touch_cache(tmp_path, monkeypatch):
    """Simulate the endpoint's structure: when the cache flag is OFF, neither
    cache_read nor compute_signature is called — the generator runs unconditionally
    (byte-identical to pre-cache behavior)."""
    from backend import main as M
    monkeypatch.delenv("TRUELINE_MRQ_EVIDENCE_CACHE", raising=False)

    touched = {"read": 0, "sig": 0, "write": 0}
    monkeypatch.setattr(C, "cache_read", lambda *a, **k: (touched.__setitem__("read", touched["read"] + 1), None)[1])
    monkeypatch.setattr(C, "compute_signature", lambda *a, **k: (touched.__setitem__("sig", touched["sig"] + 1), "x")[1])
    monkeypatch.setattr(C, "cache_write", lambda *a, **k: (touched.__setitem__("write", touched["write"] + 1), True)[1])

    gen = _StubGenerator(_envelope(["card_s1.png"]))
    # Replicate the endpoint's branch: cache-ON wrapper only runs if the flag is on.
    cache_on = M._trueline_mrq_evidence_cache_enabled()
    if cache_on:
        ev = C.cache_read("ignored", C.compute_signature(SID, PSS, _rows(), None))
        if ev is None:
            ev = gen()
    else:
        ev = gen()  # flag OFF: regenerate exactly as before, cache untouched

    assert cache_on is False
    assert ev == _envelope(["card_s1.png"])
    assert gen.calls == 1
    assert touched == {"read": 0, "sig": 0, "write": 0}  # cache never consulted
