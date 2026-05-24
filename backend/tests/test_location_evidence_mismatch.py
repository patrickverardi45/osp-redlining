"""B-MATCH-LOC-EVIDENCE-1 — diagnostic-only mismatch flag.

Covers compute_location_evidence_mismatch + extract_street_references in
backend/app/core/notes_street_evidence.py. Pure unit tests; no main.py
import; no STATE; no I/O; no fixtures.

HUISACHE bare-name case for bore_log71 is intentionally not asserted —
STREET_PATTERN requires a trailing road-type suffix and HUISACHE alone is
deferred. LAWNDALE AVE in the same notes string is sufficient to flag.
"""

from __future__ import annotations

import copy

import pytest

from app.core.notes_street_evidence import (
    compute_location_evidence_mismatch,
    extract_street_references,
)


def _group(notes: str) -> list:
    return [{"notes": notes, "station": "0+00", "station_ft": 0.0}]


def test_bore_log39_cheri_mismatch():
    group_rows = _group("WORKING NEAR CHERI LN INTERSECTION")
    filter_meta = {"street_hints": ["POST OAK CT", "GLENDA BLVD"]}

    result = compute_location_evidence_mismatch(group_rows, filter_meta)

    assert result is not None
    assert "CHERI LN" in result["notes_streets"]
    assert "POST OAK CT" in result["filter_streets"]
    assert "GLENDA BLVD" in result["filter_streets"]
    assert result["severity"] == "REVIEW"
    assert result["source"] == "bore_log_notes_vs_print_filter"


def test_bore_log71_lawndale_huisache_mismatch():
    # HUISACHE alone lacks a road-type suffix and is not extracted —
    # documented deferred limitation. LAWNDALE AVE is sufficient to flag.
    group_rows = _group("LAWNDALE AVE & HUISACHE")
    filter_meta = {"street_hints": ["CARLEE DR", "POST OAK CT"]}

    result = compute_location_evidence_mismatch(group_rows, filter_meta)

    assert result is not None
    assert "LAWNDALE AVE" in result["notes_streets"]
    assert "HUISACHE" not in result["notes_streets"]
    assert result["filter_streets"] == ["CARLEE DR", "POST OAK CT"]
    assert result["severity"] == "REVIEW"
    assert result["source"] == "bore_log_notes_vs_print_filter"


def test_bore_log72_lawndale_mismatch():
    group_rows = _group("BORE ALONG LAWNDALE AVE")
    filter_meta = {"street_hints": ["CARLEE DR", "POST OAK CT"]}

    result = compute_location_evidence_mismatch(group_rows, filter_meta)

    assert result is not None
    assert result["notes_streets"] == ["LAWNDALE AVE"]
    assert result["filter_streets"] == ["CARLEE DR", "POST OAK CT"]
    assert result["severity"] == "REVIEW"


def test_no_mismatch_when_streets_align():
    group_rows = _group("BORE AT E STONE ST CROSSING")
    filter_meta = {"street_hints": ["E STONE ST"]}

    assert compute_location_evidence_mismatch(group_rows, filter_meta) is None


def test_no_mismatch_when_one_of_many_aligns():
    group_rows = _group("WORK AREA AT NIEBUHR ST AND BRUCE ST INTERSECTION")
    filter_meta = {"street_hints": ["BRUCE ST"]}

    assert compute_location_evidence_mismatch(group_rows, filter_meta) is None


def test_no_diag_when_notes_have_no_streets():
    group_rows = _group("Depth 5 ft. Crew rotation. No issues.")
    filter_meta = {"street_hints": ["E STONE ST"]}

    assert compute_location_evidence_mismatch(group_rows, filter_meta) is None


def test_no_diag_when_filter_has_no_hints():
    group_rows = _group("WORK ON CHERI LN")
    filter_meta = {"street_hints": []}

    assert compute_location_evidence_mismatch(group_rows, filter_meta) is None


def test_no_diag_when_filter_meta_missing_key():
    group_rows = _group("WORK ON CHERI LN")
    filter_meta = {"applied": False}

    assert compute_location_evidence_mismatch(group_rows, filter_meta) is None


def test_no_diag_for_empty_group():
    assert compute_location_evidence_mismatch([], {"street_hints": ["E STONE ST"]}) is None


def test_helper_does_not_mutate_inputs():
    group_rows = [
        {"notes": "CHERI LN AT STATION 5", "station_ft": 100.0},
        {"notes": "CONTINUING ON CHERI LN", "station_ft": 200.0},
    ]
    filter_meta = {
        "applied": True,
        "street_hints": ["POST OAK CT", "GLENDA BLVD"],
        "allowed_route_ids": ["route_478", "route_475"],
        "sheet_numbers": [24, 25],
    }
    group_rows_snapshot = copy.deepcopy(group_rows)
    filter_meta_snapshot = copy.deepcopy(filter_meta)

    result = compute_location_evidence_mismatch(group_rows, filter_meta)

    assert result is not None
    assert group_rows == group_rows_snapshot
    assert filter_meta == filter_meta_snapshot


def test_extract_dedupes_and_uppercases():
    text = "Cheri Ln, then back to Cheri Ln, then onto Lawndale Ave."

    result = extract_street_references(text)

    assert result == ["CHERI LN", "LAWNDALE AVE"]


def test_extract_returns_empty_for_no_street_suffix():
    assert extract_street_references("HUISACHE") == []
    assert extract_street_references("") == []
    assert extract_street_references(None) == []


def test_filter_streets_normalized_uppercase_and_deduped():
    group_rows = _group("WORK NEAR CHERI LN")
    filter_meta = {"street_hints": ["post oak ct", "Post Oak Ct", "  GLENDA   BLVD  "]}

    result = compute_location_evidence_mismatch(group_rows, filter_meta)

    assert result is not None
    assert result["filter_streets"] == ["POST OAK CT", "GLENDA BLVD"]


def test_diag_shape_is_stable():
    group_rows = _group("BORE ON CHERI LN")
    filter_meta = {"street_hints": ["POST OAK CT"]}

    result = compute_location_evidence_mismatch(group_rows, filter_meta)

    assert set(result.keys()) == {
        "notes_streets",
        "filter_streets",
        "severity",
        "source",
    }
    assert isinstance(result["notes_streets"], list)
    assert isinstance(result["filter_streets"], list)
