"""RI.2 — Plan topology cache module tests.

Verifies the cache module's I/O contract, signature algorithm, schema
validation, atomic-write behavior, invalidation, kill-switch helper,
and the _save_engineering_plan_index integration hook.

All unit tests use synthetic topology dicts and synthetic plan metadata.
NO Brenham PDF fixtures. NO PDF parser invocation. NO httpx dependency.

COMMAND
-------
    python -m pytest backend/tests/test_plan_topology_cache.py -v
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import tempfile
import unittest
import uuid
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

# Required for backend.main import (used in integration hook tests).
os.environ.setdefault("TRUELINE_JWT_SECRET", "ri2-cache-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "ri2-cache-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend.app.core import plan_topology_cache as ptc
from backend.app.core.plan_topology_cache import (
    CacheWriteResult,
    KILL_SWITCH_ENV,
    MAX_TOPOLOGY_BYTES,
    SCHEMA_VERSION,
    cache_invalidate,
    cache_read,
    cache_write,
    derive_plan_set_signature,
    kill_switch_active,
    resolve_cache_file,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _plan(
    plan_id: str,
    stored_filename: str = "x.pdf",
    size_bytes: int = 100,
    uploaded_at: str = "2026-05-20T00:00:00Z",
    **extras: Any,
) -> Dict[str, Any]:
    base = {
        "plan_id": plan_id,
        "stored_filename": stored_filename,
        "size_bytes": size_bytes,
        "uploaded_at": uploaded_at,
    }
    base.update(extras)
    return base


def _topology(sheets: Dict[int, Dict[str, Any]] = None) -> Dict[int, Dict[str, Any]]:
    if sheets is not None:
        return sheets
    return {
        0: {"sheet_index": 0, "station_origin_ft": 0, "name": "sheet_a"},
        1: {"sheet_index": 1, "station_origin_ft": 100, "name": "sheet_b"},
    }


# ===========================================================================
# Signature derivation (no I/O)
# ===========================================================================


class TestSignatureDerivation(unittest.TestCase):
    """Pure-function tests for derive_plan_set_signature."""

    def test_01_deterministic(self) -> None:
        plans = [_plan("a"), _plan("b")]
        self.assertEqual(derive_plan_set_signature(plans), derive_plan_set_signature(plans))

    def test_02_order_independent(self) -> None:
        a = derive_plan_set_signature([_plan("a"), _plan("b")])
        b = derive_plan_set_signature([_plan("b"), _plan("a")])
        self.assertEqual(a, b)

    def test_03_changes_on_plan_added(self) -> None:
        base = derive_plan_set_signature([_plan("a")])
        added = derive_plan_set_signature([_plan("a"), _plan("b")])
        self.assertNotEqual(base, added)

    def test_04_changes_on_plan_removed(self) -> None:
        full = derive_plan_set_signature([_plan("a"), _plan("b")])
        removed = derive_plan_set_signature([_plan("a")])
        self.assertNotEqual(full, removed)

    def test_05_changes_on_stored_filename(self) -> None:
        a = derive_plan_set_signature([_plan("a", stored_filename="x.pdf")])
        b = derive_plan_set_signature([_plan("a", stored_filename="y.pdf")])
        self.assertNotEqual(a, b)

    def test_06_changes_on_size_bytes(self) -> None:
        a = derive_plan_set_signature([_plan("a", size_bytes=100)])
        b = derive_plan_set_signature([_plan("a", size_bytes=200)])
        self.assertNotEqual(a, b)

    def test_07_changes_on_uploaded_at(self) -> None:
        a = derive_plan_set_signature([_plan("a", uploaded_at="2026-05-01T00:00:00Z")])
        b = derive_plan_set_signature([_plan("a", uploaded_at="2026-05-20T00:00:00Z")])
        self.assertNotEqual(a, b)

    def test_08_unchanged_on_irrelevant_field(self) -> None:
        a = derive_plan_set_signature([_plan("a", notes="hello", print_numbers="1-3")])
        b = derive_plan_set_signature([_plan("a", notes="bye",   print_numbers="9-9")])
        self.assertEqual(a, b)

    def test_09_empty_plan_list_sentinel(self) -> None:
        # SHA256 of canonical empty list "[]"
        import hashlib
        expected = hashlib.sha256(b"[]").hexdigest()
        self.assertEqual(derive_plan_set_signature([]), expected)

    def test_10_none_input_treated_as_empty(self) -> None:
        # Defensive: derive_plan_set_signature(None) should not raise
        self.assertEqual(derive_plan_set_signature(None), derive_plan_set_signature([]))


# ===========================================================================
# Cache roundtrip (tmpdir-scoped)
# ===========================================================================


class TestCacheRoundtrip(unittest.TestCase):
    """Read/write/invalidate round-trips on a tmpdir-scoped cache file."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._uploads_dir = Path(self._tmpdir.name)
        self._session_id = "test_session"
        self._cache_file = resolve_cache_file(self._session_id, self._uploads_dir)
        self._sig = "abc123"
        self._topology = _topology()

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_01_hit_when_signature_matches(self) -> None:
        result = cache_write(self._cache_file, self._sig, self._topology, plan_count=2, compute_duration_ms=42)
        self.assertEqual(result, CacheWriteResult.WRITTEN)

        cached = cache_read(self._cache_file, self._sig)
        self.assertEqual(cached, self._topology)

    def test_02_miss_when_signature_differs(self) -> None:
        cache_write(self._cache_file, self._sig, self._topology, plan_count=2, compute_duration_ms=42)
        self.assertIsNone(cache_read(self._cache_file, "different_sig"))

    def test_03_topology_byte_identity(self) -> None:
        cache_write(self._cache_file, self._sig, self._topology, plan_count=2, compute_duration_ms=42)
        cached = cache_read(self._cache_file, self._sig)
        # Deep equality, including nested fields
        self.assertEqual(cached, self._topology)

    def test_04_int_keys_normalized(self) -> None:
        # JSON serializes dict int keys as strings; read must normalize back.
        topology = {7: {"name": "seven"}, 13: {"name": "thirteen"}}
        cache_write(self._cache_file, self._sig, topology, plan_count=1, compute_duration_ms=1)
        cached = cache_read(self._cache_file, self._sig)
        self.assertIsNotNone(cached)
        self.assertIn(7, cached)
        self.assertIn(13, cached)
        self.assertEqual(cached[7]["name"], "seven")

    def test_05_creates_parent_directory(self) -> None:
        # Cache file path includes a topology_cache/ subdirectory that doesn't exist yet.
        self.assertFalse(self._cache_file.parent.exists())
        result = cache_write(self._cache_file, self._sig, self._topology, plan_count=1, compute_duration_ms=1)
        self.assertEqual(result, CacheWriteResult.WRITTEN)
        self.assertTrue(self._cache_file.parent.exists())
        self.assertTrue(self._cache_file.exists())

    def test_06_overwrite_replaces_first(self) -> None:
        cache_write(self._cache_file, "sig_v1", {0: {"v": 1}}, plan_count=1, compute_duration_ms=1)
        cache_write(self._cache_file, "sig_v2", {0: {"v": 2}}, plan_count=1, compute_duration_ms=1)

        self.assertIsNone(cache_read(self._cache_file, "sig_v1"))
        cached = cache_read(self._cache_file, "sig_v2")
        self.assertEqual(cached, {0: {"v": 2}})

    def test_07_invalidate_then_read_is_miss(self) -> None:
        cache_write(self._cache_file, self._sig, self._topology, plan_count=2, compute_duration_ms=42)
        self.assertIsNotNone(cache_read(self._cache_file, self._sig))

        self.assertTrue(cache_invalidate(self._cache_file))
        self.assertIsNone(cache_read(self._cache_file, self._sig))

    def test_08_read_returns_none_if_file_missing(self) -> None:
        # Cache file has never been written
        self.assertIsNone(cache_read(self._cache_file, self._sig))


