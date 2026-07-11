"""Unit tests: ``contracts/station_marks.py`` -- the owner's STATION-DOT CONTRACT (Mission 8 addendum,
``.foreman/scratch/m8/design-dots.md``, BINDING). Pure, no fixture, no engine/render/PDF import. Generic
ids/values only (no customer/person/place names).
"""
from __future__ import annotations

from truelinev2.contracts import station_marks as SM


def _cell(value, verbatim=None, status="READ", confidence="MEDIUM", region=None):
    return {"value": value, "verbatim": verbatim, "status": status, "confidence": confidence, "region": region}


def _reading(station, depth=None, boc=None, *, station_verbatim=None, row_index=0, column_index=0,
            notes=None):
    reading = {
        "station": _cell(station, verbatim=station_verbatim or ("STA %s" % station)),
        "depth_ft": _cell(depth) if depth is not None else {"value": None, "verbatim": None,
                                                            "status": "NOT_PRESENT", "confidence": None,
                                                            "region": None},
        "boc_ft": _cell(boc) if boc is not None else {"value": None, "verbatim": None, "status": "NOT_PRESENT",
                                                      "confidence": None, "region": None},
        "column_index": column_index, "row_index": row_index,
    }
    if notes is not None:                      # fix-wave B3: an optional per-reading notes cell
        reading["notes"] = _cell(notes)
    return reading


def _row(readings=None, **raw_extra):
    raw = dict(raw_extra)
    if readings is not None:
        raw["station_readings"] = readings
    return {"raw": raw, "normalized": {}, "review": {"corrected_values": None}}


# --------------------------------------------------------------------------- #
# len > 2 (STATION_SERIES): exactly the recorded sequence, no fill, per-entry values.
# --------------------------------------------------------------------------- #
def test_series_gt2_irregular_intervals_and_short_final_interval_no_fill():
    readings = [
        _reading("0+00", depth=5.0, boc=8.0, row_index=0),
        _reading("0+62", depth=6.0, boc=9.0, row_index=1),
        _reading("1+20", depth=5.5, boc=8.5, row_index=2),
        _reading("1+45", depth=5.0, boc=8.0, row_index=3),           # final interval 25 ft (< 50)
    ]
    row = _row(readings, start_station="0+00", end_station="1+45", footage_ft=145.0)
    marks, basis, warnings = SM.build_station_marks(
        row, footage=145.0, start_station="0+00", end_station="1+45")
    assert basis == SM.BASIS_STATION_SERIES and warnings == []
    assert [m["footage_along"] for m in marks] == [0.0, 62.0, 120.0, 145.0]
    assert all(m["origin"] == SM.SOURCE_RECORDED for m in marks)          # never derived fill
    assert [m["station"] for m in marks] == ["0+00", "0+62", "1+20", "1+45"]
    assert [m["depth"] for m in marks] == ["5.0", "6.0", "5.5", "5.0"]    # varying per-entry depth preserved
    assert [m["boc"] for m in marks] == ["8.0", "9.0", "8.5", "8.0"]
    assert all(m["station_evidence"] is not None for m in marks)
    assert marks[0]["station_evidence"]["verbatim"] == "STA 0+00"


def test_series_gt2_uses_exact_final_interval_not_the_default_50():
    """A 4th interval well under 50 ft is never rounded up/fabricated to a 50-ft tick."""
    readings = [_reading("10+00"), _reading("10+50"), _reading("11+00"), _reading("11+22")]
    row = _row(readings, start_station="10+00", end_station="11+22", footage_ft=122.0)
    marks, basis, _w = SM.build_station_marks(row, footage=122.0, start_station="10+00", end_station="11+22")
    assert basis == SM.BASIS_STATION_SERIES
    assert [m["footage_along"] for m in marks] == [0.0, 50.0, 100.0, 122.0]


