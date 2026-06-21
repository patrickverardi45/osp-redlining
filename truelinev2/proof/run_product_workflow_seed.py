"""Internal product-workflow SEED — proves the v2 product pipeline end-to-end with ONE real drawn log.

Drives the full product contract spine against a REAL product-store, using only real v2 contracts:

    customer_project -> processing_job -> upload_pipeline -> reviewed_bore_log (MANUAL untrusted rows,
    reviewed + grouped) -> manifest_handoff (finalize a FRESH real subset bundle) -> proof artifacts
    (manifest-backed consumer) -> kmz_export safety -> closeout_review (evaluate only) ->
    billing_summary (server-side cost rules) -> export_package (descriptor of references).

Honesty contract (why this is real, not a mock):
  * MANUAL reviewed rows are explicit UNTRUSTED input (extraction_method=MANUAL_ENTRY, NO OCR is run);
    a row becomes engine-eligible ONLY after human review + a confirmed segment group.
  * the bundle binds ONE real, already-rendered drawn log (log3) whose FINAL_REDLINE_PNG artifacts
    exist on disk (rendered at commit c19b565); it is PUBLISHED through the existing publisher/store/
    handoff chain, so every artifact carries a real sha256 + bytes and `mock_example` is false.
  * it is a FRESH, generically-named single-log SUBSET (frontier "1/1") — NEVER the hand-authored
    `mock_example:true` example manifest, and NEVER claimed to be the unified all-50 bundle.
  * per-log facts are real committed values cited to the accountability ledger via `evidence[]`
    (transcribed name-free here, not read from the example manifest).

It is an INTERNAL workflow seed (not production truth): all output is written under a gitignored
data/outputs path with generic ids. No engine/renderer/fixture/coordinate is touched; no KMZ
coordinate, OCR, or export document is fabricated (KMZ safely BLOCKS on pixel-only geometry; the
export package is a descriptor of references — no file is generated).

    python -m truelinev2.proof.run_product_workflow_seed
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from truelinev2.contracts.customer_project import create_customer_project
from truelinev2.contracts.processing_job import (
    AWAITING_REVIEW,
    EXTRACTING,
    PLACED,
    PLACING,
    UPLOADING,
    create_job,
    job_dir,
    transition,
)
from truelinev2.contracts.upload_pipeline import accept_upload
from truelinev2.contracts.extracted_row import CONFIRMED, MANUAL_ENTRY, new_extracted_row
from truelinev2.contracts.reviewed_bore_log import (
    GROUPING_CONFIRMED,
    SEPARATE_BORE,
    add_extracted_rows,
    create_reviewed_bore_log,
    define_segment_group,
    is_engine_ready,
    load_reviewed_bore_log,
    review_row_in_log,
    set_grouping_status,
)
from truelinev2.contracts.redline_manifest_publisher import publish_manifest
from truelinev2.contracts.manifest_handoff import (
    BUNDLE_STORE_SUBDIR,
    finalize_handoff,
    record_handoff_attempt,
)
from truelinev2.contracts.published_bundle_consumer import StaticBundleConsumer
from truelinev2.contracts.kmz_export import evaluate_export
from truelinev2.contracts.closeout_review import (
    closeout_summary,
    create_closeout_review,
    evaluate_closeout,
)
from truelinev2.contracts.billing_summary import (
    billing_summary_view,
    compute_billing_summary,
    create_billing_summary,
)
from truelinev2.contracts.export_package import (
    assemble_export_package,
    create_export_package,
    export_package_view,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
# Internal seed product-store: under data/outputs (gitignored) — never committed, regenerated each run.
SEED_STORE_ROOT = REPO_ROOT / "data" / "outputs" / "truelinev2" / "product_store_seed"
# Existing real per-log render output (gitignored working artifacts; produced by the render at c19b565).
REAL_RENDER_DIR = REPO_ROOT / "data" / "outputs" / "callout_route_assembly_sweep"
RENDER_COMMIT = "c19b565"

# Generic, name-free identifiers (a real customer/project name is never baked into the seed).
SEED_PROJECT_ID = "seed-project"
SEED_PROJECT_NAME = "Workflow seed project (internal)"
SEED_JOB_ID = "seed-job-1"
SEED_RBL_ID = "seed-rbl-1"
SEED_GROUP_ID = "seed-grp-1"
SEED_ENGINE_RUN_ID = "seed-run-1"
SEED_BY = "workflow-seed"

# Manifest enum keys (schema constants, not names) used to build a reconciling single-log subset.
_STATUS_KEYS = ("DRAWN_REDLINE", "COVERED_BY_EXISTING_REDLINE", "OWNER_LOCKED_ABSTAIN",
                "SOURCE_GAP_BLOCKED", "MISSING_SOURCE_SHEET_BLOCKED")
_PROVENANCE_KEYS = ("DETERMINISTIC_AUTO", "OWNER_CONFIRMED_HUMAN_ADJUSTABLE",
                    "COVERED_BY_EXISTING_REDLINE", "BLOCKED_OWNER_LOCKED",
                    "BLOCKED_SOURCE_GAP", "BLOCKED_MISSING_SOURCE")

# log3's two real FINAL_REDLINE_PNG renders: (manifest-relative path, real source file, sheet).
_LOG3_ARTIFACTS = (
    ("artifacts/log3/log3_s2_redline_stroke.png", REAL_RENDER_DIR / "log3_s2_redline_stroke.png", 2),
    ("artifacts/log3/log3_s3_redline_stroke.png", REAL_RENDER_DIR / "log3_s3_redline_stroke.png", 3),
)
_LEDGER_REF = "wiki/trueline_v2_50_of_58_accountability_table.md"


def build_subset_manifest_input(log, *, project_id, project_name, render_commit, engine_head,
                                disclaimer) -> dict:
    """Build a schema-valid, reconciling SINGLE-LOG subset manifest (publisher input). Counts are derived
    from the one log, so the published output reconciles. `mock_example` is false (this is a real subset
    being published, not an example); artifact sha256/bytes are filled by the publisher."""
    status_counts = {k: 0 for k in _STATUS_KEYS}
    status_counts[log["status"]] = 1
    provenance_counts = {k: 0 for k in _PROVENANCE_KEYS}
    provenance_counts[log["provenance"]] = 1
    drawn, covered, blocked = int(log["drawn"]), int(log["covered"]), int(log["blocked"])
    return {
        "schema_version": "1.0.0",
        "mock_example": False,
        "disclaimer": disclaimer,
        "project_id": project_id,
        "project_name": project_name,
        "engine": {"branch": "feat/truelinev2", "engine_head": engine_head,
                   "render_commit": render_commit, "generated_from": "product_workflow_seed (subset)"},
        "summary": {"total_logs": 1, "drawn_count": drawn, "covered_count": covered,
                    "blocked_count": blocked, "frontier": "%d/1" % drawn},
        "status_counts": status_counts,
        "provenance_counts": provenance_counts,
        "consumption_rules": [
            "Consume only this manifest for drawn/covered/blocked truth.",
            "Single-log internal workflow seed subset; NOT the unified all-50 bundle.",
        ],
        "logs": [log],
    }


def _log3_entry() -> dict:
    """log3 as a real DRAWN subset entry. Facts are owner-confirmed committed values cited to the
    accountability ledger (transcribed name-free); drawn_ft is the drawn new-content footage."""
    return {
        "log_id": "log3", "parent_id": "bore_log3", "entry_role": "standalone",
        "status": "DRAWN_REDLINE", "provenance": "OWNER_CONFIRMED_HUMAN_ADJUSTABLE",
        "drawn": True, "covered": False, "blocked": False, "drawn_lane": "NEW_TARGETS",
        "source_sheets": [3, 4, 5],
        "span": {"start_station": "12+63", "end_station": "21+63", "label": "12+63->21+63"},
        "closure": {"drawn_ft": 249.8, "new_content_ft": 249.8, "target_ft": 250.0, "closes": True,
                    "note": "new content drawn: start stub ~2.8' + ~247' straight segment between "
                            "bound endpoints (drawn_ft = new_content_ft per the accountability ledger)"},
        "coverage": {"downstream_covered_by": ["log4"],
                     "note": "downstream span covered by drawn log4 (parent/child coverage; shared "
                             "junction only)"},
        "blocker": None,
        "artifacts": [{"kind": "FINAL_REDLINE_PNG", "sheet": sheet, "path": mpath,
                       "sha256": None, "example_placeholder": True}
                      for (mpath, _src, sheet) in _LOG3_ARTIFACTS],
        "evidence": [
            {"kind": "ACCOUNTABILITY_LEDGER", "ref": _LEDGER_REF},
            {"kind": "OWNER_REVIEW", "ref": _LEDGER_REF,
             "note": "owner-confirmed human-adjustable geometry"},
        ],
        "warnings": [],
    }


def seed_cost_rule_set() -> dict:
    """Generic, test-safe versioned cost rules (NOT real customer rates): one per-foot BASE rule. The
    server is the source of cost rules; the client never supplies a rate (billing_summary §6)."""
    return {
        "version": "seed-rules-1", "currency": "USD", "minor_unit_digits": 2,
        "rules": [{"code": "BORE_FT", "kind": "BASE", "unit": "ft", "unit_cost": "12.50",
                   "label": "Directional bore (per foot)"}],
    }


def seed_workflow(store_root, *, customer_project_id, job_id, reviewed_bore_log_id, engine_run_id,
                  group_id, manifest_input, artifact_map, cost_rule_set, upload_bytes, rows, at, by):
    """Drive the full product spine for one job against `store_root`, publishing `manifest_input` (with
    `artifact_map` -> real source files) as a fresh real subset bundle and finalizing the handoff against
    it. Writes only under `store_root`. Returns a dict of the real produced state for each stage."""
    store_root = Path(store_root)

    # project + job
    create_customer_project(store_root, customer_project_id, SEED_PROJECT_NAME, at)
    create_job(store_root, customer_project_id, job_id, at, by)

    # real BORE_LOG upload (the manual-entry source document) — stays untrusted/queued, no OCR
    upload = accept_upload(store_root, customer_project_id, job_id, kind="BORE_LOG",
                           filename="bore_log.csv", content=upload_bytes, stored_at=at)

    # lifecycle into the review phase
    transition(store_root, customer_project_id, job_id, UPLOADING, at=at, by=by)
    transition(store_root, customer_project_id, job_id, EXTRACTING, at=at, by=by)
    transition(store_root, customer_project_id, job_id, AWAITING_REVIEW, at=at, by=by)

    # reviewed-bore-log gate: MANUAL untrusted rows -> human review -> confirmed group -> engine-ready
    create_reviewed_bore_log(store_root, customer_project_id, job_id, upload["upload_id"],
                             reviewed_bore_log_id, at=at, by=by)
    built = [new_extracted_row(r["row_id"], upload["upload_id"], raw=r["raw"],
                               normalized=r["normalized"], extraction_method=MANUAL_ENTRY, at=at, by=by)
             for r in rows]
    add_extracted_rows(store_root, customer_project_id, job_id, reviewed_bore_log_id, built, at=at, by=by)
    row_ids = [r["row_id"] for r in rows]
    for rid in row_ids:
        review_row_in_log(store_root, customer_project_id, job_id, reviewed_bore_log_id, rid,
                          CONFIRMED, at=at, by=by)
    define_segment_group(store_root, customer_project_id, job_id, reviewed_bore_log_id, group_id,
                         row_ids, SEPARATE_BORE, at=at, by=by)
    set_grouping_status(store_root, customer_project_id, job_id, reviewed_bore_log_id, group_id,
                        GROUPING_CONFIRMED, at=at, by=by)
    engine_ready = is_engine_ready(
        load_reviewed_bore_log(store_root, customer_project_id, job_id, reviewed_bore_log_id))

    transition(store_root, customer_project_id, job_id, PLACING, at=at, by=by)

    # publish a FRESH real subset bundle (mock_example:false, real sha256/bytes) into job-scoped staging
    staging_root = job_dir(store_root, customer_project_id, job_id) / "engine_outputs"
    input_path = staging_root / "_seed_input_manifest.json"
    input_path.parent.mkdir(parents=True, exist_ok=True)
    input_path.write_text(json.dumps(manifest_input, indent=2), encoding="utf-8")
    published = publish_manifest(str(input_path), None, str(staging_root), engine_run_id,
                                 artifact_map=artifact_map)

    # manifest handoff: record the attempt + finalize through the real bundle validation/store
    record_handoff_attempt(store_root, customer_project_id, job_id, reviewed_bore_log_id, engine_run_id,
                           engine_run_status="completed", at=at, by=by)
    handoff = finalize_handoff(store_root, customer_project_id, job_id, engine_run_id,
                               published["publish_dir"], at=at, by=by)

    transition(store_root, customer_project_id, job_id, PLACED, at=at, by=by)

    # proof artifacts via the manifest-backed read-only consumer
    bundle_id = handoff["artifact_bundle_attachment"]["bundle_id"]
    bundle_store = job_dir(store_root, customer_project_id, job_id) / BUNDLE_STORE_SUBDIR
    bundle = StaticBundleConsumer(bundle_store, enable=True).open_bundle(bundle_id)
    artifacts = [{"log_id": lid, "path": a.get("path"), "sha256": a.get("sha256"),
                  "bytes": a.get("bytes"), "kind": a.get("kind")}
                 for lid, a in bundle.final_artifacts()]

    # KMZ geometry-export safety (pixel-only -> BLOCKED; never fakes coordinates)
    kmz = evaluate_export(store_root, customer_project_id, job_id)

    # closeout — evaluate only (NO privileged lock/approve/close/reject/reopen)
    create_closeout_review(store_root, customer_project_id, job_id, at=at, by=by)
    closeout = evaluate_closeout(store_root, customer_project_id, job_id, at=at, by=by)

    # billing — server-side computation from injected versioned cost rules (no client rates)
    create_billing_summary(store_root, customer_project_id, job_id, at=at, by=by)
    billing = compute_billing_summary(store_root, customer_project_id, job_id,
                                      cost_rule_set=cost_rule_set, at=at, by=by)

    # export package — descriptor of references only (no document/file generated)
    create_export_package(store_root, customer_project_id, job_id, at=at, by=by)
    export = assemble_export_package(store_root, customer_project_id, job_id, at=at, by=by)

    return {
        "upload": upload, "engine_ready": engine_ready, "bundle_id": bundle_id,
        "handoff": handoff, "artifacts": artifacts, "kmz": kmz,
        "closeout": closeout, "closeout_summary": closeout_summary(closeout),
        "billing": billing, "billing_view": billing_summary_view(billing),
        "export": export, "export_view": export_package_view(export),
    }


def _print_report(result) -> None:
    print("== product workflow seed (one real drawn log: log3) ==\n")
    print("  upload:            %s (%s, %d bytes)"
          % (result["upload"]["upload_id"], result["upload"]["extraction_status"],
             result["upload"]["bytes"]))
    print("  reviewed bore log: engine_ready=%s (manual rows reviewed + grouped)"
          % result["engine_ready"])
    print("  manifest handoff:  %s -> bundle %s" % (result["handoff"]["status"], result["bundle_id"]))
    for a in result["artifacts"]:
        print("    artifact:        %s  sha256=%s  bytes=%s" % (a["path"], a["sha256"], a["bytes"]))
    print("  kmz safety:        %s (%s)"
          % (result["kmz"]["status"],
             ", ".join(sorted({b["code"] for b in result["kmz"].get("blockers", [])})) or "-"))
    print("  closeout:          %s (hard_blockers=%d, decision=%s)"
          % (result["closeout"]["status"], result["closeout_summary"]["hard_blocker_count"],
             result["closeout"]["decision"]))
    print("  billing:           %s  base_total=%s %s"
          % (result["billing"]["status"], result["billing_view"]["final_total"],
             result["billing_view"]["currency"]))
    print("  export package:    %s  included=%s  omitted=%s"
          % (result["export"]["status"], result["export_view"]["included_sections"],
             result["export_view"]["omitted_sections"]))


def main() -> int:
    # Re-runnable: clear ONLY the gitignored seed store this harness owns, then regenerate.
    if (SEED_STORE_ROOT.name == "product_store_seed" and "outputs" in SEED_STORE_ROOT.parts
            and SEED_STORE_ROOT.exists()):
        shutil.rmtree(SEED_STORE_ROOT)

    missing = [str(src) for (_m, src, _s) in _LOG3_ARTIFACTS if not src.is_file()]
    if missing:
        print("ABORT: real log3 render artifact(s) not found — run the render sweep first. Missing:")
        for m in missing:
            print("  - " + m)
        return 1

    manifest_input = build_subset_manifest_input(
        _log3_entry(), project_id=SEED_PROJECT_ID, project_name=SEED_PROJECT_NAME,
        render_commit=RENDER_COMMIT, engine_head=RENDER_COMMIT,
        disclaimer=("Internal product-workflow seed: ONE real drawn log published as a subset "
                    "(mock_example:false, real sha256/bytes). NOT the hand-authored example manifest "
                    "and NOT the unified all-50 bundle."))
    artifact_map = {mpath: str(src) for (mpath, src, _s) in _LOG3_ARTIFACTS}
    rows = [{"row_id": "seed-row-1",
             "raw": {"start_station": "12+63", "end_station": "21+63"},
             "normalized": {"start_station": "12+63", "end_station": "21+63"}}]

    result = seed_workflow(
        SEED_STORE_ROOT, customer_project_id=SEED_PROJECT_ID, job_id=SEED_JOB_ID,
        reviewed_bore_log_id=SEED_RBL_ID, engine_run_id=SEED_ENGINE_RUN_ID, group_id=SEED_GROUP_ID,
        manifest_input=manifest_input, artifact_map=artifact_map, cost_rule_set=seed_cost_rule_set(),
        upload_bytes=b"row_id,start_station,end_station\nseed-row-1,12+63,21+63\n", rows=rows,
        at=datetime.now(timezone.utc).isoformat(), by=SEED_BY)

    _print_report(result)
    print("\nseed product-store (gitignored): %s" % SEED_STORE_ROOT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
