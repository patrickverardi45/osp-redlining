"""M5 harness unit tests — enumeration + classification + report-row schema.

Pure/offline: no real corpus or PDF needed (the sweep itself runs only in the proof).
Lives in tests/ (excluded from the no-convention/no-global guards), so naming the
adapter here is fine; it asserts the harness keeps the adapter/core boundary honest.
"""
from __future__ import annotations

from truelinev2.proof.run_brenham_corpus import (
    EXCLUDE_SUBDIR,
    REQUIRED_ROW_KEYS,
    build_row,
    classify,
    enumerate_corpus,
)
from truelinev2.schema.models import Bore, Placement, PlacementStatus


def _touch(p):
    p.write_bytes(b"")  # enumerate matches by name + is_file; never opens these


def test_enumerate_excludes_do_not_import_and_sorts_numerically(tmp_path):
    for n in (2, 10, 1):
        _touch(tmp_path / f"bore_log{n}.xlsx")
    sub = tmp_path / EXCLUDE_SUBDIR
    sub.mkdir()
    _touch(sub / "bore_log3.xlsx")        # archived original — MUST be excluded
    _touch(tmp_path / "notes.xlsx")       # non-matching name — ignored
    got = [p.name for p in enumerate_corpus(tmp_path)]
    assert got == ["bore_log1.xlsx", "bore_log2.xlsx", "bore_log10.xlsx"]


def test_classify_maps_engine_stage_not_fault():
    assert classify("AUTO_SELECT", "anything") == "none_placed"
    assert classify("REVIEW", "anything") == "none_placed"
    assert classify("ERROR", None) == "adapter_parser_gap"
    assert classify("ABSTAIN", "NO_CALLOUTS_EXTRACTED") == "adapter_parser_gap"
    assert classify("ABSTAIN", "NO_AUTHORED_BOX_MATCH_FOR_BORE_SPAN") == "generic_match_scoring_gap"
    assert classify("ABSTAIN", "GE_2_COEQUAL_CANDIDATES_NO_TIEBREAKER") == "generic_match_scoring_gap"


def test_build_row_has_required_keys_and_provisional_class():
    bore = Bore(bore_id="bore_log99", source_file="bore_log99.xlsx", sheet_refs=[8],
                station_start="0+00", station_end="2+99", station_start_ft=0.0,
                station_end_ft=299.0, span_ft=299.0)
    pl = Placement(bore_id="bore_log99", status=PlacementStatus.ABSTAIN, tier="FAIL_SAFE",
                   reason="NO_CALLOUTS_EXTRACTED")
    row = build_row(bore, pl, "bore_log99.xlsx", "ABSTAIN", None, None, None, None, None)
    assert set(REQUIRED_ROW_KEYS).issubset(row.keys())
    assert row["miss_class_provisional"] == "adapter_parser_gap"
    assert row["miss_class"] == "pending_grade"        # final class is grading-only
    assert row["agreement"] == "old_unknown"
