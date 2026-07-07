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
import re
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
from truelinev2.ingest.sheet_label_index import build_sheet_index
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.generic_geometry import GenericGeometryDialect
from truelinev2.match.engine import run_match
from truelinev2.render.crop import render_redline_stroke
from truelinev2.schema.models import Placement, PlacementStatus
from truelinev2.extract.matchline_join import see_sheet_crossings
from truelinev2.stations import parse_station

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

# Adapter-level REVIEW caveats (NOT engine caveats, NOT a coordinate/render change; never claim AUTO):
#  * CROSS_SHEET_CONTINUATION_REVIEW — the bore references multiple plan sheets; legs are rendered PER-SHEET
#    from each sheet's OWN drawn geometry and the cross-sheet continuation is NOT drawn as one connected /
#    validated route.
#  * PARTIAL_CROSS_SHEET_REVIEW — some referenced sheet has no source-supported leg, so coverage is partial.
CROSS_SHEET_CONTINUATION_REVIEW = "CROSS_SHEET_CONTINUATION_REVIEW"
PARTIAL_CROSS_SHEET_REVIEW = "PARTIAL_CROSS_SHEET_REVIEW"

# Matchline-continuity caveats (Phase 5; truthfulness only — never geometry, never AUTO):
#  * MATCHLINE_CONTINUATION_CONFIRMED_REVIEW — a printed matchline boundary-STATION equation links the
#    rendered legs across the matchline (both sheets print the SAME boundary station inside the bore span).
#  * MATCHLINE_CONTINUATION_UNVERIFIED — the station-level cross-matchline join is NOT proven.
#  * MATCHLINE_SHEET_ADJACENCY_CONFIRMED — the sheets DO print mutual matchline SEE-SHEET cross-references
#    (adjacency proven) even when no boundary station is printed (so continuity stays UNVERIFIED).
MATCHLINE_CONTINUATION_CONFIRMED_REVIEW = "MATCHLINE_CONTINUATION_CONFIRMED_REVIEW"
MATCHLINE_CONTINUATION_UNVERIFIED = "MATCHLINE_CONTINUATION_UNVERIFIED"
MATCHLINE_SHEET_ADJACENCY_CONFIRMED = "MATCHLINE_SHEET_ADJACENCY_CONFIRMED"

# Generic-geometry fallback caveats (Phase: general uploaded-project placement). The name-free
# GenericGeometryDialect reconstructs a plausible run from generic plan geometry when NO named dialect
# recognizes the plan; it is REVIEW by construction (a human confirms the inferred run) and NEVER AUTO.
GENERIC_GEOMETRY_REVIEW = "GENERIC_GEOMETRY_REVIEW"     # placement came from the name-free fallback
GENERIC_CAP_REVIEW = "GENERIC_CAP_REVIEW"               # a tight generic extent is still capped to REVIEW
_GENERIC_DIALECT_NAME = "generic"
# Convention-neutral matchline label substring; the SEE-SHEET grammar carries the partner sheet number.
_MATCHLINE_KEYWORD = "MATCH"
_SEE_SHEET_RE = re.compile(r"SEE\s*SH(?:EE)?T\s*0*(\d+)", re.I)

# Named blockers (honest; present when NOT runnable).
NO_PLAN_PDF_UPLOAD = "NO_PLAN_PDF_UPLOAD"
NO_ENGINE_READY_REVIEWED_BORE_LOG = "NO_ENGINE_READY_REVIEWED_BORE_LOG"
PLAN_PDF_FILE_NOT_AVAILABLE = "PLAN_PDF_FILE_NOT_AVAILABLE"
BORE_LOG_FILE_NOT_AVAILABLE = "BORE_LOG_FILE_NOT_AVAILABLE"
NO_PLAN_DIALECT_RECOGNIZED = "NO_PLAN_DIALECT_RECOGNIZED"
ENGINE_ABSTAINED = "ENGINE_ABSTAINED"
# The ENGINE's ingest normalizer could not read the bore-log file at all (the product extraction/readiness
# lanes are more permissive readers, so a job can look READY there while the engine lane stays blocked).
BORE_LOG_FORMAT_UNRECOGNIZED = "BORE_LOG_FORMAT_UNRECOGNIZED"


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


def _cap_review(placement):
    """Force a generic-geometry placement to REVIEW (never AUTO) and tag it. The name-free fallback is
    REVIEW by construction: it reconstructs a plausible run from generic plan geometry, which a human must
    confirm — even if ``decide_by_extent`` happened to return a tight AUTO_SELECT, the generic dialect is
    never source-tight enough to claim AUTO."""
    caveats = list(placement.caveats)
    if GENERIC_GEOMETRY_REVIEW not in caveats:
        caveats.append(GENERIC_GEOMETRY_REVIEW)
    if placement.status == PlacementStatus.AUTO_SELECT and GENERIC_CAP_REVIEW not in caveats:
        caveats.append(GENERIC_CAP_REVIEW)
    return placement.model_copy(update={"status": PlacementStatus.REVIEW, "caveats": caveats})


# --- Bore-aware generic placement (correctness + HONESTY): pick the drawn run most likely to BE the proposed
# bore, but earn confidence ONLY from real coverage + uniqueness, never from a confident guess. On a real
# plan the name-free shape detector fragments ALL linework (right-of-way / edge-of-pavement / centerline /
# utilities / alignment) into many "runs"; the proposed bore is distinguished by ANNOTATION (a CAD layer /
# a "DIRECTIONAL BORE" note) that the named dialects read but generic geometry cannot. So the generic lane
# must DETECT that ambiguity and report it honestly (LOW + correction-recommended), not paper over it. ----- #
_GENERIC_MIN_COVER = 0.5         # a run must cover >= this fraction of the bore span to be PLACED at all
_GENERIC_CONFIDENT_COVER = 0.85  # below this, coverage is PARTIAL -> the placement can never exceed low-MEDIUM
_GENERIC_HIGH_COVER = 0.90       # near-full span coverage (a REASON the run fits; no longer unlocks a HIGH band)
_GENERIC_MAX_CONF = 0.70         # generic INFERENCE-lane ceiling: caps at MEDIUM, NEVER HIGH (no source-tight
                                 # per-bore evidence — see C2). PROVISIONAL — validated on one corpus (ODOT).
