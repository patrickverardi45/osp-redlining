"""Layer-1 synthetic tests for evaluate_footage_range_containment.

No PDFs, no fixtures, no STATE. Every test constructs synthetic
normalized-group and sheet-origins dicts in-process.

What is being locked down:
  - classification thresholds (contained / partial / out_of_range)
  - confidence demotion rules (missing, reset, non-contiguous)
  - print-to-sheet resolution (mapping vs direct coercion)
  - would_boost evidence-flag rules
  - safe-failure on malformed inputs (None, garbage, missing fields)
  - input immutability: helper does NOT mutate caller dicts/lists
  - anchor-evidence boundary: output never carries a route_id
  - output schema completeness and types

COMMAND
-------
    python -m pytest backend/tests/test_footage_range_containment.py -v

The helper performs no I/O; this suite has no fixture dependencies.
"""

from __future__ import annotations

import copy
import os
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List

_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# Required env defaults — helper itself reads nothing from the environment.
os.environ.setdefault("TRUELINE_JWT_SECRET", "p52-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "p52-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from app.services import engineering_plan_parser as pp  # noqa: E402

evaluate = pp.evaluate_footage_range_containment


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
    chain_anchors: List[int] = None,
) -> Dict[str, Any]:
    return {
        "origin_ft": 0,
        "end_ft": int(length_ft),
        "length_ft": int(length_ft),
        "method": method,
        "confidence": confidence,
        "chain_anchor_sheets": list(chain_anchors or []),
        "has_reset_boundary": bool(has_reset),
        "matchline_count": 2,
        "callout_count": 0,
        "notes": [],
    }


# ---------------------------------------------------------------------------
# Required case 1 — clean contained span
# ---------------------------------------------------------------------------

class CleanContainedSpan(unittest.TestCase):
    def test_single_sheet_matching_length_is_contained_consistent_high(self) -> None:
        out = evaluate(
            _group(span_ft=900, print_tokens=[4]),
            {4: _origin(length_ft=900)},
        )
        self.assertEqual(out["classification"], "contained_consistent")
        self.assertEqual(out["confidence"], "high")
        self.assertEqual(out["group_span_ft"], 900)
        self.assertEqual(out["expected_plan_span_ft"], 900)
        self.assertAlmostEqual(out["consistency_ratio"], 1.0)
        self.assertEqual(out["referenced_sheets"], [4])
        self.assertEqual(out["covered_sheets"], [4])
        self.assertEqual(out["missing_sheets"], [])
        self.assertFalse(out["has_reset_boundary"])
        self.assertTrue(out["would_boost"])

    def test_ratio_at_0_85_lower_bound_is_contained(self) -> None:
        # Span 850 vs expected 1000 -> ratio 0.85 exactly.
        out = evaluate(
            _group(span_ft=850, print_tokens=[3]),
            {3: _origin(length_ft=1000)},
        )
        self.assertEqual(out["classification"], "contained_consistent")
        self.assertAlmostEqual(out["consistency_ratio"], 0.85)

    def test_high_confidence_chain_yields_high_overall(self) -> None:
        out = evaluate(
            _group(span_ft=1500, print_tokens=[5]),
            {5: _origin(length_ft=1500, method="matchline_chain", confidence="high")},
        )
        self.assertEqual(out["confidence"], "high")
        self.assertTrue(out["would_boost"])


# ---------------------------------------------------------------------------
# Required case 2 — span crossing adjacent sheets
# ---------------------------------------------------------------------------

class AdjacentSheets(unittest.TestCase):
    def test_two_adjacent_sheets_lengths_sum_matches_group_span(self) -> None:
        out = evaluate(
            _group(span_ft=1700, print_tokens=[3, 4]),
            {
                3: _origin(length_ft=800),
                4: _origin(length_ft=900),
            },
        )
        self.assertEqual(out["classification"], "contained_consistent")
        self.assertEqual(out["expected_plan_span_ft"], 1700)
        self.assertEqual(out["covered_sheets"], [3, 4])
        self.assertNotIn("non_contiguous_sheet_references", out["ambiguity_flags"])
        self.assertTrue(out["would_boost"])

    def test_three_adjacent_sheets_in_order(self) -> None:
        out = evaluate(
            _group(span_ft=2400, print_tokens=[6, 7, 8]),
            {
                6: _origin(length_ft=800),
                7: _origin(length_ft=900),
                8: _origin(length_ft=700),
            },
        )
        self.assertEqual(out["classification"], "contained_consistent")
        self.assertEqual(out["covered_sheets"], [6, 7, 8])
        self.assertEqual(out["expected_plan_span_ft"], 2400)

    def test_three_adjacent_sheets_print_tokens_out_of_order(self) -> None:
        out = evaluate(
            _group(span_ft=2400, print_tokens=[8, 6, 7]),
            {
                6: _origin(length_ft=800),
                7: _origin(length_ft=900),
                8: _origin(length_ft=700),
            },
        )
        # referenced_sheets is sorted deterministically by the helper.
        self.assertEqual(out["referenced_sheets"], [6, 7, 8])
        self.assertEqual(out["covered_sheets"], [6, 7, 8])


