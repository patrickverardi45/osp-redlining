"""KMZ Automatic Redline Placement — Trust Ledger projection.

Pure, deterministic, read-only projection from ``STATE["pipeline_diag"]`` (plus
the optional ``route_catalog``, ``coverage_sanity`` and Brenham PSG inputs) into
a per-group "trust ledger". For every bore-log group it emits one of three
machine-readable proof verdicts:

  - ``"proven"``        — the selected route is justified by a COMPLETE, citable
                          evidence chain: route geometry + bore-log station
                          range + candidate/anchor justification + route-index
                          consistency.
  - ``"abstained"``     — the engine declined to place (render not allowed or no
                          selected route); an exact abstain reason is recorded.
  - ``"missing_proof"`` — a route WAS placed (``render_allowed`` is True and a
                          ``selected_route_id`` is present) but the evidence
                          chain is incomplete. This is the dangerous "silent
                          placement" class, surfaced honestly rather than
                          reported as proven.

``"proven"`` means *the placement is justified by the recorded evidence*. It is
NOT a field-correctness claim and never says a placement "looks right".

Route-index evidence and the PSG warning are kept as SEPARATE, never-merged
signals. A row can be route-index ``consistent`` AND carry a PSG
``external_packet_mismatch_possible`` warning at the same time — those are
orthogonal axes (one checks selected-route ∈ print-index allowed set, the other
checks bore-log notes street vs the print sheet's streets).

This module is OBSERVATION ONLY. It NEVER touches matching, scoring, selection,
rendering, KMZ export, or STATE. It does not import from ``main.py`` and never
raises (returns an empty ledger on bad input).

It depends on the additive ``_diag`` proof fields written during rebuild
(``group_id``, ``selected_combined_score``, ``mapping_summary``,
``candidate_rankings_top``, ``selected_anchor_reasons``). On sessions rebuilt
BEFORE those fields existed, the absent fields are reported in ``missing_links``
and the placed row is classified ``missing_proof`` — honest degradation, never a
fake ``proven``.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Mapping, Optional, Sequence

from app.core import brenham_plan_sheet_graph as _psg


SCHEMA_VERSION = "trust-ledger-1"

_PROOF_STATUSES = ("proven", "abstained", "missing_proof")

# Operator-attention sort: surface the dangerous class first, then abstains
# (work held back), then proven placements.
_PROOF_SORT_RANK: Dict[str, int] = {
    "missing_proof": 0,
    "abstained": 1,
    "proven": 2,
}


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return str(value)
    except Exception:
        return ""


def _safe_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    return []


def _safe_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _route_index_verdict(selected_route_id: str, allowed_route_ids: Sequence[str]) -> str:
    """Mirror the frontend ``getPdfRouteVerdict`` / ``indexAgreementVerdict``:
    selected ∈ allowed -> consistent; selected ∉ non-empty allowed -> suspect;
    no selection OR empty allowed set -> not_proven. Route-index ONLY — never
    consults streets, stations, or PSG.
    """
    sel = _safe_str(selected_route_id)
    allowed = [_safe_str(r) for r in _safe_list(allowed_route_ids) if _safe_str(r)]
    if not sel:
        return "not_proven"
    if not allowed:
        return "not_proven"
    return "consistent" if sel in allowed else "suspect"


def _derive_abstain_reason(entry: Mapping[str, Any]) -> str:
    """Resolve the machine-readable abstain reason for a non-placed group.
    Reads only existing diagnostic fields; never derives new information.
    """
    stopped_at = _safe_str(entry.get("stopped_at"))
    if stopped_at and stopped_at.lower() != "none":
        return stopped_at
    reason = entry.get("abstain_reason")
    if isinstance(reason, Mapping):
        r = _safe_str(reason.get("reason"))
        if r:
            return r
    elif isinstance(reason, str) and reason:
        return reason
    rbr = [_safe_str(r) for r in _safe_list(entry.get("render_block_reasons")) if _safe_str(r)]
    if rbr:
        return "render_blocked: " + ", ".join(rbr)
    return "not_placed"


def _has_rescue_reason(entry: Mapping[str, Any]) -> bool:
    """A placed route may be justified by a recorded safety-net rescue even when
    it is not in the original strict rankings (V4 LAWNDALE rescue or the V2
    alternate-search). These are explicit, audited records — not guesses.
    """
    return (
        isinstance(entry.get("location_mismatch_rescue_selected"), dict)
        or isinstance(entry.get("route_collision_alternate_selected"), dict)
    )


def _psg_warning_for(
    source_file: Optional[str],
    plan_sheet_graph_inputs: Optional[Mapping[str, Mapping[str, Any]]],
) -> Optional[Dict[str, Any]]:
    """Project the Brenham PSG warning (status + actionability) for a row, if
    inputs are provided and the status is actionable. SEPARATE from the
    route-index verdict; never merged. Returns None when no warning applies.
    """
    if not plan_sheet_graph_inputs or not source_file:
        return None
    psg_in = plan_sheet_graph_inputs.get(source_file)
    if not isinstance(psg_in, Mapping):
        return None
    try:
        evidence = _psg.build_review_evidence(
            prints=psg_in.get("prints"),
            station_min_ft=psg_in.get("station_min_ft"),
            station_max_ft=psg_in.get("station_max_ft"),
            notes_streets=psg_in.get("notes_streets"),
            index_streets=psg_in.get("index_streets"),
        )
    except Exception:
        return None
    if not isinstance(evidence, Mapping):
        return None
    return {
        "status": _safe_str(evidence.get("status")) or None,
        "actionability": _safe_str(evidence.get("actionability")) or None,
    }


def _build_ledger_row(
    entry: Mapping[str, Any],
    *,
    catalog_route_ids: Optional[set],
    plan_sheet_graph_inputs: Optional[Mapping[str, Mapping[str, Any]]],
) -> Dict[str, Any]:
    """Assemble a single trust-ledger row from a (deep-copied) pipeline_diag
    entry. Pure projection — never mutates the entry, never recomputes scoring.
    """
    source_file = _safe_str(entry.get("source_file")) or None
    selected_route_id = _safe_str(entry.get("selected_route_id")) or None
    allowed_route_ids = [
        _safe_str(r) for r in _safe_list(entry.get("strict_allowed_route_ids")) if _safe_str(r)
    ]
    print_tokens = [_safe_str(t) for t in _safe_list(entry.get("print_tokens")) if _safe_str(t)]
    verdict = _route_index_verdict(selected_route_id or "", allowed_route_ids)

    render_allowed = entry.get("render_allowed")
    placed = (render_allowed is True) and bool(selected_route_id)

    # ── Geometry evidence ──────────────────────────────────────────────────
    selected_len = _safe_float(entry.get("selected_route_length_ft"))
    route_in_catalog: Optional[bool]
    if catalog_route_ids is not None:
        route_in_catalog = bool(selected_route_id) and selected_route_id in catalog_route_ids
        geometry_basis = "route_catalog"
        geometry_present = route_in_catalog is True
    else:
        route_in_catalog = None
        geometry_basis = "selected_route_length_ft"
        geometry_present = bool(selected_len and selected_len > 0)

    # ── Station evidence ───────────────────────────────────────────────────
    min_ft = _safe_float(entry.get("min_station_ft"))
    max_ft = _safe_float(entry.get("max_station_ft"))
    station_present = (min_ft is not None) and (max_ft is not None)

    # ── Mapping / anchor evidence (additive _diag field) ───────────────────
    mapping_raw = entry.get("mapping_summary")
    if not isinstance(mapping_raw, Mapping):
        mapping_raw = {}
    anchored_start = mapping_raw.get("anchored_start_ft")
    anchored_end = mapping_raw.get("anchored_end_ft")
    mapping_present = (anchored_start is not None) and (anchored_end is not None)

    # ── Candidate / anchor evidence (additive _diag field) ─────────────────
    candidate_top: List[Dict[str, Any]] = []
    for r in _safe_list(entry.get("candidate_rankings_top")):
        if isinstance(r, Mapping):
            candidate_top.append({
                "route_id": _safe_str(r.get("route_id")) or None,
                "score": _safe_float(r.get("score")),
                "score_breakdown": dict(r.get("score_breakdown")) if isinstance(r.get("score_breakdown"), Mapping) else {},
            })
    selected_in_rankings = bool(selected_route_id) and any(
        c.get("route_id") == selected_route_id for c in candidate_top
    )
    has_rescue = _has_rescue_reason(entry)
    selected_combined_score = _safe_float(entry.get("selected_combined_score"))

    # ── PSG warning (orthogonal, never merged with route-index verdict) ────
    psg_warning = _psg_warning_for(source_file, plan_sheet_graph_inputs)

    # ── Classify ───────────────────────────────────────────────────────────
    missing_links: List[str] = []
    abstain_reason: Optional[str] = None
    if not placed:
        proof_status = "abstained"
        abstain_reason = _derive_abstain_reason(entry)
        evidence_chain_complete = False
    else:
        if not geometry_present:
            missing_links.append("route_geometry_absent")
        if not station_present:
            missing_links.append("station_range_absent")
        if not mapping_present:
            missing_links.append("mapping_absent")
        if not (selected_in_rankings or has_rescue):
            missing_links.append("no_candidate_or_rescue_justification")
        if verdict != "consistent":
            missing_links.append("route_index_" + verdict)
        if missing_links:
            proof_status = "missing_proof"
            evidence_chain_complete = False
        else:
            proof_status = "proven"
            evidence_chain_complete = True

    return {
        "source_file": source_file,
        "group_id": _safe_str(entry.get("group_id")) or None,
        "group_idx": entry.get("group_idx") if isinstance(entry.get("group_idx"), int) else None,
        "selected_route_id": selected_route_id,
        "selected_route_name": _safe_str(entry.get("selected_route_name")) or None,
        "render_allowed": render_allowed,
        "proof_status": proof_status,
        "evidence_chain_complete": evidence_chain_complete,
        "missing_links": missing_links,
        "abstain_reason": abstain_reason,
        # GROUP 1 — route-index evidence (print-token -> route consistency)
        "route_index_evidence": {
            "selected_route_id": selected_route_id,
            "allowed_route_ids": allowed_route_ids,
            "print_tokens": print_tokens,
            "verdict": verdict,
        },
        # GROUP 2 — PSG warning (SEPARATE; orthogonal to route-index)
        "psg_warning": psg_warning,
        # GROUP 3 — geometry / station evidence
        "geometry_summary": {
            "route_length_ft": selected_len,
            "route_in_catalog": route_in_catalog,
            "geometry_basis": geometry_basis,
            "min_station_ft": min_ft,
            "max_station_ft": max_ft,
        },
        # GROUP 4 — candidate / anchor evidence
        "candidate_summary": {
            "selected_combined_score": selected_combined_score,
            "selected_in_rankings": selected_in_rankings,
            "has_rescue_reason": has_rescue,
            "top": candidate_top,
        },
        "mapping_summary": {
            "mode": _safe_str(mapping_raw.get("mode")) or None,
            "anchor_offset_ft": _safe_float(mapping_raw.get("anchor_offset_ft")),
            "anchored_start_ft": _safe_float(anchored_start),
            "anchored_end_ft": _safe_float(anchored_end),
            "mapping_present": mapping_present,
        },
        "selected_anchor_reasons": [
            _safe_str(r) for r in _safe_list(entry.get("selected_anchor_reasons")) if _safe_str(r)
        ],
    }


def _coverage_sanity_summary(coverage_sanity: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(coverage_sanity, Mapping):
        return None
    return {
        "schema_version": _safe_str(coverage_sanity.get("schema_version"))
        or _safe_str(coverage_sanity.get("schema"))
        or None,
        "placed_group_count": coverage_sanity.get("placed_group_count"),
        "abstained_group_count": coverage_sanity.get("abstained_group_count"),
        "total_groups": coverage_sanity.get("total_groups"),
        "same_route_anchor_collision_count": len(
            _safe_list(coverage_sanity.get("same_route_anchor_collisions"))
        ),
        "same_route_window_decision_count": len(
            _safe_list(coverage_sanity.get("same_route_window_decisions"))
        ),
    }


def assemble_trust_ledger(
    pipeline_diag: Optional[Sequence[Dict[str, Any]]],
    *,
    route_catalog: Optional[Sequence[Mapping[str, Any]]] = None,
    coverage_sanity: Any = None,
    plan_sheet_graph_inputs: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """Assemble the per-group trust ledger from a ``pipeline_diag`` list.

    Returns:
      {
        "schema_version": "trust-ledger-1",
        "row_count": int,
        "counts": {"proven": int, "abstained": int, "missing_proof": int},
        "silent_placement_count": int,   # == counts["missing_proof"]
        "psg_warning_count": int,
        "coverage_sanity_summary": {...} | None,
        "rows": [row, ...],              # sorted: missing_proof, abstained, proven
      }

    One row per pipeline_diag entry (per group). Pure; never raises (empty
    ledger on bad input); never mutates the input. ``route_catalog`` is used
    only to verify selected-route geometry exists; ``coverage_sanity`` only
    populates a top-level summary; ``plan_sheet_graph_inputs`` only attaches the
    orthogonal PSG warning. NONE of them change matching/scoring/selection.
    """
    out: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "row_count": 0,
        "counts": {s: 0 for s in _PROOF_STATUSES},
        "silent_placement_count": 0,
        "psg_warning_count": 0,
        "coverage_sanity_summary": None,
        "rows": [],
    }
    if not isinstance(pipeline_diag, (list, tuple)):
        return out

    # Treat the route catalog as an authoritative geometry source only when it
    # is present AND non-empty; otherwise fall back to the route-length proxy so
    # a momentarily-empty catalog never demotes every placement to missing_proof.
    catalog_route_ids: Optional[set] = None
    if isinstance(route_catalog, (list, tuple)) and len(route_catalog) > 0:
        catalog_route_ids = set()
        for r in route_catalog:
            if isinstance(r, Mapping):
                rid = _safe_str(r.get("route_id"))
                if rid:
                    catalog_route_ids.add(rid)

    rows: List[Dict[str, Any]] = []
    for entry in pipeline_diag:
        if not isinstance(entry, dict):
            continue
        # Defensive deepcopy at the projection boundary so row references can
        # never leak back into STATE via dict mutation upstream.
        rows.append(
            _build_ledger_row(
                deepcopy(entry),
                catalog_route_ids=catalog_route_ids,
                plan_sheet_graph_inputs=plan_sheet_graph_inputs,
            )
        )

    rows.sort(key=lambda r: (
        _PROOF_SORT_RANK.get(_safe_str(r.get("proof_status")), 99),
        _safe_str(r.get("source_file")),
        r.get("group_idx") if isinstance(r.get("group_idx"), int) else 99999,
        _safe_str(r.get("group_id")),
    ))

    for r in rows:
        s = r.get("proof_status")
        if s in out["counts"]:
            out["counts"][s] += 1
        if r.get("psg_warning"):
            out["psg_warning_count"] += 1

    out["silent_placement_count"] = out["counts"]["missing_proof"]
    out["row_count"] = len(rows)
    out["coverage_sanity_summary"] = _coverage_sanity_summary(coverage_sanity)
    out["rows"] = rows
    return out
