"""Phase-1 handwritten/scanned bore-log EXTRACTION tests: the extract/handwritten_borelog.py seam (page
iteration, TEXT_LAYER ladder parsing, the vision-provider seam, and the page ledger), plus the third
(handwritten) tier of extract/borelog_rows.py::extract_rows_from_borelog. Every PDF/image fixture is
generated IN-TEST (PyMuPDF / Pillow, both already-pinned deps) -- no real file is read or referenced.
Generic ids/values only -- no customer/person/project/location strings.
"""
from __future__ import annotations

import io
import time
from pathlib import Path

import pytest

from truelinev2.contracts.extracted_row import OCR, TEXT_PARSE
from truelinev2.contracts.handwritten_extraction import (
    EXTRACTED,
    LOW,
    MEDIUM,
    NOT_PRESENT,
    PAGE_RECORD_FORMAT,
    READ,
    REFUSED,
    TEXT_LAYER,
    VISION_OCR,
)
from truelinev2.extract import borelog_rows as br
from truelinev2.extract.handwritten_borelog import (
    HANDWRITTEN_EXTRACTION_TIMEOUT,
    HANDWRITTEN_NO_USABLE_ROWS,
    HANDWRITTEN_PROVIDER_OUTPUT_INVALID,
    HANDWRITTEN_VISION_PROVIDER_NOT_CONFIGURED,
    TOO_FEW_USABLE_STATIONS,
    _strip_label_prefix,
    build_page_ledger,
    extract_handwritten,
    rasterize_page,
)

AT = "2026-07-10T00:00:00Z"
BY = "op-1"


# --------------------------------------------------------------------------- #
# Synthetic fixture builders -- PDF text-layer pages (PyMuPDF) + a tiny real JPEG (Pillow).
# --------------------------------------------------------------------------- #
def _pdf_bytes(pages_lines) -> bytes:
    """One PDF, one page per ``pages_lines`` entry, each entry a list of text LINES placed top-to-bottom
    (each its own PyMuPDF text span so ``get_text('text')`` recovers them as separate lines)."""
    import fitz

    doc = fitz.open()
    for lines in pages_lines:
        page = doc.new_page(width=612, height=792)
        y = 72
        for line in lines:
            if line is not None:
                page.insert_text((72, y), line, fontsize=10)
            y += 18
    data = doc.tobytes()
    doc.close()
    return data


def _blank_pdf_bytes(page_count=1) -> bytes:
    import fitz

    doc = fitz.open()
    for _ in range(page_count):
        doc.new_page(width=612, height=792)      # no text at all -> no text layer
    data = doc.tobytes()
    doc.close()
    return data


def _pdf_bytes_positioned(pages_items) -> bytes:
    """One PDF, one page per ``pages_items`` entry, each entry a list of ``(x, y, text)`` placements at
    EXPLICIT coordinates -- lets a test put a label and its value in genuinely SEPARATE text runs (the real
    form's actual header-capture failure mode: ``get_text('text')`` does not concatenate them onto one
    line, but their word bboxes are still positionally adjacent)."""
    import fitz

    doc = fitz.open()
    for items in pages_items:
        page = doc.new_page(width=612, height=792)
        for x, y, text in items:
            page.insert_text((x, y), text, fontsize=10)
    data = doc.tobytes()
    doc.close()
    return data


def _jpeg_bytes() -> bytes:
    from PIL import Image

    img = Image.new("RGB", (12, 12), color=(200, 30, 30))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


HEADER_LINES = ["DATE: 6/1/2026", "CREW: JS", "Job Name: Test Loop", "Print #: 29,30,31"]


def _cell(value=None, status=READ, verbatim=None, confidence=MEDIUM, region=None):
    return {"value": value, "verbatim": verbatim, "status": status, "confidence": confidence, "region": region}


def _blank_cell():
    return _cell(value=None, status=NOT_PRESENT, confidence=None)


