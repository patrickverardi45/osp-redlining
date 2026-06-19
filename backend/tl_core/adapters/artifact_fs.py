"""Filesystem artifact store, scoped per (tenant, session), traversal-safe.

Replicates the proven positive-control pattern from
``app/core/pdf_first_artifacts.py::resolve_artifact_path`` (Stream-6 3a):
basename-only + re-root under the scope dir + realpath/commonpath containment +
require ``.png`` + ``isfile``. It never trusts a client-supplied path component,
and reads are confined to the caller's own (tenant, session) directory.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from ..context import IsolationError, RequestContext
from ..domain.redline import ArtifactRef


class FilesystemArtifactStore:
    def __init__(self, root: Path):
        self._root = Path(root)

    def _scope_dir(self, ctx: RequestContext) -> Path:
        # tenant.value + session_id are validated non-empty + slug-safe by the
        # RequestContext constructor, so the join cannot escape the root here.
        d = self._root / ctx.tenant.value / ctx.session_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def put(self, ctx: RequestContext, src_path: str, kind: str = "evidence_card",
            sheet=None, segment_id=None) -> ArtifactRef:
        src = Path(src_path)
        if not src.is_file():
            raise FileNotFoundError(f"artifact source not found: {src_path}")
        name = os.path.basename(str(src))
        if not name.lower().endswith(".png"):
            raise ValueError(f"artifact must be a .png: {name!r}")
        dest = self._scope_dir(ctx) / name
        if Path(src).resolve() != dest.resolve():
            shutil.copyfile(src, dest)
        return ArtifactRef(name=name, kind=kind, sheet=sheet, segment_id=segment_id,
                           size_bytes=dest.stat().st_size)

    def resolve(self, ctx: RequestContext, name: str) -> Path:
        # 1) basename-only: reject anything carrying a directory component.
        base = os.path.basename(str(name))
        if base != str(name) or base in ("", ".", ".."):
            raise IsolationError(f"invalid artifact name (no paths allowed): {name!r}")
        if not base.lower().endswith(".png"):
            raise IsolationError(f"artifact must be a .png: {base!r}")
        # 2) re-root under the caller's scope + containment check (realpath).
        scope = self._scope_dir(ctx).resolve()
        candidate = (scope / base).resolve()
        if os.path.commonpath([str(scope), str(candidate)]) != str(scope):
            raise IsolationError(f"artifact path escapes scope: {name!r}")
        if not candidate.is_file():
            raise FileNotFoundError(f"artifact not found: {base!r}")
        return candidate

    def read_bytes(self, ctx: RequestContext, name: str) -> bytes:
        return self.resolve(ctx, name).read_bytes()
