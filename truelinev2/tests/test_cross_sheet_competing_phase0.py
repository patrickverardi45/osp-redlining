"""M9.5 -- cross-sheet competing-departure frame-graph feasibility tests (offline).

Pin the PURE helpers of the Phase-0 proof (run_cross_sheet_competing_phase0) on
SYNTHETIC frame graphs + synthetic plan text -- no PDF, no fixtures. The LIVE Brenham
facts (anchor sheets {15,24,10}, single-hop far-reach {none,{25},{9,12,13}}, multi-hop
component {none,{25,26,27,28},{7,8,9,12,13,14}}, EXACT cross-sheet departures = 0 both
single- and multi-hop, verdict FEASIBLE) are gated INSIDE the proof (G1-G14).

The load-bearing tests are the NON-VACUOUS positives: a synthetic far-sheet run callout
at the EXACT frame-translated node station IS enumerated (single- AND multi-hop), while
the SAME raw station number is NOT and a near-miss is NOT -- proving the enumerator is
real and uses frame-proven translation, never raw-number equality or proximity. The
multi-hop helper is proven to ABSTAIN on an offset-inconsistent node (zero-false).
"""
import inspect
from types import SimpleNamespace

from truelinev2.match import frames as FR
from truelinev2.proof import run_cross_sheet_competing_phase0 as p5
from truelinev2.schema.frames import FrameEdge, FrameGraph, ParseConfidence
from truelinev2.stations import feet_to_station

# a synthetic, plan-neutral profile (the helpers duck-type these four fields)
SYN = SimpleNamespace(station_line_re=r"^STA\s+(\d{1,3}\+\d{2})\b",
                      run_callout_marker="TO STA", note_window=4,
                      drop_markers=("FOR FIBER DROP",))


def _graph(*edges):
    """edges: (from_sheet, to_sheet, offset_ft[, a_raw, b_raw])."""
    out = []
    for e in edges:
        a, b, off = e[0], e[1], e[2]
        a_raw = e[3] if len(e) > 3 else None
        b_raw = e[4] if len(e) > 4 else None
        out.append(FrameEdge(from_frame=FR.frame_for_sheet(a), to_frame=FR.frame_for_sheet(b),
                             offset_ft=off, confidence=ParseConfidence.HIGH,
                             a_raw=a_raw, b_raw=b_raw))
    return FrameGraph(edges=out)


# ---- safe_far_reach (single-hop) --------------------------------------------

def test_safe_far_reach_both_directions():
    g = _graph((10, 12, -1.0))
    assert p5.safe_far_reach(g, 10) == {12}
    assert p5.safe_far_reach(g, 12) == {10}


def test_safe_far_reach_isolated_anchor_is_empty():
    g = _graph((10, 12, -1.0), (24, 25, 742.0))
    assert p5.safe_far_reach(g, 99) == set()          # the AP-152 / sheet-15 analogue


def test_safe_far_reach_multiple_edges():
    g = _graph((10, 9, 3279.0), (12, 10, -1.0), (13, 10, -2.0))
    assert p5.safe_far_reach(g, 10) == {9, 12, 13}    # the AP-163 / sheet-10 analogue


# ---- safe_component_offsets (multi-hop, abstain-first) -----------------------

def test_safe_component_offsets_composes_multi_hop():
    g = _graph((10, 20, 100.0), (20, 30, 50.0))
    comp = p5.safe_component_offsets(g, 10)
    assert comp == {20: 100.0, 30: 150.0}             # station_on_s = anchor_term - offset[s]


def test_safe_component_offsets_isolated_anchor_empty():
    g = _graph((10, 20, 100.0))
    assert p5.safe_component_offsets(g, 77) == {}


def test_safe_component_offsets_abstains_on_inconsistent_cycle():
    # sheet 30 reachable by two paths with disagreeing composed offsets -> EXCLUDED.
    g = _graph((10, 20, 100.0), (20, 30, 50.0), (10, 30, 999.0))
    comp = p5.safe_component_offsets(g, 10)
    assert 30 not in comp and comp.get(20) == 100.0


# ---- exact_cross_sheet_departures (single-hop) ------------------------------

def test_exact_departure_positive_is_non_vacuous():
    g = _graph((900, 901, 742.0))
    far_sta = feet_to_station(1000.0 - 742.0)
    deps = p5.exact_cross_sheet_departures(
        g, 900, 1000.0, {901: [f"STA {far_sta} TO STA 4+00 - 1.25\" HDPE"]}, SYN)
    assert len(deps) == 1


def test_exact_departure_raw_equality_is_rejected():
    g = _graph((900, 901, 742.0))
    deps = p5.exact_cross_sheet_departures(
        g, 900, 1000.0, {901: ["STA 10+00 TO STA 12+00 - 1.25\" HDPE"]}, SYN)
    assert deps == []


def test_exact_departure_near_miss_is_not_counted():
    g = _graph((900, 901, 742.0))
    deps = p5.exact_cross_sheet_departures(
        g, 900, 1000.0, {901: ["STA 2+61 TO STA 4+73 - 1.25\" HDPE"]}, SYN)   # 261 vs 258
    assert deps == []


def test_exact_departure_no_safe_edge_abstains():
    g = _graph((900, 901, 742.0))
    deps = p5.exact_cross_sheet_departures(
        g, 555, 1000.0, {901: ["STA 2+58 TO STA 4+00 - 1.25\" HDPE"]}, SYN)
    assert deps == []


