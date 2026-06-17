"""GENERALIZED CALLOUT-IDENTITY ROUTE ASSEMBLY sweep -- offline-law + PDF/env-gated end-to-end tests.

Offline laws (always run, no PDF): the new convention-agnostic matchline primitive see_sheet_crossings
parses printed 'BOUNDARY STA a/b - SEE SHEET N' equations, keeps the boundary keyword INJECTED (no
hardcoded CAD layer), reports ALL crossings of a sheet pair (the multi-crossing "conflict" case) without
choosing, and dedups; the sweep composes base|lateral conduit (drop coverage) and excludes the new targets
from the already-drawn set; the result enum is closed. The heavy end-to-end (binds + renders 4 cross-sheet
bores on the real plan PDF) is gated behind the PDF AND TL2_TRY_DRAW_E2E=1 so it never bloats the default
suite; it asserts the 4-log rendered set (8 PNGs), per-log station closure, the two correctly-blocked logs,
and a frozen engine census.
"""
import os

import pytest

from truelinev2.extract.matchline_join import see_sheet_crossings
from truelinev2.proof.run_brenham_corpus import PDF
from truelinev2.proof.run_callout_route_assembly_sweep import (
    ALLOWED, ALREADY_DRAWN, BASE_CONDUIT, DUPLICATE_OF_DRAWN, R_COMPLETE, _resolve_endpoints,
)
from truelinev2.extract.structure_position import (
    BRENHAM_CONDUIT_LAYERS, BRENHAM_LATERAL_CONDUIT_LAYERS,
)

CROSS_SHEET_TARGETS = ("log11", "log12", "log29", "log47", "log54", "log58", "log67")  # two sheet-local legs
SINGLE_SHEET_TARGETS = ("log36",)                            # single leg, sheet source-derived
# log46 = 3-sheet route (10->13->14); sheet 13 has TWO parallel same-crew runs, but the bore's END (AP-161)
# is through-continuous with only ONE -> selected uniquely (the other run belongs to a different bore).
NLEG_TARGETS = ("log46",)
# log68 = a bore that TERMINATES at a printed matchline crossing (6+79): its start binds to a structure by
# a SOURCE-derived AP id (AP-144, from the STA 5+03 placement note -- the bare station label is not unique),
# its end is the sheet boundary (no second structure), one leg, printed-span closure (176').
MATCHLINE_TERMINUS_TARGETS = ("log68",)
# log63 = a single-sheet HH-to-HH bore (56') whose two endpoint labels collapse to ONE bound reset HH
# ('0+56=0+00'); the partner HH (a non-unique frame 0+00) is identified by the printed, value-unique
# 'HH - HH = 56'' distance annotation positioned between the two HHs -- NOT by nearest.
HH_BRIDGE_TARGETS = ("log63",)
NEW_TARGETS = (CROSS_SHEET_TARGETS + SINGLE_SHEET_TARGETS + NLEG_TARGETS
               + MATCHLINE_TERMINUS_TARGETS + HH_BRIDGE_TARGETS)
# log29 + log54 are reviewed-but-unanchored: class + (for log29) sheet derived from source, no anchors
SOURCE_DERIVED_CLASS_TARGETS = ("log29", "log54")
# log12's END is an AP TERMINAL PORT HH bound by its AP-id token (AP-121); the station 10+92 does not bind
AP_TERMINUS_TARGET = "log12"
# log46 is a 3-sheet N-leg route (10->13->14) but sheet 13 prints TWO PARALLEL runs that BOTH close the
# span; the N-leg solver enumerates them and DEFERS (no unique source-backed route) -- DO-NOT-WIDEN.
NLEG_AMBIGUOUS_TARGET = "log46"


# ---- offline laws (always run) ------------------------------------------------------

def test_see_sheet_crossings_parses_all_crossings_in_order():
    lines = [
        "MATCHLINE STA 1+82/1+81 - SEE SHEET 20",
        "MATCHLINE STA 1+75/6+79 - SEE SHEET 20",
        "MATCHLINE STA 10+73 - SEE SHEET 18",
    ]
    # both 17<->20 crossings reported, in print order, none chosen between (the "conflict" case)
    assert see_sheet_crossings(lines, 20, "MATCHLINE") == [("1+82", "1+81"), ("1+75", "6+79")]
    assert see_sheet_crossings(lines, 18, "MATCHLINE") == [("10+73",)]
    assert see_sheet_crossings(lines, 99, "MATCHLINE") == []


