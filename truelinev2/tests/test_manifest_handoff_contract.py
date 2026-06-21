"""Contract tests: the manifest_handoff engine-output attachment. Pure stdlib + tmp_path; no engine
execution / render / wiring. Generic ids/values only — no customer/person/project/location strings.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from truelinev2.contracts.customer_project import create_customer_project
from truelinev2.contracts.processing_job import create_job, load_job
from truelinev2.contracts.upload_pipeline import accept_upload
from truelinev2.contracts.extracted_row import CONFIRMED, OCR, new_extracted_row
from truelinev2.contracts.reviewed_bore_log import (
    GROUPING_CONFIRMED,
    SEPARATE_BORE,
    ReviewedBoreLogNotFoundError,
    add_extracted_rows,
    create_reviewed_bore_log,
    define_segment_group,
    review_row_in_log,
    set_grouping_status,
)
from truelinev2.contracts.manifest_handoff import (
    ATTEMPTED,
    FAILED,
    REJECTED,
    SUCCEEDED,
    HandoffNotFoundError,
    HandoffStateError,
    InvalidEngineRunIdError,
    ManifestHandoffError,
    finalize_handoff,
    load_handoff,
    record_handoff_attempt,
    validate_engine_run_id,
)

AT = "2026-06-21T00:00:00Z"
BY = "operator-1"
CP = "cp-0001"
JOB = "job-0001"
RBL = "rbl-0001"
RUN = "run-0001"


# --------------------------------------------------------------------------- #
# Generic valid engine-output bundle fixture (mirrors the published-bundle shape; generic names only).
# --------------------------------------------------------------------------- #
def _log(lid, status, prov, drawn=False, covered=False, blocked=False, artifacts=None):
    return {"log_id": lid, "parent_id": "b_" + lid, "entry_role": "standalone",
            "status": status, "provenance": prov, "drawn": drawn, "covered": covered,
            "blocked": blocked, "drawn_lane": "NEW_TARGETS" if drawn else None,
            "source_sheets": [1],
            "span": {"start_station": "0+00", "end_station": "1+00", "label": "0+00->1+00"},
            "closure": None, "coverage": {"covered_by": "logX"} if covered else None,
            "blocker": {"category": "OWNER_LOCKED", "name": "n", "unlock_requirement": "owner lifts"}
            if blocked else None,
            "artifacts": artifacts or [],
            "evidence": [{"kind": "ACCOUNTABILITY_LEDGER", "ref": "r"}], "warnings": []}


def _build_engine_output_bundle(root, *, mock_example=False, content_tag=b"A"):
    root = Path(root)
    art_dir = root / "artifacts" / "logA"
    art_dir.mkdir(parents=True)
    data = b"FAKE-PNG-" + content_tag
    (art_dir / "logA_s1_redline_stroke.png").write_bytes(data)
    sha = hashlib.sha256(data).hexdigest()
    art = {"kind": "FINAL_REDLINE_PNG", "path": "artifacts/logA/logA_s1_redline_stroke.png",
           "sha256": sha, "bytes": len(data), "published": True, "example_placeholder": False}
    manifest = {
        "schema_version": "1.0.0", "mock_example": mock_example, "disclaimer": "t",
        "project_id": "proj-a", "project_name": "Project A",
        "engine": {"branch": "feat/truelinev2", "engine_head": "h", "render_commit": "rc-0",
                   "generated_from": "test"},
        "summary": {"total_logs": 3, "drawn_count": 1, "covered_count": 1, "blocked_count": 1,
                    "frontier": "1/3"},
        "status_counts": {"DRAWN_REDLINE": 1, "COVERED_BY_EXISTING_REDLINE": 1,
                          "OWNER_LOCKED_ABSTAIN": 1, "SOURCE_GAP_BLOCKED": 0,
                          "MISSING_SOURCE_SHEET_BLOCKED": 0},
        "provenance_counts": {"DETERMINISTIC_AUTO": 1, "OWNER_CONFIRMED_HUMAN_ADJUSTABLE": 0,
                              "COVERED_BY_EXISTING_REDLINE": 1, "BLOCKED_OWNER_LOCKED": 1,
                              "BLOCKED_SOURCE_GAP": 0, "BLOCKED_MISSING_SOURCE": 0},
        "consumption_rules": ["consume the manifest"],
        "logs": [_log("logA", "DRAWN_REDLINE", "DETERMINISTIC_AUTO", drawn=True, artifacts=[art]),
                 _log("logC", "COVERED_BY_EXISTING_REDLINE", "COVERED_BY_EXISTING_REDLINE", covered=True),
                 _log("logB", "OWNER_LOCKED_ABSTAIN", "BLOCKED_OWNER_LOCKED", blocked=True)],
    }
    (root / "redline_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return root


def _job_with_unready_rbl(tmp_path):
    create_customer_project(tmp_path, CP, "Label", AT)
    create_job(tmp_path, CP, JOB, AT, BY)
    up = accept_upload(tmp_path, CP, JOB, kind="BORE_LOG", filename="log.csv", content=b"a,b", stored_at=AT)
    create_reviewed_bore_log(tmp_path, CP, JOB, up["upload_id"], RBL, at=AT, by=BY)
    add_extracted_rows(tmp_path, CP, JOB, RBL, [new_extracted_row(
        "row-1", up["upload_id"], raw={}, normalized={}, extraction_method=OCR, at=AT, by=BY)],
        at=AT, by=BY)  # left UNREVIEWED + ungrouped -> not engine-ready
    return up["upload_id"]


def _job_with_ready_rbl(tmp_path):
    up = _job_with_unready_rbl(tmp_path)
    review_row_in_log(tmp_path, CP, JOB, RBL, "row-1", CONFIRMED, at=AT, by=BY)
    define_segment_group(tmp_path, CP, JOB, RBL, "grp-1", ["row-1"], SEPARATE_BORE, at=AT, by=BY)
    set_grouping_status(tmp_path, CP, JOB, RBL, "grp-1", GROUPING_CONFIRMED, at=AT, by=BY)
    return up


def _attempt(tmp_path):
    return record_handoff_attempt(tmp_path, CP, JOB, RBL, RUN, engine_run_status="completed", at=AT, by=BY)


# --------------------------------------------------------------------------- #
def test_record_attempt_is_attempted_no_slots(tmp_path):
    _job_with_ready_rbl(tmp_path)
    h = _attempt(tmp_path)
    assert h["status"] == ATTEMPTED and h["engine_run_status"] == "completed"
    assert h["manifest_attachment"] is None and h["artifact_bundle_attachment"] is None
    job = load_job(tmp_path, CP, JOB)
    assert job["slots"]["redline_manifest"] is None and job["slots"]["artifact_bundle"] is None


def test_record_requires_existing_rbl(tmp_path):
    create_customer_project(tmp_path, CP, "Label", AT)
    create_job(tmp_path, CP, JOB, AT, BY)
    with pytest.raises(ReviewedBoreLogNotFoundError):
        record_handoff_attempt(tmp_path, CP, JOB, "rbl-missing", RUN,
                               engine_run_status="completed", at=AT, by=BY)


def test_duplicate_engine_run_id_rejected(tmp_path):
    _job_with_ready_rbl(tmp_path)
    _attempt(tmp_path)
    with pytest.raises(ManifestHandoffError):
        _attempt(tmp_path)


def test_finalize_success_attaches_validated_outputs(tmp_path):
    _job_with_ready_rbl(tmp_path)
    _attempt(tmp_path)
    bundle = _build_engine_output_bundle(tmp_path / "engine_out")
    h = finalize_handoff(tmp_path, CP, JOB, RUN, bundle, at=AT, by=BY)
    assert h["status"] == SUCCEEDED
    assert h["manifest_attachment"]["validation_status"] == "VALIDATED"
    assert h["artifact_bundle_attachment"]["validation_status"] == "VALIDATED"
    bid = h["artifact_bundle_attachment"]["bundle_id"]
    assert bid.startswith("proj-a-rc-0-")
    # job slots now point to the validated, durably stored, content-addressed bundle
    job = load_job(tmp_path, CP, JOB)
    assert job["slots"]["redline_manifest"]["ref"]["bundle_id"] == bid
    assert job["slots"]["artifact_bundle"]["ref"]["bundle_id"] == bid
    assert job["slots"]["export_package"] is None                       # untouched
    # bundle durably retained under the job-scoped bundle_store (non-dangling reference)
    stored = (Path(tmp_path) / "customer_projects" / CP / "processing_jobs" / JOB
              / "bundle_store" / "bundles" / bid / "redline_manifest.json")
    assert stored.is_file()


def test_finalize_rejected_when_not_engine_ready(tmp_path):
    _job_with_unready_rbl(tmp_path)                                     # rbl NOT ready
    _attempt(tmp_path)
    bundle = _build_engine_output_bundle(tmp_path / "engine_out")
    h = finalize_handoff(tmp_path, CP, JOB, RUN, bundle, at=AT, by=BY)
    assert h["status"] == REJECTED and h["errors"]
    job = load_job(tmp_path, CP, JOB)
    assert job["slots"]["redline_manifest"] is None and job["slots"]["artifact_bundle"] is None


def test_finalize_failed_on_mock_bundle(tmp_path):
    _job_with_ready_rbl(tmp_path)
    _attempt(tmp_path)
    bundle = _build_engine_output_bundle(tmp_path / "engine_out", mock_example=True)   # fake -> rejected
    h = finalize_handoff(tmp_path, CP, JOB, RUN, bundle, at=AT, by=BY)
    assert h["status"] == FAILED and h["errors"]
    job = load_job(tmp_path, CP, JOB)
    assert job["slots"]["redline_manifest"] is None and job["slots"]["artifact_bundle"] is None


def test_finalize_failed_on_checksum_tamper(tmp_path):
    _job_with_ready_rbl(tmp_path)
    _attempt(tmp_path)
    bundle = _build_engine_output_bundle(tmp_path / "engine_out")
    (bundle / "artifacts" / "logA" / "logA_s1_redline_stroke.png").write_bytes(b"TAMPERED")
    h = finalize_handoff(tmp_path, CP, JOB, RUN, bundle, at=AT, by=BY)
    assert h["status"] == FAILED
    assert load_job(tmp_path, CP, JOB)["slots"]["artifact_bundle"] is None


def test_terminal_succeeded_is_immutable(tmp_path):
    _job_with_ready_rbl(tmp_path)
    _attempt(tmp_path)
    bundle = _build_engine_output_bundle(tmp_path / "engine_out")
    finalize_handoff(tmp_path, CP, JOB, RUN, bundle, at=AT, by=BY)      # SUCCEEDED
    with pytest.raises(HandoffStateError):
        finalize_handoff(tmp_path, CP, JOB, RUN, bundle, at=AT, by=BY)


def test_terminal_rejected_is_immutable(tmp_path):
    _job_with_unready_rbl(tmp_path)
    _attempt(tmp_path)
    bundle = _build_engine_output_bundle(tmp_path / "engine_out")
    assert finalize_handoff(tmp_path, CP, JOB, RUN, bundle, at=AT, by=BY)["status"] == REJECTED
    with pytest.raises(HandoffStateError):
        finalize_handoff(tmp_path, CP, JOB, RUN, bundle, at=AT, by=BY)


def test_cross_project_isolation(tmp_path):
    _job_with_ready_rbl(tmp_path)
    _attempt(tmp_path)
    create_customer_project(tmp_path, "cp-other", "Other", AT)
    create_job(tmp_path, "cp-other", JOB, AT, BY)
    with pytest.raises(HandoffNotFoundError):
        load_handoff(tmp_path, "cp-other", JOB, RUN)


def test_invalid_engine_run_id():
    with pytest.raises(InvalidEngineRunIdError):
        validate_engine_run_id("Bad/Run")


def test_durable_reload(tmp_path):
    _job_with_ready_rbl(tmp_path)
    _attempt(tmp_path)
    assert load_handoff(tmp_path, CP, JOB, RUN)["status"] == ATTEMPTED
