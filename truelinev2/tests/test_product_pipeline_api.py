"""Offline tests for the default-OFF Slice 1 product-pipeline foundation API.

Follows the repo API-test convention (mirrors test_reviewer_api.py): NO httpx, NO TestClient. Mounting is
checked via app.routes; route functions are called DIRECTLY with an explicit RequestContext (identity is
never taken from the URL path or body). Generic ids/labels only.
"""
from __future__ import annotations

import base64
import dataclasses
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

from truelinev2.api import product_pipeline_routes as ppr
from truelinev2.api.app import create_app
from truelinev2.config import Settings
from truelinev2.context import require_context
from truelinev2.contracts.extracted_row import CONFIRMED, UNREVIEWED
from truelinev2.contracts.processing_job import CREATED, EXTRACTING, UPLOADING
from truelinev2.contracts.reviewed_bore_log import (
    GROUPING_CONFIRMED,
    SEPARATE_BORE,
    SOURCE_CONFLICT,
)
from truelinev2.contracts.upload_pipeline import EXTRACTION_STATUS_QUEUED

PRODUCT_PATHS = {
    "/v2/product/project",
    "/v2/product/jobs",
    "/v2/product/jobs/{job_id}",
    "/v2/product/jobs/{job_id}/transition",
    # Slice 2 — inputs + the reviewed-bore-log review gate
    "/v2/product/jobs/{job_id}/uploads",
    "/v2/product/jobs/{job_id}/reviewed-bore-logs",
    "/v2/product/jobs/{job_id}/reviewed-bore-logs/{reviewed_bore_log_id}/rows",
    "/v2/product/jobs/{job_id}/reviewed-bore-logs/{reviewed_bore_log_id}/rows/{row_id}/review",
    "/v2/product/jobs/{job_id}/reviewed-bore-logs/{reviewed_bore_log_id}/groups",
    "/v2/product/jobs/{job_id}/reviewed-bore-logs/{reviewed_bore_log_id}/groups/{group_id}/status",
    "/v2/product/jobs/{job_id}/reviewed-bore-logs/{reviewed_bore_log_id}/review-queue",
}


def _settings(tmp_path: Path, *, enabled: bool) -> Settings:
    return dataclasses.replace(
        Settings.for_proof(),
        artifact_root=tmp_path / "artifacts",
        cards_dir=tmp_path / "cards",
        db_path=tmp_path / "truelinev2.db",
        product_pipeline_api_optin=enabled,
        product_store_root=tmp_path / "product_store",
    )


def _container(tmp_path: Path):
    return create_app(_settings(tmp_path, enabled=True)).state.tl2


def _product_routes(app):
    return [r for r in app.routes
            if isinstance(r, APIRoute) and r.path.startswith("/v2/product")]


def _ctx(tenant: str, session: str = "sess-1"):
    return require_context(tenant, session)


# --------------------------------------------------------------------------- #
# Settings + mounting.
# --------------------------------------------------------------------------- #
def test_settings_default_off_and_env_paths(monkeypatch):
    monkeypatch.delenv("TL2_PRODUCT_PIPELINE_API_OPTIN", raising=False)
    monkeypatch.delenv("TL2_PRODUCT_STORE_ROOT", raising=False)
    default = Settings.from_env()
    assert default.product_pipeline_api_optin is False
    assert default.product_store_root.name == "product_store"

    monkeypatch.setenv("TL2_PRODUCT_PIPELINE_API_OPTIN", "1")
    monkeypatch.setenv("TL2_PRODUCT_STORE_ROOT", "C:/tmp/ps")
    enabled = Settings.from_env()
    assert enabled.product_pipeline_api_optin is True
    assert enabled.product_store_root == Path("C:/tmp/ps")


def test_flag_off_routes_are_dormant(tmp_path):
    app = create_app(_settings(tmp_path, enabled=False))
    assert not any(r.path.startswith("/v2/product") for r in app.routes
                   if isinstance(r, APIRoute))


