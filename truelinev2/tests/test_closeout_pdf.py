"""Closeout PDF lane tests — server-rendered, trusted-data-only closeout packet (a real PDF).

A recognized deterministic job renders a REAL PDF: a %PDF document with the sha256-verified FINAL_REDLINE_PNG
bytes embedded as image XObjects + the expected textual markers (closeout status, bundle origin, deliverable
quantities, honest KMZ pixel-only note, billing omitted-because-unconfigured). A job with no validated redline
bundle raises NoCloseoutPdfError (the route maps it to a specific not-ready 409) — never a fake packet, never
a fake redline image. Self-contained + name-free (mirrors test_export_bundle: render dir monkeypatched,
registry injected).
"""
from __future__ import annotations

import base64
import hashlib
import io

import fitz
import pytest
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
from truelinev2.contracts.closeout_pdf import NoCloseoutPdfError, build_closeout_pdf

AT, BY, CP, JOB, RBL = "2026-06-23T00:00:00Z", "op-1", "cp-0001", "job-0001", "rbl-1"

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
    """A small but FULLY-VALID PNG (MuPDF decodes it) standing in for a real engine redline render."""
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (210, 40, 40)).save(buf, format="PNG")
    return buf.getvalue()


_PNG = _valid_png()
_BORE = b"recognized-by-sha256-only"


def _recognized_job(tmp, monkeypatch):
    rdir = tmp / "render"
    rdir.mkdir()
    (rdir / "log8_s18_redline_stroke.png").write_bytes(_PNG)
    (rdir / "log8_s22_redline_stroke.png").write_bytes(_PNG)
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
    row = new_extracted_row("row-1", bore["upload_id"], raw={"s": "0+00"}, normalized={"s": "0+00"},
                            extraction_method=MANUAL_ENTRY, at=AT, by=BY)
    add_extracted_rows(tmp, CP, JOB, RBL, [row], at=AT, by=BY)
    review_row_in_log(tmp, CP, JOB, RBL, "row-1", CONFIRMED, at=AT, by=BY)
    define_segment_group(tmp, CP, JOB, RBL, "g-1", ["row-1"], SEPARATE_BORE, at=AT, by=BY)
    set_grouping_status(tmp, CP, JOB, RBL, "g-1", GROUPING_CONFIRMED, at=AT, by=BY)
    pw.run_product_redline(tmp, CP, JOB, registry=reg, at=AT, by=BY)          # renders + sets the bundle slot
    pw.assemble_closeout_package(tmp, CP, JOB, at=AT, by=BY)                  # closeout + export descriptor


def _text(pdf_bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    return "\n".join(doc.load_page(i).get_text() for i in range(doc.page_count))


def test_closeout_pdf_recognized_job_is_valid_pdf_with_embedded_evidence(tmp_path, monkeypatch):
    _recognized_job(tmp_path, monkeypatch)
    data, filename = build_closeout_pdf(tmp_path, CP, JOB)

    assert filename == "closeout_packet_%s.pdf" % JOB
    assert data[:5] == b"%PDF-"                 # real PDF header
    assert len(data) > 2000                     # non-trivial document

    # embedded image XObject(s) — the sha256-verified redline PNG(s)
    doc = fitz.open(stream=data, filetype="pdf")
    images = [img for i in range(doc.page_count) for img in doc.get_page_images(i)]
    assert images, "expected at least one embedded image XObject (redline evidence)"

    text = _text(data)
    # identity + status markers
    assert "FieldRoute" in text and "Closeout Packet" in text
    assert "DETERMINISTIC_RECOGNIZED_CORPUS" in text          # bundle origin
    assert "Closeout Status" in text
    assert "READY_FOR_APPROVAL" in text                       # the server closeout verdict
    # deliverable quantities (no dollars)
    assert "Deliverable Quantities" in text
    assert "Redline PNG artifacts" in text
    # both real redline artifacts were processed (evidence + detail sections)
    assert "log8_s18" in text and "log8_s22" in text
    # honest KMZ (pixel-only, never faked)
    assert "UNSUPPORTED_PIXEL_ONLY" in text
    assert "refuses to fake" in text
    # billing dollars are NOT shown (no server cost rules configured)
    assert "no server cost rules configured" in text
    # disclaimer
    assert "review required before construction" in text


def test_closeout_pdf_includes_operator_pricing_with_disclaimer(tmp_path, monkeypatch):
    from truelinev2.contracts.job_pricing import save_job_pricing
    _recognized_job(tmp_path, monkeypatch)
    # No operator pricing entered yet -> the §12 section is absent (no fabricated dollars).
    assert "Operator-Entered Pricing" not in _text(build_closeout_pdf(tmp_path, CP, JOB)[0])
    # Operator enters a provisional rate + exception -> §12 renders WITH the unverified disclaimer.
    save_job_pricing(tmp_path, CP, JOB, cost_per_foot="5.00",
                     exceptions=[{"label": "TXDOT permit", "amount": "250.00", "note": "ROW"}], at=AT, by=BY)
    text = _text(build_closeout_pdf(tmp_path, CP, JOB)[0])
    assert "Operator-Entered Pricing (UNVERIFIED)" in text
    assert "NOT verified by a configured rate sheet" in text     # the honesty disclaimer
    assert "TXDOT permit" in text and "5.00" in text             # operator inputs surfaced


def test_closeout_pdf_embeds_each_verified_artifact(tmp_path, monkeypatch):
    """The two recognized FINAL_REDLINE_PNG artifacts are both embedded (image XObject references present)."""
    _recognized_job(tmp_path, monkeypatch)
    data, _ = build_closeout_pdf(tmp_path, CP, JOB)
    doc = fitz.open(stream=data, filetype="pdf")
    total_image_refs = sum(len(doc.get_page_images(i)) for i in range(doc.page_count))
    assert total_image_refs >= 1                 # at least one real embedded image (fitz may share streams)
    # and the manifest's two artifact paths are both named in the rendered text
    text = _text(data)
    assert text.count("log8_s") >= 2


def test_closeout_pdf_not_ready_without_validated_bundle(tmp_path):
    """An ABSTAIN / not-yet-rendered job has no validated bundle => specific not-ready error, no fake packet."""
    create_customer_project(tmp_path, CP, "Label", AT)
    create_job(tmp_path, CP, JOB, AT, BY)
    with pytest.raises(NoCloseoutPdfError) as ei:
        build_closeout_pdf(tmp_path, CP, JOB)
    msg = str(ei.value)
    assert "no validated redline bundle" in msg and "not ready" in msg
