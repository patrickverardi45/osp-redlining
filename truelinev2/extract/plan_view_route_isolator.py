"""Read-only PLAN-VIEW route-layer / route-linework isolation for COLD / non-recognized packages (gate G-b').

The continued-95/96 cold-package arc proved two prerequisite gates for drawing a real cold redline:
  * G-a  (``printed_station_locator``)    -- resolve a bound station to its 2-D printed-label position.
  * G-a' (``plan_view_anchor_resolver``)  -- upgrade that label to a SOURCE-BACKED anchor (leader/symbol/terminus).
  * G-b  (``plan_view_run_observer``)     -- verify a single clean drawn run connects two located anchors.

On the real proof case G-a' and G-b BOTH honestly REFUSED: the route's printed station labels are framed by the
permit's grid / table boxes (each word framed by several drawings) and the route is offset from the labels, so no
clean anchor resolves and no unique connecting run can be verified. The drawn linework is tangled with grid,
border, title-block, label-box, leader and annotation linework, and the cold lane has NO CAD layer to isolate the
route by. **This gate is the missing step between G-a'/G-b and a cold REVIEW stroke (G-e):** given two
source-supported anchors, separate route-like linework from grid / border / box / annotation enough that a unique
connecting run becomes measurable -- and REFUSE (never guess, never snap, never strip) when it cannot.

What it does (read-only, refusal-first):
  * classify each drawing as ROUTE_CANDIDATE vs a closed GRID/BOX (table cell, label frame, title block) vs a
    PAGE_FRAME, and drop word-adjacent short leader / annotation-tick segments;
  * reuse G-b's proven ``observe_run_between_anchors`` weld/graph VERBATIM on (a) the route-isolated segment set
    and (b) the full segment set, and compare them to detect a connection that exists ONLY through grid/border
    artifacts;
  * report ``ROUTE_LINEWORK_ISOLATED`` only when exactly one simple route run connects both anchors tightly with
    no rival / fork / box-bridge -- otherwise a NAMED refusal.

What it does NOT do (reported, never faked):
  * NEVER draws a redline / stroke; NEVER places; NEVER promotes to AUTO. ``class_verified`` is ALWAYS False, so
    an isolated route is REVIEW evidence, never a placement or a drawn redline. (G-e draws the cold REVIEW stroke
    and is a separate, later, owner-approved gate.)
  * NEVER snaps to the nearest line as truth; NEVER strips cycles to manufacture a clean route. When grid/box
    linework is tangled with the route and cannot be conservatively separated, it REFUSES
    (``ROUTE_LAYER_AMBIGUOUS`` / ``GRID_OR_BORDER_ONLY``) rather than sculpt the data.
  * NO class verification; NO invented coordinate, station, or bore value.

Pure geometry over ``PlanPdf.line_items`` (+ optional ``words`` / page bounds) and the read-only G-a / G-b
observers. No I/O beyond opening the PDF in the path wrapper; no mutation; no contracts / match / render / api /
store / placement import; no ``_cap_review``.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from truelinev2.extract.plan_view_run_observer import (
    BROKEN_RUN as _RUN_BROKEN,
    ENDPOINT_NOT_TIGHT as _RUN_ENDPOINT_NOT_TIGHT,
    FORKED_RUN as _RUN_FORKED,
    MULTIPLE_PLAUSIBLE_RUNS as _RUN_MULTIPLE,
    NO_DRAWN_RUN as _RUN_NO_DRAWN,
    PLAN_VIEW_RUN_CONNECTED as _RUN_CONNECTED,
    UNMEASURABLE as _RUN_UNMEASURABLE,
    observe_run_between_anchors,
)
from truelinev2.extract.printed_station_locator import observe_plan_view_endpoints
from truelinev2.ingest.pdf import PlanPdf

# --- route-layer isolation verdicts (the diagnostics this gate exposes) --------------------------------- #
ROUTE_LINEWORK_ISOLATED = "ROUTE_LINEWORK_ISOLATED"     # one simple route run whose two ENDS are the two anchors,
#                                                          tight, with no rival / fork / box-bridge / dangling stub /
#                                                          tail past an anchor -> the only non-reject
NO_ROUTE_LINEWORK = "NO_ROUTE_LINEWORK"                 # no route-like linework forms a connected candidate at all
GRID_OR_BORDER_ONLY = "GRID_OR_BORDER_ONLY"            # linework near the anchors is grid/border/box; any span is
#                                                          through those artifacts, not a route
MULTIPLE_ROUTE_CANDIDATES = "MULTIPLE_ROUTE_CANDIDATES"  # >= 2 distinct route runs span both anchors (rival/parallel)
ROUTE_ENDPOINT_NOT_TIGHT = "ROUTE_ENDPOINT_NOT_TIGHT"  # a route candidate exists but does not reach an anchor (tol)
ROUTE_LAYER_AMBIGUOUS = "ROUTE_LAYER_AMBIGUOUS"        # the route cannot be conservatively separated (forks / tangled
#                                                          with grid) -> refuse rather than strip/guess
UNMEASURABLE = "UNMEASURABLE"                           # an endpoint anchor is not located -> nothing to isolate against

# --- per-drawing classification (diagnostic only) ------------------------------------------------------- #
CAT_ROUTE = "ROUTE_CANDIDATE"
CAT_BOX = "GRID_OR_BOX"          # a closed rectangle / loop: table cell, label frame, title block, grid path
CAT_FRAME = "PAGE_FRAME"         # a single drawing spanning most of the page: sheet border / frame

# --- geometry constants (display points; mirror the generic lane + G-b so behavior is consistent) ------- #
_MIN_SEG_PT = 3.0          # drop sub-pixel speckle before any analysis (= generic_geometry._MIN_SEG_PT)
_WELD_EPS_PT = 7.0         # node-identity tolerance (= the generic lane + G-b weld eps)
_REACH_TOL_PT = 12.0       # anchor-to-run 2-D gap for a run to "reach" an endpoint (= G-b _REACH_TOL_PT)
_FRAME_COVER_FRAC = 0.8    # a single drawing whose bbox covers >= this of BOTH page dims is a border / frame
_BOX_MIN_NODES = 3         # a closed loop (box) needs >= this many welded nodes (excludes a doubled single segment)
_LEADER_MAX_LEN_PT = 30.0  # only SHORT segments are leader / annotation-tick candidates (protects long route legs)
_LABEL_PAD_PT = 6.0        # endpoint within this of a printed-word bbox = label-attached (= leader-trace _BOX_MARGIN)

_NOTES = (
    "route-like linework is separated from closed grid/box and page-frame drawings and word-attached leader/tick "
    "segments; the connecting run is then verified from the isolated linework only -- no axis, no invented coordinate",
    "isolation is conservative + refusal-first: when grid/box linework is tangled with the route it REFUSES "
    "(ROUTE_LAYER_AMBIGUOUS / GRID_OR_BORDER_ONLY) and never strips cycles or snaps to the nearest line",
    "class_verified is always False -> an isolated route is REVIEW evidence, never a placement / drawn redline / AUTO; "
    "drawing the cold REVIEW stroke (G-e) is a separate, later, owner-approved gate",
)


@dataclass(frozen=True)
class RouteLayerObservation:
    """Read-only verdict over whether route-like linework can be isolated from grid/border/annotation and verified
    to connect two located endpoint anchors. Pure DATA -- confers no status, is never consumed by placement, and
    draws nothing. ``route_segments`` is the isolated route segment set (REVIEW evidence for a later gate, NOT a
    stroke); ``run_status`` is the underlying G-b verdict on that isolated set."""

    status: str
    would_reject: bool
    reject_signals: Tuple[str, ...]
    route_segments: Tuple[Dict[str, Any], ...]
    run_status: Optional[str]
    start_gap: Optional[float]
    end_gap: Optional[float]
    class_verified: bool                 # always False
    detail: Dict[str, Any] = field(default_factory=dict)
    notes: Tuple[str, ...] = ()

    def to_dict(self) -> dict:
        # deliberately omits the raw ``route_segments`` (carried as a count) and ``notes`` -- mirrors G-b.
        return {"status": self.status, "would_reject": self.would_reject,
                "reject_signals": list(self.reject_signals), "run_status": self.run_status,
                "route_segment_count": len(self.route_segments), "start_gap": self.start_gap,
                "end_gap": self.end_gap, "class_verified": self.class_verified, "detail": self.detail}


# --- pure geometry helpers ------------------------------------------------------------------------------ #
def _seg_len(ax: float, ay: float, bx: float, by: float) -> float:
    return math.hypot(bx - ax, by - ay)


def _drawing_lines(it: Dict[str, Any]) -> List[Tuple[float, float, float, float]]:
    """The straight-line items of one drawing as ``(ax, ay, bx, by)`` tuples (rect edges already exploded by
    ``PlanPdf.line_items``); speckle dropped. Empty when the drawing has no straight items (e.g. curves)."""
    out: List[Tuple[float, float, float, float]] = []
    for ln in it.get("lines") or ():
        ax, ay, bx, by = float(ln[0]), float(ln[1]), float(ln[2]), float(ln[3])
        if _seg_len(ax, ay, bx, by) >= _MIN_SEG_PT:
            out.append((ax, ay, bx, by))
    return out


def _drawing_bbox(it: Dict[str, Any], lines: Sequence[Tuple[float, float, float, float]]
                  ) -> Optional[Tuple[float, float, float, float]]:
    """The drawing's display-space bbox -- from ``line_items`` keys when present, else computed from its lines."""
    if all(k in it for k in ("x0", "y0", "x1", "y1")):
        return (float(it["x0"]), float(it["y0"]), float(it["x1"]), float(it["y1"]))
    if not lines:
        return None
    xs = [p for (ax, ay, bx, by) in lines for p in (ax, bx)]
    ys = [p for (ax, ay, bx, by) in lines for p in (ay, by)]
    return (min(xs), min(ys), max(xs), max(ys))


