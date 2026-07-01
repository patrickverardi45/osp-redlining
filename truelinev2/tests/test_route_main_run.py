"""Proof for the read-only route-vs-lateral discriminator (gate G-b''').

It separates the MAIN run from short laterals/service drops in isolated route linework between two printed-label
endpoints, and refuses on rival runs, a long branch, a disconnected run, an interior-label run, or a cyclic/meshy
component. Topology + relative length only -- never an absolute distance guess, never a snap, never a grid line.
Name-free synthetic geometry; class_verified always False. Inline geometry for the core; a real fitz PDF for the
path driver.
"""
from __future__ import annotations

import fitz

from truelinev2.extract.route_main_run import (
    MAIN_ROUTE_DISCRIMINATED,
    MAIN_ROUTE_ENDPOINT_NOT_TIGHT,
    MULTIPLE_MAIN_ROUTE_CANDIDATES,
    NO_MAIN_ROUTE,
    ROUTE_LATERAL_AMBIGUOUS,
    ROUTE_TOPOLOGY_UNSAFE,
    UNMEASURABLE,
    discriminate_main_run,
    discriminate_plan_view_main_run_for_path,
)

A = (10.0, 25.0)      # label near the (10,10) route end
B = (90.0, 25.0)      # label near the (90,10) route end


def _chain(pts):
    return {"lines": [(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1]) for i in range(len(pts) - 1)]}


def _segs(*drawings):
    out = []
    for d in drawings:
        for (ax, ay, bx, by) in d["lines"]:
            out.append({"a": (ax, ay), "b": (bx, by)})
    return out


# --- a clean main route with a short lateral is discriminated ------------------------------------------- #
def test_clean_main_route_with_short_lateral():
    segs = _segs(_chain([(10, 10), (50, 10), (90, 10)]),   # backbone, length 80
                 _chain([(50, 10), (50, 25)]))              # a 15-pt lateral off the middle (< 0.5 * 80)
    obs = discriminate_main_run(segs, A, B, anchor_radius=30)
    assert obs.status == MAIN_ROUTE_DISCRIMINATED and not obs.would_reject
    assert obs.start_anchor is not None and abs(obs.start_anchor[0] - 10) < 1
    assert obs.end_anchor is not None and abs(obs.end_anchor[0] - 90) < 1
    assert obs.class_verified is False and len(obs.main_run_segments) >= 2
    assert obs.detail["max_lateral_reach"] < obs.detail["main_run_length"]


# --- two separate runs each reaching both labels refuse ------------------------------------------------- #
def test_two_rival_runs_refuse():
    segs = _segs(_chain([(10, 10), (90, 10)]), _chain([(10, 40), (90, 40)]))
    obs = discriminate_main_run(segs, A, B, anchor_radius=30)
    assert obs.status == MULTIPLE_MAIN_ROUTE_CANDIDATES and obs.would_reject
    assert obs.detail["spanning_components"] >= 2


# --- a long off-backbone branch is not clearly a lateral -> refuse ------------------------------------- #
def test_long_branch_is_lateral_ambiguous():
    segs = _segs(_chain([(10, 10), (50, 10), (90, 10)]),   # backbone, length 80
                 _chain([(50, 10), (50, 80)]))             # a 70-pt branch (>= 0.5 * 80) -> ambiguous
    obs = discriminate_main_run(segs, A, B, anchor_radius=30)
    assert obs.status == ROUTE_LATERAL_AMBIGUOUS and obs.would_reject
    assert obs.detail["max_lateral_reach"] >= 0.5 * obs.detail["main_run_length"]


# --- a disconnected route (no run reaches both labels) refuses ----------------------------------------- #
def test_disconnected_route_no_main_route():
    segs = _segs(_chain([(10, 10), (40, 10)]), _chain([(60, 10), (90, 10)]))
    obs = discriminate_main_run(segs, A, B, anchor_radius=30)
    assert obs.status == NO_MAIN_ROUTE and obs.would_reject


# --- the station labels sit beside mid-run points (no terminus at a label) -> not tight ----------------- #
def test_interior_label_endpoint_not_tight():
    segs = _segs(_chain([(10, 10), (50, 10), (90, 10), (130, 10), (150, 10)]))
    # labels beside interior nodes (50,10)/(90,10); the run's termini (10,10)/(150,10) are far from them
    obs = discriminate_main_run(segs, (50, 25), (90, 25), anchor_radius=20)
    assert obs.status == MAIN_ROUTE_ENDPOINT_NOT_TIGHT and obs.would_reject


# --- a cyclic / meshy spanning component is unsafe -> refuse ------------------------------------------- #
def test_cyclic_component_topology_unsafe():
    segs = _segs(_chain([(10, 10), (50, 5), (90, 10)]),    # one arc between the ends
                 _chain([(10, 10), (50, 15), (90, 10)]))   # a second arc -> a loop between the same ends
    obs = discriminate_main_run(segs, A, B, anchor_radius=30)
    assert obs.status == ROUTE_TOPOLOGY_UNSAFE and obs.would_reject
    assert obs.detail["component_edges"] >= obs.detail["component_nodes"]


# --- unmeasurable when a label is not located ---------------------------------------------------------- #
def test_unmeasurable_when_label_missing():
    obs = discriminate_main_run(_segs(_chain([(10, 10), (90, 10)])), None, B)
    assert obs.status == UNMEASURABLE and obs.would_reject and obs.class_verified is False
    assert obs.main_run_segments == ()


# --- end-to-end G-a -> G-b' -> G-b''' over a real PDF: grid excluded, main run discriminated ------------ #
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


def test_path_grid_excluded_main_route_discriminated(tmp_path):
    # a clean route with a short lateral, plus a grid box (excluded by G-b'); labels near the route ends.
    path = _make_plan(tmp_path, [("0+00", 60, 100), ("1+00", 300, 100)],
                      [(70, 112, 185, 112), (185, 112, 300, 112), (185, 112, 185, 130)],
                      rects=[(60, 150, 120, 180)])
    ep, obs = discriminate_plan_view_main_run_for_path(path, 1, 0.0, 100.0, start_source_bound=True,
                                                       end_source_bound=True, anchor_radius=45)
    assert ep.start.located and ep.end.located
    assert obs.status == MAIN_ROUTE_DISCRIMINATED and obs.class_verified is False
    assert obs.start_anchor is not None and obs.end_anchor is not None


def test_path_unlocated_endpoint_is_unmeasurable(tmp_path):
    path = _make_plan(tmp_path, [("0+00", 60, 100)], [(70, 112, 300, 112)])
    ep, obs = discriminate_plan_view_main_run_for_path(path, 1, 0.0, 100.0, start_source_bound=True,
                                                       end_source_bound=True, anchor_radius=45)
    assert not (ep.start.located and ep.end.located) and obs.status == UNMEASURABLE
