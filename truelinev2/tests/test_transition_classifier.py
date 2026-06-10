"""M8.2f -- pure unit tests for the cross-sheet transition classifier (no PDF, no engine).

Locks the 6-class taxonomy and, critically, the two SAFETY properties that the first
frame opt-in violated:
  * a continuous-station transition (raw-continuous, no edge) is NEVER called a reset;
  * a reset/equation (a safe edge with a non-zero offset) is NEVER waved through by a
    coincidental raw equal-station -- it classifies AMBIGUOUS, not continuous.
"""
from __future__ import annotations

from truelinev2.match.frames import (
    build_frame_edges,
    build_frame_graph,
    frame_for_sheet,
    parse_frame_equations,
)
from truelinev2.match.transition_classifier import (
    TransitionClass,
    classify_callout_transition,
    classify_chain,
    classify_sheet_relationship,
    conflict_sheet_pairs,
    cross_sheet_transitions,
)
from truelinev2.schema.frames import FrameEdge, ParseConfidence
from truelinev2.schema.models import Callout


def _c(sheet: int, from_ft: float, to_ft: float) -> Callout:
    return Callout(sheet=sheet, page=sheet, from_sta="a", to_sta="b",
                   from_ft=from_ft, to_ft=to_ft, footage=to_ft - from_ft)


def _graph_5_17():
    """A real, safe edge sheet5 <-> sheet17 (offset 254 ft) parsed from a matchline."""
    eqs = parse_frame_equations("MATCH LINE STA 3+23 / 0+69 - SEE SHEET 17")
    g = build_frame_graph(build_frame_edges(eqs, frame_for_sheet(5)))
    return g, conflict_sheet_pairs(g)


def _conflicting_graph_5_17():
    e1 = FrameEdge(from_frame=frame_for_sheet(5), to_frame=frame_for_sheet(17),
                   offset_ft=254.0, confidence=ParseConfidence.HIGH)
    e2 = FrameEdge(from_frame=frame_for_sheet(5), to_frame=frame_for_sheet(17),
                   offset_ft=300.0, confidence=ParseConfidence.HIGH)
    g = build_frame_graph([e1, e2])
    return g, conflict_sheet_pairs(g)


# --- the six classes ----------------------------------------------------------------

def test_same_sheet():
    g, cp = _graph_5_17()
    r = classify_callout_transition(g, cp, _c(8, 0, 100), _c(8, 100, 200))
    assert r.classification is TransitionClass.SAME_SHEET
    assert r.same_sheet is True and r.linkable is True


def test_continuous_station():
    g, cp = _graph_5_17()
    r = classify_callout_transition(g, cp, _c(8, 0, 100), _c(10, 100, 200))  # raw_gap 0, no edge
    assert r.classification is TransitionClass.CONTINUOUS_STATION
    assert r.raw_gap_ft == 0.0 and r.safe_edge is False and r.conflict is False
    assert r.linkable is True


def test_continuous_station_with_no_graph_matches_default_matcher():
    # graph=None -> no edge is ever found, mirroring the default raw matcher exactly.
    r = classify_callout_transition(None, set(), _c(8, 0, 100), _c(10, 100, 200))
    assert r.classification is TransitionClass.CONTINUOUS_STATION
    assert r.safe_edge is False


def test_reset_equation_edge_reconciles_endpoints():
    g, cp = _graph_5_17()
    # 69@s17 translates to 323@s5, which equals a.to_ft -> the reset reconciles the chain.
    r = classify_callout_transition(g, cp, _c(5, 0, 323), _c(17, 69, 200))
    assert r.classification is TransitionClass.RESET_EQUATION
    assert r.safe_edge is True and r.translated_gap_ft == 0.0
    assert r.linkable is True


