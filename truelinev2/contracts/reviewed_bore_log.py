"""Permanent v2 product foundation — the reviewed_bore_log engine-eligibility gate (contract-only).

The MANDATORY gate between EXTRACTING and PLACING (contract §3): untrusted extracted_rows are grouped into
segment_groups and reviewed by a human; only then may a row become ENGINE-ELIGIBLE. The placement engine
consumes ONLY eligible rows. This module owns the aggregate record (attached to one processing_job under
its customer_project scope), the segment grouping, the audited review/grouping operations, durable JSON
persistence, and the DERIVED eligibility gate.

Engine eligibility is DERIVED ONLY — never stored as mutable truth (that was v1's defect: several
disagreeing readiness signals — salvage audit item 4c). A row is engine-eligible iff its review passed
AND it resolves into EXACTLY ONE confirmed, non-ambiguous, non-conflicting segment_group (a row that is
ungrouped, in >1 group, or in a PENDING / AMBIGUOUS / SOURCE_CONFLICT group is blocked). An empty record
is never engine-ready. Contract-only: no engine, renderer, web/backend, AI/OCR provider, or placement.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from truelinev2.contracts.customer_project import assert_same_project, validate_customer_project_id
from truelinev2.contracts.processing_job import job_dir, load_job, validate_job_id
from truelinev2.contracts.extracted_row import (
    CONFIRMED,
    CORRECTED,
    REJECTED,
    review_row,
    row_review_passes,
)

REVIEWED_BORE_LOG_RECORD_FORMAT = "trueline-reviewed-bore-log-1"
REVIEWED_BORE_LOGS_SUBDIR = "reviewed_bore_logs"
REVIEWED_BORE_LOG_FILENAME = "_reviewed_bore_log.json"
BORE_LOG_UPLOAD_KIND = "BORE_LOG"

_RBL_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")

# segment_group relations: is this group one bore, several segments of one run, or undecided?
SEPARATE_BORE = "SEPARATE_BORE"
SAME_RUN_SEGMENTS = "SAME_RUN_SEGMENTS"
AMBIGUOUS = "AMBIGUOUS"
SEGMENT_RELATIONS = (SEPARATE_BORE, SAME_RUN_SEGMENTS, AMBIGUOUS)
# Only these relations (when the group is CONFIRMED) admit engine eligibility.
ELIGIBLE_RELATIONS = (SEPARATE_BORE, SAME_RUN_SEGMENTS)

# segment_group review state. SOURCE_CONFLICT == an unresolved grouping conflict.
GROUPING_PENDING = "PENDING"
GROUPING_CONFIRMED = "CONFIRMED"
SOURCE_CONFLICT = "SOURCE_CONFLICT"
GROUPING_STATUSES = (GROUPING_PENDING, GROUPING_CONFIRMED, SOURCE_CONFLICT)


class ReviewedBoreLogError(ValueError):
    """Base reviewed_bore_log error."""


class InvalidReviewedBoreLogIdError(ReviewedBoreLogError):
    """reviewed_bore_log id is missing or not filesystem/URL-safe."""


class ReviewedBoreLogNotFoundError(ReviewedBoreLogError):
    """No stored record for the requested reviewed_bore_log."""


class SourceUploadError(ReviewedBoreLogError):
    """source_upload_id is not a BORE_LOG upload in the referenced job."""


class RowNotFoundError(ReviewedBoreLogError):
    """No row with the requested row_id in this reviewed_bore_log."""


class GroupNotFoundError(ReviewedBoreLogError):
    """No segment_group with the requested group_id in this reviewed_bore_log."""


class InvalidRelationError(ReviewedBoreLogError):
    """segment_group relation is not one of SEGMENT_RELATIONS."""


class InvalidGroupingStatusError(ReviewedBoreLogError):
    """Requested grouping status is not one of GROUPING_STATUSES."""


def validate_reviewed_bore_log_id(reviewed_bore_log_id) -> str:
    if not isinstance(reviewed_bore_log_id, str) or not _RBL_ID_RE.match(reviewed_bore_log_id):
        raise InvalidReviewedBoreLogIdError(
            "reviewed_bore_log id must match %s (got %r)" % (_RBL_ID_RE.pattern, reviewed_bore_log_id))
    return reviewed_bore_log_id


def _rbl_dir(store_root, customer_project_id, processing_job_id, reviewed_bore_log_id) -> Path:
    validate_reviewed_bore_log_id(reviewed_bore_log_id)
    return (job_dir(store_root, customer_project_id, processing_job_id)
            / REVIEWED_BORE_LOGS_SUBDIR / reviewed_bore_log_id)


def _rbl_path(store_root, customer_project_id, processing_job_id, reviewed_bore_log_id) -> Path:
    return _rbl_dir(store_root, customer_project_id, processing_job_id,
                    reviewed_bore_log_id) / REVIEWED_BORE_LOG_FILENAME


def create_reviewed_bore_log(store_root, customer_project_id, processing_job_id, source_upload_id,
                             reviewed_bore_log_id, *, at, by) -> dict:
    """Create an empty reviewed_bore_log attached to an existing job + a BORE_LOG upload in it. Verifies
    the job exists and is in-scope, and that source_upload_id is a BORE_LOG upload. Raises on a duplicate
    id (no silent overwrite). Returns the new record."""
    validate_customer_project_id(customer_project_id)
    validate_job_id(processing_job_id)
    validate_reviewed_bore_log_id(reviewed_bore_log_id)
    job = load_job(store_root, customer_project_id, processing_job_id)   # exists + isolation
    upload = next((u for u in job.get("uploads", []) if u.get("upload_id") == source_upload_id), None)
    if upload is None:
        raise SourceUploadError("source_upload_id %r is not an upload in this job" % (source_upload_id,))
    if upload.get("kind") != BORE_LOG_UPLOAD_KIND:
        raise SourceUploadError(
            "source upload %r is not a %s upload" % (source_upload_id, BORE_LOG_UPLOAD_KIND))
    path = _rbl_path(store_root, customer_project_id, processing_job_id, reviewed_bore_log_id)
    if path.exists():
        raise ReviewedBoreLogError("reviewed_bore_log already exists: %s" % reviewed_bore_log_id)
    rbl = {
        "record_format": REVIEWED_BORE_LOG_RECORD_FORMAT,
        "reviewed_bore_log_id": reviewed_bore_log_id,
        "customer_project_id": customer_project_id,
        "processing_job_id": processing_job_id,
        "source_upload_id": source_upload_id,
        "rows": [],
        "groups": [],
        "audit": [{"action": "reviewed_bore_log_created", "at": at, "by": by, "reason": None}],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rbl, indent=2) + "\n", encoding="utf-8")
    return rbl


def load_reviewed_bore_log(store_root, customer_project_id, processing_job_id,
                           reviewed_bore_log_id) -> dict:
    path = _rbl_path(store_root, customer_project_id, processing_job_id, reviewed_bore_log_id)
    if not path.is_file():
        raise ReviewedBoreLogNotFoundError(
            "no reviewed_bore_log %s/%s/%s"
            % (customer_project_id, processing_job_id, reviewed_bore_log_id))
    rbl = json.loads(path.read_text(encoding="utf-8"))
    assert_same_project(customer_project_id, rbl.get("customer_project_id"))
    return rbl


def write_reviewed_bore_log(store_root, rbl) -> str:
    """Persist a record under its OWN (cp, job, rbl) scope (derived from the record, not ambient)."""
    cp = validate_customer_project_id(rbl["customer_project_id"])
    jid = validate_job_id(rbl["processing_job_id"])
    rid = validate_reviewed_bore_log_id(rbl["reviewed_bore_log_id"])
    path = _rbl_path(store_root, cp, jid, rid)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rbl, indent=2) + "\n", encoding="utf-8")
    return str(path)


def _find_row(rbl, row_id):
    return next((r for r in rbl["rows"] if r["row_id"] == row_id), None)


def _find_group(rbl, group_id):
    return next((g for g in rbl["groups"] if g["group_id"] == group_id), None)


def _row_group_memberships(rbl, row_id):
    return [g for g in rbl["groups"] if row_id in g["member_row_ids"]]


def add_extracted_rows(store_root, customer_project_id, processing_job_id, reviewed_bore_log_id, rows,
                       *, at, by) -> dict:
    """Append already-built extracted_row dicts (see extracted_row.new_extracted_row). Rejects a
    duplicate row_id. Returns the updated record."""
    rbl = load_reviewed_bore_log(store_root, customer_project_id, processing_job_id, reviewed_bore_log_id)
    known = {r["row_id"] for r in rbl["rows"]}
    added = []
    for row in rows:
        rid = row["row_id"]
        if rid in known:
            raise ReviewedBoreLogError("duplicate row_id %r" % (rid,))
        known.add(rid)
        rbl["rows"].append(row)
        added.append(rid)
    rbl["audit"].append({"action": "rows_added", "at": at, "by": by, "row_ids": added, "reason": None})
    write_reviewed_bore_log(store_root, rbl)
    return rbl


def review_row_in_log(store_root, customer_project_id, processing_job_id, reviewed_bore_log_id, row_id,
                      to_status, *, at, by, reason=None, corrected_values=None) -> dict:
    """Apply an audited review decision (extracted_row.review_row) to one row, then persist. Returns the
    updated record."""
    rbl = load_reviewed_bore_log(store_root, customer_project_id, processing_job_id, reviewed_bore_log_id)
    row = _find_row(rbl, row_id)
    if row is None:
        raise RowNotFoundError("no row %r in %s" % (row_id, reviewed_bore_log_id))
    review_row(row, to_status, at=at, by=by, reason=reason, corrected_values=corrected_values)
    rbl["audit"].append({"action": "row_reviewed", "at": at, "by": by,
                         "row_id": row_id, "to": to_status, "reason": reason})
    write_reviewed_bore_log(store_root, rbl)
    return rbl


def define_segment_group(store_root, customer_project_id, processing_job_id, reviewed_bore_log_id,
                         group_id, member_row_ids, relation, *, at, by) -> dict:
    """Define a segment_group (status PENDING) over >= 1 existing rows with a relation (SEPARATE_BORE /
    SAME_RUN_SEGMENTS / AMBIGUOUS). Rejects a duplicate group_id or an unknown member row. Returns the
    updated record."""
    if relation not in SEGMENT_RELATIONS:
        raise InvalidRelationError("relation must be one of %r (got %r)" % (SEGMENT_RELATIONS, relation))
    rbl = load_reviewed_bore_log(store_root, customer_project_id, processing_job_id, reviewed_bore_log_id)
    if not isinstance(group_id, str) or not group_id:
        raise ReviewedBoreLogError("group_id must be a non-empty string")
    if _find_group(rbl, group_id) is not None:
        raise ReviewedBoreLogError("duplicate group_id %r" % (group_id,))
    members = list(member_row_ids)
    if not members:
        raise ReviewedBoreLogError("a segment_group needs >= 1 member row")
    known = {r["row_id"] for r in rbl["rows"]}
    for rid in members:
        if rid not in known:
            raise RowNotFoundError("group member %r is not a row in this reviewed_bore_log" % (rid,))
    rbl["groups"].append({
        "group_id": group_id, "member_row_ids": members, "relation": relation,
        "grouping_status": GROUPING_PENDING, "reason": None,
        "audit": [{"action": "group_created", "at": at, "by": by,
                   "to": GROUPING_PENDING, "relation": relation, "reason": None}],
    })
    rbl["audit"].append({"action": "group_defined", "at": at, "by": by,
                         "group_id": group_id, "relation": relation, "reason": None})
    write_reviewed_bore_log(store_root, rbl)
    return rbl


def set_grouping_status(store_root, customer_project_id, processing_job_id, reviewed_bore_log_id,
                        group_id, to_status, *, at, by, reason=None) -> dict:
    """Set a segment_group's grouping status (PENDING -> CONFIRMED | SOURCE_CONFLICT). SOURCE_CONFLICT
    requires a reason. Returns the updated record."""
    if to_status not in GROUPING_STATUSES:
        raise InvalidGroupingStatusError(
            "grouping status must be one of %r (got %r)" % (GROUPING_STATUSES, to_status))
    if to_status == SOURCE_CONFLICT and not reason:
        raise ReviewedBoreLogError("SOURCE_CONFLICT requires a reason")
    rbl = load_reviewed_bore_log(store_root, customer_project_id, processing_job_id, reviewed_bore_log_id)
    group = _find_group(rbl, group_id)
    if group is None:
        raise GroupNotFoundError("no group %r in %s" % (group_id, reviewed_bore_log_id))
    frm = group["grouping_status"]
    group["grouping_status"] = to_status
    group["reason"] = reason
    group["audit"].append({"action": "grouping_status", "at": at, "by": by,
                           "from": frm, "to": to_status, "reason": reason})
    rbl["audit"].append({"action": "grouping_status", "at": at, "by": by,
                         "group_id": group_id, "from": frm, "to": to_status, "reason": reason})
    write_reviewed_bore_log(store_root, rbl)
    return rbl


# --------------------------------------------------------------------------- #
# DERIVED eligibility gate — never stored; recomputed from review + grouping every call.
# --------------------------------------------------------------------------- #
def row_engine_eligible(rbl, row_id) -> bool:
    """True iff the row passed review AND resolves into EXACTLY ONE confirmed, non-ambiguous,
    non-conflicting segment_group. A row in zero groups (ungrouped), in >1 group (drift), or in a
    PENDING / AMBIGUOUS / SOURCE_CONFLICT group is NOT eligible."""
    row = _find_row(rbl, row_id)
    if row is None or not row_review_passes(row):
        return False
    memberships = _row_group_memberships(rbl, row_id)
    if len(memberships) != 1:                       # 0 = ungrouped, > 1 = drift across groups
        return False
    group = memberships[0]
    return (group["grouping_status"] == GROUPING_CONFIRMED
            and group["relation"] in ELIGIBLE_RELATIONS)


def engine_eligible_row_ids(rbl) -> list:
    """All row_ids that are engine-eligible right now (derived; order follows rbl['rows'])."""
    return [r["row_id"] for r in rbl["rows"] if row_engine_eligible(rbl, r["row_id"])]


def is_engine_ready(rbl) -> bool:
    """True iff the reviewed_bore_log is ready for placement: there is >= 1 row, and EVERY non-rejected
    row is engine-eligible (so nothing remains unreviewed / needs-clarification / ungrouped / drifting /
    ambiguous / in conflict). An empty record is NEVER ready."""
    rows = rbl["rows"]
    if not rows:                                    # empty -> never ready
        return False
    non_rejected = {r["row_id"] for r in rows if r["review"]["status"] != REJECTED}
    eligible = set(engine_eligible_row_ids(rbl))
    return bool(eligible) and non_rejected == eligible


def grouping_conflicts(rbl) -> dict:
    """Derived read-only view of grouping problems that block eligibility: non-rejected rows that are
    ungrouped or in multiple groups (drift), and groups that are unresolved (PENDING / AMBIGUOUS /
    SOURCE_CONFLICT)."""
    ungrouped, drifting = [], []
    for r in rbl["rows"]:
        if r["review"]["status"] == REJECTED:
            continue
        n = len(_row_group_memberships(rbl, r["row_id"]))
        if n == 0:
            ungrouped.append(r["row_id"])
        elif n > 1:
            drifting.append(r["row_id"])
    unresolved = [g["group_id"] for g in rbl["groups"]
                  if g["grouping_status"] in (GROUPING_PENDING, SOURCE_CONFLICT)
                  or g["relation"] == AMBIGUOUS]
    return {"ungrouped_rows": ungrouped, "rows_in_multiple_groups": drifting,
            "unresolved_groups": unresolved}


def review_queue(rbl) -> dict:
    """Pure read-only view of what still needs attention before the log can be engine-ready (no side
    effects; re-runnable). Mirrors the v1 'pure-observation review' pattern (salvage audit item 7a)."""
    rows = rbl["rows"]
    needing = [r["row_id"] for r in rows
               if r["review"]["status"] not in (CONFIRMED, CORRECTED, REJECTED)]
    rejected = [r["row_id"] for r in rows if r["review"]["status"] == REJECTED]
    queue = {
        "rows_needing_review": needing,
        "rows_rejected": rejected,
        "rows_review_passed": [r["row_id"] for r in rows if row_review_passes(r)],
        "engine_eligible_row_ids": engine_eligible_row_ids(rbl),
        "engine_ready": is_engine_ready(rbl),
    }
    queue.update(grouping_conflicts(rbl))
    return queue
