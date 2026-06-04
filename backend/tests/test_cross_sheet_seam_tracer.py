"""Focused unit tests for the cross-sheet seam PATH tracer (log56 sheet-17 authored-path
reconstruction). PDF-FREE / synthetic — no fitz. Validates the anti-guess contract: a unique
authored route resolves as an ordered start->seam polyline; an ambiguous (multi-route)
component abstains; an unreachable seam abstains. The tracer must FOLLOW authored vectors,
never connect anchors with a straight line.

COMMAND (from repo root):
    python -m pytest backend/tests/test_cross_sheet_seam_tracer.py -v
"""
from __future__ import annotations

from app.core.redline_consult import cross_sheet_seam_tracer as cst


def _seg(p0, p1, layer="BORE - PATH"):
    return {"p0": [float(p0[0]), float(p0[1])], "p1": [float(p1[0]), float(p1[1])], "layer": layer}


def _vseam(x, y0=0.0, y1=500.0):
    # thin, long, axis-aligned vertical MATCHLINE seam edge at x (passes seam_edges()).
    return {"layer": "MATCHLINE", "length": float(y1 - y0),
            "bbox_display": [float(x), float(y0), float(x) + 0.5, float(y1)]}


def test_unique_authored_path_resolves_ordered():
    # straight authored chain of three bore strokes from the HH (10,250) to the seam (x=100)
    segs = [_seg((10, 250), (40, 250)), _seg((40, 250), (70, 250)), _seg((70, 250), (100, 250))]
    out = cst.trace_seam_path(segs, [_vseam(100)], (10, 250))
    assert out["resolved"] is True, out
    assert out["reason"] == "authored_path_traced"
    # ordered polyline start -> seam (NOT a 2-point straight connector)
    xs = [p[0] for p in out["path_xy"]]
    assert xs == sorted(xs) and len(out["path_xy"]) >= 3
    assert out["path_xy"][0][0] == 10                       # starts at the HH node
    assert abs(out["seam_anchor"][0] - 100) < 1.0           # ends on the seam edge
    assert out["path_xy"][-1] == out["seam_anchor"]


def test_ambiguous_multi_route_abstains():
    # diamond: two equal-length authored routes reach the mid node -> ambiguous -> abstain
    segs = [_seg((10, 250), (40, 230)), _seg((10, 250), (40, 270)),
            _seg((40, 230), (70, 250)), _seg((40, 270), (70, 250)),
            _seg((70, 250), (100, 250))]
    out = cst.trace_seam_path(segs, [_vseam(100)], (10, 250))
    assert out["resolved"] is False
    assert out["reason"] == "ambiguous_path_multiple_routes"
    assert out["path_xy"] is None                           # never guesses a route


def test_unreachable_seam_abstains():
    # the run never reaches the (far) seam edge -> abstain, no draw
    segs = [_seg((10, 250), (40, 250)), _seg((40, 250), (70, 250))]
    out = cst.trace_seam_path(segs, [_vseam(200)], (10, 250))
    assert out["resolved"] is False
    assert out["reason"] == "seam_unreachable_from_hh_component"
    assert out["path_xy"] is None


def test_no_start_node_abstains():
    # HH anchor nowhere near any authored bore node -> abstain (no nearest-node guess)
    segs = [_seg((10, 250), (40, 250)), _seg((40, 250), (70, 250))]
    out = cst.trace_seam_path(segs, [_vseam(100)], (9000, 9000))
    assert out["resolved"] is False
    assert out["reason"] == "no_bore_run_node_within_start_tol"
    assert out["path_xy"] is None
