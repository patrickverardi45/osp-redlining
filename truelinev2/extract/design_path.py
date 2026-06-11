r"""Design-path adherence laws (GENERAL; M8.14.c.2). No plan-set knowledge.

THE LAW (Patrick's correction, 2026-06-11): a redline must FOLLOW the drawn
design/conduit line; it must never chord/cut corners between station ticks or
anchors. Station ticks may constrain progress; they cannot replace the route
geometry. If the design path cannot be traced uniquely, the stroke ABSTAINS
-- a chord is never drawn across a drawn route.

Adversarially-reviewed design (the projection-ordering alternative was REFUTED
-- sorting by implied station IMPOSES monotonicity instead of testing it and
re-imports the chord assumption; see the M8.14.c.2 recon):

  * PIECES: every conduit drawing splits into connected line-item sub-paths
    (consecutive items chaining within SUBPATH_TOL); each sub-path contributes
    its LONGEST line item. One law covers rectangle dashes (long axis), corner
    fragments, terminal caps, and curve dash-marks drawn as tiny triangles
    (the longest side approximates the local tangent). Outline TWINS (one
    filled dash renders as two ~stroke-width-apart triangles) merge to one
    piece; touching pieces WELD into polylines at UNAMBIGUOUS degree-2
    contacts only (a contact shared by >= 3 piece ends is a junction and is
    never welded across) -- dense curve marks compress into one drawn
    polyline while every real junction stays a walk decision.
  * WALK: anchor-seeded exhaustive search over the welded pieces. EVERY
    unvisited piece reachable within the dash-gap cap is explored (junctions
    branch; dead ends prune); a path COMPLETES at the end anchor and never
    extends past it (the M8.5 containment rule). Out-and-back spur noise is
    collapsed (hairpin collapse at stitch scale) BEFORE uniqueness is judged.
    Exactly ONE distinct trimmed vertex sequence -> traced; 0 -> not
    connected; >= 2 -> ambiguous; budget exhausted -> exhausted.
  * GATES (consumed by the lane): path-length corroboration against the
    ladder scale; in-span tick adherence (ticks near the chord or path must
    lie ON the path); terminal stitch-jitter trim (TRIM_RADIUS) so anchor
    overhang never fakes a fold.
  * CHORD CERTIFICATE: when NO conduit connects the anchors, a straight
    tick-interpolated stroke is permitted ONLY with a positive straightness
    certificate (all in-span corridor ticks collinear with the anchor chord)
    -- "no conduit of the mapped class" carries no straightness information,
    so the certificate is the evidence, not the absence.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

from truelinev2.extract.conduit_topology import MAX_DASH_GAP

SUBPATH_TOL = 0.5     # line items chain into one sub-path when continuous
STITCH_SLACK = 2.0    # hairpin-collapse band: an excursion that returns to
                      # within this of where it left contributed no forward
                      # geometry (stitch jitter, NOT a path tolerance)
TRIM_RADIUS = 2.0     # drop walked vertices this close to an anchor (stitch trim)
TWIN_TOL = 2.0        # outline-twin merge: a filled dash outline splits into
                      # two ~stroke-width-apart triangles whose long sides are
                      # the SAME drawn mark twice; un-merged twins strand the
                      # walk (the twin is always the nearest candidate). An
                      # outline artifact correction, not a path tolerance.
WELD_TOL = 4.0        # piece ends weld into one polyline when they TOUCH at
                      # sub-dash-gap scale (curve marks 0-3.5 pt apart) AND the
                      # contact is degree-2 (exactly two piece ends) -- a
                      # graph-compression of continuously-drawn linework;
                      # junctions (>= 3 ends) are never welded across.
JITTER_EQUIV_TOL = WELD_TOL  # walk variants within this cross-deviation are
                      # the SAME drawn line: entry-order permutations at a
                      # welded contact displace the path by at most the
                      # contact diameter (WELD_TOL), so the equivalence band
                      # IS the weld-contact scale -- a structural derivation,
                      # not a tunable. Two REAL conduits this close (~2.8 ft)
                      # would be drawn as one line or as outline twins.
                      # Loosening beyond the weld scale would tiebreak
                      # distinct geometry -- forbidden (a named decision).
DESIGN_LENGTH_REL_TOL = 0.25  # traced-path length vs ladder scale -- the
                      # b.8 corroboration band reused verbatim; loosening
                      # converts abstains into placements (forbidden without
                      # a named owner decision)
MAX_WALK_EXPANSIONS = 20000

TRACED = "DESIGN_PATH_TRACED"
NOT_CONNECTED = "DESIGN_PATH_NOT_CONNECTED"
AMBIGUOUS = "DESIGN_PATH_AMBIGUOUS"
EXHAUSTED = "DESIGN_PATH_SEARCH_EXHAUSTED"

Point = Tuple[float, float]


@dataclass(frozen=True)
class Piece:
    """One drawn conduit piece: an ordered polyline (a single dash long-axis,
    or a welded chain of touching marks). Walk entry/exit are its two ends."""
    points: Tuple[Point, ...]
    layer: str

    @property
    def a(self) -> Point:
        return self.points[0]

    @property
    def b(self) -> Point:
        return self.points[-1]

    @property
    def length(self) -> float:
        return sum(math.hypot(q[0] - p[0], q[1] - p[1])
                   for p, q in zip(self.points, self.points[1:]))


def split_subpaths(lines: Sequence[Tuple[float, float, float, float]],
                   tol: float = SUBPATH_TOL) -> List[List[Tuple[float, float, float, float]]]:
    """Consecutive line items chain into one sub-path while each starts where
    the previous ended (within ``tol``); a break starts a new sub-path."""
    out: List[List[Tuple[float, float, float, float]]] = []
    cur: List[Tuple[float, float, float, float]] = []
    for ln in lines:
        if cur and math.hypot(ln[0] - cur[-1][2], ln[1] - cur[-1][3]) > tol:
            out.append(cur)
            cur = []
        cur.append(ln)
    if cur:
        out.append(cur)
    return out


def _twin(p: Piece, q: Piece, tol: float) -> bool:
    return (p.layer == q.layer
            and ((_d(p.a, q.a) <= tol and _d(p.b, q.b) <= tol)
                 or (_d(p.a, q.b) <= tol and _d(p.b, q.a) <= tol)))


def _weld(pieces: List[Piece], tol: float) -> List[Piece]:
    """Weld piece ends into polylines at UNAMBIGUOUS contacts: two ends touch
    within ``tol`` and NO third piece end shares the contact (>= 3 ends = a
    junction -- never welded across). Compresses continuously-drawn linework
    (curve marks) into single pieces; every walk decision point survives."""
    pieces = list(pieces)
    while True:
        ends = [(i, e, p.points[0] if e == 0 else p.points[-1])
                for i, p in enumerate(pieces) for e in (0, 1)]
        weld = None
        for n, (i, ei, pt_i) in enumerate(ends):
            for j, ej, pt_j in ends[n + 1:]:
                if i == j or _d(pt_i, pt_j) > tol:
                    continue
                others = [1 for k, _ek, pt_k in ends
                          if k not in (i, j)
                          and (_d(pt_k, pt_i) <= tol or _d(pt_k, pt_j) <= tol)]
                if others:
                    continue  # junction: >= 3 ends share the contact (tested
                    # against BOTH contact ends -- a one-sided test can weld
                    # across a real junction whose third leg touches only pt_j)
                weld = (i, ei, j, ej)
                break
            if weld:
                break
        if weld is None:
            return pieces
        i, ei, j, ej = weld
        pi, pj = pieces[i], pieces[j]
        left = pi.points if ei == 1 else tuple(reversed(pi.points))
        right = pj.points if ej == 0 else tuple(reversed(pj.points))
        merged = Piece(points=left + right, layer=pi.layer)
        pieces = [p for k, p in enumerate(pieces) if k not in (i, j)] + [merged]


def conduit_pieces(drawings: Sequence[dict], layers: Sequence[str],
                   twin_tol: float = TWIN_TOL,
                   weld_tol: float = WELD_TOL) -> List[Piece]:
    """Walkable pieces for the given conduit layers (injected -- this module
    names no layer): sub-path long axes -> outline-twin merge -> degree-2
    contact weld."""
    raw: List[Piece] = []
    wanted = set(layers)
    for d in drawings:
        if d.get("layer") not in wanted:
            continue
        for sub in split_subpaths(d.get("lines") or ()):
            best = max(sub, key=lambda ln: math.hypot(ln[2] - ln[0], ln[3] - ln[1]))
            raw.append(Piece(points=((best[0], best[1]), (best[2], best[3])),
                             layer=d["layer"]))
    merged: List[Piece] = []
    for p in raw:
        for i, q in enumerate(merged):
            if _twin(p, q, twin_tol):
                a, b = (p.a, p.b) if _d(p.a, q.a) <= _d(p.a, q.b) else (p.b, p.a)
                merged[i] = Piece(points=(((a[0] + q.a[0]) / 2, (a[1] + q.a[1]) / 2),
                                          ((b[0] + q.b[0]) / 2, (b[1] + q.b[1]) / 2)),
                                  layer=q.layer)
                break
        else:
            merged.append(p)
    return _weld(merged, weld_tol)


def _d(p: Point, q: Point) -> float:
    return math.hypot(p[0] - q[0], p[1] - q[1])


def walk_design_path(pieces: Sequence[Piece], start_xy: Point, end_xy: Point,
                     jump_cap: float = MAX_DASH_GAP,
                     max_expansions: int = MAX_WALK_EXPANSIONS) -> dict:
    """Exhaustive anchor-seeded walk over WELDED pieces: every unvisited piece
    whose nearer end is within ``jump_cap`` of the current point is explored
    (entered at its nearer end, traversed fully). Junctions branch; dead ends
    prune; completion never extends past the end anchor. Uniqueness is judged
    on the distinct hairpin-collapsed, anchor-trimmed vertex sequences of
    COMPLETE walks (start->end)."""
    budget = {"left": max_expansions, "exhausted": False}
    complete: Dict[Tuple, Tuple[List[Point], frozenset]] = {}
    malformed = {"self_crossing": 0}

    def extend(current: Point, visited: frozenset, verts: List[Point]) -> None:
        if budget["left"] <= 0:
            budget["exhausted"] = True
            return
        budget["left"] -= 1
        if verts and _d(current, end_xy) <= jump_cap:
            # piece-free "completions" are bare chords, not traces -- refused
            pts = trim_to_anchors(collapse_hairpins(verts), start_xy, end_xy)
            if path_self_crossing(pts):
                # a sharp-turn dash entered at its (Euclidean-nearer) WRONG
                # end traverses backwards and folds the stroke over itself
                # (verification lens 1) -- a self-crossing trace is geometric
                # nonsense, never an answer candidate; refusing it converts
                # the silent wrong stroke into an honest abstain
                malformed["self_crossing"] += 1
                return
            sig = tuple((round(x, 1), round(y, 1)) for x, y in pts)
            complete.setdefault(sig, (pts, visited))
            return  # complete: never extend past the end anchor
        for de, i in sorted(
                (min(_d(current, p.a), _d(current, p.b)), i)
                for i, p in enumerate(pieces) if i not in visited):
            if de > jump_cap:
                break
            pts = pieces[i].points
            walk_pts = (list(pts) if _d(current, pts[0]) <= _d(current, pts[-1])
                        else list(reversed(pts)))
            extend(walk_pts[-1], visited | {i}, verts + walk_pts)
        # no candidate within the cap -> dead end: pruned

    extend(start_xy, frozenset(), [])
    if budget["exhausted"]:
        return {"result": EXHAUSTED, "paths_found": len(complete),
                "named_missing": (f"the design-path walk exhausted its budget "
                                  f"({max_expansions}) -- uniqueness cannot be "
                                  f"claimed from an incomplete search")}
    if not complete:
        extra = (f" ({malformed['self_crossing']} self-crossing traversal(s) "
                 f"refused -- direction evidence missing)"
                 if malformed["self_crossing"] else "")
        return {"result": NOT_CONNECTED, "paths_found": 0,
                "self_crossing_refused": malformed["self_crossing"],
                "named_missing": ("no drawn conduit path of the mapped classes "
                                  "connects the two anchors (within the dash-"
                                  "gap cap) -- the design line is not "
                                  "continuously drawn between them" + extra)}
    # Jitter equivalence: walk variants whose mutual cross-deviation stays at
    # outline/stitch scale (JITTER_EQUIV_TOL) are the SAME drawn line
    # traversed with different joint micro-ordering -- ONE answer (canonical:
    # the shortest). Anything above that scale is physically distinct and
    # never tiebroken.
    groups: List[List[Tuple[List[Point], frozenset]]] = []
    for entry in complete.values():
        for g in groups:
            if all(_cross_deviation(entry[0], other[0]) <= JITTER_EQUIV_TOL
                   for other in g):
                g.append(entry)
                break
        else:
            groups.append([entry])
    if len(groups) >= 2:
        spread = max(_cross_deviation(a[0][0], b[0][0])
                     for i, a in enumerate(groups) for b in groups[i + 1:])
        return {"result": AMBIGUOUS, "paths_found": len(complete),
                "path_groups": len(groups),
                "named_missing": (f"{len(groups)} physically distinct drawn "
                                  f"paths connect the anchors (max mutual "
                                  f"deviation {round(spread, 1)} pt) -- "
                                  f"distinct geometry is never tiebroken; the "
                                  f"named missing artifact is a strand "
                                  f"discriminator for parallel drawn runs")}
    canonical, visited = min(groups[0], key=lambda e: path_length(e[0]))
    return {"result": TRACED, "paths_found": len(complete), "path_groups": 1,
            "stroke_points": canonical, "visited_pieces": visited}


def _cross_deviation(p1: Sequence[Point], p2: Sequence[Point]) -> float:
    return max(max(point_to_polyline(p, p2) for p in p1),
               max(point_to_polyline(p, p1) for p in p2))


def path_self_crossing(pts: Sequence[Point]) -> bool:
    """True when any two NON-ADJACENT stroke segments strictly intersect --
    a drilled bore's plan-view path never folds over itself; a self-crossing
    trace is a malformed traversal, never an answer."""
    def _ccw(p, q, r):
        return (r[1] - p[1]) * (q[0] - p[0]) > (q[1] - p[1]) * (r[0] - p[0])

    segs = list(zip(pts, pts[1:]))
    for i, (a, b) in enumerate(segs):
        for c, d in segs[i + 2:]:
            if (_ccw(a, c, d) != _ccw(b, c, d)) and (_ccw(a, b, c) != _ccw(a, b, d)):
                return True
    return False


def collapse_hairpins(verts: Sequence[Point],
                      slack: float = STITCH_SLACK) -> List[Point]:
    """Drop out-and-back excursion vertices: whenever v[i-1] and v[i+1] sit
    within stitch slack of each other, v[i] contributed no forward geometry
    (corner-fragment spur noise) and is removed. Iterates to a fixed point.
    Collapsed spurs equal the direct walk -- phantom path variants never
    reach the uniqueness judgment."""
    pts = list(verts)
    changed = True
    while changed:
        changed = False
        for i in range(1, len(pts) - 1):
            if _d(pts[i - 1], pts[i + 1]) <= slack:
                del pts[i]
                changed = True
                break
    return pts


def trim_to_anchors(verts: Sequence[Point], start_xy: Point, end_xy: Point,
                    radius: float = TRIM_RADIUS) -> List[Point]:
    """Anchor-exact stroke: [start] + walked vertices (deduped, with vertices
    inside the anchor trim radius dropped -- dash overhang never fakes a fold)
    + [end]."""
    pts: List[Point] = [start_xy]
    for v in verts:
        if _d(v, start_xy) <= radius or _d(v, end_xy) <= radius:
            continue
        if _d(v, pts[-1]) <= 0.1:
            continue
        pts.append(v)
    pts.append(end_xy)
    return pts


def path_length(points: Sequence[Point]) -> float:
    return sum(_d(a, b) for a, b in zip(points, points[1:]))


def point_to_polyline(p: Point, pts: Sequence[Point]) -> float:
    best = float("inf")
    for a, b in zip(pts, pts[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        den = dx * dx + dy * dy
        t = 0.0 if den == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx
                                                    + (p[1] - a[1]) * dy) / den))
        best = min(best, _d(p, (a[0] + dx * t, a[1] + dy * t)))
    return best


def parallel_strand_guard(pieces: Sequence[Piece], visited: frozenset,
                          path: Sequence[Point], anchors: Sequence[Point],
                          corridor: float, anchor_radius: float,
                          min_len: float = 5.0) -> dict:
    """A traced path is REFUSED when an UNVISITED mapped-class piece PARALLELS
    it (both ends inside the corridor, touching nothing) -- evidence of a
    sibling drawn run the walk never saw complete (verification lens 1: when
    the true route cannot complete, a parallel sibling traces uniquely).
    Exempt as already-adjudicated: pieces with an end ON the path (within the
    weld-contact scale) are junction legs the exhaustive walk explored and
    pruned as dead ends; pieces with an end at a structure anchor are anchor
    furniture; sub-dash caps are exempt by the length floor."""
    strands = []
    for i, p in enumerate(pieces):
        if i in visited or p.length < min_len:
            continue
        if any(_d(end, a) <= anchor_radius for end in (p.a, p.b)
               for a in anchors):
            continue
        da, db = point_to_polyline(p.a, path), point_to_polyline(p.b, path)
        if min(da, db) <= WELD_TOL:
            continue  # junction-attached: walk-adjudicated (explored, pruned)
        if da <= corridor and db <= corridor:
            strands.append({"a": [round(v, 1) for v in p.a],
                            "b": [round(v, 1) for v in p.b],
                            "layer": p.layer})
    return {"parallel_strands": len(strands), "strands": strands[:4],
            "clear": not strands}


def ticks_adhere(path: Sequence[Point], tick_xys: Sequence[Point],
                 corridor: float) -> dict:
    """Every in-span tick that belongs to this route (within ``corridor`` of
    the CHORD or the PATH) must lie ON the path. A tick near the chord but far
    from the path means the path left the route's tick band -> refuse."""
    chord = [path[0], path[-1]]
    relevant = [t for t in tick_xys
                if point_to_polyline(t, chord) <= corridor
                or point_to_polyline(t, path) <= corridor]
    offenders = [t for t in relevant
                 if point_to_polyline(t, path) > corridor]
    return {"relevant_ticks": len(relevant), "offenders": len(offenders),
            "adheres": not offenders}


