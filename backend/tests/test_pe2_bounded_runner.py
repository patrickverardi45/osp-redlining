"""PE.2 — bounded plan topology runner tests.

All subprocess invocations are mocked. No real PDFs. No real timeout
wallclock. Independent of B-PARSER-FIXTURE-1.

Critical invariant under test: _build_plan_topology_for_session cannot
hang. A subprocess.TimeoutExpired in the worker invocation must result
in the affected PDF being skipped and the function returning bounded.

COMMAND
-------
    python -m pytest backend/tests/test_pe2_bounded_runner.py -v
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
import uuid
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

os.environ.setdefault("TRUELINE_JWT_SECRET", "pe2-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "pe2-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend import main as M


_TIMEOUT_ENV = "TRUELINE_PE2_PER_PDF_TIMEOUT_SEC"


def _mk_proc_result(returncode: int, stdout: str = "", stderr: str = "") -> MagicMock:
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


def _ok_payload(matchlines: List[Dict[str, Any]], callouts: List[Dict[str, Any]]) -> str:
    return json.dumps({
        "ok": True,
        "matchlines": matchlines,
        "callouts": callouts,
        "text_len": 100,
        "elapsed_ms": 100,
        "peak_kb": 500,
    })


# PE.3 helper: count-mode payload returned by the new per-page worker.
def _count_payload(page_count: int) -> str:
    return json.dumps({"ok": True, "page_count": page_count})


class TestPE2BoundedRunner(unittest.TestCase):
    """PE.2 — _build_plan_topology_for_session_with_outcomes behavior."""

    def setUp(self) -> None:
        self._saved_env_timeout = os.environ.pop(_TIMEOUT_ENV, None)

    def tearDown(self) -> None:
        if self._saved_env_timeout is None:
            os.environ.pop(_TIMEOUT_ENV, None)
        else:
            os.environ[_TIMEOUT_ENV] = self._saved_env_timeout

    # ─── A. Timeout returns empty ─────────────────────────────────────────

    def test_01_per_pdf_timeout_returns_empty_topology(self) -> None:
        """All-PDFs-timeout case: function returns {} without hanging."""
        with patch.object(M, "_resolve_engineering_plan_pdf_paths", return_value=[Path("fake.pdf")]):
            with patch.object(
                M.subprocess,
                "run",
                side_effect=subprocess.TimeoutExpired(cmd="x", timeout=1),
            ):
                topology = M._build_plan_topology_for_session("sid_test")
        self.assertEqual(topology, {})

    def test_02_all_pdfs_timeout_outcome_classification(self) -> None:
        """Multiple PDFs all timing out yields outcomes with all 'count_failed'.

        PE.3 NOTE: subprocess.run is now invoked twice per PDF (count +
        extract_page). When TimeoutExpired fires on the FIRST subprocess
        (count), the PDF never proceeds to per-page extraction and is
        recorded as status='count_failed' (PE.3 vocabulary). Under PE.2
        this case was recorded as status='timeout'."""
        paths = [Path("a.pdf"), Path("b.pdf")]
        with patch.object(M, "_resolve_engineering_plan_pdf_paths", return_value=paths):
            with patch.object(
                M.subprocess,
                "run",
                side_effect=subprocess.TimeoutExpired(cmd="x", timeout=1),
            ):
                topology, outcomes = M._build_plan_topology_for_session_with_outcomes("sid_test")
        self.assertEqual(topology, {})
        self.assertEqual(len(outcomes), 2)
        self.assertTrue(all(o["status"] == "count_failed" for o in outcomes))
        self.assertTrue(all(o.get("path") in {"a.pdf", "b.pdf"} for o in outcomes))

    # ─── B. Success path ─────────────────────────────────────────────────

    def test_03_single_pdf_ok_yields_ok_outcome(self) -> None:
        """PE.3: subprocess.run mocks must cover count + extract_page calls."""
        ml = [{"id": "ml_a"}]
        cl = [{"id": "cl_a"}]
        results = [
            _mk_proc_result(0, stdout=_count_payload(1)),       # count → 1 page
            _mk_proc_result(0, stdout=_ok_payload(ml, cl)),     # page 0 → ok
        ]
        with patch.object(M, "_resolve_engineering_plan_pdf_paths", return_value=[Path("a.pdf")]):
            with patch.object(M.subprocess, "run", side_effect=results):
                with patch.object(M._engineering_plan_parser, "derive_sheet_station_origins", return_value={0: {"sheet": "a"}}):
                    topology, outcomes = M._build_plan_topology_for_session_with_outcomes("sid_test")
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(outcomes[0]["status"], "ok")
        self.assertEqual(outcomes[0]["matchlines"], ml)
        self.assertEqual(outcomes[0]["callouts"], cl)
        self.assertEqual(outcomes[0]["pages_ok"], 1)
        self.assertEqual(topology, {0: {"sheet": "a"}})

    def test_04_multiple_pdfs_all_ok_merges_signals(self) -> None:
        """PE.3: each PDF needs count + 1 extract_page subprocess mock."""
        proc_results = [
            _mk_proc_result(0, stdout=_count_payload(1)),                      # a.pdf count
            _mk_proc_result(0, stdout=_ok_payload([{"id": "a"}], [])),         # a.pdf page 0
            _mk_proc_result(0, stdout=_count_payload(1)),                      # b.pdf count
            _mk_proc_result(0, stdout=_ok_payload([{"id": "b"}], [])),         # b.pdf page 0
            _mk_proc_result(0, stdout=_count_payload(1)),                      # c.pdf count
            _mk_proc_result(0, stdout=_ok_payload([{"id": "c"}], [])),         # c.pdf page 0
        ]
        paths = [Path("a.pdf"), Path("b.pdf"), Path("c.pdf")]
        with patch.object(M, "_resolve_engineering_plan_pdf_paths", return_value=paths):
            with patch.object(M.subprocess, "run", side_effect=proc_results):
                with patch.object(M._engineering_plan_parser, "derive_sheet_station_origins") as mock_derive:
                    mock_derive.return_value = {}
                    M._build_plan_topology_for_session_with_outcomes("sid_test")
        merged_ml = mock_derive.call_args[0][0]
        self.assertEqual(len(merged_ml), 3)
        self.assertEqual(sorted(m["id"] for m in merged_ml), ["a", "b", "c"])

    # ─── C. Partial extraction (LOAD-BEARING gate) ───────────────────────

    def test_05_partial_success_yields_partial_topology(self) -> None:
        """PE.3: PDF_0 ok, PDF_1 count times out, PDF_2 ok. Only OK PDFs contribute."""
        proc_results = [
            _mk_proc_result(0, stdout=_count_payload(1)),                     # a.pdf count
            _mk_proc_result(0, stdout=_ok_payload([{"id": "a"}], [])),        # a.pdf page 0
            subprocess.TimeoutExpired(cmd="x", timeout=1),                    # b.pdf count fails
            _mk_proc_result(0, stdout=_count_payload(1)),                     # c.pdf count
            _mk_proc_result(0, stdout=_ok_payload([{"id": "c"}], [])),        # c.pdf page 0
        ]
        paths = [Path("a.pdf"), Path("b.pdf"), Path("c.pdf")]
        with patch.object(M, "_resolve_engineering_plan_pdf_paths", return_value=paths):
            with patch.object(M.subprocess, "run", side_effect=proc_results):
                with patch.object(M._engineering_plan_parser, "derive_sheet_station_origins") as mock_derive:
                    mock_derive.return_value = {}
                    topology, outcomes = M._build_plan_topology_for_session_with_outcomes("sid_test")
        self.assertEqual(len(outcomes), 3)
        statuses = [o["status"] for o in outcomes]
        # PE.3: count-subprocess timeout classifies the PDF as 'count_failed'
        # (PDF couldn't be opened). Under PE.2 this was 'timeout'.
        self.assertEqual(statuses, ["ok", "count_failed", "ok"])
        merged_ml = mock_derive.call_args[0][0]
        self.assertEqual(sorted(m["id"] for m in merged_ml), ["a", "c"])
        self.assertEqual(outcomes[1].get("path"), "b.pdf")

    def test_06_partial_success_classification_in_rebuild(self) -> None:
        """Partial outcome in rebuild path produces cache_miss_computed_partial."""
        sid = f"pe2_int_{uuid.uuid4().hex[:12]}"
        # Set up STATE for the rebuild
        saved_state = dict(M.STATE)
        try:
            M.STATE.clear()
            M.STATE.update({
                "committed_rows": [],
                "route_catalog": [],
                "_session_id_hint": sid,
                "engineering_plans": [],
            })
            os.environ["TRUELINE_PLAN_PDF_PARSE"] = "1"
            saved_kill = os.environ.pop("TRUELINE_REBUILD_CACHE_DISABLE", None)
            try:
                with patch.object(
                    M,
                    "_build_plan_topology_for_session_with_outcomes",
                    return_value=({}, [
                        {"status": "ok", "path": "a.pdf", "elapsed_ms": 50, "matchlines": [], "callouts": []},
                        {"status": "timeout", "path": "b.pdf", "elapsed_ms": 30000},
                    ]),
                ):
                    with self.assertLogs(level="INFO") as cm:
                        M._rebuild_field_data_outputs(scope=M.RebuildScope.FULL)
                self.assertTrue(
                    any("topology_source=cache_miss_computed_partial" in line for line in cm.output),
                    f"expected cache_miss_computed_partial in logs, got: {cm.output}",
                )
            finally:
                os.environ.pop("TRUELINE_PLAN_PDF_PARSE", None)
                if saved_kill is not None:
                    os.environ["TRUELINE_REBUILD_CACHE_DISABLE"] = saved_kill
        finally:
            M.STATE.clear()
            M.STATE.update(saved_state)
            cache_file = M.plan_topology_cache.resolve_cache_file(sid, M.UPLOADS_DIR)
            try:
                if cache_file.exists():
                    cache_file.unlink()
            except OSError:
                pass

    def test_07_all_timeout_classification_in_rebuild(self) -> None:
        """All-PDF-timeout in rebuild path produces cache_miss_compute_timeout."""
        sid = f"pe2_int_{uuid.uuid4().hex[:12]}"
        saved_state = dict(M.STATE)
        try:
            M.STATE.clear()
            M.STATE.update({
                "committed_rows": [],
                "route_catalog": [],
                "_session_id_hint": sid,
                "engineering_plans": [],
            })
            os.environ["TRUELINE_PLAN_PDF_PARSE"] = "1"
            saved_kill = os.environ.pop("TRUELINE_REBUILD_CACHE_DISABLE", None)
            try:
                with patch.object(
                    M,
                    "_build_plan_topology_for_session_with_outcomes",
                    return_value=({}, [
                        {"status": "timeout", "path": "a.pdf", "elapsed_ms": 30000},
                        {"status": "timeout", "path": "b.pdf", "elapsed_ms": 30000},
                    ]),
                ):
                    with self.assertLogs(level="INFO") as cm:
                        M._rebuild_field_data_outputs(scope=M.RebuildScope.FULL)
                self.assertTrue(
                    any("topology_source=cache_miss_compute_timeout" in line for line in cm.output),
                    f"expected cache_miss_compute_timeout in logs, got: {cm.output}",
                )
            finally:
                os.environ.pop("TRUELINE_PLAN_PDF_PARSE", None)
                if saved_kill is not None:
                    os.environ["TRUELINE_REBUILD_CACHE_DISABLE"] = saved_kill
        finally:
            M.STATE.clear()
            M.STATE.update(saved_state)
            cache_file = M.plan_topology_cache.resolve_cache_file(sid, M.UPLOADS_DIR)
            try:
                if cache_file.exists():
                    cache_file.unlink()
            except OSError:
                pass

    # ─── D. Error and unparseable ─────────────────────────────────────────

    def test_08_worker_exception_recorded_as_error_status(self) -> None:
        """PE.3: count returns ok then extract_page exit 1 → per-page status='error'.

        Per-PDF aggregate becomes 'all_failed' when pages_ok==0 (no ok pages
        contributed signals)."""
        err_payload = json.dumps({"ok": False, "error": "RuntimeError: simulated"})
        results = [
            _mk_proc_result(0, stdout=_count_payload(1)),  # count ok
            _mk_proc_result(1, stdout=err_payload),         # page 0 error
        ]
        with patch.object(M, "_resolve_engineering_plan_pdf_paths", return_value=[Path("a.pdf")]):
            with patch.object(M.subprocess, "run", side_effect=results):
                with patch.object(M._engineering_plan_parser, "derive_sheet_station_origins", return_value={}):
                    _, outcomes = M._build_plan_topology_for_session_with_outcomes("sid_test")
        self.assertEqual(len(outcomes), 1)
        # Per-PDF aggregate: all_failed (no pages ok).
        self.assertEqual(outcomes[0]["status"], "all_failed")
        # Per-page: error class with the RuntimeError string preserved.
        self.assertEqual(outcomes[0]["pages_error"], 1)
        self.assertEqual(outcomes[0]["page_outcomes"][0]["status"], "error")
        self.assertIn("RuntimeError", outcomes[0]["page_outcomes"][0]["error"])

    def test_09_worker_unparseable_output_recorded_as_unparseable(self) -> None:
        """PE.3: extract_page worker emitting non-JSON → per-page status='unparseable'."""
        results = [
            _mk_proc_result(0, stdout=_count_payload(1)),         # count ok
            _mk_proc_result(0, stdout="not valid json at all"),   # page 0 unparseable
        ]
        with patch.object(M, "_resolve_engineering_plan_pdf_paths", return_value=[Path("a.pdf")]):
            with patch.object(M.subprocess, "run", side_effect=results):
                with patch.object(M._engineering_plan_parser, "derive_sheet_station_origins", return_value={}):
                    _, outcomes = M._build_plan_topology_for_session_with_outcomes("sid_test")
        # Per-PDF aggregate: all_failed (no ok pages).
        self.assertEqual(outcomes[0]["status"], "all_failed")
        # Per-page: unparseable status preserved.
        self.assertEqual(outcomes[0]["page_outcomes"][0]["status"], "unparseable")
        # 'unparseable' counts toward pages_error per PE.3 aggregation.
        self.assertEqual(outcomes[0]["pages_error"], 1)

    def test_10_ok_with_zero_chars_is_not_failure(self) -> None:
        """OK extraction with empty matchlines+callouts is valid (image-only page)."""
        results = [
            _mk_proc_result(0, stdout=_count_payload(1)),
            _mk_proc_result(0, stdout=_ok_payload([], [])),
        ]
        with patch.object(M, "_resolve_engineering_plan_pdf_paths", return_value=[Path("a.pdf")]):
            with patch.object(M.subprocess, "run", side_effect=results):
                with patch.object(M._engineering_plan_parser, "derive_sheet_station_origins", return_value={}):
                    _, outcomes = M._build_plan_topology_for_session_with_outcomes("sid_test")
        self.assertEqual(outcomes[0]["status"], "ok")  # pages_ok >= 1 → ok
        self.assertEqual(outcomes[0]["pages_ok"], 1)
        self.assertEqual(outcomes[0]["matchlines"], [])
        self.assertEqual(outcomes[0]["callouts"], [])

    # ─── E. No PDFs edge case ─────────────────────────────────────────────

    def test_11_empty_plan_set_returns_empty_no_subprocess(self) -> None:
        with patch.object(M, "_resolve_engineering_plan_pdf_paths", return_value=[]):
            with patch.object(M.subprocess, "run") as mock_run:
                topology, outcomes = M._build_plan_topology_for_session_with_outcomes("sid_test")
        self.assertEqual(topology, {})
        self.assertEqual(outcomes, [])
        self.assertEqual(mock_run.call_count, 0)

    # ─── F. Wallclock budget helper ──────────────────────────────────────

    def test_12_default_timeout_is_60(self) -> None:
        os.environ.pop(_TIMEOUT_ENV, None)
        self.assertEqual(M._pe2_per_pdf_timeout_sec(), 60)

    def test_13_env_var_override_changes_timeout(self) -> None:
        os.environ[_TIMEOUT_ENV] = "15"
        self.assertEqual(M._pe2_per_pdf_timeout_sec(), 15)

    def test_14_invalid_env_var_falls_back_to_default(self) -> None:
        os.environ[_TIMEOUT_ENV] = "not_a_number"
        self.assertEqual(M._pe2_per_pdf_timeout_sec(), 60)

    def test_15_min_timeout_is_one_second(self) -> None:
        os.environ[_TIMEOUT_ENV] = "0"
        self.assertEqual(M._pe2_per_pdf_timeout_sec(), 1)

    # ─── G. Worker module ────────────────────────────────────────────────

    def test_16_worker_file_exists_in_app_core(self) -> None:
        worker_path = Path(M.__file__).resolve().parent / "app" / "core" / "plan_topology_pdf_worker.py"
        self.assertTrue(worker_path.is_file())

    def test_17_worker_handles_missing_args_gracefully(self) -> None:
        worker_path = Path(M.__file__).resolve().parent / "app" / "core" / "plan_topology_pdf_worker.py"
        result = subprocess.run(
            [sys.executable, str(worker_path)],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 1)
        last_line = result.stdout.strip().splitlines()[-1]
        payload = json.loads(last_line)
        self.assertFalse(payload["ok"])
        self.assertIn("usage", payload["error"].lower())

    def test_18_worker_emits_error_for_missing_pdf(self) -> None:
        worker_path = Path(M.__file__).resolve().parent / "app" / "core" / "plan_topology_pdf_worker.py"
        result = subprocess.run(
            [sys.executable, str(worker_path), "C:/this/does/not/exist.pdf"],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 1)
        last_line = result.stdout.strip().splitlines()[-1]
        payload = json.loads(last_line)
        self.assertFalse(payload["ok"])


if __name__ == "__main__":
    unittest.main()
