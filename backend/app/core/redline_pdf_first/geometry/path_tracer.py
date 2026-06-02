"""Authored bore-path tracer — page-space, IDENTITY-BOUND, no proximity guessing.

Goal: highlight the ACTUAL authored drawn run for a bore, not the approximate
label-to-label connector. A vector ``run`` (a continuous authored polyline from
``pdf.vector_extract.extract_paths``) is ELIGIBLE for a bore ONLY when an AUTHORED
identity box the selector already bound for THIS bore — the DIR. BORE callout box,
or a UNIQUE endpoint AP/SPLICE label — coincides with a vertex of that polyline
within a tiny connectivity tolerance ``eps`` (a joint-rounding tolerance, NOT a
search radius). The decision:

  * exactly ONE eligible run            -> PDF_PATH_TRACE_READY  (draw it)
  * >= 2 eligible runs, no discriminator -> PDF_PATH_TRACE_REVIEW (list, draw none)
  * 0 eligible (run exists but unbound, or no continuous run) -> PDF_PATH_TRACE_BLOCKED

Run candidacy is GEOMETRY-ONLY (elongated continuous polyline); colour is NEVER a
selector. Forbidden by construction: closest-line, nearest visual feature,
colour-only selection, snapping / dash gap-bridging, route scoring, station
scaling, KMZ/world coords. Page-space verbatim vertices only.

The pure functions (``runlike_paths`` / ``eligible_runs`` / ``trace``) take plain
data and are unit-testable without ``fitz``. ``attach_path_trace`` is the thin
page-glue (it reaches the vector layer through ``pdf.vector_extract`` and the
label layer through ``parsing.anchor_labels`` — never ``fitz`` directly).
"""
from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional

from ..contracts import (
    GEOMETRY_STATUS_AP_ANCHORED,
    GEOMETRY_STATUS_FRAME_WITH_DROP_TERMINAL_CANDIDATE,
    PDF_PATH_TRACE_BLOCKED,
    PDF_PATH_TRACE_READY,
    PDF_PATH_TRACE_READY_DASH_CHAINED,
    PDF_PATH_TRACE_RENDER_TARGET,
    PDF_PATH_TRACE_REVIEW,
    PDF_PATH_TRACE_REVIEW_DASH_CHAINED,
)

# Authored CAD layer that marks the bored conduit (vs existing utilities GAS/CATV/
# STM-SWR/NEXTLINK/...). Layer is AUTHORED IDENTITY, not colour/proximity.
BORE_LAYER_RX = re.compile(r"\bBORE\b", re.I)
_BORE_LAYER_PREF = ("PATH", "PORT", "LATERAL")   # deterministic authored preference
DEFAULT_TICK_PERP = 18.0     # station label sits within this band of the run it annotates
DEFAULT_TICK_PAD_X = 20.0

# Geometry-only run-candidate gates (display units). NO colour in the predicate.
DEFAULT_MIN_EXTENT = 150.0     # longest bbox dimension of a real run
DEFAULT_MAX_THICKNESS = 60.0   # shortest bbox dimension (a line, not a blob)
DEFAULT_MIN_LENGTH = 150.0     # summed polyline length
DEFAULT_ELONGATION = 3.0       # long_dim >= ELONGATION * short_dim
DEFAULT_EPS = 2.0              # vertex<->identity-box connectivity tolerance


def runlike_paths(paths: List[Dict[str, Any]], *,
                  min_extent: float = DEFAULT_MIN_EXTENT,
                  max_thickness: float = DEFAULT_MAX_THICKNESS,
                  min_length: float = DEFAULT_MIN_LENGTH,
                  elongation: float = DEFAULT_ELONGATION) -> List[Dict[str, Any]]:
    """Geometry-only candidate runs: continuous, elongated authored polylines.
    Colour is intentionally ignored (no colour-only selection)."""
    out: List[Dict[str, Any]] = []
    for p in paths:
        bb = p.get("bbox_display")
        if not bb or int(p.get("n_items", 0)) < 2:
            continue
        w = float(bb[2]) - float(bb[0])
        h = float(bb[3]) - float(bb[1])
        long_dim = max(w, h)
        short_dim = min(w, h)
        if long_dim < min_extent:
            continue
        if short_dim > max_thickness:
            continue
        if float(p.get("length", 0.0)) < min_length:
            continue
        if long_dim < elongation * max(short_dim, 1.0):
            continue
        out.append(p)
    return out


