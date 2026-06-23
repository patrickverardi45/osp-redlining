"""Recognized-corpus auto-handoff — a NARROW, honest bridge from a POSITIVELY-RECOGNIZED uploaded plan
corpus to the EXISTING deterministic engine render, with NO manual source-anchor clicks.

This is NOT arbitrary uploaded-corpus support, and it bakes in NO customer/project/location names: the set
of recognized corpora (their display name + exact plan/bore-log content sha256 fingerprints + the
deterministic log id each bore-log maps to) is DEPLOYMENT DATA, supplied as a registry JSON (env
``TL2_RECOGNIZED_CORPUS_REGISTRY``). Unset/missing registry => nothing is recognized => everything BLOCKED.

It fires ONLY when:
  (a) an uploaded PLAN_PDF's exact content sha256 is listed for a registry corpus, AND
  (b) an engine-ready reviewed_bore_log's source BORE_LOG upload sha256 maps (in that corpus) to a DRAWN
      deterministic log id, AND
  (c) that log has committed deterministic redline-stroke render artifacts on disk.

When recognized it serves the EXISTING committed deterministic redline PNG(s) for that log (render commit
c19b565) as a job-local product bundle (kind FINAL_REDLINE_PNG), published through the EXISTING
publisher/store/handoff spine, with top-level ``bundle_origin = DETERMINISTIC_RECOGNIZED_CORPUS`` and per-log
provenance ``DETERMINISTIC_AUTO`` — ENGINE-derived, NOT human-clicked. It touches NO engine / renderer /
solver / anchor / dialect code: it only READS the committed render PNGs + upload fingerprints and REUSES the
contract publish chain, and it does NOT change the deterministic 50/58 frontier (a separate, job-local
bundle).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from truelinev2.contracts.customer_project import validate_customer_project_id
from truelinev2.contracts.processing_job import job_dir, load_job, validate_job_id
from truelinev2.contracts.reviewed_bore_log import is_engine_ready, list_reviewed_bore_logs
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

PLAN_PDF_KIND = "PLAN_PDF"
ENGINE_OUTPUTS_SUBDIR = "engine_outputs"
STATUS_RUNNABLE = "RUNNABLE"
STATUS_BLOCKED = "BLOCKED"
BUNDLE_ORIGIN_DETERMINISTIC_RECOGNIZED_CORPUS = "DETERMINISTIC_RECOGNIZED_CORPUS"
RECOGNIZED_RENDER_COMMIT = "c19b565"
# Name-FREE public label for the API/UI. The registry ``display_name`` (a real customer/location/project
# name) NEVER crosses the API to the product frontend — only this generic label + a generic corpus id do.
RECOGNIZED_PACKAGE_LABEL = "Recognized uploaded project package"

# Named blockers (honest; present when NOT recognized / not runnable).
RECOGNIZED_CORPUS_REGISTRY_NOT_CONFIGURED = "RECOGNIZED_CORPUS_REGISTRY_NOT_CONFIGURED"
UPLOADED_CORPUS_NOT_RECOGNIZED = "UPLOADED_CORPUS_NOT_RECOGNIZED"
UPLOADED_CORPUS_AUTO_HANDOFF_NOT_IMPLEMENTED = "UPLOADED_CORPUS_AUTO_HANDOFF_NOT_IMPLEMENTED"
NO_PLAN_PDF_UPLOAD = "NO_PLAN_PDF_UPLOAD"
NO_ENGINE_READY_REVIEWED_BORE_LOG = "NO_ENGINE_READY_REVIEWED_BORE_LOG"
BORE_LOG_NOT_MAPPED_TO_DETERMINISTIC_LOG = "BORE_LOG_NOT_MAPPED_TO_DETERMINISTIC_LOG"
NO_DETERMINISTIC_RENDER_FOR_LOG = "NO_DETERMINISTIC_RENDER_FOR_LOG"

# Committed deterministic render outputs (READ-ONLY; the engine's render at commit c19b565). Generic path.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_DETERMINISTIC_RENDER_DIR = _REPO_ROOT / "data" / "outputs" / "callout_route_assembly_sweep"


class RecognizedCorpusError(Exception):
    """Recognized-corpus handoff is not runnable / did not succeed."""


def load_registry(path) -> dict:
    """Load the DEPLOYMENT-provided recognized-corpus registry JSON (real corpus names + content
    fingerprints are deployment data, never baked into code). Returns ``{"corpora": [...], "configured":
    bool}``. ``configured`` is True ONLY when a registry file was actually loaded (a deployment wired
    ``TL2_RECOGNIZED_CORPUS_REGISTRY`` at a readable JSON file) — even if it holds zero corpora. It is False
    when ``path`` is falsy / missing / unreadable: an OPERATIONAL gap (no registry on this deployment),
    which is honestly DISTINCT from "this plan is not in the registry". Either way an empty/unloaded
    registry => nothing recognized => everything BLOCKED."""
    if not path:
        return {"corpora": [], "configured": False}
    p = Path(path)
    if not p.is_file():
        return {"corpora": [], "configured": False}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {"corpora": [], "configured": False}
    corpora = data.get("corpora") if isinstance(data, dict) else None
    return {"corpora": corpora if isinstance(corpora, list) else [], "configured": True}


def _uploads_of_kind(job, kind):
    return [u for u in job.get("uploads", []) if u.get("kind") == kind]


def _public_corpus_id(corpus, registry):
    """Name-FREE corpus identifier for the API/UI. Prefers the deployment-provided generic ``corpus_id``;
    falls back to a positional ``recognized-corpus-NNN``. NEVER the registry ``display_name`` — no
    customer/operator/location/project names cross the API to the product frontend (those stay in the
    gitignored deployment registry only)."""
    if not corpus:
        return None
    cid = corpus.get("corpus_id")
    if isinstance(cid, str) and cid.strip():
        return cid.strip()
    try:
        idx = list(registry.get("corpora", [])).index(corpus)
    except ValueError:
        idx = 0
    return "recognized-corpus-%03d" % (idx + 1)


def _deterministic_artifacts(log_id):
    """(manifest_path, source_png_path, sheet) for each committed render PNG of ``log_id`` — globbed from
    the committed deterministic render dir. Empty if the log has no drawn deterministic render."""
    out = []
    if not log_id:
        return out
    for png in sorted(_DETERMINISTIC_RENDER_DIR.glob("%s_s*_redline_stroke.png" % log_id)):
        try:
            sheet = int(png.stem.split("_s", 1)[1].split("_", 1)[0])
        except (IndexError, ValueError):
            continue
        out.append(("artifacts/%s/%s" % (log_id, png.name), png, sheet))
    return out


def _recognize(store_root, customer_project_id, job_id, registry, job):
    """Pure recognition over the registry + job: returns (corpus, mapped_log_id, rbl_id, ready_rbls). corpus
    is the matched registry entry (dict) or None; mapped_log_id/rbl_id are set only when a recognized plan
    AND an engine-ready reviewed_bore_log whose source upload maps to a deterministic log are both present."""
    plan_uploads = _uploads_of_kind(job, PLAN_PDF_KIND)
    plan_shas = {u.get("sha256") for u in plan_uploads if u.get("sha256")}
    corpus = next((c for c in registry.get("corpora", [])
                   if any(s in plan_shas for s in (c.get("plan_sha256") or []))), None)
    bore_map = (corpus.get("bore_log_sha256_to_log") or {}) if corpus else {}
    ready_rbls = [r for r in list_reviewed_bore_logs(store_root, customer_project_id, job_id)
                  if is_engine_ready(r)]
    rbl_id = mapped_log = None
    for r in ready_rbls:
        up = next((u for u in job.get("uploads", []) if u.get("upload_id") == r.get("source_upload_id")), None)
        if up and up.get("sha256") in bore_map:
            rbl_id, mapped_log = r.get("reviewed_bore_log_id"), bore_map[up["sha256"]]
            break
    return corpus, mapped_log, rbl_id, ready_rbls, plan_uploads


def evaluate_recognized_corpus_handoff(store_root, customer_project_id, job_id, *, registry) -> dict:
    """Read-only: is this job's RECOGNIZED uploaded corpus eligible for an automatic deterministic redline?
    RUNNABLE only when a PLAN_PDF sha256 is a registry corpus plan AND an engine-ready reviewed_bore_log's
    source BORE_LOG sha256 maps (in that corpus) to a DRAWN deterministic log with committed render
    artifacts. Otherwise BLOCKED with named blockers. Mutates/creates nothing (raises contract errors →
    404). ``registry`` is the deployment data (see ``load_registry``)."""
    validate_customer_project_id(customer_project_id)
    validate_job_id(job_id)
    job = load_job(store_root, customer_project_id, job_id)
    corpus, mapped_log, rbl_id, ready_rbls, plan_uploads = _recognize(
        store_root, customer_project_id, job_id, registry, job)
    artifacts = _deterministic_artifacts(mapped_log)
    configured = bool(registry.get("configured"))

    blockers = []
    if not plan_uploads:
        blockers.append({"code": NO_PLAN_PDF_UPLOAD, "reason": "Job has no PLAN_PDF upload."})
    if corpus is None:
        if not configured:
            # OPERATIONAL gap: the deployment has no recognized-corpus registry loaded (the staging cause).
            # Honestly DISTINCT from "your plan is unknown" — a configured registry just lacks this plan.
            blockers.append({"code": RECOGNIZED_CORPUS_REGISTRY_NOT_CONFIGURED,
                             "reason": "No recognized-corpus registry is configured on this deployment "
                                       "(TL2_RECOGNIZED_CORPUS_REGISTRY is unset or unreadable), so no "
                                       "uploaded plan can be recognized."})
        else:
            blockers.append({"code": UPLOADED_CORPUS_NOT_RECOGNIZED,
                             "reason": "Uploaded PLAN_PDF is not a recognized known corpus (no exact sha256 match)."})
            blockers.append({"code": UPLOADED_CORPUS_AUTO_HANDOFF_NOT_IMPLEMENTED,
                             "reason": "Automatic redline handoff is implemented only for recognized corpora."})
    if not ready_rbls:
        blockers.append({"code": NO_ENGINE_READY_REVIEWED_BORE_LOG,
                         "reason": "No reviewed_bore_log has passed the engine-readiness gate."})
    elif corpus is not None and mapped_log is None:
        blockers.append({"code": BORE_LOG_NOT_MAPPED_TO_DETERMINISTIC_LOG,
                         "reason": "No engine-ready reviewed bore-log's source upload maps to a known "
                                   "deterministic drawn log."})
    if corpus is not None and mapped_log is not None and not artifacts:
        blockers.append({"code": NO_DETERMINISTIC_RENDER_FOR_LOG,
                         "reason": "Recognized log %r has no committed deterministic render artifacts."
                                   % mapped_log})

    runnable = bool(corpus and mapped_log and artifacts and ready_rbls)
    return {
        "status": STATUS_RUNNABLE if runnable else STATUS_BLOCKED,
        "runnable": runnable,
        "recognized_corpus_id": _public_corpus_id(corpus, registry),
        "recognized_package_label": RECOGNIZED_PACKAGE_LABEL if corpus else None,
        "deterministic_log_id": mapped_log if runnable else None,
        "render_sheets": [s for (_p, _s, s) in artifacts] if runnable else [],
        "render_commit": RECOGNIZED_RENDER_COMMIT if runnable else None,
        "reviewed_bore_log_id": rbl_id if runnable else None,
        "blockers": blockers,
    }


def _build_manifest_input(log_id, artifacts, *, project_id, corpus_ref, log_facts) -> dict:
    sheets = sorted({s for (_m, _src, s) in artifacts})
    facts = log_facts or {}
    log = {
        "log_id": log_id, "parent_id": facts.get("parent_id", log_id), "entry_role": "standalone",
        "status": "DRAWN_REDLINE", "provenance": "DETERMINISTIC_AUTO",
        "drawn": True, "covered": False, "blocked": False, "drawn_lane": "NEW_TARGETS",
        "source_sheets": sheets,
        "span": facts.get("span", {"start_station": "0+00", "end_station": "0+00", "label": "0+00"}),
        "closure": None, "coverage": None, "blocker": None,
        "artifacts": [{"kind": "FINAL_REDLINE_PNG", "sheet": s, "path": mpath,
                       "sha256": None, "example_placeholder": True}
                      for (mpath, _src, s) in artifacts],
        "evidence": [
            {"kind": "SWEEP_CONSTANT", "ref": "callout_route_assembly_sweep",
             "note": "deterministic engine redline render for recognized corpus log %s (render commit %s)"
                     % (log_id, RECOGNIZED_RENDER_COMMIT)},
            {"kind": "ACCOUNTABILITY_LEDGER", "ref": "wiki/trueline_v2_50_of_58_accountability_table.md",
             "note": "%s is a DRAWN deterministic log in the committed 50/58 accountability" % log_id},
        ],
        "warnings": [],
    }
    return {
        "schema_version": "1.0.0", "mock_example": False,
        "disclaimer": "Recognized-corpus deterministic redline bundle (bundle_origin "
                      "DETERMINISTIC_RECOGNIZED_CORPUS): the engine's committed redline for a POSITIVELY "
                      "recognized uploaded project package (%s). NOT human-clicked, NOT arbitrary upload "
                      "support." % corpus_ref,
        "project_id": project_id, "project_name": project_id,
        "engine": {"branch": "feat/truelinev2", "engine_head": "deterministic-recognized-corpus",
                   "render_commit": RECOGNIZED_RENDER_COMMIT, "generated_from": "recognized_corpus_handoff"},
        "bundle_origin": BUNDLE_ORIGIN_DETERMINISTIC_RECOGNIZED_CORPUS,
        "summary": {"total_logs": 1, "drawn_count": 1, "covered_count": 0, "blocked_count": 0,
                    "frontier": "1/1"},
        "status_counts": {"DRAWN_REDLINE": 1, "COVERED_BY_EXISTING_REDLINE": 0, "OWNER_LOCKED_ABSTAIN": 0,
                          "SOURCE_GAP_BLOCKED": 0, "MISSING_SOURCE_SHEET_BLOCKED": 0},
        "provenance_counts": {"DETERMINISTIC_AUTO": 1, "OWNER_CONFIRMED_HUMAN_ADJUSTABLE": 0,
                              "COVERED_BY_EXISTING_REDLINE": 0, "BLOCKED_OWNER_LOCKED": 0,
                              "BLOCKED_SOURCE_GAP": 0, "BLOCKED_MISSING_SOURCE": 0},
        "consumption_rules": [
            "Consume only this manifest for drawn/covered/blocked truth.",
            "Recognized-corpus deterministic single-log subset; NOT the unified all-50 bundle.",
        ],
        "logs": [log],
    }


def _summary(store_root, customer_project_id, job_id, handoff, corpus_id, mapped_log) -> dict:
    ab = handoff.get("artifact_bundle_attachment") or {}
    mf = handoff.get("manifest_attachment") or {}
    bundle_id = ab.get("bundle_id")
    arts = []
    if bundle_id:
        bundle_store = job_dir(store_root, customer_project_id, job_id) / BUNDLE_STORE_SUBDIR
        bundle = StaticBundleConsumer(bundle_store, enable=True).open_bundle(bundle_id)
        for log_id, art in bundle.final_artifacts():
            arts.append({"log_id": log_id, "path": art.get("path"), "sha256": art.get("sha256"),
                         "bytes": art.get("bytes"), "kind": art.get("kind")})
    return {
        "status": handoff["status"], "bundle_id": bundle_id,
        "bundle_origin": BUNDLE_ORIGIN_DETERMINISTIC_RECOGNIZED_CORPUS,
        "recognized_corpus_id": corpus_id,
        "recognized_package_label": RECOGNIZED_PACKAGE_LABEL,
        "deterministic_log_id": mapped_log,
        "render_commit": RECOGNIZED_RENDER_COMMIT,
        "artifact_count": ab.get("artifact_count"), "artifacts": arts,
        "redline_manifest_slot": mf.get("store_relative_path"),
        "artifact_bundle_slot": ab.get("store_relative_path"),
    }


def render_recognized_corpus_handoff(store_root, customer_project_id, job_id, *, registry, at, by) -> dict:
    """If the job's recognized corpus is RUNNABLE, publish the EXISTING deterministic render PNG(s) for the
    mapped log as a job-local product bundle (FINAL_REDLINE_PNG, bundle_origin
    DETERMINISTIC_RECOGNIZED_CORPUS), setting the job's redline_manifest + artifact_bundle slots via the
    existing handoff. Idempotent by content. Raises RecognizedCorpusError if not runnable / failed."""
    validate_customer_project_id(customer_project_id)
    validate_job_id(job_id)
    job = load_job(store_root, customer_project_id, job_id)
    corpus, mapped_log, rbl_id, ready_rbls, _plan = _recognize(
        store_root, customer_project_id, job_id, registry, job)
    artifacts = _deterministic_artifacts(mapped_log)
    if not (corpus and mapped_log and artifacts and ready_rbls):
        ev = evaluate_recognized_corpus_handoff(store_root, customer_project_id, job_id, registry=registry)
        raise RecognizedCorpusError("recognized-corpus handoff is not runnable: %s"
                                    % "; ".join(b["code"] for b in ev["blockers"]))
    artifact_map = {mpath: str(src) for (mpath, src, _s) in artifacts}
    corpus_id = _public_corpus_id(corpus, registry)

    key_blob = json.dumps({"corpus": corpus_id, "log": mapped_log,
                           "artifacts": sorted(artifact_map.keys())}, sort_keys=True).encode("utf-8")
    engine_run_id = "rc-render-%s" % hashlib.sha256(key_blob).hexdigest()[:16]

    try:
        prior = load_handoff(store_root, customer_project_id, job_id, engine_run_id)
        if prior.get("status") == SUCCEEDED:
            return _summary(store_root, customer_project_id, job_id, prior, corpus_id, mapped_log)
    except HandoffNotFoundError:
        pass

    staging_root = job_dir(store_root, customer_project_id, job_id) / ENGINE_OUTPUTS_SUBDIR
    render_src = staging_root / ("_rc_src_%s" % engine_run_id)
    render_src.mkdir(parents=True, exist_ok=True)
    manifest_input = _build_manifest_input(
        mapped_log, artifacts, project_id=customer_project_id,
        corpus_ref=corpus_id, log_facts=(corpus.get("log_facts") or {}).get(mapped_log))
    input_path = render_src / "_input_manifest.json"
    input_path.write_text(json.dumps(manifest_input, indent=2), encoding="utf-8")

    published = publish_manifest(str(input_path), None, str(staging_root), engine_run_id,
                                 artifact_map=artifact_map)
    record_handoff_attempt(store_root, customer_project_id, job_id, rbl_id, engine_run_id,
                           engine_run_status="deterministic-recognized-corpus", at=at, by=by)
    handoff = finalize_handoff(store_root, customer_project_id, job_id, engine_run_id,
                               published["publish_dir"], at=at, by=by)
    if handoff.get("status") != SUCCEEDED:
        raise RecognizedCorpusError("recognized-corpus handoff did not succeed (%s): %s"
                                    % (handoff.get("status"), "; ".join(handoff.get("errors") or [])))
    return _summary(store_root, customer_project_id, job_id, handoff, corpus_id, mapped_log)
