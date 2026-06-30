"""G3 — read-only TERMINUS EVIDENCE REPORT (DISPLAY-only observer).

Proves the report:
  * surfaces the SAME source-backed evidence the G1/G2 oracle defines, per provisioned job;
  * reports honest NAMED blockers when an input (plan / engine-ready bore-log) is missing;
  * yields one terminus entry per engine-ready reviewed bore-log (multi-bore);
  * is READ-ONLY: calling it never changes a job's status, slots, or its REVIEW candidate (so placement /
    AUTO / the deterministic frontier are untouched);
  * is OBSERVER-ONLY at the source level (no orchestrator/renderer/mutation wiring);
  * is reachable through the default-OFF product API route with tenant isolation.
"""
from __future__ import annotations

import ast
import copy
import dataclasses
from pathlib import Path

import pytest
from fastapi import HTTPException

from truelinev2.api import product_pipeline_routes as ppr
from truelinev2.api.app import create_app
from truelinev2.config import Settings
from truelinev2.context import require_context
from truelinev2.contracts.customer_project import create_customer_project
from truelinev2.contracts.extracted_row import CONFIRMED, MANUAL_ENTRY, new_extracted_row
from truelinev2.contracts.processing_job import create_job, load_job
from truelinev2.contracts.product_workflow import run_product_redline
from truelinev2.contracts.review_acceptance import list_review_candidates
from truelinev2.contracts.reviewed_bore_log import (
    GROUPING_CONFIRMED,
    SEPARATE_BORE,
    add_extracted_rows,
    create_reviewed_bore_log,
    define_segment_group,
    review_row_in_log,
    set_grouping_status,
)
from truelinev2.contracts.terminus_report import (
    NO_ENGINE_READY_REVIEWED_BORE_LOG,
    NO_PLAN_PDF_UPLOAD,
    STATUS_EVALUATED,
    STATUS_NO_INPUTS,
    terminus_evidence_report,
)
from truelinev2.contracts.upload_pipeline import accept_upload
from truelinev2.extract import terminus_evidence as te
from truelinev2.harness.synth import borelog_xlsx, plan_tight_red_run
from truelinev2.harness.terminus_fixtures import build_terminus_fixtures, load_terminus_fixtures

_AT = "2026-01-01T00:00:00Z"
_BY = "g3-terminus-report-test"
# A configured-but-empty registry: forces the cold (non-recognized) decision path, exactly like the harness.
_COLD_REGISTRY = {"corpora": [], "configured": True}


def _provision_job(store, tenant, job, *, plan_bytes, borelogs, plan_name="project_plan.pdf"):
    """Provision a product job with one PLAN_PDF and N bore-logs. ``borelogs`` is a list of
    ``(rbl_id, group_id, filename, content_bytes, rows)`` — rows=0 leaves the review gate UNSATISFIED (no
    engine-ready reviewed bore-log), otherwise the bore-log is driven to engine-ready."""
    create_customer_project(store, tenant, "G3 terminus report fixture", _AT)
    create_job(store, tenant, job, _AT, _BY)
    if plan_bytes is not None:
        accept_upload(store, tenant, job, kind="PLAN_PDF", filename=plan_name,
                      content=plan_bytes, stored_at=_AT)
    for rbl_id, group_id, filename, content, rows in borelogs:
        rec = accept_upload(store, tenant, job, kind="BORE_LOG", filename=filename,
                            content=content, stored_at=_AT)
        up_id = rec["upload_id"]
        if not rows:
            continue
        create_reviewed_bore_log(store, tenant, job, up_id, rbl_id, at=_AT, by=_BY)
        row_ids = ["row-%d" % (k + 1) for k in range(rows)]
        row_objs = [new_extracted_row(rid, up_id, raw={"src": filename}, normalized={"src": filename},
                                      extraction_method=MANUAL_ENTRY, at=_AT, by=_BY)
                    for rid in row_ids]
        add_extracted_rows(store, tenant, job, rbl_id, row_objs, at=_AT, by=_BY)
        for rid in row_ids:
            review_row_in_log(store, tenant, job, rbl_id, rid, CONFIRMED, at=_AT, by=_BY)
        define_segment_group(store, tenant, job, rbl_id, group_id, row_ids, SEPARATE_BORE, at=_AT, by=_BY)
        set_grouping_status(store, tenant, job, rbl_id, group_id, GROUPING_CONFIRMED, at=_AT, by=_BY)


