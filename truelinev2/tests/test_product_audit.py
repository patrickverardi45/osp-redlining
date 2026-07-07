"""Phase 2 hardening: append-only product-API audit logging.

CI-safe: NO httpx / TestClient (the repo omits httpx from requirements). The middleware is exercised by
calling its async ``dispatch`` directly with a hand-built Starlette Request + a stub call_next; the pure
event/append helpers are unit-tested. Temp files only; generic ids.
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from truelinev2.api.app import create_app
from truelinev2.api.audit import (
    ProductAuditMiddleware,
    append_audit_event,
    build_audit_event,
)
from truelinev2.config import Settings


def _request(path: str, method: str = "GET", headers=None) -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    scope = {
        "type": "http", "http_version": "1.1", "method": method, "path": path,
        "raw_path": path.encode(), "query_string": b"", "headers": raw, "scheme": "http",
        "server": ("test", 80), "client": ("203.0.113.7", 5555),
    }
    return Request(scope)


def _dispatch(mw: ProductAuditMiddleware, request: Request, response: Response) -> Response:
    async def call_next(_req):
        return response
    return asyncio.run(mw.dispatch(request, call_next))


def _app(tmp_path: Path, **over):
    s = dataclasses.replace(
        Settings.for_proof(),
        artifact_root=tmp_path / "artifacts", cards_dir=tmp_path / "cards",
        db_path=tmp_path / "db.sqlite", product_store_root=tmp_path / "ps", **over)
    return create_app(s)


# --- pure event builder ---------------------------------------------------------------------------- #
def test_build_event_fields_and_no_secrets():
    ev = build_audit_event(
        ts="2026-07-07T00:00:00+00:00", request_id="req-1", method="POST",
        path="/v2/product/jobs/job-9/delete", status_code=403, tenant="cp-aaa", session="sess-1",
        client="203.0.113.7", user_agent="ua/1", duration_ms=1.25)
    assert ev["method"] == "POST" and ev["status_code"] == 403
    assert ev["tenant"] == "cp-aaa" and ev["session"] == "sess-1"
    assert ev["job_id"] == "job-9" and ev["blocked"] is True
    assert ev["client"] == "203.0.113.7" and ev["user_agent"] == "ua/1"
    assert ev["record_format"] == "trueline-product-audit-1" and ev["request_id"] == "req-1"
    # never carries bodies/secrets
    assert not (set(ev) & {"body", "payload", "authorization", "cookie", "token", "content_base64"})


def test_build_event_non_destructive_not_blocked():
    ev = build_audit_event(
        ts="t", request_id="r", method="GET", path="/v2/product/jobs", status_code=200,
        tenant=None, session=None, client=None, user_agent=None, duration_ms=0.0)
    assert ev["blocked"] is False and ev["job_id"] is None
    assert ev["tenant"] is None and ev["session"] is None
    ev2 = build_audit_event(
        ts="t", request_id="r", method="GET", path="/v2/product/jobs/job-3/uploads", status_code=200,
        tenant="cp", session="s", client=None, user_agent=None, duration_ms=0.0)
    assert ev2["job_id"] == "job-3" and ev2["blocked"] is False


# --- append helper --------------------------------------------------------------------------------- #
def test_append_writes_valid_jsonl_and_appends(tmp_path):
    log = tmp_path / "nested" / "audit.jsonl"
    assert append_audit_event(log, {"a": 1}) is True
    assert append_audit_event(log, {"b": 2}) is True
    lines = log.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert [json.loads(x) for x in lines] == [{"a": 1}, {"b": 2}]   # one valid JSON per line


def test_append_is_best_effort_on_bad_path(tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")            # a FILE where a dir is needed
    assert append_audit_event(blocker / "audit.jsonl", {"a": 1}) is False   # returns False, never raises


# --- middleware dispatch (no TestClient) ----------------------------------------------------------- #
def test_middleware_appends_one_event_for_product_request(tmp_path):
    log = tmp_path / "audit.jsonl"
    mw = ProductAuditMiddleware(app=None, log_path=log)
    req = _request("/v2/product/jobs/job-1/delete", method="POST",
                   headers={"X-TL-Tenant": "cp-aaa", "X-TL-Session": "sess-1", "User-Agent": "ua/1"})
    _dispatch(mw, req, JSONResponse({"detail": "DESTRUCTIVE_PRODUCT_ROUTES_DISABLED: ..."}, status_code=403))
    lines = log.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    ev = json.loads(lines[0])
    assert ev["method"] == "POST" and ev["status_code"] == 403
    assert ev["tenant"] == "cp-aaa" and ev["session"] == "sess-1" and ev["job_id"] == "job-1"
    assert ev["blocked"] is True and ev["user_agent"] == "ua/1"
    assert isinstance(ev["duration_ms"], (int, float)) and ev["request_id"]


def test_middleware_records_forwarded_client(tmp_path):
    log = tmp_path / "audit.jsonl"
    mw = ProductAuditMiddleware(app=None, log_path=log)
    req = _request("/v2/product/jobs", headers={"X-Forwarded-For": "198.51.100.9, 10.0.0.1"})
    _dispatch(mw, req, JSONResponse({"jobs": []}, status_code=200))
    ev = json.loads(log.read_text(encoding="utf-8").strip())
    assert ev["client"] == "198.51.100.9" and ev["status_code"] == 200 and ev["blocked"] is False


def test_middleware_skips_non_product_paths(tmp_path):
    log = tmp_path / "audit.jsonl"
    mw = ProductAuditMiddleware(app=None, log_path=log)
    _dispatch(mw, _request("/v2/health"), JSONResponse({"status": "ok"}, status_code=200))
    assert not log.exists()          # health (non-product) is never logged


# --- wiring ---------------------------------------------------------------------------------------- #
def test_middleware_mounted_only_with_product_api(tmp_path):
    on = _app(tmp_path, product_pipeline_api_optin=True, product_audit_log_path=tmp_path / "audit.jsonl")
    assert any(m.cls is ProductAuditMiddleware for m in on.user_middleware)
    off = _app(tmp_path, product_pipeline_api_optin=False)
    assert not any(m.cls is ProductAuditMiddleware for m in off.user_middleware)
