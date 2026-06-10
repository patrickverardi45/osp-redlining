"""Run/segment hierarchy foundation -- tests (M8.2 precursor).

Proves the doctrine in docs/findings/run-segment-hierarchy-doctrine.md:
segments place first; a run is the COMPOSITION of contiguous child segment
geometries (never an independent A->D redraw); contiguity needs explicit evidence
(proximity alone is insufficient); segment evidence survives into the run; and
existing M7 behavior + the drift guards are unaffected.

Synthetic geometry only -- no PDF, no convention names.
"""
from __future__ import annotations

import pytest

from truelinev2.match.assembly import (
    RunAssemblyError,
    assemble_run,
    assemble_run_geometry,
    decompose_run_geometry,
    prove_contiguity,
)
from truelinev2.match.engine import run_match
from truelinev2.match.overlap import decide_by_unique_footage
from truelinev2.proof.import_isolation import ROOT, scan_violations
from truelinev2.schema.hierarchy import (
    BoreSegment,
    ContiguityEvidenceKind,
    Point,
    RunAssemblyEvidence,
    SegmentEvidenceRef,
    SegmentGeometry,
)
from truelinev2.schema.models import Bore, Callout, PlacementStatus
from truelinev2.stations import feet_to_station

# A straight run split into three segments: A->B->C->D
A, B, C, D = (0.0, 0.0), (10.0, 0.0), (20.0, 0.0), (30.0, 0.0)


def _geom(seg_id, pts, frame=None):
    return SegmentGeometry(segment_id=seg_id, points=[Point(x=x, y=y) for x, y in pts], frame=frame)


def _seg(seg_id, pts, frame=None, evidence=None):
    return BoreSegment(
        segment_id=seg_id, bore_id="bore_" + seg_id, geometry=_geom(seg_id, pts, frame),
        evidence=evidence or [SegmentEvidenceRef(segment_id=seg_id, kind="footage_match", ref=seg_id)])


def _join(a, b, kind):
    return RunAssemblyEvidence(from_segment=a, to_segment=b, kind=kind)


# --- D1: three segments assemble into one run -------------------------------
def test_three_segments_assemble_into_one_run():
    segs = [_seg("a", [A, B]), _seg("b", [B, C]), _seg("c", [C, D])]
    ev = [_join("a", "b", ContiguityEvidenceKind.SHARED_ENDPOINT),
          _join("b", "c", ContiguityEvidenceKind.SHARED_ENDPOINT)]
    run = assemble_run("run1", segs, ev)
    assert run is not None
    assert run.segment_ids == ["a", "b", "c"]
    # one connected polyline A->B->C->D (4 vertices), NOT a 2-vertex A->D line
    assert [(p.x, p.y) for p in run.geometry.points] == [A, B, C, D]


# --- D2: run geometry is composed from segments, not redrawn ----------------
def test_run_geometry_is_composition_not_redraw():
    geoms = [_geom("a", [A, B]), _geom("b", [B, C]), _geom("c", [C, D])]
    rg = assemble_run_geometry("run1", geoms)
    # composed length == sum(child points) - shared joins == 2+2+2 - 2
    assert len(rg.points) == 4
    # passes through the intermediate junctions B and C (not a straight A->D shortcut)
    assert Point(x=10, y=0) in rg.points and Point(x=20, y=0) in rg.points
    assert rg.segment_point_counts == [2, 2, 2]
    # decomposes back to the EXACT children -> proof of composition, not redraw
    back = decompose_run_geometry(rg)
    assert [g.segment_id for g in back] == ["a", "b", "c"]
    assert [[(p.x, p.y) for p in g.points] for g in back] == [[A, B], [B, C], [C, D]]


# --- D3: segment evidence refs survive into the run ------------------------
def test_segment_evidence_survives_into_run():
    segs = [_seg("a", [A, B], evidence=[SegmentEvidenceRef(segment_id="a", kind="callout", ref="c-a")]),
            _seg("b", [B, C], evidence=[SegmentEvidenceRef(segment_id="b", kind="callout", ref="c-b")])]
    run = assemble_run("run1", segs, [_join("a", "b", ContiguityEvidenceKind.FRAME_EQUATION_RESET)])
    assert run is not None
    refs = {(r.segment_id, r.ref) for r in run.segment_evidence}
    assert ("a", "c-a") in refs and ("b", "c-b") in refs


