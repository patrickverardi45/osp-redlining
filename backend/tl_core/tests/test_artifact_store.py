"""Traversal-safe, tenant-scoped artifact store — replicates the positive-control
pattern (Stream-6 3a) and proves cross-tenant reads fail."""
from __future__ import annotations

import pytest

from tl_core.adapters.artifact_fs import FilesystemArtifactStore
from tl_core.context import IsolationError, require_context

_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 100


def _png(tmp_path, name="card.png"):
    p = tmp_path / name
    p.write_bytes(_PNG)
    return str(p)


def test_put_then_resolve_and_read(tmp_path):
    store = FilesystemArtifactStore(root=tmp_path / "store")
    ctx = require_context("acme", "s1")
    ref = store.put(ctx, _png(tmp_path))
    assert ref.name == "card.png"
    assert ref.size_bytes == len(_PNG)
    assert store.resolve(ctx, "card.png").is_file()
    assert store.read_bytes(ctx, "card.png") == _PNG


@pytest.mark.parametrize("bad", ["../secret.png", "..\\secret.png", "sub/dir.png", "/etc/x.png"])
def test_traversal_names_rejected(tmp_path, bad):
    store = FilesystemArtifactStore(root=tmp_path / "store")
    ctx = require_context("acme", "s1")
    with pytest.raises(IsolationError):
        store.resolve(ctx, bad)


def test_non_png_rejected(tmp_path):
    store = FilesystemArtifactStore(root=tmp_path / "store")
    ctx = require_context("acme", "s1")
    with pytest.raises(IsolationError):
        store.resolve(ctx, "evil.exe")


def test_cross_tenant_cannot_read(tmp_path):
    store = FilesystemArtifactStore(root=tmp_path / "store")
    store.put(require_context("acme", "s1"), _png(tmp_path))
    with pytest.raises(FileNotFoundError):
        store.read_bytes(require_context("globex", "s1"), "card.png")
