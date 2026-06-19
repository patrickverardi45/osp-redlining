"""FastAPI dependencies: pull the wired container + resolve the request context.

Identity comes from authenticated request metadata — NOT from the URL path. In
this milestone the tenant/session arrive as headers standing in for verified JWT
claims; wiring real JWT verification is a later step. The point that matters now
is the SHAPE: identity is resolved server-side and fails closed (401) when
absent, so no endpoint accepts a client-chosen tenant/session in its path (the
monolith's IDOR seam, Stream-6 1a/1b).
"""
from __future__ import annotations

from typing import Optional

from fastapi import Header, HTTPException, Request

from ..container import AppContainer
from ..context import IsolationError, RequestContext, require_context


def get_container(request: Request) -> AppContainer:
    return request.app.state.tl


def get_context(
    x_tl_tenant: Optional[str] = Header(default=None, alias="X-TL-Tenant"),
    x_tl_session: Optional[str] = Header(default=None, alias="X-TL-Session"),
) -> RequestContext:
    """Resolve the (tenant, session) scope, fail-closed. 401 if identity missing.

    Stand-in for verified JWT claims (tenant = pilot slug). Replace the header
    source with real token verification without changing any downstream code.
    """
    try:
        return require_context(x_tl_tenant or "", x_tl_session or "")
    except IsolationError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
