"""Layer-1 synthetic tests for derive_anchor_station_colocations and
_apply_station_colocation (PI.2).

No PDFs, no fixtures, no STATE. Every test constructs synthetic
positional anchor records in-process. extract_anchor_positions is
PDF-touching; it is covered indirectly via the fixture-gated mixin
tests in test_engineering_plan_parser.py.

What is being locked down:
  - input-validation refusal paths
  - nearest-station search and distance bands at boundaries
  - splice path mirrors AP path
  - equation-kind stations refused (never matched)
  - range-kind stations map to range start; reason cites "range"
  - tied-distance disagreement -> refusal; tied agreement -> deterministic pick
  - cross-page guard (anchor never matches a station on another page)
  - confidence ladder values
  - input immutability for derive_* and _apply_*
  - _apply_station_colocation join contract

COMMAND
-------
    python -m pytest backend/tests/test_anchor_station_colocations.py -v

The helper performs no I/O; this suite has no fixture dependencies.
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

os.environ.setdefault("TRUELINE_JWT_SECRET", "pi2-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "pi2-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from app.services import engineering_plan_parser as pp  # noqa: E402

derive = pp.derive_anchor_station_colocations
apply_co = pp._apply_station_colocation


# ---------------------------------------------------------------------------
# Constructors
# ---------------------------------------------------------------------------

def _ap(page: int, canonical: str, ts: int, te: int) -> Dict[str, Any]:
    return {
        "page": int(page),
        "kind": pp._COLOCATION_KIND_AP,
        "canonical": str(canonical),
        "station_ft": None,
        "second_station_ft": None,
        "text_start": int(ts),
        "text_end": int(te),
        "raw_text": str(canonical),
    }


def _splice(page: int, canonical: str, ts: int, te: int) -> Dict[str, Any]:
    return {
        "page": int(page),
        "kind": pp._COLOCATION_KIND_SPLICE,
        "canonical": str(canonical),
        "station_ft": None,
        "second_station_ft": None,
        "text_start": int(ts),
        "text_end": int(te),
        "raw_text": str(canonical),
    }


def _sta(
    page: int, station_ft: int, kind: str, ts: int, te: int,
    second_ft: Optional[int] = None,
) -> Dict[str, Any]:
    """kind is 'single' | 'range' | 'equation'."""
    kind_map = {
        "single":   pp._COLOCATION_KIND_STATION_SINGLE,
        "range":    pp._COLOCATION_KIND_STATION_RANGE,
        "equation": pp._COLOCATION_KIND_STATION_EQUATION,
    }
    return {
        "page": int(page),
        "kind": kind_map[kind],
        "canonical": None,
        "station_ft": int(station_ft),
        "second_station_ft": int(second_ft) if second_ft is not None else None,
        "text_start": int(ts),
        "text_end": int(te),
        "raw_text": f"STA {station_ft // 100}+{station_ft % 100:02d}",
    }


def _ap_record(page: int, canonical: str) -> Dict[str, Any]:
    """Synthetic AP record matching extract_ap_ids output shape."""
    return {
        "page": int(page),
        "ap_id_raw": canonical,
        "ap_id_canonical": str(canonical),
        "source_sheet": int(page),  # PI.1 enrichment; not exercised here
    }


def _splice_record(page: int, canonical: str) -> Dict[str, Any]:
    return {
        "page": int(page),
        "splice_id_raw": canonical,
        "splice_id_canonical": str(canonical),
        "source_sheet": int(page),
    }


# ===========================================================================
# V — Input validation (4 tests)
# ===========================================================================

class InputValidation(unittest.TestCase):

    def test_v1_returns_empty_list_when_input_none(self) -> None:
        self.assertEqual(derive(None), [])

    def test_v2_returns_empty_list_when_input_wrong_type(self) -> None:
        self.assertEqual(derive("not-a-list"), [])  # type: ignore[arg-type]

    def test_v3_tolerates_malformed_records_silently(self) -> None:
        out = derive([None, "junk", {"page": "x"}, {"kind": 42}, {}])
        # No raises; all anchors are unparseable; output is empty.
        self.assertEqual(out, [])

    def test_v4_empty_input_returns_empty_list(self) -> None:
        self.assertEqual(derive([]), [])


# ===========================================================================
# N — Single-AP nearest at boundaries (5 tests)
# ===========================================================================

class SingleApNearest(unittest.TestCase):

    def test_n1_zero_distance_is_tight_high(self) -> None:
        # AP at (100, 105), station at (105, 115) -> distance 0
        out = derive([
            _ap(1, "AP-1", 100, 105),
            _sta(1, 550, "single", 105, 115),
        ])
        self.assertEqual(len(out), 1)
        c = out[0]
        self.assertEqual(c["station_ft"], 550)
        self.assertEqual(c["station_distance_chars"], 0)
        self.assertEqual(c["station_source"], pp._COLOCATION_SOURCE_TIGHT)
        self.assertEqual(c["station_confidence"], pp._COLOCATION_CONF_HIGH)

    def test_n2_distance_30_is_tight_inclusive(self) -> None:
        out = derive([
            _ap(1, "AP-1", 100, 105),
            _sta(1, 550, "single", 135, 145),  # distance = 30
        ])
        c = out[0]
        self.assertEqual(c["station_distance_chars"], 30)
        self.assertEqual(c["station_confidence"], pp._COLOCATION_CONF_HIGH)

    def test_n3_distance_31_is_medium(self) -> None:
        out = derive([
            _ap(1, "AP-1", 100, 105),
            _sta(1, 550, "single", 136, 146),  # distance = 31
        ])
        c = out[0]
        self.assertEqual(c["station_distance_chars"], 31)
        self.assertEqual(c["station_confidence"], pp._COLOCATION_CONF_MEDIUM)

    def test_n4_distance_80_is_medium_inclusive(self) -> None:
        out = derive([
            _ap(1, "AP-1", 100, 105),
            _sta(1, 550, "single", 185, 195),  # distance = 80
        ])
        c = out[0]
        self.assertEqual(c["station_distance_chars"], 80)
        self.assertEqual(c["station_confidence"], pp._COLOCATION_CONF_MEDIUM)

    def test_n5_distance_151_is_refused(self) -> None:
        out = derive([
            _ap(1, "AP-1", 100, 105),
            _sta(1, 550, "single", 256, 266),  # distance = 151
        ])
        c = out[0]
        self.assertIsNone(c["station_ft"])
        self.assertEqual(c["station_source"], pp._COLOCATION_SOURCE_NONE)
        self.assertEqual(c["station_confidence"], pp._COLOCATION_CONF_UNCERTAIN)
        self.assertIn(pp._COLOCATION_AMBIGUITY_OUT_OF_WINDOW, c["ambiguity_flags"])


# ===========================================================================
# P — Splice path (3 tests)
# ===========================================================================

class SpliceNearest(unittest.TestCase):

    def test_p1_zero_distance_tight(self) -> None:
        out = derive([
            _splice(1, "SPLICE-7", 100, 110),
            _sta(1, 720, "single", 110, 120),  # distance 0
        ])
        c = out[0]
        self.assertEqual(c["anchor_type"], "splice")
        self.assertEqual(c["anchor_canonical"], "SPLICE-7")
        self.assertEqual(c["station_ft"], 720)
        self.assertEqual(c["station_confidence"], pp._COLOCATION_CONF_HIGH)

    def test_p2_distance_90_is_loose(self) -> None:
        out = derive([
            _splice(1, "SPLICE-7", 100, 110),
            _sta(1, 720, "single", 200, 210),  # distance 90
        ])
        c = out[0]
        self.assertEqual(c["station_distance_chars"], 90)
        self.assertEqual(c["station_source"], pp._COLOCATION_SOURCE_LOOSE)
        self.assertEqual(c["station_confidence"], pp._COLOCATION_CONF_LOW)

    def test_p3_no_stations_on_page_refusal(self) -> None:
        out = derive([_splice(1, "SPLICE-7", 100, 110)])
        c = out[0]
        self.assertIsNone(c["station_ft"])
        self.assertIn(pp._COLOCATION_AMBIGUITY_NO_STATIONS, c["ambiguity_flags"])


# ===========================================================================
# E — Equation skipped (3 tests)
# ===========================================================================

class EquationSkipped(unittest.TestCase):

    def test_e1_only_equation_stations_refusal(self) -> None:
        out = derive([
            _ap(1, "AP-1", 100, 105),
            _sta(1, 550, "equation", 105, 130, second_ft=325),
        ])
        c = out[0]
        self.assertIsNone(c["station_ft"])
        self.assertIn(pp._COLOCATION_AMBIGUITY_ALL_EQUATIONS, c["ambiguity_flags"])

    def test_e2_equation_closer_but_skipped_single_chosen(self) -> None:
        # Equation at distance 0, single at distance 30 -> single wins.
        out = derive([
            _ap(1, "AP-1", 100, 105),
            _sta(1, 555, "equation", 105, 130, second_ft=325),
            _sta(1, 600, "single", 135, 145),  # distance 30
        ])
        c = out[0]
        self.assertEqual(c["station_ft"], 600)
        self.assertEqual(c["station_distance_chars"], 30)

    def test_e3_equation_and_range_in_window_range_chosen(self) -> None:
        out = derive([
            _ap(1, "AP-1", 100, 105),
            _sta(1, 555, "equation", 105, 130, second_ft=325),
            _sta(1, 660, "range", 140, 160, second_ft=720),  # distance 35
        ])
        c = out[0]
        self.assertEqual(c["station_ft"], 660)
        self.assertEqual(c["station_kind"], "range")


# ===========================================================================
# R — Range mapping (3 tests)
# ===========================================================================

class RangeMapping(unittest.TestCase):

    def test_r1_ap_nearest_range_uses_start(self) -> None:
        out = derive([
            _ap(1, "AP-1", 100, 105),
            _sta(1, 550, "range", 105, 125, second_ft=720),  # start = 550
        ])
        c = out[0]
        self.assertEqual(c["station_ft"], 550)
        self.assertEqual(c["station_kind"], "range")
        self.assertIn("range; using start", c["station_reason"])

    def test_r2_range_with_nonzero_start_uses_start(self) -> None:
        out = derive([
            _ap(1, "AP-1", 100, 105),
            _sta(1, 1234, "range", 105, 125, second_ft=2000),
        ])
        c = out[0]
        self.assertEqual(c["station_ft"], 1234)

    def test_r3_range_and_single_equidistant_agree_no_ambiguity(self) -> None:
        # Both at distance 30, both station_ft=500 -> match (agreement).
        out = derive([
            _ap(1, "AP-1", 100, 105),
            _sta(1, 500, "single", 135, 145),     # distance 30
            _sta(1, 500, "range", 135, 145, second_ft=600),  # also distance 30
        ])
        c = out[0]
        self.assertEqual(c["station_ft"], 500)
        # Deterministic pick: lowest text_start then text_end. Both tied
        # at (135, 145); kind doesn't influence pick.
        self.assertIn(c["station_kind"], ("single", "range"))


# ===========================================================================
# A — Ambiguity / ties (3 tests)
# ===========================================================================

class Ambiguity(unittest.TestCase):

    def test_a1_two_singles_tied_disagree_refusal(self) -> None:
        out = derive([
            _ap(1, "AP-1", 100, 105),
            _sta(1, 400, "single", 75, 95),    # distance 5
            _sta(1, 800, "single", 110, 130),  # distance 5
        ])
        c = out[0]
        self.assertIsNone(c["station_ft"])
        self.assertIn(pp._COLOCATION_AMBIGUITY_TIED_DISTANCE, c["ambiguity_flags"])

    def test_a2_two_ranges_tied_disagree_refusal(self) -> None:
        out = derive([
            _ap(1, "AP-1", 100, 105),
            _sta(1, 400, "range", 75, 95, second_ft=500),
            _sta(1, 800, "range", 110, 130, second_ft=900),
        ])
        c = out[0]
        self.assertIsNone(c["station_ft"])
        self.assertIn(pp._COLOCATION_AMBIGUITY_TIED_DISTANCE, c["ambiguity_flags"])

    def test_a3_three_stations_two_tied_disagree_refusal(self) -> None:
        out = derive([
            _ap(1, "AP-1", 100, 105),
            _sta(1, 400, "single", 75, 95),     # distance 5
            _sta(1, 800, "single", 110, 130),   # distance 5 (tied disagree)
            _sta(1, 600, "single", 200, 220),   # distance 95 (farther)
        ])
        c = out[0]
        self.assertIsNone(c["station_ft"])
        self.assertIn(pp._COLOCATION_AMBIGUITY_TIED_DISTANCE, c["ambiguity_flags"])


# ===========================================================================
# X — Cross-page guard (2 tests)
# ===========================================================================

class CrossPageGuard(unittest.TestCase):

    def test_x1_ap_on_page_4_with_stations_only_on_page_5_refusal(self) -> None:
        out = derive([
            _ap(4, "AP-1", 100, 105),
            _sta(5, 550, "single", 100, 110),  # different page
        ])
        c = out[0]
        self.assertIsNone(c["station_ft"])
        self.assertIn(pp._COLOCATION_AMBIGUITY_NO_STATIONS, c["ambiguity_flags"])

    def test_x2_ap_matches_same_page_only_ignoring_other_pages(self) -> None:
        out = derive([
            _ap(4, "AP-1", 100, 105),
            _sta(4, 550, "single", 110, 120),  # same page, distance 5 -> match
            _sta(5, 999, "single", 100, 110),  # different page, ignored
        ])
        c = out[0]
        self.assertEqual(c["station_ft"], 550)
        self.assertEqual(c["page"], 4)


# ===========================================================================
# C — Confidence ladder (3 tests)
# ===========================================================================

class ConfidenceLadder(unittest.TestCase):

    def test_c1_distance_25_tight_high(self) -> None:
        out = derive([
            _ap(1, "AP-1", 100, 105),
            _sta(1, 550, "single", 130, 140),  # distance 25
        ])
        c = out[0]
        self.assertEqual(c["station_distance_chars"], 25)
        self.assertEqual(c["station_source"], pp._COLOCATION_SOURCE_TIGHT)
        self.assertEqual(c["station_confidence"], pp._COLOCATION_CONF_HIGH)

    def test_c2_distance_60_proximity_medium(self) -> None:
        out = derive([
            _ap(1, "AP-1", 100, 105),
            _sta(1, 550, "single", 165, 175),  # distance 60
        ])
        c = out[0]
        self.assertEqual(c["station_distance_chars"], 60)
        self.assertEqual(c["station_source"], pp._COLOCATION_SOURCE_PROXIMITY)
        self.assertEqual(c["station_confidence"], pp._COLOCATION_CONF_MEDIUM)

    def test_c3_distance_120_loose_low(self) -> None:
        out = derive([
            _ap(1, "AP-1", 100, 105),
            _sta(1, 550, "single", 225, 235),  # distance 120
        ])
        c = out[0]
        self.assertEqual(c["station_distance_chars"], 120)
        self.assertEqual(c["station_source"], pp._COLOCATION_SOURCE_LOOSE)
        self.assertEqual(c["station_confidence"], pp._COLOCATION_CONF_LOW)


# ===========================================================================
# I — Immutability (2 tests)
# ===========================================================================

class Immutability(unittest.TestCase):

    def test_i1_derive_does_not_mutate_input(self) -> None:
        positions = [
            _ap(1, "AP-1", 100, 105),
            _sta(1, 550, "single", 110, 120),
        ]
        snap = copy.deepcopy(positions)
        derive(positions)
        self.assertEqual(positions, snap)

    def test_i2_apply_does_not_mutate_inputs(self) -> None:
        records = [_ap_record(1, "AP-1")]
        colocations = derive([
            _ap(1, "AP-1", 100, 105),
            _sta(1, 550, "single", 110, 120),
        ])
        rec_snap = copy.deepcopy(records)
        co_snap = copy.deepcopy(colocations)
        apply_co(records, colocations, "ap", "ap_id_canonical")
        self.assertEqual(records, rec_snap)
        self.assertEqual(colocations, co_snap)


# ===========================================================================
# Y — _apply_station_colocation contract (4 tests)
# ===========================================================================

class ApplyContract(unittest.TestCase):

    def test_y1_matching_colocation_fills_fields(self) -> None:
        records = [_ap_record(1, "AP-1")]
        colocations = derive([
            _ap(1, "AP-1", 100, 105),
            _sta(1, 550, "single", 110, 120),  # distance 5
        ])
        out = apply_co(records, colocations, "ap", "ap_id_canonical")
        self.assertEqual(out[0]["station_ft"], 550)
        self.assertEqual(out[0]["station_confidence"], pp._COLOCATION_CONF_HIGH)
        self.assertEqual(out[0]["station_distance_chars"], 5)
        self.assertEqual(out[0]["station_source"], pp._COLOCATION_SOURCE_TIGHT)

    def test_y2_no_matching_colocation_refusal_payload(self) -> None:
        records = [_ap_record(1, "AP-99")]
        colocations = derive([
            _ap(1, "AP-1", 100, 105),
            _sta(1, 550, "single", 110, 120),
        ])
        out = apply_co(records, colocations, "ap", "ap_id_canonical")
        self.assertIsNone(out[0]["station_ft"])
        self.assertEqual(out[0]["station_source"], pp._COLOCATION_SOURCE_NONE)
        self.assertEqual(out[0]["station_confidence"],
                         pp._COLOCATION_CONF_UNCERTAIN)
        self.assertIsNone(out[0]["station_distance_chars"])

    def test_y3_upstream_station_ft_is_preserved(self) -> None:
        records = [{**_ap_record(1, "AP-1"), "station_ft": 777}]
        colocations = derive([
            _ap(1, "AP-1", 100, 105),
            _sta(1, 550, "single", 110, 120),
        ])
        out = apply_co(records, colocations, "ap", "ap_id_canonical")
        # Upstream value preserved; co-location not applied.
        self.assertEqual(out[0]["station_ft"], 777)
        self.assertEqual(out[0]["station_source"],
                         pp._COLOCATION_SOURCE_UPSTREAM)
        self.assertIn("pre-set upstream", out[0]["station_reason"])

    def test_y4_wrong_anchor_type_filter_excludes_colocation(self) -> None:
        records = [_splice_record(1, "SPLICE-7")]
        # Build colocations as ap_type — filter should exclude these
        # for the splice apply call.
        colocations = derive([
            _ap(1, "SPLICE-7", 100, 105),  # canonical reused but anchor_type=ap
            _sta(1, 550, "single", 110, 120),
        ])
        out = apply_co(records, colocations, "splice", "splice_id_canonical")
        self.assertIsNone(out[0]["station_ft"])
        self.assertEqual(out[0]["station_source"], pp._COLOCATION_SOURCE_NONE)


if __name__ == "__main__":
    unittest.main()