def test_see_sheet_crossings_boundary_keyword_is_injected():
    # a SEE-SHEET line WITHOUT the injected boundary keyword is ignored -> no hardcoded convention
    lines = ["SEE SHEET 20 STA 1+82/1+81"]
    assert see_sheet_crossings(lines, 20, "MATCHLINE") == []
    assert see_sheet_crossings(lines, 20, "SEE SHEET") == [("1+82", "1+81")]


def test_see_sheet_crossings_dedups_repeated_equation():
    lines = ["MATCHLINE STA 1+60/1+62 - SEE SHEET 10",
             "MATCHLINE STA 1+60/1+62 - SEE SHEET 10"]
    assert see_sheet_crossings(lines, 10, "MATCHLINE") == [("1+60", "1+62")]


def test_conduit_set_composes_base_plus_lateral_only():
    base = set(BRENHAM_CONDUIT_LAYERS.values())
    lat = set(BRENHAM_LATERAL_CONDUIT_LAYERS.values())
    assert base <= BASE_CONDUIT and lat <= BASE_CONDUIT
    assert "BORE - PATH" not in BASE_CONDUIT          # excluded (unproven over-coverage)


def test_new_targets_not_in_already_drawn():
    for lid in NEW_TARGETS:
        assert lid not in ALREADY_DRAWN
    assert R_COMPLETE in ALLOWED


def test_resolve_endpoints_anchored():
    anc = {"endpoint_anchors": {
        "start": {"station": "1+45", "structure_class": "installer_hh"},
        "end": {"station": "4+14", "structure_class": "flower_pot"}}}
    assert _resolve_endpoints(anc) == ("1+45", "installer_hh", "4+14", "flower_pot", True)


def test_resolve_endpoints_reviewed_unanchored_parses_reset_class_none():
    # start reset parsed from the owner-reviewed notes; end = corrected_end; classes None -> derive from source
    rev = {"evidence_notes": "Start reset 'STA 2+22 = 0+00' at INSTALLER HH; end STA 4+45 FLOWER POT.",
           "corrected_start": "0+00", "corrected_end": "4+45"}
    assert _resolve_endpoints(rev) == ("2+22", None, "4+45", None, False)
    # no reset in notes but a non-zero corrected_start -> use it (mid-run direct bore)
    rev2 = {"evidence_notes": "direct bore callout", "corrected_start": "5+03", "corrected_end": "6+79"}
    assert _resolve_endpoints(rev2) == ("5+03", None, "6+79", None, False)
    # unresolvable (reset only at 0+00, no notes reset)
    assert _resolve_endpoints({"corrected_start": "0+00", "corrected_end": None})[0] is None


def test_duplicate_of_drawn_excludes_log48():
    assert "log48" in DUPLICATE_OF_DRAWN   # sibling of drawn log50; no parent/child overlap (DO-NOT-WIDEN)


def test_conduit_components_splits_parallel_runs():
    # the N-leg solver SEES parallel printed runs because they are distinct connected components
    from truelinev2.proof.run_callout_route_assembly_sweep import _conduit_components

    def d(x0, y0, x1, y1):
        return {"x0": x0, "y0": y0, "x1": x1, "y1": y1, "xc": (x0 + x1) / 2, "yc": (y0 + y1) / 2,
                "lines": [(x0, y0, x1, y1)], "layer": "BORE - PORT"}

    # two parallel vertical runs 100 pt apart (> MAX_DASH_GAP 35) -> 2 components
    far = _conduit_components([d(100, 0, 100, 10), d(100, 12, 100, 22),
                               d(200, 0, 200, 10), d(200, 12, 200, 22)])
    assert len(far) == 2
    # dashes within a dash-gap -> a single component
    near = _conduit_components([d(100, 0, 100, 10), d(100, 12, 100, 22)])
    assert len(near) == 1


