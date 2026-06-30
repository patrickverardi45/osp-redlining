"""Proof for the read-only plan-view route-layer isolation gate (G-b').

It separates route-like linework from grid / table / border / label-box / leader / annotation linework between two
source-supported anchors, then reuses G-b's verifier on the isolated set to decide whether a unique connecting run
survives. Refusal-first: it never strips cycles, never snaps to the nearest line, never draws, and refuses on every
ambiguity (grid/border only, rivals, fork, endpoint-not-tight). Name-free synthetic geometry; class_verified always
False. Mirrors test_plan_view_run_observer.py (inline geometry for the core; a real fitz PDF for the path driver).
"""
from __future__ import annotations

import fitz

from truelinev2.extract.plan_view_run_observer import (
    ENDPOINT_NOT_TIGHT as RUN_ENDPOINT_NOT_TIGHT,
    FORKED_RUN as RUN_FORKED,
    MULTIPLE_PLAUSIBLE_RUNS as RUN_MULTIPLE,
)
from truelinev2.extract.plan_view_route_isolator import (
    CAT_BOX,
    GRID_OR_BORDER_ONLY,
    MULTIPLE_ROUTE_CANDIDATES,
    NO_ROUTE_LINEWORK,
    ROUTE_ENDPOINT_NOT_TIGHT,
    ROUTE_LAYER_AMBIGUOUS,
    ROUTE_LINEWORK_ISOLATED,
    UNMEASURABLE,
    observe_plan_view_route_for_path,
    observe_route_isolation,
)

START = (0.0, 0.0)
END = (100.0, 0.0)


def _chain_drawing(pts):
    """One drawing = an OPEN polyline (a route candidate)."""
    return {"lines": [(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1]) for i in range(len(pts) - 1)]}


def _box_drawing(x0, y0, x1, y1):
    """One drawing = a CLOSED rectangle (a grid / table cell / label frame)."""
    return {"lines": [(x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0)]}


def _word(x0, y0, x1, y1, text="x"):
    return {"text": text, "x0": x0, "y0": y0, "x1": x1, "y1": y1,
            "xc": (x0 + x1) / 2.0, "yc": (y0 + y1) / 2.0, "block": 0}


# --- core: a clean route is isolated even with nearby grid boxes ----------------------------------------- #
def test_clean_route_with_nearby_grid_is_isolated():
    route = _chain_drawing([(0, 0), (30, 1), (60, -1), (100, 0)])
    grid = [_box_drawing(10, 25, 30, 45), _box_drawing(50, 25, 70, 45)]   # boxes off the route corridor
    obs = observe_route_isolation([route] + grid, START, END)
    assert obs.status == ROUTE_LINEWORK_ISOLATED and not obs.would_reject
    assert obs.detail["route_drawings"] == 1 and obs.detail["box_drawings"] == 2
    assert obs.class_verified is False
    assert obs.start_gap is not None and obs.start_gap <= 12 and obs.end_gap <= 12


# --- core: isolation turns a box-polluted (would-refuse) sheet into a clean isolated route --------------- #
def test_isolation_resolves_full_sheet_ambiguity():
    route = _chain_drawing([(0, 0), (50, 0), (100, 0)])
    # a thin grid box spanning the same corridor (above the route, no weld): the FULL sheet sees a rival run.
    polluter = _box_drawing(-3, 8, 103, 20)
    obs = observe_route_isolation([route, polluter], START, END)
    assert obs.status == ROUTE_LINEWORK_ISOLATED and not obs.would_reject
    assert obs.detail["full_run"] == RUN_MULTIPLE      # un-isolated, G-b would refuse (rival run)
    assert obs.run_status != obs.detail["full_run"]    # the isolated run is clean


# --- core: a grid/table box alone is a refusal (no route) ----------------------------------------------- #
def test_grid_box_alone_is_grid_or_border_only():
    box = _box_drawing(-5, -5, 105, 5)                  # a box whose edges straddle both anchors
    obs = observe_route_isolation([box], START, END)
    assert obs.status == GRID_OR_BORDER_ONLY and obs.would_reject
    assert obs.detail["box_drawings"] == 1 and obs.detail["route_segment_count"] == 0
    assert obs.detail["excluded_near_anchor"] >= 1


