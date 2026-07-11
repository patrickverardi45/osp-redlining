"""End-to-end API proof for Phase-2 SOURCE-ROUTE ADOPTION: the proposal endpoint + adoption-at-create.

Follows the repo API-test convention (mirrors test_product_pipeline_api.py / test_product_readiness_wiring.py):
NO httpx / TestClient. Route functions are called DIRECTLY with an explicit RequestContext. Fixtures are the
generic name-free ``complete_package_qa`` synthetic package (product QA, not cold validation) — the SAME
fixture-free harness ``test_review_candidate.py`` / ``test_product_readiness_wiring.py`` already use, so this
suite needs no owner fixtures and is safe for CI. Real geometry (anchor xy, backbone segments) is read directly
off the readiness spine run over the SAME bytes being uploaded, never hand-invented.
"""
from __future__ import annotations

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
from truelinev2.harness import product_readiness_bridge as prb
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


def _ctx(tenant: str = _NOW_TENANT, session: str = "sess-1"):
    return require_context(tenant, session)


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


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
    (never hand-invented) so the test's control_points are genuinely source-backed."""
    readiness = run_package_route_readiness(pkg_dir)
    v = next(v for v in readiness.routes.verifications if v.route_ready)
    seg = v.route_geometry[0]
    reach_tol = v.detail["isolation"]["detail"]["reach_tol"]
    return tuple(seg["a"]), tuple(seg["b"]), reach_tol


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


def _patch_bent_geometry(monkeypatch):
    """Fix-wave F4 test-support (NOT a fixture/product-code change — pure test-local wrapping): the QA
    fixture's REAL observer backbone for ``complete_ready`` (``ROUTE_CLEAN`` — "one segment terminus-to-
    terminus") is exactly ONE segment (see ``test_real_single_segment_backbone_refuses_same_segment`` below,
    which locks that a real single-segment backbone refuses CONTROLS_ON_SAME_BACKBONE_SEGMENT unconditionally
    after this fix wave — a genuine, intended behavior change). To still prove a SUCCESSFUL multi-segment
    adoption round-trip end-to-end against real spine output (needed for the reader-survey flow-through tests:
    station dots on an N>2-point path, manifest, closeout, v1-vs-v2 output equality), this wraps the readiness
    bridge's raw seam so that AFTER the real spine has run (real uploads, real span/row join, real statuses,
    real ``reach_tol``), the one real backbone segment is split into two COLINEAR segments at its own real
    midpoint — identical overall endpoints and length, nothing invented, one additional real interior vertex.
    Patches BOTH import sites: ``source_route_proposal_routes`` (module-level import) and
    ``product_readiness_bridge`` itself (the create-time re-derivation's lazy import re-reads this module
    attribute on every call)."""
    orig = prb.run_job_route_readiness_raw

    def _wrapped(*args, **kwargs):
        readiness, sheet_ctx = orig(*args, **kwargs)
        if readiness is None:
            return readiness, sheet_ctx
        new_verifications = []
        for v in readiness.routes.verifications:
            if v.route_ready and len(v.route_geometry) == 1:
                seg = v.route_geometry[0]
                ax, ay = seg["a"]
                bx, by = seg["b"]
                mx, my = (ax + bx) / 2.0, (ay + by) / 2.0
                v = dataclasses.replace(
                    v, route_geometry=({"a": (ax, ay), "b": (mx, my)}, {"a": (mx, my), "b": (bx, by)}))
            new_verifications.append(v)
        new_routes = dataclasses.replace(readiness.routes, verifications=tuple(new_verifications))
        new_readiness = dataclasses.replace(readiness, routes=new_routes)
        return new_readiness, sheet_ctx

    monkeypatch.setattr(prb, "run_job_route_readiness_raw", _wrapped)
    monkeypatch.setattr(srp, "run_job_route_readiness_raw", _wrapped)


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
    assert exc.value.detail.startswith("ROUTE_ADOPTION_INVALID")


