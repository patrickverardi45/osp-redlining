r"""Matchline cross-sheet join laws (GENERAL; proven by M8.14.b.9/b.10,
re-homed for the M8.14.c lane). No plan-set knowledge -- matchline layer
names and equation formats are injected/parsed upstream.

  * A join is PROVEN only when every clause is printed or drawn: bound
    structure per sheet, chains terminating at drawn matchlines, ONE printed
    frame equation typeset at both boundaries, a shared printed boundary
    station, footage closure, and agreeing implied scales.
  * Boundary anchors derive from the chain's terminal dash extended along its
    OWN drawn direction to the matchline centerline, capped at the dash-gap
    constant (a dashed line includes its gaps; nothing more).
"""
from __future__ import annotations

import math
import re
from typing import List, Optional, Sequence, Tuple

from truelinev2.extract.conduit_topology import MAX_DASH_GAP

PROVEN = "CROSS_SHEET_CONTINUATION_PROVEN"
NOT_PROVEN = "CROSS_SHEET_CONTINUATION_NOT_PROVEN"
JOIN_SCALE_REL_TOL = 0.05   # the two implied scales must AGREE tightly

PROVEN_LAW = ("bound structure per sheet + chain terminates at its drawn "
              "matchline + ONE printed frame equation typeset at both "
              "matchlines + shared boundary station + footage closure with "
              "agreeing implied scales")

_FOOTAGE = re.compile(r"\((\d+(?:,\d{3})?)'\)")
# Any printed run callout -- the structural delimiter between note blocks
# (a note never contains two run callouts; the next callout starts the next
# note, so a footage printed past it belongs to THAT note, never this one).
_CALLOUT_LINE = re.compile(r"STA\s*\d+\+\d+\s*TO\s*(?:STA\s*)?\d+\+\d+", re.I)


def _note_footage(lines: Sequence[str], i: int) -> Optional[float]:
    """First printed footage within callout line ``i``'s OWN note block:
    scanned forward from the callout line, stopping at the next run-callout
    line. Replaces the older fixed 3-line window, which both missed footages
    printed deeper in the same note (descriptor lines between) and could
    grab the NEXT note's footage when the blocks ran short -- the note
    delimiter is structural, not a line count."""
    for j in range(i, len(lines)):
        if j > i and _CALLOUT_LINE.search(lines[j]):
            return None
        m = _FOOTAGE.search(lines[j])
        if m:
            return float(m.group(1).replace(",", ""))
    return None


def nearest_gap(points: Sequence[Tuple[float, float]],
                bbox: Tuple[float, float, float, float]) -> Optional[float]:
    """Min distance from any point to a bbox (0 inside). None without points."""
    best = None
    for x, y in points:
        dx = max(bbox[0] - x, 0.0, x - bbox[2])
        dy = max(bbox[1] - y, 0.0, y - bbox[3])
        d = math.hypot(dx, dy)
        best = d if best is None or d < best else best
    return best


def matchline_bboxes(drawings: Sequence[dict], layer: str,
                     min_len: float = 100.0) -> List[Tuple[float, float, float, float]]:
    """The sheet's drawn boundary lines: long thin drawings on the matchline
    layer (length floor excludes legend ticks; injected layer name)."""
    out = []
    for d in drawings:
        if d.get("layer") != layer:
            continue
        w, h = d["x1"] - d["x0"], d["y1"] - d["y0"]
        if max(w, h) >= min_len and min(w, h) <= 6.0:
            out.append((d["x0"], d["y0"], d["x1"], d["y1"]))
    return out


def find_run_callout_footage(lines: Sequence[str], start_sta: str,
                             end_sta: str) -> Optional[float]:
    """Printed footage of the run callout ``STA <a> TO [STA] <b> ... (NNN')``
    -- footage searched within the callout's own note block."""
    pat = re.compile(rf"STA\s*{re.escape(start_sta)}\s*TO\s*(?:STA\s*)?"
                     rf"{re.escape(end_sta)}\b", re.I)
    for i, ln in enumerate(lines):
        if not pat.search(ln):
            continue
        f = _note_footage(lines, i)
        if f is not None:
            return f
    return None


def _note_text(lines: Sequence[str], i: int) -> str:
    """Callout line ``i``'s OWN note block text (same delimiter law as
    ``_note_footage``): the callout line plus following lines up to the next
    run-callout line."""
    out = [lines[i]]
    for j in range(i + 1, len(lines)):
        if _CALLOUT_LINE.search(lines[j]):
            break
        out.append(lines[j])
    return " ".join(out)


def run_callouts_starting_at(lines: Sequence[str], start_sta: str
                             ) -> List[Tuple[str, Optional[float], str]]:
    """EVERY printed run callout STARTING at ``start_sta``, in print order,
    as (end station raw, note footage or None, note text). The uniqueness-
    mandatory callers decide; this only reports what is printed."""
    pat = re.compile(rf"STA\s*{re.escape(start_sta)}\s*TO\s*(?:STA\s*)?"
                     rf"(\d+\+\d+)\b", re.I)
    return [(m.group(1), _note_footage(lines, i), _note_text(lines, i))
            for i, ln in enumerate(lines) if (m := pat.search(ln))]


def run_callouts_ending_at(lines: Sequence[str], end_sta: str
                           ) -> List[Tuple[str, Optional[float], str]]:
    """EVERY printed run callout ENDING at ``end_sta``, in print order, as
    (start station raw, note footage or None, note text)."""
    pat = re.compile(rf"STA\s*(\d+\+\d+)\s*TO\s*(?:STA\s*)?"
                     rf"{re.escape(end_sta)}\b", re.I)
    return [(m.group(1), _note_footage(lines, i), _note_text(lines, i))
            for i, ln in enumerate(lines) if (m := pat.search(ln))]