# --- core: a page border / frame alone is a refusal ----------------------------------------------------- #
def test_page_frame_alone_is_no_route_linework():
    # anchors well inside the page; the only drawing is a page-spanning frame.
    s, e = (50.0, 50.0), (150.0, 50.0)
    frame = _box_drawing(0, 0, 200, 100)
    obs = observe_route_isolation([frame], s, e, page_bounds=(0.0, 0.0, 200.0, 100.0))
    assert obs.status == NO_ROUTE_LINEWORK and obs.would_reject
    assert obs.detail["frame_drawings"] == 1 and obs.detail["route_segment_count"] == 0


# --- core: rival parallel routes refuse ----------------------------------------------------------------- #
def test_multiple_route_candidates_refuse():
    r1 = _chain_drawing([(0, 0), (50, 0), (100, 0)])
    r2 = _chain_drawing([(0, 10), (50, 10), (100, 10)])   # parallel, both reach the anchors, no weld (10 > 7)
    obs = observe_route_isolation([r1, r2], START, END)
    assert obs.status == MULTIPLE_ROUTE_CANDIDATES and obs.would_reject
    assert obs.run_status == RUN_MULTIPLE


# --- core: a route that does not reach an anchor refuses ------------------------------------------------- #
def test_route_endpoint_not_tight_refuses():
    route = _chain_drawing([(0, 0), (50, 0), (80, 0)])    # ends 20 pt short of END
    obs = observe_route_isolation([route], START, END)
    assert obs.status == ROUTE_ENDPOINT_NOT_TIGHT and obs.would_reject
    assert obs.run_status == RUN_ENDPOINT_NOT_TIGHT


# --- core: a forked route (a tee in the route itself) refuses ------------------------------------------- #
def test_forked_route_is_route_layer_ambiguous():
    segs = [_chain_drawing([(0, 0), (50, 0), (100, 0)]), _chain_drawing([(50, 0), (50, 40)])]  # degree-3 junction
    obs = observe_route_isolation(segs, START, END)
    assert obs.status == ROUTE_LAYER_AMBIGUOUS and obs.would_reject
    assert obs.run_status == RUN_FORKED


# --- core: a word-attached leader is dropped, not mistaken for the route --------------------------------- #
def test_leader_to_label_is_not_mistaken_for_route():
    route = _chain_drawing([(0, 0), (10, 0), (50, 0), (100, 0)])     # node at (10,0) so a leader could weld there
    label_box = _box_drawing(0, 18, 22, 32)                          # a closed label frame -> excluded as a box
    leader = _chain_drawing([(10, 0), (10, 22)])                     # short leader from the route up to the label
    words = [_word(2, 19, 20, 31, "lbl")]                            # a printed word inside the label frame
    obs = observe_route_isolation([route, label_box, leader], START, END, words=words)
    assert obs.status == ROUTE_LINEWORK_ISOLATED and not obs.would_reject
    assert obs.detail["leader_or_tick_dropped"] >= 1


def test_without_words_a_welded_leader_safely_refuses():
    # the SAME geometry without the word context: the leader welds to the route node -> a fork -> safe refusal
    # (never silently mistaken for the route, never stripped to force success).
    route = _chain_drawing([(0, 0), (10, 0), (50, 0), (100, 0)])
    leader = _chain_drawing([(10, 0), (10, 22)])
    obs = observe_route_isolation([route, leader], START, END)
    assert obs.status == ROUTE_LAYER_AMBIGUOUS and obs.would_reject
    assert obs.class_verified is False


# --- core: a CONNECTED run that is not a clean anchor-to-anchor path refuses (no stub / no tail) --------- #
def test_dangling_stub_off_anchor_is_not_isolated():
    # one clean spanning edge PLUS a 40-pt stub hanging off the start anchor node: G-b alone calls this CONNECTED
    # (the anchor stays degree-2); G-b' must refuse because the route is not a clean anchor-to-anchor path.
    segs = [_chain_drawing([(0, 0), (100, 0)]), _chain_drawing([(0, 0), (0, 40)])]
    obs = observe_route_isolation(segs, START, END)
    assert obs.status == ROUTE_LAYER_AMBIGUOUS and obs.would_reject
    assert obs.run_status == "PLAN_VIEW_RUN_CONNECTED" and obs.detail["simple_path"] is False


