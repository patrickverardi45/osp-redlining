"""Regression: the title-block sheet-resolution layer maps a CONSTRUCTION-SHEET reference to the actual
PDF page, never to the raw PDF page index.

Reproduces the exact field-reported mismatch with a SYNTHETIC, name-free plan set (the real corpus PDF is
not committed): a 43-page set where the bore log's "sheet 7" must open the construction plan sheet whose
title block reads "7 OF 30" (PDF page 20), NOT PDF page 7 — which is a typical-details sheet ("TYP-6").
The structure (2 cover + 11 typical-detail pages, then 30 numbered plan sheets) mirrors the real upload,
so the derived sheet->page offset is 13 (page = sheet + 13), matching the engine's config sheet_offset.

Generic data only — no customer/project/location names.
"""
from __future__ import annotations

import fitz  # test fixture only — builds a synthetic plan PDF; product PDF access stays in ingest/pdf.py

from truelinev2.config import Settings
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.ingest.sheet_label_index import (
    SHEET_TYPE_CONSTRUCTION_PLAN,
    SHEET_TYPE_OTHER,
    SHEET_TYPE_TYPICAL_DETAILS,
    build_sheet_index,
    construction_sheet_for_page,
)

# Mirrors the real upload's binding order: PDF pages 1-2 cover/index; 3-13 typical details (TYP-1..TYP-11);
# 14-43 the 30 numbered construction plan sheets (1 OF 30..30 OF 30). So sheet N lives at PDF page 13 + N.
_N_PLAN = 30
_DETAIL_PAGES = 11
_COVER_PAGES = 2
_TB = (450.0, 765.0)        # title-block region (bottom-right of a 612x792 page)


def _title(page, text):
    page.insert_text(_TB, text, fontsize=9)


def _build_plan(path, *, decoy_on_sheet=None):
    """Write a synthetic 43-page plan set. ``decoy_on_sheet`` (a construction sheet number) also prints a
    stray 'k OF 30' note OUTSIDE the title block on that sheet's page, to exercise the tie-break."""
    doc = fitz.open()
    # cover/index
    for _ in range(_COVER_PAGES):
        _title(doc.new_page(width=612, height=792), "PROJECT COVER / DRAWING INDEX")
    # typical details — labelled so PDF page 7 is "TYP-6" (faithful to the field-reported mismatch, where
    # the detail label is not strictly the PDF page index).
    for k in range(1, _DETAIL_PAGES + 1):
        _title(doc.new_page(width=612, height=792), "TYPICAL DETAILS  TYP-%d" % (k + 1))
    # construction plan sheets 1 OF 30 .. 30 OF 30
    for n in range(1, _N_PLAN + 1):
        page = doc.new_page(width=612, height=792)
        _title(page, "%d OF %d   PLAN" % (n, _N_PLAN))
        if decoy_on_sheet is not None and n == decoy_on_sheet:
            # a stray 'k OF 30' note in the drawing body (top-left) — must NOT win over the title block
            page.insert_text((60.0, 60.0), "SEE NOTE 5 OF %d FOR DETAIL" % _N_PLAN, fontsize=9)
    doc.save(str(path))
    doc.close()


def test_construction_sheet_7_resolves_to_pdf_page_20_not_7(tmp_path):
    pdf = tmp_path / "plan.pdf"
    _build_plan(pdf)
    plan = PlanPdf(str(pdf))
    try:
        index = build_sheet_index(plan)
    finally:
        plan.close()

    assert index.plan_set_total == _N_PLAN
    # THE bug: sheet 7 must resolve to PDF page 20 (title block "7 OF 30"), never PDF page 7.
    assert index.resolve_construction_sheet(7) == 20
    assert index.resolve_construction_sheet(7) != 7
    # PDF page 7 is a typical-details sheet (TYP-6) — not a route plan sheet.
    p7 = index.pages[6]
    assert p7.sheet_type == SHEET_TYPE_TYPICAL_DETAILS
    assert p7.plan_sheet_label == "TYP-6"
    assert p7.is_plan_sheet is False
    # PDF page 20 IS construction sheet 7.
    p20 = index.pages[19]
    assert p20.sheet_type == SHEET_TYPE_CONSTRUCTION_PLAN
    assert p20.construction_sheet_number == 7
    assert p20.plan_sheet_label == "7 OF 30"
    assert p20.is_plan_sheet is True


