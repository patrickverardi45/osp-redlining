"""Permanent v2 product foundation — the closeout_review one-status model (contract-only).

ONE durable, server-authoritative closeout status per processing_job. The v1 monolith's core defect was
several DISAGREEING readiness signals — a client React `billingApprovalStatus` that was never persisted, a
client-computed checklist, and an in-memory lock the lock endpoint never validated against (see
docs/product_v1_workflow_salvage_audit.md items 4c/4d/5a). v2 fixes this with a single persisted
`closeout_review.status`; ALL readiness UI must render THIS value — no panel-local readiness, and no client
flag may override it (contract docs/product_v2_permanent_pipeline_contract.md §5).

The gate is evaluated SERVER-SIDE from TRUSTED PRODUCT CONTRACTS ONLY and the result is STORED (a snapshot
on the record), not recomputed per render. Closeout is BLOCKED while any HARD blocker remains open — a
closeout must never read "approved" while known engine/redline blockers are still open. If a deployment
ever needs approve-with-exceptions, that is its OWN explicit, audited exception/waiver contract; it is NOT
in this lane.

Gate inputs (trusted contracts only — never client state, never job["uploads"], never v1, never
export_package): the processing_job lifecycle + output slots; the durably stored, sha256-verified
redline_manifest; the reviewed_bore_log resolved via the manifest handoff chain (freshness — catches a row
re-reviewed after handoff); and the read-only kmz_export geometry-safety evaluation.

HARD blockers (force BLOCKED; forbid lock/approve): JOB_NOT_IN_CLOSEOUT_RANGE, MISSING_MANIFEST,
MISSING_ARTIFACT_BUNDLE, UNTRUSTED_OUTPUT, MANIFEST_NOT_RESOLVABLE, OPEN_ENGINE_BLOCKERS,
REVIEWED_BORE_LOG_NOT_READY, UNRESOLVED_REVIEW_ITEMS, SOURCE_CONFLICT.
WARNINGS (recorded; never block): KMZ_EXPORT_BLOCKED (current real manifests are pixel-only — PDF-first
closeout does not require geospatial export), REVIEWED_BORE_LOG_NOT_RESOLVABLE.
An invalid status transition is realized as the CloseoutStateError exception (the STATUS_TRANSITION_INVALID
condition), not a gate blocker.

Privileged transitions (lock/unlock/approve/reopen/close) are permission-gated: the caller's verified
`actor_role` must be a member of the deployment's `authorized_roles` — BOTH injected at runtime (opaque
data; never baked into code, no defaults), because the external auth provider owns the real role check.
Every transition is audited (action/from/to/at/by/reason); the record is durable JSON under the job scope,
so lock/approval state survives a restart (never in-memory). Contract-only: no engine execution, renderer,
web/backend, AI/OCR, KMZ/KML generation, billing, export_package producer, or deploy.
"""
from __future__ import annotations

import json
from pathlib import Path

from truelinev2.contracts.customer_project import assert_same_project, validate_customer_project_id
from truelinev2.contracts.processing_job import (
    CLOSED as JOB_CLOSED,
    CLOSEOUT_REVIEW as JOB_CLOSEOUT_REVIEW,
    PLACED as JOB_PLACED,
    job_dir,
    load_job,
    validate_job_id,
)
from truelinev2.contracts.published_bundle import MANIFEST_FILENAME, load_manifest, sha256_file
from truelinev2.contracts.published_bundle_store import BUNDLES_SUBDIR
from truelinev2.contracts.manifest_handoff import (
    BUNDLE_STORE_SUBDIR,
    VALIDATION_VALIDATED,
    ManifestHandoffError,
    load_handoff,
)
from truelinev2.contracts.reviewed_bore_log import (
    SOURCE_CONFLICT as RBL_SOURCE_CONFLICT,
    ReviewedBoreLogError,
    load_reviewed_bore_log,
    review_queue,
)
from truelinev2.contracts import kmz_export

CLOSEOUT_REVIEW_RECORD_FORMAT = "trueline-closeout-review-1"
CLOSEOUT_REVIEW_FILENAME = "_closeout_review.json"   # ONE record per job (singleton enforces one status)