# --- D4: unproven contiguity keeps segments separate / blocks assembly -----
def test_unproven_contiguity_blocks_assembly():
    segs = [_seg("a", [A, B]), _seg("b", [B, C])]
    assert assemble_run("run1", segs, []) is None          # no evidence -> no run
    res = prove_contiguity(segs, [])
    assert res.proven is False and res.joins[0].reason == "NO_EVIDENCE"
    # the placed segments are untouched and remain individually inspectable
    assert all(s.is_placed for s in segs)


# --- D5: nearby endpoints alone are insufficient --------------------------
def test_nearby_endpoints_alone_insufficient():
    # endpoints close (B vs B') but NOT identical, and only weak CONTEXT evidence
    Bp = (10.0001, 0.0)
    segs = [_seg("a", [A, B]), _seg("b", [Bp, C])]
    weak = [_join("a", "b", ContiguityEvidenceKind.CONTEXT)]
    res = prove_contiguity(segs, weak)
    assert res.proven is False and res.joins[0].reason == "NO_STRONG_EVIDENCE_PROXIMITY_INSUFFICIENT"
    assert assemble_run("run1", segs, weak) is None
    # proximity is not contiguity at the geometry layer either: composing
    # nearby-but-not-identical endpoints is rejected
    with pytest.raises(RunAssemblyError):
        assemble_run_geometry("run1", [s.geometry for s in segs])


def test_strong_evidence_assembles_even_without_shared_endpoint_kind():
    # a non-endpoint STRONG kind (same structure) proves the join; geometry still
    # must physically meet, which it does here
    segs = [_seg("a", [A, B]), _seg("b", [B, C])]
    res = prove_contiguity(segs, [_join("a", "b", ContiguityEvidenceKind.SAME_STRUCTURE)])
    assert res.proven is True


# --- D6: duplicate overlapping parent geometry is rejected / impossible ----
def test_overlapping_parent_geometry_rejected():
    children = [_geom("a", [A, B]), _geom("b", [B, C]), _geom("c", [C, D])]
    parent = _geom("parent", [A, D])  # an independent whole-run line over the children
    with pytest.raises(RunAssemblyError):
        assemble_run_geometry("run1", children + [parent])


def test_run_geometry_cannot_be_independent_AD_line():
    rg = assemble_run_geometry("run1", [_geom("a", [A, B]), _geom("b", [B, C]), _geom("c", [C, D])])
    # an A->D redraw would have 2 vertices; the composition has 4 and keeps B, C
    assert len(rg.points) == 4
    assert (rg.points[0].x, rg.points[0].y) == A and (rg.points[-1].x, rg.points[-1].y) == D
    assert sum(c - 1 for c in rg.segment_point_counts) + 1 == len(rg.points)


def test_mixed_frames_rejected():
    with pytest.raises(RunAssemblyError):
        assemble_run_geometry("run1", [_geom("a", [A, B], frame="sheetX"),
                                       _geom("b", [B, C], frame="sheetY")])


# --- D7: existing M7 placement behavior is not degraded -------------------
class _StubDialect:
    name = "test"
    match_mode = "footage"

    def __init__(self, callouts):
        self._c = callouts

    def extract_callouts(self, plan, sheet, offset):
        return [c for c in self._c if c.sheet == sheet]


def _c(sheet, f0, f1):
    return Callout(sheet=sheet, page=sheet, from_sta=feet_to_station(f0), to_sta=feet_to_station(f1),
                   from_ft=f0, to_ft=f1, footage=round(f1 - f0, 2), text="x", dialect="test")


def _bore(s, e, sheets):
    return Bore(bore_id="logT", source_file="logT.xlsx", sheet_refs=list(sheets),
                station_start=feet_to_station(s), station_end=feet_to_station(e),
                station_start_ft=s, station_end_ft=e, span_ft=round(e - s, 2))


def test_m7_unique_footage_decider_unchanged():
    assert decide_by_unique_footage([_c(7, 4000, 4416)], 416.0)["status"] == "REVIEW"
    assert decide_by_unique_footage([_c(7, 4000, 4100)], 416.0)["status"] == "ABSTAIN"
    assert decide_by_unique_footage([_c(7, 4000, 4416), _c(8, 5000, 5416)], 416.0)["status"] == "ABSTAIN"


def test_m7_engine_paths_unchanged():
    assert run_match(_bore(0, 416, [7]), None, _StubDialect([_c(7, 4000, 4416)]), 0).status == PlacementStatus.REVIEW
    assert run_match(_bore(0, 299, [8]), None, _StubDialect([_c(8, 0, 299)]), 0).status == PlacementStatus.AUTO_SELECT


# --- D8: drift guards still pass with the new modules present -------------
def test_new_modules_keep_import_isolation():
    assert scan_violations(ROOT) == []