# ---------------------------------------------------------------------------
# Required case 3 — span crossing slash-reset boundary
# ---------------------------------------------------------------------------

class SlashResetBoundary(unittest.TestCase):
    def test_reset_boundary_demotes_high_to_medium(self) -> None:
        out = evaluate(
            _group(span_ft=900, print_tokens=[4]),
            {4: _origin(length_ft=900, confidence="high", has_reset=True)},
        )
        self.assertEqual(out["classification"], "contained_consistent")
        # High confidence is demoted to medium because of reset boundary.
        self.assertEqual(out["confidence"], "medium")
        self.assertTrue(out["has_reset_boundary"])
        self.assertTrue(out["would_boost"] is False)

    def test_reset_boundary_with_medium_demotes_to_low(self) -> None:
        out = evaluate(
            _group(span_ft=900, print_tokens=[4]),
            {4: _origin(length_ft=900, confidence="medium", has_reset=True)},
        )
        self.assertEqual(out["confidence"], "low")
        self.assertFalse(out["would_boost"])

    def test_reset_boundary_with_low_stays_low(self) -> None:
        out = evaluate(
            _group(span_ft=900, print_tokens=[4]),
            {4: _origin(length_ft=900, confidence="low", has_reset=True)},
        )
        # Demotion bottoms out at low.
        self.assertEqual(out["confidence"], "low")
        self.assertFalse(out["would_boost"])

    def test_reset_boundary_on_one_sheet_in_multi_sheet_group(self) -> None:
        out = evaluate(
            _group(span_ft=1700, print_tokens=[3, 4]),
            {
                3: _origin(length_ft=800, has_reset=False),
                4: _origin(length_ft=900, has_reset=True),
            },
        )
        self.assertTrue(out["has_reset_boundary"])
        self.assertEqual(out["confidence"], "medium")  # demoted from high
        self.assertFalse(out["would_boost"])


# ---------------------------------------------------------------------------
# Required case 4 — ambiguous / missing topology
# ---------------------------------------------------------------------------

class AmbiguousMissingTopology(unittest.TestCase):
    def test_referenced_sheet_with_no_topology_marked_missing(self) -> None:
        out = evaluate(
            _group(span_ft=1700, print_tokens=[3, 4, 5]),
            {
                3: _origin(length_ft=800),
                4: _origin(length_ft=900),
                # sheet 5 absent
            },
        )
        self.assertEqual(out["missing_sheets"], [5])
        self.assertEqual(out["covered_sheets"], [3, 4])
        self.assertIn("missing_topology", out["ambiguity_flags"])
        # Missing sheet -> never high.
        self.assertNotEqual(out["confidence"], "high")
        # Evidence is incomplete -> would_boost False.
        self.assertFalse(out["would_boost"])

    def test_all_referenced_sheets_missing_yields_uncertain(self) -> None:
        out = evaluate(
            _group(span_ft=1700, print_tokens=[10, 11]),
            {},  # nothing covered
        )
        self.assertEqual(out["classification"], "uncertain")
        self.assertEqual(out["confidence"], "uncertain")
        self.assertEqual(out["missing_sheets"], [10, 11])
        self.assertEqual(out["covered_sheets"], [])
        self.assertEqual(out["expected_plan_span_ft"], 0)
        self.assertFalse(out["would_boost"])

    def test_sheet_with_uncertain_method_propagates_uncertain_confidence(self) -> None:
        out = evaluate(
            _group(span_ft=900, print_tokens=[4]),
            {4: _origin(length_ft=900, method="uncertain", confidence="uncertain")},
        )
        # Confidence propagates from worst per-sheet confidence.
        self.assertEqual(out["confidence"], "uncertain")
        self.assertFalse(out["would_boost"])

    def test_no_print_tokens_returns_no_data(self) -> None:
        out = evaluate(
            _group(span_ft=900, print_tokens=[]),
            {4: _origin(length_ft=900)},
        )
        self.assertEqual(out["classification"], "no_data")
        self.assertEqual(out["confidence"], "uncertain")
        self.assertFalse(out["would_boost"])


