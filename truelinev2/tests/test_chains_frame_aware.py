"""M8.2c Step 1 — frame-context plumbing is INERT (behavior-neutral).

Proves the optional ``frame_graph`` parameter threaded into ``build_chains`` /
``score_chain`` (and accepted by ``run_match``) is NEVER consulted in Step 1: passing
None, omitting it, or passing a POPULATED FrameGraph all yield byte-identical results.
No frame translation is active; coverage stays 23/58 (asserted separately by the corpus
sweep). The parameter is keyword-only so no existing positional call can bind into it.
"""
from __future__ import annotations

import inspect

import pytest

from truelinev2.match.chains import build_chains
from truelinev2.match.engine import run_match
from truelinev2.match.frames import (
    build_frame_edges,
    build_frame_graph,
    frame_for_sheet,
    parse_frame_equations,
)
from truelinev2.match.score import score_chain
from truelinev2.schema.frames import FrameGraph
from truelinev2.schema.models import Callout


def _callout(sheet: int, from_ft: float, to_ft: float, footage: float) -> Callout:
    return Callout(sheet=sheet, page=sheet, from_sta="a", to_sta="b",
                   from_ft=from_ft, to_ft=to_ft, footage=footage)


def _fixture():
    # one continuous 3-box chain on sheet 8 + an unlinkable box on sheet 10
    return [
        _callout(8, 0.0, 100.0, 100.0),
        _callout(8, 100.0, 250.0, 150.0),
        _callout(8, 250.0, 413.0, 163.0),
        _callout(10, 900.0, 1000.0, 100.0),
    ]


def _populated_graph() -> FrameGraph:
    eqs = parse_frame_equations("MATCH LINE STA 3+23 / 0+69 - SEE SHEET 17")
    g = build_frame_graph(build_frame_edges(eqs, frame_for_sheet(5)))
    assert g.edges  # a genuine safe edge exists (sheet 5 -> sheet 17, offset 254)
    return g


# --- build_chains inertness ---------------------------------------------------
def test_build_chains_default_equals_explicit_none():
    cs = _fixture()
    assert build_chains(cs, 0.0, 413.0) == build_chains(cs, 0.0, 413.0, frame_graph=None)


def test_build_chains_ignores_populated_graph():
    cs = _fixture()
    base = build_chains(cs, 0.0, 413.0)
    # a non-empty graph must NOT change the chains in Step 1 (never consulted)
    assert build_chains(cs, 0.0, 413.0, frame_graph=_populated_graph()) == base


# --- score_chain inertness ----------------------------------------------------
def test_score_chain_default_equals_none_and_populated_graph():
    cs = _fixture()
    ch = build_chains(cs, 0.0, 413.0)[0]
    base = score_chain(ch, 0.0, 413.0, 413.0)
    assert score_chain(ch, 0.0, 413.0, 413.0, frame_graph=None) == base
    assert score_chain(ch, 0.0, 413.0, 413.0, frame_graph=_populated_graph()) == base


# --- keyword-only guard (no positional binding into frame_graph) --------------
def test_frame_graph_is_keyword_only_on_build_chains():
    cs = _fixture()
    # callouts, start, end, start_tol, link_tol, max_depth, then a 7th positional has no
    # slot -> frame_graph is keyword-only, so this raises TypeError.
    with pytest.raises(TypeError):
        build_chains(cs, 0.0, 413.0, 8.0, 2.0, 6, _populated_graph())


def test_frame_graph_is_keyword_only_on_score_chain():
    cs = _fixture()
    ch = build_chains(cs, 0.0, 413.0)[0]
    with pytest.raises(TypeError):
        score_chain(ch, 0.0, 413.0, 413.0, _populated_graph())  # 5th positional -> TypeError


# --- run_match end-to-end plumbing present + keyword-only ----------------------
def test_run_match_accepts_keyword_only_frame_graph():
    params = inspect.signature(run_match).parameters
    assert "frame_graph" in params
    p = params["frame_graph"]
    assert p.kind == inspect.Parameter.KEYWORD_ONLY
    assert p.default is None
