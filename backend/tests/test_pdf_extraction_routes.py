"""PDF Extraction E2b — route candidate grouper + endpoint tests.

Targets ``group_route_candidates`` in app/core/pdf_extraction_routes.py
and ``get_engineering_plan_extraction_route_candidates`` in
backend/main.py.

Two layers:

  1. Pure-helper tests (no PDF, no FastAPI) for the grouper.
  2. Endpoint tests (mock raw-index, synthetic PDFs) for the HTTP
     surface, mirroring the E2a endpoint test structure.
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

os.environ.setdefault("TRUELINE_JWT_SECRET", "pdf-ext-routes-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "pdf-ext-routes-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend import main as M  # noqa: E402
from backend.app.core import pdf_extraction_routes as PER  # noqa: E402
from backend.app.core import pdf_extraction_classify as PEC  # noqa: E402

_OVERLAY_FLAG = "TRUELINE_PLAN_OVERLAY_IMAGE"
_RAW_FLAG = "TRUELINE_PDF_EXTRACTION_RAW_ENABLED"
_CLASSIFY_FLAG = "TRUELINE_PDF_EXTRACTION_CLASSIFY_ENABLED"
_ROUTES_FLAG = "TRUELINE_PDF_EXTRACTION_ROUTES_ENABLED"


# ---------------------------------------------------------------------------
# Helper builders for synthetic E1 raw + E2a classified records
# ---------------------------------------------------------------------------

def _raw_path(items_hash: str, stroke: str = "#ff0000",
              items: List[Any] = None, bbox=(0.0, 0.0, 100.0, 0.5),
              fill: str = None, width: float = 1.0,
              rule: str = "stroke") -> Dict[str, Any]:
    return {
        "items":        items or [],
        "stroke_color": stroke,
        "stroke_width": width,
        "fill_color":   fill,
        "rule":         rule,
        "bbox":         list(bbox),
        "items_hash":   items_hash,
    }


def _build_raw(vector_paths: List[Dict[str, Any]] = None,
               page_size=(612.0, 792.0)) -> Dict[str, Any]:
    return {
        "schema_version": "pdf-extraction-raw-1",
        "page_index": 0,
        "page_number": 1,
        "page_size_px": list(page_size),
        "page_rotation": 0,
        "text_blocks": [],
        "text_blocks_truncated": False,
        "vector_paths": vector_paths or [],
        "vector_paths_truncated": False,
        "text_layer_available": True,
        "extraction_caps": {
            "text_blocks_cap": 5000,
            "vector_paths_cap": 10000,
            "block_text_cap": 4000,
            "path_points_cap": 2000,
        },
        "page_load_error": None,
    }


def _classify_via_e2a(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Run the real E2a classifier so the input shape is byte-aligned
    with what the production endpoint feeds to E2b."""
    return PEC.classify_vector_paths(raw)


# ===========================================================================
# PURE HELPER TESTS
# ===========================================================================

class T1_EmptyInput(unittest.TestCase):
    def test_empty_bucket_yields_no_candidates(self):
        raw = _build_raw(vector_paths=[])
        classified = _classify_via_e2a(raw)
        out = PER.group_route_candidates(classified, raw_record=raw)
        self.assertEqual(out["schema_version"], "pdf-extraction-routes-1")
        self.assertEqual(out["bucket"], "proposed_red")
        self.assertEqual(out["route_candidates"], [])
        self.assertEqual(out["filtered_short"], [])
        self.assertEqual(out["meta"]["input_path_count"], 0)
        self.assertEqual(out["meta"]["candidate_count"], 0)

    def test_bucket_with_zero_red_paths_yields_no_candidates(self):
        # Bucket exists but contains only purple paths; requesting
        # proposed_red bucket returns 0 candidates.
        raw = _build_raw(vector_paths=[
            _raw_path("h_p", stroke="#bf00ff", bbox=(10, 10, 50, 11),
                      items=[["l", [10.0, 10.5], [50.0, 10.5]]]),
        ])
        classified = _classify_via_e2a(raw)
        out = PER.group_route_candidates(classified, raw_record=raw, bucket="proposed_red")
        self.assertEqual(out["route_candidates"], [])
        # Sanity: purple bucket has paths.
        self.assertEqual(classified["bucket_counts"]["existing_purple"], 1)
        self.assertEqual(classified["bucket_counts"]["proposed_red"], 0)


