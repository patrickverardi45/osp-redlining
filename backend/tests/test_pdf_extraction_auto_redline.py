"""PDF Extraction E3 — auto-redline generator + endpoint tests."""

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

os.environ.setdefault("TRUELINE_JWT_SECRET", "pdf-auto-redline-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "pdf-auto-redline-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend import main as M  # noqa: E402
from backend.app.core import pdf_extraction_auto_redline as PEAR  # noqa: E402
from backend.app.core import pdf_extraction_bindings as PEB  # noqa: E402
from backend.app.core import pdf_extraction_classify as PEC  # noqa: E402
from backend.app.core import pdf_extraction_routes as PER  # noqa: E402

_OVERLAY_FLAG = "TRUELINE_PLAN_OVERLAY_IMAGE"
_RAW_FLAG = "TRUELINE_PDF_EXTRACTION_RAW_ENABLED"
_CLASSIFY_FLAG = "TRUELINE_PDF_EXTRACTION_CLASSIFY_ENABLED"
_ROUTES_FLAG = "TRUELINE_PDF_EXTRACTION_ROUTES_ENABLED"
_BINDINGS_FLAG = "TRUELINE_PDF_EXTRACTION_BINDINGS_ENABLED"
_AUTOREDLINE_FLAG = "TRUELINE_PDF_AUTO_REDLINE_ENABLED"
_ALL_FLAGS = (_OVERLAY_FLAG, _RAW_FLAG, _CLASSIFY_FLAG, _ROUTES_FLAG,
              _BINDINGS_FLAG, _AUTOREDLINE_FLAG)


# ---------------------------------------------------------------------------
# Synthetic record builders
# ---------------------------------------------------------------------------

def _text_block(text: str, bbox=(100.0, 100.0, 200.0, 112.0),
                block_no: int = 0) -> Dict[str, Any]:
    return {
        "text":     text,
        "bbox":     list(bbox),
        "font":     "ArialMT",
        "size":     10.0,
        "color":    "#000000",
        "block_no": block_no,
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
            "text_blocks_cap": 5000, "vector_paths_cap": 10000,
            "block_text_cap": 4000, "path_points_cap": 2000,
        },
        "page_load_error": None,
    }


def _build_route_corpus(
    *,
    n_anchors: int = 4,
    bucket: str = "proposed_red",
) -> Dict[str, Any]:
    """Return {raw, classified, routes, bindings} for a single
    horizontal red route with N station anchors along it."""
    # Long red horizontal line at y=100 from x=50 to x=1000
    raw_vector_paths = [
        _raw_path("h_route", stroke="#ff0000",
                  bbox=(50.0, 99.0, 1000.0, 101.0),
                  items=[["l", [50.0, 100.0], [1000.0, 100.0]]]),
    ]
    # N station anchors evenly distributed.  Station "X+YY" maps to ft
    # value 100*X+YY; we place anchors so the labels read as nice
    # round station values (e.g. 10+00, 11+00, ..., 13+00).
    anchor_blocks = []
    for i in range(n_anchors):
        # x-coordinate spread along the route
        x = 100.0 + i * 200.0
        station_label = f"{10 + i}+00"  # 10+00, 11+00, ...
        anchor_blocks.append(
            _text_block(f"STA {station_label}",
                        bbox=(x - 20, 102, x + 20, 114), block_no=i + 1),
        )
    raw = _build_raw(text_blocks=anchor_blocks, vector_paths=raw_vector_paths)
    classified = PEC.classify_vector_paths(raw)
    routes = PER.group_route_candidates(classified, raw_record=raw, bucket=bucket)
    bindings = PEB.bind_labels_to_routes(raw, routes, classified_record=classified)
    return {
        "raw": raw, "classified": classified,
        "routes": routes, "bindings": bindings,
    }


# ===========================================================================
# PURE HELPER TESTS
# ===========================================================================

class T1_ValidStationRange(unittest.TestCase):
    """A row with valid start+end inside the route range creates one
    auto_extracted segment record."""
    def test_creates_segment(self):
        corp = _build_route_corpus(n_anchors=4)
        rc_id = corp["routes"]["route_candidates"][0]["candidate_id"]
        out = PEAR.generate_auto_redline_segments(
            corp["raw"], corp["routes"], corp["bindings"],
            {"route_candidate_id": rc_id,
             "rows": [{"start_station": "11+00", "end_station": "12+50"}]},
        )
        self.assertEqual(out["schema_version"], "pdf-auto-redline-1")
        self.assertEqual(out["route_candidate_id"], rc_id)
        self.assertEqual(len(out["generated_segments"]), 1)
        seg = out["generated_segments"][0]
        self.assertEqual(seg["source"], "auto_extracted")
        self.assertEqual(seg["start_station_ft"], 1100.0)
        self.assertEqual(seg["end_station_ft"], 1250.0)
        self.assertEqual(seg["length_ft"], 150.0)
        self.assertEqual(seg["route_candidate_id"], rc_id)
        self.assertTrue(seg["segment_id"].startswith("ar_"))
        # Matched anchors: 11+00 and 12+00 both fall in [11+00, 12+50]
        # (inclusive endpoints) → 2 matched.
        self.assertEqual(seg["matched_anchor_count"], 2)
        # Confidence: >= 2 anchors → high.
        self.assertEqual(seg["confidence"]["kind"], "high")


