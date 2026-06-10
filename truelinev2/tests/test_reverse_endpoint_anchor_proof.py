"""M8.5 -- tests for the reverse endpoint anchor solver + default-OFF wiring (no PDF).

Locks: flag defaults OFF; OFF/None is byte-identical; every tolerance is an existing
engine constant (pinned against build_chains defaults -- no drift, no widening); the
six-verdict taxonomy is closed; every non-READY verdict names the missing
relationship; matchline ends never anchor; >=2 reverse paths never tiebreak; footage
must close; the engine wiring REVIEW-caps (never AUTO), never overrides ambiguity,
never touches placed logs, and passes through the collision gate (demote-only).
"""
from __future__ import annotations

import dataclasses
import inspect

from truelinev2.config import Settings
from truelinev2.match.chains import build_chains
from truelinev2.match.engine import run_match
from truelinev2.match.frames import (
    build_frame_edges,
    build_frame_graph,
    frame_for_sheet,
    parse_frame_equations,
)
from truelinev2.match.reverse_anchor import (
    END_NOT_FOUND,
    FOOTAGE_MISMATCH,
    FRAME_CONFLICT,
    LINK_TOL_FT,
    MAX_DEPTH,
    OCR_REQUIRED,
    PICK_CARD,
    READY,
    START_TOL_FT,
    VERDICTS,
    ReverseAnchorContext,
    matchline_mask,
    prove_reverse_anchor,
    solve_reverse_anchor,
)
from truelinev2.match.transition_classifier import conflict_sheet_pairs
from truelinev2.schema.models import Bore, Callout, PlacementStatus
from truelinev2.stations import feet_to_station


def _c(sheet, f0, f1):
    return Callout(sheet=sheet, page=sheet, from_sta=feet_to_station(f0),
                   to_sta=feet_to_station(f1), from_ft=f0, to_ft=f1,
                   footage=round(f1 - f0, 2), text=f"s{sheet} {f0}->{f1}", dialect="test")


def _bore(s, e, sheets, span=None):
    return Bore(bore_id="logT", source_file="logT.xlsx", sheet_refs=list(sheets),
                station_start=feet_to_station(s), station_end=feet_to_station(e),
                station_start_ft=s, station_end_ft=e,
                span_ft=round((e - s) if span is None else span, 2))


class _StubDialect:
    name = "test"
    match_mode = "footage"

    def __init__(self, callouts):
        self._c = callouts

    def extract_callouts(self, plan, sheet, offset):
        return [c for c in self._c if c.sheet == sheet]


def _prove(callouts, start, end, span=None, graph=None, equations=None, end_text=None):
    return prove_reverse_anchor(
        bore_id="logT", bore_start_ft=start, bore_end_ft=end,
        span_ft=round((end - start) if span is None else span, 2),
        callouts=callouts, graph=graph, conflicts=conflict_sheet_pairs(graph),
        equations_by_sheet=equations or {}, end_text_found_in_plan=end_text)


def _graph(*texts_with_sheets):
    edges = []
    for text, sheet in texts_with_sheets:
        edges.extend(build_frame_edges(parse_frame_equations(text), frame_for_sheet(sheet)))
    return build_frame_graph(edges)


def _ctx(graph=None, equations=None):
    return ReverseAnchorContext(graph=graph, conflicts=conflict_sheet_pairs(graph),
                                equations_by_sheet=equations or {})


# --- flag + constants ---------------------------------------------------------------

def test_flag_defaults_off():
    assert Settings.for_proof().reverse_endpoint_optin is False
    on = dataclasses.replace(Settings.for_proof(), reverse_endpoint_optin=True)
    assert on.reverse_endpoint_optin is True


def test_env_flag_parsing(monkeypatch):
    monkeypatch.setenv("TL2_REVERSE_ENDPOINT_ANCHOR_OPTIN", "1")
    assert Settings.from_env().reverse_endpoint_optin is True
    monkeypatch.setenv("TL2_REVERSE_ENDPOINT_ANCHOR_OPTIN", "0")
    assert Settings.from_env().reverse_endpoint_optin is False
    monkeypatch.delenv("TL2_REVERSE_ENDPOINT_ANCHOR_OPTIN")
    assert Settings.from_env().reverse_endpoint_optin is False