def test_flag_on_mounts_expected_routes_get_post_only_with_context_dep(tmp_path):
    app = create_app(_settings(tmp_path, enabled=True))
    routes = _product_routes(app)
    assert {r.path for r in routes} == PRODUCT_PATHS
    methods = set().union(*(r.methods for r in routes))
    assert methods <= {"GET", "POST"}                       # CORS allows only GET/POST
    assert all(r.dependant.dependencies for r in routes)    # context-bearing (get_context/get_container)


def test_no_customer_project_id_in_path_or_body(tmp_path):
    # identity is never accepted from the URL path...
    app = create_app(_settings(tmp_path, enabled=True))
    for r in _product_routes(app):
        assert "customer_project" not in r.path and "tenant" not in r.path
    # ...nor from request bodies (Slice 1)
    assert set(ppr.ProjectCreate.model_fields) == {"display_name"}
    assert set(ppr.JobCreate.model_fields) == {"job_id"}
    assert set(ppr.JobTransition.model_fields) == {"to_status", "reason"}
    # ...nor from any Slice 2 request body (identity is the verified context, never a field)
    slice2_models = [ppr.UploadRegister, ppr.ReviewedBoreLogCreate, ppr.ExtractedRowInput,
                     ppr.RowsAdd, ppr.RowReview, ppr.SegmentGroupCreate, ppr.GroupingStatus]
    for model in slice2_models:
        fields = set(model.model_fields)
        assert not (fields & {"customer_project", "customer_project_id", "tenant", "tenant_id"})


