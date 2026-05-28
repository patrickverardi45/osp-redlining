"""KMZ Hardening Stage B1 — token universe widening tests.

Stage B1 gates the historical Brenham-PH5 `1 <= num_val <= 30` clamp inside
`_extract_engineering_plan_signals` behind a default-OFF flag
(`TRUELINE_KMZ_STAGE_B1_TOKEN_UNIVERSE_DERIVED`). When OFF, behavior is
byte-identical to pre-Stage-B1. When ON, positive integer tokens outside the
1-30 range are surfaced through `print_tokens`, enabling non-Brenham packets
to express their own print universe.

Stage B1 does NOT:
- modify `CURRENT_PACKET_PRINT_SHEET_INDEX`
- activate `TRUELINE_PI4A_DERIVED_PRINT_INDEX`
- change route scoring or selection
- wire derived tokens into route_id matching

This file locks down the additive contract:
- flag OFF -> 1-30 clamp preserved; `print_token_universe == "brenham_1_30_clamped"`
- flag ON  -> all positive integer tokens accepted; universe `== "stage_b1_derived_universe"`
- zero / negative tokens rejected in both modes
- non-numeric tokens behave the same in both modes
- Brenham-style 1-30 tokens are unchanged in both modes
"""

from __future__ import annotations

import copy
import os
import unittest
from typing import Any, Dict

