"""Permanent v2 product foundation — human-confirmed source-anchor route geometry (contract-only).

A source_anchor records that a HUMAN confirmed a bore's route geometry directly on an uploaded PLAN_PDF
page, by supplying ordered control points in the plan's PDF DISPLAY-space (the same coordinate space the
renderer's stroke draws in). It is the honest bridge between an uploaded plan + reviewed bore-log rows and
a real redline: the geometry is SOURCE-BOUND by explicit human confirmation, never inferred. This is NOT
automatic engine placement and never counts toward the engine's automatic frontier — its provenance is
always HUMAN_CONFIRMED_CONTROL_POINTS.

This slice records + validates ONLY. It RENDERS NOTHING, runs no engine, creates no PNG / manifest /
artifact bundle, sets no job output slot, and never mutates the job. ``create_source_anchor`` evaluates
renderability (named blockers) and stores the record as VALIDATED (renderable) or REJECTED (blocked).

Coordinate discipline (do-not-widen): the human control points live ONLY in this record's
``control_points`` field, are NEVER fed into the legacy adjudication/anchor fixtures, and identity
(``start_identity`` / ``end_identity``) is coordinate-FREE (station / structure label / note text only).
Pure stdlib + product contracts; no fitz/PlanPdf import here — the page's display-space bounds are
INJECTED by the caller (resolved at the edge) so this stays a pure validation + persistence contract.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from truelinev2.contracts.atomic_json import write_json_atomic
from truelinev2.contracts.customer_project import assert_same_project, validate_customer_project_id
from truelinev2.contracts.processing_job import job_dir, load_job, validate_job_id
from truelinev2.contracts.reviewed_bore_log import (
    ELIGIBLE_RELATIONS,
    GROUPING_CONFIRMED,
    ReviewedBoreLogNotFoundError,
    is_engine_ready,
    load_reviewed_bore_log,
    row_engine_eligible,
)

RECORD_FORMAT = "trueline-source-anchor-1"
# Phase-2 SOURCE-ROUTE ADOPTION (T31 Q5): a source_anchor created with a confirmed, server-re-derived
# ``route_adoption`` block is record_format v2. Manual (non-adopted) records are UNCHANGED v1 — this is a
# pure ADDITION, never a migration; every existing v1 reader (render/source_anchor_render.py,
# render/station_dots.py, the anchors GET routes) reads generically off ``control_points``/``status``/
# ``renderable`` and carries no ``record_format`` equality assumption, so a v2 record flows through them
# unmodified (see truelinev2/docs/source-route-adoption.md).
RECORD_FORMAT_V2 = "trueline-source-anchor-2"
GEOMETRY_BASIS_HUMAN_CLICKED = "HUMAN_CLICKED_POLYLINE"           # the honest default when unspecified (v1)
GEOMETRY_BASIS_OBSERVER_ADOPTED = "OBSERVER_BACKBONE_HUMAN_ADOPTED"
CONFIRMATION_STATE_HUMAN_REVIEWED = "HUMAN_REVIEWED"
SOURCE_ANCHORS_SUBDIR = "source_anchors"
SOURCE_ANCHOR_FILENAME = "_source_anchor.json"

# Mission 8 (honest representative fallback + manual N-point polyline): the SECOND explicit-confirmation
# provenance mode for a v2 record, mutually exclusive with ``route_adoption``. Reuses the ALREADY-EXISTING
# ``GEOMETRY_BASIS_HUMAN_CLICKED`` constant above (it was defined at v2's own introduction as "the honest
# default when unspecified" but was never actually STORED anywhere until now -- a v1 record simply omits
# ``geometry_basis`` entirely) and the ALREADY-EXISTING ``CONFIRMATION_STATE_HUMAN_REVIEWED`` constant.
# ``representative_status`` vocabulary (Sol Q2, count<->status COUNT-DERIVED, never client-declared free
# text): exactly 2 control points -> REPRESENTATIVE_STRAIGHT_ACCEPTED (the honest label for the two-point
# fallback chord the owner's screenshot defect showed rendering unlabeled); >=3 -> MANUAL_POLYLINE_CONFIRMED
# (the operator added/moved/removed bend points before confirming). A mismatch between the submitted count
# and the submitted status is refused by the API layer (``MANUAL_ROUTE_STATUS_MISMATCH``) BEFORE this module
# is ever reached -- validation of the wire request lives in ``api/product_pipeline_routes.py`` (mirroring
# where ``route_adoption``'s own request-shape validation lives), never here.
REPRESENTATIVE_STRAIGHT_ACCEPTED = "REPRESENTATIVE_STRAIGHT_ACCEPTED"
MANUAL_POLYLINE_CONFIRMED = "MANUAL_POLYLINE_CONFIRMED"

# Mission 8 create-time refusal codes (code-first detail string convention, matching ``RouteAdoptionError``).
# Unlike ``RouteAdoptionError`` (deliberately NOT a contract-error / NOT imported at module scope in the API
# router, so the flag-off path can prove zero import of ``contracts.source_route_adoption`` in a fresh
# subprocess), these subclass ``SourceAnchorError`` -- they carry NO dependency on
# ``contracts.source_route_adoption`` themselves (that module is touched ONLY, and lazily, by the API route's
# own ``reported_route_search`` taxonomy check), so eager import here creates no isolation risk, and doing so
# lets every one of these fall through the EXISTING ``_to_http`` / ``_CONTRACT_ERRORS`` machinery unchanged
# (a bare ``SourceAnchorError`` already maps to a code-first 400 -- no new dispatch branch needed).
MANUAL_ROUTE_NOT_ENABLED = "MANUAL_ROUTE_NOT_ENABLED"
MANUAL_ROUTE_INVALID = "MANUAL_ROUTE_INVALID"
MANUAL_ROUTE_STATUS_MISMATCH = "MANUAL_ROUTE_STATUS_MISMATCH"
MANUAL_ROUTE_PROVENANCE_CONFLICT = "MANUAL_ROUTE_PROVENANCE_CONFLICT"

PLAN_PDF_KIND = "PLAN_PDF"
PROVENANCE = "HUMAN_CONFIRMED_CONTROL_POINTS"
COORDINATE_SPACE = "pdf_display_space"
MIN_CONTROL_POINTS = 2

STATUS_VALIDATED = "VALIDATED"
STATUS_REJECTED = "REJECTED"

# Render-bundle constants. A rendered source-anchor bundle is tagged HUMAN_CONFIRMED_SOURCE_ANCHOR at the
# manifest top level (the additive optional `bundle_origin`) so it is unambiguously NOT deterministic
# engine output and NOT part of the 50/58 deterministic frontier. Per-log it uses the EXISTING manifest
# enums (status DRAWN_REDLINE, provenance OWNER_CONFIRMED_HUMAN_ADJUSTABLE) — no new per-log bucket, so the
# committed deterministic example/frontier is untouched.
BUNDLE_ORIGIN_HUMAN_CONFIRMED = "HUMAN_CONFIRMED_SOURCE_ANCHOR"
_MANIFEST_STATUS_KEYS = ("DRAWN_REDLINE", "COVERED_BY_EXISTING_REDLINE", "OWNER_LOCKED_ABSTAIN",
                         "SOURCE_GAP_BLOCKED", "MISSING_SOURCE_SHEET_BLOCKED")
_MANIFEST_PROVENANCE_KEYS = ("DETERMINISTIC_AUTO", "OWNER_CONFIRMED_HUMAN_ADJUSTABLE",
                             "COVERED_BY_EXISTING_REDLINE", "BLOCKED_OWNER_LOCKED",
                             "BLOCKED_SOURCE_GAP", "BLOCKED_MISSING_SOURCE")
MANIFEST_DRAWN_STATUS = "DRAWN_REDLINE"
MANIFEST_HUMAN_PROVENANCE = "OWNER_CONFIRMED_HUMAN_ADJUSTABLE"

_SA_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")

# Renderability blocker codes (a record is VALIDATED iff none apply).
NO_PLAN_PDF_UPLOAD = "NO_PLAN_PDF_UPLOAD"
PLAN_UPLOAD_NOT_FOUND = "PLAN_UPLOAD_NOT_FOUND"
PLAN_UPLOAD_NOT_PLAN_PDF = "PLAN_UPLOAD_NOT_PLAN_PDF"
REVIEWED_BORE_LOG_NOT_FOUND = "REVIEWED_BORE_LOG_NOT_FOUND"
REVIEWED_BORE_LOG_NOT_ENGINE_READY = "REVIEWED_BORE_LOG_NOT_ENGINE_READY"
GROUP_NOT_CONFIRMED_OR_ELIGIBLE = "GROUP_NOT_CONFIRMED_OR_ELIGIBLE"
ROW_NOT_ENGINE_ELIGIBLE = "ROW_NOT_ENGINE_ELIGIBLE"
CONTROL_POINTS_TOO_FEW = "CONTROL_POINTS_TOO_FEW"
PAGE_NOT_RESOLVABLE = "PAGE_NOT_RESOLVABLE"
CONTROL_POINT_OUT_OF_BOUNDS = "CONTROL_POINT_OUT_OF_BOUNDS"


class SourceAnchorError(ValueError):
    """Base source_anchor error."""


class InvalidSourceAnchorIdError(SourceAnchorError):
    """source_anchor id is missing or not filesystem/URL-safe."""


class SourceAnchorNotFoundError(SourceAnchorError):
    """No stored record for the requested source_anchor."""


class SourceAnchorStateError(SourceAnchorError):
    """source_anchor is not in a state that permits the requested action (e.g. not VALIDATED/renderable,
    or its reviewed_bore_log is no longer engine-ready)."""


class ManualRouteError(SourceAnchorError):
    """Base for a Mission-8 manual-route create-time refusal. ``code`` LEADS ``str(exc)`` (the repo's
    code-first detail-string convention, matching ``RouteAdoptionError``) so ``detail.split(":", 1)[0] ==
    code``. A bare ``ManualRouteError`` (this class, uninstantiated by a subclass) carries
    ``MANUAL_ROUTE_INVALID`` -- the catch-all for a well-typed-but-semantically-invalid manual_route block
    (``confirmed`` literally false, a zero-length polyline, or an unrecognized/malformed
    ``reported_route_search``)."""
    code = MANUAL_ROUTE_INVALID

    def __init__(self, message: str):
        super().__init__("%s: %s" % (self.code, message))
        self.message = message


class ManualRouteNotEnabledError(ManualRouteError):
    """400 -- ``manual_route`` present on the request but ``TL2_SOURCE_ANCHOR_MANUAL_ROUTE_OPTIN`` is OFF."""
    code = MANUAL_ROUTE_NOT_ENABLED


class ManualRouteStatusMismatchError(ManualRouteError):
    """400 -- the submitted control_points COUNT does not match the submitted
    ``manual_route.representative_status`` (2 <-> REPRESENTATIVE_STRAIGHT_ACCEPTED, >=3 <->
    MANUAL_POLYLINE_CONFIRMED)."""
    code = MANUAL_ROUTE_STATUS_MISMATCH


class ManualRouteProvenanceConflictError(ManualRouteError):
    """400 -- both ``manual_route`` and ``route_adoption`` present on the same create request (mutually
    exclusive provenance); validated BEFORE either provenance branch runs."""
    code = MANUAL_ROUTE_PROVENANCE_CONFLICT


def validate_source_anchor_id(source_anchor_id) -> str:
    if not isinstance(source_anchor_id, str) or not _SA_ID_RE.match(source_anchor_id):
        raise InvalidSourceAnchorIdError(
            "source_anchor id must match %s (got %r)" % (_SA_ID_RE.pattern, source_anchor_id))
    return source_anchor_id


def _sa_dir(store_root, customer_project_id, processing_job_id, source_anchor_id) -> Path:
    validate_source_anchor_id(source_anchor_id)
    return (job_dir(store_root, customer_project_id, processing_job_id)
            / SOURCE_ANCHORS_SUBDIR / source_anchor_id)


def _sa_path(store_root, customer_project_id, processing_job_id, source_anchor_id) -> Path:
    return _sa_dir(store_root, customer_project_id, processing_job_id,
                   source_anchor_id) / SOURCE_ANCHOR_FILENAME


def _blocker(code, reason) -> dict:
    return {"code": code, "reason": reason}


def _normalize_points(control_points) -> list:
    """Coerce control points to a list of {"x": float, "y": float}. Raises on a malformed point (a bad
    request — distinct from the CONTROL_POINTS_TOO_FEW renderability blocker). An empty/short list is left
    as-is for the blocker check."""
    pts = []
    for p in (control_points or []):
        try:
            x, y = float(p["x"]), float(p["y"])
        except (KeyError, TypeError, ValueError):
            raise SourceAnchorError("each control point needs numeric x and y")
        pts.append({"x": x, "y": y})
    return pts


def _normalize_identity(identity) -> dict:
    """Whitelist endpoint identity to COORDINATE-FREE fields only (station / structure label / note). Any
    other key (notably x/y/coordinates) is dropped — identity must never carry geometry (do-not-widen)."""
    identity = identity or {}
    return {
        "station": identity.get("station"),
        "structure_label": identity.get("structure_label"),
        "note": identity.get("note"),
    }


def _evaluate_renderability(store_root, customer_project_id, processing_job_id, job, *, plan_upload_id,
                            reviewed_bore_log_id, page_number, control_points, group_id, row_ids,
                            page_bounds):
    """Pure renderability evaluation -> (blockers, checks). Reads the job + reviewed_bore_log only; the
    page's display-space bounds are INJECTED (None == the caller could not resolve the page). Renders
    nothing and opens no PDF here."""
    blockers, checks = [], {}
    uploads = job.get("uploads", [])

    has_plan_pdf = any(u.get("kind") == PLAN_PDF_KIND for u in uploads)
    plan_upload = next((u for u in uploads if u.get("upload_id") == plan_upload_id), None)
    plan_upload_ok = False
    if not has_plan_pdf:
        blockers.append(_blocker(NO_PLAN_PDF_UPLOAD, "Job has no PLAN_PDF upload to bind the route to."))
    elif plan_upload is None:
        blockers.append(_blocker(PLAN_UPLOAD_NOT_FOUND,
                                 "plan_upload_id %r is not an upload in this job." % (plan_upload_id,)))
    elif plan_upload.get("kind") != PLAN_PDF_KIND:
        blockers.append(_blocker(PLAN_UPLOAD_NOT_PLAN_PDF,
                                 "upload %r is not a PLAN_PDF." % (plan_upload_id,)))
    else:
        plan_upload_ok = True
    checks["has_plan_pdf"] = has_plan_pdf
    checks["plan_upload_resolved"] = plan_upload_ok

    rbl = None
    try:
        rbl = load_reviewed_bore_log(store_root, customer_project_id, processing_job_id,
                                     reviewed_bore_log_id)
    except ReviewedBoreLogNotFoundError:
        blockers.append(_blocker(REVIEWED_BORE_LOG_NOT_FOUND,
                                 "no reviewed_bore_log %r in this job." % (reviewed_bore_log_id,)))
    rbl_engine_ready = bool(rbl is not None and is_engine_ready(rbl))
    if rbl is not None and not rbl_engine_ready:
        blockers.append(_blocker(REVIEWED_BORE_LOG_NOT_ENGINE_READY,
                                 "reviewed_bore_log %r has not passed the engine-readiness gate."
                                 % (reviewed_bore_log_id,)))
    checks["reviewed_bore_log_engine_ready"] = rbl_engine_ready

    if group_id is not None:
        group = None
        if rbl is not None:
            group = next((g for g in rbl.get("groups", []) if g.get("group_id") == group_id), None)
        eligible = bool(group is not None
                        and group.get("grouping_status") == GROUPING_CONFIRMED
                        and group.get("relation") in ELIGIBLE_RELATIONS)
        if not eligible:
            blockers.append(_blocker(GROUP_NOT_CONFIRMED_OR_ELIGIBLE,
                                     "group_id %r is not a confirmed, engine-eligible segment_group."
                                     % (group_id,)))

    if row_ids:
        rows_ok = bool(rbl is not None and all(row_engine_eligible(rbl, rid) for rid in row_ids))
        if not rows_ok:
            blockers.append(_blocker(ROW_NOT_ENGINE_ELIGIBLE,
                                     "one or more row_ids are not engine-eligible in this "
                                     "reviewed_bore_log."))

    n = len(control_points)
    checks["control_point_count"] = n
    if n < MIN_CONTROL_POINTS:
        blockers.append(_blocker(CONTROL_POINTS_TOO_FEW,
                                 "a route needs >= %d control points (got %d)."
                                 % (MIN_CONTROL_POINTS, n)))

    page_resolvable = False
    if plan_upload_ok:
        if page_bounds is None:
            blockers.append(_blocker(PAGE_NOT_RESOLVABLE,
                                     "page_number %r is not resolvable in the uploaded PLAN_PDF."
                                     % (page_number,)))
        else:
            page_resolvable = True
            x0, y0, x1, y1 = page_bounds
            oob = [i for i, p in enumerate(control_points)
                   if not (x0 <= p["x"] <= x1 and y0 <= p["y"] <= y1)]
            checks["all_control_points_in_bounds"] = not oob
            if oob:
                blockers.append(_blocker(CONTROL_POINT_OUT_OF_BOUNDS,
                                         "control point index(es) %r fall outside the page "
                                         "display-space bounds." % (oob,)))
    checks["page_resolvable"] = page_resolvable
    return blockers, checks


def create_source_anchor(store_root, customer_project_id, job_id, *, source_anchor_id, plan_upload_id,
                         reviewed_bore_log_id, page_number, control_points, group_id, at, by,
                         row_ids=None, start_identity=None, end_identity=None, notes=None,
                         page_bounds=None) -> dict:
    """Create + evaluate a human-confirmed source-anchor record under one job (tenant + job scoped). The
    job must exist and be in-scope (NotFound -> 404 upstream); a duplicate id raises (no silent overwrite).
    ``page_bounds`` is the page's DISPLAY-space (x0,y0,x1,y1) resolved by the caller from the uploaded
    PLAN_PDF (None == unresolvable). Stores the record as VALIDATED (renderable) or REJECTED (with named
    blockers). RENDERS NOTHING, runs no engine, creates no artifacts/slots/bundles, and never mutates the
    job. Returns the stored record."""
    validate_customer_project_id(customer_project_id)
    validate_job_id(job_id)
    validate_source_anchor_id(source_anchor_id)
    job = load_job(store_root, customer_project_id, job_id)              # exists + isolation
    path = _sa_path(store_root, customer_project_id, job_id, source_anchor_id)
    if path.exists():
        raise SourceAnchorError("source_anchor already exists: %s" % (source_anchor_id,))

    points = _normalize_points(control_points)
    row_ids = list(row_ids) if row_ids else []
    blockers, checks = _evaluate_renderability(
        store_root, customer_project_id, job_id, job, plan_upload_id=plan_upload_id,
        reviewed_bore_log_id=reviewed_bore_log_id, page_number=page_number, control_points=points,
        group_id=group_id, row_ids=row_ids, page_bounds=page_bounds)
    renderable = not blockers
    status = STATUS_VALIDATED if renderable else STATUS_REJECTED

    record = {
        "record_format": RECORD_FORMAT,
        "source_anchor_id": source_anchor_id,
        "customer_project_id": customer_project_id,
        "processing_job_id": job_id,
        "plan_upload_id": plan_upload_id,
        "reviewed_bore_log_id": reviewed_bore_log_id,
        "group_id": group_id,
        "row_ids": row_ids,
        "page_number": page_number,
        "coordinate_space": COORDINATE_SPACE,
        "control_points": points,
        "start_identity": _normalize_identity(start_identity),
        "end_identity": _normalize_identity(end_identity),
        "provenance": PROVENANCE,
        "status": status,
        "renderable": renderable,
        "blockers": blockers,
        "checks": checks,
        "notes": notes,
        "created_at": at,
        "created_by": by,
        "updated_at": at,
        "audit": [{"action": "source_anchor_created", "at": at, "by": by, "to": status, "reason": None}],
    }
    write_json_atomic(path, record)       # atomic (temp + fsync + os.replace); creates parents
    return record


def create_source_anchor_v2(store_root, customer_project_id, job_id, *, source_anchor_id, plan_upload_id,
                            reviewed_bore_log_id, page_number, render_control_points, group_id, at, by,
                            route_adoption=None, manual_route=None, row_ids=None, start_identity=None,
                            end_identity=None, notes=None, page_bounds=None) -> dict:
    """Create + evaluate a v2 (``trueline-source-anchor-2``) source-anchor record: identical renderability
    evaluation + persistence discipline as ``create_source_anchor``, but requires EXACTLY ONE of two
    MUTUALLY EXCLUSIVE explicit-confirmation provenance modes (Mission 8):

    - ``route_adoption`` (T31 Q5, UNCHANGED): a SERVER-DERIVED, source-route-ADOPTED record.
      ``render_control_points`` is the human clicks + the clipped observer backbone in between;
      ``geometry_basis`` is forced to ``OBSERVER_BACKBONE_HUMAN_ADOPTED``. This function performs NO
      re-derivation, NO readiness spine run, and NO hashing itself — the caller (the API route) has ALREADY
      re-derived + hash-verified the adoption via ``contracts.source_route_adoption`` before calling this;
      ``route_adoption`` is the FULLY-BUILT Q5 record block (plan_source / span_source /
      human_control_points / candidate_route_points / connectivity / warnings / confirmed_by / confirmed_at /
      candidate_route_hash / proposal_hash) to store VERBATIM (byte-for-byte unchanged from the original
      single-mode landing — every key/value/order below is IDENTICAL to before this function grew a second
      mode).
    - ``manual_route`` (Mission 8, NEW): a HUMAN-CLICKED N-point polyline the operator explicitly confirmed
      (either the honest two-point "representative straight segment" fallback, or a >=3-point manual bend
      polyline). ``render_control_points`` is the operator's OWN clicks verbatim (start/intermediate/end, NO
      welding/simplification/snap); ``geometry_basis`` is forced to ``GEOMETRY_BASIS_HUMAN_CLICKED``. The
      caller has ALREADY validated the wire request (``confirmed``, ``representative_status`` vs count,
      zero-length, ``reported_route_search`` taxonomy — ``api/product_pipeline_routes.py``); ``manual_route``
      here is the PARTIALLY-BUILT record block (``representative_status`` / ``reported_route_search`` /
      ``confirmed_by`` / ``confirmed_at``) — this function derives ``human_control_points``
      {start,end,intermediate[]} + ``intermediate_point_count`` itself, FROM THE SAME NORMALIZED point list
      it stores in ``control_points`` (never from a separate raw echo), so "exact" means numerically
      unchanged after this module's own float normalization, never raw JSON bytes.

    In both modes, in every OTHER respect this is identical to ``create_source_anchor``: renders nothing,
    runs no engine, creates no output slot; the job must exist and be in-scope (404 upstream); a duplicate id
    raises (no silent overwrite)."""
    if (route_adoption is None) == (manual_route is None):
        raise SourceAnchorError(
            "create_source_anchor_v2 requires EXACTLY ONE of route_adoption/manual_route (got %s)"
            % ("neither" if route_adoption is None else "both"))
    validate_customer_project_id(customer_project_id)
    validate_job_id(job_id)
    validate_source_anchor_id(source_anchor_id)
    job = load_job(store_root, customer_project_id, job_id)              # exists + isolation
    path = _sa_path(store_root, customer_project_id, job_id, source_anchor_id)
    if path.exists():
        raise SourceAnchorError("source_anchor already exists: %s" % (source_anchor_id,))

    points = _normalize_points(render_control_points)
    if manual_route is not None and len(points) < MIN_CONTROL_POINTS:
        # Defensive precondition, not reachable via the API route (which 400s a count/status mismatch before
        # ever calling this): a manual_route confirmation always names a valid representative_status derived
        # from a count of >= MIN_CONTROL_POINTS, so this only guards a direct/malformed caller.
        raise SourceAnchorError(
            "manual_route requires >= %d control points (got %d)" % (MIN_CONTROL_POINTS, len(points)))
    row_ids = list(row_ids) if row_ids else []
    blockers, checks = _evaluate_renderability(
        store_root, customer_project_id, job_id, job, plan_upload_id=plan_upload_id,
        reviewed_bore_log_id=reviewed_bore_log_id, page_number=page_number, control_points=points,
        group_id=group_id, row_ids=row_ids, page_bounds=page_bounds)
    renderable = not blockers
    status = STATUS_VALIDATED if renderable else STATUS_REJECTED

    if route_adoption is not None:
        record = {
            "record_format": RECORD_FORMAT_V2,
            "source_anchor_id": source_anchor_id,
            "customer_project_id": customer_project_id,
            "processing_job_id": job_id,
            "plan_upload_id": plan_upload_id,
            "reviewed_bore_log_id": reviewed_bore_log_id,
            "group_id": group_id,
            "row_ids": row_ids,
            "page_number": page_number,
            "coordinate_space": COORDINATE_SPACE,
            "control_points": points,
            "geometry_basis": GEOMETRY_BASIS_OBSERVER_ADOPTED,
            "confirmation_state": CONFIRMATION_STATE_HUMAN_REVIEWED,
            "route_adoption": dict(route_adoption),
            "start_identity": _normalize_identity(start_identity),
            "end_identity": _normalize_identity(end_identity),
            "provenance": PROVENANCE,
            "status": status,
            "renderable": renderable,
            "blockers": blockers,
            "checks": checks,
            "notes": notes,
            "created_at": at,
            "created_by": by,
            "updated_at": at,
            "audit": [
                {"action": "source_anchor_created", "at": at, "by": by, "to": status, "reason": None},
                {"action": "observer_backbone_adopted", "at": at, "by": by,
                 "proposal_hash": route_adoption.get("proposal_hash"), "reason": "explicit human confirmation"},
            ],
        }
    else:
        # Mission 8: derive human_control_points {start, end, intermediate[]} + intermediate_point_count from
        # `points` — the SAME normalized list stored in `control_points` — never from a separate raw echo, so
        # "exact" means numerically unchanged after `_normalize_points`' float conversion, matching the
        # design's do-not-widen coordinate discipline.
        start, end = points[0], points[-1]
        intermediate = points[1:-1]
        manual_route_block = {
            "representative_status": manual_route["representative_status"],
            "human_control_points": {
                "start": dict(start), "end": dict(end), "intermediate": [dict(p) for p in intermediate],
            },
            "intermediate_point_count": len(intermediate),
            "reported_route_search": manual_route.get("reported_route_search"),
            "confirmed_by": manual_route["confirmed_by"],
            "confirmed_at": manual_route["confirmed_at"],
        }
        record = {
            "record_format": RECORD_FORMAT_V2,
            "source_anchor_id": source_anchor_id,
            "customer_project_id": customer_project_id,
            "processing_job_id": job_id,
            "plan_upload_id": plan_upload_id,
            "reviewed_bore_log_id": reviewed_bore_log_id,
            "group_id": group_id,
            "row_ids": row_ids,
            "page_number": page_number,
            "coordinate_space": COORDINATE_SPACE,
            "control_points": points,
            "geometry_basis": GEOMETRY_BASIS_HUMAN_CLICKED,
            "confirmation_state": CONFIRMATION_STATE_HUMAN_REVIEWED,
            "manual_route": manual_route_block,
            "start_identity": _normalize_identity(start_identity),
            "end_identity": _normalize_identity(end_identity),
            "provenance": PROVENANCE,
            "status": status,
            "renderable": renderable,
            "blockers": blockers,
            "checks": checks,
            "notes": notes,
            "created_at": at,
            "created_by": by,
            "updated_at": at,
            "audit": [
                {"action": "source_anchor_created", "at": at, "by": by, "to": status, "reason": None},
                {"action": "manual_route_confirmed", "at": at, "by": by,
                 "representative_status": manual_route_block["representative_status"],
                 "reason": "explicit human confirmation"},
            ],
        }
    write_json_atomic(path, record)       # atomic (temp + fsync + os.replace); creates parents
    return record


def load_source_anchor(store_root, customer_project_id, processing_job_id, source_anchor_id) -> dict:
    path = _sa_path(store_root, customer_project_id, processing_job_id, source_anchor_id)
    if not path.is_file():
        raise SourceAnchorNotFoundError(
            "no source_anchor %s/%s/%s"
            % (customer_project_id, processing_job_id, source_anchor_id))
    rec = json.loads(path.read_text(encoding="utf-8"))
    assert_same_project(customer_project_id, rec.get("customer_project_id"))
    return rec


def list_source_anchors(store_root, customer_project_id, processing_job_id) -> list:
    """List every source_anchor under one job (tenant + job scoped). Reads ONLY that job's
    ``source_anchors`` directory — never another tenant's — and returns [] if there are none. Each record
    is re-verified in-scope (defense in depth). Ordered by source_anchor_id."""
    validate_customer_project_id(customer_project_id)
    validate_job_id(processing_job_id)
    sa_root = (job_dir(store_root, customer_project_id, processing_job_id) / SOURCE_ANCHORS_SUBDIR)
    if not sa_root.is_dir():
        return []
    out = []
    for child in sorted(sa_root.iterdir()):
        rec = child / SOURCE_ANCHOR_FILENAME
        if rec.is_file():
            record = json.loads(rec.read_text(encoding="utf-8"))
            assert_same_project(customer_project_id, record.get("customer_project_id"))
            out.append(record)
    return out


def build_source_anchor_manifest(anchor_entries, *, project_id, project_name, engine_head, render_commit,
                                 disclaimer) -> dict:
    """PURE builder (no render, no PDF, no engine): assemble a schema-valid, reconciling redline manifest
    for human-confirmed source anchors — ONE DRAWN_REDLINE log per anchor, provenance
    OWNER_CONFIRMED_HUMAN_ADJUSTABLE (an EXISTING manifest enum, never DETERMINISTIC_AUTO), top-level
    ``bundle_origin = HUMAN_CONFIRMED_SOURCE_ANCHOR``. ``mock_example`` is false; artifact sha256/bytes are
    filled by the publisher. ``closure``/``coverage`` are null (no station footage is solved or invented).
    Each entry is {"source_anchor": <record>, "artifact_path": <manifest-relative png>, "sheet": <int>,
    "construction_sheet": <int|None>, "station_dots": <list|None>, "station_marks_basis": <str|None>,
    "station_marks_warnings": <list|None>}. ``sheet``/``page_number`` are the 1-based PDF page index the
    stroke rendered on; ``construction_sheet`` is the CONSTRUCTION sheet number printed on that page (e.g.
    PDF page 20 -> "7 OF 30" -> 7). The manifest's ``source_sheets`` + artifact ``sheet`` report the
    construction sheet (the unit the engine/recognized bundles use), falling back to the PDF page number
    when the page has no plan-sheet label (so closeout never mislabels the sheet). ``station_dots`` is
    ADDITIVE (default [] when the caller supplies none, so old callers/manifests are unaffected): the
    interval/footage dots along the human redline, each clickable + carrying that bore's log info; it is
    emitted ONLY on this human-confirmed builder, so deterministic/recognized/uploaded manifests never carry
    it and stay byte-identical. ``station_marks_basis``/``station_marks_warnings`` (Mission 8 addendum,
    contracts/station_marks.py) are the SAME kind of additive log-level fields (default None / [] when the
    caller supplies none): the evidence basis the anchor's dots were built on + any named reason a recorded
    station series was rejected as unusable. Counts derive from the logs, so the published manifest
    reconciles. Per-job + per-bundle only — never summed into the deterministic 50/58 frontier."""
    logs = []
    for entry in anchor_entries:
        sa = entry["source_anchor"]
        start = sa.get("start_identity") or {}
        end = sa.get("end_identity") or {}
        start_sta = start.get("station") or ""
        end_sta = end.get("station") or ""
        label = ("%s->%s" % (start_sta, end_sta)) if (start_sta or end_sta) \
            else "human-confirmed control-point route"
        # Report the construction sheet number (matches engine/recognized source_sheets), not the PDF page
        # index; fall back to the PDF page number when the page carries no construction-sheet label.
        construction_sheet = entry.get("construction_sheet")
        sheet_label = int(construction_sheet) if construction_sheet is not None else int(sa["page_number"])
        log_entry = {
            "log_id": sa["source_anchor_id"],
            "parent_id": sa["reviewed_bore_log_id"],
            "entry_role": "standalone",
            "status": MANIFEST_DRAWN_STATUS,
            "provenance": MANIFEST_HUMAN_PROVENANCE,
            "drawn": True, "covered": False, "blocked": False,
            "drawn_lane": "NEW_TARGETS",
            "source_sheets": [sheet_label],
            "span": {"start_station": start_sta, "end_station": end_sta, "label": label},
            "closure": None,            # no station footage solved or invented
            "coverage": None,
            "blocker": None,
            "artifacts": [{"kind": "FINAL_REDLINE_PNG", "sheet": sheet_label,
                           "path": entry["artifact_path"], "sha256": None,
                           "example_placeholder": True}],
            "evidence": [{"kind": "OWNER_REVIEW", "ref": "source_anchor/%s" % sa["source_anchor_id"],
                          "note": "human-confirmed control points marked on the uploaded plan page"}],
            "warnings": [],
            "station_dots": list(entry.get("station_dots") or []),   # additive: interval dots (default [])
            # Station-dot contract addendum (Mission 8, ``.foreman/scratch/m8/design-dots.md``): the
            # evidence-bound basis this anchor's dots were built on (STATION_SERIES /
            # SERIES_ENDPOINTS_WITH_DERIVED_FILL / SPAN_ENDPOINTS) + why a recorded series (if any) was
            # rejected as unusable. Additive: absent/None + [] when the caller supplies none (old callers/
            # manifests -- incl. the committed deterministic example -- stay byte-identical).
            "station_marks_basis": entry.get("station_marks_basis"),
            "station_marks_warnings": list(entry.get("station_marks_warnings") or []),
        }
        # Phase-2 SOURCE-ROUTE ADOPTION (T31 Q5) + Mission 8 manual-route: ADDITIVE-ONLY, split by the
        # record's ACTUAL provenance block (never by a bare truthy ``geometry_basis`` check — Sol Q4/Q9: a
        # manual v2 record ALSO carries ``geometry_basis`` now, and must never synthesize a null-filled
        # ``route_adoption`` object). A plain v1 record (no ``geometry_basis`` at all) carries NEITHER block,
        # so every prior manifest (incl. the committed deterministic example + every pre-Mission-8
        # human-confirmed bundle) stays byte-identical.
        if sa.get("geometry_basis"):
            log_entry["geometry_basis"] = sa["geometry_basis"]
            log_entry["confirmation_state"] = sa.get("confirmation_state")
            log_entry["render_control_points"] = list(sa.get("control_points") or [])
            if sa.get("route_adoption") is not None:
                ra = sa["route_adoption"]
                plan_src = ra.get("plan_source") or {}
                span_src = ra.get("span_source") or {}
                connectivity = ra.get("connectivity") or {}
                log_entry["route_adoption"] = {
                    "geometry_source": ra.get("geometry_source"),
                    "source_anchor_ref": "source_anchor/%s" % sa["source_anchor_id"],
                    "plan_upload_id": plan_src.get("plan_upload_id"),
                    "plan_sha256": plan_src.get("plan_sha256"),
                    "engineering_sheet": plan_src.get("engineering_sheet"),
                    "pdf_page": plan_src.get("pdf_page"),
                    "sheet_offset": plan_src.get("sheet_offset"),
                    "span_id": span_src.get("span_id"),
                    "reviewed_bore_log_id": span_src.get("reviewed_bore_log_id"),
                    "row_id": span_src.get("row_id"),
                    "human_control_points": list(ra.get("human_control_points") or []),
                    "why_connected": connectivity.get("why_connected"),
                    "warnings": list(ra.get("warnings") or []),
                    "confirmed_by": ra.get("confirmed_by"),
                    "candidate_route_hash": ra.get("candidate_route_hash"),
                    "proposal_hash": ra.get("proposal_hash"),
                }
            elif sa.get("manual_route") is not None:
                mr = sa["manual_route"]
                log_entry["manual_route"] = {
                    "representative_status": mr.get("representative_status"),
                    "human_control_points": dict(mr.get("human_control_points") or {}),
                    "intermediate_point_count": mr.get("intermediate_point_count"),
                    "reported_route_search": mr.get("reported_route_search"),
                    "confirmed_by": mr.get("confirmed_by"),
                    "confirmed_at": mr.get("confirmed_at"),
                }
        logs.append(log_entry)
    n = len(logs)
    status_counts = {k: 0 for k in _MANIFEST_STATUS_KEYS}
    status_counts[MANIFEST_DRAWN_STATUS] = n
    provenance_counts = {k: 0 for k in _MANIFEST_PROVENANCE_KEYS}
    provenance_counts[MANIFEST_HUMAN_PROVENANCE] = n
    return {
        "schema_version": "1.0.0",
        "mock_example": False,
        "disclaimer": disclaimer,
        "project_id": project_id,
        "project_name": project_name,
        "engine": {"branch": "feat/truelinev2", "engine_head": engine_head,
                   "render_commit": render_commit,
                   "generated_from": "human-confirmed source anchors (no solver/renderer placement)"},
        "bundle_origin": BUNDLE_ORIGIN_HUMAN_CONFIRMED,
        "summary": {"total_logs": n, "drawn_count": n, "covered_count": 0, "blocked_count": 0,
                    "frontier": "%d/%d" % (n, n)},
        "status_counts": status_counts,
        "provenance_counts": provenance_counts,
        "consumption_rules": [
            "Consume only this manifest for this job's human-confirmed drawn redlines.",
            "Human-confirmed source-anchor bundle (bundle_origin HUMAN_CONFIRMED_SOURCE_ANCHOR): NOT "
            "deterministic engine output and NOT part of the 50/58 deterministic frontier.",
        ],
        "logs": logs,
    }
