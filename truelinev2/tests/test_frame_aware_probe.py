"""Tests for the M8.2a frame-equation probe's PURE parser helpers (no PDF).

Proves the matchline/station-equation grammar is parsed deterministically and that
non-equations (callouts, footages, fractions) are NOT mistaken for frame equations.
These helpers are read-only; the probe itself invokes no placement path.
"""
from __future__ import annotations

from truelinev2.proof.run_frame_aware_probe import (
    classify_equation,
    find_equations,
    find_see_sheets,
    has_matchline,
)


def test_matchline_equation_parsed_with_offset():
    eqs = find_equations("MATCH LINE STA 3+23 / 0+69 - SEE SHEET 17")
    assert len(eqs) == 1
    e = eqs[0]
    assert e["a_sta"] == "3+23" and e["b_sta"] == "0+69"
    assert e["a_ft"] == 323.0 and e["b_ft"] == 69.0
    assert e["offset_ft"] == 254.0 and e["parseable"] is True


def test_equals_form_frame_reset_parsed():
    eqs = find_equations("STA 45+33=0+00")
    assert len(eqs) == 1 and eqs[0]["a_ft"] == 4533.0 and eqs[0]["b_ft"] == 0.0


def test_callout_is_not_an_equation():
    # a normal STA..TO..STA callout has no '='/'/' separator -> not matched
    assert find_equations("STA 0+00 TO STA 2+99 DIR. BORE (299')") == []


def test_fractions_and_conduit_not_matched():
    assert find_equations("1-1.25\" HDPE and 1/4 turn") == []


def test_find_see_sheets():
    assert find_see_sheets("SEE SHEET 17 and SEE SHEET 04") == [4, 17]
    assert find_see_sheets("no reference here") == []


def test_has_matchline():
    assert has_matchline("MATCH LINE STA 1+00") is True
    assert has_matchline("MATCHLINE") is True
    assert has_matchline("just a callout") is False


def test_classify_cross_sheet_high_confidence():
    eq = find_equations("STA 3+23 / 0+69")[0]
    c = classify_equation(eq, nearby_see=[17], nearby_ml=True)
    assert c["kind"] == "cross_sheet" and c["confidence"] == "HIGH"


def test_classify_frame_reset_low_confidence():
    eq = find_equations("STA 45+33=0+00")[0]
    c = classify_equation(eq, nearby_see=[], nearby_ml=False)
    assert c["kind"] == "frame_reset" and c["confidence"] == "LOW"


def test_classify_ambiguous_multiple_links_is_medium_or_low():
    eq = find_equations("STA 3+23 / 0+69")[0]
    c = classify_equation(eq, nearby_see=[17, 18], nearby_ml=True)
    # matchline present but link not unique -> not HIGH
    assert c["kind"] == "cross_sheet" and c["confidence"] in ("MEDIUM", "LOW")
