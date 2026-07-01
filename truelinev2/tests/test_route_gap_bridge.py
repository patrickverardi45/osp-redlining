"""Proof for the read-only route-continuity / dash-gap bridge (gate G-b'''').

It reconnects colinear route fragments across small gaps in isolated linework, and refuses on non-colinear,
too-wide, ambiguous, lateral-branch, or loop-closing endpoint pairs. Colinearity + direction + uniqueness only --
never a nearest-endpoint guess, never a grid line, never a redline stroke. Name-free synthetic geometry;
class_verified always False. Inline geometry for the core; a real fitz PDF for the path driver.
"""
from __future__ import annotations

import fitz

from truelinev2.extract.route_gap_bridge import (
    NO_ROUTE_GAPS,
    ROUTE_BRIDGE_NOT_SUPPORTED,
    ROUTE_BRIDGE_TOPOLOGY_UNSAFE,
    ROUTE_GAP_AMBIGUOUS,
    ROUTE_GAP_NOT_COLINEAR,
    ROUTE_GAP_TOO_WIDE,
    ROUTE_GAPS_BRIDGED,
    UNMEASURABLE,
    bridge_plan_view_route_for_path,
    bridge_route_gaps,
)
from truelinev2.extract.route_main_run import MAIN_ROUTE_DISCRIMINATED, NO_MAIN_ROUTE, discriminate_main_run


def _chain(pts):
    return {"lines": [(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1]) for i in range(len(pts) - 1)]}


def _segs(*drawings):
    out = []
    for d in drawings:
        for (ax, ay, bx, by) in d["lines"]:
            out.append({"a": (ax, ay), "b": (bx, by)})
    return out


# --- a dashed main route reconnects across small colinear gaps ------------------------------------------ #
def test_dashed_route_reconnects():
    segs = _segs(_chain([(10, 10), (20, 10)]), _chain([(30, 10), (40, 10)]), _chain([(50, 10), (60, 10)]))
    obs = bridge_route_gaps(segs)
    assert obs.status == ROUTE_GAPS_BRIDGED and not obs.would_reject
    assert obs.components_before == 3 and obs.components_after == 1 and len(obs.bridges) == 2
    assert obs.class_verified is False


# --- nearby but non-colinear fragments refuse ---------------------------------------------------------- #
def test_non_colinear_refuses():
    segs = _segs(_chain([(0, 0), (10, 0)]), _chain([(20, 0), (20, 10)]))   # second fragment is perpendicular
    obs = bridge_route_gaps(segs)
    assert obs.status == ROUTE_GAP_NOT_COLINEAR and obs.would_reject


# --- an endpoint with two plausible colinear continuations refuses -------------------------------------- #
def test_ambiguous_targets_refuse():
    segs = _segs(_chain([(0, 0), (10, 0)]), _chain([(22, 0), (32, 0)]), _chain([(44, 0), (54, 0)]))
    obs = bridge_route_gaps(segs, max_gap=40)   # (10,0) has two colinear forward continuations
    assert obs.status == ROUTE_GAP_AMBIGUOUS and obs.would_reject


# --- a colinear continuation that is too far refuses --------------------------------------------------- #
def test_gap_too_wide_refuses():
    segs = _segs(_chain([(0, 0), (10, 0)]), _chain([(30, 0), (40, 0)]))    # 20-pt gap > max_gap 14
    obs = bridge_route_gaps(segs, max_gap=14)
    assert obs.status == ROUTE_GAP_TOO_WIDE and obs.would_reject


# --- a bridge that would close a loop (same fragment ends facing) refuses ------------------------------- #
def test_loop_closing_bridge_is_topology_unsafe():
    # a nearly-closed loop whose two ends face each other colinearly across a 10-pt gap (stubs long enough not to weld)
    frag = _chain([(15, 0), (0, 0), (0, 20), (40, 20), (40, 0), (25, 0)])
    obs = bridge_route_gaps(_segs(frag))
    assert obs.status == ROUTE_BRIDGE_TOPOLOGY_UNSAFE and obs.would_reject


