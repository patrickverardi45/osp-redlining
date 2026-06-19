"""Artifact serving — tenant-scoped, traversal-safe.

The only client-supplied path part is the leaf ``{name}`` (a basename). The scope
(tenant, session) comes from the auth context, so one tenant can never address
another's artifacts. Maps store errors to HTTP:
  * invalid name / traversal attempt -> 400
  * not found in the caller's scope (incl. cross-tenant) -> 404 (no existence leak)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from ..container import AppContainer
from ..context import IsolationError, RequestContext
from .deps import get_container, get_context

router = APIRouter()


@router.get("/v2/artifact/{name}")
def get_artifact(
    name: str,
    ctx: RequestContext = Depends(get_context),
    container: AppContainer = Depends(get_container),
) -> FileResponse:
    try:
        path = container.store.resolve(ctx, name)
    except IsolationError:
        raise HTTPException(status_code=400, detail="invalid artifact name")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="artifact not found")
    return FileResponse(str(path), media_type="image/png")
