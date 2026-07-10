"""Phase-1 handwritten/scanned bore-log ROUTE tests: flag-OFF byte-identity, the /extract fan-out response
(created_reviewed_bore_logs + page_ledger), the row-review CONFIRMED/CORRECTED matrix, and the flag-gated
source-page byte-serving route (mounting + 404 matrix + PNG happy path). Follows the repo API-test
convention (mirrors test_product_pipeline_api.py): NO httpx/TestClient — route functions are called
DIRECTLY with an explicit RequestContext. Every PDF/image fixture is generated IN-TEST. Generic ids only.
"""
from __future__ import annotations

import base64
import dataclasses
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.routing import APIRoute

from truelinev2.api import product_pipeline_routes as ppr
from truelinev2.api.app import create_app
from truelinev2.config import Settings
from truelinev2.context import require_context
from truelinev2.contracts.extracted_row import CONFIRMED, CORRECTED
from truelinev2.contracts.upload_pipeline import RejectedExtensionError

HEADER_LINES = ["DATE: 6/1/2026", "CREW: JS", "Job Name: Test Loop", "Print #: 29,30,31"]


def _pdf_bytes(pages_lines) -> bytes:
    import fitz

    doc = fitz.open()
    for lines in pages_lines:
        page = doc.new_page(width=612, height=792)
        y = 72
        for line in lines:
            page.insert_text((72, y), line, fontsize=10)
            y += 18
    data = doc.tobytes()
    doc.close()
    return data


def _jpeg_bytes() -> bytes:
    from PIL import Image
    import io

    img = Image.new("RGB", (12, 12), color=(200, 30, 30))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _settings(tmp_path: Path, *, handwritten: bool, pipeline: bool = True) -> Settings:
    return dataclasses.replace(
        Settings.for_proof(),
        artifact_root=tmp_path / "artifacts",
        cards_dir=tmp_path / "cards",
        db_path=tmp_path / "truelinev2.db",
        product_pipeline_api_optin=pipeline,
        product_store_root=tmp_path / "product_store",
        handwritten_borelog_extraction_optin=handwritten,
    )


def _container(tmp_path: Path, *, handwritten: bool, pipeline: bool = True):
    return create_app(_settings(tmp_path, handwritten=handwritten, pipeline=pipeline)).state.tl2


def _ctx(tenant: str, session: str = "sess-1"):
    return require_context(tenant, session)


def _job(c, ctx, job_id="job-1"):
    ppr.create_project(ppr.ProjectCreate(display_name="L"), ctx=ctx, c=c)
    ppr.create_processing_job(ppr.JobCreate(job_id=job_id), ctx=ctx, c=c)


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


# --------------------------------------------------------------------------- #
# Mounting.
# --------------------------------------------------------------------------- #
def test_borelog_source_route_not_mounted_when_flag_off(tmp_path):
    app = create_app(_settings(tmp_path, handwritten=False))
    assert not any(r.path.endswith("/borelog-source") for r in app.routes if isinstance(r, APIRoute))


def test_borelog_source_route_mounted_when_flag_on(tmp_path):
    app = create_app(_settings(tmp_path, handwritten=True))
    paths = {r.path for r in app.routes if isinstance(r, APIRoute)}
    assert "/v2/product/jobs/{job_id}/uploads/{upload_id}/borelog-source" in paths


def test_borelog_source_route_not_mounted_without_product_pipeline_api(tmp_path):
    # handwritten alone, without the product pipeline mounted, must not mount either router.
    app = create_app(_settings(tmp_path, handwritten=True, pipeline=False))
    assert not any(r.path.startswith("/v2/product") for r in app.routes if isinstance(r, APIRoute))