def _reading(station, depth, boc, *, column_index=0, row_index=0):
    return {
        "station": _cell(station), "depth_ft": _cell(depth), "boc_ft": _cell(boc),
        "column_index": column_index, "row_index": row_index,
    }


def _fake_provider_page(source, *, readings=None, extractor="fake-provider"):
    """A schema-VALID HandwrittenPageExtraction a test's injected fake provider returns."""
    return {
        "record_format": PAGE_RECORD_FORMAT, "source": dict(source), "method": VISION_OCR,
        "extractor": extractor,
        "header": {"date": _blank_cell(), "crew": _blank_cell(),
                  "job_name": _blank_cell(), "print_raw": _blank_cell()},
        "readings": readings or [], "page_status": EXTRACTED, "refusal": None,
        "warnings": [], "audit": [],
    }


# --------------------------------------------------------------------------- #
# TEXT_LAYER parsing -- single-run page.
# --------------------------------------------------------------------------- #
def test_text_layer_single_run_page_yields_one_proposal():
    pdf = _pdf_bytes([HEADER_LINES + ["STA 0+00 3.5 5'", "STA 0+50 3.5 5'", "STA 1+00 3.5 5'"]])
    out = extract_handwritten(pdf, "log.pdf", upload_id="up-1")
    assert len(out["pages"]) == 1
    page = out["pages"][0]
    assert page["method"] == TEXT_LAYER and page["page_status"] == EXTRACTED
    assert page["header"]["date"]["value"] == "6/1/2026"
    assert page["header"]["crew"]["value"] == "JS"
    assert page["header"]["job_name"]["value"] == "Test Loop"
    assert page["header"]["print_raw"]["value"] == "29,30,31"

    assert len(out["proposals"]) == 1
    proposal = out["proposals"][0]
    assert proposal["start_station"] == "0+00" and proposal["end_station"] == "1+00"
    assert proposal["footage_ft"] == pytest.approx(100.0)
    assert proposal["depth_ft"] == pytest.approx(3.5)
    assert proposal["boc_ft"] == pytest.approx(5.0)
    assert proposal["sheet_refs"] == [29, 30, 31]
    assert proposal["footage_derivation"] == "DERIVED_FROM_STATIONS"

    ledger = out["page_ledger"]
    assert len(ledger) == 1
    assert ledger[0] == {"page_index": 0, "status": EXTRACTED, "refusal": None,
                         "warnings": [], "proposal_count": 1, "runs_skipped": []}


def test_text_layer_reset_page_yields_two_sibling_proposals():
    lines = HEADER_LINES + [
        "STA 0+00 3.5 5'", "STA 0+50 3.5 5'", "STA 1+00 3.5 5'",
        "STA 0+00 3.4 4'", "STA 0+30 3.4 4'",
    ]
    out = extract_handwritten(_pdf_bytes([lines]), "log.pdf", upload_id="up-1")
    assert len(out["proposals"]) == 2
    p1, p2 = out["proposals"]
    assert (p1["start_station"], p1["end_station"]) == ("0+00", "1+00")
    assert (p2["start_station"], p2["end_station"]) == ("0+00", "0+30")
    assert out["page_ledger"][0]["proposal_count"] == 2


def test_text_layer_tolerates_sation_misprint_and_sta_variants():
    lines = ["SATION | DEPTH | BOC", "STA 0+00 3.5 5'", "0+50 3.5 5'", "STA. 1+00 3.5 5'", "STA: 1+50 3.5 5'"]
    out = extract_handwritten(_pdf_bytes([lines]), "log.pdf", upload_id="up-1")
    assert len(out["proposals"]) == 1
    proposal = out["proposals"][0]
    assert proposal["start_station"] == "0+00" and proposal["end_station"] == "1+50"


