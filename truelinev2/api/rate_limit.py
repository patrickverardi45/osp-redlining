"""In-process fixed-window rate-limit GUARDRAIL — a DEFAULT-OFF seam, not the production limiter.

``RateLimitMiddleware`` is mounted by ``create_app`` ONLY when ``settings.rate_limit_optin`` is True (default
False -> the middleware is entirely absent and request handling is byte-identical). This is a conservative,
single-instance in-process fallback so one uvicorn instance is not defenceless; REAL production rate limiting
belongs at the edge (Cloudflare) or a shared store (Redis / a managed API gateway) — see the ops docs. The
seam (``FixedWindowRateLimiter``) is deliberately small so it can later be swapped for a distributed backend
without touching call sites.

Placement matters: this middleware sits BEHIND Cloudflare Access (which challenges at the edge, before any
request reaches the backend), so it can NEVER interfere with the Access one-time-PIN flow. An over-limit
request receives a plain ``429`` + ``Retry-After`` header — never an auth redirect.

Caveat (documented, intentional): behind a single tunnel every request may share one forwarded client IP, so
the in-process key is best-effort. That is exactly why this is a guardrail, not the production limiter.
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Iterable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

# Bound the in-process bucket map so a flood of distinct keys cannot grow memory without limit. When the map
# exceeds this size we drop entries whose window has rolled over (cheap, opportunistic cleanup).
_MAX_TRACKED_KEYS = 50_000


class FixedWindowRateLimiter:
    """Pure, thread-safe fixed-window counter. ``check(key, now)`` -> ``(allowed, retry_after_seconds)``.

    Independent of any web framework so it is unit-testable in isolation and swappable for a distributed
    backend later. ``retry_after`` is 0 when the request is allowed.
    """

    def __init__(self, limit_per_window: int, window_seconds: int = 60) -> None:
        self._limit = max(1, int(limit_per_window))
        self._window = max(1, int(window_seconds))
        self._buckets: dict[str, tuple[int, int]] = {}   # key -> (window_start_epoch, count)
        self._lock = threading.Lock()

    def _window_start(self, now: float) -> int:
        n = int(now)
        return n - (n % self._window)

    def check(self, key: str, now: float) -> tuple[bool, int]:
        window_start = self._window_start(now)
        with self._lock:
            if len(self._buckets) > _MAX_TRACKED_KEYS:
                self._buckets = {
                    k: v for k, v in self._buckets.items() if v[0] == window_start
                }
            start, count = self._buckets.get(key, (window_start, 0))
            if start != window_start:                      # window rolled over -> reset this key
                start, count = window_start, 0
            if count >= self._limit:
                retry_after = self._window - (int(now) - start)
                self._buckets[key] = (start, count)
                return False, max(1, retry_after)
            self._buckets[key] = (start, count + 1)
            return True, 0


def _default_client_key(request: Request) -> str:
    """Best-effort per-client key: first hop of X-Forwarded-For, else the transport peer, else 'unknown'.
    Intentionally simple — a distributed/edge limiter would key on a trusted identity instead."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    client = request.client
    return client.host if client and client.host else "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Default-safe fixed-window rate-limit middleware. Only ever mounted when the opt-in flag is set."""

    def __init__(
        self,
        app,
        *,
        limiter: FixedWindowRateLimiter,
        exempt_paths: Iterable[str] = (),
        client_key: Callable[[Request], str] | None = None,
        time_fn: Callable[[], float] = time.time,
    ) -> None:
        super().__init__(app)
        self._limiter = limiter
        self._exempt = frozenset(exempt_paths)
        self._client_key = client_key or _default_client_key
        self._time_fn = time_fn

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in self._exempt:
            return await call_next(request)
        allowed, retry_after = self._limiter.check(self._client_key(request), self._time_fn())
        if not allowed:
            return JSONResponse(
                {"detail": "rate limit exceeded"},
                status_code=429,
                headers={"Retry-After": str(retry_after)},
            )
        return await call_next(request)
