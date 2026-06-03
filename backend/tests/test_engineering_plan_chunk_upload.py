"""Chunked large-engineering-plan upload — reassemble + register (LP.1).

Locks the behavior of the chunked upload path that lets large engineering PDFs
(e.g. the ~13 MB Brenham plan set) reach the backend through the same-origin
Vercel proxy in sub-ceiling chunks — avoiding both browser CORS and the Vercel
~4.5 MB serverless request-body limit.

Drives ``upload_engineering_plans_chunk`` directly (no TestClient/auth) the same
way ``test_upload_session_binding_hotfix.py`` drives the upload endpoints:
``asyncio.run`` + a minimal fake request + Starlette ``UploadFile`` chunks.

Asserts:
- a multi-chunk upload reassembles BYTE-EXACT and registers exactly one plan,
- a single-chunk upload registers immediately,
- a missing session is rejected (never minted),
- an oversized chunk and an unsupported extension are rejected,
- the on-disk staging directory is cleaned up after finalize.

Run from repo root:
    python -m pytest backend/tests/test_engineering_plan_chunk_upload.py -v
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import tempfile
import unittest

os.environ.setdefault("TRUELINE_JWT_SECRET", "lp1-chunk-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "lp1-chunk-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")
os.environ["OSP_UPLOAD_DIR"] = tempfile.mkdtemp(prefix="lp1_chunk_uploads_")

import pathlib  # noqa: E402

from starlette.datastructures import UploadFile  # noqa: E402 — after env defaults
from backend import main as M  # noqa: E402 — after env defaults

# Hard-isolate storage from the real backend/uploads REGARDLESS of test import
# order. The storage roots are computed at import time, and another test module
# may import backend.main first (binding the real uploads dir before our env var
# takes effect), so override the module globals to a private temp dir here and
# (re)create the session DB there.
_TMP_ROOT = pathlib.Path(tempfile.mkdtemp(prefix="lp1_chunk_iso_"))
M.UPLOADS_DIR = _TMP_ROOT
M.SESSION_DB_PATH = _TMP_ROOT / "session_store.db"
M.ENGINEERING_PLAN_ROOT = _TMP_ROOT / "engineering_plans"
M.ENGINEERING_PLAN_INDEX_PATH = M.ENGINEERING_PLAN_ROOT / "index.json"
M.ENGINEERING_PLAN_CHUNK_ROOT = M.ENGINEERING_PLAN_ROOT / "_chunks"
M._init_session_db()


class _FakeReq:
    """Minimal stand-in: the endpoint only reads request.query_params.get('session_id')."""

    def __init__(self, query=None):
        self.query_params = query or {}


def _decode(resp):
    return json.loads(bytes(resp.body).decode())


def _upload_chunk(*, session_id, upload_id, index, total, file_name, data, query=None):
    chunk = UploadFile(filename="chunk", file=io.BytesIO(data))
    # Calling the coroutine directly bypasses FastAPI dependency injection, so the
    # optional metadata params must be passed as real None (FastAPI would normally
    # substitute None for these Form(None) defaults when the client omits them).
    return asyncio.run(
        M.upload_engineering_plans_chunk(
            _FakeReq(query),
            chunk=chunk,
            upload_id=upload_id,
            chunk_index=index,
            total_chunks=total,
            file_name=file_name,
            session_id=session_id,
            plan_date=None,
            print_numbers=None,
            sheet_numbers=None,
            street_hints=None,
            notes=None,
        )
    )


class TestEngineeringPlanChunkUpload(unittest.TestCase):
    def test_multichunk_reassembles_and_registers_one_plan(self):
        session_id = "lp1-sess-A"
        upload_id = "upA-0123abcd"
        parts = [b"%PDF-1.7 chunk-0 ", b"chunk-1 payload ", b"chunk-2 tail %%EOF"]
        full = b"".join(parts)
        total = len(parts)

        # First N-1 chunks: "uploading" acks, not finalized.
        for i in range(total - 1):
            resp = _upload_chunk(
                session_id=session_id, upload_id=upload_id, index=i,
                total=total, file_name="brenham.pdf", data=parts[i],
            )
            self.assertEqual(resp.status_code, 200)
            body = _decode(resp)
            self.assertEqual(body.get("phase"), "uploading")
            self.assertEqual(body.get("received_chunks"), i + 1)
            self.assertEqual(body.get("total_chunks"), total)

        # Final chunk: reassemble + register.
        resp = _upload_chunk(
            session_id=session_id, upload_id=upload_id, index=total - 1,
            total=total, file_name="brenham.pdf", data=parts[-1],
        )
        self.assertEqual(resp.status_code, 200)
        body = _decode(resp)
        self.assertTrue(body.get("success"))

        mine = [p for p in (body.get("engineering_plans") or []) if p.get("session_id") == session_id]
        self.assertEqual(len(mine), 1, "exactly one plan should be registered")
        self.assertEqual(mine[0]["size_bytes"], len(full))
        self.assertEqual(mine[0]["original_filename"], "brenham.pdf")
        self.assertEqual(mine[0]["file_type"], "application/pdf")

        # Assembled bytes on disk match the original concatenation exactly.
        index_data = M._load_engineering_plan_index()
        rec = next(
            r for r in index_data["plans"]
            if r.get("session_id") == session_id and r.get("plan_id") == mine[0]["plan_id"]
        )
        with open(rec["stored_path"], "rb") as fh:
            self.assertEqual(fh.read(), full)

        # Staging directory is cleaned up after finalize.
        staging = M.ENGINEERING_PLAN_CHUNK_ROOT / M._safe_filename(session_id) / M._safe_filename(upload_id)
        self.assertFalse(staging.exists())

    def test_single_chunk_registers_immediately(self):
        session_id = "lp1-sess-B"
        data = b"%PDF-1.7 single chunk %%EOF"
        resp = _upload_chunk(
            session_id=session_id, upload_id="upB-1", index=0,
            total=1, file_name="small.pdf", data=data,
        )
        self.assertEqual(resp.status_code, 200)
        body = _decode(resp)
        self.assertTrue(body.get("success"))
        mine = [p for p in (body.get("engineering_plans") or []) if p.get("session_id") == session_id]
        self.assertEqual(len(mine), 1)
        self.assertEqual(mine[0]["size_bytes"], len(data))

    def test_missing_session_is_rejected_not_minted(self):
        resp = _upload_chunk(
            session_id="", upload_id="upC-1", index=0,
            total=1, file_name="x.pdf", data=b"abc",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(_decode(resp).get("success"))
        self.assertIn("active workspace session is required", bytes(resp.body).decode().lower())

    def test_oversized_chunk_rejected(self):
        big = b"x" * (M.ENGINEERING_PLAN_CHUNK_MAX_BYTES + 1)
        resp = _upload_chunk(
            session_id="lp1-sess-D", upload_id="upD-1", index=0,
            total=1, file_name="big.pdf", data=big,
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("chunk exceeds", bytes(resp.body).decode().lower())

    def test_unsupported_extension_rejected(self):
        resp = _upload_chunk(
            session_id="lp1-sess-E", upload_id="upE-1", index=0,
            total=1, file_name="evil.exe", data=b"MZ",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("unsupported file type", bytes(resp.body).decode().lower())

    def test_path_traversal_upload_id_rejected(self):
        resp = _upload_chunk(
            session_id="lp1-sess-F", upload_id="../../etc/evil", index=0,
            total=1, file_name="x.pdf", data=b"abc",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("upload_id", bytes(resp.body).decode().lower())


if __name__ == "__main__":
    unittest.main()
