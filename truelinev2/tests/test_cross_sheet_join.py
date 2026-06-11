"""M8.14.b.9 -- tests pinning the cross-sheet conduit join law.

Locks the pure decision: ANY missing clause (equation edge, equation-at-
matchline, chain reach, printed footages, footage closure, implied-scale
agreement) -> NOT_PROVEN with the exact artifact named; nothing is inferred
to fill a gap. Helper geometry (nearest_gap, matchline filtering, callout
footage grammar) pinned synthetically."""
from __future__ import annotations

from truelinev2.proof.run_cross_sheet_conduit_join_probe import (
    NOT_PROVEN,
    PROVEN,
    cross_sheet_join_verdict,
    find_run_callout_footage,
    matchline_bboxes,
    nearest_gap,
)

FULL = dict(equation_edge=True, eq_at_matchline_a=True, eq_at_matchline_b=True,
            chain_a_reaches=True, chain_b_reaches=True,
            seg_a_ft=160.0, seg_b_ft=39.0, span_ft=199.0,
            scale_a=1.4375, scale_b=1.4360)


def test_full_evidence_proves():
    v = cross_sheet_join_verdict(**FULL)
    assert v["verdict"] == PROVEN and "law" in v


def test_each_missing_clause_abstains_with_named_artifact():
    cases = [
        ({"equation_edge": False}, "frame equation"),
        ({"eq_at_matchline_b": False}, "typeset AT both"),
        ({"chain_a_reaches": False}, "sheet A's conduit chain"),
        ({"chain_b_reaches": False}, "sheet B's conduit chain"),
        ({"seg_b_ft": None}, "printed run-callout footages"),
        ({"seg_b_ft": 50.0}, "footage closure"),
        ({"scale_b": None}, "drawn structure->matchline distances"),
        ({"scale_b": 0.91}, "implied-scale agreement"),
    ]
    for patch, needle in cases:
        v = cross_sheet_join_verdict(**{**FULL, **patch})
        assert v["verdict"] == NOT_PROVEN, patch
        assert needle in v["named_missing"], (patch, v["named_missing"])


def test_nearest_gap_inside_and_outside():
    bb = (61.0, 234.0, 62.0, 537.0)
    assert nearest_gap([(61.5, 300.0)], bb) == 0.0
    assert nearest_gap([(65.0, 300.0)], bb) == 3.0
    assert nearest_gap([], bb) is None


def test_matchline_bboxes_filters_short_and_fat():
    long_thin = {"layer": "ML", "x0": 61.0, "y0": 234.0, "x1": 62.0, "y1": 537.0}
    legend_tick = {"layer": "ML", "x0": 0.0, "y0": 0.0, "x1": 20.0, "y1": 1.0}
    fat_box = {"layer": "ML", "x0": 0.0, "y0": 0.0, "x1": 300.0, "y1": 300.0}
    other = {"layer": "X", "x0": 61.0, "y0": 234.0, "x1": 62.0, "y1": 537.0}
    out = matchline_bboxes([long_thin, legend_tick, fat_box, other], "ML")
    assert out == [(61.0, 234.0, 62.0, 537.0)]


def test_find_run_callout_footage_grammar():
    lines = ["STA 4+51 TO 6+11", "DIR. BORE (160')", "2-1.25\" HDPE"]
    assert find_run_callout_footage(lines, "4+51", "6+11") == 160.0
    lines2 = ["STA 6+11 TO STA 6+50", "DIR. BORE (39')"]
    assert find_run_callout_footage(lines2, "6+11", "6+50") == 39.0
    assert find_run_callout_footage(["STA 1+00 TO 2+00"], "1+00", "3+00") is None
    assert find_run_callout_footage(["STA 1+00 TO 2+00", "no footage here"],
                                    "1+00", "2+00") is None
