"""Contract tests: the processing_job lifecycle (state machine, audit, durability, output slots,
cross-project isolation). Pure stdlib + tmp_path; no engine/render/wiring. Generic ids only.
"""
from __future__ import annotations

import pytest

from truelinev2.contracts.customer_project import create_customer_project
from truelinev2.contracts.processing_job import (
    ALLOWED_TRANSITIONS,
    AWAITING_REVIEW,
    CLOSED,
    CLOSEOUT_REVIEW,
    CREATED,
    EXTRACTING,
    FAILED,
    JOB_STATES,
    OUTPUT_SLOT_NAMES,
    PLACED,
    PLACING,
    UPLOADING,
    IllegalTransitionError,
    InvalidJobIdError,
    JobNotFoundError,
    ProcessingJobError,
    UnknownSlotError,
    create_job,
    load_job,
    set_output_slot,
    transition,
    validate_job_id,
)

AT = "2026-06-20T00:00:00Z"
BY = "operator-1"
HAPPY_PATH = [UPLOADING, EXTRACTING, AWAITING_REVIEW, PLACING, PLACED, CLOSEOUT_REVIEW, CLOSED]


def _mk(tmp_path, cp="cp-0001", job="job-0001"):
    create_customer_project(tmp_path, cp, "Label", AT)
    return create_job(tmp_path, cp, job, AT, BY)


def test_create_job_initial_state(tmp_path):
    job = _mk(tmp_path)
    assert job["status"] == CREATED
    assert job["uploads"] == []
    assert job["slots"] == {n: None for n in OUTPUT_SLOT_NAMES}
    assert job["audit"][0]["from"] is None and job["audit"][0]["to"] == CREATED


def test_duplicate_job_rejected(tmp_path):
    _mk(tmp_path)
    with pytest.raises(ProcessingJobError):
        create_job(tmp_path, "cp-0001", "job-0001", AT, BY)


def test_happy_path_transitions_and_audit(tmp_path):
    _mk(tmp_path)
    job = None
    for nxt in HAPPY_PATH:
        job = transition(tmp_path, "cp-0001", "job-0001", nxt, at=AT, by=BY, reason="step")
    assert job["status"] == CLOSED
    assert len(job["audit"]) == 1 + len(HAPPY_PATH)  # opening entry + one per transition
    last = job["audit"][-1]
    assert last["from"] == CLOSEOUT_REVIEW and last["to"] == CLOSED
    assert last["at"] == AT and last["by"] == BY and last["reason"] == "step"


def test_illegal_transition_rejected(tmp_path):
    _mk(tmp_path)
    with pytest.raises(IllegalTransitionError):  # CREATED -> PLACED skips the machine
        transition(tmp_path, "cp-0001", "job-0001", PLACED, at=AT, by=BY)
    with pytest.raises(IllegalTransitionError):  # unknown target status
        transition(tmp_path, "cp-0001", "job-0001", "NOPE", at=AT, by=BY)


def test_fail_requires_reason_and_is_terminal(tmp_path):
    _mk(tmp_path)
    transition(tmp_path, "cp-0001", "job-0001", UPLOADING, at=AT, by=BY)
    with pytest.raises(ProcessingJobError):  # FAILED needs a reason
        transition(tmp_path, "cp-0001", "job-0001", FAILED, at=AT, by=BY)
    job = transition(tmp_path, "cp-0001", "job-0001", FAILED, at=AT, by=BY, reason="bad input")
    assert job["status"] == FAILED
    with pytest.raises(IllegalTransitionError):  # terminal — no way out
        transition(tmp_path, "cp-0001", "job-0001", UPLOADING, at=AT, by=BY)


def test_status_is_durable_across_reload(tmp_path):
    _mk(tmp_path)
    transition(tmp_path, "cp-0001", "job-0001", UPLOADING, at=AT, by=BY)
    # fresh load (simulates a restart: nothing in memory)
    assert load_job(tmp_path, "cp-0001", "job-0001")["status"] == UPLOADING


def test_output_slots_interface_only(tmp_path):
    _mk(tmp_path)
    job = set_output_slot(tmp_path, "cp-0001", "job-0001", "redline_manifest",
                          {"bundle_id": "ref-x"}, at=AT, by=BY)
    assert job["slots"]["redline_manifest"]["ref"] == {"bundle_id": "ref-x"}
    assert job["slots"]["artifact_bundle"] is None and job["slots"]["export_package"] is None
    with pytest.raises(UnknownSlotError):
        set_output_slot(tmp_path, "cp-0001", "job-0001", "not_a_slot", {}, at=AT, by=BY)


def test_invalid_job_id_rejected():
    with pytest.raises(InvalidJobIdError):
        validate_job_id("Bad/Id")


def test_job_scoped_to_its_project(tmp_path):
    create_customer_project(tmp_path, "cp-a", "Label A", AT)
    create_customer_project(tmp_path, "cp-b", "Label B", AT)
    create_job(tmp_path, "cp-a", "job-0001", AT, BY)
    with pytest.raises(JobNotFoundError):  # same job id under another project does not exist
        load_job(tmp_path, "cp-b", "job-0001")


def test_allowed_transitions_cover_all_states():
    assert set(ALLOWED_TRANSITIONS) == set(JOB_STATES)
    assert ALLOWED_TRANSITIONS[CLOSED] == () and ALLOWED_TRANSITIONS[FAILED] == ()
