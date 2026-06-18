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
    ALLOWED, ALREADY_DRAWN, BASE_CONDUIT, DUPLICATE_OF_DRAWN, OWNER_CONFIRMED_PLAN_ROUTES, R_COMPLETE,
    _resolve_endpoints,
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
# log6 = a cross-sheet bore (17->5) whose start reset '0+56=0+00' is on sheet 17 but corrected_sheets=[5]
# (off-sheet start bind), and whose start chain reaches the 3+23/0+69 matchline at TWO points -- the bore's
# branch is the one THROUGH-CONTINUOUS (same height) with the sheet-5 leg; the default minimal-extension
# branch overshoots closure (296.9'/360.8' vs 243'), the through-continuous one closes (242.4').
THROUGH_CONTINUITY_TARGETS = ("log6",)
# log41 = reset-to-reset across-street bore (single sheet 2): the receiving structure binds by its own
# 'STA 0+46=0+00' reset TOKEN (corrected_end '0+44' is the bore's own length and prints no structure).
RESET_TO_RESET_TARGETS = ("log41",)
# OWNER-REVIEWED PROMOTIONS (2026-06-17): truth-table-SPAN-seeded routes the owner CONFIRMED correct
# (no owner adjudication route -- the span seeds the endpoints, owner review authorises the render).
# clean (unique crossing / single sheet): log10/log39 cross-sheet, log37/log72 single-sheet.
PROMOTED_CLEAN_TARGETS = ("log10", "log37", "log39", "log72")
# OWNER-CORRECTED (direction-strict): a candidate leg went the WRONG direction; the boundary matchline is
# taken from the printed COMBINED 'SEE SHEET' label, not an ambiguous per-station token (log9/log23).
DIRECTION_CORRECTED_TARGETS = ("log9", "log23")
# log48 = OWNER-CONFIRMED PLAN ROUTE (corrupted-adjudication override, LOG48_N_LEG_CALLOUT_ASSEMBLY_RENDER):
# cross-sheet 2-leg (10->12) via the UNIQUE 1+90/1+90 matchline -- the parallel 1+91/1+92 Ledbetter crossing
# is auto-excluded by the viable-crossing gate; reset HH 45+33=0+00 start, FLOWER POT 5+07 end; the parent
# gate passes on its OWN 0+00->5+09 corpus span and REJECTS sibling log50's 5+14.
LOG48_TARGETS = ("log48",)
# log70 = OWNER-CONFIRMED PLAN ROUTE (2026-06-17 re-correction): L-shaped corner-turn up Eledra St. Start
# re-anchored to the STA 4+54 INSTALLER HH (sheet 17 corner = log69 end), up Eledra 175' to the 1+75 matchline,
# then 40' on sheet 20 to the STA 2+15 FLOWER POT; 175+40 = 215 ft == the printed 'HH - HH = 215'' footage,
# which closure enforces (the prior 1+45 start traced 561.5'). Cross-sheet 17->20 two-leg.
LOG70_TARGETS = ("log70",)
# log61 = OWNER-CONFIRMED PLAN ROUTE (2026-06-17): Ruth Circle cul-de-sac, cross-sheet 5->6, span 207'. The
# 5<->6 boundary is a BUNDLED matchline 'STA 24+11/4+37/1+92'; the source-backed selector picks 4+37 (named by
# the sheet-6 end callout 'STA 4+37 TO STA 4+50') -> the AP-137 LEFT branch, NOT 24+11 fiber / 1+92 AP-138 right.
LOG61_TARGETS = ("log61",)
# log62 = the RIGHT (AP-138) branch of the SAME Ruth Circle cul-de-sac (bore_log26 sibling of log61). The
# bundled selector picks 1+92 (named by the sheet-6 end callout 'STA 1+92 TO STA 2+01') -> proving it
# generalizes to the sibling branch; start STA 1+82 INSTALLER HH -> STA 2+01 FLOWER POT, ~201'.
LOG62_TARGETS = ("log62",)
# log60 = a clean SINGLE-SHEET raw-corpus drop on sheet 15 (the easiest remaining): STA 6+32 INSTALLER HH ->
# STA 1+13 FLOWER POT (113'); both termini bind by clean station labels; no matchline, no bundled equation.
LOG60_TARGETS = ("log60",)
# log32 = cross-sheet drop (18->22) whose origin was disambiguated by an owner-confirmed PRINTED-DISTANCE
# discriminator: HH-HH=130' (s18) + HH-HH=83' (s22) = 213 = bore span -> origin is STA 12+22=0+00 NEXTLINK HH
# (NOT the STA 12+93=0+00 INSTALLER HH, which also closes). End STA 2+13 FLOWER POT via the 1+77/1+76 matchline.
LOG32_TARGETS = ("log32",)
NEW_TARGETS = (CROSS_SHEET_TARGETS + SINGLE_SHEET_TARGETS + NLEG_TARGETS
               + MATCHLINE_TERMINUS_TARGETS + HH_BRIDGE_TARGETS + THROUGH_CONTINUITY_TARGETS
               + RESET_TO_RESET_TARGETS + PROMOTED_CLEAN_TARGETS + DIRECTION_CORRECTED_TARGETS
               + LOG48_TARGETS + LOG70_TARGETS + LOG61_TARGETS + LOG62_TARGETS + LOG60_TARGETS
               + LOG32_TARGETS)
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


