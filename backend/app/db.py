"""
TrueLine auth database — Phase 0 foundation.

Manages the SQLite schema for companies, users, memberships, projects,
and refresh tokens. Does NOT change any runtime behavior; the existing
pilot-token auth path in auth.py is untouched.

DB file: backend/uploads/auth.db (overridable via TRUELINE_AUTH_DB_PATH)
"""

import os
import sqlite3
import uuid
import bcrypt
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_DEFAULT_DB_PATH = Path(__file__).parent.parent / "uploads" / "auth.db"
AUTH_DB_PATH = Path(os.getenv("TRUELINE_AUTH_DB_PATH", str(_DEFAULT_DB_PATH)))


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    id          TEXT PRIMARY KEY,
    slug        TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT,
    display_name  TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memberships (
    id          TEXT PRIMARY KEY,
    company_id  TEXT NOT NULL REFERENCES companies(id),
    user_id     TEXT NOT NULL REFERENCES users(id),
    role        TEXT NOT NULL DEFAULT 'member',
    created_at  TEXT NOT NULL,
    UNIQUE (company_id, user_id)
);

CREATE TABLE IF NOT EXISTS projects (
    id          TEXT PRIMARY KEY,
    company_id  TEXT NOT NULL REFERENCES companies(id),
    slug        TEXT NOT NULL,
    name        TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    UNIQUE (company_id, slug)
);

CREATE TABLE IF NOT EXISTS refresh_tokens (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id),
    token_hash  TEXT NOT NULL UNIQUE,
    expires_at  TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    revoked_at  TEXT
);
"""


def init_auth_db() -> None:
    """Create tables if they don't exist. Safe to call multiple times."""
    AUTH_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(AUTH_DB_PATH) as conn:
        conn.executescript(_SCHEMA)
        conn.commit()


@contextmanager
def auth_db():
    """Context manager yielding a sqlite3.Connection with row_factory set."""
    conn = sqlite3.connect(AUTH_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_password(plaintext: str) -> str:
    """bcrypt hash; self-describing and safe to store directly."""
    return bcrypt.hashpw(plaintext.encode(), bcrypt.gensalt()).decode()


def verify_password(plaintext: str, stored_hash: str) -> bool:
    if not stored_hash:
        return False
    return bcrypt.checkpw(plaintext.encode(), stored_hash.encode())


# ---------------------------------------------------------------------------
# Company helpers
# ---------------------------------------------------------------------------

def get_company_by_slug(conn: sqlite3.Connection, slug: str) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM companies WHERE slug = ?", (slug,)
    ).fetchone()


def create_company(conn: sqlite3.Connection, slug: str, name: str) -> str:
    """Insert company and return its id. Raises IntegrityError if slug taken."""
    company_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO companies (id, slug, name, created_at) VALUES (?, ?, ?, ?)",
        (company_id, slug, name, _now()),
    )
    return company_id


# ---------------------------------------------------------------------------
# User helpers
# ---------------------------------------------------------------------------

def get_user_by_email(conn: sqlite3.Connection, email: str) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM users WHERE email = ?", (email.lower(),)
    ).fetchone()


def create_user(
    conn: sqlite3.Connection,
    email: str,
    password: Optional[str] = None,
    display_name: Optional[str] = None,
) -> str:
    """Insert user and return its id. Raises IntegrityError if email taken."""
    user_id = str(uuid.uuid4())
    pw_hash = hash_password(password) if password else None
    now = _now()
    conn.execute(
        "INSERT INTO users (id, email, password_hash, display_name, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, email.lower(), pw_hash, display_name, now, now),
    )
    return user_id


# ---------------------------------------------------------------------------
# Membership helpers
# ---------------------------------------------------------------------------

def get_membership(
    conn: sqlite3.Connection, company_id: str, user_id: str
) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM memberships WHERE company_id = ? AND user_id = ?",
        (company_id, user_id),
    ).fetchone()


def create_membership(
    conn: sqlite3.Connection, company_id: str, user_id: str, role: str = "owner"
) -> str:
    membership_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO memberships (id, company_id, user_id, role, created_at) VALUES (?, ?, ?, ?, ?)",
        (membership_id, company_id, user_id, role, _now()),
    )
    return membership_id
