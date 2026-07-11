"""Byte-identity + filtering proof for the Phase-2 ADDITIVE bridge params
(``harness.product_readiness_bridge.materialize_package_view`` / ``run_job_readiness``'s new
``allowed_upload_ids`` keyword, and the NEW ``run_job_route_readiness_raw`` function).

Fixture-free (uses ``complete_package_qa``, same as ``test_product_readiness_wiring.py``)."""
from __future__ import annotations

import tempfile
from pathlib import Path

from truelinev2.contracts.customer_project import create_customer_project
from truelinev2.contracts.processing_job import create_job, job_dir
from truelinev2.contracts.upload_pipeline import accept_upload
from truelinev2.harness import product_readiness_bridge as prb
from truelinev2.harness.complete_package_qa import SCENARIOS, build_complete_package

_NOW = "2026-01-01T00:00:00+00:00"
_TENANT = "cp-aaa"
_JOB = "job-1"


def _scenario_bytes(tmp_path, key="complete_ready"):
    sc = next(s for s in SCENARIOS if s.key == key)
    pkg = build_complete_package(tmp_path / "qa_src", name="src-%s" % key, labels=sc.labels,
                                 route_shape=sc.route_shape, bore_csv=sc.bore_csv)
    up = Path(pkg) / "uploads"
    plan = (up / "plan.pdf").read_bytes() if (up / "plan.pdf").is_file() else None
    borelog = (up / "bore-log.csv").read_bytes() if (up / "bore-log.csv").is_file() else None
    return plan, borelog


def _seed(tmp_path):
    store = tmp_path / "product_store"
    create_customer_project(store, _TENANT, "Label", _NOW)
    create_job(store, _TENANT, _JOB, _NOW, "sess-1")
    plan, borelog = _scenario_bytes(tmp_path)
    plan_up = accept_upload(store, _TENANT, _JOB, kind="PLAN_PDF", filename="plan.pdf", content=plan,
                            stored_at=_NOW)
    bore_up = accept_upload(store, _TENANT, _JOB, kind="BORE_LOG", filename="bore-log.csv", content=borelog,
                            stored_at=_NOW)
    return store, plan_up, bore_up


# --------------------------------------------------------------------------------------------------------- #
# materialize_package_view — allowed_upload_ids additive param.
# --------------------------------------------------------------------------------------------------------- #
def test_materialize_view_none_filter_is_byte_identical_to_omitted(tmp_path):
    store, plan_up, bore_up = _seed(tmp_path)
    uploads = [plan_up, bore_up]
    with tempfile.TemporaryDirectory() as w1, tempfile.TemporaryDirectory() as w2:
        pkg_omitted = prb.materialize_package_view(uploads, job_dir(store, _TENANT, _JOB), w1)
        pkg_none = prb.materialize_package_view(uploads, job_dir(store, _TENANT, _JOB), w2,
                                                 allowed_upload_ids=None)
        manifest_omitted = (Path(pkg_omitted) / "package.json").read_text(encoding="utf-8")
        manifest_none = (Path(pkg_none) / "package.json").read_text(encoding="utf-8")
        assert manifest_omitted == manifest_none


def test_materialize_view_filters_to_allowed_uploads_only(tmp_path):
    store, plan_up, bore_up = _seed(tmp_path)
    uploads = [plan_up, bore_up]
    with tempfile.TemporaryDirectory() as w:
        pkg = prb.materialize_package_view(uploads, job_dir(store, _TENANT, _JOB), w,
                                           allowed_upload_ids=[plan_up["upload_id"]])
        import json
        manifest = json.loads((Path(pkg) / "package.json").read_text(encoding="utf-8"))
        kinds = {u["kind"] for u in manifest["uploads"]}
        assert kinds == {"PLAN_PDF"}                          # BORE_LOG excluded even though it's a valid kind


def test_materialize_view_empty_allowlist_returns_none(tmp_path):
    store, plan_up, bore_up = _seed(tmp_path)
    with tempfile.TemporaryDirectory() as w:
        pkg = prb.materialize_package_view([plan_up, bore_up], job_dir(store, _TENANT, _JOB), w,
                                           allowed_upload_ids=[])
        assert pkg is None


