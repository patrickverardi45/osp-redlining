"""Read-only printed MATCHLINE boundary-station terminus binder (MATCHLINE_BOUNDARY_STATION).

Proves: the binder confirms ONLY the strict BILATERAL tier (both sheets print the crossing), refuses
unilateral / sheet-mismatched / proximity / ambiguous crossings, binds by exact station identity with verbatim
source text, surfaces a conflict when a callout disagrees, keeps every fixture in the cold/generic lane
(select_dialect None) and REVIEW today, and never changes placement/status (observer-only).
"""
from __future__ import annotations

import copy

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
from truelinev2.contracts.terminus_report import terminus_evidence_report
from truelinev2.contracts.upload_pipeline import accept_upload
from truelinev2.extract import terminus_evidence as te
from truelinev2.extract.matchline_anchor import (
    MATCHLINE_AMBIGUOUS,
    MATCHLINE_BOUND,
    MATCHLINE_NONE,
    bilateral_boundaries,
    bind_endpoint_matchline,
)
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.terminus_extractor import extract_termini
from truelinev2.harness.terminus_matchline_fixtures import build_matchline_fixtures, load_matchline_fixtures
from truelinev2.ingest.pdf import PlanPdf

_AT, _BY = "2026-01-01T00:00:00Z", "matchline-test"
_COLD = {"corpora": [], "configured": True}


def _fixtures(tmp_path):
    root = tmp_path / "matchline_fx"
    build_matchline_fixtures(root)
    return load_matchline_fixtures(root)


def _provision_and_decide(store, tenant, job, plan_bytes, borelog_bytes):
    create_customer_project(store, tenant, "matchline fixture", _AT)
    create_job(store, tenant, job, _AT, _BY)
    accept_upload(store, tenant, job, kind="PLAN_PDF", filename="project_plan.pdf",
                  content=plan_bytes, stored_at=_AT)
    rec = accept_upload(store, tenant, job, kind="BORE_LOG", filename="bore_log.xlsx",
                        content=borelog_bytes, stored_at=_AT)
    up = rec["upload_id"]
    create_reviewed_bore_log(store, tenant, job, up, "rbl-main", at=_AT, by=_BY)
    add_extracted_rows(store, tenant, job, "rbl-main",
                       [new_extracted_row("row-1", up, raw={"s": 1}, normalized={"s": 1},
                                          extraction_method=MANUAL_ENTRY, at=_AT, by=_BY)], at=_AT, by=_BY)
    review_row_in_log(store, tenant, job, "rbl-main", "row-1", CONFIRMED, at=_AT, by=_BY)
    define_segment_group(store, tenant, job, "rbl-main", "g-1", ["row-1"], SEPARATE_BORE, at=_AT, by=_BY)
    set_grouping_status(store, tenant, job, "rbl-main", "g-1", GROUPING_CONFIRMED, at=_AT, by=_BY)
    return run_product_redline(store, tenant, job, registry=_COLD, at=_AT, by=_BY)


# --------------------------------------------------------------------------- #
# Binder unit behavior.
# --------------------------------------------------------------------------- #
def test_bilateral_boundaries_require_both_sheets():
    lines = {
        1: ["MATCHLINE STA 13+25 - SEE SHEET 2"],
        2: ["MATCHLINE STA 13+25 - SEE SHEET 1"],
    }
    bds = bilateral_boundaries(lines, [1, 2], 1175.0, 1325.0)
    assert len(bds) == 1 and bds[0].station_sta == "13+25" and bds[0].pair == (1, 2)
    # unilateral -> no bilateral boundary
    assert bilateral_boundaries({1: ["MATCHLINE STA 13+25 - SEE SHEET 2"], 2: []}, [1, 2], 1175.0, 1325.0) == []
    # out-of-span boundary excluded
    assert bilateral_boundaries(
        {1: ["MATCHLINE STA 15+00 - SEE SHEET 2"], 2: ["MATCHLINE STA 15+00 - SEE SHEET 1"]},
        [1, 2], 1175.0, 1325.0) == []


