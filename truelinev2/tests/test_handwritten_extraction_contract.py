"""Contract tests: Phase-1 handwritten bore-log page extraction + ladder->span normalization + RBL
fan-out planning. Pure stdlib; no engine/render/AI/OCR/store wiring. Generic ids/values only -- no
customer/person/project/location strings.
"""
from __future__ import annotations

import json

import pytest

from truelinev2.contracts.handwritten_extraction import (
    DERIVED_FROM_STATIONS,
    EXTRACTED,
    InvalidCellError,
    InvalidPageExtractionError,
    LOW,
    MEDIUM,
    NOT_PRESENT,
    PAGE_RECORD_FORMAT,
    READ,
    REFUSED,
    SPAN_RECORD_FORMAT,
    TEXT_LAYER,
    UNREADABLE,
    VISION_OCR,
    rbl_fanout_plan,
    spans_from_page,
    validate_page_extraction,
)

SRC = {"upload_id": "up-1", "sha256": "a" * 64, "file_name": "page.jpg", "page_index": 0, "page_count": 1}


def _cell(value=None, status=READ, verbatim=None, confidence=None, region=None):
    return {"value": value, "verbatim": verbatim, "status": status, "confidence": confidence, "region": region}


def _blank_cell():
    return _cell(value=None, status=NOT_PRESENT)


def _reading(station, depth=None, boc=None, *, column_index=0, row_index=0,
            station_confidence=None):
    return {
        "station": _cell(station, confidence=station_confidence) if station is not None else _blank_cell(),
        "depth_ft": _cell(depth) if depth is not None else _blank_cell(),
        "boc_ft": _cell(boc) if boc is not None else _blank_cell(),
        "column_index": column_index,
        "row_index": row_index,
    }


def _page(readings, *, header=None, method=VISION_OCR, page_status=EXTRACTED, refusal=None,
         warnings=None, source=None):
    return {
        "record_format": PAGE_RECORD_FORMAT,
        "source": dict(source or SRC),
        "method": method,
        "extractor": "extractor-x",
        "header": header or {
            "date": _blank_cell(), "crew": _blank_cell(),
            "job_name": _blank_cell(), "print_raw": _blank_cell(),
        },
        "readings": readings,
        "page_status": page_status,
        "refusal": refusal,
        "warnings": list(warnings or []),
        "audit": [],
    }


# --------------------------------------------------------------------------- #
# validate_page_extraction -- schema + honesty invariants.
# --------------------------------------------------------------------------- #
def test_valid_page_round_trips_through_json():
    page = _page([_reading("48+52", row_index=0), _reading("49+00", row_index=1)])
    validated = validate_page_extraction(page)
    assert validated is page
    reloaded = json.loads(json.dumps(page))
    assert validate_page_extraction(reloaded)["record_format"] == PAGE_RECORD_FORMAT


def test_wrong_record_format_rejected():
    page = _page([])
    page["record_format"] = "something-else"
    with pytest.raises(InvalidPageExtractionError):
        validate_page_extraction(page)


def test_unreadable_cell_with_value_rejected():
    page = _page([_reading("48+52", row_index=0), _reading("49+00", row_index=1)])
    page["header"]["date"] = _cell("2026-01-01", status=UNREADABLE)   # value present but NOT READ
    with pytest.raises(InvalidCellError):
        validate_page_extraction(page)


def test_not_present_cell_with_value_rejected():
    page = _page([_reading("48+52", row_index=0)])
    page["readings"][0]["depth_ft"] = _cell(5.0, status=NOT_PRESENT)
    with pytest.raises(InvalidCellError):
        validate_page_extraction(page)


def test_read_cell_without_value_is_valid():
    # READ status does not itself require a non-None value (verbatim-only illegible-but-attempted reads
    # are not modeled here) -- only the reverse (value implies READ) is enforced.
    page = _page([_reading("48+52", row_index=0)])
    page["header"]["crew"] = _cell(None, status=READ, verbatim="scribble")
    assert validate_page_extraction(page)


