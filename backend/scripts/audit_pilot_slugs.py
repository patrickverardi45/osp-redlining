"""
Read-only pre-rollout audit: compare active pilot slugs in session data
against companies.slug in the auth DB.

Exit 0  — all session slugs have a matching companies row.
Exit 1  — one or more session slugs are missing from companies (blocker).

Usage (from repo root, venv active):
    python backend/scripts/audit_pilot_slugs.py

Override DB paths via env:
    TRUELINE_AUTH_DB_PATH=/path/to/auth.db python backend/scripts/audit_pilot_slugs.py
    OSP_UPLOAD_DIR=/path/to/uploads      python backend/scripts/audit_pilot_slugs.py
"""

import json
import os
import sqlite3
import sys
from pathlib import Path

# ── Resolve paths ────────────────────────────────────────────────────────────

_SCRIPT_DIR = Path(__file__).resolve().parent
_BASE_DIR = _SCRIPT_DIR.parent  # backend/

_UPLOADS_DIR = Path(os.getenv("OSP_UPLOAD_DIR") or str(_BASE_DIR / "uploads"))
_SESSION_DB_PATH = _UPLOADS_DIR / "session_store.db"
_AUTH_DB_PATH = Path(
    os.getenv("TRUELINE_AUTH_DB_PATH") or str(_UPLOADS_DIR / "auth.db")
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _collect_session_slugs() -> set[str]:
    """Return all distinct non-empty tenant_id values in session_store.db."""
    if not _SESSION_DB_PATH.exists():
        print(f"  [WARN] Session DB not found: {_SESSION_DB_PATH}")
        return set()

    slugs: set[str] = set()
    with sqlite3.connect(_SESSION_DB_PATH) as conn:
        rows = conn.execute("SELECT session_json FROM sessions").fetchall()

    for (blob,) in rows:
        try:
            data = json.loads(blob)
        except (json.JSONDecodeError, TypeError):
            continue
        tid = data.get("tenant_id")
        if tid and isinstance(tid, str) and tid.strip():
            slugs.add(tid.strip())

    return slugs


def _collect_company_slugs() -> set[str]:
    """Return all slug values in the companies table."""
    if not _AUTH_DB_PATH.exists():
        print(f"  [WARN] Auth DB not found: {_AUTH_DB_PATH}")
        return set()

    with sqlite3.connect(_AUTH_DB_PATH) as conn:
        rows = conn.execute("SELECT slug FROM companies").fetchall()

    return {row[0] for row in rows if row[0]}


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    print("TrueLine pilot-slug audit")
    print(f"  Session DB : {_SESSION_DB_PATH}")
    print(f"  Auth DB    : {_AUTH_DB_PATH}")
    print()

    session_slugs = _collect_session_slugs()
    company_slugs = _collect_company_slugs()

    matched = session_slugs & company_slugs
    missing = session_slugs - company_slugs   # in sessions but no companies row
    orphan  = company_slugs - session_slugs   # companies row but no active sessions

    print(f"Session slugs found : {len(session_slugs)}")
    print(f"Company slugs found : {len(company_slugs)}")
    print(f"Matched             : {len(matched)}")
    print(f"Missing (BLOCKER)   : {len(missing)}")
    print(f"Orphan companies    : {len(orphan)}")
    print()

    if matched:
        print("Matched slugs:")
        for s in sorted(matched):
            print(f"  OK  {s}")
        print()

    if missing:
        print("MISSING — session slugs with no companies row (dual-auth will break):")
        for s in sorted(missing):
            print(f"  !!  {s}")
        print()
        print("Fix: run backend/scripts/bootstrap_auth.py --slug <slug> for each missing entry.")
        print()

    if orphan:
        print("Orphan companies (no active sessions — informational only):")
        for s in sorted(orphan):
            print(f"  --  {s}")
        print()

    if not session_slugs:
        print("No session slugs found — nothing to validate.")
        return 0

    if missing:
        print("RESULT: FAIL — rollout blocked until missing slugs are bootstrapped.")
        return 1

    print("RESULT: PASS — all session slugs have a matching companies row.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
