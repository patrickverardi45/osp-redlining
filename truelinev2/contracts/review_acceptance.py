"""Phase 6 — REVIEW acceptance lane (contract + thin render orchestration).

Makes REVIEW a FIRST-CLASS product output, not a failure. The uploaded-corpus placement ENGINE generates a
SOURCE-SUPPORTED REVIEW redline candidate from a job's own uploaded plan + reviewed bore-log; this lane
records that candidate, surfaces its evidence + caveats, and lets a human ACCEPT or REJECT the
engine-generated candidate WITHOUT manually drawing the route.

Three honest tiers (the product never fakes AUTO):
  * AUTO     — deterministic, source-tight; the engine alone decides it (no human confirmation gate). AUTO
               stays BLOCKED unless the engine's own source evidence supports it (it does not on a corpus
               with no per-bore termini); this lane never promotes REVIEW to AUTO.
  * REVIEW   — the engine generated a drawable candidate that is NOT source-tight enough for AUTO. It is
               rendered (a real dashed red FINAL_REDLINE_PNG) and held as a REVIEW_CANDIDATE until a human
               explicitly ACCEPTS it (-> REVIEW_ACCEPTED) or REJECTS it (-> REVIEW_REJECTED).
  * ABSTAIN  — the engine found no credible source evidence; recorded ABSTAINED with the engine's named
               blocker. Nothing is rendered.

Provenance discipline (do-not-widen, no fake AUTO):
  * The candidate geometry is ENGINE-generated from the plan's own drawn vectors — the human never draws
    control points (``no_manual_geometry`` is always True). Accepting is a decision, not a redraw; the
    rendered artifacts are byte-identical before and after acceptance.
  * The acceptance record carries the rich provenance — ENGINE_GENERATED_REVIEW_CANDIDATE while pending,
    ENGINE_GENERATED_HUMAN_ACCEPTED_REVIEW once accepted — and NEVER DETERMINISTIC_AUTO.
  * The published redline manifest stays within its frozen schema enum (per-log provenance
    OWNER_CONFIRMED_HUMAN_ADJUSTABLE, an EXISTING value — human-confirmed, never DETERMINISTIC_AUTO); the
    Phase-6 provenance is echoed into the manifest's free-form ``warnings`` by the engine adapter, so the
    committed deterministic 50/58 example/frontier + the engine->website schema are untouched.

Boundaries: this module RUNS no engine and RENDERS nothing itself — it drives the existing, tested
uploaded-corpus engine adapter (which reuses the engine + renderer + publisher read-only) and persists a
job-local acceptance record. No schema change, no fixture/anchor/coordinate change, no new manifest enum,
no second corpus. The candidate bundle is a SEPARATE job-local bundle (bundle_origin UPLOADED_CORPUS_ENGINE,
frontier "1/1") and is NEVER summed into the committed deterministic 50/58 frontier. Name-free: no
customer/project/location/operator literal lives here.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from truelinev2.contracts.customer_project import assert_same_project, validate_customer_project_id
from truelinev2.contracts.processing_job import job_dir, load_job, validate_job_id
from truelinev2.contracts import uploaded_corpus_engine_handoff as uce
from truelinev2.schema.models import PlacementStatus

RECORD_FORMAT = "trueline-review-acceptance-1"
REVIEW_ACCEPTANCE_SUBDIR = "review_acceptance"
RECORD_FILENAME = "_review_candidate.json"

# Acceptance state machine (the user-facing product status).
STATUS_REVIEW_CANDIDATE = "REVIEW_CANDIDATE"
STATUS_REVIEW_ACCEPTED = "REVIEW_ACCEPTED"
STATUS_REVIEW_REJECTED = "REVIEW_REJECTED"
STATUS_ABSTAINED = "ABSTAINED"

# Engine placement tiers (honest; AUTO is never synthesized by this lane).
TIER_AUTO = "AUTO"
TIER_REVIEW = "REVIEW"
TIER_ABSTAIN = "ABSTAIN"

# Acceptance-record provenance (NOT a manifest enum value — kept out of the frozen schema on purpose).
CANDIDATE_ORIGIN = "ENGINE_GENERATED"
CANDIDATE_PROVENANCE = "ENGINE_GENERATED_REVIEW_CANDIDATE"
ACCEPTED_PROVENANCE = "ENGINE_GENERATED_HUMAN_ACCEPTED_REVIEW"

# Named, honest reason AUTO is blocked for an uploaded corpus drawn as one continuous alignment with no
# per-bore termini / tight unique run (the banked finding). Surfaced so REVIEW is explained, never to claim
# AUTO. An engine placement that DOES reach AUTO_SELECT carries the engine's own source-tight evidence.
NO_PER_BORE_TERMINI = "NO_PER_BORE_TERMINI"

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")


class ReviewAcceptanceError(ValueError):
    """Base review-acceptance error (invalid id / missing reason / bad target)."""


class ReviewCandidateNotFoundError(ReviewAcceptanceError):
    """No stored review-acceptance record for the requested candidate."""


class ReviewAcceptanceStateError(ReviewAcceptanceError):
    """The candidate is not in a state that permits the requested action (e.g. accepting a rejected
    candidate, or rejecting an accepted one)."""


def _candidate_id(reviewed_bore_log_id) -> str:
    """Deterministic, name-free candidate id derived from the reviewed_bore_log id (one engine candidate
    per engine-ready reviewed bore-log)."""
    cid = "rc-%s" % reviewed_bore_log_id
    if not _ID_RE.match(cid):
        raise ReviewAcceptanceError("cannot derive a safe candidate id from %r" % (reviewed_bore_log_id,))
    return cid


def validate_candidate_id(candidate_id) -> str:
    if not isinstance(candidate_id, str) or not _ID_RE.match(candidate_id):
        raise ReviewAcceptanceError(
            "candidate id must match %s (got %r)" % (_ID_RE.pattern, candidate_id))
    return candidate_id


def _dir(store_root, customer_project_id, job_id, candidate_id) -> Path:
    validate_candidate_id(candidate_id)
    return (job_dir(store_root, customer_project_id, job_id)
            / REVIEW_ACCEPTANCE_SUBDIR / candidate_id)


def _path(store_root, customer_project_id, job_id, candidate_id) -> Path:
    return _dir(store_root, customer_project_id, job_id, candidate_id) / RECORD_FILENAME


def _write(store_root, record) -> None:
    cp = validate_customer_project_id(record["customer_project_id"])
    jid = validate_job_id(record["processing_job_id"])
    path = _path(store_root, cp, jid, record["candidate_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


def load_review_candidate(store_root, customer_project_id, job_id, candidate_id) -> dict:
    path = _path(store_root, customer_project_id, job_id, candidate_id)
    if not path.is_file():
        raise ReviewCandidateNotFoundError(
            "no review candidate %s/%s/%s" % (customer_project_id, job_id, candidate_id))
    rec = json.loads(path.read_text(encoding="utf-8"))
    assert_same_project(customer_project_id, rec.get("customer_project_id"))
    return rec


def list_review_candidates(store_root, customer_project_id, job_id) -> list:
    """Every review-acceptance record under one job (tenant + job scoped; [] if none). Each record is
    re-verified in-scope (defense in depth). Ordered by candidate_id."""
    validate_customer_project_id(customer_project_id)
    validate_job_id(job_id)
    root = job_dir(store_root, customer_project_id, job_id) / REVIEW_ACCEPTANCE_SUBDIR
    if not root.is_dir():
        return []
    out = []
    for child in sorted(root.iterdir()):
        rec_path = child / RECORD_FILENAME
        if rec_path.is_file():
            rec = json.loads(rec_path.read_text(encoding="utf-8"))
            assert_same_project(customer_project_id, rec.get("customer_project_id"))
            out.append(rec)
    return out


def _why_not_auto(candidate) -> dict:
    """Honest, source-grounded explanation of why this candidate is REVIEW and not AUTO. NEVER asserts AUTO.
    The deterministic AUTO gate needs per-bore termini / a tight unique drawn run; an uploaded corpus drawn
    as one continuous alignment has none, so AUTO is blocked. Cross-sheet / matchline caveats that further
    hold back AUTO are echoed from the engine candidate's caveats."""
    blockers = [NO_PER_BORE_TERMINI]
    caveats = list(candidate.get("caveats") or [])
    for c in (uce.MATCHLINE_CONTINUATION_UNVERIFIED, uce.CROSS_SHEET_CONTINUATION_REVIEW,
              uce.PARTIAL_CROSS_SHEET_REVIEW):
        if c in caveats and c not in blockers:
            blockers.append(c)
    return {"auto_blocked": True, "blockers": blockers, "engine_reason": candidate.get("reason")}