def test_constants_pinned_to_chains_defaults():
    # The solver re-cites the forward linker's constants; if build_chains ever moves
    # them, this test forces the solver to move with it (no solver-local drift).
    params = inspect.signature(build_chains).parameters
    assert START_TOL_FT == params["start_tol"].default
    assert LINK_TOL_FT == params["link_tol"].default
    assert MAX_DEPTH == params["max_depth"].default


# --- end-anchor gating (no widening) -------------------------------------------------

def test_end_tolerance_boundary_not_widened():
    # span 100 -> review_end is exactly 8.0; 8.0 in, 8.01 out.
    at_tol = [_c(1, 0, 108)]
    p = _prove(at_tol, 0, 100, span=100)
    assert p["end_anchor_candidates"]
    beyond = [_c(1, 0, 108.01)]
    p2 = _prove(beyond, 0, 100, span=100)
    assert p2["result"] == END_NOT_FOUND


def test_end_not_found_names_mid_callout():
    # the log15 class: bore end strictly inside an authored run, no run ENDS there.
    p = _prove([_c(1, 3064, 3393)], 2400, 3100)
    assert p["result"] == END_NOT_FOUND
    assert "MID-CALLOUT" in p["named_missing_relationship"]


def test_ocr_verdict_only_when_text_scan_negative():
    # the log16 class: the station string is absent from the whole text layer.
    cos = [_c(1, 0, 300)]
    assert _prove(cos, 5100, 5950, end_text=False)["result"] == OCR_REQUIRED
    assert _prove(cos, 5100, 5950, end_text=True)["result"] == END_NOT_FOUND
    assert _prove(cos, 5100, 5950, end_text=None)["result"] == END_NOT_FOUND


def test_matchline_end_is_a_continuation_marker_not_an_anchor():
    # the log53/log72 class: the only end match ENDS on a matchline frame equation.
    eqs = {1: tuple(parse_frame_equations("MATCH LINE STA 5+00 / 0+20 - SEE SHEET 2"))}
    cos = [_c(1, 100, 500)]
    assert matchline_mask(cos[0], eqs, 8.0) is not None
    p = _prove(cos, 100, 500, equations=eqs)
    assert p["result"] == END_NOT_FOUND
    assert "continuation marker" in p["named_missing_relationship"]


# --- the solver core ------------------------------------------------------------------

def test_single_callout_containment_ready_log7_shape():
    # bore 55->451 inside the authored 0+00->4+51 run; computed start 0+55 delta 0.
    p, path = solve_reverse_anchor(
        bore_id="log7", bore_start_ft=55, bore_end_ft=451, span_ft=396,
        callouts=[_c(10, 0, 451)], graph=None, conflicts=set(), equations_by_sheet={})
    assert p["result"] == READY and path is not None
    assert p["computed_start_ft"] == 55.0 and p["start_delta_vs_borelog_ft"] == 0.0
    assert p["never_auto"] is True and p["review_gated_only"] is True
    assert "REVERSE_ENDPOINT_ANCHOR" in p["caveats"]


def test_multi_callout_same_sheet_chain_ready():
    cos = [_c(12, 190, 350), _c(12, 350, 507)]
    p = _prove(cos, 265, 500, span=235)
    assert p["result"] == READY
    assert p["computed_start_ft"] == 272.0 and p["start_delta_vs_borelog_ft"] == 7.0


def test_footage_gap_refused_log70_shape():
    # end anchors but the authored run starts 175 ft after the expected start.
    p = _prove([_c(20, 175, 215)], 0, 215)
    assert p["result"] == FOOTAGE_MISMATCH
    assert "NO authored callout behind it" in p["named_missing_relationship"]


def test_two_distinct_paths_pick_card():
    # two complete paths on different sheets -> never tiebreak (M8.3a law).
    cos = [_c(1, 0, 500), _c(2, 0, 500)]
    p = _prove(cos, 100, 500, span=400)
    assert p["result"] == PICK_CARD
    assert "pick-card" in p["named_missing_relationship"]


