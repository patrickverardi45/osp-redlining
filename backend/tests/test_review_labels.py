"""Phase 1K — review-label telemetry lock-down suite.

16 tests for ``_append_review_label``, ``post_review_label``,
``get_review_labels``, and ``get_review_labels_current``.

ISOLATION STRATEGY
------------------
Each test runs in an isolated ``tempfile.TemporaryDirectory``.
``main.REVIEW_LABELS_PATH`` and ``main.REVIEW_LABELS_MAX_ROWS`` are
monkeypatched in ``setUp`` and restored in ``tearDown``.
The real ``uploads/review_labels.jsonl`` is never touched.

REGRESSION ASSERTION
---------------------
test_16 verifies that no matching, scoring, or rendering code path in
main.py calls the review-label functions.  If that test fails after a code
change, investigate before proceeding.

IF A TEST FAILS after a legitimate Phase 1K change:
  1. Confirm the change is intentional.
  2. Update the relevant constant or assertion below.
  3. Add a comment explaining why.
  DO NOT "fix to green" without understanding the failure.
"""

from __future__ import annotations

import inspect
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
# Exact key set produced by _append_review_label.
# Any change here means the schema changed — update with a comment.
# ---------------------------------------------------------------------------
EXPECTED_RL_ROW_KEYS: frozenset = frozenset(
    {
        "schema_version",
        "labeled_at",
        "match_pass_id",
        "group_id",
        "input_sha256",
        "label",
        "previous_label",
        "reviewer_hint",
        "note",
        "tombstone",
    }
)