def test_positional_header_same_line_separate_text_runs():
    # The real-form failure mode: label and value are SEPARATE insert_text runs (not one concatenated
    # string), with a genuine gap between them -- a naive per-line regex over get_text('text') can miss
    # this; the positional (word-bbox) capture must not.
    items = [
        (72, 100, "DATE"), (150, 100, "6/1/2026"),
        (72, 120, "CREW"), (150, 120, "JS"),
        (72, 140, "Job"), (105, 140, "Name"), (170, 140, "Test Loop"),
        (72, 160, "Print"), (160, 160, "29,30,31"),
        (72, 200, "STA 0+00 3.5 5'"), (72, 218, "STA 0+50 3.5 5'"), (72, 236, "STA 1+00 3.5 5'"),
    ]
    out = extract_handwritten(_pdf_bytes_positioned([items]), "log.pdf", upload_id="up-1")
    header = out["pages"][0]["header"]
    assert header["date"]["value"] == "6/1/2026" and header["date"]["status"] == READ
    assert header["crew"]["value"] == "JS"
    assert header["job_name"]["value"] == "Test Loop"
    assert header["print_raw"]["value"] == "29,30,31"
    assert len(out["proposals"]) == 1
    assert out["proposals"][0]["sheet_refs"] == [29, 30, 31]


def test_positional_header_value_printed_below_label():
    # Forms vary: some print the value on the line BELOW its label instead of beside it -- a case the old
    # single-line regex approach could never resolve at all.
    items = [
        (72, 100, "DATE"), (72, 118, "6/1/2026"),
        (72, 140, "CREW"), (72, 158, "JS"),
        (72, 180, "Job"), (105, 180, "Name"), (72, 198, "Test Loop"),
        (72, 220, "Print"), (72, 238, "29,30,31"),
        (72, 280, "STA 0+00 3.5 5'"), (72, 298, "STA 0+50 3.5 5'"),
    ]
    out = extract_handwritten(_pdf_bytes_positioned([items]), "log.pdf", upload_id="up-1")
    header = out["pages"][0]["header"]
    assert header["date"]["value"] == "6/1/2026"
    assert header["crew"]["value"] == "JS"
    assert header["job_name"]["value"] == "Test Loop"
    assert header["print_raw"]["value"] == "29,30,31"


def test_page_without_header_still_extracts_ladder_with_fields_not_present():
    lines = ["STA 0+00 3.5 5'", "STA 0+50 3.5 5'", "STA 1+00 3.5 5'"]
    out = extract_handwritten(_pdf_bytes([lines]), "log.pdf", upload_id="up-1")
    header = out["pages"][0]["header"]
    for field in ("date", "crew", "job_name", "print_raw"):
        assert header[field]["status"] == NOT_PRESENT and header[field]["value"] is None
    assert len(out["proposals"]) == 1                        # ladder unaffected by the missing header
    proposal = out["proposals"][0]
    assert proposal["start_station"] == "0+00" and proposal["end_station"] == "1+00"
    assert proposal["date"] is None and proposal["crew"] is None and proposal["notes"] is None


def test_positional_header_same_run_label_value_strips_prefix_keeps_verbatim():
    # "DATE: 2/11/2026" printed as ONE text run (label + value together) -- the value search may pick up
    # the label token along with the date; the normalized value must NOT carry the label, but verbatim
    # (the full captured run) stays intact as evidence.
    lines = ["DATE: 2/11/2026", "STA 0+00 3.5 5'", "STA 0+50 3.5 5'"]
    out = extract_handwritten(_pdf_bytes([lines]), "log.pdf", upload_id="up-1")
    date_cell = out["pages"][0]["header"]["date"]
    assert date_cell["value"] == "2/11/2026"
    assert date_cell["status"] == READ
    assert "DATE" in date_cell["verbatim"] and "2/11/2026" in date_cell["verbatim"]


def test_strip_label_prefix_matching_label_is_removed():
    assert _strip_label_prefix("date", "DATE: 2/11/2026") == "2/11/2026"
    assert _strip_label_prefix("crew", "crew JS") == "JS"
    assert _strip_label_prefix("job_name", "Job Name: Test Loop") == "Test Loop"
    assert _strip_label_prefix("print_raw", "PRINT#: 29,30,31") == "29,30,31"


