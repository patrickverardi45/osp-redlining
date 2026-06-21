"""Permanent v2 product foundation — the export_package versioned closeout model (contract-only).

ONE durable, versioned, reproducible closeout export package per processing_job, ASSEMBLED from trusted
product outputs by REFERENCE — it never invents truth, never recomputes a downstream contract, and never
renders a document. The v1 monolith's closeout packet was a browser `document.write` print with blob URLs,
no stored artifact, no versioning, no audit (salvage audit 6a/6b → DO-NOT-COPY 10). v2 fixes this with a
durable, content-addressed package DESCRIPTOR: a manifest of references to trusted sources, each carrying a
content hash where available, plus a reproducible `package_content_hash`.

This is a DESCRIPTOR / manifest-of-references, NOT a rendered document — no PDF/HTML/binary is generated
here ("no generated fake export files"); byte-level rendering is a later lane. Each item references existing
trusted state and is gated:
  * redline manifest + artifacts: included only from the VALIDATED, sha256-verified durable manifest (after
    a validated manifest handoff); artifacts are manifest-backed only.
  * KMZ: included ONLY when `kmz_export.evaluate_export` permits verified geospatial geometry (EXPORTABLE);
    a pixel/PDF-only manifest safely OMITS KMZ with a warning and does NOT block the rest of the package.
  * reviewed bore-log: included only when the review gate is engine-eligible.
  * closeout review: controls package readiness/finality (READY needs closeout ≥ READY_FOR_APPROVAL; FINAL
    needs APPROVED) — there is no package-approve action.
  * billing summary: included ONLY as a snapshot/reference; never recomputed here.

Status is server-authoritative and DERIVED (DRAFT/BLOCKED/ASSEMBLED/READY/FINAL); no client/UI value
survives a reassemble. Regeneration appends an audited revision when the trusted references change (prior
superseded, retained); an unchanged reassemble revalidates idempotently. On a successful assemble the job's
`export_package` output slot is set to a REFERENCE to this record (after the record is written) — it does
NOT transition the job lifecycle, mark the job complete, imply delivery, or override closeout/billing.
Contract-only: no engine execution, renderer, web/backend, AI/OCR, document rendering, or deploy.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from truelinev2.contracts.customer_project import assert_same_project, validate_customer_project_id
from truelinev2.contracts.processing_job import (
    CLOSED as JOB_CLOSED,
    CLOSEOUT_REVIEW as JOB_CLOSEOUT_REVIEW,
    PLACED as JOB_PLACED,
    job_dir,
    load_job,
    set_output_slot,
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
    ReviewedBoreLogError,
    is_engine_ready,
    load_reviewed_bore_log,
)
from truelinev2.contracts.closeout_review import (
    APPROVED as CO_APPROVED,
    CLOSED as CO_CLOSED,
    LOCKED as CO_LOCKED,
    OPEN_ENGINE_BLOCKERS as CO_OPEN_ENGINE_BLOCKERS,
    READY_FOR_APPROVAL as CO_READY_FOR_APPROVAL,
    CloseoutNotFoundError,
    load_closeout_review,
)
from truelinev2.contracts.kmz_export import (
    EXPORTABLE as KMZ_EXPORTABLE,
    evaluate_export as evaluate_kmz_export,
)
from truelinev2.contracts.billing_summary import (
    FINAL as BILLING_FINAL,
    BillingSummaryNotFoundError,
    load_billing_summary,
)

EXPORT_PACKAGE_RECORD_FORMAT = "trueline-export-package-1"
EXPORT_PACKAGE_FILENAME = "_export_package.json"   # ONE record per job (singleton)
EXPORT_PACKAGE_SLOT = "export_package"             # the job output slot this lane produces

# Server-authoritative package status (record level). `superseded` lives only on a revision.
DRAFT = "DRAFT"
BLOCKED = "BLOCKED"
ASSEMBLED = "ASSEMBLED"      # built from trusted inputs, closeout below the READY_FOR_APPROVAL threshold
READY = "READY"             # assembled + closeout >= READY_FOR_APPROVAL (preview/internal-grade)
FINAL = "FINAL"             # assembled + closeout APPROVED/CLOSED (share/billing-grade)
PACKAGE_STATUSES = (DRAFT, BLOCKED, ASSEMBLED, READY, FINAL)

# A job is closeout-packageable only once it has (or had) a placed redline output.
CLOSEOUT_ELIGIBLE_JOB_STATES = (JOB_PLACED, JOB_CLOSEOUT_REVIEW, JOB_CLOSED)
# Closeout states that permit package READY (generation) and FINAL (share-grade), per contract §8.
CLOSEOUT_READY_STATES = (CO_READY_FOR_APPROVAL, CO_LOCKED, CO_APPROVED, CO_CLOSED)
CLOSEOUT_APPROVED_STATES = (CO_APPROVED, CO_CLOSED)

# Package sections (only those with a v2 trusted source; §8 sections lacking a v2 source are deferred,
# never faked). Fixed order -> a stable, reproducible descriptor.
JOB_SUMMARY = "JOB_SUMMARY"
REVIEWED_BORE_LOG = "REVIEWED_BORE_LOG"
REDLINE_MANIFEST = "REDLINE_MANIFEST"
REDLINE_ARTIFACTS = "REDLINE_ARTIFACTS"
KMZ_EXPORT = "KMZ_EXPORT"
CLOSEOUT_REVIEW = "CLOSEOUT_REVIEW"
BILLING_SUMMARY = "BILLING_SUMMARY"
PACKAGE_SECTIONS = (JOB_SUMMARY, REVIEWED_BORE_LOG, REDLINE_MANIFEST, REDLINE_ARTIFACTS,
                    KMZ_EXPORT, CLOSEOUT_REVIEW, BILLING_SUMMARY)

# Item kinds + inclusion state.
REFERENCE = "REFERENCE"
SNAPSHOT_REF = "SNAPSHOT_REF"
ARTIFACT_REF = "ARTIFACT_REF"
INCLUDED = "INCLUDED"
OMITTED = "OMITTED"

# HARD blocker codes (any present => BLOCKED; never READY/FINAL).
JOB_NOT_IN_CLOSEOUT_RANGE = "JOB_NOT_IN_CLOSEOUT_RANGE"
MISSING_MANIFEST = "MISSING_MANIFEST"
MISSING_ARTIFACT_BUNDLE = "MISSING_ARTIFACT_BUNDLE"
UNTRUSTED_OUTPUT = "UNTRUSTED_OUTPUT"
MANIFEST_NOT_RESOLVABLE = "MANIFEST_NOT_RESOLVABLE"
REVIEWED_BORE_LOG_NOT_READY = "REVIEWED_BORE_LOG_NOT_READY"
HARD_BLOCKER_CODES = (JOB_NOT_IN_CLOSEOUT_RANGE, MISSING_MANIFEST, MISSING_ARTIFACT_BUNDLE,
                      UNTRUSTED_OUTPUT, MANIFEST_NOT_RESOLVABLE, REVIEWED_BORE_LOG_NOT_READY)

# READINESS blocker codes (allow ASSEMBLED, prevent READY): closeout below the generation threshold.
CLOSEOUT_NOT_READY = "CLOSEOUT_NOT_READY"
CLOSEOUT_REVIEW_MISSING = "CLOSEOUT_REVIEW_MISSING"
READINESS_BLOCKER_CODES = (CLOSEOUT_NOT_READY, CLOSEOUT_REVIEW_MISSING)

# FINALIZATION blocker codes (allow READY, prevent FINAL): closeout not yet APPROVED.
CLOSEOUT_NOT_APPROVED = "CLOSEOUT_NOT_APPROVED"
FINALIZATION_BLOCKER_CODES = (CLOSEOUT_NOT_APPROVED,)

# WARNING codes (recorded; never block). OPEN_ENGINE_BLOCKERS is closeout-owned (visibility only).
KMZ_NOT_INCLUDED = "KMZ_NOT_INCLUDED"
BILLING_NOT_FINAL = "BILLING_NOT_FINAL"
BILLING_SUMMARY_MISSING = "BILLING_SUMMARY_MISSING"
REVIEWED_BORE_LOG_NOT_RESOLVABLE = "REVIEWED_BORE_LOG_NOT_RESOLVABLE"
OPEN_ENGINE_BLOCKERS = "OPEN_ENGINE_BLOCKERS"
WARNING_CODES = (KMZ_NOT_INCLUDED, BILLING_NOT_FINAL, BILLING_SUMMARY_MISSING,
                 REVIEWED_BORE_LOG_NOT_RESOLVABLE, OPEN_ENGINE_BLOCKERS)


class ExportPackageError(ValueError):
    """Base export_package error."""


class ExportPackageNotFoundError(ExportPackageError):
    """No stored export_package for the requested job."""


# --------------------------------------------------------------------------- #
# Storage (singleton per job).
# --------------------------------------------------------------------------- #
def export_package_path(store_root, customer_project_id, processing_job_id) -> Path:
    return job_dir(store_root, customer_project_id, processing_job_id) / EXPORT_PACKAGE_FILENAME


def create_export_package(store_root, customer_project_id, processing_job_id, *, at, by) -> dict:
    """Create the ONE export_package for a job (status DRAFT, no revision yet). Verifies the job exists and
    is in-scope. Raises on a duplicate (no silent overwrite). Returns the record."""
    validate_customer_project_id(customer_project_id)
    validate_job_id(processing_job_id)
    load_job(store_root, customer_project_id, processing_job_id)          # exists + isolation
    path = export_package_path(store_root, customer_project_id, processing_job_id)
    if path.exists():
        raise ExportPackageError(
            "export_package already exists for %s/%s" % (customer_project_id, processing_job_id))
    record = {
        "record_format": EXPORT_PACKAGE_RECORD_FORMAT,
        "customer_project_id": customer_project_id,
        "processing_job_id": processing_job_id,
        "status": DRAFT,
        "gate": None,
        "current_revision_id": None,
        "revisions": [],
        "audit": [{"action": "export_package_created", "from": None, "to": DRAFT,
                   "at": at, "by": by, "reason": None}],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def load_export_package(store_root, customer_project_id, processing_job_id) -> dict:
    path = export_package_path(store_root, customer_project_id, processing_job_id)
    if not path.is_file():
        raise ExportPackageNotFoundError(
            "no export_package for %s/%s" % (customer_project_id, processing_job_id))
    record = json.loads(path.read_text(encoding="utf-8"))
    assert_same_project(customer_project_id, record.get("customer_project_id"))
    return record


def write_export_package(store_root, record) -> str:
    """Persist a record under its OWN (cp, job) scope (derived from the record, not ambient)."""
    cp = validate_customer_project_id(record["customer_project_id"])
    jid = validate_job_id(record["processing_job_id"])
    path = export_package_path(store_root, cp, jid)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return str(path)


# --------------------------------------------------------------------------- #
# Trusted-source resolution + descriptor assembly.
# --------------------------------------------------------------------------- #
def _item(section, kind, status, *, source_ref=None, sha256=None, reason=None):
    return {"section": section, "kind": kind, "status": status,
            "source_ref": source_ref, "sha256": sha256, "reason": reason}


def _resolve_manifest(store_root, cp, job_id, job, hard):
    """Resolve the VALIDATED, sha256-verified durable manifest from the trusted output slots. Appends hard
    blockers; returns (manifest|None, m_ref, b_ref)."""
    slots = job.get("slots") or {}
    m_slot, b_slot = slots.get("redline_manifest"), slots.get("artifact_bundle")
    m_ref = (m_slot or {}).get("ref") or {}
    b_ref = (b_slot or {}).get("ref") or {}
    if not m_slot:
        hard.append({"code": MISSING_MANIFEST, "reason": "job has no redline_manifest output slot"})
    if not b_slot:
        hard.append({"code": MISSING_ARTIFACT_BUNDLE, "reason": "job has no artifact_bundle output slot"})
    if not (m_slot and b_slot):
        return None, m_ref, b_ref
    if not (m_ref.get("validation_status") == VALIDATION_VALIDATED
            and b_ref.get("validation_status") == VALIDATION_VALIDATED):
        hard.append({"code": UNTRUSTED_OUTPUT, "reason": "an output slot is not %s" % VALIDATION_VALIDATED})
        return None, m_ref, b_ref
    bundle_id = b_ref.get("bundle_id")
    bundle_root = (job_dir(store_root, cp, job_id) / BUNDLE_STORE_SUBDIR / BUNDLES_SUBDIR / str(bundle_id))
    mpath = bundle_root / MANIFEST_FILENAME
    if not (mpath.is_file() and sha256_file(mpath) == m_ref.get("manifest_sha256")):
        hard.append({"code": MANIFEST_NOT_RESOLVABLE,
                     "reason": "stored manifest missing or sha256 mismatch for bundle %r" % bundle_id})
        return None, m_ref, b_ref
    return load_manifest(bundle_root), m_ref, b_ref


def _assemble(store_root, cp, job_id):
    """Resolve trusted sources into a descriptor. Returns (gate, ordered items, source_refs)."""
    hard, readiness, finalization, warnings = [], [], [], []
    by_section, source_refs = {}, {}

    job = load_job(store_root, cp, job_id)
    if job["status"] not in CLOSEOUT_ELIGIBLE_JOB_STATES:
        hard.append({"code": JOB_NOT_IN_CLOSEOUT_RANGE,
                     "reason": "job status %r not in %r" % (job["status"], CLOSEOUT_ELIGIBLE_JOB_STATES)})
    by_section[JOB_SUMMARY] = _item(JOB_SUMMARY, REFERENCE, INCLUDED,
                                    source_ref={"job_id": job_id, "status": job["status"]})

    manifest, m_ref, b_ref = _resolve_manifest(store_root, cp, job_id, job, hard)
    if manifest is not None:
        bundle_id, manifest_sha = b_ref.get("bundle_id"), m_ref.get("manifest_sha256")
        source_refs["redline_manifest"] = {"bundle_id": bundle_id, "manifest_sha256": manifest_sha}
        source_refs["artifact_bundle"] = {"bundle_id": bundle_id, "validation_status": VALIDATION_VALIDATED}
        by_section[REDLINE_MANIFEST] = _item(
            REDLINE_MANIFEST, REFERENCE, INCLUDED,
            source_ref={"bundle_id": bundle_id, "manifest_sha256": manifest_sha}, sha256=manifest_sha)
        arts = sorted((a.get("path"), a.get("sha256"))
                      for lg in manifest.get("logs", []) for a in (lg.get("artifacts") or []))
        arts_digest = hashlib.sha256(
            json.dumps(arts, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        by_section[REDLINE_ARTIFACTS] = _item(
            REDLINE_ARTIFACTS, ARTIFACT_REF, INCLUDED,
            source_ref={"bundle_id": bundle_id, "artifact_count": len(arts)}, sha256=arts_digest)
    else:
        by_section[REDLINE_MANIFEST] = _item(REDLINE_MANIFEST, REFERENCE, OMITTED,
                                             reason="no trusted redline manifest")
        by_section[REDLINE_ARTIFACTS] = _item(REDLINE_ARTIFACTS, ARTIFACT_REF, OMITTED,
                                              reason="no trusted redline manifest")

    # Reviewed bore-log (via the manifest handoff chain; included only when engine-eligible).
    rbl = None
    engine_run_id = m_ref.get("source_engine_run_id")
    if engine_run_id:
        try:
            handoff = load_handoff(store_root, cp, job_id, engine_run_id)
            rbl = load_reviewed_bore_log(store_root, cp, job_id, handoff.get("reviewed_bore_log_id"))
        except (ManifestHandoffError, ReviewedBoreLogError):
            rbl = None
    if rbl is None:
        if manifest is not None:
            warnings.append({"code": REVIEWED_BORE_LOG_NOT_RESOLVABLE,
                             "reason": "could not resolve the reviewed_bore_log via the handoff chain"})
        by_section[REVIEWED_BORE_LOG] = _item(REVIEWED_BORE_LOG, REFERENCE, OMITTED,
                                              reason="reviewed_bore_log not resolvable")
    elif not is_engine_ready(rbl):
        hard.append({"code": REVIEWED_BORE_LOG_NOT_READY,
                     "reason": "reviewed_bore_log %r is not engine-ready" % rbl.get("reviewed_bore_log_id")})
        by_section[REVIEWED_BORE_LOG] = _item(REVIEWED_BORE_LOG, REFERENCE, OMITTED,
                                              reason="reviewed_bore_log not engine-ready")
    else:
        rbl_ref = {"reviewed_bore_log_id": rbl["reviewed_bore_log_id"], "engine_ready": True}
        source_refs["reviewed_bore_log"] = rbl_ref
        by_section[REVIEWED_BORE_LOG] = _item(REVIEWED_BORE_LOG, REFERENCE, INCLUDED, source_ref=rbl_ref)

    # KMZ (included ONLY when KMZ export safety permits verified geospatial geometry; never blocks the rest).
    if manifest is not None:
        kmz = evaluate_kmz_export(store_root, cp, job_id)
        if kmz.get("status") == KMZ_EXPORTABLE:
            kmz_ref = {"geometry_basis": kmz.get("geometry_basis"),
                       "feature_count": len(kmz.get("features", []))}
            source_refs["kmz_export"] = {**kmz_ref, "kml_sha256": kmz.get("kml_sha256")}
            by_section[KMZ_EXPORT] = _item(KMZ_EXPORT, REFERENCE, INCLUDED,
                                           source_ref=kmz_ref, sha256=kmz.get("kml_sha256"))
        else:
            codes = sorted({b["code"] for b in kmz.get("blockers", [])})
            warnings.append({"code": KMZ_NOT_INCLUDED,
                             "reason": "kmz export not safe to include (%s)" % ", ".join(codes)})
            by_section[KMZ_EXPORT] = _item(KMZ_EXPORT, REFERENCE, OMITTED,
                                           reason="kmz export blocked: %s" % ", ".join(codes))
    else:
        by_section[KMZ_EXPORT] = _item(KMZ_EXPORT, REFERENCE, OMITTED,
                                       reason="no trusted redline manifest")

    # Closeout review controls readiness/finality.
    try:
        co = load_closeout_review(store_root, cp, job_id)
        co_status = co["status"]
        source_refs["closeout_review"] = {"status": co_status}
        by_section[CLOSEOUT_REVIEW] = _item(CLOSEOUT_REVIEW, REFERENCE, INCLUDED,
                                            source_ref={"status": co_status})
        co_gate = co.get("gate") or {}
        if any(b.get("code") == CO_OPEN_ENGINE_BLOCKERS for b in co_gate.get("hard_blockers", [])):
            warnings.append({"code": OPEN_ENGINE_BLOCKERS,
                             "reason": "closeout_review reports open engine/redline blockers (closeout-owned)"})
        if co_status not in CLOSEOUT_READY_STATES:
            readiness.append({"code": CLOSEOUT_NOT_READY,
                              "reason": "closeout status %r below READY_FOR_APPROVAL" % co_status})
        elif co_status not in CLOSEOUT_APPROVED_STATES:
            finalization.append({"code": CLOSEOUT_NOT_APPROVED,
                                 "reason": "closeout status %r is not APPROVED" % co_status})
    except CloseoutNotFoundError:
        readiness.append({"code": CLOSEOUT_REVIEW_MISSING, "reason": "no closeout_review exists for this job"})
        by_section[CLOSEOUT_REVIEW] = _item(CLOSEOUT_REVIEW, REFERENCE, OMITTED,
                                            reason="no closeout_review")

    # Billing summary — snapshot/reference ONLY (never recomputed here).
    try:
        bs = load_billing_summary(store_root, cp, job_id)
        bcur = next((r for r in bs.get("revisions", [])
                     if r["revision_id"] == bs.get("current_revision_id")), None)
        bill_ref = {"status": bs["status"], "current_revision_id": bs.get("current_revision_id"),
                    "final_total": (bcur["totals"]["final_total"] if bcur else None),
                    "inputs_hash": (bcur["inputs_hash"] if bcur else None)}
        source_refs["billing_summary"] = bill_ref
        by_section[BILLING_SUMMARY] = _item(BILLING_SUMMARY, SNAPSHOT_REF, INCLUDED, source_ref=bill_ref)
        if bs["status"] != BILLING_FINAL:
            warnings.append({"code": BILLING_NOT_FINAL,
                             "reason": "billing_summary status is %r (not FINAL)" % bs["status"]})
    except BillingSummaryNotFoundError:
        warnings.append({"code": BILLING_SUMMARY_MISSING, "reason": "no billing_summary exists for this job"})
        by_section[BILLING_SUMMARY] = _item(BILLING_SUMMARY, SNAPSHOT_REF, OMITTED,
                                            reason="no billing_summary")

    items = [by_section[s] for s in PACKAGE_SECTIONS if s in by_section]
    gate = {"hard_blockers": hard, "readiness_blockers": readiness,
            "finalization_blockers": finalization, "warnings": warnings,
            "closeout_status": source_refs.get("closeout_review", {}).get("status")}
    return gate, items, source_refs


def _package_content_hash(items, source_refs) -> str:
    """Reproducible hash over the descriptor's identity fields (section/kind/source_ref/sha256/status) +
    source_refs. Excludes human `reason` text and all timestamps -> identical trusted inputs ⇒ identical hash."""
    payload = {
        "items": sorted([{k: it.get(k) for k in ("section", "kind", "source_ref", "sha256", "status")}
                         for it in items], key=lambda d: str(d.get("section"))),
        "source_refs": source_refs,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _derive_status(has_revision, gate) -> str:
    if not has_revision:
        return DRAFT
    if gate["hard_blockers"]:
        return BLOCKED
    if gate["readiness_blockers"]:
        return ASSEMBLED
    if gate["finalization_blockers"]:
        return READY
    return FINAL


def _current_revision(record):
    rid = record.get("current_revision_id")
    return next((r for r in record["revisions"] if r["revision_id"] == rid), None) if rid else None


# --------------------------------------------------------------------------- #
# Assemble — the only mutating operation (no package-approval; readiness follows closeout).
# --------------------------------------------------------------------------- #
def assemble_export_package(store_root, customer_project_id, processing_job_id, *, at, by) -> dict:
    """Assemble the export package descriptor from trusted product outputs (by reference), append an audited
    revision when the trusted references change (else revalidate idempotently), derive the server-authoritative
    status (DRAFT/BLOCKED/ASSEMBLED/READY/FINAL), and — ONLY after the record is written — set the job's
    `export_package` output slot to a reference to this record. Returns the updated record."""
    record = load_export_package(store_root, customer_project_id, processing_job_id)
    gate, items, source_refs = _assemble(store_root, customer_project_id, processing_job_id)
    content = _package_content_hash(items, source_refs)

    cur = _current_revision(record)
    if cur is not None and cur["package_content_hash"] == content:
        action = "revalidated"                                 # same descriptor; only live state refreshed
    else:
        if cur is not None:
            cur["superseded_at"] = at
        rev_id = "pkg-%d" % (len(record["revisions"]) + 1)
        record["revisions"].append({
            "revision_id": rev_id, "package_content_hash": content, "items": items,
            "source_refs": source_refs, "gate_at_creation": gate,
            "generated_at": at, "generated_by": by, "superseded_at": None})
        record["current_revision_id"] = rev_id
        action = "assembled"

    record["gate"] = gate
    new_status = _derive_status(True, gate)
    frm = record["status"]
    record["audit"].append({
        "action": action, "from": frm, "to": new_status, "at": at, "by": by,
        "reason": "%d hard / %d readiness / %d finalization / %d warning"
                  % (len(gate["hard_blockers"]), len(gate["readiness_blockers"]),
                     len(gate["finalization_blockers"]), len(gate["warnings"]))})
    record["status"] = new_status
    write_export_package(store_root, record)                   # WRITE RECORD FIRST

    # THEN set the job's export_package output slot — a durable REFERENCE only (no lifecycle transition,
    # no completion/delivery implication, no closeout/billing override, no generated artifact).
    set_output_slot(store_root, customer_project_id, processing_job_id, EXPORT_PACKAGE_SLOT,
                    {"record_format": EXPORT_PACKAGE_RECORD_FORMAT,
                     "package_revision_id": record["current_revision_id"],
                     "package_content_hash": content, "status": new_status}, at=at, by=by)
    return record


# --------------------------------------------------------------------------- #
# Pure read-only view (no IO, no mutation).
# --------------------------------------------------------------------------- #
def export_package_view(record) -> dict:
    """Derived, side-effect-free summary of an export_package record (re-runnable)."""
    gate = record.get("gate") or {}
    cur = _current_revision(record)
    items = (cur["items"] if cur else [])
    status = record["status"]
    return {
        "status": status,
        "current_revision_id": record.get("current_revision_id"),
        "revision_count": len(record.get("revisions", [])),
        "package_content_hash": (cur["package_content_hash"] if cur else None),
        "included_sections": sorted(it["section"] for it in items if it["status"] == INCLUDED),
        "omitted_sections": sorted(it["section"] for it in items if it["status"] == OMITTED),
        "hard_blocker_codes": sorted({b["code"] for b in gate.get("hard_blockers", [])}),
        "readiness_blocker_codes": sorted({b["code"] for b in gate.get("readiness_blockers", [])}),
        "finalization_blocker_codes": sorted({b["code"] for b in gate.get("finalization_blockers", [])}),
        "warning_codes": sorted({w["code"] for w in gate.get("warnings", [])}),
        "is_blocked": status == BLOCKED,
        "is_ready": status in (READY, FINAL),
        "is_final": status == FINAL,
    }
