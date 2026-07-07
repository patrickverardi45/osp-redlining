"""STRUCTURE-DATUM REVIEW-CANDIDATE REASONING — a narrow, REVIEW-only placement reasoner (read-only, name-free,
harness-only).

The exact-box engine places a bore when the logged span matches a printed callout box by footage + endpoints.
This reasoner covers the DIFFERENT case: the logged span does NOT exactly match a printed callout box, but a
source-supported STRUCTURE / STATION DATUM printed on the print-ref-resolved sheet proves the correct drill run.
It produces a REVIEW candidate ONLY — never AUTO, never final placement, never a status promotion.

DOCTRINE (Patrick):
  * The TALLY decides extent            — the run length is the bore log's own footage, never re-measured.
  * The PLAN supplies shape             — geometry comes only from observer-exposed anchors, never invented.
  * The PRINT REF locates the sheet     — the construction sheet is the bore log's print reference (Slice 2/3).
  * Engineering-sheet vs PDF-page identity stay SEPARATE (carried as two fields, never conflated).
  * No source evidence -> no redline.   No wrong redlines.   REVIEW only.

A candidate is produced ONLY when ALL hold (else a NAMED refusal, never a guess):
  1. the span is a source-confirmed station-series span with footage consistent with its station delta;
  2. the bore log carries a print/sheet reference;
  3. that reference resolved to an engineering sheet + PDF page (Slice-3 ``sheet_context``; an unresolved /
     multi-sheet ref passes the Slice-3 refusal straight through — the reasoner never runs on a guessed page);
  4. a printed DATUM WITNESS exists on that resolved sheet for one endpoint — a structure symbol (HH / terminal /
     splice), a leader-tipped anchor, a drawn callout/run terminus, or a printed matchline station equation;
  5. it matches ONE span endpoint (resolved AT that endpoint's station);
  6. exactly one run is bounded from the datum + the logged footage (the datum ANCHORS, the tally EXTENDS);
  7. the OTHER endpoint independently lands on source evidence (same witness set);
  8. if the anchor endpoint resolves to >= 2 plausible datums -> ``AMBIGUOUS_STRUCTURE_DATUM`` (never choose);
  9. if neither endpoint has a datum witness -> ``NO_PRINTED_DATUM_WITNESS``.

It is a pure composition of the shipped read-only ``extract/`` observers (``plan_view_anchor_resolver`` for the
per-station anchor, ``matchline_join.see_sheet_crossings`` for printed station equations); it imports NOTHING from
render / placement / api / store / contracts / match / web, draws nothing, mutates nothing, and does not touch the
exact-box engine, ``select_dialect``, ``_cap_review``, AUTO, thresholds, recognized replay, manual anchor, the
uploaded-corpus render, or the readiness sheet derivation. It is NOT wired into the live product path here — it is
a standalone capability, like ``endpoint_binding`` / ``route_verification`` were before composition.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from truelinev2.stations import feet_to_station, parse_station

# --- the confirmed-span status this reasoner accepts (kept in sync with span_extractor via a test) -------- #
_SPAN_ROW_CONFIRMED = "SPAN_ROW_CONFIRMED"

# --- Slice-3 sheet_context vocabulary (test-locked equal to product_readiness_bridge; defined locally so this
#     module stays a pure extract/ + stations composition and never imports the bridge/spine). -------------- #
SHEET_SOURCE_SHEET_REF = "BORE_LOG_SHEET_REF_TITLE_BLOCK_RESOLVED"
SHEET_REF_UNRESOLVED = "SHEET_REF_UNRESOLVED"
MULTI_SHEET_REFS_UNSUPPORTED = "MULTI_SHEET_REFS_UNSUPPORTED"

# --- result statuses ------------------------------------------------------------------------------------- #
STRUCTURE_DATUM_REVIEW_CANDIDATE = "STRUCTURE_DATUM_REVIEW_CANDIDATE"    # the single positive
NO_CONFIRMED_SPAN = "NO_CONFIRMED_SPAN"                                  # cond. 1
NO_PRINT_SHEET_REF = "NO_PRINT_SHEET_REF"                                # cond. 2
NO_PRINTED_DATUM_WITNESS = "NO_PRINTED_DATUM_WITNESS"                    # cond. 9
AMBIGUOUS_STRUCTURE_DATUM = "AMBIGUOUS_STRUCTURE_DATUM"                  # cond. 8
UNSUPPORTED_FAR_ENDPOINT = "UNSUPPORTED_FAR_ENDPOINT"                    # cond. 7
# (SHEET_REF_UNRESOLVED / MULTI_SHEET_REFS_UNSUPPORTED are also emitted, passed through from Slice 3 — cond. 3.)

# --- datum-witness KINDS (the acceptable printed evidence classes of condition 4) ------------------------- #
STRUCTURE_SYMBOL = "STRUCTURE_SYMBOL"                    # HH / terminal / splice / flower-pot symbol at the sta
LEADER_TIP = "LEADER_TIP"                               # a unique leader off the station label, no symbol at tip
CALLOUT_RUN_ENDPOINT = "CALLOUT_RUN_ENDPOINT"           # a drawn callout / run terminus at the station
MATCHLINE_STATION_EQUATION = "MATCHLINE_STATION_EQUATION"   # a printed matchline "SEE SHEET" station equation

# anchor-resolver method -> datum kind (the resolver's own vocabulary; unknown methods stay a generic endpoint).
_KIND_BY_METHOD = {
    "LEADER_TRACED_SYMBOL": STRUCTURE_SYMBOL,
    "PROXIMITY_SYMBOL": STRUCTURE_SYMBOL,
    "LEADER_TIP": LEADER_TIP,
    "ROUTE_TERMINUS": CALLOUT_RUN_ENDPOINT,
}
# datum strength for ANCHOR selection when both endpoints carry a witness (the stronger identity anchors the
# run; a tie prefers the start). Never a placement tiebreak — only which endpoint the tally extends FROM.
_STRENGTH = {STRUCTURE_SYMBOL: 3, CALLOUT_RUN_ENDPOINT: 2, LEADER_TIP: 2, MATCHLINE_STATION_EQUATION: 1}

# REVIEW-only tolerances (this cold-lane reasoner's OWN constants — never the engine's; it imports no match/):
_FOOTAGE_CONSISTENCY_TOL_FT = 2.0       # bore log's own footage vs its station delta (internal consistency)
_MATCHLINE_STATION_TOL_FT = 2.0         # a printed equation station "matches" an endpoint within this band

_REVIEW_NOTICE = ("REVIEW candidate — human-reviewable; NOT AUTO, NOT final placement, NOT a status promotion")


@dataclass(frozen=True)
class _Witness:
    """What the resolved sheet prints at ONE endpoint station. ``supported`` is True for any accepted datum kind;
    ``ambiguous`` is True when >= 2 plausible anchors tie (the resolver's AMBIGUOUS_ANCHOR)."""
    kind: Optional[str]
    supported: bool
    ambiguous: bool
    xy: Optional[Tuple[float, float]]
    method: Optional[str]
    status: str


@dataclass(frozen=True)
class StructureDatumReasoning:
    """Outcome of one structure-datum reasoning attempt. Exactly one candidate when READY; None on any refusal.
    ``performs_auto`` / ``performs_placement`` / ``promotes_status`` are ALWAYS False (REVIEW evidence only)."""
    status: str
    ready: bool
    reason: str
    candidate: Optional[Dict[str, Any]]
    evidence_chain: Tuple[str, ...]
    engineering_sheet: Optional[int]
    pdf_page: Optional[int]
    is_review_candidate: bool = True
    performs_auto: bool = False
    performs_placement: bool = False
    promotes_status: bool = False
    detail: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"status": self.status, "ready": self.ready, "reason": self.reason,
                "candidate": dict(self.candidate) if self.candidate else None,
                "evidence_chain": list(self.evidence_chain),
                "engineering_sheet": self.engineering_sheet, "pdf_page": self.pdf_page,
                "is_review_candidate": self.is_review_candidate, "performs_auto": self.performs_auto,
                "performs_placement": self.performs_placement, "promotes_status": self.promotes_status,
                "detail": dict(self.detail)}


