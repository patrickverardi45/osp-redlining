"""PDF Plan Mode Step 3A — manual station-segment persistence.

Operator-entered station ranges bound to a saved PDF trace
(pdf_plan_trace_store.py).  Persistence shape: one JSON file per
(plan, page) containing a flat list of segments.  Each segment is a
start/end station-ft range plus operator-supplied label + optional
notes.  Segments are explicitly MANUAL / DRAFT until Step 3B+
introduces bore-log import.

File path:
    {ENGINEERING_PLAN_ROOT}/{session_id}/traces/
        {plan_id}_p{NNN}_segments.json

Same `traces/` directory as the parent trace JSON so all operator
data for a page lives next to each other.  Plan upload + delete
flows remain untouched.

Schema version: pdf-plan-segments-1.

Hard contracts:

* Pure helper.  No STATE, no env reads, no main-module imports.
* Tenant scoping enforced by caller (route layer must call
  ``_require_tenant_owns_session`` BEFORE invoking write methods).
* Deterministic JSON output (sort_keys + indent=2).
* Bounded inputs (sanity caps documented inline).
* No interpretation: this layer stores + retrieves the segment
  list.  Polyline-distance computation + rendering live frontend-side
  in pdfPlanMath.ts.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Final, List, Optional

from app.core.pdf_plan_trace_store import (
    PdfPlanTraceStoreError,
    format_station_ft_to_label,
    parse_station_label_to_ft,
)


SCHEMA_VERSION: Final[str] = "pdf-plan-segments-1"

_MAX_SEGMENTS: Final[int] = 200
_LABEL_MAX_LEN: Final[int] = 64
_NOTES_MAX_LEN: Final[int] = 280
_STATION_FT_MIN: Final[float] = 0.0
_STATION_FT_MAX: Final[float] = 1_000_000.0

# Step 3B — segment source tagging (additive, backward-compatible).
# Segments saved before Step 3B have no `source` field; the loader
# treats them as "manual" by default.  New writes can carry:
#   source = "manual"       (Step 3A operator-entered range)
#   source = "bore_log_row" (Step 3B generated from a structured row)
# source_metadata is an optional small key-value bag for the
# originating row's bookkeeping fields (depth, boc, crew, date).
# Strict cap on key/value sizes so the file can't bloat.
_VALID_SOURCES: Final[frozenset[str]] = frozenset({"manual", "bore_log_row"})
_DEFAULT_SOURCE: Final[str] = "manual"
_SOURCE_META_KEY_MAX: Final[int] = 32
_SOURCE_META_VALUE_MAX: Final[int] = 128
_SOURCE_META_KEY_COUNT_MAX: Final[int] = 16

_SAFE_ID_RX: Final = re.compile(r"^[a-zA-Z0-9_-]+$")


class PdfPlanSegmentStoreError(Exception):
    """Raised on validation failure or I/O error."""


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def _safe_segment(value: str, label: str) -> str:
    if not value or not _SAFE_ID_RX.match(value):
        raise PdfPlanSegmentStoreError(f"invalid {label}: {value!r}")
    return value


def segments_directory(
    engineering_plan_root: Path,
    session_id: str,
) -> Path:
    safe_session = _safe_segment(session_id, "session_id")
    return engineering_plan_root / safe_session / "traces"


def segments_file_path(
    engineering_plan_root: Path,
    session_id: str,
    plan_id: str,
    page_index: int,
) -> Path:
    safe_plan = _safe_segment(plan_id, "plan_id")
    if not isinstance(page_index, int) or isinstance(page_index, bool) or page_index < 0:
        raise PdfPlanSegmentStoreError(
            f"page_index must be non-negative int; got {page_index!r}"
        )
    return (
        segments_directory(engineering_plan_root, session_id)
        / f"{safe_plan}_p{page_index:03d}_segments.json"
    )


# ---------------------------------------------------------------------------
# Validation + normalization
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coerce_float(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise PdfPlanSegmentStoreError(f"{label} must be a number; got bool")
    if not isinstance(value, (int, float)):
        raise PdfPlanSegmentStoreError(
            f"{label} must be a number; got {type(value).__name__}"
        )
    fv = float(value)
    if fv != fv:  # NaN
        raise PdfPlanSegmentStoreError(f"{label} cannot be NaN")
    return fv


def _coerce_station_ft(value: Any, label: str) -> float:
    fv = _coerce_float(value, label)
    if fv < _STATION_FT_MIN or fv > _STATION_FT_MAX:
        raise PdfPlanSegmentStoreError(
            f"{label} out of range [{_STATION_FT_MIN}, {_STATION_FT_MAX}]: {fv}"
        )
    return fv


def _coerce_label(value: Any, fallback: str = "") -> str:
    if value is None:
        text = fallback
    else:
        text = str(value)
    text = text.strip()
    if not text:
        raise PdfPlanSegmentStoreError("label is required and cannot be empty")
    if len(text) > _LABEL_MAX_LEN:
        text = text[:_LABEL_MAX_LEN]
    return text


def _coerce_notes(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if len(text) > _NOTES_MAX_LEN:
        text = text[:_NOTES_MAX_LEN]
    return text


def _coerce_source(value: Any) -> str:
    """Validate the segment source tag.  Step 3B addition.  Unknown
    values fall back to the default ('manual') so older payloads
    + future tags do not crash the loader."""
    if value is None:
        return _DEFAULT_SOURCE
    text = str(value).strip().lower()
    if text in _VALID_SOURCES:
        return text
    return _DEFAULT_SOURCE


def _coerce_source_metadata(value: Any) -> Dict[str, str]:
    """Bound a small {key: value} bag carrying the originating row's
    bookkeeping (depth, BOC, crew, date, etc.).  Each key + value is
    coerced to a string and trimmed; the bag is capped at
    _SOURCE_META_KEY_COUNT_MAX keys to keep on-disk envelopes small.
    Step 3B addition; backward-compatible (default empty dict)."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        return {}
    out: Dict[str, str] = {}
    for k, v in value.items():
        if len(out) >= _SOURCE_META_KEY_COUNT_MAX:
            break
        if k is None:
            continue
        key = str(k).strip()
        if not key:
            continue
        if len(key) > _SOURCE_META_KEY_MAX:
            key = key[:_SOURCE_META_KEY_MAX]
        val = "" if v is None else str(v).strip()
        if len(val) > _SOURCE_META_VALUE_MAX:
            val = val[:_SOURCE_META_VALUE_MAX]
        out[key] = val
    return out