# ---------------------------------------------------------------------------
# Required case 5 — out-of-range span
# ---------------------------------------------------------------------------

class OutOfRangeSpan(unittest.TestCase):
    def test_span_much_smaller_than_plan_yields_out_of_range(self) -> None:
        out = evaluate(
            _group(span_ft=100, print_tokens=[4]),
            {4: _origin(length_ft=1000)},
        )
        self.assertEqual(out["classification"], "out_of_range")
        self.assertAlmostEqual(out["consistency_ratio"], 0.1)
        self.assertFalse(out["would_boost"])

    def test_span_much_larger_than_plan_yields_out_of_range(self) -> None:
        out = evaluate(
            _group(span_ft=5000, print_tokens=[4]),
            {4: _origin(length_ft=500)},
        )
        self.assertEqual(out["classification"], "out_of_range")
        self.assertAlmostEqual(out["consistency_ratio"], 0.1)

    def test_ratio_just_below_partial_threshold_yields_out_of_range(self) -> None:
        # Span 599 vs expected 1000 -> 0.599 < 0.60 partial threshold.
        out = evaluate(
            _group(span_ft=599, print_tokens=[4]),
            {4: _origin(length_ft=1000)},
        )
        self.assertEqual(out["classification"], "out_of_range")

    def test_ratio_at_partial_lower_bound_yields_partial(self) -> None:
        # Span 600 vs expected 1000 -> ratio 0.60 exactly.
        out = evaluate(
            _group(span_ft=600, print_tokens=[4]),
            {4: _origin(length_ft=1000)},
        )
        self.assertEqual(out["classification"], "partial_consistent")
        self.assertAlmostEqual(out["consistency_ratio"], 0.6)

    def test_ratio_just_below_contained_threshold_yields_partial(self) -> None:
        # Span 800 vs expected 1000 -> ratio 0.80 < 0.85.
        out = evaluate(
            _group(span_ft=800, print_tokens=[4]),
            {4: _origin(length_ft=1000)},
        )
        self.assertEqual(out["classification"], "partial_consistent")

    def test_out_of_range_still_reports_full_evidence_shape(self) -> None:
        out = evaluate(
            _group(span_ft=100, print_tokens=[3, 4]),
            {3: _origin(length_ft=800), 4: _origin(length_ft=900)},
        )
        self.assertEqual(out["classification"], "out_of_range")
        # Out-of-range with high topology still produces high confidence:
        # the data is clean, the result is just a clean negative.
        self.assertEqual(out["confidence"], "high")
        self.assertFalse(out["would_boost"])  # negative evidence -> no boost
        # No fabricated route_id.
        self.assertNotIn("route_id", out)
        self.assertNotIn("selected_route_id", out)


# ---------------------------------------------------------------------------
# Required case 6 — overlapping sheet references
# ---------------------------------------------------------------------------

class OverlappingSheetReferences(unittest.TestCase):
    def test_duplicate_print_tokens_dedupe(self) -> None:
        out = evaluate(
            _group(span_ft=900, print_tokens=[4, 4, 4]),
            {4: _origin(length_ft=900)},
        )
        self.assertEqual(out["referenced_sheets"], [4])
        self.assertEqual(out["expected_plan_span_ft"], 900)

    def test_print_to_sheets_with_overlapping_mappings(self) -> None:
        # Two different print tokens map to overlapping sheet sets.
        out = evaluate(
            _group(span_ft=900, print_tokens=["A", "B"]),
            {3: _origin(length_ft=400), 4: _origin(length_ft=500)},
            print_to_sheets={"A": [3, 4], "B": [4]},
        )
        self.assertEqual(out["referenced_sheets"], [3, 4])
        # Sheet 4 is included once, not twice.
        self.assertEqual(out["expected_plan_span_ft"], 900)

    def test_print_to_sheets_with_completely_overlapping_mappings(self) -> None:
        # All tokens point at the same single sheet.
        out = evaluate(
            _group(span_ft=900, print_tokens=["A", "B", "C"]),
            {7: _origin(length_ft=900)},
            print_to_sheets={"A": [7], "B": [7], "C": [7]},
        )
        self.assertEqual(out["referenced_sheets"], [7])
        self.assertEqual(out["expected_plan_span_ft"], 900)


