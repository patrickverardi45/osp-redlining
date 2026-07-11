"""Phase 9 — product workflow orchestrator (the 3-path redline decision + closeout assembly).

This is the seam that connects an uploaded product job to the REAL proven redline capability. It chooses,
IN ORDER, among three honest redline paths and DRIVES the existing, tested contracts read-only — it RUNS no
engine and RENDERS nothing itself:

  A. RECOGNIZED_DETERMINISTIC — the uploaded PLAN_PDF + an engine-ready reviewed bore-log positively
     recognize a DRAWN deterministic log (exact sha256 in the deployment registry). Serve the EXISTING
     committed engine render (render commit c19b565) via ``recognized_corpus_handoff`` — real PNG artifacts,
     provenance DETERMINISTIC_AUTO / bundle_origin DETERMINISTIC_RECOGNIZED_CORPUS. NEVER relabeled.
  B. UPLOADED_REVIEW / UPLOADED_AUTO — not recognized, but the shipped engine places a drawable candidate on
     the job's OWN uploaded plan; generate a REVIEW candidate (``review_acceptance``) — a real dashed
     FINAL_REDLINE_PNG held for human accept/reject. The lane never promotes REVIEW to AUTO.
  C. ABSTAIN — neither recognized nor placeable: report the SPECIFIC reasons (the recognition blockers AND
     the engine's own named reason — never a bare ENGINE_ABSTAINED) and render nothing; accept stays blocked.

After a successful render (A / B) the job lifecycle is advanced to PLACED so the downstream closeout/export
chain is reachable (slot-setting alone does not transition the job). ``assemble_closeout_package`` then walks
the job to CLOSEOUT_REVIEW, evaluates the closeout + KMZ-export safety, and assembles the export-package
descriptor — gating on REVIEW acceptance so a pending/rejected REVIEW redline is never packaged.

Boundaries: no engine/renderer/fixture/anchor/coordinate/schema change; no new manifest enum; no fake AUTO;
no invented coordinates; the deterministic 50/58 frontier is untouched (recognized/uploaded bundles are
job-local). Name-free: no customer/project/location/operator literal lives here.
"""
from __future__ import annotations

from truelinev2.contracts.customer_project import validate_customer_project_id
from truelinev2.contracts.processing_job import (
    AWAITING_REVIEW,
    CLOSED,
    CLOSEOUT_REVIEW,
    CREATED,
    EXTRACTING,
    FAILED,
    PLACED,
    PLACING,
    UPLOADING,
    load_job,
    transition,
    validate_job_id,
)
from truelinev2.contracts.recognized_corpus_handoff import (
    RecognizedCorpusError,
    evaluate_recognized_corpus_handoff,
    render_recognized_corpus_handoff,
)
from truelinev2.contracts.review_acceptance import (
    STATUS_ABSTAINED,
    STATUS_REVIEW_ACCEPTED,
    STATUS_REVIEW_CANDIDATE,
    STATUS_REVIEW_REJECTED,
    STATUS_REVIEW_SUPERSEDED,
    TIER_ABSTAIN,
    TIER_AUTO,
    TIER_REVIEW,
    generate_review_candidate,
    list_review_candidates,
)
from truelinev2.contracts.closeout_review import (
    CloseoutNotFoundError,
    closeout_summary,
    create_closeout_review,
    evaluate_closeout,
    load_closeout_review,
)
from truelinev2.contracts.billing_summary import (
    BillingSummaryNotFoundError,
    billing_summary_view,
    compute_billing_summary,
    create_billing_summary,
    load_billing_summary,
)
from truelinev2.contracts.kmz_export import evaluate_export
from truelinev2.contracts.export_package import (
    ExportPackageNotFoundError,
    assemble_export_package,
    create_export_package,
    export_package_view,
    load_export_package,
)

# Redline-path outcomes (the product-visible decision; honest, never faked).
PATH_RECOGNIZED = "RECOGNIZED_DETERMINISTIC"
PATH_UPLOADED_REVIEW = "UPLOADED_REVIEW"
PATH_UPLOADED_AUTO = "UPLOADED_AUTO"
PATH_ABSTAIN = "ABSTAIN"

# Provenance echoed back to the caller (matches what each underlying lane records — never invented here).
PROVENANCE_DETERMINISTIC_AUTO = "DETERMINISTIC_AUTO"
PROVENANCE_REVIEW_CANDIDATE = "ENGINE_GENERATED_REVIEW_CANDIDATE"

