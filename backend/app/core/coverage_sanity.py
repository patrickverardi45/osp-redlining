"""Coverage Sanity — post-rebuild collapse-and-distribution diagnostic.

Reads the per-group match outcomes after the rebuild loop completes and
emits a route-distribution + overuse report. Pure read-only; does not
modify any inputs or rebuild outputs.

Output written to STATE["coverage_sanity"] for operator audit. Designed
to surface the "completed corpus collapsed onto 4-5 routes" failure mode
the user has observed in production, plus the related "two bore-logs
project onto the same segment of the same route" anchor-collision
pattern (e.g. bore_log29 + bore_log30 stacking on route_477).

This sprint: diagnostic only — no scoring, ranking, or placement changes.
Operators can review the report and decide whether to investigate
specific routes flagged as overused or specific group pairs flagged as
same-route anchor collisions.
"""

from __future__ import annotations

import math
import os
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Defaults tuned for the Brenham 58-group corpus context. Operators can
# override at call site if needed.
_DEFAULT_OVERUSE_MIN_COUNT = 5
_DEFAULT_OVERUSE_SHARE_PCT = 0.25
_DEFAULT_TOP5_COLLAPSE_THRESHOLD = 0.80
# Same-route anchor collision: pair of groups on the same route whose
# projected route-offset ranges overlap by >= this fraction of the
# shorter group's range.
_DEFAULT_SAME_ROUTE_COLLISION_THRESHOLD = 0.50