# --------------------------------------------------------------------------- #
# Upload accept — flag-OFF byte-identity (image BORE_LOG upload stays rejected).
# --------------------------------------------------------------------------- #
def test_flag_off_image_borelog_upload_rejected_400(tmp_path):
    c, ctx = _container(tmp_path, handwritten=False), _ctx("cp-aaa")
    _job(c, ctx)
    with pytest.raises(HTTPException) as exc:
        ppr.register_upload("job-1", ppr.UploadRegister(
            kind="BORE_LOG", filename="photo.jpg", content_base64=_b64(_jpeg_bytes())), ctx=ctx, c=c)
    assert exc.value.status_code == 400


def test_flag_on_image_borelog_upload_accepted(tmp_path):
    c, ctx = _container(tmp_path, handwritten=True), _ctx("cp-aaa")
    _job(c, ctx)
    rec = ppr.register_upload("job-1", ppr.UploadRegister(
        kind="BORE_LOG", filename="photo.jpg", content_base64=_b64(_jpeg_bytes())), ctx=ctx, c=c)
    assert rec["kind"] == "BORE_LOG"


def test_flag_off_text_layer_pdf_extract_refusal_unchanged(tmp_path):
    c, ctx = _container(tmp_path, handwritten=False), _ctx("cp-aaa")
    _job(c, ctx)
    pdf = _pdf_bytes([HEADER_LINES + ["STA 0+00 3.5 5'", "STA 0+50 3.5 5'"]])
    up = ppr.register_upload("job-1", ppr.UploadRegister(
        kind="BORE_LOG", filename="log.pdf", content_base64=_b64(pdf)), ctx=ctx, c=c)
    ppr.create_bore_log_review("job-1", ppr.ReviewedBoreLogCreate(
        reviewed_bore_log_id="rbl-1", source_upload_id=up["upload_id"]), ctx=ctx, c=c)
    with pytest.raises(HTTPException) as exc:
        ppr.extract_bore_log_rows_route("job-1", "rbl-1", ctx=ctx, c=c)
    assert exc.value.status_code == 400
    assert isinstance(exc.value.detail, str)                 # unchanged shape: a plain string, no page_ledger
    assert "BORE_LOG_FORMAT_UNRECOGNIZED" in exc.value.detail


# --------------------------------------------------------------------------- #
# /extract — Phase-1 fan-out (flag ON, both prior tiers refuse).
# --------------------------------------------------------------------------- #
def test_extract_single_run_page_fans_out_one_rbl(tmp_path):
    c, ctx = _container(tmp_path, handwritten=True), _ctx("cp-aaa")
    _job(c, ctx)
    pdf = _pdf_bytes([HEADER_LINES + ["STA 0+00 3.5 5'", "STA 0+50 3.5 5'", "STA 1+00 3.5 5'"]])
    up = ppr.register_upload("job-1", ppr.UploadRegister(
        kind="BORE_LOG", filename="log.pdf", content_base64=_b64(pdf)), ctx=ctx, c=c)
    ppr.create_bore_log_review("job-1", ppr.ReviewedBoreLogCreate(
        reviewed_bore_log_id="rbl-1", source_upload_id=up["upload_id"]), ctx=ctx, c=c)
    out = ppr.extract_bore_log_rows_route("job-1", "rbl-1", ctx=ctx, c=c)
    assert out["extracted_count"] == 1
    assert len(out["page_ledger"]) == 1 and out["page_ledger"][0]["proposal_count"] == 1
    created = out["created_reviewed_bore_logs"]
    assert created == [{
        "reviewed_bore_log_id": "rbl-hw-p0-r1", "source_upload_id": up["upload_id"],
        "row_id": created[0]["row_id"], "page_index": 0, "run_index": 1,
    }]
    # The URL-level reviewed_bore_log itself stays empty; the sibling carries the row.
    original = ppr.get_reviewed_bore_log_record("job-1", "rbl-1", ctx=ctx, c=c)
    assert original["rows"] == []
    sibling = ppr.get_reviewed_bore_log_record("job-1", "rbl-hw-p0-r1", ctx=ctx, c=c)
    assert len(sibling["rows"]) == 1
    assert sibling["rows"][0]["extraction"]["extraction_method"] == "TEXT_PARSE"


