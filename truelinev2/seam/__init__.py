"""Coordinate-free exemplar -> pipeline SEAM contract (pure; eligible exemplars only).

Public API for the normalized seam payload the exemplar-pipeline seam scout (444beb5) proposed,
formalized as a typed, reusable internal schema. No product wiring, no renderer, no PDF, no
cross-sheet frame solving. Eligibility is frozen to the three proven exemplars.
"""
from truelinev2.seam.contract import (
    ELIGIBLE_EXEMPLARS,
    EXEMPLAR_TOPOLOGY,
    BoundaryKind,
    LegBoundary,
    RenderMode,
    RouteContext,
    SeamLeg,
    SeamPayload,
    SeamShape,
    SourceEvidence,
    build_seam_payload,
    eligible_seam_payloads,
    is_coordinate_free,
)

__all__ = [
    "ELIGIBLE_EXEMPLARS", "EXEMPLAR_TOPOLOGY", "BoundaryKind", "LegBoundary", "RenderMode",
    "RouteContext", "SeamLeg", "SeamPayload", "SeamShape", "SourceEvidence",
    "build_seam_payload", "eligible_seam_payloads", "is_coordinate_free",
]