class _UF:
    """Tiny union-find for welding coincident endpoints (per-drawing closed-loop detection)."""

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


def _node_edge_count(lines: Sequence[Tuple[float, float, float, float]], eps: float) -> Tuple[int, int]:
    """Weld a drawing's own endpoints (within ``eps``) and count distinct nodes + non-degenerate edges. A closed
    rectangle / loop yields ``edges >= nodes``; an open route polyline yields ``edges == nodes - 1`` (a tree)."""
    pts: List[Tuple[float, float]] = []
    for (ax, ay, bx, by) in lines:
        pts.append((ax, ay))
        pts.append((bx, by))
    n = len(pts)
    if n == 0:
        return 0, 0
    uf = _UF(n)
    e2 = eps * eps
    for i in range(n):
        xi, yi = pts[i]
        for j in range(i + 1, n):
            xj, yj = pts[j]
            if (xi - xj) ** 2 + (yi - yj) ** 2 <= e2:
                uf.union(i, j)
    roots: Dict[int, int] = {}
    for i in range(n):
        r = uf.find(i)
        if r not in roots:
            roots[r] = len(roots)
    edges = 0
    for k in range(len(lines)):
        if roots[uf.find(2 * k)] != roots[uf.find(2 * k + 1)]:
            edges += 1
    return len(roots), edges


