"""Field segment-evidence packages — the WRITE contract the mobile field app submits through.

A field crew captures evidence for one run/segment (photos, problem areas, digital bore-log readings,
notes) and SUBMITS the package to review. This contract stores that package tenant-safely under the job
and enforces the owner's field rules:

  * a segment REQUIRES a start station photo to begin,
  * a segment REQUIRES an end station photo to complete/submit,
  * those are the ONLY photos required by default,
  * every logged PROBLEM AREA (obstruction / utility conflict / damage / station mismatch / route
    deviation / unclear endpoint / blocked access / other) requires at least one problem photo,
  * OPTIONAL_CONTEXT photos are never required,
  * digital bore-log readings follow a NOMINAL ~50 ft locator cadence — advisory only, never enforced
    (``NOMINAL_READING_INTERVAL_FT``); readings are structured (offset_ft as the plotting axis +
    optional printed station code) so a later surface can plot them along the digital redline proof.

A "photo" here is a REFERENCE to a real PHOTO upload already stored on the job through the existing
upload pipeline (``upload_pipeline.accept_upload``) — this contract never invents evidence: a required
photo slot counts ONLY when its reference binds to an existing job upload of kind PHOTO.

DOCTRINE (hard): field evidence SUPPORTS review; it never places. Submitting a package performs NO
AUTO, NO final placement, NO redline generation, and NO status promotion — the web product and the v2
engine remain the truth/review/closeout layer. Every record and submit result carries the explicit
``creates_redline/performs_auto/performs_placement = False`` + ``review_support_only = True`` flags,
and an incomplete package is refused with NAMED missing-evidence reasons
(``BLOCKED_MISSING_REQUIRED_EVIDENCE``), never silently accepted.
"""
from __future__ import annotations

import json
import re

from truelinev2.contracts.processing_job import job_dir, load_job

FIELD_EVIDENCE_RECORD_FORMAT = "trueline-field-evidence-1"
FIELD_EVIDENCE_SUBDIR = "field_evidence"

# Statuses (smallest set that fits the repo's honest-refusal convention: a blocked submit REFUSES with
# named reasons and leaves the record in DRAFT — a "blocked" state is a submit RESULT, not a stored status).
DRAFT = "DRAFT"
SUBMITTED_FOR_REVIEW = "SUBMITTED_FOR_REVIEW"
BLOCKED_MISSING_REQUIRED_EVIDENCE = "BLOCKED_MISSING_REQUIRED_EVIDENCE"

# Photo evidence kinds.
START_STATION = "START_STATION"
END_STATION = "END_STATION"
PROBLEM_AREA = "PROBLEM_AREA"
OPTIONAL_CONTEXT = "OPTIONAL_CONTEXT"
PHOTO_KINDS = (START_STATION, END_STATION, PROBLEM_AREA, OPTIONAL_CONTEXT)

# Problem-area types (the field exception classes that demand photo documentation).
PROBLEM_TYPES = (
    "obstruction",
    "utility_conflict",
    "damage",
    "station_mismatch",
    "route_deviation",
    "unclear_endpoint",
    "blocked_access",
    "other",
)

# Locating methods for digital bore-log readings.
READING_METHODS = ("walkover_locator", "wireline", "manual", "other")

# Typical DigiTrak-style locator cadence. ADVISORY ONLY — never validated/enforced; crews record what
# the tool and terrain actually produced.
NOMINAL_READING_INTERVAL_FT = 50

# Missing-evidence reason codes (deterministic order: start, end, then problems in list order).
MISSING_START_STATION_PHOTO = "MISSING_START_STATION_PHOTO"
MISSING_END_STATION_PHOTO = "MISSING_END_STATION_PHOTO"
PROBLEM_PHOTO_REQUIRED = "PROBLEM_PHOTO_REQUIRED"

_SEGMENT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")     # same shape as job / reviewed-bore-log ids


class FieldEvidenceError(ValueError):
    """Base field-evidence contract error."""


class InvalidSegmentIdError(FieldEvidenceError):
    """The segment id is not a safe slug."""


class FieldEvidenceNotFoundError(FieldEvidenceError):
    """No stored field-evidence package for the requested segment."""


class InvalidFieldEvidenceError(FieldEvidenceError):
    """The submitted package payload is malformed (bad kind/type/number/duplicate id/...)."""


class FieldEvidenceLockedError(FieldEvidenceError):
    """The package was already submitted for review — field edits are locked (review owns it now)."""


def validate_segment_id(segment_id) -> str:
    if not isinstance(segment_id, str) or not _SEGMENT_ID_RE.match(segment_id):
        raise InvalidSegmentIdError(
            "segment id must match %s (got %r)" % (_SEGMENT_ID_RE.pattern, segment_id))
    return segment_id


