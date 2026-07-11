"""Mission 8 — honest representative fallback + manual N-point polyline (backend seam).

Flag-gated (``TL2_SOURCE_ANCHOR_MANUAL_ROUTE_OPTIN``, default OFF), ADDITIVE ``manual_route`` provenance
block on the EXISTING ``POST /v2/product/jobs/{job_id}/source-anchors``. Closes the customer-visible defect
where a refused source-route-adoption search left an unlabeled 2-point fallback chord rendering across
houses/aerial imagery looking like a finished engineered route: the operator either accepts an honestly
LABELED "representative straight segment", or adds/moves/removes bend points into a manual polyline, and
must EXPLICITLY confirm before the route is stored as HUMAN_REVIEWED.

Follows the SAME fixture-free, no-httpx/TestClient convention as ``test_source_route_adoption_api.py``
(route functions called directly with an explicit ``RequestContext`` for the great majority of this suite;
the stdlib-only raw-ASGI ``_asgi_call`` driver ONLY where a REAL HTTP status boundary matters — the 400-vs-
422 convention). Manual-route confirmation needs no readiness spine / observer backbone at all, so this
suite seeds only a plain ``complete_ready`` QA package (a plan + a source-confirmed span) — never
``bent_ready`` — and never imports the route-adoption geometry/hash machinery itself (only the API layer's
OWN lazy import of ``contracts.source_route_adoption``, for the ``reported_route_search`` taxonomy check,
touches that module, and only when a request clears every earlier gate).
"""
from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

from truelinev2.api import product_pipeline_routes as ppr
from truelinev2.api.app import create_app
from truelinev2.config import Settings
from truelinev2.context import require_context
from truelinev2.contracts.extracted_row import CONFIRMED, MANUAL_ENTRY
from truelinev2.contracts.reviewed_bore_log import GROUPING_CONFIRMED, SEPARATE_BORE
from truelinev2.harness.complete_package_qa import SCENARIOS, build_complete_package

_NOW_TENANT = "cp-manual"
_JOB = "job-1"


# --------------------------------------------------------------------------- #
# Harness (self-contained — a plain complete_ready package; NO readiness/observer-backbone machinery is
# exercised anywhere in this file, since manual-route confirmation needs none of it).
# --------------------------------------------------------------------------- #
def _settings(tmp_path: Path, *, pipeline=True, manual=True) -> Settings:
    import dataclasses

    return dataclasses.replace(
        Settings.for_proof(),
        artifact_root=tmp_path / "artifacts", cards_dir=tmp_path / "cards", db_path=tmp_path / "truelinev2.db",
        product_pipeline_api_optin=pipeline, source_anchor_manual_route_optin=manual,
        product_store_root=tmp_path / "product_store",
        product_billing_cost_rules_path=tmp_path / "cost_rules.json")


def _container(tmp_path: Path, **flags):
    return create_app(_settings(tmp_path, **flags)).state.tl2


def _app(tmp_path: Path, **flags):
    return create_app(_settings(tmp_path, **flags))


def _ctx(tenant: str = _NOW_TENANT, session: str = "sess-1"):
    return require_context(tenant, session)


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def _asgi_call(app, method: str, path: str, *, json_body=None, headers=None):
    """Minimal stdlib-only raw-ASGI request driver (mirrors test_source_route_adoption_api.py's
    ``_asgi_call``) — drives the REAL FastAPI/Starlette app end-to-end (routing, header-based context
    dependency injection, Pydantic request-body validation), needed to observe a genuine framework 422 (a
    direct Python function call can only raise ``ValidationError`` with no HTTP status attached)."""
    body = b"" if json_body is None else json.dumps(json_body).encode("utf-8")
    hdr_list = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode("ascii"))]
    for k, v in (headers or {}).items():
        hdr_list.append((k.lower().encode("latin-1"), str(v).encode("latin-1")))
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
    """Exact split-token equality (never startswith) — proves `code` is precisely the LEADING token of the
    detail string, mirroring test_source_route_adoption_api.py's own convention."""
    detail = exc.value.detail
    assert detail.split(":", 1)[0] == code, detail


def _scenario_bytes(tmp_path: Path, key: str = "complete_ready"):
    sc = next(s for s in SCENARIOS if s.key == key)
    pkg = build_complete_package(tmp_path / "qa_src", name="src-%s" % key, labels=sc.labels,
                                 route_shape=sc.route_shape, bore_csv=sc.bore_csv)
    up = Path(pkg) / "uploads"
    plan = (up / "plan.pdf").read_bytes()
    borelog = (up / "bore-log.csv").read_bytes()
    return plan, borelog


def _seed_job(tmp_path: Path, c, ctx, *, job_id: str = _JOB):
    """Project + job + a plain complete_ready plan/borelog + an engine-eligible reviewed_bore_log row. No
    readiness spine is ever run over this job in this file — manual-route confirmation needs none."""
    plan_bytes, borelog_bytes = _scenario_bytes(tmp_path)
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


def _cp(x, y):
    return ppr.ControlPoint(x=x, y=y)


# Two-point straight segment + a 4-point manual bend polyline, both within the 300x200 plan page's display-
# space bounds (build_plan_pdf's fixed page size).
_STRAIGHT_2PT = [_cp(70.0, 90.0), _cp(170.0, 110.0)]
_BENT_4PT = [_cp(70.0, 90.0), _cp(110.0, 70.0), _cp(140.0, 130.0), _cp(170.0, 110.0)]


def _manual(*, confirmed=True, representative_status, reported_route_search=None):
    return ppr.ManualRouteIn(confirmed=confirmed, representative_status=representative_status,
                            reported_route_search=reported_route_search)


def _reported(code, upstream_reason_code=None):
    return ppr.ReportedRouteSearchIn(code=code, upstream_reason_code=upstream_reason_code)


