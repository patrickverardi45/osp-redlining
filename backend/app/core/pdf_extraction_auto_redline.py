"""PDF Extraction E3 — auto-redline segment generation.

Takes the upstream extraction stack (E1 raw + E2b routes + E2c bindings)
plus an operator-supplied request payload that carries:

  * the confirmed ``route_candidate_id`` (operator picked one of E2b's
    candidates as the actual proposed-construction route on this page)
  * a list of bore-log-style rows or station ranges (operator-bound
    field data — NOT auto-associated from a different job)

and produces deterministic auto-redline segment SPECS — `source =
"auto_extracted"` records ready to be reviewed and (in a future
ship) persisted into the existing ``pdf-plan-segments-1`` storage.

**v1 PERSISTENCE POLICY: ALWAYS DRY-RUN.**

This module computes segment specs only.  The endpoint accepts a
``dry_run`` field for forward-compatibility, but v1 ignores its
value and never mutates the segments store.  Real persistence is
explicitly deferred to E3.1 after operator validation against
real Kelly PDFs.  This protects the existing manual + bore-log row
segment flows from any auto-extraction bug.

**E3.0.5 — Geometry projection (NEW).**

Each generated segment now carries actual PDF-pixel geometry by
projecting [start_station_ft, end_station_ft] onto the confirmed
route candidate's reconstructed polyline.  Projection model:

  1. Reconstruct the route polyline by joining the route candidate's
     source paths (greedy endpoint-chain over E1 raw items).
  2. Project E2c station_anchors bound to the route onto the polyline
     by perpendicular distance.  Each anchor pairs (station_ft,
     distance_along_polyline_pt).
  3. Build a linear station→distance model from the two anchors with
     the smallest and largest station_ft (longest baseline; most
     stable interpolation).
  4. Map each segment's [start_ft, end_ft] → distances → polyline
     subpath points.

Safety policy: if any prerequisite fails (no anchors / one anchor /
zero anchor span / empty polyline / negative slope / model errors)
the segment downgrades to ``geometry_type="bbox_fallback"`` with a
warning.  The endpoint NEVER fakes geometry — it falls back to bbox
metadata and surfaces the failure mode.

Hard contracts (mirrors E1 / E2a / E2b / E2c doctrine):

* Pure helper.  No STATE, no env reads, no main-module imports,
  no I/O.  Persistence (if any) is the caller's responsibility.
* No PyMuPDF dependency.  Operates entirely on the three JSON
  records produced upstream + the request payload.
* No AI/LLM.  Station validation = regex.  Coverage scoring =
  count of matched station anchors per segment range.  Geometry =
  euclidean projection on a polyline.
* Output is **suggestion-grade**, not authoritative.  Each
  segment carries a confidence + warnings; operator review is
  required before any persistence enables.
* Deterministic: same inputs → byte-identical output.
* Bounded: per-list safety caps prevent pathological payloads
  from blowing up the output.

Schema version: pdf-auto-redline-1.

Authoritative design: pivot reset plan §3 (E3 "auto-redline
pipeline") + E3 ship report § "Next recommended step" + E3.0.5
goal directive.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, Final, List, Optional, Tuple


SCHEMA_VERSION: Final[str] = "pdf-auto-redline-1"
ROUTES_SOURCE_SCHEMA: Final[str] = "pdf-extraction-routes-1"
BINDINGS_SOURCE_SCHEMA: Final[str] = "pdf-extraction-bindings-1"
RAW_SOURCE_SCHEMA: Final[str] = "pdf-extraction-raw-1"
PARAMETERS_VERSION: Final[str] = "v1"
PROJECTION_VERSION: Final[str] = "v1"

# v1 is dry-run only.
_PERSISTENCE_ENABLED_IN_V1: Final[bool] = False

# Per-list safety caps.
_MAX_GENERATED_SEGMENTS: Final[int] = 5_000
_MAX_REJECTED_ROWS: Final[int] = 5_000

# Geometry tunables.
_ENDPOINT_EPS_PT: Final[float] = 2.0          # chain-join tolerance (PDF pts)
_MIN_ANCHOR_SPAN_FT: Final[float] = 50.0      # 2 anchors must span ≥ this in ft
                                              # for "high" geometry_confidence
_MAX_POLYLINE_POINTS_OUT: Final[int] = 2_000  # safety cap on emitted subpath

_FLOAT_DECIMALS: Final[int] = 3

# Station regex: accepts "11+60", "104+25.5", "STA 11+60", "STA. 11+60".
_STATION_TOKEN_RE: Final = re.compile(
    r"^\s*(?:STA\.?\s+)?(\d{1,3})\+(\d{2}(?:\.\d+)?)\s*$",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class PdfAutoRedlineError(Exception):
    """Raised on schema mismatch / non-dict input / missing route candidate.

    Per-row failures (malformed station, end<start, etc.) do NOT raise —
    they surface in ``rejected_rows[]`` instead.
    """


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _r(v: Any) -> float:
    try:
        return round(float(v), _FLOAT_DECIMALS)
    except (TypeError, ValueError):
        return 0.0


def _parse_station_to_ft(s: Any) -> Optional[float]:
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
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
        return ""
    m = _STATION_TOKEN_RE.match(s)
    if not m:
        return ""
    return f"{int(m.group(1))}+{m.group(2)}"


def _confidence_for_anchor_coverage(matched_count: int, range_ft: float) -> str:
    if matched_count >= 2:
        return "high"
    if matched_count == 1 or range_ft < 100.0:
        return "medium"
    return "low"


def _safe_xy(p: Any) -> Optional[Tuple[float, float]]:
    if not isinstance(p, (list, tuple)) or len(p) < 2:
        return None
    try:
        return (float(p[0]), float(p[1]))
    except (TypeError, ValueError):
        return None


def _dist(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


# ---------------------------------------------------------------------------
# Geometry: segment extraction from raw items
# ---------------------------------------------------------------------------

def _segments_from_path_items(items: Any) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
    """Yield (a, b) line/curve-chord segments from a raw path's items list.

    rect / quad ops contribute closed-shape edges — they are typically not
    route polylines but we include them so the greedy chainer can attempt
    to use them; the operator's route_candidate confirms intent.
    """
    out: List[Tuple[Tuple[float, float], Tuple[float, float]]] = []
    if not isinstance(items, list):
        return out
    for it in items:
        if not isinstance(it, (list, tuple)) or not it:
            continue
        op = it[0]
        if op == "l" and len(it) >= 3:
            a = _safe_xy(it[1])
            b = _safe_xy(it[2])
            if a and b and a != b:
                out.append((a, b))
        elif op == "c" and len(it) >= 5:
            a = _safe_xy(it[1])
            b = _safe_xy(it[4])
            if a and b and a != b:
                out.append((a, b))
        elif op == "re" and len(it) >= 2:
            rect = _safe_xy(it[1][:2]) if isinstance(it[1], (list, tuple)) and len(it[1]) >= 4 else None
            if rect is not None and len(it[1]) >= 4:
                try:
                    rx0, ry0, rx1, ry1 = float(it[1][0]), float(it[1][1]), float(it[1][2]), float(it[1][3])
                    corners = [(rx0, ry0), (rx1, ry0), (rx1, ry1), (rx0, ry1)]
                    for i in range(4):
                        out.append((corners[i], corners[(i + 1) % 4]))
                except (TypeError, ValueError):
                    pass
        elif op == "qu" and len(it) >= 5:
            pts = [_safe_xy(it[i + 1]) for i in range(4)]
            if all(pt is not None for pt in pts):
                for i in range(4):
                    out.append((pts[i], pts[(i + 1) % 4]))
    return out


def _collect_route_segments(
    candidate: Dict[str, Any],
    raw_items_by_hash: Dict[str, List[Any]],
) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
    """Walk every path in the route candidate, in canonical
    source_items_hashes order, and return the concatenated segment list."""
    segs: List[Tuple[Tuple[float, float], Tuple[float, float]]] = []
    for h in candidate.get("source_items_hashes") or []:
        items = raw_items_by_hash.get(h)
        if not items:
            continue
        segs.extend(_segments_from_path_items(items))
    return segs


# ---------------------------------------------------------------------------
# Geometry: greedy polyline chain reconstruction
# ---------------------------------------------------------------------------

def _chain_segments_to_polyline(
    segments: List[Tuple[Tuple[float, float], Tuple[float, float]]],
    eps: float = _ENDPOINT_EPS_PT,
) -> Tuple[List[Tuple[float, float]], int]:
    """Greedy endpoint-chain a segment list into a single polyline.

    Returns (polyline_points, segments_consumed).  segments_consumed
    reflects how many input segments fit the chain; consumers can
    compare against ``len(segments)`` to gauge chain quality.

    Algorithm:
      * Start with the first segment as [p1, p2].
      * Walk the remaining segments; for each, if either endpoint is
        within ``eps`` of the current polyline's head or tail, append
        or prepend (reversing the segment if needed).
      * Otherwise queue for a later pass.  Re-pass the queue until no
        more matches.

    Deterministic because input segments come in canonical order.
    """
    if not segments:
        return [], 0

    first_a, first_b = segments[0]
    polyline: List[Tuple[float, float]] = [first_a, first_b]
    consumed = 1
    remaining: List[Tuple[Tuple[float, float], Tuple[float, float]]] = list(segments[1:])

    changed = True
    while changed and remaining:
        changed = False
        next_remaining: List[Tuple[Tuple[float, float], Tuple[float, float]]] = []
        head = polyline[0]
        tail = polyline[-1]
        for (a, b) in remaining:
            if _dist(a, tail) <= eps:
                polyline.append(b)
                tail = b
                consumed += 1
                changed = True
            elif _dist(b, tail) <= eps:
                polyline.append(a)
                tail = a
                consumed += 1
                changed = True
            elif _dist(b, head) <= eps:
                polyline.insert(0, a)
                head = a
                consumed += 1
                changed = True
            elif _dist(a, head) <= eps:
                polyline.insert(0, b)
                head = b
                consumed += 1
                changed = True
            else:
                next_remaining.append((a, b))
        remaining = next_remaining

    return polyline, consumed


def _polyline_length(points: List[Tuple[float, float]]) -> float:
    if len(points) < 2:
        return 0.0
    total = 0.0
    for i in range(len(points) - 1):
        total += _dist(points[i], points[i + 1])
    return total


def _polyline_cum_lengths(points: List[Tuple[float, float]]) -> List[float]:
    """Return cumulative arc length at each vertex.  len == len(points)."""
    if not points:
        return []
    cum: List[float] = [0.0]
    for i in range(1, len(points)):
        cum.append(cum[-1] + _dist(points[i - 1], points[i]))
    return cum


# ---------------------------------------------------------------------------
# Geometry: projection from arbitrary point to polyline
# ---------------------------------------------------------------------------

def _project_point_to_polyline(
    p: Tuple[float, float],
    points: List[Tuple[float, float]],
    cum: List[float],
) -> Optional[Tuple[float, Tuple[float, float], float]]:
    """Return (distance_along_pt, projected_point, perp_distance_pt) or None."""
    if len(points) < 2 or len(cum) != len(points):
        return None
    best: Optional[Tuple[float, Tuple[float, float], float]] = None
    for i in range(len(points) - 1):
        a = points[i]
        b = points[i + 1]
        dx = b[0] - a[0]
        dy = b[1] - a[1]
        seg_len_sq = dx * dx + dy * dy
        if seg_len_sq <= 1e-12:
            t = 0.0
            proj = a
        else:
            t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / seg_len_sq
            t_clamped = max(0.0, min(1.0, t))
            proj = (a[0] + t_clamped * dx, a[1] + t_clamped * dy)
            t = t_clamped
        perp = _dist(p, proj)
        dist_along = cum[i] + t * math.sqrt(seg_len_sq)
        if best is None or perp < best[2]:
            best = (dist_along, proj, perp)
    return best


def _point_at_polyline_distance(
    distance: float,
    points: List[Tuple[float, float]],
    cum: List[float],
) -> Optional[Tuple[float, float]]:
    """Return the (x, y) on the polyline at the given arc-length distance.
    Clamps to [0, total_length]."""
    if len(points) < 2 or len(cum) != len(points):
        return None
    total = cum[-1]
    if total <= 0.0:
        return points[0]
    d = max(0.0, min(total, distance))
    # Binary search for the segment that contains d.
    lo, hi = 0, len(cum) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if cum[mid] < d:
            lo = mid + 1
        else:
            hi = mid
    # lo is the smallest index where cum[lo] >= d.  The containing segment
    # is [lo-1, lo] (unless lo == 0, in which case use [0, 1]).
    i = max(1, lo)
    a = points[i - 1]
    b = points[i]
    seg_len = cum[i] - cum[i - 1]
    if seg_len <= 1e-9:
        return a
    t = (d - cum[i - 1]) / seg_len
    return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))


def _polyline_subpath(
    start_dist: float,
    end_dist: float,
    points: List[Tuple[float, float]],
    cum: List[float],
    max_points_out: int = _MAX_POLYLINE_POINTS_OUT,
) -> List[Tuple[float, float]]:
    """Extract the subpath of the polyline between two arc-length positions.

    Returned list always begins with the projected start point and ends
    with the projected end point.  Intermediate polyline vertices that
    fall strictly between the two distances are inserted in order.

    Handles start > end by reversing (operator-impossible per validation
    upstream, but safe-fall).  Returns [] for empty polyline.
    """
    if len(points) < 2 or len(cum) != len(points):
        return []
    if end_dist < start_dist:
        start_dist, end_dist = end_dist, start_dist
    total = cum[-1]
    start_dist = max(0.0, min(total, start_dist))
    end_dist = max(0.0, min(total, end_dist))
    start_pt = _point_at_polyline_distance(start_dist, points, cum)
    end_pt = _point_at_polyline_distance(end_dist, points, cum)
    if start_pt is None or end_pt is None:
        return []
    out: List[Tuple[float, float]] = [start_pt]
    for i, c in enumerate(cum):
        if start_dist < c < end_dist:
            out.append(points[i])
            if len(out) >= max_points_out - 1:
                break
    out.append(end_pt)
    return out


# ---------------------------------------------------------------------------
# Geometry: station-to-distance linear model
# ---------------------------------------------------------------------------

def _build_station_distance_model(
    anchor_projections: List[Dict[str, Any]],
) -> Optional[Tuple[float, float, Dict[str, Any], Dict[str, Any]]]:
    """Fit a linear station_ft → distance_along_pt model.

    Returns (slope, intercept, anchor_min, anchor_max) or None when no
    safe model can be built.  Picks the two anchors with the smallest
    and largest station_ft (longest baseline → most stable slope).
    Rejects when station_ft span is zero.  Slope may be negative (route
    drawn against station direction); caller can interpret freely.
    """
    if len(anchor_projections) < 2:
        return None
    sorted_anchors = sorted(anchor_projections, key=lambda a: a["station_ft"])
    a_min = sorted_anchors[0]
    a_max = sorted_anchors[-1]
    span_ft = a_max["station_ft"] - a_min["station_ft"]
    if span_ft <= 0:
        return None
    span_dist = a_max["distance_along_pt"] - a_min["distance_along_pt"]
    slope = span_dist / span_ft
    intercept = a_min["distance_along_pt"] - slope * a_min["station_ft"]
    return slope, intercept, a_min, a_max


def _station_ft_to_distance(slope: float, intercept: float, station_ft: float) -> float:
    return slope * station_ft + intercept


# ---------------------------------------------------------------------------
# Pure entry: build the geometry context for a route candidate
# ---------------------------------------------------------------------------

def _build_route_geometry_context(
    candidate: Dict[str, Any],
    raw_record: Dict[str, Any],
    anchor_pool: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Prepare polyline + anchor projections + station→distance model.

    Returns a dict with:
      * polyline_points: List[Tuple[float, float]]   (may be empty)
      * cum_lengths:     List[float]
      * total_length_pt: float
      * segment_count:   int (raw segments collected from items)
      * segments_consumed_in_chain: int
      * anchor_projections: List[{station_ft, distance_along_pt,
                                  projected_point, perp_distance_pt,
                                  source_anchor: <raw anchor>}]
      * model: (slope, intercept, anchor_min, anchor_max) or None
      * page_warnings: list of geometry-context warnings (page-level)
    """
    # Build raw items lookup.
    raw_items_by_hash: Dict[str, List[Any]] = {}
    for p in (raw_record.get("vector_paths") or []):
        if not isinstance(p, dict):
            continue
        h = p.get("items_hash")
        if isinstance(h, str) and h:
            raw_items_by_hash[h] = p.get("items") or []

    segments = _collect_route_segments(candidate, raw_items_by_hash)
    polyline, consumed = _chain_segments_to_polyline(segments)
    cum = _polyline_cum_lengths(polyline)
    total = cum[-1] if cum else 0.0

    page_warnings: List[str] = []
    if not segments:
        page_warnings.append("geometry_route_segments_empty")
    if not polyline:
        page_warnings.append("geometry_polyline_empty")
    if polyline and consumed < len(segments):
        page_warnings.append("geometry_polyline_chain_partial")

    # Project each anchor in the pool.
    anchor_projections: List[Dict[str, Any]] = []
    for a in anchor_pool:
        ap = a.get("_anchor_xy")
        if ap is None:
            ap_raw = a.get("anchor_point")
            ap = _safe_xy(ap_raw)
        if ap is None or not polyline:
            continue
        proj = _project_point_to_polyline(ap, polyline, cum)
        if proj is None:
            continue
        dist_along, projected_pt, perp = proj
        anchor_projections.append({
            "station_ft":         a["_station_ft"],
            "distance_along_pt":  _r(dist_along),
            "projected_point":    [_r(projected_pt[0]), _r(projected_pt[1])],
            "perp_distance_pt":   _r(perp),
            "anchor_block_no":    a.get("block_no"),
            "anchor_text":        a.get("matched_text"),
        })

    # Sort anchor projections deterministically (station_ft asc, block_no).
    anchor_projections.sort(key=lambda x: (x["station_ft"], x.get("anchor_block_no") or 0))

    model = _build_station_distance_model(anchor_projections)

    return {
        "polyline_points": polyline,
        "cum_lengths":     cum,
        "total_length_pt": _r(total),
        "segment_count":   len(segments),
        "segments_consumed_in_chain": consumed,
        "anchor_projections": anchor_projections,
        "model": model,
        "page_warnings": page_warnings,
    }


