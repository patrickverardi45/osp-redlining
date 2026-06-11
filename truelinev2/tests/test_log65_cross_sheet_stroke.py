"""M8.14.b.10 -- tests pinning the cross-sheet joined stroke contract.

Locks: boundary anchors derive ONLY from the terminal dash extended along its
own drawn direction to the matchline centerline, capped at the dash-gap
constant (beyond-gap, parallel-dash, and oblique-overrun cases REFUSE);
orientation generality (vertical AND horizontal matchlines); the join verdict
requires the SAME printed boundary station + exact footage closure; the
stroke color pin IS the canonical red object."""
from __future__ import annotations

from truelinev2.proof.run_log65_cross_sheet_stroke_proof import (
    STROKE_RGB,
    extend_dash_to_boundary,
    joined_segments_verdict,
)
from truelinev2.render.crop import REDLINE_STROKE_RGB


def _seg(lines):
    xs = [v for ln in lines for v in (ln[0], ln[2])]
    ys = [v for ln in lines for v in (ln[1], ln[3])]
    return {"layer": "L", "x0": min(xs), "y0": min(ys), "x1": max(xs),
            "y1": max(ys), "xc": sum(xs) / len(xs), "yc": sum(ys) / len(ys),
            "lines": list(lines)}


VERT_ML = (61.0, 234.0, 62.0, 537.0)     # vertical matchline (centerline 61.5)
HORZ_ML = (234.0, 61.0, 537.0, 62.0)     # horizontal matchline (centerline 61.5)


def test_extension_follows_dash_direction_to_vertical_matchline():
    chain = [_seg([(99.4, 356.8, 64.8, 356.8)])]  # horizontal dash, gap 3.3
    p = extend_dash_to_boundary(chain, VERT_ML)
    assert p == (61.5, 356.8)


def test_extension_to_horizontal_matchline_is_symmetric():
    chain = [_seg([(356.8, 99.4, 356.8, 64.8)])]  # vertical dash heading down
    p = extend_dash_to_boundary(chain, HORZ_ML)
    assert p == (356.8, 61.5)


def test_extension_refuses_beyond_dash_gap():
    far = [_seg([(200.0, 356.8, 150.0, 356.8)])]  # nearest endpoint 88.5 pt out
    assert extend_dash_to_boundary(far, VERT_ML) is None


def test_extension_refuses_dash_parallel_to_matchline():
    parallel = [_seg([(64.8, 300.0, 64.8, 340.0)])]  # vertical dash, 3.3 pt away
    assert extend_dash_to_boundary(parallel, VERT_ML) is None


def test_outline_rectangle_dash_resolves_via_long_axis():
    """Real dashes are filled OUTLINE rectangles: the terminal endpoint also
    belongs to a short cap and a diagonal. The cap is parallel (skipped) and
    the diagonal overruns; the long axis must win."""
    cap = (64.8, 356.1, 64.8, 357.4)
    long_axis = (99.4, 356.8, 64.8, 356.8)
    diagonal = (99.4, 356.1, 64.8, 357.4)
    p = extend_dash_to_boundary([_seg([cap, long_axis, diagonal])], VERT_ML)
    assert p is not None
    assert abs(p[0] - 61.5) < 1e-9 and abs(p[1] - 356.8) < 0.2


def test_extension_refuses_oblique_overrun():
    # endpoint 30 pt from the line, but the dash is so steep that following
    # its own direction to the centerline travels farther than a dash gap
    steep = [_seg([(92.0, 300.0, 91.0, 200.0)])]
    assert extend_dash_to_boundary(steep, VERT_ML) is None


def test_join_verdict_requires_shared_station_and_closure():
    ok = joined_segments_verdict(boundary_a_ft=611.0, boundary_b_ft=611.0,
                                 seg_a_ft=160.0, seg_b_ft=39.0, span_ft=199.0)
    assert ok["joined"] and ok["shared_boundary_ft"] == 611.0
    bad_b = joined_segments_verdict(boundary_a_ft=611.0, boundary_b_ft=612.0,
                                    seg_a_ft=160.0, seg_b_ft=39.0, span_ft=199.0)
    assert not bad_b["joined"] and bad_b["shared_boundary_ft"] is None
    bad_f = joined_segments_verdict(boundary_a_ft=611.0, boundary_b_ft=611.0,
                                    seg_a_ft=160.0, seg_b_ft=50.0, span_ft=199.0)
    assert not bad_f["joined"] and not bad_f["footage_closure"]


def test_stroke_color_is_the_canonical_red_object():
    assert STROKE_RGB is REDLINE_STROKE_RGB