def test_refused_page_requires_refusal_code_and_reason():
    page = _page([], page_status=REFUSED, refusal=None)
    with pytest.raises(InvalidPageExtractionError):
        validate_page_extraction(page)
    page["refusal"] = {"code": "PAGE_UNREADABLE", "reason": "no legible content"}
    assert validate_page_extraction(page)


def test_extracted_page_must_not_carry_a_refusal():
    page = _page([], page_status=EXTRACTED, refusal={"code": "X", "reason": "y"})
    with pytest.raises(InvalidPageExtractionError):
        validate_page_extraction(page)


def test_region_out_of_bounds_rejected():
    page = _page([_reading("48+52", row_index=0)])
    page["readings"][0]["station"]["region"] = [0.0, 0.0, 1.5, 1.0]
    with pytest.raises(InvalidCellError):
        validate_page_extraction(page)


def test_old_shape_record_still_loads_when_extra_key_absent():
    # Old-shape compatibility check mirrors the extracted_row additive-evolution guarantee: a page dict
    # built with exactly the pinned key set (no future additive keys) validates cleanly.
    page = _page([_reading("48+52", row_index=0), _reading("49+00", row_index=1)])
    assert set(page.keys()) == {
        "record_format", "source", "method", "extractor", "header", "readings",
        "page_status", "refusal", "warnings", "audit"}
    assert validate_page_extraction(page)


# --------------------------------------------------------------------------- #
# spans_from_page -- ladder -> span normalizer.
# --------------------------------------------------------------------------- #
def _header_with_print(print_value, *, print_status=READ):
    return {
        "date": _cell("2026-06-01"), "crew": _cell("Crew A"),
        "job_name": _cell("J. Smith"),
        "print_raw": _cell(print_value, status=print_status) if print_value is not None else _blank_cell(),
    }


def test_ascending_run_becomes_one_span_proposal():
    readings = [
        _reading("48+52", depth=5.0, boc=2.0, row_index=0),
        _reading("49+00", depth=5.0, boc=2.0, row_index=1),
        _reading("50+00", depth=5.0, boc=2.0, row_index=2),
    ]
    page = _page(readings, header=_header_with_print("29,30,31"))
    spans = spans_from_page(page)
    assert len(spans) == 1
    span = spans[0]
    assert span["record_format"] == SPAN_RECORD_FORMAT
    assert span["start_station"] == "48+52" and span["end_station"] == "50+00"
    assert span["footage_ft"] == pytest.approx(148.0)      # 50+00 - 48+52 = 5000-4852 = 148
    assert span["footage_derivation"] == DERIVED_FROM_STATIONS
    assert span["depth_ft"] == 5.0 and span["boc_ft"] == 2.0
    assert span["sheet_refs"] == [29, 30, 31]
    assert span["print_raw"] == "29,30,31"
    assert span["notes"] == "Job name: J. Smith"
    assert span["date"] == "2026-06-01" and span["crew"] == "Crew A"
    assert span["bore_id"] is None


def test_reset_token_splits_into_two_runs():
    readings = [
        _reading("48+52", row_index=0), _reading("49+00", row_index=1),
        _reading("0+00", row_index=2),                       # reset -> new bore, new run
        _reading("0+50", row_index=3), _reading("1+00", row_index=4),
    ]
    page = _page(readings, header=_header_with_print("12"))
    spans = spans_from_page(page)
    assert len(spans) == 2
    assert (spans[0]["start_station"], spans[0]["end_station"]) == ("48+52", "49+00")
    assert (spans[1]["start_station"], spans[1]["end_station"]) == ("0+00", "1+00")


