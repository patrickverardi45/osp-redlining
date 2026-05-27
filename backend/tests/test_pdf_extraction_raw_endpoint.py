"""PDF Extraction E1 — endpoint + helper module tests.

Targets ``get_engineering_plan_extraction_raw`` in backend/main.py and
the helper module ``app.core.pdf_extraction_raw``.

Mirrors the pattern of ``test_pdf_plan_index_endpoint.py``: env defaults
at module top, raw-index mock returns realistic plan records, synthetic
PDFs are generated on disk per test scenario.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

os.environ.setdefault("TRUELINE_JWT_SECRET", "pdf-extraction-raw-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "pdf-extraction-raw-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend import main as M  # noqa: E402 — must come after env defaults
from backend.app.core import pdf_extraction_raw as PER  # noqa: E402

_OVERLAY_FLAG = "TRUELINE_PLAN_OVERLAY_IMAGE"
_EXTRACTION_FLAG = "TRUELINE_PDF_EXTRACTION_RAW_ENABLED"


# ---------------------------------------------------------------------------
# Synthetic-PDF helpers
# ---------------------------------------------------------------------------

def _make_text_only_pdf(target: Path) -> None:
    """One-page PDF with text-only content (no vector drawings)."""
    import fitz
    doc = fitz.open()
    try:
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 72), "OK-51 PROPOSED UNDERGROUND CONSTRUCTION", fontsize=14)
        page.insert_text((72, 110), "STA 11+60  HANDHOLE", fontsize=10)
        page.insert_text((72, 134), "STA 14+20  DIRECTIONAL BORE", fontsize=10)
        page.insert_text((72, 158), "MATCHLINE STA 27+80 - SEE SHEET 6", fontsize=10)
        doc.save(str(target))
    finally:
        doc.close()


def _make_text_and_vectors_pdf(target: Path) -> None:
    """One-page PDF with text + several vector primitives."""
    import fitz
    doc = fitz.open()
    try:
        page = doc.new_page(width=612, height=792)
        # Text blocks
        page.insert_text((72, 72), "PLAN SHEET 4", fontsize=16)
        page.insert_text((72, 110), "STA 12+50", fontsize=10)
        # Vector drawings (each different style for stroke-color test coverage).
        shape = page.new_shape()
        # Red line
        shape.draw_line(fitz.Point(100, 200), fitz.Point(500, 200))
        shape.finish(color=(1, 0, 0), width=2.0)
        # Blue rectangle (stroke only)
        shape.draw_rect(fitz.Rect(100, 250, 400, 300))
        shape.finish(color=(0, 0, 1), width=1.5)
        # Filled grey polygon (rectangle with fill)
        shape.draw_rect(fitz.Rect(100, 350, 300, 400))
        shape.finish(color=(0.5, 0.5, 0.5), fill=(0.9, 0.9, 0.9), width=1.0)
        shape.commit()
        doc.save(str(target))
    finally:
        doc.close()


def _make_empty_pdf(target: Path) -> None:
    """One-page PDF with no text and no vectors (blank page)."""
    import fitz
    doc = fitz.open()
    try:
        doc.new_page(width=612, height=792)
        doc.save(str(target))
    finally:
        doc.close()


def _make_two_page_pdf(target: Path) -> None:
    """Two-page PDF for out-of-range testing."""
    import fitz
    doc = fitz.open()
    try:
        p1 = doc.new_page(width=612, height=792)
        p1.insert_text((72, 72), "PAGE 1", fontsize=14)
        p2 = doc.new_page(width=612, height=792)
        p2.insert_text((72, 72), "PAGE 2", fontsize=14)
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
        "original_filename": stored_path.name,
        "stored_filename": stored_path.name,
        "stored_path": str(stored_path),
        "file_type": file_type,
        "size_bytes": stored_path.stat().st_size if stored_path.exists() else 0,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }


def _read_body(response: Any) -> Dict[str, Any]:
    body = response.body
    if isinstance(body, (bytes, bytearray)):
        return json.loads(body.decode("utf-8"))
    return json.loads(body)


class _BaseExtractionTest(unittest.TestCase):
    SESSION_ID = "sess_test_extractionraw"
    PLAN_ID = "abc123def456extractionraw"

    def setUp(self) -> None:
        self._saved_overlay = os.environ.pop(_OVERLAY_FLAG, None)
        self._saved_extraction = os.environ.pop(_EXTRACTION_FLAG, None)
        self._tmp_root = Path(tempfile.mkdtemp(prefix="pdf_extraction_raw_"))
        self._uploads_dir = self._tmp_root / "uploads"
        self._eng_root = self._uploads_dir / "engineering_plans"
        self._sess_folder = self._eng_root / self.SESSION_ID
        self._sess_folder.mkdir(parents=True, exist_ok=True)
        self._pdf_path = self._sess_folder / "test_plan.pdf"
        self._build_pdf(self._pdf_path)
        self._plan = _make_plan_record(
            plan_id=self.PLAN_ID,
            session_id=self.SESSION_ID,
            stored_path=self._pdf_path,
        )

        self._patches: List[Any] = []
        self._patches.append(patch.object(M, "_resolve_session_id", return_value=self.SESSION_ID))
        self._patches.append(patch.object(M, "_require_tenant_owns_session", return_value=None))
        self._patches.append(patch.object(
            M, "_load_engineering_plan_index", return_value={"plans": [self._plan]}
        ))
        self._patches.append(patch.object(M, "ENGINEERING_PLAN_ROOT", self._eng_root))
        for p in self._patches:
            p.start()

    def tearDown(self) -> None:
        for p in self._patches:
            try:
                p.stop()
            except RuntimeError:
                pass
        for name, saved in (
            (_OVERLAY_FLAG, self._saved_overlay),
            (_EXTRACTION_FLAG, self._saved_extraction),
        ):
            if saved is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = saved
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

    def _build_pdf(self, target: Path) -> None:
        raise NotImplementedError

    def _enable_flags(self) -> None:
        os.environ[_OVERLAY_FLAG] = "1"
        os.environ[_EXTRACTION_FLAG] = "1"

    def _call(self, **kwargs: Any) -> Any:
        defaults: Dict[str, Any] = {
            "plan_id": self.PLAN_ID,
            "page_index": 0,
            "session_id": self.SESSION_ID,
            "request": None,
        }
        defaults.update(kwargs)
        return asyncio.run(M.get_engineering_plan_extraction_raw(**defaults))


# ───────────────────────────────────────────────────────────────────────────
# T1 — parent overlay-image flag OFF returns 404
# ───────────────────────────────────────────────────────────────────────────


class T1_OverlayFlagOff(_BaseExtractionTest):
    def _build_pdf(self, target: Path) -> None:
        _make_text_only_pdf(target)

    def test_overlay_unset_returns_404(self) -> None:
        # Neither flag set → expect 404 from the parent gate.
        os.environ.pop(_OVERLAY_FLAG, None)
        os.environ.pop(_EXTRACTION_FLAG, None)
        response = self._call()
        self.assertEqual(response.status_code, 404)


# ───────────────────────────────────────────────────────────────────────────
# T2 — extraction-specific flag OFF returns 404 even when parent ON
# ───────────────────────────────────────────────────────────────────────────


class T2_ExtractionFlagOff(_BaseExtractionTest):
    def _build_pdf(self, target: Path) -> None:
        _make_text_only_pdf(target)

    def test_extraction_unset_returns_404_even_with_overlay_on(self) -> None:
        os.environ[_OVERLAY_FLAG] = "1"
        os.environ.pop(_EXTRACTION_FLAG, None)
        response = self._call()
        self.assertEqual(response.status_code, 404)


# ───────────────────────────────────────────────────────────────────────────
# T3 — invalid plan_id / page_index returns 400/404
# ───────────────────────────────────────────────────────────────────────────


class T3_InvalidInputs(_BaseExtractionTest):
    def _build_pdf(self, target: Path) -> None:
        _make_text_only_pdf(target)

    def setUp(self) -> None:
        super().setUp()
        self._enable_flags()

    def test_empty_plan_id_returns_400(self) -> None:
        response = self._call(plan_id="")
        self.assertEqual(response.status_code, 400)

    def test_unknown_plan_id_returns_404(self) -> None:
        response = self._call(plan_id="not_a_real_plan_id")
        self.assertEqual(response.status_code, 404)

    def test_missing_page_index_returns_400(self) -> None:
        response = self._call(page_index=None)
        self.assertEqual(response.status_code, 400)

    def test_negative_page_index_returns_400(self) -> None:
        response = self._call(page_index=-1)
        self.assertEqual(response.status_code, 400)

    def test_out_of_range_page_index_returns_404(self) -> None:
        response = self._call(page_index=99)
        self.assertEqual(response.status_code, 404)


# ───────────────────────────────────────────────────────────────────────────
# T4 — text-only PDF: text_blocks populated, vector_paths empty
# ───────────────────────────────────────────────────────────────────────────


class T4_TextOnly(_BaseExtractionTest):
    def _build_pdf(self, target: Path) -> None:
        _make_text_only_pdf(target)

    def setUp(self) -> None:
        super().setUp()
        self._enable_flags()

    def test_text_blocks_returned_with_bbox_and_font(self) -> None:
        response = self._call()
        self.assertEqual(response.status_code, 200)
        body = _read_body(response)
        self.assertTrue(body.get("success"))
        self.assertEqual(body.get("schema_version"), "pdf-extraction-raw-1")
        self.assertEqual(body.get("page_index"), 0)
        self.assertEqual(body.get("page_number"), 1)
        self.assertEqual(body.get("cache"), "miss")
        self.assertTrue(body.get("text_layer_available"))
        self.assertFalse(body.get("text_blocks_truncated"))
        self.assertFalse(body.get("vector_paths_truncated"))
        # Page size: PyMuPDF default new_page is 612 x 792 points.
        size = body.get("page_size_px") or []
        self.assertEqual(len(size), 2)
        self.assertAlmostEqual(size[0], 612.0, places=1)
        self.assertAlmostEqual(size[1], 792.0, places=1)
        # Text blocks: at least 4 inserted lines.
        text_blocks = body.get("text_blocks") or []
        self.assertGreaterEqual(len(text_blocks), 4)
        # Each block has the required shape.
        for tb in text_blocks:
            self.assertIn("text", tb)
            self.assertIn("bbox", tb)
            self.assertEqual(len(tb["bbox"]), 4)
            self.assertIn("font", tb)
            self.assertIn("size", tb)
            self.assertIn("color", tb)
            self.assertIn("block_no", tb)
        # Text content sanity check.
        all_text = " ".join(tb["text"] for tb in text_blocks)
        self.assertIn("OK-51", all_text)
        self.assertIn("STA 11+60", all_text)
        # Vector paths: none on a text-only page (the text glyphs themselves
        # are rendered via the font system, not as drawing operators).
        vector_paths = body.get("vector_paths") or []
        self.assertEqual(len(vector_paths), 0)


# ───────────────────────────────────────────────────────────────────────────
# T5 — text + vectors PDF: both populated, colors detected
# ───────────────────────────────────────────────────────────────────────────


class T5_TextAndVectors(_BaseExtractionTest):
    def _build_pdf(self, target: Path) -> None:
        _make_text_and_vectors_pdf(target)

    def setUp(self) -> None:
        super().setUp()
        self._enable_flags()

    def test_vectors_with_stroke_and_fill_detected(self) -> None:
        response = self._call()
        self.assertEqual(response.status_code, 200)
        body = _read_body(response)
        vector_paths = body.get("vector_paths") or []
        # 3 distinct shapes inserted; PyMuPDF may emit them as 3 path records.
        self.assertGreaterEqual(len(vector_paths), 3)
        # Collect distinct stroke colors observed.
        stroke_colors = {
            p.get("stroke_color") for p in vector_paths if p.get("stroke_color")
        }
        # Red, blue, and grey strokes inserted.
        self.assertIn("#ff0000", stroke_colors)
        self.assertIn("#0000ff", stroke_colors)
        # At least one path has a fill color (the grey filled polygon).
        fill_colors = [p.get("fill_color") for p in vector_paths if p.get("fill_color")]
        self.assertGreaterEqual(len(fill_colors), 1)
        # Each path has the required shape.
        for vp in vector_paths:
            self.assertIn("items", vp)
            self.assertIn("bbox", vp)
            self.assertEqual(len(vp["bbox"]), 4)
            self.assertIn("rule", vp)
            self.assertIn("items_hash", vp)


# ───────────────────────────────────────────────────────────────────────────
# T6 — empty PDF: text_layer_available False, both arrays empty
# ───────────────────────────────────────────────────────────────────────────


class T6_EmptyPage(_BaseExtractionTest):
    def _build_pdf(self, target: Path) -> None:
        _make_empty_pdf(target)

    def setUp(self) -> None:
        super().setUp()
        self._enable_flags()

    def test_empty_page_returns_empty_arrays(self) -> None:
        response = self._call()
        self.assertEqual(response.status_code, 200)
        body = _read_body(response)
        self.assertFalse(body.get("text_layer_available"))
        self.assertEqual(body.get("text_blocks") or [], [])
        self.assertEqual(body.get("vector_paths") or [], [])


# ───────────────────────────────────────────────────────────────────────────
# T7 — cache hit second call (mtime-aware)
# ───────────────────────────────────────────────────────────────────────────


class T7_Cache(_BaseExtractionTest):
    def _build_pdf(self, target: Path) -> None:
        _make_text_only_pdf(target)

    def setUp(self) -> None:
        super().setUp()
        self._enable_flags()

    def test_first_miss_second_hit(self) -> None:
        r1 = self._call()
        self.assertEqual(r1.status_code, 200)
        b1 = _read_body(r1)
        self.assertEqual(b1.get("cache"), "miss")
        # Cache file should now exist.
        cache_file = (
            self._sess_folder
            / "extraction"
            / f"{self.PLAN_ID}_p000_pdf-extraction-raw-1.json"
        )
        self.assertTrue(cache_file.is_file())

        # Second call serves from cache.
        r2 = self._call()
        self.assertEqual(r2.status_code, 200)
        b2 = _read_body(r2)
        self.assertEqual(b2.get("cache"), "hit")
        # Deterministic: byte-identical content modulo cache header.
        for key in ("text_blocks", "vector_paths", "page_size_px", "schema_version"):
            self.assertEqual(b1.get(key), b2.get(key))


# ───────────────────────────────────────────────────────────────────────────
# T8 — deterministic ordering: same PDF → same JSON
# ───────────────────────────────────────────────────────────────────────────


class T8_Deterministic(_BaseExtractionTest):
    def _build_pdf(self, target: Path) -> None:
        _make_text_and_vectors_pdf(target)

    def setUp(self) -> None:
        super().setUp()
        self._enable_flags()

    def test_same_pdf_byte_identical_extraction(self) -> None:
        # First extraction (cache miss).
        b1 = _read_body(self._call())
        # Touch the PDF mtime to force a cache miss on the second call
        # (so we re-run the extractor, not just read cache).
        new_mtime = time.time() + 10
        os.utime(str(self._pdf_path), (new_mtime, new_mtime))
        # Clear the cache file so the second call definitely re-extracts.
        cache_file = (
            self._sess_folder
            / "extraction"
            / f"{self.PLAN_ID}_p000_pdf-extraction-raw-1.json"
        )
        if cache_file.is_file():
            cache_file.unlink()
        b2 = _read_body(self._call())
        # Same extraction primitives across two runs (modulo cache header).
        for key in (
            "schema_version",
            "page_index",
            "page_number",
            "page_size_px",
            "page_rotation",
            "text_blocks",
            "text_blocks_truncated",
            "vector_paths",
            "vector_paths_truncated",
            "text_layer_available",
        ):
            self.assertEqual(b1.get(key), b2.get(key), f"key {key!r} differs across runs")


# ───────────────────────────────────────────────────────────────────────────
# T9 — multi-page PDF: page_index=0 and page_index=1 both work
# ───────────────────────────────────────────────────────────────────────────


class T9_MultiPage(_BaseExtractionTest):
    def _build_pdf(self, target: Path) -> None:
        _make_two_page_pdf(target)

    def setUp(self) -> None:
        super().setUp()
        self._enable_flags()

    def test_two_pages_indexable(self) -> None:
        b0 = _read_body(self._call(page_index=0))
        b1 = _read_body(self._call(page_index=1))
        self.assertEqual(b0.get("page_index"), 0)
        self.assertEqual(b1.get("page_index"), 1)
        all0 = " ".join(tb.get("text", "") for tb in (b0.get("text_blocks") or []))
        all1 = " ".join(tb.get("text", "") for tb in (b1.get("text_blocks") or []))
        self.assertIn("PAGE 1", all0)
        self.assertIn("PAGE 2", all1)

    def test_third_page_returns_404(self) -> None:
        response = self._call(page_index=2)
        self.assertEqual(response.status_code, 404)


# ───────────────────────────────────────────────────────────────────────────
# T10 — helper module direct calls (file-not-found, bad page)
# ───────────────────────────────────────────────────────────────────────────


class T10_HelperDirect(unittest.TestCase):
    def test_missing_file_raises(self) -> None:
        with self.assertRaises(PER.PdfExtractionError):
            PER.extract_page_raw(Path("/does/not/exist.pdf"), 0)

    def test_out_of_range_in_helper_returns_record_with_error(self) -> None:
        tmp_root = Path(tempfile.mkdtemp(prefix="pdf_extraction_raw_helper_"))
        try:
            pdf_path = tmp_root / "x.pdf"
            _make_text_only_pdf(pdf_path)
            rec = PER.extract_page_raw(pdf_path, 99)
            self.assertIn("out of range", str(rec.get("page_load_error") or ""))
            self.assertEqual(rec.get("text_blocks") or [], [])
            self.assertEqual(rec.get("vector_paths") or [], [])
        finally:
            for p in sorted(tmp_root.rglob("*"), reverse=True):
                try:
                    p.unlink() if p.is_file() else p.rmdir()
                except OSError:
                    pass
            try:
                tmp_root.rmdir()
            except OSError:
                pass


if __name__ == "__main__":
    unittest.main()