# Closeout-assembly review gate codes (a REVIEW redline must be human-accepted before it is packaged).
REVIEW_NOT_ACCEPTED = "REVIEW_NOT_ACCEPTED"
REVIEW_WAS_REJECTED = "REVIEW_WAS_REJECTED"
REVIEW_ABSTAINED = "REVIEW_ABSTAINED"

# Linear lifecycle order (CREATED..CLOSED); FAILED is off-chain (cannot be advanced through).
_FORWARD_ORDER = (CREATED, UPLOADING, EXTRACTING, AWAITING_REVIEW, PLACING, PLACED, CLOSEOUT_REVIEW, CLOSED)


class ProductWorkflowError(ValueError):
    """Product workflow orchestration error (e.g. a FAILED job cannot be advanced)."""


def _advance_to(store_root, customer_project_id, job_id, target, *, at, by, reason):
    """Walk the linear job lifecycle FORWARD from its current status to ``target`` (idempotent: a no-op if
    already at/after target). Each step is one audited contract transition. Raises if the job is FAILED or
    the path is not a forward walk."""
    job = load_job(store_root, customer_project_id, job_id)
    cur = job["status"]
    if cur == FAILED:
        raise ProductWorkflowError("job %r is FAILED; cannot advance to %s" % (job_id, target))
    if cur not in _FORWARD_ORDER or target not in _FORWARD_ORDER:
        raise ProductWorkflowError("cannot advance %s -> %s" % (cur, target))
    ci, ti = _FORWARD_ORDER.index(cur), _FORWARD_ORDER.index(target)
    while ci < ti:
        nxt = _FORWARD_ORDER[ci + 1]
        job = transition(store_root, customer_project_id, job_id, nxt, at=at, by=by, reason=reason)
        ci += 1
    return job


def _merge_abstain_blockers(rec_ev, gen):
    """Build the SPECIFIC abstain reason set: the recognition blockers (why the package is not a known
    deterministic corpus) PLUS the engine's own named blockers (why the engine could not place — never a
    bare ENGINE_ABSTAINED, the engine's reason string is preserved). Tagged by source for the UI.

    Carries EVERY key an underlying blocker dict has (code/reason ALWAYS, plus any additive detail such as
    ``reviewed_rows_detail`` — see uploaded_corpus_engine_handoff.py's reviewed-row adapter fallback), not
    just code/reason: a blocker that named WHY the reviewed-row adapter declined (e.g.
    OCR_ROW_REQUIRES_EXPLICIT_FOOTAGE) must not go silently generic once it reaches this composite response
    — the honest detail the engine already computed must survive to the API caller. Additive; a blocker
    with no extra keys is byte-identical to before (still exactly {source, code, reason})."""
    out = []
    for b in rec_ev.get("blockers", []) or []:
        out.append({**b, "source": "recognition"})
    for b in gen.get("blockers", []) or []:
        out.append({**b, "source": "engine"})
    return out


