"""Default-OFF matchline / station-frame / correction / BOC consult — ENVELOPE-space port.

This is the LIVE row-fed sibling of the proven offline coverage consult (scratch
``_analysis/full_pdf_borelog_coverage/build_coverage.py``). It is consulted by the
TrueLine PDF-first adapter ONLY behind ``TRUELINE_MATCHLINE_FRAME_RESOLVER``; with the
flag unset nothing here is imported or called and the adapter envelope is byte-identical.

It carries NO new selection / scoring intelligence. It only:
  * applies OWNER-REVIEWED source-station OCR corrections to a COPY of ``committed_rows``
    BEFORE the engine runs (``apply_corrections``; the live STATE rows are never mutated,
    exactly as the file-fed lane never alters the original .xlsx);
  * after the engine runs, LIFTS a bore the engine left FRAME_ONLY / blocked / fail-safe —
    when it is in truth ONE owner-reviewed authored cross-sheet (or single-sheet host-
    anchored) run — into a matchline (group C) / station-frame (group B) REVIEW card, every
    authored fact VERIFIED against the live PDF before any overlay is emitted; OR
  * lets an owner-reviewed + BOC-corroborated resolver entry OVERRIDE a geometry-only A
    ``path_trace`` placement that fails the authored-endpoint/BOC proof on its own sheet
    (the NARROW false-A precedence rule — never a rerank).

Doctrine (unchanged from the scratch lane): per-bore resolutions / corrections / BOC are
OWNER-REVIEWED data (the vendored ``_redline_data`` ledgers), never guessed; EXACT authored-
text + exact-station matching only — no nearest snapping, no scoring, no span. Never raises
into the adapter (any failure leaves the envelope untouched).
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

# ── owner-reviewed ledger caches (keyed by data_dir; the ledgers are immutable) ─────────────
_RES_CACHE: Dict[str, Dict[str, Any]] = {}
_BOC_CACHE: Dict[str, Dict[str, Any]] = {}
_CORR_CACHE: Dict[str, Dict[str, Any]] = {}


def _resolutions(data_dir: str) -> Dict[str, Any]:
    # Pure JSON read (NOT via frame_resolver) so checking "is there a resolution for this log"
    # never imports fitz — only the actual PDF verification (_matchline_resolve) does.
    if data_dir not in _RES_CACHE:
        path = os.path.join(data_dir, "_matchline", "frame_resolutions.json")
        res: Dict[str, Any] = {}
        if os.path.isfile(path):
            try:
                res = {r["bore_id"]: r
                       for r in json.load(open(path, encoding="utf-8")).get("resolutions", [])}
            except Exception:
                res = {}
        _RES_CACHE[data_dir] = res
    return _RES_CACHE[data_dir]


def _corrections(data_dir: str) -> Dict[str, Any]:
    if data_dir not in _CORR_CACHE:
        from . import correction_lib
        _CORR_CACHE[data_dir] = correction_lib.load_corrections(
            os.path.join(data_dir, "_corrections", "corrections.json"))
    return _CORR_CACHE[data_dir]


def _boc_evidence(data_dir: str) -> Dict[str, Any]:
    if data_dir not in _BOC_CACHE:
        ev: Dict[str, Any] = {}
        p = os.path.join(data_dir, "_boc", "boc_evidence.json")
        if os.path.isfile(p):
            try:
                ev = {e["bore_id"]: e
                      for e in json.load(open(p, encoding="utf-8")).get("logs", [])}
            except Exception:
                ev = {}
        _BOC_CACHE[data_dir] = ev
    return _BOC_CACHE[data_dir]


def open_document(pdf_path: str) -> Any:
    """Open the plan PDF once for a session run (lazy fitz import via the engine's text
    primitive). The caller owns the handle and should close it after the per-log loop."""
    from redline_pdf_first.pdf import text_extract
    return text_extract.open_document(pdf_path)


# ── corrections (applied BEFORE the engine, row-fed) ────────────────────────────────────────
def apply_corrections(log_id: str, rows: Sequence[Mapping[str, Any]], data_dir: str
                      ) -> Tuple[Sequence[Mapping[str, Any]], List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """If an owner-reviewed correction exists for ``log_id``, return a CORRECTED COPY of
    ``rows`` + the change audit + a provenance record; else ``(rows, [], None)``. Never mutates
    the input. A stale correction (a station_map key / drop_station that no row matches) raises
    inside ``correction_lib`` (strict) — caught here and recorded as ``correction_error`` with a
    fall-back to the RAW rows, so a half-fix is never applied silently."""
    corr = _corrections(data_dir).get(log_id)
    if not corr:
        return rows, [], None
    from . import correction_lib
    try:
        new_rows, changes = correction_lib.corrected_rows(
            rows, corr.get("station_map", {}),
            drop_stations=[e["station"] for e in corr.get("row_exclusions", [])])
        return new_rows, changes, {
            "category": corr.get("reason"), "approved_by": corr.get("approved_by"),
            "reviewed_at": corr.get("reviewed_at"), "source_date": corr.get("source_date"),
            "cells_changed": len(changes), "changes": changes,
            "rows_excluded": corr.get("row_exclusions", []),
        }
    except Exception as exc:
        return rows, [], {"category": corr.get("reason"),
                          "correction_error": f"{type(exc).__name__}: {exc}"}


# ── classify (verbatim port of the proven coverage status detection) ─────────────────────────
def _first(seq):
    return seq[0] if seq else None


def classify(env: Mapping[str, Any]) -> Dict[str, Any]:
    """Per-log record from ONE adapter envelope. Status is derived ONLY from the engine's own
    result fields (never invented). Verbatim port of build_coverage.classify — the consult keys
    on the SAME fields the proven offline harness used, so detection cannot drift."""
    status = env.get("status")
    placements = env.get("placements") or []
    reviews = env.get("review_items") or []
    fail_safe = env.get("fail_safe") or []
    warnings = env.get("warnings") or []
    cards = placements + reviews

    rec: Dict[str, Any] = {
        "station_range": None, "footage": None, "print": None, "sheets": None,
        "page": None, "geometry_status": None, "trace_status": None,
        "artifact_name": None, "has_overlay_image": False,
        "caveats": [], "block_reason": None, "surface": None,
    }

    if status == "ERROR":
        rec["block_reason"] = "; ".join(warnings) or "engine returned ERROR"
        rec["status"] = "blocked"
        return rec

    if not cards and fail_safe:
        fs = fail_safe[0]
        rec["surface"] = "fail_safe"
        rec["block_reason"] = (fs.get("reason")
                               or (fs.get("caveat") or {}).get("text")
                               or "two or more equally-supported candidates; nothing placed")
        rec["status"] = "fail_safe"
        return rec

    if not cards:
        rec["block_reason"] = ("; ".join(warnings)
                               or "engine produced no placement, review item, or fail-safe candidate")
        rec["status"] = "blocked"
        return rec

    card = _first(cards)
    geo = card.get("geo") or {}
    frame = geo.get("frame") or {}
    pt = geo.get("pdf_path_trace") or {}
    rec["surface"] = card.get("surface")
    rec["station_range"] = card.get("station_range")
    rec["footage"] = card.get("footage")
    rec["print"] = card.get("print")
    rec["sheets"] = card.get("sheets")
    rec["page"] = frame.get("page") or pt.get("page")
    rec["geometry_status"] = geo.get("geometry_status")
    rec["trace_status"] = pt.get("trace_status")
    multi_sheet = bool(frame.get("multi_sheet"))

    gs = rec["geometry_status"]
    if gs == "FRAME_WITH_DROP_TERMINAL_CANDIDATE":
        rec["status"] = "fiber_drop"
    elif pt.get("artifact_name"):
        rec["status"] = "matchline" if multi_sheet else "path_trace_drawn"
    elif (geo.get("pdf_redline") or {}).get("artifact_name"):
        rec["status"] = "evidence_overlay"
    else:
        rec["block_reason"] = ("placement frame anchored; PDF path-trace not attempted for this "
                               "geometry class (FRAME_ONLY is excluded from the trace gate)")
        rec["status"] = "blocked"
    return rec


# ── resolver consult (run AFTER the engine, verified against the live PDF) ───────────────────
def _matchline_resolve(log_id: str, doc: Any, sheet_offset: int, out_dir: str, data_dir: str
                       ) -> Optional[Dict[str, Any]]:
    try:
        res = _resolutions(data_dir).get(log_id)
        if not res:
            return None
        from . import frame_resolver as fr
        return fr.verify_and_resolve(doc, res, sheet_offset, out_dir)
    except Exception as exc:
        return {"resolved": False, "reason": f"{type(exc).__name__}: {exc}"}


def _resolver_overrides_false_A(log_id: str, rec: Mapping[str, Any], doc: Any,
                                sheet_offset: int, out_dir: str, data_dir: str
                                ) -> Optional[Dict[str, Any]]:
    """Return the verified resolver result to APPLY iff it should override a geometry-only A
    path_trace, else None. NARROW safety override (NOT a rerank): fires ONLY when an owner-
    reviewed frame resolution fully resolves AND carries equation(start) + matchline + endpoint
    anchors AND an owner-reviewed BOC entry exists AND the resolver endpoint sheet PASSES the
    authored-endpoint + BOC proof while EVERY sheet of the A trace FAILS it. Any A trace that
    itself passes the authored-endpoint proof is left exactly as the engine drew it."""
    try:
        mr = _matchline_resolve(log_id, doc, sheet_offset, out_dir, data_dir)
        if not (mr and mr.get("resolved")):
            return None
        res = _resolutions(data_dir).get(log_id) or {}
        anchors = res.get("anchors", [])
        end = next((a for a in anchors if a.get("kind") == "station"), None)
        if not (end and res.get("matchline_seam")
                and any(a.get("kind") == "equation" for a in anchors)):
            return None
        from . import boc_offset as boc_mod
        ev = _boc_evidence(data_dir).get(log_id)
        if not ev:
            return None
        end_sta = end["station"]
        struct = ev.get("endpoint_structure", "INSTALLER HH")
        boc_ft = ev.get("boc_ft")
        res_ok = boc_mod.prove_candidate(
            boc_mod.tx.get_page(doc, end["sheet"], sheet_offset), end_sta, boc_ft, struct
        )["corroborated"]
        a_sheets = rec.get("sheets") or []
        a_fail = bool(a_sheets) and all(
            not boc_mod.prove_candidate(
                boc_mod.tx.get_page(doc, s, sheet_offset), end_sta, boc_ft, struct)["corroborated"]
            for s in a_sheets)
        if res_ok and a_fail:
            mr = dict(mr)
            mr["override"] = {
                "superseded_status": rec.get("status"), "a_trace_sheets": a_sheets,
                "resolver_endpoint_sheet": end["sheet"],
                "reason": (f"geometry-only A path_trace on sheet(s) {a_sheets} lacks authored STA "
                           f"{end_sta} {struct} + {boc_ft}' BOC; owner-reviewed resolver "
                           f"(equation+matchline+endpoint, BOC-corroborated on sheet {end['sheet']}) "
                           f"supersedes")}
            return mr
        return None
    except Exception:
        return None  # any failure -> do NOT override; leave the engine's A trace untouched


def _struct_connector_enabled() -> bool:
    """Default-OFF (stacks on TRUELINE_MATCHLINE_FRAME_RESOLVER). When ON, a SINGLE-SHEET
    start->end resolver frame whose two ends are PROVEN structures on one sheet (e.g. log66's
    straight HH-HH street crossing) also gets a RED structure-to-structure connector drawn between
    the two proven anchor centroids. OFF -> proof boxes only (unchanged). NEVER applies to a
    cross-sheet/matchline frame (log56/58) and NEVER traces or guesses a curved duct path."""
    return str(os.environ.get("TRUELINE_REDLINE_STRUCT_CONNECTOR", "")).strip().lower() in {
        "1", "true", "yes", "on"}


def _physical_anchor_enabled() -> bool:
    """Default-OFF (stacks on TRUELINE_REDLINE_STRUCT_CONNECTOR). When ON, the single-
    sheet connector draws to the DETERMINISTIC physical structure node (authored CAD
    layer, uniqueness-gated via physical_anchor_resolver) instead of the callout-text
    centroid. If a unique physical anchor cannot be proven for BOTH ends, it FALLS BACK
    to the text centroid (never a guess). Seeded for bore_log66; single-sheet only;
    NEVER applies to a cross-sheet/matchline frame."""
    return str(os.environ.get("TRUELINE_PHYSICAL_ANCHOR_RESOLVER", "")).strip().lower() in {
        "1", "true", "yes", "on"}


def _cross_sheet_seam_stitch_enabled() -> bool:
    """Default-OFF (stacks on TRUELINE_MATCHLINE_FRAME_RESOLVER). When ON, a cross-sheet
    (matchline-seam) frame draws TWO per-sheet redline segments via the bore-run tracer +
    physical_anchor_resolver, using an owner-reviewed+machine-verified seam anchor on the
    side whose delivered vectors are disconnected. log56-only slice; abstains (no draw)
    unless all four anchors resolve. NEVER one continuous cross-page line."""
    return str(os.environ.get("TRUELINE_CROSS_SHEET_SEAM_STITCH", "")).strip().lower() in {
        "1", "true", "yes", "on"}


# D25: run-wrong segment children of a continuous parent run must NOT draw a standalone
# structure-to-structure connector — their far endpoint is an INTERIOR local reset, not a true
# terminus, so a standalone draw is leg-true but RUN-WRONG. They fall through to evidence-card
# behavior, exactly like log58 (which is contained via the seam path). bore_log66 = the first 55'
# stub of bore_log33's continuous 650' run (sheets 10->9; sibling log65 carries 4+51->6+50).
# Re-enable ONLY after the run-33 re-join. See decisions D25 / D22.
_STRUCT_CONNECTOR_PAUSED = frozenset({"bore_log66"})


def _render_struct_connector(mr: Mapping[str, Any], res: Mapping[str, Any], doc: Any,
                             sheet_offset: int, out_dir: str) -> Optional[str]:
    """Draw a RED structure-to-structure connector between the two PROVEN anchor centroids of a
    single-sheet start->end resolver frame, reusing the engine's ``render_redline_overlay``.
    Returns the overlay basename or None. STRICTLY bounded: single-sheet only (no matchline seam);
    needs a proven start anchor + a proven end anchor with captured bboxes on the SAME sheet
    (log54 host-only frames are excluded — no role=end). It is a straight line between two AUTHORED
    structures (honest for a straight HH-HH crossing), labeled structure_to_structure — NOT a
    traced duct vector, never a curved guess. Never raises."""
    try:
        if mr.get("seam"):  # cross-sheet -> NOT a single straight crossing (leave 56/58 alone)
            return None
        if str(res.get("bore_id")) in _STRUCT_CONNECTOR_PAUSED:  # D25: run-wrong child -> evidence only
            return None
        overlays = mr.get("overlays") or []
        start = next((o for o in overlays
                      if o.get("role") in ("start", "reset_origin", "reset") and o.get("bbox")), None)
        end = next((o for o in overlays if o.get("role") == "end" and o.get("bbox")), None)
        if not (start and end) or start.get("sheet") != end.get("sheet"):
            return None
        from redline_pdf_first.pdf import text_extract, crop

        def ctr(b):
            return [(float(b[0]) + float(b[2])) / 2.0, (float(b[1]) + float(b[3])) / 2.0]

        page = text_extract.get_page(doc, start["sheet"], sheet_offset)
        elements = [{"role": "endpoint", "bbox_display": list(start["bbox"])},
                    {"role": "endpoint", "bbox_display": list(end["bbox"])}]
        pts = [ctr(start["bbox"]), ctr(end["bbox"])]
        # PHYSICAL-ANCHOR resolver (default-OFF, stacks on the struct connector). The
        # callout bbox PROVED identity upstream; re-anchor the DRAW to the authored
        # physical structure node when it resolves UNIQUELY on an allowed CAD layer
        # (never nearest-guessing). Falls back to the text centroid (the values already
        # in `pts`/`elements`) when not uniquely proven for BOTH ends. Single-sheet only
        # (this whole function already returns above for matchline-seam frames).
        if _physical_anchor_enabled():
            try:
                from . import physical_anchor_resolver as _par
                from redline_pdf_first.pdf import vector_extract as _ve
                _pa = _par.resolve_connector_anchors(
                    list(start["bbox"]), list(end["bbox"]), _ve.extract_paths(page))
                if _pa.get("resolved"):
                    elements = [{"role": "endpoint", "bbox_display": list(_pa["start"]["bbox"])},
                                {"role": "endpoint", "bbox_display": list(_pa["end"]["bbox"])}]
                    pts = [list(_pa["start_anchor"]), list(_pa["end_anchor"])]
                    _pa["applied"] = True
                else:
                    _pa["applied"] = False
                if isinstance(mr, dict):
                    mr["physical_anchor"] = _pa
            except Exception:
                pass  # any resolver failure -> keep the proven text-box anchor (no guess)
        bore = res.get("bore_id", "bore")
        fn = f"{bore}_s{start['sheet']}_structure_to_structure.png"
        cap = (f"{bore} structure-to-structure redline "
               f"({start.get('label') or start.get('station')} -> "
               f"{end.get('label') or end.get('station')}; straight crossing, not a traced duct)")
        outp = crop.render_redline_overlay(page, elements, pts, os.path.join(out_dir, fn),
                                           accent=(220, 25, 25), dashed=False, caption=cap)
        return os.path.basename(outp) if outp else None
    except Exception:
        return None


def _render_cross_sheet_seam_stitch(mr: Mapping[str, Any], res: Mapping[str, Any], doc: Any,
                                    sheet_offset: int, out_dir: str) -> Optional[Dict[str, Any]]:
    """Cross-sheet (matchline-seam) seam stitch — log56-only, default-OFF
    (TRUELINE_CROSS_SHEET_SEAM_STITCH). Each per-sheet segment FOLLOWS the AUTHORED bore
    path (never a straight anchor-to-anchor connector):
      sheet 17: physical start HH -> seam, drawn along the authored bore-run path the tracer
                reconstructs (parent-tracked through the vector graph); abstains if not unique.
      sheet 21: delivered vectors are DISCONNECTED -> no machine-traceable path; this segment
                ABSTAINS (no diagonal) pending an owner-reviewed + machine-VERIFIED
                seam_anchor_overrides[].path_xy polyline.
    All four anchors (start HH, s17 seam crossing, owner-verified s21 seam entry, endpoint HH)
    gate the run; each segment is then drawn ONLY from authored geometry. Resolves when at least
    the authored s17 path draws; per-segment status/reason stashed on mr. Never one continuous
    cross-page line. Never raises."""
    try:
        if not mr.get("seam"):
            return None
        if str(res.get("bore_id")) != "bore_log56":          # narrow slice: log56 only
            return None
        s21_override = next((o for o in (res.get("seam_anchor_overrides") or [])
                             if int(o.get("sheet", -1)) == 21), None)
        if not s21_override:
            return None
        from . import physical_anchor_resolver as _par
        from . import cross_sheet_seam_tracer as _cst
        from . import authored_path_selector as _aps
        from redline_pdf_first.pdf import text_extract as _tx, vector_extract as _ve, crop as _crop

        ov = {o.get("role"): o for o in (mr.get("overlays") or []) if o.get("bbox")}
        start_ov, end_ov = ov.get("start"), ov.get("end")
        if not (start_ov and end_ov):
            if isinstance(mr, dict):
                mr["cross_sheet_seam_stitch"] = {"resolved": False, "reason": "missing_start_or_end_overlay"}
            return None
        s17, s21 = int(start_ov["sheet"]), int(end_ov["sheet"])
        page17 = _tx.get_page(doc, s17, sheet_offset)
        page21 = _tx.get_page(doc, s21, sheet_offset)

        # (a) machine: sheet-17 physical start HH
        start_hh = _par.resolve_physical_anchor(list(start_ov["bbox"]), _ve.extract_paths(page17))
        # (b) machine: sheet-17 seam crossing (bore-run tracer)
        s17_ml = [p for p in _ve.extract_paths(page17) if str(p.get("layer")) == "MATCHLINE"]
        s17_seam = (_cst.trace_seam_anchor(_ve.extract_segments(page17), s17_ml, start_hh["anchor"])
                    if start_hh.get("resolved") else {"resolved": False, "reason": "start_hh_unresolved"})
        # (c) machine: sheet-21 physical endpoint HH
        end_hh = _par.resolve_physical_anchor(list(end_ov["bbox"]), _ve.extract_paths(page21))
        # (d) owner-reviewed + MACHINE-VERIFIED: sheet-21 seam entry (delivered s21 vectors disconnected)
        s21_ml = [p for p in _ve.extract_paths(page21) if str(p.get("layer")) == "MATCHLINE"]
        owner = _cst.verify_owner_seam_anchor(
            s21_override.get("proposed_xy"), s21_ml, _ve.extract_segments(page21),
            sheet=int(s21_override.get("sheet")), expected_sheet=21)

        anchors = {
            "sheet17_start_hh": {"source": "machine", "resolved": bool(start_hh.get("resolved")),
                                 "xy": start_hh.get("anchor"), "reason": start_hh.get("reason")},
            "sheet17_seam_crossing": {"source": "machine", "resolved": bool(s17_seam.get("resolved")),
                                      "xy": s17_seam.get("seam_anchor"), "reason": s17_seam.get("reason")},
            "sheet21_seam_crossing": {"source": "owner_reviewed_machine_verified",
                                      "resolved": bool(owner.get("verified")), "xy": owner.get("snapped_xy"),
                                      "reason": owner.get("reason"), "checks": owner.get("checks")},
            "sheet21_end_hh": {"source": "machine", "resolved": bool(end_hh.get("resolved")),
                               "xy": end_hh.get("anchor"), "reason": end_hh.get("reason")},
        }
        all_ok = bool(start_hh.get("resolved") and s17_seam.get("resolved")
                      and end_hh.get("resolved") and owner.get("verified"))
        if not all_ok:
            if isinstance(mr, dict):
                mr["cross_sheet_seam_stitch"] = {
                    "resolved": False, "run_id": "bore_log56", "reason": "cross_sheet_seam_stitch_abstain",
                    "machine_resolved_anchors": 3, "owner_verified_anchors": 1, "anchors": anchors,
                    "note": "required all four anchors; delivered sheet-21 vector run is disconnected"}
            return None

        def _bx(pt, r=4.0):
            return [pt[0] - r, pt[1] - r, pt[0] + r, pt[1] + r]
        bore = str(res.get("bore_id"))

        # --- Sheet 17: AUTHORED EVIDENCE-FUSION selector (STEP 2). Draws ONLY when run color +
        #     named matchline + a UNIQUE color-isolated candidate path + station monotonicity +
        #     BOC/11' corridor ALL agree on one authored path; else ABSTAINS with a precise reason.
        #     Connectivity is candidate geometry only, applied AFTER the authored discriminators.
        _seam = mr.get("seam") or {}
        _words17 = _tx.extract_words(page17)
        sel17 = _aps.select_authored_s17_path(
            segments=_ve.extract_segments(page17), matchline_paths=s17_ml,
            start_xy=start_hh["anchor"], home_sta=_seam.get("home_sta"), neighbor_sta=_seam.get("neighbor_sta"),
            expected_neighbor_sheet=_seam.get("neighbor_sheet"),
            station_callouts=_aps.parse_station_callouts(_words17),
            matchline_callouts=_aps.parse_matchline_callouts(_tx.extract_blocks(page17)),
            offset_callouts=_aps.parse_offset_callouts(_words17), boc_ft=res.get("boc_ft"))
        seg17 = None
        if sel17.get("resolved") and sel17.get("path_xy"):
            pts17 = [list(p) for p in sel17["path_xy"]]
            seg17 = _crop.render_redline_overlay(
                page17, [{"role": "endpoint", "bbox_display": _bx(pts17[0])},
                         {"role": "endpoint", "bbox_display": _bx(pts17[-1])}], pts17,
                os.path.join(out_dir, f"{bore}_s{s17}_seam_stitch.png"), accent=(220, 25, 25), dashed=False,
                caption=f"{bore} sheet {s17}: start HH -> seam, authored evidence-fused path (cross-sheet run 1/2)")
        s17_seg = {"sheet": s17, "from": "sheet17_start_hh", "to": "sheet17_seam_crossing",
                   "artifact_name": (os.path.basename(seg17) if seg17 else None),
                   "geometry": ("authored_path_evidence_fused" if seg17 else None),
                   "path_vertices": (len(sel17.get("path_xy") or []) if seg17 else None),
                   "status": ("drawn" if seg17 else "abstained_pending_evidence_fusion"),
                   "reason": (None if seg17 else sel17.get("reason")),
                   "discriminators": sel17.get("discriminators"),
                   "evidence": sel17.get("evidence"),
                   "start_hh_xy": start_hh.get("anchor"),
                   "named_seam_sta": _seam.get("home_sta")}

        # --- Sheet 21: delivered vectors are DISCONNECTED (no authored seam->HH chain), so there
        #     is NO machine-traceable path. Do NOT draw a straight diagonal -- ABSTAIN. A path-
        #     following s21 segment needs an owner-reviewed, machine-VERIFIED polyline override
        #     (seam_anchor_overrides[].path_xy), added + approved separately. The verified owner
        #     seam POINT proves the seam ENTRY only, never the route.
        seg21 = None
        s21_seg = {"sheet": s21, "from": "sheet21_seam_crossing", "to": "sheet21_end_hh",
                   "artifact_name": None, "geometry": None,
                   "status": "abstained_requires_path_evidence",
                   "reason": "s21_vectors_disconnected_no_authored_path",
                   "verified_seam_entry_xy": owner.get("snapped_xy"),
                   "endpoint_hh_xy": end_hh.get("anchor"),
                   "owner_path_override": "absent",
                   "note": "supply an owner-reviewed + machine-verified seam_anchor_overrides[].path_xy "
                           "to draw the s21 route; a single owner seam point is entry-only"}

        rec = {"resolved": bool(seg17 or seg21), "run_id": "bore_log56",
               "reason": ("cross_sheet_seam_path_stitched" if (seg17 and seg21)
                          else "cross_sheet_seam_path_partial_s17_only" if seg17
                          else "cross_sheet_seam_abstain_pending_evidence_fusion"),
               "machine_resolved_anchors": 3, "owner_verified_anchors": 1,
               "owner_seam_reason": s21_override.get("reason"), "anchors": anchors,
               "segments": [s17_seg, s21_seg],
               "note": "two per-sheet overlays = ONE cross-sheet bore_log56 run, each FOLLOWING the "
                       "authored bore path. s17 traced from authored vectors; s21 abstains "
                       "(disconnected vectors) pending an owner-reviewed verified path_xy polyline."}
        if isinstance(mr, dict):
            mr["cross_sheet_seam_stitch"] = rec
        return rec if rec.get("resolved") else None
    except Exception:
        return None


def compute_physical_anchor_evidence(start_bbox, end_bbox, paths) -> Dict[str, Any]:
    """Item 3 (Slice A.2) — resolve the physical structure-anchor pair as READ-ONLY EVIDENCE.
    Thin wrapper over ``physical_anchor_resolver.resolve_connector_anchors`` that tags the result
    ``applied=False`` / ``evidence_only=True`` so nothing downstream can mistake it for a draw
    anchor. The resolver itself is pure + uniqueness-gated; this adds no placement logic."""
    from . import physical_anchor_resolver as _par
    pa = _par.resolve_connector_anchors(list(start_bbox), list(end_bbox), paths)
    pa["applied"] = False
    pa["evidence_only"] = True
    return pa


def _attach_physical_anchor_evidence(mr: Dict[str, Any], doc: Any, sheet_offset: int) -> None:
    """Stash READ-ONLY physical-anchor evidence on ``mr['physical_anchor']`` for a single-sheet
    start->end resolver frame whose connector draw path did NOT compute it (e.g. log66 resolved via
    the station-frame/matchline overlay). EVIDENCE ONLY: never draws, never sets ``struct_connector``,
    never touches overlays or the rendered artifact. Single-sheet only. Never raises (failure -> no-op)."""
    try:
        overlays = mr.get("overlays") or []
        start = next((o for o in overlays
                      if o.get("role") in ("start", "reset_origin", "reset") and o.get("bbox")), None)
        end = next((o for o in overlays if o.get("role") == "end" and o.get("bbox")), None)
        if not (start and end) or start.get("sheet") != end.get("sheet"):
            return
        from redline_pdf_first.pdf import text_extract as _tx, vector_extract as _ve
        page = _tx.get_page(doc, start["sheet"], sheet_offset)
        mr["physical_anchor"] = compute_physical_anchor_evidence(
            list(start["bbox"]), list(end["bbox"]), _ve.extract_paths(page))
    except Exception:
        return  # evidence-only: any failure leaves the card exactly as before


_BOC_VERDICT_LABELS = {
    "BOC_CONTEXT_CORROBORATED": "corroborated",
    "DOWNGRADE_BOC_OFFSET_MISMATCH": "mismatch",
    "DOWNGRADE_STRUCTURE_ONLY_NO_BOC_CALLOUT": "structure_only",
    "BLOCKED_NO_AUTHORED_ENDPOINT_STRUCTURE": "blocked",
}


def _boc_verdict_label(raw_verdict) -> str:
    """Map a ``boc_offset.prove_candidate`` raw verdict to a short reviewable label
    (corroborated | mismatch | structure_only | blocked | unknown)."""
    return _BOC_VERDICT_LABELS.get(str(raw_verdict), "unknown")


def _attach_boc_corroboration(mr: Dict[str, Any], res: Mapping[str, Any], doc: Any,
                              sheet_offset: int) -> None:
    """Item 4 (Slice A) — READ-ONLY BOC/offset corroboration at the resolved endpoint. Runs the
    EXISTING deterministic ``boc_offset.prove_candidate`` (authored endpoint STA + structure + a
    co-located ``<boc>'`` offset callout) and stashes the verdict on ``mr['boc_corroboration']`` for
    WHY/EVIDENCE. EVIDENCE ONLY: never gates draw/abstain/placement/route/station-frame, never
    changes the overlay/artifact, never mutates ``res``. Single endpoint sheet. Never raises."""
    try:
        anchors = res.get("anchors") or []
        end = next((a for a in anchors if a.get("role") == "end"), None)
        boc_ft = res.get("boc_ft")
        if not end or end.get("sheet") is None or boc_ft is None:
            return
        # Authored endpoint LOCAL station (strip any '=0+00' reset/equation suffix) — the form the
        # endpoint sheet's authored callout carries (mirrors the proven false-A override usage).
        end_sta = str(end.get("station") or "").split("=")[0].strip()
        if not end_sta:
            return
        structure_kw = res.get("endpoint_structure") or "INSTALLER HH"
        from . import boc_offset as _boc
        page = _boc.tx.get_page(doc, end["sheet"], sheet_offset)
        pv = _boc.prove_candidate(page, end_sta, boc_ft, structure_kw)
        mr["boc_corroboration"] = {
            "verdict": _boc_verdict_label(pv.get("verdict")),
            "raw_verdict": pv.get("verdict"),
            "corroborated": bool(pv.get("corroborated")),
            "boc_ft": boc_ft,
            "boc_token": pv.get("boc_token"),
            "endpoint_sheet": end.get("sheet"),
            "endpoint_station": end_sta,
            "structure": structure_kw,
            "nearby_offsets": pv.get("nearby_offsets") or [],
            "evidence_only": True,
        }
    except Exception:
        return  # evidence-only: any failure leaves the card exactly as before


def _resolver_card(log_id: str, mr: Mapping[str, Any], rec: Mapping[str, Any],
                   res: Mapping[str, Any]) -> Dict[str, Any]:
    """Translate a verified resolver result into a review-grade evidence card. The ``geo`` block
    mirrors the primary overlay into the slot the existing PdfFirstEvidencePanel already renders
    (``pdf_path_trace`` for a cross-sheet C win / ``pdf_redline`` for a single-sheet B win) with
    ``frame.multi_sheet`` set, so the win lands in the correct coverage group WITH its image and
    needs NO frontend change; the full authored trail lives under ``geo.matchline_resolution``."""
    cross_sheet = bool(mr.get("seam"))
    overlays = mr.get("overlays") or []
    prim = next((o for o in overlays if o.get("role") == "end"), overlays[0] if overlays else None)
    prim_name = os.path.basename(prim["image"]) if (prim and prim.get("image")) else None
    sc = mr.get("struct_connector")  # drawn structure-to-structure connector (single-sheet crossing)
    ov_refs = [{"sheet": o.get("sheet"), "role": o.get("role"), "id": o.get("id"),
                "label": o.get("label"), "station": o.get("station"), "kind": o.get("kind"),
                "artifact_name": (os.path.basename(o["image"]) if o.get("image") else None)}
               for o in overlays]
    anchors = res.get("anchors") or []
    start_a = next((a for a in anchors if a.get("role") in ("start", "reset_origin")), None)
    end_a = next((a for a in anchors if a.get("role") == "end"), None)
    end_structs = sorted({a.get("label") for a in anchors if a.get("label")})

    geo: Dict[str, Any] = {
        "geometry_status": mr.get("geometry_status"),
        "frame": {"multi_sheet": cross_sheet},
        "matchline_resolution": {
            "group": mr.get("group"), "status": mr.get("status"),
            "class": res.get("class"), "sheets": mr.get("sheets"), "seam": mr.get("seam"),
            "canonical_span": mr.get("canonical_span"), "hh_hh_ft": res.get("hh_hh_ft"),
            "boc_ft": res.get("boc_ft"), "overlays": ov_refs, "override": mr.get("override"),
            "verification_trail": mr.get("verification_trail"),
        },
    }
    # Item 3 (Slice A.2) — surface the physical-anchor EVIDENCE (set by the connector draw path OR
    # the read-only evidence pass) so build_review_reason can show physical_handhole_anchor. Read-only
    # projection: the drawn overlay/artifact is decided below and is NOT affected by this.
    _pa = mr.get("physical_anchor")
    if isinstance(_pa, dict) and _pa:
        geo["physical_anchor"] = _pa
    # Item 4 (Slice A) — surface the READ-ONLY BOC/offset corroboration so build_review_reason can
    # show a boc_corroboration discriminator. Projection only; never affects the drawn artifact.
    _bocc = mr.get("boc_corroboration")
    if isinstance(_bocc, dict) and _bocc:
        geo["boc_corroboration"] = _bocc
    # Cross-sheet seam-stitch evidence (default-OFF). Surfaces the two per-sheet segments +
    # the 3-machine / 1-owner-verified anchor breakdown. Additive; absent when the flag is off.
    _css = mr.get("cross_sheet_seam_stitch")
    if isinstance(_css, dict):
        geo["cross_sheet_seam_stitch"] = _css
        if _css.get("resolved"):
            geo["matchline_resolution"]["cross_sheet_segments"] = _css.get("segments")
    # Mirror the displayed overlay into the existing-frontend slot (no FE change needed).
    if sc:
        # Drawn structure-to-structure redline -> path-trace slot (single-sheet -> Group A "drawn").
        geo["pdf_path_trace"] = {
            "artifact_name": sc, "trace_status": "STRUCTURE_TO_STRUCTURE",
            "path_basis": "structure_to_structure (authored straight crossing; not a traced duct vector)"}
        geo["matchline_resolution"]["redline_path"] = {
            "kind": "structure_to_structure", "sheet": (prim.get("sheet") if prim else None),
            "artifact_name": sc}
    elif cross_sheet:
        geo["pdf_path_trace"] = {"artifact_name": prim_name,
                                 "trace_status": mr.get("geometry_status"),
                                 "path_basis": "authored matchline frame"}
    else:
        geo["pdf_redline"] = {"artifact_name": prim_name}

    if mr.get("override"):
        cav_text = "RESOLVER OVERRIDE: " + mr["override"]["reason"]
    elif cross_sheet:
        seam = mr.get("seam") or {}
        cav_text = (f"authored matchline frame resolved across sheets {mr.get('sheets')} "
                    f"(seam {seam.get('home_sta')}/{seam.get('neighbor_sta')}); "
                    f"{len(overlays)} evidence overlays")
    else:
        cav_text = (f"authored station-frame resolved on sheet {mr.get('sheets')} via reset + "
                    f"host anchors; {len(overlays)} evidence overlays")

    return {
        "log_ids": [log_id],
        "segment_id": f"{log_id}-resolver",
        "tier": "SHARED_SEGMENT_REVIEW",  # review surface; never an AUTO_SELECT placement
        "surface": "review",
        "group_id": None,
        "requires_approval": True,
        "print": rec.get("print"),
        "sheets": mr.get("sheets"),
        "page": (prim.get("sheet") if prim else None),
        "station_range": {
            "start": (start_a or {}).get("station") or (start_a or {}).get("phys_sta"),
            "end": (end_a or {}).get("station"),
        },
        "footage": res.get("hh_hh_ft"),
        "conduit": None,
        "end_structures": end_structs,
        "evidence": [o.get("label") or o.get("id") for o in overlays],
        "caveat": {"code": mr.get("geometry_status"), "text": cav_text},
        "render_target": "evidence_card",
        "render_artifact_ref": (sc or prim_name),
        "geo": geo,
    }


def _recount(env: Dict[str, Any]) -> None:
    env["counts_by_surface"] = {
        "placements": len(env.get("placements") or []),
        "review_items": len(env.get("review_items") or []),
        "fail_safe": len(env.get("fail_safe") or []),
    }


def apply_resolver(log_id: str, env: Dict[str, Any], doc: Any, sheet_offset: int,
                   out_dir: str, data_dir: str) -> Dict[str, Any]:
    """Envelope-space resolver consult for ONE log (mirrors the proven offline coverage consult).
    LIFT a blocked / fail-safe FRAME_ONLY bore into a matchline (C) / station-frame (B) review
    card, OR let an owner-reviewed + BOC-corroborated resolver entry OVERRIDE a geometry-only A
    path_trace placement (dropping the superseded placement). Returns the (possibly) modified
    env. Never raises (any failure -> env unchanged)."""
    try:
        res = _resolutions(data_dir).get(log_id)
        if not res:
            return env  # no owner-reviewed resolution for this log -> untouched
        rec = classify(env)
        status = rec.get("status")
        mr: Optional[Dict[str, Any]] = None
        if status in ("blocked", "fail_safe"):
            mr = _matchline_resolve(log_id, doc, sheet_offset, out_dir, data_dir)
            mr = mr if (mr and mr.get("resolved")) else None
        elif status == "path_trace_drawn":
            mr = _resolver_overrides_false_A(log_id, rec, doc, sheet_offset, out_dir, data_dir)
        if not (mr and mr.get("resolved")):
            return env

        # Step A (default-OFF TRUELINE_REDLINE_STRUCT_CONNECTOR): for a single-sheet start->end
        # frame (e.g. log66's straight HH-HH crossing) draw a red structure-to-structure connector
        # between the two PROVEN anchor centroids. Failure-safe -> falls back to proof boxes.
        if _struct_connector_enabled():
            from app.core import mrq_perf_probe as _perf  # lazy; timed() no-op when inactive
            with _perf.timed("struct_connector"):
                _sc = _render_struct_connector(mr, res, doc, sheet_offset, out_dir)
            if _sc:
                mr = dict(mr)
                mr["struct_connector"] = _sc
        # Cross-sheet seam stitch (default-OFF TRUELINE_CROSS_SHEET_SEAM_STITCH; log56-only):
        # two per-sheet segments from 3 machine anchors + 1 owner-reviewed+verified s21 seam
        # anchor. Stashes onto mr (resolved or abstain); never draws unless all four resolve.
        if _cross_sheet_seam_stitch_enabled():
            if not isinstance(mr, dict):
                mr = dict(mr)
            from app.core import mrq_perf_probe as _perf  # lazy; timed() no-op when inactive
            with _perf.timed("seam_stitch"):
                _render_cross_sheet_seam_stitch(mr, res, doc, sheet_offset, out_dir)
        # Item 3 (Slice A.2): READ-ONLY physical-anchor evidence when the connector draw path did
        # not compute it (e.g. log66 single-sheet HH-HH resolved via the station-frame/matchline
        # overlay). Additive evidence ONLY — never sets struct_connector, never changes the draw.
        if not mr.get("seam") and not mr.get("physical_anchor"):
            if not isinstance(mr, dict):
                mr = dict(mr)
            _attach_physical_anchor_evidence(mr, doc, sheet_offset)
        # Item 4 (Slice A): READ-ONLY BOC/offset corroboration at the resolved endpoint. Additive
        # evidence ONLY — never changes draw/abstain/placement/route/station-frame behavior.
        if not mr.get("boc_corroboration"):
            if not isinstance(mr, dict):
                mr = dict(mr)
            _attach_boc_corroboration(mr, res, doc, sheet_offset)
        card = _resolver_card(log_id, mr, rec, res)
        if mr.get("override"):
            # clear the superseded geometry-only A placement(s) for this log
            env["placements"] = [c for c in (env.get("placements") or [])
                                 if log_id not in (c.get("log_ids") or [])]
        if status == "fail_safe":
            env["fail_safe"] = [c for c in (env.get("fail_safe") or [])
                                if log_id not in (c.get("log_ids") or [])]
        env.setdefault("review_items", []).append(card)
        _recount(env)
        cbt = env.setdefault("counts_by_tier", {})
        cbt["MATCHLINE_FRAME_RESOLVER"] = cbt.get("MATCHLINE_FRAME_RESOLVER", 0) + 1
        return env
    except Exception:
        return env


__all__ = ["apply_corrections", "apply_resolver", "classify", "open_document"]