# ---------------------------------------------------------------------------
# Required case 7 — multi-print bore log like Print=2,3,5
# ---------------------------------------------------------------------------

class MultiPrintBoreLog(unittest.TestCase):
    def test_non_contiguous_sheets_set_ambiguity_flag(self) -> None:
        out = evaluate(
            _group(span_ft=1700, print_tokens=[2, 3, 5]),
            {
                2: _origin(length_ft=400),
                3: _origin(length_ft=500),
                5: _origin(length_ft=800),
            },
        )
        self.assertEqual(out["covered_sheets"], [2, 3, 5])
        self.assertIn("non_contiguous_sheet_references", out["ambiguity_flags"])
        # Confidence demoted from high -> medium because of non-contiguity.
        self.assertEqual(out["confidence"], "medium")
        # Non-contiguous evidence does not boost.
        self.assertFalse(out["would_boost"])

    def test_string_print_tokens_with_mapping(self) -> None:
        out = evaluate(
            _group(span_ft=900, print_tokens=["2", "3", "5"]),
            {
                2: _origin(length_ft=200),
                3: _origin(length_ft=300),
                5: _origin(length_ft=400),
            },
            # Mapping uses string keys directly.
            print_to_sheets={"2": [2], "3": [3], "5": [5]},
        )
        self.assertEqual(out["covered_sheets"], [2, 3, 5])
        self.assertEqual(out["expected_plan_span_ft"], 900)

    def test_three_contiguous_does_not_flag_ambiguity(self) -> None:
        out = evaluate(
            _group(span_ft=2400, print_tokens=[3, 4, 5]),
            {
                3: _origin(length_ft=800),
                4: _origin(length_ft=900),
                5: _origin(length_ft=700),
            },
        )
        self.assertNotIn("non_contiguous_sheet_references", out["ambiguity_flags"])
        self.assertEqual(out["confidence"], "high")

    def test_multi_print_with_one_missing_keeps_others(self) -> None:
        out = evaluate(
            _group(span_ft=900, print_tokens=[2, 3, 5]),
            {
                2: _origin(length_ft=300),
                3: _origin(length_ft=400),
                # sheet 5 absent
            },
        )
        self.assertEqual(out["covered_sheets"], [2, 3])
        self.assertEqual(out["missing_sheets"], [5])
        self.assertIn("missing_topology", out["ambiguity_flags"])


# ---------------------------------------------------------------------------
# Required case 8 — evidence-only semantics (no hard route resolution)
# ---------------------------------------------------------------------------

class EvidenceOnlySemantics(unittest.TestCase):
    def test_output_does_not_carry_any_route_field(self) -> None:
        out = evaluate(
            _group(span_ft=900, print_tokens=[4]),
            {4: _origin(length_ft=900)},
        )
        # Helper must not synthesize a route choice.
        for forbidden in (
            "route_id", "selected_route_id", "matched_route",
            "matched_route_id", "route_choice", "selected_route",
        ):
            self.assertNotIn(forbidden, out,
                             f"helper must not emit {forbidden!r}")

    def test_would_boost_is_a_plain_bool_not_a_score(self) -> None:
        out = evaluate(
            _group(span_ft=900, print_tokens=[4]),
            {4: _origin(length_ft=900)},
        )
        self.assertIsInstance(out["would_boost"], bool)

    def test_would_boost_false_when_classification_is_out_of_range(self) -> None:
        out = evaluate(
            _group(span_ft=100, print_tokens=[4]),
            {4: _origin(length_ft=1000)},
        )
        self.assertFalse(out["would_boost"])

    def test_would_boost_false_for_partial_consistent_low_confidence(self) -> None:
        out = evaluate(
            _group(span_ft=700, print_tokens=[4]),
            {4: _origin(length_ft=1000, method="callouts_only", confidence="low")},
        )
        self.assertEqual(out["classification"], "partial_consistent")
        self.assertEqual(out["confidence"], "low")
        self.assertFalse(out["would_boost"])

    def test_would_boost_true_for_partial_consistent_medium_or_higher(self) -> None:
        # Partial consistent + medium per-sheet confidence -> would_boost True.
        out = evaluate(
            _group(span_ft=700, print_tokens=[4]),
            {4: _origin(length_ft=1000, method="matchline_partial",
                        confidence="medium")},
        )
        self.assertEqual(out["classification"], "partial_consistent")
        self.assertEqual(out["confidence"], "medium")
        self.assertTrue(out["would_boost"])

    def test_reasons_are_human_readable_strings(self) -> None:
        out = evaluate(
            _group(span_ft=900, print_tokens=[4]),
            {4: _origin(length_ft=900)},
        )
        self.assertTrue(out["reasons"])
        for r in out["reasons"]:
            self.assertIsInstance(r, str)
            self.assertGreater(len(r), 0)