def find_run_callout_from(lines: Sequence[str], start_sta: str
                          ) -> Optional[Tuple[str, float]]:
    """(end station raw, footage) of the printed run callout STARTING at
    ``start_sta`` -- the printed statement of where this sheet's segment of
    the run goes (its far side is the boundary candidate)."""
    for raw, f, _ in run_callouts_starting_at(lines, start_sta):
        if f is not None:
            return raw, f
    return None


def find_run_callout_to(lines: Sequence[str], end_sta: str
                        ) -> Optional[Tuple[str, float]]:
    """(start station raw, footage) of the printed run callout ENDING at
    ``end_sta`` -- its near side is the boundary candidate."""
    for raw, f, _ in run_callouts_ending_at(lines, end_sta):
        if f is not None:
            return raw, f
    return None


def cross_sheet_join_verdict(*, equation_edge: bool, eq_at_matchline_a: bool,
                             eq_at_matchline_b: bool, chain_a_reaches: bool,
                             chain_b_reaches: bool, seg_a_ft: Optional[float],
                             seg_b_ft: Optional[float], span_ft: float,
                             scale_a: Optional[float], scale_b: Optional[float],
                             rel_tol: float = JOIN_SCALE_REL_TOL) -> dict:
    """The join law as a pure decision. Any missing clause -> NOT_PROVEN with
    the exact missing artifact named; nothing is ever inferred to fill a gap."""
    missing = []
    if not equation_edge:
        missing.append("a printed matchline frame equation joining the two "
                       "sheets (frame-graph HIGH edge)")
    if not (eq_at_matchline_a and eq_at_matchline_b):
        missing.append("the equation text typeset AT both drawn matchlines")
    if not chain_a_reaches:
        missing.append("sheet A's conduit chain terminating at its matchline")
    if not chain_b_reaches:
        missing.append("sheet B's conduit chain terminating at its matchline")
    if seg_a_ft is None or seg_b_ft is None:
        missing.append("printed run-callout footages on both sheets")
    elif abs((seg_a_ft + seg_b_ft) - span_ft) > 0.5:
        missing.append(f"footage closure (printed {seg_a_ft}+{seg_b_ft} != "
                       f"bore span {span_ft})")
    if scale_a is None or scale_b is None or scale_a <= 0:
        missing.append("drawn structure->matchline distances on both sheets")
    elif abs(scale_a - scale_b) / scale_a > rel_tol:
        missing.append(f"implied-scale agreement (sheet A {scale_a:.4f} vs "
                       f"sheet B {scale_b:.4f} pt/ft)")
    if missing:
        return {"verdict": NOT_PROVEN, "named_missing": "; ".join(missing)}
    return {"verdict": PROVEN, "law": PROVEN_LAW}


def extend_dash_to_boundary(chain: Sequence[dict],
                            ml_bbox: Tuple[float, float, float, float],
                            max_gap: float = MAX_DASH_GAP
                            ) -> Optional[Tuple[float, float]]:
    """The chain's terminal dash, extended along its OWN drawn direction to
    the matchline centerline. Returns None (refusal) when no dash endpoint is
    within ``max_gap`` of the boundary -- a dashed line includes its gaps,
    nothing more. Works for vertical or horizontal matchlines. Dashes drawn
    as outline rectangles resolve via the long axis (caps are parallel and
    skipped; diagonals overrun; minimal-extension selection, deterministic)."""
    vertical = (ml_bbox[3] - ml_bbox[1]) >= (ml_bbox[2] - ml_bbox[0])
    target = ((ml_bbox[0] + ml_bbox[2]) / 2.0 if vertical
              else (ml_bbox[1] + ml_bbox[3]) / 2.0)
    best = None  # (extension, gap, candidate point)
    for seg in chain:
        for ln in seg.get("lines") or ():
            for p, q in (((ln[0], ln[1]), (ln[2], ln[3])),
                         ((ln[2], ln[3]), (ln[0], ln[1]))):
                gap = nearest_gap([p], ml_bbox)
                if gap is None or gap > max_gap:
                    continue
                dx, dy = p[0] - q[0], p[1] - q[1]  # direction toward boundary
                if (vertical and dx == 0) or (not vertical and dy == 0):
                    continue  # parallel to the matchline: cannot cross it
                if vertical:
                    t = (target - p[0]) / dx
                    cand = (target, p[1] + dy * t)
                else:
                    t = (target - p[1]) / dy
                    cand = (p[0] + dx * t, target)
                ext = math.hypot(cand[0] - p[0], cand[1] - p[1])
                if ext > max_gap:
                    continue  # oblique overrun longer than a dash gap: refuse
                if best is None or (ext, gap) < (best[0], best[1]):
                    best = (ext, gap, cand)
    return best[2] if best else None


def joined_segments_verdict(*, boundary_a_ft: float, boundary_b_ft: float,
                            seg_a_ft: float, seg_b_ft: float,
                            span_ft: float) -> dict:
    """Two sheet-local strokes join iff they share the SAME printed boundary
    station and their printed footages close the bore span exactly."""
    okb = boundary_a_ft == boundary_b_ft
    okf = abs((seg_a_ft + seg_b_ft) - span_ft) <= 0.5
    return {"joined": okb and okf,
            "shared_boundary_ft": boundary_a_ft if okb else None,
            "footage_closure": okf}
