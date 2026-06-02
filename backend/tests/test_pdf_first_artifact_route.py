"""Focused security tests for PDF-first evidence artifact path resolution.

Tests the PURE containment helper ``app.core.pdf_first_artifacts.resolve_artifact_path``
WITHOUT importing ``main.py`` (the monolith; ``tests/test_dual_auth_smoke.py`` avoids it
too). This helper is the security-critical core of the
``GET /api/pdf-first-evidence/{session_id}/artifact`` route: basename-only, re-rooted
under the owned session's cards dir, traversal-proof.

Tenant-ownership (403 for a non-owner) is enforced separately in the route via the
reused ``_require_tenant_owns_session`` — already covered by
``tests/test_dual_auth_smoke.py``'s cross-tenant 403 checks. This file proves the PATH
layer can never escape the session dir, serve another session's file, or serve a
non-existent / non-PNG file.

Run:  cd backend && python -m pytest tests/test_pdf_first_artifact_route.py -v
"""
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from app.core.pdf_first_artifacts import resolve_artifact_path, CARDS_SUBDIR

SID = "sess-owned-123"
PNG = "log39_pathtrace_s25.png"


def _seed(uploads_dir: str, session_id: str, filename: str = PNG) -> str:
    """Create <uploads>/pdf_first_cards/<session_id>/<filename>; return its path."""
    d = os.path.join(uploads_dir, CARDS_SUBDIR, session_id)
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, filename)
    with open(p, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n")  # minimal PNG signature
    return p


def test_owned_session_file_serves(tmp_path):
    up = str(tmp_path)
    real = _seed(up, SID)
    got = resolve_artifact_path(up, SID, PNG)
    assert got is not None
    assert os.path.realpath(got) == os.path.realpath(real)
    assert os.path.isfile(got)


def test_missing_file_returns_none(tmp_path):
    up = str(tmp_path)
    _seed(up, SID)  # dir exists, ask for a different file
    assert resolve_artifact_path(up, SID, "does_not_exist.png") is None


def test_non_png_rejected(tmp_path):
    up = str(tmp_path)
    d = os.path.join(up, CARDS_SUBDIR, SID)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "secret.txt"), "wb") as fh:
        fh.write(b"nope")
    assert resolve_artifact_path(up, SID, "secret.txt") is None


def test_empty_or_dir_name_rejected(tmp_path):
    up = str(tmp_path)
    _seed(up, SID)
    assert resolve_artifact_path(up, SID, "") is None
    assert resolve_artifact_path(up, SID, None) is None


def test_traversal_blocked(tmp_path):
    up = str(tmp_path)
    _seed(up, SID)
    # Plant a sensitive PNG OUTSIDE the cards tree.
    with open(os.path.join(up, "outside.png"), "wb") as fh:
        fh.write(b"\x89PNG")
    for attack in ("../../outside.png", "../outside.png", r"..\..\outside.png",
                   "/etc/passwd.png", "....//outside.png"):
        assert resolve_artifact_path(up, SID, attack) is None, attack


def test_absolute_path_name_reduced_to_basename(tmp_path):
    up = str(tmp_path)
    _seed(up, SID, PNG)
    # A system path's basename won't exist inside the session dir -> None.
    assert resolve_artifact_path(up, SID, "/etc/passwd.png") is None
    # A legit basename embedded in a longer path still resolves to the in-dir file.
    assert resolve_artifact_path(up, SID, "some/nested/path/" + PNG) is not None


def test_cross_session_isolation(tmp_path):
    up = str(tmp_path)
    _seed(up, "session-A", "secretA.png")
    # Asking as session-B for session-A's file must fail (different session dir).
    assert resolve_artifact_path(up, "session-B", "secretA.png") is None
    # session-A can fetch its own.
    assert resolve_artifact_path(up, "session-A", "secretA.png") is not None