def _fe_dir(store_root, customer_project_id, processing_job_id):
    return job_dir(store_root, customer_project_id, processing_job_id) / FIELD_EVIDENCE_SUBDIR


def _fe_path(store_root, customer_project_id, processing_job_id, segment_id):
    validate_segment_id(segment_id)
    return _fe_dir(store_root, customer_project_id, processing_job_id) / ("%s.json" % segment_id)


# --------------------------------------------------------------------------- #
# Payload normalization (deep validation — the route layer stays thin).
# --------------------------------------------------------------------------- #
def _opt_str(value, field) -> "str | None":
    if value is None:
        return None
    if not isinstance(value, str):
        raise InvalidFieldEvidenceError("%s must be a string when present (got %r)" % (field, value))
    return value


def _req_str(value, field) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidFieldEvidenceError("%s is required and must be a non-empty string (got %r)" % (field, value))
    return value


def _opt_num(value, field) -> "float | None":
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidFieldEvidenceError("%s must be a number when present (got %r)" % (field, value))
    return float(value)


def _req_num(value, field, *, minimum=None) -> float:
    n = _opt_num(value, field)
    if n is None:
        raise InvalidFieldEvidenceError("%s is required (got %r)" % (field, value))
    if minimum is not None and n < minimum:
        raise InvalidFieldEvidenceError("%s must be >= %s (got %s)" % (field, minimum, n))
    return n


def _unique_id(seen: set, value: str, field: str) -> str:
    if value in seen:
        raise InvalidFieldEvidenceError("duplicate %s %r" % (field, value))
    seen.add(value)
    return value


def _normalize_photo(raw, seen_ids: set) -> dict:
    if not isinstance(raw, dict):
        raise InvalidFieldEvidenceError("each photo must be an object (got %r)" % (raw,))
    kind = _req_str(raw.get("kind"), "photo.kind")
    if kind not in PHOTO_KINDS:
        raise InvalidFieldEvidenceError("photo.kind must be one of %s (got %r)" % (list(PHOTO_KINDS), kind))
    return {
        "evidence_id": _unique_id(seen_ids, _req_str(raw.get("evidence_id"), "photo.evidence_id"), "photo.evidence_id"),
        "kind": kind,
        # The binding to a REAL job upload (kind PHOTO). Optional while drafting; a required slot only
        # COUNTS once bound (see missing_required_evidence) — evidence is never invented.
        "upload_id": _opt_str(raw.get("upload_id"), "photo.upload_id"),
        "station": _opt_str(raw.get("station"), "photo.station"),
        "offset_ft": _opt_num(raw.get("offset_ft"), "photo.offset_ft"),
        "note": _opt_str(raw.get("note"), "photo.note"),
        "captured_at": _opt_str(raw.get("captured_at"), "photo.captured_at"),
    }


def _normalize_problem(raw, seen_ids: set) -> dict:
    if not isinstance(raw, dict):
        raise InvalidFieldEvidenceError("each problem must be an object (got %r)" % (raw,))
    ptype = _req_str(raw.get("type"), "problem.type")
    if ptype not in PROBLEM_TYPES:
        raise InvalidFieldEvidenceError("problem.type must be one of %s (got %r)" % (list(PROBLEM_TYPES), ptype))
    photo_ids = raw.get("photo_evidence_ids", [])
    if not isinstance(photo_ids, list) or not all(isinstance(p, str) for p in photo_ids):
        raise InvalidFieldEvidenceError("problem.photo_evidence_ids must be a list of photo evidence ids")
    return {
        "problem_id": _unique_id(seen_ids, _req_str(raw.get("problem_id"), "problem.problem_id"), "problem.problem_id"),
        "type": ptype,
        "station": _opt_str(raw.get("station"), "problem.station"),
        "offset_ft": _opt_num(raw.get("offset_ft"), "problem.offset_ft"),
        "note": _opt_str(raw.get("note"), "problem.note"),
        "photo_evidence_ids": list(photo_ids),
    }


