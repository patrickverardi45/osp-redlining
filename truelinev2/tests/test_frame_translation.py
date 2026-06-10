"""M8.2c Step 2 — synthetic frame-translation behavior (no PDF, no real corpus).

Activates frame-aware linking/scoring ONLY when an explicit ``frame_graph`` is supplied,
and proves: default (None) is byte-identical to M7; same-sheet stays raw; a cross-sheet
link/score forms ONLY through a SAFE frame edge; raw-equal stations across sheets are not
proof; ambiguous/conflicting/missing edges block; untranslatable cross-frame chains are
unscoreable; and ``decide()``'s anchor-ambiguity gate still abstains. The real corpus
keeps passing ``frame_graph=None`` (proven 23/58 by the sweep), so default placement is
unchanged. The canonical edge is the M8.2a smoking gun: sheet 5 STA 3+23 == sheet 17 STA
0+69 (offset 254 ft).
"""
from __future__ import annotations

from truelinev2.match.chains import build_chains
from truelinev2.match.decide import decide
from truelinev2.match.frames import (
    build_frame_edges,
    build_frame_graph,
    frame_for_sheet,
    parse_frame_equations,
    translate_between_sheets,
)
from truelinev2.match.score import score_chain
from truelinev2.schema.frames import FrameEdge, ParseConfidence
from truelinev2.schema.models import Callout


def _callout(sheet: int, from_ft: float, to_ft: float, footage: float) -> Callout:
    return Callout(sheet=sheet, page=sheet, from_sta="a", to_sta="b",
                   from_ft=from_ft, to_ft=to_ft, footage=footage)


def _graph_5_17():
    eqs = parse_frame_equations("MATCH LINE STA 3+23 / 0+69 - SEE SHEET 17")
    g = build_frame_graph(build_frame_edges(eqs, frame_for_sheet(5)))
    assert g.edges and not g.conflicts  # one safe edge sheet 5 <-> sheet 17, offset 254
    return g


# --- the helper ---------------------------------------------------------------
def test_translate_between_sheets():
    g = _graph_5_17()
    assert translate_between_sheets(g, 5, 5, 100.0) == 100.0       # same sheet -> identity
    assert translate_between_sheets(g, 17, 5, 69.0) == 323.0       # 0+69 @s17 -> 3+23 @s5
    assert translate_between_sheets(g, 5, 17, 323.0) == 69.0       # reverse direction
    assert translate_between_sheets(g, 5, 99, 100.0) is None       # no safe edge -> None


# --- default (None) is byte-identical to M7 -----------------------------------
def test_build_chains_none_equals_omitted():
    cs = [_callout(8, 0.0, 100.0, 100.0), _callout(8, 100.0, 250.0, 150.0)]
    assert build_chains(cs, 0.0, 250.0) == build_chains(cs, 0.0, 250.0, frame_graph=None)


def test_score_chain_none_equals_omitted():
    chain = [_callout(5, 0.0, 100.0, 100.0)]
    assert score_chain(chain, 0.0, 100.0, 100.0) == score_chain(chain, 0.0, 100.0, 100.0, frame_graph=None)


# --- same-sheet stays raw even when a graph is supplied -----------------------
def test_same_sheet_unchanged_with_graph():
    cs = [_callout(8, 0.0, 100.0, 100.0), _callout(8, 100.0, 250.0, 150.0)]
    g = _graph_5_17()
    assert build_chains(cs, 0.0, 250.0, frame_graph=g) == build_chains(cs, 0.0, 250.0)


# --- cross-sheet: safe edge links; raw-equal / no-edge does not ---------------
def test_cross_sheet_links_through_safe_edge():
    a = _callout(5, 0.0, 323.0, 323.0)     # ends at 3+23 (323) on sheet 5
    b = _callout(17, 69.0, 200.0, 131.0)   # starts at 0+69 (69) on sheet 17
    g = _graph_5_17()
    assert [a, b] in build_chains([a, b], 0.0, 500.0, frame_graph=g)   # translated link forms
    assert [a, b] not in build_chains([a, b], 0.0, 500.0)              # raw 323 != 69 -> no link


