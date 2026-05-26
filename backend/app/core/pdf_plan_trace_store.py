"""PDF Plan Mode Step 2B — operator route trace + station anchor persistence.

Operator-traced polylines (in PDF-pixel coordinates) plus station-ft
anchors attached to those traces.  One trace per (plan_id, page_index)
in this step.  Stored as a single JSON file per page under

    {ENGINEERING_PLAN_ROOT}/{session_id}/traces/{plan_id}_p{NNN}.json

Hard contracts:

* Pure helper.  No STATE, no env reads, no main-module imports, no
  network.  Accepts the engineering_plan_root path from the caller
  so it never reaches into module globals.
* Tenant scoping is enforced by the caller (route handler must call
  ``_require_tenant_owns_session(resolved_session_id, request)``
  BEFORE invoking save / delete).  This helper only knows about
  paths.
* Deterministic JSON output.  ``json.dumps(..., indent=2,
  sort_keys=True)`` so a re-save with the same input produces
  byte-identical output.
* Bounded inputs to prevent operator misuse / accidental flood:
    - max 500 points per trace
    - max 50 station anchors per trace
    - per-coordinate float bounds: [0.0, 50000.0]
    - per-anchor station_ft bounds: [0.0, 1_000_000.0]
    - label string trimmed + capped at 32 chars
* No business interpretation: this layer stores + retrieves the
  geometry.  Computing redline segments from bore logs against the
  trace is Step 3, not Step 2B.
* Schema version: pdf-plan-trace-1.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Final, List, Optional, Tuple


SCHEMA_VERSION: Final[str] = "pdf-plan-trace-1"

_MAX_POINTS: Final[int] = 500
_MAX_ANCHORS: Final[int] = 50
_COORD_MIN: Final[float] = 0.0
_COORD_MAX: Final[float] = 50000.0
_STATION_FT_MIN: Final[float] = 0.0
_STATION_FT_MAX: Final[float] = 1_000_000.0
_LABEL_MAX_LEN: Final[int] = 32


class PdfPlanTraceStoreError(Exception):
    """Raised for invalid payloads, sanity-cap violations, or I/O errors."""


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

_PAGE_INDEX_RX: Final = re.compile(r"^[0-9]+$")
_SAFE_ID_RX: Final = re.compile(r"^[a-zA-Z0-9_-]+$")


def _safe_segment(value: str, label: str) -> str:
    """Reject any segment that isn't pure alnum / underscore / hyphen.

    Defense in depth — the route layer already filters the path params,
    but this helper must refuse to walk outside its own subtree under
    any conditions.
    """
    if not value or not _SAFE_ID_RX.match(value):
        raise PdfPlanTraceStoreError(
            f"invalid {label}: {value!r}"
        )
    return value


def trace_directory(
    engineering_plan_root: Path,
    session_id: str,
) -> Path:
    """Return the on-disk directory for a session's trace files."""
    safe_session = _safe_segment(session_id, "session_id")
    return engineering_plan_root / safe_session / "traces"


def trace_file_path(
    engineering_plan_root: Path,
    session_id: str,
    plan_id: str,
    page_index: int,
) -> Path:
    """Return the canonical on-disk path for one (plan, page) trace."""
    safe_plan = _safe_segment(plan_id, "plan_id")
    if not isinstance(page_index, int) or isinstance(page_index, bool) or page_index < 0:
        raise PdfPlanTraceStoreError(
            f"page_index must be non-negative int; got {page_index!r}"
        )
    return (
        trace_directory(engineering_plan_root, session_id)
        / f"{safe_plan}_p{page_index:03d}.json"
    )


