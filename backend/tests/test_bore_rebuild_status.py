"""Async bore rebuild — durable status, state promotion, and staleness watchdog.

The async rebuild (TRUELINE_BORE_ASYNC_REBUILD) was leaving the UI stuck on
"processing" forever when the background task was SIGKILLed mid-rebuild (OOM /
worker timeout): it could never write its own failure, and current-state never
exposed a rebuild status. This locks:

- _rebuild_status_fields() ages a pending/running rebuild past the staleness
  window out to a terminal "failed" (so the UI can never hang),
- _run_bore_rebuild_background promotes running -> complete on success and
  -> failed (with reason) on a caught exception, persisting both durably.

Drives the functions directly (no TestClient/auth). Run from repo root:
    python -m pytest backend/tests/test_bore_rebuild_status.py -v
"""
from __future__ import annotations

import os
import pathlib
import tempfile
import time
import unittest

os.environ.setdefault("TRUELINE_JWT_SECRET", "rebuild-status-test")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "rebuild-status-auth")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")
os.environ["OSP_UPLOAD_DIR"] = tempfile.mkdtemp(prefix="rebuild_status_")

from backend import main as M  # noqa: E402 — after env defaults

# Hard-isolate storage from the real backend/uploads regardless of import order.
_TMP = pathlib.Path(tempfile.mkdtemp(prefix="rebuild_status_iso_"))
M.UPLOADS_DIR = _TMP
M.SESSION_DB_PATH = _TMP / "session_store.db"
M.ENGINEERING_PLAN_ROOT = _TMP / "engineering_plans"
M.ENGINEERING_PLAN_INDEX_PATH = M.ENGINEERING_PLAN_ROOT / "index.json"
M.ENGINEERING_PLAN_CHUNK_ROOT = M.ENGINEERING_PLAN_ROOT / "_chunks"
M._init_session_db()


class TestRebuildStatusFields(unittest.TestCase):
    def setUp(self):
        M.STATE.clear()

    def test_complete_passthrough(self):
        M.STATE["rebuild_status"] = "complete"
        self.assertEqual(M._rebuild_status_fields()["rebuild_status"], "complete")

    def test_running_recent_stays_running(self):
        M.STATE["rebuild_status"] = "running"
        M.STATE["rebuild_started_at"] = time.time()  # just now
        self.assertEqual(M._rebuild_status_fields()["rebuild_status"], "running")

    def test_pending_stale_ages_to_failed(self):
        M.STATE["rebuild_status"] = "pending"
        M.STATE["rebuild_started_at"] = time.time() - (M.REBUILD_STALE_SECONDS + 60)
        fields = M._rebuild_status_fields()
        self.assertEqual(fields["rebuild_status"], "failed")
        self.assertTrue(fields.get("rebuild_stalled"))
        self.assertTrue(fields.get("rebuild_error"))

    def test_running_without_start_time_not_aged(self):
        # No started_at => cannot age; stays running (defensive, never crashes).
        M.STATE["rebuild_status"] = "running"
        self.assertEqual(M._rebuild_status_fields()["rebuild_status"], "running")


class TestRunBoreRebuildBackground(unittest.TestCase):
    def test_success_marks_complete_and_persists_outputs(self):
        sid = "rb-ok-1"
        with M._session_scope(sid):
            M.STATE["committed_rows"] = []  # trivial rebuild -> empty outputs, completes fast
        M._run_bore_rebuild_background(sid)
        loaded = M._load_persisted_session(sid)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.get("rebuild_status"), "complete")
        self.assertIsNotNone(loaded.get("rebuild_finished_at"))
        self.assertIsNotNone(loaded.get("rebuild_elapsed_ms"))
        # Outputs were promoted into the persisted session.
        self.assertIn("station_points", loaded)
        self.assertIn("redline_segments", loaded)

    def test_exception_marks_failed_and_persists_reason(self):
        sid = "rb-fail-1"
        with M._session_scope(sid):
            M.STATE["committed_rows"] = []
        orig = M._rebuild_field_data_outputs

        def _boom(*args, **kwargs):
            raise RuntimeError("simulated rebuild failure")

        M._rebuild_field_data_outputs = _boom
        try:
            M._run_bore_rebuild_background(sid)
        finally:
            M._rebuild_field_data_outputs = orig

        loaded = M._load_persisted_session(sid)
        self.assertEqual(loaded.get("rebuild_status"), "failed")
        self.assertIn("simulated rebuild failure", str(loaded.get("rebuild_error")))
        self.assertIsNotNone(loaded.get("rebuild_finished_at"))


if __name__ == "__main__":
    unittest.main()
