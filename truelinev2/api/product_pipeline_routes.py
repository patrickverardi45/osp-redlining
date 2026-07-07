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
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from truelinev2.api.container import Container
from truelinev2.api.deps import get_container, get_context
from truelinev2.api.guards import assert_destructive_enabled
from truelinev2.context import IsolationError, RequestContext
from truelinev2.store.snapshot import snapshot_store
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
    delete_job,
    job_dir,
    list_jobs,
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
from truelinev2.extract.borelog_rows import (
    BoreLogExtractionError,
    extract_rows_from_borelog,
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
from truelinev2.contracts.terminus_report import terminus_evidence_report
from truelinev2.contracts.manifest_handoff import (
    ARTIFACT_BUNDLE_SLOT,
    BUNDLE_STORE_SUBDIR,
    MANIFEST_SLOT,
    HandoffNotFoundError,
    HandoffStateError,
    ManifestHandoffError,
    finalize_handoff,
    load_handoff,
    record_handoff_attempt,
)
from truelinev2.contracts.published_bundle_consumer import (
    ArtifactNotServableError,
    BundleNotReadableError,
    ConsumerError,
    StaticBundleConsumer,
)
from truelinev2.contracts.kmz_export import (
    EXPORTABLE as KMZ_EXPORTABLE,
    KMZ_MEDIA_TYPE,
    build_kmz_bytes,
    evaluate_export,
)
from truelinev2.contracts.closeout_review import (
    CloseoutNotFoundError,
    CloseoutReviewError,
    CloseoutStateError,
    closeout_summary,
    create_closeout_review,
    evaluate_closeout,
    load_closeout_review,
)
from truelinev2.contracts.billing_summary import (
    BillingSummaryError,
    BillingSummaryNotFoundError,
    billing_summary_view,
    compute_billing_summary,
    create_billing_summary,
    load_billing_summary,
)
from truelinev2.contracts.job_pricing import (
    JobPricingError,
    pricing_view,
    save_job_pricing,
)
from truelinev2.contracts.export_package import (
    ExportPackageError,
    ExportPackageNotFoundError,
    assemble_export_package,
    create_export_package,
    export_package_view,
    load_export_package,
)
from truelinev2.contracts.export_bundle import (
    EXPORT_ZIP_MEDIA_TYPE,
    ExportBundleError,
    NoRedlineBundleError,
    build_export_zip,
)
from truelinev2.contracts.closeout_pdf import (
    PDF_MEDIA_TYPE,
    CloseoutPdfError,
    NoCloseoutPdfError,
    build_closeout_pdf,
)
from truelinev2.contracts.gis_route import GisRouteError, load_job_gis_route, load_job_route_kmz
from truelinev2.contracts.engine_handoff_readiness import evaluate_engine_handoff_readiness
from truelinev2.contracts.recognized_corpus_handoff import (
    RecognizedCorpusError,
    evaluate_recognized_corpus_handoff,
    load_registry,
    render_recognized_corpus_handoff,
)
from truelinev2.contracts.uploaded_corpus_engine_handoff import (
    UploadedCorpusEngineError,
    evaluate_uploaded_corpus_engine_handoff,
    render_uploaded_corpus_engine_handoff,
)
from truelinev2.contracts.review_acceptance import (
    ReviewAcceptanceError,
    ReviewAcceptanceStateError,
    ReviewCandidateNotFoundError,
    accept_review_candidate,
    generate_review_candidate,
    list_review_candidates,
    load_review_candidate,
    reject_review_candidate,
)
from truelinev2.contracts.product_workflow import (
    ProductWorkflowError,
    assemble_closeout_package,
    export_gate,
    run_product_redline,
)
from truelinev2.contracts.source_anchor import (
    PLAN_PDF_KIND,
    SourceAnchorError,
    SourceAnchorNotFoundError,
    SourceAnchorStateError,
    create_source_anchor,
    list_source_anchors,
    load_source_anchor,
)
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.ingest.sheet_label_index import build_sheet_index, SHEET_TYPE_OTHER
from truelinev2.render.source_anchor_render import render_job_source_anchors

router = APIRouter(prefix="/v2/product")

BORE_LOG_KIND = "BORE_LOG"   # canonical upload kind for a bore-log file (mirrors PLAN_PDF_KIND)


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


# --- Slice 3 request bodies (none carries identity — the tenant is the verified context) ------------- #
class ManifestHandoffRecord(BaseModel):
    reviewed_bore_log_id: str
    engine_run_id: str
    engine_run_status: str
    warnings: Optional[list] = None


class ManifestHandoffFinalize(BaseModel):
    bundle_ref: str


# --- Source-anchor request bodies (M2; none carries identity — the tenant is the verified context) ---- #
class SourceAnchorIdentity(BaseModel):
    station: Optional[str] = None
    structure_label: Optional[str] = None
    note: Optional[str] = None


class ControlPoint(BaseModel):
    x: float
    y: float


class SourceAnchorCreate(BaseModel):
    source_anchor_id: str
    plan_upload_id: str
    reviewed_bore_log_id: str
    page_number: int
    control_points: list[ControlPoint]
    group_id: Optional[str] = None
    row_ids: Optional[list[str]] = None
    start_identity: Optional[SourceAnchorIdentity] = None
    end_identity: Optional[SourceAnchorIdentity] = None
    notes: Optional[str] = None


# --- Phase 6 REVIEW acceptance request body (no identity — the tenant is the verified context) --------- #
class ReviewReject(BaseModel):
    reason: str


class OperatorPricingException(BaseModel):
    label: str
    amount: Optional[str] = None        # blank/None allowed; validated server-side (non-negative number)
    note: Optional[str] = None


class OperatorPricingUpdate(BaseModel):
    cost_per_foot: Optional[str] = None  # blank/None allowed — NO default rate is ever invented
    exceptions: list[OperatorPricingException] = []


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _store_root(c: Container):
    return c.settings.product_store_root


def _job_summary(job: dict) -> dict:
    """Lightweight, tenant-safe job summary for the list view (no payload bytes, no audit dump). Output
    slots are surfaced as booleans (filled-or-not), never their refs."""
    audit = job.get("audit") or []
    slots = job.get("slots") or {}
    return {
        "job_id": job.get("job_id"),
        "status": job.get("status"),
        "created_at": job.get("created_at"),
        "updated_at": audit[-1].get("at") if audit else job.get("created_at"),
        "upload_count": len(job.get("uploads") or []),
        "slots": {name: (slots.get(name) is not None) for name in slots},
    }


def _to_http(exc: Exception) -> HTTPException:
    """Map a contract / isolation exception to the repo's HTTP convention (order matters: the specific
    NotFound / state-conflict subclasses are caught before the contract base errors fall through to 400)."""
    if isinstance(exc, (ProjectNotFoundError, JobNotFoundError, ReviewedBoreLogNotFoundError,
                        RowNotFoundError, GroupNotFoundError, HandoffNotFoundError,
                        BundleNotReadableError, ArtifactNotServableError, CloseoutNotFoundError,
                        BillingSummaryNotFoundError, ExportPackageNotFoundError,
                        SourceAnchorNotFoundError, ReviewCandidateNotFoundError)):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, (IllegalTransitionError, UploadsClosedError, HandoffStateError,
                        CloseoutStateError, SourceAnchorStateError,
                        ReviewAcceptanceStateError)):   # state conflicts
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, (CrossProjectAccessError, IsolationError)):
        return HTTPException(status_code=403, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))   # invalid id / bad target / missing reason / ...


# Every contract-error base this router translates to HTTP via _to_http (which dispatches by the specific
# subclass). A non-contract error is left to propagate (a real 500 — never masked as a 400).
_CONTRACT_ERRORS = (CustomerProjectError, ProcessingJobError, UploadError, ExtractedRowError,
                    ReviewedBoreLogError, ManifestHandoffError, ConsumerError, CloseoutReviewError,
                    BillingSummaryError, JobPricingError, ExportPackageError, ExportBundleError,
                    CloseoutPdfError, GisRouteError, SourceAnchorError, ReviewAcceptanceError, IsolationError)


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