# The ONE authoritative status set (contract §5, deduped with the lane's reject/close lifecycle).
OPEN = "OPEN"
BLOCKED = "BLOCKED"
READY_FOR_APPROVAL = "READY_FOR_APPROVAL"
LOCKED = "LOCKED"
APPROVED = "APPROVED"
REJECTED = "REJECTED"
CLOSED = "CLOSED"
CLOSEOUT_STATUSES = (OPEN, BLOCKED, READY_FOR_APPROVAL, LOCKED, APPROVED, REJECTED, CLOSED)
TERMINAL_STATUSES = (CLOSED,)

# A job may enter closeout only once it has (or had) a placed redline output.
CLOSEOUT_ELIGIBLE_JOB_STATES = (JOB_PLACED, JOB_CLOSEOUT_REVIEW, JOB_CLOSED)

# HARD blocker codes (any present => BLOCKED; approve/lock refused).
JOB_NOT_IN_CLOSEOUT_RANGE = "JOB_NOT_IN_CLOSEOUT_RANGE"
MISSING_MANIFEST = "MISSING_MANIFEST"
MISSING_ARTIFACT_BUNDLE = "MISSING_ARTIFACT_BUNDLE"
UNTRUSTED_OUTPUT = "UNTRUSTED_OUTPUT"
MANIFEST_NOT_RESOLVABLE = "MANIFEST_NOT_RESOLVABLE"
OPEN_ENGINE_BLOCKERS = "OPEN_ENGINE_BLOCKERS"
REVIEWED_BORE_LOG_NOT_READY = "REVIEWED_BORE_LOG_NOT_READY"
UNRESOLVED_REVIEW_ITEMS = "UNRESOLVED_REVIEW_ITEMS"
SOURCE_CONFLICT = "SOURCE_CONFLICT"
HARD_BLOCKER_CODES = (JOB_NOT_IN_CLOSEOUT_RANGE, MISSING_MANIFEST, MISSING_ARTIFACT_BUNDLE,
                      UNTRUSTED_OUTPUT, MANIFEST_NOT_RESOLVABLE, OPEN_ENGINE_BLOCKERS,
                      REVIEWED_BORE_LOG_NOT_READY, UNRESOLVED_REVIEW_ITEMS, SOURCE_CONFLICT)

# WARNING codes (recorded; never block closeout).
KMZ_EXPORT_BLOCKED = "KMZ_EXPORT_BLOCKED"
REVIEWED_BORE_LOG_NOT_RESOLVABLE = "REVIEWED_BORE_LOG_NOT_RESOLVABLE"
WARNING_CODES = (KMZ_EXPORT_BLOCKED, REVIEWED_BORE_LOG_NOT_RESOLVABLE)


class CloseoutReviewError(ValueError):
    """Base closeout_review error."""


class CloseoutNotFoundError(CloseoutReviewError):
    """No stored closeout_review for the requested job."""


class CloseoutStateError(CloseoutReviewError):
    """Operation not permitted in the record's current status (STATUS_TRANSITION_INVALID)."""


class CloseoutPermissionError(CloseoutReviewError):
    """A privileged transition was attempted without an authorized actor_role."""


# --------------------------------------------------------------------------- #
# Storage (ONE singleton record per job under its customer_project scope).
# --------------------------------------------------------------------------- #
def closeout_review_path(store_root, customer_project_id, processing_job_id) -> Path:
    return (job_dir(store_root, customer_project_id, processing_job_id) / CLOSEOUT_REVIEW_FILENAME)


