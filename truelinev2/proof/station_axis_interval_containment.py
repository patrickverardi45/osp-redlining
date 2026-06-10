r"""M8.7 -- station-axis interval containment / path-walk solver (pure, proof-only).

Field doctrine (Patrick, 2026-06-10): "end station not found" is WRONG when the
station exists as an AXIS TICK or path measurement. Evidence classes for a bore
endpoint, in decreasing directness:
  1. callout endpoint        (authored run END -- M8.5's anchor)
  2. structure endpoint      (HH / flower pot / terminal -- M8.6 origins)
  3. station-axis tick       (a drawn tick like ``31+00`` ON the design path)
  4. interval-contained      (inside a larger authored callout interval)
  5. path-walk               (across sheets along the continuing station axis)

This module proves classes 3-5: locate the bore END as a tick on the station
axis, identify the TRUNK tick ladder it belongs to (each sheet also carries
local-frame tick clusters -- never collapsed), prove sheet-to-sheet ladder
continuity by SHARED boundary ticks (the plan draws the same trunk station at
both sides of a sheet join -- e.g. 30+64 on sheets 7 AND 8), then walk backward
``span_ft`` over the authored callout intervals that live INSIDE that ladder,
allowing the end to sit INTERIOR to the last interval (containment, class 4).

Tolerances are EXISTING engine constants only (chains start_tol/link_tol,
decide review_end -- re-cited via match.reverse_anchor; pinned by tests). The
single structural parameter is the tick-cluster split gap: ticks are authored
on a 100-ft interval, so a >2-interval gap separates clusters -- it groups axis
labels and never accepts/rejects a placement by proximity.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from truelinev2.match.decide import tolerances
from truelinev2.match.reverse_anchor import LINK_TOL_FT, START_TOL_FT
from truelinev2.schema.models import Callout
from truelinev2.stations import feet_to_station

# The six allowed verdicts (fixed taxonomy).
READY = "INTERVAL_PATH_READY_FOR_REVIEW_OPTIN"
PICK_CARD = "MULTIPLE_PATHS_PICK_CARD"
TICK_NOT_FOUND = "STATION_TICK_NOT_FOUND"
DISCONTINUITY = "PATH_DISCONTINUITY"
FOOTAGE_MISMATCH = "FOOTAGE_MISMATCH"
FRAME_CONFLICT = "FRAME_OR_SHEET_CONFLICT"
VERDICTS = (READY, PICK_CARD, TICK_NOT_FOUND, DISCONTINUITY, FOOTAGE_MISMATCH, FRAME_CONFLICT)

# Plan tick ladders are authored every 100 ft; a gap of more than two intervals
# splits distinct ladders (trunk vs local-frame clusters on the same sheet).
# Structural grouping of axis labels -- NOT a matching tolerance.
TICK_INTERVAL_FT = 100.0
CLUSTER_GAP_FT = 2.0 * TICK_INTERVAL_FT


@dataclass(frozen=True)
class TickCluster:
    """One contiguous tick ladder on one sheet (a station FRAME's drawn axis)."""
    sheet: int
    ticks: Tuple[float, ...]  # sorted ascending

    @property
    def lo(self) -> float:
        return self.ticks[0]

    @property
    def hi(self) -> float:
        return self.ticks[-1]

    def contains(self, ft: float, slack: float = 0.0) -> bool:
        return self.lo - slack <= ft <= self.hi + slack

    def to_dict(self) -> dict:
        return {"sheet": self.sheet, "lo": self.lo, "hi": self.hi, "n": len(self.ticks)}


def tick_clusters(tick_values: Sequence[float], sheet: int) -> List[TickCluster]:
    """Split a sheet's tick values into contiguous ladders. Distinct clusters are
    distinct frames' axes -- NEVER merged (the M8.6 no-collapse doctrine applied
    to drawn axes)."""
    vals = sorted({float(v) for v in tick_values})
    if not vals:
        return []
    out: List[List[float]] = [[vals[0]]]
    for v in vals[1:]:
        if v - out[-1][-1] > CLUSTER_GAP_FT:
            out.append([v])
        else:
            out[-1].append(v)
    return [TickCluster(sheet=sheet, ticks=tuple(c)) for c in out]


def build_ladder(clusters_by_sheet: Dict[int, List[TickCluster]],
                 end_ft: float, target_start_ft: float
                 ) -> Tuple[List[TickCluster], List[dict]]:
    """The TRUNK ladder: starting from the cluster(s) containing ``end_ft``,
    chain backward through clusters on OTHER sheets that share a boundary tick
    (the same trunk station drawn on both sheets of a join) until the ladder
    covers ``target_start_ft`` or no shared-tick continuation exists.

    Returns (ladder lo->hi ordered, join evidence). Continuity is proven ONLY by
    a shared NON-ROUND tick value: round ticks (0, 100, 200, ...) repeat in every
    local frame, so two sheets sharing only round values is raw coincidence (the
    M8.2d trap at tick level); a shared non-round station (a matchline/interval
    boundary like 30+64 drawn on BOTH sheets of a join) is the plan asserting the
    SAME physical axis continues."""
    all_clusters = [c for cs in clusters_by_sheet.values() for c in cs]
    seeds = [c for c in all_clusters if c.contains(end_ft)]
    if not seeds:
        return [], []
    # prefer the seed whose sheet carries the exact end tick; deterministic order
    seeds.sort(key=lambda c: (end_ft not in c.ticks, c.sheet))
    ladder = [seeds[0]]
    joins: List[dict] = []
    while ladder[0].lo > target_start_ft:
        head = ladder[0]
        shared = []
        for c in all_clusters:
            if c.sheet == head.sheet or c in ladder or c.lo >= head.lo:
                continue
            common = sorted(v for v in set(c.ticks) & set(head.ticks)
                            if v % TICK_INTERVAL_FT != 0)
            if common:
                shared.append((c, common))
        if not shared:
            break
        # deterministic: the candidate reaching furthest down, then lowest sheet
        shared.sort(key=lambda t: (t[0].lo, t[0].sheet))
        nxt, common = shared[0]
        joins.append({"sheets": (nxt.sheet, head.sheet),
                      "shared_nonround_ticks": [feet_to_station(v) for v in common]})
        ladder.insert(0, nxt)
    return ladder, joins


def frame_ambiguous_seeds(clusters_by_sheet: Dict[int, List[TickCluster]],
                          end_ft: float, ladder: Sequence[TickCluster]) -> List[dict]:
    """Clusters OUTSIDE the proven ladder that also contain the bore end value:
    each is a DIFFERENT frame where the same raw number exists. Any such rival
    frame makes a raw end-value claim ambiguous (never collapse frames)."""
    in_ladder = {(c.sheet, c.lo, c.hi) for c in ladder}
    return [c.to_dict() for cs in clusters_by_sheet.values() for c in cs
            if c.contains(end_ft) and (c.sheet, c.lo, c.hi) not in in_ladder]


def intervals_in_ladder(callouts: Sequence[Callout], ladder: Sequence[TickCluster],
                        slack: float = LINK_TOL_FT) -> List[Callout]:
    """Authored callout intervals that live INSIDE the ladder's drawn axis on
    their own sheet -- frame ownership by axis containment (a local-frame
    interval whose values fall outside its sheet's trunk cluster is excluded,
    so two frames' station numbers are never mixed)."""
    by_sheet = {c.sheet: c for c in ladder}
    out = []
    for c in callouts:
        cl = by_sheet.get(c.sheet)
        if cl is not None and cl.contains(c.from_ft, slack) and cl.contains(c.to_ft, slack):
            out.append(c)
    return out


def coverage_walk(intervals: Sequence[Callout], end_ft: float, span_ft: float,
                  *, link_tol: float = LINK_TOL_FT) -> dict:
    """Walk backward ``span_ft`` from ``end_ft`` over interval coverage. The end
    may sit INTERIOR to an interval (containment); joins must be contiguous
    within the existing link tolerance. Station math is pure footage math on the
    SAME (ladder-proven) axis, so no frame translation is needed or applied."""
    expected_start = round(end_ft - span_ft, 2)
    holding = [c for c in intervals if c.from_ft - link_tol <= end_ft <= c.to_ft + link_tol]
    if not holding:
        return {"complete": False, "reason": "end_not_in_any_ladder_interval",
                "expected_start_ft": expected_start, "chain": [], "reached_ft": None}
    paths = []
    for h in holding:
        chain = [h]
        reached = h.from_ft
        # stop once the authored boundary is within the EXISTING start tolerance
        # of the expected start -- never over-extend past containment.
        while reached > expected_start + START_TOL_FT:
            preds = [c for c in intervals
                     if all(c is not x for x in chain)
                     and abs(c.to_ft - reached) <= link_tol and c.from_ft < reached]
            if not preds:
                break
            preds.sort(key=lambda c: (c.from_ft, c.sheet, c.text))
            chain.insert(0, preds[0])
            reached = preds[0].from_ft
        paths.append({"chain": chain, "reached_ft": round(reached, 2)})
    paths.sort(key=lambda p: p["reached_ft"])
    best = paths[0]
    complete = best["reached_ft"] <= expected_start + START_TOL_FT
    return {"complete": complete, "expected_start_ft": expected_start,
            "chain": best["chain"], "reached_ft": best["reached_ft"],
            "boundary_residual_ft": round(best["reached_ft"] - expected_start, 2),
            "n_holding_intervals": len(holding),
            "holding": [c.text for c in holding]}


def prove_interval_path(*, bore_id: str, bore_start_ft: float, bore_end_ft: float,
                        span_ft: float, ticks_by_sheet: Dict[int, Sequence[float]],
                        callouts: Sequence[Callout],
                        sheet_refs: Sequence[int] = ()) -> Dict[str, object]:
    """The full M8.7 proof for one bore. Returns a verdict dict; NEVER a
    placement, NEVER AUTO; every non-READY names the missing relationship.
    ``sheet_refs`` (the bore log's own print column) scopes the claim: adjacent
    sheets may CONTINUE a path, but a claim living ENTIRELY off the referenced
    sheets is never READY (print-scope guard)."""
    tol = tolerances(span_ft)
    base: Dict[str, object] = {
        "bore_id": bore_id,
        "bore_start_sta": feet_to_station(bore_start_ft),
        "bore_end_sta": feet_to_station(bore_end_ft),
        "span_ft": span_ft, "never_auto": True,
    }
    clusters = {s: tick_clusters(v, s) for s, v in ticks_by_sheet.items()}
    base["clusters"] = {s: [c.to_dict() for c in cs] for s, cs in clusters.items()}

    # class-3 evidence: the bore end as an axis tick (existing review band only)
    end_ticks = [(s, v) for s, cs in clusters.items() for c in cs for v in c.ticks
                 if abs(v - bore_end_ft) <= tol["review_end"]]
    base["end_axis_ticks"] = [(s, feet_to_station(v)) for s, v in end_ticks]
    holding_clusters = [c for cs in clusters.values() for c in cs if c.contains(bore_end_ft)]
    if not end_ticks and not holding_clusters:
        nearest = min((abs(v - bore_end_ft) for vs in ticks_by_sheet.values() for v in vs),
                      default=None)
        base["named_missing_relationship"] = (
            f"bore end {feet_to_station(bore_end_ft)} is neither an axis tick (nearest "
            f"tick {nearest} ft away) nor inside any drawn tick ladder on the bore's "
            f"sheets -- the next solver needs vision/crop inspection of the path or a "
            f"frame-binding datum")
        return {**base, "result": TICK_NOT_FOUND}

    expected_start = round(bore_end_ft - span_ft, 2)
    ladder, joins = build_ladder(clusters, bore_end_ft, expected_start)
    base["ladder"] = [c.to_dict() for c in ladder]
    base["sheet_joins"] = joins
    base["sheets_crossed"] = sorted({c.sheet for c in ladder})
    # never collapse frames: any OTHER cluster (a different frame's axis) that
    # also contains the raw end value makes the claim frame-ambiguous.
    rivals = frame_ambiguous_seeds(clusters, bore_end_ft, ladder)
    base["rival_frames_containing_end"] = rivals
    if rivals:
        base["named_missing_relationship"] = (
            f"the raw end value {feet_to_station(bore_end_ft)} exists in "
            f"{len(rivals)} OTHER frame ladder(s) ({[(r['sheet'], r['lo'], r['hi']) for r in rivals]}) "
            f"besides the proven one -- a raw station number cannot pick a frame; "
            f"the next solver needs frame ownership evidence (structure identity, "
            f"print-scoped axis, or a human pick-card)")
        return {**base, "result": FRAME_CONFLICT}
    if not ladder or ladder[0].lo > expected_start + START_TOL_FT:
        reached = ladder[0].lo if ladder else None
        base["named_missing_relationship"] = (
            f"the trunk tick ladder containing the end reaches down only to "
            f"{feet_to_station(reached) if reached is not None else 'nowhere'} but the "
            f"computed start is {feet_to_station(expected_start)}; no sheet shares a "
            f"boundary tick to continue the axis -- the next solver needs the missing "
            f"sheet's ticks (or a frame equation) to prove path continuity")
        return {**base, "result": DISCONTINUITY}

    ivs = intervals_in_ladder(callouts, ladder)
    base["ladder_intervals"] = [c.text for c in ivs]
    walk = coverage_walk(ivs, bore_end_ft, span_ft)
    base["walk"] = {k: ([c.text for c in v] if k == "chain" else v)
                    for k, v in walk.items()}
    if walk["chain"] and walk.get("n_holding_intervals", 0) > 1:
        base["named_missing_relationship"] = (
            f"{walk['n_holding_intervals']} distinct ladder intervals each contain the "
            f"bore end ({walk['holding']}); coverage cannot pick one -- human pick-card "
            f"or a structure/identity discriminator")
        return {**base, "result": PICK_CARD}
    if not walk["complete"]:
        if not walk["chain"]:
            base["named_missing_relationship"] = (
                f"the end lies on the ladder but inside NO authored interval; the next "
                f"solver must consume the drawn path geometry (vector layer), not text")
            return {**base, "result": FOOTAGE_MISMATCH}
        base["named_missing_relationship"] = (
            f"interval coverage walks back only to {feet_to_station(walk['reached_ft'])} "
            f"-- {walk['boundary_residual_ft']} ft of bore footage has no authored "
            f"interval behind it on the ladder; the next solver must find the missing "
            f"authored interval or prove unauthored extent")
        return {**base, "result": FOOTAGE_MISMATCH}

    chain_sheets = {c.sheet for c in walk["chain"]} if walk["chain"] else set()
    if sheet_refs and not (chain_sheets & set(sheet_refs)):
        base["named_missing_relationship"] = (
            f"the proven path lives entirely on sheet(s) {sorted(chain_sheets)} but the "
            f"bore log's print column references {sorted(sheet_refs)} -- an off-print "
            f"claim needs print-scope evidence (a corrected print value or a structure "
            f"identity) before it may place")
        return {**base, "result": FRAME_CONFLICT}

    start_delta = round(abs(expected_start - bore_start_ft), 2)
    base["computed_start_sta"] = feet_to_station(expected_start)
    base["start_delta_vs_borelog_ft"] = start_delta
    base["authored_boundary_residual_ft"] = walk["boundary_residual_ft"]
    if start_delta > START_TOL_FT:
        base["named_missing_relationship"] = (
            f"computed start {feet_to_station(expected_start)} disagrees with the "
            f"bore-log start {feet_to_station(bore_start_ft)} by {start_delta} ft -- "
            f"implied frame offset; needs a bore-frame binding datum")
        return {**base, "result": FRAME_CONFLICT}

    caveats = ["STATION_AXIS_INTERVAL_PATH", "NEVER_AUTO_BY_CONSTRUCTION"]
    if not end_ticks:
        caveats.append("END_INSIDE_LADDER_NO_EXACT_TICK")
    if joins:
        caveats.append("SHARED_TICK_SHEET_JOINS")
    if walk["boundary_residual_ft"] > 0:
        caveats.append("START_AT_AUTHORED_BOUNDARY_RESIDUAL")
    return {**base, "result": READY, "caveats": caveats, "review_gated_only": True}