# --------------------------------------------------------------------------- #
# (1) The report surfaces the SAME source-backed evidence the G1/G2 oracle defines.
# --------------------------------------------------------------------------- #
def test_report_surfaces_oracle_evidence_per_terminus_fixture(tmp_path):
    fx_root = tmp_path / "term_fixtures"
    build_terminus_fixtures(fx_root)
    store = tmp_path / "store"

    for fx in load_terminus_fixtures(fx_root):
        tenant = ("cp-%s" % fx.fixture_id)[:63]
        job = ("job-%s" % fx.fixture_id)[:63]
        _provision_job(store, tenant, job,
                       plan_bytes=fx.plan_path.read_bytes(),
                       borelogs=[("rbl-main", "g-1", "bore_log.xlsx", fx.borelog_path.read_bytes(), 1)])

        report = terminus_evidence_report(store, tenant, job)
        assert report["status"] == STATUS_EVALUATED and report["runnable"] is True
        assert report["plan_present"] is True
        assert len(report["termini"]) == 1, report
        entry = report["termini"][0]
        assert entry["reviewed_bore_log_id"] == "rbl-main"
        ev = entry["evidence"]
        for which in ("start", "end"):
            exp = fx.expected[which]
            obs = ev[which]
            assert obs["source_bound"] == exp["source_bound"], (fx.fixture_id, which, obs)
            assert obs["source_type"] == exp["source_type"], (fx.fixture_id, which, obs)
            assert obs["blocker"] == exp["blocker"], (fx.fixture_id, which, obs)
            # the station VALUE is always read from source (bore-log row), never invented
            assert obs["station_ft"] is not None


def test_report_bound_endpoint_carries_printed_proof_and_never_implies_auto(tmp_path):
    fx_root = tmp_path / "term_fixtures"
    build_terminus_fixtures(fx_root)
    store = tmp_path / "store"
    by_id = {f.fixture_id: f for f in load_terminus_fixtures(fx_root)}
    fx = by_id["term-001-both-bound"]
    _provision_job(store, "cp-bound", "job-bound",
                   plan_bytes=fx.plan_path.read_bytes(),
                   borelogs=[("rbl-main", "g-1", "bore_log.xlsx", fx.borelog_path.read_bytes(), 1)])

    ev = terminus_evidence_report(store, "cp-bound", "job-bound")["termini"][0]["evidence"]
    assert ev["both_source_bound"] is True and ev["missing_blockers"] == []
    # a printed-bound endpoint quotes the verbatim note + structure label; confidence reflects PRINTED proof,
    # NOT an AUTO promotion (BORE_LOG_ROW is excluded from the source-bound set on purpose).
    assert ev["start"]["source_type"] == te.PRINTED_STRUCTURE_LABEL
    assert ev["start"]["source_text"] and "INSTALLER HH" in ev["start"]["structure_label"]
    assert ev["start"]["provenance"] == te.PRINTED_PLAN_TEXT and ev["start"]["confidence"] == 1.0
    assert ev["start"]["station_str"] == "11+75" and ev["end"]["station_str"] == "13+25"


def test_report_missing_endpoint_is_borelog_value_with_named_blocker(tmp_path):
    fx_root = tmp_path / "term_fixtures"
    build_terminus_fixtures(fx_root)
    store = tmp_path / "store"
    by_id = {f.fixture_id: f for f in load_terminus_fixtures(fx_root)}
    fx = by_id["term-003-none-bound"]
    _provision_job(store, "cp-none", "job-none",
                   plan_bytes=fx.plan_path.read_bytes(),
                   borelogs=[("rbl-main", "g-1", "bore_log.xlsx", fx.borelog_path.read_bytes(), 1)])

    ev = terminus_evidence_report(store, "cp-none", "job-none")["termini"][0]["evidence"]
    assert ev["both_source_bound"] is False
    assert set(ev["missing_blockers"]) == {te.NO_PRINTED_START_STRUCTURE, te.NO_PRINTED_END_STRUCTURE}
    for end, code in ((ev["start"], te.NO_PRINTED_START_STRUCTURE), (ev["end"], te.NO_PRINTED_END_STRUCTURE)):
        assert end["source_bound"] is False and end["source_type"] == te.BORE_LOG_ROW
        assert end["blocker"] == code and end["source_text"] is None


