"""Permanent v2 product foundation — the processing_job lifecycle (contract-only).

One processing_job is a single end-to-end run scoped to exactly one customer_project. It carries the
ONE authoritative status (the v1 monolith's defect was several disagreeing readiness signals — see
docs/product_v1_workflow_salvage_audit.md items 4c/4d). The lifecycle is the contract's state machine
(docs/product_v2_permanent_pipeline_contract.md §2); transitions are server-authoritative and audited
(from/to/at/by/reason). The record also reserves typed OUTPUT SLOTS for downstream stages
(redline_manifest, artifact_bundle, export_package) — interface only; their producers are later,
separately-authorized lanes. No engine/render/manifest/export work happens here.

Durable + adapter-neutral: the job record is JSON on disk under the customer_project scope, so status
survives a restart (never in-memory global state). Contract-only: no engine, no renderer, no web/backend
wiring, no AI/OCR.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from truelinev2.contracts.customer_project import (
    assert_same_project,
    project_root,
    validate_customer_project_id,
)

JOB_RECORD_FORMAT = "trueline-processing-job-1"
PROCESSING_JOBS_SUBDIR = "processing_jobs"
JOB_RECORD_FILENAME = "_processing_job.json"

# Safe job id charset (same rule the customer_project id uses): no separators/traversal, <= 63 chars.
_JOB_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")

# Lifecycle states (contract §2).
CREATED = "CREATED"
UPLOADING = "UPLOADING"
EXTRACTING = "EXTRACTING"
AWAITING_REVIEW = "AWAITING_REVIEW"
PLACING = "PLACING"
PLACED = "PLACED"
CLOSEOUT_REVIEW = "CLOSEOUT_REVIEW"
CLOSED = "CLOSED"
FAILED = "FAILED"

JOB_STATES = (CREATED, UPLOADING, EXTRACTING, AWAITING_REVIEW, PLACING, PLACED,
              CLOSEOUT_REVIEW, CLOSED, FAILED)
TERMINAL_STATES = (CLOSED, FAILED)

# Allowed forward transitions. Any non-terminal state may ALSO go to FAILED (reason required).
ALLOWED_TRANSITIONS = {
    CREATED: (UPLOADING,),
    UPLOADING: (EXTRACTING,),
    EXTRACTING: (AWAITING_REVIEW,),
    AWAITING_REVIEW: (PLACING,),
    PLACING: (PLACED,),
    PLACED: (CLOSEOUT_REVIEW,),
    CLOSEOUT_REVIEW: (CLOSED,),
    CLOSED: (),
    FAILED: (),
}

# Typed output slots reserved for downstream stages (interface only; producers are later lanes).
OUTPUT_SLOT_NAMES = ("redline_manifest", "artifact_bundle", "export_package")


class ProcessingJobError(ValueError):
    """Base processing_job error."""


class InvalidJobIdError(ProcessingJobError):
    """job id is missing or not filesystem/URL-safe."""


class JobNotFoundError(ProcessingJobError):
    """No stored record for the requested job."""


class IllegalTransitionError(ProcessingJobError):
    """Requested status transition is not permitted from the current status."""


class UnknownSlotError(ProcessingJobError):
    """Requested output slot is not one of OUTPUT_SLOT_NAMES."""


def validate_job_id(job_id) -> str:
    """Return the id iff it is a safe job id; else raise InvalidJobIdError."""
    if not isinstance(job_id, str) or not _JOB_ID_RE.match(job_id):
        raise InvalidJobIdError("job id must match %s (got %r)" % (_JOB_ID_RE.pattern, job_id))
    return job_id


def job_dir(store_root, customer_project_id, job_id) -> Path:
    """Scoped directory for one job: ``<store_root>/customer_projects/<cp>/processing_jobs/<job>``."""
    validate_customer_project_id(customer_project_id)
    validate_job_id(job_id)
    return project_root(store_root, customer_project_id) / PROCESSING_JOBS_SUBDIR / job_id


def _job_record_path(store_root, customer_project_id, job_id) -> Path:
    return job_dir(store_root, customer_project_id, job_id) / JOB_RECORD_FILENAME


def create_job(store_root, customer_project_id, job_id, created_at, created_by) -> dict:
    """Create a new processing_job in status CREATED with an opening audit entry. A duplicate job_id
    with an existing record raises (no silent overwrite). Returns the new record."""
    validate_customer_project_id(customer_project_id)
    validate_job_id(job_id)
    jpath = _job_record_path(store_root, customer_project_id, job_id)
    if jpath.exists():
        raise ProcessingJobError("job already exists: %s/%s" % (customer_project_id, job_id))
    record = {
        "record_format": JOB_RECORD_FORMAT,
        "job_id": job_id,
        "customer_project_id": customer_project_id,
        "status": CREATED,
        "created_at": created_at,
        "created_by": created_by,
        "uploads": [],
        "slots": {name: None for name in OUTPUT_SLOT_NAMES},
        "audit": [{"from": None, "to": CREATED, "at": created_at,
                   "by": created_by, "reason": "job created"}],
    }
    jpath.parent.mkdir(parents=True, exist_ok=True)
    jpath.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def load_job(store_root, customer_project_id, job_id) -> dict:
    """Load a stored job; raise JobNotFoundError if absent. Verifies the record is in-scope."""
    jpath = _job_record_path(store_root, customer_project_id, job_id)
    if not jpath.is_file():
        raise JobNotFoundError("no job record for %s/%s" % (customer_project_id, job_id))
    job = json.loads(jpath.read_text(encoding="utf-8"))
    assert_same_project(customer_project_id, job.get("customer_project_id"))
    return job


def write_job(store_root, job) -> str:
    """Persist a job record under its OWN (cp, job) scope (derived from the record, not ambient)."""
    cp = validate_customer_project_id(job["customer_project_id"])
    jid = validate_job_id(job["job_id"])
    jpath = _job_record_path(store_root, cp, jid)
    jpath.parent.mkdir(parents=True, exist_ok=True)
    jpath.write_text(json.dumps(job, indent=2) + "\n", encoding="utf-8")
    return str(jpath)


def transition(store_root, customer_project_id, job_id, to_status, *, at, by, reason=None) -> dict:
    """Apply one server-authoritative, audited status transition. Raises IllegalTransitionError for a
    disallowed move; a transition to FAILED requires a reason. Returns the updated job."""
    job = load_job(store_root, customer_project_id, job_id)
    frm = job["status"]
    if to_status not in JOB_STATES:
        raise IllegalTransitionError("unknown target status %r" % (to_status,))
    allowed = frm not in TERMINAL_STATES and (
        to_status in ALLOWED_TRANSITIONS.get(frm, ()) or to_status == FAILED)
    if not allowed:
        raise IllegalTransitionError("illegal transition %s -> %s" % (frm, to_status))
    if to_status == FAILED and not reason:
        raise ProcessingJobError("transition to FAILED requires a reason")
    job["status"] = to_status
    job["audit"].append({"from": frm, "to": to_status, "at": at, "by": by, "reason": reason})
    write_job(store_root, job)
    return job


def set_output_slot(store_root, customer_project_id, job_id, slot_name, slot_ref, *, at, by) -> dict:
    """Record a downstream output slot reference (INTERFACE ONLY — producers are later lanes). Raises
    UnknownSlotError for a name outside OUTPUT_SLOT_NAMES. Returns the updated job."""
    if slot_name not in OUTPUT_SLOT_NAMES:
        raise UnknownSlotError(
            "unknown output slot %r (expected one of %r)" % (slot_name, OUTPUT_SLOT_NAMES))
    job = load_job(store_root, customer_project_id, job_id)
    job["slots"][slot_name] = {"ref": slot_ref, "set_at": at, "set_by": by}
    write_job(store_root, job)
    return job