def test_log48_promoted_from_hold_to_owner_confirmed_plan_route():
    # log48 was HELD under DUPLICATE_OF_DRAWN because its CORRUPTED adjudication (corrected_end 5+14) made it
    # look like sibling log50. The owner re-verified its OWN plan route from the PDF, so it is no longer a
    # hold but an OWNER-CONFIRMED PLAN ROUTE: corpus identity 0+00->5+09, plan terminus 5+07, sheets 10+12.
    assert "log48" not in DUPLICATE_OF_DRAWN
    seed = OWNER_CONFIRMED_PLAN_ROUTES["log48"]
    assert seed["corrected_end"] == "5+07" and seed["corrected_sheets"] == [10, 12] and seed["span_ft"] == 507
    assert "45+33=0+00" in seed["evidence_notes"]      # start reset (SPLICE POINT 46) seeds the start bind
    assert seed["status"] == "RECOVERED"


def test_log61_override_opts_into_bundled_matchline_selector():
    seed = OWNER_CONFIRMED_PLAN_ROUTES["log61"]
    assert seed["bundled_matchline_from_end_callout"] is True      # opt-in flag gates the selector
    assert seed["corrected_sheets"] == [5, 6] and seed["span_ft"] == 207.0
    assert seed["endpoint_anchors"]["start"]["station"] == "2+43"
    assert seed["endpoint_anchors"]["end"]["station"] == "4+50"    # LEFT-branch terminus, NOT 2+01


def test_select_bundled_station_picks_end_callout_station_else_abstains():
    # STATION-SPECIFIC (not geometry): the crossing is the start station of the printed 'STA X TO STA <end>'
    # end callout, and only if it is one of the bundled equation's stations.
    from truelinev2.proof.run_callout_route_assembly_sweep import _select_bundled_station
    eq = ("24+11", "4+37", "1+92")
    s6 = ["STA 4+37 TO STA 4+50 DIR. BORE (13') 1-1.25\" VACANT HDPE", "STA 4+50 FLOWER POT"]
    assert _select_bundled_station(s6, "4+50", eq) == "4+37"        # log61: 4+37 named by the end callout
    # log62 (RIGHT branch sibling, SAME equation): end 2+01 -> selects 1+92 (the selector generalizes)
    s6r = ["STA 1+92 TO STA 2+01 DIR. BORE (9') 1-1.25\" VACANT HDPE", "STA 2+01 FLOWER POT"]
    assert _select_bundled_station(s6r, "2+01", eq) == "1+92"
    # a callout naming a station NOT in the equation -> not selectable (no widening)
    assert _select_bundled_station(["STA 9+99 TO STA 4+50"], "4+50", eq) is None
    # no 'STA X TO STA <end>' callout -> abstain
    assert _select_bundled_station(["STA 4+50 FLOWER POT"], "4+50", eq) is None
    # >=2 equation-stations both ending at <end> -> ambiguous -> abstain (DO-NOT-WIDEN)
    assert _select_bundled_station(["STA 4+37 TO STA 4+50", "STA 1+92 TO STA 4+50"], "4+50", eq) is None


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


