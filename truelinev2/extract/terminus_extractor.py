"""Read-only per-bore TERMINUS EXTRACTOR prototype (G2 — OBSERVER-ONLY).

Given an uploaded plan + bore-log, emit source-backed terminus evidence for a bore's START and END. It REUSES
existing source readers (``load_borelog`` for the bore-log row, ``PlanPdf.lines`` + ``structure_anchor.
bind_end_structure_note`` for printed structure notes) and emits ONLY evidence / provenance:

  * if a printed structure note ``STA <station> <structure>`` sits at the endpoint station -> SOURCE-BOUND
    (PRINTED_STRUCTURE_LABEL), with the verbatim note + structure label.
  * else the station value is known from the bore-log row (BORE_LOG_ROW), but the per-bore printed identity is
    MISSING -> source_bound=False with a named blocker (NO_PRINTED_*_STRUCTURE / AMBIGUOUS_*_STRUCTURE).

This module is DELIBERATELY NOT wired into ``run_product_redline`` / the engine. It promotes nothing, alters
no placement or status, writes no redline, touches no renderer, and changes the deterministic frontier in no
way — it is a pure read-only observer the harness/tests drive directly. Printed-callout / matchline / KMZ /
reviewed-bore-log-status readers are named reuse hooks for later gates; this prototype binds from the printed
structure note + the bore-log row only. Name-free.
"""
from __future__ import annotations

from typing import List, Optional

from truelinev2.extract.callout_anchor import (
    CALLOUT_AMBIGUOUS,
    CALLOUT_BOUND,
    anchored_disagreement,
    bind_endpoint_callout,
    span_callouts,
)
from truelinev2.extract.matchline_anchor import (
    MATCHLINE_AMBIGUOUS,
    MATCHLINE_BOUND,
    bilateral_boundaries,
    bind_endpoint_matchline,
)
from truelinev2.extract.structure_anchor import BOUND, bind_end_structure_note
from truelinev2.extract.terminus_evidence import (
    ABSENT,
    AMBIGUOUS_END_STRUCTURE,
    AMBIGUOUS_START_STRUCTURE,
    BORE_LOG_ROW,
    BORE_LOG_ROW_PARSED,
    BoreTerminusEvidence,
    CONFLICTING_END_TERMINUS,
    CONFLICTING_START_TERMINUS,
    MATCHLINE_BOUNDARY_STATION,
    NO_BORE_LOG_STATION,
    NO_PRINTED_END_STRUCTURE,
    NO_PRINTED_START_STRUCTURE,
    PRINTED_PLAN_TEXT,
    PRINTED_STA_CALLOUT,
    PRINTED_STRUCTURE_LABEL,
    TerminusEvidence,
)
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.stations import feet_to_station


def _sheets_for(bore) -> List[int]:
    return sorted({int(s) for s in (getattr(bore, "sheet_refs", None) or [])}) or [1]