# --------------------------------------------------------------------------------------------------------- #
# run_job_readiness — allowed_upload_ids additive param (default None = unchanged byte-identical result).
# --------------------------------------------------------------------------------------------------------- #
def test_run_job_readiness_default_none_matches_prior_signature_call(tmp_path):
    store, plan_up, bore_up = _seed(tmp_path)
    uploads = [plan_up, bore_up]
    jroot = job_dir(store, _TENANT, _JOB)
    r_omitted = prb.run_job_readiness(uploads, jroot, plan_sheet=1)
    r_none = prb.run_job_readiness(uploads, jroot, plan_sheet=1, allowed_upload_ids=None)
    assert r_omitted == r_none


def test_run_job_readiness_filtered_to_plan_only_is_missing_span_source(tmp_path):
    store, plan_up, bore_up = _seed(tmp_path)
    jroot = job_dir(store, _TENANT, _JOB)
    r_full = prb.run_job_readiness([plan_up, bore_up], jroot, plan_sheet=1)
    assert r_full["readiness_status"] == "READY_FOR_REVIEW_REDLINE"
    r_filtered = prb.run_job_readiness([plan_up, bore_up], jroot, plan_sheet=1,
                                       allowed_upload_ids=[plan_up["upload_id"]])
    assert r_filtered["readiness_status"] != "READY_FOR_REVIEW_REDLINE"   # borelog excluded -> no span source


# --------------------------------------------------------------------------------------------------------- #
# run_job_route_readiness_raw — new function: artifact-free, filtered, returns RAW dataclasses.
# --------------------------------------------------------------------------------------------------------- #
def test_raw_readiness_returns_route_geometry_and_reach_tol(tmp_path):
    store, plan_up, bore_up = _seed(tmp_path)
    jroot = job_dir(store, _TENANT, _JOB)
    readiness, sheet_ctx = prb.run_job_route_readiness_raw(
        [plan_up, bore_up], jroot, allowed_upload_ids=[plan_up["upload_id"], bore_up["upload_id"]])
    assert readiness is not None
    assert readiness.report.status == "READY_FOR_REVIEW_REDLINE"
    v = next(v for v in readiness.routes.verifications if v.route_ready)
    assert len(v.route_geometry) >= 1
    reach_tol = v.detail["isolation"]["detail"]["reach_tol"]
    assert isinstance(reach_tol, (int, float)) and reach_tol > 0
    assert sheet_ctx["pdf_page"] == 1


def test_raw_readiness_filtered_excludes_unselected_uploads(tmp_path):
    store, plan_up, bore_up = _seed(tmp_path)
    jroot = job_dir(store, _TENANT, _JOB)
    readiness, sheet_ctx = prb.run_job_route_readiness_raw(
        [plan_up, bore_up], jroot, allowed_upload_ids=[plan_up["upload_id"]])   # NO bore log
    assert readiness is None or readiness.report.status != "READY_FOR_REVIEW_REDLINE"


def test_raw_readiness_writes_no_artifact_and_no_store_file(tmp_path):
    store, plan_up, bore_up = _seed(tmp_path)
    jroot = job_dir(store, _TENANT, _JOB)
    before = sorted(jroot.rglob("*")) if jroot.exists() else []
    prb.run_job_route_readiness_raw([plan_up, bore_up], jroot,
                                    allowed_upload_ids=[plan_up["upload_id"], bore_up["upload_id"]])
    after = sorted(jroot.rglob("*"))
    assert before == after                                    # nothing new written under the job dir
    assert not list(jroot.rglob("*.png"))


def test_raw_readiness_no_spine_input_when_allowlist_empty(tmp_path):
    store, plan_up, bore_up = _seed(tmp_path)
    jroot = job_dir(store, _TENANT, _JOB)
    readiness, sheet_ctx = prb.run_job_route_readiness_raw([plan_up, bore_up], jroot, allowed_upload_ids=[])
    assert readiness is None
    assert sheet_ctx["refusal"] == "NO_SPINE_INPUT"
