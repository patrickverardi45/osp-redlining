"""Permanent v2 product foundation — the customer_project isolation root (contract-only).

`customer_project` is the isolation root of the v2 product pipeline: every processing job, upload, and
stored artifact is partitioned beneath exactly one customer_project, and no operation may cross from one
project's storage into another's. This replaces the v1 monolith's global, unscoped state (`CURRENT_ROUTE`,
a single shared upload dir) — see docs/product_v1_workflow_salvage_audit.md items 1b/1c and
docs/product_v2_permanent_pipeline_contract.md §"Strict isolation".

Generic-product rule (strict): a real customer/project name is OPAQUE RUNTIME DATA carried in
`display_name`; it is never validated against, embedded in, or derived from code. The only constrained
identifier is the filesystem/URL-safe `id`.

Filesystem-shaped + adapter-neutral (the same `customer_projects/<id>/` prefix maps onto an object-store
prefix). Contract-only: no engine, no renderer, no web/backend wiring, no AI/OCR.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from truelinev2.contracts.atomic_json import write_json_atomic

CUSTOMER_PROJECTS_SUBDIR = "customer_projects"
PROJECT_RECORD_FILENAME = "_customer_project.json"
RECORD_FORMAT = "trueline-customer-project-1"

# Safe, lowercase, filesystem- and URL-safe id: no separators, no traversal, no drive letters, <= 63 chars.
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")


class CustomerProjectError(ValueError):
    """Base customer_project error."""


class InvalidProjectIdError(CustomerProjectError):
    """customer_project id is missing or not filesystem/URL-safe."""


class ProjectNotFoundError(CustomerProjectError):
    """No stored record for the requested customer_project id."""


class CrossProjectAccessError(CustomerProjectError):
    """An operation tried to act across customer_project boundaries (the in-process analog of a 403)."""


def validate_customer_project_id(customer_project_id) -> str:
    """Return the id iff it is a safe customer_project id; else raise InvalidProjectIdError.

    `display_name` (the human/customer label) is intentionally NOT constrained — it is opaque runtime
    data carried elsewhere, never code.
    """
    if not isinstance(customer_project_id, str) or not _ID_RE.match(customer_project_id):
        raise InvalidProjectIdError(
            "customer_project id must match %s (got %r)" % (_ID_RE.pattern, customer_project_id))
    return customer_project_id


def _within_root(root: Path, target: Path) -> bool:
    r = os.path.realpath(str(root))
    t = os.path.realpath(str(target))
    return t == r or t.startswith(r + os.sep)


def project_root(store_root, customer_project_id) -> Path:
    """The scoped directory for a customer_project: ``<store_root>/customer_projects/<id>``.

    Pure path computation (creates nothing) with a defense-in-depth containment assert.
    """
    customer_project_id = validate_customer_project_id(customer_project_id)
    root = Path(store_root)
    dest = root / CUSTOMER_PROJECTS_SUBDIR / customer_project_id
    if not _within_root(root, dest):
        raise CrossProjectAccessError("resolved project path escapes the store root: %r" % str(dest))
    return dest


def assert_same_project(authenticated_customer_project_id, record_customer_project_id) -> None:
    """Raise CrossProjectAccessError unless the two ids are the same valid customer_project id."""
    a = validate_customer_project_id(authenticated_customer_project_id)
    b = validate_customer_project_id(record_customer_project_id)
    if a != b:
        raise CrossProjectAccessError(
            "cross-customer_project access denied (authenticated=%r, target=%r)" % (a, b))


def create_customer_project(store_root, customer_project_id, display_name, created_at) -> dict:
    """Create (idempotently) the scoped root + a durable record for a customer_project.

    `display_name` is stored verbatim as opaque runtime data; it is never inspected or constrained.
    """
    customer_project_id = validate_customer_project_id(customer_project_id)
    pdir = project_root(store_root, customer_project_id)
    pdir.mkdir(parents=True, exist_ok=True)
    record = {
        "record_format": RECORD_FORMAT,
        "id": customer_project_id,
        "display_name": display_name,
        "created_at": created_at,
    }
    write_json_atomic(pdir / PROJECT_RECORD_FILENAME, record)   # atomic; parent pre-created above
    return record


def load_customer_project(store_root, customer_project_id) -> dict:
    """Load a stored customer_project record; raise ProjectNotFoundError if absent."""
    customer_project_id = validate_customer_project_id(customer_project_id)
    p = project_root(store_root, customer_project_id) / PROJECT_RECORD_FILENAME
    if not p.is_file():
        raise ProjectNotFoundError("no customer_project record for %r" % customer_project_id)
    return json.loads(p.read_text(encoding="utf-8"))