def test_extract_reset_page_fans_out_two_sibling_rbls_with_created_field(tmp_path):
    c, ctx = _container(tmp_path, handwritten=True), _ctx("cp-aaa")
    _job(c, ctx)
    lines = HEADER_LINES + [
        "STA 0+00 3.5 5'", "STA 0+50 3.5 5'", "STA 1+00 3.5 5'",
        "STA 0+00 3.4 4'", "STA 0+30 3.4 4'",
    ]
    pdf = _pdf_bytes([lines])
    up = ppr.register_upload("job-1", ppr.UploadRegister(
        kind="BORE_LOG", filename="log.pdf", content_base64=_b64(pdf)), ctx=ctx, c=c)
    ppr.create_bore_log_review("job-1", ppr.ReviewedBoreLogCreate(
        reviewed_bore_log_id="rbl-1", source_upload_id=up["upload_id"]), ctx=ctx, c=c)
    out = ppr.extract_bore_log_rows_route("job-1", "rbl-1", ctx=ctx, c=c)
    assert out["extracted_count"] == 2
    created = out["created_reviewed_bore_logs"]
    assert [c_["reviewed_bore_log_id"] for c_ in created] == ["rbl-hw-p0-r1", "rbl-hw-p0-r2"]
    assert [c_["run_index"] for c_ in created] == [1, 2]
    assert all(c_["page_index"] == 0 for c_ in created)
    assert all(c_["source_upload_id"] == up["upload_id"] for c_ in created)
    # Each sibling carries exactly its own one row — the review gate's single-eligible-row scope intact.
    for c_ in created:
        rbl = ppr.get_reviewed_bore_log_record("job-1", c_["reviewed_bore_log_id"], ctx=ctx, c=c)
        assert len(rbl["rows"]) == 1 and rbl["rows"][0]["row_id"] == c_["row_id"]


def test_extract_descending_only_page_400_with_page_ledger_detail(tmp_path):
    c, ctx = _container(tmp_path, handwritten=True), _ctx("cp-aaa")
    _job(c, ctx)
    pdf = _pdf_bytes([HEADER_LINES + ["STA 5+00 3.5 5'", "STA 4+50 3.5 5'"]])
    up = ppr.register_upload("job-1", ppr.UploadRegister(
        kind="BORE_LOG", filename="log.pdf", content_base64=_b64(pdf)), ctx=ctx, c=c)
    ppr.create_bore_log_review("job-1", ppr.ReviewedBoreLogCreate(
        reviewed_bore_log_id="rbl-1", source_upload_id=up["upload_id"]), ctx=ctx, c=c)
    with pytest.raises(HTTPException) as exc:
        ppr.extract_bore_log_rows_route("job-1", "rbl-1", ctx=ctx, c=c)
    assert exc.value.status_code == 400
    assert isinstance(exc.value.detail, dict)
    assert "HANDWRITTEN_NO_USABLE_ROWS" in exc.value.detail["message"]
    assert exc.value.detail["page_ledger"][0]["status"] == "NO_USABLE_STATION_RUN"


# --------------------------------------------------------------------------- #
# Row-review matrix (CONFIRMED / CORRECTED / bad-body-400 / cross-tenant-404).
# --------------------------------------------------------------------------- #
def _rbl_with_one_row(c, ctx, job_id="job-1", rbl_id="rbl-1"):
    up = ppr.register_upload(job_id, ppr.UploadRegister(
        kind="BORE_LOG", filename="log.xlsx", content_base64=_b64(b"bore")), ctx=ctx, c=c)
    ppr.create_bore_log_review(job_id, ppr.ReviewedBoreLogCreate(
        reviewed_bore_log_id=rbl_id, source_upload_id=up["upload_id"]), ctx=ctx, c=c)
    ppr.add_rows(job_id, rbl_id, ppr.RowsAdd(rows=[ppr.ExtractedRowInput(
        row_id="row-1", source_upload_id=up["upload_id"], raw={"s": "0+00"},
        normalized={"s": "0+00"}, extraction_method="MANUAL_ENTRY")]), ctx=ctx, c=c)


