"""Matchline page-coherence fast-follow (after Slice 1'): ``_matchline_continuity`` must read the printed
matchline grammar from each engineering sheet's RESOLVED PDF page — the plan's title-block "N OF M" page —
not from the raw scalar page index (``sheet + offset - 1``).

The bug (same family as the Slice 1' render-page bug): on a plan with FRONT MATTER (cover / general-notes
pages before the numbered construction sheets) engineering sheet N does NOT live at PDF page N. The old
matchline validator called ``plan.lines(sheet, offset)`` with the single global ``offset``, so it scanned
the front matter — where no matchline equation is printed — and reported the cross-sheet continuity as
UNVERIFIED even when both construction sheets DO print the same boundary-station matchline. The fix reuses
the identical Slice 1'/C2 resolution rule (``_resolved_sheet_offset`` → ``sheet_index``), reads each sheet's
own resolved page, and carries the pages actually read SEPARATELY from the engineering sheet ``pair``. The
verdict TIERS/THRESHOLDS are unchanged — only the pages the evidence is read from are corrected.

These tests build a synthetic REAL plan with real ``build_sheet_index`` resolution + the real matchline
grammar (nothing monkeypatched). No customer/person/place names; synthetic fixtures only; temp dirs only.
"""
from __future__ import annotations

from pathlib import Path

import fitz

from truelinev2.contracts import uploaded_corpus_engine_handoff as uce
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.ingest.sheet_label_index import build_sheet_index
from truelinev2.schema.models import Bore


def _make_matchline_plan(path: Path, *, titled: bool = True) -> None:
    """Synthetic plan with FRONT MATTER so engineering sheet N != PDF page N.

    PDF p1 = cover, p2 = general notes (both front matter: NO title block, NO matchline). PDF p3 =
    construction sheet "1 OF 2" printing ``MATCHLINE STA 15+00 - SEE SHEET 2``; PDF p4 = construction
    sheet "2 OF 2" printing ``MATCHLINE STA 15+00 - SEE SHEET 1``. So construction sheet 1 resolves to
    PDF p3 and sheet 2 to PDF p4, while the raw scalar index (sheet - 1) lands on the front matter
    (p1/p2), which prints no matchline grammar. ``titled=False`` omits the title-block labels so nothing
    resolves and the scalar fallback must byte-preserve prior behavior."""
    doc = fitz.open()
    cover = doc.new_page(width=612, height=792)
    cover.insert_text((40, 60), "PLAN SET COVER / INDEX", fontsize=12)
    notes = doc.new_page(width=612, height=792)
    notes.insert_text((40, 60), "GENERAL NOTES", fontsize=12)
    s1 = doc.new_page(width=612, height=792)
    if titled:
        s1.insert_text((470, 760), "1 OF 2", fontsize=8)
    s1.insert_text((40, 300), "MATCHLINE STA 15+00 - SEE SHEET 2", fontsize=9)
    s2 = doc.new_page(width=612, height=792)
    if titled:
        s2.insert_text((470, 760), "2 OF 2", fontsize=8)
    s2.insert_text((40, 300), "MATCHLINE STA 15+00 - SEE SHEET 1", fontsize=9)
    doc.save(str(path))
    doc.close()


def _bore_sheets_1_2(lo_ft: float = 1400.0, hi_ft: float = 1600.0) -> Bore:
    """A two-sheet bore spanning the printed 15+00 boundary, referencing construction sheets 1 and 2."""
    return Bore(bore_id="x", project=None, source_file="x", sheet_refs=[1, 2],
                station_start="14+00", station_end="16+00",
                station_start_ft=lo_ft, station_end_ft=hi_ft, span_ft=hi_ft - lo_ft)


class _StubIndex:
    """Minimal SheetIndex stand-in: resolve_construction_sheet(n) -> 1-based page, or None (honest miss)."""
    def __init__(self, mapping):
        self._m = mapping

    def resolve_construction_sheet(self, n):
        return self._m.get(int(n))


