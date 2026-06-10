"""Match orchestration: Bore + PlanPdf + dialect -> Placement (honest abstain).

Routes by the dialect's ``match_mode`` (a string the dialect declares):
  * "footage"     — span + endpoint match over authored footage chains
  * "containment" — point-in-span (plan locates a bore; log carries the footage)
  * "extent"      — drawn-segment extent coverage of the span (AUTO only on a
                    tight unique match; else REVIEW)
All deciders are convention-agnostic; the engine names no convention.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from truelinev2.extract.base import PlanDialect
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.match.chains import build_chains, chain_uses_translated_link
from truelinev2.match.decide import decide, penalty, tolerances
from truelinev2.match.overlap import decide_by_containment, decide_by_extent, decide_by_unique_footage
from truelinev2.match.score import score_chain
from truelinev2.schema.models import Bore, Placement, PlacementStatus


def _sheet_distinct_rival(cscored, winner, winner_sc, span_ft: float) -> bool:
    """SHEET-AWARE coequal re-check for the M8.4 retry ONLY. ``decide()`` keys rival
    identity on station TEXT (chain_from/chain_to), which is correct for same-frame
    extraction duplicates but blind to translated chains on DIFFERENT sheets that
    reuse the same local station numbers (reset frames make that common). A retry
    winner with ANY acceptable, penalty-coequal candidate whose (sheets, from, to)
    identity differs is NOT unique -> the retry must abstain (never pick by order)."""
    tol = tolerances(span_ft)
    wsig = (tuple(winner_sc["sheets"]), winner_sc["chain_from"], winner_sc["chain_to"])
    wpen = penalty(winner_sc)
    for ch, sc in cscored:
        if ch is winner:
            continue
        if (sc["start_delta"] > tol["review_end"] or sc["end_delta"] > tol["review_end"]
                or sc["foot_delta"] > tol["review_foot"]):
            continue  # not acceptable -> not a rival
        sig = (tuple(sc["sheets"]), sc["chain_from"], sc["chain_to"])
        if sig != wsig and abs(penalty(sc) - wpen) <= 5.0:
            return True
    return False

if TYPE_CHECKING:  # M8.2c Step 1: type-only; no runtime import (import graph unchanged).
    from truelinev2.match.collision_gate import CollisionGate
    from truelinev2.schema.frames import FrameGraph


def _abstain(bore: Bore, tier: str, reason: str) -> Placement:
    return Placement(bore_id=bore.bore_id, status=PlacementStatus.ABSTAIN,
                     tier=tier, reason=reason, abstain_reason=reason)


def run_match(bore: Bore, plan: PlanPdf, dialect: PlanDialect, offset: int, *,
              frame_graph: Optional["FrameGraph"] = None,
              collision_gate: Optional["CollisionGate"] = None,
              continuation_graph: Optional["FrameGraph"] = None) -> Placement:
    # M8.2c Step 1: ``frame_graph`` is inert plumbing -- threaded into build_chains /
    # score_chain (footage mode) but NEVER consulted yet. None/OFF -> byte-identical M7.
    callouts = []
    for s in bore.sheet_refs:
        callouts.extend(dialect.extract_callouts(plan, s, offset))
    if not callouts:
        return _abstain(bore, "FAIL_SAFE", "NO_CALLOUTS_EXTRACTED")

    mode = getattr(dialect, "match_mode", "footage")

    if mode in ("containment", "extent"):
        if mode == "containment":
            d = decide_by_containment(callouts, bore.station_start_ft, bore.station_end_ft, bore.span_ft)
        else:
            d = decide_by_extent(callouts, bore.station_start_ft, bore.station_end_ft, bore.span_ft)
        if d["winner"] is None:
            return _abstain(bore, d["tier"], d["reason"])
        c = d["winner"][0]
        # footage/span come from the bore log (authority); the plan confirms WHERE.
        status = (PlacementStatus.AUTO_SELECT if d["status"] == "AUTO_SELECT"
                  else PlacementStatus.REVIEW)
        return Placement(bore_id=bore.bore_id, status=status, tier=d["tier"], reason=d["reason"],
                         sheets=[c.sheet], station_span=f"{bore.station_start}->{bore.station_end}",
                         footage=bore.span_ft, caveats=d["caveats"], matched_callouts=[c])

    # footage mode (span + endpoint match)
    chains = build_chains(callouts, bore.station_start_ft, bore.station_end_ft,
                          frame_graph=frame_graph)
    scored = [(ch, score_chain(ch, bore.station_start_ft, bore.station_end_ft, bore.span_ft,
                               frame_graph=frame_graph))
              for ch in chains]
    d = decide(scored, bore.span_ft)
    if d["winner"] is None:
        # Translation-invariant fallback (REVIEW only): fires ONLY when the primary found
        # NO acceptable chain — never when it abstained on AMBIGUITY (d["ambiguous"]).
        # Places iff exactly one callout's footage matches the span; the uniqueness gate in
        # decide_by_unique_footage is the zero-false guarantee. Frame unconfirmed -> REVIEW.
        if not d["ambiguous"]:
            fb = decide_by_unique_footage(callouts, bore.span_ft)
            if fb["winner"] is not None:
                fc = fb["winner"][0]
                return Placement(
                    bore_id=bore.bore_id, status=PlacementStatus.REVIEW, tier=fb["tier"],
                    reason=fb["reason"], sheets=[fc.sheet],
                    station_span=f"{bore.station_start}->{bore.station_end}",
                    footage=bore.span_ft,
                    footage_delta=round(abs(fc.footage - bore.span_ft), 2),
                    caveats=fb["caveats"], matched_callouts=[fc])
            # M8.4 frame-aware continuation retry (default-OFF; fires ONLY when the
            # bore would otherwise ABSTAIN with no acceptable chain -- never on
            # ambiguity, never before the existing fallback, never for placed logs).
            # Linking is ADDITIVE (raw OR safe-HIGH-translated), so it can only ADD
            # candidates the raw matcher could not see. decide() applies un-widened
            # tolerances; because its rival signature is station-TEXT-keyed (sheet-
            # blind), the retry adds its OWN sheet-aware coequal re-check -- a winner
            # with a sheet-distinct coequal rival abstains. Any winner whose chain
            # needed a translated link is REVIEW-capped -- NEVER AUTO -- and the
            # placement passes through the collision gate (demote-only) when active.
            if continuation_graph is not None:
                cchains = build_chains(callouts, bore.station_start_ft, bore.station_end_ft,
                                       frame_graph=continuation_graph, additive=True)
                cscored = [(ch, score_chain(ch, bore.station_start_ft, bore.station_end_ft,
                                            bore.span_ft, frame_graph=continuation_graph,
                                            additive=True))
                           for ch in cchains]
                cd = decide(cscored, bore.span_ft)
                if (cd["winner"] is not None
                        and chain_uses_translated_link(cd["winner"])
                        and not _sheet_distinct_rival(cscored, cd["winner"], cd["score"],
                                                      bore.span_ft)):
                    csc = cd["score"]
                    cwinner = cd["winner"]
                    placement = Placement(
                        bore_id=bore.bore_id, status=PlacementStatus.REVIEW,
                        tier="AUTO_PLACED_REQUIRES_APPROVAL",
                        reason="FRAME_TRANSLATED_CONTINUATION",
                        sheets=csc["sheets"],
                        station_span=f"{bore.station_start}->{bore.station_end}",
                        footage=csc["summed_ft"], footage_delta=csc["foot_delta"],
                        start_delta=csc["start_delta"], end_delta=csc["end_delta"],
                        caveats=list(cd["caveats"]) + ["FRAME_TRANSLATED_CONTINUATION"],
                        matched_callouts=list(cwinner))
                    if collision_gate is not None:
                        placement = collision_gate.apply(placement, callouts)
                    return placement
        return _abstain(bore, d["tier"], d["reason"])
    sc = d["score"]
    winner = d["winner"]
    status = (PlacementStatus.AUTO_SELECT if d["status"] == "AUTO_SELECT"
              else PlacementStatus.REVIEW)
    placement = Placement(
        bore_id=bore.bore_id, status=status, tier=d["tier"], reason=d["reason"],
        sheets=sc["sheets"], station_span=f"{winner[0].from_sta}->{winner[-1].to_sta}",
        footage=sc["summed_ft"], footage_delta=sc["foot_delta"],
        start_delta=sc["start_delta"], end_delta=sc["end_delta"],
        caveats=d["caveats"], matched_callouts=list(winner))
    # M8.2l: optional, default-OFF reset-collision gate. None (the default) is the
    # OFF state -> the placement above is returned byte-identical. When injected,
    # the gate is DEMOTE-ONLY (R6): it can never promote or place anything, and it
    # touches only chains with a runtime-detected on-crossing reset collision.
    if collision_gate is not None:
        placement = collision_gate.apply(placement, callouts)
    return placement
