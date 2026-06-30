"""Offline tests for the default-OFF Slice 1 product-pipeline foundation API.

Follows the repo API-test convention (mirrors test_reviewer_api.py): NO httpx, NO TestClient. Mounting is
checked via app.routes; route functions are called DIRECTLY with an explicit RequestContext (identity is
never taken from the URL path or body). Generic ids/labels only.
"""
from __future__ import annotations

import base64
import dataclasses
import hashlib
import json
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.responses import FileResponse
from fastapi.routing import APIRoute

from truelinev2.api import product_pipeline_routes as ppr
from truelinev2.api.app import create_app
from truelinev2.config import Settings
from truelinev2.context import require_context
from truelinev2.contracts.extracted_row import CONFIRMED, MANUAL_ENTRY, UNREVIEWED
from truelinev2.contracts.manifest_handoff import ATTEMPTED, FAILED, REJECTED, SUCCEEDED
from truelinev2.contracts.processing_job import (
    AWAITING_REVIEW,
    CLOSEOUT_REVIEW,
    CREATED,
    EXTRACTING,
    PLACED,
    PLACING,
    UPLOADING,
    job_dir,
)
from truelinev2.contracts.reviewed_bore_log import (
    GROUPING_CONFIRMED,
    SEPARATE_BORE,
    SOURCE_CONFLICT,
)
from truelinev2.contracts.upload_pipeline import EXTRACTION_STATUS_QUEUED
from truelinev2.contracts import review_acceptance as ra
from truelinev2.contracts import uploaded_corpus_engine_handoff as uce
from truelinev2.schema.models import Bore, Callout, Placement, PlacementStatus

PRODUCT_PATHS = {
    "/v2/product/project",
    "/v2/product/jobs",
    "/v2/product/jobs/{job_id}",
    "/v2/product/jobs/{job_id}/transition",
    # Slice 2 — inputs + the reviewed-bore-log review gate
    "/v2/product/jobs/{job_id}/uploads",
    "/v2/product/jobs/{job_id}/reviewed-bore-logs",
    "/v2/product/jobs/{job_id}/reviewed-bore-logs/{reviewed_bore_log_id}",
    "/v2/product/jobs/{job_id}/reviewed-bore-logs/{reviewed_bore_log_id}/rows",
    "/v2/product/jobs/{job_id}/reviewed-bore-logs/{reviewed_bore_log_id}/extract",
    "/v2/product/jobs/{job_id}/reviewed-bore-logs/{reviewed_bore_log_id}/rows/{row_id}/review",
    "/v2/product/jobs/{job_id}/reviewed-bore-logs/{reviewed_bore_log_id}/groups",
    "/v2/product/jobs/{job_id}/reviewed-bore-logs/{reviewed_bore_log_id}/groups/{group_id}/status",
    "/v2/product/jobs/{job_id}/reviewed-bore-logs/{reviewed_bore_log_id}/review-queue",
    # Slice 3 — manifest handoff + proof reads
    "/v2/product/jobs/{job_id}/manifest-handoffs",
    "/v2/product/jobs/{job_id}/manifest-handoffs/{engine_run_id}/finalize",
    "/v2/product/jobs/{job_id}/redline-manifest",
    "/v2/product/jobs/{job_id}/artifacts",
    "/v2/product/jobs/{job_id}/artifacts/{artifact_path:path}",
    # Slice 4 — downstream status spine (kmz safety / closeout / billing / export package)
    "/v2/product/jobs/{job_id}/kmz-export",
    "/v2/product/jobs/{job_id}/kmz-export/download",
    "/v2/product/jobs/{job_id}/closeout/evaluate",
    "/v2/product/jobs/{job_id}/closeout",
    "/v2/product/jobs/{job_id}/billing/compute",
    "/v2/product/jobs/{job_id}/billing",
    "/v2/product/jobs/{job_id}/operator-pricing",
    "/v2/product/jobs/{job_id}/export-package/assemble",
    "/v2/product/jobs/{job_id}/export-package",
    "/v2/product/jobs/{job_id}/export-package/download",
    "/v2/product/jobs/{job_id}/export-package/pdf",
    "/v2/product/jobs/{job_id}/gis-route",
    "/v2/product/jobs/{job_id}/gis-route/download",
    # Slice C — uploaded-corpus engine-handoff readiness (read-only)
    "/v2/product/jobs/{job_id}/engine-handoff",
    # Recognized-corpus AUTOMATIC handoff (positive sha256 recognition -> existing deterministic render)
    "/v2/product/jobs/{job_id}/recognized-corpus-handoff",
    "/v2/product/jobs/{job_id}/recognized-corpus-handoff/render",
    # Uploaded-corpus ENGINE handoff (run the engine on the job's own plan + reviewed bore-log)
    "/v2/product/jobs/{job_id}/uploaded-corpus-engine-handoff",
    "/v2/product/jobs/{job_id}/uploaded-corpus-engine-handoff/render",
    # G3 — terminus evidence (DISPLAY-only observer; read-only, no placement/status/AUTO change)
    "/v2/product/jobs/{job_id}/terminus-evidence",
    # Phase 9 — product workflow orchestrator (3-path redline decision + closeout/export assembly)
    "/v2/product/jobs/{job_id}/workflow/redline",
    "/v2/product/jobs/{job_id}/workflow/closeout",
    # Phase 6 — REVIEW acceptance lane (engine generates a candidate; human accepts/rejects)
    "/v2/product/jobs/{job_id}/review-candidates/generate",
    "/v2/product/jobs/{job_id}/review-candidates",
    "/v2/product/jobs/{job_id}/review-candidates/{candidate_id}",
    "/v2/product/jobs/{job_id}/review-candidates/{candidate_id}/accept",
    "/v2/product/jobs/{job_id}/review-candidates/{candidate_id}/reject",
    # M2 — human-confirmed source anchors (record + validate; renders nothing)
    "/v2/product/jobs/{job_id}/source-anchors",
    "/v2/product/jobs/{job_id}/source-anchors/{source_anchor_id}",
    # M2 — render a validated source anchor into the job's human-confirmed redline bundle
    "/v2/product/jobs/{job_id}/source-anchors/{source_anchor_id}/render",
    # M2 — uploaded PLAN_PDF page display (read-only metadata + page raster)
    "/v2/product/jobs/{job_id}/plan-pages/{plan_upload_id}",
    "/v2/product/jobs/{job_id}/plan-pages/{plan_upload_id}/{page_number}/raster",
}


