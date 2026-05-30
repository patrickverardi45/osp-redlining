"""GAC Target #1 — AP Extraction V2 (shadow-only) tests.

Locks the pure recovery contract:
- extract_ap_ids_v2 recovers APs from words+chars text that plain extract_text()
  (the strict _AP_RE) misses, validated against the numeric Terminal Port
  Handhole id set so positional-extraction noise (1/4) is dropped;
- recover_ap_ids_for_sheets_v2 unions by sheet_number;
- build_plan_pages_v2_from_pdf_paths degrades to [] (never raises);
- emit_shadow_for_group is additive + flag-OFF byte-identical (no key when OFF).
No placement / scoring / geometry is touched. Fixture AP ids are the REAL values
recovered from the PH5 PDFs by scripts/ap_extraction_probe.py.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "backend"))

from backend.app.core import pdf_ap_route_resolver as R

TERMS = {"108", "114", "121", "148", "152", "153", "154", "156", "157"}


class TestExtractApIdsV2(unittest.TestCase):

    def test_recovers_sheet3_cluster(self):
        txt = "STA 0+00 AP108 D/W AP-114 FLOWER AP 121 ELM ST"
        self.assertEqual(R.extract_ap_ids_v2(txt, TERMS), [108, 114, 121])

    def test_strict_misses_scrambled_but_v2_recovers(self):
        # the real vector-sheet failure mode: extract_text scrambles the glyphs.
        scrambled = '1" S X T 1 A 1" 1 X + 1 1 2 3 " F 1 L 1 O " W'
        self.assertEqual(sorted(int(x) for x in R._AP_RE.findall(scrambled)), [])
        # but the words/chars stream carries the contiguous tags.
        self.assertEqual(R.extract_ap_ids_v2("AP152 AP153", TERMS), [152, 153])

    def test_drops_noise_not_matching_terminals(self):
        # broad pattern may catch AP1/AP4; terminal-validation drops them.
        self.assertEqual(R.extract_ap_ids_v2("AP1 OF 30 AP4 AP108", TERMS), [108])

    def test_separators_tolerated(self):
        self.assertEqual(R.extract_ap_ids_v2("AP-148 AP_148 AP148 AP 148", {"148"}), [148])

    def test_does_not_match_inside_words(self):
        # 'SOAP108' / 'MAP121' must NOT yield 108/121 (lookbehind for letter/digit).
        self.assertEqual(R.extract_ap_ids_v2("SOAP108 MAP121", {"108", "121"}), [])

    def test_empty_text(self):
        self.assertEqual(R.extract_ap_ids_v2("", TERMS), [])
        self.assertEqual(R.extract_ap_ids_v2(None, TERMS), [])

    def test_empty_terminals(self):
        self.assertEqual(R.extract_ap_ids_v2("AP108", set()), [])

    def test_deterministic_and_sorted_unique(self):
        self.assertEqual(R.extract_ap_ids_v2("AP121 AP108 AP108 AP114", TERMS), [108, 114, 121])


class TestRecoverApIdsForSheetsV2(unittest.TestCase):

    def test_union_by_sheet(self):
        pages = [
            {"sheet_number": 8, "ap_ids_v2": [154, 156, 157]},
            {"sheet_number": 15, "ap_ids_v2": [152, 153]},
            {"sheet_number": 99, "ap_ids_v2": [999]},
            {"sheet_number": None, "ap_ids_v2": [1]},
        ]
        self.assertEqual(R.recover_ap_ids_for_sheets_v2(pages, [8, 15]),
                         [152, 153, 154, 156, 157])

    def test_empty(self):
        self.assertEqual(R.recover_ap_ids_for_sheets_v2([], [8]), [])
        self.assertEqual(
            R.recover_ap_ids_for_sheets_v2([{"sheet_number": 8, "ap_ids_v2": [1]}], []), [])


class TestBuildPlanPagesV2Degrade(unittest.TestCase):

    def test_empty_paths(self):
        self.assertEqual(R.build_plan_pages_v2_from_pdf_paths([], TERMS), [])

    def test_nonexistent_path(self):
        self.assertEqual(R.build_plan_pages_v2_from_pdf_paths(["/no/such/file.pdf"], TERMS), [])


class TestEmitShadowFlagOffByteIdentical(unittest.TestCase):
    """On the pdf_plan_data_unavailable path (empty pdf_paths) the v2 attach is
    not reached, so flag OFF and ON are both byte-identical (no v2 key)."""

    def _emit(self, **over):
        base = dict(source_file="bore_log12.xlsx", print_tokens=["3"], notes_text="",
                    pdf_paths=[], point_features=[], route_catalog=[],
                    hardcoded_allowed_route_ids=["route_476"])
        base.update(over)
        return R.emit_shadow_for_group(**base)

    def test_off_default_no_v2_key(self):
        off = self._emit(extract_ap_v2=False)
        self.assertNotIn("ap_ids_found_v2", off)
        self.assertNotIn("ap_extract_v2", off)
        # param absent == False == byte-identical
        self.assertEqual(off, self._emit())

    def test_on_without_pdfs_still_no_v2_key(self):
        on = self._emit(extract_ap_v2=True)
        self.assertNotIn("ap_ids_found_v2", on)


if __name__ == "__main__":
    unittest.main()
