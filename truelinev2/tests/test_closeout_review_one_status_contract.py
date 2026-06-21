"""Contract tests: the closeout_review one-status model. Pure stdlib + tmp_path; no engine/render/wiring.
Generic ids/roles/values only.

Key proofs:
  * ONE authoritative, durable, server-evaluated status per job (survives reload; one record per job).
  * A closeout is BLOCKED while ANY hard blocker is open — it can never read "approved" with open blockers.
  * Decision B: KMZ export blocked on a pixel-only manifest is a WARNING (PDF-first closeout), while OPEN
    engine/redline blockers (owner-locked abstains etc.) are HARD blockers.
  * Freshness (contract §6): a reviewed_bore_log edited AFTER handoff, or an output slot broken after
    approval, is caught on re-evaluation and invalidates approval.
  * Privileged transitions are permission-gated + audited; export_package is never touched.
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
from truelinev2.contracts.kmz_export import BLOCKED as KMZ_BLOCKED
from truelinev2.contracts.closeout_review import (
    APPROVED,
    BLOCKED,
    CLOSED,
    JOB_NOT_IN_CLOSEOUT_RANGE,
    KMZ_EXPORT_BLOCKED,
    LOCKED,
    MANIFEST_NOT_RESOLVABLE,
    MISSING_ARTIFACT_BUNDLE,
    MISSING_MANIFEST,
    OPEN,
    OPEN_ENGINE_BLOCKERS,
    READY_FOR_APPROVAL,
    REJECTED,
    REVIEWED_BORE_LOG_NOT_READY,
    UNRESOLVED_REVIEW_ITEMS,
    UNTRUSTED_OUTPUT,
    CloseoutPermissionError,
    CloseoutReviewError,
    CloseoutStateError,
    approve_closeout,
    close_closeout,
    closeout_review_path,
    closeout_summary,
    create_closeout_review,
    evaluate_closeout,
    load_closeout_review,
    lock_closeout,
    reject_closeout,
    reopen_closeout,
)

AT = "2026-06-21T00:00:00Z"
BY = "operator-1"
CP = "cp-0001"
JOB = "job-0001"
RBL = "rbl-0001"
RUN = "run-0001"
ROLE = "approver"                       # generic role tokens — never customer/person names
ROLES = ("approver", "admin")
BAD_ROLE = "viewer"


# --------------------------------------------------------------------------- #
# Generic pixel-only engine-output bundles (the real shape: stations/sheets/PNG, NO geometry).
# --------------------------------------------------------------------------- #
def _log(lid, status, prov, *, drawn=False, covered=False, blocked=False, artifacts=None):
    return {"log_id": lid, "parent_id": "b_" + lid, "entry_role": "standalone",
            "status": status, "provenance": prov, "drawn": drawn, "covered": covered,
            "blocked": blocked, "drawn_lane": "NEW_TARGETS" if drawn else None, "source_sheets": [1],
            "span": {"start_station": "0+00", "end_station": "1+00", "label": "0+00->1+00"},
            "closure": None, "coverage": {"covered_by": "logX"} if covered else None,
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


def _clean_bundle(root):
    """Drawn + covered, ZERO blocked logs -> reaches READY_FOR_APPROVAL."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    logs = [_log("logA", "DRAWN_REDLINE", "DETERMINISTIC_AUTO", drawn=True,
                 artifacts=[_drawn_artifact(root, "logA")]),
            _log("logC", "COVERED_BY_EXISTING_REDLINE", "COVERED_BY_EXISTING_REDLINE", covered=True)]
    status_counts = {"DRAWN_REDLINE": 1, "COVERED_BY_EXISTING_REDLINE": 1, "OWNER_LOCKED_ABSTAIN": 0,
                     "SOURCE_GAP_BLOCKED": 0, "MISSING_SOURCE_SHEET_BLOCKED": 0}
    prov_counts = {"DETERMINISTIC_AUTO": 1, "OWNER_CONFIRMED_HUMAN_ADJUSTABLE": 0,
                   "COVERED_BY_EXISTING_REDLINE": 1, "BLOCKED_OWNER_LOCKED": 0,
                   "BLOCKED_SOURCE_GAP": 0, "BLOCKED_MISSING_SOURCE": 0}
    summary = {"total_logs": 2, "drawn_count": 1, "covered_count": 1, "blocked_count": 0, "frontier": "1/1"}
    return _write_manifest(root, logs, status_counts, prov_counts, summary)