def create_closeout_review(store_root, customer_project_id, processing_job_id, *, at, by) -> dict:
    """Create the ONE closeout_review for a job (status OPEN, no gate yet). Verifies the job exists and is
    in-scope. Raises on a duplicate (no silent overwrite — one status per job). Returns the record."""
    validate_customer_project_id(customer_project_id)
    validate_job_id(processing_job_id)
    load_job(store_root, customer_project_id, processing_job_id)          # exists + isolation
    path = closeout_review_path(store_root, customer_project_id, processing_job_id)
    if path.exists():
        raise CloseoutReviewError(
            "closeout_review already exists for %s/%s" % (customer_project_id, processing_job_id))
    record = {
        "record_format": CLOSEOUT_REVIEW_RECORD_FORMAT,
        "customer_project_id": customer_project_id,
        "processing_job_id": processing_job_id,
        "status": OPEN,
        "source_refs": {"redline_manifest": None, "artifact_bundle": None},
        "gate": None,
        "decision": None,
        "audit": [{"action": "closeout_review_created", "from": None, "to": OPEN,
                   "at": at, "by": by, "reason": None}],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def load_closeout_review(store_root, customer_project_id, processing_job_id) -> dict:
    path = closeout_review_path(store_root, customer_project_id, processing_job_id)
    if not path.is_file():
        raise CloseoutNotFoundError(
            "no closeout_review for %s/%s" % (customer_project_id, processing_job_id))
    record = json.loads(path.read_text(encoding="utf-8"))
    assert_same_project(customer_project_id, record.get("customer_project_id"))
    return record


def write_closeout_review(store_root, record) -> str:
    """Persist a record under its OWN (cp, job) scope (derived from the record, not ambient)."""
    cp = validate_customer_project_id(record["customer_project_id"])
    jid = validate_job_id(record["processing_job_id"])
    path = closeout_review_path(store_root, cp, jid)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return str(path)


# --------------------------------------------------------------------------- #
# Gate evaluation — READ-ONLY over trusted product contracts; result is STORED, not recomputed per render.
# --------------------------------------------------------------------------- #
def _snapshot_source_refs(job) -> dict:
    slots = job.get("slots") or {}
    m_slot, b_slot = slots.get("redline_manifest"), slots.get("artifact_bundle")
    return {"redline_manifest": (m_slot or {}).get("ref"),
            "artifact_bundle": (b_slot or {}).get("ref")}


def _compute_gate(store_root, customer_project_id, processing_job_id, *, at, by) -> dict:
    """Compute the closeout gate from trusted contracts only. Returns a gate snapshot
    {evaluated_at, evaluated_by, checks[], hard_blockers[], warnings[], kmz_export_status}."""
    hard, warnings, checks = [], [], []

    def hb(code, reason):
        hard.append({"code": code, "reason": reason})

    def wn(code, reason):
        warnings.append({"code": code, "reason": reason})

    def chk(name, passed, detail):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    job = load_job(store_root, customer_project_id, processing_job_id)    # exists + isolation
    in_range = job["status"] in CLOSEOUT_ELIGIBLE_JOB_STATES
    chk("job_in_closeout_range", in_range, "job status %s" % job["status"])
    if not in_range:
        hb(JOB_NOT_IN_CLOSEOUT_RANGE,
           "job status %r is not in the closeout range %r" % (job["status"], CLOSEOUT_ELIGIBLE_JOB_STATES))

    slots = job.get("slots") or {}
    m_slot, b_slot = slots.get("redline_manifest"), slots.get("artifact_bundle")
    m_ref = (m_slot or {}).get("ref") or {}
    b_ref = (b_slot or {}).get("ref") or {}
    chk("redline_manifest_slot_present", bool(m_slot), "redline_manifest output slot")
    if not m_slot:
        hb(MISSING_MANIFEST, "job has no redline_manifest output slot")
    chk("artifact_bundle_slot_present", bool(b_slot), "artifact_bundle output slot")
    if not b_slot:
        hb(MISSING_ARTIFACT_BUNDLE, "job has no artifact_bundle output slot")

    manifest = None
    if m_slot and b_slot:
        trusted = (m_ref.get("validation_status") == VALIDATION_VALIDATED
                   and b_ref.get("validation_status") == VALIDATION_VALIDATED)
        chk("output_slots_validated", trusted, "both output slots VALIDATED")
        if not trusted:
            hb(UNTRUSTED_OUTPUT, "an output slot is not %s" % VALIDATION_VALIDATED)
        else:
            bundle_id = b_ref.get("bundle_id")
            bundle_root = (job_dir(store_root, customer_project_id, processing_job_id)
                           / BUNDLE_STORE_SUBDIR / BUNDLES_SUBDIR / str(bundle_id))
            mpath = bundle_root / MANIFEST_FILENAME
            resolvable = mpath.is_file() and sha256_file(mpath) == m_ref.get("manifest_sha256")
            chk("stored_manifest_resolvable", resolvable, "durable manifest for bundle %r" % bundle_id)
            if not resolvable:
                hb(MANIFEST_NOT_RESOLVABLE,
                   "stored manifest missing or sha256 mismatch for bundle %r" % bundle_id)
            else:
                manifest = load_manifest(bundle_root)

    # Open engine/redline blockers (HARD) — only inspectable when the manifest resolved.
    if manifest is not None:
        blocked_logs = [lg.get("log_id") for lg in manifest.get("logs", [])
                        if lg.get("blocked") or lg.get("blocker")]
        chk("no_open_engine_blockers", not blocked_logs, "%d blocked log(s)" % len(blocked_logs))
        if blocked_logs:
            hb(OPEN_ENGINE_BLOCKERS,
               "manifest has %d open engine/redline blocker(s): %s"
               % (len(blocked_logs), ", ".join(str(x) for x in blocked_logs[:10])))

    # Reviewed bore-log freshness (resolve via the manifest handoff chain; catches post-handoff edits).
    rbl = None
    engine_run_id = m_ref.get("source_engine_run_id")
    if engine_run_id:
        try:
            handoff = load_handoff(store_root, customer_project_id, processing_job_id, engine_run_id)
            rbl = load_reviewed_bore_log(store_root, customer_project_id, processing_job_id,
                                         handoff.get("reviewed_bore_log_id"))
        except (ManifestHandoffError, ReviewedBoreLogError):
            rbl = None
    if rbl is None:
        chk("reviewed_bore_log_resolved", False, "reviewed_bore_log via handoff chain")
        if m_slot and b_slot:
            wn(REVIEWED_BORE_LOG_NOT_RESOLVABLE,
               "could not resolve the reviewed_bore_log via the manifest handoff chain")
    else:
        q = review_queue(rbl)
        ready = q["engine_ready"]
        needing = q["rows_needing_review"]
        conflicted = [g["group_id"] for g in rbl.get("groups", [])
                      if g.get("grouping_status") == RBL_SOURCE_CONFLICT]
        chk("reviewed_bore_log_engine_ready", ready,
            "%d row(s) needing review, %d source-conflict group(s)" % (len(needing), len(conflicted)))
        if not ready:
            hb(REVIEWED_BORE_LOG_NOT_READY,
               "reviewed_bore_log %r is not engine-ready" % rbl.get("reviewed_bore_log_id"))
        if needing:
            hb(UNRESOLVED_REVIEW_ITEMS,
               "reviewed_bore_log has %d row(s) needing review: %s"
               % (len(needing), ", ".join(str(x) for x in needing[:10])))
        if conflicted:
            hb(SOURCE_CONFLICT,
               "reviewed_bore_log has unresolved source-conflict group(s): %s" % ", ".join(conflicted))

    # KMZ/KML geometry export safety (WARNING) — current real manifests are pixel-only; PDF-first closeout
    # does not require geospatial export. (Future geospatial-severity escalation is a deliberately deferred
    # decision and is NOT implemented here.)
    kmz_status = None
    if manifest is not None:
        kmz_rec = kmz_export.evaluate_export(store_root, customer_project_id, processing_job_id)
        kmz_status = kmz_rec.get("status")
        chk("kmz_export_evaluated", True, "kmz export status %s" % kmz_status)
        if kmz_status == kmz_export.BLOCKED:
            codes = sorted({b["code"] for b in kmz_rec.get("blockers", [])})
            wn(KMZ_EXPORT_BLOCKED,
               "kmz/kml geometry export is blocked (%s); not required for PDF-first closeout"
               % ", ".join(codes))

    return {"evaluated_at": at, "evaluated_by": by, "checks": checks,
            "hard_blockers": hard, "warnings": warnings, "kmz_export_status": kmz_status}


def _status_after_eval(current_status, has_hard) -> str:
    """The status implied by a fresh evaluation. Re-evaluation may move among OPEN/BLOCKED/
    READY_FOR_APPROVAL, and SAFELY downgrades LOCKED/APPROVED -> BLOCKED when new hard blockers appear
    (an input change after approval invalidates approval — contract §6). Human decisions (REJECTED) stick
    until an explicit reopen; CLOSED is terminal (callers must not evaluate a CLOSED record)."""
    if current_status in (OPEN, BLOCKED, READY_FOR_APPROVAL):
        return BLOCKED if has_hard else READY_FOR_APPROVAL
    if current_status in (LOCKED, APPROVED):
        return BLOCKED if has_hard else current_status
    return current_status                                                # REJECTED / CLOSED unchanged


def _apply_eval(record, store_root, *, at, by, action):
    """Recompute + store the gate snapshot and update the derived status. Returns (gate, has_hard)."""
    cp, jid = record["customer_project_id"], record["processing_job_id"]
    gate = _compute_gate(store_root, cp, jid, at=at, by=by)
    record["gate"] = gate
    record["source_refs"] = _snapshot_source_refs(load_job(store_root, cp, jid))
    has_hard = bool(gate["hard_blockers"])
    frm = record["status"]
    new = _status_after_eval(frm, has_hard)
    if new != frm:
        reason = ("approval/lock invalidated by input change: %d hard blocker(s)" % len(gate["hard_blockers"])
                  if frm in (LOCKED, APPROVED) and new == BLOCKED
                  else "gate evaluated: %d hard blocker(s)" % len(gate["hard_blockers"]))
        record["audit"].append({"action": action, "from": frm, "to": new,
                                "at": at, "by": by, "reason": reason})
        record["status"] = new
    else:
        record["audit"].append({"action": action, "from": frm, "to": frm,
                                "at": at, "by": by, "reason": "re-evaluated"})
    return gate, has_hard


def evaluate_closeout(store_root, customer_project_id, processing_job_id, *, at, by) -> dict:
    """Recompute the server-side gate, store the snapshot, and set the derived status. READ-ONLY over every
    OTHER contract (writes only the closeout record); never touches export_package. Raises CloseoutStateError
    on a CLOSED (terminal) record. Returns the updated record."""
    record = load_closeout_review(store_root, customer_project_id, processing_job_id)
    if record["status"] == CLOSED:
        raise CloseoutStateError("closeout_review is CLOSED (terminal); cannot evaluate")
    _apply_eval(record, store_root, at=at, by=by, action="evaluated")
    write_closeout_review(store_root, record)
    return record


# --------------------------------------------------------------------------- #
# Audited transitions. Privileged ops (lock/unlock/approve/reopen/close) are permission-gated.
# --------------------------------------------------------------------------- #
def _require_permission(actor_role, authorized_roles) -> None:
    if not isinstance(actor_role, str) or not actor_role:
        raise CloseoutPermissionError("actor_role is required for a privileged transition")
    roles = tuple(authorized_roles or ())
    if actor_role not in roles:
        raise CloseoutPermissionError(
            "actor_role %r is not authorized (allowed roles: %r)" % (actor_role, roles))


def _transition(record, action, allowed_from, to_status, *, at, by, reason) -> None:
    frm = record["status"]
    if frm not in allowed_from:
        raise CloseoutStateError(
            "cannot %s from status %s (allowed from: %r)" % (action, frm, allowed_from))
    record["status"] = to_status
    record["audit"].append({"action": action, "from": frm, "to": to_status,
                            "at": at, "by": by, "reason": reason})


def lock_closeout(store_root, customer_project_id, processing_job_id, *, at, by,
                  actor_role, authorized_roles, reason=None) -> dict:
    """Permission-gated durable freeze: READY_FOR_APPROVAL -> LOCKED. Re-evaluates first; if any hard
    blocker is present the record is left BLOCKED and CloseoutStateError is raised. Returns the record."""
    _require_permission(actor_role, authorized_roles)
    record = load_closeout_review(store_root, customer_project_id, processing_job_id)
    _, has_hard = _apply_eval(record, store_root, at=at, by=by, action="evaluated_for_lock")
    if has_hard:
        write_closeout_review(store_root, record)
        raise CloseoutStateError(
            "cannot lock: %d hard blocker(s) present" % len(record["gate"]["hard_blockers"]))
    _transition(record, "locked", (READY_FOR_APPROVAL,), LOCKED, at=at, by=by, reason=reason)
    write_closeout_review(store_root, record)
    return record


def unlock_closeout(store_root, customer_project_id, processing_job_id, *, at, by,
                    actor_role, authorized_roles, reason=None) -> dict:
    """Permission-gated unlock: LOCKED -> READY_FOR_APPROVAL. Returns the record."""
    _require_permission(actor_role, authorized_roles)
    record = load_closeout_review(store_root, customer_project_id, processing_job_id)
    _transition(record, "unlocked", (LOCKED,), READY_FOR_APPROVAL, at=at, by=by, reason=reason)
    write_closeout_review(store_root, record)
    return record


def approve_closeout(store_root, customer_project_id, processing_job_id, *, at, by,
                     actor_role, authorized_roles, reason=None) -> dict:
    """Permission-gated approval: {READY_FOR_APPROVAL, LOCKED} -> APPROVED. Re-evaluates first and REFUSES
    (leaving the record BLOCKED) if ANY hard blocker is present — a closeout can never read "approved" while
    a known blocker is open. Returns the record."""
    _require_permission(actor_role, authorized_roles)
    record = load_closeout_review(store_root, customer_project_id, processing_job_id)
    _, has_hard = _apply_eval(record, store_root, at=at, by=by, action="evaluated_for_approval")
    if has_hard:
        write_closeout_review(store_root, record)
        raise CloseoutStateError(
            "cannot approve: %d hard blocker(s) present" % len(record["gate"]["hard_blockers"]))
    _transition(record, "approved", (READY_FOR_APPROVAL, LOCKED), APPROVED, at=at, by=by, reason=reason)
    record["decision"] = {"kind": APPROVED, "by": by, "at": at, "reason": reason}
    write_closeout_review(store_root, record)
    return record


def reject_closeout(store_root, customer_project_id, processing_job_id, *, at, by, reason) -> dict:
    """Reviewer send-back: {OPEN, BLOCKED, READY_FOR_APPROVAL, LOCKED} -> REJECTED. A reason is REQUIRED.
    Returns the record."""
    if not reason:
        raise CloseoutReviewError("reject_closeout requires a reason")
    record = load_closeout_review(store_root, customer_project_id, processing_job_id)
    _transition(record, "rejected", (OPEN, BLOCKED, READY_FOR_APPROVAL, LOCKED), REJECTED,
                at=at, by=by, reason=reason)
    record["decision"] = {"kind": REJECTED, "by": by, "at": at, "reason": reason}
    write_closeout_review(store_root, record)
    return record


def reopen_closeout(store_root, customer_project_id, processing_job_id, *, at, by,
                    actor_role, authorized_roles, reason) -> dict:
    """Permission-gated reopen: {REJECTED, APPROVED} -> OPEN. A reason is REQUIRED (reopening APPROVED
    invalidates approval — contract §6). Clears the current decision; audit retains the history. The next
    evaluate recomputes the gate/status. Returns the record."""
    if not reason:
        raise CloseoutReviewError("reopen_closeout requires a reason")
    _require_permission(actor_role, authorized_roles)
    record = load_closeout_review(store_root, customer_project_id, processing_job_id)
    _transition(record, "reopened", (REJECTED, APPROVED), OPEN, at=at, by=by, reason=reason)
    record["decision"] = None
    write_closeout_review(store_root, record)
    return record


def close_closeout(store_root, customer_project_id, processing_job_id, *, at, by,
                   actor_role, authorized_roles, reason=None) -> dict:
    """Permission-gated finalize: APPROVED -> CLOSED (terminal, immutable). Returns the record."""
    _require_permission(actor_role, authorized_roles)
    record = load_closeout_review(store_root, customer_project_id, processing_job_id)
    _transition(record, "closed", (APPROVED,), CLOSED, at=at, by=by, reason=reason)
    write_closeout_review(store_root, record)
    return record


# --------------------------------------------------------------------------- #
# Pure read-only view (no IO, no mutation) — the single value all readiness UI should render.
# --------------------------------------------------------------------------- #
def closeout_summary(record) -> dict:
    """Derived, side-effect-free summary of a closeout_review record (re-runnable)."""
    gate = record.get("gate") or {}
    hard = gate.get("hard_blockers", []) or []
    warn = gate.get("warnings", []) or []
    status = record["status"]
    return {
        "status": status,
        "hard_blocker_count": len(hard),
        "warning_count": len(warn),
        "hard_blocker_codes": sorted({b["code"] for b in hard}),
        "warning_codes": sorted({w["code"] for w in warn}),
        "is_blocked": status == BLOCKED,
        "is_locked": status == LOCKED,
        "is_approved": status == APPROVED,
        "is_terminal": status in TERMINAL_STATUSES,
        "is_approvable": status in (READY_FOR_APPROVAL, LOCKED) and not hard,
    }
