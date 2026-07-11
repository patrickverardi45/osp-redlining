"""Contract tests: the untrusted extracted_row + its review state. Pure stdlib; no engine/render/wiring.
Generic ids/values only — no customer/person/project/location strings.
"""
from __future__ import annotations

import json

import pytest

from truelinev2.contracts import extracted_row as er
from truelinev2.contracts.extracted_row import (
    CONFIRMED,
    CORRECTED,
    EXTRACTION_METHODS,
    MANUAL_ENTRY,
    NEEDS_CLARIFICATION,
    OCR,
    REJECTED,
    RE_REVIEW_WOULD_DISCARD_CORRECTIONS,
    TABLE_IMPORT,
    TEXT_PARSE,
    UNREVIEWED,
    InvalidExtractionMethodError,
    InvalidReviewStatusError,
    ReReviewWouldDiscardCorrectionsError,
    ReviewInputError,
    new_extracted_row,
    review_row,
    row_review_blocks_engine,
    row_review_passes,
)

AT = "2026-06-21T00:00:00Z"
BY = "operator-1"


def _row(method=OCR, confidence="LOW"):
    return new_extracted_row("row-1", "up-abc123", raw={"station": "0+00"},
                             normalized={"station": "0+00"}, extraction_method=method,
                             extractor_name="tool-x", confidence=confidence, at=AT, by=BY)


def test_new_row_is_untrusted_by_default():
    row = _row()
    assert row["review"]["status"] == UNREVIEWED
    assert row_review_passes(row) is False and row_review_blocks_engine(row) is True
    assert row["audit"][0]["action"] == "row_created" and row["audit"][0]["to"] == UNREVIEWED
    assert row["normalized"] == {"station": "0+00"} and row["raw"] == {"station": "0+00"}


def test_all_methods_supported_and_untrusted():
    assert set(EXTRACTION_METHODS) == {OCR, TEXT_PARSE, TABLE_IMPORT, MANUAL_ENTRY}
    for m in EXTRACTION_METHODS:
        row = _row(method=m, confidence=None)               # confidence optional (manual/import)
        assert row["review"]["status"] == UNREVIEWED        # untrusted regardless of method
        assert row["extraction"]["extraction_method"] == m
        assert row["extraction"]["confidence"] is None


def test_extraction_metadata_generic_no_engine_field():
    ex = _row()["extraction"]
    assert "extraction_method" in ex and "extractor_name" in ex
    assert "engine" not in ex                                # 'engine' is reserved for the placement engine
    assert ex["extractor_name"] == "tool-x"                 # opaque runtime data


def test_bad_method_and_confidence_rejected():
    with pytest.raises(InvalidExtractionMethodError):
        new_extracted_row("row-1", "up-1", raw={}, normalized={}, extraction_method="MAGIC", at=AT, by=BY)
    with pytest.raises(er.ExtractedRowError):
        new_extracted_row("row-1", "up-1", raw={}, normalized={}, extraction_method=OCR,
                          confidence="SUPER", at=AT, by=BY)


def test_confirm_makes_review_pass():
    row = review_row(_row(), CONFIRMED, at=AT, by=BY)
    assert row_review_passes(row) is True
    assert row["review"]["reviewed_by"] == BY and row["review"]["reviewed_at"] == AT
    assert row["audit"][-1]["from"] == UNREVIEWED and row["audit"][-1]["to"] == CONFIRMED


def test_corrected_requires_values_and_audits_prior():
    row = _row()
    with pytest.raises(ReviewInputError):
        review_row(row, CORRECTED, at=AT, by=BY)            # no corrected_values
    row = review_row(row, CORRECTED, at=AT, by=BY, corrected_values={"station": "0+10"})
    assert row_review_passes(row) is True
    assert row["review"]["corrected_values"] == {"station": "0+10"}
    assert row["audit"][-1]["corrected_values"] == {"station": "0+10"}


def test_reject_and_needs_clarification_require_reason():
    for status in (REJECTED, NEEDS_CLARIFICATION):
        row = _row()
        with pytest.raises(ReviewInputError):
            review_row(row, status, at=AT, by=BY)           # no reason
        row = review_row(row, status, at=AT, by=BY, reason="r")
        assert row["review"]["status"] == status
        assert row_review_passes(row) is False              # neither is a placement candidate


def test_invalid_status_rejected():
    with pytest.raises(InvalidReviewStatusError):
        review_row(_row(), "MAYBE", at=AT, by=BY)


def test_re_review_allowed_and_audited():
    row = review_row(_row(), NEEDS_CLARIFICATION, at=AT, by=BY, reason="unclear")
    row = review_row(row, CONFIRMED, at=AT, by=BY)          # re-review after clarification
    assert row_review_passes(row) is True
    assert [a["to"] for a in row["audit"]] == [UNREVIEWED, NEEDS_CLARIFICATION, CONFIRMED]