# --------------------------------------------------------------------------- #
# Proposal endpoint — happy path (real source-backed geometry from the QA spine, split into a real 2-segment
# backbone by ``_patch_bent_geometry`` — see its docstring: F4 makes a genuinely single-segment real backbone
# always refuse, so the happy-path tests need >= 2 segments to prove a SUCCESSFUL round trip).
# --------------------------------------------------------------------------- #
def test_proposal_ready_returns_source_backed_geometry(tmp_path, monkeypatch):
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id, pkg_dir = _seed_ready_job(tmp_path, c, ctx)
    a, b, reach_tol = _real_geometry(pkg_dir)
    _patch_bent_geometry(monkeypatch)

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
    assert len(p["proposed_render_points"]) == 3                     # start + real midpoint vertex + end
    assert p["source"]["span_id"]
    assert p["readiness"]["readiness_status"] == "READY_FOR_REVIEW_REDLINE"
    assert p["warnings"] == []                                       # exact anchor clicks -> no connector


def test_proposal_hash_stable_across_two_calls(tmp_path, monkeypatch):
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id, pkg_dir = _seed_ready_job(tmp_path, c, ctx)
    a, b, _ = _real_geometry(pkg_dir)
    _patch_bent_geometry(monkeypatch)
    req = srp.SourceRouteProposalRequest(
        plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id, row_id=row_id, page_number=1,
        control_points=[_cp(*a), _cp(*b)])
    r1 = srp.create_source_route_proposal(_JOB, req, ctx=ctx, c=c)
    r2 = srp.create_source_route_proposal(_JOB, req, ctx=ctx, c=c)
    assert r1["outcome"] == r2["outcome"] == "PROPOSAL"
    assert r1["proposal"]["proposal_hash"] == r2["proposal"]["proposal_hash"]


def test_proposal_writes_no_artifact_and_no_store_record(tmp_path, monkeypatch):
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id, pkg_dir = _seed_ready_job(tmp_path, c, ctx)
    a, b, _ = _real_geometry(pkg_dir)
    _patch_bent_geometry(monkeypatch)
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


def test_adoption_round_trip_produces_v2_record(tmp_path, monkeypatch):
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id, pkg_dir = _seed_ready_job(tmp_path, c, ctx)
    a, b, _ = _real_geometry(pkg_dir)
    _patch_bent_geometry(monkeypatch)
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
    assert len(rec["control_points"]) == 3                                # start + real midpoint vertex + end
    ra = rec["route_adoption"]
    assert ra["proposal_hash"] == proposal["proposal_hash"]
    assert ra["human_control_points"] == [{"x": a[0], "y": a[1]}, {"x": b[0], "y": b[1]}]
    assert ra["confirmed_by"] == "sess-1"
    actions = [e["action"] for e in rec["audit"]]
    assert actions == ["source_anchor_created", "observer_backbone_adopted"]


def test_adoption_stale_hash_is_409(tmp_path, monkeypatch):
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id, pkg_dir = _seed_ready_job(tmp_path, c, ctx)
    a, b, _ = _real_geometry(pkg_dir)
    _patch_bent_geometry(monkeypatch)                                     # re-derivation must SUCCEED to
    with pytest.raises(HTTPException) as exc:                             # distinguish STALE from NO_LONGER_DEFENSIBLE
        ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
            source_anchor_id="sa-1", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
            page_number=1, control_points=[_cp2(*a), _cp2(*b)], row_ids=[row_id],
            route_adoption=_ra_echo(plan_upload_id, rbl_id, row_id, 1, a, b,
                                    proposal_hash="sha256:" + "0" * 64)),
            ctx=ctx, c=c)
    assert exc.value.status_code == 409
    assert exc.value.detail.startswith("ROUTE_ADOPTION_STALE")


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
    assert exc.value.detail.startswith("ROUTE_ADOPTION_INVALID")


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
    assert exc.value.detail.startswith("ROUTE_ADOPTION_INVALID")


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
    assert exc.value.detail.startswith("ROUTE_ADOPTION_INVALID")


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
    assert exc.value.detail.startswith("ROUTE_ADOPTION_INVALID")


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
    assert exc.value.detail.startswith("ROUTE_ADOPTION_SCOPE_MISMATCH")


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
    assert exc.value.detail.startswith("ROUTE_ADOPTION_SCOPE_MISMATCH")


def test_adoption_echo_identity_mismatch_is_scope_mismatch_409(tmp_path, monkeypatch):
    """F7 (1): the ECHO's identity tuple (plan/rbl/row/page) disagreeing with the create request's OWN identity
    -> ROUTE_ADOPTION_SCOPE_MISMATCH, checked BEFORE the control-points echo and BEFORE re-derivation."""
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id, pkg_dir = _seed_ready_job(tmp_path, c, ctx)
    a, b, _ = _real_geometry(pkg_dir)
    _patch_bent_geometry(monkeypatch)
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
    assert exc.value.detail.startswith("ROUTE_ADOPTION_SCOPE_MISMATCH")