def test_strip_label_prefix_unrelated_leading_text_unchanged():
    # "DATEX ..." does not spell the DATE label at a word boundary -- must NOT be treated as a prefix match.
    assert _strip_label_prefix("date", "DATEX 5/1/2026") == "DATEX 5/1/2026"
    assert _strip_label_prefix("crew", "Crewman Joe") == "Crewman Joe"


def test_strip_label_prefix_empty_after_strip_is_none():
    assert _strip_label_prefix("date", "DATE:") is None
    assert _strip_label_prefix("date", "  DATE  ") is None


def test_text_layer_descending_only_page_yields_zero_proposals_and_ledger_flags_it():
    lines = HEADER_LINES + ["STA 5+00 3.5 5'", "STA 4+50 3.5 5'", "STA 4+00 3.5 5'"]
    out = extract_handwritten(_pdf_bytes([lines]), "log.pdf", upload_id="up-1")
    assert out["proposals"] == []
    entry = out["page_ledger"][0]
    assert entry["status"] == "NO_USABLE_STATION_RUN"
    assert entry["proposal_count"] == 0
    assert len(entry["runs_skipped"]) == 3
    assert all(r["reason"] == TOO_FEW_USABLE_STATIONS for r in entry["runs_skipped"])
    assert len(entry["warnings"]) == 3
    assert "fewer than 2 usable station readings" in entry["warnings"][0]


# --------------------------------------------------------------------------- #
# Vision-provider seam -- unconfigured / timeout / invalid output / happy path.
# --------------------------------------------------------------------------- #
def test_image_upload_without_provider_refuses_named():
    out = extract_handwritten(_jpeg_bytes(), "photo.jpg", upload_id="up-1")
    assert len(out["pages"]) == 1
    page = out["pages"][0]
    assert page["page_status"] == REFUSED
    assert page["refusal"]["code"] == HANDWRITTEN_VISION_PROVIDER_NOT_CONFIGURED
    assert page["method"] == VISION_OCR
    assert page["source"]["page_index"] == 0 and page["source"]["page_count"] == 1
    assert out["proposals"] == []
    entry = out["page_ledger"][0]
    assert entry["status"] == REFUSED
    assert entry["refusal"]["code"] == HANDWRITTEN_VISION_PROVIDER_NOT_CONFIGURED


def test_image_upload_unknown_provider_name_refuses_named():
    out = extract_handwritten(_jpeg_bytes(), "photo.jpg", upload_id="up-1",
                              provider_name="nope", providers={})
    assert out["pages"][0]["refusal"]["code"] == HANDWRITTEN_VISION_PROVIDER_NOT_CONFIGURED


def test_injected_fake_provider_happy_path_produces_ocr_page():
    def _fake(png_bytes, context):
        assert isinstance(png_bytes, (bytes, bytearray)) and png_bytes
        source = {"upload_id": context["upload_id"], "sha256": "a" * 64,
                 "file_name": context["file_name"], "page_index": context["page_index"],
                 "page_count": context["page_count"]}
        readings = [_reading("0+00", 3.5, 5.0, row_index=0), _reading("0+50", 3.5, 5.0, row_index=1)]
        return _fake_provider_page(source, readings=readings)

    out = extract_handwritten(_jpeg_bytes(), "photo.jpg", upload_id="up-1",
                              provider_name="fake", providers={"fake": _fake})
    page = out["pages"][0]
    assert page["page_status"] == EXTRACTED and page["method"] == VISION_OCR
    assert len(out["proposals"]) == 1
    assert out["page_ledger"][0]["status"] == EXTRACTED