# --------------------------------------------------------------------------- #
# len == 2 (SERIES_ENDPOINTS_WITH_DERIVED_FILL, the WP23 class): endpoints recorded + tagged fill.
# --------------------------------------------------------------------------- #
def test_series_eq2_endpoints_recorded_plus_derived_fill_wp23_shape():
    readings = [
        _reading("3+50", depth=5.0, boc=8.0, station_verbatim="STA 3+50", row_index=0),
        _reading("4+08", depth=5.0, boc=8.0, station_verbatim="STA  4+08", row_index=1),
    ]
    row = _row(readings, start_station="3+50", end_station="4+08", footage_ft=58.0)
    marks, basis, warnings = SM.build_station_marks(
        row, footage=58.0, start_station="3+50", end_station="4+08")
    assert basis == SM.BASIS_SERIES_ENDPOINTS_WITH_DERIVED_FILL and warnings == []
    assert [m["footage_along"] for m in marks] == [0.0, 50.0, 58.0]
    assert [m["station"] for m in marks] == ["3+50", "4+00", "4+08"]
    assert [m["origin"] for m in marks] == [SM.SOURCE_RECORDED, SM.DERIVED_INTERVAL, SM.SOURCE_RECORDED]
    # values ONLY on the recorded endpoints -- the derived interior fill never invents depth/BOC.
    assert marks[0]["depth"] == "5.0" and marks[0]["boc"] == "8.0"
    assert marks[2]["depth"] == "5.0" and marks[2]["boc"] == "8.0"
    assert marks[1]["depth"] is None and marks[1]["boc"] is None and marks[1]["notes"] is None
    assert marks[1]["station_evidence"] is None
    assert marks[0]["station_evidence"]["verbatim"] == "STA 3+50"
    assert marks[2]["station_evidence"]["verbatim"] == "STA  4+08"


# --------------------------------------------------------------------------- #
# No series at all (SPAN_ENDPOINTS, generic TABLE_IMPORT rows): recorded span endpoints + tagged fill,
# NO per-station depth/BOC anywhere (the row's bore-level values are not station readings).
# --------------------------------------------------------------------------- #
def test_no_series_span_endpoints_plus_fill_no_depth_boc_anywhere():
    row = _row(None, start_station="11+75", end_station="13+25", footage_ft=150.0,
              depth_ft=42.0, boc_ft=48.0)             # bore-level depth/BOC present, but NOT per-station
    marks, basis, warnings = SM.build_station_marks(
        row, footage=150.0, start_station="11+75", end_station="13+25")
    assert basis == SM.BASIS_SPAN_ENDPOINTS and warnings == []
    assert [m["footage_along"] for m in marks] == [0.0, 50.0, 100.0, 150.0]
    assert [m["station"] for m in marks] == ["11+75", "12+25", "12+75", "13+25"]
    assert [m["origin"] for m in marks] == [
        SM.SOURCE_RECORDED, SM.DERIVED_INTERVAL, SM.DERIVED_INTERVAL, SM.SOURCE_RECORDED]
    assert all(m["depth"] is None and m["boc"] is None and m["notes"] is None for m in marks)
    assert all(m["station_evidence"] is None for m in marks)


def test_no_series_absent_row_effective_fails_closed_to_none_when_footage_invalid():
    marks, basis, warnings = SM.build_station_marks(
        None, footage=0.0, start_station="0+00", end_station="1+00")
    assert marks is None and basis == SM.BASIS_SPAN_ENDPOINTS and warnings == []
    marks2, _b, _w = SM.build_station_marks({}, footage=None, start_station=None, end_station=None)
    assert marks2 is None


# --------------------------------------------------------------------------- #
# The named series-unusable warning codes -- each falls through to SPAN_ENDPOINTS, never guesses.
# --------------------------------------------------------------------------- #
def test_series_unparseable_falls_through_with_named_warning():
    readings = [_reading("3+50"), _reading("not-a-station")]
    row = _row(readings, start_station="3+50", end_station="4+08", footage_ft=58.0)
    marks, basis, warnings = SM.build_station_marks(
        row, footage=58.0, start_station="3+50", end_station="4+08")
    assert basis == SM.BASIS_SPAN_ENDPOINTS and warnings == [SM.WARN_UNPARSEABLE]
    assert marks is not None and marks[0]["origin"] == SM.SOURCE_RECORDED


def test_series_not_ascending_falls_through_with_named_warning():
    readings = [_reading("4+08"), _reading("3+50")]         # descending
    row = _row(readings, start_station="3+50", end_station="4+08", footage_ft=58.0)
    marks, basis, warnings = SM.build_station_marks(
        row, footage=58.0, start_station="3+50", end_station="4+08")
    assert basis == SM.BASIS_SPAN_ENDPOINTS and warnings == [SM.WARN_NOT_ASCENDING]
    assert marks is not None


