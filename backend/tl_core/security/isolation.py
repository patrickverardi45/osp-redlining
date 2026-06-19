"""Structural tenant/session isolation helpers. Deny by default.

The monolith leaked because ownership checks no-op'd when no auth context was
present (Stream-6 1a) and because session ids were client-chosen + anonymously
minted (1b). Here every scoped key REQUIRES a fully-formed context, and
:func:`assert_owns` fails closed on any mismatch OR missing owner — the inverse
of the monolith's permissive default.
"""
from __future__ import annotations

from typing import Optional

from ..context import IsolationError, RequestContext


def scoped_prefix(ctx: RequestContext) -> str:
    """Storage key prefix unique to (tenant, session). Both parts are guaranteed
    non-empty + slug-safe by :class:`RequestContext` construction."""
    return f"{ctx.tenant.value}/{ctx.session_id}"


def assert_owns(ctx: RequestContext, resource_tenant: Optional[str]) -> None:
    """Raise unless the resource is owned by ``ctx.tenant``. A missing/None owner
    is treated as NOT owned (deny) — the opposite of the monolith's no-op."""
    if not resource_tenant or resource_tenant.strip() != ctx.tenant.value:
        raise IsolationError(
            f"cross-tenant access denied: {ctx.tenant.value!r} cannot access "
            f"resource owned by {resource_tenant!r}")
