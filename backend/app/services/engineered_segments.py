"""V1 ENGINEERED PATH derived layer.

Backend-only, isolated, zero-side-effect module that converts a session's
station inputs + KMZ route into a clean "engineered_segments" array. This is
the alternative to rendering raw GPS breadcrumbs as the primary path.

Nothing in this module mutates session state, files, the database, or any
existing endpoint. It is not wired into any FastAPI route. It is intentionally
not imported by ``backend/main.py`` — callers must import it explicitly when
they are ready to use it.

Public surface
--------------
- ``project_point_to_route(lat, lon, route_coords)``
- ``build_engineered_segments_from_inputs(...)``
- ``build_engineered_segments(session_id)``

Coordinate conventions
----------------------
- ``route_coords`` matches the existing ``STATE["route_coords"]`` layout in
  ``backend/main.py``: a list of ``[lat, lon]`` pairs (lat first).
- Returned GeoJSON ``geometry.coordinates`` follow the GeoJSON spec
  (``[lon, lat]``), so the frontend can hand them straight to mapping libs
  later without re-ordering.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# Tunables. Kept as module-level constants so they can be overridden by future
# callers without changing the projection math.
# ---------------------------------------------------------------------------

DEFAULT_MAX_OFFSET_FT = 50.0  # projection offset above which we fall back to a straight line
HIGH_CONFIDENCE_OFFSET_FT = 25.0  # both endpoints under this -> "high" confidence
MEDIUM_CONFIDENCE_OFFSET_FT = 50.0  # both endpoints under this -> "medium" confidence


# ---------------------------------------------------------------------------
# Local geometry helpers. These mirror the formulas already in backend/main.py
# (_haversine_feet, _latlon_to_local_xy_feet, _project_point_to_segment_ft,
# _route_chainage, _interpolate_point, _point_at_distance, _clip_route_segment)
# so this module has no dependency on main and no risk of introducing an
# import cycle.
# ---------------------------------------------------------------------------


def _haversine_feet(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r_m = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r_m * c * 3.28084


def _latlon_to_local_xy_feet(lat: float, lon: float, lat0: float, lon0: float) -> Tuple[float, float]:
    # Equirectangular tangent plane in feet around (lat0, lon0). 1 deg lat ~= 364,000 ft.
    lat_scale = 364000.0
    lon_scale = 364000.0 * math.cos(math.radians(lat0))
    x = (lon - lon0) * lon_scale
    y = (lat - lat0) * lat_scale
    return x, y


def _route_chainage(coords: Sequence[Sequence[float]]) -> List[float]:
    chainage = [0.0]
    for i in range(1, len(coords)):
        chainage.append(
            chainage[-1]
            + _haversine_feet(
                float(coords[i - 1][0]),
                float(coords[i - 1][1]),
                float(coords[i][0]),
                float(coords[i][1]),
            )
        )
    return chainage


def _project_point_to_segment(
    px: float, py: float, ax: float, ay: float, bx: float, by: float
) -> Tuple[float, float, float, float]:
    """Project (px,py) onto segment (a,b) in local feet. Returns (t, qx, qy, dist_ft).
    ``t`` is clamped to [0,1] so endpoints can't escape the segment."""
    dx = bx - ax
    dy = by - ay
    seg_len_sq = dx * dx + dy * dy
    if seg_len_sq <= 1e-9:
        return 0.0, ax, ay, math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / seg_len_sq
    if t < 0.0:
        t = 0.0
    elif t > 1.0:
        t = 1.0
    qx = ax + t * dx
    qy = ay + t * dy
    return t, qx, qy, math.hypot(px - qx, py - qy)


def _interpolate_latlon(a: Sequence[float], b: Sequence[float], ratio: float) -> Tuple[float, float]:
    r = max(0.0, min(1.0, float(ratio)))
    return (
        float(a[0]) + (float(b[0]) - float(a[0])) * r,
        float(a[1]) + (float(b[1]) - float(a[1])) * r,
    )


