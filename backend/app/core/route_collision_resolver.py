"""Anti-Collapse V1 resolver — deterministic collision arbitration.

Given the post-rebuild `group_matches`, `pipeline_diag`, and the
`same_route_anchor_collisions` list emitted by `coverage_sanity`, this
module decides which group "wins" each collision cluster and which
groups must be abstained. Pure read-only — does NOT mutate any input.

A collision cluster is a connected component in the per-route overlap
graph (nodes = placed source_files on that route; edges = pairwise
overlap >= threshold per coverage_sanity).

Tie-breaker order (deterministic, runs top-to-bottom; first
differentiating key decides):
  1. Higher evidence_resolver.confidence
  2. Higher evidence_resolver.decision_basis.top1_score
  3. Has location-evidence match with the selected route
     (notes_streets present AND
      either auto_candidate_expansion's selected_candidate_route_id ==
      selected_route_id OR no location_evidence_mismatch fired)
  4. Earlier date if same crew
  5. Lower source_file lexical order
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Set, Tuple


def _safe_str(v: Any) -> str:
    return str(v if v is not None else "").strip()


def _safe_float(v: Any) -> float:
    try:
        return float(v if v is not None else 0.0)
    except (TypeError, ValueError):
        return 0.0


def _index_pipeline_diag(pipeline_diag: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Map source_file -> pipeline_diag entry (first occurrence wins for
    deterministic behavior when multiple groups share a source_file)."""
    out: Dict[str, Dict[str, Any]] = {}
    for e in pipeline_diag or []:
        sf = _safe_str((e or {}).get("source_file"))
        if sf and sf not in out:
            out[sf] = e or {}
    return out


