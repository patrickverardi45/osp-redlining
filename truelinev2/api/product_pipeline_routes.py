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
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
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
from truelinev2.contracts.kmz_export import evaluate_export
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
from truelinev2.contracts.export_package import (
    ExportPackageError,
    ExportPackageNotFoundError,
    assemble_export_package,
    create_export_package,
    export_package_view,
    load_export_package,
)
from truelinev2.contracts.engine_handoff_readiness import evaluate_engine_handoff_readiness
from truelinev2.contracts.source_anchor import (
    PLAN_PDF_KIND,
    SourceAnchorError,
    SourceAnchorNotFoundError,
    create_source_anchor,
    list_source_anchors,
    load_source_anchor,
)
from truelinev2.ingest.pdf import PlanPdf

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
                        SourceAnchorNotFoundError)):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, (IllegalTransitionError, UploadsClosedError, HandoffStateError,
                        CloseoutStateError)):                           # state conflicts
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, (CrossProjectAccessError, IsolationError)):
        return HTTPException(status_code=403, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))   # invalid id / bad target / missing reason / ...


# Every contract-error base this router translates to HTTP via _to_http (which dispatches by the specific
# subclass). A non-contract error is left to propagate (a real 500 — never masked as a 400).
_CONTRACT_ERRORS = (CustomerProjectError, ProcessingJobError, UploadError, ExtractedRowError,
                    ReviewedBoreLogError, ManifestHandoffError, ConsumerError, CloseoutReviewError,
                    BillingSummaryError, ExportPackageError, SourceAnchorError, IsolationError)


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
# M2 — human-confirmed source-anchor route geometry (record + validate ONLY; renders nothing).
# --------------------------------------------------------------------------- #
def _resolve_plan_page_bounds(store, customer_project_id, job_id, plan_upload_id, page_number, job):
    """Resolve the DISPLAY-space page bounds of the uploaded PLAN_PDF page for source-anchor renderability
    validation. Read-only: opens the PDF to read page geometry only — rasterizes nothing, draws nothing,
    writes nothing. Returns (x0,y0,x1,y1), or None when the upload is missing / not a PLAN_PDF / its file
    or the page is unresolvable (the contract maps a None for an otherwise-valid plan upload to
    PAGE_NOT_RESOLVABLE)."""
    upload = next((u for u in job.get("uploads", []) if u.get("upload_id") == plan_upload_id), None)
    if upload is None or upload.get("kind") != PLAN_PDF_KIND:
        return None
    pdf_path = job_dir(store, customer_project_id, job_id) / upload.get("stored_path", "")
    if not pdf_path.is_file() or not isinstance(page_number, int) or page_number < 1:
        return None
    plan = PlanPdf(str(pdf_path))
    try:
        if page_number > plan.page_count:
            return None
        return plan.page_bounds_display(page_number, 0)     # offset 0 -> page_index = page_number - 1
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