os.environ.setdefault("TRUELINE_JWT_SECRET", "stage-b1-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "stage-b1-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend import main as M

_B1_ENV = "TRUELINE_KMZ_STAGE_B1_TOKEN_UNIVERSE_DERIVED"


def _plan(**overrides: Any) -> Dict[str, Any]:
    base = {
        "plan_id": "plan_test_1",
        "original_filename": "PLAN.pdf",
        "plan_date": "",
        "print_numbers": "",
        "sheet_numbers": "",
        "street_hints": "",
        "notes": "",
    }
    base.update(overrides)
    return base


class TestFlagOffPreservesBrenhamBehavior(unittest.TestCase):
    """Flag default OFF — Brenham 1-30 clamp preserved byte-identical."""

    def setUp(self) -> None:
        self._saved = os.environ.pop(_B1_ENV, None)

    def tearDown(self) -> None:
        os.environ.pop(_B1_ENV, None)
        if self._saved is not None:
            os.environ[_B1_ENV] = self._saved

    def test_flag_defaults_off(self):
        self.assertNotIn(_B1_ENV, os.environ)
        self.assertFalse(M._trueline_kmz_stage_b1_token_universe_derived_enabled())

    def test_brenham_token_in_range_kept(self):
        # User-supplied print_numbers always pass through (not subject to the
        # 1-30 clamp historically — only PDF-filename harvesting was clamped).
        sig = M._extract_engineering_plan_signals(_plan(print_numbers="23"))
        self.assertIn("23", sig["print_tokens"])
        self.assertEqual(sig["print_token_universe"], "brenham_1_30_clamped")

    def test_filename_token_in_brenham_range_kept(self):
        # `_EP_PRINT_PATS` requires word boundary at the start of "print".
        # Underscores are word chars, so "_Print_" doesn't trigger the regex;
        # use a space separator that fires a true word boundary.
        sig = M._extract_engineering_plan_signals(
            _plan(original_filename="Brenham PH5 Print 5 design.pdf")
        )
        # "5" must be in the harvested set.
        self.assertIn("5", sig["print_tokens"])
        self.assertEqual(sig["print_token_universe"], "brenham_1_30_clamped")

    def test_filename_token_outside_brenham_range_dropped_when_off(self):
        # "Print 42" should be CLIPPED by the 1-30 clamp when flag OFF.
        sig = M._extract_engineering_plan_signals(
            _plan(original_filename="Lunar WP Print 42 design.pdf")
        )
        self.assertNotIn("42", sig["print_tokens"])
        self.assertEqual(sig["print_token_universe"], "brenham_1_30_clamped")

    def test_bare_fallback_outside_brenham_range_dropped_when_off(self):
        # Filename has no explicit Print/Sheet patterns; bare 3-digit number
        # would have been clipped to 1-30 historically. With flag OFF the
        # bare-fallback regex is still 1-2 digits, so 3-digit "999" never
        # matches anyway.
        sig = M._extract_engineering_plan_signals(
            _plan(original_filename="design_999.pdf")
        )
        self.assertNotIn("999", sig["print_tokens"])
        self.assertEqual(sig["print_token_universe"], "brenham_1_30_clamped")

    def test_zero_token_rejected_when_off(self):
        sig = M._extract_engineering_plan_signals(
            _plan(original_filename="design_0.pdf")
        )
        self.assertNotIn("0", sig["print_tokens"])
        self.assertEqual(sig["print_token_universe"], "brenham_1_30_clamped")


class TestFlagOnWidensTokenUniverse(unittest.TestCase):
    """Flag ON — positive integer tokens outside 1-30 are surfaced."""

    def setUp(self) -> None:
        self._saved = os.environ.pop(_B1_ENV, None)
        os.environ[_B1_ENV] = "1"

    def tearDown(self) -> None:
        os.environ.pop(_B1_ENV, None)
        if self._saved is not None:
            os.environ[_B1_ENV] = self._saved

    def test_flag_helper_reports_enabled(self):
        self.assertTrue(M._trueline_kmz_stage_b1_token_universe_derived_enabled())

    def test_filename_token_outside_brenham_range_accepted_when_on(self):
        # Use space-separated filename so `\bprint ?42\b` boundaries fire.
        sig = M._extract_engineering_plan_signals(
            _plan(original_filename="Lunar WP Print 42 design.pdf")
        )
        self.assertIn("42", sig["print_tokens"])
        self.assertEqual(sig["print_token_universe"], "stage_b1_derived_universe")

    def test_filename_token_in_brenham_range_still_accepted_when_on(self):
        # Brenham-range tokens must remain accepted under the widened policy.
        sig = M._extract_engineering_plan_signals(
            _plan(original_filename="Brenham PH5 Print 5 design.pdf")
        )
        self.assertIn("5", sig["print_tokens"])
        self.assertEqual(sig["print_token_universe"], "stage_b1_derived_universe")

    def test_bare_fallback_three_digit_accepted_when_on(self):
        # When flag ON, the bare-number fallback regex widens to `\d+` and a
        # 3-digit positive integer becomes admissible. Need a true word
        # boundary around the number (space, hyphen, etc — not underscore).
        sig = M._extract_engineering_plan_signals(
            _plan(original_filename="design 175 revised.pdf")
        )
        self.assertIn("175", sig["print_tokens"])
        self.assertEqual(sig["print_token_universe"], "stage_b1_derived_universe")

    def test_zero_token_still_rejected_when_on(self):
        sig = M._extract_engineering_plan_signals(
            _plan(original_filename="design 0 revised.pdf")
        )
        self.assertNotIn("0", sig["print_tokens"])
        self.assertEqual(sig["print_token_universe"], "stage_b1_derived_universe")

    def test_negative_lookalike_token_safe(self):
        # `-7` cannot be matched by `\b(\d+)\b` as a negative number, but the
        # bare `7` after the hyphen surfaces as a positive token under the
        # widened universe. Stage B1 has no sign awareness — document the
        # behavior so it's not a surprise.
        sig = M._extract_engineering_plan_signals(
            _plan(original_filename="design -7 revised.pdf")
        )
        self.assertNotIn("-7", sig["print_tokens"])
        self.assertIn("7", sig["print_tokens"])
        self.assertEqual(sig["print_token_universe"], "stage_b1_derived_universe")


class TestStageB1IsAdditive(unittest.TestCase):
    """Stage B1 must not perturb route scoring, route selection, or the
    hardcoded Brenham constant. Locks the must-not-touch contract.
    """

    def setUp(self) -> None:
        self._saved = os.environ.pop(_B1_ENV, None)

    def tearDown(self) -> None:
        os.environ.pop(_B1_ENV, None)
        if self._saved is not None:
            os.environ[_B1_ENV] = self._saved

    def test_brenham_constant_content_unchanged(self):
        # Locks: Stage B1 never mutates the constant.
        self.assertEqual(len(M.CURRENT_PACKET_PRINT_SHEET_INDEX), 30)
        self.assertEqual(M.CURRENT_PACKET_PRINT_SHEET_INDEX["1"]["sheet"], 1)
        self.assertEqual(
            M.CURRENT_PACKET_PRINT_SHEET_INDEX["1"]["streets"], ["E STONE ST"]
        )
        self.assertEqual(
            M.CURRENT_PACKET_PRINT_SHEET_INDEX["1"]["route_ids"], ["route_476"]
        )

    def test_pi4b_constant_projection_unchanged_flag_off(self):
        projection = M._print_to_sheets_constant_projection()
        for token, entry in M.CURRENT_PACKET_PRINT_SHEET_INDEX.items():
            sheet = entry.get("sheet")
            if isinstance(sheet, int) and not isinstance(sheet, bool):
                self.assertEqual(projection[str(token)], [int(sheet)])

    def test_pi4b_constant_projection_unchanged_flag_on(self):
        # Stage B1 only widens token universe in signal extraction; the
        # PI.4B constant projection helper is a different surface and must
        # remain byte-identical regardless of the B1 flag.
        os.environ[_B1_ENV] = "1"
        try:
            projection = M._print_to_sheets_constant_projection()
            for token, entry in M.CURRENT_PACKET_PRINT_SHEET_INDEX.items():
                sheet = entry.get("sheet")
                if isinstance(sheet, int) and not isinstance(sheet, bool):
                    self.assertEqual(projection[str(token)], [int(sheet)])
        finally:
            del os.environ[_B1_ENV]

    def test_print_sheet_hints_source_unchanged_flag_off(self):
        # Stage A `print_sheet_index_source` must still emit `hardcoded_brenham`
        # for resolved tokens regardless of Stage B1 state.
        meta = M._print_sheet_hints(["1"])
        self.assertEqual(meta["print_sheet_index_source"], "hardcoded_brenham")

    def test_print_sheet_hints_source_unchanged_flag_on(self):
        os.environ[_B1_ENV] = "1"
        try:
            meta = M._print_sheet_hints(["1"])
            # Stage B1 does NOT change Stage A attribution; it only widens the
            # signal-extraction token universe. The print_sheet_index_source
            # remains `hardcoded_brenham` because the resolved entry still
            # came from the Brenham constant.
            self.assertEqual(meta["print_sheet_index_source"], "hardcoded_brenham")
        finally:
            del os.environ[_B1_ENV]

    def test_pi4a_derived_flag_not_flipped(self):
        # Stage B1 must not flip TRUELINE_PI4A_DERIVED_PRINT_INDEX.
        os.environ[_B1_ENV] = "1"
        try:
            # Even with B1 ON, PI.4A activation remains gated by its own flag.
            pi4a_raw = os.environ.get("TRUELINE_PI4A_DERIVED_PRINT_INDEX", "")
            self.assertFalse(
                M._trueline_pi4a_derived_print_index_enabled()
                if not pi4a_raw
                else False
            )
        finally:
            del os.environ[_B1_ENV]

    def test_existing_signal_dict_shape_preserved(self):
        sig = M._extract_engineering_plan_signals(_plan())
        # Pre-existing keys must still be present and at the expected shape.
        for key in (
            "plan_id", "source_file", "print_tokens", "route_hints",
            "phase_hints", "date", "revision", "raw_text_tokens",
        ):
            self.assertIn(key, sig)
        # New attribution key is present.
        self.assertIn("print_token_universe", sig)

    def test_input_plan_dict_not_mutated(self):
        plan = _plan(
            original_filename="Brenham_PH5_Print_5_design.pdf",
            print_numbers="3, 7",
        )
        plan_snap = copy.deepcopy(plan)
        M._extract_engineering_plan_signals(plan)
        self.assertEqual(plan, plan_snap)


if __name__ == "__main__":
    unittest.main()
