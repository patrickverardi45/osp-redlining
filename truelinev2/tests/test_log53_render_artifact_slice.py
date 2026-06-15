"""OWNER-PACKET-2 log53 render artifact -- offline tests.

Locks the pure route-ordering helper: the stroke is anchored at the two proven endpoints,
ordered monotonically by descending y, down-sampled by spacing, and invents NO coordinate
(every interior vertex comes from the passed corridor set). The PNG render itself is run by
the proof (real PDF); no artifact is asserted/committed here.
"""
from truelinev2.proof.run_log53_render_artifact_slice import order_route
from truelinev2.render.crop import REDLINE_STROKE_RGB


def test_route_is_anchored_at_proven_endpoints():
    start, end = (680.0, 441.0), (667.0, 84.0)
    corridor = [(679, 400), (678, 360), (677, 320), (676, 200), (670, 120)]
    route = order_route(start, end, corridor, step=35.0)
    assert route[0] == start
    assert route[-1] == end
    assert len(route) >= 2


def test_route_is_monotonic_descending_y():
    start, end = (680.0, 441.0), (667.0, 84.0)
    corridor = [(676, 200), (679, 400), (670, 120), (678, 360), (677, 320)]  # unordered
    route = order_route(start, end, corridor, step=35.0)
    ys = [p[1] for p in route]
    assert ys == sorted(ys, reverse=True)  # start (high y) -> end (low y)


def test_route_downsamples_by_spacing():
    start, end = (680.0, 441.0), (667.0, 84.0)
    corridor = [(679, 400), (679, 390), (679, 360)]  # 390 is < step from 400 -> dropped
    route = order_route(start, end, corridor, step=35.0)
    interior_y = [p[1] for p in route[1:-1]]
    assert 390.0 not in interior_y
    assert 400.0 in interior_y and 360.0 in interior_y


def test_route_invents_no_coordinates():
    start, end = (680.0, 441.0), (667.0, 84.0)
    corridor = [(679, 400), (678, 360), (677, 320)]
    route = order_route(start, end, corridor, step=35.0)
    allowed = {start, end} | {(round(x, 2), round(y, 2)) for x, y in corridor}
    for p in route:
        assert (p == start or p == end or (round(p[0], 2), round(p[1], 2)) in allowed)


def test_route_excludes_points_at_or_beyond_endpoints():
    start, end = (680.0, 441.0), (667.0, 84.0)
    corridor = [(680, 441), (667, 84), (678, 360)]  # endpoints themselves not duplicated
    route = order_route(start, end, corridor, step=35.0)
    assert route.count(start) == 1 and route.count(end) == 1


def test_canonical_red_only():
    assert REDLINE_STROKE_RGB == (220, 25, 25)
