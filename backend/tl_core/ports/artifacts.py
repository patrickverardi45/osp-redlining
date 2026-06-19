"""Port: tenant-scoped artifact storage + traversal-safe retrieval."""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Protocol

from ..context import RequestContext
from ..domain.redline import ArtifactRef


class ArtifactStore(Protocol):
    def put(self, ctx: RequestContext, src_path: str, kind: str = "evidence_card",
            sheet: Optional[int] = None, segment_id: Optional[str] = None) -> ArtifactRef:
        """Ingest a rendered file into the (tenant, session) scope; return a ref
        whose ``.name`` is the basename serving key."""
        ...

    def resolve(self, ctx: RequestContext, name: str) -> Path:
        """Resolve a basename to a real path INSIDE the caller's scope, or raise.
        Must be traversal-safe (basename-only + containment check)."""
        ...

    def read_bytes(self, ctx: RequestContext, name: str) -> bytes:
        ...
