"""RedlineService — the v2 application service.

Orchestrates: ingest bore log -> open plan -> select dialect -> calibrate offset
-> match (honest abstain) -> render evidence crop -> tenant-scoped artifact store
-> persist + return a Match-Review payload. No old-app code.
"""
from __future__ import annotations

from truelinev2.config import Settings
from truelinev2.context import RequestContext
from truelinev2.extract.registry import select_dialect
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.match.collision_gate import CollisionGate, collect_equations, load_human_grades
from truelinev2.match.engine import run_match
from truelinev2.match.frames import build_frame_edges, build_frame_graph, frame_for_sheet, parse_frame_equations
from truelinev2.match.reverse_anchor import ReverseAnchorContext
from truelinev2.match.transition_classifier import conflict_sheet_pairs


def _build_plan_frame_graph(plan: PlanPdf, offset: int):
    """The SAFE frame graph from the plan's own text (HIGH/unique/conflict-free edges
    only -- ``match.frames`` drops everything ambiguous). Built ONLY when the M8.4
    continuation flag is ON; the default path never constructs or consults it."""
    edges = []
    for idx in range(plan.page_count):
        text = " ".join(ln for ln in plan.text_by_index(idx).splitlines() if ln.strip())
        edges.extend(build_frame_edges(parse_frame_equations(text),
                                       frame_for_sheet(idx - offset + 1)))
    return build_frame_graph(edges)
from truelinev2.render.crop import render_evidence_crop
from truelinev2.review.payload import build_review_payload
from truelinev2.schema.models import Placement, PlacementStatus, ReviewPayload
from truelinev2.store.artifacts import ArtifactStore
from truelinev2.store.db import ReviewStore


class RedlineService:
    def __init__(self, settings: Settings, artifacts: ArtifactStore, db: ReviewStore):
        self._settings = settings
        self._artifacts = artifacts
        self._db = db

    def run(self, ctx: RequestContext, bore_log_path: str, plan_pdf_path: str) -> ReviewPayload:
        bore = load_borelog(bore_log_path)
        plan = PlanPdf(plan_pdf_path)
        try:
            dialect = select_dialect(plan)
            if dialect is None:
                placement = Placement(
                    bore_id=bore.bore_id, status=PlacementStatus.ABSTAIN, tier="FAIL_SAFE",
                    reason="NO_DIALECT_MATCH",
                    abstain_reason="no registered plan dialect recognized this plan")
            else:
                offset = dialect.calibrate(plan, self._settings.sheet_offset)
                # M8.2l: DEFAULT OFF. The gate is built + injected ONLY when the
                # opt-in flag is explicitly True; OFF -> run_match is called exactly
                # as before (collision_gate=None) and behavior is byte-identical.
                gate = None
                if self._settings.reset_collision_optin:
                    gate = CollisionGate(
                        equations_by_sheet=collect_equations(plan, offset, bore.sheet_refs),
                        human_grades=load_human_grades())
                # M8.4: DEFAULT OFF. The safe frame graph is built + injected ONLY
                # when the continuation flag is explicitly True; OFF -> None ->
                # byte-identical default behavior.
                cont_graph = None
                if self._settings.frame_continuation_optin:
                    cont_graph = _build_plan_frame_graph(plan, offset)
                # M8.5: DEFAULT OFF. The reverse-anchor context is built + injected
                # ONLY when the opt-in flag is explicitly True; OFF -> None ->
                # byte-identical default behavior. The safe frame graph is shared
                # with M8.4 when both flags are on (same builder, built once).
                rev_ctx = None
                if self._settings.reverse_endpoint_optin:
                    rev_graph = (cont_graph if cont_graph is not None
                                 else _build_plan_frame_graph(plan, offset))
                    # equations for ALL sheets, not just sheet_refs: the matchline
                    # mask must see equations authored on the FAR side of a pair
                    # (linked-frame masking) -- the M8.5 adversarial mask lesson.
                    all_sheets = range(1, plan.page_count - offset + 1)
                    rev_ctx = ReverseAnchorContext(
                        graph=rev_graph,
                        conflicts=conflict_sheet_pairs(rev_graph),
                        equations_by_sheet=collect_equations(plan, offset, all_sheets))
                placement = run_match(bore, plan, dialect, offset, collision_gate=gate,
                                      continuation_graph=cont_graph,
                                      reverse_anchor=rev_ctx)
                for c in placement.matched_callouts:
                    crop_path = render_evidence_crop(
                        plan, bore.bore_id, c, str(self._settings.cards_dir), offset,
                        zoom=self._settings.render_zoom)
                    if crop_path:
                        art = self._artifacts.put(ctx, crop_path, sheet=c.sheet, bbox=c.bbox)
                        placement.artifacts.append(art)
        finally:
            plan.close()

        payload = build_review_payload(ctx, [(bore, placement)])
        self._db.save_review(ctx, payload.model_dump_json())
        return payload
