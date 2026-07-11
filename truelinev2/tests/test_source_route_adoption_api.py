"""End-to-end API proof for Phase-2 SOURCE-ROUTE ADOPTION: the proposal endpoint + adoption-at-create.

Follows the repo API-test convention (mirrors test_product_pipeline_api.py / test_product_readiness_wiring.py):
NO httpx / TestClient (neither is a project dependency). Route functions are called DIRECTLY with an explicit
RequestContext for the great majority of this suite. Fixtures are the generic name-free ``complete_package_qa``
synthetic package (product QA, not cold validation) — the SAME fixture-free harness
``test_review_candidate.py`` / ``test_product_readiness_wiring.py`` already use, so this suite needs no owner
fixtures and is safe for CI. Real geometry (anchor xy, backbone segments) is read directly off the readiness
spine run over the SAME bytes being uploaded, never hand-invented.

Fix-wave-2 G3 exception: a SMALL number of tests below prove the amended endpoint-ordering ruling (resource
resolution before adoption validation; a missing/mistyped ``route_adoption`` echo field is FastAPI's own
framework-standard 422) at the REAL ASGI request boundary — something a direct Python function call cannot
observe (constructing a Pydantic model in Python raises ``ValidationError`` before any HTTP status exists).
Since httpx/TestClient are NOT installed and adding a new dependency is out of scope, ``_asgi_call`` below is a
minimal, stdlib-only (``asyncio``) raw-ASGI request driver — it calls the REAL mounted FastAPI/Starlette app
end-to-end (routing, header-based context dependency injection, Pydantic request-body validation) without any
new dependency.
"""
from __future__ import annotations

import asyncio
import base64
import dataclasses
import json
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

from truelinev2.api import product_pipeline_routes as ppr
from truelinev2.api import source_route_proposal_routes as srp
from truelinev2.api.app import create_app
from truelinev2.config import Settings
from truelinev2.context import require_context
from truelinev2.contracts.extracted_row import CONFIRMED, MANUAL_ENTRY
from truelinev2.contracts.reviewed_bore_log import GROUPING_CONFIRMED, SEPARATE_BORE
from truelinev2.harness.complete_package_qa import SCENARIOS, build_complete_package
from truelinev2.harness.route_verification import run_package_route_readiness

_NOW_TENANT = "cp-aaa"
_JOB = "job-1"


# --------------------------------------------------------------------------- #
# Harness.
# --------------------------------------------------------------------------- #
def _settings(tmp_path: Path, *, pipeline=True, readiness=True, adoption=True) -> Settings:
    return dataclasses.replace(
        Settings.for_proof(),
        artifact_root=tmp_path / "artifacts", cards_dir=tmp_path / "cards", db_path=tmp_path / "truelinev2.db",
        product_pipeline_api_optin=pipeline, product_readiness_api_optin=readiness,
        source_route_adoption_api_optin=adoption,
        product_store_root=tmp_path / "product_store",
        product_billing_cost_rules_path=tmp_path / "cost_rules.json")


def _container(tmp_path: Path, **flags):
    return create_app(_settings(tmp_path, **flags)).state.tl2


def _app(tmp_path: Path, **flags):
    """Like ``_container`` but returns the FULL app (so ``app.state.tl2`` is the SAME container a direct-call
    seed can share with a real ASGI dispatch of the same store — Fix-wave-2 G3/G5)."""
    return create_app(_settings(tmp_path, **flags))


def _ctx(tenant: str = _NOW_TENANT, session: str = "sess-1"):
    return require_context(tenant, session)


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def _asgi_call(app, method: str, path: str, *, json_body=None, headers=None):
    """Fix-wave-2 G3/G5: a minimal raw-ASGI request dispatcher (stdlib ``asyncio`` only — NO httpx/TestClient/
    new dependency) that drives the REAL FastAPI/Starlette ASGI app end-to-end: routing, header-based context
    dependency injection, and Pydantic REQUEST-BODY validation, so a missing/mistyped field genuinely produces
    the framework's real HTTP status (a direct Python route-function call only raises ``ValidationError`` with
    no HTTP status attached at all). Returns ``(status_code, raw_body_bytes, parsed_json_or_None)``."""
    body = b"" if json_body is None else json.dumps(json_body).encode("utf-8")
    hdr_list = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode("ascii"))]
    for k, v in (headers or {}).items():
        hdr_list.append((k.lower().encode("latin-1"), str(v).encode("latin-1")))   # ASGI headers are lowercase
    scope = {
        "type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"}, "http_version": "1.1",
        "method": method, "path": path, "raw_path": path.encode("latin-1"), "query_string": b"",
        "headers": hdr_list, "client": ("test", 12345), "server": ("test", 80), "scheme": "http",
        "root_path": "",
    }
    state = {"status": None, "body": b""}
    consumed = {"done": False}

    async def receive():
        if consumed["done"]:
            return {"type": "http.disconnect"}
        consumed["done"] = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        if message["type"] == "http.response.start":
            state["status"] = message["status"]
        elif message["type"] == "http.response.body":
            state["body"] += message.get("body", b"")

    asyncio.run(app(scope, receive, send))
    parsed = None
    if state["body"]:
        try:
            parsed = json.loads(state["body"])
        except ValueError:
            parsed = None
    return state["status"], state["body"], parsed


def _assert_detail_code(exc, code: str) -> None:
    """Fix-wave-2 G3: exact split-token equality (never ``startswith``) — proves ``code`` is precisely the
    LEADING token of the detail string (``detail.split(":", 1)[0] == code``), not merely a prefix that a
    longer/different code could also satisfy (e.g. a hypothetical ``ROUTE_ADOPTION_INVALID_EXTRA`` code would
    pass a ``startswith("ROUTE_ADOPTION_INVALID")`` check but must NOT pass this one)."""
    detail = exc.value.detail
    assert detail.split(":", 1)[0] == code, detail


def _scenario_bytes(tmp_path: Path, key: str = "complete_ready"):
    sc = next(s for s in SCENARIOS if s.key == key)
    pkg = build_complete_package(tmp_path / "qa_src", name="src-%s" % key, labels=sc.labels,
                                 route_shape=sc.route_shape, bore_csv=sc.bore_csv)
    up = Path(pkg) / "uploads"
    plan = (up / "plan.pdf").read_bytes() if (up / "plan.pdf").is_file() else None
    borelog = (up / "bore-log.csv").read_bytes() if (up / "bore-log.csv").is_file() else None
    return pkg, plan, borelog


def _real_geometry(pkg_dir):
    """Run the SAME readiness spine directly over the QA package to read REAL anchor xy / backbone / reach_tol
    (never hand-invented) so the test's control_points are genuinely source-backed. Uses the FIRST segment's
    ``a`` and the LAST segment's ``b`` (not ``route_geometry[0]["b"]``) so this generalizes correctly to a
    multi-segment backbone (Fix-wave-2 G9: the "bent_ready" scenario) — for a single-segment backbone
    (``complete_ready``) this is unchanged (segment 0's own ``a``/``b``)."""
    readiness = run_package_route_readiness(pkg_dir)
    v = next(v for v in readiness.routes.verifications if v.route_ready)
    reach_tol = v.detail["isolation"]["detail"]["reach_tol"]
    return tuple(v.route_geometry[0]["a"]), tuple(v.route_geometry[-1]["b"]), reach_tol


def _seed_ready_job(tmp_path: Path, c, ctx, *, key: str = "complete_ready", job_id: str = _JOB):
    """Project + job + the QA scenario's plan+borelog uploads + an engine-eligible reviewed_bore_log row
    matching the scenario's own span. Returns (plan_upload_id, rbl_id, row_id, pkg_dir)."""
    pkg_dir, plan_bytes, borelog_bytes = _scenario_bytes(tmp_path, key)
    ppr.create_project(ppr.ProjectCreate(display_name="Label"), ctx=ctx, c=c)
    ppr.create_processing_job(ppr.JobCreate(job_id=job_id), ctx=ctx, c=c)
    plan_upload_id = ppr.register_upload(
        job_id, ppr.UploadRegister(kind="PLAN_PDF", filename="plan.pdf", content_base64=_b64(plan_bytes)),
        ctx=ctx, c=c)["upload_id"]
    bore_upload_id = ppr.register_upload(
        job_id, ppr.UploadRegister(kind="BORE_LOG", filename="bore-log.csv",
                                   content_base64=_b64(borelog_bytes)), ctx=ctx, c=c)["upload_id"]
    rbl_id = "rbl-main"
    ppr.create_bore_log_review(
        job_id, ppr.ReviewedBoreLogCreate(reviewed_bore_log_id=rbl_id, source_upload_id=bore_upload_id),
        ctx=ctx, c=c)
    row_id = "row-1"
    ppr.add_rows(job_id, rbl_id, ppr.RowsAdd(rows=[ppr.ExtractedRowInput(
        row_id=row_id, source_upload_id=bore_upload_id,
        raw={"start_station": "11+75", "end_station": "13+25", "footage": "150"},
        normalized={"start_station": "11+75", "end_station": "13+25", "footage": "150"},
        extraction_method=MANUAL_ENTRY)]), ctx=ctx, c=c)
    ppr.review_row_route(job_id, rbl_id, row_id, ppr.RowReview(to_status=CONFIRMED), ctx=ctx, c=c)
    ppr.define_group(job_id, rbl_id, ppr.SegmentGroupCreate(
        group_id="grp-1", member_row_ids=[row_id], relation=SEPARATE_BORE), ctx=ctx, c=c)
    ppr.set_group_status(job_id, rbl_id, "grp-1", ppr.GroupingStatus(to_status=GROUPING_CONFIRMED), ctx=ctx, c=c)
    return plan_upload_id, rbl_id, row_id, pkg_dir


def _cp(x, y):
    return srp.ControlPointIn(x=x, y=y)


# Fix-wave-2 G9 (Item-10 ruling): the old ``_patch_bent_geometry`` test-local helper (which split the real
# single-segment ``complete_ready`` backbone into two SYNTHETIC collinear segments at its own midpoint) is
# DELETED. It manufactured exactly the segment boundary needed to flip the real fixture's same-segment refusal
# into a success, so it could not prove adoption against the unmodified readiness spine, that the real fixture
# supplies adoptable geometry, bend preservation, or a genuinely end-to-end reader/closeout/export path. Every
# success-path test below now seeds the REAL "bent_ready" QA scenario (``harness.complete_package_qa`` G8) —
# a genuinely non-collinear, real, UNPATCHED 3-segment / 2-bend observer backbone reaching
# READY_FOR_REVIEW_REDLINE through the unmodified spine — instead of patching geometry after the fact. The
# unpatched single-segment refusal tests above (``complete_ready``) are untouched.


