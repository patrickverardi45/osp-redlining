"""RedlineService — orchestrate: bore log -> reused engine -> rendered PNG ->
tenant-scoped artifact store.

Thin by design: it injects a :class:`RedlineEnginePort` and an
:class:`ArtifactStore` and wires them together. No engine internals, no global
state, no FastAPI types.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from ..context import RequestContext
from ..domain.redline import ArtifactRef, RedlineResult
from ..ports.artifacts import ArtifactStore
from ..ports.engine import RedlineEnginePort


@dataclass(frozen=True)
class RedlineRunOutcome:
    """What a run produced: the engine-agnostic result + the artifacts that were
    ingested into the caller's scoped store (the serving keys)."""

    result: RedlineResult
    stored_artifacts: List[ArtifactRef] = field(default_factory=list)


class RedlineService:
    def __init__(self, engine: RedlineEnginePort, artifacts: ArtifactStore):
        self._engine = engine
        self._artifacts = artifacts

    def run_for_bore(self, ctx: RequestContext, bore_log_path: str,
                     plan_pdf_path: str) -> RedlineRunOutcome:
        """Run the engine for one bore log, then ingest every rendered PNG into
        the (tenant, session) scoped store. Returns the result + stored refs."""
        result = self._engine.run(bore_log_path, plan_pdf_path)
        stored: List[ArtifactRef] = []
        for art in result.all_artifacts:
            if not art.source_path:
                continue
            stored.append(self._artifacts.put(
                ctx, art.source_path, kind=art.kind,
                sheet=art.sheet, segment_id=art.segment_id))
        return RedlineRunOutcome(result=result, stored_artifacts=stored)
