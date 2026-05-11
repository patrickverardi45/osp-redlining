"""Phase 1L — review-label analytics summary lock-down suite.

15 tests for ``_compute_review_label_summary`` and
``get_review_label_summary``, added in Phase 1L.

ISOLATION STRATEGY
------------------
Each test that touches file I/O runs in an isolated ``tempfile.TemporaryDirectory``.
``main.REVIEW_LABELS_PATH`` and ``main.MATCH_SHADOW_COMPARE_PATH`` are
monkeypatched in ``setUp`` and restored in ``tearDown``.
The real uploads/*.jsonl files are never touched.

All rate/coverage assertions tolerate the MIN_SAMPLES=3 guard: results with
fewer than 3 samples return ``None`` for rate fields.

IF A TEST FAILS after a legitimate Phase 1L change:
  1. Confirm the change is intentional.
  2. Update the relevant constant or assertion below.
  3. Add a comment explaining why.
  DO NOT "fix to green" without understanding the failure.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional

_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import main  # noqa: E402

# ---------------------------------------------------------------------------
# Exact top-level key set for the summary schema.
# Any addition/removal here means the schema changed — update with a comment.
# ---------------------------------------------------------------------------
EXPECTED_SUMMARY_TOP_KEYS: frozenset = frozenset(
    {
        "schema_version",
        "generated_at",
        "window",
        "total_review_labels",
        "resolved_label_counts",
        "useful_catch_rate_by_review_priority",
        "useful_catch_rate_by_disagreement_kind",
        "label_coverage_by_review_priority",
        "top_input_sha256_by_noise_rate",
        "stability_note",
    }
)

EXPECTED_WINDOW_KEYS: frozenset = frozenset(
    {"label_events_read", "shadow_rows_read", "resolved_labels", "disagreements_in_window"}
)

_STABILITY_NOTE_PREFIX = "review-label-summary-1 describes review telemetry patterns"


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _label_event(
    match_pass_id: str = "pass-1",
    group_id: Optional[str] = "G1",
    label: str = "useful_catch",
    input_sha256: Optional[str] = "sha-A",
    tombstone: bool = False,
) -> Dict[str, Any]:
    return {
        "schema_version": "review-label-1",
        "labeled_at": "2026-05-10T00:00:00+00:00",
        "match_pass_id": match_pass_id,
        "group_id": group_id,
        "input_sha256": input_sha256,
        "label": label,
        "previous_label": None,
        "reviewer_hint": None,
        "note": None,
        "tombstone": tombstone,
    }


def _shadow_row(
    match_pass_id: str = "pass-1",
    group_id: Optional[str] = "G1",
    had_shadow: bool = True,
    agreement: Optional[bool] = False,
    op_route_id: str = "R1",
    sem_route_id: str = "R2",
    anchors_op: int = 0,
    anchors_sem: int = 4,
    contrib_ids: Optional[List[str]] = None,
    input_sha256: Optional[str] = "sha-A",
) -> Dict[str, Any]:
    return {
        "schema_version": "match-shadow-1",
        "decided_at": "2026-05-10T00:00:00+00:00",
        "match_pass_id": match_pass_id,
        "group_id": group_id,
        "input_sha256": input_sha256,
        "had_shadow_payload": had_shadow,
        "agreement": agreement,
        "operational_winner_route_id": op_route_id,
        "operational_winner_route_name": f"Route {op_route_id}",
        "semantic_winner_route_id": sem_route_id,
        "semantic_winner_route_name": f"Route {sem_route_id}",
        "anchors_near_operational_winner": anchors_op,
        "anchors_near_semantic_winner": anchors_sem,
        "contributing_anchor_ids": (
            contrib_ids if contrib_ids is not None else ["a1", "a2", "a3"]
        ),
        "shadow_explanation": "test explanation",
    }


def _call_helper(
    label_rows: List[Dict[str, Any]],
    shadow_rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return main._compute_review_label_summary(label_rows, shadow_rows)


def _endpoint_summary() -> Dict[str, Any]:
    response = main.get_review_label_summary()
    return json.loads(response.body)


# ---------------------------------------------------------------------------
# Test suite
# ---------------------------------------------------------------------------

class TestReviewLabelSummary(unittest.TestCase):
    """Lock-down suite for Phase 1L review-label analytics summary."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._orig_rl_path = main.REVIEW_LABELS_PATH
        self._orig_sc_path = main.MATCH_SHADOW_COMPARE_PATH

        main.REVIEW_LABELS_PATH = Path(self._tmpdir.name) / "review_labels.jsonl"
        main.MATCH_SHADOW_COMPARE_PATH = (
            Path(self._tmpdir.name) / "match_shadow_compare.jsonl"
        )

    def tearDown(self) -> None:
        main.REVIEW_LABELS_PATH = self._orig_rl_path
        main.MATCH_SHADOW_COMPARE_PATH = self._orig_sc_path
        self._tmpdir.cleanup()

    # ------------------------------------------------------------------
    # 01 — empty inputs return valid skeleton
    # ------------------------------------------------------------------

    def test_01_empty_inputs_return_skeleton(self) -> None:
        """Both empty lists → valid skeleton with zero counts."""
        result = _call_helper([], [])
        self.assertEqual(result["schema_version"], "review-label-summary-1")
        self.assertEqual(result["total_review_labels"], 0)
        self.assertEqual(result["resolved_label_counts"]["useful_catch"], 0)
        self.assertEqual(result["window"]["resolved_labels"], 0)

    # ------------------------------------------------------------------
    # 02 — exact top-level key set (schema lock)
    # ------------------------------------------------------------------

    def test_02_endpoint_top_level_key_schema_lock(self) -> None:
        """Endpoint must return exactly the documented top-level keys."""
        result = _endpoint_summary()
        self.assertEqual(frozenset(result.keys()), EXPECTED_SUMMARY_TOP_KEYS)

    # ------------------------------------------------------------------
    # 03 — window keys exactly match spec
    # ------------------------------------------------------------------

    def test_03_window_key_set(self) -> None:
        """Helper window dict must contain exactly the 4 expected keys."""
        result = _call_helper(
            [_label_event()],
            [_shadow_row()],
        )
        self.assertEqual(frozenset(result["window"].keys()), EXPECTED_WINDOW_KEYS)

    # ------------------------------------------------------------------
    # 04 — resolved_label_counts correct
    # ------------------------------------------------------------------

    def test_04_resolved_label_counts_correct(self) -> None:
        """Counts for useful_catch / noise / unclear are accurate."""
        labels = [
            _label_event(label="useful_catch", group_id="G1"),
            _label_event(label="noise", group_id="G2"),
            _label_event(label="noise", group_id="G3"),
            _label_event(label="unclear", group_id="G4"),
        ]
        result = _call_helper(labels, [])
        self.assertEqual(result["resolved_label_counts"]["useful_catch"], 1)
        self.assertEqual(result["resolved_label_counts"]["noise"], 2)
        self.assertEqual(result["resolved_label_counts"]["unclear"], 1)

    # ------------------------------------------------------------------
    # 05 — latest-wins resolution: only last label per (pass_id, group_id)
    # ------------------------------------------------------------------

    def test_05_latest_wins_in_summary(self) -> None:
        """Two labels for same (pass_id, group_id): only last one counts."""
        labels = [
            _label_event(match_pass_id="p1", group_id="G1", label="unclear"),
            _label_event(match_pass_id="p1", group_id="G1", label="noise"),
        ]
        result = _call_helper(labels, [])
        # After latest-wins: only noise survives
        self.assertEqual(result["resolved_label_counts"]["noise"], 1)
        self.assertEqual(result["resolved_label_counts"]["unclear"], 0)
        self.assertEqual(result["window"]["resolved_labels"], 1)

    # ------------------------------------------------------------------
    # 06 — tombstone excluded from resolved counts
    # ------------------------------------------------------------------

    def test_06_tombstone_excluded_from_counts(self) -> None:
        """A tombstone as the latest event clears the label from counts."""
        labels = [
            _label_event(match_pass_id="p1", group_id="G1", label="useful_catch"),
            _label_event(
                match_pass_id="p1", group_id="G1", label="cleared", tombstone=True
            ),
        ]
        result = _call_helper(labels, [])
        self.assertEqual(result["resolved_label_counts"]["useful_catch"], 0)
        self.assertEqual(result["window"]["resolved_labels"], 0)

    # ------------------------------------------------------------------
    # 07 — malformed rows are silently skipped
    # ------------------------------------------------------------------

    def test_07_malformed_rows_skipped(self) -> None:
        """Non-dict, null, and missing-field rows must not raise."""
        bad_label_rows: List[Any] = [
            None,
            "not a dict",
            42,
            {},
            {"label": "useful_catch"},  # missing match_pass_id
            _label_event(),
        ]
        bad_shadow_rows: List[Any] = [
            None,
            "garbage",
            {},
        ]
        try:
            result = _call_helper(bad_label_rows, bad_shadow_rows)  # type: ignore[arg-type]
        except Exception as exc:
            self.fail(f"Helper raised on malformed input: {type(exc).__name__}: {exc}")
        # Should at least see the well-formed label
        self.assertGreaterEqual(result["total_review_labels"], 1)

    # ------------------------------------------------------------------
    # 08 — useful_catch_rate_by_review_priority calculation
    # ------------------------------------------------------------------

    def test_08_useful_catch_rate_by_priority(self) -> None:
        """Correct rate computed for elevated priority with >= MIN_SAMPLES labels."""
        # Build 4 disagreements with elevated priority (anch_op=0, anch_sem>=3)
        shadows = [
            _shadow_row(
                match_pass_id="p1",
                group_id=f"G{i}",
                anchors_op=0,
                anchors_sem=4,
                contrib_ids=["a1", "a2", "a3"],
            )
            for i in range(4)
        ]
        # Label 3 of them: 2 useful_catch, 1 noise
        labels = [
            _label_event(match_pass_id="p1", group_id="G0", label="useful_catch"),
            _label_event(match_pass_id="p1", group_id="G1", label="useful_catch"),
            _label_event(match_pass_id="p1", group_id="G2", label="noise"),
        ]
        result = _call_helper(labels, shadows)
        elevated = result["useful_catch_rate_by_review_priority"]["elevated"]
        self.assertEqual(elevated["labeled"], 3)
        self.assertEqual(elevated["useful_catch"], 2)
        # rate = 2/3 = 0.6667 (rounded to 4dp)
        self.assertIsNotNone(elevated["rate"])
        self.assertAlmostEqual(elevated["rate"], round(2 / 3, 4), places=4)

    # ------------------------------------------------------------------
    # 09 — zero division / small sample: rate is None when < MIN_SAMPLES
    # ------------------------------------------------------------------

    def test_09_rate_is_none_below_min_samples(self) -> None:
        """Rate fields are None when fewer than 3 labeled items exist."""
        shadows = [
            _shadow_row(
                match_pass_id="p1",
                group_id=f"G{i}",
                anchors_op=0,
                anchors_sem=4,
                contrib_ids=["a1", "a2", "a3"],
            )
            for i in range(2)
        ]
        labels = [
            _label_event(match_pass_id="p1", group_id="G0", label="useful_catch"),
            _label_event(match_pass_id="p1", group_id="G1", label="useful_catch"),
        ]
        result = _call_helper(labels, shadows)
        # Only 2 labeled — below MIN_SAMPLES=3
        elevated = result["useful_catch_rate_by_review_priority"]["elevated"]
        self.assertEqual(elevated["labeled"], 2)
        self.assertIsNone(elevated["rate"])

    # ------------------------------------------------------------------
    # 10 — useful_catch_rate_by_disagreement_kind calculation
    # ------------------------------------------------------------------

    def test_10_useful_catch_rate_by_kind(self) -> None:
        """Kind-level rate row appears when at least 1 label cross-references."""
        shadows = [
            _shadow_row(
                match_pass_id="p1",
                group_id=f"G{i}",
                anchors_op=0,
                anchors_sem=4,
                contrib_ids=["a1", "a2", "a3"],
            )
            for i in range(4)
        ]
        labels = [
            _label_event(match_pass_id="p1", group_id=f"G{i}", label="useful_catch")
            for i in range(4)
        ]
        result = _call_helper(labels, shadows)
        kind_rows = result["useful_catch_rate_by_disagreement_kind"]
        self.assertGreater(len(kind_rows), 0)
        # All 4 labeled as useful_catch → DOMINANT_SHADOW_SUPPORT row should have rate >= 0
        dom_rows = [r for r in kind_rows if r["kind"] == "DOMINANT_SHADOW_SUPPORT"]
        self.assertEqual(len(dom_rows), 1)
        self.assertEqual(dom_rows[0]["labeled"], 4)
        self.assertEqual(dom_rows[0]["useful_catch"], 4)
        # rate = 4/4 = 1.0
        self.assertIsNotNone(dom_rows[0]["rate"])
        self.assertAlmostEqual(dom_rows[0]["rate"], 1.0, places=4)

    # ------------------------------------------------------------------
    # 11 — label_coverage_by_review_priority correct
    # ------------------------------------------------------------------

    def test_11_label_coverage_by_priority(self) -> None:
        """Coverage rate = labeled / total_disagreements per priority."""
        # 4 elevated disagreements, label 3 of them
        shadows = [
            _shadow_row(
                match_pass_id="p1",
                group_id=f"G{i}",
                anchors_op=0,
                anchors_sem=4,
                contrib_ids=["a1", "a2", "a3"],
            )
            for i in range(4)
        ]
        labels = [
            _label_event(match_pass_id="p1", group_id=f"G{i}", label="useful_catch")
            for i in range(3)
        ]
        result = _call_helper(labels, shadows)
        coverage = result["label_coverage_by_review_priority"]["elevated"]
        self.assertEqual(coverage["total_disagreements"], 4)
        self.assertEqual(coverage["labeled"], 3)
        # coverage_rate = 3/4 = 0.75, but total=4 >= MIN_SAMPLES=3, so rate is set
        self.assertIsNotNone(coverage["coverage_rate"])
        self.assertAlmostEqual(coverage["coverage_rate"], round(3 / 4, 4), places=4)

    # ------------------------------------------------------------------
    # 12 — top_input_sha256_by_noise_rate respects MIN_SAMPLES
    # ------------------------------------------------------------------

    def test_12_top_sha_by_noise_rate_min_samples(self) -> None:
        """SHA with fewer than 3 labels is excluded from top_input_sha256_by_noise_rate."""
        # sha-A has 2 labels (below MIN_SAMPLES)
        labels = [
            _label_event(group_id="G1", label="noise", input_sha256="sha-A"),
            _label_event(group_id="G2", label="noise", input_sha256="sha-A"),
        ]
        result = _call_helper(labels, [])
        self.assertEqual(result["top_input_sha256_by_noise_rate"], [])

    # ------------------------------------------------------------------
    # 13 — top_input_sha256_by_noise_rate sorted by noise_rate desc
    # ------------------------------------------------------------------

    def test_13_top_sha_sorted_by_noise_rate(self) -> None:
        """SHAs with >= 3 labels are sorted by noise_rate descending."""
        # sha-HIGH: 3 noise out of 3 → rate 1.0
        # sha-LOW: 0 noise out of 3 → rate 0.0
        labels = (
            [
                _label_event(
                    match_pass_id="pX",
                    group_id=f"G{i}",
                    label="noise",
                    input_sha256="sha-HIGH",
                )
                for i in range(3)
            ]
            + [
                _label_event(
                    match_pass_id="pY",
                    group_id=f"H{i}",
                    label="useful_catch",
                    input_sha256="sha-LOW",
                )
                for i in range(3)
            ]
        )
        result = _call_helper(labels, [])
        top = result["top_input_sha256_by_noise_rate"]
        self.assertEqual(len(top), 2)
        self.assertEqual(top[0]["input_sha256"], "sha-HIGH")
        self.assertAlmostEqual(top[0]["noise_rate"], 1.0, places=4)
        self.assertEqual(top[1]["input_sha256"], "sha-LOW")
        self.assertAlmostEqual(top[1]["noise_rate"], 0.0, places=4)

    # ------------------------------------------------------------------
    # 14 — missing files → endpoint returns valid skeleton
    # ------------------------------------------------------------------

    def test_14_missing_files_endpoint_returns_skeleton(self) -> None:
        """Endpoint returns valid skeleton when both JSONL files are missing."""
        self.assertFalse(main.REVIEW_LABELS_PATH.exists())
        self.assertFalse(main.MATCH_SHADOW_COMPARE_PATH.exists())
        result = _endpoint_summary()
        self.assertEqual(result["schema_version"], "review-label-summary-1")
        self.assertEqual(result["total_review_labels"], 0)
        self.assertIn("generated_at", result)

    # ------------------------------------------------------------------
    # 15 — stability_note is present and contains expected prefix
    # ------------------------------------------------------------------

    def test_15_stability_note_present(self) -> None:
        """stability_note must be present and start with the expected prefix."""
        result = _call_helper([], [])
        note = result.get("stability_note", "")
        self.assertTrue(
            note.startswith(_STABILITY_NOTE_PREFIX),
            f"stability_note does not start with expected prefix.\n"
            f"Expected prefix: {_STABILITY_NOTE_PREFIX!r}\n"
            f"Got: {note!r}",
        )


if __name__ == "__main__":
    unittest.main()