def test_reset_equation_relationship_level_without_endpoints():
    # log11-style: no placed chain, but the two frames ARE linked by a safe reset edge.
    g, cp = _graph_5_17()
    r = classify_sheet_relationship(g, cp, 5, 17)
    assert r.classification is TransitionClass.RESET_EQUATION
    assert r.safe_edge is True and r.edge_offset_ft == 254.0


def test_ambiguous_raw_equal_but_reset_edge_disagrees():
    # SAFETY: raw_gap ~= 0 AND a safe edge whose offset breaks continuity -> ambiguous,
    # never continuous. This is exactly how a reset must NOT slip through raw matching.
    g, cp = _graph_5_17()
    r = classify_callout_transition(g, cp, _c(5, 0, 100), _c(17, 100, 200))  # raw_gap 0
    assert r.classification is TransitionClass.AMBIGUOUS
    assert r.raw_gap_ft == 0.0 and r.safe_edge is True and r.translated_gap_ft > 2.0
    assert r.linkable is False


def test_missing_evidence_no_edge_big_gap():
    g, cp = _graph_5_17()
    r = classify_callout_transition(g, cp, _c(8, 0, 100), _c(99, 500, 600))  # no edge, big gap
    assert r.classification is TransitionClass.MISSING_EVIDENCE
    assert r.safe_edge is False and r.linkable is False


def test_missing_evidence_edge_offset_mismatch_no_continuity():
    g, cp = _graph_5_17()
    # edge exists but 69->323 != 100, and raw_gap (100) is not continuous either.
    r = classify_callout_transition(g, cp, _c(5, 0, 100), _c(17, 0, 200))
    assert r.classification is TransitionClass.MISSING_EVIDENCE
    assert r.safe_edge is True and r.linkable is False


def test_conflict_takes_precedence_over_edge():
    g, cp = _conflicting_graph_5_17()
    assert cp == {(5, 17)}
    r = classify_callout_transition(g, cp, _c(5, 0, 323), _c(17, 69, 200))
    assert r.classification is TransitionClass.CONFLICT
    assert r.conflict is True and r.linkable is False


# --- the two safety properties, stated directly -------------------------------------

def test_property_continuous_never_classified_reset():
    # A genuinely continuous run (no edge) must never be a reset, for any raw-continuous pair.
    g, cp = _graph_5_17()
    for sa, sb in [(8, 10), (10, 12), (1, 2)]:
        r = classify_callout_transition(g, cp, _c(sa, 0, 100), _c(sb, 100, 200))
        assert r.classification is TransitionClass.CONTINUOUS_STATION
        assert r.classification is not TransitionClass.RESET_EQUATION


def test_property_reset_never_passes_as_continuous_via_raw_equal():
    # A reset frame pair (safe edge, offset 254) with a coincidental equal raw station
    # must NOT be continuous; it is ambiguous (refused).
    g, cp = _graph_5_17()
    r = classify_callout_transition(g, cp, _c(5, 0, 69), _c(17, 69, 200))  # raw equal at 69
    assert r.classification is not TransitionClass.CONTINUOUS_STATION
    assert r.classification is TransitionClass.AMBIGUOUS and r.linkable is False


# --- chain helpers ------------------------------------------------------------------

def test_classify_chain_and_cross_sheet_filter():
    g, cp = _graph_5_17()
    chain = [_c(8, 0, 100), _c(10, 100, 200), _c(10, 200, 300)]  # cross then same-sheet
    results = classify_chain(g, cp, chain)
    assert [r.classification for r in results] == [
        TransitionClass.CONTINUOUS_STATION, TransitionClass.SAME_SHEET]
    cross = cross_sheet_transitions(results)
    assert len(cross) == 1 and cross[0].classification is TransitionClass.CONTINUOUS_STATION
    assert all(r.linkable for r in results)


def test_empty_and_singleton_chains_have_no_transitions():
    g, cp = _graph_5_17()
    assert classify_chain(g, cp, []) == []
    assert classify_chain(g, cp, [_c(8, 0, 100)]) == []
