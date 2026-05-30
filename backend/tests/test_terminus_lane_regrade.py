"""Target #12 — terminus-aware LANE re-grade in placement_proof (default-OFF) tests.

Locks the read-only re-grader surface:
- flag OFF (no terminus_lane_by_source) => placement_proof byte-identical (no
  `terminus_lane` rows, no `terminus_regrade`);
- flag ON (lane map passed) => additive only: per-row `terminus_lane` + a top-level
  `terminus_regrade` lane summary, with EVERYTHING ELSE byte-identical;
- the 14 route_480 logs bucket exactly: DROP=5, BACKBONE_AP=[bore_log7], MAIN_CHAIN=2,
  MULTI_DRIVE_UNKNOWN=1, UNKNOWN=5;
- flower-pot drops are NEVER backbone-safe; bore_log7 is the lone BACKBONE_AP candidate.
No placement / scoring / geometry / STATE is touched.
"""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "backend"))

from backend.app.core.match_review_queue import assemble_placement_proof, _terminus_lane_record
from backend.app.core import pdf_ap_route_resolver as R

# (print_tokens, station_min_ft, station_max_ft) — the real Target #10/#11 per-log values.
FIXTURES = {
    "bore_log5":  ([12],        265.0, 500.0),
    "bore_log7":  ([10],        55.0,  451.0),
    "bore_log16": ([8, 9, 10],  5100.0, 5950.0),
    "bore_log29": ([10, 12],    0.0,   415.0),
    "bore_log30": ([10, 12],    0.0,   500.0),
    "bore_log31": ([10, 12],    0.0,   260.0),
    "bore_log43": ([10],        4000.0, 5919.0),
    "bore_log46": ([10, 13, 14], 0.0,  534.0),
    "bore_log47": ([10, 13, 14], 325.0, 494.0),
    "bore_log48": ([10, 11, 12], 0.0,  509.0),
    "bore_log50": ([10, 11, 12], 0.0,  514.0),
    "bore_log57": ([8, 10, 13], 0.0,   413.0),
    "bore_log58": ([8, 10, 13], 0.0,   256.0),
    "bore_log65": ([9, 10],     451.0, 650.0),
}
FLOWER_POT = {"bore_log5", "bore_log30", "bore_log48", "bore_log50", "bore_log65"}


def _diag():
    out = []
    for stem, (pt, smin, smax) in FIXTURES.items():
        out.append({"source_file": stem + ".xlsx", "render_allowed": False,
                    "stopped_at": "abstained_location_evidence_mismatch",
                    "print_tokens": pt, "min_station_ft": smin, "max_station_ft": smax})
    return out


def _lane_map():
    return {stem + ".xlsx": R.classify_terminus_type(
        source_file=stem + ".xlsx", print_tokens=pt, station_min_ft=smin, station_max_ft=smax)
        for stem, (pt, smin, smax) in FIXTURES.items()}


class TestFlagOffByteIdentical(unittest.TestCase):

    def test_off_has_no_terminus_keys(self):
        pp = assemble_placement_proof(_diag())
        self.assertNotIn("terminus_regrade", pp)
        for row in pp["rows"]:
            self.assertNotIn("terminus_lane", row)

    def test_off_equals_param_absent(self):
        self.assertEqual(assemble_placement_proof(_diag(), terminus_lane_by_source=None),
                         assemble_placement_proof(_diag()))


class TestFlagOnAdditive(unittest.TestCase):

    def test_on_is_additive_only(self):
        off = assemble_placement_proof(_diag())
        on = assemble_placement_proof(_diag(), terminus_lane_by_source=_lane_map())
        self.assertIn("terminus_regrade", on)
        # strip the additive keys from ON -> must equal OFF exactly
        stripped = copy.deepcopy(on)
        stripped.pop("terminus_regrade", None)
        for row in stripped["rows"]:
            row.pop("terminus_lane", None)
        self.assertEqual(stripped, off)

    def test_every_bucket_row_gets_a_lane(self):
        on = assemble_placement_proof(_diag(), terminus_lane_by_source=_lane_map())
        for row in on["rows"]:
            self.assertIn("terminus_lane", row)
            self.assertIn(row["terminus_lane"]["lane"],
                          {"DROP", "BACKBONE_AP", "MAIN_CHAIN_HIGH_STATION",
                           "MULTI_DRIVE_UNKNOWN", "UNKNOWN"})


