"""Permanent v2 product foundation — the manifest_handoff engine-output attachment (contract-only).

After a processing_job's reviewed_bore_log gate is engine-ready and the TrueLine PLACEMENT ENGINE produces
an output bundle (a redline_manifest + final artifacts), this lane records the HANDOFF and — only when the
gate is ready AND the bundle validates + durably stores — attaches content-addressed `redline_manifest`
and `artifact_bundle` references to the job's output slots.

This is NOT engine execution, rendering, or export: the engine output bundle is a GIVEN input. All
validation + durable storage REUSES the existing published-bundle machinery (`store_bundle`, which runs
`admission_errors` then content-keys + copies the bundle into a job-scoped durable store); no new validator
is introduced. Output slots are set via the existing `processing_job.set_output_slot` (unchanged). A
handoff that is REJECTED (gate not ready) or FAILED (bundle invalid) leaves the job's output slots
UNTOUCHED, and every terminal handoff is immutable. The term "engine" here refers ONLY to the placement
engine (`engine_run_id` / `engine_run_status`), never to an AI/OCR/extraction provider.

Contract-only: no engine execution, renderer, web/backend, AI/OCR, KMZ/KML, billing/closeout, or deploy.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from truelinev2.contracts.customer_project import assert_same_project, validate_customer_project_id
from truelinev2.contracts.processing_job import (
    job_dir,
    load_job,
    set_output_slot,
    validate_job_id,
)
from truelinev2.contracts.reviewed_bore_log import (
    is_engine_ready,
    load_reviewed_bore_log,
    validate_reviewed_bore_log_id,
)
from truelinev2.contracts.published_bundle import MANIFEST_FILENAME
from truelinev2.contracts.published_bundle_store import (
    BUNDLES_SUBDIR,
    BundleImmutableError,
    BundleRejectedError,
    StoreError,
    store_bundle,
)

HANDOFF_RECORD_FORMAT = "trueline-manifest-handoff-1"
HANDOFFS_SUBDIR = "handoffs"
HANDOFF_FILENAME = "_manifest_handoff.json"
BUNDLE_STORE_SUBDIR = "bundle_store"   # job-scoped durable store root for validated engine outputs

_ENGINE_RUN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")

# handoff state machine — ATTEMPTED is the only non-terminal state.
ATTEMPTED = "ATTEMPTED"
SUCCEEDED = "SUCCEEDED"
FAILED = "FAILED"
REJECTED = "REJECTED"
HANDOFF_STATUSES = (ATTEMPTED, SUCCEEDED, FAILED, REJECTED)
TERMINAL_STATUSES = (SUCCEEDED, FAILED, REJECTED)

# Output slots this lane may attach (NEVER export_package).
MANIFEST_SLOT = "redline_manifest"
ARTIFACT_BUNDLE_SLOT = "artifact_bundle"

VALIDATION_VALIDATED = "VALIDATED"


class ManifestHandoffError(ValueError):
    """Base manifest_handoff error."""


class InvalidEngineRunIdError(ManifestHandoffError):
    """engine_run_id is missing or not filesystem/URL-safe."""


class HandoffNotFoundError(ManifestHandoffError):
    """No stored handoff record for the requested engine_run_id."""


class HandoffStateError(ManifestHandoffError):
    """Operation not permitted in the handoff's current state (e.g. re-finalizing a terminal handoff)."""


def validate_engine_run_id(engine_run_id) -> str:
    if not isinstance(engine_run_id, str) or not _ENGINE_RUN_ID_RE.match(engine_run_id):
        raise InvalidEngineRunIdError(
            "engine_run_id must match %s (got %r)" % (_ENGINE_RUN_ID_RE.pattern, engine_run_id))
    return engine_run_id


def _handoff_dir(store_root, customer_project_id, processing_job_id, engine_run_id) -> Path:
    validate_engine_run_id(engine_run_id)
    return (job_dir(store_root, customer_project_id, processing_job_id)
            / HANDOFFS_SUBDIR / engine_run_id)


def _handoff_path(store_root, customer_project_id, processing_job_id, engine_run_id) -> Path:
    return _handoff_dir(store_root, customer_project_id, processing_job_id,
                        engine_run_id) / HANDOFF_FILENAME


def record_handoff_attempt(store_root, customer_project_id, processing_job_id, reviewed_bore_log_id,
                           engine_run_id, *, engine_run_status, at, by, warnings=None) -> dict:
    """Record an engine-output handoff attempt (status ATTEMPTED). Verifies the job + reviewed_bore_log
    exist and are in-scope; rejects a duplicate engine_run_id (no silent overwrite). `engine_run_status`
    is the placement engine's opaque self-reported run status (runtime data). Returns the record."""
    validate_customer_project_id(customer_project_id)
    validate_job_id(processing_job_id)
    validate_reviewed_bore_log_id(reviewed_bore_log_id)
    validate_engine_run_id(engine_run_id)
    if not isinstance(engine_run_status, str) or not engine_run_status:
        raise ManifestHandoffError("engine_run_status must be a non-empty string")
    load_job(store_root, customer_project_id, processing_job_id)                # exists + isolation
    load_reviewed_bore_log(store_root, customer_project_id, processing_job_id,  # exists + in-scope
                           reviewed_bore_log_id)
    path = _handoff_path(store_root, customer_project_id, processing_job_id, engine_run_id)
    if path.exists():
        raise ManifestHandoffError("handoff already exists for engine_run_id %r" % (engine_run_id,))
    handoff = {
        "record_format": HANDOFF_RECORD_FORMAT,
        "engine_run_id": engine_run_id,
        "customer_project_id": customer_project_id,
        "processing_job_id": processing_job_id,
        "reviewed_bore_log_id": reviewed_bore_log_id,
        "status": ATTEMPTED,
        "engine_run_status": engine_run_status,
        "summary_counts": None,
        "warnings": list(warnings or []),
        "errors": [],
        "manifest_attachment": None,
        "artifact_bundle_attachment": None,
        "audit": [{"action": "handoff_attempted", "at": at, "by": by,
                   "from": None, "to": ATTEMPTED, "reason": None}],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(handoff, indent=2) + "\n", encoding="utf-8")
    return handoff