def test_ambiguous_crossing_refused_frame_conflict_log9_shape():
    # raw continuity at the crossing DISPUTED by a safe equation (s14 10+44 == s7
    # 9+53 -> offset 91): the classifier says ambiguous; the walk must refuse.
    graph = _graph(("MATCH LINE STA 10+44 / 9+53 - SEE SHEET 7", 14))
    cos = [_c(14, 389, 1044), _c(7, 1044, 1100), _c(7, 1100, 1264)]
    p = _prove(cos, 534, 1264, span=730, graph=graph)
    assert p["result"] == FRAME_CONFLICT
    assert "[(7, 14)]" in p["named_missing_relationship"]
    assert any(r["classification"] == "ambiguous" for r in p["refused_hops"])


def test_reset_equation_hop_translates_and_confirms_start():
    # s1's 6+00 == s2's 1+00 (offset 500). Anchor s2 1+00->5+00; predecessor s1
    # 5+00->6+00 translates to s2 0+00->1+00; bore 0+50->5+00 (450 ft) closes.
    graph = _graph(("MATCH LINE STA 6+00 / 1+00 - SEE SHEET 2", 1))
    cos = [_c(1, 500, 600), _c(2, 100, 500)]
    p = _prove(cos, 50, 500, span=450, graph=graph)
    assert p["result"] == READY
    assert "FRAME_TRANSLATED_HOP" in p["caveats"]
    assert p["computed_start_ft"] == 50.0 and p["start_confirmed"] is True


def test_start_disagreement_is_a_frame_conflict():
    # span-inconsistent bore: end+footage close but the computed start disagrees
    # with the bore-log start beyond the EXISTING start tolerance -> never place.
    p = _prove([_c(1, 0, 500)], 100, 500, span=350)
    assert p["result"] == FRAME_CONFLICT
    assert "implied local-frame offset" in p["named_missing_relationship"]
    assert p["start_confirmed"] is False


def test_verdicts_confined_and_named():
    # every verdict is one of the six; every non-READY names the relationship.
    fixtures = [
        _prove([_c(1, 0, 300)], 5100, 5950, end_text=False),
        _prove([_c(1, 3064, 3393)], 2400, 3100),
        _prove([_c(20, 175, 215)], 0, 215),
        _prove([_c(1, 0, 500), _c(2, 0, 500)], 100, 500, span=400),
        _prove([_c(10, 0, 451)], 55, 451, span=396),
    ]
    for p in fixtures:
        assert p["result"] in VERDICTS
        if p["result"] != READY:
            assert p["named_missing_relationship"].strip()


# --- engine wiring (default-OFF) ------------------------------------------------------

_REVERSE_FIXTURE = [_c(1, 0, 300), _c(2, 300, 500)]  # raw-continuous; bore 50->500


def test_engine_off_none_is_byte_identical_abstain():
    off = run_match(_bore(50, 500, [1, 2]), None, _StubDialect(_REVERSE_FIXTURE), 0)
    explicit = run_match(_bore(50, 500, [1, 2]), None, _StubDialect(_REVERSE_FIXTURE), 0,
                         reverse_anchor=None)
    assert off.status is PlacementStatus.ABSTAIN
    assert off == explicit


def test_engine_reverse_places_review_never_auto():
    # exact end delta + exact start agreement would be AUTO-grade evidence on the
    # forward path -- the reverse retry must cap at REVIEW with its caveats.
    pl = run_match(_bore(50, 500, [1, 2]), None, _StubDialect(_REVERSE_FIXTURE), 0,
                   reverse_anchor=_ctx())
    assert pl.status is PlacementStatus.REVIEW
    assert pl.reason == "REVERSE_ENDPOINT_ANCHOR"
    assert "REVERSE_ENDPOINT_ANCHOR" in pl.caveats
    assert "NEVER_AUTO_BY_CONSTRUCTION" in pl.caveats
    assert pl.start_delta == 0.0 and pl.end_delta == 0.0
    assert [c.sheet for c in pl.matched_callouts] == [1, 2]


