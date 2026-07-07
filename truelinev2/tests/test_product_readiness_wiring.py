"""Offline tests for STAGING_REVIEW_CANDIDATE_PRODUCT_WIRING — the source-backed readiness / REVIEW-candidate lane
wired onto the product upload/job store.

Follows the repo API-test convention (mirrors test_product_pipeline_api.py): NO httpx / TestClient. Mounting is
checked via app.routes; route functions are called DIRECTLY with an explicit RequestContext (identity is never
taken from the URL path or body). The job + uploads are seeded through the SAME product contracts the API uses
(create_customer_project / create_job / accept_upload), and the fixtures are the generic name-free synthetic
packages from complete_package_qa — so each scenario's readiness status is COMPUTED by the real spine through the
product path, never hard-coded. Generic ids/labels only.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

from truelinev2.api import product_readiness_routes as prr
from truelinev2.api.app import create_app
from truelinev2.config import Settings
from truelinev2.context import require_context
from truelinev2.contracts.customer_project import create_customer_project
from truelinev2.contracts.processing_job import create_job, job_dir
from truelinev2.contracts.upload_pipeline import accept_upload
from truelinev2.harness.complete_package_qa import SCENARIOS, build_complete_package

_NOW = "2026-01-01T00:00:00+00:00"
_TENANT = "cp-aaa"
_JOB = "job-1"

READINESS_PATHS = {
    "/v2/product/jobs/{job_id}/review-readiness/run",
    "/v2/product/jobs/{job_id}/review-readiness",
    "/v2/product/jobs/{job_id}/review-readiness/artifacts/{artifact_path:path}",
}


# --------------------------------------------------------------------------- #
# Harness.
# --------------------------------------------------------------------------- #
def _settings(tmp_path: Path, *, enabled: bool) -> Settings:
    return dataclasses.replace(
        Settings.for_proof(),
        artifact_root=tmp_path / "artifacts",
        cards_dir=tmp_path / "cards",
        db_path=tmp_path / "truelinev2.db",
        product_readiness_api_optin=enabled,
        product_store_root=tmp_path / "product_store",
    )


def _app(tmp_path: Path, *, enabled: bool = True):
    return create_app(_settings(tmp_path, enabled=enabled))


def _ctx(tenant: str = _TENANT, session: str = "sess-1"):
    return require_context(tenant, session)


def _readiness_routes(app):
    return [r for r in app.routes
            if isinstance(r, APIRoute) and "review-readiness" in r.path]


def _seed_job(store, *, tenant: str = _TENANT, job_id: str = _JOB):
    create_customer_project(store, tenant, "Label", _NOW)
    create_job(store, tenant, job_id, _NOW, "sess-1")


def _upload(store, kind: str, filename: str, content: bytes, *, tenant: str = _TENANT, job_id: str = _JOB):
    return accept_upload(store, tenant, job_id, kind=kind, filename=filename, content=content, stored_at=_NOW)


def _scenario_bytes(tmp_path: Path, scenario):
    """Build the scenario's generic synthetic package and return its (plan_pdf_bytes|None, bore_log_csv_bytes|None)."""
    pkg = build_complete_package(tmp_path / "qa_src", name="src-%s" % scenario.key, labels=scenario.labels,
                                 route_shape=scenario.route_shape, bore_csv=scenario.bore_csv)
    up = Path(pkg) / "uploads"
    plan = (up / "plan.pdf").read_bytes() if (up / "plan.pdf").is_file() else None
    borelog = (up / "bore-log.csv").read_bytes() if (up / "bore-log.csv").is_file() else None
    return plan, borelog


def _seed_scenario(tmp_path: Path, store, scenario):
    _seed_job(store)
    plan, borelog = _scenario_bytes(tmp_path, scenario)
    if plan is not None:
        _upload(store, "PLAN_PDF", "plan.pdf", plan)
    if borelog is not None:
        _upload(store, "BORE_LOG", "bore-log.csv", borelog)


def _run(tmp_path: Path, scenario):
    app = _app(tmp_path)
    c = app.state.tl2
    _seed_scenario(tmp_path, c.settings.product_store_root, scenario)
    ctx = _ctx()
    result = prr.run_review_readiness(_JOB, plan_sheet=1, ctx=ctx, c=c)
    return app, c, ctx, result