# ---------------------------------------------------------------------------
# Required case 9 — malformed inputs safe-fail
# ---------------------------------------------------------------------------

class MalformedInputSafeFail(unittest.TestCase):
    def test_none_group_returns_no_data(self) -> None:
        out = evaluate(None, {4: _origin(length_ft=900)})
        self.assertEqual(out["classification"], "no_data")
        self.assertEqual(out["confidence"], "uncertain")

    def test_group_missing_span_ft_returns_no_data(self) -> None:
        out = evaluate({"print_tokens": [4]}, {4: _origin(length_ft=900)})
        self.assertEqual(out["classification"], "no_data")

    def test_zero_or_negative_span_returns_no_data(self) -> None:
        for span in (0, -100, 0.0, -1.5):
            with self.subTest(span=span):
                out = evaluate(_group(span_ft=span, print_tokens=[4]),
                               {4: _origin(length_ft=900)})
                self.assertEqual(out["classification"], "no_data")

    def test_non_numeric_span_returns_no_data(self) -> None:
        for bad in ("abc", None, [], {}, True, False, float("nan"),
                    float("inf"), float("-inf")):
            with self.subTest(span=bad):
                out = evaluate(_group(span_ft=bad, print_tokens=[4]),
                               {4: _origin(length_ft=900)})
                self.assertEqual(out["classification"], "no_data")

    def test_garbage_sheet_origins_treated_as_empty(self) -> None:
        out = evaluate(_group(span_ft=900, print_tokens=[4]), "not a dict")  # type: ignore[arg-type]
        # Sheet origins absent -> no covered sheets -> uncertain.
        self.assertEqual(out["classification"], "uncertain")

    def test_garbage_entries_in_sheet_origins_are_skipped(self) -> None:
        out = evaluate(
            _group(span_ft=900, print_tokens=[3, 4]),
            {
                3: _origin(length_ft=400),
                4: "not a dict",  # type: ignore[dict-item]
                "bad_key": _origin(length_ft=1000),  # non-int key
                -1: _origin(length_ft=200),  # negative key skipped
            },
        )
        self.assertEqual(out["covered_sheets"], [3])
        self.assertIn(4, out["missing_sheets"])

    def test_invalid_length_ft_in_origin_treats_sheet_as_missing(self) -> None:
        out = evaluate(
            _group(span_ft=900, print_tokens=[4]),
            {4: {"length_ft": "garbage", "method": "uncertain",
                 "confidence": "uncertain", "has_reset_boundary": False}},
        )
        self.assertIn(4, out["missing_sheets"])
        self.assertEqual(out["classification"], "uncertain")

    def test_helper_never_raises_on_arbitrary_garbage(self) -> None:
        nasties = [
            (None, None),
            (None, {}),
            ({}, None),
            ({"span_ft": 1}, {1: None}),
            ({"span_ft": 1, "print_tokens": ["a", None, object()]},
             {1: {"length_ft": object()}}),
            (object(), object()),
        ]
        for group_arg, origins_arg in nasties:
            with self.subTest(group=group_arg, origins=origins_arg):
                try:
                    out = evaluate(group_arg, origins_arg)  # type: ignore[arg-type]
                except Exception as exc:
                    self.fail(f"evaluate raised on {group_arg!r}, "
                              f"{origins_arg!r}: {exc!r}")
                # Always returns a dict with classification.
                self.assertIn("classification", out)

    def test_non_list_print_tokens_treated_as_empty(self) -> None:
        out = evaluate(
            {"span_ft": 900, "print_tokens": "not a list"},
            {4: _origin(length_ft=900)},
        )
        self.assertEqual(out["classification"], "no_data")