class TestLaneTable(unittest.TestCase):

    def setUp(self):
        self.rg = assemble_placement_proof(_diag(), terminus_lane_by_source=_lane_map())["terminus_regrade"]

    def test_counts(self):
        self.assertEqual(self.rg["counts"], {
            "DROP": 5, "BACKBONE_AP": 1, "MAIN_CHAIN_HIGH_STATION": 2,
            "MULTI_DRIVE_UNKNOWN": 1, "UNKNOWN": 5})

    def test_lane_membership(self):
        self.assertEqual(set(self.rg["lanes"]["DROP"]),
                         {"bore_log5.xlsx", "bore_log30.xlsx", "bore_log48.xlsx",
                          "bore_log50.xlsx", "bore_log65.xlsx"})
        self.assertEqual(self.rg["lanes"]["BACKBONE_AP"], ["bore_log7.xlsx"])
        self.assertEqual(set(self.rg["lanes"]["MAIN_CHAIN_HIGH_STATION"]),
                         {"bore_log16.xlsx", "bore_log43.xlsx"})
        self.assertEqual(self.rg["lanes"]["MULTI_DRIVE_UNKNOWN"], ["bore_log57.xlsx"])
        self.assertEqual(set(self.rg["lanes"]["UNKNOWN"]),
                         {"bore_log29.xlsx", "bore_log31.xlsx", "bore_log46.xlsx",
                          "bore_log47.xlsx", "bore_log58.xlsx"})

    def test_backbone_ap_candidates_is_only_bore_log7(self):
        self.assertEqual(self.rg["backbone_ap_candidates"], ["bore_log7.xlsx"])

    def test_blocked_from_backbone_is_13(self):
        self.assertEqual(len(self.rg["blocked_from_backbone"]), 13)
        self.assertNotIn("bore_log7.xlsx", self.rg["blocked_from_backbone"])
        for fp in FLOWER_POT:
            self.assertIn(fp + ".xlsx", self.rg["blocked_from_backbone"])


class TestSafety(unittest.TestCase):

    def test_flower_pots_never_backbone(self):
        on = assemble_placement_proof(_diag(), terminus_lane_by_source=_lane_map())
        by_sf = {r["source_file"]: r for r in on["rows"]}
        for fp in FLOWER_POT:
            tl = by_sf[fp + ".xlsx"]["terminus_lane"]
            self.assertEqual(tl["lane"], "DROP")
            self.assertFalse(tl["backbone_ap_candidate"])
            self.assertFalse(tl["backbone_promotion_ready"])

    def test_bore_log7_is_backbone_ap_candidate(self):
        on = assemble_placement_proof(_diag(), terminus_lane_by_source=_lane_map())
        by_sf = {r["source_file"]: r for r in on["rows"]}
        tl = by_sf["bore_log7.xlsx"]["terminus_lane"]
        self.assertEqual(tl["lane"], "BACKBONE_AP")
        self.assertTrue(tl["backbone_ap_candidate"])
        self.assertFalse(tl["backbone_promotion_ready"])  # candidate != ready

    def test_no_row_is_backbone_promotion_ready(self):
        on = assemble_placement_proof(_diag(), terminus_lane_by_source=_lane_map())
        for row in on["rows"]:
            self.assertFalse(row["terminus_lane"]["backbone_promotion_ready"])


class TestLaneRecordUnit(unittest.TestCase):

    def test_mapping(self):
        self.assertEqual(_terminus_lane_record({"terminus_type": "flower_pot_drop"})["lane"], "DROP")
        self.assertEqual(_terminus_lane_record({"terminus_type": "backbone_ap_bore"})["lane"], "BACKBONE_AP")
        self.assertTrue(_terminus_lane_record({"terminus_type": "backbone_ap_bore"})["backbone_ap_candidate"])
        self.assertFalse(_terminus_lane_record({"terminus_type": "flower_pot_drop"})["backbone_ap_candidate"])

    def test_none_input(self):
        self.assertIsNone(_terminus_lane_record(None))
        self.assertIsNone(_terminus_lane_record("not a dict"))

    def test_unknown_type_defaults_to_unknown_lane(self):
        rec = _terminus_lane_record({"terminus_type": "something_new"})
        self.assertEqual(rec["lane"], "UNKNOWN")
        self.assertFalse(rec["backbone_ap_candidate"])


class TestNonBucketRowNoLane(unittest.TestCase):

    def test_row_absent_from_lane_map_has_no_terminus_lane(self):
        # a non-bucket log (not in the lane map) must not get a terminus_lane.
        diag = _diag() + [{"source_file": "bore_log9.xlsx", "render_allowed": True,
                           "stopped_at": None, "selected_route_id": "route_479"}]
        on = assemble_placement_proof(diag, terminus_lane_by_source=_lane_map())
        by_sf = {r["source_file"]: r for r in on["rows"]}
        self.assertNotIn("terminus_lane", by_sf["bore_log9.xlsx"])


if __name__ == "__main__":
    unittest.main()
