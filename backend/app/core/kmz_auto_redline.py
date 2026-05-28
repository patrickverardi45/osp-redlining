"""KMZ Hardening Stage R1 — auto-redline projection helper.

Pure helper that closes the KMZ -> bore-log -> redline loop. Given a route
polyline in WGS84 (lon, lat), a set of station anchors that pin known
station_ft values to lon/lat coordinates on or near the route, and a list
of bore-log rows with start/end station labels, this module deterministically
projects each bore-log station range onto the route polyline and emits a
``KmzRedlineSegmentSpec`` with WGS84 polyline geometry.

This is the KMZ-side analog of PDF E3 + E3.0.5. PDF E3 projects onto
PDF-pixel polylines for operator review; R1 projects onto geographic
polylines for hero-map drawing (in a later R3 stage).

**v1 POLICY: SUGGESTION-GRADE OUTPUT ONLY.**

R1 computes specs only. Persistence is reserved for R4 and requires
explicit re-authorization. Hero-map render integration is reserved for
R3. R5 is auto-confirm and also requires re-authorization.

Hard contracts (mirror PDF E3 + KMZ B2b doctrine):

* Pure helper. No STATE. No env reads. No main-module imports. No I/O.
* No PyMuPDF. No KMZ parsing. Operates on the request payload only.
* No AI/LLM. Station validation = regex. Projection = geodesic math
  (haversine + per-segment equirectangular tangent for perpendicular
  projection; identical to ``coverage_sanity._route_offset_for_point``).
* Deterministic: same inputs -> byte-identical output (including
  ``segment_id`` hash).
* Bounded: ``_MAX_GENERATED_SEGMENTS = 5_000``,
  ``_MAX_REJECTED_ROWS = 5_000``, ``_MAX_POLYLINE_POINTS_OUT = 2_000``.
* Abstain-when-uncertain: per-row failures land in ``rejected_rows[]``;
  per-route fallbacks emit a flagged ``lonlat_fallback`` geometry with
  ``confidence="fallback"`` rather than fabricated geometry.

Schema version: ``kmz-auto-redline-1``.

Authoritative design: ``wiki/sprints/kmz-r/r0-auto-redline-closure-design.md``.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Any, Dict, Final, List, Optional, Sequence, Tuple


SCHEMA_VERSION: Final[str] = "kmz-auto-redline-1"
PARAMETERS_VERSION: Final[str] = "v1"
PROJECTION_VERSION: Final[str] = "v1"

# Per-list safety caps.
_MAX_GENERATED_SEGMENTS: Final[int] = 5_000
_MAX_REJECTED_ROWS: Final[int] = 5_000
_MAX_POLYLINE_POINTS_OUT: Final[int] = 2_000

# Geometry tunables.
_MIN_ANCHOR_SPAN_FT: Final[float] = 50.0
_OUTSIDE_ENVELOPE_TOLERANCE: Final[float] = 0.20   # row station may exceed
                                                    # anchor span by <= 20%
_RESIDUAL_HIGH_M: Final[float] = 2.0
_RESIDUAL_MEDIUM_M: Final[float] = 5.0
_RESIDUAL_LOW_M: Final[float] = 15.0

# Distance constants (match coverage_sanity.py).
_EARTH_RADIUS_FT: Final[float] = 20902231.0
_FT_PER_METER: Final[float] = 3.280839895013123
_FT_PER_DEGREE_LAT: Final[float] = 364567.2

_FLOAT_DECIMALS: Final[int] = 6   # lon/lat preserve ~0.1m precision
_FT_DECIMALS: Final[int] = 3

# Station label regex matches PDF E3 ``_STATION_TOKEN_RE`` exactly so
# round-tripping a PDF-derived label through R1 emits the same canonical form.
_STATION_TOKEN_RE: Final = re.compile(
    r"^\s*(?:STA\.?\s+)?(\d{1,3})\+(\d{2}(?:\.\d+)?)\s*$",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class KmzAutoRedlineError(Exception):
    """Raised on caller-side bugs (malformed request, empty polyline).

    Per-row failures (malformed station label, end<=start, station outside
    anchor envelope, etc.) do NOT raise; they surface in ``rejected_rows[]``.
    """


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _r6(v: Any) -> float:
    try:
        return round(float(v), _FLOAT_DECIMALS)
    except (TypeError, ValueError):
        return 0.0


def _rft(v: Any) -> float:
    try:
        return round(float(v), _FT_DECIMALS)
    except (TypeError, ValueError):
        return 0.0


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return str(value)
    except Exception:
        return ""


def _parse_station_to_ft(s: Any) -> Optional[float]:
    """Convert a station label to a feet value.

    Accepts ``"11+60"``, ``"104+25.5"``, ``"STA 11+60"``, ``"STA. 11+60"``,
    and bare numerics. Returns ``None`` on unparseable input. Mirrors PDF E3.
    """
    if s is None:
        return None
    if isinstance(s, (int, float)):
        try:
            return float(s)
        except (TypeError, ValueError):
            return None
    if not isinstance(s, str):
        return None
    m = _STATION_TOKEN_RE.match(s)
    if not m:
        return None
    try:
        n = int(m.group(1))
        p = float(m.group(2))
        return float(n) * 100.0 + p
    except (TypeError, ValueError):
        return None


def _normalize_station_label(s: Any) -> str:
    if not isinstance(s, str):
        if isinstance(s, (int, float)):
            # Best-effort canonical for numeric-only input (e.g. 1160 -> "11+60").
            try:
                ft = float(s)
                whole = int(ft // 100)
                plus = ft - whole * 100.0
                return f"{whole}+{plus:05.2f}".rstrip("0").rstrip(".") if plus != int(plus) else f"{whole}+{int(plus):02d}"
            except (TypeError, ValueError):
                return ""
        return ""
    m = _STATION_TOKEN_RE.match(s)
    if not m:
        return ""
    return f"{int(m.group(1))}+{m.group(2)}"


def _coerce_lonlat_pair(pair: Any) -> Optional[Tuple[float, float]]:
    """Accept ``(lon, lat)`` or ``[lon, lat]``. Returns ``None`` on invalid
    input. Does NOT swap based on hemisphere — callers are responsible for
    supplying canonical (lon, lat) shape, mirroring the PDF E3 contract."""
    if pair is None:
        return None
    if not isinstance(pair, (list, tuple)) or len(pair) < 2:
        return None
    try:
        lon = float(pair[0])
        lat = float(pair[1])
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(lon) and math.isfinite(lat)):
        return None
    return (lon, lat)


# ---------------------------------------------------------------------------
# Geodesic primitives
# ---------------------------------------------------------------------------

def _haversine_ft(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    """Great-circle distance between two (lon, lat) points in feet. Matches
    ``coverage_sanity._haversine_ft`` exactly."""
    lon1, lat1 = math.radians(p1[0]), math.radians(p1[1])
    lon2, lat2 = math.radians(p2[0]), math.radians(p2[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * _EARTH_RADIUS_FT * math.asin(math.sqrt(max(0.0, min(1.0, a))))


def _polyline_cum_lengths_ft(polyline: Sequence[Tuple[float, float]]) -> List[float]:
    """Cumulative arc length (feet) at each vertex. ``len == len(polyline)``."""
    if not polyline:
        return []
    cum: List[float] = [0.0]
    for i in range(1, len(polyline)):
        cum.append(cum[-1] + _haversine_ft(polyline[i - 1], polyline[i]))
    return cum


def _project_point_to_polyline_ft(
    p: Tuple[float, float],
    polyline: Sequence[Tuple[float, float]],
    cum_ft: Sequence[float],
) -> Optional[Tuple[float, Tuple[float, float], float]]:
    """Return ``(distance_along_ft, projected_lonlat, perp_distance_ft)`` or
    ``None`` if the polyline cannot support a projection. Equirectangular
    tangent projection per segment — same pattern as
    ``coverage_sanity._route_offset_for_point``."""
    if len(polyline) < 2 or len(cum_ft) != len(polyline):
        return None
    px, py = p
    best: Optional[Tuple[float, Tuple[float, float], float]] = None
    cumulative_ft = 0.0
    for i in range(len(polyline) - 1):
        a = polyline[i]
        b = polyline[i + 1]
        seg_len_ft = _haversine_ft(a, b)
        if seg_len_ft <= 0.0:
            continue
        mid_lat_rad = math.radians((a[1] + b[1]) / 2.0)
        cos_lat = math.cos(mid_lat_rad)
        ax_ft = a[0] * _FT_PER_DEGREE_LAT * cos_lat
        ay_ft = a[1] * _FT_PER_DEGREE_LAT
        bx_ft = b[0] * _FT_PER_DEGREE_LAT * cos_lat
        by_ft = b[1] * _FT_PER_DEGREE_LAT
        ppx_ft = px * _FT_PER_DEGREE_LAT * cos_lat
        ppy_ft = py * _FT_PER_DEGREE_LAT
        seg_dx = bx_ft - ax_ft
        seg_dy = by_ft - ay_ft
        seg_len_sq = seg_dx * seg_dx + seg_dy * seg_dy
        if seg_len_sq <= 0.0:
            cumulative_ft += seg_len_ft
            continue
        t = ((ppx_ft - ax_ft) * seg_dx + (ppy_ft - ay_ft) * seg_dy) / seg_len_sq
        t_clamped = max(0.0, min(1.0, t))
        closest_x = ax_ft + t_clamped * seg_dx
        closest_y = ay_ft + t_clamped * seg_dy
        perp_ft = math.hypot(ppx_ft - closest_x, ppy_ft - closest_y)
        proj_lon = a[0] + t_clamped * (b[0] - a[0])
        proj_lat = a[1] + t_clamped * (b[1] - a[1])
        dist_along = cumulative_ft + t_clamped * seg_len_ft
        if best is None or perp_ft < best[2]:
            best = (dist_along, (proj_lon, proj_lat), perp_ft)
        cumulative_ft += seg_len_ft
    return best


def _point_at_polyline_distance_ft(
    distance_ft: float,
    polyline: Sequence[Tuple[float, float]],
    cum_ft: Sequence[float],
) -> Optional[Tuple[float, float]]:
    """Return the ``(lon, lat)`` at the given arc-length distance along the
    polyline. Clamps to ``[0, total_length_ft]``. Linear interpolation in
    lon/lat per segment is acceptable over typical KMZ route segments (sub-km)
    where great-circle deviation from a rhumb-line is negligible."""
    if len(polyline) < 2 or len(cum_ft) != len(polyline):
        return None
    total = cum_ft[-1]
    if total <= 0.0:
        return polyline[0]
    d = max(0.0, min(total, distance_ft))
    lo, hi = 0, len(cum_ft) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if cum_ft[mid] < d:
            lo = mid + 1
        else:
            hi = mid
    i = max(1, lo)
    a = polyline[i - 1]
    b = polyline[i]
    seg_len_ft = cum_ft[i] - cum_ft[i - 1]
    if seg_len_ft <= 1e-9:
        return a
    t = (d - cum_ft[i - 1]) / seg_len_ft
    return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))


def _polyline_subpath_ft(
    start_dist_ft: float,
    end_dist_ft: float,
    polyline: Sequence[Tuple[float, float]],
    cum_ft: Sequence[float],
    max_points_out: int = _MAX_POLYLINE_POINTS_OUT,
) -> List[Tuple[float, float]]:
    """Extract the lon/lat subpath of the polyline between two arc-length
    positions. Always begins with the projected start point and ends with
    the projected end point; intermediate polyline vertices that fall
    strictly between the two distances are inserted in order."""
    if len(polyline) < 2 or len(cum_ft) != len(polyline):
        return []
    if end_dist_ft < start_dist_ft:
        start_dist_ft, end_dist_ft = end_dist_ft, start_dist_ft
    total = cum_ft[-1]
    start_dist_ft = max(0.0, min(total, start_dist_ft))
    end_dist_ft = max(0.0, min(total, end_dist_ft))
    start_pt = _point_at_polyline_distance_ft(start_dist_ft, polyline, cum_ft)
    end_pt = _point_at_polyline_distance_ft(end_dist_ft, polyline, cum_ft)
    if start_pt is None or end_pt is None:
        return []
    out: List[Tuple[float, float]] = [start_pt]
    for i, c in enumerate(cum_ft):
        if start_dist_ft < c < end_dist_ft:
            out.append(polyline[i])
            if len(out) >= max_points_out - 1:
                break
    out.append(end_pt)
    return out


# ---------------------------------------------------------------------------
# Anchor / station-to-distance model
# ---------------------------------------------------------------------------

def _build_anchor_projections(
    station_anchors_lonlat: Sequence[Any],
    polyline: Sequence[Tuple[float, float]],
    cum_ft: Sequence[float],
) -> List[Dict[str, Any]]:
    """Project each ``(station_ft, (lon, lat))`` anchor onto the polyline.

    Skips anchors with invalid station_ft or invalid lon/lat. Returns a
    deterministic list sorted ascending by ``station_ft``.
    """
    out: List[Dict[str, Any]] = []
    for entry in station_anchors_lonlat:
        if not isinstance(entry, (list, tuple)) or len(entry) < 2:
            continue
        try:
            station_ft = float(entry[0])
        except (TypeError, ValueError):
            continue
        if not math.isfinite(station_ft):
            continue
        ap = _coerce_lonlat_pair(entry[1])
        if ap is None:
            continue
        proj = _project_point_to_polyline_ft(ap, polyline, cum_ft)
        if proj is None:
            continue
        dist_along_ft, projected_pt, perp_ft = proj
        out.append({
            "station_ft": _rft(station_ft),
            "anchor_lonlat": [_r6(ap[0]), _r6(ap[1])],
            "projected_lonlat": [_r6(projected_pt[0]), _r6(projected_pt[1])],
            "distance_along_ft": _rft(dist_along_ft),
            "perp_distance_ft": _rft(perp_ft),
            "perp_distance_m": _rft(perp_ft / _FT_PER_METER),
        })
    out.sort(key=lambda a: (a["station_ft"], a["distance_along_ft"]))
    return out


def _build_station_distance_model(
    anchor_projections: Sequence[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Fit a linear ``station_ft -> distance_along_ft`` model using the two
    anchors with the smallest and largest ``station_ft`` (longest baseline).

    Returns ``None`` when no safe positive-slope model can be built.
    """
    if len(anchor_projections) < 2:
        return None
    sorted_anchors = sorted(anchor_projections, key=lambda a: a["station_ft"])
    a_min = sorted_anchors[0]
    a_max = sorted_anchors[-1]
    span_ft = a_max["station_ft"] - a_min["station_ft"]
    if span_ft <= 0:
        return None
    span_dist_ft = a_max["distance_along_ft"] - a_min["distance_along_ft"]
    slope = span_dist_ft / span_ft
    if slope <= 0:
        return None
    intercept = a_min["distance_along_ft"] - slope * a_min["station_ft"]
    return {
        "slope": slope,
        "intercept": intercept,
        "anchor_min": a_min,
        "anchor_max": a_max,
        "span_ft": span_ft,
    }


