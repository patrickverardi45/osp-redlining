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


def test_station_role_evidence_flag_flip_invalidates(tmp_path, monkeypatch):
    # Item-1 cache-flag gap fix: TRUELINE_STATION_ROLE_EVIDENCE changes the MRQ evidence
    # OUTPUT (adds evidence.station_roles), so flipping it must invalidate the cache.
    monkeypatch.setenv(C.CACHE_FLAG, "1")
    pdf = _pdf(tmp_path)
    calls, builder = _counting_builder()
    monkeypatch.setenv("TRUELINE_STATION_ROLE_EVIDENCE", "0")
    C.get_or_build("s1", ROWS_A, pdf, None, builder)
    monkeypatch.setenv("TRUELINE_STATION_ROLE_EVIDENCE", "1")   # output flag flip -> rebuild
    C.get_or_build("s1", ROWS_A, pdf, None, builder)
    assert calls["n"] == 2


def test_evidence_output_flags_membership_and_key(tmp_path, monkeypatch):
    # Both additive MRQ evidence flags are output-affecting -> in _OUTPUT_FLAGS, and each
    # flip changes the cache key (so a stale payload is never served after a flip).
    assert "TRUELINE_STATION_ROLE_EVIDENCE" in C._OUTPUT_FLAGS
    assert "TRUELINE_PATH_SELECTION_EVIDENCE" in C._OUTPUT_FLAGS   # regression: A.1 still covered
    pdf = _pdf(tmp_path)
    for flag in ("TRUELINE_STATION_ROLE_EVIDENCE", "TRUELINE_PATH_SELECTION_EVIDENCE"):
        monkeypatch.setenv(flag, "0")
        k_off = C.cache_key(ROWS_A, pdf)
        monkeypatch.setenv(flag, "1")
        k_on = C.cache_key(ROWS_A, pdf)
        assert k_off != k_on, flag


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


# ── Item 7 observability: behavior-neutral hit/miss + timing telemetry ──────────────

def test_observer_reports_disabled_when_flag_off(tmp_path, monkeypatch):
    monkeypatch.delenv(C.CACHE_FLAG, raising=False)
    pdf = _pdf(tmp_path)
    _, builder = _counting_builder()
    seen = []
    C.get_or_build("s1", ROWS_A, pdf, None, builder, observer=seen.append)
    assert [e["status"] for e in seen] == ["disabled"]
    assert seen[0]["build_ms"] is not None and seen[0]["elapsed_ms"] is not None
    assert seen[0]["cache_key"] is None  # no key computed in the disabled path


def test_observer_reports_miss_then_hit(tmp_path, monkeypatch):
    monkeypatch.setenv(C.CACHE_FLAG, "1")
    pdf = _pdf(tmp_path)
    _, builder = _counting_builder()
    seen = []
    C.get_or_build("s1", ROWS_A, pdf, None, builder, observer=seen.append)   # miss
    C.get_or_build("s1", ROWS_A, pdf, None, builder, observer=seen.append)   # hit
    assert [e["status"] for e in seen] == ["miss", "hit"]
    assert seen[0]["build_ms"] >= 0.0    # miss timed the real build
    assert seen[1]["build_ms"] == 0.0    # hit skipped the build
    assert all(len(e["cache_key"]) <= 12 for e in seen)  # short prefix only


def test_observer_optional_and_never_breaks(tmp_path, monkeypatch):
    monkeypatch.setenv(C.CACHE_FLAG, "1")
    pdf = _pdf(tmp_path)
    calls, builder = _counting_builder()
    C.get_or_build("s1", ROWS_A, pdf, None, builder)            # no observer -> no error
    def _boom(_info):
        raise RuntimeError("observer blew up")
    p = C.get_or_build("s1", ROWS_A, pdf, None, builder, observer=_boom)  # raising observer swallowed
    assert p is not None and calls["n"] == 1   # still a hit; observer never affected caching


def test_cached_payload_equals_fresh_build(tmp_path, monkeypatch):
    pdf = _pdf(tmp_path)

    def _det_builder(plan_pdf, committed_rows, card_out_dir=None):
        rows = list(committed_rows)
        return {"schema_version": "test", "rows": len(rows),
                "first_station": (rows[0]["station"] if rows else None)}

    monkeypatch.setenv(C.CACHE_FLAG, "1")
    cached = C.get_or_build("s1", ROWS_A, pdf, None, _det_builder)
    cached2 = C.get_or_build("s1", ROWS_A, pdf, None, _det_builder)
    assert cached2 is cached  # served from cache, not rebuilt
    monkeypatch.setenv(C.CACHE_FLAG, "0")
    fresh = C.get_or_build("s1", ROWS_A, pdf, None, _det_builder)  # flag off -> fresh build
    assert cached == fresh  # cached payload is NOT stale: equals an independent fresh build