_GENERIC_FRAG_COVER = 0.25       # a non-baseline run covering >= this much of the span is a PLAUSIBLE RIVAL
_GENERIC_FULL_SHEET_FRAC = 0.8   # a run spanning >= this fraction of the detected sheet range = a baseline
_GENERIC_BORE_NOTE_PT = 220.0    # a printed 'BORE' note within this many display-pt weakly corroborates
_GENERIC_MAX_ALTERNATIVES = 4    # how many runner-up runs to surface for the correction step
GENERIC_RUN_MATCHES_SPAN = "GENERIC_RUN_MATCHES_BORE_SPAN"
GENERIC_PLACED_ON_ALIGNMENT = "GENERIC_PLACED_ON_ALIGNMENT_LINE_UNVERIFIED"
GENERIC_PARTIAL_SPAN = "GENERIC_PARTIAL_SPAN_COVERAGE"
GENERIC_MULTIPLE_RUNS = "GENERIC_MULTIPLE_PLAUSIBLE_RUNS"
GENERIC_CORRECTION_RECOMMENDED = "GENERIC_CORRECTION_RECOMMENDED"
NO_DRAWN_RUN_OVER_SPAN = "NO_DRAWN_RUN_OVER_SPAN"
# 'BORE' / 'DIRECTIONAL BORE' is an industry term (not a customer/project/location name), so reading it in
# the generic lane stays name-free; it is a WEAK corroboration only, never a confidence promoter.
_BORE_NOTE_RE = re.compile(r"\bBORE\b", re.I)


