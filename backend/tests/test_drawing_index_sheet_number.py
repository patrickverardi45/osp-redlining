"""PI.3 — drawing-index sheet_number enrichment unit tests.

Covers the pure enricher `_apply_drawing_sheet_number`. All inputs are
inline dicts; no PDF dependencies, no fixture gating. The helper is
expected to be byte-equivalent in behavior to a per-record
`_parse_sheet_from_dwg_filename(file_name)` lookup, with the additional
contracts that:
  - input is never mutated
  - non-list inputs return []
  - non-dict records are passed through unchanged
  - upstream-provided positive-int `sheet_number` is preserved
  - sheet 0 (and other non-positive values) is normalized to None
  - multiplicity is preserved (same sheet across many records is fine)
"""

from __future__ import annotations

import copy
import unittest
from typing import Any, Dict, List

from backend.app.services import engineering_plan_parser as pp


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


class TestInputValidation(unittest.TestCase):
    def test_none_input_returns_empty_list(self) -> None:
        self.assertEqual(pp._apply_drawing_sheet_number(None), [])  # type: ignore[arg-type]

    def test_non_list_input_returns_empty_list(self) -> None:
        for bad in ({"file_name": "X.DWG"}, "X.DWG", 42, object()):
            self.assertEqual(
                pp._apply_drawing_sheet_number(bad),  # type: ignore[arg-type]
                [],
                msg=f"unexpected output for {bad!r}",
            )

    def test_non_dict_records_passed_through_unchanged(self) -> None:
        sentinel = object()
        out = pp._apply_drawing_sheet_number([sentinel, "junk", 7])  # type: ignore[list-item]
        self.assertEqual(len(out), 3)
        self.assertIs(out[0], sentinel)
        self.assertEqual(out[1], "junk")
        self.assertEqual(out[2], 7)


# ---------------------------------------------------------------------------
# Filename parse roundtrip
# ---------------------------------------------------------------------------


class TestFilenameParseRoundtrip(unittest.TestCase):
    def test_brenham_style_filename_parses_to_trailing_digit_group(self) -> None:
        out = pp._apply_drawing_sheet_number([
            {"page": 1, "file_name": "BRENHAM-PH-5_P_3.DWG"},
        ])
        self.assertEqual(out[0]["sheet_number"], 3)

    def test_short_filename_parses_correctly(self) -> None:
        out = pp._apply_drawing_sheet_number([
            {"page": 2, "file_name": "T-001.DWG"},
        ])
        self.assertEqual(out[0]["sheet_number"], 1)

    def test_filename_without_digit_group_returns_none(self) -> None:
        out = pp._apply_drawing_sheet_number([
            {"page": 3, "file_name": "MAIN-PLAN.DWG"},
        ])
        self.assertIsNone(out[0]["sheet_number"])

    def test_missing_file_name_returns_none(self) -> None:
        out = pp._apply_drawing_sheet_number([
            {"page": 4},
            {"page": 5, "file_name": None},
            {"page": 6, "file_name": 12345},
        ])
        for r in out:
            self.assertIsNone(r["sheet_number"])


# ---------------------------------------------------------------------------
# Upstream-provided sheet_number respect
# ---------------------------------------------------------------------------


