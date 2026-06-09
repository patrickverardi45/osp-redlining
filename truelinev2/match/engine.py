"""Match orchestration: Bore + PlanPdf + dialect -> Placement (honest abstain).

Routes by the dialect's ``match_mode`` (a string the dialect declares):
  * "footage"     — span + endpoint match over authored footage chains
  * "containment" — point-in-span (plan locates a bore; log carries the footage)
  * "extent"      — drawn-segment extent coverage of the span (AUTO only on a
                    tight unique match; else REVIEW)
All deciders are convention-agnostic; the engine names no convention.
"""
from __future__ import annotations

from truelinev2.extract.base import PlanDialect
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.match.chains import build_chains
from truelinev2.match.decide import decide
from truelinev2.match.overlap import decide_by_containment, decide_by_extent
from truelinev2.match.score import score_chain
from truelinev2.schema.models import Bore, Placement, PlacementStatus


def _abstain(bore: Bore, tier: str, reason: str) -> Placement:
    return Placement(bore_id=bore.bore_id, status=PlacementStatus.ABSTAIN,
                     tier=tier, reason=reason, abstain_reason=reason)


def run_match(bore: Bore, plan: PlanPdf, dialect: PlanDialect, offset: int) -> Placement:
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
    chains = build_chains(callouts, bore.station_start_ft, bore.station_end_ft)
    scored = [(ch, score_chain(ch, bore.station_start_ft, bore.station_end_ft, bore.span_ft))
              for ch in chains]
    d = decide(scored, bore.span_ft)
    if d["winner"] is None:
        return _abstain(bore, d["tier"], d["reason"])
    sc = d["score"]
    winner = d["winner"]
    status = (PlacementStatus.AUTO_SELECT if d["status"] == "AUTO_SELECT"
              else PlacementStatus.REVIEW)
    return Placement(
        bore_id=bore.bore_id, status=status, tier=d["tier"], reason=d["reason"],
        sheets=sc["sheets"], station_span=f"{winner[0].from_sta}->{winner[-1].to_sta}",
        footage=sc["summed_ft"], footage_delta=sc["foot_delta"],
        start_delta=sc["start_delta"], end_delta=sc["end_delta"],
        caveats=d["caveats"], matched_callouts=list(winner))
