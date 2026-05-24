"""Anti-Collapse V2 alternate-placement search — deterministic, audit-only.

Given the V1 collision resolution result, this module searches each loser's
existing candidate_rankings for an alternate route that:

  1. Clears a deterministic score floor.
  2. Lies geographically near the loser's existing redline_segments
     (mean perpendicular distance <= max_perp_ft).
  3. Does NOT collide with any already-kept group on that alternate route
     (overlap_ratio against every kept range < overlap_threshold).

Pure read-only. Never mutates inputs. Returns a structured decision per
loser; the caller is responsible for re-running the build path and
mutating group_match if an alternate is selected.

This module deliberately does NOT call into main.py or STATE. The caller
passes:

  - the loser's group_match dict (carries route_id, group_redline_segments,
    _normalized_group, source_file, candidate_rankings)
  - the route_catalog list
  - a precomputed kept_offsets_by_route map
    {route_id: [(lo_ft, hi_ft), ...]}

Geographic-proximity guard intentionally projects the loser's EXISTING
segments (built for the original route) onto the alternate route. If the
loser was working on a corridor near the alternate, that projection will
yield a small mean perpendicular distance; if the alternate is in a
different part of town, the perp distance blows up and we abstain. This
is the "deterministic evidence, not guessing" requirement.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple


# Coverage_sanity uses the same earth-radius constant; mirror it byte-identical
# so projections agree to the foot.
_EARTH_RADIUS_FT = 20902231.0
_FT_PER_DEG_LAT = 364567.2


def _safe_float(value: Any) -> float:
    try:
        return float(value if value is not None else 0.0)
    except (TypeError, ValueError):
        return 0.0


def _safe_str(value: Any) -> str:
    return str(value if value is not None else "").strip()


def _haversine_ft(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    lon1, lat1 = math.radians(p1[0]), math.radians(p1[1])
    lon2, lat2 = math.radians(p2[0]), math.radians(p2[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * _EARTH_RADIUS_FT * math.asin(math.sqrt(max(0.0, min(1.0, a))))


def _coerce_lonlat(coord: Any) -> Optional[Tuple[float, float]]:
    """Accept (lon, lat) tuples/lists OR [lat, lon] frontend-style lists.

    Mirrors coverage_sanity._coerce_lonlat so the same projection math
    works on every coord shape the engine produces. Brenham-area sanity:
    lon < 0, lat > 0; for any pair that does not fit that, fall through
    unchanged (caller has already established WGS84).
    """
    if coord is None:
        return None
    try:
        a, b = float(coord[0]), float(coord[1])
    except (TypeError, ValueError, IndexError):
        return None
    if a < 0 and 0 < b < 90:
        return (a, b)
    if 0 < a < 90 and b < 0:
        return (b, a)
    return (a, b)


def _normalize_route_coords(coords: Sequence[Any]) -> List[Tuple[float, float]]:
    out: List[Tuple[float, float]] = []
    for raw in coords or []:
        lonlat = _coerce_lonlat(raw)
        if lonlat is not None:
            out.append(lonlat)
    return out


def _project_point_onto_route(
    point: Tuple[float, float],
    route_coords: Sequence[Tuple[float, float]],
) -> Optional[Tuple[float, float]]:
    """Return (cumulative_offset_ft, perp_distance_ft) for the closest
    projection of `point` onto the polyline `route_coords`. None when the
    route is degenerate.

    Equirectangular projection at segment-midpoint latitude — matches
    coverage_sanity._route_offset_for_point exactly so V2 and V1 collision
    arithmetic agree.
    """
    if not route_coords or len(route_coords) < 2:
        return None
    best_offset: Optional[float] = None
    best_perp_ft = float("inf")
    cumulative_ft = 0.0
    px, py = point
    for i in range(len(route_coords) - 1):
        a = route_coords[i]
        b = route_coords[i + 1]
        seg_len_ft = _haversine_ft(a, b)
        if seg_len_ft <= 0.0:
            continue
        mid_lat_rad = math.radians((a[1] + b[1]) / 2.0)
        cos_lat = math.cos(mid_lat_rad)
        ax_ft = a[0] * _FT_PER_DEG_LAT * cos_lat
        ay_ft = a[1] * _FT_PER_DEG_LAT
        bx_ft = b[0] * _FT_PER_DEG_LAT * cos_lat
        by_ft = b[1] * _FT_PER_DEG_LAT
        ppx_ft = px * _FT_PER_DEG_LAT * cos_lat
        ppy_ft = py * _FT_PER_DEG_LAT
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
        if perp_ft < best_perp_ft:
            best_perp_ft = perp_ft
            best_offset = cumulative_ft + t_clamped * seg_len_ft
        cumulative_ft += seg_len_ft
    if best_offset is None:
        return None
    return (best_offset, best_perp_ft)


def project_segments_onto_route(
    group_redline_segments: Sequence[Dict[str, Any]],
    route_coords: Sequence[Tuple[float, float]],
) -> Optional[Dict[str, float]]:
    """Project every coord of every segment onto `route_coords`. Return
      {"lo_ft", "hi_ft", "span_ft", "mean_perp_ft", "max_perp_ft", "point_count"}
    or None when nothing projects (degenerate route or no usable coords).

    `route_coords` must already be `_normalize_route_coords`-ed.
    """
    if not group_redline_segments or not route_coords or len(route_coords) < 2:
        return None
    offsets: List[float] = []
    perps: List[float] = []
    for seg in group_redline_segments:
        for raw in (seg or {}).get("coords") or []:
            lonlat = _coerce_lonlat(raw)
            if lonlat is None:
                continue
            proj = _project_point_onto_route(lonlat, route_coords)
            if proj is None:
                continue
            offsets.append(proj[0])
            perps.append(proj[1])
    if not offsets:
        return None
    lo = min(offsets)
    hi = max(offsets)
    return {
        "lo_ft": lo,
        "hi_ft": hi,
        "span_ft": max(0.0, hi - lo),
        "mean_perp_ft": sum(perps) / len(perps),
        "max_perp_ft": max(perps),
        "point_count": len(offsets),
    }


def compute_pair_overlap_ratio(
    a: Tuple[float, float],
    b: Tuple[float, float],
) -> Tuple[float, float]:
    """Return (overlap_ratio, overlap_ft) using the SHORTER-span normalization
    used by coverage_sanity._detect_same_route_collisions.

    Identical normalization is critical so V2's reject decision agrees with
    the post-resolution coverage_sanity recompute.
    """
    a_lo, a_hi = a
    b_lo, b_hi = b
    a_span = max(0.0, a_hi - a_lo)
    b_span = max(0.0, b_hi - b_lo)
    overlap_lo = max(a_lo, b_lo)
    overlap_hi = min(a_hi, b_hi)
    overlap_ft = max(0.0, overlap_hi - overlap_lo)
    min_span = min(a_span, b_span)
    if min_span <= 0.0:
        return (0.0, overlap_ft)
    return (overlap_ft / min_span, overlap_ft)


def build_kept_offsets_by_route(
    group_matches: Sequence[Dict[str, Any]],
    abstained_source_files: Sequence[str],
    route_catalog: Sequence[Dict[str, Any]],
) -> Dict[str, List[Tuple[float, float]]]:
    """Project every kept group's redline_segments onto its own route to
    build the per-route offset-range map V2's overlap guard consults.

    A "kept" group is one with render_allowed=True AND source_file not in
    the V1 abstained set. We use the same projection used by coverage_sanity
    so V2 and V1 see overlaps identically.
    """
    abstained = {str(sf or "") for sf in abstained_source_files or []}
    coords_by_route: Dict[str, List[Tuple[float, float]]] = {}
    for r in route_catalog or []:
        rid = _safe_str((r or {}).get("route_id"))
        if rid:
            coords_by_route[rid] = _normalize_route_coords((r or {}).get("coords") or [])

    out: Dict[str, List[Tuple[float, float]]] = {}
    for m in group_matches or []:
        if not bool((m or {}).get("render_allowed")):
            continue
        sf = _safe_str((m or {}).get("source_file"))
        if sf in abstained:
            continue
        rid = _safe_str((m or {}).get("route_id"))
        if not rid:
            continue
        coords = coords_by_route.get(rid) or []
        if len(coords) < 2:
            continue
        projection = project_segments_onto_route(
            (m or {}).get("group_redline_segments") or [],
            coords,
        )
        if projection is None:
            continue
        out.setdefault(rid, []).append(
            (projection["lo_ft"], projection["hi_ft"])
        )
    return out


def search_alternate_placement(
    loser_match: Dict[str, Any],
    *,
    route_catalog: Sequence[Dict[str, Any]],
    kept_offsets_by_route: Dict[str, List[Tuple[float, float]]],
    min_score: float = 0.10,
    max_perp_ft: float = 200.0,
    overlap_threshold: float = 0.50,
) -> Dict[str, Any]:
    """Search the loser's candidate_rankings for the highest-ranked
    alternate route that (a) clears the score floor, (b) is geographically
    near the loser's existing segments, and (c) does not collide with any
    already-kept group on that route.

    Returns:
      {
        "outcome": "alternate_selected" | "no_safe_alternate",
        "source_file": <str>,
        "original_route_id": <str>,
        "original_confidence": <float>,
        "alternate_route_id": <str|None>,
        "alternate_route_name": <str|None>,
        "alternate_confidence": <float|None>,
        "projected_range_ft": [lo, hi] | None,
        "alternate_mean_perp_ft": <float|None>,
        "candidate_count": <int>,
        "rejected_candidates": [{"route_id", "score", "reason", "detail"}, ...],
      }
    """
    source_file = _safe_str((loser_match or {}).get("source_file"))
    original_route_id = _safe_str((loser_match or {}).get("route_id"))
    original_confidence = _safe_float((loser_match or {}).get("confidence"))
    rankings = list((loser_match or {}).get("candidate_rankings") or [])
    loser_segments = (loser_match or {}).get("group_redline_segments") or []

    route_by_id: Dict[str, Dict[str, Any]] = {}
    for r in route_catalog or []:
        rid = _safe_str((r or {}).get("route_id"))
        if rid and rid not in route_by_id:
            route_by_id[rid] = r or {}

    rejected: List[Dict[str, Any]] = []
    examined = 0

    for cand in rankings:
        cand_rid = _safe_str((cand or {}).get("route_id"))
        cand_score = _safe_float((cand or {}).get("score"))
        cand_name = _safe_str((cand or {}).get("route_name"))

        if not cand_rid or cand_rid == original_route_id:
            continue

        examined += 1

        if cand_score < min_score:
            rejected.append({
                "route_id": cand_rid,
                "route_name": cand_name,
                "score": round(cand_score, 4),
                "reason": "below_min_score",
                "detail": {"min_score": min_score},
            })
            continue

        route = route_by_id.get(cand_rid) or {}
        coords = _normalize_route_coords(route.get("coords") or [])
        if len(coords) < 2:
            rejected.append({
                "route_id": cand_rid,
                "route_name": cand_name,
                "score": round(cand_score, 4),
                "reason": "route_geometry_unusable",
                "detail": {"point_count": len(coords)},
            })
            continue

        projection = project_segments_onto_route(loser_segments, coords)
        if projection is None:
            rejected.append({
                "route_id": cand_rid,
                "route_name": cand_name,
                "score": round(cand_score, 4),
                "reason": "no_projection_onto_alternate",
                "detail": {},
            })
            continue

        if projection["mean_perp_ft"] > max_perp_ft:
            rejected.append({
                "route_id": cand_rid,
                "route_name": cand_name,
                "score": round(cand_score, 4),
                "reason": "geographically_distant",
                "detail": {
                    "mean_perp_ft": round(projection["mean_perp_ft"], 2),
                    "max_perp_ft": round(projection["max_perp_ft"], 2),
                    "max_perp_threshold_ft": max_perp_ft,
                },
            })
            continue

        kept_ranges = kept_offsets_by_route.get(cand_rid) or []
        alt_range = (projection["lo_ft"], projection["hi_ft"])
        worst_overlap_ratio = 0.0
        worst_overlap_ft = 0.0
        colliding_kept_range: Optional[Tuple[float, float]] = None
        for kr in kept_ranges:
            ratio, ft = compute_pair_overlap_ratio(alt_range, kr)
            if ratio > worst_overlap_ratio:
                worst_overlap_ratio = ratio
                worst_overlap_ft = ft
                colliding_kept_range = kr

        if worst_overlap_ratio >= overlap_threshold:
            rejected.append({
                "route_id": cand_rid,
                "route_name": cand_name,
                "score": round(cand_score, 4),
                "reason": "would_collide_with_kept_group",
                "detail": {
                    "overlap_ratio": round(worst_overlap_ratio, 4),
                    "overlap_ft": round(worst_overlap_ft, 2),
                    "alternate_range_ft": [
                        round(alt_range[0], 2),
                        round(alt_range[1], 2),
                    ],
                    "colliding_kept_range_ft": (
                        [round(colliding_kept_range[0], 2), round(colliding_kept_range[1], 2)]
                        if colliding_kept_range else None
                    ),
                    "overlap_threshold": overlap_threshold,
                },
            })
            continue

        return {
            "outcome": "alternate_selected",
            "source_file": source_file,
            "original_route_id": original_route_id,
            "original_confidence": round(original_confidence, 4),
            "alternate_route_id": cand_rid,
            "alternate_route_name": cand_name,
            "alternate_confidence": round(cand_score, 4),
            "projected_range_ft": [
                round(projection["lo_ft"], 2),
                round(projection["hi_ft"], 2),
            ],
            "alternate_mean_perp_ft": round(projection["mean_perp_ft"], 2),
            "alternate_max_perp_ft": round(projection["max_perp_ft"], 2),
            "alternate_overlap_ratio": round(worst_overlap_ratio, 4),
            "candidate_count": examined,
            "rejected_candidates": rejected,
            "thresholds": {
                "min_score": min_score,
                "max_perp_ft": max_perp_ft,
                "overlap_threshold": overlap_threshold,
            },
        }

    return {
        "outcome": "no_safe_alternate",
        "source_file": source_file,
        "original_route_id": original_route_id,
        "original_confidence": round(original_confidence, 4),
        "alternate_route_id": None,
        "alternate_route_name": None,
        "alternate_confidence": None,
        "projected_range_ft": None,
        "alternate_mean_perp_ft": None,
        "candidate_count": examined,
        "rejected_candidates": rejected,
        "thresholds": {
            "min_score": min_score,
            "max_perp_ft": max_perp_ft,
            "overlap_threshold": overlap_threshold,
        },
    }
