"""Proof for the read-only isolated-route -> anchor composition gate (G-b'').

It binds each printed-station label to a UNIQUE drawn route TERMINUS taken from G-b''s route-isolated linework
(never a nearest-line snap, never a grid/box line), then re-verifies the run between the two improved anchors.
Refusal-first: refuses on 0 / >=2 candidate termini, on a still-forked route, on a broken run, and when isolation
yields no usable route. Name-free synthetic geometry; class_verified always False. Mirrors the observer test
pattern (inline geometry for the core; a real fitz PDF for the path driver).
"""
from __future__ import annotations

import fitz

from truelinev2.extract.isolated_route_anchor import (
    ISOLATED_ROUTE_ANCHOR_AMBIGUOUS,
    ISOLATED_ROUTE_ANCHOR_NOT_TIGHT,
    ISOLATED_ROUTE_ANCHOR_RESOLVED,
    NO_ISOLATED_ROUTE_ANCHOR,
    ROUTE_ISOLATION_REQUIRED,
    ROUTE_STILL_AMBIGUOUS,
    UNMEASURABLE,
    resolve_isolated_route_anchors,
    resolve_plan_view_route_anchors_for_path,
)


def _chain(pts):
    return {"lines": [(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1]) for i in range(len(pts) - 1)]}


def _box(x0, y0, x1, y1):
    return {"lines": [(x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0)]}


# --- the win: an offset label + grid box resolves to the unique route terminus, run re-verifies ---------- #
def test_offset_label_resolves_to_route_terminus():
    route = _chain([(10, 10), (50, 10), (90, 10)])       # ends at (10,10) and (90,10)
    grid = _box(30, 40, 60, 70)                          # a grid box off the route -> excluded, never an anchor
    obs = resolve_isolated_route_anchors([route, grid], (10, 25), (90, 25), anchor_radius=30)
    assert obs.status == ISOLATED_ROUTE_ANCHOR_RESOLVED and not obs.would_reject
    assert obs.start_anchor is not None and abs(obs.start_anchor[0] - 10) < 1 and abs(obs.start_anchor[1] - 10) < 1
    assert obs.end_anchor is not None and abs(obs.end_anchor[0] - 90) < 1
    assert obs.class_verified is False and obs.detail["reverify_status"] == "ROUTE_LINEWORK_ISOLATED"


# --- a grid/table line never becomes an anchor ---------------------------------------------------------- #
def test_grid_line_does_not_become_anchor():
    grid = _box(0, 15, 40, 45)                            # a box straddling the start label
    route = _chain([(200, 10), (260, 10)])               # a real route, but FAR from both labels
    obs = resolve_isolated_route_anchors([grid, route], (15, 25), (25, 25), anchor_radius=30)
    assert obs.would_reject and obs.status in (NO_ISOLATED_ROUTE_ANCHOR, ROUTE_ISOLATION_REQUIRED)
    assert obs.start_anchor is None and obs.end_anchor is None   # the box corner is NOT used as an anchor


# --- ambiguous: two candidate route termini near a label refuses --------------------------------------- #
def test_ambiguous_two_termini_near_label():
    r1 = _chain([(5, 10), (60, 10)])                     # end at (5,10)
    r2 = _chain([(18, 10), (60, 90)])                    # end at (18,10) -- 13 pt from r1's end (no weld)
    obs = resolve_isolated_route_anchors([r1, r2], (10, 25), (300, 25), anchor_radius=30)
    assert obs.status == ISOLATED_ROUTE_ANCHOR_AMBIGUOUS and obs.would_reject
    assert obs.detail["start_termini"] >= 2


# --- forked isolated route: termini resolve but the run between them still forks -> refuse -------------- #
def test_forked_route_between_anchors_refuses():
    segs = [_chain([(10, 10), (50, 10), (90, 10)]), _chain([(50, 10), (50, 45)])]   # a tee at the middle
    obs = resolve_isolated_route_anchors(segs, (10, 25), (90, 25), anchor_radius=30)
    assert obs.status == ROUTE_STILL_AMBIGUOUS and obs.would_reject
    assert obs.start_anchor is not None and obs.end_anchor is not None   # anchors resolved, but run is ambiguous


# --- endpoint too far: no route terminus within the search radius -> refuse ---------------------------- #
def test_terminus_too_far_refuses():
    route = _chain([(10, 10), (90, 10)])
    obs = resolve_isolated_route_anchors([route], (10, 90), (90, 90), anchor_radius=30)  # labels 80 pt below ends
    assert obs.status == NO_ISOLATED_ROUTE_ANCHOR and obs.would_reject
    assert obs.detail["start_termini"] == 0


# --- resolved termini but a broken run between them -> not tight ---------------------------------------- #
def test_resolved_but_broken_run_is_not_tight():
    segs = [_chain([(10, 10), (40, 10)]), _chain([(60, 10), (90, 10)])]   # two disjoint stubs, no bridge
    obs = resolve_isolated_route_anchors(segs, (10, 25), (90, 25), anchor_radius=30)
    assert obs.status == ISOLATED_ROUTE_ANCHOR_NOT_TIGHT and obs.would_reject
    assert obs.start_anchor is not None and obs.end_anchor is not None


# --- isolation produced nothing usable near the labels -> isolation required --------------------------- #
def test_no_isolated_route_is_isolation_required():
    obs = resolve_isolated_route_anchors([_box(0, 15, 40, 45)], (15, 25), (25, 25), anchor_radius=30)
    assert obs.status == ROUTE_ISOLATION_REQUIRED and obs.would_reject
    assert obs.detail["route_segment_count"] == 0


# --- unmeasurable when a label is not located ---------------------------------------------------------- #
def test_unmeasurable_when_label_missing():
    obs = resolve_isolated_route_anchors([_chain([(10, 10), (90, 10)])], None, (90, 25))
    assert obs.status == UNMEASURABLE and obs.would_reject and obs.class_verified is False
    assert obs.start_anchor is None


# --- end-to-end G-a -> G-b' -> G-b'' over a real PDF ---------------------------------------------------- #
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


def test_path_offset_label_resolves_to_terminus(tmp_path):
    # labels at ~ (60,100)/(300,100); the route ENDS near them but offset; plus a grid box (excluded).
    path = _make_plan(tmp_path, [("0+00", 60, 100), ("1+00", 300, 100)],
                      [(70, 112, 185, 112), (185, 112, 300, 112)], rects=[(60, 150, 120, 180)])
    ep, obs = resolve_plan_view_route_anchors_for_path(path, 1, 0.0, 100.0, start_source_bound=True,
                                                       end_source_bound=True, anchor_radius=45, reach_tol=40)
    assert ep.start.located and ep.end.located
    assert obs.status == ISOLATED_ROUTE_ANCHOR_RESOLVED and obs.class_verified is False
    assert obs.start_anchor is not None and obs.end_anchor is not None


def test_path_unlocated_endpoint_is_unmeasurable(tmp_path):
    path = _make_plan(tmp_path, [("0+00", 60, 100)], [(70, 112, 300, 112)])   # only the start label
    ep, obs = resolve_plan_view_route_anchors_for_path(path, 1, 0.0, 100.0, start_source_bound=True,
                                                       end_source_bound=True, anchor_radius=45, reach_tol=40)
    assert not (ep.start.located and ep.end.located) and obs.status == UNMEASURABLE