class T2_MissingRouteCandidateRejects(unittest.TestCase):
    def test_unknown_id_raises(self):
        corp = _build_route_corpus()
        with self.assertRaises(PEAR.PdfAutoRedlineError):
            PEAR.generate_auto_redline_segments(
                corp["raw"], corp["routes"], corp["bindings"],
                {"route_candidate_id": "rc_nonexistent",
                 "rows": [{"start_station": "11+00", "end_station": "12+00"}]},
            )

    def test_missing_id_raises(self):
        corp = _build_route_corpus()
        with self.assertRaises(PEAR.PdfAutoRedlineError):
            PEAR.generate_auto_redline_segments(
                corp["raw"], corp["routes"], corp["bindings"],
                {"rows": [{"start_station": "11+00", "end_station": "12+00"}]},
            )


class T3_InvalidStationFormat(unittest.TestCase):
    def test_bad_start_station_rejected(self):
        corp = _build_route_corpus()
        rc_id = corp["routes"]["route_candidates"][0]["candidate_id"]
        out = PEAR.generate_auto_redline_segments(
            corp["raw"], corp["routes"], corp["bindings"],
            {"route_candidate_id": rc_id,
             "rows": [{"start_station": "BADSTA", "end_station": "12+00"}]},
        )
        self.assertEqual(out["generated_segments"], [])
        self.assertEqual(len(out["rejected_rows"]), 1)
        r = out["rejected_rows"][0]
        self.assertEqual(r["rule_id"], "auto_redline_v1:start_station_format")
        self.assertIn("BADSTA", r["reason"])

    def test_bad_end_station_rejected(self):
        corp = _build_route_corpus()
        rc_id = corp["routes"]["route_candidates"][0]["candidate_id"]
        out = PEAR.generate_auto_redline_segments(
            corp["raw"], corp["routes"], corp["bindings"],
            {"route_candidate_id": rc_id,
             "rows": [{"start_station": "11+00", "end_station": "NOPE"}]},
        )
        self.assertEqual(out["generated_segments"], [])
        self.assertEqual(len(out["rejected_rows"]), 1)
        self.assertEqual(out["rejected_rows"][0]["rule_id"],
                         "auto_redline_v1:end_station_format")

    def test_sta_prefix_accepted(self):
        corp = _build_route_corpus()
        rc_id = corp["routes"]["route_candidates"][0]["candidate_id"]
        out = PEAR.generate_auto_redline_segments(
            corp["raw"], corp["routes"], corp["bindings"],
            {"route_candidate_id": rc_id,
             "rows": [{"start_station": "STA 11+00", "end_station": "STA. 12+50"}]},
        )
        self.assertEqual(len(out["generated_segments"]), 1)
        self.assertEqual(out["generated_segments"][0]["start_station_ft"], 1100.0)
        self.assertEqual(out["generated_segments"][0]["end_station_ft"], 1250.0)


class T4_EndBeforeStart(unittest.TestCase):
    def test_end_le_start_rejected(self):
        corp = _build_route_corpus()
        rc_id = corp["routes"]["route_candidates"][0]["candidate_id"]
        out = PEAR.generate_auto_redline_segments(
            corp["raw"], corp["routes"], corp["bindings"],
            {"route_candidate_id": rc_id,
             "rows": [
                 {"start_station": "12+00", "end_station": "11+00"},   # reverse
                 {"start_station": "11+00", "end_station": "11+00"},   # equal
             ]},
        )
        self.assertEqual(out["generated_segments"], [])
        self.assertEqual(len(out["rejected_rows"]), 2)
        for r in out["rejected_rows"]:
            self.assertEqual(r["rule_id"], "auto_redline_v1:end_before_start")


class T5_DryRunNoPersistence(unittest.TestCase):
    """v1 NEVER persists, regardless of dry_run flag value."""
    def test_dry_run_true_no_persist(self):
        corp = _build_route_corpus()
        rc_id = corp["routes"]["route_candidates"][0]["candidate_id"]
        out = PEAR.generate_auto_redline_segments(
            corp["raw"], corp["routes"], corp["bindings"],
            {"route_candidate_id": rc_id,
             "rows": [{"start_station": "11+00", "end_station": "12+00"}],
             "dry_run": True},
        )
        self.assertTrue(out["meta"]["dry_run_intent"])
        self.assertFalse(out["meta"]["persisted"])
        self.assertFalse(out["meta"]["persistence_enabled_in_v1"])

    def test_dry_run_false_still_no_persist_in_v1(self):
        corp = _build_route_corpus()
        rc_id = corp["routes"]["route_candidates"][0]["candidate_id"]
        out = PEAR.generate_auto_redline_segments(
            corp["raw"], corp["routes"], corp["bindings"],
            {"route_candidate_id": rc_id,
             "rows": [{"start_station": "11+00", "end_station": "12+00"}],
             "dry_run": False},
        )
        # Operator intent recorded but v1 doesn't act on it.
        self.assertFalse(out["meta"]["dry_run_intent"])
        self.assertFalse(out["meta"]["persisted"])
        self.assertIn("v1 NEVER persists", out["meta"]["persistence_note"])


