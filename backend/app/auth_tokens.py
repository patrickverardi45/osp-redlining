"""
Phase 1 real auth token helpers.

Uses TRUELINE_AUTH_JWT_SECRET — separate from TRUELINE_JWT_SECRET (pilot auth).
Access tokens: HS256 JWTs, 15 min.
Refresh tokens: opaque random strings, SHA-256 hashed before storage.
"""

import hashlib
import os
import secrets
import sqlite3
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple

import jwt

AUTH_JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_TTL = timedelta(minutes=15)
REFRESH_TOKEN_TTL = timedelta(days=14)


def _secret() -> str:
    s = os.getenv("TRUELINE_AUTH_JWT_SECRET")
    if not s:
        raise RuntimeError("TRUELINE_AUTH_JWT_SECRET is not set")
    return s


def create_access_token(user_row: sqlite3.Row, membership_row: sqlite3.Row) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_row["id"],
        "email": user_row["email"],
        "company_id": membership_row["company_id"],
        "role": membership_row["role"],
        "typ": "access",
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + ACCESS_TOKEN_TTL,
    }
    return jwt.encode(payload, _secret(), algorithm=AUTH_JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Decode and validate; raises jwt.InvalidTokenError subclasses on failure."""
    payload = jwt.decode(token, _secret(), algorithms=[AUTH_JWT_ALGORITHM])
    if payload.get("typ") != "access":
        raise jwt.InvalidTokenError("invalid_token_type")
    return payload


# ---------------------------------------------------------------------------
# Refresh token helpers — callers supply an open sqlite3.Connection
# ---------------------------------------------------------------------------

def _hash_refresh(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def create_refresh_token(conn: sqlite3.Connection, user_id: str) -> Tuple[str, str]:
    """Insert hashed refresh token row. Returns (raw_token, expires_at_iso)."""
    raw = secrets.token_urlsafe(48)
    token_hash = _hash_refresh(raw)
    now = datetime.now(timezone.utc)
    expires_at = (now + REFRESH_TOKEN_TTL).isoformat()
    conn.execute(
        "INSERT INTO refresh_tokens (id, user_id, token_hash, expires_at, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), user_id, token_hash, expires_at, now.isoformat()),
    )
    return raw, expires_at


def find_active_refresh(conn: sqlite3.Connection, raw: str) -> Optional[sqlite3.Row]:
    """Return row if token exists, is not revoked, and is not expired."""
    now = datetime.now(timezone.utc).isoformat()
    return conn.execute(
        "SELECT * FROM refresh_tokens "
        "WHERE token_hash = ? AND revoked_at IS NULL AND expires_at > ?",
        (_hash_refresh(raw), now),
    ).fetchone()


def revoke_refresh_token(conn: sqlite3.Connection, raw: str) -> bool:
    """Mark token revoked. Returns True if a row was updated."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE refresh_tokens SET revoked_at = ? "
        "WHERE token_hash = ? AND revoked_at IS NULL",
        (now, _hash_refresh(raw)),
    )
    return conn.execute("SELECT changes()").fetchone()[0] > 0


def rotate_refresh_token(
    conn: sqlite3.Connection, raw: str
) -> Tuple[str, str, str]:
    """
    Revoke old token, issue new one.
    Returns (user_id, new_raw_token, new_expires_at_iso).
    Raises ValueError("invalid_refresh_token") if old token is not active.
    """
    old_row = find_active_refresh(conn, raw)
    if not old_row:
        raise ValueError("invalid_refresh_token")
    user_id = old_row["user_id"]
    revoke_refresh_token(conn, raw)
    new_raw, new_expires_at = create_refresh_token(conn, user_id)
    return user_id, new_raw, new_expires_at
