"""Proof for the read-only plan-view drawn-run verifier (gate G-b).

It verifies whether a single clean drawn run connects two located endpoint anchors, and refuses on every
ambiguity (no run / broken / fork / rival / endpoint-not-tight). Name-free synthetic geometry; strict refusal;
no axis; never draws/places/promotes; class_verified always False.
"""
from __future__ import annotations

import fitz

from truelinev2.extract.plan_view_run_observer import (
    BROKEN_RUN,
    ENDPOINT_NOT_TIGHT,
    FORKED_RUN,
    MULTIPLE_PLAUSIBLE_RUNS,
    NO_DRAWN_RUN,
    PLAN_VIEW_RUN_CONNECTED,
    UNMEASURABLE,
    observe_plan_view_run_for_path,
    observe_run_between_anchors,
)

START = (0.0, 0.0)
END = (100.0, 0.0)


def _chain(pts):
    return [{"a": pts[i], "b": pts[i + 1]} for i in range(len(pts) - 1)]


# --- core verifier: the adversarial matrix (direct segment geometry) --------------------------------------- #
def test_clean_single_run_is_connected():
    r = observe_run_between_anchors(_chain([(0, 0), (30, 1), (60, -1), (100, 0)]), START, END)
    assert r.status == PLAN_VIEW_RUN_CONNECTED and not r.would_reject
    assert r.start_gap <= 12 and r.end_gap <= 12 and r.class_verified is False


def test_no_segments_is_no_drawn_run():
    r = observe_run_between_anchors([], START, END)
    assert r.status == NO_DRAWN_RUN and r.would_reject


def test_far_segments_are_prefiltered_to_no_drawn_run():
    r = observe_run_between_anchors(_chain([(0, 500), (100, 500)]), START, END)   # far from the anchors
    assert r.status == NO_DRAWN_RUN


def test_broken_run_is_refused():
    segs = _chain([(0, 0), (40, 0)]) + _chain([(60, 0), (100, 0)])               # 20-pt gap between two runs
    r = observe_run_between_anchors(segs, START, END)
    assert r.status == BROKEN_RUN and r.would_reject


def test_forked_run_is_refused():
    segs = _chain([(0, 0), (50, 0), (100, 0)]) + _chain([(50, 0), (50, 40)])     # a tee -> degree-3 junction
    r = observe_run_between_anchors(segs, START, END)
    assert r.status == FORKED_RUN and r.would_reject


def test_rival_parallel_runs_are_multiple_plausible():
    segs = _chain([(0, 0), (50, 0), (100, 0)]) + _chain([(0, 10), (50, 10), (100, 10)])
    r = observe_run_between_anchors(segs, START, END)
    assert r.status == MULTIPLE_PLAUSIBLE_RUNS and r.would_reject


def test_endpoint_too_far_is_not_tight():
    r = observe_run_between_anchors(_chain([(0, 0), (50, 0), (80, 0)]), START, END)   # ends 20 pt short of END
    assert r.status == ENDPOINT_NOT_TIGHT and r.would_reject


def test_unmeasurable_when_an_anchor_is_missing():
    r = observe_run_between_anchors(_chain([(0, 0), (100, 0)]), None, END)
    assert r.status == UNMEASURABLE and r.would_reject and r.class_verified is False


# --- end-to-end G-a -> G-b over a real PDF (locate labels, then verify the drawn run) --------------------- #
def _make_plan(tmp_path, labels, lines, name="plan.pdf"):
    doc = fitz.open()
    page = doc.new_page(width=400, height=200)
    for text, x, y in labels:
        page.insert_text((x, y), text, fontsize=8)
    for (x0, y0, x1, y1) in lines:
        page.draw_line((x0, y0), (x1, y1), color=(1, 0, 0), width=1)
    p = tmp_path / name
    doc.save(str(p))
    doc.close()
    return str(p)


def test_path_clean_route_connects(tmp_path):
    path = _make_plan(tmp_path, [("0+00", 60, 100), ("1+00", 300, 100)],
                      [(60, 100, 180, 100), (180, 100, 300, 100)])
    ep, run = observe_plan_view_run_for_path(path, 1, 0.0, 100.0,
                                             start_source_bound=True, end_source_bound=True, reach_tol=40)
    assert ep.start.located and ep.end.located
    assert run.status == PLAN_VIEW_RUN_CONNECTED and not run.would_reject and run.class_verified is False


def test_path_no_route_is_no_drawn_run(tmp_path):
    path = _make_plan(tmp_path, [("0+00", 60, 100), ("1+00", 300, 100)], [])
    ep, run = observe_plan_view_run_for_path(path, 1, 0.0, 100.0,
                                             start_source_bound=True, end_source_bound=True, reach_tol=40)
    assert ep.start.located and ep.end.located and run.status == NO_DRAWN_RUN


def test_path_unlocated_endpoint_is_unmeasurable(tmp_path):
    path = _make_plan(tmp_path, [("0+00", 60, 100)], [(60, 100, 300, 100)])   # only the start label printed
    ep, run = observe_plan_view_run_for_path(path, 1, 0.0, 100.0,
                                             start_source_bound=True, end_source_bound=True, reach_tol=40)
    assert not (ep.start.located and ep.end.located) and run.status == UNMEASURABLE
