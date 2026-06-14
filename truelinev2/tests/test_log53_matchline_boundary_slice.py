"""OWNER-PACKET-2 log53 matchline-boundary slice -- offline tests.

Locks the proof's pure laws: the allowed boundary statuses, the no-coordinate guard,
and that the slice consumes log53's endpoint_anchors bridge (end = matchline
continuation). No PDF parse here (the proof runs the real sheet-5 geometry).
"""
from truelinev2.ingest.manual_adjudication import load_adjudication
from truelinev2.proof.run_log53_matchline_boundary_slice import (
    AMBIGUOUS,
    BOUNDARY_READY,
    BOUNDARY_READY_STROKE_NOT,
    ENGINE_LAW,
    FRAME_CONTESTED,
    NO_PRIMITIVE,
    NO_SEAM,
    _no_coords,
)

ALLOWED_STATUSES = {
    BOUNDARY_READY, BOUNDARY_READY_STROKE_NOT, NO_SEAM, AMBIGUOUS,
    FRAME_CONTESTED, NO_PRIMITIVE, ENGINE_LAW,
}


def test_allowed_status_set_exact():
    # exactly the mission's seven allowed statuses, no extras
    assert ALLOWED_STATUSES == {
        "BOUNDARY_GEOMETRY_READY",
        "BOUNDARY_GEOMETRY_READY_BUT_STROKE_NOT_READY",
        "BLOCKED_NO_MATCHLINE_BOUNDARY_GEOMETRY_SEAM",
        "BLOCKED_AMBIGUOUS_MATCHLINE_BOUNDARY_GEOMETRY",
        "BLOCKED_FRAME_CONTESTED_MATCHLINE",
        "BLOCKED_NO_SOURCE_BOUNDARY_PRIMITIVE",
        "BLOCKED_ENGINE_LAW",
    }


def test_no_coords_accepts_real_anchor():
    doc = load_adjudication()
    l53 = next(r for r in doc["logs"] if r["log_id"] == "log53")
    assert _no_coords(l53["endpoint_anchors"]) is True


def test_no_coords_rejects_injected_coordinate():
    assert _no_coords({"end": {"x": 12.0, "y": 34.0}}) is False
    assert _no_coords({"end": {"stroke_points": [[1, 2]]}}) is False
    assert _no_coords({"end": {"boundary_kind": "matchline_continuation"}}) is True


def test_slice_consumes_endpoint_anchor_bridge():
    doc = load_adjudication()
    l53 = next(r for r in doc["logs"] if r["log_id"] == "log53")
    end = l53["endpoint_anchors"]["end"]
    assert end["boundary_kind"] == "matchline_continuation"
    assert end["continues_to_sheet"] == 6
    assert end["structure_class"] is None  # a continuation is not a terminus
