"""Frame-equation parsing and SAFE frame translation -- the pure foundation for
frame-aware assembly (M8.2b). NOT wired into the matcher: it imports nothing from
chains / engine / decide / assembly / score and changes no placement decision. No IO,
no global mutable state, no convention names, no old-app imports.

Grammar (proven read-only by the M8.2a probe): a matchline carries a frame equation
``STA a / b`` or ``STA a = b``; a nearby ``SEE SHEET N`` links this frame to frame N.
ONLY HIGH-confidence, uniquely-linked, conflict-free edges are translatable; raw equal
station numbers ALONE never establish a link, and an unknown frame pair translates to
``None`` (the caller must ABSTAIN -- never fall back to the raw value).
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

from truelinev2.schema.frames import (
    EquationKind,
    FrameConflict,
    FrameEdge,
    FrameEquation,
    FrameGraph,
    FrameId,
    ParseConfidence,
    SheetFrame,
    StationValue,
)
from truelinev2.stations import parse_station

# --- grammar (frame-neutral; no customer/region assumptions) ------------------
_STA = r"\d+\+\d+(?:\.\d+)?"
_EQ = re.compile(rf"(?:STA\s*)?({_STA})\s*([=/])\s*(?:STA\s*)?({_STA})", re.I)
_SEE_SHEET = re.compile(r"SEE\s+SHEET\s+0*(\d{1,3})", re.I)
_MATCHLINE = re.compile(r"MATCH\s*LINE", re.I)

# Offset spread (ft) above which two edges for the same frame pair are a conflict.
_CONFLICT_TOL_FT = 2.0
# How far (chars) around an equation to look for its SEE-SHEET / matchline context.
_CONTEXT_WINDOW = 70


def frame_for_sheet(sheet: int) -> FrameId:
    """The canonical FrameId for a plan sheet's station frame."""
    return FrameId(f"sheet:{int(sheet)}")


def sheet_frame(sheet: int) -> SheetFrame:
    """A SheetFrame binding a sheet number to its canonical FrameId."""
    return SheetFrame(frame_id=frame_for_sheet(sheet), sheet=int(sheet))


def parse_station_value(raw) -> Optional[StationValue]:
    """``'3+23'`` -> StationValue(raw='3+23', feet=323.0); None if unparseable.
    Reuses ``truelinev2.stations.parse_station`` (the single station parser)."""
    ft = parse_station(raw)
    if ft is None:
        return None
    return StationValue(raw=str(raw).strip(), feet=ft)


def find_see_sheets(text: str) -> List[int]:
    """The sheet numbers referenced by ``SEE SHEET N`` tokens, sorted + unique."""
    return sorted({int(x) for x in _SEE_SHEET.findall(text or "")})


def has_matchline(text: str) -> bool:
    return bool(_MATCHLINE.search(text or ""))


def _confidence(has_ml: bool, n_links: int) -> ParseConfidence:
    if has_ml and n_links == 1:
        return ParseConfidence.HIGH
    if has_ml or n_links == 1:
        return ParseConfidence.MEDIUM
    return ParseConfidence.LOW


def _kind(a_ft: float, b_ft: float, n_links: int) -> EquationKind:
    if n_links:
        return EquationKind.CROSS_FRAME
    if a_ft == 0.0 or b_ft == 0.0:
        return EquationKind.FRAME_RESET
    return EquationKind.STATION_EQUATION


def parse_frame_equations(text: str, *, context_window: int = _CONTEXT_WINDOW) -> List[FrameEquation]:
    """Parse EVERY station-pair equation in ``text`` into a typed FrameEquation, each
    classified by the SEE-SHEET / matchline context within ``context_window`` chars of
    the match. A plain ``STA 0+00 TO STA 2+99`` callout (no ``=`` / ``/`` separator) is
    NOT an equation; fractions / conduit sizes are not mistaken for one."""
    out: List[FrameEquation] = []
    blob = text or ""
    for m in _EQ.finditer(blob):
        a = parse_station_value(m.group(1))
        b = parse_station_value(m.group(3))
        if a is None or b is None:
            continue
        ctx = blob[max(0, m.start() - context_window): m.end() + context_window]
        links = find_see_sheets(ctx)
        ml = has_matchline(ctx)
        out.append(FrameEquation(
            a=a, b=b, separator=m.group(2),
            offset_ft=round(a.feet - b.feet, 2),
            kind=_kind(a.feet, b.feet, len(links)),
            confidence=_confidence(ml, len(links)),
            linked_frames=links, has_matchline=ml, source=m.group(0).strip(),
        ))
    return out