def test_injected_fake_provider_timeout_refuses_named():
    def _slow(png_bytes, context):
        time.sleep(1.0)
        return _fake_provider_page({"upload_id": "up-1", "sha256": "a" * 64, "file_name": "photo.jpg",
                                    "page_index": 0, "page_count": 1})

    out = extract_handwritten(_jpeg_bytes(), "photo.jpg", upload_id="up-1",
                              provider_name="slow", providers={"slow": _slow}, timeout_s=0.05)
    assert out["pages"][0]["refusal"]["code"] == HANDWRITTEN_EXTRACTION_TIMEOUT


def test_injected_fake_provider_invalid_output_refuses_named():
    def _bad(png_bytes, context):
        return {"not": "a valid record"}

    out = extract_handwritten(_jpeg_bytes(), "photo.jpg", upload_id="up-1",
                              provider_name="bad", providers={"bad": _bad})
    assert out["pages"][0]["refusal"]["code"] == HANDWRITTEN_PROVIDER_OUTPUT_INVALID


def test_injected_fake_provider_raising_refuses_as_invalid_output():
    def _raises(png_bytes, context):
        raise RuntimeError("boom")

    out = extract_handwritten(_jpeg_bytes(), "photo.jpg", upload_id="up-1",
                              provider_name="raises", providers={"raises": _raises})
    assert out["pages"][0]["refusal"]["code"] == HANDWRITTEN_PROVIDER_OUTPUT_INVALID


# --------------------------------------------------------------------------- #
# rasterize_page -- shared PDF-page PNG helper.
# --------------------------------------------------------------------------- #
def test_rasterize_page_returns_png_bytes_and_none_out_of_range():
    pdf = _pdf_bytes([["hello"], ["world"]])
    png = rasterize_page(pdf, 0)
    assert png is not None and png[:8] == b"\x89PNG\r\n\x1a\n"
    assert rasterize_page(pdf, 5) is None
    assert rasterize_page(b"not a pdf", 0) is None


def test_pdf_page_with_no_text_layer_needs_vision():
    out = extract_handwritten(_blank_pdf_bytes(1), "scan.pdf", upload_id="up-1")
    page = out["pages"][0]
    assert page["method"] == VISION_OCR
    assert page["page_status"] == REFUSED
    assert page["refusal"]["code"] == HANDWRITTEN_VISION_PROVIDER_NOT_CONFIGURED


# --------------------------------------------------------------------------- #
# build_page_ledger -- direct unit coverage (every page accounted for exactly once).
# --------------------------------------------------------------------------- #
def test_build_page_ledger_covers_every_page_exactly_once():
    src0 = {"upload_id": "up-1", "sha256": "a" * 64, "file_name": "f.pdf", "page_index": 0, "page_count": 2}
    src1 = {"upload_id": "up-1", "sha256": "a" * 64, "file_name": "f.pdf", "page_index": 1, "page_count": 2}
    extracted_page = {
        "record_format": PAGE_RECORD_FORMAT, "source": src0, "method": TEXT_LAYER, "extractor": "x",
        "header": {"date": _blank_cell(), "crew": _blank_cell(), "job_name": _blank_cell(),
                  "print_raw": _blank_cell()},
        "readings": [_reading("0+00", 3.5, 5.0, row_index=0), _reading("0+50", 3.5, 5.0, row_index=1)],
        "page_status": EXTRACTED, "refusal": None, "warnings": [], "audit": [],
    }
    refused_page = {
        "record_format": PAGE_RECORD_FORMAT, "source": src1, "method": VISION_OCR, "extractor": "y",
        "header": {"date": _blank_cell(), "crew": _blank_cell(), "job_name": _blank_cell(),
                  "print_raw": _blank_cell()},
        "readings": [], "page_status": REFUSED,
        "refusal": {"code": HANDWRITTEN_VISION_PROVIDER_NOT_CONFIGURED, "reason": "no provider"},
        "warnings": [], "audit": [],
    }
    from truelinev2.contracts.handwritten_extraction import spans_from_page

    proposals_by_page = {0: spans_from_page(extracted_page), 1: spans_from_page(refused_page)}
    ledger = build_page_ledger([extracted_page, refused_page], proposals_by_page)
    assert [e["page_index"] for e in ledger] == [0, 1]
    assert ledger[0]["status"] == EXTRACTED and ledger[0]["proposal_count"] == 1
    assert ledger[1]["status"] == REFUSED
    assert ledger[1]["refusal"]["code"] == HANDWRITTEN_VISION_PROVIDER_NOT_CONFIGURED