@router.get("/jobs")
def list_processing_jobs(ctx: RequestContext = Depends(get_context),
                         c: Container = Depends(get_container)) -> dict:
    """List the authenticated tenant's processing_jobs (tenant-scoped — only this tenant's project, never
    another's). Returns a lightweight summary per job (id / status / created+updated / upload count /
    which output slots are filled). Empty list if the tenant has no jobs yet. Read-only."""
    try:
        jobs = list_jobs(_store_root(c), ctx.tenant.value)
    except (ProcessingJobError, IsolationError) as exc:
        raise _to_http(exc)
    return {"jobs": [_job_summary(j) for j in jobs]}


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


@router.post("/jobs/{job_id}/delete")
def delete_processing_job(job_id: str,
                          ctx: RequestContext = Depends(get_context),
                          c: Container = Depends(get_container)) -> dict:
    """Permanently delete the authenticated tenant's job — its record + all uploads + every artifact / stage
    subdir — so test/demo jobs do not stack forever. Tenant-safe + path-safe: the job dir is resolved under
    the verified tenant's project root and re-asserted contained before removal, so a tenant can only ever
    delete its OWN job. 404 if the job is missing (incl. a cross-tenant id); 403 on a cross-project record.
    POST (not DELETE) so no CORS method change is needed. No engine / render / status promotion — pure store
    removal."""
    # Fail-closed footgun gate (default BLOCKED): refuse before touching the store unless the operator
    # set TL2_ENABLE_DESTRUCTIVE_PRODUCT_ROUTES=1. NOT auth; the tenant/isolation checks below are
    # unchanged. See truelinev2/api/guards.py.
    assert_destructive_enabled(c.settings)
    cp, store = ctx.tenant.value, _store_root(c)
    # Confirm the job exists (tenant-scoped) BEFORE snapshotting/deleting, so a missing / cross-tenant id is
    # a clean 404/403 with no wasted snapshot.
    try:
        load_job(store, cp, job_id)
    except _CONTRACT_ERRORS as exc:
        raise _to_http(exc)
    # Phase 3: best-effort point-in-time snapshot of the served store BEFORE deletion, so an accidental
    # delete stays recoverable. A snapshot failure is RECORDED but does NOT block the (owner-enabled,
    # gated + audited) delete. See truelinev2/store/snapshot.py.
    snap = snapshot_store(store, reason="pre-delete-%s" % job_id)
    try:
        result = delete_job(store, cp, job_id)
    except _CONTRACT_ERRORS as exc:
        raise _to_http(exc)
    return {**result, "snapshot": {"ok": snap["ok"], "snapshot_path": snap["snapshot_path"],
                                   "file_count": snap["file_count"], "error": snap["error"]}}


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


@router.get("/jobs/{job_id}/reviewed-bore-logs/{reviewed_bore_log_id}")
def get_reviewed_bore_log_record(job_id: str, reviewed_bore_log_id: str,
                                 ctx: RequestContext = Depends(get_context),
                                 c: Container = Depends(get_container)) -> dict:
    """Read ONE reviewed_bore_log record in the tenant's job: rows (raw/normalized candidate values +
    per-row review state/audit) + segment groups. Read-only — no review/grouping mutation, no engine, no
    OCR. 404 if the reviewed_bore_log is missing; cross-tenant access cannot resolve it (tenant-scoped)."""
    cp, store = ctx.tenant.value, _store_root(c)
    try:
        return load_reviewed_bore_log(store, cp, job_id, reviewed_bore_log_id)
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


@router.post("/jobs/{job_id}/reviewed-bore-logs/{reviewed_bore_log_id}/extract")
def extract_bore_log_rows_route(job_id: str, reviewed_bore_log_id: str,
                                ctx: RequestContext = Depends(get_context),
                                c: Container = Depends(get_container)) -> dict:
    """Read-only deterministic bore-log TABLE extraction: parse the reviewed_bore_log's SOURCE upload into
    UNTRUSTED extracted rows (extraction_method=TABLE_IMPORT, status UNREVIEWED) and append them so the
    existing human review/grouping/eligibility gate is unchanged. This is the auto-extract path that replaces
    manual row entry as the default — it places NO geometry, fabricates NO confidence (deterministic table
    parse, not OCR), and confers NO engine eligibility. 404 if the log/job is missing; 400 if the source
    upload is missing/not a BORE_LOG/unparseable."""
    cp, store, now = ctx.tenant.value, _store_root(c), _now()
    try:
        rbl = load_reviewed_bore_log(store, cp, job_id, reviewed_bore_log_id)
        job = load_job(store, cp, job_id)
    except _CONTRACT_ERRORS as exc:
        raise _to_http(exc)
    source_upload_id = rbl.get("source_upload_id")
    upload = next((u for u in job.get("uploads", []) if u.get("upload_id") == source_upload_id), None)
    if upload is None or upload.get("kind") != BORE_LOG_KIND:
        raise HTTPException(status_code=400, detail="reviewed_bore_log has no BORE_LOG source upload")
    path = job_dir(store, cp, job_id) / upload.get("stored_path", "")
    if not path.is_file():
        raise HTTPException(status_code=400, detail="the bore-log source file is not available")
    existing = {r.get("row_id") for r in rbl.get("rows", [])}
    try:
        rows = extract_rows_from_borelog(path, source_upload_id, at=now, by=ctx.session_id,
                                         existing_row_ids=existing)
        record = add_extracted_rows(store, cp, job_id, reviewed_bore_log_id, rows, at=now, by=ctx.session_id)
    except BoreLogExtractionError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except _CONTRACT_ERRORS as exc:
        raise _to_http(exc)
    return {"extracted_count": len(rows),
            "extracted_row_ids": [r["row_id"] for r in rows],
            "record": record}


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


# --------------------------------------------------------------------------- #
# Slice 3 — manifest handoff + proof reads.
# --------------------------------------------------------------------------- #
ENGINE_OUTPUTS_SUBDIR = "engine_outputs"   # server-side, job-scoped staging for engine-output bundles
_BUNDLE_REF_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")


def _staged_bundle_root(store_root, customer_project_id, job_id, bundle_ref):
    """Resolve a SAFE client-supplied bundle_ref to the server-side engine-output staging path under the
    tenant's job scope. The ref must be ONE safe path segment (no separators/traversal); the bundle
    CONTENT is validated by the contract (store_bundle via finalize_handoff), never here."""
    if not isinstance(bundle_ref, str) or not _BUNDLE_REF_RE.match(bundle_ref):
        raise HTTPException(status_code=400, detail="invalid bundle_ref")
    return job_dir(store_root, customer_project_id, job_id) / ENGINE_OUTPUTS_SUBDIR / bundle_ref


def _open_job_bundle(store_root, customer_project_id, job_id):
    """Open the job's attached, validated redline bundle from its durable bundle_store via the read-only
    consumer (which re-enforces the website read contract). Requires a validated artifact_bundle output
    slot (set ONLY by a SUCCEEDED handoff) — raises BundleNotReadableError (→ 404) otherwise."""
    job = load_job(store_root, customer_project_id, job_id)
    slot = job["slots"].get(ARTIFACT_BUNDLE_SLOT)
    if not slot:
        raise BundleNotReadableError("no validated artifact_bundle for this job")
    bundle_store = job_dir(store_root, customer_project_id, job_id) / BUNDLE_STORE_SUBDIR
    consumer = StaticBundleConsumer(bundle_store, enable=True)
    return consumer.open_bundle(slot["ref"]["bundle_id"])


