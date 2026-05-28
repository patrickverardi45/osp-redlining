"""KMZ Matching Trust Slice C1 — operator override persistence + audit.

Pure helpers for validating, building, and persisting operator overrides
of engine route picks. Slice C1 is RECORD-ONLY: this module produces the
override record + audit event but does NOT apply the override to matching.
The apply seam is reserved for Slice C2 and is explicitly NOT implemented
here.

Public surface:
  - validate_override_payload(payload, pipeline_diag, route_catalog) -> dict
  - build_override_record(payload, *, tenant_id, session_id, operator_email,
                          supersedes_emit_id=None) -> MatchOverride
  - snapshot_engine_selection(pipeline_diag, group_id) -> dict
  - build_audit_event(event, override, *, supersedes_emit_id=None) -> dict
  - append_audit_event(event_row, target_path) -> bool

Schemas:
  - match-override-1               (the MatchOverride record stored in STATE)
  - match-override-list-1          (GET response wrapping the active+orphan lists)
  - match-override-audit-1         (one JSONL row per write/clear/supersede)

DO NOT IMPORT FROM main.py. DO NOT TOUCH STATE.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


RECORD_SCHEMA_VERSION = "match-override-1"
LIST_SCHEMA_VERSION = "match-override-list-1"
AUDIT_SCHEMA_VERSION = "match-override-audit-1"

# Trim policy — mirror PT.ACT R3.g.
DEFAULT_AUDIT_MAX_ROWS = 5000
DEFAULT_AUDIT_TRIM_TRIGGER_BYTES = 8 * 1024 * 1024

_ALLOWED_EVENTS = frozenset({"create", "supersede", "clear", "no_op_idempotent"})

# Override status values.
STATUS_ACTIVE = "active"
STATUS_SUPERSEDED = "superseded"
STATUS_CLEARED = "cleared"
STATUS_ORPHANED = "orphaned"


# ── Validation ────────────────────────────────────────────────────────────


class OverrideValidationError(ValueError):
    """Raised by validate_override_payload on invalid input. Carries an
    HTTP status hint via .status_code (400 or 403)."""

    def __init__(self, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return str(value)
    except Exception:
        return ""


def _group_ids_in_diag(pipeline_diag: Optional[Sequence[Dict[str, Any]]]) -> set:
    out: set = set()
    if not isinstance(pipeline_diag, (list, tuple)):
        return out
    for entry in pipeline_diag:
        if not isinstance(entry, dict):
            continue
        gid = _safe_str(entry.get("group_id"))
        if gid:
            out.add(gid)
    return out


def _route_ids_in_catalog(route_catalog: Optional[Sequence[Dict[str, Any]]]) -> set:
    out: set = set()
    if not isinstance(route_catalog, (list, tuple)):
        return out
    for entry in route_catalog:
        if not isinstance(entry, dict):
            continue
        rid = _safe_str(entry.get("route_id"))
        if rid:
            out.add(rid)
    return out


def validate_override_payload(
    payload: Optional[Dict[str, Any]],
    pipeline_diag: Optional[Sequence[Dict[str, Any]]],
    route_catalog: Optional[Sequence[Dict[str, Any]]],
) -> Dict[str, Any]:
    """Validate the operator's override POST body.

    Raises OverrideValidationError(status_code=400) on missing/invalid fields.
    Returns a normalized payload dict on success: {group_id, override_route_id, reason}.

    NOTE: caller is responsible for the closeout-lock check before invoking.
    """
    if not isinstance(payload, dict):
        raise OverrideValidationError("payload must be a JSON object")

    group_id = _safe_str(payload.get("group_id")).strip()
    if not group_id:
        raise OverrideValidationError("group_id required")

    reason = _safe_str(payload.get("reason")).strip()
    if not reason:
        raise OverrideValidationError("reason required")

    # override_route_id MAY be None (force-abstain) or a non-empty string.
    raw_route = payload.get("override_route_id")
    if raw_route is None:
        override_route_id: Optional[str] = None
    else:
        rid = _safe_str(raw_route).strip()
        if not rid:
            # Treat empty string the same as None (force-abstain).
            override_route_id = None
        else:
            override_route_id = rid

    diag_groups = _group_ids_in_diag(pipeline_diag)
    if group_id not in diag_groups:
        raise OverrideValidationError(
            f"group_id '{group_id}' not in current pipeline_diag"
        )

    if override_route_id is not None:
        catalog_ids = _route_ids_in_catalog(route_catalog)
        if override_route_id not in catalog_ids:
            raise OverrideValidationError(
                f"override_route_id '{override_route_id}' not in route_catalog"
            )

    return {
        "group_id": group_id,
        "override_route_id": override_route_id,
        "reason": reason,
    }


# ── Record builder ────────────────────────────────────────────────────────


def build_override_record(
    payload: Dict[str, Any],
    *,
    tenant_id: Optional[str],
    session_id: str,
    operator_email: Optional[str],
    supersedes_emit_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a MatchOverride record from a validated payload. Pure builder."""
    return {
        "schema_version": RECORD_SCHEMA_VERSION,
        "group_id": _safe_str(payload.get("group_id")),
        "override_route_id": payload.get("override_route_id"),
        "reason": _safe_str(payload.get("reason")),
        "tenant_id": _safe_str(tenant_id) or None,
        "session_id": _safe_str(session_id) or None,
        "operator_email": _safe_str(operator_email) or None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "emit_id": uuid.uuid4().hex,
        "supersedes_emit_id": _safe_str(supersedes_emit_id) or None,
        "status": STATUS_ACTIVE,
    }