def _refuse(status: str, reason: str, *, eng_sheet=None, pdf_page=None, chain=(), detail=None
            ) -> StructureDatumReasoning:
    return StructureDatumReasoning(status=status, ready=False, reason=reason, candidate=None,
                                   evidence_chain=tuple(chain), engineering_sheet=eng_sheet, pdf_page=pdf_page,
                                   detail=dict(detail or {}))


def _matchline_stations(plan_path: str, sheet: int, offset: int,
                        partner_sheets: Sequence[int]) -> List[float]:
    """Printed matchline "SEE SHEET" boundary-station feet on the RESOLVED page (offset), for each referenced
    partner sheet — reuses ``matchline_join.see_sheet_crossings`` verbatim, never re-parsing the grammar."""
    from truelinev2.extract.matchline_join import see_sheet_crossings
    from truelinev2.ingest.pdf import PlanPdf
    plan = PlanPdf(str(plan_path))
    try:
        lines = plan.lines(int(sheet), int(offset))
    finally:
        plan.close()
    out: List[float] = []
    for partner in partner_sheets:
        for tup in see_sheet_crossings(lines, int(partner), "MATCH"):
            for tok in tup:
                ft = parse_station(tok)
                if ft is not None:
                    out.append(round(ft, 2))
    return out


def _witness_at(plan_path: str, sheet: int, station_ft: float, offset: int,
                matchline_stations: Sequence[float]) -> _Witness:
    """Resolve the printed datum witness at one endpoint STATION on the resolved sheet. Reuses the read-only
    G-a' anchor resolver (structure symbol / leader tip / route terminus) FIRST; falls back to a printed
    matchline station equation. Invents no coordinate — any (x, y) is exactly what the observer exposed."""
    from truelinev2.extract.plan_view_anchor_resolver import (
        AMBIGUOUS_ANCHOR,
        resolve_plan_view_anchor_for_path,
    )
    ar = resolve_plan_view_anchor_for_path(str(plan_path), int(sheet), float(station_ft), offset=int(offset))
    if ar.status == AMBIGUOUS_ANCHOR:
        return _Witness(kind=None, supported=False, ambiguous=True, xy=None, method=ar.method, status=ar.status)
    if ar.resolved:
        kind = _KIND_BY_METHOD.get(ar.method, CALLOUT_RUN_ENDPOINT)
        xy = (float(ar.x), float(ar.y)) if ar.x is not None and ar.y is not None else None
        return _Witness(kind=kind, supported=True, ambiguous=False, xy=xy, method=ar.method, status=ar.status)
    if any(abs(s - float(station_ft)) <= _MATCHLINE_STATION_TOL_FT for s in matchline_stations):
        return _Witness(kind=MATCHLINE_STATION_EQUATION, supported=True, ambiguous=False, xy=None,
                        method="MATCHLINE_SEE_SHEET", status=MATCHLINE_STATION_EQUATION)
    return _Witness(kind=None, supported=False, ambiguous=False, xy=None, method=None, status=ar.status)