def _nearest_bore_note(plan, sheet, offset, bbox):
    """Display-pt distance from a run's bbox center to the nearest printed 'BORE' note word on the sheet, or
    None when there is none. Name-free corroboration only — the note typically sits well off the drawn line
    (observed 140-480pt on real plans), so it never sets geometry and never lifts the confidence band."""
    if not bbox:
        return None
    cx, cy = (bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0
    best = None
    for w in plan.words(sheet, offset):
        if _BORE_NOTE_RE.search(w.get("text") or ""):
            d = ((w["xc"] - cx) ** 2 + (w["yc"] - cy) ** 2) ** 0.5
            best = d if best is None else min(best, d)
    return round(best, 0) if best is not None else None


def _score_bore_run(sig, bore):
    """Score a drawn run for being THIS bore's proposed line. COVERAGE dominates (does the run actually span
    the bore?), then extent match + endpoint bracket; red is only a WEAK tie-breaker (right-of-way / edge
    lines are also drawn red on real plans, so red must never dominate). A full-sheet baseline is heavily
    penalized."""
    lo, hi = min(bore.station_start_ft, bore.station_end_ft), max(bore.station_start_ft, bore.station_end_ft)
    span = max(float(bore.span_ft), 1.0)
    run_lo, run_hi = float(sig.get("run_from_ft", lo)), float(sig.get("run_to_ft", hi))
    run_len = max(run_hi - run_lo, 0.0)
    sheet_span = float(sig.get("sheet_station_span_ft") or 0.0)
    cover = max(0.0, min(run_hi, hi) - max(run_lo, lo)) / (hi - lo) if hi > lo else 0.0
    extent_fit = max(0.0, 1.0 - abs(run_len - span) / span)
    end_fit = max(0.0, 1.0 - (abs(run_lo - lo) + abs(run_hi - hi)) / (2.0 * span))
    full_sheet = sheet_span > 0 and run_len >= _GENERIC_FULL_SHEET_FRAC * sheet_span
    red = bool(sig.get("is_red"))
    score = 0.40 * min(1.0, cover) + 0.30 * extent_fit + 0.25 * end_fit + (0.05 if red else 0.0)
    if full_sheet:
        score *= 0.35                                        # alignment baseline, not a per-bore run
    return {"score": round(score, 3), "cover": round(cover, 3), "extent_fit": round(extent_fit, 3),
            "end_fit": round(end_fit, 3), "full_sheet": full_sheet, "is_red": red,
            "run_extent_ft": round(run_len, 1)}


def _place_generic(bore, plan, dialect, offset):
    """Bore-aware generic placement (REVIEW only): across the bore's referenced sheets, select the drawn run
    most likely to BE the proposed bore, CLIP its stroke to the bore-log span (projected onto the run via the
    station axis) so the drawn redline spans EXACTLY the bore (never the full run / a sheet-long baseline),
    and return a REVIEW Placement plus HONEST selection signals (coverage, plausible-rival count, axis
    quality, alternatives for the correction step). Returns (None, blocker) when no drawn run covers the span.
    Never AUTO; never invents a coordinate (every vertex is a real run point or an axis projection between
    real run points). The confidence band is EARNED downstream from these signals — a partial-coverage or
    ambiguous (many-rival) selection reports LOW + correction-recommended, never a confident guess."""
    lo, hi = min(bore.station_start_ft, bore.station_end_ft), max(bore.station_start_ft, bore.station_end_ft)
    sheets = [int(s) for s in (bore.sheet_refs or [])] or [1]
    scored, overlapping = [], []
    for sheet in sheets:
        for c in dialect.extract_callouts(plan, sheet, offset):
            sig = dialect.signals_for(c)
            run_lo, run_hi = sig.get("run_from_ft"), sig.get("run_to_ft")
            if not c.bbox or run_lo is None or run_hi is None or min(run_hi, hi) <= max(run_lo, lo):
                continue                                     # no overlap with the bore span
            sc = _score_bore_run(sig, bore)
            overlapping.append((sc, c, sheet))               # EVERY overlapping run -> honest ambiguity count
            if sc["cover"] >= _GENERIC_MIN_COVER:
                scored.append((sc, c, sheet))
    if not scored:
        return None, {"code": NO_DRAWN_RUN_OVER_SPAN,
                      "reason": "No drawn run covers the bore-log station span on the referenced sheet(s)."}
    scored.sort(key=lambda t: t[0]["score"], reverse=True)
    sc, winner, sheet = scored[0]

    # Over-placement guard: if the ONLY run covering the bore span is a full-sheet alignment/baseline (no
    # bore-shaped run qualifies), this is NOT a placeable bore -> abstain honestly rather than drawing a
    # redline on the survey baseline. Confined to the name-free generic lane; the named-dialect/deterministic
    # path never reaches _place_generic.
    if sc["full_sheet"] and not any(not s["full_sheet"] for s, _c, _sh in scored):
        return None, {"code": NO_DRAWN_RUN_OVER_SPAN,
                      "reason": "Only a full-sheet alignment/baseline covers the bore span; "
                                "no bore-shaped run was drawn over it."}

    def _other(c, sh):
        return list(c.bbox or []) != list(winner.bbox or []) or sh != sheet

    # HONEST ambiguity — counted over ALL overlapping runs (NOT the cover-prefiltered set, the prior bug that
    # hid competition). fragments = distinct non-baseline runs that ALSO plausibly cover the span; competition
    # = placement candidates scoring within a hair of the winner. On a real plan these are large (the bore is
    # one of many co-linear lines); on a clean single-bore plan they are zero.
    fragments = sum(1 for s, c, sh in overlapping
                    if _other(c, sh) and not s["full_sheet"] and s["cover"] >= _GENERIC_FRAG_COVER)
    competition = sum(1 for s, c, sh in scored if _other(c, sh) and s["score"] >= sc["score"] - 0.08)
    wsig = dialect.signals_for(winner)

    axis = dialect.axis_for(sheet)
    x_lo = axis.x_at(bore.station_start_ft) if axis else None
    x_hi = axis.x_at(bore.station_end_ft) if axis else None
    clipped = (dialect.clip_centerline_to_x(winner, x_lo, x_hi)
               if (x_lo is not None and x_hi is not None) else None)
    if clipped and len(clipped) >= 2:
        dialect.set_stroke(winner, clipped)                  # stroke spans EXACTLY the bore, not the full run

    # JSON-safe runner-up runs for a guided "Correct redline placement" step (let a human pick the intended
    # line instead of trusting the geometry guess). Distinct from the winner, best score first.
    alternatives = [{"from_sta": c.from_sta, "to_sta": c.to_sta, "sheet": int(sh),
                     "score": s["score"], "cover": s["cover"], "is_red": s["is_red"]}
                    for s, c, sh in scored if _other(c, sh)][:_GENERIC_MAX_ALTERNATIVES]

    sc["competition"] = competition
    sc["fragments"] = fragments
    sc["overlapping_runs"] = len(overlapping)
    sc["axis_ticks"] = int(wsig.get("axis_ticks") or 0)
    sc["axis_residual_ft"] = wsig.get("axis_residual_ft")
    sc["bore_note_dist"] = _nearest_bore_note(plan, sheet, offset, winner.bbox)
    sc["alternatives"] = alternatives
    dialect.merge_signals(winner, sc)
    caveats = [GENERIC_GEOMETRY_REVIEW]
    if sc["full_sheet"]:
        caveats.append(GENERIC_PLACED_ON_ALIGNMENT)
        reason = "DRAWN_ALIGNMENT_COVERS_SPAN_LINE_UNVERIFIED"
    else:
        caveats.append(GENERIC_RUN_MATCHES_SPAN)
        reason = "DRAWN_RUN_MATCHES_BORE_SPAN_REVIEW"
    if sc["cover"] < _GENERIC_CONFIDENT_COVER:
        caveats.append(GENERIC_PARTIAL_SPAN)
    if fragments >= 1 or competition >= 1:
        caveats.append(GENERIC_MULTIPLE_RUNS)
    if sc["full_sheet"] or fragments >= 2 or sc["cover"] < _GENERIC_CONFIDENT_COVER:
        caveats.append(GENERIC_CORRECTION_RECOMMENDED)       # auto-pick is uncertain -> route to human correction
    if sc["run_extent_ft"] > bore.span_ft + 25.0:
        caveats.append("DRAWN_EXTENT_EXCEEDS_BORE_SPAN")
    placement = Placement(
        bore_id=bore.bore_id, status=PlacementStatus.REVIEW, tier="AUTO_PLACED_REQUIRES_APPROVAL",
        reason=reason, sheets=[int(winner.sheet)],
        station_span="%s->%s" % (bore.station_start, bore.station_end), footage=bore.span_ft,
        caveats=caveats, matched_callouts=[winner])
    return placement, sc


def _confidence(placement, candidate, bore, signals):
    """Honest graded REVIEW confidence — EARNED by how completely + uniquely the SELECTED run spans the bore,
    NEVER by axis readability or color alone. Drivers, in order: span COVERAGE (does the run actually cover
    the bore-log range?), extent/endpoint fit, and ABSENCE of plausible rivals. Confidence is forced DOWN —
    to LOW + correction-recommended — whenever the selection is partial, ambiguous, on a full-sheet baseline,
    or rests on a sparse/noisy station axis, because on a real plan the proposed bore is one of many co-linear
    lines and geometry alone cannot single it out. HIGH is reserved for a near-full, tight, rival-free run
    (the clean single-bore case). Capped < 0.86 — the generic lane INFERS the bore, so REVIEW, never AUTO.
    For the named-dialect path ``signals`` is empty (no graded confidence emitted)."""
    reasons, warnings = [], []
    cover = float(signals.get("cover", 0.0) or 0.0)
    extent_fit = float(signals.get("extent_fit", 0.0) or 0.0)
    end_fit = float(signals.get("end_fit", 0.0) or 0.0)
    full_sheet = bool(signals.get("full_sheet"))
    fragments = int(signals.get("fragments", 0) or 0)
    competition = int(signals.get("competition", 0) or 0)
    axis_ticks = int(signals.get("axis_ticks", 0) or 0)
    resid = signals.get("axis_residual_ft")
    note_dist = signals.get("bore_note_dist")

    # Coverage dominates: a run that does not span the bore is not a confident identification of it.
    conf = 0.45 * min(1.0, cover) + 0.30 * extent_fit + 0.25 * end_fit

    if cover >= _GENERIC_HIGH_COVER and extent_fit >= 0.80:
        reasons.append("the drawn run spans the full bore-log station range")
    if extent_fit >= 0.80:
        reasons.append("drawn run length matches the bore-log span (%.0f%%)" % (extent_fit * 100))
    elif extent_fit < 0.50:
        warnings.append("RUN_LENGTH_UNLIKE_BORE_SPAN")
    if end_fit >= 0.80:
        reasons.append("the drawn run brackets the bore start/end stations")
    if signals.get("is_red"):
        reasons.append("inferred run is drawn red (proposed-construction color)")   # weak — a REASON only

    # Penalties for ambiguity / weak axis (subtract before the hard ceilings).
    if fragments >= 1:                                      # several plausible runs over the span -> ambiguous
        warnings.append("MULTIPLE_PLAUSIBLE_RUNS_%d" % fragments)
        conf -= 0.12 * min(fragments, 4)
    if competition >= 1:
        warnings.append("COMPETING_RUNS_NEAR_SCORE")
        conf -= 0.10 * min(competition, 3)
    if axis_ticks and axis_ticks < 5:                       # sparse station labels -> a less trustworthy axis
        warnings.append("SPARSE_STATION_LABELS_%d" % axis_ticks)
        conf -= 0.10
    if resid is not None and resid > 6.0:
        warnings.append("NOISY_STATION_AXIS"); conf -= 0.10
    if note_dist is not None and note_dist <= _GENERIC_BORE_NOTE_PT:   # weak, name-free corroboration only
        reasons.append("near a printed directional-bore note")
        conf += 0.05

    # Hard ceilings LAST so nothing (color/note/etc.) can lift a partial / ambiguous / baseline pick above them.
    if fragments >= 2:                                      # 3+ plausible runs over the span -> cannot single
        conf = min(conf, 0.45)                             # out the bore from geometry alone -> LOW + correct
    if cover < _GENERIC_CONFIDENT_COVER:                   # PARTIAL coverage -> never a confident placement
        warnings.append("PARTIAL_SPAN_COVERAGE_%d_PCT" % round(cover * 100))
        cap = (0.55 if (cover >= 0.70 and fragments == 0 and competition == 0 and extent_fit >= 0.60)
               else 0.40)                                   # decent-but-partial -> low-MEDIUM; otherwise LOW
        conf = min(conf, cap)
    if full_sheet:
        reasons.append("placed on the alignment at the bore's stations — the exact drawn line is unverified")
        warnings.append("PLACED_ON_FULL_SHEET_ALIGNMENT_LINE")
        conf = min(conf, 0.35)                              # baseline pick: station location only

    # The generic lane INFERS the bore from plan geometry with NO source-tight per-bore evidence (on a real
    # plan the bore is one of many co-linear drawn lines; only an annotation a named dialect reads could single
    # it out). Its honest ceiling is therefore MEDIUM ("verify") — it must NEVER show HIGH to a customer, even
    # on a clean single-bore plan where coverage/extent look perfect. Capped at _GENERIC_MAX_CONF; banded
    # MEDIUM/LOW only. (C2 — a HIGH on an inference lane that itself reports NO_PER_BORE_TERMINI is dishonest.)
    conf = max(0.05, min(_GENERIC_MAX_CONF, conf))
    band = "MEDIUM" if conf >= 0.50 else "LOW"
    correction = (band == "LOW" or full_sheet or fragments >= 2
                  or cover < _GENERIC_CONFIDENT_COVER)
    if band == "LOW":
        warnings.append("LOW_CONFIDENCE_REVIEW_VERIFY_PLACEMENT")
    if correction:
        warnings.append("CORRECTION_RECOMMENDED")
    return {"score": round(conf, 2), "band": band, "reasons": reasons, "warnings": warnings,
            "correction_recommended": correction}


def _run_engine(plan_path, borelog_path):
    """Run the shipped engine on the resolved files. Returns (bore, placement, offset, dialect_name,
    extra_legs, matchline, dialect). The DEFAULT (all-off) match path is used — no opt-in gates — so this
    mirrors the deterministic engine's default behavior for a RECOGNIZED plan.

    GENERIC FALLBACK: when no named (Brenham/ODOT) dialect recognizes the plan, OR the named engine
    abstains / places nothing drawable, the name-free GenericGeometryDialect is tried. It reconstructs a
    plausible drawn run from generic geometry + the station-label axis and places it via the dedicated
    BORE-AWARE ``_place_generic`` (select the drawn run most likely to BE the bore + clip the stroke to the
    bore-log span). That helper constructs the candidate DIRECTLY as REVIEW — it does NOT route through
    ``run_match`` / ``decide_by_extent`` — and earns a graded MEDIUM/LOW confidence from real coverage +
    uniqueness; it is never AUTO and (capped at ``_GENERIC_MAX_CONF``) never HIGH. This NEVER fires for a
    recognized plan that places — the deterministic ODOT/Brenham paths are byte-identical. The returned
    ``dialect`` instance lets the renderer read back the traced centerline.

    ``extra_legs`` are source-supported drawn legs on REFERENCED sheets OTHER than the winner's sheet
    (cross-sheet REVIEW coverage). ``matchline`` is the read-only printed-matchline continuity verdict over
    the rendered sheets. Caller owns no plan handle (opened/closed here)."""
    _na = {"verdict": "N/A", "caveats": [], "evidence": []}
    try:
        bore = load_borelog(str(borelog_path))
    except ValueError:
        # Unreadable/unrecognized bore-log FILE (detect_format funnels every non-workbook/garbage file
        # here). A named input blocker — the caller reports BLOCKED and the workflow abstains with
        # plain-English copy; this must never escape as an unhandled 500.
        return None, None, None, None, [], _na, None, {
            "code": BORE_LOG_FORMAT_UNRECOGNIZED,
            "reason": "The engine could not read this bore log's file format. Upload the bore log as a "
                      "standard bore schedule spreadsheet, then run the redline again.",
        }
    plan = PlanPdf(str(plan_path))
    try:
        dialect = select_dialect(plan)
        used = dialect
        offset = _DEFAULT_OFFSET
        placement = None
        sheet_index = None            # title-block index; built only when a named dialect runs (C2)
        if dialect is not None:
            offset = dialect.calibrate(plan, _DEFAULT_OFFSET)
            # C2 (B-ENGINE-SHEET-PAGE-1): resolve each construction-sheet ref to its ACTUAL PDF page from the
            # plan's own printed title-block "N OF M" labels, instead of treating the sheet number as a raw page
            # index under a single global offset (a dialect whose calibrate is a no-op otherwise reads the wrong
            # page and abstains NO_CALLOUTS_EXTRACTED). Falls back to ``offset`` for any sheet the title block
            # cannot resolve, and to prior behavior entirely on a plan with no title-block index -> product
            # behavior preserved. Read-only; touches no dialect/renderer/select code.
            sheet_index = build_sheet_index(plan)
            placement = run_match(bore, plan, dialect, offset, sheet_index=sheet_index)

        # Generic fallback — only when the named path produced no drawable candidate. Reordering is
        # impossible (named dialects are tried first and win whenever they place), so a recognized plan is
        # never routed here and its render stays byte-identical. The generic lane uses a dedicated BORE-AWARE
        # placement (select the run most likely to be the bore + clip the stroke to the bore span), NOT the
        # midpoint-only decide_by_extent pick.
        named_cand = _candidate(placement)
        generic_blocker = None
        if named_cand is None or not getattr(named_cand, "bbox", None):
            generic = GenericGeometryDialect()
            if generic.detect(plan):
                gen_off = generic.calibrate(plan, _DEFAULT_OFFSET)
                gen_pl, gen_sig = _place_generic(bore, plan, generic, gen_off)
                if gen_pl is not None:
                    placement = gen_pl                       # REVIEW; stroke already clipped to the bore span
                    used = generic
                    offset = gen_off
                elif isinstance(gen_sig, dict) and gen_sig.get("code"):
                    generic_blocker = gen_sig                # the generic lane's SPECIFIC abstain reason
            else:
                # The fallback found no usable drawn run at all: classify WHY (no axis / weak axis / no
                # weldable run) instead of the single coarse NO_PLAN_DIALECT_RECOGNIZED. Diagnostic only.
                generic_blocker = generic.detect_blocker(plan)

        cand = _candidate(placement)
        is_generic = getattr(used, "name", None) == _GENERIC_DIALECT_NAME
        if cand is not None and cand.bbox:
            # The generic lane places a single clipped bore stroke (no cross-sheet leg assembly yet); named
            # dialects keep their per-sheet cross-sheet REVIEW legs.
            # Slice 1': extra legs get the SAME per-sheet title-block resolution the winner's extraction
            # used (run_match/C2) — a referenced construction sheet behind front matter reads ITS page,
            # not the raw page index (which silently found nothing and dropped the leg).
            extra_legs = ([] if is_generic
                          else _extra_sheet_legs(plan, used, offset, bore, cand.sheet,
                                                 sheet_index=sheet_index))
            render_sheets = {int(cand.sheet)} | {int(l["sheet"]) for l in extra_legs}
            matchline = _matchline_continuity(plan, offset, bore, render_sheets)
        else:
            extra_legs, matchline = [], _na
        return bore, placement, offset, getattr(used, "name", None), extra_legs, matchline, used, generic_blocker
    finally:
        plan.close()


def _candidate(placement):
    """The winning matched callout (drawn extent) for a placed candidate, else None."""
    if placement is None or placement.status == PlacementStatus.ABSTAIN:
        return None
    return placement.matched_callouts[0] if placement.matched_callouts else None


def _extra_sheet_legs(plan, dialect, offset, bore, winner_sheet, sheet_index=None):
    """Source-supported drawn legs on REFERENCED sheets OTHER than the winner's sheet — the cross-sheet
    REVIEW coverage. A leg = the drawn bore-layer extents on that sheet that overlap the bore's station span,
    with a stroke polyline along them (page coords). NEVER a connecting segment across sheets: each leg is
    built only from that sheet's OWN drawn geometry; a sheet with no overlapping drawn extent yields no leg
    (honest partial coverage). The winner's own sheet keeps its existing single-callout render.

    Slice 1': each leg records the 1-based PDF page its callouts were extracted from (``pdf_page``). When
    ``sheet_index`` (the plan's title-block "N OF M" index) resolves a referenced construction sheet,
    extraction reads THAT page — mirroring run_match's C2 resolution — else the scalar ``offset`` maps it
    byte-identically to prior behavior. The construction-sheet number itself is never redefined."""
    lo, hi = bore.station_start_ft, bore.station_end_ft
    legs = []
    for sheet in sorted({int(s) for s in (bore.sheet_refs or [])} - {int(winner_sheet)}):
        s_off = offset
        if sheet_index is not None:
            resolved = sheet_index.resolve_construction_sheet(sheet)   # 1-based PDF page, or None (honest miss)
            if resolved is not None:
                s_off = int(resolved) - int(sheet)
        callouts = [c for c in dialect.extract_callouts(plan, sheet, s_off)
                    if c.bbox and c.to_ft >= lo and c.from_ft <= hi]
        if not callouts:
            continue
        callouts.sort(key=lambda c: c.from_ft)
        pts = []
        for c in callouts:
            cl = dialect.centerline_for(c) if hasattr(dialect, "centerline_for") else None
            if cl and len(cl) >= 2:                           # generic dialect: traced centerline
                pts += [(float(p[0]), float(p[1])) for p in cl]
            else:                                             # named dialect: bbox-corner extent
                bx0, by0, bx1, by1 = c.bbox
                pts += [(float(bx0), float(by0)), (float(bx1), float(by1))]
        legs.append({"sheet": sheet,
                     "pdf_page": int(sheet) + int(s_off),   # the page the callouts were READ from
                     "from_ft": round(min(c.from_ft for c in callouts), 1),
                     "to_ft": round(max(c.to_ft for c in callouts), 1),
                     "stroke_points": pts})
    return legs


def _adapter_caveats(bore, rendered_sheets):
    """Adapter-level REVIEW truth annotations (NOT engine caveats, NOT a coordinate/render change; never an
    AUTO claim): CROSS_SHEET_CONTINUATION_REVIEW for any bore that references multiple plan sheets (legs are
    rendered per-sheet; the cross-sheet continuation is NOT drawn as one connected/validated route), plus
    PARTIAL_CROSS_SHEET_REVIEW when some referenced sheet has no rendered leg (partial coverage)."""
    referenced = {int(s) for s in (bore.sheet_refs or [])}
    rendered = {int(s) for s in (rendered_sheets or [])}
    out = []
    if len(referenced) > 1:
        out.append(CROSS_SHEET_CONTINUATION_REVIEW)
        if referenced - rendered:
            out.append(PARTIAL_CROSS_SHEET_REVIEW)
    return out


def _sheet_sees(lines, partner) -> bool:
    """True iff this sheet prints a matchline cross-reference to ``partner`` (e.g. 'MATCHLINE: SEE SHEET N').
    Read-only text grammar; no station required (the no-station adjacency case)."""
    for ln in lines:
        if _MATCHLINE_KEYWORD in (ln or "").upper():
            m = _SEE_SHEET_RE.search(ln or "")
            if m and int(m.group(1)) == partner:
                return True
    return False


def _shared_boundary_station(cross_ab, cross_ba, lo, hi):
    """The boundary STATION (ft) printed by BOTH sheets' matchline equations and falling inside the bore span,
    else None. ``cross_*`` are see_sheet_crossings outputs (tuples of printed station tokens)."""
    a = {parse_station(s) for tup in cross_ab for s in tup if parse_station(s) is not None}
    b = {parse_station(s) for tup in cross_ba for s in tup if parse_station(s) is not None}
    for s in sorted(a & b):
        if lo - 1.0 <= s <= hi + 1.0:
            return s
    return None


def _matchline_continuity(plan, offset, bore, render_sheets) -> dict:
    """Validate, from PRINTED matchline evidence ONLY, whether the rendered per-sheet legs are continuous
    across the matchline. Read-only: reuses ``see_sheet_crossings`` for printed boundary-STATION equations
    (the strict CONFIRMED tier) and a SEE-SHEET adjacency check for the no-station case. Never fakes
    continuity, never changes geometry. Returns {verdict, caveats, evidence}."""
    sheets = sorted({int(s) for s in (render_sheets or [])})
    if len(sheets) < 2:
        return {"verdict": "N/A", "caveats": [], "evidence": []}
    lo, hi = bore.station_start_ft, bore.station_end_ft
    evidence, confirmed, adjacent = [], 0, 0
    for a, b in zip(sheets, sheets[1:]):
        la, lb = plan.lines(a, offset), plan.lines(b, offset)
        cross_ab = see_sheet_crossings(la, b, _MATCHLINE_KEYWORD)
        cross_ba = see_sheet_crossings(lb, a, _MATCHLINE_KEYWORD)
        shared = _shared_boundary_station(cross_ab, cross_ba, lo, hi)
        sees = _sheet_sees(la, b) and _sheet_sees(lb, a)
        if shared is not None:
            confirmed += 1
        elif sees:
            adjacent += 1
        evidence.append({"pair": [a, b], "see_sheet_a_to_b": _sheet_sees(la, b),
                         "see_sheet_b_to_a": _sheet_sees(lb, a),
                         "shared_boundary_station_ft": shared})
    pairs = len(sheets) - 1
    caveats = []
    if confirmed == pairs:                       # every adjacent rendered pair has a printed boundary station
        verdict, caveats = "CONFIRMED", [MATCHLINE_CONTINUATION_CONFIRMED_REVIEW]
    else:
        verdict, caveats = "UNVERIFIED", [MATCHLINE_CONTINUATION_UNVERIFIED]
        if confirmed or adjacent:                # mutual SEE-SHEET adjacency printed (no boundary station)
            caveats.append(MATCHLINE_SHEET_ADJACENCY_CONFIRMED)
    return {"verdict": verdict, "caveats": caveats, "evidence": evidence}


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
    extra_legs = []
    used = None
    matchline = {"verdict": "N/A", "caveats": [], "evidence": []}
    if plan_path is not None and borelog_path is not None:
        bore, placement, offset, dialect_name, extra_legs, matchline, used, generic_blocker = _run_engine(
            plan_path, borelog_path)
        if placement is None:
            # Surface the generic lane's SPECIFIC abstain reason (e.g. NO_DRAWN_RUN_OVER_SPAN) when it ran but
            # placed nothing drawable; otherwise the package matched no plan dialect at all. (The broader split
            # of NO_PLAN_DIALECT_RECOGNIZED into per-cause codes is a separate, deferred change.)
            blockers.append(generic_blocker or
                            {"code": NO_PLAN_DIALECT_RECOGNIZED,
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
        render_sheets = sorted({candidate.sheet} | {int(l["sheet"]) for l in extra_legs})
        signals = used.signals_for(candidate) if hasattr(used, "signals_for") else {}
        out["candidate"] = {
            "placement_status": placement.status.value,
            "reason": placement.reason,
            "dialect": dialect_name,
            "generic_fallback": dialect_name == _GENERIC_DIALECT_NAME,
            "caveats": list(placement.caveats) + _adapter_caveats(bore, render_sheets) + matchline["caveats"],
            "sheet": candidate.sheet,
            # Slice 1': the RESOLVED 1-based PDF page the candidate was extracted from (Callout.page —
            # title-block resolution when available, else sheet+offset). Reported SEPARATELY from the
            # engineering sheet number so no consumer ever conflates the two axes.
            "pdf_page": int(candidate.page),
            "referenced_sheets": list(bore.sheet_refs),
            "render_sheets": render_sheets,
            "extra_leg_sheets": [int(l["sheet"]) for l in extra_legs],
            "drawn_extent": candidate.text,
            "bore_span": "%s->%s" % (bore.station_start, bore.station_end),
            "render_tier": ("solid" if placement.status == PlacementStatus.AUTO_SELECT else "dashed"),
            "matchline_continuity": matchline["verdict"],
            "matchline_evidence": matchline["evidence"],
        }
        # Confidence is the GENERIC fallback's graded REVIEW signal; the named-dialect path emits none
        # (signals empty -> output byte-identical to the proven ODOT/Brenham REVIEW path).
        if signals:
            out["candidate"]["confidence"] = _confidence(placement, candidate, bore, signals)
    return out


def _placement_candidate_block(confidence, dialect) -> dict:
    """The additive per-log placement_candidate block (general uploaded-project REVIEW state). The manifest
    is published at render time, so state is CANDIDATE; the live accept/reject lives in the review-acceptance
    record and is overlaid by the export/closeout reader. ``confidence`` is None on a named-dialect candidate
    (ungraded), present (graded) on the generic fallback."""
    return {
        "state": "CANDIDATE",
        "confidence": confidence.get("band") if confidence else None,
        "confidence_score": confidence.get("score") if confidence else None,
        "reasons": list(confidence.get("reasons") or []) if confidence else [],
        "warnings": list(confidence.get("warnings") or []) if confidence else [],
        "dialect": dialect,
        "generic_fallback": dialect == _GENERIC_DIALECT_NAME,
    }


def _manifest_input(log_id, *, placement, bore, legs, project_id, matchline_caveats=(),
                    confidence=None, dialect=None) -> dict:
    """Job-local single-log manifest for the engine-rendered redline (mock_example:false). ``legs`` is a list
    of {sheet, artifact_path}: one FINAL_REDLINE_PNG per rendered sheet (the winner's sheet plus any
    cross-sheet legs). One log (one bore) with one artifact per sheet; source_sheets = all rendered sheets.
    ``matchline_caveats`` are the read-only printed-matchline continuity annotations (metadata only).
    ``confidence`` (when supplied) is the graded REVIEW confidence — surfaced in the free-form warnings (the
    structured per-log placement_candidate block + its schema are an additive follow-on)."""
    status_value = placement.status.value
    provenance = _PROVENANCE_BY_STATUS.get(status_value, "OWNER_CONFIRMED_HUMAN_ADJUSTABLE")
    auto = status_value == PlacementStatus.AUTO_SELECT.value
    sheets = sorted({int(l["sheet"]) for l in legs})
    conf_warnings = []
    if confidence is not None:
        conf_warnings.append("placement confidence %s (%.2f)"
                             % (confidence.get("band"), confidence.get("score", 0.0)))
        conf_warnings += list(confidence.get("warnings") or [])
    log = {
        "log_id": log_id, "parent_id": log_id, "entry_role": "standalone",
        "status": "DRAWN_REDLINE", "provenance": provenance,
        "drawn": True, "covered": False, "blocked": False, "drawn_lane": "NEW_TARGETS",
        "source_sheets": sheets,
        "span": {"start_station": bore.station_start, "end_station": bore.station_end,
                 "label": "%s->%s" % (bore.station_start, bore.station_end)},
        "closure": None, "coverage": None, "blocker": None,
        "artifacts": [{"kind": "FINAL_REDLINE_PNG", "sheet": int(l["sheet"]), "path": l["artifact_path"],
                       "sha256": None, "example_placeholder": True} for l in legs],
        "evidence": [],
        "warnings": (["engine %s placement (%s); rendered from the plan's own drawn geometry on %d sheet(s)"
                      % (status_value, placement.reason, len(sheets))]
                     + list(placement.caveats) + _adapter_caveats(bore, sheets) + list(matchline_caveats)
                     + conf_warnings),
        "placement_candidate": _placement_candidate_block(confidence, dialect),
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


def _render_content_key(plan_name, borelog_name, log_id, status_value, legs) -> str:
    """Idempotency key for one engine render: identical content -> the same engine_run_id/bundle. Slice 1':
    each leg's RESOLVED ``pdf_page`` is part of the key, so a corrected page resolution mints a NEW engine
    run — the idempotency short-circuit can never replay a stale wrong-page bundle as current content."""
    blob = json.dumps({"plan": plan_name, "bore": borelog_name, "log": log_id, "status": status_value,
                       "legs": [[l["sheet"], l["pdf_page"], l["stroke_points"]] for l in legs]},
                      sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


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

    bore, placement, offset, dialect_name, extra_legs, matchline, used, _generic_blocker = _run_engine(
        plan_path, borelog_path)
    candidate = _candidate(placement)
    if candidate is None or not candidate.bbox:
        ev = evaluate_uploaded_corpus_engine_handoff(store_root, customer_project_id, job_id)
        raise UploadedCorpusEngineError("not runnable: %s"
                                        % "; ".join(b["code"] for b in ev["blockers"]))

    log_id = rbl["reviewed_bore_log_id"]                       # generic, name-free artifact/log id
    wx0, wy0, wx1, wy1 = candidate.bbox
    # Leg list: the winner's sheet renders the traced centerline when the generic dialect supplies one
    # (a real route polyline, not a bbox diagonal); a named dialect has no centerline so the existing
    # single-callout bbox-extent render is preserved BYTE-IDENTICAL. Each extra referenced sheet adds a
    # per-sheet leg from that sheet's OWN drawn geometry (no connecting segment across sheets).
    winner_centerline = used.centerline_for(candidate) if hasattr(used, "centerline_for") else None
    winner_points = ([(float(p[0]), float(p[1])) for p in winner_centerline]
                     if winner_centerline and len(winner_centerline) >= 2
                     else [(float(wx0), float(wy0)), (float(wx1), float(wy1))])
    # Slice 1': every leg carries BOTH axes — ``sheet`` (the engineering/construction sheet number: the
    # filename + manifest identity, unchanged) and ``pdf_page`` (the RESOLVED 1-based PDF page the leg's
    # geometry was extracted from: the raster target). The winner's page is the callout's own extraction
    # truth (Callout.page = sheet + offset-actually-used, i.e. the title-block-resolved page when C2
    # resolved it, else the scalar mapping — so this is byte-identical whenever the two agree). Stubbed/
    # legacy extra legs without pdf_page fall back to the scalar mapping exactly as before.
    legs = [{"sheet": int(candidate.sheet), "pdf_page": int(candidate.page),
             "stroke_points": winner_points}]
    legs += [{"sheet": int(l["sheet"]),
              "pdf_page": int(l.get("pdf_page", int(l["sheet"]) + int(offset))),
              "stroke_points": l["stroke_points"]} for l in extra_legs]

    # Idempotent content key over (plan, bore-log, status, ALL leg geometry incl. resolved pages).
    engine_run_id = "uce-render-%s" % _render_content_key(
        plan_path.name, borelog_path.name, log_id, placement.status.value, legs)

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
        rendered = []                                          # one FINAL_REDLINE_PNG per rendered sheet leg
        for leg in legs:
            png = render_redline_stroke(
                # Slice 1' (page-resolution fix): rasterize the RESOLVED page. render_redline_stroke keys
                # its page as page_index(sheet, offset) = sheet + offset - 1, so a per-leg offset of
                # (pdf_page - sheet) lands exactly on the leg's own extraction page while the ``sheet``
                # argument — and therefore the artifact FILENAME (…_s{sheet}_…) and manifest identity —
                # keeps meaning the construction sheet. No renderer change; page targeting only.
                plan, bore_id=log_id, sheet=leg["sheet"],
                offset=int(leg["pdf_page"]) - int(leg["sheet"]),
                stroke_points=leg["stroke_points"], status=placement.status.value,
                reason=placement.reason, out_dir=str(render_src),
                # Customer-facing product artifact: NO diagnostic caption band. The status /
                # reason / bore id stay in the structured manifest fields below -- traceability
                # lives in metadata, never burned into the customer's redline pixels.
                caption=False)
            if png:
                rendered.append({"sheet": leg["sheet"],
                                 "artifact_path": "artifacts/%s/%s" % (log_id, Path(png).name),
                                 "png": png})
    finally:
        plan.close()
    if not rendered:
        raise UploadedCorpusEngineError("renderer produced no stroke for the engine candidate")

    artifact_map = {r["artifact_path"]: r["png"] for r in rendered}
    signals = used.signals_for(candidate) if hasattr(used, "signals_for") else {}
    confidence = _confidence(placement, candidate, bore, signals) if signals else None
    manifest_input = _manifest_input(
        log_id, placement=placement, bore=bore,
        legs=[{"sheet": r["sheet"], "artifact_path": r["artifact_path"]} for r in rendered],
        project_id=customer_project_id, matchline_caveats=matchline["caveats"],
        confidence=confidence, dialect=dialect_name)
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
