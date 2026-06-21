"""Contract tests: the billing_summary server-computed model. Pure stdlib + tmp_path; no engine/render/
wiring. Generic ids/rules/values only.

Key proofs:
  * ONE durable server-authoritative billing record per job; totals computed server-side from injected
    VERSIONED cost rules (quantity x unit_cost), never client-supplied amounts; Decimal money, ROUND_HALF_UP.
  * Billability follows closeout — there is no "approve billing" action: FINAL requires closeout APPROVED
    AND zero billing hard blockers. Closeout not-approved/missing -> COMPUTED (finalization blocker);
    closeout BLOCKED (open engine blockers) -> billing surfaces OPEN_ENGINE_BLOCKERS as a WARNING but is
    NEVER FINAL.
  * Hard input problems (missing/untrusted/unresolvable manifest, rbl-not-ready, job out of range) -> BLOCKED.
  * Reproducible + auditable revisions: identical inputs revalidate idempotently; changed inputs/rules append
    a new revision (old superseded). No client/UI override of status survives a server recompute.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from truelinev2.contracts.customer_project import CrossProjectAccessError, create_customer_project
from truelinev2.contracts.processing_job import (
    AWAITING_REVIEW,
    CLOSEOUT_REVIEW,
    EXTRACTING,
    PLACED,
    PLACING,
    UPLOADING,
    create_job,
    load_job,
    transition,
)
from truelinev2.contracts.upload_pipeline import accept_upload
from truelinev2.contracts.extracted_row import CONFIRMED, OCR, new_extracted_row
from truelinev2.contracts.reviewed_bore_log import (
    GROUPING_CONFIRMED,
    SEPARATE_BORE,
    add_extracted_rows,
    create_reviewed_bore_log,
    define_segment_group,
    review_row_in_log,
    set_grouping_status,
)
from truelinev2.contracts.manifest_handoff import finalize_handoff, record_handoff_attempt
from truelinev2.contracts.closeout_review import (
    approve_closeout,
    create_closeout_review,
    evaluate_closeout,
)
from truelinev2.contracts.billing_summary import (
    BLOCKED,
    CLOSEOUT_NOT_APPROVED,
    CLOSEOUT_REVIEW_MISSING,
    COMPUTED,
    DRAFT,
    FINAL,
    JOB_NOT_IN_BILLING_RANGE,
    MANIFEST_NOT_RESOLVABLE,
    MISSING_ARTIFACT_BUNDLE,
    MISSING_MANIFEST,
    OPEN_ENGINE_BLOCKERS,
    REVIEWED_BORE_LOG_NOT_READY,
    UNTRUSTED_OUTPUT,
    ZERO_BILLABLE_TOTAL,
    BillingSummaryError,
    InvalidCostRuleSetError,
    UntrustedItemizationError,
    billing_summary_path,
    billing_summary_view,
    compute_billing_summary,
    create_billing_summary,
    load_billing_summary,
)

AT = "2026-06-21T00:00:00Z"
BY = "operator-1"
CP = "cp-0001"
JOB = "job-0001"
RBL = "rbl-0001"
RUN = "run-0001"
ROLE = "approver"                       # generic role tokens — never customer/person names
ROLES = ("approver", "admin")

COST_RULES = {
    "version": "rules-v1", "currency": "USD", "minor_unit_digits": 2,
    "rules": [
        {"code": "base_ft", "kind": "BASE", "unit": "ft", "unit_cost": "1.25", "label": "Base footage"},
        {"code": "exc_a", "kind": "EXCEPTION", "unit": "ft", "unit_cost": "3.00", "label": "Exception A"},
        {"code": "adj_a", "kind": "ADJUSTMENT", "unit": "ea", "unit_cost": "500.00", "label": "Adjustment A"},
    ],
}
ITEM_EXC = [{"rule_code": "exc_a", "quantity": "10", "source": "REVIEWED_INPUT", "note": "extra", "ref": "i1"}]


# --------------------------------------------------------------------------- #
# Generic pixel-only engine-output bundles with footage (closure.drawn_ft on the drawn log).
# --------------------------------------------------------------------------- #
def _log(lid, status, prov, *, drawn=False, covered=False, blocked=False, artifacts=None, closure=None):
    return {"log_id": lid, "parent_id": "b_" + lid, "entry_role": "standalone",
            "status": status, "provenance": prov, "drawn": drawn, "covered": covered,
            "blocked": blocked, "drawn_lane": "NEW_TARGETS" if drawn else None, "source_sheets": [1],
            "span": {"start_station": "0+00", "end_station": "1+00", "label": "0+00->1+00"},
            "closure": closure, "coverage": {"covered_by": "logX"} if covered else None,
            "blocker": {"category": "OWNER_LOCKED", "name": "n", "unlock_requirement": "owner lifts"}
            if blocked else None,
            "artifacts": artifacts or [],
            "evidence": [{"kind": "ACCOUNTABILITY_LEDGER", "ref": "r"}], "warnings": []}


def _drawn_artifact(root, lid):
    art_dir = root / "artifacts" / lid
    art_dir.mkdir(parents=True, exist_ok=True)
    data = b"FAKE-PNG-" + lid.encode()
    fname = "%s_s1_redline_stroke.png" % lid
    (art_dir / fname).write_bytes(data)
    return {"kind": "FINAL_REDLINE_PNG", "path": "artifacts/%s/%s" % (lid, fname),
            "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data),
            "published": True, "example_placeholder": False}


def _write_manifest(root, logs, status_counts, prov_counts, summary):
    manifest = {
        "schema_version": "1.0.0", "mock_example": False, "disclaimer": "t",
        "project_id": "proj-a", "project_name": "Project A",
        "engine": {"branch": "feat/truelinev2", "engine_head": "h", "render_commit": "rc-0",
                   "generated_from": "test"},
        "summary": summary, "status_counts": status_counts, "provenance_counts": prov_counts,
        "consumption_rules": ["consume the manifest"], "logs": logs,
    }
    (root / "redline_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return root


def _clean_bundle(root, drawn_ft=100.5):
    """Drawn (with footage) + covered, ZERO blocked logs -> closeout can be APPROVED."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    logs = [_log("logA", "DRAWN_REDLINE", "DETERMINISTIC_AUTO", drawn=True,
                 artifacts=[_drawn_artifact(root, "logA")], closure={"drawn_ft": drawn_ft}),
            _log("logC", "COVERED_BY_EXISTING_REDLINE", "COVERED_BY_EXISTING_REDLINE", covered=True)]
    status_counts = {"DRAWN_REDLINE": 1, "COVERED_BY_EXISTING_REDLINE": 1, "OWNER_LOCKED_ABSTAIN": 0,
                     "SOURCE_GAP_BLOCKED": 0, "MISSING_SOURCE_SHEET_BLOCKED": 0}
    prov_counts = {"DETERMINISTIC_AUTO": 1, "OWNER_CONFIRMED_HUMAN_ADJUSTABLE": 0,
                   "COVERED_BY_EXISTING_REDLINE": 1, "BLOCKED_OWNER_LOCKED": 0,
                   "BLOCKED_SOURCE_GAP": 0, "BLOCKED_MISSING_SOURCE": 0}
    summary = {"total_logs": 2, "drawn_count": 1, "covered_count": 1, "blocked_count": 0, "frontier": "1/1"}
    return _write_manifest(root, logs, status_counts, prov_counts, summary)