def test_through_continuous_pair_selects_matching_coordinate():
    # a leg's blob may reach a matchline at MORE THAN ONE point; the bore's branch is the one
    # through-continuous (same along-matchline coordinate) with the other leg -- not a length/nearest pick
    from truelinev2.proof.run_callout_route_assembly_sweep import _through_continuous_pair, _boundary_crossings

    def dash(x0, y0, x1, y1):
        return {"lines": [(x0, y0, x1, y1)]}

    s_mlb = (60.0, 0.0, 62.0, 400.0)        # vertical matchline (sheet-17 left edge)
    e_mlb = (1140.0, 0.0, 1142.0, 400.0)    # vertical matchline (sheet-5 right edge)
    # start chain reaches the matchline at y=100 AND y=300 (two branches); end chain only at y=300
    s_chain = [dash(80.0, 100.0, 63.0, 100.0), dash(80.0, 300.0, 63.0, 300.0)]
    e_chain = [dash(1120.0, 300.0, 1139.0, 300.0)]
    assert len(_boundary_crossings(s_chain, s_mlb)) == 2   # two distinct crossing branches enumerated
    s_bnd, e_bnd = _through_continuous_pair(s_chain, s_mlb, e_chain, e_mlb)
    assert s_bnd is not None and abs(s_bnd[1] - 300.0) < 2.0   # the y=300 branch (matches the end leg)
    assert e_bnd is not None and abs(e_bnd[1] - 300.0) < 2.0
    # no through-continuous pair -> abstain (end leg crosses at y=200, which the start leg never reaches)
    assert _through_continuous_pair(s_chain, s_mlb, [dash(1120.0, 200.0, 1139.0, 200.0)], e_mlb) == (None, None)


def test_promotion_constants_well_formed():
    from truelinev2.proof.run_callout_route_assembly_sweep import (
        OWNER_APPROVED_SPAN_PROMOTIONS, OWNER_CORRECTED_SPAN_PROMOTIONS, OWNER_DIRECTION_CORRECTED,
        SPAN_SEEDED_PROMOTIONS,
    )
    for lid in SPAN_SEEDED_PROMOTIONS:                         # promotions are new, not already-drawn dups
        assert lid not in ALREADY_DRAWN and lid not in DUPLICATE_OF_DRAWN
    assert set(OWNER_DIRECTION_CORRECTED) == set(OWNER_CORRECTED_SPAN_PROMOTIONS)   # log9/log23 get strict
    assert (set(SPAN_SEEDED_PROMOTIONS)
            == set(OWNER_APPROVED_SPAN_PROMOTIONS) | set(OWNER_CORRECTED_SPAN_PROMOTIONS))
    # log70 renders via OWNER_CONFIRMED_PLAN_ROUTES (the L-turn up Eledra St, start re-anchored to STA 4+54),
    # NOT via span-seeding -- so it is correctly absent from the span-seeded promotion set.
    assert "log70" not in SPAN_SEEDED_PROMOTIONS


def test_span_seed_record_normalises_truth_span():
    from truelinev2.proof.run_callout_route_assembly_sweep import _span_seed_record
    rows = [{"bore_id": "logX", "span": "02+65->05+00", "sheets": [12]}]
    r = _span_seed_record("logX", rows)
    assert r["corrected_start"] == "2+65" and r["corrected_end"] == "5+00"   # zero-pad stripped for bind
    assert r["corrected_sheets"] == [12] and r["status"] == "RECOVERED" and r["span_ft"] is None
    assert _span_seed_record("missing", rows) is None


