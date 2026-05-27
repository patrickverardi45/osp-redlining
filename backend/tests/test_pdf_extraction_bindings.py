"""PDF Extraction E2c — label-to-route binder + endpoint tests.

Targets ``bind_labels_to_routes`` in app/core/pdf_extraction_bindings.py
and ``get_engineering_plan_extraction_bindings`` in backend/main.py.
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

os.environ.setdefault("TRUELINE_JWT_SECRET", "pdf-ext-bindings-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "pdf-ext-bindings-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend import main as M  # noqa: E402
from backend.app.core import pdf_extraction_bindings as PEB  # noqa: E402
from backend.app.core import pdf_extraction_classify as PEC  # noqa: E402
from backend.app.core import pdf_extraction_routes as PER  # noqa: E402

_OVERLAY_FLAG = "TRUELINE_PLAN_OVERLAY_IMAGE"
_RAW_FLAG = "TRUELINE_PDF_EXTRACTION_RAW_ENABLED"
_CLASSIFY_FLAG = "TRUELINE_PDF_EXTRACTION_CLASSIFY_ENABLED"
_ROUTES_FLAG = "TRUELINE_PDF_EXTRACTION_ROUTES_ENABLED"
_BINDINGS_FLAG = "TRUELINE_PDF_EXTRACTION_BINDINGS_ENABLED"


# ---------------------------------------------------------------------------
# Synthetic E1 record builders
# ---------------------------------------------------------------------------

def _text_block(text: str, bbox=(100.0, 100.0, 200.0, 112.0), block_no: int = 0) -> Dict[str, Any]:
    return {
        "text":       text,
        "bbox":       list(bbox),
        "font":       "ArialMT",
        "size":       10.0,
        "color":      "#000000",
        "block_no":   block_no,
    }


def _raw_path(items_hash: str, stroke: str = "#ff0000",
              items: List[Any] = None, bbox=(0.0, 0.0, 100.0, 0.5)) -> Dict[str, Any]:
    return {
        "items":        items or [],
        "stroke_color": stroke,
        "stroke_width": 1.0,
        "fill_color":   None,
        "rule":         "stroke",
        "bbox":         list(bbox),
        "items_hash":   items_hash,
    }


def _build_raw(text_blocks=None, vector_paths=None,
               page_size=(612.0, 792.0)) -> Dict[str, Any]:
    return {
        "schema_version": "pdf-extraction-raw-1",
        "page_index": 0,
        "page_number": 1,
        "page_size_px": list(page_size),
        "page_rotation": 0,
        "text_blocks": text_blocks or [],
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


def _routes_for(raw: Dict[str, Any], bucket: str = "proposed_red") -> Dict[str, Any]:
    """Run the real E2a + E2b on the raw record so the input shape is
    byte-aligned with what the production endpoint feeds to E2c."""
    classified = PEC.classify_vector_paths(raw)
    return PER.group_route_candidates(classified, raw_record=raw, bucket=bucket)


# ===========================================================================
# PURE HELPER TESTS
# ===========================================================================

class T1_EmptyInputs(unittest.TestCase):
    def test_no_routes_no_text(self):
        raw = _build_raw()
        routes = _routes_for(raw)
        out = PEB.bind_labels_to_routes(raw, routes)
        self.assertEqual(out["schema_version"], "pdf-extraction-bindings-1")
        self.assertEqual(out["station_anchors"], [])
        self.assertEqual(out["matchline_records"], [])
        self.assertEqual(out["construction_labels"], [])
        self.assertEqual(out["unbound_text"], [])
        self.assertEqual(out["meta"]["input_text_block_count"], 0)
        self.assertEqual(out["meta"]["input_route_candidate_count"], 0)

    def test_text_but_no_routes_yields_unbound(self):
        raw = _build_raw(text_blocks=[
            _text_block("STA 11+60", bbox=(100, 100, 150, 112)),
        ])
        routes = _routes_for(raw)
        out = PEB.bind_labels_to_routes(raw, routes)
        # No candidates → station goes to unbound.
        self.assertEqual(out["station_anchors"], [])
        self.assertEqual(len(out["unbound_text"]), 1)
        u = out["unbound_text"][0]
        self.assertEqual(u["matched_text"], "11+60")
        self.assertEqual(u["rule_id"], "station_regex_v1")
        self.assertIsNone(u["route_candidate_id"])


class T2_StationRegex(unittest.TestCase):
    def test_station_bound_to_nearest_route(self):
        # Route at y=100 horizontal: from x=50 to x=250
        # Station text at (150, 110) — near the route
        raw = _build_raw(
            text_blocks=[
                _text_block("STA 11+60", bbox=(140, 105, 160, 117)),
            ],
            vector_paths=[
                _raw_path("h_route", stroke="#ff0000",
                          bbox=(50, 99, 250, 101),
                          items=[["l", [50.0, 100.0], [250.0, 100.0]]]),
            ],
        )
        routes = _routes_for(raw)
        out = PEB.bind_labels_to_routes(raw, routes)
        self.assertEqual(len(out["station_anchors"]), 1)
        sa = out["station_anchors"][0]
        self.assertEqual(sa["matched_text"], "11+60")
        self.assertIsNotNone(sa["route_candidate_id"])
        self.assertLess(sa["distance_pt"], 20.0)
        self.assertEqual(sa["confidence"]["kind"], "bound")

    def test_multiple_stations_in_one_block(self):
        raw = _build_raw(
            text_blocks=[
                _text_block("11+60 to 14+20", bbox=(140, 105, 200, 117)),
            ],
            vector_paths=[
                _raw_path("h_route", stroke="#ff0000",
                          bbox=(50, 99, 250, 101),
                          items=[["l", [50.0, 100.0], [250.0, 100.0]]]),
            ],
        )
        out = PEB.bind_labels_to_routes(raw, _routes_for(raw))
        # Two distinct station strings → two anchor records.
        self.assertEqual(len(out["station_anchors"]), 2)
        matched = sorted(sa["matched_text"] for sa in out["station_anchors"])
        self.assertEqual(matched, ["11+60", "14+20"])


class T3_MatchlineExtraction(unittest.TestCase):
    def test_matchline_with_sheet_ref_extracted(self):
        raw = _build_raw(
            text_blocks=[
                _text_block("MATCH LINE STA 27+80 - SEE SHEET 6",
                            bbox=(50, 50, 350, 62)),
            ],
            vector_paths=[
                _raw_path("h_route", stroke="#ff0000",
                          bbox=(50, 60, 350, 62),
                          items=[["l", [50.0, 61.0], [350.0, 61.0]]]),
            ],
        )
        out = PEB.bind_labels_to_routes(raw, _routes_for(raw))
        self.assertEqual(len(out["matchline_records"]), 1)
        ml = out["matchline_records"][0]
        self.assertEqual(ml["references_sheet"], 6)
        self.assertEqual(ml["station"], "27+80")
        self.assertEqual(ml["rule_id"], "matchline_regex_v1")
        self.assertIsNotNone(ml["route_candidate_id"])

    def test_matchline_without_sheet_ref(self):
        raw = _build_raw(
            text_blocks=[
                _text_block("MATCHLINE", bbox=(50, 50, 150, 62)),
            ],
            vector_paths=[
                _raw_path("h_route", stroke="#ff0000",
                          bbox=(50, 60, 350, 62),
                          items=[["l", [50.0, 61.0], [350.0, 61.0]]]),
            ],
        )
        out = PEB.bind_labels_to_routes(raw, _routes_for(raw))
        self.assertEqual(len(out["matchline_records"]), 1)
        ml = out["matchline_records"][0]
        self.assertIsNone(ml["references_sheet"])
        self.assertIsNone(ml["station"])


class T4_ConstructionKeywords(unittest.TestCase):
    def test_each_keyword_detected(self):
        # All labels within max_bind_distance_pt (75pt) of the route at y=100.
        raw = _build_raw(
            text_blocks=[
                _text_block("PROPOSED BORE", bbox=(140, 102, 200, 114)),
                _text_block("EXISTING HANDHOLE", bbox=(140, 118, 220, 130)),
                _text_block("UNDERGROUND CONDUIT", bbox=(140, 134, 240, 146)),
                _text_block("HDPE FIBER CABLE", bbox=(140, 150, 240, 162)),
                _text_block("UTILITY POTHOLE", bbox=(140, 166, 220, 178)),
            ],
            vector_paths=[
                _raw_path("h_route", stroke="#ff0000",
                          bbox=(50, 99, 250, 101),
                          items=[["l", [50.0, 100.0], [250.0, 100.0]]]),
            ],
        )
        out = PEB.bind_labels_to_routes(raw, _routes_for(raw))
        keywords = sorted({c["keyword"] for c in out["construction_labels"]})
        # All 9 keywords appear across these 5 text blocks.
        self.assertEqual(set(keywords), {
            "PROPOSED", "BORE", "EXISTING", "HANDHOLE",
            "UNDERGROUND", "CONDUIT", "HDPE", "FIBER", "POTHOLE",
        })
        # Each labeled record has provenance.
        for c in out["construction_labels"]:
            self.assertIn("rule_id", c)
            self.assertTrue(c["rule_id"].startswith("construction_keyword_v1:"))
            self.assertIn("raw_text", c)
            self.assertIn("anchor_point", c)

    def test_keyword_word_boundary(self):
        # "BORERS" should NOT match BORE (word-boundary regex).
        raw = _build_raw(
            text_blocks=[
                _text_block("WATERBORERS QTY 5", bbox=(140, 105, 200, 117)),
            ],
            vector_paths=[
                _raw_path("h_route", stroke="#ff0000",
                          bbox=(50, 99, 250, 101),
                          items=[["l", [50.0, 100.0], [250.0, 100.0]]]),
            ],
        )
        out = PEB.bind_labels_to_routes(raw, _routes_for(raw))
        # No BORE construction match should appear.
        kws = {c["keyword"] for c in out["construction_labels"]}
        self.assertNotIn("BORE", kws)


class T5_NearestRouteBinding(unittest.TestCase):
    def test_picks_closer_of_two_routes(self):
        # Two parallel routes, label closer to upper one.
        raw = _build_raw(
            text_blocks=[
                _text_block("STA 11+60", bbox=(140, 102, 160, 112)),  # near upper
            ],
            vector_paths=[
                _raw_path("h_upper", stroke="#ff0000",
                          bbox=(50, 99, 250, 101),
                          items=[["l", [50.0, 100.0], [250.0, 100.0]]]),
                _raw_path("h_lower", stroke="#ff0000",
                          bbox=(50, 199, 250, 201),
                          items=[["l", [50.0, 200.0], [250.0, 200.0]]]),
            ],
        )
        routes = _routes_for(raw)
        out = PEB.bind_labels_to_routes(raw, routes)
        # Should bind to upper route.
        self.assertEqual(len(out["station_anchors"]), 1)
        sa = out["station_anchors"][0]
        bound_id = sa["route_candidate_id"]
        # Find the candidate id for the upper route (the smaller y0).
        upper_id = min(routes["route_candidates"], key=lambda c: c["bbox"][1])["candidate_id"]
        self.assertEqual(bound_id, upper_id)


class T6_UnboundWhenFar(unittest.TestCase):
    def test_far_label_goes_unbound(self):
        # Station label is 500pt away from the only route.
        raw = _build_raw(
            text_blocks=[
                _text_block("STA 99+00", bbox=(50, 700, 100, 712)),
            ],
            vector_paths=[
                _raw_path("h_route", stroke="#ff0000",
                          bbox=(50, 100, 250, 102),
                          items=[["l", [50.0, 101.0], [250.0, 101.0]]]),
            ],
        )
        out = PEB.bind_labels_to_routes(raw, _routes_for(raw), max_bind_distance_pt=75.0)
        self.assertEqual(len(out["station_anchors"]), 0)
        self.assertEqual(len(out["unbound_text"]), 1)
        u = out["unbound_text"][0]
        self.assertEqual(u["matched_text"], "99+00")
        self.assertIsNone(u["route_candidate_id"])
        self.assertEqual(u["confidence"]["kind"], "unbound")


class T7_DeterministicOrdering(unittest.TestCase):
    def test_byte_identical_twice(self):
        raw = _build_raw(
            text_blocks=[
                _text_block("STA 11+60", bbox=(140, 102, 160, 112), block_no=0),
                _text_block("STA 14+20", bbox=(140, 152, 160, 162), block_no=1),
                _text_block("MATCH LINE STA 27+80 - SEE SHEET 6",
                            bbox=(50, 50, 350, 62), block_no=2),
            ],
            vector_paths=[
                _raw_path("h_a", stroke="#ff0000",
                          bbox=(50, 99, 250, 165),
                          items=[
                              ["l", [50.0, 100.0], [250.0, 100.0]],
                              ["l", [250.0, 100.0], [250.0, 160.0]],
                          ]),
            ],
        )
        routes = _routes_for(raw)
        o1 = PEB.bind_labels_to_routes(raw, routes)
        o2 = PEB.bind_labels_to_routes(raw, routes)
        self.assertEqual(json.dumps(o1, sort_keys=True), json.dumps(o2, sort_keys=True))


class T8_ProvenancePreserved(unittest.TestCase):
    def test_provenance_fields_present(self):
        raw = _build_raw(
            text_blocks=[
                _text_block("STA 11+60 BORE", bbox=(140, 105, 220, 117), block_no=7),
            ],
            vector_paths=[
                _raw_path("h_route", stroke="#ff0000",
                          bbox=(50, 99, 250, 101),
                          items=[["l", [50.0, 100.0], [250.0, 100.0]]]),
            ],
        )
        out = PEB.bind_labels_to_routes(raw, _routes_for(raw))
        # Station anchor provenance.
        self.assertEqual(len(out["station_anchors"]), 1)
        sa = out["station_anchors"][0]
        self.assertEqual(sa["raw_text"], "STA 11+60 BORE")
        self.assertEqual(sa["text_bbox"], [140.0, 105.0, 220.0, 117.0])
        self.assertEqual(sa["block_no"], 7)
        self.assertEqual(sa["rule_id"], "station_regex_v1")
        # Construction label provenance.
        self.assertEqual(len(out["construction_labels"]), 1)
        cl = out["construction_labels"][0]
        self.assertEqual(cl["raw_text"], "STA 11+60 BORE")
        self.assertEqual(cl["keyword"], "BORE")
        self.assertEqual(cl["rule_id"], "construction_keyword_v1:BORE")


class T9_MalformedDataSafe(unittest.TestCase):
    def test_bad_route_record_no_crash(self):
        raw = _build_raw(text_blocks=[
            _text_block("STA 11+60", bbox=(100, 100, 150, 112)),
        ])
        # Route record with a non-dict candidate entry.
        bad_routes = {
            "schema_version": "pdf-extraction-routes-1",
            "source_schema_version": "pdf-extraction-classified-1",
            "raw_schema_version": "pdf-extraction-raw-1",
            "page_index": 0,
            "bucket": "proposed_red",
            "route_candidates": [
                "not a dict",
                {"candidate_id": "rc_0", "bbox": "not a bbox", "source_items_hashes": ["x"]},
                {"candidate_id": "rc_1", "bbox": [50, 99, 250, 101],
                 "source_items_hashes": ["h_route"]},
            ],
        }
        raw["vector_paths"] = [
            _raw_path("h_route", stroke="#ff0000", bbox=(50, 99, 250, 101),
                      items=[["l", [50.0, 100.0], [250.0, 100.0]]]),
        ]
        # Should not raise.
        out = PEB.bind_labels_to_routes(raw, bad_routes)
        # rc_1 is the only valid candidate.  Should bind to it.
        self.assertEqual(len(out["station_anchors"]), 1)
        self.assertEqual(out["station_anchors"][0]["route_candidate_id"], "rc_1")

    def test_bad_text_block_skipped(self):
        raw = _build_raw(text_blocks=[
            "not a dict",
            {"text": "STA 11+60", "bbox": "not a bbox"},
            _text_block("STA 14+20", bbox=(100, 100, 150, 112)),
        ])
        raw["vector_paths"] = [
            _raw_path("h_route", stroke="#ff0000", bbox=(50, 99, 250, 101),
                      items=[["l", [50.0, 100.0], [250.0, 100.0]]]),
        ]
        out = PEB.bind_labels_to_routes(raw, _routes_for(raw))
        # Only 14+20 should be detected.
        self.assertEqual(len(out["station_anchors"]), 1)
        self.assertEqual(out["station_anchors"][0]["matched_text"], "14+20")


class T10_SchemaValidation(unittest.TestCase):
    def test_non_dict_raw_raises(self):
        with self.assertRaises(PEB.PdfExtractionBindingsError):
            PEB.bind_labels_to_routes("nope", {"schema_version": "pdf-extraction-routes-1"})  # type: ignore

    def test_wrong_raw_schema_raises(self):
        bad = _build_raw()
        bad["schema_version"] = "wrong"
        with self.assertRaises(PEB.PdfExtractionBindingsError):
            PEB.bind_labels_to_routes(bad, _routes_for(_build_raw()))

    def test_wrong_routes_schema_raises(self):
        raw = _build_raw()
        with self.assertRaises(PEB.PdfExtractionBindingsError):
            PEB.bind_labels_to_routes(raw, {"schema_version": "wrong"})


# ===========================================================================
# ENDPOINT TESTS
# ===========================================================================

def _make_text_route_pdf(target: Path) -> None:
    """One-page PDF with text labels + a red horizontal line."""
    import fitz
    doc = fitz.open()
    try:
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 80), "STA 11+60", fontsize=10)
        page.insert_text((72, 105), "MATCH LINE STA 27+80 - SEE SHEET 6", fontsize=10)
        page.insert_text((72, 130), "PROPOSED BORE", fontsize=10)
        shape = page.new_shape()
        shape.draw_line(fitz.Point(72, 90), fitz.Point(540, 90))
        shape.finish(color=(1, 0, 0), width=1.5)
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
    SESSION_ID = "sess_test_bindings"
    PLAN_ID = "abc123bindings"

    def setUp(self) -> None:
        self._saved = {f: os.environ.pop(f, None) for f in
                       (_OVERLAY_FLAG, _RAW_FLAG, _CLASSIFY_FLAG,
                        _ROUTES_FLAG, _BINDINGS_FLAG)}
        self._tmp_root = Path(tempfile.mkdtemp(prefix="pdf_ext_bindings_"))
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
        for f in (_OVERLAY_FLAG, _RAW_FLAG, _CLASSIFY_FLAG,
                  _ROUTES_FLAG, _BINDINGS_FLAG):
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
        return asyncio.run(M.get_engineering_plan_extraction_bindings(**defaults))


class T11_FlagGating(_BaseEndpointTest):
    def _build_pdf(self, target: Path) -> None:
        _make_text_route_pdf(target)

    def test_all_flags_off_returns_404(self) -> None:
        for f in (_OVERLAY_FLAG, _RAW_FLAG, _CLASSIFY_FLAG, _ROUTES_FLAG, _BINDINGS_FLAG):
            os.environ.pop(f, None)
        self.assertEqual(self._call().status_code, 404)

    def test_bindings_flag_off_returns_404(self) -> None:
        for f in (_OVERLAY_FLAG, _RAW_FLAG, _CLASSIFY_FLAG, _ROUTES_FLAG):
            os.environ[f] = "1"
        os.environ.pop(_BINDINGS_FLAG, None)
        self.assertEqual(self._call().status_code, 404)

    def test_routes_flag_off_returns_404(self) -> None:
        for f in (_OVERLAY_FLAG, _RAW_FLAG, _CLASSIFY_FLAG, _BINDINGS_FLAG):
            os.environ[f] = "1"
        os.environ.pop(_ROUTES_FLAG, None)
        self.assertEqual(self._call().status_code, 404)


class T12_InvalidInputs(_BaseEndpointTest):
    def _build_pdf(self, target: Path) -> None:
        _make_text_route_pdf(target)

    def setUp(self) -> None:
        super().setUp()
        self._enable_all_flags()

    def test_missing_page_index_returns_400(self) -> None:
        self.assertEqual(self._call(page_index=None).status_code, 400)

    def test_invalid_bucket_returns_400(self) -> None:
        self.assertEqual(self._call(bucket="nope").status_code, 400)

    def test_unknown_plan_id_returns_404(self) -> None:
        self.assertEqual(self._call(plan_id="missing").status_code, 404)

    def test_negative_page_index_returns_400(self) -> None:
        self.assertEqual(self._call(page_index=-1).status_code, 400)

    def test_out_of_range_page_returns_404(self) -> None:
        self.assertEqual(self._call(page_index=99).status_code, 404)


class T13_HappyPath(_BaseEndpointTest):
    def _build_pdf(self, target: Path) -> None:
        _make_text_route_pdf(target)

    def setUp(self) -> None:
        super().setUp()
        self._enable_all_flags()

    def test_endpoint_returns_bindings(self) -> None:
        r = self._call()
        self.assertEqual(r.status_code, 200)
        body = _read_body(r)
        self.assertTrue(body.get("success"))
        self.assertEqual(body.get("schema_version"), "pdf-extraction-bindings-1")
        self.assertEqual(body.get("bucket"), "proposed_red")
        self.assertEqual(body.get("cache"), "miss")
        # PDF has STA 11+60 + MATCH LINE STA 27+80 SEE SHEET 6 + PROPOSED BORE.
        # We expect at least one station and at least one construction label.
        meta = body.get("meta") or {}
        self.assertGreaterEqual(
            meta.get("station_anchor_count", 0) + len(body.get("unbound_text") or []),
            1,
        )
        self.assertGreaterEqual(meta.get("construction_label_count", 0), 1)


class T14_Cache(_BaseEndpointTest):
    def _build_pdf(self, target: Path) -> None:
        _make_text_route_pdf(target)

    def setUp(self) -> None:
        super().setUp()
        self._enable_all_flags()

    def test_first_miss_second_hit(self) -> None:
        r1 = self._call()
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(_read_body(r1).get("cache"), "miss")
        cache_file = (
            self._sess_folder / "extraction"
            / f"{self.PLAN_ID}_p000_pdf-extraction-bindings-1_b-proposed_red.json"
        )
        self.assertTrue(cache_file.is_file())
        r2 = self._call()
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(_read_body(r2).get("cache"), "hit")


class T15_OwnershipDelegation(_BaseEndpointTest):
    def _build_pdf(self, target: Path) -> None:
        _make_text_route_pdf(target)

    def setUp(self) -> None:
        super().setUp()
        self._enable_all_flags()

    def test_require_tenant_owns_session_invoked(self) -> None:
        with patch.object(M, "_require_tenant_owns_session", return_value=None) as spy:
            r = self._call()
            self.assertEqual(r.status_code, 200)
            self.assertEqual(spy.call_count, 1)
            args, _ = spy.call_args
            self.assertEqual(args[0], self.SESSION_ID)


if __name__ == "__main__":
    unittest.main()
