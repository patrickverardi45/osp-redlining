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


class TestPageReverseTextSignal(unittest.TestCase):
    """B2b.1 — graduated reverse-text detection. A single incidental
    substring should no longer skip the page. The B2b probe (2026-05-28)
    showed the prior policy discarded 50-100% of legitimate Brenham +
    ODOT pages because `ENILHCTAM` (MATCHLINE reversed) appeared in
    column-shuffled MATCHLINE callouts on real plan sheets.
    """

    def test_single_incidental_indicator_does_not_skip(self):
        # Single `ENILHCTAM` occurrence: NOT skipped under B2b.1 (was
        # skipped under B2b).
        sig = B2.page_reverse_text_signal(
            "MATCHLINE STA 12+34 - SEE SHEET 5 ENILHCTAM"
        )
        self.assertFalse(sig["should_skip"])
        self.assertIn("ENILHCTAM", sig["indicators_matched"])
        self.assertEqual(sig["distinct_indicator_count"], 1)

    def test_two_distinct_indicators_skips(self):
        sig = B2.page_reverse_text_signal("LANOISSEFORP DESOPORP")
        self.assertTrue(sig["should_skip"])
        self.assertEqual(sig["distinct_indicator_count"], 2)

    def test_three_same_indicator_skips(self):
        sig = B2.page_reverse_text_signal(
            "LANOISSEFORP LANOISSEFORP LANOISSEFORP X"
        )
        self.assertTrue(sig["should_skip"])
        self.assertEqual(sig["max_indicator_occurrences"], 3)

    def test_two_same_indicator_does_not_skip(self):
        sig = B2.page_reverse_text_signal("LANOISSEFORP LANOISSEFORP")
        self.assertFalse(sig["should_skip"])
        self.assertEqual(sig["max_indicator_occurrences"], 2)

    def test_normal_text_not_flagged(self):
        sig = B2.page_reverse_text_signal("E STONE ST LAWNDALE AVE")
        self.assertFalse(sig["should_skip"])
        self.assertEqual(sig["distinct_indicator_count"], 0)

    def test_short_indicator_tfard_removed(self):
        # B2b had TFARD in the indicator set; B2b.1 removed it because
        # 5-letter substrings can incidentally match legitimate text.
        sig = B2.page_reverse_text_signal("TFARD ABC")
        self.assertFalse(sig["should_skip"])
        self.assertEqual(sig["distinct_indicator_count"], 0)

    def test_eerhthctaep_removed(self):
        # B2b had a typo'd `EERHTHCTAEP` (PEACHTREE-reversed was the
        # intent, but the actual reverse is EERTHCAEP). B2b.1 removed it.
        sig = B2.page_reverse_text_signal("EERHTHCTAEP street stuff")
        self.assertFalse(sig["should_skip"])
        self.assertEqual(sig["distinct_indicator_count"], 0)

    def test_empty_not_flagged(self):
        sig = B2.page_reverse_text_signal("")
        self.assertFalse(sig["should_skip"])

    def test_back_compat_page_text_is_reversed(self):
        # Legacy wrapper returns the should_skip decision.
        self.assertTrue(
            B2.page_text_is_reversed("LANOISSEFORP DESOPORP")
        )
        self.assertFalse(
            B2.page_text_is_reversed("MATCHLINE STA 12+34 SEE SHEET 5")
        )


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

    def test_reverse_text_skipped_only_on_multiple_indicators(self):
        # B2b.1 — graduated detection. A SINGLE `LANOISSEFORP` occurrence
        # no longer skips the page (was the B2b over-aggressive behavior
        # that the probe demonstrated discards 50-100% of real PDF pages).
        # Two distinct indicators DO skip.
        rec_single = B2.extract_page_street_labels_from_text(
            "LANOISSEFORP 2770 ARAPAHOE RD"
        )
        self.assertFalse(rec_single["reverse_text_skipped"])

        rec_multi = B2.extract_page_street_labels_from_text(
            "LANOISSEFORP DESOPORP some text"
        )
        self.assertTrue(rec_multi["reverse_text_skipped"])
        self.assertEqual(rec_multi["filtered_streets"], [])
        self.assertEqual(rec_multi["raw_candidates"], [])

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


