"""RI.3 — KMZ cache consumer tests.

Verifies the cache-aware FULL-scope branch inside _rebuild_field_data_outputs.
All tests mock _build_plan_topology_for_session — no Brenham PDF dependency.

Critical invariant under test: cache-warm output equals cache-cold output
byte-for-byte. Tests #01 and #04 are the load-bearing parity tests.

COMMAND
-------
    python -m pytest backend/tests/test_ri3_kmz_cache_consumer.py -v
"""

from __future__ import annotations

import copy
import json
import logging
import os
import unittest
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

# Required for backend.main import.
os.environ.setdefault("TRUELINE_JWT_SECRET", "ri3-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "ri3-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend import main as M
from backend.app.core import plan_topology_cache as ptc
from backend.app.core.plan_topology_cache import (
    CacheWriteResult,
    SCHEMA_VERSION,
    KILL_SWITCH_ENV,
)
from backend.app.core.rebuild_scope import RebuildScope

FLAG_ENV = "TRUELINE_PLAN_PDF_PARSE"


def _synthetic_topology() -> Dict[int, Dict[str, Any]]:
    """Synthetic parser output. JSON-stable; matches Dict[int, Dict[str, Any]]."""
    return {
        0: {"sheet_index": 0, "station_origin_ft": 0, "name": "sheet_a"},
        1: {"sheet_index": 1, "station_origin_ft": 100, "name": "sheet_b"},
    }


class TestRI3CacheConsumer(unittest.TestCase):
    """RI.3 — FULL scope cache consumer behavior."""

    def setUp(self) -> None:
        self._saved_state = copy.deepcopy(dict(M.STATE))
        self._saved_flag = os.environ.pop(FLAG_ENV, None)
        self._saved_kill = os.environ.pop(KILL_SWITCH_ENV, None)
        self._test_session_id = f"ri3_{uuid.uuid4().hex[:12]}"
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

    def _snapshot_state(self) -> Dict[str, Any]:
        return copy.deepcopy(dict(M.STATE))

    # ─── A. Cold/warm parity (load-bearing) ────────────────────────────────

    def test_01_cold_then_warm_state_byte_identity(self) -> None:
        """COLD parse → cache populated → WARM read. STATE deep-equal."""
        self._enable_flag()
        synthetic = _synthetic_topology()

        self._reset_state()
        with patch.object(M, "_build_plan_topology_for_session", return_value=synthetic) as mock_parse_cold:
            M._rebuild_field_data_outputs(scope=RebuildScope.FULL)
        self.assertEqual(mock_parse_cold.call_count, 1, "parser must be called on cold")
        state_cold = self._snapshot_state()
        self.assertTrue(self._cache_file.exists(), "cache file should exist after cold rebuild")

        self._reset_state()
        with patch.object(M, "_build_plan_topology_for_session", return_value=synthetic) as mock_parse_warm:
            M._rebuild_field_data_outputs(scope=RebuildScope.FULL)
        self.assertEqual(mock_parse_warm.call_count, 0, "parser must NOT be called on warm")
        state_warm = self._snapshot_state()

        self.assertEqual(state_cold, state_warm, "STATE byte-identity violated")

    def test_02_topology_roundtrip_byte_identity(self) -> None:
        """cache_write(T) → cache_read → T'. T == T' deep equality."""
        T = _synthetic_topology()
        signature = "sig_abc"
        result = ptc.cache_write(self._cache_file, signature, T, plan_count=2, compute_duration_ms=1)
        self.assertEqual(result, CacheWriteResult.WRITTEN)
        T_prime = ptc.cache_read(self._cache_file, signature)
        self.assertEqual(T, T_prime)

    def test_03_cold_path_matches_today_behavior(self) -> None:
        """Parser IS called on cold; cache IS written after parse."""
        self._enable_flag()
        synthetic = _synthetic_topology()

        self._reset_state()
        with patch.object(M, "_build_plan_topology_for_session", return_value=synthetic) as mock_parse:
            M._rebuild_field_data_outputs(scope=RebuildScope.FULL)
        self.assertEqual(mock_parse.call_count, 1)
        self.assertTrue(self._cache_file.exists())

    def test_04_warm_path_skips_parser(self) -> None:
        """Pre-populated cache → parser NOT called."""
        self._enable_flag()
        signature = ptc.derive_plan_set_signature([])
        T = _synthetic_topology()
        ptc.cache_write(self._cache_file, signature, T, plan_count=0, compute_duration_ms=0)

        self._reset_state()
        with patch.object(M, "_build_plan_topology_for_session", side_effect=AssertionError("parser must not be called")) as mock_parse:
            M._rebuild_field_data_outputs(scope=RebuildScope.FULL)
        self.assertEqual(mock_parse.call_count, 0)

    # ─── B. Cache miss behavior ─────────────────────────────────────────────

    def test_05_cache_miss_signature_mismatch_triggers_parse(self) -> None:
        """Cache with wrong signature → miss → parse → cache overwritten."""
        self._enable_flag()
        ptc.cache_write(self._cache_file, "wrong_sig", {0: {"stale": True}}, plan_count=0, compute_duration_ms=0)

        self._reset_state()
        synthetic = _synthetic_topology()
        with patch.object(M, "_build_plan_topology_for_session", return_value=synthetic) as mock_parse:
            M._rebuild_field_data_outputs(scope=RebuildScope.FULL)
        self.assertEqual(mock_parse.call_count, 1)

        # Cache should now have the new content under the current signature
        current_sig = ptc.derive_plan_set_signature([])
        cached = ptc.cache_read(self._cache_file, current_sig)
        self.assertEqual(cached, synthetic)

    def test_06_cache_miss_corrupt_file_triggers_parse(self) -> None:
        """Corrupt JSON in cache → miss → parse → cache overwritten."""
        self._enable_flag()
        self._cache_file.parent.mkdir(parents=True, exist_ok=True)
        self._cache_file.write_text("{ this is not valid json", encoding="utf-8")

        self._reset_state()
        synthetic = _synthetic_topology()
        with patch.object(M, "_build_plan_topology_for_session", return_value=synthetic) as mock_parse:
            M._rebuild_field_data_outputs(scope=RebuildScope.FULL)
        self.assertEqual(mock_parse.call_count, 1)

        current_sig = ptc.derive_plan_set_signature([])
        cached = ptc.cache_read(self._cache_file, current_sig)
        self.assertEqual(cached, synthetic)

    def test_07_cache_miss_absent_triggers_parse_and_write(self) -> None:
        """No cache file → miss → parse → cache populated."""
        self._enable_flag()
        self.assertFalse(self._cache_file.exists())

        self._reset_state()
        synthetic = _synthetic_topology()
        with patch.object(M, "_build_plan_topology_for_session", return_value=synthetic):
            M._rebuild_field_data_outputs(scope=RebuildScope.FULL)
        self.assertTrue(self._cache_file.exists())

    def test_08_cache_write_failure_non_fatal(self) -> None:
        """If cache_write returns ERROR_IO, rebuild still completes from parser output."""
        self._enable_flag()
        synthetic = _synthetic_topology()

        self._reset_state()
        with patch.object(M, "_build_plan_topology_for_session", return_value=synthetic):
            with patch.object(M.plan_topology_cache, "cache_write", return_value=CacheWriteResult.ERROR_IO):
                # Should not raise; STATE should still be populated as if from parser
                M._rebuild_field_data_outputs(scope=RebuildScope.FULL)
        # No exception = pass

    # ─── C. Kill switch behavior ───────────────────────────────────────────

    def test_09_kill_switch_bypasses_cache_read(self) -> None:
        """Kill switch ON → cache_read NOT called; parser IS called."""
        self._enable_flag()
        self._enable_kill_switch()
        signature = ptc.derive_plan_set_signature([])
        ptc.cache_write(self._cache_file, signature, _synthetic_topology(), plan_count=0, compute_duration_ms=0)

        self._reset_state()
        with patch.object(M.plan_topology_cache, "cache_read") as mock_read:
            with patch.object(M, "_build_plan_topology_for_session", return_value={}) as mock_parse:
                M._rebuild_field_data_outputs(scope=RebuildScope.FULL)
        self.assertEqual(mock_read.call_count, 0, "cache_read should be bypassed when kill switch is on")
        self.assertGreaterEqual(mock_parse.call_count, 1, "parser should be called directly when kill switch is on")

    def test_10_kill_switch_bypasses_cache_write(self) -> None:
        """Kill switch ON → cache_write NOT called by rebuild."""
        self._enable_flag()
        self._enable_kill_switch()

        self._reset_state()
        with patch.object(M.plan_topology_cache, "cache_write") as mock_write:
            with patch.object(M, "_build_plan_topology_for_session", return_value=_synthetic_topology()):
                M._rebuild_field_data_outputs(scope=RebuildScope.FULL)
        self.assertEqual(mock_write.call_count, 0)

    def test_11_kill_switch_invalidation_hook_still_runs(self) -> None:
        """Kill switch active does NOT disable the _save_engineering_plan_index invalidation hook."""
        self._enable_kill_switch()
        # Create a synthetic cache file
        self._cache_file.parent.mkdir(parents=True, exist_ok=True)
        self._cache_file.write_text(
            json.dumps({"schema": SCHEMA_VERSION, "plan_set_signature": "s", "topology": {}}),
            encoding="utf-8",
        )
        self.assertTrue(self._cache_file.exists())

        # Save the existing index for restoration
        index_path = M.ENGINEERING_PLAN_INDEX_PATH
        saved_index = index_path.read_text(encoding="utf-8") if index_path.exists() else None

        try:
            M._save_engineering_plan_index({
                "plans": [{
                    "session_id": self._test_session_id,
                    "plan_id": "p1",
                    "stored_filename": "x.pdf",
                    "size_bytes": 100,
                    "uploaded_at": "2026-05-20T00:00:00Z",
                }]
            })
            self.assertFalse(self._cache_file.exists(), "invalidation should fire regardless of kill switch")
        finally:
            if saved_index is not None:
                index_path.write_text(saved_index, encoding="utf-8")
            else:
                try:
                    if index_path.exists():
                        index_path.unlink()
                except OSError:
                    pass

    # ─── D. Flag gate behavior ─────────────────────────────────────────────

    def test_12_parser_flag_off_bypasses_cache_entirely(self) -> None:
        """TRUELINE_PLAN_PDF_PARSE unset → cache_read NOT called, cache_write NOT called."""
        # Flag intentionally NOT enabled here

        self._reset_state()
        with patch.object(M.plan_topology_cache, "cache_read") as mock_read:
            with patch.object(M.plan_topology_cache, "cache_write") as mock_write:
                with patch.object(M, "_build_plan_topology_for_session") as mock_parse:
                    M._rebuild_field_data_outputs(scope=RebuildScope.FULL)
        self.assertEqual(mock_read.call_count, 0)
        self.assertEqual(mock_write.call_count, 0)
        self.assertEqual(mock_parse.call_count, 0, "parser should not be called when flag is off")

    # ─── E. Observability ──────────────────────────────────────────────────

    def test_13_log_line_emits_correct_source_cache_hit(self) -> None:
        """Pre-populate cache, run rebuild, assert log contains 'topology_source=cache_hit'."""
        self._enable_flag()
        signature = ptc.derive_plan_set_signature([])
        ptc.cache_write(self._cache_file, signature, _synthetic_topology(), plan_count=0, compute_duration_ms=0)

        self._reset_state()
        with self.assertLogs(level="INFO") as cm:
            with patch.object(M, "_build_plan_topology_for_session", return_value={}):
                M._rebuild_field_data_outputs(scope=RebuildScope.FULL)
        joined = "\n".join(cm.output)
        self.assertIn("topology_source=cache_hit", joined)

    def test_14_log_line_emits_correct_source_cache_miss(self) -> None:
        """No cache; rebuild; assert log contains 'topology_source=cache_miss_computed'."""
        self._enable_flag()

        self._reset_state()
        with self.assertLogs(level="INFO") as cm:
            with patch.object(M, "_build_plan_topology_for_session", return_value=_synthetic_topology()):
                M._rebuild_field_data_outputs(scope=RebuildScope.FULL)
        joined = "\n".join(cm.output)
        self.assertIn("topology_source=cache_miss_computed", joined)

    def test_15_log_line_emits_correct_source_bypassed_kill_switch(self) -> None:
        """Kill switch ON; rebuild; assert log contains 'topology_source=bypassed_kill_switch'."""
        self._enable_flag()
        self._enable_kill_switch()

        self._reset_state()
        with self.assertLogs(level="INFO") as cm:
            with patch.object(M, "_build_plan_topology_for_session", return_value=_synthetic_topology()):
                M._rebuild_field_data_outputs(scope=RebuildScope.FULL)
        joined = "\n".join(cm.output)
        self.assertIn("topology_source=bypassed_kill_switch", joined)


if __name__ == "__main__":
    unittest.main()