def test_leg_matchline_strict_uses_combined_label_matchline():
    # DIRECTION RULE: with strict, the boundary sits on the matchline carrying the COMBINED 'a/b' label
    # (the physical SEE-SHEET line), NOT a matchline merely near a same-numbered mid-sheet run-callout token.
    from truelinev2.proof.run_callout_route_assembly_sweep import _leg_matchline
    ml_a = {"layer": "MATCHLINE", "x0": 58, "y0": 0, "x1": 62, "y1": 400, "xc": 60, "yc": 200,
            "lines": [(60, 0, 60, 400)]}                       # the SEE-SHEET partner matchline (left)
    ml_b = {"layer": "MATCHLINE", "x0": 0, "y0": 48, "x1": 1000, "y1": 52, "xc": 500, "yc": 50,
            "lines": [(0, 50, 1000, 50)]}                      # decoy matchline (top), near a run callout
    words = [{"text": "3+98/3+08", "xc": 70, "yc": 200, "x0": 64, "y0": 196, "x1": 110, "y1": 204},
             {"text": "3+08", "xc": 500, "yc": 45, "x0": 490, "y0": 41, "x1": 520, "y1": 49}]
    chain = [{"lines": [(300, 200, 63, 200)]}, {"lines": [(300, 200, 500, 53)]}]
    res = _leg_matchline(words, [ml_a, ml_b], chain, ("3+98", "3+08"), strict=True)
    assert res is not None
    _, bnd = res
    assert abs(bnd[0] - 60) < 6 and 150 < bnd[1] < 250        # extended to ML_A (left), not the top decoy


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
    # log6 = cross-sheet 17->5 via through-continuity, with an OFF-SHEET start bind (reset on sheet 17, not in
    # corrected_sheets=[5]); two legs close to 243' only when the crossing branch is through-continuous
    for lid in THROUGH_CONTINUITY_TARGETS:
        t = rep["verdicts"][lid]
        pngs = sorted(OUT_DIR.glob(f"{lid}_*.png"))
        assert len(pngs) == 2, (lid, [p.name for p in pngs])
        assert t["through_continuity"] is True                # the default minimal-extension branch overshot
        assert t["start_sheet"] == 17 and t["end_sheet"] == 5 and t["sheets_set"] == [5]   # off-sheet start
        assert t["closure"]["closes"] is True
    # through-continuity fires for log6 (off-sheet start, branch overshoot), log70 (L-turn) AND log32 (the
    # 12+22 origin chain reaches the 1+77 matchline at multiple points; the branch through-continuous with the
    # sheet-22 leg closes). The other cross-sheet renders close on the default minimal-extension branch.
    assert sorted(lid for lid in rep["newly_rendered_full"]
                  if rep["verdicts"][lid].get("through_continuity")) == sorted(THROUGH_CONTINUITY_TARGETS + LOG70_TARGETS + LOG32_TARGETS)
    # log41 = reset-to-reset single-sheet across-street bore: one leg, closes (receiving HH by reset token)
    for lid in RESET_TO_RESET_TARGETS:
        v = rep["verdicts"][lid]
        assert v["single_sheet"] is True and v["closure"]["closes"] is True
        assert len(sorted(OUT_DIR.glob(f"{lid}_*.png"))) == 1
    # OWNER-APPROVED + OWNER-CORRECTED promotions: each renders ALL its legs and CLOSES the printed span
    for lid in (PROMOTED_CLEAN_TARGETS + DIRECTION_CORRECTED_TARGETS):
        v = rep["verdicts"][lid]
        assert v["closure"]["closes"] is True, (lid, v.get("closure"))
        assert len(sorted(OUT_DIR.glob(f"{lid}_*.png"))) == len(v["leg_summary"]), lid
    # owner-corrected logs are cross-sheet (two legs) routed via the STRICT combined-label matchline (the
    # legacy per-token boundary went the wrong direction and either failed or mis-closed)
    for lid in DIRECTION_CORRECTED_TARGETS:
        assert len(rep["verdicts"][lid]["leg_summary"]) == 2, lid
    # log70 NOW renders the owner-corrected L-shaped corner-turn route UP Eledra St (2026-06-17 re-correction):
    # start re-anchored to the STA 4+54 INSTALLER HH (sheet 17, the Niebuhr/Eledra corner = log69 end), up
    # Eledra 175' to the 1+75 matchline, then 40' on sheet 20 to the STA 2+15 FLOWER POT. 175+40 = 215 ft ==
    # the printed 'HH - HH = 215'' footage, enforced by closure (the prior 1+45 start traced 561.5').
    for lid in LOG70_TARGETS:
        v = rep["verdicts"][lid]
        assert len(sorted(OUT_DIR.glob(f"{lid}_*.png"))) == 2, lid             # cross-sheet 2-leg
        assert v["start_sheet"] == 17 and v["end_sheet"] == 20
        assert v["start_class"] == "installer_hh" and v["end_class"] == "flower_pot"
        assert v["bound_labels"] == {"start": "4+54", "end": "2+15"}           # corrected start (NOT 1+45)
        assert v["crossing_equation"] == ["1+75", "6+79"]
        assert v["closure"]["closes"] is True and abs(v["closure"]["drawn_ft"] - 215.0) <= 21.5
        assert v["parent_source_gate"]["ok"] is True                          # owns 0+00->2+15, rejects log69's 454
    # PARENT-SOURCE GATE: every rendered child passed its parent-group ownership gate (a child cannot claim
    # a sibling's route -- the log48<-log50 mixup).
    assert all(rep["verdicts"][l]["parent_source_gate"]["ok"] for l in rep["newly_rendered_full"])
    # log48 NOW renders its OWN owner-confirmed plan route (corrupted-adjudication override), DISTINCT from
    # sibling log50: cross-sheet 2-leg on sheets 10+12 (NOT log50's 10+11) via the UNIQUE 1+90/1+90 crossing
    # (the parallel 1+91/1+92 Ledbetter run excluded), reset HH 45+33 -> FLOWER POT 5+07, closing the span.
    assert "log48" in rep["newly_rendered_full"]
    for lid in LOG48_TARGETS:
        f = rep["verdicts"][lid]
        assert len(sorted(OUT_DIR.glob(f"{lid}_*.png"))) == 2, lid          # cross-sheet 2-leg
        assert f["start_sheet"] == 10 and f["end_sheet"] == 12              # NOT log50's 10+11
        assert f["start_class"] == "nextlink_hh" and f["end_class"] == "flower_pot"
        assert f["bound_labels"] == {"start": "45+33", "end": "5+07"}       # reset HH -> 5+07 flower pot
        assert f["crossing_equation"] == ["1+90", "1+90"]                   # the UNIQUE crossing
        assert len(f["viable_crossings"]) == 1                              # 1+91/1+92 Ledbetter excluded
        assert f["closure"]["closes"] is True                              # ~504' vs 507'
        assert f["parent_source_gate"]["ok"] is True                       # owns 0+00->5+09, not 5+14
    # log61 NOW renders the AP-137 / LEFT branch of the Ruth Circle cul-de-sac via the BUNDLED-MATCHLINE
    # SELECTOR: the sheet-6 end callout 'STA 4+37 TO 4+50' names 4+37, so 4+37 is selected from the bundled
    # 24+11/4+37/1+92 equation (NOT 24+11 fiber / 1+92 = AP-138 RIGHT branch -> the 250.7' overshoot). ~207'.
    assert "log61" in rep["newly_rendered_full"]
    for lid in LOG61_TARGETS:
        c = rep["verdicts"][lid]
        assert len(sorted(OUT_DIR.glob(f"{lid}_*.png"))) == 2, lid          # cross-sheet 2-leg
        assert c["start_sheet"] == 5 and c["end_sheet"] == 6
        assert c["bound_labels"] == {"start": "2+43", "end": "4+50"}
        assert c["bundled_equation"] == ["24+11", "4+37", "1+92"]           # the bundled matchline
        assert c["bundled_selected_station"] == "4+37"                      # NOT 24+11 / 1+92
        assert c["closure"]["closes"] is True and abs(c["closure"]["drawn_ft"] - 207.0) <= 20.7
        assert c["parent_source_gate"]["ok"] is True
    # log62 = the RIGHT (AP-138) branch (bore_log26 sibling of log61): the SAME bundled selector picks 1+92
    # (named by the sheet-6 end callout 'STA 1+92 TO STA 2+01') -> generalizes from log61's 4+37. ~201'.
    assert "log62" in rep["newly_rendered_full"]
    for lid in LOG62_TARGETS:
        g = rep["verdicts"][lid]
        assert len(sorted(OUT_DIR.glob(f"{lid}_*.png"))) == 2, lid
        assert g["start_sheet"] == 5 and g["end_sheet"] == 6
        assert g["bound_labels"] == {"start": "1+82", "end": "2+01"}        # right-branch entrance -> 2+01
        assert g["bundled_equation"] == ["24+11", "4+37", "1+92"]
        assert g["bundled_selected_station"] == "1+92"                      # RIGHT branch (NOT 4+37 / 24+11)
        assert g["closure"]["closes"] is True and abs(g["closure"]["drawn_ft"] - 201.0) <= 20.1
        assert g["parent_source_gate"]["ok"] is True
    # log60 = a clean SINGLE-SHEET raw-corpus drop (sheet 15): STA 6+32 INSTALLER HH -> STA 1+13 FLOWER POT,
    # ~113'. One leg, both termini bound by their station labels; no matchline.
    assert "log60" in rep["newly_rendered_full"]
    for lid in LOG60_TARGETS:
        h = rep["verdicts"][lid]
        assert len(sorted(OUT_DIR.glob(f"{lid}_*.png"))) == 1, lid          # single sheet
        assert h["single_sheet"] is True and h["start_sheet"] == 15 and h["end_sheet"] == 15
        assert h["start_class"] == "installer_hh" and h["end_class"] == "flower_pot"
        assert h["bound_labels"] == {"start": "6+32", "end": "1+13"}
        assert h["closure"]["closes"] is True and abs(h["closure"]["drawn_ft"] - 113.0) <= 11.3
        assert h["parent_source_gate"]["ok"] is True
    # log32 = cross-sheet drop (18->22): owner-confirmed origin STA 12+22=0+00 NEXTLINK HH (printed HH-HH
    # 130'+83'=213 selects 12+22 over the 12+93 INSTALLER HH), end STA 2+13 FLOWER POT via the 1+77/1+76 matchline.
    assert "log32" in rep["newly_rendered_full"]
    for lid in LOG32_TARGETS:
        j = rep["verdicts"][lid]
        assert len(sorted(OUT_DIR.glob(f"{lid}_*.png"))) == 2, lid          # cross-sheet 2-leg
        assert j["start_sheet"] == 18 and j["end_sheet"] == 22
        assert j["start_class"] == "nextlink_hh" and j["end_class"] == "flower_pot"
        assert j["bound_labels"] == {"start": "12+22", "end": "2+13"}       # 12+22 selected, NOT 12+93
        assert j["crossing_equation"] == ["1+77", "1+76"]
        assert j["closure"]["closes"] is True and abs(j["closure"]["drawn_ft"] - 213.0) <= 21.3
        assert j["parent_source_gate"]["ok"] is True
    assert rep["engine_census_frozen"] is True and rep["no_fixture_mutation"] is True