# --------------------------------------------------------------------------- #
# Settings + mounting.
# --------------------------------------------------------------------------- #
def test_settings_default_off_and_env(monkeypatch):
    monkeypatch.delenv("TL2_SOURCE_ROUTE_ADOPTION_API_OPTIN", raising=False)
    assert Settings.from_env().source_route_adoption_api_optin is False
    monkeypatch.setenv("TL2_SOURCE_ROUTE_ADOPTION_API_OPTIN", "1")
    assert Settings.from_env().source_route_adoption_api_optin is True


def test_flag_off_route_is_dormant(tmp_path):
    app = create_app(_settings(tmp_path, adoption=False))
    assert not any("source-route-proposals" in r.path for r in app.routes if isinstance(r, APIRoute))


def test_flag_off_when_readiness_off_route_is_dormant(tmp_path):
    app = create_app(_settings(tmp_path, readiness=False, adoption=True))
    assert not any("source-route-proposals" in r.path for r in app.routes if isinstance(r, APIRoute))


def test_flag_on_mounts_exactly_the_proposal_route(tmp_path):
    app = create_app(_settings(tmp_path))
    routes = [r for r in app.routes if isinstance(r, APIRoute) and "source-route-proposals" in r.path]
    assert {r.path for r in routes} == {"/v2/product/jobs/{job_id}/source-route-proposals"}
    assert set().union(*(r.methods for r in routes)) == {"POST"}
    assert all(r.dependant.dependencies for r in routes)        # context-bearing


def test_flag_off_never_imports_the_adoption_module(tmp_path):
    """Fix-wave F6 (blind-verification FAIL — flag/import isolation): with pipeline+readiness ON but adoption
    OFF, ``truelinev2.contracts.source_route_adoption`` must NEVER be imported — not even its exception
    classes. Run in a FRESH subprocess (not in-process): every OTHER test module in this suite imports that
    module at module scope for its own testing convenience, which would already be sitting in ``sys.modules``
    by pytest COLLECTION time (before any test body runs) if checked in-process — a false pass. A clean
    interpreter is the only way to observe the real OFF-path import behavior."""
    import subprocess
    import sys as _sys

    repo_root = Path(__file__).resolve().parents[2]
    script = (
        "import sys\n"
        "from truelinev2.api.app import create_app\n"
        "from truelinev2.config import Settings\n"
        "import dataclasses, tempfile\n"
        "from pathlib import Path\n"
        "tmp = Path(tempfile.mkdtemp())\n"
        "settings = dataclasses.replace(Settings.for_proof(), artifact_root=tmp/'a', cards_dir=tmp/'c', "
        "db_path=tmp/'d.db', product_pipeline_api_optin=True, product_readiness_api_optin=True, "
        "source_route_adoption_api_optin=False, product_store_root=tmp/'store', "
        "product_billing_cost_rules_path=tmp/'cr.json')\n"
        "create_app(settings)\n"
        "assert 'truelinev2.contracts.source_route_adoption' not in sys.modules, "
        "sorted(m for m in sys.modules if 'source_route_adoption' in m)\n"
        "print('OK')\n"
    )
    result = subprocess.run([_sys.executable, "-c", script], cwd=str(repo_root),
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK" in result.stdout


# --------------------------------------------------------------------------- #
# Flag OFF / no route_adoption -> the EXISTING v1 create path is byte-identical.
# --------------------------------------------------------------------------- #
def test_manual_create_unchanged_with_new_flag_on(tmp_path):
    """Flag ON, but no route_adoption in the request -> identical v1 record/behavior as before this ticket."""
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id, _ = _seed_ready_job(tmp_path, c, ctx)
    rec = ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
        source_anchor_id="sa-1", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
        page_number=1, control_points=[_cp2(70.0, 90.0), _cp2(170.0, 110.0)],
        row_ids=[row_id]), ctx=ctx, c=c)
    assert rec["record_format"] == "trueline-source-anchor-1"
    assert "geometry_basis" not in rec and "route_adoption" not in rec
    assert rec["provenance"] == "HUMAN_CONFIRMED_CONTROL_POINTS"


def test_manual_create_unchanged_with_new_flag_off(tmp_path):
    c, ctx = _container(tmp_path, adoption=False), _ctx()
    plan_upload_id, rbl_id, row_id, _ = _seed_ready_job(tmp_path, c, ctx)
    rec = ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
        source_anchor_id="sa-1", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
        page_number=1, control_points=[_cp2(70.0, 90.0), _cp2(170.0, 110.0)],
        row_ids=[row_id]), ctx=ctx, c=c)
    assert rec["record_format"] == "trueline-source-anchor-1"


def _cp2(x, y):
    return ppr.ControlPoint(x=x, y=y)


def test_route_adoption_with_flag_off_is_400(tmp_path):
    c, ctx = _container(tmp_path, adoption=False), _ctx()
    plan_upload_id, rbl_id, row_id, _ = _seed_ready_job(tmp_path, c, ctx)
    with pytest.raises(HTTPException) as exc:
        ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
            source_anchor_id="sa-1", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
            page_number=1, control_points=[_cp2(0.0, 0.0), _cp2(1.0, 1.0)], row_ids=[row_id],
            route_adoption=ppr.RouteAdoptionIn(
                proposal_hash="sha256:" + "a" * 64, confirmed=True,
                plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id, row_id=row_id, page_number=1,
                control_points=[_cp2(0.0, 0.0), _cp2(1.0, 1.0)])),
            ctx=ctx, c=c)
    assert exc.value.status_code == 400
    _assert_detail_code(exc, "ROUTE_ADOPTION_INVALID")


# --------------------------------------------------------------------------- #
# Proposal endpoint — happy path (REAL source-backed geometry from the REAL, UNPATCHED "bent_ready" QA spine —
# Fix-wave-2 G9/Item-10 ruling: a genuinely non-collinear 3-segment / 2-bend observer backbone, never a
# test-local synthetic geometry patch. F4 makes a genuinely single-segment real backbone ["complete_ready"]
# always refuse, so the happy-path tests need a real multi-segment backbone to prove a SUCCESSFUL round trip).
# --------------------------------------------------------------------------- #
def test_proposal_ready_returns_source_backed_geometry(tmp_path):
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id, pkg_dir = _seed_ready_job(tmp_path, c, ctx, key="bent_ready")
    a, b, reach_tol = _real_geometry(pkg_dir)

    result = srp.create_source_route_proposal(_JOB, srp.SourceRouteProposalRequest(
        plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id, row_id=row_id, page_number=1,
        control_points=[_cp(*a), _cp(*b)]), ctx=ctx, c=c)

    assert result["outcome"] == "PROPOSAL", result
    p = result["proposal"]
    assert p["proposal_hash"].startswith("sha256:")
    assert p["geometry_basis"] == "OBSERVER_BACKBONE_HUMAN_ADOPTED"
    assert p["coordinate_space"] == "pdf_display_space"
    assert p["human_control_points"] == [{"x": a[0], "y": a[1]}, {"x": b[0], "y": b[1]}]
    assert p["proposed_render_points"][0] == {"x": a[0], "y": a[1]}
    assert p["proposed_render_points"][-1] == {"x": b[0], "y": b[1]}
    assert len(p["proposed_render_points"]) == 4                 # start + 2 REAL bend vertices + end (3 segments)
    assert p["source"]["span_id"]
    assert p["readiness"]["readiness_status"] == "READY_FOR_REVIEW_REDLINE"
    assert p["warnings"] == []                                       # exact anchor clicks -> no connector


def test_proposal_hash_stable_across_two_calls(tmp_path):
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id, pkg_dir = _seed_ready_job(tmp_path, c, ctx, key="bent_ready")
    a, b, _ = _real_geometry(pkg_dir)
    req = srp.SourceRouteProposalRequest(
        plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id, row_id=row_id, page_number=1,
        control_points=[_cp(*a), _cp(*b)])
    r1 = srp.create_source_route_proposal(_JOB, req, ctx=ctx, c=c)
    r2 = srp.create_source_route_proposal(_JOB, req, ctx=ctx, c=c)
    assert r1["outcome"] == r2["outcome"] == "PROPOSAL"
    assert r1["proposal"]["proposal_hash"] == r2["proposal"]["proposal_hash"]


def test_proposal_writes_no_artifact_and_no_store_record(tmp_path):
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id, pkg_dir = _seed_ready_job(tmp_path, c, ctx, key="bent_ready")
    a, b, _ = _real_geometry(pkg_dir)
    result = srp.create_source_route_proposal(_JOB, srp.SourceRouteProposalRequest(
        plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id, row_id=row_id, page_number=1,
        control_points=[_cp(*a), _cp(*b)]), ctx=ctx, c=c)
    assert result["outcome"] == "PROPOSAL"
    store = c.settings.product_store_root / _NOW_TENANT / "jobs" / _JOB
    # no review_readiness dir, no source_anchors dir created by the proposal call
    assert not (store / "review_readiness").exists()
    assert not (store / "source_anchors").exists()


def test_real_single_segment_backbone_refuses_same_segment(tmp_path):
    """Fix-wave F4, exercised end-to-end against the REAL (unpatched) QA spine: ``complete_ready``'s observer
    backbone is genuinely one segment (``ROUTE_CLEAN``), so the two overall endpoints as human clicks now
    refuse ``CONTROLS_ON_SAME_BACKBONE_SEGMENT`` — a real-world "straight run" no longer offers a source-backed
    proposal over the honest manual straight line. Locks the intended real-path consequence of F4, not just
    the pure-geometry unit test."""
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id, pkg_dir = _seed_ready_job(tmp_path, c, ctx)
    a, b, _ = _real_geometry(pkg_dir)
    result = srp.create_source_route_proposal(_JOB, srp.SourceRouteProposalRequest(
        plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id, row_id=row_id, page_number=1,
        control_points=[_cp(*a), _cp(*b)]), ctx=ctx, c=c)
    assert result["outcome"] == "REFUSAL"
    assert result["refusal"]["code"] == "CONTROLS_ON_SAME_BACKBONE_SEGMENT"


def test_real_single_segment_backbone_with_mid_segment_controls_refuses_same_segment(tmp_path):
    """Fix-wave-2 G2 (F4 FAIL — the real-fixture end-to-end lock must use MID-SEGMENT controls, not the
    segment's own endpoints): two points strictly INTERIOR to the single real backbone segment (30%/70% along
    it, nowhere near either overall terminus) still refuse ``CONTROLS_ON_SAME_BACKBONE_SEGMENT`` end-to-end
    against the REAL (unpatched) QA spine. Proves the refusal fires organically from real segment-index
    equality over the observer-exposed backbone — not merely because the test happened to click the segment's
    own two endpoints (a coincidence the test above's clicks, while real, could not rule out on their own)."""
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id, pkg_dir = _seed_ready_job(tmp_path, c, ctx)
    a, b, _ = _real_geometry(pkg_dir)
    mid1 = (a[0] + (b[0] - a[0]) * 0.3, a[1] + (b[1] - a[1]) * 0.3)
    mid2 = (a[0] + (b[0] - a[0]) * 0.7, a[1] + (b[1] - a[1]) * 0.7)
    result = srp.create_source_route_proposal(_JOB, srp.SourceRouteProposalRequest(
        plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id, row_id=row_id, page_number=1,
        control_points=[_cp(*mid1), _cp(*mid2)]), ctx=ctx, c=c)
    assert result["outcome"] == "REFUSAL"
    assert result["refusal"]["code"] == "CONTROLS_ON_SAME_BACKBONE_SEGMENT"


