"""PDF Extraction E2a — classifier + endpoint tests.

Targets ``classify_vector_paths`` in app/core/pdf_extraction_classify.py
and ``get_engineering_plan_extraction_classified`` in backend/main.py.

Tests are organized into two layers:

  1. Pure-helper tests (no PDF, no FastAPI) for the classifier.
  2. Endpoint tests (mock raw-index, synthetic PDFs) for the
     HTTP surface, mirroring the E1 endpoint test structure.

Color buckets cover the full ODOT_TULSA palette finding from the
2026-05-26 strategy report.
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

os.environ.setdefault("TRUELINE_JWT_SECRET", "pdf-ext-classify-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "pdf-ext-classify-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend import main as M  # noqa: E402
from backend.app.core import pdf_extraction_classify as PEC  # noqa: E402

_OVERLAY_FLAG = "TRUELINE_PLAN_OVERLAY_IMAGE"
_EXTRACTION_FLAG = "TRUELINE_PDF_EXTRACTION_RAW_ENABLED"
_CLASSIFY_FLAG = "TRUELINE_PDF_EXTRACTION_CLASSIFY_ENABLED"


# ---------------------------------------------------------------------------
# Helper: build a minimal `pdf-extraction-raw-1` record by hand
# ---------------------------------------------------------------------------

def _build_raw_record(
    *,
    page_index: int = 0,
    page_size: List[float] = (612.0, 792.0),
    vector_paths: List[Dict[str, Any]] = None,
    text_blocks: List[Dict[str, Any]] = None,
    text_blocks_truncated: bool = False,
    vector_paths_truncated: bool = False,
    text_layer_available: bool = True,
) -> Dict[str, Any]:
    return {
        "schema_version": "pdf-extraction-raw-1",
        "page_index": page_index,
        "page_number": page_index + 1,
        "page_size_px": list(page_size),
        "page_rotation": 0,
        "text_blocks": text_blocks or [],
        "text_blocks_truncated": text_blocks_truncated,
        "vector_paths": vector_paths or [],
        "vector_paths_truncated": vector_paths_truncated,
        "text_layer_available": text_layer_available,
        "extraction_caps": {
            "text_blocks_cap": 5000,
            "vector_paths_cap": 10000,
            "block_text_cap": 4000,
            "path_points_cap": 2000,
        },
        "page_load_error": None,
    }


def _path(items_hash: str, stroke: str = None, fill: str = None,
          bbox=(100.0, 100.0, 200.0, 200.0), width: float = 1.0,
          rule: str = "stroke") -> Dict[str, Any]:
    return {
        "items": [],
        "stroke_color": stroke,
        "stroke_width": width,
        "fill_color":   fill,
        "rule":         rule,
        "bbox":         list(bbox),
        "items_hash":   items_hash,
    }


# ===========================================================================
# PURE HELPER TESTS
# ===========================================================================

class T1_ClassifyColor(unittest.TestCase):
    """Color → bucket mapping."""
    def test_pure_white(self):
        self.assertEqual(PEC.classify_color("#ffffff"), "white_mask")

    def test_near_white(self):
        self.assertEqual(PEC.classify_color("#fafafa"), "white_mask")

    def test_pure_black(self):
        self.assertEqual(PEC.classify_color("#000000"), "base_black")

    def test_near_black(self):
        self.assertEqual(PEC.classify_color("#0a0a0a"), "base_black")

    def test_saturated_red(self):
        self.assertEqual(PEC.classify_color("#ff0000"), "proposed_red")

    def test_off_red(self):
        # #cc1010: r>=0xc0, g and b both <= 0x60
        self.assertEqual(PEC.classify_color("#cc1010"), "proposed_red")

    def test_purple(self):
        self.assertEqual(PEC.classify_color("#bf00ff"), "existing_purple")

    def test_orange(self):
        # #ff7f00: r=0xff, g=0x7f (in 0x40-0xa0), b=0x00
        self.assertEqual(PEC.classify_color("#ff7f00"), "existing_orange")

    def test_blue(self):
        self.assertEqual(PEC.classify_color("#0000ff"), "existing_blue")

    def test_green(self):
        self.assertEqual(PEC.classify_color("#00ff3f"), "row_green")

    def test_dark_green_variant(self):
        # #37dd00 from corpus
        self.assertEqual(PEC.classify_color("#37dd00"), "row_green")

    def test_medium_gray(self):
        self.assertEqual(PEC.classify_color("#545454"), "template_gray")

    def test_mid_gray_989898(self):
        self.assertEqual(PEC.classify_color("#989898"), "template_gray")

    def test_light_gray_dcdcdc(self):
        # All 3 channels equal, but >= 0xd0 — does this go to white_mask?
        # 0xdc >= 0xf0 is False, so it should land in template_gray.
        self.assertEqual(PEC.classify_color("#dcdcdc"), "template_gray")

    def test_yellow_falls_to_other(self):
        # #dddd00 — not in any saturated bucket; the gray rule rejects
        # because b=0 differs from r=g by 0xdd.  Should be "other".
        self.assertEqual(PEC.classify_color("#dddd00"), "other")

    def test_none_input(self):
        self.assertEqual(PEC.classify_color(None), "other")

    def test_malformed_string(self):
        self.assertEqual(PEC.classify_color("not a color"), "other")
        self.assertEqual(PEC.classify_color("#xyz"), "other")
        self.assertEqual(PEC.classify_color(""), "other")

    def test_case_insensitive(self):
        self.assertEqual(PEC.classify_color("#FF0000"), "proposed_red")


class T2_ClassifyEmptyInput(unittest.TestCase):
    """Empty raw extraction → all buckets empty, no crash."""
    def test_empty_vector_paths(self):
        raw = _build_raw_record(vector_paths=[])
        out = PEC.classify_vector_paths(raw)
        self.assertEqual(out["schema_version"], "pdf-extraction-classified-1")
        self.assertEqual(out["source_schema_version"], "pdf-extraction-raw-1")
        for name in PEC.BUCKET_NAMES:
            self.assertEqual(out["bucket_counts"][name], 0)
            self.assertEqual(out["color_buckets"][name], [])
        self.assertEqual(out["template_candidates"], [])
        self.assertEqual(out["unclassified_paths"], [])
        self.assertEqual(out["classification_meta"]["page_path_count_total"], 0)
        self.assertEqual(out["classification_meta"]["page_path_count_classified"], 0)


class T3_ClassifyBasicBucketing(unittest.TestCase):
    """Each ODOT-palette color lands in its expected bucket."""
    def test_red_to_proposed_red(self):
        raw = _build_raw_record(vector_paths=[_path("h_red", stroke="#ff0000")])
        out = PEC.classify_vector_paths(raw)
        self.assertEqual(out["bucket_counts"]["proposed_red"], 1)
        self.assertEqual(out["color_buckets"]["proposed_red"][0]["items_hash"], "h_red")

    def test_full_odot_palette(self):
        raw = _build_raw_record(vector_paths=[
            _path("h_red",    stroke="#ff0000", bbox=(100, 100, 200, 110)),
            _path("h_purple", stroke="#bf00ff", bbox=(100, 200, 200, 210)),
            _path("h_orange", stroke="#ff7f00", bbox=(100, 300, 200, 310)),
            _path("h_blue",   stroke="#0000ff", bbox=(100, 400, 200, 410)),
            _path("h_green",  stroke="#00ff3f", bbox=(100, 500, 200, 510)),
            _path("h_black",  stroke="#000000", bbox=(100, 600, 200, 610)),
            _path("h_gray",   stroke="#545454", bbox=(100, 700, 200, 710)),
            _path("h_white",  stroke="#ffffff", bbox=(200, 100, 300, 110)),
            _path("h_yellow", stroke="#dddd00", bbox=(200, 200, 300, 210)),
        ])
        out = PEC.classify_vector_paths(raw)
        self.assertEqual(out["bucket_counts"]["proposed_red"], 1)
        self.assertEqual(out["bucket_counts"]["existing_purple"], 1)
        self.assertEqual(out["bucket_counts"]["existing_orange"], 1)
        self.assertEqual(out["bucket_counts"]["existing_blue"], 1)
        self.assertEqual(out["bucket_counts"]["row_green"], 1)
        self.assertEqual(out["bucket_counts"]["base_black"], 1)
        self.assertEqual(out["bucket_counts"]["template_gray"], 1)
        self.assertEqual(out["bucket_counts"]["white_mask"], 1)
        # Yellow falls to "other".
        self.assertEqual(out["bucket_counts"]["other"], 1)

    def test_fill_only_falls_through_to_fill_color(self):
        # stroke_color absent → use fill_color.
        raw = _build_raw_record(vector_paths=[
            _path("h_fill_red", stroke=None, fill="#ff0000", rule="fill"),
        ])
        out = PEC.classify_vector_paths(raw)
        self.assertEqual(out["bucket_counts"]["proposed_red"], 1)

    def test_no_colors_lands_in_unclassified(self):
        raw = _build_raw_record(vector_paths=[
            _path("h_no_color", stroke=None, fill=None),
        ])
        out = PEC.classify_vector_paths(raw)
        # No stroke or fill → bucket is "other" AND items_hash in unclassified_paths.
        self.assertEqual(out["bucket_counts"]["other"], 1)
        self.assertIn("h_no_color", out["unclassified_paths"])


class T4_ProvenancePreserved(unittest.TestCase):
    """Each bucketed path keeps items_hash + bbox + style for downstream."""
    def test_items_hash_and_bbox_in_output(self):
        raw = _build_raw_record(vector_paths=[
            _path("hash_alpha", stroke="#ff0000", bbox=(10.0, 20.0, 30.0, 40.0), width=2.5, rule="stroke"),
        ])
        out = PEC.classify_vector_paths(raw)
        red = out["color_buckets"]["proposed_red"][0]
        self.assertEqual(red["items_hash"], "hash_alpha")
        self.assertEqual(red["bbox"], [10.0, 20.0, 30.0, 40.0])
        self.assertEqual(red["stroke_color"], "#ff0000")
        self.assertEqual(red["stroke_width"], 2.5)
        self.assertEqual(red["rule"], "stroke")
        # `items` itself is NOT preserved (intentional — caller joins by hash).
        self.assertNotIn("items", red)


class T5_DeterministicOrdering(unittest.TestCase):
    """Same raw input → same classified output (byte-identical via json.dumps)."""
    def test_byte_identical_across_two_runs(self):
        raw = _build_raw_record(vector_paths=[
            _path("h_c", stroke="#ff0000", bbox=(100, 300, 200, 310)),
            _path("h_a", stroke="#ff0000", bbox=(100, 100, 200, 110)),
            _path("h_b", stroke="#ff0000", bbox=(100, 200, 200, 210)),
            _path("h_d", stroke="#bf00ff", bbox=(50, 50, 60, 60)),
        ])
        o1 = PEC.classify_vector_paths(raw)
        o2 = PEC.classify_vector_paths(raw)
        # Top-level structural equality.
        self.assertEqual(json.dumps(o1, sort_keys=True), json.dumps(o2, sort_keys=True))
        # Within the red bucket, ordering is by (y0, x0, items_hash).
        reds = o1["color_buckets"]["proposed_red"]
        self.assertEqual([r["items_hash"] for r in reds], ["h_a", "h_b", "h_c"])


class T6_TemplateCandidatesConservative(unittest.TestCase):
    """Template-candidate detection should NOT over-classify.

    A single normal red path on a normal-sized page is NOT a template
    candidate.  A repeated items_hash IS.  A tiny gray bbox IS.  A gray
    bbox at the page edge IS.
    """
    def test_single_red_path_is_not_template_candidate(self):
        raw = _build_raw_record(vector_paths=[
            _path("h_red", stroke="#ff0000", bbox=(100, 100, 500, 110)),
        ])
        out = PEC.classify_vector_paths(raw)
        self.assertEqual(out["template_candidates"], [])

    def test_repeated_items_hash_flagged(self):
        # Two paths sharing the same items_hash — typical of a stamp /
        # repeated symbol.  Helper currently flags by hash only;
        # caller can de-dup later.
        raw = _build_raw_record(vector_paths=[
            _path("h_dup", stroke="#000000", bbox=(100, 100, 110, 110)),
            _path("h_dup", stroke="#000000", bbox=(200, 200, 210, 210)),
        ])
        out = PEC.classify_vector_paths(raw)
        self.assertIn("h_dup", out["template_candidates"])
        self.assertIn("h_dup", out["template_reasons"])
        self.assertTrue(out["template_reasons"]["h_dup"].startswith("repeated"))

    def test_tiny_gray_path_flagged(self):
        raw = _build_raw_record(vector_paths=[
            _path("h_tiny", stroke="#808080", bbox=(100, 100, 102, 102)),  # 2x2 → area 4 < 25
        ])
        out = PEC.classify_vector_paths(raw)
        self.assertIn("h_tiny", out["template_candidates"])

    def test_gray_path_at_page_edge_flagged(self):
        # Page is 612x792; bbox at left edge x=0..5 with reasonable size.
        raw = _build_raw_record(vector_paths=[
            _path("h_edge", stroke="#808080", bbox=(0.0, 50.0, 5.0, 700.0)),
        ])
        out = PEC.classify_vector_paths(raw)
        self.assertIn("h_edge", out["template_candidates"])

    def test_red_path_at_page_edge_not_flagged(self):
        # Edge-rule only fires for gray paths.  A red path at the edge
        # might legitimately be a route line wrapping the sheet.
        raw = _build_raw_record(vector_paths=[
            _path("h_red_edge", stroke="#ff0000", bbox=(0.0, 50.0, 5.0, 700.0)),
        ])
        out = PEC.classify_vector_paths(raw)
        self.assertNotIn("h_red_edge", out["template_candidates"])


class T7_MalformedInputHandling(unittest.TestCase):
    """Malformed records raise ValueError for schema mismatch but
    tolerate per-path malformation gracefully."""
    def test_non_dict_input_raises(self):
        with self.assertRaises(ValueError):
            PEC.classify_vector_paths("not a dict")  # type: ignore

    def test_wrong_schema_raises(self):
        bad = _build_raw_record()
        bad["schema_version"] = "wrong-schema"
        with self.assertRaises(ValueError):
            PEC.classify_vector_paths(bad)

    def test_malformed_path_skipped_silently(self):
        # vector_paths contains a string instead of a dict — should be skipped.
        raw = _build_raw_record(vector_paths=[
            "not a dict",  # type: ignore[list-item]
            _path("h_ok", stroke="#ff0000"),
        ])
        out = PEC.classify_vector_paths(raw)
        self.assertEqual(out["bucket_counts"]["proposed_red"], 1)

    def test_malformed_bbox_does_not_crash_template_check(self):
        raw = _build_raw_record(vector_paths=[
            {"items_hash": "h_x", "stroke_color": "#808080", "bbox": "not a bbox", "items": []},
        ])
        # Should not raise.
        out = PEC.classify_vector_paths(raw)
        # Path still gets a bucket assignment based on color.
        self.assertEqual(out["bucket_counts"]["template_gray"], 1)


class T8_SourceMetaCarriedThrough(unittest.TestCase):
    """Source-level truncation/availability flags appear in
    classification_meta so consumers know the raw input wasn't complete."""
    def test_text_layer_unavailable_flag_carried(self):
        raw = _build_raw_record(text_layer_available=False)
        out = PEC.classify_vector_paths(raw)
        self.assertFalse(out["classification_meta"]["source_text_layer_available"])

    def test_vector_paths_truncated_flag_carried(self):
        raw = _build_raw_record(vector_paths_truncated=True)
        out = PEC.classify_vector_paths(raw)
        self.assertTrue(out["classification_meta"]["source_vector_paths_truncated"])

    def test_page_meta_copied(self):
        raw = _build_raw_record(page_index=4, page_size=(2448.0, 1584.0))
        raw["page_rotation"] = 270
        out = PEC.classify_vector_paths(raw)
        self.assertEqual(out["page_index"], 4)
        self.assertEqual(out["page_number"], 5)
        self.assertEqual(out["page_size_px"], [2448.0, 1584.0])
        self.assertEqual(out["page_rotation"], 270)


