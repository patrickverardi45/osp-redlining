"""Slice 1': the uploaded-corpus RENDER must draw on the RESOLVED PDF page.

The engine's extraction resolves a bore log's construction-sheet reference to its ACTUAL PDF page via the
plan's own title-block "N OF M" index (C2), and records it as ``Callout.page``. The render step previously
re-resolved the page by the SCALAR offset (``sheet + offset - 1``), so on a plan with front matter (cover /
detail sheets before the numbered construction sheets) the stroke was extracted from the right page but
RASTERIZED onto the wrong one — a wrong-redline bug.

These tests run the REAL engine + REAL renderer (nothing monkeypatched) on a synthetic, generic 3-page
plan: PDF p1 = cover (no title block), p2 = construction sheet "1 OF 2" (small page), p3 = construction
sheet "2 OF 2" (large page). A bore log whose ``print`` column says sheet 2 must extract AND render on
PDF p3. Assertions are STRUCTURAL (raster dimensions, artifact names, reported pages) — never PNG hashes,
so they are stable across fitz/Pillow versions and platforms. Sheet identity semantics are locked: the
artifact filename stays keyed by the CONSTRUCTION sheet (``_s2_``), never renamed to the PDF page.

No customer/person/place names; synthetic fixtures only; temp dirs only.
"""
from __future__ import annotations

from pathlib import Path

import fitz
import openpyxl
import pytest
from PIL import Image

from truelinev2.contracts import uploaded_corpus_engine_handoff as uce
from truelinev2.contracts.customer_project import create_customer_project
from truelinev2.contracts.extracted_row import CONFIRMED, MANUAL_ENTRY, new_extracted_row
from truelinev2.contracts.processing_job import create_job, job_dir
from truelinev2.contracts.reviewed_bore_log import (
    GROUPING_CONFIRMED,
    SEPARATE_BORE,
    add_extracted_rows,
    create_reviewed_bore_log,
    define_segment_group,
    review_row_in_log,
    set_grouping_status,
)
from truelinev2.contracts.upload_pipeline import accept_upload
from truelinev2.extract.brenham import BrenhamDialect
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.ingest.sheet_label_index import build_sheet_index
from truelinev2.schema.models import Bore

AT = "2026-07-07T00:00:00Z"
BY = "op-1"
CP = "cp-0001"
JOB = "job-0001"
RBL = "rbl-1"

_SMALL = (300.0, 300.0)     # cover + construction sheet 1: the WRONG pre-fix raster target for sheet 2
_LARGE = (1224.0, 792.0)    # construction sheet 2: the page the winner callout actually lives on


def _make_plan(path: Path, *, titled: bool = True, callout_on_pdf_page: int = 3,
               sheet1_callout: bool = False) -> None:
    """Synthetic generic plan. p1 cover, p2 = "1 OF 2" (small), p3 = "2 OF 2" (large). ``titled=False``
    omits every title-block label (nothing resolvable -> the scalar mapping must byte-preserve).
    The 200' winner callout text is written on ``callout_on_pdf_page`` (1-based)."""
    doc = fitz.open()
    cover = doc.new_page(width=_SMALL[0], height=_SMALL[1])
    cover.insert_text((30, 40), "PLAN SET COVER / INDEX", fontsize=10)
    s1 = doc.new_page(width=_SMALL[0], height=_SMALL[1])
    if titled:
        s1.insert_text((220, 285), "1 OF 2", fontsize=8)
    s1.insert_text((30, 40), "ROUTE PLAN SEGMENT A", fontsize=10)
    if sheet1_callout:
        s1.insert_text((40, 150), "STA 1+50 TO STA 2+50", fontsize=8)
        s1.insert_text((40, 165), "DIR. BORE (100')", fontsize=8)
    s2 = doc.new_page(width=_LARGE[0], height=_LARGE[1])
    if titled:
        s2.insert_text((1120, 780), "2 OF 2", fontsize=8)
    # Re-fetch by index: a held Page ref is orphaned once a later new_page() mutates the doc.
    target = doc[callout_on_pdf_page - 1]
    x, y = ((400.0, 400.0) if callout_on_pdf_page == 3 else (40.0, 150.0))
    target.insert_text((x, y), "STA 1+00 TO STA 3+00", fontsize=10)
    target.insert_text((x, y + 18), "DIR. BORE (200')", fontsize=10)
    doc.save(str(path))
    doc.close()


