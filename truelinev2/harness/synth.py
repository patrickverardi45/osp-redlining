"""Synthetic, name-free cold-package fixture generators.

Builds self-contained PDF + xlsx inputs (the same fitz/openpyxl pattern the product proof seed uses) that
exercise distinct engine decisions WITHOUT any real customer/project/location content. These plans carry NO
named-dialect text ('STA <a> TO STA <b>' / 'DIR(ECTIONAL) BORE') so select_dialect returns None and the
engine routes through the name-free generic-geometry lane (or abstains) — exactly the cold-package path.

Coordinate scheme (shared): station ticks at x=120..720 map to stations 1000..1600 (station_at(x) ~= x+880),
so the bore-log span 11+75..13+25 sits at x 295..445. A tight red run over that x-range is the bore; a
full-sheet line is a survey baseline the bore-aware selector must NOT mistake for the bore.

These generators write fixture directories under a gitignored fixtures root; they are pure data builders and
run no engine.
"""
from __future__ import annotations

import io
import json
import shutil
from pathlib import Path

import fitz
import openpyxl

from truelinev2.harness.fixtures import STATUS_ABSTAIN, STATUS_REVIEW

# Shared bore-log span (feet) used by the fixtures whose plan geometry is calibrated to it.
_BORE_START = "11+75"
_BORE_END = "13+25"


def _new_plan():
    doc = fitz.open()
    page = doc.new_page(width=792, height=612)            # landscape, plan-like
    return doc, page