# ===========================================================================
# ENDPOINT TESTS
# ===========================================================================

def _make_text_only_pdf(target: Path) -> None:
    """One-page PDF with text only (no vectors)."""
    import fitz
    doc = fitz.open()
    try:
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 72), "OK-51 PROPOSED UNDERGROUND", fontsize=14)
        page.insert_text((72, 110), "STA 11+60", fontsize=10)
        doc.save(str(target))
    finally:
        doc.close()


def _make_palette_pdf(target: Path) -> None:
    """One-page PDF with a strip of the ODOT palette so the classifier
    has real PyMuPDF-emitted color values to bucket."""
    import fitz
    doc = fitz.open()
    try:
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 72), "PALETTE", fontsize=14)
        shape = page.new_shape()
        # Red line (proposed_red)
        shape.draw_line(fitz.Point(72, 110), fitz.Point(540, 110))
        shape.finish(color=(1, 0, 0), width=1.5)
        # Blue line (existing_blue)
        shape.draw_line(fitz.Point(72, 140), fitz.Point(540, 140))
        shape.finish(color=(0, 0, 1), width=1.5)
        # Green line (row_green)
        shape.draw_line(fitz.Point(72, 170), fitz.Point(540, 170))
        shape.finish(color=(0, 1, 0.25), width=1.5)
        shape.commit()
        doc.save(str(target))
    finally:
        doc.close()


