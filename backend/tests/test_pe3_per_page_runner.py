"""PE.3 — per-page bounded plan topology runner tests.

All subprocess invocations are mocked. No real PDFs. No real timeout
wallclock. Independent of B-PARSER-FIXTURE-1.

Critical invariant under test: one pathological page does NOT poison
an otherwise-useful PDF. PE.2 (per-PDF granularity) lost an entire 43-
page PDF when page 6 hung pdfminer; PE.3 (per-page granularity) loses
only page 6 and still contributes matchlines/callouts from the other
12 ok pages.

COMMAND
-------
    python -m pytest backend/tests/test_pe3_per_page_runner.py -v
"""

from __future__ import annotations

import json
import os
import subprocess
import unittest
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

os.environ.setdefault("TRUELINE_JWT_SECRET", "pe3-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "pe3-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend import main as M

_PAGE_ENV = "TRUELINE_PE3_PER_PAGE_TIMEOUT_SEC"
_BUDGET_ENV = "TRUELINE_PE3_PER_PDF_TOTAL_BUDGET_SEC"
_PE2_ENV = "TRUELINE_PE2_PER_PDF_TIMEOUT_SEC"


def _mk_proc(returncode: int, stdout: str = "") -> MagicMock:
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = ""
    return m


def _count_payload(page_count: int) -> str:
    return json.dumps({"ok": True, "page_count": page_count})


def _page_payload(
    matchlines: List[Dict[str, Any]] = None,
    callouts: List[Dict[str, Any]] = None,
    text_len: int = 100,
) -> str:
    return json.dumps({
        "ok": True,
        "matchlines": matchlines or [],
        "callouts": callouts or [],
        "text_len": text_len,
        "elapsed_ms": 50,
        "peak_kb": 100,
    })


def _page_error_payload(error: str) -> str:
    return json.dumps({"ok": False, "error": error})


class TestPE3PerPageRunner(unittest.TestCase):
    """PE.3 — _extract_pdf_signals_per_page_bounded + orchestrator + cache."""

    def setUp(self) -> None:
        self._saved_page = os.environ.pop(_PAGE_ENV, None)
        self._saved_budget = os.environ.pop(_BUDGET_ENV, None)
        self._saved_pe2 = os.environ.pop(_PE2_ENV, None)

    def tearDown(self) -> None:
        for k, v in (
            (_PAGE_ENV, self._saved_page),
            (_BUDGET_ENV, self._saved_budget),
            (_PE2_ENV, self._saved_pe2),
        ):
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    # ─── A. Per-page timeout enforcement (G2) ────────────────────────────

    def test_01_per_page_timeout_recorded_as_timeout(self) -> None:
        """One page subprocess.TimeoutExpired → that page status='timeout'."""
        results = [
            _mk_proc(0, _count_payload(3)),                  # count → 3 pages
            _mk_proc(0, _page_payload([{"id": "a"}], [])),   # page 0 → ok
            subprocess.TimeoutExpired(cmd="x", timeout=1),    # page 1 → timeout
            _mk_proc(0, _page_payload([{"id": "c"}], [])),   # page 2 → ok
        ]
        with patch.object(M.subprocess, "run", side_effect=results):
            outcome = M._extract_pdf_signals_per_page_bounded(
                Path("test.pdf"), per_page_timeout_sec=10, per_pdf_total_budget_sec=60
            )
        statuses = [po["status"] for po in outcome["page_outcomes"]]
        self.assertEqual(statuses, ["ok", "timeout", "ok"])
        self.assertEqual(outcome["pages_timeout"], 1)
        self.assertEqual(outcome["pages_ok"], 2)

    def test_02_per_page_timeout_does_not_stop_subsequent_pages(self) -> None:
        """After a per-page timeout, the next page is still attempted."""
        results = [
            _mk_proc(0, _count_payload(2)),
            subprocess.TimeoutExpired(cmd="x", timeout=1),
            _mk_proc(0, _page_payload([{"id": "b"}], [])),
        ]
        with patch.object(M.subprocess, "run", side_effect=results):
            outcome = M._extract_pdf_signals_per_page_bounded(
                Path("test.pdf"), per_page_timeout_sec=10, per_pdf_total_budget_sec=60
            )
        self.assertEqual(outcome["page_outcomes"][0]["status"], "timeout")
        self.assertEqual(outcome["page_outcomes"][1]["status"], "ok")
        self.assertEqual(outcome["matchlines"], [{"id": "b"}])

    def test_03_per_page_timeout_raises_via_subprocess_run(self) -> None:
        """The per-page timeout passed to subprocess.run is per_page_timeout_sec."""
        captured_timeouts: List[int] = []

        def fake_run(*args, **kwargs):
            captured_timeouts.append(kwargs.get("timeout"))
            return _mk_proc(0, _count_payload(1) if len(captured_timeouts) == 1 else _page_payload())

        with patch.object(M.subprocess, "run", side_effect=fake_run):
            M._extract_pdf_signals_per_page_bounded(
                Path("test.pdf"), per_page_timeout_sec=7, per_pdf_total_budget_sec=60
            )
        # Both count and extract_page should use per_page_timeout_sec.
        self.assertEqual(captured_timeouts, [7, 7])

    # ─── B. PDF-level budget enforcement (G3) ───────────────────────────

    def test_04_pdf_budget_exhaustion_records_remaining_as_skipped(self) -> None:
        """Mock time so the PDF budget exhausts mid-loop; remaining pages 'skipped'."""
        results = [
            _mk_proc(0, _count_payload(5)),
            _mk_proc(0, _page_payload([{"id": "a"}], [])),
            _mk_proc(0, _page_payload([{"id": "b"}], [])),
            _mk_proc(0, _page_payload([{"id": "c"}], [])),
            # budget exhausts before page 3 attempted
        ]
        # perf_counter call sequence:
        #   1. pdf_t0
        #   2-3. count worker (t0 + elapsed_ms inside _pe3_run_worker)
        #   4-6. page 0: elapsed_pdf check + worker t0 + worker elapsed_ms
        #   7-9. page 1: same triple
        #   10-12. page 2: same triple
        #   13. page 3: elapsed_pdf check >= budget → break
        #   14. final elapsed_pdf_ms
        times = [
            0.0,                                # pdf_t0
            0.0, 0.1,                           # count worker
            1.0, 1.0, 1.1,                      # page 0
            2.0, 2.0, 2.1,                      # page 1
            3.0, 3.0, 3.1,                      # page 2
            70.0,                               # page 3 elapsed_pdf check (>60 → break)
            71.0,                               # final elapsed_pdf_ms
        ]
        with patch.object(M.subprocess, "run", side_effect=results):
            with patch.object(M.time, "perf_counter", side_effect=times):
                outcome = M._extract_pdf_signals_per_page_bounded(
                    Path("test.pdf"), per_page_timeout_sec=10, per_pdf_total_budget_sec=60
                )
        statuses = [po["status"] for po in outcome["page_outcomes"]]
        self.assertEqual(statuses, ["ok", "ok", "ok", "skipped", "skipped"])
        self.assertEqual(outcome["pages_skipped"], 2)
        self.assertEqual(outcome["bounded_by"], "per_pdf_total_budget")

    def test_05_natural_completion_marked_in_bounded_by(self) -> None:
        """If all pages complete within budget, bounded_by='natural_completion'."""
        results = [
            _mk_proc(0, _count_payload(2)),
            _mk_proc(0, _page_payload()),
            _mk_proc(0, _page_payload()),
        ]
        with patch.object(M.subprocess, "run", side_effect=results):
            outcome = M._extract_pdf_signals_per_page_bounded(
                Path("test.pdf"), per_page_timeout_sec=10, per_pdf_total_budget_sec=60
            )
        self.assertEqual(outcome["bounded_by"], "natural_completion")
        self.assertEqual(outcome["pages_skipped"], 0)

    def test_06_default_per_pdf_total_budget_is_60(self) -> None:
        self.assertEqual(M._pe3_per_pdf_total_budget_sec(), 60)

    # ─── C. Partial extraction (LOAD-BEARING gate G4) ────────────────────

    def test_07_three_ok_pages_contribute_matchlines(self) -> None:
        """3 ok pages in a single PDF contribute their matchlines (central invariant)."""
        results = [
            _mk_proc(0, _count_payload(3)),
            _mk_proc(0, _page_payload([{"page": 1, "id": "a"}], [])),
            _mk_proc(0, _page_payload([{"page": 2, "id": "b"}], [{"page": 2, "id": "x"}])),
            _mk_proc(0, _page_payload([{"page": 3, "id": "c"}], [])),
        ]
        with patch.object(M.subprocess, "run", side_effect=results):
            outcome = M._extract_pdf_signals_per_page_bounded(
                Path("test.pdf"), per_page_timeout_sec=10, per_pdf_total_budget_sec=60
            )
        self.assertEqual(outcome["status"], "ok")
        self.assertEqual(outcome["pages_ok"], 3)
        self.assertEqual(len(outcome["matchlines"]), 3)
        self.assertEqual(len(outcome["callouts"]), 1)

    def test_08_one_timeout_among_three_pages_yields_two_ok_contributions(self) -> None:
        """The central PE.3 invariant: pathological page 6 doesn't poison the PDF."""
        results = [
            _mk_proc(0, _count_payload(3)),
            _mk_proc(0, _page_payload([{"page": 1, "id": "a"}], [])),
            subprocess.TimeoutExpired(cmd="x", timeout=1),  # page 1 hangs
            _mk_proc(0, _page_payload([{"page": 3, "id": "c"}], [])),
        ]
        with patch.object(M.subprocess, "run", side_effect=results):
            outcome = M._extract_pdf_signals_per_page_bounded(
                Path("test.pdf"), per_page_timeout_sec=10, per_pdf_total_budget_sec=60
            )
        self.assertEqual(outcome["status"], "ok")  # at least one page ok
        self.assertEqual(outcome["pages_ok"], 2)
        self.assertEqual(outcome["pages_timeout"], 1)
        self.assertEqual(len(outcome["matchlines"]), 2)
        match_ids = sorted(m["id"] for m in outcome["matchlines"])
        self.assertEqual(match_ids, ["a", "c"])

    def test_09_all_pages_timeout_yields_all_failed_status(self) -> None:
        """All pages timeout → status='all_failed'; no matchlines."""
        results = [
            _mk_proc(0, _count_payload(2)),
            subprocess.TimeoutExpired(cmd="x", timeout=1),
            subprocess.TimeoutExpired(cmd="x", timeout=1),
        ]
        with patch.object(M.subprocess, "run", side_effect=results):
            outcome = M._extract_pdf_signals_per_page_bounded(
                Path("test.pdf"), per_page_timeout_sec=10, per_pdf_total_budget_sec=60
            )
        self.assertEqual(outcome["status"], "all_failed")
        self.assertEqual(outcome["pages_ok"], 0)
        self.assertEqual(outcome["pages_timeout"], 2)
        self.assertEqual(outcome["matchlines"], [])

    def test_10_count_failed_records_zero_pages(self) -> None:
        """Count subprocess fails → status='count_failed', no pages attempted."""
        results = [
            subprocess.TimeoutExpired(cmd="x", timeout=1),
        ]
        with patch.object(M.subprocess, "run", side_effect=results):
            outcome = M._extract_pdf_signals_per_page_bounded(
                Path("test.pdf"), per_page_timeout_sec=10, per_pdf_total_budget_sec=60
            )
        self.assertEqual(outcome["status"], "count_failed")
        self.assertEqual(outcome["page_count"], 0)
        self.assertEqual(outcome["page_outcomes"], [])
        self.assertEqual(outcome["bounded_by"], "count_failed")

    # ─── D. Page outcome vocabulary (G5, G2 nuances) ─────────────────────

    def test_11_ok_with_zero_text_len_is_status_ok(self) -> None:
        """Image-only page returns text_len=0 with status='ok' (load-bearing for VO)."""
        results = [
            _mk_proc(0, _count_payload(1)),
            _mk_proc(0, _page_payload([], [], text_len=0)),
        ]
        with patch.object(M.subprocess, "run", side_effect=results):
            outcome = M._extract_pdf_signals_per_page_bounded(
                Path("test.pdf"), per_page_timeout_sec=10, per_pdf_total_budget_sec=60
            )
        self.assertEqual(outcome["page_outcomes"][0]["status"], "ok")
        self.assertEqual(outcome["page_outcomes"][0]["text_len"], 0)
        self.assertEqual(outcome["pages_ok"], 1)
        self.assertEqual(outcome["status"], "ok")

    def test_12_subprocess_exit_1_recorded_as_error(self) -> None:
        """Worker exit 1 with payload {ok: false} → status='error'."""
        results = [
            _mk_proc(0, _count_payload(1)),
            _mk_proc(1, _page_error_payload("RuntimeError: simulated")),
        ]
        with patch.object(M.subprocess, "run", side_effect=results):
            outcome = M._extract_pdf_signals_per_page_bounded(
                Path("test.pdf"), per_page_timeout_sec=10, per_pdf_total_budget_sec=60
            )
        self.assertEqual(outcome["page_outcomes"][0]["status"], "error")
        self.assertIn("RuntimeError", outcome["page_outcomes"][0]["error"])
        self.assertEqual(outcome["pages_error"], 1)

    def test_13_unparseable_stdout_recorded_as_unparseable(self) -> None:
        """Worker stdout that isn't JSON → status='unparseable'."""
        results = [
            _mk_proc(0, _count_payload(1)),
            _mk_proc(0, "not valid json at all"),
        ]
        with patch.object(M.subprocess, "run", side_effect=results):
            outcome = M._extract_pdf_signals_per_page_bounded(
                Path("test.pdf"), per_page_timeout_sec=10, per_pdf_total_budget_sec=60
            )
        self.assertEqual(outcome["page_outcomes"][0]["status"], "unparseable")
        self.assertEqual(outcome["pages_error"], 1)

    def test_14_skipped_pages_carry_status_skipped(self) -> None:
        """Pages skipped by circuit breaker → status='skipped'."""
        results = [
            _mk_proc(0, _count_payload(3)),
            _mk_proc(0, _page_payload()),
            # remaining pages skipped via time mock
        ]
        # See test_04 for perf_counter call layout. Here: 3 pages, break after page 0.
        times = [
            0.0,            # pdf_t0
            0.0, 0.1,       # count worker
            1.0, 1.0, 1.1,  # page 0
            70.0,           # page 1 elapsed_pdf check >60 → break
            71.0,           # final elapsed_pdf_ms
        ]
        with patch.object(M.subprocess, "run", side_effect=results):
            with patch.object(M.time, "perf_counter", side_effect=times):
                outcome = M._extract_pdf_signals_per_page_bounded(
                    Path("test.pdf"), per_page_timeout_sec=10, per_pdf_total_budget_sec=60
                )
        skipped = [po for po in outcome["page_outcomes"] if po["status"] == "skipped"]
        self.assertEqual(len(skipped), 2)
        self.assertEqual([po["page_index"] for po in skipped], [1, 2])

    # ─── E. Cache schema v2 (G6, G7) ─────────────────────────────────────

    def test_15_cache_schema_version_is_v2(self) -> None:
        """plan_topology_cache.SCHEMA_VERSION bumped to 'plan-topology-cache-2'."""
        self.assertEqual(M.plan_topology_cache.SCHEMA_VERSION, "plan-topology-cache-2")
        self.assertEqual(M.plan_topology_cache._SCHEMA_VERSION_V2, "plan-topology-cache-2")
        self.assertEqual(M.plan_topology_cache._SCHEMA_VERSION_V1, "plan-topology-cache-1")

    def test_16_cache_write_includes_pdf_outcomes_and_per_page_outcomes(self) -> None:
        """cache_write persists v2 fields when supplied."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            cache_file = Path(tmp) / "sid.json"
            result = M.plan_topology_cache.cache_write(
                cache_file,
                signature="sig",
                topology={0: {"sheet": "A"}},
                plan_count=1,
                compute_duration_ms=100,
                pdf_outcomes=[{"pdf_index": 0, "path": "a.pdf", "status": "ok"}],
                per_page_outcomes=[
                    {"pdf_index": 0, "page_index": 0, "status": "ok", "text_len": 50}
                ],
            )
            self.assertEqual(result, M.plan_topology_cache.CacheWriteResult.WRITTEN)
            payload = json.loads(cache_file.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema"], "plan-topology-cache-2")
            self.assertEqual(payload["generated_by"], "rebuild-isolation/v2")
            self.assertEqual(len(payload["pdf_outcomes"]), 1)
            self.assertEqual(len(payload["per_page_outcomes"]), 1)
            self.assertEqual(payload["pdf_outcomes"][0]["path"], "a.pdf")

    def test_17_cache_write_defaults_outcomes_to_empty(self) -> None:
        """cache_write without v2 kwargs writes empty lists (back-compat)."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            cache_file = Path(tmp) / "sid.json"
            M.plan_topology_cache.cache_write(
                cache_file,
                signature="sig",
                topology={},
                plan_count=0,
                compute_duration_ms=0,
            )
            payload = json.loads(cache_file.read_text(encoding="utf-8"))
            self.assertEqual(payload["pdf_outcomes"], [])
            self.assertEqual(payload["per_page_outcomes"], [])

    def test_18_cache_read_treats_v1_schema_as_miss(self) -> None:
        """A v1 cache file is silently treated as cache miss (graceful upgrade)."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            cache_file = Path(tmp) / "sid.json"
            cache_file.write_text(json.dumps({
                "schema": "plan-topology-cache-1",  # v1
                "session_id": "sid",
                "plan_set_signature": "sig",
                "plan_count": 1,
                "generated_at": "2026-01-01T00:00:00",
                "generated_by": "rebuild-isolation/v1",
                "topology_bytes": 0,
                "compute_duration_ms": 0,
                "topology": {"0": {"sheet": "A"}},
            }), encoding="utf-8")
            result = M.plan_topology_cache.cache_read(cache_file, "sig")
            self.assertIsNone(result)  # MISS_SCHEMA

    def test_19_cache_read_accepts_v2_schema(self) -> None:
        """A v2 cache file with matching signature returns the topology."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            cache_file = Path(tmp) / "sid.json"
            M.plan_topology_cache.cache_write(
                cache_file,
                signature="sig",
                topology={0: {"sheet": "A"}},
                plan_count=1,
                compute_duration_ms=0,
            )
            result = M.plan_topology_cache.cache_read(cache_file, "sig")
            self.assertEqual(result, {0: {"sheet": "A"}})

    # ─── F. Env-var configuration (G12) ──────────────────────────────────

    def test_20_default_per_page_timeout_is_10(self) -> None:
        self.assertEqual(M._pe3_per_page_timeout_sec(), 10)

    def test_21_env_override_changes_per_page_timeout(self) -> None:
        os.environ[_PAGE_ENV] = "5"
        self.assertEqual(M._pe3_per_page_timeout_sec(), 5)

    def test_22_per_pdf_budget_min_is_5(self) -> None:
        """Per-PDF total budget minimum is 5s."""
        os.environ[_BUDGET_ENV] = "1"
        self.assertEqual(M._pe3_per_pdf_total_budget_sec(), 5)

    def test_23_pe2_env_var_falls_back_for_per_pdf_budget(self) -> None:
        """If PE.3 budget env var unset and PE.2 env var set, PE.2 value used."""
        os.environ[_PE2_ENV] = "120"
        self.assertEqual(M._pe3_per_pdf_total_budget_sec(), 120)

    def test_24_orchestrator_invariant_zero_count_under_count_failed(self) -> None:
        """Orchestrator: count_failed PDF contributes no signals, status preserved."""
        with patch.object(M, "_resolve_engineering_plan_pdf_paths", return_value=[Path("x.pdf")]):
            with patch.object(M.subprocess, "run", side_effect=subprocess.TimeoutExpired(cmd="x", timeout=1)):
                with patch.object(M._engineering_plan_parser, "derive_sheet_station_origins", return_value={}):
                    topology, outcomes = M._build_plan_topology_for_session_with_outcomes("sid")
        self.assertEqual(topology, {})
        self.assertEqual(outcomes[0]["status"], "count_failed")
        self.assertEqual(outcomes[0]["pages_ok"], 0)


if __name__ == "__main__":
    unittest.main()