# ---------------------------------------------------------------------------
# Segment ID
# ---------------------------------------------------------------------------

def _segment_id(route_id: str, row_id: str) -> str:
    """Deterministic hash of (route_id, row_id, projection_version). Same
    inputs always produce the same id — locks idempotent test assertions."""
    h = hashlib.sha256()
    h.update(_safe_str(route_id).encode("utf-8"))
    h.update(b"\x00")
    h.update(_safe_str(row_id).encode("utf-8"))
    h.update(b"\x00")
    h.update(PROJECTION_VERSION.encode("utf-8"))
    return "kar_" + h.hexdigest()[:16]


# ---------------------------------------------------------------------------
# Per-row geometry computation
# ---------------------------------------------------------------------------

def _proportional_fallback_subpath(
    row_index: int,
    row_count: int,
    polyline: Sequence[Tuple[float, float]],
    cum_ft: Sequence[float],
) -> List[Tuple[float, float]]:
    """Per-row proportional subpath of the polyline.

    Used only when no usable station-distance model exists (less than 2
    anchors, negative slope, or all residuals exceed the low-confidence
    cap). Each row gets an equal-length slice of the polyline so multiple
    rows do not collapse onto the same coordinates. NEVER fabricated.
    """
    total = cum_ft[-1] if cum_ft else 0.0
    if total <= 0.0 or row_count <= 0:
        return [polyline[0], polyline[-1]] if len(polyline) >= 2 else []
    slice_len = total / max(1, row_count)
    start_dist = row_index * slice_len
    end_dist = start_dist + slice_len
    return _polyline_subpath_ft(start_dist, end_dist, polyline, cum_ft)