class T2_SingleConnectedRoute(unittest.TestCase):
    """A path with three connected line segments forms ONE candidate."""
    def test_three_line_path_one_candidate(self):
        raw = _build_raw(vector_paths=[
            _raw_path(
                "h_red", stroke="#ff0000",
                bbox=(0, 0, 100, 0.5),
                items=[
                    ["l", [0.0, 0.5], [30.0, 0.5]],
                    ["l", [30.0, 0.5], [60.0, 0.5]],
                    ["l", [60.0, 0.5], [100.0, 0.5]],
                ],
            ),
        ])
        classified = _classify_via_e2a(raw)
        out = PER.group_route_candidates(classified, raw_record=raw)
        self.assertEqual(len(out["route_candidates"]), 1)
        c = out["route_candidates"][0]
        self.assertEqual(c["path_count"], 1)
        self.assertEqual(c["segment_count"], 3)
        self.assertEqual(c["total_length_pt"], 100.0)
        # 2 free endpoints (start of first segment, end of last).
        self.assertEqual(c["confidence"]["free_endpoint_count"], 2)
        self.assertEqual(c["confidence"]["kind"], "single_path")
        self.assertEqual(c["dominant_orientation"], "horizontal")
        self.assertEqual(c["source_items_hashes"], ["h_red"])


class T3_DisconnectedGroups(unittest.TestCase):
    """Two physically-separated red lines form TWO candidates."""
    def test_two_disconnected_lines(self):
        raw = _build_raw(vector_paths=[
            _raw_path(
                "h_a", stroke="#ff0000",
                bbox=(0, 0, 100, 0.5),
                items=[["l", [0.0, 0.5], [100.0, 0.5]]],
            ),
            _raw_path(
                "h_b", stroke="#ff0000",
                bbox=(0, 200, 100, 200.5),
                items=[["l", [0.0, 200.5], [100.0, 200.5]]],
            ),
        ])
        classified = _classify_via_e2a(raw)
        out = PER.group_route_candidates(classified, raw_record=raw)
        self.assertEqual(len(out["route_candidates"]), 2)
        ids = [c["candidate_id"] for c in out["route_candidates"]]
        self.assertEqual(ids, ["rc_0000", "rc_0001"])


class T4_EndpointProximityGrouping(unittest.TestCase):
    """Two lines whose endpoints are within eps merge into ONE candidate."""
    def test_lines_share_endpoint_eps_2(self):
        raw = _build_raw(vector_paths=[
            _raw_path(
                "h_a", stroke="#ff0000",
                bbox=(0, 0, 50, 0.5),
                items=[["l", [0.0, 0.5], [50.0, 0.5]]],
            ),
            _raw_path(
                "h_b", stroke="#ff0000",
                bbox=(50, 0, 100, 0.5),
                items=[["l", [50.5, 0.5], [100.0, 0.5]]],  # 0.5pt gap < eps=2
            ),
        ])
        classified = _classify_via_e2a(raw)
        out = PER.group_route_candidates(classified, raw_record=raw, endpoint_eps_pt=2.0)
        self.assertEqual(len(out["route_candidates"]), 1)
        c = out["route_candidates"][0]
        self.assertEqual(c["path_count"], 2)
        self.assertEqual(c["confidence"]["kind"], "multi_path_connected")
        self.assertEqual(c["confidence"]["free_endpoint_count"], 2)
        self.assertEqual(set(c["source_items_hashes"]), {"h_a", "h_b"})

    def test_endpoint_outside_eps_does_not_merge(self):
        raw = _build_raw(vector_paths=[
            _raw_path(
                "h_a", stroke="#ff0000",
                bbox=(0, 0, 50, 0.5),
                items=[["l", [0.0, 0.5], [50.0, 0.5]]],
            ),
            _raw_path(
                "h_b", stroke="#ff0000",
                bbox=(60, 0, 110, 0.5),
                items=[["l", [60.0, 0.5], [110.0, 0.5]]],  # 10pt gap > eps=2
            ),
        ])
        classified = _classify_via_e2a(raw)
        out = PER.group_route_candidates(classified, raw_record=raw, endpoint_eps_pt=2.0)
        self.assertEqual(len(out["route_candidates"]), 2)


