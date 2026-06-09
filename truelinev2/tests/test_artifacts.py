import pytest

from truelinev2.context import IsolationError, require_context
from truelinev2.store.artifacts import ArtifactStore

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 60


def _png(tmp, name="c.png"):
    p = tmp / name
    p.write_bytes(PNG)
    return str(p)


def test_put_resolve_read(tmp_path):
    s = ArtifactStore(tmp_path / "store")
    ctx = require_context("acme", "s1")
    ref = s.put(ctx, _png(tmp_path))
    assert ref.name == "c.png" and ref.size_bytes == len(PNG)
    assert s.read_bytes(ctx, "c.png") == PNG


@pytest.mark.parametrize("bad", ["../x.png", "..\\x.png", "sub/y.png", "/etc/z.png"])
def test_traversal_rejected(tmp_path, bad):
    s = ArtifactStore(tmp_path / "store")
    with pytest.raises(IsolationError):
        s.resolve(require_context("acme", "s1"), bad)


def test_cross_tenant_cannot_read(tmp_path):
    s = ArtifactStore(tmp_path / "store")
    s.put(require_context("acme", "s1"), _png(tmp_path))
    with pytest.raises(FileNotFoundError):
        s.read_bytes(require_context("globex", "s1"), "c.png")