def _normalize_reading(raw, seen_ids: set) -> dict:
    if not isinstance(raw, dict):
        raise InvalidFieldEvidenceError("each reading must be an object (got %r)" % (raw,))
    method = _opt_str(raw.get("method"), "reading.method")
    if method is not None and method not in READING_METHODS:
        raise InvalidFieldEvidenceError("reading.method must be one of %s (got %r)" % (list(READING_METHODS), method))
    problem = raw.get("problem", False)
    if not isinstance(problem, bool):
        raise InvalidFieldEvidenceError("reading.problem must be a boolean when present (got %r)" % (problem,))
    return {
        "reading_id": _unique_id(seen_ids, _req_str(raw.get("reading_id"), "reading.reading_id"), "reading.reading_id"),
        # offset_ft = distance from segment start: the plotting axis for the future digital
        # redline/proof surface. Cadence is whatever the crew recorded (~50 ft nominal, NOT enforced).
        "offset_ft": _req_num(raw.get("offset_ft"), "reading.offset_ft", minimum=0.0),
        "station": _opt_str(raw.get("station"), "reading.station"),
        "depth_ft": _req_num(raw.get("depth_ft"), "reading.depth_ft", minimum=0.0),
        "pitch_pct": _opt_num(raw.get("pitch_pct"), "reading.pitch_pct"),
        "method": method,
        "recorded_at": _opt_str(raw.get("recorded_at"), "reading.recorded_at"),
        "note": _opt_str(raw.get("note"), "reading.note"),
        "problem": problem,
        "evidence_id": _opt_str(raw.get("evidence_id"), "reading.evidence_id"),
    }


def _normalize_payload(payload) -> dict:
    if not isinstance(payload, dict):
        raise InvalidFieldEvidenceError("field-evidence payload must be an object")
    photos_raw = payload.get("photos", [])
    problems_raw = payload.get("problems", [])
    readings_raw = payload.get("readings", [])
    for name, val in (("photos", photos_raw), ("problems", problems_raw), ("readings", readings_raw)):
        if not isinstance(val, list):
            raise InvalidFieldEvidenceError("%s must be a list" % name)

    photo_ids: set = set()
    photos = [_normalize_photo(p, photo_ids) for p in photos_raw]
    problem_ids: set = set()
    problems = [_normalize_problem(p, problem_ids) for p in problems_raw]
    reading_ids: set = set()
    readings = [_normalize_reading(r, reading_ids) for r in readings_raw]

    for prob in problems:                                     # problem photo refs must exist and be PROBLEM_AREA
        for pid in prob["photo_evidence_ids"]:
            match = next((ph for ph in photos if ph["evidence_id"] == pid), None)
            if match is None:
                raise InvalidFieldEvidenceError(
                    "problem %r references unknown photo evidence id %r" % (prob["problem_id"], pid))
            if match["kind"] != PROBLEM_AREA:
                raise InvalidFieldEvidenceError(
                    "problem %r photo %r must have kind %s (got %s)"
                    % (prob["problem_id"], pid, PROBLEM_AREA, match["kind"]))

    return {
        "reviewed_bore_log_id": _opt_str(payload.get("reviewed_bore_log_id"), "reviewed_bore_log_id"),
        "source_span_ref": _opt_str(payload.get("source_span_ref"), "source_span_ref"),
        "start_station": _opt_str(payload.get("start_station"), "start_station"),
        "end_station": _opt_str(payload.get("end_station"), "end_station"),
        "photos": photos,
        "problems": problems,
        "readings": readings,
        "notes": _opt_str(payload.get("notes"), "notes"),
    }


# --------------------------------------------------------------------------- #
# Required-evidence rules (pure; deterministic reason order).
# --------------------------------------------------------------------------- #
def _bound_photo_upload_ids(job: dict) -> set:
    return {u.get("upload_id") for u in (job.get("uploads") or []) if u.get("kind") == "PHOTO"}


def _has_bound_photo(record: dict, job_photo_ids: set, kind: str) -> bool:
    return any(ph["kind"] == kind and ph.get("upload_id") in job_photo_ids
               for ph in record.get("photos", []))


def missing_required_evidence(record: dict, job: dict) -> list:
    """Return the NAMED missing-evidence reasons for this package, in deterministic order (start photo,
    end photo, then each problem in list order). Empty list == the required evidence exists. A required
    photo counts ONLY when it binds (``upload_id``) to an existing job upload of kind PHOTO — a claimed
    photo with no real upload behind it satisfies nothing. OPTIONAL_CONTEXT photos are never required."""
    job_photo_ids = _bound_photo_upload_ids(job)
    missing = []
    if not _has_bound_photo(record, job_photo_ids, START_STATION):
        missing.append({"code": MISSING_START_STATION_PHOTO,
                        "reason": "a start station photo (bound to a real PHOTO upload) is required to begin this segment"})
    if not _has_bound_photo(record, job_photo_ids, END_STATION):
        missing.append({"code": MISSING_END_STATION_PHOTO,
                        "reason": "an end station photo (bound to a real PHOTO upload) is required to complete this segment"})
    photos_by_id = {ph["evidence_id"]: ph for ph in record.get("photos", [])}
    for prob in record.get("problems", []):
        bound = any(photos_by_id.get(pid, {}).get("upload_id") in job_photo_ids
                    for pid in prob.get("photo_evidence_ids", []))
        if not bound:
            missing.append({"code": PROBLEM_PHOTO_REQUIRED,
                            "problem_id": prob["problem_id"], "type": prob["type"],
                            "reason": "problem area %r (%s) requires at least one problem photo bound to a real PHOTO upload"
                                      % (prob["problem_id"], prob["type"])})
    return missing


