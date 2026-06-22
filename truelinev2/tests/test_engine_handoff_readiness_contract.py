"""Contract tests: uploaded-corpus engine-handoff readiness (read-only). Asserts it is ALWAYS BLOCKED /
not runnable, names the capability + input blockers, never mutates the job (no slots / no bundle), and that
list_reviewed_bore_logs is tenant/job scoped. Pure stdlib + tmp_path; no engine/render. Generic ids only.
"""
from __future__ import annotations

from truelinev2.contracts.customer_project import create_customer_project
from truelinev2.contracts.processing_job import create_job, job_dir, load_job
from truelinev2.contracts.reviewed_bore_log import create_reviewed_bore_log, list_reviewed_bore_logs
from truelinev2.contracts.upload_pipeline import accept_upload
from truelinev2.contracts.engine_handoff_readiness import (
    GEOMETRY_SOLVER_CORPUS_SPECIFIC,
    NO_ENGINE_READY_REVIEWED_BORE_LOG,
    NO_PLAN_DIALECT,
    NO_PLAN_PDF_UPLOAD,
    NO_SOURCE_ANCHORS,
    UPLOADED_CORPUS_NOT_IMPLEMENTED,
    evaluate_engine_handoff_readiness,
)

AT = "2026-06-22T00:00:00Z"
BY = "operator-1"


def _job(tmp_path, cp="cp-0001", job="job-0001"):
    create_customer_project(tmp_path, cp, "Label", AT)
    create_job(tmp_path, cp, job, AT, BY)


def _codes(result):
    return {b["code"] for b in result["blockers"]}


def test_always_blocked_with_all_blockers_when_empty(tmp_path):
    _job(tmp_path)
    r = evaluate_engine_handoff_readiness(tmp_path, "cp-0001", "job-0001")
    assert r["status"] == "BLOCKED" and r["runnable"] is False
    assert r["checks"] == {"has_plan_pdf": False, "has_engine_ready_reviewed_bore_log": False}
    assert {UPLOADED_CORPUS_NOT_IMPLEMENTED, NO_PLAN_DIALECT, NO_SOURCE_ANCHORS,
            GEOMETRY_SOLVER_CORPUS_SPECIFIC, NO_PLAN_PDF_UPLOAD,
            NO_ENGINE_READY_REVIEWED_BORE_LOG} <= _codes(r)


def test_has_plan_pdf_true_drops_input_blocker_but_stays_blocked(tmp_path):
    _job(tmp_path)
    accept_upload(tmp_path, "cp-0001", "job-0001", kind="PLAN_PDF", filename="plan.pdf",
                  content=b"%PDF-1.4 x", stored_at=AT)
    r = evaluate_engine_handoff_readiness(tmp_path, "cp-0001", "job-0001")
    assert r["checks"]["has_plan_pdf"] is True
    assert NO_PLAN_PDF_UPLOAD not in _codes(r)
    assert r["status"] == "BLOCKED" and r["runnable"] is False
    assert UPLOADED_CORPUS_NOT_IMPLEMENTED in _codes(r)              # capability blocker always present


def test_readiness_does_not_mutate_job(tmp_path):
    _job(tmp_path)
    accept_upload(tmp_path, "cp-0001", "job-0001", kind="PLAN_PDF", filename="plan.pdf",
                  content=b"x", stored_at=AT)
    evaluate_engine_handoff_readiness(tmp_path, "cp-0001", "job-0001")
    job = load_job(tmp_path, "cp-0001", "job-0001")
    assert all(v is None for v in job["slots"].values())            # no output slots created
    assert not (job_dir(tmp_path, "cp-0001", "job-0001") / "bundle_store").exists()  # no bundle written


def test_list_reviewed_bore_logs_tenant_scoped(tmp_path):
    _job(tmp_path)
    up = accept_upload(tmp_path, "cp-0001", "job-0001", kind="BORE_LOG", filename="b.csv",
                       content=b"row\n", stored_at=AT)
    create_reviewed_bore_log(tmp_path, "cp-0001", "job-0001", up["upload_id"], "rbl-main", at=AT, by=BY)
    mine = [r["reviewed_bore_log_id"] for r in list_reviewed_bore_logs(tmp_path, "cp-0001", "job-0001")]
    assert mine == ["rbl-main"]
    create_customer_project(tmp_path, "cp-0002", "L", AT)
    create_job(tmp_path, "cp-0002", "job-0001", AT, BY)
    assert list_reviewed_bore_logs(tmp_path, "cp-0002", "job-0001") == []   # other project sees none
