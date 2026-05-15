"""
V1 admin / user-management endpoints.

Role model:
  owner — global platform admin; all companies, all users
  admin — company admin; own company's users only; cannot create companies
  member — no admin access (blocked at auth layer)

All routes require at least owner-or-admin role (require_admin dependency).
Owner-only routes use require_owner.
Never returns password hashes. Uses existing db.py helpers throughout.
"""

import re
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


def _decode_claims(credentials: Optional[HTTPAuthorizationCredentials]) -> dict:
    if not credentials:
        raise HTTPException(status_code=401, detail="missing_token")
    try:
        return decode_access_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="token_expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="invalid_token")


def require_admin(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> dict:
    """Validate JWT and enforce owner-or-admin role."""
    claims = _decode_claims(credentials)
    if claims.get("role") not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="admin_required")
    return claims


def require_owner(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> dict:
    """Validate JWT and enforce owner-only role."""
    claims = _decode_claims(credentials)
    if claims.get("role") != "owner":
        raise HTTPException(status_code=403, detail="owner_required")
    return claims


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

def _slugify(name: str) -> str:
    s = name.strip().lower()
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"[^a-z0-9-]", "", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-")


class CreateCompanyRequest(BaseModel):
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


class UpdateUserRequest(BaseModel):
    display_name: Optional[str] = None


# ---------------------------------------------------------------------------
# Companies — owner only
# ---------------------------------------------------------------------------

@router.get("/companies")
def list_companies(claims: dict = Depends(require_admin)):
    """Owners see all companies; admins see only their own."""
    with auth_db() as conn:
        if claims["role"] == "owner":
            rows = conn.execute(
                "SELECT id, slug, name, created_at FROM companies ORDER BY created_at ASC"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, slug, name, created_at FROM companies WHERE id = ?",
                (claims["company_id"],),
            ).fetchall()
    return [dict(r) for r in rows]


@router.post("/companies", status_code=201)
def create_company_endpoint(body: CreateCompanyRequest, _: dict = Depends(require_owner)):
    """Only platform owners may create companies."""
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="name_required")
    base_slug = _slugify(name)
    if not base_slug:
        raise HTTPException(status_code=422, detail="name_produces_empty_slug")
    with auth_db() as conn:
        candidate = base_slug
        for i in range(2, 12):
            if not conn.execute("SELECT id FROM companies WHERE slug = ?", (candidate,)).fetchone():
                break
            candidate = f"{base_slug}-{i}"
        else:
            raise HTTPException(status_code=409, detail="company_slug_taken")
        company_id = create_company(conn, candidate, name)
    return {"id": company_id, "slug": candidate, "name": name}


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

@router.get("/users")
def list_users(claims: dict = Depends(require_admin)):
    """Owners see all users; admins see only users in their own company."""
    with auth_db() as conn:
        if claims["role"] == "owner":
            users = conn.execute(
                "SELECT id, email, display_name, created_at, disabled_at "
                "FROM users ORDER BY created_at ASC"
            ).fetchall()
        else:
            users = conn.execute(
                """SELECT u.id, u.email, u.display_name, u.created_at, u.disabled_at
                   FROM users u
                   JOIN memberships m ON m.user_id = u.id
                   WHERE m.company_id = ?
                   ORDER BY u.created_at ASC""",
                (claims["company_id"],),
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
                "disabled_at": u["disabled_at"],
                "memberships": [dict(m) for m in memberships],
            })
    return result


@router.patch("/users/{user_id}")
def update_user(user_id: str, body: UpdateUserRequest, claims: dict = Depends(require_admin)):
    """Update mutable user fields (currently display_name). Never touches password hashes."""
    with auth_db() as conn:
        user = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="user_not_found")
        _assert_user_in_scope(conn, user_id, claims)
        if body.display_name is not None:
            dn = body.display_name.strip() or None
            conn.execute(
                "UPDATE users SET display_name = ?, updated_at = ? WHERE id = ?",
                (dn, _now(), user_id),
            )
    return {"ok": True}


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
def assign_user(user_id: str, body: AssignUserRequest, claims: dict = Depends(require_admin)):
    valid_roles = {"owner", "admin", "member"}
    if body.role not in valid_roles:
        raise HTTPException(status_code=422, detail=f"invalid_role; allowed: {sorted(valid_roles)}")

    # Admins can only assign within their own company and cannot grant owner role.
    if claims["role"] != "owner":
        if body.company_id != claims["company_id"]:
            raise HTTPException(status_code=403, detail="admin_can_only_assign_to_own_company")
        if body.role == "owner":
            raise HTTPException(status_code=403, detail="admin_cannot_grant_owner_role")

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
def reset_password(user_id: str, body: ResetPasswordRequest, claims: dict = Depends(require_admin)):
    if not body.new_password or len(body.new_password) < 8:
        raise HTTPException(status_code=422, detail="password_too_short")
    with auth_db() as conn:
        user = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="user_not_found")
        # Admins can only reset passwords for users in their company.
        if claims["role"] != "owner":
            membership = conn.execute(
                "SELECT id FROM memberships WHERE user_id = ? AND company_id = ?",
                (user_id, claims["company_id"]),
            ).fetchone()
            if not membership:
                raise HTTPException(status_code=403, detail="not_in_your_company")
        new_hash = hash_password(body.new_password)
        conn.execute(
            "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
            (new_hash, _now(), user_id),
        )
    return {"ok": True}


