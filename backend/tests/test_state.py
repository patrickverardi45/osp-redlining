"""Cleanup PR-2 — session-state data-layer extraction (backend/app/state.py).

Locks the behaviour-preserving contract of moving STATE / _SESSIONS /
_SESSION_LOCK / _default_session_state / _resolve_session_id out of main.py:

- main re-imports the moved names, so the objects main exposes ARE the objects
  app.state defines (shared single instance — the load-bearing invariant).
- the monolith still imports cleanly.
- _session_scope STAYS in main.py and its round-trip is unchanged.

``import app.state`` (top-level ``app``) resolves to the SAME module object that
main.py binds via ``from app.state import ...`` — both rely on ``backend/`` being
on sys.path during the test run — so the identity assertions are meaningful.
"""
from __future__ import annotations

import os
import uuid

os.environ.setdefault("TRUELINE_JWT_SECRET", "state-extraction-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "state-extraction-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend import main as M  # noqa: E402 — must follow env defaults
import app.state as state_mod  # noqa: E402 — same module instance main imports


def test_state_objects_are_shared_with_main():
    # The whole extraction rests on a single shared, never-rebound object.
    assert state_mod.STATE is M.STATE
    assert state_mod._SESSIONS is M._SESSIONS
    assert state_mod._SESSION_LOCK is M._SESSION_LOCK
    # main re-imports (does not redefine) the moved callables.
    assert state_mod._default_session_state is M._default_session_state
    assert state_mod._resolve_session_id is M._resolve_session_id


def test_backend_main_imports_cleanly():
    # Import smoke — the 25k-line monolith still loads after the extraction.
    import backend.main as _again  # noqa: F401

    assert M.STATE is not None
    assert isinstance(M._SESSIONS, dict)


def test_default_session_state_key_set():
    s = M._default_session_state()
    expected = {
        "route_name",
        "route_id",
        "route_coords",
        "route_length_ft",
        "route_catalog",
        "committed_rows",
        "station_points",
        "redline_segments",
        "kmz_reference",
        "match_overrides",
        "walk_active",
        "closeout_lock",
        "company_id",
        "tenant_id",
        "created_at",
        "updated_at",
    }
    missing = expected - set(s)
    assert not missing, f"missing keys: {sorted(missing)}"
    # Factory hands back a fresh dict each call (not a shared singleton).
    assert M._default_session_state() is not s


def test_resolve_session_id_mints_when_empty():
    minted = M._resolve_session_id("")
    assert isinstance(minted, str) and minted
    # None also mints a fresh id; two mints differ.
    assert M._resolve_session_id(None)
    assert M._resolve_session_id("") != M._resolve_session_id("")


def test_resolve_session_id_echoes_explicit():
    assert M._resolve_session_id("x") == "x"
    assert M._resolve_session_id("  abc  ") == "abc"  # strips whitespace


def test_session_scope_round_trip_unchanged():
    # _session_scope stays in main.py; entering clears+loads STATE, exiting
    # persists the snapshot. A second scope must reload what the first wrote.
    sid = "pr2-state-roundtrip-" + uuid.uuid4().hex
    sentinel = "PR2-RT-" + uuid.uuid4().hex
    with M._session_scope(sid):
        M.STATE["route_name"] = sentinel
    with M._session_scope(sid):
        assert M.STATE.get("route_name") == sentinel
    # Mutating STATE inside the scope mutates the shared app.state object.
    with M._session_scope(sid):
        assert state_mod.STATE.get("route_name") == sentinel
