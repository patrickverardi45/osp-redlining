"""B-MATCH-LOC-EVIDENCE-1 V3 — auto candidate expansion (rebuild-loop rescue).

When BOTH TRUELINE_ABSTAIN_ON_LOCATION_MISMATCH=1 AND
TRUELINE_AUTO_CANDIDATE_EXPANSION=1, the per-group loop attempts to
deterministically discover a trunk candidate from KMZ address-point
proximity. If discovery succeeds and the discovered route's score beats
the current top-1 (with a 0.30 floor), the discovered route is prepended
to rankings and the abstain `continue` is skipped — the existing
downstream pipeline (anchoring, segment build) proceeds with the rescued
candidate.

Default (either gate OFF) preserves V2 abstain behavior byte-for-byte.

These tests mock discover_candidate_routes_from_notes_streets and
_score_route_for_group so the rebuild loop's rescue branch is exercised
in isolation without needing the full Brenham fixture pipeline.
"""

from __future__ import annotations

import copy
import os
import unittest
import uuid
from unittest.mock import patch

os.environ.setdefault("TRUELINE_JWT_SECRET", "v3-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "v3-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend import main as M
from backend.app.core.rebuild_scope import RebuildScope

ABSTAIN_ENV = "TRUELINE_ABSTAIN_ON_LOCATION_MISMATCH"
EXPANSION_ENV = "TRUELINE_AUTO_CANDIDATE_EXPANSION"


def _synthetic_row(notes: str, source_file: str, print_token: str = "1", station: str = "0+00", station_ft: float = 0.0) -> dict:
    return {
        "station": station,
        "station_ft": station_ft,
        "depth_ft": 5.0,
        "boc_ft": 4.0,
        "date": "2026-01-01",
        "crew": "test_crew",
        "print": print_token,
        "notes": notes,
        "source_file": source_file,
    }


def _two_group_rows(notes_a: str, notes_b: str) -> list:
    return [
        _synthetic_row(notes_a, "group_a.xlsx", station="0+00", station_ft=0.0),
        _synthetic_row(notes_a, "group_a.xlsx", station="1+00", station_ft=100.0),
        _synthetic_row(notes_b, "group_b.xlsx", print_token="2", station="0+00", station_ft=0.0),
        _synthetic_row(notes_b, "group_b.xlsx", print_token="2", station="1+00", station_ft=100.0),
    ]


def _stub_rankings_v2(route_id: str = "route_nonexistent", score: float = 0.20) -> tuple:
    rankings = [{
        "route_id": route_id,
        "route_name": "Stub",
        "score": score,
        "route_length_ft": 100.0,
        "expected_span_ft": 100.0,
        "route_role": "underground_cable",
    }]
    filter_meta = {
        "applied": True,
        "mode": "print_to_street_extraction",
        "print_tokens": ["1"],
        "sheet_numbers": [1],
        "street_hints": ["E STONE ST"],
        "allowed_route_ids": [route_id],
        "reason": "stub",
    }
    return (rankings, filter_meta, list(rankings))


def _mismatch_payload(notes: str = "LAWNDALE AVE") -> dict:
    return {
        "notes_streets": [notes],
        "filter_streets": ["E STONE ST"],
        "severity": "REVIEW",
        "source": "bore_log_notes_vs_print_filter",
    }


def _discovery_payload(route_id: str = "route_trunk", coverage_count: int = 17) -> dict:
    return {
        "source": "kmz_point_to_linestring_proximity",
        "notes_streets": ["LAWNDALE AVE"],
        "discovered_route_ids": [route_id],
        "evidence": {
            "point_count": 17,
            "coverage_count": coverage_count,
            "coverage_ratio": coverage_count / 17.0,
            "distance_threshold_ft": 100.0,
            "nearest_distance_ft": 39.2,
            "route_name": "Underground Cable",
            "source_folder": "Connections / underground cable",
        },
    }


def _scored_route(route_id: str = "route_trunk", score: float = 0.55) -> dict:
    return {
        "route_id": route_id,
        "route_name": "Underground Cable",
        "source_folder": "Connections / underground cable",
        "route_role": "underground_cable",
        "route_length_ft": 2812.0,
        "expected_span_ft": 100.0,
        "length_gap_ft": 2712.0,
        "score": score,
    }


class TestAutoCandidateExpansion(unittest.TestCase):
    """V3 auto candidate expansion env-gated rescue branch."""

    def setUp(self) -> None:
        self._saved_state = copy.deepcopy(dict(M.STATE))
        self._saved_abstain = os.environ.pop(ABSTAIN_ENV, None)
        self._saved_expansion = os.environ.pop(EXPANSION_ENV, None)
        self._session_id = f"v3_{uuid.uuid4().hex[:12]}"

    def tearDown(self) -> None:
        M.STATE.clear()
        M.STATE.update(self._saved_state)
        for env, saved in ((ABSTAIN_ENV, self._saved_abstain), (EXPANSION_ENV, self._saved_expansion)):
            if saved is None:
                os.environ.pop(env, None)
            else:
                os.environ[env] = saved

    def _reset_state(self, rows: list) -> None:
        M.STATE.clear()
        M.STATE.update({
            "committed_rows": list(rows),
            "route_catalog": [],
            "address_points": [],
            "_session_id_hint": self._session_id,
            "engineering_plans": [],
        })

    def _find_diag(self, source_file: str) -> dict:
        for entry in (M.STATE.get("pipeline_diag") or []):
            if entry.get("source_file") == source_file:
                return entry
        raise AssertionError(f"No pipeline_diag entry for source_file={source_file!r}")

    # ── A. Default-OFF parity ──────────────────────────────────────────────

    def test_both_flags_off_no_expansion_no_abstain(self) -> None:
        rows = _two_group_rows("LAWNDALE AVE", "no street")
        self._reset_state(rows)
        with patch.object(M, "_candidate_rankings_for_group_v2", return_value=_stub_rankings_v2()), \
             patch.object(M, "compute_location_evidence_mismatch", return_value=_mismatch_payload()):
            M._rebuild_field_data_outputs(scope=RebuildScope.FULL)
        diag_a = self._find_diag("group_a.xlsx")
        self.assertNotIn("auto_candidate_expansion", diag_a)
        self.assertNotIn("abstain_reason", diag_a)

    def test_abstain_on_expansion_off_preserves_v2_abstain(self) -> None:
        os.environ[ABSTAIN_ENV] = "1"
        # EXPANSION_ENV intentionally UNSET
        rows = _two_group_rows("LAWNDALE AVE", "no street")
        self._reset_state(rows)
        with patch.object(M, "_candidate_rankings_for_group_v2", return_value=_stub_rankings_v2()), \
             patch.object(M, "compute_location_evidence_mismatch", return_value=_mismatch_payload()):
            M._rebuild_field_data_outputs(scope=RebuildScope.FULL)
        diag_a = self._find_diag("group_a.xlsx")
        self.assertEqual(diag_a.get("stopped_at"), "abstained_location_evidence_mismatch")
        self.assertNotIn("auto_candidate_expansion", diag_a)

    def test_expansion_on_abstain_off_does_not_expand(self) -> None:
        # Expansion gate is downstream of abstain gate; if abstain OFF, the
        # rescue branch is never evaluated.
        os.environ[EXPANSION_ENV] = "1"
        rows = _two_group_rows("LAWNDALE AVE", "no street")
        self._reset_state(rows)
        with patch.object(M, "_candidate_rankings_for_group_v2", return_value=_stub_rankings_v2()), \
             patch.object(M, "compute_location_evidence_mismatch", return_value=_mismatch_payload()), \
             patch.object(M, "discover_candidate_routes_from_notes_streets", return_value=_discovery_payload()) as mock_disc:
            M._rebuild_field_data_outputs(scope=RebuildScope.FULL)
        # Discovery is never called when abstain gate is OFF
        self.assertEqual(mock_disc.call_count, 0)
        diag_a = self._find_diag("group_a.xlsx")
        self.assertNotIn("auto_candidate_expansion", diag_a)
        self.assertNotIn("abstain_reason", diag_a)

    # ── B. Both flags ON + LAWNDALE mismatch + clean discovery → expansion fires

    def test_both_flags_on_lawndale_expansion_fires(self) -> None:
        os.environ[ABSTAIN_ENV] = "1"
        os.environ[EXPANSION_ENV] = "1"
        rows = _two_group_rows("LAWNDALE AVE", "no street")
        self._reset_state(rows)
        with patch.object(M, "_candidate_rankings_for_group_v2", return_value=_stub_rankings_v2(score=0.20)), \
             patch.object(M, "compute_location_evidence_mismatch", return_value=_mismatch_payload()), \
             patch.object(M, "discover_candidate_routes_from_notes_streets", return_value=_discovery_payload("route_trunk")), \
             patch.object(M, "_find_route_by_id", return_value={"route_id": "route_trunk", "coords": [(0, 0), (1, 1)], "route_name": "Underground Cable", "source_folder": "Connections / underground cable"}), \
             patch.object(M, "_score_route_for_group", return_value=_scored_route("route_trunk", 0.55)):
            M._rebuild_field_data_outputs(scope=RebuildScope.FULL)
        diag_a = self._find_diag("group_a.xlsx")
        self.assertIn("auto_candidate_expansion", diag_a)
        ace = diag_a["auto_candidate_expansion"]
        self.assertEqual(ace["source"], "kmz_point_to_linestring_proximity")
        self.assertEqual(ace["discovered_route_ids"], ["route_trunk"])
        self.assertEqual(ace["selected_candidate_route_id"], "route_trunk")
        self.assertEqual(ace["evidence"]["point_count"], 17)
        # Abstain reason should NOT be set when expansion succeeded
        self.assertNotIn("abstain_reason", diag_a)
        self.assertNotEqual(diag_a.get("stopped_at"), "abstained_location_evidence_mismatch")
        # Rescued route should be in the allowed_route_ids
        self.assertIn("route_trunk", diag_a.get("strict_allowed_route_ids") or [])

    # ── C. Both flags ON + CHERI mismatch (no discovery) → abstain preserved

    def test_both_flags_on_cheri_remains_abstained(self) -> None:
        os.environ[ABSTAIN_ENV] = "1"
        os.environ[EXPANSION_ENV] = "1"
        rows = _two_group_rows("CHERI LN", "no street")
        self._reset_state(rows)

        def _mismatch_only_for_cheri(group, filter_meta):
            for row in group:
                if "CHERI" in str(row.get("notes") or "").upper():
                    return _mismatch_payload("CHERI LN")
            return None

        with patch.object(M, "_candidate_rankings_for_group_v2", return_value=_stub_rankings_v2()), \
             patch.object(M, "compute_location_evidence_mismatch", side_effect=_mismatch_only_for_cheri), \
             patch.object(M, "discover_candidate_routes_from_notes_streets", return_value=None) as mock_disc:
            M._rebuild_field_data_outputs(scope=RebuildScope.FULL)
        diag_a = self._find_diag("group_a.xlsx")
        self.assertEqual(diag_a.get("stopped_at"), "abstained_location_evidence_mismatch")
        self.assertIn("abstain_reason", diag_a)
        self.assertNotIn("auto_candidate_expansion", diag_a)
        # Discovery was called exactly once — for the CHERI group only;
        # group_b ("no street") had no mismatch and never entered the rescue branch.
        self.assertEqual(mock_disc.call_count, 1)

    # ── D. Discovery returns route but score is too low → fall through to abstain

    def test_discovery_with_low_score_falls_through_to_abstain(self) -> None:
        os.environ[ABSTAIN_ENV] = "1"
        os.environ[EXPANSION_ENV] = "1"
        rows = _two_group_rows("LAWNDALE AVE", "no street")
        self._reset_state(rows)
        with patch.object(M, "_candidate_rankings_for_group_v2", return_value=_stub_rankings_v2(score=0.20)), \
             patch.object(M, "compute_location_evidence_mismatch", return_value=_mismatch_payload()), \
             patch.object(M, "discover_candidate_routes_from_notes_streets", return_value=_discovery_payload("route_trunk")), \
             patch.object(M, "_find_route_by_id", return_value={"route_id": "route_trunk", "coords": [(0, 0), (1, 1)]}), \
             patch.object(M, "_score_route_for_group", return_value=_scored_route("route_trunk", 0.05)):
            M._rebuild_field_data_outputs(scope=RebuildScope.FULL)
        diag_a = self._find_diag("group_a.xlsx")
        self.assertEqual(diag_a.get("stopped_at"), "abstained_location_evidence_mismatch")
        self.assertNotIn("auto_candidate_expansion", diag_a)

    # ── E. Non-mismatch groups never enter the rescue branch

    def test_non_mismatch_groups_unaffected_when_flags_on(self) -> None:
        os.environ[ABSTAIN_ENV] = "1"
        os.environ[EXPANSION_ENV] = "1"
        rows = _two_group_rows("neutral notes a", "neutral notes b")
        self._reset_state(rows)
        with patch.object(M, "_candidate_rankings_for_group_v2", return_value=_stub_rankings_v2()), \
             patch.object(M, "compute_location_evidence_mismatch", return_value=None), \
             patch.object(M, "discover_candidate_routes_from_notes_streets") as mock_disc:
            M._rebuild_field_data_outputs(scope=RebuildScope.FULL)
        self.assertEqual(mock_disc.call_count, 0)
        for source in ("group_a.xlsx", "group_b.xlsx"):
            diag = self._find_diag(source)
            self.assertNotIn("auto_candidate_expansion", diag)
            self.assertNotIn("location_evidence_mismatch", diag)
            self.assertNotIn("abstain_reason", diag)

    # ── F. Expansion diag carries the full evidence payload contract

    def test_expansion_diag_payload_shape(self) -> None:
        os.environ[ABSTAIN_ENV] = "1"
        os.environ[EXPANSION_ENV] = "1"
        rows = _two_group_rows("LAWNDALE AVE", "no street")
        self._reset_state(rows)
        with patch.object(M, "_candidate_rankings_for_group_v2", return_value=_stub_rankings_v2(score=0.10)), \
             patch.object(M, "compute_location_evidence_mismatch", return_value=_mismatch_payload()), \
             patch.object(M, "discover_candidate_routes_from_notes_streets", return_value=_discovery_payload("route_trunk")), \
             patch.object(M, "_find_route_by_id", return_value={"route_id": "route_trunk", "coords": [(0, 0), (1, 1)]}), \
             patch.object(M, "_score_route_for_group", return_value=_scored_route("route_trunk", 0.55)):
            M._rebuild_field_data_outputs(scope=RebuildScope.FULL)
        ace = self._find_diag("group_a.xlsx").get("auto_candidate_expansion")
        self.assertIsNotNone(ace)
        # Required diag fields per the V3 contract
        for top_key in ("source", "notes_streets", "discovered_route_ids", "selected_candidate_route_id", "evidence"):
            self.assertIn(top_key, ace, f"missing top-level diag key {top_key!r}")
        for ev_key in ("point_count", "coverage_count", "coverage_ratio", "distance_threshold_ft", "nearest_distance_ft", "route_name", "source_folder"):
            self.assertIn(ev_key, ace["evidence"], f"missing evidence key {ev_key!r}")

    # ── G. State default contains address_points key

    def test_default_session_state_has_address_points_key(self) -> None:
        state = M._default_session_state()
        self.assertIn("address_points", state)
        self.assertEqual(state["address_points"], [])


if __name__ == "__main__":
    unittest.main()