@router.post("/jobs/{job_id}/manifest-handoffs")
def record_manifest_handoff(job_id: str, req: ManifestHandoffRecord,
                            ctx: RequestContext = Depends(get_context),
                            c: Container = Depends(get_container)) -> dict:
    """Record an engine-output handoff ATTEMPT for the tenant's job (does NOT run the engine/renderer — the
    placement engine's output bundle is a GIVEN, finalized separately). 404 if the job/reviewed_bore_log is
    missing; 409 if a handoff with that engine_run_id already exists."""
    cp, store = ctx.tenant.value, _store_root(c)
    try:
        load_handoff(store, cp, job_id, req.engine_run_id)
    except HandoffNotFoundError:
        pass                                                # expected: not recorded yet
    except _CONTRACT_ERRORS as exc:                         # e.g. invalid engine_run / job id
        raise _to_http(exc)
    else:
        raise HTTPException(status_code=409, detail="handoff already exists")
    try:
        return record_handoff_attempt(store, cp, job_id, req.reviewed_bore_log_id, req.engine_run_id,
                                      engine_run_status=req.engine_run_status, warnings=req.warnings,
                                      at=_now(), by=ctx.session_id)
    except _CONTRACT_ERRORS as exc:
        raise _to_http(exc)


@router.post("/jobs/{job_id}/manifest-handoffs/{engine_run_id}/finalize")
def finalize_manifest_handoff(job_id: str, engine_run_id: str, req: ManifestHandoffFinalize,
                              ctx: RequestContext = Depends(get_context),
                              c: Container = Depends(get_container)) -> dict:
    """Finalize a recorded handoff THROUGH the contract: validate the staged engine-output bundle + durably
    store it + attach the redline_manifest / artifact_bundle output slots — ONLY if the reviewed_bore_log is
    engine-ready AND the bundle validates. The bundle is identified by a SAFE server-side staging ref (never
    a raw client path); validation is the contract's, never the API's. Returns the terminal record
    (SUCCEEDED / REJECTED / FAILED). 404 if no such handoff; 409 if already terminal; 400 on an unsafe ref."""
    cp, store = ctx.tenant.value, _store_root(c)
    try:
        bundle_root = _staged_bundle_root(store, cp, job_id, req.bundle_ref)
        return finalize_handoff(store, cp, job_id, engine_run_id, bundle_root,
                                at=_now(), by=ctx.session_id)
    except _CONTRACT_ERRORS as exc:
        raise _to_http(exc)


@router.get("/jobs/{job_id}/redline-manifest")
def get_redline_manifest(job_id: str,
                         ctx: RequestContext = Depends(get_context),
                         c: Container = Depends(get_container)) -> dict:
    """Read the job's validated redline_manifest output slot (descriptor / state ONLY — manifest_id,
    sha256, bundle_id, summary counts, validation_status). 404 if no validated handoff has attached it."""
    cp, store = ctx.tenant.value, _store_root(c)
    try:
        job = load_job(store, cp, job_id)
    except _CONTRACT_ERRORS as exc:
        raise _to_http(exc)
    slot = job["slots"].get(MANIFEST_SLOT)
    if not slot:
        raise HTTPException(status_code=404, detail="no validated redline_manifest for this job")
    return slot


@router.get("/jobs/{job_id}/artifacts")
def list_artifacts(job_id: str,
                   ctx: RequestContext = Depends(get_context),
                   c: Container = Depends(get_container)) -> dict:
    """List ONLY the manifest-backed FINAL_REDLINE_PNG artifact references of the job's validated bundle
    (log_id + manifest path + sha256 + bytes + kind). 404 if no validated handoff has attached a bundle."""
    cp, store = ctx.tenant.value, _store_root(c)
    try:
        bundle = _open_job_bundle(store, cp, job_id)
    except _CONTRACT_ERRORS as exc:
        raise _to_http(exc)
    return {
        "bundle_id": bundle.bundle_id,
        "artifacts": [{"log_id": lid, "path": a["path"], "sha256": a.get("sha256"),
                       "bytes": a.get("bytes"), "kind": a.get("kind")}
                      for lid, a in bundle.final_artifacts()],
    }


@router.get("/jobs/{job_id}/artifacts/{artifact_path:path}")
def get_artifact(job_id: str, artifact_path: str,
                 ctx: RequestContext = Depends(get_context),
                 c: Container = Depends(get_container)) -> FileResponse:
    """Serve ONE proof artifact of the job's validated bundle, BY ITS MANIFEST PATH only. The consumer
    enforces the allowlist + traversal-safety + checksum contract: a path that is not a manifest-listed
    FINAL_REDLINE_PNG (or is unsafe) is denied. 404 if the artifact is not manifest-backed / not found."""
    cp, store = ctx.tenant.value, _store_root(c)
    try:
        bundle = _open_job_bundle(store, cp, job_id)
        desc = bundle.resolve_artifact(artifact_path, read_bytes=False)
    except _CONTRACT_ERRORS as exc:
        raise _to_http(exc)
    return FileResponse(str(bundle.bundle_root / desc["path"]), media_type=desc["content_type"])


# --------------------------------------------------------------------------- #
# Slice 4 — downstream status spine (KMZ safety / closeout / billing / export package): server-derived
# reads + safe server actions only. NO privileged closeout transitions (lock/approve/close/reject/reopen).
# --------------------------------------------------------------------------- #
def _server_cost_rule_set(settings) -> dict:
    """Load the deployment's versioned billing cost-rule set from SERVER config (never the client). The path
    is `product_billing_cost_rules_path` (env TL2_PRODUCT_BILLING_COST_RULES); rates live in deployment data,
    never baked in code and never trusted from a request. Structural validation is the billing contract's."""
    path = settings.product_billing_cost_rules_path
    if not path:
        raise HTTPException(status_code=400, detail="billing cost rules are not configured")
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise HTTPException(status_code=400, detail="billing cost rules are not loadable")


@router.get("/jobs/{job_id}/kmz-export")
def get_kmz_export(job_id: str,
                   ctx: RequestContext = Depends(get_context),
                   c: Container = Depends(get_container)) -> dict:
    """Evaluate KMZ/KML geometry-export SAFETY for the job's approved redline output (READ-ONLY; persists
    nothing). Today's real (sheet/station/pixel) manifests return BLOCKED[UNSUPPORTED_PIXEL_ONLY] — the
    system abstains rather than fake coordinates. 404 if the job is missing."""
    cp, store = ctx.tenant.value, _store_root(c)
    try:
        return evaluate_export(store, cp, job_id)
    except _CONTRACT_ERRORS as exc:
        raise _to_http(exc)


@router.get("/jobs/{job_id}/kmz-export/download")
def download_kmz_export(job_id: str,
                        ctx: RequestContext = Depends(get_context),
                        c: Container = Depends(get_container)) -> Response:
    """Serve the job's redline KMZ as a downloadable application/vnd.google-earth.kmz file — ONLY when the
    redline manifest carries VERIFIED geospatial geometry (EXPORTABLE). Today's real (sheet/station/pixel)
    redline manifests have no coordinates, so this is honestly 409 with the named blocker (e.g.
    UNSUPPORTED_PIXEL_ONLY) — never a faked KMZ. 404 if the job is missing."""
    cp, store = ctx.tenant.value, _store_root(c)
    try:
        record = evaluate_export(store, cp, job_id)
    except _CONTRACT_ERRORS as exc:
        raise _to_http(exc)
    if record.get("status") != KMZ_EXPORTABLE or not record.get("kml"):
        codes = ", ".join(sorted({b["code"] for b in record.get("blockers", [])})) or "NOT_EXPORTABLE"
        raise HTTPException(status_code=409, detail="kmz export not available (%s)" % codes)
    data = build_kmz_bytes(record["kml"])
    return Response(content=data, media_type=KMZ_MEDIA_TYPE,
                    headers={"Content-Disposition": 'attachment; filename="redline_export.kmz"'})