def _resolve_station_ft_and_label(
    raw_station_ft: Any,
    raw_label: Any,
    field_label: str,
) -> tuple[float, str]:
    """Resolve station_ft + label from either an explicit number or a
    parsed label string.  Symmetric on input: if station_ft is given,
    it wins; if only the label is given, parse it.
    """
    if raw_station_ft is not None:
        station_ft = _coerce_station_ft(raw_station_ft, f"{field_label}_station_ft")
        if raw_label is not None and str(raw_label).strip():
            label = str(raw_label).strip()
            if len(label) > _LABEL_MAX_LEN:
                label = label[:_LABEL_MAX_LEN]
        else:
            label = format_station_ft_to_label(station_ft)
        return station_ft, label
    # Fall back to parsing the label.
    if raw_label is None or not str(raw_label).strip():
        raise PdfPlanSegmentStoreError(
            f"either {field_label}_station_ft or {field_label}_label is required"
        )
    label = str(raw_label).strip()
    if len(label) > _LABEL_MAX_LEN:
        label = label[:_LABEL_MAX_LEN]
    try:
        station_ft = parse_station_label_to_ft(label)
    except PdfPlanTraceStoreError as e:
        raise PdfPlanSegmentStoreError(
            f"{field_label}_label could not be parsed as a station: {e}"
        ) from e
    if station_ft < _STATION_FT_MIN or station_ft > _STATION_FT_MAX:
        raise PdfPlanSegmentStoreError(
            f"{field_label}_station_ft (from label) out of range "
            f"[{_STATION_FT_MIN}, {_STATION_FT_MAX}]: {station_ft}"
        )
    return station_ft, label


