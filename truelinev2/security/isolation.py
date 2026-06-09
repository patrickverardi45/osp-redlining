"""Structural tenant isolation. Deny by default."""
from __future__ import annotations

from typing import Optional

from truelinev2.context import IsolationError, RequestContext


def scoped_prefix(ctx: RequestContext) -> str:
    return f"{ctx.tenant.value}/{ctx.session_id}"


def assert_owns(ctx: RequestContext, resource_tenant: Optional[str]) -> None:
    """Raise unless the resource is owned by ctx.tenant. Missing owner == denied."""
    if not resource_tenant or resource_tenant.strip() != ctx.tenant.value:
        raise IsolationError(
            f"cross-tenant access denied: {ctx.tenant.value!r} vs {resource_tenant!r}")