def _blocked_bundle(root, drawn_ft=100.5):
    """Drawn (with footage) + covered + ONE owner-locked blocked log -> closeout BLOCKED (engine blocker)."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    logs = [_log("logA", "DRAWN_REDLINE", "DETERMINISTIC_AUTO", drawn=True,
                 artifacts=[_drawn_artifact(root, "logA")], closure={"drawn_ft": drawn_ft}),
            _log("logC", "COVERED_BY_EXISTING_REDLINE", "COVERED_BY_EXISTING_REDLINE", covered=True),
            _log("logB", "OWNER_LOCKED_ABSTAIN", "BLOCKED_OWNER_LOCKED", blocked=True)]
    status_counts = {"DRAWN_REDLINE": 1, "COVERED_BY_EXISTING_REDLINE": 1, "OWNER_LOCKED_ABSTAIN": 1,
                     "SOURCE_GAP_BLOCKED": 0, "MISSING_SOURCE_SHEET_BLOCKED": 0}
    prov_counts = {"DETERMINISTIC_AUTO": 1, "OWNER_CONFIRMED_HUMAN_ADJUSTABLE": 0,
                   "COVERED_BY_EXISTING_REDLINE": 1, "BLOCKED_OWNER_LOCKED": 1,
                   "BLOCKED_SOURCE_GAP": 0, "BLOCKED_MISSING_SOURCE": 0}
    summary = {"total_logs": 3, "drawn_count": 1, "covered_count": 1, "blocked_count": 1, "frontier": "1/2"}
    return _write_manifest(root, logs, status_counts, prov_counts, summary)


_JOB_WALK = [UPLOADING, EXTRACTING, AWAITING_REVIEW, PLACING, PLACED, CLOSEOUT_REVIEW]


def _advance_job(tmp_path, upto):
    for s in _JOB_WALK:
        transition(tmp_path, CP, JOB, s, at=AT, by=BY, reason=None)
        if s == upto:
            return


def _spine(tmp_path, *, bundle_builder, advance_to=CLOSEOUT_REVIEW):
    create_customer_project(tmp_path, CP, "Label", AT)
    create_job(tmp_path, CP, JOB, AT, BY)
    up = accept_upload(tmp_path, CP, JOB, kind="BORE_LOG", filename="log.csv", content=b"a,b", stored_at=AT)
    create_reviewed_bore_log(tmp_path, CP, JOB, up["upload_id"], RBL, at=AT, by=BY)
    add_extracted_rows(tmp_path, CP, JOB, RBL, [new_extracted_row(
        "row-1", up["upload_id"], raw={}, normalized={}, extraction_method=OCR, at=AT, by=BY)],
        at=AT, by=BY)
    review_row_in_log(tmp_path, CP, JOB, RBL, "row-1", CONFIRMED, at=AT, by=BY)
    define_segment_group(tmp_path, CP, JOB, RBL, "grp-1", ["row-1"], SEPARATE_BORE, at=AT, by=BY)
    set_grouping_status(tmp_path, CP, JOB, RBL, "grp-1", GROUPING_CONFIRMED, at=AT, by=BY)
    record_handoff_attempt(tmp_path, CP, JOB, RBL, RUN, engine_run_status="completed", at=AT, by=BY)
    finalize_handoff(tmp_path, CP, JOB, RUN, bundle_builder(tmp_path / "engine_out"), at=AT, by=BY)
    if advance_to is not None:
        _advance_job(tmp_path, advance_to)
    return up["upload_id"]


def _closeout_approved(tmp_path):
    create_closeout_review(tmp_path, CP, JOB, at=AT, by=BY)
    evaluate_closeout(tmp_path, CP, JOB, at=AT, by=BY)
    approve_closeout(tmp_path, CP, JOB, at=AT, by=BY, actor_role=ROLE, authorized_roles=ROLES, reason="ok")


def _closeout_evaluated(tmp_path):
    create_closeout_review(tmp_path, CP, JOB, at=AT, by=BY)
    evaluate_closeout(tmp_path, CP, JOB, at=AT, by=BY)


def _view(rec):
    return billing_summary_view(rec)


def _job_path(tmp_path):
    return Path(tmp_path) / "customer_projects" / CP / "processing_jobs" / JOB / "_processing_job.json"


# --------------------------------------------------------------------------- #
# FINAL only when closeout APPROVED; deterministic money.
# --------------------------------------------------------------------------- #
def test_final_when_closeout_approved_money_half_up(tmp_path):
    _spine(tmp_path, bundle_builder=_clean_bundle)            # footage 100.5
    _closeout_approved(tmp_path)
    create_billing_summary(tmp_path, CP, JOB, at=AT, by=BY)
    rec = compute_billing_summary(tmp_path, CP, JOB, cost_rule_set=COST_RULES, at=AT, by=BY)
    assert rec["status"] == FINAL
    v = _view(rec)
    assert v["totals"]["base_total"] == "125.63"             # 100.5 * 1.25 = 125.625 -> HALF_UP 125.63
    assert v["totals"]["final_total"] == "125.63"
    assert v["is_billable"] is True
    assert rec["currency"] == "USD"


def test_itemized_exception_totals(tmp_path):
    _spine(tmp_path, bundle_builder=_clean_bundle)
    _closeout_approved(tmp_path)
    create_billing_summary(tmp_path, CP, JOB, at=AT, by=BY)
    rec = compute_billing_summary(tmp_path, CP, JOB, cost_rule_set=COST_RULES,
                                  itemized_inputs=ITEM_EXC, at=AT, by=BY)
    assert rec["status"] == FINAL
    t = _view(rec)["totals"]
    assert t["base_total"] == "125.63" and t["exception_total"] == "30.00"   # 10 * 3.00
    assert t["final_total"] == "155.63"
    kinds = {cl["kind"] for cl in rec["revisions"][-1]["charge_lines"]}
    assert kinds == {"BASE", "EXCEPTION"}


# --------------------------------------------------------------------------- #
# Billability follows closeout (the clarification): never FINAL unless closeout APPROVED.
# --------------------------------------------------------------------------- #
def test_closeout_not_approved_is_computed_not_final(tmp_path):
    _spine(tmp_path, bundle_builder=_clean_bundle)
    _closeout_evaluated(tmp_path)                            # READY, not approved
    create_billing_summary(tmp_path, CP, JOB, at=AT, by=BY)
    rec = compute_billing_summary(tmp_path, CP, JOB, cost_rule_set=COST_RULES, at=AT, by=BY)
    assert rec["status"] == COMPUTED
    assert CLOSEOUT_NOT_APPROVED in _view(rec)["finalization_blocker_codes"]
    assert _view(rec)["is_final"] is False


def test_closeout_missing_is_computed_not_final(tmp_path):
    _spine(tmp_path, bundle_builder=_clean_bundle)           # no closeout_review created
    create_billing_summary(tmp_path, CP, JOB, at=AT, by=BY)
    rec = compute_billing_summary(tmp_path, CP, JOB, cost_rule_set=COST_RULES, at=AT, by=BY)
    assert rec["status"] == COMPUTED
    assert CLOSEOUT_REVIEW_MISSING in _view(rec)["finalization_blocker_codes"]


def test_closeout_blocked_engine_blockers_never_final_warning_only(tmp_path):
    _spine(tmp_path, bundle_builder=_blocked_bundle)         # closeout will be BLOCKED (engine blocker)
    _closeout_evaluated(tmp_path)
    create_billing_summary(tmp_path, CP, JOB, at=AT, by=BY)
    rec = compute_billing_summary(tmp_path, CP, JOB, cost_rule_set=COST_RULES, at=AT, by=BY)
    assert rec["status"] == COMPUTED                         # NEVER FINAL while closeout not approved
    v = _view(rec)
    assert OPEN_ENGINE_BLOCKERS in v["warning_codes"]        # visibility only (closeout owns it as hard)
    assert OPEN_ENGINE_BLOCKERS not in v["hard_blocker_codes"]
    assert CLOSEOUT_NOT_APPROVED in v["finalization_blocker_codes"]
    assert v["is_final"] is False


# --------------------------------------------------------------------------- #
# Hard blockers (untrusted/missing/unresolvable inputs) -> BLOCKED.
# --------------------------------------------------------------------------- #
def test_missing_output_slots_block(tmp_path):
    create_customer_project(tmp_path, CP, "Label", AT)
    create_job(tmp_path, CP, JOB, AT, BY)
    _advance_job(tmp_path, CLOSEOUT_REVIEW)
    create_billing_summary(tmp_path, CP, JOB, at=AT, by=BY)
    rec = compute_billing_summary(tmp_path, CP, JOB, cost_rule_set=COST_RULES, at=AT, by=BY)
    assert rec["status"] == BLOCKED
    codes = _view(rec)["hard_blocker_codes"]
    assert MISSING_MANIFEST in codes and MISSING_ARTIFACT_BUNDLE in codes


def test_untrusted_output_blocks(tmp_path):
    _spine(tmp_path, bundle_builder=_clean_bundle)
    jpath = _job_path(tmp_path)
    job = json.loads(jpath.read_text())
    job["slots"]["redline_manifest"]["ref"]["validation_status"] = "UNVALIDATED"
    jpath.write_text(json.dumps(job, indent=2), encoding="utf-8")
    create_billing_summary(tmp_path, CP, JOB, at=AT, by=BY)
    rec = compute_billing_summary(tmp_path, CP, JOB, cost_rule_set=COST_RULES, at=AT, by=BY)
    assert rec["status"] == BLOCKED and UNTRUSTED_OUTPUT in _view(rec)["hard_blocker_codes"]


def test_manifest_sha_drift_blocks(tmp_path):
    _spine(tmp_path, bundle_builder=_clean_bundle)
    bid = load_job(tmp_path, CP, JOB)["slots"]["artifact_bundle"]["ref"]["bundle_id"]
    stored = (Path(tmp_path) / "customer_projects" / CP / "processing_jobs" / JOB
              / "bundle_store" / "bundles" / bid / "redline_manifest.json")
    stored.write_text(stored.read_text() + "\n ", encoding="utf-8")
    create_billing_summary(tmp_path, CP, JOB, at=AT, by=BY)
    rec = compute_billing_summary(tmp_path, CP, JOB, cost_rule_set=COST_RULES, at=AT, by=BY)
    assert rec["status"] == BLOCKED and MANIFEST_NOT_RESOLVABLE in _view(rec)["hard_blocker_codes"]


def test_job_not_in_billing_range_blocks(tmp_path):
    _spine(tmp_path, bundle_builder=_clean_bundle, advance_to=None)   # job stays CREATED
    create_billing_summary(tmp_path, CP, JOB, at=AT, by=BY)
    rec = compute_billing_summary(tmp_path, CP, JOB, cost_rule_set=COST_RULES, at=AT, by=BY)
    assert rec["status"] == BLOCKED and JOB_NOT_IN_BILLING_RANGE in _view(rec)["hard_blocker_codes"]


def test_reviewed_bore_log_edited_after_handoff_blocks(tmp_path):
    up_id = _spine(tmp_path, bundle_builder=_clean_bundle)
    add_extracted_rows(tmp_path, CP, JOB, RBL, [new_extracted_row(
        "row-2", up_id, raw={}, normalized={}, extraction_method=OCR, at=AT, by=BY)], at=AT, by=BY)
    create_billing_summary(tmp_path, CP, JOB, at=AT, by=BY)
    rec = compute_billing_summary(tmp_path, CP, JOB, cost_rule_set=COST_RULES, at=AT, by=BY)
    assert rec["status"] == BLOCKED and REVIEWED_BORE_LOG_NOT_READY in _view(rec)["hard_blocker_codes"]


# --------------------------------------------------------------------------- #
# Caller/config errors raise (no baked rates; raw never becomes truth).
# --------------------------------------------------------------------------- #
def test_invalid_cost_rule_set_raises(tmp_path):
    _spine(tmp_path, bundle_builder=_clean_bundle)
    _closeout_approved(tmp_path)
    create_billing_summary(tmp_path, CP, JOB, at=AT, by=BY)
    with pytest.raises(InvalidCostRuleSetError):
        compute_billing_summary(tmp_path, CP, JOB, cost_rule_set={"currency": "USD", "rules": []}, at=AT, by=BY)
    two_base = {"version": "v", "currency": "USD", "rules": [
        {"code": "b1", "kind": "BASE", "unit_cost": "1"}, {"code": "b2", "kind": "BASE", "unit_cost": "2"}]}
    with pytest.raises(InvalidCostRuleSetError):
        compute_billing_summary(tmp_path, CP, JOB, cost_rule_set=two_base, at=AT, by=BY)


def test_untrusted_itemization_raises(tmp_path):
    _spine(tmp_path, bundle_builder=_clean_bundle)
    _closeout_approved(tmp_path)
    create_billing_summary(tmp_path, CP, JOB, at=AT, by=BY)
    raw_item = [{"rule_code": "exc_a", "quantity": "5", "source": "RAW_UPLOAD", "ref": "x"}]
    with pytest.raises(UntrustedItemizationError):
        compute_billing_summary(tmp_path, CP, JOB, cost_rule_set=COST_RULES,
                                itemized_inputs=raw_item, at=AT, by=BY)


def test_itemized_referencing_base_rule_raises(tmp_path):
    _spine(tmp_path, bundle_builder=_clean_bundle)
    _closeout_approved(tmp_path)
    create_billing_summary(tmp_path, CP, JOB, at=AT, by=BY)
    bad = [{"rule_code": "base_ft", "quantity": "5", "source": "REVIEWED_INPUT", "ref": "x"}]
    with pytest.raises(InvalidCostRuleSetError):
        compute_billing_summary(tmp_path, CP, JOB, cost_rule_set=COST_RULES, itemized_inputs=bad, at=AT, by=BY)


# --------------------------------------------------------------------------- #
# Reproducibility, regeneration, invalidation, no override.
# --------------------------------------------------------------------------- #
def test_identical_recompute_is_idempotent_revalidate(tmp_path):
    _spine(tmp_path, bundle_builder=_clean_bundle)
    _closeout_approved(tmp_path)
    create_billing_summary(tmp_path, CP, JOB, at=AT, by=BY)
    r1 = compute_billing_summary(tmp_path, CP, JOB, cost_rule_set=COST_RULES, at=AT, by=BY)
    h1 = r1["revisions"][-1]["inputs_hash"]
    r2 = compute_billing_summary(tmp_path, CP, JOB, cost_rule_set=COST_RULES, at=AT, by=BY)
    assert len(r2["revisions"]) == 1                          # no new revision for identical inputs
    assert r2["revisions"][-1]["inputs_hash"] == h1
    assert r2["audit"][-1]["action"] == "revalidated"


def test_regeneration_appends_revision(tmp_path):
    _spine(tmp_path, bundle_builder=_clean_bundle)
    _closeout_approved(tmp_path)
    create_billing_summary(tmp_path, CP, JOB, at=AT, by=BY)
    compute_billing_summary(tmp_path, CP, JOB, cost_rule_set=COST_RULES, at=AT, by=BY)
    rules_v2 = dict(COST_RULES, version="rules-v2")           # changed rule version -> new revision
    rec = compute_billing_summary(tmp_path, CP, JOB, cost_rule_set=rules_v2, at=AT, by=BY)
    assert len(rec["revisions"]) == 2
    assert rec["current_revision_id"] == "rev-2"
    assert rec["revisions"][0]["superseded_at"] is not None   # prior retained + superseded
    assert rec["revisions"][1]["superseded_at"] is None


def test_final_invalidated_when_inputs_break(tmp_path):
    _spine(tmp_path, bundle_builder=_clean_bundle)
    _closeout_approved(tmp_path)
    create_billing_summary(tmp_path, CP, JOB, at=AT, by=BY)
    assert compute_billing_summary(tmp_path, CP, JOB, cost_rule_set=COST_RULES, at=AT, by=BY)["status"] == FINAL
    jpath = _job_path(tmp_path)                               # break a trusted output slot post-FINAL
    job = json.loads(jpath.read_text())
    job["slots"]["redline_manifest"]["ref"]["validation_status"] = "UNVALIDATED"
    jpath.write_text(json.dumps(job, indent=2), encoding="utf-8")
    rec = compute_billing_summary(tmp_path, CP, JOB, cost_rule_set=COST_RULES, at=AT, by=BY)
    assert rec["status"] == BLOCKED and UNTRUSTED_OUTPUT in _view(rec)["hard_blocker_codes"]


def test_no_status_override_survives_recompute(tmp_path):
    _spine(tmp_path, bundle_builder=_clean_bundle)
    _closeout_evaluated(tmp_path)                            # READY, not approved -> COMPUTED
    create_billing_summary(tmp_path, CP, JOB, at=AT, by=BY)
    compute_billing_summary(tmp_path, CP, JOB, cost_rule_set=COST_RULES, at=AT, by=BY)
    path = billing_summary_path(tmp_path, CP, JOB)           # tamper status to FINAL on disk
    rec = json.loads(path.read_text())
    rec["status"] = FINAL
    path.write_text(json.dumps(rec, indent=2), encoding="utf-8")
    rec = compute_billing_summary(tmp_path, CP, JOB, cost_rule_set=COST_RULES, at=AT, by=BY)
    assert rec["status"] == COMPUTED                         # server re-derives; client override discarded


# --------------------------------------------------------------------------- #
# Durability, one-per-job, isolation, zero total, pure view.
# --------------------------------------------------------------------------- #
def test_durable_across_reload(tmp_path):
    _spine(tmp_path, bundle_builder=_clean_bundle)
    _closeout_approved(tmp_path)
    create_billing_summary(tmp_path, CP, JOB, at=AT, by=BY)
    compute_billing_summary(tmp_path, CP, JOB, cost_rule_set=COST_RULES, at=AT, by=BY)
    assert load_billing_summary(tmp_path, CP, JOB)["status"] == FINAL   # fresh read == "restart"


def test_one_billing_summary_per_job(tmp_path):
    _spine(tmp_path, bundle_builder=_clean_bundle)
    create_billing_summary(tmp_path, CP, JOB, at=AT, by=BY)
    with pytest.raises(BillingSummaryError):
        create_billing_summary(tmp_path, CP, JOB, at=AT, by=BY)


def test_cross_project_access_denied(tmp_path):
    _spine(tmp_path, bundle_builder=_clean_bundle)
    create_billing_summary(tmp_path, CP, JOB, at=AT, by=BY)
    path = billing_summary_path(tmp_path, CP, JOB)
    rec = json.loads(path.read_text())
    rec["customer_project_id"] = "cp-9999"
    path.write_text(json.dumps(rec, indent=2), encoding="utf-8")
    with pytest.raises(CrossProjectAccessError):
        load_billing_summary(tmp_path, CP, JOB)


def test_zero_footage_warns_but_can_be_final(tmp_path):
    _spine(tmp_path, bundle_builder=lambda r: _clean_bundle(r, drawn_ft=0))
    _closeout_approved(tmp_path)
    create_billing_summary(tmp_path, CP, JOB, at=AT, by=BY)
    rec = compute_billing_summary(tmp_path, CP, JOB, cost_rule_set=COST_RULES, at=AT, by=BY)
    assert rec["status"] == FINAL
    assert _view(rec)["totals"]["final_total"] == "0.00"
    assert ZERO_BILLABLE_TOTAL in _view(rec)["warning_codes"]


def test_create_is_draft_before_compute(tmp_path):
    _spine(tmp_path, bundle_builder=_clean_bundle)
    rec = create_billing_summary(tmp_path, CP, JOB, at=AT, by=BY)
    assert rec["status"] == DRAFT and rec["current_revision_id"] is None
    assert _view(rec)["final_total"] is None


def test_billing_summary_view_is_pure(tmp_path):
    _spine(tmp_path, bundle_builder=_clean_bundle)
    _closeout_approved(tmp_path)
    create_billing_summary(tmp_path, CP, JOB, at=AT, by=BY)
    rec = compute_billing_summary(tmp_path, CP, JOB, cost_rule_set=COST_RULES,
                                  itemized_inputs=ITEM_EXC, at=AT, by=BY)
    v1 = _view(rec)
    v2 = _view(rec)
    assert v1 == v2                                          # deterministic, no side effects
    assert v1["is_billable"] is True and v1["revision_count"] == 1
    assert rec["status"] == FINAL                            # record unchanged by the view