# --------------------------------------------------------------------------- #
# Settings + flag default.
# --------------------------------------------------------------------------- #
def test_settings_default_off_and_env(monkeypatch):
    """Locks: Settings.source_anchor_manual_route_optin default False; TL2_SOURCE_ANCHOR_MANUAL_ROUTE_OPTIN
    env-controlled."""
    monkeypatch.delenv("TL2_SOURCE_ANCHOR_MANUAL_ROUTE_OPTIN", raising=False)
    assert Settings.from_env().source_anchor_manual_route_optin is False
    monkeypatch.setenv("TL2_SOURCE_ANCHOR_MANUAL_ROUTE_OPTIN", "1")
    assert Settings.from_env().source_anchor_manual_route_optin is True


# --------------------------------------------------------------------------- #
# OFF-identity: a blockless request is byte-identical regardless of the flag.
# --------------------------------------------------------------------------- #
def _source_anchor_record_path(store_root, cp, job_id, source_anchor_id):
    from truelinev2.contracts.processing_job import job_dir
    from truelinev2.contracts.source_anchor import SOURCE_ANCHOR_FILENAME, SOURCE_ANCHORS_SUBDIR

    return (job_dir(store_root, cp, job_id) / SOURCE_ANCHORS_SUBDIR / source_anchor_id
            / SOURCE_ANCHOR_FILENAME)


def test_blockless_create_is_byte_identical_flag_off_vs_on(tmp_path, monkeypatch):
    """Locks: a request that carries NO manual_route block produces byte-identical stored-record-file bytes
    AND response-body bytes whether the flag is OFF or ON — the flag only unlocks the OPTIONAL block, never
    changes blockless behavior (the design's own binding requirement)."""
    monkeypatch.setattr(ppr, "_now", lambda: "2026-01-01T00:00:00+00:00")
    plan_bytes, borelog_bytes = _scenario_bytes(tmp_path)
    headers = {"X-TL-Tenant": _NOW_TENANT, "X-TL-Session": "sess-1"}
    app_off = _app(tmp_path / "off", manual=False)
    app_on = _app(tmp_path / "on", manual=True)
    ctx = _ctx()

    def _seed(app):
        c = app.state.tl2
        ppr.create_project(ppr.ProjectCreate(display_name="Label"), ctx=ctx, c=c)
        ppr.create_processing_job(ppr.JobCreate(job_id=_JOB), ctx=ctx, c=c)
        plan_id = ppr.register_upload(
            _JOB, ppr.UploadRegister(kind="PLAN_PDF", filename="plan.pdf", content_base64=_b64(plan_bytes)),
            ctx=ctx, c=c)["upload_id"]
        bore_id = ppr.register_upload(
            _JOB, ppr.UploadRegister(kind="BORE_LOG", filename="bore-log.csv",
                                     content_base64=_b64(borelog_bytes)), ctx=ctx, c=c)["upload_id"]
        ppr.create_bore_log_review(
            _JOB, ppr.ReviewedBoreLogCreate(reviewed_bore_log_id="rbl-main", source_upload_id=bore_id),
            ctx=ctx, c=c)
        return plan_id

    plan_off = _seed(app_off)
    plan_on = _seed(app_on)
    assert plan_off == plan_on                      # sanity: deterministic content ids

    body = {
        "source_anchor_id": "sa-1", "plan_upload_id": plan_off, "reviewed_bore_log_id": "rbl-main",
        "page_number": 1, "control_points": [{"x": 70.0, "y": 90.0}, {"x": 170.0, "y": 110.0}],
    }
    status_off, resp_off, parsed_off = _asgi_call(
        app_off, "POST", "/v2/product/jobs/%s/source-anchors" % _JOB, json_body=body, headers=headers)
    status_on, resp_on, parsed_on = _asgi_call(
        app_on, "POST", "/v2/product/jobs/%s/source-anchors" % _JOB, json_body=body, headers=headers)
    assert status_off == status_on == 200
    assert parsed_off["record_format"] == parsed_on["record_format"] == "trueline-source-anchor-1"
    assert resp_off == resp_on                                     # raw HTTP response body bytes

    path_off = _source_anchor_record_path(app_off.state.tl2.settings.product_store_root, _NOW_TENANT, _JOB, "sa-1")
    path_on = _source_anchor_record_path(app_on.state.tl2.settings.product_store_root, _NOW_TENANT, _JOB, "sa-1")
    assert path_off.read_bytes() == path_on.read_bytes()           # raw stored record file bytes


def test_two_point_manual_create_without_block_stays_byte_identical_flag_on(tmp_path):
    """Locks (design test-surface (f)): a 2-point create WITHOUT the manual_route block is a legacy v1
    record even with the flag ON — the flag only unlocks the OPTIONAL block."""
    c, ctx = _container(tmp_path, manual=True), _ctx()
    plan_upload_id, rbl_id, row_id = _seed_job(tmp_path, c, ctx)
    rec = ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
        source_anchor_id="sa-1", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
        page_number=1, control_points=_STRAIGHT_2PT, row_ids=[row_id]), ctx=ctx, c=c)
    assert rec["record_format"] == "trueline-source-anchor-1"
    assert "geometry_basis" not in rec and "manual_route" not in rec and "route_adoption" not in rec


# --------------------------------------------------------------------------- #
# Flag OFF + block present -> 400 MANUAL_ROUTE_NOT_ENABLED.
# --------------------------------------------------------------------------- #
def test_manual_route_block_present_flag_off_is_400(tmp_path):
    c, ctx = _container(tmp_path, manual=False), _ctx()
    plan_upload_id, rbl_id, row_id = _seed_job(tmp_path, c, ctx)
    with pytest.raises(HTTPException) as exc:
        ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
            source_anchor_id="sa-1", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
            page_number=1, control_points=_STRAIGHT_2PT, row_ids=[row_id],
            manual_route=_manual(representative_status="REPRESENTATIVE_STRAIGHT_ACCEPTED")), ctx=ctx, c=c)
    assert exc.value.status_code == 400
    _assert_detail_code(exc, "MANUAL_ROUTE_NOT_ENABLED")