# ---------------------------------------------------------------------------
# Required case 10 — no mutation of input objects
# ---------------------------------------------------------------------------

class InputImmutability(unittest.TestCase):
    def test_normalized_group_dict_not_mutated(self) -> None:
        group = _group(span_ft=900, print_tokens=[3, 4])
        snapshot = copy.deepcopy(group)
        evaluate(group, {3: _origin(length_ft=400), 4: _origin(length_ft=500)})
        self.assertEqual(group, snapshot)

    def test_print_tokens_list_not_mutated(self) -> None:
        tokens = [3, 4, 5]
        group = {"span_ft": 1700, "print_tokens": tokens}
        snapshot = list(tokens)
        evaluate(group, {3: _origin(length_ft=400), 4: _origin(length_ft=500),
                         5: _origin(length_ft=800)})
        self.assertEqual(tokens, snapshot)

    def test_sheet_origins_dict_not_mutated(self) -> None:
        origins = {3: _origin(length_ft=400), 4: _origin(length_ft=500)}
        snapshot = copy.deepcopy(origins)
        evaluate(_group(span_ft=900, print_tokens=[3, 4]), origins)
        self.assertEqual(origins, snapshot)

    def test_individual_sheet_origin_entry_not_mutated(self) -> None:
        sheet_entry = _origin(length_ft=900)
        snapshot = copy.deepcopy(sheet_entry)
        evaluate(_group(span_ft=900, print_tokens=[4]), {4: sheet_entry})
        self.assertEqual(sheet_entry, snapshot)

    def test_print_to_sheets_mapping_not_mutated(self) -> None:
        mapping = {"A": [3, 4], "B": [5]}
        snapshot = copy.deepcopy(mapping)
        evaluate(
            _group(span_ft=900, print_tokens=["A", "B"]),
            {3: _origin(length_ft=300), 4: _origin(length_ft=300),
             5: _origin(length_ft=300)},
            print_to_sheets=mapping,
        )
        self.assertEqual(mapping, snapshot)

    def test_two_back_to_back_calls_return_independent_dicts(self) -> None:
        # Calling twice in a row must not share output state.
        group = _group(span_ft=900, print_tokens=[4])
        origins = {4: _origin(length_ft=900)}
        a = evaluate(group, origins)
        b = evaluate(group, origins)
        self.assertEqual(a, b)
        a["referenced_sheets"].append(999)
        self.assertNotIn(999, b["referenced_sheets"])


# ---------------------------------------------------------------------------
# Print-to-sheets mapping resolution
# ---------------------------------------------------------------------------

class PrintToSheetsMapping(unittest.TestCase):
    def test_mapping_resolves_string_tokens_to_sheets(self) -> None:
        out = evaluate(
            _group(span_ft=1700, print_tokens=["alpha", "beta"]),
            {3: _origin(length_ft=800), 4: _origin(length_ft=900)},
            print_to_sheets={"alpha": [3], "beta": [4]},
        )
        self.assertEqual(out["referenced_sheets"], [3, 4])
        self.assertEqual(out["classification"], "contained_consistent")

    def test_mapping_with_token_to_multiple_sheets(self) -> None:
        # A single token resolves to multiple sheets (e.g. a print covers
        # several drawing sheets).
        out = evaluate(
            _group(span_ft=1700, print_tokens=["X"]),
            {3: _origin(length_ft=800), 4: _origin(length_ft=900)},
            print_to_sheets={"X": [3, 4]},
        )
        self.assertEqual(out["referenced_sheets"], [3, 4])

    def test_token_not_in_mapping_falls_back_to_direct_coercion(self) -> None:
        out = evaluate(
            _group(span_ft=900, print_tokens=["7"]),
            {7: _origin(length_ft=900)},
            print_to_sheets={"A": [3]},
        )
        self.assertEqual(out["referenced_sheets"], [7])
        self.assertEqual(out["classification"], "contained_consistent")

    def test_no_mapping_uses_direct_token_coercion(self) -> None:
        out = evaluate(
            _group(span_ft=900, print_tokens=["4"]),
            {4: _origin(length_ft=900)},
            print_to_sheets=None,
        )
        self.assertEqual(out["referenced_sheets"], [4])

    def test_mapping_with_non_iterable_value_coerced_singleton(self) -> None:
        # If a caller mistakenly provides a single int instead of a list,
        # the helper still tolerates it.
        out = evaluate(
            _group(span_ft=900, print_tokens=["A"]),
            {7: _origin(length_ft=900)},
            print_to_sheets={"A": 7},  # type: ignore[dict-item]
        )
        self.assertEqual(out["referenced_sheets"], [7])

    def test_int_and_string_token_match_same_mapping_via_string_key(self) -> None:
        # Token is the int 4; mapping key is "4". Direct lookup misses;
        # fallback string-key lookup hits.
        out = evaluate(
            _group(span_ft=900, print_tokens=[4]),
            {3: _origin(length_ft=900)},
            print_to_sheets={"4": [3]},
        )
        self.assertEqual(out["referenced_sheets"], [3])


