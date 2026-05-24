"""Candidate Matrix V1 — break candidate starvation post-print-filter.

The hardcoded print filter (`CURRENT_PACKET_PRINT_SHEET_INDEX` at
backend/main.py:715) prunes the route_catalog down to 1-3 routes per
print token. Combined with the span gate at _build_candidate_pool_for_group,
many bore-log groups end up with `candidate_rankings` of length 1 —
the original print-filter winner. When that winner ALSO collides with
another group, Anti-Collapse V2 has no alternates to test against.

This module assembles an *additional* set of route candidates from six
deterministic evidence sources. It does NOT mutate the print filter
or the rebuild loop's top-1 selection — it only widens the candidate
pool that V2 (or any future re-ranking layer) can search.

Sources (priority order):

  1. print_filter (baseline) — already in base_rankings; preserved as-is.
  2. geometry_proximity_to_top — routes whose centroid is within
     `geometry_proximity_ft` of the top base candidate's centroid.
  3. kmz_point_address — routes derived from KMZ subscriber-point
     proximity to street names found in bore-log notes (reuses the
     dormant `candidate_route_discovery.discover_candidate_routes_from_notes_streets`).
  4. same_source_folder_or_role — routes sharing the top candidate's
     `source_folder`, or sharing `route_role` AND within
     `geometry_proximity_ft` of the top centroid.
  5. adjacent_print_or_sheet — routes appearing in print_sheet_index
     entries adjacent (±`adjacent_print_radius`) to the group's prints.
  6. fallback_proximity — wider-radius geometry scan, fires only when
     the expanded pool is still below the target minimum.

Universal admission gates (applied to every source):
  - Route exists in route_catalog.
  - Route is NOT already in base_rankings.
  - Route length is within `[min_route_length_ratio * span,
    max_route_length_ratio * span]`.

Dedup + attribution: each per-source helper returns IDs it would
admit; the orchestrator's _admit_batch handles dedup and records every
admitting source in `attribution_by_route_id`. `candidate_sources[src]`
records only the FIRST (winning) source that admitted each route.

Output is purely advisory data plus a per-group diagnostic payload.
The caller scores admitted routes via its own scorer and decides how
to merge them into the live ranking.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from .route_collision_alternate_search import _coerce_lonlat, _haversine_ft

try:
    from .candidate_route_discovery import discover_candidate_routes_from_notes_streets
except Exception:  # pragma: no cover — defensive import
    discover_candidate_routes_from_notes_streets = None  # type: ignore


SCHEMA_VERSION = "candidate-matrix-1"


# ── Helpers ────────────────────────────────────────────────────────────────


def _safe_str(value: Any) -> str:
    return str(value if value is not None else "").strip()


def _safe_float(value: Any) -> float:
    try:
        return float(value if value is not None else 0.0)
    except (TypeError, ValueError):
        return 0.0


def _route_centroid_lonlat(coords: Sequence[Any]) -> Optional[Tuple[float, float]]:
    """Return (lon, lat) centroid using the coercion that respects both
    [lat,lon] and [lon,lat] storage conventions."""
    pts: List[Tuple[float, float]] = []
    for raw in coords or []:
        lonlat = _coerce_lonlat(raw)
        if lonlat is not None:
            pts.append(lonlat)
    if not pts:
        return None
    lon = sum(p[0] for p in pts) / len(pts)
    lat = sum(p[1] for p in pts) / len(pts)
    return (lon, lat)


def _centroid_distance_ft(
    a: Tuple[float, float], b: Tuple[float, float]
) -> float:
    """Haversine in feet between two (lon, lat) points."""
    return _haversine_ft(a, b)


def _length_gate_passes(
    route_length_ft: float,
    span_ft: float,
    min_ratio: float,
    max_ratio: float,
) -> Tuple[bool, str]:
    if span_ft <= 0.0:
        return True, ""
    if route_length_ft <= 0.0:
        return False, "route_length_zero"
    if route_length_ft < span_ft * min_ratio:
        return False, f"length_below_{round(span_ft * min_ratio, 1)}ft"
    if route_length_ft > span_ft * max_ratio:
        return False, f"length_above_{round(span_ft * max_ratio, 1)}ft"
    return True, ""


def _index_by_route_id(routes: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for r in routes or []:
        rid = _safe_str((r or {}).get("route_id"))
        if rid and rid not in out:
            out[rid] = r or {}
    return out


# ── Per-source admission ───────────────────────────────────────────────────


def _admit_source_2_geometry_proximity_to_top(
    *,
    base_top_centroid: Optional[Tuple[float, float]],
    base_route_ids: Set[str],
    route_catalog_by_id: Dict[str, Dict[str, Any]],
    span_ft: float,
    geometry_proximity_ft: float,
    min_ratio: float,
    max_ratio: float,
) -> Tuple[List[str], List[Dict[str, Any]]]:
    admitted: List[str] = []
    rejected: List[Dict[str, Any]] = []
    if base_top_centroid is None:
        return admitted, rejected
    for rid, route in route_catalog_by_id.items():
        if rid in base_route_ids:
            continue
        c = _route_centroid_lonlat(route.get("coords") or [])
        if c is None:
            continue
        dist = _centroid_distance_ft(base_top_centroid, c)
        ok_len, len_reason = _length_gate_passes(
            _safe_float(route.get("length_ft")), span_ft, min_ratio, max_ratio
        )
        if not ok_len:
            rejected.append({
                "route_id": rid, "source": "geometry_proximity_to_top",
                "reason": len_reason, "centroid_distance_ft": round(dist, 2),
            })
            continue
        if dist > geometry_proximity_ft:
            rejected.append({
                "route_id": rid, "source": "geometry_proximity_to_top",
                "reason": "outside_geometry_proximity",
                "centroid_distance_ft": round(dist, 2),
                "threshold_ft": geometry_proximity_ft,
            })
            continue
        admitted.append(rid)
    return admitted, rejected


def _admit_source_3_kmz_point_address(
    *,
    notes_streets: Sequence[str],
    address_points: Sequence[Dict[str, Any]],
    route_catalog: Sequence[Dict[str, Any]],
    base_route_ids: Set[str],
    route_catalog_by_id: Dict[str, Dict[str, Any]],
    span_ft: float,
    min_ratio: float,
    max_ratio: float,
) -> Tuple[List[str], List[Dict[str, Any]]]:
    admitted: List[str] = []
    rejected: List[Dict[str, Any]] = []
    if not notes_streets or not address_points or discover_candidate_routes_from_notes_streets is None:
        return admitted, rejected
    try:
        result = discover_candidate_routes_from_notes_streets(
            list(notes_streets), list(address_points), list(route_catalog)
        )
    except Exception:
        return admitted, rejected
    if not result:
        return admitted, rejected
    for rid_any in result.get("discovered_route_ids") or []:
        rid = _safe_str(rid_any)
        if not rid or rid in base_route_ids:
            continue
        route = route_catalog_by_id.get(rid)
        if not route:
            rejected.append({
                "route_id": rid, "source": "kmz_point_address",
                "reason": "route_not_in_catalog",
            })
            continue
        ok_len, len_reason = _length_gate_passes(
            _safe_float(route.get("length_ft")), span_ft, min_ratio, max_ratio
        )
        if not ok_len:
            rejected.append({
                "route_id": rid, "source": "kmz_point_address",
                "reason": len_reason,
            })
            continue
        admitted.append(rid)
    return admitted, rejected


def _admit_source_4_same_source_folder_or_role(
    *,
    base_top_route: Optional[Dict[str, Any]],
    base_top_centroid: Optional[Tuple[float, float]],
    base_route_ids: Set[str],
    route_catalog_by_id: Dict[str, Dict[str, Any]],
    span_ft: float,
    geometry_proximity_ft: float,
    min_ratio: float,
    max_ratio: float,
) -> Tuple[List[str], List[Dict[str, Any]]]:
    admitted: List[str] = []
    rejected: List[Dict[str, Any]] = []
    if not base_top_route:
        return admitted, rejected
    top_folder = _safe_str(base_top_route.get("source_folder")).lower()
    top_role = _safe_str(base_top_route.get("route_role")).lower()
    for rid, route in route_catalog_by_id.items():
        if rid in base_route_ids:
            continue
        cand_folder = _safe_str(route.get("source_folder")).lower()
        cand_role = _safe_str(route.get("route_role")).lower()
        folder_match = bool(top_folder) and cand_folder == top_folder
        role_match = bool(top_role) and cand_role == top_role
        if not (folder_match or role_match):
            continue
        ok_len, len_reason = _length_gate_passes(
            _safe_float(route.get("length_ft")), span_ft, min_ratio, max_ratio
        )
        if not ok_len:
            rejected.append({
                "route_id": rid, "source": "same_source_folder_or_role",
                "reason": len_reason,
                "folder_match": folder_match, "role_match": role_match,
            })
            continue
        if folder_match:
            admitted.append(rid)
            continue
        if role_match and base_top_centroid is not None:
            c = _route_centroid_lonlat(route.get("coords") or [])
            if c is None:
                continue
            dist = _centroid_distance_ft(base_top_centroid, c)
            if dist <= geometry_proximity_ft:
                admitted.append(rid)
            else:
                rejected.append({
                    "route_id": rid, "source": "same_source_folder_or_role",
                    "reason": "role_match_but_outside_proximity",
                    "centroid_distance_ft": round(dist, 2),
                    "threshold_ft": geometry_proximity_ft,
                })
    return admitted, rejected


def _admit_source_5_adjacent_print_or_sheet(
    *,
    sheet_numbers: Sequence[int],
    print_sheet_index: Dict[str, Dict[str, Any]],
    base_route_ids: Set[str],
    route_catalog_by_id: Dict[str, Dict[str, Any]],
    span_ft: float,
    adjacent_print_radius: int,
    min_ratio: float,
    max_ratio: float,
) -> Tuple[List[str], List[Dict[str, Any]]]:
    admitted: List[str] = []
    rejected: List[Dict[str, Any]] = []
    if not sheet_numbers or not print_sheet_index:
        return admitted, rejected
    sheet_to_routes: Dict[int, List[str]] = {}
    for _token, entry in print_sheet_index.items():
        sheet = entry.get("sheet")
        if not isinstance(sheet, int):
            continue
        for r in entry.get("route_ids") or []:
            rid = _safe_str(r)
            if rid:
                sheet_to_routes.setdefault(sheet, []).append(rid)
    target_sheets: Set[int] = set()
    for s in sheet_numbers:
        for offset in range(-adjacent_print_radius, adjacent_print_radius + 1):
            target_sheets.add(int(s) + offset)
    target_sheets -= set(int(s) for s in sheet_numbers)
    seen_local: Set[str] = set()
    for sheet_n in sorted(target_sheets):
        for rid in sheet_to_routes.get(sheet_n, []):
            if rid in base_route_ids or rid in seen_local:
                continue
            seen_local.add(rid)
            route = route_catalog_by_id.get(rid)
            if not route:
                rejected.append({
                    "route_id": rid, "source": "adjacent_print_or_sheet",
                    "reason": "route_not_in_catalog", "adjacent_sheet": sheet_n,
                })
                continue
            ok_len, len_reason = _length_gate_passes(
                _safe_float(route.get("length_ft")), span_ft, min_ratio, max_ratio
            )
            if not ok_len:
                rejected.append({
                    "route_id": rid, "source": "adjacent_print_or_sheet",
                    "reason": len_reason, "adjacent_sheet": sheet_n,
                })
                continue
            admitted.append(rid)
    return admitted, rejected


def _admit_source_6_fallback_proximity(
    *,
    base_top_centroid: Optional[Tuple[float, float]],
    base_route_ids: Set[str],
    route_catalog_by_id: Dict[str, Dict[str, Any]],
    span_ft: float,
    fallback_proximity_ft: float,
    min_ratio: float,
    max_ratio: float,
    current_expanded_count: int,
    min_target_candidates: int,
) -> Tuple[List[str], List[Dict[str, Any]]]:
    admitted: List[str] = []
    rejected: List[Dict[str, Any]] = []
    if base_top_centroid is None:
        return admitted, rejected
    if current_expanded_count >= min_target_candidates:
        return admitted, rejected
    for rid, route in route_catalog_by_id.items():
        if rid in base_route_ids:
            continue
        c = _route_centroid_lonlat(route.get("coords") or [])
        if c is None:
            continue
        dist = _centroid_distance_ft(base_top_centroid, c)
        ok_len, len_reason = _length_gate_passes(
            _safe_float(route.get("length_ft")), span_ft, min_ratio, max_ratio
        )
        if not ok_len:
            rejected.append({
                "route_id": rid, "source": "fallback_proximity",
                "reason": len_reason, "centroid_distance_ft": round(dist, 2),
            })
            continue
        if dist > fallback_proximity_ft:
            rejected.append({
                "route_id": rid, "source": "fallback_proximity",
                "reason": "outside_fallback_proximity",
                "centroid_distance_ft": round(dist, 2),
                "threshold_ft": fallback_proximity_ft,
            })
            continue
        admitted.append(rid)
    return admitted, rejected


# ── Top-level orchestrator ────────────────────────────────────────────────


def build_expanded_candidate_pool(
    *,
    source_file: str,
    base_rankings: Sequence[Dict[str, Any]],
    base_filter_meta: Dict[str, Any],
    route_catalog: Sequence[Dict[str, Any]],
    address_points: Sequence[Dict[str, Any]],
    notes_streets: Sequence[str],
    span_ft: float,
    print_sheet_index: Dict[str, Dict[str, Any]],
    max_total_candidates: int = 15,
    geometry_proximity_ft: float = 800.0,
    fallback_proximity_ft: float = 1500.0,
    min_route_length_ratio: float = 0.30,
    max_route_length_ratio: float = 5.00,
    adjacent_print_radius: int = 1,
    min_target_candidates_for_fallback: int = 3,
) -> Dict[str, Any]:
    """Discover additional route_ids from six evidence sources.

    Returns a dict with the per-source admission breakdown plus a
    `matrix` diagnostic payload ready to land on pipeline_diag.

    Pure function. Never mutates inputs. Caller is responsible for
    scoring admitted routes and merging into the live ranking.
    """
    base_route_ids: Set[str] = {
        _safe_str(r.get("route_id")) for r in base_rankings or []
    }
    base_route_ids.discard("")
    route_catalog_by_id = _index_by_route_id(route_catalog)

    base_top_route: Optional[Dict[str, Any]] = None
    base_top_centroid: Optional[Tuple[float, float]] = None
    if base_rankings:
        top_rid = _safe_str(base_rankings[0].get("route_id"))
        base_top_route = route_catalog_by_id.get(top_rid)
        if base_top_route:
            base_top_centroid = _route_centroid_lonlat(
                base_top_route.get("coords") or []
            )

    sheet_numbers_raw = (base_filter_meta or {}).get("sheet_numbers") or []
    sheet_numbers: List[int] = []
    for s in sheet_numbers_raw:
        try:
            sheet_numbers.append(int(s))
        except (TypeError, ValueError):
            continue

    sources: Dict[str, List[str]] = {
        "print_filter": sorted(base_route_ids),
        "geometry_proximity_to_top": [],
        "kmz_point_address": [],
        "same_source_folder_or_role": [],
        "adjacent_print_or_sheet": [],
        "fallback_proximity": [],
    }
    attribution: Dict[str, List[str]] = {}
    rejected_all: List[Dict[str, Any]] = []
    admitted_set: Set[str] = set()
    admitted_order: List[str] = []

    def _admit_batch(source_name: str, route_ids: Sequence[str]) -> None:
        for rid in route_ids:
            if rid in admitted_set:
                attribution.setdefault(rid, []).append(source_name)
                continue
            admitted_set.add(rid)
            admitted_order.append(rid)
            attribution.setdefault(rid, []).append(source_name)
            sources[source_name].append(rid)

    s2_admit, s2_reject = _admit_source_2_geometry_proximity_to_top(
        base_top_centroid=base_top_centroid,
        base_route_ids=base_route_ids,
        route_catalog_by_id=route_catalog_by_id,
        span_ft=span_ft,
        geometry_proximity_ft=geometry_proximity_ft,
        min_ratio=min_route_length_ratio,
        max_ratio=max_route_length_ratio,
    )
    _admit_batch("geometry_proximity_to_top", s2_admit)
    rejected_all.extend(s2_reject)

    s3_admit, s3_reject = _admit_source_3_kmz_point_address(
        notes_streets=notes_streets,
        address_points=address_points,
        route_catalog=route_catalog,
        base_route_ids=base_route_ids,
        route_catalog_by_id=route_catalog_by_id,
        span_ft=span_ft,
        min_ratio=min_route_length_ratio,
        max_ratio=max_route_length_ratio,
    )
    _admit_batch("kmz_point_address", s3_admit)
    rejected_all.extend(s3_reject)

    s4_admit, s4_reject = _admit_source_4_same_source_folder_or_role(
        base_top_route=base_top_route,
        base_top_centroid=base_top_centroid,
        base_route_ids=base_route_ids,
        route_catalog_by_id=route_catalog_by_id,
        span_ft=span_ft,
        geometry_proximity_ft=geometry_proximity_ft,
        min_ratio=min_route_length_ratio,
        max_ratio=max_route_length_ratio,
    )
    _admit_batch("same_source_folder_or_role", s4_admit)
    rejected_all.extend(s4_reject)

    s5_admit, s5_reject = _admit_source_5_adjacent_print_or_sheet(
        sheet_numbers=sheet_numbers,
        print_sheet_index=print_sheet_index,
        base_route_ids=base_route_ids,
        route_catalog_by_id=route_catalog_by_id,
        span_ft=span_ft,
        adjacent_print_radius=adjacent_print_radius,
        min_ratio=min_route_length_ratio,
        max_ratio=max_route_length_ratio,
    )
    _admit_batch("adjacent_print_or_sheet", s5_admit)
    rejected_all.extend(s5_reject)

    s6_admit, s6_reject = _admit_source_6_fallback_proximity(
        base_top_centroid=base_top_centroid,
        base_route_ids=base_route_ids,
        route_catalog_by_id=route_catalog_by_id,
        span_ft=span_ft,
        fallback_proximity_ft=fallback_proximity_ft,
        min_ratio=min_route_length_ratio,
        max_ratio=max_route_length_ratio,
        current_expanded_count=len(admitted_order) + len(base_route_ids),
        min_target_candidates=min_target_candidates_for_fallback,
    )
    _admit_batch("fallback_proximity", s6_admit)
    rejected_all.extend(s6_reject)

    headroom = max(0, max_total_candidates - len(base_route_ids))
    additional_route_ids = admitted_order[:headroom]
    capped_off = admitted_order[headroom:]
    for rid in capped_off:
        rejected_all.append({
            "route_id": rid, "source": "_cap",
            "reason": "exceeded_max_total_candidates",
            "max_total_candidates": max_total_candidates,
        })
        for src_list in sources.values():
            if rid in src_list:
                src_list.remove(rid)

    final_candidate_ids = sorted(base_route_ids) + additional_route_ids

    matrix = {
        "schema": SCHEMA_VERSION,
        "source_file": source_file,
        "original_candidate_count": len(base_route_ids),
        "expanded_candidate_count": len(additional_route_ids),
        "candidate_sources": sources,
        "attribution_by_route_id": attribution,
        "rejected_candidates": rejected_all,
        "final_candidate_ids": final_candidate_ids,
        "thresholds": {
            "geometry_proximity_ft": geometry_proximity_ft,
            "fallback_proximity_ft": fallback_proximity_ft,
            "min_route_length_ratio": min_route_length_ratio,
            "max_route_length_ratio": max_route_length_ratio,
            "adjacent_print_radius": adjacent_print_radius,
            "max_total_candidates": max_total_candidates,
            "min_target_candidates_for_fallback": min_target_candidates_for_fallback,
        },
    }
    return {
        "additional_route_ids": additional_route_ids,
        "attribution_by_route_id": attribution,
        "rejected_candidates": rejected_all,
        "matrix": matrix,
    }