def is_idempotent_retry(
    existing: Optional[Dict[str, Any]],
    new_payload: Dict[str, Any],
) -> bool:
    """Return True iff an existing active override matches the new payload
    exactly (same override_route_id + same reason). Used by the POST handler
    to skip writing a duplicate record.
    """
    if not isinstance(existing, dict):
        return False
    if existing.get("status") != STATUS_ACTIVE:
        return False
    if existing.get("override_route_id") != new_payload.get("override_route_id"):
        return False
    if _safe_str(existing.get("reason")) != _safe_str(new_payload.get("reason")):
        return False
    return True


# ── Engine-selection snapshot ─────────────────────────────────────────────


def snapshot_engine_selection(
    pipeline_diag: Optional[Sequence[Dict[str, Any]]],
    group_id: str,
) -> Dict[str, Any]:
    """Extract the engine's current decision state for a group from the
    pipeline_diag. Surfaces selected_route_id + render flags + top alternates
    for forensic recording at override-write time.

    Returns {} when no matching diag entry exists. Pure.
    """
    out: Dict[str, Any] = {}
    if not isinstance(pipeline_diag, (list, tuple)):
        return out
    target = _safe_str(group_id)
    for entry in pipeline_diag:
        if not isinstance(entry, dict):
            continue
        if _safe_str(entry.get("group_id")) != target:
            continue
        top5 = entry.get("strict_top5")
        top3: List[Dict[str, Any]] = []
        if isinstance(top5, list):
            for item in top5[:3]:
                if not isinstance(item, dict):
                    continue
                top3.append({
                    "route_id": _safe_str(item.get("route_id")) or None,
                    "route_name": _safe_str(item.get("route_name")) or None,
                    "score": item.get("score"),
                    "route_length_ft": item.get("route_length_ft"),
                })
        out = {
            "source_file": _safe_str(entry.get("source_file")) or None,
            "selected_route_id": _safe_str(entry.get("selected_route_id")) or None,
            "selected_route_name": _safe_str(entry.get("selected_route_name")) or None,
            "render_allowed": entry.get("render_allowed"),
            "render_block_reasons": [
                _safe_str(r) for r in (entry.get("render_block_reasons") or [])
                if _safe_str(r)
            ],
            "stopped_at": _safe_str(entry.get("stopped_at")) or None,
            "ambiguity_resolution_status": _safe_str(
                entry.get("ambiguity_resolution_status")
            ) or None,
            "top_3_alternates": top3,
        }
        break
    return out


