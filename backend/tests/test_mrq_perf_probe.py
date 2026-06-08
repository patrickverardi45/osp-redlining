"""mrq_perf_probe — behavior-neutral granular render telemetry, unit tests.

Default-OFF: record()/timed() are no-ops with no active probe; perf_build_probe(None) is a
no-op; an active probe (observer set) counts/times fitz.open + Page.get_pixmap, detects
duplicate (page, clip) rasterizations, accumulates stage timers, samples RSS, and flushes
mrq_pf.* rows via the observer. NEVER raises into the build; fitz wrappers are restored on
exit. Measurement only — no draw/correctness behavior here to assert.
"""
from __future__ import annotations

from app.core import mrq_perf_probe as P


def test_record_and_timed_noop_when_inactive():
    P.record("x", 5.0)          # no active ctx -> dropped, never raises
    with P.timed("y"):
        pass
    assert P._ctx() is None


def test_perf_build_probe_none_is_noop():
    with P.perf_build_probe(None):
        P.record("x", 1.0)      # no ctx installed -> dropped
    assert P._ctx() is None     # nothing emitted, no error


def test_active_probe_flushes_stage_and_summary_rows():
    rows = []
    with P.perf_build_probe(rows.append):
        with P.timed("crop_render"):
            pass
        P.record("resolver_consult", 12.5)
    stages = [r["stage"] for r in rows]
    for s in ("mrq_pf.fitz_open", "mrq_pf.rasterize", "mrq_pf.rasterize_dup",
              "mrq_pf.crop_render", "mrq_pf.resolver_consult"):
        assert s in stages, (s, stages)
    assert P._ctx() is None
    for r in rows:                                   # only safe keys ever leave the probe
        assert set(r) <= {"stage", "elapsed_ms", "output_count", "detail"}


def test_fitz_open_and_rasterize_counted_with_duplicate():
    import fitz
    rows = []
    with P.perf_build_probe(rows.append):
        doc = fitz.open()        # new empty PDF -> 1 fitz_open
        page = doc.new_page()
        page.get_pixmap()        # rasterize #1
        page.get_pixmap()        # same (page, no-clip) -> duplicate
        doc.close()
    by = {r["stage"]: r for r in rows}
    assert by["mrq_pf.fitz_open"]["output_count"] >= 1
    assert by["mrq_pf.rasterize"]["output_count"] >= 2
    assert by["mrq_pf.rasterize_dup"]["output_count"] >= 1
    assert fitz.open.__name__ != "_w_open"           # wrapper restored after the probe


def test_raising_observer_never_breaks():
    def _boom(_evt):
        raise RuntimeError("sink boom")
    with P.perf_build_probe(_boom):                  # flush swallows observer errors
        P.record("x", 1.0)
    assert P._ctx() is None


def test_reentrant_probe_inner_is_noop():
    outer = []
    with P.perf_build_probe(outer.append):
        inner = []
        with P.perf_build_probe(inner.append):       # nested -> no-op (no reinstall/flush)
            P.record("x", 1.0)
        assert inner == []
    assert any(r["stage"] == "mrq_pf.fitz_open" for r in outer)