def _box_touches_path(box: List[float], path: Dict[str, Any], eps: float) -> bool:
    """True iff a VERTEX of ``path`` falls within ``eps`` of ``box`` — i.e. the
    authored linework actually meets the authored label. ``eps`` is a small
    joint-rounding tolerance, never a 'nearest within N' search radius."""
    x0, y0, x1, y1 = box
    for pt in path.get("points_display", []):
        if (x0 - eps) <= pt[0] <= (x1 + eps) and (y0 - eps) <= pt[1] <= (y1 + eps):
            return True
    return False


def eligible_runs(paths: List[Dict[str, Any]], identity_boxes: List[Dict[str, Any]], *,
                  eps: float = DEFAULT_EPS, **runlike_kw) -> Dict[str, Any]:
    """Run candidates (geometry) + those bound to an authored identity box."""
    cands = runlike_paths(paths, **runlike_kw)
    elig: List[Dict[str, Any]] = []
    for p in cands:
        binders = [b for b in identity_boxes
                   if b.get("bbox_display") and _box_touches_path(b["bbox_display"], p, eps)]
        if binders:
            elig.append({"path": p, "binders": binders})
    return {"candidates": cands, "eligible": elig}


def trace(sheet: Optional[int], page_no: Optional[int],
          paths: List[Dict[str, Any]], identity_boxes: List[Dict[str, Any]], *,
          eps: float = DEFAULT_EPS, conduit_signature: Optional[str] = None,
          runlike_kw: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Pure decision -> a ``pdf_path_trace`` dict (page-space only; no map keys)."""
    res = eligible_runs(paths, identity_boxes, eps=eps, **(runlike_kw or {}))
    cands, elig = res["candidates"], res["eligible"]
    spec: Dict[str, Any] = {
        "trace_status": PDF_PATH_TRACE_BLOCKED,
        "sheet": sheet,
        "page": page_no,
        "path_basis": None,
        "path_points_display": [],
        "source_vector_refs": [],
        "endpoint_evidence": [],
        "binding_evidence": {
            "runlike_candidates": len(cands),
            "eligible_runs": len(elig),
            "identity_boxes": [b.get("role") for b in identity_boxes],
            "eps_display_pt": eps,
            "conduit_signature": conduit_signature,
        },
        "caveats": [],
        "render_target": PDF_PATH_TRACE_RENDER_TARGET,
        "rules": ("authored-identity vertex binding only; no nearest/colour-only/"
                  "snapping/gap-bridging/scoring/scaling; page-space verbatim vertices; "
                  "no KMZ/world coords"),
    }
    if len(elig) == 1:
        p = elig[0]["path"]
        binders = elig[0]["binders"]
        spec.update({
            "trace_status": PDF_PATH_TRACE_READY,
            "path_basis": "authored_identity_bound_polyline",
            "path_points_display": [[float(pt[0]), float(pt[1])] for pt in p["points_display"]],
            "source_vector_refs": [p["source_ref"]],
            "endpoint_evidence": [{
                "role": b.get("role"), "id": b.get("id"),
                "bbox_display": [float(v) for v in b["bbox_display"]],
                "binds": "vertex_within_eps",
            } for b in binders],
            "caveats": ["READY: single authored-identity-bound run; "
                        "traced from page-space vector vertices (not the label connector)"],
        })
    elif len(elig) >= 2:
        spec.update({
            "trace_status": PDF_PATH_TRACE_REVIEW,
            "path_basis": "multiple_identity_bound_runs_no_discriminator",
            "source_vector_refs": [e["path"]["source_ref"] for e in elig],
            "caveats": ["REVIEW: >=2 identity-bound runs and no authored discriminator; "
                        "candidates listed, NONE auto-traced (no proximity guess)"],
        })
    else:
        reason = "no_continuous_authored_run" if not cands else "no_authored_identity_binding"
        spec.update({
            "trace_status": PDF_PATH_TRACE_BLOCKED,
            "path_basis": reason,
            "caveats": [f"BLOCKED: {reason}; abstaining — no nearest/colour/snap guess"],
        })
    return spec


# ─────────────────────────────────────────────────────────────────────────────
# Dash-chain decision (PURE): bind a reconstructed chain to the bore by AUTHORED
# LAYER (BORE-family) + callout corridor + station-tick corroboration. No nearest,
# no colour-only (layer is authored identity), no scoring of the bore vs utilities.
# ─────────────────────────────────────────────────────────────────────────────
def _bore_pref(layer: Optional[str]) -> int:
    up = (layer or "").upper()
    for i, p in enumerate(_BORE_LAYER_PREF):
        if p in up:
            return i
    return len(_BORE_LAYER_PREF)


def dash_chain_decide(sheet: Optional[int], page_no: Optional[int],
                      chains: List[Dict[str, Any]], station_labels: List[Dict[str, Any]],
                      identity_boxes: List[Dict[str, Any]], bore_range, *,
                      conduit_signature: Optional[str] = None,
                      bore_layer_rx=BORE_LAYER_RX, tick_perp: float = DEFAULT_TICK_PERP,
                      tick_pad_x: float = DEFAULT_TICK_PAD_X,
                      rejected_seed: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Bind reconstructed dash chains to the bore. Returns a pdf_path_trace dict
    (page-space only). READY_DASH_CHAINED only for a UNIQUE eligible chain that
    BRACKETS the full bore range; otherwise REVIEW_DASH_CHAINED (the bar) or BLOCKED."""
    lo, hi = (min(bore_range), max(bore_range)) if bore_range else (None, None)
    callout = next((b["bbox_display"] for b in identity_boxes if b.get("role") == "callout"), None)
    rejected: List[Dict[str, Any]] = list(rejected_seed or [])

    bore_chains, eligible = [], []
    for c in chains:
        if c.get("layer") and bore_layer_rx.search(c["layer"]):
            bore_chains.append(c)
        else:
            rejected.append({"layer": c.get("layer"), "span": c.get("span"),
                             "reason": "non_bore_layer"})
    for c in bore_chains:
        bb = c["bbox_display"]
        if callout and not (callout[0] <= bb[2] and callout[2] >= bb[0]):
            rejected.append({"layer": c["layer"], "reason": "outside_callout_corridor"})
            continue
        ymid = (bb[1] + bb[3]) / 2.0
        ticks = sorted({s["value_ft"] for s in station_labels
                        if (bb[0] - tick_pad_x) <= s["center"][0] <= (bb[2] + tick_pad_x)
                        and abs(s["center"][1] - ymid) <= tick_perp
                        and (lo is None or (lo - 30) <= s["value_ft"] <= (hi + 30))})
        if len(ticks) < 2:
            rejected.append({"layer": c["layer"], "reason": "insufficient_station_ticks",
                             "ticks": ticks})
            continue
        ec = dict(c)
        ec["station_ticks"] = ticks
        eligible.append(ec)

    spec: Dict[str, Any] = {
        "trace_status": PDF_PATH_TRACE_BLOCKED, "sheet": sheet, "page": page_no,
        "path_basis": None, "path_points_display": [], "source_vector_refs": [],
        "endpoint_evidence": [], "dash_chain_evidence": None,
        "binding_evidence": {"bore_layer_chains": len(bore_chains),
                             "eligible_chains": len(eligible),
                             "identity_boxes": [b.get("role") for b in identity_boxes],
                             "conduit_signature": conduit_signature},
        "rejected_candidates": rejected, "caveats": [],
        "render_target": PDF_PATH_TRACE_RENDER_TARGET,
        "rules": ("dash-chain reconstruction bound by authored LAYER (BORE-family) + "
                  "callout corridor + station-tick corroboration; no nearest/colour-only/"
                  "scoring/scaling; intrinsic gap bound; page-space verbatim vertices; no KMZ"),
    }
    if not eligible:
        spec["path_basis"] = "no_bore_layer_dash_chain" if not bore_chains else "no_corroborated_bore_chain"
        spec["caveats"] = [f"BLOCKED: {spec['path_basis']}; abstaining (no nearest/colour guess)"]
        return spec

    eligible.sort(key=lambda c: (_bore_pref(c["layer"]), -len(c["station_ticks"]), -c["span"]))
    primary, others = eligible[0], eligible[1:]
    full_bracket = bool(lo is not None and primary["station_ticks"]
                        and min(primary["station_ticks"]) <= lo + 30
                        and max(primary["station_ticks"]) >= hi - 30)
    unique = len(eligible) == 1
    status = (PDF_PATH_TRACE_READY_DASH_CHAINED if (unique and full_bracket)
              else PDF_PATH_TRACE_REVIEW_DASH_CHAINED)
    sublayers = [{"layer": c["layer"], "span": c["span"], "station_ticks": c["station_ticks"]}
                 for c in others]
    caveats = ["reconstructed dashed run (not a single authored polyline)",
               f"bound by authored layer {primary['layer']!r} + station ticks "
               f"{primary['station_ticks']} + callout corridor"]
    if status == PDF_PATH_TRACE_REVIEW_DASH_CHAINED:
        if sublayers:
            caveats.append(f"REVIEW: {len(sublayers)} parallel bore sub-layer chain(s) present "
                           "(PORT/LATERAL/PATH); confirm exact conduit")
        if not full_bracket:
            caveats.append("REVIEW: station ticks do not bracket the full bore range")
    spec.update({
        "trace_status": status,
        "path_basis": "bounded_dash_chain+authored_layer+station_ticks+callout_corridor",
        "path_points_display": [[float(x), float(y)] for (x, y) in primary["points_display"]],
        "source_vector_refs": list(primary.get("source_vector_refs") or []),
        "endpoint_evidence": [{"role": "station_tick", "value_ft": v} for v in primary["station_ticks"]],
        "dash_chain_evidence": {
            "stroke_family": {"layer": primary["layer"], "color": primary.get("color"),
                              "width": primary.get("width")},
            "dash_count": primary.get("dash_count"), "median_dash_len": primary.get("median_dash_len"),
            "gap_bound": primary.get("gap_bound"), "span": primary.get("span"),
            "station_ticks": primary["station_ticks"], "full_bracket": full_bracket,
            "bore_sublayers": sublayers, "conduit_signature": conduit_signature, "reconstructed": True,
        },
        "caveats": caveats,
    })
    return spec


# ─────────────────────────────────────────────────────────────────────────────
# Page-glue (no fitz: reaches the vector layer via pdf.vector_extract, the label
# layer via parsing.anchor_labels). Builds THIS bore's authored identity boxes,
# extracts the page's authored paths, runs the pure tracer, sets pdf_path_trace.
# ─────────────────────────────────────────────────────────────────────────────
def _identity_boxes(seg, page, render_sheet, anchor_labels) -> List[Dict[str, Any]]:
    """Authored identity boxes for THIS bore on ``render_sheet``: the DIR. BORE
    callout box (always) + UNIQUE endpoint AP/SPLICE labels (count==1 only —
    ambiguous/multi-hit labels are NOT used, mirroring the connector discipline)."""
    boxes: List[Dict[str, Any]] = []
    co = next((c for c in (seg.callouts or [])
               if c.sheet == render_sheet and c.bbox_display), None)
    if co and co.bbox_display:
        boxes.append({"role": "callout", "id": None, "bbox_display": list(co.bbox_display)})
    p = getattr(seg, "placement", None)
    tokens = [(a.kind, a.id) for a in (getattr(p, "geo_anchors", None) or [])
              if a.sheet == render_sheet]
    if tokens:
        lookup = anchor_labels.capture(page, tokens)
        for (kind, ident), rec in lookup.items():
            if rec.get("count") == 1 and rec.get("hits") and rec["hits"][0].get("bbox_display"):
                boxes.append({
                    "role": ("endpoint_ap" if kind == "AP" else "endpoint_splice"),
                    "id": ident, "bbox_display": list(rec["hits"][0]["bbox_display"]),
                })
    return boxes


def attach_path_trace(seg, doc, sheet_offset: int = 13, eps: float = DEFAULT_EPS,
                      dash_chain: bool = False):
    """Set ``seg.placement.pdf_path_trace`` for an AP_ANCHORED / drop-terminal
    segment by tracing the authored run on its render sheet. When ``dash_chain`` is
    enabled and the base (single-polyline) trace is BLOCKED, fall back to bounded
    dash-chain reconstruction (layer + corridor + station-tick bound). Never raises."""
    try:
        from ..pdf import vector_extract                       # pdf/ (fitz confined there)
        from ..parsing import anchor_labels, station_labels    # parsing/ (text layer)
        from . import dash_chain as dc                         # geometry/ (pure)
        p = getattr(seg, "placement", None)
        if p is None or p.geometry_status not in (
                GEOMETRY_STATUS_AP_ANCHORED, GEOMETRY_STATUS_FRAME_WITH_DROP_TERMINAL_CANDIDATE):
            return None
        render_sheet = (seg.callouts[0].sheet if seg.callouts else
                        (seg.sheets[0] if seg.sheets else None))
        if render_sheet is None:
            return None
        page = doc[int(render_sheet) + sheet_offset - 1]
        paths = vector_extract.extract_paths(page)
        identity_boxes = _identity_boxes(seg, page, render_sheet, anchor_labels)
        page_no = (seg.callouts[0].page if seg.callouts else None)
        spec = trace(render_sheet, page_no, paths, identity_boxes, eps=eps,
                     conduit_signature=(seg.conduit or None))
        # Dash-chain fallback ONLY when the base trace abstained and it's enabled.
        if dash_chain and spec.get("trace_status") == PDF_PATH_TRACE_BLOCKED:
            segments = vector_extract.extract_segments(page)
            built = dc.build_chains(segments)
            labels = station_labels.extract_station_labels(page)
            bore_range = (float(p.station_span_ft.start), float(p.station_span_ft.end))
            spec = dash_chain_decide(render_sheet, page_no, built["chains"], labels,
                                     identity_boxes, bore_range,
                                     conduit_signature=(seg.conduit or None),
                                     rejected_seed=built["rejected_candidates"])
            # Multi-sheet (matchline) bore: a single-sheet chain is only a PORTION of
            # the run -> never READY, always REVIEW, with an explicit matchline caveat
            # (never a drawn cross-sheet line).
            if spec.get("trace_status") in (PDF_PATH_TRACE_READY_DASH_CHAINED,
                                            PDF_PATH_TRACE_REVIEW_DASH_CHAINED):
                multi = bool(getattr(p, "frame", None) and getattr(p.frame, "multi_sheet", False))
                if multi:
                    spec["trace_status"] = PDF_PATH_TRACE_REVIEW_DASH_CHAINED
                    spec.setdefault("caveats", []).append(
                        f"MATCHLINE: multi-sheet bore; trace is the sheet-{render_sheet} portion "
                        "only (no cross-sheet line)")
        p.pdf_path_trace = spec
        return spec
    except Exception:
        return None
