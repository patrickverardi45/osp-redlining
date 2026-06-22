"""Permanent v2 product foundation — uploaded-corpus engine-handoff READINESS (contract-only, read-only).

Evaluates whether a processing_job's UPLOADED inputs could be handed to the TrueLine placement engine. In
this slice the answer is always NO: the engine's extraction + placement is corpus/dialect-specific (the
internal plan dialects + committed source anchors + a corpus-specific geometry solver), and no adapter
exists to consume an arbitrary uploaded plan corpus. This module RENDERS NOTHING, runs no engine, creates
no artifacts/slots, and never mutates the job — it only READS job + reviewed_bore_log state and reports the
exact named blockers. It is the honest bridge before the real (deferred) uploaded-corpus engine work.

Contract-only: no engine, no renderer, no web/backend wiring, no AI/OCR, no output bundle, no placement.
"""
from __future__ import annotations

from truelinev2.contracts.customer_project import validate_customer_project_id
from truelinev2.contracts.processing_job import load_job, validate_job_id
from truelinev2.contracts.reviewed_bore_log import is_engine_ready, list_reviewed_bore_logs

PLAN_PDF_KIND = "PLAN_PDF"
STATUS_BLOCKED = "BLOCKED"

# Capability blockers — ALWAYS present in this slice (no uploaded-corpus engine adapter exists).
UPLOADED_CORPUS_NOT_IMPLEMENTED = "ENGINE_HANDOFF_NOT_IMPLEMENTED_FOR_UPLOADED_CORPUS"
NO_PLAN_DIALECT = "NO_PLAN_DIALECT_FOR_UPLOADED_CONVENTION"
NO_SOURCE_ANCHORS = "NO_SOURCE_ANCHORS_FOR_UPLOADED_CORPUS"
GEOMETRY_SOLVER_CORPUS_SPECIFIC = "GEOMETRY_SOLVER_IS_CORPUS_SPECIFIC"

# Input-readiness blockers — conditional on the job's uploaded inputs.
NO_PLAN_PDF_UPLOAD = "NO_PLAN_PDF_UPLOAD"
NO_ENGINE_READY_REVIEWED_BORE_LOG = "NO_ENGINE_READY_REVIEWED_BORE_LOG"

_CAPABILITY_BLOCKERS = (
    (UPLOADED_CORPUS_NOT_IMPLEMENTED, "Uploaded-corpus engine adapter is not implemented yet."),
    (NO_PLAN_DIALECT, "No plan dialect recognizes an arbitrary uploaded plan convention "
                      "(only the internal corpus dialects exist)."),
    (NO_SOURCE_ANCHORS, "No source anchors / parent-source model exist for an uploaded corpus."),
    (GEOMETRY_SOLVER_CORPUS_SPECIFIC, "The redline geometry solver is corpus-specific; it cannot place "
                                      "redlines from station strings alone."),
)


def evaluate_engine_handoff_readiness(store_root, customer_project_id, job_id) -> dict:
    """Read-only readiness evaluation for an uploaded-corpus engine handoff. Loads the job (must exist and
    be in-scope), inspects its uploads + reviewed_bore_logs, and returns a status + named blockers. Always
    ``BLOCKED`` / ``runnable: False`` in this slice. Renders nothing; mutates nothing; creates no
    slots/artifacts/bundles. Raises the job/project contract errors (NotFound -> 404 upstream)."""
    validate_customer_project_id(customer_project_id)
    validate_job_id(job_id)
    job = load_job(store_root, customer_project_id, job_id)            # exists + isolation

    has_plan_pdf = any(u.get("kind") == PLAN_PDF_KIND for u in job.get("uploads", []))
    rbls = list_reviewed_bore_logs(store_root, customer_project_id, job_id)
    has_engine_ready = any(is_engine_ready(rbl) for rbl in rbls)

    blockers = [{"code": code, "reason": reason} for code, reason in _CAPABILITY_BLOCKERS]
    if not has_plan_pdf:
        blockers.append({"code": NO_PLAN_PDF_UPLOAD,
                         "reason": "Job has no PLAN_PDF upload to use as the plan corpus."})
    if not has_engine_ready:
        blockers.append({"code": NO_ENGINE_READY_REVIEWED_BORE_LOG,
                         "reason": "Job has no reviewed_bore_log that has passed the engine-readiness gate."})

    return {
        "status": STATUS_BLOCKED,
        "runnable": False,
        "checks": {
            "has_plan_pdf": has_plan_pdf,
            "has_engine_ready_reviewed_bore_log": has_engine_ready,
        },
        "blockers": blockers,
    }