# --------------------------------------------------------------------------- #
# Settings + mounting + dev-tool separation (smoke #7 backend side).
# --------------------------------------------------------------------------- #
def test_settings_default_off_and_env(monkeypatch):
    monkeypatch.delenv("TL2_PRODUCT_READINESS_API_OPTIN", raising=False)
    assert Settings.from_env().product_readiness_api_optin is False
    monkeypatch.setenv("TL2_PRODUCT_READINESS_API_OPTIN", "1")
    assert Settings.from_env().product_readiness_api_optin is True


def test_flag_off_routes_are_dormant(tmp_path):
    app = _app(tmp_path, enabled=False)
    assert not any("review-readiness" in r.path for r in app.routes if isinstance(r, APIRoute))


def test_flag_on_mounts_only_readiness_get_post_context_bearing(tmp_path):
    app = _app(tmp_path, enabled=True)
    routes = _readiness_routes(app)
    assert {r.path for r in routes} == READINESS_PATHS
    methods = set().union(*(r.methods for r in routes))
    assert methods <= {"GET", "POST"}                          # CORS allows only GET/POST
    assert all(r.dependant.dependencies for r in routes)       # context-bearing (get_context/get_container)


def test_readiness_lane_does_not_mount_manual_anchor_tools(tmp_path):
    """Dev-only manual source-anchor capture tools belong to the SEPARATE pipeline lane; enabling ONLY the readiness
    lane must not expose any /source-anchors or plan-page raster capture route in the normal staging flow."""
    app = _app(tmp_path, enabled=True)                          # pipeline lane OFF; readiness lane ON
    paths = {r.path for r in app.routes if isinstance(r, APIRoute)}
    assert not any("source-anchor" in p or "plan-pages" in p for p in paths)


def test_no_customer_identity_in_readiness_paths(tmp_path):
    app = _app(tmp_path, enabled=True)
    for r in _readiness_routes(app):
        assert "customer_project" not in r.path and "tenant" not in r.path


# --------------------------------------------------------------------------- #
# Core: every generic scenario computes its status THROUGH the product path; artifacts ONLY when READY (smokes 1-5).
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s.key for s in SCENARIOS])
def test_scenario_status_and_artifact_gate(tmp_path, scenario):
    app, c, ctx, result = _run(tmp_path, scenario)

    # status is COMPUTED by the real spine through the product path (never hard-coded / mocked).
    assert result["readiness_status"] == scenario.expected_status
    assert result["ready"] == scenario.expected_ready
    # never AUTO / placement / promotion; this is a REVIEW candidate lane only.
    assert result["is_review_candidate"] is True
    assert result["performs_auto"] is False
    assert result["performs_placement"] is False
    assert result["promotes_status"] is False
    assert result["draws_anything"] is False

    rdir = job_dir(c.settings.product_store_root, _TENANT, _JOB) / prr.REVIEW_READINESS_SUBDIR
    pngs = sorted(rdir.glob("*.png"))

    if scenario.expected_ready:
        # READY -> exactly one candidate + before/after overlay PNGs served + drawn.
        assert result["review_candidate_status"] == "REVIEW_CANDIDATE_READY"
        assert result["generated_visual"] is True
        assert result["candidate"] is not None
        assert result["refusal_reason"] is None
        arts = result["artifacts"]
        assert {a["role"] for a in arts} == {"before", "after"}
        assert len(pngs) == 2
        for a in arts:
            assert a["url"].startswith("/v2/product/jobs/%s/review-readiness/artifacts/" % _JOB)
            served = prr.get_review_readiness_artifact(_JOB, a["filename"], ctx=ctx, c=c)
            data = Path(served.path).read_bytes()
            assert data[:8] == b"\x89PNG\r\n\x1a\n"             # a real PNG
        before = next(p for p in pngs if "before" in p.name).read_bytes()
        after = next(p for p in pngs if "after" in p.name).read_bytes()
        assert before != after                                 # the RED REVIEW stroke actually changed the raster
    else:
        # every refusal draws ZERO artifacts.
        assert result["review_candidate_status"] == "REVIEW_CANDIDATE_REFUSED"
        assert result["generated_visual"] is False
        assert result["candidate"] is None
        assert result["artifacts"] == []
        assert result["refusal_reason"]
        assert pngs == []


