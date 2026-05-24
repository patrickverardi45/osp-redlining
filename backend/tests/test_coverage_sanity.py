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
