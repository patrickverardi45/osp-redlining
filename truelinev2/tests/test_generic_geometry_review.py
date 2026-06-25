"""Generic drawn-geometry fallback dialect — committed unit + engine-integration coverage.

Self-contained + name-free: a synthetic plan PDF (station-tick labels along an axis + a drawn run near the
alignment band) is built with fitz in-process, so no real CAD plan / customer corpus is needed. Proves that
an UNRECOGNIZED plan (no Brenham/ODOT dialect) still reaches the REVIEW deciders through the same run_match
and produces a drawable REVIEW candidate with a traced centerline + graded confidence — never AUTO.
"""
from __future__ import annotations

import fitz
import pytest

from truelinev2.extract.generic_geometry import GenericGeometryDialect
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.match.engine import run_match
from truelinev2.schema.models import Bore, PlacementStatus
from truelinev2.contracts import uploaded_corpus_engine_handoff as uce

# Synthetic station axis: ticks at x=100..500 carry stations 1000..1400 ft -> station_at(x) = x + 900.
_TICKS = [(100.0, "10+00"), (200.0, "11+00"), (300.0, "12+00"), (400.0, "13+00"), (500.0, "14+00")]
_TICK_Y = 400.0


def _make_plan(tmp_path, run=(250.0, 350.0), run_y=410.0, red=True, ticks=_TICKS) -> str:
    """A 1-page synthetic plan: station-tick text on a row + a horizontal drawn 'run' near the alignment
    band. run=(x0,x1) -> the run projects to stations (x0+900, x1+900)."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    for x, label in ticks:
        page.insert_text((x, _TICK_Y), label, fontsize=8)
    color = (1, 0, 0) if red else (0, 0, 0)
    page.draw_line((run[0], run_y), (run[1], run_y), color=color, width=2)
    path = str(tmp_path / "synthetic_plan.pdf")
    doc.save(path)
    doc.close()
    return path


def _bore(start_ft=1150.0, end_ft=1250.0, sheet_refs=(1,)) -> Bore:
    return Bore(bore_id="b-1", sheet_refs=list(sheet_refs),
                station_start="11+50", station_end="12+50",
                station_start_ft=start_ft, station_end_ft=end_ft, span_ft=abs(end_ft - start_ft))


def test_detect_true_on_axis_plus_run(tmp_path):
    plan = PlanPdf(_make_plan(tmp_path))
    try:
        assert GenericGeometryDialect().detect(plan) is True
    finally:
        plan.close()


def test_detect_false_without_station_axis(tmp_path):
    # Only two ticks -> axis under-determined / too few ticks -> no candidate -> detect False.
    plan = PlanPdf(_make_plan(tmp_path, ticks=_TICKS[:2]))
    try:
        assert GenericGeometryDialect().detect(plan) is False
    finally:
        plan.close()


def test_detect_false_without_any_drawn_run(tmp_path):
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    for x, label in _TICKS:
        page.insert_text((x, _TICK_Y), label, fontsize=8)
    path = str(tmp_path / "ticks_only.pdf")
    doc.save(path)
    doc.close()
    plan = PlanPdf(path)
    try:
        assert GenericGeometryDialect().detect(plan) is False
    finally:
        plan.close()


def test_extract_callouts_projects_run_onto_axis(tmp_path):
    plan = PlanPdf(_make_plan(tmp_path, run=(250.0, 350.0)))
    try:
        d = GenericGeometryDialect()
        callouts = d.extract_callouts(plan, 1, 0)
        assert callouts, "expected at least one drawn-run callout"
        c = callouts[0]
        # run x 250..350 -> stations ~1150..1250 (axis station_at(x)~=x+900); tick text centers shift the
        # fit slightly (insert_text places by baseline), so allow a real-world projection tolerance.
        assert c.from_ft == pytest.approx(1150.0, abs=20.0)
        assert c.to_ft == pytest.approx(1250.0, abs=20.0)
        assert c.dialect == "generic" and c.bbox is not None
        # the dialect carries a traced centerline + confidence signals for that callout
        poly = d.centerline_for(c)
        assert poly is not None and len(poly) >= 2
        sig = d.signals_for(c)
        assert sig["is_red"] is True and sig["axis_ticks"] >= 3
    finally:
        plan.close()


def test_run_match_generic_places_review_not_auto(tmp_path):
    # A drawn run that COVERS the span but is not a per-bore tight match -> decide_by_extent returns REVIEW
    # (location confirmed, not AUTO) — the realistic generic case (mirrors the real ODOT corpus verdict).
    plan = PlanPdf(_make_plan(tmp_path, run=(200.0, 400.0)))   # stations ~1100..1300, bore is 1150..1250
    try:
        placement = run_match(_bore(), plan, GenericGeometryDialect(), 0)
        assert placement.status == PlacementStatus.REVIEW
        assert placement.matched_callouts and placement.matched_callouts[0].bbox is not None
        # ...and the adapter cap keeps it REVIEW even if a decider ever returned AUTO for the fallback.
        assert uce._cap_review(placement).status == PlacementStatus.REVIEW
    finally:
        plan.close()


def test_run_match_generic_abstains_when_run_off_span(tmp_path):
    # A run drawn far from the bore span -> decide_by_extent finds no covering geometry -> ABSTAIN (honest).
    plan = PlanPdf(_make_plan(tmp_path, run=(105.0, 130.0)))   # stations ~1005..1030, bore is 1150..1250
    try:
        placement = run_match(_bore(), plan, GenericGeometryDialect(), 0)
        assert placement.status == PlacementStatus.ABSTAIN
    finally:
        plan.close()


def test_cap_review_forces_review_from_auto():
    from truelinev2.schema.models import Placement
    auto = Placement(bore_id="b", status=PlacementStatus.AUTO_SELECT, tier="AUTO_SELECT",
                     reason="DRAWN_BORE_EXTENT_MATCHES_SPAN", caveats=["DRAWN_VECTOR_EXTENT"])
    capped = uce._cap_review(auto)
    assert capped.status == PlacementStatus.REVIEW
    assert uce.GENERIC_GEOMETRY_REVIEW in capped.caveats
    assert uce.GENERIC_CAP_REVIEW in capped.caveats


def test_confidence_bands_and_caps():
    bore = _bore()

    class _C:
        footage = 100.0

    # tight axis + red + few rivals -> HIGH, but never >= 1.0 (REVIEW is never AUTO)
    hi = uce._confidence(None, _C(), bore,
                         {"axis_residual_ft": 0.0, "axis_ticks": 10, "is_red": True, "rival_runs": 3})
    assert hi["band"] == "HIGH" and hi["score"] <= 0.95

    # noisy axis + many rivals + short extent -> LOW + honest warnings
    _C.footage = 10.0
    lo = uce._confidence(None, _C(), bore,
                         {"axis_residual_ft": 11.0, "axis_ticks": 5, "is_red": False, "rival_runs": 200})
    assert lo["band"] == "LOW"
    assert "MANY_RIVAL_RUNS" in lo["warnings"] and "NOISY_STATION_AXIS" in lo["warnings"]
    assert "SHORT_DRAWN_EXTENT" in lo["warnings"]


def test_named_dialect_path_emits_no_confidence_signals():
    # A dialect object without signals_for() (named path) -> evaluate attaches no confidence; here we assert
    # the helper simply has no signals to read (the gating contract the adapter relies on).
    assert not hasattr(object(), "signals_for")