@router.post("/jobs/{job_id}/closeout/evaluate")
def evaluate_closeout_route(job_id: str,
                            ctx: RequestContext = Depends(get_context),
                            c: Container = Depends(get_container)) -> dict:
    """Evaluate/refresh the job's ONE server-authoritative closeout status from trusted contracts (creates the
    record on first call). NOT a privileged transition — no lock/approve/close/reject/reopen here. 404 if the
    job is missing; 409 if the closeout is CLOSED (terminal)."""
    cp, store, now = ctx.tenant.value, _store_root(c), _now()
    try:
        try:
            load_closeout_review(store, cp, job_id)
        except CloseoutNotFoundError:
            create_closeout_review(store, cp, job_id, at=now, by=ctx.session_id)   # idempotent init
        return evaluate_closeout(store, cp, job_id, at=now, by=ctx.session_id)
    except _CONTRACT_ERRORS as exc:
        raise _to_http(exc)


@router.get("/jobs/{job_id}/closeout")
def get_closeout(job_id: str,
                 ctx: RequestContext = Depends(get_context),
                 c: Container = Depends(get_container)) -> dict:
    """Read the job's closeout_review record + the derived summary (the single value all readiness UI should
    render). 404 if no closeout_review has been evaluated yet."""
    cp, store = ctx.tenant.value, _store_root(c)
    try:
        record = load_closeout_review(store, cp, job_id)
    except _CONTRACT_ERRORS as exc:
        raise _to_http(exc)
    return {**record, "summary": closeout_summary(record)}


@router.post("/jobs/{job_id}/billing/compute")
def compute_billing_route(job_id: str,
                          ctx: RequestContext = Depends(get_context),
                          c: Container = Depends(get_container)) -> dict:
    """Compute the job's ONE server-authoritative billing summary from TRUSTED product state + the SERVER
    cost-rule set (creates the record on first call). The client supplies NO rates and NO itemized lines —
    billing is derived entirely server-side. 404 if the job is missing; 400 if cost rules are not
    configured/loadable/valid."""
    cp, store, now = ctx.tenant.value, _store_root(c), _now()
    cost_rule_set = _server_cost_rule_set(c.settings)       # server-sourced; never client-supplied
    try:
        try:
            load_billing_summary(store, cp, job_id)
        except BillingSummaryNotFoundError:
            create_billing_summary(store, cp, job_id, at=now, by=ctx.session_id)   # idempotent init
        return compute_billing_summary(store, cp, job_id, cost_rule_set=cost_rule_set,
                                       at=now, by=ctx.session_id)
    except _CONTRACT_ERRORS as exc:
        raise _to_http(exc)


@router.get("/jobs/{job_id}/billing")
def get_billing(job_id: str,
                ctx: RequestContext = Depends(get_context),
                c: Container = Depends(get_container)) -> dict:
    """Read the job's billing_summary record + the derived view. 404 if none has been computed yet."""
    cp, store = ctx.tenant.value, _store_root(c)
    try:
        record = load_billing_summary(store, cp, job_id)
    except _CONTRACT_ERRORS as exc:
        raise _to_http(exc)
    return {**record, "view": billing_summary_view(record)}


@router.get("/jobs/{job_id}/operator-pricing")
def get_operator_pricing(job_id: str,
                         ctx: RequestContext = Depends(get_context),
                         c: Container = Depends(get_container)) -> dict:
    """Read the job's OPERATOR-ENTERED pricing + the SERVER footage quantity + computed totals. This is the
    operator's own provisional rate table (provenance OPERATOR_ENTERED_UNVERIFIED + disclaimer), DISTINCT
    from the server-authoritative billing_summary — dollars are the operator's entered rates, never a
    configured rate sheet, never invented. Returns a blank table (no rates) when nothing is saved. 404 if the
    job is missing."""
    cp, store = ctx.tenant.value, _store_root(c)
    try:
        return pricing_view(store, cp, job_id)
    except _CONTRACT_ERRORS as exc:
        raise _to_http(exc)


@router.post("/jobs/{job_id}/operator-pricing")
def put_operator_pricing(job_id: str, req: OperatorPricingUpdate,
                         ctx: RequestContext = Depends(get_context),
                         c: Container = Depends(get_container)) -> dict:
    """Save the operator-entered cost-per-foot + exception rows for one job, then return the recomputed view.
    Blank rates are allowed and stay blank (NO invented default); a negative/non-numeric amount is a 400.
    Quantities are NOT accepted from the client — footage comes from the server. 404 if the job is missing."""
    cp, store = ctx.tenant.value, _store_root(c)
    try:
        save_job_pricing(store, cp, job_id,
                         cost_per_foot=req.cost_per_foot,
                         exceptions=[e.model_dump() for e in req.exceptions],
                         at=_now(), by=ctx.session_id)
        return pricing_view(store, cp, job_id)
    except _CONTRACT_ERRORS as exc:
        raise _to_http(exc)


@router.post("/jobs/{job_id}/export-package/assemble")
def assemble_export_package_route(job_id: str,
                                  ctx: RequestContext = Depends(get_context),
                                  c: Container = Depends(get_container)) -> dict:
    """Assemble the job's export-package DESCRIPTOR (a manifest-of-references) from trusted outputs (creates
    the record on first call). NO PDF/HTML/binary/export file is generated; billing is included by snapshot
    reference only. Closeout controls readiness/finality — there is no package-approve action. 404 if the job
    is missing."""
    cp, store, now = ctx.tenant.value, _store_root(c), _now()
    try:
        try:
            load_export_package(store, cp, job_id)
        except ExportPackageNotFoundError:
            create_export_package(store, cp, job_id, at=now, by=ctx.session_id)    # idempotent init
        return assemble_export_package(store, cp, job_id, at=now, by=ctx.session_id)
    except _CONTRACT_ERRORS as exc:
        raise _to_http(exc)


@router.get("/jobs/{job_id}/export-package")
def get_export_package(job_id: str,
                       ctx: RequestContext = Depends(get_context),
                       c: Container = Depends(get_container)) -> dict:
    """Read the job's export_package descriptor record + the derived view (included/omitted sections,
    blockers, content hash). 404 if none has been assembled yet."""
    cp, store = ctx.tenant.value, _store_root(c)
    try:
        record = load_export_package(store, cp, job_id)
    except _CONTRACT_ERRORS as exc:
        raise _to_http(exc)
    return {**record, "view": export_package_view(record)}


@router.get("/jobs/{job_id}/export-package/download")
def download_export_package(job_id: str,
                            ctx: RequestContext = Depends(get_context),
                            c: Container = Depends(get_container)) -> Response:
    """Stream the job's DOWNLOADABLE closeout export bundle (a real .zip: the redline manifest + the
    sha256-verified FINAL_REDLINE_PNG bytes + closeout/export/KMZ status JSON + reviewed-bore-log metadata,
    and a valid KMZ only when genuinely geospatially exportable). Assembled from EXISTING trusted output —
    nothing rendered or faked. 409 if the job has no validated redline bundle yet; 404 if the job is
    missing."""
    cp, store = ctx.tenant.value, _store_root(c)
    ok, gate_code = export_gate(store, cp, job_id)
    if not ok:
        raise HTTPException(status_code=409,
                            detail="redline REVIEW not resolved (%s); accept or correct it before downloading"
                                   % gate_code)
    try:
        data, filename = build_export_zip(store, cp, job_id)
    except NoRedlineBundleError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except _CONTRACT_ERRORS as exc:
        raise _to_http(exc)
    return Response(content=data, media_type=EXPORT_ZIP_MEDIA_TYPE,
                    headers={"Content-Disposition": 'attachment; filename="%s"' % filename})