class T6_DeterministicOrdering(unittest.TestCase):
    def test_byte_identical_twice(self):
        corp = _build_route_corpus()
        rc_id = corp["routes"]["route_candidates"][0]["candidate_id"]
        payload = {
            "route_candidate_id": rc_id,
            "rows": [
                {"start_station": "12+50", "end_station": "13+00"},
                {"start_station": "10+00", "end_station": "10+50"},
                {"start_station": "11+00", "end_station": "11+50"},
            ],
        }
        o1 = PEAR.generate_auto_redline_segments(
            corp["raw"], corp["routes"], corp["bindings"], payload)
        o2 = PEAR.generate_auto_redline_segments(
            corp["raw"], corp["routes"], corp["bindings"], payload)
        self.assertEqual(json.dumps(o1, sort_keys=True),
                         json.dumps(o2, sort_keys=True))
        # Verify sort order by start_station_ft.
        starts = [s["start_station_ft"] for s in o1["generated_segments"]]
        self.assertEqual(starts, sorted(starts))
        # segment_ids assigned in sort order.
        ids = [s["segment_id"] for s in o1["generated_segments"]]
        self.assertEqual(ids, ["ar_0000", "ar_0001", "ar_0002"])


class T7_ProvenancePreserved(unittest.TestCase):
    def test_input_row_in_provenance(self):
        corp = _build_route_corpus()
        rc_id = corp["routes"]["route_candidates"][0]["candidate_id"]
        row = {"start_station": "11+00", "end_station": "12+00",
               "notes": "manual entry from rig"}
        out = PEAR.generate_auto_redline_segments(
            corp["raw"], corp["routes"], corp["bindings"],
            {"route_candidate_id": rc_id, "rows": [row]},
        )
        seg = out["generated_segments"][0]
        self.assertEqual(seg["provenance"]["input_row_index"], 0)
        self.assertEqual(seg["provenance"]["input_row"], row)
        self.assertEqual(seg["notes"], "manual entry from rig")
        self.assertEqual(seg["rule_id"], "auto_redline_v1")


class T8_WarningsForMissingAnchors(unittest.TestCase):
    """When no station anchors fall in the [start, end] range, the
    segment carries a 'no_station_anchors_in_range' warning."""
    def test_range_without_anchors(self):
        # Build corpus with anchors at 10+00, 11+00, 12+00, 13+00.
        # Request range 20+00 to 21+00 — no anchors in it.
        corp = _build_route_corpus(n_anchors=4)
        rc_id = corp["routes"]["route_candidates"][0]["candidate_id"]
        out = PEAR.generate_auto_redline_segments(
            corp["raw"], corp["routes"], corp["bindings"],
            {"route_candidate_id": rc_id,
             "rows": [{"start_station": "20+00", "end_station": "21+00"}]},
        )
        self.assertEqual(len(out["generated_segments"]), 1)
        seg = out["generated_segments"][0]
        self.assertEqual(seg["matched_anchor_count"], 0)
        self.assertIn("no_station_anchors_in_range", seg["confidence"]["warnings"])
        self.assertIn("range_outside_anchored_extent", seg["confidence"]["warnings"])
        # Confidence: 0 anchors + 100ft range → low (range >= 100).
        self.assertEqual(seg["confidence"]["kind"], "low")

    def test_short_range_without_anchors_is_medium(self):
        # 0 anchors but range < 100ft → medium confidence
        corp = _build_route_corpus(n_anchors=4)
        rc_id = corp["routes"]["route_candidates"][0]["candidate_id"]
        out = PEAR.generate_auto_redline_segments(
            corp["raw"], corp["routes"], corp["bindings"],
            {"route_candidate_id": rc_id,
             "rows": [{"start_station": "20+00", "end_station": "20+50"}]},
        )
        seg = out["generated_segments"][0]
        self.assertEqual(seg["matched_anchor_count"], 0)
        self.assertEqual(seg["confidence"]["kind"], "medium")  # range_ft=50 < 100


class T9_HighConfidenceWithMultipleAnchors(unittest.TestCase):
    def test_two_anchors_in_range_is_high(self):
        corp = _build_route_corpus(n_anchors=4)
        rc_id = corp["routes"]["route_candidates"][0]["candidate_id"]
        out = PEAR.generate_auto_redline_segments(
            corp["raw"], corp["routes"], corp["bindings"],
            {"route_candidate_id": rc_id,
             "rows": [{"start_station": "11+00", "end_station": "13+00"}]},
        )
        seg = out["generated_segments"][0]
        # Anchors 11+00, 12+00, 13+00 all in [1100, 1300].
        self.assertEqual(seg["matched_anchor_count"], 3)
        self.assertEqual(seg["confidence"]["kind"], "high")


class T10_SchemaValidation(unittest.TestCase):
    def test_non_dict_raw_raises(self):
        corp = _build_route_corpus()
        with self.assertRaises(PEAR.PdfAutoRedlineError):
            PEAR.generate_auto_redline_segments(
                "nope", corp["routes"], corp["bindings"],
                {"route_candidate_id": "x", "rows": []},
            )  # type: ignore

    def test_wrong_routes_schema_raises(self):
        corp = _build_route_corpus()
        bad = dict(corp["routes"])
        bad["schema_version"] = "wrong"
        with self.assertRaises(PEAR.PdfAutoRedlineError):
            PEAR.generate_auto_redline_segments(
                corp["raw"], bad, corp["bindings"],
                {"route_candidate_id": "x", "rows": []},
            )

    def test_wrong_bindings_schema_raises(self):
        corp = _build_route_corpus()
        bad = dict(corp["bindings"])
        bad["schema_version"] = "wrong"
        with self.assertRaises(PEAR.PdfAutoRedlineError):
            PEAR.generate_auto_redline_segments(
                corp["raw"], corp["routes"], bad,
                {"route_candidate_id": "x", "rows": []},
            )

    def test_rows_not_list_raises(self):
        corp = _build_route_corpus()
        rc_id = corp["routes"]["route_candidates"][0]["candidate_id"]
        with self.assertRaises(PEAR.PdfAutoRedlineError):
            PEAR.generate_auto_redline_segments(
                corp["raw"], corp["routes"], corp["bindings"],
                {"route_candidate_id": rc_id, "rows": "not a list"},
            )


