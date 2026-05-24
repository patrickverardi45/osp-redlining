"""B-MATCH-LOC-EVIDENCE-1 V2 — abstain behavior under env-var gate.

Tests the env-gated abstain branch inside the per-group loop of
_rebuild_field_data_outputs. The branch fires only when:
  (1) compute_location_evidence_mismatch returns a non-None payload, AND
  (2) TRUELINE_ABSTAIN_ON_LOCATION_MISMATCH == "1"

When it fires, the group is excluded from rankings/anchor/segment-build via
`continue`, and pipeline_diag receives an entry with
  stopped_at = "abstained_location_evidence_mismatch"
  abstain_reason = {reason, notes_streets, filter_streets, source}
  location_evidence_mismatch = <original payload>

Default behavior (flag UNSET or "0") is byte-identical to today.

These tests mock _candidate_rankings_for_group_v2 to bypass route_catalog
setup, return a non-empty ranking that references a route_id NOT present
in the (empty) catalog. That makes the non-abstain branch terminate
cleanly at the "no_anchored_hypotheses" stopped_at without exercising the
full segment-build path. The abstain branch terminates earlier with a
distinct stopped_at value, which lets the tests distinguish the two
branches by pipeline_diag content alone.
"""

from __future__ import annotations

import copy
import os
import unittest
import uuid
from unittest.mock import patch

