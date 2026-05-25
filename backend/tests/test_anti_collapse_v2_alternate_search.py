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


if __name__ == "__main__":
    unittest.main()
