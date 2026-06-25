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


def test_confidence_high_only_when_placement_earns_it():
    # Confidence is EARNED by placement quality: tight extent match + endpoint bracket + red + isolated.
    bore = _bore()
    hi = uce._confidence(None, object(), bore,
                         {"score": 0.95, "extent_fit": 1.0, "end_fit": 0.95, "is_red": True,
                          "full_sheet": False, "competition": 0})
    assert hi["band"] == "HIGH" and hi["score"] <= 0.92      # never AUTO
    assert any("matches the bore-log span" in r for r in hi["reasons"])


def test_confidence_low_capped_for_full_sheet_baseline():
    # A full-sheet alignment/baseline pick is capped LOW (station location only; line unverified) even though
    # the axis is perfect — readability never inflates confidence.
    bore = _bore()
    lo = uce._confidence(None, object(), bore,
                         {"score": 0.04, "extent_fit": 0.0, "end_fit": 0.0, "is_red": False,
                          "full_sheet": True, "competition": 1, "axis_residual_ft": 0.0})
    assert lo["band"] == "LOW" and lo["score"] <= 0.40
    assert "PLACED_ON_FULL_SHEET_ALIGNMENT_LINE" in lo["warnings"]
    assert "RUN_LENGTH_UNLIKE_BORE_SPAN" in lo["warnings"]


# --- Bore-aware placement on a REALISTIC plan (full-sheet baselines + a tight per-bore run) ---------------- #
_R_TICK_Y = 400.0


def _realistic_plan(tmp_path, include_bore=True) -> str:
    """Grid + ticks (10+00..16+00) + a full-sheet survey baseline + 2 full-sheet utilities + (optionally) the
    PROPOSED bore drawn red, TIGHTLY spanning 11+75..13+25 (x 295..445). Axis station_at(x)=x+880."""
    doc = fitz.open()
    page = doc.new_page(width=792, height=612)
    for gy in range(300, 361, 20):
        page.draw_line((120, gy), (720, gy), color=(0.8, 0.8, 0.8), width=0.4)
    for ft in range(1000, 1601, 100):
        x = 120 + (ft - 1000) / 100 * 100
        page.draw_line((x, _R_TICK_Y), (x, _R_TICK_Y + 12), color=(0, 0, 0), width=0.8)
        page.insert_text((x - 12, _R_TICK_Y + 26), "%d+%02d" % (ft // 100, ft % 100), fontsize=8)
    page.draw_line((120, _R_TICK_Y), (720, _R_TICK_Y), color=(0, 0, 0), width=0.7)       # baseline (600ft)
    page.draw_line((120, 372), (720, 372), color=(0.2, 0.5, 0.9), width=0.8)            # blue utility
    page.draw_line((120, 388), (720, 388), color=(0.1, 0.6, 0.2), width=0.8)            # green utility
    if include_bore:
        page.draw_line((295, 384), (445, 384), color=(1, 0, 0), width=1.8)              # proposed bore (150ft)
    path = str(tmp_path / "realistic.pdf")
    doc.save(path)
    doc.close()
    return path


def _bore175() -> Bore:
    return Bore(bore_id="b-1", sheet_refs=[1], station_start="11+75", station_end="13+25",
                station_start_ft=1175.0, station_end_ft=1325.0, span_ft=150.0)


def test_place_generic_selects_bore_run_over_full_sheet_baselines(tmp_path):
    # The classic failure mode: a survey baseline must NOT be chosen as the bore. The bore-aware selector
    # picks the tight per-bore red run instead.
    plan = PlanPdf(_realistic_plan(tmp_path))
    try:
        d = GenericGeometryDialect()
        placement, sig = uce._place_generic(_bore175(), plan, d, 0)
        assert placement is not None and placement.status == PlacementStatus.REVIEW
        s = d.signals_for(placement.matched_callouts[0])
        assert s["run_extent_ft"] < 250 and not s.get("full_sheet")   # the 150ft bore run, not a 600ft baseline
        assert uce.GENERIC_RUN_MATCHES_SPAN in placement.caveats
    finally:
        plan.close()


def test_place_generic_clips_stroke_to_bore_span(tmp_path):
    # The drawn stroke spans EXACTLY the bore-log stations, never the full run (the owner's overstatement bug).
    plan = PlanPdf(_realistic_plan(tmp_path))
    try:
        d = GenericGeometryDialect()
        placement, sig = uce._place_generic(_bore175(), plan, d, 0)
        poly = d.centerline_for(placement.matched_callouts[0])
        axis = d.axis_for(1)
        lo, hi = sorted([axis.station_at(poly[0][0]), axis.station_at(poly[-1][0])])
        assert abs(lo - 1175.0) < 20.0 and abs(hi - 1325.0) < 20.0
    finally:
        plan.close()


def test_place_generic_baseline_only_is_low_and_unverified(tmp_path):
    # No per-bore run, only full-sheet lines -> it still locates the bore on the alignment, but confidence is
    # LOW and the caveat says the exact line is unverified (no fake high confidence on a guessed line).
    plan = PlanPdf(_realistic_plan(tmp_path, include_bore=False))
    try:
        d = GenericGeometryDialect()
        placement, sig = uce._place_generic(_bore175(), plan, d, 0)
        assert placement is not None
        conf = uce._confidence(placement, placement.matched_callouts[0], _bore175(),
                               d.signals_for(placement.matched_callouts[0]))
        assert conf["band"] == "LOW"
        assert uce.GENERIC_PLACED_ON_ALIGNMENT in placement.caveats
        # ...and even the baseline pick is clipped to the bore stations (location is still useful)
        poly = d.centerline_for(placement.matched_callouts[0]); axis = d.axis_for(1)
        lo, hi = sorted([axis.station_at(poly[0][0]), axis.station_at(poly[-1][0])])
        assert abs(lo - 1175.0) < 20.0 and abs(hi - 1325.0) < 20.0
    finally:
        plan.close()
