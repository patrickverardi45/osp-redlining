"""Shared, fail-closed guards for DESTRUCTIVE product routes.

NOT authentication and NOT a change to the tenant/session model — a coarse on/off FOOTGUN gate so an
accidental (or casual) destructive product-API call (job delete today; any future clear/reset/purge)
cannot delete or wipe customer data unless the operator has EXPLICITLY opted in. Default is BLOCKED.

Call ``assert_destructive_enabled(settings)`` at the TOP of every destructive route handler, before any
data is touched. Enable with ``TL2_ENABLE_DESTRUCTIVE_PRODUCT_ROUTES=1``
(``settings.enable_destructive_product_routes``).
"""
from __future__ import annotations

from fastapi import HTTPException

from truelinev2.config import Settings

# Stable, importable error code — asserted by tests and surfaced verbatim in the 403 detail so callers
# (and the request audit log) get a consistent machine-readable reason.
DESTRUCTIVE_ROUTES_DISABLED = "DESTRUCTIVE_PRODUCT_ROUTES_DISABLED"


def assert_destructive_enabled(settings: Settings) -> None:
    """Raise HTTP 403 unless destructive product routes are explicitly enabled. Fail-closed: the default
    (flag unset/False) BLOCKS the destructive action before any store mutation. Returns None when enabled."""
    if not settings.enable_destructive_product_routes:
        raise HTTPException(
            status_code=403,
            detail=(
                f"{DESTRUCTIVE_ROUTES_DISABLED}: destructive product routes are disabled by default; "
                "set TL2_ENABLE_DESTRUCTIVE_PRODUCT_ROUTES=1 to enable"
            ),
        )
