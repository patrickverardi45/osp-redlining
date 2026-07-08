"""M2 render adapter — render a job's VALIDATED human-confirmed source anchors into a real published
redline bundle, reusing the existing publisher/store/handoff spine.

This is NOT a pure contract: it opens the uploaded PLAN_PDF (PlanPdf) and calls the renderer
(render_redline_stroke). It draws ONLY the human-confirmed control points already stored on each source
anchor — it infers no geometry, solves no stations, does no nearest/length matching, and touches NO
dialect / match / endpoint / solver code. Output is a dashed REVIEW stroke (human-adjustable), published
as a `mock_example:false` bundle with `bundle_origin = HUMAN_CONFIRMED_SOURCE_ANCHOR` (NOT deterministic,
NOT part of the 50/58 frontier). Truth + validation stay in the contracts (publisher/store/handoff).

Idempotent by content: the engine_run_id is derived from the rendered anchor set, so re-rendering the same
content returns the existing SUCCEEDED bundle; adding/changing an anchor produces a new content-keyed
bundle and repoints the job's output slots.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from truelinev2.ingest.pdf import PlanPdf
from truelinev2.ingest.sheet_label_index import build_sheet_index, construction_sheet_for_page
from truelinev2.render.crop import render_redline_stroke
from truelinev2.render.station_dots import (
    compute_station_dots,
    dot_xys,
    resolve_bore_fields,
    stroke_polyline_with_dots,
)
from truelinev2.contracts.processing_job import job_dir, load_job
from truelinev2.contracts.reviewed_bore_log import (
    ReviewedBoreLogNotFoundError,
    is_engine_ready,
    load_reviewed_bore_log,
)
from truelinev2.contracts.source_anchor import (
    BUNDLE_ORIGIN_HUMAN_CONFIRMED,
    PLAN_PDF_KIND,
    STATUS_VALIDATED,
    SourceAnchorStateError,
    build_source_anchor_manifest,
    list_source_anchors,
    load_source_anchor,
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
from truelinev2.contracts.review_acceptance import (
    supersede_review_candidate_for_reviewed_bore_log,
)

ENGINE_OUTPUTS_SUBDIR = "engine_outputs"
RENDER_STATUS = "REVIEW"                       # dashed, human-adjustable — NEVER AUTO_SELECT (solid)
RENDER_ENGINE_HEAD = "human-confirmed-source-anchor"   # not a deterministic render commit


def _stroke_points(sa) -> list:
    return [(float(p["x"]), float(p["y"])) for p in sa.get("control_points", [])]


def _dots_for_anchor(store_root, customer_project_id, job_id, sa) -> tuple:
    """Interval/footage dots for one anchor + the reviewed-row footage used to self-calibrate them. Best-effort
    and NON-FATAL: any missing row/footage -> ([], None) so the render still draws the bare human redline. Reads
    the reviewed_bore_log (already validated at anchor creation) for the row's footage/start-station/log info;
    infers NO geometry (dots are interpolated only along the human control-point polyline)."""
    try:
        rbl = load_reviewed_bore_log(store_root, customer_project_id, job_id, sa["reviewed_bore_log_id"])
    except ReviewedBoreLogNotFoundError:
        return [], None
    rows = rbl.get("rows", [])
    row_ids = sa.get("row_ids") or []
    row = next((r for r in rows if r.get("row_id") in row_ids), None) if row_ids else (rows[0] if rows else None)
    fields = resolve_bore_fields(row)
    footage = fields["footage"]
    if not footage or footage <= 0:
        return [], None
    info = dict(fields["info"])
    if not info.get("bore_log_id"):                    # fall back to the reviewed-bore-log id when the row
        info["bore_log_id"] = sa.get("reviewed_bore_log_id")   # carries no explicit bore id
    dots = compute_station_dots(sa.get("control_points", []), footage=footage,
                                start_station=fields["start_station"], info=info)
    return dots, footage


def _plan_path_for(store_root, customer_project_id, job_id, job, plan_upload_id):
    upload = next((u for u in job.get("uploads", []) if u.get("upload_id") == plan_upload_id), None)
    if upload is None or upload.get("kind") != PLAN_PDF_KIND:
        return None
    path = job_dir(store_root, customer_project_id, job_id) / upload.get("stored_path", "")
    return path if path.is_file() else None


def _require_renderable(sa, source_anchor_id) -> None:
    if sa.get("status") != STATUS_VALIDATED or sa.get("renderable") is not True:
        raise SourceAnchorStateError(
            "source_anchor %r is not VALIDATED/renderable (status=%s, renderable=%s)"
            % (source_anchor_id, sa.get("status"), sa.get("renderable")))


def _content_key(anchors) -> str:
    """Deterministic key over the rendered set (ids + page + control points). Same content -> same key ->
    idempotent bundle; changed content -> new key -> new content-keyed bundle."""
    canon = [{"id": a["source_anchor_id"], "page": a["page_number"],
              "points": a.get("control_points", [])} for a in anchors]
    blob = json.dumps(canon, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def _summary(store_root, customer_project_id, job_id, handoff, anchor_ids) -> dict:
    """Render summary built from the finalized handoff + the durable bundle (manifest-backed read)."""
    ab = handoff.get("artifact_bundle_attachment") or {}
    mf = handoff.get("manifest_attachment") or {}
    bundle_id = ab.get("bundle_id")
    artifacts = []
    if bundle_id:
        bundle_store = job_dir(store_root, customer_project_id, job_id) / BUNDLE_STORE_SUBDIR
        bundle = StaticBundleConsumer(bundle_store, enable=True).open_bundle(bundle_id)
        for log_id, art in bundle.final_artifacts():
            artifacts.append({"log_id": log_id, "path": art.get("path"), "sha256": art.get("sha256"),
                              "bytes": art.get("bytes"), "kind": art.get("kind")})
    return {
        "status": handoff["status"],
        "bundle_id": bundle_id,
        "bundle_origin": BUNDLE_ORIGIN_HUMAN_CONFIRMED,
        "artifact_count": ab.get("artifact_count"),
        "source_anchor_ids": list(anchor_ids),
        "artifacts": artifacts,
        "redline_manifest_slot": mf.get("store_relative_path"),
        "artifact_bundle_slot": ab.get("store_relative_path"),
    }


def render_job_source_anchors(store_root, customer_project_id, job_id, source_anchor_id, *, at, by) -> dict:
    """Render ALL currently VALIDATED/renderable source anchors of a job (the job has ONE artifact-bundle
    slot, so a render assembles the job's complete human-confirmed set) and publish them as one real
    bundle, setting the job's redline_manifest + artifact_bundle slots via the existing handoff. The
    requested anchor must itself be VALIDATED/renderable. Renders nothing automatic; draws only stored
    control points. Returns a render/bundle/artifact summary."""
    job = load_job(store_root, customer_project_id, job_id)                 # exists + isolation (404)
    trigger = load_source_anchor(store_root, customer_project_id, job_id, source_anchor_id)  # 404 if none
    _require_renderable(trigger, source_anchor_id)

    anchors = [a for a in list_source_anchors(store_root, customer_project_id, job_id)
               if a.get("status") == STATUS_VALIDATED and a.get("renderable") is True]
    anchors.sort(key=lambda a: a["source_anchor_id"])                       # deterministic order

    # Freshness gate (finalize_handoff independently re-gates on this too): the triggering anchor's
    # reviewed_bore_log must still exist and be engine-ready.
    rbl_id = trigger["reviewed_bore_log_id"]
    try:
        rbl = load_reviewed_bore_log(store_root, customer_project_id, job_id, rbl_id)
    except ReviewedBoreLogNotFoundError as exc:
        raise SourceAnchorStateError("reviewed_bore_log %r no longer exists" % rbl_id) from exc
    if not is_engine_ready(rbl):
        raise SourceAnchorStateError("reviewed_bore_log %r is no longer engine-ready" % rbl_id)

    engine_run_id = "sa-render-%s" % _content_key(anchors)
    anchor_ids = [a["source_anchor_id"] for a in anchors]

    # Idempotent: identical content already published -> return the existing bundle summary, re-render none.
    try:
        prior = load_handoff(store_root, customer_project_id, job_id, engine_run_id)
        if prior.get("status") == SUCCEEDED:
            return _summary(store_root, customer_project_id, job_id, prior, anchor_ids)
    except HandoffNotFoundError:
        pass

    staging_root = job_dir(store_root, customer_project_id, job_id) / ENGINE_OUTPUTS_SUBDIR
    render_src = staging_root / ("_render_src_%s" % _content_key(anchors))
    render_src.mkdir(parents=True, exist_ok=True)

    entries, artifact_map = [], {}
    sheet_index_cache = {}
    for sa in anchors:
        sa_id = sa["source_anchor_id"]
        plan_path = _plan_path_for(store_root, customer_project_id, job_id, job, sa["plan_upload_id"])
        if plan_path is None:
            raise SourceAnchorStateError("PLAN_PDF for source_anchor %r is not available" % sa_id)
        page = int(sa["page_number"])                       # 1-based PDF page index the stroke renders on
        # Additive: interval/footage dots along THIS human redline (best-effort; [] never blocks the render).
        dots, footage = _dots_for_anchor(store_root, customer_project_id, job_id, sa)
        if dots and footage:                            # augment the drawn polyline so the dot marks get rings
            stroke_pts = stroke_polyline_with_dots(sa.get("control_points", []), footage=footage)
            mandatory = tuple(dot_xys(dots)) + ((stroke_pts[0], stroke_pts[-1]) if stroke_pts else ())
        else:
            stroke_pts, mandatory = _stroke_points(sa), ()
        plan = PlanPdf(str(plan_path))
        try:
            png = render_redline_stroke(
                plan, bore_id=sa_id, sheet=page, offset=0, stroke_points=stroke_pts,
                status=RENDER_STATUS, reason="human-confirmed source anchor %s" % sa_id,
                out_dir=str(render_src), mandatory_points=mandatory)
            # Honest sheet labelling: the manifest reports the CONSTRUCTION sheet number printed on that PDF
            # page (e.g. PDF page 20 -> "7 OF 30" -> 7), matching the unit the engine/recognized bundles use
            # for source_sheets. Falls back to the PDF page number when the page carries no plan-sheet label.
            cache_key = str(plan_path)
            if cache_key not in sheet_index_cache:
                sheet_index_cache[cache_key] = build_sheet_index(plan)
            construction_sheet = construction_sheet_for_page(sheet_index_cache[cache_key], page)
        finally:
            plan.close()
        if not png:
            raise SourceAnchorStateError("render produced no stroke for source_anchor %r" % sa_id)
        manifest_path = "artifacts/%s/%s" % (sa_id, Path(png).name)
        artifact_map[manifest_path] = png
        entries.append({"source_anchor": sa, "artifact_path": manifest_path, "sheet": page,
                        "construction_sheet": construction_sheet, "station_dots": dots})

    manifest_input = build_source_anchor_manifest(
        entries, project_id=customer_project_id, project_name=customer_project_id,
        engine_head=RENDER_ENGINE_HEAD, render_commit=RENDER_ENGINE_HEAD,
        disclaimer="Human-confirmed source-anchor redline bundle (mock_example:false).")
    input_path = render_src / "_input_manifest.json"
    input_path.write_text(json.dumps(manifest_input, indent=2), encoding="utf-8")

    published = publish_manifest(str(input_path), None, str(staging_root), engine_run_id,
                                 artifact_map=artifact_map)
    record_handoff_attempt(store_root, customer_project_id, job_id, rbl_id, engine_run_id,
                           engine_run_status="human-confirmed-source-anchor", at=at, by=by)
    handoff = finalize_handoff(store_root, customer_project_id, job_id, engine_run_id,
                               published["publish_dir"], at=at, by=by)
    if handoff.get("status") != SUCCEEDED:                                  # gate-fail / bundle-invalid
        raise SourceAnchorStateError(
            "render handoff did not succeed (%s): %s"
            % (handoff.get("status"), "; ".join(handoff.get("errors") or [])))

    # The human-confirmed render is now the authoritative redline filling this job's slot. Supersede any
    # pending/rejected engine REVIEW candidate for the same reviewed bore-log so the gated closeout/export
    # workflow no longer treats the job as un-accepted — the correction IS the placement (no false "accept"
    # of the engine's geometry). Safe no-op when there was no engine candidate (a direct source-anchor).
    bundle_id = (handoff.get("artifact_bundle_attachment") or {}).get("bundle_id")
    supersede_review_candidate_for_reviewed_bore_log(
        store_root, customer_project_id, job_id, rbl_id,
        source_anchor_bundle_id=bundle_id, at=at, by=by)
    return _summary(store_root, customer_project_id, job_id, handoff, anchor_ids)