# --------------------------------------------------------------------------- #
# Proposal endpoint — refusals.
# --------------------------------------------------------------------------- #
def test_proposal_row_not_eligible_refuses(tmp_path):
    c, ctx = _container(tmp_path), _ctx()
    pkg_dir, plan_bytes, borelog_bytes = _scenario_bytes(tmp_path)
    ppr.create_project(ppr.ProjectCreate(display_name="Label"), ctx=ctx, c=c)
    ppr.create_processing_job(ppr.JobCreate(job_id=_JOB), ctx=ctx, c=c)
    plan_upload_id = ppr.register_upload(_JOB, ppr.UploadRegister(
        kind="PLAN_PDF", filename="plan.pdf", content_base64=_b64(plan_bytes)), ctx=ctx, c=c)["upload_id"]
    bore_upload_id = ppr.register_upload(_JOB, ppr.UploadRegister(
        kind="BORE_LOG", filename="bore-log.csv", content_base64=_b64(borelog_bytes)), ctx=ctx, c=c)["upload_id"]
    ppr.create_bore_log_review(_JOB, ppr.ReviewedBoreLogCreate(
        reviewed_bore_log_id="rbl-main", source_upload_id=bore_upload_id), ctx=ctx, c=c)
    ppr.add_rows(_JOB, "rbl-main", ppr.RowsAdd(rows=[ppr.ExtractedRowInput(
        row_id="row-1", source_upload_id=bore_upload_id,
        raw={"start_station": "11+75", "end_station": "13+25"},
        normalized={"start_station": "11+75", "end_station": "13+25"},
        extraction_method=MANUAL_ENTRY)]), ctx=ctx, c=c)                # UNREVIEWED -> not eligible

    result = srp.create_source_route_proposal(_JOB, srp.SourceRouteProposalRequest(
        plan_upload_id=plan_upload_id, reviewed_bore_log_id="rbl-main", row_id="row-1", page_number=1,
        control_points=[_cp(0.0, 0.0), _cp(1.0, 1.0)]), ctx=ctx, c=c)
    assert result["outcome"] == "REFUSAL"
    assert result["refusal"]["code"] == "ROW_NOT_ENGINE_ELIGIBLE"


def test_proposal_no_borelog_upload_is_not_ready_refusal(tmp_path):
    # "plan_only" QA scenario has NO bore-log at all; seed a plan upload + a dummy (header-only, no rows)
    # BORE_LOG upload so the reviewed_bore_log join can exist, but the filtered readiness spine still finds
    # no source-confirmed span -> a real (never invented) non-READY refusal.
    c, ctx = _container(tmp_path), _ctx()
    _, plan_bytes, _ = _scenario_bytes(tmp_path, "plan_only")
    ppr.create_project(ppr.ProjectCreate(display_name="Label"), ctx=ctx, c=c)
    ppr.create_processing_job(ppr.JobCreate(job_id=_JOB), ctx=ctx, c=c)
    plan_upload_id = ppr.register_upload(_JOB, ppr.UploadRegister(
        kind="PLAN_PDF", filename="plan.pdf", content_base64=_b64(plan_bytes)), ctx=ctx, c=c)["upload_id"]
    bore_upload_id = ppr.register_upload(_JOB, ppr.UploadRegister(
        kind="BORE_LOG", filename="bores.csv",
        content_base64=_b64(b"row_id,start_station,end_station\n")), ctx=ctx, c=c)["upload_id"]
    ppr.create_bore_log_review(_JOB, ppr.ReviewedBoreLogCreate(
        reviewed_bore_log_id="rbl-main", source_upload_id=bore_upload_id), ctx=ctx, c=c)
    ppr.add_rows(_JOB, "rbl-main", ppr.RowsAdd(rows=[ppr.ExtractedRowInput(
        row_id="row-1", source_upload_id=bore_upload_id,
        raw={"start_station": "0+00", "end_station": "2+99"},
        normalized={"start_station": "0+00", "end_station": "2+99"},
        extraction_method=MANUAL_ENTRY)]), ctx=ctx, c=c)
    ppr.review_row_route(_JOB, "rbl-main", "row-1", ppr.RowReview(to_status=CONFIRMED), ctx=ctx, c=c)
    ppr.define_group(_JOB, "rbl-main", ppr.SegmentGroupCreate(
        group_id="grp-1", member_row_ids=["row-1"], relation=SEPARATE_BORE), ctx=ctx, c=c)
    ppr.set_group_status(_JOB, "rbl-main", "grp-1", ppr.GroupingStatus(to_status=GROUPING_CONFIRMED),
                         ctx=ctx, c=c)

    result = srp.create_source_route_proposal(_JOB, srp.SourceRouteProposalRequest(
        plan_upload_id=plan_upload_id, reviewed_bore_log_id="rbl-main", row_id="row-1", page_number=1,
        control_points=[_cp(0.0, 0.0), _cp(1.0, 1.0)]), ctx=ctx, c=c)
    assert result["outcome"] == "REFUSAL"
    assert result["refusal"]["code"] == "ROUTE_EVIDENCE_NOT_READY"
    # Fix-wave F9(b): assert the EXACT expected upstream status (never invented), not mere truthiness — the
    # dummy header-only BORE_LOG upload carries no rows the span extractor can confirm a span from.
    assert result["refusal"]["upstream_reason_code"] == "NO_SOURCE_CONFIRMED_SPAN"


def test_proposal_cross_page_refuses(tmp_path):
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id, pkg_dir = _seed_ready_job(tmp_path, c, ctx)
    a, b, _ = _real_geometry(pkg_dir)
    result = srp.create_source_route_proposal(_JOB, srp.SourceRouteProposalRequest(
        plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id, row_id=row_id, page_number=99,
        control_points=[_cp(*a), _cp(*b)]), ctx=ctx, c=c)
    assert result["outcome"] == "REFUSAL"
    assert result["refusal"]["code"] == "CROSS_PAGE_CANDIDATE"


def test_proposal_row_not_found_is_404(tmp_path):
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id, _ = _seed_ready_job(tmp_path, c, ctx)
    with pytest.raises(HTTPException) as exc:
        srp.create_source_route_proposal(_JOB, srp.SourceRouteProposalRequest(
            plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id, row_id="row-nope", page_number=1,
            control_points=[_cp(0.0, 0.0), _cp(1.0, 1.0)]), ctx=ctx, c=c)
    assert exc.value.status_code == 404


def test_proposal_malformed_control_count_is_400(tmp_path):
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id, _ = _seed_ready_job(tmp_path, c, ctx)
    with pytest.raises(HTTPException) as exc:
        srp.create_source_route_proposal(_JOB, srp.SourceRouteProposalRequest(
            plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id, row_id=row_id, page_number=1,
            control_points=[_cp(0.0, 0.0)]), ctx=ctx, c=c)
    assert exc.value.status_code == 400


def test_proposal_cross_tenant_job_is_404(tmp_path):
    c = _container(tmp_path)
    a, b = _ctx("cp-aaa"), _ctx("cp-bbb")
    plan_upload_id, rbl_id, row_id, _ = _seed_ready_job(tmp_path, c, a)
    ppr.create_project(ppr.ProjectCreate(display_name="B"), ctx=b, c=c)
    with pytest.raises(HTTPException) as exc:
        srp.create_source_route_proposal(_JOB, srp.SourceRouteProposalRequest(
            plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id, row_id=row_id, page_number=1,
            control_points=[_cp(0.0, 0.0), _cp(1.0, 1.0)]), ctx=b, c=c)
    assert exc.value.status_code == 404


# --------------------------------------------------------------------------- #
# Adoption-at-create — success, stale, invalid, scope mismatch, control mismatch, no-longer-defensible.
#
# Fix-wave F7 note: ``RouteAdoptionIn`` now REQUIRES the echo fields (plan_upload_id, reviewed_bore_log_id,
# row_id, page_number, control_points) — the client's echo of the proposal binding it claims to adopt. Tests
# below that expect a refusal BEFORE the echo is ever compared (malformed shape / create-request-own-scope
# checks) supply an arbitrary well-formed echo; tests that need the echo to actually MATCH the create request
# (to reach STALE / NO_LONGER_DEFENSIBLE, or a real success) echo the exact same identity/control_points.
# --------------------------------------------------------------------------- #
def _ra_echo(plan_upload_id, rbl_id, row_id, page_number, a, b, *, proposal_hash, confirmed=True):
    return ppr.RouteAdoptionIn(
        proposal_hash=proposal_hash, confirmed=confirmed,
        plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id, row_id=row_id, page_number=page_number,
        control_points=[_cp2(*a), _cp2(*b)])


def test_adoption_round_trip_produces_v2_record(tmp_path):
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id, pkg_dir = _seed_ready_job(tmp_path, c, ctx, key="bent_ready")
    a, b, _ = _real_geometry(pkg_dir)
    proposal = srp.create_source_route_proposal(_JOB, srp.SourceRouteProposalRequest(
        plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id, row_id=row_id, page_number=1,
        control_points=[_cp(*a), _cp(*b)]), ctx=ctx, c=c)["proposal"]

    rec = ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
        source_anchor_id="sa-adopted", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
        page_number=1, control_points=[_cp2(*a), _cp2(*b)], row_ids=[row_id],
        route_adoption=_ra_echo(plan_upload_id, rbl_id, row_id, 1, a, b,
                                proposal_hash=proposal["proposal_hash"])),
        ctx=ctx, c=c)

    assert rec["record_format"] == "trueline-source-anchor-2"
    assert rec["geometry_basis"] == "OBSERVER_BACKBONE_HUMAN_ADOPTED"
    assert rec["confirmation_state"] == "HUMAN_REVIEWED"
    assert rec["provenance"] == "HUMAN_CONFIRMED_CONTROL_POINTS"          # unchanged confirmation-authority enum
    assert rec["status"] == "VALIDATED" and rec["renderable"] is True
    assert rec["control_points"] == proposal["proposed_render_points"]    # server-derived render polyline stored
    assert len(rec["control_points"]) == 4                # start + 2 REAL bend vertices + end (3 segments)
    ra = rec["route_adoption"]
    assert ra["proposal_hash"] == proposal["proposal_hash"]
    assert ra["human_control_points"] == [{"x": a[0], "y": a[1]}, {"x": b[0], "y": b[1]}]
    assert ra["confirmed_by"] == "sess-1"
    actions = [e["action"] for e in rec["audit"]]
    assert actions == ["source_anchor_created", "observer_backbone_adopted"]