class T5_MinLengthFilter(unittest.TestCase):
    """Short groups land in filtered_short, not route_candidates."""
    def test_short_path_filtered(self):
        raw = _build_raw(vector_paths=[
            _raw_path(
                "h_long", stroke="#ff0000",
                bbox=(0, 0, 100, 0.5),
                items=[["l", [0.0, 0.5], [100.0, 0.5]]],
            ),
            _raw_path(
                "h_short", stroke="#ff0000",
                bbox=(0, 100, 5, 100.5),
                items=[["l", [0.0, 100.5], [5.0, 100.5]]],  # length 5 < min 20
            ),
        ])
        classified = _classify_via_e2a(raw)
        out = PER.group_route_candidates(classified, raw_record=raw, min_length_pt=20.0)
        self.assertEqual(len(out["route_candidates"]), 1)
        self.assertEqual(out["route_candidates"][0]["source_items_hashes"], ["h_long"])
        self.assertEqual(len(out["filtered_short"]), 1)
        self.assertEqual(out["filtered_short"][0]["source_items_hashes"], ["h_short"])


class T6_DeterministicOrdering(unittest.TestCase):
    """Same input → byte-identical output."""
    def test_byte_identical_twice(self):
        raw = _build_raw(vector_paths=[
            _raw_path("h_c", stroke="#ff0000", bbox=(0, 300, 50, 300.5),
                      items=[["l", [0.0, 300.5], [50.0, 300.5]]]),
            _raw_path("h_a", stroke="#ff0000", bbox=(0, 100, 50, 100.5),
                      items=[["l", [0.0, 100.5], [50.0, 100.5]]]),
            _raw_path("h_b", stroke="#ff0000", bbox=(0, 200, 50, 200.5),
                      items=[["l", [0.0, 200.5], [50.0, 200.5]]]),
        ])
        classified = _classify_via_e2a(raw)
        o1 = PER.group_route_candidates(classified, raw_record=raw)
        o2 = PER.group_route_candidates(classified, raw_record=raw)
        self.assertEqual(json.dumps(o1, sort_keys=True), json.dumps(o2, sort_keys=True))
        # Top-to-bottom ordering by bbox y0.
        ids = [c["candidate_id"] for c in o1["route_candidates"]]
        hashes = [c["source_items_hashes"][0] for c in o1["route_candidates"]]
        self.assertEqual(ids, ["rc_0000", "rc_0001", "rc_0002"])
        self.assertEqual(hashes, ["h_a", "h_b", "h_c"])  # sorted by y0


class T7_ProvenancePreserved(unittest.TestCase):
    """items_hashes from the bucket are carried through end-to-end."""
    def test_items_hashes_preserved(self):
        raw = _build_raw(vector_paths=[
            _raw_path("hash_one", stroke="#ff0000", bbox=(0, 0, 50, 0.5),
                      items=[["l", [0.0, 0.5], [50.0, 0.5]]]),
            _raw_path("hash_two", stroke="#ff0000", bbox=(50, 0, 100, 0.5),
                      items=[["l", [50.0, 0.5], [100.0, 0.5]]]),
        ])
        classified = _classify_via_e2a(raw)
        out = PER.group_route_candidates(classified, raw_record=raw)
        # Two paths share an endpoint → one candidate.
        self.assertEqual(len(out["route_candidates"]), 1)
        c = out["route_candidates"][0]
        self.assertEqual(set(c["source_items_hashes"]), {"hash_one", "hash_two"})


class T8_MalformedGeometryHandled(unittest.TestCase):
    """Garbage items/bboxes don't crash; path is best-effort skipped or proxy'd."""
    def test_malformed_items_does_not_crash(self):
        raw = _build_raw(vector_paths=[
            _raw_path("h_bad", stroke="#ff0000", bbox=(0, 0, 50, 0.5),
                      items=[["l", "not a point", [50.0, 0.5]]]),
            _raw_path("h_good", stroke="#ff0000", bbox=(0, 100, 50, 100.5),
                      items=[["l", [0.0, 100.5], [50.0, 100.5]]]),
        ])
        classified = _classify_via_e2a(raw)
        # Should not raise.
        out = PER.group_route_candidates(classified, raw_record=raw)
        # h_good still produces a candidate; h_bad either gets a zero-length
        # candidate (filtered by min_length=20) or none.  Either way no crash.
        hashes = {h for c in out["route_candidates"] for h in c["source_items_hashes"]}
        self.assertIn("h_good", hashes)

    def test_malformed_bbox_does_not_crash(self):
        raw = _build_raw(vector_paths=[
            {"items_hash": "h_bb", "stroke_color": "#ff0000",
             "bbox": "not a bbox",
             "items": [["l", [0.0, 0.0], [50.0, 0.0]]]},
        ])
        classified = _classify_via_e2a(raw)
        # Should not raise; path with bad bbox is skipped from grouping.
        out = PER.group_route_candidates(classified, raw_record=raw)
        self.assertIsInstance(out["route_candidates"], list)


