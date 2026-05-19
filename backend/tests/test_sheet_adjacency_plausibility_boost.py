"""PT.2.0 — sheet adjacency plausibility boost tests.

Exercises `_apply_sheet_adjacency_plausibility_boost` under the
`TRUELINE_SHEET_ADJACENCY_BOOST` flag (default OFF). Covers:

  - Flag-OFF passthrough (no-op, no helper invocation, identity return)
  - All six documented `reason_if_not_applied` codes (early returns)
  - Single-token full match -> delta = cap
  - Multi-token full contiguous match -> delta = cap
  - Partial / non-contiguous match -> low quality, sub-cap delta
  - Duplicate handling in route sheet sequences
  - Cap enforcement at quality=1.0
  - Reorder gate fires (pre-bias gap ≤ _PLAN_BIAS_REORDER_GAP)
  - Reorder gate blocked (gap > _PLAN_BIAS_REORDER_GAP)
  - Input immutability (by-reference identity on no-op; deep-copy on apply)
  - Never-raises on pathological inputs (None, broken dicts, raising helpers)
  - Diagnostic schema validation (keys + types)
  - Honored mocked seam outputs
  - Honored mocked `_route_sheet_sequence` outputs
  - Stacking on top of upstream PT.1 boost fields without overwriting them

All tests mock `_print_to_sheets_from_packet_index` and
`_route_sheet_sequence` for determinism. No fixtures. No PDF dependency.
"""

from __future__ import annotations

import copy
import os

