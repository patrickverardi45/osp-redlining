"""PHASE-2 SOURCE-ROUTE PROPOSAL — a read-only-by-effect, stateless, artifact-free proposal endpoint
(T31 spec Q7; foreman ticket W-B).

    POST /v2/product/jobs/{job_id}/source-route-proposals

Given a selected plan upload, reviewed bore-log, product row, page, and exactly two HUMAN control points, this
route: (1) requires the row to be engine-eligible and share the reviewed bore-log's BORE_LOG source upload;
(2) runs the UNCHANGED read-only readiness spine (``harness.product_readiness_bridge.run_job_route_readiness_raw``)
FILTERED to ONLY the selected plan + BORE_LOG uploads — never the job's full upload set; (3) requires exactly one
READY_FOR_REVIEW_REDLINE route-ready candidate whose span matches the selected row's effective stations and whose
resolved page matches the request; (4) projects the two human controls onto the verified observer backbone
(``contracts.source_route_adoption.derive_route_geometry``, pure) and returns either a stateless, content-addressed
PROPOSAL (never persisted — the client must round-trip its ``proposal_hash`` back through
``POST .../source-anchors`` with a ``route_adoption`` block to durably adopt it) or a named, path-free REFUSAL.

It writes NOTHING: no readiness artifact, no PNG, no record, no job-state mutation. HTTP 200 on both outcomes
(``{"outcome": "PROPOSAL", ...}`` / ``{"outcome": "REFUSAL", ...}``) — a defensible "no route" is an expected
search result, not an error. Malformed request identity / non-finite controls / a control count != 2 is HTTP 400;
missing scoped resources use the repo's existing 404/403 conventions.

Mounted by ``api.app.create_app`` ONLY when ALL THREE are True: ``product_pipeline_api_optin`` AND
``product_readiness_api_optin`` AND ``source_route_adoption_api_optin`` (every one DEFAULT OFF). With the new flag
OFF, this module is never imported at request time and the existing ``SourceAnchorCreate`` path is untouched.
"""
from __future__ import annotations

import math
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from truelinev2.api.container import Container
from truelinev2.api.deps import get_container, get_context
from truelinev2.context import IsolationError, RequestContext
from truelinev2.contracts.customer_project import CrossProjectAccessError, CustomerProjectError
from truelinev2.contracts.processing_job import (
    JobNotFoundError,
    ProcessingJobError,
    job_dir,
    load_job,
)
from truelinev2.contracts.reviewed_bore_log import (
    ReviewedBoreLogError,
    ReviewedBoreLogNotFoundError,
    load_reviewed_bore_log,
    row_engine_eligible,
)
from truelinev2.contracts.source_anchor import PLAN_PDF_KIND
from truelinev2.contracts.source_route_adoption import (
    check_cross_page,
    check_row_engine_eligible,
    check_row_source_upload,
    check_row_span_match,
    check_single_ready_candidate,
    build_proposal,
    derive_route_geometry,
    not_ready_refusal,
    row_effective_stations,
    row_evidence_hash,
)
from truelinev2.harness.product_readiness_bridge import READY_STATUS, run_job_route_readiness_raw
from truelinev2.stations import parse_station

router = APIRouter(prefix="/v2/product")

_JOB_ERRORS = (ProcessingJobError, CustomerProjectError, IsolationError)
_RBL_ERRORS = (ReviewedBoreLogError, IsolationError)


class ControlPointIn(BaseModel):
    x: float
    y: float


class SourceRouteProposalRequest(BaseModel):
    plan_upload_id: str
    reviewed_bore_log_id: str
    row_id: str
    page_number: int
    control_points: List[ControlPointIn]


def _store_root(c: Container):
    return c.settings.product_store_root


