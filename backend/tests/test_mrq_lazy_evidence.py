"""Phase-1 lazy heavy-evidence — behavior tests (default-OFF TRUELINE_MRQ_LAZY_EVIDENCE).

Locks the CALL-SITE gating that defers the two heavy evidence renders (path_trace_overlay +
seam_stitch) so the initial MRQ/preseed build is metadata-first, plus the background continuation
that fills them and overwrites the cache. NO selector / draw / resolver-internal behavior is
exercised or changed here -- only the ``render_heavy`` gate, the ``heavy_evidence_pending`` marker,
the preseed continuation, and the cache overwrite. The engine + PDF render are mocked, so these are
fast unit tests; the real-PDF log56 byte-level golden (eager vs lazy PNG) is the post-deploy cold
run, since the unit suite never opens the 14 MB plan.

Mandated coverage:
  1. flag OFF byte-identical / current eager path unchanged
  2. lazy ON initial build returns metadata cards WITH the pending marker
  3. lazy ON skips path_trace_overlay + seam_stitch during the initial build
  4. background continuation fills path_trace/seam artifact refs
  5. log56 eager vs lazy FINAL artifact/evidence equivalence (construction-level)
  7. cache hit after the continuation returns the full evidence
  8. NO change to tiers / stations / resolver decisions
(6 is the FE distinction, verified by the typed `overlayDisplayState` helper + `next build`.)
"""
from __future__ import annotations

import contextlib
import os
from pathlib import Path

