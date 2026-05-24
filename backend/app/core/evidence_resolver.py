"""Evidence Resolver — per-group evidence packet + advisory decision tag.

Builds a single auditable record per bore-log group capturing every signal
the matcher had access to (notes streets, print refs, print-hint route_ids,
KMZ ranking, address-point candidates, conflicts, confidence). Emits a
decision tag PLACE_CONFIDENTLY / PLACE_WITH_CAUTION / ABSTAIN_CONFLICT /
ABSTAIN_INSUFFICIENT_EVIDENCE.

This sprint: the decision tag is ADVISORY — it is recorded in pipeline_diag
for audit and downstream review but does NOT override the matcher's
placement. The V1 location-evidence mismatch and V2 abstain branch retain
authority over actual placement.

Pure read-only; no mutation of inputs.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

DECISION_PLACE_CONFIDENTLY = "PLACE_CONFIDENTLY"
DECISION_PLACE_WITH_CAUTION = "PLACE_WITH_CAUTION"
DECISION_ABSTAIN_CONFLICT = "ABSTAIN_CONFLICT"
DECISION_ABSTAIN_INSUFFICIENT_EVIDENCE = "ABSTAIN_INSUFFICIENT_EVIDENCE"

# Confidence floor: top ranking score must clear this for any non-abstain
# decision when no location evidence corroborates.
_TOP_SCORE_FLOOR = 0.30
# Margin floor: top-1 must beat top-2 by at least this delta to count as
# "clean" placement (otherwise tag PLACE_WITH_CAUTION).
_CLEAN_MARGIN = 0.05


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _collect_unique_strings(rows: Sequence[Dict[str, Any]], key: str) -> List[str]:
    seen: set = set()
    out: List[str] = []
    for r in rows or []:
        text = _safe_text((r or {}).get(key))
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _collect_station_range(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    fts: List[float] = []
    for r in rows or []:
        v = (r or {}).get("station_ft")
        if isinstance(v, (int, float)):
            fts.append(float(v))
    if not fts:
        return {"min_ft": None, "max_ft": None, "span_ft": None, "row_count": len(rows or [])}
    return {
        "min_ft": round(min(fts), 2),
        "max_ft": round(max(fts), 2),
        "span_ft": round(max(fts) - min(fts), 2),
        "row_count": len(rows or []),
    }


def _decide(
    rankings_top1: Optional[Dict[str, Any]],
    rankings_top2: Optional[Dict[str, Any]],
    location_evidence_mismatch: Optional[Dict[str, Any]],
    auto_candidate_expansion: Optional[Dict[str, Any]],
) -> str:
    if not rankings_top1:
        return DECISION_ABSTAIN_INSUFFICIENT_EVIDENCE
    if location_evidence_mismatch and not auto_candidate_expansion:
        return DECISION_ABSTAIN_CONFLICT
    top1_score = _safe_float(rankings_top1.get("score"))
    if top1_score < _TOP_SCORE_FLOOR:
        return DECISION_ABSTAIN_INSUFFICIENT_EVIDENCE
    if rankings_top2:
        margin = top1_score - _safe_float(rankings_top2.get("score"))
        if margin < _CLEAN_MARGIN:
            return DECISION_PLACE_WITH_CAUTION
    if auto_candidate_expansion:
        return DECISION_PLACE_CONFIDENTLY
    return DECISION_PLACE_CONFIDENTLY


def _compute_confidence_score(
    rankings_top1: Optional[Dict[str, Any]],
    rankings_top2: Optional[Dict[str, Any]],
    location_evidence_mismatch: Optional[Dict[str, Any]],
    auto_candidate_expansion: Optional[Dict[str, Any]],
) -> float:
    if not rankings_top1:
        return 0.0
    base = _safe_float(rankings_top1.get("score"))
    if rankings_top2:
        margin = max(0.0, base - _safe_float(rankings_top2.get("score")))
    else:
        margin = base
    score = 0.5 * base + 0.5 * min(margin, 0.30) / 0.30
    if location_evidence_mismatch and not auto_candidate_expansion:
        score *= 0.25
    if auto_candidate_expansion:
        # Discovery rescue narrows uncertainty — modest boost.
        score = min(1.0, score + 0.10)
    return round(max(0.0, min(1.0, score)), 4)


def resolve_evidence_for_group(
    group_rows: Sequence[Dict[str, Any]],
    normalized_group: Dict[str, Any],
    filter_meta: Dict[str, Any],
    rankings: Sequence[Dict[str, Any]],
    location_evidence_mismatch: Optional[Dict[str, Any]],
    auto_candidate_expansion: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Return the per-group evidence packet + decision tag.

    All inputs are read-only. Output is JSON-serializable.
    """
    rows = list(group_rows or [])
    top1 = rankings[0] if rankings else None
    top2 = rankings[1] if rankings and len(rankings) > 1 else None

    print_hint_route_ids = list((filter_meta or {}).get("allowed_route_ids") or [])
    street_hints = list((filter_meta or {}).get("street_hints") or [])

    kmz_route_candidates = [
        {
            "route_id": (r or {}).get("route_id"),
            "route_name": (r or {}).get("route_name"),
            "score": round(_safe_float((r or {}).get("score")), 4),
        }
        for r in (rankings or [])[:5]
    ]

    notes_streets: List[str] = []
    if location_evidence_mismatch:
        notes_streets = list((location_evidence_mismatch.get("notes_streets") or []))

    point_candidates: List[Dict[str, Any]] = []
    if auto_candidate_expansion:
        for rid in (auto_candidate_expansion.get("discovered_route_ids") or []):
            point_candidates.append({
                "route_id": rid,
                "source": auto_candidate_expansion.get("source"),
                "evidence": dict(auto_candidate_expansion.get("evidence") or {}),
            })

    conflicts: List[str] = []
    if location_evidence_mismatch:
        conflicts.append("notes_streets_disjoint_from_print_hint_streets")
    if (
        top1
        and top2
        and abs(_safe_float(top1.get("score")) - _safe_float(top2.get("score"))) < _CLEAN_MARGIN
    ):
        conflicts.append("top_2_scores_within_clean_margin")
    if not top1:
        conflicts.append("no_ranking_candidates_after_filter")

    confidence = _compute_confidence_score(top1, top2, location_evidence_mismatch, auto_candidate_expansion)
    decision = _decide(top1, top2, location_evidence_mismatch, auto_candidate_expansion)

    packet = {
        "source_file": _safe_text((rows[0] if rows else {}).get("source_file")),
        "notes_streets": notes_streets,
        "print_refs": _collect_unique_strings(rows, "print"),
        "station_range": _collect_station_range(rows),
        "date_values": _collect_unique_strings(rows, "date"),
        "crew_values": _collect_unique_strings(rows, "crew"),
        "print_hint_route_ids": print_hint_route_ids,
        "print_hint_street_hints": street_hints,
        "kmz_route_candidates": kmz_route_candidates,
        "kmz_point_address_candidates": point_candidates,
        "pdf_evidence": None,
        "sequence_evidence": None,
        "coverage_evidence": None,
        "conflicts": conflicts,
        "confidence": confidence,
        "decision": decision,
        "decision_basis": {
            "top1_score": round(_safe_float((top1 or {}).get("score")), 4) if top1 else None,
            "top2_score": round(_safe_float((top2 or {}).get("score")), 4) if top2 else None,
            "top_score_floor": _TOP_SCORE_FLOOR,
            "clean_margin": _CLEAN_MARGIN,
            "location_mismatch_present": bool(location_evidence_mismatch),
            "auto_expansion_applied": bool(auto_candidate_expansion),
        },
    }
    return packet