def _new_record(*, candidate_id, customer_project_id, job_id, reviewed_bore_log_id, tier, status,
                provenance, candidate=None, bundle=None, blockers=None, at, by) -> dict:
    cand = candidate or {}
    return {
        "record_format": RECORD_FORMAT,
        "candidate_id": candidate_id,
        "customer_project_id": customer_project_id,
        "processing_job_id": job_id,
        "reviewed_bore_log_id": reviewed_bore_log_id,
        "tier": tier,
        "status": status,
        "candidate_origin": CANDIDATE_ORIGIN,
        "no_manual_geometry": True,             # the human never draws — engine geometry only
        "provenance": provenance,
        "placement_status": cand.get("placement_status"),
        "engine_reason": cand.get("reason"),
        "dialect": cand.get("dialect"),
        "bore_span": cand.get("bore_span"),
        "referenced_sheets": cand.get("referenced_sheets") or [],
        "render_sheets": cand.get("render_sheets") or [],
        "caveats": list(cand.get("caveats") or []),
        "matchline_continuity": cand.get("matchline_continuity"),
        "matchline_evidence": cand.get("matchline_evidence") or [],
        "why_not_auto": _why_not_auto(cand) if tier == TIER_REVIEW else None,
        "coverage": None,                       # per-sheet coverage metrics: a later lane (not solved here)
        "blockers": list(blockers or []),
        "bundle": bundle,
        "created_at": at,
        "created_by": by,
        "updated_at": at,
        "accepted_at": None,
        "accepted_by": None,
        "rejected_at": None,
        "rejected_by": None,
        "rejection_reason": None,
        "audit": [{"action": "review_candidate_generated", "at": at, "by": by,
                   "from": None, "to": status, "reason": None}],
    }