class T9_BboxProxyFallback(unittest.TestCase):
    """When raw_record is omitted, falls back to bbox-corner proxies and
    flags the confidence as bbox_proxy."""
    def test_bbox_proxy_kind_set(self):
        raw = _build_raw(vector_paths=[
            _raw_path("h_a", stroke="#ff0000", bbox=(0, 0, 100, 0.5),
                      items=[["l", [0.0, 0.5], [100.0, 0.5]]]),
        ])
        classified = _classify_via_e2a(raw)
        # Call WITHOUT raw_record.
        out = PER.group_route_candidates(classified, raw_record=None)
        self.assertFalse(out["meta"]["raw_record_provided"])
        # At least one candidate should be flagged bbox_proxy.
        if out["route_candidates"]:
            self.assertEqual(out["route_candidates"][0]["confidence"]["kind"], "bbox_proxy")


class T10_SchemaValidation(unittest.TestCase):
    def test_non_dict_input_raises(self):
        with self.assertRaises(PER.PdfExtractionRoutesError):
            PER.group_route_candidates("not a dict")  # type: ignore

    def test_wrong_classified_schema_raises(self):
        bad = _classify_via_e2a(_build_raw())
        bad["schema_version"] = "wrong-schema"
        with self.assertRaises(PER.PdfExtractionRoutesError):
            PER.group_route_candidates(bad)

    def test_wrong_raw_schema_raises(self):
        classified = _classify_via_e2a(_build_raw())
        bad_raw = _build_raw()
        bad_raw["schema_version"] = "wrong-raw-schema"
        with self.assertRaises(PER.PdfExtractionRoutesError):
            PER.group_route_candidates(classified, raw_record=bad_raw)


class T11_DominantOrientation(unittest.TestCase):
    def test_horizontal(self):
        raw = _build_raw(vector_paths=[
            _raw_path("h_h", stroke="#ff0000", bbox=(0, 0, 200, 5),
                      items=[["l", [0.0, 2.5], [200.0, 2.5]]]),
        ])
        out = PER.group_route_candidates(_classify_via_e2a(raw), raw_record=raw)
        self.assertEqual(out["route_candidates"][0]["dominant_orientation"], "horizontal")

    def test_vertical(self):
        raw = _build_raw(vector_paths=[
            _raw_path("h_v", stroke="#ff0000", bbox=(0, 0, 5, 200),
                      items=[["l", [2.5, 0.0], [2.5, 200.0]]]),
        ])
        out = PER.group_route_candidates(_classify_via_e2a(raw), raw_record=raw)
        self.assertEqual(out["route_candidates"][0]["dominant_orientation"], "vertical")

    def test_mixed(self):
        raw = _build_raw(vector_paths=[
            _raw_path("h_d", stroke="#ff0000", bbox=(0, 0, 100, 100),
                      items=[["l", [0.0, 0.0], [100.0, 100.0]]]),
        ])
        out = PER.group_route_candidates(_classify_via_e2a(raw), raw_record=raw)
        self.assertEqual(out["route_candidates"][0]["dominant_orientation"], "mixed")


class T12_ClosedShapeHandling(unittest.TestCase):
    """Rectangles are treated as closed shapes; can still be candidates
    via perimeter length, but with confidence kind closed_shape_group."""
    def test_rect_path_classified_as_closed(self):
        raw = _build_raw(vector_paths=[
            _raw_path("h_rect", stroke="#ff0000", bbox=(0, 0, 50, 30),
                      items=[["re", [0.0, 0.0, 50.0, 30.0], 0]]),
        ])
        classified = _classify_via_e2a(raw)
        out = PER.group_route_candidates(classified, raw_record=raw)
        # Perimeter = 2 * (50 + 30) = 160 > 20 → passes min_length.
        self.assertEqual(len(out["route_candidates"]), 1)
        c = out["route_candidates"][0]
        self.assertEqual(c["confidence"]["kind"], "closed_shape_group")
        self.assertEqual(c["confidence"]["free_endpoint_count"], 0)


# ===========================================================================
# ENDPOINT TESTS
# ===========================================================================

