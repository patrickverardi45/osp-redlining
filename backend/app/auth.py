import os
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from typing import Optional

import jwt
from fastapi import Request
from fastapi.exceptions import HTTPException

JWT_SECRET = os.getenv("TRUELINE_JWT_SECRET")
assert JWT_SECRET, "TRUELINE_JWT_SECRET must be set before starting the server."

JWT_ALGORITHM = "HS256"


@dataclass
class CurrentTenant:
    tenant_id: str
    user_id: Optional[str] = None
    email: Optional[str] = None


def get_current_tenant(request: Request) -> CurrentTenant:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header.")
    token = auth_header[len("Bearer "):]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token.")
    tenant_id = payload.get("tenant_id")
    if not tenant_id or not isinstance(tenant_id, str) or not tenant_id.strip():
        raise HTTPException(status_code=401, detail="Token missing required tenant_id claim.")
    return CurrentTenant(
        tenant_id=tenant_id.strip(),
        user_id=payload.get("user_id"),
        email=payload.get("email"),
    )


def issue_pilot_token(
    tenant_id: str,
    user_id: Optional[str] = None,
    email: Optional[str] = None,
    ttl_days: int = 90,
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "tenant_id": tenant_id,
        "user_id": user_id,
        "email": email,
        "iat": now,
        "exp": now + timedelta(days=ttl_days),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