# ---------------------------------------------------------------------------
# Classification boundary fine-grain
# ---------------------------------------------------------------------------

class ClassificationBoundaries(unittest.TestCase):
    def test_exactly_equal_spans_yield_ratio_1_0(self) -> None:
        out = evaluate(
            _group(span_ft=1234, print_tokens=[4]),
            {4: _origin(length_ft=1234)},
        )
        self.assertAlmostEqual(out["consistency_ratio"], 1.0)
        self.assertEqual(out["classification"], "contained_consistent")

    def test_zero_expected_plan_span_yields_uncertain(self) -> None:
        # Sheet exists in topology with length 0 -> expected sum 0.
        out = evaluate(
            _group(span_ft=900, print_tokens=[4]),
            {4: _origin(length_ft=0, method="uncertain", confidence="uncertain")},
        )
        self.assertEqual(out["expected_plan_span_ft"], 0)
        self.assertEqual(out["classification"], "uncertain")

    def test_classification_uses_min_over_max_symmetric(self) -> None:
        # Span > expected and span < expected should give same ratio.
        out_a = evaluate(_group(span_ft=800, print_tokens=[4]),
                         {4: _origin(length_ft=1000)})
        out_b = evaluate(_group(span_ft=1000, print_tokens=[4]),
                         {4: _origin(length_ft=800)})
        self.assertAlmostEqual(out_a["consistency_ratio"],
                               out_b["consistency_ratio"])

    def test_only_classification_labels_are_emitted(self) -> None:
        valid = {"contained_consistent", "partial_consistent",
                 "out_of_range", "uncertain", "no_data"}
        examples = [
            evaluate(_group(span_ft=900, print_tokens=[4]),
                     {4: _origin(length_ft=900)}),
            evaluate(_group(span_ft=100, print_tokens=[4]),
                     {4: _origin(length_ft=1000)}),
            evaluate(_group(span_ft=700, print_tokens=[4]),
                     {4: _origin(length_ft=1000)}),
            evaluate(_group(span_ft=900, print_tokens=[10]), {}),
            evaluate(_group(span_ft=0, print_tokens=[4]),
                     {4: _origin(length_ft=900)}),
        ]
        for out in examples:
            self.assertIn(out["classification"], valid)


# ---------------------------------------------------------------------------
# Output schema completeness
# ---------------------------------------------------------------------------