VALID_LABELS = {"useful_catch", "noise", "unclear", "cleared"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_rl_rows(path: Path) -> List[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    return [
        json.loads(line)
        for line in text.strip().splitlines()
        if line.strip()
    ]


def _endpoint_events(limit: int = 100) -> List[Dict[str, Any]]:
    response = main.get_review_labels(limit=limit)
    data: Dict[str, Any] = json.loads(response.body)
    return data.get("events") or []


def _endpoint_current(match_pass_id: str) -> List[Dict[str, Any]]:
    response = main.get_review_labels_current(match_pass_id=match_pass_id)
    data: Dict[str, Any] = json.loads(response.body)
    return data.get("resolved") or []


def _post_label(body: Dict[str, Any]) -> Dict[str, Any]:
    response = main.post_review_label(body=body)
    return json.loads(response.body)


# ---------------------------------------------------------------------------
# Test suite
# ---------------------------------------------------------------------------

class TestReviewLabels(unittest.TestCase):
    """Lock-down suite for Phase 1K review-label telemetry."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._orig_path = main.REVIEW_LABELS_PATH
        self._orig_max_rows = main.REVIEW_LABELS_MAX_ROWS

        main.REVIEW_LABELS_PATH = (
            Path(self._tmpdir.name) / "review_labels.jsonl"
        )

    def tearDown(self) -> None:
        main.REVIEW_LABELS_MAX_ROWS = self._orig_max_rows
        main.REVIEW_LABELS_PATH = self._orig_path
        self._tmpdir.cleanup()

    # ------------------------------------------------------------------
    # 01 — append creates file with correct schema_version
    # ------------------------------------------------------------------

    def test_01_append_creates_file_with_schema_version(self) -> None:
        """_append_review_label creates the file; schema_version == 'review-label-1'."""
        main._append_review_label(
            match_pass_id="pass-001",
            group_id="G1",
            input_sha256=None,
            label="useful_catch",
        )
        self.assertTrue(main.REVIEW_LABELS_PATH.exists())
        rows = _read_rl_rows(main.REVIEW_LABELS_PATH)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["schema_version"], "review-label-1")

    # ------------------------------------------------------------------
    # 02 — exact key set
    # ------------------------------------------------------------------

    def test_02_exact_row_key_set(self) -> None:
        """Every appended row has exactly the documented 10 keys."""
        main._append_review_label(
            match_pass_id="pass-002",
            group_id="G1",
            input_sha256="abc123",
            label="noise",
            previous_label="useful_catch",
            reviewer_hint="hint text",
            note="a note",
            tombstone=False,
        )
        rows = _read_rl_rows(main.REVIEW_LABELS_PATH)
        self.assertEqual(frozenset(rows[0].keys()), EXPECTED_RL_ROW_KEYS)

    # ------------------------------------------------------------------
    # 03 — all valid labels are accepted by POST endpoint
    # ------------------------------------------------------------------

    def test_03_valid_labels_accepted(self) -> None:
        """POST accepts all four valid label values."""
        for lbl in VALID_LABELS:
            result = _post_label({"match_pass_id": f"pass-{lbl}", "label": lbl})
            self.assertTrue(result.get("accepted"), f"Expected accepted for label={lbl}")
            self.assertEqual(result.get("label"), lbl)

    # ------------------------------------------------------------------
    # 04 — invalid label → silent no-op
    # ------------------------------------------------------------------

    def test_04_invalid_label_silent_noop(self) -> None:
        """Invalid label value → accepted=False, no file created."""
        result = _post_label({"match_pass_id": "pass-x", "label": "wrong_value"})
        self.assertFalse(result.get("accepted"))
        self.assertIsNone(result.get("label"))
        self.assertFalse(main.REVIEW_LABELS_PATH.exists())

    # ------------------------------------------------------------------
    # 05 — missing match_pass_id → silent no-op
    # ------------------------------------------------------------------

    def test_05_missing_match_pass_id_silent_noop(self) -> None:
        """Missing or empty match_pass_id → accepted=False, no file created."""
        for body in [
            {"label": "noise"},
            {"match_pass_id": "", "label": "noise"},
            {"match_pass_id": "   ", "label": "noise"},
        ]:
            result = _post_label(body)
            self.assertFalse(result.get("accepted"), f"Expected rejected for body={body}")
        self.assertFalse(main.REVIEW_LABELS_PATH.exists())

    # ------------------------------------------------------------------
    # 06 — append is append-only; old rows are never mutated
    # ------------------------------------------------------------------

    def test_06_append_is_append_only(self) -> None:
        """Multiple appends grow the file; old rows survive unchanged."""
        main._append_review_label(
            match_pass_id="pass-A", group_id="G1", input_sha256=None, label="noise"
        )
        main._append_review_label(
            match_pass_id="pass-A", group_id="G2", input_sha256=None, label="unclear"
        )
        rows = _read_rl_rows(main.REVIEW_LABELS_PATH)
        self.assertEqual(len(rows), 2)
        # First row untouched
        self.assertEqual(rows[0]["label"], "noise")
        self.assertEqual(rows[0]["group_id"], "G1")

    # ------------------------------------------------------------------
    # 07 — truncation at cap
    # ------------------------------------------------------------------

    def test_07_truncation_at_cap(self) -> None:
        """File is tail-truncated to REVIEW_LABELS_MAX_ROWS after append."""
        main.REVIEW_LABELS_MAX_ROWS = 3
        for i in range(5):
            main._append_review_label(
                match_pass_id="pass-cap",
                group_id=f"G{i}",
                input_sha256=None,
                label="noise",
            )
        rows = _read_rl_rows(main.REVIEW_LABELS_PATH)
        self.assertEqual(len(rows), 3)
        # Should retain the 3 newest (G2, G3, G4)
        group_ids = [r["group_id"] for r in rows]
        self.assertEqual(group_ids, ["G2", "G3", "G4"])

    # ------------------------------------------------------------------
    # 08 — GET events returns newest-first
    # ------------------------------------------------------------------

    def test_08_get_events_newest_first(self) -> None:
        """GET /review-labels returns rows newest-first."""
        for i in range(3):
            main._append_review_label(
                match_pass_id="pass-ord",
                group_id=f"G{i}",
                input_sha256=None,
                label="unclear",
            )
        events = _endpoint_events(limit=10)
        self.assertEqual(len(events), 3)
        group_ids = [e["group_id"] for e in events]
        # Newest first → G2, G1, G0
        self.assertEqual(group_ids, ["G2", "G1", "G0"])

    # ------------------------------------------------------------------
    # 09 — GET events missing file → empty list
    # ------------------------------------------------------------------

    def test_09_get_events_missing_file_returns_empty(self) -> None:
        """GET /review-labels with no file returns {"events": []}."""
        self.assertFalse(main.REVIEW_LABELS_PATH.exists())
        events = _endpoint_events()
        self.assertEqual(events, [])

    # ------------------------------------------------------------------
    # 10 — current endpoint latest-wins resolution
    # ------------------------------------------------------------------

    def test_10_current_latest_wins_resolution(self) -> None:
        """GET /review-labels/current resolves to last label per group_id."""
        # Write two labels for the same group; second should win.
        main._append_review_label(
            match_pass_id="pass-lw",
            group_id="G1",
            input_sha256=None,
            label="unclear",
        )
        main._append_review_label(
            match_pass_id="pass-lw",
            group_id="G1",
            input_sha256=None,
            label="noise",
        )
        resolved = _endpoint_current("pass-lw")
        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0]["label"], "noise")
        self.assertEqual(resolved[0]["group_id"], "G1")

    # ------------------------------------------------------------------
    # 11 — tombstone excludes entry from resolved output
    # ------------------------------------------------------------------

    def test_11_tombstone_excluded_from_resolved(self) -> None:
        """A tombstone entry is excluded from GET /review-labels/current."""
        main._append_review_label(
            match_pass_id="pass-tb",
            group_id="G1",
            input_sha256=None,
            label="useful_catch",
        )
        # Tombstone overwrites the previous label
        main._append_review_label(
            match_pass_id="pass-tb",
            group_id="G1",
            input_sha256=None,
            label="cleared",
            tombstone=True,
        )
        resolved = _endpoint_current("pass-tb")
        # Tombstoned → no entry in resolved
        self.assertEqual(resolved, [])

    # ------------------------------------------------------------------
    # 12 — current endpoint missing file → empty
    # ------------------------------------------------------------------

    def test_12_current_missing_file_returns_empty(self) -> None:
        """GET /review-labels/current with no file returns {"resolved": []}."""
        self.assertFalse(main.REVIEW_LABELS_PATH.exists())
        resolved = _endpoint_current("pass-abc")
        self.assertEqual(resolved, [])

    # ------------------------------------------------------------------
    # 13 — current endpoint missing match_pass_id → empty
    # ------------------------------------------------------------------

    def test_13_current_empty_match_pass_id_returns_empty(self) -> None:
        """GET /review-labels/current with empty match_pass_id → {"resolved": []}."""
        main._append_review_label(
            match_pass_id="pass-real",
            group_id="G1",
            input_sha256=None,
            label="noise",
        )
        for mpid in ["", "   "]:
            resolved = _endpoint_current(mpid)
            self.assertEqual(
                resolved, [], f"Expected [] for match_pass_id={repr(mpid)}"
            )

    # ------------------------------------------------------------------
    # 14 — helper never raises on bad input
    # ------------------------------------------------------------------

    def test_14_helper_never_raises_on_bad_input(self) -> None:
        """_append_review_label never raises regardless of argument types."""
        bad_inputs = [
            dict(match_pass_id=None, group_id=None, input_sha256=None, label="noise"),  # type: ignore[arg-type]
            dict(match_pass_id=123, group_id=456, input_sha256=None, label="unclear"),  # type: ignore[arg-type]
            dict(match_pass_id="p", group_id="g", input_sha256="s", label="useful_catch",
                 note="\x00" * 1000, reviewer_hint=object()),  # type: ignore[arg-type]
        ]
        for kwargs in bad_inputs:
            try:
                main._append_review_label(**kwargs)
            except Exception as exc:  # noqa: BLE001
                self.fail(f"_append_review_label raised {type(exc).__name__}: {exc}")

    # ------------------------------------------------------------------
    # 15 — helper never raises when path is unwritable
    # ------------------------------------------------------------------

    def test_15_helper_never_raises_when_path_unwritable(self) -> None:
        """_append_review_label silently ignores I/O failures."""
        main.REVIEW_LABELS_PATH = Path("/nonexistent_dir_xyz/review_labels.jsonl")
        try:
            main._append_review_label(
                match_pass_id="pass-io",
                group_id="G1",
                input_sha256=None,
                label="noise",
            )
        except Exception as exc:
            self.fail(f"Helper raised on bad path: {type(exc).__name__}: {exc}")
        finally:
            main.REVIEW_LABELS_PATH = (
                Path(self._tmpdir.name) / "review_labels.jsonl"
            )

    # ------------------------------------------------------------------
    # 16 — regression: matching/scoring code does NOT call label functions
    # ------------------------------------------------------------------

    def test_16_matching_code_does_not_call_label_functions(self) -> None:
        """No matching, scoring, or rendering function calls review-label helpers.

        This is the key isolation regression test.  If it fails after a code
        change, investigate before proceeding — it means labels may be leaking
        into operational behavior.
        """
        _LABEL_FUNCTIONS = {
            "_append_review_label",
            "get_review_labels",
            "get_review_labels_current",
            "post_review_label",
            "REVIEW_LABELS_PATH",
        }

        # Functions that are operationally active (matching, scoring, rendering).
        # We check that their source code does not reference any label function.
        _OPERATIONAL_FUNCTIONS = [
            "_match_bore_groups_to_routes",
            "_build_semantic_match_shadow",
            "_build_kmz_semantic",
            "_append_match_shadow_compare_entries",
            "_append_match_audit_entry",
            "_append_match_audit_v2_entries",
            "_compute_match_shadow_summary",
            "_compute_match_shadow_disagreements",
        ]

        for fn_name in _OPERATIONAL_FUNCTIONS:
            fn = getattr(main, fn_name, None)
            if fn is None:
                continue
            try:
                src = inspect.getsource(fn)
            except (OSError, TypeError):
                continue
            for label_fn in _LABEL_FUNCTIONS:
                self.assertNotIn(
                    label_fn,
                    src,
                    f"ISOLATION VIOLATION: {fn_name} references {label_fn}. "
                    f"Labels must never influence operational behavior.",
                )


if __name__ == "__main__":
    unittest.main()
