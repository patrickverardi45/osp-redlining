"""Tests for backend/app/core/address_point_index.py.

Exercises the parser against the Brenham PH5 source-truth KMZ fixture used
by the F7f harness. Asserts that LAWNDALE (17) and HUISACHE (9) subscriber
Points are extracted with full address schema, and that CHERI yields zero
Points (no CHERI data exists anywhere in the Brenham PH5 design).
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("TRUELINE_JWT_SECRET", "addr-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "addr-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend.app.core.address_point_index import (
    parse_address_points_from_kml,
    _parse_description_kv,
    _parse_point_coords,
)

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "brenham_phase5_source_truth.kmz"


def _load_kmz_bytes() -> bytes:
    return FIXTURE_PATH.read_bytes()


def test_fixture_kmz_extraction_runs() -> None:
    points = parse_address_points_from_kml(_load_kmz_bytes(), "brenham_phase5_source_truth.kmz")
    assert isinstance(points, list)
    assert len(points) > 0


def test_extracts_lawndale_points_with_full_schema() -> None:
    points = parse_address_points_from_kml(_load_kmz_bytes(), "brenham_phase5_source_truth.kmz")
    lawndale = [p for p in points if "LAWNDALE" in (p.get("street_name") or "").upper()]
    assert len(lawndale) == 17
    sample = lawndale[0]
    for key in ("lon", "lat", "street_name", "street_number", "address", "ap_number", "node_type", "splice_location", "folder_path"):
        assert key in sample, f"missing key {key}"
    assert isinstance(sample["lon"], float)
    assert isinstance(sample["lat"], float)
    # Brenham latitude / longitude range
    assert -97.0 < sample["lon"] < -96.0
    assert 30.0 < sample["lat"] < 30.5
    # All entries should have Lawndale Avenue street_name
    for p in lawndale:
        assert "LAWNDALE" in p["street_name"].upper()


def test_extracts_huisache_points_with_full_schema() -> None:
    points = parse_address_points_from_kml(_load_kmz_bytes(), "brenham_phase5_source_truth.kmz")
    huisache = [p for p in points if "HUISACHE" in (p.get("street_name") or "").upper()]
    assert len(huisache) == 9
    for p in huisache:
        assert "HUISACHE" in p["street_name"].upper()
        assert p["address"].strip() != ""


def test_no_cheri_points_in_brenham_fixture() -> None:
    points = parse_address_points_from_kml(_load_kmz_bytes(), "brenham_phase5_source_truth.kmz")
    cheri = [p for p in points if "CHERI" in (p.get("street_name") or "").upper()]
    assert cheri == [], f"unexpected CHERI hits: {cheri}"


def test_output_is_deterministic_across_runs() -> None:
    kmz = _load_kmz_bytes()
    run1 = parse_address_points_from_kml(kmz, "test.kmz")
    run2 = parse_address_points_from_kml(kmz, "test.kmz")
    assert run1 == run2


def test_output_is_sorted_by_lon_lat() -> None:
    points = parse_address_points_from_kml(_load_kmz_bytes(), "test.kmz")
    for i in range(1, len(points)):
        assert (points[i - 1]["lon"], points[i - 1]["lat"]) <= (points[i]["lon"], points[i]["lat"])


def test_points_without_street_name_are_dropped() -> None:
    # The Brenham fixture has 576 Point placemarks but only those with a
    # populated Street Name field should survive (subscriber addresses).
    points = parse_address_points_from_kml(_load_kmz_bytes(), "test.kmz")
    for p in points:
        assert (p.get("street_name") or "").strip() != ""


def test_description_kv_parser_handles_typical_table() -> None:
    html = (
        "<html><body><table>"
        "<tr><td>Address</td><td>802 Lawndale Ave, Brenham, TX 77833, USA</td></tr>"
        "<tr><td>Street Name</td><td>Lawndale Avenue</td></tr>"
        "<tr><td>Street Number</td><td>802</td></tr>"
        "</table></body></html>"
    )
    kv = _parse_description_kv(html)
    assert kv["Address"] == "802 Lawndale Ave, Brenham, TX 77833, USA"
    assert kv["Street Name"] == "Lawndale Avenue"
    assert kv["Street Number"] == "802"


def test_description_kv_parser_handles_empty_input() -> None:
    assert _parse_description_kv("") == {}
    assert _parse_description_kv(None) == {}
    assert _parse_description_kv("no html here") == {}


def test_point_coord_parser_handles_standard_format() -> None:
    assert _parse_point_coords("-96.38557,30.15095,0") == (-96.38557, 30.15095)
    assert _parse_point_coords("-96.38557,30.15095") == (-96.38557, 30.15095)
    assert _parse_point_coords("") == ()
    assert _parse_point_coords("garbage") == ()
