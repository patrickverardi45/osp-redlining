"""Tests for backend/app/core/candidate_route_discovery.py.

Pure unit tests using synthetic address-point + route-catalog fixtures
shaped to mirror the Brenham observation: LAWNDALE points cluster near
one Underground Cable trunk surrounded by many short House Drop tails.

Allowlist scope: LAWNDALE only. HUISACHE alone and CHERI return None
deterministically.
"""

from __future__ import annotations

import copy
import os

os.environ.setdefault("TRUELINE_JWT_SECRET", "disc-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "disc-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend.app.core.candidate_route_discovery import (
    discover_candidate_routes_from_notes_streets,
)


def _lawndale_address_points() -> list:
    # Approximate Brenham PH5 LAWNDALE cluster — 17 points along a ~800 ft EW span
    base_lon = -96.38557
    base_lat = 30.15095
    out = []
    for i in range(17):
        out.append({
            "lon": base_lon + 0.00015 * i,  # spread eastward
            "lat": base_lat + 0.00008 * (i % 3),  # slight N/S jitter
            "street_name": "Lawndale Avenue",
            "street_number": str(800 + i * 2),
            "address": f"{800 + i*2} Lawndale Ave, Brenham, TX 77833, USA",
            "ap_number": "120",
            "node_type": "House",
            "splice_location": "28",
            "folder_path": "Brenham_PH5",
        })
    return out


def _huisache_address_points() -> list:
    base_lon = -96.38627
    base_lat = 30.15127
    out = []
    for i in range(9):
        out.append({
            "lon": base_lon - 0.00010 * i,
            "lat": base_lat + 0.00020 * i,
            "street_name": "Huisache Street",
            "street_number": str(2100 + i),
            "address": f"{2100 + i} Huisache St, Brenham, TX 77833, USA",
            "ap_number": "120",
            "node_type": "House",
            "splice_location": "28",
            "folder_path": "Brenham_PH5",
        })
    return out


def _route_catalog_with_trunk_and_drops() -> list:
    # Trunk Underground Cable that runs along the LAWNDALE row (covers the cluster)
    trunk_coords = [
        (-96.38560, 30.15100),
        (-96.38260, 30.15100),
    ]
    trunk = {
        "route_id": "route_trunk",
        "route_name": "Underground Cable",
        "source_folder": "Connections / underground cable",
        "coords": trunk_coords,
        "length_ft": 2800.0,
        "point_count": 2,
        "route_role": "underground_cable",
    }
    # 17 short House Drop tails, each terminating at a LAWNDALE address
    base_lon = -96.38557
    base_lat = 30.15095
    drops = []
    for i in range(17):
        drops.append({
            "route_id": f"route_drop_{i}",
            "route_name": "House Drop",
            "source_folder": "Connections / House Drop",
            "coords": [
                (base_lon + 0.00015 * i, base_lat + 0.00008 * (i % 3)),
                (base_lon + 0.00015 * i + 0.00005, base_lat + 0.00008 * (i % 3) + 0.00005),
            ],
            "length_ft": 60.0,
            "point_count": 2,
            "route_role": "house_drop",
        })
    return [trunk] + drops


def test_lawndale_notes_returns_trunk_candidate() -> None:
    result = discover_candidate_routes_from_notes_streets(
        ["LAWNDALE AVE"],
        _lawndale_address_points(),
        _route_catalog_with_trunk_and_drops(),
    )
    assert result is not None
    assert result["discovered_route_ids"] == ["route_trunk"]
    assert result["source"] == "kmz_point_to_linestring_proximity"
    assert result["evidence"]["point_count"] == 17
    assert result["evidence"]["coverage_count"] == 17
    assert result["evidence"]["coverage_ratio"] == 1.0
    assert result["evidence"]["distance_threshold_ft"] == 100.0
    assert result["evidence"]["route_name"] == "Underground Cable"
    assert "underground cable" in result["evidence"]["source_folder"]


def test_lawndale_avenue_full_form_also_matches() -> None:
    result = discover_candidate_routes_from_notes_streets(
        ["Lawndale Avenue"],
        _lawndale_address_points(),
        _route_catalog_with_trunk_and_drops(),
    )
    assert result is not None
    assert result["discovered_route_ids"] == ["route_trunk"]


def test_lawndale_plus_huisache_in_notes_returns_lawndale_trunk() -> None:
    # bore_log71 case: notes contain both terms
    result = discover_candidate_routes_from_notes_streets(
        ["LAWNDALE AVE", "HUISACHE"],
        _lawndale_address_points() + _huisache_address_points(),
        _route_catalog_with_trunk_and_drops(),
    )
    assert result is not None
    assert result["discovered_route_ids"] == ["route_trunk"]


def test_huisache_alone_returns_none() -> None:
    # bore_log71 evidence isolated to Huisache only — must remain abstained
    result = discover_candidate_routes_from_notes_streets(
        ["HUISACHE"],
        _huisache_address_points(),
        _route_catalog_with_trunk_and_drops(),
    )
    assert result is None


def test_cheri_returns_none() -> None:
    # No CHERI in either address_points or route_catalog
    result = discover_candidate_routes_from_notes_streets(
        ["CHERI LN"],
        _lawndale_address_points() + _huisache_address_points(),
        _route_catalog_with_trunk_and_drops(),
    )
    assert result is None


def test_returns_none_when_only_drop_tails_match() -> None:
    drops_only = [r for r in _route_catalog_with_trunk_and_drops() if "House Drop" in r["source_folder"]]
    result = discover_candidate_routes_from_notes_streets(
        ["LAWNDALE AVE"],
        _lawndale_address_points(),
        drops_only,
    )
    assert result is None


def test_returns_none_when_address_points_empty() -> None:
    result = discover_candidate_routes_from_notes_streets(
        ["LAWNDALE AVE"],
        [],
        _route_catalog_with_trunk_and_drops(),
    )
    assert result is None


def test_returns_none_when_route_catalog_empty() -> None:
    result = discover_candidate_routes_from_notes_streets(
        ["LAWNDALE AVE"],
        _lawndale_address_points(),
        [],
    )
    assert result is None


def test_returns_none_when_notes_streets_empty() -> None:
    result = discover_candidate_routes_from_notes_streets(
        [],
        _lawndale_address_points(),
        _route_catalog_with_trunk_and_drops(),
    )
    assert result is None


def test_returns_none_for_unsupported_street() -> None:
    # POST OAK CT is in CURRENT_PACKET_PRINT_SHEET_INDEX but NOT in the
    # discovery allowlist — must return None to remain conservative.
    result = discover_candidate_routes_from_notes_streets(
        ["POST OAK CT"],
        _lawndale_address_points(),
        _route_catalog_with_trunk_and_drops(),
    )
    assert result is None


def test_dominance_gate_blocks_tied_candidates() -> None:
    # Two parallel trunks both covering the LAWNDALE cluster → tied →
    # discovery must return None (ambiguous, prefer abstain over guess).
    catalog = _route_catalog_with_trunk_and_drops()
    # Add a second identical trunk under a different route_id
    second_trunk = dict(catalog[0])
    second_trunk["route_id"] = "route_trunk_b"
    catalog.append(second_trunk)
    result = discover_candidate_routes_from_notes_streets(
        ["LAWNDALE AVE"],
        _lawndale_address_points(),
        catalog,
    )
    assert result is None


def test_helper_does_not_mutate_inputs() -> None:
    notes = ["LAWNDALE AVE"]
    points = _lawndale_address_points()
    catalog = _route_catalog_with_trunk_and_drops()
    notes_snap = copy.deepcopy(notes)
    points_snap = copy.deepcopy(points)
    catalog_snap = copy.deepcopy(catalog)
    _ = discover_candidate_routes_from_notes_streets(notes, points, catalog)
    assert notes == notes_snap
    assert points == points_snap
    assert catalog == catalog_snap


def test_distance_threshold_kwarg_changes_coverage() -> None:
    # Tighten threshold to 5 ft; the trunk should no longer cover the
    # cluster (cluster points are roughly 6+ ft from the trunk).
    result = discover_candidate_routes_from_notes_streets(
        ["LAWNDALE AVE"],
        _lawndale_address_points(),
        _route_catalog_with_trunk_and_drops(),
        distance_threshold_ft=0.1,
    )
    assert result is None


def test_coverage_threshold_kwarg_blocks_below_floor() -> None:
    # Require 100% coverage but synthetic trunk only passes near most points;
    # if we set 1.01 the gate always fails.
    result = discover_candidate_routes_from_notes_streets(
        ["LAWNDALE AVE"],
        _lawndale_address_points(),
        _route_catalog_with_trunk_and_drops(),
        coverage_ratio_threshold=1.01,
    )
    assert result is None