class T11_MalformedRowHandled(unittest.TestCase):
    def test_non_dict_row_rejected(self):
        corp = _build_route_corpus()
        rc_id = corp["routes"]["route_candidates"][0]["candidate_id"]
        out = PEAR.generate_auto_redline_segments(
            corp["raw"], corp["routes"], corp["bindings"],
            {"route_candidate_id": rc_id,
             "rows": ["not a dict",
                      {"start_station": "11+00", "end_station": "12+00"}]},
        )
        self.assertEqual(len(out["generated_segments"]), 1)
        self.assertEqual(len(out["rejected_rows"]), 1)
        self.assertEqual(out["rejected_rows"][0]["rule_id"],
                         "auto_redline_v1:row_shape")


class T12_PageLevelWarnings(unittest.TestCase):
    def test_no_anchors_bound_to_route(self):
        # Build a corpus where route exists but NO station anchors are
        # bound to it (the text labels are far from the route).
        raw_vector_paths = [
            _raw_path("h_route", stroke="#ff0000",
                      bbox=(50.0, 99.0, 1000.0, 101.0),
                      items=[["l", [50.0, 100.0], [1000.0, 100.0]]]),
        ]
        # Place anchor labels 500pt away from the route (won't bind).
        text_blocks = [
            _text_block("STA 11+00", bbox=(100, 700, 200, 712), block_no=1),
        ]
        raw = _build_raw(text_blocks=text_blocks, vector_paths=raw_vector_paths)
        classified = PEC.classify_vector_paths(raw)
        routes = PER.group_route_candidates(classified, raw_record=raw,
                                            bucket="proposed_red")
        bindings = PEB.bind_labels_to_routes(raw, routes,
                                             classified_record=classified)
        rc_id = routes["route_candidates"][0]["candidate_id"]
        out = PEAR.generate_auto_redline_segments(
            raw, routes, bindings,
            {"route_candidate_id": rc_id,
             "rows": [{"start_station": "11+00", "end_station": "12+00"}]},
        )
        self.assertIn("no_station_anchors_bound_to_route_candidate", out["warnings"])
        self.assertEqual(out["meta"]["available_anchor_count"], 0)

    def test_all_rows_rejected_page_warning(self):
        corp = _build_route_corpus()
        rc_id = corp["routes"]["route_candidates"][0]["candidate_id"]
        out = PEAR.generate_auto_redline_segments(
            corp["raw"], corp["routes"], corp["bindings"],
            {"route_candidate_id": rc_id,
             "rows": [{"start_station": "BAD", "end_station": "ALSOBAD"}]},
        )
        self.assertIn("no_segments_generated_all_rows_rejected", out["warnings"])


# ===========================================================================
# ENDPOINT TESTS
# ===========================================================================