def _classify_drawing(lines: Sequence[Tuple[float, float, float, float]],
                      bbox: Optional[Tuple[float, float, float, float]],
                      page_bounds: Optional[Tuple[float, float, float, float]], weld_eps: float) -> str:
    """Conservative per-drawing category: PAGE_FRAME (spans the page) > GRID_OR_BOX (a closed loop) > ROUTE_CANDIDATE.
    Never classifies an open polyline as a box; a single segment is never a frame/box."""
    if not lines:
        return CAT_ROUTE  # nothing to contribute; harmless (no segments collected)
    if bbox is not None and page_bounds is not None:
        pw = abs(page_bounds[2] - page_bounds[0])
        ph = abs(page_bounds[3] - page_bounds[1])
        bw = abs(bbox[2] - bbox[0])
        bh = abs(bbox[3] - bbox[1])
        if pw > 0 and ph > 0 and bw >= _FRAME_COVER_FRAC * pw and bh >= _FRAME_COVER_FRAC * ph:
            return CAT_FRAME
    n_nodes, n_edges = _node_edge_count(lines, weld_eps)
    if n_nodes >= _BOX_MIN_NODES and n_edges >= n_nodes:
        return CAT_BOX
    return CAT_ROUTE


def _word_boxes(words: Optional[Sequence[Dict[str, Any]]]) -> List[Tuple[float, float, float, float]]:
    if not words:
        return []
    out: List[Tuple[float, float, float, float]] = []
    for w in words:
        try:
            out.append((float(w["x0"]), float(w["y0"]), float(w["x1"]), float(w["y1"])))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _endpoint_near_word(ax: float, ay: float, bx: float, by: float,
                        word_boxes: Sequence[Tuple[float, float, float, float]], pad: float) -> bool:
    for (x0, y0, x1, y1) in word_boxes:
        for (px, py) in ((ax, ay), (bx, by)):
            if x0 - pad <= px <= x1 + pad and y0 - pad <= py <= y1 + pad:
                return True
    return False


