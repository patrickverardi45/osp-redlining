"""KMZ Hardening Stage R2a — anchor-builder shadow telemetry writer.

Append-only JSONL writer that persists one row per
``(session, route_id)`` when the R2a shadow flag is enabled. Mirrors the
PT.ACT R3.g + KMZ B2b + KMZ R1 shadow patterns exactly: safe-failure,
size-trigger trim, schema-versioned rows, no input mutation.

Stage R2a is OBSERVATION ONLY. This module never mutates routing state,
never invokes the matching engine, never wires anchors into R1, never
persists segments. It transcribes the already-computed
``generate_kmz_station_anchors`` output into a JSONL row.

JSONL target: ``<uploads_dir>/kmz_stage_r2a_shadow.jsonl``
Schema version: ``kmz-stage-r2a-shadow-1``

DO NOT IMPORT FROM main.py. DO NOT TOUCH STATE.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


SCHEMA_VERSION = "kmz-stage-r2a-shadow-1"

# Telemetry file shape constants. Mirror PT.ACT R3.g + KMZ B2b + R1.
DEFAULT_MAX_ROWS = 5000
DEFAULT_TRIM_TRIGGER_BYTES = 8 * 1024 * 1024
DEFAULT_BASENAME = "kmz_stage_r2a_shadow.jsonl"

# Per-row safety caps. Keep JSONL line size bounded even for routes with
# many anchors.
_MAX_REJECTION_REASONS_KEYS = 32
_MAX_CLASSIFICATION_KEYS = 16
_MAX_WARNINGS = 16
_MAX_ANCHOR_PREVIEW = 25      # ≤25 anchors carried in the telemetry row
                              # (full anchor_records stay in the helper's
                              # response; the telemetry projection is compact)


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
    anchor_records: Optional[List[Dict[str, Any]]] = None,
    parameters_version: str = "v1",
) -> Dict[str, Any]:
    """Build one shadow-row dict in the schema ``kmz-stage-r2a-shadow-1``.

    Pure. Never raises. Never mutates inputs. Bounded sizes per field to
    keep JSONL lines manageable.

    ``diagnostics`` is the ``diagnostics`` sub-dict returned by
    ``generate_kmz_station_anchors``. Forward-compatible with additive
    diagnostic fields.
    """
    if not isinstance(diagnostics, dict):
        diagnostics = {}

    perp_stats_raw = diagnostics.get("perp_distance_m_stats") or {}
    if not isinstance(perp_stats_raw, dict):
        perp_stats_raw = {}
    perp_stats = {
        "min": _round6(perp_stats_raw.get("min")),
        "median": _round6(perp_stats_raw.get("median")),
        "max": _round6(perp_stats_raw.get("max")),
    }

    raw_rejection_reasons = diagnostics.get("rejection_reasons") or {}
    rejection_reasons: Dict[str, int] = {}
    if isinstance(raw_rejection_reasons, dict):
        for k, v in list(raw_rejection_reasons.items())[:_MAX_REJECTION_REASONS_KEYS]:
            rejection_reasons[_trunc(k, 64) or "unknown"] = _safe_int(v)

    raw_class_tally = diagnostics.get("classification_tally") or {}
    classification_tally: Dict[str, int] = {}
    if isinstance(raw_class_tally, dict):
        for k, v in list(raw_class_tally.items())[:_MAX_CLASSIFICATION_KEYS]:
            classification_tally[_trunc(k, 32) or "unknown"] = _safe_int(v)

    raw_tally = diagnostics.get("confidence_tally") or {}
    confidence_tally: Dict[str, int] = {"high": 0, "medium": 0, "low": 0}
    if isinstance(raw_tally, dict):
        for k in confidence_tally.keys():
            confidence_tally[k] = _safe_int(raw_tally.get(k))

    raw_warnings = diagnostics.get("warnings") or []
    warnings: List[str] = []
    if isinstance(raw_warnings, (list, tuple)):
        for w in raw_warnings[:_MAX_WARNINGS]:
            tw = _trunc(w, 200)
            if tw:
                warnings.append(tw)

    request_meta_compact: Dict[str, Any] = {}
    if isinstance(request_meta, dict):
        for k in ("operator_id", "operator_email", "source_file", "group_id", "tenant_id", "ts"):
            v = request_meta.get(k)
            if v is not None:
                request_meta_compact[k] = _trunc(v, 200)

    # Bounded anchor preview — compact projection only, no internal-only
    # fields. Useful for operator review without bloating the JSONL line.
    anchor_preview: List[Dict[str, Any]] = []
    if isinstance(anchor_records, (list, tuple)):
        for rec in list(anchor_records)[:_MAX_ANCHOR_PREVIEW]:
            if not isinstance(rec, dict):
                continue
            anchor_preview.append({
                "station_ft": _round6(rec.get("station_ft")),
                "lon": _round6(rec.get("lon")),
                "lat": _round6(rec.get("lat")),
                "perp_distance_m": _round6(rec.get("perp_distance_m")),
                "classification": _trunc(rec.get("classification"), 32),
                "anchor_confidence": _trunc(rec.get("anchor_confidence"), 16),
            })

    row: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "decided_at": datetime.now(timezone.utc).isoformat(),
        "emit_id": uuid.uuid4().hex,
        "session_id": _trunc(session_id, 200),
        "plan_id": _trunc(plan_id, 200),
        "route_id": _trunc(route_id, 200) or "",
        "request_meta": request_meta_compact,
        "input_feature_count": _safe_int(diagnostics.get("input_feature_count")),
        "candidate_count_pre_proximity_filter": _safe_int(
            diagnostics.get("candidate_count_pre_proximity_filter")
        ),
        "candidate_count_post_proximity_filter": _safe_int(
            diagnostics.get("candidate_count_post_proximity_filter")
        ),
        "candidate_count_post_dedupe": _safe_int(
            diagnostics.get("candidate_count_post_dedupe")
        ),
        "anchor_count": _safe_int(diagnostics.get("anchor_count")),
        "anchor_span_ft": _round6(diagnostics.get("anchor_span_ft")),
        "perp_distance_m_stats": perp_stats,
        "classification_tally": classification_tally,
        "confidence_tally": confidence_tally,
        "rejection_reasons": rejection_reasons,
        "route_confidence": _trunc(diagnostics.get("route_confidence"), 50) or "abstain",
        "polyline_total_length_ft": _round6(diagnostics.get("polyline_total_length_ft")),
        "polyline_vertex_count": _safe_int(diagnostics.get("polyline_vertex_count")),
        "warnings": warnings,
        "anchor_preview": anchor_preview,
        "parameters_version": parameters_version,
    }
    return row


def append_shadow_row(
    row: Dict[str, Any],
    *,
    target_path: Optional[Path] = None,
    max_rows: int = DEFAULT_MAX_ROWS,
    trim_trigger_bytes: int = DEFAULT_TRIM_TRIGGER_BYTES,
) -> bool:
    """Append a row to the ``kmz_stage_r2a_shadow.jsonl`` file. Returns True
    on success, False on any failure. Never raises.

    Caller decides whether to write (the shadow flag check happens upstream;
    this function does not know about the flag — it is purely a write
    primitive).

    Size-trigger trim: after append, if the file exceeds
    ``trim_trigger_bytes``, perform a single read+rewrite to keep only the
    most recent ``max_rows`` entries. Mirrors PT.ACT R3.g + KMZ B2b + R1.
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