def generate_review_candidate(store_root, customer_project_id, job_id, *, at, by) -> dict:
    """Ask the uploaded-corpus engine for this job's redline candidate and record the honest tier.

      * REVIEW  -> render the candidate (real dashed FINAL_REDLINE_PNG bundle) and persist a
                   REVIEW_CANDIDATE record awaiting human accept/reject.
      * AUTO    -> deterministic + source-tight; render it (no acceptance record / no human gate) and report
                   tier AUTO. This lane never synthesizes AUTO — only the engine can.
      * ABSTAIN -> persist an ABSTAINED record with the engine's named blocker; render nothing.
      * not runnable (inputs missing) -> no record; report the input blockers.

    Idempotent: if a record already exists for this candidate, its decision is preserved and returned
    unchanged (re-generating never resets an accept/reject)."""
    validate_customer_project_id(customer_project_id)
    validate_job_id(job_id)
    load_job(store_root, customer_project_id, job_id)            # exists + isolation (404)

    ev = uce.evaluate_uploaded_corpus_engine_handoff(store_root, customer_project_id, job_id)
    rbl_id = ev.get("reviewed_bore_log_id")
    if rbl_id is None:                                           # no engine-ready reviewed bore-log
        return {"tier": None, "runnable": False, "candidate_id": None, "record": None,
                "bundle": None, "blockers": ev["blockers"]}

    candidate_id = _candidate_id(rbl_id)
    try:                                                        # decision already taken -> preserve it
        existing = load_review_candidate(store_root, customer_project_id, job_id, candidate_id)
        return _report(existing)
    except ReviewCandidateNotFoundError:
        pass

    if ev["runnable"]:
        cand = ev["candidate"]
        if cand["placement_status"] == PlacementStatus.AUTO_SELECT.value:
            # AUTO: engine-determined, source-tight. No acceptance gate; render deterministically as-is.
            bundle = uce.render_uploaded_corpus_engine_handoff(
                store_root, customer_project_id, job_id, at=at, by=by)
            return {"tier": TIER_AUTO, "runnable": True, "candidate_id": None, "record": None,
                    "bundle": bundle, "blockers": [], "requires_acceptance": False}
        # REVIEW: render the candidate, then record it pending human accept/reject.
        bundle = uce.render_uploaded_corpus_engine_handoff(
            store_root, customer_project_id, job_id, at=at, by=by)
        record = _new_record(
            candidate_id=candidate_id, customer_project_id=customer_project_id, job_id=job_id,
            reviewed_bore_log_id=rbl_id, tier=TIER_REVIEW, status=STATUS_REVIEW_CANDIDATE,
            provenance=CANDIDATE_PROVENANCE, candidate=cand, bundle=bundle, at=at, by=by)
        _write(store_root, record)
        return _report(record)

    # Not runnable: an engine ABSTAIN / no-dialect is a credible-evidence ABSTAIN (record it); pure input
    # preconditions (no plan / no engine-ready reviewed bore-log) are not an abstain (no record).
    codes = {b["code"] for b in ev["blockers"]}
    if codes & {uce.ENGINE_ABSTAINED, uce.NO_PLAN_DIALECT_RECOGNIZED}:
        record = _new_record(
            candidate_id=candidate_id, customer_project_id=customer_project_id, job_id=job_id,
            reviewed_bore_log_id=rbl_id, tier=TIER_ABSTAIN, status=STATUS_ABSTAINED,
            provenance=None, candidate=None, bundle=None, blockers=ev["blockers"], at=at, by=by)
        _write(store_root, record)
        return _report(record)
    return {"tier": None, "runnable": False, "candidate_id": candidate_id, "record": None,
            "bundle": None, "blockers": ev["blockers"]}