def normalize_segment_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Validate + normalize a single incoming segment payload.

    Accepts either explicit ``start_station_ft`` / ``end_station_ft``
    numbers OR ``start_label`` / ``end_label`` strings (the helper
    parses the latter using the station parser shared with the trace
    store).  At least one of each pair must be present.

    Returns the canonical disk shape for a single segment record.
    Raises ``PdfPlanSegmentStoreError`` on any validation failure.
    """
    if not isinstance(payload, dict):
        raise PdfPlanSegmentStoreError(
            f"payload must be an object; got {type(payload).__name__}"
        )

    label = _coerce_label(payload.get("label"))
    notes = _coerce_notes(payload.get("notes"))

    start_ft, start_label = _resolve_station_ft_and_label(
        payload.get("start_station_ft"),
        payload.get("start_label"),
        "start",
    )
    end_ft, end_label = _resolve_station_ft_and_label(
        payload.get("end_station_ft"),
        payload.get("end_label"),
        "end",
    )

    seg_id_raw = payload.get("segment_id")
    if isinstance(seg_id_raw, str) and _SAFE_ID_RX.match(seg_id_raw):
        segment_id = seg_id_raw
    else:
        segment_id = uuid.uuid4().hex[:24]

    now = _now_iso()
    created_at_raw = payload.get("created_at")
    if isinstance(created_at_raw, str) and created_at_raw:
        created_at = created_at_raw
    else:
        created_at = now

    # Step 3B — preserve any existing source / source_metadata on re-
    # normalize cycles; new payloads can carry these fields explicitly.
    source = _coerce_source(payload.get("source"))
    source_metadata = _coerce_source_metadata(payload.get("source_metadata"))

    return {
        "segment_id": segment_id,
        "label": label,
        "start_station_ft": start_ft,
        "end_station_ft": end_ft,
        "start_label": start_label,
        "end_label": end_label,
        "notes": notes,
        "source": source,
        "source_metadata": source_metadata,
        "created_at": created_at,
        "updated_at": now,
    }


def _build_envelope(
    *,
    plan_id: str,
    session_id: str,
    page_index: int,
    trace_id: Optional[str],
    segments: List[Dict[str, Any]],
    created_at: str,
) -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "plan_id": plan_id,
        "session_id": session_id,
        "page_index": int(page_index),
        "trace_id": trace_id,
        "segments": segments,
        "created_at": created_at,
        "updated_at": _now_iso(),
    }


# ---------------------------------------------------------------------------
# Disk I/O
# ---------------------------------------------------------------------------

def load_segments(
    engineering_plan_root: Path,
    session_id: str,
    plan_id: str,
    page_index: int,
) -> Dict[str, Any]:
    """Return the envelope ``{segments: [...]}`` for one (plan, page).

    Returns an empty envelope (with empty ``segments`` list) when no
    file exists yet so callers can treat "no segments" as a valid
    state without 404-handling logic.
    """
    path = segments_file_path(engineering_plan_root, session_id, plan_id, page_index)
    if not path.is_file():
        return _build_envelope(
            plan_id=plan_id,
            session_id=session_id,
            page_index=page_index,
            trace_id=None,
            segments=[],
            created_at=_now_iso(),
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise PdfPlanSegmentStoreError(
            f"failed to read segments file: {type(e).__name__}: {e}"
        ) from e
    if not isinstance(data, dict):
        raise PdfPlanSegmentStoreError(
            f"segments file content is not an object: {path}"
        )
    if data.get("schema_version") != SCHEMA_VERSION:
        # Unknown / older schema — surface as empty envelope rather than
        # crash; a future migration step can read the raw file directly.
        return _build_envelope(
            plan_id=plan_id,
            session_id=session_id,
            page_index=page_index,
            trace_id=None,
            segments=[],
            created_at=_now_iso(),
        )
    return data


def add_segment(
    engineering_plan_root: Path,
    session_id: str,
    plan_id: str,
    page_index: int,
    payload: Dict[str, Any],
    *,
    trace_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Append one new segment to the (plan, page) envelope.

    Returns the full updated envelope (so the caller can return it
    to the client in one shot).  Raises if the payload is invalid or
    the segment cap is exceeded.
    """
    envelope = load_segments(engineering_plan_root, session_id, plan_id, page_index)

    segments = list(envelope.get("segments") or [])
    if len(segments) >= _MAX_SEGMENTS:
        raise PdfPlanSegmentStoreError(
            f"segments list exceeds cap of {_MAX_SEGMENTS}; cannot add more"
        )

    new_segment = normalize_segment_payload(payload)
    # Reject exact duplicate (same start/end_ft + label) so accidental
    # double-clicks don't create silent clones.
    for existing in segments:
        if (
            existing.get("label") == new_segment["label"]
            and float(existing.get("start_station_ft") or 0)
            == new_segment["start_station_ft"]
            and float(existing.get("end_station_ft") or 0)
            == new_segment["end_station_ft"]
        ):
            raise PdfPlanSegmentStoreError(
                "a segment with the same label + start + end already exists"
            )

    segments.append(new_segment)

    created_at = envelope.get("created_at") or _now_iso()
    new_envelope = _build_envelope(
        plan_id=plan_id,
        session_id=session_id,
        page_index=page_index,
        trace_id=trace_id or envelope.get("trace_id"),
        segments=segments,
        created_at=created_at,
    )
    _persist_envelope(engineering_plan_root, session_id, plan_id, page_index, new_envelope)
    return new_envelope


