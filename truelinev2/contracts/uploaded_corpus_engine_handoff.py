"""Uploaded-corpus engine handoff — run the deterministic placement ENGINE on an uploaded corpus and, when
the engine produces a drawable candidate, publish its rendered redline as a job-local product bundle.

This is the FIRST real (non-replay) uploaded-corpus engine adapter. Unlike the recognized-corpus bridge
(which replays an EXISTING committed render for a known fingerprint), this RUNS the engine on the job's own
uploaded plan + bore-log:

  uploaded PLAN_PDF + an engine-ready reviewed_bore_log's source BORE_LOG
    -> normalize the bore log (format-agnostic reader)
    -> select the plan dialect by PATTERN (no per-project lookup, no baked names)
    -> match (honest abstain) on the drawn plan geometry
    -> if the engine places a candidate, RENDER the redline stroke along the DRAWN route and publish it as a
       job-local FINAL_REDLINE_PNG bundle; otherwise return BLOCKED with the engine's named reason.

It is NAME-FREE: it bakes in NO customer/project/location/operator name. The corpus is whatever the tenant
uploaded; the dialect is chosen by the registry's pattern detectors; geometry comes only from the plan's own
drawn vectors (never invented coordinates, never nearest-length guessing, never manual control points).

Honesty / boundaries:
  * The redline is drawn from the engine's matched DRAWN extent only. A REVIEW placement renders a DASHED
    (human-adjustable) stroke with provenance OWNER_CONFIRMED_HUMAN_ADJUSTABLE; an AUTO_SELECT placement
    renders a SOLID stroke with provenance DETERMINISTIC_AUTO. An ABSTAIN renders nothing and is reported as
    a named blocker (the engine's own reason, e.g. NO_DRAWN_BORE_OVER_SPAN / INSUFFICIENT_DRAWN_COVERAGE).
  * The published bundle is a SEPARATE, job-local bundle (top-level bundle_origin UPLOADED_CORPUS_ENGINE,
    frontier "1/1"); it is NEVER summed into the committed deterministic 50/58 frontier.
  * It touches NO engine/renderer/solver/dialect/fixture/coordinate code: it only CALLS the shipped engine
    (load_borelog + select_dialect + run_match) and renderer (render_redline_stroke) read-only, and REUSES
    the existing publisher/store/handoff spine. The only additive contract change is one OPTIONAL manifest
    bundle_origin enum value.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from truelinev2.contracts.customer_project import validate_customer_project_id
from truelinev2.contracts.processing_job import job_dir, load_job, validate_job_id
from truelinev2.contracts.reviewed_bore_log import (
    is_engine_ready,
    list_reviewed_bore_logs,
)
from truelinev2.contracts.redline_manifest_publisher import publish_manifest
from truelinev2.contracts.manifest_handoff import (
    BUNDLE_STORE_SUBDIR,
    SUCCEEDED,
    HandoffNotFoundError,
    finalize_handoff,
    load_handoff,
    record_handoff_attempt,
)
from truelinev2.contracts.published_bundle_consumer import StaticBundleConsumer

# Engine + renderer (read-only reuse; this adapter changes none of it).
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.extract.registry import select_dialect
from truelinev2.match.engine import run_match
from truelinev2.render.crop import render_redline_stroke
from truelinev2.schema.models import PlacementStatus

PLAN_PDF_KIND = "PLAN_PDF"
BORE_LOG_KIND = "BORE_LOG"
ENGINE_OUTPUTS_SUBDIR = "engine_outputs"
STATUS_RUNNABLE = "RUNNABLE"
STATUS_BLOCKED = "BLOCKED"
BUNDLE_ORIGIN_UPLOADED_CORPUS_ENGINE = "UPLOADED_CORPUS_ENGINE"
RENDER_ENGINE_HEAD = "uploaded-corpus-engine"          # not a deterministic render commit
_DEFAULT_OFFSET = 0                                      # the dialect derives its own offset; this is the fallback

# Per-status render + manifest mapping (REVIEW => dashed/human-adjustable; AUTO => solid/deterministic).
_PROVENANCE_BY_STATUS = {
    PlacementStatus.REVIEW.value: "OWNER_CONFIRMED_HUMAN_ADJUSTABLE",
    PlacementStatus.AUTO_SELECT.value: "DETERMINISTIC_AUTO",
}

# Adapter-level REVIEW caveat (NOT an engine caveat, NOT a coordinate/render change): the bore references
# multiple plan sheets but the engine placed/rendered on a SINGLE winning sheet, so the cross-sheet
# continuation is not assembled into one per-bore route. Surfaced in the candidate report + manifest
# warnings so the REVIEW truth is explicit; it never changes geometry and never claims AUTO.
CROSS_SHEET_CONTINUATION_REVIEW = "CROSS_SHEET_CONTINUATION_REVIEW"

# Named blockers (honest; present when NOT runnable).
NO_PLAN_PDF_UPLOAD = "NO_PLAN_PDF_UPLOAD"
NO_ENGINE_READY_REVIEWED_BORE_LOG = "NO_ENGINE_READY_REVIEWED_BORE_LOG"
PLAN_PDF_FILE_NOT_AVAILABLE = "PLAN_PDF_FILE_NOT_AVAILABLE"
BORE_LOG_FILE_NOT_AVAILABLE = "BORE_LOG_FILE_NOT_AVAILABLE"
NO_PLAN_DIALECT_RECOGNIZED = "NO_PLAN_DIALECT_RECOGNIZED"
ENGINE_ABSTAINED = "ENGINE_ABSTAINED"


class UploadedCorpusEngineError(Exception):
    """Uploaded-corpus engine handoff is not runnable / did not succeed."""


def _uploads_of_kind(job, kind):
    return [u for u in job.get("uploads", []) if u.get("kind") == kind]


def _upload_file(store_root, customer_project_id, job_id, upload):
    if not upload:
        return None
    path = job_dir(store_root, customer_project_id, job_id) / (upload.get("stored_path") or "")
    return path if path.is_file() else None


def _first_ready_rbl(store_root, customer_project_id, job_id):
    for r in list_reviewed_bore_logs(store_root, customer_project_id, job_id):
        if is_engine_ready(r):
            return r
    return None


def _resolve_inputs(store_root, customer_project_id, job_id, job):
    """Resolve (plan_path, borelog_path, rbl) + the input-availability blockers. The bore log comes from an
    engine-ready reviewed_bore_log's SOURCE upload (the product review gate must have passed), so the engine
    never runs on un-reviewed raw rows."""
    blockers = []
    plan_uploads = _uploads_of_kind(job, PLAN_PDF_KIND)
    if not plan_uploads:
        blockers.append({"code": NO_PLAN_PDF_UPLOAD, "reason": "Job has no PLAN_PDF upload."})
    rbl = _first_ready_rbl(store_root, customer_project_id, job_id)
    if rbl is None:
        blockers.append({"code": NO_ENGINE_READY_REVIEWED_BORE_LOG,
                         "reason": "No reviewed_bore_log has passed the engine-readiness gate."})

    plan_path = _upload_file(store_root, customer_project_id, job_id, plan_uploads[0]) if plan_uploads else None
    if plan_uploads and plan_path is None:
        blockers.append({"code": PLAN_PDF_FILE_NOT_AVAILABLE,
                         "reason": "The PLAN_PDF upload is recorded but its stored file is not available."})
    borelog_path = None
    if rbl is not None:
        src = next((u for u in job.get("uploads", [])
                    if u.get("upload_id") == rbl.get("source_upload_id")), None)
        borelog_path = _upload_file(store_root, customer_project_id, job_id, src)
        if borelog_path is None:
            blockers.append({"code": BORE_LOG_FILE_NOT_AVAILABLE,
                             "reason": "The reviewed bore-log's source BORE_LOG file is not available."})
    return plan_path, borelog_path, rbl, blockers


def _run_engine(plan_path, borelog_path):
    """Run the shipped engine on the resolved files. Returns (bore, placement, offset, dialect_name). The
    DEFAULT (all-off) match path is used — no opt-in gates — so this mirrors the deterministic engine's
    default behavior. Caller owns no plan handle (it is opened + closed here)."""
    bore = load_borelog(str(borelog_path))
    plan = PlanPdf(str(plan_path))
    try:
        dialect = select_dialect(plan)
        if dialect is None:
            return bore, None, _DEFAULT_OFFSET, None
        offset = dialect.calibrate(plan, _DEFAULT_OFFSET)
        placement = run_match(bore, plan, dialect, offset)
        return bore, placement, offset, getattr(dialect, "name", None)
    finally:
        plan.close()


def _candidate(placement):
    """The winning matched callout (drawn extent) for a placed candidate, else None."""
    if placement is None or placement.status == PlacementStatus.ABSTAIN:
        return None
    return placement.matched_callouts[0] if placement.matched_callouts else None


def _adapter_caveats(bore, placement):
    """Adapter-level REVIEW truth annotations derived from (bore, placement) — NOT engine caveats and NOT a
    coordinate/render change. Currently emits CROSS_SHEET_CONTINUATION_REVIEW when the bore references more
    than one plan sheet but the engine placed/rendered on a single winning sheet (so the cross-sheet
    continuation is not assembled into one per-bore route — an honest REVIEW caveat, never an AUTO claim)."""
    if placement is None:
        return []
    referenced = {int(s) for s in (bore.sheet_refs or [])}
    covered = {int(s) for s in (placement.sheets or [])}
    if not covered and placement.matched_callouts:
        covered = {int(placement.matched_callouts[0].sheet)}
    out = []
    if len(referenced) > 1 and (referenced - covered):
        out.append(CROSS_SHEET_CONTINUATION_REVIEW)
    return out


def evaluate_uploaded_corpus_engine_handoff(store_root, customer_project_id, job_id) -> dict:
    """Read-only candidate report: can the ENGINE place a redline for this job's uploaded corpus? Resolves
    the plan + an engine-ready reviewed bore-log, runs the engine, and reports a drawable candidate
    (RUNNABLE) or a named blocker (BLOCKED). Mutates/creates nothing (raises contract errors -> 404)."""
    validate_customer_project_id(customer_project_id)
    validate_job_id(job_id)
    job = load_job(store_root, customer_project_id, job_id)
    plan_path, borelog_path, rbl, blockers = _resolve_inputs(
        store_root, customer_project_id, job_id, job)

    placement = bore = offset = dialect_name = None
    candidate = None
    if plan_path is not None and borelog_path is not None:
        bore, placement, offset, dialect_name = _run_engine(plan_path, borelog_path)
        if placement is None:
            blockers.append({"code": NO_PLAN_DIALECT_RECOGNIZED,
                             "reason": "No registered plan dialect recognized this plan."})
        elif placement.status == PlacementStatus.ABSTAIN:
            blockers.append({"code": ENGINE_ABSTAINED,
                             "reason": "Engine abstained: %s" % (placement.abstain_reason
                                                                 or placement.reason or "no candidate")})
        else:
            candidate = _candidate(placement)
            if candidate is None or not candidate.bbox:
                placement = None
                blockers.append({"code": ENGINE_ABSTAINED,
                                 "reason": "Engine placed a candidate with no drawable geometry."})

    runnable = candidate is not None and bool(getattr(candidate, "bbox", None))
    out = {
        "status": STATUS_RUNNABLE if runnable else STATUS_BLOCKED,
        "runnable": runnable,
        "reviewed_bore_log_id": rbl.get("reviewed_bore_log_id") if rbl else None,
        "dialect": dialect_name,
        "blockers": blockers,
    }
    if runnable:
        out["candidate"] = {
            "placement_status": placement.status.value,
            "reason": placement.reason,
            "caveats": list(placement.caveats) + _adapter_caveats(bore, placement),
            "sheet": candidate.sheet,
            "referenced_sheets": list(bore.sheet_refs),
            "drawn_extent": candidate.text,
            "bore_span": "%s->%s" % (bore.station_start, bore.station_end),
            "render_tier": ("solid" if placement.status == PlacementStatus.AUTO_SELECT else "dashed"),
        }
    return out


def _manifest_input(log_id, *, placement, bore, sheet, artifact_path, project_id) -> dict:
    """Job-local single-log manifest for the engine-rendered redline (mock_example:false)."""
    status_value = placement.status.value
    provenance = _PROVENANCE_BY_STATUS.get(status_value, "OWNER_CONFIRMED_HUMAN_ADJUSTABLE")
    auto = status_value == PlacementStatus.AUTO_SELECT.value
    log = {
        "log_id": log_id, "parent_id": log_id, "entry_role": "standalone",
        "status": "DRAWN_REDLINE", "provenance": provenance,
        "drawn": True, "covered": False, "blocked": False, "drawn_lane": "NEW_TARGETS",
        "source_sheets": [sheet],
        "span": {"start_station": bore.station_start, "end_station": bore.station_end,
                 "label": "%s->%s" % (bore.station_start, bore.station_end)},
        "closure": None, "coverage": None, "blocker": None,
        "artifacts": [{"kind": "FINAL_REDLINE_PNG", "sheet": sheet, "path": artifact_path,
                       "sha256": None, "example_placeholder": True}],
        "evidence": [],
        "warnings": (["engine %s placement (%s); rendered from the plan's own drawn geometry"
                      % (status_value, placement.reason)]
                     + list(placement.caveats) + _adapter_caveats(bore, placement)),
    }
    return {
        "schema_version": "1.0.0", "mock_example": False,
        "disclaimer": "Uploaded-corpus engine redline bundle (bundle_origin UPLOADED_CORPUS_ENGINE): the "
                      "engine's placement for an uploaded plan + reviewed bore-log, rendered from the plan's "
                      "own drawn geometry. %s — NOT human-clicked, NOT a recognized-corpus replay, NOT part "
                      "of the deterministic frontier."
                      % ("SOLID = AUTO" if auto else "DASHED = REVIEW (human-adjustable)"),
        "project_id": project_id, "project_name": project_id,
        "engine": {"branch": "feat/truelinev2", "engine_head": RENDER_ENGINE_HEAD,
                   "render_commit": RENDER_ENGINE_HEAD, "generated_from": "uploaded_corpus_engine_handoff"},
        "bundle_origin": BUNDLE_ORIGIN_UPLOADED_CORPUS_ENGINE,
        "summary": {"total_logs": 1, "drawn_count": 1, "covered_count": 0, "blocked_count": 0,
                    "frontier": "1/1"},
        "status_counts": {"DRAWN_REDLINE": 1, "COVERED_BY_EXISTING_REDLINE": 0, "OWNER_LOCKED_ABSTAIN": 0,
                          "SOURCE_GAP_BLOCKED": 0, "MISSING_SOURCE_SHEET_BLOCKED": 0},
        "provenance_counts": {"DETERMINISTIC_AUTO": 1 if auto else 0,
                              "OWNER_CONFIRMED_HUMAN_ADJUSTABLE": 0 if auto else 1,
                              "COVERED_BY_EXISTING_REDLINE": 0, "BLOCKED_OWNER_LOCKED": 0,
                              "BLOCKED_SOURCE_GAP": 0, "BLOCKED_MISSING_SOURCE": 0},
        "consumption_rules": [
            "Consume only this manifest for drawn/covered/blocked truth.",
            "Uploaded-corpus engine single-log subset; NOT the unified all-50 bundle.",
        ],
        "logs": [log],
    }


def _summary(store_root, customer_project_id, job_id, handoff, *, log_id, placement, dialect_name) -> dict:
    ab = handoff.get("artifact_bundle_attachment") or {}
    mf = handoff.get("manifest_attachment") or {}
    bundle_id = ab.get("bundle_id")
    arts = []
    if bundle_id:
        bundle_store = job_dir(store_root, customer_project_id, job_id) / BUNDLE_STORE_SUBDIR
        bundle = StaticBundleConsumer(bundle_store, enable=True).open_bundle(bundle_id)
        for lid, art in bundle.final_artifacts():
            arts.append({"log_id": lid, "path": art.get("path"), "sha256": art.get("sha256"),
                         "bytes": art.get("bytes"), "kind": art.get("kind")})
    return {
        "status": handoff["status"], "bundle_id": bundle_id,
        "bundle_origin": BUNDLE_ORIGIN_UPLOADED_CORPUS_ENGINE,
        "placement_status": placement.status.value, "reason": placement.reason,
        "dialect": dialect_name, "log_id": log_id,
        "artifact_count": ab.get("artifact_count"), "artifacts": arts,
        "redline_manifest_slot": mf.get("store_relative_path"),
        "artifact_bundle_slot": ab.get("store_relative_path"),
    }


def render_uploaded_corpus_engine_handoff(store_root, customer_project_id, job_id, *, at, by) -> dict:
    """Run the engine; if it places a drawable candidate, render the redline stroke along the DRAWN route and
    publish it as a job-local FINAL_REDLINE_PNG bundle (bundle_origin UPLOADED_CORPUS_ENGINE), setting the
    job's redline_manifest + artifact_bundle slots via the existing handoff. Idempotent by content. Raises
    UploadedCorpusEngineError if not runnable / failed."""
    validate_customer_project_id(customer_project_id)
    validate_job_id(job_id)
    job = load_job(store_root, customer_project_id, job_id)
    plan_path, borelog_path, rbl, blockers = _resolve_inputs(
        store_root, customer_project_id, job_id, job)
    if plan_path is None or borelog_path is None or rbl is None:
        raise UploadedCorpusEngineError("not runnable: %s" % "; ".join(b["code"] for b in blockers))

    bore, placement, offset, dialect_name = _run_engine(plan_path, borelog_path)
    candidate = _candidate(placement)
    if candidate is None or not candidate.bbox:
        ev = evaluate_uploaded_corpus_engine_handoff(store_root, customer_project_id, job_id)
        raise UploadedCorpusEngineError("not runnable: %s"
                                        % "; ".join(b["code"] for b in ev["blockers"]))

    log_id = rbl["reviewed_bore_log_id"]                       # generic, name-free artifact/log id
    sheet = candidate.sheet
    x0, y0, x1, y1 = candidate.bbox
    stroke_points = [(float(x0), float(y0)), (float(x1), float(y1))]

    # Idempotent content key over (plan, bore-log, placement geometry): identical content -> same bundle.
    key_blob = json.dumps({"plan": plan_path.name, "bore": borelog_path.name, "log": log_id,
                           "sheet": sheet, "extent": [x0, y0, x1, y1],
                           "status": placement.status.value}, sort_keys=True).encode("utf-8")
    engine_run_id = "uce-render-%s" % hashlib.sha256(key_blob).hexdigest()[:16]

    try:
        prior = load_handoff(store_root, customer_project_id, job_id, engine_run_id)
        if prior.get("status") == SUCCEEDED:
            return _summary(store_root, customer_project_id, job_id, prior,
                            log_id=log_id, placement=placement, dialect_name=dialect_name)
    except HandoffNotFoundError:
        pass

    staging_root = job_dir(store_root, customer_project_id, job_id) / ENGINE_OUTPUTS_SUBDIR
    render_src = staging_root / ("_uce_src_%s" % engine_run_id)
    render_src.mkdir(parents=True, exist_ok=True)

    plan = PlanPdf(str(plan_path))
    try:
        png = render_redline_stroke(
            plan, bore_id=log_id, sheet=sheet, offset=offset, stroke_points=stroke_points,
            status=placement.status.value, reason=placement.reason, out_dir=str(render_src))
    finally:
        plan.close()
    if not png:
        raise UploadedCorpusEngineError("renderer produced no stroke for the engine candidate")

    artifact_path = "artifacts/%s/%s" % (log_id, Path(png).name)
    artifact_map = {artifact_path: png}
    manifest_input = _manifest_input(
        log_id, placement=placement, bore=bore, sheet=sheet, artifact_path=artifact_path,
        project_id=customer_project_id)
    input_path = render_src / "_input_manifest.json"
    input_path.write_text(json.dumps(manifest_input, indent=2), encoding="utf-8")

    published = publish_manifest(str(input_path), None, str(staging_root), engine_run_id,
                                 artifact_map=artifact_map)
    record_handoff_attempt(store_root, customer_project_id, job_id, log_id, engine_run_id,
                           engine_run_status="uploaded-corpus-engine", at=at, by=by)
    handoff = finalize_handoff(store_root, customer_project_id, job_id, engine_run_id,
                               published["publish_dir"], at=at, by=by)
    if handoff.get("status") != SUCCEEDED:
        raise UploadedCorpusEngineError("engine handoff did not succeed (%s): %s"
                                        % (handoff.get("status"), "; ".join(handoff.get("errors") or [])))
    return _summary(store_root, customer_project_id, job_id, handoff,
                    log_id=log_id, placement=placement, dialect_name=dialect_name)
