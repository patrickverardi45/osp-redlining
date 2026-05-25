"""Phase 1H-B-II (Part A) — match-shadow-1 compare row lock-down suite.

11 tests for ``_append_match_shadow_compare_entries`` and
``get_match_shadow_compare``, added in Phase 1H-A.

ISOLATION STRATEGY
------------------
Each test runs in an isolated ``tempfile.TemporaryDirectory``.
``main.MATCH_SHADOW_COMPARE_PATH`` and ``main.MATCH_SHADOW_COMPARE_MAX_ROWS``
are monkeypatched in ``setUp`` and restored in ``tearDown``.
``main._build_semantic_match_shadow`` is snapshotted and restored in
``tearDown``; individual tests override it in their own scope.
Relevant ``main.STATE`` fields are snapshotted and restored.
The real ``uploads/match_shadow_compare.jsonl`` is never touched.

IF A TEST FAILS after a legitimate Phase 1H-A change:
  1. Confirm the change is intentional.
  2. Update the relevant constant or assertion below.
  3. Add a comment explaining why.
  DO NOT "fix to green" without understanding the failure.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import main  # noqa: E402

# ---------------------------------------------------------------------------
# Exact key set produced by _append_match_shadow_compare_entries.
# Verified by inspection of live output.  Any change here means the schema
# changed — update with a comment.
# ---------------------------------------------------------------------------
EXPECTED_SC_ROW_KEYS: frozenset = frozenset(
    {
        "schema_version",
        "decided_at",
        "match_pass_id",
        "session_id_hint",
        "input_sha256",
        "shadow_version",
        "had_shadow_payload",
        "group_id",
        "group_index",
        "operational_winner_route_id",
        "operational_winner_route_name",
        "operational_confidence",
        "semantic_winner_route_id",
        "semantic_winner_route_name",
        "semantic_winner_score",
        "agreement",
        "anchors_near_operational_winner",
        "anchors_near_semantic_winner",
        "contributing_anchor_ids",
        "shadow_explanation",
    }
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _fake_operational_group(
    group_id: str = "G1",
    route_id: str = "R1",
    route_name: str = "Route R1",
    confidence: float = 0.9,
) -> Dict[str, Any]:
    """Minimal group_match dict covering all projected operational fields."""
    return {
        "group_id": group_id,
        "route_id": route_id,
        "route_name": route_name,
        "confidence": confidence,
    }


def _fake_shadow_group(
    group_id: str = "G1",
    semantic_best_route_id: str = "R2",
    semantic_best_route_name: str = "Route R2",
    semantic_best_score: float = 1.5,
    agreement: Optional[bool] = False,
    anchors_near_selected_route: int = 1,
    anchors_near_semantic_best_route: int = 3,
    contributing_anchor_ids: Optional[List[str]] = None,
    explanation: str = "Semantic prefers R2 over R1.",
) -> Dict[str, Any]:
    """Minimal shadow payload groups[i] dict covering all projected fields."""
    return {
        "group_id": group_id,
        "semantic_best_route_id": semantic_best_route_id,
        "semantic_best_route_name": semantic_best_route_name,
        "semantic_best_score": semantic_best_score,
        "agreement": agreement,
        "anchors_near_selected_route": anchors_near_selected_route,
        "anchors_near_semantic_best_route": anchors_near_semantic_best_route,
        "contributing_anchor_ids": (
            contributing_anchor_ids if contributing_anchor_ids is not None else ["a1"]
        ),
        "explanation": explanation,
    }


def _mock_shadow_payload(*shadow_groups: Dict[str, Any]) -> Callable:
    """Return a callable that yields a valid shadow payload with given groups."""
    def _shadow() -> Dict[str, Any]:
        return {"version": "shadow-1", "groups": list(shadow_groups)}
    return _shadow


def _read_sc_rows(path: Path) -> List[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    return [
        json.loads(line)
        for line in text.strip().splitlines()
        if line.strip()
    ]


def _endpoint_sc_entries(limit: int = 50) -> List[Dict[str, Any]]:
    response = main.get_match_shadow_compare(limit=limit)
    data: Dict[str, Any] = json.loads(response.body)
    return data.get("entries") or []


# ---------------------------------------------------------------------------
# Test suite
# ---------------------------------------------------------------------------

class TestMatchShadowCompare(unittest.TestCase):
    """Lock-down suite for Phase 1H-A per-group shadow-compare audit."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()

        self._orig_path = main.MATCH_SHADOW_COMPARE_PATH
        self._orig_max_rows = main.MATCH_SHADOW_COMPARE_MAX_ROWS
        self._orig_shadow: Callable = main._build_semantic_match_shadow  # type: ignore[assignment]

        main.MATCH_SHADOW_COMPARE_PATH = (
            Path(self._tmpdir.name) / "match_shadow_compare.jsonl"
        )

        # B-PERF-OPT-1: writer is env-gated default OFF. These tests verify
        # legacy behavior — set the flag ON for their duration. Gating itself
        # is verified by test_match_audit_gating.py.
        self._orig_sc_flag = os.environ.get("TRUELINE_MATCH_SHADOW_COMPARE_WRITE")
        os.environ["TRUELINE_MATCH_SHADOW_COMPARE_WRITE"] = "1"

        self._orig_session = main.STATE.get("_session_id_hint")
        self._orig_sha = main.STATE.get("last_kmz_input_sha256")

        main.STATE["_session_id_hint"] = "test-sc-session"
        main.STATE["last_kmz_input_sha256"] = None

        # Default: shadow unavailable (returns None) so most tests work
        # without setting up full semantic STATE.
        main._build_semantic_match_shadow = lambda: None  # type: ignore[assignment]

    def tearDown(self) -> None:
        main.STATE["last_kmz_input_sha256"] = self._orig_sha
        main.STATE["_session_id_hint"] = self._orig_session
        main._build_semantic_match_shadow = self._orig_shadow  # type: ignore[assignment]
        if self._orig_sc_flag is None:
            os.environ.pop("TRUELINE_MATCH_SHADOW_COMPARE_WRITE", None)
        else:
            os.environ["TRUELINE_MATCH_SHADOW_COMPARE_WRITE"] = self._orig_sc_flag
        main.MATCH_SHADOW_COMPARE_MAX_ROWS = self._orig_max_rows
        main.MATCH_SHADOW_COMPARE_PATH = self._orig_path
        self._tmpdir.cleanup()

    # ------------------------------------------------------------------
    # 01 — basic append + schema_version
    # ------------------------------------------------------------------

    def test_01_shadow_compare_creates_rows(self) -> None:
        """Two operational groups → 2 JSONL rows; schema_version == 'match-shadow-1'."""
        main._append_match_shadow_compare_entries(
            [_fake_operational_group("G1"), _fake_operational_group("G2")]
        )

        self.assertTrue(main.MATCH_SHADOW_COMPARE_PATH.exists())
        rows = _read_sc_rows(main.MATCH_SHADOW_COMPARE_PATH)
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertEqual(row["schema_version"], "match-shadow-1")

    # ------------------------------------------------------------------
    # 02 — match_pass_id shared within one call
    # ------------------------------------------------------------------

    def test_02_shadow_compare_shared_match_pass_id(self) -> None:
        """All rows from one helper call share the same match_pass_id."""
        main._append_match_shadow_compare_entries(
            [_fake_operational_group(f"G{i}") for i in range(3)]
        )

        rows = _read_sc_rows(main.MATCH_SHADOW_COMPARE_PATH)
        self.assertEqual(len(rows), 3)
        pass_ids = {r["match_pass_id"] for r in rows}
        self.assertEqual(len(pass_ids), 1, f"Expected 1 unique match_pass_id; got {pass_ids}")
        self.assertTrue(rows[0]["match_pass_id"])  # non-empty

    # ------------------------------------------------------------------
    # 03 — match_pass_id changes between calls
    # ------------------------------------------------------------------

    def test_03_shadow_compare_match_pass_changes_between_calls(self) -> None:
        """Two separate calls must produce different match_pass_ids."""
        main._append_match_shadow_compare_entries([_fake_operational_group("G1")])
        main._append_match_shadow_compare_entries([_fake_operational_group("G2")])

        rows = _read_sc_rows(main.MATCH_SHADOW_COMPARE_PATH)
        self.assertEqual(len(rows), 2)
        self.assertNotEqual(
            rows[0]["match_pass_id"],
            rows[1]["match_pass_id"],
            "Different calls must generate different match_pass_ids",
        )

    # ------------------------------------------------------------------
    # 04 — no shadow payload path
    # ------------------------------------------------------------------

    def test_04_shadow_compare_no_shadow_payload_path(self) -> None:
        """When _build_semantic_match_shadow raises, row must carry null semantic fields.

        had_shadow_payload must be False; semantic_* fields must be None;
        agreement must be None; contributing_anchor_ids must be [].
        The helper must not propagate the exception.
        """
        def _raises():
            raise RuntimeError("shadow unavailable")

        main._build_semantic_match_shadow = _raises  # type: ignore[assignment]

        try:
            main._append_match_shadow_compare_entries(
                [_fake_operational_group("G1")]
            )
        except Exception as exc:
            self.fail(f"Helper raised when shadow threw: {exc}")

        rows = _read_sc_rows(main.MATCH_SHADOW_COMPARE_PATH)
        self.assertEqual(len(rows), 1)
        row = rows[0]

        self.assertFalse(row["had_shadow_payload"])
        self.assertIsNone(row["semantic_winner_route_id"])
        self.assertIsNone(row["semantic_winner_route_name"])
        self.assertIsNone(row["semantic_winner_score"])
        self.assertIsNone(row["agreement"])
        self.assertEqual(row["contributing_anchor_ids"], [])
        self.assertIsNone(row["shadow_explanation"])
        self.assertIsNone(row["shadow_version"])

    # ------------------------------------------------------------------
    # 05 — contributing_anchor_ids capped at 10
    # ------------------------------------------------------------------

    def test_05_shadow_compare_anchor_ids_capped(self) -> None:
        """15 contributing_anchor_ids → persisted length == 10."""
        long_ids = [f"anchor_{i}" for i in range(15)]
        shadow_group = _fake_shadow_group("G1", contributing_anchor_ids=long_ids)
        main._build_semantic_match_shadow = _mock_shadow_payload(shadow_group)  # type: ignore[assignment]

        main._append_match_shadow_compare_entries([_fake_operational_group("G1")])

        rows = _read_sc_rows(main.MATCH_SHADOW_COMPARE_PATH)
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            len(rows[0]["contributing_anchor_ids"]),
            10,
            "contributing_anchor_ids must be capped at 10",
        )
        self.assertEqual(rows[0]["contributing_anchor_ids"][0], "anchor_0")
        self.assertEqual(rows[0]["contributing_anchor_ids"][9], "anchor_9")

    # ------------------------------------------------------------------
    # 06 — shadow_explanation truncated at 500 chars
    # ------------------------------------------------------------------

    def test_06_shadow_compare_explanation_truncated(self) -> None:
        """600-char explanation → persisted length <= 500."""
        long_expl = "X" * 600
        shadow_group = _fake_shadow_group("G1", explanation=long_expl)
        main._build_semantic_match_shadow = _mock_shadow_payload(shadow_group)  # type: ignore[assignment]

        main._append_match_shadow_compare_entries([_fake_operational_group("G1")])

        rows = _read_sc_rows(main.MATCH_SHADOW_COMPARE_PATH)
        self.assertEqual(len(rows), 1)
        persisted_expl = rows[0]["shadow_explanation"]
        self.assertIsNotNone(persisted_expl)
        self.assertLessEqual(
            len(persisted_expl),
            500,
            f"shadow_explanation must be truncated to 500 chars; got {len(persisted_expl)}",
        )

    # ------------------------------------------------------------------
    # 07 — row cap enforcement
    # ------------------------------------------------------------------

    def test_07_shadow_compare_truncates_to_max_rows(self) -> None:
        """Cap = 3; append 5 rows (5 calls × 1 group each) → 3 newest survive."""
        main.MATCH_SHADOW_COMPARE_MAX_ROWS = 3

        for i in range(5):
            main._append_match_shadow_compare_entries(
                [_fake_operational_group(f"G{i}")]
            )

        rows = _read_sc_rows(main.MATCH_SHADOW_COMPARE_PATH)
        self.assertEqual(len(rows), 3, f"Expected 3 rows after cap=3; got {len(rows)}")
        surviving = {r["group_id"] for r in rows}
        self.assertNotIn("G0", surviving, "G0 (oldest) must be truncated")
        self.assertNotIn("G1", surviving, "G1 (oldest) must be truncated")
        self.assertIn("G4", surviving, "G4 (newest) must survive")

    # ------------------------------------------------------------------
    # 08 — endpoint returns rows newest-first
    # ------------------------------------------------------------------

    def test_08_shadow_compare_reverse_chronological_endpoint(self) -> None:
        """Endpoint returns rows newest-first (reverse of append order).

        Append G0 → G1 → G2 via separate calls; expect G2, G1, G0.
        """
        for i in range(3):
            main._append_match_shadow_compare_entries(
                [_fake_operational_group(f"G{i}")]
            )

        entries = _endpoint_sc_entries(limit=10)
        self.assertEqual(len(entries), 3)
        self.assertEqual(entries[0]["group_id"], "G2", "Newest row must be first")
        self.assertEqual(entries[1]["group_id"], "G1")
        self.assertEqual(entries[2]["group_id"], "G0")

    # ------------------------------------------------------------------
    # 09 — input_sha256 passthrough
    # ------------------------------------------------------------------

    def test_09_shadow_compare_input_sha_passthrough(self) -> None:
        """Row must carry STATE['last_kmz_input_sha256'] unchanged."""
        expected_sha = "c" * 64
        main.STATE["last_kmz_input_sha256"] = expected_sha

        main._append_match_shadow_compare_entries([_fake_operational_group("G1")])

        rows = _read_sc_rows(main.MATCH_SHADOW_COMPARE_PATH)
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0]["input_sha256"],
            expected_sha,
            "input_sha256 must be forwarded from STATE unchanged",
        )

    # ------------------------------------------------------------------
    # 10 — exact 20-key schema
    # ------------------------------------------------------------------

    def test_10_shadow_compare_schema_exact_keys(self) -> None:
        """Persisted row key set must exactly match EXPECTED_SC_ROW_KEYS (20 keys).

        Failure here means the schema changed.  Update EXPECTED_SC_ROW_KEYS
        with a comment explaining why.
        """
        main._append_match_shadow_compare_entries([_fake_operational_group("G1")])

        rows = _read_sc_rows(main.MATCH_SHADOW_COMPARE_PATH)
        self.assertEqual(len(rows), 1)
        actual = frozenset(rows[0].keys())

        extra = actual - EXPECTED_SC_ROW_KEYS
        missing = EXPECTED_SC_ROW_KEYS - actual

        self.assertEqual(
            extra,
            frozenset(),
            f"Unexpected keys in shadow-compare row: {extra}",
        )
        self.assertEqual(
            missing,
            frozenset(),
            f"Expected keys missing from shadow-compare row: {missing}",
        )

    # ------------------------------------------------------------------
    # 11 — helper never raises
    # ------------------------------------------------------------------

    def test_11_shadow_compare_helper_never_raises(self) -> None:
        """Helper must swallow all exceptions and return None.

        Forces failure by pointing path at a non-existent parent directory.
        """
        main.MATCH_SHADOW_COMPARE_PATH = (
            Path(self._tmpdir.name) / "no_such_dir" / "sc.jsonl"
        )

        try:
            result = main._append_match_shadow_compare_entries(
                [_fake_operational_group("G1")]
            )
        except Exception as exc:
            self.fail(
                f"_append_match_shadow_compare_entries raised "
                f"{type(exc).__name__}: {exc}"
            )

        self.assertIsNone(result)
        self.assertFalse(main.MATCH_SHADOW_COMPARE_PATH.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
