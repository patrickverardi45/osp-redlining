"""Read-only LEADER-TRACED structure-coordinate resolver for COLD / non-recognized packages (name-free).

The continued-90 cold-lane ``TERMINUS_DRAWN_COORDINATE`` is geometry-only (a compact drawn shape at the
projected station-x). This resolver UPGRADES the provenance when the source supports it: a printed terminus
label whose own drawn LEADER LINE points at a unique drawn SYMBOL — the honest position per the r3 lesson
("a stroke may never be drawn to a label centroid; the only honest position is the symbol the leader points
at"). It mirrors the proven dialect chain in ``extract/structure_position.py`` (word -> label box -> leader ->
symbol) but LAYER-AGNOSTICALLY: ZERO CAD layer names, ZERO class fill colors — so it runs in the cold/generic
lane with no dialect layer table.

What it does NOT do (reported, never faked):
  * NO CLASS VERIFICATION. ``structure_position`` checks the symbol's fill against a dialect class color; that
    needs a layer/class table the cold lane does not have. This resolver locates WHERE a structure is drawn
    (the leader tip), not WHAT class it is — callers keep ``class_verified=False``. Generic class verification
    remains a NAMED MISSING capability.
  * NEVER the label / text centroid as a coordinate. NEVER a guess. Uniqueness-mandatory at every hop: 0 or
    >= 2 candidates -> a named non-promoting refusal.

Pure geometry over ``PlanPdf.words`` + ``PlanPdf.line_items`` + ``PlanPdf.vector_segments``. No I/O, no
mutation, no placement / render / contract import.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Leader-trace sub-statuses (the provenance ladder's strongest rung + its named refusals).
LEADER_TRACED_SYMBOL = "LEADER_TRACED_SYMBOL"   # unique label -> box -> leader -> symbol resolved
LABEL_ONLY_NO_SYMBOL = "LABEL_ONLY_NO_SYMBOL"   # label found but no leader/symbol resolves -> no coordinate
AMBIGUOUS_LEADER = "AMBIGUOUS_LEADER"           # >= 2 label words / boxes / leaders -> never chosen between
AMBIGUOUS_SYMBOL = "AMBIGUOUS_SYMBOL"           # >= 2 symbols at the leader tip -> never chosen between
NO_LEADER_EVIDENCE = "NO_LEADER_EVIDENCE"       # no label word on the sheet -> nothing to trace

# Probe-calibrated geometry constants — the SAME values as extract/structure_position.py (the proven dialect
# chain), restated here so this cold-lane resolver carries no dialect coupling. Name-free.
_LEADER_MIN_LEN = 8.0       # shorter same-region strokes are glyph work, not leaders
_BOX_MARGIN = 6.0           # endpoint-inside-box tolerance for leader attachment
_BOX_MIN_W = 10.0           # a label box is bigger than a glyph fill
_BOX_MIN_H = 6.0
_TIP_TOL = 8.0              # leader tip -> symbol center
_SYMBOL_MIN_DIM = 3.0       # a symbol has area in both dims
_SYMBOL_MAX_DIM = 25.0      # ...and is compact (not a long run line)
_SYMBOL_MAX_ASPECT = 2.0    # ...and roughly square -> excludes thin LEADER lines from symbol candidates


def _in_box(pt: Tuple[float, float], box: Tuple[float, float, float, float], m: float = _BOX_MARGIN) -> bool:
    return box[0] - m <= pt[0] <= box[2] + m and box[1] - m <= pt[1] <= box[3] + m


def _label_boxes(line_items: Sequence[Dict[str, Any]], word_xy: Tuple[float, float]) -> List[Dict[str, Any]]:
    """Layer-agnostic ``find_label_box``: drawings big enough to be a label FRAME whose bbox contains the
    identity word's center. Glyph fills fail the size floor; the layer filter is dropped (no dialect table)."""
    out = []
    for d in line_items:
        if (float(d["x1"]) - float(d["x0"])) < _BOX_MIN_W or (float(d["y1"]) - float(d["y0"])) < _BOX_MIN_H:
            continue
        if float(d["x0"]) <= word_xy[0] <= float(d["x1"]) and float(d["y0"]) <= word_xy[1] <= float(d["y1"]):
            out.append(d)
    return out


