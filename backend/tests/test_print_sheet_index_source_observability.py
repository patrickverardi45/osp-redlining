"""KMZ Hardening Priority #1 — Stage A observability tests.

Verifies that the `print_sheet_index_source` field is correctly emitted by
`_print_sheet_hints` and `_route_filter_for_print_tokens` across the four
documented states. Stage A activates only `hardcoded_brenham` and
`no_print_index_available`; `pi4a_derived` and `manual_override` are reserved
namespace for later stages and are NOT exercised here.

This file also locks down the regression-safety contract for Stage A:
- existing fields are still present
- allowed_route_ids / sheet_numbers / street_hints values unchanged
- filter `applied`, `mode`, `reason` unchanged
"""

from __future__ import annotations

import copy
import os
import unittest

os.environ.setdefault("TRUELINE_JWT_SECRET", "stage-a-observability-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "stage-a-observability-auth-test-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend import main as M


class TestPrintSheetHintsSourceField(unittest.TestCase):
    """`_print_sheet_hints` must emit `print_sheet_index_source`."""

    def test_resolved_token_emits_hardcoded_brenham(self):
        meta = M._print_sheet_hints(["1"])
        self.assertEqual(meta["print_sheet_index_source"], "hardcoded_brenham")
        # Sanity: the Brenham constant resolves token "1" → route_476.
        self.assertIn("route_476", meta["allowed_route_ids"])

    def test_multiple_resolved_tokens_emit_hardcoded_brenham(self):
        meta = M._print_sheet_hints(["1", "9", "25"])
        self.assertEqual(meta["print_sheet_index_source"], "hardcoded_brenham")

    def test_unresolved_token_emits_no_print_index_available(self):
        meta = M._print_sheet_hints(["999"])
        self.assertEqual(meta["print_sheet_index_source"], "no_print_index_available")
        self.assertEqual(meta["allowed_route_ids"], [])
        self.assertEqual(meta["sheet_numbers"], [])
        self.assertEqual(meta["street_hints"], [])

    def test_empty_token_list_emits_no_print_index_available(self):
        meta = M._print_sheet_hints([])
        self.assertEqual(meta["print_sheet_index_source"], "no_print_index_available")

    def test_mixed_resolved_and_unresolved_tokens_emit_hardcoded_brenham(self):
        # Any single token resolving against the constant promotes the source.
        meta = M._print_sheet_hints(["1", "999"])
        self.assertEqual(meta["print_sheet_index_source"], "hardcoded_brenham")
        self.assertIn("route_476", meta["allowed_route_ids"])

    def test_existing_field_shape_preserved(self):
        # Regression lock: pre-existing fields are still present and untouched.
        meta = M._print_sheet_hints(["1"])
        for key in ("print_tokens", "sheet_numbers", "street_hints", "allowed_route_ids"):
            self.assertIn(key, meta)


class TestRouteFilterSourceField(unittest.TestCase):
    """`_route_filter_for_print_tokens` must propagate the source field."""

    def _brenham_route(self, route_id: str, length_ft: float = 500.0):
        return {
            "route_id": route_id,
            "route_name": route_id,
            "route_role": "underground_cable",
            "source_folder": "Brenham",
            "length_ft": length_ft,
            "coords": [[-96.4, 30.2], [-96.4, 30.3]],
        }

    def test_empty_print_tokens_emit_no_print_index_available(self):
        catalog = [self._brenham_route("route_476")]
        filtered, filter_meta = M._route_filter_for_print_tokens([], catalog)
        self.assertEqual(filter_meta["print_sheet_index_source"], "no_print_index_available")
        self.assertFalse(filter_meta["applied"])
        self.assertEqual(filter_meta["mode"], "none")
        # Caller sees full catalog when no tokens are present.
        self.assertEqual(len(filtered), 1)

    def test_unresolved_print_tokens_emit_no_print_index_available(self):
        catalog = [self._brenham_route("route_476")]
        filtered, filter_meta = M._route_filter_for_print_tokens(["999"], catalog)
        self.assertEqual(filter_meta["print_sheet_index_source"], "no_print_index_available")
        self.assertFalse(filter_meta["applied"])
        self.assertEqual(filter_meta["mode"], "none")

    def test_brenham_resolved_no_kmz_match_emits_hardcoded_brenham(self):
        # Token "1" resolves to route_476 via the constant, but the KMZ
        # catalog supplied here does not contain route_476.
        catalog = [self._brenham_route("route_999_unrelated")]
        filtered, filter_meta = M._route_filter_for_print_tokens(["1"], catalog)
        self.assertEqual(filter_meta["print_sheet_index_source"], "hardcoded_brenham")
        self.assertFalse(filter_meta["applied"])
        self.assertEqual(filter_meta["mode"], "print_to_street_extraction")
        self.assertIn("route_476", filter_meta["allowed_route_ids"])

    def test_brenham_resolved_with_kmz_match_emits_hardcoded_brenham(self):
        catalog = [self._brenham_route("route_476"), self._brenham_route("route_477")]
        filtered, filter_meta = M._route_filter_for_print_tokens(["1"], catalog)
        self.assertEqual(filter_meta["print_sheet_index_source"], "hardcoded_brenham")
        self.assertTrue(filter_meta["applied"])
        self.assertEqual(filter_meta["mode"], "print_to_street_extraction")
        self.assertEqual([r["route_id"] for r in filtered], ["route_476"])


class TestStageAIsAdditive(unittest.TestCase):
    """Stage A must not change route selection, scoring, or filter logic."""

    def test_pi4b_constant_projection_unchanged(self):
        # Stage A must not perturb `_print_to_sheets_constant_projection`,
        # which is byte-equivalent to the pre-PI.4B.2 projection contract.
        projection = M._print_to_sheets_constant_projection()
        # Every entry in the Brenham constant whose `sheet` is an int must
        # still appear in the projection with its sheet value.
        for token, entry in M.CURRENT_PACKET_PRINT_SHEET_INDEX.items():
            sheet = entry.get("sheet")
            if isinstance(sheet, int) and not isinstance(sheet, bool):
                self.assertEqual(projection[str(token)], [int(sheet)])

    def test_sheet_to_route_ids_projection_unchanged(self):
        # The reverse-projection used by P5.4 shadow diagnostics must
        # continue to expose Brenham's sheet → route_id mapping.
        projection = M._sheet_to_route_ids_from_packet_index()
        # Sheet 1 maps to route_476 in the Brenham constant.
        self.assertIn(1, projection)
        self.assertIn("route_476", projection[1])

    def test_print_sheet_index_constant_unchanged(self):
        # The 30-token Brenham PH5 constant must not be modified by Stage A.
        self.assertEqual(len(M.CURRENT_PACKET_PRINT_SHEET_INDEX), 30)
        # Spot-check a calibrated entry.
        entry_1 = M.CURRENT_PACKET_PRINT_SHEET_INDEX["1"]
        self.assertEqual(entry_1["sheet"], 1)
        self.assertEqual(entry_1["streets"], ["E STONE ST"])
        self.assertEqual(entry_1["route_ids"], ["route_476"])

    def test_hint_helper_does_not_mutate_input_tokens(self):
        tokens = ["1", "999"]
        tokens_snap = copy.deepcopy(tokens)
        M._print_sheet_hints(tokens)
        self.assertEqual(tokens, tokens_snap)

    def test_filter_helper_does_not_mutate_input_catalog(self):
        catalog = [
            {"route_id": "route_476", "route_name": "route_476", "length_ft": 500.0},
            {"route_id": "route_477", "route_name": "route_477", "length_ft": 600.0},
        ]
        catalog_snap = copy.deepcopy(catalog)
        M._route_filter_for_print_tokens(["1"], catalog)
        self.assertEqual(catalog, catalog_snap)


if __name__ == "__main__":
    unittest.main()
