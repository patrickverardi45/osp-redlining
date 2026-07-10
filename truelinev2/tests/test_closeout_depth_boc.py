"""Closeout PDF — additive per-row depth/BOC carry-through (contract-only; source-backed only, never invented).

Section 6 ("Reviewed Bore-Log Summary") of the closeout packet lists one line per human-REVIEWED
(CONFIRMED/CORRECTED) row: station span + footage always, plus depth/BOC WHEN the row's own effective
values (raw < normalized < corrected_values) actually carry them. A row with no depth/BOC column shows
NEITHER — never a fabricated zero or placeholder. Self-contained + name-free, mirrors test_closeout_pdf.py's
recognized-job fixture (a validated redline bundle is required before build_closeout_pdf will render at all).
"""
from __future__ import annotations

import base64
import hashlib
import io

import fitz
from PIL import Image

from truelinev2.contracts.customer_project import create_customer_project
from truelinev2.contracts.processing_job import create_job
from truelinev2.contracts.upload_pipeline import accept_upload
from truelinev2.contracts.extracted_row import CONFIRMED, MANUAL_ENTRY, new_extracted_row
from truelinev2.contracts.reviewed_bore_log import (
    GROUPING_CONFIRMED, SEPARATE_BORE, add_extracted_rows, create_reviewed_bore_log,
    define_segment_group, review_row_in_log, set_grouping_status,
)
from truelinev2.contracts import recognized_corpus_handoff as rch
from truelinev2.contracts import product_workflow as pw
from truelinev2.contracts.closeout_pdf import build_closeout_pdf

AT, BY, CP, JOB, RBL = "2026-06-23T00:00:00Z", "op-1", "cp-dep1", "job-dep1", "rbl-1"

_PDF = base64.b64decode(
    "JVBERi0xLjcKJcK1wrYKJSBXcml0dGVuIGJ5IE11UERGIDEuMjcuMgoKMSAwIG9iago8PC9UeXBlL0NhdGFsb2cvUGFnZXMg"
    "MiAwIFIvSW5mbzw8L1Byb2R1Y2VyKE11UERGIDEuMjcuMik+Pj4+CmVuZG9iagoKMiAwIG9iago8PC9UeXBlL1BhZ2VzL0Nv"
    "dW50IDEvS2lkc1s0IDAgUl0+PgplbmRvYmoKCjMgMCBvYmoKPDw+PgplbmRvYmoKCjQgMCBvYmoKPDwvVHlwZS9QYWdlL01l"
    "ZGlhQm94WzAgMCA2MTIgNzkyXS9Sb3RhdGUgMC9SZXNvdXJjZXMgMyAwIFIvUGFyZW50IDIgMCBSPj4KZW5kb2JqCgp4cmVm"
    "CjAgNQowMDAwMDAwMDAwIDY1NTM1IGYgCjAwMDAwMDAwNDIgMDAwMDAgbiAKMDAwMDAwMDEyMCAwMDAwMCBuIAowMDAwMDAw"
    "MTcyIDAwMDAwIG4gCjAwMDAwMDAxOTMgMDAwMDAgbiAKCnRyYWlsZXIKPDwvU2l6ZSA1L1Jvb3QgMSAwIFIvSURbPDI1QzNB"
    "MjRFNEVDMjgwQzJBQzY1QzM4NEMzQTJDMjg1PjwxQjAyRUMzMkUxRDMwNUYzNDJBRjZFMjI2MkYzNTZDND5dPj4Kc3RhcnR4"
    "cmVmCjI4NAolJUVPRgo=")


def _valid_png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (210, 40, 40)).save(buf, format="PNG")
    return buf.getvalue()


_PNG = _valid_png()
_BORE = b"recognized-by-sha256-only-depth-boc"