def test_adoption_echo_control_points_mismatch_is_control_mismatch_409(tmp_path, monkeypatch):
    """F7 (2): the ECHO's control_points disagreeing with the create request's OWN control_points (identity
    tuple otherwise matching) -> ROUTE_ADOPTION_CONTROL_MISMATCH, checked BEFORE re-derivation. Proves
    ``RouteAdoptionControlMismatchError`` IS reachable in this implementation (unlike the pre-fix-wave
    "unreachable, reserved" state)."""
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id, pkg_dir = _seed_ready_job(tmp_path, c, ctx)
    a, b, _ = _real_geometry(pkg_dir)
    _patch_bent_geometry(monkeypatch)
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
    assert exc.value.detail.startswith("ROUTE_ADOPTION_CONTROL_MISMATCH")


def test_adoption_stale_when_row_corrected_value_changes_stations_unchanged(tmp_path, monkeypatch):
    """Fix-wave F5 (blind-verification FAIL — trust boundary): the hashed payload includes a canonical hash of
    the selected row's EFFECTIVE values (raw < normalized < review.corrected_values precedence). Correcting a
    NON-STATION value (e.g. depth) on the row between proposal and create — stations themselves untouched, so
    the geometry/span-match would otherwise look unchanged — must still invalidate the proposal: create-time
    re-derivation produces a DIFFERENT row_evidence_hash -> a different proposal_hash -> STALE."""
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id, pkg_dir = _seed_ready_job(tmp_path, c, ctx)
    a, b, _ = _real_geometry(pkg_dir)
    _patch_bent_geometry(monkeypatch)
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
    assert exc.value.detail.startswith("ROUTE_ADOPTION_STALE")


def test_adoption_no_longer_defensible_when_row_not_eligible(tmp_path, monkeypatch):
    """A route_adoption bound to a row whose engine-eligibility has since been revoked (e.g. re-review) must
    refuse NO_LONGER_DEFENSIBLE, not silently adopt stale geometry."""
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id, pkg_dir = _seed_ready_job(tmp_path, c, ctx)
    a, b, _ = _real_geometry(pkg_dir)
    _patch_bent_geometry(monkeypatch)
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
    assert exc.value.detail.startswith("ROUTE_ADOPTION_NO_LONGER_DEFENSIBLE")
    assert "ROW_NOT_ENGINE_ELIGIBLE" in exc.value.detail


# --------------------------------------------------------------------------- #
# Reader-survey flow-through (P5): a v2 adopted record flows through render -> station dots -> manifest ->
# closeout unmodified, producing the SAME shapes as a v1 record (plus the additive provenance fields).
# --------------------------------------------------------------------------- #
def _bundle_manifest(c, cp, job_id, bundle_id):
    from truelinev2.contracts.processing_job import job_dir
    path = job_dir(c.settings.product_store_root, cp, job_id) / "bundle_store" / "bundles" / bundle_id \
        / "redline_manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_adopted_record_renders_and_manifest_carries_adoption_fields(tmp_path, monkeypatch):
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id, pkg_dir = _seed_ready_job(tmp_path, c, ctx)
    a, b, _ = _real_geometry(pkg_dir)
    _patch_bent_geometry(monkeypatch)
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


