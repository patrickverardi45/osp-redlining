"""Phase 1 hardening: the fail-closed DESTRUCTIVE product-route gate.

Default is BLOCKED (403 with a stable code); a destructive route runs only when
TL2_ENABLE_DESTRUCTIVE_PRODUCT_ROUTES=1 (settings.enable_destructive_product_routes). NOT auth — the
tenant/isolation checks are unchanged. Follows the repo API-test convention: route handlers are called
DIRECTLY with an explicit RequestContext (no TestClient); generic ids only.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest
from fastapi import HTTPException

from truelinev2.api import product_pipeline_routes as ppr
from truelinev2.api.app import create_app
from truelinev2.api.guards import DESTRUCTIVE_ROUTES_DISABLED, assert_destructive_enabled
from truelinev2.config import Settings
from truelinev2.context import require_context


def _settings(tmp_path: Path, *, destructive: bool) -> Settings:
    return dataclasses.replace(
        Settings.for_proof(),
        artifact_root=tmp_path / "artifacts",
        cards_dir=tmp_path / "cards",
        db_path=tmp_path / "truelinev2.db",
        product_pipeline_api_optin=True,
        product_store_root=tmp_path / "product_store",
        enable_destructive_product_routes=destructive,
    )


def _container(tmp_path: Path, *, destructive: bool):
    return create_app(_settings(tmp_path, destructive=destructive)).state.tl2


def _ctx(tenant: str = "cp-aaa"):
    return require_context(tenant, "sess-1")


# --- config default (fail-closed) ------------------------------------------------------------------ #
def test_destructive_flag_defaults_off(monkeypatch):
    monkeypatch.delenv("TL2_ENABLE_DESTRUCTIVE_PRODUCT_ROUTES", raising=False)
    assert Settings.from_env().enable_destructive_product_routes is False
    monkeypatch.setenv("TL2_ENABLE_DESTRUCTIVE_PRODUCT_ROUTES", "1")
    assert Settings.from_env().enable_destructive_product_routes is True


# --- shared guard unit ----------------------------------------------------------------------------- #
def test_guard_blocks_when_disabled_and_passes_when_enabled():
    blocked = dataclasses.replace(Settings.for_proof(), enable_destructive_product_routes=False)
    with pytest.raises(HTTPException) as exc:
        assert_destructive_enabled(blocked)
    assert exc.value.status_code == 403
    assert DESTRUCTIVE_ROUTES_DISABLED in str(exc.value.detail)
    # enabled -> returns None, raises nothing
    enabled = dataclasses.replace(Settings.for_proof(), enable_destructive_product_routes=True)
    assert assert_destructive_enabled(enabled) is None


# --- representative destructive route: job delete -------------------------------------------------- #
def test_delete_route_blocked_by_default(tmp_path):
    c, ctx = _container(tmp_path, destructive=False), _ctx()
    ppr.create_project(ppr.ProjectCreate(display_name="Label"), ctx=ctx, c=c)
    ppr.create_processing_job(ppr.JobCreate(job_id="job-1"), ctx=ctx, c=c)
    with pytest.raises(HTTPException) as exc:
        ppr.delete_processing_job("job-1", ctx=ctx, c=c)
    assert exc.value.status_code == 403
    assert DESTRUCTIVE_ROUTES_DISABLED in str(exc.value.detail)
    # the job MUST still exist — the gate refused before any store mutation
    assert ppr.get_processing_job("job-1", ctx=ctx, c=c)["job_id"] == "job-1"


def test_delete_route_allowed_when_enabled(tmp_path):
    c, ctx = _container(tmp_path, destructive=True), _ctx()
    ppr.create_project(ppr.ProjectCreate(display_name="Label"), ctx=ctx, c=c)
    ppr.create_processing_job(ppr.JobCreate(job_id="job-1"), ctx=ctx, c=c)
    out = ppr.delete_processing_job("job-1", ctx=ctx, c=c)
    assert out["deleted"] is True and out["job_id"] == "job-1"
    with pytest.raises(HTTPException) as exc:                     # gone afterwards
        ppr.get_processing_job("job-1", ctx=ctx, c=c)
    assert exc.value.status_code == 404
