"""
Phase 2b dual-auth trust bridge.

resolve_caller() decodes EITHER a real-auth access token OR a pilot JWT and returns
a CurrentTenant whose tenant_id is ALWAYS a company slug — never a company UUID.

NOT wired into protected_router yet. Import and smoke-test only until Step 4.
"""

import jwt
from fastapi import HTTPException, Request

from app.auth import JWT_ALGORITHM, JWT_SECRET, CurrentTenant
from app.auth_tokens import decode_access_token
from app.db import auth_db, get_company_by_id, get_first_membership


def resolve_caller(request: Request) -> CurrentTenant:
    """
    Unified token resolver for protected routes (Phase 2b).

    Decode order:
      1. Real-auth access token (TRUELINE_AUTH_JWT_SECRET, typ=access required).
         On success: user + first membership + company slug → CurrentTenant.
      2. Pilot JWT (TRUELINE_JWT_SECRET, tenant_id claim required).

    INVARIANT: CurrentTenant.tenant_id is always a company slug, never a UUID.
    This function has no side effects — it does not write to _current_tenant_ctx.
    The wiring step (Step 4) must add that write after calling resolve_caller().
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        request.state.auth_path = None
        request.state.auth_outcome = "missing_header"
        raise HTTPException(
            status_code=401, detail="Missing or invalid Authorization header."
        )
    token = auth_header[len("Bearer "):]

    # ── Path A: real-auth access token ──────────────────────────────────────
    try:
        claims = decode_access_token(token)
        # Token is valid and typ == "access". Resolve slug from company UUID.
        user_id = claims.get("sub")
        company_id = claims.get("company_id")
        if not user_id or not company_id:
            request.state.auth_path = "realauth"
            request.state.auth_outcome = "malformed_claims"
            raise HTTPException(status_code=401, detail="Malformed access token claims.")

        with auth_db() as conn:
            user = conn.execute(
                "SELECT id, email FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            if not user:
                request.state.auth_path = "realauth"
                request.state.auth_outcome = "user_not_found"
                raise HTTPException(status_code=401, detail="user_not_found")

            membership = get_first_membership(conn, user_id)
            if not membership:
                request.state.auth_path = "realauth"
                request.state.auth_outcome = "no_company"
                raise HTTPException(status_code=401, detail="no_company_assigned")

            company = get_company_by_id(conn, membership["company_id"])
            if not company:
                request.state.auth_path = "realauth"
                request.state.auth_outcome = "company_not_found"
                raise HTTPException(status_code=401, detail="company_not_found")

        # Slug is the tenant namespace — NEVER use company UUID here.
        request.state.auth_path = "realauth"
        request.state.auth_outcome = "realauth_ok"
        request.state.caller_tenant_slug = company["slug"]
        request.state.user_id = user["id"]
        request.state.company_id = membership["company_id"]
        request.state.role = membership["role"]
        return CurrentTenant(
            tenant_id=company["slug"],
            user_id=user["id"],
            email=user["email"],
        )

    except HTTPException:
        raise  # surface user/company lookup failures as-is

    except jwt.ExpiredSignatureError:
        # Signature matched real-auth secret but token is expired.
        # Definitively a real-auth token — do NOT fall back to pilot path.
        request.state.auth_path = "realauth"
        request.state.auth_outcome = "expired_realauth"
        raise HTTPException(status_code=401, detail="Token expired.")

    except jwt.InvalidTokenError:
        # Signature mismatch, decode error, or wrong typ — could be a pilot token.
        pass

    # ── Path B: pilot JWT fallback ───────────────────────────────────────────
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        request.state.auth_path = "pilot"
        request.state.auth_outcome = "token_expired"
        raise HTTPException(status_code=401, detail="Token expired.")
    except jwt.InvalidTokenError:
        request.state.auth_path = "pilot"
        request.state.auth_outcome = "invalid_token"
        raise HTTPException(status_code=401, detail="Invalid token.")

    tenant_id = payload.get("tenant_id")
    if not tenant_id or not isinstance(tenant_id, str) or not tenant_id.strip():
        request.state.auth_path = "pilot"
        request.state.auth_outcome = "pilot_no_tenant"
        raise HTTPException(
            status_code=401, detail="Token missing required tenant_id claim."
        )

    request.state.auth_path = "pilot"
    request.state.auth_outcome = "pilot_ok"
    request.state.caller_tenant_slug = tenant_id.strip()
    request.state.user_id = payload.get("user_id")
    request.state.company_id = None
    request.state.role = None
    return CurrentTenant(
        tenant_id=tenant_id.strip(),
        user_id=payload.get("user_id"),
        email=payload.get("email"),
    )