def _job_with_rows(tmp, monkeypatch):
    """A recognized-lane job (so a validated bundle exists) carrying TWO reviewed rows in the SAME
    reviewed_bore_log: one row with source-backed depth_min_ft/boc_min_ft, one row with neither."""
    rdir = tmp / "render"
    rdir.mkdir()
    (rdir / "log8_s18_redline_stroke.png").write_bytes(_PNG)
    monkeypatch.setattr(rch, "_DETERMINISTIC_RENDER_DIR", rdir)
    reg = {"corpora": [{"corpus_id": "recognized-corpus-001", "display_name": "Test Corpus",
                        "plan_sha256": [hashlib.sha256(_PDF).hexdigest()],
                        "bore_log_sha256_to_log": {hashlib.sha256(_BORE).hexdigest(): "log8"},
                        "log_facts": {}}], "configured": True}
    create_customer_project(tmp, CP, "Label", AT)
    create_job(tmp, CP, JOB, AT, BY)
    accept_upload(tmp, CP, JOB, kind="PLAN_PDF", filename="plan.pdf", content=_PDF, stored_at=AT)
    bore = accept_upload(tmp, CP, JOB, kind="BORE_LOG", filename="bore_log8.xlsx", content=_BORE, stored_at=AT)
    create_reviewed_bore_log(tmp, CP, JOB, bore["upload_id"], RBL, at=AT, by=BY)

    # row-1: source carries depth/BOC (the generic extractor's own keys -- depth_min_ft/boc_min_ft).
    row1 = new_extracted_row(
        "row-1", bore["upload_id"],
        raw={"start_station": "5+03", "end_station": "6+79", "footage_ft": 176.0,
            "depth_min_ft": 42.0, "boc_min_ft": 48.0},
        normalized={"start_station": "5+03", "end_station": "6+79"},
        extraction_method=MANUAL_ENTRY, at=AT, by=BY)
    # row-2: no depth/BOC column at all -- must show neither.
    row2 = new_extracted_row(
        "row-2", bore["upload_id"],
        raw={"start_station": "9+00", "end_station": "9+50", "footage_ft": 50.0},
        normalized={"start_station": "9+00", "end_station": "9+50"},
        extraction_method=MANUAL_ENTRY, at=AT, by=BY)
    add_extracted_rows(tmp, CP, JOB, RBL, [row1, row2], at=AT, by=BY)
    review_row_in_log(tmp, CP, JOB, RBL, "row-1", CONFIRMED, at=AT, by=BY)
    review_row_in_log(tmp, CP, JOB, RBL, "row-2", CONFIRMED, at=AT, by=BY)
    define_segment_group(tmp, CP, JOB, RBL, "g-1", ["row-1", "row-2"], SEPARATE_BORE, at=AT, by=BY)
    set_grouping_status(tmp, CP, JOB, RBL, "g-1", GROUPING_CONFIRMED, at=AT, by=BY)

    pw.run_product_redline(tmp, CP, JOB, registry=reg, at=AT, by=BY)
    pw.assemble_closeout_package(tmp, CP, JOB, at=AT, by=BY)


def _text(pdf_bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    return "\n".join(doc.load_page(i).get_text() for i in range(doc.page_count))


def test_row_with_depth_and_boc_shows_both(tmp_path, monkeypatch):
    _job_with_rows(tmp_path, monkeypatch)
    text = _text(build_closeout_pdf(tmp_path, CP, JOB)[0])
    assert "5+03" in text and "6+79" in text
    assert "depth 42.0 ft" in text
    assert "BOC 48.0 ft" in text


def test_row_without_depth_or_boc_shows_neither(tmp_path, monkeypatch):
    _job_with_rows(tmp_path, monkeypatch)
    text = _text(build_closeout_pdf(tmp_path, CP, JOB)[0])
    assert "9+00" in text and "9+50" in text
    # row-2's own line must not claim a depth/BOC it never had -- scope the check to that row's line.
    lines = [ln for ln in text.split("\n") if "9+00" in ln and "9+50" in ln]
    assert lines, "expected row-2's summary line in the rendered text"
    for ln in lines:
        assert "depth" not in ln and "BOC" not in ln