def accept_review_candidate(store_root, customer_project_id, job_id, candidate_id, *, at, by) -> dict:
    """Human ACCEPTS the engine-generated REVIEW candidate as-is (no geometry redrawn). Transitions
    REVIEW_CANDIDATE -> REVIEW_ACCEPTED and confers provenance ENGINE_GENERATED_HUMAN_ACCEPTED_REVIEW. The
    rendered artifacts are unchanged (acceptance is a decision, not a re-render). Idempotent on an
    already-accepted candidate; 409 (state) if the candidate was rejected / abstained / is not a REVIEW
    candidate."""
    rec = load_review_candidate(store_root, customer_project_id, job_id, candidate_id)
    if rec["status"] == STATUS_REVIEW_ACCEPTED:
        return rec                                              # idempotent
    if rec["status"] != STATUS_REVIEW_CANDIDATE:
        raise ReviewAcceptanceStateError(
            "candidate %r is %s; only a %s can be accepted"
            % (candidate_id, rec["status"], STATUS_REVIEW_CANDIDATE))
    rec["status"] = STATUS_REVIEW_ACCEPTED
    rec["provenance"] = ACCEPTED_PROVENANCE
    rec["no_manual_geometry"] = True
    rec["accepted_at"] = at
    rec["accepted_by"] = by
    rec["updated_at"] = at
    rec["audit"].append({"action": "review_candidate_accepted", "at": at, "by": by,
                         "from": STATUS_REVIEW_CANDIDATE, "to": STATUS_REVIEW_ACCEPTED, "reason": None})
    _write(store_root, rec)
    return rec


def reject_review_candidate(store_root, customer_project_id, job_id, candidate_id, *, reason, at, by) -> dict:
    """Human REJECTS the engine-generated REVIEW candidate (needs correction). Transitions
    REVIEW_CANDIDATE -> REVIEW_REJECTED with a required non-empty reason. A rejected candidate stays
    rejected (it can never be silently accepted). Idempotent on an already-rejected candidate; 409 (state)
    if the candidate was accepted / abstained / is not a REVIEW candidate."""
    if not isinstance(reason, str) or not reason.strip():
        raise ReviewAcceptanceError("a rejection reason is required")
    rec = load_review_candidate(store_root, customer_project_id, job_id, candidate_id)
    if rec["status"] == STATUS_REVIEW_REJECTED:
        return rec                                              # idempotent (original reason preserved)
    if rec["status"] != STATUS_REVIEW_CANDIDATE:
        raise ReviewAcceptanceStateError(
            "candidate %r is %s; only a %s can be rejected"
            % (candidate_id, rec["status"], STATUS_REVIEW_CANDIDATE))
    rec["status"] = STATUS_REVIEW_REJECTED
    rec["rejection_reason"] = reason.strip()
    rec["rejected_at"] = at
    rec["rejected_by"] = by
    rec["updated_at"] = at
    rec["audit"].append({"action": "review_candidate_rejected", "at": at, "by": by,
                         "from": STATUS_REVIEW_CANDIDATE, "to": STATUS_REVIEW_REJECTED,
                         "reason": reason.strip()})
    _write(store_root, rec)
    return rec


def _report(record) -> dict:
    """Uniform generate() report wrapping a stored acceptance record."""
    tier = record.get("tier")
    return {
        "tier": tier,
        "runnable": tier in (TIER_REVIEW, TIER_AUTO),
        "candidate_id": record.get("candidate_id"),
        "record": record,
        "bundle": record.get("bundle"),
        "blockers": record.get("blockers") or [],
    }
