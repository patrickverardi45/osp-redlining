"""Marker-density law (Patrick, 2026-06-11) -- station marker rings on tight
curves overlap into a blob; thinning is RENDER-ONLY.

Locks: the stroke GEOMETRY is never altered (thinning returns a subset of
vertex indices; the polyline always draws every vertex -- source-pinned);
endpoints and mandatory anchors (structures/equations/potholes/review) always
keep their rings even when crowded; dense curve interiors are decimated to
the rendered-pixel spacing floor; sparse strokes keep every ring; the debug
mode shows all; inputs are never mutated; payload evidence is untouched by
construction (the renderer consumes, never writes)."""
from __future__ import annotations

import inspect
import math

from truelinev2.render import crop
from truelinev2.render.crop import (
    MIN_MARKER_SPACING_PX,
    thin_markers,
)


def _dense_arc(n=30, r=60.0):
    """A tight rendered-pixel curve: consecutive vertices ~6 px apart --
    far below the spacing floor (the log25 U-bow at zoom 2)."""
    return [(200 + r * math.cos(i * math.pi / n), 200 + r * math.sin(i * math.pi / n))
            for i in range(n + 1)]


def test_dense_curve_markers_are_decimated_to_the_spacing_floor():
    pts = _dense_arc()
    keep = thin_markers(pts)
    assert len(keep) < len(pts) / 2  # visibly decimated
    drawn = [pts[i] for i in keep]
    for i, p in enumerate(drawn):
        for q in drawn[i + 1:]:
            d = math.hypot(p[0] - q[0], p[1] - q[1])
            # interior rings respect the floor (endpoint pair may be closer
            # only if the arc's two ends are -- not the case here)
            assert d >= MIN_MARKER_SPACING_PX * 0.99 or d == 0.0


def test_endpoints_and_mandatory_always_survive_crowding():
    pts = _dense_arc()
    mand = [7, 8, 9]  # three adjacent crowded structure vertices
    keep = thin_markers(pts, mandatory_idx=mand)
    assert 0 in keep and len(pts) - 1 in keep
    assert set(mand) <= set(keep)  # mandatory rings never thinned away


def test_sparse_stroke_keeps_every_ring():
    pts = [(0.0, 0.0), (100.0, 0.0), (200.0, 0.0), (300.0, 0.0)]
    assert thin_markers(pts) == [0, 1, 2, 3]


def test_debug_mode_shows_all():
    pts = _dense_arc()
    assert thin_markers(pts, show_all=True) == list(range(len(pts)))


def test_thinning_is_pure_and_subset_only():
    pts = _dense_arc()
    snapshot = list(pts)
    keep = thin_markers(pts)
    assert pts == snapshot                       # input never mutated
    assert keep == sorted(set(keep))             # ordered, no duplicates
    assert all(0 <= i < len(pts) for i in keep)  # subset of input indices


def test_folded_curve_checks_all_drawn_not_just_last():
    # a hairpin in PIXEL space: the return leg passes near the out leg --
    # last-only spacing would re-crowd; all-drawn spacing must not
    out_leg = [(x, 0.0) for x in range(0, 200, 6)]
    back_leg = [(x, 10.0) for x in range(194, -1, -6)]
    pts = out_leg + [(200.0, 5.0)] + back_leg
    keep = thin_markers(pts)
    drawn = [pts[i] for i in keep if i not in (0, len(pts) - 1)]
    for i, p in enumerate(drawn):
        for q in drawn[i + 1:]:
            assert math.hypot(p[0] - q[0], p[1] - q[1]) >= MIN_MARKER_SPACING_PX * 0.99


def test_stroke_polyline_always_draws_every_vertex():
    """Geometry is never thinned: the renderer's polyline loop iterates the
    FULL vertex list; only the marker loop consumes thin_markers."""
    src = inspect.getsource(crop.render_redline_stroke)
    assert "for a, b in zip(ppts, ppts[1:])" in src   # full-geometry polyline
    assert "thin_markers(" in src                      # markers thinned
    assert "the FULL geometry, every vertex, always" in src