def load_handoff(store_root, customer_project_id, processing_job_id, engine_run_id) -> dict:
    path = _handoff_path(store_root, customer_project_id, processing_job_id, engine_run_id)
    if not path.is_file():
        raise HandoffNotFoundError(
            "no handoff for %s/%s/%s" % (customer_project_id, processing_job_id, engine_run_id))
    handoff = json.loads(path.read_text(encoding="utf-8"))
    assert_same_project(customer_project_id, handoff.get("customer_project_id"))
    return handoff


def write_handoff(store_root, handoff) -> str:
    """Persist a handoff under its OWN (cp, job, engine_run) scope (derived from the record)."""
    cp = validate_customer_project_id(handoff["customer_project_id"])
    jid = validate_job_id(handoff["processing_job_id"])
    rid = validate_engine_run_id(handoff["engine_run_id"])
    path = _handoff_path(store_root, cp, jid, rid)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(handoff, indent=2) + "\n", encoding="utf-8")
    return str(path)


def _terminate(store_root, handoff, status, *, at, by, reason) -> dict:
    handoff["status"] = status
    handoff["audit"].append({"action": "handoff_finalized", "at": at, "by": by,
                             "from": ATTEMPTED, "to": status, "reason": reason})
    write_handoff(store_root, handoff)
    return handoff


def finalize_handoff(store_root, customer_project_id, processing_job_id, engine_run_id, bundle_root,
                     *, at, by, schema=None) -> dict:
    """Finalize a handoff. SUCCEEDS only when BOTH (a) the referenced reviewed_bore_log is engine-ready
    AND (b) the engine output bundle validates + durably stores via `store_bundle`. On success, attaches
    content-addressed `redline_manifest` + `artifact_bundle` references (pointing at the durably stored,
    content-keyed bundle) to the job's output slots and returns the SUCCEEDED record. Gate-fail returns
    REJECTED; bundle-invalid returns FAILED — both leave the job's output slots UNTOUCHED. A terminal
    handoff cannot be re-finalized (raises HandoffStateError)."""
    handoff = load_handoff(store_root, customer_project_id, processing_job_id, engine_run_id)
    if handoff["status"] in TERMINAL_STATUSES:
        raise HandoffStateError(
            "handoff %r is terminal (%s); cannot re-finalize" % (engine_run_id, handoff["status"]))

    # (a) gate: the reviewed_bore_log must be engine-ready.
    rbl = load_reviewed_bore_log(store_root, customer_project_id, processing_job_id,
                                 handoff["reviewed_bore_log_id"])
    if not is_engine_ready(rbl):
        handoff["errors"].append(
            "reviewed_bore_log %r is not engine-ready" % handoff["reviewed_bore_log_id"])
        return _terminate(store_root, handoff, REJECTED, at=at, by=by,
                          reason="reviewed_bore_log not engine-ready")

    # (b) validate + durably store the engine output bundle (reuses admission_errors via store_bundle).
    bundle_store_root = (job_dir(store_root, customer_project_id, processing_job_id)
                         / BUNDLE_STORE_SUBDIR)
    try:
        result = store_bundle(bundle_root, bundle_store_root, schema=schema, created_at=at)
    except (BundleRejectedError, BundleImmutableError, StoreError) as exc:
        handoff["errors"].append("bundle validation/store failed: %s" % exc)
        return _terminate(store_root, handoff, FAILED, at=at, by=by,
                          reason="bundle validation/store failed")

    meta = result["meta"]
    bundle_id = result["bundle_id"]
    manifest_sha256 = meta["manifest_sha256"]
    summary = meta.get("summary", {})

    manifest_attachment = {
        "manifest_id": manifest_sha256,
        "manifest_filename": MANIFEST_FILENAME,
        "manifest_sha256": manifest_sha256,
        "bundle_id": bundle_id,
        "store_relative_path": "%s/%s/%s" % (BUNDLES_SUBDIR, bundle_id, MANIFEST_FILENAME),
        "source_engine_run_id": engine_run_id,
        "summary_counts": summary,
        "validation_status": VALIDATION_VALIDATED,
    }
    artifact_bundle_attachment = {
        "bundle_id": bundle_id,
        "bundle_format": meta.get("store_format"),
        "store_relative_path": "%s/%s/" % (BUNDLES_SUBDIR, bundle_id),
        "manifest_sha256": manifest_sha256,
        "source_manifest_id": manifest_sha256,
        "source_engine_run_id": engine_run_id,
        "artifact_count": meta.get("artifact_count"),
        "total_bytes": meta.get("total_bytes"),
        "validation_status": VALIDATION_VALIDATED,
    }

    # Attach ONLY after validation passes; reuse set_output_slot (rejects unknown slots, job-scoped).
    set_output_slot(store_root, customer_project_id, processing_job_id,
                    MANIFEST_SLOT, manifest_attachment, at=at, by=by)
    set_output_slot(store_root, customer_project_id, processing_job_id,
                    ARTIFACT_BUNDLE_SLOT, artifact_bundle_attachment, at=at, by=by)

    handoff["summary_counts"] = summary
    handoff["manifest_attachment"] = manifest_attachment
    handoff["artifact_bundle_attachment"] = artifact_bundle_attachment
    return _terminate(store_root, handoff, SUCCEEDED, at=at, by=by, reason="validated + attached")