@router.get("/jobs/{job_id}/export-package/pdf")
def download_closeout_pdf(job_id: str,
                          ctx: RequestContext = Depends(get_context),
                          c: Container = Depends(get_container)) -> Response:
    """Stream the job's server-rendered closeout PACKET PDF (a real PDF: FieldRoute header, job/closeout
    summary, deliverable QUANTITIES, the sha256-verified FINAL_REDLINE_PNG evidence EMBEDDED as image
    XObjects, artifact metadata, reviewed-bore-log + export-package section summary, honest KMZ status, and
    a billing section that shows DOLLARS only when billing is server-COMPUTED from configured cost rules —
    else 'omitted, no server cost rules configured'). Rendered from EXISTING trusted output — nothing
    faked. 409 (specific not-ready) if the job has no validated redline bundle yet; 404 if the job is
    missing."""
    cp, store = ctx.tenant.value, _store_root(c)
    ok, gate_code = export_gate(store, cp, job_id)
    if not ok:
        raise HTTPException(status_code=409,
                            detail="redline REVIEW not resolved (%s); accept or correct it before downloading"
                                   % gate_code)
    try:
        data, filename = build_closeout_pdf(store, cp, job_id)
    except NoCloseoutPdfError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except _CONTRACT_ERRORS as exc:
        raise _to_http(exc)
    return Response(content=data, media_type=PDF_MEDIA_TYPE,
                    headers={"Content-Disposition": 'attachment; filename="%s"' % filename})


@router.get("/jobs/{job_id}/gis-route")
def get_gis_route(job_id: str,
                  ctx: RequestContext = Depends(get_context),
                  c: Container = Depends(get_container)) -> dict:
    """Read-only: parse the job's uploaded GIS_ROUTE (.kmz/.kml) into REAL WGS84 geometry (LineString /
    Point / Polygon) + a bbox, so the workspace Map can show route CONTEXT from the operator's own upload.
    Dialect-free; reads ONLY the stored GIS_ROUTE upload; invents nothing (no geocoding / no street-name
    synthesis / no snapping). Honest NAMED states when there is no GIS_ROUTE upload, the file is missing or
    unparseable, or no coordinates are present. 404 if the job is missing."""
    cp, store = ctx.tenant.value, _store_root(c)
    try:
        return load_job_gis_route(store, cp, job_id)
    except _CONTRACT_ERRORS as exc:
        raise _to_http(exc)


@router.get("/jobs/{job_id}/gis-route/download")
def download_gis_route(job_id: str,
                       ctx: RequestContext = Depends(get_context),
                       c: Container = Depends(get_container)) -> Response:
    """Serve the job's UPLOADED route as a downloadable KMZ (real WGS84 geometry + verbatim names / street
    labels) to open in Google Earth. This is the operator's uploaded DESIGN route, NOT redline output —
    redlines are pixel-only and are NOT in this KMZ (the redline-KMZ status lives at kmz-export/download,
    which honestly blocks pixel-only). 409 honest state when the job has no usable GIS_ROUTE; 404 if the
    job is missing. Invents nothing."""
    cp, store = ctx.tenant.value, _store_root(c)
    try:
        out = load_job_route_kmz(store, cp, job_id)
    except _CONTRACT_ERRORS as exc:
        raise _to_http(exc)
    if not out.get("present") or not out.get("kmz_bytes"):
        raise HTTPException(status_code=409,
                            detail="route export not available (%s)" % (out.get("reason") or "NO_ROUTE"))
    fname = out.get("filename") or "route.kmz"          # derived from the customer file, Content-Disposition-safe
    return Response(content=out["kmz_bytes"], media_type=KMZ_MEDIA_TYPE,
                    headers={"Content-Disposition": 'attachment; filename="%s"' % fname})


# --------------------------------------------------------------------------- #
# Slice C — uploaded-corpus engine-handoff READINESS (read-only; renders nothing; creates nothing).
# --------------------------------------------------------------------------- #
@router.get("/jobs/{job_id}/engine-handoff")
def get_engine_handoff_readiness(job_id: str,
                                 ctx: RequestContext = Depends(get_context),
                                 c: Container = Depends(get_container)) -> dict:
    """Read-only uploaded-corpus engine-handoff READINESS check: reports whether the job's uploaded inputs
    (a PLAN_PDF + an engine-ready reviewed_bore_log) are present, and the exact named blockers. Always
    BLOCKED / runnable:false in this slice — the uploaded-corpus engine adapter is not implemented; this
    runs no engine, renders nothing, and creates no artifacts/slots/bundles. 404 if the job is missing."""
    cp, store = ctx.tenant.value, _store_root(c)
    try:
        return evaluate_engine_handoff_readiness(store, cp, job_id)
    except _CONTRACT_ERRORS as exc:
        raise _to_http(exc)


# --------------------------------------------------------------------------- #
# Recognized-corpus AUTOMATIC handoff (NO manual source-anchor clicks). Narrow + honest: fires only for a
# POSITIVELY-recognized known corpus; serves the EXISTING deterministic engine render. Unknown -> blocked.
# --------------------------------------------------------------------------- #
@router.get("/jobs/{job_id}/recognized-corpus-handoff")
def get_recognized_corpus_handoff(job_id: str,
                                  ctx: RequestContext = Depends(get_context),
                                  c: Container = Depends(get_container)) -> dict:
    """Read-only: is this job's RECOGNIZED uploaded corpus eligible for an AUTOMATIC deterministic redline
    (no manual point-clicking)? RUNNABLE only when the uploaded PLAN_PDF is positively recognized (exact
    sha256) as a known corpus AND an engine-ready reviewed_bore_log's source BORE_LOG maps to a DRAWN
    deterministic log with committed render artifacts; otherwise BLOCKED with named blockers
    (UPLOADED_CORPUS_NOT_RECOGNIZED / BORE_LOG_NOT_MAPPED_TO_DETERMINISTIC_LOG / ...). Renders/creates
    nothing. 404 if the job is missing."""
    cp, store = ctx.tenant.value, _store_root(c)
    registry = load_registry(c.settings.recognized_corpus_registry_path)
    try:
        return evaluate_recognized_corpus_handoff(store, cp, job_id, registry=registry)
    except _CONTRACT_ERRORS as exc:
        raise _to_http(exc)


@router.post("/jobs/{job_id}/recognized-corpus-handoff/render")
def render_recognized_corpus_handoff_route(job_id: str,
                                           ctx: RequestContext = Depends(get_context),
                                           c: Container = Depends(get_container)) -> dict:
    """Run the recognized-corpus auto-handoff: if RUNNABLE, publish the EXISTING deterministic engine render
    PNG(s) for the recognized log as a job-local FINAL_REDLINE_PNG bundle (bundle_origin
    DETERMINISTIC_RECOGNIZED_CORPUS — engine-derived, NOT human-clicked, NOT arbitrary upload support) and
    set the job's redline_manifest + artifact_bundle slots via the existing handoff. 409 if not
    recognized/runnable; 404 if the job is missing. Does NOT touch the deterministic 50/58 frontier (a
    separate job-local bundle). Idempotent for identical recognized content."""
    cp, store = ctx.tenant.value, _store_root(c)
    registry = load_registry(c.settings.recognized_corpus_registry_path)
    try:
        return render_recognized_corpus_handoff(store, cp, job_id, registry=registry, at=_now(), by=ctx.session_id)
    except RecognizedCorpusError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except _CONTRACT_ERRORS as exc:
        raise _to_http(exc)


# --------------------------------------------------------------------------- #
# Uploaded-corpus ENGINE handoff (NO manual clicks, NO recognized-corpus replay). Runs the shipped engine on
# the job's OWN uploaded plan + reviewed bore-log; renders the redline from the plan's drawn geometry, or
# returns the engine's named blocker. Name-free (dialect chosen by pattern). Separate job-local bundle.
# --------------------------------------------------------------------------- #
@router.get("/jobs/{job_id}/uploaded-corpus-engine-handoff")
def get_uploaded_corpus_engine_handoff(job_id: str,
                                       ctx: RequestContext = Depends(get_context),
                                       c: Container = Depends(get_container)) -> dict:
    """Read-only candidate report: can the ENGINE place a redline for this job's uploaded corpus? Resolves
    the uploaded PLAN_PDF + an engine-ready reviewed_bore_log's source BORE_LOG, runs the engine, and reports
    a drawable candidate (RUNNABLE) or a named blocker (BLOCKED) — NO_PLAN_PDF_UPLOAD /
    NO_ENGINE_READY_REVIEWED_BORE_LOG / NO_PLAN_DIALECT_RECOGNIZED / ENGINE_ABSTAINED (+ the engine's own
    reason). Mutates/creates nothing. 404 if the job is missing."""
    cp, store = ctx.tenant.value, _store_root(c)
    try:
        return evaluate_uploaded_corpus_engine_handoff(store, cp, job_id)
    except _CONTRACT_ERRORS as exc:
        raise _to_http(exc)