os.environ.setdefault("TRUELINE_JWT_SECRET", "abstain-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "abstain-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend import main as M
from backend.app.core.rebuild_scope import RebuildScope

ABSTAIN_ENV = "TRUELINE_ABSTAIN_ON_LOCATION_MISMATCH"


def _synthetic_row(notes: str, print_token: str = "1", source_file: str = "test_log.xlsx") -> dict:
    return {
        "station": "0+00",
        "station_ft": 0.0,
        "depth_ft": 5.0,
        "boc_ft": 4.0,
        "date": "2026-01-01",
        "crew": "test_crew",
        "print": print_token,
        "notes": notes,
        "source_file": source_file,
    }


def _synthetic_rows_two_groups(notes_a: str, notes_b: str) -> list:
    return [
        _synthetic_row(notes_a, print_token="1", source_file="group_a.xlsx"),
        # second row for group A to give it a non-zero span
        {**_synthetic_row(notes_a, print_token="1", source_file="group_a.xlsx"), "station": "1+00", "station_ft": 100.0},
        _synthetic_row(notes_b, print_token="2", source_file="group_b.xlsx"),
        {**_synthetic_row(notes_b, print_token="2", source_file="group_b.xlsx"), "station": "1+00", "station_ft": 100.0},
    ]


def _mock_rankings(route_id: str = "route_nonexistent") -> tuple:
    """Return (rankings, filter_meta, all_rankings) tuple for a non-empty
    ranking referencing a route_id that does NOT exist in the route catalog,
    so the non-abstain path terminates at "no_anchored_hypotheses"."""
    rankings = [
        {
            "route_id": route_id,
            "route_name": "Synthetic Route",
            "score": 0.5,
            "route_length_ft": 100.0,
            "expected_span_ft": 100.0,
            "route_role": "underground_cable",
        }
    ]
    filter_meta = {
        "applied": True,
        "mode": "print_to_street_extraction",
        "print_tokens": ["1"],
        "sheet_numbers": [1],
        "street_hints": ["E STONE ST"],
        "allowed_route_ids": [route_id],
        "reason": "synthetic test filter_meta",
    }
    return (rankings, filter_meta, list(rankings))


def _mismatch_payload() -> dict:
    return {
        "notes_streets": ["CHERI LN"],
        "filter_streets": ["E STONE ST"],
        "severity": "REVIEW",
        "source": "bore_log_notes_vs_print_filter",
    }


class TestAbstainOnLocationMismatch(unittest.TestCase):
    """V2 abstain branch — env-gated, default OFF."""

    def setUp(self) -> None:
        self._saved_state = copy.deepcopy(dict(M.STATE))
        self._saved_env = os.environ.pop(ABSTAIN_ENV, None)
        self._session_id = f"abstain_{uuid.uuid4().hex[:12]}"

    def tearDown(self) -> None:
        M.STATE.clear()
        M.STATE.update(self._saved_state)
        if self._saved_env is None:
            os.environ.pop(ABSTAIN_ENV, None)
        else:
            os.environ[ABSTAIN_ENV] = self._saved_env

    def _reset_state(self, rows: list) -> None:
        M.STATE.clear()
        M.STATE.update({
            "committed_rows": list(rows),
            "route_catalog": [],
            "_session_id_hint": self._session_id,
            "engineering_plans": [],
        })

    def _find_diag_for_source(self, source_file: str) -> dict:
        for entry in (M.STATE.get("pipeline_diag") or []):
            if entry.get("source_file") == source_file:
                return entry
        raise AssertionError(f"No pipeline_diag entry found for source_file={source_file!r}")

    # ── 1. Flag OFF (UNSET) — abstain branch never fires ──────────────────

    def test_flag_unset_no_abstain_even_with_mismatch(self) -> None:
        rows = _synthetic_rows_two_groups(
            notes_a="WORK ON CHERI LN",
            notes_b="depth 5 ft, no street",
        )
        self._reset_state(rows)
        with patch.object(M, "_candidate_rankings_for_group_v2", return_value=_mock_rankings()), \
             patch.object(M, "compute_location_evidence_mismatch", return_value=_mismatch_payload()):
            M._rebuild_field_data_outputs(scope=RebuildScope.FULL)

        diag_a = self._find_diag_for_source("group_a.xlsx")
        self.assertEqual(diag_a.get("location_evidence_mismatch"), _mismatch_payload())
        self.assertNotIn("abstain_reason", diag_a)
        self.assertNotEqual(diag_a.get("stopped_at"), "abstained_location_evidence_mismatch")

    # ── 2. Flag OFF ("0") — abstain branch never fires ────────────────────

    def test_flag_zero_no_abstain_even_with_mismatch(self) -> None:
        os.environ[ABSTAIN_ENV] = "0"
        rows = _synthetic_rows_two_groups("WORK ON CHERI LN", "no street")
        self._reset_state(rows)
        with patch.object(M, "_candidate_rankings_for_group_v2", return_value=_mock_rankings()), \
             patch.object(M, "compute_location_evidence_mismatch", return_value=_mismatch_payload()):
            M._rebuild_field_data_outputs(scope=RebuildScope.FULL)

        diag_a = self._find_diag_for_source("group_a.xlsx")
        self.assertEqual(diag_a.get("location_evidence_mismatch"), _mismatch_payload())
        self.assertNotIn("abstain_reason", diag_a)
        self.assertNotEqual(diag_a.get("stopped_at"), "abstained_location_evidence_mismatch")

    # ── 3. Flag ON ("1") + mismatch — abstain fires ───────────────────────

    def test_flag_on_abstain_fires_when_mismatch_present(self) -> None:
        os.environ[ABSTAIN_ENV] = "1"
        rows = _synthetic_rows_two_groups("WORK ON CHERI LN", "no street")
        self._reset_state(rows)
        with patch.object(M, "_candidate_rankings_for_group_v2", return_value=_mock_rankings()), \
             patch.object(M, "compute_location_evidence_mismatch", return_value=_mismatch_payload()):
            M._rebuild_field_data_outputs(scope=RebuildScope.FULL)

        diag_a = self._find_diag_for_source("group_a.xlsx")
        self.assertEqual(diag_a.get("stopped_at"), "abstained_location_evidence_mismatch")
        self.assertEqual(diag_a.get("abstain_reason"), {
            "reason": "location_evidence_mismatch",
            "notes_streets": ["CHERI LN"],
            "filter_streets": ["E STONE ST"],
            "source": "bore_log_notes_vs_print_filter",
        })

    # ── 4. Flag ON + NO mismatch — abstain does NOT fire ──────────────────

    def test_flag_on_no_abstain_when_mismatch_absent(self) -> None:
        os.environ[ABSTAIN_ENV] = "1"
        rows = _synthetic_rows_two_groups("no street notes here", "no street")
        self._reset_state(rows)
        with patch.object(M, "_candidate_rankings_for_group_v2", return_value=_mock_rankings()), \
             patch.object(M, "compute_location_evidence_mismatch", return_value=None):
            M._rebuild_field_data_outputs(scope=RebuildScope.FULL)

        for source in ("group_a.xlsx", "group_b.xlsx"):
            diag = self._find_diag_for_source(source)
            self.assertNotIn("abstain_reason", diag)
            self.assertNotIn("location_evidence_mismatch", diag)
            self.assertNotEqual(diag.get("stopped_at"), "abstained_location_evidence_mismatch")

    # ── 5. Abstain diag preserves both location_evidence_mismatch + abstain_reason

    def test_abstain_diag_preserves_location_evidence_payload(self) -> None:
        os.environ[ABSTAIN_ENV] = "1"
        payload = _mismatch_payload()
        rows = _synthetic_rows_two_groups("CHERI LN work", "no street")
        self._reset_state(rows)
        with patch.object(M, "_candidate_rankings_for_group_v2", return_value=_mock_rankings()), \
             patch.object(M, "compute_location_evidence_mismatch", return_value=payload):
            M._rebuild_field_data_outputs(scope=RebuildScope.FULL)

        diag_a = self._find_diag_for_source("group_a.xlsx")
        self.assertEqual(diag_a.get("location_evidence_mismatch"), payload)
        self.assertIn("abstain_reason", diag_a)
        # abstain_reason's payload fields mirror the mismatch payload
        ar = diag_a["abstain_reason"]
        self.assertEqual(ar["notes_streets"], payload["notes_streets"])
        self.assertEqual(ar["filter_streets"], payload["filter_streets"])
        self.assertEqual(ar["source"], payload["source"])
        self.assertEqual(ar["reason"], "location_evidence_mismatch")

    # ── 6. Abstain skips group from group_matches / station_points / redline_segments

    def test_abstain_excludes_group_from_outputs(self) -> None:
        os.environ[ABSTAIN_ENV] = "1"
        rows = _synthetic_rows_two_groups("CHERI LN work", "no street")
        self._reset_state(rows)
        with patch.object(M, "_candidate_rankings_for_group_v2", return_value=_mock_rankings()), \
             patch.object(M, "compute_location_evidence_mismatch", return_value=_mismatch_payload()):
            M._rebuild_field_data_outputs(scope=RebuildScope.FULL)

        station_points = M.STATE.get("station_points") or []
        redline_segments = M.STATE.get("redline_segments") or []
        for point in station_points:
            self.assertNotEqual(point.get("source_file"), "group_a.xlsx")
        for seg in redline_segments:
            self.assertNotEqual(seg.get("source_file"), "group_a.xlsx")

    # ── 7. Mixed: mismatch group abstains, non-mismatch group does not ────

    def test_mixed_groups_abstain_only_mismatch_group(self) -> None:
        os.environ[ABSTAIN_ENV] = "1"
        rows = _synthetic_rows_two_groups("CHERI LN", "neutral notes")
        self._reset_state(rows)

        def _mismatch_only_for_group_a(group, filter_meta):
            for row in group:
                if row.get("source_file") == "group_a.xlsx":
                    return _mismatch_payload()
            return None

        with patch.object(M, "_candidate_rankings_for_group_v2", return_value=_mock_rankings()), \
             patch.object(M, "compute_location_evidence_mismatch", side_effect=_mismatch_only_for_group_a):
            M._rebuild_field_data_outputs(scope=RebuildScope.FULL)

        diag_a = self._find_diag_for_source("group_a.xlsx")
        diag_b = self._find_diag_for_source("group_b.xlsx")
        # group_a abstains
        self.assertEqual(diag_a.get("stopped_at"), "abstained_location_evidence_mismatch")
        self.assertIn("abstain_reason", diag_a)
        # group_b does not
        self.assertNotIn("abstain_reason", diag_b)
        self.assertNotEqual(diag_b.get("stopped_at"), "abstained_location_evidence_mismatch")

    # ── 8. Env-var parsing semantics — only "1" enables; nothing else ─────

    def test_env_var_other_truthy_values_do_not_enable(self) -> None:
        rows = _synthetic_rows_two_groups("CHERI LN", "no street")
        for truthy in ("true", "yes", "on", "TRUE", "2", "01", "11", ""):
            os.environ[ABSTAIN_ENV] = truthy
            self._reset_state(rows)
            with patch.object(M, "_candidate_rankings_for_group_v2", return_value=_mock_rankings()), \
                 patch.object(M, "compute_location_evidence_mismatch", return_value=_mismatch_payload()):
                M._rebuild_field_data_outputs(scope=RebuildScope.FULL)
            diag_a = self._find_diag_for_source("group_a.xlsx")
            self.assertNotEqual(
                diag_a.get("stopped_at"),
                "abstained_location_evidence_mismatch",
                f"Value {truthy!r} should not enable abstain",
            )

    def test_env_var_whitespace_around_one_enables(self) -> None:
        # "0".strip() == "0" and "1".strip() == "1"; values with surrounding
        # whitespace should be tolerated by .strip(). " 1 " enables.
        os.environ[ABSTAIN_ENV] = " 1 "
        rows = _synthetic_rows_two_groups("CHERI LN", "no street")
        self._reset_state(rows)
        with patch.object(M, "_candidate_rankings_for_group_v2", return_value=_mock_rankings()), \
             patch.object(M, "compute_location_evidence_mismatch", return_value=_mismatch_payload()):
            M._rebuild_field_data_outputs(scope=RebuildScope.FULL)
        diag_a = self._find_diag_for_source("group_a.xlsx")
        self.assertEqual(diag_a.get("stopped_at"), "abstained_location_evidence_mismatch")

    # ── 9. Flag OFF byte-identity with no-mismatch baseline ───────────────

    def test_flag_off_state_byte_identity_with_unflagged_baseline(self) -> None:
        rows = _synthetic_rows_two_groups("CHERI LN", "no street")

        # Baseline: flag UNSET, mismatch produced
        os.environ.pop(ABSTAIN_ENV, None)
        self._reset_state(rows)
        with patch.object(M, "_candidate_rankings_for_group_v2", return_value=_mock_rankings()), \
             patch.object(M, "compute_location_evidence_mismatch", return_value=_mismatch_payload()):
            M._rebuild_field_data_outputs(scope=RebuildScope.FULL)
        baseline_pipeline_diag = copy.deepcopy(M.STATE.get("pipeline_diag") or [])
        baseline_station_points = copy.deepcopy(M.STATE.get("station_points") or [])
        baseline_redline_segments = copy.deepcopy(M.STATE.get("redline_segments") or [])

        # Compare: flag = "0" explicitly
        os.environ[ABSTAIN_ENV] = "0"
        self._reset_state(rows)
        with patch.object(M, "_candidate_rankings_for_group_v2", return_value=_mock_rankings()), \
             patch.object(M, "compute_location_evidence_mismatch", return_value=_mismatch_payload()):
            M._rebuild_field_data_outputs(scope=RebuildScope.FULL)
        compare_pipeline_diag = M.STATE.get("pipeline_diag") or []
        compare_station_points = M.STATE.get("station_points") or []
        compare_redline_segments = M.STATE.get("redline_segments") or []

        self.assertEqual(baseline_pipeline_diag, compare_pipeline_diag)
        self.assertEqual(baseline_station_points, compare_station_points)
        self.assertEqual(baseline_redline_segments, compare_redline_segments)


if __name__ == "__main__":
    unittest.main()
