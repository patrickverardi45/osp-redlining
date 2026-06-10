"""Station-frame model — types for matchline frame equations and SAFE frame
translation (M8.2b foundation).

A plan sheet defines a STATION FRAME: stationing local to that sheet. A matchline
carries a FRAME EQUATION like ``STA 3+23 / 0+69 - SEE SHEET 17`` -- meaning this
frame's STA 3+23 is the SAME physical point as sheet 17's STA 0+69 (a frame
translation of 254 ft). Linking callouts by RAW station number across that matchline
is wrong (``0+69`` here is not ``0+69`` there); only a translation THROUGH a proven
frame edge is safe.

This module defines TYPES only -- no parsing, no placement decision, no IO, no global
mutable state, no convention names. A future frame-aware assembler consumes these to
translate a station between frames BEFORE composing segments across them (today
``match/assembly.py`` simply refuses to compose across mismatched frames).
"""
from __future__ import annotations

from enum import Enum
from typing import List, NewType, Optional, Tuple

from pydantic import BaseModel, Field

# Identity of a station frame. Distinct at type-check time; a plain ``str`` at
# runtime (serializes cleanly, stays inspectable in payloads/logs/QA), mirroring the
# ``SegmentId`` / ``RunId`` newtypes in schema/hierarchy.py.
FrameId = NewType("FrameId", str)


class ParseConfidence(str, Enum):
    """How strongly a parsed equation is believed to be a real, uniquely-linked frame
    edge. Only HIGH is ever eligible to become a translatable (safe) edge."""
    HIGH = "HIGH"      # explicit matchline marker AND exactly one linked frame
    MEDIUM = "MEDIUM"  # matchline OR exactly one linked frame (not both)
    LOW = "LOW"        # neither / ambiguous


class EquationKind(str, Enum):
    """What a parsed station-pair equation appears to express."""
    CROSS_FRAME = "CROSS_FRAME"            # links this frame to another (a translation)
    FRAME_RESET = "FRAME_RESET"            # one side is 0+00: a local reset, no link
    STATION_EQUATION = "STATION_EQUATION"  # an equation not (yet) associable to a 2nd frame


class StationValue(BaseModel):
    """A parsed station notation and its value in feet (``A+BB`` == A*100 + BB)."""
    raw: str
    feet: float


class SheetFrame(BaseModel):
    """A station frame anchored to a specific plan sheet number."""
    frame_id: FrameId
    sheet: int


class FrameEquation(BaseModel):
    """A station-pair equation ``a <sep> b`` parsed from plan text, plus the nearby
    context that decides whether it links two frames. Frame-neutral: it records the
    two station values, the separator, and the implied offset, but asserts a link only
    via ``linked_frames`` + ``confidence`` (never from the raw numbers alone)."""
    a: StationValue
    b: StationValue
    separator: str                  # '=' or '/'
    offset_ft: float                # a.feet - b.feet (the implied frame translation)
    kind: EquationKind = EquationKind.STATION_EQUATION
    confidence: ParseConfidence = ParseConfidence.LOW
    linked_frames: List[int] = Field(default_factory=list)  # nearby SEE-SHEET targets
    has_matchline: bool = False
    source: Optional[str] = None    # raw matched text (provenance)


class FrameEdge(BaseModel):
    """A directed frame translation: a point at ``from_frame`` STA equals a point at
    ``to_frame`` STA, with a constant ``offset_ft = from_feet - to_feet``. Only edges
    that are HIGH confidence, uniquely linked, and conflict-free are SAFE to translate
    through (see match/frames.safe_edges + build_frame_graph)."""
    from_frame: FrameId
    to_frame: FrameId
    offset_ft: float
    confidence: ParseConfidence
    a_raw: Optional[str] = None
    b_raw: Optional[str] = None
    source: Optional[str] = None


class FrameConflict(BaseModel):
    """A frame pair with two-or-more edges whose offsets disagree (beyond tolerance):
    the pair is AMBIGUOUS and must never be translated through. Recorded, not silently
    dropped, so the ambiguity stays inspectable."""
    frame_pair: Tuple[FrameId, FrameId]   # canonical (sorted) pair
    offsets_ft: List[float]


class FrameGraph(BaseModel):
    """The set of SAFE, translatable frame edges (HIGH-confidence, unique,
    conflict-free) plus the rejected conflicts. Built ONLY from safe edges;
    ambiguous/conflicting evidence is preserved in ``conflicts`` but is never made
    translatable. Translation lookups are pure functions in match/frames.py."""
    edges: List[FrameEdge] = Field(default_factory=list)
    conflicts: List[FrameConflict] = Field(default_factory=list)
