"""API tests: the field-evidence WRITE routes (mobile submit-to-review seam).

Follows the repo API-test convention (mirrors test_product_readiness_wiring.py): NO httpx / TestClient.
Mounting is asserted on the real app; route behavior is exercised by calling the route functions directly
with a verified RequestContext + the app container. Locks: DEFAULT-OFF flag + conditional mount,
tenant/path safety, create/update/read, blocked-vs-successful submit, and the no-AUTO doctrine at the API
surface (no job status/slot change; doctrine flags in every response).
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

from truelinev2.api import field_evidence_routes as fer
from truelinev2.api.app import create_app
from truelinev2.config import Settings
from truelinev2.context import require_context
from truelinev2.contracts import field_evidence as fe
from truelinev2.contracts.customer_project import create_customer_project
from truelinev2.contracts.processing_job import create_job, load_job
from truelinev2.contracts.upload_pipeline import accept_upload

_NOW = "2026-01-01T00:00:00+00:00"
_TENANT, _JOB, _SEG = "cp-aaa", "job-1", "seg-001"

FIELD_EVIDENCE_PATHS = {
    "/v2/product/jobs/{job_id}/field-evidence",
    "/v2/product/jobs/{job_id}/field-evidence/{segment_id}",
    "/v2/product/jobs/{job_id}/field-evidence/{segment_id}/submit",
}


def _settings(tmp_path: Path, *, enabled: bool) -> Settings:
    return dataclasses.replace(
        Settings.for_proof(),
        artifact_root=tmp_path / "artifacts",
        cards_dir=tmp_path / "cards",
        db_path=tmp_path / "truelinev2.db",
        field_evidence_api_optin=enabled,
        product_store_root=tmp_path / "product_store",
    )


def _app(tmp_path: Path, *, enabled: bool = True):
    return create_app(_settings(tmp_path, enabled=enabled))


def _ctx(tenant: str = _TENANT, session: str = "field-1"):
    return require_context(tenant, session)


def _fe_routes(app):
    return [r for r in app.routes if isinstance(r, APIRoute) and "field-evidence" in r.path]


def _seed_job(store, *, tenant: str = _TENANT, job_id: str = _JOB):
    create_customer_project(store, tenant, "Label", _NOW)
    create_job(store, tenant, job_id, _NOW, "field-1")


def _photo(store, name: str, *, tenant: str = _TENANT, job_id: str = _JOB) -> str:
    up = accept_upload(store, tenant, job_id, kind="PHOTO", filename=name,
                       content=("bytes-%s" % name).encode(), stored_at=_NOW)
    return up["upload_id"]


def _payload(**over) -> fer.FieldEvidencePayload:
    base = {"start_station": "11+75", "end_station": "13+25"}
    base.update(over)
    return fer.FieldEvidencePayload(**base)


def _complete_payload(store) -> fer.FieldEvidencePayload:
    start, end = _photo(store, "start.jpg"), _photo(store, "end.jpg")
    return _payload(photos=[
        {"evidence_id": "ev-start", "kind": fe.START_STATION, "upload_id": start, "station": "11+75"},
        {"evidence_id": "ev-end", "kind": fe.END_STATION, "upload_id": end, "station": "13+25"},
    ])


# --------------------------------------------------------------------------- #
# Flag + mounting.
# --------------------------------------------------------------------------- #
def test_settings_default_off_and_env(monkeypatch):
    monkeypatch.delenv("TL2_FIELD_EVIDENCE_API_OPTIN", raising=False)
    assert Settings.from_env().field_evidence_api_optin is False
    monkeypatch.setenv("TL2_FIELD_EVIDENCE_API_OPTIN", "1")
    assert Settings.from_env().field_evidence_api_optin is True


def test_routes_not_mounted_by_default(tmp_path):
    assert _fe_routes(_app(tmp_path, enabled=False)) == []


def test_routes_mounted_when_enabled(tmp_path):
    assert {r.path for r in _fe_routes(_app(tmp_path))} == FIELD_EVIDENCE_PATHS


# --------------------------------------------------------------------------- #
# Create / update / read.
# --------------------------------------------------------------------------- #
def test_put_get_list_roundtrip(tmp_path):
    app = _app(tmp_path)
    c = app.state.tl2
    _seed_job(c.settings.product_store_root)
    ctx = _ctx()
    rec = fer.put_field_evidence_route(_JOB, _SEG, _payload(notes="first save"), ctx=ctx, c=c)
    assert rec["status"] == fe.DRAFT and rec["notes"] == "first save"
    got = fer.get_field_evidence_route(_JOB, _SEG, ctx=ctx, c=c)
    assert got["segment_id"] == _SEG
    listed = fer.list_field_evidence_route(_JOB, ctx=ctx, c=c)
    assert [r["segment_id"] for r in listed["field_evidence"]] == [_SEG]


def test_put_invalid_payload_is_400(tmp_path):
    app = _app(tmp_path)
    c = app.state.tl2
    _seed_job(c.settings.product_store_root)
    bad = _payload(photos=[{"evidence_id": "e1", "kind": "SELFIE"}])
    with pytest.raises(HTTPException) as exc:
        fer.put_field_evidence_route(_JOB, _SEG, bad, ctx=_ctx(), c=c)
    assert exc.value.status_code == 400


def test_missing_job_and_missing_package_are_404(tmp_path):
    app = _app(tmp_path)
    c = app.state.tl2
    with pytest.raises(HTTPException) as exc:
        fer.get_field_evidence_route("job-ghost", _SEG, ctx=_ctx(), c=c)
    assert exc.value.status_code == 404
    _seed_job(c.settings.product_store_root)
    with pytest.raises(HTTPException) as exc:
        fer.get_field_evidence_route(_JOB, "seg-ghost", ctx=_ctx(), c=c)
    assert exc.value.status_code == 404


def test_cross_tenant_is_404(tmp_path):
    app = _app(tmp_path)
    c = app.state.tl2
    store = c.settings.product_store_root
    _seed_job(store)                                              # job belongs to cp-aaa
    create_customer_project(store, "cp-bbb", "Other", _NOW)
    with pytest.raises(HTTPException) as exc:
        fer.put_field_evidence_route(_JOB, _SEG, _payload(), ctx=_ctx("cp-bbb"), c=c)
    assert exc.value.status_code == 404                           # never confirms the other tenant's job


def test_invalid_segment_id_is_400(tmp_path):
    app = _app(tmp_path)
    c = app.state.tl2
    _seed_job(c.settings.product_store_root)
    with pytest.raises(HTTPException) as exc:
        fer.put_field_evidence_route(_JOB, "UPPER/CASE", _payload(), ctx=_ctx(), c=c)
    assert exc.value.status_code == 400


# --------------------------------------------------------------------------- #
# Submit: blocked vs successful; doctrine at the API surface.
# --------------------------------------------------------------------------- #
def test_submit_blocked_when_required_evidence_missing(tmp_path):
    app = _app(tmp_path)
    c = app.state.tl2
    _seed_job(c.settings.product_store_root)
    ctx = _ctx()
    fer.put_field_evidence_route(_JOB, _SEG, _payload(), ctx=ctx, c=c)
    result = fer.submit_field_evidence_route(_JOB, _SEG, ctx=ctx, c=c)
    assert result["submitted"] is False
    assert result["blocked"] == fe.BLOCKED_MISSING_REQUIRED_EVIDENCE
    assert [m["code"] for m in result["missing_evidence"]] == [
        fe.MISSING_START_STATION_PHOTO, fe.MISSING_END_STATION_PHOTO]
    assert fer.get_field_evidence_route(_JOB, _SEG, ctx=ctx, c=c)["status"] == fe.DRAFT


def test_submit_succeeds_with_required_evidence_and_promotes_nothing(tmp_path):
    app = _app(tmp_path)
    c = app.state.tl2
    store = c.settings.product_store_root
    _seed_job(store)
    ctx = _ctx()
    fer.put_field_evidence_route(_JOB, _SEG, _complete_payload(store), ctx=ctx, c=c)

    before = load_job(store, _TENANT, _JOB)
    result = fer.submit_field_evidence_route(_JOB, _SEG, ctx=ctx, c=c)
    after = load_job(store, _TENANT, _JOB)

    assert result["submitted"] is True and result["status"] == fe.SUBMITTED_FOR_REVIEW
    # Doctrine flags travel on every response; the job itself is untouched (no AUTO, no placement,
    # no output slot, no lifecycle transition).
    assert result["creates_redline"] is False and result["performs_auto"] is False
    assert result["performs_placement"] is False and result["review_support_only"] is True
    assert after["status"] == before["status"] and after["slots"] == before["slots"]


def test_no_auto_or_placement_fields_in_stored_record(tmp_path):
    app = _app(tmp_path)
    c = app.state.tl2
    store = c.settings.product_store_root
    _seed_job(store)
    ctx = _ctx()
    fer.put_field_evidence_route(_JOB, _SEG, _complete_payload(store), ctx=ctx, c=c)
    fer.submit_field_evidence_route(_JOB, _SEG, ctx=ctx, c=c)
    rec = fer.get_field_evidence_route(_JOB, _SEG, ctx=ctx, c=c)
    assert rec["status"] == fe.SUBMITTED_FOR_REVIEW
    # No placement vocabulary appears as a stored capability: the flags exist ONLY as always-False guards.
    for key in ("redline_manifest", "placement_status", "auto_status", "tier"):
        assert key not in rec
    assert rec["creates_redline"] is False and rec["review_support_only"] is True
