"""KMZ Matching Trust Slice B — match_review_queue projection.

Pure, deterministic projection from `STATE["pipeline_diag"]` into a
prioritized operator-review queue. Reads the existing per-group diagnostic
rows produced by `_rebuild_field_data_outputs` and surfaces only those
groups that need operator attention: abstained matches, ambiguous matches
that weren't conclusively resolved, V1 collision arbitrations, V4 LAWNDALE
rescues, and placed-with-low-confidence outcomes.

Operator trust signal:
- HIGH    — abstained groups and ambiguity-not-resolved cases need
            attention first (work is being blocked or could be wrong)
- MEDIUM  — collision-arbitration outcomes and low-confidence placements
            (a route was picked, but the cascade leaned heavily on a
            safety net or the score gap was narrow)
- LOW     — V4 LAWNDALE rescue successes (a route was picked, but only
            because the fallback rescuer fired — worth a review on
            non-Brenham packets)

This module is OBSERVATION ONLY. It NEVER touches matching, scoring,
selection, rendering, KMZ export, STATE, or anything other than the
input list of diag dicts. It does not import from `main.py`.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Mapping, Optional, Sequence

from app.core import brenham_plan_sheet_graph as _psg


SCHEMA_VERSION = "match-review-queue-1"

_ALL_STATUSES = (
    "abstained",
    "ambiguous",
    "collision_resolved",
    "rescued_v4",
    "placed_with_low_confidence",
)

# Score floor below which a successfully-placed group is still added to the
# queue under the `placed_with_low_confidence` status. Tuned conservatively;
# the canonical scoring range is [0, 1] (see `_score_route_candidate`).
LOW_CONFIDENCE_SCORE_FLOOR = 0.40


_PRIORITY_RANK: Dict[str, int] = {
    "high": 0,
    "medium": 1,
    "low": 2,
}


def _safe_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    return []


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return str(value)
    except Exception:
        return ""


def _safe_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _classify_status(entry: Dict[str, Any]) -> Optional[str]:
    """Pick the single most-actionable status label for an entry.

    Order of precedence (most-blocking first):
        abstained > ambiguous > collision_resolved > rescued_v4
        > placed_with_low_confidence > None (excluded from queue)

    Returns None when the entry does not need operator review.
    """
    stopped_at = _safe_str(entry.get("stopped_at")).lower()
    render_allowed = entry.get("render_allowed")
    selected_route_id = _safe_str(entry.get("selected_route_id"))
    ambiguity_status = _safe_str(entry.get("ambiguity_resolution_status")).lower()

    # 1. Abstain — explicit stopped_at marker OR render_block + no selection.
    if "abstain" in stopped_at:
        return "abstained"
    # The location-mismatch abstain marker uses stopped_at = "abstained_location_evidence_mismatch".
    # The V1-collision abstain may also leave selected_route_id empty + render_allowed=False.
    if render_allowed is False and not selected_route_id:
        return "abstained"

    # 2. Ambiguous-not-resolved.
    if ambiguity_status in {"still_review_required", "not_enough_plan_evidence"}:
        return "ambiguous"

    # 3. V4 rescue success — has rescue metadata AND a winning route.
    if isinstance(entry.get("location_mismatch_rescue_selected"), dict) and selected_route_id:
        return "rescued_v4"

    # 4. V1/V2 collision arbitration that produced a (possibly switched) winner.
    coll_meta = entry.get("anti_collapse_v2_attempt")
    if isinstance(coll_meta, dict) and coll_meta.get("alternate_chosen") and selected_route_id:
        return "collision_resolved"
    if isinstance(entry.get("same_route_anchor_collision"), dict) and render_allowed:
        return "collision_resolved"

    # 5. Placed-with-low-confidence — score below floor, but render allowed.
    if render_allowed and selected_route_id:
        top5 = _safe_list(entry.get("strict_top5"))
        if top5:
            top_score = _safe_float(top5[0].get("score") if isinstance(top5[0], dict) else None)
            if top_score is not None and top_score < LOW_CONFIDENCE_SCORE_FLOOR:
                return "placed_with_low_confidence"

    # 6. Everything else — placed_normal; excluded from queue.
    return None


def _priority_for(status: str, entry: Dict[str, Any]) -> str:
    """Priority calibration.

    HIGH    — abstained, ambiguous
    MEDIUM  — collision_resolved, placed_with_low_confidence
    LOW     — rescued_v4
    """
    if status in ("abstained", "ambiguous"):
        return "high"
    if status in ("collision_resolved", "placed_with_low_confidence"):
        return "medium"
    if status == "rescued_v4":
        return "low"
    return "low"


def _top_3_alternates(entry: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Project the existing `strict_top5` field into a top-3-alternates list.
    Pure projection — never mutates the entry.
    """
    top5 = _safe_list(entry.get("strict_top5"))
    out: List[Dict[str, Any]] = []
    selected_route_id = _safe_str(entry.get("selected_route_id"))
    for idx, item in enumerate(top5[:3]):
        if not isinstance(item, dict):
            continue
        rid = _safe_str(item.get("route_id"))
        is_selected = bool(rid) and rid == selected_route_id
        out.append({
            "route_id": rid or None,
            "route_name": _safe_str(item.get("route_name")) or None,
            "score": _safe_float(item.get("score")),
            "route_length_ft": _safe_float(item.get("route_length_ft")),
            "was_selected": is_selected,
        })
    return out