def _near_anchor(ax: float, ay: float, bx: float, by: float,
                 start_xy: Tuple[float, float], end_xy: Tuple[float, float], tol: float) -> bool:
    for (px, py) in ((ax, ay), (bx, by)):
        if math.hypot(px - start_xy[0], py - start_xy[1]) <= tol or \
                math.hypot(px - end_xy[0], py - end_xy[1]) <= tol:
            return True
    return False


def _grid_cluster_ids(pts: Sequence[Tuple[float, float]], eps: float) -> List[int]:
    """Cluster coincident points into dense node ids via a spatial hash (O(n) average; same weld as G-b)."""
    n = len(pts)
    uf = _UF(n)
    cell = max(eps, 1e-6)
    grid: Dict[Tuple[int, int], List[int]] = {}
    for i, (x, y) in enumerate(pts):
        grid.setdefault((int(x // cell), int(y // cell)), []).append(i)
    e2 = eps * eps
    for (cx, cy), idxs in grid.items():
        neigh: List[int] = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                neigh.extend(grid.get((cx + dx, cy + dy), ()))
        for a in idxs:
            xa, ya = pts[a]
            for b in neigh:
                if b <= a:
                    continue
                xb, yb = pts[b]
                if (xa - xb) ** 2 + (ya - yb) ** 2 <= e2:
                    uf.union(a, b)
    roots: Dict[int, int] = {}
    ids: List[int] = []
    for i in range(n):
        r = uf.find(i)
        if r not in roots:
            roots[r] = len(roots)
        ids.append(roots[r])
    return ids


def _isolated_run_is_simple_path(segments: Sequence[Dict[str, Any]], start_xy: Tuple[float, float],
                                 end_xy: Tuple[float, float], reach_tol: float, weld_eps: float) -> bool:
    """Confirm linework G-b verified as CONNECTED is a SIMPLE path whose two ENDS are the two anchors (within
    ``reach_tol``) -- no dangling stub off an anchor and no tail past an anchor. G-b's CONNECTED only forbids an
    INTERIOR degree>=3 junction or a cycle, so it admits a degree-2 anchor with extra linework hanging off it (a
    stub) or a chain end beyond an anchor (a tail); this stricter check refuses those, so ROUTE_LINEWORK_ISOLATED
    means a clean anchor-to-anchor route whose ``route_segments`` carry no extra strokes. Read-only; pure geometry."""
    pts: List[Tuple[float, float]] = []
    sp: List[Tuple[int, int]] = []
    for s in segments:
        a = s.get("a")
        b = s.get("b")
        if a is None or b is None:
            continue
        ia = len(pts)
        pts.append((float(a[0]), float(a[1])))
        ib = len(pts)
        pts.append((float(b[0]), float(b[1])))
        sp.append((ia, ib))
    if not sp:
        return False
    ids = _grid_cluster_ids(pts, weld_eps)
    n_nodes = max(ids) + 1
    sums: Dict[int, List[float]] = {}
    for idx, nid in enumerate(ids):
        acc = sums.setdefault(nid, [0.0, 0.0, 0.0])
        acc[0] += pts[idx][0]
        acc[1] += pts[idx][1]
        acc[2] += 1.0
    coord = {nid: (acc[0] / acc[2], acc[1] / acc[2]) for nid, acc in sums.items()}
    deg = [0] * n_nodes
    comp = _UF(n_nodes)
    for ia, ib in sp:
        na, nb = ids[ia], ids[ib]
        if na == nb:
            continue
        deg[na] += 1
        deg[nb] += 1
        comp.union(na, nb)
    groups: Dict[int, List[int]] = {}
    for nid in range(n_nodes):
        groups.setdefault(comp.find(nid), []).append(nid)

    def _reaches(nodes: List[int], p: Tuple[float, float]) -> bool:
        return min(math.hypot(coord[n][0] - p[0], coord[n][1] - p[1]) for n in nodes) <= reach_tol

    spanning = [nodes for nodes in groups.values() if _reaches(nodes, start_xy) and _reaches(nodes, end_xy)]
    if len(spanning) != 1:
        return False
    ends = [coord[n] for n in spanning[0] if deg[n] == 1]
    if len(ends) != 2:
        return False                      # a stub adds a 3rd end (or a lone point) -> not a simple two-ended path
    e0, e1 = ends

    def _gap(p: Tuple[float, float], q: Tuple[float, float]) -> float:
        return math.hypot(p[0] - q[0], p[1] - q[1])

    # each anchor must coincide with a DISTINCT chain end (within reach_tol): no interior anchor, no extra end
    direct = max(_gap(e0, start_xy), _gap(e1, end_xy))
    swapped = max(_gap(e1, start_xy), _gap(e0, end_xy))
    return min(direct, swapped) <= reach_tol


def observe_route_isolation(line_items: Sequence[Dict[str, Any]],
                            start_xy: Optional[Tuple[float, float]],
                            end_xy: Optional[Tuple[float, float]],
                            *, page_bounds: Optional[Tuple[float, float, float, float]] = None,
                            words: Optional[Sequence[Dict[str, Any]]] = None,
                            reach_tol: float = _REACH_TOL_PT,
                            weld_eps: float = _WELD_EPS_PT) -> RouteLayerObservation:
    """Isolate route-like linework between two source-supported anchors and verify it forms a unique connecting run.

    ``line_items`` is ``PlanPdf.line_items(...)`` (per-drawing dicts; the consumed key is ``lines``). ``start_xy`` /
    ``end_xy`` are the two anchors' display-space positions (from G-a / G-a'); ``None`` => ``UNMEASURABLE``. The
    isolated route segments are passed to G-b's ``observe_run_between_anchors`` VERBATIM; the same verifier is run on
    the FULL segment set so a connection that only exists through excluded grid/border artifacts is reported as
    ``GRID_OR_BORDER_ONLY``. Read-only; never draws/places/promotes; ``class_verified`` always False."""
    if start_xy is None or end_xy is None:
        return RouteLayerObservation(UNMEASURABLE, True, (UNMEASURABLE,), (), None, None, None, False,
                                     {"reason": "endpoint anchor(s) not located", "reach_tol": reach_tol}, _NOTES)

    word_boxes = _word_boxes(words)
    route_segs: List[Dict[str, Any]] = []      # isolated route-candidate segments ({"a","b"})
    full_segs: List[Dict[str, Any]] = []       # every drawn segment (the un-isolated view G-b would see)
    n_route = n_box = n_frame = 0
    leader_dropped = 0
    excluded_near = 0                          # excluded (box/frame/leader) segments near an anchor

    for it in line_items:
        lines = _drawing_lines(it)
        if not lines:
            continue
        bbox = _drawing_bbox(it, lines)
        cat = _classify_drawing(lines, bbox, page_bounds, weld_eps)
        if cat == CAT_BOX:
            n_box += 1
        elif cat == CAT_FRAME:
            n_frame += 1
        else:
            n_route += 1
        for (ax, ay, bx, by) in lines:
            seg = {"a": (ax, ay), "b": (bx, by)}
            full_segs.append(seg)
            if cat != CAT_ROUTE:
                if _near_anchor(ax, ay, bx, by, start_xy, end_xy, reach_tol):
                    excluded_near += 1
                continue
            # route-candidate drawing: drop word-attached short leader / annotation-tick segments.
            if word_boxes and _seg_len(ax, ay, bx, by) <= _LEADER_MAX_LEN_PT and \
                    _endpoint_near_word(ax, ay, bx, by, word_boxes, _LABEL_PAD_PT):
                leader_dropped += 1
                if _near_anchor(ax, ay, bx, by, start_xy, end_xy, reach_tol):
                    excluded_near += 1
                continue
            route_segs.append(seg)

    iso = observe_run_between_anchors(route_segs, start_xy, end_xy, reach_tol=reach_tol, weld_eps=weld_eps)
    full = observe_run_between_anchors(full_segs, start_xy, end_xy, reach_tol=reach_tol, weld_eps=weld_eps)

    bridged_by_artifacts = full.status == _RUN_CONNECTED  # the full sheet spans only via excluded linework

    simple_path: Optional[bool] = None
    if iso.status == _RUN_CONNECTED:
        # G-b says one acyclic non-junctioned run spans both anchors; require it also be a SIMPLE anchor-to-anchor
        # path (no dangling stub / no tail past an anchor) before declaring the route cleanly isolated.
        simple_path = _isolated_run_is_simple_path(route_segs, start_xy, end_xy, reach_tol, weld_eps)
        status = ROUTE_LINEWORK_ISOLATED if simple_path else ROUTE_LAYER_AMBIGUOUS
    elif iso.status == _RUN_MULTIPLE:
        status = MULTIPLE_ROUTE_CANDIDATES
    elif iso.status == _RUN_FORKED:
        status = ROUTE_LAYER_AMBIGUOUS
    elif iso.status == _RUN_UNMEASURABLE:
        status = UNMEASURABLE                              # defensive: anchors checked above
    elif bridged_by_artifacts:
        status = GRID_OR_BORDER_ONLY
    elif iso.status in (_RUN_BROKEN, _RUN_ENDPOINT_NOT_TIGHT):
        status = ROUTE_ENDPOINT_NOT_TIGHT
    elif iso.status == _RUN_NO_DRAWN and excluded_near > 0:
        status = GRID_OR_BORDER_ONLY                       # near-anchor linework existed but was all grid/border/box
    else:
        status = NO_ROUTE_LINEWORK

    would_reject = status != ROUTE_LINEWORK_ISOLATED
    detail = {
        "drawings_total": n_route + n_box + n_frame,
        "route_drawings": n_route, "box_drawings": n_box, "frame_drawings": n_frame,
        "leader_or_tick_dropped": leader_dropped,
        "full_segment_count": len(full_segs), "route_segment_count": len(route_segs),
        "excluded_near_anchor": excluded_near,
        "simple_path": simple_path,
        "iso_run": iso.status, "full_run": full.status,
        "iso_run_detail": iso.detail, "reach_tol": reach_tol, "weld_eps": weld_eps,
    }
    return RouteLayerObservation(status, would_reject, () if not would_reject else (status,),
                                 tuple(route_segs), iso.status, iso.start_gap, iso.end_gap, False, detail, _NOTES)


def observe_plan_view_route_for_path(plan_path: str, sheet: int, start_ft: float, end_ft: float,
                                     *, start_source_bound: bool, end_source_bound: bool, offset: int = 0,
                                     reach_tol: float = _REACH_TOL_PT
                                     ) -> Tuple[Any, RouteLayerObservation]:
    """End-to-end G-a -> G-b' driver: locate the two printed-station endpoints (G-a), then isolate the route
    linework between them and verify a unique connecting run. Returns ``(endpoint_observation, route_layer_obs)``.
    Opens + closes the PDF; writes nothing; runs no placement / render; ``class_verified`` always False.

    Note: the endpoints come from the printed-station LABEL positions (G-a). When the labels are offset from the
    drawn route (a common cold-package style), an isolated route can read ``ROUTE_ENDPOINT_NOT_TIGHT`` against the
    label centres -- the honest signal that a stronger anchor (G-a' route terminus / symbol) is needed; the
    isolated ``route_segments`` are the read-only input such a later composition would consume."""
    plan = PlanPdf(plan_path)
    try:
        ep = observe_plan_view_endpoints(plan, sheet, start_ft, end_ft,
                                         start_source_bound=start_source_bound,
                                         end_source_bound=end_source_bound, offset=offset)
        if not (ep.start.located and ep.end.located):
            obs = RouteLayerObservation(UNMEASURABLE, True, (UNMEASURABLE,), (), None, None, None, False,
                                        {"reason": "endpoint anchor(s) not located", "reach_tol": reach_tol}, _NOTES)
            return ep, obs
        line_items = plan.line_items(int(sheet), int(offset))
        words = plan.words(int(sheet), int(offset))
        page_bounds = plan.page_bounds_display(int(sheet), int(offset))
        obs = observe_route_isolation(line_items, (float(ep.start.x), float(ep.start.y)),
                                      (float(ep.end.x), float(ep.end.y)),
                                      page_bounds=page_bounds, words=words, reach_tol=reach_tol)
        return ep, obs
    finally:
        plan.close()