def reason_structure_datum(span, sheet_context: Dict[str, Any], plan_path: str) -> StructureDatumReasoning:
    """Attempt a structure-datum REVIEW candidate for one source-confirmed span on its print-ref-resolved sheet.

    ``span`` is a ``span_extractor.SpanRow`` (carries start/end stations, footage, sheet_refs, print_raw).
    ``sheet_context`` is the Slice-3 dict {engineering_sheet, pdf_page, sheet_offset, source, refusal, ...}.
    Returns a ``StructureDatumReasoning`` — READY with exactly one candidate, or a NAMED refusal. Read-only:
    draws nothing, mutates nothing, promotes nothing."""
    # --- condition 1: a source-confirmed station-series span with internally-consistent footage --------------
    if getattr(span, "status", None) != _SPAN_ROW_CONFIRMED:
        return _refuse(NO_CONFIRMED_SPAN, "the span is not source-confirmed — nothing to anchor")
    start_ft = parse_station(span.start_station)
    end_ft = parse_station(span.end_station)
    footage = span.footage
    if start_ft is None or end_ft is None:
        return _refuse(NO_CONFIRMED_SPAN, "the span's start/end station is not parseable")
    lo_ft, hi_ft = (start_ft, end_ft) if start_ft <= end_ft else (end_ft, start_ft)
    if footage is None or footage <= 0:
        return _refuse(NO_CONFIRMED_SPAN, "the span carries no positive logged footage (the tally that sets extent)")
    if abs((hi_ft - lo_ft) - float(footage)) > _FOOTAGE_CONSISTENCY_TOL_FT:
        return _refuse(NO_CONFIRMED_SPAN,
                       "the logged footage %.1f ft disagrees with the station span %.1f ft — the source's own "
                       "numbers are inconsistent; refusing rather than choosing an extent"
                       % (float(footage), hi_ft - lo_ft))

    # --- condition 2: a print/sheet reference is present -----------------------------------------------------
    if not getattr(span, "sheet_refs", None):
        return _refuse(NO_PRINT_SHEET_REF,
                       "the bore log carries no print/sheet reference — the construction sheet cannot be located")

    # --- condition 3: the reference resolved to an engineering sheet + PDF page (else pass Slice-3 through) ---
    refusal = sheet_context.get("refusal")
    if refusal in (SHEET_REF_UNRESOLVED, MULTI_SHEET_REFS_UNSUPPORTED):
        return _refuse(refusal, sheet_context.get("reason")
                       or "the print/sheet reference did not resolve to a single construction sheet")
    eng_sheet = sheet_context.get("engineering_sheet")
    pdf_page = sheet_context.get("pdf_page")
    offset = sheet_context.get("sheet_offset")
    if (sheet_context.get("source") != SHEET_SOURCE_SHEET_REF or eng_sheet is None or pdf_page is None
            or offset is None):
        return _refuse(SHEET_REF_UNRESOLVED,
                       "the print/sheet reference did not resolve to an engineering sheet + PDF page via the "
                       "title-block index — refusing rather than guessing a page")
    eng_sheet, pdf_page, offset = int(eng_sheet), int(pdf_page), int(offset)

    chain = [
        "confirmed station-series span %s -> %s (%.1f ft tally)" % (
            feet_to_station(lo_ft), feet_to_station(hi_ft), float(footage)),
        "print/sheet ref %s -> engineering sheet %d -> PDF page %d (title-block resolved; identities separate)"
        % (list(span.sheet_refs), eng_sheet, pdf_page),
    ]

    # --- conditions 4-5: printed datum witnesses at BOTH endpoints on the RESOLVED page ---------------------
    partners = [int(s) for s in span.sheet_refs if int(s) != eng_sheet]
    ml = _matchline_stations(plan_path, eng_sheet, offset, partners)
    w_lo = _witness_at(plan_path, eng_sheet, lo_ft, offset, ml)
    w_hi = _witness_at(plan_path, eng_sheet, hi_ft, offset, ml)

    # --- condition 8: an endpoint resolving to >= 2 plausible datums is ambiguous — never choose -------------
    if w_lo.ambiguous or w_hi.ambiguous:
        which = feet_to_station(lo_ft if w_lo.ambiguous else hi_ft)
        return _refuse(AMBIGUOUS_STRUCTURE_DATUM,
                       "station %s resolves to more than one plausible printed datum on sheet %d (PDF page %d); "
                       "the next step is a human pick — never a guess" % (which, eng_sheet, pdf_page),
                       eng_sheet=eng_sheet, pdf_page=pdf_page, chain=chain)

    # --- condition 9: neither endpoint carries a printed datum witness --------------------------------------
    endpoints = [("start" if lo_ft == start_ft else "end", lo_ft, w_lo),
                 ("end" if lo_ft == start_ft else "start", hi_ft, w_hi)]
    supported = [(name, ft, w) for (name, ft, w) in endpoints if w.supported]
    if not supported:
        return _refuse(NO_PRINTED_DATUM_WITNESS,
                       "neither endpoint (%s / %s) binds to a printed structure/callout/matchline datum on "
                       "sheet %d (PDF page %d); no source datum -> no redline"
                       % (feet_to_station(lo_ft), feet_to_station(hi_ft), eng_sheet, pdf_page),
                       eng_sheet=eng_sheet, pdf_page=pdf_page, chain=chain)

    # --- condition 6: bound exactly one run — the strongest datum ANCHORS, the tally EXTENDS to the far end --
    anchor_name, anchor_ft, anchor_w = max(
        supported, key=lambda t: (_STRENGTH.get(t[2].kind, 0), t[0] == "start"))
    far_name, far_ft, far_w = next((e for e in endpoints if e[0] != anchor_name))
    chain.append("datum witness at the %s endpoint %s: %s (method %s)%s"
                 % (anchor_name, feet_to_station(anchor_ft), anchor_w.kind, anchor_w.method,
                    "" if anchor_w.xy is None else " at (%.1f, %.1f)" % anchor_w.xy))
    chain.append("run bounded from the datum + the %.1f ft tally: %s -> %s (extent from footage, not re-measured)"
                 % (float(footage), feet_to_station(lo_ft), feet_to_station(hi_ft)))

    # --- condition 7: the OTHER endpoint must independently land on source evidence -------------------------
    if not far_w.supported:
        return _refuse(UNSUPPORTED_FAR_ENDPOINT,
                       "the %s endpoint is datum-anchored, but the other endpoint %s lands on no source evidence "
                       "on sheet %d (PDF page %d) — refusing rather than drawing an unsupported far end"
                       % (anchor_name, feet_to_station(far_ft), eng_sheet, pdf_page),
                       eng_sheet=eng_sheet, pdf_page=pdf_page, chain=chain)
    chain.append("far endpoint %s lands on source evidence: %s (method %s)%s"
                 % (feet_to_station(far_ft), far_w.kind, far_w.method,
                    "" if far_w.xy is None else " at (%.1f, %.1f)" % far_w.xy))
    chain.append(_REVIEW_NOTICE)

    candidate = {
        "anchor_endpoint": anchor_name, "anchor_station": feet_to_station(anchor_ft),
        "anchor_datum_kind": anchor_w.kind, "anchor_method": anchor_w.method, "anchor_xy": list(anchor_w.xy)
        if anchor_w.xy else None,
        "far_endpoint": far_name, "far_station": feet_to_station(far_ft),
        "far_evidence_kind": far_w.kind, "far_method": far_w.method, "far_xy": list(far_w.xy)
        if far_w.xy else None,
        "run_lo_ft": lo_ft, "run_hi_ft": hi_ft, "footage_ft": float(footage),
        "engineering_sheet": eng_sheet, "pdf_page": pdf_page,          # SEPARATE axes, never conflated
        "start_station": span.start_station, "end_station": span.end_station,
    }
    return StructureDatumReasoning(
        status=STRUCTURE_DATUM_REVIEW_CANDIDATE, ready=True,
        reason="structure/station datum at the %s endpoint + the %.1f ft tally bound exactly one run; the far "
               "endpoint is source-supported" % (anchor_name, float(footage)),
        candidate=candidate, evidence_chain=tuple(chain), engineering_sheet=eng_sheet, pdf_page=pdf_page,
        detail={"far_endpoint_supported": True})