def test_series_endpoint_mismatch_falls_through_with_named_warning():
    readings = [_reading("3+60"), _reading("4+08")]         # first reading != effective start_station
    row = _row(readings, start_station="3+50", end_station="4+08", footage_ft=58.0)
    marks, basis, warnings = SM.build_station_marks(
        row, footage=58.0, start_station="3+50", end_station="4+08")
    assert basis == SM.BASIS_SPAN_ENDPOINTS and warnings == [SM.WARN_ENDPOINT_MISMATCH]
    assert marks is not None


def test_series_row_endpoints_unparseable_is_distinct_from_endpoint_mismatch_f2():
    """Fix-wave F2 (blind-verify note 2): when the ROW's own effective start/end station text is garbled
    (unparseable), no comparison against the recorded readings was ever actually made -- this must NOT be
    reported as STATION_SERIES_ENDPOINT_MISMATCH (which asserts a proven inequality); it gets its own,
    narrower, named code."""
    readings = [_reading("3+50"), _reading("4+08")]           # perfectly usable, parseable readings
    row = _row(readings, start_station="garbled", end_station="4+08", footage_ft=58.0)
    marks, basis, warnings = SM.build_station_marks(
        row, footage=58.0, start_station="garbled", end_station="4+08")
    assert basis == SM.BASIS_SPAN_ENDPOINTS and warnings == [SM.WARN_ROW_ENDPOINTS_UNPARSEABLE]
    assert warnings != [SM.WARN_ENDPOINT_MISMATCH]
    assert marks is not None


def test_series_footage_mismatch_falls_through_with_named_warning():
    readings = [_reading("3+50"), _reading("4+08")]          # 58 ft apart
    row = _row(readings, start_station="3+50", end_station="4+08", footage_ft=100.0)   # disagrees
    marks, basis, warnings = SM.build_station_marks(
        row, footage=100.0, start_station="3+50", end_station="4+08")
    assert basis == SM.BASIS_SPAN_ENDPOINTS and warnings == [SM.WARN_FOOTAGE_MISMATCH]
    assert marks is not None
    assert [m["footage_along"] for m in marks] == [0.0, 50.0, 100.0]     # the APPROVED span remains truth


def test_unusable_series_never_mixes_recorded_and_generic_fill():
    """Owner clause 5/6: an unusable len>2 series ALSO falls through cleanly (no partial/hybrid dot set)."""
    readings = [_reading("3+50"), _reading("3+80"), _reading("not-a-station")]
    row = _row(readings, start_station="3+50", end_station="4+08", footage_ft=58.0)
    marks, basis, warnings = SM.build_station_marks(
        row, footage=58.0, start_station="3+50", end_station="4+08")
    assert basis == SM.BASIS_SPAN_ENDPOINTS and warnings == [SM.WARN_UNPARSEABLE]
    assert [m["station"] for m in marks] == ["3+50", "4+00", "4+08"]


# --------------------------------------------------------------------------- #
# Corrected_values precedence (raw < normalized < corrected) reaches station_readings/effective values
# the SAME way render.station_dots.resolve_bore_fields does.
# --------------------------------------------------------------------------- #
def test_station_readings_reached_through_corrected_values_precedence():
    row = {"raw": {"footage_ft": 100.0}, "normalized": {},
          "review": {"corrected_values": {"station_readings": [
              _reading("0+00", depth=1.0, boc=2.0), _reading("1+00", depth=1.0, boc=2.0)]}}}
    marks, basis, warnings = SM.build_station_marks(row, footage=100.0, start_station="0+00",
                                                    end_station="1+00")
    assert basis == SM.BASIS_SERIES_ENDPOINTS_WITH_DERIVED_FILL and warnings == []
    assert [m["footage_along"] for m in marks] == [0.0, 50.0, 100.0]


def test_len_1_series_is_treated_as_no_series():
    row = _row([_reading("3+50")], start_station="3+50", end_station="4+08", footage_ft=58.0)
    marks, basis, warnings = SM.build_station_marks(
        row, footage=58.0, start_station="3+50", end_station="4+08")
    assert basis == SM.BASIS_SPAN_ENDPOINTS and warnings == []           # not a "rejected series", just none


