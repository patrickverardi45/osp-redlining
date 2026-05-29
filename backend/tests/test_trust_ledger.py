"""KMZ Automatic Redline Placement — Trust Ledger tests (core-only).

Locks the read-only proof-grade trust-ledger contract:

- A placed group with a COMPLETE evidence chain (geometry + station + candidate
  /anchor + route-index consistent) classifies ``proven``.
- A non-placed group classifies ``abstained`` with the exact recorded reason.
- A placed group with an INCOMPLETE chain classifies ``missing_proof`` (the
  silent-placement class) and is NEVER reported as ``proven``.
- Route-index evidence and the PSG warning remain SEPARATE signals (a row can be
  route-index ``consistent`` AND carry a PSG ``external_packet_mismatch_possible``
  warning at once).
- The assembler is a pure read-only projection: never mutates input, never
  raises on bad input.

These guard the foundation built in this lane; the PSG inputs reuse the REAL
Brenham CURRENT_PACKET_PRINT_SHEET_INDEX street mappings (no fabricated data).
"""

from __future__ import annotations

import copy
import os
import unittest
from typing import Any, Dict, List

os.environ.setdefault("TRUELINE_JWT_SECRET", "trust-ledger-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "trust-ledger-auth-test-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend.app.core.trust_ledger import assemble_trust_ledger, SCHEMA_VERSION


# Real index-street mappings from CURRENT_PACKET_PRINT_SHEET_INDEX:
#   23 -> CARLEE DR, 24 -> POST OAK CT  (LAWNDALE AVE is NOT among them)
IDX_23_24 = ["CARLEE DR", "POST OAK CT"]

ROUTE_CATALOG = [
    {"route_id": "route_478", "route_name": "E Mansfield St", "length_ft": 4182.0},
    {"route_id": "route_477", "route_name": "Tom Green", "length_ft": 905.0},
    {"route_id": "route_479", "route_name": "Niebuhr", "length_ft": 1200.0},
]


def _proven_entry(**overrides: Any) -> Dict[str, Any]:
    """A placed group with a complete proof chain (mirrors a real fresh-rebuild
    pipeline_diag entry that carries the additive trust fields)."""
    entry: Dict[str, Any] = {
        "group_idx": 8,
        "source_file": "bore_log9.xlsx",
        "group_id": "g8",
        "min_station_ft": 0.0,
        "max_station_ft": 410.0,
        "print_tokens": ["8", "9"],
        "strict_allowed_route_ids": ["route_478", "route_477"],
        "selected_route_id": "route_478",
        "selected_route_name": "E Mansfield St",
        "selected_route_length_ft": 4182.0,
        "selected_combined_score": 0.7213,
        "selected_anchor_reasons": ["length_fit", "anchor_fit"],
        "mapping_summary": {
            "mode": "group_relative",
            "anchor_offset_ft": 0.0,
            "anchored_start_ft": 0.0,
            "anchored_end_ft": 410.0,
        },
        "candidate_rankings_top": [
            {"route_id": "route_478", "score": 0.71, "score_breakdown": {"base_score": 0.6}},
            {"route_id": "route_477", "score": 0.41, "score_breakdown": {}},
        ],
        "render_allowed": True,
        "render_block_reasons": [],
        "stopped_at": None,
    }
    entry.update(overrides)
    return entry


def _abstained_entry(**overrides: Any) -> Dict[str, Any]:
    entry: Dict[str, Any] = {
        "group_idx": 4,
        "source_file": "bore_log5.xlsx",
        "group_id": "g4",
        "min_station_ft": 0.0,
        "max_station_ft": 235.0,
        "print_tokens": ["23", "24"],
        "strict_allowed_route_ids": ["route_477"],
        "selected_route_id": None,
        "selected_route_name": None,
        "render_allowed": False,
        "render_block_reasons": ["same_route_anchor_collision"],
        "stopped_at": "abstained_same_route_anchor_collision",
        "abstain_reason": {"reason": "true_window_overlap", "route_id": "route_477"},
    }
    entry.update(overrides)
    return entry


def _ledger_by_source(result: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {r["source_file"]: r for r in result["rows"]}


class TestProvenClassification(unittest.TestCase):
    def test_complete_chain_is_proven(self) -> None:
        res = assemble_trust_ledger([_proven_entry()], route_catalog=ROUTE_CATALOG)
        row = res["rows"][0]
        self.assertEqual(row["proof_status"], "proven")
        self.assertTrue(row["evidence_chain_complete"])
        self.assertEqual(row["missing_links"], [])
        self.assertIsNone(row["abstain_reason"])
        self.assertEqual(row["route_index_evidence"]["verdict"], "consistent")
        self.assertTrue(row["candidate_summary"]["selected_in_rankings"])
        self.assertTrue(row["mapping_summary"]["mapping_present"])
        self.assertTrue(row["geometry_summary"]["route_in_catalog"])
        self.assertEqual(res["counts"]["proven"], 1)
        self.assertEqual(res["silent_placement_count"], 0)

    def test_rescue_reason_satisfies_candidate_link(self) -> None:
        # Selected route NOT in the candidate_rankings_top, but an explicit V4
        # rescue record justifies it -> still proven.
        entry = _proven_entry(
            candidate_rankings_top=[{"route_id": "route_477", "score": 0.4}],
            location_mismatch_rescue_selected={"reason": "lawndale_allowlist_ratio_gate_pass"},
        )
        res = assemble_trust_ledger([entry], route_catalog=ROUTE_CATALOG)
        row = res["rows"][0]
        self.assertFalse(row["candidate_summary"]["selected_in_rankings"])
        self.assertTrue(row["candidate_summary"]["has_rescue_reason"])
        self.assertEqual(row["proof_status"], "proven")


class TestAbstainedClassification(unittest.TestCase):
    def test_abstain_with_exact_reason(self) -> None:
        res = assemble_trust_ledger([_abstained_entry()], route_catalog=ROUTE_CATALOG)
        row = res["rows"][0]
        self.assertEqual(row["proof_status"], "abstained")
        self.assertEqual(row["abstain_reason"], "abstained_same_route_anchor_collision")
        self.assertFalse(row["evidence_chain_complete"])
        self.assertEqual(res["counts"]["abstained"], 1)

    def test_render_gate_blocked_is_abstained(self) -> None:
        # render_allowed False even though a route was matched -> abstained,
        # reason render_gate_blocked (not proven, not missing_proof).
        entry = _proven_entry(
            source_file="bore_log37.xlsx",
            render_allowed=False,
            render_block_reasons=["no_geometry_output"],
            stopped_at="render_gate_blocked",
        )
        res = assemble_trust_ledger([entry], route_catalog=ROUTE_CATALOG)
        row = res["rows"][0]
        self.assertEqual(row["proof_status"], "abstained")
        self.assertEqual(row["abstain_reason"], "render_gate_blocked")

    def test_no_anchored_hypotheses_is_abstained(self) -> None:
        entry = {
            "group_idx": 1,
            "source_file": "bore_log64.xlsx",
            "group_id": "g1",
            "selected_route_id": None,
            "render_allowed": None,
            "stopped_at": "no_anchored_hypotheses",
        }
        res = assemble_trust_ledger([entry], route_catalog=ROUTE_CATALOG)
        self.assertEqual(res["rows"][0]["proof_status"], "abstained")
        self.assertEqual(res["rows"][0]["abstain_reason"], "no_anchored_hypotheses")


class TestMissingProofClassification(unittest.TestCase):
    def test_missing_mapping_is_missing_proof(self) -> None:
        entry = _proven_entry(mapping_summary={"mode": "group_relative"})  # no anchored_*
        res = assemble_trust_ledger([entry], route_catalog=ROUTE_CATALOG)
        row = res["rows"][0]
        self.assertEqual(row["proof_status"], "missing_proof")
        self.assertIn("mapping_absent", row["missing_links"])
        self.assertFalse(row["evidence_chain_complete"])
        self.assertEqual(res["silent_placement_count"], 1)

    def test_suspect_placement_is_missing_proof_not_proven(self) -> None:
        # Selected route NOT in the print-index allowed set, no rescue record:
        # a would-be silent placement. Must NOT pass as proven.
        entry = _proven_entry(
            selected_route_id="route_999",
            candidate_rankings_top=[{"route_id": "route_999", "score": 0.5}],
        )
        res = assemble_trust_ledger([entry], route_catalog=ROUTE_CATALOG + [{"route_id": "route_999"}])
        row = res["rows"][0]
        self.assertEqual(row["route_index_evidence"]["verdict"], "suspect")
        self.assertEqual(row["proof_status"], "missing_proof")
        self.assertIn("route_index_suspect", row["missing_links"])

    def test_old_session_without_additive_fields_degrades_honestly(self) -> None:
        # An entry from a session rebuilt BEFORE the additive _diag fields: it is
        # placed and route-index consistent, but lacks mapping_summary +
        # candidate_rankings_top -> missing_proof, never fake proven.
        entry = {
            "group_idx": 8,
            "source_file": "bore_log9.xlsx",
            "group_id": None,
            "min_station_ft": 0.0,
            "max_station_ft": 410.0,
            "strict_allowed_route_ids": ["route_478"],
            "selected_route_id": "route_478",
            "selected_route_length_ft": 4182.0,
            "render_allowed": True,
            "stopped_at": None,
        }
        res = assemble_trust_ledger([entry], route_catalog=ROUTE_CATALOG)
        row = res["rows"][0]
        self.assertEqual(row["proof_status"], "missing_proof")
        self.assertIn("mapping_absent", row["missing_links"])
        self.assertIn("no_candidate_or_rescue_justification", row["missing_links"])


class TestRouteIndexAndPsgSeparate(unittest.TestCase):
    def test_consistent_route_index_with_psg_warning_coexist(self) -> None:
        # bore_log72-style: route-index CONSISTENT and PSG possible packet
        # mismatch at the same time. The two must surface independently.
        entry = _proven_entry(source_file="bore_log72.xlsx")
        psg_inputs = {
            "bore_log72.xlsx": {
                "prints": ["23", "24"],
                "station_min_ft": 0.0,
                "station_max_ft": 410.0,
                "notes_streets": ["LAWNDALE AVE"],
                "index_streets": IDX_23_24,
            }
        }
        res = assemble_trust_ledger(
            [entry], route_catalog=ROUTE_CATALOG, plan_sheet_graph_inputs=psg_inputs
        )
        row = res["rows"][0]
        # route-index verdict unaffected by PSG
        self.assertEqual(row["route_index_evidence"]["verdict"], "consistent")
        self.assertEqual(row["proof_status"], "proven")
        # PSG warning present and SEPARATE
        self.assertIsNotNone(row["psg_warning"])
        self.assertEqual(row["psg_warning"]["status"], "external_packet_mismatch_possible")
        self.assertEqual(res["psg_warning_count"], 1)

    def test_no_psg_inputs_means_no_warning(self) -> None:
        res = assemble_trust_ledger([_proven_entry()], route_catalog=ROUTE_CATALOG)
        self.assertIsNone(res["rows"][0]["psg_warning"])
        self.assertEqual(res["psg_warning_count"], 0)


class TestPurityAndSafety(unittest.TestCase):
    def test_does_not_mutate_input(self) -> None:
        entry = _proven_entry()
        snapshot = copy.deepcopy(entry)
        assemble_trust_ledger([entry], route_catalog=ROUTE_CATALOG)
        self.assertEqual(entry, snapshot)

    def test_empty_and_bad_input_safe(self) -> None:
        for bad in (None, [], "nope", 42, {}):
            res = assemble_trust_ledger(bad)  # type: ignore[arg-type]
            self.assertEqual(res["row_count"], 0)
            self.assertEqual(res["rows"], [])
            self.assertEqual(res["schema_version"], SCHEMA_VERSION)

    def test_counts_and_sort_order(self) -> None:
        rows_in = [
            _proven_entry(source_file="bore_log9.xlsx"),
            _abstained_entry(source_file="bore_log5.xlsx"),
            _proven_entry(source_file="bore_log_x.xlsx", mapping_summary={"mode": "x"}),  # missing_proof
        ]
        res = assemble_trust_ledger(rows_in, route_catalog=ROUTE_CATALOG)
        self.assertEqual(res["row_count"], 3)
        self.assertEqual(res["counts"], {"proven": 1, "abstained": 1, "missing_proof": 1})
        self.assertEqual(res["silent_placement_count"], 1)
        # Sort surfaces missing_proof first, then abstained, then proven.
        self.assertEqual(res["rows"][0]["proof_status"], "missing_proof")
        self.assertEqual(res["rows"][-1]["proof_status"], "proven")

    def test_coverage_sanity_summary_projected(self) -> None:
        cov = {
            "schema_version": "coverage-sanity-3",
            "placed_group_count": 31,
            "abstained_group_count": 33,
            "total_groups": 64,
            "same_route_anchor_collisions": [{"route_id": "route_480"}],
            "same_route_window_decisions": [1, 2, 3],
        }
        res = assemble_trust_ledger([_proven_entry()], route_catalog=ROUTE_CATALOG, coverage_sanity=cov)
        summary = res["coverage_sanity_summary"]
        self.assertEqual(summary["placed_group_count"], 31)
        self.assertEqual(summary["abstained_group_count"], 33)
        self.assertEqual(summary["same_route_anchor_collision_count"], 1)
        self.assertEqual(summary["same_route_window_decision_count"], 3)


if __name__ == "__main__":
    unittest.main()
