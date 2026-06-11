"""M8.14.b.5 Phase 0 -- tests pinning the start-evidence probe helpers.

Locks: origin extrapolation is a locator heuristic with exact linear math;
co-located rivals are ALL reported (across layers); the typed outcome never
lane-opens without a printed origin -- a single metric candidate is still a
pick-card (identity is never bound by extrapolated position)."""
from __future__ import annotations

from truelinev2.extract.structure_position import SymbolCluster
from truelinev2.proof.run_log51_start_evidence_probe import (
    LANE_READY,
    MISSING_ARTIFACT,
    PICK_CARD,
    classify_start_evidence,
    colocated_candidates,
    extrapolate_origin,
)


def test_extrapolate_origin_linear():
    # ladder 1+00@(436,360), end 2+99@(149.9,343.3): origin past the low end
    ox, oy = extrapolate_origin([(100.0, 436.0, 359.5), (200.0, 292.0, 351.7),
                                 (299.0, 149.9, 343.3)])
    assert 570.0 <= ox <= 590.0
    assert 360.0 <= oy <= 372.0
    # pure two-point line: exact values
    assert extrapolate_origin([(100.0, 200.0, 50.0), (200.0, 100.0, 50.0)]) == (300.0, 50.0)


def test_colocated_candidates_projects_along_frame():
    # real sheet-8 frame: ticks 1+00/2+00 + the b.4-bound end pot at 2+99
    frame = [(100.0, 436.0, 359.5), (200.0, 292.0, 351.7), (299.0, 149.9, 343.3)]
    clusters = {"NEXTLINK": [SymbolCluster(577.6, 354.2, 4)],
                "FLOWER POT": [SymbolCluster(574.6, 354.3, 11),
                               SymbolCluster(149.9, 343.3, 13)]}
    rivals = colocated_candidates(clusters, frame)
    assert {r["layer"] for r in rivals} == {"NEXTLINK", "FLOWER POT"}
    assert len(rivals) == 2  # the far end pot (station ~299) is not a rival
    assert all(abs(r["implied_station_ft"]) <= 10.0 for r in rivals)
    # the perpendicular offset is the text-row class, NOT a station error
    assert all(5.0 <= r["perp_offset_pt"] <= 20.0 for r in rivals)


def test_project_station_separates_along_from_perpendicular():
    from truelinev2.proof.run_log51_start_evidence_probe import project_station
    frame = [(100.0, 200.0, 50.0), (200.0, 100.0, 50.0)]
    sta, perp = project_station(frame, (300.0, 57.0))  # on-axis x, 7 pt beside
    assert sta == 0.0 and perp == 7.0


def test_classification_never_lane_opens_without_printed_origin():
    two = [{"layer": "NEXTLINK"}, {"layer": "FLOWER POT"}]
    v = classify_start_evidence(0, two)
    assert v["outcome"] == PICK_CARD
    assert v["named_missing_artifact"] == MISSING_ARTIFACT
    assert "ambiguous" in v["reason"]
    # even a SINGLE metric candidate stays a pick-card
    v1 = classify_start_evidence(0, two[:1])
    assert v1["outcome"] == PICK_CARD and "forbidden" in v1["reason"]
    # a printed origin reopens the resolver lane
    assert classify_start_evidence(1, [])["outcome"] == LANE_READY