# --------------------------------------------------------------------------- #
# Flag ON — happy paths.
# --------------------------------------------------------------------------- #
def test_two_point_representative_confirm_creates_v2_record(tmp_path):
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id = _seed_job(tmp_path, c, ctx)
    rec = ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
        source_anchor_id="sa-1", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
        page_number=1, control_points=_STRAIGHT_2PT, row_ids=[row_id],
        manual_route=_manual(representative_status="REPRESENTATIVE_STRAIGHT_ACCEPTED")), ctx=ctx, c=c)

    assert rec["record_format"] == "trueline-source-anchor-2"
    assert rec["geometry_basis"] == "HUMAN_CLICKED_POLYLINE"
    assert rec["confirmation_state"] == "HUMAN_REVIEWED"
    assert rec["provenance"] == "HUMAN_CONFIRMED_CONTROL_POINTS"
    assert rec["status"] == "VALIDATED" and rec["renderable"] is True
    mr = rec["manual_route"]
    assert mr["representative_status"] == "REPRESENTATIVE_STRAIGHT_ACCEPTED"
    assert mr["human_control_points"] == {
        "start": {"x": 70.0, "y": 90.0}, "end": {"x": 170.0, "y": 110.0}, "intermediate": []}
    assert mr["intermediate_point_count"] == 0
    assert mr["reported_route_search"] is None
    assert mr["confirmed_by"] == "sess-1"
    assert mr["confirmed_at"]
    assert "route_adoption" not in rec
    actions = [e["action"] for e in rec["audit"]]
    assert actions == ["source_anchor_created", "manual_route_confirmed"]


def test_four_point_manual_polyline_confirm_creates_v2_record(tmp_path):
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id = _seed_job(tmp_path, c, ctx)
    rec = ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
        source_anchor_id="sa-1", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
        page_number=1, control_points=_BENT_4PT, row_ids=[row_id],
        manual_route=_manual(representative_status="MANUAL_POLYLINE_CONFIRMED")), ctx=ctx, c=c)

    assert rec["record_format"] == "trueline-source-anchor-2"
    assert rec["control_points"] == [
        {"x": 70.0, "y": 90.0}, {"x": 110.0, "y": 70.0}, {"x": 140.0, "y": 130.0}, {"x": 170.0, "y": 110.0}]
    mr = rec["manual_route"]
    assert mr["representative_status"] == "MANUAL_POLYLINE_CONFIRMED"
    assert mr["human_control_points"] == {
        "start": {"x": 70.0, "y": 90.0}, "end": {"x": 170.0, "y": 110.0},
        "intermediate": [{"x": 110.0, "y": 70.0}, {"x": 140.0, "y": 130.0}]}
    assert mr["intermediate_point_count"] == 2


def test_manual_row_ids_allow_zero_and_many_unlike_adoption(tmp_path):
    """Ground truth: 'Manual creates allow row_ids 0..many (adoption's exactly-1 rule is adoption-only)' —
    a manual confirm with ZERO row_ids succeeds (unlike route_adoption, which requires exactly one)."""
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, _row_id = _seed_job(tmp_path, c, ctx)
    rec = ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
        source_anchor_id="sa-1", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
        page_number=1, control_points=_STRAIGHT_2PT,                    # row_ids OMITTED entirely
        manual_route=_manual(representative_status="REPRESENTATIVE_STRAIGHT_ACCEPTED")), ctx=ctx, c=c)
    assert rec["row_ids"] == []
    assert rec["status"] == "VALIDATED"


# --------------------------------------------------------------------------- #
# Validation: confirmed literal, count<->status, zero-length.
# --------------------------------------------------------------------------- #
def test_confirmed_false_is_400_manual_route_invalid(tmp_path):
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id = _seed_job(tmp_path, c, ctx)
    with pytest.raises(HTTPException) as exc:
        ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
            source_anchor_id="sa-1", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
            page_number=1, control_points=_STRAIGHT_2PT, row_ids=[row_id],
            manual_route=_manual(confirmed=False, representative_status="REPRESENTATIVE_STRAIGHT_ACCEPTED")),
            ctx=ctx, c=c)
    assert exc.value.status_code == 400
    _assert_detail_code(exc, "MANUAL_ROUTE_INVALID")


def test_confirmed_missing_is_422_via_real_endpoint(tmp_path):
    """A well-typed body whose manual_route object is MISSING the required `confirmed` field never reaches
    product validation — FastAPI's own Pydantic request-body validation refuses it FIRST as a
    framework-standard 422 (mirrors the adoption suite's own missing-echo-field 422 proof)."""
    app = _app(tmp_path)
    c, ctx = app.state.tl2, _ctx()
    plan_upload_id, rbl_id, row_id = _seed_job(tmp_path, c, ctx)
    body = {
        "source_anchor_id": "sa-1", "plan_upload_id": plan_upload_id, "reviewed_bore_log_id": rbl_id,
        "page_number": 1, "control_points": [{"x": 70.0, "y": 90.0}, {"x": 170.0, "y": 110.0}],
        "row_ids": [row_id],
        "manual_route": {"representative_status": "REPRESENTATIVE_STRAIGHT_ACCEPTED"},   # confirmed OMITTED
    }
    status, _raw, parsed = _asgi_call(
        app, "POST", "/v2/product/jobs/%s/source-anchors" % _JOB, json_body=body,
        headers={"X-TL-Tenant": _NOW_TENANT, "X-TL-Session": "sess-1"})
    assert status == 422, (status, parsed)


def test_two_points_with_manual_polyline_confirmed_status_is_mismatch(tmp_path):
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id = _seed_job(tmp_path, c, ctx)
    with pytest.raises(HTTPException) as exc:
        ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
            source_anchor_id="sa-1", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
            page_number=1, control_points=_STRAIGHT_2PT, row_ids=[row_id],
            manual_route=_manual(representative_status="MANUAL_POLYLINE_CONFIRMED")), ctx=ctx, c=c)
    assert exc.value.status_code == 400
    _assert_detail_code(exc, "MANUAL_ROUTE_STATUS_MISMATCH")


def test_four_points_with_representative_straight_status_is_mismatch(tmp_path):
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id = _seed_job(tmp_path, c, ctx)
    with pytest.raises(HTTPException) as exc:
        ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
            source_anchor_id="sa-1", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
            page_number=1, control_points=_BENT_4PT, row_ids=[row_id],
            manual_route=_manual(representative_status="REPRESENTATIVE_STRAIGHT_ACCEPTED")), ctx=ctx, c=c)
    assert exc.value.status_code == 400
    _assert_detail_code(exc, "MANUAL_ROUTE_STATUS_MISMATCH")


