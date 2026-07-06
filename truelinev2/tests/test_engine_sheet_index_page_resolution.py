"""Regression (C2 / B-ENGINE-SHEET-PAGE-1): the match engine resolves a construction-sheet ref to its
ACTUAL PDF page from the plan's own title-block "N OF M" label when a sheet index is supplied, instead of
treating the sheet number as a raw PDF page index under a single global offset.

The proven field failure: the product upload handoff calibrates the Brenham dialect to offset 0 (its
``calibrate`` is a no-op), so ``page_index(sheet=10, offset=0) = 9`` opens PDF page 10 -- a typical-detail
sheet -- while the real callout lives on the construction plan sheet "10 OF 30" at PDF page 23. The engine
then abstains ``NO_CALLOUTS_EXTRACTED`` even though the correct page carries the printed callout.

Faithful, name-free reproduction with a SYNTHETIC plan (the real corpus PDF is not committed): a 23-page set
(2 cover + 11 typical-detail pages, then construction plan sheets "1 OF 30".."10 OF 30"), so construction
sheet 10 -> PDF page 23 (offset 13). Candidate #3's real span (STA 38+90 TO STA 44+08, DIR. BORE 518') is
printed on sheet 10's real page (PDF page 23). Uses the shipped Brenham dialect, sheet index, and matcher
unchanged -- this test edits none of them.
"""
from __future__ import annotations

import fitz  # test fixture only -- builds a synthetic plan PDF; product PDF access stays in ingest/pdf.py

from truelinev2.extract.brenham import BrenhamDialect
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.ingest.sheet_label_index import build_sheet_index
from truelinev2.match.engine import run_match
from truelinev2.schema.models import Bore, PlacementStatus

_TB = (450.0, 765.0)   # title-block region (bottom-right of a 612x792 page)
# Candidate #3 (real bore): Sheet 10 / PDF p23, STA 38+90 TO STA 44+08, DIR. BORE (518').
_CALLOUT = "STA 38+90 TO STA 44+08  DIR. BORE (518')  2-1.25\" HDPE"


def _build_brenham_like_plan(path, *, callout_on_sheet_10=True, with_titleblocks=True):
    """23-page set mirroring the real binding: 2 cover + 11 typical-detail pages, then plan sheets
    '1 OF 30'..'10 OF 30' (PDF pages 14..23). Construction sheet 10 -> PDF page 23; raw PDF page 10 is a
    typical-detail sheet with no bore callout."""
    doc = fitz.open()
    for _ in range(2):                                   # PDF pages 1-2: cover / index
        doc.new_page(width=612, height=792).insert_text(_TB, "PROJECT COVER / DRAWING INDEX", fontsize=9)
    for k in range(1, 12):                               # PDF pages 3-13: typical details TYP-1..TYP-11
        doc.new_page(width=612, height=792).insert_text(_TB, "TYPICAL DETAILS  TYP-%d" % k, fontsize=9)
    for n in range(1, 11):                               # PDF pages 14-23: plan sheets 1 OF 30 .. 10 OF 30
        page = doc.new_page(width=612, height=792)
        if with_titleblocks:
            page.insert_text(_TB, "%d OF 30   PLAN" % n, fontsize=9)
        if n == 10 and callout_on_sheet_10:
            page.insert_text((72.0, 300.0), _CALLOUT, fontsize=9)
    doc.save(str(path))
    doc.close()


def _candidate3_bore():
    return Bore(bore_id="log-candidate-3", project=None, source_file="log-candidate-3.xlsx",
                sheet_refs=[10], station_start="38+90", station_end="44+08",
                station_start_ft=3890.0, station_end_ft=4408.0, span_ft=518.0)


def test_sheet10_callout_read_from_pdf_page_23_not_raw_page_10(tmp_path):
    pdf = tmp_path / "plan.pdf"
    _build_brenham_like_plan(pdf)
    plan = PlanPdf(str(pdf))
    try:
        index = build_sheet_index(plan)
        # Sheet 10 resolves to PDF page 23 by the printed title block (Candidate #3's page).
        assert index.resolve_construction_sheet(10) == 23

        bore = _candidate3_bore()
        dialect = BrenhamDialect()

        # Direct proof the resolved offset makes the dialect read PDF page 23 (never raw page 10).
        resolved_offset = index.resolve_construction_sheet(10) - 10        # 23 - 10 = 13
        on_p23 = dialect.extract_callouts(plan, 10, resolved_offset)
        assert on_p23, "expected the Candidate #3 callout on PDF page 23"
        assert on_p23[0].page == 23
        assert on_p23[0].from_sta == "38+90" and on_p23[0].to_sta == "44+08"

        # THE BUG: the product handoff calibrates Brenham to offset 0 (no-op calibrate), so sheet 10 opens
        # raw PDF page 10 (a typical-detail sheet) -> no callout -> the wrong-page abstain.
        buggy = run_match(bore, plan, dialect, 0)
        assert buggy.status == PlacementStatus.ABSTAIN
        assert buggy.reason == "NO_CALLOUTS_EXTRACTED"

        # THE FIX: with the title-block sheet index, sheet 10 resolves to PDF page 23 -> the real callout is
        # read -> the wrong-page abstain is gone and any matched callout comes from PDF page 23.
        fixed = run_match(bore, plan, dialect, 0, sheet_index=index)
        assert fixed.reason != "NO_CALLOUTS_EXTRACTED"
        for c in fixed.matched_callouts:
            assert c.page == 23, "a matched callout must come from PDF page 23, never raw page 10"
    finally:
        plan.close()


def test_no_titleblock_index_falls_back_to_scalar_offset(tmp_path):
    """A plan with NO 'N OF M' title blocks -> the sheet index resolves nothing -> run_match with the index
    behaves byte-identically to run_match without it (honest fallback; product behavior preserved)."""
    pdf = tmp_path / "plain.pdf"
    doc = fitz.open()
    for _ in range(23):
        doc.new_page(width=612, height=792)              # blank pages, no title-block labels
    doc[9].insert_text((72.0, 300.0), _CALLOUT, fontsize=9)   # callout on RAW PDF page 10 (offset 0 finds it)
    doc.save(str(pdf))
    doc.close()
    plan = PlanPdf(str(pdf))
    try:
        index = build_sheet_index(plan)
        assert index.plan_set_total is None                       # no title-block labels at all
        assert index.resolve_construction_sheet(10) is None       # honest miss

        bore = _candidate3_bore()
        dialect = BrenhamDialect()
        without = run_match(bore, plan, dialect, 0)
        with_idx = run_match(bore, plan, dialect, 0, sheet_index=index)
        # Identical page selection + identical outcome: the unresolvable index never overrides the offset.
        assert without.reason == with_idx.reason
        assert without.status == with_idx.status
    finally:
        plan.close()
