"""Local/staging generic source-backed READINESS + REVIEW-candidate routes (STAGING_REVIEW_CANDIDATE_PRODUCT_WIRING).

Thin, context-bearing routes that run the SHIPPED read-only readiness spine (span extractor -> endpoint binder ->
route verifier -> readiness classifier -> ``review_candidate``) on a tenant job's UPLOADED files, so a staging user
can upload a complete package and see honest results instead of developer-only harness output. Identity is the
VERIFIED ``X-TL-Tenant`` slug from the request context (``customer_project_id == ctx.tenant.value``) — never the URL
path or a request body. Mounted by create_app ONLY when settings.product_readiness_api_optin is True (DEFAULT OFF).

Distinct from the existing Phase-6 ``/review-candidates/*`` lane (the uploaded-corpus ENGINE handoff). This lane is
the SOURCE-BACKED readiness spine: it draws a REVIEW candidate overlay ONLY when the spine reports exactly
``READY_FOR_REVIEW_REDLINE`` (through the gated ``review_candidate.build_review_candidate``); every refusal writes
zero artifacts. It performs NO AUTO, NO final placement, and NO status promotion, sets no job output slot, and runs
no job lifecycle transition. All business logic lives in the read-only spine (harness), never here.

Endpoints (all tenant + job scoped):
  POST /jobs/{job_id}/review-readiness/run              — run the spine on the job's uploads; persist + return the
                                                          product-safe result (+ a REVIEW candidate overlay ONLY
                                                          when READY_FOR_REVIEW_REDLINE).
  GET  /jobs/{job_id}/review-readiness                  — read the last persisted result (404 if never run).
  GET  /jobs/{job_id}/review-readiness/artifacts/{path} — serve one persisted REVIEW-candidate PNG (path-safe).
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from truelinev2.api.container import Container
from truelinev2.api.deps import get_container, get_context
from truelinev2.context import IsolationError, RequestContext
from truelinev2.contracts.customer_project import (
    CrossProjectAccessError,
    CustomerProjectError,
    ProjectNotFoundError,
)
from truelinev2.contracts.processing_job import (
    JobNotFoundError,
    ProcessingJobError,
    job_dir,
    load_job,
)
from truelinev2.harness.product_readiness_bridge import run_job_readiness

router = APIRouter(prefix="/v2/product")

# Job-scoped subdir (under the gitignored product_store) for this lane's persisted result + REVIEW-candidate PNGs.
REVIEW_READINESS_SUBDIR = "review_readiness"
RESULT_FILENAME = "result.json"


def _store_root(c: Container):
    return c.settings.product_store_root


def _readiness_dir(store, customer_project_id, job_id) -> Path:
    return job_dir(store, customer_project_id, job_id) / REVIEW_READINESS_SUBDIR


def _job_to_http(exc: Exception) -> HTTPException:
    """Map a job / customer_project / isolation error to the repo's HTTP convention, mirroring
    product_pipeline_routes._to_http (order matters): missing job/project -> 404, cross-project / isolation -> 403,
    invalid slug / job id / other contract error -> 400. A non-contract error is left to propagate (a real 500,
    never masked)."""
    if isinstance(exc, (JobNotFoundError, ProjectNotFoundError)):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, (CrossProjectAccessError, IsolationError)):
        return HTTPException(status_code=403, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


# Job/context errors this router maps via _job_to_http (a CustomerProjectError covers an invalid tenant slug + a
# cross-project record mismatch from load_job's defense-in-depth assert_same_project; ProcessingJobError covers a
# missing/invalid job id).
_JOB_ERRORS = (ProcessingJobError, CustomerProjectError, IsolationError)


def _serve_url(job_id: str, name: str) -> str:
    return "/v2/product/jobs/%s/review-readiness/artifacts/%s" % (job_id, name)


def _with_served_artifacts(result: dict, job_id: str) -> dict:
    """Rewrite the bridge's candidate artifact BASENAMES into served API URLs, and expose a structured ``artifacts``
    list ([{role, filename, url}]). Refusals carry no candidate and an empty list."""
    cand = result.get("candidate")
    arts = []
    if cand:
        for role in ("before", "after"):
            name = cand.get("artifact_%s" % role)
            if name:
                url = _serve_url(job_id, name)
                cand["artifact_%s" % role] = url
                arts.append({"role": role, "filename": name, "url": url})
    result["artifacts"] = arts
    return result


@router.post("/jobs/{job_id}/review-readiness/run")
def run_review_readiness(job_id: str, plan_sheet: int = 1,
                         ctx: RequestContext = Depends(get_context),
                         c: Container = Depends(get_container)) -> dict:
    """Run the source-backed readiness / REVIEW-candidate spine on the authenticated tenant's job uploads and
    persist + return the product-safe result. A REVIEW candidate overlay (before/after PNGs) is drawn ONLY when the
    spine reports exactly READY_FOR_REVIEW_REDLINE (through the gated review_candidate builder); every refusal writes
    no artifact. Read-only wrt the job: no AUTO, no placement, no status promotion, no output slot, no lifecycle
    transition. 404 if the job is missing (incl. cross-tenant); 400 on an invalid plan_sheet."""
    if not isinstance(plan_sheet, int) or plan_sheet < 1:
        raise HTTPException(status_code=400, detail="plan_sheet must be a positive integer")
    cp, store = ctx.tenant.value, _store_root(c)
    try:
        job = load_job(store, cp, job_id)
    except _JOB_ERRORS as exc:
        raise _job_to_http(exc)

    rdir = _readiness_dir(store, cp, job_id)
    rdir.mkdir(parents=True, exist_ok=True)
    result = run_job_readiness(job.get("uploads") or [], job_dir(store, cp, job_id),
                               plan_sheet=plan_sheet, artifact_dir=rdir)
    result = _with_served_artifacts(result, job_id)
    (rdir / RESULT_FILENAME).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


@router.get("/jobs/{job_id}/review-readiness")
def get_review_readiness(job_id: str,
                         ctx: RequestContext = Depends(get_context),
                         c: Container = Depends(get_container)) -> dict:
    """Read the job's last persisted readiness / REVIEW-candidate result (the same shape the run endpoint returns).
    Read-only; runs nothing. 404 if the job is missing or readiness has not been run yet."""
    cp, store = ctx.tenant.value, _store_root(c)
    try:
        load_job(store, cp, job_id)                            # 404 (incl. cross-tenant) before any read
    except _JOB_ERRORS as exc:
        raise _job_to_http(exc)
    result_path = _readiness_dir(store, cp, job_id) / RESULT_FILENAME
    if not result_path.is_file():
        raise HTTPException(status_code=404, detail="readiness has not been run for this job")
    try:
        return json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise HTTPException(status_code=404, detail="readiness result is not readable")


def _safe_readiness_artifact(rdir: Path, artifact_path: str) -> Path:
    """Resolve a client-supplied artifact path SAFELY under the job's readiness dir: reject traversal / absolute /
    escaping paths, and allow only an existing ``.png`` file inside the dir. Raises HTTPException(404) otherwise."""
    if not artifact_path or "\x00" in artifact_path:
        raise HTTPException(status_code=404, detail="artifact not found")
    try:
        resolved = (rdir / artifact_path).resolve()
        root = rdir.resolve()
    except OSError:
        raise HTTPException(status_code=404, detail="artifact not found")
    if not resolved.is_relative_to(root):                      # inside the job's readiness dir only
        raise HTTPException(status_code=404, detail="artifact not found")
    if resolved.suffix.lower() != ".png" or not resolved.is_file():
        raise HTTPException(status_code=404, detail="artifact not found")
    return resolved


@router.get("/jobs/{job_id}/review-readiness/artifacts/{artifact_path:path}")
def get_review_readiness_artifact(job_id: str, artifact_path: str,
                                  ctx: RequestContext = Depends(get_context),
                                  c: Container = Depends(get_container)) -> FileResponse:
    """Serve ONE persisted REVIEW-candidate PNG for the tenant's job, by its safe basename. The image is a REVIEW
    candidate overlay (before = plan as-is, after = plan + RED REVIEW stroke) — NOT an AUTO / final placement. 404 if
    the job is missing, readiness has not been run, or the path is not a readiness PNG (traversal is refused)."""
    cp, store = ctx.tenant.value, _store_root(c)
    try:
        load_job(store, cp, job_id)                            # 404 (incl. cross-tenant) before serving bytes
    except _JOB_ERRORS as exc:
        raise _job_to_http(exc)
    path = _safe_readiness_artifact(_readiness_dir(store, cp, job_id), artifact_path)
    return FileResponse(str(path), media_type="image/png")
