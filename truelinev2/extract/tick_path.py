r"""M8.14 -- clean route-ladder tick-path solver (pure; uniqueness-mandatory).

The product deliverable is a VISIBLE redline stroke along the design route
from the bore-log start station to the bore-log end station. Plans author the
route's station ladder ON the alignment, so a chain of positioned DRAWN ticks
traces the route at station-tick resolution -- real extracted geometry.

Two failure modes were proven by the M8.14.a proof and are gated here:

1. CALLOUT TEXT POLLUTION. Bare ``parse_tick`` over all words matches station
   tokens INSIDE callout/note text boxes; chains through them draw misleading
   zig-zag strokes through labels instead of the route. The deterministic
   classifier: drawn route ladders are authored as ALL-TICK text blocks (zero
   alphabetic words -- e.g. ``1+00 2+00 3+00 4+00 5+00 6+00`` in one block
   along the street); callout/note station tokens share blocks with words.
   Stroke construction uses LADDER-BLOCK ticks ONLY.

2. STRUCTURE-OWNED ENDPOINTS. Local-frame origins (``STA X=0+00``) are
   STRUCTURES (installer HH / terminal HH / flower pot), not drawn ticks, and
   multiple rival structures coexist per sheet; metric gates can bind the
   WRONG one (proven: ladder-extrapolation consistency selects 2+22=0+00 over
   log7's true 0+55=0+00). Binding the correct structure to the correct bore
   frame is the named STRUCTURE-IDENTITY BINDING solver -- NOT implemented
   here. When a span endpoint falls outside the clean ladder, this solver
   ABSTAINS with that named relationship; it never guesses an anchor.

Chain safety (M8.5-style, abstain-first): station-monotonic hops, each hop's
points-per-foot scale consistent with the chain's running upper-median; hops
go to the NEAREST next consistent station (consistent ticks are never
skipped); same-station ties BRANCH; uniqueness is judged on the TRIMMED
STROKE GEOMETRY (lead-in differences are one answer); exactly ONE distinct
stroke -> READY, else the named abstain. No v1 import; no production import.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from truelinev2.extract.station_axis import parse_tick

# Probe-calibrated constants (2026-06-10 feasibility + r2 ladder probes).
# Widening is forbidden; tightening is a future named decision.
SCALE_REL_TOL = 0.35   # max relative deviation of a hop's pts/ft from the chain median
MAX_GAP_FT = 600.0     # max station gap a single hop may bridge
MAX_EXPANSIONS = 20000

READY = "TICK_PATH_READY"
MULTIPLE = "MULTIPLE_ROUTE_TICK_CHAINS"
NOT_COVERED = "ROUTE_TICK_LADDER_SPAN_NOT_COVERED"
STRUCTURE_REQUIRED = "STRUCTURE_IDENTITY_BINDING_REQUIRED"
EXHAUSTED = "TICK_PATH_SEARCH_EXHAUSTED"


@dataclass(frozen=True)
class Tick:
    station_ft: float
    x: float
    y: float


def ladder_ticks_from_words(words: Sequence[dict]) -> Tuple[List[Tick], Dict[str, int]]:
    """Classify positioned words into clean route-LADDER ticks vs excluded
    callout/note station tokens. A drawn ladder is an ALL-TICK text block:
    every word in the block parses as a station tick and none contains an
    alphabetic character. Returns (clean ticks, honest counts)."""
    by_block: Dict[int, List[dict]] = {}
    for w in words:
        by_block.setdefault(int(w.get("block", -1)), []).append(w)
    clean: List[Tick] = []
    raw = excluded = 0
    for ws in by_block.values():
        all_ticks = all(parse_tick(w["text"]) is not None for w in ws)
        for w in ws:
            v = parse_tick(w["text"])
            if v is None:
                continue
            raw += 1
            if all_ticks:
                clean.append(Tick(float(v), float(w["xc"]), float(w["yc"])))
            else:
                excluded += 1  # station token inside callout/note text
    counts = {"raw_tick_tokens": raw, "excluded_text_tokens": excluded,
              "clean_ladder_ticks": len(clean)}
    return clean, counts


def route_ladder_ticks(plan, sheet: int, offset: int) -> Tuple[List[Tick], Dict[str, int]]:
    """Clean route-ladder ticks for a sheet (positions ``plan.words`` already
    carries; the block id separates drawn ladders from text tokens)."""
    return ladder_ticks_from_words(plan.words(sheet, offset))


@dataclass(frozen=True)
class TickPathVerdict:
    """The solver's typed answer. ``stroke_points`` is non-None ONLY for READY
    (trimmed: interpolated start point, interior ladder ticks, interpolated
    end point). Never a placement; drawing on a non-READY verdict is forbidden."""
    bore_id: str
    sheet: int
    result: str
    start_ft: float
    end_ft: float
    chain: Tuple[Tick, ...] = ()
    stroke_points: Optional[Tuple[Tuple[float, float], ...]] = None
    start_point: Optional[Tuple[float, float]] = None
    end_point: Optional[Tuple[float, float]] = None
    hop_scales: Tuple[float, ...] = ()
    strokes_found: int = 0
    named_missing_relationship: Optional[str] = None
    detail: dict = field(default_factory=dict)

    @property
    def endpoint_type(self) -> str:
        return ("interpolated_from_tick_ladder" if self.result == READY
                else "abstained")

    def to_dict(self) -> dict:
        return {
            "bore_id": self.bore_id, "sheet": self.sheet, "result": self.result,
            "start_ft": self.start_ft, "end_ft": self.end_ft,
            "endpoint_type": self.endpoint_type,
            "chain": [(t.station_ft, round(t.x, 1), round(t.y, 1)) for t in self.chain],
            "stroke_points": ([[round(x, 1), round(y, 1)] for x, y in self.stroke_points]
                              if self.stroke_points else None),
            "start_point": list(self.start_point) if self.start_point else None,
            "end_point": list(self.end_point) if self.end_point else None,
            "hop_scales": [round(s, 3) for s in self.hop_scales],
            "strokes_found": self.strokes_found,
            "named_missing_relationship": self.named_missing_relationship,
            "detail": self.detail,
        }


def _upper_median(xs: Sequence[float]) -> float:
    return sorted(xs)[len(xs) // 2]


def _scale_ok(scale: float, scales: Sequence[float], rel_tol: float) -> bool:
    if not scales:
        return True  # first hop establishes the chain's frame scale
    med = _upper_median(scales)
    return med > 0 and abs(scale - med) / med <= rel_tol


def _interp(lo: Tick, hi: Tick, v: float) -> Tuple[float, float]:
    t = 0.0 if hi.station_ft == lo.station_ft else (v - lo.station_ft) / (hi.station_ft - lo.station_ft)
    return (lo.x + (hi.x - lo.x) * t, lo.y + (hi.y - lo.y) * t)


def _trimmed_stroke(chain: Sequence[Tick], start_ft: float, end_ft: float
                    ) -> Optional[Tuple[Tuple[float, float], ...]]:
    """Interpolated start point + interior ticks strictly inside the span +
    interpolated end point. None if either endpoint is not bracketed by
    adjacent chain ticks."""
    def bracket(v: float) -> Optional[Tuple[Tick, Tick]]:
        for a, b in zip(chain, chain[1:]):
            if a.station_ft <= v <= b.station_ft:
                return a, b
        return None

    lo = bracket(start_ft)
    hi = bracket(end_ft)
    if lo is None or hi is None:
        return None
    pts: List[Tuple[float, float]] = [_interp(lo[0], lo[1], start_ft)]
    pts += [(t.x, t.y) for t in chain if start_ft < t.station_ft < end_ft]
    pts.append(_interp(hi[0], hi[1], end_ft))
    return tuple(pts)


def solve_tick_path(*, bore_id: str, sheet: int, start_ft: float, end_ft: float,
                    ticks: Sequence[Tick],
                    scale_rel_tol: float = SCALE_REL_TOL,
                    max_gap_ft: float = MAX_GAP_FT,
                    max_expansions: int = MAX_EXPANSIONS) -> TickPathVerdict:
    """All station-monotonic, scale-consistent CLEAN-LADDER chains covering
    [start_ft, end_ft]; READY iff exactly ONE distinct trimmed stroke.
    ``ticks`` must be clean route-ladder ticks (``route_ladder_ticks``) --
    callout/note tokens are never valid stroke material."""
    base = dict(bore_id=bore_id, sheet=sheet, start_ft=start_ft, end_ft=end_ft)
    seeds = [t for t in ticks
             if t.station_ft <= start_ft and start_ft - t.station_ft <= max_gap_ft]
    if not seeds:
        low = min((t.station_ft for t in ticks), default=None)
        named = (f"the bore start {start_ft} ft lies below the clean route "
                 f"ladder's lowest reachable tick on sheet {sheet} "
                 f"(lowest ladder tick: {low}); the start endpoint is a "
                 f"local-frame origin owned by a STRUCTURE (installer HH / "
                 f"terminal HH / flower pot), not a drawn tick -- binding the "
                 f"correct structure to this bore's frame requires the "
                 f"structure-identity binding solver; guessing an anchor is "
                 f"forbidden")
        return TickPathVerdict(**base, result=STRUCTURE_REQUIRED,
                               named_missing_relationship=named)

    budget = {"left": max_expansions, "exhausted": False}
    complete: List[Tuple[Tuple[Tick, ...], Tuple[float, ...]]] = []
    best_reach = {"station": max(s.station_ft for s in seeds)}

    def extend(chain: List[Tick], scales: List[float]) -> None:
        if budget["left"] <= 0:
            budget["exhausted"] = True
            return
        budget["left"] -= 1
        last = chain[-1]
        best_reach["station"] = max(best_reach["station"], last.station_ft)
        if last.station_ft >= end_ft:
            complete.append((tuple(chain), tuple(scales)))
            return  # covered: never extend past the span (M8.5 containment rule)
        consistent: List[Tuple[Tick, float]] = []
        for t in ticks:
            ds = t.station_ft - last.station_ft
            if ds <= 0 or ds > max_gap_ft:
                continue
            sc = math.hypot(t.x - last.x, t.y - last.y) / ds
            if _scale_ok(sc, scales, scale_rel_tol):
                consistent.append((t, sc))
        if not consistent:
            return
        # nearest next CONSISTENT station; never skip a consistent tick;
        # same-station ties branch (real ambiguity is explored, not chosen)
        min_ds = min(t.station_ft - last.station_ft for t, _ in consistent)
        for t, sc in consistent:
            if t.station_ft - last.station_ft == min_ds:
                extend(chain + [t], scales + [sc])

    for s in sorted(seeds, key=lambda t: (start_ft - t.station_ft, t.x, t.y)):
        extend([s], [])

    if budget["exhausted"]:
        named = (f"the tick-chain search exhausted its expansion budget "
                 f"({max_expansions}) before completing -- uniqueness cannot be "
                 f"claimed from an incomplete search; reduce duplicate ticks or "
                 f"raise the budget, then re-prove")
        return TickPathVerdict(**base, result=EXHAUSTED,
                               named_missing_relationship=named)

    # uniqueness on the TRIMMED STROKE: lead-in differences are one answer
    strokes: dict = {}
    for chain, scales in complete:
        pts = _trimmed_stroke(chain, start_ft, end_ft)
        if pts is None:
            continue
        sig = tuple((round(x, 1), round(y, 1)) for x, y in pts)
        strokes.setdefault(sig, (chain, scales, pts))

    if not strokes:
        named = (f"no scale-consistent clean-ladder chain on sheet {sheet} covers "
                 f"the bore span {start_ft}->{end_ft} ft (chains reached "
                 f"{best_reach['station']} ft); the route's drawn tick ladder does "
                 f"not span the bore here -- the next solver needs the missing "
                 f"drawn ticks, a matchline continuation, or an END structure "
                 f"anchor (structure-identity binding); drawing anyway is forbidden")
        return TickPathVerdict(**base, result=NOT_COVERED,
                               named_missing_relationship=named,
                               detail={"complete_chains": len(complete)})

    if len(strokes) >= 2:
        named = (f"{len(strokes)} distinct scale-consistent clean-ladder paths each "
                 f"cover the bore span on sheet {sheet} -- per the M8.3a law "
                 f"physically distinct geometry is never tiebroken; the next solver "
                 f"needs a frame discriminator (structure identity, callout-anchored "
                 f"frame choice, or a human pick); no stroke is drawn")
        return TickPathVerdict(**base, result=MULTIPLE, strokes_found=len(strokes),
                               named_missing_relationship=named,
                               detail={"stroke_starts": [list(s[0]) for s in strokes]})

    chain, scales, pts = next(iter(strokes.values()))
    return TickPathVerdict(**base, result=READY, chain=chain, stroke_points=pts,
                           start_point=pts[0], end_point=pts[-1],
                           hop_scales=scales, strokes_found=1)
