"""Field segment-evidence WRITE routes — the mobile field app's submit-to-review seam.

Thin, context-bearing routes over ``contracts.field_evidence``: create/update a segment's DRAFT evidence
package, read it back, and SUBMIT it for office review. Identity is the VERIFIED ``X-TL-Tenant`` slug from
the request context (``customer_project_id == ctx.tenant.value``) — never the URL path or a request body.
Mounted by create_app ONLY when settings.field_evidence_api_optin is True (DEFAULT OFF).

Photos are REFERENCES to job uploads of kind PHOTO made through the EXISTING binary upload route
(``POST /jobs/{job_id}/uploads``) — this lane adds no binary handling, no camera/GPS, no offline sync.

DOCTRINE (hard): field evidence SUPPORTS review; it never places. Nothing here touches the engine,
renderer, placement, job output slots, or lifecycle transitions; submit either transitions the package to
SUBMITTED_FOR_REVIEW or REFUSES with named BLOCKED_MISSING_REQUIRED_EVIDENCE reasons. All business logic
lives in the contract module, never here.

Endpoints (all tenant + job scoped):
  GET  /jobs/{job_id}/field-evidence                       — list the job's evidence packages.
  GET  /jobs/{job_id}/field-evidence/{segment_id}          — read one package (404 if never saved).
  PUT  /jobs/{job_id}/field-evidence/{segment_id}          — create/update the DRAFT package.
  POST /jobs/{job_id}/field-evidence/{segment_id}/submit   — validate required evidence; submit or refuse.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from truelinev2.api.container import Container
from truelinev2.api.deps import get_container, get_context
from truelinev2.context import IsolationError, RequestContext
from truelinev2.contracts.customer_project import (
    CrossProjectAccessError,
    CustomerProjectError,
    ProjectNotFoundError,
)
from truelinev2.contracts.field_evidence import (
    FieldEvidenceError,
    FieldEvidenceNotFoundError,
    list_field_evidence,
    load_field_evidence,
    save_field_evidence,
    submit_field_evidence,
)
from truelinev2.contracts.processing_job import JobNotFoundError, ProcessingJobError

router = APIRouter(prefix="/v2/product")


def _store_root(c: Container):
    return c.settings.product_store_root


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_http(exc: Exception) -> HTTPException:
    """Map contract errors to the repo's HTTP convention, mirroring product_readiness_routes._job_to_http
    (order matters): missing job/project/package -> 404, cross-project / isolation -> 403, invalid
    slug / payload / locked package / other contract error -> 400. Non-contract errors propagate (a real
    500, never masked)."""
    if isinstance(exc, (JobNotFoundError, ProjectNotFoundError, FieldEvidenceNotFoundError)):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, (CrossProjectAccessError, IsolationError)):
        return HTTPException(status_code=403, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


_ERRORS = (ProcessingJobError, CustomerProjectError, IsolationError, FieldEvidenceError)


class FieldEvidencePayload(BaseModel):
    """Thin transport wrapper — DEEP validation (kinds, types, numbers, duplicate ids, problem-photo
    linkage) lives in the contract's normalizer, the single source of truth."""
    reviewed_bore_log_id: Optional[str] = None
    source_span_ref: Optional[str] = None
    start_station: Optional[str] = None
    end_station: Optional[str] = None
    photos: list = Field(default_factory=list)
    problems: list = Field(default_factory=list)
    readings: list = Field(default_factory=list)
    notes: Optional[str] = None


@router.get("/jobs/{job_id}/field-evidence")
def list_field_evidence_route(job_id: str,
                              ctx: RequestContext = Depends(get_context),
                              c: Container = Depends(get_container)) -> dict:
    """List the tenant job's field-evidence packages (honest empty list when none). 404 if the job is
    missing (incl. cross-tenant)."""
    try:
        return {"field_evidence": list_field_evidence(_store_root(c), ctx.tenant.value, job_id)}
    except _ERRORS as exc:
        raise _to_http(exc)


@router.get("/jobs/{job_id}/field-evidence/{segment_id}")
def get_field_evidence_route(job_id: str, segment_id: str,
                             ctx: RequestContext = Depends(get_context),
                             c: Container = Depends(get_container)) -> dict:
    """Read one segment's evidence package. 404 if the job or the package is missing."""
    try:
        return load_field_evidence(_store_root(c), ctx.tenant.value, job_id, segment_id)
    except _ERRORS as exc:
        raise _to_http(exc)


@router.put("/jobs/{job_id}/field-evidence/{segment_id}")
def put_field_evidence_route(job_id: str, segment_id: str, req: FieldEvidencePayload,
                             ctx: RequestContext = Depends(get_context),
                             c: Container = Depends(get_container)) -> dict:
    """Create/update the segment's DRAFT evidence package (start/end stations, photo references to real
    PHOTO uploads, problem areas, digital bore-log readings, notes). Saving never submits; a package
    already submitted for review is locked (400). 404 if the job is missing."""
    try:
        return save_field_evidence(_store_root(c), ctx.tenant.value, job_id, segment_id,
                                   req.model_dump(), at=_now(), by=ctx.session_id)
    except _ERRORS as exc:
        raise _to_http(exc)


@router.post("/jobs/{job_id}/field-evidence/{segment_id}/submit")
def submit_field_evidence_route(job_id: str, segment_id: str,
                                ctx: RequestContext = Depends(get_context),
                                c: Container = Depends(get_container)) -> dict:
    """Submit the segment's evidence package for office review. Enforces the owner's field rules (start
    station photo, end station photo, a photo per logged problem area — all bound to real PHOTO uploads);
    an incomplete package is REFUSED with named BLOCKED_MISSING_REQUIRED_EVIDENCE reasons and stays
    DRAFT. Performs NO AUTO, NO placement, NO redline generation, NO job status/slot change. 404 if the
    job or the package is missing."""
    try:
        return submit_field_evidence(_store_root(c), ctx.tenant.value, job_id, segment_id,
                                     at=_now(), by=ctx.session_id)
    except _ERRORS as exc:
        raise _to_http(exc)
