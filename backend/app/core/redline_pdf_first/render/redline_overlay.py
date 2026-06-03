"""PDF redline overlay for DROP_TERMINAL_CANDIDATE segments (log51 class).

Builds a PDF-SPACE overlay spec from the existing ``drop_terminal`` metadata and
renders a de-rotated highlighted PNG (review-grade, dashed/amber). Authored
page-space ONLY — NO lon/lat, NO KMZ, NO route_id, NO snapping/scaling, NO
AP/SPLICE promotion (AP/SPLICE ride as context_identities). Imports the ``pdf``
subpackage (not ``fitz`` directly), preserving the import boundary.

Connector order is HUB -> intermediate(s, by station) -> DROP. Excluded flower
pots (outside the bore span) are listed but NEVER connected.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from ..contracts import (RenderArtifact, GEOMETRY_STATUS_FRAME_WITH_DROP_TERMINAL_CANDIDATE,
                         GEOMETRY_STATUS_AP_ANCHORED,
                         PDF_PATH_TRACE_READY, PDF_PATH_TRACE_REVIEW,
                         PDF_PATH_TRACE_READY_DASH_CHAINED, PDF_PATH_TRACE_REVIEW_DASH_CHAINED,
                         PDF_PATH_TRACE_DRAWING_STATUSES)
from ..geometry import path_tracer
from ..parsing import anchor_labels
from ..pdf import crop, text_extract
from . import evidence_card

DEFAULT_CARD_DIR = os.path.join("_analysis", "day3_cards")


def _safe(name: str) -> str:
    return name.replace("+", "p").replace(" ", "_").replace("/", "-")


def _centroid(b: List[float]) -> List[float]:
    return [(float(b[0]) + float(b[2])) / 2.0, (float(b[1]) + float(b[3])) / 2.0]


def _fmt_sta(ft) -> Optional[str]:
    if ft is None:
        return None
    ft = int(round(float(ft)))
    return f"{ft // 100}+{ft % 100:02d}"


def _ctx_str(ctx: List[Dict[str, Any]]) -> str:
    parts = []
    for c in ctx:
        if c.get("kind") == "AP":
            parts.append("AP-" + str(c.get("id")))
        elif c.get("kind") == "SPLICE_LOC":
            parts.append("SPLICE " + str(c.get("id")))
    return " / ".join(parts)


def build_pdf_redline_spec(seg) -> Optional[Dict[str, Any]]:
    """Pure: derive the PDF-space overlay spec from a candidate segment's
    ``drop_terminal`` metadata. Returns None unless the segment is a
    FRAME_WITH_DROP_TERMINAL_CANDIDATE with a drop endpoint. No fitz, no I/O."""
    p = getattr(seg, "placement", None)
    if p is None or p.geometry_status != GEOMETRY_STATUS_FRAME_WITH_DROP_TERMINAL_CANDIDATE:
        return None
    dt = p.drop_terminal
    if not dt:
        return None

    eps = dt.get("endpoints", {}) or {}
    drop = eps.get("drop") or {}
    hub = eps.get("hub") or {}
    drop_bbox = drop.get("page_bbox_display")
    inter = [r for r in (dt.get("intermediate_drops") or []) if r.get("page_bbox_display")]
    inter = sorted(inter, key=lambda r: r.get("sta_ft", 0.0))
    # hub marker = the authored terminal cluster whose AP EXACTLY matches a context
    # identity (matches_context_ap). NOT proximity — an exact AP-string join.
    hub_cluster = next((c for c in (dt.get("sheet_terminal_clusters") or [])
                        if c.get("matches_context_ap")), None)
    hub_bbox = hub_cluster.get("page_bbox_display") if hub_cluster else None
    callout_bbox = seg.callouts[0].bbox_display if (seg.callouts and seg.callouts[0].bbox_display) else None
    if not drop_bbox:
        return None  # nothing to anchor the drop end -> draw nothing

    elements: List[Dict[str, Any]] = []
    if callout_bbox:
        elements.append({"role": "callout", "bbox_display": list(callout_bbox),
                         "label": (seg.callouts[0].text or "")[:80]})
    if hub_bbox:
        elements.append({"role": "endpoint_hub", "authored_sta": hub.get("authored_sta"),
                         "kind": "DROP_TERMINAL_CLUSTER", "bbox_display": list(hub_bbox),
                         "context_ap": hub_cluster.get("ap_id"),
                         "basis": "exact_context_ap_cluster"})
    for r in inter:
        elements.append({"role": "intermediate", "authored_sta": r.get("authored_sta"),
                         "kind": "FLOWER_POT", "bbox_display": list(r["page_bbox_display"])})
    elements.append({"role": "endpoint_drop", "authored_sta": drop.get("authored_sta"),
                     "kind": "FLOWER_POT", "bbox_display": list(drop_bbox)})

    # connector: HUB -> intermediates -> DROP (excluded pots never included)
    order: List[str] = []
    points: List[List[float]] = []
    if hub_bbox:
        order.append(hub.get("authored_sta") or "0+00")
        points.append(_centroid(hub_bbox))
    for r in inter:
        order.append(r.get("authored_sta"))
        points.append(_centroid(r["page_bbox_display"]))
    order.append(drop.get("authored_sta") or "2+99")
    points.append(_centroid(drop_bbox))

    excluded = [{"role": "context_excluded", "authored_sta": r.get("authored_sta"),
                 "reason": r.get("reason")} for r in (dt.get("excluded_flower_pots") or [])]
    ctx = dt.get("context_identities") or []
    ctx_str = _ctx_str(ctx)

    return {
        "render_target": "evidence_card",
        "source_geometry": "authored_labels",
        "status_style": {"geometry_status": p.geometry_status,
                         "confidence": dt.get("confidence", "REVIEW"),
                         "color": "amber", "line": "dashed"},
        "sheet": (seg.sheets[0] if seg.sheets else None),
        "page": (seg.callouts[0].page if seg.callouts else None),
        "elements": elements,
        "excluded": excluded,
        "connector": {"kind": "approximate_label_path", "order": order,
                      "points_display": points, "style": {"dashed": True, "color": "amber"},
                      "caveat": "straight label-to-label approximation; not the surveyed bore alignment"},
        "context_identities": ctx,
        "caveats": ["REVIEW — DROP TERMINAL CANDIDATE",
                    (f"{ctx_str} are context only, not promoted" if ctx_str
                     else "terminal-area AP/SPLICE are context only, not promoted"),
                    "FLOWER_POT_UNLABELED_IN_KMZ"],
        "artifact_refs": [],
    }


def build_ap_anchored_spec(seg, lookup: Dict, render_sheet: int,
                           multi_sheet: bool = False, other_sheets=None) -> Optional[Dict[str, Any]]:
    """Pure: build the AP_ANCHORED overlay spec from EXACT-captured label bboxes.
    UNIQUE label -> marker + connector point; AMBIGUOUS (>1 hit) -> recorded note,
    NO marker (no proximity disambiguation); ABSENT -> unresolved. Connector forms
    only with >=2 unique anchors (else markers only — no fake line)."""
    p = getattr(seg, "placement", None)
    if p is None:
        return None
    callout = next((c for c in (seg.callouts or [])
                    if c.sheet == render_sheet and c.bbox_display), None)
    elements: List[Dict[str, Any]] = []
    if callout:
        elements.append({"role": "callout", "bbox_display": list(callout.bbox_display),
                         "label": (callout.text or "")[:80]})

    conn_pool: List[tuple] = []   # (sta_ft, centroid, sta_str)
    ambiguous: List[Dict[str, Any]] = []
    unresolved: List[Dict[str, Any]] = []
    for a in (p.geo_anchors or []):
        if a.sheet != render_sheet:
            unresolved.append({"kind": a.kind, "id": a.id, "sheet": a.sheet,
                               "reason": "anchor_on_other_sheet"})
            continue
        rec = lookup.get((a.kind, a.id)) or {"count": 0, "hits": [], "query": None}
        sta_str = _fmt_sta(a.sta)
        if rec["count"] == 1 and rec["hits"] and rec["hits"][0].get("bbox_display"):
            bb = rec["hits"][0]["bbox_display"]
            elements.append({"role": ("endpoint_ap" if a.kind == "AP" else "endpoint_splice"),
                             "kind": a.kind, "id": a.id, "authored_sta": sta_str,
                             "bbox_display": list(bb), "label_query": rec["query"]})
            conn_pool.append((a.sta if a.sta is not None else 0.0, _centroid(bb), sta_str))
        elif rec["count"] > 1:
            ambiguous.append({"kind": a.kind, "id": a.id, "query": rec["query"],
                              "hit_count": rec["count"],
                              "note": "label drawn at multiple authored positions; "
                                      "not disambiguated (no proximity)"})
        else:
            unresolved.append({"kind": a.kind, "id": a.id, "query": rec.get("query"),
                               "reason": "label_not_found_on_sheet"})

    if not elements:
        return None  # nothing authored to draw

    conn_pool.sort(key=lambda t: t[0])
    order = [t[2] for t in conn_pool]
    points = [t[1] for t in conn_pool]
    caveats = ["AP_ANCHORED — AP/SPLICE exact identity",
               "approximate label-to-label evidence path; not the surveyed bore alignment"]
    if multi_sheet:
        sheets = sorted(set([render_sheet] + list(other_sheets or [])))
        caveats.append(f"MATCHLINE_FRAME — span crosses sheets {sheets}; "
                       f"drawn on sheet {render_sheet} only (no cross-sheet line)")
    connector = None
    if len(points) >= 2:
        connector = {"kind": "approximate_label_path", "order": order,
                     "points_display": points, "style": {"dashed": False, "color": "green"},
                     "caveat": "approximate label-to-label evidence path; not the surveyed bore alignment"}
    return {
        "render_target": "evidence_card",
        "source_geometry": "authored_labels",
        "status_style": {"geometry_status": p.geometry_status, "confidence": "ANCHORED",
                         "color": "green", "line": "solid"},
        "sheet": render_sheet,
        "page": (callout.page if callout else None),
        "elements": elements,
        "connector": connector,
        "ambiguous_labels": ambiguous,
        "unresolved_labels": unresolved,
        "multi_sheet": bool(multi_sheet),
        "caveats": caveats,
        "artifact_refs": [],
    }


def ap_anchored_spec(seg, doc, sheet_offset: int = 13) -> Optional[Dict[str, Any]]:
    """Capture AP/SPLICE label bboxes on the bore's render sheet (exact text) and
    build the AP_ANCHORED spec. Needs an open ``doc`` for the page. Never raises."""
    try:
        p = getattr(seg, "placement", None)
        if p is None or p.geometry_status != GEOMETRY_STATUS_AP_ANCHORED:
            return None
        render_sheet = (seg.callouts[0].sheet if seg.callouts else
                        (seg.sheets[0] if seg.sheets else None))
        if render_sheet is None:
            return None
        page = doc[int(render_sheet) + sheet_offset - 1]
        tokens = [(a.kind, a.id) for a in (p.geo_anchors or []) if a.sheet == render_sheet]
        lookup = anchor_labels.capture(page, tokens)
        multi = bool(p.frame and getattr(p.frame, "multi_sheet", False))
        return build_ap_anchored_spec(seg, lookup, render_sheet, multi_sheet=multi,
                                      other_sheets=list(seg.sheets or []))
    except Exception:
        return None


def render_and_attach_redline(result, pdf_path: str, out_dir: str = DEFAULT_CARD_DIR,
                              sheet_offset: int = 13):
    """Render a de-rotated PDF redline overlay PNG for each placed segment with
    drawable authored geometry:
      * FRAME_WITH_DROP_TERMINAL_CANDIDATE -> amber/dashed (review) from drop_terminal
      * AP_ANCHORED -> green/solid from EXACT-captured AP/SPLICE label bboxes
    Sets ``placement.pdf_redline`` + ``artifact_refs`` + a ``pdf_redline_overlay``
    RenderArtifact. Page-space only; never raises into the caller."""
    if result.render_artifacts is None:
        evidence_card.attach_render_artifacts(result)
    segs = [s for s in list(result.selected_segments) + list(result.review_items)
            if getattr(s, "placement", None) is not None
            and s.placement.geometry_status in (GEOMETRY_STATUS_FRAME_WITH_DROP_TERMINAL_CANDIDATE,
                                                GEOMETRY_STATUS_AP_ANCHORED)]
    if not segs:
        return result
    doc = text_extract.open_document(pdf_path)
    try:
        for seg in segs:
            gs = seg.placement.geometry_status
            if gs == GEOMETRY_STATUS_FRAME_WITH_DROP_TERMINAL_CANDIDATE:
                spec, accent, dashed, tag = build_pdf_redline_spec(seg), (220, 25, 25), True, "REVIEW DROP_TERMINAL_CANDIDATE"
            else:  # AP_ANCHORED
                spec, accent, dashed, tag = ap_anchored_spec(seg, doc, sheet_offset), (40, 150, 40), False, "AP_ANCHORED"
            if not spec:
                continue
            seg.placement.pdf_redline = spec
            sheet = spec.get("sheet")
            if sheet is None:
                continue
            page = doc[int(sheet) + sheet_offset - 1]
            conn = (spec.get("connector") or {}).get("points_display") or []
            order = (spec.get("connector") or {}).get("order") or []
            fn = _safe(f"{seg.segment_id}_redline_s{sheet}.png")
            cap = f"{seg.segment_id} {tag} " + ("->".join(order) if order else "(markers only)")
            outp = crop.render_redline_overlay(page, spec["elements"], conn,
                                               os.path.join(out_dir, fn),
                                               accent=accent, dashed=dashed, caption=cap)
            if outp:
                ref = os.path.abspath(outp)
                spec["artifact_refs"] = [ref]
                result.render_artifacts.append(RenderArtifact(
                    artifact_id=f"redline-{seg.segment_id}", segment_id=seg.segment_id,
                    render_target="evidence_card", kind="pdf_redline_overlay",
                    ref=ref, payload={"pdf_redline_ref": [ref]}))
    finally:
        doc.close()
    return result


def render_and_attach_path_trace(result, pdf_path: str, out_dir: str = DEFAULT_CARD_DIR,
                                 sheet_offset: int = 13, dash_chain: bool = False):
    """Attach ``placement.pdf_path_trace`` (the authored drawn-run trace) for each
    placed segment and, when the trace is a DRAWING status (READY / READY_DASH_CHAINED
    / REVIEW_DASH_CHAINED), render a de-rotated PNG of the traced page-space run as
    the PRIMARY redline. ``dash_chain`` enables bounded dash-chain reconstruction as
    the fallback when the base trace is BLOCKED. The existing label connector
    (``pdf_redline``) is left intact as fallback/secondary evidence. A BLOCKED trace
    sets metadata only (no PNG; existing overlays untouched). Page-space only; never
    raises into the caller."""
    if result.render_artifacts is None:
        evidence_card.attach_render_artifacts(result)
    segs = [s for s in list(result.selected_segments) + list(result.review_items)
            if getattr(s, "placement", None) is not None
            and s.placement.geometry_status in (GEOMETRY_STATUS_FRAME_WITH_DROP_TERMINAL_CANDIDATE,
                                                GEOMETRY_STATUS_AP_ANCHORED)]
    if not segs:
        return result
    doc = text_extract.open_document(pdf_path)
    try:
        for seg in segs:
            spec = path_tracer.attach_path_trace(seg, doc, sheet_offset, dash_chain=dash_chain)
            if not spec:
                continue
            status = spec.get("trace_status")
            pts = spec.get("path_points_display") or []
            # Only DRAWING statuses render a line; BLOCKED -> metadata only (no guess).
            if status not in PDF_PATH_TRACE_DRAWING_STATUSES or len(pts) < 2:
                continue
            sheet = spec.get("sheet")
            if sheet is None:
                continue
            page = doc[int(sheet) + sheet_offset - 1]
            # context: highlight the authored callout box (needed for the crop clip)
            callout = next((c for c in (seg.callouts or [])
                            if c.sheet == sheet and c.bbox_display), None)
            elements = ([{"role": "callout", "bbox_display": list(callout.bbox_display)}]
                        if callout and callout.bbox_display else [])
            reconstructed = status in (PDF_PATH_TRACE_READY_DASH_CHAINED,
                                       PDF_PATH_TRACE_REVIEW_DASH_CHAINED)
            ready = status in (PDF_PATH_TRACE_READY, PDF_PATH_TRACE_READY_DASH_CHAINED)
            accent = (40, 150, 40) if ready else (220, 25, 25)   # green READY / RED review (TrueLine redline)
            fn = _safe(f"{seg.segment_id}_pathtrace_s{sheet}.png")
            mark = "DASH-RECONSTRUCTED" if reconstructed else "authored run trace"
            cap = f"{seg.segment_id} {status} ({mark})"
            outp = crop.render_redline_overlay(page, elements, pts,
                                               os.path.join(out_dir, fn),
                                               accent=accent, dashed=reconstructed, caption=cap)
            if outp:
                ref = os.path.abspath(outp)
                spec["artifact_refs"] = [ref]
                result.render_artifacts.append(RenderArtifact(
                    artifact_id=f"pathtrace-{seg.segment_id}", segment_id=seg.segment_id,
                    render_target="evidence_card", kind="pdf_path_trace_overlay",
                    ref=ref, payload={"pdf_path_trace_ref": [ref]}))
    finally:
        doc.close()
    return result
