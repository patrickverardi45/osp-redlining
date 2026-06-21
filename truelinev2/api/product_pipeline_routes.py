"""Local-only, flag-gated, generic product-pipeline routes (Slices 1-2).

Thin, context-bearing routes that DRIVE the existing product contracts (no business logic lives here — it
lives in the contracts; mirrors api/routes.py). Identity is the VERIFIED `X-TL-Tenant` slug from the
request context (never the URL path or a request body): `customer_project_id == ctx.tenant.value`, so a
tenant can only ever address its own customer_project subtree. Mounted by create_app ONLY when
settings.product_pipeline_api_optin is True (DEFAULT OFF).

Slice 1 — customer_project + processing_job foundation (create / get / transition).
Slice 2 — inputs + the reviewed-bore-log review gate: register an upload (bytes as base64 JSON; every
  upload stays UNTRUSTED, extraction_status="queued" — NO OCR/AI runs), create a reviewed_bore_log over a
  BORE_LOG upload, add UNTRUSTED extracted rows, review a row, define a segment_group, set its grouping
  status, and read the derived review-queue (which exposes the engine-eligibility / readiness gate). A row
  becomes engine-eligible ONLY through the contract's review + grouping gate; the API never confers trust.

Manifest handoff, proof artifacts, KMZ, closeout, billing, and export are later slices and are NOT
implemented here. No engine, renderer, fixtures, web/backend wiring, AI/OCR, deploy, or new dependency.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from truelinev2.api.container import Container
from truelinev2.api.deps import get_container, get_context
from truelinev2.context import IsolationError, RequestContext
from truelinev2.contracts.customer_project import (
    CrossProjectAccessError,
    CustomerProjectError,
    ProjectNotFoundError,
    create_customer_project,
    load_customer_project,
)
from truelinev2.contracts.processing_job import (
    IllegalTransitionError,
    JobNotFoundError,
    ProcessingJobError,
    create_job,
    load_job,
    transition,
)
from truelinev2.contracts.upload_pipeline import (
    UploadError,
    UploadsClosedError,
    accept_upload,
)
from truelinev2.contracts.extracted_row import (
    ExtractedRowError,
    new_extracted_row,
)
from truelinev2.contracts.reviewed_bore_log import (
    GroupNotFoundError,
    ReviewedBoreLogError,
    ReviewedBoreLogNotFoundError,
    RowNotFoundError,
    add_extracted_rows,
    create_reviewed_bore_log,
    define_segment_group,
    load_reviewed_bore_log,
    review_queue,
    review_row_in_log,
    set_grouping_status,
)

router = APIRouter(prefix="/v2/product")


class ProjectCreate(BaseModel):
    display_name: str


class JobCreate(BaseModel):
    job_id: str


class JobTransition(BaseModel):
    to_status: str
    reason: Optional[str] = None


# --- Slice 2 request bodies (none carries identity — the tenant is the verified context) ------------- #
class UploadRegister(BaseModel):
    kind: str
    filename: str
    content_base64: str


class ReviewedBoreLogCreate(BaseModel):
    reviewed_bore_log_id: str
    source_upload_id: str


class ExtractedRowInput(BaseModel):
    row_id: str
    source_upload_id: str
    raw: dict
    normalized: dict
    extraction_method: str
    extractor_name: Optional[str] = None
    confidence: Optional[str] = None
    warnings: Optional[list] = None


class RowsAdd(BaseModel):
    rows: list[ExtractedRowInput]


class RowReview(BaseModel):
    to_status: str
    reason: Optional[str] = None
    corrected_values: Optional[dict] = None


class SegmentGroupCreate(BaseModel):
    group_id: str
    member_row_ids: list[str]
    relation: str


class GroupingStatus(BaseModel):
    to_status: str
    reason: Optional[str] = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _store_root(c: Container):
    return c.settings.product_store_root


def _to_http(exc: Exception) -> HTTPException:
    """Map a contract / isolation exception to the repo's HTTP convention (order matters: the specific
    NotFound / state-conflict subclasses are caught before the contract base errors fall through to 400)."""
    if isinstance(exc, (ProjectNotFoundError, JobNotFoundError, ReviewedBoreLogNotFoundError,
                        RowNotFoundError, GroupNotFoundError)):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, (IllegalTransitionError, UploadsClosedError)):    # state conflicts
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, (CrossProjectAccessError, IsolationError)):
        return HTTPException(status_code=403, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))   # invalid id / bad target / missing reason / ...


# Every contract-error base this router translates to HTTP via _to_http (which dispatches by the specific
# subclass). A non-contract error is left to propagate (a real 500 — never masked as a 400).
_CONTRACT_ERRORS = (CustomerProjectError, ProcessingJobError, UploadError,
                    ExtractedRowError, ReviewedBoreLogError, IsolationError)


@router.post("/project")
def create_project(req: ProjectCreate,
                   ctx: RequestContext = Depends(get_context),
                   c: Container = Depends(get_container)) -> dict:
    """Create the customer_project for the authenticated tenant (id == ctx.tenant.value). The id is never
    taken from the path or body. 409 if it already exists; display_name is opaque runtime data."""
    cp, store = ctx.tenant.value, _store_root(c)
    try:
        load_customer_project(store, cp)
    except ProjectNotFoundError:
        pass                                                # expected: not created yet
    except (CustomerProjectError, IsolationError) as exc:   # e.g. invalid slug
        raise _to_http(exc)
    else:
        raise HTTPException(status_code=409, detail="project already exists")
    try:
        return create_customer_project(store, cp, req.display_name, _now())
    except (CustomerProjectError, IsolationError) as exc:
        raise _to_http(exc)


@router.get("/project")
def get_project(ctx: RequestContext = Depends(get_context),
                c: Container = Depends(get_container)) -> dict:
    """Load the authenticated tenant's customer_project (404 if none)."""
    try:
        return load_customer_project(_store_root(c), ctx.tenant.value)
    except (CustomerProjectError, IsolationError) as exc:
        raise _to_http(exc)


