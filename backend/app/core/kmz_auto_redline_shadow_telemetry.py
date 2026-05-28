"""KMZ Hardening Stage R1 — auto-redline shadow telemetry writer.

Append-only JSONL writer that persists one row per
``(session, plan_id, route_id)`` when the R1 shadow flag is enabled.
Mirrors the PT.ACT R3.g + KMZ B2b shadow patterns exactly: safe-failure,
size-trigger trim, schema-versioned rows, no input mutation.

Stage R1 is OBSERVATION ONLY. This module never mutates routing state,
never invokes the matching engine, never persists redline segments,
never wires anything into the hero-map render path. It transcribes the
already-computed ``generate_kmz_auto_redline_segments`` output into a
JSONL row.

JSONL target: ``<uploads_dir>/kmz_stage_r1_shadow.jsonl``
Schema version: ``kmz-stage-r1-shadow-1``

DO NOT IMPORT FROM main.py. DO NOT TOUCH STATE.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


SCHEMA_VERSION = "kmz-stage-r1-shadow-1"

# Telemetry file shape constants. Mirror PT.ACT R3.g + KMZ B2b constraints.
DEFAULT_MAX_ROWS = 5000
DEFAULT_TRIM_TRIGGER_BYTES = 8 * 1024 * 1024
DEFAULT_BASENAME = "kmz_stage_r1_shadow.jsonl"

# Per-row safety caps. Keep the JSONL line size bounded even when the
# helper returns large segment counts on long routes.
_MAX_REJECTION_REASONS_KEYS = 32
_MAX_RESIDUALS_RECORDED = 64
_MAX_GENERATED_SEGMENT_PREVIEW = 0   # R1 does not emit segment bodies in
                                      # the telemetry row; preview reserved
                                      # for a later stage if needed.
_MAX_PAGE_WARNINGS = 32


def _trunc(value: Any, limit: int) -> Optional[str]:
    """Coerce value to string and truncate to limit chars. Returns None
    when value is None."""
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


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _round6(value: Any) -> float:
    try:
        return round(float(value), 6)
    except (TypeError, ValueError):
        return 0.0


def build_row(
    *,
    session_id: Optional[str],
    plan_id: Optional[str],
    route_id: str,
    request_meta: Optional[Dict[str, Any]],
    diagnostics: Dict[str, Any],
    parameters_version: str = "v1",
    projection_version: str = "v1",
) -> Dict[str, Any]:
    """Build one shadow-row dict in the schema ``kmz-stage-r1-shadow-1``.

    Pure. Never raises. Never mutates inputs. Bounded sizes per field to
    keep JSONL lines manageable.

    ``diagnostics`` is the ``diagnostics`` sub-dict returned by
    ``generate_kmz_auto_redline_segments``. The builder pulls only the
    fields it needs and ignores everything else — forward-compatible with
    additive diagnostic fields.
    """
    if not isinstance(diagnostics, dict):
        diagnostics = {}

    raw_residuals = diagnostics.get("anchor_residuals_m") or []
    if not isinstance(raw_residuals, (list, tuple)):
        raw_residuals = []
    residuals: List[float] = []
    for r in raw_residuals[:_MAX_RESIDUALS_RECORDED]:
        residuals.append(_round6(r))

    raw_rejection_reasons = diagnostics.get("rejection_reasons") or {}
    rejection_reasons: Dict[str, int] = {}
    if isinstance(raw_rejection_reasons, dict):
        for k, v in list(raw_rejection_reasons.items())[:_MAX_REJECTION_REASONS_KEYS]:
            rejection_reasons[_trunc(k, 64) or "unknown"] = _safe_int(v)

    raw_tally = diagnostics.get("confidence_tally") or {}
    confidence_tally: Dict[str, int] = {"high": 0, "medium": 0, "low": 0, "fallback": 0}
    if isinstance(raw_tally, dict):
        for k in confidence_tally.keys():
            confidence_tally[k] = _safe_int(raw_tally.get(k))

    raw_warnings = diagnostics.get("warnings") or []
    warnings: List[str] = []
    if isinstance(raw_warnings, (list, tuple)):
        for w in raw_warnings[:_MAX_PAGE_WARNINGS]:
            tw = _trunc(w, 200)
            if tw:
                warnings.append(tw)

    request_meta_compact: Dict[str, Any] = {}
    if isinstance(request_meta, dict):
        for k in ("operator_id", "operator_email", "source_file", "group_id", "tenant_id", "ts"):
            v = request_meta.get(k)
            if v is not None:
                request_meta_compact[k] = _trunc(v, 200)

    row: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "decided_at": datetime.now(timezone.utc).isoformat(),
        "emit_id": uuid.uuid4().hex,
        "session_id": _trunc(session_id, 200),
        "plan_id": _trunc(plan_id, 200),
        "route_id": _trunc(route_id, 200) or "",
        "request_meta": request_meta_compact,
        "anchor_count": _safe_int(diagnostics.get("anchor_count")),
        "anchor_span_ft": _round6(diagnostics.get("anchor_span_ft")),
        "anchor_residuals_m": residuals,
        "polyline_total_length_ft": _round6(diagnostics.get("polyline_total_length_ft")),
        "polyline_vertex_count": _safe_int(diagnostics.get("polyline_vertex_count")),
        "rows_input": _safe_int(diagnostics.get("rows_input")),
        "rows_generated": _safe_int(diagnostics.get("rows_generated")),
        "rows_rejected": _safe_int(diagnostics.get("rows_rejected")),
        "rejection_reasons": rejection_reasons,
        "confidence_tally": confidence_tally,
        "model_built": bool(diagnostics.get("model_built")),
        "model_slope_ft_per_ft": _round6(diagnostics.get("model_slope_ft_per_ft")),
        "residual_tier": _trunc(diagnostics.get("residual_tier"), 50),
        "warnings": warnings,
        "parameters_version": parameters_version,
        "projection_version": projection_version,
    }
    return row


def append_shadow_row(
    row: Dict[str, Any],
    *,
    target_path: Optional[Path] = None,
    max_rows: int = DEFAULT_MAX_ROWS,
    trim_trigger_bytes: int = DEFAULT_TRIM_TRIGGER_BYTES,
) -> bool:
    """Append a row to the ``kmz_stage_r1_shadow.jsonl`` file. Returns True
    on success, False on any failure. Never raises.

    Caller decides whether to write (the shadow flag check happens upstream;
    this function does not know about the flag — it is purely a write
    primitive).

    Size-trigger trim: after append, if the file exceeds
    ``trim_trigger_bytes``, perform a single read+rewrite to keep only the
    most recent ``max_rows`` entries. Mirrors PT.ACT R3.g + KMZ B2b.
    """
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
            # Trim failure is non-fatal; the row already landed.
            pass
    return True
