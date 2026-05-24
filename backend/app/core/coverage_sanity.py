"""Coverage Sanity — post-rebuild collapse-and-distribution diagnostic.

Reads the per-group match outcomes after the rebuild loop completes and
emits a route-distribution + overuse report. Pure read-only; does not
modify any inputs or rebuild outputs.

Output written to STATE["coverage_sanity"] for operator audit. Designed
to surface the "completed corpus collapsed onto 4-5 routes" failure mode
the user has observed in production.

This sprint: diagnostic only — no scoring, ranking, or placement changes.
Operators can review the report and decide whether to investigate
specific routes flagged as overused.
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

# Defaults tuned for the Brenham 58-group corpus context. Operators can
# override at call site if needed.
_DEFAULT_OVERUSE_MIN_COUNT = 5
_DEFAULT_OVERUSE_SHARE_PCT = 0.25
_DEFAULT_TOP5_COLLAPSE_THRESHOLD = 0.80


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _route_role_for_id(route_catalog: Sequence[Dict[str, Any]], route_id: str) -> str:
    target = str(route_id or "").strip()
    if not target:
        return ""
    for r in route_catalog or []:
        if str((r or {}).get("route_id") or "").strip() == target:
            return str((r or {}).get("route_role") or "")
    return ""


def compute_coverage_sanity(
    group_matches: Sequence[Dict[str, Any]],
    route_catalog: Sequence[Dict[str, Any]],
    total_groups: int,
    *,
    overuse_min_count: int = _DEFAULT_OVERUSE_MIN_COUNT,
    overuse_share_pct: float = _DEFAULT_OVERUSE_SHARE_PCT,
    top5_collapse_threshold: float = _DEFAULT_TOP5_COLLAPSE_THRESHOLD,
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

    return {
        "schema": "coverage-sanity-1",
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
        "warnings": _build_warnings(
            placed_count, matched_route_count, suspicious, corpus_collapse_detected
        ),
    }


def _build_warnings(
    placed_count: int,
    matched_route_count: int,
    suspicious: List[Dict[str, Any]],
    corpus_collapse_detected: bool,
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
    return out
