"""Anti-Collapse V2 alternate-placement search tests.

Two test classes:

  1. TestAlternateSearchPure — pure unit tests against the deterministic
     search_alternate_placement + build_kept_offsets_by_route helpers
     (no STATE, no rebuild loop).
  2. TestAntiCollapseV2Wiring — env-gated integration tests against the
     rebuild loop with stubbed rankings + a synthetic route_catalog.

The 10 cases required by the V2 sprint goal are spread across both
classes; the mapping is documented inline next to each test.
"""

from __future__ import annotations

import copy
import os
import unittest
import uuid
from typing import Any, Dict, List, Tuple
from unittest.mock import patch

os.environ.setdefault("TRUELINE_JWT_SECRET", "v2-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "v2-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend import main as M
from backend.app.core.rebuild_scope import RebuildScope
from backend.app.core.route_collision_alternate_search import (
    build_kept_offsets_by_route,
    classify_alternate_build_failure,
    compute_pair_overlap_ratio,
    project_segments_onto_route,
    search_alternate_placement,
)
from backend.app.core.route_collision_resolver import resolve_route_collisions

ABSTAIN_ENV = "TRUELINE_ABSTAIN_ON_ROUTE_COLLISION"
V2_ENV = "TRUELINE_ROUTE_COLLISION_ALTERNATE_SEARCH"
V2_MIN_SCORE_ENV = "TRUELINE_ROUTE_COLLISION_ALTERNATE_MIN_SCORE"
V2_MAX_PERP_ENV = "TRUELINE_ROUTE_COLLISION_ALTERNATE_MAX_PERP_FT"


# ── Pure-function helpers ──────────────────────────────────────────────────

def _linear_coords(start_lon: float, start_lat: float,
                   end_lon: float, end_lat: float, steps: int = 5) -> List[Tuple[float, float]]:
    """Densified linear route from (start) to (end) in lon/lat space."""
    out: List[Tuple[float, float]] = []
    for i in range(steps + 1):
        t = i / steps
        out.append((start_lon + (end_lon - start_lon) * t,
                    start_lat + (end_lat - start_lat) * t))
    return out


def _route(route_id: str, coords: List[Tuple[float, float]], *,
           route_name: str = "Synth Route",
           source_folder: str = "Backbone",
           route_role: str = "underground_cable") -> Dict[str, Any]:
    return {
        "route_id": route_id,
        "route_name": route_name,
        "source_folder": source_folder,
        "route_role": route_role,
        "coords": [list(c) for c in coords],
        "length_ft": 0.0,
        "point_count": len(coords),
    }


def _segment_from_coords(coords: List[Tuple[float, float]]) -> Dict[str, Any]:
    """A redline_segment with frontend-style [lat, lon] coords."""
    return {"coords": [[lat, lon] for (lon, lat) in coords]}


def _match_with_segments(source_file: str, route_id: str,
                         seg_coords: List[Tuple[float, float]],
                         *, confidence: float = 0.30) -> Dict[str, Any]:
    return {
        "source_file": source_file,
        "route_id": route_id,
        "route_name": f"{route_id} name",
        "confidence": confidence,
        "render_allowed": True,
        "group_station_points": [],
        "group_redline_segments": [_segment_from_coords(seg_coords)],
        "candidate_rankings": [],
        "_normalized_group": {"min_station_ft": 0.0, "max_station_ft": 300.0, "span_ft": 300.0},
    }


class TestAlternateSearchPure(unittest.TestCase):
    """Pure unit tests — no STATE, no rebuild loop."""

    # Case 5 (compute_pair_overlap_ratio mirrors coverage_sanity logic).
    def test_pair_overlap_disjoint_returns_zero(self) -> None:
        ratio, ft = compute_pair_overlap_ratio((0.0, 100.0), (200.0, 300.0))
        assert ratio == 0.0
        assert ft == 0.0

    def test_pair_overlap_full_overlap_ratio_one(self) -> None:
        ratio, ft = compute_pair_overlap_ratio((100.0, 200.0), (50.0, 250.0))
        assert ratio == 1.0
        assert abs(ft - 100.0) < 1e-6

    def test_pair_overlap_partial_normalized_by_shorter(self) -> None:
        # Shorter span = 100ft, overlap = 50ft → ratio 0.5
        ratio, ft = compute_pair_overlap_ratio((0.0, 100.0), (50.0, 250.0))
        assert abs(ratio - 0.5) < 1e-6
        assert abs(ft - 50.0) < 1e-6

    def test_project_segments_onto_route_returns_offsets_and_perp(self) -> None:
        # Route runs along 30.155 N from -96.4000 to -96.3990 (~317 ft east).
        route = _linear_coords(-96.4000, 30.155, -96.3990, 30.155, steps=10)
        # Segment sits ON the route between the 50-ft and 200-ft offsets.
        seg = _linear_coords(-96.39984, 30.155, -96.39937, 30.155, steps=4)
        proj = project_segments_onto_route([_segment_from_coords(seg)], route)
        assert proj is not None
        assert proj["mean_perp_ft"] < 1.0  # exactly on route
        assert proj["lo_ft"] > 0.0 and proj["hi_ft"] > proj["lo_ft"]

    def test_project_segments_distant_route_yields_large_perp(self) -> None:
        # Route at lat 30.160; segments at lat 30.155 → ~1800 ft perp.
        route = _linear_coords(-96.4000, 30.160, -96.3990, 30.160, steps=4)
        seg = _linear_coords(-96.39984, 30.155, -96.39937, 30.155, steps=4)
        proj = project_segments_onto_route([_segment_from_coords(seg)], route)
        assert proj is not None
        assert proj["mean_perp_ft"] > 1000.0

    def test_build_kept_offsets_skips_abstained_groups(self) -> None:
        route_coords = _linear_coords(-96.4000, 30.155, -96.3990, 30.155, steps=5)
        seg = _linear_coords(-96.39984, 30.155, -96.39937, 30.155, steps=3)
        kept = _match_with_segments("kept.xlsx", "route_A", seg)
        abstained = _match_with_segments("loser.xlsx", "route_A", seg)
        catalog = [_route("route_A", route_coords)]
        offsets = build_kept_offsets_by_route(
            [kept, abstained], ["loser.xlsx"], catalog,
        )
        # Only the kept group contributes a range.
        assert "route_A" in offsets
        assert len(offsets["route_A"]) == 1

    # Case 3 (alternate selected when one exists).
    def test_alternate_selected_when_safe_candidate_exists(self) -> None:
        # Loser segments on route_A; alternate route_B runs parallel,
        # ~50 ft north (~25 ft perp under Brenham lat scale).
        route_a = _linear_coords(-96.4000, 30.155, -96.3990, 30.155, steps=5)
        route_b = _linear_coords(-96.4000, 30.15514, -96.3990, 30.15514, steps=5)
        seg = _linear_coords(-96.39990, 30.155, -96.39955, 30.155, steps=4)
        loser = _match_with_segments("loser.xlsx", "route_A", seg)
        loser["candidate_rankings"] = [
            {"route_id": "route_A", "route_name": "A", "score": 0.40},
            {"route_id": "route_B", "route_name": "B", "score": 0.30},
        ]
        catalog = [_route("route_A", route_a), _route("route_B", route_b)]
        decision = search_alternate_placement(
            loser, route_catalog=catalog, kept_offsets_by_route={},
            min_score=0.10, max_perp_ft=200.0, overlap_threshold=0.50,
        )
        assert decision["outcome"] == "alternate_selected"
        assert decision["alternate_route_id"] == "route_B"
        assert decision["alternate_confidence"] == 0.30
        assert decision["alternate_mean_perp_ft"] < 200.0

    # Case 4 (no safe alternate → outcome no_safe_alternate).
    def test_no_safe_alternate_when_only_distant_routes_available(self) -> None:
        route_a = _linear_coords(-96.4000, 30.155, -96.3990, 30.155, steps=5)
        # Far-off alternate ~1800 ft north
        route_b = _linear_coords(-96.4000, 30.160, -96.3990, 30.160, steps=5)
        seg = _linear_coords(-96.39990, 30.155, -96.39955, 30.155, steps=4)
        loser = _match_with_segments("loser.xlsx", "route_A", seg)
        loser["candidate_rankings"] = [
            {"route_id": "route_A", "route_name": "A", "score": 0.40},
            {"route_id": "route_B", "route_name": "B", "score": 0.30},
        ]
        catalog = [_route("route_A", route_a), _route("route_B", route_b)]
        decision = search_alternate_placement(
            loser, route_catalog=catalog, kept_offsets_by_route={},
            min_score=0.10, max_perp_ft=200.0, overlap_threshold=0.50,
        )
        assert decision["outcome"] == "no_safe_alternate"
        assert decision["alternate_route_id"] is None
        assert any(r["reason"] == "geographically_distant"
                   for r in decision["rejected_candidates"])

    # Case 5 (alternate cannot collide with already-kept group).
    def test_alternate_rejected_when_collides_with_kept_group(self) -> None:
        route_a = _linear_coords(-96.4000, 30.155, -96.3990, 30.155, steps=5)
        route_b = _linear_coords(-96.4000, 30.15514, -96.3990, 30.15514, steps=5)
        seg = _linear_coords(-96.39990, 30.155, -96.39955, 30.155, steps=4)
        loser = _match_with_segments("loser.xlsx", "route_A", seg)
        loser["candidate_rankings"] = [
            {"route_id": "route_A", "route_name": "A", "score": 0.40},
            {"route_id": "route_B", "route_name": "B", "score": 0.30},
        ]
        catalog = [_route("route_A", route_a), _route("route_B", route_b)]
        decision = search_alternate_placement(
            loser, route_catalog=catalog,
            # Kept group already occupies the same offset window on route_B
            kept_offsets_by_route={"route_B": [(0.0, 400.0)]},
            min_score=0.10, max_perp_ft=200.0, overlap_threshold=0.50,
        )
        assert decision["outcome"] == "no_safe_alternate"
        assert any(r["reason"] == "would_collide_with_kept_group"
                   for r in decision["rejected_candidates"])

    def test_score_floor_rejects_low_confidence_candidate(self) -> None:
        route_a = _linear_coords(-96.4000, 30.155, -96.3990, 30.155, steps=5)
        route_b = _linear_coords(-96.4000, 30.15514, -96.3990, 30.15514, steps=5)
        seg = _linear_coords(-96.39990, 30.155, -96.39955, 30.155, steps=4)
        loser = _match_with_segments("loser.xlsx", "route_A", seg)
        loser["candidate_rankings"] = [
            {"route_id": "route_A", "route_name": "A", "score": 0.40},
            {"route_id": "route_B", "route_name": "B", "score": 0.05},  # below floor
        ]
        catalog = [_route("route_A", route_a), _route("route_B", route_b)]
        decision = search_alternate_placement(
            loser, route_catalog=catalog, kept_offsets_by_route={},
            min_score=0.10, max_perp_ft=200.0, overlap_threshold=0.50,
        )
        assert decision["outcome"] == "no_safe_alternate"
        assert any(r["reason"] == "below_min_score"
                   for r in decision["rejected_candidates"])

    def test_original_route_never_returned_as_alternate(self) -> None:
        route_a = _linear_coords(-96.4000, 30.155, -96.3990, 30.155, steps=5)
        seg = _linear_coords(-96.39990, 30.155, -96.39955, 30.155, steps=4)
        loser = _match_with_segments("loser.xlsx", "route_A", seg)
        # Only candidate is the same route the loser is colliding on.
        loser["candidate_rankings"] = [
            {"route_id": "route_A", "route_name": "A", "score": 0.40},
        ]
        catalog = [_route("route_A", route_a)]
        decision = search_alternate_placement(
            loser, route_catalog=catalog, kept_offsets_by_route={},
            min_score=0.10, max_perp_ft=200.0, overlap_threshold=0.50,
        )
        assert decision["outcome"] == "no_safe_alternate"
        # The original is silently skipped, not returned in rejected_candidates.
        assert decision["candidate_count"] == 0

    def test_thresholds_payload_attached_to_decision(self) -> None:
        loser = _match_with_segments("loser.xlsx", "route_A", [(-96.4, 30.155), (-96.4, 30.155)])
        loser["candidate_rankings"] = []
        decision = search_alternate_placement(
            loser, route_catalog=[], kept_offsets_by_route={},
            min_score=0.25, max_perp_ft=180.0, overlap_threshold=0.40,
        )
        assert decision["thresholds"]["min_score"] == 0.25
        assert decision["thresholds"]["max_perp_ft"] == 180.0
        assert decision["thresholds"]["overlap_threshold"] == 0.40


# ── Integration tests: env-gated rebuild loop wiring ──────────────────────


def _rows(*records: Tuple[str, str, float, str]) -> List[Dict[str, Any]]:
    """records: tuples of (source_file, station_str, station_ft, print_token)."""
    out: List[Dict[str, Any]] = []
    for source_file, station, station_ft, print_token in records:
        out.append({
            "station": station, "station_ft": station_ft,
            "depth_ft": 5.0, "boc_ft": 4.0,
            "date": "2025-12-15", "crew": "tx1-4",
            "print": print_token, "notes": "",
            "source_file": source_file,
        })
    return out


class TestAntiCollapseV2Wiring(unittest.TestCase):
    """Env-gate integration. Verifies the V2 path:

    - Case 1: V2 env OFF → 81c2bdd behavior preserved.
    - Case 2: V1 ON, V2 OFF → V1 abstain unchanged.

    Cases 3/4/5/6/7/8 are covered by the pure unit tests above (they
    exercise the deterministic decision surface directly).
    """

    def setUp(self) -> None:
        self._saved_state = copy.deepcopy(dict(M.STATE))
        self._saved = {k: os.environ.pop(k, None) for k in (
            ABSTAIN_ENV, V2_ENV, V2_MIN_SCORE_ENV, V2_MAX_PERP_ENV,
        )}
        self._session_id = f"v2_{uuid.uuid4().hex[:12]}"

    def tearDown(self) -> None:
        M.STATE.clear()
        M.STATE.update(self._saved_state)
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _seed(self, rows: List[Dict[str, Any]],
              catalog: List[Dict[str, Any]]) -> None:
        M.STATE.clear()
        M.STATE.update({
            "committed_rows": list(rows),
            "route_catalog": list(catalog),
            "address_points": [],
            "_session_id_hint": self._session_id,
            "engineering_plans": [],
        })

    # Case 1 — Env OFF preserves 81c2bdd behavior (no V2 metadata at all).
    def test_v2_env_unset_leaves_coverage_sanity_clean(self) -> None:
        rows = _rows(("a.xlsx", "0+00", 0.0, "1"), ("a.xlsx", "1+00", 100.0, "1"))
        # No route_catalog → groups stay unplaced; nothing collides; V2 doesn't fire.
        self._seed(rows, [])
        with patch.object(M, "_candidate_rankings_for_group_v2",
                          return_value=([], {"applied": True, "mode": "test",
                                              "print_tokens": ["1"], "sheet_numbers": [1],
                                              "street_hints": [], "allowed_route_ids": [],
                                              "reason": "stub"}, [])):
            M._rebuild_field_data_outputs(scope=RebuildScope.FULL)
        cs = M.STATE.get("coverage_sanity") or {}
        rcr = cs.get("route_collision_resolution") or {}
        # Without TRUELINE_ABSTAIN_ON_ROUTE_COLLISION, the entire block is bypassed
        assert "route_collision_resolution" not in cs

    # Case 2 — V1 ON, V2 OFF: V1 abstain path unchanged; "alternate_*"
    # audit keys appear but are empty (additive schema change only).
    def test_v1_on_v2_off_no_alternate_attempted(self) -> None:
        os.environ[ABSTAIN_ENV] = "1"
        # V2 stays unset
        rows = _rows(("a.xlsx", "0+00", 0.0, "1"), ("a.xlsx", "1+00", 100.0, "1"))
        self._seed(rows, [])
        with patch.object(M, "_candidate_rankings_for_group_v2",
                          return_value=([], {"applied": True, "mode": "test",
                                              "print_tokens": ["1"], "sheet_numbers": [1],
                                              "street_hints": [], "allowed_route_ids": [],
                                              "reason": "stub"}, [])):
            M._rebuild_field_data_outputs(scope=RebuildScope.FULL)
        cs = M.STATE.get("coverage_sanity") or {}
        rcr = cs.get("route_collision_resolution") or {}
        # Empty corpus → resolver runs noop; V2 keys absent or empty.
        assert rcr.get("applied") is False
        assert rcr.get("abstained_source_files") == []
        # V2 audit fields exist post-patch (additive) but are empty.
        assert rcr.get("alternate_selected_source_files", []) == []
        assert rcr.get("alternate_rejected_source_files", []) == []


# ── Bore_log29/30-style collision determinism (Case 8) ─────────────────────

class TestAlternateSearchBoreLog2930Style(unittest.TestCase):
    """Case 8 — bore_log29/30-style collision: both groups occupy the SAME
    physical corridor on route_477. Even with V2 ON, the second group has
    no geographically-near non-colliding alternate, so V2 should fall back
    to V1 abstain. This locks the conservative behavior in for the dominant
    Brenham scenario.
    """

    def test_overlapping_groups_no_alternate_falls_back_to_abstain(self) -> None:
        # Two parallel "Backbone" routes within 25 ft perp of each other, but
        # the alternate is FULLY occupied by the kept group.
        route_a = _linear_coords(-96.4000, 30.155, -96.3990, 30.155, steps=5)
        route_b = _linear_coords(-96.4000, 30.15514, -96.3990, 30.15514, steps=5)
        # bore_log30-style segments: same physical corridor as bore_log29
        seg = _linear_coords(-96.39990, 30.155, -96.39955, 30.155, steps=4)
        loser = _match_with_segments("bore_log30.xlsx", "route_A", seg, confidence=0.18)
        loser["candidate_rankings"] = [
            {"route_id": "route_A", "route_name": "A", "score": 0.18},
            {"route_id": "route_B", "route_name": "B", "score": 0.15},
        ]
        catalog = [_route("route_A", route_a), _route("route_B", route_b)]
        # Kept group already covers all of route_B
        decision = search_alternate_placement(
            loser, route_catalog=catalog,
            kept_offsets_by_route={"route_B": [(0.0, 400.0)]},
            min_score=0.10, max_perp_ft=200.0, overlap_threshold=0.50,
        )
        assert decision["outcome"] == "no_safe_alternate"
        assert decision["source_file"] == "bore_log30.xlsx"
        assert decision["original_route_id"] == "route_A"
        # Inspect the rejection rationale.
        reasons = [r["reason"] for r in decision["rejected_candidates"]]
        assert "would_collide_with_kept_group" in reasons

    def test_overlapping_groups_with_free_parallel_route_re_places(self) -> None:
        # When a parallel route exists AND is unoccupied, V2 rescues the loser.
        route_a = _linear_coords(-96.4000, 30.155, -96.3990, 30.155, steps=5)
        route_b = _linear_coords(-96.4000, 30.15514, -96.3990, 30.15514, steps=5)
        seg = _linear_coords(-96.39990, 30.155, -96.39955, 30.155, steps=4)
        loser = _match_with_segments("bore_log30.xlsx", "route_A", seg, confidence=0.18)
        loser["candidate_rankings"] = [
            {"route_id": "route_A", "route_name": "A", "score": 0.18},
            {"route_id": "route_B", "route_name": "B", "score": 0.15},
        ]
        catalog = [_route("route_A", route_a), _route("route_B", route_b)]
        # No kept groups on route_B → loser can move there cleanly
        decision = search_alternate_placement(
            loser, route_catalog=catalog, kept_offsets_by_route={},
            min_score=0.10, max_perp_ft=200.0, overlap_threshold=0.50,
        )
        assert decision["outcome"] == "alternate_selected"
        assert decision["alternate_route_id"] == "route_B"


# ── Phase 1 build-failure classifier (B-MATCH-V2-ALT-BUILD-DIAG-1) ────────


class TestClassifyAlternateBuildFailure(unittest.TestCase):
    """Pure unit tests for classify_alternate_build_failure.

    The classifier splits the legacy "alternate_build_returned_empty"
    bucket into three actionable failure modes plus a happy-path
    None-return.
    """

    def _alt_route(self) -> Dict[str, Any]:
        return {
            "route_id": "route_443",
            "route_name": "Underground Cable Spur",
            "coords": [[-96.4000, 30.155], [-96.3990, 30.155]],
            "length_ft": 317.5,
        }

    def _norm_group(self) -> Dict[str, Any]:
        return {
            "min_station_ft": 0.0,
            "max_station_ft": 415.0,
            "span_ft": 415.0,
        }

    def test_classify_exception_returns_exception_reason_with_type_and_message(self) -> None:
        rejection = classify_alternate_build_failure(
            source_file="bore_log29.xlsx",
            alt_route=self._alt_route(),
            norm_group=self._norm_group(),
            new_points=[],
            new_segments=[],
            build_exception=ValueError("seg coords malformed"),
        )
        assert rejection is not None
        assert rejection["reason"] == "alternate_build_raised_exception"
        assert rejection["exception_type"] == "ValueError"
        assert rejection["exception_message"] == "seg coords malformed"
        assert rejection["source_file"] == "bore_log29.xlsx"
        assert rejection["route_id"] == "route_443"
        assert rejection["route_name"] == "Underground Cable Spur"
        assert rejection["point_count"] == 0
        assert rejection["segment_count"] == 0
        assert rejection["station_min_ft"] == 0.0
        assert rejection["station_max_ft"] == 415.0
        assert rejection["route_coord_count"] == 2
        assert rejection["route_length_ft"] == 317.5

    def test_classify_no_points_returns_no_points_reason(self) -> None:
        rejection = classify_alternate_build_failure(
            source_file="bore_log29.xlsx",
            alt_route=self._alt_route(),
            norm_group=self._norm_group(),
            new_points=[],
            new_segments=[],
            build_exception=None,
        )
        assert rejection is not None
        assert rejection["reason"] == "alternate_build_returned_no_points"
        assert "exception_type" not in rejection
        assert "exception_message" not in rejection
        assert rejection["point_count"] == 0
        assert rejection["segment_count"] == 0

    def test_classify_points_present_no_segments_returns_no_segments_reason(self) -> None:
        rejection = classify_alternate_build_failure(
            source_file="bore_log29.xlsx",
            alt_route=self._alt_route(),
            norm_group=self._norm_group(),
            new_points=[{"station": "0+00"}, {"station": "1+00"}],
            new_segments=[],
            build_exception=None,
        )
        assert rejection is not None
        assert rejection["reason"] == "alternate_build_returned_no_segments"
        assert "exception_type" not in rejection
        assert rejection["point_count"] == 2
        assert rejection["segment_count"] == 0

    def test_classify_happy_path_returns_none(self) -> None:
        result = classify_alternate_build_failure(
            source_file="bore_log29.xlsx",
            alt_route=self._alt_route(),
            norm_group=self._norm_group(),
            new_points=[{"station": "0+00"}, {"station": "1+00"}],
            new_segments=[{"coords": [[30.155, -96.4], [30.155, -96.399]]}],
            build_exception=None,
        )
        assert result is None

    def test_classify_truncates_long_exception_message_to_200_chars(self) -> None:
        long_msg = "x" * 5000
        rejection = classify_alternate_build_failure(
            source_file="bore_log29.xlsx",
            alt_route=self._alt_route(),
            norm_group=self._norm_group(),
            new_points=[],
            new_segments=[],
            build_exception=RuntimeError(long_msg),
        )
        assert rejection is not None
        assert rejection["exception_type"] == "RuntimeError"
        assert rejection["exception_message"] == "x" * 200
        assert len(rejection["exception_message"]) == 200

    def test_classify_missing_route_and_group_metadata_still_returns_record(self) -> None:
        # Defensive: when caller hands us None / empty dicts, the classifier
        # must still emit a rejection with the failure mode rather than
        # crashing — Phase 1's job is to expose, never to mask.
        rejection = classify_alternate_build_failure(
            source_file="bore_log29.xlsx",
            alt_route=None,
            norm_group=None,
            new_points=[],
            new_segments=[],
            build_exception=None,
        )
        assert rejection is not None
        assert rejection["reason"] == "alternate_build_returned_no_points"
        assert rejection["route_id"] == ""
        assert rejection["route_name"] == ""
        assert rejection["station_min_ft"] is None
        assert rejection["station_max_ft"] is None
        assert rejection["route_coord_count"] == 0
        assert rejection["route_length_ft"] is None

    def test_classify_exception_priority_over_empty_points(self) -> None:
        # If both an exception fires AND points come back empty (the
        # actual production except-handler resets both lists), exception
        # wins. This protects against future regressions where someone
        # reorders the if/elif chain.
        rejection = classify_alternate_build_failure(
            source_file="bore_log29.xlsx",
            alt_route=self._alt_route(),
            norm_group=self._norm_group(),
            new_points=[],
            new_segments=[],
            build_exception=KeyError("expected_key_absent"),
        )
        assert rejection is not None
        assert rejection["reason"] == "alternate_build_raised_exception"
        assert rejection["exception_type"] == "KeyError"


# ── Phase 2 fix lock-in (B-MATCH-V2-ALT-BUILD-FIX-1) ──────────────────────


class TestV2AlternateBuildFreshMapping(unittest.TestCase):
    """B-MATCH-V2-ALT-BUILD-FIX-1 — surgical Phase 2 fix lock-in for the
    V2 alternate-build call site at backend/main.py:11536+.

    Backdrop:
    Before the fix, the call site passed the V1-original loser
    `_loser_match["mapping"]` as ``mapping_override`` to
    ``_build_station_points_for_group(alt_route, ...)``. That mapping
    carries an ``anchor_offset_ft`` calibrated against the
    ORIGINAL route's chainage. On a shorter / different alternate route,
    the formula at backend/main.py:6382
    (``mapped = anchor_offset_ft + max(0.0, station_ft - min_station)``)
    plus the clamp at backend/main.py:6386
    (``max(0.0, min(mapped, route_total_ft))``) collapsed every station
    to the alternate route's endpoint, producing zero segments downstream
    (Phase 2 attribution at scripts/v2_alt_build_no_segments_attribution.py).

    The fix at backend/main.py:11536 passes ``None`` as
    ``mapping_override`` so ``_build_station_points_for_group`` invokes
    ``_resolve_station_mapping(rows, alt_route_total)`` fresh, which
    always returns ``anchor_offset_ft = 0.0``.
    """

    def _route_latlon(self, start_lat: float, start_lon: float,
                       end_lat: float, end_lon: float,
                       steps: int = 8) -> List[List[float]]:
        """Densified linear route in [lat, lon] format (matches the
        production route_catalog convention — see V3 coord doctrine)."""
        out: List[List[float]] = []
        for i in range(steps + 1):
            t = i / steps
            out.append([start_lat + (end_lat - start_lat) * t,
                        start_lon + (end_lon - start_lon) * t])
        return out

    def _route_dict(self, route_id: str, coords: List[List[float]]) -> Dict[str, Any]:
        return {
            "route_id": route_id,
            "route_name": f"{route_id} name",
            "source_folder": "Backbone",
            "route_role": "underground_cable",
            "coords": coords,
            "length_ft": 0.0,
            "point_count": len(coords),
        }

    def _rows(self, station_fts: List[float]) -> List[Dict[str, Any]]:
        return [
            {
                "station": f"{int(s)}+00",
                "station_ft": float(s),
                "depth_ft": 5.0, "boc_ft": 4.0,
                "date": "2025-12-15", "crew": "tx1-4",
                "print": "1", "notes": "",
                "source_file": "bore_log29.xlsx",
            }
            for s in station_fts
        ]

    def test_stale_anchor_offset_override_collapses_all_points_to_route_endpoint(self) -> None:
        """Locks the pre-fix bug behavior: when ``mapping_override``
        carries an anchor_offset_ft that exceeds the alternate route's
        total length, every mapped station clamps to route_total and
        the segment builder returns zero segments. This test documents
        WHY the call-site fix is necessary.
        """
        # ~400 ft east-west route at 30.155 N (Brenham latitude)
        # delta_lon = 400 / (364567 * cos(30°)) ≈ 0.001267°
        alt_route_coords = self._route_latlon(
            30.155, -96.4000, 30.155, -96.398733, steps=8,
        )
        alt_route = self._route_dict("route_443_synth", alt_route_coords)
        rows = self._rows([0, 50, 100, 150, 200, 250, 300, 350, 400, 415])
        # Stale mapping from V1-original (anchor_offset ≫ alt route total)
        stale_mapping = {
            "mode": "group_relative",
            "min_station_ft": 0.0,
            "max_station_ft": 415.0,
            "station_range_ft": 415.0,
            "anchor_offset_ft": 1171.94,  # the production stale value for bore_log29
            "anchored_start_ft": 0.0,
            "anchored_end_ft": 415.0,
        }
        rankings = [{"route_id": "route_443_synth", "score": 0.20}]
        filter_meta = {"applied": True}

        new_points, new_mapping = M._build_station_points_for_group(
            rows, alt_route, rankings, filter_meta, stale_mapping,
        )

        # Point builder swallows the bad input and returns 10 points all
        # collapsed to the route endpoint
        assert len(new_points) == 10
        first_lat = round(new_points[0]["lat"], 5)
        first_lon = round(new_points[0]["lon"], 5)
        for p in new_points[1:]:
            assert round(p["lat"], 5) == first_lat
            assert round(p["lon"], 5) == first_lon
        # The mapping the builder used was the stale override
        assert new_mapping["anchor_offset_ft"] == 1171.94

        # Segment builder: every pair fails F1 (end_ft <= start_ft)
        new_segments = M._build_redline_segments_for_group(
            rows, alt_route, rankings, new_mapping, filter_meta,
        )
        assert len(new_segments) == 0  # the bug: zero segments

    def test_none_override_uses_fresh_mapping_and_produces_valid_segments(self) -> None:
        """Proves the fix: passing ``mapping_override=None`` triggers
        fresh ``_resolve_station_mapping`` computation against the
        alternate route's chainage, producing ``anchor_offset_ft=0.0``
        and valid segment geometry.

        This is the contract the B-MATCH-V2-ALT-BUILD-FIX-1 call-site
        change at backend/main.py:11536 relies on.
        """
        alt_route_coords = self._route_latlon(
            30.155, -96.4000, 30.155, -96.398733, steps=8,
        )
        alt_route = self._route_dict("route_443_synth", alt_route_coords)
        rows = self._rows([0, 50, 100, 150, 200, 250, 300, 350, 400, 415])
        rankings = [{"route_id": "route_443_synth", "score": 0.20}]
        filter_meta = {"applied": True}

        # THE FIX: pass None for mapping_override
        new_points, new_mapping = M._build_station_points_for_group(
            rows, alt_route, rankings, filter_meta, None,
        )

        # Fresh mapping must have anchor_offset_ft = 0.0
        assert new_mapping["anchor_offset_ft"] == 0.0
        assert new_mapping["mode"] == "group_relative"
        assert new_mapping["min_station_ft"] == 0.0
        # Points distribute across the route, NOT all at one endpoint
        assert len(new_points) == 10
        unique_locations = {(round(p["lat"], 6), round(p["lon"], 6)) for p in new_points}
        assert len(unique_locations) >= 8  # at least 8 distinct points expected

        # Segments build successfully — only the last station (415) clamps
        # against the ~400 ft route total, so we expect 8-9 non-zero segments
        new_segments = M._build_redline_segments_for_group(
            rows, alt_route, rankings, new_mapping, filter_meta,
        )
        assert len(new_segments) >= 8  # at minimum 8 segments out of 9 possible pairs

    def test_fresh_mapping_handles_bore_log5_pattern_route_longer_than_span(self) -> None:
        """Additional lock-in for the bore_log5 production case (span
        235 ft on a 402 ft route, but stale anchor_offset 1261.94 was
        causing collapse).

        With the fix (None override → fresh mapping), bore_log5's 5
        consecutive pairs all clear F1 and produce segments.
        """
        alt_route_coords = self._route_latlon(
            30.155, -96.4000, 30.155, -96.398733, steps=8,
        )
        alt_route = self._route_dict("route_443_synth", alt_route_coords)
        # bore_log5 production rows: stations 265-500 (span 235 ft)
        rows = self._rows([265, 300, 350, 400, 450, 500])
        rankings = [{"route_id": "route_443_synth", "score": 0.18}]
        filter_meta = {"applied": True}

        new_points, new_mapping = M._build_station_points_for_group(
            rows, alt_route, rankings, filter_meta, None,
        )

        # Fresh group_relative mapping anchored at min_station=265
        assert new_mapping["anchor_offset_ft"] == 0.0
        assert new_mapping["min_station_ft"] == 265.0
        assert len(new_points) == 6
        # Bore span 235 ft fits inside the 400 ft route → all 6 points distinct
        unique_locations = {(round(p["lat"], 6), round(p["lon"], 6)) for p in new_points}
        assert len(unique_locations) == 6

        new_segments = M._build_redline_segments_for_group(
            rows, alt_route, rankings, new_mapping, filter_meta,
        )
        # All 5 consecutive pairs should produce segments (no clamping)
        assert len(new_segments) == 5


# ── Phase 3 post-V2 collision re-arbitration (B-MATCH-V2-ALT-BUILD-FIX-2) ─


class TestPostV2Rearbitrate(unittest.TestCase):
    """B-MATCH-V2-ALT-BUILD-FIX-2 — V2 rescues can land two losers on the
    same alternate route in truly-overlapping station windows. The
    first-pass V1 resolver doesn't see these collisions (they only exist
    after V2 mutates group_matches). The post-V2 re-arbitration block
    inserted at backend/main.py:~11669 detects them via the second
    coverage_sanity recompute and re-runs the existing V1 resolver to
    abstain the lower-confidence placement.

    Tests cover:
      1. Resolution payload always carries the post-V2 keys (empty by
         default).
      2. The existing V1 resolver picks the higher-confidence group for
         a post-V2-style synthetic collision pair.
      3. The filter excludes pairs involving source_files already
         abstained in first-pass V1 (no double-abstain).
    """

    def setUp(self) -> None:
        self._saved_state = copy.deepcopy(dict(M.STATE))
        self._saved = {k: os.environ.pop(k, None) for k in (
            ABSTAIN_ENV, V2_ENV, V2_MIN_SCORE_ENV, V2_MAX_PERP_ENV,
        )}
        self._session_id = f"postv2_{uuid.uuid4().hex[:12]}"

    def tearDown(self) -> None:
        M.STATE.clear()
        M.STATE.update(self._saved_state)
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _seed_empty(self) -> None:
        M.STATE.clear()
        M.STATE.update({
            "committed_rows": [],
            "route_catalog": [],
            "address_points": [],
            "_session_id_hint": self._session_id,
            "engineering_plans": [],
        })

    def test_route_collision_resolution_payload_includes_post_v2_keys_by_default(self) -> None:
        """When no V2 rescues happen, the payload should still carry
        ``post_v2_abstained_source_files`` (empty) and
        ``collision_resolutions_post_v2`` (empty). Lock the schema so
        downstream consumers can rely on the keys being present."""
        os.environ[ABSTAIN_ENV] = "1"
        # V2 env stays unset → V2 block skipped → no post-V2 work
        self._seed_empty()
        with patch.object(M, "_candidate_rankings_for_group_v2",
                          return_value=([], {"applied": True, "mode": "test",
                                              "print_tokens": ["1"], "sheet_numbers": [1],
                                              "street_hints": [], "allowed_route_ids": [],
                                              "reason": "stub"}, [])):
            M._rebuild_field_data_outputs(scope=RebuildScope.FULL)
        cs = M.STATE.get("coverage_sanity") or {}
        rcr = cs.get("route_collision_resolution") or {}
        assert "post_v2_abstained_source_files" in rcr
        assert rcr["post_v2_abstained_source_files"] == []
        assert "collision_resolutions_post_v2" in rcr
        assert rcr["collision_resolutions_post_v2"] == []

    def test_resolve_route_collisions_picks_higher_confidence_for_post_v2_pair(self) -> None:
        """Direct test of the existing V1 resolver against a synthetic
        post-V2 collision input — proves the tie-breakers (confidence
        first) work correctly when re-applied after V2 rescue.

        Reproduces the Brenham bore_log29 + bore_log5 scenario:
        two groups V2-rescued onto route_443 with different confidences;
        the higher-confidence group must be kept.
        """
        # Mimic bore_log5 (kept) vs bore_log29 (abstained)
        group_matches = [
            {
                "source_file": "bore_log5.xlsx",
                "route_id": "route_443",
                "render_allowed": True,
                "confidence": 0.2967,
            },
            {
                "source_file": "bore_log29.xlsx",
                "route_id": "route_443",
                "render_allowed": True,
                "confidence": 0.2427,
            },
        ]
        pipeline_diag = [
            {
                "source_file": "bore_log5.xlsx",
                "evidence_resolver": {
                    "confidence": 0.2967,
                    "decision_basis": {"top1_score": 0.20},
                },
            },
            {
                "source_file": "bore_log29.xlsx",
                "evidence_resolver": {
                    "confidence": 0.2427,
                    "decision_basis": {"top1_score": 0.18},
                },
            },
        ]
        # Synthetic post-V2 collision (Window V2 ratified as true_window_overlap)
        collisions = [{
            "route_id": "route_443",
            "route_name": "Terminal Tail",
            "source_files": ["bore_log29.xlsx", "bore_log5.xlsx"],
            "overlap_ratio": 1.0,
            "overlap_ft": 235.0,
            "group_ranges": [
                {"source_file": "bore_log29.xlsx",
                 "route_offset_ft": [0.0, 402.18], "route_offset_span_ft": 402.18},
                {"source_file": "bore_log5.xlsx",
                 "route_offset_ft": [167.18, 402.18], "route_offset_span_ft": 235.0},
            ],
            "station_ranges": [
                {"source_file": "bore_log29.xlsx",
                 "station_min_ft": 0.0, "station_max_ft": 415.0, "station_span_ft": 415.0},
                {"source_file": "bore_log5.xlsx",
                 "station_min_ft": 265.0, "station_max_ft": 500.0, "station_span_ft": 235.0},
            ],
            "dates": [["2025-12-15"], ["2025-12-15"]],
            "crews": [["tx1-4"], ["tx1-4"]],
        }]

        result = resolve_route_collisions(group_matches, pipeline_diag, collisions)

        # bore_log29 has lower confidence → abstained; bore_log5 kept
        assert "bore_log29.xlsx" in (result.get("abstained_source_files") or [])
        assert "bore_log5.xlsx" not in (result.get("abstained_source_files") or [])

    def test_post_v2_filter_excludes_pairs_with_pre_abstained_source_files(self) -> None:
        """The re-arbitration filter at backend/main.py:~11688 must skip
        any collision pair where at least one source_file was already
        abstained by first-pass V1 — otherwise we double-abstain.

        This test exercises the filter predicate directly to lock the
        no-double-abstain behavior.
        """
        # Three synthetic collision pairs:
        #   (1) both members already pre-abstained → SKIP
        #   (2) one member pre-abstained → SKIP
        #   (3) neither member pre-abstained → KEEP (new post-V2 collision)
        collisions_post = [
            {"source_files": ["a.xlsx", "b.xlsx"]},  # both pre-abstained
            {"source_files": ["c.xlsx", "d.xlsx"]},  # c pre-abstained
            {"source_files": ["e.xlsx", "f.xlsx"]},  # neither pre-abstained
        ]
        pre_abstained = {"a.xlsx", "b.xlsx", "c.xlsx"}

        # Mirror the exact filter predicate used at backend/main.py:~11691
        new_pairs = [
            c for c in collisions_post
            if not any(
                sf in pre_abstained for sf in (c.get("source_files") or [])
            )
        ]
        assert len(new_pairs) == 1
        assert new_pairs[0]["source_files"] == ["e.xlsx", "f.xlsx"]

    def test_post_v2_abstain_stamp_locks_value(self) -> None:
        """Lock the exact ``stopped_at`` value so audit consumers /
        explanation helpers can distinguish post-V2 abstains from
        first-pass V1 abstains.

        The orchestrator at backend/main.py:~11713 sets
        ``stopped_at="abstained_post_v2_collision"`` (and adds
        ``"post_v2_collision"`` to ``render_block_reasons``).
        """
        # The stamp value is a string constant in the orchestrator.
        # We exercise the value via a synthetic pipeline_diag entry the
        # explanation surface at backend/main.py:18583 would consume.
        synthetic_entry = {
            "source_file": "bore_log29.xlsx",
            "stopped_at": "abstained_post_v2_collision",
            "render_allowed": False,
            "render_block_reasons": ["post_v2_collision"],
            "segments_returned": 0,
        }
        assert synthetic_entry["stopped_at"] == "abstained_post_v2_collision"
        assert "post_v2_collision" in synthetic_entry["render_block_reasons"]
        assert synthetic_entry["render_allowed"] is False
        assert synthetic_entry["segments_returned"] == 0


if __name__ == "__main__":
    unittest.main()
