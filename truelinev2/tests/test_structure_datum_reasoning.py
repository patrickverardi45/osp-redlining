"""Structure-datum REVIEW-candidate reasoning (the owner-gated slice after the Print-Reference audit).

A NARROW, REVIEW-ONLY reasoner that can place a bore when the logged span does NOT exactly match a printed
callout box, but a source-supported structure/station DATUM on the print-ref-resolved sheet proves the correct
drill run. Doctrine: the tally decides extent; the plan supplies shape; the print ref locates the construction
sheet; engineering-sheet identity and PDF-page identity stay separate; no source evidence -> no redline; no
wrong redlines; REVIEW only, never AUTO/final.

A candidate is produced ONLY when all hold: (1) confirmed station-series span, (2) print/sheet ref present,
(3) the ref resolves to an engineering sheet + PDF page, (4) a printed datum witness exists on that sheet,
(5) it matches one span endpoint, (6) exactly one run is bounded from that datum + the logged footage, and
(7) the other endpoint lands on independent source evidence. (8) >1 candidate -> named ambiguity refusal;
(9) no datum witness -> named missing-datum refusal.

The reasoner is a pure read-only harness composition of the shipped ``extract/`` observers
(``plan_view_anchor_resolver`` + ``matchline_join``); it imports nothing from render / placement / api / store
/ contracts / match / web, draws nothing, places nothing, promotes nothing. All fixtures are generic + synthetic
(tmp_path); no customer/person/place names. Front-matter plans prove the reasoner reads the RESOLVED PDF page,
not the raw page index.
"""
from __future__ import annotations

from pathlib import Path

import fitz

from truelinev2.harness import structure_datum_reasoning as sdr
from truelinev2.harness.span_extractor import SPAN_ROW_CONFIRMED, SpanRow
from truelinev2.ingest.pdf import PlanPdf

# Two endpoints, 200 ft apart, on the construction sheet (PDF p2) behind one front-matter page (PDF p1).
_START_STA, _END_STA = "10+00", "12+00"
_START_FT, _END_FT, _FOOTAGE = 1000.0, 1200.0, 200.0
# engineering sheet 1 lives at PDF page 2 (front matter shifts it) -> offset 1; the resolved read must land on p2.
_SHEET, _PDF_PAGE, _OFFSET = 1, 2, 1


def _sheet_ctx(*, refusal=None, source=sdr.SHEET_SOURCE_SHEET_REF, sheet=_SHEET, page=_PDF_PAGE):
    """A Slice-3 sheet_context dict as the reasoner receives it (engineering sheet + resolved PDF page separate)."""
    off = None if (sheet is None or page is None) else int(page) - int(sheet)
    return {"engineering_sheet": sheet, "pdf_page": page, "sheet_offset": off, "source": source,
            "sheet_refs": [1], "print_refs": ["1"], "refusal": refusal,
            "reason": "test" if refusal is None else refusal}


def _row(*, footage=_FOOTAGE, sheet_refs=(1,), status=SPAN_ROW_CONFIRMED):
    return SpanRow(span_id="span-001", source_file="b.csv", source_page=None, source_kind="CSV_TABLE",
                   start_station=_START_STA, end_station=_END_STA, footage=footage,
                   start_structure=None, end_structure=None, status=status, confidence="HIGH",
                   citation="", bbox=None, detail={}, print_raw="1", sheet_refs=tuple(sheet_refs))


def _word_center(pdf_path, sheet, offset, station_text):
    plan = PlanPdf(str(pdf_path))
    try:
        return {w["text"]: (w["xc"], w["yc"]) for w in plan.words(sheet, offset)}[station_text]
    finally:
        plan.close()


def _symbol(page, cx, cy):
    """A compact closed 8x8 square ~12 pt from a label center -> a PROXIMITY_SYMBOL structure datum."""
    page.draw_rect(fitz.Rect(cx + 8, cy - 4, cx + 16, cy + 4), color=(0, 0, 0), width=1)