def test_adoption_stale_hash_is_409(tmp_path):
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id, pkg_dir = _seed_ready_job(tmp_path, c, ctx, key="bent_ready")
    a, b, _ = _real_geometry(pkg_dir)
    with pytest.raises(HTTPException) as exc:                             # distinguish STALE from NO_LONGER_DEFENSIBLE
        ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
            source_anchor_id="sa-1", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
            page_number=1, control_points=[_cp2(*a), _cp2(*b)], row_ids=[row_id],
            route_adoption=_ra_echo(plan_upload_id, rbl_id, row_id, 1, a, b,
                                    proposal_hash="sha256:" + "0" * 64)),
            ctx=ctx, c=c)
    assert exc.value.status_code == 409
    _assert_detail_code(exc, "ROUTE_ADOPTION_STALE")


def test_adoption_control_count_wrong_is_400(tmp_path):
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id, pkg_dir = _seed_ready_job(tmp_path, c, ctx)
    a, b, _ = _real_geometry(pkg_dir)
    with pytest.raises(HTTPException) as exc:
        ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
            source_anchor_id="sa-1", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
            page_number=1, control_points=[_cp2(*a), _cp2(*b), _cp2(1.0, 1.0)], row_ids=[row_id],
            route_adoption=_ra_echo(plan_upload_id, rbl_id, row_id, 1, a, b,
                                    proposal_hash="sha256:" + "a" * 64)),
            ctx=ctx, c=c)
    assert exc.value.status_code == 400
    _assert_detail_code(exc, "ROUTE_ADOPTION_INVALID")


def test_adoption_echo_control_count_wrong_is_400(tmp_path):
    """F7: the ECHO's own control_points must also carry exactly two — malformed on the echo side alone (the
    create request's own control_points are fine) is still ROUTE_ADOPTION_INVALID."""
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id, pkg_dir = _seed_ready_job(tmp_path, c, ctx)
    a, b, _ = _real_geometry(pkg_dir)
    with pytest.raises(HTTPException) as exc:
        ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
            source_anchor_id="sa-1", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
            page_number=1, control_points=[_cp2(*a), _cp2(*b)], row_ids=[row_id],
            route_adoption=ppr.RouteAdoptionIn(
                proposal_hash="sha256:" + "a" * 64, confirmed=True,
                plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id, row_id=row_id, page_number=1,
                control_points=[_cp2(*a)])),                              # only ONE echoed control point
            ctx=ctx, c=c)
    assert exc.value.status_code == 400
    _assert_detail_code(exc, "ROUTE_ADOPTION_INVALID")


def test_adoption_not_confirmed_is_400(tmp_path):
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id, pkg_dir = _seed_ready_job(tmp_path, c, ctx)
    a, b, _ = _real_geometry(pkg_dir)
    with pytest.raises(HTTPException) as exc:
        ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
            source_anchor_id="sa-1", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
            page_number=1, control_points=[_cp2(*a), _cp2(*b)], row_ids=[row_id],
            route_adoption=_ra_echo(plan_upload_id, rbl_id, row_id, 1, a, b,
                                    proposal_hash="sha256:" + "a" * 64, confirmed=False)),
            ctx=ctx, c=c)
    assert exc.value.status_code == 400
    _assert_detail_code(exc, "ROUTE_ADOPTION_INVALID")


def test_adoption_malformed_hash_string_is_400(tmp_path):
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id, pkg_dir = _seed_ready_job(tmp_path, c, ctx)
    a, b, _ = _real_geometry(pkg_dir)
    with pytest.raises(HTTPException) as exc:
        ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
            source_anchor_id="sa-1", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
            page_number=1, control_points=[_cp2(*a), _cp2(*b)], row_ids=[row_id],
            route_adoption=_ra_echo(plan_upload_id, rbl_id, row_id, 1, a, b, proposal_hash="not-a-hash")),
            ctx=ctx, c=c)
    assert exc.value.status_code == 400
    _assert_detail_code(exc, "ROUTE_ADOPTION_INVALID")


def test_adoption_multiple_row_ids_is_scope_mismatch_409(tmp_path):
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id, pkg_dir = _seed_ready_job(tmp_path, c, ctx)
    a, b, _ = _real_geometry(pkg_dir)
    with pytest.raises(HTTPException) as exc:
        ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
            source_anchor_id="sa-1", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
            page_number=1, control_points=[_cp2(*a), _cp2(*b)], row_ids=[row_id, "row-2"],
            route_adoption=_ra_echo(plan_upload_id, rbl_id, row_id, 1, a, b,
                                    proposal_hash="sha256:" + "a" * 64)),
            ctx=ctx, c=c)
    assert exc.value.status_code == 409
    _assert_detail_code(exc, "ROUTE_ADOPTION_SCOPE_MISMATCH")


def test_adoption_group_id_present_is_scope_mismatch_409(tmp_path):
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id, pkg_dir = _seed_ready_job(tmp_path, c, ctx)
    a, b, _ = _real_geometry(pkg_dir)
    with pytest.raises(HTTPException) as exc:
        ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
            source_anchor_id="sa-1", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
            page_number=1, control_points=[_cp2(*a), _cp2(*b)], row_ids=[row_id], group_id="grp-1",
            route_adoption=_ra_echo(plan_upload_id, rbl_id, row_id, 1, a, b,
                                    proposal_hash="sha256:" + "a" * 64)),
            ctx=ctx, c=c)
    assert exc.value.status_code == 409
    _assert_detail_code(exc, "ROUTE_ADOPTION_SCOPE_MISMATCH")


def test_adoption_echo_identity_mismatch_is_scope_mismatch_409(tmp_path):
    """F7 (1): the ECHO's identity tuple (plan/rbl/row/page) disagreeing with the create request's OWN identity
    -> ROUTE_ADOPTION_SCOPE_MISMATCH, checked BEFORE the control-points echo and BEFORE re-derivation."""
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id, pkg_dir = _seed_ready_job(tmp_path, c, ctx, key="bent_ready")
    a, b, _ = _real_geometry(pkg_dir)
    proposal = srp.create_source_route_proposal(_JOB, srp.SourceRouteProposalRequest(
        plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id, row_id=row_id, page_number=1,
        control_points=[_cp(*a), _cp(*b)]), ctx=ctx, c=c)["proposal"]

    with pytest.raises(HTTPException) as exc:
        ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
            source_anchor_id="sa-1", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
            page_number=1, control_points=[_cp2(*a), _cp2(*b)], row_ids=[row_id],
            route_adoption=_ra_echo(plan_upload_id, rbl_id, row_id, 2, a, b,       # echo page_number=2 != 1
                                    proposal_hash=proposal["proposal_hash"])),
            ctx=ctx, c=c)
    assert exc.value.status_code == 409
    _assert_detail_code(exc, "ROUTE_ADOPTION_SCOPE_MISMATCH")


def test_adoption_echo_control_points_mismatch_is_control_mismatch_409(tmp_path):
    """F7 (2): the ECHO's control_points disagreeing with the create request's OWN control_points (identity
    tuple otherwise matching) -> ROUTE_ADOPTION_CONTROL_MISMATCH, checked BEFORE re-derivation. Proves
    ``RouteAdoptionControlMismatchError`` IS reachable in this implementation (unlike the pre-fix-wave
    "unreachable, reserved" state)."""
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id, pkg_dir = _seed_ready_job(tmp_path, c, ctx, key="bent_ready")
    a, b, _ = _real_geometry(pkg_dir)
    proposal = srp.create_source_route_proposal(_JOB, srp.SourceRouteProposalRequest(
        plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id, row_id=row_id, page_number=1,
        control_points=[_cp(*a), _cp(*b)]), ctx=ctx, c=c)["proposal"]

    other_a = (a[0] + 1.0, a[1])
    with pytest.raises(HTTPException) as exc:
        ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
            source_anchor_id="sa-1", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
            page_number=1, control_points=[_cp2(*a), _cp2(*b)], row_ids=[row_id],
            route_adoption=_ra_echo(plan_upload_id, rbl_id, row_id, 1, other_a, b,   # echo start != create start
                                    proposal_hash=proposal["proposal_hash"])),
            ctx=ctx, c=c)
    assert exc.value.status_code == 409
    _assert_detail_code(exc, "ROUTE_ADOPTION_CONTROL_MISMATCH")


def test_adoption_stale_when_row_corrected_value_changes_stations_unchanged(tmp_path):
    """Fix-wave F5 (blind-verification FAIL — trust boundary): the hashed payload includes a canonical hash of
    the selected row's EFFECTIVE values (raw < normalized < review.corrected_values precedence). Correcting a
    NON-STATION value (e.g. depth) on the row between proposal and create — stations themselves untouched, so
    the geometry/span-match would otherwise look unchanged — must still invalidate the proposal: create-time
    re-derivation produces a DIFFERENT row_evidence_hash -> a different proposal_hash -> STALE."""
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id, pkg_dir = _seed_ready_job(tmp_path, c, ctx, key="bent_ready")
    a, b, _ = _real_geometry(pkg_dir)
    proposal = srp.create_source_route_proposal(_JOB, srp.SourceRouteProposalRequest(
        plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id, row_id=row_id, page_number=1,
        control_points=[_cp(*a), _cp(*b)]), ctx=ctx, c=c)["proposal"]

    # correct a NON-station value; stations stay "11+75"/"13+25" (unchanged) via raw/normalized precedence.
    from truelinev2.contracts.extracted_row import CORRECTED
    ppr.review_row_route(_JOB, rbl_id, row_id, ppr.RowReview(
        to_status=CORRECTED, reason="depth correction", corrected_values={"depth": "5.5"}), ctx=ctx, c=c)

    with pytest.raises(HTTPException) as exc:
        ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
            source_anchor_id="sa-1", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
            page_number=1, control_points=[_cp2(*a), _cp2(*b)], row_ids=[row_id],
            route_adoption=_ra_echo(plan_upload_id, rbl_id, row_id, 1, a, b,
                                    proposal_hash=proposal["proposal_hash"])),
            ctx=ctx, c=c)
    assert exc.value.status_code == 409
    _assert_detail_code(exc, "ROUTE_ADOPTION_STALE")