def _leaders(line_items: Sequence[Dict[str, Any]], box: Tuple[float, float, float, float]
             ) -> List[Tuple[float, float, float, float]]:
    """Layer-agnostic ``find_leaders``: line items with EXACTLY ONE endpoint at the box (xor) and length >=
    the floor. Box edges have both endpoints on the box (excluded); glyph strokes fail the length floor.
    Returned oriented (box end first); the tip is the far endpoint."""
    out: List[Tuple[float, float, float, float]] = []
    for d in line_items:
        for (ax, ay, bx, by) in d.get("lines") or ():
            a_in, b_in = _in_box((ax, ay), box), _in_box((bx, by), box)
            if a_in == b_in:
                continue
            if math.hypot(bx - ax, by - ay) < _LEADER_MIN_LEN:
                continue
            out.append((ax, ay, bx, by) if a_in else (bx, by, ax, ay))
    return out


def _symbol_centroids(shapes: Sequence[Dict[str, Any]]) -> List[Tuple[float, float]]:
    """Compact, roughly-SQUARE drawn shapes (a symbol/marker), as (xc, yc). The aspect bound excludes thin
    LEADER lines (which are compact in one dim but elongated) from being mistaken for the symbol they point
    at — so a leader can never count as the symbol at its own tip."""
    out = []
    for s in shapes:
        w = float(s["x1"]) - float(s["x0"]); h = float(s["y1"]) - float(s["y0"])
        if min(w, h) < _SYMBOL_MIN_DIM or max(w, h) > _SYMBOL_MAX_DIM:
            continue
        if max(w, h) > _SYMBOL_MAX_ASPECT * max(min(w, h), 1e-6):
            continue
        out.append((float(s["xc"]), float(s["yc"])))
    return out


def trace_label_to_symbol(words: Sequence[Dict[str, Any]], line_items: Sequence[Dict[str, Any]],
                          shapes: Sequence[Dict[str, Any]], *, label_tokens: Sequence[str],
                          tip_tol: float = _TIP_TOL
                          ) -> Tuple[Optional[Tuple[float, float]], str, Dict[str, Any]]:
    """Resolve a terminus label to its drawn symbol via its own leader, uniqueness-mandatory + layer-agnostic.

    Chain (every hop 0 or >=2 -> a named refusal): unique label word -> unique label box framing it -> unique
    leader off the box -> unique compact symbol at the leader tip. Returns ``(xy | None, sub_status, detail)``.
    ``xy`` is non-None ONLY for ``LEADER_TRACED_SYMBOL``. Never the label centroid; never a guess; no class check.
    """
    tokens = {str(t) for t in label_tokens if t}
    detail: Dict[str, Any] = {}
    hits = [w for w in words if str(w.get("text")) in tokens] if tokens else []
    detail["label_word_hits"] = len(hits)
    if not hits:
        return None, NO_LEADER_EVIDENCE, detail
    if len(hits) > 1:
        return None, AMBIGUOUS_LEADER, detail          # ambiguous label identity -> cannot isolate a trace
    w = hits[0]
    word_xy = (float(w["xc"]), float(w["yc"]))

    boxes = _label_boxes(line_items, word_xy)
    detail["label_box_hits"] = len(boxes)
    if not boxes:
        return None, LABEL_ONLY_NO_SYMBOL, detail       # a label but no drawn frame to leader from
    if len(boxes) > 1:
        return None, AMBIGUOUS_LEADER, detail
    b = boxes[0]
    box = (float(b["x0"]), float(b["y0"]), float(b["x1"]), float(b["y1"]))

    leaders = _leaders(line_items, box)
    detail["leader_hits"] = len(leaders)
    if not leaders:
        return None, LABEL_ONLY_NO_SYMBOL, detail        # a framed label but no leader exits it
    if len(leaders) > 1:
        return None, AMBIGUOUS_LEADER, detail
    tip = (leaders[0][2], leaders[0][3])
    detail["leader_tip"] = [round(tip[0], 1), round(tip[1], 1)]

    at_tip = [c for c in _symbol_centroids(shapes) if math.hypot(c[0] - tip[0], c[1] - tip[1]) <= tip_tol]
    detail["symbols_at_tip"] = len(at_tip)
    if not at_tip:
        return None, LABEL_ONLY_NO_SYMBOL, detail        # the leader points at no drawn symbol
    if len(at_tip) > 1:
        return None, AMBIGUOUS_SYMBOL, detail
    return at_tip[0], LEADER_TRACED_SYMBOL, detail
