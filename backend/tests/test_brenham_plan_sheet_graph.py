"""Brenham Plan Sheet Station Graph — pure-helper unit tests. Brenham only.

Covers: station parsing, sheet→page offset, main-chain shared boundary STAs,
independent corridor axes, multi-corridor sheet behavior, bore_log16 anomaly,
Niebuhr dual-corridor route_478/479 case, CHERI/LAWNDALE external mismatch,
and deterministic output.
"""

from __future__ import annotations

import unittest

from backend.app.core import brenham_plan_sheet_graph as G


class TestStationParsing(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(G.parse_station_label("16+25"), 1625.0)
        self.assertEqual(G.parse_station_label("0+00"), 0.0)
        self.assertEqual(G.parse_station_label("104+25.5"), 10425.5)

    def test_prefix(self):
        self.assertEqual(G.parse_station_label("STA 16+25"), 1625.0)
        self.assertEqual(G.parse_station_label("STA. 33+93"), 3393.0)

    def test_numeric_passthrough(self):
        self.assertEqual(G.parse_station_label(1625.0), 1625.0)

    def test_invalid(self):
        self.assertIsNone(G.parse_station_label("not a station"))
        self.assertIsNone(G.parse_station_label(""))
        self.assertIsNone(G.parse_station_label(None))


class TestSheetToPage(unittest.TestCase):
    def test_offset_13(self):
        self.assertEqual(G.sheet_to_page(1), 14)
        self.assertEqual(G.sheet_to_page(4), 17)   # validated by SEE SHEET chain
        self.assertEqual(G.sheet_to_page(9), 22)
        self.assertEqual(G.sheet_to_page(30), 43)

    def test_out_of_range(self):
        self.assertIsNone(G.sheet_to_page(0))
        self.assertIsNone(G.sheet_to_page(31))
        self.assertIsNone(G.sheet_to_page("x"))


class TestMainChainBoundaries(unittest.TestCase):
    def test_main_chain_shared_boundary_stas(self):
        # Proven shared boundary STA values on the main corridor chain 3-9.
        self.assertEqual(G._BOUNDARY_STA_FT[frozenset((3, 4))], 1625.0)
        self.assertEqual(G._BOUNDARY_STA_FT[frozenset((4, 5))], 2018.0)
        self.assertEqual(G._BOUNDARY_STA_FT[frozenset((5, 6))], 2411.0)
        self.assertEqual(G._BOUNDARY_STA_FT[frozenset((6, 7))], 2671.0)
        self.assertEqual(G._BOUNDARY_STA_FT[frozenset((7, 8))], 3064.0)
        self.assertEqual(G._BOUNDARY_STA_FT[frozenset((8, 9))], 3393.0)

    def test_main_chain_monotonic_continuous(self):
        seq = [G._BOUNDARY_STA_FT[frozenset(p)] for p in [(3, 4), (4, 5), (5, 6), (6, 7), (7, 8), (8, 9)]]
        self.assertEqual(seq, sorted(seq))  # strictly increasing → continuous axis

    def test_main_chain_is_one_corridor(self):
        corr = G.corridor_for_sheet(5)
        for s in (3, 4, 5, 6, 7, 8, 9):
            self.assertIn(s, corr)


class TestCorridors(unittest.TestCase):
    def test_connected_components_deterministic(self):
        a = G.build_corridors()
        b = G.build_corridors()
        self.assertEqual(a, b)

    def test_niebuhr_separate_corridor(self):
        # Niebuhr sheets 17/20/21 (+2) form a corridor separate from the main chain.
        niebuhr = G.corridor_for_sheet(17)
        self.assertIn(20, niebuhr)
        self.assertIn(21, niebuhr)
        self.assertNotIn(5, niebuhr)   # main chain sheet NOT in Niebuhr corridor

    def test_isolated_sheet_is_singleton(self):
        self.assertEqual(G.corridor_for_sheet(11), [11])

    def test_independent_axis_low_vs_high(self):
        # Niebuhr corridor extent is low/local; main chain extent is high.
        main = G.corridor_extent_ft(G.corridor_for_sheet(5))
        nieb = G.corridor_extent_ft(G.corridor_for_sheet(17))
        self.assertIsNotNone(main)
        self.assertIsNotNone(nieb)
        self.assertGreater(main[1], 3000.0)   # main reaches >30+00


class TestEvaluateBoreLog(unittest.TestCase):
    def test_bore_log16_station_print_disjoint(self):
        # prints 8,9,10; station 5100-5950 → beyond all sheet windows = hard anomaly.
        ev = G.evaluate_bore_log(prints="8,9,10", station_min_ft=5100, station_max_ft=5950)
        self.assertEqual(ev["status"], G.STATUS_STATION_PRINT_DISJOINT)

    def test_niebuhr_dual_corridor_route_479(self):
        # prints 5,6 (main) + 17,21 (Niebuhr) span two corridors = over-assignment cause.
        ev = G.evaluate_bore_log(prints="5,6,17,21", station_min_ft=0, station_max_ft=243)
        self.assertEqual(ev["status"], G.STATUS_MULTI_CORRIDOR_SPAN)
        self.assertEqual(ev["corridor_count"], 2)

    def test_cheri_external_packet_mismatch(self):
        ev = G.evaluate_bore_log(
            prints="24,25", station_min_ft=1000, station_max_ft=1441,
            notes_streets=["CHERI LN"], index_streets=["POST OAK CT", "GLENDA BLVD"],
        )
        self.assertEqual(ev["status"], G.STATUS_EXTERNAL_PACKET_MISMATCH)

    def test_lawndale_external_packet_mismatch(self):
        ev = G.evaluate_bore_log(
            prints="23,24", station_min_ft=0, station_max_ft=695,
            notes_streets=["LAWNDALE AVE"], index_streets=["CARLEE DR", "POST OAK CT"],
        )
        self.assertEqual(ev["status"], G.STATUS_EXTERNAL_PACKET_MISMATCH)

    def test_clean_within_corridor(self):
        ev = G.evaluate_bore_log(prints="7", station_min_ft=200, station_max_ft=800)
        self.assertEqual(ev["status"], G.STATUS_WITHIN_CORRIDOR)
        self.assertEqual(ev["corridor_count"], 1)

    def test_unknown_when_no_valid_prints(self):
        ev = G.evaluate_bore_log(prints="99,100", station_min_ft=0, station_max_ft=10)
        self.assertEqual(ev["status"], G.STATUS_UNKNOWN)

    def test_no_external_mismatch_when_streets_align(self):
        # notes street present in index streets → no external flag; multi-corridor or within.
        ev = G.evaluate_bore_log(
            prints="7", station_min_ft=200, station_max_ft=800,
            notes_streets=["E STONE ST"], index_streets=["E STONE ST"],
        )
        self.assertNotEqual(ev["status"], G.STATUS_EXTERNAL_PACKET_MISMATCH)

    def test_pages_reported(self):
        ev = G.evaluate_bore_log(prints="4", station_min_ft=1700, station_max_ft=1900)
        self.assertEqual(ev["pages"], [17])  # sheet 4 → page 17

    def test_schema_version(self):
        ev = G.evaluate_bore_log(prints="7")
        self.assertEqual(ev["schema_version"], "brenham-plan-sheet-graph-1")


class TestDeterminism(unittest.TestCase):
    def test_print_order_independent(self):
        a = G.evaluate_bore_log(prints="5,6,17,21", station_min_ft=0, station_max_ft=243)
        b = G.evaluate_bore_log(prints="21,17,6,5", station_min_ft=243, station_max_ft=0)
        self.assertEqual(a["status"], b["status"])
        self.assertEqual(a["corridors"], b["corridors"])
        self.assertEqual(a["sheets"], b["sheets"])

    def test_repeat_call_identical(self):
        kw = dict(prints="8,9,10", station_min_ft=5100, station_max_ft=5950)
        self.assertEqual(G.evaluate_bore_log(**kw), G.evaluate_bore_log(**kw))


if __name__ == "__main__":
    unittest.main()
