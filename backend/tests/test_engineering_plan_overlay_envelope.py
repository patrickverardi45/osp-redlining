"""VO.1a — engineering_plan_overlay envelope tests (T1–T10).

Targets ``build_engineering_plan_overlay_envelope`` from
``backend/app/core/plan_overlay.py`` against the contract in
``wiki/sprints/visual-overlay/vo-0-design-packet.md`` §3 and the
implementation plan ``wiki/sprints/visual-overlay/vo-1a-implementation-plan.md``.

COMMAND
-------
    python -m pytest backend/tests/test_engineering_plan_overlay_envelope.py -v
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

os.environ.setdefault("TRUELINE_JWT_SECRET", "vo1a-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "vo1a-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend import main as M  # noqa: E402 — envelope helper resolves main via sys.modules
# Import plan_topology_cache + plan_overlay via the SAME module path that
# backend/app/core/plan_overlay.py uses internally (``from app.core import
# plan_topology_cache``).  Python keys sys.modules by import name, so
# ``backend.app.core.plan_topology_cache`` and ``app.core.plan_topology_cache``
# are distinct module objects when both paths are reachable.  Patching the
# wrong instance would not affect what the helper sees at runtime.  Pytest
# adds ``backend/`` to sys.path via tests/__init__.py, so ``app.core`` is
# resolvable here.
from app.core import plan_topology_cache  # noqa: E402
from app.core.plan_overlay import (  # noqa: E402
    _SCHEMA_VERSION,
    build_engineering_plan_overlay_envelope,
)


_PARSE_FLAG = "TRUELINE_PLAN_PDF_PARSE"


class _FlagOnMixin:
    """Mixin that turns the PDF parse flag ON for the test class and
    restores prior env state on teardown."""

    def setUp(self) -> None:  # type: ignore[override]
        self._saved_parse_flag = os.environ.get(_PARSE_FLAG)
        os.environ[_PARSE_FLAG] = "1"

    def tearDown(self) -> None:  # type: ignore[override]
        if self._saved_parse_flag is None:
            os.environ.pop(_PARSE_FLAG, None)
        else:
            os.environ[_PARSE_FLAG] = self._saved_parse_flag


# ─── T1 ──────────────────────────────────────────────────────────────────────


class T1_SchemaConstant(unittest.TestCase):
    """T1 — module-level schema constant matches the design packet."""

    def test_schema_version_is_v1(self) -> None:
        self.assertEqual(_SCHEMA_VERSION, "engineering-plan-overlay-1")


# ─── T2 ──────────────────────────────────────────────────────────────────────


class T2_ParseFlagOff(unittest.TestCase):
    """T2 — TRUELINE_PLAN_PDF_PARSE off (default) → empty envelope."""

    def setUp(self) -> None:
        self._saved = os.environ.pop(_PARSE_FLAG, None)

    def tearDown(self) -> None:
        if self._saved is None:
            os.environ.pop(_PARSE_FLAG, None)
        else:
            os.environ[_PARSE_FLAG] = self._saved

    def test_flag_off_returns_empty_envelope(self) -> None:
        os.environ[_PARSE_FLAG] = "0"
        result = build_engineering_plan_overlay_envelope("any_session_id")
        self.assertEqual(result["schema"], "engineering-plan-overlay-1")
        self.assertEqual(result["topology_source"], "bypassed_flag_off")
        self.assertIsNone(result["plan_set_signature"])
        self.assertEqual(result["sheets"], [])
        self.assertEqual(result["pdfs"], [])
        self.assertEqual(result["pages"], [])

    def test_flag_unset_returns_empty_envelope(self) -> None:
        os.environ.pop(_PARSE_FLAG, None)
        result = build_engineering_plan_overlay_envelope("any_session_id")
        self.assertEqual(result["topology_source"], "bypassed_flag_off")


# ─── T3 ──────────────────────────────────────────────────────────────────────


class T3_EmptySessionId(_FlagOnMixin, unittest.TestCase):
    """T3 — empty session_id with flag on → empty envelope."""

    def test_empty_session_id_returns_empty_envelope(self) -> None:
        result = build_engineering_plan_overlay_envelope("")
        self.assertEqual(result["topology_source"], "bypassed_flag_off")
        self.assertEqual(result["sheets"], [])


# ─── T4 ──────────────────────────────────────────────────────────────────────


class T4_NoPDFsUploaded(_FlagOnMixin, unittest.TestCase):
    """T4 — flag on, no PDFs uploaded → bypassed_other_scope."""

    def test_no_pdfs_returns_bypassed_other_scope(self) -> None:
        with patch.object(M, "_resolve_engineering_plan_pdf_paths", return_value=[]):
            with patch.object(M, "_load_engineering_plan_index_for_session", return_value=[]):
                result = build_engineering_plan_overlay_envelope("sid_no_plans")
        self.assertEqual(result["topology_source"], "bypassed_other_scope")
        self.assertEqual(result["sheets"], [])
        self.assertEqual(result["pdfs"], [])
        self.assertEqual(result["pages"], [])


# ─── T5 ──────────────────────────────────────────────────────────────────────


class T5_CacheAbsent(_FlagOnMixin, unittest.TestCase):
    """T5 — flag on, PDFs uploaded, cache absent → rows_only_cache_miss_empty."""

    def test_cache_absent_returns_rows_only_cache_miss_empty(self) -> None:
        plans: List[Dict[str, Any]] = [{
            "plan_id": "abc",
            "stored_filename": "a.pdf",
            "size_bytes": 100,
            "uploaded_at": "now",
        }]
        with patch.object(M, "_resolve_engineering_plan_pdf_paths", return_value=[Path("/fake/a.pdf")]):
            with patch.object(M, "_load_engineering_plan_index_for_session", return_value=plans):
                with patch.object(plan_topology_cache, "cache_read_full", return_value=None):
                    result = build_engineering_plan_overlay_envelope("sid_no_cache")
        self.assertEqual(result["topology_source"], "rows_only_cache_miss_empty")
        self.assertEqual(result["sheets"], [])


# ─── T6 ──────────────────────────────────────────────────────────────────────


class T6_CacheStaleSignature(_FlagOnMixin, unittest.TestCase):
    """T6 — flag on, cache exists but signature stale → rows_only_cache_miss_empty."""

    def test_stale_signature_returns_rows_only_cache_miss_empty(self) -> None:
        plans: List[Dict[str, Any]] = [{
            "plan_id": "abc",
            "stored_filename": "a.pdf",
            "size_bytes": 100,
            "uploaded_at": "now",
        }]
        fake_cache: Dict[str, Any] = {
            "schema": plan_topology_cache.SCHEMA_VERSION,
            "plan_set_signature": "DEFINITELY_NOT_THE_RIGHT_SIGNATURE",
            "topology": {},
            "pdf_outcomes": [],
            "per_page_outcomes": [],
        }
        with patch.object(M, "_resolve_engineering_plan_pdf_paths", return_value=[Path("/fake/a.pdf")]):
            with patch.object(M, "_load_engineering_plan_index_for_session", return_value=plans):
                with patch.object(plan_topology_cache, "cache_read_full", return_value=fake_cache):
                    result = build_engineering_plan_overlay_envelope("sid_stale")
        self.assertEqual(result["topology_source"], "rows_only_cache_miss_empty")


# ─── T7 ──────────────────────────────────────────────────────────────────────


class T7_CacheHitPopulated(_FlagOnMixin, unittest.TestCase):
    """T7 — flag on, cache hit with matching signature → populated envelope."""

    def test_cache_hit_yields_populated_envelope(self) -> None:
        plans: List[Dict[str, Any]] = [{
            "plan_id": "p1",
            "original_filename": "plan1.pdf",
            "stored_filename": "1_p1.pdf",
            "size_bytes": 100,
            "uploaded_at": "t1",
        }]
        signature = plan_topology_cache.derive_plan_set_signature(plans)
        fake_cache: Dict[str, Any] = {
            "schema": plan_topology_cache.SCHEMA_VERSION,
            "plan_set_signature": signature,
            "topology": {
                12: {
                    "anchor_station_ft": 100.0,
                    "span_ft": 938.0,
                    "source_pdf_index": 0,
                    "source_page_index": 11,
                    "confidence": 0.72,
                },
                13: {
                    "anchor_station_ft": 1038.0,
                    "span_ft": 800.0,
                    "source_pdf_index": 0,
                    "source_page_index": 12,
                },
            },
            "pdf_outcomes": [{
                "pdf_index": 0,
                "path": "/fake/1.pdf",
                "status": "ok",
                "page_count": 43,
                "pages_ok": 43,
                "pages_timeout": 0,
                "pages_error": 0,
                "pages_skipped": 0,
                "total_matchlines": 48,
                "total_callouts": 376,
                "bounded_by": "natural_completion",
                "elapsed_ms": 543800,
            }],
            "per_page_outcomes": [
                {"pdf_index": 0, "page_index": 0,  "status": "ok",      "text_len": 2453, "elapsed_ms": 100},
                {"pdf_index": 0, "page_index": 22, "status": "timeout", "text_len": 0,    "error": None, "elapsed_ms": 25000},
            ],
        }
        with patch.object(M, "_resolve_engineering_plan_pdf_paths", return_value=[Path("/fake/1.pdf")]):
            with patch.object(M, "_load_engineering_plan_index_for_session", return_value=plans):
                with patch.object(plan_topology_cache, "cache_read_full", return_value=fake_cache):
                    result = build_engineering_plan_overlay_envelope("sid_hit")

        self.assertEqual(result["schema"], "engineering-plan-overlay-1")
        self.assertEqual(result["topology_source"], "cache_hit")
        self.assertEqual(result["plan_set_signature"], signature[:16])

        self.assertEqual(len(result["sheets"]), 2)
        self.assertEqual(result["sheets"][0]["sheet_number"], 12)
        self.assertEqual(result["sheets"][0]["anchor_station_ft"], 100.0)
        self.assertEqual(result["sheets"][0]["span_ft"], 938.0)
        self.assertEqual(result["sheets"][0]["source_pdf_index"], 0)
        self.assertEqual(result["sheets"][0]["source_page_index"], 11)
        self.assertAlmostEqual(result["sheets"][0]["confidence"], 0.72)
        self.assertEqual(result["sheets"][1]["sheet_number"], 13)
        self.assertIsNone(result["sheets"][1]["confidence"])

        self.assertEqual(len(result["pdfs"]), 1)
        self.assertEqual(result["pdfs"][0]["plan_id"], "p1")
        self.assertEqual(result["pdfs"][0]["original_filename"], "plan1.pdf")
        self.assertEqual(result["pdfs"][0]["page_count"], 43)
        self.assertEqual(result["pdfs"][0]["bounded_by"], "natural_completion")
        self.assertEqual(result["pdfs"][0]["total_matchlines"], 48)
        self.assertEqual(result["pdfs"][0]["total_callouts"], 376)

        self.assertEqual(len(result["pages"]), 2)
        statuses = {p["status"] for p in result["pages"]}
        self.assertEqual(statuses, {"ok", "timeout"})


# ─── T8 ──────────────────────────────────────────────────────────────────────


class T8_PdfsJoinWithPlanIndexMetadata(_FlagOnMixin, unittest.TestCase):
    """T8 — pdf_outcomes joined with plan_index metadata for plan_id + original_filename."""

    def test_pdfs_joined_by_pdf_index(self) -> None:
        plans: List[Dict[str, Any]] = [
            {"plan_id": "abc123", "original_filename": "first.pdf",  "stored_filename": "1_a.pdf", "size_bytes": 100, "uploaded_at": "t1"},
            {"plan_id": "def456", "original_filename": "second.pdf", "stored_filename": "2_b.pdf", "size_bytes": 200, "uploaded_at": "t2"},
        ]
        signature = plan_topology_cache.derive_plan_set_signature(plans)
        fake_cache: Dict[str, Any] = {
            "schema": plan_topology_cache.SCHEMA_VERSION,
            "plan_set_signature": signature,
            "topology": {},
            "pdf_outcomes": [
                {"pdf_index": 0, "path": "/fake/1.pdf", "status": "ok", "page_count": 5,  "pages_ok": 5,  "pages_timeout": 0, "pages_error": 0, "pages_skipped": 0, "total_matchlines": 0, "total_callouts": 0, "bounded_by": "natural_completion", "elapsed_ms": 100},
                {"pdf_index": 1, "path": "/fake/2.pdf", "status": "ok", "page_count": 10, "pages_ok": 10, "pages_timeout": 0, "pages_error": 0, "pages_skipped": 0, "total_matchlines": 0, "total_callouts": 0, "bounded_by": "natural_completion", "elapsed_ms": 200},
            ],
            "per_page_outcomes": [],
        }
        paths = [Path("/fake/1.pdf"), Path("/fake/2.pdf")]
        with patch.object(M, "_resolve_engineering_plan_pdf_paths", return_value=paths):
            with patch.object(M, "_load_engineering_plan_index_for_session", return_value=plans):
                with patch.object(plan_topology_cache, "cache_read_full", return_value=fake_cache):
                    result = build_engineering_plan_overlay_envelope("sid_join")

        self.assertEqual(len(result["pdfs"]), 2)
        joined = {p["pdf_index"]: p for p in result["pdfs"]}
        self.assertEqual(joined[0]["plan_id"], "abc123")
        self.assertEqual(joined[0]["original_filename"], "first.pdf")
        self.assertEqual(joined[1]["plan_id"], "def456")
        self.assertEqual(joined[1]["original_filename"], "second.pdf")


# ─── T9 ──────────────────────────────────────────────────────────────────────


class T9_PagesMirrorPerPageOutcomes(_FlagOnMixin, unittest.TestCase):
    """T9 — per_page_outcomes surface as pages[] verbatim."""

    def test_pages_surface_per_page_outcomes(self) -> None:
        plans: List[Dict[str, Any]] = [{
            "plan_id": "p",
            "original_filename": "x.pdf",
            "stored_filename": "x.pdf",
            "size_bytes": 1,
            "uploaded_at": "t",
        }]
        signature = plan_topology_cache.derive_plan_set_signature(plans)
        fake_cache: Dict[str, Any] = {
            "schema": plan_topology_cache.SCHEMA_VERSION,
            "plan_set_signature": signature,
            "topology": {},
            "pdf_outcomes": [],
            "per_page_outcomes": [
                {"pdf_index": 0, "page_index": 0, "status": "ok",      "text_len": 1000},
                {"pdf_index": 0, "page_index": 1, "status": "timeout", "text_len": 0, "error": None},
                {"pdf_index": 0, "page_index": 2, "status": "error",   "text_len": 0, "error": "ValueError: bad page"},
                {"pdf_index": 0, "page_index": 3, "status": "skipped", "text_len": 0},
            ],
        }
        with patch.object(M, "_resolve_engineering_plan_pdf_paths", return_value=[Path("/fake/x.pdf")]):
            with patch.object(M, "_load_engineering_plan_index_for_session", return_value=plans):
                with patch.object(plan_topology_cache, "cache_read_full", return_value=fake_cache):
                    result = build_engineering_plan_overlay_envelope("sid_pages")

        self.assertEqual(len(result["pages"]), 4)
        by_idx = {p["page_index"]: p for p in result["pages"]}
        self.assertEqual(by_idx[0]["status"], "ok")
        self.assertEqual(by_idx[0]["text_len"], 1000)
        self.assertEqual(by_idx[1]["status"], "timeout")
        self.assertEqual(by_idx[2]["status"], "error")
        self.assertEqual(by_idx[2]["error"], "ValueError: bad page")
        self.assertEqual(by_idx[3]["status"], "skipped")


# ─── T10 ─────────────────────────────────────────────────────────────────────


class T10_CrossTenantIsolation(_FlagOnMixin, unittest.TestCase):
    """T10 — every tenant-relevant lookup receives the caller's session_id.

    A bug that hardcoded or leaked another session's id (e.g. by reading
    a module-level STATE attribute) would be caught here.
    """

    def test_caller_session_id_threads_through_every_lookup(self) -> None:
        plans: List[Dict[str, Any]] = [{
            "plan_id": "b1",
            "original_filename": "b.pdf",
            "stored_filename": "b_b.pdf",
            "size_bytes": 200,
            "uploaded_at": "tb",
        }]
        seen: List[Any] = []

        def fake_resolve(sid: str) -> List[Path]:
            seen.append(("resolve", sid))
            return [Path(f"/fake/{sid}.pdf")]

        def fake_load(sid: str) -> List[Dict[str, Any]]:
            seen.append(("load", sid))
            return plans if sid else []

        def fake_cache_file(sid: str, uploads_dir: Any) -> Path:
            seen.append(("cache_file", sid, str(uploads_dir)))
            return Path(f"/fake/topology_cache/{sid}.json")

        with patch.object(M, "_resolve_engineering_plan_pdf_paths", side_effect=fake_resolve):
            with patch.object(M, "_load_engineering_plan_index_for_session", side_effect=fake_load):
                with patch.object(plan_topology_cache, "resolve_cache_file", side_effect=fake_cache_file):
                    with patch.object(plan_topology_cache, "cache_read_full", return_value=None):
                        result = build_engineering_plan_overlay_envelope("session_b")

        # Every tenant-relevant lookup received the caller's sid.
        self.assertIn(("resolve", "session_b"), seen)
        self.assertIn(("load", "session_b"), seen)
        cache_file_calls = [s for s in seen if s[0] == "cache_file"]
        self.assertEqual(len(cache_file_calls), 1)
        self.assertEqual(cache_file_calls[0][1], "session_b")

        # And no leak: no lookup was ever called with anything other than "session_b".
        for entry in seen:
            sid_arg = entry[1]
            self.assertEqual(sid_arg, "session_b", f"leaked sid in {entry}")

        # Envelope reflects cache miss (cache_read_full → None).
        self.assertEqual(result["topology_source"], "rows_only_cache_miss_empty")


if __name__ == "__main__":
    unittest.main()
