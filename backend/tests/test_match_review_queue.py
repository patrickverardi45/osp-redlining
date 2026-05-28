"""KMZ Matching Trust Slice B — match_review_queue tests.

Verifies the pure projection helper assembles a prioritized operator-review
queue from synthetic `pipeline_diag` rows. Locks the additive contract:
- ABSTAIN + ambiguity-not-resolved rank HIGH
- collision_resolved + placed_with_low_confidence rank MEDIUM
- rescued_v4 ranks LOW
- placed_normal is excluded entirely
- Stage A `print_sheet_index_source` surfaces in evidence_summary
- Empty / non-list input → empty queue (safe-failure)
- Input pipeline_diag is never mutated
"""

from __future__ import annotations

import copy
import os
import unittest
from typing import Any, Dict, List

os.environ.setdefault("TRUELINE_JWT_SECRET", "match-review-queue-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "match-review-queue-auth-test-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend.app.core.match_review_queue import (
    LOW_CONFIDENCE_SCORE_FLOOR,
    SCHEMA_VERSION,
    assemble_match_review_queue,
)


def _diag_abstained(source_file: str = "abstain.xlsx") -> Dict[str, Any]:
    """A bore-log group that abstained via location-mismatch."""
    return {
        "source_file": source_file,
        "group_id": "g_abstained",
        "stopped_at": "abstained_location_evidence_mismatch",
        "abstain_reason": {
            "reason": "notes_streets_not_in_filter",
            "notes_streets": ["CHERI LN"],
        },
        "selected_route_id": None,
        "selected_route_name": None,
        "render_allowed": False,
        "render_block_reasons": ["abstain_location_evidence_mismatch"],
        "strict_top5": [
            {"route_id": "route_478", "route_name": "E Mansfield St",
             "score": 0.82, "route_length_ft": 500.0},
            {"route_id": "route_476", "route_name": "E Stone St",
             "score": 0.71, "route_length_ft": 480.0},
        ],
        "print_filter": {
            "applied": True,
            "print_tokens": ["23"],
            "sheet_numbers": [23],
            "street_hints": ["CARLEE DR"],
            "allowed_route_ids": ["route_478"],
            "print_sheet_index_source": "hardcoded_brenham",
        },
        "location_evidence_mismatch": {
            "notes_streets": ["CHERI LN"],
            "filter_streets": ["CARLEE DR"],
            "severity": "REVIEW",
        },
        "ambiguity_resolution_status": "not_applicable",
    }


def _diag_ambiguous(source_file: str = "ambig.xlsx") -> Dict[str, Any]:
    """A group whose ambiguity wasn't resolved by plan signals."""
    return {
        "source_file": source_file,
        "group_id": "g_ambig",
        "stopped_at": None,
        "selected_route_id": "route_479",
        "selected_route_name": "Niebuhr St",
        "render_allowed": False,
        "render_block_reasons": ["chain_gate:multiple_possible_chain_links"],
        "strict_top5": [
            {"route_id": "route_479", "route_name": "Niebuhr St",
             "score": 0.62, "route_length_ft": 612.0},
            {"route_id": "route_480", "route_name": "Niebuhr St (south)",
             "score": 0.60, "route_length_ft": 605.0},
        ],
        "print_filter": {
            "applied": True,
            "print_tokens": ["5"],
            "sheet_numbers": [5],
            "street_hints": ["NIEBUHR ST"],
            "allowed_route_ids": ["route_479", "route_480"],
            "print_sheet_index_source": "hardcoded_brenham",
        },
        "ambiguity_resolution_status": "still_review_required",
    }


def _diag_collision_resolved(source_file: str = "coll.xlsx") -> Dict[str, Any]:
    """A group where V2 alternate-search picked a non-colliding alternate."""
    return {
        "source_file": source_file,
        "group_id": "g_coll",
        "stopped_at": None,
        "selected_route_id": "route_477",
        "selected_route_name": "E Tom Green St",
        "render_allowed": True,
        "render_block_reasons": [],
        "strict_top5": [
            {"route_id": "route_478", "route_name": "E Mansfield St",
             "score": 0.85, "route_length_ft": 500.0},
            {"route_id": "route_477", "route_name": "E Tom Green St",
             "score": 0.71, "route_length_ft": 489.0},
        ],
        "print_filter": {
            "applied": True,
            "print_tokens": ["9"],
            "print_sheet_index_source": "hardcoded_brenham",
        },
        "anti_collapse_v2_attempt": {
            "alternate_chosen": True,
            "alternate_route_id": "route_477",
            "reason": "primary_collided_with_other_group",
        },
        "ambiguity_resolution_status": "not_applicable",
    }


def _diag_rescued_v4(source_file: str = "lawn.xlsx") -> Dict[str, Any]:
    """A LAWNDALE-allowlist V4 rescue success."""
    return {
        "source_file": source_file,
        "group_id": "g_v4",
        "stopped_at": None,
        "selected_route_id": "route_477",
        "selected_route_name": "Lawndale Ave",
        "render_allowed": True,
        "render_block_reasons": [],
        "strict_top5": [
            {"route_id": "route_477", "route_name": "Lawndale Ave",
             "score": 0.49, "route_length_ft": 612.0},
        ],
        "print_filter": {
            "applied": False,
            "print_tokens": ["23"],
            "print_sheet_index_source": "hardcoded_brenham",
        },
        "location_mismatch_rescue_selected": {
            "rescued_route_id": "route_477",
            "discovered_score": 0.12,
            "rescue_gate": "ratio_floor",
        },
        "ambiguity_resolution_status": "not_applicable",
    }


def _diag_low_confidence(source_file: str = "low.xlsx") -> Dict[str, Any]:
    """A successfully placed group with low top score."""
    return {
        "source_file": source_file,
        "group_id": "g_low",
        "stopped_at": None,
        "selected_route_id": "route_478",
        "selected_route_name": "E Mansfield St",
        "render_allowed": True,
        "render_block_reasons": [],
        "strict_top5": [
            {"route_id": "route_478", "route_name": "E Mansfield St",
             "score": 0.33, "route_length_ft": 489.0},
        ],
        "print_filter": {
            "applied": True,
            "print_tokens": ["14"],
            "print_sheet_index_source": "hardcoded_brenham",
        },
        "ambiguity_resolution_status": "not_applicable",
    }


def _diag_placed_normal(source_file: str = "ok.xlsx") -> Dict[str, Any]:
    """A normally-placed group — should be EXCLUDED from the queue."""
    return {
        "source_file": source_file,
        "group_id": "g_ok",
        "stopped_at": None,
        "selected_route_id": "route_476",
        "selected_route_name": "E Stone St",
        "render_allowed": True,
        "render_block_reasons": [],
        "strict_top5": [
            {"route_id": "route_476", "route_name": "E Stone St",
             "score": 0.88, "route_length_ft": 489.0},
        ],
        "print_filter": {
            "applied": True,
            "print_tokens": ["1"],
            "print_sheet_index_source": "hardcoded_brenham",
        },
        "ambiguity_resolution_status": "not_applicable",
    }


class TestEmptyOrInvalidInput(unittest.TestCase):
    def test_empty_list(self):
        out = assemble_match_review_queue([])
        self.assertEqual(out["row_count"], 0)
        self.assertEqual(out["rows"], [])
        self.assertEqual(out["schema_version"], SCHEMA_VERSION)

    def test_none(self):
        out = assemble_match_review_queue(None)  # type: ignore[arg-type]
        self.assertEqual(out["row_count"], 0)
        self.assertEqual(out["rows"], [])

    def test_non_list(self):
        out = assemble_match_review_queue("not a list")  # type: ignore[arg-type]
        self.assertEqual(out["row_count"], 0)

    def test_non_dict_entries_skipped(self):
        out = assemble_match_review_queue([None, "x", 42, _diag_abstained()])  # type: ignore[list-item]
        self.assertEqual(out["row_count"], 1)
        self.assertEqual(out["rows"][0]["status"], "abstained")


class TestStatusClassification(unittest.TestCase):
    def test_abstained_classified(self):
        out = assemble_match_review_queue([_diag_abstained()])
        self.assertEqual(out["row_count"], 1)
        self.assertEqual(out["rows"][0]["status"], "abstained")
        self.assertEqual(out["rows"][0]["priority"], "high")

    def test_ambiguous_classified(self):
        out = assemble_match_review_queue([_diag_ambiguous()])
        self.assertEqual(out["row_count"], 1)
        self.assertEqual(out["rows"][0]["status"], "ambiguous")
        self.assertEqual(out["rows"][0]["priority"], "high")

    def test_collision_resolved_classified(self):
        out = assemble_match_review_queue([_diag_collision_resolved()])
        self.assertEqual(out["row_count"], 1)
        self.assertEqual(out["rows"][0]["status"], "collision_resolved")
        self.assertEqual(out["rows"][0]["priority"], "medium")

    def test_rescued_v4_classified(self):
        out = assemble_match_review_queue([_diag_rescued_v4()])
        self.assertEqual(out["row_count"], 1)
        self.assertEqual(out["rows"][0]["status"], "rescued_v4")
        self.assertEqual(out["rows"][0]["priority"], "low")

    def test_placed_with_low_confidence_classified(self):
        out = assemble_match_review_queue([_diag_low_confidence()])
        self.assertEqual(out["row_count"], 1)
        self.assertEqual(out["rows"][0]["status"], "placed_with_low_confidence")
        self.assertEqual(out["rows"][0]["priority"], "medium")

    def test_placed_normal_excluded(self):
        # A normally-placed high-confidence group is not in the queue.
        out = assemble_match_review_queue([_diag_placed_normal()])
        self.assertEqual(out["row_count"], 0)
        self.assertEqual(out["rows"], [])

    def test_score_floor_boundary(self):
        # A score exactly at the floor must NOT be flagged low-confidence.
        entry = _diag_low_confidence()
        entry["strict_top5"][0]["score"] = LOW_CONFIDENCE_SCORE_FLOOR
        out = assemble_match_review_queue([entry])
        self.assertEqual(out["row_count"], 0)

        # A score just below MUST be flagged.
        entry["strict_top5"][0]["score"] = LOW_CONFIDENCE_SCORE_FLOOR - 0.01
        out2 = assemble_match_review_queue([entry])
        self.assertEqual(out2["row_count"], 1)
        self.assertEqual(out2["rows"][0]["status"], "placed_with_low_confidence")


class TestPriorityOrdering(unittest.TestCase):
    def test_high_before_medium_before_low(self):
        rows_in = [
            _diag_rescued_v4(),            # low
            _diag_placed_normal(),         # excluded
            _diag_collision_resolved(),    # medium
            _diag_abstained(),             # high
            _diag_ambiguous(),             # high
            _diag_low_confidence(),        # medium
        ]
        out = assemble_match_review_queue(rows_in)
        statuses = [r["status"] for r in out["rows"]]
        priorities = [r["priority"] for r in out["rows"]]
        # Excluded: placed_normal. Expect 5 rows.
        self.assertEqual(out["row_count"], 5)
        # High priorities come first.
        self.assertEqual(priorities[:2], ["high", "high"])
        # Then medium.
        self.assertEqual(priorities[2:4], ["medium", "medium"])
        # Then low.
        self.assertEqual(priorities[4:], ["low"])
        # Counts populated.
        self.assertEqual(out["counts_by_priority"], {"high": 2, "medium": 2, "low": 1})
        self.assertEqual(
            out["counts_by_status"],
            {
                "abstained": 1, "ambiguous": 1, "collision_resolved": 1,
                "rescued_v4": 1, "placed_with_low_confidence": 1,
            },
        )
        # Statuses appear within their priority tier in deterministic order
        # (alphabetic by source_file then group_id).
        self.assertIn("abstained", statuses)
        self.assertIn("ambiguous", statuses)


class TestRowShape(unittest.TestCase):
    def test_abstain_row_contents(self):
        out = assemble_match_review_queue([_diag_abstained()])
        row = out["rows"][0]
        self.assertEqual(row["source_file"], "abstain.xlsx")
        self.assertEqual(row["group_id"], "g_abstained")
        self.assertEqual(row["status"], "abstained")
        self.assertEqual(row["priority"], "high")
        self.assertIsNone(row["selected_route_id"])
        self.assertEqual(row["render_allowed"], False)
        self.assertIn("abstain_location_evidence_mismatch", row["render_block_reasons"])
        # Top alternates surfaced (top 3 from strict_top5).
        self.assertEqual(len(row["top_3_alternates"]), 2)
        self.assertEqual(row["top_3_alternates"][0]["route_id"], "route_478")
        # Evidence summary includes Stage A print_sheet_index_source.
        self.assertEqual(
            row["evidence_summary"]["print_sheet_index_source"],
            "hardcoded_brenham",
        )
        self.assertEqual(row["evidence_summary"]["notes_streets"], ["CHERI LN"])
        self.assertEqual(row["evidence_summary"]["street_hints"], ["CARLEE DR"])
        self.assertIn("CHERI LN",
                      row["evidence_summary"]["location_evidence_mismatch"]["notes_streets"])
        # Abstain reason surfaced.
        self.assertEqual(
            row["abstain_reason"], "abstained_location_evidence_mismatch"
        )

    def test_v4_row_contents(self):
        out = assemble_match_review_queue([_diag_rescued_v4()])
        row = out["rows"][0]
        self.assertEqual(row["status"], "rescued_v4")
        self.assertEqual(row["priority"], "low")
        self.assertEqual(row["selected_route_id"], "route_477")
        # KMZ-address-cluster evidence (V4 rescue meta) surfaces.
        self.assertEqual(
            row["evidence_summary"]["kmz_address_cluster_evidence"]["rescued_route_id"],
            "route_477",
        )
        # Safety-net log records the V4 rescue layer.
        layers = [s["layer"] for s in row["safety_net_log"]]
        self.assertIn("location_mismatch_rescue_v4", layers)

    def test_collision_row_contents(self):
        out = assemble_match_review_queue([_diag_collision_resolved()])
        row = out["rows"][0]
        self.assertEqual(row["status"], "collision_resolved")
        self.assertEqual(row["selected_route_id"], "route_477")
        # Safety-net log records the V2 layer.
        layers = [s["layer"] for s in row["safety_net_log"]]
        self.assertIn("anti_collapse_v2", layers)
        # Selected route is marked in top_3_alternates (when present there).
        self.assertTrue(
            any(a["was_selected"] for a in row["top_3_alternates"] if a["route_id"] == "route_477")
        )


class TestInputImmutability(unittest.TestCase):
    def test_does_not_mutate_input(self):
        diag: List[Dict[str, Any]] = [
            _diag_abstained(),
            _diag_rescued_v4(),
            _diag_placed_normal(),
        ]
        snap = copy.deepcopy(diag)
        assemble_match_review_queue(diag)
        self.assertEqual(diag, snap)


class TestSchemaVersionStable(unittest.TestCase):
    def test_schema_version_constant(self):
        self.assertEqual(SCHEMA_VERSION, "match-review-queue-1")
        out = assemble_match_review_queue([])
        self.assertEqual(out["schema_version"], "match-review-queue-1")


if __name__ == "__main__":
    unittest.main()