def test_full_mapping_and_offset_match_config(tmp_path):
    pdf = tmp_path / "plan.pdf"
    _build_plan(pdf)
    plan = PlanPdf(str(pdf))
    try:
        index = build_sheet_index(plan)
    finally:
        plan.close()

    # endpoints + count
    assert index.resolve_construction_sheet(1) == 14
    assert index.resolve_construction_sheet(_N_PLAN) == 13 + _N_PLAN
    assert sum(1 for p in index.pages if p.is_plan_sheet) == _N_PLAN
    assert sum(1 for p in index.pages if p.sheet_type == SHEET_TYPE_TYPICAL_DETAILS) == _DETAIL_PAGES
    assert sum(1 for p in index.pages if p.sheet_type == SHEET_TYPE_OTHER) == _COVER_PAGES
    # the data-derived offset equals the engine's configured sheet_offset (no hardcoded constant in code)
    offsets = {p.pdf_page_number - p.construction_sheet_number for p in index.pages if p.is_plan_sheet}
    assert offsets == {Settings.__dataclass_fields__["sheet_offset"].default}


def test_unresolvable_sheet_ref_is_honest_none(tmp_path):
    pdf = tmp_path / "plan.pdf"
    _build_plan(pdf)
    plan = PlanPdf(str(pdf))
    try:
        index = build_sheet_index(plan)
    finally:
        plan.close()
    # a sheet ref past the plan set resolves to None (honest miss) — never the raw PDF page index.
    assert index.resolve_construction_sheet(_N_PLAN + 5) is None
    assert index.resolve_construction_sheet(0) is None


def test_reverse_lookup_construction_sheet_for_page(tmp_path):
    pdf = tmp_path / "plan.pdf"
    _build_plan(pdf)
    plan = PlanPdf(str(pdf))
    try:
        index = build_sheet_index(plan)
    finally:
        plan.close()
    assert construction_sheet_for_page(index, 20) == 7     # rendered on PDF page 20 -> labelled sheet 7
    assert construction_sheet_for_page(index, 7) is None   # a detail page has no construction-sheet number


def test_titleblock_wins_over_stray_of_note(tmp_path):
    # Sheet 7's page also prints a stray '5 OF 30' note in the body; the title-block "7 OF 30" must win,
    # and the stray note must not corrupt sheet 5's own resolution.
    pdf = tmp_path / "plan.pdf"
    _build_plan(pdf, decoy_on_sheet=7)
    plan = PlanPdf(str(pdf))
    try:
        index = build_sheet_index(plan)
    finally:
        plan.close()
    assert index.pages[19].construction_sheet_number == 7  # PDF page 20 stays sheet 7 (title block wins)
    assert index.resolve_construction_sheet(7) == 20
    assert index.resolve_construction_sheet(5) == 18       # sheet 5 = PDF page 18, unaffected by the note


def test_rotated_pages_are_read(tmp_path):
    # Rotation must not break label reading (the real plan is rotation 270). Small rotated set: 1 cover +
    # 2 plan sheets "1 OF 2" / "2 OF 2".
    pdf = tmp_path / "rot.pdf"
    doc = fitz.open()
    cover = doc.new_page(width=792, height=612)
    cover.set_rotation(270)
    _title(cover, "COVER")
    for n in (1, 2):
        p = doc.new_page(width=792, height=612)
        p.set_rotation(270)
        p.insert_text((500.0, 560.0), "%d OF 2  PLAN" % n, fontsize=9)
    doc.save(str(pdf))
    doc.close()
    plan = PlanPdf(str(pdf))
    try:
        index = build_sheet_index(plan)
    finally:
        plan.close()
    assert index.plan_set_total == 2
    assert index.resolve_construction_sheet(1) == 2        # cover is PDF page 1; sheet 1 -> PDF page 2
    assert index.resolve_construction_sheet(2) == 3
