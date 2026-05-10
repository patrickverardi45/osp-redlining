"""Phase 1F-B — MatchAudit lock-down regression suite.

7 tests that lock down the behaviour of ``_append_match_audit_entry`` and
``get_match_audit`` added in Phase 1F.

ISOLATION STRATEGY
------------------
Each test runs in an isolated ``tempfile.TemporaryDirectory``.  The module-level
globals ``main.MATCH_AUDIT_PATH`` and ``main.MATCH_AUDIT_MAX_ROWS`` are
monkeypatched in ``setUp`` and restored in ``tearDown``.  The real
``uploads/match_audit.jsonl`` is never touched.

``main.STATE`` entries that the helper reads
(``_session_id_hint``, ``last_kmz_input_sha256``, ``route_catalog``) are
snapshotted and restored the same way.

The GET endpoint function ``get_match_audit`` is called directly — no HTTP
server is started, no HTTP client library is used.  ``response.body`` is
bytes returned by Starlette's ``JSONResponse``.

IF A TEST FAILS after a legitimate Phase 1F change:
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

# Put backend/ on sys.path so ``import main`` works regardless of cwd.
_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# Module-level import: FastAPI app is constructed, os.makedirs runs, but no
# server starts.  All required packages must be installed in the active env.
import main  # noqa: E402

# Expected row schema — must match the keys written by _append_match_audit_entry.
EXPECTED_ROW_KEYS: frozenset = frozenset(
    {
        "decided_at",
        "event",
        "session_id_hint",
        "route_id",
        "route_name",
        "route_length_ft",
        "previous_route_id",
        "route_catalog_size",
        "input_sha256",
    }
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_rows(path: Path) -> List[Dict[str, Any]]:
    """Return all valid JSONL rows from *path* in append order."""
    text = path.read_text(encoding="utf-8")
    return [
        json.loads(line)
        for line in text.strip().splitlines()
        if line.strip()
    ]


def _make_route(
    route_id: str = "R1",
    route_name: Optional[str] = None,
    length_ft: float = 1000.0,
) -> Dict[str, Any]:
    return {
        "route_id": route_id,
        "route_name": route_name or f"Route {route_id}",
        "length_ft": length_ft,
    }


def _endpoint_entries(limit: int = 25) -> List[Dict[str, Any]]:
    """Call ``get_match_audit`` directly; return its ``entries`` list."""
    response = main.get_match_audit(limit=limit)
    data: Dict[str, Any] = json.loads(response.body)
    return data.get("entries") or []


# ---------------------------------------------------------------------------
# Test suite
# ---------------------------------------------------------------------------

class TestMatchAudit(unittest.TestCase):
    """Lock-down regression suite for Phase 1F MatchAudit."""

    def setUp(self) -> None:
        # Isolated temp directory for each test.
        self._tmpdir = tempfile.TemporaryDirectory()

        # Snapshot module globals that will be patched.
        self._orig_path = main.MATCH_AUDIT_PATH
        self._orig_max_rows = main.MATCH_AUDIT_MAX_ROWS

        # Redirect audit writes into the temp directory.
        main.MATCH_AUDIT_PATH = Path(self._tmpdir.name) / "match_audit.jsonl"
        # max_rows stays at the production default unless a test overrides it.

        # Snapshot STATE fields that _append_match_audit_entry reads.
        self._orig_session = main.STATE.get("_session_id_hint")
        self._orig_sha = main.STATE.get("last_kmz_input_sha256")
        self._orig_catalog = main.STATE.get("route_catalog")

        # Set predictable values for isolation.
        main.STATE["_session_id_hint"] = "test-session"
        main.STATE["last_kmz_input_sha256"] = None
        main.STATE["route_catalog"] = []

    def tearDown(self) -> None:
        # Restore STATE in reverse dependency order.
        main.STATE["route_catalog"] = self._orig_catalog
        main.STATE["last_kmz_input_sha256"] = self._orig_sha
        main.STATE["_session_id_hint"] = self._orig_session

        # Restore module globals.
        main.MATCH_AUDIT_MAX_ROWS = self._orig_max_rows
        main.MATCH_AUDIT_PATH = self._orig_path

        # Clean up temp directory.
        self._tmpdir.cleanup()

    # ------------------------------------------------------------------
    # 01 — basic append + schema guard
    # ------------------------------------------------------------------

    def test_01_append_creates_row_with_correct_schema(self) -> None:
        """A single call must create the JSONL file with exactly one row.

        The row must carry all required keys (EXPECTED_ROW_KEYS) and the
        event / route values must match what was passed.
        """
        route = _make_route("RA", length_ft=5280.0)
        main._append_match_audit_entry(
            event="active_route_set",
            route=route,
            previous_route_id=None,
        )

        self.assertTrue(
            main.MATCH_AUDIT_PATH.exists(),
            "match_audit.jsonl was not created",
        )
        rows = _read_rows(main.MATCH_AUDIT_PATH)
        self.assertEqual(len(rows), 1, "Expected exactly 1 row")

        row = rows[0]
        # Schema guard — no extra or missing keys.
        self.assertEqual(set(row.keys()), EXPECTED_ROW_KEYS)
        # Value assertions.
        self.assertEqual(row["event"], "active_route_set")
        self.assertEqual(row["route_id"], "RA")
        self.assertEqual(row["route_name"], "Route RA")
        self.assertIsNone(row["previous_route_id"])
        # decided_at must be a non-empty string — do NOT assert literal value.
        self.assertIsInstance(row["decided_at"], str)
        self.assertTrue(row["decided_at"], "decided_at must be non-empty")

    # ------------------------------------------------------------------
    # 02 — previous_route_id linkage
    # ------------------------------------------------------------------

    def test_02_preserves_previous_route_id(self) -> None:
        """The second row must record the first route's id as previous_route_id.

        Simulates: upload sets route RA, then user switches to RB.
        RA's route_id must appear in RB's row as previous_route_id.
        """
        route_a = _make_route("RA")
        route_b = _make_route("RB")

        main._append_match_audit_entry(
            event="active_route_set",
            route=route_a,
            previous_route_id=None,
        )
        main._append_match_audit_entry(
            event="active_route_set",
            route=route_b,
            previous_route_id="RA",   # as _set_active_route would pass it
        )

        rows = _read_rows(main.MATCH_AUDIT_PATH)
        self.assertEqual(len(rows), 2)

        first_row = rows[0]
        second_row = rows[1]

        self.assertEqual(first_row["route_id"], "RA")
        self.assertIsNone(first_row["previous_route_id"])  # no prior route

        self.assertEqual(second_row["route_id"], "RB")
        self.assertEqual(
            second_row["previous_route_id"],
            "RA",
            "second row must carry first route_id as previous_route_id",
        )

    # ------------------------------------------------------------------
    # 03 — row-cap enforcement
    # ------------------------------------------------------------------

    def test_03_truncates_to_max_rows(self) -> None:
        """After MATCH_AUDIT_MAX_ROWS is set to 3 and 5 rows are appended,
        only the latest 3 rows must remain in the file.

        Verifies the tail-truncation logic mirrors _append_ingestion_ledger_entry.
        """
        main.MATCH_AUDIT_MAX_ROWS = 3  # low cap for this test only

        for i in range(5):
            main._append_match_audit_entry(
                event="active_route_set",
                route=_make_route(f"R{i}"),
                previous_route_id=None,
            )

        rows = _read_rows(main.MATCH_AUDIT_PATH)
        self.assertEqual(
            len(rows),
            3,
            f"Expected 3 rows after truncation, got {len(rows)}",
        )
        # Latest rows (R2, R3, R4) must survive; earliest (R0, R1) must be gone.
        surviving_ids = [r["route_id"] for r in rows]
        self.assertNotIn("R0", surviving_ids, "R0 must be truncated")
        self.assertNotIn("R1", surviving_ids, "R1 must be truncated")
        self.assertIn("R4", surviving_ids, "R4 (most recent) must survive")

    # ------------------------------------------------------------------
    # 04 — missing file returns empty list
    # ------------------------------------------------------------------

    def test_04_missing_file_returns_empty_entries(self) -> None:
        """GET endpoint must return {\"entries\": []} when no file exists.

        setUp points MATCH_AUDIT_PATH at a file that does not yet exist.
        The endpoint function is called directly — no server started.
        """
        # Confirm the file really doesn't exist.
        self.assertFalse(
            main.MATCH_AUDIT_PATH.exists(),
            "setUp should provide a path to a non-existent file",
        )

        response = main.get_match_audit(limit=10)
        data: Dict[str, Any] = json.loads(response.body)
        self.assertEqual(data, {"entries": []})

    # ------------------------------------------------------------------
    # 05 — reverse chronological order
    # ------------------------------------------------------------------

    def test_05_reverse_chronological_order(self) -> None:
        """Endpoint must return rows newest-first (reverse of append order).

        Appends R0 → R1 → R2 in that order.  Endpoint must return R2, R1, R0.
        Order is derived from file line reversal, not timestamp comparison,
        so the test is deterministic regardless of clock resolution.
        """
        for i in range(3):
            main._append_match_audit_entry(
                event="active_route_set",
                route=_make_route(f"R{i}"),
                previous_route_id=None,
            )

        entries = _endpoint_entries(limit=10)
        self.assertEqual(len(entries), 3)
        # Newest appended → first in output.
        self.assertEqual(
            entries[0]["route_id"],
            "R2",
            "Most recently appended route must appear first",
        )
        self.assertEqual(entries[1]["route_id"], "R1")
        self.assertEqual(entries[2]["route_id"], "R0")

    # ------------------------------------------------------------------
    # 06 — input_sha256 passthrough
    # ------------------------------------------------------------------

    def test_06_input_sha_passthrough(self) -> None:
        """Row must carry STATE['last_kmz_input_sha256'] unchanged.

        Simulates the Phase 1F link between an ingestion ledger entry and a
        match audit entry: upload sets the SHA, the next _set_active_route
        call picks it up.
        """
        expected_sha = "a" * 64  # 64 hex chars — deterministic fixture value
        main.STATE["last_kmz_input_sha256"] = expected_sha

        main._append_match_audit_entry(
            event="active_route_set",
            route=_make_route("RX"),
            previous_route_id=None,
        )

        rows = _read_rows(main.MATCH_AUDIT_PATH)
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0]["input_sha256"],
            expected_sha,
            "input_sha256 must be forwarded from STATE to the row unchanged",
        )

    # ------------------------------------------------------------------
    # 07 — helper never raises
    # ------------------------------------------------------------------

    def test_07_helper_never_raises(self) -> None:
        """_append_match_audit_entry must never propagate an exception.

        Forces the helper into an error path by pointing MATCH_AUDIT_PATH at a
        path whose parent directory does not exist.  On Windows and POSIX,
        open() in append mode raises FileNotFoundError for a missing parent.
        The helper must swallow it silently and return None.
        """
        main.MATCH_AUDIT_PATH = (
            Path(self._tmpdir.name) / "does_not_exist" / "match_audit.jsonl"
        )
        # Must not raise.
        try:
            result = main._append_match_audit_entry(
                event="active_route_set",
                route=_make_route("R_bad"),
                previous_route_id=None,
            )
        except Exception as exc:
            self.fail(
                f"_append_match_audit_entry raised {type(exc).__name__}: {exc}"
            )
        # Helper returns None on both success and failure paths.
        self.assertIsNone(result)
        # File must not have been created.
        self.assertFalse(
            main.MATCH_AUDIT_PATH.exists(),
            "No file should be created when the parent dir is missing",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