class TestB2B1HardCaps(unittest.TestCase):
    """B2b.1 — hard caps on candidate shape."""

    def test_short_real_street_passes(self):
        self.assertFalse(B2.candidate_exceeds_size_caps("E STONE ST"))
        self.assertFalse(B2.candidate_exceeds_size_caps("S CHAPPELL HILL ST"))

    def test_long_paragraph_rejected_by_token_count(self):
        # The probe failure example.
        long_match = (
            "DRAWING INDEX HECTOR ELIZONDO JAMES BARRICK KHRIS JONES TEXAS "
            "DEPARTMENT OF TRANSPORTATION DIRECTOR OF OPERATIONS CITY OF "
            "BRENHAM PROJECT MANAGER PERMIT COORDINATOR CONTACT 48 HOURS "
            "PRIOR TO CONSTRUCTION BRENHAM PH 5 1305 E STONE ST"
        )
        self.assertTrue(B2.candidate_exceeds_size_caps(long_match))

    def test_long_paragraph_rejected_by_char_length(self):
        moderate_long = "ALPHA BETA GAMMA DELTA EPSILON ZETA ETA THETA ST"
        # 9 tokens — exceeds the 5-token cap regardless of char count.
        self.assertTrue(B2.candidate_exceeds_size_caps(moderate_long))

    def test_six_token_rejected_by_token_count(self):
        six_tok = "ALPHA BETA GAMMA DELTA EPSILON ST"
        self.assertTrue(B2.candidate_exceeds_size_caps(six_tok))

    def test_five_token_accepted(self):
        five_tok = "A B C D ST"
        # Token-count check passes; the single-letter rejection is a
        # separate filter (tested below).
        self.assertFalse(B2.candidate_exceeds_size_caps(five_tok))

    def test_empty_passes(self):
        self.assertFalse(B2.candidate_exceeds_size_caps(""))


class TestB2B1SingleLetterRejection(unittest.TestCase):
    """B2b.1 — column-shuffled PDF text rejection."""

    def test_column_shuffled_artifact_rejected(self):
        artifact = "L D A N V D E R A I CT"
        self.assertTrue(B2.candidate_has_adjacent_single_letters(artifact))

    def test_real_street_passes(self):
        self.assertFalse(B2.candidate_has_adjacent_single_letters("E STONE ST"))
        # `S WALNUT HILL DR` has `S` as a directional prefix — single
        # letter — but only ONE such token (not a run of 3+).
        self.assertFalse(
            B2.candidate_has_adjacent_single_letters("S WALNUT HILL DR")
        )

    def test_two_single_letters_pass(self):
        # Two adjacent single letters are still under the floor of 3.
        self.assertFalse(B2.candidate_has_adjacent_single_letters("N S ST"))


class TestB2B1FillerRatio(unittest.TestCase):
    """B2b.1 — filler ratio drops paragraph-shaped noise."""

    def test_real_street_low_filler_ratio(self):
        # `E STONE ST` body is `E STONE` — neither is filler.
        self.assertEqual(B2.candidate_filler_ratio("E STONE ST"), 0.0)

    def test_paragraph_high_filler_ratio(self):
        # Body: `THE OF FOR AND TO` (5 filler tokens).
        self.assertGreater(
            B2.candidate_filler_ratio("THE OF FOR AND TO ST"), 0.4
        )

    def test_single_token_no_division_error(self):
        # `ST` alone has no body.
        self.assertEqual(B2.candidate_filler_ratio("ST"), 0.0)


class TestB2B1BoilerplateAnywhere(unittest.TestCase):
    """B2b.1 — full-body boilerplate scan."""

    def test_drawing_anywhere_rejected(self):
        # B2b leader-only check failed this: `DRAWING INDEX ... E STONE ST`
        # has `DRAWING` as the first token (not in the B2b leader set), so
        # passed. B2b.1 expanded vocabulary + scans every non-final token.
        self.assertTrue(
            B2.has_boilerplate_anywhere("DRAWING INDEX HECTOR ELIZONDO ST")
        )

    def test_construction_mid_body_rejected(self):
        # `MAIN CONSTRUCTION ST` — CONSTRUCTION is mid-body but should now fire.
        self.assertTrue(B2.has_boilerplate_anywhere("MAIN CONSTRUCTION ST"))

    def test_brenham_in_body_rejected(self):
        self.assertTrue(B2.has_boilerplate_anywhere("BRENHAM PH 5 ST"))

    def test_real_street_passes(self):
        self.assertFalse(B2.has_boilerplate_anywhere("E STONE ST"))
        self.assertFalse(B2.has_boilerplate_anywhere("LAWNDALE AVE"))
        self.assertFalse(B2.has_boilerplate_anywhere("S CHAPPELL HILL ST"))

    def test_single_token_passes(self):
        # Pure suffix; no body to scan.
        self.assertFalse(B2.has_boilerplate_anywhere("ST"))