def _make_route_pdf(target: Path) -> None:
    """One-page PDF with a red horizontal line + station label."""
    import fitz
    doc = fitz.open()
    try:
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 80), "STA 11+60", fontsize=10)
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
    SESSION_ID = "sess_test_autoredline"
    PLAN_ID = "abc123autoredline"

    def setUp(self) -> None:
        self._saved = {f: os.environ.pop(f, None) for f in _ALL_FLAGS}
        self._tmp_root = Path(tempfile.mkdtemp(prefix="pdf_ext_autoredline_"))
        self._eng_root = self._tmp_root / "uploads" / "engineering_plans"
        self._sess_folder = self._eng_root / self.SESSION_ID
        self._sess_folder.mkdir(parents=True, exist_ok=True)
        self._pdf_path = self._sess_folder / "test_plan.pdf"
        self._build_pdf(self._pdf_path)
        self._plan = _make_plan_record(
            plan_id=self.PLAN_ID, session_id=self.SESSION_ID,
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
        for f in _ALL_FLAGS:
            os.environ[f] = "1"

    def _call(self, payload: Dict[str, Any] = None) -> Any:
        if payload is None:
            payload = {
                "session_id": self.SESSION_ID,
                "page_index": 0,
                "bucket": "proposed_red",
                "route_candidate_id": "rc_0000",
                "rows": [],
                "dry_run": True,
            }
        return asyncio.run(
            M.post_engineering_plan_extraction_auto_redline(
                plan_id=self.PLAN_ID, payload=payload, request=None,
            )
        )


# T13: flag gating
class T13_FlagGating(_BaseEndpointTest):
    def _build_pdf(self, target: Path) -> None:
        _make_route_pdf(target)

    def test_all_flags_off_returns_404(self) -> None:
        for f in _ALL_FLAGS:
            os.environ.pop(f, None)
        self.assertEqual(self._call().status_code, 404)

    def test_autoredline_flag_off_returns_404(self) -> None:
        for f in _ALL_FLAGS:
            os.environ[f] = "1"
        os.environ.pop(_AUTOREDLINE_FLAG, None)
        self.assertEqual(self._call().status_code, 404)

    def test_bindings_flag_off_returns_404(self) -> None:
        for f in _ALL_FLAGS:
            os.environ[f] = "1"
        os.environ.pop(_BINDINGS_FLAG, None)
        self.assertEqual(self._call().status_code, 404)


# T14: invalid payload
class T14_InvalidPayload(_BaseEndpointTest):
    def _build_pdf(self, target: Path) -> None:
        _make_route_pdf(target)

    def setUp(self) -> None:
        super().setUp()
        self._enable_all_flags()

    def test_missing_page_index_returns_400(self) -> None:
        r = self._call({
            "session_id": self.SESSION_ID, "bucket": "proposed_red",
            "route_candidate_id": "rc_0000", "rows": [],
        })
        self.assertEqual(r.status_code, 400)

    def test_missing_route_candidate_id_returns_400(self) -> None:
        r = self._call({
            "session_id": self.SESSION_ID, "page_index": 0,
            "bucket": "proposed_red", "rows": [],
        })
        self.assertEqual(r.status_code, 400)

    def test_missing_rows_returns_400(self) -> None:
        r = self._call({
            "session_id": self.SESSION_ID, "page_index": 0,
            "bucket": "proposed_red", "route_candidate_id": "rc_0000",
        })
        self.assertEqual(r.status_code, 400)

    def test_invalid_bucket_returns_400(self) -> None:
        r = self._call({
            "session_id": self.SESSION_ID, "page_index": 0,
            "bucket": "BOGUS", "route_candidate_id": "rc_0000", "rows": [],
        })
        self.assertEqual(r.status_code, 400)

    def test_unknown_route_candidate_returns_400(self) -> None:
        # Helper-layer error surfaces as 400 (operator-facing).
        r = self._call({
            "session_id": self.SESSION_ID, "page_index": 0,
            "bucket": "proposed_red",
            "route_candidate_id": "rc_does_not_exist",
            "rows": [{"start_station": "11+00", "end_station": "12+00"}],
        })
        self.assertEqual(r.status_code, 400)


# T15: ownership delegation
class T15_OwnershipDelegation(_BaseEndpointTest):
    def _build_pdf(self, target: Path) -> None:
        _make_route_pdf(target)

    def setUp(self) -> None:
        super().setUp()
        self._enable_all_flags()

    def test_require_tenant_owns_session_invoked(self) -> None:
        with patch.object(M, "_require_tenant_owns_session", return_value=None) as spy:
            r = self._call({
                "session_id": self.SESSION_ID, "page_index": 0,
                "bucket": "proposed_red",
                "route_candidate_id": "rc_0000",
                "rows": [],
            })
            # Even if compute fails downstream, ownership check fired first.
            self.assertEqual(spy.call_count, 1)
            args, _ = spy.call_args
            self.assertEqual(args[0], self.SESSION_ID)


# T16: cache cascade — endpoint actually runs E1+E2a+E2b+E2c+E3 on a real PDF
class T16_CacheCascadeRunsAllLayers(_BaseEndpointTest):
    def _build_pdf(self, target: Path) -> None:
        _make_route_pdf(target)

    def setUp(self) -> None:
        super().setUp()
        self._enable_all_flags()

    def test_first_call_creates_all_caches(self) -> None:
        # Need to learn the route_candidate_id the PDF produces first.
        # Use a payload with empty rows so we don't reject anything, and
        # use a route_candidate_id known not to match → expect 400, but
        # caches still populated.  Then read the routes cache to get
        # the real id, then call with valid id.
        # Step 1: trigger cache fill with an invalid route_id (400 OK).
        r0 = self._call({
            "session_id": self.SESSION_ID, "page_index": 0,
            "bucket": "proposed_red",
            "route_candidate_id": "rc_unknown",
            "rows": [],
            "dry_run": True,
        })
        self.assertEqual(r0.status_code, 400)
        # Cache files should now exist from the cascade.
        raw_cache = self._sess_folder / "extraction" / f"{self.PLAN_ID}_p000_pdf-extraction-raw-1.json"
        routes_cache = (
            self._sess_folder / "extraction"
            / f"{self.PLAN_ID}_p000_pdf-extraction-routes-1_b-proposed_red.json"
        )
        self.assertTrue(raw_cache.is_file(), "raw cache missing")
        self.assertTrue(routes_cache.is_file(), "routes cache missing")

        # Step 2: read the actual route_candidate_id from the cache and
        # call with valid id.  PyMuPDF emission may yield 1+ candidates.
        with routes_cache.open(encoding="utf-8") as f:
            routes = json.load(f)
        if not routes.get("route_candidates"):
            self.skipTest("PDF produced no route candidates (PyMuPDF emission "
                          "variance); endpoint cache cascade still verified")
        real_rc_id = routes["route_candidates"][0]["candidate_id"]
        r = self._call({
            "session_id": self.SESSION_ID, "page_index": 0,
            "bucket": "proposed_red",
            "route_candidate_id": real_rc_id,
            "rows": [{"start_station": "11+60", "end_station": "12+00"}],
            "dry_run": True,
        })
        self.assertEqual(r.status_code, 200)
        body = _read_body(r)
        self.assertEqual(body["schema_version"], "pdf-auto-redline-1")
        self.assertEqual(body["route_candidate_id"], real_rc_id)
        self.assertFalse(body["meta"]["persisted"])


# ===========================================================================
# E3.0.5 GEOMETRY PROJECTION TESTS
# ===========================================================================

class T17_GeometryProjectionSucceeds(unittest.TestCase):
    """With >=2 anchors bound to a clean horizontal route, geometry is
    emitted as a polyline subpath."""
    def test_two_anchors_produces_polyline(self):
        corp = _build_route_corpus(n_anchors=4)
        rc_id = corp["routes"]["route_candidates"][0]["candidate_id"]
        out = PEAR.generate_auto_redline_segments(
            corp["raw"], corp["routes"], corp["bindings"],
            {"route_candidate_id": rc_id,
             "rows": [{"start_station": "11+00", "end_station": "12+00"}]},
        )
        self.assertEqual(len(out["generated_segments"]), 1)
        seg = out["generated_segments"][0]
        self.assertEqual(seg["geometry_type"], "polyline")
        self.assertEqual(seg["projection_method"], "two_anchor_linear")
        self.assertIsNotNone(seg["polyline_points"])
        self.assertGreaterEqual(len(seg["polyline_points"]), 2)
        # Each polyline point is [x, y]
        for pt in seg["polyline_points"]:
            self.assertEqual(len(pt), 2)
            self.assertIsInstance(pt[0], (int, float))
            self.assertIsInstance(pt[1], (int, float))
        # Start + end projections present.
        self.assertIsNotNone(seg["start_projection"])
        self.assertIsNotNone(seg["end_projection"])
        self.assertEqual(seg["start_projection"]["source"], "interpolated")
        self.assertEqual(seg["end_projection"]["source"], "interpolated")
        # Confidence "high" because: anchor_span=300ft >= 50, range in
        # span, no clipping, single segment fully consumed.
        self.assertEqual(seg["geometry_confidence"], "high")
        # Route polyline emitted at envelope level.
        self.assertTrue(out["route_polyline_built"])
        self.assertGreater(len(out["route_polyline_points"]), 0)
        self.assertGreater(out["route_polyline_total_length_pt"], 0.0)
        self.assertGreater(len(out["anchor_projections"]), 0)


class T18_GeometryProjectionStartEndOrder(unittest.TestCase):
    """For a positive-slope model (station_ft increases with polyline
    distance), start_projection.distance < end_projection.distance."""
    def test_start_distance_less_than_end(self):
        corp = _build_route_corpus(n_anchors=4)
        rc_id = corp["routes"]["route_candidates"][0]["candidate_id"]
        out = PEAR.generate_auto_redline_segments(
            corp["raw"], corp["routes"], corp["bindings"],
            {"route_candidate_id": rc_id,
             "rows": [{"start_station": "11+00", "end_station": "12+00"}]},
        )
        seg = out["generated_segments"][0]
        sd = seg["start_projection"]["distance_along_route_pt"]
        ed = seg["end_projection"]["distance_along_route_pt"]
        self.assertLess(sd, ed)
        # x-coordinate of start_pt should be less than x-coord of end_pt
        # (since the route is left-to-right horizontal).
        self.assertLess(seg["start_projection"]["point"][0],
                        seg["end_projection"]["point"][0])


class T19_FallbackZeroAnchors(unittest.TestCase):
    """When NO station anchors are bound to the route, segment downgrades
    to bbox_fallback with the appropriate warning."""
    def test_no_anchors_falls_back(self):
        # Route exists; text labels are 500pt away so binding fails.
        raw_vector_paths = [
            _raw_path("h_route", stroke="#ff0000",
                      bbox=(50.0, 99.0, 1000.0, 101.0),
                      items=[["l", [50.0, 100.0], [1000.0, 100.0]]]),
        ]
        text_blocks = [
            _text_block("STA 11+00", bbox=(100, 700, 200, 712), block_no=1),
        ]
        raw = _build_raw(text_blocks=text_blocks, vector_paths=raw_vector_paths)
        classified = PEC.classify_vector_paths(raw)
        routes = PER.group_route_candidates(classified, raw_record=raw,
                                            bucket="proposed_red")
        bindings = PEB.bind_labels_to_routes(raw, routes,
                                             classified_record=classified)
        rc_id = routes["route_candidates"][0]["candidate_id"]
        out = PEAR.generate_auto_redline_segments(
            raw, routes, bindings,
            {"route_candidate_id": rc_id,
             "rows": [{"start_station": "11+00", "end_station": "12+00"}]},
        )
        seg = out["generated_segments"][0]
        self.assertEqual(seg["geometry_type"], "bbox_fallback")
        self.assertIsNone(seg["polyline_points"])
        self.assertIsNone(seg["start_projection"])
        self.assertIsNone(seg["end_projection"])
        self.assertEqual(seg["projection_method"], "bbox_fallback")
        self.assertEqual(seg["geometry_confidence"], "none")
        self.assertIn("geometry_bbox_fallback_no_anchors", seg["geometry_warnings"])
        # Route_candidate_bbox preserved for fallback rendering.
        self.assertGreater(len(seg["route_candidate_bbox"]), 0)


class T20_FallbackSingleAnchor(unittest.TestCase):
    """With exactly 1 bound anchor, fall back (need >=2 for linear model)."""
    def test_single_anchor_falls_back(self):
        corp = _build_route_corpus(n_anchors=1)
        rc_id = corp["routes"]["route_candidates"][0]["candidate_id"]
        # Confirm only 1 anchor is in pool.
        self.assertEqual(len(corp["bindings"]["station_anchors"]), 1)
        out = PEAR.generate_auto_redline_segments(
            corp["raw"], corp["routes"], corp["bindings"],
            {"route_candidate_id": rc_id,
             "rows": [{"start_station": "11+00", "end_station": "12+00"}]},
        )
        seg = out["generated_segments"][0]
        self.assertEqual(seg["geometry_type"], "bbox_fallback")
        self.assertIn("geometry_bbox_fallback_single_anchor", seg["geometry_warnings"])


class T21_FallbackEmptyRouteGeometry(unittest.TestCase):
    """When the route candidate's paths have no usable items, polyline
    cannot be built; fall back."""
    def test_empty_items_falls_back(self):
        # Build a route candidate whose source path has empty items.
        # E2b will still group it (it has bbox), but reconstruction fails.
        raw_vector_paths = [
            _raw_path("h_empty", stroke="#ff0000",
                      bbox=(50.0, 99.0, 1000.0, 101.0),
                      items=[]),  # EMPTY items
        ]
        text_blocks = [
            _text_block("STA 11+00", bbox=(100, 102, 200, 114), block_no=1),
            _text_block("STA 13+00", bbox=(500, 102, 600, 114), block_no=2),
        ]
        raw = _build_raw(text_blocks=text_blocks, vector_paths=raw_vector_paths)
        classified = PEC.classify_vector_paths(raw)
        routes = PER.group_route_candidates(classified, raw_record=raw,
                                            bucket="proposed_red")
        # Need at least one candidate for the test to be meaningful.
        if not routes["route_candidates"]:
            self.skipTest("E2b filtered out empty-items candidate (correct behavior)")
        rc_id = routes["route_candidates"][0]["candidate_id"]
        bindings = PEB.bind_labels_to_routes(raw, routes,
                                             classified_record=classified)
        out = PEAR.generate_auto_redline_segments(
            raw, routes, bindings,
            {"route_candidate_id": rc_id,
             "rows": [{"start_station": "11+00", "end_station": "12+00"}]},
        )
        seg = out["generated_segments"][0]
        self.assertEqual(seg["geometry_type"], "bbox_fallback")
        self.assertIn(
            "geometry_bbox_fallback_polyline_empty", seg["geometry_warnings"],
        )


class T22_DeterministicPolylineOutput(unittest.TestCase):
    """Same inputs → byte-identical polyline_points + projections."""
    def test_byte_identical_geometry(self):
        corp = _build_route_corpus(n_anchors=4)
        rc_id = corp["routes"]["route_candidates"][0]["candidate_id"]
        payload = {
            "route_candidate_id": rc_id,
            "rows": [
                {"start_station": "11+00", "end_station": "11+50"},
                {"start_station": "12+00", "end_station": "12+50"},
            ],
        }
        o1 = PEAR.generate_auto_redline_segments(
            corp["raw"], corp["routes"], corp["bindings"], payload)
        o2 = PEAR.generate_auto_redline_segments(
            corp["raw"], corp["routes"], corp["bindings"], payload)
        # Geometry fields are deterministic.
        for k in ("polyline_points", "start_projection", "end_projection",
                  "geometry_type", "projection_method", "geometry_confidence"):
            for s1, s2 in zip(o1["generated_segments"], o2["generated_segments"]):
                self.assertEqual(s1[k], s2[k], f"key {k!r} differs across runs")
        # Top-level route polyline also deterministic.
        self.assertEqual(o1["route_polyline_points"], o2["route_polyline_points"])
        self.assertEqual(o1["anchor_projections"], o2["anchor_projections"])


class T23_GeometryWithEndBeforeStart(unittest.TestCase):
    """E3.0.5 doesn't break the existing end<=start rejection — projection
    isn't even attempted because the row gets rejected upstream."""
    def test_end_before_start_still_rejected(self):
        corp = _build_route_corpus(n_anchors=4)
        rc_id = corp["routes"]["route_candidates"][0]["candidate_id"]
        out = PEAR.generate_auto_redline_segments(
            corp["raw"], corp["routes"], corp["bindings"],
            {"route_candidate_id": rc_id,
             "rows": [{"start_station": "12+00", "end_station": "11+00"}]},
        )
        self.assertEqual(out["generated_segments"], [])
        self.assertEqual(len(out["rejected_rows"]), 1)
        self.assertEqual(out["rejected_rows"][0]["rule_id"],
                         "auto_redline_v1:end_before_start")


class T24_ExtrapolatedOutsideAnchorSpan(unittest.TestCase):
    """A range that falls OUTSIDE the bound anchor span produces a
    polyline (extrapolated) but emits a warning + downgrades confidence."""
    def test_extrapolation_warned(self):
        # Anchors at 10+00, 11+00, 12+00, 13+00.  Request range 14+00 to 15+00.
        corp = _build_route_corpus(n_anchors=4)
        rc_id = corp["routes"]["route_candidates"][0]["candidate_id"]
        out = PEAR.generate_auto_redline_segments(
            corp["raw"], corp["routes"], corp["bindings"],
            {"route_candidate_id": rc_id,
             "rows": [{"start_station": "14+00", "end_station": "15+00"}]},
        )
        seg = out["generated_segments"][0]
        # May still produce a polyline (extrapolation is allowed); OR may
        # clip to bounds and warn.  Either way must NOT be "high" confidence.
        self.assertIn(seg["geometry_confidence"], {"low", "medium", "none"})
        if seg["geometry_type"] == "polyline":
            self.assertIn(
                "geometry_extrapolated_outside_anchor_span",
                seg["geometry_warnings"],
            )


class T25_AnchorSpanTooShortIsMedium(unittest.TestCase):
    """With anchor span < _MIN_ANCHOR_SPAN_FT (50ft default), even a
    clean projection is "medium" confidence."""
    def test_short_anchor_span(self):
        # Build a route with two anchors only 30ft apart in station_ft.
        raw_vector_paths = [
            _raw_path("h_route", stroke="#ff0000",
                      bbox=(50.0, 99.0, 1000.0, 101.0),
                      items=[["l", [50.0, 100.0], [1000.0, 100.0]]]),
        ]
        text_blocks = [
            _text_block("STA 11+00", bbox=(100, 102, 200, 114), block_no=1),
            _text_block("STA 11+30", bbox=(150, 102, 250, 114), block_no=2),
        ]
        raw = _build_raw(text_blocks=text_blocks, vector_paths=raw_vector_paths)
        classified = PEC.classify_vector_paths(raw)
        routes = PER.group_route_candidates(classified, raw_record=raw,
                                            bucket="proposed_red")
        bindings = PEB.bind_labels_to_routes(raw, routes,
                                             classified_record=classified)
        rc_id = routes["route_candidates"][0]["candidate_id"]
        out = PEAR.generate_auto_redline_segments(
            raw, routes, bindings,
            {"route_candidate_id": rc_id,
             "rows": [{"start_station": "11+10", "end_station": "11+25"}]},
        )
        seg = out["generated_segments"][0]
        if seg["geometry_type"] == "polyline":
            # Anchor span = 30ft < 50ft, so not "high" confidence.
            self.assertNotEqual(seg["geometry_confidence"], "high")


class T26_NoPersistenceEvenWithDryRunFalse_E305(unittest.TestCase):
    """E3.0.5 inherits the v1 dry-run-only policy — confirm explicitly."""
    def test_dry_run_false_no_persist(self):
        corp = _build_route_corpus(n_anchors=4)
        rc_id = corp["routes"]["route_candidates"][0]["candidate_id"]
        out = PEAR.generate_auto_redline_segments(
            corp["raw"], corp["routes"], corp["bindings"],
            {"route_candidate_id": rc_id,
             "rows": [{"start_station": "11+00", "end_station": "12+00"}],
             "dry_run": False},
        )
        # Geometry computed but NO persistence.
        self.assertEqual(out["generated_segments"][0]["geometry_type"], "polyline")
        self.assertFalse(out["meta"]["persisted"])
        self.assertFalse(out["meta"]["persistence_enabled_in_v1"])


class T27_ProvenancePreservedWithGeometry(unittest.TestCase):
    """Geometry additions don't displace existing provenance."""
    def test_provenance_intact(self):
        corp = _build_route_corpus(n_anchors=4)
        rc_id = corp["routes"]["route_candidates"][0]["candidate_id"]
        row = {"start_station": "11+00", "end_station": "12+00",
               "notes": "operator note"}
        out = PEAR.generate_auto_redline_segments(
            corp["raw"], corp["routes"], corp["bindings"],
            {"route_candidate_id": rc_id, "rows": [row]},
        )
        seg = out["generated_segments"][0]
        # Original provenance fields all still present.
        self.assertEqual(seg["rule_id"], "auto_redline_v1")
        self.assertEqual(seg["provenance"]["input_row"], row)
        self.assertEqual(seg["provenance"]["input_row_index"], 0)
        self.assertEqual(seg["notes"], "operator note")
        # And new geometry fields are present.
        self.assertEqual(seg["geometry_type"], "polyline")


class T28_SameStationAnchorsFallback(unittest.TestCase):
    """When 2+ anchors all map to the same station_ft (anchor span = 0),
    no linear model is buildable; fall back."""
    def test_same_station_anchors(self):
        # Build a route with two anchors that both read "STA 11+00"
        # (operator may have placed duplicate labels).
        raw_vector_paths = [
            _raw_path("h_route", stroke="#ff0000",
                      bbox=(50.0, 99.0, 1000.0, 101.0),
                      items=[["l", [50.0, 100.0], [1000.0, 100.0]]]),
        ]
        text_blocks = [
            _text_block("STA 11+00", bbox=(100, 102, 200, 114), block_no=1),
            _text_block("STA 11+00", bbox=(500, 102, 600, 114), block_no=2),
        ]
        raw = _build_raw(text_blocks=text_blocks, vector_paths=raw_vector_paths)
        classified = PEC.classify_vector_paths(raw)
        routes = PER.group_route_candidates(classified, raw_record=raw,
                                            bucket="proposed_red")
        bindings = PEB.bind_labels_to_routes(raw, routes,
                                             classified_record=classified)
        rc_id = routes["route_candidates"][0]["candidate_id"]
        out = PEAR.generate_auto_redline_segments(
            raw, routes, bindings,
            {"route_candidate_id": rc_id,
             "rows": [{"start_station": "11+00", "end_station": "12+00"}]},
        )
        seg = out["generated_segments"][0]
        self.assertEqual(seg["geometry_type"], "bbox_fallback")
        self.assertIn(
            "geometry_bbox_fallback_anchor_span_zero",
            seg["geometry_warnings"],
        )


if __name__ == "__main__":
    unittest.main()