def test_zero_length_two_point_polyline_is_400_invalid(tmp_path):
    """Sol amendment: reject a zero-TOTAL-length polyline when the manual block is present (identical points
    would otherwise "confirm" a route that is really a single point)."""
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id = _seed_job(tmp_path, c, ctx)
    with pytest.raises(HTTPException) as exc:
        ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
            source_anchor_id="sa-1", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
            page_number=1, control_points=[_cp(100.0, 100.0), _cp(100.0, 100.0)], row_ids=[row_id],
            manual_route=_manual(representative_status="REPRESENTATIVE_STRAIGHT_ACCEPTED")), ctx=ctx, c=c)
    assert exc.value.status_code == 400
    _assert_detail_code(exc, "MANUAL_ROUTE_INVALID")


def test_zero_length_multi_point_all_identical_is_400_invalid(tmp_path):
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id = _seed_job(tmp_path, c, ctx)
    identical = [_cp(100.0, 100.0)] * 3
    with pytest.raises(HTTPException) as exc:
        ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
            source_anchor_id="sa-1", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
            page_number=1, control_points=identical, row_ids=[row_id],
            manual_route=_manual(representative_status="MANUAL_POLYLINE_CONFIRMED")), ctx=ctx, c=c)
    assert exc.value.status_code == 400
    _assert_detail_code(exc, "MANUAL_ROUTE_INVALID")


# --------------------------------------------------------------------------- #
# reported_route_search taxonomy (Sol Q1 VOCABULARY — the 21-code set; lazy import).
# --------------------------------------------------------------------------- #
def test_reported_code_accepted_geometry_refusal(tmp_path):
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id = _seed_job(tmp_path, c, ctx)
    rec = ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
        source_anchor_id="sa-1", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
        page_number=1, control_points=_STRAIGHT_2PT, row_ids=[row_id],
        manual_route=_manual(representative_status="REPRESENTATIVE_STRAIGHT_ACCEPTED",
                             reported_route_search=_reported("BACKBONE_EMPTY"))), ctx=ctx, c=c)
    assert rec["manual_route"]["reported_route_search"] == {"code": "BACKBONE_EMPTY", "upstream_reason_code": None}


def test_reported_code_route_evidence_not_ready_requires_upstream_reason_code(tmp_path):
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id = _seed_job(tmp_path, c, ctx)
    rec = ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
        source_anchor_id="sa-1", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
        page_number=1, control_points=_STRAIGHT_2PT, row_ids=[row_id],
        manual_route=_manual(
            representative_status="REPRESENTATIVE_STRAIGHT_ACCEPTED",
            reported_route_search=_reported("ROUTE_EVIDENCE_NOT_READY", "NO_SOURCE_CONFIRMED_SPAN"))),
        ctx=ctx, c=c)
    assert rec["manual_route"]["reported_route_search"] == {
        "code": "ROUTE_EVIDENCE_NOT_READY", "upstream_reason_code": "NO_SOURCE_CONFIRMED_SPAN"}


def test_reported_code_route_evidence_not_ready_missing_upstream_is_400(tmp_path):
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id = _seed_job(tmp_path, c, ctx)
    with pytest.raises(HTTPException) as exc:
        ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
            source_anchor_id="sa-1", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
            page_number=1, control_points=_STRAIGHT_2PT, row_ids=[row_id],
            manual_route=_manual(representative_status="REPRESENTATIVE_STRAIGHT_ACCEPTED",
                                 reported_route_search=_reported("ROUTE_EVIDENCE_NOT_READY", None))),
            ctx=ctx, c=c)
    assert exc.value.status_code == 400
    _assert_detail_code(exc, "MANUAL_ROUTE_INVALID")


def test_reported_code_route_evidence_not_ready_bad_upstream_shape_is_400(tmp_path):
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id = _seed_job(tmp_path, c, ctx)
    with pytest.raises(HTTPException) as exc:
        ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
            source_anchor_id="sa-1", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
            page_number=1, control_points=_STRAIGHT_2PT, row_ids=[row_id],
            manual_route=_manual(
                representative_status="REPRESENTATIVE_STRAIGHT_ACCEPTED",
                reported_route_search=_reported("ROUTE_EVIDENCE_NOT_READY", "no source confirmed span"))),
            ctx=ctx, c=c)
    assert exc.value.status_code == 400
    _assert_detail_code(exc, "MANUAL_ROUTE_INVALID")


def test_reported_code_upstream_reason_code_trailing_newline_is_400_f2_b2(tmp_path):
    """Fix-wave B2 (Sol xhigh verification): Python's ``$`` anchor matches immediately before a trailing
    ``\\n``, so a naive ``.match()`` against ``^[A-Z][A-Z0-9_]{0,63}$`` would let
    ``"NO_SOURCE_CONFIRMED_SPAN\\n"`` through. The validator now uses ``.fullmatch()`` -- must 400."""
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id = _seed_job(tmp_path, c, ctx)
    with pytest.raises(HTTPException) as exc:
        ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
            source_anchor_id="sa-1", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
            page_number=1, control_points=_STRAIGHT_2PT, row_ids=[row_id],
            manual_route=_manual(
                representative_status="REPRESENTATIVE_STRAIGHT_ACCEPTED",
                reported_route_search=_reported("ROUTE_EVIDENCE_NOT_READY",
                                                "NO_SOURCE_CONFIRMED_SPAN\n"))),
            ctx=ctx, c=c)
    assert exc.value.status_code == 400
    _assert_detail_code(exc, "MANUAL_ROUTE_INVALID")


