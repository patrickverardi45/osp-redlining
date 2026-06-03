"""Survival-guard tests for /api/upload-structured-bore-files.

Disk exhaustion was ruled out as the bore-upload 502 cause; the remaining risks
are processing time (the rebuild over ~1,339 Brenham rows) and memory. This file
covers the small, isolated SIZE guard added to the handler: an absurdly large
upload now returns a clean JSON 413 instead of being read fully into memory and
risking an OOM worker death (which the client would see as an HTML 502).

Route-level (no multipart machinery, no KMZ, no session scope): the 413 fires in
the file-read loop BEFORE the session scope / rebuild, so no STATE is needed.
Run from repo root:
    python -m pytest backend/tests/test_bore_upload_size_guard.py -v
"""
from __future__ import annotations

import asyncio
import os

os.environ.setdefault("TRUELINE_JWT_SECRET", "guard-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "guard-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend import main as M  # noqa: E402 — after env defaults


class _FakeReq:
    """Minimal stand-in: the handler only reads request.query_params.get('session_id')."""

    def __init__(self, query=None):
        self.query_params = query or {}


class _FakeUpload:
    """Minimal UploadFile stand-in: the handler only uses .filename and await .read()."""

    def __init__(self, data: bytes, filename: str):
        self._data = data
        self.filename = filename

    async def read(self) -> bytes:
        return self._data


def _decoded(resp) -> str:
    return bytes(resp.body).decode().lower()


def test_oversize_bore_file_returns_413(monkeypatch):
    # Patch the cap tiny so we don't allocate 50 MB; a 64-byte file then trips it.
    monkeypatch.setattr(M, "_MAX_BORE_UPLOAD_BYTES", 16)
    big = _FakeUpload(b"x" * 64, "huge.csv")
    resp = asyncio.run(
        M.upload_structured_bore_files(_FakeReq(), None, files=[big], session_id="beta-test")
    )
    assert resp.status_code == 413
    body = _decoded(resp)
    assert "bore-log file" in body and "limit" in body
    assert "huge.csv" in body


def test_size_cap_is_generous_enough_for_real_files():
    # Real Brenham bore CSV is ~1.1 MB; the cap must never block a legitimate file.
    assert M._MAX_BORE_UPLOAD_BYTES >= 25 * 1024 * 1024


def test_missing_session_errors_before_size_guard():
    # No session id anywhere -> the non-minting resolver returns the
    # session-required error BEFORE the file loop / size guard runs. Ordering
    # check: a missing session is a session error, never a spurious 413.
    resp = asyncio.run(
        M.upload_structured_bore_files(_FakeReq(), None, files=[], session_id="")
    )
    assert resp.status_code != 413
    assert "active workspace session is required" in _decoded(resp)


def test_async_rebuild_flag_defaults_off(monkeypatch):
    # The staged/deferred rebuild is opt-in: default OFF so the synchronous path
    # (today's behavior) is unchanged unless the operator enables it.
    monkeypatch.delenv("TRUELINE_BORE_ASYNC_REBUILD", raising=False)
    assert M._trueline_bore_async_rebuild_enabled() is False
    for truthy in ("1", "true", "YES", "on"):
        monkeypatch.setenv("TRUELINE_BORE_ASYNC_REBUILD", truthy)
        assert M._trueline_bore_async_rebuild_enabled() is True
    for falsy in ("0", "false", "", "off"):
        monkeypatch.setenv("TRUELINE_BORE_ASYNC_REBUILD", falsy)
        assert M._trueline_bore_async_rebuild_enabled() is False
