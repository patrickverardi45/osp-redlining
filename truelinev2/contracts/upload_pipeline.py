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


# Phase-1 handwritten/scanned bore-log extraction: additive image extensions accepted for BORE_LOG ONLY
# when a caller explicitly opts in (route passes the settings flag). DEFAULT False everywhere -> the
# accepted-extension set for BORE_LOG is byte-identical to before this evolution.
IMAGE_BORELOG_EXTENSIONS = (".jpg", ".jpeg", ".png")


def _ext(filename) -> str:
    return Path(str(filename)).suffix.lower()


def _allowed_extensions(kind, allow_image_borelog) -> tuple:
    exts = ACCEPTED_KINDS[kind]
    if kind == "BORE_LOG" and allow_image_borelog:
        exts = exts + IMAGE_BORELOG_EXTENSIONS
    return exts


def validate_upload(kind, filename, size, *, max_bytes=DEFAULT_MAX_BYTES,
                    allow_image_borelog=False) -> None:
    """Validate kind + extension + size. Raises a specific UploadError subclass on rejection.
    ``allow_image_borelog`` (DEFAULT False, byte-identical) additionally accepts .jpg/.jpeg/.png for the
    BORE_LOG kind -- a scanned/photographed bore-log page, gated by the Phase-1 handwritten-extraction
    flag (never on for any other kind)."""
    if kind not in ACCEPTED_KINDS:
        raise UnknownKindError(
            "unknown upload kind %r (expected one of %r)" % (kind, tuple(ACCEPTED_KINDS)))
    allowed = _allowed_extensions(kind, allow_image_borelog)
    if _ext(filename) not in allowed:
        raise RejectedExtensionError(
            "extension %r not allowed for kind %r (allowed: %r)"
            % (_ext(filename), kind, allowed))
    if size <= 0:
        raise EmptyUploadError("refusing an empty upload")
    if size > max_bytes:
        raise FileTooLargeError("upload is %d bytes > max_bytes %d" % (size, max_bytes))


def accept_upload(store_root, customer_project_id, job_id, *, kind, filename, content,
                  stored_at, max_bytes=DEFAULT_MAX_BYTES, allow_image_borelog=False) -> dict:
    """Validate + store one upload into a job and append its durable metadata record. Idempotent by
    content (same bytes -> same upload_id -> the existing record is returned, no duplicate file/record).
    Returns the upload record. Does NOT extract: extraction_status is always "queued".
    ``allow_image_borelog`` (DEFAULT False, byte-identical) is forwarded to ``validate_upload``."""
    if not isinstance(content, (bytes, bytearray)):
        raise UploadError("content must be bytes")
    content = bytes(content)
    size = len(content)
    validate_upload(kind, filename, size, max_bytes=max_bytes, allow_image_borelog=allow_image_borelog)

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


# --------------------------------------------------------------------------- #
# Read-only byte-serving resolution (office-review photo display).
# --------------------------------------------------------------------------- #

# Fixed extension -> served content-type map for PHOTO byte-serving. Serving trusts ONLY the RECORDED
# upload kind + this map — never a client-declared type; anything outside it is not servable.
PHOTO_CONTENT_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


class UploadFileNotFoundError(UploadError):
    """No servable upload file: unknown upload_id, wrong kind, unsafe path, or missing payload —
    uniform not-found semantics on purpose (never confirms what exists under another kind/tenant)."""


def resolve_upload_file(store_root, customer_project_id, job_id, upload_id, *,
                        require_kind="PHOTO") -> dict:
    """Resolve one stored upload payload for READ-ONLY byte-serving (field-evidence office review).

    Tenant-safe by construction (the job loads through ``load_job``) and path-safe: the stored payload
    must resolve strictly INSIDE the job directory (the same containment assertion ``delete_job`` uses).
    Only an upload whose RECORDED kind == ``require_kind`` is servable — a mis-declared or non-photo
    file is never served as an image. Pure read: no record, lifecycle, slot, or status change.
    Returns ``{"path": Path, "content_type": str}``; raises UploadFileNotFoundError otherwise."""
    job = load_job(store_root, customer_project_id, job_id)          # exists + isolation first
    record = next((u for u in job.get("uploads", [])
                   if u.get("upload_id") == upload_id and u.get("kind") == require_kind), None)
    if record is None:
        raise UploadFileNotFoundError(
            "no %s upload %r on job %r" % (require_kind, upload_id, job_id))
    content_type = PHOTO_CONTENT_TYPES.get(_ext(record.get("stored_path", "")))
    if content_type is None:
        raise UploadFileNotFoundError("upload %r has no servable image extension" % (upload_id,))
    root = job_dir(store_root, customer_project_id, job_id).resolve()
    path = (root / str(record.get("stored_path", ""))).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise UploadFileNotFoundError("upload %r payload is not available" % (upload_id,))
    return {"path": path, "content_type": content_type}


# Extensions a BORE_LOG upload can serve a SOURCE PAGE image for (Phase-1 handwritten-extraction review UI:
# show the original page beside the parsed row). .csv/.xlsx BORE_LOG uploads have no "page image" concept
# and are deliberately excluded (not servable).
BORE_LOG_SOURCE_EXTENSIONS = (".pdf",) + IMAGE_BORELOG_EXTENSIONS


def resolve_borelog_source_file(store_root, customer_project_id, job_id, upload_id) -> dict:
    """Resolve one stored BORE_LOG upload payload for READ-ONLY source-page byte-serving (mirrors
    ``resolve_upload_file``'s PHOTO pattern exactly: tenant-safe via ``load_job``, path-safe via the same
    containment assertion ``delete_job`` uses). Only an upload RECORDED as kind BORE_LOG with a servable
    extension (a PDF -- rasterized page-by-page by the caller -- or a plain image, servable at page 0) is
    servable. Pure read: no record, lifecycle, slot, or status change. Returns ``{"path": Path, "ext": str}``;
    raises UploadFileNotFoundError otherwise (uniform not-found -- never confirms cross-tenant/wrong-kind
    existence)."""
    job = load_job(store_root, customer_project_id, job_id)          # exists + isolation first
    record = next((u for u in job.get("uploads", [])
                   if u.get("upload_id") == upload_id and u.get("kind") == "BORE_LOG"), None)
    if record is None:
        raise UploadFileNotFoundError("no BORE_LOG upload %r on job %r" % (upload_id, job_id))
    ext = _ext(record.get("stored_path", ""))
    if ext not in BORE_LOG_SOURCE_EXTENSIONS:
        raise UploadFileNotFoundError("upload %r has no servable source-page format" % (upload_id,))
    root = job_dir(store_root, customer_project_id, job_id).resolve()
    path = (root / str(record.get("stored_path", ""))).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise UploadFileNotFoundError("upload %r payload is not available" % (upload_id,))
    return {"path": path, "ext": ext}
