"""M8.19 -- tests pinning the path-length implied-scale helper (synthetic).

Locks: the implied scale is the DRAWN route length / footage (not the chord),
so a curved route yields a LARGER scale than its straight-line distance would;
an untraceable route abstains (None, None); zero footage abstains. Pure."""
from __future__ import annotations

import math

from truelinev2.extract.design_path import Piece, path_length
from truelinev2.proof.run_path_length_join_probe import design_path_implied_scale


def _piece(pts, layer="BORE - VACANT PIPE"):
    return Piece(points=tuple(pts), layer=layer)


def test_scale_uses_drawn_length_not_chord():
    # an L-shaped drawn route: anchor (0,0) -> (100,0) -> (100,100), boundary
    # at (100,100). Chord = 141.4; drawn length = 200. footage 100 ft.
    anchor, boundary = (0.0, 0.0), (100.0, 100.0)
    pieces = [_piece([(0.0, 0.0), (100.0, 0.0), (100.0, 100.0)])]
    scale, plen = design_path_implied_scale(pieces, anchor, boundary, 100.0)
    assert plen is not None
    chord = math.hypot(*boundary)
    assert plen > chord                    # path is longer than the chord
    assert abs(plen - 200.0) < 1e-6        # the true drawn length
    assert abs(scale - 2.0) < 1e-6         # 200 pt / 100 ft


def test_untraceable_route_abstains():
    # no drawn piece connects the anchor to the boundary
    pieces = [_piece([(500.0, 500.0), (600.0, 500.0)])]
    scale, plen = design_path_implied_scale(pieces, (0.0, 0.0), (100.0, 0.0), 100.0)
    assert scale is None and plen is None


def test_zero_footage_abstains():
    pieces = [_piece([(0.0, 0.0), (100.0, 0.0)])]
    assert design_path_implied_scale(pieces, (0.0, 0.0), (100.0, 0.0), 0.0) == (None, None)


def test_straight_route_scale_equals_chord_scale():
    # a straight drawn route: path == chord, so path-length scale == chord scale
    pieces = [_piece([(0.0, 0.0), (144.0, 0.0)])]
    scale, plen = design_path_implied_scale(pieces, (0.0, 0.0), (144.0, 0.0), 100.0)
    assert abs(plen - 144.0) < 1e-6 and abs(scale - 1.44) < 1e-6