# --------------------------------------------------------------------------- #
# Fix-wave B1 (Sol xhigh verification): station_readings is UNTRUSTED reviewed-row data -- a malformed
# entry must fall back honestly (SPAN_ENDPOINTS + a named warning), never raise.
# --------------------------------------------------------------------------- #
def test_all_null_station_readings_falls_back_without_raising_b1():
    row = _row([None, None], start_station="3+50", end_station="4+08", footage_ft=58.0)
    marks, basis, warnings = SM.build_station_marks(
        row, footage=58.0, start_station="3+50", end_station="4+08")
    assert basis == SM.BASIS_SPAN_ENDPOINTS and warnings == [SM.WARN_UNPARSEABLE]
    assert marks is not None and [m["footage_along"] for m in marks] == [0.0, 50.0, 58.0]


def test_mixed_valid_and_malformed_station_readings_falls_back_without_raising_b1():
    readings = [_reading("3+50"), "garbage", 5]
    row = _row(readings, start_station="3+50", end_station="4+08", footage_ft=58.0)
    marks, basis, warnings = SM.build_station_marks(
        row, footage=58.0, start_station="3+50", end_station="4+08")
    assert basis == SM.BASIS_SPAN_ENDPOINTS and warnings == [SM.WARN_UNPARSEABLE]
    assert marks is not None


def test_non_list_station_readings_value_falls_back_without_raising_b1():
    """A ``station_readings`` value that is present but not a list at all (e.g. a stray string/dict) is
    treated as "this row never had a series" -- the ordinary, unremarkable SPAN_ENDPOINTS case (no
    warning; it never reached series validation at all) -- and, crucially, never raises."""
    row = _row(None, start_station="3+50", end_station="4+08", footage_ft=58.0,
              station_readings="not-a-list")
    marks, basis, warnings = SM.build_station_marks(
        row, footage=58.0, start_station="3+50", end_station="4+08")
    assert basis == SM.BASIS_SPAN_ENDPOINTS and warnings == []
    assert marks is not None


# --------------------------------------------------------------------------- #
# Fix-wave B3 (Sol xhigh verification): a recorded reading's OWN "notes" cell is attached to its mark
# when present (the SAME cell-value pattern as depth_ft/boc_ft) -- never a row-level notes value, and
# never on a derived-fill mark.
# --------------------------------------------------------------------------- #
def test_series_gt2_carries_per_entry_notes_only_where_present_b3():
    readings = [
        _reading("0+00", depth=5.0, boc=8.0, row_index=0, notes="soft soil"),
        _reading("0+62", depth=6.0, boc=9.0, row_index=1),                       # no note on THIS entry
        _reading("1+20", depth=5.5, boc=8.5, row_index=2, notes="rock"),
    ]
    row = _row(readings, start_station="0+00", end_station="1+20", footage_ft=120.0, notes="ROW-LEVEL NOTE")
    marks, basis, warnings = SM.build_station_marks(
        row, footage=120.0, start_station="0+00", end_station="1+20")
    assert basis == SM.BASIS_STATION_SERIES and warnings == []
    assert marks[0]["notes"] == "soft soil"
    assert marks[1]["notes"] is None            # honestly absent -- never the row-level value leaking in
    assert marks[2]["notes"] == "rock"


def test_series_eq2_endpoint_notes_present_only_on_the_entry_that_carries_one_b3():
    readings = [
        _reading("3+50", depth=5.0, boc=8.0, row_index=0, notes="start note"),
        _reading("4+08", depth=5.0, boc=8.0, row_index=1),                       # no note
    ]
    row = _row(readings, start_station="3+50", end_station="4+08", footage_ft=58.0, notes="ROW-LEVEL NOTE")
    marks, basis, warnings = SM.build_station_marks(
        row, footage=58.0, start_station="3+50", end_station="4+08")
    assert basis == SM.BASIS_SERIES_ENDPOINTS_WITH_DERIVED_FILL and warnings == []
    assert marks[0]["notes"] == "start note"
    assert marks[2]["notes"] is None                     # the end entry carries no note of its own
    # the derived interior fill NEVER carries notes, even though both endpoint entries have a notes cell.
    assert marks[1]["origin"] == SM.DERIVED_INTERVAL and marks[1]["notes"] is None
