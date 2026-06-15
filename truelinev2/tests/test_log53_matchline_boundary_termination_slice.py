"""OWNER-PACKET-2 log53 matchline boundary termination -- offline tests.

Locks: the typed result enum, the on-matchline-line helper, and the boundary-point law
(matchline_join.extend_dash_to_boundary) -- a terminal dash that reaches the matchline
resolves a point ON the line; a dash that stops short of the dash-gap resolves nothing.
No PDF parse here (the proof runs the real sheet-5 termination).
"""
from truelinev2.extract.matchline_join import extend_dash_to_boundary
from truelinev2.ingest.manual_adjudication import load_adjudication
from truelinev2.proof.run_log53_matchline_boundary_termination_slice import (
    ALLOWED,
    R_RESOLVED,
    R_RESOLVED_S5,
    R_STOPS,
    _on_line,
)

ML = (0.0, 100.0, 400.0, 102.0)  # a horizontal matchline line, centerline y=101


def _dash(x0, y0, x1, y1):
    return {"lines": [(x0, y0, x1, y1)]}


def test_result_enum_exact():
    assert ALLOWED == {
        "BOUNDARY_POINT_RESOLVED",
        "BOUNDARY_POINT_RESOLVED_SHEET5_ONLY",
        "BLOCKED_CHAIN_STOPS_BEFORE_MATCHLINE",
        "BLOCKED_CHAIN_MATCHLINE_INTERSECTION_AMBIGUOUS",
        "BLOCKED_BOUNDARY_POINT_NOT_ON_CHAIN",
        "BLOCKED_FRAME_CONTESTED_MATCHLINE",
        "BLOCKED_MATCHLINE_LABEL_NOT_UNIQUE",
        "BLOCKED_MATCHLINE_LINE_NOT_UNIQUE",
        "BLOCKED_NO_SAFE_BOUNDARY_POINT",
    }
    assert {R_RESOLVED, R_RESOLVED_S5, R_STOPS} <= ALLOWED


def test_on_line_helper():
    assert _on_line((50.0, 101.0), ML) is True
    assert _on_line((50.0, 150.0), ML) is False     # well below the line
    assert _on_line((50.0, 104.0), ML) is True      # within the +/-4 margin
    assert _on_line((-10.0, 101.0), ML) is False    # left of the line span


def test_terminal_dash_reaches_resolves_point_on_line():
    # a dash whose endpoint touches the matchline -> extend to the centerline (y=101)
    chain = [_dash(50, 130, 50, 103)]
    bnd = extend_dash_to_boundary(chain, ML)
    assert bnd is not None
    assert round(bnd[1], 1) == 101.0          # on the matchline centerline
    assert _on_line(bnd, ML) is True


def test_terminal_dash_stops_short_resolves_nothing():
    # a dash that ends 48 pt away (> dash-gap) -> no boundary point (no nearest-snap)
    chain = [_dash(50, 160, 50, 150)]
    assert extend_dash_to_boundary(chain, ML) is None


def test_slice_consumes_end_anchor_bridge():
    doc = load_adjudication()
    l53 = next(r for r in doc["logs"] if r["log_id"] == "log53")
    end = l53["endpoint_anchors"]["end"]
    assert end["boundary_kind"] == "matchline_continuation"
    assert end["station"] == "24+11"
    assert end["continues_to_sheet"] == 6
