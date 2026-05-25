"""Tests for B-PERF-OPT-1-MATCH-AUDIT-GATE.

Covers:
  1. _append_match_audit_v2_entries env gate (off=no I/O, on=writes)
  2. _append_match_shadow_compare_entries env gate (off=no I/O, on=writes)
  3. Non-debug _summary_payload omits kmz_semantic_match_shadow
  4. Debug _summary_payload still includes kmz_semantic_match_shadow

The Window V2 production-state regression (302/247/31/1/20) is verified
separately by re-running scripts/collision_window_v2_replay.py.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

os.environ.setdefault("TRUELINE_JWT_SECRET", "audit-gate-test")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "audit-gate-test-auth")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

import backend.main as M


AUDIT_FLAG = "TRUELINE_MATCH_AUDIT_V2_WRITE"
SHADOW_FLAG = "TRUELINE_MATCH_SHADOW_COMPARE_WRITE"


def _clear_file(path: Path) -> None:
    if path.exists():
        path.unlink()


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
    return out


def _minimal_group_match() -> Dict[str, Any]:
    """Build a minimal but valid group_match shape so the writer
    iterates one row without choking on missing keys."""
    return {
        "group_id": "test_group_0",
        "route_id": "route_x",
        "route_name": "Test Route",
        "confidence": 0.5,
        "render_allowed": True,
        "rendered_station_point_count": 0,
        "rendered_redline_segment_count": 0,
        "selected_hypothesis": {
            "anchor_reasons": [],
        },
        "candidate_rankings": [],
        "validation": {
            "render_gate": {},
        },
    }


# ── A. _append_match_audit_v2_entries gating ─────────────────────────────────


def test_match_audit_v2_off_no_file_writes(monkeypatch) -> None:
    """Default OFF: writer no-ops; no file appears."""
    monkeypatch.delenv(AUDIT_FLAG, raising=False)
    _clear_file(M.MATCH_AUDIT_GROUPS_PATH)
    M._append_match_audit_v2_entries([_minimal_group_match()])
    assert not M.MATCH_AUDIT_GROUPS_PATH.exists()


def test_match_audit_v2_zero_no_file_writes(monkeypatch) -> None:
    """Explicit "0": same no-op as unset."""
    monkeypatch.setenv(AUDIT_FLAG, "0")
    _clear_file(M.MATCH_AUDIT_GROUPS_PATH)
    M._append_match_audit_v2_entries([_minimal_group_match()])
    assert not M.MATCH_AUDIT_GROUPS_PATH.exists()


def test_match_audit_v2_garbage_no_file_writes(monkeypatch) -> None:
    """Garbage value: strict "1" required, others no-op."""
    monkeypatch.setenv(AUDIT_FLAG, "yes")
    _clear_file(M.MATCH_AUDIT_GROUPS_PATH)
    M._append_match_audit_v2_entries([_minimal_group_match()])
    assert not M.MATCH_AUDIT_GROUPS_PATH.exists()


def test_match_audit_v2_on_writes_rows(monkeypatch) -> None:
    """With TRUELINE_MATCH_AUDIT_V2_WRITE=1: rows are written (legacy
    behavior preserved)."""
    monkeypatch.setenv(AUDIT_FLAG, "1")
    _clear_file(M.MATCH_AUDIT_GROUPS_PATH)
    M._append_match_audit_v2_entries(
        [_minimal_group_match(), _minimal_group_match()]
    )
    rows = _read_jsonl(M.MATCH_AUDIT_GROUPS_PATH)
    assert len(rows) == 2
    for r in rows:
        assert r.get("schema_version") == "match-audit-2"
        # match_pass_id is uuid-shaped
        assert isinstance(r.get("match_pass_id"), str) and len(r["match_pass_id"]) >= 36


def test_match_audit_v2_off_does_not_call_semantic_shadow(monkeypatch) -> None:
    """The most expensive cost driver — _build_semantic_match_shadow —
    must NOT be invoked when the flag is off."""
    monkeypatch.delenv(AUDIT_FLAG, raising=False)
    calls = {"count": 0}
    original = M._build_semantic_match_shadow

    def _spy() -> Any:
        calls["count"] += 1
        return original()

    monkeypatch.setattr(M, "_build_semantic_match_shadow", _spy)
    M._append_match_audit_v2_entries([_minimal_group_match()])
    assert calls["count"] == 0


# ── B. _append_match_shadow_compare_entries gating ───────────────────────────


def test_match_shadow_compare_off_no_file_writes(monkeypatch) -> None:
    monkeypatch.delenv(SHADOW_FLAG, raising=False)
    _clear_file(M.MATCH_SHADOW_COMPARE_PATH)
    M._append_match_shadow_compare_entries([_minimal_group_match()])
    assert not M.MATCH_SHADOW_COMPARE_PATH.exists()


def test_match_shadow_compare_zero_no_file_writes(monkeypatch) -> None:
    monkeypatch.setenv(SHADOW_FLAG, "0")
    _clear_file(M.MATCH_SHADOW_COMPARE_PATH)
    M._append_match_shadow_compare_entries([_minimal_group_match()])
    assert not M.MATCH_SHADOW_COMPARE_PATH.exists()


def test_match_shadow_compare_on_writes_rows(monkeypatch) -> None:
    monkeypatch.setenv(SHADOW_FLAG, "1")
    _clear_file(M.MATCH_SHADOW_COMPARE_PATH)
    M._append_match_shadow_compare_entries(
        [_minimal_group_match(), _minimal_group_match()]
    )
    rows = _read_jsonl(M.MATCH_SHADOW_COMPARE_PATH)
    assert len(rows) == 2
    for r in rows:
        assert r.get("schema_version") == "match-shadow-1"


def test_match_shadow_compare_off_does_not_call_semantic_shadow(monkeypatch) -> None:
    monkeypatch.delenv(SHADOW_FLAG, raising=False)
    calls = {"count": 0}
    original = M._build_semantic_match_shadow

    def _spy() -> Any:
        calls["count"] += 1
        return original()

    monkeypatch.setattr(M, "_build_semantic_match_shadow", _spy)
    M._append_match_shadow_compare_entries([_minimal_group_match()])
    assert calls["count"] == 0


# ── C. _summary_payload — kmz_semantic_match_shadow gating ───────────────────


def test_summary_payload_non_debug_omits_kmz_semantic_match_shadow() -> None:
    """B-PERF-OPT-1: the heavy semantic shadow compute is removed from
    the production upload-completion response."""
    M.STATE.clear()
    M.STATE.update({
        "_session_id_hint": "test_summary_non_debug",
        "committed_rows": [],
        "engineering_plans": [],
    })
    payload = M._summary_payload(include_debug=False)
    assert "kmz_semantic_match_shadow" not in payload


def test_summary_payload_debug_still_includes_kmz_semantic_match_shadow() -> None:
    """Debug payload (operator-only) preserves the field — legacy
    behavior intact for diagnostic surfaces."""
    M.STATE.clear()
    M.STATE.update({
        "_session_id_hint": "test_summary_debug",
        "committed_rows": [],
        "engineering_plans": [],
    })
    payload = M._summary_payload(include_debug=True)
    assert "kmz_semantic_match_shadow" in payload
    # When prerequisites are absent, _build_semantic_match_shadow returns
    # None — that's an expected value; the key must be present nonetheless.
    assert payload["kmz_semantic_match_shadow"] is None or isinstance(
        payload["kmz_semantic_match_shadow"], dict
    )


def test_summary_payload_non_debug_retains_kmz_semantic() -> None:
    """B-PERF-OPT-1 only removes the SHADOW compute; the regular
    kmz_semantic field must still be present (RedlineMap.tsx consumes
    it directly via onKmzSemanticChange)."""
    M.STATE.clear()
    M.STATE.update({
        "_session_id_hint": "test_kmz_semantic_present",
        "committed_rows": [],
        "engineering_plans": [],
        "kmz_semantic": {"features": [], "summary": "test"},
    })
    payload = M._summary_payload(include_debug=False)
    assert "kmz_semantic" in payload
    assert payload["kmz_semantic"] == {"features": [], "summary": "test"}