def _compute_row_geometry(
    *,
    row_index: int,
    row_count: int,
    start_ft: float,
    end_ft: float,
    polyline: Sequence[Tuple[float, float]],
    cum_ft: Sequence[float],
    model: Optional[Dict[str, Any]],
    residual_tier: str,
    anchor_count: int,
    polyline_total_ft: float,
) -> Dict[str, Any]:
    """Project a single row's ``[start_ft, end_ft]`` onto the polyline and
    classify the resulting confidence tier.

    Returns a dict with ``geometry_type``, ``geometry_lonlat``,
    ``geometry_confidence``, ``warnings``, ``start_dist_ft``, ``end_dist_ft``.
    """
    warnings: List[str] = []
    if model is None:
        warnings.append(
            "fallback_no_model"
            if anchor_count == 0
            else "fallback_non_monotone_anchor_model"
            if anchor_count >= 2
            else "fallback_single_anchor"
        )
        subpath = _proportional_fallback_subpath(row_index, row_count, polyline, cum_ft)
        return {
            "geometry_type": "lonlat_fallback",
            "geometry_lonlat": [[_r6(x), _r6(y)] for (x, y) in subpath],
            "geometry_confidence": "fallback",
            "warnings": warnings,
            "start_dist_ft": _rft(row_index / max(1, row_count) * polyline_total_ft),
            "end_dist_ft": _rft((row_index + 1) / max(1, row_count) * polyline_total_ft),
        }

    slope = model["slope"]
    intercept = model["intercept"]
    start_dist_raw = slope * start_ft + intercept
    end_dist_raw = slope * end_ft + intercept
    start_dist = max(0.0, min(polyline_total_ft, start_dist_raw))
    end_dist = max(0.0, min(polyline_total_ft, end_dist_raw))
    if start_dist != start_dist_raw:
        warnings.append("geometry_start_clipped_to_polyline_bounds")
    if end_dist != end_dist_raw:
        warnings.append("geometry_end_clipped_to_polyline_bounds")
    if abs(end_dist - start_dist) < 1e-6:
        warnings.append("geometry_zero_length_after_clip")
        subpath = _proportional_fallback_subpath(row_index, row_count, polyline, cum_ft)
        return {
            "geometry_type": "lonlat_fallback",
            "geometry_lonlat": [[_r6(x), _r6(y)] for (x, y) in subpath],
            "geometry_confidence": "fallback",
            "warnings": warnings,
            "start_dist_ft": _rft(start_dist),
            "end_dist_ft": _rft(end_dist),
        }

    subpath = _polyline_subpath_ft(start_dist, end_dist, polyline, cum_ft)
    if len(subpath) < 2:
        warnings.append("geometry_subpath_empty")
        subpath = _proportional_fallback_subpath(row_index, row_count, polyline, cum_ft)
        return {
            "geometry_type": "lonlat_fallback",
            "geometry_lonlat": [[_r6(x), _r6(y)] for (x, y) in subpath],
            "geometry_confidence": "fallback",
            "warnings": warnings,
            "start_dist_ft": _rft(start_dist),
            "end_dist_ft": _rft(end_dist),
        }

    # Confidence tier from anchor span + residual tier + clipping.
    anchor_span_ft = model["span_ft"]
    clipped = (
        "geometry_start_clipped_to_polyline_bounds" in warnings
        or "geometry_end_clipped_to_polyline_bounds" in warnings
    )
    if anchor_span_ft < _MIN_ANCHOR_SPAN_FT:
        confidence = "low"
        warnings.append("anchor_span_below_min")
    elif residual_tier == "fallback":
        confidence = "fallback"
    elif clipped:
        confidence = "low"
    elif residual_tier == "high":
        confidence = "high"
    elif residual_tier == "medium":
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "geometry_type": "lonlat_polyline",
        "geometry_lonlat": [[_r6(x), _r6(y)] for (x, y) in subpath],
        "geometry_confidence": confidence,
        "warnings": warnings,
        "start_dist_ft": _rft(start_dist),
        "end_dist_ft": _rft(end_dist),
    }


