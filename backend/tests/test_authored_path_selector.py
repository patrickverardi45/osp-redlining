"""Focused unit tests for the log56 evidence-fusion authored-path selector. PDF-FREE / synthetic.

Validates the abstain-FIRST contract: the selector draws ONLY when run color + named matchline +
a UNIQUE color-isolated candidate path + station monotonicity + BOC/11' corridor ALL agree; any
single failure yields a precise, machine-readable discriminator reason (never a guess).

COMMAND (from repo root):
    python -m pytest backend/tests/test_authored_path_selector.py -v
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


def _happy(**over):
    """Kwargs where EVERY discriminator agrees on one authored magenta run (10,250)->(100,250)."""
    kw = dict(
        segments=[_seg((10, 250), (40, 250)), _seg((40, 250), (70, 250)), _seg((70, 250), (100, 250)),
                  _seg((40, 270), (70, 270), color=BLUE)],   # sibling run, different color -> excluded
        matchline_paths=[_vseam(100)],
        start_xy=[10, 250], home_sta="1+61", neighbor_sta="1+59",
        station_callouts=[{"ft": 50, "xy": [30, 240]}, {"ft": 120, "xy": [80, 240]}],
        matchline_callouts=[{"text": "MATCHLINE STA 1+61 - SEE SHEET 21", "xy": [100, 250]}],
        offset_callouts=[{"ft": 11, "xy": [50, 260]}],
        boc_ft=11)
    kw.update(over)
    return kw


def test_all_discriminators_agree_draws():
    out = aps.select_authored_s17_path(**_happy())
    assert out["resolved"] is True, out
    assert out["reason"] == "authored_path_evidence_fused"
    xs = [p[0] for p in out["path_xy"]]
    assert xs == sorted(xs) and out["path_xy"][0][0] == 10 and abs(out["path_xy"][-1][0] - 100) < 1
    assert out["discriminators"]["run_color"] == MAGENTA       # blue sibling excluded by color


def test_named_matchline_not_bound():
    out = aps.select_authored_s17_path(**_happy(matchline_callouts=[]))
    assert out["resolved"] is False and out["reason"] == "named_matchline_not_bound"


def test_color_did_not_isolate_single_run():
    # a different-color stroke ALSO incident to the start -> mixed -> abstain
    segs = _happy()["segments"] + [_seg((10, 250), (40, 230), color=BLUE)]
    out = aps.select_authored_s17_path(**_happy(segments=segs))
    assert out["resolved"] is False and out["reason"] == "color_did_not_isolate_single_run"


def test_multiple_candidate_paths_after_evidence_fusion():
    # diamond within the magenta run -> two equal routes to the seam -> abstain (not a guess)
    segs = [_seg((10, 250), (40, 230)), _seg((10, 250), (40, 270)),
            _seg((40, 230), (70, 250)), _seg((40, 270), (70, 250)),
            _seg((70, 250), (100, 250))]
    out = aps.select_authored_s17_path(**_happy(segments=segs))
    assert out["resolved"] is False
    assert out["reason"] == "multiple_candidate_paths_after_evidence_fusion"


def test_station_callouts_insufficient_to_orient():
    out = aps.select_authored_s17_path(**_happy(station_callouts=[{"ft": 50, "xy": [30, 240]}]))
    assert out["resolved"] is False and out["reason"] == "station_callouts_insufficient_to_orient"


def test_path_not_station_monotonic():
    out = aps.select_authored_s17_path(**_happy(
        station_callouts=[{"ft": 120, "xy": [30, 240]}, {"ft": 50, "xy": [80, 240]}]))  # decreasing
    assert out["resolved"] is False and out["reason"] == "path_not_station_monotonic"


def test_boc_corridor_ambiguous():
    out = aps.select_authored_s17_path(**_happy(offset_callouts=[]))  # no 11' callout near the path
    assert out["resolved"] is False and out["reason"] == "boc_corridor_ambiguous"


def test_parse_station_callouts_pure():
    words = [{"text": "STA 1+50", "bbox_display": [10, 20, 30, 40]},
             {"text": "POTHOLE", "bbox_display": [0, 0, 1, 1]}]
    got = aps.parse_station_callouts(words)
    assert len(got) == 1 and got[0]["ft"] == 150 and got[0]["sta"] == "1+50"
