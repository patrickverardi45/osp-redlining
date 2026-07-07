"""Append-only JSONL audit log for the product API (Phase 2 hardening).

Best-effort and FAIL-OPEN: audit logging never breaks request handling (any error is swallowed). Records
request METADATA only — NEVER request/response bodies, upload bytes, cookies, tokens, or Authorization
headers. The tenant/session VALUES are recorded (in this system they are non-secret routing identifiers,
already the store path component); no auth/cookie headers are ever read.
"""
from __future__ import annotations

import json
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

AUDIT_RECORD_FORMAT = "trueline-product-audit-1"
DEFAULT_AUDIT_PREFIX = "/v2/product"

# Destructive product routes (path suffix). A 403 on one of these is recorded as blocked=True (the
# destructive action was refused before any store mutation — e.g. by the default-off destructive gate).
_DESTRUCTIVE_SUFFIXES = ("/delete",)
_JOB_RE = re.compile(r"/v2/product/jobs/([^/]+)")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _job_id_from_path(path: str) -> Optional[str]:
    m = _JOB_RE.search(path or "")
    return m.group(1) if m else None


def _is_destructive_path(path: str) -> bool:
    p = (path or "").rstrip("/")
    return any(p.endswith(s) for s in _DESTRUCTIVE_SUFFIXES)


def build_audit_event(*, ts: str, request_id: str, method: str, path: str, status_code: int,
                      tenant: Optional[str], session: Optional[str], client: Optional[str],
                      user_agent: Optional[str], duration_ms: float) -> dict:
    """Build a sanitized audit event dict. PURE (no I/O, no secrets). ``blocked`` is True when a destructive
    route returned 403 (the destructive action was refused before any store mutation)."""
    return {
        "record_format": AUDIT_RECORD_FORMAT,
        "ts": ts,
        "request_id": request_id,
        "method": method,
        "path": path,
        "status_code": status_code,
        "tenant": tenant or None,
        "session": session or None,
        "job_id": _job_id_from_path(path),
        "client": client or None,
        "user_agent": user_agent or None,
        "duration_ms": duration_ms,
        "blocked": bool(_is_destructive_path(path) and status_code == 403),
    }


def append_audit_event(log_path, event: dict) -> bool:
    """Append ONE JSON line to log_path (creating parent dirs). Best-effort: NEVER raises; returns False on
    any failure so the caller carries on."""
    try:
        log_path = Path(log_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, separators=(",", ":"), ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False


def _client_info(request: Request) -> Optional[str]:
    """First forwarded hop if present (Cloudflare/proxy), else the direct client host. Never full headers."""
    fwd = request.headers.get("x-forwarded-for") or request.headers.get("cf-connecting-ip")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


class ProductAuditMiddleware(BaseHTTPMiddleware):
    """Append one JSONL audit event per product-API request. Best-effort; never breaks the request."""

    def __init__(self, app, *, log_path, path_prefix: str = DEFAULT_AUDIT_PREFIX):
        super().__init__(app)
        self._log_path = Path(log_path)
        self._prefix = path_prefix

    async def dispatch(self, request: Request,
                       call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        path = request.url.path
        if not path.startswith(self._prefix):
            return await call_next(request)
        start = time.perf_counter()
        response = await call_next(request)
        try:
            event = build_audit_event(
                ts=_utc_now_iso(),
                request_id=request.headers.get("x-request-id") or uuid.uuid4().hex,
                method=request.method,
                path=path,
                status_code=response.status_code,
                tenant=request.headers.get("x-tl-tenant"),
                session=request.headers.get("x-tl-session"),
                client=_client_info(request),
                user_agent=request.headers.get("user-agent"),
                duration_ms=round((time.perf_counter() - start) * 1000, 3),
            )
            append_audit_event(self._log_path, event)
        except Exception:
            pass  # audit is best-effort — NEVER break the request
        return response