def test_engine_ambiguity_is_never_overridden():
    tie = [_c(1, 0, 500), _c(3, 2, 502)]
    pl = run_match(_bore(0, 500, [1, 2, 3]), None, _StubDialect(tie + _REVERSE_FIXTURE), 0,
                   reverse_anchor=_ctx())
    assert pl.status is PlacementStatus.ABSTAIN
    assert pl.reason == "GE_2_COEQUAL_CANDIDATES_NO_TIEBREAKER"


def test_engine_existing_placements_untouched():
    # a start-anchored continuous run places AUTO on the primary path; the reverse
    # context must not change a single byte of it.
    raw = [_c(1, 0, 300), _c(2, 300, 500)]
    off = run_match(_bore(0, 500, [1, 2]), None, _StubDialect(raw), 0)
    on = run_match(_bore(0, 500, [1, 2]), None, _StubDialect(raw), 0, reverse_anchor=_ctx())
    assert off.status is PlacementStatus.AUTO_SELECT
    assert on == off


def test_engine_reverse_passes_through_collision_gate():
    # the reverse placement is gated like any other: a graded abstain_required
    # collision on its crossing demotes REVIEW -> ABSTAIN (demote-only).
    from truelinev2.match.collision_gate import CollisionGate
    gate_eqs = {1: tuple(parse_frame_equations(
        "MATCHLINE STA 3+00/1+00 - SEE SHEET 2 ................ "
        "MATCHLINE STA 3+00/1+05 - SEE SHEET 2")), 2: ()}
    gate = CollisionGate(equations_by_sheet=gate_eqs,
                         human_grades={"logT": "abstain_required"})
    pl = run_match(_bore(50, 500, [1, 2]), None, _StubDialect(_REVERSE_FIXTURE), 0,
                   reverse_anchor=_ctx(), collision_gate=gate)
    assert pl.status is PlacementStatus.ABSTAIN
    assert "RESET_COLLISION_GATE" in pl.caveats


def test_engine_no_end_anchor_still_abstains():
    # the log15/log16 class survives wiring: no end anchor -> abstain unchanged.
    far = [_c(1, 4000, 4300)]
    pl = run_match(_bore(0, 500, [1]), None, _StubDialect(far), 0, reverse_anchor=_ctx())
    assert pl.status is PlacementStatus.ABSTAIN
    assert pl.reason == "NO_AUTHORED_BOX_MATCH_FOR_BORE_SPAN"


# --- adversarial-review fixes (pinned) ------------------------------------------------

def test_frame_doppelganger_anchor_refused():
    # CRITICAL fix: a safe reset edge (s1 5+00 == s2 0+00) declares the frames
    # distinct; a raw end-equality anchor on s2 whose path never crosses the edge
    # is a frame doppelganger -> FRAME_CONFLICT, never a placement.
    graph = _graph(("MATCH LINE STA 5+00 / 0+00 - SEE SHEET 2", 1))
    cos = [_c(1, 50, 330), _c(1, 330, 480), _c(2, 10, 501)]
    p = _prove(cos, 50, 500, graph=graph)
    assert p["result"] == FRAME_CONFLICT
    assert "frame-doppelganger" in p["named_missing_relationship"]
    assert p["frame_incoherent_paths"]
    # engine-level: must abstain, not place
    pl = run_match(_bore(50, 500, [1, 2]), None, _StubDialect(cos), 0,
                   reverse_anchor=_ctx(graph=graph))
    assert pl.status is PlacementStatus.ABSTAIN


def test_reset_boundary_end_is_masked_log36_shape():
    # CRITICAL fix: 'STA 1+45=0+00' is an installer-HH drive boundary; a run
    # ending 3 ft from it is boundary evidence, not a terminus -> masked.
    eqs = {17: tuple(parse_frame_equations("STA 1+45=0+00"))}
    cos = [_c(17, 0, 142)]
    assert matchline_mask(cos[0], eqs, 8.0) is not None
    p = _prove(cos, 56, 145, span=89, equations=eqs)
    assert p["result"] == END_NOT_FOUND
    assert "drive-boundary" in p["named_missing_relationship"]


