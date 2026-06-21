"""Offline tests for the default-OFF Slice 1 product-pipeline foundation API.

Follows the repo API-test convention (mirrors test_reviewer_api.py): NO httpx, NO TestClient. Mounting is
checked via app.routes; route functions are called DIRECTLY with an explicit RequestContext (identity is
never taken from the URL path or body). Generic ids/labels only.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

from truelinev2.api import product_pipeline_routes as ppr
from truelinev2.api.app import create_app
from truelinev2.config import Settings
from truelinev2.context import require_context
from truelinev2.contracts.processing_job import CREATED, UPLOADING

PRODUCT_PATHS = {
    "/v2/product/project",
    "/v2/product/jobs",
    "/v2/product/jobs/{job_id}",
    "/v2/product/jobs/{job_id}/transition",
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
    # ...nor from request bodies
    assert set(ppr.ProjectCreate.model_fields) == {"display_name"}
    assert set(ppr.JobCreate.model_fields) == {"job_id"}
    assert set(ppr.JobTransition.model_fields) == {"to_status", "reason"}


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
