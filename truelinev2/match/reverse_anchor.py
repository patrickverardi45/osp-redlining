r"""M8.5 -- reverse endpoint anchor solver (pure core; default-OFF opt-in wiring).

Doctrine: every bore is called out somewhere on the plan. When the FORWARD start
anchor never binds (the M8.4-proven blocker: no callout ``from_ft`` within
``start_tol`` of the bore start), try the bore's ENDING station and work backward
using the bore's total footage:

  1. find callout(s) whose authored run ENDS at the bore's end station,
  2. walk BACKWARD through authored callouts, gating every hop with the banked
     M8.2f transition classifier (same-sheet raw / continuous-station raw /
     reset-equation translation; ambiguous|conflict|missing-evidence REFUSE),
  3. compute the expected start = anchor end - bore footage (in the anchor frame),
  4. require the walked authored coverage to contiguously CONTAIN that start,
  5. compare the computed start against the bore-log start,
  6. claim only when EXACTLY ONE reverse path survives end-to-end.

Safety inherited, never widened:
  * every tolerance is an EXISTING engine constant (chains.build_chains start_tol /
    link_tol; decide.tolerances review_end / review_foot) -- nothing new, nothing wider;
  * an end-station match that sits ON a matchline frame equation is a CONTINUATION
    MARKER, not a terminus -- masked from anchoring (the monolith's Target #32 lesson);
  * >= 2 surviving reverse paths -> pick-card abstain, NEVER delta-tiebreak (M8.3a law);
  * the solver emits VERDICTS; the engine wiring REVIEW-caps the single READY class
    and composes it with the reset-collision gate -- nothing here can produce AUTO.

Every non-READY verdict carries ``named_missing_relationship`` -- the exact evidence
relationship that was searched, what was found, and what the next solver must consume.
This module was proven proof-first (proof/run_reverse_endpoint_anchor_proof.py) and
re-homed into match/ for the default-OFF wiring, the M8.2k -> M8.2l precedent.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Sequence, Set, Tuple

from truelinev2.match.chains import raw_link_ok
from truelinev2.match.decide import tolerances
from truelinev2.match.frames import translate_between_sheets
from truelinev2.match.transition_classifier import (
    TransitionClass,
    classify_callout_transition,
)
from truelinev2.schema.frames import EquationKind, FrameEquation, FrameGraph
from truelinev2.schema.models import Callout
from truelinev2.stations import feet_to_station

# EXISTING engine constants, re-cited (single source: match/chains.py defaults).
# Asserted equal to the build_chains defaults by the M8.5 test suite -- if the engine
# ever moves them, the solver moves with it (no solver-local tolerance may drift).
START_TOL_FT = 8.0   # chains.build_chains start_tol -- reused for start agreement
LINK_TOL_FT = 2.0    # chains.build_chains link_tol  -- reused for backward links
MAX_DEPTH = 6        # chains.build_chains max_depth -- reused for walk depth

# The six allowed verdicts (fixed taxonomy -- the proof never invents a seventh).
READY = "REVERSE_ANCHOR_READY_FOR_OPTIN_REVIEW"
PICK_CARD = "MULTIPLE_REVERSE_PATHS_PICK_CARD"
END_NOT_FOUND = "END_STATION_NOT_FOUND"
FOOTAGE_MISMATCH = "FOOTAGE_MISMATCH"
FRAME_CONFLICT = "FRAME_PATH_CONFLICT"
OCR_REQUIRED = "OCR_REQUIRED_OR_FAILED"
VERDICTS = (READY, PICK_CARD, END_NOT_FOUND, FOOTAGE_MISMATCH, FRAME_CONFLICT, OCR_REQUIRED)


@dataclass(frozen=True)
class ReverseAnchorContext:
    """Everything the engine's default-OFF reverse retry needs, prebuilt by the
    caller (RedlineService when ``Settings.reverse_endpoint_optin`` is True)."""
    graph: Optional[FrameGraph]
    conflicts: Set[Tuple[int, int]]
    equations_by_sheet: Mapping[int, Sequence[FrameEquation]]


@dataclass(frozen=True)
class ReverseHop:
    """One backward adjacency pred -> head, with its M8.2f classification and the
    frame correction (anchor-frame feet added to the predecessor's raw stations)."""
    from_sheet: int
    to_sheet: int
    classification: str
    raw_gap_ft: Optional[float]
    translated_gap_ft: Optional[float]
    correction_ft: float

    def to_dict(self) -> dict:
        return {"from_sheet": self.from_sheet, "to_sheet": self.to_sheet,
                "classification": self.classification, "raw_gap_ft": self.raw_gap_ft,
                "translated_gap_ft": self.translated_gap_ft,
                "correction_ft": self.correction_ft}


@dataclass(frozen=True)
class ReversePath:
    """A complete backward walk: ``callouts`` in start->end order (last == anchor),
    every hop proven, coverage containing the expected start in the anchor frame."""
    callouts: Tuple[Callout, ...]
    hops: Tuple[ReverseHop, ...]
    anchor_end_ft: float          # anchor.to_ft (anchor frame)
    coverage_lo_ft: float         # first callout's from_ft in the ANCHOR frame
    expected_start_ft: float      # anchor_end_ft - span (anchor frame)
    containing_callout_text: str  # the chain element containing the expected start

    @property
    def signature(self) -> Tuple:
        # footage + vacancy INCLUDED: two boxes authored at the same stations with
        # different footage/vacancy are physically distinct evidence -- they must
        # surface as a pick-card, never silently collapse (M8.5 adversarial P3).
        return tuple((c.sheet, c.from_sta, c.to_sta, c.footage, c.vacant)
                     for c in self.callouts)

    @property
    def sheets(self) -> List[int]:
        return sorted({c.sheet for c in self.callouts})

    @property
    def summed_footage(self) -> float:
        return round(sum(c.footage for c in self.callouts), 2)

    def to_dict(self) -> dict:
        return {
            "chain": [c.text for c in self.callouts],
            "sheets": self.sheets,
            "hops": [h.to_dict() for h in self.hops],
            "anchor_end_ft": self.anchor_end_ft,
            "coverage_lo_ft": self.coverage_lo_ft,
            "expected_start_ft": self.expected_start_ft,
            "expected_start_sta": feet_to_station(self.expected_start_ft),
            "containing_callout": self.containing_callout_text,
            "summed_footage": self.summed_footage,
        }


@dataclass
class _WalkState:
    """One in-progress backward chain (head-first extension)."""
    callouts: List[Callout]          # start->end order; callouts[0] is the current head
    hops: List[ReverseHop]
    head_correction_ft: float        # head-frame -> anchor-frame additive correction


def end_anchor_candidates(callouts: Sequence[Callout], bore_end_ft: float,
                          review_end: float) -> List[Tuple[Callout, float]]:
    """Callouts whose authored run ENDS at the bore end within the EXISTING review
    tolerance. Sorted by |delta| then text for determinism; tolerance never widened."""
    out = [(c, round(abs(c.to_ft - bore_end_ft), 2)) for c in callouts
           if abs(c.to_ft - bore_end_ft) <= review_end]
    return sorted(out, key=lambda t: (t[1], t[0].sheet, t[0].text))


def matchline_mask(c: Callout,
                   equations_by_sheet: Mapping[int, Sequence[FrameEquation]],
                   tol: float) -> Optional[str]:
    """A run that ENDS at a matchline / frame-equation station is a CONTINUATION
    or DRIVE-BOUNDARY marker, not a structure terminus (the monolith's Target #32
    over-generation lesson + the M8.5-adversarial log36 lesson, re-derived for v2).
    Returns the masking equation's source text, or None. Masks on:
      * CROSS_FRAME / matchline equations: EITHER station side (the collision
        gate's banked ``_pair_equations`` both-sides precedent), whether authored
        on the callout's own sheet OR on a sheet whose equation LINKS this sheet
        (matchlines are routinely authored on the far side of the pair);
      * FRAME_RESET equations on the callout's own sheet: the NONZERO side -- a
        drive-boundary reset like ``STA 1+45=0+00`` marks an installer-HH drive
        boundary, and a run ending there is boundary evidence, not a terminus.
    Over-masking is abstain-direction (safe); under-masking anchors continuations."""
    for sheet, eqs in equations_by_sheet.items():
        for eq in eqs:
            own_sheet = sheet == c.sheet
            links_here = c.sheet in eq.linked_frames
            if not (own_sheet or links_here):
                continue
            if eq.kind is EquationKind.CROSS_FRAME or eq.has_matchline:
                if (abs(eq.a.feet - c.to_ft) <= tol
                        or abs(eq.b.feet - c.to_ft) <= tol):
                    return eq.source or f"{eq.a.raw} {eq.separator} {eq.b.raw}"
            elif eq.kind is EquationKind.FRAME_RESET and own_sheet:
                boundary = eq.a.feet if eq.b.feet == 0.0 else eq.b.feet
                if boundary != 0.0 and abs(boundary - c.to_ft) <= tol:
                    return eq.source or f"{eq.a.raw} {eq.separator} {eq.b.raw}"
    return None


def walk_backward(callouts: Sequence[Callout], anchor: Callout, span_ft: float,
                  graph: Optional[FrameGraph], conflicts: Set[Tuple[int, int]],
                  *, link_tol: float = LINK_TOL_FT, max_depth: int = MAX_DEPTH,
                  max_expansions: int = 20000
                  ) -> Tuple[List[ReversePath], List[dict], List[dict], bool]:
    """All complete backward paths from ``anchor`` whose authored, hop-proven
    coverage contiguously contains ``expected_start = anchor.to_ft - span_ft``.

    Returns (complete_paths, stalls, refusals, budget_exhausted):
      * stalls   -- incomplete walks (how far coverage reached, the remaining gap)
        -> FOOTAGE_MISMATCH evidence;
      * refusals -- in-gap-tolerance predecessors REFUSED by the transition
        classifier (ambiguous/conflict/missing-evidence cross-sheet hops)
        -> FRAME_PATH_CONFLICT evidence;
      * budget_exhausted -- the expansion budget tripped (duplicate-dense callout
        sets are exponential): the search is INCOMPLETE, so uniqueness can never
        be claimed from it (the caller must refuse READY).
    A path stops extending the moment it is complete: predecessors EARLIER than the
    bore start cannot change the bore's span (containment, not span-equality)."""
    expected_start = round(anchor.to_ft - span_ft, 2)
    complete: List[ReversePath] = []
    seen_signatures: Set[Tuple] = set()
    stalls: List[dict] = []
    refusals: List[dict] = []
    budget = {"left": max_expansions, "exhausted": False}

    def containing_text(chain: List[Callout], corrs: List[float]) -> str:
        for c, corr in zip(chain, corrs):
            if c.from_ft + corr - link_tol <= expected_start <= c.to_ft + corr + link_tol:
                return c.text
        return "(expected start falls in a link gap <= link_tol)"

    def extend(state: _WalkState, corrs: List[float]) -> None:
        if budget["left"] <= 0:
            budget["exhausted"] = True
            return
        budget["left"] -= 1
        head = state.callouts[0]
        coverage_lo = round(head.from_ft + state.head_correction_ft, 2)
        if coverage_lo <= expected_start + link_tol:
            path = ReversePath(
                callouts=tuple(state.callouts), hops=tuple(state.hops),
                anchor_end_ft=anchor.to_ft, coverage_lo_ft=coverage_lo,
                expected_start_ft=expected_start,
                containing_callout_text=containing_text(state.callouts, corrs))
            if path.signature not in seen_signatures:
                seen_signatures.add(path.signature)
                complete.append(path)
            return  # complete: do not extend past the bore start
        if len(state.callouts) >= max_depth:
            stalls.append({"reached_ft": coverage_lo, "gap_ft": round(coverage_lo - expected_start, 2),
                           "chain": [c.text for c in state.callouts], "stop": "max_depth"})
            return
        extended = False
        for pred in callouts:
            if any(pred is c for c in state.callouts):
                continue
            t = classify_callout_transition(graph, conflicts, pred, head, link_tol=link_tol)
            corr: Optional[float] = None
            hop: Optional[ReverseHop] = None
            if t.classification in (TransitionClass.SAME_SHEET, TransitionClass.CONTINUOUS_STATION):
                if raw_link_ok(pred, head, link_tol):
                    corr = state.head_correction_ft
                    hop = ReverseHop(pred.sheet, head.sheet, t.classification.value,
                                     t.raw_gap_ft, t.translated_gap_ft,
                                     round(corr, 2))
            elif t.classification is TransitionClass.RESET_EQUATION:
                tr_to = translate_between_sheets(graph, pred.sheet, head.sheet, pred.to_ft)
                tr_from = translate_between_sheets(graph, pred.sheet, head.sheet, pred.from_ft)
                if (tr_to is not None and tr_from is not None
                        and abs(tr_to - head.from_ft) <= link_tol and tr_to < head.to_ft
                        and tr_from < tr_to):
                    corr = round(state.head_correction_ft + (tr_to - pred.to_ft), 2)
                    hop = ReverseHop(pred.sheet, head.sheet, t.classification.value,
                                     t.raw_gap_ft, t.translated_gap_ft, corr)
            else:
                # REFUSED class: record only when the gap itself was in tolerance
                # (i.e. the ONLY thing blocking the hop is frame proof).
                near = (t.raw_gap_ft is not None and t.raw_gap_ft <= link_tol) or (
                    t.translated_gap_ft is not None and t.translated_gap_ft <= link_tol)
                if near:
                    refusals.append({"pred": pred.text, "head": head.text,
                                     "sheet_pair": sorted({pred.sheet, head.sheet}),
                                     "classification": t.classification.value,
                                     "reason": t.reason})
            if corr is not None and hop is not None:
                extend(_WalkState([pred] + state.callouts, [hop] + state.hops, corr),
                       [corr] + corrs)
                extended = True
        if not extended:
            stalls.append({"reached_ft": coverage_lo,
                           "gap_ft": round(coverage_lo - expected_start, 2),
                           "chain": [c.text for c in state.callouts],
                           "stop": "no_proven_predecessor"})

    extend(_WalkState([anchor], [], 0.0), [0.0])
    return complete, stalls, refusals, budget["exhausted"]


def _unconsumed_anchor_edges(graph: Optional[FrameGraph], path: ReversePath,
                             universe_sheets: Set[int]) -> List[Tuple[int, int]]:
    """Frame-coherence check (M8.5 adversarial critical finding): a safe RESET edge
    between the anchor's sheet and another sheet of the bore's own callout universe
    declares that raw station numbers are NOT shared across that pair -- so a path
    that never CROSSES the edge cannot prove which frame the bore's stations live
    in (raw end equality on one side may be a frame doppelganger ~offset ft away).
    Returns the in-universe anchor-sheet edge pairs the path leaves unconsumed."""
    if graph is None:
        return []
    anchor_sheet = path.callouts[-1].sheet
    required: Set[Tuple[int, int]] = set()
    for s in universe_sheets:
        if s != anchor_sheet and translate_between_sheets(graph, anchor_sheet, s, 0.0) is not None:
            required.add((min(anchor_sheet, s), max(anchor_sheet, s)))
    consumed = {(min(h.from_sheet, h.to_sheet), max(h.from_sheet, h.to_sheet))
                for h in path.hops
                if h.classification == TransitionClass.RESET_EQUATION.value}
    return sorted(required - consumed)


def solve_reverse_anchor(*, bore_id: str, bore_start_ft: float, bore_end_ft: float,
                         span_ft: float, callouts: Sequence[Callout],
                         graph: Optional[FrameGraph], conflicts: Set[Tuple[int, int]],
                         equations_by_sheet: Mapping[int, Sequence[FrameEquation]],
                         end_text_found_in_plan: Optional[bool] = None,
                         max_expansions: int = 20000
                         ) -> Tuple[Dict[str, object], Optional[ReversePath]]:
    """The full M8.5 proof for one bore over an ENGINE-SCOPED callout universe
    (the bore's own sheet_refs -- the same universe run_match sees). Returns
    ``(verdict_dict, winning_path_or_None)``; the path is non-None ONLY for READY.
    NEVER a placement, NEVER AUTO. ``end_text_found_in_plan`` is the runner's
    whole-document text-layer scan for the literal end-station string (None = not
    scanned): it distinguishes END_STATION_NOT_FOUND (callout absent, text present
    or unscanned) from OCR_REQUIRED_OR_FAILED (the text layer cannot see the
    station at all and no OCR stack exists in this venv)."""
    tol = tolerances(span_ft)
    span_consistency_ft = round(abs(span_ft - (bore_end_ft - bore_start_ft)), 2)
    base: Dict[str, object] = {
        "bore_id": bore_id,
        "bore_start_ft": bore_start_ft, "bore_start_sta": feet_to_station(bore_start_ft),
        "bore_end_ft": bore_end_ft, "bore_end_sta": feet_to_station(bore_end_ft),
        "span_ft": span_ft, "span_consistency_ft": span_consistency_ft,
        "tolerances": tol, "never_auto": True,
    }

    cands = end_anchor_candidates(callouts, bore_end_ft, tol["review_end"])
    if not cands:
        deltas = [round(abs(c.to_ft - bore_end_ft), 2) for c in callouts]
        nearest = min(deltas) if deltas else None
        containing = [c.text for c in callouts if c.from_ft < bore_end_ft < c.to_ft]
        if end_text_found_in_plan is False:
            named = (f"end station {feet_to_station(bore_end_ft)} appears NOWHERE in the "
                     f"plan's text layer and no OCR stack is installed in this venv; the "
                     f"station frame itself is absent from the plan text -- the next solver "
                     f"needs a bore-frame->plan-frame binding datum (or richer source data), "
                     f"not rasterization")
            verdict = OCR_REQUIRED
        else:
            named = (f"no authored callout ENDS within review_end {tol['review_end']} ft of "
                     f"bore end {feet_to_station(bore_end_ft)} on the bore's referenced "
                     f"sheets (nearest authored end is {nearest} ft away)"
                     + (f"; the bore end lies MID-CALLOUT inside {containing[0]!r} -- the "
                        f"next solver must consume interval containment with endpoint-"
                        f"rounding evidence, not run-end equality" if containing else
                        "; no callout contains the end station either"))
            verdict = END_NOT_FOUND
        return ({**base, "result": verdict, "end_anchor_candidates": [],
                 "min_end_delta_ft": nearest, "end_contained_in": containing,
                 "named_missing_relationship": named}, None)

    masked = []
    eligible: List[Tuple[Callout, float]] = []
    for c, d in cands:
        m = matchline_mask(c, equations_by_sheet, tol["review_end"])
        if m is not None:
            masked.append({"callout": c.text, "end_delta_ft": d, "masking_equation": m})
        else:
            eligible.append((c, d))
    cand_report = [{"callout": c.text, "sheet": c.sheet, "end_delta_ft": d,
                    "vacant": c.vacant, "footage_verified": c.footage_verified}
                   for c, d in eligible]
    base["end_anchor_candidates"] = cand_report
    base["matchline_masked_candidates"] = masked

    if not eligible:
        named = (f"the only end-station match(es) sit ON a matchline / drive-boundary "
                 f"frame equation ({masked[0]['masking_equation']!r}) -- a continuation "
                 f"marker or drive-boundary marker, not a run terminus; the next solver "
                 f"must resolve that boundary relationship (cross-matchline continuation, "
                 f"or which side of the drive boundary the bore terminates on) before any "
                 f"end-anchored claim")
        return ({**base, "result": END_NOT_FOUND, "named_missing_relationship": named}, None)

    paths: List[ReversePath] = []
    stalls: List[dict] = []
    refusals: List[dict] = []
    exhausted = False
    end_delta_by_sig: Dict[Tuple, float] = {}
    for c, d in eligible:
        p, s, r, ex = walk_backward(callouts, c, span_ft, graph, conflicts,
                                    max_expansions=max_expansions)
        for path in p:
            end_delta_by_sig.setdefault(path.signature, d)
        paths.extend(p)
        stalls.extend(s)
        refusals.extend(r)
        exhausted = exhausted or ex
    # cross-candidate dedup by signature
    uniq: Dict[Tuple, ReversePath] = {}
    for p in paths:
        uniq.setdefault(p.signature, p)
    paths = list(uniq.values())
    # frame-coherence filter: drop paths whose anchor sheet is reset-linked to
    # another universe sheet WITHOUT the path crossing that edge (doppelganger gate).
    universe_sheets = {c.sheet for c in callouts}
    frame_incoherent: List[dict] = []
    kept: List[ReversePath] = []
    for p in paths:
        unconsumed = _unconsumed_anchor_edges(graph, p, universe_sheets)
        if unconsumed:
            frame_incoherent.append({"chain": [c.text for c in p.callouts],
                                     "unconsumed_edge_pairs": unconsumed})
        else:
            kept.append(p)
    paths = kept
    base["complete_paths"] = [p.to_dict() for p in paths]
    base["frame_incoherent_paths"] = frame_incoherent
    base["stalled_walks"] = stalls
    base["refused_hops"] = refusals
    base["search_budget_exhausted"] = exhausted

    if exhausted:
        named = (f"the backward search exhausted its expansion budget "
                 f"({max_expansions}) before completing -- uniqueness cannot be "
                 f"proven from an incomplete search; the next solver must reduce "
                 f"duplicate/station-identical callouts or raise the budget, then "
                 f"re-prove")
        return ({**base, "result": PICK_CARD, "named_missing_relationship": named}, None)

    if not paths and frame_incoherent:
        pairs = sorted({tuple(p) for fi in frame_incoherent
                        for p in fi["unconsumed_edge_pairs"]})
        named = (f"every complete reverse path anchors on a sheet that a safe reset "
                 f"equation links to another sheet of the bore's own universe "
                 f"({pairs}) without the path crossing that edge -- raw end-station "
                 f"equality cannot identify the bore's frame across a declared reset "
                 f"(frame-doppelganger hazard); the next solver needs the bore's "
                 f"frame bound to one side (a crossing hop, a structure identity, or "
                 f"a human grade)")
        return ({**base, "result": FRAME_CONFLICT, "named_missing_relationship": named}, None)

    if not paths:
        if refusals:
            pairs = sorted({tuple(r["sheet_pair"]) for r in refusals})
            named = (f"the backward walk needs a cross-sheet hop on sheet pair(s) "
                     f"{pairs} but every in-gap-tolerance predecessor is REFUSED by the "
                     f"transition classifier ({sorted({r['classification'] for r in refusals})}); "
                     f"the next solver needs a proven frame relationship for those pairs "
                     f"(a HIGH/unique/conflict-free matchline equation or a human grade)")
            return ({**base, "result": FRAME_CONFLICT, "named_missing_relationship": named}, None)
        best = min(stalls, key=lambda s: s["gap_ft"]) if stalls else None
        named = (f"end anchored, but authored contiguous coverage walks back only to "
                 f"{feet_to_station(best['reached_ft'])} -- {best['gap_ft']} ft of bore "
                 f"footage has NO authored callout behind it; the next solver must find "
                 f"the missing authored run segment (or prove the bore footage overlaps "
                 f"an unauthored extent)" if best else
                 "end anchored but no backward walk possible")
        return ({**base, "result": FOOTAGE_MISMATCH, "named_missing_relationship": named}, None)

    if len(paths) >= 2:
        named = (f"{len(paths)} distinct reverse paths each satisfy end anchor + footage "
                 f"containment; per the M8.3a law physically distinct routes are never "
                 f"delta-tiebroken -- the next solver is a HUMAN pick-card (or a new "
                 f"deterministic discriminator such as structure-identity binding)")
        return ({**base, "result": PICK_CARD, "named_missing_relationship": named}, None)

    p = paths[0]
    # near-rival end guard (M8.5 adversarial log5 lesson): a second AUTHORED run
    # end within review_end of the WINNING anchor's end means two physically
    # parallel runs terminate a few feet apart -- a bore end that itself needs
    # review-band slop cannot distinguish them. Demote to pick-card, never choose.
    anchor_callout = p.callouts[-1]
    near_rivals = [c for c in callouts
                   if all(c is not pc for pc in p.callouts)
                   and abs(c.to_ft - anchor_callout.to_ft) <= tol["review_end"]
                   and matchline_mask(c, equations_by_sheet, tol["review_end"]) is None]
    if near_rivals:
        named = (f"the winning anchor end {anchor_callout.to_sta} has authored rival "
                 f"run end(s) within review_end {tol['review_end']} ft "
                 f"({[c.to_sta for c in near_rivals]}); parallel runs terminating "
                 f"feet apart cannot be distinguished by the bore end alone -- the "
                 f"next solver is a HUMAN pick-card (or structure-identity binding)")
        return ({**base, "result": PICK_CARD,
                 "near_rival_ends": [c.text for c in near_rivals],
                 "named_missing_relationship": named}, None)
    start_delta = round(abs(p.expected_start_ft - bore_start_ft), 2)
    start_confirmed = start_delta <= START_TOL_FT
    base["computed_start_ft"] = p.expected_start_ft
    base["computed_start_sta"] = feet_to_station(p.expected_start_ft)
    base["start_delta_vs_borelog_ft"] = start_delta
    base["start_confirmed"] = start_confirmed
    # honesty: for a span-consistent bore (span == end - start) the start check is
    # arithmetically IMPLIED by the end check -- it adds independent evidence only
    # when the bore log's own numbers disagree internally.
    base["start_check_independent"] = span_consistency_ft > 0
    if not start_confirmed:
        named = (f"unique reverse path proven from the end anchor, but the computed start "
                 f"{feet_to_station(p.expected_start_ft)} disagrees with the bore-log start "
                 f"{feet_to_station(bore_start_ft)} by {start_delta} ft (implied local-frame "
                 f"offset); the next solver needs a bore-frame->plan-frame binding datum "
                 f"before this may place")
        return ({**base, "result": FRAME_CONFLICT, "named_missing_relationship": named}, None)

    caveats = ["REVERSE_ENDPOINT_ANCHOR", "NEVER_AUTO_BY_CONSTRUCTION"]
    if any(h.classification == TransitionClass.CONTINUOUS_STATION.value and
           h.from_sheet != h.to_sheet for h in p.hops):
        caveats.append("RAW_CROSS_SHEET_CONTINUATION")
    if any(h.classification == TransitionClass.RESET_EQUATION.value for h in p.hops):
        caveats.append("FRAME_TRANSLATED_HOP")
    winning_end_delta = end_delta_by_sig.get(p.signature, 0.0)
    if winning_end_delta > tol["auto_end"]:
        caveats.append("END_DELTA_REVIEW_BAND")
    if any(c.vacant for c in p.callouts):
        caveats.append("VACANT_IN_CHAIN")
    if masked:
        caveats.append("MATCHLINE_MASKED_RIVAL_ANCHOR")
    if any(all(c is not pc for pc in p.callouts)
           and c.from_ft < bore_end_ft < c.to_ft for c in callouts):
        caveats.append("BORE_END_INSIDE_ADJACENT_CALLOUT")
    return ({**base, "result": READY, "winning_path": p.to_dict(), "caveats": caveats,
             "winning_end_delta_ft": winning_end_delta, "review_gated_only": True}, p)


def prove_reverse_anchor(**kwargs) -> Dict[str, object]:
    """Proof-harness convenience: the verdict dict only (JSON-serializable)."""
    proof, _path = solve_reverse_anchor(**kwargs)
    return proof
