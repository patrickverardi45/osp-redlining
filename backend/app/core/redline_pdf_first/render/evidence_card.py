"""Minimal evidence-card payload builder (Day 1).

Turns ``EngineResult`` items into structured evidence cards that the future
TrueLine WORKSPACE_PLAN_EVIDENCE_PANEL (same-workspace review surface) can
consume. No UI, no ``fitz``, no PNG yet (``render_artifact_ref`` is None Day-1).
"""
from __future__ import annotations

from typing import Any, Dict, List

from ..contracts import (
    EngineResult,
    FailSafeItem,
    RenderArtifact,
    SelectedSegment,
    RENDER_TARGET_EVIDENCE_CARD,
)


def _span(seg: SelectedSegment) -> Dict[str, Any]:
    if seg.station_span is None:
        return {"start": None, "end": None}
    return {"start": seg.station_span.start, "end": seg.station_span.end}


def build_segment_card(seg: SelectedSegment) -> Dict[str, Any]:
    """Evidence/review card for one selected (AUTO or review) segment."""
    return {
        "log_ids": list(seg.log_ids),
        "segment_id": seg.segment_id,
        "tier": seg.tier,
        "group_id": seg.group_id,
        "requires_approval": bool(seg.requires_approval),
        "print": seg.print,
        "sheets": list(seg.sheets),
        "page": (seg.callouts[0].page if seg.callouts else None),
        "station_range": _span(seg),
        "footage": seg.footage,
        "conduit": seg.conduit,
        "end_structures": list(seg.end_structures),
        "evidence": [c.text for c in seg.callouts],
        "caveat": ({"code": seg.caveat.code, "text": seg.caveat.text} if seg.caveat else None),
        "render_target": seg.render_target,
        "render_artifact_ref": None,  # Day-1: highlighted crop PNG not generated yet
    }


def build_failsafe_card(item: FailSafeItem) -> Dict[str, Any]:
    """Evidence card for a FAIL_SAFE item — candidates only, nothing placed."""
    return {
        "log_ids": list(item.log_ids),
        "tier": item.tier,
        "reason": item.reason,
        "candidates": list(item.candidates),
        "render_target": None,
        "render_artifact_ref": None,
        "note": "FAIL_SAFE: nothing placed; candidates shown for review only.",
    }


def build_render_artifacts(result: EngineResult) -> List[RenderArtifact]:
    artifacts: List[RenderArtifact] = []
    for seg in list(result.selected_segments) + list(result.review_items):
        artifacts.append(RenderArtifact(
            artifact_id=f"card-{seg.segment_id}",
            segment_id=seg.segment_id,
            render_target=seg.render_target or RENDER_TARGET_EVIDENCE_CARD,
            kind="evidence_card",
            ref=None,
            payload=build_segment_card(seg),
        ))
    for fs in result.fail_safe_items:
        artifacts.append(RenderArtifact(
            artifact_id=f"card-failsafe-{'-'.join(fs.log_ids) or 'unknown'}",
            segment_id=None,
            render_target=RENDER_TARGET_EVIDENCE_CARD,
            kind="evidence_card_failsafe",
            ref=None,
            payload=build_failsafe_card(fs),
        ))
    return artifacts


def attach_render_artifacts(result: EngineResult) -> EngineResult:
    """Populate ``result.render_artifacts`` in place and return the result."""
    result.render_artifacts = build_render_artifacts(result)
    return result