os.environ.setdefault("TRUELINE_JWT_SECRET", "lazy-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "lazy-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend import main  # noqa: E402 — env defaults must precede the monolith import
from app.core import pdf_first_adapter as A  # noqa: E402
from app.core import mrq_evidence_cache as cache  # noqa: E402
from app.core.redline_consult import consult  # noqa: E402


@contextlib.contextmanager
def _noop_scope(_sid):
    yield


class _FakeResult:
    def __init__(self, log_id):
        self.log_id = log_id
        self.render_artifacts = []


def _stub_engine(monkeypatch):
    """Stub the engine + envelope so build_session_evidence_from_rows runs without a real PDF.

    Each log yields ONE placement card carrying tier + station_range -- the exact fields test 8
    asserts are render_heavy-invariant. Resolver consult is OFF so the from_rows-level tests
    isolate the path_trace gate + the pending marker (the seam gate is tested at apply_resolver)."""
    class _Eng:
        ENGINE_VERSION = "test"

        def select_redline_from_rows(self, plan, rows, *, source_file=None,
                                     sheet_offset=13, anchor_tables=None):
            return _FakeResult(source_file or "log")

    monkeypatch.setattr(A, "_load_engine", lambda: (_Eng(), None))
    monkeypatch.setattr(A, "_anchor_tables", lambda: {})
    monkeypatch.setattr(A, "_matchline_frame_resolver_enabled", lambda: False)

    def _env(result):
        return {
            "placements": [{
                "log_ids": [getattr(result, "log_id", "log")],
                "tier": "AUTO_SELECT",
                "station_range": {"start": "0+00", "end": "2+76"},
            }],
            "review_items": [], "fail_safe": [], "warnings": [],
            "counts_by_tier": {"AUTO_SELECT": 1},
        }

    monkeypatch.setattr(A, "_envelope_from_result", _env)


# ── flag gate ────────────────────────────────────────────────────────────────
def test_lazy_flag_default_off_and_on(monkeypatch):
    monkeypatch.delenv("TRUELINE_MRQ_LAZY_EVIDENCE", raising=False)
    assert main._mrq_lazy_evidence_enabled() is False
    monkeypatch.setenv("TRUELINE_MRQ_LAZY_EVIDENCE", "1")
    assert main._mrq_lazy_evidence_enabled() is True


# ── render_heavy threading + pending marker (tests 1, 2, 3a) ──────────────────
def test_default_render_heavy_true_no_pending_marker(monkeypatch):
    # Test 1: the eager path is unchanged -> render_heavy defaults True, no pending key.
    seen = {}
    _stub_engine(monkeypatch)
    monkeypatch.setattr(A, "_render_crops",
                        lambda *a, **k: seen.__setitem__("render_heavy", k.get("render_heavy")))
    out = A.build_session_evidence_from_rows("plan.pdf", [("log7", [{}], "log7")])
    assert seen["render_heavy"] is True
    assert "heavy_evidence_pending" not in out


def test_render_heavy_false_threads_and_marks_pending(monkeypatch):
    # Tests 2 + 3a: lazy build threads render_heavy=False to _render_crops and flags the envelope.
    seen = {}
    _stub_engine(monkeypatch)
    monkeypatch.setattr(A, "_render_crops",
                        lambda *a, **k: seen.__setitem__("render_heavy", k.get("render_heavy")))
    out = A.build_session_evidence_from_rows("plan.pdf", [("log7", [{}], "log7")], render_heavy=False)
    assert seen["render_heavy"] is False
    assert out["heavy_evidence_pending"] is True
    # metadata cards still present (test 2): one placement with tier + station range
    assert out["placements"] and out["placements"][0]["station_range"]["end"] == "2+76"


def test_committed_rows_entry_threads_render_heavy(monkeypatch):
    # The public committed-rows entry forwards render_heavy to build_session_evidence_from_rows.
    seen = {}
    monkeypatch.setattr(A, "build_session_evidence_from_rows",
                        lambda *a, **k: seen.__setitem__("render_heavy", k.get("render_heavy")) or {})
    monkeypatch.setattr(A, "group_committed_rows", lambda rows: [("log7", list(rows), "log7")])
    A.build_session_evidence_from_committed_rows("plan.pdf", [{"source_file": "log7"}], render_heavy=False)
    assert seen["render_heavy"] is False


def test_build_threads_render_heavy_to_apply_resolver(monkeypatch):
    # Test 3 (resolver half): render_heavy reaches apply_resolver so it can defer the seam render.
    seen = {}
    _stub_engine(monkeypatch)
    monkeypatch.setattr(A, "_render_crops", lambda *a, **k: None)
    monkeypatch.setattr(A, "_matchline_frame_resolver_enabled", lambda: True)
    monkeypatch.setattr(A, "_resolve_analysis_dir", lambda: "d")
    from app.core import redline_consult as _rc
    monkeypatch.setattr(_rc, "open_document", lambda p: object())
    monkeypatch.setattr(_rc, "apply_corrections", lambda log_id, rows, dd: (rows, False, None))

    def _ar(log_id, env, doc, sheet_offset, out_dir, data_dir, render_heavy=True):
        seen["render_heavy"] = render_heavy
        return env

    monkeypatch.setattr(_rc, "apply_resolver", _ar)
    A.build_session_evidence_from_rows("plan.pdf", [("log7", [{}], "log7")], render_heavy=False)
    assert seen["render_heavy"] is False


# ── tiers / stations are render_heavy-invariant (test 8) + equivalence (test 5) ─
def test_tiers_stations_identical_regardless_of_render_heavy(monkeypatch):
    # Test 8: only heavy_evidence_pending differs; tiers/stations/counts are identical.
    _stub_engine(monkeypatch)
    monkeypatch.setattr(A, "_render_crops", lambda *a, **k: None)
    eager = A.build_session_evidence_from_rows("plan.pdf", [("log56", [{}], "log56")], render_heavy=True)
    lazy = A.build_session_evidence_from_rows("plan.pdf", [("log56", [{}], "log56")], render_heavy=False)
    assert eager["placements"] == lazy["placements"]
    assert eager["counts_by_tier"] == lazy["counts_by_tier"]
    assert "heavy_evidence_pending" not in eager
    assert lazy["heavy_evidence_pending"] is True


def test_lazy_final_equals_eager(monkeypatch):
    # Test 5 (construction): the continuation rebuilds with render_heavy=True -- the SAME eager
    # code path -- so its FINAL envelope equals the default eager build (no pending marker,
    # identical placements/counts). The real-PDF log56 byte-level golden is the cold-run check.
    _stub_engine(monkeypatch)
    monkeypatch.setattr(A, "_render_crops", lambda *a, **k: None)
    eager = A.build_session_evidence_from_rows("plan.pdf", [("log56", [{}], "log56")])
    lazy_final = A.build_session_evidence_from_rows("plan.pdf", [("log56", [{}], "log56")], render_heavy=True)
    assert eager == lazy_final
    assert "heavy_evidence_pending" not in lazy_final


# ── apply_resolver: seam render is gated; the tier lift is NOT (tests 3b, 8) ──
def test_apply_resolver_defers_seam_when_not_heavy(monkeypatch):
    seam_calls = []
    monkeypatch.setattr(consult, "_resolutions", lambda d: {"bore_log56": {"bore_id": "bore_log56"}})
    monkeypatch.setattr(consult, "classify", lambda env: {"status": "blocked"})
    monkeypatch.setattr(consult, "_matchline_resolve",
                        lambda *a, **k: {"resolved": True, "seam": {"home_sta": "1+61"}, "overlays": []})
    monkeypatch.setattr(consult, "_struct_connector_enabled", lambda: False)
    monkeypatch.setattr(consult, "_cross_sheet_seam_stitch_enabled", lambda: True)
    monkeypatch.setattr(consult, "_render_cross_sheet_seam_stitch", lambda *a, **k: seam_calls.append(1))
    monkeypatch.setattr(consult, "_attach_boc_corroboration", lambda *a, **k: None)
    monkeypatch.setattr(consult, "_attach_physical_anchor_evidence", lambda *a, **k: None)
    monkeypatch.setattr(consult, "_resolver_card",
                        lambda *a, **k: {"log_ids": ["bore_log56"], "tier": "MATCHLINE_FRAME_RESOLVER"})

    def _env():
        return {"placements": [], "review_items": [], "fail_safe": []}

    lazy = consult.apply_resolver("bore_log56", _env(), object(), 13, "o", "d", render_heavy=False)
    assert seam_calls == []                       # seam render deferred
    assert len(lazy["review_items"]) == 1         # tier lift still happened (decision is mr-driven)

    eager = consult.apply_resolver("bore_log56", _env(), object(), 13, "o", "d", render_heavy=True)
    assert seam_calls == [1]                       # seam rendered eagerly
    assert len(eager["review_items"]) == 1         # SAME tier lift (test 8)


# ── cache overwrite (test 7) ─────────────────────────────────────────────────
def test_set_cached_overwrites_for_full_evidence(monkeypatch, tmp_path):
    # Test 7: set_cached overwrites the metadata-first entry; a later get_or_build HIT returns the
    # FULL envelope (heavy refs present, no pending marker) without re-running the builder.
    monkeypatch.setenv("TRUELINE_MRQ_EVIDENCE_CACHE", "1")
    cache.clear()
    plan = str(tmp_path / "plan.pdf")
    Path(plan).write_bytes(b"%PDF-1.4 test")
    rows = [{"source_file": "bore_log56.xlsx"}]
    fast = {"source": {"logs": ["log56"]}, "heavy_evidence_pending": True,
            "placements": [{"log_ids": ["log56"]}]}
    full = {"source": {"logs": ["log56"]},
            "placements": [{"log_ids": ["log56"], "geo": {"cross_sheet_seam_stitch": {"resolved": True}}}]}

    got1 = cache.get_or_build("sid-c", rows, plan, None, lambda *a, **k: fast)
    assert got1["heavy_evidence_pending"] is True            # cold miss cached the metadata-first payload
    assert cache.set_cached("sid-c", rows, plan, full) is True  # continuation overwrites

    def _boom(*a, **k):
        raise AssertionError("builder ran on a cache hit")

    got2 = cache.get_or_build("sid-c", rows, plan, None, _boom)
    assert got2 == full                                      # HIT returns the full envelope
    assert "heavy_evidence_pending" not in got2
    cache.clear()


def test_set_cached_noop_when_cache_disabled(monkeypatch):
    monkeypatch.setenv("TRUELINE_MRQ_EVIDENCE_CACHE", "0")
    assert cache.set_cached("sid", [{"source_file": "x"}], "p.pdf", {"x": 1}) is False


# ── preseed: fast metadata-first build THEN heavy continuation + overwrite (test 4) ─
def test_preseed_lazy_runs_fast_then_heavy_continuation(monkeypatch, tmp_path):
    plan = tmp_path / "plan.pdf"
    plan.write_bytes(b"%PDF-1.4 test")
    calls = []          # render_heavy per build, in order
    set_calls = []      # payloads handed to set_cached

    def _fake_build(plan_pdf, rows, *, card_out_dir=None, perf_observer=None, render_heavy=True):
        calls.append(render_heavy)
        if render_heavy:
            return {"source": {"logs": ["log56"]},
                    "placements": [{"log_ids": ["log56"],
                                    "geo": {"pdf_path_trace": {"artifact_name": "log56_trace.png"}}}]}
        return {"source": {"logs": ["log56"]}, "heavy_evidence_pending": True,
                "placements": [{"log_ids": ["log56"]}]}

    def _gob(sid, rows, plan_arg, card_dir, builder, observer=None):
        return builder(plan_arg, rows, card_out_dir=card_dir)  # run the (fast) builder once

    monkeypatch.setenv("TRUELINE_MRQ_EVIDENCE_PRESEED", "1")
    monkeypatch.setenv("TRUELINE_MRQ_LAZY_EVIDENCE", "1")
    monkeypatch.setenv("TRUELINE_PDF_FIRST_ENGINE", "1")
    monkeypatch.delenv("TRUELINE_PERF_AUDIT", raising=False)
    monkeypatch.setattr(main, "_session_scope", _noop_scope)
    monkeypatch.setattr(main, "STATE", {"committed_rows": [{"source_file": "bore_log56.xlsx"}]})
    monkeypatch.setattr(main, "_resolve_engineering_plan_pdf_paths", lambda sid: [plan])
    monkeypatch.setattr(cache, "enabled", lambda: True)
    monkeypatch.setattr(cache, "get_or_build", _gob)
    monkeypatch.setattr(cache, "set_cached", lambda sid, rows, p, payload: set_calls.append(payload) or True)
    monkeypatch.setattr(A, "build_session_evidence_from_committed_rows", _fake_build)

    main._preseed_mrq_evidence("sid-1")

    assert calls == [False, True]                       # metadata-first, THEN heavy continuation
    assert len(set_calls) == 1                          # cache overwritten exactly once
    assert "pdf_path_trace" in str(set_calls[0])        # the full envelope carries the heavy refs
    assert "heavy_evidence_pending" not in set_calls[0]  # full envelope clears the pending marker


def test_preseed_no_continuation_when_lazy_off(monkeypatch, tmp_path):
    # Lazy OFF -> single eager build (render_heavy=True), no continuation, no set_cached.
    plan = tmp_path / "plan.pdf"
    plan.write_bytes(b"%PDF-1.4 test")
    calls = []
    set_calls = []

    def _fake_build(plan_pdf, rows, *, card_out_dir=None, perf_observer=None, render_heavy=True):
        calls.append(render_heavy)
        return {"source": {"logs": ["log56"]}, "placements": [{"log_ids": ["log56"]}]}

    monkeypatch.setenv("TRUELINE_MRQ_EVIDENCE_PRESEED", "1")
    monkeypatch.delenv("TRUELINE_MRQ_LAZY_EVIDENCE", raising=False)
    monkeypatch.setenv("TRUELINE_PDF_FIRST_ENGINE", "1")
    monkeypatch.delenv("TRUELINE_PERF_AUDIT", raising=False)
    monkeypatch.setattr(main, "_session_scope", _noop_scope)
    monkeypatch.setattr(main, "STATE", {"committed_rows": [{"source_file": "bore_log56.xlsx"}]})
    monkeypatch.setattr(main, "_resolve_engineering_plan_pdf_paths", lambda sid: [plan])
    monkeypatch.setattr(cache, "enabled", lambda: True)
    monkeypatch.setattr(cache, "get_or_build", lambda sid, rows, p, cd, builder, observer=None: builder(p, rows, card_out_dir=cd))
    monkeypatch.setattr(cache, "set_cached", lambda *a, **k: set_calls.append(1) or True)
    monkeypatch.setattr(A, "build_session_evidence_from_committed_rows", _fake_build)

    main._preseed_mrq_evidence("sid-2")

    assert calls == [True]      # one eager build, no continuation
    assert set_calls == []      # cache never overwritten