def test_near_rival_end_demotes_to_pick_card_log5_shape():
    # CRITICAL fix: two parallel drop lanes ending 3 ft apart (5+07 vs 5+10);
    # a bore end needing 7 ft of slop cannot distinguish them -> pick-card.
    cos = [_c(12, 190, 350), _c(12, 350, 507), _c(12, 191, 355), _c(12, 355, 510)]
    p = _prove(cos, 265, 500, span=235)
    assert p["result"] == PICK_CARD
    assert p["near_rival_ends"]
    assert "rival run end" in p["named_missing_relationship"]


def test_matchline_mask_other_sheet_authored():
    # mask must catch equations authored on the FAR side of the pair (linked-frame)
    # and other-station-first (b-side) variants -- the collision gate's both-sides
    # precedent.
    far_side = {2: tuple(parse_frame_equations("MATCH LINE STA 0+00 / 5+00 - SEE SHEET 1"))}
    assert matchline_mask(_c(1, 100, 500), far_side, 8.0) is not None
    b_side = {1: tuple(parse_frame_equations("MATCH LINE STA 0+00 / 5+00 - SEE SHEET 2"))}
    assert matchline_mask(_c(1, 100, 500), b_side, 8.0) is not None


def test_engine_footage_ambiguity_not_tiebroken_by_reverse():
    # REAL fix: the unique-footage fallback declared two coequal candidates; the
    # reverse retry may NOT place one of those rivals (that would be tiebreaking).
    # span 400 -> review_foot 24; both callouts footage 410 (delta 10 -> coequal).
    cos = [_c(1, 90, 500), _c(2, 1000, 1410)]
    pl = run_match(_bore(100, 500, [1, 2]), None, _StubDialect(cos), 0,
                   reverse_anchor=_ctx())
    assert pl.status is PlacementStatus.ABSTAIN


def test_engine_reverse_disjoint_from_footage_rivals_still_places():
    # ...but a reverse winner DISJOINT from the declared rivals is new positional
    # evidence, not a tiebreak: it places REVIEW. Rivals: two footage-380 decoys
    # (span 400 -> review_foot 24 -> coequal); winner chain footages 300+200.
    cos = [_c(1, 0, 300), _c(1, 300, 500), _c(3, 5000, 5380), _c(4, 6000, 6380)]
    pl = run_match(_bore(100, 500, [1, 3, 4]), None, _StubDialect(cos), 0,
                   reverse_anchor=_ctx())
    assert pl.status is PlacementStatus.REVIEW
    assert pl.reason == "REVERSE_ENDPOINT_ANCHOR"


def test_budget_exhaustion_blocks_ready():
    # an incomplete search can never prove uniqueness -> PICK_CARD, never READY.
    p, path = solve_reverse_anchor(
        bore_id="logT", bore_start_ft=50, bore_end_ft=500, span_ft=450,
        callouts=[_c(1, 0, 300), _c(1, 300, 500)], graph=None, conflicts=set(),
        equations_by_sheet={}, max_expansions=1)
    assert p["result"] == PICK_CARD and path is None
    assert p["search_budget_exhausted"] is True
    assert "budget" in p["named_missing_relationship"]


def test_duplicate_station_distinct_evidence_pick_cards():
    # two boxes authored at the SAME stations with different footage/vacancy are
    # physically distinct evidence -> distinct signatures -> pick-card.
    a = _c(1, 100, 500)
    b = Callout(sheet=1, page=1, from_sta=feet_to_station(100), to_sta=feet_to_station(500),
                from_ft=100, to_ft=500, footage=90.0, vacant=True,
                text="s1 dup vacant 90", dialect="test")
    p = _prove([a, b], 150, 500, span=350)
    assert p["result"] == PICK_CARD


def test_ready_carries_vacancy_and_honesty_fields():
    cos = [_c(12, 190, 350), _c(12, 350, 507)]
    cos[1] = cos[1].model_copy(update={"vacant": True})
    p = _prove(cos, 265, 500, span=235)
    assert p["result"] == READY
    assert "VACANT_IN_CHAIN" in p["caveats"]
    # span-consistent bore: the start check is implied by the end check -- honesty
    # field must say so.
    assert p["start_check_independent"] is False
