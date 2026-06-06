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


# ─── PDF-first review-reason normalizer (Monday hardening — item 6) ───────────
# Pure, ADDITIVE projection of an already-emitted PDF-first ``geo`` evidence block
# into one operator-facing "why it drew / why it abstained" record. Reads ONLY
# fields the engine + resolver-consult layers already computed (geometry_status,
# frame chainage, matchline_resolution, physical_anchor, cross_sheet_seam_stitch
# reasons/discriminators, pdf_path_trace status). It NEVER changes any draw,
# abstain, placement, scoring, or geometry decision — it only explains them.
# Null-safe: returns None when there is no geo to summarize (so the caller
# attaches the key only when meaningful; flag-OFF => key absent => byte-identical).
# Never raises; never mutates its input.

REVIEW_REASON_SCHEMA_VERSION = "pdf-first-review-reason-1"


def _dedup_str(items: Sequence[Any]) -> List[str]:
    seen: set = set()
    out: List[str] = []
    for it in items:
        s = _safe_str(it).strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _as_mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _is_resolved_status(status: Optional[str]) -> bool:
    s = (status or "").upper()
    return s.endswith("_RESOLVED") or "RESOLVED" in s


def build_review_reason(geo: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    """Normalize a PDF-first ``geo`` block into an operator review reason.

    Pure, additive, read-only. Returns a ``{schema_version, code, message,
    discriminators, missing, evidence}`` record, or ``None`` when there is no geo
    evidence to explain. NEVER alters any draw/abstain/placement/geometry
    decision and NEVER raises. The ``discriminators``/``missing`` fields make an
    abstain explainable to a reviewer (missing matchline, unclear handhole,
    ambiguous offset, station-direction problem, endpoint not bound, multiple
    candidate paths, …); the ``evidence`` field echoes the proof the engine used
    (station/chainage frame, matchline + sheets, BOC offset, physical anchor).
    """
    try:
        if not isinstance(geo, Mapping):
            return None
        frame = _as_mapping(geo.get("frame"))
        mlr = _as_mapping(geo.get("matchline_resolution"))
        phys = _as_mapping(geo.get("physical_anchor"))
        seam = _as_mapping(geo.get("cross_sheet_seam_stitch"))
        trace = _as_mapping(geo.get("pdf_path_trace"))
        redline = _as_mapping(geo.get("pdf_redline"))

        geometry_status = _safe_str(geo.get("geometry_status")) or None
        discriminators: List[Dict[str, Any]] = []
        missing: List[str] = []

        # Named matchline binding (item 2).
        ml_status = _safe_str(mlr.get("status")) or None
        ml_class = _safe_str(mlr.get("class")) or None
        if ml_status:
            discriminators.append({
                "name": "named_matchline",
                "ok": _is_resolved_status(ml_status),
                "detail": ml_class or ml_status,
            })

        # Physical handhole identity (item 3): real structure symbol vs text label.
        phys_resolved = phys.get("resolved")
        # Item 3 enrichment (evidence-ONLY): nearby NON-allowed structures the layer allow-list
        # rejected (TEL-HH / FLOWER POT / HOUSES), aggregated from the connector start/end (or a
        # single-anchor result). NEVER affects any draw/abstain decision — display only.
        _rej: List[Dict[str, Any]] = []
        for _src in (phys, _as_mapping(phys.get("start")), _as_mapping(phys.get("end"))):
            for _r in _safe_list(_src.get("rejected_candidates")):
                if isinstance(_r, Mapping):
                    _lay = _safe_str(_r.get("layer"))
                    if _lay:
                        _rej.append({"layer": _lay, "reason": _safe_str(_r.get("reason")) or "layer_not_allowed"})
        _rej_layers: List[str] = []
        for _r in _rej:
            if _r["layer"] not in _rej_layers:
                _rej_layers.append(_r["layer"])
        if isinstance(phys_resolved, bool):
            _detail = ("anchored to authored structure symbol" if phys_resolved
                       else (_safe_str(phys.get("reason")) or "text-label fallback"))
            if phys_resolved and _rej_layers:
                _detail = _detail + " (preferred over nearby " + ", ".join(_rej_layers[:3]) + ")"
            discriminators.append({
                "name": "physical_handhole_anchor",
                "ok": phys_resolved,
                "detail": _detail,
            })
            if not phys_resolved:
                missing.append(_safe_str(phys.get("reason")) or "physical_handhole_not_uniquely_bound")

        # Cross-sheet seam discriminators (items 1/2/5) + per-segment abstain reasons.
        for d in _safe_list(seam.get("discriminators")):
            if isinstance(d, Mapping):
                discriminators.append({
                    "name": _safe_str(d.get("name")) or "discriminator",
                    "ok": bool(d.get("ok")),
                    "detail": _safe_str(d.get("detail")) or _safe_str(d.get("reason")) or None,
                })
            elif _safe_str(d):
                discriminators.append({"name": _safe_str(d), "ok": True, "detail": None})
        seam_reason = _safe_str(seam.get("reason")) or None
        if seam_reason:
            missing.append(seam_reason)
        for seg in _safe_list(seam.get("segments")):
            if not isinstance(seg, Mapping):
                continue
            st = _safe_str(seg.get("status"))
            if "abstain" in st.lower():
                sheet = seg.get("sheet")
                rs = _safe_str(seg.get("reason")) or st
                missing.append(f"sheet {sheet}: {rs}" if sheet is not None else rs)

        # Station / chainage frame evidence (item 1).
        cs = _safe_float(frame.get("chainage_start_ft"))
        ce = _safe_float(frame.get("chainage_end_ft"))
        axis = _safe_str(frame.get("axis")) or None
        eqs = [_safe_str(e) for e in _safe_list(frame.get("eqs_used")) if _safe_str(e)]
        station_frame = None
        if cs is not None or ce is not None or axis or eqs:
            station_frame = {
                "chainage_start_ft": cs,
                "chainage_end_ft": ce,
                "axis": axis,
                "eqs_used": eqs,
                "multi_sheet": bool(frame.get("multi_sheet")),
            }

        # BOC / offset (item 4) + matchline sheets / HH-HH span.
        boc_ft = _safe_float(mlr.get("boc_ft"))
        if boc_ft is None:
            boc_ft = _safe_float(geo.get("boc_ft"))
        hh_hh_ft = _safe_float(mlr.get("hh_hh_ft"))
        sheets = [int(s) for s in _safe_list(mlr.get("sheets"))
                  if isinstance(s, (int, float)) and not isinstance(s, bool)]

        # Did the engine draw an authored overlay?
        drawn = bool(_safe_str(trace.get("artifact_name")) or _safe_str(redline.get("artifact_name")))
        missing = _dedup_str(missing)

        # Presentation only — code + human message.
        if missing and not drawn:
            code = "abstained"
            head = "Abstained — authored PDF evidence did not prove the path."
            message = f"{head} Missing: {'; '.join(missing[:3])}" if missing else head
        elif geometry_status and _is_resolved_status(geometry_status):
            code = geometry_status.lower()
            kind = "matchline" if "MATCHLINE" in geometry_status.upper() else "station"
            message = f"Drew authored {kind}-frame evidence — placement proven."
        elif drawn:
            code = "authored_trace"
            message = "Drew an authored bore-path trace from the PDF's CAD layers."
        else:
            code = (geometry_status or "review").lower()
            message = "Review-grade evidence; not promoted to a drawn placement."

        evidence = {
            "geometry_status": geometry_status,
            "station_frame": station_frame,
            "matchline": ({"status": ml_status, "class": ml_class, "sheets": sheets, "hh_hh_ft": hh_hh_ft}
                          if (ml_status or sheets) else None),
            "physical_anchor": ({"resolved": phys_resolved, "reason": _safe_str(phys.get("reason")) or None,
                                 **({"rejected": _rej[:5]} if _rej else {})}
                                if isinstance(phys_resolved, bool) else None),
            "boc_ft": boc_ft,
        }

        if not (discriminators or missing or station_frame or ml_status
                or isinstance(phys_resolved, bool) or geometry_status or drawn):
            return None

        return {
            "schema_version": REVIEW_REASON_SCHEMA_VERSION,
            "code": code,
            "message": message,
            "discriminators": discriminators,
            "missing": missing,
            "evidence": evidence,
        }
    except Exception:
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
            _safe_str(t) for t in _safe_list(
                print_filter.get("print_tokens") or entry.get("print_tokens")
            )
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
            # Real pipeline_diag entries expose the print-filter result at the
            # top-level `strict_allowed_route_ids` (main.py `_diag`), NOT under a
            # `print_filter` sub-dict. Prefer print_filter (forward-compat /
            # synthetic test entries), then fall back to the actual diag field —
            # without this every live row has an empty set and reads Not proven.
            _safe_str(r) for r in _safe_list(
                print_filter.get("allowed_route_ids") or entry.get("strict_allowed_route_ids")
            )
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


# ─────────────────────────────────────────────────────────────────────────────
# GAC Sprint 1 — per-log redline PLACEMENT PROOF (read-only attribution).
#
# Separate from the operator-review queue above (which intentionally surfaces
# ONLY groups needing attention, so cleanly-placed logs are excluded). This
# projection covers EVERY bore-log in pipeline_diag and answers, per log: which
# route did the redline land on, and on WHAT EVIDENCE. It exists because the
# production Render shell crashes — this makes per-log placement provable inside
# the app instead of via a shell.
#
# Pure. Reads ONLY existing pipeline_diag `_diag` fields (never recomputes
# matching / scoring / geometry / selection). Station-point and segment counts
# are NOT present on `_diag`; the caller joins them in via `counts_by_source`,
# aggregated from the already-persisted STATE["station_points"] /
# STATE["redline_segments"] (which are exactly what the map renders). When that
# render is absent, counts are None.
# ─────────────────────────────────────────────────────────────────────────────

PLACEMENT_PROOF_SCHEMA_VERSION = "placement-proof-1"

_PLACEMENT_EVIDENCE_SOURCES = (
    "pdf_ap_authoritative",
    "print_index",
    "geometry_fallback",
    "abstained",
)

# Evidence-source precedence when a single log spans multiple print-groups
# (placed wins over abstained; PDF-AP wins over print-index wins over geometry).
_PLACEMENT_EVIDENCE_RANK: Dict[str, int] = {
    "pdf_ap_authoritative": 0,
    "print_index": 1,
    "geometry_fallback": 2,
    "abstained": 3,
}


def classify_placement(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Classify ONE pipeline_diag group into a placement-attribution record.

    Pure projection of existing `_diag` fields. Precedence (highest first):
        pdf_ap_authoritative > abstained > print_index > geometry_fallback

    - ``pdf_ap_authoritative`` — ``_diag["pdf_ap_route_authoritative"].applied``
      is truthy (the PDF plan-sheet / AP route won over the hardcoded index).
    - ``abstained`` — a real abstain marker is set (``stopped_at`` other than the
      placed-but-not-rendered ``render_gate_blocked``), or render was blocked
      with no selected route.
    - ``print_index`` — a route was selected AND the hardcoded print-sheet index
      drove the candidate restriction (``strict_allowed_route_ids`` non-empty).
    - ``geometry_fallback`` — a route was selected with no allow-set restriction
      (the hardcoded index did not resolve; pure geometry proximity placed it).

    Returns ``{source_file, selected_route_id, evidence_source, dist_ft,
    abstain_reason}``. ``dist_ft`` is the nearest terminal→corridor haversine
    from the (proof-slice-only) PDF-AP shadow when present, else ``None``.
    """
    d = entry or {}
    source_file = _safe_str(d.get("source_file")) or None
    selected_route_id = _safe_str(d.get("selected_route_id")) or None
    render_allowed = d.get("render_allowed")
    stopped_at = _safe_str(d.get("stopped_at"))
    strict_allowed = _safe_list(d.get("strict_allowed_route_ids"))

    auth = d.get("pdf_ap_route_authoritative")
    auth_applied = isinstance(auth, dict) and bool(auth.get("applied"))

    shadow = d.get("pdf_ap_route_shadow")
    shadow = shadow if isinstance(shadow, dict) else {}
    nearest = shadow.get("nearest_routes")
    nearest = nearest if isinstance(nearest, list) else []
    dist_ft: Optional[float] = None
    if nearest and isinstance(nearest[0], dict):
        dist_ft = _safe_float(nearest[0].get("dist_ft"))

    # "render_gate_blocked" is placed-but-not-rendered — NOT a true abstain
    # (mirrors the downstream convention in main.py that treats it separately).
    is_abstain = bool(stopped_at) and stopped_at.lower() != "render_gate_blocked"
    if not is_abstain and render_allowed is False and not selected_route_id:
        is_abstain = True

    if auth_applied:
        evidence_source = "pdf_ap_authoritative"
    elif is_abstain or not selected_route_id:
        evidence_source = "abstained"
    elif strict_allowed:
        evidence_source = "print_index"
    else:
        evidence_source = "geometry_fallback"

    abstain_reason: Optional[str] = None
    if evidence_source == "abstained":
        abstain_reason = (
            (_safe_str(stopped_at) or None)
            or _abstain_reason(d)
            or (_safe_str(shadow.get("reason")) or None)
        )

    return {
        "source_file": source_file,
        "selected_route_id": selected_route_id if evidence_source != "abstained" else None,
        "evidence_source": evidence_source,
        "dist_ft": dist_ft,
        "abstain_reason": abstain_reason,
    }


# Target #12 — terminus-aware LANE re-grade. Maps the Target #11 terminus work-type
# (from classify_terminus_type) to a placement LANE + disposition for operator review.
# Pure presentation; backbone_ap_candidate is True ONLY for backbone_ap_bore (a bore
# whose run ENDS at a TERMINAL PORT HH). flower_pot_drop / main_chain_high_station /
# multi_drive_unknown / unknown_insufficient are NEVER backbone-safe. The classifier
# itself lives in pdf_ap_route_resolver; this module only buckets its result.
_TERMINUS_REGRADE_SOURCE = "target10_verified_run_endpoint_table"
_TERMINUS_LANE_MAP = {
    "flower_pot_drop": ("DROP", "drop_lane_only_blocked_from_backbone"),
    "backbone_ap_bore": ("BACKBONE_AP", "future_narrow_backbone_ap_candidate"),
    "main_chain_high_station": ("MAIN_CHAIN_HIGH_STATION", "future_absolute_stationing_candidate"),
    "multi_drive_unknown": ("MULTI_DRIVE_UNKNOWN", "blocked_pending_stronger_evidence"),
    "unknown_insufficient": ("UNKNOWN", "blocked_insufficient_evidence"),
}


def _terminus_lane_record(classification: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    """Pure: map a ``classify_terminus_type`` result -> a placement-lane review record.
    ``backbone_ap_candidate`` is True ONLY for the backbone_ap_bore work-type; every
    other type (esp. flower_pot_drop) is blocked from backbone placement. No log is
    placement-validated, so ``backbone_promotion_ready`` is always False (candidate !=
    ready). Returns None for a non-dict input. Never raises."""
    if not isinstance(classification, Mapping):
        return None
    ttype = str(classification.get("terminus_type") or "unknown_insufficient")
    lane, disposition = _TERMINUS_LANE_MAP.get(ttype, ("UNKNOWN", "blocked_insufficient_evidence"))
    return {
        "lane": lane,
        "terminus_type": ttype,
        "confidence": classification.get("confidence"),
        "disposition": disposition,
        "backbone_ap_candidate": (lane == "BACKBONE_AP"),
        "backbone_promotion_ready": False,
        "evidence": classification.get("evidence"),
        "source": classification.get("source"),
    }


def assemble_placement_proof(
    pipeline_diag: Optional[Sequence[Dict[str, Any]]],
    *,
    counts_by_source: Optional[Mapping[str, Mapping[str, Any]]] = None,
    terminus_lane_by_source: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Per-LOG redline placement-proof report over the whole session.

    One row per ``source_file`` (a log may span several print-groups; they are
    aggregated to the most-authoritative classification so station-point /
    segment counts are never double-counted). Pure projection of
    ``pipeline_diag`` via :func:`classify_placement`. Never raises; never
    mutates the input.

    ``counts_by_source`` (optional): a read-only
    ``{source_file: {"station_pts": int, "segs": int}}`` map the caller derives
    from the persisted rendered geometry (``STATE["station_points"]`` /
    ``STATE["redline_segments"]``). When provided, per-log + total counts are
    filled in and ``totals`` reconciles to the rendered map. When ``None``,
    counts are ``None`` (the report still classifies evidence_source).

    Returns ``{schema_version, log_count, counts_by_evidence_source, totals,
    rows}``. Observation only — NEVER affects matching / scoring / geometry /
    selection / STATE.
    """
    out: Dict[str, Any] = {
        "schema_version": PLACEMENT_PROOF_SCHEMA_VERSION,
        "log_count": 0,
        "counts_by_evidence_source": {s: 0 for s in _PLACEMENT_EVIDENCE_SOURCES},
        "totals": {"placed_logs": 0, "abstained_logs": 0, "station_pts": 0, "segs": 0},
        "rows": [],
    }
    if not isinstance(pipeline_diag, (list, tuple)):
        return out

    have_counts = isinstance(counts_by_source, Mapping)
    counts: Mapping[str, Mapping[str, Any]] = counts_by_source if have_counts else {}

    by_source: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    for entry in pipeline_diag:
        if not isinstance(entry, dict):
            continue
        rec = classify_placement(deepcopy(entry))
        sf = rec.get("source_file") or ""
        if sf not in by_source:
            by_source[sf] = rec
            order.append(sf)
            continue
        # Aggregate: keep the most-authoritative (lowest-rank) classification,
        # preserving any dist_ft the other group carried.
        cur = by_source[sf]
        if (_PLACEMENT_EVIDENCE_RANK.get(rec.get("evidence_source"), 9)
                < _PLACEMENT_EVIDENCE_RANK.get(cur.get("evidence_source"), 9)):
            if rec.get("dist_ft") is None and cur.get("dist_ft") is not None:
                rec["dist_ft"] = cur.get("dist_ft")
            by_source[sf] = rec

    rows: List[Dict[str, Any]] = []
    for sf in order:
        rec = dict(by_source[sf])
        if have_counts:
            c = counts.get(sf) if isinstance(counts.get(sf), Mapping) else {}
            rec["station_pts"] = int(c.get("station_pts") or 0)
            rec["segs"] = int(c.get("segs") or 0)
        else:
            rec["station_pts"] = None
            rec["segs"] = None
        # Target #12: read-only terminus LANE (additive; only when the caller passes
        # the lane map, i.e. TRUELINE_TERMINUS_TYPE_SHADOW ON). Key absent otherwise.
        if terminus_lane_by_source is not None:
            _tl = _terminus_lane_record(terminus_lane_by_source.get(sf))
            if _tl is not None:
                rec["terminus_lane"] = _tl
        rows.append(rec)

    rows.sort(key=lambda r: _safe_str(r.get("source_file")))

    for r in rows:
        es = r.get("evidence_source")
        if es in out["counts_by_evidence_source"]:
            out["counts_by_evidence_source"][es] += 1
        if es == "abstained":
            out["totals"]["abstained_logs"] += 1
        else:
            out["totals"]["placed_logs"] += 1
        if isinstance(r.get("station_pts"), int):
            out["totals"]["station_pts"] += r["station_pts"]
        if isinstance(r.get("segs"), int):
            out["totals"]["segs"] += r["segs"]

    out["log_count"] = len(rows)
    out["rows"] = rows

    # Target #12: top-level terminus-aware LANE re-grade summary (additive; only when
    # the caller passes the lane map). Buckets the classified logs by lane so flower-pot
    # DROPS are never treated as backbone-promotion-ready. Read-only; no placement.
    if terminus_lane_by_source is not None:
        lanes: Dict[str, List[str]] = {}
        for r in rows:
            tl = r.get("terminus_lane")
            if isinstance(tl, dict):
                lanes.setdefault(_safe_str(tl.get("lane")), []).append(_safe_str(r.get("source_file")))
        lanes = {k: sorted(v) for k, v in sorted(lanes.items())}
        blocked = sorted(s for lane_k, sfs in lanes.items() if lane_k != "BACKBONE_AP" for s in sfs)
        out["terminus_regrade"] = {
            "schema": "terminus-regrade-1",
            "source": _TERMINUS_REGRADE_SOURCE,
            "lanes": lanes,
            "counts": {k: len(v) for k, v in lanes.items()},
            "backbone_ap_candidates": sorted(lanes.get("BACKBONE_AP", [])),
            "blocked_from_backbone": blocked,
            "note": ("read-only terminus-aware re-grade; no placement; "
                     "flower_pot_drop never backbone-safe"),
        }
    return out
