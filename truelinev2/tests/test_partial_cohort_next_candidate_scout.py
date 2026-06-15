"""OWNER-PACKET-2 PARTIAL cohort next-candidate scout -- offline tests.

Locks: the result enum; the transparent risk-tiering rules (station-OCR / sibling overlap /
no-modeled-terminus -> HIGH; print-OCR or >=3 sheets -> MEDIUM; else LOW); reset-origin exclusion
from shared-station detection; the real-cohort ranking (PARTIAL = 9, log71 is the sole LOW and the
recommendation, log69/log70 are HIGH for sibling overlap). No PDF parse, no truth table.
"""
from truelinev2.ingest.manual_adjudication import load_adjudication
from truelinev2.proof.run_partial_cohort_next_candidate_scout import (
    ALLOWED,
    EXPECTED_PARTIAL,
    R_SELECTED,
    RISK_HIGH,
    RISK_LOW,
    RISK_MEDIUM,
    _endpoint_stations,
    rank_partial_cohort,
    scout_record,
    sibling_overlap,
)


def _rec(**kw):
    base = {
        "log_id": "synth", "parent": None, "correction_types": [],
        "corrected_start": "1+00", "corrected_end": "2+00", "corrected_sheets": [5, 6],
        "evidence_notes": "ends at STA 2+00 FLOWER POT",
    }
    base.update(kw)
    return base


def _risk(rec):
    return scout_record(rec, {"logs": [rec]})["risk"]


def test_result_enum_exact():
    assert ALLOWED == {"NEXT_CANDIDATE_SELECTED", "NO_SAFE_CANDIDATE"}
    assert R_SELECTED == "NEXT_CANDIDATE_SELECTED"


def test_endpoint_stations_excludes_reset_origin():
    assert _endpoint_stations({"corrected_start": "0+00", "corrected_end": "6+95"}) == {"6+95"}
    assert _endpoint_stations({"corrected_start": "2+15", "corrected_end": "4+54"}) == {"2+15", "4+54"}


# --- risk-tiering rules (synthetic) ---------------------------------------------

def test_clean_two_sheet_modeled_is_low():
    assert _risk(_rec()) == RISK_LOW


def test_station_ocr_is_high():
    assert _risk(_rec(correction_types=["STATION_OCR_CORRECTION"])) == RISK_HIGH


def test_no_modeled_terminus_is_high():
    assert _risk(_rec(evidence_notes="ends at the endpoint structure")) == RISK_HIGH


def test_print_ocr_is_medium():
    assert _risk(_rec(correction_types=["PRINT_OCR_CORRECTION"])) == RISK_MEDIUM


def test_three_sheets_is_medium():
    assert _risk(_rec(corrected_sheets=[5, 6, 7])) == RISK_MEDIUM


# --- real cohort ----------------------------------------------------------------

def test_sibling_overlap_flags_log69_log70():
    doc = load_adjudication()
    rec = {r["log_id"]: r for r in doc["logs"]}
    assert "log70" in sibling_overlap(rec["log69"], doc)
    assert "log69" in sibling_overlap(rec["log70"], doc)
    # a clean single-segment family member has no overlap
    assert sibling_overlap(rec["log64"], doc) == []


def test_partial_cohort_is_the_expected_nine():
    rows = rank_partial_cohort(load_adjudication())
    assert tuple(sorted(r["log_id"] for r in rows)) == EXPECTED_PARTIAL
    assert len(rows) == 9


def test_log71_is_sole_low_and_recommended():
    rows = rank_partial_cohort(load_adjudication())
    low = [r for r in rows if r["risk"] == RISK_LOW]
    assert [r["log_id"] for r in low] == ["log71"]
    assert rows[0]["log_id"] == "log71" and rows[0]["rank"] == 1


def test_log69_log70_are_high_for_overlap():
    rows = {r["log_id"]: r for r in rank_partial_cohort(load_adjudication())}
    for l in ("log69", "log70"):
        assert rows[l]["risk"] == RISK_HIGH
        assert rows[l]["sibling_overlap"]