# Collision Window V2 — Station-Frame Distinctness Override.
# When TRUELINE_SAME_ROUTE_WINDOW_OWNERSHIP=1, a projected-overlap pair is
# only treated as a true collision when the two groups' STATION-FRAME
# ranges also overlap by >= this fraction of the shorter station span.
# Below the floor, the pair is reclassified as
# "allow_both_distinct_station_windows": the projection collapsed two
# distinct field-frame work windows onto the same KMZ route, but the
# crews bored physically distinct stretches and both should draw.
_DEFAULT_STATION_DISTINCTNESS_FLOOR = 0.10
_ENV_STATION_DISTINCTNESS = "TRUELINE_SAME_ROUTE_WINDOW_OWNERSHIP"


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _safe_float_or_none(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _resolve_station_distinctness_floor(explicit: Optional[float]) -> Optional[float]:
    """Determine the effective station-distinctness floor.

    Priority:
      1. Explicit kwarg (any float, including 0.0) wins for tests + callers.
      2. Else if env TRUELINE_SAME_ROUTE_WINDOW_OWNERSHIP=1, use 0.10 default.
      3. Else None — override disabled; legacy behavior preserved byte-identically.
    """
    if explicit is not None:
        return explicit
    if os.getenv(_ENV_STATION_DISTINCTNESS, "0").strip() == "1":
        return _DEFAULT_STATION_DISTINCTNESS_FLOOR
    return None


def _station_overlap(
    a_min: Any, a_max: Any, b_min: Any, b_max: Any,
) -> Tuple[Optional[float], Optional[float]]:
    """Return (overlap_ft, overlap_ratio_against_shorter_span).

    Returns (None, None) when any station-frame endpoint is missing /
    non-numeric, OR when either group's station span is non-positive
    (single-point groups cannot be meaningfully distinct in station-frame).
    """
    am = _safe_float_or_none(a_min)
    ax = _safe_float_or_none(a_max)
    bm = _safe_float_or_none(b_min)
    bx = _safe_float_or_none(b_max)
    if am is None or ax is None or bm is None or bx is None:
        return (None, None)
    a_span = max(ax - am, 0.0)
    b_span = max(bx - bm, 0.0)
    shorter = min(a_span, b_span)
    if shorter <= 0.0:
        return (None, None)
    overlap_ft = max(0.0, min(ax, bx) - max(am, bm))
    return (overlap_ft, overlap_ft / shorter)


def _route_role_for_id(route_catalog: Sequence[Dict[str, Any]], route_id: str) -> str:
    target = str(route_id or "").strip()
    if not target:
        return ""
    for r in route_catalog or []:
        if str((r or {}).get("route_id") or "").strip() == target:
            return str((r or {}).get("route_role") or "")
    return ""


def _route_lookup(route_catalog: Sequence[Dict[str, Any]], route_id: str) -> Dict[str, Any]:
    target = str(route_id or "").strip()
    if not target:
        return {}
    for r in route_catalog or []:
        if str((r or {}).get("route_id") or "").strip() == target:
            return r or {}
    return {}


_EARTH_RADIUS_FT = 20902231.0


def _haversine_ft(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    """Distance between two (lon, lat) points in feet."""
    lon1, lat1 = math.radians(p1[0]), math.radians(p1[1])
    lon2, lat2 = math.radians(p2[0]), math.radians(p2[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * _EARTH_RADIUS_FT * math.asin(math.sqrt(max(0.0, min(1.0, a))))


def _coerce_lonlat(coord: Any) -> Optional[Tuple[float, float]]:
    """Accept (lon, lat) tuples/lists OR [lat, lon] frontend-style lists.

    Bore-log redline_segments produced by the engine store coords as
    [lat, lon] arrays (matches the Leaflet frontend), while
    route_catalog["coords"] from _build_route_catalog stores (lon, lat)
    tuples. Both shapes are handled by ordering on Brenham-area sanity
    (lon < 0, lat > 0).
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


def _route_offset_for_point(point: Tuple[float, float], route_coords: Sequence[Tuple[float, float]]) -> Optional[float]:
    """Project (lon, lat) point onto a polyline; return cumulative distance
    (feet) along the polyline to the closest projection. None if route has
    no usable geometry."""
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
        # Equirectangular projection at segment-midpoint latitude
        mid_lat_rad = math.radians((a[1] + b[1]) / 2.0)
        cos_lat = math.cos(mid_lat_rad)
        ax_ft = a[0] * 364567.2 * cos_lat
        ay_ft = a[1] * 364567.2
        bx_ft = b[0] * 364567.2 * cos_lat
        by_ft = b[1] * 364567.2
        ppx_ft = px * 364567.2 * cos_lat
        ppy_ft = py * 364567.2
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
    return best_offset


def _group_route_offset_range(group_segments: Sequence[Dict[str, Any]], route_coords: Sequence[Tuple[float, float]]) -> Optional[Tuple[float, float]]:
    """Return (min_offset_ft, max_offset_ft) covered by this group's
    segments when projected onto the route geometry, or None if no usable
    coords."""
    if not group_segments or not route_coords:
        return None
    offsets: List[float] = []
    for seg in group_segments:
        for raw in (seg or {}).get("coords") or []:
            lonlat = _coerce_lonlat(raw)
            if lonlat is None:
                continue
            off = _route_offset_for_point(lonlat, route_coords)
            if off is not None:
                offsets.append(off)
    if not offsets:
        return None
    return (min(offsets), max(offsets))


def _normalize_route_coords(coords: Sequence[Any]) -> List[Tuple[float, float]]:
    out: List[Tuple[float, float]] = []
    for raw in coords or []:
        lonlat = _coerce_lonlat(raw)
        if lonlat is not None:
            out.append(lonlat)
    return out


def _detect_same_route_collisions(
    group_matches: Sequence[Dict[str, Any]],
    route_catalog: Sequence[Dict[str, Any]],
    *,
    threshold: float = _DEFAULT_SAME_ROUTE_COLLISION_THRESHOLD,
    station_distinctness_floor: Optional[float] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Identify pairs of placed groups on the same route whose projected
    route-offset ranges overlap by >= threshold of the shorter group's
    range. Returns (collisions, window_decisions).

    `collisions` matches the pre-override schema and is what feeds the
    Anti-Collapse V1 resolver downstream.

    `window_decisions` is non-empty ONLY when station_distinctness_floor
    is not None (Collision Window V2 override active). Every
    projected-overlap pair that clears `threshold` lands in this list
    with its station-frame analysis + decision. Pairs reclassified as
    "allow_both_distinct_station_windows" are suppressed from
    `collisions`.

    Pure read-only; never mutates group_matches or route_catalog.
    """
    placed: List[Dict[str, Any]] = [
        m for m in (group_matches or [])
        if bool((m or {}).get("render_allowed"))
        and str((m or {}).get("route_id") or "").strip()
    ]
    by_route: Dict[str, List[Dict[str, Any]]] = {}
    for m in placed:
        rid = str(m.get("route_id") or "").strip()
        if rid:
            by_route.setdefault(rid, []).append(m)

    collisions: List[Dict[str, Any]] = []
    window_decisions: List[Dict[str, Any]] = []
    for rid in sorted(by_route.keys()):
        groups = by_route[rid]
        if len(groups) < 2:
            continue
        route = _route_lookup(route_catalog, rid)
        route_coords = _normalize_route_coords(route.get("coords") or [])
        if len(route_coords) < 2:
            continue

        per_group_ranges: List[Dict[str, Any]] = []
        for m in groups:
            segments = (m.get("group_redline_segments") or [])
            rng = _group_route_offset_range(segments, route_coords)
            if rng is None:
                continue
            norm = (m.get("_normalized_group") or {})
            stations = (m.get("group_station_points") or [])
            dates = sorted({str((p or {}).get("date") or "").strip() for p in stations if (p or {}).get("date")})
            crews = sorted({str((p or {}).get("crew") or "").strip() for p in stations if (p or {}).get("crew")})
            per_group_ranges.append({
                "source_file": str(m.get("source_file") or ""),
                "route_offset_range_ft": [round(rng[0], 2), round(rng[1], 2)],
                "route_offset_span_ft": round(rng[1] - rng[0], 2),
                "station_min_ft": norm.get("min_station_ft"),
                "station_max_ft": norm.get("max_station_ft"),
                "station_span_ft": norm.get("span_ft"),
                "dates": dates,
                "crews": crews,
            })

        per_group_ranges.sort(key=lambda r: (r["route_offset_range_ft"][0], r["source_file"]))

        for i in range(len(per_group_ranges)):
            a = per_group_ranges[i]
            a_lo, a_hi = a["route_offset_range_ft"]
            a_span = max(a_hi - a_lo, 0.0)
            for j in range(i + 1, len(per_group_ranges)):
                b = per_group_ranges[j]
                b_lo, b_hi = b["route_offset_range_ft"]
                b_span = max(b_hi - b_lo, 0.0)
                overlap_lo = max(a_lo, b_lo)
                overlap_hi = min(a_hi, b_hi)
                overlap_ft = max(0.0, overlap_hi - overlap_lo)
                min_span = min(a_span, b_span)
                if min_span <= 0.0:
                    continue
                overlap_ratio = overlap_ft / min_span
                if overlap_ratio < threshold:
                    continue

                collision_record = {
                    "route_id": rid,
                    "route_name": str(route.get("route_name") or ""),
                    "route_role": str(route.get("route_role") or ""),
                    "source_folder": str(route.get("source_folder") or ""),
                    "source_files": [a["source_file"], b["source_file"]],
                    "overlap_ratio": round(overlap_ratio, 4),
                    "overlap_ft": round(overlap_ft, 2),
                    "group_ranges": [
                        {
                            "source_file": a["source_file"],
                            "route_offset_ft": a["route_offset_range_ft"],
                            "route_offset_span_ft": a["route_offset_span_ft"],
                        },
                        {
                            "source_file": b["source_file"],
                            "route_offset_ft": b["route_offset_range_ft"],
                            "route_offset_span_ft": b["route_offset_span_ft"],
                        },
                    ],
                    "station_ranges": [
                        {
                            "source_file": a["source_file"],
                            "station_min_ft": a["station_min_ft"],
                            "station_max_ft": a["station_max_ft"],
                            "station_span_ft": a["station_span_ft"],
                        },
                        {
                            "source_file": b["source_file"],
                            "station_min_ft": b["station_min_ft"],
                            "station_max_ft": b["station_max_ft"],
                            "station_span_ft": b["station_span_ft"],
                        },
                    ],
                    "dates": [a["dates"], b["dates"]],
                    "crews": [a["crews"], b["crews"]],
                    "warning": (
                        f"same_route_anchor_collision_detected: {a['source_file']} and "
                        f"{b['source_file']} project onto {round(overlap_ratio * 100)}% "
                        f"overlapping ranges of {rid}"
                    ),
                }

                if station_distinctness_floor is None:
                    # Legacy path — byte-identical to pre-override behavior.
                    collisions.append(collision_record)
                    continue

                # Collision Window V2 — Station-Frame Distinctness Override.
                # Compute station-frame overlap. Pairs whose station-frame
                # ranges are disjoint (or near-disjoint) are reclassified
                # as projection artifacts: distinct field-frame work windows
                # collapsed onto the same KMZ route by the projector.
                st_overlap_ft, st_overlap_ratio = _station_overlap(
                    a["station_min_ft"], a["station_max_ft"],
                    b["station_min_ft"], b["station_max_ft"],
                )

                if st_overlap_ratio is None:
                    decision = "abstain_loser"
                    reason = "station_metadata_unavailable"
                    include_in_collisions = True
                elif st_overlap_ratio < station_distinctness_floor:
                    decision = "allow_both_distinct_station_windows"
                    reason = "station_overlap_below_distinctness_floor"
                    include_in_collisions = False
                else:
                    decision = "abstain_loser"
                    reason = "true_window_overlap"
                    include_in_collisions = True

                window_decisions.append({
                    "route_id": rid,
                    "route_name": str(route.get("route_name") or ""),
                    "source_files": [a["source_file"], b["source_file"]],
                    "projected_overlap_ft": round(overlap_ft, 2),
                    "projected_overlap_ratio": round(overlap_ratio, 4),
                    "station_overlap_ft": (
                        round(st_overlap_ft, 2) if st_overlap_ft is not None else None
                    ),
                    "station_overlap_ratio": (
                        round(st_overlap_ratio, 4) if st_overlap_ratio is not None else None
                    ),
                    "decision": decision,
                    "reason": reason,
                    # kept_group / abstained_group: resolver determines these
                    # downstream on `decision == "abstain_loser"` cases. Left
                    # as None at coverage_sanity time; operators can join
                    # against `route_collision_resolution.collision_resolutions`
                    # for the resolver verdict.
                    "kept_group": None,
                    "abstained_group": None,
                })

                if include_in_collisions:
                    collisions.append(collision_record)

    return collisions, window_decisions


def compute_coverage_sanity(
    group_matches: Sequence[Dict[str, Any]],
    route_catalog: Sequence[Dict[str, Any]],
    total_groups: int,
    *,
    overuse_min_count: int = _DEFAULT_OVERUSE_MIN_COUNT,
    overuse_share_pct: float = _DEFAULT_OVERUSE_SHARE_PCT,
    top5_collapse_threshold: float = _DEFAULT_TOP5_COLLAPSE_THRESHOLD,
    same_route_collision_threshold: float = _DEFAULT_SAME_ROUTE_COLLISION_THRESHOLD,
    station_distinctness_floor: Optional[float] = None,
) -> Dict[str, Any]:
    """Build the coverage-sanity diagnostic dict.

    Args:
      group_matches: STATE["group_matches"]-style list (each entry has
        route_id, render_allowed, group_station_points, etc.)
      route_catalog: STATE["route_catalog"]
      total_groups: total number of bore-log groups processed (= len(groups))
      overuse_min_count: a route is flagged "overused" if assigned more
        than this many groups OR more than this share of total_groups
      overuse_share_pct: see above
      top5_collapse_threshold: if top-5 routes hold >= this share of all
        placed groups, corpus is flagged as "collapse_detected"
      station_distinctness_floor: optional float in [0,1]. When provided
        (or when TRUELINE_SAME_ROUTE_WINDOW_OWNERSHIP=1 is set in env),
        activates the Collision Window V2 station-frame override:
        projected-overlap pairs whose station-frame overlap_ratio is
        below this floor are reclassified as
        "allow_both_distinct_station_windows" and dropped from the
        `same_route_anchor_collisions` list. Schema bumps to
        coverage-sanity-3 in that case; otherwise byte-identical to
        coverage-sanity-2 output.
    """
    placed = [
        m for m in (group_matches or [])
        if bool((m or {}).get("render_allowed"))
        and str((m or {}).get("route_id") or "").strip()
    ]
    placed_count = len(placed)
    abstained_count = max(0, _safe_int(total_groups) - placed_count)

    groups_per_route: Dict[str, int] = {}
    stations_per_route: Dict[str, int] = {}
    for m in placed:
        rid = str((m or {}).get("route_id") or "").strip()
        if not rid:
            continue
        groups_per_route[rid] = groups_per_route.get(rid, 0) + 1
        station_count = len((m or {}).get("group_station_points") or [])
        stations_per_route[rid] = stations_per_route.get(rid, 0) + station_count

    matched_route_count = len(groups_per_route)
    diversity_ratio = (
        matched_route_count / placed_count if placed_count else 0.0
    )

    top_by_groups = sorted(
        groups_per_route.items(), key=lambda kv: (-kv[1], kv[0])
    )[:10]
    top_by_stations = sorted(
        stations_per_route.items(), key=lambda kv: (-kv[1], kv[0])
    )[:10]

    overuse_threshold_for_corpus = max(
        overuse_min_count,
        int(_safe_int(total_groups) * overuse_share_pct),
    )
    suspicious = [
        {
            "route_id": rid,
            "assigned_group_count": cnt,
            "assigned_station_count": stations_per_route.get(rid, 0),
            "route_role": _route_role_for_id(route_catalog, rid),
        }
        for rid, cnt in groups_per_route.items()
        if cnt >= overuse_threshold_for_corpus
    ]
    suspicious.sort(key=lambda r: (-r["assigned_group_count"], r["route_id"]))

    sorted_counts = sorted(groups_per_route.values(), reverse=True)
    top5_share = (
        sum(sorted_counts[:5]) / placed_count if placed_count else 0.0
    )
    corpus_collapse_detected = bool(
        placed_count > 0 and matched_route_count > 0 and top5_share >= top5_collapse_threshold
    )

    effective_distinctness_floor = _resolve_station_distinctness_floor(
        station_distinctness_floor
    )
    same_route_collisions, same_route_window_decisions = _detect_same_route_collisions(
        group_matches,
        route_catalog,
        threshold=same_route_collision_threshold,
        station_distinctness_floor=effective_distinctness_floor,
    )
    same_route_collision_detected = bool(same_route_collisions)

    out: Dict[str, Any] = {
        "schema": "coverage-sanity-3" if effective_distinctness_floor is not None else "coverage-sanity-2",
        "total_groups": _safe_int(total_groups),
        "placed_group_count": placed_count,
        "abstained_group_count": abstained_count,
        "matched_route_count": matched_route_count,
        "diversity_ratio": round(diversity_ratio, 4),
        "top_routes_by_group_count": [
            {
                "route_id": rid,
                "assigned_group_count": cnt,
                "assigned_station_count": stations_per_route.get(rid, 0),
                "route_role": _route_role_for_id(route_catalog, rid),
            }
            for rid, cnt in top_by_groups
        ],
        "top_routes_by_station_count": [
            {
                "route_id": rid,
                "assigned_station_count": cnt,
                "assigned_group_count": groups_per_route.get(rid, 0),
                "route_role": _route_role_for_id(route_catalog, rid),
            }
            for rid, cnt in top_by_stations
        ],
        "suspicious_overuse_routes": suspicious,
        "overuse_threshold_count": overuse_threshold_for_corpus,
        "top5_share_of_placed": round(top5_share, 4),
        "top5_collapse_threshold": top5_collapse_threshold,
        "corpus_collapse_detected": corpus_collapse_detected,
        "same_route_anchor_collision_threshold": same_route_collision_threshold,
        "same_route_anchor_collision_detected": same_route_collision_detected,
        "same_route_anchor_collisions": same_route_collisions,
        "warnings": _build_warnings(
            placed_count, matched_route_count, suspicious, corpus_collapse_detected,
            same_route_collision_detected, len(same_route_collisions),
        ),
    }
    if effective_distinctness_floor is not None:
        out["same_route_window_distinctness_floor"] = effective_distinctness_floor
        out["same_route_window_decisions"] = same_route_window_decisions
    return out


def _build_warnings(
    placed_count: int,
    matched_route_count: int,
    suspicious: List[Dict[str, Any]],
    corpus_collapse_detected: bool,
    same_route_collision_detected: bool = False,
    same_route_collision_count: int = 0,
) -> List[str]:
    out: List[str] = []
    if placed_count > 0 and matched_route_count <= 5:
        out.append(
            f"low_route_diversity: {placed_count} placed groups distributed across "
            f"only {matched_route_count} routes"
        )
    if suspicious:
        out.append(
            f"route_overuse_detected: {len(suspicious)} routes assigned "
            f">= overuse threshold groups"
        )
    if corpus_collapse_detected:
        out.append(
            "corpus_collapse_detected: top-5 routes absorb >= threshold "
            "share of placed groups; investigate evidence for these placements"
        )
    if same_route_collision_detected:
        out.append(
            f"same_route_anchor_collision_detected: {same_route_collision_count} "
            f"group pair(s) project onto >= threshold overlapping ranges of the "
            f"same route; investigate stacked redlines"
        )
    return out
