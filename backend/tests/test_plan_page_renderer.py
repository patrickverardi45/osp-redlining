"""VO.2a — unit tests for plan_page_renderer + plan_page_image_cache helpers.

Targets:
    backend/app/core/plan_page_renderer.py
    backend/app/core/plan_page_image_cache.py

Both are pure utilities; tests generate a tiny PDF on the fly via PyMuPDF
and exercise the helper contracts directly.  No env vars, no main.py
import, no STATE mutation.

COMMAND
-------
    python -m pytest backend/tests/test_plan_page_renderer.py -v
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

# These imports do not require any env setup — both helper modules are
# pure and have no top-level side effects beyond the lazy PyMuPDF import
# inside render_plan_page_to_png_bytes.
from backend.app.core import plan_page_image_cache
from backend.app.core.plan_page_renderer import (
    PlanPageRenderError,
    render_plan_page_to_png_bytes,
)


def _make_tiny_pdf(target: Path, page_count: int = 1) -> None:
    """Create a tiny PDF on disk for tests. Requires PyMuPDF installed."""
    import fitz  # PyMuPDF
    doc = fitz.open()
    try:
        for i in range(page_count):
            page = doc.new_page(width=612, height=792)  # US Letter
            page.insert_text(
                (72, 72),
                f"VO.2a test page {i}",
                fontsize=12,
            )
        doc.save(str(target))
    finally:
        doc.close()


# ─── Renderer tests ─────────────────────────────────────────────────────────


class T_Renderer_Success(unittest.TestCase):
    """render_plan_page_to_png_bytes returns non-empty PNG on valid input."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
        self._pdf = Path(self._tmp) / "tiny.pdf"
        _make_tiny_pdf(self._pdf, page_count=3)

    def tearDown(self) -> None:
        try:
            self._pdf.unlink(missing_ok=True)
            os.rmdir(self._tmp)
        except OSError:
            pass

    def test_render_page_0_returns_png_bytes(self) -> None:
        png = render_plan_page_to_png_bytes(self._pdf, page_index=0, dpi=96)
        self.assertIsInstance(png, bytes)
        self.assertGreater(len(png), 100)
        # PNG magic header
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")

    def test_render_page_2_returns_png_bytes(self) -> None:
        png = render_plan_page_to_png_bytes(self._pdf, page_index=2, dpi=96)
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")

    def test_render_higher_dpi_produces_larger_png(self) -> None:
        small = render_plan_page_to_png_bytes(self._pdf, 0, 48)
        large = render_plan_page_to_png_bytes(self._pdf, 0, 300)
        self.assertGreater(len(large), len(small))


class T_Renderer_FileMissing(unittest.TestCase):
    def test_missing_pdf_raises_plan_page_render_error(self) -> None:
        with self.assertRaises(PlanPageRenderError):
            render_plan_page_to_png_bytes(
                Path("/definitely/does/not/exist.pdf"), 0, 96
            )