def _make_plan_record(plan_id: str, session_id: str, stored_path: Path,
                      file_type: str = "application/pdf") -> Dict[str, Any]:
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


class _BaseEndpointTest(unittest.TestCase):
    SESSION_ID = "sess_test_classify"
    PLAN_ID = "abc123classify"

    def setUp(self) -> None:
        self._saved = {f: os.environ.pop(f, None) for f in (_OVERLAY_FLAG, _EXTRACTION_FLAG, _CLASSIFY_FLAG)}
        self._tmp_root = Path(tempfile.mkdtemp(prefix="pdf_ext_classify_"))
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
        for name, saved in self._saved.items():
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

    def _enable_all_flags(self) -> None:
        os.environ[_OVERLAY_FLAG] = "1"
        os.environ[_EXTRACTION_FLAG] = "1"
        os.environ[_CLASSIFY_FLAG] = "1"

    def _call(self, **kwargs: Any) -> Any:
        defaults: Dict[str, Any] = {
            "plan_id": self.PLAN_ID,
            "page_index": 0,
            "session_id": self.SESSION_ID,
            "request": None,
        }
        defaults.update(kwargs)
        return asyncio.run(M.get_engineering_plan_extraction_classified(**defaults))


# ---------------------------------------------------------------------------
# T9 — flag gating returns 404 when ANY of the 3 flags is off
# ---------------------------------------------------------------------------