def _index_group_matches(group_matches: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for m in group_matches or []:
        sf = _safe_str((m or {}).get("source_file"))
        if sf and sf not in out:
            out[sf] = m or {}
    return out


def _group_dates(match: Dict[str, Any]) -> List[str]:
    pts = (match or {}).get("group_station_points") or []
    out: Set[str] = set()
    for p in pts:
        d = _safe_str((p or {}).get("date"))
        if d:
            out.add(d)
    return sorted(out)


def _group_crews(match: Dict[str, Any]) -> List[str]:
    pts = (match or {}).get("group_station_points") or []
    out: Set[str] = set()
    for p in pts:
        c = _safe_str((p or {}).get("crew"))
        if c:
            out.add(c)
    return sorted(out)


def _has_location_evidence_match(diag: Dict[str, Any], match: Dict[str, Any]) -> bool:
    """True if the group carries notes street evidence that aligns with
    the selected route — i.e. V3 expansion targeted the selected route OR
    no mismatch was fired for a notes-bearing group."""
    evr = (diag or {}).get("evidence_resolver") or {}
    notes_streets = list(evr.get("notes_streets") or [])
    if not notes_streets:
        return False
    selected_route_id = _safe_str((match or {}).get("route_id"))
    ace = (diag or {}).get("auto_candidate_expansion") or {}
    selected_candidate = _safe_str(ace.get("selected_candidate_route_id"))
    if ace and selected_candidate and selected_candidate == selected_route_id:
        return True
    if not (diag or {}).get("location_evidence_mismatch"):
        return True
    return False


def _confidence_for(diag: Dict[str, Any]) -> float:
    evr = (diag or {}).get("evidence_resolver") or {}
    return _safe_float(evr.get("confidence"))


def _top1_score_for(diag: Dict[str, Any]) -> float:
    evr = (diag or {}).get("evidence_resolver") or {}
    db = evr.get("decision_basis") or {}
    return _safe_float(db.get("top1_score"))


def _earliest_date(dates: Sequence[str]) -> str:
    # ISO-formatted dates sort lexically; if format is mixed, this still
    # yields a deterministic order even if it's not strict chronological.
    return min(dates) if dates else ""


def _tiebreak_sort_key(
    source_file: str,
    diag_by_sf: Dict[str, Dict[str, Any]],
    match_by_sf: Dict[str, Dict[str, Any]],
) -> Tuple:
    diag = diag_by_sf.get(source_file) or {}
    match = match_by_sf.get(source_file) or {}
    # All keys negated where higher = better, so a single ascending sort
    # places the winner first.
    return (
        -_confidence_for(diag),
        -_top1_score_for(diag),
        0 if _has_location_evidence_match(diag, match) else 1,
        _earliest_date(_group_dates(match)) or "9999-99-99",
        source_file,
    )


def _build_per_route_components(
    collisions: Sequence[Dict[str, Any]],
) -> Dict[str, Dict[str, Set[str]]]:
    """Group collision pairs by route, then union-find connected
    components within each route. Returns
    { route_id: { component_root: set(source_files) } }."""
    by_route: Dict[str, List[Tuple[str, str]]] = {}
    for c in collisions or []:
        rid = _safe_str((c or {}).get("route_id"))
        sfs = list((c or {}).get("source_files") or [])
        if not rid or len(sfs) < 2:
            continue
        by_route.setdefault(rid, []).append((_safe_str(sfs[0]), _safe_str(sfs[1])))

    result: Dict[str, Dict[str, Set[str]]] = {}
    for rid, pairs in by_route.items():
        parent: Dict[str, str] = {}

        def find(x: str) -> str:
            while parent.get(x, x) != x:
                parent[x] = parent.get(parent[x], parent[x])
                x = parent[x]
            return x

        def union(a: str, b: str) -> None:
            ra, rb = find(a), find(b)
            if ra == rb:
                return
            # Lexically lower root for determinism
            if ra < rb:
                parent[rb] = ra
            else:
                parent[ra] = rb

        for a, b in pairs:
            if a and b:
                parent.setdefault(a, a)
                parent.setdefault(b, b)
                union(a, b)

        comps: Dict[str, Set[str]] = {}
        for node in parent:
            comps.setdefault(find(node), set()).add(node)
        result[rid] = comps
    return result


def _max_pair_overlap_for_cluster(
    route_id: str,
    cluster: Set[str],
    collisions: Sequence[Dict[str, Any]],
) -> Tuple[float, float]:
    """Find the maximum overlap_ratio + overlap_ft among any pair within
    the cluster on the given route. Used for the abstain_reason payload."""
    best_ratio = 0.0
    best_ft = 0.0
    for c in collisions or []:
        if _safe_str((c or {}).get("route_id")) != route_id:
            continue
        sfs = set(_safe_str(s) for s in ((c or {}).get("source_files") or []))
        if not sfs.issubset(cluster):
            continue
        ratio = _safe_float((c or {}).get("overlap_ratio"))
        ft = _safe_float((c or {}).get("overlap_ft"))
        if ratio > best_ratio:
            best_ratio = ratio
        if ft > best_ft:
            best_ft = ft
    return (best_ratio, best_ft)


def resolve_route_collisions(
    group_matches: Sequence[Dict[str, Any]],
    pipeline_diag: Sequence[Dict[str, Any]],
    collisions: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """Return the collision arbitration result. Pure function.

    Output:
      {
        "abstained_source_files": [...],
        "per_source_file_abstain_reason": {
          "<source_file>": {
            "reason": "same_route_anchor_collision",
            "route_id": ...,
            "route_name": ...,
            "overlap_ratio": <max in cluster>,
            "overlap_ft": <max in cluster>,
            "kept_source_file": ...,
            "kept_confidence": ...,
            "collision_source_files": [...sorted cluster...]
          }
        },
        "collision_resolutions": [
          { "route_id": ..., "route_name": ..., "cluster_size": N,
            "kept_source_file": ..., "kept_confidence": ...,
            "abstained_source_files": [...sorted...],
            "max_overlap_ratio": ..., "max_overlap_ft": ... },
          ...
        ]
      }

    If `collisions` is empty, returns empty structures (no abstains).
    """
    diag_by_sf = _index_pipeline_diag(pipeline_diag)
    match_by_sf = _index_group_matches(group_matches)

    # Build per-route route_name lookup from group_matches (avoids needing
    # route_catalog as an input)
    route_name_by_id: Dict[str, str] = {}
    for m in group_matches or []:
        rid = _safe_str((m or {}).get("route_id"))
        nm = _safe_str((m or {}).get("route_name"))
        if rid and nm and rid not in route_name_by_id:
            route_name_by_id[rid] = nm

    components_by_route = _build_per_route_components(collisions)

    abstained_set: Set[str] = set()
    per_source_file_reason: Dict[str, Dict[str, Any]] = {}
    collision_resolutions: List[Dict[str, Any]] = []

    # Deterministic outer iteration order (sorted route_ids)
    for route_id in sorted(components_by_route.keys()):
        for component in components_by_route[route_id].values():
            if len(component) < 2:
                continue
            # Filter to source_files that are actually placed and render_allowed
            placed_in_component: List[str] = [
                sf for sf in component
                if _safe_str((match_by_sf.get(sf) or {}).get("route_id")) == route_id
                and bool((match_by_sf.get(sf) or {}).get("render_allowed"))
            ]
            if len(placed_in_component) < 2:
                continue
            sorted_cluster = sorted(
                placed_in_component,
                key=lambda sf: _tiebreak_sort_key(sf, diag_by_sf, match_by_sf),
            )
            kept = sorted_cluster[0]
            losers = sorted_cluster[1:]
            kept_diag = diag_by_sf.get(kept) or {}
            kept_confidence = _confidence_for(kept_diag)
            max_ratio, max_ft = _max_pair_overlap_for_cluster(
                route_id, set(sorted_cluster), collisions
            )
            route_name = route_name_by_id.get(route_id, "")
            for loser in losers:
                abstained_set.add(loser)
                per_source_file_reason[loser] = {
                    "reason": "same_route_anchor_collision",
                    "route_id": route_id,
                    "route_name": route_name,
                    "overlap_ratio": round(max_ratio, 4),
                    "overlap_ft": round(max_ft, 2),
                    "kept_source_file": kept,
                    "kept_confidence": round(kept_confidence, 4),
                    "collision_source_files": list(sorted_cluster),
                }
            collision_resolutions.append({
                "route_id": route_id,
                "route_name": route_name,
                "cluster_size": len(sorted_cluster),
                "kept_source_file": kept,
                "kept_confidence": round(kept_confidence, 4),
                "abstained_source_files": list(losers),
                "max_overlap_ratio": round(max_ratio, 4),
                "max_overlap_ft": round(max_ft, 2),
            })

    return {
        "abstained_source_files": sorted(abstained_set),
        "per_source_file_abstain_reason": per_source_file_reason,
        "collision_resolutions": collision_resolutions,
    }
