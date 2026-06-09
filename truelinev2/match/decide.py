"""Tiering: scored chains -> AUTO_SELECT | REVIEW | ABSTAIN. Honest abstain.

Penalty over authored evidence so a coincidental sum of small/VACANT lateral
boxes cannot out-rank the true authored segment. Two co-equal different segments
with no tiebreaker -> abstain (never guess).
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from truelinev2.schema.models import Callout


def tolerances(span_ft: float) -> Dict[str, float]:
    return {"auto_foot": max(5.0, 0.015 * span_ft),
            "review_foot": max(20.0, 0.06 * span_ft),
            "auto_end": 5.0, "review_end": 8.0}


def penalty(sc: Dict[str, Any]) -> float:
    return (sc["foot_delta"] + 30.0 * sc["vacant"] + 8.0 * (sc["n_boxes"] - 1)
            + (sc["start_delta"] + sc["end_delta"]))


def _sig(sc: Dict[str, Any]) -> Tuple[str, str]:
    return (sc["chain_from"], sc["chain_to"])


def decide(scored: List[Tuple[List[Callout], Dict[str, Any]]], span_ft: float) -> Dict[str, Any]:
    tol = tolerances(span_ft)
    acceptable = [(ch, sc) for (ch, sc) in scored
                  if sc["start_delta"] <= tol["review_end"]
                  and sc["end_delta"] <= tol["review_end"]
                  and sc["foot_delta"] <= tol["review_foot"]]
    if not acceptable:
        return {"status": "ABSTAIN", "tier": "FAIL_SAFE",
                "reason": "NO_AUTHORED_BOX_MATCH_FOR_BORE_SPAN",
                "winner": None, "score": None, "caveats": [], "ambiguous": []}

    ranked = sorted(acceptable, key=lambda t: (penalty(t[1]), t[1]["n_boxes"], t[1]["foot_delta"]))
    best_ch, best = ranked[0]
    bp = penalty(best)
    bsig = _sig(best)
    rivals = [(ch, sc) for (ch, sc) in ranked
              if _sig(sc) != bsig and abs(penalty(sc) - bp) <= 5.0]
    if rivals:
        return {"status": "ABSTAIN", "tier": "FAIL_SAFE",
                "reason": "GE_2_COEQUAL_CANDIDATES_NO_TIEBREAKER",
                "winner": None, "score": None, "caveats": [],
                "ambiguous": [best_ch] + [c for c, _ in rivals]}

    if (best["foot_delta"] <= tol["auto_foot"]
            and best["start_delta"] <= tol["auto_end"]
            and best["end_delta"] <= tol["auto_end"]):
        return {"status": "AUTO_SELECT", "tier": "AUTO_SELECT",
                "reason": "EXACT_BOX_FOOTAGE_AND_ENDPOINTS",
                "winner": best_ch, "score": best, "caveats": [], "ambiguous": []}

    caveats: List[str] = []
    if best["start_delta"] > tol["auto_end"] or best["end_delta"] > tol["auto_end"]:
        caveats.append("INTERIOR_ENDPOINT")
    if best["foot_delta"] > tol["auto_foot"]:
        caveats.append("FOOTAGE_TOLERANCE")
    if best["multi_sheet"]:
        caveats.append("MATCHLINE_PAGE_FLIP")
    return {"status": "REVIEW", "tier": "AUTO_PLACED_REQUIRES_APPROVAL",
            "reason": "UNIQUE_BUT_CAVEATED", "winner": best_ch, "score": best,
            "caveats": caveats, "ambiguous": []}
