"""Item 2 — SEE-SHEET-N named-matchline target validation (PDF-FREE / synthetic).

Locks the FAIL-OPEN contract added to the log56 s17 authored-path selector: it follows
the matchline whose 'SEE SHEET N' target matches the seam's expected neighbor sheet —
never just any callout with matching station text — while staying byte-identical to prior
behavior when the expected sheet is unknown or the callout has no parseable SEE-SHEET.

COMMAND (from repo root):
    python -m pytest backend/tests/test_authored_path_selector_see_sheet.py -v
"""
from __future__ import annotations

from app.core.redline_consult import authored_path_selector as aps

MAGENTA = [1.0, 0.0, 1.0]
BLUE = [0.0, 0.0, 1.0]


def _seg(p0, p1, color=MAGENTA, layer="BORE - PATH"):
    return {"p0": [float(p0[0]), float(p0[1])], "p1": [float(p1[0]), float(p1[1])],
            "color": list(color), "layer": layer}


def _vseam(x, y0=0.0, y1=500.0):
    return {"layer": "MATCHLINE", "length": float(y1 - y0),
            "bbox_display": [float(x), float(y0), float(x) + 0.5, float(y1)]}


def _ml(text, xy=(100, 250)):
    return {"text": text, "xy": [float(xy[0]), float(xy[1])]}


def _happy(**over):
    """Every discriminator agrees on one authored magenta run (10,250)->(100,250).
    Mirrors test_authored_path_selector._happy so a green result == 'still draws'."""
    kw = dict(
        segments=[_seg((10, 250), (40, 250)), _seg((40, 250), (70, 250)), _seg((70, 250), (100, 250)),
                  _seg((40, 270), (70, 270), color=BLUE)],
        matchline_paths=[_vseam(100)],
        start_xy=[10, 250], home_sta="1+61", neighbor_sta="1+59",
        station_callouts=[{"ft": 50, "xy": [30, 240]}, {"ft": 120, "xy": [80, 240]}],
        matchline_callouts=[_ml("MATCHLINE STA 1+61 - SEE SHEET 21")],
        offset_callouts=[{"ft": 11, "xy": [50, 260]}],
        boc_ft=11)
    kw.update(over)
    return kw


# 1. log56-shaped: callout targets SEE SHEET 21, expected 21 -> STILL BINDS + draws (regression lock).
def test_correct_see_sheet_still_binds_and_draws():
    out = aps.select_authored_s17_path(**_happy(expected_neighbor_sheet=21))
    assert out["resolved"] is True, out
    assert out["reason"] == "authored_path_evidence_fused"


# 2. STA matches but SEE SHEET 5 while expected 21 -> abstain wrong target sheet (never a wrong draw).
def test_wrong_see_sheet_abstains():
    out = aps.select_authored_s17_path(**_happy(
        matchline_callouts=[_ml("MATCHLINE STA 1+61 - SEE SHEET 5")], expected_neighbor_sheet=21))
    assert out["resolved"] is False
    assert out["reason"] == "named_matchline_wrong_target_sheet"


# 3. Two STA-matching callouts (SEE SHEET 5 + SEE SHEET 21), expected 21 -> binds the 21 one.
def test_picks_callout_with_matching_see_sheet():
    out = aps.select_authored_s17_path(**_happy(
        matchline_callouts=[_ml("MATCHLINE STA 1+61 - SEE SHEET 5"),
                            _ml("MATCHLINE STA 1+61 - SEE SHEET 21")],
        expected_neighbor_sheet=21))
    assert out["resolved"] is True, out
    assert out["reason"] == "authored_path_evidence_fused"


# 4a. expected_neighbor_sheet None -> behavior unchanged (happy still draws).
def test_expected_none_preserves_happy():
    out = aps.select_authored_s17_path(**_happy(expected_neighbor_sheet=None))
    assert out["resolved"] is True and out["reason"] == "authored_path_evidence_fused"


# 4b. expected None + a wrong-sheet callout -> still binds (old behavior: STA-text only, no rejection).
def test_expected_none_binds_regardless_of_see_sheet():
    out = aps.select_authored_s17_path(**_happy(
        matchline_callouts=[_ml("MATCHLINE STA 1+61 - SEE SHEET 5")], expected_neighbor_sheet=None))
    assert out["resolved"] is True, out


# 5. No parseable SEE SHEET on the callout, expected 21 -> fail-open binds (no regression).
def test_no_parseable_see_sheet_fails_open():
    out = aps.select_authored_s17_path(**_happy(
        matchline_callouts=[_ml("MATCHLINE STA 1+61")], expected_neighbor_sheet=21))
    assert out["resolved"] is True, out
    assert out["reason"] == "authored_path_evidence_fused"


# Direct bind_named_matchline unit: wrong sheet -> abstain; matching/absent -> bind.
def test_bind_named_matchline_see_sheet_unit():
    paths = [_vseam(100)]
    assert aps.bind_named_matchline(
        paths, [_ml("MATCHLINE STA 1+61 - SEE SHEET 5")], "1+61", "1+59",
        expected_neighbor_sheet=21) == (None, "named_matchline_wrong_target_sheet")
    edge, why = aps.bind_named_matchline(
        paths, [_ml("MATCHLINE STA 1+61 - SEE SHEET 21")], "1+61", "1+59", expected_neighbor_sheet=21)
    assert why is None and edge is not None
    # fail-open: no expected sheet -> binds the SEE SHEET 5 callout (old behavior preserved).
    edge2, why2 = aps.bind_named_matchline(paths, [_ml("MATCHLINE STA 1+61 - SEE SHEET 5")], "1+61", "1+59")
    assert why2 is None and edge2 is not None
