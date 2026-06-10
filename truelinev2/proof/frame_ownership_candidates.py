r"""M8.9 -- frame ownership for local-frame bores (pure, proof-only).

The largest remaining abstain class (23 logs) is FRAME_OR_SHEET_CONFLICT: the
bore's raw station values exist in MULTIPLE sheets' local frames, and a raw
number can never pick a frame. This module asks whether the evidence already
banked can: M8.6 structure origins (``STA X=0+00`` -- a local frame SEEDED at a
physical structure), M8.7 tick ladders/interval coverage (does a frame's drawn
axis actually SUPPORT the bore span?), print scope, and HH-HH distance notes.

Product doctrine (Patrick, 2026-06-10): the engine does not need to auto-place
100%. Remaining abstains are CLASSIFIED, not failed:
  FRAME_OWNERSHIP_READY_FOR_REVIEW_OPTIN  -- exactly one frame proven
  PICK_CARD_ROUTE_SUGGESTION              -- 2-3 plausible frames, each a labeled
                                             SUGGESTION (never a placement)
  HUMAN_ADJUSTABLE_LENGTH_REDLINE         -- footage is certain, frame is not:
                                             a reviewer-draggable redline object
  SOURCE_REVIEW_REQUIRED                  -- the bore log's own numbers look wrong
  UNSAFE_NO_UNIQUE_FRAME                  -- abstain with the named relationship

A frame CANDIDATE is one sheet-local tick cluster (M8.7) on a REFERENCED sheet
whose drawn axis covers the bore's values; it SUPPORTS the bore when the M8.7
coverage walk completes inside it (authored intervals contiguously contain the
span within EXISTING tolerances -- nothing widened, no translation, no blanket
M8.2d revival, frames never collapsed)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from truelinev2.match.decide import tolerances
from truelinev2.match.reverse_anchor import LINK_TOL_FT, START_TOL_FT
from truelinev2.match.reverse_anchor import matchline_mask
from truelinev2.match.station_axis_interval import (
    TickCluster,
    coverage_walk,
    tick_clusters,
)
from truelinev2.schema.frames import FrameEquation
from truelinev2.proof.station_equation_ownership import (
    StructureOrigin,
    extract_reset_origins,
    parse_hh_distances,
)
from truelinev2.schema.models import Callout
from truelinev2.stations import feet_to_station

READY = "FRAME_OWNERSHIP_READY_FOR_REVIEW_OPTIN"
PICK_CARD = "PICK_CARD_ROUTE_SUGGESTION"
ADJUSTABLE = "HUMAN_ADJUSTABLE_LENGTH_REDLINE"
SOURCE_REVIEW = "SOURCE_REVIEW_REQUIRED"
UNSAFE = "UNSAFE_NO_UNIQUE_FRAME"
VERDICTS = (READY, PICK_CARD, ADJUSTABLE, SOURCE_REVIEW, UNSAFE)

# Pick-cards stay human-sized: 2-3 candidates is a decidable card; more is not.
MAX_PICK_CARD_CANDIDATES = 3

# Banked human grades (the M8.2j/M8.2l ledger pattern): a human already judged
# these ties; no solver may override a banked TIE with a new route reading.
BANKED_HUMAN_TIES = {
    "log48": ("M8.3a run-identity tiebreaker NOT_READY -- two physically distinct "
              "routes (s11 TOM GREEN vs s12 LEDBETTER fiber-drop terminations), "
              "both plausible; banked human pick-card"),
}


@dataclass(frozen=True)
class FrameCandidate:
    """One sheet-local frame (a tick cluster) that might own the bore's values,
    with the evidence gathered for/against it."""
    sheet: int
    cluster_lo: float
    cluster_hi: float
    walk_complete: bool
    chain_texts: Tuple[str, ...]
    reached_ft: Optional[float]
    n_holding_intervals: int        # intervals containing the bore end IN this frame
    origin: Optional[dict]          # the M8.6 reset origin seeding this frame, if any
    hh_note_matches_span: bool
    on_referenced_sheet: bool

    end_evidence: Optional[str] = None  # tick/callout-end evidence, None = containment-only

    @property
    def unique_path(self) -> bool:
        """Frame-unique is NOT route-unique: a frame holding the end in >= 2
        intervals (e.g. parallel drop lanes) is a pick-card, never READY."""
        return self.walk_complete and self.n_holding_intervals == 1

    @property
    def ready_grade(self) -> bool:
        """READY needs POSITIVE end evidence in the owned frame (an axis tick or
        an authored callout END near the bore end). Mere interval containment is
        suggestion-grade: with many 0-starting local frames, an [0..X] bore will
        'complete' in whichever frame happens to be best-authored -- that is
        closest-looking geometry, not proof."""
        return self.unique_path and self.end_evidence is not None

    def to_dict(self) -> dict:
        return {"sheet": self.sheet, "cluster": (self.cluster_lo, self.cluster_hi),
                "walk_complete": self.walk_complete, "chain": list(self.chain_texts),
                "reached_ft": self.reached_ft,
                "n_holding_intervals": self.n_holding_intervals,
                "unique_path": self.unique_path, "origin": self.origin,
                "hh_note_matches_span": self.hh_note_matches_span,
                "on_referenced_sheet": self.on_referenced_sheet,
                "label": "SUGGESTION_NOT_PLACEMENT"}


def _origin_for_cluster(cluster: TickCluster,
                        origins: Sequence[StructureOrigin]) -> Optional[dict]:
    """The M8.6 reset origin that plausibly SEEDS this local frame: an origin on
    the same sheet is frame-seeding evidence when the cluster's axis starts at
    its local zero (cluster lo within the existing link tolerance of 0+00).
    Identity is the origin's, never the shared zero (no-collapse doctrine)."""
    if cluster.lo > LINK_TOL_FT:
        return None
    for o in origins:
        if o.sheet == cluster.sheet:
            return o.to_dict()
    return None