def build_frame_edges(equations: List[FrameEquation], from_frame: FrameId) -> List[FrameEdge]:
    """Candidate edges from equations parsed on ``from_frame``'s sheet: keep ONLY
    CROSS_FRAME equations with EXACTLY ONE linked frame (a unique link). Multi-link
    and unlinked equations build NO edge."""
    edges: List[FrameEdge] = []
    for eq in equations:
        if eq.kind == EquationKind.CROSS_FRAME and len(eq.linked_frames) == 1:
            edges.append(FrameEdge(
                from_frame=from_frame,
                to_frame=frame_for_sheet(eq.linked_frames[0]),
                offset_ft=eq.offset_ft, confidence=eq.confidence,
                a_raw=eq.a.raw, b_raw=eq.b.raw, source=eq.source,
            ))
    return edges


def _canonical_pair(edge: FrameEdge) -> Tuple[str, str, float]:
    """``(lo, hi, signed offset in the lo->hi direction)`` so both directions of the
    same physical relationship compare equal."""
    f, t, off = str(edge.from_frame), str(edge.to_frame), edge.offset_ft
    if f <= t:
        return f, t, off
    return t, f, -off


def detect_conflicts(edges: List[FrameEdge]) -> List[FrameConflict]:
    """Frame pairs whose edges DISAGREE on the offset (spread > tolerance) after
    normalizing direction. A pair with consistent offsets is NOT a conflict."""
    by_pair: dict = {}
    for e in edges:
        lo, hi, off = _canonical_pair(e)
        by_pair.setdefault((lo, hi), []).append(off)
    conflicts: List[FrameConflict] = []
    for (lo, hi), offs in by_pair.items():
        if max(offs) - min(offs) > _CONFLICT_TOL_FT:
            conflicts.append(FrameConflict(
                frame_pair=(FrameId(lo), FrameId(hi)),
                offsets_ft=sorted({round(o, 2) for o in offs}),
            ))
    return conflicts


def safe_edges(edges: List[FrameEdge]) -> List[FrameEdge]:
    """Translatable edges only: HIGH confidence AND the (direction-normalized) frame
    pair is conflict-free. One representative edge per safe pair (deduped). Everything
    ambiguous (MEDIUM/LOW, multi-defined, conflicting) is dropped -- abstain-first."""
    conflicted = {(c.frame_pair[0], c.frame_pair[1]) for c in detect_conflicts(edges)}
    out: List[FrameEdge] = []
    seen = set()
    for e in edges:
        if e.confidence != ParseConfidence.HIGH:
            continue
        lo, hi, _off = _canonical_pair(e)
        if (lo, hi) in conflicted or (lo, hi) in seen:
            continue
        seen.add((lo, hi))
        out.append(e)
    return out


def build_frame_graph(edges: List[FrameEdge]) -> FrameGraph:
    """A FrameGraph from candidate edges: keep ONLY safe edges; preserve the rejected
    conflicts for inspection. Ambiguous / conflicting evidence is never translatable."""
    return FrameGraph(edges=safe_edges(edges), conflicts=detect_conflicts(edges))


def translate_station_ft(graph: FrameGraph, from_frame: FrameId, to_frame: FrameId,
                         feet: float) -> Optional[float]:
    """Translate a station (ft) from ``from_frame`` into ``to_frame`` THROUGH a SAFE
    edge. Same frame -> identity. Otherwise returns the translated feet via a safe
    forward (``feet - offset``) or reverse (``feet + offset``) edge, or **None** when
    no safe edge connects the pair -- the caller must ABSTAIN, never fall back to
    ``feet`` (a raw equal station value across frames is not proof of anything)."""
    if str(from_frame) == str(to_frame):
        return feet
    for e in graph.edges:
        if str(e.from_frame) == str(from_frame) and str(e.to_frame) == str(to_frame):
            return round(feet - e.offset_ft, 2)
        if str(e.from_frame) == str(to_frame) and str(e.to_frame) == str(from_frame):
            return round(feet + e.offset_ft, 2)
    return None


def translate_between_sheets(graph: FrameGraph, from_sheet: int, to_sheet: int,
                             feet: float) -> Optional[float]:
    """Translate a station (ft) from ``from_sheet``'s frame into ``to_sheet``'s frame
    through a SAFE direct frame edge -- the sheet-keyed convenience over
    ``translate_station_ft`` for the chain-assembly callers. Same sheet -> identity
    (the raw value). Returns **None** when no safe direct edge connects the two sheets
    (ambiguous / conflicting / missing edge): the caller must abstain and must NEVER
    fall back to the raw value (a raw equal station across sheets is not proof)."""
    return translate_station_ft(graph, frame_for_sheet(from_sheet),
                                frame_for_sheet(to_sheet), feet)