def test_reported_code_upstream_reason_code_embedded_newline_is_400_f2_b2(tmp_path):
    """Fix-wave B2: an embedded newline must not let ``^...$`` re-anchor on a false "whole line" -- 400."""
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id = _seed_job(tmp_path, c, ctx)
    with pytest.raises(HTTPException) as exc:
        ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
            source_anchor_id="sa-1", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
            page_number=1, control_points=_STRAIGHT_2PT, row_ids=[row_id],
            manual_route=_manual(
                representative_status="REPRESENTATIVE_STRAIGHT_ACCEPTED",
                reported_route_search=_reported("ROUTE_EVIDENCE_NOT_READY",
                                                "NO_SOURCE\nCONFIRMED_SPAN"))),
            ctx=ctx, c=c)
    assert exc.value.status_code == 400
    _assert_detail_code(exc, "MANUAL_ROUTE_INVALID")


def test_reported_code_upstream_reason_code_exactly_64_chars_accepted_f2_b2(tmp_path):
    """Fix-wave B2: the boundary itself -- ``^[A-Z][A-Z0-9_]{0,63}$`` allows 1 + 63 = 64 chars total."""
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id = _seed_job(tmp_path, c, ctx)
    code64 = "A" + "B" * 63
    assert len(code64) == 64
    rec = ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
        source_anchor_id="sa-1", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
        page_number=1, control_points=_STRAIGHT_2PT, row_ids=[row_id],
        manual_route=_manual(representative_status="REPRESENTATIVE_STRAIGHT_ACCEPTED",
                             reported_route_search=_reported("ROUTE_EVIDENCE_NOT_READY", code64))),
        ctx=ctx, c=c)
    assert rec["manual_route"]["reported_route_search"] == {
        "code": "ROUTE_EVIDENCE_NOT_READY", "upstream_reason_code": code64}


def test_reported_code_upstream_reason_code_65_chars_is_400_f2_b2(tmp_path):
    """Fix-wave B2: one char past the boundary -- 65 chars total -- must 400."""
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id = _seed_job(tmp_path, c, ctx)
    code65 = "A" + "B" * 64
    assert len(code65) == 65
    with pytest.raises(HTTPException) as exc:
        ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
            source_anchor_id="sa-1", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
            page_number=1, control_points=_STRAIGHT_2PT, row_ids=[row_id],
            manual_route=_manual(representative_status="REPRESENTATIVE_STRAIGHT_ACCEPTED",
                                 reported_route_search=_reported("ROUTE_EVIDENCE_NOT_READY", code65))),
            ctx=ctx, c=c)
    assert exc.value.status_code == 400
    _assert_detail_code(exc, "MANUAL_ROUTE_INVALID")


def test_reported_code_non_not_ready_with_upstream_reason_code_is_400(tmp_path):
    """Cross-field rule, other direction: ANY code other than ROUTE_EVIDENCE_NOT_READY must carry a null/
    absent upstream_reason_code."""
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id = _seed_job(tmp_path, c, ctx)
    with pytest.raises(HTTPException) as exc:
        ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
            source_anchor_id="sa-1", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
            page_number=1, control_points=_STRAIGHT_2PT, row_ids=[row_id],
            manual_route=_manual(representative_status="REPRESENTATIVE_STRAIGHT_ACCEPTED",
                                 reported_route_search=_reported("BACKBONE_EMPTY", "SOME_UPSTREAM"))),
            ctx=ctx, c=c)
    assert exc.value.status_code == 400
    _assert_detail_code(exc, "MANUAL_ROUTE_INVALID")


def test_reported_code_unknown_is_400(tmp_path):
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id = _seed_job(tmp_path, c, ctx)
    with pytest.raises(HTTPException) as exc:
        ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
            source_anchor_id="sa-1", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
            page_number=1, control_points=_STRAIGHT_2PT, row_ids=[row_id],
            manual_route=_manual(representative_status="REPRESENTATIVE_STRAIGHT_ACCEPTED",
                                 reported_route_search=_reported("NOT_A_REAL_CODE"))), ctx=ctx, c=c)
    assert exc.value.status_code == 400
    _assert_detail_code(exc, "MANUAL_ROUTE_INVALID")


def test_reported_code_malformed_control_points_is_rejected(tmp_path):
    """`MALFORMED_CONTROL_POINTS` is a REAL refusal code the derivation module defines, but the proposal
    endpoint 400s before it can ever be RETURNED as a refusal payload (Sol Q1) — it must be rejected here
    exactly like an unknown code."""
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id = _seed_job(tmp_path, c, ctx)
    with pytest.raises(HTTPException) as exc:
        ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
            source_anchor_id="sa-1", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
            page_number=1, control_points=_STRAIGHT_2PT, row_ids=[row_id],
            manual_route=_manual(representative_status="REPRESENTATIVE_STRAIGHT_ACCEPTED",
                                 reported_route_search=_reported("MALFORMED_CONTROL_POINTS"))), ctx=ctx, c=c)
    assert exc.value.status_code == 400
    _assert_detail_code(exc, "MANUAL_ROUTE_INVALID")


def test_reported_code_route_adoption_invalid_is_rejected():
    """`ROUTE_ADOPTION_INVALID` is a create-time adoption exception code, never a member of the proposal
    endpoint's own refusal vocabulary — must be rejected exactly like any other unrecognized code."""
    from truelinev2.contracts.source_route_adoption import ALL_REFUSAL_CODES

    assert "ROUTE_ADOPTION_INVALID" not in ALL_REFUSAL_CODES


def test_reported_code_route_adoption_invalid_creates_is_400(tmp_path):
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id = _seed_job(tmp_path, c, ctx)
    with pytest.raises(HTTPException) as exc:
        ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
            source_anchor_id="sa-1", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
            page_number=1, control_points=_STRAIGHT_2PT, row_ids=[row_id],
            manual_route=_manual(representative_status="REPRESENTATIVE_STRAIGHT_ACCEPTED",
                                 reported_route_search=_reported("ROUTE_ADOPTION_INVALID"))), ctx=ctx, c=c)
    assert exc.value.status_code == 400
    _assert_detail_code(exc, "MANUAL_ROUTE_INVALID")


