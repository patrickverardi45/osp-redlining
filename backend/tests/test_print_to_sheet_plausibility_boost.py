"""PT.1 — print-to-sheet plausibility boost tests.

Exercises `_apply_print_to_sheet_plausibility_boost` under the
`TRUELINE_PRINT_TO_SHEET_BOOST` flag (default OFF). Covers:

  - Flag-OFF passthrough (no-op, no seam call, no STATE write)
  - Empty / no-numeric-token / pathological inputs (safe-fail)
  - Single-token single-route boost
  - Multi-token per-route cap enforcement (delta ≤ _PLAN_BIAS_MAX_BOOST)
  - Multi-route evidence accumulation
  - Reorder gate fires when pre-bias top-2 gap ≤ _PLAN_BIAS_REORDER_GAP
  - Reorder gate blocked when gap > _PLAN_BIAS_REORDER_GAP
  - Input immutability
  - Diagnostic shape
  - Never-raises on broken inputs
  - Stacking with already-boosted scores (upstream _plan_aware_ranking_boost
    state preserved)
  - Honors patched seam outputs (synthetic projections)

All tests mock `_print_to_sheets_from_packet_index` and
`_sheet_to_route_ids_from_packet_index` for determinism. No fixtures.
"""

from __future__ import annotations

import copy
import os

