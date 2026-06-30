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

from truelinev2.extract.structure_anchor import BOUND, bind_end_structure_note
from truelinev2.extract.terminus_evidence import (
    ABSENT,
    AMBIGUOUS_END_STRUCTURE,
    AMBIGUOUS_START_STRUCTURE,
    BORE_LOG_ROW,
    BORE_LOG_ROW_PARSED,
    BoreTerminusEvidence,
    NO_BORE_LOG_STATION,
    NO_PRINTED_END_STRUCTURE,
    NO_PRINTED_START_STRUCTURE,
    PRINTED_PLAN_TEXT,
    PRINTED_STRUCTURE_LABEL,
    TerminusEvidence,
)
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.stations import feet_to_station


def _sheets_for(bore) -> List[int]:
    return sorted({int(s) for s in (getattr(bore, "sheet_refs", None) or [])}) or [1]


def _bind_endpoint(plan: PlanPdf, station_ft: Optional[float], which: str, sheets: List[int]) -> TerminusEvidence:
    """Bind one endpoint from a printed structure note (source-bound) or fall back to the bore-log row value
    with a named missing-evidence blocker. Never infers from geometry."""
    no_struct = NO_PRINTED_START_STRUCTURE if which == "START" else NO_PRINTED_END_STRUCTURE
    ambiguous = AMBIGUOUS_START_STRUCTURE if which == "START" else AMBIGUOUS_END_STRUCTURE

    if station_ft is None:
        return TerminusEvidence(
            which=which, source_type=ABSENT, source_bound=False, blocker=NO_BORE_LOG_STATION,
            provenance=BORE_LOG_ROW_PARSED,
            pedigree="the bore-log row carries no %s station; nothing to bind" % which.lower())

    station_str = feet_to_station(station_ft)
    max_candidates = 0
    for sheet in sheets:
        b = bind_end_structure_note(station_ft, plan.lines(sheet, 0))
        max_candidates = max(max_candidates, getattr(b, "candidates", 0) or 0)
        if b.result == BOUND:
            return TerminusEvidence(
                which=which, source_type=PRINTED_STRUCTURE_LABEL, source_bound=True,
                station_ft=station_ft, station_str=station_str, sheet=sheet,
                source_text=b.note_line, structure_label=b.structure_label,
                provenance=PRINTED_PLAN_TEXT, confidence=1.0, blocker=None,
                pedigree="sheet %d: printed structure note %r binds %s at STA %s"
                         % (sheet, b.note_line, which.lower(), station_str))

    # No printed structure note bound: the station VALUE is source-backed (bore-log row), but the per-bore
    # printed endpoint identity is missing -> NOT source-bound for AUTO; report exactly which proof is absent.
    blocker = ambiguous if max_candidates >= 2 else no_struct
    detail = ("%d structure notes share STA %s (ambiguous)" % (max_candidates, station_str)
              if max_candidates >= 2 else
              "no printed structure note 'STA %s <structure>' on sheet(s) %s" % (station_str, sheets))
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
        start = _bind_endpoint(plan, getattr(bore, "station_start_ft", None), "START", sheets)
        end = _bind_endpoint(plan, getattr(bore, "station_end_ft", None), "END", sheets)
        return BoreTerminusEvidence(bore_label=getattr(bore, "bore_id", None), start=start, end=end)
    finally:
        plan.close()
