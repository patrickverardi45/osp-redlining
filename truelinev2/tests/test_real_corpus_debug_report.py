"""M8.2e -- pure classification-helper tests for the real-corpus debug report (no PDF).

Locks the ``classify_transition`` logic the report relies on: a cross-sheet transition is
``continuous_station`` (raw-continuous, no edge), ``reset_equation`` (a safe edge translates
the link), ``reset_equation_offset_mismatch`` (edge exists but its offset does not fit this
chain), ``ambiguous_conflicting`` (conflicting edges), or ``ambiguous_missing``. These are the
distinctions that explain why the M8.2c opt-in rule wrongly broke continuous runs.
"""
from __future__ import annotations

from truelinev2.match.frames import (
    build_frame_edges,
    build_frame_graph,
    frame_for_sheet,
    parse_frame_equations,
)
from truelinev2.proof.run_real_corpus_debug_report import _conflict_pairs, classify_transition
from truelinev2.schema.frames import FrameEdge, ParseConfidence
from truelinev2.schema.models import Callout


def _c(sheet: int, from_ft: float, to_ft: float) -> Callout:
    return Callout(sheet=sheet, page=sheet, from_sta="a", to_sta="b",
                   from_ft=from_ft, to_ft=to_ft, footage=to_ft - from_ft)


def _graph_5_17():
    eqs = parse_frame_equations("MATCH LINE STA 3+23 / 0+69 - SEE SHEET 17")
    return build_frame_graph(build_frame_edges(eqs, frame_for_sheet(5)))


def test_continuous_station():
    g = _graph_5_17(); cp = _conflict_pairs(g)
    t = classify_transition(g, cp, _c(8, 0, 100), _c(10, 100, 200))  # s8->s10, raw_gap 0, no edge
    assert t["classification"] == "continuous_station"
    assert t["raw_gap_ft"] == 0.0 and t["safe_edge"] is False and t["conflict"] is False


def test_reset_equation():
    g = _graph_5_17(); cp = _conflict_pairs(g)
    t = classify_transition(g, cp, _c(5, 0, 323), _c(17, 69, 200))   # 69@s17 -> 323@s5 == a.to_ft
    assert t["classification"] == "reset_equation" and t["safe_edge"] is True


def test_reset_equation_offset_mismatch():
    g = _graph_5_17(); cp = _conflict_pairs(g)
    t = classify_transition(g, cp, _c(5, 0, 100), _c(17, 69, 200))   # edge exists but 69->323 != 100
    assert t["classification"] == "reset_equation_offset_mismatch" and t["safe_edge"] is True


def test_ambiguous_missing():
    g = _graph_5_17(); cp = _conflict_pairs(g)
    t = classify_transition(g, cp, _c(5, 0, 100), _c(99, 500, 600))  # no edge, big raw gap
    assert t["classification"] == "ambiguous_missing"


def test_ambiguous_conflicting():
    e1 = FrameEdge(from_frame=frame_for_sheet(5), to_frame=frame_for_sheet(17),
                   offset_ft=254.0, confidence=ParseConfidence.HIGH)
    e2 = FrameEdge(from_frame=frame_for_sheet(5), to_frame=frame_for_sheet(17),
                   offset_ft=300.0, confidence=ParseConfidence.HIGH)
    g = build_frame_graph([e1, e2]); cp = _conflict_pairs(g)         # conflict on 5<->17
    t = classify_transition(g, cp, _c(5, 0, 323), _c(17, 69, 200))
    assert t["classification"] == "ambiguous_conflicting" and t["conflict"] is True
