"""Layer-1 synthetic tests for derive_page_to_sheet_index and the
supporting PI.1 ingestion plumbing (extract_sheet_labels,
_parse_sheet_from_dwg_filename, _apply_source_sheet).

No PDFs, no fixtures, no STATE. Every test constructs synthetic
metadata / title_block / drawing_index / matchline / sheet_label dicts
in-process. PDF-touching paths are covered separately in
test_engineering_plan_parser.py.

What is being locked down:
  - input validation refusal paths (helpers never raise on bad input)
  - DWG filename → sheet number parsing matrix
  - title_block anchor evidence (page 1 mapping)
  - sheet_labels direct evidence
  - drawing_index file_name evidence
  - conflict resolution (multi-candidate page -> None)
  - input immutability for all helpers
  - source_sheet enrichment respects upstream-provided values
  - output schema and deterministic ordering

COMMAND
-------
    python -m pytest backend/tests/test_page_to_sheet_mapping.py -v

The helpers perform no I/O; this suite has no fixture dependencies.
"""

from __future__ import annotations

import copy
import os
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional

_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

os.environ.setdefault("TRUELINE_JWT_SECRET", "pi1-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "pi1-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from app.services import engineering_plan_parser as pp  # noqa: E402

derive = pp.derive_page_to_sheet_index
parse_dwg = pp._parse_sheet_from_dwg_filename
apply_source = pp._apply_source_sheet


# ---------------------------------------------------------------------------
# Small constructors so test intent is readable
# ---------------------------------------------------------------------------

def _tb(sheet_first_seen: Optional[int] = None) -> Dict[str, Any]:
    return {
        "project": None,
        "address": None,
        "revision_date": None,
        "original_date": None,
        "sheet_number_first_seen": sheet_first_seen,
    }


def _di(page: int, file_name: str) -> Dict[str, Any]:
    return {"page": int(page), "file_name": file_name}


def _sl(page: int, sheet: int) -> Dict[str, Any]:
    return {
        "page": int(page),
        "sheet_label": int(sheet),
        "raw_text": f"SHEET {sheet}",
    }


# ===========================================================================
# V — Input-validation refusal paths (4 tests)
# ===========================================================================

class InputValidation(unittest.TestCase):

    def test_v1_returns_empty_dict_when_all_inputs_none(self) -> None:
        self.assertEqual(derive(None, None, None, None), {})

    def test_v2_returns_empty_dict_when_all_inputs_wrong_types(self) -> None:
        self.assertEqual(derive("x", 42, "y", 3.14, sheet_labels="z"), {})

    def test_v3_tolerates_malformed_records_without_raising(self) -> None:
        # Records that are not dicts, missing keys, bad types — none raises.
        out = derive(
            None,
            _tb(1),
            [None, "junk", {"page": "x"}, {"file_name": None}],
            ["not-a-dict", {"page": -1}, {}],
            sheet_labels=[None, {"page": None, "sheet_label": "bad"}],
        )
        # Only the title_block anchor survives — page 1 -> sheet 1.
        self.assertEqual(out, {1: 1})

    def test_v4_returns_empty_dict_when_evidence_empty(self) -> None:
        self.assertEqual(derive({}, {}, [], [], sheet_labels=[]), {})


# ===========================================================================
# D — DWG filename parsing matrix (6 tests)
# ===========================================================================

class DwgFilenameParsing(unittest.TestCase):

    def test_d1_simple_trailing_digit(self) -> None:
        self.assertEqual(parse_dwg("BRENHAM-PH-5_P_3.DWG"), 3)

    def test_d2_zero_padded_digits(self) -> None:
        self.assertEqual(parse_dwg("T-001.DWG"), 1)

    def test_d3_no_digit_returns_none(self) -> None:
        self.assertIsNone(parse_dwg("MAIN-PLAN.DWG"))

    def test_d4_case_insensitive_extension(self) -> None:
        self.assertEqual(parse_dwg("Sheet5.dwg"), 5)
        self.assertEqual(parse_dwg("Sheet5.DWG"), 5)

    def test_d5_multiple_digit_groups_returns_last(self) -> None:
        self.assertEqual(parse_dwg("BRENHAM-PH-5_P_23.DWG"), 23)

    def test_d6_none_or_empty_or_nonstring_returns_none(self) -> None:
        self.assertIsNone(parse_dwg(None))
        self.assertIsNone(parse_dwg(""))
        self.assertIsNone(parse_dwg(42))  # type: ignore[arg-type]


# ===========================================================================
# A — Title-block anchor evidence (3 tests)
# ===========================================================================

class TitleBlockAnchor(unittest.TestCase):

    def test_a1_anchor_maps_page_1_to_sheet(self) -> None:
        out = derive(None, _tb(7), None, None)
        self.assertEqual(out, {1: 7})

    def test_a2_anchor_is_overridden_when_sheet_label_disagrees(self) -> None:
        out = derive(
            None, _tb(7), None, None,
            sheet_labels=[_sl(1, 99)],
        )
        # Page 1 now has two candidates {7, 99} -> None (conflict).
        self.assertIsNone(out[1])

    def test_a3_missing_anchor_does_not_add_page_1(self) -> None:
        out = derive(None, _tb(None), None, None,
                     sheet_labels=[_sl(2, 2)])
        self.assertNotIn(1, out)
        self.assertEqual(out[2], 2)


# ===========================================================================
# L — Sheet-label direct evidence (4 tests)
# ===========================================================================

class SheetLabelEvidence(unittest.TestCase):

    def test_l1_single_label_maps_page_to_sheet(self) -> None:
        out = derive(None, None, None, None,
                     sheet_labels=[_sl(5, 5)])
        self.assertEqual(out, {5: 5})

    def test_l2_two_labels_same_page_same_sheet_resolve(self) -> None:
        # Multiple matches on same page that agree -> single candidate -> resolved.
        out = derive(None, None, None, None,
                     sheet_labels=[_sl(5, 5), _sl(5, 5)])
        self.assertEqual(out[5], 5)

    def test_l3_two_labels_same_page_disagree_emit_none(self) -> None:
        out = derive(None, None, None, None,
                     sheet_labels=[_sl(5, 5), _sl(5, 6)])
        self.assertIsNone(out[5])

    def test_l4_negative_or_zero_sheet_ignored(self) -> None:
        out = derive(None, None, None, None,
                     sheet_labels=[{"page": 5, "sheet_label": 0},
                                   {"page": 5, "sheet_label": -3},
                                   _sl(5, 5)])
        # Only the valid sheet=5 contributes.
        self.assertEqual(out[5], 5)


# ===========================================================================
# G — Drawing-index file_name evidence (4 tests)
# ===========================================================================

class DrawingIndexEvidence(unittest.TestCase):

    def test_g1_each_page_with_own_dwg_maps_correctly(self) -> None:
        out = derive(
            None, None,
            [_di(4, "BRENHAM-PH-5_P_3.DWG"),
             _di(5, "BRENHAM-PH-5_P_4.DWG"),
             _di(6, "BRENHAM-PH-5_P_5.DWG")],
            None,
        )
        self.assertEqual(out, {4: 3, 5: 4, 6: 5})

    def test_g2_index_page_listing_many_dwgs_emits_none(self) -> None:
        # Same page lists multiple DWGs -> conflict on that page -> None.
        out = derive(
            None, None,
            [_di(2, "T-001.DWG"),
             _di(2, "T-002.DWG"),
             _di(2, "T-003.DWG")],
            None,
        )
        self.assertIsNone(out[2])

    def test_g3_unparseable_filenames_contribute_nothing(self) -> None:
        out = derive(
            None, None,
            [_di(4, "MAIN-PLAN.DWG"),
             _di(5, "OVERVIEW.DWG")],
            None,
        )
        self.assertEqual(out, {})

    def test_g4_mixed_parseable_and_unparseable(self) -> None:
        out = derive(
            None, None,
            [_di(4, "MAIN-PLAN.DWG"),
             _di(5, "T-007.DWG")],
            None,
        )
        self.assertEqual(out, {5: 7})


# ===========================================================================
# C — Conflict resolution across signal classes (3 tests)
# ===========================================================================

class ConflictResolution(unittest.TestCase):

    def test_c1_agreement_across_signals_resolves(self) -> None:
        out = derive(
            None, _tb(1),
            [_di(1, "T-001.DWG")],
            None,
            sheet_labels=[_sl(1, 1)],
        )
        # All three signals agree -> page 1 -> sheet 1.
        self.assertEqual(out[1], 1)

    def test_c2_disagreement_emits_none(self) -> None:
        out = derive(
            None, None,
            [_di(7, "T-007.DWG")],
            None,
            sheet_labels=[_sl(7, 8)],
        )
        # drawing_index says 7, sheet_label says 8 -> conflict -> None.
        self.assertIsNone(out[7])

    def test_c3_unresolved_pages_are_absent(self) -> None:
        out = derive(
            None, None,
            [_di(4, "T-004.DWG")],
            None,
        )
        # Only page 4 has evidence; other pages do not appear.
        self.assertIn(4, out)
        self.assertNotIn(5, out)
        self.assertNotIn(1, out)


# ===========================================================================
# I — Input immutability (3 tests)
# ===========================================================================

class InputImmutability(unittest.TestCase):

    def test_i1_derive_does_not_mutate_inputs(self) -> None:
        md = {"page_count": 5}
        tb = _tb(1)
        di = [_di(2, "T-2.DWG")]
        ml: List[Dict[str, Any]] = []
        sl = [_sl(2, 2)]
        snap = (copy.deepcopy(md), copy.deepcopy(tb), copy.deepcopy(di),
                copy.deepcopy(ml), copy.deepcopy(sl))
        derive(md, tb, di, ml, sheet_labels=sl)
        self.assertEqual((md, tb, di, ml, sl), snap)

    def test_i2_apply_source_sheet_does_not_mutate_records(self) -> None:
        records = [{"page": 3, "station": "5+00"}]
        snap = copy.deepcopy(records)
        out = apply_source(records, {3: 3})
        self.assertEqual(records, snap)
        self.assertEqual(out[0]["source_sheet"], 3)
        self.assertEqual(out[0]["station"], "5+00")
        # New list, not the same object.
        self.assertIsNot(out, records)
        self.assertIsNot(out[0], records[0])

    def test_i3_apply_source_sheet_preserves_upstream_source_sheet(self) -> None:
        records = [{"page": 3, "source_sheet": 99}]
        out = apply_source(records, {3: 3})
        # Upstream-provided source_sheet is NOT overwritten.
        self.assertEqual(out[0]["source_sheet"], 99)


# ===========================================================================
# S — _apply_source_sheet safety contract (4 tests)
# ===========================================================================

class ApplySourceSheetSafety(unittest.TestCase):

    def test_s1_records_with_no_page_get_none(self) -> None:
        out = apply_source([{"station": "x"}], {3: 3})
        self.assertIsNone(out[0]["source_sheet"])

    def test_s2_records_with_unmapped_page_get_none(self) -> None:
        out = apply_source([{"page": 99}], {3: 3})
        self.assertIsNone(out[0]["source_sheet"])

    def test_s3_records_with_explicit_none_map_value_get_none(self) -> None:
        out = apply_source([{"page": 3}], {3: None})
        self.assertIsNone(out[0]["source_sheet"])

    def test_s4_handles_non_list_input_gracefully(self) -> None:
        self.assertEqual(apply_source(None, {3: 3}), [])  # type: ignore[arg-type]
        self.assertEqual(apply_source("not-a-list", {3: 3}), [])  # type: ignore[arg-type]


# ===========================================================================
# O — Output schema and determinism (3 tests)
# ===========================================================================

class OutputSchema(unittest.TestCase):

    def test_o1_keys_are_python_ints(self) -> None:
        out = derive(None, _tb(1), None, None)
        for key in out.keys():
            self.assertIsInstance(key, int)

    def test_o2_values_are_int_or_none(self) -> None:
        out = derive(
            None, _tb(1),
            [_di(7, "T-007.DWG")],
            None,
            sheet_labels=[_sl(7, 8)],  # conflict -> None
        )
        for val in out.values():
            self.assertTrue(val is None or isinstance(val, int))

    def test_o3_two_equivalent_calls_produce_equal_output(self) -> None:
        args = (None, _tb(1), [_di(2, "T-2.DWG")], None)
        sl = [_sl(3, 3)]
        a = derive(*args, sheet_labels=sl)
        b = derive(*args, sheet_labels=sl)
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
