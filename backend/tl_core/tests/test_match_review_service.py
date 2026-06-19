"""Match-Review payload contract: UI-compatible shape + artifact URL carries the
basename ONLY (no tenant/session in the URL -> IDOR-resistant)."""
from __future__ import annotations

from tl_core.context import require_context
from tl_core.domain.redline import ArtifactRef, Placement, RedlineResult
from tl_core.services.match_review_service import MatchReviewService
from tl_core.services.redline_service import RedlineRunOutcome


def _outcome():
    ref = ArtifactRef(name="log51_s8.png", kind="evidence_card", sheet=8,
                      segment_id="log51", size_bytes=1234)
    p = Placement(segment_id="log51", log_ids=["log51"], tier="AUTO_SELECT",
                  surface="placement", sheets=[8], station_start="0+00",
                  station_end="2+99", footage=299.0, artifacts=[ref])
    result = RedlineResult(job_id="j", status="OK", source_file="bore_log51.xlsx",
                           placements=[p])
    return RedlineRunOutcome(result=result, stored_artifacts=[ref])


def test_payload_shape():
    payload = MatchReviewService().build_payload(require_context("acme", "s1"), _outcome())
    assert payload["schema_version"] == "match-review-queue-1"
    assert payload["row_count"] == 1
    assert payload["pdf_first_evidence"]["schema_version"] == "pdf-first-evidence-1"
    assert payload["pdf_first_evidence"]["counts_by_surface"]["placements"] == 1


def test_artifact_url_has_no_identity():
    payload = MatchReviewService().build_payload(require_context("acme", "s1"), _outcome())
    art = payload["pdf_first_evidence"]["placements"][0]["artifact"]
    assert art["url"] == "/v2/artifact/log51_s8.png"
    assert "acme" not in art["url"]
    assert "s1" not in art["url"]