def test_adoption_no_longer_defensible_when_row_not_eligible(tmp_path):
    """A route_adoption bound to a row whose engine-eligibility has since been revoked (e.g. re-review) must
    refuse NO_LONGER_DEFENSIBLE, not silently adopt stale geometry."""
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id, pkg_dir = _seed_ready_job(tmp_path, c, ctx, key="bent_ready")
    a, b, _ = _real_geometry(pkg_dir)
    proposal = srp.create_source_route_proposal(_JOB, srp.SourceRouteProposalRequest(
        plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id, row_id=row_id, page_number=1,
        control_points=[_cp(*a), _cp(*b)]), ctx=ctx, c=c)["proposal"]

    # revoke eligibility: re-review the row to REJECTED after the proposal was generated
    from truelinev2.contracts.extracted_row import REJECTED
    ppr.review_row_route(_JOB, rbl_id, row_id, ppr.RowReview(to_status=REJECTED, reason="withdrawn"),
                         ctx=ctx, c=c)

    with pytest.raises(HTTPException) as exc:
        ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
            source_anchor_id="sa-1", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
            page_number=1, control_points=[_cp2(*a), _cp2(*b)], row_ids=[row_id],
            route_adoption=_ra_echo(plan_upload_id, rbl_id, row_id, 1, a, b,
                                    proposal_hash=proposal["proposal_hash"])),
            ctx=ctx, c=c)
    assert exc.value.status_code == 409
    _assert_detail_code(exc, "ROUTE_ADOPTION_NO_LONGER_DEFENSIBLE")
    assert "ROW_NOT_ENGINE_ELIGIBLE" in exc.value.detail


# --------------------------------------------------------------------------- #
# Fix-wave-2 G3 (FOREMAN RULING — amended endpoint ordering, exercised at the REAL ASGI request boundary):
# resource resolution (job/plan/RBL existence -> 404/403) runs FIRST, BEFORE any adoption validation; a
# missing/mistyped ``route_adoption`` echo field is FastAPI's own framework-standard 422 (never a code-first
# 400 — that taxonomy is reserved for WELL-TYPED-but-semantically-invalid adoption); ROUTE_ADOPTION_INVALID
# 400 runs as step 0 of ``_rederive_route_adoption`` AFTER resources resolve. See
# ``truelinev2/docs/source-route-adoption.md`` (refusal-order section) for the documented truth this proves.
# --------------------------------------------------------------------------- #
def test_adoption_missing_echo_field_is_422_via_real_endpoint(tmp_path):
    """G3(a): a well-typed JSON body whose ``route_adoption`` object is MISSING a required echo field
    (``page_number``) never reaches ``_rederive_route_adoption``'s step-0 ``ROUTE_ADOPTION_INVALID`` — FastAPI's
    own Pydantic request-body validation refuses it FIRST as a framework-standard 422, before any
    adoption-specific code runs at all. Proven via a REAL ASGI dispatch (a direct Python function call could
    only raise a ``ValidationError`` with no HTTP status attached — see the module docstring)."""
    app = _app(tmp_path)
    c, ctx = app.state.tl2, _ctx()
    plan_upload_id, rbl_id, row_id, pkg_dir = _seed_ready_job(tmp_path, c, ctx)
    a, b, _ = _real_geometry(pkg_dir)
    body = {
        "source_anchor_id": "sa-1", "plan_upload_id": plan_upload_id, "reviewed_bore_log_id": rbl_id,
        "page_number": 1, "control_points": [{"x": a[0], "y": a[1]}, {"x": b[0], "y": b[1]}],
        "row_ids": [row_id],
        "route_adoption": {
            "proposal_hash": "sha256:" + "a" * 64, "confirmed": True,
            "plan_upload_id": plan_upload_id, "reviewed_bore_log_id": rbl_id, "row_id": row_id,
            # page_number OMITTED -- a required RouteAdoptionIn echo field.
            "control_points": [{"x": a[0], "y": a[1]}, {"x": b[0], "y": b[1]}],
        },
    }
    status, _raw, parsed = _asgi_call(
        app, "POST", "/v2/product/jobs/%s/source-anchors" % _JOB, json_body=body,
        headers={"X-TL-Tenant": _NOW_TENANT, "X-TL-Session": "sess-1"})
    assert status == 422, (status, parsed)


def test_adoption_not_confirmed_with_valid_resources_is_400_exact_code_via_real_endpoint(tmp_path):
    """G3(b): ``confirmed=false`` with otherwise VALID (existing) resources -> HTTP 400 whose detail's LEADING
    token is EXACTLY ``ROUTE_ADOPTION_INVALID`` (``detail.split(":")[0]``), asserted on the REAL endpoint
    response (not a direct function call)."""
    app = _app(tmp_path)
    c, ctx = app.state.tl2, _ctx()
    plan_upload_id, rbl_id, row_id, pkg_dir = _seed_ready_job(tmp_path, c, ctx)
    a, b, _ = _real_geometry(pkg_dir)
    body = {
        "source_anchor_id": "sa-1", "plan_upload_id": plan_upload_id, "reviewed_bore_log_id": rbl_id,
        "page_number": 1, "control_points": [{"x": a[0], "y": a[1]}, {"x": b[0], "y": b[1]}],
        "row_ids": [row_id],
        "route_adoption": {
            "proposal_hash": "sha256:" + "a" * 64, "confirmed": False,
            "plan_upload_id": plan_upload_id, "reviewed_bore_log_id": rbl_id, "row_id": row_id,
            "page_number": 1, "control_points": [{"x": a[0], "y": a[1]}, {"x": b[0], "y": b[1]}],
        },
    }
    status, _raw, parsed = _asgi_call(
        app, "POST", "/v2/product/jobs/%s/source-anchors" % _JOB, json_body=body,
        headers={"X-TL-Tenant": _NOW_TENANT, "X-TL-Session": "sess-1"})
    assert status == 400, (status, parsed)
    assert parsed["detail"].split(":", 1)[0] == "ROUTE_ADOPTION_INVALID"


def test_adoption_nonexistent_plan_with_malformed_adoption_is_404_resource_first(tmp_path):
    """G3(c): a nonexistent ``plan_upload_id`` PLUS a malformed/invalid ``route_adoption`` body still returns
    404 (resource resolution) — never the 400 ``ROUTE_ADOPTION_INVALID`` the malformed body would otherwise
    produce — documenting resource-first ordering at the real endpoint boundary."""
    app = _app(tmp_path)
    c, ctx = app.state.tl2, _ctx()
    plan_upload_id, rbl_id, row_id, pkg_dir = _seed_ready_job(tmp_path, c, ctx)
    a, b, _ = _real_geometry(pkg_dir)
    body = {
        "source_anchor_id": "sa-1", "plan_upload_id": "up-does-not-exist", "reviewed_bore_log_id": rbl_id,
        "page_number": 1, "control_points": [{"x": a[0], "y": a[1]}, {"x": b[0], "y": b[1]}],
        "row_ids": [row_id],
        "route_adoption": {
            "proposal_hash": "not-a-hash", "confirmed": False,             # malformed AND semantically invalid
            "plan_upload_id": "up-does-not-exist", "reviewed_bore_log_id": rbl_id, "row_id": row_id,
            "page_number": 1, "control_points": [{"x": a[0], "y": a[1]}, {"x": b[0], "y": b[1]}],
        },
    }
    status, _raw, parsed = _asgi_call(
        app, "POST", "/v2/product/jobs/%s/source-anchors" % _JOB, json_body=body,
        headers={"X-TL-Tenant": _NOW_TENANT, "X-TL-Session": "sess-1"})
    assert status == 404, (status, parsed)


@pytest.mark.parametrize("confirmed", [True, False])
def test_adoption_nonexistent_reviewed_bore_log_is_404_resource_first(tmp_path, confirmed):
    """H1 (closing round — completes G3): a VALID job + VALID plan, but a NONEXISTENT
    ``reviewed_bore_log_id``, with an otherwise well-shaped ``route_adoption`` body (both the
    ``confirmed=true`` and ``confirmed=false`` variants) — must 404 via the EXISTING resource convention
    (the SAME 404 a create request without ``route_adoption`` at all would get for the same nonexistent RBL),
    never 400 ``ROUTE_ADOPTION_INVALID`` and never 409 ``ROUTE_ADOPTION_SCOPE_MISMATCH``. The RBL now joins
    the resource-404 tier in the CALLER, resolved BEFORE ``_rederive_route_adoption`` runs any semantic step
    (``product_pipeline_routes.py`` — the ``load_reviewed_bore_log`` call in the ``route_adoption`` branch of
    ``create_source_anchor_route``, immediately after the plan-upload resource check and BEFORE
    ``_rederive_route_adoption`` is invoked)."""
    app = _app(tmp_path)
    c, ctx = app.state.tl2, _ctx()
    plan_upload_id, rbl_id, row_id, pkg_dir = _seed_ready_job(tmp_path, c, ctx)
    a, b, _ = _real_geometry(pkg_dir)
    body = {
        "source_anchor_id": "sa-1", "plan_upload_id": plan_upload_id,
        "reviewed_bore_log_id": "rbl-does-not-exist",
        "page_number": 1, "control_points": [{"x": a[0], "y": a[1]}, {"x": b[0], "y": b[1]}],
        "row_ids": [row_id],
        "route_adoption": {
            "proposal_hash": "sha256:" + "a" * 64, "confirmed": confirmed,
            "plan_upload_id": plan_upload_id, "reviewed_bore_log_id": "rbl-does-not-exist", "row_id": row_id,
            "page_number": 1, "control_points": [{"x": a[0], "y": a[1]}, {"x": b[0], "y": b[1]}],
        },
    }
    status, _raw, parsed = _asgi_call(
        app, "POST", "/v2/product/jobs/%s/source-anchors" % _JOB, json_body=body,
        headers={"X-TL-Tenant": _NOW_TENANT, "X-TL-Session": "sess-1"})
    assert status == 404, (status, parsed)
    assert not str(parsed.get("detail", "")).startswith("ROUTE_ADOPTION_")   # never an adoption-specific code


