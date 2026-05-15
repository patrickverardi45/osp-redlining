"""
V1 admin / user-management endpoints.

All routes require owner or admin role (require_admin dependency).
Never returns password hashes. Uses existing db.py helpers throughout.
"""

import sqlite3
from datetime import datetime, timezone
from typing import Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.auth_tokens import decode_access_token
from app.db import (
    auth_db,
    create_company,
    create_membership,
    create_user,
    hash_password,
)

router = APIRouter(prefix="/admin", tags=["admin"])

_bearer = HTTPBearer(auto_error=False)


def require_admin(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> dict:
    """Validate JWT and enforce owner-or-admin role."""
    if not credentials:
        raise HTTPException(status_code=401, detail="missing_token")
    try:
        claims = decode_access_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="token_expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="invalid_token")
    if claims.get("role") not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="admin_required")
    return claims


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class CreateCompanyRequest(BaseModel):
    slug: str
    name: str


class CreateUserRequest(BaseModel):
    email: str
    password: str
    display_name: Optional[str] = None


class AssignUserRequest(BaseModel):
    company_id: str
    role: str = "member"


class ResetPasswordRequest(BaseModel):
    new_password: str


# ---------------------------------------------------------------------------
# Companies
# ---------------------------------------------------------------------------

@router.get("/companies")
def list_companies(_: dict = Depends(require_admin)):
    with auth_db() as conn:
        rows = conn.execute(
            "SELECT id, slug, name, created_at FROM companies ORDER BY created_at ASC"
        ).fetchall()
    return [dict(r) for r in rows]


@router.post("/companies", status_code=201)
def create_company_endpoint(body: CreateCompanyRequest, _: dict = Depends(require_admin)):
    slug = body.slug.strip().lower()
    name = body.name.strip()
    if not slug or not name:
        raise HTTPException(status_code=422, detail="slug_and_name_required")
    try:
        with auth_db() as conn:
            company_id = create_company(conn, slug, name)
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="company_slug_taken")
    return {"id": company_id, "slug": slug, "name": name}


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

@router.get("/users")
def list_users(_: dict = Depends(require_admin)):
    with auth_db() as conn:
        users = conn.execute(
            "SELECT id, email, display_name, created_at FROM users ORDER BY created_at ASC"
        ).fetchall()
        result = []
        for u in users:
            memberships = conn.execute(
                """SELECT m.id AS membership_id, m.company_id, m.role,
                          c.slug AS company_slug, c.name AS company_name
                   FROM memberships m JOIN companies c ON c.id = m.company_id
                   WHERE m.user_id = ? ORDER BY m.created_at ASC""",
                (u["id"],),
            ).fetchall()
            result.append({
                "id": u["id"],
                "email": u["email"],
                "display_name": u["display_name"],
                "created_at": u["created_at"],
                "memberships": [dict(m) for m in memberships],
            })
    return result


@router.post("/users", status_code=201)
def create_user_endpoint(body: CreateUserRequest, _: dict = Depends(require_admin)):
    if not body.password or len(body.password) < 8:
        raise HTTPException(status_code=422, detail="password_too_short")
    email = body.email.strip().lower()
    if not email:
        raise HTTPException(status_code=422, detail="email_required")
    try:
        with auth_db() as conn:
            user_id = create_user(
                conn,
                email=email,
                password=body.password,
                display_name=body.display_name,
            )
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="email_taken")
    return {"id": user_id, "email": email, "display_name": body.display_name}


@router.post("/users/{user_id}/assign")
def assign_user(user_id: str, body: AssignUserRequest, _: dict = Depends(require_admin)):
    valid_roles = {"owner", "admin", "member"}
    if body.role not in valid_roles:
        raise HTTPException(status_code=422, detail=f"invalid_role; allowed: {sorted(valid_roles)}")
    with auth_db() as conn:
        user = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="user_not_found")
        company = conn.execute(
            "SELECT id FROM companies WHERE id = ?", (body.company_id,)
        ).fetchone()
        if not company:
            raise HTTPException(status_code=404, detail="company_not_found")
        existing = conn.execute(
            "SELECT id FROM memberships WHERE company_id = ? AND user_id = ?",
            (body.company_id, user_id),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE memberships SET role = ? WHERE company_id = ? AND user_id = ?",
                (body.role, body.company_id, user_id),
            )
            membership_id = existing["id"]
        else:
            membership_id = create_membership(conn, body.company_id, user_id, role=body.role)
    return {
        "membership_id": membership_id,
        "user_id": user_id,
        "company_id": body.company_id,
        "role": body.role,
    }


@router.post("/users/{user_id}/reset-password")
def reset_password(user_id: str, body: ResetPasswordRequest, _: dict = Depends(require_admin)):
    if not body.new_password or len(body.new_password) < 8:
        raise HTTPException(status_code=422, detail="password_too_short")
    with auth_db() as conn:
        user = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="user_not_found")
        new_hash = hash_password(body.new_password)
        conn.execute(
            "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
            (new_hash, datetime.now(timezone.utc).isoformat(), user_id),
        )
    return {"ok": True}