class TestB2B1TierACallouts(unittest.TestCase):
    """B2b.1 — constrained engineering-plan callout extraction."""

    def test_profile_callout(self):
        callouts = B2.extract_tier_a_callouts(
            "PROFILE - E STONE ST  STA 0+00 TO STA 5+50"
        )
        streets = [c["street"] for c in callouts]
        contexts = [c["context"] for c in callouts]
        self.assertIn("E STONE ST", streets)
        self.assertIn("profile", contexts)

    def test_plan_callout(self):
        callouts = B2.extract_tier_a_callouts("PLAN - NIEBUHR ST")
        streets = [c["street"] for c in callouts]
        self.assertIn("NIEBUHR ST", streets)

    def test_sheet_title_callout(self):
        callouts = B2.extract_tier_a_callouts(
            "SHEET 5 OF 30 - E TOM GREEN ST"
        )
        streets = [c["street"] for c in callouts]
        self.assertIn("E TOM GREEN ST", streets)

    def test_station_line_callout(self):
        callouts = B2.extract_tier_a_callouts(
            "LAWNDALE AVE - STA 12+34"
        )
        streets = [c["street"] for c in callouts]
        self.assertIn("LAWNDALE AVE", streets)

    def test_matchline_adjacent_callout(self):
        callouts = B2.extract_tier_a_callouts(
            "MATCHLINE STA 12+34 - SEE SHEET 5  E STONE ST"
        )
        streets = [c["street"] for c in callouts]
        self.assertIn("E STONE ST", streets)

    def test_street_and_cross_pattern(self):
        # Lunar-packet shape: `LAWNDALE AVE & HUISACHE ST`.
        callouts = B2.extract_tier_a_callouts(
            "BORE LOCATION: LAWNDALE AVE & HUISACHE ST"
        )
        streets = [c["street"] for c in callouts]
        self.assertIn("LAWNDALE AVE", streets)
        self.assertIn("HUISACHE ST", streets)

    def test_paragraph_noise_does_not_match_tier_a(self):
        # Noise paragraph that B2b's generic STREET_PATTERN incorrectly
        # captured. Tier A's constrained patterns should not match.
        noisy = (
            "DRAWING INDEX HECTOR ELIZONDO JAMES BARRICK KHRIS JONES "
            "TEXAS DEPARTMENT OF TRANSPORTATION DIRECTOR OF OPERATIONS "
            "CITY OF BRENHAM PROJECT MANAGER 1305 E STONE ST"
        )
        callouts = B2.extract_tier_a_callouts(noisy)
        # Tier A should not match — there is no PROFILE/PLAN/SHEET/STA
        # anchor before "E STONE ST" in this paragraph.
        streets = [c.get("street") for c in callouts]
        # Even if no callout matches, the function returns []; this is the
        # safe-failure happy path.
        self.assertNotIn(
            "DRAWING INDEX HECTOR ELIZONDO JAMES BARRICK KHRIS JONES "
            "TEXAS DEPARTMENT OF TRANSPORTATION DIRECTOR OF OPERATIONS "
            "CITY OF BRENHAM PROJECT MANAGER E STONE ST",
            streets,
        )

    def test_tier_a_hard_caps_applied(self):
        # If a context anchor somehow grabbed too long a body, the Tier A
        # extractor should still reject via the same size caps.
        # Construct a synthetic match: long body before ST.
        synthetic = "PROFILE - " + " ".join(["ALPHA"] * 10) + " ST"
        callouts = B2.extract_tier_a_callouts(synthetic)
        for c in callouts:
            self.assertFalse(B2.candidate_exceeds_size_caps(c["street"]))

    def test_empty_input(self):
        self.assertEqual(B2.extract_tier_a_callouts(""), [])

    def test_non_string_input(self):
        self.assertEqual(B2.extract_tier_a_callouts(None), [])  # type: ignore[arg-type]


