"""
Mint a pilot JWT for one tenant and print it to stdout.

Usage (from repo root, venv active):
    python backend/scripts/issue_pilot_token.py --tenant-id acme-corp --email ops@acme.com
"""

import argparse
import re
import sys
import os


_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$|^[a-z0-9]$")


def _validate_slug(value: str) -> str:
    if not _SLUG_RE.match(value):
        raise argparse.ArgumentTypeError(
            f"Invalid tenant slug {value!r}. "
            "Use lowercase a-z, 0-9, and hyphens only; no leading/trailing hyphen."
        )
    return value


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mint a TrueLine pilot JWT for a given tenant."
    )
    parser.add_argument(
        "--tenant-id",
        required=True,
        type=_validate_slug,
        metavar="SLUG",
        help="Tenant identifier slug (lowercase, a-z0-9-, no leading/trailing hyphen).",
    )
    parser.add_argument(
        "--email",
        default=None,
        metavar="EMAIL",
        help="Optional email address to embed in the token.",
    )
    parser.add_argument(
        "--user-id",
        default=None,
        metavar="USER_ID",
        help="Optional user identifier to embed in the token.",
    )
    parser.add_argument(
        "--ttl-days",
        type=int,
        default=30,
        metavar="DAYS",
        help="Token lifetime in days (default: 30). Negative values create already-expired tokens for testing.",
    )
    args = parser.parse_args()

    if not os.getenv("TRUELINE_JWT_SECRET"):
        print(
            "ERROR: TRUELINE_JWT_SECRET environment variable is not set.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Import after env check so auth.py's module-level assert does not fire
    # before we can print a useful error message.
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from app.auth import issue_pilot_token  # noqa: E402

    token = issue_pilot_token(
        tenant_id=args.tenant_id,
        user_id=args.user_id,
        email=args.email,
        ttl_days=args.ttl_days,
    )
    print(token)


if __name__ == "__main__":
    main()
