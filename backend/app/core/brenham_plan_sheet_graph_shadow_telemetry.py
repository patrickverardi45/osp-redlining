"""Brenham Plan Sheet Station Graph — shadow telemetry writer (Brenham only).

Append-only JSONL writer that persists one row per (session, source_file)
bore-log group when the plan-sheet-graph shadow flag is enabled. Mirrors the
PT.ACT R3.g + KMZ B2b + R1 + R2a shadow patterns exactly: safe-failure,
size-trigger trim, schema-versioned rows, no input mutation.

DIAGNOSTIC / OBSERVATION ONLY. Never mutates routing state, never invokes the
matching engine, never changes scoring / selection / rendering. Transcribes
the already-computed ``evaluate_bore_log`` evidence into a JSONL row.

JSONL target: ``<uploads_dir>/brenham_plan_sheet_graph_shadow.jsonl``
Schema version: ``brenham-plan-sheet-graph-shadow-1``

DO NOT IMPORT FROM main.py. DO NOT TOUCH STATE.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


SCHEMA_VERSION = "brenham-plan-sheet-graph-shadow-1"

DEFAULT_MAX_ROWS = 5000
DEFAULT_TRIM_TRIGGER_BYTES = 8 * 1024 * 1024
DEFAULT_BASENAME = "brenham_plan_sheet_graph_shadow.jsonl"

_MAX_REASONS = 12
_MAX_LIST = 40


def _trunc(value: Any, limit: int) -> Optional[str]:
    if value is None:
        return None
    try:
        s = str(value)
    except Exception:
        return None
    return s if len(s) <= limit else s[:limit]


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def build_row(
    *,
    session_id: Optional[str],
    source_file: Optional[str],
    group_id: Optional[str],
    selected_route_id: Optional[str],
    render_allowed: Optional[bool],
    evidence: Dict[str, Any],
) -> Dict[str, Any]:
    """Build one shadow-row dict (schema ``brenham-plan-sheet-graph-shadow-1``).

    Pure. Never raises. Never mutates inputs. ``evidence`` is the dict returned
    by ``brenham_plan_sheet_graph.evaluate_bore_log``.
    """
    if not isinstance(evidence, dict):
        evidence = {}

    reasons = evidence.get("status_reasons") or []
    if isinstance(reasons, (list, tuple)):
        reasons = [_trunc(r, 200) for r in list(reasons)[:_MAX_REASONS] if _trunc(r, 200)]
    else:
        reasons = []

    corridors = evidence.get("corridors") or []
    if isinstance(corridors, (list, tuple)):
        corridors = [list(c)[:_MAX_LIST] for c in list(corridors)[:_MAX_LIST] if isinstance(c, (list, tuple))]
    else:
        corridors = []

    sheets = evidence.get("sheets") or []
    sheets = list(sheets)[:_MAX_LIST] if isinstance(sheets, (list, tuple)) else []

    station_range = evidence.get("station_range")
    if not (isinstance(station_range, (list, tuple)) and len(station_range) == 2):
        station_range = None

    row: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "decided_at": datetime.now(timezone.utc).isoformat(),
        "emit_id": uuid.uuid4().hex,
        "session_id": _trunc(session_id, 200),
        "source_file": _trunc(source_file, 200),
        "group_id": _trunc(group_id, 200),
        "selected_route_id": _trunc(selected_route_id, 80),
        "render_allowed": bool(render_allowed) if render_allowed is not None else None,
        "prints": sheets,
        "corridors": corridors,
        "corridor_count": _safe_int(evidence.get("corridor_count")),
        "station_range": list(station_range) if station_range else None,
        "status": _trunc(evidence.get("status"), 60) or "unknown",
        "status_reasons": reasons,
    }
    return row


def append_shadow_row(
    row: Dict[str, Any],
    *,
    target_path: Optional[Path] = None,
    max_rows: int = DEFAULT_MAX_ROWS,
    trim_trigger_bytes: int = DEFAULT_TRIM_TRIGGER_BYTES,
) -> bool:
    """Append a row to the brenham_plan_sheet_graph_shadow.jsonl file. Returns
    True on success, False on any failure. Never raises. The caller decides
    whether to write (flag check is upstream); this is purely the write
    primitive. Size-trigger trim mirrors PT.ACT R3.g / R2a."""
    if not isinstance(row, dict):
        return False
    if target_path is None:
        return False
    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(row, separators=(",", ":")) + "\n"
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
            pass
    return True
