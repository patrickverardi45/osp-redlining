"""Containment matcher (convention-agnostic): place a bore at the point-extent
callout within its span. For dialects (e.g. ODOT) whose plan evidence locates a
bore but does not author its footage.

``tol_ft`` absorbs the offset between a directional-bore NOTE's text position and
the bored segment's true station extent (the callout text is placed near, not
exactly on, the bore). Honest abstain when no anchor falls in the (tolerant)
span. REVIEW (location-only) so a human approves before closeout.
"""
from __future__ import annotations

from typing import Any, Dict, List

from truelinev2.schema.models import Callout


def _mid(c: Callout) -> float:
    return (c.from_ft + c.to_ft) / 2.0


def decide_by_containment(callouts: List[Callout], bore_start_ft: float,
                          bore_end_ft: float, span_ft: float,
                          tol_ft: float = 25.0) -> Dict[str, Any]:
    lo = min(bore_start_ft, bore_end_ft) - tol_ft
    hi = max(bore_start_ft, bore_end_ft) + tol_ft
    inside = [c for c in callouts if lo <= _mid(c) <= hi]
    if not inside:
        return {"status": "ABSTAIN", "tier": "FAIL_SAFE", "reason": "NO_DIRBORE_IN_BORE_SPAN",
                "winner": None, "score": None, "caveats": [], "ambiguous": []}
    mid = (bore_start_ft + bore_end_ft) / 2.0
    winner = min(inside, key=lambda c: abs(_mid(c) - mid))
    return {"status": "REVIEW", "tier": "AUTO_PLACED_REQUIRES_APPROVAL",
            "reason": "ODOT_DIRBORE_WITHIN_BORE_SPAN", "winner": [winner],
            "score": {"sheets": [winner.sheet]},
            "caveats": ["ODOT_POINT_EXTENT", "LOCATION_ONLY"], "ambiguous": []}
