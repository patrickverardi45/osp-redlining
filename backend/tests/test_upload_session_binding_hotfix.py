"""Session-binding hotfix tests for /api/upload-design and /api/upload-structured-bore-files.

Both endpoints used to call `_resolve_session_id`, which MINTS a random uuid when the
multipart `session_id` is empty — orphaning route_catalog / committed_rows off the active
project (the beta-test "No route catalog loaded" symptom). The hotfix switches them to the
same non-minting form->query->error resolver the engineering-plan upload uses.

Targeted/route-level + import test (no KMZ parsing, no multipart machinery): drive the error
path directly and assert the resolver behavior + endpoint wiring. Run from repo root:
    python -m pytest backend/tests/test_upload_session_binding_hotfix.py -v
"""
from __future__ import annotations

import asyncio
import inspect
import os

os.environ.setdefault("TRUELINE_JWT_SECRET", "hotfix-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "hotfix-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend import main as M  # noqa: E402 — after env defaults


class _FakeReq:
    """Minimal stand-in: the patched endpoints only read request.query_params.get('session_id')."""
    def __init__(self, query=None):
        self.query_params = query or {}


def _decoded(resp):
    return bytes(resp.body).decode().lower()


# ── the shared non-minting resolver behaves form -> query -> None ────────────────────────────
def test_resolver_form_then_query_then_none():
    assert M._resolve_engineering_plan_session_id("beta-test", None) == "beta-test"
    assert M._resolve_engineering_plan_session_id("  beta-test  ", None) == "beta-test"
    assert M._resolve_engineering_plan_session_id("", "beta-test") == "beta-test"   # query fallback
    assert M._resolve_engineering_plan_session_id(None, None) is None               # never mints
    assert M._resolve_engineering_plan_session_id("", "") is None


# ── the shared minting helper is UNCHANGED elsewhere (we only swapped 2 call sites) ──────────
def test_minting_helper_unchanged():
    assert M._resolve_session_id("beta-test") == "beta-test"
    minted = M._resolve_session_id("")           # still mints for empty input
    assert isinstance(minted, str) and len(minted) >= 16


# ── both patched endpoints now accept the request (so the query-param fallback works) ────────
def test_endpoints_accept_request_param():
    assert "request" in inspect.signature(M.upload_design).parameters
    assert "request" in inspect.signature(M.upload_structured_bore_files).parameters


# ── error-not-mint: no session id anywhere => clear error, no orphaned session ────────────────
def test_upload_design_without_session_errors_not_mints():
    resp = asyncio.run(M.upload_design(_FakeReq(), file=None, session_id="", project_id=None))
    body = _decoded(resp)
    assert "active workspace session is required" in body
    assert "design" in body  # design/KMZ-specific message


def test_upload_structured_bore_without_session_errors_not_mints():
    # background_tasks param (added for the staged-rebuild flag) is unused on this
    # early-return path; pass None.
    resp = asyncio.run(M.upload_structured_bore_files(_FakeReq(), None, files=[], session_id=""))
    body = _decoded(resp)
    assert "active workspace session is required" in body
    assert "bore-log" in body  # bore-specific message


# ── query-param path resolves (the direct-to-Render multipart case where the form is dropped) ─
def test_query_param_session_is_honored():
    # form empty, query carries beta-test -> resolver binds to beta-test (no mint)
    assert M._resolve_engineering_plan_session_id("", "beta-test") == "beta-test"