def test_single_reading_run_produces_no_proposal_and_warns_sibling_proposal():
    # One page, two runs: a lone stray reading (run of 1) plus a real 2-station run. The higher-then-lower
    # step (60+00 -> 48+52) is itself a run boundary, so 60+00 forms its own 1-reading run. The stray
    # produces NO proposal, but its skip is named in the warning carried by the run that DOES produce one.
    readings = [
        _reading("60+00", row_index=0),                       # lone stray -- becomes a run of 1
        _reading("48+52", row_index=1), _reading("49+00", row_index=2),
    ]
    page = _page(readings, header=_header_with_print("12"))
    spans = spans_from_page(page)
    assert len(spans) == 1
    assert any("fewer than 2 usable station readings" in w for w in spans[0]["warnings"])
    assert "row 0" in spans[0]["warnings"][-1] or "row 0" in " ".join(spans[0]["warnings"])


def test_entire_page_single_reading_yields_zero_proposals():
    page = _page([_reading("10+00", row_index=0)], header=_header_with_print("12"))
    assert spans_from_page(page) == []


def test_varying_depth_across_run_becomes_null_with_series_preserved():
    readings = [
        _reading("48+52", depth=5.0, row_index=0),
        _reading("49+00", depth=6.0, row_index=1),          # disagrees -> depth_ft None
    ]
    page = _page(readings, header=_header_with_print("12"))
    span = spans_from_page(page)[0]
    assert span["depth_ft"] is None
    assert [r["depth_ft"]["value"] for r in span["station_readings"]] == [5.0, 6.0]
    assert span["cell_evidence"]["depth_ft"]["status"] == "VARIED"


def test_unreadable_depth_cell_forces_null_even_if_others_agree():
    readings = [
        _reading("48+52", depth=5.0, row_index=0),
        {**_reading("49+00", row_index=1), "depth_ft": _cell(None, status=UNREADABLE)},
        _reading("50+00", depth=5.0, row_index=2),
    ]
    page = _page(readings, header=_header_with_print("12"))
    span = spans_from_page(page)[0]
    assert span["depth_ft"] is None
    assert span["cell_evidence"]["depth_ft"]["status"] == UNREADABLE


def test_constant_boc_across_run_resolves_to_value():
    readings = [
        _reading("48+52", boc=2.0, row_index=0),
        _reading("49+00", boc=2.0, row_index=1),
        _reading("50+00", boc=None, row_index=2),            # NOT_PRESENT -- ignored, not a disagreement
    ]
    page = _page(readings, header=_header_with_print("12"))
    span = spans_from_page(page)[0]
    assert span["boc_ft"] == 2.0
    assert span["cell_evidence"]["boc_ft"]["status"] == READ


@pytest.mark.parametrize("raw,expected_feet", [
    ("48+52", 4852.0),
    ("STA 3+50", 350.0),
    ("STA. 3+50", 350.0),
])
def test_station_parse_variants(raw, expected_feet):
    readings = [_reading(raw, row_index=0), _reading("99+99", row_index=1)]
    page = _page(readings, header=_header_with_print("12"))
    span = spans_from_page(page)[0]
    assert span["start_station"] == raw
    assert span["footage_ft"] == pytest.approx(9999.0 - expected_feet)


@pytest.mark.parametrize("print_value,expected_refs", [
    ("29,30,31", [29, 30, 31]),
    ("WP 23", [23]),
    ("12", [12]),
])
def test_print_raw_sheet_ref_parsing(print_value, expected_refs):
    readings = [_reading("1+00", row_index=0), _reading("2+00", row_index=1)]
    page = _page(readings, header=_header_with_print(print_value))
    span = spans_from_page(page)[0]
    assert span["sheet_refs"] == expected_refs
    assert span["print_raw"] == print_value


def test_unparseable_station_excluded_from_runs():
    readings = [
        _reading("not-a-station", row_index=0),
        _reading("48+52", row_index=1), _reading("49+00", row_index=2),
    ]
    page = _page(readings, header=_header_with_print("12"))
    spans = spans_from_page(page)
    assert len(spans) == 1
    assert spans[0]["start_station"] == "48+52"


