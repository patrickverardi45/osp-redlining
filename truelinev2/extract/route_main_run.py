"""Read-only ROUTE-vs-LATERAL discriminator for isolated plan-view route linework (gate G-b''').

G-b' isolates route-like linework; G-b'' binds a printed station label to a unique drawn route terminus. On the
real proof case G-b'' refuses because there are MULTIPLE route termini near each station label -- laterals /
service drops drawn in the same un-layered linework. This gate distinguishes the MAIN run from those laterals
ONLY when the geometry strongly supports one main run, and REFUSES otherwise (never a distance-only guess).

Method (conservative, refusal-first): over the ISOLATED route segments, find the single connected component that
reaches near BOTH source-bound station labels. Require it to be a TREE (a cycle/mesh means the path is not unique
-> refuse). The MAIN run = the longest simple path from a terminus near label-A to a terminus near label-B; every
off-backbone branch must be a SHORT lateral (its reach below a fraction of the main-run length) and the two labels
must sit at the backbone's ENDS. Anything else -- a long branch, a rival component, an interior-label run, a
meshy component -- is a NAMED refusal.

What it does NOT do (reported, never faked):
  * NEVER snaps to an arbitrary nearest line; the main-run ends are drawn route TERMINI near the labels.
  * NEVER uses grid / table / border / annotation linework (excluded by G-b' before this runs).
  * NEVER distinguishes route from lateral on a weak absolute-distance guess -- it uses connectivity to BOTH
    labels + a RELATIVE length ratio + topology, and refuses when a branch is long or the topology is unsafe.
  * NEVER draws a redline / stroke; NEVER places; NEVER promotes to AUTO. ``class_verified`` is ALWAYS False, so
    a discriminated main run is REVIEW evidence, never a placement or a drawn redline. (G-e draws the cold REVIEW
    stroke and is a separate, later, owner-approved gate.)
  * NO class verification; NO invented coordinate, station, or bore value.

Pure geometry over the G-b' route-isolated segments (+ optional G-a labels via the path wrapper). No I/O beyond
opening the PDF in the path wrapper; no mutation; no contracts / match / render / api / store / placement import;
no ``_cap_review``.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from truelinev2.extract.plan_view_route_isolator import _grid_cluster_ids, observe_route_isolation
from truelinev2.extract.printed_station_locator import observe_plan_view_endpoints
from truelinev2.ingest.pdf import PlanPdf

# --- discriminator verdicts ----------------------------------------------------------------------------- #
MAIN_ROUTE_DISCRIMINATED = "MAIN_ROUTE_DISCRIMINATED"          # one main run uniquely separated from short laterals --
#                                                                the only non-reject
MULTIPLE_MAIN_ROUTE_CANDIDATES = "MULTIPLE_MAIN_ROUTE_CANDIDATES"  # >= 2 separate runs each reach both labels (rivals)
ROUTE_LATERAL_AMBIGUOUS = "ROUTE_LATERAL_AMBIGUOUS"           # an off-backbone branch is long -> not clearly a lateral
NO_MAIN_ROUTE = "NO_MAIN_ROUTE"                               # no connected route reaches both labels
MAIN_ROUTE_ENDPOINT_NOT_TIGHT = "MAIN_ROUTE_ENDPOINT_NOT_TIGHT"   # the run passes the label region but does not END at
#                                                                    a terminus there (station beside a mid-run point)
ROUTE_TOPOLOGY_UNSAFE = "ROUTE_TOPOLOGY_UNSAFE"              # the spanning component has a cycle/mesh -> path not unique
UNMEASURABLE = "UNMEASURABLE"                                 # a printed station label is not located

# --- geometry constants (display points) ---------------------------------------------------------------- #
_ANCHOR_RADIUS_PT = 50.0     # a route terminus within this of a printed label is a candidate main-run end
_LATERAL_FRACTION = 0.5      # an off-backbone branch reaching >= this fraction of the main-run length is NOT a lateral
_WELD_EPS_PT = 7.0           # node-identity tolerance (= the generic lane + G-b/G-b'/G-b'' weld eps)

_NOTES = (
    "the main run is the longest simple path between a drawn route terminus near label-A and one near label-B in the "
    "single connected component reaching both source-bound labels; laterals are short branches off that backbone",
    "discrimination is topology + RELATIVE length only, never an absolute distance guess: a long off-backbone branch, "
    "a rival component, an interior-label run, or a cyclic/meshy component is a refusal, not a guess",
    "class_verified is always False -> a discriminated main run is REVIEW evidence, never a placement / drawn redline "
    "/ AUTO; drawing the cold REVIEW stroke (G-e) is a separate, later, owner-approved gate",
)


@dataclass(frozen=True)
class MainRunObservation:
    """Read-only verdict over whether one MAIN run can be separated from laterals in the isolated route linework
    between two printed-label endpoints. Pure DATA -- confers no status, is never consumed by placement, draws
    nothing. ``main_run_segments`` is the backbone (REVIEW evidence for a later gate, NOT a stroke)."""

    status: str
    would_reject: bool
    reject_signals: Tuple[str, ...]
    start_anchor: Optional[Tuple[float, float]]
    end_anchor: Optional[Tuple[float, float]]
    main_run_segments: Tuple[Dict[str, Any], ...]
    class_verified: bool                 # always False
    detail: Dict[str, Any] = field(default_factory=dict)
    notes: Tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {"status": self.status, "would_reject": self.would_reject,
                "reject_signals": list(self.reject_signals),
                "start_anchor": list(self.start_anchor) if self.start_anchor else None,
                "end_anchor": list(self.end_anchor) if self.end_anchor else None,
                "main_run_segment_count": len(self.main_run_segments),
                "class_verified": self.class_verified, "detail": self.detail}


def _obs(status: str, start_anchor, end_anchor, main_run_segments, detail: Dict[str, Any]) -> MainRunObservation:
    would_reject = status != MAIN_ROUTE_DISCRIMINATED
    return MainRunObservation(status, would_reject, () if not would_reject else (status,),
                              start_anchor, end_anchor, tuple(main_run_segments), False, detail, _NOTES)


def _build_simple_graph(route_segs: Sequence[Dict[str, Any]], weld_eps: float):
    """Weld endpoints into nodes and build an undirected SIMPLE graph (parallel segments between the same node pair
    collapse, keeping the shorter weight). Returns (coord, adj, n_nodes) or None. ``adj[u] = {v: weight}``."""
    pts: List[Tuple[float, float]] = []
    sp: List[Tuple[int, int]] = []
    for s in route_segs:
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
        return None
    ids = _grid_cluster_ids(pts, weld_eps)
    n = max(ids) + 1
    sums: Dict[int, List[float]] = {}
    for idx, nid in enumerate(ids):
        acc = sums.setdefault(nid, [0.0, 0.0, 0.0])
        acc[0] += pts[idx][0]
        acc[1] += pts[idx][1]
        acc[2] += 1.0
    coord = {nid: (acc[0] / acc[2], acc[1] / acc[2]) for nid, acc in sums.items()}
    adj: Dict[int, Dict[int, float]] = {i: {} for i in range(n)}
    for ia, ib in sp:
        na, nb = ids[ia], ids[ib]
        if na == nb:
            continue
        w = math.hypot(coord[na][0] - coord[nb][0], coord[na][1] - coord[nb][1])
        if nb not in adj[na] or w < adj[na][nb]:
            adj[na][nb] = w
            adj[nb][na] = w
    return coord, adj, n


def _component_of(adj: Dict[int, Dict[int, float]], seed: int) -> List[int]:
    seen = {seed}
    dq = deque([seed])
    while dq:
        u = dq.popleft()
        for v in adj[u]:
            if v not in seen:
                seen.add(v)
                dq.append(v)
    return sorted(seen)


def _components(adj: Dict[int, Dict[int, float]], n: int) -> List[List[int]]:
    seen: set = set()
    out: List[List[int]] = []
    for s in range(n):
        if s in seen:
            continue
        comp = _component_of(adj, s)
        seen.update(comp)
        out.append(comp)
    return out


def _tree_dists(adj: Dict[int, Dict[int, float]], source: int) -> Tuple[Dict[int, float], Dict[int, Optional[int]]]:
    """Weighted distances + parents from ``source`` within its (acyclic) component."""
    dist = {source: 0.0}
    parent: Dict[int, Optional[int]] = {source: None}
    dq = deque([source])
    while dq:
        u = dq.popleft()
        for v, w in adj[u].items():
            if v not in dist:
                dist[v] = dist[u] + w
                parent[v] = u
                dq.append(v)
    return dist, parent


def _path(parent: Dict[int, Optional[int]], target: int) -> List[int]:
    out: List[int] = []
    cur: Optional[int] = target
    while cur is not None:
        out.append(cur)
        cur = parent[cur]
    out.reverse()
    return out


def _dist_to_backbone(adj: Dict[int, Dict[int, float]], backbone: Sequence[int]) -> Dict[int, float]:
    dist = {n: 0.0 for n in backbone}
    dq = deque(backbone)
    while dq:
        u = dq.popleft()
        for v, w in adj[u].items():
            if v not in dist:
                dist[v] = dist[u] + w
                dq.append(v)
    return dist


def discriminate_main_run(route_segs: Sequence[Dict[str, Any]],
                          label_a_xy: Optional[Tuple[float, float]],
                          label_b_xy: Optional[Tuple[float, float]],
                          *, anchor_radius: float = _ANCHOR_RADIUS_PT,
                          lateral_fraction: float = _LATERAL_FRACTION,
                          weld_eps: float = _WELD_EPS_PT) -> MainRunObservation:
    """Separate the MAIN run from laterals in isolated route linework between two printed-label endpoints, or refuse.
    ``route_segs`` are G-b''s isolated route segments (``{"a","b"}``). ``label_a_xy`` / ``label_b_xy`` are the two
    printed-label positions (``None`` => UNMEASURABLE). Read-only; never draws/places/promotes; ``class_verified``
    always False."""
    if label_a_xy is None or label_b_xy is None:
        return _obs(UNMEASURABLE, None, None, (), {"reason": "printed station label(s) not located"})
    g = _build_simple_graph(route_segs, weld_eps)
    if g is None:
        return _obs(NO_MAIN_ROUTE, None, None, (), {"reason": "no route linework"})
    coord, adj, n = g

    def _near(nid: int, p: Tuple[float, float]) -> float:
        return math.hypot(coord[nid][0] - p[0], coord[nid][1] - p[1])

    comps = _components(adj, n)
    spanning = [c for c in comps
                if any(_near(nd, label_a_xy) <= anchor_radius for nd in c)
                and any(_near(nd, label_b_xy) <= anchor_radius for nd in c)]
    base: Dict[str, Any] = {"components": len(comps), "spanning_components": len(spanning),
                            "anchor_radius": anchor_radius, "lateral_fraction": lateral_fraction}
    if len(spanning) == 0:
        return _obs(NO_MAIN_ROUTE, None, None, (), base)
    if len(spanning) >= 2:
        return _obs(MULTIPLE_MAIN_ROUTE_CANDIDATES, None, None, (), base)

    comp = spanning[0]
    comp_set = set(comp)
    edge_count = sum(len(adj[u]) for u in comp) // 2       # undirected simple edges within the component
    base["component_nodes"] = len(comp)
    base["component_edges"] = edge_count
    if edge_count >= len(comp):                            # a tree has exactly nodes-1 edges; >= means a cycle/mesh
        return _obs(ROUTE_TOPOLOGY_UNSAFE, None, None, (), base)

    a_leaves = [nd for nd in comp if len(adj[nd]) == 1 and _near(nd, label_a_xy) <= anchor_radius]
    b_leaves = [nd for nd in comp if len(adj[nd]) == 1 and _near(nd, label_b_xy) <= anchor_radius]
    base["a_leaves"] = len(a_leaves)
    base["b_leaves"] = len(b_leaves)
    if not a_leaves or not b_leaves:
        return _obs(MAIN_ROUTE_ENDPOINT_NOT_TIGHT, None, None, (), base)

    # backbone = the longest simple path from an A-leaf to a B-leaf (unique in a tree)
    best_len = -1.0
    a_star = b_star = -1
    best_parent: Dict[int, Optional[int]] = {}
    for a in a_leaves:
        dist, parent = _tree_dists(adj, a)
        for b in b_leaves:
            if b in dist and dist[b] > best_len:
                best_len = dist[b]
                a_star, b_star, best_parent = a, b, parent
    if a_star == b_star or best_len <= 0.0:
        return _obs(NO_MAIN_ROUTE, None, None, (), base)
    backbone = _path(best_parent, b_star)
    backbone_set = set(backbone)
    base["main_run_length"] = round(best_len, 2)

    # every off-backbone node must be a SHORT lateral (reach below a fraction of the main-run length)
    dtb = _dist_to_backbone(adj, backbone)
    max_lateral = max((dtb[nd] for nd in comp if nd not in backbone_set), default=0.0)
    base["max_lateral_reach"] = round(max_lateral, 2)
    if max_lateral >= lateral_fraction * best_len:
        return _obs(ROUTE_LATERAL_AMBIGUOUS, None, None, (), base)

    # endpoint tightness: the nearest backbone node to each label must be the backbone END (not an interior node)
    nearest_a = min(backbone, key=lambda nd: _near(nd, label_a_xy))
    nearest_b = min(backbone, key=lambda nd: _near(nd, label_b_xy))
    if nearest_a != a_star or nearest_b != b_star:
        base["reason"] = "label is nearer a mid-run node than the main-run end"
        return _obs(MAIN_ROUTE_ENDPOINT_NOT_TIGHT, None, None, (), base)

    main_segments = [{"a": coord[backbone[i]], "b": coord[backbone[i + 1]]} for i in range(len(backbone) - 1)]
    base["start_gap"] = round(_near(a_star, label_a_xy), 2)
    base["end_gap"] = round(_near(b_star, label_b_xy), 2)
    return _obs(MAIN_ROUTE_DISCRIMINATED, coord[a_star], coord[b_star], main_segments, base)


def discriminate_plan_view_main_run_for_path(plan_path: str, sheet: int, start_ft: float, end_ft: float,
                                             *, start_source_bound: bool, end_source_bound: bool, offset: int = 0,
                                             anchor_radius: float = _ANCHOR_RADIUS_PT,
                                             lateral_fraction: float = _LATERAL_FRACTION
                                             ) -> Tuple[Any, MainRunObservation]:
    """End-to-end G-a -> G-b' -> G-b''' driver: locate the two printed-station labels, isolate the route between
    them (G-b'), then discriminate the main run from laterals. Returns ``(endpoint_observation, main_run_obs)``.
    Opens + closes the PDF; writes nothing; runs no placement / render; ``class_verified`` always False."""
    plan = PlanPdf(plan_path)
    try:
        ep = observe_plan_view_endpoints(plan, sheet, start_ft, end_ft,
                                         start_source_bound=start_source_bound,
                                         end_source_bound=end_source_bound, offset=offset)
        if not (ep.start.located and ep.end.located):
            return ep, _obs(UNMEASURABLE, None, None, (), {"reason": "printed station label(s) not located"})
        line_items = plan.line_items(int(sheet), int(offset))
        words = plan.words(int(sheet), int(offset))
        page_bounds = plan.page_bounds_display(int(sheet), int(offset))
        iso = observe_route_isolation(line_items, (float(ep.start.x), float(ep.start.y)),
                                      (float(ep.end.x), float(ep.end.y)),
                                      page_bounds=page_bounds, words=words, weld_eps=_WELD_EPS_PT)
        obs = discriminate_main_run(list(iso.route_segments),
                                    (float(ep.start.x), float(ep.start.y)),
                                    (float(ep.end.x), float(ep.end.y)),
                                    anchor_radius=anchor_radius, lateral_fraction=lateral_fraction)
        return ep, obs
    finally:
        plan.close()