# ---------------------------------------------------------------------------
# Validation + normalization
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coerce_float(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise PdfPlanTraceStoreError(f"{label} must be a number; got bool")
    if not isinstance(value, (int, float)):
        raise PdfPlanTraceStoreError(f"{label} must be a number; got {type(value).__name__}")
    fv = float(value)
    if fv != fv:  # NaN check
        raise PdfPlanTraceStoreError(f"{label} cannot be NaN")
    return fv


def _coerce_point(point: Any, label: str) -> Tuple[float, float]:
    if not isinstance(point, (list, tuple)) or len(point) != 2:
        raise PdfPlanTraceStoreError(
            f"{label} must be a [x, y] pair; got {point!r}"
        )
    x = _coerce_float(point[0], f"{label}.x")
    y = _coerce_float(point[1], f"{label}.y")
    if x < _COORD_MIN or x > _COORD_MAX:
        raise PdfPlanTraceStoreError(
            f"{label}.x out of range [{_COORD_MIN}, {_COORD_MAX}]: {x}"
        )
    if y < _COORD_MIN or y > _COORD_MAX:
        raise PdfPlanTraceStoreError(
            f"{label}.y out of range [{_COORD_MIN}, {_COORD_MAX}]: {y}"
        )
    return (x, y)


def _coerce_page_size(value: Any) -> Tuple[float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise PdfPlanTraceStoreError(
            f"page_size_px must be a [W, H] pair; got {value!r}"
        )
    w = _coerce_float(value[0], "page_size_px.W")
    h = _coerce_float(value[1], "page_size_px.H")
    if w <= 0 or w > _COORD_MAX:
        raise PdfPlanTraceStoreError(f"page_size_px.W out of range: {w}")
    if h <= 0 or h > _COORD_MAX:
        raise PdfPlanTraceStoreError(f"page_size_px.H out of range: {h}")
    return (w, h)


def _coerce_dpi(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PdfPlanTraceStoreError(f"page_dpi must be a number; got {value!r}")
    iv = int(value)
    if iv < 48 or iv > 600:
        raise PdfPlanTraceStoreError(f"page_dpi out of range [48, 600]: {iv}")
    return iv


# Station label parsing — accepts "11+60", "STA 11+60", "1160", "11+60.5"
# Used server-side as defense in depth; the frontend also pre-normalizes.
_STATION_TOKEN_RX: Final = re.compile(
    r"^\s*(?:STA\s+)?(\d{1,5})\s*\+\s*(\d{1,3}(?:\.\d+)?)\s*$",
    re.IGNORECASE,
)


def parse_station_label_to_ft(label: str) -> float:
    """Parse a station label like "11+60" to a feet value.

    Accepts:
      "11+60"     -> 1160.0
      "STA 11+60" -> 1160.0
      "11+60.5"   -> 1160.5
      "1160"      -> 1160.0  (raw feet)

    Raises PdfPlanTraceStoreError on unparseable input.
    """
    if not isinstance(label, str):
        raise PdfPlanTraceStoreError(f"station label must be str; got {type(label).__name__}")
    stripped = label.strip()
    if not stripped:
        raise PdfPlanTraceStoreError("station label is empty")
    m = _STATION_TOKEN_RX.match(stripped)
    if m:
        hundreds = int(m.group(1))
        fraction = float(m.group(2))
        return float(hundreds) * 100.0 + fraction
    # Raw feet fallback
    try:
        return float(stripped)
    except ValueError:
        raise PdfPlanTraceStoreError(
            f"station label could not be parsed: {label!r}"
        ) from None


def format_station_ft_to_label(ft: float) -> str:
    """Inverse of parse_station_label_to_ft for display.

    1160.0 -> "11+60"
    1160.5 -> "11+60.5"
    """
    if ft < 0:
        return "0+00"
    hundreds = int(ft // 100)
    remainder = ft - (hundreds * 100)
    if abs(remainder - round(remainder)) < 1e-9:
        return f"{hundreds}+{int(round(remainder)):02d}"
    return f"{hundreds}+{remainder:05.2f}"


def _coerce_anchor(anchor: Any, idx: int) -> Dict[str, Any]:
    if not isinstance(anchor, dict):
        raise PdfPlanTraceStoreError(
            f"anchors[{idx}] must be an object; got {type(anchor).__name__}"
        )
    raw_label = anchor.get("label")
    if raw_label is None:
        raw_label = anchor.get("station_label")
    label_str = "" if raw_label is None else str(raw_label).strip()
    if not label_str:
        raise PdfPlanTraceStoreError(f"anchors[{idx}].label is required")
    if len(label_str) > _LABEL_MAX_LEN:
        label_str = label_str[:_LABEL_MAX_LEN]

    raw_station_ft = anchor.get("station_ft")
    if raw_station_ft is None:
        # Derive from label
        station_ft = parse_station_label_to_ft(label_str)
    else:
        station_ft = _coerce_float(raw_station_ft, f"anchors[{idx}].station_ft")
    if station_ft < _STATION_FT_MIN or station_ft > _STATION_FT_MAX:
        raise PdfPlanTraceStoreError(
            f"anchors[{idx}].station_ft out of range "
            f"[{_STATION_FT_MIN}, {_STATION_FT_MAX}]: {station_ft}"
        )

    point = _coerce_point(anchor.get("point"), f"anchors[{idx}].point")

    anchor_id_raw = anchor.get("anchor_id")
    if isinstance(anchor_id_raw, str) and _SAFE_ID_RX.match(anchor_id_raw):
        anchor_id = anchor_id_raw
    else:
        anchor_id = uuid.uuid4().hex[:24]

    created_at_raw = anchor.get("created_at")
    if isinstance(created_at_raw, str) and created_at_raw:
        created_at = created_at_raw
    else:
        created_at = _now_iso()

    return {
        "anchor_id": anchor_id,
        "station_ft": station_ft,
        "label": label_str,
        "point": [point[0], point[1]],
        "created_at": created_at,
    }


def _coerce_anchors(value: Any) -> List[Dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise PdfPlanTraceStoreError(
            f"anchors must be a list; got {type(value).__name__}"
        )
    if len(value) > _MAX_ANCHORS:
        raise PdfPlanTraceStoreError(
            f"anchors list exceeds cap of {_MAX_ANCHORS}; got {len(value)}"
        )
    return [_coerce_anchor(a, i) for i, a in enumerate(value)]


def _coerce_points(value: Any) -> List[List[float]]:
    if not isinstance(value, list):
        raise PdfPlanTraceStoreError(
            f"points must be a list; got {type(value).__name__}"
        )
    if len(value) < 2:
        raise PdfPlanTraceStoreError(
            f"points must contain at least 2 vertices; got {len(value)}"
        )
    if len(value) > _MAX_POINTS:
        raise PdfPlanTraceStoreError(
            f"points list exceeds cap of {_MAX_POINTS}; got {len(value)}"
        )
    out: List[List[float]] = []
    for i, p in enumerate(value):
        x, y = _coerce_point(p, f"points[{i}]")
        out.append([x, y])
    return out


def _generate_trace_id(plan_id: str, session_id: str, page_index: int) -> str:
    """Deterministic trace id derived from (plan, session, page).

    Keeping the trace id stable across save cycles for the same page
    means downstream Step 3 work can key off it without needing extra
    rebinding logic.
    """
    h = hashlib.sha256(
        f"{plan_id}|{session_id}|{page_index}".encode("utf-8")
    ).hexdigest()
    return h[:24]


def normalize_trace_payload(
    *,
    plan_id: str,
    session_id: str,
    page_index: int,
    payload: Dict[str, Any],
    preserve_created_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Validate + normalize an incoming trace payload.

    The output is the canonical disk shape (schema pdf-plan-trace-1).
    Any incoming field not in the schema is dropped.

    Raises PdfPlanTraceStoreError on any validation failure.
    """
    if not isinstance(payload, dict):
        raise PdfPlanTraceStoreError(
            f"payload must be an object; got {type(payload).__name__}"
        )

    points = _coerce_points(payload.get("points"))
    anchors = _coerce_anchors(payload.get("anchors"))
    page_size_px = _coerce_page_size(payload.get("page_size_px"))
    page_dpi = _coerce_dpi(payload.get("page_dpi") if payload.get("page_dpi") is not None else 96)

    now = _now_iso()
    created_at = preserve_created_at if preserve_created_at else now

    return {
        "schema_version": SCHEMA_VERSION,
        "trace_id": _generate_trace_id(plan_id, session_id, page_index),
        "plan_id": plan_id,
        "session_id": session_id,
        "page_index": int(page_index),
        "page_dpi": page_dpi,
        "page_size_px": [page_size_px[0], page_size_px[1]],
        "points": points,
        "anchors": anchors,
        "created_at": created_at,
        "updated_at": now,
    }


# ---------------------------------------------------------------------------
# Disk I/O
# ---------------------------------------------------------------------------

def load_trace(
    engineering_plan_root: Path,
    session_id: str,
    plan_id: str,
    page_index: int,
) -> Optional[Dict[str, Any]]:
    """Read and return the stored trace for one (plan, page), or None."""
    path = trace_file_path(engineering_plan_root, session_id, plan_id, page_index)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise PdfPlanTraceStoreError(
            f"failed to read trace file: {type(e).__name__}: {e}"
        ) from e
    if not isinstance(data, dict):
        raise PdfPlanTraceStoreError(
            f"trace file content is not an object: {path}"
        )
    if data.get("schema_version") != SCHEMA_VERSION:
        # Unknown / older schema — surface as None so caller treats it as
        # absent rather than crashing.  A future migration step can read
        # the raw file directly.
        return None
    return data


def save_trace(
    engineering_plan_root: Path,
    session_id: str,
    plan_id: str,
    page_index: int,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    """Validate, normalize, and persist a trace for one (plan, page).

    Preserves ``created_at`` from any existing trace for this page so
    edit cycles do not lose first-trace timestamps.  Returns the
    canonical stored trace.
    """
    existing = None
    try:
        existing = load_trace(engineering_plan_root, session_id, plan_id, page_index)
    except PdfPlanTraceStoreError:
        # Corrupt existing file: ignore, overwrite.
        existing = None
    preserve_created_at = None
    if isinstance(existing, dict):
        existing_created = existing.get("created_at")
        if isinstance(existing_created, str) and existing_created:
            preserve_created_at = existing_created

    normalized = normalize_trace_payload(
        plan_id=plan_id,
        session_id=session_id,
        page_index=page_index,
        payload=payload,
        preserve_created_at=preserve_created_at,
    )

    path = trace_file_path(engineering_plan_root, session_id, plan_id, page_index)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(
        json.dumps(normalized, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    tmp_path.replace(path)
    return normalized


def delete_trace(
    engineering_plan_root: Path,
    session_id: str,
    plan_id: str,
    page_index: int,
) -> bool:
    """Delete the trace for one (plan, page).  Returns True if a file
    was removed, False if no trace was present."""
    path = trace_file_path(engineering_plan_root, session_id, plan_id, page_index)
    if not path.is_file():
        return False
    try:
        path.unlink()
        return True
    except Exception as e:
        raise PdfPlanTraceStoreError(
            f"failed to delete trace file: {type(e).__name__}: {e}"
        ) from e
