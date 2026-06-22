"""Permanent v2 product foundation — the upload_pipeline intake + accepted-file inventory (contract-only).

Accepts product input files INTO one processing_job under its customer_project scope, records durable
per-file metadata, and stores bytes in the job-scoped layout. Replaces the v1 monolith's global, unscoped
upload path (single shared dir + CURRENT_ROUTE — docs/product_v1_workflow_salvage_audit.md 1a/1b). The
accepted kinds + upload-procedure contract are docs/product_v2_permanent_pipeline_contract.md §1.

EXTRACTION IS NOT PERFORMED HERE. Every accepted upload is recorded with extraction_status="queued"; no
OCR/AI/text-parse runs in this slice. AI/OCR output is untrusted and is gated behind review in a later,
separately-authorized lane. Contract-only: no engine, no renderer, no web/backend wiring, no AI/OCR.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from truelinev2.contracts.customer_project import assert_same_project
from truelinev2.contracts.processing_job import (
    CREATED,
    UPLOADING,
    job_dir,
    load_job,
    write_job,
)

UPLOADS_SUBDIR = "uploads"
PAYLOAD_BASENAME = "payload"
EXTRACTION_STATUS_QUEUED = "queued"

# Accepted upload kinds -> allowed extensions (contract §1). Unknown kinds/extensions are rejected.
ACCEPTED_KINDS = {
    "PLAN_PDF": (".pdf",),
    "BORE_LOG": (".csv", ".xlsx", ".pdf"),
    "GIS_ROUTE": (".kmz", ".kml"),
    # Image evidence (photos): stored as-is like any other upload — NEVER parsed. No extraction, no
    # image analysis, no fake evidence/proof output; extraction_status stays "queued".
    "PHOTO": (".jpg", ".jpeg", ".png", ".webp"),
}

# Uploads land BEFORE extraction begins (contract lifecycle). Once EXTRACTING starts, intake is closed.
UPLOADABLE_STATES = (CREATED, UPLOADING)

DEFAULT_MAX_BYTES = 100 * 1024 * 1024  # 100 MiB per file; callers may pass a smaller max_bytes.


class UploadError(ValueError):
    """Base upload_pipeline error."""


class UnknownKindError(UploadError):
    """Declared upload kind is not in ACCEPTED_KINDS."""


class RejectedExtensionError(UploadError):
    """File extension is not allowed for the declared kind."""


class FileTooLargeError(UploadError):
    """Upload exceeds the allowed byte budget."""


class EmptyUploadError(UploadError):
    """Upload has no bytes."""


class UploadsClosedError(UploadError):
    """Job is past the upload phase; no more uploads accepted."""


def _ext(filename) -> str:
    return Path(str(filename)).suffix.lower()


def validate_upload(kind, filename, size, *, max_bytes=DEFAULT_MAX_BYTES) -> None:
    """Validate kind + extension + size. Raises a specific UploadError subclass on rejection."""
    if kind not in ACCEPTED_KINDS:
        raise UnknownKindError(
            "unknown upload kind %r (expected one of %r)" % (kind, tuple(ACCEPTED_KINDS)))
    if _ext(filename) not in ACCEPTED_KINDS[kind]:
        raise RejectedExtensionError(
            "extension %r not allowed for kind %r (allowed: %r)"
            % (_ext(filename), kind, ACCEPTED_KINDS[kind]))
    if size <= 0:
        raise EmptyUploadError("refusing an empty upload")
    if size > max_bytes:
        raise FileTooLargeError("upload is %d bytes > max_bytes %d" % (size, max_bytes))


def accept_upload(store_root, customer_project_id, job_id, *, kind, filename, content,
                  stored_at, max_bytes=DEFAULT_MAX_BYTES) -> dict:
    """Validate + store one upload into a job and append its durable metadata record. Idempotent by
    content (same bytes -> same upload_id -> the existing record is returned, no duplicate file/record).
    Returns the upload record. Does NOT extract: extraction_status is always "queued"."""
    if not isinstance(content, (bytes, bytearray)):
        raise UploadError("content must be bytes")
    content = bytes(content)
    size = len(content)
    validate_upload(kind, filename, size, max_bytes=max_bytes)

    job = load_job(store_root, customer_project_id, job_id)
    assert_same_project(customer_project_id, job["customer_project_id"])
    if job["status"] not in UPLOADABLE_STATES:
        raise UploadsClosedError(
            "job status %r is past the upload phase (uploadable: %r)"
            % (job["status"], UPLOADABLE_STATES))

    sha = hashlib.sha256(content).hexdigest()
    upload_id = "up-" + sha[:12]

    # Idempotent by content within the job: an identical upload returns the existing record unchanged.
    for existing in job["uploads"]:
        if existing["upload_id"] == upload_id:
            return existing

    rel = "%s/%s/%s%s" % (UPLOADS_SUBDIR, upload_id, PAYLOAD_BASENAME, _ext(filename))
    dest = job_dir(store_root, customer_project_id, job_id) / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)

    record = {
        "upload_id": upload_id,
        "kind": kind,
        "original_filename": str(filename),
        "sha256": sha,
        "bytes": size,
        "stored_path": rel,
        "stored_at": stored_at,
        "extraction_status": EXTRACTION_STATUS_QUEUED,
    }
    job["uploads"].append(record)
    write_job(store_root, job)
    return record