def test_tail_past_anchor_is_not_isolated():
    # the run reaches both anchors but extends 20 pt PAST the end anchor (the end anchor is an interior node):
    # G-b calls it CONNECTED; G-b' refuses (not tight to a chain end).
    segs = [_chain_drawing([(0, 0), (100, 0), (120, 0)])]
    obs = observe_route_isolation(segs, START, END)
    assert obs.status == ROUTE_LAYER_AMBIGUOUS and obs.would_reject
    assert obs.detail["simple_path"] is False


def test_isolated_status_sets_simple_path_true():
    obs = observe_route_isolation([_chain_drawing([(0, 0), (50, 0), (100, 0)])], START, END)
    assert obs.status == ROUTE_LINEWORK_ISOLATED and obs.detail["simple_path"] is True


# --- core: unmeasurable when an anchor is missing ------------------------------------------------------- #
def test_unmeasurable_when_anchor_missing():
    obs = observe_route_isolation([_chain_drawing([(0, 0), (100, 0)])], None, END)
    assert obs.status == UNMEASURABLE and obs.would_reject and obs.class_verified is False
    assert obs.route_segments == ()


# --- core: a box is classified as a box, never collected as route -------------------------------------- #
def test_box_drawing_is_classified_box():
    from truelinev2.extract.plan_view_route_isolator import _classify_drawing, _drawing_lines
    box = _box_drawing(0, 0, 20, 20)
    lines = _drawing_lines(box)
    assert _classify_drawing(lines, (0, 0, 20, 20), None, 7.0) == CAT_BOX
    seg = _chain_drawing([(0, 0), (40, 0), (80, 0)])
    assert _classify_drawing(_drawing_lines(seg), (0, 0, 80, 0), None, 7.0) != CAT_BOX


# --- end-to-end G-a -> G-b' over a real PDF (locate labels, then isolate + verify the drawn run) -------- #
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


def test_path_clean_route_with_grid_box_isolates(tmp_path):
    path = _make_plan(tmp_path, [("0+00", 60, 100), ("1+00", 300, 100)],
                      [(60, 100, 180, 100), (180, 100, 300, 100)],
                      rects=[(60, 150, 120, 180)])           # a grid box well below the route
    ep, obs = observe_plan_view_route_for_path(path, 1, 0.0, 100.0,
                                               start_source_bound=True, end_source_bound=True, reach_tol=40)
    assert ep.start.located and ep.end.located
    assert obs.status == ROUTE_LINEWORK_ISOLATED and not obs.would_reject and obs.class_verified is False
    assert obs.detail["box_drawings"] >= 1


def test_path_grid_only_refuses(tmp_path):
    path = _make_plan(tmp_path, [("0+00", 60, 100), ("1+00", 300, 100)], [],
                      rects=[(50, 90, 90, 130), (290, 90, 330, 130)])   # boxes around the labels, no route
    ep, obs = observe_plan_view_route_for_path(path, 1, 0.0, 100.0,
                                               start_source_bound=True, end_source_bound=True, reach_tol=40)
    assert ep.start.located and ep.end.located
    assert obs.would_reject and obs.status in (GRID_OR_BORDER_ONLY, NO_ROUTE_LINEWORK)
    assert obs.detail["box_drawings"] >= 1 and obs.detail["route_segment_count"] == 0


def test_path_unlocated_endpoint_is_unmeasurable(tmp_path):
    path = _make_plan(tmp_path, [("0+00", 60, 100)], [(60, 100, 300, 100)])   # only the start label printed
    ep, obs = observe_plan_view_route_for_path(path, 1, 0.0, 100.0,
                                               start_source_bound=True, end_source_bound=True, reach_tol=40)
    assert not (ep.start.located and ep.end.located) and obs.status == UNMEASURABLE