@router.post("/jobs/{job_id}/uploaded-corpus-engine-handoff/render")
def render_uploaded_corpus_engine_handoff_route(job_id: str,
                                                ctx: RequestContext = Depends(get_context),
                                                c: Container = Depends(get_container)) -> dict:
    """Run the uploaded-corpus engine handoff: if the engine places a drawable candidate, render the redline
    stroke along the plan's DRAWN route and publish it as a job-local FINAL_REDLINE_PNG bundle (bundle_origin
    UPLOADED_CORPUS_ENGINE; REVIEW => dashed/human-adjustable, AUTO => solid/deterministic) and set the job's
    redline_manifest + artifact_bundle slots. 409 if not runnable (engine abstained / inputs missing); 404 if
    the job is missing. Does NOT touch the deterministic 50/58 frontier (a separate job-local bundle).
    Idempotent for identical content."""
    cp, store = ctx.tenant.value, _store_root(c)
    try:
        return render_uploaded_corpus_engine_handoff(store, cp, job_id, at=_now(), by=ctx.session_id)
    except UploadedCorpusEngineError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except _CONTRACT_ERRORS as exc:
        raise _to_http(exc)


# --------------------------------------------------------------------------- #
# Terminus evidence (G3 — DISPLAY-only OBSERVER). Read-only source-backed per-bore endpoint evidence for the
# REVIEW flow: for each engine-ready reviewed bore-log, what the START/END bound to (a printed structure note)
# or the named missing-evidence blocker. Runs NO engine, renders nothing, sets no slot, advances no job,
# changes no placement/status/AUTO. A separate read path — never the placement orchestrator.
# --------------------------------------------------------------------------- #
@router.get("/jobs/{job_id}/terminus-evidence")
def get_terminus_evidence(job_id: str,
                          ctx: RequestContext = Depends(get_context),
                          c: Container = Depends(get_container)) -> dict:
    """Read-only DISPLAY of source-backed per-bore TERMINUS EVIDENCE (observer-only). For each engine-ready
    reviewed bore-log, resolves the job's stored PLAN_PDF + the bore-log source file and reports each
    endpoint's source_bound / source_type / station / sheet / printed text / named blocker / provenance —
    with honest named blockers when an input is missing. Changes NO placement/status/AUTO, runs no engine,
    renders nothing, sets no slot. 404 if the job is missing (incl. cross-tenant)."""
    cp, store = ctx.tenant.value, _store_root(c)
    try:
        return terminus_evidence_report(store, cp, job_id)
    except _CONTRACT_ERRORS as exc:
        raise _to_http(exc)


# --------------------------------------------------------------------------- #
# Phase 6 — REVIEW acceptance lane: the engine generates a source-supported REVIEW redline candidate; a
# human ACCEPTS or REJECTS it (never draws geometry). REVIEW is a first-class product output, never AUTO.
# --------------------------------------------------------------------------- #
@router.post("/jobs/{job_id}/review-candidates/generate")
def generate_review_candidate_route(job_id: str,
                                    ctx: RequestContext = Depends(get_context),
                                    c: Container = Depends(get_container)) -> dict:
    """Ask the uploaded-corpus engine for this job's redline candidate and record its honest tier: a REVIEW
    candidate is RENDERED (real dashed FINAL_REDLINE_PNG) and held as REVIEW_CANDIDATE for human
    accept/reject; an AUTO placement is rendered deterministically (no acceptance gate); an engine ABSTAIN
    is recorded ABSTAINED with its named blocker (renders nothing); missing inputs report blockers with no
    record. Never promotes REVIEW to AUTO. Idempotent (an existing decision is preserved). 409 if a runnable
    candidate fails to render; 404 if the job is missing."""
    cp, store = ctx.tenant.value, _store_root(c)
    try:
        return generate_review_candidate(store, cp, job_id, at=_now(), by=ctx.session_id,
                                         uploaded_corpus_auto_optin=c.settings.uploaded_corpus_auto_optin)
    except UploadedCorpusEngineError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except _CONTRACT_ERRORS as exc:
        raise _to_http(exc)


@router.get("/jobs/{job_id}/review-candidates")
def list_review_candidates_route(job_id: str,
                                 ctx: RequestContext = Depends(get_context),
                                 c: Container = Depends(get_container)) -> dict:
    """List the tenant's engine REVIEW-acceptance records for one job (tenant + job scoped; [] if none).
    Read-only — each record carries its tier/status, evidence, caveats, why-not-AUTO, and bundle refs."""
    try:
        return {"review_candidates": list_review_candidates(_store_root(c), ctx.tenant.value, job_id)}
    except _CONTRACT_ERRORS as exc:
        raise _to_http(exc)


@router.get("/jobs/{job_id}/review-candidates/{candidate_id}")
def get_review_candidate_route(job_id: str, candidate_id: str,
                              ctx: RequestContext = Depends(get_context),
                              c: Container = Depends(get_container)) -> dict:
    """Load one REVIEW-acceptance record (evidence + caveats + provenance + bundle refs) in the tenant's
    scope. 404 if the candidate is missing."""
    try:
        return load_review_candidate(_store_root(c), ctx.tenant.value, job_id, candidate_id)
    except _CONTRACT_ERRORS as exc:
        raise _to_http(exc)


@router.post("/jobs/{job_id}/review-candidates/{candidate_id}/accept")
def accept_review_candidate_route(job_id: str, candidate_id: str,
                                  ctx: RequestContext = Depends(get_context),
                                  c: Container = Depends(get_container)) -> dict:
    """ACCEPT the engine-generated REVIEW candidate as-is (no geometry drawn): REVIEW_CANDIDATE ->
    REVIEW_ACCEPTED, provenance ENGINE_GENERATED_HUMAN_ACCEPTED_REVIEW (never DETERMINISTIC_AUTO). The
    rendered FINAL_REDLINE_PNG artifacts are unchanged. Idempotent on an already-accepted candidate; 409 if
    it was rejected/abstained; 404 if the candidate is missing."""
    cp, store = ctx.tenant.value, _store_root(c)
    try:
        return accept_review_candidate(store, cp, job_id, candidate_id, at=_now(), by=ctx.session_id)
    except _CONTRACT_ERRORS as exc:
        raise _to_http(exc)


@router.post("/jobs/{job_id}/review-candidates/{candidate_id}/reject")
def reject_review_candidate_route(job_id: str, candidate_id: str, req: ReviewReject,
                                  ctx: RequestContext = Depends(get_context),
                                  c: Container = Depends(get_container)) -> dict:
    """REJECT the engine-generated REVIEW candidate (needs correction) with a required reason:
    REVIEW_CANDIDATE -> REVIEW_REJECTED. A rejected candidate stays rejected (can never be silently
    accepted). Idempotent on an already-rejected candidate; 409 if it was accepted/abstained; 400 if the
    reason is empty; 404 if the candidate is missing."""
    cp, store = ctx.tenant.value, _store_root(c)
    try:
        return reject_review_candidate(store, cp, job_id, candidate_id, reason=req.reason,
                                       at=_now(), by=ctx.session_id)
    except _CONTRACT_ERRORS as exc:
        raise _to_http(exc)


