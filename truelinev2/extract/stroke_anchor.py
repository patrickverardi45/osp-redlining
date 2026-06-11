r"""Symbol-anchored stroke laws (GENERAL; proven by M8.14.b.3/b.7, re-homed
for the M8.14.c lane). No plan-set knowledge.

  * Anchor ticks exist ONLY for POSITION_BOUND structure-position verdicts --
    a stroke may never be anchored to a label, a guess, or an unresolved
    endpoint (typed refusal).
  * The trimmed stroke must START/END exactly ON the anchor symbols.
  * Rival symbols are never stroke vertices; stroke endpoints never sit at
    identity label words (the r3-class failure).
"""
from __future__ import annotations

import math
from typing import Optional, Sequence, Tuple

from truelinev2.extract.structure_position import (
    POSITION_BOUND,
    StructurePositionVerdict,
)
from truelinev2.extract.tick_path import READY, Tick, TickPathVerdict

RIVAL_MIN_SEP = 25.0   # stroke vertices vs rival symbol centers
LABEL_MIN_SEP = 20.0   # stroke endpoints vs identity label WORD centers


def anchor_ticks_from_verdicts(start_v: StructurePositionVerdict,
                               end_v: StructurePositionVerdict,
                               start_ft: float, end_ft: float
                               ) -> Tuple[Optional[Tuple[Tick, Tick]], Optional[str]]:
    """Anchor ticks exist ONLY for POSITION_BOUND verdicts -- any other verdict
    refuses with the named relationship (never anchor to a label or a guess)."""
    for v in (start_v, end_v):
        if v.result != POSITION_BOUND or v.symbol_xy is None:
            return None, (f"endpoint {v.label_text!r} is {v.result}, not "
                          f"{POSITION_BOUND} -- a stroke may not be anchored to "
                          f"an unresolved position; "
                          f"{v.named_missing_relationship or 'no symbol'}")
    return (Tick(start_ft, start_v.symbol_xy[0], start_v.symbol_xy[1]),
            Tick(end_ft, end_v.symbol_xy[0], end_v.symbol_xy[1])), None


def stroke_endpoint_fidelity(verdict: TickPathVerdict,
                             start_xy: Tuple[float, float],
                             end_xy: Tuple[float, float], tol: float = 0.1) -> bool:
    """The trimmed stroke must START and END exactly at the anchor symbols
    (anchor stations equal the span bounds, so interpolation lands ON them)."""
    if verdict.result != READY or not verdict.stroke_points:
        return False
    (sx, sy), (ex, ey) = verdict.stroke_points[0], verdict.stroke_points[-1]
    return (math.hypot(sx - start_xy[0], sy - start_xy[1]) <= tol
            and math.hypot(ex - end_xy[0], ey - end_xy[1]) <= tol)


def rival_vertex_safety(stroke_points: Sequence[Tuple[float, float]],
                        rival_xys: Sequence[Tuple[float, float]],
                        min_sep: float = RIVAL_MIN_SEP) -> dict:
    """No stroke VERTEX may sit at a rival symbol -- rivals are never anchors
    and never interior points. Reports the worst separation exactly."""
    worst = None
    for p in stroke_points:
        for r in rival_xys:
            d = math.hypot(p[0] - r[0], p[1] - r[1])
            if worst is None or d < worst:
                worst = d
    return {"min_vertex_to_rival_pt": (round(worst, 1) if worst is not None else None),
            "min_sep_required": min_sep,
            "safe": worst is None or worst >= min_sep}


def label_offset_safety(endpoints: Sequence[Tuple[float, float]],
                        label_word_xys: Sequence[Tuple[float, float]],
                        min_sep: float = LABEL_MIN_SEP) -> dict:
    """Stroke ENDPOINTS must sit away from the identity label words -- ending a
    stroke at leader-offset text is the exact r3-class failure this lane bans."""
    worst = None
    for p in endpoints:
        for w in label_word_xys:
            if w is None:
                continue
            d = math.hypot(p[0] - w[0], p[1] - w[1])
            if worst is None or d < worst:
                worst = d
    return {"min_endpoint_to_label_pt": (round(worst, 1) if worst is not None else None),
            "min_sep_required": min_sep,
            "safe": worst is None or worst >= min_sep}
