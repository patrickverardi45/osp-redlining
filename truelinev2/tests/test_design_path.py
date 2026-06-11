"""M8.14.c.2 -- tests pinning the design-path adherence laws (synthetic).

Locks Patrick's graded-FAIL correction: a stroke FOLLOWS the drawn conduit
line and never chords across a curve; pieces come from sub-path long axes
with outline-twin merge and degree-2 welding (junctions never welded across);
the walk explores junction branches, prunes dead ends, collapses hairpin
spurs, treats jitter-scale variants as ONE answer, and refuses physically
distinct alternatives; a tick-chord is permitted only with a positive
straightness certificate."""
from __future__ import annotations

import math

from truelinev2.extract.design_path import (
    AMBIGUOUS,
    NOT_CONNECTED,
    TRACED,
    Piece,
    chord_straightness_certificate,
    collapse_hairpins,
    conduit_pieces,
    path_length,
    point_to_polyline,
    split_subpaths,
    ticks_adhere,
    walk_design_path,
)


def _seg_piece(a, b, layer="C"):
    return Piece(points=(a, b), layer=layer)


def _dash_drawing(a, b, layer="C"):
    """A filled dash as TWO offset triangles (the real outline structure)."""
    off = 1.4
    t1 = [(a[0], a[1], b[0], b[1]), (b[0], b[1], b[0], b[1] + off),
          (b[0], b[1] + off, a[0], a[1])]
    t2 = [(a[0], a[1] + off, b[0], b[1] + off), (b[0], b[1] + off, a[0], a[1] + off + 0.1),
          (a[0], a[1] + off + 0.1, a[0], a[1] + off)]
    return {"layer": layer, "lines": t1 + t2}


# --- piece extraction -------------------------------------------------------------------

def test_split_subpaths_breaks_on_discontinuity():
    lines = [(0, 0, 10, 0), (10, 0, 10, 5), (50, 50, 60, 50)]
    subs = split_subpaths(lines)
    assert [len(s) for s in subs] == [2, 1]


def test_outline_twins_merge_to_one_piece():
    pieces = conduit_pieces([_dash_drawing((0.0, 0.0), (34.0, 0.0))], ["C"])
    assert len(pieces) == 1
    assert abs(pieces[0].length - 34.0) < 1.5


def test_degree_two_weld_compresses_marks_but_never_junctions():
    # three touching marks weld into one polyline...
    chain = [_seg_piece((0.0, 0.0), (10.0, 0.0)),
             _seg_piece((10.5, 0.0), (20.0, 0.0)),
             _seg_piece((20.5, 0.0), (30.0, 0.0))]
    welded = conduit_pieces([], ["C"])  # empty ok
    from truelinev2.extract.design_path import _weld
    out = _weld(chain, 4.0)
    assert len(out) == 1 and len(out[0].points) == 6
    # ...but a 3-way junction contact is NEVER welded across
    junction = chain[:2] + [_seg_piece((10.5, 0.5), (10.5, 30.0))]
    out2 = _weld(junction, 4.0)
    assert len(out2) == 3


# --- the chord-prevention law -----------------------------------------------------------

def _arc_marks(r=200.0, cx=0.0, cy=0.0, n=24):
    """Quarter-circle drawn as touching marks (a curved conduit). Welded
    before walking -- exactly the conduit_pieces pipeline."""
    from truelinev2.extract.design_path import _weld
    pts = [(cx + r * math.cos(t), cy + r * math.sin(t))
           for t in [i * (math.pi / 2) / n for i in range(n + 1)]]
    return _weld([_seg_piece(p, q) for p, q in zip(pts, pts[1:])], 4.0)


def test_stroke_follows_the_curve_never_the_chord():
    marks = _arc_marks()
    assert len(marks) == 1  # touching curve marks weld into ONE drawn polyline
    start, end = (200.0, 0.0), (0.0, 200.0)
    w = walk_design_path(marks, start, end)
    assert w["result"] == TRACED
    pts = w["stroke_points"]
    arc_len = math.pi / 2 * 200.0          # ~314
    chord_len = math.hypot(200.0, 200.0)   # ~283
    assert abs(path_length(pts) - arc_len) < 8.0  # follows the ARC
    # the chord's midpoint is ~58 pt off the arc; the stroke stays ON it
    chord_mid = (100.0, 100.0)
    assert point_to_polyline(chord_mid, pts) > 50.0
    assert all(abs(math.hypot(x, y) - 200.0) < 2.0 for x, y in pts[1:-1])


