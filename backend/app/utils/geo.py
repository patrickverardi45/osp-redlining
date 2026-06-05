"""Pure geo / route-geometry helpers extracted from backend/main.py (PR-1 cleanup).

Behavior-preserving: these are the EXACT functions previously defined inline in main.py
(`_haversine_feet`, `_route_length_ft`, `_route_bbox`). main.py now imports them by the SAME
names so every call site is unchanged. Pure stdlib math — no STATE, no I/O, no import of
``backend.main`` (no cycle).
"""
from __future__ import annotations

import math
from typing import Dict, Optional, Sequence


def _haversine_feet(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r_m = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r_m * c * 3.28084


def _route_length_ft(coords: Sequence[Sequence[float]]) -> float:
    total = 0.0
    for i in range(1, len(coords)):
        total += _haversine_feet(
            float(coords[i - 1][0]),
            float(coords[i - 1][1]),
            float(coords[i][0]),
            float(coords[i][1]),
        )
    return total


def _route_bbox(coords: Sequence[Sequence[float]]) -> Optional[Dict[str, float]]:
    if not coords:
        return None
    lats = [float(pt[0]) for pt in coords if len(pt) >= 2]
    lons = [float(pt[1]) for pt in coords if len(pt) >= 2]
    if not lats or not lons:
        return None
    return {
        "min_lat": min(lats),
        "max_lat": max(lats),
        "min_lon": min(lons),
        "max_lon": max(lons),
    }
