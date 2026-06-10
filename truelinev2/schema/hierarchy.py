"""Run / Segment hierarchy — foundational domain model (M8.2 precursor).

Implements the model in docs/findings/run-segment-hierarchy-doctrine.md:

    Project -> Package/Plan Set -> Run -> Segment -> Evidence

A bore-log row is usually a SEGMENT, not a whole physical run. A RUN is the
COMPOSITION of contiguous child segment geometries -- never a second, independent
geometry drawn over the top of them.

This module defines TYPES only. It makes no placement decision, creates no
geometry, and changes no existing behavior. Geometry here is coordinate-frame
agnostic (plan-space pixels OR geo lon/lat); the ``frame`` tag records which frame
a set of points lives in, so a future frame-aware assembler can refuse to compose
across mismatched frames.

Pure data: no engine/PDF/IO imports, no convention names, no global mutable state.
"""
from __future__ import annotations

from enum import Enum
from typing import List, NewType, Optional

from pydantic import BaseModel, Field

# --- identity newtypes ---------------------------------------------------------
# Distinct at type-check time; plain ``str`` at runtime, so they serialize cleanly
# and stay human-inspectable in payloads/logs/QA.
SegmentId = NewType("SegmentId", str)
RunId = NewType("RunId", str)
SourceContextId = NewType("SourceContextId", str)


class ContiguityEvidenceKind(str, Enum):
    """Kinds of evidence that can justify joining two segments into a run
    (doctrine section 8). Proximity is deliberately NOT a kind -- nearness is not
    proof; only an explicit, named relationship is."""
    SHARED_ENDPOINT = "SHARED_ENDPOINT"
    SAME_STRUCTURE = "SAME_STRUCTURE"
    FRAME_EQUATION_RESET = "FRAME_EQUATION_RESET"
    MATCHLINE_CONTINUITY = "MATCHLINE_CONTINUITY"
    DRAWN_PATH_CONTINUITY = "DRAWN_PATH_CONTINUITY"
    BOC_CALLOUT_CORROBORATION = "BOC_CALLOUT_CORROBORATION"
    CONTEXT = "CONTEXT"  # date / crew / source-page -- contextual only


class EvidenceStrength(str, Enum):
    STRONG = "STRONG"
    MEDIUM = "MEDIUM"
    WEAK = "WEAK"


class Point(BaseModel):
    """A coordinate-frame-agnostic 2D point (plan-space px or geo lon/lat)."""
    x: float
    y: float

    def close_to(self, other: "Point", tol: float = 1e-9) -> bool:
        return abs(self.x - other.x) <= tol and abs(self.y - other.y) <= tol


class SegmentGeometry(BaseModel):
    """The placed polyline of ONE segment, in a named coordinate frame.
    ``points`` is the segment's own geometry; >=2 points form a drawable line."""
    segment_id: SegmentId
    points: List[Point]
    frame: Optional[str] = None


class RunGeometry(BaseModel):
    """The COMPOSED geometry of a run: the ordered concatenation of its child
    segment polylines with shared join vertices de-duplicated. It introduces NO
    new vertices and adds NO overlapping span -- it is derived from the children,
    never an independent A->D redraw.

    ``segment_point_counts`` records each child's ORIGINAL point count (in order),
    so the composition is fully decomposable back to the child segments
    (reversibility is mandatory for QA / closeout / billing / audit)."""
    run_id: RunId
    segment_ids: List[SegmentId]
    points: List[Point]
    segment_point_counts: List[int]
    frame: Optional[str] = None


class SegmentEvidenceRef(BaseModel):
    """A lightweight, inspectable pointer to the evidence backing a segment's
    placement. Carried up into the run so a run can always be traced back to each
    child segment's proof. A reference -- not a copy of the whole callout."""
    segment_id: SegmentId
    kind: str
    detail: Optional[str] = None
    source_context: Optional[SourceContextId] = None
    ref: Optional[str] = None  # opaque pointer (callout id / artifact name / ...)


class RunAssemblyEvidence(BaseModel):
    """Evidence justifying ONE join (``from_segment`` -> ``to_segment``).
    Contiguity is proven join-by-join; a join needs at least one STRONG kind
    (doctrine section 8)."""
    from_segment: SegmentId
    to_segment: SegmentId
    kind: ContiguityEvidenceKind
    detail: Optional[str] = None


class BoreSegment(BaseModel):
    """The smallest independently-placeable unit -- usually one bore-log row (or a
    proven sub-range of one). Placed FIRST from its own evidence; assembled into a
    run only LATER, and only when contiguity is proven. Until then it stands alone."""
    segment_id: SegmentId
    bore_id: str
    source_context: Optional[SourceContextId] = None
    station_start_ft: Optional[float] = None
    station_end_ft: Optional[float] = None
    span_ft: Optional[float] = None
    frame: Optional[str] = None
    geometry: Optional[SegmentGeometry] = None
    evidence: List[SegmentEvidenceRef] = Field(default_factory=list)

    @property
    def is_placed(self) -> bool:
        """A segment is eligible for run assembly only once it has proven, drawable
        geometry (>=2 points)."""
        return self.geometry is not None and len(self.geometry.points) >= 2


class BoreRun(BaseModel):
    """A run: the aggregate of contiguous child segments. Holds the COMPOSED run
    geometry, the ordered child ids, the per-join assembly evidence, and the
    carried-up segment evidence. It contains NO independent geometry beyond the
    composition of its children."""
    run_id: RunId
    segment_ids: List[SegmentId]
    geometry: RunGeometry
    assembly_evidence: List[RunAssemblyEvidence] = Field(default_factory=list)
    segment_evidence: List[SegmentEvidenceRef] = Field(default_factory=list)
    frame: Optional[str] = None


class JoinVerdict(BaseModel):
    """Per-join result from contiguity proving."""
    from_segment: SegmentId
    to_segment: SegmentId
    proven: bool
    strongest: Optional[EvidenceStrength] = None
    kinds: List[ContiguityEvidenceKind] = Field(default_factory=list)
    reason: str = ""


class ContiguityResult(BaseModel):
    """Whole-chain result: proven only if EVERY consecutive join is proven."""
    proven: bool
    joins: List[JoinVerdict] = Field(default_factory=list)
    reason: str = ""