def test_dead_end_branch_is_pruned_not_chosen():
    # realistic dash pitch: 34-pt dashes, 32-pt gaps (skips are unreachable)
    main = [_seg_piece((0.0, 0.0), (34.0, 0.0)),
            _seg_piece((66.0, 0.0), (100.0, 0.0)),
            _seg_piece((132.0, 0.0), (166.0, 0.0))]
    dead_leg = [_seg_piece((67.0, 1.0), (67.0, 35.0)),
                _seg_piece((67.0, 67.0), (67.0, 100.0))]
    w = walk_design_path(main + dead_leg, (0.0, 0.0), (166.0, 0.0))
    assert w["result"] == TRACED
    assert all(y < 5.0 for _x, y in w["stroke_points"])  # never up the dead leg


def test_physically_distinct_parallel_routes_refuse():
    a = [_seg_piece((0.0, 0.0), (30.0, 0.0)), _seg_piece((32.0, 0.0), (62.0, 0.0)),
         _seg_piece((64.0, 0.0), (94.0, 0.0))]
    b = [_seg_piece((0.0, 14.0), (30.0, 14.0)), _seg_piece((32.0, 14.0), (62.0, 14.0)),
         _seg_piece((64.0, 14.0), (94.0, 14.0))]
    w = walk_design_path(a + b, (0.0, 7.0), (94.0, 7.0))
    assert w["result"] == AMBIGUOUS
    assert "strand discriminator" in w["named_missing"]


def test_jitter_scale_variants_are_one_answer():
    a = [_seg_piece((0.0, 0.0), (30.0, 0.0)), _seg_piece((32.0, 0.0), (62.0, 0.0))]
    twin_jitter = [_seg_piece((0.0, 1.0), (30.0, 1.0))]  # <= TWIN_TOL off route a
    w = walk_design_path(a + twin_jitter, (0.0, 0.5), (62.0, 0.0))
    assert w["result"] == TRACED and w["path_groups"] == 1


def test_gap_beyond_cap_is_not_connected():
    a = [_seg_piece((0.0, 0.0), (30.0, 0.0)), _seg_piece((80.0, 0.0), (110.0, 0.0))]
    w = walk_design_path(a, (0.0, 0.0), (110.0, 0.0))
    assert w["result"] == NOT_CONNECTED
    assert "not continuously drawn" in w["named_missing"]


def test_hairpin_spur_collapses():
    verts = [(0.0, 0.0), (10.0, 0.0), (10.5, 10.0), (10.9, 0.3), (30.0, 0.0)]
    out = collapse_hairpins(verts)
    assert (10.5, 10.0) not in out


# --- declared-general extract modules carry no convention strings ----------------------

def test_general_law_modules_name_no_convention():
    """extract/ is exempt from the core drift guard by design, but these
    modules DECLARE themselves convention-agnostic law -- hold them to it."""
    import inspect
    import re as _re
    from truelinev2.extract import (conduit_topology, design_path,
                                    matchline_join, stroke_anchor)
    # company names anywhere (case-insensitive); CAD layer names only as
    # QUOTED LITERALS (the English words 'matchline'/'flower' in prose are
    # concepts, not configuration)
    forbidden = _re.compile(r"\b(?i:brenham|odot|tulsa|creek|nextlink|verofy)\b"
                            r"|[\"'](?:BORE - |MATCHLINE|FLOWER|INSTALLER"
                            r"|PORT HH)")
    for mod in (design_path, conduit_topology, matchline_join, stroke_anchor):
        src = inspect.getsource(mod)
        assert not forbidden.search(src), mod.__name__


# --- the verification-lens regressions (wrong-stroke constructions, refuted) ------------

def test_sharp_turn_dash_never_traversed_backwards_silently():
    """Verification lens 1: forcing nearer-end entry traversed a sharp-turn
    dash BACKWARDS and drew a unique self-crossing stroke. Both entries now
    branch; the variants land in distinct groups -> honest ambiguity (or the
    true direction wins) -- never a silent backwards bowtie."""
    pieces = [Piece(points=((-55.0, 0.0), (0.0, 0.0)), layer="C"),
              Piece(points=((30.0, 2.0), (20.0, 14.0)), layer="C"),
              Piece(points=((50.0, 30.0), (90.0, 70.0)), layer="C")]
    w = walk_design_path(pieces, (-60.0, 0.0), (95.0, 75.0))
    assert w["result"] != TRACED or not _self_crossing(w["stroke_points"])