def run_product_redline(store_root, customer_project_id, job_id, *, registry, at, by,
                        uploaded_corpus_auto_optin: bool = False) -> dict:
    """Choose + run the correct redline path for a job's uploaded package, IN ORDER (recognized
    deterministic -> uploaded REVIEW/AUTO -> abstain). On a successful render the job advances to PLACED.
    Returns a uniform decision report; never fakes AUTO and never invents geometry. 404 if the job is
    missing (raised by the underlying contracts)."""
    validate_customer_project_id(customer_project_id)
    validate_job_id(job_id)
    load_job(store_root, customer_project_id, job_id)               # exists + isolation (404)

    # --- Path A: recognized deterministic package (serve the existing committed engine render) --------- #
    rec_ev = evaluate_recognized_corpus_handoff(store_root, customer_project_id, job_id, registry=registry)
    if rec_ev.get("runnable"):
        render = render_recognized_corpus_handoff(
            store_root, customer_project_id, job_id, registry=registry, at=at, by=by)
        _advance_to(store_root, customer_project_id, job_id, PLACED,
                    at=at, by=by, reason="workflow: recognized deterministic redline placed")
        return {
            "path": PATH_RECOGNIZED, "runnable": True, "rendered": True,
            "provenance": PROVENANCE_DETERMINISTIC_AUTO,
            "recognized_corpus_id": rec_ev.get("recognized_corpus_id"),
            "deterministic_log_id": rec_ev.get("deterministic_log_id"),
            "render_commit": rec_ev.get("render_commit"),
            "render_sheets": rec_ev.get("render_sheets"),
            "render": render, "candidate_id": None, "review": None, "blockers": [],
        }

    # --- Path B: uploaded supported package (engine places a candidate -> REVIEW, never faked AUTO) ---- #
    # generate_review_candidate is IDEMPOTENT — it PRESERVES a prior decision, so calling it again for a job
    # whose candidate was already accepted (e.g. from the Review panel) returns that ACCEPTED record. Echo the
    # candidate's current acceptance status back so the caller never has to re-accept and is never stranded:
    # an already-accepted REVIEW reports requires_acceptance=False (ready to assemble), not a fresh gate.
    gen = generate_review_candidate(store_root, customer_project_id, job_id, at=at, by=by,
                                    uploaded_corpus_auto_optin=uploaded_corpus_auto_optin)
    tier = gen.get("tier")
    if tier in (TIER_REVIEW, TIER_AUTO):
        _advance_to(store_root, customer_project_id, job_id, PLACED,
                    at=at, by=by, reason="workflow: uploaded-corpus engine redline placed")
        is_auto = tier == TIER_AUTO
        review_status = (gen.get("record") or {}).get("status")
        review_accepted = review_status == STATUS_REVIEW_ACCEPTED
        review_rejected = review_status == STATUS_REVIEW_REJECTED
        # SUPERSEDED: the human corrected this candidate via a source-anchor render — the redline is placed
        # (human-confirmed) and needs no acceptance, exactly like an accepted candidate.
        review_superseded = review_status == STATUS_REVIEW_SUPERSEDED
        return {
            "path": PATH_UPLOADED_AUTO if is_auto else PATH_UPLOADED_REVIEW,
            "runnable": True, "rendered": True,
            "provenance": PROVENANCE_DETERMINISTIC_AUTO if is_auto else PROVENANCE_REVIEW_CANDIDATE,
            "recognized_corpus_id": None, "deterministic_log_id": None,
            "candidate_id": gen.get("candidate_id"), "review": gen, "bundle": gen.get("bundle"),
            # An AUTO render needs no acceptance; a REVIEW needs it ONLY while still pending (not yet accepted
            # and not superseded by a human correction).
            "requires_acceptance": (not is_auto) and not review_accepted and not review_superseded,
            "review_status": review_status, "review_accepted": review_accepted,
            "review_rejected": review_rejected, "review_superseded": review_superseded, "blockers": [],
        }

    # --- Path C: abstain with SPECIFIC, preserved reasons (recognition + engine), accept stays blocked - #
    return {
        "path": PATH_ABSTAIN, "runnable": False, "rendered": False,
        "provenance": None, "recognized_corpus_id": None, "deterministic_log_id": None,
        "candidate_id": gen.get("candidate_id"), "review": gen,
        "blockers": _merge_abstain_blockers(rec_ev, gen),
    }


def _review_gate(cands) -> tuple:
    """Decide whether a job's REVIEW redline may be packaged. Only an UNRESOLVED RENDERED review (pending or
    rejected) blocks closeout. An ABSTAINED record (the engine produced NO geometry) is IGNORED: it never
    gates a later authoritative render — a job recognized as a deterministic package, or one that abstained
    and has no render at all, is not blocked here (the latter hard-blocks honestly at closeout on the missing
    manifest, which is the truthful reason). A SUPERSEDED record is also IGNORED: the human corrected the
    candidate via a source-anchor render, which is the authoritative redline now filling the slot (SUPERSEDED
    is set ONLY by a successful human-confirmed render, so ignoring it never lets a still-pending engine
    REVIEW through). A recognized/AUTO job has no review candidate -> passes. Returns
    (ok, review_status, blocker_code)."""
    resolved = (STATUS_ABSTAINED, STATUS_REVIEW_SUPERSEDED)
    statuses = [c.get("status") for c in (cands or []) if c.get("status") not in resolved]
    if not statuses:
        return True, None, None
    if all(s == STATUS_REVIEW_ACCEPTED for s in statuses):
        return True, STATUS_REVIEW_ACCEPTED, None
    if any(s == STATUS_REVIEW_REJECTED for s in statuses):
        return False, STATUS_REVIEW_REJECTED, REVIEW_WAS_REJECTED
    if any(s == STATUS_REVIEW_CANDIDATE for s in statuses):
        return False, STATUS_REVIEW_CANDIDATE, REVIEW_NOT_ACCEPTED
    return True, statuses[0], None