# --------------------------------------------------------------------------- #
# Smoke #6 — no silent mock fallback: statuses are input-sensitive + reflect the real uploads.
# --------------------------------------------------------------------------- #
def test_input_sensitivity_three_inputs_three_statuses(tmp_path):
    by_key = {s.key: s for s in SCENARIOS}
    seen = set()
    for key in ("complete_ready", "plan_only", "span_anchors_route_blocked"):
        # a fresh app/store per input so each is an independent product run.
        _, _, _, result = _run(tmp_path / key, by_key[key])
        seen.add(result["readiness_status"])
    assert seen == {"READY_FOR_REVIEW_REDLINE", "MISSING_BORE_SPAN_SOURCE", "ROUTE_BLOCKED"}


def test_ready_result_echoes_the_uploaded_span_not_a_fixture(tmp_path):
    by_key = {s.key: s for s in SCENARIOS}
    _, _, _, result = _run(tmp_path, by_key["complete_ready"])
    spans = result["span_rows"]
    assert len(spans) == 1
    # the synthetic complete package ties stations 11+75 -> 13+25 (runtime data, echoed back, not a mock number).
    assert spans[0]["start_station"] == "11+75" and spans[0]["end_station"] == "13+25"
    assert spans[0]["source_file"] == "bore-log.csv"           # basename echoed, never an absolute/temp path


def test_no_uploads_is_honest_refusal_not_mock(tmp_path):
    app = _app(tmp_path)
    c = app.state.tl2
    _seed_job(c.settings.product_store_root)                    # job exists, but zero uploads
    result = prr.run_review_readiness(_JOB, plan_sheet=1, ctx=_ctx(), c=c)
    assert result["readiness_status"] == "NO_SPINE_INPUT"
    assert result["candidate"] is None and result["artifacts"] == []


def test_missing_job_is_404(tmp_path):
    app = _app(tmp_path)
    with pytest.raises(HTTPException) as exc:
        prr.run_review_readiness("nope", plan_sheet=1, ctx=_ctx(), c=app.state.tl2)
    assert exc.value.status_code == 404


def test_cross_tenant_job_is_404(tmp_path):
    app = _app(tmp_path)
    c = app.state.tl2
    _seed_job(c.settings.product_store_root, tenant=_TENANT)
    with pytest.raises(HTTPException) as exc:                   # a different tenant cannot resolve this job
        prr.run_review_readiness(_JOB, plan_sheet=1, ctx=_ctx(tenant="cp-bbb"), c=c)
    assert exc.value.status_code == 404


def test_invalid_tenant_slug_is_400_not_500(tmp_path):
    """An invalid customer_project slug raises a CustomerProjectError from load_job; it must fail closed as 400
    (mirroring product_pipeline_routes), never bubble up as an unhandled 500."""
    app = _app(tmp_path)
    with pytest.raises(HTTPException) as exc:
        prr.run_review_readiness(_JOB, plan_sheet=1, ctx=_ctx(tenant="Upper"), c=app.state.tl2)
    assert exc.value.status_code == 400


def test_render_failure_is_graceful_not_500(tmp_path, monkeypatch):
    """A READY package whose overlay render throws must return an HONEST refusal (readiness stays READY, no
    artifact, render_error flagged) — never an unhandled 500, and never a stray partial PNG."""
    import truelinev2.harness.review_candidate as rc

    by_key = {s.key: s for s in SCENARIOS}
    app = _app(tmp_path)
    c = app.state.tl2
    _seed_scenario(tmp_path, c.settings.product_store_root, by_key["complete_ready"])

    def _boom(*a, **k):
        raise RuntimeError("simulated overlay render failure")

    monkeypatch.setattr(rc, "build_review_candidate", _boom)   # bridge lazy-imports this at call time
    result = prr.run_review_readiness(_JOB, plan_sheet=1, ctx=_ctx(), c=c)

    assert result["readiness_status"] == "READY_FOR_REVIEW_REDLINE"    # readiness is honestly still READY
    assert result["review_candidate_status"] == "REVIEW_CANDIDATE_REFUSED"
    assert result["generated_visual"] is False
    assert result["candidate"] is None and result["artifacts"] == []
    assert result["detail"].get("render_error") is True
    assert result["performs_auto"] is False and result["is_review_candidate"] is True
    rdir = job_dir(c.settings.product_store_root, _TENANT, _JOB) / prr.REVIEW_READINESS_SUBDIR
    assert sorted(rdir.glob("*.png")) == []                    # no stray partial artifact left behind