_DOCTRINE_FLAGS = {
    "creates_redline": False,
    "performs_auto": False,
    "performs_placement": False,
    "review_support_only": True,
}


# --------------------------------------------------------------------------- #
# Store operations (tenant-safe by construction: every path flows through job_dir + load_job).
# --------------------------------------------------------------------------- #
def save_field_evidence(store_root, customer_project_id, processing_job_id, segment_id,
                        payload, *, at, by) -> dict:
    """Create or update (upsert) the DRAFT field-evidence package for one segment. Saving never submits
    and never changes status; a package already SUBMITTED_FOR_REVIEW is locked (review owns it)."""
    job = load_job(store_root, customer_project_id, processing_job_id)   # exists + isolation first
    path = _fe_path(store_root, customer_project_id, processing_job_id, segment_id)
    normalized = _normalize_payload(payload)

    created_at, audit = at, []
    if path.is_file():
        prior = json.loads(path.read_text(encoding="utf-8"))
        if prior.get("status") == SUBMITTED_FOR_REVIEW:
            raise FieldEvidenceLockedError(
                "field evidence %r was already submitted for review — edits are locked" % segment_id)
        created_at = prior.get("created_at", at)
        audit = list(prior.get("audit", []))
    audit.append({"action": "field_evidence_saved", "at": at, "by": by})

    record = {
        "record_format": FIELD_EVIDENCE_RECORD_FORMAT,
        "customer_project_id": customer_project_id,
        "processing_job_id": job["job_id"],
        "segment_id": segment_id,
        "status": DRAFT,
        **normalized,
        **_DOCTRINE_FLAGS,
        "created_at": created_at,
        "updated_at": at,
        "updated_by": by,
        "audit": audit,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def load_field_evidence(store_root, customer_project_id, processing_job_id, segment_id) -> dict:
    load_job(store_root, customer_project_id, processing_job_id)
    path = _fe_path(store_root, customer_project_id, processing_job_id, segment_id)
    if not path.is_file():
        raise FieldEvidenceNotFoundError(
            "no field evidence for segment %r on job %r" % (segment_id, processing_job_id))
    return json.loads(path.read_text(encoding="utf-8"))


def list_field_evidence(store_root, customer_project_id, processing_job_id) -> list:
    load_job(store_root, customer_project_id, processing_job_id)
    fdir = _fe_dir(store_root, customer_project_id, processing_job_id)
    if not fdir.is_dir():
        return []
    out = []
    for p in sorted(fdir.glob("*.json")):
        out.append(json.loads(p.read_text(encoding="utf-8")))
    return out


def submit_field_evidence(store_root, customer_project_id, processing_job_id, segment_id,
                          *, at, by) -> dict:
    """Validate the owner's required-evidence rules and either transition the package to
    SUBMITTED_FOR_REVIEW or REFUSE with the named ``BLOCKED_MISSING_REQUIRED_EVIDENCE`` reasons (the
    record stays DRAFT; nothing is silently accepted). Submitting performs NO AUTO, NO placement, NO
    redline generation, NO job status/slot change — review happens in the office product."""
    job = load_job(store_root, customer_project_id, processing_job_id)
    record = load_field_evidence(store_root, customer_project_id, processing_job_id, segment_id)

    if record.get("status") == SUBMITTED_FOR_REVIEW:           # idempotent: already with review
        return {"submitted": True, "status": SUBMITTED_FOR_REVIEW, "segment_id": segment_id,
                "missing_evidence": [], **_DOCTRINE_FLAGS}

    missing = missing_required_evidence(record, job)
    if missing:
        return {"submitted": False, "status": DRAFT, "segment_id": segment_id,
                "blocked": BLOCKED_MISSING_REQUIRED_EVIDENCE, "missing_evidence": missing,
                **_DOCTRINE_FLAGS}

    record["status"] = SUBMITTED_FOR_REVIEW
    record["submitted_at"] = at
    record["submitted_by"] = by
    record["updated_at"] = at
    record["updated_by"] = by
    record.setdefault("audit", []).append({"action": "field_evidence_submitted", "at": at, "by": by})
    path = _fe_path(store_root, customer_project_id, processing_job_id, segment_id)
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return {"submitted": True, "status": SUBMITTED_FOR_REVIEW, "segment_id": segment_id,
            "missing_evidence": [], **_DOCTRINE_FLAGS}