# --------------------------------------------------------------------------- #
# (2) Honest NAMED blockers when an input is missing (no invented endpoints).
# --------------------------------------------------------------------------- #
def test_report_no_plan_pdf_blocks_honestly(tmp_path):
    store = tmp_path / "store"
    _provision_job(store, "cp-noplan", "job-noplan",
                   plan_bytes=None,
                   borelogs=[("rbl-main", "g-1", "bore_log.xlsx", borelog_xlsx(), 1)])
    report = terminus_evidence_report(store, "cp-noplan", "job-noplan")
    assert report["status"] == STATUS_NO_INPUTS and report["runnable"] is False
    assert report["plan_present"] is False and report["termini"] == []
    assert NO_PLAN_PDF_UPLOAD in {b["code"] for b in report["blockers"]}


def test_report_no_engine_ready_borelog_blocks_honestly(tmp_path):
    store = tmp_path / "store"
    # bore-log uploaded but the review gate is NOT satisfied (rows=0) -> not engine-ready.
    _provision_job(store, "cp-nordy", "job-nordy",
                   plan_bytes=plan_tight_red_run(),
                   borelogs=[("rbl-main", "g-1", "bore_log.xlsx", borelog_xlsx(), 0)])
    report = terminus_evidence_report(store, "cp-nordy", "job-nordy")
    assert report["status"] == STATUS_NO_INPUTS and report["termini"] == []
    assert NO_ENGINE_READY_REVIEWED_BORE_LOG in {b["code"] for b in report["blockers"]}
    # the plan WAS resolved -> the report is honest about what it did and did not find
    assert report["plan_present"] is True


# --------------------------------------------------------------------------- #
# (3) Multi-bore: one terminus entry per engine-ready reviewed bore-log.
# --------------------------------------------------------------------------- #
def test_report_yields_one_entry_per_engine_ready_bore_log(tmp_path):
    store = tmp_path / "store"
    _provision_job(store, "cp-multi", "job-multi",
                   plan_bytes=plan_tight_red_run(),
                   borelogs=[
                       ("rbl-a", "g-a", "bore_log_a.xlsx", borelog_xlsx("11+75", "13+25"), 1),
                       ("rbl-b", "g-b", "bore_log_b.xlsx", borelog_xlsx("20+00", "21+50"), 1),
                   ])
    report = terminus_evidence_report(store, "cp-multi", "job-multi")
    assert report["status"] == STATUS_EVALUATED
    rbl_ids = sorted(e["reviewed_bore_log_id"] for e in report["termini"])
    assert rbl_ids == ["rbl-a", "rbl-b"]
    # each entry is a full BoreTerminusEvidence with both endpoints present
    for e in report["termini"]:
        assert e["evidence"]["start"]["which"] == "START" and e["evidence"]["end"]["which"] == "END"


# --------------------------------------------------------------------------- #
# (4) READ-ONLY: the report changes no placement status, no slots, no REVIEW candidate.
# --------------------------------------------------------------------------- #
def test_report_does_not_change_job_status_slots_or_review_candidate(tmp_path):
    store = tmp_path / "store"
    tenant, job = "cp-readonly", "job-readonly"
    _provision_job(store, tenant, job,
                   plan_bytes=plan_tight_red_run(),
                   borelogs=[("rbl-main", "g-1", "bore_log.xlsx", borelog_xlsx(), 1)])

    # Drive the REAL cold decision so the job has a placement status + a REVIEW candidate to protect.
    decision = run_product_redline(store, tenant, job, registry=_COLD_REGISTRY, at=_AT, by=_BY)
    assert decision["path"] in ("UPLOADED_REVIEW", "ABSTAIN")     # cold path; never recognized/AUTO here

    job_before = copy.deepcopy(load_job(store, tenant, job))
    cands_before = copy.deepcopy(list_review_candidates(store, tenant, job))

    # Call the observer twice — it must mutate nothing.
    r1 = terminus_evidence_report(store, tenant, job)
    r2 = terminus_evidence_report(store, tenant, job)
    assert r1 == r2                                              # deterministic, no side effects

    job_after = load_job(store, tenant, job)
    cands_after = list_review_candidates(store, tenant, job)
    assert job_after == job_before, "terminus report must not change job status/slots/audit"
    assert cands_after == cands_before, "terminus report must not change the REVIEW candidate"
    # the placement decision itself is unchanged after the read
    decision_again = run_product_redline(store, tenant, job, registry=_COLD_REGISTRY, at=_AT, by=_BY)
    assert decision_again["path"] == decision["path"]