class T_Renderer_PageIndexOutOfRange(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
        self._pdf = Path(self._tmp) / "single.pdf"
        _make_tiny_pdf(self._pdf, page_count=1)

    def tearDown(self) -> None:
        try:
            self._pdf.unlink(missing_ok=True)
            os.rmdir(self._tmp)
        except OSError:
            pass

    def test_page_index_negative_raises(self) -> None:
        with self.assertRaises(PlanPageRenderError):
            render_plan_page_to_png_bytes(self._pdf, -1, 96)

    def test_page_index_above_page_count_raises(self) -> None:
        # PDF has 1 page (page_index 0 is valid; 1 is out of range).
        with self.assertRaises(PlanPageRenderError):
            render_plan_page_to_png_bytes(self._pdf, 1, 96)

    def test_page_index_non_int_raises(self) -> None:
        with self.assertRaises(PlanPageRenderError):
            render_plan_page_to_png_bytes(self._pdf, "not an int", 96)  # type: ignore[arg-type]

    def test_page_index_bool_raises(self) -> None:
        # bool is a subclass of int in Python; the helper must reject it.
        with self.assertRaises(PlanPageRenderError):
            render_plan_page_to_png_bytes(self._pdf, True, 96)  # type: ignore[arg-type]


class T_Renderer_DpiBounds(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
        self._pdf = Path(self._tmp) / "one.pdf"
        _make_tiny_pdf(self._pdf, page_count=1)

    def tearDown(self) -> None:
        try:
            self._pdf.unlink(missing_ok=True)
            os.rmdir(self._tmp)
        except OSError:
            pass

    def test_dpi_too_low_raises(self) -> None:
        with self.assertRaises(PlanPageRenderError):
            render_plan_page_to_png_bytes(self._pdf, 0, 47)

    def test_dpi_too_high_raises(self) -> None:
        with self.assertRaises(PlanPageRenderError):
            render_plan_page_to_png_bytes(self._pdf, 0, 301)

    def test_dpi_at_minimum_succeeds(self) -> None:
        png = render_plan_page_to_png_bytes(self._pdf, 0, 48)
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")

    def test_dpi_at_maximum_succeeds(self) -> None:
        png = render_plan_page_to_png_bytes(self._pdf, 0, 300)
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")

    def test_dpi_non_int_raises(self) -> None:
        with self.assertRaises(PlanPageRenderError):
            render_plan_page_to_png_bytes(self._pdf, 0, "96")  # type: ignore[arg-type]


# ─── Cache tests ────────────────────────────────────────────────────────────


class T_Cache_ResolvePath(unittest.TestCase):
    def test_resolve_cache_file_constructs_expected_path(self) -> None:
        session_folder = Path("/tmp/uploads/engineering_plans/sess_abc")
        cf = plan_page_image_cache.resolve_cache_file(
            session_folder=session_folder,
            plan_id="abcdef0123456789",
            page_index=5,
            dpi=96,
        )
        self.assertEqual(
            str(cf).replace("\\", "/"),
            "/tmp/uploads/engineering_plans/sess_abc/_page_cache/abcdef0123456789_5_96.png",
        )

    def test_resolve_cache_file_sanitizes_plan_id(self) -> None:
        # plan_id is SHA256 hex by construction but defense-in-depth
        # sanitization must prevent path-segment escape.  Periods are
        # filename-safe and remain; path separators ('/', '\\') collapse
        # to '_'.  The crucial guarantee: the result is a single filename
        # under <session_folder>/_page_cache/, never a path that escapes
        # via a '..' segment.
        session_folder = Path("/tmp")
        cf = plan_page_image_cache.resolve_cache_file(
            session_folder=session_folder,
            plan_id="../evil/plan",
            page_index=0,
            dpi=96,
        )
        normalized = str(cf).replace("\\", "/")
        # Path separators collapsed → no extra path segments introduced.
        self.assertEqual(cf.parent, session_folder / "_page_cache")
        # File lives under the cache subdir, not anywhere else.
        self.assertTrue(cf.name.endswith("_0_96.png"))
        # No traversal segment in the resolved path.
        self.assertNotIn("/../", normalized)
        # Slashes from the input plan_id were collapsed.
        self.assertNotIn("/evil/", normalized)
        self.assertNotIn("/plan_", normalized)

    def test_resolve_cache_file_coerces_int_args(self) -> None:
        session_folder = Path("/tmp")
        cf = plan_page_image_cache.resolve_cache_file(
            session_folder=session_folder,
            plan_id="x",
            page_index=3.0,  # type: ignore[arg-type]
            dpi=96,
        )
        # int() coercion in the filename
        self.assertIn("x_3_96.png", str(cf).replace("\\", "/"))


class T_Cache_ReadMiss(unittest.TestCase):
    def test_cache_read_absent_returns_none(self) -> None:
        nonexistent = Path(tempfile.gettempdir()) / "no" / "such" / "file.png"
        self.assertIsNone(plan_page_image_cache.cache_read(nonexistent))


class T_Cache_WriteThenRead(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        # Recursive cleanup
        for p in sorted(self._tmp.rglob("*"), reverse=True):
            try:
                if p.is_file():
                    p.unlink()
                else:
                    p.rmdir()
            except OSError:
                pass
        try:
            self._tmp.rmdir()
        except OSError:
            pass

    def test_write_then_read_round_trip(self) -> None:
        cf = plan_page_image_cache.resolve_cache_file(
            session_folder=self._tmp,
            plan_id="abc",
            page_index=0,
            dpi=96,
        )
        # Parent does not yet exist.
        self.assertFalse(cf.parent.exists())
        ok = plan_page_image_cache.cache_write(cf, b"\x89PNG\r\n\x1a\nDUMMY")
        self.assertTrue(ok)
        # cache_write must create the parent.
        self.assertTrue(cf.parent.is_dir())
        # And the file.
        hit = plan_page_image_cache.cache_read(cf)
        self.assertIsNotNone(hit)
        self.assertEqual(hit.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")

    def test_cache_write_atomic_no_partial_file_on_open_failure(self) -> None:
        # If the parent dir cannot be created (e.g. parent is a file),
        # cache_write must return False without leaving a tmp file behind.
        blocker = self._tmp / "blocker"
        blocker.write_text("not a directory")
        cf = blocker / "_page_cache" / "x_0_96.png"
        ok = plan_page_image_cache.cache_write(cf, b"data")
        self.assertFalse(ok)
        # No .tmp file should remain anywhere under self._tmp.
        for p in self._tmp.rglob("*.tmp.*"):
            self.fail(f"tmp file left behind: {p}")


if __name__ == "__main__":
    unittest.main()
