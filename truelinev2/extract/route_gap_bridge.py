"""Read-only ROUTE-CONTINUITY / DASH-GAP bridge for fragmented isolated route linework (gate G-b'''').

G-b' isolates route-like linework; on the real proof case G-b''' finds it FRAGMENTED into many disconnected
components (a dashed line / plotting gaps), so no connected spine exists to discriminate. This gate reconnects
colinear / near-colinear route fragments across SMALL gaps -- but ONLY when the source geometry strongly supports
continuity -- and refuses otherwise. It runs BEFORE G-b''' in the pipeline: isolate -> bridge -> discriminate.

A bridge is proposed ONLY between two drawn fragment ENDPOINTS (degree-1 nodes) that are:
  * close (gap within a small bound),
  * near-colinear AND directionally consistent (each fragment points at the other -- a straight continuation, not
    a corner or a reversal),
  * in DIFFERENT components (bridging two ends of the same fragment would close a loop -> unsafe),
  * a UNIQUE, MUTUAL choice (each endpoint's only continuation is the other) -- never "nearest wins".
Bridging degree-1 to degree-1 uniquely keeps the linework a forest of chains; under strict colinearity a straight
dash chain can never close into a loop, so any cycle candidate is a NAMED refusal.

What it does NOT do (reported, never faked):
  * NEVER bridges because endpoints are merely nearby (colinearity + direction are mandatory).
  * NEVER bridges across a label / table / title block / page frame / annotation -- those are already excluded by
    G-b' before this runs (it operates ONLY on the isolated route segments).
  * NEVER bridges to a lateral / service-drop end (a branch is not colinear with the main line -> refused).
  * NEVER invents a route where fragments are far / non-colinear / ambiguous -> a NAMED refusal.
  * NEVER draws a redline / stroke; NEVER places; NEVER promotes to AUTO. ``class_verified`` is ALWAYS False, so
    a bridged run is REVIEW evidence (a continuity HYPOTHESIS between real drawn endpoints), never a placement or a
    drawn redline. (G-e draws the cold REVIEW stroke and is a separate, later, owner-approved gate.)
  * NO class verification; NO invented coordinate, station, or bore value (bridge ends are existing drawn points).

Pure geometry over the G-b' route-isolated segments (+ optional G-a labels via the path wrapper). No I/O beyond
opening the PDF in the path wrapper; no mutation; no contracts / match / render / api / store / placement import;
no ``_cap_review``.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from truelinev2.extract.plan_view_route_isolator import _grid_cluster_ids, observe_route_isolation
from truelinev2.extract.printed_station_locator import observe_plan_view_endpoints
from truelinev2.ingest.pdf import PlanPdf

# --- bridge verdicts ------------------------------------------------------------------------------------ #
ROUTE_GAPS_BRIDGED = "ROUTE_GAPS_BRIDGED"                    # >= 1 safe unique colinear bridge added -- the reconnect
NO_ROUTE_GAPS = "NO_ROUTE_GAPS"                              # the isolated route is already connected; nothing to bridge
ROUTE_GAP_AMBIGUOUS = "ROUTE_GAP_AMBIGUOUS"                 # a fragment end has >= 2 plausible colinear continuations
ROUTE_GAP_TOO_WIDE = "ROUTE_GAP_TOO_WIDE"                   # a colinear continuation exists but beyond the gap bound
ROUTE_GAP_NOT_COLINEAR = "ROUTE_GAP_NOT_COLINEAR"          # a close fragment end exists but is not a straight continuation
ROUTE_BRIDGE_TOPOLOGY_UNSAFE = "ROUTE_BRIDGE_TOPOLOGY_UNSAFE"  # bridging would close a loop (same-fragment ends / cycle)
ROUTE_BRIDGE_NOT_SUPPORTED = "ROUTE_BRIDGE_NOT_SUPPORTED"  # fragments exist but no endpoint pair meets the criteria
UNMEASURABLE = "UNMEASURABLE"                               # a printed station label is not located (path wrapper)

# --- geometry constants (display points / degrees) ------------------------------------------------------ #
_MAX_GAP_PT = 14.0        # a dash gap this small (and > the weld eps) may be bridged if strongly colinear
_WIDE_FACTOR = 3.0        # a colinear continuation within MAX_GAP*this but beyond MAX_GAP reads TOO_WIDE (diagnostic)
_ANGLE_TOL_DEG = 20.0     # a straight continuation must align within this angle (fragment dir vs bridge dir)
_WELD_EPS_PT = 7.0        # node-identity tolerance (= the generic lane + G-b/G-b'/G-b''/G-b''' weld eps)

_NOTES = (
    "a bridge reconnects two DRAWN fragment endpoints (degree-1 run ends) that are close, near-colinear, and point "
    "at each other -- a straight dash/gap continuation; the endpoints are real, only the gap-crossing is hypothesized",
    "bridging is conservative + refusal-first: a non-colinear, too-wide, ambiguous, lateral-branch, or loop-closing "
    "endpoint pair is a NAMED refusal, never a nearest-endpoint guess and never a redline stroke",
    "class_verified is always False -> a bridged run is REVIEW continuity evidence, never a placement / drawn redline "
    "/ AUTO; drawing the cold REVIEW stroke (G-e) is a separate, later, owner-approved gate",
)


@dataclass(frozen=True)
class RouteBridgeObservation:
    """Read-only verdict over whether fragmented isolated route linework can be safely reconnected across dash gaps.
    Pure DATA -- confers no status, is never consumed by placement, draws nothing. ``bridged_segments`` is the
    original isolated segments plus any added bridge segments (REVIEW continuity evidence, NOT a stroke)."""

    status: str
    would_reject: bool
    reject_signals: Tuple[str, ...]
    bridged_segments: Tuple[Dict[str, Any], ...]
    bridges: Tuple[Tuple[Tuple[float, float], Tuple[float, float]], ...]
    components_before: Optional[int]
    components_after: Optional[int]
    class_verified: bool                 # always False
    detail: Dict[str, Any] = field(default_factory=dict)
    notes: Tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {"status": self.status, "would_reject": self.would_reject,
                "reject_signals": list(self.reject_signals),
                "bridged_segment_count": len(self.bridged_segments), "bridge_count": len(self.bridges),
                "components_before": self.components_before, "components_after": self.components_after,
                "class_verified": self.class_verified, "detail": self.detail}


class _UF:
    def __init__(self, n: int):
        self.p = list(range(n))

    def find(self, i: int) -> int:
        while self.p[i] != i:
            self.p[i] = self.p[self.p[i]]
            i = self.p[i]
        return i

    def union(self, i: int, j: int) -> bool:
        ri, rj = self.find(i), self.find(j)
        if ri == rj:
            return False            # already connected -> a union here would create a cycle
        self.p[ri] = rj
        return True


def _unit(dx: float, dy: float) -> Optional[Tuple[float, float]]:
    d = math.hypot(dx, dy)
    return (dx / d, dy / d) if d > 1e-9 else None


def _build_graph(route_segs: Sequence[Dict[str, Any]], weld_eps: float):
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
    adj: Dict[int, set] = {i: set() for i in range(n)}
    uf = _UF(n)
    for ia, ib in sp:
        na, nb = ids[ia], ids[ib]
        if na == nb:
            continue
        adj[na].add(nb)
        adj[nb].add(na)
        uf.union(na, nb)
    comp = {i: uf.find(i) for i in range(n)}
    n_components = len({uf.find(i) for i in range(n)})
    return coord, adj, comp, n, n_components


def _colinear(a: Tuple[float, float], da: Tuple[float, float], b: Tuple[float, float],
              db: Tuple[float, float], cos_tol: float) -> bool:
    bd = _unit(b[0] - a[0], b[1] - a[1])
    if bd is None:
        return False
    # A's fragment must point toward B, and B's fragment must point back toward A (a straight continuation)
    if da[0] * bd[0] + da[1] * bd[1] < cos_tol:
        return False
    if db[0] * bd[0] + db[1] * bd[1] > -cos_tol:
        return False
    return True


def bridge_route_gaps(route_segs: Sequence[Dict[str, Any]], *, max_gap: float = _MAX_GAP_PT,
                      angle_tol_deg: float = _ANGLE_TOL_DEG, wide_factor: float = _WIDE_FACTOR,
                      weld_eps: float = _WELD_EPS_PT) -> RouteBridgeObservation:
    """Reconnect colinear route fragments across small gaps in the isolated linework, or refuse. ``route_segs`` are
    G-b''s isolated route segments (``{"a","b"}``). Read-only; never draws/places/promotes; ``class_verified``
    always False. Added bridge segments carry ``"bridge": True`` (a continuity hypothesis, never a stroke)."""
    orig = [{"a": (float(s["a"][0]), float(s["a"][1])), "b": (float(s["b"][0]), float(s["b"][1]))}
            for s in route_segs if s.get("a") is not None and s.get("b") is not None]
    g = _build_graph(orig, weld_eps)
    if g is None:
        return _obs(ROUTE_BRIDGE_NOT_SUPPORTED, orig, [], 0, 0, {"reason": "no route linework"})
    coord, adj, comp, n, n_components = g
    cos_tol = math.cos(math.radians(angle_tol_deg))

    endpoints = [nid for nid in range(n) if len(adj[nid]) == 1]
    edir: Dict[int, Tuple[float, float]] = {}
    for nid in endpoints:
        nbr = next(iter(adj[nid]))
        d = _unit(coord[nid][0] - coord[nbr][0], coord[nid][1] - coord[nbr][1])
        if d is not None:
            edir[nid] = d
    endpoints = [e for e in endpoints if e in edir]

    close_bridge: List[Tuple[int, int, float]] = []   # diff-comp, colinear, gap <= max_gap
    cycle_cand = False                                 # same-comp, colinear, gap <= max_gap (loop-closing)
    too_wide = False                                   # diff-comp, colinear, max_gap < gap <= max_gap*wide
    not_colinear_close = False                         # diff-comp, close, not colinear
    for ii in range(len(endpoints)):
        i = endpoints[ii]
        for jj in range(ii + 1, len(endpoints)):
            j = endpoints[jj]
            gap = math.hypot(coord[i][0] - coord[j][0], coord[i][1] - coord[j][1])
            if gap < 1e-9:
                continue
            same = comp[i] == comp[j]
            colinear = _colinear(coord[i], edir[i], coord[j], edir[j], cos_tol)
            if colinear and gap <= max_gap:
                if same:
                    cycle_cand = True
                else:
                    close_bridge.append((i, j, gap))
            elif colinear and not same and gap <= max_gap * wide_factor:
                too_wide = True
            elif (not colinear) and (not same) and gap <= max_gap:
                not_colinear_close = True

    count: Dict[int, int] = {}
    for i, j, _gap in close_bridge:
        count[i] = count.get(i, 0) + 1
        count[j] = count.get(j, 0) + 1
    supported = [(i, j) for (i, j, _gap) in close_bridge if count.get(i) == 1 and count.get(j) == 1]

    base: Dict[str, Any] = {"components": n_components, "endpoints": len(endpoints),
                            "close_colinear_pairs": len(close_bridge), "supported_bridges": len(supported),
                            "max_gap": max_gap, "angle_tol_deg": angle_tol_deg}

    if supported:
        # add supported bridges with a cycle guard (belt-and-suspenders; colinear straight chains cannot loop)
        buf = _UF(n)
        for a, b in ((x, y) for x in range(n) for y in adj[x] if y > x):
            buf.union(a, b)
        added: List[Tuple[Tuple[float, float], Tuple[float, float]]] = []
        cycle = False
        bridge_segs: List[Dict[str, Any]] = []
        for i, j in supported:
            if not buf.union(i, j):
                cycle = True
                continue
            added.append((coord[i], coord[j]))
            bridge_segs.append({"a": coord[i], "b": coord[j], "bridge": True})
        if cycle and not added:
            return _obs(ROUTE_BRIDGE_TOPOLOGY_UNSAFE, orig, [], n_components, n_components, base)
        after = n_components - len(added)
        base["cycle_skipped"] = cycle
        return _obs(ROUTE_GAPS_BRIDGED, orig + bridge_segs, added, n_components, after, base)

    # no supported bridge -> the most informative named refusal
    if any(v >= 2 for v in count.values()):
        return _obs(ROUTE_GAP_AMBIGUOUS, orig, [], n_components, n_components, base)
    if cycle_cand:
        return _obs(ROUTE_BRIDGE_TOPOLOGY_UNSAFE, orig, [], n_components, n_components, base)
    if too_wide:
        return _obs(ROUTE_GAP_TOO_WIDE, orig, [], n_components, n_components, base)
    if not_colinear_close:
        return _obs(ROUTE_GAP_NOT_COLINEAR, orig, [], n_components, n_components, base)
    if n_components <= 1:
        return _obs(NO_ROUTE_GAPS, orig, [], n_components, n_components, base)
    return _obs(ROUTE_BRIDGE_NOT_SUPPORTED, orig, [], n_components, n_components, base)


def _obs(status: str, bridged_segments, bridges, comp_before, comp_after,
         detail: Dict[str, Any]) -> RouteBridgeObservation:
    would_reject = status not in (ROUTE_GAPS_BRIDGED, NO_ROUTE_GAPS)
    return RouteBridgeObservation(status, would_reject, () if not would_reject else (status,),
                                  tuple(bridged_segments), tuple(bridges), comp_before, comp_after,
                                  False, detail, _NOTES)


def bridge_plan_view_route_for_path(plan_path: str, sheet: int, start_ft: float, end_ft: float,
                                    *, start_source_bound: bool, end_source_bound: bool, offset: int = 0,
                                    max_gap: float = _MAX_GAP_PT, angle_tol_deg: float = _ANGLE_TOL_DEG
                                    ) -> Tuple[Any, RouteBridgeObservation]:
    """End-to-end G-a -> G-b' -> G-b'''' driver: locate the two printed-station labels, isolate the route (G-b'),
    then reconnect colinear fragment gaps. Returns ``(endpoint_observation, route_bridge_obs)``. Opens + closes the
    PDF; writes nothing; runs no placement / render; ``class_verified`` always False."""
    plan = PlanPdf(plan_path)
    try:
        ep = observe_plan_view_endpoints(plan, sheet, start_ft, end_ft,
                                         start_source_bound=start_source_bound,
                                         end_source_bound=end_source_bound, offset=offset)
        if not (ep.start.located and ep.end.located):
            obs = _obs(UNMEASURABLE, [], [], None, None, {"reason": "printed station label(s) not located"})
            return ep, obs
        line_items = plan.line_items(int(sheet), int(offset))
        words = plan.words(int(sheet), int(offset))
        page_bounds = plan.page_bounds_display(int(sheet), int(offset))
        iso = observe_route_isolation(line_items, (float(ep.start.x), float(ep.start.y)),
                                      (float(ep.end.x), float(ep.end.y)),
                                      page_bounds=page_bounds, words=words, weld_eps=_WELD_EPS_PT)
        obs = bridge_route_gaps(list(iso.route_segments), max_gap=max_gap, angle_tol_deg=angle_tol_deg)
        return ep, obs
    finally:
        plan.close()