def test_exact_departure_carries_injected_drop_flag():
    g = _graph((900, 901, 742.0))
    deps = p5.exact_cross_sheet_departures(
        g, 900, 1000.0, {901: ["STA 2+58 TO STA 4+00 FOR FIBER DROP"]}, SYN)
    assert len(deps) == 1 and deps[0].is_drop is True


# ---- exact_cross_sheet_departures_component (multi-hop) ----------------------

def test_exact_component_departure_positive_two_hops():
    # node on sheet 900; reach sheet 902 only via 900->901->902 (2 hops).
    g = _graph((900, 901, 742.0), (902, 901, 100.0))
    comp = p5.safe_component_offsets(g, 900)           # {901:742, 902:642}
    far_sta = feet_to_station(1000.0 - comp[902])      # 358 -> "3+58"
    deps, used = p5.exact_cross_sheet_departures_component(
        g, 900, 1000.0, {902: [f"STA {far_sta} TO STA 5+00 - 1.25\" HDPE"],
                         901: ["STA 9+99 TO STA 9+98"]}, SYN)
    assert len(deps) == 1 and used == comp


# ---- edge_far_partner_stations + near matchline boundary --------------------

def test_edge_far_partner_stations():
    g = _graph((24, 25, 742.0, "10+03", "2+61"))
    assert p5.edge_far_partner_stations(g, 24, 25) == {"2+61"}
    assert p5.edge_far_partner_stations(g, 25, 24) == {"10+03"}


def test_near_callout_matchline_boundary_flag():
    g = _graph((24, 25, 742.0, "10+03", "2+61"))
    near = p5.near_callouts_diag(
        g, 24, 1000.0,
        {25: ["STA 2+61 TO STA 4+73 - 1.25\" HDPE",     # 261 -> back 1003 (matchline partner)
              "STA 2+71 TO STA 5+00 - 1.25\" HDPE"]},    # 271 -> back 1013, out of window
        SYN, window_ft=5.0)
    assert len(near) == 1
    assert near[0]["far_station"] == "2+61" and near[0]["delta_ft"] == 3.0
    assert near[0]["at_matchline_boundary"] is True


# ---- decide_verdict (all three branches reachable) --------------------------

def test_decide_verdict_all_three_branches():
    assert p5.decide_verdict(True, True) == p5.BLOCKED_NEEDS_SOURCE_REREAD
    assert p5.decide_verdict(True, False) == p5.BLOCKED_NEEDS_SOURCE_REREAD
    assert p5.decide_verdict(False, True) == p5.SAFE_FRAME_GRAPH_EXTENSION_FEASIBLE
    assert p5.decide_verdict(False, False) == p5.HONEST_NEGATIVE_FRAME_GRAPH_INSUFFICIENT


# ---- synthetic non-vacuous self-check (mirrors proof G10) --------------------

def test_synthetic_enumerator_check_helper():
    syn = p5._synthetic_enumerator_check(SYN)
    assert syn["positive_hit"] == 1
    assert syn["raw_equality_decoy"] == 0
    assert syn["near_miss_3ft"] == 0
    assert syn["isolated_anchor"] == 0


# ---- banked constants -------------------------------------------------------

def test_banked_constants():
    assert p5.EXPECT_ANCHOR_SHEET == {152: 15, 117: 24, 163: 10}
    assert p5.EXPECT_FAR_REACH == {152: set(), 117: {25}, 163: {9, 12, 13}}
    assert p5.EXPECT_COMPONENT_REACH == {152: set(), 117: {25, 26, 27, 28},
                                         163: {7, 8, 9, 12, 13, 14}}
    assert p5.EXPECT_DEADEND_TERMINALS == {105, 121, 148, 157}
    assert p5.EXPECT_CANDIDATES == {("log10", "log27"), ("log72", "log39")}
    assert p5.EXPECT_DROPS == {("log7", "log65")}
    assert p5.SAFE_FRAME_GRAPH_EXTENSION_FEASIBLE == "SAFE_FRAME_GRAPH_EXTENSION_FEASIBLE"
    assert p5.HONEST_NEGATIVE_FRAME_GRAPH_INSUFFICIENT == "HONEST_NEGATIVE_FRAME_GRAPH_INSUFFICIENT"
    assert p5.BLOCKED_NEEDS_SOURCE_REREAD == "BLOCKED_NEEDS_SOURCE_REREAD"


# ---- read-only / proof-only posture -----------------------------------------

def test_proof_is_read_only_and_places_nothing():
    src = inspect.getsource(p5)
    assert "truelinev2.render" not in src and "render_redline_stroke" not in src
    assert "place_bore" not in src and "run_match" not in src
    assert "RedlineService" not in src and "REDLINE_STROKE" not in src
    assert "FR._build_plan_frame_graph" in src and "RA.extract_run_assembly" in src
    assert "translate_between_sheets" in src


def test_proof_does_not_modify_core_modules():
    from pathlib import Path
    pkg = Path(p5.__file__).resolve().parents[1]
    assert (pkg / "match" / "run_assembly.py").exists()
    assert (pkg / "match" / "frames.py").exists()
    assert (pkg / "match" / "terminus_attribution.py").exists()
