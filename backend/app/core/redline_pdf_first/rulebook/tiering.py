"""Day-2 tiering: turn scored candidate chains into a tier decision.

Tiers: AUTO_SELECT, AUTO_PLACED_REQUIRES_APPROVAL, FAIL_SAFE. (ERROR is produced
upstream on exceptions.) No coordinate-snapping.

Ranking uses a composite penalty over AUTHORED evidence so a coincidental sum of
small/VACANT lateral boxes cannot out-rank the true authored segment:
    penalty = foot_delta + 30*vacant_boxes + 8*(n_boxes-1) + (start_delta + end_delta)
- vacant boxes are strongly dispreferred (the bore is the active corridor),
- a single authored box beats a multi-box concatenation when footage is close,
- exact footage + exact endpoints still win among like-signature candidates.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from ..contracts import (
    TIER_AUTO_PLACED_REQUIRES_APPROVAL,
    TIER_AUTO_SELECT,
    TIER_FAIL_SAFE,
)


def tolerances(span_ft: float) -> Dict[str, float]:
    return {
        "auto_foot": max(5.0, 0.015 * span_ft),
        "review_foot": max(20.0, 0.06 * span_ft),
        "auto_end": 5.0,
        "review_end": 8.0,
    }


def penalty(sc: Dict[str, Any]) -> float:
    return (sc["foot_delta"]
            + 30.0 * sc["vacant"]
            + 8.0 * (sc["n_boxes"] - 1)
            + (sc["start_delta"] + sc["end_delta"]))


def _sig(score: Dict[str, Any]) -> Tuple[str, str]:
    """Segment identity = (from station, to station). Distinguishes genuinely
    different corridors from mere prefix/extension chains of the same span."""
    return (score["chain_from"], score["chain_to"])


def decide(scored: List[Tuple[List[Dict[str, Any]], Dict[str, Any]]], span_ft: float) -> Dict[str, Any]:
    tol = tolerances(span_ft)
    acceptable = [
        (ch, sc) for (ch, sc) in scored
        if sc["start_delta"] <= tol["review_end"]
        and sc["end_delta"] <= tol["review_end"]
        and sc["foot_delta"] <= tol["review_foot"]
    ]
    if not acceptable:
        return {"tier": TIER_FAIL_SAFE, "winner": None, "caveat": None,
                "reason": "NO_AUTHORED_BOX_MATCH_FOR_BORE_SPAN",
                "ambiguous": [], "n_acceptable": 0}

    ranked = sorted(acceptable, key=lambda t: (penalty(t[1]), t[1]["n_boxes"], t[1]["foot_delta"]))
    best_ch, best = ranked[0]
    best_pen = penalty(best)
    best_sig = _sig(best)

    # genuine rivals: a DIFFERENT segment (different station endpoints) with ~equal penalty
    # and no tiebreaker -> ambiguous fail-safe (parallel co-equal corridors).
    rivals = [(ch, sc) for (ch, sc) in ranked
              if _sig(sc) != best_sig and abs(penalty(sc) - best_pen) <= 5.0]
    if rivals:
        return {"tier": TIER_FAIL_SAFE, "winner": None, "caveat": None,
                "reason": "GE_2_COEQUAL_CANDIDATES_NO_TIEBREAKER",
                "ambiguous": [best_ch] + [c for c, _ in rivals], "n_acceptable": len(acceptable)}

    if (best["foot_delta"] <= tol["auto_foot"]
            and best["start_delta"] <= tol["auto_end"]
            and best["end_delta"] <= tol["auto_end"]):
        return {"tier": TIER_AUTO_SELECT, "winner": best_ch, "caveat": None,
                "reason": "EXACT_BOX_FOOTAGE_AND_ENDPOINTS",
                "ambiguous": [], "n_acceptable": len(acceptable)}

    caveats = []
    if best["start_delta"] > tol["auto_end"] or best["end_delta"] > tol["auto_end"]:
        caveats.append("INTERIOR_ENDPOINT")
    if best["foot_delta"] > tol["auto_foot"]:
        caveats.append("FOOTAGE_TOLERANCE")
    if best["multi_sheet"]:
        caveats.append("MATCHLINE_PAGE_FLIP")
    return {"tier": TIER_AUTO_PLACED_REQUIRES_APPROVAL, "winner": best_ch,
            "caveat": "|".join(caveats) or "REVIEW", "reason": "UNIQUE_BUT_CAVEATED",
            "ambiguous": [], "n_acceptable": len(acceptable)}