# --- a lateral/service-drop is never chosen as the continuation ----------------------------------------- #
def test_bridge_ignores_lateral_and_takes_main():
    segs = _segs(_chain([(0, 0), (10, 0)]),        # fragment end at (10,0)
                 _chain([(20, 0), (30, 0)]),        # the true colinear continuation
                 _chain([(10, 10), (10, 24)]))      # a lateral stub near (10,0) at a right angle
    obs = bridge_route_gaps(segs)
    assert obs.status == ROUTE_GAPS_BRIDGED
    # the single bridge connects (10,0) to the main continuation (20,0), NOT the lateral end (16,4)
    assert len(obs.bridges) == 1
    ends = {(round(obs.bridges[0][0][0]), round(obs.bridges[0][0][1])),
            (round(obs.bridges[0][1][0]), round(obs.bridges[0][1][1]))}
    assert ends == {(10, 0), (20, 0)}


# --- an already-connected route has no gaps ------------------------------------------------------------ #
def test_already_connected_no_gaps():
    obs = bridge_route_gaps(_segs(_chain([(0, 0), (30, 0), (60, 0)])))
    assert obs.status == NO_ROUTE_GAPS and not obs.would_reject


# --- after bridging, G-b''' can discriminate a main route it could not before --------------------------- #
def test_bridging_enables_main_run_discrimination():
    a, b = (10.0, 25.0), (60.0, 25.0)
    dashes = _segs(_chain([(10, 10), (20, 10)]), _chain([(30, 10), (40, 10)]), _chain([(50, 10), (60, 10)]))
    before = discriminate_main_run(dashes, a, b, anchor_radius=18)
    assert before.status == NO_MAIN_ROUTE          # fragmented -> no spanning spine
    bridged = bridge_route_gaps(dashes)
    assert bridged.status == ROUTE_GAPS_BRIDGED
    after = discriminate_main_run(list(bridged.bridged_segments), a, b, anchor_radius=18)
    assert after.status == MAIN_ROUTE_DISCRIMINATED and after.class_verified is False


# --- end-to-end G-a -> G-b' -> G-b'''' over a real PDF: grid excluded, dashed route reconnects ---------- #
def _make_plan(tmp_path, labels, lines, rects=(), name="plan.pdf"):
    doc = fitz.open()
    page = doc.new_page(width=400, height=200)
    for text, x, y in labels:
        page.insert_text((x, y), text, fontsize=8)
    for (x0, y0, x1, y1) in lines:
        page.draw_line((x0, y0), (x1, y1), color=(1, 0, 0), width=1)
    for (x0, y0, x1, y1) in rects:
        page.draw_rect(fitz.Rect(x0, y0, x1, y1), color=(0, 0, 0), width=1)
    p = tmp_path / name
    doc.save(str(p))
    doc.close()
    return str(p)


def test_path_dashed_route_bridges_grid_excluded(tmp_path):
    # a dashed route (three dashes, ~10-pt gaps) between two labels, plus a grid box (excluded by G-b').
    path = _make_plan(tmp_path, [("0+00", 60, 100), ("1+00", 300, 100)],
                      [(70, 112, 130, 112), (140, 112, 220, 112), (230, 112, 300, 112)],
                      rects=[(60, 150, 120, 180)])
    ep, obs = bridge_plan_view_route_for_path(path, 1, 0.0, 100.0, start_source_bound=True,
                                              end_source_bound=True, max_gap=14)
    assert ep.start.located and ep.end.located
    assert obs.status == ROUTE_GAPS_BRIDGED and obs.class_verified is False
    assert obs.components_after < obs.components_before and len(obs.bridges) >= 1


def test_path_unlocated_endpoint_is_unmeasurable(tmp_path):
    path = _make_plan(tmp_path, [("0+00", 60, 100)], [(70, 112, 300, 112)])
    ep, obs = bridge_plan_view_route_for_path(path, 1, 0.0, 100.0, start_source_bound=True,
                                              end_source_bound=True, max_gap=14)
    assert not (ep.start.located and ep.end.located) and obs.status == UNMEASURABLE
