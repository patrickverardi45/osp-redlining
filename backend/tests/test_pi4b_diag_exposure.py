"""PI.4B.2 diagnostic exposure tests — Phase A proving infrastructure.

Verifies that ``/api/debug/pipeline-diag`` surfaces
``STATE[_PI4B_ATTRIBUTION_STATE_KEY]`` under the key ``_PI4B_DIAG_KEY``
(``pi4b_print_to_sheets_attribution``) so Tier-2 PDF proving results can
be observed after controlled flag flips.

These tests call ``debug_pipeline_diag`` directly with a session_id; the
session is pre-seeded into ``_SESSIONS`` and disk persistence is mocked,
so no real session lifecycle / disk I/O is involved. The endpoint's
exception-free behavior under both flag-OFF (empty dict) and flag-ON
(populated dict) STATE is the contract under test here.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

import pytest

# Make ``backend`` importable when pytest is invoked from the repo root.
_BACKEND_PARENT = Path(__file__).resolve().parents[2]
if str(_BACKEND_PARENT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_PARENT))

# Required for backend.main import (mirrors existing PT.ACT test prelude).
os.environ.setdefault("TRUELINE_JWT_SECRET", "pi4b-diag-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "pi4b-diag-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend import main as M  # noqa: E402


_TEST_SID = "pi4b-diag-test-sid"


def _decode(response: Any) -> Dict[str, Any]:
    """Decode a starlette JSONResponse body back into a Python dict."""
    return json.loads(bytes(response.body).decode("utf-8"))


@pytest.fixture(autouse=True)
def _isolate_session_storage(monkeypatch):
    """Snapshot _SESSIONS + STATE; mock disk persistence; restore on exit."""
    saved_sessions = dict(M._SESSIONS)
    saved_state = dict(M.STATE)
    monkeypatch.setattr(M, "_persist_session", lambda *args, **kwargs: None)
    M._SESSIONS.pop(_TEST_SID, None)
    yield
    M._SESSIONS.clear()
    M._SESSIONS.update(saved_sessions)
    M.STATE.clear()
    M.STATE.update(saved_state)


def _seed_session(*, attribution: Any = ...) -> None:
    """Pre-populate ``_SESSIONS[_TEST_SID]`` with a default state plus an
    optional attribution dict. ``attribution=...`` sentinel means "do not
    set the key at all" (simulates seam never invoked).
    """
    session = M._default_session_state()
    if attribution is not ...:
        session[M._PI4B_ATTRIBUTION_STATE_KEY] = attribution
    M._SESSIONS[_TEST_SID] = session


# ─── 1. field present when attribution state exists ───────────────────────────

def test_pi4b_diag_field_present_when_state_exists() -> None:
    synthetic = {
        "enabled":                  True,
        "session_id":               _TEST_SID,
        "catalog_size":             5,
        "catalog_source":           "built_from_1_pdfs",
        "tokens_total":             20,
        "tokens_derived":           7,
        "tokens_constant_fallback": 10,
        "tokens_disagreement":      2,
        "tokens_refused_both":      1,
        "disagreement_examples":    [
            {"token": "3", "derived_sheet": 12, "constant_sheet": 11},
            {"token": "4", "derived_sheet": 13, "constant_sheet": 11},
        ],
    }
    _seed_session(attribution=synthetic)
    resp = M.debug_pipeline_diag(session_id=_TEST_SID)
    payload = _decode(resp)
    assert M._PI4B_DIAG_KEY in payload, f"missing key {M._PI4B_DIAG_KEY!r}"
    assert payload[M._PI4B_DIAG_KEY] == synthetic


# ─── 2. field present and {} when attribution state missing or None ───────────

def test_pi4b_diag_field_empty_when_state_key_absent() -> None:
    _seed_session()  # attribution sentinel — key not set on session
    resp = M.debug_pipeline_diag(session_id=_TEST_SID)
    payload = _decode(resp)
    assert M._PI4B_DIAG_KEY in payload
    assert payload[M._PI4B_DIAG_KEY] == {}


def test_pi4b_diag_field_empty_when_state_key_is_none() -> None:
    _seed_session(attribution=None)
    resp = M.debug_pipeline_diag(session_id=_TEST_SID)
    payload = _decode(resp)
    assert M._PI4B_DIAG_KEY in payload
    assert payload[M._PI4B_DIAG_KEY] == {}


def test_pi4b_diag_field_empty_when_state_key_is_empty_dict() -> None:
    _seed_session(attribution={})
    resp = M.debug_pipeline_diag(session_id=_TEST_SID)
    payload = _decode(resp)
    assert payload[M._PI4B_DIAG_KEY] == {}


# ─── 3. existing pipeline diag keys still present ─────────────────────────────

def test_existing_pipeline_diag_keys_still_present() -> None:
    session = M._default_session_state()
    session["pipeline_diag"] = [{"source_file": "abc.csv", "group_idx": 0}]
    session["engineering_plan_signals"] = [
        {"plan_id": "p1", "source_file": "kelly.pdf", "print_tokens": ["5"]}
    ]
    session[M._PI4B_ATTRIBUTION_STATE_KEY] = {"catalog_source": "cache_hit"}
    M._SESSIONS[_TEST_SID] = session

    resp = M.debug_pipeline_diag(session_id=_TEST_SID)
    payload = _decode(resp)

    assert payload["success"] is True
    assert payload["session_id"] == _TEST_SID
    assert payload["pipeline_diag"] == [{"source_file": "abc.csv", "group_idx": 0}]
    assert payload["engineering_plan_signal_count"] == 1
    assert payload["engineering_plan_signals"][0]["plan_id"] == "p1"
    # The new key must coexist with all of the above, not replace any.
    assert M._PI4B_DIAG_KEY in payload
    assert payload[M._PI4B_DIAG_KEY] == {"catalog_source": "cache_hit"}


def test_source_file_filter_still_applies_and_does_not_touch_pi4b() -> None:
    session = M._default_session_state()
    session["pipeline_diag"] = [
        {"source_file": "a.csv", "group_idx": 0},
        {"source_file": "b.csv", "group_idx": 1},
    ]
    session[M._PI4B_ATTRIBUTION_STATE_KEY] = {"catalog_source": "built_from_1_pdfs"}
    M._SESSIONS[_TEST_SID] = session

    resp = M.debug_pipeline_diag(session_id=_TEST_SID, source_file="a.csv")
    payload = _decode(resp)
    assert [d["source_file"] for d in payload["pipeline_diag"]] == ["a.csv"]
    # The pi4b attribution is global (not per-source-file) and must not be
    # touched by the source_file filter.
    assert payload[M._PI4B_DIAG_KEY] == {"catalog_source": "built_from_1_pdfs"}


# ─── 4. deepcopy: response mutation cannot mutate STATE ───────────────────────

def test_response_mutation_does_not_mutate_state() -> None:
    synthetic = {
        "enabled": True,
        "disagreement_examples": [
            {"token": "9", "derived_sheet": 1, "constant_sheet": 2},
        ],
    }
    _seed_session(attribution=synthetic)

    resp = M.debug_pipeline_diag(session_id=_TEST_SID)
    payload = _decode(resp)

    # Mutate the returned attribution dict (both top-level and nested list).
    payload[M._PI4B_DIAG_KEY]["enabled"] = False
    payload[M._PI4B_DIAG_KEY]["disagreement_examples"].append(
        {"token": "injected", "derived_sheet": 0, "constant_sheet": 0}
    )

    # Re-fetch; the persisted session attribution must still match the
    # original synthetic input byte-for-byte.
    resp2 = M.debug_pipeline_diag(session_id=_TEST_SID)
    payload2 = _decode(resp2)
    assert payload2[M._PI4B_DIAG_KEY]["enabled"] is True
    assert payload2[M._PI4B_DIAG_KEY]["disagreement_examples"] == [
        {"token": "9", "derived_sheet": 1, "constant_sheet": 2}
    ]


def test_state_attribution_is_not_replaced_or_cleared_by_endpoint() -> None:
    """The endpoint is read-only: STATE[_PI4B_ATTRIBUTION_STATE_KEY] must
    survive a debug fetch unchanged."""
    synthetic = {"enabled": True, "catalog_size": 3}
    _seed_session(attribution=synthetic)

    M.debug_pipeline_diag(session_id=_TEST_SID)

    # _SESSIONS still holds the same attribution dict after the endpoint
    # call (the endpoint must not have cleared, replaced, or mutated it).
    persisted_attr = M._SESSIONS[_TEST_SID].get(M._PI4B_ATTRIBUTION_STATE_KEY)
    assert persisted_attr == synthetic


# ─── 5. missing session_id behavior unchanged ─────────────────────────────────

def test_missing_session_id_returns_400_with_no_pi4b_leak() -> None:
    resp = M.debug_pipeline_diag(session_id=None)
    assert resp.status_code == 400
    payload = _decode(resp)
    assert "error" in payload
    # Critical: the 400 error path must NOT include any pi4b attribution.
    # The new exposure key lives only on the success path.
    assert M._PI4B_DIAG_KEY not in payload


def test_empty_session_id_returns_400_with_no_pi4b_leak() -> None:
    resp = M.debug_pipeline_diag(session_id="   ")
    assert resp.status_code == 400
    payload = _decode(resp)
    assert M._PI4B_DIAG_KEY not in payload
