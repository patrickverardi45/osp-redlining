"""M8.2b — frame model + parser foundation tests (pure; no PDF, no placement).

Proves: station parsing reuse, the equation grammar (``=`` and ``/`` forms), safe-edge
acceptance, ambiguity/conflict rejection, raw-equal-is-not-proof, and translation
through a safe edge. Exercises truelinev2.schema.frames + truelinev2.match.frames
ONLY; invokes no placement path and imports nothing from the matcher decision modules.
The canonical case is the M8.2a smoking gun: sheet 5 STA 3+23 == sheet 17 STA 0+69
(offset 254 ft) -- proof that a raw 0+69 -> 0+69 link across that matchline is wrong.
"""
from __future__ import annotations

import ast
import inspect

from truelinev2.match.frames import (
    build_frame_edges,
    build_frame_graph,
    detect_conflicts,
    frame_for_sheet,
    parse_frame_equations,
    parse_station_value,
    safe_edges,
    translate_station_ft,
)
from truelinev2.schema.frames import EquationKind, FrameEdge, ParseConfidence
from truelinev2.stations import parse_station


# 1-2: station parsing (reuses the single existing parser)
def test_parse_station_3p23_is_323ft():
    assert parse_station("3+23") == 323.0
    assert parse_station_value("3+23").feet == 323.0


def test_parse_station_0p69_is_69ft():
    assert parse_station("0+69") == 69.0
    assert parse_station_value("0+69").feet == 69.0


# 3: equals form parses into a frame-equation candidate
def test_equals_equation_parses():
    eqs = parse_frame_equations("STA 3+23 = 0+69 - SEE SHEET 17")
    assert len(eqs) == 1
    e = eqs[0]
    assert e.a.feet == 323.0 and e.b.feet == 69.0 and e.separator == "="
    assert e.offset_ft == 254.0
    assert e.kind == EquationKind.CROSS_FRAME and e.linked_frames == [17]


# 4: slash form parses (the probe-proven grammar)
def test_slash_equation_parses_high_confidence():
    eqs = parse_frame_equations("MATCH LINE STA 3+23 / 0+69 - SEE SHEET 17")
    assert len(eqs) == 1 and eqs[0].separator == "/"
    assert eqs[0].confidence == ParseConfidence.HIGH  # matchline + exactly one link


def test_callouts_and_fractions_are_not_equations():
    assert parse_frame_equations("STA 0+00 TO STA 2+99 DIR. BORE (299')") == []
    assert parse_frame_equations('1-1.25" HDPE and 1/4 turn') == []


# 5: a clean unique edge is accepted as safe
def test_clean_unique_edge_is_safe():
    eqs = parse_frame_equations("MATCH LINE STA 3+23 / 0+69 - SEE SHEET 17")
    edges = build_frame_edges(eqs, frame_for_sheet(5))
    assert len(edges) == 1
    graph = build_frame_graph(edges)
    assert len(graph.edges) == 1 and graph.conflicts == []
    assert graph.edges[0].from_frame == frame_for_sheet(5)
    assert graph.edges[0].to_frame == frame_for_sheet(17)
    assert graph.edges[0].confidence == ParseConfidence.HIGH


# 6: multi-link ambiguity builds no safe edge (unsafe)
def test_multi_link_equation_builds_no_safe_edge():
    eqs = parse_frame_equations("MATCH LINE STA 3+23 / 0+69 SEE SHEET 17 SEE SHEET 18")
    assert eqs[0].linked_frames == [17, 18]
    assert eqs[0].confidence != ParseConfidence.HIGH  # link is not unique
    edges = build_frame_edges(eqs, frame_for_sheet(5))
    assert edges == []                                 # >1 link -> no edge built
    assert build_frame_graph(edges).edges == []


# 7: conflicting offsets for one frame pair are rejected
def test_conflicting_offsets_rejected():
    e1 = FrameEdge(from_frame=frame_for_sheet(5), to_frame=frame_for_sheet(17),
                   offset_ft=254.0, confidence=ParseConfidence.HIGH)
    e2 = FrameEdge(from_frame=frame_for_sheet(5), to_frame=frame_for_sheet(17),
                   offset_ft=300.0, confidence=ParseConfidence.HIGH)
    assert len(detect_conflicts([e1, e2])) == 1
    assert safe_edges([e1, e2]) == []                  # conflicted pair -> nothing safe
    graph = build_frame_graph([e1, e2])
    assert graph.edges == [] and len(graph.conflicts) == 1


def test_consistent_duplicate_offsets_are_not_a_conflict():
    e1 = FrameEdge(from_frame=frame_for_sheet(5), to_frame=frame_for_sheet(17),
                   offset_ft=254.0, confidence=ParseConfidence.HIGH)
    e2 = FrameEdge(from_frame=frame_for_sheet(17), to_frame=frame_for_sheet(5),
                   offset_ft=-254.0, confidence=ParseConfidence.HIGH)  # reverse, consistent
    assert detect_conflicts([e1, e2]) == []
    assert len(build_frame_graph([e1, e2]).edges) == 1  # deduped to one safe edge


# 8: raw equal station values across different frames are NOT proof
def test_raw_equal_values_are_not_proof():
    # no separator + no SEE-SHEET -> no equation, no edge
    assert parse_frame_equations("sheet 5 STA 0+69 ... sheet 17 STA 0+69") == []
    empty = build_frame_graph([])
    # translating an unknown pair ABSTAINS (None) -- never returns the raw feet
    assert translate_station_ft(empty, frame_for_sheet(5), frame_for_sheet(17), 69.0) is None


# 9: translation through a safe edge (the M8.2a smoking gun)
def test_translation_through_safe_edge():
    eqs = parse_frame_equations("MATCH LINE STA 3+23 / 0+69 - SEE SHEET 17")
    graph = build_frame_graph(build_frame_edges(eqs, frame_for_sheet(5)))
    # sheet 5 STA 3+23 (323 ft) maps to sheet 17 STA 0+69 (69 ft)
    assert translate_station_ft(graph, frame_for_sheet(5), frame_for_sheet(17), 323.0) == 69.0
    # the same safe edge translates the reverse direction
    assert translate_station_ft(graph, frame_for_sheet(17), frame_for_sheet(5), 69.0) == 323.0
    # same-frame translation is identity
    assert translate_station_ft(graph, frame_for_sheet(5), frame_for_sheet(5), 323.0) == 323.0


# 10 (structural): the foundation imports nothing from the placement-decision modules
def test_frame_core_imports_no_placement_modules():
    import truelinev2.match.frames as fr
    import truelinev2.schema.frames as sc
    forbidden = ("truelinev2.match.chains", "truelinev2.match.engine",
                 "truelinev2.match.decide", "truelinev2.match.assembly",
                 "truelinev2.match.score", "truelinev2.match.overlap")
    for mod in (fr, sc):
        tree = ast.parse(inspect.getsource(mod))
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
            elif isinstance(node, ast.Import):
                imported += [a.name for a in node.names]
        for bad in forbidden:
            assert not any(bad in name for name in imported), f"{mod.__name__} imports {bad}"