# --------------------------------------------------------------------------- #
# extract/borelog_rows.py -- the third (handwritten) tier.
# --------------------------------------------------------------------------- #
def _handwritten_extractor(providers=None, provider_name=None):
    def _fn(path: Path):
        return extract_handwritten(path.read_bytes(), path.name, upload_id="up-1",
                                   provider_name=provider_name, providers=providers)
    return _fn


def test_flag_off_default_none_reraises_generic_refusal_unchanged(tmp_path):
    # A text-layer ladder PDF is NOT a recognized named/generic bore-log format -> both tier 1 + tier 2
    # refuse; handwritten_extractor=None (the default) means the SAME BORE_LOG_FORMAT_UNRECOGNIZED refusal
    # propagates, byte-identical to before this evolution.
    pdf_path = tmp_path / "log.pdf"
    pdf_path.write_bytes(_pdf_bytes([HEADER_LINES + ["STA 0+00 3.5 5'", "STA 0+50 3.5 5'"]]))
    with pytest.raises(br.BoreLogExtractionError) as exc:
        br.extract_rows_from_borelog(pdf_path, "up-1", at=AT, by=BY)
    assert br.BORE_LOG_FORMAT_UNRECOGNIZED in str(exc.value)
    assert getattr(exc.value, "page_ledger", None) is None


def test_handwritten_tier_maps_text_layer_to_text_parse_rows(tmp_path):
    pdf_path = tmp_path / "log.pdf"
    pdf_path.write_bytes(_pdf_bytes([HEADER_LINES + ["STA 0+00 3.5 5'", "STA 0+50 3.5 5'", "STA 1+00 3.5 5'"]]))
    rows = br.extract_rows_from_borelog(pdf_path, "up-1", at=AT, by=BY,
                                        handwritten_extractor=_handwritten_extractor())
    assert len(rows) == 1
    row = rows[0]
    assert row["extraction"]["extraction_method"] == TEXT_PARSE
    assert row["raw"]["start_station"] == "0+00" and row["raw"]["end_station"] == "1+00"
    assert row["raw"]["footage_derivation"] == "DERIVED_FROM_STATIONS"
    assert "station_readings" in row["raw"]
    assert row["extraction"]["source_evidence"]["page_index"] == 0
    ledger = getattr(rows, "page_ledger", None)
    assert ledger is not None and ledger[0]["proposal_count"] == 1


def test_handwritten_tier_maps_vision_ocr_to_ocr_extraction_method(tmp_path):
    def _fake(png_bytes, context):
        source = {"upload_id": context["upload_id"], "sha256": "a" * 64, "file_name": context["file_name"],
                 "page_index": context["page_index"], "page_count": context["page_count"]}
        readings = [_reading("0+00", 3.5, 5.0, row_index=0), _reading("0+50", 3.5, 5.0, row_index=1)]
        return _fake_provider_page(source, readings=readings)

    img_path = tmp_path / "photo.jpg"
    img_path.write_bytes(_jpeg_bytes())
    rows = br.extract_rows_from_borelog(
        img_path, "up-1", at=AT, by=BY,
        handwritten_extractor=_handwritten_extractor(providers={"fake": _fake}, provider_name="fake"))
    assert len(rows) == 1
    assert rows[0]["extraction"]["extraction_method"] == OCR


