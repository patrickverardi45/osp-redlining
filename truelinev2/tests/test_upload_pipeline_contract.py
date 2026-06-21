"""Contract tests: the upload_pipeline intake + accepted-file inventory. Asserts NO extraction runs
(extraction_status stays "queued"). Pure stdlib + tmp_path; no engine/render/wiring. Generic ids only.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from truelinev2.contracts.customer_project import CUSTOMER_PROJECTS_SUBDIR, create_customer_project
from truelinev2.contracts.processing_job import (
    EXTRACTING,
    PROCESSING_JOBS_SUBDIR,
    UPLOADING,
    create_job,
    load_job,
    transition,
)
from truelinev2.contracts.upload_pipeline import (
    ACCEPTED_KINDS,
    EXTRACTION_STATUS_QUEUED,
    EmptyUploadError,
    FileTooLargeError,
    RejectedExtensionError,
    UnknownKindError,
    UploadsClosedError,
    accept_upload,
    validate_upload,
)

AT = "2026-06-20T00:00:00Z"
BY = "operator-1"


def _job(tmp_path):
    create_customer_project(tmp_path, "cp-0001", "Label", AT)
    create_job(tmp_path, "cp-0001", "job-0001", AT, BY)


def _stored(tmp_path, rel):
    return (Path(tmp_path) / CUSTOMER_PROJECTS_SUBDIR / "cp-0001"
            / PROCESSING_JOBS_SUBDIR / "job-0001" / rel)


def test_accepts_each_kind_and_records_metadata(tmp_path):
    _job(tmp_path)
    for kind, fname in [("PLAN_PDF", "plan.pdf"), ("BORE_LOG", "log.csv"), ("GIS_ROUTE", "route.kmz")]:
        content = b"bytes-for-" + fname.encode()
        rec = accept_upload(tmp_path, "cp-0001", "job-0001", kind=kind, filename=fname,
                            content=content, stored_at=AT)
        assert rec["kind"] == kind
        assert rec["sha256"] == hashlib.sha256(content).hexdigest()
        assert rec["bytes"] == len(content)
        assert rec["extraction_status"] == EXTRACTION_STATUS_QUEUED  # NO extraction performed
        stored = _stored(tmp_path, rec["stored_path"])
        assert stored.is_file() and stored.read_bytes() == content
    assert len(load_job(tmp_path, "cp-0001", "job-0001")["uploads"]) == 3


def test_rejects_unknown_kind(tmp_path):
    _job(tmp_path)
    with pytest.raises(UnknownKindError):
        accept_upload(tmp_path, "cp-0001", "job-0001", kind="VIDEO", filename="x.mp4",
                      content=b"x", stored_at=AT)


def test_rejects_bad_extension(tmp_path):
    _job(tmp_path)
    with pytest.raises(RejectedExtensionError):
        accept_upload(tmp_path, "cp-0001", "job-0001", kind="PLAN_PDF", filename="plan.kmz",
                      content=b"x", stored_at=AT)


def test_rejects_oversize_and_empty(tmp_path):
    _job(tmp_path)
    with pytest.raises(FileTooLargeError):
        accept_upload(tmp_path, "cp-0001", "job-0001", kind="PLAN_PDF", filename="p.pdf",
                      content=b"abcdef", stored_at=AT, max_bytes=3)
    with pytest.raises(EmptyUploadError):
        accept_upload(tmp_path, "cp-0001", "job-0001", kind="PLAN_PDF", filename="p.pdf",
                      content=b"", stored_at=AT)


def test_idempotent_by_content(tmp_path):
    _job(tmp_path)
    a = accept_upload(tmp_path, "cp-0001", "job-0001", kind="PLAN_PDF", filename="p.pdf",
                      content=b"same", stored_at=AT)
    b = accept_upload(tmp_path, "cp-0001", "job-0001", kind="PLAN_PDF", filename="p.pdf",
                      content=b"same", stored_at="2099-01-01T00:00:00Z")
    assert a["upload_id"] == b["upload_id"]
    uploads = load_job(tmp_path, "cp-0001", "job-0001")["uploads"]
    assert len(uploads) == 1                 # no duplicate
    assert uploads[0]["stored_at"] == AT     # original record retained


def test_uploads_closed_after_extracting(tmp_path):
    _job(tmp_path)
    transition(tmp_path, "cp-0001", "job-0001", UPLOADING, at=AT, by=BY)
    transition(tmp_path, "cp-0001", "job-0001", EXTRACTING, at=AT, by=BY)
    with pytest.raises(UploadsClosedError):
        accept_upload(tmp_path, "cp-0001", "job-0001", kind="PLAN_PDF", filename="p.pdf",
                      content=b"late", stored_at=AT)


def test_accepted_kind_inventory_and_validate(tmp_path):
    assert set(ACCEPTED_KINDS) == {"PLAN_PDF", "BORE_LOG", "GIS_ROUTE"}
    validate_upload("BORE_LOG", "x.xlsx", 10)  # valid -> no raise