# --------------------------------------------------------------------------- #
# Reader-survey flow-through (P5): a v2 adopted record flows through render -> station dots -> manifest ->
# closeout unmodified, producing the SAME shapes as a v1 record (plus the additive provenance fields).
# --------------------------------------------------------------------------- #
def _bundle_manifest(c, cp, job_id, bundle_id):
    from truelinev2.contracts.processing_job import job_dir
    path = job_dir(c.settings.product_store_root, cp, job_id) / "bundle_store" / "bundles" / bundle_id \
        / "redline_manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_adopted_record_renders_and_manifest_carries_adoption_fields(tmp_path):
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id, pkg_dir = _seed_ready_job(tmp_path, c, ctx, key="bent_ready")
    a, b, _ = _real_geometry(pkg_dir)
    proposal = srp.create_source_route_proposal(_JOB, srp.SourceRouteProposalRequest(
        plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id, row_id=row_id, page_number=1,
        control_points=[_cp(*a), _cp(*b)]), ctx=ctx, c=c)["proposal"]
    rec = ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
        source_anchor_id="sa-adopted", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
        page_number=1, control_points=[_cp2(*a), _cp2(*b)], row_ids=[row_id],
        start_identity=ppr.SourceAnchorIdentity(station="11+75"),
        end_identity=ppr.SourceAnchorIdentity(station="13+25"),
        route_adoption=_ra_echo(plan_upload_id, rbl_id, row_id, 1, a, b,
                                proposal_hash=proposal["proposal_hash"])),
        ctx=ctx, c=c)
    assert rec["status"] == "VALIDATED" and rec["renderable"] is True

    summary = ppr.render_source_anchor_route(_JOB, "sa-adopted", ctx=ctx, c=c)
    assert summary["status"] == "SUCCEEDED"
    assert summary["bundle_id"]
    manifest = _bundle_manifest(c, _NOW_TENANT, _JOB, summary["bundle_id"])
    log = next(l for l in manifest["logs"] if l["log_id"] == "sa-adopted")

    # additive-only fields present on the ADOPTED log, absent shape unaffected otherwise.
    assert log["geometry_basis"] == "OBSERVER_BACKBONE_HUMAN_ADOPTED"
    assert log["confirmation_state"] == "HUMAN_REVIEWED"
    assert log["render_control_points"] == rec["control_points"]
    assert log["route_adoption"]["proposal_hash"] == proposal["proposal_hash"]
    assert log["route_adoption"]["span_id"]
    # unchanged manifest truth: status/provenance/frontier stay the EXISTING enums.
    assert log["status"] == "DRAWN_REDLINE" and log["provenance"] == "OWNER_CONFIRMED_HUMAN_ADJUSTABLE"
    assert manifest["bundle_origin"] == "HUMAN_CONFIRMED_SOURCE_ANCHOR"

    # schema-valid (the additive route_adoption/geometry_basis/render_control_points/confirmation_state keys
    # are declared in redline_manifest.schema.json, additionalProperties:false would else reject them).
    from truelinev2.contracts.redline_manifest_publisher import load_schema, validate_manifest
    assert validate_manifest(manifest, load_schema()) == []


def test_manual_record_manifest_never_carries_adoption_keys(tmp_path):
    """A plain (non-adopted) manual anchor's manifest log must NOT carry any of the four additive keys —
    proves non-adopted manifests stay byte-identical."""
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id, _ = _seed_ready_job(tmp_path, c, ctx)
    ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
        source_anchor_id="sa-manual", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
        page_number=1, control_points=[_cp2(70.0, 90.0), _cp2(170.0, 110.0)], row_ids=[row_id]),
        ctx=ctx, c=c)
    summary = ppr.render_source_anchor_route(_JOB, "sa-manual", ctx=ctx, c=c)
    manifest = _bundle_manifest(c, _NOW_TENANT, _JOB, summary["bundle_id"])
    log = next(l for l in manifest["logs"] if l["log_id"] == "sa-manual")
    for key in ("geometry_basis", "confirmation_state", "render_control_points", "route_adoption"):
        assert key not in log, key


def _point_to_segment_distance(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    seg_len2 = dx * dx + dy * dy
    if seg_len2 <= 0.0:
        t = 0.0
    else:
        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg_len2))
    fx, fy = ax + t * dx, ay + t * dy
    import math as _math
    return _math.hypot(px - fx, py - fy)


def _local_cumulative_arclen(pts):
    """Fix-wave-2 G6: a LOCAL reimplementation (never imported from ``render/`` — the repo's established
    "reimplement locally" convention for pure math a test needs independently of product code, e.g.
    ``contracts.source_route_adoption._row_effective_merge``) of ``render.station_dots``'s documented
    cumulative-arc-length algorithm, so this test can derive the EXACT (unrounded) expected on-polyline point
    for a given footage and prove genuine geometric on-polyline correctness at float-representation scale."""
    cum = [0.0]
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        cum.append(cum[-1] + ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5)
    return cum


def _local_point_at_arclen(pts, cum, target):
    total = cum[-1]
    if target <= 0:
        return pts[0]
    if target >= total:
        return pts[-1]
    for i in range(len(pts) - 1):
        if cum[i] <= target <= cum[i + 1]:
            seg = cum[i + 1] - cum[i]
            t = 0.0 if seg <= 0 else (target - cum[i]) / seg
            (ax, ay), (bx, by) = pts[i], pts[i + 1]
            return (ax + t * (bx - ax), ay + t * (by - ay))
    return pts[-1]


def test_adopted_record_station_dots_ride_the_n_point_path(tmp_path):
    """No render/station_dots code change is expected: dots already interpolate along stored control_points,
    so the adopted N-point render polyline naturally rides the same interpolation, with metadata/provenance
    identical in SHAPE to a manual record's dots.

    Fix-wave-2 G6 (F9(c) FAIL — bounding-box-only 0.05pt check), H2 CORRECTED FOREMAN RULING (the original
    "<=1e-9 against the RETURNED dot" demand was miscalibrated against production's own pre-existing,
    FENCED, correct 2-decimal ``xy_display`` contract — ``render/station_dots.py:137`` rounds every dot's
    display coordinate to 2dp; that rounding is production's contract, not a test defect, and a literal 1e-9
    tolerance against a 2dp-rounded value is mathematically impossible for real (non-2dp-clean) PDF geometry
    like ``71.23198699951172``). The lock is now TWO exact assertions per dot (0 ft / every 50 ft / the
    endpoint), never a fuzzy tolerance:

    (i) the INDEPENDENTLY-recomputed EXACT (unrounded) interpolated point genuinely lies ON the adopted
        polyline within <= 1e-9 display points (float-representation noise only) — proves the true geometric
        on-polyline correctness, checked against the exact point, never the rounded one;
    (ii) the RETURNED dot's ``xy_display`` equals ``round(exact_xy, 2)`` with EXACT dict equality — the
         returned value is used AS-IS, never re-rounded by the test itself, so a dishonestly over-precise
         return (e.g. ``123.4649`` where ``123.46`` is expected) would FAIL this assertion outright; honest
         output always passes exactly because production's own 2-decimal contract means every real
         ``xy_display`` IS already ``round(<its true point>, 2)``.

    Footages themselves are asserted EXACTLY (not a fuzzy tolerance): ``dot_marks()`` produces clean values
    for a whole-number footage/interval (150.0 ft, 50.0 ft interval), so the four expected marks
    (0 / 50 / 100 / 150 ft) compare bit-for-bit."""
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id, pkg_dir = _seed_ready_job(tmp_path, c, ctx, key="bent_ready")
    a, b, _ = _real_geometry(pkg_dir)
    proposal = srp.create_source_route_proposal(_JOB, srp.SourceRouteProposalRequest(
        plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id, row_id=row_id, page_number=1,
        control_points=[_cp(*a), _cp(*b)]), ctx=ctx, c=c)["proposal"]
    rec = ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
        source_anchor_id="sa-adopted", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
        page_number=1, control_points=[_cp2(*a), _cp2(*b)], row_ids=[row_id],
        route_adoption=_ra_echo(plan_upload_id, rbl_id, row_id, 1, a, b,
                                proposal_hash=proposal["proposal_hash"])),
        ctx=ctx, c=c)
    polyline = rec["control_points"]                          # the REAL server-derived N-point (N=4) polyline
    assert len(polyline) == 4                                 # start + 2 REAL bend vertices + end (3 segments)

    summary = ppr.render_source_anchor_route(_JOB, "sa-adopted", ctx=ctx, c=c)
    dots = summary["station_dots"].get("sa-adopted") or []
    assert dots, "expected interval dots along the adopted redline (the row carries a real footage)"
    assert dots[0]["footage_along"] == 0.0
    assert dots[0]["provenance"] == "HUMAN_CONFIRMED_CONTROL_POINTS"
    for k in ("index", "footage_along", "xy_display", "provenance"):
        assert k in dots[0]

    # footages present, asserted EXACTLY (H2: no fuzzy tolerance): 0 ft, every interior 50 ft tick, and the
    # final endpoint footage (150 ft — the seeded row's own footage). Clean for a whole-number footage/interval.
    footages = sorted(d["footage_along"] for d in dots)
    assert footages == [0.0, 50.0, 100.0, 150.0]

    # LOCK UPDATE (Mission 8 addendum, owner's STATION-DOT CONTRACT, ``.foreman/scratch/m8/design-dots.md``):
    # this seeded row carries no station_readings series (start/end/footage only), so every dot is now
    # tagged SPAN_ENDPOINTS provenance via ``origin`` -- an ADDITIVE key, never affecting the footages/
    # positions asserted above or below (this test doubles as the adoption-lane POSITION-EQUALITY LOCK: the
    # addendum changes tags/metadata, never where a footage-only row's dots actually sit).
    assert [d["origin"] for d in dots] == ["SOURCE_RECORDED", "DERIVED_INTERVAL", "DERIVED_INTERVAL",
                                           "SOURCE_RECORDED"]

    footage_total = 150.0
    pts = [(p["x"], p["y"]) for p in polyline]
    cum = _local_cumulative_arclen(pts)
    total_len = cum[-1]
    for d in dots:
        fa = d["footage_along"]
        target_pt = (fa / footage_total) * total_len
        exact_xy = _local_point_at_arclen(pts, cum, target_pt)

        # the TRUE geometric on-polyline distance (against the exact, unrounded interpolated point) is tight
        # to float-representation noise only.
        min_dist = min(
            _point_to_segment_distance(exact_xy[0], exact_xy[1], pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1])
            for i in range(len(pts) - 1))
        assert min_dist <= 1e-9, (d, min_dist, exact_xy)

        # H2: the RETURNED dot's xy_display (used AS-IS, never re-rounded here) must equal round(exact_xy, 2)
        # EXACTLY. Production's own fenced contract (render/station_dots.py:137) is that xy_display is ALWAYS
        # a 2-decimal value -- so an honest dot passes this exactly; a dishonestly over-precise return (e.g.
        # 123.4649 where 123.46 is expected) fails it outright. This is NOT a tautological self-call: exact_xy
        # comes from this test's OWN independent arc-length recomputation, never from calling render code.
        assert d["xy_display"] == {"x": round(exact_xy[0], 2), "y": round(exact_xy[1], 2)}, (d, exact_xy)