def _point_at_distance(
    route_coords: Sequence[Sequence[float]],
    chainage: Sequence[float],
    distance_ft: float,
) -> Tuple[float, float]:
    if not route_coords:
        raise ValueError("Route is empty.")
    if len(route_coords) == 1:
        return float(route_coords[0][0]), float(route_coords[0][1])
    total = float(chainage[-1])
    d = max(0.0, min(float(distance_ft), total))
    for idx in range(1, len(chainage)):
        seg_start = float(chainage[idx - 1])
        seg_end = float(chainage[idx])
        if d <= seg_end or idx == len(chainage) - 1:
            seg_len = max(seg_end - seg_start, 1e-9)
            return _interpolate_latlon(
                route_coords[idx - 1], route_coords[idx], (d - seg_start) / seg_len
            )
    last = route_coords[-1]
    return float(last[0]), float(last[1])


def _clip_route_substring(
    route_coords: Sequence[Sequence[float]],
    chainage: Sequence[float],
    start_ft: float,
    end_ft: float,
) -> List[List[float]]:
    """Return polyline between two distances along the route as ``[[lon,lat],...]``
    (GeoJSON order). Returns ``[]`` if the inputs collapse."""
    if len(route_coords) < 2:
        return []
    total = float(chainage[-1])
    start_d = max(0.0, min(float(start_ft), total))
    end_d = max(0.0, min(float(end_ft), total))
    if end_d <= start_d:
        return []

    start_lat, start_lon = _point_at_distance(route_coords, chainage, start_d)
    end_lat, end_lon = _point_at_distance(route_coords, chainage, end_d)

    pts_latlon: List[Tuple[float, float]] = [(start_lat, start_lon)]
    for idx in range(1, len(chainage) - 1):
        d = float(chainage[idx])
        if start_d < d < end_d:
            pts_latlon.append((float(route_coords[idx][0]), float(route_coords[idx][1])))
    pts_latlon.append((end_lat, end_lon))

    out: List[List[float]] = []
    for lat, lon in pts_latlon:
        # GeoJSON wants [lon, lat]
        if not out or abs(out[-1][0] - lon) > 1e-9 or abs(out[-1][1] - lat) > 1e-9:
            out.append([lon, lat])
    return out if len(out) >= 2 else []


# ---------------------------------------------------------------------------
# Projection
# ---------------------------------------------------------------------------


def project_point_to_route(
    lat: float,
    lon: float,
    route_coords: Sequence[Sequence[float]],
) -> Optional[Dict[str, Any]]:
    """Find the closest point on the KMZ polyline to ``(lat, lon)``.

    Returns ``None`` if the route is empty or coords are unparseable. Otherwise
    returns:

        {
            "lat":               <closest point on route>,
            "lon":               <closest point on route>,
            "distance_along_ft": <distance along the route to the closest point>,
            "fraction":          <distance_along_ft / total_route_length, in [0,1]>,
            "offset_ft":         <perpendicular distance from station to route>,
            "segment_index":     <which polyline segment the closest point lies on>,
        }
    """
    if not route_coords or len(route_coords) < 2:
        return None
    try:
        plat = float(lat)
        plon = float(lon)
    except (TypeError, ValueError):
        return None

    chainage = _route_chainage(route_coords)
    total_ft = float(chainage[-1]) if chainage else 0.0
    if total_ft <= 0.0:
        return None

    # Anchor the local tangent plane at the route's first vertex. Acceptable for
    # walk-scale routes (<< a few miles); identical to what main.py does.
    lat0 = float(route_coords[0][0])
    lon0 = float(route_coords[0][1])
    px, py = _latlon_to_local_xy_feet(plat, plon, lat0, lon0)

    best_segment = 0
    best_t = 0.0
    best_dist_ft = float("inf")
    best_q_ft: Tuple[float, float] = (0.0, 0.0)

    for i in range(1, len(route_coords)):
        ax, ay = _latlon_to_local_xy_feet(
            float(route_coords[i - 1][0]), float(route_coords[i - 1][1]), lat0, lon0
        )
        bx, by = _latlon_to_local_xy_feet(
            float(route_coords[i][0]), float(route_coords[i][1]), lat0, lon0
        )
        t, qx, qy, dist_ft = _project_point_to_segment(px, py, ax, ay, bx, by)
        if dist_ft < best_dist_ft:
            best_dist_ft = dist_ft
            best_segment = i - 1
            best_t = t
            best_q_ft = (qx, qy)

    seg_start_ft = float(chainage[best_segment])
    seg_end_ft = float(chainage[best_segment + 1])
    distance_along_ft = seg_start_ft + best_t * (seg_end_ft - seg_start_ft)

    closest_lat, closest_lon = _interpolate_latlon(
        route_coords[best_segment], route_coords[best_segment + 1], best_t
    )

    # Cross-check the closest-point lat/lon vs the local-XY projection to bound
    # rounding error from the equirectangular approximation.
    haversine_offset_ft = _haversine_feet(plat, plon, closest_lat, closest_lon)
    offset_ft = max(best_dist_ft, haversine_offset_ft)

    return {
        "lat": float(closest_lat),
        "lon": float(closest_lon),
        "distance_along_ft": float(distance_along_ft),
        "fraction": float(distance_along_ft / total_ft) if total_ft > 0.0 else 0.0,
        "offset_ft": float(offset_ft),
        "segment_index": int(best_segment),
    }


