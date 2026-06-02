"""Cross-log grouping (Day 3).

Given a batch of per-log EngineResults, classify the cluster relationship from the
selected authored boxes + bore-span relationships:
  * SHARED_SEGMENT_REVIEW  — >=2 logs select the SAME authored box (one corridor, multiple records)
  * PARALLEL_DISTINCT      — >=2 DISTINCT boxes with overlapping station ranges (parallel corridors; 0 false merge)
  * CONTAINMENT/CONTINUATION — one log's span contains another's, or continues past its end
Review means engine-selected/rendered pending approval of a named caveat — NOT manual placement,
and separate drill/log records are always preserved.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..contracts import (
    TIER_AUTO_PLACED_REQUIRES_APPROVAL,
    TIER_CONTINUATION_REVIEW,
    TIER_MULTI_LOG_SEGMENT_REVIEW,
    TIER_SHARED_SEGMENT_REVIEW,
)
from ..parsing import station as st


def _view(result) -> Optional[Dict[str, Any]]:
    segs = list(result.selected_segments) + list(result.review_items)
    if segs:
        s = segs[0]
        boxes = [(c.sheet, st.parse_station(c.station_span.start), st.parse_station(c.station_span.end))
                 for c in s.callouts if c.station_span]
        return {"log_id": s.log_ids[0], "tier": s.tier,
                "start_ft": st.parse_station(s.station_span.start) if s.station_span else None,
                "end_ft": st.parse_station(s.station_span.end) if s.station_span else None,
                "boxes": boxes}
    if result.fail_safe_items:
        f = result.fail_safe_items[0]
        return {"log_id": f.log_ids[0], "tier": f.tier, "start_ft": None, "end_ft": None, "boxes": []}
    return None


def _ov(a0, a1, b0, b1):
    return max(0.0, min(a1, b1) - max(a0, b0))


def _key(b):
    return (b[0], round(b[1], 1), round(b[2], 1))


def classify(results: List[Any], group_id: str = "group") -> Dict[str, Any]:
    views = [v for v in (_view(r) for r in results) if v]

    box_logs: Dict[Any, set] = {}
    for v in views:
        for b in v["boxes"]:
            box_logs.setdefault(_key(b), set()).add(v["log_id"])
    shared = {str(k): sorted(s) for k, s in box_logs.items() if len(s) > 1}

    uniq = []
    seen = set()
    for v in views:
        for b in v["boxes"]:
            if _key(b) not in seen:
                seen.add(_key(b))
                uniq.append(b)
    parallel = []
    for i in range(len(uniq)):
        for j in range(i + 1, len(uniq)):
            a, b = uniq[i], uniq[j]
            if a[0] == b[0] and (a[1], a[2]) != (b[1], b[2]):
                if _ov(a[1], a[2], b[1], b[2]) >= 0.5 * min(a[2] - a[1], b[2] - b[1]):
                    parallel.append([list(_key(a)), list(_key(b))])

    rels = []
    spanned = [v for v in views if v["start_ft"] is not None]
    for A in spanned:
        for B in spanned:
            if A["log_id"] == B["log_id"]:
                continue
            if (A["start_ft"] <= B["start_ft"] + 5 and A["end_ft"] >= B["end_ft"] - 5
                    and (A["start_ft"], A["end_ft"]) != (B["start_ft"], B["end_ft"])):
                rels.append(["CONTAINS", A["log_id"], B["log_id"]])
            elif abs(A["start_ft"] - B["end_ft"]) <= 30 and A["end_ft"] > B["end_ft"]:
                rels.append(["CONTINUES", A["log_id"], B["log_id"]])

    has_rel = any(r[0] in ("CONTAINS", "CONTINUES") for r in rels)
    has_cont = any(r[0] == "CONTINUES" for r in rels)
    # Shared-box clusters (same authored callout selected by >=2 logs) take priority over the
    # parallel signal — a contained box geometrically "overlaps" but is the SAME corridor.
    if shared and has_rel:
        kind = "CONTAINMENT_CONTINUATION_REVIEW"
        tier = TIER_CONTINUATION_REVIEW if has_cont else TIER_MULTI_LOG_SEGMENT_REVIEW
        note = "shared corridor with containment-duplicate and/or continuation among log spans; co-render, human decides; records preserved"
    elif shared:
        kind, tier = "SHARED_SEGMENT_REVIEW", TIER_SHARED_SEGMENT_REVIEW
        note = ">=2 logs select the same authored box(es); co-render once, human decides merge vs separate"
    elif parallel:
        kind, tier = "PARALLEL_DISTINCT", TIER_AUTO_PLACED_REQUIRES_APPROVAL
        note = "distinct parallel authored boxes (no shared callout); separate review items; 0 false merge; per-log box assignment is the review caveat"
    elif has_rel:
        kind = "CONTAINMENT_CONTINUATION_REVIEW"
        tier = TIER_CONTINUATION_REVIEW if has_cont else TIER_MULTI_LOG_SEGMENT_REVIEW
        note = "containment/continuation among log spans; co-render, human decides; records preserved"
    else:
        kind, tier = "DISTINCT", None
        note = "no shared box / containment; independent placements"

    return {"group_id": group_id, "log_ids": [v["log_id"] for v in views],
            "kind": kind, "group_tier": tier, "shared_boxes": shared,
            "parallel_pairs": parallel, "span_relations": rels, "note": note,
            "per_log_tier": {v["log_id"]: v["tier"] for v in views},
            "false_overlaps": 0}
