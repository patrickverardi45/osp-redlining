"""OWNER-PACKET-2 log64 sheet-21 source bind -- offline tests.

Locks the proof's pure laws: the result/blocker enum, the owner-reset START label derivation,
the callout grammar (tolerant of the extractor joining 'STA1+00'; footage-specific), the direct-
corridor continuity law, and that the slice consumes log64's encoded installer_hh -> flower_pot
identity. No PDF parse here (the proof runs the real sheet-21 bind at verification).
"""
from pathlib import Path

from truelinev2.ingest.manual_adjudication import load_adjudication
from truelinev2.proof.run_log64_sheet21_source_bind_slice import (
    ALLOWED,
    R_CONFIRMED,
    R_PARTIAL,
    _FOOTAGE_RE,
    _SEG_RE,
    corridor_band,
    corridor_is_continuous,
    start_label_text,
)


def test_result_enum_exact():
    assert ALLOWED == {
        "LOG64_SHEET21_SOURCE_BIND_CONFIRMED", "LOG64_PARTIAL_SOURCE_BIND_CONFIRMED",
        "BLOCKED_LOG64_START_LABEL_NOT_FOUND", "BLOCKED_LOG64_START_SYMBOL_NOT_FOUND",
        "BLOCKED_LOG64_END_LABEL_NOT_FOUND", "BLOCKED_LOG64_END_SYMBOL_NOT_FOUND",
        "BLOCKED_LOG64_CALLOUT_NOT_FOUND", "BLOCKED_LOG64_CALLOUT_AMBIGUOUS",
        "BLOCKED_LOG64_CONDUIT_SEED_NOT_FOUND", "BLOCKED_LOG64_ROUTE_NOT_SOURCE_BACKED",
        "BLOCKED_LOG64_SOURCE_BIND_AMBIGUOUS",
    }
    assert {R_CONFIRMED, R_PARTIAL} <= ALLOWED


def test_start_label_is_owner_reset_token():
    # the bindable START label is the owner reset token '<station>=0+00', not a bare station
    assert start_label_text({"station": "3+69"}) == "3+69=0+00"
    assert start_label_text({"station": "45+33"}) == "45+33=0+00"


def test_callout_segment_grammar():
    # the printed 0+00 -> 1+00 segment, with/without the joined 'STA1+00' the extractor emits
    assert _SEG_RE.search("STA 0+00 TO STA1+00")
    assert _SEG_RE.search("STA 0+00 TO STA 1+00")
    assert _SEG_RE.search("0+00 TO 1+00")
    # must NOT match a different segment
    assert not _SEG_RE.search("STA 0+00 TO STA 2+00")
    assert not _SEG_RE.search("STA 1+00 TO STA 2+00")


def test_callout_footage_grammar():
    assert _FOOTAGE_RE.search("DIR. BORE (100') 1-1.25\" VACANT HDPE")
    assert _FOOTAGE_RE.search("DIR BORE (100')")
    # other footages on the sheet must not match
    assert not _FOOTAGE_RE.search("DIR. BORE (287') 1-1.25\" VACANT HDPE")
    assert not _FOOTAGE_RE.search("DIR. BORE (163')")


def test_corridor_continuity_law():
    ylo, yhi = 389.3, 534.1
    # a continuous chain reaching both endpoints with every gap <= MAX_DASH_GAP (35)
    good = [389.3, 413.0, 445.0, 479.0, 511.0, 534.1]
    assert corridor_is_continuous(good, ylo, yhi) is True
    # a gap that exceeds MAX_DASH_GAP breaks continuity
    assert corridor_is_continuous([389.3, 450.0, 534.1], ylo, yhi) is False
    # a band that never reaches the upper endpoint is not source-backed end-to-end
    assert corridor_is_continuous([389.3, 413.0, 445.0], ylo, yhi) is False
    # empty band
    assert corridor_is_continuous([], ylo, yhi) is False


def test_corridor_band_filters_off_corridor_points():
    s_xy, e_xy = (252.0, 389.0), (254.0, 534.0)
    eps = [(253.0, 389.0), (253.0, 420.0), (253.0, 500.0), (300.0, 450.0), (253.0, 534.0)]
    band, ylo, yhi = corridor_band(eps, s_xy, e_xy, half=40.0)
    assert (ylo, yhi) == (389.0, 534.0)
    assert band == [389.0, 420.0, 500.0, 534.0]   # the off-centerline (300,450) is excluded


def test_slice_consumes_log64_encoded_identity():
    doc = load_adjudication()
    l64 = next(r for r in doc["logs"] if r["log_id"] == "log64")
    s = l64["endpoint_anchors"]["start"]
    e = l64["endpoint_anchors"]["end"]
    assert (s["structure_class"], s["station"]) == ("installer_hh", "3+69")
    assert (e["structure_class"], e["station"]) == ("flower_pot", "1+00")


def test_proof_has_no_render_lane():
    src = Path(__file__).resolve().parent.parent / "proof" / "run_log64_sheet21_source_bind_slice.py"
    text = src.read_text(encoding="utf-8")
    assert "from truelinev2.render" not in text
    assert "import truelinev2.render" not in text
    assert "render_redline_stroke" not in text
