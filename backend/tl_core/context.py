"""Request-scoped identity. Replaces the monolith's process-global ``STATE`` +
ContextVar tenant with an explicit, fail-closed context object threaded through
call sites.

Security rules enforced here (from the Stream-6 audit of the monolith):
  * 1a — tenant identity is MANDATORY. There is no ``caller is None -> allow``
    escape hatch; constructing a context without a tenant raises.
  * 1b — no anonymous session minting; a blank session_id is rejected, not
    silently replaced with a fresh uuid that then exposes arbitrary state.
  * 1d — :class:`TenantId` is a distinct type carrying a pilot SLUG (never a
    company UUID), so the slug/UUID confusion footgun cannot mis-compare.
"""
from __future__ import annotations

from dataclasses import dataclass


class IsolationError(PermissionError):
    """Raised when tenant/session identity is missing or a cross-tenant access is
    attempted. Always fails closed (deny by default)."""


@dataclass(frozen=True)
class TenantId:
    """Canonical tenant identifier — a pilot slug, never a UUID."""

    value: str

    def __post_init__(self) -> None:
        v = (self.value or "").strip()
        if not v:
            raise IsolationError("tenant id is required (fail-closed; no anonymous tenant)")
        # A company UUID is 36 chars with 4 dashes; the tenant key must be a slug.
        if len(v) == 36 and v.count("-") == 4:
            raise IsolationError(f"tenant id must be a slug, not a UUID: {v!r}")
        object.__setattr__(self, "value", v)


@dataclass(frozen=True)
class RequestContext:
    """The (tenant, session) scope for one unit of work. Immutable; built at the
    request boundary and passed explicitly — never a process global."""

    tenant: TenantId
    session_id: str

    def __post_init__(self) -> None:
        sid = (self.session_id or "").strip()
        if not sid:
            raise IsolationError(
                "session_id is required (fail-closed; no anonymous session minting)")
        object.__setattr__(self, "session_id", sid)


def require_context(tenant: str, session_id: str) -> RequestContext:
    """Build a fail-closed :class:`RequestContext`. Raises :class:`IsolationError`
    if either part is missing/invalid."""
    return RequestContext(tenant=TenantId(tenant), session_id=session_id)
