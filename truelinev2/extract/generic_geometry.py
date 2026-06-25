"""Generic drawn-geometry dialect — the name-free placement FALLBACK for plans that match no
named (Brenham / ODOT) convention.

The named dialects isolate the proposed bore by a convention-specific signal (Brenham footage
grammar; ODOT's ``DIRECTIONAL BORE`` CAD layer). A general engineering plan from an unknown firm
has neither, so ``select_dialect`` returns ``None`` and the deterministic engine abstains. This
dialect is the evidence-based fallback: it reconstructs a *drawable* candidate run from the plan's
own generic vector geometry + station-label axis, with NO convention name and NO invented
coordinate — every emitted extent is projected from a real fitted station axis onto real drawn
segments.

It is REVIEW-grade by construction. It conforms to the ``PlanDialect`` Protocol (``match_mode =
"extent"``) so it runs through the EXISTING, tested ``run_match`` + ``decide_by_extent`` unchanged —
inheriting their span-coverage + uniqueness gates and REVIEW-capping. It is NEVER registered in the
global ``_DIALECTS``; only the uploaded-corpus adapter constructs it, and only AFTER the named
dialects decline, so the deterministic 50/58 path is provably byte-identical.

Heuristics brought forward from the v1 monolith (REVIEW-only, never an AUTO claim):
  * color-agnostic SHAPE gates (elongation / min axis-extent / max thickness) as the primary
    run detector, with a RED-bucket boost only (v1 pdf_extraction_classify color buckets);
  * endpoint union-find welding of dashed/segmented paths into one run (v1 pdf_extraction_routes
    group_route_candidates);
  * alignment-band + legend/title-block suppression so base linework / keys are not mistaken for
    the bore (ODOT alignment-band + generic legend detector, reused).

Geometry only. No I/O beyond the ``PlanPdf`` reader. Pure + deterministic, so re-running
``extract_callouts`` reproduces the same callouts AND the same traced centerlines.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from truelinev2.extract.legend import detect_legend_block, point_in_bbox
from truelinev2.extract.sheet_map import derive_offset
from truelinev2.extract.station_axis import StationAxis, fit_axis, parse_tick
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.schema.models import Callout
from truelinev2.stations import feet_to_station

# --- Shape-gate constants (color-AGNOSTIC; red is only a confidence boost, never required). ------ #
_ALIGN_BAND = 260.0          # display pts around the station-tick row = the alignment band
_WELD_EPS_PT = 7.0           # endpoint-adjacency tolerance for union-find welding of dash segments
_MIN_SEG_PT = 3.0            # drop sub-pixel speckle segments before welding
_MIN_RUN_LEN_PT = 36.0       # a welded run must be at least this long in display pts
_MIN_RUN_EXTENT_FT = 10.0    # ...and span at least this many feet on the fitted station axis
_MIN_ELONGATION = 4.0        # run length / run thickness: a bore run is a thin line, not a box/blob
_MAX_RUN_THICKNESS_PT = 34.0 # a run is thin; title-block / legend fills are thick
_AXIS_MAX_RESIDUAL_FT = 12.0 # reject a station-axis fit this noisy (not a real stationed alignment)
_MIN_AXIS_TICKS = 3          # need at least this many station ticks to trust the axis


def _key(bbox) -> Tuple[float, float, float, float]:
    """Stable rounded bbox key (deterministic lookup of a callout's traced centerline)."""
    return tuple(round(float(v), 1) for v in bbox)  # type: ignore[return-value]


def _is_reddish(color) -> bool:
    """True for a stroke whose RGB (fitz 0..1 triple) reads as red — a confidence BOOST only.
    Proposed construction is OFTEN drawn red, but NOT always, so red is never required."""
    if not color or len(color) < 3:
        return False
    r, g, b = float(color[0]), float(color[1]), float(color[2])
    return r >= 0.45 and r >= 1.6 * g and r >= 1.6 * b


def _segments_near_band(plan: PlanPdf, sheet: int, offset: int, tick_y: float,
                        legend: Optional[List[float]]) -> List[Dict[str, Any]]:
    """Every straight drawn line segment near the alignment band, legend/title-block suppressed.
    Drops vertical-dominant segments (station tick marks / leaders) so they do not weld into the
    run. Reuses ``line_items`` (true line geometry + CAD color), falling back to ``vector_segments``
    bbox edges only when a PDF exposes no straight-line items."""
    out: List[Dict[str, Any]] = []
    items = plan.line_items(sheet, offset)
    for it in items:
        color = it.get("color")
        for (ax, ay, bx, by) in it.get("lines") or ():
            mx, my = (ax + bx) / 2.0, (ay + by) / 2.0
            dx, dy = abs(bx - ax), abs(by - ay)
            length = (dx * dx + dy * dy) ** 0.5
            if length < _MIN_SEG_PT:
                continue
            if abs(my - tick_y) > _ALIGN_BAND:                 # alignment-band gate
                continue
            if dy > dx:                                        # vertical-dominant -> tick/leader, skip
                continue
            if legend is not None and point_in_bbox(mx, my, legend, pad=8.0):
                continue                                       # legend-block exclusion (defense)
            out.append({"a": (float(ax), float(ay)), "b": (float(bx), float(by)),
                        "mx": mx, "my": my, "len": length, "red": _is_reddish(color)})
    return out


class _UnionFind:
    """Tiny union-find for welding endpoint-adjacent dash segments into one run (v1 E2b)."""

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


def _weld_runs(segs: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    """Group segments whose endpoints touch (within ``_WELD_EPS_PT``) into runs (union-find)."""
    n = len(segs)
    uf = _UnionFind(n)
    eps2 = _WELD_EPS_PT * _WELD_EPS_PT
    pts = [(s["a"], s["b"]) for s in segs]
    for i in range(n):
        ai, bi = pts[i]
        for j in range(i + 1, n):
            aj, bj = pts[j]
            for p in (ai, bi):
                for q in (aj, bj):
                    if (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 <= eps2:
                        uf.union(i, j)
                        break
                else:
                    continue
                break
    groups: Dict[int, List[Dict[str, Any]]] = {}
    for i in range(n):
        groups.setdefault(uf.find(i), []).append(segs[i])
    return list(groups.values())


def _run_polyline(run: List[Dict[str, Any]]) -> List[Tuple[float, float]]:
    """Order a welded run's endpoints into a centerline polyline. Station axes are monotonic in x,
    so sort the unique endpoints by x (a coarse but honest trace; a back-folding run is flagged
    low-confidence elsewhere, never silently mis-drawn)."""
    pts: List[Tuple[float, float]] = []
    for s in run:
        pts.append(s["a"])
        pts.append(s["b"])
    uniq: List[Tuple[float, float]] = []
    for p in sorted(pts, key=lambda q: (round(q[0], 1), round(q[1], 1))):
        if not uniq or (abs(p[0] - uniq[-1][0]) > 0.5 or abs(p[1] - uniq[-1][1]) > 0.5):
            uniq.append(p)
    return uniq


class GenericGeometryDialect:
    """Name-free drawn-geometry fallback dialect (``match_mode = "extent"``). Construct fresh per
    engine run; ``extract_callouts`` populates the per-callout centerline + confidence-signal maps
    that the adapter reads back via ``centerline_for`` / ``signals_for``."""

    name = "generic"
    match_mode = "extent"

    def __init__(self) -> None:
        self._polys: Dict[Tuple[int, Tuple[float, float, float, float]], List[Tuple[float, float]]] = {}
        self._meta: Dict[Tuple[int, Tuple[float, float, float, float]], Dict[str, Any]] = {}

    # -- PlanDialect protocol ---------------------------------------------------------------- #
    def detect(self, plan: PlanPdf) -> bool:
        """True iff SOME page has a trustworthy station axis AND >= 1 run-like drawn extent. Scans
        raw pages (sheet = idx + 1, offset = 0); conservative — abstains on a bare/striped sheet
        rather than guessing. Offset-independent like every dialect detector."""
        for idx in range(plan.page_count):
            if self.extract_callouts(plan, idx + 1, 0):
                return True
        return False

    def calibrate(self, plan: PlanPdf, default_offset: int) -> int:
        off, _ev = derive_offset(plan)
        return off if off is not None else default_offset

    def extract_callouts(self, plan: PlanPdf, sheet: int, offset: int) -> List[Callout]:
        words = plan.words(sheet, offset)
        if not words:
            return []
        tick_words = [w for w in words if parse_tick(w["text"]) is not None]
        if len(tick_words) < _MIN_AXIS_TICKS:
            return []
        axis = fit_axis([(w["xc"], parse_tick(w["text"])) for w in tick_words])
        if axis is None or axis.residual_ft > _AXIS_MAX_RESIDUAL_FT:
            return []
        tick_y = sum(w["yc"] for w in tick_words) / len(tick_words)
        legend = detect_legend_block(words)

        segs = _segments_near_band(plan, sheet, offset, tick_y, legend)
        if not segs:
            return []
        runs = _weld_runs(segs)

        candidates: List[Dict[str, Any]] = []
        for run in runs:
            xs = [p[0] for s in run for p in (s["a"], s["b"])]
            ys = [p[1] for s in run for p in (s["a"], s["b"])]
            x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
            length = max(x1 - x0, 1e-6)
            thickness = max(y1 - y0, 1e-6)
            if length < _MIN_RUN_LEN_PT or thickness > _MAX_RUN_THICKNESS_PT:
                continue
            if length / thickness < _MIN_ELONGATION:
                continue
            sa, sb = axis.station_at(x0), axis.station_at(x1)
            f0, f1 = (sa, sb) if sa <= sb else (sb, sa)
            if (f1 - f0) < _MIN_RUN_EXTENT_FT:
                continue
            candidates.append({"bbox": [x0, y0, x1, y1], "from_ft": f0, "to_ft": f1,
                               "poly": _run_polyline(run), "len": length,
                               "red": any(s["red"] for s in run)})

        out: List[Callout] = []
        n_red = sum(1 for c in candidates if c["red"])
        for c in candidates:
            f0, f1 = c["from_ft"], c["to_ft"]
            callout = Callout(
                sheet=sheet, page=sheet + offset,
                from_sta=feet_to_station(f0), to_sta=feet_to_station(f1),
                from_ft=round(f0, 1), to_ft=round(f1, 1), footage=round(f1 - f0, 1),
                conduit=None, vacant=False, footage_verified=False,
                text="DRAWN RUN (generic geometry) %s->%s%s"
                     % (feet_to_station(f0), feet_to_station(f1), " [red]" if c["red"] else ""),
                bbox=c["bbox"], dialect="generic")
            k = (sheet, _key(c["bbox"]))
            self._polys[k] = c["poly"]
            self._meta[k] = {"axis_residual_ft": axis.residual_ft, "axis_ticks": len(tick_words),
                             "is_red": c["red"], "run_len_pt": c["len"],
                             "rival_runs": len(candidates), "red_runs": n_red}
            out.append(callout)
        return out

    # -- adapter read-back (deterministic; recomputed from the same extract) ------------------ #
    def centerline_for(self, callout: Callout) -> Optional[List[List[float]]]:
        """The traced centerline polyline for a callout this dialect emitted (>= 2 points), or None
        if it has no trustworthy trace (caller renders the bbox-corner location indicator instead)."""
        if not callout.bbox:
            return None
        poly = self._polys.get((callout.sheet, _key(callout.bbox)))
        if not poly or len(poly) < 2:
            return None
        return [[float(x), float(y)] for (x, y) in poly]

    def signals_for(self, callout: Callout) -> Dict[str, Any]:
        """Confidence signals for a callout this dialect emitted (axis residual, tick count, red
        boost, rival-run count). Empty dict if unknown."""
        if not callout.bbox:
            return {}
        return dict(self._meta.get((callout.sheet, _key(callout.bbox)), {}))