def test_station_placement_ap_ids_binds_unique_block():
    from truelinev2.proof.run_callout_route_assembly_sweep import station_placement_ap_ids
    lines = [
        "STA 4+54", '13"X24"X24"', "INSTALLER HH",
        "STA 5+03", 'PLACE 13"X24"X24"', "TERMINAL 8 PORT HH", "AP-144 SPLICE LOC 33",
        "TERMINAL TAIL = 750'", '11"X11"X12"', "FLOWER POT",
        "STA 6+30", '11"X11"X12"', "FLOWER POT",
        "STA 5+03 TO STA 6+79", 'DIR. BORE (176\') 1-1.25" VACANT HDPE',  # run callout, NOT a placement header
    ]
    # the AP id in the STA 5+03 PLACEMENT block (bounded by the next STA header); the run callout is ignored
    assert station_placement_ap_ids(lines, "5+03") == ["AP-144"]
    assert station_placement_ap_ids(lines, "4+54") == []   # no AP in its block (typed absence, DO-NOT-WIDEN)
    assert station_placement_ap_ids(lines, "9+99") == []   # no such placement header


def test_station_placement_ap_ids_refuses_ambiguous():
    from truelinev2.proof.run_callout_route_assembly_sweep import station_placement_ap_ids
    two = ["STA 5+03", "TERMINAL 8 PORT HH", "AP-144 SPLICE LOC 33", "AP-145 SPLICE LOC 34", "STA 6+30"]
    assert station_placement_ap_ids(two, "5+03") == []     # two AP ids in one block -> abstain
    dup = ["STA 5+03", "AP-144 SPLICE LOC 33", "STA 6+30", "STA 5+03", "AP-200 SPLICE LOC 9", "STA 7+00"]
    assert station_placement_ap_ids(dup, "5+03") == []     # two placement headers for one station -> abstain


def test_hh_symbol_clusters_dedups_within_footprint():
    from truelinev2.proof.run_callout_route_assembly_sweep import _hh_symbol_clusters, HH_SYMBOL_LAYER

    def s(x, y):
        return {"layer": HH_SYMBOL_LAYER, "xc": x, "yc": y}

    draw = [s(100, 100), s(101, 102), s(300, 300), {"layer": "OTHER", "xc": 100, "yc": 100}]
    cl = _hh_symbol_clusters(draw)
    assert len(cl) == 2                                    # the two near strokes collapse; OTHER-layer ignored


def test_ann_between_requires_projection_onto_segment():
    # the HH-HH annotation must project ONTO the A-B run (param in [0,1]) within the perp tol to label THAT
    # pair -- prevents an annotation beyond an endpoint or far to the side from bridging the wrong pair
    from truelinev2.proof.run_callout_route_assembly_sweep import _ann_between
    a, b = (160.0, 342.0), (160.0, 421.0)
    assert _ann_between((153.0, 386.0), a, b) is True      # alongside the run (perp ~7pt) -> labels this pair
    assert _ann_between((153.0, 300.0), a, b) is False     # above A -> projects off the segment (t < 0)
    assert _ann_between((250.0, 386.0), a, b) is False     # 90pt to the side -> not this pair


# ---- heavy end-to-end (PDF + env gated) ---------------------------------------------

@pytest.mark.skipif(not os.path.isfile(PDF), reason="Brenham plan PDF not present")
@pytest.mark.skipif(os.environ.get("TL2_TRY_DRAW_E2E") != "1",
                    reason="heavy end-to-end (binds + renders the cross-sheet bores); set TL2_TRY_DRAW_E2E=1 to run")