@router.post("/jobs")
def create_processing_job(req: JobCreate,
                          ctx: RequestContext = Depends(get_context),
                          c: Container = Depends(get_container)) -> dict:
    """Create a processing_job under the authenticated tenant's project (the project must exist first).
    409 if the job already exists."""
    cp, store = ctx.tenant.value, _store_root(c)
    try:
        load_customer_project(store, cp)                    # project required (404 if missing)
    except (CustomerProjectError, IsolationError) as exc:
        raise _to_http(exc)
    try:
        load_job(store, cp, req.job_id)
    except JobNotFoundError:
        pass                                                # expected: not created yet
    except (ProcessingJobError, IsolationError) as exc:     # e.g. invalid job id
        raise _to_http(exc)
    else:
        raise HTTPException(status_code=409, detail="job already exists")
    try:
        return create_job(store, cp, req.job_id, _now(), ctx.session_id)
    except (ProcessingJobError, IsolationError) as exc:
        raise _to_http(exc)


@router.get("/jobs/{job_id}")
def get_processing_job(job_id: str,
                       ctx: RequestContext = Depends(get_context),
                       c: Container = Depends(get_container)) -> dict:
    """Load one processing_job in the authenticated tenant's scope (404 if none)."""
    try:
        return load_job(_store_root(c), ctx.tenant.value, job_id)
    except (ProcessingJobError, IsolationError) as exc:
        raise _to_http(exc)


@router.post("/jobs/{job_id}/transition")
def transition_processing_job(job_id: str, req: JobTransition,
                              ctx: RequestContext = Depends(get_context),
                              c: Container = Depends(get_container)) -> dict:
    """Apply one server-authoritative, audited lifecycle transition (delegates to the processing_job
    contract). An illegal / unknown transition is a 409; a FAILED transition without a reason is a 400."""
    try:
        return transition(_store_root(c), ctx.tenant.value, job_id, req.to_status,
                          at=_now(), by=ctx.session_id, reason=req.reason)
    except (ProcessingJobError, IsolationError) as exc:
        raise _to_http(exc)


# --------------------------------------------------------------------------- #
# Slice 2 — inputs + the reviewed-bore-log review gate.
# --------------------------------------------------------------------------- #
@router.post("/jobs/{job_id}/uploads")
def register_upload(job_id: str, req: UploadRegister,
                    ctx: RequestContext = Depends(get_context),
                    c: Container = Depends(get_container)) -> dict:
    """Register one product input file into the tenant's job. Bytes arrive base64-encoded (no
    python-multipart). The upload is stored and recorded UNTRUSTED — extraction_status is always
    "queued"; NO OCR/AI extraction runs here. 404 if the job is missing, 409 if intake is closed (job
    past the upload phase), 400 on a bad kind/extension/size or invalid base64."""
    cp, store = ctx.tenant.value, _store_root(c)
    try:
        content = base64.b64decode(req.content_base64, validate=True)
    except ValueError:
        raise HTTPException(status_code=400, detail="content_base64 must be valid base64")
    try:
        return accept_upload(store, cp, job_id, kind=req.kind, filename=req.filename,
                             content=content, stored_at=_now())
    except _CONTRACT_ERRORS as exc:
        raise _to_http(exc)


@router.post("/jobs/{job_id}/reviewed-bore-logs")
def create_bore_log_review(job_id: str, req: ReviewedBoreLogCreate,
                           ctx: RequestContext = Depends(get_context),
                           c: Container = Depends(get_container)) -> dict:
    """Create a reviewed_bore_log over an existing BORE_LOG upload in the tenant's job. 409 if one with
    that id already exists; 404 if the job is missing; 400 if source_upload_id is not a BORE_LOG upload."""
    cp, store = ctx.tenant.value, _store_root(c)
    try:
        load_reviewed_bore_log(store, cp, job_id, req.reviewed_bore_log_id)
    except ReviewedBoreLogNotFoundError:
        pass                                                # expected: not created yet
    except _CONTRACT_ERRORS as exc:                         # e.g. invalid reviewed_bore_log id
        raise _to_http(exc)
    else:
        raise HTTPException(status_code=409, detail="reviewed_bore_log already exists")
    try:
        return create_reviewed_bore_log(store, cp, job_id, req.source_upload_id,
                                        req.reviewed_bore_log_id, at=_now(), by=ctx.session_id)
    except _CONTRACT_ERRORS as exc:
        raise _to_http(exc)