class T9_FlagGating(_BaseEndpointTest):
    def _build_pdf(self, target: Path) -> None:
        _make_text_only_pdf(target)

    def test_overlay_unset_returns_404(self) -> None:
        # All flags unset.
        for f in (_OVERLAY_FLAG, _EXTRACTION_FLAG, _CLASSIFY_FLAG):
            os.environ.pop(f, None)
        r = self._call()
        self.assertEqual(r.status_code, 404)

    def test_classify_unset_with_overlay_and_raw_on_returns_404(self) -> None:
        os.environ[_OVERLAY_FLAG] = "1"
        os.environ[_EXTRACTION_FLAG] = "1"
        os.environ.pop(_CLASSIFY_FLAG, None)
        r = self._call()
        self.assertEqual(r.status_code, 404)

    def test_raw_unset_with_overlay_and_classify_on_returns_404(self) -> None:
        os.environ[_OVERLAY_FLAG] = "1"
        os.environ.pop(_EXTRACTION_FLAG, None)
        os.environ[_CLASSIFY_FLAG] = "1"
        r = self._call()
        self.assertEqual(r.status_code, 404)


# ---------------------------------------------------------------------------
# T10 — invalid plan_id / page_index returns 400/404
# ---------------------------------------------------------------------------

class T10_InvalidInputs(_BaseEndpointTest):
    def _build_pdf(self, target: Path) -> None:
        _make_text_only_pdf(target)

    def setUp(self) -> None:
        super().setUp()
        self._enable_all_flags()

    def test_empty_plan_id_returns_400(self) -> None:
        self.assertEqual(self._call(plan_id="").status_code, 400)

    def test_unknown_plan_id_returns_404(self) -> None:
        self.assertEqual(self._call(plan_id="nope").status_code, 404)

    def test_missing_page_index_returns_400(self) -> None:
        self.assertEqual(self._call(page_index=None).status_code, 400)

    def test_negative_page_index_returns_400(self) -> None:
        self.assertEqual(self._call(page_index=-1).status_code, 400)

    def test_out_of_range_page_index_returns_404(self) -> None:
        self.assertEqual(self._call(page_index=99).status_code, 404)