def test_sweep_renders_new_logs_end_to_end():
    import json
    from truelinev2.proof.run_callout_route_assembly_sweep import OUT_DIR, main
    rc = main()
    assert rc == 0
    rep = json.loads((OUT_DIR / "callout_route_assembly_sweep.json").read_text(encoding="utf-8"))
    assert rep["verdict"] == "PASS" and rep["result"] == R_COMPLETE
    assert set(rep["newly_rendered_full"]) == set(NEW_TARGETS)
    # cross-sheet bores drew BOTH legs (2 real PNGs) and close against the printed bore span
    for lid in CROSS_SHEET_TARGETS:
        pngs = sorted(OUT_DIR.glob(f"{lid}_*.png"))
        assert len(pngs) == 2, (lid, [p.name for p in pngs])
        assert rep["verdicts"][lid]["closure"]["closes"] is True
    # the single-sheet bore drew one leg, closes, and had its sheet EXTRACTED from source
    for lid in SINGLE_SHEET_TARGETS:
        pngs = sorted(OUT_DIR.glob(f"{lid}_*.png"))
        assert len(pngs) == 1, (lid, [p.name for p in pngs])
        assert rep["verdicts"][lid]["closure"]["closes"] is True
        assert rep["verdicts"][lid]["sheet_source_derived"] is True
    # the 3-sheet N-leg bore RENDERS: sheet 13 has two parallel same-crew runs, but the bore's END is
    # through-continuous (crosses each matchline at the run's x) with EXACTLY ONE run -> selected uniquely,
    # 3 legs, middle sheet not omitted. The other parallel run belongs to a different bore.
    for lid in NLEG_TARGETS:
        pngs = sorted(OUT_DIR.glob(f"{lid}_*.png"))
        assert len(pngs) == 3, (lid, [p.name for p in pngs])
        assert rep["verdicts"][lid]["closure"]["closes"] is True
        assert len(rep["verdicts"][lid]["nleg_closing_solutions"]) == 1   # through-continuity -> unique run
        assert len(rep["verdicts"][lid]["crossing_chain"]) == 2
    # the reviewed-but-unanchored logs had their terminus CLASS derived from source (no owner naming)
    for lid in SOURCE_DERIVED_CLASS_TARGETS:
        assert rep["verdicts"][lid]["class_source_derived"] is True
    # log12's AP terminus bound by its AP-id token (the station label does not bind) -> terminal_port_hh
    ap = rep["verdicts"][AP_TERMINUS_TARGET]
    assert ap["bound_labels"]["end"].startswith("AP-")
    assert ap["end_class"] == "terminal_port_hh"
    # log68 = end-at-matchline single leg: SOURCE-derived AP-144 start bind (the bare 5+03 label is not
    # unique), end is the printed 6+79 matchline crossing (no second structure), one PNG, closes to 176'
    for lid in MATCHLINE_TERMINUS_TARGETS:
        m = rep["verdicts"][lid]
        pngs = sorted(OUT_DIR.glob(f"{lid}_*.png"))
        assert len(pngs) == 1, (lid, [p.name for p in pngs])
        assert m["end_at_matchline"] is True and m["single_sheet"] is True
        assert m["pdf_start_ap_ids"] == ["AP-144"] and m["bound_labels"]["start"] == "AP-144"
        assert m["start_class"] == "terminal_port_hh" and m["end_sheet"] is None
        assert m["leg_summary"][0]["kind"] == "matchline_terminus"
        assert m["closure"]["closes"] is True
    # log63 = HH-HH distance-annotation bridge: one PNG, the 'HH - HH = 56'' annotation is unique by value
    # (1 hit, no stacked collapse), EXACTLY one HH symbol at 56' (no nearest pick), and closure holds
    for lid in HH_BRIDGE_TARGETS:
        h = rep["verdicts"][lid]
        pngs = sorted(OUT_DIR.glob(f"{lid}_*.png"))
        assert len(pngs) == 1, (lid, [p.name for p in pngs])
        assert h["hh_hh_bridge"] is True and h["single_sheet"] is True
        assert h["hh_annotation_value"] == 56 and h["hh_annotation_hits"] == 1
        assert len(h["hh_bridge_candidates"]) == 1            # unique HH at the printed span distance
        assert h["leg_summary"][0]["kind"] == "hh_hh_bridge"
        assert h["closure"]["closes"] is True
    # the correctly-withheld log (DO-NOT-WIDEN): log70 fails closure (the owner's flagged -504ft conflict)
    assert "log70" in rep["still_blocked"]
    assert rep["engine_census_frozen"] is True and rep["no_fixture_mutation"] is True