# ── Audit event ───────────────────────────────────────────────────────────


def build_audit_event(
    event: str,
    override: Dict[str, Any],
    *,
    supersedes_emit_id: Optional[str] = None,
    engine_selection: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build one append-only audit row. Pure builder.

    event ∈ {"create", "supersede", "clear", "no_op_idempotent"}.
    """
    if event not in _ALLOWED_EVENTS:
        event = "create"
    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "event": event,
        "decided_at": datetime.now(timezone.utc).isoformat(),
        "emit_id": _safe_str(override.get("emit_id")) or uuid.uuid4().hex,
        "tenant_id": _safe_str(override.get("tenant_id")) or None,
        "session_id": _safe_str(override.get("session_id")) or None,
        "operator_email": _safe_str(override.get("operator_email")) or None,
        "group_id": _safe_str(override.get("group_id")) or None,
        "override_route_id": override.get("override_route_id"),
        "reason": _safe_str(override.get("reason")) or None,
        "supersedes_emit_id": _safe_str(supersedes_emit_id) or None,
        "engine_selection_at_write": engine_selection or {},
    }


def append_audit_event(
    event_row: Dict[str, Any],
    *,
    target_path: Optional[Path] = None,
    max_rows: int = DEFAULT_AUDIT_MAX_ROWS,
    trim_trigger_bytes: int = DEFAULT_AUDIT_TRIM_TRIGGER_BYTES,
) -> bool:
    """Append-only JSONL writer. Mirrors PT.ACT R3.g pattern: safe-failure,
    size-trigger trim. Returns True on success, False on any failure. Never
    raises.

    Caller decides whether to write. This function is purely the I/O primitive.
    """
    if not isinstance(event_row, dict):
        return False
    if target_path is None:
        return False
    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(event_row, separators=(",", ":")) + "\n"
        with open(target_path, "a", encoding="utf-8") as fh:
            fh.write(line)
    except Exception:
        return False

    try:
        size = os.path.getsize(target_path)
    except OSError:
        return True
    if size > trim_trigger_bytes:
        try:
            with open(target_path, "r", encoding="utf-8") as fh:
                lines = fh.readlines()
            if len(lines) > max_rows:
                lines = lines[-max_rows:]
                with open(target_path, "w", encoding="utf-8") as fh:
                    fh.writelines(lines)
        except Exception:
            # Trim failure is non-fatal; the row already landed.
            pass
    return True


# ── List projection ────────────────────────────────────────────────────────


def classify_overrides_for_listing(
    overrides_state: Optional[Dict[str, Dict[str, Any]]],
    route_catalog: Optional[Sequence[Dict[str, Any]]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Split the STATE["match_overrides"] map into (active, orphaned) lists.

    An override is `orphaned` when its `override_route_id` is non-null but
    not present in the current `route_catalog` (e.g., KMZ re-uploaded with
    a different route set). Force-abstain overrides (route_id=None) are
    never orphaned.

    Pure. Never raises. Never mutates input.
    """
    active: List[Dict[str, Any]] = []
    orphaned: List[Dict[str, Any]] = []
    if not isinstance(overrides_state, dict):
        return active, orphaned
    catalog_ids = _route_ids_in_catalog(route_catalog)
    for _gid, ovr in overrides_state.items():
        if not isinstance(ovr, dict):
            continue
        status = _safe_str(ovr.get("status")) or STATUS_ACTIVE
        if status == STATUS_CLEARED:
            # Cleared overrides are not returned to the operator UI.
            continue
        # Take a shallow copy to avoid leaking mutation back into STATE.
        row = dict(ovr)
        route = ovr.get("override_route_id")
        if route is not None:
            rid = _safe_str(route)
            if rid and rid not in catalog_ids:
                row["status"] = STATUS_ORPHANED
                orphaned.append(row)
                continue
        active.append(row)
    return active, orphaned
