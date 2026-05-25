"""Tests for backend/app/core/coverage_sanity.py.

Pure unit tests against the collapse-detection diagnostic. Synthetic
group_matches simulate the production failure mode: many groups packed
onto a handful of long routes.
"""

from __future__ import annotations

import os

os.environ.setdefault("TRUELINE_JWT_SECRET", "cov-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "cov-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend.app.core.coverage_sanity import compute_coverage_sanity


def _match(route_id: str, station_points: int = 5, render_allowed: bool = True, source_file: str = "f.xlsx") -> dict:
    return {
        "route_id": route_id,
        "render_allowed": render_allowed,
        "group_station_points": [{"station_ft": i * 10.0} for i in range(station_points)],
        "source_file": source_file,
    }


def _route(route_id: str, role: str = "underground_cable") -> dict:
    return {"route_id": route_id, "route_role": role, "route_name": f"Route {route_id}"}


# ── A. Basic counting ────────────────────────────────────────────────────────


def test_empty_inputs_yield_zero_counts() -> None:
    out = compute_coverage_sanity([], [], 0)
    assert out["total_groups"] == 0
    assert out["placed_group_count"] == 0
    assert out["abstained_group_count"] == 0
    assert out["matched_route_count"] == 0
    assert out["corpus_collapse_detected"] is False
    assert out["warnings"] == []


def test_abstained_count_when_groups_exceed_placed() -> None:
    matches = [_match("route_a") for _ in range(10)]
    out = compute_coverage_sanity(matches, [_route("route_a")], total_groups=58)
    assert out["placed_group_count"] == 10
    assert out["abstained_group_count"] == 48


def test_render_allowed_false_excluded_from_placed_count() -> None:
    matches = [_match("route_a", render_allowed=True), _match("route_b", render_allowed=False)]
    out = compute_coverage_sanity(matches, [_route("route_a"), _route("route_b")], total_groups=2)
    assert out["placed_group_count"] == 1


def test_missing_route_id_excluded() -> None:
    matches = [_match("route_a"), {"route_id": "", "render_allowed": True, "group_station_points": []}]
    out = compute_coverage_sanity(matches, [_route("route_a")], total_groups=2)
    assert out["placed_group_count"] == 1
    assert out["matched_route_count"] == 1


# ── B. Distribution / diversity ──────────────────────────────────────────────


def test_diversity_ratio_full_distribution() -> None:
    matches = [_match(f"route_{i}") for i in range(20)]
    catalog = [_route(f"route_{i}") for i in range(20)]
    out = compute_coverage_sanity(matches, catalog, total_groups=20)
    assert out["matched_route_count"] == 20
    assert out["diversity_ratio"] == 1.0


def test_diversity_ratio_perfect_collapse() -> None:
    matches = [_match("route_x") for _ in range(20)]
    out = compute_coverage_sanity(matches, [_route("route_x")], total_groups=20)
    assert out["matched_route_count"] == 1
    assert out["diversity_ratio"] == round(1 / 20, 4)


# ── C. Top routes ────────────────────────────────────────────────────────────


def test_top_routes_by_group_count_ordering() -> None:
    matches = (
        [_match("route_a") for _ in range(10)]
        + [_match("route_b") for _ in range(5)]
        + [_match("route_c") for _ in range(2)]
    )
    catalog = [_route("route_a"), _route("route_b"), _route("route_c")]
    out = compute_coverage_sanity(matches, catalog, total_groups=17)
    top = out["top_routes_by_group_count"]
    assert [r["route_id"] for r in top] == ["route_a", "route_b", "route_c"]
    assert [r["assigned_group_count"] for r in top] == [10, 5, 2]


def test_top_routes_by_station_count_uses_station_totals() -> None:
    matches = [
        _match("route_a", station_points=10),
        _match("route_a", station_points=10),
        _match("route_b", station_points=100),
    ]
    out = compute_coverage_sanity(matches, [_route("route_a"), _route("route_b")], total_groups=3)
    top = out["top_routes_by_station_count"]
    assert top[0]["route_id"] == "route_b"
    assert top[0]["assigned_station_count"] == 100
    assert top[1]["route_id"] == "route_a"
    assert top[1]["assigned_station_count"] == 20


# ── D. Overuse detection ─────────────────────────────────────────────────────


def test_overuse_flags_route_above_threshold() -> None:
    matches = [_match("route_a") for _ in range(15)] + [_match("route_b") for _ in range(2)]
    catalog = [_route("route_a"), _route("route_b")]
    out = compute_coverage_sanity(matches, catalog, total_groups=58, overuse_min_count=5, overuse_share_pct=0.25)
    overuse_ids = [r["route_id"] for r in out["suspicious_overuse_routes"]]
    # Threshold = max(5, int(58*0.25)) = max(5, 14) = 14
    assert overuse_ids == ["route_a"]
    assert "route_overuse_detected" in " ".join(out["warnings"])


def test_overuse_route_carries_role_and_counts() -> None:
    matches = [_match("route_a") for _ in range(15)]
    catalog = [_route("route_a", role="underground_cable")]
    out = compute_coverage_sanity(matches, catalog, total_groups=58)
    suspicious = out["suspicious_overuse_routes"][0]
    assert suspicious["route_role"] == "underground_cable"
    assert suspicious["assigned_group_count"] == 15
    assert suspicious["assigned_station_count"] == 75  # 15 groups * 5 station_points


# ── E. Corpus collapse detection ─────────────────────────────────────────────


def test_collapse_detected_when_top5_holds_above_threshold_share() -> None:
    # Simulate the "4-5 routes absorbing 500 stations" failure mode:
    # 50 groups onto 4 distinct routes
    matches = (
        [_match("route_a") for _ in range(15)]
        + [_match("route_b") for _ in range(15)]
        + [_match("route_c") for _ in range(10)]
        + [_match("route_d") for _ in range(10)]
    )
    catalog = [_route(f"route_{c}") for c in "abcd"]
    out = compute_coverage_sanity(matches, catalog, total_groups=58)
    assert out["corpus_collapse_detected"] is True
    assert "corpus_collapse_detected" in " ".join(out["warnings"])


def test_collapse_not_detected_for_distributed_corpus() -> None:
    # 58 groups onto 30 distinct routes
    matches = [_match(f"route_{i}") for i in range(58)]
    catalog = [_route(f"route_{i}") for i in range(58)]
    out = compute_coverage_sanity(matches, catalog, total_groups=58)
    assert out["corpus_collapse_detected"] is False


def test_low_route_diversity_warning_fires() -> None:
    matches = [_match("route_a") for _ in range(30)] + [_match("route_b") for _ in range(20)]
    catalog = [_route("route_a"), _route("route_b")]
    out = compute_coverage_sanity(matches, catalog, total_groups=58)
    joined = " ".join(out["warnings"])
    assert "low_route_diversity" in joined


# ── F. Threshold kwargs configurability ──────────────────────────────────────


def test_overuse_thresholds_are_configurable_via_kwargs() -> None:
    matches = [_match("route_a") for _ in range(6)]
    catalog = [_route("route_a")]
    out_strict = compute_coverage_sanity(matches, catalog, total_groups=10, overuse_min_count=3, overuse_share_pct=0.10)
    assert len(out_strict["suspicious_overuse_routes"]) == 1
    out_lax = compute_coverage_sanity(matches, catalog, total_groups=10, overuse_min_count=10, overuse_share_pct=0.50)
    assert len(out_lax["suspicious_overuse_routes"]) == 0


# ── G. Same-route anchor collision detection ─────────────────────────────────


def _route_with_coords(route_id: str, role: str = "underground_cable") -> dict:
    # Straight east-west polyline at Brenham latitude, ~6900 ft long.
    return {
        "route_id": route_id,
        "route_name": f"Route {route_id}",
        "route_role": role,
        "source_folder": "Connections / underground cable",
        "coords": [(-96.39, 30.15), (-96.37, 30.15)],
    }


def _segment_with_coords(route_id: str, lat_lon_pairs: list) -> dict:
    # Frontend [lat, lon] order — matches what the engine actually emits.
    return {
        "route_id": route_id,
        "coords": [[lat, lon] for lon, lat in lat_lon_pairs],
        "source_file": "x.xlsx",
    }


def _match_with_segments(route_id: str, source_file: str, lon_lat_seg_endpoints: list,
                         station_min: float, station_max: float,
                         dates: list = ("2025-12-15",), crews: list = ("tx1-4",),
                         render_allowed: bool = True) -> dict:
    # Build redline segments from lon-lat endpoint pairs.
    segments = []
    for (lon1, lat1, lon2, lat2) in lon_lat_seg_endpoints:
        segments.append({
            "route_id": route_id,
            "source_file": source_file,
            "coords": [[lat1, lon1], [lat2, lon2]],
        })
    station_points = []
    for d in dates:
        for c in crews:
            station_points.append({"date": d, "crew": c, "station_ft": station_min})
            station_points.append({"date": d, "crew": c, "station_ft": station_max})
    return {
        "route_id": route_id,
        "source_file": source_file,
        "render_allowed": render_allowed,
        "group_redline_segments": segments,
        "group_station_points": station_points,
        "_normalized_group": {
            "min_station_ft": station_min,
            "max_station_ft": station_max,
            "span_ft": station_max - station_min,
        },
    }


def test_collision_detected_for_overlapping_groups_on_same_route() -> None:
    # bore_log29 / bore_log30 pattern: both groups span similar route-offset
    # range from the same anchor.
    catalog = [_route_with_coords("route_x")]
    match_a = _match_with_segments(
        "route_x", "bore_log_a.xlsx",
        lon_lat_seg_endpoints=[(-96.390, 30.150, -96.388, 30.150),
                                (-96.388, 30.150, -96.386, 30.150)],
        station_min=0.0, station_max=415.0, dates=["2025-12-15"], crews=["tx1-4"],
    )
    match_b = _match_with_segments(
        "route_x", "bore_log_b.xlsx",
        lon_lat_seg_endpoints=[(-96.390, 30.150, -96.388, 30.150),
                                (-96.388, 30.150, -96.385, 30.150)],
        station_min=0.0, station_max=500.0, dates=["2025-12-17"], crews=["tx1-4"],
    )
    out = compute_coverage_sanity([match_a, match_b], catalog, total_groups=2)
    assert out["same_route_anchor_collision_detected"] is True
    assert len(out["same_route_anchor_collisions"]) == 1
    c = out["same_route_anchor_collisions"][0]
    assert c["route_id"] == "route_x"
    assert set(c["source_files"]) == {"bore_log_a.xlsx", "bore_log_b.xlsx"}
    assert c["overlap_ratio"] >= 0.50


def test_no_collision_for_groups_on_different_routes() -> None:
    catalog = [_route_with_coords("route_x"), _route_with_coords("route_y")]
    match_a = _match_with_segments(
        "route_x", "f1.xlsx",
        lon_lat_seg_endpoints=[(-96.390, 30.150, -96.388, 30.150)],
        station_min=0.0, station_max=415.0,
    )
    match_b = _match_with_segments(
        "route_y", "f2.xlsx",
        lon_lat_seg_endpoints=[(-96.390, 30.150, -96.388, 30.150)],
        station_min=0.0, station_max=415.0,
    )
    out = compute_coverage_sanity([match_a, match_b], catalog, total_groups=2)
    assert out["same_route_anchor_collision_detected"] is False
    assert out["same_route_anchor_collisions"] == []


def test_no_collision_for_non_overlapping_ranges_on_same_route() -> None:
    catalog = [_route_with_coords("route_x")]
    match_a = _match_with_segments(
        "route_x", "f_left.xlsx",
        lon_lat_seg_endpoints=[(-96.390, 30.150, -96.388, 30.150)],
        station_min=0.0, station_max=415.0,
    )
    match_b = _match_with_segments(
        "route_x", "f_right.xlsx",
        lon_lat_seg_endpoints=[(-96.372, 30.150, -96.370, 30.150)],
        station_min=0.0, station_max=415.0,
    )
    out = compute_coverage_sanity([match_a, match_b], catalog, total_groups=2)
    assert out["same_route_anchor_collision_detected"] is False
    assert out["same_route_anchor_collisions"] == []


def test_collision_record_carries_all_required_fields() -> None:
    catalog = [_route_with_coords("route_x")]
    match_a = _match_with_segments(
        "route_x", "bore_log29.xlsx",
        lon_lat_seg_endpoints=[(-96.390, 30.150, -96.387, 30.150)],
        station_min=0.0, station_max=415.0, dates=["2025-12-15"], crews=["tx1-4"],
    )
    match_b = _match_with_segments(
        "route_x", "bore_log30.xlsx",
        lon_lat_seg_endpoints=[(-96.390, 30.150, -96.387, 30.150)],
        station_min=0.0, station_max=500.0, dates=["2025-12-17"], crews=["tx1-4"],
    )
    out = compute_coverage_sanity([match_a, match_b], catalog, total_groups=2)
    c = out["same_route_anchor_collisions"][0]
    required = {"route_id", "route_name", "route_role", "source_folder",
                "source_files", "overlap_ratio", "overlap_ft", "group_ranges",
                "station_ranges", "dates", "crews", "warning"}
    assert required.issubset(c.keys())
    assert c["route_role"] == "underground_cable"
    assert isinstance(c["overlap_ratio"], float)
    assert isinstance(c["overlap_ft"], float)
    assert len(c["group_ranges"]) == 2
    assert len(c["station_ranges"]) == 2
    assert len(c["dates"]) == 2
    assert len(c["crews"]) == 2


def test_collision_warning_appears_in_warnings_list() -> None:
    catalog = [_route_with_coords("route_x")]
    match_a = _match_with_segments(
        "route_x", "a.xlsx",
        lon_lat_seg_endpoints=[(-96.390, 30.150, -96.388, 30.150)],
        station_min=0.0, station_max=415.0,
    )
    match_b = _match_with_segments(
        "route_x", "b.xlsx",
        lon_lat_seg_endpoints=[(-96.390, 30.150, -96.388, 30.150)],
        station_min=0.0, station_max=500.0,
    )
    out = compute_coverage_sanity([match_a, match_b], catalog, total_groups=2)
    joined = " ".join(out["warnings"])
    assert "same_route_anchor_collision_detected" in joined


def test_collision_threshold_kwarg_is_configurable() -> None:
    catalog = [_route_with_coords("route_x")]
    # Two groups whose projections overlap ~30% — below default 0.50 but
    # above a stricter 0.20.
    match_a = _match_with_segments(
        "route_x", "f1.xlsx",
        lon_lat_seg_endpoints=[(-96.390, 30.150, -96.385, 30.150)],
        station_min=0.0, station_max=1574.0,
    )
    match_b = _match_with_segments(
        "route_x", "f2.xlsx",
        lon_lat_seg_endpoints=[(-96.386, 30.150, -96.380, 30.150)],
        station_min=0.0, station_max=1888.0,
    )
    out_default = compute_coverage_sanity([match_a, match_b], catalog, total_groups=2)
    out_strict = compute_coverage_sanity([match_a, match_b], catalog, total_groups=2,
                                          same_route_collision_threshold=0.10)
    # With default 0.50 threshold the overlap is below the bar → no collision
    assert out_default["same_route_anchor_collision_detected"] is False
    # With 0.10 threshold the small overlap is flagged
    assert out_strict["same_route_anchor_collision_detected"] is True


def test_collision_skips_groups_with_no_segments() -> None:
    catalog = [_route_with_coords("route_x")]
    match_a = _match_with_segments(
        "route_x", "a.xlsx",
        lon_lat_seg_endpoints=[(-96.390, 30.150, -96.388, 30.150)],
        station_min=0.0, station_max=415.0,
    )
    match_b = _match("route_x", station_points=3, source_file="b.xlsx")  # legacy shape, no segments
    out = compute_coverage_sanity([match_a, match_b], catalog, total_groups=2)
    assert out["same_route_anchor_collision_detected"] is False


def test_collision_skips_routes_with_no_coords() -> None:
    catalog = [_route("route_x")]  # no coords
    match_a = _match_with_segments(
        "route_x", "a.xlsx",
        lon_lat_seg_endpoints=[(-96.390, 30.150, -96.388, 30.150)],
        station_min=0.0, station_max=415.0,
    )
    match_b = _match_with_segments(
        "route_x", "b.xlsx",
        lon_lat_seg_endpoints=[(-96.390, 30.150, -96.388, 30.150)],
        station_min=0.0, station_max=500.0,
    )
    out = compute_coverage_sanity([match_a, match_b], catalog, total_groups=2)
    assert out["same_route_anchor_collision_detected"] is False


def test_existing_schema_fields_preserved() -> None:
    # Smoke regression: legacy callers still receive every coverage-sanity-1
    # field plus the new collision fields.
    matches = [_match("route_a"), _match("route_b")]
    out = compute_coverage_sanity(matches, [_route("route_a"), _route("route_b")], total_groups=2)
    for legacy_key in ("total_groups", "placed_group_count", "abstained_group_count",
                        "matched_route_count", "diversity_ratio",
                        "top_routes_by_group_count", "top_routes_by_station_count",
                        "suspicious_overuse_routes", "overuse_threshold_count",
                        "top5_share_of_placed", "top5_collapse_threshold",
                        "corpus_collapse_detected", "warnings"):
        assert legacy_key in out, f"missing legacy key {legacy_key!r}"
    for new_key in ("same_route_anchor_collision_threshold",
                     "same_route_anchor_collision_detected",
                     "same_route_anchor_collisions"):
        assert new_key in out, f"missing new key {new_key!r}"


# ── H. Collision Window V2 — Station-Frame Distinctness Override ─────────────
#
# Env gate: TRUELINE_SAME_ROUTE_WINDOW_OWNERSHIP=1
# Behavior: when ON, projected-overlap pairs whose station-frame overlap
# is below the distinctness floor (default 0.10) are reclassified as
# "allow_both_distinct_station_windows" and dropped from
# same_route_anchor_collisions. New diagnostic key
# same_route_window_decisions records every projected-overlap pair.
# Tests pass `station_distinctness_floor=0.10` as an explicit kwarg so
# they do not depend on os.environ state.


def _pair_with_proj_overlap_one(route_id: str, sf_a: str, sf_b: str,
                                 a_station: tuple, b_station: tuple) -> tuple:
    """Build a matched-pair with projected_overlap_ratio=1.0 on a shared
    KMZ window, parameterizing each group's station-frame range.

    Both groups draw two identical segments at lon (-96.390 .. -96.388)
    on a route polyline at (-96.39, 30.15) -> (-96.37, 30.15). Their
    projected route_offset_ranges are nearly identical (~6312 ft span on
    a ~6312 ft route), so overlap_ratio ~= 1.0 under the 0.50 default.
    """
    match_a = _match_with_segments(
        route_id, sf_a,
        lon_lat_seg_endpoints=[(-96.390, 30.150, -96.388, 30.150)],
        station_min=a_station[0], station_max=a_station[1],
        dates=["2025-12-15"], crews=["tx1-4"],
    )
    match_b = _match_with_segments(
        route_id, sf_b,
        lon_lat_seg_endpoints=[(-96.390, 30.150, -96.388, 30.150)],
        station_min=b_station[0], station_max=b_station[1],
        dates=["2025-12-17"], crews=["tx1-4"],
    )
    return match_a, match_b


def test_window_override_flag_off_preserves_legacy_output_byte_identically() -> None:
    catalog = [_route_with_coords("route_x")]
    match_a, match_b = _pair_with_proj_overlap_one(
        "route_x", "a.xlsx", "b.xlsx",
        a_station=(0.0, 100.0), b_station=(500.0, 600.0),  # disjoint station-frame
    )
    legacy = compute_coverage_sanity([match_a, match_b], catalog, total_groups=2)
    # Schema preserved
    assert legacy["schema"] == "coverage-sanity-2"
    # Legacy collision present (would have been allow_both under override)
    assert legacy["same_route_anchor_collision_detected"] is True
    assert len(legacy["same_route_anchor_collisions"]) == 1
    # Override-only keys absent
    assert "same_route_window_decisions" not in legacy
    assert "same_route_window_distinctness_floor" not in legacy


def test_window_override_proj_one_station_zero_allows_both() -> None:
    catalog = [_route_with_coords("route_x")]
    match_a, match_b = _pair_with_proj_overlap_one(
        "route_x", "log_left.xlsx", "log_right.xlsx",
        a_station=(0.0, 100.0), b_station=(500.0, 600.0),  # station overlap = 0
    )
    out = compute_coverage_sanity([match_a, match_b], catalog, total_groups=2,
                                   station_distinctness_floor=0.10)
    # Schema bumped
    assert out["schema"] == "coverage-sanity-3"
    assert out["same_route_window_distinctness_floor"] == 0.10
    # Pair is suppressed from collisions
    assert out["same_route_anchor_collision_detected"] is False
    assert out["same_route_anchor_collisions"] == []
    # Decision record emitted
    decisions = out["same_route_window_decisions"]
    assert len(decisions) == 1
    d = decisions[0]
    assert d["decision"] == "allow_both_distinct_station_windows"
    assert d["reason"] == "station_overlap_below_distinctness_floor"
    assert d["projected_overlap_ratio"] >= 0.50
    assert d["station_overlap_ft"] == 0.0
    assert d["station_overlap_ratio"] == 0.0
    assert set(d["source_files"]) == {"log_left.xlsx", "log_right.xlsx"}
    # kept_group / abstained_group are null at coverage_sanity time
    assert d["kept_group"] is None
    assert d["abstained_group"] is None


def test_window_override_proj_one_station_eighty_keeps_collision() -> None:
    catalog = [_route_with_coords("route_x")]
    # Station ranges 0-100 and 20-120 -> overlap_ft = 80, shorter span = 100,
    # station_overlap_ratio = 0.80
    match_a, match_b = _pair_with_proj_overlap_one(
        "route_x", "log_overlap_a.xlsx", "log_overlap_b.xlsx",
        a_station=(0.0, 100.0), b_station=(20.0, 120.0),
    )
    out = compute_coverage_sanity([match_a, match_b], catalog, total_groups=2,
                                   station_distinctness_floor=0.10)
    assert out["schema"] == "coverage-sanity-3"
    # Collision retained
    assert out["same_route_anchor_collision_detected"] is True
    assert len(out["same_route_anchor_collisions"]) == 1
    # Decision record shows abstain_loser / true_window_overlap
    decisions = out["same_route_window_decisions"]
    assert len(decisions) == 1
    d = decisions[0]
    assert d["decision"] == "abstain_loser"
    assert d["reason"] == "true_window_overlap"
    assert d["station_overlap_ratio"] == 0.8
    assert d["station_overlap_ft"] == 80.0


def test_window_override_missing_station_metadata_keeps_collision() -> None:
    catalog = [_route_with_coords("route_x")]
    match_a, match_b = _pair_with_proj_overlap_one(
        "route_x", "with_meta.xlsx", "no_meta.xlsx",
        a_station=(0.0, 100.0), b_station=(0.0, 100.0),
    )
    # Strip station metadata from match_b's _normalized_group so the
    # override falls through to current abstain behavior.
    match_b["_normalized_group"] = {
        "min_station_ft": None,
        "max_station_ft": None,
        "span_ft": None,
    }
    out = compute_coverage_sanity([match_a, match_b], catalog, total_groups=2,
                                   station_distinctness_floor=0.10)
    assert out["schema"] == "coverage-sanity-3"
    # Collision retained (fail-safe to abstain)
    assert out["same_route_anchor_collision_detected"] is True
    assert len(out["same_route_anchor_collisions"]) == 1
    decisions = out["same_route_window_decisions"]
    assert len(decisions) == 1
    d = decisions[0]
    assert d["decision"] == "abstain_loser"
    assert d["reason"] == "station_metadata_unavailable"
    assert d["station_overlap_ft"] is None
    assert d["station_overlap_ratio"] is None


def test_window_override_station_ratio_exactly_at_floor_keeps_collision() -> None:
    catalog = [_route_with_coords("route_x")]
    # Station ranges 0-100 and 90-190 -> overlap_ft = 10, shorter span = 100,
    # station_overlap_ratio = 0.10 exactly. Floor is 0.10. Strict less-than
    # comparison -> 0.10 is NOT below floor -> keeps collision.
    match_a, match_b = _pair_with_proj_overlap_one(
        "route_x", "edge_a.xlsx", "edge_b.xlsx",
        a_station=(0.0, 100.0), b_station=(90.0, 190.0),
    )
    out = compute_coverage_sanity([match_a, match_b], catalog, total_groups=2,
                                   station_distinctness_floor=0.10)
    assert out["schema"] == "coverage-sanity-3"
    # Collision retained — exactly at floor is NOT "below"
    assert out["same_route_anchor_collision_detected"] is True
    assert len(out["same_route_anchor_collisions"]) == 1
    decisions = out["same_route_window_decisions"]
    assert len(decisions) == 1
    d = decisions[0]
    assert d["decision"] == "abstain_loser"
    assert d["reason"] == "true_window_overlap"
    assert d["station_overlap_ratio"] == 0.1