# --------------------------------------------------------------------------- #
# (5) OBSERVER-ONLY at the source level: no orchestrator / renderer / mutation wiring.
# --------------------------------------------------------------------------- #
def test_terminus_report_module_is_observer_only():
    """AST-level (not doc-prose) proof: terminus_report imports no placement/mutation contract and calls no
    orchestrator / renderer / persistence mutator — so it can never change a placement, its status, AUTO, or
    the deterministic frontier."""
    path = Path(te.__file__).resolve().parents[1] / "contracts" / "terminus_report.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename="terminus_report.py")

    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(n.name for n in node.names)
    forbidden_imports = {
        "truelinev2.contracts.product_workflow",
        "truelinev2.contracts.uploaded_corpus_engine_handoff",
        "truelinev2.contracts.review_acceptance",
        "truelinev2.contracts.recognized_corpus_handoff",
        "truelinev2.contracts.manifest_handoff",
        "truelinev2.contracts.kmz_export",
        "truelinev2.contracts.closeout_review",
        "truelinev2.contracts.billing_summary",
        "truelinev2.contracts.export_package",
    }
    assert not (imported & forbidden_imports), \
        "terminus_report must not import placement/mutation contracts: %r" % (imported & forbidden_imports)

    called = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name):
                called.add(f.id)
            elif isinstance(f, ast.Attribute):
                called.add(f.attr)
    forbidden_calls = {
        "run_product_redline", "generate_review_candidate", "accept_review_candidate",
        "reject_review_candidate", "transition", "render_recognized_corpus_handoff",
        "render_uploaded_corpus_engine_handoff", "assemble_export_package", "write_reviewed_bore_log",
        "write_text", "write_bytes", "mkdir",
    }
    assert not (called & forbidden_calls), \
        "terminus_report must not call mutators: %r" % (called & forbidden_calls)


# --------------------------------------------------------------------------- #
# (6) The default-OFF product API route exposes the report with tenant isolation.
# --------------------------------------------------------------------------- #
def _container(tmp_path, store):
    settings = dataclasses.replace(
        Settings.for_proof(),
        artifact_root=tmp_path / "artifacts",
        cards_dir=tmp_path / "cards",
        db_path=tmp_path / "truelinev2.db",
        product_pipeline_api_optin=True,
        product_store_root=store,
        product_billing_cost_rules_path=tmp_path / "cost_rules.json",
    )
    return create_app(settings).state.tl2


def test_route_returns_evidence_and_isolates_tenants(tmp_path):
    store = tmp_path / "product_store"
    _provision_job(store, "cp-route", "job-route",
                   plan_bytes=plan_tight_red_run(),
                   borelogs=[("rbl-main", "g-1", "bore_log.xlsx", borelog_xlsx(), 1)])
    c = _container(tmp_path, store)

    out = ppr.get_terminus_evidence("job-route", ctx=require_context("cp-route", "sess-1"), c=c)
    assert out["status"] == STATUS_EVALUATED and len(out["termini"]) == 1
    assert out["termini"][0]["reviewed_bore_log_id"] == "rbl-main"

    # a different tenant cannot see this job -> 404 (cross-tenant isolation)
    with pytest.raises(HTTPException) as exc:
        ppr.get_terminus_evidence("job-route", ctx=require_context("cp-other", "sess-1"), c=c)
    assert exc.value.status_code == 404

    # a missing job under the owning tenant -> 404
    with pytest.raises(HTTPException) as exc2:
        ppr.get_terminus_evidence("job-absent", ctx=require_context("cp-route", "sess-1"), c=c)
    assert exc2.value.status_code == 404
