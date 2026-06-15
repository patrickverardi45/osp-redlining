"""OWNER-PACKET-2 log66 render artifact -- offline tests.

Locks the pure honesty helpers for log66's ordered-chain render: every INTERIOR route vertex is a
real drawn conduit dash endpoint (no invented coordinate), and every route EDGE is either a real
drawn dash or a <= MAX_DASH_GAP gap hop -- so no edge fabricates a straight jump across log66's
36.36 pt direct-corridor gap. Also locks the result enum, the canonical red color, that MAX_DASH_GAP
is NOT loosened, log66-only output naming, that the slice consumes log66's encoded identity AND that
sheet 10 is owner-confirmed (corrected_sheets == [10]) and log66 is PROMOTED into the seam, and
that the proof is a contained artifact (no product/API/match wiring). The PNG render itself is run by
the proof against the real PDF; no artifact is asserted/committed here.
"""
from pathlib import Path

import pytest

from truelinev2.extract.conduit_topology import MAX_DASH_GAP
from truelinev2.extract.structure_position import BRENHAM_STRUCTURE_LAYERS
from truelinev2.ingest.manual_adjudication import load_adjudication
from truelinev2.proof.run_log59_render_artifact_slice import (
    interior_vertices_are_dash_endpoints,
    route_edges_source_backed,
)
from truelinev2.proof.run_log66_render_artifact_slice import ALLOWED, OUT_DIR, R_CREATED
from truelinev2.seam import ELIGIBLE_EXEMPLARS, build_seam_payload
from truelinev2.render.crop import REDLINE_STROKE_RGB
from truelinev2.stations import parse_station

# a synthetic dashed horizontal conduit chain (log66 family): three drawn dashes with 30 pt gaps
_CHAIN = [
    {"lines": [(0.0, 0.0, 30.0, 0.0)]},
    {"lines": [(60.0, 0.0, 90.0, 0.0)]},
    {"lines": [(120.0, 0.0, 150.0, 0.0)]},
]
_DASH_ROUTE = [(0.0, 0.0), (30.0, 0.0), (60.0, 0.0), (90.0, 0.0), (120.0, 0.0), (150.0, 0.0)]


def test_result_enum_exact():
    assert ALLOWED == {
        "LOG66_RENDER_ARTIFACT_CREATED",
        "BLOCKED_LOG66_RENDER_ENDPOINT_MISMATCH",
        "BLOCKED_LOG66_RENDER_CHAIN_NOT_CONNECTED",
        "BLOCKED_LOG66_RENDER_DIRECT_CORRIDOR_CONTINUOUS",
        "BLOCKED_LOG66_RENDER_ROUTE_NOT_SOURCE_BACKED",
        "BLOCKED_LOG66_RENDER_SPAN_ANNOTATION_MISMATCH",
        "BLOCKED_LOG66_RENDER_ARTIFACT_FAILED",
    }
    assert R_CREATED == "LOG66_RENDER_ARTIFACT_CREATED"


def test_canonical_red_only():
    assert REDLINE_STROKE_RGB == (220, 25, 25)


def test_max_dash_gap_not_loosened():
    assert MAX_DASH_GAP == 35.0


def test_interior_vertices_must_be_real_dash_endpoints():
    assert interior_vertices_are_dash_endpoints(_DASH_ROUTE, _CHAIN)
    invented = [(0.0, 0.0), (45.0, 5.0), (150.0, 0.0)]
    assert not interior_vertices_are_dash_endpoints(invented, _CHAIN)


def test_route_edges_reject_fabricated_straight_jump():
    # threading the dashes: every edge is a drawn dash or a <= MAX_DASH_GAP gap hop -> source-backed
    assert route_edges_source_backed(_DASH_ROUTE, _CHAIN)
    # a 2-point straight shortcut (150 pt) that is NOT a drawn dash -> refused (the 36.36 gap fake)
    assert not route_edges_source_backed([(0.0, 0.0), (150.0, 0.0)], _CHAIN)


def test_route_edges_allow_long_edge_only_when_a_real_drawn_dash():
    long_chain = [{"lines": [(0.0, 0.0, 150.0, 0.0)]}]
    assert route_edges_source_backed([(0.0, 0.0), (150.0, 0.0)], long_chain)


def test_output_dir_is_gitignored_data_outputs():
    p = str(OUT_DIR).replace("\\", "/")
    assert "/data/outputs/log66_render_artifact" in p


def test_slice_consumes_log66_identity_owner_confirmed_and_promoted():
    doc = load_adjudication()
    rec = {r["log_id"]: r for r in doc["logs"]}
    l66 = rec["log66"]
    s, e = l66["endpoint_anchors"]["start"], l66["endpoint_anchors"]["end"]
    assert (s["structure_class"], s["station"]) == ("installer_hh", "0+55")
    assert (e["structure_class"], e["station"]) == ("nextlink_hh", "45+33")
    # the END is a nextlink_hh -> NO structure-layer entry; it binds only via the callout locator
    assert "nextlink_hh" not in BRENHAM_STRUCTURE_LAYERS
    # sheet 10 is owner-confirmed -> recorded in corrected_sheets
    assert list(l66["corrected_sheets"]) == [10]
    # log66 is now PROMOTED into the seam (eligible set includes it; build_seam_payload builds it)
    assert tuple(ELIGIBLE_EXEMPLARS) == ("log53", "log64", "log71", "log59", "log66")
    build_seam_payload("log66", l66)


def test_span_is_owner_evidence_not_cross_frame_math():
    # the 55' run is the owner annotation + span_ft, NOT a station subtraction (different reset frames)
    doc = load_adjudication()
    l66 = next(r for r in doc["logs"] if r["log_id"] == "log66")
    assert abs(float(l66["span_ft"]) - 55.0) <= 0.5
    s, e = l66["endpoint_anchors"]["start"]["station"], l66["endpoint_anchors"]["end"]["station"]
    assert abs(parse_station(e) - parse_station(s)) != 55.0   # naive cross-frame subtraction is WRONG


def test_proof_is_contained_no_product_wiring():
    src = Path(__file__).resolve().parent.parent / "proof" / "run_log66_render_artifact_slice.py"
    text = src.read_text(encoding="utf-8")
    # contained artifact: uses the render.crop helper directly, never the product pipeline
    assert "truelinev2.service" not in text
    assert "truelinev2.api" not in text
    assert "from truelinev2.match" not in text
    # END binds via the callout locator (nextlink_hh has no structure-layer entry)
    assert "resolve_nextlink_hh_callout" in text
