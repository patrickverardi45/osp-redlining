"""Permanent v2 product foundation — the untrusted extracted_row + its review state (contract-only).

An `extracted_row` is ONE untrusted candidate row pulled into a processing_job's bore-log review — from
AI/OCR, a CSV/table import, or manual entry. It is NOT a placement candidate by default: it carries raw +
normalized-candidate values (suggestions, never truth — salvage audit item 1e) plus extraction
provenance, and a human must REVIEW it before the placement engine may consider it.

Row-level logic here is limited to REVIEW validity. A row ALONE can never be engine-eligible — true engine
eligibility also requires grouping and is derived ONLY in reviewed_bore_log.py.

Naming: `extraction_method`/`extractor_name` are generic; the originating tool/provider name is OPAQUE
RUNTIME DATA (never hardcoded). The word "engine" is reserved for the TrueLine placement engine and does
NOT appear in extraction metadata. Contract-only, pure functions on row dicts (rows live inside the
reviewed_bore_log record; this module owns no persistence). No engine, renderer, web/backend, or AI/OCR.
"""
from __future__ import annotations

# Review states for one extracted_row.
UNREVIEWED = "UNREVIEWED"
CONFIRMED = "CONFIRMED"
CORRECTED = "CORRECTED"
REJECTED = "REJECTED"
NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
REVIEW_STATUSES = (UNREVIEWED, CONFIRMED, CORRECTED, REJECTED, NEEDS_CLARIFICATION)

# A reviewed row is a placement CANDIDATE only when a human confirmed or corrected it.
REVIEW_PASS_STATUSES = (CONFIRMED, CORRECTED)

# Generic extraction methods — covers AI/OCR, deterministic text parsing, table imports, and manual
# entry. Every method produces an UNTRUSTED row. The tool/provider name is opaque runtime data.
OCR = "OCR"
TEXT_PARSE = "TEXT_PARSE"
TABLE_IMPORT = "TABLE_IMPORT"
MANUAL_ENTRY = "MANUAL_ENTRY"
EXTRACTION_METHODS = (OCR, TEXT_PARSE, TABLE_IMPORT, MANUAL_ENTRY)

# Optional extraction confidence (may be absent for manual/imported input).
HIGH = "HIGH"
MEDIUM = "MEDIUM"
LOW = "LOW"
CONFIDENCE_LEVELS = (HIGH, MEDIUM, LOW)


class ExtractedRowError(ValueError):
    """Base extracted_row error."""


class InvalidReviewStatusError(ExtractedRowError):
    """Requested review status is not one of REVIEW_STATUSES."""


class InvalidExtractionMethodError(ExtractedRowError):
    """Extraction method is not one of EXTRACTION_METHODS."""


class ReviewInputError(ExtractedRowError):
    """A review action is missing a required input (corrected_values / reason)."""


def _require_nonempty_str(value, label) -> str:
    if not isinstance(value, str) or not value:
        raise ExtractedRowError("%s must be a non-empty string (got %r)" % (label, value))
    return value


def new_extracted_row(row_id, source_upload_id, *, raw, normalized, extraction_method,
                      extractor_name=None, confidence=None, warnings=None,
                      source_evidence=None, cell_evidence=None, at, by) -> dict:
    """Build one UNTRUSTED extracted_row (status UNREVIEWED, not a candidate) with an opening audit
    entry. `normalized` holds candidate SUGGESTIONS, never truth. `extractor_name` is opaque runtime
    data (a tool/provider label, or None) — never a hardcoded provider name in code.

    `source_evidence` ({sha256, file, page_index, region|None}) and `cell_evidence`
    ({field: {status, page_index, region|None, verbatim|None}}) are ADDITIVE OPTIONAL per-cell
    provenance (Phase-1 handwritten-extraction contract, see contracts/handwritten_extraction.py). When
    omitted (the default, and every existing TABLE_IMPORT/MANUAL_ENTRY/TEXT_PARSE call site) the
    `extraction` dict is byte-identical to before this evolution — the keys are added ONLY when the
    caller actually supplies them, so old-shape rows (missing these keys entirely) remain valid without
    any schema migration."""
    _require_nonempty_str(row_id, "row_id")
    _require_nonempty_str(source_upload_id, "source_upload_id")
    if extraction_method not in EXTRACTION_METHODS:
        raise InvalidExtractionMethodError(
            "extraction_method must be one of %r (got %r)" % (EXTRACTION_METHODS, extraction_method))
    if confidence is not None and confidence not in CONFIDENCE_LEVELS:
        raise ExtractedRowError(
            "confidence must be None or one of %r (got %r)" % (CONFIDENCE_LEVELS, confidence))
    extraction = {
        "extraction_method": extraction_method,
        "extractor_name": extractor_name,          # opaque runtime data (nullable)
        "confidence": confidence,                  # optional (may be None for manual/import)
        "warnings": list(warnings or []),
    }
    if source_evidence is not None:
        extraction["source_evidence"] = dict(source_evidence)
    if cell_evidence is not None:
        extraction["cell_evidence"] = {k: dict(v) for k, v in cell_evidence.items()}
    return {
        "row_id": row_id,
        "source_upload_id": source_upload_id,
        "extraction": extraction,
        "raw": dict(raw),                              # raw extracted/imported/entered values
        "normalized": dict(normalized),                # candidate suggestions — never truth
        "review": {
            "status": UNREVIEWED, "reviewed_by": None, "reviewed_at": None,
            "corrected_values": None, "reason": None,
        },
        "audit": [{
            "action": "row_created", "at": at, "by": by,
            "from": None, "to": UNREVIEWED,
            "prior_values": None, "corrected_values": None, "reason": None,
        }],
    }


def review_row(row, to_status, *, at, by, reason=None, corrected_values=None) -> dict:
    """Apply one audited human review decision to a row. CORRECTED requires corrected_values;
    REJECTED / NEEDS_CLARIFICATION require a reason. Re-review is allowed (every decision is audited).
    Mutates + returns the row. Does NOT confer engine eligibility (grouping is required — see
    reviewed_bore_log.py)."""
    if to_status not in REVIEW_STATUSES:
        raise InvalidReviewStatusError(
            "review status must be one of %r (got %r)" % (REVIEW_STATUSES, to_status))
    if to_status == CORRECTED and not corrected_values:
        raise ReviewInputError("CORRECTED requires non-empty corrected_values")
    if to_status in (REJECTED, NEEDS_CLARIFICATION) and not reason:
        raise ReviewInputError("%s requires a reason" % to_status)
    frm = row["review"]["status"]
    prior_values = row["review"].get("corrected_values")
    corrected = dict(corrected_values) if corrected_values else None
    row["review"] = {
        "status": to_status, "reviewed_by": by, "reviewed_at": at,
        "corrected_values": corrected, "reason": reason,
    }
    row["audit"].append({
        "action": "row_review", "at": at, "by": by, "from": frm, "to": to_status,
        "prior_values": prior_values, "corrected_values": corrected, "reason": reason,
    })
    return row


def row_review_passes(row) -> bool:
    """True iff the row's REVIEW state makes it a placement candidate (human CONFIRMED or CORRECTED).
    Review-level only — this is NOT engine eligibility (grouping is also required)."""
    return row["review"]["status"] in REVIEW_PASS_STATUSES


def row_review_blocks_engine(row) -> bool:
    """True iff the row's REVIEW state alone disqualifies it (UNREVIEWED / REJECTED /
    NEEDS_CLARIFICATION). The complement of row_review_passes over REVIEW_STATUSES."""
    return not row_review_passes(row)