# Set required env vars before importing backend.main (mirrors prelude in
# test_print_to_sheet_plausibility_boost.py).
os.environ.setdefault("TRUELINE_JWT_SECRET", "pt20-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "pt20-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

import unittest
from typing import Any, Dict, List, Optional
from unittest.mock import patch

from backend import main as M


# ---------------------------------------------------------------------------
# Flag context — mirrors test_print_to_sheet_plausibility_boost._FlagContext
# ---------------------------------------------------------------------------


class _FlagContext:
    """Set/clear PT.2.0 env var deterministically for the duration of the
    `with` block. Snapshots whatever value the env had before and restores
    it on exit. Optionally toggles other env vars.
    """

    def __init__(self, **flags: bool) -> None:
        self.flags = flags
        self._sentinel = object()
        self._saved: Dict[str, Any] = {}

    def __enter__(self) -> "_FlagContext":
        for env_name, on in self.flags.items():
            self._saved[env_name] = os.environ.get(env_name, self._sentinel)
            if on:
                os.environ[env_name] = "1"
            else:
                os.environ.pop(env_name, None)
        return self

    def __exit__(self, *args: Any) -> None:
        for env_name, prior in self._saved.items():
            if prior is self._sentinel:
                os.environ.pop(env_name, None)
            else:
                os.environ[env_name] = prior  # type: ignore[assignment]


PT20_FLAG = M._SHEET_ADJACENCY_BOOST_FLAG_ENV


# ---------------------------------------------------------------------------
# Helpers — synthetic rankings and groups
# ---------------------------------------------------------------------------


def _ranking(route_id: str, score: float, *, route_name: str = "", route_score: float = 0.0) -> Dict[str, Any]:
    return {
        "route_id":        route_id,
        "route_name":      route_name or f"name_{route_id}",
        "score":           float(score),
        "combined_score":  float(score),
        "route_score":     float(route_score),
        "route_length_ft": 1000.0,
    }


def _group(tokens: List[Any]) -> Dict[str, Any]:
    return {
        "group_idx":   0,
        "source_file": "synthetic.csv",
        "print_tokens": list(tokens),
    }


REQUIRED_META_KEYS = {
    "applied", "flag_enabled", "reason_if_not_applied",
    "seam_sheets", "tokens_considered", "tokens_resolving_to_sheets",
    "routes_with_sequence", "boosted_entries", "max_delta_applied",
    "top2_gap_before_bias", "reordered", "per_route_match",
    # PT.ACT R1 — diagnostic schema hardening.
    "mode", "reorder_attempted", "reorder_blocked_reason", "selection_impact",
}


# ===========================================================================
# 1. Flag OFF — no-op passthrough
# ===========================================================================


class TestFlagOff(unittest.TestCase):
    def test_returns_original_reference_and_flag_off_reason(self) -> None:
        rankings_in = [_ranking("route_476", 0.6), _ranking("route_477", 0.55)]
        with _FlagContext(**{PT20_FLAG: False}):
            self.assertFalse(M._trueline_sheet_adjacency_boost_enabled())
            out, meta = M._apply_sheet_adjacency_plausibility_boost(
                rankings_in, _group(["7"])
            )
            self.assertIs(out, rankings_in)
            self.assertFalse(meta["applied"])
            self.assertFalse(meta["flag_enabled"])
            self.assertEqual(meta["reason_if_not_applied"], "flag_off")

    def test_does_not_call_seam_or_route_sequence(self) -> None:
        rankings_in = [_ranking("route_476", 0.6)]
        with _FlagContext(**{PT20_FLAG: False}), \
                patch.object(M, "_print_to_sheets_from_packet_index") as seam_mock, \
                patch.object(M, "_route_sheet_sequence") as seq_mock:
            M._apply_sheet_adjacency_plausibility_boost(rankings_in, _group(["7"]))
            seam_mock.assert_not_called()
            seq_mock.assert_not_called()


# ===========================================================================
# 2-7. Six documented early-return reasons
# ===========================================================================


class TestEarlyReturns(unittest.TestCase):
    def test_no_rankings(self) -> None:
        with _FlagContext(**{PT20_FLAG: True}):
            out, meta = M._apply_sheet_adjacency_plausibility_boost([], _group(["7"]))
            self.assertEqual(out, [])
            self.assertEqual(meta["reason_if_not_applied"], "no_rankings")

    def test_no_numeric_print_tokens_in_group(self) -> None:
        rankings_in = [_ranking("route_476", 0.6)]
        with _FlagContext(**{PT20_FLAG: True}):
            out, meta = M._apply_sheet_adjacency_plausibility_boost(
                rankings_in, _group(["T-3", "ABC", "", None])
            )
            self.assertIs(out, rankings_in)
            self.assertEqual(meta["reason_if_not_applied"], "no_numeric_print_tokens_in_group")
            self.assertEqual(meta["tokens_considered"], 0)

    def test_seam_empty(self) -> None:
        rankings_in = [_ranking("route_476", 0.6)]
        with _FlagContext(**{PT20_FLAG: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index", return_value={}), \
                patch.object(M, "_route_sheet_sequence", return_value=[]):
            out, meta = M._apply_sheet_adjacency_plausibility_boost(
                rankings_in, _group(["7"])
            )
            self.assertIs(out, rankings_in)
            self.assertEqual(meta["reason_if_not_applied"], "seam_empty")
            self.assertEqual(meta["tokens_resolving_to_sheets"], 0)
            self.assertEqual(meta["seam_sheets"], [])

    def test_no_route_sheet_sequences(self) -> None:
        rankings_in = [
            _ranking("route_476", 0.6),
            _ranking("route_477", 0.55),
        ]
        with _FlagContext(**{PT20_FLAG: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index",
                             return_value={"7": [7]}), \
                patch.object(M, "_route_sheet_sequence", return_value=[]):
            out, meta = M._apply_sheet_adjacency_plausibility_boost(
                rankings_in, _group(["7"])
            )
            self.assertIs(out, rankings_in)
            self.assertEqual(meta["reason_if_not_applied"], "no_route_sheet_sequences")
            self.assertEqual(meta["routes_with_sequence"], 0)
            self.assertEqual(meta["seam_sheets"], [7])

    def test_no_eligible_route_matches(self) -> None:
        # Seam resolves "7" -> sheet 7, but no candidate's route_sequence
        # contains sheet 7.
        rankings_in = [_ranking("route_476", 0.6)]
        with _FlagContext(**{PT20_FLAG: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index",
                             return_value={"7": [7]}), \
                patch.object(M, "_route_sheet_sequence",
                             return_value=[1, 2, 3]):
            out, meta = M._apply_sheet_adjacency_plausibility_boost(
                rankings_in, _group(["7"])
            )
            self.assertIs(out, rankings_in)
            self.assertEqual(meta["reason_if_not_applied"], "no_eligible_route_matches")
            self.assertEqual(meta["routes_with_sequence"], 1)
            self.assertEqual(meta["boosted_entries"], 0)


# ===========================================================================
# 8. Single-token full match -> delta = cap
# ===========================================================================


class TestSingleTokenFullMatch(unittest.TestCase):
    def test_quality_one_yields_cap_delta(self) -> None:
        rankings_in = [
            _ranking("route_476", 0.6),
            _ranking("route_999", 0.55),
        ]
        # Token "7" -> [7]; route_476 has [7, 8, 9]; only that route matches.
        def fake_route_seq(rid):
            return {"route_476": [7, 8, 9], "route_999": [1, 2, 3]}.get(rid, [])
        with _FlagContext(**{PT20_FLAG: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index",
                             return_value={"7": [7]}), \
                patch.object(M, "_route_sheet_sequence",
                             side_effect=fake_route_seq):
            out, meta = M._apply_sheet_adjacency_plausibility_boost(
                rankings_in, _group(["7"])
            )
            self.assertTrue(meta["applied"])
            self.assertEqual(meta["boosted_entries"], 1)
            self.assertAlmostEqual(meta["max_delta_applied"], M._PLAN_BIAS_MAX_BOOST, places=6)
            r476 = next(r for r in out if r["route_id"] == "route_476")
            self.assertAlmostEqual(r476["combined_score"], 0.6 + M._PLAN_BIAS_MAX_BOOST, places=6)
            self.assertEqual(meta["per_route_match"]["route_476"]["matched_count"], 1)
            self.assertAlmostEqual(meta["per_route_match"]["route_476"]["coverage"], 1.0, places=6)


# ===========================================================================
# 9. Multi-token full contiguous match
# ===========================================================================


class TestMultiTokenContiguousMatch(unittest.TestCase):
    def test_three_contiguous_tokens_full_coverage(self) -> None:
        rankings_in = [_ranking("route_476", 0.6)]
        # Tokens 7, 8, 9 all in route_476's sequence contiguously.
        with _FlagContext(**{PT20_FLAG: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index",
                             return_value={"7": [7], "8": [8], "9": [9]}), \
                patch.object(M, "_route_sheet_sequence",
                             return_value=[7, 8, 9, 10]):
            out, meta = M._apply_sheet_adjacency_plausibility_boost(
                rankings_in, _group(["7", "8", "9"])
            )
            self.assertTrue(meta["applied"])
            self.assertEqual(meta["per_route_match"]["route_476"]["matched_count"], 3)
            self.assertAlmostEqual(
                meta["per_route_match"]["route_476"]["coverage"], 1.0, places=6
            )
            # Delta = cap (quality 1.0 saturates).
            self.assertAlmostEqual(meta["max_delta_applied"], M._PLAN_BIAS_MAX_BOOST, places=6)


# ===========================================================================
# 10. Partial contiguous match — sub-cap delta
# ===========================================================================


class TestPartialContiguousMatch(unittest.TestCase):
    def test_two_of_three_seam_sheets_contiguous_in_route(self) -> None:
        # Seam = {1, 2, 7}; route_seq = [1, 2, 3, 4, 7].
        # Longest contiguous run inside seam: [1, 2] (length 2). Then [7] (1).
        # Best = 2, coverage = 2/3, quality = 2/3.
        rankings_in = [_ranking("route_476", 0.6)]
        with _FlagContext(**{PT20_FLAG: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index",
                             return_value={"1": [1], "2": [2], "7": [7]}), \
                patch.object(M, "_route_sheet_sequence",
                             return_value=[1, 2, 3, 4, 7]):
            out, meta = M._apply_sheet_adjacency_plausibility_boost(
                rankings_in, _group(["1", "2", "7"])
            )
            self.assertTrue(meta["applied"])
            self.assertEqual(meta["per_route_match"]["route_476"]["matched_count"], 2)
            self.assertAlmostEqual(
                meta["per_route_match"]["route_476"]["coverage"], 2.0 / 3.0, places=6
            )
            expected_delta = M._PLAN_BIAS_MAX_BOOST * (2.0 / 3.0)
            self.assertAlmostEqual(meta["max_delta_applied"], expected_delta, places=6)
            self.assertAlmostEqual(out[0]["combined_score"], 0.6 + expected_delta, places=6)


# ===========================================================================
# 11. Non-contiguous -> longest contiguous run = 1
# ===========================================================================


class TestNonContiguousMatch(unittest.TestCase):
    def test_two_seam_sheets_split_by_gap_yields_run_one(self) -> None:
        # Seam = {1, 7}; route_seq = [1, 2, 3, 4, 7].
        # Longest contiguous run inside seam: [1] or [7], length 1.
        # Coverage = 1/2.
        rankings_in = [_ranking("route_476", 0.6)]
        with _FlagContext(**{PT20_FLAG: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index",
                             return_value={"1": [1], "7": [7]}), \
                patch.object(M, "_route_sheet_sequence",
                             return_value=[1, 2, 3, 4, 7]):
            out, meta = M._apply_sheet_adjacency_plausibility_boost(
                rankings_in, _group(["1", "7"])
            )
            self.assertTrue(meta["applied"])
            self.assertEqual(meta["per_route_match"]["route_476"]["matched_count"], 1)
            self.assertAlmostEqual(
                meta["per_route_match"]["route_476"]["coverage"], 0.5, places=6
            )
            expected_delta = M._PLAN_BIAS_MAX_BOOST * 0.5
            self.assertAlmostEqual(meta["max_delta_applied"], expected_delta, places=6)


# ===========================================================================
# 12. Duplicate sheets in route_sequence deduped
# ===========================================================================


class TestDedupeRouteSequence(unittest.TestCase):
    def test_duplicates_in_route_seq_are_collapsed(self) -> None:
        # Route_seq with duplicates: [1, 1, 2, 3, 2, 3] -> deduped [1, 2, 3].
        # Seam = {1, 2, 3}. Best run = 3 (full match).
        rankings_in = [_ranking("route_476", 0.6)]
        with _FlagContext(**{PT20_FLAG: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index",
                             return_value={"1": [1], "2": [2], "3": [3]}), \
                patch.object(M, "_route_sheet_sequence",
                             return_value=[1, 1, 2, 3, 2, 3]):
            out, meta = M._apply_sheet_adjacency_plausibility_boost(
                rankings_in, _group(["1", "2", "3"])
            )
            self.assertTrue(meta["applied"])
            self.assertEqual(meta["per_route_match"]["route_476"]["route_sequence"], [1, 2, 3])
            self.assertEqual(meta["per_route_match"]["route_476"]["matched_count"], 3)


# ===========================================================================
# 13. Cap enforcement
# ===========================================================================


class TestCapEnforcement(unittest.TestCase):
    def test_quality_one_delta_saturates_at_max_boost(self) -> None:
        rankings_in = [_ranking("route_476", 0.6)]
        with _FlagContext(**{PT20_FLAG: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index",
                             return_value={"7": [7]}), \
                patch.object(M, "_route_sheet_sequence",
                             return_value=[7]):
            out, meta = M._apply_sheet_adjacency_plausibility_boost(
                rankings_in, _group(["7"])
            )
            self.assertAlmostEqual(meta["max_delta_applied"], M._PLAN_BIAS_MAX_BOOST, places=6)
            # delta_applied recorded in per_route_match
            self.assertAlmostEqual(
                meta["per_route_match"]["route_476"]["delta_applied"],
                M._PLAN_BIAS_MAX_BOOST,
                places=6,
            )


# ===========================================================================
# 14. Reorder gate fires
# ===========================================================================


class TestReorderGateFires(unittest.TestCase):
    def test_lower_candidate_overtakes_when_gap_within_threshold(self) -> None:
        # Pre-bias gap = 0.02 (within _PLAN_BIAS_REORDER_GAP=0.10).
        rankings_in = [
            _ranking("route_LEAD", 0.60),  # no evidence
            _ranking("route_476", 0.58),   # full evidence -> +cap
        ]
        def fake_route_seq(rid):
            return {"route_476": [7], "route_LEAD": [99, 100]}.get(rid, [])
        with _FlagContext(**{PT20_FLAG: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index",
                             return_value={"7": [7]}), \
                patch.object(M, "_route_sheet_sequence",
                             side_effect=fake_route_seq):
            out, meta = M._apply_sheet_adjacency_plausibility_boost(
                rankings_in, _group(["7"])
            )
            self.assertTrue(meta["applied"])
            self.assertTrue(meta["reordered"])
            # 0.58 + 0.03 = 0.61 > 0.60 -> route_476 overtakes
            self.assertEqual(out[0]["route_id"], "route_476")
            self.assertEqual(out[1]["route_id"], "route_LEAD")


# ===========================================================================
# 15. Reorder gate blocked
# ===========================================================================


class TestReorderGateBlocked(unittest.TestCase):
    def test_no_reorder_when_pre_bias_gap_too_large(self) -> None:
        # Pre-bias gap = 0.20 > _PLAN_BIAS_REORDER_GAP=0.10.
        rankings_in = [
            _ranking("route_LEAD", 0.80),  # no evidence
            _ranking("route_476", 0.60),   # full evidence -> +cap = 0.63
        ]
        def fake_route_seq(rid):
            return {"route_476": [7], "route_LEAD": [99, 100]}.get(rid, [])
        with _FlagContext(**{PT20_FLAG: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index",
                             return_value={"7": [7]}), \
                patch.object(M, "_route_sheet_sequence",
                             side_effect=fake_route_seq):
            out, meta = M._apply_sheet_adjacency_plausibility_boost(
                rankings_in, _group(["7"])
            )
            self.assertTrue(meta["applied"])
            self.assertFalse(meta["reordered"])
            # Order preserved; delta applied but lead candidate still first.
            self.assertEqual(out[0]["route_id"], "route_LEAD")
            self.assertEqual(out[1]["route_id"], "route_476")
            self.assertAlmostEqual(out[1]["combined_score"], 0.63, places=6)


# ===========================================================================
# 16. Input immutability
# ===========================================================================


class TestInputsNotMutated(unittest.TestCase):
    def test_inputs_unchanged_after_apply(self) -> None:
        rankings_in = [_ranking("route_476", 0.6)]
        group = _group(["7"])
        rankings_snapshot = copy.deepcopy(rankings_in)
        group_snapshot = copy.deepcopy(group)
        with _FlagContext(**{PT20_FLAG: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index",
                             return_value={"7": [7]}), \
                patch.object(M, "_route_sheet_sequence",
                             return_value=[7]):
            out, _ = M._apply_sheet_adjacency_plausibility_boost(rankings_in, group)
            self.assertEqual(rankings_in, rankings_snapshot)
            self.assertEqual(group, group_snapshot)
            self.assertIsNot(out, rankings_in)
            self.assertIsNot(out[0], rankings_in[0])


# ===========================================================================
# 17. Never raises on pathological inputs
# ===========================================================================


class TestNeverRaises(unittest.TestCase):
    def test_none_rankings(self) -> None:
        with _FlagContext(**{PT20_FLAG: True}):
            out, meta = M._apply_sheet_adjacency_plausibility_boost([], _group(["7"]))
            self.assertEqual(out, [])
            self.assertEqual(meta["reason_if_not_applied"], "no_rankings")

    def test_non_dict_entries_in_rankings(self) -> None:
        rankings_in: List[Any] = [_ranking("route_476", 0.6), "not-a-dict", 42, None]
        with _FlagContext(**{PT20_FLAG: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index",
                             return_value={"7": [7]}), \
                patch.object(M, "_route_sheet_sequence",
                             return_value=[7]):
            out, meta = M._apply_sheet_adjacency_plausibility_boost(
                rankings_in, _group(["7"])
            )
            self.assertEqual(len(out), 4)
            self.assertEqual(out[1], "not-a-dict")
            self.assertEqual(out[2], 42)
            self.assertIsNone(out[3])
            self.assertTrue(meta["applied"])

    def test_seam_raises(self) -> None:
        rankings_in = [_ranking("route_476", 0.6)]
        with _FlagContext(**{PT20_FLAG: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index",
                             side_effect=RuntimeError("boom")), \
                patch.object(M, "_route_sheet_sequence",
                             return_value=[7]):
            out, meta = M._apply_sheet_adjacency_plausibility_boost(
                rankings_in, _group(["7"])
            )
            self.assertIs(out, rankings_in)
            self.assertEqual(meta["reason_if_not_applied"], "seam_empty")

    def test_route_sequence_raises(self) -> None:
        rankings_in = [_ranking("route_476", 0.6)]
        with _FlagContext(**{PT20_FLAG: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index",
                             return_value={"7": [7]}), \
                patch.object(M, "_route_sheet_sequence",
                             side_effect=RuntimeError("boom")):
            out, meta = M._apply_sheet_adjacency_plausibility_boost(
                rankings_in, _group(["7"])
            )
            self.assertIs(out, rankings_in)
            self.assertEqual(meta["reason_if_not_applied"], "no_route_sheet_sequences")

    def test_broken_normalized_group(self) -> None:
        rankings_in = [_ranking("route_476", 0.6)]
        with _FlagContext(**{PT20_FLAG: True}):
            for bad in (None, [], "not a dict", 42):
                out, meta = M._apply_sheet_adjacency_plausibility_boost(
                    rankings_in, bad  # type: ignore[arg-type]
                )
                self.assertIs(out, rankings_in)
                self.assertEqual(meta["reason_if_not_applied"], "no_numeric_print_tokens_in_group")


# ===========================================================================
# 18. Diagnostic shape
# ===========================================================================


class TestDiagnosticShape(unittest.TestCase):
    def test_meta_keys_and_types_complete(self) -> None:
        rankings_in = [_ranking("route_476", 0.6)]
        with _FlagContext(**{PT20_FLAG: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index",
                             return_value={"7": [7]}), \
                patch.object(M, "_route_sheet_sequence",
                             return_value=[7]):
            _, meta = M._apply_sheet_adjacency_plausibility_boost(
                rankings_in, _group(["7"])
            )
            self.assertEqual(set(meta.keys()), REQUIRED_META_KEYS)
            self.assertIsInstance(meta["applied"], bool)
            self.assertIsInstance(meta["flag_enabled"], bool)
            self.assertIsInstance(meta["seam_sheets"], list)
            self.assertIsInstance(meta["tokens_considered"], int)
            self.assertIsInstance(meta["tokens_resolving_to_sheets"], int)
            self.assertIsInstance(meta["routes_with_sequence"], int)
            self.assertIsInstance(meta["boosted_entries"], int)
            self.assertIsInstance(meta["max_delta_applied"], float)
            self.assertIsInstance(meta["top2_gap_before_bias"], float)
            self.assertIsInstance(meta["reordered"], bool)
            self.assertIsInstance(meta["per_route_match"], dict)
            rm = meta["per_route_match"]["route_476"]
            self.assertIn("route_sequence", rm)
            self.assertIn("matched_count", rm)
            self.assertIn("coverage", rm)
            self.assertIn("delta_applied", rm)


# ===========================================================================
# 19. Respects mocked helpers
# ===========================================================================


class TestRespectsMockedHelpers(unittest.TestCase):
    def test_route_sequence_mock_honored(self) -> None:
        # Use a synthetic route_sequence that's NOT the real Brenham one.
        rankings_in = [_ranking("route_ZZZ", 0.6)]
        with _FlagContext(**{PT20_FLAG: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index",
                             return_value={"42": [42]}), \
                patch.object(M, "_route_sheet_sequence",
                             return_value=[40, 41, 42, 43]):
            _, meta = M._apply_sheet_adjacency_plausibility_boost(
                rankings_in, _group(["42"])
            )
            self.assertTrue(meta["applied"])
            self.assertEqual(meta["per_route_match"]["route_ZZZ"]["route_sequence"],
                             [40, 41, 42, 43])
            self.assertEqual(meta["seam_sheets"], [42])

    def test_seam_mock_honored(self) -> None:
        # Synthetic seam mapping; the boost should reflect it exactly.
        rankings_in = [_ranking("route_476", 0.6)]
        with _FlagContext(**{PT20_FLAG: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index",
                             return_value={"7": [99]}), \
                patch.object(M, "_route_sheet_sequence",
                             return_value=[99, 100]):
            _, meta = M._apply_sheet_adjacency_plausibility_boost(
                rankings_in, _group(["7"])
            )
            self.assertTrue(meta["applied"])
            self.assertEqual(meta["seam_sheets"], [99])
            self.assertEqual(meta["per_route_match"]["route_476"]["matched_count"], 1)


# ===========================================================================
# 20. Stacking with upstream PT.1 fields
# ===========================================================================


class TestStackingWithPT1(unittest.TestCase):
    def test_pt20_layered_on_post_pt1_scores_without_overwrite(self) -> None:
        # Simulate the upstream PT.1 having already added +0.01 to route_476
        # via its print_to_sheet_boost_delta field. PT.2.0 reads the current
        # combined_score (0.61) and adds its own delta on top.
        upstream = {
            "route_id":                       "route_476",
            "route_name":                     "name_route_476",
            "score":                          0.61,
            "combined_score":                 0.61,
            "route_score":                    0.0,
            "route_length_ft":                1000.0,
            "original_score":                 0.60,
            "plan_adjusted_score":            0.60,
            "print_to_sheet_boost_delta":     0.01,
            "print_to_sheet_boost_evidence":  ["7"],
        }
        rankings_in = [upstream, _ranking("route_999", 0.55)]
        with _FlagContext(**{PT20_FLAG: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index",
                             return_value={"7": [7]}), \
                patch.object(M, "_route_sheet_sequence",
                             side_effect=lambda rid: [7] if rid == "route_476" else []):
            out, meta = M._apply_sheet_adjacency_plausibility_boost(
                rankings_in, _group(["7"])
            )
            r476 = next(r for r in out if r["route_id"] == "route_476")
            # PT.2.0 delta is +cap (quality 1.0) on top of 0.61 = 0.64.
            self.assertAlmostEqual(r476["combined_score"], 0.61 + M._PLAN_BIAS_MAX_BOOST, places=6)
            # PT.1 fields preserved unchanged.
            self.assertAlmostEqual(r476["original_score"], 0.60, places=6)
            self.assertAlmostEqual(r476["plan_adjusted_score"], 0.60, places=6)
            self.assertAlmostEqual(r476["print_to_sheet_boost_delta"], 0.01, places=6)
            self.assertEqual(r476["print_to_sheet_boost_evidence"], ["7"])
            # PT.2.0 fields newly written.
            self.assertAlmostEqual(r476["sheet_adjacency_boost_delta"], M._PLAN_BIAS_MAX_BOOST, places=6)
            self.assertEqual(r476["sheet_adjacency_boost_evidence"]["matched_count"], 1)
            # Combined PT.1+PT.2.0 delta cannot exceed 2 * cap.
            total_delta = r476["combined_score"] - r476["original_score"]
            self.assertLessEqual(total_delta, 2 * M._PLAN_BIAS_MAX_BOOST + 1e-9)


# ===========================================================================
# PT.ACT R1 — diagnostic schema hardening (no behavior change)
# ===========================================================================


class TestR1MetaShape(unittest.TestCase):
    """R1 adds: mode / reorder_attempted / reorder_blocked_reason /
    selection_impact. No scoring, no reorder math, no flag interaction
    changes."""

    def test_off_mode_emits_mode_off_and_layer_not_applied(self) -> None:
        rankings_in = [_ranking("route_476", 0.6), _ranking("route_477", 0.55)]
        with _FlagContext(**{PT20_FLAG: False}):
            out, meta = M._apply_sheet_adjacency_plausibility_boost(
                rankings_in, _group(["7"])
            )
            self.assertIs(out, rankings_in)
            self.assertEqual(meta["mode"], "off")
            self.assertFalse(meta["reorder_attempted"])
            self.assertEqual(meta["reorder_blocked_reason"], "layer_not_applied")
            self.assertIsNone(meta["selection_impact"])

    def test_live_mode_early_return_keeps_layer_not_applied(self) -> None:
        # Flag ON but seam empty -> reason_if_not_applied="seam_empty".
        # mode reads "live"; reorder/selection_impact remain at defaults.
        rankings_in = [_ranking("route_476", 0.6)]
        with _FlagContext(**{PT20_FLAG: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index", return_value={}), \
                patch.object(M, "_route_sheet_sequence", return_value=[]):
            out, meta = M._apply_sheet_adjacency_plausibility_boost(
                rankings_in, _group(["7"])
            )
            self.assertEqual(meta["mode"], "live")
            self.assertEqual(meta["reason_if_not_applied"], "seam_empty")
            self.assertFalse(meta["reorder_attempted"])
            self.assertEqual(meta["reorder_blocked_reason"], "layer_not_applied")
            self.assertIsNone(meta["selection_impact"])

    def test_live_mode_with_boost_emits_selection_impact(self) -> None:
        # Pre-bias gap = 0.01 (<= 0.10 threshold), route_B gets full coverage
        # (delta = cap = 0.03). 0.59 + 0.03 = 0.62 > 0.60 -> gate fires AND
        # order flips.
        seam_map = {"7": [101, 102]}
        seq_map = {"route_A": [201], "route_B": [101, 102]}
        rankings_in = [_ranking("route_A", 0.60), _ranking("route_B", 0.59)]
        with _FlagContext(**{PT20_FLAG: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index", return_value=seam_map), \
                patch.object(M, "_route_sheet_sequence", side_effect=lambda rid: seq_map.get(rid, [])):
            out, meta = M._apply_sheet_adjacency_plausibility_boost(
                rankings_in, _group(["7"])
            )
            self.assertEqual(meta["mode"], "live")
            self.assertTrue(meta["applied"])
            self.assertTrue(meta["reorder_attempted"])
            self.assertIsNone(meta["reorder_blocked_reason"])
            self.assertEqual(meta["selection_impact"]["pre_layer_top1"], "route_A")
            self.assertEqual(meta["selection_impact"]["post_layer_top1"], "route_B")
            self.assertTrue(meta["selection_impact"]["changed"])

    def test_reorder_attempted_false_with_gap_above_threshold(self) -> None:
        # Pre-bias gap = 0.30 -> gate does not fire even though boost applies.
        seam_map = {"7": [101, 102]}
        seq_map = {"route_A": [101, 102], "route_B": [201]}
        rankings_in = [_ranking("route_A", 0.85), _ranking("route_B", 0.55)]
        with _FlagContext(**{PT20_FLAG: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index", return_value=seam_map), \
                patch.object(M, "_route_sheet_sequence", side_effect=lambda rid: seq_map.get(rid, [])):
            out, meta = M._apply_sheet_adjacency_plausibility_boost(
                rankings_in, _group(["7"])
            )
            self.assertEqual(meta["mode"], "live")
            self.assertTrue(meta["applied"])
            self.assertFalse(meta["reordered"])
            self.assertFalse(meta["reorder_attempted"])
            self.assertEqual(meta["reorder_blocked_reason"], "gap_above_threshold")
            self.assertEqual(meta["selection_impact"]["pre_layer_top1"], "route_A")
            self.assertEqual(meta["selection_impact"]["post_layer_top1"], "route_A")
            self.assertFalse(meta["selection_impact"]["changed"])

    def test_reorder_attempted_false_with_single_candidate(self) -> None:
        seam_map = {"7": [101, 102]}
        seq_map = {"route_A": [101, 102]}
        rankings_in = [_ranking("route_A", 0.6)]
        with _FlagContext(**{PT20_FLAG: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index", return_value=seam_map), \
                patch.object(M, "_route_sheet_sequence", side_effect=lambda rid: seq_map.get(rid, [])):
            out, meta = M._apply_sheet_adjacency_plausibility_boost(
                rankings_in, _group(["7"])
            )
            self.assertEqual(meta["mode"], "live")
            self.assertTrue(meta["applied"])
            self.assertFalse(meta["reordered"])
            self.assertFalse(meta["reorder_attempted"])
            self.assertEqual(meta["reorder_blocked_reason"], "single_candidate")
            self.assertEqual(meta["selection_impact"]["pre_layer_top1"], "route_A")
            self.assertEqual(meta["selection_impact"]["post_layer_top1"], "route_A")
            self.assertFalse(meta["selection_impact"]["changed"])

    def test_selection_impact_unchanged_when_top1_was_already_boosted(self) -> None:
        # Top-1 (route_A) receives the full boost; order does not change but
        # gate still fires (gap small). selection_impact.changed=False.
        seam_map = {"7": [101, 102]}
        seq_map = {"route_A": [101, 102], "route_B": [201]}
        rankings_in = [_ranking("route_A", 0.60), _ranking("route_B", 0.55)]
        with _FlagContext(**{PT20_FLAG: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index", return_value=seam_map), \
                patch.object(M, "_route_sheet_sequence", side_effect=lambda rid: seq_map.get(rid, [])):
            out, meta = M._apply_sheet_adjacency_plausibility_boost(
                rankings_in, _group(["7"])
            )
            self.assertEqual(meta["mode"], "live")
            self.assertTrue(meta["reorder_attempted"])
            self.assertIsNone(meta["reorder_blocked_reason"])
            self.assertFalse(meta["reordered"])
            self.assertEqual(meta["selection_impact"]["pre_layer_top1"], "route_A")
            self.assertEqual(meta["selection_impact"]["post_layer_top1"], "route_A")
            self.assertFalse(meta["selection_impact"]["changed"])


if __name__ == "__main__":
    unittest.main()
