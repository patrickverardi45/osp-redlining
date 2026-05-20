"""RI.4 — bore-log ROWS_ONLY consumer tests.

Verifies the structural fix for B-WS-12: the ROWS_ONLY branch inside
_rebuild_field_data_outputs NEVER invokes _build_plan_topology_for_session()
under any condition.

All tests mock _build_plan_topology_for_session — no Brenham PDF dependency.

Critical invariant tested: bore-log uploads cannot trigger fresh PDF parsing.
Tests #01-#07 collectively form the load-bearing invariant gate.

COMMAND
-------
    python -m pytest backend/tests/test_ri4_bore_log_rows_only.py -v
"""

from __future__ import annotations

import copy
import json
import os
import unittest
import uuid
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import patch

os.environ.setdefault("TRUELINE_JWT_SECRET", "ri4-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "ri4-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend import main as M
from backend.app.core import plan_topology_cache as ptc
from backend.app.core.plan_topology_cache import (
    CacheWriteResult,
    KILL_SWITCH_ENV,
    SCHEMA_VERSION,
)
from backend.app.core.rebuild_scope import RebuildScope

FLAG_ENV = "TRUELINE_PLAN_PDF_PARSE"


def _synthetic_topology() -> Dict[int, Dict[str, Any]]:
    return {
        0: {"sheet_index": 0, "station_origin_ft": 0, "name": "sheet_a"},
        1: {"sheet_index": 1, "station_origin_ft": 100, "name": "sheet_b"},
    }


class TestRI4BoreLogRowsOnly(unittest.TestCase):
    """RI.4 — ROWS_ONLY scope structural invariant + parity."""

    def setUp(self) -> None:
        self._saved_state = copy.deepcopy(dict(M.STATE))
        self._saved_flag = os.environ.pop(FLAG_ENV, None)
        self._saved_kill = os.environ.pop(KILL_SWITCH_ENV, None)
        self._test_session_id = f"ri4_{uuid.uuid4().hex[:12]}"
        self._cache_file: Path = ptc.resolve_cache_file(self._test_session_id, M.UPLOADS_DIR)

    def tearDown(self) -> None:
        M.STATE.clear()
        M.STATE.update(self._saved_state)
        if self._saved_flag is None:
            os.environ.pop(FLAG_ENV, None)
        else:
            os.environ[FLAG_ENV] = self._saved_flag
        if self._saved_kill is None:
            os.environ.pop(KILL_SWITCH_ENV, None)
        else:
            os.environ[KILL_SWITCH_ENV] = self._saved_kill
        try:
            if self._cache_file.exists():
                self._cache_file.unlink()
        except OSError:
            pass

    def _reset_state(self) -> None:
        M.STATE.clear()
        M.STATE.update({
            "committed_rows": [],
            "route_catalog": [],
            "_session_id_hint": self._test_session_id,
            "engineering_plans": [],
        })

    def _enable_flag(self) -> None:
        os.environ[FLAG_ENV] = "1"

    def _enable_kill_switch(self) -> None:
        os.environ[KILL_SWITCH_ENV] = "1"

    def _seed_cache(self, topology: Optional[Dict[int, Dict[str, Any]]] = None) -> None:
        """Pre-populate the cache file with the current plan-set signature."""
        signature = ptc.derive_plan_set_signature([])
        ptc.cache_write(
            self._cache_file,
            signature,
            topology if topology is not None else _synthetic_topology(),
            plan_count=0,
            compute_duration_ms=0,
        )

    def _snapshot_state(self) -> Dict[str, Any]:
        return copy.deepcopy(dict(M.STATE))

    # ─── A. Central invariant — parser never invoked under ROWS_ONLY ───────

    def test_01_rows_only_never_invokes_parser_on_cache_hit(self) -> None:
        self._enable_flag()
        self._seed_cache()
        self._reset_state()
        with patch.object(M, "_build_plan_topology_for_session", side_effect=AssertionError("parser must not be called")) as mock_parse:
            M._rebuild_field_data_outputs(scope=RebuildScope.ROWS_ONLY)
        self.assertEqual(mock_parse.call_count, 0)

    def test_02_rows_only_never_invokes_parser_on_cache_miss(self) -> None:
        self._enable_flag()
        self.assertFalse(self._cache_file.exists())
        self._reset_state()
        with patch.object(M, "_build_plan_topology_for_session", side_effect=AssertionError("parser must not be called")) as mock_parse:
            M._rebuild_field_data_outputs(scope=RebuildScope.ROWS_ONLY)
        self.assertEqual(mock_parse.call_count, 0)

    def test_03_rows_only_never_invokes_parser_on_corrupt_cache(self) -> None:
        self._enable_flag()
        self._cache_file.parent.mkdir(parents=True, exist_ok=True)
        self._cache_file.write_text("{ not valid json", encoding="utf-8")
        self._reset_state()
        with patch.object(M, "_build_plan_topology_for_session", side_effect=AssertionError("parser must not be called")) as mock_parse:
            M._rebuild_field_data_outputs(scope=RebuildScope.ROWS_ONLY)
        self.assertEqual(mock_parse.call_count, 0)

    def test_04_rows_only_never_invokes_parser_on_signature_mismatch(self) -> None:
        self._enable_flag()
        ptc.cache_write(self._cache_file, "wrong_sig", _synthetic_topology(), plan_count=0, compute_duration_ms=0)
        self._reset_state()
        with patch.object(M, "_build_plan_topology_for_session", side_effect=AssertionError("parser must not be called")) as mock_parse:
            M._rebuild_field_data_outputs(scope=RebuildScope.ROWS_ONLY)
        self.assertEqual(mock_parse.call_count, 0)

    def test_05_rows_only_never_invokes_parser_when_kill_switch_on(self) -> None:
        self._enable_flag()
        self._enable_kill_switch()
        self._seed_cache()  # even with cache present, parser must not be called
        self._reset_state()
        with patch.object(M, "_build_plan_topology_for_session", side_effect=AssertionError("parser must not be called")) as mock_parse:
            M._rebuild_field_data_outputs(scope=RebuildScope.ROWS_ONLY)
        self.assertEqual(mock_parse.call_count, 0)

    def test_06_rows_only_never_invokes_parser_when_flag_off(self) -> None:
        # Flag intentionally NOT enabled (production state)
        self._reset_state()
        with patch.object(M, "_build_plan_topology_for_session", side_effect=AssertionError("parser must not be called")) as mock_parse:
            M._rebuild_field_data_outputs(scope=RebuildScope.ROWS_ONLY)
        self.assertEqual(mock_parse.call_count, 0)

    def test_07_rows_only_never_calls_cache_write(self) -> None:
        """ROWS_ONLY is a consumer only — must never produce/write cache."""
        self._enable_flag()
        self._reset_state()
        with patch.object(M.plan_topology_cache, "cache_write") as mock_write:
            with patch.object(M, "_build_plan_topology_for_session", side_effect=AssertionError("parser must not be called")):
                M._rebuild_field_data_outputs(scope=RebuildScope.ROWS_ONLY)
        self.assertEqual(mock_write.call_count, 0)

    # ─── B. Behavior parity with flag-off production ────────────────────────

    def test_08_rows_only_flag_off_state_byte_identity_with_default(self) -> None:
        """Flag OFF: ROWS_ONLY produces same STATE as today (default-kwarg FULL with flag off)."""
        # Both runs with flag OFF — neither should touch cache or parser
        self._reset_state()
        M._rebuild_field_data_outputs()  # default-FULL via RI.1 safety net
        state_default = self._snapshot_state()

        self._reset_state()
        M._rebuild_field_data_outputs(scope=RebuildScope.ROWS_ONLY)
        state_rows_only = self._snapshot_state()

        self.assertEqual(state_default, state_rows_only)

    # ─── C. Cache-hit parity with FULL ──────────────────────────────────────

    def test_09_rows_only_cache_hit_state_byte_identity_with_full_warm(self) -> None:
        """Flag ON + warm cache: ROWS_ONLY produces same STATE as FULL."""
        self._enable_flag()
        synthetic = _synthetic_topology()

        # FULL cold → populates cache
        self._reset_state()
        with patch.object(M, "_build_plan_topology_for_session", return_value=synthetic):
            M._rebuild_field_data_outputs(scope=RebuildScope.FULL)
        state_full_warm = self._snapshot_state()

        # ROWS_ONLY warm
        self._reset_state()
        with patch.object(M, "_build_plan_topology_for_session", side_effect=AssertionError("parser must not be called")):
            M._rebuild_field_data_outputs(scope=RebuildScope.ROWS_ONLY)
        state_rows_only_warm = self._snapshot_state()

        self.assertEqual(state_full_warm, state_rows_only_warm)

    # ─── D. Cache-miss empty topology ───────────────────────────────────────

    def test_10_rows_only_cache_miss_produces_empty_topology(self) -> None:
        """Flag ON + no cache: ROWS_ONLY produces empty topology (no parse)."""
        self._enable_flag()
        self.assertFalse(self._cache_file.exists())
        self._reset_state()
        with patch.object(M, "_build_plan_topology_for_session", side_effect=AssertionError("parser must not be called")):
            M._rebuild_field_data_outputs(scope=RebuildScope.ROWS_ONLY)
        # No cache file should be created on the ROWS_ONLY miss
        self.assertFalse(self._cache_file.exists())

    # ─── E. Kill-switch interaction ────────────────────────────────────────

    def test_11_rows_only_kill_switch_on_produces_empty_topology(self) -> None:
        """Kill switch ON + cache present → STILL empty topology, NEVER parser."""
        self._enable_flag()
        self._enable_kill_switch()
        self._seed_cache()
        self._reset_state()
        with patch.object(M, "_build_plan_topology_for_session", side_effect=AssertionError("parser must not be called")):
            with patch.object(M.plan_topology_cache, "cache_read") as mock_read:
                M._rebuild_field_data_outputs(scope=RebuildScope.ROWS_ONLY)
        # Kill switch should also bypass cache_read on ROWS_ONLY
        self.assertEqual(mock_read.call_count, 0)

    def test_12_rows_only_kill_switch_does_not_unlock_parser(self) -> None:
        """Operational safety: flipping kill switch must NOT re-enable parser on ROWS_ONLY."""
        self._enable_flag()
        self._enable_kill_switch()
        self._reset_state()
        with patch.object(M, "_build_plan_topology_for_session", side_effect=AssertionError("parser must not be called")):
            M._rebuild_field_data_outputs(scope=RebuildScope.ROWS_ONLY)

    # ─── F. Observability ──────────────────────────────────────────────────

    def test_13_log_line_emits_cache_hit_under_rows_only(self) -> None:
        self._enable_flag()
        self._seed_cache()
        self._reset_state()
        with self.assertLogs(level="INFO") as cm:
            with patch.object(M, "_build_plan_topology_for_session", side_effect=AssertionError("parser must not be called")):
                M._rebuild_field_data_outputs(scope=RebuildScope.ROWS_ONLY)
        joined = "\n".join(cm.output)
        self.assertIn("topology_source=cache_hit", joined)
        self.assertIn("scope=rows_only", joined)

    def test_14_log_line_emits_rows_only_cache_miss_empty(self) -> None:
        self._enable_flag()
        self._reset_state()
        with self.assertLogs(level="INFO") as cm:
            with patch.object(M, "_build_plan_topology_for_session", side_effect=AssertionError("parser must not be called")):
                M._rebuild_field_data_outputs(scope=RebuildScope.ROWS_ONLY)
        joined = "\n".join(cm.output)
        self.assertIn("topology_source=rows_only_cache_miss_empty", joined)

    def test_15_log_line_emits_rows_only_bypassed_kill_switch(self) -> None:
        self._enable_flag()
        self._enable_kill_switch()
        self._reset_state()
        with self.assertLogs(level="INFO") as cm:
            with patch.object(M, "_build_plan_topology_for_session", side_effect=AssertionError("parser must not be called")):
                M._rebuild_field_data_outputs(scope=RebuildScope.ROWS_ONLY)
        joined = "\n".join(cm.output)
        self.assertIn("topology_source=rows_only_bypassed_kill_switch", joined)

    def test_16_log_line_emits_bypassed_flag_off_under_rows_only(self) -> None:
        # Flag intentionally OFF
        self._reset_state()
        with self.assertLogs(level="INFO") as cm:
            M._rebuild_field_data_outputs(scope=RebuildScope.ROWS_ONLY)
        joined = "\n".join(cm.output)
        self.assertIn("topology_source=bypassed_flag_off", joined)

    # ─── G. Cache state safety ─────────────────────────────────────────────

    def test_17_rows_only_does_not_mutate_cache_file_on_disk(self) -> None:
        """Verify cache file content is unchanged after a ROWS_ONLY pass."""
        self._enable_flag()
        self._seed_cache(_synthetic_topology())
        original_bytes = self._cache_file.read_bytes()

        self._reset_state()
        with patch.object(M, "_build_plan_topology_for_session", side_effect=AssertionError("parser must not be called")):
            M._rebuild_field_data_outputs(scope=RebuildScope.ROWS_ONLY)
        post_bytes = self._cache_file.read_bytes()
        self.assertEqual(original_bytes, post_bytes)

    # ─── H. Explicit KMZ → bore-log workflow (B-WS-12 reproduction repellent) ─

    def test_18_kmz_then_bore_log_workflow_no_reparse(self) -> None:
        """End-to-end: KMZ FULL populates cache; subsequent ROWS_ONLY consumes it.

        Simulates the exact reproduction sequence of B-WS-12 (KMZ → bore-log)
        with the parser flag ON locally and asserts that the bore-log path
        consumes the cached topology without invoking the parser.

        PE.2: cache-miss branch invokes
        _build_plan_topology_for_session_with_outcomes; mocks updated.
        The B-WS-12 invariant (bore-log NEVER invokes parser) is preserved.
        """
        self._enable_flag()
        synthetic = _synthetic_topology()

        # Phase 1: KMZ upload → FULL rebuild → cache populated
        self._reset_state()
        with patch.object(
            M,
            "_build_plan_topology_for_session_with_outcomes",
            return_value=(synthetic, []),
        ) as mock_parse_kmz:
            M._rebuild_field_data_outputs(scope=RebuildScope.FULL)
        self.assertEqual(mock_parse_kmz.call_count, 1, "parser should run on cold KMZ")
        self.assertTrue(self._cache_file.exists(), "KMZ FULL must populate cache")

        # Phase 2: bore-log upload → ROWS_ONLY rebuild → cache consumed; NO parser
        # ROWS_ONLY must NEVER invoke either parser function (with or without outcomes).
        self._reset_state()
        with patch.object(
            M,
            "_build_plan_topology_for_session",
            side_effect=AssertionError("parser must not be called on bore-log"),
        ) as mock_parse_borelog:
            with patch.object(
                M,
                "_build_plan_topology_for_session_with_outcomes",
                side_effect=AssertionError("parser must not be called on bore-log (with_outcomes variant)"),
            ) as mock_parse_borelog_outcomes:
                M._rebuild_field_data_outputs(scope=RebuildScope.ROWS_ONLY)
        self.assertEqual(
            mock_parse_borelog.call_count, 0,
            "bore-log ROWS_ONLY must NEVER invoke parser (B-WS-12 structural fix)",
        )
        self.assertEqual(
            mock_parse_borelog_outcomes.call_count, 0,
            "bore-log ROWS_ONLY must NEVER invoke parser-with-outcomes either",
        )

        # Phase 3: cache content unchanged after bore-log pass
        cached = ptc.cache_read(self._cache_file, ptc.derive_plan_set_signature([]))
        self.assertEqual(cached, synthetic, "cache content must survive ROWS_ONLY pass")


if __name__ == "__main__":
    unittest.main()