def _draw_axis(page) -> None:
    """Station ticks + labels (x=120..720 -> 10+00..16+00). No named-dialect text."""
    for ft in range(1000, 1601, 100):
        x = 120 + (ft - 1000) / 100 * 100
        page.draw_line((x, 400), (x, 412), color=(0, 0, 0), width=0.8)
        page.insert_text((x - 12, 426), "%d+%02d" % (ft // 100, ft % 100), fontsize=8)


def _save(doc) -> bytes:
    out = io.BytesIO()
    doc.save(out)
    doc.close()
    return out.getvalue()


def plan_tight_red_run() -> bytes:
    """Axis + survey baseline + two existing utilities + a single PROPOSED bore drawn red, tightly spanning
    the bore-log range. The bore-aware generic selector should pick the red run and clip to the span ->
    REVIEW (capped; generic never AUTO)."""
    doc, page = _new_plan()
    page.insert_text((60, 60), "PLAN & PROFILE  -  ALIGNMENT 10+00 thru 16+00", fontsize=11)
    for gx in range(120, 721, 50):
        page.draw_line((gx, 300), (gx, 360), color=(0.8, 0.8, 0.8), width=0.4)
    _draw_axis(page)
    page.draw_line((120, 400), (720, 400), color=(0, 0, 0), width=0.7)            # full-sheet baseline
    page.draw_line((120, 372), (720, 372), color=(0.2, 0.5, 0.9), width=0.8)      # blue utility
    page.draw_line((120, 388), (720, 388), color=(0.1, 0.6, 0.2), width=0.8)      # green utility
    page.draw_line((295, 384), (445, 384), color=(1, 0, 0), width=1.8)            # the PROPOSED bore (red)
    return _save(doc)


def plan_ambiguous_runs() -> bytes:
    """Several co-linear runs over the SAME span (no single line is clearly the bore). The honest generic
    lane should still place a candidate but flag LOW / correction-recommended -> REVIEW path (never a
    confident AUTO)."""
    doc, page = _new_plan()
    page.insert_text((60, 60), "PLAN & PROFILE  -  ALIGNMENT 10+00 thru 16+00 (ambiguous)", fontsize=11)
    _draw_axis(page)
    page.draw_line((120, 400), (720, 400), color=(0, 0, 0), width=0.7)            # full-sheet baseline
    page.draw_line((295, 378), (445, 378), color=(0, 0, 0), width=1.4)            # rival A
    page.draw_line((295, 392), (445, 392), color=(1, 0, 0), width=1.6)            # rival B (red)
    page.draw_line((310, 406), (445, 406), color=(0, 0, 0), width=1.4)            # rival C
    return _save(doc)


def plan_axis_no_runs() -> bytes:
    """Axis ticks present but NO drawn run anywhere over the span (no bore line). The generic lane finds no
    drawable bore run -> ABSTAIN (honest 'nothing to place')."""
    doc, page = _new_plan()
    page.insert_text((60, 60), "PLAN & PROFILE  -  ALIGNMENT 10+00 thru 16+00 (no proposed work)", fontsize=11)
    for gx in range(120, 721, 50):
        page.draw_line((gx, 300), (gx, 360), color=(0.8, 0.8, 0.8), width=0.4)
    _draw_axis(page)
    return _save(doc)


def plan_blank() -> bytes:
    """A page with text only — no station ticks, no drawn geometry. No dialect, no axis -> ABSTAIN."""
    doc, page = _new_plan()
    page.insert_text((60, 60), "GENERAL NOTES SHEET", fontsize=12)
    page.insert_text((60, 90), "1. ALL WORK PER APPLICABLE STANDARDS.", fontsize=9)
    page.insert_text((60, 110), "2. CONTRACTOR TO VERIFY EXISTING CONDITIONS.", fontsize=9)
    return _save(doc)


def plan_partial_run(width_pt) -> bytes:
    """Axis + baseline + a red run covering only PART of the 150-pt bore span (x 295..295+width_pt). Below the
    ~50% coverage gate the generic lane should not place (ABSTAIN); 50-85% places only as a partial / low
    REVIEW."""
    doc, page = _new_plan()
    page.insert_text((60, 60), "PLAN & PROFILE  -  ALIGNMENT 10+00 thru 16+00 (partial run)", fontsize=11)
    _draw_axis(page)
    page.draw_line((120, 400), (720, 400), color=(0, 0, 0), width=0.7)
    page.draw_line((295, 384), (295 + width_pt, 384), color=(1, 0, 0), width=1.8)
    return _save(doc)


def plan_weak_axis() -> bytes:
    """Only TWO station ticks (below the 3-tick minimum to trust the axis) over a red run. The axis cannot be
    trusted -> ABSTAIN."""
    doc, page = _new_plan()
    page.insert_text((60, 60), "PLAN & PROFILE  -  (sparse stationing)", fontsize=11)
    for ft in (1000, 1600):
        x = 120 + (ft - 1000) / 100 * 100
        page.draw_line((x, 400), (x, 412), color=(0, 0, 0), width=0.8)
        page.insert_text((x - 12, 426), "%d+%02d" % (ft // 100, ft % 100), fontsize=8)
    page.draw_line((295, 384), (445, 384), color=(1, 0, 0), width=1.8)
    return _save(doc)


def plan_baseline_only() -> bytes:
    """Full axis but ONLY a full-sheet survey baseline (no tight proposed bore drawn). The honest answer is
    ABSTAIN: there is no bore to place, and the full-sheet baseline must NOT be mistaken for the bore. This is
    the over-placement probe (a placement on the baseline would be a FAIL)."""
    doc, page = _new_plan()
    page.insert_text((60, 60), "PLAN & PROFILE  -  (existing survey only)", fontsize=11)
    _draw_axis(page)
    page.draw_line((120, 400), (720, 400), color=(0, 0, 0), width=0.7)            # full-sheet baseline only
    return _save(doc)


def plan_speckle_no_run() -> bytes:
    """Axis + only short, widely-spaced red specks over the span (each below the minimum run length, gaps too
    wide to weld). No weldable run -> ABSTAIN."""
    doc, page = _new_plan()
    page.insert_text((60, 60), "PLAN & PROFILE  -  (no continuous proposed run)", fontsize=11)
    _draw_axis(page)
    for x in range(300, 441, 40):
        page.draw_line((x, 384), (x + 8, 384), color=(1, 0, 0), width=1.8)
    return _save(doc)


def plan_multi_sheet() -> bytes:
    """A TWO-page plan: each page carries the station axis + a red run over the span. The generic lane places a
    single clipped stroke on one sheet (it does not assemble cross-sheet legs yet) -> REVIEW. Probes multi-page
    handling."""
    doc = fitz.open()
    for label in ("SHEET 1", "SHEET 2"):
        page = doc.new_page(width=792, height=612)
        page.insert_text((60, 60), "PLAN & PROFILE  -  ALIGNMENT 10+00 thru 16+00 (%s)" % label, fontsize=11)
        _draw_axis(page)
        page.draw_line((120, 400), (720, 400), color=(0, 0, 0), width=0.7)
        page.draw_line((295, 384), (445, 384), color=(1, 0, 0), width=1.8)
    return _save(doc)


def plan_with_structure_notes(start_note: bool = True, end_note: bool = True) -> bytes:
    """A COLD plan (no named-dialect trigger): axis + a red bore run over the span 11+75..13+25, plus printed
    structure NOTE lines 'STA <station> <structure>' at the start and/or end station so the structure reader
    can bind those endpoints from source. The notes use generic industry structure terms and carry NO
    'STA a TO STA b' run-callout or 'DIR(ECTIONAL) BORE' text, so select_dialect stays None (generic cold lane)
    and the named dialects are never triggered."""
    doc, page = _new_plan()
    page.insert_text((60, 60), "PLAN & PROFILE  -  ALIGNMENT 10+00 thru 16+00", fontsize=11)
    _draw_axis(page)
    page.draw_line((120, 400), (720, 400), color=(0, 0, 0), width=0.7)            # full-sheet baseline
    page.draw_line((295, 384), (445, 384), color=(1, 0, 0), width=1.8)            # the bore (11+75..13+25)
    if start_note:
        page.insert_text((250, 360), "STA 11+75 INSTALLER HH", fontsize=8)        # printed START structure note
    if end_note:
        page.insert_text((450, 360), "STA 13+25 SPLICE", fontsize=8)              # printed END structure note
    return _save(doc)


def plan_ambiguous_end_notes() -> bytes:
    """COLD plan: axis + a red bore run over 11+75..13+25, a single printed START note, and TWO different
    printed structure notes at the SAME end station 13+25. The structure reader must NOT pick between two
    rival identities -> the END is reported AMBIGUOUS (source-bound=False, AMBIGUOUS_END_STRUCTURE), never a
    coin-flip bind. Name-free generic structure terms; no run-callout / 'DIR BORE' text."""
    doc, page = _new_plan()
    page.insert_text((60, 60), "PLAN & PROFILE  -  ALIGNMENT 10+00 thru 16+00", fontsize=11)
    _draw_axis(page)
    page.draw_line((120, 400), (720, 400), color=(0, 0, 0), width=0.7)
    page.draw_line((295, 384), (445, 384), color=(1, 0, 0), width=1.8)
    page.insert_text((250, 360), "STA 11+75 INSTALLER HH", fontsize=8)        # single START note -> bound
    page.insert_text((450, 360), "STA 13+25 SPLICE", fontsize=8)              # END rival A
    page.insert_text((450, 372), "STA 13+25 TERMINAL", fontsize=8)            # END rival B -> ambiguous
    return _save(doc)


def plan_offset_end_note() -> bytes:
    """COLD plan: axis + a red bore run over 11+75..13+25, a correct printed START note, and an END-area
    structure note that belongs to a DIFFERENT station (14+50, not the bore end 13+25). Identity binding is
    by EXACT station, never by proximity, so the END stays NOT source-bound (NO_PRINTED_END_STRUCTURE) — the
    nearby note is another station's. The negative case that guards against over-binding."""
    doc, page = _new_plan()
    page.insert_text((60, 60), "PLAN & PROFILE  -  ALIGNMENT 10+00 thru 16+00", fontsize=11)
    _draw_axis(page)
    page.draw_line((120, 400), (720, 400), color=(0, 0, 0), width=0.7)
    page.draw_line((295, 384), (445, 384), color=(1, 0, 0), width=1.8)
    page.insert_text((250, 360), "STA 11+75 INSTALLER HH", fontsize=8)        # correct START note -> bound
    page.insert_text((455, 360), "STA 14+50 SPLICE", fontsize=8)              # belongs to 14+50, not 13+25
    return _save(doc)


def plan_bare_station_callouts() -> bytes:
    """COLD plan: axis + a red bore run + bare station callouts 'STA 11+75' / 'STA 13+25' that carry NO
    structure keyword. A bare station callout is not a printed STRUCTURE identity, so BOTH endpoints stay NOT
    source-bound (NO_PRINTED_*_STRUCTURE) — the observer never upgrades a bare callout to a structure proof."""
    doc, page = _new_plan()
    page.insert_text((60, 60), "PLAN & PROFILE  -  ALIGNMENT 10+00 thru 16+00", fontsize=11)
    _draw_axis(page)
    page.draw_line((120, 400), (720, 400), color=(0, 0, 0), width=0.7)
    page.draw_line((295, 384), (445, 384), color=(1, 0, 0), width=1.8)
    page.insert_text((250, 360), "STA 11+75", fontsize=8)                     # bare callout, no structure word
    page.insert_text((450, 360), "STA 13+25", fontsize=8)                     # bare callout, no structure word
    return _save(doc)


def plan_multi_sheet_end_note() -> bytes:
    """COLD TWO-page plan: the START structure note + the bore run sit on sheet 1; the END structure note sits
    on sheet 2. With a bore-log that references both sheets, the observer binds the START on sheet 1 and the
    END on sheet 2 — exercising cross-sheet endpoint binding without inventing any boundary equation."""
    doc = fitz.open()
    p1 = doc.new_page(width=792, height=612)
    p1.insert_text((60, 60), "PLAN & PROFILE  -  ALIGNMENT 10+00 thru 16+00 (SHEET 1)", fontsize=11)
    _draw_axis(p1)
    p1.draw_line((120, 400), (720, 400), color=(0, 0, 0), width=0.7)
    p1.draw_line((295, 384), (445, 384), color=(1, 0, 0), width=1.8)
    p1.insert_text((250, 360), "STA 11+75 INSTALLER HH", fontsize=8)          # START note on sheet 1
    p2 = doc.new_page(width=792, height=612)
    p2.insert_text((60, 60), "PLAN & PROFILE  -  ALIGNMENT 10+00 thru 16+00 (SHEET 2)", fontsize=11)
    _draw_axis(p2)
    p2.insert_text((450, 360), "STA 13+25 SPLICE", fontsize=8)                # END note on sheet 2
    return _save(doc)


def _start_end_notes(page) -> None:
    page.insert_text((250, 360), "STA 11+75 INSTALLER HH", fontsize=8)          # printed START structure note
    page.insert_text((450, 360), "STA 13+25 SPLICE", fontsize=8)               # printed END structure note


# --- G4 preflight builders: each combines printed structure notes (both endpoints source-bound) with a
# DIFFERENT placement-geometry condition, so the future AUTO gate's geometry/sheet checks can be exercised
# against a both-bound terminus. All REVIEW today (the generic lane never auto-promotes). Name-free. --------- #
def plan_clean_bore_with_notes() -> bytes:
    """The LONE positive candidate shape: axis + a SINGLE tight red bore run over the span (no baseline, no
    rival utilities) + printed structure notes at BOTH endpoints. Near-perfect coverage, zero rivals, both
    endpoints source-bound — the only shape a future AUTO gate would accept. STILL REVIEW today."""
    doc, page = _new_plan()
    page.insert_text((60, 60), "PLAN & PROFILE  -  ALIGNMENT 10+00 thru 16+00", fontsize=11)
    _draw_axis(page)
    page.draw_line((295, 384), (445, 384), color=(1, 0, 0), width=1.8)         # the sole bore run, no rivals
    _start_end_notes(page)
    return _save(doc)


def plan_ambiguous_runs_with_notes() -> bytes:
    """Both endpoints source-bound BUT the geometry is ambiguous: several co-linear runs over the same span
    (no single drawn line is clearly the bore). The future AUTO gate must REJECT this (rivals present) even
    though the termini are printed-bound. REVIEW + correction-recommended today."""
    doc, page = _new_plan()
    page.insert_text((60, 60), "PLAN & PROFILE  -  ALIGNMENT 10+00 thru 16+00 (ambiguous runs)", fontsize=11)
    _draw_axis(page)
    page.draw_line((120, 400), (720, 400), color=(0, 0, 0), width=0.7)         # full-sheet baseline
    page.draw_line((295, 378), (445, 378), color=(0, 0, 0), width=1.4)         # rival A
    page.draw_line((295, 392), (445, 392), color=(1, 0, 0), width=1.6)         # rival B (red)
    page.draw_line((310, 406), (445, 406), color=(0, 0, 0), width=1.4)         # rival C
    _start_end_notes(page)
    return _save(doc)


def plan_partial_run_with_notes(width_pt) -> bytes:
    """Both endpoints source-bound BUT the drawn run covers only PART of the span (partial coverage -> low
    generic confidence). The future AUTO gate must REJECT this (coverage below the confident floor). REVIEW
    (low) today."""
    doc, page = _new_plan()
    page.insert_text((60, 60), "PLAN & PROFILE  -  ALIGNMENT 10+00 thru 16+00 (partial run)", fontsize=11)
    _draw_axis(page)
    page.draw_line((120, 400), (720, 400), color=(0, 0, 0), width=0.7)
    page.draw_line((295, 384), (295 + width_pt, 384), color=(1, 0, 0), width=1.8)
    _start_end_notes(page)
    return _save(doc)


def plan_run_sheet1_notes_sheet2() -> bytes:
    """Both endpoints source-bound BUT on a DIFFERENT sheet than the placement: the bore run is drawn on sheet
    1 while BOTH printed structure notes sit on sheet 2 (bore-log references both). Placement lands on sheet 1;
    the termini bind on sheet 2 -> a sheet mismatch the future AUTO gate must REJECT. REVIEW today."""
    doc = fitz.open()
    p1 = doc.new_page(width=792, height=612)
    p1.insert_text((60, 60), "PLAN & PROFILE  -  ALIGNMENT 10+00 thru 16+00 (SHEET 1 — run)", fontsize=11)
    _draw_axis(p1)
    p1.draw_line((295, 384), (445, 384), color=(1, 0, 0), width=1.8)           # the bore run on sheet 1
    p2 = doc.new_page(width=792, height=612)
    p2.insert_text((60, 60), "PLAN & PROFILE  -  ALIGNMENT 10+00 thru 16+00 (SHEET 2 — notes)", fontsize=11)
    _draw_axis(p2)
    _start_end_notes(p2)                                                       # BOTH structure notes on sheet 2
    return _save(doc)


# --- Printed STATION-CALLOUT builders (PRINTED_STA_CALLOUT evidence). The callout grammar is name-free and
# carries NO per-station 'STA' prefix and NO 'DIR(ECTIONAL) BORE', so it never triggers the named Brenham/ODOT
# dialects (select_dialect stays None -> the fixture stays in the cold/generic lane). ------------------------- #
def _bore_run_axis(page) -> None:
    page.insert_text((60, 60), "PLAN & PROFILE  -  ALIGNMENT 10+00 thru 16+00", fontsize=11)
    _draw_axis(page)
    page.draw_line((295, 384), (445, 384), color=(1, 0, 0), width=1.8)             # the drawn bore run


def plan_callout_span_both() -> bytes:
    """A printed station-range callout that brackets the bore span exactly -> BOTH endpoints bind as
    PRINTED_STA_CALLOUT. No 'STA a TO STA b' (would trigger Brenham); no structure notes."""
    doc, page = _new_plan()
    _bore_run_axis(page)
    page.insert_text((250, 360), "BORE 11+75 TO 13+25", fontsize=8)                # name-free span callout
    return _save(doc)


def plan_callout_start_only() -> bytes:
    """A span callout whose LOW station is the bore start but whose HIGH station is NOT the bore end and no
    other end evidence is printed -> only the START is callout-bound; the END stays missing (partial)."""
    doc, page = _new_plan()
    _bore_run_axis(page)
    page.insert_text((250, 360), "BORE 11+75 TO 12+50", fontsize=8)                # brackets the start only
    return _save(doc)


def plan_callout_ambiguous() -> bytes:
    """TWO rival span callouts that both bracket the bore span -> each endpoint is AMBIGUOUS (never
    coin-flipped)."""
    doc, page = _new_plan()
    _bore_run_axis(page)
    page.insert_text((250, 360), "BORE 11+75 TO 13+25", fontsize=8)                # rival A
    page.insert_text((250, 348), "PROPOSED BORE 11+75 TO 13+25", fontsize=8)       # rival B (same span)
    return _save(doc)


def plan_callout_unrelated() -> bytes:
    """A span callout for a DIFFERENT range (neither station matches the bore) -> binds NEITHER endpoint."""
    doc, page = _new_plan()
    _bore_run_axis(page)
    page.insert_text((250, 360), "BORE 14+50 TO 16+00", fontsize=8)                # another run's callout
    return _save(doc)


def plan_callout_conflicts_structure() -> bytes:
    """A printed structure note binds the END at 13+25 while a span callout anchored to the bore start
    brackets the bore to a DIFFERENT end (13+50) -> the two printed sources CONFLICT about the end."""
    doc, page = _new_plan()
    _bore_run_axis(page)
    page.insert_text((250, 360), "STA 11+75 INSTALLER HH", fontsize=8)             # START structure note
    page.insert_text((450, 360), "STA 13+25 SPLICE", fontsize=8)                   # END structure note (13+25)
    page.insert_text((250, 348), "BORE 11+75 TO 13+50", fontsize=8)                # callout disagrees (13+50)
    return _save(doc)


# --- Printed MATCHLINE boundary-station builders (MATCHLINE_BOUNDARY_STATION evidence). A multi-sheet bore can
# end on a printed matchline crossing; the binder confirms ONLY the BILATERAL case (both sheets print the same
# 'MATCH... STA <n> - SEE SHEET <m>' equation). The grammar carries NO 'STA a TO STA b' / 'DIR(ECTIONAL) BORE',
# so select_dialect stays None (cold/generic lane). -------------------------------------------------------- #
def _ml_sheet(doc, label, *, run=False, texts=()):
    page = doc.new_page(width=792, height=612)
    page.insert_text((60, 60), "PLAN & PROFILE  -  ALIGNMENT 10+00 thru 16+00 (%s)" % label, fontsize=11)
    _draw_axis(page)
    if run:
        page.draw_line((295, 384), (445, 384), color=(1, 0, 0), width=1.8)         # the drawn bore run
    y = 360
    for t in texts:
        page.insert_text((250, y), t, fontsize=8)
        y -= 12
    return page


def plan_matchline_bilateral() -> bytes:
    """Clean BILATERAL matchline: the END station 13+25 is printed as a matchline crossing by BOTH sheet 1 and
    sheet 2 -> the END binds MATCHLINE_BOUNDARY_STATION; the START binds via a structure note."""
    doc = fitz.open()
    _ml_sheet(doc, "SHEET 1", run=True,
              texts=("STA 11+75 INSTALLER HH", "MATCHLINE STA 13+25 - SEE SHEET 2"))
    _ml_sheet(doc, "SHEET 2", texts=("MATCHLINE STA 13+25 - SEE SHEET 1",))
    return _save(doc)


def plan_matchline_unilateral() -> bytes:
    """UNILATERAL matchline: only sheet 1 prints the 13+25 crossing; sheet 2 does NOT reciprocate -> not
    bilateral -> the END does NOT bind (the engine's CONFIRMED tier requires both sides)."""
    doc = fitz.open()
    _ml_sheet(doc, "SHEET 1", run=True,
              texts=("STA 11+75 INSTALLER HH", "MATCHLINE STA 13+25 - SEE SHEET 2"))
    _ml_sheet(doc, "SHEET 2", texts=())                       # no reciprocal equation
    return _save(doc)


def plan_matchline_ambiguous() -> bytes:
    """Two RIVAL bilateral crossings at 13+25 (the same station is a confirmed boundary in BOTH sheet pairs
    1-2 and 2-3) -> the END is AMBIGUOUS; the binder never coin-flips between rival crossings."""
    doc = fitz.open()
    _ml_sheet(doc, "SHEET 1", run=True,
              texts=("STA 11+75 INSTALLER HH", "MATCHLINE STA 13+25 - SEE SHEET 2"))
    _ml_sheet(doc, "SHEET 2",
              texts=("MATCHLINE STA 13+25 - SEE SHEET 1", "MATCHLINE STA 13+25 - SEE SHEET 3"))
    _ml_sheet(doc, "SHEET 3", texts=("MATCHLINE STA 13+25 - SEE SHEET 2",))
    return _save(doc)


def plan_matchline_sheet_mismatch() -> bytes:
    """The matchline crossing references SHEET 3, which the bore does NOT reference (bore sheets = 1,2) -> no
    bilateral boundary on the bore's own sheet pair -> the END does not bind (sheet mismatch)."""
    doc = fitz.open()
    _ml_sheet(doc, "SHEET 1", run=True,
              texts=("STA 11+75 INSTALLER HH", "MATCHLINE STA 13+25 - SEE SHEET 3"))
    _ml_sheet(doc, "SHEET 2", texts=())
    return _save(doc)


def plan_matchline_unrelated() -> bytes:
    """A bilateral matchline crossing at 13+20 (inside the span but NOT the bore end 13+25) -> binds NEITHER
    endpoint; proximity is never an exact match."""
    doc = fitz.open()
    _ml_sheet(doc, "SHEET 1", run=True,
              texts=("STA 11+75 INSTALLER HH", "MATCHLINE STA 13+20 - SEE SHEET 2"))
    _ml_sheet(doc, "SHEET 2", texts=("MATCHLINE STA 13+20 - SEE SHEET 1",))
    return _save(doc)


def plan_matchline_conflicts_callout() -> bytes:
    """The END is bilaterally matchline-bound at 13+25, but a span callout anchored to the bore start brackets
    the bore to a DIFFERENT end (13+50) -> the two printed sources CONFLICT about the end."""
    doc = fitz.open()
    _ml_sheet(doc, "SHEET 1", run=True,
              texts=("STA 11+75 INSTALLER HH", "MATCHLINE STA 13+25 - SEE SHEET 2", "BORE 11+75 TO 13+50"))
    _ml_sheet(doc, "SHEET 2", texts=("MATCHLINE STA 13+25 - SEE SHEET 1",))
    return _save(doc)


def plan_matchline_both_bound() -> bytes:
    """Both endpoints land on bilateral matchline crossings: START 11+75 (sheets 1-2) and END 13+25 (sheets
    2-3); the bore references all three sheets -> both endpoints bind MATCHLINE_BOUNDARY_STATION."""
    doc = fitz.open()
    _ml_sheet(doc, "SHEET 1", run=True, texts=("MATCHLINE STA 11+75 - SEE SHEET 2",))
    _ml_sheet(doc, "SHEET 2",
              texts=("MATCHLINE STA 11+75 - SEE SHEET 1", "MATCHLINE STA 13+25 - SEE SHEET 3"))
    _ml_sheet(doc, "SHEET 3", texts=("MATCHLINE STA 13+25 - SEE SHEET 2",))
    return _save(doc)


# --- G4 GEOMETRY-vs-ENDPOINT adversarial builders. Each prints structure notes at BOTH endpoints (so the
# termini are source-bound) but draws a SPECIFIC geometry pathology between them, to challenge the idea that
# correct endpoints prove the line. All REVIEW/ABSTAIN today (the generic lane never auto-promotes). --------- #
def _both_notes_axis(page, title) -> None:
    page.insert_text((60, 60), "PLAN & PROFILE  -  ALIGNMENT 10+00 thru 16+00 (%s)" % title, fontsize=11)
    _draw_axis(page)


def plan_parallel_rivals_with_notes() -> bytes:
    """Both endpoints source-bound, but TWO parallel red runs span the same stations -> two plausible bores."""
    doc, page = _new_plan()
    _both_notes_axis(page, "parallel rivals")
    page.draw_line((295, 380), (445, 380), color=(1, 0, 0), width=1.8)            # rival A (red)
    page.draw_line((295, 392), (445, 392), color=(1, 0, 0), width=1.8)            # rival B (red, parallel)
    _start_end_notes(page)
    return _save(doc)


def plan_broken_fragments_with_notes() -> bytes:
    """Both endpoints source-bound, but only short widely-spaced specks span the range (no weldable run)."""
    doc, page = _new_plan()
    _both_notes_axis(page, "broken fragments")
    for x in range(300, 441, 40):
        page.draw_line((x, 384), (x + 8, 384), color=(1, 0, 0), width=1.8)
    _start_end_notes(page)
    return _save(doc)


def plan_overshoot_run_with_notes() -> bytes:
    """Both endpoints source-bound, but the selected red run extends MATERIALLY BEYOND the termini."""
    doc, page = _new_plan()
    _both_notes_axis(page, "overshoot")
    page.draw_line((200, 384), (540, 384), color=(1, 0, 0), width=1.8)            # ~10+80 .. ~14+20 (>> span)
    _start_end_notes(page)
    return _save(doc)


def plan_undershoot_run_with_notes() -> bytes:
    """Both endpoints source-bound, but the red run sits in the MIDDLE and reaches neither terminus."""
    doc, page = _new_plan()
    _both_notes_axis(page, "undershoot")
    page.draw_line((325, 384), (415, 384), color=(1, 0, 0), width=1.8)            # ~12+05 .. ~12+95 only
    _start_end_notes(page)
    return _save(doc)


def plan_forked_run_with_notes() -> bytes:
    """Both endpoints source-bound, but the run FORKS: a common start segment then two diverging branches to
    the end -> the selected path can follow the wrong branch (no proven uniqueness)."""
    doc, page = _new_plan()
    _both_notes_axis(page, "forked")
    page.draw_line((295, 384), (370, 384), color=(1, 0, 0), width=1.8)            # common start
    page.draw_line((370, 384), (445, 376), color=(1, 0, 0), width=1.8)            # branch A (up to end)
    page.draw_line((370, 384), (445, 392), color=(1, 0, 0), width=1.8)            # branch B (down to end)
    _start_end_notes(page)
    return _save(doc)


def plan_baseline_trap_with_notes() -> bytes:
    """Both endpoints source-bound, but ONLY a full-sheet survey baseline spans the stations (no proposed
    bore run) -> the over-placement guard must keep this out of AUTO (abstain / baseline-flagged)."""
    doc, page = _new_plan()
    _both_notes_axis(page, "baseline trap")
    page.draw_line((120, 400), (720, 400), color=(0, 0, 0), width=0.7)            # full-sheet baseline only
    _start_end_notes(page)
    return _save(doc)


def borelog_xlsx(start=_BORE_START, end=_BORE_END, *, print_val="1", depth=5.0, boc=None) -> bytes:
    """A flat bore-log: a single bore span (station/depth/print). ``print_val`` controls the referenced plan
    sheet(s) — e.g. ``"1,2"`` declares a two-sheet bore (load_borelog -> sheet_refs=[1,2]). ``boc``, when
    given, adds a bottom-of-casing column: it is CARRIED metadata only (load_borelog does not read it and the
    terminus/placement path never uses it), exercised here to prove depth/BOC do not affect endpoint binding.
    Defaults reproduce the original single-sheet bore-log byte-for-byte."""
    wb = openpyxl.Workbook()
    ws = wb.active
    header = ["station", "depth", "print", "notes"]
    if boc is not None:
        header.insert(2, "boc")                       # carried metadata; read-order is by column NAME
    ws.append(header)

    def _row(sta, note):
        cells = [sta, depth, str(print_val), note]
        if boc is not None:
            cells.insert(2, boc)
        return cells

    ws.append(_row(start, "bore start"))
    ws.append(_row(end, "bore end"))
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


# Fixture catalog: (id, description, plan-bytes builder, expected_status, expected_blockers, n_reviewed_rows).
# expected_blockers is set only where it is already OBSERVED and stable (an honest abstain with the right named
# code is the goal); where left empty the matrix simply REPORTS the observed codes for later tightening.
# n_reviewed_rows = 0 means the bore-log review gate is intentionally left unsatisfied (no engine-ready RBL).
_CATALOG = (
    # --- placeable: the generic lane reconstructs a run and holds it for review (never auto) -------------- #
    ("pkg-001-tight-red-run",
     "Single tight red proposed bore over the bore-log span; axis + baseline + two utilities as rivals.",
     plan_tight_red_run, STATUS_REVIEW, (), 1),
    ("pkg-002-ambiguous-runs",
     "Several co-linear runs over the same span; no single line is clearly the bore.",
     plan_ambiguous_runs, STATUS_REVIEW, (), 1),
    ("pkg-007-partial-mid",
     "Red run covers ~70% of the bore span (partial coverage, above the placement floor).",
     lambda: plan_partial_run(105), STATUS_REVIEW, (), 1),
    ("pkg-009-multi-sheet",
     "Two-page plan; station axis + a red run over the span on each page.",
     plan_multi_sheet, STATUS_REVIEW, (), 1),
    # --- honest abstains: no placeable evidence -> ABSTAIN with a named reason --------------------------- #
    ("pkg-003-axis-no-runs",
     "Axis ticks present but no proposed bore drawn anywhere over the span.",
     plan_axis_no_runs, STATUS_ABSTAIN, ("NO_WELDABLE_RUN",), 1),
    ("pkg-004-blank-plan",
     "Notes-only sheet: no station axis and no drawn geometry.",
     plan_blank, STATUS_ABSTAIN, ("NO_STATION_AXIS",), 1),
    ("pkg-005-weak-axis-2-ticks",
     "Only two station ticks (below the 3-tick minimum to trust the axis) over a red run.",
     plan_weak_axis, STATUS_ABSTAIN, ("INSUFFICIENT_AXIS_QUALITY",), 1),
    ("pkg-006-partial-below-min",
     "Red run covers <50% of the bore span (below the placement floor).",
     lambda: plan_partial_run(60), STATUS_ABSTAIN, ("NO_DRAWN_RUN_OVER_SPAN",), 1),
    ("pkg-008-over-placement-baseline",
     "Full axis but only a full-sheet survey baseline; no proposed bore drawn (over-placement probe).",
     plan_baseline_only, STATUS_ABSTAIN, ("NO_DRAWN_RUN_OVER_SPAN",), 1),
    ("pkg-010-speckle-no-run",
     "Axis + short widely-spaced specks over the span; no weldable continuous run.",
     plan_speckle_no_run, STATUS_ABSTAIN, ("NO_WELDABLE_RUN",), 1),
    # --- gate-state abstain: geometry is fine but the human review gate is not satisfied ----------------- #
    ("pkg-011-no-engine-ready-borelog",
     "A good red run, but the bore-log review gate is not satisfied (no reviewed rows).",
     plan_tight_red_run, STATUS_ABSTAIN, ("NO_ENGINE_READY_REVIEWED_BORE_LOG",), 0),
)


def build_synthetic_fixtures(fixtures_root) -> list:
    """(Re)generate the synthetic fixture set under ``fixtures_root`` (idempotent: wipes + rebuilds). Returns
    the list of fixture ids written. Each fixture gets a PLAN_PDF + a BORE_LOG; ``n_reviewed_rows`` confirmed
    rows are declared (0 leaves the review gate intentionally unsatisfied)."""
    root = Path(fixtures_root)
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    written = []
    for fixture_id, desc, plan_builder, status, blockers, n_rows in _CATALOG:
        fdir = root / fixture_id
        udir = fdir / "uploads"
        udir.mkdir(parents=True, exist_ok=True)
        (udir / "project_plan.pdf").write_bytes(plan_builder())
        (udir / "bore_log.xlsx").write_bytes(borelog_xlsx())
        bore_rows = [{"row_id": "row-%d" % (i + 1),
                      "raw": {"src": "bore_log.xlsx"},
                      "normalized": {"src": "bore_log.xlsx"}}
                     for i in range(n_rows)]
        spec = {
            "fixture_id": fixture_id,
            "description": desc,
            "uploads": [
                {"kind": "PLAN_PDF", "filename": "project_plan.pdf"},
                {"kind": "BORE_LOG", "filename": "bore_log.xlsx"},
            ],
            "bore_rows": bore_rows,
            "expected": {"status": status, "blockers": list(blockers)},
        }
        (fdir / "fixture.json").write_text(json.dumps(spec, indent=2), encoding="utf-8")
        written.append(fixture_id)
    return written

