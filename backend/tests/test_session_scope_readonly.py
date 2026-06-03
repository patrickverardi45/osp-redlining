"""Session-scope readonly mode + session-size instrumentation (OOM survivability).

Read-only routes (e.g. /api/current-state, kmz-render-payload, per-chunk closeout
checks) must NOT re-serialize + rewrite the entire multi-MB session JSON on every
request — that repeated json.dumps + SQLite write is a major source of memory/IO
churn under polling. This locks:

- a writing _session_scope persists mutations (unchanged behavior),
- a readonly _session_scope does NOT persist mutations,
- _log_session_size_if_large fires over threshold and names the largest key,
  and is silent under threshold.

Drives the primitives directly (no TestClient/auth). Run from repo root:
    python -m pytest backend/tests/test_session_scope_readonly.py -v
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest

os.environ.setdefault("TRUELINE_JWT_SECRET", "ro-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "ro-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")
os.environ["OSP_UPLOAD_DIR"] = tempfile.mkdtemp(prefix="ro_session_test_")

import pathlib  # noqa: E402

from backend import main as M  # noqa: E402 — after env defaults

# Hard-isolate the session DB from the real backend/uploads REGARDLESS of test
# import order (another module may import backend.main first). Override the
# module global and (re)create the sessions table in the private temp DB.
_TMP_ROOT = pathlib.Path(tempfile.mkdtemp(prefix="ro_session_iso_"))
M.SESSION_DB_PATH = _TMP_ROOT / "session_store.db"
M._init_session_db()


class TestSessionScopeReadonly(unittest.TestCase):
    def test_writing_scope_persists_mutation(self):
        sid = "ro-write-1"
        with M._session_scope(sid):
            M.STATE["route_name"] = "WROTE_IT"
        loaded = M._load_persisted_session(sid)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.get("route_name"), "WROTE_IT")

    def test_readonly_scope_does_not_persist_mutation(self):
        sid = "ro-read-1"
        # Seed a known persisted value with a normal writing scope.
        with M._session_scope(sid):
            M.STATE["route_name"] = "ORIGINAL"
        # Enter readonly, mutate STATE (top-level), exit.
        with M._session_scope(sid, readonly=True):
            self.assertEqual(M.STATE.get("route_name"), "ORIGINAL")
            M.STATE["route_name"] = "SHOULD_NOT_PERSIST"
        # Disk must still hold the original — the readonly exit skipped the save.
        reloaded = M._load_persisted_session(sid)
        self.assertEqual(reloaded.get("route_name"), "ORIGINAL")

    def test_size_logger_fires_over_threshold_and_names_top_key(self):
        original = M.SESSION_SIZE_WARN_BYTES
        try:
            M.SESSION_SIZE_WARN_BYTES = 1000
            data = {"big": "x" * 5000, "small": [1, 2, 3]}
            js = json.dumps(data)
            with self.assertLogs(level="WARNING") as cm:
                M._log_session_size_if_large("sid-big", data, js)
            joined = "\n".join(cm.output)
            self.assertIn("session_size", joined)
            self.assertIn("big=", joined)  # largest key surfaced
        finally:
            M.SESSION_SIZE_WARN_BYTES = original

    def test_size_logger_silent_under_threshold(self):
        original = M.SESSION_SIZE_WARN_BYTES
        try:
            M.SESSION_SIZE_WARN_BYTES = 10 ** 9
            data = {"k": "small"}
            js = json.dumps(data)
            # assertNoLogs (py3.10+) — no WARNING emitted under threshold.
            with self.assertNoLogs(level="WARNING"):
                M._log_session_size_if_large("sid-small", data, js)
        finally:
            M.SESSION_SIZE_WARN_BYTES = original


if __name__ == "__main__":
    unittest.main()
