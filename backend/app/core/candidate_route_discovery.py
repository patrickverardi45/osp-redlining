"""Candidate route discovery for B-MATCH-LOC-EVIDENCE-1 V3.

Given a bore-log group's notes-extracted street names plus the KMZ
address-point index plus the route catalog, deterministically discover
a trunk LineString candidate that runs through the named-street
subscriber cluster, excluding drop-tail-family folders.

Pure function; never mutates inputs; never raises on bad data (returns
None instead).

Scope (this sprint): the allowlist is constrained to LAWNDALE-bearing
notes only. HUISACHE alone and CHERI return None deterministically.
- LAWNDALE was empirically validated against the Brenham fixture: 17
  subscriber points cluster, 1 dominant trunk (route_477 Underground
  Cable, 64.7% coverage, 39.2 ft min distance).
- HUISACHE alone produced no trunk-class candidate (3 tied Vacant Pipe
  stubs, 11% coverage each — too weak to act on).
- CHERI was absent from KMZ and PDF entirely.

Heuristic thresholds match the diagnostic that motivated this sprint:
  distance_threshold_ft = 100.0
  coverage_ratio_threshold = 0.50
  excluded_folder_tokens = HOUSE DROP / FLOWER POT / TERMINAL TAIL

A dominant candidate is one whose neighborhood coverage strictly exceeds
the second-best candidate's coverage AND meets the absolute thresholds.
If two candidates tie, discovery returns None (ambiguous — abstain).
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence

# Brenham latitude approximation. KMZ truth is WGS84 lon/lat; we approximate
# planar distance using equirectangular projection at this latitude. Within
# the Brenham project area the per-degree-foot constants vary by < 0.1%.
_BRENHAM_LAT_DEG = 30.155
_FT_PER_DEG_LAT = 364567.2
_FT_PER_DEG_LON = _FT_PER_DEG_LAT * math.cos(math.radians(_BRENHAM_LAT_DEG))

# LAWNDALE-only allowlist. HUISACHE alone returns None (insufficient
# evidence per the diagnostic). CHERI returns None (no KMZ/PDF data).
_ALLOWED_STREETS = frozenset({"LAWNDALE", "LAWNDALE AVE", "LAWNDALE AVENUE"})

_DEFAULT_EXCLUDED_FOLDER_TOKENS = ("HOUSE DROP", "FLOWER POT", "TERMINAL TAIL")
_DEFAULT_DISTANCE_THRESHOLD_FT = 100.0
_DEFAULT_COVERAGE_RATIO_THRESHOLD = 0.50


def _normalize_street(value: Any) -> str:
    text = str(value or "").strip().upper()
    if not text:
        return ""
    parts = text.split()
    return " ".join(parts)


def _lonlat_to_xy_ft(lon: float, lat: float, lon0: float, lat0: float) -> tuple:
    return ((lon - lon0) * _FT_PER_DEG_LON, (lat - lat0) * _FT_PER_DEG_LAT)


def _point_to_segment_ft(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    abx, aby = bx - ax, by - ay
    apx, apy = px - ax, py - ay
    seg2 = abx * abx + aby * aby
    if seg2 < 1e-9:
        return math.hypot(apx, apy)
    t = max(0.0, min(1.0, (apx * abx + apy * aby) / seg2))
    cx, cy = ax + t * abx, ay + t * aby
    return math.hypot(px - cx, py - cy)


def _street_matches_allowlist(notes_streets: Sequence[str]) -> bool:
    for street in notes_streets or []:
        norm = _normalize_street(street)
        if norm in _ALLOWED_STREETS:
            return True
    return False


def _addr_street_matches_allowlist(address_street: str) -> bool:
    norm = _normalize_street(address_street)
    if not norm:
        return False
    if norm in _ALLOWED_STREETS:
        return True
    # KMZ subscriber points use "Lawndale Avenue" full form; accept if any
    # allowlist token is a prefix of the normalized address street.
    for allow in _ALLOWED_STREETS:
        if norm.startswith(allow + " ") or norm == allow:
            return True
    return False


def discover_candidate_routes_from_notes_streets(
    notes_streets: Sequence[str],
    address_points: Sequence[Dict[str, Any]],
    route_catalog: Sequence[Dict[str, Any]],
    *,
    distance_threshold_ft: float = _DEFAULT_DISTANCE_THRESHOLD_FT,
    coverage_ratio_threshold: float = _DEFAULT_COVERAGE_RATIO_THRESHOLD,
    excluded_folder_tokens: Sequence[str] = _DEFAULT_EXCLUDED_FOLDER_TOKENS,
) -> Optional[Dict[str, Any]]:
    """Discover a candidate route_id from KMZ address-point clusters.

    Returns None when no candidate can be deterministically identified.
    Returns a discovery dict only when a single dominant non-drop trunk
    LineString covers >= coverage_ratio_threshold of the matched
    address-point cluster within distance_threshold_ft.
    """
    if not _street_matches_allowlist(notes_streets):
        return None
    if not address_points or not route_catalog:
        return None

    cluster = [
        p for p in address_points
        if _addr_street_matches_allowlist(p.get("street_name") or "")
    ]
    if not cluster:
        return None

    excluded_upper = tuple(tok.upper() for tok in excluded_folder_tokens)
    lon0 = sum(p["lon"] for p in cluster) / len(cluster)
    lat0 = sum(p["lat"] for p in cluster) / len(cluster)
    cluster_xy = [_lonlat_to_xy_ft(p["lon"], p["lat"], lon0, lat0) for p in cluster]
    cluster_size = len(cluster_xy)

    scored_routes: List[Dict[str, Any]] = []
    for route in route_catalog:
        folder = str(route.get("source_folder") or "").upper()
        if any(tok in folder for tok in excluded_upper):
            continue
        coords = route.get("coords") or []
        if len(coords) < 2:
            continue
        route_xy = [_lonlat_to_xy_ft(c[0], c[1], lon0, lat0) for c in coords]
        coverage_count = 0
        min_distance = float("inf")
        for px, py in cluster_xy:
            best_d = float("inf")
            for i in range(len(route_xy) - 1):
                d = _point_to_segment_ft(
                    px, py,
                    route_xy[i][0], route_xy[i][1],
                    route_xy[i + 1][0], route_xy[i + 1][1],
                )
                if d < best_d:
                    best_d = d
            if best_d <= distance_threshold_ft:
                coverage_count += 1
            if best_d < min_distance:
                min_distance = best_d
        scored_routes.append({
            "route_id": route.get("route_id"),
            "route_name": route.get("route_name"),
            "source_folder": route.get("source_folder"),
            "coverage_count": coverage_count,
            "coverage_ratio": coverage_count / cluster_size if cluster_size else 0.0,
            "min_distance_ft": round(min_distance, 2),
        })

    scored_routes.sort(
        key=lambda r: (-r["coverage_count"], r["min_distance_ft"], str(r["route_id"]))
    )

    if not scored_routes:
        return None

    top = scored_routes[0]
    if top["coverage_ratio"] < coverage_ratio_threshold:
        return None
    if top["coverage_count"] <= 0:
        return None
    # Dominance gate: top must STRICTLY exceed the second candidate's
    # coverage (otherwise ambiguous → abstain).
    if len(scored_routes) > 1 and scored_routes[1]["coverage_count"] >= top["coverage_count"]:
        return None

    return {
        "source": "kmz_point_to_linestring_proximity",
        "notes_streets": [str(s) for s in (notes_streets or [])],
        "discovered_route_ids": [top["route_id"]],
        "evidence": {
            "point_count": cluster_size,
            "coverage_count": top["coverage_count"],
            "coverage_ratio": round(top["coverage_ratio"], 4),
            "distance_threshold_ft": distance_threshold_ft,
            "nearest_distance_ft": top["min_distance_ft"],
            "route_name": top["route_name"],
            "source_folder": top["source_folder"],
        },
    }
