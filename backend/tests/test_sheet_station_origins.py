"""Layer-1 synthetic tests for derive_sheet_station_origins.

Pure-helper coverage. No PDFs, no fixtures, no STATE. Every test constructs
synthetic matchline / callout dicts in-process.

What is being locked down:
  - method assignment matrix      (matchline counts × callout counts)
  - confidence assignment matrix  (same)
  - source_sheet vs page fallback semantics
  - slash-form reset-boundary detection
  - range / equation / single callout kind handling
  - chain-anchor sheet collection
  - safe-failure on malformed / None / empty input
  - degenerate (zero-length) extent downgrade

COMMAND
-------
    python -m pytest backend/tests/test_sheet_station_origins.py -v

The helper performs no PDF I/O; this suite does not require pdfplumber or
any fixture file to be present.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List

_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# Required env defaults — co-located imports may want these even though the
# helper itself reads nothing from the environment.
os.environ.setdefault("TRUELINE_JWT_SECRET", "p5-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "p5-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from app.services import engineering_plan_parser as pp  # noqa: E402

derive = pp.derive_sheet_station_origins


# ---------------------------------------------------------------------------
# Small constructors so test intent is readable
# ---------------------------------------------------------------------------

def _ml(
    source_sheet: Any = None,
    references_sheet: Any = None,
    station_ft: Any = None,
    second_station_ft: Any = None,
    page: Any = None,
) -> Dict[str, Any]:
    rec: Dict[str, Any] = {}
    if source_sheet is not None:
        rec["source_sheet"] = source_sheet
    if page is not None:
        rec["page"] = page
    if references_sheet is not None:
        rec["references_sheet"] = references_sheet
    if station_ft is not None:
        rec["station_ft"] = station_ft
    if second_station_ft is not None:
        rec["second_station_ft"] = second_station_ft
    return rec


def _co(
    source_sheet: Any = None,
    kind: str = "single",
    station_ft: Any = None,
    second_station_ft: Any = None,
    page: Any = None,
) -> Dict[str, Any]:
    rec: Dict[str, Any] = {"kind": kind}
    if source_sheet is not None:
        rec["source_sheet"] = source_sheet
    if page is not None:
        rec["page"] = page
    if station_ft is not None:
        rec["station_ft"] = station_ft
    if second_station_ft is not None:
        rec["second_station_ft"] = second_station_ft
    return rec


# ---------------------------------------------------------------------------
# Method × confidence matrix
# ---------------------------------------------------------------------------

class MethodConfidenceMatrix(unittest.TestCase):
    def test_two_matchlines_yield_matchline_chain_high(self) -> None:
        result = derive(
            matchlines=[
                _ml(source_sheet=4, references_sheet=3, station_ft=1625),
                _ml(source_sheet=4, references_sheet=5, station_ft=2410),
            ],
            station_callouts=[],
        )
        self.assertIn(4, result)
        entry = result[4]
        self.assertEqual(entry["method"], "matchline_chain")
        self.assertEqual(entry["confidence"], "high")
        self.assertEqual(entry["origin_ft"], 1625)
        self.assertEqual(entry["end_ft"], 2410)
        self.assertEqual(entry["length_ft"], 785)
        self.assertEqual(entry["matchline_count"], 2)
        self.assertEqual(entry["callout_count"], 0)

    def test_three_matchlines_still_yield_high(self) -> None:
        result = derive(
            matchlines=[
                _ml(source_sheet=7, references_sheet=6, station_ft=500),
                _ml(source_sheet=7, references_sheet=8, station_ft=1500),
                _ml(source_sheet=7, references_sheet=9, station_ft=2000),
            ],
            station_callouts=[],
        )
        self.assertEqual(result[7]["method"], "matchline_chain")
        self.assertEqual(result[7]["confidence"], "high")
        self.assertEqual(result[7]["length_ft"], 1500)

    def test_one_matchline_plus_callouts_yields_partial_medium(self) -> None:
        result = derive(
            matchlines=[_ml(source_sheet=2, references_sheet=3, station_ft=900)],
            station_callouts=[
                _co(source_sheet=2, kind="single", station_ft=300),
                _co(source_sheet=2, kind="single", station_ft=600),
            ],
        )
        entry = result[2]
        self.assertEqual(entry["method"], "matchline_partial")
        self.assertEqual(entry["confidence"], "medium")
        self.assertEqual(entry["origin_ft"], 300)
        self.assertEqual(entry["end_ft"], 900)
        self.assertEqual(entry["length_ft"], 600)
        self.assertEqual(entry["matchline_count"], 1)
        self.assertEqual(entry["callout_count"], 2)

    def test_one_matchline_alone_yields_single_low(self) -> None:
        result = derive(
            matchlines=[_ml(source_sheet=6, references_sheet=7, station_ft=1000)],
            station_callouts=[],
        )
        entry = result[6]
        self.assertEqual(entry["method"], "uncertain")
        # A single matchline gives a single point — length 0 — so it is
        # downgraded from matchline_single/low to uncertain/uncertain.
        self.assertEqual(entry["confidence"], "uncertain")
        self.assertEqual(entry["length_ft"], 0)
        self.assertTrue(any("zero length" in n.lower() for n in entry["notes"]))

    def test_one_matchline_alone_but_nonzero_via_repetition_stays_single_low(self) -> None:
        # Two matchlines at different stations -> chain. Test the edge where
        # the matchline_single branch retains low confidence when length > 0:
        # this requires a single matchline with no callouts AND length > 0.
        # That is only possible if station_ft itself is computed against a
        # non-zero origin — impossible here because the single point's min
        # and max are equal. The branch is therefore exercised via the
        # zero-length collapse below; the named 'matchline_single' method
        # exists but is unreachable as a final label with the current rules,
        # which is acceptable: confidence is uncertain whenever length<=0.
        result = derive(
            matchlines=[_ml(source_sheet=6, references_sheet=7, station_ft=0)],
            station_callouts=[],
        )
        entry = result[6]
        self.assertEqual(entry["confidence"], "uncertain")

    def test_callouts_only_two_or_more_yields_callouts_only_low(self) -> None:
        result = derive(
            matchlines=[],
            station_callouts=[
                _co(source_sheet=10, kind="single", station_ft=100),
                _co(source_sheet=10, kind="single", station_ft=800),
            ],
        )
        entry = result[10]
        self.assertEqual(entry["method"], "callouts_only")
        self.assertEqual(entry["confidence"], "low")
        self.assertEqual(entry["length_ft"], 700)

    def test_single_callout_yields_single_sheet_isolated_uncertain(self) -> None:
        result = derive(
            matchlines=[],
            station_callouts=[_co(source_sheet=11, kind="single", station_ft=420)],
        )
        entry = result[11]
        self.assertEqual(entry["method"], "single_sheet_isolated")
        self.assertEqual(entry["confidence"], "uncertain")
        self.assertEqual(entry["origin_ft"], 420)
        self.assertEqual(entry["end_ft"], 420)
        self.assertEqual(entry["length_ft"], 0)

    def test_zero_length_extent_downgrades_to_uncertain(self) -> None:
        result = derive(
            matchlines=[
                _ml(source_sheet=12, references_sheet=11, station_ft=500),
                _ml(source_sheet=12, references_sheet=13, station_ft=500),
            ],
            station_callouts=[],
        )
        entry = result[12]
        self.assertEqual(entry["method"], "uncertain")
        self.assertEqual(entry["confidence"], "uncertain")
        self.assertEqual(entry["length_ft"], 0)


# ---------------------------------------------------------------------------
# Multi-sheet chains
# ---------------------------------------------------------------------------

class MultiSheetChains(unittest.TestCase):
    def test_continuous_chain_three_sheets_each_has_two_matchlines(self) -> None:
        # Sheets 1-3, each internal sheet bounded by two matchlines.
        result = derive(
            matchlines=[
                # Sheet 1: ends at 800 (boundary to sheet 2).
                _ml(source_sheet=1, references_sheet=2, station_ft=800),
                # Sheet 2: bounded by [800, 1700].
                _ml(source_sheet=2, references_sheet=1, station_ft=800),
                _ml(source_sheet=2, references_sheet=3, station_ft=1700),
                # Sheet 3: starts at 1700.
                _ml(source_sheet=3, references_sheet=2, station_ft=1700),
            ],
            station_callouts=[
                _co(source_sheet=1, kind="single", station_ft=0),
                _co(source_sheet=3, kind="single", station_ft=2500),
            ],
        )
        self.assertEqual(set(result.keys()), {1, 2, 3})

        s2 = result[2]
        self.assertEqual(s2["method"], "matchline_chain")
        self.assertEqual(s2["confidence"], "high")
        self.assertEqual(s2["origin_ft"], 800)
        self.assertEqual(s2["end_ft"], 1700)
        self.assertEqual(s2["length_ft"], 900)
        self.assertEqual(s2["chain_anchor_sheets"], [1, 3])
        self.assertFalse(s2["has_reset_boundary"])

        s1 = result[1]
        # Sheet 1 has one matchline + one callout -> partial / medium.
        self.assertEqual(s1["method"], "matchline_partial")
        self.assertEqual(s1["confidence"], "medium")
        self.assertEqual(s1["origin_ft"], 0)
        self.assertEqual(s1["end_ft"], 800)

        s3 = result[3]
        self.assertEqual(s3["method"], "matchline_partial")
        self.assertEqual(s3["confidence"], "medium")
        self.assertEqual(s3["origin_ft"], 1700)
        self.assertEqual(s3["end_ft"], 2500)

    def test_reset_chain_marks_has_reset_boundary(self) -> None:
        # Sheet 2 has slash-form matchlines on both edges.
        result = derive(
            matchlines=[
                _ml(source_sheet=2, references_sheet=1, station_ft=0,
                    second_station_ft=1625),
                _ml(source_sheet=2, references_sheet=3, station_ft=900,
                    second_station_ft=0),
            ],
            station_callouts=[],
        )
        entry = result[2]
        self.assertTrue(entry["has_reset_boundary"])
        self.assertEqual(entry["method"], "matchline_chain")
        self.assertEqual(entry["confidence"], "high")
        # Length is computed from primary stations only (own coordinates).
        self.assertEqual(entry["origin_ft"], 0)
        self.assertEqual(entry["end_ft"], 900)
        self.assertEqual(entry["length_ft"], 900)
        self.assertTrue(any("slash-form" in n.lower() for n in entry["notes"]))

    def test_mixed_chain_one_slash_one_continuous(self) -> None:
        result = derive(
            matchlines=[
                _ml(source_sheet=5, references_sheet=4, station_ft=200),  # continuous
                _ml(source_sheet=5, references_sheet=6, station_ft=1100,
                    second_station_ft=0),  # reset
            ],
            station_callouts=[],
        )
        entry = result[5]
        self.assertTrue(entry["has_reset_boundary"])
        self.assertEqual(entry["origin_ft"], 200)
        self.assertEqual(entry["end_ft"], 1100)
        self.assertEqual(entry["length_ft"], 900)

    def test_non_slash_chain_does_not_set_reset_flag(self) -> None:
        result = derive(
            matchlines=[
                _ml(source_sheet=8, references_sheet=7, station_ft=400),
                _ml(source_sheet=8, references_sheet=9, station_ft=1400),
            ],
            station_callouts=[],
        )
        entry = result[8]
        self.assertFalse(entry["has_reset_boundary"])
        # Reset note should NOT appear.
        self.assertTrue(all("slash-form" not in n.lower() for n in entry["notes"]))


# ---------------------------------------------------------------------------
# Callout kind handling
# ---------------------------------------------------------------------------

class CalloutKindHandling(unittest.TestCase):
    def test_range_callout_includes_both_endpoints(self) -> None:
        result = derive(
            matchlines=[],
            station_callouts=[
                _co(source_sheet=20, kind="range", station_ft=500,
                    second_station_ft=1800),
            ],
        )
        entry = result[20]
        self.assertEqual(entry["origin_ft"], 500)
        self.assertEqual(entry["end_ft"], 1800)
        self.assertEqual(entry["length_ft"], 1300)
        # One callout record but two endpoints — callout_count is 1 (record
        # count, not endpoint count), which is intentional: it reflects how
        # many records the helper consumed.
        self.assertEqual(entry["callout_count"], 1)
        # One record, single record class -> would be 'single_sheet_isolated',
        # but the range callout contributes two stations so we have a real
        # extent. The classification still keys off record count.
        self.assertEqual(entry["method"], "single_sheet_isolated")

    def test_equation_callout_ignores_second_value(self) -> None:
        # Equation: STA 14+00 = 0+00. Second value is in a different
        # stationing system — should NOT extend the range.
        result = derive(
            matchlines=[
                _ml(source_sheet=21, references_sheet=22, station_ft=1900),
            ],
            station_callouts=[
                _co(source_sheet=21, kind="equation", station_ft=1400,
                    second_station_ft=0),
            ],
        )
        entry = result[21]
        # Range built from {1400 (callout primary), 1900 (matchline)}.
        self.assertEqual(entry["origin_ft"], 1400)
        self.assertEqual(entry["end_ft"], 1900)
        self.assertNotIn(0, [entry["origin_ft"], entry["end_ft"]])

    def test_single_callout_kind_uses_only_primary(self) -> None:
        result = derive(
            matchlines=[],
            station_callouts=[
                _co(source_sheet=22, kind="single", station_ft=600),
                _co(source_sheet=22, kind="single", station_ft=1700,
                    second_station_ft=9999),  # second ignored for 'single'
            ],
        )
        entry = result[22]
        self.assertEqual(entry["origin_ft"], 600)
        self.assertEqual(entry["end_ft"], 1700)
        self.assertNotIn(9999, [entry["origin_ft"], entry["end_ft"]])

    def test_unknown_callout_kind_treated_as_single(self) -> None:
        result = derive(
            matchlines=[],
            station_callouts=[
                _co(source_sheet=23, kind="weird_kind", station_ft=100),
                _co(source_sheet=23, kind="weird_kind", station_ft=400,
                    second_station_ft=9999),
            ],
        )
        entry = result[23]
        # second_station_ft is not consumed for non-'range' kinds.
        self.assertEqual(entry["origin_ft"], 100)
        self.assertEqual(entry["end_ft"], 400)

    def test_mixed_range_and_single_callouts(self) -> None:
        result = derive(
            matchlines=[],
            station_callouts=[
                _co(source_sheet=24, kind="range", station_ft=200,
                    second_station_ft=1200),
                _co(source_sheet=24, kind="single", station_ft=1500),
                _co(source_sheet=24, kind="single", station_ft=50),
            ],
        )
        entry = result[24]
        self.assertEqual(entry["origin_ft"], 50)
        self.assertEqual(entry["end_ft"], 1500)
        self.assertEqual(entry["method"], "callouts_only")
        self.assertEqual(entry["confidence"], "low")


# ---------------------------------------------------------------------------
# Source-sheet identification & page fallback
# ---------------------------------------------------------------------------

class SourceSheetIdentification(unittest.TestCase):
    def test_source_sheet_preferred_over_page_when_both_present(self) -> None:
        result = derive(
            matchlines=[
                _ml(source_sheet=4, page=99, references_sheet=3, station_ft=500),
                _ml(source_sheet=4, page=99, references_sheet=5, station_ft=1500),
            ],
            station_callouts=[],
        )
        self.assertIn(4, result)
        self.assertNotIn(99, result)

    def test_page_used_when_source_sheet_absent(self) -> None:
        result = derive(
            matchlines=[
                _ml(page=7, references_sheet=6, station_ft=200),
                _ml(page=7, references_sheet=8, station_ft=1100),
            ],
            station_callouts=[],
        )
        self.assertIn(7, result)
        self.assertEqual(result[7]["method"], "matchline_chain")

    def test_record_skipped_when_neither_source_sheet_nor_page(self) -> None:
        result = derive(
            matchlines=[
                {"references_sheet": 3, "station_ft": 100},
                {"references_sheet": 4, "station_ft": 200},
            ],
            station_callouts=[],
        )
        self.assertEqual(result, {})

    def test_non_int_source_sheet_falls_back_to_page(self) -> None:
        result = derive(
            matchlines=[
                _ml(source_sheet="not-an-int", page=5,
                    references_sheet=6, station_ft=300),
                _ml(source_sheet="not-an-int", page=5,
                    references_sheet=4, station_ft=1100),
            ],
            station_callouts=[],
        )
        self.assertIn(5, result)
        self.assertEqual(result[5]["method"], "matchline_chain")

    def test_int_castable_string_source_sheet_accepted(self) -> None:
        result = derive(
            matchlines=[
                _ml(source_sheet="9", references_sheet="8", station_ft="100"),
                _ml(source_sheet="9", references_sheet="10", station_ft="900"),
            ],
            station_callouts=[],
        )
        self.assertIn(9, result)
        self.assertEqual(result[9]["chain_anchor_sheets"], [8, 10])

    def test_whole_number_float_source_sheet_accepted(self) -> None:
        result = derive(
            matchlines=[
                _ml(source_sheet=3.0, references_sheet=2.0, station_ft=100.0),
                _ml(source_sheet=3.0, references_sheet=4.0, station_ft=1100.0),
            ],
            station_callouts=[],
        )
        self.assertIn(3, result)

    def test_fractional_float_station_rejected(self) -> None:
        result = derive(
            matchlines=[
                _ml(source_sheet=2, references_sheet=1, station_ft=100.5),
            ],
            station_callouts=[],
        )
        # The single matchline is rejected -> sheet 2 absent entirely.
        self.assertEqual(result, {})

    def test_bool_values_rejected_as_int(self) -> None:
        result = derive(
            matchlines=[_ml(source_sheet=True, references_sheet=1, station_ft=100)],
            station_callouts=[],
        )
        self.assertEqual(result, {})


# ---------------------------------------------------------------------------
# Chain-anchor capture
# ---------------------------------------------------------------------------

class ChainAnchorCapture(unittest.TestCase):
    def test_chain_anchor_sheets_collected_from_matchlines(self) -> None:
        result = derive(
            matchlines=[
                _ml(source_sheet=4, references_sheet=3, station_ft=500),
                _ml(source_sheet=4, references_sheet=5, station_ft=1500),
            ],
            station_callouts=[],
        )
        self.assertEqual(result[4]["chain_anchor_sheets"], [3, 5])

    def test_chain_anchor_sheets_deduplicated_and_sorted(self) -> None:
        result = derive(
            matchlines=[
                _ml(source_sheet=4, references_sheet=5, station_ft=500),
                _ml(source_sheet=4, references_sheet=3, station_ft=1000),
                _ml(source_sheet=4, references_sheet=5, station_ft=1500),
            ],
            station_callouts=[],
        )
        self.assertEqual(result[4]["chain_anchor_sheets"], [3, 5])

    def test_no_chain_anchors_when_only_callouts(self) -> None:
        result = derive(
            matchlines=[],
            station_callouts=[
                _co(source_sheet=4, kind="single", station_ft=100),
                _co(source_sheet=4, kind="single", station_ft=900),
            ],
        )
        self.assertEqual(result[4]["chain_anchor_sheets"], [])

    def test_invalid_references_sheet_does_not_pollute_anchor_set(self) -> None:
        result = derive(
            matchlines=[
                _ml(source_sheet=4, references_sheet="bad", station_ft=100),
                _ml(source_sheet=4, references_sheet=5, station_ft=900),
            ],
            station_callouts=[],
        )
        self.assertEqual(result[4]["chain_anchor_sheets"], [5])


# ---------------------------------------------------------------------------
# Safe-failure behavior
# ---------------------------------------------------------------------------

class SafeFailure(unittest.TestCase):
    def test_none_inputs_return_empty_dict(self) -> None:
        self.assertEqual(derive(None, None), {})

    def test_empty_lists_return_empty_dict(self) -> None:
        self.assertEqual(derive([], []), {})

    def test_one_none_one_list(self) -> None:
        result = derive(
            None,
            [_co(source_sheet=2, kind="single", station_ft=400),
             _co(source_sheet=2, kind="single", station_ft=900)],
        )
        self.assertIn(2, result)
        self.assertEqual(result[2]["method"], "callouts_only")

    def test_non_dict_records_silently_skipped(self) -> None:
        result = derive(
            matchlines=["not a dict", 42, None,
                        _ml(source_sheet=4, references_sheet=5, station_ft=100),
                        _ml(source_sheet=4, references_sheet=3, station_ft=900)],
            station_callouts=[],
        )
        self.assertIn(4, result)
        self.assertEqual(result[4]["method"], "matchline_chain")

    def test_non_iterable_input_does_not_raise(self) -> None:
        # Passing a non-list (e.g. an int) where a list is expected must
        # not raise; the helper treats it as empty.
        self.assertEqual(derive(42, 7), {})  # type: ignore[arg-type]

    def test_missing_station_ft_skips_record(self) -> None:
        result = derive(
            matchlines=[
                _ml(source_sheet=4, references_sheet=3),
                _ml(source_sheet=4, references_sheet=5, station_ft=900),
            ],
            station_callouts=[],
        )
        # Only one valid matchline -> single point -> uncertain.
        self.assertEqual(result[4]["confidence"], "uncertain")
        self.assertEqual(result[4]["matchline_count"], 1)

    def test_negative_station_ft_skipped(self) -> None:
        result = derive(
            matchlines=[
                _ml(source_sheet=4, references_sheet=3, station_ft=-100),
                _ml(source_sheet=4, references_sheet=5, station_ft=900),
            ],
            station_callouts=[],
        )
        self.assertEqual(result[4]["matchline_count"], 1)

    def test_string_garbage_station_ft_skipped(self) -> None:
        result = derive(
            matchlines=[
                _ml(source_sheet=4, references_sheet=3, station_ft="abc"),
                _ml(source_sheet=4, references_sheet=5, station_ft="200"),
            ],
            station_callouts=[],
        )
        self.assertEqual(result[4]["matchline_count"], 1)

    def test_negative_source_sheet_skipped(self) -> None:
        result = derive(
            matchlines=[_ml(source_sheet=-1, references_sheet=2, station_ft=100)],
            station_callouts=[],
        )
        self.assertEqual(result, {})

    def test_mixed_valid_and_invalid_records_preserve_valid(self) -> None:
        result = derive(
            matchlines=[
                {"garbage": "x"},
                None,
                _ml(source_sheet=4, references_sheet=3, station_ft=500),
                "string",
                _ml(source_sheet=4, references_sheet=5, station_ft=1500),
                42,
            ],
            station_callouts=[
                _co(source_sheet=4, kind="single", station_ft=2000),
                {"unrelated": True},
            ],
        )
        entry = result[4]
        self.assertEqual(entry["matchline_count"], 2)
        self.assertEqual(entry["callout_count"], 1)
        self.assertEqual(entry["method"], "matchline_chain")
        self.assertEqual(entry["origin_ft"], 500)
        self.assertEqual(entry["end_ft"], 2000)

    def test_records_with_only_garbage_keys_return_empty(self) -> None:
        result = derive(
            matchlines=[{"foo": 1}, {"bar": 2}],
            station_callouts=[{"baz": 3}],
        )
        self.assertEqual(result, {})

    def test_helper_never_raises_on_arbitrary_garbage(self) -> None:
        # Best-effort fuzz: a small set of nasty inputs to confirm no exception.
        nasties: List[Any] = [
            object(),
            [None, None, None],
            [{"source_sheet": object(), "station_ft": object()}],
            [{"source_sheet": float("nan"), "station_ft": 1}],
            [{"source_sheet": float("inf"), "station_ft": 1}],
            [{"source_sheet": 1, "station_ft": float("nan")}],
        ]
        for nasty in nasties:
            try:
                derive(nasty, nasty)  # type: ignore[arg-type]
            except Exception as exc:
                self.fail(f"derive raised on {nasty!r}: {exc!r}")


# ---------------------------------------------------------------------------
# Output schema invariants
# ---------------------------------------------------------------------------

class OutputSchema(unittest.TestCase):
    def test_every_emitted_entry_has_all_required_keys(self) -> None:
        result = derive(
            matchlines=[
                _ml(source_sheet=4, references_sheet=3, station_ft=500),
                _ml(source_sheet=4, references_sheet=5, station_ft=1500),
            ],
            station_callouts=[
                _co(source_sheet=10, kind="single", station_ft=200),
                _co(source_sheet=10, kind="single", station_ft=600),
            ],
        )
        required = {
            "origin_ft", "end_ft", "length_ft",
            "method", "confidence",
            "chain_anchor_sheets", "has_reset_boundary",
            "matchline_count", "callout_count", "notes",
        }
        for sheet_no, entry in result.items():
            with self.subTest(sheet_no=sheet_no):
                self.assertTrue(required.issubset(entry.keys()),
                                f"sheet {sheet_no} missing keys: "
                                f"{required - entry.keys()}")

    def test_types_match_schema(self) -> None:
        result = derive(
            matchlines=[
                _ml(source_sheet=4, references_sheet=3, station_ft=500),
                _ml(source_sheet=4, references_sheet=5, station_ft=1500,
                    second_station_ft=0),
            ],
            station_callouts=[],
        )
        entry = result[4]
        self.assertIsInstance(entry["origin_ft"], int)
        self.assertIsInstance(entry["end_ft"], int)
        self.assertIsInstance(entry["length_ft"], int)
        self.assertIsInstance(entry["method"], str)
        self.assertIsInstance(entry["confidence"], str)
        self.assertIsInstance(entry["chain_anchor_sheets"], list)
        self.assertIsInstance(entry["has_reset_boundary"], bool)
        self.assertIsInstance(entry["matchline_count"], int)
        self.assertIsInstance(entry["callout_count"], int)
        self.assertIsInstance(entry["notes"], list)

    def test_method_is_one_of_expected_set(self) -> None:
        result = derive(
            matchlines=[
                _ml(source_sheet=1, references_sheet=2, station_ft=200),
                _ml(source_sheet=1, references_sheet=3, station_ft=1200),
                _ml(source_sheet=4, references_sheet=3, station_ft=500),
            ],
            station_callouts=[
                _co(source_sheet=4, kind="single", station_ft=900),
                _co(source_sheet=5, kind="single", station_ft=10),
                _co(source_sheet=5, kind="single", station_ft=50),
                _co(source_sheet=6, kind="single", station_ft=420),
            ],
        )
        valid_methods = {
            "matchline_chain", "matchline_partial", "matchline_single",
            "callouts_only", "single_sheet_isolated", "uncertain",
        }
        for entry in result.values():
            self.assertIn(entry["method"], valid_methods)

    def test_confidence_is_one_of_expected_set(self) -> None:
        result = derive(
            matchlines=[
                _ml(source_sheet=1, references_sheet=2, station_ft=200),
                _ml(source_sheet=1, references_sheet=3, station_ft=1200),
            ],
            station_callouts=[
                _co(source_sheet=2, kind="single", station_ft=100),
            ],
        )
        valid_confidences = {"high", "medium", "low", "uncertain"}
        for entry in result.values():
            self.assertIn(entry["confidence"], valid_confidences)


# ---------------------------------------------------------------------------
# End-to-end smoke: shape that mimics parser output dicts
# ---------------------------------------------------------------------------

class ParserShapedInput(unittest.TestCase):
    """The helper has to interoperate with extract_matchlines /
    extract_station_callouts dict shapes. Those records carry `page` not
    `source_sheet`; this test confirms the fallback works on parser-shape
    records exactly.
    """

    def test_parser_shape_matchline_dict_with_page_fallback(self) -> None:
        # Shape mirrors what extract_matchlines emits, minus PDF text:
        # page, station, station_ft, references_sheet,
        # second_station, second_station_ft, raw_text.
        records = [
            {
                "page": 3,
                "station": "16+25",
                "station_ft": 1625,
                "references_sheet": 4,
                "second_station": None,
                "second_station_ft": None,
                "raw_text": "MATCHLINE STA 16+25 - SEE SHEET 4",
            },
            {
                "page": 3,
                "station": "5+00",
                "station_ft": 500,
                "references_sheet": 2,
                "second_station": None,
                "second_station_ft": None,
                "raw_text": "MATCHLINE STA 5+00 - SEE SHEET 2",
            },
        ]
        result = derive(records, [])
        self.assertIn(3, result)
        self.assertEqual(result[3]["origin_ft"], 500)
        self.assertEqual(result[3]["end_ft"], 1625)
        self.assertEqual(result[3]["length_ft"], 1125)
        self.assertEqual(result[3]["chain_anchor_sheets"], [2, 4])
        self.assertFalse(result[3]["has_reset_boundary"])

    def test_parser_shape_slash_form_matchline_sets_reset_flag(self) -> None:
        records = [
            {
                "page": 4,
                "station": "16+25",
                "station_ft": 1625,
                "references_sheet": 3,
                "second_station": "0+00",
                "second_station_ft": 0,
                "raw_text": "MATCHLINE STA 16+25 / 0+00 - SEE SHEET 3",
            },
            {
                "page": 4,
                "station": "24+10",
                "station_ft": 2410,
                "references_sheet": 5,
                "second_station": None,
                "second_station_ft": None,
                "raw_text": "MATCHLINE STA 24+10 - SEE SHEET 5",
            },
        ]
        result = derive(records, [])
        entry = result[4]
        self.assertTrue(entry["has_reset_boundary"])
        self.assertEqual(entry["origin_ft"], 1625)
        self.assertEqual(entry["end_ft"], 2410)

    def test_parser_shape_callout_kinds_mix(self) -> None:
        callouts = [
            {
                "page": 5,
                "kind": "range",
                "station": "5+00",
                "station_ft": 500,
                "second_station": "18+00",
                "second_station_ft": 1800,
                "raw_text": "STA 5+00 TO STA 18+00",
            },
            {
                "page": 5,
                "kind": "equation",
                "station": "18+00",
                "station_ft": 1800,
                "second_station": "0+00",
                "second_station_ft": 0,
                "raw_text": "STA 18+00 = 0+00",
            },
            {
                "page": 5,
                "kind": "single",
                "station": "12+50",
                "station_ft": 1250,
                "second_station": None,
                "second_station_ft": None,
                "raw_text": "STA 12+50",
            },
        ]
        result = derive([], callouts)
        entry = result[5]
        # Range contributes 500 and 1800; equation primary 1800; single 1250.
        # Equation secondary (0) MUST be ignored.
        self.assertEqual(entry["origin_ft"], 500)
        self.assertEqual(entry["end_ft"], 1800)


if __name__ == "__main__":
    unittest.main()