# --------------------------------------------------------------------------- #
# Unit: the shared Slice 1'/C2 resolution rule.
# --------------------------------------------------------------------------- #
def test_resolved_sheet_offset_resolves_or_falls_back():
    idx = _StubIndex({1: 3, 2: 4})              # construction sheet 1 -> PDF p3, sheet 2 -> PDF p4
    # resolvable: return the offset that lands page_index (= sheet + offset - 1) on the resolved 1-based
    # page, i.e. resolved - sheet — and ignore the scalar entirely when the sheet resolves.
    assert uce._resolved_sheet_offset(1, 0, idx) == 2       # 3 - 1
    assert uce._resolved_sheet_offset(2, 13, idx) == 2      # 4 - 2 (scalar 13 ignored)
    # honest per-sheet miss in an otherwise-present index -> scalar offset unchanged
    assert uce._resolved_sheet_offset(9, 13, idx) == 13
    # no index at all -> scalar offset unchanged (byte-identical fallback)
    assert uce._resolved_sheet_offset(1, 13, None) == 13
    # the resolved 1-based page is always sheet + returned offset
    assert 1 + uce._resolved_sheet_offset(1, 0, idx) == 3
    assert 2 + uce._resolved_sheet_offset(2, 0, idx) == 4


# --------------------------------------------------------------------------- #
# THE regression: with the title-block index the matchline grammar is read from the RESOLVED pages
# (p3/p4) and the two sheets' shared 15+00 boundary CONFIRMS continuity. Pre-fix, matchline had no way
# to reach the resolved pages (no sheet_index param), so this could not be CONFIRMED at all.
# --------------------------------------------------------------------------- #
def test_matchline_uses_resolved_pdf_page_not_raw_index(tmp_path):
    plan_path = tmp_path / "plan.pdf"
    _make_matchline_plan(plan_path)
    plan = PlanPdf(str(plan_path))
    try:
        idx = build_sheet_index(plan)
        # sanity: the index really does resolve the construction sheets behind the front matter
        assert idx.resolve_construction_sheet(1) == 3
        assert idx.resolve_construction_sheet(2) == 4

        r = uce._matchline_continuity(plan, 0, _bore_sheets_1_2(), [1, 2], sheet_index=idx)
        assert r["verdict"] == "CONFIRMED"
        assert uce.MATCHLINE_CONTINUATION_CONFIRMED_REVIEW in r["caveats"]
        row = r["evidence"][0]
        assert row["shared_boundary_station_ft"] == 1500.0
        # RESOLVED pages are carried SEPARATELY from the engineering sheet pair, and they DIFFER here
        # (front matter present) — proving the read happened on the resolved page, not the raw index.
        assert row["pair"] == [1, 2]
        assert row["pdf_pages"] == [3, 4]
    finally:
        plan.close()


def test_matchline_scalar_offset_reads_wrong_page_and_misses_evidence(tmp_path):
    # The SAME plan read via the raw scalar offset (no sheet_index) scans the front matter (p1/p2), which
    # prints no matchline — so continuity is UNVERIFIED. This is (a) the pre-fix wrong-page read the fix
    # corrects, and (b) the preserved fallback parity: with no resolvable index the behavior is unchanged.
    plan_path = tmp_path / "plan.pdf"
    _make_matchline_plan(plan_path)
    plan = PlanPdf(str(plan_path))
    try:
        r = uce._matchline_continuity(plan, 0, _bore_sheets_1_2(), [1, 2])   # no sheet_index -> scalar
        assert r["verdict"] == "UNVERIFIED"
        assert uce.MATCHLINE_CONTINUATION_UNVERIFIED in r["caveats"]
        row = r["evidence"][0]
        assert row["shared_boundary_station_ft"] is None       # nothing found on the front matter
        assert row["pdf_pages"] == [1, 2]                      # read the raw scalar pages (the bug's target)
    finally:
        plan.close()


def test_matchline_untitled_plan_is_scalar_identical(tmp_path):
    # A plan with NO title-block labels: build_sheet_index resolves nothing, so passing the index is
    # byte-identical to the scalar path. Both read the raw pages and report UNVERIFIED — the fix creates
    # no new CONFIRMED path on an unresolvable plan.
    plan_path = tmp_path / "plan.pdf"
    _make_matchline_plan(plan_path, titled=False)
    plan = PlanPdf(str(plan_path))
    try:
        idx = build_sheet_index(plan)
        with_idx = uce._matchline_continuity(plan, 0, _bore_sheets_1_2(), [1, 2], sheet_index=idx)
        scalar = uce._matchline_continuity(plan, 0, _bore_sheets_1_2(), [1, 2])
        assert with_idx == scalar
        assert with_idx["verdict"] == "UNVERIFIED"
        assert with_idx["evidence"][0]["pdf_pages"] == [1, 2]
    finally:
        plan.close()
