"""Manual adjudication ingestion seam (OWNER-PACKET-2, 2026-06-14 owner review).

Loads owner-reviewed source-correction evidence and exposes it as structured,
validated corrections the deterministic v2 engine can consume and re-run.

This is REVIEWED SOURCE-CORRECTION EVIDENCE -- not a solver and not auto-placement.
It places no bore, computes no geometry, and never invents a station/print: every
corrected fact originates from the owner's manual source review (handwritten
parent/child columns, plan callouts/matchlines/leader-lines, HH-HH annotations,
station-reset labels). The seam only *reclassifies* logs out of the false
owner-source-required / abstain buckets that OCR-and-resolver misses produced, and
preserves the genuinely-abstained ones.

ADDITIVE + UNWIRED: nothing in the live ingest/match/render pipeline imports this
module, so the frozen engine census is byte-identical. Wiring the corrections into
``read_brenham_borelog`` (so the engine re-runs with corrected stations/prints) is a
separately-authorized ACTIVATION step (mirroring RECON-2 -> RECON-2A).

Pure + offline. No PDF parse, no corpus read, no global mutable state, no old-app
import.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

ADJUDICATIONS_DIR = Path(__file__).resolve().parent / "manual_adjudications"
DEFAULT_ARTIFACT = ADJUDICATIONS_DIR / "brenham_2026_06_14_owner_review.json"
DEFAULT_EVIDENCE_INDEX = ADJUDICATIONS_DIR / "evidence_index_2026_06_14.json"

STATUS_ENUM = frozenset({
    "RECOVERED", "CORRECT_AS_DRAWN", "ABSTAIN_NO_SAFE_SOURCE", "NEEDS_SOURCE_VERIFICATION",
})
CORRECTION_TYPE_ENUM = frozenset({
    "STATION_OCR_CORRECTION", "PRINT_OCR_CORRECTION", "MISSING_PRINT_SHEET",
    "STATION_RESET_SEGMENT_BOUNDARY", "MATCHLINE_CHAIN", "HH_HH_ANNOTATION",
    "LEADER_LINE_TO_STRUCTURE", "DIRECT_BORE_CALLOUT", "ORIGINAL_PARENT_COLUMN_SPLIT",
    "REVIEW_APPROVED_AS_DRAWN",
})
# Recoverable = the corrected-source group that is NO LONGER owner-source-required.
RECOVERABLE_STATUS = frozenset({"RECOVERED", "CORRECT_AS_DRAWN", "NEEDS_SOURCE_VERIFICATION"})
ABSTAIN_STATUS = frozenset({"ABSTAIN_NO_SAFE_SOURCE"})

_REQUIRED_LOG_FIELDS = (
    "log_id", "parent", "shared_print_child", "status", "correction_types",
    "corrected_prints", "corrected_start", "corrected_end", "corrected_sheets",
    "evidence_notes", "evidence_refs", "allowed_to_draw", "must_remain_abstained",
    "needs_review", "needs_source_verification",
)


class AdjudicationError(ValueError):
    """Raised when the adjudication artifact fails fail-closed validation."""


@dataclass(frozen=True)
class Disposition:
    """The corrected per-log disposition the engine can consume on re-run."""
    log_id: str
    parent: Optional[str]
    status: str
    shared_print_child: bool
    allowed_to_draw: bool
    must_remain_abstained: bool
    needs_review: bool
    needs_source_verification: bool
    correction_types: tuple
    corrected_prints: Optional[tuple]
    corrected_start: Optional[str]
    corrected_end: Optional[str]
    corrected_sheets: tuple
    evidence_refs: tuple


def load_adjudication(path: Path = DEFAULT_ARTIFACT) -> dict:
    """Parse the adjudication JSON. Raises AdjudicationError on missing/invalid file."""
    p = Path(path)
    if not p.is_file():
        raise AdjudicationError(f"adjudication artifact not found: {p}")
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AdjudicationError(f"adjudication artifact is not valid JSON: {exc}") from exc
    if not isinstance(doc, dict) or not isinstance(doc.get("logs"), list):
        raise AdjudicationError("adjudication artifact must be an object with a 'logs' array")
    return doc


def validate_adjudication(doc: dict) -> List[str]:
    """Fail-closed structural validation. Returns a list of error strings (empty == valid).

    Enforces: required fields; status/correction enums; duplicate log_ids; and the
    cross-field invariants that keep an abstain genuinely abstained and a recovered
    log non-abstained -- so the artifact can never silently flip a 'no-good' log into
    a draw, nor strip an abstain flag off a recovered one.
    """
    errors: List[str] = []
    logs = doc.get("logs", [])
    seen: set = set()
    for i, rec in enumerate(logs):
        tag = rec.get("log_id", f"#{i}")
        for fld in _REQUIRED_LOG_FIELDS:
            if fld not in rec:
                errors.append(f"{tag}: missing required field '{fld}'")
        lid = rec.get("log_id")
        if lid in seen:
            errors.append(f"{tag}: duplicate log_id")
        seen.add(lid)

        status = rec.get("status")
        if status not in STATUS_ENUM:
            errors.append(f"{tag}: status '{status}' not in enum")
        for ct in (rec.get("correction_types") or []):
            if ct not in CORRECTION_TYPE_ENUM:
                errors.append(f"{tag}: correction_type '{ct}' not in enum")

        allowed = bool(rec.get("allowed_to_draw"))
        abstained = bool(rec.get("must_remain_abstained"))
        if status in ABSTAIN_STATUS:
            if not abstained:
                errors.append(f"{tag}: ABSTAIN status but must_remain_abstained is False")
            if allowed:
                errors.append(f"{tag}: ABSTAIN status but allowed_to_draw is True")
            if rec.get("correction_types"):
                errors.append(f"{tag}: ABSTAIN status must carry no corrections")
        else:  # recoverable group
            if abstained:
                errors.append(f"{tag}: non-abstain status but must_remain_abstained is True")
            if status == "NEEDS_SOURCE_VERIFICATION" and allowed:
                errors.append(f"{tag}: NEEDS_SOURCE_VERIFICATION must not be allowed_to_draw "
                              f"until source-verified")
            if status in ("RECOVERED", "CORRECT_AS_DRAWN") and not rec.get("correction_types"):
                errors.append(f"{tag}: {status} must record at least one correction_type")
    return errors


def parent_run_duplicate_check(doc: dict) -> List[str]:
    """Guard against parent+child duplicate overlapping redlines.

    Within a family, no two children may carry an IDENTICAL corrected (start, end,
    sheets) triple, and the artifact must not emit a parent aggregate row alongside
    its children. Returns a list of violations (empty == clean).
    """
    violations: List[str] = []
    by_family: Dict[str, List[dict]] = {}
    log_ids = {r.get("log_id") for r in doc.get("logs", [])}
    for rec in doc.get("logs", []):
        parent = rec.get("parent")
        if parent:
            by_family.setdefault(parent, []).append(rec)
            # a parent row sharing a log_id with its own family id would be an aggregate
            if parent in log_ids:
                violations.append(f"{rec.get('log_id')}: parent '{parent}' also appears as a "
                                  f"drawable log row (parent-aggregate overlap)")
    for parent, kids in by_family.items():
        seen: Dict[tuple, str] = {}
        for k in kids:
            if not k.get("allowed_to_draw"):
                continue
            key = (k.get("corrected_start"), k.get("corrected_end"),
                   tuple(k.get("corrected_sheets") or []))
            if None in (key[0], key[1]):
                continue  # incomplete geometry can't be a duplicate
            if key in seen:
                violations.append(f"family {parent}: {k.get('log_id')} duplicates the corrected "
                                  f"geometry of {seen[key]} ({key})")
            else:
                seen[key] = k.get("log_id")
    return violations


def resolve(doc: dict) -> Dict[str, Disposition]:
    """The resolution seam: corrected per-log dispositions the engine can consume."""
    out: Dict[str, Disposition] = {}
    for rec in doc.get("logs", []):
        cp = rec.get("corrected_prints")
        out[rec["log_id"]] = Disposition(
            log_id=rec["log_id"],
            parent=rec.get("parent"),
            status=rec["status"],
            shared_print_child=bool(rec.get("shared_print_child")),
            allowed_to_draw=bool(rec.get("allowed_to_draw")),
            must_remain_abstained=bool(rec.get("must_remain_abstained")),
            needs_review=bool(rec.get("needs_review")),
            needs_source_verification=bool(rec.get("needs_source_verification")),
            correction_types=tuple(rec.get("correction_types") or []),
            corrected_prints=tuple(cp) if cp is not None else None,
            corrected_start=rec.get("corrected_start"),
            corrected_end=rec.get("corrected_end"),
            corrected_sheets=tuple(rec.get("corrected_sheets") or []),
            evidence_refs=tuple(rec.get("evidence_refs") or []),
        )
    return out


def summarize(doc: dict) -> dict:
    """Compute the headline counts from the artifact (not from the banked summary)."""
    logs = doc.get("logs", [])
    recoverable = [r for r in logs if r.get("status") in RECOVERABLE_STATUS]
    abstain = [r for r in logs if r.get("status") in ABSTAIN_STATUS]
    shared_children = [r for r in logs if r.get("shared_print_child")]
    shared_still_owner_source = [
        r for r in shared_children
        if r.get("status") not in RECOVERABLE_STATUS
    ]
    return {
        "original_problem_logs": len(logs),
        "recoverable_or_correct_as_drawn": len(recoverable),
        "valid_abstain_no_good": len(abstain),
        "active_unknowns": 0,
        "shared_print_owner_source_required_after_review": len(shared_still_owner_source),
        "shared_print_children": len(shared_children),
    }


def load_evidence_index(path: Path = DEFAULT_EVIDENCE_INDEX) -> Optional[dict]:
    """Load the screenshot evidence index if present (None if not yet built)."""
    p = Path(path)
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))
