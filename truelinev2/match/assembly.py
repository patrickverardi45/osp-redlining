"""Run assembly -- compose proven contiguous segments into a run (M8.2 precursor).

Two pure capabilities, per docs/findings/run-segment-hierarchy-doctrine.md:

  * ``prove_contiguity(...)``       -- (C) validate that an ordered segment chain may
    become a run: every consecutive join needs EXPLICIT evidence, with at least one
    STRONG kind. Proximity alone is never accepted (it is not even an evidence kind).

  * ``assemble_run_geometry(...)``  -- (B) compose ordered, proven segment geometries
    into ONE run polyline by concatenating child points and de-duplicating the shared
    join vertex. It introduces no new vertices and emits no independent A->D parent
    line; a non-contiguous or overlap-producing input is REJECTED (RunAssemblyError).

  * ``assemble_run(...)`` ties them together: prove first, then compose. Returns
    ``None`` (segments stay separate / REVIEW) when contiguity is not proven.

  * ``decompose_run_geometry(...)`` reverses a composition back to its child
    segment geometries -- proving a run is a composition, not an independent redraw,
    and that segments remain inspectable.

Pure functions only: no IO, no global mutable state, no convention names, no old-app
code. Run geometry is always derived from child segments -- never drawn on top.
"""
from __future__ import annotations

from typing import List, Optional

from truelinev2.schema.hierarchy import (
    BoreRun,
    BoreSegment,
    ContiguityEvidenceKind,
    ContiguityResult,
    EvidenceStrength,
    JoinVerdict,
    RunAssemblyEvidence,
    RunGeometry,
    RunId,
    SegmentEvidenceRef,
    SegmentGeometry,
    SegmentId,
)

# Doctrine section 8: strength of each contiguity-evidence kind. A join is proven
# only with >=1 STRONG kind; MEDIUM/WEAK corroborate but cannot substitute.
STRENGTH_BY_KIND = {
    ContiguityEvidenceKind.SHARED_ENDPOINT: EvidenceStrength.STRONG,
    ContiguityEvidenceKind.SAME_STRUCTURE: EvidenceStrength.STRONG,
    ContiguityEvidenceKind.FRAME_EQUATION_RESET: EvidenceStrength.STRONG,
    ContiguityEvidenceKind.MATCHLINE_CONTINUITY: EvidenceStrength.STRONG,
    ContiguityEvidenceKind.DRAWN_PATH_CONTINUITY: EvidenceStrength.MEDIUM,
    ContiguityEvidenceKind.BOC_CALLOUT_CORROBORATION: EvidenceStrength.MEDIUM,
    ContiguityEvidenceKind.CONTEXT: EvidenceStrength.WEAK,
}
_STRENGTH_ORDER = {EvidenceStrength.WEAK: 0, EvidenceStrength.MEDIUM: 1, EvidenceStrength.STRONG: 2}


class RunAssemblyError(ValueError):
    """Raised when an input would produce a non-composition: a gap or overlap
    between consecutive segments, or an independent parent line spanning the run.
    Run geometry must be a clean composition of its children."""


def _strongest(strengths: List[EvidenceStrength]) -> Optional[EvidenceStrength]:
    if not strengths:
        return None
    return max(strengths, key=lambda s: _STRENGTH_ORDER[s])


def prove_contiguity(segments: List[BoreSegment],
                     evidence: List[RunAssemblyEvidence]) -> ContiguityResult:
    """(C) A chain may become a run only when EVERY consecutive join carries
    explicit evidence including at least one STRONG kind. No evidence, or only
    medium/weak (e.g. CONTEXT) evidence, leaves the chain UNPROVEN -- the segments
    stay separate. Proximity is not representable here, so it can never prove a join."""
    if not segments:
        return ContiguityResult(proven=False, reason="NO_SEGMENTS")
    if len(segments) == 1:
        # A single placed segment is a trivially-valid one-segment run: no joins.
        return ContiguityResult(proven=True, reason="SINGLE_SEGMENT")

    joins: List[JoinVerdict] = []
    all_proven = True
    for a, b in zip(segments, segments[1:]):
        ev = [e for e in evidence
              if e.from_segment == a.segment_id and e.to_segment == b.segment_id]
        kinds = [e.kind for e in ev]
        strengths = [STRENGTH_BY_KIND[k] for k in kinds]
        strongest = _strongest(strengths)
        if not ev:
            proven, reason = False, "NO_EVIDENCE"
        elif EvidenceStrength.STRONG not in strengths:
            proven, reason = False, "NO_STRONG_EVIDENCE_PROXIMITY_INSUFFICIENT"
        else:
            proven, reason = True, "PROVEN"
        all_proven = all_proven and proven
        joins.append(JoinVerdict(from_segment=a.segment_id, to_segment=b.segment_id,
                                 proven=proven, strongest=strongest, kinds=kinds,
                                 reason=reason))
    return ContiguityResult(proven=all_proven, joins=joins,
                            reason="PROVEN" if all_proven else "UNPROVEN_JOIN")


