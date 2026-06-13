r"""M9.4.2 -- RUN-ASSEMBLY review service surface (parallel to the per-bore bundle).

Composes the shipped M9.4.1 product-layer pipeline:

  TA.attribute_bore (M9.3.1)  ->  extract_run_assembly (M9.4.1)  ->  build_run_assembly_cards (M9.4.1)

Deliberately separate from ``ReviewerBundleService.generate`` -- exactly as the M8.20
``GroupReviewService`` is separate from the per-bore bundle. The per-bore M8.10/M8.11
bundle, statuses, census, lanes, and contracts remain UNCHANGED: this service adds
NOTHING to the bundle; it surfaces the run-assembly review cards through a parallel
service under their own schema (``truelinev2-run-assembly-review-1``).

REVIEW/evidence-only: the cards carry no geometry, no strokes, no AUTO, no product
bucket (the M9.4.1 card validator fails closed on any of these). No proof imports, no
env reads, no persistence, no rendering, no engine writes, NO placement-path call
(``resolve_bore`` / sweep / ``run_match`` are never invoked here). No cross-sheet /
M9.2 frame-graph expansion: the competing-departure guarantee carried in each card
stays the M9.4.1 frame-scoped one.

CONVENTION-AGNOSTIC: this module holds zero plan-set literals (drift-guard-enforced).
The KMZ model, the terminus profile, and the banked source-contradiction set are all
INJECTED by the caller (the proof / a test) -- mirroring how ``GroupReviewService``
takes its ``lane_dialect``.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Sequence

from truelinev2.extract.registry import select_dialect
from truelinev2.extract.terminus_profile import TerminusProfile
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.match import terminus_attribution as TA
from truelinev2.match.run_assembly import extract_run_assembly
from truelinev2.review.run_assembly_review import (
    RunAssemblyReviewCard,
    build_run_assembly_cards,
)
from truelinev2.stations import feet_to_station


class RunAssemblyReviewService:
    """Generate validated RUN-ASSEMBLY review cards without changing per-bore output."""

    def __init__(self, *, corpus_dir: str, plan_pdf_path: str,
                 bore_log_paths: Sequence[Path], kmz_model,
                 terminus_profile: TerminusProfile,
                 source_contradiction_bores: Sequence[str] = (),
                 sheet_offset: int = 13):
        self._corpus_dir = corpus_dir
        self._plan_pdf_path = plan_pdf_path
        self._bore_log_paths = [Path(p) for p in bore_log_paths]
        self._kmz_model = kmz_model
        self._profile = terminus_profile
        self._source_contradiction = frozenset(source_contradiction_bores)
        self._sheet_offset = sheet_offset

    def generate(self) -> List[RunAssemblyReviewCard]:
        """Return the run-assembly review cards -- ONE per SHARED-TERMINAL evidence
        item (a typed blocker yields no card), in deterministic (end_bore, start_bore)
        order. Unparseable bore sources are ignored (they cannot attribute a terminus
        and stay represented by the separate per-bore reviewer bundle). PURE read: the
        per-bore bundle is never touched; nothing is rendered or written."""
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
            results: List[TA.BoreTerminusResult] = []
            lines_by_id = {}
            for bore in bores:
                lbs = {s: plan.lines(s, offset) for s in sorted(set(bore.sheet_refs))}
                lines_by_id[bore.bore_id] = lbs
                results.append(TA.attribute_bore(
                    bore.bore_id,
                    feet_to_station(bore.station_start_ft),
                    feet_to_station(bore.station_end_ft),
                    lbs, self._profile, kmz_model=self._kmz_model,
                    source_contradiction=bore.bore_id in self._source_contradiction))
            evidence = extract_run_assembly(results, lines_by_id, self._profile)
            cards = build_run_assembly_cards(evidence)
            return sorted(cards, key=lambda c: (c.end_bore, c.start_bore))
        finally:
            plan.close()
