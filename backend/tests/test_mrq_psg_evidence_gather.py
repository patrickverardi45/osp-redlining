"""KMZ Hardening — MRQ PSG precision-evidence plumbing tests (main-level).

Covers the two main.py seams added for the slice:
- `_trueline_mrq_plan_sheet_graph_evidence_enabled` runtime flag (default OFF).
- `_gather_mrq_plan_sheet_graph_inputs` read-only derivation, which MUST mirror
  the PSG shadow emit seam exactly (prints + station from committed_rows; index
  streets from CURRENT_PACKET_PRINT_SHEET_INDEX; notes from the existing
  location_evidence_mismatch diag).

Imports main.py (needs `backend/` on sys.path so the `app.*` convention
resolves, same as the production entrypoint and the replay scripts).
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "backend"))

os.environ.setdefault("TRUELINE_JWT_SECRET", "mrq-psg-gather-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "mrq-psg-gather-auth-test-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend import main as M
from backend.app.core import brenham_plan_sheet_graph as psg

_FLAG = "TRUELINE_MRQ_PLAN_SHEET_GRAPH_EVIDENCE"


class TestFlagHelper(unittest.TestCase):

    def setUp(self):
        self._saved = os.environ.get(_FLAG)
        os.environ.pop(_FLAG, None)

    def tearDown(self):
        if self._saved is None:
            os.environ.pop(_FLAG, None)
        else:
            os.environ[_FLAG] = self._saved

    def test_default_off(self):
        self.assertFalse(M._trueline_mrq_plan_sheet_graph_evidence_enabled())

    def test_on_variants(self):
        for v in ("1", "true", "TRUE", "yes", "on", " On "):
            os.environ[_FLAG] = v
            self.assertTrue(M._trueline_mrq_plan_sheet_graph_evidence_enabled(), v)

    def test_off_variants(self):
        for v in ("0", "false", "no", "off", "garbage", ""):
            os.environ[_FLAG] = v
            self.assertFalse(M._trueline_mrq_plan_sheet_graph_evidence_enabled(), v)


class TestGatherInputs(unittest.TestCase):

    def test_derives_prints_station_index_notes(self):
        committed_rows = [
            {"source_file": "bore_log39.xlsx", "print": "24,25", "station_ft": 1000.0},
            {"source_file": "bore_log39.xlsx", "print": "24,25", "station_ft": 1441.0},
        ]
        diag = [{
            "source_file": "bore_log39.xlsx",
            "location_evidence_mismatch": {"notes_streets": ["CHERI LN"]},
        }]
        out = M._gather_mrq_plan_sheet_graph_inputs(diag, committed_rows)
        self.assertIn("bore_log39.xlsx", out)
        got = out["bore_log39.xlsx"]
        self.assertEqual(got["prints"], ["24", "25"])
        self.assertEqual(got["station_min_ft"], 1000.0)
        self.assertEqual(got["station_max_ft"], 1441.0)
        # Real index mapping: 24 -> POST OAK CT, 25 -> GLENDA BLVD
        self.assertEqual(got["index_streets"], ["POST OAK CT", "GLENDA BLVD"])
        self.assertEqual(got["notes_streets"], ["CHERI LN"])

    def test_end_to_end_gather_then_evidence_external_mismatch(self):
        committed_rows = [
            {"source_file": "bore_log39.xlsx", "print": "24,25", "station_ft": 1000.0},
            {"source_file": "bore_log39.xlsx", "print": "24,25", "station_ft": 1441.0},
        ]
        diag = [{
            "source_file": "bore_log39.xlsx",
            "location_evidence_mismatch": {"notes_streets": ["CHERI LN"]},
        }]
        inputs = M._gather_mrq_plan_sheet_graph_inputs(diag, committed_rows)
        ev = psg.build_review_evidence(**inputs["bore_log39.xlsx"])
        self.assertIsNotNone(ev)
        self.assertEqual(ev["status"], "external_packet_mismatch_possible")

    def test_skips_file_with_no_print_tokens(self):
        committed_rows = [
            {"source_file": "bore_log_np.xlsx", "print": "", "station_ft": 10.0},
            {"source_file": "bore_log_np.xlsx", "print": None, "station_ft": 20.0},
        ]
        out = M._gather_mrq_plan_sheet_graph_inputs([], committed_rows)
        self.assertNotIn("bore_log_np.xlsx", out)

    def test_empty_inputs_safe(self):
        self.assertEqual(M._gather_mrq_plan_sheet_graph_inputs(None, None), {})
        self.assertEqual(M._gather_mrq_plan_sheet_graph_inputs([], []), {})

    def test_does_not_mutate_inputs(self):
        committed_rows = [{"source_file": "bore_log4.xlsx", "print": "3,4,5", "station_ft": 1500.0}]
        diag = [{"source_file": "bore_log4.xlsx"}]
        import copy
        cr_snap, d_snap = copy.deepcopy(committed_rows), copy.deepcopy(diag)
        M._gather_mrq_plan_sheet_graph_inputs(diag, committed_rows)
        self.assertEqual(committed_rows, cr_snap)
        self.assertEqual(diag, d_snap)


if __name__ == "__main__":
    unittest.main()