def assemble_run_geometry(run_id: RunId, segment_geometries: List[SegmentGeometry],
                          join_tol: float = 1e-9) -> RunGeometry:
    """(B) Compose ordered, proven segment geometries into ONE run polyline.

    The composition is exactly the children's points in order, with each shared
    join vertex de-duplicated -- so it adds no new vertices and no overlapping span.
    Consecutive segments MUST meet at a shared endpoint (within ``join_tol``); a gap,
    an overlap, or an independent parent line (e.g. an A->D geometry appended over
    A->B->C->D children) breaks the shared-endpoint chain and is REJECTED."""
    if not segment_geometries:
        raise RunAssemblyError("no segment geometries to assemble")
    for g in segment_geometries:
        if len(g.points) < 2:
            raise RunAssemblyError(f"segment {g.segment_id!r} has <2 points; not a drawable segment")
    frames = {g.frame for g in segment_geometries}
    if len(frames) > 1:
        # Cannot compose across mismatched coordinate frames -- that is exactly the
        # frame-awareness M8.2 must resolve before any cross-frame assembly.
        raise RunAssemblyError(f"cannot compose across mixed coordinate frames: {sorted(map(str, frames))}")

    composed: List = list(segment_geometries[0].points)
    counts: List[int] = [len(segment_geometries[0].points)]
    seg_ids: List[SegmentId] = [segment_geometries[0].segment_id]
    for prev, cur in zip(segment_geometries, segment_geometries[1:]):
        if not prev.points[-1].close_to(cur.points[0], tol=join_tol):
            raise RunAssemblyError(
                f"non-contiguous join {prev.segment_id!r}->{cur.segment_id!r}: "
                f"end ({prev.points[-1].x},{prev.points[-1].y}) != "
                f"start ({cur.points[0].x},{cur.points[0].y}) -- gap, overlap, or "
                f"independent parent geometry rejected (proximity is not contiguity)")
        composed.extend(cur.points[1:])  # drop the duplicated shared join vertex
        counts.append(len(cur.points))   # ORIGINAL child count -> decomposable
        seg_ids.append(cur.segment_id)
    return RunGeometry(run_id=run_id, segment_ids=seg_ids, points=composed,
                       segment_point_counts=counts, frame=segment_geometries[0].frame)


def decompose_run_geometry(run: RunGeometry) -> List[SegmentGeometry]:
    """Reverse a composition back to its child segment geometries. Each child
    re-shares the join vertex with its neighbor, so the originals are reconstructed
    exactly -- this is the proof that a run is a composition, not an independent draw."""
    out: List[SegmentGeometry] = []
    start = 0
    for sid, n in zip(run.segment_ids, run.segment_point_counts):
        out.append(SegmentGeometry(segment_id=sid, points=run.points[start:start + n],
                                   frame=run.frame))
        start += n - 1  # the next child begins at the shared vertex
    return out


def assemble_run(run_id: RunId, segments: List[BoreSegment],
                 evidence: List[RunAssemblyEvidence]) -> Optional[BoreRun]:
    """Prove contiguity, then compose. Returns ``None`` (keep segments separate /
    REVIEW) when any segment is unplaced or contiguity is not proven. On success the
    returned run composes child geometries and carries up every child's evidence ref."""
    if not segments:
        return None
    if not all(s.is_placed for s in segments):
        return None  # cannot assemble what is not yet placed
    if not prove_contiguity(segments, evidence).proven:
        return None  # unproven contiguity -> segments stay separate
    geom = assemble_run_geometry(run_id, [s.geometry for s in segments])  # type: ignore[arg-type]
    carried: List[SegmentEvidenceRef] = [ref for s in segments for ref in s.evidence]
    return BoreRun(run_id=run_id, segment_ids=[s.segment_id for s in segments],
                   geometry=geom, assembly_evidence=list(evidence),
                   segment_evidence=carried, frame=geom.frame)