# --------------------------------------------------------------------------- #
# Phase 9 — product workflow orchestrator: choose among the 3 redline paths (recognized deterministic ->
# uploaded REVIEW/AUTO -> abstain) IN ORDER, then assemble the closeout/export package. Drives the EXISTING
# contracts read-only; runs no engine here; never fakes AUTO / coordinates.
# --------------------------------------------------------------------------- #
def _optional_cost_rule_set(settings) -> Optional[dict]:
    """Load the server billing cost-rule set if configured + loadable, else None (billing is OPTIONAL in the
    workflow — it never blocks the export package)."""
    path = settings.product_billing_cost_rules_path
    if not path:
        return None
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


@router.post("/jobs/{job_id}/workflow/redline")
def run_product_redline_route(job_id: str,
                              ctx: RequestContext = Depends(get_context),
                              c: Container = Depends(get_container)) -> dict:
    """Run the correct redline path for the job's uploaded package, IN ORDER: a recognized deterministic
    package serves the EXISTING committed engine render (real PNGs, DETERMINISTIC_AUTO); else a supported
    uploaded package produces an engine REVIEW candidate (never faked AUTO); else ABSTAIN with the SPECIFIC
    recognition + engine reasons (never a bare ENGINE_ABSTAINED). A successful render advances the job to
    PLACED. 409 if the recognition/engine render fails or the job is FAILED; 404 if the job is missing."""
    cp, store = ctx.tenant.value, _store_root(c)
    registry = load_registry(c.settings.recognized_corpus_registry_path)
    try:
        return run_product_redline(store, cp, job_id, registry=registry, at=_now(), by=ctx.session_id,
                                   uploaded_corpus_auto_optin=c.settings.uploaded_corpus_auto_optin)
    except (RecognizedCorpusError, UploadedCorpusEngineError, ProductWorkflowError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except _CONTRACT_ERRORS as exc:
        raise _to_http(exc)


@router.post("/jobs/{job_id}/workflow/closeout")
def assemble_closeout_package_route(job_id: str,
                                    ctx: RequestContext = Depends(get_context),
                                    c: Container = Depends(get_container)) -> dict:
    """Drive the closeout/export chain for a job whose redline is placed: gate on REVIEW acceptance, advance
    to CLOSEOUT_REVIEW, evaluate the closeout + KMZ-export safety, optionally compute billing (only when
    server cost-rules are configured), and assemble the export-package descriptor. Returns a unified summary
    ({assembled, closeout_status, export_status, kmz_status, ...}). 409 if a REVIEW candidate is not accepted
    or the job is FAILED; 404 if the job is missing."""
    cp, store = ctx.tenant.value, _store_root(c)
    try:
        return assemble_closeout_package(store, cp, job_id, at=_now(), by=ctx.session_id,
                                         cost_rule_set=_optional_cost_rule_set(c.settings))
    except ProductWorkflowError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except _CONTRACT_ERRORS as exc:
        raise _to_http(exc)


# --------------------------------------------------------------------------- #
# M2 — human-confirmed source-anchor route geometry (record + validate ONLY; renders nothing).
# --------------------------------------------------------------------------- #
def _plan_pdf_path(store, customer_project_id, job_id, plan_upload_id, job):
    """Absolute path to an uploaded PLAN_PDF's file, or None if the id is missing / not a PLAN_PDF / the
    file is absent. Read-only resolution; opens nothing."""
    upload = next((u for u in job.get("uploads", []) if u.get("upload_id") == plan_upload_id), None)
    if upload is None or upload.get("kind") != PLAN_PDF_KIND:
        return None
    path = job_dir(store, customer_project_id, job_id) / upload.get("stored_path", "")
    return path if path.is_file() else None


def _resolve_plan_page_bounds(store, customer_project_id, job_id, plan_upload_id, page_number, job):
    """Resolve the DISPLAY-space page bounds of the uploaded PLAN_PDF page for source-anchor renderability
    validation. Read-only: opens the PDF to read page geometry only — rasterizes nothing, draws nothing,
    writes nothing. Returns (x0,y0,x1,y1), or None when the upload/page is unresolvable (the contract maps
    a None for an otherwise-valid plan upload to PAGE_NOT_RESOLVABLE)."""
    path = _plan_pdf_path(store, customer_project_id, job_id, plan_upload_id, job)
    if path is None or not isinstance(page_number, int) or page_number < 1:
        return None
    plan = PlanPdf(str(path))
    try:
        if page_number > plan.page_count:
            return None
        return plan.page_rect_bounds(page_number, 0)        # display space matching the raster + render_clip
    finally:
        plan.close()


@router.post("/jobs/{job_id}/source-anchors")
def create_source_anchor_route(job_id: str, req: SourceAnchorCreate,
                               ctx: RequestContext = Depends(get_context),
                               c: Container = Depends(get_container)) -> dict:
    """Create + validate a HUMAN-confirmed source-anchor (ordered PDF display-space control points) for a
    bore route on an uploaded PLAN_PDF page. Records the geometry and returns its renderability state +
    named blockers (VALIDATED or REJECTED) — it RENDERS NOTHING, runs no engine, and creates no
    artifacts/slots/bundles. 404 if the job is missing; 409 if the source_anchor id already exists; 400 on
    an invalid id / malformed control point."""
    cp, store = ctx.tenant.value, _store_root(c)
    try:
        load_source_anchor(store, cp, job_id, req.source_anchor_id)
    except SourceAnchorNotFoundError:
        pass                                                # expected: not created yet
    except _CONTRACT_ERRORS as exc:                         # e.g. invalid source_anchor id
        raise _to_http(exc)
    else:
        raise HTTPException(status_code=409, detail="source_anchor already exists")
    try:
        job = load_job(store, cp, job_id)                   # 404 (incl. cross-tenant) before PDF resolution
    except _CONTRACT_ERRORS as exc:
        raise _to_http(exc)
    bounds = _resolve_plan_page_bounds(store, cp, job_id, req.plan_upload_id, req.page_number, job)
    try:
        return create_source_anchor(
            store, cp, job_id,
            source_anchor_id=req.source_anchor_id,
            plan_upload_id=req.plan_upload_id,
            reviewed_bore_log_id=req.reviewed_bore_log_id,
            page_number=req.page_number,
            control_points=[{"x": p.x, "y": p.y} for p in req.control_points],
            group_id=req.group_id,
            row_ids=req.row_ids,
            start_identity=(req.start_identity.model_dump() if req.start_identity else None),
            end_identity=(req.end_identity.model_dump() if req.end_identity else None),
            notes=req.notes, page_bounds=bounds, at=_now(), by=ctx.session_id)
    except _CONTRACT_ERRORS as exc:
        raise _to_http(exc)


@router.get("/jobs/{job_id}/source-anchors")
def list_source_anchors_route(job_id: str,
                              ctx: RequestContext = Depends(get_context),
                              c: Container = Depends(get_container)) -> dict:
    """List the tenant's source-anchors for one job (tenant + job scoped; [] if none). Read-only."""
    try:
        return {"source_anchors": list_source_anchors(_store_root(c), ctx.tenant.value, job_id)}
    except _CONTRACT_ERRORS as exc:
        raise _to_http(exc)


@router.get("/jobs/{job_id}/source-anchors/{source_anchor_id}")
def get_source_anchor_route(job_id: str, source_anchor_id: str,
                            ctx: RequestContext = Depends(get_context),
                            c: Container = Depends(get_container)) -> dict:
    """Load one source-anchor record in the tenant's scope (404 if none)."""
    try:
        return load_source_anchor(_store_root(c), ctx.tenant.value, job_id, source_anchor_id)
    except _CONTRACT_ERRORS as exc:
        raise _to_http(exc)


@router.post("/jobs/{job_id}/source-anchors/{source_anchor_id}/render")
def render_source_anchor_route(job_id: str, source_anchor_id: str,
                               ctx: RequestContext = Depends(get_context),
                               c: Container = Depends(get_container)) -> dict:
    """Render the job's VALIDATED human-confirmed source anchors into a real `mock_example:false` redline
    bundle — dashed REVIEW strokes drawn ONLY from the stored control points — and set the job's
    redline_manifest + artifact_bundle slots via the existing handoff. The requested anchor must be
    VALIDATED/renderable (409 otherwise); 404 if the job/anchor is missing. Draws nothing automatic (no
    geometry inference, no station solving, no engine) and does NOT touch the deterministic 50/58 frontier.
    Returns a bundle/artifact summary; idempotent for identical content."""
    cp, store = ctx.tenant.value, _store_root(c)
    try:
        return render_job_source_anchors(store, cp, job_id, source_anchor_id, at=_now(), by=ctx.session_id)
    except _CONTRACT_ERRORS as exc:
        raise _to_http(exc)


# --------------------------------------------------------------------------- #
# M2 — uploaded PLAN_PDF page DISPLAY (read-only page metadata + page raster for source-anchor capture).
# Rasterizes the uploaded plan AS-IS for the browser — NO redline drawn, NO artifact/slot/bundle created.
# --------------------------------------------------------------------------- #
_PLAN_RASTER_ZOOM = 2.0                 # default browser raster (unchanged: existing behavior byte-identical)
# Bounds for an on-demand HIGHER-DPI raster (precision source-anchor placement). A dense plan sheet is
# unreadable when a 2x raster is merely CSS-upscaled, so the viewer may request a crisper raster; the zoom
# is capped and the longest raster edge is bounded so a large sheet never yields a monster PNG. This is the
# fitz PAGE raster (the plan AS-IS) — NOT the redline renderer, not engine truth.
_PLAN_RASTER_ZOOM_MAX = 4.0
_PLAN_RASTER_MAX_PIXELS = 8000


def _require_plan_upload(job, plan_upload_id):
    """Return the named PLAN_PDF upload dict, or raise HTTPException (404 missing / 400 wrong kind)."""
    upload = next((u for u in job.get("uploads", []) if u.get("upload_id") == plan_upload_id), None)
    if upload is None:
        raise HTTPException(status_code=404, detail="no upload %r in this job" % (plan_upload_id,))
    if upload.get("kind") != PLAN_PDF_KIND:
        raise HTTPException(status_code=400, detail="upload %r is not a PLAN_PDF" % (plan_upload_id,))
    return upload


def _bounded_raster_zoom(requested, bounds) -> float:
    """Clamp a client-requested plan-raster zoom into a safe range (display-only; never errors the viewer).
    Non-finite / non-positive falls back to the default; the zoom is capped at ``_PLAN_RASTER_ZOOM_MAX`` and
    further reduced so the longest raster edge stays within ``_PLAN_RASTER_MAX_PIXELS`` (a big sheet never
    yields a monster PNG)."""
    z = float(requested)
    if not math.isfinite(z) or z <= 0:
        z = _PLAN_RASTER_ZOOM
    z = min(z, _PLAN_RASTER_ZOOM_MAX)
    if bounds is not None:
        x0, y0, x1, y1 = bounds
        longest = max(x1 - x0, y1 - y0)
        if longest > 0:
            z = min(z, _PLAN_RASTER_MAX_PIXELS / longest)
    return max(1.0, z)


@router.get("/jobs/{job_id}/plan-pages/{plan_upload_id}")
def get_plan_page_metadata(job_id: str, plan_upload_id: str,
                           ctx: RequestContext = Depends(get_context),
                           c: Container = Depends(get_container)) -> dict:
    """Read-only page metadata for an uploaded PLAN_PDF: page_count + per-page DISPLAY-space bounds (the
    coordinate space source-anchor control points use) + width/height + the raster zoom/pixel size, AND the
    page's printed CONSTRUCTION-SHEET label/number/type (from the title block). The label distinction lets
    the web resolve a bore-log sheet ref (e.g. "7" = the plan sheet "7 OF 30") to the correct PDF page
    instead of treating the sheet number as a raw PDF page index, and prefer route plan sheets over
    cover/typical-detail pages. ``page_number`` stays a 1-based PDF page index everywhere. 404 if the upload
    is missing, 400 if it is not a PLAN_PDF. Opens the PDF read-only (no rasterization here); creates no
    artifacts/slots."""
    cp, store = ctx.tenant.value, _store_root(c)
    try:
        job = load_job(store, cp, job_id)
    except _CONTRACT_ERRORS as exc:
        raise _to_http(exc)
    upload = _require_plan_upload(job, plan_upload_id)
    path = job_dir(store, cp, job_id) / upload.get("stored_path", "")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="plan file is not available")
    plan = PlanPdf(str(path))
    try:
        index = build_sheet_index(plan)                     # title-block construction-sheet labels per page
        by_page = {p.pdf_page_number: p for p in index.pages}
        pages = []
        for n in range(1, plan.page_count + 1):
            bounds = plan.page_rect_bounds(n, 0)            # display space matching the raster + render_clip
            if bounds is None:
                continue
            x0, y0, x1, y1 = bounds
            w, h = x1 - x0, y1 - y0
            sp = by_page.get(n)
            pages.append({
                "page_number": n,                           # 1-based PDF page index (NOT a construction sheet)
                "bounds": {"x0": x0, "y0": y0, "x1": x1, "y1": y1},
                "width": w, "height": h,
                "zoom": _PLAN_RASTER_ZOOM,
                "raster_width": round(w * _PLAN_RASTER_ZOOM),
                "raster_height": round(h * _PLAN_RASTER_ZOOM),
                # Construction-sheet identity from the printed title block (null on cover/detail pages).
                "construction_sheet_number": sp.construction_sheet_number if sp else None,
                "sheet_total": sp.sheet_total if sp else None,
                "plan_sheet_label": sp.plan_sheet_label if sp else None,
                "sheet_type": sp.sheet_type if sp else SHEET_TYPE_OTHER,
                "is_plan_sheet": bool(sp and sp.is_plan_sheet),
            })
        return {"plan_upload_id": plan_upload_id, "page_count": plan.page_count,
                "plan_set_total": index.plan_set_total, "pages": pages}
    finally:
        plan.close()