# Set required env vars before importing backend.main (mirrors prelude in
# test_confirmed_sheet_set_cache.py, test_pi4b_print_to_sheets_activation.py).
os.environ.setdefault("TRUELINE_JWT_SECRET", "pt1-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "pt1-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

import unittest
from typing import Any, Dict, List, Optional
from unittest.mock import patch

from backend import main as M


# ---------------------------------------------------------------------------
# Flag context — mirrors test_pi4b_print_to_sheets_activation._FlagContext
# ---------------------------------------------------------------------------


class _FlagContext:
    """Set/clear PT.1 env var deterministically for the duration of the
    `with` block. Snapshots whatever value the env had before and restores
    it on exit. Optionally toggles other env vars (e.g. PI.4B.2 flag).
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


PT1_FLAG = M._PRINT_TO_SHEET_BOOST_FLAG_ENV


# ---------------------------------------------------------------------------
# Helpers — build synthetic rankings + group dicts
# ---------------------------------------------------------------------------


def _ranking(route_id: str, score: float, *, route_name: str = "", route_score: float = 0.0) -> Dict[str, Any]:
    return {
        "route_id":       route_id,
        "route_name":     route_name or f"name_{route_id}",
        "score":          float(score),
        "combined_score": float(score),
        "route_score":    float(route_score),
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
    "tokens_considered", "tokens_resolving_to_sheets",
    "routes_with_evidence", "boosted_entries", "max_delta_applied",
    "top2_gap_before_bias", "reordered",
    "evidence_by_route_id", "evidence_by_sheet_int",
    # PT.ACT R1 — diagnostic schema hardening.
    "mode", "reorder_attempted", "reorder_blocked_reason", "selection_impact",
}


# ===========================================================================
# 1. Flag OFF — no-op passthrough
# ===========================================================================


class TestFlagOff(unittest.TestCase):
    """Default-OFF: rankings reference preserved; meta says flag_off; the
    seam is NOT invoked (no STATE side-effects from the boost layer).
    """

    def test_flag_off_returns_original_reference_and_flag_off_reason(self) -> None:
        rankings_in = [_ranking("route_476", 0.6), _ranking("route_477", 0.55)]
        group = _group(["7"])
        with _FlagContext(**{PT1_FLAG: False}):
            self.assertFalse(M._trueline_print_to_sheet_boost_enabled())
            out, meta = M._apply_print_to_sheet_plausibility_boost(rankings_in, group)
            self.assertIs(out, rankings_in)
            self.assertEqual(meta["applied"], False)
            self.assertEqual(meta["flag_enabled"], False)
            self.assertEqual(meta["reason_if_not_applied"], "flag_off")

    def test_flag_off_does_not_call_seam(self) -> None:
        rankings_in = [_ranking("route_476", 0.6)]
        group = _group(["7"])
        with _FlagContext(**{PT1_FLAG: False}), \
                patch.object(M, "_print_to_sheets_from_packet_index") as mock_seam, \
                patch.object(M, "_sheet_to_route_ids_from_packet_index") as mock_routes:
            M._apply_print_to_sheet_plausibility_boost(rankings_in, group)
            mock_seam.assert_not_called()
            mock_routes.assert_not_called()


# ===========================================================================
# 2-5. Flag ON — early-return safe-fail paths
# ===========================================================================


class TestFlagOnEarlyReturns(unittest.TestCase):
    """The six documented `reason_if_not_applied` codes."""

    def test_no_rankings(self) -> None:
        with _FlagContext(**{PT1_FLAG: True}):
            out, meta = M._apply_print_to_sheet_plausibility_boost([], _group(["7"]))
            self.assertEqual(out, [])
            self.assertEqual(meta["applied"], False)
            self.assertEqual(meta["reason_if_not_applied"], "no_rankings")

    def test_no_numeric_print_tokens_in_group(self) -> None:
        rankings_in = [_ranking("route_476", 0.6)]
        with _FlagContext(**{PT1_FLAG: True}):
            out, meta = M._apply_print_to_sheet_plausibility_boost(
                rankings_in, _group(["T-3", "ABC", ""])
            )
            self.assertIs(out, rankings_in)
            self.assertEqual(meta["reason_if_not_applied"], "no_numeric_print_tokens_in_group")
            self.assertEqual(meta["tokens_considered"], 0)

    def test_seam_empty(self) -> None:
        rankings_in = [_ranking("route_476", 0.6)]
        with _FlagContext(**{PT1_FLAG: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index", return_value={}), \
                patch.object(M, "_sheet_to_route_ids_from_packet_index", return_value={}):
            out, meta = M._apply_print_to_sheet_plausibility_boost(
                rankings_in, _group(["7"])
            )
            self.assertIs(out, rankings_in)
            self.assertEqual(meta["reason_if_not_applied"], "seam_empty")
            self.assertEqual(meta["tokens_resolving_to_sheets"], 0)

    def test_no_sheet_to_route_evidence(self) -> None:
        # Seam returns a sheet for the token, but sheet -> routes is empty.
        rankings_in = [_ranking("route_476", 0.6)]
        with _FlagContext(**{PT1_FLAG: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index",
                             return_value={"7": [7]}), \
                patch.object(M, "_sheet_to_route_ids_from_packet_index",
                             return_value={}):
            out, meta = M._apply_print_to_sheet_plausibility_boost(
                rankings_in, _group(["7"])
            )
            self.assertIs(out, rankings_in)
            self.assertEqual(meta["reason_if_not_applied"], "no_sheet_to_route_evidence")
            self.assertEqual(meta["routes_with_evidence"], 0)

    def test_no_eligible_route_matches(self) -> None:
        # Evidence resolves to a route_id none of the rankings carry.
        rankings_in = [_ranking("route_XYZ", 0.6)]
        with _FlagContext(**{PT1_FLAG: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index",
                             return_value={"7": [7]}), \
                patch.object(M, "_sheet_to_route_ids_from_packet_index",
                             return_value={7: ["route_476"]}):
            out, meta = M._apply_print_to_sheet_plausibility_boost(
                rankings_in, _group(["7"])
            )
            self.assertIs(out, rankings_in)
            self.assertEqual(meta["reason_if_not_applied"], "no_eligible_route_matches")
            self.assertEqual(meta["routes_with_evidence"], 1)
            self.assertEqual(meta["boosted_entries"], 0)


# ===========================================================================
# 6. Single token → single route boost
# ===========================================================================


class TestSingleTokenSingleRouteBoost(unittest.TestCase):
    def test_one_evidence_token_yields_one_one_hundredth_delta(self) -> None:
        rankings_in = [
            _ranking("route_476", 0.6),
            _ranking("route_999", 0.55),
        ]
        with _FlagContext(**{PT1_FLAG: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index",
                             return_value={"7": [7]}), \
                patch.object(M, "_sheet_to_route_ids_from_packet_index",
                             return_value={7: ["route_476"]}):
            out, meta = M._apply_print_to_sheet_plausibility_boost(
                rankings_in, _group(["7"])
            )
            self.assertEqual(meta["applied"], True)
            self.assertEqual(meta["boosted_entries"], 1)
            self.assertAlmostEqual(meta["max_delta_applied"], 0.01, places=6)
            # The boosted entry now has combined_score = 0.61 and the
            # other is unchanged at 0.55.
            scores_by_route = {r["route_id"]: r["combined_score"] for r in out}
            self.assertAlmostEqual(scores_by_route["route_476"], 0.61, places=6)
            self.assertAlmostEqual(scores_by_route["route_999"], 0.55, places=6)


# ===========================================================================
# 7. Cap enforcement
# ===========================================================================


class TestTokenCountCap(unittest.TestCase):
    def test_five_matching_tokens_for_one_route_caps_at_max_boost(self) -> None:
        rankings_in = [_ranking("route_476", 0.6)]
        # 5 tokens, each resolving to a distinct sheet that maps to route_476.
        seam = {str(n): [n] for n in (1, 2, 3, 4, 5)}
        sheet_routes = {n: ["route_476"] for n in (1, 2, 3, 4, 5)}
        with _FlagContext(**{PT1_FLAG: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index",
                             return_value=seam), \
                patch.object(M, "_sheet_to_route_ids_from_packet_index",
                             return_value=sheet_routes):
            out, meta = M._apply_print_to_sheet_plausibility_boost(
                rankings_in, _group(["1", "2", "3", "4", "5"])
            )
            self.assertEqual(meta["applied"], True)
            self.assertEqual(meta["boosted_entries"], 1)
            # 5 * 0.01 = 0.05 > cap 0.03 -> capped at 0.03.
            self.assertAlmostEqual(meta["max_delta_applied"], M._PLAN_BIAS_MAX_BOOST, places=6)
            self.assertAlmostEqual(out[0]["combined_score"], 0.6 + M._PLAN_BIAS_MAX_BOOST, places=6)
            self.assertAlmostEqual(out[0]["print_to_sheet_boost_delta"], M._PLAN_BIAS_MAX_BOOST, places=6)


# ===========================================================================
# 8. Multi-route evidence
# ===========================================================================


class TestMultiRouteEvidence(unittest.TestCase):
    def test_multiple_routes_each_get_independent_delta(self) -> None:
        rankings_in = [
            _ranking("route_476", 0.6),
            _ranking("route_479", 0.55),
            _ranking("route_999", 0.5),   # no evidence
        ]
        seam = {"7": [7], "15": [15]}
        sheet_routes = {7: ["route_476"], 15: ["route_479", "route_480"]}
        with _FlagContext(**{PT1_FLAG: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index",
                             return_value=seam), \
                patch.object(M, "_sheet_to_route_ids_from_packet_index",
                             return_value=sheet_routes):
            out, meta = M._apply_print_to_sheet_plausibility_boost(
                rankings_in, _group(["7", "15"])
            )
            self.assertEqual(meta["applied"], True)
            self.assertEqual(meta["routes_with_evidence"], 3)  # 476, 479, 480
            self.assertEqual(meta["boosted_entries"], 2)       # 476 and 479 present in rankings
            scores_by_route = {r["route_id"]: r["combined_score"] for r in out}
            self.assertAlmostEqual(scores_by_route["route_476"], 0.61, places=6)
            self.assertAlmostEqual(scores_by_route["route_479"], 0.56, places=6)
            self.assertAlmostEqual(scores_by_route["route_999"], 0.5, places=6)


# ===========================================================================
# 9. Reorder gate fires
# ===========================================================================


class TestReorderGateFires(unittest.TestCase):
    def test_lower_candidate_with_evidence_overtakes_when_gap_within_threshold(self) -> None:
        # Pre-bias gap = 0.02 (within _PLAN_BIAS_REORDER_GAP=0.10).
        rankings_in = [
            _ranking("route_LEAD", 0.60),
            _ranking("route_476", 0.58),
        ]
        # Three evidence tokens for route_476 -> +0.03 -> final 0.61, overtakes 0.60.
        seam = {"1": [1], "2": [2], "3": [3]}
        sheet_routes = {1: ["route_476"], 2: ["route_476"], 3: ["route_476"]}
        with _FlagContext(**{PT1_FLAG: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index",
                             return_value=seam), \
                patch.object(M, "_sheet_to_route_ids_from_packet_index",
                             return_value=sheet_routes):
            out, meta = M._apply_print_to_sheet_plausibility_boost(
                rankings_in, _group(["1", "2", "3"])
            )
            self.assertEqual(meta["applied"], True)
            self.assertTrue(meta["reordered"])
            self.assertEqual(out[0]["route_id"], "route_476")
            self.assertEqual(out[1]["route_id"], "route_LEAD")


# ===========================================================================
# 10. Reorder gate blocked
# ===========================================================================


class TestReorderGateBlocked(unittest.TestCase):
    def test_boost_applied_but_no_reorder_when_gap_too_large(self) -> None:
        # Pre-bias gap = 0.20 > _PLAN_BIAS_REORDER_GAP=0.10.
        rankings_in = [
            _ranking("route_LEAD", 0.80),
            _ranking("route_476", 0.60),
        ]
        seam = {"1": [1], "2": [2], "3": [3]}
        sheet_routes = {1: ["route_476"], 2: ["route_476"], 3: ["route_476"]}
        with _FlagContext(**{PT1_FLAG: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index",
                             return_value=seam), \
                patch.object(M, "_sheet_to_route_ids_from_packet_index",
                             return_value=sheet_routes):
            out, meta = M._apply_print_to_sheet_plausibility_boost(
                rankings_in, _group(["1", "2", "3"])
            )
            self.assertEqual(meta["applied"], True)
            self.assertFalse(meta["reordered"])
            # route_476 received the cap boost but ordering preserved.
            self.assertEqual(out[0]["route_id"], "route_LEAD")
            self.assertEqual(out[1]["route_id"], "route_476")
            # The boost was still recorded on the loser.
            self.assertAlmostEqual(out[1]["combined_score"], 0.63, places=6)


# ===========================================================================
# 11. Input immutability
# ===========================================================================


class TestInputsNotMutated(unittest.TestCase):
    def test_inputs_unchanged_after_boost(self) -> None:
        rankings_in = [
            _ranking("route_476", 0.6),
            _ranking("route_479", 0.55),
        ]
        group = _group(["7", "15"])
        rankings_snapshot = copy.deepcopy(rankings_in)
        group_snapshot = copy.deepcopy(group)
        with _FlagContext(**{PT1_FLAG: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index",
                             return_value={"7": [7], "15": [15]}), \
                patch.object(M, "_sheet_to_route_ids_from_packet_index",
                             return_value={7: ["route_476"], 15: ["route_479"]}):
            out, meta = M._apply_print_to_sheet_plausibility_boost(rankings_in, group)
            self.assertEqual(rankings_in, rankings_snapshot)
            self.assertEqual(group, group_snapshot)
            # The returned list is a new object when applying.
            self.assertIsNot(out, rankings_in)
            # Each boosted dict is a copy, not the original reference.
            self.assertIsNot(out[0], rankings_in[0])


# ===========================================================================
# 12. Diagnostic shape
# ===========================================================================


class TestDiagnosticShape(unittest.TestCase):
    def test_meta_keys_and_types_complete(self) -> None:
        rankings_in = [_ranking("route_476", 0.6)]
        with _FlagContext(**{PT1_FLAG: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index",
                             return_value={"7": [7]}), \
                patch.object(M, "_sheet_to_route_ids_from_packet_index",
                             return_value={7: ["route_476"]}):
            _, meta = M._apply_print_to_sheet_plausibility_boost(
                rankings_in, _group(["7"])
            )
            self.assertEqual(set(meta.keys()), REQUIRED_META_KEYS)
            self.assertIsInstance(meta["applied"], bool)
            self.assertIsInstance(meta["flag_enabled"], bool)
            self.assertIsInstance(meta["tokens_considered"], int)
            self.assertIsInstance(meta["tokens_resolving_to_sheets"], int)
            self.assertIsInstance(meta["routes_with_evidence"], int)
            self.assertIsInstance(meta["boosted_entries"], int)
            self.assertIsInstance(meta["max_delta_applied"], float)
            self.assertIsInstance(meta["top2_gap_before_bias"], float)
            self.assertIsInstance(meta["reordered"], bool)
            self.assertIsInstance(meta["evidence_by_route_id"], dict)
            self.assertIsInstance(meta["evidence_by_sheet_int"], dict)


# ===========================================================================
# 13. Never raises on pathological inputs
# ===========================================================================


class TestNeverRaises(unittest.TestCase):
    def test_none_rankings(self) -> None:
        with _FlagContext(**{PT1_FLAG: True}):
            out, meta = M._apply_print_to_sheet_plausibility_boost([], _group(["7"]))
            self.assertEqual(out, [])
            self.assertEqual(meta["reason_if_not_applied"], "no_rankings")

    def test_non_dict_entries_in_rankings(self) -> None:
        rankings_in: List[Any] = [_ranking("route_476", 0.6), "not-a-dict", 42, None]
        with _FlagContext(**{PT1_FLAG: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index",
                             return_value={"7": [7]}), \
                patch.object(M, "_sheet_to_route_ids_from_packet_index",
                             return_value={7: ["route_476"]}):
            out, meta = M._apply_print_to_sheet_plausibility_boost(
                rankings_in, _group(["7"])
            )
            # Non-dict entries passed through unchanged; dict entry boosted.
            self.assertEqual(len(out), 4)
            self.assertEqual(out[1], "not-a-dict")
            self.assertEqual(out[2], 42)
            self.assertIsNone(out[3])
            self.assertEqual(meta["applied"], True)

    def test_seam_raises(self) -> None:
        rankings_in = [_ranking("route_476", 0.6)]
        with _FlagContext(**{PT1_FLAG: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index",
                             side_effect=RuntimeError("boom")), \
                patch.object(M, "_sheet_to_route_ids_from_packet_index",
                             return_value={7: ["route_476"]}):
            out, meta = M._apply_print_to_sheet_plausibility_boost(
                rankings_in, _group(["7"])
            )
            self.assertIs(out, rankings_in)
            self.assertEqual(meta["reason_if_not_applied"], "seam_empty")

    def test_broken_normalized_group(self) -> None:
        rankings_in = [_ranking("route_476", 0.6)]
        with _FlagContext(**{PT1_FLAG: True}):
            # normalized_group is None / non-dict
            for bad in (None, [], "not a dict", 42):
                out, meta = M._apply_print_to_sheet_plausibility_boost(
                    rankings_in, bad  # type: ignore[arg-type]
                )
                self.assertIs(out, rankings_in)
                self.assertEqual(meta["reason_if_not_applied"], "no_numeric_print_tokens_in_group")


# ===========================================================================
# 14. Stacking with existing _plan_aware_ranking_boost output
# ===========================================================================


class TestStackingWithExistingBoost(unittest.TestCase):
    def test_pt1_delta_layered_on_post_existing_boost_scores(self) -> None:
        # Simulate the upstream `_plan_aware_ranking_boost` having already
        # raised route_476's combined_score from 0.60 to 0.62 and recorded
        # original_score=0.60, plan_adjusted_score=0.62.
        upstream_boosted = {
            "route_id":             "route_476",
            "route_name":           "name_route_476",
            "score":                0.62,
            "combined_score":       0.62,
            "route_score":          0.0,
            "route_length_ft":      1000.0,
            "original_score":       0.60,
            "plan_adjusted_score":  0.62,
        }
        rankings_in = [upstream_boosted, _ranking("route_999", 0.55)]
        with _FlagContext(**{PT1_FLAG: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index",
                             return_value={"7": [7]}), \
                patch.object(M, "_sheet_to_route_ids_from_packet_index",
                             return_value={7: ["route_476"]}):
            out, meta = M._apply_print_to_sheet_plausibility_boost(
                rankings_in, _group(["7"])
            )
            self.assertEqual(meta["applied"], True)
            r476 = next(r for r in out if r["route_id"] == "route_476")
            # PT.1 delta is +0.01 added on top of the already-boosted 0.62.
            self.assertAlmostEqual(r476["combined_score"], 0.63, places=6)
            # Original/plan_adjusted_score preserved (NOT overwritten by PT.1).
            self.assertAlmostEqual(r476["original_score"], 0.60, places=6)
            self.assertAlmostEqual(r476["plan_adjusted_score"], 0.62, places=6)
            # PT.1 records its own delta separately.
            self.assertAlmostEqual(r476["print_to_sheet_boost_delta"], 0.01, places=6)
            # Combined effect across layers ≤ 2 * _PLAN_BIAS_MAX_BOOST.
            total_delta = r476["combined_score"] - r476["original_score"]
            self.assertLessEqual(total_delta, 2 * M._PLAN_BIAS_MAX_BOOST + 1e-9)


# ===========================================================================
# 15. Respects mocked seam outputs
# ===========================================================================


class TestRespectsSeamOutputs(unittest.TestCase):
    def test_evidence_by_sheet_int_matches_patched_seam_exactly(self) -> None:
        # The boost MUST honor the patched seam output — not the real
        # CURRENT_PACKET_PRINT_SHEET_INDEX values.
        rankings_in = [
            _ranking("route_ALPHA", 0.6),
            _ranking("route_BETA", 0.55),
        ]
        # Token "7" -> sheet 42 (NOT the real-world mapping).
        # Token "9" -> sheet 99 -> route_BETA.
        seam = {"7": [42], "9": [99]}
        sheet_routes = {42: ["route_ALPHA"], 99: ["route_BETA"]}
        with _FlagContext(**{PT1_FLAG: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index",
                             return_value=seam), \
                patch.object(M, "_sheet_to_route_ids_from_packet_index",
                             return_value=sheet_routes):
            out, meta = M._apply_print_to_sheet_plausibility_boost(
                rankings_in, _group(["7", "9"])
            )
            self.assertEqual(meta["applied"], True)
            self.assertEqual(meta["evidence_by_sheet_int"]["42"], ["7"])
            self.assertEqual(meta["evidence_by_sheet_int"]["99"], ["9"])
            self.assertEqual(meta["evidence_by_route_id"]["route_ALPHA"], ["7"])
            self.assertEqual(meta["evidence_by_route_id"]["route_BETA"], ["9"])
            scores_by_route = {r["route_id"]: r["combined_score"] for r in out}
            self.assertAlmostEqual(scores_by_route["route_ALPHA"], 0.61, places=6)
            self.assertAlmostEqual(scores_by_route["route_BETA"], 0.56, places=6)


# ===========================================================================
# 15. PT.ACT R1 — diagnostic schema hardening (no behavior change)
# ===========================================================================


class TestR1MetaShape(unittest.TestCase):
    """R1 adds: mode / reorder_attempted / reorder_blocked_reason /
    selection_impact. No scoring, no reorder math, no flag interaction
    changes."""

    def test_off_mode_emits_mode_off_and_layer_not_applied(self) -> None:
        rankings_in = [_ranking("route_476", 0.6), _ranking("route_477", 0.55)]
        with _FlagContext(**{PT1_FLAG: False}):
            out, meta = M._apply_print_to_sheet_plausibility_boost(
                rankings_in, _group(["7"])
            )
            self.assertIs(out, rankings_in)
            self.assertEqual(meta["mode"], "off")
            self.assertFalse(meta["reorder_attempted"])
            self.assertEqual(meta["reorder_blocked_reason"], "layer_not_applied")
            self.assertIsNone(meta["selection_impact"])

    def test_live_mode_early_return_keeps_layer_not_applied(self) -> None:
        # Flag ON but seam empty -> reason_if_not_applied="seam_empty".
        # mode must read "live" (the flag was on); reorder/selection_impact
        # remain at the layer_not_applied / None defaults because the
        # reorder step is not reached.
        rankings_in = [_ranking("route_476", 0.6)]
        with _FlagContext(**{PT1_FLAG: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index", return_value={}), \
                patch.object(M, "_sheet_to_route_ids_from_packet_index", return_value={}):
            out, meta = M._apply_print_to_sheet_plausibility_boost(
                rankings_in, _group(["7"])
            )
            self.assertEqual(meta["mode"], "live")
            self.assertEqual(meta["reason_if_not_applied"], "seam_empty")
            self.assertFalse(meta["reorder_attempted"])
            self.assertEqual(meta["reorder_blocked_reason"], "layer_not_applied")
            self.assertIsNone(meta["selection_impact"])

    def test_live_mode_with_boost_emits_selection_impact(self) -> None:
        # Pre-bias gap = 0.01 (<= 0.10 threshold), and route_477 gets 3 tokens
        # of evidence (3 * 0.01 = cap = 0.03). 0.59 + 0.03 = 0.62 > 0.60 ->
        # gate fires AND order flips.
        rankings_in = [_ranking("route_476", 0.60), _ranking("route_477", 0.59)]
        seam_map = {"7": [42], "8": [43], "9": [44]}
        s2r = {42: ["route_477"], 43: ["route_477"], 44: ["route_477"]}
        with _FlagContext(**{PT1_FLAG: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index", return_value=seam_map), \
                patch.object(M, "_sheet_to_route_ids_from_packet_index", return_value=s2r):
            out, meta = M._apply_print_to_sheet_plausibility_boost(
                rankings_in, _group(["7", "8", "9"])
            )
            self.assertEqual(meta["mode"], "live")
            self.assertTrue(meta["applied"])
            self.assertTrue(meta["reorder_attempted"])
            self.assertIsNone(meta["reorder_blocked_reason"])
            self.assertEqual(meta["selection_impact"]["pre_layer_top1"], "route_476")
            self.assertEqual(meta["selection_impact"]["post_layer_top1"], "route_477")
            self.assertTrue(meta["selection_impact"]["changed"])

    def test_reorder_attempted_false_with_gap_above_threshold(self) -> None:
        # Pre-bias gap = 0.30 -> gate does not fire even though boost applies.
        rankings_in = [_ranking("route_476", 0.85), _ranking("route_477", 0.55)]
        with _FlagContext(**{PT1_FLAG: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index",
                             return_value={"7": [42]}), \
                patch.object(M, "_sheet_to_route_ids_from_packet_index",
                             return_value={42: ["route_476"]}):
            out, meta = M._apply_print_to_sheet_plausibility_boost(
                rankings_in, _group(["7"])
            )
            self.assertEqual(meta["mode"], "live")
            self.assertTrue(meta["applied"])
            self.assertFalse(meta["reordered"])
            self.assertFalse(meta["reorder_attempted"])
            self.assertEqual(meta["reorder_blocked_reason"], "gap_above_threshold")
            self.assertEqual(meta["selection_impact"]["pre_layer_top1"], "route_476")
            self.assertEqual(meta["selection_impact"]["post_layer_top1"], "route_476")
            self.assertFalse(meta["selection_impact"]["changed"])

    def test_reorder_attempted_false_with_single_candidate(self) -> None:
        rankings_in = [_ranking("route_476", 0.6)]
        with _FlagContext(**{PT1_FLAG: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index",
                             return_value={"7": [42]}), \
                patch.object(M, "_sheet_to_route_ids_from_packet_index",
                             return_value={42: ["route_476"]}):
            out, meta = M._apply_print_to_sheet_plausibility_boost(
                rankings_in, _group(["7"])
            )
            self.assertEqual(meta["mode"], "live")
            self.assertTrue(meta["applied"])
            self.assertFalse(meta["reordered"])
            self.assertFalse(meta["reorder_attempted"])
            self.assertEqual(meta["reorder_blocked_reason"], "single_candidate")
            self.assertEqual(meta["selection_impact"]["pre_layer_top1"], "route_476")
            self.assertEqual(meta["selection_impact"]["post_layer_top1"], "route_476")
            self.assertFalse(meta["selection_impact"]["changed"])

    def test_selection_impact_unchanged_when_top1_was_already_boosted(self) -> None:
        # Top-1 (route_476) receives the boost; order does not change but
        # gate still fires (gap small). selection_impact.changed=False.
        rankings_in = [_ranking("route_476", 0.60), _ranking("route_477", 0.55)]
        with _FlagContext(**{PT1_FLAG: True}), \
                patch.object(M, "_print_to_sheets_from_packet_index",
                             return_value={"7": [42]}), \
                patch.object(M, "_sheet_to_route_ids_from_packet_index",
                             return_value={42: ["route_476"]}):
            out, meta = M._apply_print_to_sheet_plausibility_boost(
                rankings_in, _group(["7"])
            )
            self.assertEqual(meta["mode"], "live")
            self.assertTrue(meta["reorder_attempted"])
            self.assertIsNone(meta["reorder_blocked_reason"])
            self.assertFalse(meta["reordered"])
            self.assertEqual(meta["selection_impact"]["pre_layer_top1"], "route_476")
            self.assertEqual(meta["selection_impact"]["post_layer_top1"], "route_476")
            self.assertFalse(meta["selection_impact"]["changed"])


if __name__ == "__main__":
    unittest.main()
