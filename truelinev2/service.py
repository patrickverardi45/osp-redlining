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
from truelinev2.match.engine import run_match
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
                placement = run_match(bore, plan, dialect, offset)
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
