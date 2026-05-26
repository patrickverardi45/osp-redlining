"""VO.2a — integration tests for the GET /api/engineering-plans/{plan_id}/page/{page_index}/image endpoint.

Targets ``get_engineering_plan_page_image`` in backend/main.py.

Pattern follows test_pe2_bounded_runner.py:
    - Set env defaults at module top before importing main.
    - Import main as ``M`` via ``from backend import main as M``.
    - Patch tenant + index helpers on M for each test case.
    - Generate a tiny PDF on disk per test where rendering must succeed.
    - Drive the async route by ``asyncio.run(...)``.

Verifies all 8 gates from the VO.2a ratification + the no-parser-invocation
invariant from the design packet §9.1.

COMMAND
-------
    python -m pytest backend/tests/test_engineering_plan_page_image_endpoint.py -v
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

os.environ.setdefault("TRUELINE_JWT_SECRET", "vo2a-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "vo2a-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend import main as M  # noqa: E402 — must come after env defaults
from backend.app.core import plan_page_image_cache  # noqa: E402


_FLAG = "TRUELINE_PLAN_OVERLAY_IMAGE"


def _make_tiny_pdf(target: Path, page_count: int = 2) -> None:
    """Create a tiny PDF on disk. Requires PyMuPDF installed."""
    import fitz  # PyMuPDF
    doc = fitz.open()
    try:
        for i in range(page_count):
            page = doc.new_page(width=612, height=792)
            page.insert_text((72, 72), f"VO.2a integration test page {i}", fontsize=12)
        doc.save(str(target))
    finally:
        doc.close()


def _make_plan_record(
    plan_id: str,
    session_id: str,
    stored_path: Path,
    file_type: str = "application/pdf",
) -> Dict[str, Any]:
    return {
        "plan_id": plan_id,
        "session_id": session_id,
        "original_filename": "test.pdf",
        "stored_filename": stored_path.name,
        "stored_path": str(stored_path),
        "file_type": file_type,
        "size_bytes": stored_path.stat().st_size if stored_path.exists() else 0,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }


class _BaseEndpointTest(unittest.TestCase):
    """Common scaffolding: tmpdir, fake plan record, mock helpers."""

    SESSION_ID = "sess_test_vo2a"
    PLAN_ID = "abc123def456"  # 12 chars; mirrors hex prefix shape

    def setUp(self) -> None:
        # Preserve env state for restoration.
        self._saved_flag = os.environ.pop(_FLAG, None)

        # Tmp workspace.
        self._tmp_root = Path(tempfile.mkdtemp())
        self._uploads_dir = self._tmp_root / "uploads"
        self._eng_root = self._uploads_dir / "engineering_plans"
        self._sess_folder = self._eng_root / self.SESSION_ID
        self._sess_folder.mkdir(parents=True, exist_ok=True)
        self._pdf_path = self._sess_folder / "tiny.pdf"
        _make_tiny_pdf(self._pdf_path, page_count=2)
        self._plan = _make_plan_record(
            plan_id=self.PLAN_ID,
            session_id=self.SESSION_ID,
            stored_path=self._pdf_path,
        )

        # Default patches: tenant gate, session resolve, index lookup.
        # VO.2b R6: endpoint now reads the RAW index (not the public projection)
        # so it has access to internal `stored_path`. The mock returns the
        # raw-shape dict {"plans": [...]} to match `_load_engineering_plan_index`.
        self._patches: List[Any] = []
        self._patches.append(patch.object(M, "_resolve_session_id", return_value=self.SESSION_ID))
        self._patches.append(patch.object(M, "_require_tenant_owns_session", return_value=None))
        self._patches.append(patch.object(M, "_load_engineering_plan_index", return_value={"plans": [self._plan]}))
        # Redirect ENGINEERING_PLAN_ROOT to our tmp dir so cache files
        # land under the test tmp tree rather than the prod uploads dir.
        self._patches.append(patch.object(M, "ENGINEERING_PLAN_ROOT", self._eng_root))
        # Sentinel: this endpoint must NEVER invoke the parser orchestrator.
        self._parser_mock = patch.object(
            M,
            "_build_plan_topology_for_session",
            side_effect=AssertionError("parser must not be invoked from the page-image endpoint"),
        )
        self._patches.append(self._parser_mock)
        self._parser_mock_with_outcomes = patch.object(
            M,
            "_build_plan_topology_for_session_with_outcomes",
            side_effect=AssertionError("parser-with-outcomes must not be invoked from the page-image endpoint"),
        )
        self._patches.append(self._parser_mock_with_outcomes)

        for p in self._patches:
            p.start()

    def tearDown(self) -> None:
        for p in self._patches:
            p.stop()
        # Restore env flag.
        if self._saved_flag is None:
            os.environ.pop(_FLAG, None)
        else:
            os.environ[_FLAG] = self._saved_flag
        # Cleanup tmp tree.
        for p in sorted(self._tmp_root.rglob("*"), reverse=True):
            try:
                if p.is_file():
                    p.unlink()
                else:
                    p.rmdir()
            except OSError:
                pass
        try:
            self._tmp_root.rmdir()
        except OSError:
            pass

    def _call(self, **kwargs: Any) -> Any:
        """Invoke the async endpoint synchronously via asyncio.run."""
        defaults: Dict[str, Any] = {
            "plan_id": self.PLAN_ID,
            "page_index": 0,
            "dpi": 96,
            "session_id": self.SESSION_ID,
            "request": None,
        }
        defaults.update(kwargs)
        return asyncio.run(M.get_engineering_plan_page_image(**defaults))


# ─── T1 — env flag off (default) returns 404 ────────────────────────────────


class T1_FlagOffReturns404(_BaseEndpointTest):
    def test_flag_unset_returns_404(self) -> None:
        os.environ.pop(_FLAG, None)
        response = self._call()
        self.assertEqual(response.status_code, 404)

    def test_flag_zero_returns_404(self) -> None:
        os.environ[_FLAG] = "0"
        response = self._call()
        self.assertEqual(response.status_code, 404)


# ─── T2 — invalid dpi bounds return 400 ─────────────────────────────────────


class T2_InvalidDpi(_BaseEndpointTest):
    def setUp(self) -> None:
        super().setUp()
        os.environ[_FLAG] = "1"

    def test_dpi_too_low_returns_400(self) -> None:
        response = self._call(dpi=47)
        self.assertEqual(response.status_code, 400)

    def test_dpi_too_high_returns_400(self) -> None:
        response = self._call(dpi=301)
        self.assertEqual(response.status_code, 400)

    def test_dpi_at_minimum_succeeds(self) -> None:
        response = self._call(dpi=48)
        self.assertEqual(response.status_code, 200)

    def test_dpi_at_maximum_succeeds(self) -> None:
        response = self._call(dpi=300)
        self.assertEqual(response.status_code, 200)


# ─── T3 — missing plan returns 404 ──────────────────────────────────────────


class T3_MissingPlan(_BaseEndpointTest):
    def setUp(self) -> None:
        super().setUp()
        os.environ[_FLAG] = "1"

    def test_plan_id_not_in_index_returns_404(self) -> None:
        response = self._call(plan_id="not_a_real_plan_id")
        self.assertEqual(response.status_code, 404)

    def test_empty_plan_id_returns_400(self) -> None:
        response = self._call(plan_id="")
        self.assertEqual(response.status_code, 400)


# ─── T4 — invalid page index returns 400 / 404 ──────────────────────────────


class T4_InvalidPageIndex(_BaseEndpointTest):
    def setUp(self) -> None:
        super().setUp()
        os.environ[_FLAG] = "1"

    def test_negative_page_index_returns_400(self) -> None:
        response = self._call(page_index=-1)
        self.assertEqual(response.status_code, 400)

    def test_page_index_out_of_range_returns_500(self) -> None:
        # The PDF has 2 pages (indexes 0 and 1).  page_index=99 triggers
        # PlanPageRenderError → 500.  This is correct: the input passed
        # endpoint-level validation (non-negative int) but the renderer
        # rejects it.  Frontend/operator should clamp page_index using
        # pdfs[].page_count from the VO.1a envelope.
        response = self._call(page_index=99)
        self.assertEqual(response.status_code, 500)


# ─── T5 — cache miss creates PNG ────────────────────────────────────────────


class T5_CacheMissCreatesPng(_BaseEndpointTest):
    def setUp(self) -> None:
        super().setUp()
        os.environ[_FLAG] = "1"

    def test_cache_miss_renders_and_writes_png(self) -> None:
        cache_file = plan_page_image_cache.resolve_cache_file(
            session_folder=self._sess_folder,
            plan_id=self.PLAN_ID,
            page_index=0,
            dpi=96,
        )
        # Pre-call: cache file must not exist.
        self.assertFalse(cache_file.exists())
        response = self._call()
        self.assertEqual(response.status_code, 200)
        # Post-call: cache file must exist and be a valid PNG.
        self.assertTrue(cache_file.is_file())
        body = cache_file.read_bytes()
        self.assertEqual(body[:8], b"\x89PNG\r\n\x1a\n")
        self.assertGreater(len(body), 100)


# ─── T6 — cache hit reuses PNG (renderer not re-invoked) ────────────────────


class T6_CacheHitReusesPng(_BaseEndpointTest):
    def setUp(self) -> None:
        super().setUp()
        os.environ[_FLAG] = "1"

    def test_cache_hit_serves_existing_file_without_rerender(self) -> None:
        cache_file = plan_page_image_cache.resolve_cache_file(
            session_folder=self._sess_folder,
            plan_id=self.PLAN_ID,
            page_index=0,
            dpi=96,
        )
        # First call: cache miss, renders.
        response1 = self._call()
        self.assertEqual(response1.status_code, 200)
        self.assertTrue(cache_file.is_file())
        first_mtime = cache_file.stat().st_mtime
        first_bytes = cache_file.read_bytes()

        # Patch the renderer to raise so we can prove it is NOT called on cache hit.
        with patch(
            "app.core.plan_page_renderer.render_plan_page_to_png_bytes",
            side_effect=AssertionError("renderer must not be called on cache hit"),
        ):
            response2 = self._call()
        self.assertEqual(response2.status_code, 200)
        # Cache file unchanged.
        self.assertEqual(cache_file.stat().st_mtime, first_mtime)
        self.assertEqual(cache_file.read_bytes(), first_bytes)


# ─── T7 — tenant / session isolation ────────────────────────────────────────


class T7_TenantIsolation(_BaseEndpointTest):
    def setUp(self) -> None:
        super().setUp()
        os.environ[_FLAG] = "1"

    def test_tenant_owns_session_called_with_resolved_sid(self) -> None:
        """The endpoint must call _require_tenant_owns_session with the
        resolved session id BEFORE doing any work — this is the tenant
        gate that prevents cross-tenant reads."""
        seen: List[Any] = []

        def fake_tenant_gate(resolved_sid: str, request: Any) -> None:
            seen.append(resolved_sid)
            return None

        with patch.object(M, "_require_tenant_owns_session", side_effect=fake_tenant_gate):
            response = self._call()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(seen, [self.SESSION_ID])

    def test_tenant_gate_can_block_request(self) -> None:
        """When _require_tenant_owns_session raises (cross-tenant), the
        endpoint propagates the exception (FastAPI turns it into 403)."""
        from fastapi import HTTPException

        with patch.object(
            M,
            "_require_tenant_owns_session",
            side_effect=HTTPException(status_code=403, detail="Forbidden"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                self._call()
            self.assertEqual(ctx.exception.status_code, 403)

    def test_index_lookup_uses_caller_session_id(self) -> None:
        """The endpoint must filter the index by the resolved session id —
        not a hardcoded value, not from STATE. A cross-session leak would
        surface here.

        VO.2b R6: after the lookup switched from the public-projection helper
        to the raw index reader, the per-record session filter is the new
        chokepoint. We spy on `_engineering_plan_record_matches_session` to
        confirm every call uses the resolved session id."""
        seen: List[Any] = []

        def fake_match(record: Dict[str, Any], session_id: str) -> bool:
            seen.append(session_id)
            return (
                str(record.get("session_id") or "").strip()
                == str(session_id or "").strip()
            )

        with patch.object(M, "_engineering_plan_record_matches_session", side_effect=fake_match):
            response = self._call()
        self.assertEqual(response.status_code, 200)
        # Matcher is called once per record in the index. All calls must use
        # the resolved session id — no cross-session probing.
        self.assertGreaterEqual(len(seen), 1)
        for sid in seen:
            self.assertEqual(sid, self.SESSION_ID)


# ─── T8 — no parser invocation ──────────────────────────────────────────────


class T8_NoParserInvocation(_BaseEndpointTest):
    """Sentinel mocks already patched in _BaseEndpointTest.setUp will raise
    AssertionError if either parser orchestrator is invoked.  This test
    simply runs the happy path and asserts the response is 200 — if any
    parser path fires, the sentinel raises and the test fails."""

    def setUp(self) -> None:
        super().setUp()
        os.environ[_FLAG] = "1"

    def test_happy_path_does_not_invoke_topology_builder(self) -> None:
        response = self._call()
        self.assertEqual(response.status_code, 200)
        # If we got here, neither _build_plan_topology_for_session nor
        # _build_plan_topology_for_session_with_outcomes was called.


# ─── T9 — non-PDF file type returns 400 ─────────────────────────────────────


class T9_NonPdfFileType(_BaseEndpointTest):
    def setUp(self) -> None:
        super().setUp()
        os.environ[_FLAG] = "1"
        # Override plan record file_type via a fresh patch.
        self._plan_png = dict(self._plan)
        self._plan_png["file_type"] = "image/png"
        # Stop the existing index-load patch and replace it.
        for p in self._patches:
            try:
                p.stop()
            except RuntimeError:
                pass
        self._patches = []
        self._patches.append(patch.object(M, "_resolve_session_id", return_value=self.SESSION_ID))
        self._patches.append(patch.object(M, "_require_tenant_owns_session", return_value=None))
        self._patches.append(patch.object(M, "_load_engineering_plan_index", return_value={"plans": [self._plan_png]}))
        self._patches.append(patch.object(M, "ENGINEERING_PLAN_ROOT", self._eng_root))
        for p in self._patches:
            p.start()

    def test_image_file_type_returns_400(self) -> None:
        response = self._call()
        self.assertEqual(response.status_code, 400)


# ─── T10 — stored file missing on disk returns 404 ──────────────────────────


class T10_StoredFileMissingOnDisk(_BaseEndpointTest):
    def setUp(self) -> None:
        super().setUp()
        os.environ[_FLAG] = "1"
        # Delete the PDF so stored_path points at a missing file.
        self._pdf_path.unlink()

    def test_missing_stored_file_returns_404(self) -> None:
        response = self._call()
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