def candidate_frames(*, bore_start_ft: float, bore_end_ft: float, span_ft: float,
                     ticks_by_sheet: Dict[int, Sequence[float]],
                     callouts: Sequence[Callout],
                     origins: Sequence[StructureOrigin],
                     hh_notes_by_sheet: Dict[int, Sequence[float]],
                     sheet_refs: Sequence[int]) -> List[FrameCandidate]:
    """Every sheet-local frame whose drawn axis contains the bore END value,
    evaluated independently (frames never mixed): does the M8.7 coverage walk
    complete INSIDE this frame's own sheet intervals?"""
    out: List[FrameCandidate] = []
    refs = set(sheet_refs)
    review_end = tolerances(span_ft)["review_end"]
    for sheet, vals in ticks_by_sheet.items():
        for cluster in tick_clusters(vals, sheet):
            if not cluster.contains(bore_end_ft):
                continue
            ivs = [c for c in callouts if c.sheet == sheet
                   and cluster.contains(c.from_ft, LINK_TOL_FT)
                   and cluster.contains(c.to_ft, LINK_TOL_FT)]
            walk = coverage_walk(ivs, bore_end_ft, span_ft)
            hh = any(abs(n - span_ft) < 1e-9
                     for n in hh_notes_by_sheet.get(sheet, ()))
            end_ev = None
            tick_hits = [v for v in cluster.ticks if abs(v - bore_end_ft) <= review_end]
            if tick_hits:
                end_ev = f"axis_tick {feet_to_station(min(tick_hits, key=lambda v: abs(v - bore_end_ft)))}"
            else:
                cal_hits = [c for c in ivs if abs(c.to_ft - bore_end_ft) <= review_end]
                if cal_hits:
                    end_ev = f"callout_end {cal_hits[0].to_sta}"
            out.append(FrameCandidate(
                sheet=sheet, cluster_lo=cluster.lo, cluster_hi=cluster.hi,
                walk_complete=bool(walk["complete"]),
                chain_texts=tuple(c.text for c in walk["chain"]),
                reached_ft=walk.get("reached_ft"),
                n_holding_intervals=int(walk.get("n_holding_intervals", 0)),
                origin=_origin_for_cluster(cluster, origins),
                hh_note_matches_span=hh,
                on_referenced_sheet=sheet in refs,
                end_evidence=end_ev))
    return out


