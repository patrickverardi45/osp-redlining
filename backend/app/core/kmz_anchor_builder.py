"""KMZ Hardening Stage R2a — station-anchor builder.

Pure helper that collects the KMZ Point placemarks with already-extracted
``chainage_ft`` and projects them onto a route polyline to produce a
deterministic list of ``(station_ft, (lon, lat))`` anchors. The output list
matches the contract of R1's
``kmz_auto_redline.generate_kmz_auto_redline_segments(request)``
``station_anchors_lonlat`` field, byte-for-byte.

**R2a is OBSERVATION ONLY.** This module never mutates routing state, never
invokes the matching engine, never wires anchors into R1, never persists
segments, never touches the hero map. Its only job is "given this route +
the already-built kmz_semantic features, here are the anchor candidates I
trust, with their per-anchor + per-route confidence."

Hard contracts (mirror PDF E3 + KMZ B2b + R1 doctrine):

* Pure helper. No STATE. No env reads. No main-module imports. No I/O.
* No PyMuPDF. No KMZ parsing (``kmz_semantic_features`` is the caller's
  already-parsed list from ``STATE["kmz_semantic"]["features"]``).
* No AI/LLM. Anchor confidence = deterministic rules on classification +
  semantic_confidence + chainage_source + perpendicular distance.
* No PDF dependency. R2a does not import any pdf_* module.
* Deterministic: same inputs -> byte-identical output (including the order
  of ``anchor_records``).
* Bounded: ``_MAX_ANCHORS_PER_ROUTE = 200``, ``_MAX_REJECTED_FEATURES = 5_000``.
* Abstain-when-uncertain: returns an empty ``station_anchors_lonlat`` with
  diagnostics rather than fabricating anchors.

Schema version: ``kmz-anchor-builder-1``.

Authoritative design: ``wiki/sprints/kmz-r/r2-anchor-builder-design.md``.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Final, List, Optional, Sequence, Tuple


SCHEMA_VERSION: Final[str] = "kmz-anchor-builder-1"
PARAMETERS_VERSION: Final[str] = "v1"

# Per-list safety caps (§4.4).
_MAX_ANCHORS_PER_ROUTE: Final[int] = 200
_MAX_REJECTED_FEATURES: Final[int] = 5_000

# Anchor-eligible classification set (§4.3 step 2). Mirrors the existing
# ``_ANCHOR_KINDS`` constant at ``backend/main.py:2536`` exactly.
_ANCHOR_KINDS_R2: Final[frozenset] = frozenset(
    {"station_label", "handhole", "structure_marker", "reel"}
)

# Proximity filter cap (§4.3 step 4). Candidates farther than this from the
# route polyline are rejected; placemarks half a mile off-route are not
# anchors for that route.
_MAX_PROXIMITY_M: Final[float] = 100.0

# Per-anchor confidence thresholds (§4.5).
_ANCHOR_HIGH_PERP_M: Final[float] = 5.0
_ANCHOR_MEDIUM_PERP_M: Final[float] = 25.0

# Per-route confidence thresholds (§4.6).
_ROUTE_HIGH_PERP_M_CAP: Final[float] = 10.0
_ROUTE_HIGH_SPAN_FT: Final[float] = 200.0
_ROUTE_MEDIUM_SPAN_FT: Final[float] = 50.0

# Dedupe + sanity tolerances.
_STATION_FT_DEDUPE_TOLERANCE: Final[float] = 1.0
_MAX_REASONABLE_STATION_FT: Final[float] = 1_000_000.0

# Distance constants (match coverage_sanity.py + R1 helper).
_EARTH_RADIUS_FT: Final[float] = 20902231.0
_FT_PER_METER: Final[float] = 3.280839895013123
_FT_PER_DEGREE_LAT: Final[float] = 364567.2

_FLOAT_DECIMALS: Final[int] = 6
_FT_DECIMALS: Final[int] = 3


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class KmzAnchorBuilderError(Exception):
    """Raised on caller-side bugs (request not a dict, missing route_id,
    empty polyline). Per-feature failures (no chainage, wrong classification,
    out-of-range station, dedupe loss, etc.) do NOT raise; they surface in
    ``rejected_features[]``.
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