def _settings(tmp_path: Path, *, enabled: bool) -> Settings:
    return dataclasses.replace(
        Settings.for_proof(),
        artifact_root=tmp_path / "artifacts",
        cards_dir=tmp_path / "cards",
        db_path=tmp_path / "truelinev2.db",
        product_pipeline_api_optin=enabled,
        product_store_root=tmp_path / "product_store",
        product_billing_cost_rules_path=tmp_path / "cost_rules.json",
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
    monkeypatch.delenv("TL2_PRODUCT_BILLING_COST_RULES", raising=False)
    default = Settings.from_env()
    assert default.product_pipeline_api_optin is False
    assert default.product_store_root.name == "product_store"
    assert default.product_billing_cost_rules_path is None      # billing unavailable until configured

    monkeypatch.setenv("TL2_PRODUCT_PIPELINE_API_OPTIN", "1")
    monkeypatch.setenv("TL2_PRODUCT_STORE_ROOT", "C:/tmp/ps")
    monkeypatch.setenv("TL2_PRODUCT_BILLING_COST_RULES", "C:/tmp/rules.json")
    enabled = Settings.from_env()
    assert enabled.product_pipeline_api_optin is True
    assert enabled.product_store_root == Path("C:/tmp/ps")
    assert enabled.product_billing_cost_rules_path == Path("C:/tmp/rules.json")


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
    # ...nor from any Slice 2/3 request body (identity is the verified context, never a field)
    body_models = [ppr.UploadRegister, ppr.ReviewedBoreLogCreate, ppr.ExtractedRowInput,
                   ppr.RowsAdd, ppr.RowReview, ppr.SegmentGroupCreate, ppr.GroupingStatus,
                   ppr.ManifestHandoffRecord, ppr.ManifestHandoffFinalize, ppr.SourceAnchorCreate,
                   ppr.ReviewReject]
    for model in body_models:
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


def test_list_jobs_lists_tenant_jobs_with_summary(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    ppr.create_project(ppr.ProjectCreate(display_name="Label"), ctx=ctx, c=c)
    ppr.create_processing_job(ppr.JobCreate(job_id="job-1"), ctx=ctx, c=c)
    ppr.create_processing_job(ppr.JobCreate(job_id="job-2"), ctx=ctx, c=c)
    out = ppr.list_processing_jobs(ctx=ctx, c=c)
    assert {j["job_id"] for j in out["jobs"]} == {"job-1", "job-2"}
    one = out["jobs"][0]
    assert one["status"] == CREATED and one["upload_count"] == 0
    assert set(one["slots"]) == {"redline_manifest", "artifact_bundle", "export_package"}
    assert all(v is False for v in one["slots"].values())          # no output slots filled yet
    assert "created_at" in one and "updated_at" in one


def test_list_jobs_empty_for_tenant_without_jobs(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-empty")                # no project / no jobs
    assert ppr.list_processing_jobs(ctx=ctx, c=c) == {"jobs": []}


def test_list_jobs_no_cross_tenant_leak(tmp_path):
    c = _container(tmp_path)
    a, b = _ctx("cp-aaa"), _ctx("cp-bbb")
    ppr.create_project(ppr.ProjectCreate(display_name="A"), ctx=a, c=c)
    ppr.create_processing_job(ppr.JobCreate(job_id="job-a"), ctx=a, c=c)
    ppr.create_project(ppr.ProjectCreate(display_name="B"), ctx=b, c=c)
    ppr.create_processing_job(ppr.JobCreate(job_id="job-b"), ctx=b, c=c)
    assert {j["job_id"] for j in ppr.list_processing_jobs(ctx=a, c=c)["jobs"]} == {"job-a"}
    assert {j["job_id"] for j in ppr.list_processing_jobs(ctx=b, c=c)["jobs"]} == {"job-b"}


def test_upload_photo_kind_via_route_stays_queued(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    ppr.create_project(ppr.ProjectCreate(display_name="Label"), ctx=ctx, c=c)
    ppr.create_processing_job(ppr.JobCreate(job_id="job-1"), ctx=ctx, c=c)
    content_b64 = base64.b64encode(b"\x89PNG\r\n\x1a\n not-parsed").decode()
    rec = ppr.register_upload(
        "job-1",
        ppr.UploadRegister(kind="PHOTO", filename="site-photo.png", content_base64=content_b64),
        ctx=ctx, c=c)
    assert rec["kind"] == "PHOTO" and rec["extraction_status"] == EXTRACTION_STATUS_QUEUED


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


# --------------------------------------------------------------------------- #
# Slice 2 — deterministic table extraction (read-only; rows stay UNTRUSTED, no fabricated confidence).
# --------------------------------------------------------------------------- #
def test_extract_route_adds_untrusted_table_import_rows(tmp_path, monkeypatch):
    from truelinev2.contracts.extracted_row import new_extracted_row, TABLE_IMPORT
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    up, _ = _seed_reviewed_bore_log(c, ctx)

    def fake_extract(path, source_upload_id, *, at, by, existing_row_ids=()):  # noqa: ARG001
        return [new_extracted_row("extracted-1", source_upload_id,
                                  raw={"start_station": "0+00", "end_station": "2+99", "footage_ft": 299.0},
                                  normalized={"start_station": "0+00", "end_station": "2+99"},
                                  extraction_method=TABLE_IMPORT, confidence=None, at=at, by=by)]

    monkeypatch.setattr(ppr, "extract_rows_from_borelog", fake_extract)
    out = ppr.extract_bore_log_rows_route("job-1", "rbl-1", ctx=ctx, c=c)
    assert out["extracted_count"] == 1 and out["extracted_row_ids"] == ["extracted-1"]
    row = out["record"]["rows"][0]
    assert row["extraction"]["extraction_method"] == TABLE_IMPORT
    assert row["extraction"]["confidence"] is None          # deterministic parse — never fabricated
    assert row["review"]["status"] == UNREVIEWED             # not a placement candidate until reviewed


def test_extract_route_missing_rbl_is_404(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    _seed_job(c, ctx)
    with pytest.raises(HTTPException) as exc:
        ppr.extract_bore_log_rows_route("job-1", "ghost", ctx=ctx, c=c)
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


# --------------------------------------------------------------------------- #
# Slice 3 helpers (engine-ready rbl + a valid, server-staged engine-output bundle).
# --------------------------------------------------------------------------- #
def _log(lid, status, prov, *, drawn=False, covered=False, blocked=False, artifacts=None):
    return {"log_id": lid, "parent_id": "b_" + lid, "entry_role": "standalone",
            "status": status, "provenance": prov, "drawn": drawn, "covered": covered,
            "blocked": blocked, "drawn_lane": "NEW_TARGETS" if drawn else None,
            "source_sheets": [1],
            "span": {"start_station": "0+00", "end_station": "1+00", "label": "0+00->1+00"},
            "closure": None, "coverage": {"covered_by": "logX"} if covered else None,
            "blocker": {"category": "OWNER_LOCKED", "name": "n", "unlock_requirement": "owner lifts"}
            if blocked else None,
            "artifacts": artifacts or [],
            "evidence": [{"kind": "ACCOUNTABILITY_LEDGER", "ref": "r"}], "warnings": []}


def _build_engine_bundle(dest, *, mock_example=False, tag=b"A"):
    """Write a minimal VALID engine-output bundle (one drawn log + one FINAL_REDLINE_PNG, one covered, one
    blocked) at dest. Mirrors the published-bundle shape the store/consumer require; generic names only."""
    dest = Path(dest)
    art_dir = dest / "artifacts" / "logA"
    art_dir.mkdir(parents=True)
    data = b"FAKE-PNG-" + tag
    (art_dir / "logA_s1_redline_stroke.png").write_bytes(data)
    art = {"kind": "FINAL_REDLINE_PNG", "path": "artifacts/logA/logA_s1_redline_stroke.png",
           "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data),
           "published": True, "example_placeholder": False}
    manifest = {
        "schema_version": "1.0.0", "mock_example": mock_example, "disclaimer": "t",
        "project_id": "proj-a", "project_name": "Project A",
        "engine": {"branch": "feat/truelinev2", "engine_head": "h", "render_commit": "rc-0",
                   "generated_from": "test"},
        "summary": {"total_logs": 3, "drawn_count": 1, "covered_count": 1, "blocked_count": 1,
                    "frontier": "1/3"},
        "status_counts": {"DRAWN_REDLINE": 1, "COVERED_BY_EXISTING_REDLINE": 1,
                          "OWNER_LOCKED_ABSTAIN": 1, "SOURCE_GAP_BLOCKED": 0,
                          "MISSING_SOURCE_SHEET_BLOCKED": 0},
        "provenance_counts": {"DETERMINISTIC_AUTO": 1, "OWNER_CONFIRMED_HUMAN_ADJUSTABLE": 0,
                              "COVERED_BY_EXISTING_REDLINE": 1, "BLOCKED_OWNER_LOCKED": 1,
                              "BLOCKED_SOURCE_GAP": 0, "BLOCKED_MISSING_SOURCE": 0},
        "consumption_rules": ["consume the manifest"],
        "logs": [_log("logA", "DRAWN_REDLINE", "DETERMINISTIC_AUTO", drawn=True, artifacts=[art]),
                 _log("logC", "COVERED_BY_EXISTING_REDLINE", "COVERED_BY_EXISTING_REDLINE", covered=True),
                 _log("logB", "OWNER_LOCKED_ABSTAIN", "BLOCKED_OWNER_LOCKED", blocked=True)],
    }
    (dest / "redline_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return dest


ART_PATH = "artifacts/logA/logA_s1_redline_stroke.png"


def _ready_rbl(c, ctx, *, job_id="job-1", rbl_id="rbl-1"):
    """Project + job + BORE_LOG upload + reviewed_bore_log with one CONFIRMED, grouped+confirmed row →
    engine-ready (so a handoff can finalize). Returns the upload record."""
    up, _ = _seed_reviewed_bore_log(c, ctx, job_id, rbl_id)
    _add_one_row(c, ctx, up["upload_id"], job_id=job_id, rbl_id=rbl_id)
    ppr.review_row_route(job_id, rbl_id, "row-1", ppr.RowReview(to_status=CONFIRMED), ctx=ctx, c=c)
    ppr.define_group(job_id, rbl_id, ppr.SegmentGroupCreate(
        group_id="g-1", member_row_ids=["row-1"], relation=SEPARATE_BORE), ctx=ctx, c=c)
    ppr.set_group_status(job_id, rbl_id, "g-1", ppr.GroupingStatus(to_status=GROUPING_CONFIRMED),
                         ctx=ctx, c=c)
    return up


def _stage_bundle(c, cp, ref, *, job_id="job-1", **kw):
    """Build a valid engine-output bundle at the server-side staging path the finalize route resolves."""
    dest = job_dir(c.settings.product_store_root, cp, job_id) / ppr.ENGINE_OUTPUTS_SUBDIR / ref
    return _build_engine_bundle(dest, **kw)


def _record(c, ctx, *, run="run-1", job_id="job-1", rbl_id="rbl-1"):
    return ppr.record_manifest_handoff(job_id, ppr.ManifestHandoffRecord(
        reviewed_bore_log_id=rbl_id, engine_run_id=run, engine_run_status="completed"), ctx=ctx, c=c)


def _finalized_job(c, ctx, *, ref="bundle-1", run="run-1", job_id="job-1", rbl_id="rbl-1"):
    """Engine-ready rbl + recorded handoff + staged valid bundle + SUCCEEDED finalize. Returns the
    finalize result (the SUCCEEDED handoff record)."""
    _ready_rbl(c, ctx, job_id=job_id, rbl_id=rbl_id)
    _record(c, ctx, run=run, job_id=job_id, rbl_id=rbl_id)
    _stage_bundle(c, ctx.tenant.value, ref, job_id=job_id)
    return ppr.finalize_manifest_handoff(job_id, run, ppr.ManifestHandoffFinalize(bundle_ref=ref),
                                         ctx=ctx, c=c)


# --------------------------------------------------------------------------- #
# Slice 3 — manifest handoff record / finalize.
# --------------------------------------------------------------------------- #
def test_handoff_record_is_attempted_no_slots(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    _ready_rbl(c, ctx)
    h = _record(c, ctx)
    assert h["status"] == ATTEMPTED and h["engine_run_id"] == "run-1"
    job = ppr.get_processing_job("job-1", ctx=ctx, c=c)
    assert job["slots"]["redline_manifest"] is None and job["slots"]["artifact_bundle"] is None


def test_handoff_record_requires_rbl_is_404(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    _seed_job(c, ctx)                                        # job but no reviewed_bore_log
    with pytest.raises(HTTPException) as exc:
        ppr.record_manifest_handoff("job-1", ppr.ManifestHandoffRecord(
            reviewed_bore_log_id="rbl-missing", engine_run_id="run-1", engine_run_status="completed"),
            ctx=ctx, c=c)
    assert exc.value.status_code == 404


def test_handoff_record_duplicate_is_409(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    _ready_rbl(c, ctx)
    _record(c, ctx)
    with pytest.raises(HTTPException) as exc:
        _record(c, ctx)
    assert exc.value.status_code == 409


def test_handoff_finalize_success_attaches_slots(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    h = _finalized_job(c, ctx)
    assert h["status"] == SUCCEEDED
    assert h["manifest_attachment"]["validation_status"] == "VALIDATED"
    bid = h["artifact_bundle_attachment"]["bundle_id"]
    job = ppr.get_processing_job("job-1", ctx=ctx, c=c)
    assert job["slots"]["redline_manifest"]["ref"]["bundle_id"] == bid
    assert job["slots"]["artifact_bundle"]["ref"]["bundle_id"] == bid
    assert job["slots"]["export_package"] is None           # never touched by this lane


def test_handoff_finalize_rejected_when_not_engine_ready(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    _seed_reviewed_bore_log(c, ctx)                          # rbl exists but is NOT engine-ready
    _record(c, ctx)
    _stage_bundle(c, "cp-aaa", "bundle-1")
    h = ppr.finalize_manifest_handoff("job-1", "run-1", ppr.ManifestHandoffFinalize(bundle_ref="bundle-1"),
                                      ctx=ctx, c=c)
    assert h["status"] == REJECTED and h["errors"]
    job = ppr.get_processing_job("job-1", ctx=ctx, c=c)
    assert job["slots"]["redline_manifest"] is None and job["slots"]["artifact_bundle"] is None


def test_handoff_finalize_failed_on_mock_bundle(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    _ready_rbl(c, ctx)
    _record(c, ctx)
    _stage_bundle(c, "cp-aaa", "bundle-1", mock_example=True)   # fake -> contract rejects -> FAILED
    h = ppr.finalize_manifest_handoff("job-1", "run-1", ppr.ManifestHandoffFinalize(bundle_ref="bundle-1"),
                                      ctx=ctx, c=c)
    assert h["status"] == FAILED and h["errors"]
    assert ppr.get_processing_job("job-1", ctx=ctx, c=c)["slots"]["artifact_bundle"] is None


def test_finalize_unsafe_bundle_ref_is_400(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    _ready_rbl(c, ctx)
    _record(c, ctx)
    with pytest.raises(HTTPException) as exc:                # traversal-shaped ref rejected before any FS use
        ppr.finalize_manifest_handoff("job-1", "run-1",
            ppr.ManifestHandoffFinalize(bundle_ref="../escape"), ctx=ctx, c=c)
    assert exc.value.status_code == 400


def test_finalize_missing_handoff_is_404(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    _ready_rbl(c, ctx)
    _stage_bundle(c, "cp-aaa", "bundle-1")
    with pytest.raises(HTTPException) as exc:                # never recorded run-1
        ppr.finalize_manifest_handoff("job-1", "run-1",
            ppr.ManifestHandoffFinalize(bundle_ref="bundle-1"), ctx=ctx, c=c)
    assert exc.value.status_code == 404


def test_finalize_terminal_is_409(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    _finalized_job(c, ctx)                                   # run-1 SUCCEEDED (terminal)
    with pytest.raises(HTTPException) as exc:
        ppr.finalize_manifest_handoff("job-1", "run-1",
            ppr.ManifestHandoffFinalize(bundle_ref="bundle-1"), ctx=ctx, c=c)
    assert exc.value.status_code == 409


# --------------------------------------------------------------------------- #
# Slice 3 — proof reads (redline manifest, artifact listing, artifact serving).
# --------------------------------------------------------------------------- #
def test_redline_manifest_requires_validated_handoff(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    _ready_rbl(c, ctx)
    with pytest.raises(HTTPException) as exc:                # nothing finalized yet -> no slot
        ppr.get_redline_manifest("job-1", ctx=ctx, c=c)
    assert exc.value.status_code == 404
    _record(c, ctx)
    _stage_bundle(c, "cp-aaa", "bundle-1")
    ppr.finalize_manifest_handoff("job-1", "run-1", ppr.ManifestHandoffFinalize(bundle_ref="bundle-1"),
                                  ctx=ctx, c=c)
    slot = ppr.get_redline_manifest("job-1", ctx=ctx, c=c)
    assert slot["ref"]["validation_status"] == "VALIDATED" and len(slot["ref"]["manifest_sha256"]) == 64


def test_artifacts_list_only_manifest_backed(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    _finalized_job(c, ctx)
    out = ppr.list_artifacts("job-1", ctx=ctx, c=c)
    assert out["bundle_id"].startswith("proj-a-rc-0-")
    assert {a["path"] for a in out["artifacts"]} == {ART_PATH}   # ONLY the drawn FINAL_REDLINE_PNG
    a = out["artifacts"][0]
    assert a["log_id"] == "logA" and a["kind"] == "FINAL_REDLINE_PNG" and len(a["sha256"]) == 64


def test_artifacts_require_validated_handoff_is_404(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    _ready_rbl(c, ctx)                                       # no finalize -> no artifact_bundle slot
    with pytest.raises(HTTPException) as exc:
        ppr.list_artifacts("job-1", ctx=ctx, c=c)
    assert exc.value.status_code == 404


def test_artifact_serve_manifest_backed(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    _finalized_job(c, ctx)
    resp = ppr.get_artifact("job-1", ART_PATH, ctx=ctx, c=c)
    assert isinstance(resp, FileResponse) and resp.media_type == "image/png"
    assert Path(resp.path).is_file() and Path(resp.path).name == "logA_s1_redline_stroke.png"


def test_artifact_serve_non_manifest_path_is_404(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    _finalized_job(c, ctx)
    with pytest.raises(HTTPException) as exc:                # not a manifest-listed artifact path
        ppr.get_artifact("job-1", "artifacts/logA/not_in_manifest.png", ctx=ctx, c=c)
    assert exc.value.status_code == 404


# --------------------------------------------------------------------------- #
# Slice 3 — tenant isolation across the whole handoff/proof surface.
# --------------------------------------------------------------------------- #
def test_slice3_tenant_isolation_b_cannot_address_a(tmp_path):
    c = _container(tmp_path)
    ctx_a, ctx_b = _ctx("cp-aaa"), _ctx("cp-bbb")
    _finalized_job(c, ctx_a)                                 # A: finalized job-1 with an attached bundle
    # B addresses A's job-1 / run-1 by the same ids, but B's scope is empty -> 404 everywhere
    with pytest.raises(HTTPException) as e_rec:
        ppr.record_manifest_handoff("job-1", ppr.ManifestHandoffRecord(
            reviewed_bore_log_id="rbl-1", engine_run_id="run-2", engine_run_status="x"), ctx=ctx_b, c=c)
    assert e_rec.value.status_code == 404
    with pytest.raises(HTTPException) as e_fin:
        ppr.finalize_manifest_handoff("job-1", "run-1",
            ppr.ManifestHandoffFinalize(bundle_ref="bundle-1"), ctx=ctx_b, c=c)
    assert e_fin.value.status_code == 404
    with pytest.raises(HTTPException) as e_man:
        ppr.get_redline_manifest("job-1", ctx=ctx_b, c=c)
    assert e_man.value.status_code == 404
    with pytest.raises(HTTPException) as e_list:
        ppr.list_artifacts("job-1", ctx=ctx_b, c=c)
    assert e_list.value.status_code == 404
    with pytest.raises(HTTPException) as e_art:
        ppr.get_artifact("job-1", ART_PATH, ctx=ctx_b, c=c)
    assert e_art.value.status_code == 404
    # A still reads its own bundle
    assert ppr.list_artifacts("job-1", ctx=ctx_a, c=c)["artifacts"][0]["log_id"] == "logA"


# --------------------------------------------------------------------------- #
# Slice 4 helpers (advance the job lifecycle into the billing/closeout range; server cost rules).
# --------------------------------------------------------------------------- #
def _advance_job_to(c, ctx, target, *, job_id="job-1"):
    """Walk the job lifecycle forward to `target` via the transition route (uploads must already be done)."""
    for st in (UPLOADING, EXTRACTING, AWAITING_REVIEW, PLACING, PLACED, CLOSEOUT_REVIEW):
        ppr.transition_processing_job(job_id, ppr.JobTransition(to_status=st), ctx=ctx, c=c)
        if st == target:
            return


def _write_cost_rules(c, *, base_unit_cost="2.50"):
    """Write a deployment cost-rule fixture to the server-configured path (the 'server fixture' pattern)."""
    rules = {"version": "v1", "currency": "USD", "minor_unit_digits": 2,
             "rules": [{"code": "BASE_FOOTAGE", "kind": "BASE", "unit": "ft",
                        "unit_cost": base_unit_cost, "label": "Base footage"}]}
    Path(c.settings.product_billing_cost_rules_path).write_text(json.dumps(rules), encoding="utf-8")


# --------------------------------------------------------------------------- #
# Slice 4 — KMZ export safety (read/evaluate; never fakes coordinates).
# --------------------------------------------------------------------------- #
def test_kmz_export_pixel_only_is_blocked_no_coords(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    _finalized_job(c, ctx)                                   # attaches a validated pixel-only manifest
    rec = ppr.get_kmz_export("job-1", ctx=ctx, c=c)
    assert rec["status"] == "BLOCKED"
    assert "UNSUPPORTED_PIXEL_ONLY" in {b["code"] for b in rec["blockers"]}
    assert rec["kml"] is None and rec["crs"] is None and rec["features"] == []   # no invented coordinates


def test_kmz_export_missing_manifest_slot_is_blocked(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    _seed_job(c, ctx)                                        # no handoff -> no output slots
    rec = ppr.get_kmz_export("job-1", ctx=ctx, c=c)
    assert rec["status"] == "BLOCKED"
    assert "MISSING_MANIFEST_SLOT" in {b["code"] for b in rec["blockers"]}


# --------------------------------------------------------------------------- #
# Slice 4 — closeout evaluate/read (server-derived status; NO privileged transitions).
# --------------------------------------------------------------------------- #
def test_closeout_evaluate_creates_and_is_server_derived(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    _seed_job(c, ctx)                                        # job CREATED -> not in closeout range
    rec = ppr.evaluate_closeout_route("job-1", ctx=ctx, c=c)
    assert rec["status"] == "BLOCKED"                        # derived from the server gate, not the client
    assert "JOB_NOT_IN_CLOSEOUT_RANGE" in {b["code"] for b in rec["gate"]["hard_blockers"]}


def test_closeout_read_returns_record_and_summary(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    _seed_job(c, ctx)
    ppr.evaluate_closeout_route("job-1", ctx=ctx, c=c)
    out = ppr.get_closeout("job-1", ctx=ctx, c=c)
    assert out["status"] == "BLOCKED" and out["summary"]["status"] == "BLOCKED"
    assert out["summary"]["is_blocked"] is True


def test_closeout_read_missing_is_404(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    _seed_job(c, ctx)
    with pytest.raises(HTTPException) as exc:
        ppr.get_closeout("job-1", ctx=ctx, c=c)
    assert exc.value.status_code == 404


def test_no_privileged_closeout_routes(tmp_path):
    # ONLY evaluate + read closeout routes exist (plus the Phase 9 workflow orchestrator, which EVALUATES
    # closeout — NOT a privileged transition) — no lock/approve/close/reject/reopen/unlock surface.
    app = create_app(_settings(tmp_path, enabled=True))
    closeout_paths = {r.path for r in _product_routes(app) if "/closeout" in r.path}
    assert closeout_paths == {"/v2/product/jobs/{job_id}/closeout",
                              "/v2/product/jobs/{job_id}/closeout/evaluate",
                              "/v2/product/jobs/{job_id}/workflow/closeout"}


# --------------------------------------------------------------------------- #
# Slice 4 — billing compute/read (server-side cost rules only; never client billing truth).
# --------------------------------------------------------------------------- #
def test_billing_compute_uses_server_cost_rules(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    _finalized_job(c, ctx)
    _advance_job_to(c, ctx, PLACED)                          # into the billing range
    _write_cost_rules(c, base_unit_cost="2.50")
    rec = ppr.compute_billing_route("job-1", ctx=ctx, c=c)
    assert rec["status"] == "COMPUTED"                       # no hard blockers; closeout missing -> not FINAL
    cur = next(r for r in rec["revisions"] if r["revision_id"] == rec["current_revision_id"])
    base = next(cl for cl in cur["charge_lines"] if cl["kind"] == "BASE")
    assert base["unit_cost"] == "2.50"                       # the SERVER fixture rate (client supplies none)
    assert rec["currency"] == "USD"


def test_billing_compute_unconfigured_is_400(tmp_path):
    settings = dataclasses.replace(_settings(tmp_path, enabled=True), product_billing_cost_rules_path=None)
    c, ctx = create_app(settings).state.tl2, _ctx("cp-aaa")
    _seed_job(c, ctx)
    with pytest.raises(HTTPException) as exc:                # billing refuses without server-configured rules
        ppr.compute_billing_route("job-1", ctx=ctx, c=c)
    assert exc.value.status_code == 400


def test_billing_read_after_compute(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    _finalized_job(c, ctx)
    _advance_job_to(c, ctx, PLACED)
    _write_cost_rules(c)
    ppr.compute_billing_route("job-1", ctx=ctx, c=c)
    out = ppr.get_billing("job-1", ctx=ctx, c=c)
    assert out["view"]["status"] == "COMPUTED" and out["view"]["currency"] == "USD"


def test_billing_read_missing_is_404(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    _seed_job(c, ctx)
    with pytest.raises(HTTPException) as exc:
        ppr.get_billing("job-1", ctx=ctx, c=c)
    assert exc.value.status_code == 404


# --------------------------------------------------------------------------- #
# Slice 4 — export package assemble/read (descriptor of references; never generates files).
# --------------------------------------------------------------------------- #
def test_export_package_assemble_is_descriptor_no_files(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    _finalized_job(c, ctx)
    _advance_job_to(c, ctx, PLACED)
    rec = ppr.assemble_export_package_route("job-1", ctx=ctx, c=c)
    assert rec["status"] == "ASSEMBLED" and rec["current_revision_id"]   # closeout missing -> not READY/FINAL
    view = ppr.get_export_package("job-1", ctx=ctx, c=c)["view"]
    assert "REDLINE_MANIFEST" in view["included_sections"]
    assert "CLOSEOUT_REVIEW" in view["omitted_sections"]
    # the package is a DESCRIPTOR — no rendered/exported binary is generated anywhere under the job
    jdir = job_dir(c.settings.product_store_root, "cp-aaa", "job-1")
    generated = [p.name for p in jdir.rglob("*")
                 if p.suffix.lower() in (".pdf", ".html", ".zip", ".kmz", ".docx")]
    assert generated == []


def test_export_package_read_missing_is_404(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    _seed_job(c, ctx)
    with pytest.raises(HTTPException) as exc:
        ppr.get_export_package("job-1", ctx=ctx, c=c)
    assert exc.value.status_code == 404


def test_closeout_pdf_route_not_ready_without_bundle_is_409(tmp_path):
    """The closeout PDF route returns a SPECIFIC not-ready 409 (never a fake packet) when the job has no
    validated redline bundle yet."""
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    _seed_job(c, ctx)
    with pytest.raises(HTTPException) as exc:
        ppr.download_closeout_pdf("job-1", ctx=ctx, c=c)
    assert exc.value.status_code == 409
    assert "no validated redline bundle" in str(exc.value.detail)


def test_gis_route_route_honest_when_absent(tmp_path):
    """The gis-route read returns an honest NO_GIS_ROUTE_UPLOADED state (never invents) for a job with no
    GIS_ROUTE upload, and 404 for a missing job."""
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    _seed_job(c, ctx)
    r = ppr.get_gis_route("job-1", ctx=ctx, c=c)
    assert r["present"] is False and r["reason"] == "NO_GIS_ROUTE_UPLOADED" and r["features"] == []
    with pytest.raises(HTTPException) as exc:
        ppr.get_gis_route("nope", ctx=ctx, c=c)
    assert exc.value.status_code == 404


def test_gis_route_download_kmz_present_and_honest_409_when_absent(tmp_path):
    """The route-export endpoint serves a Google-Earth-openable KMZ of the UPLOADED route when one is present,
    an honest 409 (never a faked file) when the job has no usable GIS_ROUTE, and 404 for a missing job."""
    import base64
    import io
    import zipfile
    from truelinev2.contracts.kmz_export import KMZ_MEDIA_TYPE, validate_kmz_bytes
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    ppr.create_project(ppr.ProjectCreate(display_name="Label"), ctx=ctx, c=c)
    ppr.create_processing_job(ppr.JobCreate(job_id="job-1"), ctx=ctx, c=c)
    with pytest.raises(HTTPException) as exc:                       # no GIS_ROUTE yet -> honest 409
        ppr.download_gis_route("job-1", ctx=ctx, c=c)
    assert exc.value.status_code == 409
    with pytest.raises(HTTPException) as exc2:                      # missing job -> 404
        ppr.download_gis_route("nope", ctx=ctx, c=c)
    assert exc2.value.status_code == 404
    kml = (b'<?xml version="1.0"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
           b'<Placemark><name>R</name><LineString><coordinates>-96.1,30.1 -96.2,30.2</coordinates>'
           b'</LineString></Placemark></Document></kml>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("doc.kml", kml)
    b64 = base64.b64encode(buf.getvalue()).decode()
    ppr.register_upload("job-1", ppr.UploadRegister(kind="GIS_ROUTE", filename="route.kmz", content_base64=b64),
                        ctx=ctx, c=c)
    resp = ppr.download_gis_route("job-1", ctx=ctx, c=c)            # uploaded route -> real KMZ
    assert resp.media_type == KMZ_MEDIA_TYPE
    assert validate_kmz_bytes(resp.body)["valid"] is True


# --------------------------------------------------------------------------- #
# Slice 4 — tenant isolation across the whole status/closeout/billing/export surface.
# --------------------------------------------------------------------------- #
def test_slice4_tenant_isolation_b_cannot_address_a(tmp_path):
    c = _container(tmp_path)
    ctx_a, ctx_b = _ctx("cp-aaa"), _ctx("cp-bbb")
    _finalized_job(c, ctx_a)
    _advance_job_to(c, ctx_a, PLACED)
    _write_cost_rules(c)
    ppr.evaluate_closeout_route("job-1", ctx=ctx_a, c=c)
    ppr.compute_billing_route("job-1", ctx=ctx_a, c=c)
    ppr.assemble_export_package_route("job-1", ctx=ctx_a, c=c)
    # B (empty scope) cannot touch A's job-1 via any Slice 4 route
    for call in (
        lambda: ppr.get_kmz_export("job-1", ctx=ctx_b, c=c),
        lambda: ppr.evaluate_closeout_route("job-1", ctx=ctx_b, c=c),
        lambda: ppr.get_closeout("job-1", ctx=ctx_b, c=c),
        lambda: ppr.compute_billing_route("job-1", ctx=ctx_b, c=c),
        lambda: ppr.get_billing("job-1", ctx=ctx_b, c=c),
        lambda: ppr.assemble_export_package_route("job-1", ctx=ctx_b, c=c),
        lambda: ppr.get_export_package("job-1", ctx=ctx_b, c=c),
        lambda: ppr.download_closeout_pdf("job-1", ctx=ctx_b, c=c),
        lambda: ppr.get_gis_route("job-1", ctx=ctx_b, c=c),
        lambda: ppr.download_gis_route("job-1", ctx=ctx_b, c=c),
    ):
        with pytest.raises(HTTPException) as exc:
            call()
        assert exc.value.status_code == 404
    # A still reads its own
    assert ppr.get_closeout("job-1", ctx=ctx_a, c=c)["status"] in ("BLOCKED", "READY_FOR_APPROVAL")


# --------------------------------------------------------------------------- #
# Slice B — reviewed_bore_log full-record read route + route-driven gate flow.
# --------------------------------------------------------------------------- #
def _bore_log_upload(c, ctx, job_id="job-1"):
    """Project + job + one BORE_LOG upload; returns its upload_id (the rbl source)."""
    ppr.create_project(ppr.ProjectCreate(display_name="Label"), ctx=ctx, c=c)
    ppr.create_processing_job(ppr.JobCreate(job_id=job_id), ctx=ctx, c=c)
    b64 = base64.b64encode(b"row_id,start_station,end_station\n").decode()
    up = ppr.register_upload(
        job_id, ppr.UploadRegister(kind="BORE_LOG", filename="bores.csv", content_base64=b64),
        ctx=ctx, c=c)
    return up["upload_id"]


def _manual_row(row_id, upload_id, start, end):
    return ppr.ExtractedRowInput(
        row_id=row_id, source_upload_id=upload_id,
        raw={"start_station": start, "end_station": end},
        normalized={"start_station": start, "end_station": end},
        extraction_method=MANUAL_ENTRY)


def test_get_reviewed_bore_log_full_record(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    up = _bore_log_upload(c, ctx)
    ppr.create_bore_log_review(
        "job-1", ppr.ReviewedBoreLogCreate(reviewed_bore_log_id="rbl-main", source_upload_id=up),
        ctx=ctx, c=c)
    ppr.add_rows("job-1", "rbl-main", ppr.RowsAdd(rows=[_manual_row("row-1", up, "0+00", "2+99")]),
                 ctx=ctx, c=c)
    rec = ppr.get_reviewed_bore_log_record("job-1", "rbl-main", ctx=ctx, c=c)
    assert rec["reviewed_bore_log_id"] == "rbl-main" and rec["source_upload_id"] == up
    assert len(rec["rows"]) == 1 and rec["rows"][0]["row_id"] == "row-1"
    assert rec["rows"][0]["raw"]["start_station"] == "0+00"          # persisted values are returned
    assert rec["rows"][0]["review"]["status"] == UNREVIEWED
    assert rec["groups"] == []


def test_get_reviewed_bore_log_missing_is_404(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    _bore_log_upload(c, ctx)
    with pytest.raises(HTTPException) as exc:
        ppr.get_reviewed_bore_log_record("job-1", "nope", ctx=ctx, c=c)
    assert exc.value.status_code == 404


def test_get_reviewed_bore_log_tenant_isolation(tmp_path):
    c = _container(tmp_path)
    a, b = _ctx("cp-aaa"), _ctx("cp-bbb")
    up = _bore_log_upload(c, a)
    ppr.create_bore_log_review(
        "job-1", ppr.ReviewedBoreLogCreate(reviewed_bore_log_id="rbl-main", source_upload_id=up),
        ctx=a, c=c)
    ppr.create_project(ppr.ProjectCreate(display_name="B"), ctx=b, c=c)
    ppr.create_processing_job(ppr.JobCreate(job_id="job-1"), ctx=b, c=c)
    with pytest.raises(HTTPException) as exc:                        # B cannot resolve A's rbl
        ppr.get_reviewed_bore_log_record("job-1", "rbl-main", ctx=b, c=c)
    assert exc.value.status_code == 404


def test_route_flow_reaches_engine_ready_true(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    up = _bore_log_upload(c, ctx)
    ppr.create_bore_log_review(
        "job-1", ppr.ReviewedBoreLogCreate(reviewed_bore_log_id="rbl-main", source_upload_id=up),
        ctx=ctx, c=c)
    ppr.add_rows("job-1", "rbl-main", ppr.RowsAdd(rows=[
        _manual_row("row-1", up, "0+00", "2+99"), _manual_row("row-2", up, "3+00", "5+00")]),
        ctx=ctx, c=c)
    for rid in ("row-1", "row-2"):
        ppr.review_row_route("job-1", "rbl-main", rid, ppr.RowReview(to_status=CONFIRMED), ctx=ctx, c=c)
    ppr.define_group("job-1", "rbl-main", ppr.SegmentGroupCreate(
        group_id="grp-1", member_row_ids=["row-1", "row-2"], relation=SEPARATE_BORE), ctx=ctx, c=c)
    ppr.set_group_status("job-1", "rbl-main", "grp-1",
                         ppr.GroupingStatus(to_status=GROUPING_CONFIRMED), ctx=ctx, c=c)
    q = ppr.get_review_queue("job-1", "rbl-main", ctx=ctx, c=c)
    assert q["engine_ready"] is True
    assert set(q["engine_eligible_row_ids"]) == {"row-1", "row-2"}
    assert q["ungrouped_rows"] == [] and q["unresolved_groups"] == [] and q["rows_in_multiple_groups"] == []


def test_route_flow_engine_not_ready_with_blockers(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    up = _bore_log_upload(c, ctx)
    ppr.create_bore_log_review(
        "job-1", ppr.ReviewedBoreLogCreate(reviewed_bore_log_id="rbl-main", source_upload_id=up),
        ctx=ctx, c=c)
    ppr.add_rows("job-1", "rbl-main", ppr.RowsAdd(rows=[
        _manual_row("row-1", up, "0+00", "2+99"), _manual_row("row-2", up, "3+00", "5+00")]),
        ctx=ctx, c=c)
    ppr.review_row_route("job-1", "rbl-main", "row-1", ppr.RowReview(to_status=CONFIRMED), ctx=ctx, c=c)
    # row-2 left UNREVIEWED + no group defined -> honest blockers, not ready
    q = ppr.get_review_queue("job-1", "rbl-main", ctx=ctx, c=c)
    assert q["engine_ready"] is False
    assert "row-2" in q["rows_needing_review"]
    assert set(q["ungrouped_rows"]) == {"row-1", "row-2"}


# --------------------------------------------------------------------------- #
# Slice C — uploaded-corpus engine-handoff readiness route (read-only; renders/creates nothing).
# --------------------------------------------------------------------------- #
def test_engine_handoff_readiness_blocked_with_ready_inputs(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    up = _bore_log_upload(c, ctx)                                          # project + job + BORE_LOG
    ppr.register_upload(                                                   # + a PLAN_PDF upload
        "job-1", ppr.UploadRegister(kind="PLAN_PDF", filename="plan.pdf",
                                    content_base64=base64.b64encode(b"%PDF-1.4 fake").decode()),
        ctx=ctx, c=c)
    ppr.create_bore_log_review(
        "job-1", ppr.ReviewedBoreLogCreate(reviewed_bore_log_id="rbl-main", source_upload_id=up),
        ctx=ctx, c=c)
    ppr.add_rows("job-1", "rbl-main", ppr.RowsAdd(rows=[_manual_row("row-1", up, "0+00", "2+99")]),
                 ctx=ctx, c=c)
    ppr.review_row_route("job-1", "rbl-main", "row-1", ppr.RowReview(to_status=CONFIRMED), ctx=ctx, c=c)
    ppr.define_group("job-1", "rbl-main", ppr.SegmentGroupCreate(
        group_id="grp-1", member_row_ids=["row-1"], relation=SEPARATE_BORE), ctx=ctx, c=c)
    ppr.set_group_status("job-1", "rbl-main", "grp-1",
                         ppr.GroupingStatus(to_status=GROUPING_CONFIRMED), ctx=ctx, c=c)

    r = ppr.get_engine_handoff_readiness("job-1", ctx=ctx, c=c)
    assert r["status"] == "BLOCKED" and r["runnable"] is False
    assert r["checks"] == {"has_plan_pdf": True, "has_engine_ready_reviewed_bore_log": True}
    codes = {b["code"] for b in r["blockers"]}
    assert "ENGINE_HANDOFF_NOT_IMPLEMENTED_FOR_UPLOADED_CORPUS" in codes
    assert "NO_PLAN_PDF_UPLOAD" not in codes and "NO_ENGINE_READY_REVIEWED_BORE_LOG" not in codes
    # proves no mutation: output slots stay null (no handoff/bundle/artifact produced)
    job = ppr.get_processing_job("job-1", ctx=ctx, c=c)
    assert all(v is None for v in job["slots"].values())


def test_engine_handoff_readiness_input_blockers_when_missing(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    _bore_log_upload(c, ctx)                                               # BORE_LOG only; no PLAN_PDF; no rbl
    r = ppr.get_engine_handoff_readiness("job-1", ctx=ctx, c=c)
    assert r["checks"] == {"has_plan_pdf": False, "has_engine_ready_reviewed_bore_log": False}
    codes = {b["code"] for b in r["blockers"]}
    assert {"NO_PLAN_PDF_UPLOAD", "NO_ENGINE_READY_REVIEWED_BORE_LOG",
            "ENGINE_HANDOFF_NOT_IMPLEMENTED_FOR_UPLOADED_CORPUS"} <= codes


def test_engine_handoff_readiness_missing_job_404(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    ppr.create_project(ppr.ProjectCreate(display_name="Label"), ctx=ctx, c=c)
    with pytest.raises(HTTPException) as exc:
        ppr.get_engine_handoff_readiness("nope", ctx=ctx, c=c)
    assert exc.value.status_code == 404


def test_engine_handoff_readiness_tenant_isolation(tmp_path):
    c = _container(tmp_path)
    a, b = _ctx("cp-aaa"), _ctx("cp-bbb")
    _bore_log_upload(c, a)                                                 # A owns job-1
    ppr.create_project(ppr.ProjectCreate(display_name="B"), ctx=b, c=c)
    with pytest.raises(HTTPException) as exc:                              # B has no job-1 -> 404
        ppr.get_engine_handoff_readiness("job-1", ctx=b, c=c)
    assert exc.value.status_code == 404


# --------------------------------------------------------------------------- #
# M2 — human-confirmed source-anchor routes (record + validate; renders nothing).
# A minimal valid blank PDF (1 page, US-Letter 612x792, rotation 0), generated once by PyMuPDF. The TEST
# never imports fitz; it ships these bytes so the route's read-only PlanPdf page-bounds resolution runs on
# a real PDF (page display-space bounds become (0,0,612,792)).
# --------------------------------------------------------------------------- #
_MINIMAL_PLAN_PDF_B64 = (
    "JVBERi0xLjcKJcK1wrYKJSBXcml0dGVuIGJ5IE11UERGIDEuMjcuMgoKMSAwIG9iago8PC9UeXBlL0NhdGFsb2cvUGFnZXMg"
    "MiAwIFIvSW5mbzw8L1Byb2R1Y2VyKE11UERGIDEuMjcuMik+Pj4+CmVuZG9iagoKMiAwIG9iago8PC9UeXBlL1BhZ2VzL0Nv"
    "dW50IDEvS2lkc1s0IDAgUl0+PgplbmRvYmoKCjMgMCBvYmoKPDw+PgplbmRvYmoKCjQgMCBvYmoKPDwvVHlwZS9QYWdlL01l"
    "ZGlhQm94WzAgMCA2MTIgNzkyXS9Sb3RhdGUgMC9SZXNvdXJjZXMgMyAwIFIvUGFyZW50IDIgMCBSPj4KZW5kb2JqCgp4cmVm"
    "CjAgNQowMDAwMDAwMDAwIDY1NTM1IGYgCjAwMDAwMDAwNDIgMDAwMDAgbiAKMDAwMDAwMDEyMCAwMDAwMCBuIAowMDAwMDAw"
    "MTcyIDAwMDAwIG4gCjAwMDAwMDAxOTMgMDAwMDAgbiAKCnRyYWlsZXIKPDwvU2l6ZSA1L1Jvb3QgMSAwIFIvSURbPDI1QzNB"
    "MjRFNEVDMjgwQzJBQzY1QzM4NEMzQTJDMjg1PjwxQjAyRUMzMkUxRDMwNUYzNDJBRjZFMjI2MkYzNTZDND5dPj4Kc3RhcnR4"
    "cmVmCjI4NAolJUVPRgo=")


def _cp(x, y):
    return ppr.ControlPoint(x=x, y=y)


def _source_anchor_ready(c, ctx, *, job_id="job-1", rbl_id="rbl-main"):
    """Project + job + a real PLAN_PDF upload + an engine-ready reviewed_bore_log. Returns the PLAN_PDF
    upload id (the source-anchor's plan_upload_id)."""
    bore = _bore_log_upload(c, ctx, job_id)                  # creates project + job + a BORE_LOG upload
    plan = ppr.register_upload(
        job_id, ppr.UploadRegister(kind="PLAN_PDF", filename="plan.pdf",
                                   content_base64=_MINIMAL_PLAN_PDF_B64), ctx=ctx, c=c)
    ppr.create_bore_log_review(
        job_id, ppr.ReviewedBoreLogCreate(reviewed_bore_log_id=rbl_id, source_upload_id=bore),
        ctx=ctx, c=c)
    ppr.add_rows(job_id, rbl_id, ppr.RowsAdd(rows=[_manual_row("row-1", bore, "0+00", "2+99")]),
                 ctx=ctx, c=c)
    ppr.review_row_route(job_id, rbl_id, "row-1", ppr.RowReview(to_status=CONFIRMED), ctx=ctx, c=c)
    ppr.define_group(job_id, rbl_id, ppr.SegmentGroupCreate(
        group_id="grp-1", member_row_ids=["row-1"], relation=SEPARATE_BORE), ctx=ctx, c=c)
    ppr.set_group_status(job_id, rbl_id, "grp-1", ppr.GroupingStatus(to_status=GROUPING_CONFIRMED),
                         ctx=ctx, c=c)
    return plan["upload_id"]


def test_source_anchor_validated_via_route(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    plan = _source_anchor_ready(c, ctx)
    rec = ppr.create_source_anchor_route("job-1", ppr.SourceAnchorCreate(
        source_anchor_id="sa-1", plan_upload_id=plan, reviewed_bore_log_id="rbl-main",
        page_number=1, control_points=[_cp(100.0, 120.0), _cp(300.0, 340.0)],
        start_identity=ppr.SourceAnchorIdentity(station="0+00", structure_label="HH")),
        ctx=ctx, c=c)
    assert rec["status"] == "VALIDATED" and rec["renderable"] is True and rec["blockers"] == []
    assert rec["provenance"] == "HUMAN_CONFIRMED_CONTROL_POINTS"
    assert rec["coordinate_space"] == "pdf_display_space"
    assert rec["start_identity"] == {"station": "0+00", "structure_label": "HH", "note": None}
    job = ppr.get_processing_job("job-1", ctx=ctx, c=c)                    # proves no output mutation
    assert all(v is None for v in job["slots"].values())


def test_source_anchor_too_few_points_via_route(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    plan = _source_anchor_ready(c, ctx)
    rec = ppr.create_source_anchor_route("job-1", ppr.SourceAnchorCreate(
        source_anchor_id="sa-1", plan_upload_id=plan, reviewed_bore_log_id="rbl-main",
        page_number=1, control_points=[_cp(10.0, 10.0)]), ctx=ctx, c=c)
    assert rec["status"] == "REJECTED"
    assert "CONTROL_POINTS_TOO_FEW" in {b["code"] for b in rec["blockers"]}


def test_source_anchor_out_of_bounds_via_route(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    plan = _source_anchor_ready(c, ctx)
    rec = ppr.create_source_anchor_route("job-1", ppr.SourceAnchorCreate(   # page is 612x792
        source_anchor_id="sa-1", plan_upload_id=plan, reviewed_bore_log_id="rbl-main",
        page_number=1, control_points=[_cp(10.0, 10.0), _cp(99999.0, 5.0)]), ctx=ctx, c=c)
    assert "CONTROL_POINT_OUT_OF_BOUNDS" in {b["code"] for b in rec["blockers"]}


def test_source_anchor_page_not_resolvable_via_route(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    plan = _source_anchor_ready(c, ctx)
    rec = ppr.create_source_anchor_route("job-1", ppr.SourceAnchorCreate(   # PDF has only 1 page
        source_anchor_id="sa-1", plan_upload_id=plan, reviewed_bore_log_id="rbl-main",
        page_number=99, control_points=[_cp(10.0, 10.0), _cp(20.0, 20.0)]), ctx=ctx, c=c)
    assert "PAGE_NOT_RESOLVABLE" in {b["code"] for b in rec["blockers"]}


def test_source_anchor_wrong_upload_kind_via_route(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    _source_anchor_ready(c, ctx)
    job = ppr.get_processing_job("job-1", ctx=ctx, c=c)
    bore = next(u["upload_id"] for u in job["uploads"] if u["kind"] == "BORE_LOG")
    rec = ppr.create_source_anchor_route("job-1", ppr.SourceAnchorCreate(
        source_anchor_id="sa-1", plan_upload_id=bore, reviewed_bore_log_id="rbl-main",
        page_number=1, control_points=[_cp(10.0, 10.0), _cp(20.0, 20.0)]), ctx=ctx, c=c)
    assert "PLAN_UPLOAD_NOT_PLAN_PDF" in {b["code"] for b in rec["blockers"]}


def test_source_anchor_rbl_not_ready_via_route(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    bore = _bore_log_upload(c, ctx)                                        # project + job + BORE_LOG
    plan = ppr.register_upload("job-1", ppr.UploadRegister(
        kind="PLAN_PDF", filename="plan.pdf", content_base64=_MINIMAL_PLAN_PDF_B64), ctx=ctx, c=c)
    ppr.create_bore_log_review("job-1", ppr.ReviewedBoreLogCreate(
        reviewed_bore_log_id="rbl-main", source_upload_id=bore), ctx=ctx, c=c)
    ppr.add_rows("job-1", "rbl-main", ppr.RowsAdd(rows=[_manual_row("row-1", bore, "0+00", "2+99")]),
                 ctx=ctx, c=c)                                             # UNREVIEWED -> not ready
    rec = ppr.create_source_anchor_route("job-1", ppr.SourceAnchorCreate(
        source_anchor_id="sa-1", plan_upload_id=plan["upload_id"], reviewed_bore_log_id="rbl-main",
        page_number=1, control_points=[_cp(10.0, 10.0), _cp(20.0, 20.0)]), ctx=ctx, c=c)
    assert "REVIEWED_BORE_LOG_NOT_ENGINE_READY" in {b["code"] for b in rec["blockers"]}


def test_source_anchor_list_get_and_missing_404(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    plan = _source_anchor_ready(c, ctx)
    ppr.create_source_anchor_route("job-1", ppr.SourceAnchorCreate(
        source_anchor_id="sa-1", plan_upload_id=plan, reviewed_bore_log_id="rbl-main",
        page_number=1, control_points=[_cp(10.0, 10.0), _cp(20.0, 20.0)]), ctx=ctx, c=c)
    listed = ppr.list_source_anchors_route("job-1", ctx=ctx, c=c)
    assert [r["source_anchor_id"] for r in listed["source_anchors"]] == ["sa-1"]
    assert ppr.get_source_anchor_route("job-1", "sa-1", ctx=ctx, c=c)["source_anchor_id"] == "sa-1"
    with pytest.raises(HTTPException) as exc:
        ppr.get_source_anchor_route("job-1", "sa-nope", ctx=ctx, c=c)
    assert exc.value.status_code == 404


def test_source_anchor_duplicate_409_via_route(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    plan = _source_anchor_ready(c, ctx)
    body = ppr.SourceAnchorCreate(
        source_anchor_id="sa-1", plan_upload_id=plan, reviewed_bore_log_id="rbl-main",
        page_number=1, control_points=[_cp(10.0, 10.0), _cp(20.0, 20.0)])
    ppr.create_source_anchor_route("job-1", body, ctx=ctx, c=c)
    with pytest.raises(HTTPException) as exc:
        ppr.create_source_anchor_route("job-1", body, ctx=ctx, c=c)
    assert exc.value.status_code == 409


def test_source_anchor_missing_job_404(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    ppr.create_project(ppr.ProjectCreate(display_name="Label"), ctx=ctx, c=c)
    with pytest.raises(HTTPException) as exc:
        ppr.create_source_anchor_route("nope", ppr.SourceAnchorCreate(
            source_anchor_id="sa-1", plan_upload_id="up-x", reviewed_bore_log_id="rbl-main",
            page_number=1, control_points=[_cp(10.0, 10.0), _cp(20.0, 20.0)]), ctx=ctx, c=c)
    assert exc.value.status_code == 404


def test_source_anchor_tenant_isolation_via_route(tmp_path):
    c = _container(tmp_path)
    a, b = _ctx("cp-aaa"), _ctx("cp-bbb")
    plan = _source_anchor_ready(c, a)                                      # A owns job-1 + sa-1
    ppr.create_source_anchor_route("job-1", ppr.SourceAnchorCreate(
        source_anchor_id="sa-1", plan_upload_id=plan, reviewed_bore_log_id="rbl-main",
        page_number=1, control_points=[_cp(10.0, 10.0), _cp(20.0, 20.0)]), ctx=a, c=c)
    ppr.create_project(ppr.ProjectCreate(display_name="B"), ctx=b, c=c)
    with pytest.raises(HTTPException) as exc:                              # B cannot read A's anchor
        ppr.get_source_anchor_route("job-1", "sa-1", ctx=b, c=c)
    assert exc.value.status_code == 404
    assert ppr.list_source_anchors_route("job-1", ctx=b, c=c) == {"source_anchors": []}


# --------------------------------------------------------------------------- #
# M2 — uploaded PLAN_PDF page display (metadata + raster; no redline, no artifacts).
# --------------------------------------------------------------------------- #
def _plan_pdf_only(c, ctx, *, job_id="job-1"):
    """Project + job + one real PLAN_PDF upload. Returns the PLAN_PDF upload id."""
    ppr.create_project(ppr.ProjectCreate(display_name="Label"), ctx=ctx, c=c)
    ppr.create_processing_job(ppr.JobCreate(job_id=job_id), ctx=ctx, c=c)
    plan = ppr.register_upload(job_id, ppr.UploadRegister(
        kind="PLAN_PDF", filename="plan.pdf", content_base64=_MINIMAL_PLAN_PDF_B64), ctx=ctx, c=c)
    return plan["upload_id"]


def test_plan_page_metadata_happy(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    plan = _plan_pdf_only(c, ctx)
    meta = ppr.get_plan_page_metadata("job-1", plan, ctx=ctx, c=c)
    assert meta["plan_upload_id"] == plan and meta["page_count"] == 1
    page = meta["pages"][0]
    assert page["page_number"] == 1
    assert page["bounds"] == {"x0": 0.0, "y0": 0.0, "x1": 612.0, "y1": 792.0}
    assert page["width"] == 612.0 and page["height"] == 792.0
    assert page["zoom"] == 2.0 and page["raster_width"] == 1224 and page["raster_height"] == 1584


def test_plan_page_metadata_wrong_kind_400(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    bore = _bore_log_upload(c, ctx)                                        # project + job + BORE_LOG
    with pytest.raises(HTTPException) as exc:
        ppr.get_plan_page_metadata("job-1", bore, ctx=ctx, c=c)
    assert exc.value.status_code == 400


def test_plan_page_metadata_missing_upload_404(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    _plan_pdf_only(c, ctx)
    with pytest.raises(HTTPException) as exc:
        ppr.get_plan_page_metadata("job-1", "up-nope", ctx=ctx, c=c)
    assert exc.value.status_code == 404


def test_plan_page_metadata_tenant_isolation(tmp_path):
    c = _container(tmp_path)
    a, b = _ctx("cp-aaa"), _ctx("cp-bbb")
    plan = _plan_pdf_only(c, a)
    ppr.create_project(ppr.ProjectCreate(display_name="B"), ctx=b, c=c)
    with pytest.raises(HTTPException) as exc:                              # B has no job-1 -> 404
        ppr.get_plan_page_metadata("job-1", plan, ctx=b, c=c)
    assert exc.value.status_code == 404


def test_plan_page_raster_happy_returns_png(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    plan = _plan_pdf_only(c, ctx)
    resp = ppr.get_plan_page_raster("job-1", plan, 1, ctx=ctx, c=c)
    assert resp.status_code == 200 and resp.media_type == "image/png"
    assert resp.body[:4] == b"\x89PNG"                                    # real PNG bytes, in-memory
    # nothing written to disk (the raster is response bytes, not an artifact)
    assert list(Path(c.settings.product_store_root).rglob("*.png")) == []


def test_plan_page_raster_wrong_kind_400(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    bore = _bore_log_upload(c, ctx)
    with pytest.raises(HTTPException) as exc:
        ppr.get_plan_page_raster("job-1", bore, 1, ctx=ctx, c=c)
    assert exc.value.status_code == 400


def test_plan_page_raster_missing_page_404(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    plan = _plan_pdf_only(c, ctx)
    with pytest.raises(HTTPException) as exc:
        ppr.get_plan_page_raster("job-1", plan, 99, ctx=ctx, c=c)         # PDF has 1 page
    assert exc.value.status_code == 404


def test_plan_page_raster_tenant_isolation(tmp_path):
    c = _container(tmp_path)
    a, b = _ctx("cp-aaa"), _ctx("cp-bbb")
    plan = _plan_pdf_only(c, a)
    ppr.create_project(ppr.ProjectCreate(display_name="B"), ctx=b, c=c)
    with pytest.raises(HTTPException) as exc:
        ppr.get_plan_page_raster("job-1", plan, 1, ctx=b, c=c)
    assert exc.value.status_code == 404


def test_plan_pages_create_no_output_or_artifacts(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    plan = _plan_pdf_only(c, ctx)
    ppr.get_plan_page_metadata("job-1", plan, ctx=ctx, c=c)
    ppr.get_plan_page_raster("job-1", plan, 1, ctx=ctx, c=c)
    job = ppr.get_processing_job("job-1", ctx=ctx, c=c)
    assert all(v is None for v in job["slots"].values())                  # no output slots
    jd = job_dir(c.settings.product_store_root, "cp-aaa", "job-1")
    assert not (jd / "bundle_store").exists() and not (jd / "handoffs").exists()
    assert list(jd.rglob("*.png")) == []                                  # nothing rendered to disk


# --------------------------------------------------------------------------- #
# M2 — render a validated source anchor into the job's human-confirmed redline bundle.
# --------------------------------------------------------------------------- #
def _validated_anchor(c, ctx, *, sa_id="sa-1", points=None):
    plan = _source_anchor_ready(c, ctx)                                    # job-1 + PLAN_PDF + engine-ready rbl
    rec = ppr.create_source_anchor_route("job-1", ppr.SourceAnchorCreate(
        source_anchor_id=sa_id, plan_upload_id=plan, reviewed_bore_log_id="rbl-main",
        page_number=1, control_points=points or [_cp(100.0, 120.0), _cp(300.0, 340.0)],
        start_identity=ppr.SourceAnchorIdentity(station="0+00", structure_label="HH")), ctx=ctx, c=c)
    assert rec["status"] == "VALIDATED"
    return plan


def test_render_route_happy_produces_real_bundle(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    _validated_anchor(c, ctx)
    summary = ppr.render_source_anchor_route("job-1", "sa-1", ctx=ctx, c=c)
    assert summary["status"] == "SUCCEEDED" and summary["bundle_id"]
    assert summary["bundle_origin"] == "HUMAN_CONFIRMED_SOURCE_ANCHOR"
    assert summary["artifact_count"] == 1 and summary["source_anchor_ids"] == ["sa-1"]
    art = summary["artifacts"][0]
    assert art["kind"] == "FINAL_REDLINE_PNG" and len(art["sha256"]) == 64 and art["bytes"] > 0
    # job output slots set through the existing handoff
    job = ppr.get_processing_job("job-1", ctx=ctx, c=c)
    assert job["slots"]["redline_manifest"] is not None
    assert job["slots"]["artifact_bundle"] is not None
    # existing artifact list + serve routes surface the real PNG
    listed = ppr.list_artifacts("job-1", ctx=ctx, c=c)
    assert any(a["path"] == art["path"] for a in listed["artifacts"])
    resp = ppr.get_artifact("job-1", art["path"], ctx=ctx, c=c)
    assert Path(resp.path).read_bytes()[:4] == b"\x89PNG"                  # real PNG bytes served


def test_render_route_rejects_unvalidated_anchor(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    plan = _source_anchor_ready(c, ctx)
    ppr.create_source_anchor_route("job-1", ppr.SourceAnchorCreate(   # 1 point -> REJECTED
        source_anchor_id="sa-bad", plan_upload_id=plan, reviewed_bore_log_id="rbl-main",
        page_number=1, control_points=[_cp(10.0, 10.0)]), ctx=ctx, c=c)
    with pytest.raises(HTTPException) as exc:
        ppr.render_source_anchor_route("job-1", "sa-bad", ctx=ctx, c=c)
    assert exc.value.status_code == 409
    job = ppr.get_processing_job("job-1", ctx=ctx, c=c)                    # no slots set on reject
    assert all(v is None for v in job["slots"].values())


def test_render_route_rejects_stale_rbl(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    _validated_anchor(c, ctx)
    # make the reviewed bore-log no longer engine-ready: add a second UNREVIEWED row
    up = next(u["upload_id"] for u in ppr.get_processing_job("job-1", ctx=ctx, c=c)["uploads"]
              if u["kind"] == "BORE_LOG")
    ppr.add_rows("job-1", "rbl-main", ppr.RowsAdd(rows=[_manual_row("row-2", up, "3+00", "4+00")]),
                 ctx=ctx, c=c)
    with pytest.raises(HTTPException) as exc:
        ppr.render_source_anchor_route("job-1", "sa-1", ctx=ctx, c=c)
    assert exc.value.status_code == 409
    job = ppr.get_processing_job("job-1", ctx=ctx, c=c)
    assert all(v is None for v in job["slots"].values())                  # no render, no slots


def test_render_route_renders_all_validated_anchors(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    plan = _validated_anchor(c, ctx, sa_id="sa-1")
    ppr.create_source_anchor_route("job-1", ppr.SourceAnchorCreate(       # second validated anchor
        source_anchor_id="sa-2", plan_upload_id=plan, reviewed_bore_log_id="rbl-main",
        page_number=1, control_points=[_cp(50.0, 60.0), _cp(70.0, 80.0)]), ctx=ctx, c=c)
    summary = ppr.render_source_anchor_route("job-1", "sa-1", ctx=ctx, c=c)   # trigger on sa-1
    assert summary["status"] == "SUCCEEDED"
    assert summary["artifact_count"] == 2 and summary["source_anchor_ids"] == ["sa-1", "sa-2"]


def test_render_route_missing_anchor_404(tmp_path):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    _source_anchor_ready(c, ctx)
    with pytest.raises(HTTPException) as exc:
        ppr.render_source_anchor_route("job-1", "sa-nope", ctx=ctx, c=c)
    assert exc.value.status_code == 404


def test_render_route_tenant_isolation(tmp_path):
    c = _container(tmp_path)
    a, b = _ctx("cp-aaa"), _ctx("cp-bbb")
    _validated_anchor(c, a)                                                # A owns job-1 + sa-1
    ppr.create_project(ppr.ProjectCreate(display_name="B"), ctx=b, c=c)
    with pytest.raises(HTTPException) as exc:                              # B cannot render A's anchor
        ppr.render_source_anchor_route("job-1", "sa-1", ctx=b, c=c)
    assert exc.value.status_code == 404


# --------------------------------------------------------------------------- #
# Phase 6 — REVIEW acceptance lane routes (engine generates candidate; human accepts/rejects).
# The heavy engine + renderer are monkeypatched (uce flows through), so the route wiring + state machine
# are exercised over real product-store records. Name-free.
# --------------------------------------------------------------------------- #
_RA_PDF = base64.b64decode(
    "JVBERi0xLjcKJcK1wrYKJSBXcml0dGVuIGJ5IE11UERGIDEuMjcuMgoKMSAwIG9iago8PC9UeXBlL0NhdGFsb2cvUGFnZXMg"
    "MiAwIFIvSW5mbzw8L1Byb2R1Y2VyKE11UERGIDEuMjcuMik+Pj4+CmVuZG9iagoKMiAwIG9iago8PC9UeXBlL1BhZ2VzL0Nv"
    "dW50IDEvS2lkc1s0IDAgUl0+PgplbmRvYmoKCjMgMCBvYmoKPDw+PgplbmRvYmoKCjQgMCBvYmoKPDwvVHlwZS9QYWdlL01l"
    "ZGlhQm94WzAgMCA2MTIgNzkyXS9Sb3RhdGUgMC9SZXNvdXJjZXMgMyAwIFIvUGFyZW50IDIgMCBSPj4KZW5kb2JqCgp4cmVm"
    "CjAgNQowMDAwMDAwMDAwIDY1NTM1IGYgCjAwMDAwMDAwNDIgMDAwMDAgbiAKMDAwMDAwMDEyMCAwMDAwMCBuIAowMDAwMDAw"
    "MTcyIDAwMDAwIG4gCjAwMDAwMDAxOTMgMDAwMDAgbiAKCnRyYWlsZXIKPDwvU2l6ZSA1L1Jvb3QgMSAwIFIvSURbPDI1QzNB"
    "MjRFNEVDMjgwQzJBQzY1QzM4NEMzQTJDMjg1PjwxQjAyRUMzMkUxRDMwNUYzNDJBRjZFMjI2MkYzNTZDND5dPj4Kc3RhcnR4"
    "cmVmCjI4NAolJUVPRgo=")


def _fake_render_png(plan, bore_id, sheet, offset, stroke_points, *, status, reason, out_dir):
    import os
    os.makedirs(out_dir, exist_ok=True)
    p = os.path.join(out_dir, "%s_s%d_redline_stroke.png" % (bore_id, sheet))
    with open(p, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + b"r(%s)" % status.encode())
    return p


def _engine_ready_job(c, ctx, monkeypatch, *, placement_status=PlacementStatus.REVIEW, with_callout=True):
    """Build an engine-ready job via the ROUTES, then monkeypatch the engine + renderer so the acceptance
    routes exercise a deterministic REVIEW/ABSTAIN candidate."""
    ppr.create_project(ppr.ProjectCreate(display_name="L"), ctx=ctx, c=c)
    ppr.create_processing_job(ppr.JobCreate(job_id="job-1"), ctx=ctx, c=c)
    ppr.register_upload("job-1", ppr.UploadRegister(
        kind="PLAN_PDF", filename="plan.pdf", content_base64=base64.b64encode(_RA_PDF).decode()), ctx=ctx, c=c)
    bore_up = ppr.register_upload("job-1", ppr.UploadRegister(
        kind="BORE_LOG", filename="log.xlsx", content_base64=base64.b64encode(b"bore").decode()), ctx=ctx, c=c)
    ppr.create_bore_log_review("job-1", ppr.ReviewedBoreLogCreate(
        reviewed_bore_log_id="rbl-1", source_upload_id=bore_up["upload_id"]), ctx=ctx, c=c)
    ppr.add_rows("job-1", "rbl-1", ppr.RowsAdd(rows=[ppr.ExtractedRowInput(
        row_id="row-1", source_upload_id=bore_up["upload_id"], raw={"s": "0+00"},
        normalized={"s": "0+00"}, extraction_method=MANUAL_ENTRY)]), ctx=ctx, c=c)
    ppr.review_row_route("job-1", "rbl-1", "row-1", ppr.RowReview(to_status=CONFIRMED), ctx=ctx, c=c)
    ppr.define_group("job-1", "rbl-1", ppr.SegmentGroupCreate(
        group_id="g-1", member_row_ids=["row-1"], relation=SEPARATE_BORE), ctx=ctx, c=c)
    ppr.set_group_status("job-1", "rbl-1", "g-1", ppr.GroupingStatus(to_status=GROUPING_CONFIRMED),
                         ctx=ctx, c=c)

    bore = Bore(bore_id="log.xlsx", project=None, source_file="log.xlsx", sheet_refs=[11],
                station_start="19+76", station_end="20+47", station_start_ft=1976.0,
                station_end_ft=2047.0, span_ft=71.0)
    callouts = []
    if with_callout:
        callouts = [Callout(sheet=11, page=11, from_sta="19+84", to_sta="20+24", from_ft=1984.0,
                            to_ft=2024.0, footage=40.0, text="DRAWN DIRECTIONAL BORE",
                            bbox=[100.0, 200.0, 300.0, 205.0], dialect="generic")]
    placement = Placement(bore_id="log.xlsx", status=placement_status, tier="t",
                          reason="DRAWN_EXTENT_COVERS_SPAN_NOT_TIGHT", sheets=[11], caveats=[],
                          abstain_reason=("no drawn bore" if placement_status == PlacementStatus.ABSTAIN
                                          else None),
                          matched_callouts=callouts)
    na = {"verdict": "N/A", "caveats": [], "evidence": []}
    monkeypatch.setattr(uce, "_run_engine",
                        lambda p, bl: (bore, placement, 0, "generic", [], na, None, None))
    monkeypatch.setattr(uce, "render_redline_stroke", _fake_render_png)


def test_generate_review_candidate_route_renders_and_records(tmp_path, monkeypatch):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    _engine_ready_job(c, ctx, monkeypatch)
    out = ppr.generate_review_candidate_route("job-1", ctx=ctx, c=c)
    assert out["tier"] == "REVIEW" and out["runnable"] is True
    assert out["record"]["status"] == "REVIEW_CANDIDATE"
    assert out["record"]["provenance"] == "ENGINE_GENERATED_REVIEW_CANDIDATE"
    assert out["record"]["bundle"]["artifact_count"] == 1


def test_review_candidate_list_and_get_routes(tmp_path, monkeypatch):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    _engine_ready_job(c, ctx, monkeypatch)
    ppr.generate_review_candidate_route("job-1", ctx=ctx, c=c)
    listed = ppr.list_review_candidates_route("job-1", ctx=ctx, c=c)
    assert [r["candidate_id"] for r in listed["review_candidates"]] == ["rc-rbl-1"]
    got = ppr.get_review_candidate_route("job-1", "rc-rbl-1", ctx=ctx, c=c)
    assert got["status"] == "REVIEW_CANDIDATE"


def test_get_review_candidate_missing_is_404(tmp_path, monkeypatch):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    _engine_ready_job(c, ctx, monkeypatch)
    with pytest.raises(HTTPException) as exc:
        ppr.get_review_candidate_route("job-1", "rc-nope", ctx=ctx, c=c)
    assert exc.value.status_code == 404


def test_accept_route_confers_human_accepted_review(tmp_path, monkeypatch):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    _engine_ready_job(c, ctx, monkeypatch)
    ppr.generate_review_candidate_route("job-1", ctx=ctx, c=c)
    accepted = ppr.accept_review_candidate_route("job-1", "rc-rbl-1", ctx=ctx, c=c)
    assert accepted["status"] == "REVIEW_ACCEPTED"
    assert accepted["provenance"] == "ENGINE_GENERATED_HUMAN_ACCEPTED_REVIEW"
    assert accepted["provenance"] != "DETERMINISTIC_AUTO"        # never relabeled as AUTO


def test_reject_route_requires_reason_and_is_terminal(tmp_path, monkeypatch):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    _engine_ready_job(c, ctx, monkeypatch)
    ppr.generate_review_candidate_route("job-1", ctx=ctx, c=c)
    with pytest.raises(HTTPException) as exc:                    # empty reason -> 400
        ppr.reject_review_candidate_route("job-1", "rc-rbl-1", ppr.ReviewReject(reason="  "), ctx=ctx, c=c)
    assert exc.value.status_code == 400
    rejected = ppr.reject_review_candidate_route(
        "job-1", "rc-rbl-1", ppr.ReviewReject(reason="needs correction"), ctx=ctx, c=c)
    assert rejected["status"] == "REVIEW_REJECTED"
    with pytest.raises(HTTPException) as exc:                    # rejected cannot be accepted -> 409
        ppr.accept_review_candidate_route("job-1", "rc-rbl-1", ctx=ctx, c=c)
    assert exc.value.status_code == 409


def test_engine_abstain_route_records_abstained(tmp_path, monkeypatch):
    c, ctx = _container(tmp_path), _ctx("cp-aaa")
    _engine_ready_job(c, ctx, monkeypatch, placement_status=PlacementStatus.ABSTAIN, with_callout=False)
    out = ppr.generate_review_candidate_route("job-1", ctx=ctx, c=c)
    assert out["tier"] == "ABSTAIN" and out["record"]["status"] == "ABSTAINED"
    assert "ENGINE_ABSTAINED" in {b["code"] for b in out["record"]["blockers"]}


def test_review_candidate_routes_tenant_isolation(tmp_path, monkeypatch):
    c = _container(tmp_path)
    a, b = _ctx("cp-aaa"), _ctx("cp-bbb")
    _engine_ready_job(c, a, monkeypatch)
    ppr.generate_review_candidate_route("job-1", ctx=a, c=c)
    ppr.create_project(ppr.ProjectCreate(display_name="B"), ctx=b, c=c)
    with pytest.raises(HTTPException) as exc:                    # B cannot read A's candidate
        ppr.get_review_candidate_route("job-1", "rc-rbl-1", ctx=b, c=c)
    assert exc.value.status_code == 404