# ---------------------------------------------------------------------------
# Station normalization
# ---------------------------------------------------------------------------


def _coerce_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def _normalize_station(raw: Dict[str, Any], fallback_index: int) -> Optional[Dict[str, Any]]:
    """Coerce one station-like dict into a stable shape regardless of whether it
    came from ``STATE["station_points"]`` (office) or ``STATE["walk_station_events"]``
    (field). Returns ``None`` if it lacks usable coordinates."""
    if not isinstance(raw, dict):
        return None
    lat = _coerce_float(raw.get("lat") if "lat" in raw else raw.get("latitude"))
    lon = _coerce_float(raw.get("lon") if "lon" in raw else raw.get("longitude"))
    if lat is None or lon is None:
        return None
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        return None

    station_id = (
        str(
            raw.get("station_id")
            or raw.get("id")
            or raw.get("station_number")
            or raw.get("station")
            or raw.get("station_label")
            or f"station_{fallback_index}"
        ).strip()
        or f"station_{fallback_index}"
    )
    label = str(
        raw.get("station")
        or raw.get("station_label")
        or raw.get("station_number")
        or station_id
    ).strip()
    station_ft = _coerce_float(raw.get("station_ft"))

    return {
        "station_id": station_id,
        "label": label,
        "lat": lat,
        "lon": lon,
        "station_ft": station_ft,
        "_order": fallback_index,
    }


