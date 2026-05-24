"""Location-Mismatch V4 — LAWNDALE-targeted rescue before upstream abstain.

V3 (TRUELINE_AUTO_CANDIDATE_EXPANSION) already attempts to discover a
trunk route from KMZ subscriber-point proximity, but its gate is too
strict for the LAWNDALE corridor on Brenham:
  discovered Lawndale trunk scores ~0.18 (oversize-penalty saturation
  against a long Underground Cable trunk vs a short bore span), while
  the gate requires `max(current_top, 0.30)`. The mismatch-bearing
  print-filter "top" can score higher than the discovered route even
  though the notes name a different street, so V3 abstains.

V4 inserts a second-chance rescue between V3 and the
`abstained_location_evidence_mismatch` finalize. It is intentionally
narrow:

  - Only fires when notes_streets matches the LAWNDALE allowlist
    (so CHERI, HUISACHE alone, and every other street still abstain).
  - Only consults the existing V3 discovery helper
    (`discover_candidate_routes_from_notes_streets`) — no new evidence
    source, no GIS, no runtime AI.
  - Uses a relaxed two-way gate:
      best_discovered_score >= min_absolute_score
      OR best_discovered_score >= current_top_score * score_ratio_fallback
    With defaults 0.15 / 0.60.

This module is pure: never mutates inputs, never reads STATE, never
calls into main.py. The caller is expected to inject a score callback
(typically `_score_route_for_group(group_rows, route)`) so V4 matches
V3's existing scoring contract exactly.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence


# LAWNDALE allowlist mirrors `candidate_route_discovery._ALLOWED_STREETS`
# byte-identical so V4's "is this a LAWNDALE group?" check stays in
# lockstep with V3's "is there a LAWNDALE cluster to discover?" check.
_LAWNDALE_ALLOWLIST: frozenset = frozenset({
    "LAWNDALE", "LAWNDALE AVE", "LAWNDALE AVENUE",
})

_DEFAULT_MIN_ABSOLUTE_SCORE = 0.15
_DEFAULT_SCORE_RATIO_FALLBACK = 0.60


def _safe_str(value: Any) -> str:
    return str(value if value is not None else "").strip()


def _safe_float(value: Any) -> float:
    try:
        return float(value if value is not None else 0.0)
    except (TypeError, ValueError):
        return 0.0


def _normalize_street(value: Any) -> str:
    text = _safe_str(value).upper()
    if not text:
        return ""
    return " ".join(text.split())


def _matches_lawndale_allowlist(notes_streets: Sequence[str]) -> bool:
    """True iff any notes street normalizes to a LAWNDALE-family token."""
    for s in notes_streets or []:
        if _normalize_street(s) in _LAWNDALE_ALLOWLIST:
            return True
    return False


def attempt_location_mismatch_rescue(
    *,
    notes_streets: Sequence[str],
    filter_streets: Sequence[str],
    current_rankings: Sequence[Dict[str, Any]],
    route_catalog: Sequence[Dict[str, Any]],
    address_points: Sequence[Dict[str, Any]],
    group_rows: Sequence[Dict[str, Any]],
    discover_callback: Callable[..., Optional[Dict[str, Any]]],
    score_callback: Callable[[Sequence[Dict[str, Any]], Dict[str, Any]], Dict[str, Any]],
    find_route_callback: Callable[[str], Optional[Dict[str, Any]]],
    min_absolute_score: float = _DEFAULT_MIN_ABSOLUTE_SCORE,
    score_ratio_fallback: float = _DEFAULT_SCORE_RATIO_FALLBACK,
) -> Dict[str, Any]:
    """Return a structured rescue decision.

    Outcome possibilities:
      - "rescued": LAWNDALE notes + discovery yielded a route that cleared
        the relaxed gate. Caller should promote `selected_scored` to top
        of rankings.
      - "skipped_not_lawndale": notes do not name LAWNDALE; preserve
        existing abstain semantics (this is the CHERI / HUISACHE-only path).
      - "rejected_no_discovery": LAWNDALE in notes but V3 helper found
        no candidate route (e.g. address_points missing, KMZ has no
        Lawndale subscriber cluster, dominance gate failed).
      - "rejected_no_route_in_catalog": discovery returned route_ids
        absent from the live catalog.
      - "rejected_below_gate": discovered route scored below the relaxed
        gate (both absolute floor and ratio fallback).

    Pure function. Never mutates inputs. Returns a self-describing dict
    suitable to land on pipeline_diag under either
    `location_mismatch_rescue_selected` (on rescued) or
    `location_mismatch_rescue_rejected` (on any rejection).
    """
    current_top_score = _safe_float(
        (current_rankings[0].get("score") if current_rankings else 0.0)
    )
    current_top_route_id = _safe_str(
        (current_rankings[0].get("route_id") if current_rankings else "")
    )

    base_diag = {
        "notes_streets": [_safe_str(s) for s in (notes_streets or [])],
        "original_filter_streets": [_safe_str(s) for s in (filter_streets or [])],
        "original_top_route_id": current_top_route_id,
        "original_top_score": round(current_top_score, 4),
        "thresholds": {
            "min_absolute_score": min_absolute_score,
            "score_ratio_fallback": score_ratio_fallback,
            "ratio_floor_against_top": round(
                current_top_score * score_ratio_fallback, 4
            ),
        },
        "evidence_source": "kmz_point_address",
        "rescue_allowlist": "LAWNDALE",
    }

    # Step 1 — Allowlist gate. CHERI / HUISACHE-alone / anything else: skip.
    if not _matches_lawndale_allowlist(notes_streets):
        return {
            "outcome": "skipped_not_lawndale",
            "rescued": False,
            "reason": "notes_streets_outside_lawndale_allowlist",
            "selected_route_id": None,
            "selected_route_name": None,
            "selected_score": None,
            "discovered_route_ids": [],
            "best_discovered_score": None,
            "scored_full": None,
            **base_diag,
        }

    # Step 2 — Discovery. Reuse V3's helper unchanged.
    try:
        discovery = discover_callback(
            list(notes_streets or []),
            list(address_points or []),
            list(route_catalog or []),
        )
    except Exception:
        discovery = None
    discovered_route_ids: List[str] = []
    discovery_evidence: Optional[Dict[str, Any]] = None
    if discovery and discovery.get("discovered_route_ids"):
        discovered_route_ids = [
            _safe_str(r) for r in discovery["discovered_route_ids"]
            if _safe_str(r)
        ]
        discovery_evidence = discovery.get("evidence") or None
    if not discovered_route_ids:
        return {
            "outcome": "rejected_no_discovery",
            "rescued": False,
            "reason": "v3_discovery_yielded_no_candidate",
            "selected_route_id": None,
            "selected_route_name": None,
            "selected_score": None,
            "discovered_route_ids": [],
            "best_discovered_score": None,
            "scored_full": None,
            "discovery_evidence": discovery_evidence,
            **base_diag,
        }

    # Step 3 — Score discovered routes; pick the best.
    best_scored: Optional[Dict[str, Any]] = None
    best_rid: Optional[str] = None
    for rid in discovered_route_ids:
        route = find_route_callback(rid)
        if not route:
            continue
        try:
            scored = score_callback(group_rows, route)
        except Exception:
            continue
        if (best_scored is None
                or _safe_float(scored.get("score"))
                > _safe_float(best_scored.get("score"))):
            best_scored = scored
            best_rid = rid

    if not best_rid or best_scored is None:
        return {
            "outcome": "rejected_no_route_in_catalog",
            "rescued": False,
            "reason": "discovered_route_ids_not_in_catalog",
            "selected_route_id": None,
            "selected_route_name": None,
            "selected_score": None,
            "discovered_route_ids": discovered_route_ids,
            "best_discovered_score": None,
            "scored_full": None,
            "discovery_evidence": discovery_evidence,
            **base_diag,
        }

    best_score = _safe_float(best_scored.get("score"))

    # Step 4 — Relaxed gate. Pass if EITHER condition holds.
    absolute_passes = best_score >= min_absolute_score
    ratio_passes = (
        current_top_score > 0.0
        and best_score >= current_top_score * score_ratio_fallback
    )

    if not (absolute_passes or ratio_passes):
        return {
            "outcome": "rejected_below_gate",
            "rescued": False,
            "reason": "discovered_score_below_both_absolute_and_ratio_gates",
            "selected_route_id": best_rid,
            "selected_route_name": _safe_str(best_scored.get("route_name")),
            "selected_score": round(best_score, 4),
            "discovered_route_ids": discovered_route_ids,
            "best_discovered_score": round(best_score, 4),
            "scored_full": None,
            "discovery_evidence": discovery_evidence,
            "absolute_gate_passes": absolute_passes,
            "ratio_gate_passes": ratio_passes,
            **base_diag,
        }

    return {
        "outcome": "rescued",
        "rescued": True,
        "reason": (
            "lawndale_allowlist_absolute_gate_pass"
            if absolute_passes else "lawndale_allowlist_ratio_gate_pass"
        ),
        "selected_route_id": best_rid,
        "selected_route_name": _safe_str(best_scored.get("route_name")),
        "selected_score": round(best_score, 4),
        "discovered_route_ids": discovered_route_ids,
        "best_discovered_score": round(best_score, 4),
        "scored_full": dict(best_scored),
        "discovery_evidence": discovery_evidence,
        "absolute_gate_passes": absolute_passes,
        "ratio_gate_passes": ratio_passes,
        **base_diag,
    }