class TestB2B1ExtractPageStreetLabelsIntegration(unittest.TestCase):
    """B2b.1 — end-to-end per-page denoise."""

    def test_paragraph_noise_dropped_at_per_page_level(self):
        noisy = (
            "DRAWING INDEX HECTOR ELIZONDO JAMES BARRICK KHRIS JONES "
            "TEXAS DEPARTMENT OF TRANSPORTATION DIRECTOR OF OPERATIONS "
            "CITY OF BRENHAM PROJECT MANAGER 1305 E STONE ST"
        )
        rec = B2.extract_page_street_labels_from_text(noisy)
        # The probe failure: a single ~33-token "street" survived to
        # `filtered_streets`. B2b.1 must drop it via hard caps OR
        # boilerplate-anywhere.
        for s in rec["filtered_streets"]:
            self.assertLessEqual(len(s.split()), 5)
            self.assertLessEqual(len(s), 40)
        # At least one filter must have fired on the long candidate.
        self.assertTrue(
            rec["length_cap_drops"] > 0
            or rec["construction_leader_drops"] > 0
        )

    def test_real_street_surfaces_via_profile_tier_a(self):
        rec = B2.extract_page_street_labels_from_text(
            "PROFILE - E STONE ST  STA 0+00 TO STA 5+50"
        )
        self.assertIn("E STONE ST", rec["filtered_streets"])
        self.assertEqual(len(rec["tier_a_callouts"]), 1)
        self.assertEqual(rec["tier_a_callouts"][0]["context"], "profile")

    def test_column_shuffle_artifact_dropped(self):
        artifact_text = "L D A N V D E R A I C FI T E U D A T L O P CT"
        rec = B2.extract_page_street_labels_from_text(artifact_text)
        # Column-shuffled artifact must not surface as a "street."
        for s in rec["filtered_streets"]:
            self.assertFalse(B2.candidate_has_adjacent_single_letters(s))

    def test_single_reverse_indicator_does_not_skip_page(self):
        # B2b would have skipped this entire page; B2b.1 should let it
        # proceed and extract real streets.
        rec = B2.extract_page_street_labels_from_text(
            "MATCHLINE STA 12+34 - SEE SHEET 5 ENILHCTAM\n"
            "PROFILE - E STONE ST"
        )
        self.assertFalse(rec["reverse_text_skipped"])
        self.assertIn("E STONE ST", rec["filtered_streets"])

    def test_multi_reverse_indicator_skips_page(self):
        rec = B2.extract_page_street_labels_from_text(
            "LANOISSEFORP DESOPORP ARAPAHOE RD"
        )
        self.assertTrue(rec["reverse_text_skipped"])
        self.assertEqual(rec["filtered_streets"], [])

    def test_b2b1_new_telemetry_fields_present(self):
        rec = B2.extract_page_street_labels_from_text(
            "PROFILE - E STONE ST"
        )
        # New B2b.1 fields must exist.
        for key in (
            "tier_a_callouts", "reverse_text_indicators",
            "length_cap_drops", "filler_ratio_drops", "single_letter_drops",
        ):
            self.assertIn(key, rec)


class TestB2B1TitleBlockInvariant(unittest.TestCase):
    """B2b.1 — title-block subtraction must remove the verbatim project
    address (e.g., `1305 E STONE ST`) WITHOUT removing the shorter
    legitimate corridor name (`E STONE ST`) when it appears as a real
    per-sheet label.

    This was the design bug discovered + corrected mid-B2b implementation;
    the invariant test is added in B2b.1 per the design packet.
    """

    def test_title_block_returns_with_number_form(self):
        tb = {"address": "1305 E STONE ST, BRENHAM, TX 77833"}
        streets = B2.compute_title_block_address_streets(tb)
        self.assertIn("1305 E STONE ST", streets)
        # Critically: the bare `E STONE ST` (post-strip form) must NOT be
        # in the title-block subtraction set, or it would collide with the
        # legitimate per-sheet corridor name on plan pages.
        self.assertNotIn("E STONE ST", streets)

    def test_corridor_name_survives_when_title_block_address_subtracted(self):
        # Synthetic per-page records: page 1 has the title-block address;
        # page 2 has the bare corridor name.
        per_page = [
            {
                "page": 1,
                "raw_candidates": ["1305 E STONE ST"],
                "filtered_streets": [],
                "reverse_text_skipped": False,
                "construction_leader_drops": 0,
                "numeric_prefix_strips": 0,
                "empty_after_strip_drops": 0,
                "length_cap_drops": 0,
                "filler_ratio_drops": 0,
                "single_letter_drops": 0,
            },
            {
                "page": 2,
                "raw_candidates": ["E STONE ST"],
                "filtered_streets": ["E STONE ST"],
                "reverse_text_skipped": False,
                "construction_leader_drops": 0,
                "numeric_prefix_strips": 0,
                "empty_after_strip_drops": 0,
                "length_cap_drops": 0,
                "filler_ratio_drops": 0,
                "single_letter_drops": 0,
            },
        ]
        out = B2.apply_cross_page_denoise(
            per_page, title_block_streets=["1305 E STONE ST"]
        )
        # Page 1's raw `1305 E STONE ST` got counted in title_block_drops;
        # page 2's bare `E STONE ST` must SURVIVE — that's the corridor
        # name we want to recover.
        self.assertEqual(out[0]["title_block_drops"], 1)
        self.assertIn("E STONE ST", out[1]["final_streets"])


if __name__ == "__main__":
    unittest.main()
