"""Tests for the DEFAULT-OFF fixed-window rate-limit guardrail.

Two layers, no httpx/TestClient (repo convention):
  * FixedWindowRateLimiter — pure allow/block/retry-after/window-reset/per-key/bounded-memory logic.
  * RateLimitMiddleware — driven directly via `dispatch` with a minimal Request + async call_next.
  * create_app wiring — default-off => middleware absent (byte-identical); opt-in => mounted with /v2/health
    exempt.
"""
from __future__ import annotations

import asyncio
import dataclasses

from starlette.requests import Request
from starlette.responses import PlainTextResponse

from truelinev2.api.app import create_app
from truelinev2.api.rate_limit import FixedWindowRateLimiter, RateLimitMiddleware
from truelinev2.config import Settings


# --------------------------- pure limiter --------------------------- #

def test_allows_up_to_limit_then_blocks():
    rl = FixedWindowRateLimiter(limit_per_window=3, window_seconds=60)
    now = 1000.0
    assert rl.check("k", now) == (True, 0)
    assert rl.check("k", now) == (True, 0)
    assert rl.check("k", now) == (True, 0)
    allowed, retry_after = rl.check("k", now)
    assert allowed is False
    assert retry_after > 0


def test_window_resets_after_window_elapses():
    rl = FixedWindowRateLimiter(limit_per_window=1, window_seconds=60)
    assert rl.check("k", 0.0) == (True, 0)
    assert rl.check("k", 30.0)[0] is False       # same 60s window -> blocked
    assert rl.check("k", 60.0) == (True, 0)      # next window -> allowed again


def test_keys_are_independent():
    rl = FixedWindowRateLimiter(limit_per_window=1, window_seconds=60)
    assert rl.check("a", 0.0)[0] is True
    assert rl.check("a", 0.0)[0] is False
    assert rl.check("b", 0.0)[0] is True          # different key unaffected


def test_retry_after_never_below_one():
    rl = FixedWindowRateLimiter(limit_per_window=1, window_seconds=60)
    rl.check("k", 59.9)                            # consume within the window
    allowed, retry_after = rl.check("k", 59.9)
    assert allowed is False
    assert retry_after >= 1


# --------------------------- middleware (direct dispatch) --------------------------- #

def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _request(path: str, *, client_host: str = "1.2.3.4", xff: str | None = None) -> Request:
    headers = []
    if xff is not None:
        headers.append((b"x-forwarded-for", xff.encode()))
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": headers,
        "client": (client_host, 54321),
        "server": ("testserver", 80),
        "scheme": "http",
    }
    return Request(scope)


async def _ok(_request):
    return PlainTextResponse("ok")


def _mw(limit=2, exempt=("/v2/health",), now=1000.0):
    return RateLimitMiddleware(
        app=None,
        limiter=FixedWindowRateLimiter(limit, 60),
        exempt_paths=exempt,
        time_fn=lambda: now,
    )


def test_middleware_blocks_over_limit_with_retry_after():
    mw = _mw(limit=2)
    assert _run(mw.dispatch(_request("/x"), _ok)).status_code == 200
    assert _run(mw.dispatch(_request("/x"), _ok)).status_code == 200
    blocked = _run(mw.dispatch(_request("/x"), _ok))
    assert blocked.status_code == 429
    assert "retry-after" in {k.lower() for k in blocked.headers.keys()}


def test_middleware_exempt_path_is_never_limited():
    mw = _mw(limit=1)
    for _ in range(5):
        assert _run(mw.dispatch(_request("/v2/health"), _ok)).status_code == 200


def test_middleware_keys_by_forwarded_for_first_hop():
    mw = _mw(limit=1)
    # Two distinct forwarded clients behind the same transport peer are limited independently.
    assert _run(mw.dispatch(_request("/x", xff="9.9.9.1, 10.0.0.1"), _ok)).status_code == 200
    assert _run(mw.dispatch(_request("/x", xff="9.9.9.1, 10.0.0.1"), _ok)).status_code == 429
    assert _run(mw.dispatch(_request("/x", xff="9.9.9.2, 10.0.0.1"), _ok)).status_code == 200


# --------------------------- create_app wiring --------------------------- #

def _settings(**over) -> Settings:
    return dataclasses.replace(Settings.for_proof(), **over)


def test_default_off_does_not_mount_middleware():
    app = create_app(_settings())                 # rate_limit_optin defaults False
    assert RateLimitMiddleware not in [m.cls for m in app.user_middleware]


def test_optin_mounts_middleware():
    app = create_app(_settings(rate_limit_optin=True, rate_limit_per_minute=5))
    assert RateLimitMiddleware in [m.cls for m in app.user_middleware]