def test_row_review_confirmed_ok(tmp_path):
    c, ctx = _container(tmp_path, handwritten=True), _ctx("cp-aaa")
    _job(c, ctx)
    _rbl_with_one_row(c, ctx)
    out = ppr.review_row_route("job-1", "rbl-1", "row-1", ppr.RowReview(to_status=CONFIRMED), ctx=ctx, c=c)
    row = next(r for r in out["rows"] if r["row_id"] == "row-1")
    assert row["review"]["status"] == CONFIRMED


def test_row_review_corrected_requires_and_accepts_corrections(tmp_path):
    c, ctx = _container(tmp_path, handwritten=True), _ctx("cp-aaa")
    _job(c, ctx)
    _rbl_with_one_row(c, ctx)
    with pytest.raises(HTTPException) as exc:                # CORRECTED with no corrected_values -> 400
        ppr.review_row_route("job-1", "rbl-1", "row-1", ppr.RowReview(to_status=CORRECTED), ctx=ctx, c=c)
    assert exc.value.status_code == 400
    out = ppr.review_row_route("job-1", "rbl-1", "row-1",
                               ppr.RowReview(to_status=CORRECTED, corrected_values={"s": "0+10"}),
                               ctx=ctx, c=c)
    row = next(r for r in out["rows"] if r["row_id"] == "row-1")
    assert row["review"]["status"] == CORRECTED and row["review"]["corrected_values"] == {"s": "0+10"}


def test_row_review_confirmed_forbids_corrections_400(tmp_path):
    c, ctx = _container(tmp_path, handwritten=True), _ctx("cp-aaa")
    _job(c, ctx)
    _rbl_with_one_row(c, ctx)
    with pytest.raises(HTTPException) as exc:
        ppr.review_row_route("job-1", "rbl-1", "row-1",
                             ppr.RowReview(to_status=CONFIRMED, corrected_values={"s": "0+10"}),
                             ctx=ctx, c=c)
    assert exc.value.status_code == 400


def test_row_review_cross_tenant_is_404(tmp_path):
    c = _container(tmp_path, handwritten=True)
    a = _ctx("cp-aaa")
    _job(c, a)
    _rbl_with_one_row(c, a)
    b = _ctx("cp-bbb")
    with pytest.raises(HTTPException) as exc:
        ppr.review_row_route("job-1", "rbl-1", "row-1", ppr.RowReview(to_status=CONFIRMED), ctx=b, c=c)
    assert exc.value.status_code == 404


# --------------------------------------------------------------------------- #
# Source-page byte serving (flag-gated route).
# --------------------------------------------------------------------------- #
def test_borelog_source_pdf_page_happy_path(tmp_path):
    c, ctx = _container(tmp_path, handwritten=True), _ctx("cp-aaa")
    _job(c, ctx)
    pdf = _pdf_bytes([["hello"], ["world"]])
    up = ppr.register_upload("job-1", ppr.UploadRegister(
        kind="BORE_LOG", filename="log.pdf", content_base64=_b64(pdf)), ctx=ctx, c=c)
    resp = ppr.get_borelog_source_page_route("job-1", up["upload_id"], page=1, ctx=ctx, c=c)
    assert isinstance(resp, Response)
    assert resp.media_type == "image/png"
    assert bytes(resp.body)[:8] == b"\x89PNG\r\n\x1a\n"