def classify_frame_ownership(*, bore_id: str, bore_start_ft: float,
                             bore_end_ft: float, span_ft: float,
                             ticks_by_sheet: Dict[int, Sequence[float]],
                             callouts: Sequence[Callout],
                             origins: Sequence[StructureOrigin],
                             hh_notes_by_sheet: Dict[int, Sequence[float]],
                             sheet_refs: Sequence[int],
                             equations_by_sheet: Optional[Dict[int, Sequence[FrameEquation]]] = None
                             ) -> Dict[str, object]:
    """The M8.9 classification for one FRAME_OR_SHEET_CONFLICT bore. Returns a
    verdict dict; NEVER a placement, NEVER AUTO; suggestions are labeled
    suggestions; every UNSAFE names the missing relationship."""
    base: Dict[str, object] = {
        "bore_id": bore_id,
        "bore_start_sta": feet_to_station(bore_start_ft),
        "bore_end_sta": feet_to_station(bore_end_ft),
        "span_ft": span_ft, "never_auto": True,
        "sheet_refs": sorted(sheet_refs),
    }
    span_inconsistency = round(abs(span_ft - (bore_end_ft - bore_start_ft)), 2)
    if span_inconsistency > START_TOL_FT:
        base["named_missing_relationship"] = (
            f"the bore log's own numbers disagree: span {span_ft} ft vs end-start "
            f"{round(bore_end_ft - bore_start_ft, 2)} ft (delta {span_inconsistency}); "
            f"review the source cells for start {feet_to_station(bore_start_ft)} / "
            f"end {feet_to_station(bore_end_ft)} before any frame claim")
        return {**base, "result": SOURCE_REVIEW,
                "suspect_values": {"start": feet_to_station(bore_start_ft),
                                   "end": feet_to_station(bore_end_ft),
                                   "span_ft": span_ft}}

    cands = candidate_frames(
        bore_start_ft=bore_start_ft, bore_end_ft=bore_end_ft, span_ft=span_ft,
        ticks_by_sheet=ticks_by_sheet, callouts=callouts, origins=origins,
        hh_notes_by_sheet=hh_notes_by_sheet, sheet_refs=sheet_refs)
    base["competing_frames"] = [c.to_dict() for c in cands]

    # print scope first (the M8.8 guard), then walk support.
    supported = [c for c in cands if c.walk_complete and c.on_referenced_sheet]
    off_print = [c for c in cands if c.walk_complete and not c.on_referenced_sheet]
    base["supported_frames"] = len(supported)
    base["off_print_supported_frames"] = len(off_print)

    banked = BANKED_HUMAN_TIES.get(bore_id)
    if banked and len(supported) >= 1:
        # a human already graded this bore a TIE; no solver reading (including a
        # NEW route a frame walk surfaces) may override the banked grade.
        return {**base, "result": PICK_CARD,
                "label": "SUGGESTION_NOT_PLACEMENT",
                "banked_human_grade": banked,
                "suggestions": [c.to_dict() for c in supported],
                "named_missing_relationship": (
                    f"banked human grade holds: {banked}")}

    if len(supported) == 1 and supported[0].ready_grade:
        c = supported[0]
        # a NON-supported rival frame holding its own positive end evidence
        # CONTESTS the claim (the log71 lesson: the ground-truth route's frame
        # had a 1-ft callout end but incomplete coverage -- picking the frame
        # that happens to complete is closest-looking geometry).
        contested = [r for r in cands
                     if r is not c and r.end_evidence is not None]
        if contested:
            return {**base, "result": PICK_CARD,
                    "label": "SUGGESTION_NOT_PLACEMENT",
                    "suggestions": [c.to_dict()] + [r.to_dict() for r in contested],
                    "named_missing_relationship": (
                        f"the supported frame s{c.sheet} is CONTESTED: rival frame(s) "
                        f"{[(r.sheet, r.end_evidence) for r in contested]} hold their own "
                        f"end evidence without complete coverage; a human (or new "
                        f"coverage evidence) picks the route")}
        # an end sitting ON a matchline / drive-boundary equation is boundary
        # evidence, not a terminus (the M8.5 mask, consulted here too).
        if equations_by_sheet:
            probe = Callout(sheet=c.sheet, page=c.sheet, from_sta="0+00",
                            to_sta=feet_to_station(bore_end_ft), from_ft=0.0,
                            to_ft=bore_end_ft, footage=bore_end_ft, dialect="probe")
            m = matchline_mask(probe, equations_by_sheet,
                               tolerances(span_ft)["review_end"])
            if m is not None:
                return {**base, "result": PICK_CARD,
                        "label": "SUGGESTION_NOT_PLACEMENT",
                        "suggestions": [c.to_dict()],
                        "named_missing_relationship": (
                            f"the bore end {feet_to_station(bore_end_ft)} sits ON a "
                            f"matchline/drive-boundary equation ({m!r}); the cross-"
                            f"boundary continuation must be resolved by a human "
                            f"before this frame claim places")}
        evidence = ["interval_coverage_walk_complete", "unique_path_in_frame",
                    f"end_evidence: {c.end_evidence}", "print_scope"]
        if c.origin:
            evidence.append("seeded_by_structure_origin")
        if c.hh_note_matches_span:
            evidence.append("hh_distance_matches_span")
        return {**base, "result": READY, "owned_frame": c.to_dict(),
                "evidence": evidence, "review_gated_only": True}

    if len(supported) == 1 and supported[0].unique_path:
        # frame owned, route unique, but the end is containment-only (no tick /
        # callout-end evidence): suggestion-grade, not placement-grade.
        return {**base, "result": PICK_CARD,
                "label": "SUGGESTION_NOT_PLACEMENT",
                "suggestions": [supported[0].to_dict()],
                "named_missing_relationship": (
                    f"one frame supports the span but the bore end "
                    f"{feet_to_station(bore_end_ft)} has NO positive evidence in it "
                    f"(no axis tick, no callout end within the review band -- "
                    f"containment only); suggest the route, let the reviewer confirm")}

    if len(supported) == 1:
        # the frame is owned but the ROUTE inside it is not unique (>= 2
        # intervals hold the bore end -- e.g. parallel drop lanes): pick-card.
        return {**base, "result": PICK_CARD,
                "label": "SUGGESTION_NOT_PLACEMENT",
                "suggestions": [supported[0].to_dict()],
                "named_missing_relationship": (
                    f"one frame is owned but {supported[0].n_holding_intervals} "
                    f"intervals inside it hold the bore end (parallel runs); "
                    f"structure identity / a human pick selects the route")}

    if 2 <= len(supported) <= MAX_PICK_CARD_CANDIDATES:
        return {**base, "result": PICK_CARD,
                "label": "SUGGESTION_NOT_PLACEMENT",
                "suggestions": [c.to_dict() for c in supported],
                "named_missing_relationship": (
                    f"{len(supported)} frames on the bore's own sheets each fully "
                    f"support the span by authored coverage; structure identity / "
                    f"a human pick selects between them")}

    if len(supported) > MAX_PICK_CARD_CANDIDATES or (not supported and (cands or off_print)):
        return {**base, "result": ADJUSTABLE,
                "label": "SUGGESTION_NOT_PLACEMENT",
                "redline_object": {
                    "footage_ft": span_ft,
                    "station_span": f"{feet_to_station(bore_start_ft)}->"
                                    f"{feet_to_station(bore_end_ft)}",
                    "likely_sheet_range": sorted(sheet_refs),
                    "candidate_sheets": sorted({c.sheet for c in cands}),
                },
                "named_missing_relationship": (
                    f"the footage ({span_ft} ft) and station interval are certain but "
                    f"{len(supported) or len(cands)} frames remain plausible -- emit a "
                    f"human-adjustable length redline; the reviewer drags it onto the "
                    f"true path and the engine snaps/traces afterward")}

    base["named_missing_relationship"] = (
        f"no frame on the bore's referenced sheets contains the end value "
        f"{feet_to_station(bore_end_ft)} with supporting authored coverage; the next "
        f"solver needs new evidence (structure identity binding, drawn-path geometry, "
        f"or richer source data) -- never a guess")
    return {**base, "result": UNSAFE}
