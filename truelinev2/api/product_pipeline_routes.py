"""Slice 1 — local-only, flag-gated, generic product-pipeline FOUNDATION routes.

Thin, context-bearing routes that DRIVE the existing product contracts (no business logic lives here — it
lives in the contracts; mirrors api/routes.py). Identity is the VERIFIED `X-TL-Tenant` slug from the
request context (never the URL path or a request body): `customer_project_id == ctx.tenant.value`, so a
tenant can only ever address its own customer_project subtree. Mounted by create_app ONLY when
settings.product_pipeline_api_optin is True (DEFAULT OFF).

Slice 1 wires ONLY the customer_project + processing_job foundation (create / get / transition). Uploads,
the reviewed bore-log gate, manifest handoff, proof artifacts, KMZ/closeout/billing/export are later slices
and are NOT implemented here.
"""
from __future__ import annotations

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

router = APIRouter(prefix="/v2/product")


class ProjectCreate(BaseModel):
    display_name: str


class JobCreate(BaseModel):
    job_id: str


class JobTransition(BaseModel):
    to_status: str
    reason: Optional[str] = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _store_root(c: Container):
    return c.settings.product_store_root


def _to_http(exc: Exception) -> HTTPException:
    """Map a contract / isolation exception to the repo's HTTP convention (order matters: NotFound and
    IllegalTransition are subclasses of the contract base errors)."""
    if isinstance(exc, (ProjectNotFoundError, JobNotFoundError)):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, IllegalTransitionError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, (CrossProjectAccessError, IsolationError)):
        return HTTPException(status_code=403, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))   # invalid id / bad target / missing reason / ...


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
