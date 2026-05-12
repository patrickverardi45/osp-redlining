"""
Phase 1 real user auth endpoints.

Runs parallel to pilot token auth (protected_router / get_current_tenant).
Does NOT affect any existing routes.
"""

from typing import Optional

import jwt
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
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
def login(body: LoginRequest, response: Response):
    _invalid = HTTPException(status_code=401, detail="invalid_credentials")

    with auth_db() as conn:
        user = get_user_by_email(conn, body.email)
        if not user or not verify_password(body.password, user["password_hash"] or ""):
            raise _invalid

        membership = conn.execute(
            "SELECT * FROM memberships WHERE user_id = ? ORDER BY created_at ASC LIMIT 1",
            (user["id"],),
        ).fetchone()
        if not membership:
            raise HTTPException(status_code=403, detail="no_company_assigned")

        company = conn.execute(
            "SELECT * FROM companies WHERE id = ?", (membership["company_id"],)
        ).fetchone()

        access_token = create_access_token(user, membership)
        raw_refresh, _ = create_refresh_token(conn, user["id"])

    _set_refresh_cookie(response, raw_refresh)
    return {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": 900,
        "user": _user_shape(user, membership, company),
    }


@router.post("/refresh")
def refresh(
    response: Response,
    tl_refresh: Optional[str] = Cookie(default=None),
):
    if not tl_refresh:
        raise HTTPException(status_code=401, detail="invalid_refresh_token")

    with auth_db() as conn:
        try:
            user_id, new_raw, _ = rotate_refresh_token(conn, tl_refresh)
        except ValueError:
            raise HTTPException(status_code=401, detail="invalid_refresh_token")

        user = conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        membership = conn.execute(
            "SELECT * FROM memberships WHERE user_id = ? ORDER BY created_at ASC LIMIT 1",
            (user_id,),
        ).fetchone()
        if not user or not membership:
            raise HTTPException(status_code=401, detail="invalid_refresh_token")

        access_token = create_access_token(user, membership)

    _set_refresh_cookie(response, new_raw)
    return {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": 900,
    }


@router.post("/logout", status_code=204)
def logout(
    response: Response,
    tl_refresh: Optional[str] = Cookie(default=None),
):
    if tl_refresh:
        with auth_db() as conn:
            revoke_refresh_token(conn, tl_refresh)
    _clear_refresh_cookie(response)


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