def _abstain_reason(entry: Dict[str, Any]) -> Optional[str]:
    """Return a stable abstain-reason string when the entry abstained.
    Reads only existing diagnostic fields; never derives new information.
    """
    stopped_at = _safe_str(entry.get("stopped_at"))
    if "abstain" in stopped_at.lower():
        return stopped_at
    reason = entry.get("abstain_reason")
    if isinstance(reason, dict):
        # Already a structured payload — keep verbatim.
        return _safe_str(reason.get("reason")) or None
    if isinstance(reason, str) and reason:
        return reason
    return None


def _evidence_summary(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Project evidence-bearing fields from the entry into a compact summary.
    Includes Stage A `print_sheet_index_source` attribution when present.
    Pure projection.
    """
    print_filter = entry.get("print_filter") or {}
    if not isinstance(print_filter, dict):
        print_filter = {}

    loc_mismatch = entry.get("location_evidence_mismatch")
    if not isinstance(loc_mismatch, dict):
        loc_mismatch = None

    # The KMZ-address-cluster evidence is surfaced today via the evidence
    # resolver and the V4 rescue meta. Read both where available.
    evidence_resolver = entry.get("evidence_resolver")
    if not isinstance(evidence_resolver, dict):
        evidence_resolver = None
    rescue_meta = entry.get("location_mismatch_rescue_selected")
    if not isinstance(rescue_meta, dict):
        rescue_meta = None

    notes_streets: List[str] = []
    if isinstance(loc_mismatch, dict):
        ns = loc_mismatch.get("notes_streets")
        if isinstance(ns, list):
            notes_streets = [str(s) for s in ns if isinstance(s, str)]
    if not notes_streets and isinstance(evidence_resolver, dict):
        ns = evidence_resolver.get("notes_streets")
        if isinstance(ns, list):
            notes_streets = [str(s) for s in ns if isinstance(s, str)]

    return {
        "print_tokens": [
            _safe_str(t) for t in _safe_list(print_filter.get("print_tokens"))
            if _safe_str(t)
        ],
        "print_sheet_index_source": _safe_str(
            print_filter.get("print_sheet_index_source")
        ) or None,
        "filter_applied": bool(print_filter.get("applied")),
        "street_hints": [
            _safe_str(s) for s in _safe_list(print_filter.get("street_hints"))
            if _safe_str(s)
        ],
        "allowed_route_ids": [
            _safe_str(r) for r in _safe_list(print_filter.get("allowed_route_ids"))
            if _safe_str(r)
        ],
        "notes_streets": notes_streets,
        "location_evidence_mismatch": loc_mismatch,
        "evidence_resolver_tag": evidence_resolver,
        "kmz_address_cluster_evidence": rescue_meta,
    }


def _safety_net_log(entry: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Project per-layer safety-net outcomes from the existing diagnostic
    fields. Pure projection — only includes layers that left a trace.
    """
    out: List[Dict[str, Any]] = []

    expansion = entry.get("auto_candidate_expansion")
    if isinstance(expansion, dict):
        out.append({"layer": "candidate_matrix_v1", "meta": expansion})

    v2 = entry.get("anti_collapse_v2_attempt")
    if isinstance(v2, dict):
        out.append({"layer": "anti_collapse_v2", "meta": v2})

    v4 = entry.get("location_mismatch_rescue_selected")
    if isinstance(v4, dict):
        out.append({"layer": "location_mismatch_rescue_v4", "outcome": "selected", "meta": v4})
    v4_rejected = entry.get("location_mismatch_rescue_rejected")
    if isinstance(v4_rejected, dict):
        out.append({"layer": "location_mismatch_rescue_v4", "outcome": "rejected", "meta": v4_rejected})

    window = entry.get("same_route_anchor_collision")
    if isinstance(window, dict):
        out.append({"layer": "collision_window_v2", "meta": window})

    loc_mismatch = entry.get("location_evidence_mismatch")
    if isinstance(loc_mismatch, dict):
        out.append({"layer": "location_evidence_mismatch", "meta": loc_mismatch})

    return out


def _build_row(entry: Dict[str, Any], status: str) -> Dict[str, Any]:
    """Assemble a single queue row from a pipeline_diag entry + classified
    status. Pure projection. Never mutates the entry.
    """
    return {
        "source_file": _safe_str(entry.get("source_file")) or None,
        "group_id": _safe_str(entry.get("group_id")) or None,
        "status": status,
        "priority": _priority_for(status, entry),
        "selected_route_id": _safe_str(entry.get("selected_route_id")) or None,
        "selected_route_name": _safe_str(entry.get("selected_route_name")) or None,
        "render_allowed": entry.get("render_allowed"),
        "render_block_reasons": [
            _safe_str(r) for r in _safe_list(entry.get("render_block_reasons"))
            if _safe_str(r)
        ],
        "abstain_reason": _abstain_reason(entry),
        "top_3_alternates": _top_3_alternates(entry),
        "evidence_summary": _evidence_summary(entry),
        "safety_net_log": _safety_net_log(entry),
        "ambiguity_resolution_status": _safe_str(
            entry.get("ambiguity_resolution_status")
        ) or None,
    }


def assemble_match_review_queue(
    pipeline_diag: Optional[Sequence[Dict[str, Any]]],
    *,
    plan_sheet_graph_inputs: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """Assemble the operator-review queue from a `pipeline_diag` list.

    Returns a dict:
      {
        "schema_version": "match-review-queue-1",
        "row_count": int,
        "counts_by_status": {abstained: int, ambiguous: int, ...},
        "counts_by_priority": {high: int, medium: int, low: int},
        "rows": List[row],   # priority-sorted
      }

    Sort key: priority rank ascending (high first), then source_file
    alphabetic, then group_id alphabetic — fully deterministic ordering.

    Pure. Never raises (returns empty queue on bad input). Never mutates
    the input.

    ``plan_sheet_graph_inputs`` (optional; default-OFF Brenham PSG precision
    evidence): a read-only ``{source_file: {prints, station_min_ft,
    station_max_ft, index_streets, notes_streets}}`` map. When provided (and
    non-empty), each queue row whose ``source_file`` resolves to an ACTIONABLE
    Brenham plan-sheet-graph status (``station_print_disjoint`` /
    ``external_packet_mismatch_possible`` / ``unknown``) gains a read-only
    ``plan_sheet_graph_evidence`` field. The noisy statuses (``within_corridor``,
    ``multi_corridor_span``) never attach a field. When the arg is ``None`` /
    empty, behavior — including the absence of the field — is byte-identical to
    pre-slice. This NEVER changes status classification, priority, counts,
    sort order, scoring, selection, or rendering. Observation only.
    """
    out: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "row_count": 0,
        "counts_by_status": {s: 0 for s in _ALL_STATUSES},
        "counts_by_priority": {"high": 0, "medium": 0, "low": 0},
        "rows": [],
    }
    if not isinstance(pipeline_diag, (list, tuple)):
        return out

    rows: List[Dict[str, Any]] = []
    for entry in pipeline_diag:
        if not isinstance(entry, dict):
            continue
        status = _classify_status(entry)
        if status is None:
            continue
        # Defensive deepcopy at projection boundary so the row references
        # cannot leak back into STATE via dict mutation upstream.
        row = _build_row(deepcopy(entry), status)
        # Brenham PSG precision evidence (default-OFF; attached only when the
        # caller passes inputs AND the status is actionable). Read-only field;
        # never alters classification / priority / counts / sort / routing.
        if plan_sheet_graph_inputs:
            sf = row.get("source_file")
            psg_in = plan_sheet_graph_inputs.get(sf) if sf else None
            if isinstance(psg_in, Mapping):
                evidence = _psg.build_review_evidence(
                    prints=psg_in.get("prints"),
                    station_min_ft=psg_in.get("station_min_ft"),
                    station_max_ft=psg_in.get("station_max_ft"),
                    notes_streets=psg_in.get("notes_streets"),
                    index_streets=psg_in.get("index_streets"),
                )
                if evidence is not None:
                    row["plan_sheet_graph_evidence"] = evidence
        rows.append(row)

    rows.sort(key=lambda r: (
        _PRIORITY_RANK.get(str(r.get("priority") or "low"), 99),
        str(r.get("source_file") or ""),
        str(r.get("group_id") or ""),
    ))

    for r in rows:
        s = r.get("status")
        if s in out["counts_by_status"]:
            out["counts_by_status"][s] += 1
        p = r.get("priority")
        if p in out["counts_by_priority"]:
            out["counts_by_priority"][p] += 1

    out["row_count"] = len(rows)
    out["rows"] = rows
    return out