class TestUpstreamRespect(unittest.TestCase):
    def test_pre_existing_positive_int_preserved(self) -> None:
        out = pp._apply_drawing_sheet_number([
            {"page": 1, "file_name": "BRENHAM-PH-5_P_3.DWG", "sheet_number": 42},
        ])
        self.assertEqual(out[0]["sheet_number"], 42)

    def test_pre_existing_zero_rejected_and_reparsed(self) -> None:
        # sheet 0 is invalid; the helper must normalize and re-derive.
        out = pp._apply_drawing_sheet_number([
            {"page": 1, "file_name": "BRENHAM-PH-5_P_7.DWG", "sheet_number": 0},
        ])
        self.assertEqual(out[0]["sheet_number"], 7)

    def test_pre_existing_negative_rejected_and_reparsed(self) -> None:
        out = pp._apply_drawing_sheet_number([
            {"page": 1, "file_name": "BRENHAM-PH-5_P_5.DWG", "sheet_number": -3},
        ])
        self.assertEqual(out[0]["sheet_number"], 5)

    def test_pre_existing_non_int_rejected_and_reparsed(self) -> None:
        out = pp._apply_drawing_sheet_number([
            {"page": 1, "file_name": "BRENHAM-PH-5_P_9.DWG", "sheet_number": "nine"},
            {"page": 1, "file_name": "BRENHAM-PH-5_P_9.DWG", "sheet_number": True},
        ])
        for r in out:
            self.assertEqual(r["sheet_number"], 9)


# ---------------------------------------------------------------------------
# Per-record independence (no cross-record voting, no page-order inference,
# multiplicity preserved)
# ---------------------------------------------------------------------------


class TestPerRecordIndependence(unittest.TestCase):
    def test_same_page_many_records_each_independently_parsed(self) -> None:
        records = [
            {"page": 1, "file_name": "BRENHAM-PH-5_P_3.DWG"},
            {"page": 1, "file_name": "BRENHAM-PH-5_P_23.DWG"},
            {"page": 1, "file_name": "BRENHAM-PH-5_P_24.DWG"},
            {"page": 1, "file_name": "MAIN-PLAN.DWG"},
        ]
        out = pp._apply_drawing_sheet_number(records)
        self.assertEqual([r["sheet_number"] for r in out], [3, 23, 24, None])

    def test_same_sheet_on_multiple_records_preserved_independently(self) -> None:
        # Multiplicity: identical sheet on multiple records is fine; the
        # helper does NOT collapse or dedup.
        out = pp._apply_drawing_sheet_number([
            {"page": 1, "file_name": "BRENHAM-PH-5_P_7.DWG"},
            {"page": 2, "file_name": "BRENHAM-PH-5_P_7.DWG"},
        ])
        self.assertEqual([r["sheet_number"] for r in out], [7, 7])

    def test_existing_fields_preserved(self) -> None:
        out = pp._apply_drawing_sheet_number([
            {"page": 1, "file_name": "BRENHAM-PH-5_P_3.DWG", "source_sheet": None,
             "extra": "keep"},
        ])
        self.assertEqual(out[0]["page"], 1)
        self.assertEqual(out[0]["file_name"], "BRENHAM-PH-5_P_3.DWG")
        self.assertIsNone(out[0]["source_sheet"])
        self.assertEqual(out[0]["extra"], "keep")
        self.assertEqual(out[0]["sheet_number"], 3)


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------


class TestImmutability(unittest.TestCase):
    def test_input_list_unchanged(self) -> None:
        records: List[Dict[str, Any]] = [
            {"page": 1, "file_name": "BRENHAM-PH-5_P_3.DWG"},
            {"page": 2, "file_name": "MAIN-PLAN.DWG"},
        ]
        snapshot = copy.deepcopy(records)
        pp._apply_drawing_sheet_number(records)
        self.assertEqual(records, snapshot)

    def test_input_dicts_unchanged(self) -> None:
        rec = {"page": 1, "file_name": "BRENHAM-PH-5_P_3.DWG"}
        before_keys = set(rec.keys())
        pp._apply_drawing_sheet_number([rec])
        # The new field must NOT appear on the input dict — only the
        # returned (fresh) record.
        self.assertEqual(set(rec.keys()), before_keys)
        self.assertNotIn("sheet_number", rec)


# ---------------------------------------------------------------------------
# Empty input
# ---------------------------------------------------------------------------


class TestEmpty(unittest.TestCase):
    def test_empty_list_returns_empty_list(self) -> None:
        self.assertEqual(pp._apply_drawing_sheet_number([]), [])


if __name__ == "__main__":
    unittest.main()