def _blocked_bundle(root):
    """Drawn + covered + ONE owner-locked blocked log -> OPEN_ENGINE_BLOCKERS (hard)."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    logs = [_log("logA", "DRAWN_REDLINE", "DETERMINISTIC_AUTO", drawn=True,
                 artifacts=[_drawn_artifact(root, "logA")]),
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


def _spine(tmp_path, *, bundle_builder, advance_to=CLOSEOUT_REVIEW, extra_uploads=()):
    """Full core spine -> a job with VALIDATED redline_manifest + artifact_bundle slots, advanced into the
    closeout range. Returns the BORE_LOG upload_id."""
    create_customer_project(tmp_path, CP, "Label", AT)
    create_job(tmp_path, CP, JOB, AT, BY)
    up = accept_upload(tmp_path, CP, JOB, kind="BORE_LOG", filename="log.csv", content=b"a,b", stored_at=AT)
    for kind, filename, content in extra_uploads:
        accept_upload(tmp_path, CP, JOB, kind=kind, filename=filename, content=content, stored_at=AT)
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


def _hard(rec):
    return {b["code"] for b in rec["gate"]["hard_blockers"]}


def _warn(rec):
    return {w["code"] for w in rec["gate"]["warnings"]}


def _job_path(tmp_path):
    return Path(tmp_path) / "customer_projects" / CP / "processing_jobs" / JOB / "_processing_job.json"


# --------------------------------------------------------------------------- #
# Happy path + Decision B (KMZ warning vs OPEN_ENGINE_BLOCKERS hard).
# --------------------------------------------------------------------------- #
def test_clean_spine_evaluates_ready(tmp_path):
    _spine(tmp_path, bundle_builder=_clean_bundle)
    create_closeout_review(tmp_path, CP, JOB, at=AT, by=BY)
    rec = evaluate_closeout(tmp_path, CP, JOB, at=AT, by=BY)
    assert rec["status"] == READY_FOR_APPROVAL
    assert _hard(rec) == set()


def test_kmz_blocked_is_warning_not_hard_blocker(tmp_path):
    _spine(tmp_path, bundle_builder=_clean_bundle)
    create_closeout_review(tmp_path, CP, JOB, at=AT, by=BY)
    rec = evaluate_closeout(tmp_path, CP, JOB, at=AT, by=BY)
    assert rec["status"] == READY_FOR_APPROVAL
    assert KMZ_EXPORT_BLOCKED in _warn(rec)
    assert KMZ_EXPORT_BLOCKED not in _hard(rec)
    assert rec["gate"]["kmz_export_status"] == KMZ_BLOCKED


def test_open_engine_blockers_is_hard_blocker(tmp_path):
    _spine(tmp_path, bundle_builder=_blocked_bundle)
    create_closeout_review(tmp_path, CP, JOB, at=AT, by=BY)
    rec = evaluate_closeout(tmp_path, CP, JOB, at=AT, by=BY)
    assert rec["status"] == BLOCKED
    assert OPEN_ENGINE_BLOCKERS in _hard(rec)


# --------------------------------------------------------------------------- #
# Hard blockers: missing / untrusted / unresolvable outputs; out-of-range job.
# --------------------------------------------------------------------------- #
def test_missing_output_slots_block(tmp_path):
    create_customer_project(tmp_path, CP, "Label", AT)
    create_job(tmp_path, CP, JOB, AT, BY)
    _advance_job(tmp_path, CLOSEOUT_REVIEW)
    create_closeout_review(tmp_path, CP, JOB, at=AT, by=BY)
    rec = evaluate_closeout(tmp_path, CP, JOB, at=AT, by=BY)
    assert rec["status"] == BLOCKED
    assert MISSING_MANIFEST in _hard(rec) and MISSING_ARTIFACT_BUNDLE in _hard(rec)


def test_untrusted_output_blocks(tmp_path):
    _spine(tmp_path, bundle_builder=_clean_bundle)
    jpath = _job_path(tmp_path)
    job = json.loads(jpath.read_text())
    job["slots"]["redline_manifest"]["ref"]["validation_status"] = "UNVALIDATED"
    jpath.write_text(json.dumps(job, indent=2), encoding="utf-8")
    create_closeout_review(tmp_path, CP, JOB, at=AT, by=BY)
    rec = evaluate_closeout(tmp_path, CP, JOB, at=AT, by=BY)
    assert rec["status"] == BLOCKED and UNTRUSTED_OUTPUT in _hard(rec)


def test_manifest_sha_drift_blocks(tmp_path):
    _spine(tmp_path, bundle_builder=_clean_bundle)
    bid = load_job(tmp_path, CP, JOB)["slots"]["artifact_bundle"]["ref"]["bundle_id"]
    stored = (Path(tmp_path) / "customer_projects" / CP / "processing_jobs" / JOB
              / "bundle_store" / "bundles" / bid / "redline_manifest.json")
    stored.write_text(stored.read_text() + "\n ", encoding="utf-8")     # change bytes -> sha drift
    create_closeout_review(tmp_path, CP, JOB, at=AT, by=BY)
    rec = evaluate_closeout(tmp_path, CP, JOB, at=AT, by=BY)
    assert rec["status"] == BLOCKED and MANIFEST_NOT_RESOLVABLE in _hard(rec)


def test_job_not_in_closeout_range_blocks(tmp_path):
    _spine(tmp_path, bundle_builder=_clean_bundle, advance_to=None)   # job stays CREATED
    create_closeout_review(tmp_path, CP, JOB, at=AT, by=BY)
    rec = evaluate_closeout(tmp_path, CP, JOB, at=AT, by=BY)
    assert rec["status"] == BLOCKED and JOB_NOT_IN_CLOSEOUT_RANGE in _hard(rec)


# --------------------------------------------------------------------------- #
# Freshness (§6): a reviewed_bore_log edited AFTER handoff is caught.
# --------------------------------------------------------------------------- #
def test_reviewed_bore_log_edited_after_handoff_blocks(tmp_path):
    up_id = _spine(tmp_path, bundle_builder=_clean_bundle)
    add_extracted_rows(tmp_path, CP, JOB, RBL, [new_extracted_row(   # new UNREVIEWED row
        "row-2", up_id, raw={}, normalized={}, extraction_method=OCR, at=AT, by=BY)], at=AT, by=BY)
    create_closeout_review(tmp_path, CP, JOB, at=AT, by=BY)
    rec = evaluate_closeout(tmp_path, CP, JOB, at=AT, by=BY)
    assert rec["status"] == BLOCKED
    assert REVIEWED_BORE_LOG_NOT_READY in _hard(rec)
    assert UNRESOLVED_REVIEW_ITEMS in _hard(rec)


# --------------------------------------------------------------------------- #
# Approval / lock: gate-enforced + permission-gated + audited.
# --------------------------------------------------------------------------- #
def test_approve_refused_while_hard_blockers(tmp_path):
    create_customer_project(tmp_path, CP, "Label", AT)
    create_job(tmp_path, CP, JOB, AT, BY)
    _advance_job(tmp_path, CLOSEOUT_REVIEW)                           # in range but no manifest
    create_closeout_review(tmp_path, CP, JOB, at=AT, by=BY)
    evaluate_closeout(tmp_path, CP, JOB, at=AT, by=BY)
    with pytest.raises(CloseoutStateError):
        approve_closeout(tmp_path, CP, JOB, at=AT, by=BY, actor_role=ROLE, authorized_roles=ROLES)
    assert load_closeout_review(tmp_path, CP, JOB)["status"] == BLOCKED


def test_lock_and_approve_permission_gated(tmp_path):
    _spine(tmp_path, bundle_builder=_clean_bundle)
    create_closeout_review(tmp_path, CP, JOB, at=AT, by=BY)
    evaluate_closeout(tmp_path, CP, JOB, at=AT, by=BY)
    with pytest.raises(CloseoutPermissionError):
        lock_closeout(tmp_path, CP, JOB, at=AT, by=BY, actor_role=BAD_ROLE, authorized_roles=ROLES)
    rec = lock_closeout(tmp_path, CP, JOB, at=AT, by=BY, actor_role=ROLE, authorized_roles=ROLES)
    assert rec["status"] == LOCKED
    with pytest.raises(CloseoutPermissionError):
        approve_closeout(tmp_path, CP, JOB, at=AT, by=BY, actor_role=BAD_ROLE, authorized_roles=ROLES)
    rec = approve_closeout(tmp_path, CP, JOB, at=AT, by=BY, actor_role=ROLE, authorized_roles=ROLES,
                           reason="reviewed")
    assert rec["status"] == APPROVED and rec["decision"]["kind"] == APPROVED


def test_approval_invalidated_when_inputs_break(tmp_path):
    _spine(tmp_path, bundle_builder=_clean_bundle)
    create_closeout_review(tmp_path, CP, JOB, at=AT, by=BY)
    evaluate_closeout(tmp_path, CP, JOB, at=AT, by=BY)
    approve_closeout(tmp_path, CP, JOB, at=AT, by=BY, actor_role=ROLE, authorized_roles=ROLES)
    jpath = _job_path(tmp_path)                                       # break an output slot post-approval
    job = json.loads(jpath.read_text())
    job["slots"]["redline_manifest"]["ref"]["validation_status"] = "UNVALIDATED"
    jpath.write_text(json.dumps(job, indent=2), encoding="utf-8")
    rec = evaluate_closeout(tmp_path, CP, JOB, at=AT, by=BY)
    assert rec["status"] == BLOCKED and UNTRUSTED_OUTPUT in _hard(rec)
    last = rec["audit"][-1]
    assert last["from"] == APPROVED and last["to"] == BLOCKED and "invalidated" in last["reason"]


# --------------------------------------------------------------------------- #
# Reject / reopen / close / durability / isolation / one-per-job.
# --------------------------------------------------------------------------- #
def test_reject_requires_reason_then_reopen(tmp_path):
    _spine(tmp_path, bundle_builder=_clean_bundle)
    create_closeout_review(tmp_path, CP, JOB, at=AT, by=BY)
    evaluate_closeout(tmp_path, CP, JOB, at=AT, by=BY)
    with pytest.raises(CloseoutReviewError):
        reject_closeout(tmp_path, CP, JOB, at=AT, by=BY, reason="")
    rec = reject_closeout(tmp_path, CP, JOB, at=AT, by=BY, reason="needs field evidence")
    assert rec["status"] == REJECTED and rec["decision"]["kind"] == REJECTED
    with pytest.raises(CloseoutReviewError):
        reopen_closeout(tmp_path, CP, JOB, at=AT, by=BY, actor_role=ROLE, authorized_roles=ROLES, reason="")
    rec = reopen_closeout(tmp_path, CP, JOB, at=AT, by=BY, actor_role=ROLE, authorized_roles=ROLES,
                          reason="resubmitted")
    assert rec["status"] == OPEN and rec["decision"] is None
    rec = evaluate_closeout(tmp_path, CP, JOB, at=AT, by=BY)
    assert rec["status"] == READY_FOR_APPROVAL


def test_lock_state_durable_across_reload(tmp_path):
    _spine(tmp_path, bundle_builder=_clean_bundle)
    create_closeout_review(tmp_path, CP, JOB, at=AT, by=BY)
    evaluate_closeout(tmp_path, CP, JOB, at=AT, by=BY)
    lock_closeout(tmp_path, CP, JOB, at=AT, by=BY, actor_role=ROLE, authorized_roles=ROLES)
    assert load_closeout_review(tmp_path, CP, JOB)["status"] == LOCKED   # fresh read == "restart"


def test_one_closeout_review_per_job(tmp_path):
    _spine(tmp_path, bundle_builder=_clean_bundle)
    create_closeout_review(tmp_path, CP, JOB, at=AT, by=BY)
    with pytest.raises(CloseoutReviewError):
        create_closeout_review(tmp_path, CP, JOB, at=AT, by=BY)


def test_cross_project_access_denied(tmp_path):
    _spine(tmp_path, bundle_builder=_clean_bundle)
    create_closeout_review(tmp_path, CP, JOB, at=AT, by=BY)
    path = closeout_review_path(tmp_path, CP, JOB)
    rec = json.loads(path.read_text())
    rec["customer_project_id"] = "cp-9999"                            # tamper internal scope
    path.write_text(json.dumps(rec, indent=2), encoding="utf-8")
    with pytest.raises(CrossProjectAccessError):
        load_closeout_review(tmp_path, CP, JOB)


def test_export_package_never_touched_through_full_lifecycle(tmp_path):
    _spine(tmp_path, bundle_builder=_clean_bundle)
    create_closeout_review(tmp_path, CP, JOB, at=AT, by=BY)
    evaluate_closeout(tmp_path, CP, JOB, at=AT, by=BY)
    lock_closeout(tmp_path, CP, JOB, at=AT, by=BY, actor_role=ROLE, authorized_roles=ROLES)
    approve_closeout(tmp_path, CP, JOB, at=AT, by=BY, actor_role=ROLE, authorized_roles=ROLES)
    rec = close_closeout(tmp_path, CP, JOB, at=AT, by=BY, actor_role=ROLE, authorized_roles=ROLES)
    assert rec["status"] == CLOSED
    assert load_job(tmp_path, CP, JOB)["slots"]["export_package"] is None


def test_evaluate_on_closed_raises(tmp_path):
    _spine(tmp_path, bundle_builder=_clean_bundle)
    create_closeout_review(tmp_path, CP, JOB, at=AT, by=BY)
    evaluate_closeout(tmp_path, CP, JOB, at=AT, by=BY)
    lock_closeout(tmp_path, CP, JOB, at=AT, by=BY, actor_role=ROLE, authorized_roles=ROLES)
    approve_closeout(tmp_path, CP, JOB, at=AT, by=BY, actor_role=ROLE, authorized_roles=ROLES)
    close_closeout(tmp_path, CP, JOB, at=AT, by=BY, actor_role=ROLE, authorized_roles=ROLES)
    with pytest.raises(CloseoutStateError):
        evaluate_closeout(tmp_path, CP, JOB, at=AT, by=BY)


def test_uploaded_gis_route_never_referenced(tmp_path):
    _spine(tmp_path, bundle_builder=_clean_bundle,
           extra_uploads=[("GIS_ROUTE", "route.kmz", b"PK\x03\x04 fake-kmz")])
    create_closeout_review(tmp_path, CP, JOB, at=AT, by=BY)
    rec = evaluate_closeout(tmp_path, CP, JOB, at=AT, by=BY)
    assert rec["status"] == READY_FOR_APPROVAL
    assert "route.kmz" not in json.dumps(rec)                         # uploads are never closeout truth


# --------------------------------------------------------------------------- #
# Audit + pure summary view.
# --------------------------------------------------------------------------- #
def test_all_transitions_are_audited(tmp_path):
    _spine(tmp_path, bundle_builder=_clean_bundle)
    create_closeout_review(tmp_path, CP, JOB, at=AT, by=BY)
    evaluate_closeout(tmp_path, CP, JOB, at=AT, by=BY)
    lock_closeout(tmp_path, CP, JOB, at=AT, by=BY, actor_role=ROLE, authorized_roles=ROLES)
    rec = approve_closeout(tmp_path, CP, JOB, at=AT, by=BY, actor_role=ROLE, authorized_roles=ROLES)
    actions = [a["action"] for a in rec["audit"]]
    assert "closeout_review_created" in actions
    assert any(a["action"] == "locked" and a["from"] == READY_FOR_APPROVAL and a["to"] == LOCKED
               for a in rec["audit"])
    assert any(a["action"] == "approved" and a["to"] == APPROVED for a in rec["audit"])
    for a in rec["audit"]:
        assert {"action", "from", "to", "at", "by", "reason"} <= set(a.keys())


def test_closeout_summary_is_pure(tmp_path):
    _spine(tmp_path, bundle_builder=_clean_bundle)
    create_closeout_review(tmp_path, CP, JOB, at=AT, by=BY)
    rec = evaluate_closeout(tmp_path, CP, JOB, at=AT, by=BY)
    s1 = closeout_summary(rec)
    s2 = closeout_summary(rec)
    assert s1 == s2                                                   # deterministic, no side effects
    assert s1["status"] == READY_FOR_APPROVAL
    assert s1["is_approvable"] is True and s1["hard_blocker_count"] == 0
    assert KMZ_EXPORT_BLOCKED in s1["warning_codes"]
    assert rec["status"] == READY_FOR_APPROVAL                        # record unchanged by the view