def _sort_stations_for_segments(
    stations: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Sort by ``station_ft`` if every station has it, else keep input order."""
    normalized: List[Dict[str, Any]] = []
    for idx, raw in enumerate(stations or []):
        st = _normalize_station(raw, idx)
        if st is not None:
            normalized.append(st)

    if normalized and all(s.get("station_ft") is not None for s in normalized):
        normalized.sort(key=lambda s: (float(s["station_ft"]), s["_order"]))
    else:
        normalized.sort(key=lambda s: s["_order"])
    return normalized


# ---------------------------------------------------------------------------
# Segment construction
# ---------------------------------------------------------------------------


def _straight_line_segment(
    session_id: str,
    a: Dict[str, Any],
    b: Dict[str, Any],
    warnings: List[str],
    confidence: str = "low",
) -> Dict[str, Any]:
    geom_coords = [[a["lon"], a["lat"]], [b["lon"], b["lat"]]]
    station_distance_ft = _haversine_feet(a["lat"], a["lon"], b["lat"], b["lon"])
    return {
        "session_id": session_id,
        "from_station_id": a["station_id"],
        "to_station_id": b["station_id"],
        "method": "station_straight",
        "geometry": {"type": "LineString", "coordinates": geom_coords},
        "from_fraction": None,
        "to_fraction": None,
        "route_distance_ft": None,
        "station_distance_ft": float(station_distance_ft),
        "confidence": confidence,
        "warnings": list(warnings),
    }


def _route_substring_segment(
    session_id: str,
    a: Dict[str, Any],
    b: Dict[str, Any],
    proj_a: Dict[str, Any],
    proj_b: Dict[str, Any],
    route_coords: Sequence[Sequence[float]],
    chainage: Sequence[float],
    warnings: List[str],
) -> Optional[Dict[str, Any]]:
    start_ft = float(proj_a["distance_along_ft"])
    end_ft = float(proj_b["distance_along_ft"])
    if end_ft <= start_ft:
        return None
    geom_coords = _clip_route_substring(route_coords, chainage, start_ft, end_ft)
    if len(geom_coords) < 2:
        return None

    offset_a = float(proj_a["offset_ft"])
    offset_b = float(proj_b["offset_ft"])
    worst = max(offset_a, offset_b)
    if worst <= HIGH_CONFIDENCE_OFFSET_FT:
        confidence = "high"
    elif worst <= MEDIUM_CONFIDENCE_OFFSET_FT:
        confidence = "medium"
    else:
        confidence = "low"

    station_distance_ft = _haversine_feet(a["lat"], a["lon"], b["lat"], b["lon"])

    return {
        "session_id": session_id,
        "from_station_id": a["station_id"],
        "to_station_id": b["station_id"],
        "method": "route_substring",
        "geometry": {"type": "LineString", "coordinates": geom_coords},
        "from_fraction": float(proj_a["fraction"]),
        "to_fraction": float(proj_b["fraction"]),
        "route_distance_ft": float(end_ft - start_ft),
        "station_distance_ft": float(station_distance_ft),
        "confidence": confidence,
        "warnings": list(warnings),
    }


def build_engineered_segments_from_inputs(
    *,
    stations: Sequence[Dict[str, Any]],
    route_coords: Sequence[Sequence[float]],
    session_id: str,
    max_offset_ft: float = DEFAULT_MAX_OFFSET_FT,
) -> List[Dict[str, Any]]:
    """Pure function: derive engineered segments from already-loaded inputs.

    No I/O, no global state. This is the unit-testable core that
    ``build_engineered_segments`` wraps once the session has been resolved.
    """
    sid = str(session_id or "").strip() or "unknown"
    sorted_stations = _sort_stations_for_segments(stations)
    if len(sorted_stations) < 2:
        return []

    has_route = bool(route_coords) and len(route_coords) >= 2
    chainage = _route_chainage(route_coords) if has_route else []
    if has_route and (not chainage or chainage[-1] <= 0.0):
        has_route = False  # collapsed/zero-length route -> always fall back

    segments: List[Dict[str, Any]] = []

    for i in range(1, len(sorted_stations)):
        a = sorted_stations[i - 1]
        b = sorted_stations[i]
        warnings: List[str] = []

        if not has_route:
            warnings.append("missing_route")
            segments.append(_straight_line_segment(sid, a, b, warnings, confidence="low"))
            continue

        proj_a = project_point_to_route(a["lat"], a["lon"], route_coords)
        proj_b = project_point_to_route(b["lat"], b["lon"], route_coords)
        if proj_a is None or proj_b is None:
            warnings.append("projection_failed")
            segments.append(_straight_line_segment(sid, a, b, warnings, confidence="low"))
            continue

        if proj_a["offset_ft"] > max_offset_ft:
            warnings.append("projection_offset_high_from")
        if proj_b["offset_ft"] > max_offset_ft:
            warnings.append("projection_offset_high_to")
        if proj_a["distance_along_ft"] >= proj_b["distance_along_ft"]:
            warnings.append("non_monotonic_projection")

        substring = None
        if (
            proj_a["offset_ft"] <= max_offset_ft
            and proj_b["offset_ft"] <= max_offset_ft
            and proj_a["distance_along_ft"] < proj_b["distance_along_ft"]
        ):
            substring = _route_substring_segment(
                sid, a, b, proj_a, proj_b, route_coords, chainage, warnings
            )

        if substring is not None:
            segments.append(substring)
        else:
            # Carry the projection diagnostics into the fallback so reviewers
            # can see why we straight-lined this pair.
            segments.append(_straight_line_segment(sid, a, b, warnings, confidence="low"))

    return segments


# ---------------------------------------------------------------------------
# Session-aware wrapper. Not registered as a route. Reads from main.py's
# in-memory _SESSIONS via lazy import to avoid any top-level coupling.
# ---------------------------------------------------------------------------


def _read_session_inputs(session_id: str) -> Tuple[List[Dict[str, Any]], List[List[float]]]:
    """Pull (stations, route_coords) for the given session_id.

    Lazy-imports ``backend.main`` so this module remains decoupled at import
    time. Returns ``([], [])`` if the session is unknown — callers get an empty
    segment list rather than an exception.

    Stations resolve in this priority order:

      1. ``walk_station_events`` (field-collected) — preferred when the walk
         is the source of truth for station positions.
      2. ``station_points``      (office-side) — fallback for sessions that
         haven't walked yet.
    """
    sid = str(session_id or "").strip()
    if not sid:
        return [], []

    try:
        # Local import: avoids circular import risk and keeps this module
        # importable in isolation (e.g. unit tests).
        from backend import main as _m  # type: ignore
    except Exception:
        try:
            import main as _m  # type: ignore
        except Exception:
            return [], []

    sessions = getattr(_m, "_SESSIONS", None)
    lock = getattr(_m, "_SESSION_LOCK", None)

    def _snapshot() -> Tuple[List[Dict[str, Any]], List[List[float]]]:
        if not isinstance(sessions, dict):
            return [], []
        session = sessions.get(sid)
        if not isinstance(session, dict):
            return [], []
        walk_events = session.get("walk_station_events") or []
        station_points = session.get("station_points") or []
        stations: List[Dict[str, Any]] = []
        if isinstance(walk_events, list) and walk_events:
            stations = [dict(ev) for ev in walk_events if isinstance(ev, dict)]
        if not stations and isinstance(station_points, list):
            stations = [dict(p) for p in station_points if isinstance(p, dict)]
        route_coords_raw = session.get("route_coords") or []
        route_coords: List[List[float]] = []
        if isinstance(route_coords_raw, list):
            for pt in route_coords_raw:
                if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                    try:
                        route_coords.append([float(pt[0]), float(pt[1])])
                    except (TypeError, ValueError):
                        continue
        return stations, route_coords

    if lock is not None and hasattr(lock, "acquire") and hasattr(lock, "release"):
        lock.acquire()
        try:
            return _snapshot()
        finally:
            lock.release()
    return _snapshot()


def build_engineered_segments(session_id: str) -> List[Dict[str, Any]]:
    """Top-level entry point requested by the V1 spec.

    Reads stations + KMZ route for ``session_id``, projects each station onto
    the route, and emits an array of engineered segments in the documented
    shape. **Read-only**: never mutates session state, never writes to disk,
    never touches GPS breadcrumbs.
    """
    stations, route_coords = _read_session_inputs(session_id)
    return build_engineered_segments_from_inputs(
        stations=stations,
        route_coords=route_coords,
        session_id=session_id,
    )


__all__ = [
    "DEFAULT_MAX_OFFSET_FT",
    "HIGH_CONFIDENCE_OFFSET_FT",
    "MEDIUM_CONFIDENCE_OFFSET_FT",
    "project_point_to_route",
    "build_engineered_segments_from_inputs",
    "build_engineered_segments",
]