def _job_to_http(exc: Exception) -> HTTPException:
    """Mirrors ``product_readiness_routes._job_to_http`` (order matters): missing job/project -> 404,
    cross-project / isolation -> 403, invalid slug / job id / other contract error -> 400."""
    if isinstance(exc, JobNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, (CrossProjectAccessError, IsolationError)):
        return HTTPException(status_code=403, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


def _refusal(refusal) -> dict:
    return {"outcome": "REFUSAL", "refusal": refusal.to_dict()}


def _require_finite_control_points(control_points: List[ControlPointIn]) -> None:
    if len(control_points) != 2:
        raise HTTPException(status_code=400,
                            detail="control_points must be exactly two points for a route proposal")
    for p in control_points:
        if not (isinstance(p.x, (int, float)) and isinstance(p.y, (int, float))
                and math.isfinite(p.x) and math.isfinite(p.y)):
            raise HTTPException(status_code=400, detail="control_points must be finite numeric coordinates")


@router.post("/jobs/{job_id}/source-route-proposals")
def create_source_route_proposal(job_id: str, req: SourceRouteProposalRequest,
                                 ctx: RequestContext = Depends(get_context),
                                 c: Container = Depends(get_container)) -> dict:
    """Stateless source-route proposal (see module docstring). Runs no renderer, writes no readiness result or
    proposal record, creates no artifacts, and changes no job state. 200 on both PROPOSAL and REFUSAL outcomes;
    400 on a malformed request; 404/403 for missing/cross-tenant scoped resources."""
    _require_finite_control_points(req.control_points)
    cp, store = ctx.tenant.value, _store_root(c)

    try:
        job = load_job(store, cp, job_id)
    except _JOB_ERRORS as exc:
        raise _job_to_http(exc)

    plan_upload = next((u for u in job.get("uploads", [])
                        if u.get("upload_id") == req.plan_upload_id and u.get("kind") == PLAN_PDF_KIND), None)
    if plan_upload is None:
        raise HTTPException(status_code=404,
                            detail="no PLAN_PDF upload %r in this job" % (req.plan_upload_id,))

    try:
        rbl = load_reviewed_bore_log(store, cp, job_id, req.reviewed_bore_log_id)
    except ReviewedBoreLogNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except _RBL_ERRORS as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    row = next((r for r in rbl.get("rows", []) if r.get("row_id") == req.row_id), None)
    if row is None:
        raise HTTPException(status_code=404, detail="no row %r in this reviewed_bore_log" % (req.row_id,))

    refusal = check_row_engine_eligible(row_engine_eligible(rbl, req.row_id))
    if refusal is not None:
        return _refusal(refusal)

    refusal = check_row_source_upload(row.get("source_upload_id"), rbl.get("source_upload_id"))
    if refusal is not None:
        return _refusal(refusal)

    # Run the UNCHANGED readiness spine, FILTERED to ONLY this selection's plan + BORE_LOG uploads (never the
    # job's full upload set) — artifact-free, no store write, no PNG.
    allowed_upload_ids = [req.plan_upload_id, rbl.get("source_upload_id")]
    readiness, sheet_ctx = run_job_route_readiness_raw(
        job.get("uploads") or [], job_dir(store, cp, job_id), allowed_upload_ids=allowed_upload_ids,
        store_root=store)
    if readiness is None:
        return _refusal(not_ready_refusal(sheet_ctx.get("refusal") or "NO_SPINE_INPUT"))
    if readiness.report.status != READY_STATUS:
        return _refusal(not_ready_refusal(readiness.report.status))

    ready_verifications = [v for v in readiness.routes.verifications if v.route_ready]
    refusal = check_single_ready_candidate(len(ready_verifications))
    if refusal is not None:
        return _refusal(refusal)
    if not ready_verifications:                                    # defensive — READY implies >= 1
        return _refusal(not_ready_refusal(readiness.report.status))
    verification = ready_verifications[0]

    span = next((s for s in readiness.extraction.spans if s.span_id == verification.span_id), None)
    if span is None:                                                # defensive — READY implies a matching span
        return _refusal(not_ready_refusal(readiness.report.status))

    row_start_txt, row_end_txt = row_effective_stations(row)
    row_start_ft = parse_station(row_start_txt) if row_start_txt else None
    row_end_ft = parse_station(row_end_txt) if row_end_txt else None
    candidate_start_ft = parse_station(span.start_station)
    candidate_end_ft = parse_station(span.end_station)
    refusal = check_row_span_match(row_start_ft, row_end_ft, candidate_start_ft, candidate_end_ft)
    if refusal is not None:
        return _refusal(refusal)

    refusal = check_cross_page(req.page_number, sheet_ctx.get("pdf_page"))
    if refusal is not None:
        return _refusal(refusal)

    reach_tol = (verification.detail or {}).get("isolation", {}).get("detail", {}).get("reach_tol")

    human_start = (req.control_points[0].x, req.control_points[0].y)
    human_end = (req.control_points[1].x, req.control_points[1].y)

    geometry, refusal = derive_route_geometry(
        backbone_segments=verification.route_geometry, gap_bridge_status=verification.gap_bridge_status,
        reach_tol=reach_tol, human_start=human_start, human_end=human_end)
    if refusal is not None:
        return _refusal(refusal)

    scope = {"tenant": cp, "job_id": job_id, "plan_upload_id": req.plan_upload_id,
             "reviewed_bore_log_id": req.reviewed_bore_log_id, "row_id": req.row_id,
             "page_number": req.page_number}
    plan_source = {"plan_upload_id": req.plan_upload_id, "plan_sha256": plan_upload.get("sha256"),
                   "engineering_sheet": sheet_ctx.get("engineering_sheet"), "pdf_page": sheet_ctx.get("pdf_page"),
                   "sheet_offset": sheet_ctx.get("sheet_offset")}
    span_source = {"span_id": span.span_id, "source_file": span.source_file, "source_page": span.source_page,
                   "reviewed_bore_log_id": req.reviewed_bore_log_id, "row_id": req.row_id,
                   # Fix-wave F5: the row's FULL effective-value hash (raw < normalized < corrected precedence)
                   # -- any reviewed/corrected value change (not just stations) invalidates this proposal.
                   "row_evidence_hash": row_evidence_hash(row)}
    readiness_dict = {"readiness_status": readiness.report.status,
                      "route_isolation_status": verification.route_isolation_status,
                      "main_run_status": verification.main_run_status,
                      "gap_bridge_status": verification.gap_bridge_status}

    proposal = build_proposal(
        scope=scope, plan_source=plan_source, span_source=span_source, readiness=readiness_dict,
        reach_tol=float(reach_tol), human_start=human_start, human_end=human_end, geometry=geometry,
        confirmed_by=ctx.session_id)
    return {"outcome": "PROPOSAL", "proposal": proposal.to_dict()}
