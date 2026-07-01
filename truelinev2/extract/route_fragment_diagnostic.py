"""Read-only FRAGMENTATION DIAGNOSTIC for cold plan-view route linework (investigation, not a placement gate).

G-b' isolates route-like linework; G-b'''' reconnects safe colinear dash gaps; but on the real proof case the
isolated route stays fragmented into many components even after a wide safe bridge. This module does NOT invent the
next algorithm and does NOT widen any tolerance -- it MEASURES why the route is fragmented so the owner can pick
the next code gate from evidence.

It answers, read-only:
  1. component breakdown (how many route segments / components, sizes, which reach the labels, main-run candidates);
  2. gap taxonomy for nearby fragment endpoints (close+colinear / close+curved / close+inconsistent / too-wide /
     ambiguous / blocked-by-annotation);
  3. over-exclusion (did G-b' drop linework -- leader/tick/word-attached segments -- that actually sits in a route
     gap as a missing connector?);
  4. curvature (do fragments form a bending route where strict straight colinearity is too conservative?);
  5. vector/raster completeness (is the vector layer sparse enough that connectors are likely dropped curves or a
     raster-only route?);
  6. main-run reachability after the current safe bridge;
  7. a single recommended next code gate, with the reasons.

It reclassifies NOTHING, bridges NOTHING new, and draws NOTHING. ``class_verified`` is ALWAYS False. Pure geometry
over the G-b' isolated segments + the raw ``line_items`` (for the excluded set) + the read-only G-b'''' bridge; no
contracts / match / render / api / store / placement import; no ``_cap_review``.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from truelinev2.extract.plan_view_route_isolator import _grid_cluster_ids, observe_route_isolation
from truelinev2.extract.route_gap_bridge import bridge_route_gaps

# --- next-gate recommendation vocabulary ---------------------------------------------------------------- #
REC_READY_FOR_DISCRIMINATION = "READY_FOR_DISCRIMINATION"   # a safe bridge already yields a spine -> run G-b'''
REC_GB_PRIME_EXCLUSION_TUNING = "GB_PRIME_EXCLUSION_TUNING"  # G-b' dropped real connectors sitting in route gaps
REC_CURVE_AWARE_BRIDGE = "CURVE_AWARE_BRIDGE"              # gaps are gentle turns straight-colinear bridging misses
REC_ROUTE_FRAGMENT_RECOVERY = "ROUTE_FRAGMENT_RECOVERY"   # colinear connectors exist just beyond the safe gap window
REC_RASTER_OCR_LANE = "RASTER_OCR_LANE"                   # the vector layer is too sparse -> connectors not vectors
REC_KEEP_BLOCKED = "KEEP_BLOCKED"                          # no source-supported continuity evidence -> honestly blocked
REC_UNMEASURABLE = "UNMEASURABLE"                          # a label is not located -> nothing to diagnose against

# --- diagnostic measurement constants (a read-only WINDOW, never a bridge threshold) -------------------- #
_CLOSE_MAX_PT = 40.0      # measure endpoint pairs this close (NOT a bridge tolerance -- pure observation)
_WIDE_MAX_PT = 80.0       # ...and bucket colinear pairs out to here as "too wide"
_WELD_EPS_PT = 7.0        # node-identity tolerance (= the generic lane + G-b family weld eps)
_MIN_SEG_PT = 3.0         # drop sub-pixel speckle
_ALIGN_COS = math.cos(math.radians(20.0))   # a straight continuation aligns within 20 deg
_TOWARD_COS = math.cos(math.radians(45.0))  # a gentle turn still points within 45 deg
_CONNECTOR_TOL_PT = 8.0   # an excluded segment endpoint this close to a gap endpoint = a dropped connector
_SPARSE_VECTOR_SEGMENTS = 12  # fewer straight vectors than this near the route reads as raster-suspect


@dataclass(frozen=True)
class RouteFragmentDiagnostic:
    """Read-only characterization of why isolated route linework is fragmented. Pure DATA -- confers no status,
    reclassifies nothing, draws nothing. ``recommendation`` names the single next code gate suggested by evidence."""

    route_segments: int
    components: int
    component_summary: Tuple[Dict[str, Any], ...]
    near_start_components: int
    near_end_components: int
    main_run_candidate_components: int
    gap_taxonomy: Dict[str, int]
    ambiguous_endpoints: int
    excluded_segments: int
    over_exclusion_gaps: int
    over_exclusion_word_attached: int
    all_vector_segments: int
    route_fraction: float
    components_after_safe_bridge: int
    reachable_after_safe_bridge: bool
    recommendation: str
    reasons: Tuple[str, ...]
    class_verified: bool                 # always False
    detail: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"route_segments": self.route_segments, "components": self.components,
                "component_summary": list(self.component_summary),
                "near_start_components": self.near_start_components,
                "near_end_components": self.near_end_components,
                "main_run_candidate_components": self.main_run_candidate_components,
                "gap_taxonomy": self.gap_taxonomy, "ambiguous_endpoints": self.ambiguous_endpoints,
                "excluded_segments": self.excluded_segments, "over_exclusion_gaps": self.over_exclusion_gaps,
                "over_exclusion_word_attached": self.over_exclusion_word_attached,
                "all_vector_segments": self.all_vector_segments, "route_fraction": self.route_fraction,
                "components_after_safe_bridge": self.components_after_safe_bridge,
                "reachable_after_safe_bridge": self.reachable_after_safe_bridge,
                "recommendation": self.recommendation, "reasons": list(self.reasons),
                "class_verified": self.class_verified, "detail": self.detail}


def _unit(dx: float, dy: float) -> Optional[Tuple[float, float]]:
    d = math.hypot(dx, dy)
    return (dx / d, dy / d) if d > 1e-9 else None


def _flatten_all(line_items: Sequence[Dict[str, Any]]) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
    out: List[Tuple[Tuple[float, float], Tuple[float, float]]] = []
    for it in line_items:
        for ln in (it.get("lines") or ()):
            ax, ay, bx, by = float(ln[0]), float(ln[1]), float(ln[2]), float(ln[3])
            if math.hypot(bx - ax, by - ay) >= _MIN_SEG_PT:
                out.append(((ax, ay), (bx, by)))
    return out


def _seg_key(a: Tuple[float, float], b: Tuple[float, float]):
    pa = (round(a[0], 1), round(a[1], 1))
    pb = (round(b[0], 1), round(b[1], 1))
    return frozenset((pa, pb))


def _graph(route_segs: Sequence[Dict[str, Any]], weld_eps: float):
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
    edges: List[Tuple[int, int]] = []
    for ia, ib in sp:
        na, nb = ids[ia], ids[ib]
        if na == nb:
            continue
        adj[na].add(nb)
        adj[nb].add(na)
        edges.append((na, nb))
    # components via BFS
    comp: Dict[int, int] = {}
    cid = 0
    for s in range(n):
        if s in comp:
            continue
        stack = [s]
        comp[s] = cid
        while stack:
            u = stack.pop()
            for v in adj[u]:
                if v not in comp:
                    comp[v] = cid
                    stack.append(v)
        cid += 1
    return coord, adj, comp, edges, n, cid


def diagnose_route_fragmentation(line_items: Sequence[Dict[str, Any]],
                                 start_xy: Optional[Tuple[float, float]],
                                 end_xy: Optional[Tuple[float, float]],
                                 *, page_bounds: Optional[Tuple[float, float, float, float]] = None,
                                 words: Optional[Sequence[Dict[str, Any]]] = None,
                                 weld_eps: float = _WELD_EPS_PT) -> RouteFragmentDiagnostic:
    """Measure why the isolated route linework is fragmented and recommend the next code gate. Read-only; changes
    nothing; ``class_verified`` always False."""
    if start_xy is None or end_xy is None:
        return _empty(REC_UNMEASURABLE, ("printed station label(s) not located",))

    iso = observe_route_isolation(line_items, start_xy, end_xy, page_bounds=page_bounds, words=words,
                                  weld_eps=weld_eps)
    route_segs = list(iso.route_segments)
    all_segs = _flatten_all(line_items)
    route_keys = {_seg_key(s["a"], s["b"]) for s in route_segs}
    excluded = [(a, b) for (a, b) in all_segs if _seg_key(a, b) not in route_keys]

    g = _graph(route_segs, weld_eps)
    if g is None:
        return _empty(REC_KEEP_BLOCKED, ("no isolated route linework at all",),
                      all_vector_segments=len(all_segs), excluded_segments=len(excluded))
    coord, adj, comp, edges, n, n_components = g

    # --- (1) component breakdown ---------------------------------------------------------------------- #
    comp_nodes: Dict[int, List[int]] = {}
    for nid, c in comp.items():
        comp_nodes.setdefault(c, []).append(nid)
    comp_edges: Dict[int, int] = {}
    comp_len: Dict[int, float] = {}
    for na, nb in edges:
        c = comp[na]
        comp_edges[c] = comp_edges.get(c, 0) + 1
        comp_len[c] = comp_len.get(c, 0.0) + math.hypot(coord[na][0] - coord[nb][0], coord[na][1] - coord[nb][1])

    def _near(nodes: List[int], p: Tuple[float, float]) -> bool:
        return any(math.hypot(coord[nd][0] - p[0], coord[nd][1] - p[1]) <= _CLOSE_MAX_PT for nd in nodes)

    summary: List[Dict[str, Any]] = []
    near_start = near_end = both = 0
    for c, nodes in comp_nodes.items():
        ns, ne = _near(nodes, start_xy), _near(nodes, end_xy)
        near_start += 1 if ns else 0
        near_end += 1 if ne else 0
        both += 1 if (ns and ne) else 0
        summary.append({"segments": comp_edges.get(c, 0), "length": round(comp_len.get(c, 0.0), 1),
                        "near_start": ns, "near_end": ne})
    summary.sort(key=lambda d: d["length"], reverse=True)

    # --- (2) gap taxonomy + (3) over-exclusion + (4) curvature ---------------------------------------- #
    endpoints = [nid for nid in range(n) if len(adj[nid]) == 1]
    edir: Dict[int, Tuple[float, float]] = {}
    for nid in endpoints:
        nbr = next(iter(adj[nid]))
        d = _unit(coord[nid][0] - coord[nbr][0], coord[nid][1] - coord[nbr][1])
        if d is not None:
            edir[nid] = d
    endpoints = [e for e in endpoints if e in edir]
    word_boxes = _word_boxes(words)

    tax = {"close_colinear": 0, "close_curved": 0, "close_inconsistent": 0,
           "too_wide": 0, "blocked": 0}
    close_partner_count: Dict[int, int] = {}
    over_gaps = 0
    over_word = 0
    curved_examples: List[Tuple] = []
    for ii in range(len(endpoints)):
        i = endpoints[ii]
        for jj in range(ii + 1, len(endpoints)):
            j = endpoints[jj]
            if comp[i] == comp[j]:
                continue
            gap = math.hypot(coord[i][0] - coord[j][0], coord[i][1] - coord[j][1])
            if gap < 1e-9:
                continue
            bd = _unit(coord[j][0] - coord[i][0], coord[j][1] - coord[i][1])
            if bd is None:
                continue
            a_dot = edir[i][0] * bd[0] + edir[i][1] * bd[1]           # A points toward B ~ +1
            b_dot = edir[j][0] * bd[0] + edir[j][1] * bd[1]           # B points toward A ~ -1
            colinear = a_dot >= _ALIGN_COS and b_dot <= -_ALIGN_COS
            curved = (a_dot >= _TOWARD_COS and b_dot <= -_TOWARD_COS) and not colinear
            if gap <= _CLOSE_MAX_PT:
                blocked = _bridge_blocked(coord[i], coord[j], word_boxes)
                if blocked:
                    tax["blocked"] += 1
                elif colinear:
                    tax["close_colinear"] += 1
                elif curved:
                    tax["close_curved"] += 1
                    if len(curved_examples) < 5:
                        curved_examples.append(((round(coord[i][0], 1), round(coord[i][1], 1)),
                                                (round(coord[j][0], 1), round(coord[j][1], 1)), round(gap, 1)))
                else:
                    tax["close_inconsistent"] += 1
                if colinear or curved:
                    close_partner_count[i] = close_partner_count.get(i, 0) + 1
                    close_partner_count[j] = close_partner_count.get(j, 0) + 1
                # over-exclusion: a dropped segment sitting in this gap
                hit, word_hit = _excluded_connector(excluded, coord[i], coord[j], word_boxes)
                if hit:
                    over_gaps += 1
                    if word_hit:
                        over_word += 1
            elif gap <= _WIDE_MAX_PT and (colinear or curved):
                tax["too_wide"] += 1
    ambiguous = sum(1 for v in close_partner_count.values() if v >= 2)

    # --- (5) vector/raster + (6) reachability --------------------------------------------------------- #
    route_fraction = round(len(route_segs) / len(all_segs), 3) if all_segs else 0.0
    br = bridge_route_gaps(route_segs, weld_eps=weld_eps)
    reachable = _reachable_after(br.bridged_segments, start_xy, end_xy, weld_eps)

    # --- (7) recommendation --------------------------------------------------------------------------- #
    rec, reasons = _recommend(both, reachable, over_gaps, tax, ambiguous, len(all_segs), route_fraction)

    detail = {"curved_examples": curved_examples, "close_max": _CLOSE_MAX_PT,
              "isolation_status": iso.status, "bridge_status": br.status,
              "bridges_added": len(br.bridges)}
    return RouteFragmentDiagnostic(
        route_segments=len(route_segs), components=n_components, component_summary=tuple(summary),
        near_start_components=near_start, near_end_components=near_end, main_run_candidate_components=both,
        gap_taxonomy=tax, ambiguous_endpoints=ambiguous, excluded_segments=len(excluded),
        over_exclusion_gaps=over_gaps, over_exclusion_word_attached=over_word,
        all_vector_segments=len(all_segs), route_fraction=route_fraction,
        components_after_safe_bridge=(br.components_after if br.components_after is not None else n_components),
        reachable_after_safe_bridge=reachable, recommendation=rec, reasons=tuple(reasons),
        class_verified=False, detail=detail)


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


def _bridge_blocked(a: Tuple[float, float], b: Tuple[float, float],
                    word_boxes: Sequence[Tuple[float, float, float, float]], pad: float = 2.0) -> bool:
    mx, my = (a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0
    for (x0, y0, x1, y1) in word_boxes:
        if x0 - pad <= mx <= x1 + pad and y0 - pad <= my <= y1 + pad:
            return True
    return False


def _excluded_connector(excluded, a: Tuple[float, float], b: Tuple[float, float],
                        word_boxes) -> Tuple[bool, bool]:
    """Is there an EXCLUDED segment whose endpoints sit at the two gap endpoints (a dropped connector)?"""
    for (ea, eb) in excluded:
        near_ab = (_close(ea, a) and _close(eb, b)) or (_close(ea, b) and _close(eb, a))
        if near_ab:
            word_hit = _endpoint_in_word(ea, word_boxes) or _endpoint_in_word(eb, word_boxes)
            return True, word_hit
    return False, False


def _close(p: Tuple[float, float], q: Tuple[float, float]) -> bool:
    return math.hypot(p[0] - q[0], p[1] - q[1]) <= _CONNECTOR_TOL_PT


def _endpoint_in_word(p: Tuple[float, float], word_boxes, pad: float = 6.0) -> bool:
    for (x0, y0, x1, y1) in word_boxes:
        if x0 - pad <= p[0] <= x1 + pad and y0 - pad <= p[1] <= y1 + pad:
            return True
    return False


def _reachable_after(bridged_segments, start_xy, end_xy, weld_eps: float) -> bool:
    g = _graph(list(bridged_segments), weld_eps)
    if g is None:
        return False
    coord, adj, comp, edges, n, n_components = g
    comp_nodes: Dict[int, List[int]] = {}
    for nid, c in comp.items():
        comp_nodes.setdefault(c, []).append(nid)
    for nodes in comp_nodes.values():
        ns = any(math.hypot(coord[nd][0] - start_xy[0], coord[nd][1] - start_xy[1]) <= _CLOSE_MAX_PT for nd in nodes)
        ne = any(math.hypot(coord[nd][0] - end_xy[0], coord[nd][1] - end_xy[1]) <= _CLOSE_MAX_PT for nd in nodes)
        if ns and ne:
            return True
    return False


def _recommend(main_candidates: int, reachable: bool, over_gaps: int, tax: Dict[str, int],
               ambiguous: int, all_segs: int, route_fraction: float) -> Tuple[str, List[str]]:
    # Priority: real continuity evidence first; the coarse sparse-vector/raster check is a LAST-resort fallback.
    reasons: List[str] = []
    if reachable:
        reasons.append("a safe colinear bridge already yields a component reaching both labels")
        return REC_READY_FOR_DISCRIMINATION, reasons
    if over_gaps >= 1:
        reasons.append("%d route gap(s) contain an EXCLUDED segment (a connector G-b' dropped as leader/tick)"
                       % over_gaps)
        return REC_GB_PRIME_EXCLUSION_TUNING, reasons
    if tax["close_curved"] >= 2 and tax["close_curved"] >= tax["close_colinear"]:
        reasons.append("%d gap(s) are gentle turns (close+curved) that straight colinear bridging misses"
                       % tax["close_curved"])
        return REC_CURVE_AWARE_BRIDGE, reasons
    if tax["close_colinear"] >= 1 or tax["too_wide"] >= 1:
        reasons.append("%d colinear connector gap(s) sit just beyond the safe bridge window (recover, do NOT widen "
                       "blindly)" % (tax["close_colinear"] + tax["too_wide"]))
        return REC_ROUTE_FRAGMENT_RECOVERY, reasons
    if all_segs < _SPARSE_VECTOR_SEGMENTS:
        reasons.append("the vector layer is very sparse near the route -> connectors are likely raster/dropped curves")
        return REC_RASTER_OCR_LANE, reasons
    reasons.append("no source-supported continuity evidence found in the isolated linework")
    if main_candidates == 0:
        reasons.append("no single component reaches both station labels")
    if ambiguous:
        reasons.append("%d endpoint(s) have multiple plausible continuations (ambiguous)" % ambiguous)
    return REC_KEEP_BLOCKED, reasons


def _empty(rec: str, reasons: Tuple[str, ...], *, all_vector_segments: int = 0,
           excluded_segments: int = 0) -> RouteFragmentDiagnostic:
    return RouteFragmentDiagnostic(
        route_segments=0, components=0, component_summary=(), near_start_components=0, near_end_components=0,
        main_run_candidate_components=0,
        gap_taxonomy={"close_colinear": 0, "close_curved": 0, "close_inconsistent": 0, "too_wide": 0, "blocked": 0},
        ambiguous_endpoints=0, excluded_segments=excluded_segments, over_exclusion_gaps=0,
        over_exclusion_word_attached=0, all_vector_segments=all_vector_segments, route_fraction=0.0,
        components_after_safe_bridge=0, reachable_after_safe_bridge=False, recommendation=rec,
        reasons=tuple(reasons), class_verified=False, detail={})
