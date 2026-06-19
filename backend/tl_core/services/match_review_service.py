"""MatchReviewService — assemble a UI-compatible Match-Review-Queue payload that
references artifact URLs.

Shapes mirror the monolith contracts the frontend already consumes (Stream-4):
``match-review-queue-1`` rows + an additive ``pdf-first-evidence-1`` block whose
placements carry an ``artifact`` URL. Identity (tenant/session) is NEVER put in
the artifact URL — only the basename — so the URL cannot be used for IDOR; the
caller's auth context selects the scope server-side.

JSON values are carried RAW (not HTML-escaped): per the Stream-6 rule, output
encoding belongs at the HTML sink (see :mod:`tl_core.security.sanitize`), not in
the JSON layer, where escaping would double-encode for a React consumer.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..context import RequestContext
from ..domain.redline import ArtifactRef, Placement
from .redline_service import RedlineRunOutcome


def _artifact_obj(ref: ArtifactRef) -> Dict[str, Any]:
    return {
        "name": ref.name,
        "kind": ref.kind,
        "sheet": ref.sheet,
        "size_bytes": ref.size_bytes,
        # Relative URL; the leaf basename is the ONLY client-supplied path part.
        "url": f"/v2/artifact/{ref.name}",
    }


class MatchReviewService:
    def build_payload(self, ctx: RequestContext, outcome: RedlineRunOutcome) -> Dict[str, Any]:
        result = outcome.result
        stored_by_seg: Dict[Optional[str], List[ArtifactRef]] = {}
        for ref in outcome.stored_artifacts:
            stored_by_seg.setdefault(ref.segment_id, []).append(ref)

        rows: List[Dict[str, Any]] = []
        placements_payload: List[Dict[str, Any]] = []
        for p in list(result.placements) + list(result.review_items):
            arts = [_artifact_obj(r) for r in stored_by_seg.get(p.segment_id, [])]
            span = (f"{p.station_start}->{p.station_end}"
                    if p.station_start is not None else None)
            rows.append({
                "source_file": result.source_file,
                "segment_id": p.segment_id,
                "status": result.status,
                "tier": p.tier,
                "surface": p.surface,
                "sheets": p.sheets,
                "station_span": span,
                "footage": p.footage,
                "artifacts": arts,
            })
            placements_payload.append({
                "segment_id": p.segment_id,
                "tier": p.tier,
                "sheets": p.sheets,
                "station_span": {"start": p.station_start, "end": p.station_end},
                "footage": p.footage,
                "geometry_status": p.geometry_status,
                "artifact": arts[0] if arts else None,
            })

        return {
            "schema_version": "match-review-queue-1",
            "session_id": ctx.session_id,
            "row_count": len(rows),
            "rows": rows,
            "pdf_first_evidence": {
                "schema_version": "pdf-first-evidence-1",
                "status": result.status,
                "render_target": "evidence_card",
                "source": {"bore_log": result.source_file},
                "counts_by_surface": {
                    "placements": len(result.placements),
                    "review_items": len(result.review_items),
                    "fail_safe": len(result.fail_safe),
                },
                "placements": placements_payload,
                "warnings": result.warnings,
            },
        }