def test_cross_sheet_raw_equal_is_not_proof():
    a = _callout(5, 0.0, 100.0, 100.0)
    b = _callout(8, 100.0, 200.0, 100.0)   # raw-equal 100 across sheets, but NO 5<->8 edge
    g = _graph_5_17()
    assert [a, b] not in build_chains([a, b], 0.0, 300.0, frame_graph=g)  # graph + no edge -> no link
    assert [a, b] in build_chains([a, b], 0.0, 300.0)                     # None -> raw link (M7 kept)


def test_cross_sheet_no_edge_does_not_link():
    a = _callout(5, 0.0, 323.0, 323.0)
    b = _callout(99, 69.0, 200.0, 131.0)   # sheet 99 has no safe edge to sheet 5
    assert [a, b] not in build_chains([a, b], 0.0, 500.0, frame_graph=_graph_5_17())


def test_ambiguous_or_conflicting_edge_blocks_link():
    e1 = FrameEdge(from_frame=frame_for_sheet(5), to_frame=frame_for_sheet(17),
                   offset_ft=254.0, confidence=ParseConfidence.HIGH)
    e2 = FrameEdge(from_frame=frame_for_sheet(5), to_frame=frame_for_sheet(17),
                   offset_ft=300.0, confidence=ParseConfidence.HIGH)
    g = build_frame_graph([e1, e2])                 # conflicting offsets -> no safe edge
    assert g.edges == [] and len(g.conflicts) == 1
    a = _callout(5, 0.0, 323.0, 323.0)
    b = _callout(17, 69.0, 200.0, 131.0)
    assert [a, b] not in build_chains([a, b], 0.0, 500.0, frame_graph=g)


# --- score_chain cross-frame end delta ----------------------------------------
def test_score_chain_cross_frame_end_delta_translated():
    a = _callout(5, 0.0, 323.0, 323.0)
    b = _callout(17, 69.0, 200.0, 131.0)
    g = _graph_5_17()
    chain = [a, b]
    # b ends at 200 on sheet 17 -> 200 + 254 = 454 on the sheet-5 anchor frame
    sc = score_chain(chain, 0.0, 454.0, 454.0, frame_graph=g)
    assert sc["end_delta"] == 0.0
    sc_raw = score_chain(chain, 0.0, 454.0, 454.0)         # None -> raw 200 -> |200-454|
    assert sc_raw["end_delta"] == 254.0


def test_score_chain_untranslatable_cross_frame_is_unscoreable():
    a = _callout(5, 0.0, 100.0, 100.0)
    b = _callout(99, 0.0, 100.0, 100.0)   # no 5<->99 edge -> far endpoint not translatable
    sc = score_chain([a, b], 0.0, 200.0, 200.0, frame_graph=_graph_5_17())
    assert sc["end_delta"] >= 1.0e9       # unscoreable sentinel -> decide() rejects it


# --- decide() anchor-ambiguity gate still blocks (decide.py untouched) --------
def test_decide_still_abstains_on_coequal_candidates():
    a = _callout(5, 0.0, 100.0, 100.0)
    b = _callout(5, 0.0, 200.0, 100.0)
    sc_a = {"summed_ft": 100.0, "start_delta": 0.0, "end_delta": 0.0, "foot_delta": 0.0,
            "vacant": 0, "sheets": [5], "multi_sheet": False, "n_boxes": 1,
            "chain_from": "0+00", "chain_to": "1+00"}
    sc_b = dict(sc_a, chain_to="2+00")    # same penalty (0), different signature -> co-equal rival
    d = decide([([a], sc_a), ([b], sc_b)], 100.0)
    assert d["status"] == "ABSTAIN" and d["winner"] is None and d["ambiguous"]
