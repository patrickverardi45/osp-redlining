"""Read-only run-geometry OBSERVER — the two diagnostics G4 named as missing (name-free).

The G4 geometry-vs-endpoint validation (``tests/test_g4_geometry_validation.py``) proved that, from the
signals exposed today, a wrong-branch FORK is indistinguishable from the clean positive: both have
source-bound endpoints, full station coverage, no rivals, and no extent/coverage warning, yet the fork's
drawn path could follow the wrong branch. The two signals that would separate them did not exist —
``BRANCH_PATH_UNIQUENESS`` and ``ENDPOINT_TO_RUN_COORDINATE_TIGHTNESS`` (named ``*_NOT_EXPOSED`` there).

This module computes BOTH, read-only, from the drawn-segment graph the generic lane already builds but then
DISCARDS (union-find welding + x-sorted polyline ordering collapse a fork into one opaque run; only a rival
COUNT survives). ``GenericGeometryDialect.band_segments_for(sheet)`` now retains those raw segments, so the
observer can reconstruct topology without inventing any coordinate.

What it is NOT:
  * NOT an AUTO gate, NOT a promotion, NOT a placement/status/render change. It reads geometry and reports.
  * It does not call, import, or mutate any placement / contract / renderer code (kept a pure geometry
    function so it can never affect a decision). A future, separately-authorized gate may CONSULT it.

Honest scope (the residual still-missing data, reported never invented):
  * A source-bound terminus carries a STATION, not a drawn (x,y) — so tightness is measured in the PROVEN
    station-x axis (``axis.x_at``); the y of a printed structure is not source-proven (no leader geometry),
    so the y dimension is not penalized. The missing real-package step is STRUCTURE-COORDINATE EXTRACTION:
    binding each terminus to the structure symbol's DRAWN (x, y) on the plan so full 2-D tightness can be
    measured. Without it, a real run whose y-reach does not meet a structure drawn off the run's band would
    still read TIGHT here. This proves the signals against the adversarial harness, NOT real generalization.
  * Single-sheet observation only; cross-sheet continuation stays the existing caveat's job.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

# --- The two named diagnostics this observer exposes (the G4 missing signals, now computed). ------------- #
BRANCH_PATH_UNIQUENESS = "BRANCH_PATH_UNIQUENESS"
ENDPOINT_TO_RUN_COORDINATE_TIGHTNESS = "ENDPOINT_TO_RUN_COORDINATE_TIGHTNESS"

# branch-uniqueness verdicts
BRANCH_UNIQUE = "UNIQUE"                 # exactly one spanning run, a simple chain (no fork, no loop) -> OK
BRANCH_FORKED = "FORKED"                 # the spanning run branches (a degree>=3 junction or a loop)
BRANCH_RIVAL_RUNS = "RIVAL_RUNS"         # >= 2 distinct runs each plausibly span the bore (parallel rivals)
BRANCH_NO_SPANNING_RUN = "NO_SPANNING_RUN"  # no welded run covers enough of the bore span (broken / absent)

# endpoint-tightness verdicts
TIGHTNESS_TIGHT = "TIGHT"               # both run terminals sit at the bound endpoint stations (within tol)
TIGHTNESS_LOOSE = "LOOSE"               # a run terminal is materially off the bound endpoint station
TIGHTNESS_UNMEASURABLE = "UNMEASURABLE"  # an endpoint is not station-bound -> no proven position to measure to

# Defaults (display pts; the synthetic harness axis is ~1 ft per pt, so these read ~ in feet there).
_WELD_EPS_PT = 7.0          # node-identity tolerance = the generic lane's own weld eps (segments that touch)
_TIGHT_TOL_PT = 15.0        # terminal-to-endpoint x-gap above which an endpoint is LOOSE (~15 ft on a 1ft/pt axis)
_SPAN_OVERLAP_MIN = 0.5     # a component must cover >= this fraction of [start_x, end_x] to count as a spanning run


@dataclass(frozen=True)
class RunGeometryObservation:
    """A read-only verdict over one sheet's drawn geometry vs two bound endpoint x-positions. Pure DATA — it
    confers no status and is never consumed by placement; a future gate may read ``would_reject``."""

    branch_uniqueness: str
    endpoint_tightness: str
    would_reject: bool
    reject_signals: Tuple[str, ...]
    detail: Dict[str, Any]
    notes: Tuple[str, ...]


class _UF:
    """Tiny union-find (point clustering into nodes; component grouping over edges)."""

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


def _cluster_points(points: Sequence[Tuple[float, float]], eps: float) -> List[int]:
    """Cluster endpoint coordinates within ``eps`` into node ids (one id per input point). O(n^2); n is tiny."""
    n = len(points)
    uf = _UF(n)
    e2 = eps * eps
    for i in range(n):
        xi, yi = points[i]
        for j in range(i + 1, n):
            xj, yj = points[j]
            if (xi - xj) ** 2 + (yi - yj) ** 2 <= e2:
                uf.union(i, j)
    # remap roots -> dense node ids
    roots: Dict[int, int] = {}
    ids: List[int] = []
    for i in range(n):
        r = uf.find(i)
        if r not in roots:
            roots[r] = len(roots)
        ids.append(roots[r])
    return ids


def _overlap_fraction(lo: float, hi: float, a: float, b: float) -> float:
    """Fraction of the bore x-range [a, b] covered by a component's x-range [lo, hi] (0..1)."""
    span = max(b - a, 1e-9)
    return max(0.0, min(hi, b) - max(lo, a)) / span