@router.get("/jobs/{job_id}/plan-pages/{plan_upload_id}/{page_number}/raster")
def get_plan_page_raster(job_id: str, plan_upload_id: str, page_number: int,
                         zoom: float = _PLAN_RASTER_ZOOM,
                         ctx: RequestContext = Depends(get_context),
                         c: Container = Depends(get_container)) -> Response:
    """Read-only PNG raster of ONE uploaded PLAN_PDF page (the plan AS-IS — NO redline overlay), returned
    as image/png bytes for browser display. The optional ``zoom`` query param requests an on-demand
    higher-DPI raster for precision source-anchor placement on a dense sheet; it defaults to the standard
    browser zoom (so the default response is unchanged) and is clamped to a safe range (a large sheet never
    yields a monster PNG) — display-only, never the redline renderer. 404 if the upload/page is missing, 400
    if the upload is not a PLAN_PDF. Writes NO PNG to disk, creates no artifacts/slots/bundles, runs no
    engine."""
    cp, store = ctx.tenant.value, _store_root(c)
    try:
        job = load_job(store, cp, job_id)
    except _CONTRACT_ERRORS as exc:
        raise _to_http(exc)
    upload = _require_plan_upload(job, plan_upload_id)
    path = job_dir(store, cp, job_id) / upload.get("stored_path", "")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="plan file is not available")
    plan = PlanPdf(str(path))
    try:
        if page_number < 1 or page_number > plan.page_count:
            raise HTTPException(status_code=404, detail="page %r not in plan" % (page_number,))
        eff_zoom = _bounded_raster_zoom(zoom, plan.page_rect_bounds(page_number, 0))
        png = plan.render_page_png(page_number, 0, zoom=eff_zoom)
    finally:
        plan.close()
    if png is None:
        raise HTTPException(status_code=404, detail="page %r not resolvable" % (page_number,))
    return Response(content=png, media_type="image/png")