def chord_straightness_certificate(tick_xys: Sequence[Point], start_xy: Point,
                                   end_xy: Point, corridor: float) -> dict:
    """A tick-chord stroke is permitted ONLY with POSITIVE evidence of
    straightness. ALL in-span ticks are evidence: any tick beyond the corridor
    is proof the route LEAVES the chord and fails the certificate outright
    (verification lens 1: filtering refuting ticks certified a curved route).
    The collinear ticks must also SAMPLE the span (>= 2 ticks; no un-sampled
    stretch longer than half the chord) -- straightness is measured, never
    assumed between sparse ticks."""
    chord = [start_xy, end_xy]
    residuals = [round(point_to_polyline(t, chord), 1) for t in tick_xys]
    off_chord = [r for r in residuals if r > corridor]
    if off_chord or len(tick_xys) < 2:
        return {"relevant_ticks": len(tick_xys), "residuals_pt": residuals,
                "off_chord_ticks": len(off_chord), "straight": False}
    span = _d(start_xy, end_xy)
    dx, dy = end_xy[0] - start_xy[0], end_xy[1] - start_xy[1]
    ts = sorted([0.0, 1.0] + [
        max(0.0, min(1.0, ((t[0] - start_xy[0]) * dx + (t[1] - start_xy[1]) * dy)
                     / (span * span))) for t in tick_xys]) if span else [0.0, 1.0]
    max_gap = max((b - a) * span for a, b in zip(ts, ts[1:]))
    ok = max(residuals) <= corridor / 2.0 and max_gap <= span / 2.0
    return {"relevant_ticks": len(tick_xys), "residuals_pt": residuals,
            "off_chord_ticks": 0, "max_unsampled_pt": round(max_gap, 1),
            "straight": ok}
