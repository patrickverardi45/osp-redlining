"""G4 GEOMETRY-vs-ENDPOINT validation — the read-only proof bed for the hardest AUTO risk.

Every fixture has both endpoints source-bound; only the geometry between them varies. A DESIGN-ONLY oracle
(mirroring the proposed geometry gate over CURRENTLY-AVAILABLE signals; never imported by placement) is run
over each. The central result: the oracle PASSES both the clean positive AND the wrong-branch fork — they are
indistinguishable from current data — so a known-negative slips through, proving the gate is NOT safely
implementable from current data without a branch-uniqueness / endpoint-to-run-coordinate signal that does not
yet exist. Nothing here promotes anything; every fixture is REVIEW/ABSTAIN today.
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
from truelinev2.harness.g4_geometry_fixtures import (
    NEGATIVE,
    POSITIVE,
    build_g4_geometry_fixtures,
    load_g4_geometry_fixtures,
)

_AT, _BY = "2026-01-01T00:00:00Z", "g4-geometry-test"
_COLD = {"corpora": [], "configured": True}

# --- DESIGN-ONLY validation oracle (a TEST artifact; never imported by placement/contract code) ----------- #
_AUTO_ELIGIBLE = {te.PRINTED_STRUCTURE_LABEL, te.PRINTED_STA_CALLOUT, te.MATCHLINE_BOUNDARY_STATION}
# Generic-lane warning substrings + caveats that signal "the selected run may not be the bore".
_REJECT_WARNING_SUBSTR = ("MULTIPLE_PLAUSIBLE_RUNS", "COMPETING_RUNS_NEAR_SCORE", "PARTIAL_SPAN_COVERAGE",
                          "PLACED_ON_FULL_SHEET_ALIGNMENT_LINE", "RUN_LENGTH_UNLIKE_BORE_SPAN",
                          "NOISY_STATION_AXIS", "SPARSE_STATION_LABELS")
_REJECT_CAVEATS = {"DRAWN_EXTENT_EXCEEDS_BORE_SPAN", "GENERIC_MULTIPLE_PLAUSIBLE_RUNS",
                   "GENERIC_PARTIAL_SPAN_COVERAGE", "GENERIC_CORRECTION_RECOMMENDED",
                   "CROSS_SHEET_CONTINUATION_REVIEW", "PARTIAL_CROSS_SHEET_REVIEW",
                   "GENERIC_PLACED_ON_ALIGNMENT_LINE_UNVERIFIED"}
# Signals the future gate needs but the CURRENT data does not expose — reported, never invented.
_MISSING_SIGNALS = ("BRANCH_PATH_UNIQUENESS_NOT_EXPOSED", "ENDPOINT_TO_RUN_COORDINATE_TIGHTNESS_NOT_EXPOSED")


def geometry_gate_oracle(ev, decision) -> dict:
    """Mirror of the PROPOSED geometry gate over only the signals available today. Returns whether the case
    would pass, the reject reasons, and the signals the gate still lacks. DESIGN-ONLY; promotes nothing."""
    reasons = []
    if not (ev.start.source_bound and ev.end.source_bound):
        reasons.append("ENDPOINT_NOT_SOURCE_BOUND")
    if ev.start.source_type not in _AUTO_ELIGIBLE or ev.end.source_type not in _AUTO_ELIGIBLE:
        reasons.append("SOURCE_TYPE_NOT_AUTO_ELIGIBLE")
    if decision.get("path") != "UPLOADED_REVIEW":
        reasons.append("NOT_PLACED_REVIEW")                  # abstained / not a placed REVIEW
    rec = (decision.get("review") or {}).get("record") or {}
    conf = rec.get("confidence") or {}
    if conf.get("band") == "LOW":
        reasons.append("LOW_CONFIDENCE")
    if conf.get("correction_recommended"):
        reasons.append("CORRECTION_RECOMMENDED")
    if any(any(sub in w for sub in _REJECT_WARNING_SUBSTR) for w in (conf.get("warnings") or [])):
        reasons.append("GEOMETRY_WARNING")
    if any(c in _REJECT_CAVEATS for c in (rec.get("caveats") or [])):
        reasons.append("GEOMETRY_CAVEAT")
    render = set(rec.get("render_sheets") or [])
    tsheets = {s for s in (ev.start.sheet, ev.end.sheet) if s is not None}
    if render and tsheets and not tsheets.issubset(render):
        reasons.append("SHEET_MISMATCH")
    return {"would_pass": not reasons, "reject_reasons": reasons, "missing_signals": list(_MISSING_SIGNALS)}


def _provision_and_decide(store, tenant, job, plan_bytes, borelog_bytes):
    create_customer_project(store, tenant, "g4 geometry", _AT)
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


def _run(tmp_path):
    root = tmp_path / "g4geo"
    build_g4_geometry_fixtures(root)
    out = []
    for fx in load_g4_geometry_fixtures(root):
        tenant, job = ("cp-%s" % fx.fixture_id)[:63], ("job-%s" % fx.fixture_id)[:63]
        store = tmp_path / fx.fixture_id
        decision = _provision_and_decide(store, tenant, job, fx.plan_path.read_bytes(),
                                         fx.borelog_path.read_bytes())
        ev = extract_termini(fx.plan_path, fx.borelog_path)
        out.append((fx, ev, decision, geometry_gate_oracle(ev, decision), store, tenant, job))
    return out


def test_all_fixtures_have_source_bound_endpoints_and_are_review_or_abstain_today(tmp_path):
    for fx, ev, decision, _o, _s, _t, _j in _run(tmp_path):
        # endpoints are source-bound by design (the geometry, not the endpoints, is what varies)
        assert ev.start.source_bound is True and ev.end.source_bound is True, fx.fixture_id
        for which, obs, exp in (("start", ev.start, fx.expected_start), ("end", ev.end, fx.expected_end)):
            assert obs.source_type == exp["source_type"], (fx.fixture_id, which)
        # no fixture is AUTO today
        assert decision["path"] == fx.expected_path, fx.fixture_id
        assert decision["path"] != "UPLOADED_AUTO"
        assert (decision.get("review") or {}).get("tier") != "AUTO"


def test_oracle_result_matches_each_fixture_expectation(tmp_path):
    for fx, _ev, _d, oracle, _s, _t, _j in _run(tmp_path):
        assert oracle["would_pass"] == fx.oracle_would_pass, (fx.fixture_id, oracle)
        if not oracle["would_pass"]:
            assert oracle["reject_reasons"], fx.fixture_id          # a rejected case names why
        # the gate always reports the signals it still lacks (never invents them)
        assert set(_MISSING_SIGNALS).issubset(set(oracle["missing_signals"]))


def test_current_data_cannot_separate_the_fork_from_the_true_positive(tmp_path):
    """THE CENTRAL RESULT: the current-data oracle passes BOTH the clean positive and the wrong-branch fork,
    so a ground-truth NEGATIVE slips through -> the future gate is NOT safely implementable from current data."""
    results = _run(tmp_path)
    passing = sorted(fx.fixture_id for fx, _e, _d, o, _s, _t, _j in results if o["would_pass"])
    assert passing == ["g4geo-01-perfect-line", "g4geo-06-wrong-branch-fork"]

    by = {fx.fixture_id: (fx, o) for fx, _e, _d, o, _s, _t, _j in results}
    # the true positive is genuinely clean
    pos_fx, pos_o = by["g4geo-01-perfect-line"]
    assert pos_fx.ground_truth == POSITIVE and pos_o["would_pass"] is True
    # the fork PASSES the current-data oracle but is a ground-truth NEGATIVE -> a FALSE POSITIVE
    fork_fx, fork_o = by["g4geo-06-wrong-branch-fork"]
    assert fork_fx.ground_truth == NEGATIVE and fork_o["would_pass"] is True

    false_positives = [fx.fixture_id for fx, _e, _d, o, _s, _t, _j in results
                       if o["would_pass"] and fx.ground_truth == NEGATIVE]
    assert false_positives == ["g4geo-06-wrong-branch-fork"]
    safe_to_implement_from_current_data = (len(false_positives) == 0)
    assert safe_to_implement_from_current_data is False        # documented conclusion of this gate


def test_each_true_negative_with_a_signal_is_correctly_rejected(tmp_path):
    """Every ground-truth NEGATIVE except the fork IS caught by a currently-available signal."""
    for fx, _ev, _d, oracle, _s, _t, _j in _run(tmp_path):
        if fx.ground_truth == NEGATIVE and fx.fixture_id != "g4geo-06-wrong-branch-fork":
            assert oracle["would_pass"] is False, fx.fixture_id
            assert oracle["reject_reasons"], fx.fixture_id


def test_observer_is_read_only_on_a_geometry_fixture(tmp_path):
    fx, _ev, _d, _o, store, tenant, job = next(
        r for r in _run(tmp_path) if r[0].fixture_id == "g4geo-01-perfect-line")
    job_before = copy.deepcopy(load_job(store, tenant, job))
    cands_before = copy.deepcopy(list_review_candidates(store, tenant, job))
    terminus_evidence_report(store, tenant, job)
    assert load_job(store, tenant, job) == job_before
    assert list_review_candidates(store, tenant, job) == cands_before
