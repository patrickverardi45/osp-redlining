"""Read-only ISOLATED-ROUTE -> ANCHOR composition for COLD / non-recognized packages (gate G-b'').

On the real proof case the printed station LABEL sits offset from the drawn route and is framed by grid/table
boxes, so G-a' (leader / symbol / route-terminus resolver) refuses `AMBIGUOUS_ANCHOR` on the raw linework. G-b'
can now SEPARATE route-like linework from that grid/box/leader noise. This gate composes the two: it takes the
G-b' route-isolated segments as EVIDENCE and resolves a SOURCE-SUPPORTED route anchor -- a UNIQUE drawn route
TERMINUS (a degree-1 run end) near the printed label -- then re-verifies the run between the two improved anchors.

Why a route TERMINUS (not the nearest point on the route): a bore endpoint is drawn where the route ENDS at its
structure; the printed station identifies WHICH end. Binding the label to the unique nearby route end is
identity-supported. Binding it to the nearest point on a passing line would be an invented coordinate -- forbidden.

What it does NOT do (reported, never faked):
  * NEVER snaps to an arbitrary nearest line; a route merely passing near the label has no end there -> no anchor.
  * NEVER uses a grid / table / border / annotation line as an anchor (those are excluded by G-b' before this runs).
  * REFUSES on >= 2 candidate route termini (ambiguous), on a route region that still forks / rivals after
    anchoring (ROUTE_STILL_AMBIGUOUS), and when isolation yields no usable route (ROUTE_ISOLATION_REQUIRED).
  * NEVER draws a redline / stroke; NEVER places; NEVER promotes to AUTO. ``class_verified`` is ALWAYS False, so
    a resolved anchor is REVIEW evidence, never a placement or a drawn redline. (G-e draws the cold REVIEW stroke
    and is a separate, later, owner-approved gate.)
  * NO class verification; NO invented coordinate, station, or bore value.

Pure geometry over ``PlanPdf.line_items`` (+ optional ``words`` / page bounds) and the read-only G-a / G-b'
observers. No I/O beyond opening the PDF in the path wrapper; no mutation; no contracts / match / render / api /
store / placement import; no ``_cap_review``.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from truelinev2.extract.plan_view_route_isolator import (
    GRID_OR_BORDER_ONLY as _ISO_GRID_OR_BORDER_ONLY,
    MULTIPLE_ROUTE_CANDIDATES as _ISO_MULTIPLE,
    ROUTE_LAYER_AMBIGUOUS as _ISO_AMBIGUOUS,
    ROUTE_LINEWORK_ISOLATED as _ISO_ISOLATED,
    _grid_cluster_ids,
    observe_route_isolation,
)
from truelinev2.extract.printed_station_locator import observe_plan_view_endpoints
from truelinev2.ingest.pdf import PlanPdf

# --- composition verdicts ------------------------------------------------------------------------------- #
ISOLATED_ROUTE_ANCHOR_RESOLVED = "ISOLATED_ROUTE_ANCHOR_RESOLVED"    # both labels bound to a unique route terminus and
#                                                                       the run between them cleanly re-verifies -- the
#                                                                       only non-reject
ISOLATED_ROUTE_ANCHOR_AMBIGUOUS = "ISOLATED_ROUTE_ANCHOR_AMBIGUOUS"  # >= 2 candidate route termini near a label (or the
#                                                                       two labels resolve to the same route end)
ISOLATED_ROUTE_ANCHOR_NOT_TIGHT = "ISOLATED_ROUTE_ANCHOR_NOT_TIGHT"  # unique termini bound, but the run between them
#                                                                       does not cleanly connect (broken / not tight)
NO_ISOLATED_ROUTE_ANCHOR = "NO_ISOLATED_ROUTE_ANCHOR"                # no drawn route TERMINUS near a label (the route
#                                                                       does not end at the station; no snap allowed)
ROUTE_ISOLATION_REQUIRED = "ROUTE_ISOLATION_REQUIRED"               # G-b' produced no usable isolated route near the
#                                                                       labels (all grid/border) -> nothing to bind to
ROUTE_STILL_AMBIGUOUS = "ROUTE_STILL_AMBIGUOUS"                     # even anchored to termini the route region forks /
#                                                                       has rivals -> cannot resolve a unique route
UNMEASURABLE = "UNMEASURABLE"                                        # a printed station label is not located

# --- geometry constants (display points) ---------------------------------------------------------------- #
_ANCHOR_RADIUS_PT = 50.0    # search radius for a route terminus near the (offset) printed label
_REACH_TOL_PT = 12.0        # tight run re-verification tolerance once anchored to route termini
_WELD_EPS_PT = 7.0          # node-identity tolerance (= the generic lane + G-b/G-b' weld eps)

_NOTES = (
    "the improved anchor is a UNIQUE drawn route TERMINUS (a degree-1 run end) near the printed station label, taken "
    "from G-b''s route-isolated linework only -- never the nearest point on a passing line, never a grid/box line",
    "the run between the two improved anchors is re-verified by G-b' (route isolation + simple anchor-to-anchor path); "
    "a fork / rival / broken run after anchoring is a refusal, not a guess",
    "class_verified is always False -> a resolved anchor is REVIEW evidence, never a placement / drawn redline / AUTO; "
    "drawing the cold REVIEW stroke (G-e) is a separate, later, owner-approved gate",
)


@dataclass(frozen=True)
class IsolatedRouteAnchorObservation:
    """Read-only verdict over whether G-b''s isolated route linework yields a source-supported route anchor for each
    printed-label endpoint, and whether the run between the improved anchors re-verifies. Pure DATA -- confers no
    status, is never consumed by placement, and draws nothing."""

    status: str
    would_reject: bool
    reject_signals: Tuple[str, ...]
    start_anchor: Optional[Tuple[float, float]]
    end_anchor: Optional[Tuple[float, float]]
    run_status: Optional[str]            # the underlying G-b run verdict on the re-verified (terminus-anchored) run
    class_verified: bool                 # always False
    detail: Dict[str, Any] = field(default_factory=dict)
    notes: Tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {"status": self.status, "would_reject": self.would_reject,
                "reject_signals": list(self.reject_signals),
                "start_anchor": list(self.start_anchor) if self.start_anchor else None,
                "end_anchor": list(self.end_anchor) if self.end_anchor else None,
                "run_status": self.run_status, "class_verified": self.class_verified, "detail": self.detail}


def _obs(status: str, start_anchor: Optional[Tuple[float, float]], end_anchor: Optional[Tuple[float, float]],
         run_status: Optional[str], detail: Dict[str, Any]) -> IsolatedRouteAnchorObservation:
    would_reject = status != ISOLATED_ROUTE_ANCHOR_RESOLVED
    return IsolatedRouteAnchorObservation(status, would_reject, () if not would_reject else (status,),
                                          start_anchor, end_anchor, run_status, False, detail, _NOTES)


def _route_termini_near(route_segs: Sequence[Dict[str, Any]], p: Tuple[float, float],
                        radius: float, weld_eps: float) -> List[Tuple[float, float]]:
    """Degree-1 run-end coordinates within ``radius`` of ``p`` in the welded route graph. A line merely PASSING
    near ``p`` has no endpoint there -> not returned (never a nearest-line snap). Read-only; pure geometry."""
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
        return []
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
    for ia, ib in sp:
        na, nb = ids[ia], ids[ib]
        if na != nb:
            deg[na] += 1
            deg[nb] += 1
    return [coord[nid] for nid in range(n_nodes)
            if deg[nid] == 1 and math.hypot(coord[nid][0] - p[0], coord[nid][1] - p[1]) <= radius]


def resolve_isolated_route_anchors(line_items: Sequence[Dict[str, Any]],
                                   start_label_xy: Optional[Tuple[float, float]],
                                   end_label_xy: Optional[Tuple[float, float]],
                                   *, page_bounds: Optional[Tuple[float, float, float, float]] = None,
                                   words: Optional[Sequence[Dict[str, Any]]] = None,
                                   anchor_radius: float = _ANCHOR_RADIUS_PT,
                                   reach_tol: float = _REACH_TOL_PT,
                                   weld_eps: float = _WELD_EPS_PT) -> IsolatedRouteAnchorObservation:
    """Compose G-b' route isolation with route-terminus anchor resolution: bind each printed-label endpoint to a
    UNIQUE drawn route terminus from the isolated linework, then re-verify the run between the two improved anchors.
    ``start_label_xy`` / ``end_label_xy`` are the printed-label positions from G-a (``None`` => UNMEASURABLE).
    Read-only; never draws/places/promotes; ``class_verified`` always False."""
    if start_label_xy is None or end_label_xy is None:
        return _obs(UNMEASURABLE, None, None, None, {"reason": "printed station label(s) not located"})

    iso = observe_route_isolation(line_items, start_label_xy, end_label_xy,
                                  page_bounds=page_bounds, words=words, reach_tol=reach_tol, weld_eps=weld_eps)
    route_segs = list(iso.route_segments)
    base_detail: Dict[str, Any] = {"label_isolation_status": iso.status,
                                   "route_segment_count": len(route_segs),
                                   "anchor_radius": anchor_radius, "reach_tol": reach_tol}
    if not route_segs or iso.status == _ISO_GRID_OR_BORDER_ONLY:
        return _obs(ROUTE_ISOLATION_REQUIRED, None, None, None, base_detail)

    s_term = _route_termini_near(route_segs, start_label_xy, anchor_radius, weld_eps)
    e_term = _route_termini_near(route_segs, end_label_xy, anchor_radius, weld_eps)
    base_detail["start_termini"] = len(s_term)
    base_detail["end_termini"] = len(e_term)
    if len(s_term) >= 2 or len(e_term) >= 2:
        return _obs(ISOLATED_ROUTE_ANCHOR_AMBIGUOUS, None, None, None, base_detail)
    if len(s_term) == 0 or len(e_term) == 0:
        return _obs(NO_ISOLATED_ROUTE_ANCHOR, None, None, None, base_detail)

    start_anchor, end_anchor = s_term[0], e_term[0]
    if math.hypot(start_anchor[0] - end_anchor[0], start_anchor[1] - end_anchor[1]) <= weld_eps:
        base_detail["reason"] = "both labels resolve to the same route end"
        return _obs(ISOLATED_ROUTE_ANCHOR_AMBIGUOUS, None, None, None, base_detail)

    # re-verify the run between the SOURCE-SUPPORTED (terminus) anchors via G-b' (isolation + simple anchor-to-anchor
    # path). Only a clean ROUTE_LINEWORK_ISOLATED result promotes to RESOLVED.
    reverify = observe_route_isolation(line_items, start_anchor, end_anchor,
                                       page_bounds=page_bounds, words=words, reach_tol=reach_tol, weld_eps=weld_eps)
    base_detail["reverify_status"] = reverify.status
    base_detail["reverify_run"] = reverify.run_status
    if reverify.status == _ISO_ISOLATED:
        return _obs(ISOLATED_ROUTE_ANCHOR_RESOLVED, start_anchor, end_anchor, reverify.run_status, base_detail)
    if reverify.status in (_ISO_MULTIPLE, _ISO_AMBIGUOUS):
        return _obs(ROUTE_STILL_AMBIGUOUS, start_anchor, end_anchor, reverify.run_status, base_detail)
    return _obs(ISOLATED_ROUTE_ANCHOR_NOT_TIGHT, start_anchor, end_anchor, reverify.run_status, base_detail)


def resolve_plan_view_route_anchors_for_path(plan_path: str, sheet: int, start_ft: float, end_ft: float,
                                             *, start_source_bound: bool, end_source_bound: bool, offset: int = 0,
                                             anchor_radius: float = _ANCHOR_RADIUS_PT,
                                             reach_tol: float = _REACH_TOL_PT
                                             ) -> Tuple[Any, IsolatedRouteAnchorObservation]:
    """End-to-end G-a -> G-b' -> G-b'' driver: locate the two printed-station labels, isolate the route between
    them, and resolve a source-supported route anchor for each from the isolated linework. Returns
    ``(endpoint_observation, isolated_route_anchor_obs)``. Opens + closes the PDF; writes nothing; runs no
    placement / render; ``class_verified`` always False."""
    plan = PlanPdf(plan_path)
    try:
        ep = observe_plan_view_endpoints(plan, sheet, start_ft, end_ft,
                                         start_source_bound=start_source_bound,
                                         end_source_bound=end_source_bound, offset=offset)
        if not (ep.start.located and ep.end.located):
            return ep, _obs(UNMEASURABLE, None, None, None, {"reason": "printed station label(s) not located"})
        line_items = plan.line_items(int(sheet), int(offset))
        words = plan.words(int(sheet), int(offset))
        page_bounds = plan.page_bounds_display(int(sheet), int(offset))
        obs = resolve_isolated_route_anchors(line_items, (float(ep.start.x), float(ep.start.y)),
                                             (float(ep.end.x), float(ep.end.y)),
                                             page_bounds=page_bounds, words=words,
                                             anchor_radius=anchor_radius, reach_tol=reach_tol)
        return ep, obs
    finally:
        plan.close()