def export_gate(store_root, customer_project_id, job_id) -> tuple:
    """Public REVIEW-acceptance gate for the DOWNLOAD routes (export ZIP / closeout PDF), identical to the
    closeout-assembly gate so EVERY export path agrees: a job's redline may be downloaded only when its REVIEW
    is RESOLVED. A recognized DETERMINISTIC / engine AUTO job (no candidate), an ACCEPTED REVIEW, a
    human-corrected SUPERSEDED candidate, and a stale ABSTAINED record all PASS; a still-pending
    REVIEW_CANDIDATE or a REVIEW_REJECTED candidate BLOCKS — so an un-accepted or rejected dashed REVIEW is
    never downloadable. Returns (ok, blocker_code)."""
    validate_customer_project_id(customer_project_id)
    validate_job_id(job_id)
    cands = list_review_candidates(store_root, customer_project_id, job_id)
    ok, _status, code = _review_gate(cands)
    return ok, code


def assemble_closeout_package(store_root, customer_project_id, job_id, *, at, by,
                              cost_rule_set=None) -> dict:
    """Drive the closeout/export chain for a job whose redline is already placed: gate on REVIEW acceptance,
    advance the job to CLOSEOUT_REVIEW, evaluate the closeout + KMZ-export safety, optionally compute billing
    (only when a server cost-rule set is supplied), and assemble the export-package descriptor. Returns a
    unified summary. Idempotent (re-running revalidates). 404 if the job is missing."""
    validate_customer_project_id(customer_project_id)
    validate_job_id(job_id)
    load_job(store_root, customer_project_id, job_id)               # exists + isolation (404)

    # Review-acceptance gate: a REVIEW redline must be human-accepted before it is packaged.
    cands = list_review_candidates(store_root, customer_project_id, job_id)
    ok, review_status, gate_code = _review_gate(cands)
    if not ok:
        return {"assembled": False, "blocker": gate_code, "review_status": review_status,
                "closeout_status": None, "export_status": None, "kmz_status": None}

    # Enter closeout review (walk PLACED -> CLOSEOUT_REVIEW; idempotent).
    _advance_to(store_root, customer_project_id, job_id, CLOSEOUT_REVIEW,
                at=at, by=by, reason="workflow: enter closeout review")

    # Closeout (server-authoritative; clean spine auto-evaluates READY_FOR_APPROVAL).
    try:
        load_closeout_review(store_root, customer_project_id, job_id)
    except CloseoutNotFoundError:
        create_closeout_review(store_root, customer_project_id, job_id, at=at, by=by)
    co = evaluate_closeout(store_root, customer_project_id, job_id, at=at, by=by)

    # Billing (snapshot-only; OPTIONAL — only computed when a server cost-rule set is configured).
    billing_view = None
    if cost_rule_set is not None:
        try:
            load_billing_summary(store_root, customer_project_id, job_id)
        except BillingSummaryNotFoundError:
            create_billing_summary(store_root, customer_project_id, job_id, at=at, by=by)
        bill = compute_billing_summary(store_root, customer_project_id, job_id,
                                       cost_rule_set=cost_rule_set, at=at, by=by)
        billing_view = billing_summary_view(bill)

    # KMZ-export safety (honest: a pixel-only redline manifest blocks; never fakes coordinates).
    kmz = evaluate_export(store_root, customer_project_id, job_id)

    # Export-package descriptor (references the redline manifest + artifacts; KMZ included only if EXPORTABLE).
    try:
        load_export_package(store_root, customer_project_id, job_id)
    except ExportPackageNotFoundError:
        create_export_package(store_root, customer_project_id, job_id, at=at, by=by)
    pkg = assemble_export_package(store_root, customer_project_id, job_id, at=at, by=by)
    pkg_view = export_package_view(pkg)

    return {
        "assembled": True, "blocker": None, "review_status": review_status,
        "closeout_status": co["status"], "closeout_summary": closeout_summary(co),
        "kmz_status": kmz.get("status"), "kmz_geometry_basis": kmz.get("geometry_basis"),
        "kmz_blockers": [b.get("code") for b in (kmz.get("blockers") or [])],
        "export_status": pkg["status"], "export_view": pkg_view,
        "billing_view": billing_view,
    }