def _self_crossing(pts):
    def inter(a, b, c, d):
        def ccw(p, q, r):
            return (r[1] - p[1]) * (q[0] - p[0]) > (q[1] - p[1]) * (r[0] - p[0])
        return (ccw(a, c, d) != ccw(b, c, d)) and (ccw(a, b, c) != ccw(a, b, d))
    segs = list(zip(pts, pts[1:]))
    return any(inter(*s1, *s2) for i, s1 in enumerate(segs)
               for s2 in segs[i + 2:])


def test_one_sided_junction_is_never_welded_across():
    """Verification lens 1: the third leg touched only pt_j and the junction
    was welded across. Both contact ends are now tested."""
    from truelinev2.extract.design_path import _weld
    i_piece = Piece(points=((-40.0, 0.0), (0.0, 0.0)), layer="C")
    j_piece = Piece(points=((3.9, 0.0), (44.0, 0.0)), layer="C")
    k_leg = Piece(points=((4.5, -0.5), (4.5, -50.0)), layer="C")
    out = _weld([i_piece, j_piece, k_leg], 4.0)
    assert len(out) == 3  # the junction survives; nothing welded across it


def test_piece_free_completion_is_not_a_trace():
    w = walk_design_path([], (0.0, 0.0), (20.0, 0.0))
    assert w["result"] == NOT_CONNECTED  # a bare chord is never TRACED


def test_parallel_strand_guard_refuses_unvisited_sibling():
    from truelinev2.extract.design_path import parallel_strand_guard
    path = [(0.0, 0.0), (100.0, 0.0), (200.0, 0.0)]
    sibling = Piece(points=((40.0, 12.0), (160.0, 12.0)), layer="C")
    anchor_leg = Piece(points=((1.0, 1.0), (1.0, 25.0)), layer="C")
    # a junction leg at an INTERIOR structure: one end ON the path -> the
    # exhaustive walk already explored and pruned it (adjudicated, exempt)
    junction_leg = Piece(points=((100.0, 2.0), (102.0, 25.0)), layer="C")
    cap = Piece(points=((50.0, 3.0), (51.0, 3.0)), layer="C")
    out = parallel_strand_guard([sibling, anchor_leg, junction_leg, cap],
                                frozenset(), path,
                                [(0.0, 0.0), (200.0, 0.0)], 30.0, 8.0)
    assert not out["clear"] and out["parallel_strands"] == 1  # sibling only


# --- chord certificate + tick adherence -------------------------------------------------

def test_chord_certificate_requires_collinear_ticks():
    s, e = (0.0, 0.0), (400.0, 0.0)
    straight = chord_straightness_certificate(
        [(100.0, 6.0), (300.0, 9.0)], s, e, 30.0)
    assert straight["straight"]
    curved = chord_straightness_certificate(
        [(100.0, 6.0), (200.0, 28.0)], s, e, 30.0)  # 28 > 30/2: route curves
    assert not curved["straight"]
    empty = chord_straightness_certificate([], s, e, 30.0)
    assert not empty["straight"]  # no evidence is never a certificate


def test_chord_certificate_refuting_and_sampling_laws():
    """Verification lens 1: an off-corridor in-span tick is PROOF the route
    leaves the chord -- it fails the certificate instead of being filtered;
    and sparse ticks that leave half the span un-sampled never certify."""
    s, e = (0.0, 0.0), (400.0, 0.0)
    refuted = chord_straightness_certificate(
        [(50.0, 4.0), (350.0, 5.0), (200.0, 45.0)], s, e, 30.0)
    assert not refuted["straight"] and refuted["off_chord_ticks"] == 1
    unsampled = chord_straightness_certificate(
        [(10.0, 4.0), (30.0, 5.0)], s, e, 30.0)  # 370 pt un-sampled
    assert not unsampled["straight"]
    one_tick = chord_straightness_certificate([(200.0, 4.0)], s, e, 30.0)
    assert not one_tick["straight"]  # a single tick samples nothing


def test_ticks_adhere_catches_a_path_leaving_the_tick_band():
    path = [(0.0, 0.0), (200.0, 60.0), (400.0, 0.0)]  # bulges away
    ticks = [(200.0, 5.0)]  # the route's tick sits near the CHORD
    out = ticks_adhere(path, ticks, 30.0)
    assert not out["adheres"] and out["offenders"] == 1
    ok = ticks_adhere([(0.0, 0.0), (200.0, 10.0), (400.0, 0.0)], ticks, 30.0)
    assert ok["adheres"]
