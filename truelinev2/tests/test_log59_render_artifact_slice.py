"""OWNER-PACKET-2 log59 render artifact -- offline tests.

Locks the pure honesty helpers for log59's ordered-chain render: every INTERIOR route vertex is a
real drawn conduit dash endpoint (no invented coordinate), and every route EDGE is either a real
drawn dash or a <= MAX_DASH_GAP gap hop -- so no edge fabricates a straight jump across log59's
35.64 pt direct-corridor gap. Also locks the result enum, the canonical red color, that MAX_DASH_GAP
is NOT loosened, log59-only output naming, that the slice consumes log59's encoded identity AND keeps
corrected_sheets == [] (sheet 21 stays SOURCE-RECOVERED bridge evidence, NOT promoted), and that the
proof is a contained artifact (no product/API/match wiring). The PNG render itself is run by the proof
against the real PDF; no artifact is asserted/committed here.
"""
from pathlib import Path

from truelinev2.extract.conduit_topology import MAX_DASH_GAP
from truelinev2.ingest.manual_adjudication import load_adjudication
from truelinev2.proof.run_log59_render_artifact_slice import (
    ALLOWED,
    OUT_DIR,
    R_CREATED,
    interior_vertices_are_dash_endpoints,
    route_edges_source_backed,
)
from truelinev2.render.crop import REDLINE_STROKE_RGB

# a synthetic dashed horizontal conduit chain (log59 family): three drawn dashes with 30 pt gaps
_CHAIN = [
    {"lines": [(0.0, 0.0, 30.0, 0.0)]},
    {"lines": [(60.0, 0.0, 90.0, 0.0)]},
    {"lines": [(120.0, 0.0, 150.0, 0.0)]},
]
_DASH_ROUTE = [(0.0, 0.0), (30.0, 0.0), (60.0, 0.0), (90.0, 0.0), (120.0, 0.0), (150.0, 0.0)]


def test_result_enum_exact():
    assert ALLOWED == {
        "LOG59_RENDER_ARTIFACT_CREATED",
        "BLOCKED_LOG59_RENDER_ENDPOINT_MISMATCH",
        "BLOCKED_LOG59_RENDER_CHAIN_NOT_CONNECTED",
        "BLOCKED_LOG59_RENDER_DIRECT_CORRIDOR_CONTINUOUS",
        "BLOCKED_LOG59_RENDER_ROUTE_NOT_SOURCE_BACKED",
        "BLOCKED_LOG59_RENDER_SPAN_ANNOTATION_MISMATCH",
        "BLOCKED_LOG59_RENDER_ARTIFACT_FAILED",
    }
    assert R_CREATED == "LOG59_RENDER_ARTIFACT_CREATED"


def test_canonical_red_only():
    assert REDLINE_STROKE_RGB == (220, 25, 25)


def test_max_dash_gap_not_loosened():
    assert MAX_DASH_GAP == 35.0


def test_interior_vertices_must_be_real_dash_endpoints():
    # interior (30,0),(60,0),(90,0),(120,0) are all real dash endpoints
    assert interior_vertices_are_dash_endpoints(_DASH_ROUTE, _CHAIN)
    # an invented interior vertex (45,5) lies near no drawn dash endpoint -> rejected
    invented = [(0.0, 0.0), (45.0, 5.0), (150.0, 0.0)]
    assert not interior_vertices_are_dash_endpoints(invented, _CHAIN)


def test_route_edges_reject_fabricated_straight_jump():
    # threading the dashes: every edge is a drawn dash or a <= MAX_DASH_GAP gap hop -> source-backed
    assert route_edges_source_backed(_DASH_ROUTE, _CHAIN)
    # a 2-point straight shortcut (150 pt) that is NOT a drawn dash -> refused (the 35.64 gap fake)
    assert not route_edges_source_backed([(0.0, 0.0), (150.0, 0.0)], _CHAIN)


def test_route_edges_allow_long_edge_only_when_a_real_drawn_dash():
    # a single long drawn dash legitimately spans 150 pt: the long edge IS source-backed
    long_chain = [{"lines": [(0.0, 0.0, 150.0, 0.0)]}]
    assert route_edges_source_backed([(0.0, 0.0), (150.0, 0.0)], long_chain)


def test_output_dir_is_gitignored_data_outputs():
    p = str(OUT_DIR).replace("\\", "/")
    assert "/data/outputs/log59_render_artifact" in p


def test_slice_consumes_log59_identity_and_does_not_promote():
    doc = load_adjudication()
    l59 = next(r for r in doc["logs"] if r["log_id"] == "log59")
    s, e = l59["endpoint_anchors"]["start"], l59["endpoint_anchors"]["end"]
    assert (s["structure_class"], s["station"]) == ("installer_hh", "2+76")
    assert (e["structure_class"], e["station"]) == ("flower_pot", "4+46")
    # sheet 21 stays SOURCE-RECOVERED bridge evidence -- NOT promoted to corrected_sheets
    assert list(l59["corrected_sheets"]) == []


def test_proof_is_contained_no_product_wiring():
    src = Path(__file__).resolve().parent.parent / "proof" / "run_log59_render_artifact_slice.py"
    text = src.read_text(encoding="utf-8")
    # contained artifact: uses the render.crop helper directly, never the product pipeline
    assert "truelinev2.service" not in text
    assert "truelinev2.api" not in text
    assert "from truelinev2.match" not in text
