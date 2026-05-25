"""Phase 1G-B — MatchAudit v2 (match-audit-2) lock-down regression suite.

12 tests that lock down the behaviour of ``_append_match_audit_v2_entries``
and ``get_match_audit_groups`` added in Phase 1G.

ISOLATION STRATEGY
------------------
Each test runs in an isolated ``tempfile.TemporaryDirectory``.  Module-level
globals ``main.MATCH_AUDIT_GROUPS_PATH`` and ``main.MATCH_AUDIT_GROUPS_MAX_ROWS``
are monkeypatched in ``setUp`` and restored in ``tearDown``.
``main._build_semantic_match_shadow`` is snapshotted and restored in
``tearDown``; individual tests may override it in their own scope.
``main.STATE`` fields consumed by the helper are snapshotted and restored.
The real ``uploads/match_audit_groups.jsonl`` is never touched.

``get_match_audit_groups`` is called directly — no HTTP server is started.

NOTE: The schema has 26 keys (the design document said "27" but the
implementation produces 26; this test locks down the implementation).

IF A TEST FAILS after a legitimate Phase 1G change:
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

# Put backend/ on sys.path so ``import main`` works regardless of cwd.
_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import main  # noqa: E402

# ---------------------------------------------------------------------------
# Exact key set produced by _append_match_audit_v2_entries.
# Verified by running the helper and inspecting output.  Any change here
# means the schema changed — update with a comment explaining why.
# ---------------------------------------------------------------------------
EXPECTED_V2_ROW_KEYS: frozenset = frozenset(
    {
        "schema_version",
        "decided_at",
        "match_pass_id",
        "session_id_hint",
        "input_sha256",
        "group_id",
        "source_file",
        "print",
        "winning_route_id",
        "winning_route_name",
        "winning_route_role",
        "confidence",
        "confidence_label",
        "final_decision",
        "expected_span_ft",
        "length_gap_ft",
        "validation_status",
        "render_allowed",
        "render_mode",
        "render_block_reasons",
        "rendered_station_point_count",
        "rendered_redline_segment_count",
        "anchor_reasons",
        "candidate_rankings_top3",
        "candidate_rankings_total_count",
        "semantic_shadow_available",
    }
)


# ---------------------------------------------------------------------------
# Synthetic fixture helpers
# ---------------------------------------------------------------------------

def _fake_ranking(
    route_id: str = "R1",
    score: float = 0.9,
    route_length_ft: float = 5000.0,
) -> Dict[str, Any]:
    """Minimal candidate_rankings entry covering all projected fields."""
    return {
        "route_id": route_id,
        "route_name": f"Route {route_id}",
        "route_role": "backbone",
        "route_length_ft": route_length_ft,
        "expected_span_ft": route_length_ft * 0.95,
        "length_gap_ft": route_length_ft * 0.05,
        "score": score,
    }


def _fake_group_match(
    group_id: str = "G1",
    route_id: str = "R1",
    route_name: str = "Test Route",
    route_role: str = "backbone",
    confidence: float = 0.92,
    confidence_label: str = "high",
    final_decision: str = "anchor score dominant",
    expected_span_ft: float = 5000.0,
    length_gap_ft: float = 50.0,
    render_allowed: bool = True,
    render_block_reasons: Optional[List[str]] = None,
    render_mode: str = "normal",
    validation_status: str = "pass",
    rendered_station_point_count: int = 10,
    rendered_redline_segment_count: int = 5,
    anchor_reasons: Optional[List[str]] = None,
    candidate_rankings: Optional[List[Dict[str, Any]]] = None,
    source_file: str = "bore.csv",
    print_val: str = "17+50",
) -> Dict[str, Any]:
    """Return a group_match dict with all fields the v2 helper projects."""
    return {
        "route_id": route_id,
        "route_name": route_name,
        "route_role": route_role,
        "confidence": confidence,
        "confidence_label": confidence_label,
        "final_decision": final_decision,
        "expected_span_ft": expected_span_ft,
        "length_gap_ft": length_gap_ft,
        "render_allowed": render_allowed,
        "render_block_reasons": render_block_reasons or [],
        "validation": {
            "render_gate": {"mode": render_mode},
            "validation_status": validation_status,
        },
        "rendered_station_point_count": rendered_station_point_count,
        "rendered_redline_segment_count": rendered_redline_segment_count,
        "selected_hypothesis": {
            "anchor_reasons": anchor_reasons or ["anchor matched route segment"],
        },
        "candidate_rankings": candidate_rankings
        if candidate_rankings is not None
        else [_fake_ranking("R1")],
        "group_id": group_id,
        "source_file": source_file,
        "print": print_val,
    }


def _read_v2_rows(path: Path) -> List[Dict[str, Any]]:
    """Return all valid JSONL rows from *path* in append (file) order."""
    text = path.read_text(encoding="utf-8")
    return [
        json.loads(line)
        for line in text.strip().splitlines()
        if line.strip()
    ]


def _endpoint_v2_entries(limit: int = 50) -> List[Dict[str, Any]]:
    """Call ``get_match_audit_groups`` directly; return its entries list."""
    response = main.get_match_audit_groups(limit=limit)
    data: Dict[str, Any] = json.loads(response.body)
    return data.get("entries") or []


# ---------------------------------------------------------------------------
# Test suite
# ---------------------------------------------------------------------------

class TestMatchAuditV2(unittest.TestCase):
    """Lock-down regression suite for Phase 1G per-group MatchAudit."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()

        # Snapshot and patch module globals.
        self._orig_path = main.MATCH_AUDIT_GROUPS_PATH
        self._orig_max_rows = main.MATCH_AUDIT_GROUPS_MAX_ROWS
        self._orig_shadow_fn: Callable = main._build_semantic_match_shadow  # type: ignore[assignment]

        main.MATCH_AUDIT_GROUPS_PATH = (
            Path(self._tmpdir.name) / "match_audit_groups.jsonl"
        )
        # max_rows stays at production default unless a test overrides it.

        # B-PERF-OPT-1: writer is env-gated default OFF. These tests verify
        # legacy behavior — set the flag ON for their duration. Gating itself
        # is verified by test_match_audit_gating.py.
        self._orig_audit_flag = os.environ.get("TRUELINE_MATCH_AUDIT_V2_WRITE")
        os.environ["TRUELINE_MATCH_AUDIT_V2_WRITE"] = "1"

        # Snapshot STATE fields that _append_match_audit_v2_entries reads.
        self._orig_session = main.STATE.get("_session_id_hint")
        self._orig_sha = main.STATE.get("last_kmz_input_sha256")
        self._orig_catalog = main.STATE.get("route_catalog")

        main.STATE["_session_id_hint"] = "test-v2-session"
        main.STATE["last_kmz_input_sha256"] = None
        main.STATE["route_catalog"] = []

    def tearDown(self) -> None:
        # Restore STATE.
        main.STATE["route_catalog"] = self._orig_catalog
        main.STATE["last_kmz_input_sha256"] = self._orig_sha
        main.STATE["_session_id_hint"] = self._orig_session

        # Restore env flag.
        if self._orig_audit_flag is None:
            os.environ.pop("TRUELINE_MATCH_AUDIT_V2_WRITE", None)
        else:
            os.environ["TRUELINE_MATCH_AUDIT_V2_WRITE"] = self._orig_audit_flag

        # Restore module globals.
        main._build_semantic_match_shadow = self._orig_shadow_fn  # type: ignore[assignment]
        main.MATCH_AUDIT_GROUPS_MAX_ROWS = self._orig_max_rows
        main.MATCH_AUDIT_GROUPS_PATH = self._orig_path

        self._tmpdir.cleanup()

    # ------------------------------------------------------------------
    # 01 — basic append + schema_version smoke
    # ------------------------------------------------------------------

    def test_01_append_match_audit_v2_creates_rows(self) -> None:
        """Two group matches → two JSONL rows; each carries schema_version='match-audit-2'."""
        matches = [
            _fake_group_match("G1", route_id="R1"),
            _fake_group_match("G2", route_id="R2"),
        ]
        main._append_match_audit_v2_entries(matches)

        self.assertTrue(
            main.MATCH_AUDIT_GROUPS_PATH.exists(),
            "match_audit_groups.jsonl must be created",
        )
        rows = _read_v2_rows(main.MATCH_AUDIT_GROUPS_PATH)
        self.assertEqual(len(rows), 2, "Expected 2 rows")
        for i, row in enumerate(rows):
            with self.subTest(row_index=i):
                self.assertEqual(row["schema_version"], "match-audit-2")

    # ------------------------------------------------------------------
    # 02 — match_pass_id shared within a single call
    # ------------------------------------------------------------------

    def test_02_match_pass_id_shared_per_call(self) -> None:
        """All rows from one helper call must share the same match_pass_id."""
        matches = [
            _fake_group_match(f"G{i}", route_id=f"R{i}") for i in range(3)
        ]
        main._append_match_audit_v2_entries(matches)

        rows = _read_v2_rows(main.MATCH_AUDIT_GROUPS_PATH)
        self.assertEqual(len(rows), 3)

        pass_ids = {r["match_pass_id"] for r in rows}
        self.assertEqual(
            len(pass_ids),
            1,
            f"All rows in one call must share one match_pass_id; got {pass_ids}",
        )
        # Sanity: pass_id must be a non-empty string (uuid4 format not asserted).
        self.assertTrue(rows[0]["match_pass_id"])

    # ------------------------------------------------------------------
    # 03 — match_pass_id changes between calls
    # ------------------------------------------------------------------

    def test_03_match_pass_id_changes_between_calls(self) -> None:
        """Two separate helper calls must produce different match_pass_ids."""
        main._append_match_audit_v2_entries([_fake_group_match("G1")])
        main._append_match_audit_v2_entries([_fake_group_match("G2")])

        rows = _read_v2_rows(main.MATCH_AUDIT_GROUPS_PATH)
        self.assertEqual(len(rows), 2)
        self.assertNotEqual(
            rows[0]["match_pass_id"],
            rows[1]["match_pass_id"],
            "Different calls must generate different match_pass_ids",
        )

    # ------------------------------------------------------------------
    # 04 — candidate_rankings_top3 capped at 3
    # ------------------------------------------------------------------

    def test_04_candidate_rankings_top3_capped(self) -> None:
        """5 candidate_rankings provided → persisted top3 length == 3; total_count == 5."""
        rankings = [_fake_ranking(f"R{i}", score=0.9 - i * 0.1) for i in range(5)]
        match = _fake_group_match("G1", candidate_rankings=rankings)
        main._append_match_audit_v2_entries([match])

        rows = _read_v2_rows(main.MATCH_AUDIT_GROUPS_PATH)
        self.assertEqual(len(rows), 1)
        row = rows[0]

        self.assertEqual(
            len(row["candidate_rankings_top3"]),
            3,
            "candidate_rankings_top3 must be capped at 3",
        )
        self.assertEqual(
            row["candidate_rankings_total_count"],
            5,
            "candidate_rankings_total_count must reflect the full list length",
        )
        # First entry must be the first ranking (R0, highest score).
        self.assertEqual(row["candidate_rankings_top3"][0]["route_id"], "R0")

    # ------------------------------------------------------------------
    # 05 — anchor_reasons capped at 5 and each ≤ 200 chars
    # ------------------------------------------------------------------

    def test_05_anchor_reasons_capped_and_truncated(self) -> None:
        """7 anchor_reasons with 300-char strings → at most 5 survive, each ≤ 200 chars."""
        long_reason = "A" * 300  # 300 chars > 200-char cap
        reasons = [f"Reason {i}: {long_reason}" for i in range(7)]
        match = _fake_group_match("G1", anchor_reasons=reasons)
        main._append_match_audit_v2_entries([match])

        rows = _read_v2_rows(main.MATCH_AUDIT_GROUPS_PATH)
        row = rows[0]

        persisted = row["anchor_reasons"]
        self.assertLessEqual(
            len(persisted),
            5,
            f"anchor_reasons must be capped at 5; got {len(persisted)}",
        )
        for reason_str in persisted:
            self.assertLessEqual(
                len(reason_str),
                200,
                f"Each anchor_reason must be ≤ 200 chars; got {len(reason_str)}",
            )

    # ------------------------------------------------------------------
    # 06 — render_block_reasons capped at 10
    # ------------------------------------------------------------------

    def test_06_render_block_reasons_capped(self) -> None:
        """15 render_block_reasons provided → persisted list length == 10."""
        reasons = [f"block_reason_{i}" for i in range(15)]
        match = _fake_group_match(
            "G1",
            render_allowed=False,
            render_block_reasons=reasons,
            validation_status="fail",
        )
        main._append_match_audit_v2_entries([match])

        rows = _read_v2_rows(main.MATCH_AUDIT_GROUPS_PATH)
        row = rows[0]

        self.assertEqual(
            len(row["render_block_reasons"]),
            10,
            f"render_block_reasons must be capped at 10; got {len(row['render_block_reasons'])}",
        )
        # First 10 reasons must survive (list[:10]).
        self.assertEqual(row["render_block_reasons"][0], "block_reason_0")
        self.assertEqual(row["render_block_reasons"][9], "block_reason_9")

    # ------------------------------------------------------------------
    # 07 — row-cap enforcement
    # ------------------------------------------------------------------

    def test_07_match_audit_v2_truncates_to_max_rows(self) -> None:
        """Cap = 3; append 5 rows total (across 5 calls of 1 match each) → 3 survive."""
        main.MATCH_AUDIT_GROUPS_MAX_ROWS = 3

        for i in range(5):
            main._append_match_audit_v2_entries(
                [_fake_group_match(f"G{i}", route_id=f"R{i}")]
            )

        rows = _read_v2_rows(main.MATCH_AUDIT_GROUPS_PATH)
        self.assertEqual(
            len(rows),
            3,
            f"Expected 3 rows after truncation at cap=3, got {len(rows)}",
        )
        # Oldest rows (G0, G1) must be gone; newest (G4) must survive.
        surviving_gids = [r["group_id"] for r in rows]
        self.assertNotIn("G0", surviving_gids, "G0 must be truncated (oldest)")
        self.assertNotIn("G1", surviving_gids, "G1 must be truncated (oldest)")
        self.assertIn("G4", surviving_gids, "G4 (most recent) must survive")

    # ------------------------------------------------------------------
    # 08 — endpoint returns rows newest-first
    # ------------------------------------------------------------------

    def test_08_match_audit_v2_reverse_chronological_endpoint(self) -> None:
        """Endpoint must return rows newest-first (reverse of append order).

        Append G0 → G1 → G2 via separate calls.  Endpoint must return G2, G1, G0.
        Order is based on file-line reversal, not timestamp comparison.
        """
        for i in range(3):
            main._append_match_audit_v2_entries(
                [_fake_group_match(f"G{i}", route_id=f"R{i}")]
            )

        entries = _endpoint_v2_entries(limit=10)
        self.assertEqual(len(entries), 3)
        self.assertEqual(
            entries[0]["group_id"],
            "G2",
            "Most recently appended group must appear first",
        )
        self.assertEqual(entries[1]["group_id"], "G1")
        self.assertEqual(entries[2]["group_id"], "G0")

    # ------------------------------------------------------------------
    # 09 — input_sha256 passthrough
    # ------------------------------------------------------------------

    def test_09_match_audit_v2_input_sha_passthrough(self) -> None:
        """Row must carry STATE['last_kmz_input_sha256'] unchanged."""
        expected_sha = "b" * 64  # deterministic fixture value
        main.STATE["last_kmz_input_sha256"] = expected_sha

        main._append_match_audit_v2_entries([_fake_group_match("G1")])

        rows = _read_v2_rows(main.MATCH_AUDIT_GROUPS_PATH)
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0]["input_sha256"],
            expected_sha,
            "input_sha256 must be forwarded from STATE unchanged",
        )

    # ------------------------------------------------------------------
    # 10 — semantic_shadow_available presence-only, resilient to exception
    # ------------------------------------------------------------------

    def test_10_match_audit_v2_semantic_shadow_presence_only(self) -> None:
        """semantic_shadow_available must reflect shadow presence; shadow errors → False.

        Part A: monkeypatch returns a non-None dict → True.
        Part B: monkeypatch raises → False, helper must not propagate the exception.
        """
        # ── Part A: shadow present ───────────────────────────────────────────
        main._build_semantic_match_shadow = lambda: {"groups": [], "present": True}  # type: ignore[assignment]
        main._append_match_audit_v2_entries([_fake_group_match("GA")])

        rows = _read_v2_rows(main.MATCH_AUDIT_GROUPS_PATH)
        self.assertEqual(len(rows), 1)
        self.assertTrue(
            rows[0]["semantic_shadow_available"],
            "semantic_shadow_available must be True when shadow returns a dict",
        )

        # ── Part B: shadow raises → False, no propagation ────────────────────
        # Point to a new file so we start fresh for part B.
        main.MATCH_AUDIT_GROUPS_PATH = (
            Path(self._tmpdir.name) / "mg_part_b.jsonl"
        )

        def _shadow_raises() -> None:
            raise RuntimeError("shadow computation failed")

        main._build_semantic_match_shadow = _shadow_raises  # type: ignore[assignment]

        try:
            main._append_match_audit_v2_entries([_fake_group_match("GB")])
        except Exception as exc:
            self.fail(
                f"Helper raised when _build_semantic_match_shadow threw: {exc}"
            )

        rows_b = _read_v2_rows(main.MATCH_AUDIT_GROUPS_PATH)
        self.assertEqual(len(rows_b), 1)
        self.assertFalse(
            rows_b[0]["semantic_shadow_available"],
            "semantic_shadow_available must be False when shadow raises",
        )

    # ------------------------------------------------------------------
    # 11 — exact schema key set
    # ------------------------------------------------------------------

    def test_11_match_audit_v2_schema_exact_keys(self) -> None:
        """Persisted row key set must match EXPECTED_V2_ROW_KEYS exactly.

        Failure here means the schema changed (key added or removed).
        Update EXPECTED_V2_ROW_KEYS with a comment explaining why.
        """
        main._append_match_audit_v2_entries([_fake_group_match("G1")])

        rows = _read_v2_rows(main.MATCH_AUDIT_GROUPS_PATH)
        self.assertEqual(len(rows), 1)

        actual_keys = frozenset(rows[0].keys())
        extra = actual_keys - EXPECTED_V2_ROW_KEYS
        missing = EXPECTED_V2_ROW_KEYS - actual_keys

        self.assertEqual(
            extra,
            frozenset(),
            f"Unexpected keys found in v2 row: {extra}. "
            "Add them to EXPECTED_V2_ROW_KEYS with a comment.",
        )
        self.assertEqual(
            missing,
            frozenset(),
            f"Expected keys missing from v2 row: {missing}. "
            "Remove them from EXPECTED_V2_ROW_KEYS if intentionally dropped.",
        )

    # ------------------------------------------------------------------
    # 12 — helper never raises
    # ------------------------------------------------------------------

    def test_12_match_audit_v2_helper_never_raises(self) -> None:
        """_append_match_audit_v2_entries must never propagate an exception.

        Forces the helper into an error path by pointing MATCH_AUDIT_GROUPS_PATH
        at a path whose parent directory does not exist.
        """
        main.MATCH_AUDIT_GROUPS_PATH = (
            Path(self._tmpdir.name) / "does_not_exist" / "match_audit_groups.jsonl"
        )

        try:
            result = main._append_match_audit_v2_entries([_fake_group_match("G1")])
        except Exception as exc:
            self.fail(
                f"_append_match_audit_v2_entries raised {type(exc).__name__}: {exc}"
            )

        # Helper returns None on both success and failure paths.
        self.assertIsNone(result)
        # File must not have been created.
        self.assertFalse(
            main.MATCH_AUDIT_GROUPS_PATH.exists(),
            "No file should be created when the parent directory is missing",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
