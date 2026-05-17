"""Layer-1 synthetic tests for evaluate_localized_subextent_plausibility.

No PDFs, no fixtures, no STATE. Every test constructs synthetic
normalized-group and sheet-origins dicts in-process.

What is being locked down:
  - input-validation refusal paths (no_data classifications)
  - single-sheet sub-window classification matrix
  - multi-sheet contiguous-chain enumeration and rejection
  - ambiguity preservation rules (multi-strong, strong-vs-weak)
  - anchor corroboration (matchline_crossings as the gating anchor)
  - input immutability: helper does NOT mutate caller dicts/lists
  - threshold-boundary stability across the band edges
  - output schema completeness and deterministic ordering

COMMAND
-------
    python -m pytest backend/tests/test_localized_subextent_plausibility.py -v

The helper performs no I/O; this suite has no fixture dependencies.
"""

from __future__ import annotations

import copy
import json
import os
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List

_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# Required env defaults — helper itself reads nothing from the environment.
os.environ.setdefault("TRUELINE_JWT_SECRET", "p52b-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "p52b-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from app.services import engineering_plan_parser as pp  # noqa: E402

evaluate = pp.evaluate_localized_subextent_plausibility


# ---------------------------------------------------------------------------
# Small constructors so test intent is readable
# ---------------------------------------------------------------------------

def _group(span_ft: Any, print_tokens: List[Any]) -> Dict[str, Any]:
    return {"span_ft": span_ft, "print_tokens": list(print_tokens)}


def _origin(
    length_ft: int,
    method: str = "matchline_chain",
    confidence: str = "high",
    has_reset: bool = False,
) -> Dict[str, Any]:
    return {
        "origin_ft": 0,
        "end_ft": int(length_ft),
        "length_ft": int(length_ft),
        "method": method,
        "confidence": confidence,
        "chain_anchor_sheets": [],
        "has_reset_boundary": bool(has_reset),
        "matchline_count": 2,
        "callout_count": 0,
        "notes": [],
    }


def _chain(*pairs: List[int]) -> Dict[int, List[int]]:
    """Build a symmetric chain_adjacency map from consecutive sheet pairs."""
    adj: Dict[int, List[int]] = {}
    for a, b in pairs:
        adj.setdefault(int(a), []).append(int(b))
        adj.setdefault(int(b), []).append(int(a))
    return adj


# ===========================================================================
# V — Input-validation refusal paths (6 tests)
# ===========================================================================

class InputValidation(unittest.TestCase):

    def test_v1_returns_no_data_when_group_is_none(self) -> None:
        result = evaluate(None, {})
        self.assertEqual(result["classification"], "no_data")
        self.assertFalse(result["would_boost"])
        self.assertIsNone(result["best_candidate_index"])

    def test_v2_returns_no_data_when_group_is_not_dict(self) -> None:
        result = evaluate("not a dict", {})  # type: ignore[arg-type]
        self.assertEqual(result["classification"], "no_data")
        self.assertEqual(result["candidate_subextents"], [])

    def test_v3_returns_no_data_when_span_missing(self) -> None:
        result = evaluate({"print_tokens": [3]}, {3: _origin(938)})
        self.assertEqual(result["classification"], "no_data")

    def test_v4_returns_no_data_when_span_zero(self) -> None:
        result = evaluate(_group(0, [3]), {3: _origin(938)})
        self.assertEqual(result["classification"], "no_data")

    def test_v5_returns_no_data_when_span_negative(self) -> None:
        result = evaluate(_group(-100, [3]), {3: _origin(938)})
        self.assertEqual(result["classification"], "no_data")

    def test_v6_returns_no_data_when_span_non_numeric(self) -> None:
        result = evaluate(_group("not-a-number", [3]), {3: _origin(938)})
        self.assertEqual(result["classification"], "no_data")


# ===========================================================================
# S — Single-sheet plausibility matrix (8 tests)
# ===========================================================================

class SingleSheetPlausibility(unittest.TestCase):

    def test_s1_high_conf_with_anchor_is_fit_strong(self) -> None:
        result = evaluate(
            _group(300, [3]),
            {3: _origin(938)},
            anchor_hints={"matchline_crossings": [3]},
        )
        self.assertEqual(result["classification"], "subextent_fit_strong")
        self.assertTrue(result["would_boost"])
        self.assertEqual(result["best_candidate_index"], 0)
        self.assertEqual(len(result["candidate_subextents"]), 1)
        cand = result["candidate_subextents"][0]
        self.assertEqual(cand["sheet_set"], [3])
        self.assertEqual(cand["chain_method"], "single_sheet")
        self.assertEqual(cand["corroborating_anchors"], ["matchline_crossing:3"])
        self.assertEqual(cand["demotion_reasons"], [])
        self.assertEqual(result["confidence"], "high")

    def test_s2_high_conf_without_anchor_is_fit_weak(self) -> None:
        result = evaluate(
            _group(300, [3]),
            {3: _origin(938)},
        )
        self.assertEqual(result["classification"], "subextent_fit_weak")
        self.assertFalse(result["would_boost"])
        cand = result["candidate_subextents"][0]
        self.assertIn("no_corroborating_anchor", cand["demotion_reasons"])

    def test_s3_trivial_ratio_is_fit_weak_with_trivial_reason(self) -> None:
        # 30/938 ≈ 0.032 < _RATIO_TRIVIAL_MIN
        result = evaluate(
            _group(30, [3]),
            {3: _origin(938)},
            anchor_hints={"matchline_crossings": [3]},
        )
        self.assertEqual(result["classification"], "subextent_fit_weak")
        cand = result["candidate_subextents"][0]
        self.assertTrue(
            any("fit_ratio_below_trivial" in r for r in cand["demotion_reasons"])
        )
        self.assertTrue(
            any("trivial threshold" in r for r in result["reasons"])
        )

    def test_s4_exact_equality_is_fit_strong(self) -> None:
        result = evaluate(
            _group(938, [3]),
            {3: _origin(938)},
            anchor_hints={"matchline_crossings": [3]},
        )
        self.assertEqual(result["classification"], "subextent_fit_strong")
        self.assertEqual(result["candidate_subextents"][0]["fit_ratio"], 1.0)

    def test_s5_overflow_is_subextent_overflow(self) -> None:
        result = evaluate(
            _group(1000, [3]),
            {3: _origin(938)},
            anchor_hints={"matchline_crossings": [3]},
        )
        self.assertEqual(result["classification"], "subextent_overflow")
        self.assertFalse(result["would_boost"])
        self.assertIsNone(result["best_candidate_index"])

    def test_s6_low_conf_demotes_to_fit_weak(self) -> None:
        result = evaluate(
            _group(300, [3]),
            {3: _origin(938, method="callouts_only", confidence="low")},
            anchor_hints={"matchline_crossings": [3]},
        )
        self.assertEqual(result["classification"], "subextent_fit_weak")
        cand = result["candidate_subextents"][0]
        self.assertIn("low_sheet_confidence", cand["demotion_reasons"])

    def test_s7_reset_boundary_demotes_to_fit_weak(self) -> None:
        result = evaluate(
            _group(300, [3]),
            {3: _origin(938, has_reset=True)},
            anchor_hints={"matchline_crossings": [3]},
        )
        self.assertEqual(result["classification"], "subextent_fit_weak")
        cand = result["candidate_subextents"][0]
        self.assertIn("reset_boundary_in_candidate", cand["demotion_reasons"])
        self.assertIn("reset_boundary_in_candidate", result["ambiguity_flags"])
        self.assertTrue(result["has_reset_boundary"])

    def test_s8_isolated_method_is_subextent_uncertain(self) -> None:
        result = evaluate(
            _group(300, [3]),
            {3: _origin(100, method="single_sheet_isolated", confidence="uncertain")},
        )
        self.assertEqual(result["classification"], "subextent_uncertain")
        self.assertEqual(result["covered_sheets"], [])


# ===========================================================================
# M — Multi-sheet contiguous-chain matrix (8 tests)
# ===========================================================================

class MultiSheetChainPlausibility(unittest.TestCase):

    def test_m1_chain_with_adjacency_and_anchor_is_fit_strong(self) -> None:
        result = evaluate(
            _group(1500, [3, 4]),
            {3: _origin(1000), 4: _origin(1000)},
            chain_adjacency=_chain([3, 4]),
            anchor_hints={"matchline_crossings": [3]},
        )
        self.assertEqual(result["classification"], "subextent_fit_strong")
        top = result["candidate_subextents"][0]
        self.assertEqual(top["sheet_set"], [3, 4])
        self.assertEqual(top["chain_method"], "contiguous_chain")
        self.assertEqual(top["max_subextent_ft"], 2000)

    def test_m2_chain_without_adjacency_with_anchor_is_fit_weak(self) -> None:
        result = evaluate(
            _group(1500, [3, 4]),
            {3: _origin(1000), 4: _origin(1000)},
            anchor_hints={"matchline_crossings": [3]},
        )
        self.assertEqual(result["classification"], "subextent_fit_weak")
        chain = next(
            (c for c in result["candidate_subextents"]
             if c["chain_method"] == "contiguous_chain"),
            None,
        )
        self.assertIsNotNone(chain)
        self.assertIn("chain_adjacency_unverified", chain["demotion_reasons"])
        self.assertIn("chain_adjacency_unverified", result["ambiguity_flags"])

    def test_m3_chain_without_adjacency_without_anchor_is_fit_weak(self) -> None:
        result = evaluate(
            _group(1500, [3, 4]),
            {3: _origin(1000), 4: _origin(1000)},
        )
        self.assertEqual(result["classification"], "subextent_fit_weak")
        chain = next(
            (c for c in result["candidate_subextents"]
             if c["chain_method"] == "contiguous_chain"),
            None,
        )
        self.assertIsNotNone(chain)
        self.assertIn("chain_adjacency_unverified", chain["demotion_reasons"])
        self.assertIn("no_corroborating_anchor", chain["demotion_reasons"])

    def test_m4_non_contiguous_pair_rejects_chain_candidate(self) -> None:
        result = evaluate(
            _group(1500, [3, 7]),
            {3: _origin(2000), 7: _origin(2000)},
        )
        chain = next(
            (c for c in result["candidate_subextents"]
             if c["chain_method"] == "contiguous_chain"),
            None,
        )
        self.assertIsNone(chain)
        single_sheets = [
            c["sheet_set"] for c in result["candidate_subextents"]
            if c["chain_method"] == "single_sheet"
        ]
        self.assertIn([3], single_sheets)
        self.assertIn([7], single_sheets)
        self.assertTrue(
            any("non-contiguous sheet set" in r for r in result["reasons"])
        )

    def test_m5_chain_with_reset_boundary_demotes_to_fit_weak(self) -> None:
        result = evaluate(
            _group(1500, [3, 4]),
            {3: _origin(1000, has_reset=True), 4: _origin(1000)},
            chain_adjacency=_chain([3, 4]),
            anchor_hints={"matchline_crossings": [3, 4]},
        )
        self.assertEqual(result["classification"], "subextent_fit_weak")
        chain = next(
            (c for c in result["candidate_subextents"]
             if c["chain_method"] == "contiguous_chain"),
            None,
        )
        self.assertIsNotNone(chain)
        self.assertIn("reset_boundary_in_candidate", chain["demotion_reasons"])
        self.assertTrue(result["has_reset_boundary"])

    def test_m6_all_candidates_overflow_is_subextent_overflow(self) -> None:
        result = evaluate(
            _group(5000, [3, 4]),
            {3: _origin(938), 4: _origin(1003)},
            chain_adjacency=_chain([3, 4]),
            anchor_hints={"matchline_crossings": [3, 4]},
        )
        self.assertEqual(result["classification"], "subextent_overflow")
        for c in result["candidate_subextents"]:
            self.assertGreater(c["fit_ratio"], 1.0)

    def test_m7_chain_at_trivial_floor_is_fit_weak(self) -> None:
        # span 100 / chain sum 2000 = 0.05 exactly
        result = evaluate(
            _group(100, [3, 4]),
            {3: _origin(1000), 4: _origin(1000)},
            chain_adjacency=_chain([3, 4]),
            anchor_hints={"matchline_crossings": [3, 4]},
        )
        self.assertEqual(result["classification"], "subextent_fit_weak")
        chain = next(
            (c for c in result["candidate_subextents"]
             if c["chain_method"] == "contiguous_chain"),
            None,
        )
        self.assertIsNotNone(chain)
        self.assertEqual(chain["fit_ratio"], 0.05)

    def test_m8_three_sheet_chain_with_reset_demotes_to_fit_weak(self) -> None:
        result = evaluate(
            _group(1500, [3, 4, 5]),
            {
                3: _origin(700),
                4: _origin(700, has_reset=True),
                5: _origin(700),
            },
            chain_adjacency=_chain([3, 4], [4, 5]),
            anchor_hints={"matchline_crossings": [4]},
        )
        self.assertEqual(result["classification"], "subextent_fit_weak")
        self.assertTrue(result["has_reset_boundary"])


# ===========================================================================
# A — Ambiguity preservation (5 tests)
# ===========================================================================

class AmbiguityPreservation(unittest.TestCase):

    def test_a1_two_strong_candidates_is_fit_ambiguous(self) -> None:
        result = evaluate(
            _group(1500, [3, 7]),
            {3: _origin(2000), 7: _origin(2000)},
            anchor_hints={"matchline_crossings": [3, 7]},
        )
        self.assertEqual(result["classification"], "subextent_fit_ambiguous")
        self.assertIsNone(result["best_candidate_index"])
        self.assertIn("multiple_strong_candidates", result["ambiguity_flags"])
        self.assertEqual(result["confidence"], "medium")

    def test_a2_strong_beats_weak_is_fit_strong(self) -> None:
        result = evaluate(
            _group(1500, [3, 7]),
            {3: _origin(2000), 7: _origin(2000)},
            anchor_hints={"matchline_crossings": [3]},  # only sheet 3
        )
        self.assertEqual(result["classification"], "subextent_fit_strong")
        top = result["candidate_subextents"][result["best_candidate_index"]]
        self.assertEqual(top["sheet_set"], [3])
        self.assertEqual(top["corroborating_anchors"], ["matchline_crossing:3"])
        weak_present = any(
            c["sheet_set"] == [7] for c in result["candidate_subextents"]
        )
        self.assertTrue(weak_present)

    def test_a3_two_strong_equally_has_none_best_index(self) -> None:
        result = evaluate(
            _group(1500, [3, 7]),
            {3: _origin(2000), 7: _origin(2000)},
            anchor_hints={"matchline_crossings": [3, 7]},
        )
        self.assertIsNone(result["best_candidate_index"])
        self.assertEqual(result["classification"], "subextent_fit_ambiguous")

    def test_a4_helper_ignores_extraneous_normalized_group_keys(self) -> None:
        group = {
            "span_ft": 300,
            "print_tokens": [3],
            "p52_evidence_for_disagree": {"classification": "out_of_range"},
            "some_other_extra_key": "ignored",
        }
        result = evaluate(
            group,
            {3: _origin(938)},
            anchor_hints={"matchline_crossings": [3]},
        )
        self.assertEqual(result["classification"], "subextent_fit_strong")
        self.assertNotIn("p52_disagreement", result["ambiguity_flags"])

    def test_a5_all_candidates_overflow(self) -> None:
        result = evaluate(
            _group(1500, [3, 4]),
            {3: _origin(100), 4: _origin(100)},
            chain_adjacency=_chain([3, 4]),
            anchor_hints={"matchline_crossings": [3, 4]},
        )
        self.assertEqual(result["classification"], "subextent_overflow")
        self.assertIsNone(result["best_candidate_index"])
        for c in result["candidate_subextents"]:
            self.assertGreater(c["fit_ratio"], 1.0)


# ===========================================================================
# C — Anchor corroboration semantics (5 tests)
# ===========================================================================

class AnchorCorroboration(unittest.TestCase):

    def test_c1_matchline_anchor_promotes_to_fit_strong(self) -> None:
        without = evaluate(_group(300, [3]), {3: _origin(938)})
        with_anchor = evaluate(
            _group(300, [3]),
            {3: _origin(938)},
            anchor_hints={"matchline_crossings": [3]},
        )
        self.assertEqual(without["classification"], "subextent_fit_weak")
        self.assertEqual(with_anchor["classification"], "subextent_fit_strong")

    def test_c2_splice_ids_alone_do_not_corroborate(self) -> None:
        result = evaluate(
            _group(300, [3]),
            {3: _origin(938)},
            anchor_hints={"splice_ids": ["SPL-12"]},
        )
        self.assertEqual(result["classification"], "subextent_fit_weak")
        cand = result["candidate_subextents"][0]
        self.assertEqual(cand["corroborating_anchors"], [])
        self.assertIn("no_corroborating_anchor", cand["demotion_reasons"])

    def test_c3_anchor_hints_none_is_fit_weak(self) -> None:
        result = evaluate(
            _group(300, [3]),
            {3: _origin(938)},
            anchor_hints=None,
        )
        self.assertEqual(result["classification"], "subextent_fit_weak")

    def test_c4_anchor_hints_empty_dict_is_fit_weak(self) -> None:
        result = evaluate(
            _group(300, [3]),
            {3: _origin(938)},
            anchor_hints={},
        )
        self.assertEqual(result["classification"], "subextent_fit_weak")

    def test_c5_anchor_hints_unknown_keys_are_ignored(self) -> None:
        result = evaluate(
            _group(300, [3]),
            {3: _origin(938)},
            anchor_hints={"unknown_key": ["x"], "another": 42},
        )
        self.assertEqual(result["classification"], "subextent_fit_weak")


# ===========================================================================
# I — Input immutability (4 tests)
# ===========================================================================

class InputImmutability(unittest.TestCase):

    def test_i1_normalized_group_is_not_mutated(self) -> None:
        group = {"span_ft": 300, "print_tokens": [3]}
        snapshot = copy.deepcopy(group)
        evaluate(
            group,
            {3: _origin(938)},
            anchor_hints={"matchline_crossings": [3]},
        )
        self.assertEqual(group, snapshot)

    def test_i2_sheet_origins_is_not_mutated(self) -> None:
        origins = {3: _origin(938)}
        snapshot = copy.deepcopy(origins)
        evaluate(
            _group(300, [3]),
            origins,
            anchor_hints={"matchline_crossings": [3]},
        )
        self.assertEqual(origins, snapshot)

    def test_i3_print_to_sheets_is_not_mutated(self) -> None:
        mapping = {"P3": [3]}
        snapshot = copy.deepcopy(mapping)
        evaluate(
            _group(300, ["P3"]),
            {3: _origin(938)},
            print_to_sheets=mapping,
            anchor_hints={"matchline_crossings": [3]},
        )
        self.assertEqual(mapping, snapshot)

    def test_i4_anchor_hints_is_not_mutated(self) -> None:
        anchor = {"matchline_crossings": [3], "ap_tokens": ["AP-1"]}
        snapshot = copy.deepcopy(anchor)
        evaluate(
            _group(300, [3]),
            {3: _origin(938)},
            anchor_hints=anchor,
        )
        self.assertEqual(anchor, snapshot)


# ===========================================================================
# T — Threshold-boundary tests (6 tests)
# ===========================================================================

class ThresholdBoundaries(unittest.TestCase):

    def test_t1_ratio_at_trivial_floor_is_fit_weak_band(self) -> None:
        # 50 / 1000 = 0.05 — at the floor, not below it; goes to weak band.
        result = evaluate(
            _group(50, [3]),
            {3: _origin(1000)},
            anchor_hints={"matchline_crossings": [3]},
        )
        self.assertEqual(result["classification"], "subextent_fit_weak")
        cand = result["candidate_subextents"][0]
        self.assertEqual(cand["fit_ratio"], 0.05)
        self.assertTrue(
            any("below_subextent_min" in r for r in cand["demotion_reasons"])
        )

    def test_t2_ratio_just_below_trivial_floor_is_fit_weak_trivial(self) -> None:
        # 49 / 1000 = 0.049 — below trivial floor.
        result = evaluate(
            _group(49, [3]),
            {3: _origin(1000)},
            anchor_hints={"matchline_crossings": [3]},
        )
        self.assertEqual(result["classification"], "subextent_fit_weak")
        cand = result["candidate_subextents"][0]
        self.assertEqual(cand["fit_ratio"], 0.049)
        self.assertTrue(
            any("below_trivial" in r for r in cand["demotion_reasons"])
        )
        self.assertTrue(
            any("trivial threshold" in r for r in result["reasons"])
        )

    def test_t3_ratio_at_subextent_min_is_fit_strong(self) -> None:
        # 150 / 1000 = 0.15 — at the strong-band floor.
        result = evaluate(
            _group(150, [3]),
            {3: _origin(1000)},
            anchor_hints={"matchline_crossings": [3]},
        )
        self.assertEqual(result["classification"], "subextent_fit_strong")
        self.assertEqual(result["candidate_subextents"][0]["fit_ratio"], 0.15)

    def test_t4_ratio_at_one_is_fit_strong(self) -> None:
        result = evaluate(
            _group(1000, [3]),
            {3: _origin(1000)},
            anchor_hints={"matchline_crossings": [3]},
        )
        self.assertEqual(result["classification"], "subextent_fit_strong")
        self.assertEqual(result["candidate_subextents"][0]["fit_ratio"], 1.0)

    def test_t5_ratio_above_one_is_overflow(self) -> None:
        result = evaluate(
            _group(1001, [3]),
            {3: _origin(1000)},
            anchor_hints={"matchline_crossings": [3]},
        )
        self.assertEqual(result["classification"], "subextent_overflow")

    def test_t6_fit_ratio_rounded_to_six_decimal_places(self) -> None:
        # 100 / 330 is irrational-style; must be stably rounded to 6 dp.
        result = evaluate(
            _group(100, [3]),
            {3: _origin(330)},
            anchor_hints={"matchline_crossings": [3]},
        )
        cand = result["candidate_subextents"][0]
        self.assertEqual(cand["fit_ratio"], round(100 / 330, 6))


# ===========================================================================
# O — Output-shape and determinism (4 tests)
# ===========================================================================

class OutputShape(unittest.TestCase):

    _REQUIRED_KEYS = {
        "classification",
        "confidence",
        "group_span_ft",
        "candidate_subextents",
        "best_candidate_index",
        "covered_sheets",
        "missing_sheets",
        "has_reset_boundary",
        "ambiguity_flags",
        "reasons",
        "would_boost",
    }

    def test_o1_all_required_keys_present_on_every_classification(self) -> None:
        scenarios = [
            (None, {}),
            ({"span_ft": 0}, {}),
            (_group(300, [3]), {}),  # missing-topology -> uncertain
            (_group(300, [3]), {3: _origin(938)}),  # fit_weak
            (_group(1000, [3]), {3: _origin(100)}),  # overflow
            (
                _group(300, [3]),
                {3: _origin(938, method="single_sheet_isolated")},
            ),  # uncertain
            (
                _group(300, [3]),
                {3: _origin(938)},
            ),  # plain fit_weak again
        ]
        for group, origins in scenarios:
            result = evaluate(group, origins)
            self.assertEqual(
                set(result.keys()), self._REQUIRED_KEYS,
                msg=f"Missing keys for scenario {group!r} / origins {origins!r}",
            )

    def test_o2_ambiguity_flags_sorted_and_unique(self) -> None:
        # Force multiple ambiguity flags: reset_boundary + chain_unverified.
        result = evaluate(
            _group(1500, [3, 4]),
            {3: _origin(1000, has_reset=True), 4: _origin(1000)},
            anchor_hints={"matchline_crossings": [3, 4]},
        )
        flags = result["ambiguity_flags"]
        self.assertEqual(flags, sorted(flags))
        self.assertEqual(len(flags), len(set(flags)))

    def test_o3_candidate_subextents_deterministic_order(self) -> None:
        result = evaluate(
            _group(1500, [3, 7]),
            {3: _origin(2000), 7: _origin(2000)},
            anchor_hints={"matchline_crossings": [3, 7]},
        )
        # Two strong candidates with equal ratio -> sorted by sheet_set[0].
        first_sheets = [c["sheet_set"][0] for c in result["candidate_subextents"]]
        self.assertEqual(first_sheets, sorted(first_sheets))

    def test_o4_two_calls_with_equal_inputs_produce_equal_outputs(self) -> None:
        group = _group(300, [3])
        origins = {3: _origin(938)}
        anchor = {"matchline_crossings": [3]}
        a = evaluate(group, origins, anchor_hints=anchor)
        b = evaluate(group, origins, anchor_hints=anchor)
        self.assertEqual(a, b)
        self.assertEqual(
            json.dumps(a, sort_keys=True),
            json.dumps(b, sort_keys=True),
        )


if __name__ == "__main__":
    unittest.main()