def test_closeout_names_adopted_geometry_only_when_present(tmp_path):
    """Closeout adds adopted-only wording under Artifact Detail ONLY for a log carrying geometry_basis; a
    manual (non-adopted) job's closeout output must be unaffected (asserted by the manifest-shape test above;
    here we assert the manifest log itself carries the fields closeout reads from)."""
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id, pkg_dir = _seed_ready_job(tmp_path, c, ctx, key="bent_ready")
    a, b, _ = _real_geometry(pkg_dir)
    proposal = srp.create_source_route_proposal(_JOB, srp.SourceRouteProposalRequest(
        plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id, row_id=row_id, page_number=1,
        control_points=[_cp(*a), _cp(*b)]), ctx=ctx, c=c)["proposal"]
    ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
        source_anchor_id="sa-adopted", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
        page_number=1, control_points=[_cp2(*a), _cp2(*b)], row_ids=[row_id],
        route_adoption=_ra_echo(plan_upload_id, rbl_id, row_id, 1, a, b,
                                proposal_hash=proposal["proposal_hash"])),
        ctx=ctx, c=c)
    summary = ppr.render_source_anchor_route(_JOB, "sa-adopted", ctx=ctx, c=c)
    manifest = _bundle_manifest(c, _NOW_TENANT, _JOB, summary["bundle_id"])
    log = next(l for l in manifest["logs"] if l["log_id"] == "sa-adopted")
    assert log.get("geometry_basis") and log.get("route_adoption", {}).get("proposal_hash")


# --------------------------------------------------------------------------- #
# Fix-wave F9(d): v1 (manual) vs v2 (adopted) non-provenance output equality — when the human clicks happen to
# equal the adopted geometry's own termini exactly and the observer backbone is a straight through-run, the
# CLOSEOUT / manifest / render output for the v1 manual record and the v2 adopted record must agree on every
# non-provenance-specific field; v2 only ADDS the specced additive fields, never changes shared ones.
# --------------------------------------------------------------------------- #
def test_v1_manual_vs_v2_adopted_closeout_and_manifest_agree_on_shared_fields(tmp_path):
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id, pkg_dir = _seed_ready_job(tmp_path, c, ctx, key="bent_ready")
    a, b, _ = _real_geometry(pkg_dir)
    proposal = srp.create_source_route_proposal(_JOB, srp.SourceRouteProposalRequest(
        plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id, row_id=row_id, page_number=1,
        control_points=[_cp(*a), _cp(*b)]), ctx=ctx, c=c)["proposal"]
    render_points = proposal["proposed_render_points"]           # the SAME N-point path, submitted as v1 too

    # v1 manual anchor: the operator submits the adopted polyline's OWN points directly (a legitimate,
    # unrestricted N-point HUMAN geometry submission — never carries OBSERVER_BACKBONE_HUMAN_ADOPTED).
    rec_v1 = ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
        source_anchor_id="sa-manual-same-geom", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
        page_number=1, control_points=[_cp2(p["x"], p["y"]) for p in render_points], row_ids=[row_id]),
        ctx=ctx, c=c)
    # v2 adopted anchor: SAME job, same row, adopted via route_adoption.
    rec_v2 = ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
        source_anchor_id="sa-adopted-same-geom", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
        page_number=1, control_points=[_cp2(*a), _cp2(*b)], row_ids=[row_id],
        route_adoption=_ra_echo(plan_upload_id, rbl_id, row_id, 1, a, b,
                                proposal_hash=proposal["proposal_hash"])),
        ctx=ctx, c=c)

    assert rec_v1["control_points"] == rec_v2["control_points"] == render_points

    sm1 = ppr.render_source_anchor_route(_JOB, "sa-manual-same-geom", ctx=ctx, c=c)
    sm2 = ppr.render_source_anchor_route(_JOB, "sa-adopted-same-geom", ctx=ctx, c=c)
    man1 = _bundle_manifest(c, _NOW_TENANT, _JOB, sm1["bundle_id"])
    man2 = _bundle_manifest(c, _NOW_TENANT, _JOB, sm2["bundle_id"])
    log1 = next(l for l in man1["logs"] if l["log_id"] == "sa-manual-same-geom")
    log2 = next(l for l in man2["logs"] if l["log_id"] == "sa-adopted-same-geom")

    # non-provenance-specific manifest fields are IDENTICAL (same geometry -> same drawn stroke).
    for key in ("control_points", "status", "provenance", "coordinate_space", "kind"):
        if key in log1 or key in log2:
            assert log1.get(key) == log2.get(key), key
    # v2 adds ONLY the specced additive fields.
    v2_only_keys = set(log2) - set(log1)
    assert v2_only_keys <= {"geometry_basis", "confirmation_state", "render_control_points", "route_adoption"}

    # station dots: same geometry -> same dot xy/footages (provenance may legitimately differ: HUMAN_CONFIRMED
    # is the confirmation authority for BOTH v1 and v2, so even that stays identical here).
    dots1 = sm1["station_dots"].get("sa-manual-same-geom") or []
    dots2 = sm2["station_dots"].get("sa-adopted-same-geom") or []
    assert len(dots1) == len(dots2) and len(dots1) > 0
    for d1, d2 in zip(dots1, dots2):
        assert d1["footage_along"] == d2["footage_along"]
        assert d1["xy_display"] == d2["xy_display"]
        assert d1["provenance"] == d2["provenance"] == "HUMAN_CONFIRMED_CONTROL_POINTS"


def _pdf_text(data: bytes) -> str:
    """Extract full text from PDF bytes via fitz (already a v2 dependency — ``contracts.closeout_pdf`` itself
    uses it). The closeout PDF's content streams are NOT raw-byte-searchable (PyMuPDF compresses them), so a
    real assertion on the packet's wording needs real PDF text extraction, not a substring probe on ``data``."""
    import fitz

    doc = fitz.open(stream=data, filetype="pdf")
    try:
        return "".join(page.get_text() for page in doc)
    finally:
        doc.close()


_CAPTION_BAND_H = 30    # render/crop.py::render_redline_stroke: draw.rectangle([0, 0, img.width, 30], ...)
                        # -- the FIXED-height diagnostic caption band (only rows y < 30 are ever touched).


def _read_artifact_png_bytes(c, cp, job_id, bundle_id, artifact_path):
    from truelinev2.contracts.processing_job import job_dir

    return (job_dir(c.settings.product_store_root, cp, job_id) / "bundle_store" / "bundles" / bundle_id
            / artifact_path).read_bytes()


def _pixels_below_caption_band(png_bytes):
    """The evidentiary DRAWN pixels only (excludes the fixed-height diagnostic caption band rows y < 30 —
    see the root-cause comment on the assertion below)."""
    import io

    from PIL import Image

    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    w, h = img.size
    return list(img.crop((0, _CAPTION_BAND_H, w, h)).getdata())


def test_v1_manual_vs_v2_adopted_closeout_pdf_build_and_export_assembly_agree_on_shared_outputs(tmp_path):
    """Fix-wave-2 G7 (F9(d) FAIL — the alleged v1-vs-v2 equality test never called either the closeout-PDF-
    build or the export/bundle-assembly path). This test actually CALLS the real
    ``download_closeout_pdf`` (-> ``contracts.closeout_pdf.build_closeout_pdf``) and
    ``assemble_export_package_route`` / ``get_export_package`` / ``download_export_package`` paths for BOTH a
    v1 manual record and a v2 adopted record (same job, same geometry, rendered sequentially), and compares
    their SHARED derived outputs: v2 differs from v1 ONLY by the specced additive provenance (the manifest's
    ``route_adoption``/``geometry_basis`` fields, and one ADOPTED-ONLY wording line in the closeout PDF text) —
    never in the underlying deliverable quantities, export-package view, or redline artifact identity."""
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id, pkg_dir = _seed_ready_job(tmp_path, c, ctx, key="bent_ready")
    a, b, _ = _real_geometry(pkg_dir)
    proposal = srp.create_source_route_proposal(_JOB, srp.SourceRouteProposalRequest(
        plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id, row_id=row_id, page_number=1,
        control_points=[_cp(*a), _cp(*b)]), ctx=ctx, c=c)["proposal"]
    render_points = proposal["proposed_render_points"]

    # v1 manual anchor (SAME geometry, no route_adoption) -> render -> real closeout PDF + export assembly.
    ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
        source_anchor_id="sa-manual-x", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
        page_number=1, control_points=[_cp2(p["x"], p["y"]) for p in render_points], row_ids=[row_id]),
        ctx=ctx, c=c)
    ppr.render_source_anchor_route(_JOB, "sa-manual-x", ctx=ctx, c=c)

    pdf_v1 = ppr.download_closeout_pdf(_JOB, ctx=ctx, c=c)
    assert pdf_v1.status_code == 200 and len(pdf_v1.body) > 1000
    view_v1 = ppr.assemble_export_package_route(_JOB, ctx=ctx, c=c)
    assert ppr.get_export_package(_JOB, ctx=ctx, c=c)["view"]
    zip_v1 = ppr.download_export_package(_JOB, ctx=ctx, c=c)
    assert zip_v1.status_code == 200 and len(zip_v1.body) > 0
    artifacts_v1 = ppr.list_artifacts(_JOB, ctx=ctx, c=c)
    text_v1 = _pdf_text(pdf_v1.body)

    # v2 adopted anchor (SAME job, SAME geometry, via route_adoption) -> render -> real closeout PDF + export.
    ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
        source_anchor_id="sa-adopted-x", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
        page_number=1, control_points=[_cp2(*a), _cp2(*b)], row_ids=[row_id],
        route_adoption=_ra_echo(plan_upload_id, rbl_id, row_id, 1, a, b,
                                proposal_hash=proposal["proposal_hash"])),
        ctx=ctx, c=c)
    ppr.render_source_anchor_route(_JOB, "sa-adopted-x", ctx=ctx, c=c)

    pdf_v2 = ppr.download_closeout_pdf(_JOB, ctx=ctx, c=c)
    assert pdf_v2.status_code == 200 and len(pdf_v2.body) > 1000
    view_v2 = ppr.assemble_export_package_route(_JOB, ctx=ctx, c=c)
    assert ppr.get_export_package(_JOB, ctx=ctx, c=c)["view"]
    zip_v2 = ppr.download_export_package(_JOB, ctx=ctx, c=c)
    assert zip_v2.status_code == 200 and len(zip_v2.body) > 0
    artifacts_v2 = ppr.list_artifacts(_JOB, ctx=ctx, c=c)
    text_v2 = _pdf_text(pdf_v2.body)

    # SHARED deliverable quantity: both real bundles carry a validated FINAL_REDLINE_PNG for their own log
    # (proves both real paths actually produced trusted evidence, not merely "didn't crash"). v2's bundle
    # (rendered second, same job) accumulates BOTH logs; v1's own sha256 is still present unchanged in it —
    # the v1 evidence itself was never mutated by rendering v2 alongside it in the same job.
    sha_v1 = {art["sha256"] for art in artifacts_v1["artifacts"]}
    sha_v2 = {art["sha256"] for art in artifacts_v2["artifacts"]}
    assert sha_v1 and sha_v1 <= sha_v2                            # v1's evidence unchanged by v2's later render

    # DIAGNOSED (coordinator follow-up): the FULL PNG files are NOT byte-identical between v1/v2 (confirmed:
    # sha256 differs, ~130 bytes). Root cause traced by direct pixel diff: render/crop.py::render_redline_stroke
    # (called from render/source_anchor_render.py's ``render_job_source_anchors``, which never passes
    # ``caption=False``, so its documented default ``caption=True`` applies) draws a FIXED-height diagnostic
    # caption band (rows y < 30: ``draw.rectangle([0, 0, img.width, 30], ...)`` + ``draw.text((8, 8), cap, ...)``
    # at truelinev2/render/crop.py:145-146) whose text embeds ``bore_id`` (== the record's OWN
    # ``source_anchor_id``) and ``reason`` (which also embeds it) — see the call site at
    # truelinev2/render/source_anchor_render.py:205-206 (``bore_id=sa_id``,
    # ``reason="human-confirmed source anchor %s" % sa_id``). TWO DISTINCT records ALWAYS have two distinct
    # ids (that IS their primary key — colliding them is impossible, a re-used id 409s), so this diagnostic
    # band ALWAYS differs between any two records, v1-vs-v1 or v1-vs-v2 alike — it is symmetric, pre-existing
    # (untouched by any commit in this ticket; the render/** fence diff is empty), and carries no
    # route_adoption/geometry_basis content at all: it is NOT a v2-only field reaching the renderer.
    # Confirmed empirically: cropping BOTH PNGs to rows y >= 30 (excluding only the caption band) makes the
    # remaining pixel content of these two same-geometry records EXACTLY identical (verified directly with
    # PIL before writing this assertion). The row/footage/dot-metadata hypothesis is REFUTED — both records
    # here already share the same row_ids/page, so ``_dots_for_anchor`` computes identical dots for both; the
    # difference was never about input parity on the evidence side, only about the mandatory-unique caption
    # text. This is the strongest achievable equality (full-file sha equality is architecturally unreachable
    # while two distinct ids both go through this pre-existing caption default): the ACTUAL drawn evidence —
    # stroke geometry, markers, everything render_redline_stroke draws from stroke_points/mandatory_points —
    # is pixel-for-pixel identical, proving route_adoption/geometry_basis provenance truly never reaches the
    # renderer or changes a single evidentiary pixel.
    art_v1 = next(art for art in artifacts_v1["artifacts"] if art["log_id"] == "sa-manual-x")
    art_v2 = next(art for art in artifacts_v2["artifacts"] if art["log_id"] == "sa-adopted-x")
    png_v1 = _read_artifact_png_bytes(c, _NOW_TENANT, _JOB, artifacts_v1["bundle_id"], art_v1["path"])
    png_v2 = _read_artifact_png_bytes(c, _NOW_TENANT, _JOB, artifacts_v2["bundle_id"], art_v2["path"])
    assert _pixels_below_caption_band(png_v1) == _pixels_below_caption_band(png_v2)

    # export-package view: the shared structural fields agree (both assemble cleanly, same blockers/status).
    for key in ("status", "blockers"):
        if key in view_v1 or key in view_v2:
            assert view_v1.get(key) == view_v2.get(key), key

    # closeout PDF TEXT (real fitz extraction, not a raw-byte search — PyMuPDF compresses content streams):
    # v1's packet carries no ADOPTED-ONLY wording; v2's DOES -- the specced additive difference, never a
    # change to the shared deliverable-quantity sections both packets carry identically.
    marker = "source-backed observer backbone"
    assert marker not in text_v1
    assert marker in text_v2
    assert "1. Job / Project Summary" in text_v1 and "1. Job / Project Summary" in text_v2
    assert "3. Deliverable Quantities" in text_v1 and "3. Deliverable Quantities" in text_v2


