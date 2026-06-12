r"""M8.20 GROUP REVIEW service output (parallel to the per-bore bundle).

This service composes the shipped product-layer pipeline:

``extract_group_claims`` -> ``shared_alignment_verdict`` ->
``build_group_review_card``

It is deliberately separate from ``ReviewerBundleService.generate``. The
per-bore bundle, statuses, census, and contracts remain unchanged. Group cards
are REVIEW-only, geometry-free outputs under their own schema.

No proof imports, environment reads, persistence, rendering, or engine writes.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

from truelinev2.extract.registry import select_dialect
from truelinev2.extract.structure_position import LaneDialect
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.match.shared_alignment import (
    BoreClaim,
    shared_alignment_verdict,
)
from truelinev2.match.shared_alignment_extract import (
    extract_group_claims,
    origin_chain_boundaries,
)
from truelinev2.match.symbol_conduit_lane import resolve_bore
from truelinev2.review.group_review import (
    SharedAlignmentGroupCard,
    build_group_review_card,
)
from truelinev2.service import _build_plan_frame_graph
from truelinev2.stations import feet_to_station


def _claim_context(bore, outcome) -> Tuple[int, int, str] | None:
    """The common printed-chain context needed for the Law-1 bijection gate.

    A claim must identify one far sheet, one other (end) sheet, and its printed
    start station. Ambiguous sheet context abstains softly by returning None.
    """
    far = outcome.detail.get("far_sheet")
    if far is None:
        return None
    others = [s for s in sorted(set(bore.sheet_refs)) if s != far]
    if len(others) != 1:
        return None
    return far, others[0], feet_to_station(bore.station_start_ft)


class GroupReviewService:
    """Generate validated GROUP REVIEW cards without changing per-bore output."""

    def __init__(self, *, corpus_dir: str, plan_pdf_path: str,
                 bore_log_paths: Sequence[Path], lane_dialect: LaneDialect,
                 sheet_offset: int = 13):
        self._corpus_dir = corpus_dir
        self._plan_pdf_path = plan_pdf_path
        self._bore_log_paths = [Path(p) for p in bore_log_paths]
        self._lane_dialect = lane_dialect
        self._sheet_offset = sheet_offset

    def generate(self) -> List[SharedAlignmentGroupCard]:
        """Return proven group cards in deterministic shared-origin order.

        Unparseable bore sources are ignored here, matching the shipped claim
        extractor proof: they cannot form a group claim and remain represented
        by the separate per-bore reviewer bundle. Non-proven or context-
        ambiguous groups emit no card.
        """
        bores = []
        for path in self._bore_log_paths:
            try:
                bores.append(load_borelog(str(path)))
            except Exception:
                continue

        plan = PlanPdf(self._plan_pdf_path)
        try:
            plan_dialect = select_dialect(plan)
            if plan_dialect is None:
                raise ValueError("no registered plan dialect recognized this plan")
            offset = plan_dialect.calibrate(plan, self._sheet_offset)
            graph = _build_plan_frame_graph(plan, offset)
            claims = extract_group_claims(
                plan, offset, graph, self._lane_dialect, bores)
            bore_by_id = {b.bore_id: b for b in bores}

            grouped: Dict[str, List[BoreClaim]] = defaultdict(list)
            for claim in claims:
                grouped[claim.survivor_id].append(claim)

            cards: List[SharedAlignmentGroupCard] = []
            for shared_origin in sorted(grouped):
                sharing = grouped[shared_origin]
                if len(sharing) < 2:
                    continue

                statuses = {}
                contexts = set()
                valid = True
                for claim in sharing:
                    bore = bore_by_id.get(claim.bore_id)
                    if bore is None:
                        valid = False
                        break
                    outcome = resolve_bore(
                        plan, bore, offset, self._lane_dialect, frame_graph=graph)
                    statuses[claim.bore_id] = outcome.status
                    context = _claim_context(bore, outcome)
                    if context is None:
                        valid = False
                        break
                    contexts.add(context)
                if not valid or len(contexts) != 1:
                    continue

                far, end, start_raw = next(iter(contexts))
                universe = origin_chain_boundaries(
                    plan, offset, graph, self._lane_dialect,
                    far, end, start_raw)
                verdict = shared_alignment_verdict(
                    sharing, origin_chain_boundaries=universe)
                card = build_group_review_card(verdict, sharing, statuses)
                if card is not None:
                    cards.append(card)
            return cards
        finally:
            plan.close()