def _bind_endpoint(plan: PlanPdf, station_ft: Optional[float], which: str, sheets: List[int],
                   other_ft: Optional[float]) -> TerminusEvidence:
    """Bind one endpoint by PRINTED source identity, in priority order: a CONFLICT between printed sources
    (never silently preferred) -> a printed structure note (PRINTED_STRUCTURE_LABEL) -> a printed station-range
    callout (PRINTED_STA_CALLOUT) -> else the bore-log row value with a named missing/ambiguous blocker. The
    station VALUE is always read from source; nothing is inferred from geometry."""
    no_struct = NO_PRINTED_START_STRUCTURE if which == "START" else NO_PRINTED_END_STRUCTURE
    ambiguous = AMBIGUOUS_START_STRUCTURE if which == "START" else AMBIGUOUS_END_STRUCTURE
    conflict = CONFLICTING_START_TERMINUS if which == "START" else CONFLICTING_END_TERMINUS

    if station_ft is None:
        return TerminusEvidence(
            which=which, source_type=ABSENT, source_bound=False, blocker=NO_BORE_LOG_STATION,
            provenance=BORE_LOG_ROW_PARSED,
            pedigree="the bore-log row carries no %s station; nothing to bind" % which.lower())

    station_str = feet_to_station(station_ft)
    other_str = feet_to_station(other_ft) if other_ft is not None else None

    # Gather printed evidence across the bore's referenced sheets: structure notes + station-range callouts +
    # bilateral matchline boundary equations.
    struct_bound = None                                       # (sheet, EndNoteBinding) when a note binds
    max_struct_candidates = 0
    spans = []                                                # [(sheet, SpanCallout)]
    sheet_lines = {}
    for sheet in sheets:
        lines = plan.lines(sheet, 0)
        sheet_lines[sheet] = lines
        b = bind_end_structure_note(station_ft, lines)
        max_struct_candidates = max(max_struct_candidates, getattr(b, "candidates", 0) or 0)
        if b.result == BOUND and struct_bound is None:
            struct_bound = (sheet, b)
        spans.extend((sheet, sc) for sc in span_callouts(lines))

    flat_spans = [sc for _sheet, sc in spans]
    cb = bind_endpoint_callout(which, station_str, flat_spans)

    lo_ft = min(station_ft, other_ft) if other_ft is not None else station_ft
    hi_ft = max(station_ft, other_ft) if other_ft is not None else station_ft
    boundaries = bilateral_boundaries(sheet_lines, sheets, lo_ft, hi_ft)
    mb = bind_endpoint_matchline(station_str, boundaries)

    # (1) CONFLICT: a printed source binds this endpoint (structure note OR bilateral matchline) AND a printed
    # span callout anchored to the bore's other endpoint brackets it to a DIFFERENT station -> two printed
    # sources disagree. Never silently chosen between.
    a_printed_binds = struct_bound is not None or mb.result == MATCHLINE_BOUND
    if a_printed_binds and other_str is not None:
        disagree = anchored_disagreement(which, station_str, other_str, flat_spans)
        if disagree is not None:
            return TerminusEvidence(
                which=which, source_type=BORE_LOG_ROW, source_bound=False,
                station_ft=station_ft, station_str=station_str,
                sheet=(struct_bound[0] if struct_bound else sheets[0]),
                source_text=None, structure_label=None, provenance=BORE_LOG_ROW_PARSED,
                confidence=None, blocker=conflict,
                pedigree="a printed source binds %s at STA %s but a printed span callout brackets the bore to "
                         "STA %s -> source conflict; never chosen between"
                         % (which.lower(), station_str, disagree))

    # (2) Printed structure note (PRINTED_STRUCTURE_LABEL).
    if struct_bound is not None:
        sheet, b = struct_bound
        return TerminusEvidence(
            which=which, source_type=PRINTED_STRUCTURE_LABEL, source_bound=True,
            station_ft=station_ft, station_str=station_str, sheet=sheet,
            source_text=b.note_line, structure_label=b.structure_label,
            provenance=PRINTED_PLAN_TEXT, confidence=1.0, blocker=None,
            pedigree="sheet %d: printed structure note %r binds %s at STA %s"
                     % (sheet, b.note_line, which.lower(), station_str))

    # (3) Printed BILATERAL matchline boundary station (MATCHLINE_BOUNDARY_STATION) — both adjacent referenced
    # sheets print the same crossing at this endpoint; unilateral / sheet-mismatched matchlines never reach here.
    if mb.result == MATCHLINE_BOUND:
        sheet = mb.pair[0] if mb.pair else sheets[0]
        return TerminusEvidence(
            which=which, source_type=MATCHLINE_BOUNDARY_STATION, source_bound=True,
            station_ft=station_ft, station_str=station_str, sheet=sheet,
            source_text=mb.text, structure_label=None,
            provenance=PRINTED_PLAN_TEXT, confidence=1.0, blocker=None,
            pedigree="sheets %d+%d: bilateral printed matchline boundary %r binds %s at STA %s"
                     % (mb.pair[0], mb.pair[1], mb.text, which.lower(), station_str))

    # (4) Printed station-range callout (PRINTED_STA_CALLOUT) — exact station identity, unique.
    if cb.result == CALLOUT_BOUND:
        sheet = next((sh for sh, sc in spans if sc.text == cb.text), sheets[0])
        return TerminusEvidence(
            which=which, source_type=PRINTED_STA_CALLOUT, source_bound=True,
            station_ft=station_ft, station_str=station_str, sheet=sheet,
            source_text=cb.text, structure_label=None,
            provenance=PRINTED_PLAN_TEXT, confidence=1.0, blocker=None,
            pedigree="sheet %d: printed station callout %r brackets %s at STA %s"
                     % (sheet, cb.text, which.lower(), station_str))

    # (5) No printed proof bound: the station VALUE is the bore-log row; report the precise missing/ambiguous
    # reason (a structure-note / callout / matchline ambiguity is reported as the endpoint-ambiguous blocker).
    if max_struct_candidates >= 2 or cb.result == CALLOUT_AMBIGUOUS or mb.result == MATCHLINE_AMBIGUOUS:
        blocker = ambiguous
        n = max(max_struct_candidates, cb.candidates, mb.candidates)
        detail = "%d printed structure notes / station callouts / matchlines share STA %s (ambiguous)" \
                 % (n, station_str)
    else:
        blocker = no_struct
        detail = ("no printed structure note, station-range callout, or bilateral matchline boundary binds "
                  "STA %s on sheet(s) %s" % (station_str, sheets))
    return TerminusEvidence(
        which=which, source_type=BORE_LOG_ROW, source_bound=False,
        station_ft=station_ft, station_str=station_str, sheet=sheets[0],
        source_text=None, structure_label=None, provenance=BORE_LOG_ROW_PARSED,
        confidence=None, blocker=blocker,
        pedigree="bore-log station %s known; %s -> not printed-proven" % (station_str, detail))


def extract_termini(plan_path, borelog_path) -> BoreTerminusEvidence:
    """Read the uploaded plan + bore-log and emit source-backed terminus evidence for the bore. Read-only:
    opens/closes the plan, runs no engine, renders nothing, returns evidence only."""
    bore = load_borelog(str(borelog_path))
    plan = PlanPdf(str(plan_path))
    try:
        sheets = _sheets_for(bore)
        start_ft = getattr(bore, "station_start_ft", None)
        end_ft = getattr(bore, "station_end_ft", None)
        start = _bind_endpoint(plan, start_ft, "START", sheets, end_ft)
        end = _bind_endpoint(plan, end_ft, "END", sheets, start_ft)
        return BoreTerminusEvidence(bore_label=getattr(bore, "bore_id", None), start=start, end=end)
    finally:
        plan.close()
