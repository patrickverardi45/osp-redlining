"""OWNER-PACKET-2 log64 render artifact -- offline tests.

Locks the pure route helpers: corridor points are filtered to the direct band (off-corridor
points rejected), the route is anchored at both proven endpoints with correct orientation even
though log64's start sits BELOW its end, it is monotonic by y, and it invents no coordinate. Also
locks the result enum, the canonical red color, log64-only output naming, and that the proof is a
contained artifact (no product/API/match wiring). The PNG render itself is run by the proof
(real PDF); no artifact is asserted/committed here.
"""
from pathlib import Path

from truelinev2.ingest.manual_adjudication import load_adjudication
from truelinev2.proof.run_log64_render_artifact_slice import (
    ALLOWED,
    OUT_DIR,
    R_CREATED,
    build_route,
    corridor_points,
)
from truelinev2.render.crop import REDLINE_STROKE_RGB


def test_result_enum_exact():
    assert ALLOWED == {
        "LOG64_RENDER_ARTIFACT_CREATED", "BLOCKED_LOG64_RENDER_NO_SOURCE_CORRIDOR",
        "BLOCKED_LOG64_RENDER_ROUTE_AMBIGUOUS", "BLOCKED_LOG64_RENDER_ENDPOINT_MISSING",
        "BLOCKED_LOG64_RENDER_ARTIFACT_FAILED",
    }
    assert R_CREATED == "LOG64_RENDER_ARTIFACT_CREATED"


def test_canonical_red_only():
    assert REDLINE_STROKE_RGB == (220, 25, 25)


def test_corridor_points_filter_off_corridor():
    s_xy, e_xy = (252.0, 389.0), (254.0, 534.0)
    eps = [(253.0, 389.0), (253.0, 420.0), (253.0, 500.0), (300.0, 450.0), (253.0, 534.0)]
    pts = corridor_points(eps, s_xy, e_xy, half=40.0)
    assert (300.0, 450.0) not in pts          # off-centerline stub rejected
    assert (253.0, 420.0) in pts and (253.0, 500.0) in pts


def test_build_route_orients_start_to_end():
    # log64 orientation: start (installer HH) y=389 sits BELOW end (flower pot) y=534;
    # build_route must still emit the polyline START -> END as documented (not reversed)
    start, end = (252.31, 389.34), (254.29, 534.07)
    corridor = [(253.0, 413.0), (253.0, 445.0), (253.0, 479.0), (253.0, 511.0)]
    route = build_route(start, end, corridor, step=35.0)
    assert route[0] == start and route[-1] == end    # documented direction: installer HH -> flower pot
    assert len(route) >= 3                            # has interior corridor vertices
    ys = [p[1] for p in route]
    assert ys == sorted(ys)                           # monotonic ascending y: start (low) -> end (high)


def test_build_route_invents_no_coordinate():
    start, end = (252.31, 389.34), (254.29, 534.07)
    corridor = [(253.0, 413.0), (253.0, 445.0), (253.0, 479.0), (253.0, 511.0)]
    route = build_route(start, end, corridor, step=35.0)
    allowed = {start, end} | {(round(x, 2), round(y, 2)) for x, y in corridor}
    for p in route:
        assert p == start or p == end or (round(p[0], 2), round(p[1], 2)) in allowed


def test_output_dir_is_gitignored_data_outputs():
    p = str(OUT_DIR).replace("\\", "/")
    assert "/data/outputs/log64_render_artifact" in p


def test_slice_consumes_log64_encoded_identity():
    doc = load_adjudication()
    l64 = next(r for r in doc["logs"] if r["log_id"] == "log64")
    s, e = l64["endpoint_anchors"]["start"], l64["endpoint_anchors"]["end"]
    assert (s["structure_class"], s["station"]) == ("installer_hh", "3+69")
    assert (e["structure_class"], e["station"]) == ("flower_pot", "1+00")


def test_proof_is_contained_no_product_wiring():
    src = Path(__file__).resolve().parent.parent / "proof" / "run_log64_render_artifact_slice.py"
    text = src.read_text(encoding="utf-8")
    # contained artifact: uses the render.crop helper directly, never the product pipeline
    assert "truelinev2.service" not in text
    assert "truelinev2.api" not in text
    assert "from truelinev2.match" not in text