def main(argv: Optional[Sequence[str]] = None) -> int:  # pragma: no cover - diagnostic CLI parity
    """Harness diagnostic CLI: read a JSON {span, sheet_context, plan_path} and print the reasoning. Draws /
    places / promotes nothing. ``python -m truelinev2.harness.structure_datum_reasoning <input.json>``."""
    import json
    import sys

    from truelinev2.harness.span_extractor import SpanRow
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        sys.stderr.write("usage: structure_datum_reasoning <input.json>\n")
        return 2
    raw = json.loads(open(args[0], encoding="utf-8").read())
    s = raw["span"]
    span = SpanRow(span_id=s.get("span_id", "span-001"), source_file=s.get("source_file", ""),
                   source_page=s.get("source_page"), source_kind=s.get("source_kind", ""),
                   start_station=s["start_station"], end_station=s["end_station"], footage=s.get("footage"),
                   start_structure=s.get("start_structure"), end_structure=s.get("end_structure"),
                   status=s.get("status", _SPAN_ROW_CONFIRMED), confidence=s.get("confidence", "HIGH"),
                   citation=s.get("citation", ""), bbox=None, detail=dict(s.get("detail", {})),
                   print_raw=s.get("print_raw"), sheet_refs=tuple(s.get("sheet_refs", ())))
    result = reason_structure_datum(span, dict(raw["sheet_context"]), raw["plan_path"])
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0 if result.ready else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