# --------------------------------------------------------------------------- #
# Doctrine guard: banked human review (corrected_values) is never silently overridden by a plain re-review.
# --------------------------------------------------------------------------- #
def test_confirmed_re_review_wiping_corrections_is_refused():
    row = review_row(_row(), CORRECTED, at=AT, by=BY, corrected_values={"station": "0+10"})
    with pytest.raises(ReReviewWouldDiscardCorrectionsError) as exc:
        review_row(row, CONFIRMED, at=AT, by=BY)              # no corrected_values -> would wipe
    assert RE_REVIEW_WOULD_DISCARD_CORRECTIONS in str(exc.value)
    # Mutates NOTHING: the row's banked review state (status/corrected_values/audit) is untouched.
    assert row["review"]["status"] == CORRECTED
    assert row["review"]["corrected_values"] == {"station": "0+10"}
    assert len(row["audit"]) == 2                             # row_created + the original CORRECTED entry


def test_confirmed_re_review_resending_same_corrections_is_ok():
    # The caller may re-send CORRECTED with the SAME (or updated) corrections -- that's an explicit intent,
    # never silently discarded, so it stays idempotent-OK.
    row = review_row(_row(), CORRECTED, at=AT, by=BY, corrected_values={"station": "0+10"})
    row = review_row(row, CORRECTED, at=AT, by=BY, corrected_values={"station": "0+10"})
    assert row["review"]["status"] == CORRECTED
    assert row["review"]["corrected_values"] == {"station": "0+10"}


def test_confirmed_re_review_idempotent_when_no_corrections_to_lose():
    # CONFIRMED -> CONFIRMED again with no corrections: the row never had corrections, so nothing would be
    # discarded -- stays idempotent-OK (the guard only fires when corrected_values is ALREADY non-empty).
    row = review_row(_row(), CONFIRMED, at=AT, by=BY)
    row = review_row(row, CONFIRMED, at=AT, by=BY)
    assert row["review"]["status"] == CONFIRMED
    assert row["review"]["corrected_values"] is None


def test_fresh_row_confirmed_unaffected_by_guard():
    row = review_row(_row(), CONFIRMED, at=AT, by=BY)          # never corrected -> no guard trip
    assert row["review"]["status"] == CONFIRMED
    assert row_review_passes(row) is True


def test_no_row_level_engine_eligibility_symbol():
    # correction 1: a row ALONE can never be engine-eligible (grouping is required); this module must
    # NOT expose any row-level engine-eligibility predicate.
    for forbidden in ("row_is_engine_eligible", "engine_eligible", "row_engine_eligible"):
        assert not hasattr(er, forbidden)


# --------------------------------------------------------------------------- #
# Additive: optional per-cell evidence (Phase-1 handwritten extraction, see
# contracts/handwritten_extraction.py). Absent by default -- byte-identical extraction dict for every
# existing call site; present ONLY when a caller actually supplies it.
# --------------------------------------------------------------------------- #
def test_extraction_dict_unchanged_when_evidence_omitted():
    row = _row()
    assert set(row["extraction"].keys()) == {"extraction_method", "extractor_name", "confidence", "warnings"}
    assert "source_evidence" not in row["extraction"] and "cell_evidence" not in row["extraction"]


def test_source_and_cell_evidence_round_trip_when_supplied():
    source_evidence = {"sha256": "a" * 64, "file": "page.jpg", "page_index": 0, "region": [0.1, 0.1, 0.9, 0.9]}
    cell_evidence = {
        "start_station": {"status": "READ", "page_index": 0, "region": [0.0, 0.0, 0.5, 0.5], "verbatim": "48+52"},
        "depth_ft": {"status": "UNREADABLE", "page_index": 0, "region": None, "verbatim": None},
    }
    row = new_extracted_row("row-1", "up-abc123", raw={"start_station": "48+52"}, normalized={},
                            extraction_method=OCR, confidence="LOW",
                            source_evidence=source_evidence, cell_evidence=cell_evidence, at=AT, by=BY)
    assert row["extraction"]["source_evidence"] == source_evidence
    assert row["extraction"]["cell_evidence"] == cell_evidence
    # JSON round-trip (rows persist as plain JSON inside reviewed_bore_log.py) preserves both additions.
    reloaded = json.loads(json.dumps(row))
    assert reloaded["extraction"]["source_evidence"] == source_evidence
    assert reloaded["extraction"]["cell_evidence"] == cell_evidence


def test_old_shape_row_without_evidence_keys_still_reviewable():
    # Simulates a record persisted BEFORE this additive evolution: no source_evidence/cell_evidence keys
    # at all. review_row / row_review_passes must work unchanged (no KeyError, no migration needed).
    row = _row()
    assert "source_evidence" not in row["extraction"] and "cell_evidence" not in row["extraction"]
    row = review_row(row, CONFIRMED, at=AT, by=BY)
    assert row_review_passes(row) is True