# --------------------------------------------------------------------------- #
# Project create / get.
# --------------------------------------------------------------------------- #
def test_project_create_and_get(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    rec = ppr.create_project(ppr.ProjectCreate(display_name="Label"), ctx=ctx, c=c)
    assert rec["id"] == "cp-aaa" and rec["display_name"] == "Label"
    got = ppr.get_project(ctx=ctx, c=c)
    assert got["id"] == "cp-aaa"


def test_project_create_conflict(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    ppr.create_project(ppr.ProjectCreate(display_name="Label"), ctx=ctx, c=c)
    with pytest.raises(HTTPException) as exc:
        ppr.create_project(ppr.ProjectCreate(display_name="Label-2"), ctx=ctx, c=c)
    assert exc.value.status_code == 409


def test_get_project_missing_is_404(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-none")
    with pytest.raises(HTTPException) as exc:
        ppr.get_project(ctx=ctx, c=c)
    assert exc.value.status_code == 404


def test_invalid_tenant_slug_is_400(tmp_path):
    c, ctx = _container(tmp_path), _ctx("Upper")            # uppercase -> not a valid customer_project id
    with pytest.raises(HTTPException) as exc:
        ppr.create_project(ppr.ProjectCreate(display_name="Label"), ctx=ctx, c=c)
    assert exc.value.status_code == 400


# --------------------------------------------------------------------------- #
# Job create / get / transition.
# --------------------------------------------------------------------------- #
def test_job_create_and_get(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    ppr.create_project(ppr.ProjectCreate(display_name="Label"), ctx=ctx, c=c)
    job = ppr.create_processing_job(ppr.JobCreate(job_id="job-1"), ctx=ctx, c=c)
    assert job["status"] == CREATED and job["job_id"] == "job-1"
    got = ppr.get_processing_job("job-1", ctx=ctx, c=c)
    assert got["job_id"] == "job-1" and got["customer_project_id"] == "cp-aaa"


def test_job_create_requires_project(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-bbb")           # no project created
    with pytest.raises(HTTPException) as exc:
        ppr.create_processing_job(ppr.JobCreate(job_id="job-1"), ctx=ctx, c=c)
    assert exc.value.status_code == 404


def test_job_create_conflict(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    ppr.create_project(ppr.ProjectCreate(display_name="Label"), ctx=ctx, c=c)
    ppr.create_processing_job(ppr.JobCreate(job_id="job-1"), ctx=ctx, c=c)
    with pytest.raises(HTTPException) as exc:
        ppr.create_processing_job(ppr.JobCreate(job_id="job-1"), ctx=ctx, c=c)
    assert exc.value.status_code == 409


def test_get_job_missing_is_404(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    ppr.create_project(ppr.ProjectCreate(display_name="Label"), ctx=ctx, c=c)
    with pytest.raises(HTTPException) as exc:
        ppr.get_processing_job("nope", ctx=ctx, c=c)
    assert exc.value.status_code == 404


def test_transition_delegates_to_contract(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    ppr.create_project(ppr.ProjectCreate(display_name="Label"), ctx=ctx, c=c)
    ppr.create_processing_job(ppr.JobCreate(job_id="job-1"), ctx=ctx, c=c)
    job = ppr.transition_processing_job("job-1", ppr.JobTransition(to_status=UPLOADING), ctx=ctx, c=c)
    assert job["status"] == UPLOADING
    assert job["audit"][-1]["to"] == UPLOADING and job["audit"][-1]["by"] == "sess-1"


def test_transition_illegal_is_409(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    ppr.create_project(ppr.ProjectCreate(display_name="Label"), ctx=ctx, c=c)
    ppr.create_processing_job(ppr.JobCreate(job_id="job-1"), ctx=ctx, c=c)
    with pytest.raises(HTTPException) as exc:                # CREATED -> PLACED is not allowed
        ppr.transition_processing_job("job-1", ppr.JobTransition(to_status="PLACED"), ctx=ctx, c=c)
    assert exc.value.status_code == 409


# --------------------------------------------------------------------------- #
# Tenant isolation.
# --------------------------------------------------------------------------- #
def test_tenant_isolation_b_cannot_address_a(tmp_path):
    c = _container(tmp_path)
    ctx_a, ctx_b = _ctx("cp-aaa"), _ctx("cp-bbb")
    ppr.create_project(ppr.ProjectCreate(display_name="Label"), ctx=ctx_a, c=c)
    ppr.create_processing_job(ppr.JobCreate(job_id="job-1"), ctx=ctx_a, c=c)
    # tenant B cannot read A's job or project (different scope)
    with pytest.raises(HTTPException) as exc_job:
        ppr.get_processing_job("job-1", ctx=ctx_b, c=c)
    assert exc_job.value.status_code == 404
    with pytest.raises(HTTPException) as exc_proj:
        ppr.get_project(ctx=ctx_b, c=c)
    assert exc_proj.value.status_code == 404
    # and B cannot transition A's job
    with pytest.raises(HTTPException) as exc_tr:
        ppr.transition_processing_job("job-1", ppr.JobTransition(to_status=UPLOADING), ctx=ctx_b, c=c)
    assert exc_tr.value.status_code == 404
    # A still owns its job
    assert ppr.get_processing_job("job-1", ctx=ctx_a, c=c)["job_id"] == "job-1"


# --------------------------------------------------------------------------- #
# Slice 2 helpers.
# --------------------------------------------------------------------------- #
def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _seed_job(c, ctx, job_id="job-1"):
    """Project + job in CREATED (an uploadable state) for the tenant."""
    ppr.create_project(ppr.ProjectCreate(display_name="Label"), ctx=ctx, c=c)
    ppr.create_processing_job(ppr.JobCreate(job_id=job_id), ctx=ctx, c=c)


def _register_bore_log(c, ctx, job_id="job-1", filename="rows.csv"):
    return ppr.register_upload(
        job_id, ppr.UploadRegister(kind="BORE_LOG", filename=filename,
                                   content_base64=_b64(b"a,b\n1,2\n")),
        ctx=ctx, c=c)


def _seed_reviewed_bore_log(c, ctx, job_id="job-1", rbl_id="rbl-1"):
    """Project + job + a BORE_LOG upload + an empty reviewed_bore_log over it. Returns (upload, rbl)."""
    _seed_job(c, ctx, job_id)
    up = _register_bore_log(c, ctx, job_id)
    rbl = ppr.create_bore_log_review(
        job_id, ppr.ReviewedBoreLogCreate(reviewed_bore_log_id=rbl_id, source_upload_id=up["upload_id"]),
        ctx=ctx, c=c)
    return up, rbl


def _add_one_row(c, ctx, upload_id, *, row_id="row-1", job_id="job-1", rbl_id="rbl-1"):
    return ppr.add_rows(
        job_id, rbl_id, ppr.RowsAdd(rows=[ppr.ExtractedRowInput(
            row_id=row_id, source_upload_id=upload_id, raw={"len": "100"},
            normalized={"len_ft": 100}, extraction_method="TABLE_IMPORT")]),
        ctx=ctx, c=c)


# --------------------------------------------------------------------------- #
# Slice 2 — uploads (untrusted intake; bytes as base64, no python-multipart).
# --------------------------------------------------------------------------- #
def test_upload_is_stored_but_stays_queued(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    _seed_job(c, ctx)
    rec = _register_bore_log(c, ctx)
    assert rec["kind"] == "BORE_LOG"
    assert rec["extraction_status"] == EXTRACTION_STATUS_QUEUED   # untrusted: no OCR/AI ran
    assert rec["bytes"] > 0 and len(rec["sha256"]) == 64
    job = ppr.get_processing_job("job-1", ctx=ctx, c=c)          # the queued upload is durable on the job
    assert [u["upload_id"] for u in job["uploads"]] == [rec["upload_id"]]
    assert job["uploads"][0]["extraction_status"] == EXTRACTION_STATUS_QUEUED


def test_upload_invalid_base64_is_400(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    _seed_job(c, ctx)
    with pytest.raises(HTTPException) as exc:
        ppr.register_upload("job-1", ppr.UploadRegister(
            kind="BORE_LOG", filename="rows.csv", content_base64="@@@not-base64@@@"), ctx=ctx, c=c)
    assert exc.value.status_code == 400


def test_upload_unknown_kind_is_400(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    _seed_job(c, ctx)
    with pytest.raises(HTTPException) as exc:
        ppr.register_upload("job-1", ppr.UploadRegister(
            kind="NOPE", filename="x.pdf", content_base64=_b64(b"%PDF-1.4")), ctx=ctx, c=c)
    assert exc.value.status_code == 400


def test_upload_rejected_extension_is_400(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    _seed_job(c, ctx)
    with pytest.raises(HTTPException) as exc:                     # PLAN_PDF allows only .pdf
        ppr.register_upload("job-1", ppr.UploadRegister(
            kind="PLAN_PDF", filename="plan.csv", content_base64=_b64(b"x,y\n")), ctx=ctx, c=c)
    assert exc.value.status_code == 400


def test_upload_to_missing_job_is_404(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    ppr.create_project(ppr.ProjectCreate(display_name="Label"), ctx=ctx, c=c)   # project but no job
    with pytest.raises(HTTPException) as exc:
        ppr.register_upload("ghost", ppr.UploadRegister(
            kind="BORE_LOG", filename="rows.csv", content_base64=_b64(b"a\n")), ctx=ctx, c=c)
    assert exc.value.status_code == 404


def test_upload_after_intake_closed_is_409(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    _seed_job(c, ctx)
    ppr.transition_processing_job("job-1", ppr.JobTransition(to_status=UPLOADING), ctx=ctx, c=c)
    ppr.transition_processing_job("job-1", ppr.JobTransition(to_status=EXTRACTING), ctx=ctx, c=c)
    with pytest.raises(HTTPException) as exc:                     # job is past the upload phase
        _register_bore_log(c, ctx)
    assert exc.value.status_code == 409


# --------------------------------------------------------------------------- #
# Slice 2 — reviewed_bore_log create.
# --------------------------------------------------------------------------- #
def test_create_reviewed_bore_log(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    up, rbl = _seed_reviewed_bore_log(c, ctx)
    assert rbl["reviewed_bore_log_id"] == "rbl-1"
    assert rbl["source_upload_id"] == up["upload_id"]
    assert rbl["rows"] == [] and rbl["groups"] == []
    assert rbl["customer_project_id"] == "cp-aaa"


def test_create_reviewed_bore_log_conflict_is_409(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    up, _ = _seed_reviewed_bore_log(c, ctx)
    with pytest.raises(HTTPException) as exc:
        ppr.create_bore_log_review("job-1", ppr.ReviewedBoreLogCreate(
            reviewed_bore_log_id="rbl-1", source_upload_id=up["upload_id"]), ctx=ctx, c=c)
    assert exc.value.status_code == 409


def test_create_reviewed_bore_log_non_bore_log_source_is_400(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    _seed_job(c, ctx)
    plan = ppr.register_upload("job-1", ppr.UploadRegister(   # a PLAN_PDF, not a BORE_LOG
        kind="PLAN_PDF", filename="plan.pdf", content_base64=_b64(b"%PDF-1.4 plan")), ctx=ctx, c=c)
    with pytest.raises(HTTPException) as exc:
        ppr.create_bore_log_review("job-1", ppr.ReviewedBoreLogCreate(
            reviewed_bore_log_id="rbl-x", source_upload_id=plan["upload_id"]), ctx=ctx, c=c)
    assert exc.value.status_code == 400


# --------------------------------------------------------------------------- #
# Slice 2 — rows start untrusted; review + grouping drive the eligibility gate.
# --------------------------------------------------------------------------- #
def test_imported_rows_start_untrusted(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    up, _ = _seed_reviewed_bore_log(c, ctx)
    rbl = _add_one_row(c, ctx, up["upload_id"])
    assert rbl["rows"][0]["review"]["status"] == UNREVIEWED       # never a candidate by default
    q = ppr.get_review_queue("job-1", "rbl-1", ctx=ctx, c=c)
    assert q["rows_needing_review"] == ["row-1"]
    assert q["engine_eligible_row_ids"] == [] and q["engine_ready"] is False


def test_row_review_updates_trust_state(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    up, _ = _seed_reviewed_bore_log(c, ctx)
    _add_one_row(c, ctx, up["upload_id"])
    rbl = ppr.review_row_route("job-1", "rbl-1", "row-1", ppr.RowReview(to_status=CONFIRMED),
                               ctx=ctx, c=c)
    assert rbl["rows"][0]["review"]["status"] == CONFIRMED
    q = ppr.get_review_queue("job-1", "rbl-1", ctx=ctx, c=c)
    assert "row-1" in q["rows_review_passed"] and q["rows_needing_review"] == []


def test_review_corrected_without_values_is_400(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    up, _ = _seed_reviewed_bore_log(c, ctx)
    _add_one_row(c, ctx, up["upload_id"])
    with pytest.raises(HTTPException) as exc:                     # CORRECTED requires corrected_values
        ppr.review_row_route("job-1", "rbl-1", "row-1", ppr.RowReview(to_status="CORRECTED"),
                             ctx=ctx, c=c)
    assert exc.value.status_code == 400


def test_review_missing_row_is_404(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    _seed_reviewed_bore_log(c, ctx)
    with pytest.raises(HTTPException) as exc:
        ppr.review_row_route("job-1", "rbl-1", "ghost", ppr.RowReview(to_status=CONFIRMED),
                             ctx=ctx, c=c)
    assert exc.value.status_code == 404


def test_review_queue_missing_rbl_is_404(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    _seed_job(c, ctx)
    with pytest.raises(HTTPException) as exc:
        ppr.get_review_queue("job-1", "ghost", ctx=ctx, c=c)
    assert exc.value.status_code == 404


def test_grouping_and_engine_eligibility_gate(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    up, _ = _seed_reviewed_bore_log(c, ctx)
    _add_one_row(c, ctx, up["upload_id"])
    ppr.review_row_route("job-1", "rbl-1", "row-1", ppr.RowReview(to_status=CONFIRMED), ctx=ctx, c=c)
    # a reviewed row is NOT yet eligible — grouping is also required (gate stays closed)
    q = ppr.get_review_queue("job-1", "rbl-1", ctx=ctx, c=c)
    assert q["engine_ready"] is False and "row-1" in q["ungrouped_rows"]
    # define + confirm a single-bore group -> the gate opens
    ppr.define_group("job-1", "rbl-1", ppr.SegmentGroupCreate(
        group_id="g-1", member_row_ids=["row-1"], relation=SEPARATE_BORE), ctx=ctx, c=c)
    ppr.set_group_status("job-1", "rbl-1", "g-1", ppr.GroupingStatus(to_status=GROUPING_CONFIRMED),
                         ctx=ctx, c=c)
    q2 = ppr.get_review_queue("job-1", "rbl-1", ctx=ctx, c=c)
    assert q2["engine_eligible_row_ids"] == ["row-1"] and q2["engine_ready"] is True


def test_grouping_status_source_conflict_requires_reason_is_400(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    up, _ = _seed_reviewed_bore_log(c, ctx)
    _add_one_row(c, ctx, up["upload_id"])
    ppr.define_group("job-1", "rbl-1", ppr.SegmentGroupCreate(
        group_id="g-1", member_row_ids=["row-1"], relation=SEPARATE_BORE), ctx=ctx, c=c)
    with pytest.raises(HTTPException) as exc:                     # SOURCE_CONFLICT needs a reason
        ppr.set_group_status("job-1", "rbl-1", "g-1", ppr.GroupingStatus(to_status=SOURCE_CONFLICT),
                             ctx=ctx, c=c)
    assert exc.value.status_code == 400


# --------------------------------------------------------------------------- #
# Slice 2 — tenant isolation across the whole inputs/review surface.
# --------------------------------------------------------------------------- #
def test_slice2_tenant_isolation_b_cannot_address_a(tmp_path):
    c = _container(tmp_path)
    ctx_a, ctx_b = _ctx("cp-aaa"), _ctx("cp-bbb")
    up_a, _ = _seed_reviewed_bore_log(c, ctx_a)                  # A: job-1 + upload + rbl-1
    _add_one_row(c, ctx_a, up_a["upload_id"])
    # B addresses A's job-1 / rbl-1 by the same ids, but B's scope is empty -> 404 everywhere
    with pytest.raises(HTTPException) as e_up:
        ppr.register_upload("job-1", ppr.UploadRegister(
            kind="BORE_LOG", filename="rows.csv", content_base64=_b64(b"x\n")), ctx=ctx_b, c=c)
    assert e_up.value.status_code == 404
    with pytest.raises(HTTPException) as e_rbl:
        ppr.create_bore_log_review("job-1", ppr.ReviewedBoreLogCreate(
            reviewed_bore_log_id="rbl-2", source_upload_id=up_a["upload_id"]), ctx=ctx_b, c=c)
    assert e_rbl.value.status_code == 404
    with pytest.raises(HTTPException) as e_rows:
        _add_one_row(c, ctx_b, up_a["upload_id"], row_id="row-9")
    assert e_rows.value.status_code == 404
    with pytest.raises(HTTPException) as e_q:
        ppr.get_review_queue("job-1", "rbl-1", ctx=ctx_b, c=c)
    assert e_q.value.status_code == 404
    # A still owns its data
    assert ppr.get_review_queue("job-1", "rbl-1", ctx=ctx_a, c=c)["rows_needing_review"] == ["row-1"]
