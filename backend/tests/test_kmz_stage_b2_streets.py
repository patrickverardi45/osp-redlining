"""KMZ Hardening Stage B2b — pure-helper unit tests.

Covers the denoise pipeline + per-page extraction + per-sheet aggregation +
per-token projection + constant-comparison primitives in
`backend/app/core/kmz_stage_b2_streets.py`. These helpers are pure: no
STATE, no PDF I/O at the per-page level (the PDF-opening wrapper has its
own test via the shadow-write telemetry tests).

Stage B2b is OBSERVATION ONLY — no scoring / selection / filter behavior
changes. This file locks the additive contract.
"""

from __future__ import annotations

import copy
import os
import unittest

os.environ.setdefault("TRUELINE_JWT_SECRET", "stage-b2-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "stage-b2-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend.app.core import kmz_stage_b2_streets as B2


class TestStripNumericPrefix(unittest.TestCase):
    def test_strips_leading_address_number(self):
        self.assertEqual(B2.strip_numeric_prefix("708 PEACHTREE DR"), "PEACHTREE DR")

    def test_strips_leading_callout_glued_to_address(self):
        # B2a finding: '06 708 PEACHTREE DR' — strip only first numeric run.
        self.assertEqual(B2.strip_numeric_prefix("06 708 PEACHTREE DR"), "708 PEACHTREE DR")

    def test_no_strip_when_no_leading_number(self):
        self.assertEqual(B2.strip_numeric_prefix("E STONE ST"), "E STONE ST")

    def test_strips_decimal_lookalike(self):
        # Leading '2.5' should be stripped (greedy first-numeric-run).
        self.assertEqual(B2.strip_numeric_prefix("2.5 LAWNDALE AVE"), "LAWNDALE AVE")

    def test_empty_input(self):
        self.assertEqual(B2.strip_numeric_prefix(""), "")

    def test_non_string_input(self):
        self.assertEqual(B2.strip_numeric_prefix(None), "")
        self.assertEqual(B2.strip_numeric_prefix(42), "")


class TestHasConstructionLeader(unittest.TestCase):
    def test_proposed_leader_detected(self):
        self.assertTrue(B2.has_construction_leader("PROPOSED CARLEE DR"))

    def test_existing_leader_detected(self):
        self.assertTrue(B2.has_construction_leader("EXISTING NIEBUHR ST"))

    def test_depth_leader_detected(self):
        self.assertTrue(B2.has_construction_leader("DEPTH 905 LAWNDALE AVE"))

    def test_real_street_passes(self):
        self.assertFalse(B2.has_construction_leader("E STONE ST"))
        self.assertFalse(B2.has_construction_leader("LAWNDALE AVE"))
        self.assertFalse(B2.has_construction_leader("CARLEE DR"))

    def test_empty_passes(self):
        self.assertFalse(B2.has_construction_leader(""))


class TestPageTextIsReversed(unittest.TestCase):
    def test_lanoisseforp_detected(self):
        # B2a finding: ODOT_CREEK_27 had 'LANOISSEFORP' (PROFESSIONAL reversed)
        # across 13 of 15 pages — rotated title-block stamp extracted in
        # reverse reading order.
        self.assertTrue(B2.page_text_is_reversed("LANOISSEFORP 2770 ARAPAHOE RD"))

    def test_tfard_detected(self):
        self.assertTrue(B2.page_text_is_reversed("TFARD DRAFT"))

    def test_normal_text_not_flagged(self):
        self.assertFalse(B2.page_text_is_reversed("E STONE ST LAWNDALE AVE"))

    def test_empty_not_flagged(self):
        self.assertFalse(B2.page_text_is_reversed(""))


class TestExtractPageStreetLabelsFromText(unittest.TestCase):
    """Per-page denoise pipeline."""

    def test_real_street_surfaces(self):
        rec = B2.extract_page_street_labels_from_text(
            "PROFILE - E STONE ST  STA 0+00 TO STA 5+50"
        )
        self.assertIn("E STONE ST", rec["filtered_streets"])
        self.assertFalse(rec["reverse_text_skipped"])

    def test_construction_leader_dropped(self):
        rec = B2.extract_page_street_labels_from_text("PROPOSED CARLEE DR")
        # The 'PROPOSED CARLEE DR' raw match is dropped by construction-leader
        # filter; final filtered list does not include the candidate.
        self.assertNotIn("PROPOSED CARLEE DR", rec["filtered_streets"])
        self.assertGreaterEqual(rec["construction_leader_drops"], 1)

    def test_numeric_prefix_stripped(self):
        rec = B2.extract_page_street_labels_from_text("06 708 PEACHTREE DR")
        # Either '708 PEACHTREE DR' or 'PEACHTREE DR' surfaces (depending on
        # how many strip iterations apply); the bare prefix '06' is gone.
        self.assertTrue(any("PEACHTREE DR" in s for s in rec["filtered_streets"]))
        self.assertGreaterEqual(rec["numeric_prefix_strips"], 1)

    def test_reverse_text_skipped(self):
        rec = B2.extract_page_street_labels_from_text(
            "LANOISSEFORP 2770 ARAPAHOE RD"
        )
        self.assertTrue(rec["reverse_text_skipped"])
        self.assertEqual(rec["filtered_streets"], [])
        self.assertEqual(rec["raw_candidates"], [])

    def test_empty_input(self):
        rec = B2.extract_page_street_labels_from_text("")
        self.assertEqual(rec["filtered_streets"], [])
        self.assertEqual(rec["raw_candidates"], [])
        self.assertFalse(rec["reverse_text_skipped"])

    def test_non_string_input(self):
        rec = B2.extract_page_street_labels_from_text(None)  # type: ignore[arg-type]
        self.assertEqual(rec["filtered_streets"], [])

    def test_helper_does_not_mutate_input(self):
        text = "PROFILE - E STONE ST"
        text_snap = copy.deepcopy(text)
        B2.extract_page_street_labels_from_text(text)
        self.assertEqual(text, text_snap)


class TestComputeTitleBlockAddressStreets(unittest.TestCase):
    def test_extracts_address_street(self):
        tb = {"address": "1305 E STONE ST, BRENHAM, TX 77833"}
        streets = B2.compute_title_block_address_streets(tb)
        self.assertIn("1305 E STONE ST", streets)

    def test_handles_none(self):
        self.assertEqual(B2.compute_title_block_address_streets(None), [])

    def test_handles_missing_address(self):
        self.assertEqual(B2.compute_title_block_address_streets({}), [])

    def test_does_not_mutate_input(self):
        tb = {"address": "1305 E STONE ST, BRENHAM, TX 77833"}
        tb_snap = copy.deepcopy(tb)
        B2.compute_title_block_address_streets(tb)
        self.assertEqual(tb, tb_snap)


class TestApplyCrossPageDenoise(unittest.TestCase):
    """Title-block subtraction + frequency-filter denoise across pages."""

    def _per_page(self, n_pages: int, repeating_street: str, unique_per_page: bool):
        records = []
        for page in range(1, n_pages + 1):
            streets = [repeating_street]
            if unique_per_page:
                streets.append(f"STREET_{page} ST")
            records.append({
                "page": page,
                "raw_candidates": list(streets),
                "filtered_streets": list(streets),
                "reverse_text_skipped": False,
                "construction_leader_drops": 0,
                "numeric_prefix_strips": 0,
                "empty_after_strip_drops": 0,
            })
        return records

    def test_title_block_subtraction(self):
        per_page = self._per_page(5, "TITLE BLOCK ST", unique_per_page=True)
        out = B2.apply_cross_page_denoise(per_page, title_block_streets=["TITLE BLOCK ST"])
        for rec in out:
            self.assertNotIn("TITLE BLOCK ST", rec["final_streets"])
            self.assertTrue(rec["title_block_subtracted"])

    def test_frequency_filter_drops_repeated_street(self):
        # 'REPEATED ST' appears on every page -> 5/5 = 100% >= 70% floor -> filtered out.
        per_page = self._per_page(5, "REPEATED ST", unique_per_page=True)
        out = B2.apply_cross_page_denoise(per_page, title_block_streets=[])
        for rec in out:
            self.assertNotIn("REPEATED ST", rec["final_streets"])
            self.assertGreaterEqual(rec["frequency_filter_drops"], 1)

    def test_unique_streets_preserved(self):
        # 'STREET_3 ST' appears only on page 3 -> 1/5 = 20% < 70% -> kept.
        per_page = self._per_page(5, "REPEATED ST", unique_per_page=True)
        out = B2.apply_cross_page_denoise(per_page, title_block_streets=[])
        # The unique-per-page street should survive on its page.
        rec_3 = next(r for r in out if r["page"] == 3)
        self.assertIn("STREET_3 ST", rec_3["final_streets"])

    def test_reverse_skipped_page_passthrough(self):
        per_page = [
            {
                "page": 1,
                "raw_candidates": [],
                "filtered_streets": [],
                "reverse_text_skipped": True,
                "construction_leader_drops": 0,
                "numeric_prefix_strips": 0,
                "empty_after_strip_drops": 0,
            },
        ]
        out = B2.apply_cross_page_denoise(per_page, title_block_streets=[])
        self.assertEqual(out[0]["final_streets"], [])

    def test_does_not_mutate_input(self):
        per_page = self._per_page(3, "REPEATED ST", unique_per_page=True)
        snap = copy.deepcopy(per_page)
        B2.apply_cross_page_denoise(per_page, title_block_streets=["TB"])
        self.assertEqual(per_page, snap)


class TestDeriveSheetToStreets(unittest.TestCase):
    def test_basic_aggregation(self):
        per_page = [
            {"page": 1, "final_streets": ["E STONE ST"]},
            {"page": 2, "final_streets": ["E STONE ST"]},
            {"page": 3, "final_streets": ["NIEBUHR ST"]},
        ]
        page_to_sheet = {1: 1, 2: 1, 3: 2}
        out = B2.derive_sheet_to_streets(per_page, page_to_sheet)
        self.assertEqual(out[1], ["E STONE ST"])
        self.assertEqual(out[2], ["NIEBUHR ST"])

    def test_unresolved_pages_dropped(self):
        per_page = [
            {"page": 1, "final_streets": ["E STONE ST"]},
            {"page": 2, "final_streets": ["GHOST ST"]},
        ]
        page_to_sheet = {1: 1, 2: None}
        out = B2.derive_sheet_to_streets(per_page, page_to_sheet)
        self.assertEqual(out, {1: ["E STONE ST"]})
        self.assertNotIn(2, out)

    def test_dedupe_across_pages(self):
        per_page = [
            {"page": 1, "final_streets": ["E STONE ST", "BRUCE ST"]},
            {"page": 2, "final_streets": ["E STONE ST", "CARLEE DR"]},
        ]
        page_to_sheet = {1: 5, 2: 5}
        out = B2.derive_sheet_to_streets(per_page, page_to_sheet)
        self.assertEqual(set(out[5]), {"E STONE ST", "BRUCE ST", "CARLEE DR"})

    def test_handles_none(self):
        self.assertEqual(B2.derive_sheet_to_streets(None, None), {})  # type: ignore[arg-type]
        self.assertEqual(B2.derive_sheet_to_streets([], {}), {})


class TestDerivePrintToSheetStreets(unittest.TestCase):
    def test_basic_projection(self):
        sheet_to_streets = {1: ["E STONE ST"], 5: ["NIEBUHR ST"]}
        out = B2.derive_print_to_sheet_streets(sheet_to_streets, ["1", "5"])
        self.assertEqual(out["1"], ["E STONE ST"])
        self.assertEqual(out["5"], ["NIEBUHR ST"])

    def test_token_not_in_catalog(self):
        out = B2.derive_print_to_sheet_streets({1: ["X"]}, ["999"])
        self.assertIsNone(out["999"])

    def test_non_digit_token(self):
        out = B2.derive_print_to_sheet_streets({1: ["X"]}, ["abc"])
        self.assertIsNone(out["abc"])

    def test_zero_token(self):
        out = B2.derive_print_to_sheet_streets({1: ["X"]}, ["0"])
        self.assertIsNone(out["0"])

    def test_empty_inputs(self):
        self.assertEqual(B2.derive_print_to_sheet_streets({}, []), {})
        self.assertEqual(B2.derive_print_to_sheet_streets(None, None), {})  # type: ignore[arg-type]


class TestCompareDerivedToConstant(unittest.TestCase):
    def test_subset_agreement_high(self):
        constant = {"streets": ["E STONE ST"], "route_ids": ["route_476"]}
        cmp_ = B2.compare_derived_to_constant("1", ["E STONE ST"], constant)
        self.assertEqual(cmp_["agreement"], "derived_subset_of_constant")
        self.assertEqual(cmp_["confidence"], "high")

    def test_partial_overlap_medium(self):
        constant = {"streets": ["E STONE ST", "NIEBUHR ST"], "route_ids": ["route_476"]}
        cmp_ = B2.compare_derived_to_constant("1", ["E STONE ST", "BRUCE ST"], constant)
        self.assertEqual(cmp_["agreement"], "partial_overlap")
        self.assertEqual(cmp_["confidence"], "medium")

    def test_disjoint_conflict_abstain(self):
        constant = {"streets": ["E STONE ST"], "route_ids": ["route_476"]}
        cmp_ = B2.compare_derived_to_constant("1", ["LAWNDALE AVE"], constant)
        self.assertEqual(cmp_["agreement"], "disjoint_conflict")
        self.assertEqual(cmp_["confidence"], "abstain")

    def test_derived_empty_low(self):
        constant = {"streets": ["E STONE ST"], "route_ids": ["route_476"]}
        cmp_ = B2.compare_derived_to_constant("1", [], constant)
        self.assertEqual(cmp_["agreement"], "derived_empty_constant_present")
        self.assertEqual(cmp_["confidence"], "low")

    def test_both_empty_null(self):
        cmp_ = B2.compare_derived_to_constant("999", [], None)
        self.assertEqual(cmp_["agreement"], "both_empty")
        self.assertEqual(cmp_["confidence"], "null")

    def test_constant_none(self):
        cmp_ = B2.compare_derived_to_constant("999", ["X"], None)
        self.assertEqual(cmp_["confidence"], "low")

    def test_does_not_mutate_inputs(self):
        constant = {"streets": ["E STONE ST"], "route_ids": ["route_476"]}
        constant_snap = copy.deepcopy(constant)
        derived = ["E STONE ST"]
        derived_snap = copy.deepcopy(derived)
        B2.compare_derived_to_constant("1", derived, constant)
        self.assertEqual(constant, constant_snap)
        self.assertEqual(derived, derived_snap)


if __name__ == "__main__":
    unittest.main()
