"""Title-block sheet-resolution layer — map a CONSTRUCTION-SHEET reference to the actual PDF page.

A construction set's bore log references a sheet by its TITLE-BLOCK label (e.g. "7", meaning the plan
sheet whose title block reads "SHEETS 7 OF 30"). That construction-sheet number is NOT the same as the
PDF document page index: a 30-sheet plan set is commonly bound behind a cover/index + a run of
typical-detail sheets, so "sheet 7 OF 30" can live at PDF page 20 of 43. Treating the sheet label as a
raw PDF page index opens the wrong page (a typical-details sheet, not the route plan sheet).

This module reads each page's printed title-block label to build that mapping from the PDF's OWN evidence
— no hardcoded offset, no customer/project/location literals (the plan set total, e.g. 30, is DATA
discovered from the title blocks). It distinguishes three page types so a caller can prefer a route/station
plan sheet and avoid cover/index/legend/typical/detail pages:

  * CONSTRUCTION_PLAN   — title block carries an "N OF M" sheet number (M = the plan-set total).
  * TYPICAL_DETAILS     — title block carries a "TYP-n" / typical-detail label (no "N OF M").
  * OTHER               — cover / index / legend / standard inserts (neither label).

It is read-only and takes a ``PlanPdf`` (the v2 fitz wrapper), mirroring ``extract/sheet_map.derive_offset``.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Optional

# "N OF M" sheet-number token, e.g. "7 OF 30". A run of digits, the word OF, a run of digits — with word
# boundaries so an inch-marked note like '12" OF 3/4"' (the quote breaks the digit run) does NOT match.
_OF_RE = re.compile(r"\b(\d{1,3})\s+OF\s+(\d{1,3})\b", re.IGNORECASE)
# Typical / standard-detail label, e.g. "TYP-6", "TYP-8A".
_TYP_RE = re.compile(r"\bTYP\s*-\s*(\d{1,3}[A-Z]?)\b", re.IGNORECASE)

# Title-block region (DISPLAY space): bottom-right of the page. Used ONLY to disambiguate when one page
# prints more than one distinct "N OF M(total)" token (the title-block one wins). The primary signal is the
# modal plan-set total, which already rejects stray note matches.
_TB_RIGHT_FRAC = 0.45   # right-most 45% of the page width
_TB_BOTTOM_FRAC = 0.30  # bottom-most 30% of the page height

SHEET_TYPE_CONSTRUCTION_PLAN = "CONSTRUCTION_PLAN"
SHEET_TYPE_TYPICAL_DETAILS = "TYPICAL_DETAILS"
SHEET_TYPE_OTHER = "OTHER"


@dataclass(frozen=True)
class PageSheet:
    pdf_page_number: int                       # 1-based PDF page number (what the viewer shows: "X of N")
    pdf_page_index: int                        # 0-based page index
    construction_sheet_number: Optional[int]   # the "N" in the title-block "N OF M" (a plan sheet), else None
    sheet_total: Optional[int]                 # the "M" (plan-set total), else None
    plan_sheet_label: Optional[str]            # human label, e.g. "7 OF 30" or "TYP-6", else None
    sheet_type: str                            # one of the SHEET_TYPE_* constants

    @property
    def is_plan_sheet(self) -> bool:
        return self.sheet_type == SHEET_TYPE_CONSTRUCTION_PLAN


@dataclass(frozen=True)
class SheetIndex:
    pages: List[PageSheet]
    plan_set_total: Optional[int]              # the modal "M" across the document (e.g. 30), or None

    def resolve_construction_sheet(self, sheet_ref: int) -> Optional[int]:
        """Map a construction-sheet reference (e.g. 7 = "7 OF 30") to its PDF page NUMBER, or None when no
        plan sheet carries that label (honest miss — never a guess / never the raw page index)."""
        try:
            ref = int(sheet_ref)
        except (TypeError, ValueError):
            return None
        for p in self.pages:
            if p.sheet_type == SHEET_TYPE_CONSTRUCTION_PLAN and p.construction_sheet_number == ref:
                return p.pdf_page_number
        return None


def _titleblock_tokens(plan, page_number: int) -> str:
    """Concatenated text of the title-block region (bottom-right, DISPLAY space) for tie-breaking."""
    bounds = plan.page_bounds_display(page_number, 0)
    if bounds is None:
        return ""
    x0, y0, x1, y1 = bounds
    w, h = x1 - x0, y1 - y0
    x_min = x0 + (1.0 - _TB_RIGHT_FRAC) * w
    y_min = y0 + (1.0 - _TB_BOTTOM_FRAC) * h
    toks = [wd["text"] for wd in plan.words(page_number, 0)
            if wd["x0"] >= x_min and wd["y0"] >= y_min]
    return " ".join(toks)


def build_sheet_index(plan) -> SheetIndex:
    """Build the per-page construction-sheet index from a plan's own title-block labels. Read-only."""
    # Pass 1: gather every "N OF M" candidate per page (whole-page text) and the typical-detail label.
    per_page_ofs: List[List[tuple]] = []
    per_page_typ: List[Optional[str]] = []
    totals: Counter = Counter()
    for idx in range(plan.page_count):
        text = plan.text_by_index(idx)
        ofs = [(int(a), int(b)) for a, b in _OF_RE.findall(text)]
        typ = _TYP_RE.search(text)
        per_page_ofs.append(ofs)
        per_page_typ.append(typ.group(1) if typ else None)
        for _, m in ofs:
            totals[m] += 1
    plan_set_total = totals.most_common(1)[0][0] if totals else None

    pages: List[PageSheet] = []
    for idx in range(plan.page_count):
        page_number = idx + 1
        ofs, typ = per_page_ofs[idx], per_page_typ[idx]
        construction_sheet = sheet_total = None
        label = None
        sheet_type = SHEET_TYPE_OTHER

        # A construction plan sheet = a title-block "N OF <plan_set_total>" token.
        distinct_n = sorted({n for (n, m) in ofs if m == plan_set_total}) if plan_set_total else []
        chosen_n: Optional[int] = None
        if len(distinct_n) == 1:
            chosen_n = distinct_n[0]
        elif len(distinct_n) > 1:
            # Ambiguous: more than one "N OF total" on the page (e.g. a note). The title-block one wins.
            tb = _titleblock_tokens(plan, page_number).upper()
            tb_n = sorted({int(a) for a, b in _OF_RE.findall(tb) if int(b) == plan_set_total})
            if len(tb_n) == 1:
                chosen_n = tb_n[0]
            # else: genuinely ambiguous -> leave OTHER (honest; never guess a plan-sheet number)

        if chosen_n is not None:
            construction_sheet, sheet_total = chosen_n, plan_set_total
            label = "%d OF %d" % (chosen_n, plan_set_total)
            sheet_type = SHEET_TYPE_CONSTRUCTION_PLAN
        elif typ is not None:
            label = "TYP-%s" % typ
            sheet_type = SHEET_TYPE_TYPICAL_DETAILS

        pages.append(PageSheet(pdf_page_number=page_number, pdf_page_index=idx,
                               construction_sheet_number=construction_sheet, sheet_total=sheet_total,
                               plan_sheet_label=label, sheet_type=sheet_type))
    return SheetIndex(pages=pages, plan_set_total=plan_set_total)


def construction_sheet_for_page(index: SheetIndex, pdf_page_number: int) -> Optional[int]:
    """Reverse lookup: the construction-sheet number printed on a given PDF page (for honest labelling of a
    rendered artifact), or None if that page is not a numbered plan sheet."""
    for p in index.pages:
        if p.pdf_page_number == pdf_page_number:
            return p.construction_sheet_number
    return None
