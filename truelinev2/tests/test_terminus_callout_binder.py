"""Read-only printed station-callout terminus binder (PRINTED_STA_CALLOUT).

Proves: the binder reads name-free station-range callouts and binds endpoints by EXACT identity only (no
proximity, no coin-flip, no bare-station bind); it NEVER reads named-dialect text; each fixture stays in the
cold/generic lane (select_dialect is None) and remains REVIEW today; a callout that conflicts with a printed
structure label is surfaced as a conflict (never silently preferred); and observing the evidence changes no
placement/status.
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
from truelinev2.extract.callout_anchor import (
    CALLOUT_AMBIGUOUS,
    CALLOUT_BOUND,
    CALLOUT_NONE,
    anchored_disagreement,
    bind_endpoint_callout,
    span_callouts,
)
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.terminus_extractor import extract_termini
from truelinev2.harness.terminus_callout_fixtures import build_callout_fixtures, load_callout_fixtures
from truelinev2.ingest.pdf import PlanPdf

_AT, _BY = "2026-01-01T00:00:00Z", "callout-test"
_COLD = {"corpora": [], "configured": True}


def _fixtures(tmp_path):
    root = tmp_path / "callout_fx"
    build_callout_fixtures(root)
    return load_callout_fixtures(root)


def _provision_and_decide(store, tenant, job, plan_bytes, borelog_bytes):
    create_customer_project(store, tenant, "callout fixture", _AT)
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
def test_span_callouts_grammar_and_named_dialect_exclusion():
    # a name-free range binds; reversed range normalizes to (low, high)
    spans = span_callouts(["BORE 11+75 TO 13+25"])
    assert len(spans) == 1 and spans[0].from_sta == "11+75" and spans[0].to_sta == "13+25"
    assert span_callouts(["BORE 13+25 TO 11+75"])[0].from_sta == "11+75"   # normalized
    # NAMED-dialect grammars are never read (keeps a cold fixture cold)
    assert span_callouts(["STA 11+75 TO STA 13+25"]) == []                 # Brenham run callout
    assert span_callouts(["STA 11+75 TO STA 13+25 DIR. BORE (150')"]) == []
    assert span_callouts(["DIRECTIONAL BORE 11+75 TO 13+25"]) == []        # ODOT trigger
    assert span_callouts(["ALIGNMENT 10+00 thru 16+00"]) == []            # benign extent title (THRU)
    assert span_callouts(["STA 13+25"]) == []                             # bare station, no span


def test_bind_endpoint_callout_exact_and_ambiguous():
    spans = span_callouts(["BORE 11+75 TO 13+25"])
    assert bind_endpoint_callout("START", "11+75", spans).result == CALLOUT_BOUND
    assert bind_endpoint_callout("END", "13+25", spans).result == CALLOUT_BOUND
    # proximity is never a match (exact station only)
    assert bind_endpoint_callout("START", "11+80", spans).result == CALLOUT_NONE
    # two rivals -> ambiguous
    rivals = span_callouts(["BORE 11+75 TO 13+25", "PROPOSED BORE 11+75 TO 13+25"])
    assert bind_endpoint_callout("START", "11+75", rivals).result == CALLOUT_AMBIGUOUS


def test_anchored_disagreement_detects_a_conflicting_span():
    spans = span_callouts(["BORE 11+75 TO 13+50"])              # anchored at start 11+75, ends at 13+50
    assert anchored_disagreement("END", "13+25", "11+75", spans) == "13+50"
    assert anchored_disagreement("END", "13+25", "11+75", span_callouts(["BORE 11+75 TO 13+25"])) is None


def test_printed_sta_callout_is_in_the_auto_eligible_source_set():
    assert te.PRINTED_STA_CALLOUT in te.SOURCE_BOUND_TYPES
    assert te.BORE_LOG_ROW not in te.SOURCE_BOUND_TYPES


# --------------------------------------------------------------------------- #
# Per-fixture observer evidence.
# --------------------------------------------------------------------------- #
def test_callout_fixtures_match_expected_evidence(tmp_path):
    for fx in _fixtures(tmp_path):
        ev = extract_termini(fx.plan_path, fx.borelog_path)
        for which, obs in (("start", ev.start), ("end", ev.end)):
            exp = fx.expected[which]
            assert obs.source_bound == exp["source_bound"], (fx.fixture_id, which, obs)
            assert obs.source_type == exp["source_type"], (fx.fixture_id, which, obs)
            assert obs.blocker == exp["blocker"], (fx.fixture_id, which, obs)


def test_span_callout_binds_both_with_verbatim_text(tmp_path):
    fx = {f.fixture_id: f for f in _fixtures(tmp_path)}["callout-001-span-both-bound"]
    ev = extract_termini(fx.plan_path, fx.borelog_path)
    assert ev.both_source_bound is True
    assert ev.start.source_type == te.PRINTED_STA_CALLOUT and ev.end.source_type == te.PRINTED_STA_CALLOUT
    assert ev.start.source_text == "BORE 11+75 TO 13+25" and ev.end.source_text == "BORE 11+75 TO 13+25"
    assert ev.start.confidence == 1.0 and ev.end.confidence == 1.0


def test_callout_conflict_with_structure_label_is_surfaced_not_preferred(tmp_path):
    fx = {f.fixture_id: f for f in _fixtures(tmp_path)}["callout-006-conflicts-structure"]
    ev = extract_termini(fx.plan_path, fx.borelog_path)
    assert ev.start.source_bound is True and ev.start.source_type == te.PRINTED_STRUCTURE_LABEL
    # the END is NOT silently bound to either reading -> a conflict blocker, not a source-bound endpoint
    assert ev.end.source_bound is False and ev.end.blocker == te.CONFLICTING_END_TERMINUS
    assert "13+50" in ev.end.pedigree and "13+25" in ev.end.pedigree


# --------------------------------------------------------------------------- #
# Cold-lane guard + observer-only (no placement/status change).
# --------------------------------------------------------------------------- #
def test_every_callout_fixture_stays_in_the_cold_generic_lane(tmp_path):
    for fx in _fixtures(tmp_path):
        plan = PlanPdf(str(fx.plan_path))
        try:
            dialect = select_dialect(plan)
        finally:
            plan.close()
        # the callout grammar must NOT trigger a named dialect -> the fixture stays cold/generic
        assert dialect is None, (fx.fixture_id, getattr(dialect, "name", None))


def test_callout_fixtures_are_review_today_and_observer_is_read_only(tmp_path):
    for fx in _fixtures(tmp_path):
        tenant, job = ("cp-%s" % fx.fixture_id)[:63], ("job-%s" % fx.fixture_id)[:63]
        store = tmp_path / fx.fixture_id
        decision = _provision_and_decide(store, tenant, job,
                                         fx.plan_path.read_bytes(), fx.borelog_path.read_bytes())
        # placed by the generic lane as REVIEW (never recognized / AUTO)
        assert decision["path"] == "UPLOADED_REVIEW", fx.fixture_id
        assert decision.get("provenance") != "DETERMINISTIC_AUTO"
        assert (decision.get("review") or {}).get("tier") != "AUTO"
        # observing the terminus evidence changes nothing
        job_before = copy.deepcopy(load_job(store, tenant, job))
        cands_before = copy.deepcopy(list_review_candidates(store, tenant, job))
        terminus_evidence_report(store, tenant, job)
        assert load_job(store, tenant, job) == job_before
        assert list_review_candidates(store, tenant, job) == cands_before