def _coerce_lonlat_pair(pair: Any) -> Optional[Tuple[float, float]]:
    """Accept ``(lon, lat)``, ``[lon, lat]``, OR ``[lat, lon]`` (frontend-style)
    and return canonical ``(lon, lat)``.

    Internal TrueLine coords are inconsistent: ``_build_route_catalog`` and
    ``_extract_point_coords`` return ``[lat, lon]`` (Leaflet-style), while
    PDF E3 + R1 helper assume ``(lon, lat)``. R2a is the integration point,
    so it accepts both and disambiguates by hemisphere — same heuristic as
    ``coverage_sanity._coerce_lonlat``. Brenham operates in
    ``lat in (0, 90), lon in (-180, 0)`` so the swap is deterministic.
    """
    if pair is None:
        return None
    if not isinstance(pair, (list, tuple)) or len(pair) < 2:
        return None
    try:
        a = float(pair[0])
        b = float(pair[1])
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(a) and math.isfinite(b)):
        return None
    if a < 0 and 0 < b < 90:        # (lon, lat) — return as-is
        return (a, b)
    if 0 < a < 90 and b < 0:         # [lat, lon] — swap
        return (b, a)
    return (a, b)                    # ambiguous — return positional as-is


# ---------------------------------------------------------------------------
# Geodesic primitives (mirror coverage_sanity + R1)
# ---------------------------------------------------------------------------

