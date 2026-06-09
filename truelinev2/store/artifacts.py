"""Tenant-scoped, traversal-safe artifact store (basename-only + containment)."""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import List, Optional

from truelinev2.context import IsolationError, RequestContext
from truelinev2.schema.models import Artifact


class ArtifactStore:
    def __init__(self, root: Path):
        self._root = Path(root)

    def _scope(self, ctx: RequestContext) -> Path:
        d = self._root / ctx.tenant.value / ctx.session_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def put(self, ctx: RequestContext, src_path: str, kind: str = "evidence_crop",
            sheet: Optional[int] = None, bbox: Optional[List[float]] = None) -> Artifact:
        src = Path(src_path)
        if not src.is_file():
            raise FileNotFoundError(f"artifact source not found: {src_path}")
        name = os.path.basename(str(src))
        if not name.lower().endswith(".png"):
            raise ValueError(f"artifact must be .png: {name!r}")
        dest = self._scope(ctx) / name
        if src.resolve() != dest.resolve():
            shutil.copyfile(src, dest)
        return Artifact(name=name, kind=kind, sheet=sheet, bbox=bbox,
                        size_bytes=dest.stat().st_size)

    def resolve(self, ctx: RequestContext, name: str) -> Path:
        base = os.path.basename(str(name))
        if base != str(name) or base in ("", ".", ".."):
            raise IsolationError(f"invalid artifact name: {name!r}")
        if not base.lower().endswith(".png"):
            raise IsolationError(f"artifact must be .png: {base!r}")
        scope = self._scope(ctx).resolve()
        cand = (scope / base).resolve()
        if os.path.commonpath([str(scope), str(cand)]) != str(scope):
            raise IsolationError(f"artifact path escapes scope: {name!r}")
        if not cand.is_file():
            raise FileNotFoundError(f"artifact not found: {base!r}")
        return cand

    def read_bytes(self, ctx: RequestContext, name: str) -> bytes:
        return self.resolve(ctx, name).read_bytes()
