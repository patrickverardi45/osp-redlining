"""PDF Plan Mode Step 2A — endpoint + classification tests.

Targets ``get_engineering_plan_index`` in backend/main.py and the
helper module ``app.core.pdf_plan_index``.

Mirrors the pattern of ``test_engineering_plan_page_image_endpoint.py``:
env defaults at module top, raw-index mock returns realistic plan
records, synthetic PDFs are generated on disk per test scenario.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

os.environ.setdefault("TRUELINE_JWT_SECRET", "pdf-plan-index-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "pdf-plan-index-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend import main as M  # noqa: E402 — must come after env defaults

_FLAG = "TRUELINE_PLAN_OVERLAY_IMAGE"


# ---------------------------------------------------------------------------
# Synthetic-PDF helpers
# ---------------------------------------------------------------------------

def _make_cover_pdf(target: Path) -> None:
    """One-page PDF with cover-sheet vocabulary."""
    import fitz
    doc = fitz.open()
    try:
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 72), "TITLE SHEET", fontsize=24)
        page.insert_text((72, 120), "PROJECT: Brenham Phase 5 — Fiber Build", fontsize=12)
        page.insert_text((72, 144), "SHEET INDEX", fontsize=14)
        page.insert_text((72, 168), "1. Cover", fontsize=10)
        page.insert_text((72, 180), "2. General Notes", fontsize=10)
        page.insert_text((72, 192), "3. Plan 1", fontsize=10)
        doc.save(str(target))
    finally:
        doc.close()


def _make_notes_pdf(target: Path) -> None:
    """One-page PDF with notes-sheet vocabulary."""
    import fitz
    doc = fitz.open()
    try:
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 72), "GENERAL NOTES", fontsize=20)
        page.insert_text((72, 110), "LEGEND", fontsize=14)
        page.insert_text((72, 134), "ABBREVIATIONS: HH = HANDHOLE, SP = SPLICE POINT", fontsize=10)
        page.insert_text((72, 158), "SYMBOLS table below.", fontsize=10)
        doc.save(str(target))
    finally:
        doc.close()


def _make_detail_pdf(target: Path) -> None:
    """One-page PDF with detail-sheet vocabulary — no station chain."""
    import fitz
    doc = fitz.open()
    try:
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 72), "UTILITY POTHOLE REPAIR DETAIL", fontsize=18)
        page.insert_text((72, 110), "TYPICAL SECTION", fontsize=14)
        page.insert_text((72, 134), "NOT TO SCALE", fontsize=10)
        page.insert_text((72, 158), "Section A-A elevation view.", fontsize=10)
        doc.save(str(target))
    finally:
        doc.close()


def _make_plan_sheet_pdf(target: Path) -> None:
    """One-page PDF with realistic plan-sheet content."""
    import fitz
    doc = fitz.open()
    try:
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 72), "OK-51 PROPOSED UNDERGROUND CONSTRUCTION", fontsize=14)
        page.insert_text((72, 110), "MATCHLINE STA 11+60 - SEE SHEET 4", fontsize=10)
        page.insert_text((72, 134), "STA 11+60", fontsize=10)
        page.insert_text((72, 158), "STA 14+20  HANDHOLE", fontsize=10)
        page.insert_text((72, 182), "STA 20+47 DIRECTIONAL BORE", fontsize=10)
        page.insert_text((72, 206), "STA 25+10 SPLICE POINT", fontsize=10)
        page.insert_text((72, 230), "FIBER OPTIC CABLE", fontsize=10)
        page.insert_text((72, 254), "MATCHLINE STA 27+80 - SEE SHEET 6", fontsize=10)
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


class _BaseIndexTest(unittest.TestCase):
    SESSION_ID = "sess_test_pdfplanindex"
    PLAN_ID = "abc123def456pdfplan2a"

    def setUp(self) -> None:
        self._saved_flag = os.environ.pop(_FLAG, None)
        self._tmp_root = Path(tempfile.mkdtemp(prefix="pdf_plan_index_"))
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
        if self._saved_flag is None:
            os.environ.pop(_FLAG, None)
        else:
            os.environ[_FLAG] = self._saved_flag
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

    def _call(self, **kwargs: Any) -> Any:
        defaults: Dict[str, Any] = {
            "plan_id": self.PLAN_ID,
            "session_id": self.SESSION_ID,
            "request": None,
        }
        defaults.update(kwargs)
        return asyncio.run(M.get_engineering_plan_index(**defaults))


def _read_body(response: Any) -> Dict[str, Any]:
    body = response.body
    if isinstance(body, (bytes, bytearray)):
        return json.loads(body.decode("utf-8"))
    return json.loads(body)


# ───────────────────────────────────────────────────────────────────────────
# T1 — env flag off returns 404
# ───────────────────────────────────────────────────────────────────────────


class T1_FlagOff(_BaseIndexTest):
    def _build_pdf(self, target: Path) -> None:
        _make_plan_sheet_pdf(target)

    def test_flag_unset_returns_404(self) -> None:
        os.environ.pop(_FLAG, None)
        response = self._call()
        self.assertEqual(response.status_code, 404)


# ───────────────────────────────────────────────────────────────────────────
# T2 — empty / missing plan_id returns 400 / 404
# ───────────────────────────────────────────────────────────────────────────


class T2_InvalidPlanId(_BaseIndexTest):
    def _build_pdf(self, target: Path) -> None:
        _make_plan_sheet_pdf(target)

    def setUp(self) -> None:
        super().setUp()
        os.environ[_FLAG] = "1"

    def test_empty_plan_id_returns_400(self) -> None:
        response = self._call(plan_id="")
        self.assertEqual(response.status_code, 400)

    def test_unknown_plan_id_returns_404(self) -> None:
        response = self._call(plan_id="not_a_real_plan_id")
        self.assertEqual(response.status_code, 404)


# ───────────────────────────────────────────────────────────────────────────
# T3 — plan_sheet detection on a realistic plan page
# ───────────────────────────────────────────────────────────────────────────


class T3_PlanSheet(_BaseIndexTest):
    def _build_pdf(self, target: Path) -> None:
        _make_plan_sheet_pdf(target)

    def setUp(self) -> None:
        super().setUp()
        os.environ[_FLAG] = "1"

    def test_classifies_as_plan_sheet_with_signals(self) -> None:
        response = self._call()
        self.assertEqual(response.status_code, 200)
        body = _read_body(response)
        self.assertTrue(body.get("success"))
        self.assertEqual(body.get("plan_id"), self.PLAN_ID)
        self.assertEqual(body.get("page_count"), 1)
        self.assertEqual(body.get("schema_version"), "pdf-plan-index-1")
        pages = body.get("pages") or []
        self.assertEqual(len(pages), 1)
        page = pages[0]
        self.assertEqual(page.get("page_index"), 0)
        self.assertEqual(page.get("page_number"), 1)
        self.assertEqual(page.get("classification"), "plan_sheet")
        self.assertTrue(page.get("redline_candidate"))
        self.assertTrue(page.get("text_layer_available"))
        # Route detection — OK-51 should appear
        self.assertIn("OK-51", page.get("route_names") or [])
        # Station chain — at least 3 unique stations
        stations = page.get("station_labels") or []
        self.assertGreaterEqual(len(stations), 3)
        self.assertIn("11+60", stations)
        self.assertIn("14+20", stations)
        # Matchlines — at least one
        matchlines = page.get("matchline_refs") or []
        self.assertGreaterEqual(len(matchlines), 1)
        # Construction keywords
        kws = page.get("construction_keywords") or []
        self.assertTrue(any("handhole" in k.lower() for k in kws))
        self.assertTrue(any("bore" in k.lower() for k in kws))
        # Cache header on first call
        self.assertEqual(body.get("cache"), "miss")


# ───────────────────────────────────────────────────────────────────────────
# T4 — detail_sheet detection
# ───────────────────────────────────────────────────────────────────────────


class T4_DetailSheet(_BaseIndexTest):
    def _build_pdf(self, target: Path) -> None:
        _make_detail_pdf(target)

    def setUp(self) -> None:
        super().setUp()
        os.environ[_FLAG] = "1"

    def test_classifies_as_detail_sheet(self) -> None:
        response = self._call()
        self.assertEqual(response.status_code, 200)
        body = _read_body(response)
        page = (body.get("pages") or [])[0]
        self.assertEqual(page.get("classification"), "detail_sheet")
        self.assertFalse(page.get("redline_candidate"))
        # No station chain
        self.assertEqual(len(page.get("station_labels") or []), 0)


# ───────────────────────────────────────────────────────────────────────────
# T5 — notes_sheet detection
# ───────────────────────────────────────────────────────────────────────────


class T5_NotesSheet(_BaseIndexTest):
    def _build_pdf(self, target: Path) -> None:
        _make_notes_pdf(target)

    def setUp(self) -> None:
        super().setUp()
        os.environ[_FLAG] = "1"

    def test_classifies_as_notes_sheet(self) -> None:
        response = self._call()
        self.assertEqual(response.status_code, 200)
        body = _read_body(response)
        page = (body.get("pages") or [])[0]
        self.assertEqual(page.get("classification"), "notes_sheet")
        self.assertFalse(page.get("redline_candidate"))


# ───────────────────────────────────────────────────────────────────────────
# T6 — cover_sheet detection
# ───────────────────────────────────────────────────────────────────────────


class T6_CoverSheet(_BaseIndexTest):
    def _build_pdf(self, target: Path) -> None:
        _make_cover_pdf(target)

    def setUp(self) -> None:
        super().setUp()
        os.environ[_FLAG] = "1"

    def test_classifies_as_cover_sheet(self) -> None:
        response = self._call()
        self.assertEqual(response.status_code, 200)
        body = _read_body(response)
        page = (body.get("pages") or [])[0]
        self.assertEqual(page.get("classification"), "cover_sheet")
        self.assertFalse(page.get("redline_candidate"))


# ───────────────────────────────────────────────────────────────────────────
# T7 — cache hit on second call
# ───────────────────────────────────────────────────────────────────────────


class T7_CacheHit(_BaseIndexTest):
    def _build_pdf(self, target: Path) -> None:
        _make_plan_sheet_pdf(target)

    def setUp(self) -> None:
        super().setUp()
        os.environ[_FLAG] = "1"

    def test_second_call_serves_from_cache(self) -> None:
        r1 = self._call()
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(_read_body(r1).get("cache"), "miss")
        r2 = self._call()
        self.assertEqual(r2.status_code, 200)
        body2 = _read_body(r2)
        self.assertEqual(body2.get("cache"), "hit")
        # Same classification + same page content
        self.assertEqual(
            (body2.get("pages") or [])[0].get("classification"),
            "plan_sheet",
        )


# ───────────────────────────────────────────────────────────────────────────
# T8 — non-PDF file type returns 400
# ───────────────────────────────────────────────────────────────────────────


class T8_NonPdf(_BaseIndexTest):
    def _build_pdf(self, target: Path) -> None:
        _make_plan_sheet_pdf(target)

    def setUp(self) -> None:
        super().setUp()
        os.environ[_FLAG] = "1"
        # Override the record's file_type to non-PDF and re-patch.
        for p in list(self._patches):
            try:
                p.stop()
            except RuntimeError:
                pass
        self._patches = []
        non_pdf_plan = dict(self._plan)
        non_pdf_plan["file_type"] = "image/png"
        self._patches.append(patch.object(M, "_resolve_session_id", return_value=self.SESSION_ID))
        self._patches.append(patch.object(M, "_require_tenant_owns_session", return_value=None))
        self._patches.append(patch.object(
            M, "_load_engineering_plan_index", return_value={"plans": [non_pdf_plan]}
        ))
        self._patches.append(patch.object(M, "ENGINEERING_PLAN_ROOT", self._eng_root))
        for p in self._patches:
            p.start()

    def test_non_pdf_returns_400(self) -> None:
        response = self._call()
        self.assertEqual(response.status_code, 400)


# ───────────────────────────────────────────────────────────────────────────
# T9 — multi-page PDF index aggregates all pages
# ───────────────────────────────────────────────────────────────────────────


class T9_MultiPageIndex(_BaseIndexTest):
    def _build_pdf(self, target: Path) -> None:
        import fitz
        doc = fitz.open()
        try:
            # Page 0 — cover
            p0 = doc.new_page(width=612, height=792)
            p0.insert_text((72, 72), "TITLE SHEET", fontsize=24)
            p0.insert_text((72, 120), "PROJECT: Multi-Page Test", fontsize=12)
            # Page 1 — notes
            p1 = doc.new_page(width=612, height=792)
            p1.insert_text((72, 72), "GENERAL NOTES", fontsize=18)
            p1.insert_text((72, 110), "LEGEND", fontsize=14)
            p1.insert_text((72, 134), "ABBREVIATIONS", fontsize=12)
            # Page 2 — detail
            p2 = doc.new_page(width=612, height=792)
            p2.insert_text((72, 72), "POTHOLE REPAIR DETAIL", fontsize=18)
            p2.insert_text((72, 110), "TYPICAL SECTION", fontsize=14)
            p2.insert_text((72, 134), "NOT TO SCALE", fontsize=10)
            # Page 3 — plan
            p3 = doc.new_page(width=612, height=792)
            p3.insert_text((72, 72), "OK-51 PROPOSED UNDERGROUND CONSTRUCTION", fontsize=14)
            p3.insert_text((72, 110), "MATCHLINE STA 11+60 - SEE SHEET 4", fontsize=10)
            p3.insert_text((72, 134), "STA 11+60 STA 14+20 STA 20+47 HANDHOLE BORE", fontsize=10)
            doc.save(str(target))
        finally:
            doc.close()

    def setUp(self) -> None:
        super().setUp()
        os.environ[_FLAG] = "1"

    def test_each_page_classified_independently(self) -> None:
        response = self._call()
        self.assertEqual(response.status_code, 200)
        body = _read_body(response)
        self.assertEqual(body.get("page_count"), 4)
        pages = body.get("pages") or []
        self.assertEqual(len(pages), 4)
        classifications = [p.get("classification") for p in pages]
        self.assertEqual(classifications[0], "cover_sheet")
        self.assertEqual(classifications[1], "notes_sheet")
        self.assertEqual(classifications[2], "detail_sheet")
        self.assertEqual(classifications[3], "plan_sheet")
        self.assertTrue(pages[3].get("redline_candidate"))
        self.assertFalse(pages[0].get("redline_candidate"))
        self.assertFalse(pages[1].get("redline_candidate"))
        self.assertFalse(pages[2].get("redline_candidate"))


if __name__ == "__main__":
    unittest.main()
