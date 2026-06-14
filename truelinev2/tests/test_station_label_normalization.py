"""PARENT-CHILD-RECON-2 Part A: the 'STA ' station-label ingest normalization.

Proves the narrow seam: a leading 'STA'/'STA.'/'STA:' label is stripped before
parsing (so PDF digital-fill stations like 'STA 3+50' parse), while bare stations
and non-station text are untouched, and the shared ``parse_station`` is unchanged.
Pure + offline (the reader regression builds an in-memory .xlsx, no corpus)."""
import openpyxl
import pytest

from truelinev2.ingest.borelog_brenham import read_brenham_borelog
from truelinev2.stations import parse_station, strip_station_label


# --- helper: strips ONLY the label, in the listed forms ------------------------
@pytest.mark.parametrize("raw,expected", [
    ("STA 3+50", "3+50"),
    ("STA. 3+50", "3+50"),
    ("STA: 3+50", "3+50"),
    ("STA   3+50", "3+50"),       # extra whitespace
    ("  STA 3+50", "3+50"),       # leading whitespace
    ("sta 3+50", "3+50"),         # case-insensitive
    ("STA 16+21", "16+21"),
])
def test_strip_label_positive(raw, expected):
    assert strip_station_label(raw) == expected


@pytest.mark.parametrize("raw", [
    "3+50", "12+22", "0+00",                 # bare stations unchanged
    "nope", "", "STATION 3+50",              # non-station / not the exact label
    "STA nonsense", "ROW STA 3+50",          # label not at the start / no digit
])
def test_strip_label_leaves_unchanged(raw):
    assert strip_station_label(raw) == raw


def test_strip_label_none():
    assert strip_station_label(None) == ""


# --- pipeline: strip-then-parse ------------------------------------------------
@pytest.mark.parametrize("raw,ft", [
    ("STA 3+50", 350.0), ("STA. 4+08", 408.0), ("STA: 0+62", 62.0),
    ("STA 16+21", 1621.0), ("3+50", 350.0), ("12+22", 1222.0),
])
def test_parse_after_strip(raw, ft):
    assert parse_station(strip_station_label(raw)) == ft


@pytest.mark.parametrize("raw", ["nope", "STATION 3+50", "STA nonsense", ""])
def test_parse_after_strip_rejects_nonstation(raw):
    assert parse_station(strip_station_label(raw)) is None


# --- shared parser is UNCHANGED (fix is reader-confined, zero blast radius) -----
def test_parse_station_itself_unchanged():
    assert parse_station("STA 3+50") is None      # still None: parse_station not touched
    assert parse_station("3+50") == 350.0
    assert parse_station("nope") is None


# --- reader regression (offline in-memory .xlsx, no corpus) ---------------------
def _make_xlsx(tmp_path, name, station_cells):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["station", "depth", "boc", "date", "crew", "print", "notes"])
    for s in station_cells:
        ws.append([s, 4.0, 8, "2026-02-11", "TX28-1", "WP 23", ""])
    p = tmp_path / name
    wb.save(p)
    return str(p)


def test_reader_default_on_parses_explicit_off_raises(tmp_path):
    """DEFAULT (ON since RECON-2A activation): a 'STA '-prefixed sheet now PARSES.
    Passing normalize_station_label=False recovers the pre-activation raise (the
    proofs that demonstrate the OFF baseline do exactly this)."""
    path = _make_xlsx(tmp_path, "bore_log37.xlsx", ["STA 3+50", "STA 4+08"])
    bore = read_brenham_borelog(path)                    # default now ON
    assert bore.station_start_ft == 350.0 and bore.station_end_ft == 408.0
    with pytest.raises(ValueError):
        read_brenham_borelog(path, normalize_station_label=False)


def test_reader_optin_parses_sta_prefixed_log37_shape(tmp_path):
    """Explicit ON: log37 shape parses ('STA 3+50'/'STA 4+08' -> 3+50..4+08)."""
    path = _make_xlsx(tmp_path, "bore_log37.xlsx", ["STA 3+50", "STA 4+08"])
    bore = read_brenham_borelog(path, normalize_station_label=True)
    assert bore.station_start_ft == 350.0
    assert bore.station_end_ft == 408.0
    assert bore.span_ft == 58.0
    assert bore.sheet_refs == [23]


def test_reader_bare_stations_identical_off_and_on(tmp_path):
    """Control: a normal bare-station bore reads IDENTICALLY with the flag OFF and ON
    (the opt-in only ever affects 'STA '-prefixed cells)."""
    path = _make_xlsx(tmp_path, "bore_log99.xlsx", ["0+00", "5+34"])
    off = read_brenham_borelog(path)
    on = read_brenham_borelog(path, normalize_station_label=True)
    for b in (off, on):
        assert b.station_start_ft == 0.0 and b.station_end_ft == 534.0 and b.span_ft == 534.0


def test_reader_optin_still_raises_on_truly_unparseable(tmp_path):
    """Even opted-in, non-station junk is still rejected (no fuzzy correction)."""
    path = _make_xlsx(tmp_path, "bore_logX.xlsx", ["nope", "STATION 3+50"])
    with pytest.raises(ValueError):
        read_brenham_borelog(path, normalize_station_label=True)
