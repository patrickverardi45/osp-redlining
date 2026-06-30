"""Read-only PLAN-VIEW drawn-run verification (gate G-b): does a single clean drawn run connect two located
endpoint anchors? Name-free; source-evidence-derived; strict refusal; no axis. Never draws, places, promotes,
or unblocks AUTO.

WHY THIS EXISTS
Gate G-a (``printed_station_locator``) resolves each source-bound endpoint to a 2-D anchor on a plan-view sheet
(no linear axis). That proves WHERE each endpoint is, not that the drawn line between them is the bore path.
G-b reconstructs the drawn linework near the two anchors and asks: is there exactly ONE simple drawn run that
connects them, tightly, with no rival/fork/break? It distinguishes a clean connecting run from every ambiguity
and refuses rather than guess.

HONEST SCOPE (reported, never papered over)
- The connecting run is verified from the drawn vector linework in the bore region. On a plan-view sheet with NO
  CAD layer to isolate the route (grid + border + annotation + route share one anonymous layer), multiple
  components can plausibly span the two anchors -> ``MULTIPLE_PLAUSIBLE_RUNS`` (a refusal), not a guess. Two
  later gates remove that ambiguity: structure-coordinate anchoring (trace each station label to its structure
  symbol so the anchor sits ON the run, not offset) and route-layer isolation. Until then this observer REFUSES
  on ambiguous geometry by design.
- ``class_verified`` is ALWAYS False -> never unblocks AUTO. A verified connecting run is REVIEW evidence, not a
  placement and not a drawn redline.

SAFETY
Read-only: imports only the read-only ``PlanPdf`` reader + the G-a locator. Imports NOTHING from
contracts/match/render/api/store/placement; no ``_cap_review``; mutates nothing; draws nothing.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from truelinev2.extract.printed_station_locator import observe_plan_view_endpoints
from truelinev2.ingest.pdf import PlanPdf

# --- verdicts ------------------------------------------------------------------------------------------- #
PLAN_VIEW_RUN_CONNECTED = "PLAN_VIEW_RUN_CONNECTED"   # exactly one simple drawn chain connects both anchors, tight
NO_DRAWN_RUN = "NO_DRAWN_RUN"                         # no drawn linework reaches either anchor
BROKEN_RUN = "BROKEN_RUN"                             # linework reaches BOTH anchors but no single run bridges them
MULTIPLE_PLAUSIBLE_RUNS = "MULTIPLE_PLAUSIBLE_RUNS"   # >= 2 distinct runs each span both anchors (rival / parallel)
FORKED_RUN = "FORKED_RUN"                             # the one spanning run branches (degree>=3 junction or a loop)
ENDPOINT_NOT_TIGHT = "ENDPOINT_NOT_TIGHT"            # a run reaches one anchor but not the other (within tol)
UNMEASURABLE = "UNMEASURABLE"                         # an endpoint anchor is not located -> nothing to verify against

_WELD_EPS_PT = 7.0          # node-identity tolerance (segments whose endpoints touch weld into one node)
_REACH_TOL_PT = 12.0        # max anchor-to-run-node 2-D gap for a run to "reach" an endpoint (= endpoint tightness)


@dataclass(frozen=True)
class PlanViewRunObservation:
    """Read-only verdict over the drawn linework between two located endpoint anchors. Pure DATA; confers no
    status; never consumed by placement. ``start_gap``/``end_gap`` are the nearest run-node 2-D distances to the
    anchors (None when not computable)."""
    status: str
    would_reject: bool
    reject_signals: Tuple[str, ...]
    start_gap: Optional[float]
    end_gap: Optional[float]
    class_verified: bool                 # always False
    detail: Dict[str, Any] = field(default_factory=dict)
    notes: Tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {"status": self.status, "would_reject": self.would_reject,
                "reject_signals": list(self.reject_signals), "start_gap": self.start_gap,
                "end_gap": self.end_gap, "class_verified": self.class_verified, "detail": self.detail}


_NOTES = (
    "the connecting run is verified from drawn vector linework in the bore region; no axis, no invented coordinate",
    "with no CAD layer to isolate the route, rival components can span the anchors -> MULTIPLE_PLAUSIBLE_RUNS (a "
    "refusal); structure-coordinate anchoring + route-layer isolation are later gates",
    "class_verified is always False -> a verified run is REVIEW evidence, never a placement / drawn redline / AUTO",
)


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


def _grid_cluster(pts: Sequence[Tuple[float, float]], eps: float) -> List[int]:
    """Cluster coincident endpoints into node ids via a spatial hash (O(n) average — safe on dense sheets,
    unlike an O(n^2) pairwise scan). Points within ``eps`` weld into one node."""
    uf = _UF(len(pts))
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
    for i in range(len(pts)):
        r = uf.find(i)
        if r not in roots:
            roots[r] = len(roots)
        ids.append(roots[r])
    return ids


def _flatten(segments: Sequence[Dict[str, Any]]) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
    out: List[Tuple[Tuple[float, float], Tuple[float, float]]] = []
    for s in segments:
        a = s.get("a"); b = s.get("b")
        if a is None or b is None:
            continue
        out.append(((float(a[0]), float(a[1])), (float(b[0]), float(b[1]))))
    return out


def observe_run_between_anchors(segments: Sequence[Dict[str, Any]],
                                start_xy: Optional[Tuple[float, float]],
                                end_xy: Optional[Tuple[float, float]],
                                *, reach_tol: float = _REACH_TOL_PT,
                                weld_eps: float = _WELD_EPS_PT) -> PlanViewRunObservation:
    """Verify whether a single clean drawn run connects ``start_xy`` and ``end_xy``. ``segments`` are drawn line
    segments ``{"a": (x, y), "b": (x, y)}`` (e.g. flattened ``PlanPdf.line_items``). Geometry only; no I/O, no
    placement, never draws."""
    def _reject(status: str, sg=None, eg=None, **detail) -> PlanViewRunObservation:
        return PlanViewRunObservation(status, status != PLAN_VIEW_RUN_CONNECTED,
                                      () if status == PLAN_VIEW_RUN_CONNECTED else (status,),
                                      sg, eg, False, {**detail, "reach_tol": reach_tol}, _NOTES)

    if start_xy is None or end_xy is None:
        return _reject(UNMEASURABLE, node_count=0)

    segs = _flatten(segments)
    # bbox prefilter: the connecting run lies near the two anchors -> ignore far linework (title block / legend).
    sep = math.hypot(start_xy[0] - end_xy[0], start_xy[1] - end_xy[1])
    margin = max(2.0 * reach_tol, sep)
    lo = (min(start_xy[0], end_xy[0]) - margin, min(start_xy[1], end_xy[1]) - margin)
    hi = (max(start_xy[0], end_xy[0]) + margin, max(start_xy[1], end_xy[1]) + margin)

    def _in(p):
        return lo[0] <= p[0] <= hi[0] and lo[1] <= p[1] <= hi[1]

    segs = [(a, b) for a, b in segs if _in(a) or _in(b)]
    if not segs:
        return _reject(NO_DRAWN_RUN, sg=None, eg=None, node_count=0, edge_count=0)

    pts: List[Tuple[float, float]] = []
    sp: List[Tuple[int, int]] = []
    for a, b in segs:
        ia = len(pts); pts.append(a)
        ib = len(pts); pts.append(b)
        sp.append((ia, ib))
    node_of = _grid_cluster(pts, weld_eps)
    n_nodes = max(node_of) + 1

    sums: Dict[int, List[float]] = {}
    for idx, nid in enumerate(node_of):
        acc = sums.setdefault(nid, [0.0, 0.0, 0.0])
        acc[0] += pts[idx][0]; acc[1] += pts[idx][1]; acc[2] += 1.0
    coord = {nid: (acc[0] / acc[2], acc[1] / acc[2]) for nid, acc in sums.items()}

    degree = [0] * n_nodes
    comp = _UF(n_nodes)
    edges_of: Dict[int, int] = {}
    for ia, ib in sp:
        na, nb = node_of[ia], node_of[ib]
        if na == nb:
            continue
        degree[na] += 1
        degree[nb] += 1
        comp.union(na, nb)
    comps: Dict[int, List[int]] = {}
    for nid in range(n_nodes):
        comps.setdefault(comp.find(nid), []).append(nid)
    for ia, ib in sp:
        na, nb = node_of[ia], node_of[ib]
        if na != nb:
            edges_of[comp.find(na)] = edges_of.get(comp.find(na), 0) + 1

    def _min_gap(nodes: List[int], p: Tuple[float, float]) -> float:
        return min(math.hypot(coord[n][0] - p[0], coord[n][1] - p[1]) for n in nodes)

    start_gap = round(min(math.hypot(coord[n][0] - start_xy[0], coord[n][1] - start_xy[1])
                          for n in coord), 2) if coord else None
    end_gap = round(min(math.hypot(coord[n][0] - end_xy[0], coord[n][1] - end_xy[1])
                        for n in coord), 2) if coord else None

    near_start, near_end, spanning = [], [], []
    for root, nodes in comps.items():
        ds = _min_gap(nodes, start_xy)
        de = _min_gap(nodes, end_xy)
        if ds <= reach_tol:
            near_start.append(root)
        if de <= reach_tol:
            near_end.append(root)
        if ds <= reach_tol and de <= reach_tol:
            spanning.append(root)

    base = {"node_count": n_nodes, "component_count": len(comps), "segment_count": len(segs),
            "spanning_components": len(spanning), "near_start": len(near_start), "near_end": len(near_end)}

    if len(spanning) >= 2:
        return _reject(MULTIPLE_PLAUSIBLE_RUNS, start_gap, end_gap, **base)
    if len(spanning) == 1:
        run = spanning[0]
        nodes = comps[run]
        junctions = [n for n in nodes if degree[n] >= 3]
        looped = edges_of.get(run, 0) >= len(nodes)            # a cycle -> two paths between the anchors
        if junctions or looped:
            return _reject(FORKED_RUN, start_gap, end_gap, junction_count=len(junctions), **base)
        return _reject(PLAN_VIEW_RUN_CONNECTED, start_gap, end_gap, **base)
    # 0 spanning components
    if near_start and near_end:
        return _reject(BROKEN_RUN, start_gap, end_gap, **base)
    if near_start or near_end:
        return _reject(ENDPOINT_NOT_TIGHT, start_gap, end_gap, **base)
    return _reject(NO_DRAWN_RUN, start_gap, end_gap, **base)


def _sheet_segments(plan: PlanPdf, sheet: int, offset: int) -> List[Dict[str, Any]]:
    """Flatten every drawn straight-line item on a sheet to ``{"a","b"}`` segments (read-only)."""
    out: List[Dict[str, Any]] = []
    for it in plan.line_items(int(sheet), int(offset)):
        for ln in (it.get("lines") or ()):
            ax, ay, bx, by = ln
            out.append({"a": (float(ax), float(ay)), "b": (float(bx), float(by))})
    return out


def observe_plan_view_run_for_path(plan_path: str, sheet: int, start_ft: float, end_ft: float,
                                   *, start_source_bound: bool, end_source_bound: bool, offset: int = 0,
                                   reach_tol: float = _REACH_TOL_PT
                                   ) -> Tuple[Any, PlanViewRunObservation]:
    """End-to-end read-only G-a→G-b: locate both endpoints' printed-label 2-D anchors, then verify the drawn run
    between them. Returns ``(endpoint_observation, run_observation)``. If an endpoint is not located the run is
    ``UNMEASURABLE``. Opens + closes the PDF; writes nothing; runs no placement/render."""
    plan = PlanPdf(str(plan_path))
    try:
        ep = observe_plan_view_endpoints(
            plan, int(sheet), float(start_ft), float(end_ft),
            start_source_bound=start_source_bound, end_source_bound=end_source_bound, offset=int(offset))
        if not (ep.start.located and ep.end.located):
            return ep, PlanViewRunObservation(UNMEASURABLE, True, (UNMEASURABLE,), None, None, False,
                                              {"reason": "endpoint anchor(s) not located"}, _NOTES)
        run = observe_run_between_anchors(
            _sheet_segments(plan, int(sheet), int(offset)),
            (ep.start.x, ep.start.y), (ep.end.x, ep.end.y), reach_tol=reach_tol)
        return ep, run
    finally:
        plan.close()
