"""KMZ Hardening — Match Review Queue PSG precision-evidence tests (core-only).

Locks the additive, default-OFF contract for the Brenham Plan Sheet Graph
precision-evidence field on the Match Review Queue:

- The PSG precision filter (`build_review_evidence`) emits ONLY the actionable
  statuses (station_print_disjoint / external_packet_mismatch_possible /
  unknown) and returns None for the noisy ones (within_corridor /
  multi_corridor_span).
- The MRQ builder attaches `plan_sheet_graph_evidence` ONLY when inputs are
  passed AND the status is actionable; otherwise the row is unchanged.
- Flag-OFF analog (no inputs / None / {}) → byte-identical to pre-slice.
- Attaching the field NEVER changes classification, priority, counts, sort,
  or any routing field — the ONLY delta is the added evidence key.

All bore-log values below are the REAL extracted inputs from the 2026-05-28
Brenham PSG telemetry review (no fabricated mappings).
"""

from __future__ import annotations

import copy
import os
import unittest
from typing import Any, Dict, List

os.environ.setdefault("TRUELINE_JWT_SECRET", "mrq-psg-evidence-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "mrq-psg-evidence-auth-test-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend.app.core import brenham_plan_sheet_graph as psg
from backend.app.core.match_review_queue import assemble_match_review_queue


# Real index-street mappings from CURRENT_PACKET_PRINT_SHEET_INDEX:
#   23 -> CARLEE DR, 24 -> POST OAK CT, 25 -> GLENDA BLVD
IDX_23_24 = ["CARLEE DR", "POST OAK CT"]
IDX_24_25 = ["POST OAK CT", "GLENDA BLVD"]


def _queueable(source_file: str, group_id: str = "g") -> Dict[str, Any]:
    """A minimal pipeline_diag entry that classifies as `abstained` so it is
    guaranteed to appear in the review queue (MRQ membership is independent of
    PSG; we only need the row present to test field attachment)."""
    return {
        "source_file": source_file,
        "group_id": group_id,
        "stopped_at": "abstained_location_evidence_mismatch",
        "selected_route_id": None,
        "selected_route_name": None,
        "render_allowed": False,
        "render_block_reasons": ["abstain"],
        "strict_top5": [],
    }


# ── PSG precision filter (build_review_evidence) ────────────────────────────

class TestBuildReviewEvidence(unittest.TestCase):

    def test_station_print_disjoint_bore_log16(self):
        # bore_log16: prints 8,9,10; station 5100-5950 ft (beyond every window).
        ev = psg.build_review_evidence(prints=[8, 9, 10], station_min_ft=5100.0,
                                       station_max_ft=5950.0)
        self.assertIsNotNone(ev)
        self.assertEqual(ev["status"], "station_print_disjoint")
        self.assertEqual(ev["actionability"], "high")
        self.assertEqual(ev["schema_version"], "plan-sheet-graph-evidence-1")
        self.assertEqual(ev["station_range"], [5100.0, 5950.0])
        self.assertEqual(ev["sheets"], [8, 9, 10])
        self.assertTrue(ev["reasons"])
        self.assertTrue(any("outside all sheet windows" in r for r in ev["reasons"]))

    def test_external_packet_mismatch_cheri_bore_log39(self):
        ev = psg.build_review_evidence(prints=[24, 25], station_min_ft=1000.0,
                                       station_max_ft=1441.0,
                                       notes_streets=["CHERI LN"],
                                       index_streets=IDX_24_25)
        self.assertIsNotNone(ev)
        self.assertEqual(ev["status"], "external_packet_mismatch_possible")
        self.assertEqual(ev["actionability"], "high")
        self.assertEqual(ev["notes_streets"], ["CHERI LN"])
        self.assertEqual(ev["index_streets"], IDX_24_25)

    def test_external_packet_mismatch_lawndale_bore_log71(self):
        ev = psg.build_review_evidence(prints=[23, 24], station_min_ft=0.0,
                                       station_max_ft=695.0,
                                       notes_streets=["LAWNDALE AVE"],
                                       index_streets=IDX_23_24)
        self.assertIsNotNone(ev)
        self.assertEqual(ev["status"], "external_packet_mismatch_possible")
        self.assertEqual(ev["actionability"], "high")

    def test_external_packet_mismatch_lawndale_bore_log72(self):
        # bore_log72 is PLACED (rescued_v4) yet PSG flags it — the high-value case.
        ev = psg.build_review_evidence(prints=[23, 24], station_min_ft=750.0,
                                       station_max_ft=1000.0,
                                       notes_streets=["DIFFERENT STREET", "LAWNDALE AVE"],
                                       index_streets=IDX_23_24)
        self.assertIsNotNone(ev)
        self.assertEqual(ev["status"], "external_packet_mismatch_possible")

    def test_unknown_missing_print_bore_log37(self):
        # Print token present but not in [1,30] -> no valid sheets -> unknown.
        ev = psg.build_review_evidence(prints=["0"], station_min_ft=350.0,
                                       station_max_ft=408.0)
        self.assertIsNotNone(ev)
        self.assertEqual(ev["status"], "unknown")
        self.assertEqual(ev["actionability"], "data_quality")
        self.assertEqual(ev["sheets"], [])

    def test_unknown_empty_prints(self):
        ev = psg.build_review_evidence(prints=[])
        self.assertIsNotNone(ev)
        self.assertEqual(ev["status"], "unknown")
        self.assertEqual(ev["actionability"], "data_quality")

    def test_excludes_multi_corridor_span(self):
        # prints 7,14 span corridor [3..9,23,24] + [10,12,13,14]; station inside.
        ev = psg.build_review_evidence(prints=[7, 14], station_min_ft=500.0,
                                       station_max_ft=1000.0)
        self.assertIsNone(ev)

    def test_excludes_within_corridor(self):
        # prints 3,4,5 all in one corridor; station inside the sheet windows.
        ev = psg.build_review_evidence(prints=[3, 4, 5], station_min_ft=1500.0,
                                       station_max_ft=2000.0)
        self.assertIsNone(ev)

    def test_evidence_shape_has_required_keys(self):
        ev = psg.build_review_evidence(prints=[8, 9, 10], station_min_ft=5100.0,
                                       station_max_ft=5950.0)
        for key in ("schema_version", "status", "actionability", "reasons",
                    "prints", "sheets", "corridors", "station_range"):
            self.assertIn(key, ev)

    def test_no_street_keys_when_absent(self):
        ev = psg.build_review_evidence(prints=[8, 9, 10], station_min_ft=5100.0,
                                       station_max_ft=5950.0)
        self.assertNotIn("index_streets", ev)
        self.assertNotIn("notes_streets", ev)

    def test_actionable_status_set_excludes_noisy(self):
        self.assertNotIn("within_corridor", psg.MRQ_ACTIONABLE_STATUSES)
        self.assertNotIn("multi_corridor_span", psg.MRQ_ACTIONABLE_STATUSES)
        self.assertNotIn("outside_corridor_extent", psg.MRQ_ACTIONABLE_STATUSES)
        self.assertIn("station_print_disjoint", psg.MRQ_ACTIONABLE_STATUSES)
        self.assertIn("external_packet_mismatch_possible", psg.MRQ_ACTIONABLE_STATUSES)
        self.assertIn("unknown", psg.MRQ_ACTIONABLE_STATUSES)


# ── MRQ attach / exclude / no-op ────────────────────────────────────────────

class TestAssembleQueuePsgEvidence(unittest.TestCase):

    def setUp(self):
        self.diag: List[Dict[str, Any]] = [
            _queueable("bore_log16.xlsx"),   # -> station_print_disjoint (attach)
            _queueable("bore_log39.xlsx"),   # -> external mismatch (attach)
            _queueable("bore_log72.xlsx"),   # -> external mismatch (attach)
            _queueable("bore_log9.xlsx"),    # -> multi_corridor_span (exclude)
            _queueable("bore_log4.xlsx"),    # -> within_corridor (exclude)
        ]
        self.inputs = {
            "bore_log16.xlsx": {"prints": [8, 9, 10], "station_min_ft": 5100.0,
                                "station_max_ft": 5950.0, "index_streets": None,
                                "notes_streets": None},
            "bore_log39.xlsx": {"prints": [24, 25], "station_min_ft": 1000.0,
                                "station_max_ft": 1441.0, "index_streets": IDX_24_25,
                                "notes_streets": ["CHERI LN"]},
            "bore_log72.xlsx": {"prints": [23, 24], "station_min_ft": 750.0,
                                "station_max_ft": 1000.0, "index_streets": IDX_23_24,
                                "notes_streets": ["DIFFERENT STREET", "LAWNDALE AVE"]},
            "bore_log9.xlsx": {"prints": [7, 14], "station_min_ft": 500.0,
                               "station_max_ft": 1000.0, "index_streets": None,
                               "notes_streets": None},
            "bore_log4.xlsx": {"prints": [3, 4, 5], "station_min_ft": 1500.0,
                               "station_max_ft": 2000.0, "index_streets": None,
                               "notes_streets": None},
        }

    def _row_by_sf(self, queue: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        return {r["source_file"]: r for r in queue["rows"]}

    def test_flag_off_no_field(self):
        q = assemble_match_review_queue(self.diag)
        for r in q["rows"]:
            self.assertNotIn("plan_sheet_graph_evidence", r)

    def test_flag_on_attaches_bore_log16_disjoint(self):
        q = assemble_match_review_queue(self.diag, plan_sheet_graph_inputs=self.inputs)
        ev = self._row_by_sf(q)["bore_log16.xlsx"].get("plan_sheet_graph_evidence")
        self.assertIsNotNone(ev)
        self.assertEqual(ev["status"], "station_print_disjoint")
        self.assertEqual(ev["actionability"], "high")

    def test_flag_on_attaches_bore_log72_external(self):
        q = assemble_match_review_queue(self.diag, plan_sheet_graph_inputs=self.inputs)
        ev = self._row_by_sf(q)["bore_log72.xlsx"].get("plan_sheet_graph_evidence")
        self.assertIsNotNone(ev)
        self.assertEqual(ev["status"], "external_packet_mismatch_possible")

    def test_flag_on_attaches_cheri_lawndale_external(self):
        q = assemble_match_review_queue(self.diag, plan_sheet_graph_inputs=self.inputs)
        ev = self._row_by_sf(q)["bore_log39.xlsx"].get("plan_sheet_graph_evidence")
        self.assertIsNotNone(ev)
        self.assertEqual(ev["status"], "external_packet_mismatch_possible")
        self.assertEqual(ev["notes_streets"], ["CHERI LN"])

    def test_flag_on_excludes_multi_corridor_span(self):
        q = assemble_match_review_queue(self.diag, plan_sheet_graph_inputs=self.inputs)
        self.assertNotIn("plan_sheet_graph_evidence",
                         self._row_by_sf(q)["bore_log9.xlsx"])

    def test_flag_on_excludes_within_corridor(self):
        q = assemble_match_review_queue(self.diag, plan_sheet_graph_inputs=self.inputs)
        self.assertNotIn("plan_sheet_graph_evidence",
                         self._row_by_sf(q)["bore_log4.xlsx"])

    def test_exactly_three_targets_get_field(self):
        q = assemble_match_review_queue(self.diag, plan_sheet_graph_inputs=self.inputs)
        attached = {r["source_file"] for r in q["rows"]
                    if "plan_sheet_graph_evidence" in r}
        self.assertEqual(attached, {"bore_log16.xlsx", "bore_log39.xlsx", "bore_log72.xlsx"})

    def test_none_and_empty_inputs_byte_identical_to_off(self):
        base = assemble_match_review_queue(self.diag)
        self.assertEqual(base, assemble_match_review_queue(self.diag, plan_sheet_graph_inputs=None))
        self.assertEqual(base, assemble_match_review_queue(self.diag, plan_sheet_graph_inputs={}))

    def test_counts_and_classification_unchanged_by_evidence(self):
        off = assemble_match_review_queue(self.diag)
        on = assemble_match_review_queue(self.diag, plan_sheet_graph_inputs=self.inputs)
        self.assertEqual(off["row_count"], on["row_count"])
        self.assertEqual(off["counts_by_status"], on["counts_by_status"])
        self.assertEqual(off["counts_by_priority"], on["counts_by_priority"])

    def test_only_delta_is_the_added_field(self):
        """No routing/selection/render field changes — stripping the evidence
        key from the ON rows reproduces the OFF rows exactly."""
        off = assemble_match_review_queue(self.diag)
        on = assemble_match_review_queue(self.diag, plan_sheet_graph_inputs=self.inputs)
        off_by_sf = self._row_by_sf(off)
        for r in on["rows"]:
            stripped = {k: v for k, v in r.items() if k != "plan_sheet_graph_evidence"}
            self.assertEqual(stripped, off_by_sf[r["source_file"]])

    def test_input_diag_not_mutated(self):
        snapshot = copy.deepcopy(self.diag)
        assemble_match_review_queue(self.diag, plan_sheet_graph_inputs=self.inputs)
        self.assertEqual(self.diag, snapshot)
        for entry in self.diag:
            self.assertNotIn("plan_sheet_graph_evidence", entry)


if __name__ == "__main__":
    unittest.main()