def _make_palette_pdf(target: Path) -> None:
    """One-page PDF with two clearly disconnected red lines."""
    import fitz
    doc = fitz.open()
    try:
        page = doc.new_page(width=612, height=792)
        shape = page.new_shape()
        # Red horizontal line, far apart from the next so they don't merge.
        shape.draw_line(fitz.Point(72, 100), fitz.Point(540, 100))
        shape.finish(color=(1, 0, 0), width=1.5)
        # Another red horizontal line, separated by 200pt vertically.
        shape.draw_line(fitz.Point(72, 300), fitz.Point(540, 300))
        shape.finish(color=(1, 0, 0), width=1.5)
        # Blue line (different bucket — should be ignored when bucket=proposed_red).
        shape.draw_line(fitz.Point(72, 500), fitz.Point(540, 500))
        shape.finish(color=(0, 0, 1), width=1.5)
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
    SESSION_ID = "sess_test_routes"
    PLAN_ID = "abc123routes"

    def setUp(self) -> None:
        self._saved = {f: os.environ.pop(f, None) for f in
                       (_OVERLAY_FLAG, _RAW_FLAG, _CLASSIFY_FLAG, _ROUTES_FLAG)}
        self._tmp_root = Path(tempfile.mkdtemp(prefix="pdf_ext_routes_"))
        self._eng_root = self._tmp_root / "uploads" / "engineering_plans"
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
            try: p.stop()
            except RuntimeError: pass
        for name, saved in self._saved.items():
            if saved is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = saved
        for p in sorted(self._tmp_root.rglob("*"), reverse=True):
            try:
                if p.is_file(): p.unlink()
                else: p.rmdir()
            except OSError:
                pass
        try: self._tmp_root.rmdir()
        except OSError: pass

    def _build_pdf(self, target: Path) -> None:
        raise NotImplementedError

    def _enable_all_flags(self) -> None:
        for f in (_OVERLAY_FLAG, _RAW_FLAG, _CLASSIFY_FLAG, _ROUTES_FLAG):
            os.environ[f] = "1"

    def _call(self, **kwargs: Any) -> Any:
        defaults: Dict[str, Any] = {
            "plan_id": self.PLAN_ID,
            "page_index": 0,
            "session_id": self.SESSION_ID,
            "bucket": "proposed_red",
            "request": None,
        }
        defaults.update(kwargs)
        return asyncio.run(M.get_engineering_plan_extraction_route_candidates(**defaults))


# ---------------------------------------------------------------------------
# T13 — flag gating returns 404 when ANY of the 4 flags is off
# ---------------------------------------------------------------------------

class T13_FlagGating(_BaseEndpointTest):
    def _build_pdf(self, target: Path) -> None:
        _make_palette_pdf(target)

    def test_all_flags_off_returns_404(self) -> None:
        for f in (_OVERLAY_FLAG, _RAW_FLAG, _CLASSIFY_FLAG, _ROUTES_FLAG):
            os.environ.pop(f, None)
        self.assertEqual(self._call().status_code, 404)

    def test_routes_flag_off_returns_404(self) -> None:
        os.environ[_OVERLAY_FLAG] = "1"
        os.environ[_RAW_FLAG] = "1"
        os.environ[_CLASSIFY_FLAG] = "1"
        os.environ.pop(_ROUTES_FLAG, None)
        self.assertEqual(self._call().status_code, 404)

    def test_classify_flag_off_returns_404(self) -> None:
        os.environ[_OVERLAY_FLAG] = "1"
        os.environ[_RAW_FLAG] = "1"
        os.environ.pop(_CLASSIFY_FLAG, None)
        os.environ[_ROUTES_FLAG] = "1"
        self.assertEqual(self._call().status_code, 404)


# ---------------------------------------------------------------------------
# T14 — invalid inputs (plan_id, page_index, bucket)
# ---------------------------------------------------------------------------

class T14_InvalidInputs(_BaseEndpointTest):
    def _build_pdf(self, target: Path) -> None:
        _make_palette_pdf(target)

    def setUp(self) -> None:
        super().setUp()
        self._enable_all_flags()

    def test_empty_plan_id_returns_400(self) -> None:
        self.assertEqual(self._call(plan_id="").status_code, 400)

    def test_unknown_plan_id_returns_404(self) -> None:
        self.assertEqual(self._call(plan_id="nope").status_code, 404)

    def test_missing_page_index_returns_400(self) -> None:
        self.assertEqual(self._call(page_index=None).status_code, 400)

    def test_invalid_bucket_returns_400(self) -> None:
        self.assertEqual(self._call(bucket="bogus_bucket").status_code, 400)

    def test_out_of_range_page_returns_404(self) -> None:
        self.assertEqual(self._call(page_index=99).status_code, 404)


