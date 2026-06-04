"""Focused unit tests for the default-OFF MRQ PDF-first evidence cache.

PDF-FREE / no main import: exercises the cache wrapper with a fake builder (call counter),
so it validates miss/hit/invalidation/flag-off WITHOUT running the real PDF-first engine.

COMMAND (from repo root):
    python -m pytest backend/tests/test_mrq_evidence_cache.py -v
"""
from __future__ import annotations

import os

os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from app.core import mrq_evidence_cache as C


def _counting_builder():
    calls = {"n": 0}

    def builder(plan_pdf, committed_rows, card_out_dir=None):
        calls["n"] += 1
        return {"schema_version": "test", "build_no": calls["n"], "rows": len(list(committed_rows))}

    return calls, builder


ROWS_A = [{"source_file": "bore_log56.xlsx", "station": "0+00", "boc": 11}]
ROWS_B = [{"source_file": "bore_log56.xlsx", "station": "1+00", "boc": 11}]


def setup_function(_fn):
    C.clear()


def _pdf(tmp_path, content=b"%PDF-1.4 plan"):
    p = tmp_path / "plan.pdf"
    p.write_bytes(content)
    return str(p)


def test_flag_off_always_builds(tmp_path, monkeypatch):
    monkeypatch.delenv(C.CACHE_FLAG, raising=False)
    pdf = _pdf(tmp_path)
    calls, builder = _counting_builder()
    C.get_or_build("s1", ROWS_A, pdf, None, builder)
    C.get_or_build("s1", ROWS_A, pdf, None, builder)
    assert calls["n"] == 2  # OFF -> no caching, byte-identical to prior behavior


def test_cache_miss_then_hit(tmp_path, monkeypatch):
    monkeypatch.setenv(C.CACHE_FLAG, "1")
    pdf = _pdf(tmp_path)
    calls, builder = _counting_builder()
    p1 = C.get_or_build("s1", ROWS_A, pdf, None, builder)   # miss -> build
    p2 = C.get_or_build("s1", ROWS_A, pdf, None, builder)   # hit -> cached
    assert calls["n"] == 1
    assert p1 is p2  # same cached object, not rebuilt


def test_committed_rows_change_invalidates(tmp_path, monkeypatch):
    monkeypatch.setenv(C.CACHE_FLAG, "1")
    pdf = _pdf(tmp_path)
    calls, builder = _counting_builder()
    C.get_or_build("s1", ROWS_A, pdf, None, builder)
    C.get_or_build("s1", ROWS_B, pdf, None, builder)   # different rows -> rebuild
    assert calls["n"] == 2


def test_plan_identity_change_invalidates(tmp_path, monkeypatch):
    monkeypatch.setenv(C.CACHE_FLAG, "1")
    pdf = _pdf(tmp_path, b"%PDF-1.4 v1")
    calls, builder = _counting_builder()
    C.get_or_build("s1", ROWS_A, pdf, None, builder)
    # Rewrite the plan PDF (size changes) -> identity changes -> rebuild.
    with open(pdf, "wb") as fh:
        fh.write(b"%PDF-1.4 v2-longer-content")
    C.get_or_build("s1", ROWS_A, pdf, None, builder)
    assert calls["n"] == 2


def test_output_flag_flip_invalidates(tmp_path, monkeypatch):
    monkeypatch.setenv(C.CACHE_FLAG, "1")
    pdf = _pdf(tmp_path)
    calls, builder = _counting_builder()
    monkeypatch.setenv("TRUELINE_CROSS_SHEET_SEAM_STITCH", "0")
    C.get_or_build("s1", ROWS_A, pdf, None, builder)
    monkeypatch.setenv("TRUELINE_CROSS_SHEET_SEAM_STITCH", "1")   # output flag flip -> rebuild
    C.get_or_build("s1", ROWS_A, pdf, None, builder)
    assert calls["n"] == 2


