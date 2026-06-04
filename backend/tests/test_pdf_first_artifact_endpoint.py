"""Route-level integration tests for GET /api/pdf-first-evidence/{session_id}/artifact.

Targets ``get_pdf_first_evidence_artifact`` in backend/main.py. Mirrors the VO.2a
endpoint-test pattern (test_engineering_plan_page_image_endpoint.py): set env defaults
before importing main, import via ``from backend import main as M``, patch the tenant
ownership helper per case, drive the (sync) route directly.

Proves end-to-end:
  * flag OFF (TRUELINE_PDF_FIRST_ENGINE unset/'0') => 404 with NO filesystem access
  * owned session + real file        => 200 image/png FileResponse for the right file
  * missing file / path traversal     => 404
  * non-owner (ownership helper raises)=> 403 propagates (route does not swallow it)

COMMAND (from repo root):
    python -m pytest backend/tests/test_pdf_first_artifact_endpoint.py -v
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

os.environ.setdefault("TRUELINE_JWT_SECRET", "pf-artifact-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "pf-artifact-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend import main as M  # noqa: E402 — must come after env defaults
from fastapi import HTTPException  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402

_FLAG = "TRUELINE_PDF_FIRST_ENGINE"
SID = "sess-itest-1"
PNG = "log39_pathtrace_s25.png"


def _seed(uploads: Path, session_id: str, filename: str = PNG) -> Path:
    d = uploads / "pdf_first_cards" / session_id
    d.mkdir(parents=True, exist_ok=True)
    p = d / filename
    p.write_bytes(b"\x89PNG\r\n\x1a\n")
    return p


def _call(name, session_id=SID):
    return M.get_pdf_first_evidence_artifact(session_id=session_id, name=name, request=None)


def test_flag_off_returns_404_no_fs(tmp_path, monkeypatch):
    monkeypatch.delenv(_FLAG, raising=False)  # flag OFF (unset)
    with patch.object(M, "UPLOADS_DIR", tmp_path):
        assert _call(PNG).status_code == 404
    # Even with a real file present and flag='0', still 404 — flag-off touches no fs.
    _seed(tmp_path, SID)
    monkeypatch.setenv(_FLAG, "0")
    with patch.object(M, "UPLOADS_DIR", tmp_path):
        assert _call(PNG).status_code == 404


def test_owned_session_serves_png(tmp_path, monkeypatch):
    monkeypatch.setenv(_FLAG, "1")
    real = _seed(tmp_path, SID)
    with patch.object(M, "UPLOADS_DIR", tmp_path):
        resp = _call(PNG)
    assert isinstance(resp, FileResponse)
    assert resp.status_code == 200
    assert resp.media_type == "image/png"
    assert os.path.realpath(resp.path) == os.path.realpath(str(real))


def test_missing_file_404(tmp_path, monkeypatch):
    monkeypatch.setenv(_FLAG, "1")
    _seed(tmp_path, SID)
    with patch.object(M, "UPLOADS_DIR", tmp_path):
        assert _call("not_here.png").status_code == 404


def test_traversal_404(tmp_path, monkeypatch):
    monkeypatch.setenv(_FLAG, "1")
    _seed(tmp_path, SID)
    (tmp_path / "outside.png").write_bytes(b"\x89PNG")  # sensitive file outside cards tree
    with patch.object(M, "UPLOADS_DIR", tmp_path):
        for attack in ("../../outside.png", r"..\..\outside.png", "/etc/passwd.png"):
            assert _call(attack).status_code == 404, attack


def test_non_png_404(tmp_path, monkeypatch):
    monkeypatch.setenv(_FLAG, "1")
    d = tmp_path / "pdf_first_cards" / SID
    d.mkdir(parents=True, exist_ok=True)
    (d / "secret.txt").write_bytes(b"nope")
    with patch.object(M, "UPLOADS_DIR", tmp_path):
        assert _call("secret.txt").status_code == 404


def test_non_owner_403_propagates(tmp_path, monkeypatch):
    monkeypatch.setenv(_FLAG, "1")
    _seed(tmp_path, SID)

    def _deny(session_id, request=None):
        raise HTTPException(status_code=403, detail="session does not belong to this tenant")

    with patch.object(M, "UPLOADS_DIR", tmp_path), \
         patch.object(M, "_require_tenant_owns_session", _deny):
        with pytest.raises(HTTPException) as ei:
            _call(PNG)
    assert ei.value.status_code == 403