# ---------------------------------------------------------------------------
# Per-segment geometry computation
# ---------------------------------------------------------------------------

def _compute_segment_geometry(
    start_ft: float,
    end_ft: float,
    geom_ctx: Dict[str, Any],
) -> Dict[str, Any]:
    """Map a station range to polyline subpath via the geometry context.

    Returns a dict with geometry_type, polyline_points, start_projection,
    end_projection, projection_method, geometry_confidence, geometry_warnings.

    Always emits *some* result; on failure returns bbox_fallback record
    with appropriate warnings.  The caller adds route_candidate_bbox
    separately (already in the candidate record).
    """
    polyline = geom_ctx["polyline_points"]
    cum = geom_ctx["cum_lengths"]
    total = geom_ctx["total_length_pt"]
    model = geom_ctx["model"]
    warnings: List[str] = []

    def _fallback(reason: str) -> Dict[str, Any]:
        warnings.append(reason)
        return {
            "geometry_type":       "bbox_fallback",
            "polyline_points":     None,
            "start_projection":    None,
            "end_projection":      None,
            "projection_method":   "bbox_fallback",
            "geometry_confidence": "none",
            "geometry_warnings":   warnings,
        }

    if not polyline:
        return _fallback("geometry_bbox_fallback_polyline_empty")
    if model is None:
        n_anchors = len(geom_ctx["anchor_projections"])
        if n_anchors == 0:
            return _fallback("geometry_bbox_fallback_no_anchors")
        if n_anchors == 1:
            return _fallback("geometry_bbox_fallback_single_anchor")
        # >=2 anchors but model failed (e.g. same station_ft) → safe fallback
        return _fallback("geometry_bbox_fallback_anchor_span_zero")

    slope, intercept, anchor_min, anchor_max = model

    # Map stations to distances along the polyline.
    start_dist_raw = _station_ft_to_distance(slope, intercept, start_ft)
    end_dist_raw   = _station_ft_to_distance(slope, intercept, end_ft)

    # Clamp to polyline bounds + warn.
    start_dist = max(0.0, min(total, start_dist_raw))
    end_dist = max(0.0, min(total, end_dist_raw))
    if start_dist != start_dist_raw:
        warnings.append("geometry_start_clipped_to_polyline_bounds")
    if end_dist != end_dist_raw:
        warnings.append("geometry_end_clipped_to_polyline_bounds")

    if abs(end_dist - start_dist) < 1e-6:
        # Zero-length result after clip → fallback (no meaningful polyline).
        return _fallback("geometry_bbox_fallback_zero_length_after_clip")

    subpath = _polyline_subpath(start_dist, end_dist, polyline, cum)
    if len(subpath) < 2:
        return _fallback("geometry_bbox_fallback_subpath_empty")

    # Direction normalization: the subpath helper sorts start_dist/end_dist
    # internally; preserve the operator's start→end direction by checking
    # whether start_dist < end_dist.  If end_dist < start_dist (negative
    # slope and reversed input), flip the subpath.
    if end_dist < start_dist:
        subpath = list(reversed(subpath))

    start_pt = subpath[0]
    end_pt = subpath[-1]

    # Determine if the segment range is OUTSIDE the anchor span.
    anchor_span_ft = anchor_max["station_ft"] - anchor_min["station_ft"]
    outside_anchor_span = (
        start_ft < anchor_min["station_ft"] - 1e-6
        or end_ft > anchor_max["station_ft"] + 1e-6
        or start_ft > anchor_max["station_ft"] + 1e-6
        or end_ft < anchor_min["station_ft"] - 1e-6
    )
    if outside_anchor_span:
        warnings.append("geometry_extrapolated_outside_anchor_span")

    # geometry_confidence:
    #   - "high":   model from anchors with span >= _MIN_ANCHOR_SPAN_FT
    #               AND segment range inside anchor span AND no clipping
    #               AND polyline chain consumed all segments cleanly
    #   - "medium": some condition relaxed (extrapolated OR partial chain
    #               OR small anchor span) but no clipping
    #   - "low":    clipping occurred OR meaningful extrapolation
    if (
        anchor_span_ft >= _MIN_ANCHOR_SPAN_FT
        and not outside_anchor_span
        and "geometry_start_clipped_to_polyline_bounds" not in warnings
        and "geometry_end_clipped_to_polyline_bounds" not in warnings
        and geom_ctx["segments_consumed_in_chain"] == geom_ctx["segment_count"]
        and geom_ctx["segment_count"] > 0
    ):
        geom_conf = "high"
    elif (
        "geometry_start_clipped_to_polyline_bounds" in warnings
        or "geometry_end_clipped_to_polyline_bounds" in warnings
    ):
        geom_conf = "low"
    else:
        geom_conf = "medium"

    # Round emitted coordinates.
    polyline_out = [[_r(x), _r(y)] for (x, y) in subpath]

    return {
        "geometry_type":     "polyline",
        "polyline_points":   polyline_out,
        "start_projection": {
            "point":                  [_r(start_pt[0]), _r(start_pt[1])],
            "distance_along_route_pt": _r(start_dist),
            "source":                  "interpolated",
        },
        "end_projection": {
            "point":                  [_r(end_pt[0]), _r(end_pt[1])],
            "distance_along_route_pt": _r(end_dist),
            "source":                  "interpolated",
        },
        "projection_method":   "two_anchor_linear",
        "geometry_confidence": geom_conf,
        "geometry_warnings":   warnings,
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def generate_auto_redline_segments(
    raw_record: Dict[str, Any],
    routes_record: Dict[str, Any],
    bindings_record: Dict[str, Any],
    request_payload: Dict[str, Any],
) -> Dict[str, Any]:
    """Produce auto_extracted segment specs with projected polyline
    geometry from the extraction stack output."""
    # ──── Schema validation (raise-able) ────────────────────────────────
    for name, rec, expected in (
        ("raw_record",      raw_record,      RAW_SOURCE_SCHEMA),
        ("routes_record",   routes_record,   ROUTES_SOURCE_SCHEMA),
        ("bindings_record", bindings_record, BINDINGS_SOURCE_SCHEMA),
    ):
        if not isinstance(rec, dict):
            raise PdfAutoRedlineError(
                f"{name} must be a dict; got {type(rec).__name__}"
            )
        if rec.get("schema_version") != expected:
            raise PdfAutoRedlineError(
                f"{name} schema_version must be {expected!r}; "
                f"got {rec.get('schema_version')!r}"
            )
    if not isinstance(request_payload, dict):
        raise PdfAutoRedlineError(
            f"request_payload must be a dict; got {type(request_payload).__name__}"
        )

    # ──── Confirm route candidate ───────────────────────────────────────
    confirmed_id = str(request_payload.get("route_candidate_id") or "").strip()
    if not confirmed_id:
        raise PdfAutoRedlineError("request_payload.route_candidate_id is required.")

    candidate: Optional[Dict[str, Any]] = None
    for c in routes_record.get("route_candidates") or []:
        if isinstance(c, dict) and c.get("candidate_id") == confirmed_id:
            candidate = c
            break
    if candidate is None:
        raise PdfAutoRedlineError(
            f"route_candidate_id {confirmed_id!r} not found in routes_record. "
            f"Available: "
            f"{[c.get('candidate_id') for c in (routes_record.get('route_candidates') or []) if isinstance(c, dict)]}"
        )

    rows = request_payload.get("rows")
    if not isinstance(rows, list):
        raise PdfAutoRedlineError(
            f"request_payload.rows must be a list; got {type(rows).__name__}"
        )

    # ──── Pre-compute anchor pool ───────────────────────────────────────
    anchor_pool: List[Dict[str, Any]] = []
    for a in bindings_record.get("station_anchors") or []:
        if not isinstance(a, dict):
            continue
        if a.get("route_candidate_id") != confirmed_id:
            continue
        ft = _parse_station_to_ft(a.get("matched_text"))
        if ft is None:
            continue
        anchor_pool.append({
            **a,
            "_station_ft": _r(ft),
            "_anchor_xy":  _safe_xy(a.get("anchor_point")),
        })
    available_anchor_count = len(anchor_pool)

    # ──── Build geometry context ONCE for this route candidate ──────────
    geom_ctx = _build_route_geometry_context(candidate, raw_record, anchor_pool)

    # ──── Per-row generation ────────────────────────────────────────────
    generated: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []

    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            rejected.append({
                "input_row_index": idx,
                "input_row":       row,
                "reason":          "row is not a dict",
                "rule_id":         "auto_redline_v1:row_shape",
            })
            continue
        start_raw = row.get("start_station")
        end_raw   = row.get("end_station")
        start_ft = _parse_station_to_ft(start_raw)
        end_ft   = _parse_station_to_ft(end_raw)
        if start_ft is None:
            rejected.append({
                "input_row_index": idx,
                "input_row":       row,
                "reason":          f"start_station unparseable: {start_raw!r}",
                "rule_id":         "auto_redline_v1:start_station_format",
            })
            continue
        if end_ft is None:
            rejected.append({
                "input_row_index": idx,
                "input_row":       row,
                "reason":          f"end_station unparseable: {end_raw!r}",
                "rule_id":         "auto_redline_v1:end_station_format",
            })
            continue
        if end_ft <= start_ft:
            rejected.append({
                "input_row_index": idx,
                "input_row":       row,
                "reason":          (
                    f"end_station_ft ({end_ft}) must be > start_station_ft "
                    f"({start_ft})"
                ),
                "rule_id":         "auto_redline_v1:end_before_start",
            })
            continue

        range_ft = end_ft - start_ft

        # Anchor coverage within [start_ft, end_ft].
        matched_anchors: List[Dict[str, Any]] = []
        for a in anchor_pool:
            ft = a["_station_ft"]
            if start_ft <= ft <= end_ft:
                exposed = {k: v for k, v in a.items() if not k.startswith("_")}
                matched_anchors.append(exposed)

        coverage_warnings: List[str] = []
        if len(matched_anchors) == 0:
            coverage_warnings.append("no_station_anchors_in_range")
        if anchor_pool:
            anchor_min = min(a["_station_ft"] for a in anchor_pool)
            anchor_max = max(a["_station_ft"] for a in anchor_pool)
            if start_ft < anchor_min or end_ft > anchor_max:
                coverage_warnings.append("range_outside_anchored_extent")

        coverage_conf = _confidence_for_anchor_coverage(len(matched_anchors), range_ft)

        # Geometry projection (E3.0.5).
        geom = _compute_segment_geometry(start_ft, end_ft, geom_ctx)

        seg: Dict[str, Any] = {
            "start_label":        _normalize_station_label(start_raw),
            "end_label":          _normalize_station_label(end_raw),
            "start_station_ft":   _r(start_ft),
            "end_station_ft":     _r(end_ft),
            "length_ft":          _r(range_ft),
            "source":             "auto_extracted",
            "route_candidate_id": confirmed_id,
            "route_candidate_bbox": list(candidate.get("bbox") or []),
            "notes":              str(row.get("notes") or "") or None,
            "matched_anchor_count": len(matched_anchors),
            "matched_anchors":    matched_anchors,
            "confidence": {
                "kind":                 coverage_conf,
                "matched_anchor_count": len(matched_anchors),
                "warnings":             coverage_warnings,
            },
            # NEW E3.0.5 geometry fields:
            "geometry_type":       geom["geometry_type"],
            "polyline_points":     geom["polyline_points"],
            "start_projection":    geom["start_projection"],
            "end_projection":      geom["end_projection"],
            "projection_method":   geom["projection_method"],
            "geometry_confidence": geom["geometry_confidence"],
            "geometry_warnings":   geom["geometry_warnings"],
            # Provenance (unchanged):
            "rule_id":            "auto_redline_v1",
            "provenance": {
                "input_row_index": idx,
                "input_row":       row,
            },
        }
        generated.append(seg)

    # ──── Apply caps ────────────────────────────────────────────────────
    generated = generated[:_MAX_GENERATED_SEGMENTS]
    rejected = rejected[:_MAX_REJECTED_ROWS]

    # ──── Deterministic sort + ID assignment ────────────────────────────
    generated.sort(key=lambda s: (
        s["start_station_ft"],
        s["end_station_ft"],
        s["provenance"]["input_row_index"],
    ))
    for i, seg in enumerate(generated):
        seg["segment_id"] = f"ar_{i:04d}"

    rejected.sort(key=lambda r: r["input_row_index"])

    # ──── Page-level warnings ───────────────────────────────────────────
    page_warnings: List[str] = list(geom_ctx.get("page_warnings") or [])
    if available_anchor_count == 0:
        page_warnings.append("no_station_anchors_bound_to_route_candidate")
    if len(generated) == 0 and len(rows) > 0:
        page_warnings.append("no_segments_generated_all_rows_rejected")

    # Dry-run policy.
    dry_run_intent = bool(request_payload.get("dry_run", True))
    persisted = False

    # ──── Assemble envelope ─────────────────────────────────────────────
    page_size_px = raw_record.get("page_size_px") or [0.0, 0.0]
    try:
        page_w = _r(page_size_px[0])
        page_h = _r(page_size_px[1])
    except (TypeError, IndexError):
        page_w = page_h = 0.0

    # Anchor projections (without internal helper fields) for caller visibility.
    public_anchor_projections = list(geom_ctx["anchor_projections"])

    return {
        "schema_version":                 SCHEMA_VERSION,
        "source_routes_schema_version":   ROUTES_SOURCE_SCHEMA,
        "source_bindings_schema_version": BINDINGS_SOURCE_SCHEMA,
        "source_raw_schema_version":      RAW_SOURCE_SCHEMA,
        "page_index":                     raw_record.get("page_index"),
        "page_number":                    raw_record.get("page_number"),
        "page_size_px":                   [page_w, page_h],
        "page_rotation":                  int(raw_record.get("page_rotation") or 0),
        "bucket":                         routes_record.get("bucket"),
        "route_candidate_id":             confirmed_id,
        "route_candidate_bbox":           list(candidate.get("bbox") or []),
        "route_candidate_total_length_pt": _r(candidate.get("total_length_pt") or 0.0),
        # NEW E3.0.5 page-level geometry fields:
        "route_polyline_points":         [
            [_r(x), _r(y)] for (x, y) in (geom_ctx["polyline_points"] or [])[:_MAX_POLYLINE_POINTS_OUT]
        ],
        "route_polyline_total_length_pt": geom_ctx["total_length_pt"],
        "route_polyline_built":           bool(geom_ctx["polyline_points"]),
        "anchor_projections":             public_anchor_projections,
        "parameters": {
            "version":            PARAMETERS_VERSION,
            "projection_version": PROJECTION_VERSION,
            "dry_run_intent":     dry_run_intent,
            "endpoint_eps_pt":    _ENDPOINT_EPS_PT,
            "min_anchor_span_ft": _MIN_ANCHOR_SPAN_FT,
        },
        "generated_segments": generated,
        "rejected_rows":      rejected,
        "warnings":           page_warnings,
        "meta": {
            "input_row_count":            len(rows),
            "generated_segment_count":    len(generated),
            "rejected_row_count":         len(rejected),
            "available_anchor_count":     available_anchor_count,
            "anchor_projection_count":    len(public_anchor_projections),
            "route_polyline_segment_count": geom_ctx["segment_count"],
            "route_polyline_segments_consumed_in_chain": geom_ctx["segments_consumed_in_chain"],
            "dry_run_intent":             dry_run_intent,
            "persisted":                  persisted,
            "persistence_enabled_in_v1":  _PERSISTENCE_ENABLED_IN_V1,
            "persistence_note":           (
                "v1 NEVER persists.  dry_run_intent is recorded for "
                "forward-compatibility; real persistence ships in E3.1 "
                "after operator validation against Kelly PDFs."
            ),
        },
    }
