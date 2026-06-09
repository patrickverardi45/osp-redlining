"""Point/extent matchers (convention-agnostic) for dialects whose plan evidence
locates a bore but does not author its footage (the bore log is the authority).

  * decide_by_containment — point anchors: place at the single anchor whose
    point falls in the bore span.
  * decide_by_extent — drawn segment extents: place when drawn geometry COVERS
    the bore span; AUTO only when the union of covering segments tightly and
    uniquely matches the span, else REVIEW (location confirmed); abstain when
    coverage is insufficient.
Honest abstain on no/insufficient evidence; REVIEW so a human approves.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

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
        return {"status": "ABSTAIN", "tier": "FAIL_SAFE", "reason": "NO_ANCHOR_IN_SPAN",
                "winner": None, "score": None, "caveats": [], "ambiguous": []}
    mid = (bore_start_ft + bore_end_ft) / 2.0
    winner = min(inside, key=lambda c: abs(_mid(c) - mid))
    return {"status": "REVIEW", "tier": "AUTO_PLACED_REQUIRES_APPROVAL",
            "reason": "POINT_ANCHOR_WITHIN_SPAN", "winner": [winner],
            "score": {"sheets": [winner.sheet]},
            "caveats": ["POINT_EXTENT", "LOCATION_ONLY"], "ambiguous": []}


def _covered_length(intervals: List[Tuple[float, float]], lo: float, hi: float) -> float:
    """Length of [lo,hi] covered by the union of intervals."""
    clipped = sorted((max(a, lo), min(b, hi)) for a, b in intervals if min(b, hi) > max(a, lo))
    covered = 0.0
    cur = None
    for a, b in clipped:
        if cur is None:
            cur = [a, b]
        elif a <= cur[1]:
            cur[1] = max(cur[1], b)
        else:
            covered += cur[1] - cur[0]
            cur = [a, b]
    if cur:
        covered += cur[1] - cur[0]
    return covered


def decide_by_extent(callouts: List[Callout], bore_start_ft: float, bore_end_ft: float,
                     span_ft: float, cover_min: float = 0.6, auto_tol: float = 25.0) -> Dict[str, Any]:
    lo, hi = min(bore_start_ft, bore_end_ft), max(bore_start_ft, bore_end_ft)
    overlapping = [c for c in callouts
                   if min(c.from_ft, c.to_ft) <= hi and max(c.from_ft, c.to_ft) >= lo]
    if not overlapping:
        return {"status": "ABSTAIN", "tier": "FAIL_SAFE", "reason": "NO_DRAWN_BORE_OVER_SPAN",
                "winner": None, "score": None, "caveats": [], "ambiguous": []}
    intervals = [(min(c.from_ft, c.to_ft), max(c.from_ft, c.to_ft)) for c in overlapping]
    cover = (_covered_length(intervals, lo, hi) / span_ft) if span_ft > 0 else 0.0
    if cover < cover_min:
        return {"status": "ABSTAIN", "tier": "FAIL_SAFE", "reason": "INSUFFICIENT_DRAWN_COVERAGE",
                "winner": None, "score": None, "caveats": [], "ambiguous": []}
    mid = (lo + hi) / 2.0
    winner = min(overlapping, key=lambda c: abs(_mid(c) - mid))
    umin = min(i[0] for i in intervals)
    umax = max(i[1] for i in intervals)
    tight = abs(umin - lo) <= auto_tol and abs(umax - hi) <= auto_tol
    if tight:
        return {"status": "AUTO_SELECT", "tier": "AUTO_SELECT",
                "reason": "DRAWN_BORE_EXTENT_MATCHES_SPAN", "winner": [winner],
                "score": {"sheets": [winner.sheet]}, "caveats": ["DRAWN_VECTOR_EXTENT"],
                "ambiguous": []}
    # Covers the span, but the covering geometry's endpoints are NOT a tight,
    # unique match to this bore's start/end. When a plan draws one continuous run
    # that is not segmented per bore, the drawn extent cannot delimit THIS bore:
    # location is confirmed (REVIEW) but the run is never tight enough to AUTO.
    # This is the correct ceiling, not a gap. See
    # truelinev2/docs/findings/m4-drawn-extent-not-per-bore.md.
    review_caveats = ["DRAWN_VECTOR_EXTENT", "LOCATION_ONLY"]
    if umin < lo - auto_tol or umax > hi + auto_tol:
        review_caveats.append("DRAWN_EXTENT_EXCEEDS_BORE_SPAN")
    return {"status": "REVIEW", "tier": "AUTO_PLACED_REQUIRES_APPROVAL",
            "reason": "DRAWN_EXTENT_COVERS_SPAN_NOT_TIGHT", "winner": [winner],
            "score": {"sheets": [winner.sheet]},
            "caveats": review_caveats, "ambiguous": []}