# --------------------------------------------------------------------------- #
# Persistence (GET) + serve safety + no path leak.
# --------------------------------------------------------------------------- #
def test_get_before_run_is_404_then_matches_after_run(tmp_path):
    by_key = {s.key: s for s in SCENARIOS}
    app = _app(tmp_path)
    c = app.state.tl2
    _seed_scenario(tmp_path, c.settings.product_store_root, by_key["complete_ready"])
    ctx = _ctx()
    with pytest.raises(HTTPException) as exc:
        prr.get_review_readiness(_JOB, ctx=ctx, c=c)
    assert exc.value.status_code == 404
    ran = prr.run_review_readiness(_JOB, plan_sheet=1, ctx=ctx, c=c)
    got = prr.get_review_readiness(_JOB, ctx=ctx, c=c)
    assert got == ran                                          # the persisted result matches the run result


def test_artifact_path_traversal_is_refused(tmp_path):
    by_key = {s.key: s for s in SCENARIOS}
    _, c, ctx, _ = _run(tmp_path, by_key["complete_ready"])
    for bad in ("../../result.json", "..\\..\\secret", "nope.png", "sub/evil.png"):
        with pytest.raises(HTTPException) as exc:
            prr.get_review_readiness_artifact(_JOB, bad, ctx=ctx, c=c)
        assert exc.value.status_code == 404


def test_refusal_artifact_fetch_is_404(tmp_path):
    by_key = {s.key: s for s in SCENARIOS}
    _, c, ctx, result = _run(tmp_path, by_key["plan_only"])
    assert result["artifacts"] == []
    with pytest.raises(HTTPException) as exc:
        prr.get_review_readiness_artifact(_JOB, "review_candidate_span-001_after.png", ctx=ctx, c=c)
    assert exc.value.status_code == 404


def test_result_leaks_no_filesystem_or_temp_path(tmp_path):
    by_key = {s.key: s for s in SCENARIOS}
    _, c, _, result = _run(tmp_path, by_key["complete_ready"])
    blob = json.dumps(result)
    assert "tl2_readiness_" not in blob                        # the ephemeral view path never leaks
    cand = result["candidate"]
    assert "/" not in cand["source_file"] and "\\" not in cand["source_file"]
    for row in result["span_rows"]:
        sf = row["source_file"] or ""
        assert "/" not in sf and "\\" not in sf


# --------------------------------------------------------------------------- #
# Slice 3 — route-level sheet selection: omitted plan_sheet derives (default preserved for ref-less
# packages), explicit stays validated. The full derivation behavior matrix is covered at the bridge
# level in test_readiness_sheet_resolution.py.
# --------------------------------------------------------------------------- #
def test_run_without_plan_sheet_derives_and_preserves_default(tmp_path):
    # The QA scenario's bore CSV has NO print/sheet column, so the derived run must land on the prior
    # sheet-1 default (source says so) and reach the SAME READY outcome the explicit runs assert.
    app = _app(tmp_path)
    c = app.state.tl2
    by_key = {s.key: s for s in SCENARIOS}
    _seed_scenario(tmp_path, c.settings.product_store_root, by_key["complete_ready"])
    result = prr.run_review_readiness(_JOB, ctx=_ctx(), c=c)   # plan_sheet OMITTED -> derive
    ctx_out = result["sheet_context"]
    assert ctx_out["source"] == "DEFAULT_PLAN_SHEET"
    assert ctx_out["engineering_sheet"] == 1 and ctx_out["pdf_page"] == 1
    assert result["readiness_status"] == "READY_FOR_REVIEW_REDLINE"
    # the persisted result carries the same context (the GET endpoint serves this file verbatim)
    persisted = json.loads((prr._readiness_dir(c.settings.product_store_root, _TENANT, _JOB)
                            / prr.RESULT_FILENAME).read_text(encoding="utf-8"))
    assert persisted["sheet_context"]["source"] == "DEFAULT_PLAN_SHEET"


def test_run_rejects_non_positive_plan_sheet(tmp_path):
    app = _app(tmp_path)
    c = app.state.tl2
    _seed_job(c.settings.product_store_root)
    with pytest.raises(HTTPException) as exc:
        prr.run_review_readiness(_JOB, plan_sheet=0, ctx=_ctx(), c=c)
    assert exc.value.status_code == 400