# ---------------------------------------------------------------------------
# T11 — happy path with palette PDF, color buckets populated
# ---------------------------------------------------------------------------

class T11_HappyPath(_BaseEndpointTest):
    def _build_pdf(self, target: Path) -> None:
        _make_palette_pdf(target)

    def setUp(self) -> None:
        super().setUp()
        self._enable_all_flags()

    def test_palette_pdf_bucketed(self) -> None:
        r = self._call()
        self.assertEqual(r.status_code, 200)
        body = _read_body(r)
        self.assertTrue(body.get("success"))
        self.assertEqual(body.get("schema_version"), "pdf-extraction-classified-1")
        self.assertEqual(body.get("source_schema_version"), "pdf-extraction-raw-1")
        self.assertEqual(body.get("cache"), "miss")
        bc = body.get("bucket_counts") or {}
        # Each of the three strokes should land in the expected bucket.
        self.assertGreaterEqual(bc.get("proposed_red", 0), 1)
        self.assertGreaterEqual(bc.get("existing_blue", 0), 1)
        self.assertGreaterEqual(bc.get("row_green", 0), 1)


# ---------------------------------------------------------------------------
# T12 — cache miss then hit
# ---------------------------------------------------------------------------

class T12_Cache(_BaseEndpointTest):
    def _build_pdf(self, target: Path) -> None:
        _make_palette_pdf(target)

    def setUp(self) -> None:
        super().setUp()
        self._enable_all_flags()

    def test_first_miss_second_hit(self) -> None:
        r1 = self._call()
        self.assertEqual(r1.status_code, 200)
        b1 = _read_body(r1)
        self.assertEqual(b1.get("cache"), "miss")
        # Classified cache file written.
        cache_file = (
            self._sess_folder
            / "extraction"
            / f"{self.PLAN_ID}_p000_pdf-extraction-classified-1.json"
        )
        self.assertTrue(cache_file.is_file())
        # Raw cache file also written as a side effect of the classified call.
        raw_cache_file = (
            self._sess_folder
            / "extraction"
            / f"{self.PLAN_ID}_p000_pdf-extraction-raw-1.json"
        )
        self.assertTrue(raw_cache_file.is_file())

        r2 = self._call()
        self.assertEqual(r2.status_code, 200)
        b2 = _read_body(r2)
        self.assertEqual(b2.get("cache"), "hit")
        # Same classified buckets across runs.
        self.assertEqual(b1.get("color_buckets"), b2.get("color_buckets"))
        self.assertEqual(b1.get("bucket_counts"), b2.get("bucket_counts"))


# ---------------------------------------------------------------------------
# T13 — endpoint requires session ownership (delegates to
# _require_tenant_owns_session like E1).  We assert the call is made.
# ---------------------------------------------------------------------------

class T13_OwnershipDelegation(_BaseEndpointTest):
    def _build_pdf(self, target: Path) -> None:
        _make_palette_pdf(target)

    def setUp(self) -> None:
        super().setUp()
        self._enable_all_flags()

    def test_require_tenant_owns_session_invoked(self) -> None:
        # The mock for _require_tenant_owns_session is installed in
        # _BaseEndpointTest; spy on it via .mock_calls after a happy call.
        with patch.object(M, "_require_tenant_owns_session", return_value=None) as spy:
            r = self._call()
            self.assertEqual(r.status_code, 200)
            # Called once, with our resolved session id.
            self.assertEqual(spy.call_count, 1)
            args, _ = spy.call_args
            self.assertEqual(args[0], self.SESSION_ID)


if __name__ == "__main__":
    unittest.main()