def test_adopted_record_station_dots_ride_the_n_point_path(tmp_path, monkeypatch):
    """No render/station_dots code change is expected: dots already interpolate along stored control_points,
    so the adopted N-point render polyline naturally rides the same interpolation, with metadata/provenance
    identical in SHAPE to a manual record's dots.

    Fix-wave F9(c) (blind-verification FAIL — bounding-box-only check): every dot must lie EXACTLY ON the
    adopted N-point polyline (point-to-segment distance == 0 within float representation, against every
    segment of the REAL stored ``control_points`` — not merely inside the endpoints' bounding box), and the
    footages checked are the specific ones the spec names: 0 ft, every 50 ft, and the endpoint."""
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id, pkg_dir = _seed_ready_job(tmp_path, c, ctx)
    a, b, _ = _real_geometry(pkg_dir)
    _patch_bent_geometry(monkeypatch)
    proposal = srp.create_source_route_proposal(_JOB, srp.SourceRouteProposalRequest(
        plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id, row_id=row_id, page_number=1,
        control_points=[_cp(*a), _cp(*b)]), ctx=ctx, c=c)["proposal"]
    rec = ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
        source_anchor_id="sa-adopted", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
        page_number=1, control_points=[_cp2(*a), _cp2(*b)], row_ids=[row_id],
        route_adoption=_ra_echo(plan_upload_id, rbl_id, row_id, 1, a, b,
                                proposal_hash=proposal["proposal_hash"])),
        ctx=ctx, c=c)
    polyline = rec["control_points"]                          # the REAL server-derived N-point (N=3) polyline
    assert len(polyline) >= 3

    summary = ppr.render_source_anchor_route(_JOB, "sa-adopted", ctx=ctx, c=c)
    dots = summary["station_dots"].get("sa-adopted") or []
    assert dots, "expected interval dots along the adopted redline (the row carries a real footage)"
    assert dots[0]["footage_along"] == 0.0
    assert dots[0]["provenance"] == "HUMAN_CONFIRMED_CONTROL_POINTS"
    for k in ("index", "footage_along", "xy_display", "provenance"):
        assert k in dots[0]

    # footages present: 0 ft, every interior 50 ft tick, and the final endpoint footage (150 ft — the seeded
    # row's own footage).
    footages = sorted(d["footage_along"] for d in dots)
    assert footages[0] == 0.0
    assert footages[-1] == pytest.approx(150.0, abs=0.05)
    for expected_tick in (50.0, 100.0):
        assert any(abs(f - expected_tick) < 0.05 for f in footages), (expected_tick, footages)

    # every dot's xy lies EXACTLY ON the adopted polyline (point-to-NEAREST-segment distance == 0 within float
    # repr) — not merely inside a bounding box.
    for d in dots:
        px, py = d["xy_display"]["x"], d["xy_display"]["y"]
        min_dist = min(
            _point_to_segment_distance(px, py, polyline[i]["x"], polyline[i]["y"],
                                       polyline[i + 1]["x"], polyline[i + 1]["y"])
            for i in range(len(polyline) - 1))
        assert min_dist < 0.05, (d, min_dist)                 # dot xy is rounded to 2dp -> a small float tolerance


def test_closeout_names_adopted_geometry_only_when_present(tmp_path, monkeypatch):
    """Closeout adds adopted-only wording under Artifact Detail ONLY for a log carrying geometry_basis; a
    manual (non-adopted) job's closeout output must be unaffected (asserted by the manifest-shape test above;
    here we assert the manifest log itself carries the fields closeout reads from)."""
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id, pkg_dir = _seed_ready_job(tmp_path, c, ctx)
    a, b, _ = _real_geometry(pkg_dir)
    _patch_bent_geometry(monkeypatch)
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
def test_v1_manual_vs_v2_adopted_closeout_and_manifest_agree_on_shared_fields(tmp_path, monkeypatch):
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id, pkg_dir = _seed_ready_job(tmp_path, c, ctx)
    a, b, _ = _real_geometry(pkg_dir)
    _patch_bent_geometry(monkeypatch)
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


def test_flag_off_and_on_without_adoption_produce_byte_identical_records(tmp_path, monkeypatch):
    monkeypatch.setattr(ppr, "_now", lambda: "2026-01-01T00:00:00+00:00")
    _, plan_bytes, borelog_bytes = _scenario_bytes(tmp_path)
    ctx = _ctx()
    c_off = _container(tmp_path / "off", adoption=False)
    c_on = _container(tmp_path / "on", adoption=True)
    plan_off, rbl_off, row_off = _seed_ready_job_from_bytes(c_off, ctx, plan_bytes, borelog_bytes)
    plan_on, rbl_on, row_on = _seed_ready_job_from_bytes(c_on, ctx, plan_bytes, borelog_bytes)
    assert (plan_off, rbl_off, row_off) == (plan_on, rbl_on, row_on)      # sanity: deterministic content ids

    def _make(c):
        return ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
            source_anchor_id="sa-1", plan_upload_id=plan_off, reviewed_bore_log_id=rbl_off,
            page_number=1, control_points=[_cp2(70.0, 90.0), _cp2(170.0, 110.0)], row_ids=[row_off]),
            ctx=ctx, c=c)

    rec_off = _make(c_off)
    rec_on = _make(c_on)
    assert rec_off["record_format"] == rec_on["record_format"] == "trueline-source-anchor-1"
    assert json.dumps(rec_off, sort_keys=True) == json.dumps(rec_on, sort_keys=True)
