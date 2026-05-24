"""Tests for backend/app/core/route_collision_resolver.py.

Pure unit tests against the deterministic tie-breaker + cluster
arbitration logic. The resolver is a read-only pure function — it never
mutates inputs and never invokes any I/O.
"""

from __future__ import annotations

import copy
import os

os.environ.setdefault("TRUELINE_JWT_SECRET", "rcr-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "rcr-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend.app.core.route_collision_resolver import resolve_route_collisions


def _diag(source_file: str, *, confidence: float = 0.20, top1_score: float = 0.50,
          notes_streets: list = (), mismatch: bool = False,
          expansion_route_id: str = "") -> dict:
    out = {
        "source_file": source_file,
        "evidence_resolver": {
            "confidence": confidence,
            "decision_basis": {"top1_score": top1_score},
            "notes_streets": list(notes_streets),
        },
    }
    if mismatch:
        out["location_evidence_mismatch"] = {
            "notes_streets": list(notes_streets) or ["X"],
            "filter_streets": ["Y"],
            "severity": "REVIEW",
            "source": "test",
        }
    if expansion_route_id:
        out["auto_candidate_expansion"] = {
            "source": "test",
            "discovered_route_ids": [expansion_route_id],
            "selected_candidate_route_id": expansion_route_id,
            "evidence": {},
        }
    return out


def _match(source_file: str, route_id: str, route_name: str = "Test Route",
           *, render_allowed: bool = True, dates: list = ("2025-12-15",),
           crews: list = ("tx1-4",)) -> dict:
    station_points = []
    for d in dates:
        for c in crews:
            station_points.append({"date": d, "crew": c, "station_ft": 0.0})
    return {
        "source_file": source_file,
        "route_id": route_id,
        "route_name": route_name,
        "render_allowed": render_allowed,
        "group_station_points": station_points,
        "group_redline_segments": [{"coords": [[30.15, -96.39], [30.15, -96.38]]}],
    }


def _collision(route_id: str, sf_a: str, sf_b: str,
                overlap_ft: float = 415.0, overlap_ratio: float = 1.0,
                route_name: str = "Test Route") -> dict:
    return {
        "route_id": route_id,
        "route_name": route_name,
        "route_role": "underground_cable",
        "source_files": [sf_a, sf_b],
        "overlap_ft": overlap_ft,
        "overlap_ratio": overlap_ratio,
    }


# ── A. No-op cases ───────────────────────────────────────────────────────────


def test_empty_collisions_returns_empty_resolution() -> None:
    out = resolve_route_collisions([], [], [])
    assert out["abstained_source_files"] == []
    assert out["per_source_file_abstain_reason"] == {}
    assert out["collision_resolutions"] == []


def test_collision_on_groups_not_in_matches_skipped() -> None:
    # Collision references source_files that don't appear in group_matches
    collisions = [_collision("route_x", "missing_a.xlsx", "missing_b.xlsx")]
    out = resolve_route_collisions([], [], collisions)
    assert out["abstained_source_files"] == []


# ── B. Two-way collision: higher confidence wins ─────────────────────────────


def test_higher_confidence_wins_two_way_collision() -> None:
    matches = [
        _match("low.xlsx", "route_x"),
        _match("high.xlsx", "route_x"),
    ]
    diags = [
        _diag("low.xlsx", confidence=0.20, top1_score=0.30),
        _diag("high.xlsx", confidence=0.80, top1_score=0.30),
    ]
    collisions = [_collision("route_x", "low.xlsx", "high.xlsx")]
    out = resolve_route_collisions(matches, diags, collisions)
    assert out["abstained_source_files"] == ["low.xlsx"]
    assert "low.xlsx" in out["per_source_file_abstain_reason"]
    reason = out["per_source_file_abstain_reason"]["low.xlsx"]
    assert reason["reason"] == "same_route_anchor_collision"
    assert reason["route_id"] == "route_x"
    assert reason["kept_source_file"] == "high.xlsx"
    assert reason["kept_confidence"] == 0.80
    assert set(reason["collision_source_files"]) == {"low.xlsx", "high.xlsx"}


def test_tiebreaker_falls_through_to_top1_score_when_confidence_equal() -> None:
    matches = [
        _match("a.xlsx", "route_x"),
        _match("b.xlsx", "route_x"),
    ]
    diags = [
        _diag("a.xlsx", confidence=0.30, top1_score=0.10),
        _diag("b.xlsx", confidence=0.30, top1_score=0.55),  # wins on top1
    ]
    collisions = [_collision("route_x", "a.xlsx", "b.xlsx")]
    out = resolve_route_collisions(matches, diags, collisions)
    assert out["abstained_source_files"] == ["a.xlsx"]


def test_tiebreaker_location_evidence_match_beats_no_match() -> None:
    matches = [
        _match("nomatch.xlsx", "route_x"),
        _match("haslocmatch.xlsx", "route_x"),
    ]
    diags = [
        _diag("nomatch.xlsx", confidence=0.30, top1_score=0.30),
        _diag("haslocmatch.xlsx", confidence=0.30, top1_score=0.30,
              notes_streets=["LAWNDALE AVE"], expansion_route_id="route_x"),
    ]
    collisions = [_collision("route_x", "nomatch.xlsx", "haslocmatch.xlsx")]
    out = resolve_route_collisions(matches, diags, collisions)
    assert out["abstained_source_files"] == ["nomatch.xlsx"]


def test_tiebreaker_earliest_date_when_same_crew() -> None:
    matches = [
        _match("later.xlsx", "route_x", dates=["2025-12-17"], crews=["tx1-4"]),
        _match("earlier.xlsx", "route_x", dates=["2025-12-15"], crews=["tx1-4"]),
    ]
    diags = [
        _diag("later.xlsx", confidence=0.30, top1_score=0.30),
        _diag("earlier.xlsx", confidence=0.30, top1_score=0.30),
    ]
    collisions = [_collision("route_x", "later.xlsx", "earlier.xlsx")]
    out = resolve_route_collisions(matches, diags, collisions)
    assert out["abstained_source_files"] == ["later.xlsx"]


def test_tiebreaker_final_source_file_lexical_order() -> None:
    matches = [
        _match("z.xlsx", "route_x", dates=["2025-12-15"], crews=["tx1-4"]),
        _match("a.xlsx", "route_x", dates=["2025-12-15"], crews=["tx1-4"]),
    ]
    diags = [
        _diag("z.xlsx", confidence=0.30, top1_score=0.30),
        _diag("a.xlsx", confidence=0.30, top1_score=0.30),
    ]
    collisions = [_collision("route_x", "z.xlsx", "a.xlsx")]
    out = resolve_route_collisions(matches, diags, collisions)
    # a.xlsx wins lexically; z.xlsx abstained
    assert out["abstained_source_files"] == ["z.xlsx"]


# ── C. Multi-way collision clusters ──────────────────────────────────────────


def test_three_way_cluster_keeps_one_abstains_two() -> None:
    matches = [
        _match(f"f{i}.xlsx", "route_x") for i in range(3)
    ]
    diags = [
        _diag("f0.xlsx", confidence=0.10),
        _diag("f1.xlsx", confidence=0.50),  # winner
        _diag("f2.xlsx", confidence=0.20),
    ]
    # Pairwise collisions forming a triangle (transitively connected)
    collisions = [
        _collision("route_x", "f0.xlsx", "f1.xlsx"),
        _collision("route_x", "f1.xlsx", "f2.xlsx"),
        _collision("route_x", "f0.xlsx", "f2.xlsx"),
    ]
    out = resolve_route_collisions(matches, diags, collisions)
    assert set(out["abstained_source_files"]) == {"f0.xlsx", "f2.xlsx"}
    res = out["collision_resolutions"][0]
    assert res["kept_source_file"] == "f1.xlsx"
    assert res["cluster_size"] == 3


def test_two_disjoint_clusters_on_same_route_resolve_independently() -> None:
    # 4 groups on route_x: {a,b} overlap each other; {c,d} overlap each other;
    # a/b don't overlap c/d
    matches = [_match(sf, "route_x") for sf in ("a.xlsx", "b.xlsx", "c.xlsx", "d.xlsx")]
    diags = [
        _diag("a.xlsx", confidence=0.60),
        _diag("b.xlsx", confidence=0.30),
        _diag("c.xlsx", confidence=0.20),
        _diag("d.xlsx", confidence=0.70),
    ]
    collisions = [
        _collision("route_x", "a.xlsx", "b.xlsx"),
        _collision("route_x", "c.xlsx", "d.xlsx"),
    ]
    out = resolve_route_collisions(matches, diags, collisions)
    # b is abstained (a wins cluster 1); c is abstained (d wins cluster 2)
    assert set(out["abstained_source_files"]) == {"b.xlsx", "c.xlsx"}


# ── D. Cross-route safety ────────────────────────────────────────────────────


def test_collisions_on_different_routes_resolve_independently() -> None:
    matches = [
        _match("a.xlsx", "route_x"),
        _match("b.xlsx", "route_x"),
        _match("c.xlsx", "route_y"),
        _match("d.xlsx", "route_y"),
    ]
    diags = [
        _diag("a.xlsx", confidence=0.80),
        _diag("b.xlsx", confidence=0.20),
        _diag("c.xlsx", confidence=0.30),
        _diag("d.xlsx", confidence=0.70),
    ]
    collisions = [
        _collision("route_x", "a.xlsx", "b.xlsx"),
        _collision("route_y", "c.xlsx", "d.xlsx"),
    ]
    out = resolve_route_collisions(matches, diags, collisions)
    assert set(out["abstained_source_files"]) == {"b.xlsx", "c.xlsx"}


# ── E. render_allowed=False groups are excluded ──────────────────────────────


def test_already_unallowed_match_excluded_from_resolution() -> None:
    # If a match already has render_allowed=False, the resolver must not
    # count it as part of the cluster, and must not abstain anything else
    # based on a collision with it.
    matches = [
        _match("a.xlsx", "route_x", render_allowed=True),
        _match("b.xlsx", "route_x", render_allowed=False),
    ]
    diags = [
        _diag("a.xlsx", confidence=0.20),
        _diag("b.xlsx", confidence=0.90),
    ]
    collisions = [_collision("route_x", "a.xlsx", "b.xlsx")]
    out = resolve_route_collisions(matches, diags, collisions)
    # Cluster has only 1 placed group (a) → no collision to resolve
    assert out["abstained_source_files"] == []


# ── F. Reason payload completeness ───────────────────────────────────────────


def test_abstain_reason_has_all_required_fields() -> None:
    matches = [_match("a.xlsx", "route_477", route_name="Underground Cable"),
               _match("b.xlsx", "route_477", route_name="Underground Cable")]
    diags = [_diag("a.xlsx", confidence=0.30),
              _diag("b.xlsx", confidence=0.50)]
    collisions = [_collision("route_477", "a.xlsx", "b.xlsx",
                             overlap_ft=415.0, overlap_ratio=0.98,
                             route_name="Underground Cable")]
    out = resolve_route_collisions(matches, diags, collisions)
    reason = out["per_source_file_abstain_reason"]["a.xlsx"]
    for key in ("reason", "route_id", "route_name", "overlap_ratio",
                "overlap_ft", "kept_source_file", "kept_confidence",
                "collision_source_files"):
        assert key in reason, f"missing reason field {key!r}"
    assert reason["reason"] == "same_route_anchor_collision"
    assert reason["route_id"] == "route_477"
    assert reason["route_name"] == "Underground Cable"
    assert reason["overlap_ft"] == 415.0
    assert reason["overlap_ratio"] == 0.98
    assert reason["kept_source_file"] == "b.xlsx"
    assert reason["kept_confidence"] == 0.50


# ── G. Mutation safety ───────────────────────────────────────────────────────


def test_resolver_does_not_mutate_inputs() -> None:
    matches = [_match("a.xlsx", "route_x"), _match("b.xlsx", "route_x")]
    diags = [_diag("a.xlsx", confidence=0.20), _diag("b.xlsx", confidence=0.80)]
    collisions = [_collision("route_x", "a.xlsx", "b.xlsx")]
    matches_snap = copy.deepcopy(matches)
    diags_snap = copy.deepcopy(diags)
    collisions_snap = copy.deepcopy(collisions)
    _ = resolve_route_collisions(matches, diags, collisions)
    assert matches == matches_snap
    assert diags == diags_snap
    assert collisions == collisions_snap


# ── H. bore_log29 / bore_log30 production scenario ──────────────────────────


def test_bore_log_29_30_collision_pattern() -> None:
    # Mirror the actual production-parity data for bore_log29 + bore_log30
    # on route_477:
    #   bore_log29: confidence 0.2427, top1 0.1120
    #   bore_log30: confidence 0.2481, top1 0.1145
    #   collision: overlap_ft ~415, ratio 1.0
    matches = [
        _match("bore_log29.xlsx", "route_477", route_name="Underground Cable",
               dates=["2025-12-15"], crews=["tx1-4"]),
        _match("bore_log30.xlsx", "route_477", route_name="Underground Cable",
               dates=["2025-12-17"], crews=["tx1-4"]),
    ]
    diags = [
        _diag("bore_log29.xlsx", confidence=0.2427, top1_score=0.1120),
        _diag("bore_log30.xlsx", confidence=0.2481, top1_score=0.1145),
    ]
    collisions = [_collision("route_477", "bore_log29.xlsx", "bore_log30.xlsx",
                              overlap_ft=415.0, overlap_ratio=1.0,
                              route_name="Underground Cable")]
    out = resolve_route_collisions(matches, diags, collisions)
    # bore_log30 has marginally higher confidence (0.2481 > 0.2427)
    assert out["abstained_source_files"] == ["bore_log29.xlsx"]
    res = out["collision_resolutions"][0]
    assert res["kept_source_file"] == "bore_log30.xlsx"