# ---------------------------------------------------------------------------
# Per-row builders (as_built + proposed redline record)
# ---------------------------------------------------------------------------

def _build_as_built(row: Dict[str, Any]) -> Dict[str, Any]:
    """Project a bore-log row dict into the ``AsBuiltFieldsModel`` shape.

    Pure dict construction — does NOT import or invoke pydantic so the
    helper remains dependency-light. Caller can wrap with the actual model
    if persistence ever ships in R4.
    """
    return {
        "owner": _safe_str(row.get("owner")) or None,
        "conduit_size": _safe_str(row.get("conduit_size")) or None,
        "conduit_count": row.get("conduit_count") if isinstance(row.get("conduit_count"), int) else None,
        "fiber_count": row.get("fiber_count") if isinstance(row.get("fiber_count"), int) else None,
        "placement": _safe_str(row.get("placement")) or None,
        "sequential_in_ft": row.get("sequential_in_ft") if isinstance(row.get("sequential_in_ft"), (int, float)) else None,
        "sequential_out_ft": row.get("sequential_out_ft") if isinstance(row.get("sequential_out_ft"), (int, float)) else None,
        "panel_size": _safe_str(row.get("panel_size")) or None,
        "panel_assignment": _safe_str(row.get("panel_assignment")) or None,
        "pole_owner": _safe_str(row.get("pole_owner")) or None,
        "note_text": _safe_str(row.get("notes")) or _safe_str(row.get("note_text")) or None,
    }


