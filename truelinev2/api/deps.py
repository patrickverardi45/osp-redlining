"""FastAPI dependencies: container + fail-closed request context (from headers
standing in for verified JWT claims; identity never comes from the URL path)."""
from __future__ import annotations

from typing import Optional

from fastapi import Header, HTTPException, Request

from truelinev2.api.container import Container
from truelinev2.context import IsolationError, RequestContext, require_context


def get_container(request: Request) -> Container:
    return request.app.state.tl2


def get_context(
    x_tl_tenant: Optional[str] = Header(default=None, alias="X-TL-Tenant"),
    x_tl_session: Optional[str] = Header(default=None, alias="X-TL-Session"),
) -> RequestContext:
    try:
        return require_context(x_tl_tenant or "", x_tl_session or "")
    except IsolationError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