def test_bind_endpoint_matchline_exact_unique():
    lines = {1: ["MATCHLINE STA 13+25 - SEE SHEET 2"], 2: ["MATCHLINE STA 13+25 - SEE SHEET 1"]}
    bds = bilateral_boundaries(lines, [1, 2], 1175.0, 1325.0)
    assert bind_endpoint_matchline("13+25", bds).result == MATCHLINE_BOUND
    assert bind_endpoint_matchline("13+20", bds).result == MATCHLINE_NONE     # exact only (proximity refused)


def test_matchline_boundary_station_is_auto_eligible():
    assert te.MATCHLINE_BOUNDARY_STATION in te.SOURCE_BOUND_TYPES


# --------------------------------------------------------------------------- #
# Per-fixture observer evidence.
# --------------------------------------------------------------------------- #
def test_matchline_fixtures_match_expected_evidence(tmp_path):
    for fx in _fixtures(tmp_path):
        ev = extract_termini(fx.plan_path, fx.borelog_path)
        for which, obs in (("start", ev.start), ("end", ev.end)):
            exp = fx.expected[which]
            assert obs.source_bound == exp["source_bound"], (fx.fixture_id, which, obs)
            assert obs.source_type == exp["source_type"], (fx.fixture_id, which, obs)
            assert obs.blocker == exp["blocker"], (fx.fixture_id, which, obs)


def test_bilateral_endpoint_binds_with_verbatim_text_and_sheets(tmp_path):
    fx = {f.fixture_id: f for f in _fixtures(tmp_path)}["matchline-001-bilateral-end"]
    ev = extract_termini(fx.plan_path, fx.borelog_path)
    assert ev.end.source_type == te.MATCHLINE_BOUNDARY_STATION and ev.end.source_bound is True
    assert ev.end.source_text == "MATCHLINE STA 13+25 - SEE SHEET 2"
    assert ev.end.confidence == 1.0 and ev.end.sheet == 1
    assert "sheets 1+2" in ev.end.pedigree


def test_both_endpoints_can_bind_matchline(tmp_path):
    fx = {f.fixture_id: f for f in _fixtures(tmp_path)}["matchline-002-both-bound"]
    ev = extract_termini(fx.plan_path, fx.borelog_path)
    assert ev.both_source_bound is True
    assert ev.start.source_type == te.MATCHLINE_BOUNDARY_STATION
    assert ev.end.source_type == te.MATCHLINE_BOUNDARY_STATION


def test_matchline_conflict_with_callout_is_surfaced(tmp_path):
    fx = {f.fixture_id: f for f in _fixtures(tmp_path)}["matchline-005-conflicts-callout"]
    ev = extract_termini(fx.plan_path, fx.borelog_path)
    assert ev.end.source_bound is False and ev.end.blocker == te.CONFLICTING_END_TERMINUS
    assert "13+50" in ev.end.pedigree


# --------------------------------------------------------------------------- #
# Cold-lane guard + observer-only.
# --------------------------------------------------------------------------- #
def test_every_matchline_fixture_stays_in_the_cold_generic_lane(tmp_path):
    for fx in _fixtures(tmp_path):
        plan = PlanPdf(str(fx.plan_path))
        try:
            dialect = select_dialect(plan)
        finally:
            plan.close()
        assert dialect is None, (fx.fixture_id, getattr(dialect, "name", None))


def test_matchline_fixtures_are_review_today_and_observer_is_read_only(tmp_path):
    for fx in _fixtures(tmp_path):
        tenant, job = ("cp-%s" % fx.fixture_id)[:63], ("job-%s" % fx.fixture_id)[:63]
        store = tmp_path / fx.fixture_id
        decision = _provision_and_decide(store, tenant, job,
                                         fx.plan_path.read_bytes(), fx.borelog_path.read_bytes())
        assert decision["path"] == "UPLOADED_REVIEW", fx.fixture_id
        assert decision.get("provenance") != "DETERMINISTIC_AUTO"
        assert (decision.get("review") or {}).get("tier") != "AUTO"
        job_before = copy.deepcopy(load_job(store, tenant, job))
        cands_before = copy.deepcopy(list_review_candidates(store, tenant, job))
        terminus_evidence_report(store, tenant, job)
        assert load_job(store, tenant, job) == job_before
        assert list_review_candidates(store, tenant, job) == cands_before