def _make_borelog(path: Path, *, print_ref: str) -> None:
    """Brenham flat-table bore log (station|depth|boc|date|crew|print|notes) spanning 1+00 -> 3+00."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["station", "depth", "boc", "date", "crew", "print", "notes"])
    ws.append(["1+00", 4.5, None, None, None, print_ref, None])
    ws.append(["3+00", 4.8, None, None, None, None, None])
    wb.save(str(path))


def _seed_job(store: Path, plan_bytes: bytes, bore_bytes: bytes) -> None:
    create_customer_project(store, CP, "Label", AT)
    create_job(store, CP, JOB, AT, BY)
    accept_upload(store, CP, JOB, kind="PLAN_PDF", filename="plan.pdf", content=plan_bytes, stored_at=AT)
    up = accept_upload(store, CP, JOB, kind="BORE_LOG", filename="log.xlsx", content=bore_bytes, stored_at=AT)
    create_reviewed_bore_log(store, CP, JOB, up["upload_id"], RBL, at=AT, by=BY)
    row = new_extracted_row("row-1", up["upload_id"],
                            raw={"start_station": "1+00", "end_station": "3+00"},
                            normalized={"start_station": "1+00", "end_station": "3+00"},
                            extraction_method=MANUAL_ENTRY, at=AT, by=BY)
    add_extracted_rows(store, CP, JOB, RBL, [row], at=AT, by=BY)
    review_row_in_log(store, CP, JOB, RBL, "row-1", CONFIRMED, at=AT, by=BY)
    define_segment_group(store, CP, JOB, RBL, "g-1", ["row-1"], SEPARATE_BORE, at=AT, by=BY)
    set_grouping_status(store, CP, JOB, RBL, "g-1", GROUPING_CONFIRMED, at=AT, by=BY)


def _build(tmp: Path, *, titled: bool = True, print_ref: str = "2",
           callout_on_pdf_page: int = 3, sheet1_callout: bool = False) -> Path:
    plan, bore = tmp / "src_plan.pdf", tmp / "src_log.xlsx"
    _make_plan(plan, titled=titled, callout_on_pdf_page=callout_on_pdf_page, sheet1_callout=sheet1_callout)
    _make_borelog(bore, print_ref=print_ref)
    store = tmp / "store"
    store.mkdir()
    _seed_job(store, plan.read_bytes(), bore.read_bytes())
    return store


def _artifact_paths(store: Path, summary: dict) -> list:
    base = job_dir(store, CP, JOB) / uce.BUNDLE_STORE_SUBDIR / summary["artifact_bundle_slot"]
    return [base / a["path"] for a in summary["artifacts"]]


# --------------------------------------------------------------------------- #
# THE regression: extraction resolved construction sheet 2 -> PDF p3 (title block), so the stroke
# must be RASTERIZED on PDF p3. Pre-fix, the render re-resolved by scalar offset and rasterized
# PDF p2 (small "1 OF 2" page) where the callout bbox lies almost entirely off-page -> the published
# PNG was a boundary sliver. Raster dimensions are the environment-stable discriminator.
# --------------------------------------------------------------------------- #
def test_render_rasterizes_the_resolved_pdf_page(tmp_path):
    store = _build(tmp_path)
    summary = uce.render_uploaded_corpus_engine_handoff(store, CP, JOB, at=AT, by=BY)
    assert summary["status"] == "SUCCEEDED"
    paths = _artifact_paths(store, summary)
    assert len(paths) == 1 and paths[0].is_file()
    img = Image.open(paths[0])
    # On PDF p3 the clip = callout bbox +/- 130pt pad at zoom 2 -> hundreds of px per axis. On the
    # wrong page (PDF p2, 300x300pt, bbox mostly outside) the clip clamps to a sliver < 200px wide.
    assert img.width > 400 and img.height > 300, (
        "raster %dx%d is a wrong-page sliver — the stroke was rendered on the scalar-offset page, "
        "not the title-block-resolved PDF page" % (img.width, img.height))
    # Sheet-identity lock: the artifact stays keyed by the CONSTRUCTION sheet (s2), never renamed to
    # the PDF page (s3) — engineering sheet number and PDF page index are separate axes.
    assert paths[0].name.endswith("_s2_redline_stroke.png")


def test_candidate_reports_sheet_and_resolved_pdf_page_separately(tmp_path):
    store = _build(tmp_path)
    ev = uce.evaluate_uploaded_corpus_engine_handoff(store, CP, JOB)
    assert ev["runnable"] is True
    c = ev["candidate"]
    assert c["sheet"] == 2          # engineering sheet identity (what the bore log's print says)
    assert c["pdf_page"] == 3       # the resolved raster/render page — reported SEPARATELY, never conflated


def test_unresolvable_plan_keeps_scalar_mapping(tmp_path):
    # NO title-block labels anywhere -> the sheet index resolves nothing -> extraction AND render use
    # the scalar mapping exactly as before this slice (fallback parity; behavior preserved).
    store = _build(tmp_path, titled=False, callout_on_pdf_page=2)
    ev = uce.evaluate_uploaded_corpus_engine_handoff(store, CP, JOB)
    assert ev["runnable"] is True
    assert ev["candidate"]["sheet"] == 2
    assert ev["candidate"]["pdf_page"] == 2          # sheet + offset(0): the unchanged scalar mapping
    summary = uce.render_uploaded_corpus_engine_handoff(store, CP, JOB, at=AT, by=BY)
    img = Image.open(_artifact_paths(store, summary)[0])
    assert img.width > 300 and img.height > 300      # rendered ON PDF p2 (clip interior, not a sliver)


def test_render_key_includes_resolved_page():
    # A corrected page resolution must mint a NEW engine run: a pre-fix wrong-page bundle can never be
    # replayed as current content by the idempotency short-circuit.
    legs_a = [{"sheet": 2, "pdf_page": 3, "stroke_points": [(1.0, 2.0), (3.0, 4.0)]}]
    legs_b = [{"sheet": 2, "pdf_page": 2, "stroke_points": [(1.0, 2.0), (3.0, 4.0)]}]
    ka = uce._render_content_key("p.pdf", "b.xlsx", "log-1", "REVIEW", legs_a)
    kb = uce._render_content_key("p.pdf", "b.xlsx", "log-1", "REVIEW", legs_b)
    assert ka != kb
    assert ka == uce._render_content_key("p.pdf", "b.xlsx", "log-1", "REVIEW", legs_a)   # stable


def test_extra_sheet_legs_resolve_their_own_pages(tmp_path):
    # Cross-sheet legs: referenced construction sheet 1 lives at PDF p2 (behind the cover). With the
    # title-block index the leg extracts from ITS resolved page; without it (pre-fix behavior) the
    # raw page index hits the cover and the leg silently vanishes.
    plan_path = tmp_path / "p.pdf"
    _make_plan(plan_path, sheet1_callout=True)
    bore = Bore(bore_id="log", source_file="log.xlsx", sheet_refs=[2, 1],
                station_start="1+00", station_end="3+00",
                station_start_ft=100.0, station_end_ft=300.0, span_ft=200.0)
    plan = PlanPdf(str(plan_path))
    try:
        idx = build_sheet_index(plan)
        legs = uce._extra_sheet_legs(plan, BrenhamDialect(), 0, bore, 2, sheet_index=idx)
        assert [l["sheet"] for l in legs] == [1]
        assert legs[0]["pdf_page"] == 2              # construction sheet 1 -> PDF p2 (its OWN page)
        # scalar fallback (no index): raw page index 1 = the cover -> no callouts -> no leg (the
        # pre-fix silent-missing-leg behavior, preserved as the honest fallback)
        assert uce._extra_sheet_legs(plan, BrenhamDialect(), 0, bore, 2) == []
    finally:
        plan.close()


def test_multi_leg_render_covers_both_resolved_pages(tmp_path):
    # End-to-end: print "2, 1" -> winner on construction sheet 2 (PDF p3) + a cross-sheet leg on
    # construction sheet 1 (PDF p2). Pre-fix the extra leg silently vanished (cover had no callouts),
    # so artifact_count == 2 is itself the regression assertion.
    store = _build(tmp_path, print_ref="2, 1", sheet1_callout=True)
    summary = uce.render_uploaded_corpus_engine_handoff(store, CP, JOB, at=AT, by=BY)
    assert summary["status"] == "SUCCEEDED"
    assert summary["artifact_count"] == 2
    names = sorted(p.name for p in _artifact_paths(store, summary))
    assert names == ["%s_s1_redline_stroke.png" % RBL, "%s_s2_redline_stroke.png" % RBL]


def test_unresolvable_sheet_ref_still_abstains(tmp_path):
    # Refusal posture unchanged: a print reference no construction sheet carries (and no raw page
    # backs) still abstains honestly — this slice creates ZERO new render-success paths.
    store = _build(tmp_path, print_ref="7")
    ev = uce.evaluate_uploaded_corpus_engine_handoff(store, CP, JOB)
    assert ev["runnable"] is False
    assert any(b["code"] == uce.ENGINE_ABSTAINED for b in ev["blockers"])
    with pytest.raises(uce.UploadedCorpusEngineError):
        uce.render_uploaded_corpus_engine_handoff(store, CP, JOB, at=AT, by=BY)
