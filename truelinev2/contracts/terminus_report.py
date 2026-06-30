"""G3 — read-only TERMINUS EVIDENCE REPORT (DISPLAY-only observer; no placement impact).

Surfaces the source-backed per-bore terminus evidence (G1 schema / G2 extractor) for a stored product job so
the REVIEW flow can show, for each bore endpoint: is it source-bound or only known from the bore-log row,
what source type supports it, what station was read, what sheet/printed text supports it, what named blocker
explains missing evidence, and what provenance/confidence applies.

This is a SEPARATE read path. It RUNS no engine, RENDERS nothing, sets no slot, writes no file, and advances
no job — it only resolves a job's already-stored PLAN_PDF + bore-log uploads from disk and drives the
read-only observer ``extract_termini``. It is DELIBERATELY not part of the placement orchestrator
(``product_workflow``) nor the uploaded-corpus engine handoff, so it can never change a placement, its status,
AUTO, the renderer, or the deterministic frontier.

Honesty rules (inherited from the terminus model):
  * the displayed bore set mirrors the engine's consideration set — one terminus entry per ENGINE-READY
    reviewed bore-log (the same gate the REVIEW candidate uses), so the panel matches what the engine placed;
  * a missing input is reported as a NAMED blocker (mirroring the uploaded-corpus engine vocabulary), never
    an invented endpoint and never a silent empty;
  * the per-endpoint source_bound / blocker honesty comes straight from ``extract_termini`` unchanged.

Name-free: no customer/project/location/operator literal lives here.
"""
from __future__ import annotations

from truelinev2.contracts.customer_project import validate_customer_project_id
from truelinev2.contracts.processing_job import job_dir, load_job, validate_job_id
from truelinev2.contracts.reviewed_bore_log import is_engine_ready, list_reviewed_bore_logs
from truelinev2.extract.terminus_extractor import extract_termini

# Canonical upload kind for a plan PDF (mirrors the repo-wide literal; reviewed_bore_log defines its own
# BORE_LOG_UPLOAD_KIND the same way rather than importing, so this module stays decoupled + lightweight).
PLAN_PDF_KIND = "PLAN_PDF"

# Report statuses (a DISPLAY verdict, never a placement status).
STATUS_EVALUATED = "EVALUATED"      # the observer ran and produced >= 1 bore's terminus evidence
STATUS_NO_INPUTS = "NO_INPUTS"      # the job has no usable plan + engine-ready bore-log to read termini from

# Named missing-input blockers (mirror the uploaded-corpus engine handoff vocabulary so the UI copy is shared).
NO_PLAN_PDF_UPLOAD = "NO_PLAN_PDF_UPLOAD"
PLAN_PDF_FILE_NOT_AVAILABLE = "PLAN_PDF_FILE_NOT_AVAILABLE"
NO_ENGINE_READY_REVIEWED_BORE_LOG = "NO_ENGINE_READY_REVIEWED_BORE_LOG"
BORE_LOG_FILE_NOT_AVAILABLE = "BORE_LOG_FILE_NOT_AVAILABLE"


def _blocker(code, reason) -> dict:
    return {"code": code, "reason": reason}


def terminus_evidence_report(store_root, customer_project_id, job_id) -> dict:
    """Read a job's stored plan + bore-log uploads and return source-backed terminus evidence for DISPLAY.

    For every ENGINE-READY reviewed bore-log in the job, resolve its source BORE_LOG file + the job's PLAN_PDF
    and call the read-only observer ``extract_termini`` once, collecting one ``BoreTerminusEvidence`` per bore.
    Honest NAMED blockers are reported when the plan or an engine-ready bore-log is missing/unavailable.

    Pure read: validates ids, loads the job (404 + tenant isolation), and reads files only. Never writes,
    renders, runs the engine, advances the job, or touches any slot. Returns::

        {"job_id", "status", "runnable", "plan_present", "termini": [...], "blockers": [...]}

    where each ``termini`` entry is
    ``{"reviewed_bore_log_id", "source_upload_id", "evidence": <BoreTerminusEvidence.as_dict()>}``.
    """
    validate_customer_project_id(customer_project_id)
    validate_job_id(job_id)
    job = load_job(store_root, customer_project_id, job_id)          # exists + isolation (404)
    jd = job_dir(store_root, customer_project_id, job_id)
    uploads = job.get("uploads") or []
    blockers = []

    # --- resolve the plan PDF (one per job; the first PLAN_PDF, mirroring the engine handoff) --------------- #
    plan_upload = next((u for u in uploads if u.get("kind") == PLAN_PDF_KIND), None)
    plan_path = None
    if plan_upload is None:
        blockers.append(_blocker(NO_PLAN_PDF_UPLOAD,
                                 "Job has no plan PDF upload to read endpoint evidence from."))
    else:
        candidate = jd / (plan_upload.get("stored_path") or "")
        if candidate.is_file():
            plan_path = candidate
        else:
            blockers.append(_blocker(PLAN_PDF_FILE_NOT_AVAILABLE,
                                     "The plan PDF upload is recorded but its file is not on disk."))

    # --- resolve the bore set: one ENGINE-READY reviewed bore-log per bore (mirrors the REVIEW candidate) --- #
    ready = [r for r in list_reviewed_bore_logs(store_root, customer_project_id, job_id) if is_engine_ready(r)]
    if not ready:
        blockers.append(_blocker(NO_ENGINE_READY_REVIEWED_BORE_LOG,
                                 "No engine-ready reviewed bore-log; there is no bore to read termini for yet."))

    uploads_by_id = {u.get("upload_id"): u for u in uploads}
    termini = []
    for rbl in ready:
        src = uploads_by_id.get(rbl.get("source_upload_id"))
        bore_path = None
        if src is not None:
            candidate = jd / (src.get("stored_path") or "")
            if candidate.is_file():
                bore_path = candidate
        if bore_path is None:
            blockers.append(_blocker(
                BORE_LOG_FILE_NOT_AVAILABLE,
                "Reviewed bore-log %r has no readable source bore-log file." % rbl.get("reviewed_bore_log_id")))
            continue
        if plan_path is None:
            continue                                                # plan already reported missing above
        evidence = extract_termini(plan_path, bore_path)            # read-only observer; no engine/render
        termini.append({
            "reviewed_bore_log_id": rbl.get("reviewed_bore_log_id"),
            "source_upload_id": rbl.get("source_upload_id"),
            "evidence": evidence.as_dict(),
        })

    return {
        "job_id": job_id,
        "status": STATUS_EVALUATED if termini else STATUS_NO_INPUTS,
        "runnable": bool(termini),
        "plan_present": plan_path is not None,
        "termini": termini,
        "blockers": blockers,
    }
