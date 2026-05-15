"""
Phase 1 real user auth endpoints.

Runs parallel to pilot token auth (protected_router / get_current_tenant).
Does NOT affect any existing routes.
"""

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import jwt
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.auth_tokens import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    revoke_refresh_token,
    rotate_refresh_token,
)
from app.db import auth_db, get_user_by_email, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

_REFRESH_COOKIE = "tl_refresh"
_REFRESH_COOKIE_PATH = "/auth"
_REFRESH_MAX_AGE = 14 * 24 * 3600

_bearer = HTTPBearer(auto_error=False)

# Auth lifecycle event log — same uploads directory as request_audit.jsonl.
_BASE_DIR = Path(__file__).resolve().parent.parent  # backend/
_AUTH_EVENTS_PATH = (
    Path(os.getenv("OSP_UPLOAD_DIR") or str(_BASE_DIR / "uploads")) / "auth_events.jsonl"
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _set_refresh_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        key=_REFRESH_COOKIE,
        value=raw_token,
        httponly=True,
        secure=True,
        samesite="none",
        path=_REFRESH_COOKIE_PATH,
        max_age=_REFRESH_MAX_AGE,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=_REFRESH_COOKIE,
        path=_REFRESH_COOKIE_PATH,
        httponly=True,
        secure=True,
        samesite="none",
    )


def require_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> dict:
    if not credentials:
        raise HTTPException(status_code=401, detail="missing_token")
    try:
        return decode_access_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="token_expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="invalid_token")


def _user_shape(user_row, membership_row, company_row) -> dict:
    return {
        "id": user_row["id"],
        "email": user_row["email"],
        "display_name": user_row["display_name"],
        "company_id": membership_row["company_id"],
        "company_slug": company_row["slug"],
        "role": membership_row["role"],
    }


def _write_auth_event(
    request: Request,
    event: str,
    outcome: str,
    *,
    user_id: Optional[str] = None,
    email_sha8: Optional[str] = None,
) -> None:
    """Append one auth lifecycle record to auth_events.jsonl. Never raises."""
    try:
        record: dict = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": getattr(request.state, "request_id", uuid.uuid4().hex),
            "event": event,
            "outcome": outcome,
        }
        if user_id is not None:
            record["user_id"] = user_id
        if email_sha8 is not None:
            record["email_sha8"] = email_sha8
        try:
            with open(str(_AUTH_EVENTS_PATH), "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, separators=(",", ":")) + "\n")
        except Exception:
            pass  # fail-closed: file write errors must never fail the request
    except Exception:
        pass  # outer guard: protect request flow from any unexpected error


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    email: str
    password: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/login")
def login(body: LoginRequest, response: Response, request: Request):
    _invalid = HTTPException(status_code=401, detail="invalid_credentials")
    _email_sha8 = hashlib.sha256(body.email.encode()).hexdigest()[:8]

    with auth_db() as conn:
        user = get_user_by_email(conn, body.email)
        if not user or not verify_password(body.password, user["password_hash"] or ""):
            _write_auth_event(request, "login", "invalid_credentials", email_sha8=_email_sha8)
            raise _invalid

        if user["disabled_at"]:
            _write_auth_event(request, "login", "account_disabled", email_sha8=_email_sha8)
            raise HTTPException(status_code=403, detail="account_disabled")

        membership = conn.execute(
            "SELECT * FROM memberships WHERE user_id = ? ORDER BY created_at ASC LIMIT 1",
            (user["id"],),
        ).fetchone()
        if not membership:
            _write_auth_event(request, "login", "no_company_assigned", email_sha8=_email_sha8)
            raise HTTPException(status_code=403, detail="no_company_assigned")

        company = conn.execute(
            "SELECT * FROM companies WHERE id = ?", (membership["company_id"],)
        ).fetchone()

        access_token = create_access_token(user, membership)
        raw_refresh, _ = create_refresh_token(conn, user["id"])

    _set_refresh_cookie(response, raw_refresh)
    _write_auth_event(request, "login", "ok", user_id=user["id"])
    return {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": 900,
        "user": _user_shape(user, membership, company),
    }


@router.post("/refresh")
def refresh(
    response: Response,
    request: Request,
    tl_refresh: Optional[str] = Cookie(default=None),
):
    if not tl_refresh:
        _write_auth_event(request, "refresh", "invalid_refresh_token")
        raise HTTPException(status_code=401, detail="invalid_refresh_token")

    with auth_db() as conn:
        try:
            user_id, new_raw, _ = rotate_refresh_token(conn, tl_refresh)
        except ValueError:
            _write_auth_event(request, "refresh", "invalid_refresh_token")
            raise HTTPException(status_code=401, detail="invalid_refresh_token")

        user = conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        membership = conn.execute(
            "SELECT * FROM memberships WHERE user_id = ? ORDER BY created_at ASC LIMIT 1",
            (user_id,),
        ).fetchone()
        if not user or not membership or user["disabled_at"]:
            _write_auth_event(request, "refresh", "invalid_refresh_token")
            raise HTTPException(status_code=401, detail="invalid_refresh_token")

        access_token = create_access_token(user, membership)

    _set_refresh_cookie(response, new_raw)
    _write_auth_event(request, "refresh", "ok", user_id=user_id)
    return {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": 900,
    }


@router.post("/logout", status_code=204)
def logout(
    response: Response,
    request: Request,
    tl_refresh: Optional[str] = Cookie(default=None),
):
    if tl_refresh:
        with auth_db() as conn:
            revoke_refresh_token(conn, tl_refresh)
    _clear_refresh_cookie(response)
    _write_auth_event(request, "logout", "ok")


@router.get("/me")
def me(claims: dict = Depends(require_user)):
    user_id = claims.get("sub")
    with auth_db() as conn:
        user = conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        membership = conn.execute(
            "SELECT * FROM memberships WHERE user_id = ? ORDER BY created_at ASC LIMIT 1",
            (user_id,),
        ).fetchone()
        company = conn.execute(
            "SELECT * FROM companies WHERE id = ?", (membership["company_id"],)
        ).fetchone() if membership else None

    if not user or not membership or not company:
        raise HTTPException(status_code=401, detail="user_not_found")
    return _user_shape(user, membership, company)