class OutputSchema(unittest.TestCase):
    REQUIRED_KEYS = {
        "classification", "confidence",
        "group_span_ft", "expected_plan_span_ft", "consistency_ratio",
        "referenced_sheets", "missing_sheets", "covered_sheets",
        "sheet_confidence_levels", "sheet_methods",
        "has_reset_boundary",
        "ambiguity_flags", "reasons",
        "would_boost",
    }

    def test_clean_call_emits_all_keys(self) -> None:
        out = evaluate(
            _group(span_ft=900, print_tokens=[4]),
            {4: _origin(length_ft=900)},
        )
        self.assertTrue(self.REQUIRED_KEYS.issubset(out.keys()),
                        f"missing keys: {self.REQUIRED_KEYS - out.keys()}")

    def test_no_data_path_still_emits_all_keys(self) -> None:
        out = evaluate(None, None)
        self.assertTrue(self.REQUIRED_KEYS.issubset(out.keys()),
                        f"missing keys: {self.REQUIRED_KEYS - out.keys()}")

    def test_uncertain_path_still_emits_all_keys(self) -> None:
        out = evaluate(_group(span_ft=900, print_tokens=[10]), {})
        self.assertTrue(self.REQUIRED_KEYS.issubset(out.keys()),
                        f"missing keys: {self.REQUIRED_KEYS - out.keys()}")

    def test_field_types_match_schema(self) -> None:
        out = evaluate(
            _group(span_ft=1700, print_tokens=[3, 4]),
            {3: _origin(length_ft=800),
             4: _origin(length_ft=900, has_reset=True)},
        )
        self.assertIsInstance(out["classification"], str)
        self.assertIsInstance(out["confidence"], str)
        self.assertIsInstance(out["group_span_ft"], int)
        self.assertIsInstance(out["expected_plan_span_ft"], int)
        self.assertIsInstance(out["consistency_ratio"], float)
        self.assertIsInstance(out["referenced_sheets"], list)
        self.assertIsInstance(out["missing_sheets"], list)
        self.assertIsInstance(out["covered_sheets"], list)
        self.assertIsInstance(out["sheet_confidence_levels"], dict)
        self.assertIsInstance(out["sheet_methods"], dict)
        self.assertIsInstance(out["has_reset_boundary"], bool)
        self.assertIsInstance(out["ambiguity_flags"], list)
        self.assertIsInstance(out["reasons"], list)
        self.assertIsInstance(out["would_boost"], bool)

    def test_referenced_sheets_sorted_deduplicated(self) -> None:
        out = evaluate(
            _group(span_ft=1700, print_tokens=[5, 3, 4, 3, 5]),
            {3: _origin(length_ft=400), 4: _origin(length_ft=500),
             5: _origin(length_ft=800)},
        )
        self.assertEqual(out["referenced_sheets"], [3, 4, 5])

    def test_ambiguity_flags_deduplicated_and_sorted(self) -> None:
        out = evaluate(
            _group(span_ft=1700, print_tokens=[2, 3, 5, 10]),
            {2: _origin(length_ft=400), 3: _origin(length_ft=500),
             5: _origin(length_ft=800)},
        )
        # missing_topology AND non_contiguous_sheet_references both present.
        self.assertEqual(
            out["ambiguity_flags"],
            sorted(set(out["ambiguity_flags"])),
        )
        self.assertIn("missing_topology", out["ambiguity_flags"])
        self.assertIn("non_contiguous_sheet_references", out["ambiguity_flags"])


# ---------------------------------------------------------------------------
# End-to-end smoke: P5.1 output flows into P5.2 helper
# ---------------------------------------------------------------------------

class IntegrationWithDerive(unittest.TestCase):
    """The intended runtime composition is
       parser_outputs -> derive_sheet_station_origins -> evaluate_footage_range_containment
    This test confirms the two helpers compose without contract drift.
    """

    def test_p51_output_feeds_p52_helper(self) -> None:
        # Build a P5.1 result by calling derive directly with synthetic
        # parser-shaped records.
        matchlines = [
            # Sheet 3 bounded by [500, 1300] -> length 800
            {"page": 3, "station_ft": 500, "references_sheet": 2,
             "second_station_ft": None},
            {"page": 3, "station_ft": 1300, "references_sheet": 4,
             "second_station_ft": None},
            # Sheet 4 bounded by [1300, 2200] -> length 900
            {"page": 4, "station_ft": 1300, "references_sheet": 3,
             "second_station_ft": None},
            {"page": 4, "station_ft": 2200, "references_sheet": 5,
             "second_station_ft": None},
        ]
        sheet_origins = pp.derive_sheet_station_origins(matchlines, [])

        # Group span 1700 = 800 + 900 -> contained_consistent.
        out = evaluate(
            _group(span_ft=1700, print_tokens=[3, 4]),
            sheet_origins,
        )
        self.assertEqual(out["classification"], "contained_consistent")
        self.assertEqual(out["expected_plan_span_ft"], 1700)
        self.assertEqual(out["confidence"], "high")
        self.assertTrue(out["would_boost"])

    def test_p51_uncertain_sheet_propagates_to_p52(self) -> None:
        matchlines = [
            # Only one matchline -> uncertain (single-point extent).
            {"page": 3, "station_ft": 500, "references_sheet": 2,
             "second_station_ft": None},
        ]
        sheet_origins = pp.derive_sheet_station_origins(matchlines, [])
        # Sheet 3's length is 0 -> sheet entry exists but is uncertain.
        # evaluate sees expected_plan_span_ft = 0 -> classification uncertain.
        out = evaluate(_group(span_ft=900, print_tokens=[3]), sheet_origins)
        self.assertEqual(out["classification"], "uncertain")
        self.assertEqual(out["confidence"], "uncertain")


if __name__ == "__main__":
    unittest.main()