def _build_plan(tmp_path, *, start_kind, end_kind, titled=True):
    """3-object synthetic plan: p1 front matter, p2 = the construction sheet with the two station labels and a
    datum of ``start_kind``/``end_kind`` at each ('symbol' = structure square, 'route' = a drawn run terminus,
    'ambiguous' = two squares, 'none' = label only / nothing). Endpoint geometry is read from a probe so font
    metrics are never guessed."""
    probe = tmp_path / "probe.pdf"
    doc = fitz.open()
    doc.new_page(width=300, height=200)                                  # p1 front matter (unused geometry)
    pg = doc.new_page(width=612, height=300)                             # p2 construction sheet
    pg.insert_text((110, 150), _START_STA, fontsize=8)
    pg.insert_text((430, 150), _END_STA, fontsize=8)
    doc.save(str(probe))
    doc.close()
    c_start = _word_center(probe, _SHEET, _OFFSET, _START_STA)
    c_end = _word_center(probe, _SHEET, _OFFSET, _END_STA)

    doc = fitz.open()
    cover = doc.new_page(width=300, height=200)
    cover.insert_text((30, 40), "PLAN SET COVER / INDEX", fontsize=10)
    pg = doc.new_page(width=612, height=300)
    pg.insert_text((110, 150), _START_STA, fontsize=8)
    pg.insert_text((430, 150), _END_STA, fontsize=8)

    def _place(kind, center, other_center):
        cx, cy = center
        if kind == "symbol":
            _symbol(pg, cx, cy)
        elif kind == "ambiguous":
            _symbol(pg, cx, cy)
            pg.draw_rect(fitz.Rect(cx - 16, cy - 4, cx - 8, cy + 4), color=(0, 0, 0), width=1)   # 2nd symbol
        elif kind == "route":                                            # a run terminating AT this label
            ox, oy = other_center
            mx, my = (cx + ox) / 2.0, (cy + oy) / 2.0
            pg.draw_line(fitz.Point(cx, cy), fitz.Point(mx, my), color=(0, 0, 0), width=1)
        # "none" -> draw nothing near this endpoint

    _place(start_kind, c_start, c_end)
    _place(end_kind, c_end, c_start)
    out = tmp_path / ("plan-%s-%s.pdf" % (start_kind, end_kind))
    doc.save(str(out))
    doc.close()
    return str(out)


# --------------------------------------------------------------------------------------------------------- #
# Constant-sync lock: the pass-through refusal codes match the Slice-3 bridge (single source of truth).
# --------------------------------------------------------------------------------------------------------- #
def test_refusal_codes_match_slice3_bridge():
    from truelinev2.harness import product_readiness_bridge as bridge
    assert sdr.SHEET_REF_UNRESOLVED == bridge.SHEET_REF_UNRESOLVED
    assert sdr.MULTI_SHEET_REFS_UNSUPPORTED == bridge.MULTI_SHEET_REFS_UNSUPPORTED
    assert sdr.SHEET_SOURCE_SHEET_REF == bridge.SHEET_SOURCE_SHEET_REF


# --------------------------------------------------------------------------------------------------------- #
# (1) Positive: structure datum at the bore-log START, far endpoint (END) on a run terminus -> REVIEW candidate
# on the RESOLVED PDF page, with both axes reported separately and the run bounded by the tally.
# --------------------------------------------------------------------------------------------------------- #
def test_structure_datum_at_start_places_review_candidate(tmp_path):
    plan = _build_plan(tmp_path, start_kind="symbol", end_kind="route")
    r = sdr.reason_structure_datum(_row(), _sheet_ctx(), plan)
    assert r.status == sdr.STRUCTURE_DATUM_REVIEW_CANDIDATE and r.ready is True
    c = r.candidate
    assert c["anchor_endpoint"] == "start" and c["anchor_datum_kind"] == sdr.STRUCTURE_SYMBOL
    assert c["far_endpoint"] == "end" and c["far_evidence_kind"] == sdr.CALLOUT_RUN_ENDPOINT
    assert c["run_lo_ft"] == _START_FT and c["run_hi_ft"] == _END_FT       # tally decides extent (200 ft)
    assert c["engineering_sheet"] == 1 and c["pdf_page"] == 2              # identities kept SEPARATE
    # REVIEW-only invariants locked
    assert r.is_review_candidate and not r.performs_auto and not r.performs_placement and not r.promotes_status
    assert c["anchor_xy"] is not None                                      # observer-exposed, never invented
    assert any("review candidate" in s.lower() for s in r.evidence_chain)


# (2) Positive: structure datum at the bore-log END (far endpoint = START on a run terminus).
def test_structure_datum_at_end_places_review_candidate(tmp_path):
    plan = _build_plan(tmp_path, start_kind="route", end_kind="symbol")
    r = sdr.reason_structure_datum(_row(), _sheet_ctx(), plan)
    assert r.status == sdr.STRUCTURE_DATUM_REVIEW_CANDIDATE and r.ready is True
    c = r.candidate
    assert c["anchor_endpoint"] == "end" and c["anchor_datum_kind"] == sdr.STRUCTURE_SYMBOL
    assert c["far_endpoint"] == "start" and c["far_evidence_kind"] == sdr.CALLOUT_RUN_ENDPOINT
    assert c["run_lo_ft"] == _START_FT and c["run_hi_ft"] == _END_FT