def test_flag_off_never_imports_the_route_adoption_module(tmp_path):
    """Mirrors test_source_route_adoption_api.py's own subprocess isolation proof: with the manual-route
    flag OFF, `contracts.source_route_adoption` must NEVER be imported — not even when the request also
    carries a manual_route block with a reported_route_search (the flag-off 400 fires before ANY manual-
    route validation runs). Run in a FRESH subprocess (every other test module in this suite imports that
    module at collection time, which would already contaminate sys.modules in-process)."""
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
        "db_path=tmp/'d.db', product_pipeline_api_optin=True, "
        "source_anchor_manual_route_optin=False, product_store_root=tmp/'store', "
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
# Mutual exclusion: manual_route + route_adoption both present.
# --------------------------------------------------------------------------- #
def test_manual_route_and_route_adoption_both_present_is_400_conflict(tmp_path):
    c, ctx = _container(tmp_path, manual=True), _ctx()
    plan_upload_id, rbl_id, row_id = _seed_job(tmp_path, c, ctx)
    with pytest.raises(HTTPException) as exc:
        ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
            source_anchor_id="sa-1", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
            page_number=1, control_points=_STRAIGHT_2PT, row_ids=[row_id],
            manual_route=_manual(representative_status="REPRESENTATIVE_STRAIGHT_ACCEPTED"),
            route_adoption=ppr.RouteAdoptionIn(
                proposal_hash="sha256:" + "a" * 64, confirmed=True,
                plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id, row_id=row_id, page_number=1,
                control_points=_STRAIGHT_2PT)),
            ctx=ctx, c=c)
    assert exc.value.status_code == 400
    _assert_detail_code(exc, "MANUAL_ROUTE_PROVENANCE_CONFLICT")


def test_manual_route_and_route_adoption_conflict_fires_even_with_both_flags_off(tmp_path):
    """The conflict check is validated BEFORE either provenance branch — it fires even when NEITHER flag is
    enabled (a request this malformed is refused on shape, not on feature availability)."""
    c, ctx = _container(tmp_path, manual=False), _ctx()
    plan_upload_id, rbl_id, row_id = _seed_job(tmp_path, c, ctx)
    with pytest.raises(HTTPException) as exc:
        ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
            source_anchor_id="sa-1", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
            page_number=1, control_points=_STRAIGHT_2PT, row_ids=[row_id],
            manual_route=_manual(representative_status="REPRESENTATIVE_STRAIGHT_ACCEPTED"),
            route_adoption=ppr.RouteAdoptionIn(
                proposal_hash="sha256:" + "a" * 64, confirmed=True,
                plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id, row_id=row_id, page_number=1,
                control_points=_STRAIGHT_2PT)),
            ctx=ctx, c=c)
    assert exc.value.status_code == 400
    _assert_detail_code(exc, "MANUAL_ROUTE_PROVENANCE_CONFLICT")


# --------------------------------------------------------------------------- #
# Manifest emission: split by ACTUAL provenance block.
# --------------------------------------------------------------------------- #
def _bundle_manifest(c, cp, job_id, bundle_id):
    from truelinev2.contracts.processing_job import job_dir
    path = job_dir(c.settings.product_store_root, cp, job_id) / "bundle_store" / "bundles" / bundle_id \
        / "redline_manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_manifest_carries_manual_route_block_and_never_route_adoption(tmp_path):
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id = _seed_job(tmp_path, c, ctx)
    ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
        source_anchor_id="sa-manual", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
        page_number=1, control_points=_BENT_4PT, row_ids=[row_id],
        manual_route=_manual(representative_status="MANUAL_POLYLINE_CONFIRMED",
                             reported_route_search=_reported("BACKBONE_EMPTY"))), ctx=ctx, c=c)
    summary = ppr.render_source_anchor_route(_JOB, "sa-manual", ctx=ctx, c=c)
    manifest = _bundle_manifest(c, _NOW_TENANT, _JOB, summary["bundle_id"])
    log = next(lg for lg in manifest["logs"] if lg["log_id"] == "sa-manual")

    assert log["geometry_basis"] == "HUMAN_CLICKED_POLYLINE"
    assert log["confirmation_state"] == "HUMAN_REVIEWED"
    assert log["render_control_points"] == [
        {"x": 70.0, "y": 90.0}, {"x": 110.0, "y": 70.0}, {"x": 140.0, "y": 130.0}, {"x": 170.0, "y": 110.0}]
    assert log["manual_route"]["representative_status"] == "MANUAL_POLYLINE_CONFIRMED"
    assert log["manual_route"]["reported_route_search"] == {"code": "BACKBONE_EMPTY", "upstream_reason_code": None}
    assert "route_adoption" not in log
    # unchanged manifest truth: status/provenance/frontier stay the EXISTING enums.
    assert log["status"] == "DRAWN_REDLINE" and log["provenance"] == "OWNER_CONFIRMED_HUMAN_ADJUSTABLE"

    from truelinev2.contracts.redline_manifest_publisher import load_schema, validate_manifest
    assert validate_manifest(manifest, load_schema()) == []


def test_manifest_v1_and_adoption_never_gain_manual_route_key(tmp_path):
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id = _seed_job(tmp_path, c, ctx)
    ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
        source_anchor_id="sa-v1", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
        page_number=1, control_points=_STRAIGHT_2PT, row_ids=[row_id]), ctx=ctx, c=c)
    summary = ppr.render_source_anchor_route(_JOB, "sa-v1", ctx=ctx, c=c)
    manifest = _bundle_manifest(c, _NOW_TENANT, _JOB, summary["bundle_id"])
    log = next(lg for lg in manifest["logs"] if lg["log_id"] == "sa-v1")
    for key in ("geometry_basis", "confirmation_state", "render_control_points", "route_adoption",
               "manual_route"):
        assert key not in log, key


