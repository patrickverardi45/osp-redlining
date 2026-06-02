"""PDF-first selector funnel: bore log -> candidate sheets (from the bore-log
``print`` column) -> authored callouts -> candidate chains -> score -> tier ->
EngineResult.

Day-2: boundary chains (endpoints align) -> AUTO / FAIL_SAFE.
Day-3 additions: a REVIEW-GRADE overlap/containment matcher for interior-endpoint
bores (the bore lies inside an authored chain), and named-structure attachment.
NO coordinate-snapping, NO KMZ-as-source, NO manual placement. render_target=evidence_card.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..contracts import (
    Callout,
    Caveat,
    EngineResult,
    Evidence,
    FailSafeItem,
    Placement,
    RouteKey,
    SelectedSegment,
    StationSpan,
    StationSpanFt,
    ENGINE_VERSION,
    GEOMETRY_STATUS_AP_ANCHORED,
    GEOMETRY_STATUS_FRAME_ONLY,
    GEOMETRY_STATUS_FRAME_WITH_DROP_TERMINAL_CANDIDATE,
    RENDER_TARGET_EVIDENCE_CARD,
    REVIEW_TIERS,
    STATUS_FAIL_SAFE_GLOBAL,
    STATUS_OK,
    TIER_AUTO_PLACED_REQUIRES_APPROVAL,
    TIER_AUTO_SELECT,
    TIER_FAIL_SAFE,
    error_result,
)
from ..geometry import identity_binder as binder
from ..geometry import path_tracer
from ..parsing import borelog_reader
from ..parsing import callouts as co
from ..parsing import drop_terminal as dropterm
from ..parsing import structures as struct
from ..pdf import text_extract
from ..rulebook import tiering
from . import candidate_builder as cb
from . import evidence_scorer as es


def _chain_summary(chain: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {"sheets": sorted({c["sheet"] for c in chain}),
            "from": chain[0]["from_sta"], "to": chain[-1]["to_sta"],
            "footage": round(sum(c["footage"] for c in chain), 2),
            "boxes": [c["text"] for c in chain]}


def _print_tokens(print_raw) -> List[str]:
    """Authored print tokens from the bore-log 'print' column (e.g. '8,9' -> ['8','9']).
    Pure string split of authored evidence — no route scoring, no catalog lookup."""
    if not print_raw:
        return []
    s = str(print_raw)
    for sep in (";", "/", "|", " "):
        s = s.replace(sep, ",")
    return [t.strip() for t in s.split(",") if t.strip()]


def _review_grade(all_callouts, bore_start, bore_end, span) -> Optional[Dict[str, Any]]:
    """Interior-endpoint match: an authored chain that CONTAINS or substantially
    OVERLAPS the bore span. Returns a decision dict or None."""
    chains = cb.build_chains(all_callouts, bore_start, bore_end, start_tol=10000.0)
    cands = []
    for ch in chains:
        c0, c1 = ch[0]["from_ft"], ch[-1]["to_ft"]
        ov = max(0.0, min(c1, bore_end) - max(c0, bore_start))
        if span <= 0 or ov < 0.5 * span:
            continue
        sc = es.score_chain(ch, bore_start, bore_end, span)
        contains = (c0 <= bore_start + 8.0) and (c1 >= bore_end - 8.0)
        sc["overlap_frac"] = round(ov / span, 3)
        sc["contains"] = contains
        cands.append((ch, sc))
    if not cands:
        return None
    cands.sort(key=lambda t: (0 if t[1]["contains"] else 1,
                              abs(t[1]["summed_ft"] - span),
                              t[1]["vacant"], t[1]["n_boxes"], -t[1]["overlap_frac"]))
    best_ch, best = cands[0]
    # >=2 co-equal parallel overlap candidates with no tiebreaker -> FAIL_SAFE (parallel corridors).
    if len(cands) >= 2:
        rch, r = cands[1]
        bfd = abs(best["summed_ft"] - span)
        rfd = abs(r["summed_ft"] - span)
        same_seg = (best_ch[0]["from_sta"], best_ch[-1]["to_sta"]) == (rch[0]["from_sta"], rch[-1]["to_sta"])
        if (not same_seg and abs(bfd - rfd) <= 5.0
                and best["vacant"] == r["vacant"] and best.get("contains") == r.get("contains")):
            return {"tier": TIER_FAIL_SAFE, "winner": None, "caveat": None,
                    "reason": "GE_2_COEQUAL_OVERLAP_CANDIDATES",
                    "ambiguous": [best_ch, rch], "n_acceptable": len(cands)}
    caveats = ["INTERIOR_ENDPOINT"]
    if best["multi_sheet"]:
        caveats.append("MATCHLINE_PAGE_FLIP")
    return {"tier": TIER_AUTO_PLACED_REQUIRES_APPROVAL, "winner": best_ch,
            "caveat": "|".join(caveats), "reason": "REVIEW_GRADE_OVERLAP_MATCH",
            "ambiguous": [], "n_acceptable": len(cands), "score": best}


def _attach_structures(doc, winner, page_cache, sheet_offset) -> List[str]:
    out: List[str] = []
    for c in winner:
        page = page_cache.get(c["sheet"])
        if page is None:
            continue
        toks = struct.extract_structures(page)
        for s in struct.structures_near(page, c.get("bbox_display"), toks):
            if s not in out:
                out.append(s)
    return out


def _run_selection(bore: Dict[str, Any], pdf_path: str, sheet_offset: int,
                   source: Dict[str, Any], job_id: str,
                   anchor_tables: Optional[Dict[str, Any]] = None,
                   trace_paths: bool = False, dash_chain: bool = False) -> EngineResult:
    """Shared selector core — IDENTICAL for file-fed and row-fed input. Consumes
    the normalized bore model + the plan PDF and never branches on input origin,
    so ``select`` and ``select_from_rows`` produce equivalent EngineResults."""
    source.update({"log_id": bore["log_id"], "candidate_sheets": bore["candidate_sheets"],
                   "bore_station": f"{bore['station_start']}->{bore['station_end']}",
                   "bore_span_ft": bore["span_ft"], "print": bore["print_raw"]})

    doc = text_extract.open_document(pdf_path)
    try:
        page_cache: Dict[int, Any] = {}
        all_callouts: List[Dict[str, Any]] = []
        for sheet in bore["candidate_sheets"]:
            idx = sheet + sheet_offset - 1
            if idx < 0 or idx >= doc.page_count:
                continue
            page = doc[idx]
            page_cache[sheet] = page
            all_callouts.extend(co.extract_callouts(page, sheet, sheet_offset))

        chains = cb.build_chains(all_callouts, bore["station_start_ft"], bore["station_end_ft"])
        scored = [(ch, es.score_chain(ch, bore["station_start_ft"],
                                      bore["station_end_ft"], bore["span_ft"])) for ch in chains]
        decision = tiering.decide(scored, bore["span_ft"])

        # Day-3 review-grade fallback for interior-endpoint bores.
        if decision["tier"] == TIER_FAIL_SAFE and decision["reason"] == "NO_AUTHORED_BOX_MATCH_FOR_BORE_SPAN":
            rg = _review_grade(all_callouts, bore["station_start_ft"], bore["station_end_ft"], bore["span_ft"])
            if rg is not None:
                decision = rg

        tier = decision["tier"]
        if tier == TIER_FAIL_SAFE or decision["winner"] is None:
            pool = decision["ambiguous"] or [ch for ch, _ in scored]
            return EngineResult(
                job_id=job_id, status=STATUS_FAIL_SAFE_GLOBAL, source=source,
                fail_safe_items=[FailSafeItem(log_ids=[bore["log_id"]], reason=decision["reason"],
                                              candidates=[_chain_summary(ch) for ch in pool[:6]])],
                evidence={"reason": decision["reason"], "n_chains": len(chains)},
                warnings=[f"FAIL_SAFE: {decision['reason']}"])

        winner = decision["winner"]
        sc = es.score_chain(winner, bore["station_start_ft"], bore["station_end_ft"], bore["span_ft"])
        for c in winner:
            page = page_cache.get(c["sheet"])
            if page is not None:
                co.attach_bbox(page, c)
        end_structures = _attach_structures(doc, winner, page_cache, sheet_offset)

        # structure-anchored AUTO upgrade: single box, contains bore, an endpoint
        # exact, and a named structure at it -> AUTO despite an interior other end.
        if (tier == TIER_AUTO_PLACED_REQUIRES_APPROVAL and decision["reason"] == "REVIEW_GRADE_OVERLAP_MATCH"
                and len(winner) == 1 and end_structures
                and (sc["start_delta"] <= 5.0 or sc["end_delta"] <= 5.0)
                and decision["score"].get("contains")):
            tier = TIER_AUTO_SELECT
            decision = {**decision, "tier": tier, "caveat": None,
                        "reason": "STRUCTURE_ANCHORED_END (interior other endpoint)"}

        seg_callouts = [Callout(
            text=c["text"], kind="DIR_BORE", sheet=c["sheet"], page=c["page"],
            station_span=StationSpan(start=c["from_sta"], end=c["to_sta"]),
            footage=c["footage"], conduit=c["conduit"],
            bbox_display=c["bbox_display"], visually_verified=bool(c["bbox_display"])) for c in winner]
        funnel = ["print", "sheet", "station_band", "dir_bore"]
        if sc["multi_sheet"]:
            funnel.append("footage_sum")
        funnel.append("tier")
        evidence = Evidence(
            funnel_path=funnel,
            matched_on=["Print", "Sheet", "Station", "Footage"]
            + (["Matchline"] if sc["multi_sheet"] else []) + (["Structure"] if end_structures else []),
            footage_check={"authored": sc["summed_ft"], "bore_log": bore["span_ft"], "delta": sc["foot_delta"]},
            tiebreaker=("min-footage-delta + prefer active HDPE" if decision.get("n_acceptable", 0) > 1 else None),
            callout_ids=[str(i) for i in range(len(winner))], notes=decision["reason"])
        caveat_obj = (Caveat(code=decision["caveat"], text=f"{decision['caveat']} — human approves before closeout")
                      if decision["caveat"] else None)
        # Phase-2 Slice A: geometry-free placement intent. Absolute authored station
        # feet (already parsed in the bore model) + the AUTHORED route key (print/sheets).
        # No route binding, no coords — that is the deterministic Slice-B adapter step.
        placement = Placement(
            placement_segment_id=(
                f"{bore['log_id']}:"
                f"{int(round(bore['station_start_ft']))}-{int(round(bore['station_end_ft']))}"),
            station_span_ft=StationSpanFt(start=bore["station_start_ft"], end=bore["station_end_ft"]),
            footage_ft=sc["summed_ft"],
            route_key=RouteKey(print_tokens=_print_tokens(bore["print_raw"]),
                               sheets=list(bore["candidate_sheets"])),
        )
        seg = SelectedSegment(
            segment_id=bore["log_id"], log_ids=[bore["log_id"]], tier=tier, print=bore["print_raw"],
            sheets=sc["sheets"], station_span=StationSpan(start=bore["station_start"], end=bore["station_end"]),
            footage=sc["summed_ft"], end_structures=end_structures, conduit=winner[0]["conduit"],
            callouts=seg_callouts, evidence=evidence, render_target=RENDER_TARGET_EVIDENCE_CARD,
            caveat=caveat_obj, requires_approval=(tier in REVIEW_TIERS), placement=placement)
        # Slice B (opt-in): AP/structure-anchored geometry. Only runs when anchor
        # tables are supplied; otherwise placement stays NEEDS_IDENTITY_BINDING.
        # Deterministic, EXACT identity join only — never a route bind / guess.
        if anchor_tables is not None:
            binder.bind_segment(seg, anchor_tables)
            # Fiber-drop enrichment: ONLY for FRAME_ONLY bores (AP_ANCHORED is left
            # untouched). Authored PDF-space, exact-station; never promotes AP/SPLICE.
            if seg.placement is not None and seg.placement.geometry_status == GEOMETRY_STATUS_FRAME_ONLY:
                page = page_cache.get(seg.sheets[0]) if seg.sheets else None
                dt = dropterm.extract(page, winner[0] if winner else None, seg, sheet_offset)
                if dt is not None:
                    seg.placement.drop_terminal = dt
                    seg.placement.geometry_status = GEOMETRY_STATUS_FRAME_WITH_DROP_TERMINAL_CANDIDATE
            # PDF bore-path trace (opt-in seam; default OFF -> path byte-identical).
            # Attaches page-space pdf_path_trace metadata for AP_ANCHORED / drop-terminal
            # placements ONLY when explicitly enabled. Identity-bound, never proximity;
            # never raises. (The drawable overlay PNG is produced render-side.)
            if (trace_paths and seg.placement is not None
                    and seg.placement.geometry_status in (
                        GEOMETRY_STATUS_AP_ANCHORED,
                        GEOMETRY_STATUS_FRAME_WITH_DROP_TERMINAL_CANDIDATE)):
                path_tracer.attach_path_trace(seg, doc, sheet_offset, dash_chain=dash_chain)
        if tier == TIER_AUTO_SELECT:
            return EngineResult(job_id=job_id, status=STATUS_OK, engine_version=ENGINE_VERSION,
                                source=source, selected_segments=[seg], evidence={"reason": decision["reason"]})
        return EngineResult(job_id=job_id, status=STATUS_OK, engine_version=ENGINE_VERSION,
                            source=source, review_items=[seg], evidence={"reason": decision["reason"]})
    finally:
        doc.close()


def select(borelog_path: str, pdf_path: str, sheet_offset: int = 13,
           anchor_tables: Optional[Dict[str, Any]] = None,
           trace_paths: bool = False, dash_chain: bool = False) -> EngineResult:
    """File-fed entrypoint: read a bore-log .xlsx, then run the shared selector.
    ``anchor_tables`` (optional) enables Slice-B AP/structure-anchored geometry.
    ``trace_paths`` (optional, default OFF) additionally attaches page-space
    ``pdf_path_trace`` metadata; ``dash_chain`` enables bounded dash-chain
    reconstruction as the BLOCKED fallback. OFF keeps the result byte-identical."""
    job_id = "sel-unknown"
    source: Dict[str, Any] = {"borelog": borelog_path, "pdf": pdf_path, "sheet_offset": sheet_offset}
    try:
        bore = borelog_reader.read_borelog(borelog_path)
        job_id = f"sel-{bore['log_id']}"
        return _run_selection(bore, pdf_path, sheet_offset, source, job_id, anchor_tables,
                              trace_paths=trace_paths, dash_chain=dash_chain)
    except Exception as exc:
        return error_result(job_id, f"{type(exc).__name__}: {exc}", source)


def select_from_rows(rows, pdf_path: str, source_file: Optional[str] = None,
                     sheet_offset: int = 13,
                     anchor_tables: Optional[Dict[str, Any]] = None,
                     trace_paths: bool = False, dash_chain: bool = False) -> EngineResult:
    """Row-fed entrypoint: normalize TrueLine-style ``committed_rows`` into the
    SAME bore model, then run the SAME selector core (no duplicate selection
    brain). Honest fail-safe: an empty / station-less row set yields an ERROR
    result (never invents a placement). ``anchor_tables`` (optional) enables
    Slice-B AP/structure-anchored geometry. ``trace_paths`` (default OFF) attaches
    page-space ``pdf_path_trace`` metadata; OFF keeps the result byte-identical."""
    job_id = "sel-unknown"
    source: Dict[str, Any] = {"borelog": None, "source_file": source_file,
                              "input": "committed_rows", "pdf": pdf_path, "sheet_offset": sheet_offset}
    try:
        bore = borelog_reader.from_rows(rows, source_file=source_file)
        job_id = f"sel-{bore['log_id']}"
        return _run_selection(bore, pdf_path, sheet_offset, source, job_id, anchor_tables,
                              trace_paths=trace_paths, dash_chain=dash_chain)
    except Exception as exc:
        return error_result(job_id, f"{type(exc).__name__}: {exc}", source)