# --------------------------------------------------------------------------------------------------------- #
# (3) Refusal: no printed datum witness at either endpoint (labels only, no drawn anchor).
# --------------------------------------------------------------------------------------------------------- #
def test_no_datum_witness_refuses_named(tmp_path):
    plan = _build_plan(tmp_path, start_kind="none", end_kind="none")
    r = sdr.reason_structure_datum(_row(), _sheet_ctx(), plan)
    assert r.status == sdr.NO_PRINTED_DATUM_WITNESS and r.ready is False and r.candidate is None
    assert "datum" in r.reason.lower()


# --------------------------------------------------------------------------------------------------------- #
# (4) Refusal: the anchor station resolves to TWO plausible structures -> named ambiguity (no guessing).
# --------------------------------------------------------------------------------------------------------- #
def test_ambiguous_datum_refuses_named(tmp_path):
    plan = _build_plan(tmp_path, start_kind="ambiguous", end_kind="route")
    r = sdr.reason_structure_datum(_row(), _sheet_ctx(), plan)
    assert r.status == sdr.AMBIGUOUS_STRUCTURE_DATUM and r.ready is False and r.candidate is None


# --------------------------------------------------------------------------------------------------------- #
# (5) Refusal: a datum exists at one endpoint but the OTHER endpoint lands on no source evidence.
# --------------------------------------------------------------------------------------------------------- #
def test_unsupported_far_endpoint_refuses_named(tmp_path):
    plan = _build_plan(tmp_path, start_kind="symbol", end_kind="none")
    r = sdr.reason_structure_datum(_row(), _sheet_ctx(), plan)
    assert r.status == sdr.UNSUPPORTED_FAR_ENDPOINT and r.ready is False and r.candidate is None
    assert "other endpoint" in r.reason.lower() or "far" in r.reason.lower()


# --------------------------------------------------------------------------------------------------------- #
# (6) Refusal: unresolved / multi-sheet print refs continue the existing safe behavior (Slice-3 pass-through)
# -> the reasoner never runs on a guessed page.
# --------------------------------------------------------------------------------------------------------- #
def test_unresolved_sheet_ref_passes_through(tmp_path):
    plan = _build_plan(tmp_path, start_kind="symbol", end_kind="route")
    r = sdr.reason_structure_datum(_row(), _sheet_ctx(refusal=sdr.SHEET_REF_UNRESOLVED, source=None,
                                                     sheet=1, page=None), plan)
    assert r.status == sdr.SHEET_REF_UNRESOLVED and r.ready is False and r.candidate is None


def test_multi_sheet_refs_pass_through(tmp_path):
    plan = _build_plan(tmp_path, start_kind="symbol", end_kind="route")
    r = sdr.reason_structure_datum(_row(sheet_refs=(1, 2)),
                                   _sheet_ctx(refusal=sdr.MULTI_SHEET_REFS_UNSUPPORTED, source=None,
                                              sheet=None, page=None), plan)
    assert r.status == sdr.MULTI_SHEET_REFS_UNSUPPORTED and r.ready is False


# --------------------------------------------------------------------------------------------------------- #
# Precondition refusals: no print ref; internally-inconsistent span (footage != station delta).
# --------------------------------------------------------------------------------------------------------- #
def test_no_print_ref_refuses_named(tmp_path):
    plan = _build_plan(tmp_path, start_kind="symbol", end_kind="route")
    r = sdr.reason_structure_datum(_row(sheet_refs=()), _sheet_ctx(source=sdr.SHEET_SOURCE_SHEET_REF), plan)
    assert r.status == sdr.NO_PRINT_SHEET_REF and r.ready is False


def test_footage_span_inconsistent_refuses_named(tmp_path):
    plan = _build_plan(tmp_path, start_kind="symbol", end_kind="route")
    r = sdr.reason_structure_datum(_row(footage=999.0), _sheet_ctx(), plan)   # 999 != (1200-1000)
    assert r.status == sdr.NO_CONFIRMED_SPAN and r.ready is False


# --------------------------------------------------------------------------------------------------------- #
# The reasoner reads the RESOLVED page, not the raw page index: pointing the sheet_context at PDF page 1
# (the front-matter cover, which has no station labels) yields NO datum witness — proving it honored the page.
# --------------------------------------------------------------------------------------------------------- #
def test_reads_resolved_page_not_raw_index(tmp_path):
    plan = _build_plan(tmp_path, start_kind="symbol", end_kind="route")
    on_cover = _sheet_ctx(sheet=1, page=1)                                # offset 0 -> raw page 1 (the cover)
    r = sdr.reason_structure_datum(_row(), on_cover, plan)
    assert r.status == sdr.NO_PRINTED_DATUM_WITNESS                        # nothing on the cover
    on_sheet = _sheet_ctx(sheet=1, page=2)                                # offset 1 -> the real construction sheet
    assert sdr.reason_structure_datum(_row(), on_sheet, plan).ready is True