def test_handwritten_tier_zero_proposals_raises_with_ledger_attached(tmp_path):
    pdf_path = tmp_path / "log.pdf"
    pdf_path.write_bytes(_pdf_bytes([HEADER_LINES + ["STA 5+00 3.5 5'", "STA 4+50 3.5 5'"]]))
    with pytest.raises(br.BoreLogExtractionError) as exc:
        br.extract_rows_from_borelog(pdf_path, "up-1", at=AT, by=BY,
                                     handwritten_extractor=_handwritten_extractor())
    assert HANDWRITTEN_NO_USABLE_ROWS in str(exc.value)
    ledger = getattr(exc.value, "page_ledger", None)
    assert ledger is not None and ledger[0]["status"] == "NO_USABLE_STATION_RUN"


# --------------------------------------------------------------------------- #
# Adapter chain lock (Wave-1 preflight, already covered by test_reviewed_bore_engine_adapter.py's own
# OCR_ROW_REQUIRES_EXPLICIT_FOOTAGE cases) -- confirm THIS tier's extraction_method wiring actually feeds
# that preflight the value it keys on.
# --------------------------------------------------------------------------- #
def test_ocr_extraction_method_feeds_the_existing_footage_preflight(tmp_path):
    from truelinev2.contracts.extracted_row import CONFIRMED, review_row
    from truelinev2.contracts.reviewed_bore_adapter import (
        OCR_ROW_REQUIRES_EXPLICIT_FOOTAGE,
        bore_from_reviewed_rows,
    )

    def _fake(png_bytes, context):
        source = {"upload_id": context["upload_id"], "sha256": "a" * 64, "file_name": context["file_name"],
                 "page_index": context["page_index"], "page_count": context["page_count"]}
        readings = [_reading("0+00", 3.5, 5.0, row_index=0), _reading("1+50", 3.5, 5.0, row_index=1)]
        return _fake_provider_page(source, readings=readings)

    img_path = tmp_path / "photo.jpg"
    img_path.write_bytes(_jpeg_bytes())
    rows = br.extract_rows_from_borelog(
        img_path, "up-1", at=AT, by=BY,
        handwritten_extractor=_handwritten_extractor(providers={"fake": _fake}, provider_name="fake"))
    row = rows[0]
    assert row["extraction"]["extraction_method"] == OCR
    # No explicit "footage" key in raw (only footage_ft, the derived span-normalizer key -- not a recognized
    # alias) -> the adapter's OCR-only preflight declines rather than deriving from the station delta.
    review_row(row, CONFIRMED, at=AT, by=BY)
    rbl = {"record_format": "trueline-reviewed-bore-log-1", "reviewed_bore_log_id": "rbl-x",
          "customer_project_id": "cp-1", "processing_job_id": "job-1", "source_upload_id": "up-1",
          "rows": [row],
          "groups": [{"group_id": "g-1", "member_row_ids": [row["row_id"]], "relation": "SEPARATE_BORE",
                     "grouping_status": "CONFIRMED", "reason": None, "audit": []}],
          "audit": []}
    bore, reason = bore_from_reviewed_rows(rbl, source_filename="photo.jpg")
    assert bore is None and reason == OCR_ROW_REQUIRES_EXPLICIT_FOOTAGE

    # Now CORRECTED with an explicit footage value -> passes.
    row2 = rows2 = br.extract_rows_from_borelog(
        img_path, "up-1", at=AT, by=BY, existing_row_ids=(),
        handwritten_extractor=_handwritten_extractor(providers={"fake": _fake}, provider_name="fake"))[0]
    review_row(row2, CONFIRMED, at=AT, by=BY, corrected_values={"footage": "150"})
    rbl2 = dict(rbl, rows=[row2],
               groups=[{"group_id": "g-1", "member_row_ids": [row2["row_id"]], "relation": "SEPARATE_BORE",
                       "grouping_status": "CONFIRMED", "reason": None, "audit": []}])
    bore2, reason2 = bore_from_reviewed_rows(rbl2, source_filename="photo.jpg")
    assert bore2 is not None and bore2.span_ft == pytest.approx(150.0)