# --------------------------------------------------------------------------- #
# Publisher semantic checks (Sol change: both-blocks => error; basis/block mismatch => error).
# --------------------------------------------------------------------------- #
def _minimal_manifest(log_overrides: dict) -> dict:
    """A minimal, otherwise schema-valid manifest with ONE log, for exercising
    `redline_manifest_publisher.reconciliation_errors` directly (unit-level, no render/store involved)."""
    log = {
        "log_id": "sa-x", "parent_id": "rbl-main", "entry_role": "standalone",
        "status": "DRAWN_REDLINE", "provenance": "OWNER_CONFIRMED_HUMAN_ADJUSTABLE",
        "drawn": True, "covered": False, "blocked": False, "drawn_lane": "NEW_TARGETS",
        "source_sheets": [1], "span": {"start_station": "", "end_station": "", "label": "x"},
        "closure": None, "coverage": None, "blocker": None, "artifacts": [], "evidence": [], "warnings": [],
    }
    log.update(log_overrides)
    return {
        "schema_version": "1.0.0", "mock_example": False, "disclaimer": "x",
        "project_id": "p", "project_name": "P",
        "engine": {"branch": "x", "engine_head": "x", "render_commit": "x", "generated_from": "x"},
        "summary": {"total_logs": 1, "drawn_count": 1, "covered_count": 0, "blocked_count": 0,
                   "frontier": "1/1"},
        "status_counts": {"DRAWN_REDLINE": 1, "COVERED_BY_EXISTING_REDLINE": 0, "OWNER_LOCKED_ABSTAIN": 0,
                          "SOURCE_GAP_BLOCKED": 0, "MISSING_SOURCE_SHEET_BLOCKED": 0},
        "provenance_counts": {"DETERMINISTIC_AUTO": 0, "OWNER_CONFIRMED_HUMAN_ADJUSTABLE": 1,
                              "COVERED_BY_EXISTING_REDLINE": 0, "BLOCKED_OWNER_LOCKED": 0,
                              "BLOCKED_SOURCE_GAP": 0, "BLOCKED_MISSING_SOURCE": 0},
        "consumption_rules": ["x"], "logs": [log],
    }


def test_publisher_rejects_both_provenance_blocks_on_one_log():
    from truelinev2.contracts.redline_manifest_publisher import reconciliation_errors

    manifest = _minimal_manifest({
        "geometry_basis": "OBSERVER_BACKBONE_HUMAN_ADOPTED",
        "route_adoption": {"geometry_source": "x"},
        "manual_route": {"representative_status": "MANUAL_POLYLINE_CONFIRMED"},
    })
    errors = reconciliation_errors(manifest)
    assert any("mutually exclusive" in e for e in errors), errors


def test_publisher_rejects_adoption_basis_mismatch():
    from truelinev2.contracts.redline_manifest_publisher import reconciliation_errors

    manifest = _minimal_manifest({
        "geometry_basis": "HUMAN_CLICKED_POLYLINE",       # WRONG basis for a route_adoption block
        "route_adoption": {"geometry_source": "x"},
    })
    errors = reconciliation_errors(manifest)
    assert any("route_adoption but geometry_basis" in e for e in errors), errors


def test_publisher_rejects_manual_basis_mismatch():
    from truelinev2.contracts.redline_manifest_publisher import reconciliation_errors

    manifest = _minimal_manifest({
        "geometry_basis": "OBSERVER_BACKBONE_HUMAN_ADOPTED",   # WRONG basis for a manual_route block
        "manual_route": {"representative_status": "MANUAL_POLYLINE_CONFIRMED"},
    })
    errors = reconciliation_errors(manifest)
    assert any("manual_route but geometry_basis" in e for e in errors), errors


def test_publisher_rejects_basis_present_without_matching_block():
    from truelinev2.contracts.redline_manifest_publisher import reconciliation_errors

    manifest = _minimal_manifest({"geometry_basis": "HUMAN_CLICKED_POLYLINE"})    # basis but no block at all
    errors = reconciliation_errors(manifest)
    assert any("no manual_route block" in e for e in errors), errors


def test_publisher_accepts_a_clean_manual_log():
    from truelinev2.contracts.redline_manifest_publisher import reconciliation_errors

    manifest = _minimal_manifest({
        "geometry_basis": "HUMAN_CLICKED_POLYLINE",
        "manual_route": {"representative_status": "MANUAL_POLYLINE_CONFIRMED"},
    })
    assert reconciliation_errors(manifest) == []


# --------------------------------------------------------------------------- #
# Closeout wording — discriminated by ACTUAL provenance block.
# --------------------------------------------------------------------------- #
def _pdf_text(data: bytes) -> str:
    import fitz

    doc = fitz.open(stream=data, filetype="pdf")
    try:
        return "".join(page.get_text() for page in doc)
    finally:
        doc.close()


def test_closeout_wording_manual_polyline_confirmed(tmp_path):
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id = _seed_job(tmp_path, c, ctx)
    ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
        source_anchor_id="sa-manual", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
        page_number=1, control_points=_BENT_4PT, row_ids=[row_id],
        manual_route=_manual(representative_status="MANUAL_POLYLINE_CONFIRMED",
                             reported_route_search=_reported("ROUTE_EVIDENCE_NOT_READY",
                                                            "NO_SOURCE_CONFIRMED_SPAN"))), ctx=ctx, c=c)
    ppr.render_source_anchor_route(_JOB, "sa-manual", ctx=ctx, c=c)
    pdf = ppr.download_closeout_pdf(_JOB, ctx=ctx, c=c)
    text = _pdf_text(pdf.body)
    assert "manual polyline confirmed by reviewer" in text
    assert "sess-1" in text
    assert "reported route-search refusal: ROUTE_EVIDENCE_NOT_READY" in text
    assert "upstream NO_SOURCE_CONFIRMED_SPAN" in text
    assert "source-backed observer backbone" not in text     # adoption-only wording never leaks here


def test_closeout_wording_representative_straight_accepted_no_reported_search(tmp_path):
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id = _seed_job(tmp_path, c, ctx)
    ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
        source_anchor_id="sa-rep", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
        page_number=1, control_points=_STRAIGHT_2PT, row_ids=[row_id],
        manual_route=_manual(representative_status="REPRESENTATIVE_STRAIGHT_ACCEPTED")), ctx=ctx, c=c)
    ppr.render_source_anchor_route(_JOB, "sa-rep", ctx=ctx, c=c)
    pdf = ppr.download_closeout_pdf(_JOB, ctx=ctx, c=c)
    text = _pdf_text(pdf.body)
    assert "representative straight segment accepted by reviewer" in text
    assert "reported route-search refusal" not in text        # no reported_route_search on this record


