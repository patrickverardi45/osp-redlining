"""Contract tests: the reviewed_bore_log engine-eligibility gate (grouping + review + DERIVED gate).
Pure stdlib + tmp_path; no engine/render/wiring. Generic ids/values only.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from truelinev2.contracts.customer_project import create_customer_project
from truelinev2.contracts.processing_job import create_job
from truelinev2.contracts.upload_pipeline import accept_upload
from truelinev2.contracts.extracted_row import (
    CONFIRMED,
    CORRECTED,
    OCR,
    REJECTED,
    RE_REVIEW_WOULD_DISCARD_CORRECTIONS,
    ReReviewWouldDiscardCorrectionsError,
    new_extracted_row,
)
from truelinev2.contracts.reviewed_bore_log import (
    AMBIGUOUS,
    GROUPING_CONFIRMED,
    SAME_RUN_SEGMENTS,
    SEPARATE_BORE,
    SOURCE_CONFLICT,
    ReviewedBoreLogError,
    ReviewedBoreLogNotFoundError,
    RowNotFoundError,
    SourceUploadError,
    add_extracted_rows,
    create_reviewed_bore_log,
    define_segment_group,
    engine_eligible_row_ids,
    is_engine_ready,
    load_reviewed_bore_log,
    review_queue,
    review_row_in_log,
    row_engine_eligible,
    set_grouping_status,
)

AT = "2026-06-21T00:00:00Z"
BY = "operator-1"
CP = "cp-0001"
JOB = "job-0001"
RBL = "rbl-0001"


def _job_with_bore_log(tmp_path):
    create_customer_project(tmp_path, CP, "Label", AT)
    create_job(tmp_path, CP, JOB, AT, BY)
    rec = accept_upload(tmp_path, CP, JOB, kind="BORE_LOG", filename="log.csv",
                        content=b"a,b,c", stored_at=AT)
    return rec["upload_id"]


def _mk_rbl(tmp_path):
    up = _job_with_bore_log(tmp_path)
    create_reviewed_bore_log(tmp_path, CP, JOB, up, RBL, at=AT, by=BY)
    return up


def _row(row_id, up):
    return new_extracted_row(row_id, up, raw={"station": "0+00"}, normalized={"station": "0+00"},
                             extraction_method=OCR, confidence="LOW", at=AT, by=BY)


def _confirm_grouped(tmp_path, row_ids, relation=SEPARATE_BORE, group_id="grp-1"):
    for rid in row_ids:
        review_row_in_log(tmp_path, CP, JOB, RBL, rid, CONFIRMED, at=AT, by=BY)
    define_segment_group(tmp_path, CP, JOB, RBL, group_id, list(row_ids), relation, at=AT, by=BY)
    set_grouping_status(tmp_path, CP, JOB, RBL, group_id, GROUPING_CONFIRMED, at=AT, by=BY)


def test_create_requires_existing_bore_log_upload(tmp_path):
    create_customer_project(tmp_path, CP, "Label", AT)
    create_job(tmp_path, CP, JOB, AT, BY)
    with pytest.raises(SourceUploadError):                      # no such upload
        create_reviewed_bore_log(tmp_path, CP, JOB, "up-missing", RBL, at=AT, by=BY)
    pdf = accept_upload(tmp_path, CP, JOB, kind="PLAN_PDF", filename="p.pdf", content=b"x", stored_at=AT)
    with pytest.raises(SourceUploadError):                      # wrong-kind upload
        create_reviewed_bore_log(tmp_path, CP, JOB, pdf["upload_id"], RBL, at=AT, by=BY)


def test_empty_record_is_not_engine_ready(tmp_path):
    _mk_rbl(tmp_path)
    rbl = load_reviewed_bore_log(tmp_path, CP, JOB, RBL)
    assert rbl["rows"] == [] and is_engine_ready(rbl) is False  # correction 4


def test_unreviewed_or_ungrouped_not_eligible(tmp_path):
    up = _mk_rbl(tmp_path)
    add_extracted_rows(tmp_path, CP, JOB, RBL, [_row("row-1", up)], at=AT, by=BY)
    rbl = load_reviewed_bore_log(tmp_path, CP, JOB, RBL)
    assert engine_eligible_row_ids(rbl) == [] and is_engine_ready(rbl) is False   # unreviewed
    review_row_in_log(tmp_path, CP, JOB, RBL, "row-1", CONFIRMED, at=AT, by=BY)
    rbl = load_reviewed_bore_log(tmp_path, CP, JOB, RBL)
    assert engine_eligible_row_ids(rbl) == [] and is_engine_ready(rbl) is False   # confirmed but ungrouped


def test_confirmed_in_confirmed_group_is_eligible_and_ready(tmp_path):
    up = _mk_rbl(tmp_path)
    add_extracted_rows(tmp_path, CP, JOB, RBL, [_row("row-1", up)], at=AT, by=BY)
    review_row_in_log(tmp_path, CP, JOB, RBL, "row-1", CONFIRMED, at=AT, by=BY)
    define_segment_group(tmp_path, CP, JOB, RBL, "grp-1", ["row-1"], SEPARATE_BORE, at=AT, by=BY)
    rbl = load_reviewed_bore_log(tmp_path, CP, JOB, RBL)
    assert is_engine_ready(rbl) is False                       # group still PENDING
    set_grouping_status(tmp_path, CP, JOB, RBL, "grp-1", GROUPING_CONFIRMED, at=AT, by=BY)
    rbl = load_reviewed_bore_log(tmp_path, CP, JOB, RBL)
    assert engine_eligible_row_ids(rbl) == ["row-1"]
    assert row_engine_eligible(rbl, "row-1") is True and is_engine_ready(rbl) is True


# --------------------------------------------------------------------------- #
# Doctrine guard, PERSISTED: a re-review to CONFIRMED that would wipe existing corrected_values is refused
# 409 (RE_REVIEW_WOULD_DISCARD_CORRECTIONS), leaves the row's banked review state untouched on disk, but
# the REFUSAL ATTEMPT ITSELF is recorded in the reviewed_bore_log's audit trail and persisted.
# --------------------------------------------------------------------------- #
def test_review_row_in_log_refuses_wipe_and_persists_refusal_audit(tmp_path):
    up = _mk_rbl(tmp_path)
    add_extracted_rows(tmp_path, CP, JOB, RBL, [_row("row-1", up)], at=AT, by=BY)
    review_row_in_log(tmp_path, CP, JOB, RBL, "row-1", CORRECTED, at=AT, by=BY,
                      corrected_values={"station": "0+10"})

    with pytest.raises(ReReviewWouldDiscardCorrectionsError):
        review_row_in_log(tmp_path, CP, JOB, RBL, "row-1", CONFIRMED, at=AT, by=BY)

    # Corrections survive on disk (a fresh load, not an in-memory artifact).
    rbl = load_reviewed_bore_log(tmp_path, CP, JOB, RBL)
    row = next(r for r in rbl["rows"] if r["row_id"] == "row-1")
    assert row["review"]["status"] == CORRECTED
    assert row["review"]["corrected_values"] == {"station": "0+10"}
    # The refusal ATTEMPT is recorded (and persisted) in the reviewed_bore_log's own audit trail.
    refusals = [a for a in rbl["audit"] if a.get("action") == "row_review_refused"]
    assert len(refusals) == 1
    assert refusals[0]["row_id"] == "row-1" and refusals[0]["attempted_to"] == CONFIRMED
    assert refusals[0]["code"] == RE_REVIEW_WOULD_DISCARD_CORRECTIONS


def test_review_row_in_log_idempotent_cases_still_succeed(tmp_path):
    up = _mk_rbl(tmp_path)
    add_extracted_rows(tmp_path, CP, JOB, RBL, [_row("row-1", up), _row("row-2", up)], at=AT, by=BY)

    # CONFIRMED -> CONFIRMED (no corrections ever) stays OK.
    review_row_in_log(tmp_path, CP, JOB, RBL, "row-1", CONFIRMED, at=AT, by=BY)
    review_row_in_log(tmp_path, CP, JOB, RBL, "row-1", CONFIRMED, at=AT, by=BY)
    rbl = load_reviewed_bore_log(tmp_path, CP, JOB, RBL)
    row1 = next(r for r in rbl["rows"] if r["row_id"] == "row-1")
    assert row1["review"]["status"] == CONFIRMED

    # CORRECTED -> CORRECTED with the SAME values resent stays OK.
    review_row_in_log(tmp_path, CP, JOB, RBL, "row-2", CORRECTED, at=AT, by=BY,
                      corrected_values={"station": "0+20"})
    review_row_in_log(tmp_path, CP, JOB, RBL, "row-2", CORRECTED, at=AT, by=BY,
                      corrected_values={"station": "0+20"})
    rbl = load_reviewed_bore_log(tmp_path, CP, JOB, RBL)
    row2 = next(r for r in rbl["rows"] if r["row_id"] == "row-2")
    assert row2["review"]["status"] == CORRECTED
    assert row2["review"]["corrected_values"] == {"station": "0+20"}


def test_same_run_segments_eligible(tmp_path):
    up = _mk_rbl(tmp_path)
    add_extracted_rows(tmp_path, CP, JOB, RBL, [_row("row-1", up), _row("row-2", up)], at=AT, by=BY)
    _confirm_grouped(tmp_path, ["row-1", "row-2"], relation=SAME_RUN_SEGMENTS)
    rbl = load_reviewed_bore_log(tmp_path, CP, JOB, RBL)
    assert set(engine_eligible_row_ids(rbl)) == {"row-1", "row-2"} and is_engine_ready(rbl) is True


def test_ambiguous_or_conflict_group_blocks(tmp_path):
    up = _mk_rbl(tmp_path)
    add_extracted_rows(tmp_path, CP, JOB, RBL, [_row("row-1", up)], at=AT, by=BY)
    review_row_in_log(tmp_path, CP, JOB, RBL, "row-1", CONFIRMED, at=AT, by=BY)
    define_segment_group(tmp_path, CP, JOB, RBL, "grp-1", ["row-1"], AMBIGUOUS, at=AT, by=BY)
    set_grouping_status(tmp_path, CP, JOB, RBL, "grp-1", GROUPING_CONFIRMED, at=AT, by=BY)
    rbl = load_reviewed_bore_log(tmp_path, CP, JOB, RBL)
    assert engine_eligible_row_ids(rbl) == []                  # AMBIGUOUS never eligible
    set_grouping_status(tmp_path, CP, JOB, RBL, "grp-1", SOURCE_CONFLICT, at=AT, by=BY, reason="contradiction")
    rbl = load_reviewed_bore_log(tmp_path, CP, JOB, RBL)
    assert engine_eligible_row_ids(rbl) == [] and is_engine_ready(rbl) is False


def test_source_conflict_requires_reason(tmp_path):
    up = _mk_rbl(tmp_path)
    add_extracted_rows(tmp_path, CP, JOB, RBL, [_row("row-1", up)], at=AT, by=BY)
    define_segment_group(tmp_path, CP, JOB, RBL, "grp-1", ["row-1"], SEPARATE_BORE, at=AT, by=BY)
    with pytest.raises(ReviewedBoreLogError):
        set_grouping_status(tmp_path, CP, JOB, RBL, "grp-1", SOURCE_CONFLICT, at=AT, by=BY)


def test_row_in_multiple_groups_is_drift_not_eligible(tmp_path):
    up = _mk_rbl(tmp_path)
    add_extracted_rows(tmp_path, CP, JOB, RBL, [_row("row-1", up)], at=AT, by=BY)
    review_row_in_log(tmp_path, CP, JOB, RBL, "row-1", CONFIRMED, at=AT, by=BY)
    # same row in two confirmed groups -> ambiguous membership -> blocked (correction 5)
    define_segment_group(tmp_path, CP, JOB, RBL, "grp-1", ["row-1"], SEPARATE_BORE, at=AT, by=BY)
    define_segment_group(tmp_path, CP, JOB, RBL, "grp-2", ["row-1"], SEPARATE_BORE, at=AT, by=BY)
    set_grouping_status(tmp_path, CP, JOB, RBL, "grp-1", GROUPING_CONFIRMED, at=AT, by=BY)
    set_grouping_status(tmp_path, CP, JOB, RBL, "grp-2", GROUPING_CONFIRMED, at=AT, by=BY)
    rbl = load_reviewed_bore_log(tmp_path, CP, JOB, RBL)
    assert row_engine_eligible(rbl, "row-1") is False
    assert "row-1" in review_queue(rbl)["rows_in_multiple_groups"]


def test_rejected_row_never_eligible_but_does_not_block_others(tmp_path):
    up = _mk_rbl(tmp_path)
    add_extracted_rows(tmp_path, CP, JOB, RBL, [_row("row-1", up), _row("row-2", up)], at=AT, by=BY)
    review_row_in_log(tmp_path, CP, JOB, RBL, "row-1", CONFIRMED, at=AT, by=BY)
    review_row_in_log(tmp_path, CP, JOB, RBL, "row-2", REJECTED, at=AT, by=BY, reason="not a bore")
    define_segment_group(tmp_path, CP, JOB, RBL, "grp-1", ["row-1"], SEPARATE_BORE, at=AT, by=BY)
    set_grouping_status(tmp_path, CP, JOB, RBL, "grp-1", GROUPING_CONFIRMED, at=AT, by=BY)
    rbl = load_reviewed_bore_log(tmp_path, CP, JOB, RBL)
    assert engine_eligible_row_ids(rbl) == ["row-1"]           # row-2 rejected, excluded
    assert is_engine_ready(rbl) is True                        # rejected row doesn't block readiness


def test_eligibility_is_derived_not_stored(tmp_path):
    up = _mk_rbl(tmp_path)
    add_extracted_rows(tmp_path, CP, JOB, RBL, [_row("row-1", up)], at=AT, by=BY)
    _confirm_grouped(tmp_path, ["row-1"])
    # correction 6: no engine_eligible / engine_ready flag is ever persisted
    raw = (Path(tmp_path) / "customer_projects" / CP / "processing_jobs" / JOB
           / "reviewed_bore_logs" / RBL / "_reviewed_bore_log.json").read_text(encoding="utf-8")
    assert "engine_eligible" not in raw and "engine_ready" not in raw


def test_durable_reload_and_isolation(tmp_path):
    up = _mk_rbl(tmp_path)
    add_extracted_rows(tmp_path, CP, JOB, RBL, [_row("row-1", up)], at=AT, by=BY)
    assert len(load_reviewed_bore_log(tmp_path, CP, JOB, RBL)["rows"]) == 1   # survives reload
    create_customer_project(tmp_path, "cp-other", "Other", AT)
    create_job(tmp_path, "cp-other", JOB, AT, BY)
    with pytest.raises(ReviewedBoreLogNotFoundError):          # isolation by construction
        load_reviewed_bore_log(tmp_path, "cp-other", JOB, RBL)


def test_duplicate_row_and_unknown_member_rejected(tmp_path):
    up = _mk_rbl(tmp_path)
    add_extracted_rows(tmp_path, CP, JOB, RBL, [_row("row-1", up)], at=AT, by=BY)
    with pytest.raises(ReviewedBoreLogError):
        add_extracted_rows(tmp_path, CP, JOB, RBL, [_row("row-1", up)], at=AT, by=BY)  # dup row_id
    with pytest.raises(RowNotFoundError):
        define_segment_group(tmp_path, CP, JOB, RBL, "grp-1", ["ghost"], SEPARATE_BORE, at=AT, by=BY)


def test_review_queue_surfaces_state(tmp_path):
    up = _mk_rbl(tmp_path)
    add_extracted_rows(tmp_path, CP, JOB, RBL, [_row("row-1", up), _row("row-2", up)], at=AT, by=BY)
    review_row_in_log(tmp_path, CP, JOB, RBL, "row-1", CONFIRMED, at=AT, by=BY)
    q = review_queue(load_reviewed_bore_log(tmp_path, CP, JOB, RBL))
    assert q["rows_needing_review"] == ["row-2"]              # row-2 still UNREVIEWED
    assert q["rows_review_passed"] == ["row-1"]
    assert q["ungrouped_rows"] == ["row-1", "row-2"]          # neither grouped yet
    assert q["engine_ready"] is False