# ---------------------------------------------------------------------------
# User lifecycle — disable / enable
# ---------------------------------------------------------------------------

def _assert_user_in_scope(conn, user_id: str, claims: dict) -> None:
    """Raise 403 if non-owner admin tries to act on a user outside their company."""
    if claims["role"] == "owner":
        return
    membership = conn.execute(
        "SELECT id FROM memberships WHERE user_id = ? AND company_id = ?",
        (user_id, claims["company_id"]),
    ).fetchone()
    if not membership:
        raise HTTPException(status_code=403, detail="not_in_your_company")


@router.post("/users/{user_id}/disable")
def disable_user(user_id: str, claims: dict = Depends(require_admin)):
    with auth_db() as conn:
        user = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="user_not_found")
        _assert_user_in_scope(conn, user_id, claims)
        conn.execute(
            "UPDATE users SET disabled_at = ?, updated_at = ? WHERE id = ?",
            (_now(), _now(), user_id),
        )
    return {"ok": True}


@router.post("/users/{user_id}/enable")
def enable_user(user_id: str, claims: dict = Depends(require_admin)):
    with auth_db() as conn:
        user = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="user_not_found")
        _assert_user_in_scope(conn, user_id, claims)
        conn.execute(
            "UPDATE users SET disabled_at = NULL, updated_at = ? WHERE id = ?",
            (_now(), user_id),
        )
    return {"ok": True}


# ---------------------------------------------------------------------------
# Hard-delete endpoints — beta cleanup only
# ---------------------------------------------------------------------------

@router.delete("/users/{user_id}", status_code=200)
def delete_user(user_id: str, claims: dict = Depends(require_admin)):
    """
    Permanently remove a user.
    Cascades: refresh_tokens → memberships → user row.
    Guards:
      - Cannot delete yourself.
      - Admin cannot delete a user that holds any 'owner' membership.
      - Admin can only delete users in their own company.
    """
    if user_id == claims.get("sub"):
        raise HTTPException(status_code=403, detail="cannot_delete_self")

    with auth_db() as conn:
        user = conn.execute(
            "SELECT id, email FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="user_not_found")

        if claims["role"] != "owner":
            # Must be in admin's company.
            membership = conn.execute(
                "SELECT id FROM memberships WHERE user_id = ? AND company_id = ?",
                (user_id, claims["company_id"]),
            ).fetchone()
            if not membership:
                raise HTTPException(status_code=403, detail="not_in_your_company")
            # Admins cannot delete users with an owner role in any company.
            owner_ms = conn.execute(
                "SELECT id FROM memberships WHERE user_id = ? AND role = 'owner'",
                (user_id,),
            ).fetchone()
            if owner_ms:
                raise HTTPException(status_code=403, detail="admin_cannot_delete_owner_user")

        conn.execute("DELETE FROM refresh_tokens WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM memberships WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))

    return {"ok": True, "deleted_user_id": user_id}


@router.delete("/companies/{company_id}", status_code=200)
def delete_company(company_id: str, _: dict = Depends(require_owner)):
    """
    Permanently remove a company.
    Owner only. Blocked if any memberships or projects reference it.
    Does NOT touch upload files — server-side evidence is never auto-cascaded.
    """
    with auth_db() as conn:
        company = conn.execute(
            "SELECT id, name FROM companies WHERE id = ?", (company_id,)
        ).fetchone()
        if not company:
            raise HTTPException(status_code=404, detail="company_not_found")

        membership_count = conn.execute(
            "SELECT COUNT(*) FROM memberships WHERE company_id = ?", (company_id,)
        ).fetchone()[0]
        if membership_count > 0:
            raise HTTPException(
                status_code=409,
                detail=f"company_has_users: remove {membership_count} user(s) first",
            )

        project_count = conn.execute(
            "SELECT COUNT(*) FROM projects WHERE company_id = ?", (company_id,)
        ).fetchone()[0]
        if project_count > 0:
            raise HTTPException(
                status_code=409,
                detail=f"company_has_projects: remove {project_count} project(s) first",
            )

        conn.execute("DELETE FROM companies WHERE id = ?", (company_id,))

    return {"ok": True, "deleted_company_id": company_id}
