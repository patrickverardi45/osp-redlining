"""Request-scoped identity, fail-closed. No process globals.

Tenant identity is mandatory (no anonymous escape hatch); the tenant key is a
slug, never a UUID. Session ids are never anonymously minted.
"""
from __future__ import annotations

from dataclasses import dataclass


class IsolationError(PermissionError):
    """Missing identity or cross-tenant access. Always fails closed."""


@dataclass(frozen=True)
class TenantId:
    value: str

    def __post_init__(self) -> None:
        v = (self.value or "").strip()
        if not v:
            raise IsolationError("tenant id required (no anonymous tenant)")
        if len(v) == 36 and v.count("-") == 4:
            raise IsolationError(f"tenant id must be a slug, not a UUID: {v!r}")
        object.__setattr__(self, "value", v)


@dataclass(frozen=True)
class RequestContext:
    tenant: TenantId
    session_id: str

    def __post_init__(self) -> None:
        sid = (self.session_id or "").strip()
        if not sid:
            raise IsolationError("session_id required (no anonymous minting)")
        object.__setattr__(self, "session_id", sid)


def require_context(tenant: str, session_id: str) -> RequestContext:
    return RequestContext(tenant=TenantId(tenant), session_id=session_id)
