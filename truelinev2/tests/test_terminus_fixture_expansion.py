"""Track B fixture expansion — realistic, name-free terminus EVIDENCE classes (read-only observer).

Beyond the generic per-fixture oracle check in test_terminus_extractor.py, this pins the SPECIFIC honest
behavior of each new evidence class, proves depth/BOC are carried-but-inert, and shows the observer never
changes placement/status/AUTO — including the case that is a FUTURE AUTO candidate (places a REVIEW today AND
has both endpoints source-bound) which still stays REVIEW because no AUTO promotion exists yet.
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
from truelinev2.contracts.terminus_report import STATUS_EVALUATED, terminus_evidence_report
from truelinev2.contracts.upload_pipeline import accept_upload
from truelinev2.extract import terminus_evidence as te
from truelinev2.extract.terminus_extractor import extract_termini
from truelinev2.harness.terminus_fixtures import build_terminus_fixtures, load_terminus_fixtures
from truelinev2.ingest.normalize import load_borelog

_AT, _BY = "2026-01-01T00:00:00Z", "g3-expansion-test"
_COLD = {"corpora": [], "configured": True}


def _fixtures(tmp_path):
    root = tmp_path / "term_fixtures"
    build_terminus_fixtures(root)
    return {f.fixture_id: f for f in load_terminus_fixtures(root)}


def _ev(fx):
    return extract_termini(fx.plan_path, fx.borelog_path)


def _provision(store, tenant, job, plan_bytes, borelog_bytes):
    """Provision a cold product job (plan + one engine-ready reviewed bore-log) and return (tenant, job)."""
    create_customer_project(store, tenant, "expansion fixture", _AT)
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


# --------------------------------------------------------------------------- #
# New evidence classes — the SPECIFIC honest behavior of each.
# --------------------------------------------------------------------------- #
def test_ambiguous_endpoint_is_never_coin_flipped(tmp_path):
    ev = _ev(_fixtures(tmp_path)["term-005-ambiguous-end"])
    assert ev.start.source_bound is True                       # a single START note still binds
    assert ev.end.source_bound is False and ev.end.source_type == te.BORE_LOG_ROW
    assert ev.end.blocker == te.AMBIGUOUS_END_STRUCTURE
    assert ev.end.structure_label is None and ev.end.source_text is None   # never picked one rival


def test_bare_station_callout_is_not_a_structure_proof(tmp_path):
    ev = _ev(_fixtures(tmp_path)["term-006-bare-station-callout"])
    for end, code in ((ev.start, te.NO_PRINTED_START_STRUCTURE), (ev.end, te.NO_PRINTED_END_STRUCTURE)):
        assert end.source_bound is False and end.source_type == te.BORE_LOG_ROW
        assert end.blocker == code and end.source_text is None      # a bare 'STA n' is not bound


def test_nearby_note_for_another_station_does_not_over_bind(tmp_path):
    ev = _ev(_fixtures(tmp_path)["term-007-offset-note-other-station"])
    assert ev.start.source_bound is True                       # the correct START note binds
    # the END-area note is for 14+50, not the bore end 13+25 -> NOT bound (identity is exact, not nearest)
    assert ev.end.source_bound is False and ev.end.blocker == te.NO_PRINTED_END_STRUCTURE
    assert ev.end.station_str == "13+25" and ev.end.structure_label is None


def test_multi_sheet_end_binds_on_the_second_sheet(tmp_path):
    ev = _ev(_fixtures(tmp_path)["term-008-multi-sheet-end-on-sheet-2"])
    assert ev.start.source_bound is True and ev.start.sheet == 1
    assert ev.end.source_bound is True and ev.end.sheet == 2
    assert ev.end.source_text and "SPLICE" in ev.end.structure_label


def test_depth_and_boc_are_carried_metadata_not_used_for_binding(tmp_path):
    by = _fixtures(tmp_path)
    carried = _ev(by["term-009-depth-boc-carried-metadata"])
    plain = _ev(by["term-001-both-bound"])
    # the bore-log DOES carry depth (read into the Bore) ...
    bore = load_borelog(str(by["term-009-depth-boc-carried-metadata"].borelog_path))
    assert bore.depth_min_ft == 7.5
    # ... but the terminus evidence is identical with or without depth/BOC -> they do not affect binding.
    for c, p in ((carried.start, plain.start), (carried.end, plain.end)):
        assert (c.source_bound, c.source_type, c.station_str, c.blocker) == \
               (p.source_bound, p.source_type, p.station_str, p.blocker)


def test_route_geometry_without_printed_termini_has_no_source_bound_endpoints(tmp_path):
    ev = _ev(_fixtures(tmp_path)["term-010-route-geometry-no-termini"])
    assert ev.both_source_bound is False
    assert set(ev.missing_blockers) == {te.NO_PRINTED_START_STRUCTURE, te.NO_PRINTED_END_STRUCTURE}


# --------------------------------------------------------------------------- #
# The observer never changes placement/status/AUTO — including the future-AUTO-candidate case.
# --------------------------------------------------------------------------- #
def test_both_source_bound_is_a_future_auto_candidate_but_still_review(tmp_path):
    by = _fixtures(tmp_path)
    fx = by["term-001-both-bound"]
    store, tenant, job = tmp_path / "store", "cp-bound-review", "job-bound-review"
    _provision(store, tenant, job, fx.plan_path.read_bytes(), fx.borelog_path.read_bytes())

    decision = run_product_redline(store, tenant, job, registry=_COLD, at=_AT, by=_BY)
    # places a REVIEW candidate (the generic lane never auto-promotes) ...
    assert decision["path"] == "UPLOADED_REVIEW"

    report = terminus_evidence_report(store, tenant, job)
    assert report["status"] == STATUS_EVALUATED
    ev = report["termini"][0]["evidence"]
    # ... AND both endpoints are source-bound -> this is the shape a FUTURE AUTO gate would consider.
    assert ev["both_source_bound"] is True and ev["missing_blockers"] == []
    # But observing that evidence must NOT have promoted anything: the placement is still REVIEW, never AUTO.
    after = run_product_redline(store, tenant, job, registry=_COLD, at=_AT, by=_BY)
    assert after["path"] == "UPLOADED_REVIEW"
    assert (after.get("review") or {}).get("tier") != "AUTO"


def test_observer_does_not_change_decision_status_or_candidate(tmp_path):
    by = _fixtures(tmp_path)
    fx = by["term-010-route-geometry-no-termini"]            # places a REVIEW, no source-bound termini
    store, tenant, job = tmp_path / "store", "cp-readonly2", "job-readonly2"
    _provision(store, tenant, job, fx.plan_path.read_bytes(), fx.borelog_path.read_bytes())

    decision = run_product_redline(store, tenant, job, registry=_COLD, at=_AT, by=_BY)
    assert decision["path"] == "UPLOADED_REVIEW"
    job_before = copy.deepcopy(load_job(store, tenant, job))
    cands_before = copy.deepcopy(list_review_candidates(store, tenant, job))

    report = terminus_evidence_report(store, tenant, job)
    # this fixture is NOT an AUTO candidate (no printed termini)
    assert report["termini"][0]["evidence"]["both_source_bound"] is False

    assert load_job(store, tenant, job) == job_before, "terminus report must not change the job"
    assert list_review_candidates(store, tenant, job) == cands_before, "must not change the candidate"