def delete_segment(
    engineering_plan_root: Path,
    session_id: str,
    plan_id: str,
    page_index: int,
    segment_id: str,
) -> tuple[bool, Dict[str, Any]]:
    """Remove one segment by id from the (plan, page) envelope.

    Returns (removed, envelope).  ``removed`` is True iff a matching
    segment was found + deleted.  If the resulting list is empty the
    on-disk file is removed entirely to avoid empty-record clutter.
    """
    envelope = load_segments(engineering_plan_root, session_id, plan_id, page_index)
    segments = list(envelope.get("segments") or [])
    target_id = str(segment_id or "").strip()
    if not target_id:
        raise PdfPlanSegmentStoreError("segment_id is required")

    kept: List[Dict[str, Any]] = []
    removed = False
    for s in segments:
        if str(s.get("segment_id") or "").strip() == target_id:
            removed = True
            continue
        kept.append(s)

    if not removed:
        return False, envelope

    path = segments_file_path(engineering_plan_root, session_id, plan_id, page_index)
    if not kept:
        # Empty list → unlink the file entirely.
        if path.is_file():
            try:
                path.unlink()
            except Exception as e:
                raise PdfPlanSegmentStoreError(
                    f"failed to remove empty segments file: {type(e).__name__}: {e}"
                ) from e
        return True, _build_envelope(
            plan_id=plan_id,
            session_id=session_id,
            page_index=page_index,
            trace_id=envelope.get("trace_id"),
            segments=[],
            created_at=envelope.get("created_at") or _now_iso(),
        )

    created_at = envelope.get("created_at") or _now_iso()
    new_envelope = _build_envelope(
        plan_id=plan_id,
        session_id=session_id,
        page_index=page_index,
        trace_id=envelope.get("trace_id"),
        segments=kept,
        created_at=created_at,
    )
    _persist_envelope(engineering_plan_root, session_id, plan_id, page_index, new_envelope)
    return True, new_envelope


def _persist_envelope(
    engineering_plan_root: Path,
    session_id: str,
    plan_id: str,
    page_index: int,
    envelope: Dict[str, Any],
) -> None:
    path = segments_file_path(engineering_plan_root, session_id, plan_id, page_index)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(
        json.dumps(envelope, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    tmp_path.replace(path)