# ===========================================================================
# Atomic write contract
# ===========================================================================


class TestAtomicWrite(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._uploads_dir = Path(self._tmpdir.name)
        self._cache_file = resolve_cache_file("atomic_sess", self._uploads_dir)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_01_no_tmp_file_left_on_success(self) -> None:
        cache_write(self._cache_file, "sig", _topology(), plan_count=1, compute_duration_ms=1)
        # No leftover tmp.<uuid> siblings of the cache file
        siblings = list(self._cache_file.parent.iterdir())
        non_cache = [s for s in siblings if s.name != self._cache_file.name]
        self.assertEqual(non_cache, [], f"Stray tmp files: {non_cache}")

    def test_02_oversize_refused(self) -> None:
        # Build a topology that serializes well above the 5 MB cap.
        # Use a long-stringed value to inflate.
        oversize_value = "x" * (MAX_TOPOLOGY_BYTES + 1024)
        topology = {0: {"blob": oversize_value}}
        result = cache_write(self._cache_file, "sig", topology, plan_count=1, compute_duration_ms=1)
        self.assertEqual(result, CacheWriteResult.REFUSED_OVERSIZE)
        self.assertFalse(self._cache_file.exists())

    def test_03_invalid_payload_refused(self) -> None:
        # set() is not JSON-serializable
        topology = {0: {"unserialized": {1, 2, 3}}}
        result = cache_write(self._cache_file, "sig", topology, plan_count=1, compute_duration_ms=1)
        self.assertEqual(result, CacheWriteResult.REFUSED_INVALID)
        self.assertFalse(self._cache_file.exists())

    def test_04_oversize_preserves_existing_cache(self) -> None:
        # Step 1: write a valid cache
        original_topology = _topology()
        cache_write(self._cache_file, "orig_sig", original_topology, plan_count=2, compute_duration_ms=10)
        self.assertTrue(self._cache_file.exists())

        # Step 2: attempt an oversize write
        oversize_value = "x" * (MAX_TOPOLOGY_BYTES + 1024)
        oversize_topology = {0: {"blob": oversize_value}}
        result = cache_write(self._cache_file, "new_sig", oversize_topology, plan_count=1, compute_duration_ms=1)
        self.assertEqual(result, CacheWriteResult.REFUSED_OVERSIZE)

        # Step 3: original cache is still readable with original signature
        cached = cache_read(self._cache_file, "orig_sig")
        self.assertEqual(cached, original_topology)


# ===========================================================================
# Schema validation (read-side)
# ===========================================================================


class TestSchemaValidation(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._cache_file = Path(self._tmpdir.name) / "x.json"

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _write_raw(self, payload_str: str) -> None:
        self._cache_file.write_text(payload_str, encoding="utf-8")

    def test_01_miss_on_corrupt_json(self) -> None:
        self._write_raw("{ this is not valid json")
        self.assertIsNone(cache_read(self._cache_file, "any_sig"))

    def test_02_miss_on_wrong_schema_version(self) -> None:
        payload = {
            "schema": "plan-topology-cache-99",
            "plan_set_signature": "sig",
            "topology": {},
        }
        self._write_raw(json.dumps(payload))
        self.assertIsNone(cache_read(self._cache_file, "sig"))

    def test_03_miss_on_missing_topology_field(self) -> None:
        payload = {
            "schema": SCHEMA_VERSION,
            "plan_set_signature": "sig",
        }
        self._write_raw(json.dumps(payload))
        self.assertIsNone(cache_read(self._cache_file, "sig"))

    def test_04_miss_on_non_dict_topology(self) -> None:
        payload = {
            "schema": SCHEMA_VERSION,
            "plan_set_signature": "sig",
            "topology": [],
        }
        self._write_raw(json.dumps(payload))
        self.assertIsNone(cache_read(self._cache_file, "sig"))

    def test_05_miss_on_missing_signature_field(self) -> None:
        payload = {
            "schema": SCHEMA_VERSION,
            "topology": {"0": {}},
        }
        self._write_raw(json.dumps(payload))
        # No plan_set_signature field — read uses .get() which returns None;
        # comparison against "sig" fails → miss.
        self.assertIsNone(cache_read(self._cache_file, "sig"))

    def test_06_miss_on_non_dict_root(self) -> None:
        self._write_raw(json.dumps(["not", "an", "object"]))
        self.assertIsNone(cache_read(self._cache_file, "sig"))


# ===========================================================================
# Invalidation
# ===========================================================================


class TestInvalidation(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._cache_file = Path(self._tmpdir.name) / "x.json"

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_01_existing_file_removed(self) -> None:
        self._cache_file.write_text("{}", encoding="utf-8")
        self.assertTrue(self._cache_file.exists())

        self.assertTrue(cache_invalidate(self._cache_file))
        self.assertFalse(self._cache_file.exists())

    def test_02_missing_file_returns_true(self) -> None:
        # File never existed; invalidate is idempotent.
        self.assertTrue(cache_invalidate(self._cache_file))

    def test_03_on_permission_error_returns_false(self) -> None:
        self._cache_file.write_text("{}", encoding="utf-8")

        # Monkey-patch Path.unlink to raise OSError
        def raising_unlink(self_path):  # noqa: ARG001
            raise OSError("simulated permission denied")

        with patch.object(Path, "unlink", raising_unlink):
            result = cache_invalidate(self._cache_file)

        self.assertFalse(result)
        self.assertTrue(self._cache_file.exists(), "file should still exist after failed invalidate")

    def test_04_safe_to_call_multiple_times(self) -> None:
        self._cache_file.write_text("{}", encoding="utf-8")
        self.assertTrue(cache_invalidate(self._cache_file))
        self.assertTrue(cache_invalidate(self._cache_file))  # second call no-ops
        self.assertTrue(cache_invalidate(self._cache_file))  # third call no-ops


# ===========================================================================
# Kill switch helper
# ===========================================================================


class TestKillSwitch(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = os.environ.pop(KILL_SWITCH_ENV, None)

    def tearDown(self) -> None:
        if self._saved is None:
            os.environ.pop(KILL_SWITCH_ENV, None)
        else:
            os.environ[KILL_SWITCH_ENV] = self._saved

    def test_01_default_false(self) -> None:
        self.assertFalse(kill_switch_active())

    def test_02_truthy_values(self) -> None:
        for v in ("1", "true", "yes", "TRUE", "Yes", "YES"):
            with self.subTest(value=v):
                os.environ[KILL_SWITCH_ENV] = v
                self.assertTrue(kill_switch_active(), f"{v!r} should be truthy")

    def test_03_falsy_values(self) -> None:
        for v in ("0", "false", "no", "", "False", "off"):
            with self.subTest(value=v):
                os.environ[KILL_SWITCH_ENV] = v
                self.assertFalse(kill_switch_active(), f"{v!r} should be falsy")

    def test_04_whitespace_handling(self) -> None:
        os.environ[KILL_SWITCH_ENV] = "  1  "
        self.assertTrue(kill_switch_active())

    def test_05_unknown_value_treated_false(self) -> None:
        for v in ("maybe", "xyz", "enable"):
            with self.subTest(value=v):
                os.environ[KILL_SWITCH_ENV] = v
                self.assertFalse(kill_switch_active())


# ===========================================================================
# Integration hook with _save_engineering_plan_index
# ===========================================================================


class TestIntegrationHook(unittest.TestCase):
    """Verify _save_engineering_plan_index invalidates per-session caches.

    Uses the real UPLOADS_DIR (whatever main.py resolved at import time).
    Cache files are created with UUID-prefixed session IDs to avoid
    colliding with real session data. Each test backs up and restores
    the existing engineering plan index.json so production data is not
    polluted.
    """

    @classmethod
    def setUpClass(cls) -> None:
        from backend import main as M
        cls._M = M
        cls._uploads_dir: Path = M.UPLOADS_DIR
        cls._index_path: Path = M.ENGINEERING_PLAN_INDEX_PATH

    def setUp(self) -> None:
        # Snapshot the existing index.json (if any) for restoration in tearDown.
        if self._index_path.exists():
            self._saved_index = self._index_path.read_text(encoding="utf-8")
        else:
            self._saved_index = None

        self._created_sids: List[str] = []

    def tearDown(self) -> None:
        # Remove any synthetic cache files we created
        for sid in self._created_sids:
            cache_file = resolve_cache_file(sid, self._uploads_dir)
            try:
                if cache_file.exists():
                    cache_file.unlink()
            except OSError:
                pass

        # Restore the original index.json content
        if self._saved_index is not None:
            self._index_path.write_text(self._saved_index, encoding="utf-8")
        else:
            try:
                if self._index_path.exists():
                    self._index_path.unlink()
            except OSError:
                pass

    def _create_synthetic_cache(self, sid: str) -> Path:
        cache_file = resolve_cache_file(sid, self._uploads_dir)
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": SCHEMA_VERSION,
            "session_id": sid,
            "plan_set_signature": "test_sig",
            "plan_count": 0,
            "generated_at": "2026-05-20T00:00:00Z",
            "generated_by": "test",
            "topology_bytes": 0,
            "compute_duration_ms": 0,
            "topology": {},
        }
        cache_file.write_text(json.dumps(payload), encoding="utf-8")
        self._created_sids.append(sid)
        return cache_file

    def test_01_save_index_invalidates_caches_for_affected_sessions(self) -> None:
        sid_a = f"ri2_int_{uuid.uuid4().hex[:12]}"
        sid_b = f"ri2_int_{uuid.uuid4().hex[:12]}"
        sid_c = f"ri2_int_{uuid.uuid4().hex[:12]}"  # control — should survive

        cache_a = self._create_synthetic_cache(sid_a)
        cache_b = self._create_synthetic_cache(sid_b)
        cache_c = self._create_synthetic_cache(sid_c)

        self.assertTrue(cache_a.exists())
        self.assertTrue(cache_b.exists())
        self.assertTrue(cache_c.exists())

        index_data = {
            "plans": [
                {"session_id": sid_a, "plan_id": "p1", "stored_filename": "x.pdf",
                 "size_bytes": 100, "uploaded_at": "2026-05-20T00:00:00Z"},
                {"session_id": sid_b, "plan_id": "p2", "stored_filename": "y.pdf",
                 "size_bytes": 200, "uploaded_at": "2026-05-20T00:00:00Z"},
            ]
        }
        self._M._save_engineering_plan_index(index_data)

        self.assertFalse(cache_a.exists(), f"{sid_a} cache should be invalidated")
        self.assertFalse(cache_b.exists(), f"{sid_b} cache should be invalidated")
        self.assertTrue(cache_c.exists(), f"{sid_c} cache should be untouched")

    def test_02_save_index_with_empty_plans_invalidates_nothing(self) -> None:
        sid_a = f"ri2_int_{uuid.uuid4().hex[:12]}"
        cache_a = self._create_synthetic_cache(sid_a)
        self.assertTrue(cache_a.exists())

        self._M._save_engineering_plan_index({"plans": []})

        self.assertTrue(cache_a.exists(), "no invalidation should occur with empty plans")


if __name__ == "__main__":
    unittest.main()
