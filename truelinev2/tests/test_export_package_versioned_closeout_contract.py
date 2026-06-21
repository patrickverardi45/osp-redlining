"""Contract tests: the export_package versioned closeout model. Pure stdlib + tmp_path; no engine/render/
wiring; no rendered document. Generic ids/values only.

Key proofs:
  * ONE durable versioned export package per job; a descriptor / manifest-of-references (no binary/PDF/HTML).
  * Items reference TRUSTED sources only; reproducible `package_content_hash`; no client/UI status override.
  * KMZ included ONLY when kmz_export permits verified geospatial geometry; a pixel-only manifest OMITS KMZ
    with a warning and does NOT block the rest of the package.
  * Closeout controls readiness/finality (ASSEMBLED < READY < FINAL); hard input problems -> BLOCKED.
  * Billing is included only as a snapshot/reference (never recomputed). Regeneration appends a revision.
  * assemble sets the job export_package slot (reference only) AFTER writing the record, without transitioning
    the job.
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
    set_output_slot,
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
from truelinev2.contracts.published_bundle import sha256_file
from truelinev2.contracts.closeout_review import (
    approve_closeout,
    create_closeout_review,
    evaluate_closeout,
)
from truelinev2.contracts.billing_summary import (
    compute_billing_summary,
    create_billing_summary,
    load_billing_summary,
)
from truelinev2.contracts.export_package import (
    ASSEMBLED,
    BILLING_SUMMARY,
    BILLING_SUMMARY_MISSING,
    BLOCKED,
    CLOSEOUT_NOT_APPROVED,
    CLOSEOUT_NOT_READY,
    CLOSEOUT_REVIEW_MISSING,
    DRAFT,
    FINAL,
    INCLUDED,
    JOB_NOT_IN_CLOSEOUT_RANGE,
    KMZ_EXPORT,
    KMZ_NOT_INCLUDED,
    MANIFEST_NOT_RESOLVABLE,
    MISSING_ARTIFACT_BUNDLE,
    MISSING_MANIFEST,
    OPEN_ENGINE_BLOCKERS,
    READY,
    REDLINE_MANIFEST,
    REVIEWED_BORE_LOG_NOT_READY,
    UNTRUSTED_OUTPUT,
    ExportPackageError,
    assemble_export_package,
    create_export_package,
    export_package_path,
    export_package_view,
    load_export_package,
)

AT = "2026-06-21T00:00:00Z"
BY = "operator-1"
CP = "cp-0001"
JOB = "job-0001"
RBL = "rbl-0001"
RUN = "run-0001"
ROLE = "approver"
ROLES = ("approver", "admin")

COST_RULES = {
    "version": "rules-v1", "currency": "USD", "minor_unit_digits": 2,
    "rules": [{"code": "base_ft", "kind": "BASE", "unit": "ft", "unit_cost": "1.25", "label": "Base footage"}],
}


# --------------------------------------------------------------------------- #
# Bundles (pixel-only with footage; blocked variant; geospatial for the KMZ-included path).
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


def _billing_computed(tmp_path):
    create_billing_summary(tmp_path, CP, JOB, at=AT, by=BY)
    compute_billing_summary(tmp_path, CP, JOB, cost_rule_set=COST_RULES, at=AT, by=BY)


def _geo_job_approved(tmp_path):
    """Manual setup: a job in the closeout range with VALIDATED slots pointing at a hand-written GEOSPATIAL
    manifest (so kmz_export is EXPORTABLE), then closeout APPROVED. No handoff/rbl (bypasses the spine)."""
    create_customer_project(tmp_path, CP, "Label", AT)
    create_job(tmp_path, CP, JOB, AT, BY)
    _advance_job(tmp_path, CLOSEOUT_REVIEW)
    bid = "proj-a-rc-0-feeddeadbeef"
    broot = (Path(tmp_path) / "customer_projects" / CP / "processing_jobs" / JOB
             / "bundle_store" / "bundles" / bid)
    broot.mkdir(parents=True)
    manifest = {"logs": [{"log_id": "logA", "drawn": True, "covered": False, "blocked": False,
                          "status": "DRAWN_REDLINE", "source_sheets": [1], "closure": None,
                          "span": {"start_station": "0+00", "end_station": "9+99", "label": "x"},
                          "geometry": {"crs": "EPSG:4326", "datum": "WGS84", "units": "degrees",
                                       "kind": "LineString", "coordinates": [[0.0, 0.0], [1.0, 1.0]],
                                       "source": "ENGINE_REVIEWED", "confidence": "HIGH"}}]}
    mpath = broot / "redline_manifest.json"
    mpath.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    msha = sha256_file(mpath)
    set_output_slot(tmp_path, CP, JOB, "redline_manifest",
                    {"manifest_id": msha, "manifest_sha256": msha, "bundle_id": bid,
                     "validation_status": "VALIDATED"}, at=AT, by=BY)
    set_output_slot(tmp_path, CP, JOB, "artifact_bundle",
                    {"bundle_id": bid, "manifest_sha256": msha, "validation_status": "VALIDATED"},
                    at=AT, by=BY)
    _closeout_approved(tmp_path)


def _view(rec):
    return export_package_view(rec)


def _job_path(tmp_path):
    return Path(tmp_path) / "customer_projects" / CP / "processing_jobs" / JOB / "_processing_job.json"


# --------------------------------------------------------------------------- #
# FINAL + KMZ omission (pixel-only) does not block the package.
# --------------------------------------------------------------------------- #
def test_final_when_closeout_approved(tmp_path):
    _spine(tmp_path, bundle_builder=_clean_bundle)
    _closeout_approved(tmp_path)
    _billing_computed(tmp_path)
    create_export_package(tmp_path, CP, JOB, at=AT, by=BY)
    rec = assemble_export_package(tmp_path, CP, JOB, at=AT, by=BY)
    v = _view(rec)
    assert v["status"] == FINAL
    assert {"JOB_SUMMARY", "REVIEWED_BORE_LOG", "REDLINE_MANIFEST", "REDLINE_ARTIFACTS",
            "CLOSEOUT_REVIEW", "BILLING_SUMMARY"} <= set(v["included_sections"])
    assert v["package_content_hash"] is not None


def test_kmz_omitted_pixel_only_does_not_block(tmp_path):
    _spine(tmp_path, bundle_builder=_clean_bundle)
    _closeout_approved(tmp_path)
    create_export_package(tmp_path, CP, JOB, at=AT, by=BY)
    rec = assemble_export_package(tmp_path, CP, JOB, at=AT, by=BY)
    v = _view(rec)
    assert v["status"] == FINAL                              # KMZ omission never blocks
    assert KMZ_EXPORT in v["omitted_sections"]
    assert KMZ_NOT_INCLUDED in v["warning_codes"]


def test_kmz_included_when_exportable(tmp_path):
    _geo_job_approved(tmp_path)
    create_export_package(tmp_path, CP, JOB, at=AT, by=BY)
    rec = assemble_export_package(tmp_path, CP, JOB, at=AT, by=BY)
    v = _view(rec)
    assert v["status"] == FINAL
    assert KMZ_EXPORT in v["included_sections"]
    assert KMZ_NOT_INCLUDED not in v["warning_codes"]
    kmz_item = next(it for it in rec["revisions"][-1]["items"] if it["section"] == KMZ_EXPORT)
    assert kmz_item["status"] == INCLUDED and kmz_item["sha256"]   # references the KML content hash


# --------------------------------------------------------------------------- #
# Closeout controls readiness/finality.
# --------------------------------------------------------------------------- #
def test_closeout_ready_is_package_ready(tmp_path):
    _spine(tmp_path, bundle_builder=_clean_bundle)
    _closeout_evaluated(tmp_path)                            # READY_FOR_APPROVAL, not approved
    create_export_package(tmp_path, CP, JOB, at=AT, by=BY)
    rec = assemble_export_package(tmp_path, CP, JOB, at=AT, by=BY)
    v = _view(rec)
    assert v["status"] == READY and CLOSEOUT_NOT_APPROVED in v["finalization_blocker_codes"]


def test_closeout_open_is_assembled(tmp_path):
    _spine(tmp_path, bundle_builder=_clean_bundle)
    create_closeout_review(tmp_path, CP, JOB, at=AT, by=BY)  # OPEN (not evaluated)
    create_export_package(tmp_path, CP, JOB, at=AT, by=BY)
    rec = assemble_export_package(tmp_path, CP, JOB, at=AT, by=BY)
    v = _view(rec)
    assert v["status"] == ASSEMBLED and CLOSEOUT_NOT_READY in v["readiness_blocker_codes"]


def test_closeout_blocked_is_assembled_with_warning(tmp_path):
    _spine(tmp_path, bundle_builder=_blocked_bundle)         # closeout will be BLOCKED (engine blocker)
    _closeout_evaluated(tmp_path)
    create_export_package(tmp_path, CP, JOB, at=AT, by=BY)
    rec = assemble_export_package(tmp_path, CP, JOB, at=AT, by=BY)
    v = _view(rec)
    assert v["status"] == ASSEMBLED                          # closeout not ready -> not READY/FINAL
    assert CLOSEOUT_NOT_READY in v["readiness_blocker_codes"]
    assert OPEN_ENGINE_BLOCKERS in v["warning_codes"]        # visibility only (closeout-owned)


def test_closeout_missing_is_assembled(tmp_path):
    _spine(tmp_path, bundle_builder=_clean_bundle)           # no closeout_review created
    create_export_package(tmp_path, CP, JOB, at=AT, by=BY)
    rec = assemble_export_package(tmp_path, CP, JOB, at=AT, by=BY)
    v = _view(rec)
    assert v["status"] == ASSEMBLED and CLOSEOUT_REVIEW_MISSING in v["readiness_blocker_codes"]


# --------------------------------------------------------------------------- #
# Hard blockers -> BLOCKED.
# --------------------------------------------------------------------------- #
def test_missing_output_slots_block(tmp_path):
    create_customer_project(tmp_path, CP, "Label", AT)
    create_job(tmp_path, CP, JOB, AT, BY)
    _advance_job(tmp_path, CLOSEOUT_REVIEW)
    create_export_package(tmp_path, CP, JOB, at=AT, by=BY)
    rec = assemble_export_package(tmp_path, CP, JOB, at=AT, by=BY)
    codes = _view(rec)["hard_blocker_codes"]
    assert _view(rec)["status"] == BLOCKED
    assert MISSING_MANIFEST in codes and MISSING_ARTIFACT_BUNDLE in codes


def test_untrusted_output_blocks(tmp_path):
    _spine(tmp_path, bundle_builder=_clean_bundle)
    _closeout_approved(tmp_path)
    jpath = _job_path(tmp_path)
    job = json.loads(jpath.read_text())
    job["slots"]["redline_manifest"]["ref"]["validation_status"] = "UNVALIDATED"
    jpath.write_text(json.dumps(job, indent=2), encoding="utf-8")
    create_export_package(tmp_path, CP, JOB, at=AT, by=BY)
    rec = assemble_export_package(tmp_path, CP, JOB, at=AT, by=BY)
    assert _view(rec)["status"] == BLOCKED and UNTRUSTED_OUTPUT in _view(rec)["hard_blocker_codes"]


def test_manifest_sha_drift_blocks(tmp_path):
    _spine(tmp_path, bundle_builder=_clean_bundle)
    _closeout_approved(tmp_path)
    bid = load_job(tmp_path, CP, JOB)["slots"]["artifact_bundle"]["ref"]["bundle_id"]
    stored = (Path(tmp_path) / "customer_projects" / CP / "processing_jobs" / JOB
              / "bundle_store" / "bundles" / bid / "redline_manifest.json")
    stored.write_text(stored.read_text() + "\n ", encoding="utf-8")
    create_export_package(tmp_path, CP, JOB, at=AT, by=BY)
    rec = assemble_export_package(tmp_path, CP, JOB, at=AT, by=BY)
    assert _view(rec)["status"] == BLOCKED and MANIFEST_NOT_RESOLVABLE in _view(rec)["hard_blocker_codes"]


def test_job_not_in_range_blocks(tmp_path):
    _spine(tmp_path, bundle_builder=_clean_bundle, advance_to=None)   # job stays CREATED
    create_export_package(tmp_path, CP, JOB, at=AT, by=BY)
    rec = assemble_export_package(tmp_path, CP, JOB, at=AT, by=BY)
    assert _view(rec)["status"] == BLOCKED and JOB_NOT_IN_CLOSEOUT_RANGE in _view(rec)["hard_blocker_codes"]


def test_reviewed_bore_log_edited_after_handoff_blocks(tmp_path):
    up_id = _spine(tmp_path, bundle_builder=_clean_bundle)
    add_extracted_rows(tmp_path, CP, JOB, RBL, [new_extracted_row(
        "row-2", up_id, raw={}, normalized={}, extraction_method=OCR, at=AT, by=BY)], at=AT, by=BY)
    create_export_package(tmp_path, CP, JOB, at=AT, by=BY)
    rec = assemble_export_package(tmp_path, CP, JOB, at=AT, by=BY)
    assert _view(rec)["status"] == BLOCKED and REVIEWED_BORE_LOG_NOT_READY in _view(rec)["hard_blocker_codes"]


# --------------------------------------------------------------------------- #
# Billing snapshot (never recomputed) + regeneration + no override + reproducibility.
# --------------------------------------------------------------------------- #
def test_billing_included_as_snapshot_not_recomputed(tmp_path):
    _spine(tmp_path, bundle_builder=_clean_bundle)
    _closeout_approved(tmp_path)
    _billing_computed(tmp_path)
    before = len(load_billing_summary(tmp_path, CP, JOB)["revisions"])
    create_export_package(tmp_path, CP, JOB, at=AT, by=BY)
    rec = assemble_export_package(tmp_path, CP, JOB, at=AT, by=BY)
    after = len(load_billing_summary(tmp_path, CP, JOB)["revisions"])
    assert before == after == 1                              # export did not recompute billing
    bill_item = next(it for it in rec["revisions"][-1]["items"] if it["section"] == BILLING_SUMMARY)
    assert bill_item["status"] == INCLUDED
    assert bill_item["source_ref"]["current_revision_id"] == "rev-1"
    assert bill_item["source_ref"]["final_total"] == "125.63"


def test_billing_missing_warns_but_not_blocks(tmp_path):
    _spine(tmp_path, bundle_builder=_clean_bundle)
    _closeout_approved(tmp_path)                             # no billing_summary
    create_export_package(tmp_path, CP, JOB, at=AT, by=BY)
    rec = assemble_export_package(tmp_path, CP, JOB, at=AT, by=BY)
    v = _view(rec)
    assert v["status"] == FINAL and BILLING_SUMMARY_MISSING in v["warning_codes"]


def test_reproducible_idempotent_revalidate(tmp_path):
    _spine(tmp_path, bundle_builder=_clean_bundle)
    _closeout_approved(tmp_path)
    create_export_package(tmp_path, CP, JOB, at=AT, by=BY)
    r1 = assemble_export_package(tmp_path, CP, JOB, at=AT, by=BY)
    h1 = r1["revisions"][-1]["package_content_hash"]
    r2 = assemble_export_package(tmp_path, CP, JOB, at=AT, by=BY)
    assert len(r2["revisions"]) == 1                         # no new revision for identical descriptor
    assert r2["revisions"][-1]["package_content_hash"] == h1
    assert r2["audit"][-1]["action"] == "revalidated"


def test_regeneration_on_trusted_change(tmp_path):
    _spine(tmp_path, bundle_builder=_clean_bundle)
    _closeout_approved(tmp_path)
    _billing_computed(tmp_path)
    create_export_package(tmp_path, CP, JOB, at=AT, by=BY)
    assemble_export_package(tmp_path, CP, JOB, at=AT, by=BY)              # pkg-1
    compute_billing_summary(tmp_path, CP, JOB, cost_rule_set=dict(COST_RULES, version="rules-v2"),
                            at=AT, by=BY)                                 # billing snapshot changes
    rec = assemble_export_package(tmp_path, CP, JOB, at=AT, by=BY)        # pkg-2
    assert len(rec["revisions"]) == 2
    assert rec["current_revision_id"] == "pkg-2"
    assert rec["revisions"][0]["superseded_at"] is not None
    assert rec["revisions"][1]["superseded_at"] is None


def test_no_status_override_survives_reassemble(tmp_path):
    _spine(tmp_path, bundle_builder=_clean_bundle)
    _closeout_evaluated(tmp_path)                            # READY, not approved -> package READY
    create_export_package(tmp_path, CP, JOB, at=AT, by=BY)
    assemble_export_package(tmp_path, CP, JOB, at=AT, by=BY)
    path = export_package_path(tmp_path, CP, JOB)
    rec = json.loads(path.read_text())
    rec["status"] = FINAL                                    # tamper on disk
    path.write_text(json.dumps(rec, indent=2), encoding="utf-8")
    rec = assemble_export_package(tmp_path, CP, JOB, at=AT, by=BY)
    assert rec["status"] == READY                            # server re-derives; override discarded


# --------------------------------------------------------------------------- #
# Job slot, durability, isolation, lifecycle, pure view, references.
# --------------------------------------------------------------------------- #
def test_assemble_sets_export_package_slot_reference_only(tmp_path):
    _spine(tmp_path, bundle_builder=_clean_bundle)
    _closeout_approved(tmp_path)
    job_before = load_job(tmp_path, CP, JOB)
    assert job_before["slots"]["export_package"] is None
    create_export_package(tmp_path, CP, JOB, at=AT, by=BY)
    rec = assemble_export_package(tmp_path, CP, JOB, at=AT, by=BY)
    job_after = load_job(tmp_path, CP, JOB)
    slot = job_after["slots"]["export_package"]
    assert slot is not None
    assert slot["ref"]["package_revision_id"] == rec["current_revision_id"]
    assert slot["ref"]["status"] == FINAL
    assert job_after["status"] == job_before["status"]       # slot write did NOT transition the job


def test_durable_across_reload(tmp_path):
    _spine(tmp_path, bundle_builder=_clean_bundle)
    _closeout_approved(tmp_path)
    create_export_package(tmp_path, CP, JOB, at=AT, by=BY)
    assemble_export_package(tmp_path, CP, JOB, at=AT, by=BY)
    assert load_export_package(tmp_path, CP, JOB)["status"] == FINAL


def test_one_export_package_per_job(tmp_path):
    _spine(tmp_path, bundle_builder=_clean_bundle)
    create_export_package(tmp_path, CP, JOB, at=AT, by=BY)
    with pytest.raises(ExportPackageError):
        create_export_package(tmp_path, CP, JOB, at=AT, by=BY)


def test_cross_project_access_denied(tmp_path):
    _spine(tmp_path, bundle_builder=_clean_bundle)
    create_export_package(tmp_path, CP, JOB, at=AT, by=BY)
    path = export_package_path(tmp_path, CP, JOB)
    rec = json.loads(path.read_text())
    rec["customer_project_id"] = "cp-9999"
    path.write_text(json.dumps(rec, indent=2), encoding="utf-8")
    with pytest.raises(CrossProjectAccessError):
        load_export_package(tmp_path, CP, JOB)


def test_create_is_draft_no_slot(tmp_path):
    _spine(tmp_path, bundle_builder=_clean_bundle)
    rec = create_export_package(tmp_path, CP, JOB, at=AT, by=BY)
    assert rec["status"] == DRAFT and rec["current_revision_id"] is None
    assert load_job(tmp_path, CP, JOB)["slots"]["export_package"] is None   # slot set only on assemble


def test_included_items_all_reference_trusted_sources(tmp_path):
    _spine(tmp_path, bundle_builder=_clean_bundle)
    _closeout_approved(tmp_path)
    create_export_package(tmp_path, CP, JOB, at=AT, by=BY)
    rec = assemble_export_package(tmp_path, CP, JOB, at=AT, by=BY)
    for it in rec["revisions"][-1]["items"]:
        if it["status"] == INCLUDED:
            assert it["source_ref"] is not None             # no invented content; every item is a reference


def test_export_package_view_is_pure(tmp_path):
    _spine(tmp_path, bundle_builder=_clean_bundle)
    _closeout_approved(tmp_path)
    create_export_package(tmp_path, CP, JOB, at=AT, by=BY)
    rec = assemble_export_package(tmp_path, CP, JOB, at=AT, by=BY)
    v1 = _view(rec)
    v2 = _view(rec)
    assert v1 == v2 and v1["is_final"] is True
    assert rec["status"] == FINAL                            # record unchanged by the view