def test_confidence_medium_requires_both_endpoints_medium_and_print_read():
    readings = [
        _reading("48+52", row_index=0, station_confidence=MEDIUM),
        _reading("49+00", row_index=1, station_confidence=MEDIUM),
    ]
    page = _page(readings, header=_header_with_print("12"))
    assert spans_from_page(page)[0]["confidence"] == MEDIUM

    readings_low = [
        _reading("48+52", row_index=0, station_confidence=MEDIUM),
        _reading("49+00", row_index=1, station_confidence=LOW),
    ]
    page_low = _page(readings_low, header=_header_with_print("12"))
    assert spans_from_page(page_low)[0]["confidence"] == LOW


def test_confidence_never_high_even_with_no_print():
    readings = [
        _reading("48+52", row_index=0, station_confidence=MEDIUM),
        _reading("49+00", row_index=1, station_confidence=MEDIUM),
    ]
    page = _page(readings, header=_header_with_print(None))       # print_raw NOT_PRESENT -> not READ
    span = spans_from_page(page)[0]
    assert span["confidence"] == LOW


def test_refused_page_yields_no_spans():
    page = _page([_reading("48+52", row_index=0), _reading("49+00", row_index=1)],
                page_status=REFUSED, refusal={"code": "PAGE_UNREADABLE", "reason": "blank scan"})
    assert spans_from_page(page) == []


def test_job_name_only_becomes_notes_when_read():
    readings = [_reading("1+00", row_index=0), _reading("2+00", row_index=1)]
    header = _header_with_print("12")
    header["job_name"] = _blank_cell()
    page = _page(readings, header=header)
    assert spans_from_page(page)[0]["notes"] is None


def test_cell_evidence_present_for_start_and_end_station():
    readings = [
        _reading("48+52", row_index=0, station_confidence=MEDIUM),
        _reading("49+00", row_index=1, station_confidence=MEDIUM),
    ]
    page = _page(readings, header=_header_with_print("12"), source={**SRC, "page_index": 3, "page_count": 5})
    span = spans_from_page(page)[0]
    ev = span["cell_evidence"]
    assert ev["start_station"]["status"] == READ and ev["start_station"]["page_index"] == 3
    assert ev["end_station"]["status"] == READ and ev["end_station"]["page_index"] == 3


# --------------------------------------------------------------------------- #
# rbl_fanout_plan -- pure planning, no store I/O.
# --------------------------------------------------------------------------- #
def test_fanout_one_plan_per_proposal_with_stable_ids():
    readings = [
        _reading("48+52", row_index=0), _reading("49+00", row_index=1),
        _reading("0+00", row_index=2), _reading("1+00", row_index=3),
        _reading("2+00", row_index=4),
    ]
    page = _page(readings, header=_header_with_print("12"))
    spans = spans_from_page(page)
    assert len(spans) == 2
    plan = rbl_fanout_plan(spans)
    assert len(plan) == 2
    assert [p["reviewed_bore_log_id"] for p in plan] == ["rbl-hw-p0-r1", "rbl-hw-p0-r2"]
    assert all(p["source_upload_id"] == "up-1" for p in plan)
    assert plan[0]["proposal"] is spans[0] and plan[1]["proposal"] is spans[1]
    # Re-running is deterministic (pure planning, no store writes / hidden state).
    assert rbl_fanout_plan(spans) == plan


def test_fanout_ids_scoped_per_page():
    page_a = _page([_reading("1+00", row_index=0), _reading("2+00", row_index=1)],
                   header=_header_with_print("12"), source={**SRC, "page_index": 0, "page_count": 2})
    page_b = _page([_reading("3+00", row_index=0), _reading("4+00", row_index=1)],
                   header=_header_with_print("12"), source={**SRC, "page_index": 1, "page_count": 2})
    proposals = spans_from_page(page_a) + spans_from_page(page_b)
    plan = rbl_fanout_plan(proposals)
    assert [p["reviewed_bore_log_id"] for p in plan] == ["rbl-hw-p0-r1", "rbl-hw-p1-r1"]


def test_fanout_empty_input_yields_empty_plan():
    assert rbl_fanout_plan([]) == []
