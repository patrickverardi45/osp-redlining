"""Engine-agnostic domain types the services + API speak.

The engine adapter translates the reused ``EngineResult`` contract into these so
nothing downstream depends on the engine's internal shapes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class ArtifactRef:
    """A rendered evidence artifact (PNG) owned by a (tenant, session).

    ``name`` is the basename serving key (the only path component a client ever
    sees). ``source_path`` is the raw render path on the server used to ingest
    the file into the scoped store; it is NEVER serialized to clients.
    """

    name: str
    kind: str = "evidence_card"
    sheet: Optional[int] = None
    segment_id: Optional[str] = None
    size_bytes: Optional[int] = None
    source_path: Optional[str] = None


@dataclass(frozen=True)
class Placement:
    """One selected / review / fail-safe segment translated from the engine."""

    segment_id: str
    log_ids: List[str]
    tier: str
    surface: str  # placement | review | fail_safe
    sheets: List[int] = field(default_factory=list)
    station_start: Optional[str] = None
    station_end: Optional[str] = None
    footage: Optional[float] = None
    geometry_status: Optional[str] = None
    artifacts: List[ArtifactRef] = field(default_factory=list)


@dataclass(frozen=True)
class RedlineResult:
    """The engine-agnostic result. ``status`` mirrors the engine envelope:
    OK | FAIL_SAFE_GLOBAL | ERROR (the engine never raises into the caller)."""

    job_id: str
    status: str
    source_file: Optional[str]
    placements: List[Placement] = field(default_factory=list)
    review_items: List[Placement] = field(default_factory=list)
    fail_safe: List[Placement] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def all_artifacts(self) -> List[ArtifactRef]:
        out: List[ArtifactRef] = []
        for p in list(self.placements) + list(self.review_items):
            out.extend(p.artifacts)
        return out