def test_distinct_sessions_isolated(tmp_path, monkeypatch):
    monkeypatch.setenv(C.CACHE_FLAG, "1")
    pdf = _pdf(tmp_path)
    calls, builder = _counting_builder()
    C.get_or_build("s1", ROWS_A, pdf, None, builder)
    C.get_or_build("s2", ROWS_A, pdf, None, builder)   # different session -> own build
    assert calls["n"] == 2
    C.get_or_build("s1", ROWS_A, pdf, None, builder)   # s1 still cached
    assert calls["n"] == 2


def test_falsy_payload_not_cached(tmp_path, monkeypatch):
    monkeypatch.setenv(C.CACHE_FLAG, "1")
    pdf = _pdf(tmp_path)

    def none_builder(plan_pdf, committed_rows, card_out_dir=None):
        return None

    C.get_or_build("s1", ROWS_A, pdf, None, none_builder)   # None -> not cached
    calls, builder = _counting_builder()
    C.get_or_build("s1", ROWS_A, pdf, None, builder)        # rebuilds (nothing cached)
    assert calls["n"] == 1


# ── observability metadata (additive meta_out; payload behavior unchanged) ────
def test_meta_flag_off_reports_disabled(tmp_path, monkeypatch):
    monkeypatch.delenv(C.CACHE_FLAG, raising=False)
    pdf = _pdf(tmp_path)
    _calls, builder = _counting_builder()
    meta = {}
    C.get_or_build("s1", ROWS_A, pdf, None, builder, meta_out=meta)
    assert meta["cache_enabled"] is False
    assert meta["cache_hit"] is None            # n/a when disabled
    assert meta["cache_key_short"] is None      # no key computed when disabled
    assert meta["artifact_render_skipped"] is False
    assert meta["sessions_cached"] == 0
    assert isinstance(meta["evidence_build_ms"], float) and meta["evidence_build_ms"] >= 0.0


def test_meta_miss_then_hit_reports_render_skipped(tmp_path, monkeypatch):
    monkeypatch.setenv(C.CACHE_FLAG, "1")
    pdf = _pdf(tmp_path)
    _calls, builder = _counting_builder()
    m1, m2 = {}, {}
    C.get_or_build("s1", ROWS_A, pdf, None, builder, meta_out=m1)   # miss -> build
    C.get_or_build("s1", ROWS_A, pdf, None, builder, meta_out=m2)   # hit -> cached
    assert m1["cache_enabled"] is True and m1["cache_hit"] is False
    assert m1["artifact_render_skipped"] is False                   # built -> PNGs rendered
    assert m1["sessions_cached"] == 1
    assert m2["cache_hit"] is True
    assert m2["artifact_render_skipped"] is True                    # hit -> PNG re-render skipped
    assert m2["evidence_build_ms"] == 0.0
    assert m1["cache_key_short"] and m1["cache_key_short"] == m2["cache_key_short"]
    assert len(m1["cache_key_short"]) == 12


def test_meta_key_short_changes_with_rows(tmp_path, monkeypatch):
    monkeypatch.setenv(C.CACHE_FLAG, "1")
    pdf = _pdf(tmp_path)
    _calls, builder = _counting_builder()
    ma, mb = {}, {}
    C.get_or_build("s1", ROWS_A, pdf, None, builder, meta_out=ma)
    C.get_or_build("s1", ROWS_B, pdf, None, builder, meta_out=mb)
    assert ma["cache_key_short"] != mb["cache_key_short"]


def test_meta_out_is_optional_backcompat(tmp_path, monkeypatch):
    # Callers that pass NO meta_out keep working and get the same cached object.
    monkeypatch.setenv(C.CACHE_FLAG, "1")
    pdf = _pdf(tmp_path)
    _calls, builder = _counting_builder()
    p1 = C.get_or_build("s1", ROWS_A, pdf, None, builder)
    p2 = C.get_or_build("s1", ROWS_A, pdf, None, builder)
    assert p1 is p2