def _haversine_ft(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    """Great-circle distance between two ``(lon, lat)`` points, feet."""
    lon1, lat1 = math.radians(p1[0]), math.radians(p1[1])
    lon2, lat2 = math.radians(p2[0]), math.radians(p2[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * _EARTH_RADIUS_FT * math.asin(math.sqrt(max(0.0, min(1.0, a))))


def _polyline_cum_lengths_ft(polyline: Sequence[Tuple[float, float]]) -> List[float]:
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
    tangent projection per segment, matching R1's exact pattern."""
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


# ---------------------------------------------------------------------------
# Per-feature candidate extraction
# ---------------------------------------------------------------------------

def _extract_point_lonlat_from_feature(feature: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    """Best-effort lon/lat extractor for a kmz_semantic feature whose
    ``geometry_type == "Point"``. The canonical source is
    ``feature["full_geometry"]["coord"]`` which is ``[lat, lon]``
    (see ``_kmz_semantic_extract_full_geometry`` in ``main.py``). We coerce
    through ``_coerce_lonlat_pair`` to land on canonical ``(lon, lat)``.

    Returns ``None`` when no usable coord is present.
    """
    full_geom = feature.get("full_geometry")
    if isinstance(full_geom, dict) and full_geom.get("kind") == "Point":
        coord = full_geom.get("coord")
        coerced = _coerce_lonlat_pair(coord)
        if coerced is not None:
            return coerced
    # Defensive fallback: some feature shapes may carry ``coords_hint``
    # or direct lat/lon. R2a does not require this fallback but accepts
    # ``{"lat": ..., "lon": ...}`` shape if present (e.g., feature
    # originating from ``kmz_reference.point_features``).
    if "lat" in feature and "lon" in feature:
        try:
            return (float(feature["lon"]), float(feature["lat"]))
        except (TypeError, ValueError):
            return None
    return None


def _classify_anchor_confidence(
    *,
    classification: str,
    semantic_confidence: str,
    chainage_source: str,
    perp_distance_m: float,
) -> str:
    """Per-anchor confidence grade. §4.5 of the R2 design packet."""
    if (
        classification in {"station_label", "handhole"}
        and semantic_confidence in {"medium", "high"}
        and chainage_source == "name"
        and perp_distance_m <= _ANCHOR_HIGH_PERP_M
    ):
        return "high"
    if (
        classification in {"station_label", "handhole", "structure_marker"}
        and perp_distance_m <= _ANCHOR_MEDIUM_PERP_M
    ):
        return "medium"
    return "low"


def _classify_route_confidence(anchor_records: Sequence[Dict[str, Any]]) -> str:
    """Per-route confidence grade. §4.6 of the R2 design packet."""
    if not anchor_records:
        return "abstain"
    high_count = sum(1 for a in anchor_records if a.get("anchor_confidence") == "high")
    medium_or_better = sum(
        1 for a in anchor_records
        if a.get("anchor_confidence") in {"high", "medium"}
    )
    stations = [a["station_ft"] for a in anchor_records]
    span_ft = max(stations) - min(stations) if len(stations) >= 2 else 0.0
    perps_m = [a.get("perp_distance_m", float("inf")) for a in anchor_records]
    max_perp_m = max(perps_m) if perps_m else float("inf")

    if (
        high_count >= 2
        and span_ft >= _ROUTE_HIGH_SPAN_FT
        and max_perp_m <= _ROUTE_HIGH_PERP_M_CAP
    ):
        return "high"
    if medium_or_better >= 2 and span_ft >= _ROUTE_MEDIUM_SPAN_FT:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def generate_kmz_station_anchors(
    request: Dict[str, Any],
) -> Dict[str, Any]:
    """Derive a list of station anchors for the given route polyline by
    filtering and projecting the already-built KMZ semantic features.

    Mirrors the R1 / PDF E3 caller contract: pure helper, no STATE, no env,
    no I/O, no main-module imports, deterministic output.

    Raises ``KmzAnchorBuilderError`` ONLY on caller-side bugs (request not
    a dict, missing route_id, empty polyline). Per-feature failures land
    in ``rejected_features[]``.

    Returns a dict matching the ``KmzAnchorBuilderResponse`` schema:
    ``schema_version``, ``parameters_version``, ``route_id``,
    ``station_anchors_lonlat``, ``anchor_records``, ``rejected_features``,
    ``diagnostics``.

    The ``station_anchors_lonlat`` field is the exact shape R1 expects in
    its ``KmzAutoRedlineRequest.station_anchors_lonlat`` slot:
    ``[(station_ft, (lon, lat)), ...]`` sorted ascending by station_ft.
    """
    # ──── Validate request shape ──────────────────────────────────────────
    if not isinstance(request, dict):
        raise KmzAnchorBuilderError(
            f"request must be a dict; got {type(request).__name__}"
        )

    route_id = _safe_str(request.get("route_id")).strip()
    if not route_id:
        raise KmzAnchorBuilderError("request.route_id is required")

    raw_polyline = request.get("route_polyline_lonlat")
    if not isinstance(raw_polyline, (list, tuple)):
        raise KmzAnchorBuilderError(
            "request.route_polyline_lonlat must be a list of (lon, lat) pairs"
        )
    polyline_coerced: List[Tuple[float, float]] = []
    for pt in raw_polyline:
        coerced = _coerce_lonlat_pair(pt)
        if coerced is not None:
            polyline_coerced.append(coerced)
    if len(polyline_coerced) < 2:
        raise KmzAnchorBuilderError(
            "request.route_polyline_lonlat must contain at least 2 valid (lon, lat) points"
        )

    semantic_features = request.get("kmz_semantic_features")
    if semantic_features is None:
        semantic_features = []
    if not isinstance(semantic_features, (list, tuple)):
        raise KmzAnchorBuilderError(
            "request.kmz_semantic_features must be a list (or absent)"
        )

    request_meta = request.get("request_meta") or {}
    if not isinstance(request_meta, dict):
        request_meta = {}

    cum_ft = _polyline_cum_lengths_ft(polyline_coerced)
    polyline_total_ft = cum_ft[-1] if cum_ft else 0.0

    # ──── Iterate, filter, project ───────────────────────────────────────
    anchor_records: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    rejection_reasons: Dict[str, int] = {}
    classification_tally: Dict[str, int] = {}

    candidate_count_pre_proximity = 0
    candidate_count_post_proximity = 0

    def _reject(feature_id: str, reason: str, rule_id: str, extra: Optional[Dict[str, Any]] = None) -> None:
        if len(rejected) >= _MAX_REJECTED_FEATURES:
            return
        row = {
            "source_feature_id": feature_id,
            "reason": reason,
            "rule_id": rule_id,
        }
        if extra:
            row.update(extra)
        rejected.append(row)
        rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1

    for feature in semantic_features:
        if not isinstance(feature, dict):
            _reject(
                "(non-dict)",
                "feature_not_a_dict",
                "kmz_anchor_builder_v1:feature_shape",
            )
            continue

        feature_id = _safe_str(feature.get("feature_id"))
        geom_type = _safe_str(feature.get("geometry_type"))
        if geom_type != "Point":
            _reject(
                feature_id,
                "non_point_geometry",
                "kmz_anchor_builder_v1:geometry_kind",
                {"geometry_type": geom_type or None},
            )
            continue

        chainage_raw = feature.get("chainage_ft")
        if chainage_raw is None:
            _reject(
                feature_id,
                "no_chainage",
                "kmz_anchor_builder_v1:chainage_present",
            )
            continue
        try:
            chainage_ft = float(chainage_raw)
        except (TypeError, ValueError):
            _reject(
                feature_id,
                "chainage_not_numeric",
                "kmz_anchor_builder_v1:chainage_format",
            )
            continue
        if not math.isfinite(chainage_ft):
            _reject(
                feature_id,
                "chainage_not_finite",
                "kmz_anchor_builder_v1:chainage_format",
            )
            continue
        if chainage_ft < 0.0 or chainage_ft > _MAX_REASONABLE_STATION_FT:
            _reject(
                feature_id,
                "chainage_out_of_range",
                "kmz_anchor_builder_v1:chainage_range",
                {"chainage_ft": chainage_ft},
            )
            continue

        classification = _safe_str(feature.get("classification"))
        if classification not in _ANCHOR_KINDS_R2:
            _reject(
                feature_id,
                "classification_not_anchor_kind",
                "kmz_anchor_builder_v1:classification",
                {"classification": classification or None},
            )
            continue

        lonlat = _extract_point_lonlat_from_feature(feature)
        if lonlat is None:
            _reject(
                feature_id,
                "missing_point_coord",
                "kmz_anchor_builder_v1:point_coord",
            )
            continue

        proj = _project_point_to_polyline_ft(lonlat, polyline_coerced, cum_ft)
        if proj is None:
            _reject(
                feature_id,
                "projection_failed",
                "kmz_anchor_builder_v1:projection",
            )
            continue
        dist_along_ft, projected_lonlat, perp_ft = proj
        perp_m = perp_ft / _FT_PER_METER

        candidate_count_pre_proximity += 1
        if perp_m > _MAX_PROXIMITY_M:
            _reject(
                feature_id,
                "perp_distance_exceeds_cap",
                "kmz_anchor_builder_v1:proximity",
                {"perp_distance_m": _rft(perp_m)},
            )
            continue
        candidate_count_post_proximity += 1

        semantic_confidence = _safe_str(feature.get("confidence")) or "low"
        chainage_source = _safe_str(feature.get("chainage_source")) or "name"
        anchor_confidence = _classify_anchor_confidence(
            classification=classification,
            semantic_confidence=semantic_confidence,
            chainage_source=chainage_source,
            perp_distance_m=perp_m,
        )

        anchor_records.append({
            "station_ft": _rft(chainage_ft),
            "lon": _r6(lonlat[0]),
            "lat": _r6(lonlat[1]),
            "projected_lonlat": [_r6(projected_lonlat[0]), _r6(projected_lonlat[1])],
            "distance_along_route_ft": _rft(dist_along_ft),
            "perp_distance_ft": _rft(perp_ft),
            "perp_distance_m": _rft(perp_m),
            "source_feature_id": feature_id,
            "placemark_name": _safe_str(feature.get("placemark_name")),
            "classification": classification,
            "chainage_source": chainage_source,
            "semantic_confidence": semantic_confidence,
            "anchor_confidence": anchor_confidence,
        })
        classification_tally[classification] = classification_tally.get(classification, 0) + 1

    # ──── Deduplicate by station_ft ──────────────────────────────────────
    anchor_records.sort(key=lambda a: (a["station_ft"], a["perp_distance_ft"], a["source_feature_id"]))
    deduped: List[Dict[str, Any]] = []
    last_station: Optional[float] = None
    last_record: Optional[Dict[str, Any]] = None
    for rec in anchor_records:
        if last_record is None or last_station is None:
            deduped.append(rec)
            last_record = rec
            last_station = rec["station_ft"]
            continue
        if abs(rec["station_ft"] - last_station) <= _STATION_FT_DEDUPE_TOLERANCE:
            # Winner is the one with smaller perp_distance_ft; if existing
            # record has smaller perp, current loses.
            if last_record["perp_distance_ft"] <= rec["perp_distance_ft"]:
                _reject(
                    rec["source_feature_id"],
                    "duplicate_station_ft",
                    "kmz_anchor_builder_v1:dedupe",
                    {
                        "station_ft": rec["station_ft"],
                        "kept_feature_id": last_record["source_feature_id"],
                    },
                )
                continue
            # New record wins; demote previous.
            _reject(
                last_record["source_feature_id"],
                "duplicate_station_ft",
                "kmz_anchor_builder_v1:dedupe",
                {
                    "station_ft": last_record["station_ft"],
                    "kept_feature_id": rec["source_feature_id"],
                },
            )
            # Remove last from deduped and adjust classification_tally on
            # the removed feature so the deduped tally below stays clean.
            removed_class = last_record.get("classification")
            if isinstance(removed_class, str):
                classification_tally[removed_class] = max(
                    0, classification_tally.get(removed_class, 0) - 1
                )
            deduped.pop()
        else:
            # Different station — but the prior accumulator is now closed.
            pass
        deduped.append(rec)
        last_record = rec
        last_station = rec["station_ft"]

    anchor_records = deduped

    # ──── Cap output ─────────────────────────────────────────────────────
    if len(anchor_records) > _MAX_ANCHORS_PER_ROUTE:
        # Keep the 200 with the smallest perp_distance_ft (deterministic).
        anchor_records.sort(key=lambda a: (a["perp_distance_ft"], a["station_ft"], a["source_feature_id"]))
        anchor_records = anchor_records[:_MAX_ANCHORS_PER_ROUTE]

    # Final deterministic sort by station_ft for downstream consumption.
    anchor_records.sort(key=lambda a: (a["station_ft"], a["source_feature_id"]))

    # ──── Build the R1-shaped anchor list ────────────────────────────────
    station_anchors_lonlat: List[Tuple[float, Tuple[float, float]]] = [
        (rec["station_ft"], (rec["lon"], rec["lat"]))
        for rec in anchor_records
    ]

    # ──── Diagnostics ────────────────────────────────────────────────────
    perp_distances_m = [a["perp_distance_m"] for a in anchor_records]
    if perp_distances_m:
        sorted_perps = sorted(perp_distances_m)
        mid = len(sorted_perps) // 2
        if len(sorted_perps) % 2 == 1:
            median_perp = sorted_perps[mid]
        else:
            median_perp = (sorted_perps[mid - 1] + sorted_perps[mid]) / 2.0
        perp_stats = {
            "min": _rft(min(sorted_perps)),
            "median": _rft(median_perp),
            "max": _rft(max(sorted_perps)),
        }
    else:
        perp_stats = {"min": 0.0, "median": 0.0, "max": 0.0}

    if anchor_records:
        stations = [a["station_ft"] for a in anchor_records]
        anchor_span_ft = _rft(max(stations) - min(stations))
    else:
        anchor_span_ft = 0.0

    confidence_tally = {"high": 0, "medium": 0, "low": 0}
    for rec in anchor_records:
        ac = rec.get("anchor_confidence")
        if isinstance(ac, str) and ac in confidence_tally:
            confidence_tally[ac] += 1

    route_confidence = _classify_route_confidence(anchor_records)

    warnings: List[str] = []
    if not isinstance(semantic_features, (list, tuple)) or len(semantic_features) == 0:
        warnings.append("kmz_semantic_unavailable")
    if not anchor_records:
        warnings.append("zero_anchors_after_filter")
    if len(anchor_records) == 1:
        warnings.append("only_one_anchor")
    if anchor_records and anchor_span_ft < _ROUTE_MEDIUM_SPAN_FT:
        warnings.append("anchor_span_below_min")

    diagnostics: Dict[str, Any] = {
        "input_feature_count": len(semantic_features),
        "candidate_count_pre_proximity_filter": candidate_count_pre_proximity,
        "candidate_count_post_proximity_filter": candidate_count_post_proximity,
        "candidate_count_post_dedupe": len(anchor_records),
        "anchor_count": len(anchor_records),
        "anchor_span_ft": anchor_span_ft,
        "perp_distance_m_stats": perp_stats,
        "classification_tally": classification_tally,
        "confidence_tally": confidence_tally,
        "rejection_reasons": rejection_reasons,
        "route_confidence": route_confidence,
        "polyline_total_length_ft": _rft(polyline_total_ft),
        "polyline_vertex_count": len(polyline_coerced),
        "warnings": warnings,
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "parameters_version": PARAMETERS_VERSION,
        "route_id": route_id,
        "request_meta": dict(request_meta),
        "station_anchors_lonlat": station_anchors_lonlat,
        "anchor_records": anchor_records,
        "rejected_features": rejected,
        "diagnostics": diagnostics,
        "parameters": {
            "max_proximity_m": _MAX_PROXIMITY_M,
            "anchor_high_perp_m": _ANCHOR_HIGH_PERP_M,
            "anchor_medium_perp_m": _ANCHOR_MEDIUM_PERP_M,
            "route_high_span_ft": _ROUTE_HIGH_SPAN_FT,
            "route_medium_span_ft": _ROUTE_MEDIUM_SPAN_FT,
            "route_high_perp_m_cap": _ROUTE_HIGH_PERP_M_CAP,
            "station_ft_dedupe_tolerance": _STATION_FT_DEDUPE_TOLERANCE,
            "max_anchors_per_route": _MAX_ANCHORS_PER_ROUTE,
            "max_rejected_features": _MAX_REJECTED_FEATURES,
            "anchor_kinds": sorted(_ANCHOR_KINDS_R2),
        },
    }