def test_borelog_source_image_page_zero_happy_path(tmp_path):
    c, ctx = _container(tmp_path, handwritten=True), _ctx("cp-aaa")
    _job(c, ctx)
    up = ppr.register_upload("job-1", ppr.UploadRegister(
        kind="BORE_LOG", filename="photo.jpg", content_base64=_b64(_jpeg_bytes())), ctx=ctx, c=c)
    resp = ppr.get_borelog_source_page_route("job-1", up["upload_id"], page=0, ctx=ctx, c=c)
    assert isinstance(resp, FileResponse)
    assert resp.media_type == "image/jpeg"


def test_borelog_source_image_page_nonzero_404(tmp_path):
    c, ctx = _container(tmp_path, handwritten=True), _ctx("cp-aaa")
    _job(c, ctx)
    up = ppr.register_upload("job-1", ppr.UploadRegister(
        kind="BORE_LOG", filename="photo.jpg", content_base64=_b64(_jpeg_bytes())), ctx=ctx, c=c)
    with pytest.raises(HTTPException) as exc:
        ppr.get_borelog_source_page_route("job-1", up["upload_id"], page=1, ctx=ctx, c=c)
    assert exc.value.status_code == 404


def test_borelog_source_pdf_page_out_of_range_404(tmp_path):
    c, ctx = _container(tmp_path, handwritten=True), _ctx("cp-aaa")
    _job(c, ctx)
    pdf = _pdf_bytes([["hello"]])
    up = ppr.register_upload("job-1", ppr.UploadRegister(
        kind="BORE_LOG", filename="log.pdf", content_base64=_b64(pdf)), ctx=ctx, c=c)
    with pytest.raises(HTTPException) as exc:
        ppr.get_borelog_source_page_route("job-1", up["upload_id"], page=99, ctx=ctx, c=c)
    assert exc.value.status_code == 404


def test_borelog_source_missing_job_404(tmp_path):
    c, ctx = _container(tmp_path, handwritten=True), _ctx("cp-aaa")
    with pytest.raises(HTTPException) as exc:
        ppr.get_borelog_source_page_route("job-nope", "up-nope", page=0, ctx=ctx, c=c)
    assert exc.value.status_code == 404


def test_borelog_source_non_borelog_upload_404(tmp_path):
    c, ctx = _container(tmp_path, handwritten=True), _ctx("cp-aaa")
    _job(c, ctx)
    up = ppr.register_upload("job-1", ppr.UploadRegister(
        kind="PLAN_PDF", filename="plan.pdf", content_base64=_b64(_pdf_bytes([["hi"]]))), ctx=ctx, c=c)
    with pytest.raises(HTTPException) as exc:
        ppr.get_borelog_source_page_route("job-1", up["upload_id"], page=0, ctx=ctx, c=c)
    assert exc.value.status_code == 404


def test_borelog_source_wrong_kind_extension_404(tmp_path):
    # A BORE_LOG upload with no "source page" concept (.csv/.xlsx) is not servable.
    c, ctx = _container(tmp_path, handwritten=True), _ctx("cp-aaa")
    _job(c, ctx)
    up = ppr.register_upload("job-1", ppr.UploadRegister(
        kind="BORE_LOG", filename="log.csv", content_base64=_b64(b"a,b\n1,2")), ctx=ctx, c=c)
    with pytest.raises(HTTPException) as exc:
        ppr.get_borelog_source_page_route("job-1", up["upload_id"], page=0, ctx=ctx, c=c)
    assert exc.value.status_code == 404


def test_borelog_source_cross_tenant_404(tmp_path):
    c = _container(tmp_path, handwritten=True)
    a = _ctx("cp-aaa")
    _job(c, a)
    up = ppr.register_upload("job-1", ppr.UploadRegister(
        kind="BORE_LOG", filename="log.pdf", content_base64=_b64(_pdf_bytes([["hi"]]))), ctx=a, c=c)
    b = _ctx("cp-bbb")
    with pytest.raises(HTTPException) as exc:
        ppr.get_borelog_source_page_route("job-1", up["upload_id"], page=0, ctx=b, c=c)
    assert exc.value.status_code == 404