def _build_proposed_redline_record(
    *,
    segment_id: str,
    row: Dict[str, Any],
    start_label: str,
    end_label: str,
    start_ft: float,
    end_ft: float,
    geometry_lonlat: Sequence[Tuple[float, float]],
    as_built: Dict[str, Any],
) -> Dict[str, Any]:
    """Project the helper output into the ``RedlineRecordModel`` shape with
    ``source="bore_log"``. Lon/lat coordinates ride in the ``geometry.points``
    list as ``{x: lon, y: lat}``.
    """
    notes_text = _safe_str(row.get("notes")) or _safe_str(row.get("note_text")) or ""
    record: Dict[str, Any] = {
        "record_id": segment_id,
        "sheet_number": _safe_str(row.get("print")) or _safe_str(row.get("sheet_number")) or "",
        "station_from": start_label or None,
        "station_to": end_label or None,
        "issue_type": "new_conduit",
        "note_text": notes_text,
        "geometry": {
            "geometry_type": "polyline",
            "points": [
                {"x": _r6(lon), "y": _r6(lat)} for (lon, lat) in geometry_lonlat
            ],
            "color": "red",
            "stroke_width": 3,
        },
        "affected_assets": [],
        "as_built": as_built,
        "source": "bore_log",
        "severity": "review",
        "metric_feet": _rft(end_ft - start_ft),
        "verified_by_foreman": False,
    }
    return record


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def generate_kmz_auto_redline_segments(
    request: Dict[str, Any],
) -> Dict[str, Any]:
    """Project a bore-log group's station ranges onto a KMZ route polyline.

    Mirrors the PDF E3 ``generate_auto_redline_segments`` contract for
    geographic (WGS84) input. Pure helper — no STATE, no env reads, no I/O,
    no main-module imports.

    Raises ``KmzAutoRedlineError`` only on caller-side bugs (request not a
    dict, missing route_id, empty polyline). Per-row failures are surfaced
    in ``rejected_rows[]``; per-route confidence failures emit
    ``lonlat_fallback`` segments with ``confidence="fallback"``.
    """
    # ──── Validate request shape ──────────────────────────────────────────
    if not isinstance(request, dict):
        raise KmzAutoRedlineError(
            f"request must be a dict; got {type(request).__name__}"
        )

    route_id = _safe_str(request.get("route_id")).strip()
    if not route_id:
        raise KmzAutoRedlineError("request.route_id is required")

    raw_polyline = request.get("route_polyline_lonlat")
    if not isinstance(raw_polyline, (list, tuple)):
        raise KmzAutoRedlineError(
            "request.route_polyline_lonlat must be a list of (lon, lat) pairs"
        )
    polyline_coerced: List[Tuple[float, float]] = []
    for pt in raw_polyline:
        coerced = _coerce_lonlat_pair(pt)
        if coerced is not None:
            polyline_coerced.append(coerced)
    if len(polyline_coerced) < 2:
        raise KmzAutoRedlineError(
            "request.route_polyline_lonlat must contain at least 2 valid (lon, lat) points"
        )

    raw_anchors = request.get("station_anchors_lonlat") or []
    if not isinstance(raw_anchors, (list, tuple)):
        raw_anchors = []

    raw_rows = request.get("bore_log_rows")
    if raw_rows is None:
        raw_rows = []
    if not isinstance(raw_rows, (list, tuple)):
        raise KmzAutoRedlineError(
            "request.bore_log_rows must be a list of row dicts (or absent)"
        )

    request_meta = request.get("request_meta") or {}
    if not isinstance(request_meta, dict):
        request_meta = {}

    # ──── Build geometry context ──────────────────────────────────────────
    cum_ft = _polyline_cum_lengths_ft(polyline_coerced)
    polyline_total_ft = cum_ft[-1] if cum_ft else 0.0
    anchor_projections = _build_anchor_projections(raw_anchors, polyline_coerced, cum_ft)
    model = _build_station_distance_model(anchor_projections)

    # Residual-tier classification across all anchors. None of the anchors
    # individually drive the per-segment confidence; the worst-residual
    # bound clamps the tier ceiling for the whole route.
    residuals_m = [a["perp_distance_m"] for a in anchor_projections]
    if residuals_m:
        worst_m = max(residuals_m)
        if worst_m <= _RESIDUAL_HIGH_M:
            residual_tier = "high"
        elif worst_m <= _RESIDUAL_MEDIUM_M:
            residual_tier = "medium"
        elif worst_m <= _RESIDUAL_LOW_M:
            residual_tier = "low"
        else:
            residual_tier = "fallback"
    else:
        residual_tier = "fallback"

    page_warnings: List[str] = []
    if len(anchor_projections) < 2:
        page_warnings.append("insufficient_anchors_lt_2")
    if model is None and len(anchor_projections) >= 2:
        page_warnings.append("non_monotone_anchor_model")
    if model is not None and model["span_ft"] < _MIN_ANCHOR_SPAN_FT:
        page_warnings.append("anchor_span_below_min")
    if residuals_m and max(residuals_m) > _RESIDUAL_LOW_M:
        page_warnings.append("worst_residual_exceeds_low_cap")

    # Anchor envelope (used for per-row outside-envelope rejection).
    anchor_envelope: Optional[Tuple[float, float, float]] = None  # (min, max, span)
    if anchor_projections:
        anchor_min = min(a["station_ft"] for a in anchor_projections)
        anchor_max = max(a["station_ft"] for a in anchor_projections)
        anchor_span = anchor_max - anchor_min
        if anchor_span > 0:
            anchor_envelope = (anchor_min, anchor_max, anchor_span)

    # ──── Per-row generation ──────────────────────────────────────────────
    generated: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    rows_input = len(raw_rows)
    row_count_for_fallback = max(1, rows_input)

    for idx, row in enumerate(raw_rows):
        if not isinstance(row, dict):
            rejected.append({
                "row_index": idx,
                "row_id": None,
                "reason": "row_not_a_dict",
                "rule_id": "kmz_auto_redline_v1:row_shape",
            })
            continue

        row_id = _safe_str(row.get("row_id"))
        if not row_id:
            row_id = f"row_{idx:04d}"

        start_raw = row.get("start_label")
        if start_raw is None:
            start_raw = row.get("start_station")
        end_raw = row.get("end_label")
        if end_raw is None:
            end_raw = row.get("end_station")

        start_ft = _parse_station_to_ft(start_raw)
        end_ft = _parse_station_to_ft(end_raw)
        if start_ft is None:
            rejected.append({
                "row_index": idx,
                "row_id": row_id,
                "reason": "malformed_station_label_start",
                "rule_id": "kmz_auto_redline_v1:start_station_format",
                "input_value": _safe_str(start_raw),
            })
            continue
        if end_ft is None:
            rejected.append({
                "row_index": idx,
                "row_id": row_id,
                "reason": "malformed_station_label_end",
                "rule_id": "kmz_auto_redline_v1:end_station_format",
                "input_value": _safe_str(end_raw),
            })
            continue
        if end_ft <= start_ft:
            rejected.append({
                "row_index": idx,
                "row_id": row_id,
                "reason": "end_before_start",
                "rule_id": "kmz_auto_redline_v1:end_before_start",
                "start_ft": _rft(start_ft),
                "end_ft": _rft(end_ft),
            })
            continue

        # Outside-anchor-envelope rejection. Tolerance is a percentage of the
        # anchor span; rows that exceed it on either side are rejected.
        if anchor_envelope is not None:
            anchor_min, anchor_max, anchor_span = anchor_envelope
            tolerance_ft = anchor_span * _OUTSIDE_ENVELOPE_TOLERANCE
            if (start_ft < anchor_min - tolerance_ft
                    or end_ft > anchor_max + tolerance_ft):
                rejected.append({
                    "row_index": idx,
                    "row_id": row_id,
                    "reason": "station_outside_anchor_envelope",
                    "rule_id": "kmz_auto_redline_v1:outside_anchor_envelope",
                    "start_ft": _rft(start_ft),
                    "end_ft": _rft(end_ft),
                    "anchor_min_ft": _rft(anchor_min),
                    "anchor_max_ft": _rft(anchor_max),
                    "tolerance_ft": _rft(tolerance_ft),
                })
                continue

        # Compute geometry for this row.
        geom = _compute_row_geometry(
            row_index=idx,
            row_count=row_count_for_fallback,
            start_ft=start_ft,
            end_ft=end_ft,
            polyline=polyline_coerced,
            cum_ft=cum_ft,
            model=model,
            residual_tier=residual_tier,
            anchor_count=len(anchor_projections),
            polyline_total_ft=polyline_total_ft,
        )

        start_label_norm = _normalize_station_label(start_raw)
        end_label_norm = _normalize_station_label(end_raw)
        seg_id = _segment_id(route_id, row_id)
        as_built = _build_as_built(row)
        geometry_lonlat = [tuple(p) for p in geom["geometry_lonlat"]]
        proposed = _build_proposed_redline_record(
            segment_id=seg_id,
            row=row,
            start_label=start_label_norm,
            end_label=end_label_norm,
            start_ft=start_ft,
            end_ft=end_ft,
            geometry_lonlat=geometry_lonlat,
            as_built=as_built,
        )

        generated.append({
            "segment_id": seg_id,
            "source_row_id": row_id,
            "source_row_index": idx,
            "station_from_ft": _rft(start_ft),
            "station_to_ft": _rft(end_ft),
            "station_from_label": start_label_norm,
            "station_to_label": end_label_norm,
            "geometry_type": geom["geometry_type"],
            "geometry_lonlat": geom["geometry_lonlat"],
            "geometry_confidence": geom["geometry_confidence"],
            "warnings": geom["warnings"],
            "projection": {
                "start_dist_along_ft": geom["start_dist_ft"],
                "end_dist_along_ft": geom["end_dist_ft"],
                "method": (
                    "two_anchor_linear" if model is not None and geom["geometry_type"] == "lonlat_polyline"
                    else "proportional_fallback"
                ),
            },
            "as_built": as_built,
            "proposed_redline_record": proposed,
        })

        if len(generated) >= _MAX_GENERATED_SEGMENTS:
            break

    rejected = rejected[:_MAX_REJECTED_ROWS]

    # ──── Deterministic sort (segments and rejections) ────────────────────
    generated.sort(key=lambda s: (s["station_from_ft"], s["station_to_ft"], s["source_row_index"]))
    rejected.sort(key=lambda r: r["row_index"])

    # Confidence tally + rejection reason tally.
    confidence_tally: Dict[str, int] = {"high": 0, "medium": 0, "low": 0, "fallback": 0}
    for seg in generated:
        c = seg.get("geometry_confidence")
        if isinstance(c, str) and c in confidence_tally:
            confidence_tally[c] += 1
    rejection_reasons: Dict[str, int] = {}
    for rej in rejected:
        reason = _safe_str(rej.get("reason")) or "unknown"
        rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1

    # Diagnostics — input to shadow telemetry row builder.
    diagnostics: Dict[str, Any] = {
        "anchor_count": len(anchor_projections),
        "anchor_span_ft": _rft(anchor_envelope[2]) if anchor_envelope else 0.0,
        "anchor_residuals_m": [a["perp_distance_m"] for a in anchor_projections],
        "polyline_total_length_ft": _rft(polyline_total_ft),
        "polyline_vertex_count": len(polyline_coerced),
        "rows_input": rows_input,
        "rows_generated": len(generated),
        "rows_rejected": len(rejected),
        "rejection_reasons": rejection_reasons,
        "confidence_tally": confidence_tally,
        "model_built": model is not None,
        "model_slope_ft_per_ft": _rft(model["slope"]) if model is not None else 0.0,
        "residual_tier": residual_tier,
        "warnings": page_warnings,
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "parameters_version": PARAMETERS_VERSION,
        "projection_version": PROJECTION_VERSION,
        "route_id": route_id,
        "request_meta": dict(request_meta),
        "anchor_projections": anchor_projections,
        "generated_segments": generated,
        "rejected_rows": rejected,
        "diagnostics": diagnostics,
        "parameters": {
            "min_anchor_span_ft": _MIN_ANCHOR_SPAN_FT,
            "outside_envelope_tolerance": _OUTSIDE_ENVELOPE_TOLERANCE,
            "residual_high_m": _RESIDUAL_HIGH_M,
            "residual_medium_m": _RESIDUAL_MEDIUM_M,
            "residual_low_m": _RESIDUAL_LOW_M,
            "max_generated_segments": _MAX_GENERATED_SEGMENTS,
            "max_rejected_rows": _MAX_REJECTED_ROWS,
            "max_polyline_points_out": _MAX_POLYLINE_POINTS_OUT,
        },
    }
