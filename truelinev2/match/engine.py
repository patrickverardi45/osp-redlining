"""Match orchestration: Bore + PlanPdf + dialect -> Placement (honest abstain)."""
from __future__ import annotations

from truelinev2.extract.base import PlanDialect
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.match.chains import build_chains
from truelinev2.match.decide import decide
from truelinev2.match.score import score_chain
from truelinev2.schema.models import Bore, Placement, PlacementStatus


def run_match(bore: Bore, plan: PlanPdf, dialect: PlanDialect, offset: int) -> Placement:
    callouts = []
    for s in bore.sheet_refs:
        callouts.extend(dialect.extract_callouts(plan, s, offset))

    if not callouts:
        return Placement(bore_id=bore.bore_id, status=PlacementStatus.ABSTAIN,
                         tier="FAIL_SAFE", reason="NO_CALLOUTS_EXTRACTED",
                         abstain_reason="dialect extracted no callouts on candidate sheets")

    chains = build_chains(callouts, bore.station_start_ft, bore.station_end_ft)
    scored = [(ch, score_chain(ch, bore.station_start_ft, bore.station_end_ft, bore.span_ft))
              for ch in chains]
    d = decide(scored, bore.span_ft)

    if d["winner"] is None:
        return Placement(bore_id=bore.bore_id, status=PlacementStatus.ABSTAIN,
                         tier=d["tier"], reason=d["reason"], abstain_reason=d["reason"])

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