def observe_run_geometry(segments: Sequence[Dict[str, Any]], start_x: Optional[float], end_x: Optional[float],
                         *, weld_eps: float = _WELD_EPS_PT, tight_tol: float = _TIGHT_TOL_PT,
                         span_overlap_min: float = _SPAN_OVERLAP_MIN) -> RunGeometryObservation:
    """Observe the drawn-segment graph against two source-bound endpoint x-positions (station-axis projected).

    ``segments``: raw near-band line segments, each ``{"a": (x, y), "b": (x, y), ...}`` (extra keys ignored) —
    e.g. ``GenericGeometryDialect.band_segments_for(sheet)``.
    ``start_x`` / ``end_x``: the bound endpoints' display-space x (``axis.x_at(station_ft)``); ``None`` if an
    endpoint is not station-bound (tightness becomes UNMEASURABLE — never guessed).

    Returns the two diagnostics + ``would_reject`` (True if the run is NOT a unique, tightly-bound chain).
    Geometry only; no I/O, no placement, no mutation.
    """
    notes = (
        "tightness measured in the proven station-x axis; a bound structure's y is not source-proven "
        "(termini carry a station, not a drawn coordinate) so the y dimension is not penalized",
        "full 2-D tightness needs structure-coordinate extraction (the bound structure's drawn x,y) — the "
        "missing real-package step; an off-band structure could still read tight here",
        "single-sheet drawn geometry only; cross-sheet continuation is out of scope for this observer",
    )

    # --- build the node/edge graph from the raw segments ------------------------------------------------- #
    pts: List[Tuple[float, float]] = []
    seg_pts: List[Tuple[int, int]] = []
    for s in segments:
        a = s.get("a"); b = s.get("b")
        if a is None or b is None:
            continue
        ia = len(pts); pts.append((float(a[0]), float(a[1])))
        ib = len(pts); pts.append((float(b[0]), float(b[1])))
        seg_pts.append((ia, ib))

    if not seg_pts or start_x is None or end_x is None:
        # no drawable geometry, or an endpoint is not station-bound -> nothing to weld against
        branch = BRANCH_NO_SPANNING_RUN
        tight = TIGHTNESS_UNMEASURABLE if (start_x is None or end_x is None) else TIGHTNESS_LOOSE
        sigs = [BRANCH_PATH_UNIQUENESS]
        if tight == TIGHTNESS_LOOSE:
            sigs.append(ENDPOINT_TO_RUN_COORDINATE_TIGHTNESS)
        return RunGeometryObservation(branch, tight, True, tuple(sigs),
                                      {"node_count": 0, "edge_count": 0, "spanning_components": 0,
                                       "start_x": start_x, "end_x": end_x}, notes)

    node_of = _cluster_points(pts, weld_eps)
    n_nodes = max(node_of) + 1

    # node representative coordinate = centroid of its clustered points
    sums: Dict[int, List[float]] = {}
    for idx, nid in enumerate(node_of):
        acc = sums.setdefault(nid, [0.0, 0.0, 0.0])
        acc[0] += pts[idx][0]; acc[1] += pts[idx][1]; acc[2] += 1.0
    coord = {nid: (acc[0] / acc[2], acc[1] / acc[2]) for nid, acc in sums.items()}

    # edges (drop zero-length segments that collapse into one node) + node degree
    degree = [0] * n_nodes
    comp = _UF(n_nodes)
    edge_count = 0
    for ia, ib in seg_pts:
        na, nb = node_of[ia], node_of[ib]
        if na == nb:
            continue
        degree[na] += 1
        degree[nb] += 1
        comp.union(na, nb)
        edge_count += 1

    # group nodes into connected components
    comps: Dict[int, List[int]] = {}
    for nid in range(n_nodes):
        comps.setdefault(comp.find(nid), []).append(nid)

    lo_x, hi_x = (start_x, end_x) if start_x <= end_x else (end_x, start_x)

    def _xrange(nodes: List[int]) -> Tuple[float, float]:
        xs = [coord[n][0] for n in nodes]
        return min(xs), max(xs)

    spanning: List[List[int]] = []
    for nodes in comps.values():
        cminx, cmaxx = _xrange(nodes)
        if _overlap_fraction(cminx, cmaxx, lo_x, hi_x) >= span_overlap_min:
            spanning.append(nodes)

    # --- BRANCH_PATH_UNIQUENESS ------------------------------------------------------------------------- #
    junctions: List[int] = []
    if len(spanning) == 0:
        branch = BRANCH_NO_SPANNING_RUN
    elif len(spanning) >= 2:
        branch = BRANCH_RIVAL_RUNS
    else:
        run = spanning[0]
        n_c = len(run)
        e_c = 0
        for ia, ib in seg_pts:
            na, nb = node_of[ia], node_of[ib]
            if na != nb and comp.find(na) == comp.find(run[0]):
                e_c += 1
        junctions = [n for n in run if degree[n] >= 3]
        if junctions:
            branch = BRANCH_FORKED               # a node where the path can diverge -> not a unique path
        elif e_c >= n_c:
            branch = BRANCH_FORKED               # a loop (edges >= nodes) -> two paths between endpoints
        else:
            branch = BRANCH_UNIQUE               # a simple chain (edges == nodes-1, max degree 2)

    # --- ENDPOINT_TO_RUN_COORDINATE_TIGHTNESS ----------------------------------------------------------- #
    # measure each bound endpoint x against the nearest run's extreme-x terminal (the run's actual reach).
    def _nearest_node(target_x: float) -> Optional[int]:
        if not coord:
            return None
        return min(coord, key=lambda n: abs(coord[n][0] - target_x))

    sx_node = _nearest_node(start_x)
    ex_node = _nearest_node(end_x)
    start_gap = end_gap = None
    if sx_node is not None and ex_node is not None:
        start_run = comps[comp.find(sx_node)]
        end_run = comps[comp.find(ex_node)]
        s_lo, s_hi = _xrange(start_run)
        e_lo, e_hi = _xrange(end_run)
        # the start terminus should sit at the start-side reach of its run; the end terminus at the end-side
        start_gap = abs((s_lo if abs(s_lo - start_x) <= abs(s_hi - start_x) else s_hi) - start_x)
        end_gap = abs((e_hi if abs(e_hi - end_x) <= abs(e_lo - end_x) else e_lo) - end_x)
        tight = TIGHTNESS_TIGHT if max(start_gap, end_gap) <= tight_tol else TIGHTNESS_LOOSE
    else:
        tight = TIGHTNESS_UNMEASURABLE

    # --- combine ---------------------------------------------------------------------------------------- #
    reject_signals: List[str] = []
    if branch != BRANCH_UNIQUE:
        reject_signals.append(BRANCH_PATH_UNIQUENESS)
    if tight == TIGHTNESS_LOOSE:
        reject_signals.append(ENDPOINT_TO_RUN_COORDINATE_TIGHTNESS)
    would_reject = bool(reject_signals)

    detail = {
        "node_count": n_nodes,
        "edge_count": edge_count,
        "component_count": len(comps),
        "spanning_components": len(spanning),
        "junction_count": len(junctions),
        "start_x": round(float(start_x), 2),
        "end_x": round(float(end_x), 2),
        "start_gap": None if start_gap is None else round(float(start_gap), 2),
        "end_gap": None if end_gap is None else round(float(end_gap), 2),
        "tight_tol": tight_tol,
    }
    return RunGeometryObservation(branch, tight, would_reject, tuple(reject_signals), detail, notes)


def observe_dialect_run(dialect: Any, sheet: int, start_ft: float, end_ft: float,
                        **kwargs: Any) -> Optional[RunGeometryObservation]:
    """Thin read-only adapter: derive the observer inputs from a generic dialect that has already run
    ``extract_callouts`` on ``sheet``. Projects the bore-log station span to display-x via the fitted axis and
    feeds the retained band segments to :func:`observe_run_geometry`. Returns ``None`` if the sheet has no
    trustworthy station axis (the observer needs the proven axis to place the endpoints). Reads only — it
    calls ``axis_for`` / ``band_segments_for`` and mutates nothing.
    """
    axis = dialect.axis_for(sheet)
    if axis is None:
        return None
    sx = axis.x_at(float(start_ft))
    ex = axis.x_at(float(end_ft))
    if sx is None or ex is None:
        return None
    return observe_run_geometry(dialect.band_segments_for(sheet), sx, ex, **kwargs)
