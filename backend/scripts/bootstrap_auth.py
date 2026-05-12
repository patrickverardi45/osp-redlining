"""
Bootstrap the TrueLine auth database with one company + owner user.

Idempotent: running twice with the same --company-slug / --email will print
a "already exists" notice and exit without duplicating any rows.

Usage (from repo root, venv active):
    python backend/scripts/bootstrap_auth.py \
        --company-slug acme-corp \
        --company-name "Acme Corp" \
        --email owner@acme.com \
        --password "change-me-123" \
        --display-name "Alice Owner"

If --password is omitted, a random 20-char password is generated and printed
once — store it somewhere safe, there is no recovery path yet.
"""

import argparse
import os
import re
import secrets
import string
import sys

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$|^[a-z0-9]$")


def _require_env():
    if not os.getenv("TRUELINE_JWT_SECRET"):
        print(
            "ERROR: TRUELINE_JWT_SECRET is not set. "
            "auth.py will assert-fail on import without it.",
            file=sys.stderr,
        )
        sys.exit(1)


def _validate_slug(value: str) -> str:
    if not _SLUG_RE.match(value):
        raise argparse.ArgumentTypeError(
            f"Invalid slug {value!r}. Use lowercase a-z, 0-9, hyphens; no leading/trailing hyphen."
        )
    return value


def _generate_password(length: int = 20) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bootstrap TrueLine auth DB with a company + owner user."
    )
    parser.add_argument("--company-slug", required=True, type=_validate_slug)
    parser.add_argument("--company-name", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument(
        "--password",
        default=None,
        help="Plaintext password to hash and store. Omit to auto-generate.",
    )
    parser.add_argument("--display-name", default=None)
    args = parser.parse_args()

    _require_env()

    # Add backend/ to sys.path so app.db resolves regardless of cwd.
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from app.db import init_auth_db, auth_db  # noqa: E402
    from app.db import (  # noqa: E402
        get_company_by_slug,
        create_company,
        get_user_by_email,
        create_user,
        get_membership,
        create_membership,
    )

    init_auth_db()

    generated_password: str | None = None
    if args.password is None:
        generated_password = _generate_password()
        password = generated_password
    else:
        password = args.password

    with auth_db() as conn:
        # ── Company ──────────────────────────────────────────────────────────
        company = get_company_by_slug(conn, args.company_slug)
        if company:
            company_id = company["id"]
            print(f"[skip] Company '{args.company_slug}' already exists (id={company_id})")
        else:
            company_id = create_company(conn, args.company_slug, args.company_name)
            print(f"[ok]   Created company '{args.company_name}' (slug={args.company_slug}, id={company_id})")

        # ── User ─────────────────────────────────────────────────────────────
        user = get_user_by_email(conn, args.email)
        if user:
            user_id = user["id"]
            print(f"[skip] User '{args.email}' already exists (id={user_id})")
        else:
            user_id = create_user(
                conn,
                email=args.email,
                password=password,
                display_name=args.display_name,
            )
            print(f"[ok]   Created user '{args.email}' (id={user_id})")
            if generated_password:
                print(f"\n  *** Auto-generated password: {generated_password}")
                print("  *** Store this now — it cannot be recovered.\n")

        # ── Membership ───────────────────────────────────────────────────────
        membership = get_membership(conn, company_id, user_id)
        if membership:
            print(
                f"[skip] Membership already exists "
                f"(company={args.company_slug}, user={args.email}, role={membership['role']})"
            )
        else:
            m_id = create_membership(conn, company_id, user_id, role="owner")
            print(
                f"[ok]   Bound user '{args.email}' to company '{args.company_slug}' "
                f"as owner (membership id={m_id})"
            )

    print("\nDone. Pilot token auth is unchanged — existing sessions continue to work.")


if __name__ == "__main__":
    main()
