"""G4 PREFLIGHT fixtures — prove the proof-bed loads, every case stays REVIEW/ABSTAIN TODAY (no AUTO, no
status change), and a DESIGN-ONLY oracle (mirroring G4_TERMINUS_AUTO_DESIGN.md §4) classifies exactly one
future positive candidate while rejecting every negative shape.

Nothing here promotes anything: the oracle is a TEST artifact, never wired into placement. The current engine
caps the generic lane at REVIEW; these tests assert that holds for every fixture.
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
from truelinev2.extract.terminus_extractor import extract_termini
from truelinev2.harness.g4_preflight_fixtures import (
    POSITIVE_CANDIDATE,
    build_g4_preflight_fixtures,
    load_g4_preflight_fixtures,
)

_AT, _BY = "2026-01-01T00:00:00Z", "g4-preflight-test"
_COLD = {"corpora": [], "configured": True}

# The proposed gate's AUTO-eligible terminus source types TODAY (design §2). DESIGN-ONLY (test oracle).
_AUTO_ELIGIBLE = {te.PRINTED_STRUCTURE_LABEL}


def _provision(store, tenant, job, plan_bytes, borelog_bytes, *, reviewed):
    create_customer_project(store, tenant, "g4 preflight", _AT)
    create_job(store, tenant, job, _AT, _BY)
    accept_upload(store, tenant, job, kind="PLAN_PDF", filename="project_plan.pdf",
                  content=plan_bytes, stored_at=_AT)
    rec = accept_upload(store, tenant, job, kind="BORE_LOG", filename="bore_log.xlsx",
                        content=borelog_bytes, stored_at=_AT)
    if not reviewed:
        return
    up = rec["upload_id"]
    create_reviewed_bore_log(store, tenant, job, up, "rbl-main", at=_AT, by=_BY)
    add_extracted_rows(store, tenant, job, "rbl-main",
                       [new_extracted_row("row-1", up, raw={"s": 1}, normalized={"s": 1},
                                          extraction_method=MANUAL_ENTRY, at=_AT, by=_BY)], at=_AT, by=_BY)
    review_row_in_log(store, tenant, job, "rbl-main", "row-1", CONFIRMED, at=_AT, by=_BY)
    define_segment_group(store, tenant, job, "rbl-main", "g-1", ["row-1"], SEPARATE_BORE, at=_AT, by=_BY)
    set_grouping_status(store, tenant, job, "rbl-main", "g-1", GROUPING_CONFIRMED, at=_AT, by=_BY)


def _would_auto_qualify(ev, decision) -> bool:
    """DESIGN-ONLY oracle mirroring G4_TERMINUS_AUTO_DESIGN.md §4 — applied to OBSERVED evidence + the real
    cold decision. This is a TEST artifact: it is never imported by any placement/contract code and promotes
    nothing. It returns True only for the lone source-backed, geometry-clean, same-sheet candidate."""
    if decision.get("path") != "UPLOADED_REVIEW":
        return False                                            # not even a placed REVIEW (e.g. abstained)
    if not (ev.start.source_bound and ev.end.source_bound):
        return False                                            # both endpoints must be source-bound
    if ev.start.source_type not in _AUTO_ELIGIBLE or ev.end.source_type not in _AUTO_ELIGIBLE:
        return False                                            # only printed-structure evidence today
    rec = (decision.get("review") or {}).get("record") or {}
    conf = rec.get("confidence") or {}
    if conf.get("band") == "LOW" or conf.get("correction_recommended"):
        return False                                            # geometry uncertain / correction-recommended
    warns = conf.get("warnings") or []
    if any("MULTIPLE_PLAUSIBLE" in w or "PARTIAL_SPAN" in w for w in warns):
        return False                                            # rival runs / partial coverage
    render_sheets = set(rec.get("render_sheets") or [])
    term_sheets = {s for s in (ev.start.sheet, ev.end.sheet) if s is not None}
    if render_sheets and term_sheets and not term_sheets.issubset(render_sheets):
        return False                                            # terminus bound on a different sheet
    return True


def _run(tmp_path):
    root = tmp_path / "g4fx"
    build_g4_preflight_fixtures(root)
    fixtures = load_g4_preflight_fixtures(root)
    store = tmp_path / "store"
    results = []
    for fx in fixtures:
        tenant, job = ("cp-%s" % fx.fixture_id)[:63], ("job-%s" % fx.fixture_id)[:63]
        _provision(store, tenant, job, fx.plan_path.read_bytes(), fx.borelog_path.read_bytes(),
                   reviewed=fx.reviewed)
        ev = extract_termini(fx.plan_path, fx.borelog_path)     # file-level observer (no rbl needed)
        decision = run_product_redline(store, tenant, job, registry=_COLD, at=_AT, by=_BY)
        results.append((fx, ev, decision, store, tenant, job))
    return results


def test_preflight_fixtures_load_and_observer_matches_expected(tmp_path):
    for fx, ev, _decision, _store, _t, _j in _run(tmp_path):
        for which, obs, exp in (("start", ev.start, fx.expected_start), ("end", ev.end, fx.expected_end)):
            assert obs.source_bound == exp["source_bound"], (fx.fixture_id, which)
            assert obs.source_type == exp["source_type"], (fx.fixture_id, which)
            assert obs.blocker == exp["blocker"], (fx.fixture_id, which)


def test_every_preflight_case_is_review_or_abstain_today_never_auto(tmp_path):
    for fx, _ev, decision, _store, _t, _j in _run(tmp_path):
        assert decision["path"] == fx.expected_path, fx.fixture_id          # behavior unchanged today
        assert decision["path"] in ("UPLOADED_REVIEW", "ABSTAIN")
        assert decision["path"] != "UPLOADED_AUTO"
        assert (decision.get("review") or {}).get("tier") != "AUTO"
        assert decision.get("provenance") != "DETERMINISTIC_AUTO"


def test_oracle_identifies_exactly_one_future_positive_candidate(tmp_path):
    results = _run(tmp_path)
    qualifies = {fx.fixture_id: _would_auto_qualify(ev, decision)
                 for fx, ev, decision, _s, _t, _j in results}
    positives = [fid for fid, q in qualifies.items() if q]
    # exactly one fixture WOULD qualify under the proposed gate ...
    assert positives == ["g4-01-lone-positive-candidate"], qualifies
    # ... and the declared labels agree: the positive is POSITIVE_CANDIDATE, every other is a NEGATIVE_*.
    for fx, _ev, _d, _s, _t, _j in results:
        if fx.future_auto == POSITIVE_CANDIDATE:
            assert qualifies[fx.fixture_id] is True, fx.fixture_id
        else:
            assert qualifies[fx.fixture_id] is False, fx.fixture_id
    # ... but even the qualifying candidate is still REVIEW today (no AUTO exists).
    cand = next(d for fx, _e, d, _s, _t, _j in results if fx.fixture_id == "g4-01-lone-positive-candidate")
    assert cand["path"] == "UPLOADED_REVIEW"


def test_negative_shapes_each_have_their_blocking_signal(tmp_path):
    by = {fx.fixture_id: (fx, ev, d) for fx, ev, d, _s, _t, _j in _run(tmp_path)}

    def conf(fid):
        return ((by[fid][2].get("review") or {}).get("record") or {}).get("confidence") or {}

    # ambiguous geometry: rival-run warning + correction
    assert conf("g4-02-both-bound-uncertain-geometry").get("correction_recommended") is True
    assert any("MULTIPLE_PLAUSIBLE" in w for w in conf("g4-02-both-bound-uncertain-geometry").get("warnings") or [])
    # low confidence: partial-coverage warning + LOW band
    assert conf("g4-03-both-bound-low-confidence-geometry").get("band") == "LOW"
    assert any("PARTIAL_SPAN" in w for w in conf("g4-03-both-bound-low-confidence-geometry").get("warnings") or [])
    # sheet mismatch: termini bound on sheet 2, placement on sheet 1
    fx4, ev4, d4 = by["g4-04-both-bound-sheet-mismatch"]
    assert ev4.start.sheet == 2 and ev4.end.sheet == 2
    rec4 = (d4.get("review") or {}).get("record") or {}
    assert set(rec4.get("render_sheets") or []) == {1}
    # conflicting endpoint: end is ambiguous, never coin-flipped
    _, ev5, _ = by["g4-05-conflicting-end-identity"]
    assert ev5.end.source_bound is False and ev5.end.blocker == te.AMBIGUOUS_END_STRUCTURE
    # false positive nearby text: the end stays unbound
    _, ev6, _ = by["g4-06-false-positive-nearby-text"]
    assert ev6.end.source_bound is False and ev6.end.blocker == te.NO_PRINTED_END_STRUCTURE


def test_reviewed_vs_unreviewed_pair(tmp_path):
    """Same clean both-bound plan: reviewed -> REVIEW (placeable); unreviewed -> ABSTAIN via the existing
    engine-ready gate (no AUTO, no bypass)."""
    by = {fx.fixture_id: d for fx, _e, d, _s, _t, _j in _run(tmp_path)}
    assert by["g4-01-lone-positive-candidate"]["path"] == "UPLOADED_REVIEW"
    unrev = by["g4-07-unreviewed-bore-log-row"]
    assert unrev["path"] == "ABSTAIN"
    assert any(b.get("code") == "NO_ENGINE_READY_REVIEWED_BORE_LOG" for b in unrev.get("blockers") or [])


def test_terminus_report_is_read_only_on_a_preflight_job(tmp_path):
    """Observing the terminus evidence for a preflight job changes nothing (status/slots/candidate identical)."""
    results = _run(tmp_path)
    fx, _ev, _d, store, tenant, job = next(r for r in results
                                           if r[0].fixture_id == "g4-01-lone-positive-candidate")
    job_before = copy.deepcopy(load_job(store, tenant, job))
    cands_before = copy.deepcopy(list_review_candidates(store, tenant, job))
    terminus_evidence_report(store, tenant, job)
    assert load_job(store, tenant, job) == job_before
    assert list_review_candidates(store, tenant, job) == cands_before
