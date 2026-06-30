"""Read-only PLAN-VIEW anchor resolver (gate G-a'): upgrade a printed station LABEL to a source-backed
structure/route anchor when the drawn evidence UNIQUELY supports it -- else refuse. Name-free; no axis; never
snaps blindly to the nearest line; never draws/places/promotes; ``class_verified`` always False.

WHY
G-a (``printed_station_locator``) locates the printed station LABEL in 2-D. G-b (``plan_view_run_observer``)
proved the label CENTROID is the wrong anchor for run verification -- on the real proof case it sat 16-40 pt off
the drawn route. The honest anchor for a redline is the SOURCE-BACKED point the label refers to, resolved in
strict priority:
  1. the structure SYMBOL its own leader points at (reuses the proven ``leader_symbol_trace`` chain);
  2. the LEADER TIP, when a unique leader exits the label box but no compact symbol is drawn at the tip;
  3. a unique nearby compact SYMBOL, when there is no leader evidence at all;
  4. a unique route TERMINUS (a drawn line END at the label), when nothing above resolves.
Every tier is uniqueness-mandatory: two plausible candidates -> ``AMBIGUOUS_ANCHOR`` (never chosen between). A
line merely PASSING near the label is NOT an anchor (no terminus there) -> no arbitrary nearest-line snapping.

NOT
- No class verification (the cold lane has no CAD layer/class table) -> ``class_verified`` always False; this
  never unblocks AUTO. Resolving an anchor proves WHERE the endpoint is, not a placement and not a drawn redline.
- Reads only ``PlanPdf.words`` / ``line_items`` / ``vector_segments`` + the read-only G-a/leader-trace helpers.
  Imports NOTHING from contracts/match/render/api/store/placement; no ``_cap_review``; mutates nothing.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from truelinev2.extract.leader_symbol_trace import (
    AMBIGUOUS_LEADER,
    AMBIGUOUS_SYMBOL,
    LABEL_ONLY_NO_SYMBOL,
    LEADER_TRACED_SYMBOL,
    _symbol_centroids,
    trace_label_to_symbol,
)
from truelinev2.extract.printed_station_locator import (
    AMBIGUOUS_STATION_LABEL,
    locate_printed_station,
)
from truelinev2.ingest.pdf import PlanPdf

# --- resolution statuses -------------------------------------------------------------------------------- #
ANCHOR_RESOLVED_TO_SYMBOL = "ANCHOR_RESOLVED_TO_SYMBOL"           # leader-traced symbol OR a unique nearby symbol
ANCHOR_RESOLVED_TO_LEADER_TIP = "ANCHOR_RESOLVED_TO_LEADER_TIP"   # unique leader off the label box, no symbol at tip
ANCHOR_RESOLVED_TO_ROUTE_ENDPOINT = "ANCHOR_RESOLVED_TO_ROUTE_ENDPOINT"  # a unique drawn route terminus at the label
LABEL_ONLY_NO_ANCHOR = "LABEL_ONLY_NO_ANCHOR"                     # linework near but no source-supported anchor
AMBIGUOUS_ANCHOR = "AMBIGUOUS_ANCHOR"                             # >= 2 plausible anchors at a tier
NO_SUPPORTED_ANCHOR = "NO_SUPPORTED_ANCHOR"                       # no drawn linework near the label at all
UNMEASURABLE = "UNMEASURABLE"                                     # the printed station label itself is not located

_SYMBOL_RADIUS = 18.0       # a structure symbol drawn next to its label
_ROUTE_RADIUS = 18.0        # a route terminus drawn at its label
_WELD_EPS = 7.0             # node-identity tolerance (matches the run observer)
_RESOLVED = (ANCHOR_RESOLVED_TO_SYMBOL, ANCHOR_RESOLVED_TO_LEADER_TIP, ANCHOR_RESOLVED_TO_ROUTE_ENDPOINT)

_NOTES = (
    "the anchor is a source-backed structure/route point, not the label centroid and not the nearest line",
    "uniqueness-mandatory at every tier; ambiguous evidence -> AMBIGUOUS_ANCHOR (never chosen between)",
    "class_verified always False -> a resolved anchor is evidence, never a placement / drawn redline / AUTO",
)


@dataclass(frozen=True)
class AnchorResolution:
    """A read-only resolved anchor (or refusal). ``x``/``y`` set only when resolved. ``method`` records HOW it
    resolved (LEADER_TRACED_SYMBOL / LEADER_TIP / PROXIMITY_SYMBOL / ROUTE_TERMINUS)."""
    status: str
    x: Optional[float]
    y: Optional[float]
    method: Optional[str]
    class_verified: bool
    detail: Dict[str, Any] = field(default_factory=dict)
    notes: Tuple[str, ...] = _NOTES

    @property
    def resolved(self) -> bool:
        return self.status in _RESOLVED

    def to_dict(self) -> dict:
        return {"status": self.status, "x": self.x, "y": self.y, "method": self.method,
                "class_verified": self.class_verified, "detail": self.detail}


def _res(status, xy, method, detail) -> AnchorResolution:
    x, y = (float(xy[0]), float(xy[1])) if xy is not None else (None, None)
    return AnchorResolution(status, x, y, method, False, detail)


class _UF:
    def __init__(self, n: int):
        self.p = list(range(n))

    def find(self, i: int) -> int:
        while self.p[i] != i:
            self.p[i] = self.p[self.p[i]]
            i = self.p[i]
        return i

    def union(self, i: int, j: int) -> None:
        ri, rj = self.find(i), self.find(j)
        if ri != rj:
            self.p[ri] = rj


def _flatten(line_items: Sequence[Dict[str, Any]]) -> List[Tuple[float, float, float, float]]:
    out: List[Tuple[float, float, float, float]] = []
    for it in line_items:
        for ln in (it.get("lines") or ()):
            ax, ay, bx, by = ln
            out.append((float(ax), float(ay), float(bx), float(by)))
    return out


def _seg_point_dist(seg: Tuple[float, float, float, float], p: Tuple[float, float]) -> float:
    ax, ay, bx, by = seg
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(p[0] - ax, p[1] - ay)
    t = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(p[0] - (ax + t * dx), p[1] - (ay + t * dy))


def _linework_near(segs: Sequence[Tuple[float, float, float, float]], p: Tuple[float, float],
                   radius: float) -> bool:
    return any(_seg_point_dist(s, p) <= radius for s in segs)


def _route_termini_near(segs: Sequence[Tuple[float, float, float, float]], p: Tuple[float, float],
                        radius: float, weld_eps: float) -> List[Tuple[float, float]]:
    """Drawn line TERMINI (degree-1 nodes — a route ENDS there, not passes through) within ``radius`` of ``p``.
    A line passing near ``p`` has no endpoint near it -> not a terminus -> not an anchor (no nearest-line snap)."""
    gather = radius + 30.0
    near = [(ax, ay, bx, by) for (ax, ay, bx, by) in segs
            if math.hypot(ax - p[0], ay - p[1]) <= gather or math.hypot(bx - p[0], by - p[1]) <= gather]
    pts: List[Tuple[float, float]] = []
    sp: List[Tuple[int, int]] = []
    for ax, ay, bx, by in near:
        i = len(pts); pts.append((ax, ay))
        j = len(pts); pts.append((bx, by))
        sp.append((i, j))
    if not pts:
        return []
    uf = _UF(len(pts)); e2 = weld_eps * weld_eps
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            if (pts[i][0] - pts[j][0]) ** 2 + (pts[i][1] - pts[j][1]) ** 2 <= e2:
                uf.union(i, j)
    cen: Dict[int, List[float]] = {}
    for idx in range(len(pts)):
        r = uf.find(idx)
        acc = cen.setdefault(r, [0.0, 0.0, 0.0])
        acc[0] += pts[idx][0]; acc[1] += pts[idx][1]; acc[2] += 1.0
    coord = {r: (a[0] / a[2], a[1] / a[2]) for r, a in cen.items()}
    deg: Dict[int, int] = {r: 0 for r in coord}
    for i, j in sp:
        ri, rj = uf.find(i), uf.find(j)
        if ri != rj:
            deg[ri] += 1; deg[rj] += 1
    return [coord[r] for r in coord
            if deg[r] == 1 and math.hypot(coord[r][0] - p[0], coord[r][1] - p[1]) <= radius]


def resolve_label_anchor(words: Sequence[Dict[str, Any]], line_items: Sequence[Dict[str, Any]],
                         shapes: Sequence[Dict[str, Any]], *, label_token: str,
                         label_xy: Tuple[float, float], symbol_radius: float = _SYMBOL_RADIUS,
                         route_radius: float = _ROUTE_RADIUS, weld_eps: float = _WELD_EPS) -> AnchorResolution:
    """Resolve a located station label to a source-backed anchor. Reads geometry only; never draws/places."""
    detail: Dict[str, Any] = {"label_xy": [round(label_xy[0], 1), round(label_xy[1], 1)]}

    # Tier 1 — leader-traced symbol / leader tip (the proven, strongest evidence).
    xy, sub, t1 = trace_label_to_symbol(words, line_items, shapes, label_tokens=[label_token])
    detail["leader_trace"] = sub
    if sub == LEADER_TRACED_SYMBOL:
        return _res(ANCHOR_RESOLVED_TO_SYMBOL, xy, "LEADER_TRACED_SYMBOL", detail)
    if sub in (AMBIGUOUS_LEADER, AMBIGUOUS_SYMBOL):
        return _res(AMBIGUOUS_ANCHOR, None, None, detail)
    if sub == LABEL_ONLY_NO_SYMBOL and t1.get("leader_tip") is not None:
        return _res(ANCHOR_RESOLVED_TO_LEADER_TIP, tuple(t1["leader_tip"]), "LEADER_TIP", detail)

    # Tier 2 — a unique nearby compact structure symbol (no leader evidence at all).
    syms = [c for c in _symbol_centroids(shapes)
            if math.hypot(c[0] - label_xy[0], c[1] - label_xy[1]) <= symbol_radius]
    detail["proximity_symbols"] = len(syms)
    if len(syms) == 1:
        return _res(ANCHOR_RESOLVED_TO_SYMBOL, syms[0], "PROXIMITY_SYMBOL", detail)
    if len(syms) >= 2:
        return _res(AMBIGUOUS_ANCHOR, None, None, detail)

    # Tier 3 — a unique route terminus drawn at the label.
    segs = _flatten(line_items)
    termini = _route_termini_near(segs, label_xy, route_radius, weld_eps)
    detail["route_termini"] = len(termini)
    if len(termini) == 1:
        return _res(ANCHOR_RESOLVED_TO_ROUTE_ENDPOINT, termini[0], "ROUTE_TERMINUS", detail)
    if len(termini) >= 2:
        return _res(AMBIGUOUS_ANCHOR, None, None, detail)

    # nothing resolved: distinguish "linework present but unanchorable" from "no drawn evidence near".
    if _linework_near(segs, label_xy, route_radius):
        return _res(LABEL_ONLY_NO_ANCHOR, None, None, detail)
    return _res(NO_SUPPORTED_ANCHOR, None, None, detail)


def resolve_plan_view_anchor_for_path(plan_path: str, sheet: int, station_ft: float, *, offset: int = 0,
                                      symbol_radius: float = _SYMBOL_RADIUS, route_radius: float = _ROUTE_RADIUS,
                                      weld_eps: float = _WELD_EPS) -> AnchorResolution:
    """Open a plan read-only, locate the printed station label (G-a), then resolve a source-backed anchor for it.
    Opens + closes the PDF; writes nothing; runs no placement/render."""
    plan = PlanPdf(str(plan_path))
    try:
        words = plan.words(int(sheet), int(offset))
        loc = locate_printed_station(words, float(station_ft))
        if loc.status == AMBIGUOUS_STATION_LABEL:
            return _res(AMBIGUOUS_ANCHOR, None, None, {"label_status": loc.status})
        if not loc.located:
            return _res(UNMEASURABLE, None, None, {"label_status": loc.status})
        return resolve_label_anchor(
            words, plan.line_items(int(sheet), int(offset)), plan.vector_segments(int(sheet), int(offset)),
            label_token=str(loc.text), label_xy=(float(loc.x), float(loc.y)),
            symbol_radius=symbol_radius, route_radius=route_radius, weld_eps=weld_eps)
    finally:
        plan.close()
