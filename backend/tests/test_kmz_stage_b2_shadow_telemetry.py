"""KMZ Hardening Stage B2b — shadow-telemetry writer + flag-gate tests.

Verifies:
  - row schema + bounded sizes
  - append succeeds + creates file
  - flag default OFF
  - emission seam in main is a no-op when flag OFF (no file written, no
    pipeline output change, no STATE mutation, no signal-dict mutation)
  - emission seam writes a row when flag ON with a real PDF fixture
  - existing PI.4A `derive_print_to_sheet_index` byte-identity preserved
    regardless of B2b flag state (B2b adds NEW functions; does not touch
    existing signatures)
"""

from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from typing import Any, Dict, List

os.environ.setdefault("TRUELINE_JWT_SECRET", "stage-b2-shadow-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "stage-b2-shadow-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend import main as M
from backend.app.core import kmz_stage_b2_shadow_telemetry as TEL
from backend.app.core import kmz_stage_b2_streets as B2

_B2_SHADOW_ENV = "TRUELINE_KMZ_STAGE_B2_STREETS_SHADOW"


class TestBuildRow(unittest.TestCase):
    """Telemetry row schema."""

    def test_schema_version_set(self):
        row = TEL.build_row(
            session_id="sess_a",
            plan_id="plan_a",
            source_file="x.pdf",
            per_page_records=[],
            sheet_to_streets={},
            per_token_comparisons=[],
            n_pages_total=0,
            n_pages_reverse_skipped=0,
            title_block_streets=[],
        )
        self.assertEqual(row["schema_version"], TEL.SCHEMA_VERSION)
        # B2b shipped "kmz-stage-b2-shadow-1"; B2b.1 bumps to v2 because
        # the per_page projection adds tier_a_count + length_cap_drops +
        # filler_ratio_drops + single_letter_drops + reverse_text_indicators.
        # All pre-existing v1 fields preserved.
        self.assertEqual(row["schema_version"], "kmz-stage-b2-shadow-2")

    def test_confidence_tally(self):
        comparisons = [
            {"token": "1", "confidence": "high", "agreement": "x",
             "derived_streets": [], "constant_streets": []},
            {"token": "2", "confidence": "abstain", "agreement": "y",
             "derived_streets": [], "constant_streets": []},
            {"token": "3", "confidence": "abstain", "agreement": "y",
             "derived_streets": [], "constant_streets": []},
        ]
        row = TEL.build_row(
            session_id="s", plan_id="p", source_file="x",
            per_page_records=[], sheet_to_streets={},
            per_token_comparisons=comparisons,
            n_pages_total=0, n_pages_reverse_skipped=0, title_block_streets=[],
        )
        self.assertEqual(row["confidence_tally"]["high"], 1)
        self.assertEqual(row["confidence_tally"]["abstain"], 2)
        self.assertEqual(row["confidence_tally"]["low"], 0)

    def test_per_page_compacted(self):
        # Inputs include large fields; compact projection only keeps counts.
        per_page = [{
            "page": 1,
            "raw_candidates": ["A", "B", "C"],
            "filtered_streets": ["A", "B"],
            "final_streets": ["A"],
            "reverse_text_skipped": False,
            "construction_leader_drops": 1,
            "numeric_prefix_strips": 0,
            "frequency_filter_drops": 0,
            "title_block_drops": 0,
            "title_block_subtracted": True,
        }]
        row = TEL.build_row(
            session_id="s", plan_id="p", source_file="x",
            per_page_records=per_page, sheet_to_streets={1: ["A"]},
            per_token_comparisons=[],
            n_pages_total=1, n_pages_reverse_skipped=0, title_block_streets=[],
        )
        page = row["per_page"][0]
        self.assertEqual(page["page"], 1)
        self.assertEqual(page["raw_candidate_count"], 3)
        self.assertEqual(page["filtered_count"], 2)
        self.assertEqual(page["final_count"], 1)
        self.assertEqual(page["construction_leader_drops"], 1)
        self.assertEqual(page["final_streets"], ["A"])

    def test_json_serializable(self):
        row = TEL.build_row(
            session_id="s", plan_id="p", source_file="x",
            per_page_records=[],
            sheet_to_streets={5: ["E STONE ST"]},
            per_token_comparisons=[],
            n_pages_total=0, n_pages_reverse_skipped=0, title_block_streets=[],
        )
        # Must serialize without raising.
        s = json.dumps(row)
        self.assertIn("kmz-stage-b2-shadow-2", s)


class TestAppendShadowRow(unittest.TestCase):
    """Write primitive."""

    def setUp(self) -> None:
        self.tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jsonl")
        self.tmp.close()
        os.remove(self.tmp.name)
        self.path = Path(self.tmp.name)

    def tearDown(self) -> None:
        if self.path.exists():
            self.path.unlink()

    def test_append_creates_and_writes(self):
        row = TEL.build_row(
            session_id="s", plan_id="p", source_file="x",
            per_page_records=[], sheet_to_streets={},
            per_token_comparisons=[],
            n_pages_total=0, n_pages_reverse_skipped=0, title_block_streets=[],
        )
        ok = TEL.append_shadow_row(row, target_path=self.path)
        self.assertTrue(ok)
        self.assertTrue(self.path.exists())
        text = self.path.read_text(encoding="utf-8")
        self.assertIn("kmz-stage-b2-shadow-2", text)
        self.assertTrue(text.endswith("\n"))

    def test_append_multiple_rows_are_jsonl(self):
        for i in range(3):
            row = TEL.build_row(
                session_id=f"s_{i}", plan_id="p", source_file="x",
                per_page_records=[], sheet_to_streets={},
                per_token_comparisons=[],
                n_pages_total=0, n_pages_reverse_skipped=0, title_block_streets=[],
            )
            TEL.append_shadow_row(row, target_path=self.path)
        lines = self.path.read_text(encoding="utf-8").strip().split("\n")
        self.assertEqual(len(lines), 3)
        for line in lines:
            # Each line must be a valid JSON object.
            parsed = json.loads(line)
            self.assertEqual(parsed["schema_version"], "kmz-stage-b2-shadow-2")

    def test_append_returns_false_on_bad_row(self):
        self.assertFalse(TEL.append_shadow_row(None, target_path=self.path))  # type: ignore[arg-type]
        self.assertFalse(TEL.append_shadow_row({"x": 1}, target_path=None))

    def test_size_trigger_trim(self):
        # Generate enough rows to exceed a very small trim trigger; then
        # verify only the most recent rows survive.
        small_trim = 1024  # 1 KiB
        small_max = 3
        for i in range(50):
            row = TEL.build_row(
                session_id=f"sess_{i}_{uuid.uuid4().hex[:8]}",
                plan_id="p", source_file="x" * 200,
                per_page_records=[], sheet_to_streets={},
                per_token_comparisons=[],
                n_pages_total=0, n_pages_reverse_skipped=0, title_block_streets=[],
            )
            TEL.append_shadow_row(
                row, target_path=self.path,
                max_rows=small_max, trim_trigger_bytes=small_trim,
            )
        lines = self.path.read_text(encoding="utf-8").strip().split("\n")
        # Trim is best-effort post-write; the final-file row count should be
        # bounded close to small_max (within one append window).
        self.assertLessEqual(len(lines), small_max + 1)


class TestB2ShadowFlagDefaultOff(unittest.TestCase):
    """Stage B2b shadow flag must default OFF."""

    def setUp(self) -> None:
        self._saved = os.environ.pop(_B2_SHADOW_ENV, None)

    def tearDown(self) -> None:
        os.environ.pop(_B2_SHADOW_ENV, None)
        if self._saved is not None:
            os.environ[_B2_SHADOW_ENV] = self._saved

    def test_flag_helper_defaults_off(self):
        self.assertNotIn(_B2_SHADOW_ENV, os.environ)
        self.assertFalse(M._trueline_kmz_stage_b2_streets_shadow_enabled())

    def test_flag_helper_true_on_yes(self):
        os.environ[_B2_SHADOW_ENV] = "yes"
        try:
            self.assertTrue(M._trueline_kmz_stage_b2_streets_shadow_enabled())
        finally:
            del os.environ[_B2_SHADOW_ENV]


class TestB2EmissionSeamFlagOff(unittest.TestCase):
    """When flag OFF, the emission seam must be a no-op:
       - no shadow file written
       - no STATE mutation
       - input plan_signals not mutated"""

    def setUp(self) -> None:
        self._saved = os.environ.pop(_B2_SHADOW_ENV, None)
        # Ensure flag is OFF for this suite.
        os.environ.pop(_B2_SHADOW_ENV, None)
        # Snapshot the shadow file path's existing content (if any) so we
        # can assert no new write occurs.
        self._existing_path = M.KMZ_STAGE_B2_SHADOW_PATH
        self._pre_state = (
            self._existing_path.exists(),
            self._existing_path.stat().st_size if self._existing_path.exists() else 0,
        )

    def tearDown(self) -> None:
        if self._saved is not None:
            os.environ[_B2_SHADOW_ENV] = self._saved

    def _shadow_state(self):
        return (
            self._existing_path.exists(),
            self._existing_path.stat().st_size if self._existing_path.exists() else 0,
        )

    def test_seam_noop_when_flag_off(self):
        # Confirm flag is OFF.
        self.assertFalse(M._trueline_kmz_stage_b2_streets_shadow_enabled())

        # Snapshot STATE keys we care about — emission seam must not touch them.
        state_snap = copy.deepcopy(dict(M.STATE))

        plan_records: List[Dict[str, Any]] = [
            {"plan_id": "p1", "original_filename": "test.pdf"},
        ]
        plan_signals: List[Dict[str, Any]] = [
            {"plan_id": "p1", "print_tokens": ["1", "2"]},
        ]
        plan_signals_snap = copy.deepcopy(plan_signals)

        M._emit_kmz_stage_b2_streets_shadow_if_enabled(
            "sess_test_offflag", plan_records, plan_signals,
        )

        # No new shadow row written.
        self.assertEqual(self._shadow_state(), self._pre_state)
        # plan_signals not mutated.
        self.assertEqual(plan_signals, plan_signals_snap)
        # STATE not mutated.
        self.assertEqual(dict(M.STATE), state_snap)


class TestPI4ADerivePrintToSheetIndexUnchanged(unittest.TestCase):
    """B2b must NOT touch the existing PI.4A `derive_print_to_sheet_index`
    function signature or behavior. The new B2b `derive_print_to_sheet_streets`
    lives alongside it. This test pins the legacy contract.
    """

    def test_legacy_pi4a_byte_identity(self):
        from backend.app.services.engineering_plan_parser import (
            derive_print_to_sheet_index,
        )
        out = derive_print_to_sheet_index({1, 3, 5}, ["1", "3", "5", "99"])
        # Existing contract: each present token -> [int]; absent -> None;
        # non-digit -> None.
        self.assertEqual(out["1"], [1])
        self.assertEqual(out["3"], [3])
        self.assertEqual(out["5"], [5])
        self.assertIsNone(out["99"])

    def test_b2b_new_function_is_alongside(self):
        # New B2b function must exist with matching shape (Dict[str, Optional[List[str]]]).
        out = B2.derive_print_to_sheet_streets({1: ["E STONE ST"]}, ["1", "999"])
        self.assertEqual(out["1"], ["E STONE ST"])
        self.assertIsNone(out["999"])


class TestStageAStillEmitsHardcodedBrenham(unittest.TestCase):
    """B2b must not change Stage A's print_sheet_index_source value space.
    Specifically, when B2b shadow flag is ON, `_print_sheet_hints` still
    emits `hardcoded_brenham` for resolved Brenham tokens — B2c (LIVE
    activation) is the stage that would flip this to `pi4a_derived`, and
    B2c is explicitly not started.
    """

    def setUp(self) -> None:
        self._saved = os.environ.pop(_B2_SHADOW_ENV, None)

    def tearDown(self) -> None:
        os.environ.pop(_B2_SHADOW_ENV, None)
        if self._saved is not None:
            os.environ[_B2_SHADOW_ENV] = self._saved

    def test_stage_a_source_unchanged_with_b2b_shadow_flag_on(self):
        os.environ[_B2_SHADOW_ENV] = "1"
        try:
            meta = M._print_sheet_hints(["1"])
            self.assertEqual(meta["print_sheet_index_source"], "hardcoded_brenham")
        finally:
            del os.environ[_B2_SHADOW_ENV]


class TestB2EmissionSeamFlagOnAgainstBrenhamPDF(unittest.TestCase):
    """Integration-ish: emit a row against a real Brenham PDF when the flag
    is ON. Verifies a single row is appended and is JSON-deserializable.
    Skipped when the Brenham fixture is not present locally."""

    BRENHAM_PDF = Path(
        r"C:\Nova\knowledge\TrueLine-Wiki\raw\trueline\engineering-plans"
        r"\brenham\BRENHAM PH5 - 18-02-2026.pdf"
    )

    def setUp(self) -> None:
        if not self.BRENHAM_PDF.exists():
            self.skipTest("Brenham fixture PDF not present locally")
        self._saved = os.environ.pop(_B2_SHADOW_ENV, None)
        # Redirect shadow path to a temp file for isolation.
        self._tmp_path = Path(tempfile.gettempdir()) / f"kmz_b2_test_{uuid.uuid4().hex}.jsonl"
        self._orig_shadow_path = M.KMZ_STAGE_B2_SHADOW_PATH
        M.KMZ_STAGE_B2_SHADOW_PATH = self._tmp_path

    def tearDown(self) -> None:
        M.KMZ_STAGE_B2_SHADOW_PATH = self._orig_shadow_path
        if self._tmp_path.exists():
            self._tmp_path.unlink()
        if self._saved is not None:
            os.environ[_B2_SHADOW_ENV] = self._saved
        else:
            os.environ.pop(_B2_SHADOW_ENV, None)

    def test_emission_writes_one_row_per_pdf(self):
        os.environ[_B2_SHADOW_ENV] = "1"

        # Build a fake plan record + signals pair that points at the real
        # Brenham PDF and a couple of observed print tokens. The emission
        # seam internally calls `_load_engineering_plan_index` to get
        # `stored_path` — we bypass that by monkey-patching `_load_engineering_plan_index`
        # and `_engineering_plan_record_matches_session` for this test.
        fake_record = {
            "plan_id": "test_plan_b2_brenham",
            "session_id": "sess_b2_brenham_test",
            "original_filename": "BRENHAM PH5 - 18-02-2026.pdf",
            "stored_path": str(self.BRENHAM_PDF),
        }
        plan_records_public = [{"plan_id": "test_plan_b2_brenham"}]
        plan_signals = [{
            "plan_id": "test_plan_b2_brenham",
            "print_tokens": ["1", "5", "999"],
        }]

        orig_load = M._load_engineering_plan_index
        orig_match = M._engineering_plan_record_matches_session
        M._load_engineering_plan_index = lambda: {"plans": [fake_record]}
        M._engineering_plan_record_matches_session = (
            lambda rec, sid: rec.get("session_id") == sid
        )
        try:
            M._emit_kmz_stage_b2_streets_shadow_if_enabled(
                "sess_b2_brenham_test",
                plan_records_public,
                plan_signals,
            )
        finally:
            M._load_engineering_plan_index = orig_load
            M._engineering_plan_record_matches_session = orig_match

        # Exactly one row should have been written.
        self.assertTrue(self._tmp_path.exists())
        lines = [
            l for l in self._tmp_path.read_text(encoding="utf-8").splitlines() if l.strip()
        ]
        self.assertEqual(len(lines), 1)
        row = json.loads(lines[0])
        self.assertEqual(row["schema_version"], "kmz-stage-b2-shadow-2")
        self.assertEqual(row["session_id"], "sess_b2_brenham_test")
        self.assertEqual(row["plan_id"], "test_plan_b2_brenham")
        # Should have iterated all 4 Brenham pages.
        self.assertGreater(row["n_pages_total"], 0)
        # Per-token comparisons cover observed tokens.
        observed = {c["token"] for c in row["per_token_comparisons"]}
        self.assertIn("1", observed)
        self.assertIn("5", observed)
        self.assertIn("999", observed)


if __name__ == "__main__":
    unittest.main()