def test_closeout_wording_adoption_and_v1_unaffected(tmp_path):
    """v1 (blockless) closeout output carries NEITHER adoption nor manual wording."""
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id = _seed_job(tmp_path, c, ctx)
    ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
        source_anchor_id="sa-v1", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
        page_number=1, control_points=_STRAIGHT_2PT, row_ids=[row_id]), ctx=ctx, c=c)
    ppr.render_source_anchor_route(_JOB, "sa-v1", ctx=ctx, c=c)
    pdf = ppr.download_closeout_pdf(_JOB, ctx=ctx, c=c)
    text = _pdf_text(pdf.body)
    assert "source-backed observer backbone" not in text
    assert "manual polyline confirmed" not in text
    assert "representative straight segment accepted" not in text


# --------------------------------------------------------------------------- #
# ZIP export README — honest wording ONLY for a manifest carrying manual_route.
# --------------------------------------------------------------------------- #
def _zip_readme(zip_bytes: bytes) -> str:
    import io
    import zipfile

    zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    return zf.read("README.txt").decode("utf-8")


def test_export_readme_honest_wording_for_manual_route(tmp_path):
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id = _seed_job(tmp_path, c, ctx)
    ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
        source_anchor_id="sa-manual", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
        page_number=1, control_points=_BENT_4PT, row_ids=[row_id],
        manual_route=_manual(representative_status="MANUAL_POLYLINE_CONFIRMED")), ctx=ctx, c=c)
    ppr.render_source_anchor_route(_JOB, "sa-manual", ctx=ctx, c=c)
    zip_resp = ppr.download_export_package(_JOB, ctx=ctx, c=c)
    readme = _zip_readme(zip_resp.body)
    assert "reviewer's OWN confirmed control points" in readme
    assert "Redline geometry is the engine's, rendered from the plan's own drawn vectors" not in readme


def test_export_readme_v1_manual_unchanged_from_baseline(tmp_path):
    """A v1 (blockless) manual anchor's export README is UNCHANGED (byte-identical wording) — the honest
    human-confirmed sentence is emitted ONLY for a manifest that actually carries a manual_route block."""
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id = _seed_job(tmp_path, c, ctx)
    ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
        source_anchor_id="sa-v1", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
        page_number=1, control_points=_STRAIGHT_2PT, row_ids=[row_id]), ctx=ctx, c=c)
    ppr.render_source_anchor_route(_JOB, "sa-v1", ctx=ctx, c=c)
    zip_resp = ppr.download_export_package(_JOB, ctx=ctx, c=c)
    readme = _zip_readme(zip_resp.body)
    assert "Redline geometry is the engine's, rendered from the plan's own drawn vectors — never invented." in readme
    assert "reviewer's OWN confirmed control points" not in readme


# --------------------------------------------------------------------------- #
# Station dots ride the manual N-point polyline (same rigor as the adoption suite's own lock).
# --------------------------------------------------------------------------- #
def _local_cumulative_arclen(pts):
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


def _point_to_segment_distance(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    seg_len2 = dx * dx + dy * dy
    t = 0.0 if seg_len2 <= 0.0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg_len2))
    fx, fy = ax + t * dx, ay + t * dy
    import math as _math
    return _math.hypot(px - fx, py - fy)


def test_dots_ride_the_manual_four_point_polyline(tmp_path):
    c, ctx = _container(tmp_path), _ctx()
    plan_upload_id, rbl_id, row_id = _seed_job(tmp_path, c, ctx)
    rec = ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
        source_anchor_id="sa-manual", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
        page_number=1, control_points=_BENT_4PT, row_ids=[row_id],
        manual_route=_manual(representative_status="MANUAL_POLYLINE_CONFIRMED")), ctx=ctx, c=c)
    polyline = rec["control_points"]
    assert len(polyline) == 4

    summary = ppr.render_source_anchor_route(_JOB, "sa-manual", ctx=ctx, c=c)
    dots = summary["station_dots"].get("sa-manual") or []
    assert dots
    footages = sorted(d["footage_along"] for d in dots)
    assert footages == [0.0, 50.0, 100.0, 150.0]        # the seeded row's own 150ft footage, every 50ft tick

    pts = [(p["x"], p["y"]) for p in polyline]
    cum = _local_cumulative_arclen(pts)
    total_len = cum[-1]
    for d in dots:
        target_pt = (d["footage_along"] / 150.0) * total_len
        exact_xy = _local_point_at_arclen(pts, cum, target_pt)
        min_dist = min(
            _point_to_segment_distance(exact_xy[0], exact_xy[1], pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1])
            for i in range(len(pts) - 1))
        assert min_dist <= 1e-9, (d, min_dist, exact_xy)
        assert d["xy_display"] == {"x": round(exact_xy[0], 2), "y": round(exact_xy[1], 2)}, (d, exact_xy)
        assert d["provenance"] == "HUMAN_CONFIRMED_CONTROL_POINTS"


# --------------------------------------------------------------------------- #
# Tenant isolation (mirrors the adoption suite's own lock).
# --------------------------------------------------------------------------- #
def test_manual_route_tenant_isolation(tmp_path):
    c = _container(tmp_path)
    a_ctx, b_ctx = _ctx("cp-manual-a"), _ctx("cp-manual-b")
    plan_upload_id, rbl_id, row_id = _seed_job(tmp_path, c, a_ctx)
    ppr.create_project(ppr.ProjectCreate(display_name="B"), ctx=b_ctx, c=c)
    with pytest.raises(HTTPException) as exc:                   # B has no job-1 -> 404 before manual validation
        ppr.create_source_anchor_route(_JOB, ppr.SourceAnchorCreate(
            source_anchor_id="sa-1", plan_upload_id=plan_upload_id, reviewed_bore_log_id=rbl_id,
            page_number=1, control_points=_STRAIGHT_2PT, row_ids=[row_id],
            manual_route=_manual(representative_status="REPRESENTATIVE_STRAIGHT_ACCEPTED")),
            ctx=b_ctx, c=c)
    assert exc.value.status_code == 404