def test_adoption_tenant_isolation(tmp_path):
    c = _container(tmp_path)
    a_ctx, b_ctx = _ctx("cp-aaa"), _ctx("cp-bbb")
    plan_upload_id, rbl_id, row_id, pkg_dir = _seed_ready_job(tmp_path, c, a_ctx)
    a, b, _ = _real_geometry(pkg_dir)
    ppr.create_project(ppr.ProjectCreate(display_name="B"), ctx=b_ctx, c=c)
    with pytest.raises(HTTPException) as exc:                    # B has no job-1 -> 404 before any derivation
        ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
            source_anchor_id="sa-1", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
            page_number=1, control_points=[_cp2(*a), _cp2(*b)], row_ids=[row_id],
            route_adoption=_ra_echo(plan_upload_id, rbl_id, row_id, 1, a, b,
                                    proposal_hash="sha256:" + "a" * 64)),
            ctx=b_ctx, c=c)
    assert exc.value.status_code == 404


# --------------------------------------------------------------------------- #
# Fix-wave F9(a): OFF vs ON-without-adoption byte-identity — compare the FULL serialized v1 record and the
# FULL response body byte-for-byte between flag states (not field-presence probing).
# --------------------------------------------------------------------------- #
def _seed_ready_job_from_bytes(c, ctx, plan_bytes, borelog_bytes, job_id=_JOB):
    """Like ``_seed_ready_job`` but takes ALREADY-BUILT plan/bore-log bytes (so two separate containers seeded
    from the SAME bytes get IDENTICAL content-hash-derived upload_ids — required for a true byte-for-byte
    comparison across two independent stores)."""
    ppr.create_project(ppr.ProjectCreate(display_name="Label"), ctx=ctx, c=c)
    ppr.create_processing_job(ppr.JobCreate(job_id=job_id), ctx=ctx, c=c)
    plan_upload_id = ppr.register_upload(
        job_id, ppr.UploadRegister(kind="PLAN_PDF", filename="plan.pdf", content_base64=_b64(plan_bytes)),
        ctx=ctx, c=c)["upload_id"]
    bore_upload_id = ppr.register_upload(
        job_id, ppr.UploadRegister(kind="BORE_LOG", filename="bore-log.csv",
                                   content_base64=_b64(borelog_bytes)), ctx=ctx, c=c)["upload_id"]
    rbl_id = "rbl-main"
    ppr.create_bore_log_review(
        job_id, ppr.ReviewedBoreLogCreate(reviewed_bore_log_id=rbl_id, source_upload_id=bore_upload_id),
        ctx=ctx, c=c)
    row_id = "row-1"
    ppr.add_rows(job_id, rbl_id, ppr.RowsAdd(rows=[ppr.ExtractedRowInput(
        row_id=row_id, source_upload_id=bore_upload_id,
        raw={"start_station": "11+75", "end_station": "13+25", "footage": "150"},
        normalized={"start_station": "11+75", "end_station": "13+25", "footage": "150"},
        extraction_method=MANUAL_ENTRY)]), ctx=ctx, c=c)
    ppr.review_row_route(job_id, rbl_id, row_id, ppr.RowReview(to_status=CONFIRMED), ctx=ctx, c=c)
    ppr.define_group(job_id, rbl_id, ppr.SegmentGroupCreate(
        group_id="grp-1", member_row_ids=[row_id], relation=SEPARATE_BORE), ctx=ctx, c=c)
    ppr.set_group_status(job_id, rbl_id, "grp-1", ppr.GroupingStatus(to_status=GROUPING_CONFIRMED), ctx=ctx, c=c)
    return plan_upload_id, rbl_id, row_id


def _source_anchor_record_path(store_root, cp, job_id, source_anchor_id):
    from truelinev2.contracts.processing_job import job_dir
    from truelinev2.contracts.source_anchor import SOURCE_ANCHOR_FILENAME, SOURCE_ANCHORS_SUBDIR

    return (job_dir(store_root, cp, job_id) / SOURCE_ANCHORS_SUBDIR / source_anchor_id
            / SOURCE_ANCHOR_FILENAME)


def test_flag_off_and_on_without_adoption_produce_byte_identical_records(tmp_path, monkeypatch):
    """Fix-wave-2 G5 (F9(a) FAIL — canonicalized-dict compare, not real bytes): compares RAW STORED RECORD
    FILE BYTES on disk and RAW HTTP RESPONSE BODY BYTES across flag states (OFF vs ON-without-adoption), via a
    REAL ASGI POST dispatch (``_asgi_call`` — routing + header context + Pydantic validation, not a direct
    Python function call), rather than ``json.dumps(rec, sort_keys=True)`` canonicalization — which could mask
    a genuine byte-level difference (e.g. key ORDER) that a real client or a stored-file diff tool would still
    observe."""
    monkeypatch.setattr(ppr, "_now", lambda: "2026-01-01T00:00:00+00:00")
    _, plan_bytes, borelog_bytes = _scenario_bytes(tmp_path)
    headers = {"X-TL-Tenant": _NOW_TENANT, "X-TL-Session": "sess-1"}
    app_off = _app(tmp_path / "off", adoption=False)
    app_on = _app(tmp_path / "on", adoption=True)
    c_off, c_on = app_off.state.tl2, app_on.state.tl2
    ctx = _ctx()
    plan_off, rbl_off, row_off = _seed_ready_job_from_bytes(c_off, ctx, plan_bytes, borelog_bytes)
    plan_on, rbl_on, row_on = _seed_ready_job_from_bytes(c_on, ctx, plan_bytes, borelog_bytes)
    assert (plan_off, rbl_off, row_off) == (plan_on, rbl_on, row_on)      # sanity: deterministic content ids

    body = {
        "source_anchor_id": "sa-1", "plan_upload_id": plan_off, "reviewed_bore_log_id": rbl_off,
        "page_number": 1, "control_points": [{"x": 70.0, "y": 90.0}, {"x": 170.0, "y": 110.0}],
        "row_ids": [row_off],
    }
    status_off, resp_bytes_off, parsed_off = _asgi_call(
        app_off, "POST", "/v2/product/jobs/%s/source-anchors" % _JOB, json_body=body, headers=headers)
    status_on, resp_bytes_on, parsed_on = _asgi_call(
        app_on, "POST", "/v2/product/jobs/%s/source-anchors" % _JOB, json_body=body, headers=headers)
    assert status_off == status_on == 200
    assert parsed_off["record_format"] == parsed_on["record_format"] == "trueline-source-anchor-1"

    # RAW HTTP RESPONSE BODY BYTES, byte-for-byte, across flag states.
    assert resp_bytes_off == resp_bytes_on

    # RAW STORED RECORD FILE BYTES on disk, byte-for-byte, across two independent stores.
    path_off = _source_anchor_record_path(c_off.settings.product_store_root, _NOW_TENANT, _JOB, "sa-1")
    path_on = _source_anchor_record_path(c_on.settings.product_store_root, _NOW_TENANT, _JOB, "sa-1")
    assert path_off.read_bytes() == path_on.read_bytes()
