"""Target #11 — terminus-type work-class shadow (default-OFF) tests.

Locks the pure classify_terminus_type contract + the required Target #10
classifications of the 14 route_480-bucket logs:
- a bore is backbone_ap_bore ONLY if a DIR.BORE run ENDS at a TERMINAL PORT HH (AP);
  an AP label alone is rejected (anti-artifact: bore_log46 end 534 / AP-161 label;
  bore_log65 ends at a FLOWER POT, not AP-155);
- flower-pot drops are classified as drops, never backbone;
- high-station bores are main_chain_high_station;
- the scope gate is_route_480_bucket_source is exactly the 14.
No placement / scoring / geometry / STATE is touched.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "backend"))

from backend.app.core import pdf_ap_route_resolver as R

# (print_tokens, station_min_ft, station_max_ft, expected_terminus_type) — the real
# Target #10 per-log values (read from the xlsx) -> the required classifications.
FIXTURES = {
    "bore_log5":  ([12],        265.0, 500.0,  "flower_pot_drop"),
    "bore_log7":  ([10],        55.0,  451.0,  "backbone_ap_bore"),
    "bore_log16": ([8, 9, 10],  5100.0, 5950.0, "main_chain_high_station"),
    "bore_log29": ([10, 12],    0.0,   415.0,  "unknown_insufficient"),
    "bore_log30": ([10, 12],    0.0,   500.0,  "flower_pot_drop"),
    "bore_log31": ([10, 12],    0.0,   260.0,  "unknown_insufficient"),
    "bore_log43": ([10],        4000.0, 5919.0, "main_chain_high_station"),
    "bore_log46": ([10, 13, 14], 0.0,  534.0,  "unknown_insufficient"),
    "bore_log47": ([10, 13, 14], 325.0, 494.0, "unknown_insufficient"),
    "bore_log48": ([10, 11, 12], 0.0,  509.0,  "flower_pot_drop"),
    "bore_log50": ([10, 11, 12], 0.0,  514.0,  "flower_pot_drop"),
    "bore_log57": ([8, 10, 13], 0.0,   413.0,  "multi_drive_unknown"),
    "bore_log58": ([8, 10, 13], 0.0,   256.0,  "unknown_insufficient"),
    "bore_log65": ([9, 10],     451.0, 650.0,  "flower_pot_drop"),
}
FLOWER_POT_LOGS = ["bore_log5", "bore_log30", "bore_log48", "bore_log50", "bore_log65"]


def _classify(stem):
    pt, smin, smax, _exp = FIXTURES[stem]
    return R.classify_terminus_type(source_file=stem + ".xlsx", print_tokens=pt,
                                    station_min_ft=smin, station_max_ft=smax)


class TestRequired14Classifications(unittest.TestCase):

    def test_all_14_match_target10(self):
        for stem, (_pt, _smin, _smax, expected) in FIXTURES.items():
            res = _classify(stem)
            self.assertEqual(res["terminus_type"], expected,
                             f"{stem}: got {res['terminus_type']} expected {expected} ({res['evidence']})")

    def test_counts(self):
        from collections import Counter
        c = Counter(_classify(s)["terminus_type"] for s in FIXTURES)
        self.assertEqual(c["flower_pot_drop"], 5)
        self.assertEqual(c["main_chain_high_station"], 2)
        self.assertEqual(c["backbone_ap_bore"], 1)
        self.assertEqual(c["multi_drive_unknown"], 1)
        self.assertEqual(c["unknown_insufficient"], 5)


class TestAntiArtifact(unittest.TestCase):

    def test_bore_log65_is_flower_pot_not_backbone(self):
        res = _classify("bore_log65")
        self.assertEqual(res["terminus_type"], "flower_pot_drop")
        self.assertNotEqual(res["terminus_type"], "backbone_ap_bore")
        # its matched run terminus is a flower pot, not an AP terminal
        ep_types = {e["endpoint_type"] for e in res["evidence"]["matched_run_endpoints"]}
        self.assertEqual(ep_types, {"flower_pot"})
        self.assertNotIn("ap", ep_types)  # NOT AP-155

    def test_bore_log7_is_backbone_ap(self):
        res = _classify("bore_log7")
        self.assertEqual(res["terminus_type"], "backbone_ap_bore")
        aps = {e["ap"] for e in res["evidence"]["matched_run_endpoints"]}
        self.assertIn(163, aps)  # ends at AP-163 run terminus

    def test_flower_pot_logs_never_backbone(self):
        for stem in FLOWER_POT_LOGS:
            res = _classify(stem)
            self.assertNotEqual(res["terminus_type"], "backbone_ap_bore",
                                f"{stem} must never be backbone_ap_bore")

    def test_bore_log46_ap161_label_rejected(self):
        # end 534 has an AP-161 *label* on sheet 14 but NO run terminus there -> NOT backbone.
        res = _classify("bore_log46")
        self.assertEqual(res["terminus_type"], "unknown_insufficient")
        self.assertNotEqual(res["terminus_type"], "backbone_ap_bore")
        self.assertEqual(res["evidence"]["matched_run_endpoints"], [])

    def test_bore_log57_ambiguous_not_backbone(self):
        # end 413 matches AP-157 (sheet 8) AND a sheet-13 matchline -> cannot call backbone.
        res = _classify("bore_log57")
        self.assertEqual(res["terminus_type"], "multi_drive_unknown")
        self.assertIn("anti_artifact_note", res["evidence"])


class TestStructure(unittest.TestCase):

    def test_main_chain_high_station(self):
        for stem in ("bore_log16", "bore_log43"):
            self.assertEqual(_classify(stem)["terminus_type"], "main_chain_high_station")

    def test_evidence_shape_and_source(self):
        res = _classify("bore_log50")
        self.assertEqual(res["source"], "target10_verified_run_endpoint_table")
        self.assertEqual(res["source"], R.TERMINUS_TYPE_SOURCE)
        ev = res["evidence"]
        for k in ("station_end_ft", "station_min_ft", "print_sheets", "matched_run_endpoints"):
            self.assertIn(k, ev)
        self.assertEqual(ev["station_end_ft"], 514.0)
        self.assertEqual(ev["print_sheets"], [10, 11, 12])
        for e in ev["matched_run_endpoints"]:
            self.assertEqual(set(e.keys()), {"sheet", "run_end_ft", "endpoint_type", "ap"})

    def test_confidence_levels(self):
        self.assertEqual(_classify("bore_log50")["confidence"], "high")   # flower_pot
        self.assertEqual(_classify("bore_log7")["confidence"], "med")     # backbone
        self.assertEqual(_classify("bore_log16")["confidence"], "med")    # main_chain
        self.assertEqual(_classify("bore_log29")["confidence"], "low")    # unknown

    def test_no_station_data(self):
        res = R.classify_terminus_type(source_file="x.xlsx", print_tokens=[10], station_max_ft=None)
        self.assertEqual(res["terminus_type"], "unknown_insufficient")

    def test_pure_no_raise_on_garbage(self):
        res = R.classify_terminus_type(source_file=None, print_tokens=["abc", None, 10],
                                       station_min_ft=None, station_max_ft=451.0)
        self.assertIn("terminus_type", res)
        # print sheet 10 + end 451 -> AP-163 terminus
        self.assertEqual(res["terminus_type"], "backbone_ap_bore")


class TestScopeGate(unittest.TestCase):

    def test_bucket_membership_is_the_14(self):
        for stem in FIXTURES:
            self.assertTrue(R.is_route_480_bucket_source(stem + ".xlsx"), stem)
        # proof-slice + other logs are NOT in the route_480 bucket
        for other in ("bore_log71.xlsx", "bore_log72.xlsx", "bore_log39.xlsx",
                      "bore_log4.xlsx", "bore_log1.xlsx", "bore_log9.xlsx"):
            self.assertFalse(R.is_route_480_bucket_source(other), other)

    def test_bucket_case_and_ext_insensitive(self):
        self.assertTrue(R.is_route_480_bucket_source("BORE_LOG7"))
        self.assertTrue(R.is_route_480_bucket_source("bore_log7.XLSX"))


if __name__ == "__main__":
    unittest.main()