# ---------------------------------------------------------------------------
# T15 — happy path with palette PDF: two red lines → two candidates
# ---------------------------------------------------------------------------

class T15_HappyPath(_BaseEndpointTest):
    def _build_pdf(self, target: Path) -> None:
        _make_palette_pdf(target)

    def setUp(self) -> None:
        super().setUp()
        self._enable_all_flags()

    def test_palette_pdf_two_red_candidates(self) -> None:
        r = self._call()
        self.assertEqual(r.status_code, 200)
        body = _read_body(r)
        self.assertTrue(body.get("success"))
        self.assertEqual(body.get("schema_version"), "pdf-extraction-routes-1")
        self.assertEqual(body.get("source_schema_version"), "pdf-extraction-classified-1")
        self.assertEqual(body.get("bucket"), "proposed_red")
        self.assertEqual(body.get("cache"), "miss")
        # PyMuPDF's exact emission shape for draw_line + finish varies
        # (sometimes a single "l" op stroked path, sometimes a filled
        # rect for the stroke outline).  The invariants we DO want to
        # check: at least 2 distinct candidates exist (the two red
        # lines were drawn far apart vertically so they cannot merge),
        # all carry source items_hashes for provenance, all pass the
        # min_length filter.
        candidates = body.get("route_candidates") or []
        self.assertGreaterEqual(len(candidates), 2)
        for c in candidates:
            self.assertGreaterEqual(c["total_length_pt"], 20.0)
            self.assertGreater(len(c["source_items_hashes"]), 0)
            self.assertIn(
                c["confidence"]["kind"],
                {"single_path", "multi_path_connected", "closed_shape_group"},
            )
        # Cache file written for proposed_red.
        cache_file = (
            self._sess_folder
            / "extraction"
            / f"{self.PLAN_ID}_p000_pdf-extraction-routes-1_b-proposed_red.json"
        )
        self.assertTrue(cache_file.is_file())


# ---------------------------------------------------------------------------
# T16 — cache miss → hit
# ---------------------------------------------------------------------------

class T16_Cache(_BaseEndpointTest):
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
        # Routes cache file written.
        cache_file = (
            self._sess_folder
            / "extraction"
            / f"{self.PLAN_ID}_p000_pdf-extraction-routes-1_b-proposed_red.json"
        )
        self.assertTrue(cache_file.is_file())
        r2 = self._call()
        self.assertEqual(r2.status_code, 200)
        b2 = _read_body(r2)
        self.assertEqual(b2.get("cache"), "hit")
        self.assertEqual(b1.get("route_candidates"), b2.get("route_candidates"))

    def test_different_bucket_has_separate_cache(self) -> None:
        # Hit proposed_red first.
        self._call(bucket="proposed_red")
        # Hit existing_blue — must NOT serve proposed_red's cached result.
        r = self._call(bucket="existing_blue")
        self.assertEqual(r.status_code, 200)
        b = _read_body(r)
        self.assertEqual(b.get("bucket"), "existing_blue")
        # And a different cache file exists.
        blue_cache = (
            self._sess_folder
            / "extraction"
            / f"{self.PLAN_ID}_p000_pdf-extraction-routes-1_b-existing_blue.json"
        )
        self.assertTrue(blue_cache.is_file())


# ---------------------------------------------------------------------------
# T17 — ownership delegation (require_tenant_owns_session is invoked)
# ---------------------------------------------------------------------------

class T17_OwnershipDelegation(_BaseEndpointTest):
    def _build_pdf(self, target: Path) -> None:
        _make_palette_pdf(target)

    def setUp(self) -> None:
        super().setUp()
        self._enable_all_flags()

    def test_require_tenant_owns_session_called(self) -> None:
        with patch.object(M, "_require_tenant_owns_session", return_value=None) as spy:
            r = self._call()
            self.assertEqual(r.status_code, 200)
            self.assertEqual(spy.call_count, 1)
            args, _ = spy.call_args
            self.assertEqual(args[0], self.SESSION_ID)


if __name__ == "__main__":
    unittest.main()