@router.post("/jobs/{job_id}/reviewed-bore-logs/{reviewed_bore_log_id}/rows")
def add_rows(job_id: str, reviewed_bore_log_id: str, req: RowsAdd,
             ctx: RequestContext = Depends(get_context),
             c: Container = Depends(get_container)) -> dict:
    """Append UNTRUSTED extracted rows (built via the contract's new_extracted_row; every row starts
    UNREVIEWED — never a placement candidate). 404 if the reviewed_bore_log is missing; 400 on a bad
    extraction_method / confidence or a duplicate row_id."""
    cp, store, now = ctx.tenant.value, _store_root(c), _now()
    try:
        built = [new_extracted_row(r.row_id, r.source_upload_id, raw=r.raw, normalized=r.normalized,
                                   extraction_method=r.extraction_method, extractor_name=r.extractor_name,
                                   confidence=r.confidence, warnings=r.warnings, at=now, by=ctx.session_id)
                 for r in req.rows]
        return add_extracted_rows(store, cp, job_id, reviewed_bore_log_id, built,
                                  at=now, by=ctx.session_id)
    except _CONTRACT_ERRORS as exc:
        raise _to_http(exc)


@router.post("/jobs/{job_id}/reviewed-bore-logs/{reviewed_bore_log_id}/rows/{row_id}/review")
def review_row_route(job_id: str, reviewed_bore_log_id: str, row_id: str, req: RowReview,
                     ctx: RequestContext = Depends(get_context),
                     c: Container = Depends(get_container)) -> dict:
    """Apply one audited human review decision to a row (CONFIRMED / CORRECTED / REJECTED /
    NEEDS_CLARIFICATION / UNREVIEWED). Trust rules live in the contract: CORRECTED needs corrected_values,
    REJECTED / NEEDS_CLARIFICATION need a reason (400 otherwise). 404 if the row or log is missing."""
    cp, store = ctx.tenant.value, _store_root(c)
    try:
        return review_row_in_log(store, cp, job_id, reviewed_bore_log_id, row_id, req.to_status,
                                 at=_now(), by=ctx.session_id, reason=req.reason,
                                 corrected_values=req.corrected_values)
    except _CONTRACT_ERRORS as exc:
        raise _to_http(exc)


@router.post("/jobs/{job_id}/reviewed-bore-logs/{reviewed_bore_log_id}/groups")
def define_group(job_id: str, reviewed_bore_log_id: str, req: SegmentGroupCreate,
                 ctx: RequestContext = Depends(get_context),
                 c: Container = Depends(get_container)) -> dict:
    """Define a segment_group (status PENDING) over >= 1 existing rows with a relation
    (SEPARATE_BORE / SAME_RUN_SEGMENTS / AMBIGUOUS). 404 if a member row is unknown; 400 on a bad relation
    or a duplicate group_id."""
    cp, store = ctx.tenant.value, _store_root(c)
    try:
        return define_segment_group(store, cp, job_id, reviewed_bore_log_id, req.group_id,
                                    req.member_row_ids, req.relation, at=_now(), by=ctx.session_id)
    except _CONTRACT_ERRORS as exc:
        raise _to_http(exc)


@router.post("/jobs/{job_id}/reviewed-bore-logs/{reviewed_bore_log_id}/groups/{group_id}/status")
def set_group_status(job_id: str, reviewed_bore_log_id: str, group_id: str, req: GroupingStatus,
                     ctx: RequestContext = Depends(get_context),
                     c: Container = Depends(get_container)) -> dict:
    """Set a segment_group's grouping status (PENDING -> CONFIRMED | SOURCE_CONFLICT; SOURCE_CONFLICT
    requires a reason -> 400 otherwise). 404 if the group is missing; 400 on an unknown status."""
    cp, store = ctx.tenant.value, _store_root(c)
    try:
        return set_grouping_status(store, cp, job_id, reviewed_bore_log_id, group_id, req.to_status,
                                   at=_now(), by=ctx.session_id, reason=req.reason)
    except _CONTRACT_ERRORS as exc:
        raise _to_http(exc)


@router.get("/jobs/{job_id}/reviewed-bore-logs/{reviewed_bore_log_id}/review-queue")
def get_review_queue(job_id: str, reviewed_bore_log_id: str,
                     ctx: RequestContext = Depends(get_context),
                     c: Container = Depends(get_container)) -> dict:
    """Pure, read-only review-queue view for the reviewed_bore_log: what still needs review, what passed,
    and the DERIVED engine-eligibility gate (engine_eligible_row_ids + engine_ready). Eligibility is never
    stored — the contract recomputes it from review + grouping. 404 if the log is missing."""
    cp, store = ctx.tenant.value, _store_root(c)
    try:
        rbl = load_reviewed_bore_log(store, cp, job_id, reviewed_bore_log_id)
    except _CONTRACT_ERRORS as exc:
        raise _to_http(exc)
    return review_queue(rbl)
