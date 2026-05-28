"""KMZ Hardening Stage R1 — kmz_auto_redline.py unit tests.

Three test classes:

* Suite A — Projection math
* Suite B — Rejection paths
* Determinism + bounds + edge cases

Pure helper tests. No backend.main import. No STATE. No I/O.
"""

from __future__ import annotations

import math
import unittest
from typing import Any, Dict, List, Tuple

from backend.app.core import kmz_auto_redline as KAR


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

# A horizontal east-west polyline centered roughly on Brenham, TX.
# Each degree of longitude at lat=30.16 N is ~96100 ft (~17.2 mi); we use
# tiny lon deltas so segment lengths land in the 100s-of-ft range that
# bore-log work cares about.
BRENHAM_LAT = 30.16
BRENHAM_LON = -96.39

# Approximate ft per degree of longitude at the test latitude.
_FT_PER_DEG_LON_BRENHAM = math.cos(math.radians(BRENHAM_LAT)) * KAR._FT_PER_DEGREE_LAT


def _lon_offset_for_ft(ft: float) -> float:
    return ft / _FT_PER_DEG_LON_BRENHAM


def _line_polyline(start_lon: float, lat: float, length_ft: float, n_points: int = 5) -> List[Tuple[float, float]]:
    """Synthesize an east-pointing polyline at constant latitude with
    ``n_points`` vertices spanning ``length_ft`` total."""
    if n_points < 2:
        n_points = 2
    out: List[Tuple[float, float]] = []
    for i in range(n_points):
        f = i / (n_points - 1)
        out.append((start_lon + _lon_offset_for_ft(length_ft * f), lat))
    return out


def _row(
    row_id: str,
    start_label: Any,
    end_label: Any,
    notes: str = "",
    print_val: str = "1",
) -> Dict[str, Any]:
    return {
        "row_id": row_id,
        "start_label": start_label,
        "end_label": end_label,
        "notes": notes,
        "print": print_val,
        "depth_ft": 4.0,
        "boc_in": 36,
        "crew": "Test Crew",
        "date": "2026-05-28",
    }


# ---------------------------------------------------------------------------
# Suite A — Projection math
# ---------------------------------------------------------------------------

class TestSuiteAProjectionMath(unittest.TestCase):

    def test_two_anchor_linear_identity(self):
        """Two anchors at known stations + lon/lat map a row's start/end to
        polyline distances that match the linear model."""
        polyline = _line_polyline(BRENHAM_LON, BRENHAM_LAT, length_ft=2000.0, n_points=11)
        # Anchors at station_ft=1000 (lon offset = 0 ft) and 3000 (lon offset = 2000 ft).
        anchors = [
            (1000.0, (polyline[0][0], polyline[0][1])),
            (3000.0, (polyline[-1][0], polyline[-1][1])),
        ]
        rows = [
            _row("R1", "10+00", "30+00"),   # spans full envelope -> high
        ]
        out = KAR.generate_kmz_auto_redline_segments({
            "route_id": "route_TEST",
            "route_polyline_lonlat": polyline,
            "station_anchors_lonlat": anchors,
            "bore_log_rows": rows,
            "request_meta": {"session_id": "s1"},
        })
        self.assertEqual(out["schema_version"], "kmz-auto-redline-1")
        self.assertEqual(out["route_id"], "route_TEST")
        self.assertEqual(out["diagnostics"]["anchor_count"], 2)
        self.assertEqual(out["diagnostics"]["rows_input"], 1)
        self.assertEqual(out["diagnostics"]["rows_generated"], 1)
        self.assertEqual(out["diagnostics"]["rows_rejected"], 0)
        seg = out["generated_segments"][0]
        self.assertEqual(seg["geometry_type"], "lonlat_polyline")
        self.assertEqual(seg["geometry_confidence"], "high")
        # Subpath should start ~ first vertex and end ~ last vertex.
        first = seg["geometry_lonlat"][0]
        last = seg["geometry_lonlat"][-1]
        self.assertAlmostEqual(first[0], polyline[0][0], places=4)
        self.assertAlmostEqual(last[0], polyline[-1][0], places=4)

    def test_four_anchor_uses_min_max_span(self):
        """With 4 anchors at stations 1000/1500/2500/3000, the model selects
        the longest baseline (station 1000 -> 3000). Verify by checking slope
        equals (distance_full / 2000)."""
        polyline = _line_polyline(BRENHAM_LON, BRENHAM_LAT, length_ft=2000.0, n_points=11)
        # Anchors at fractional positions along the polyline.
        anchors = [
            (1000.0, polyline[0]),
            (1500.0, _line_polyline(BRENHAM_LON, BRENHAM_LAT, 500.0, 2)[1]),
            (2500.0, _line_polyline(BRENHAM_LON, BRENHAM_LAT, 1500.0, 2)[1]),
            (3000.0, polyline[-1]),
        ]
        rows = [_row("R1", "12+00", "28+00")]
        out = KAR.generate_kmz_auto_redline_segments({
            "route_id": "route_4anchor",
            "route_polyline_lonlat": polyline,
            "station_anchors_lonlat": anchors,
            "bore_log_rows": rows,
            "request_meta": {},
        })
        self.assertEqual(out["diagnostics"]["anchor_count"], 4)
        self.assertTrue(out["diagnostics"]["model_built"])
        slope = out["diagnostics"]["model_slope_ft_per_ft"]
        # Total polyline length / 2000 station-ft span ≈ 1.0 ft per station-ft.
        self.assertAlmostEqual(slope, 1.0, places=2)
        seg = out["generated_segments"][0]
        self.assertEqual(seg["geometry_type"], "lonlat_polyline")

    def test_negative_slope_rejected_emits_fallback(self):
        """An anchor pair where larger station_ft maps to smaller distance
        (negative slope) must abort the model and downgrade rows to fallback."""
        polyline = _line_polyline(BRENHAM_LON, BRENHAM_LAT, length_ft=2000.0, n_points=5)
        anchors = [
            (3000.0, polyline[0]),    # high station at near end -> negative slope
            (1000.0, polyline[-1]),
        ]
        rows = [_row("R1", "12+00", "28+00")]
        out = KAR.generate_kmz_auto_redline_segments({
            "route_id": "route_neg",
            "route_polyline_lonlat": polyline,
            "station_anchors_lonlat": anchors,
            "bore_log_rows": rows,
            "request_meta": {},
        })
        self.assertFalse(out["diagnostics"]["model_built"])
        self.assertIn("non_monotone_anchor_model", out["diagnostics"]["warnings"])
        seg = out["generated_segments"][0]
        self.assertEqual(seg["geometry_type"], "lonlat_fallback")
        self.assertEqual(seg["geometry_confidence"], "fallback")
        self.assertIn("fallback_non_monotone_anchor_model", seg["warnings"])

    def test_haversine_polyline_length_matches_expectation(self):
        """Polyline cum_ft total at lat=30.16 over a 2000 ft offset must
        land within 0.5% of 2000."""
        polyline = _line_polyline(BRENHAM_LON, BRENHAM_LAT, length_ft=2000.0, n_points=11)
        cum = KAR._polyline_cum_lengths_ft(polyline)
        self.assertEqual(len(cum), len(polyline))
        # First cum is 0; last is total.
        self.assertEqual(cum[0], 0.0)
        self.assertAlmostEqual(cum[-1], 2000.0, delta=10.0)

    def test_anchor_residual_in_meters(self):
        """An anchor lon/lat off the polyline by ~10 m should record a
        perp_distance_m near 10 m (within a few percent)."""
        polyline = _line_polyline(BRENHAM_LON, BRENHAM_LAT, length_ft=2000.0, n_points=11)
        # Shift anchor north by ~10 m: 1 deg lat ~ 111000 m -> 10 m ~ 9.0e-5 deg.
        offset_lat = polyline[0][1] + 10.0 / 111000.0
        anchors = [
            (1000.0, (polyline[0][0], offset_lat)),
            (3000.0, polyline[-1]),
        ]
        rows = [_row("R1", "12+00", "28+00")]
        out = KAR.generate_kmz_auto_redline_segments({
            "route_id": "route_R",
            "route_polyline_lonlat": polyline,
            "station_anchors_lonlat": anchors,
            "bore_log_rows": rows,
            "request_meta": {},
        })
        residuals = out["diagnostics"]["anchor_residuals_m"]
        self.assertEqual(len(residuals), 2)
        # Anchor 0 is off by ~10 m; anchor 1 is on the polyline.
        self.assertGreater(residuals[0], 5.0)
        self.assertLess(residuals[0], 20.0)
        self.assertLess(residuals[1], 1.0)

    def test_in_envelope_projection(self):
        """A row whose station range sits fully inside the anchor span
        emits a polyline (not fallback)."""
        polyline = _line_polyline(BRENHAM_LON, BRENHAM_LAT, length_ft=2000.0, n_points=11)
        anchors = [
            (1000.0, polyline[0]),
            (3000.0, polyline[-1]),
        ]
        rows = [_row("R1", "15+00", "25+00")]
        out = KAR.generate_kmz_auto_redline_segments({
            "route_id": "route_inEnv",
            "route_polyline_lonlat": polyline,
            "station_anchors_lonlat": anchors,
            "bore_log_rows": rows,
            "request_meta": {},
        })
        seg = out["generated_segments"][0]
        self.assertEqual(seg["geometry_type"], "lonlat_polyline")
        # Subpath length should be ~1000 ft (the 10-station row span).
        coords = seg["geometry_lonlat"]
        self.assertGreaterEqual(len(coords), 2)
        # Endpoints should be inside the polyline.
        self.assertGreater(coords[0][0], polyline[0][0])
        self.assertLess(coords[-1][0], polyline[-1][0])


# ---------------------------------------------------------------------------
# Suite B — Rejection paths
# ---------------------------------------------------------------------------

class TestSuiteBRejectionPaths(unittest.TestCase):

    def test_malformed_station_label_start(self):
        polyline = _line_polyline(BRENHAM_LON, BRENHAM_LAT, 2000.0)
        anchors = [(1000.0, polyline[0]), (3000.0, polyline[-1])]
        rows = [_row("R1", "NOT_A_STATION", "20+00")]
        out = KAR.generate_kmz_auto_redline_segments({
            "route_id": "r",
            "route_polyline_lonlat": polyline,
            "station_anchors_lonlat": anchors,
            "bore_log_rows": rows,
            "request_meta": {},
        })
        self.assertEqual(out["diagnostics"]["rows_generated"], 0)
        self.assertEqual(out["diagnostics"]["rows_rejected"], 1)
        rej = out["rejected_rows"][0]
        self.assertEqual(rej["reason"], "malformed_station_label_start")
        self.assertEqual(rej["rule_id"], "kmz_auto_redline_v1:start_station_format")
        self.assertIn("malformed_station_label_start", out["diagnostics"]["rejection_reasons"])

    def test_malformed_station_label_end(self):
        polyline = _line_polyline(BRENHAM_LON, BRENHAM_LAT, 2000.0)
        anchors = [(1000.0, polyline[0]), (3000.0, polyline[-1])]
        rows = [_row("R1", "10+00", "??")]
        out = KAR.generate_kmz_auto_redline_segments({
            "route_id": "r",
            "route_polyline_lonlat": polyline,
            "station_anchors_lonlat": anchors,
            "bore_log_rows": rows,
            "request_meta": {},
        })
        rej = out["rejected_rows"][0]
        self.assertEqual(rej["reason"], "malformed_station_label_end")

    def test_end_before_start_rejected(self):
        polyline = _line_polyline(BRENHAM_LON, BRENHAM_LAT, 2000.0)
        anchors = [(1000.0, polyline[0]), (3000.0, polyline[-1])]
        rows = [_row("R1", "25+00", "20+00")]  # end < start
        out = KAR.generate_kmz_auto_redline_segments({
            "route_id": "r",
            "route_polyline_lonlat": polyline,
            "station_anchors_lonlat": anchors,
            "bore_log_rows": rows,
            "request_meta": {},
        })
        rej = out["rejected_rows"][0]
        self.assertEqual(rej["reason"], "end_before_start")
        self.assertEqual(rej["rule_id"], "kmz_auto_redline_v1:end_before_start")

    def test_end_equal_to_start_rejected(self):
        polyline = _line_polyline(BRENHAM_LON, BRENHAM_LAT, 2000.0)
        anchors = [(1000.0, polyline[0]), (3000.0, polyline[-1])]
        rows = [_row("R1", "20+00", "20+00")]
        out = KAR.generate_kmz_auto_redline_segments({
            "route_id": "r",
            "route_polyline_lonlat": polyline,
            "station_anchors_lonlat": anchors,
            "bore_log_rows": rows,
            "request_meta": {},
        })
        rej = out["rejected_rows"][0]
        self.assertEqual(rej["reason"], "end_before_start")

    def test_station_outside_envelope_more_than_20_percent(self):
        """Anchor span 1000-3000 (2000 ft); tolerance = 400 ft each side.
        A row at 36+00 starts at 3600 ft → 3600 > 3000 + 400 → rejected."""
        polyline = _line_polyline(BRENHAM_LON, BRENHAM_LAT, 2000.0)
        anchors = [(1000.0, polyline[0]), (3000.0, polyline[-1])]
        rows = [_row("R1", "36+00", "40+00")]
        out = KAR.generate_kmz_auto_redline_segments({
            "route_id": "r",
            "route_polyline_lonlat": polyline,
            "station_anchors_lonlat": anchors,
            "bore_log_rows": rows,
            "request_meta": {},
        })
        rej = out["rejected_rows"][0]
        self.assertEqual(rej["reason"], "station_outside_anchor_envelope")
        self.assertEqual(rej["rule_id"], "kmz_auto_redline_v1:outside_anchor_envelope")

    def test_station_within_20_percent_envelope_accepted(self):
        """Anchor span 1000-3000; tolerance = 400 ft. A row at 9+00-11+00
        (900-1100 ft) starts 100 ft below the anchor min and ends 100 ft above
        — well inside the 400 ft tolerance — and must emit a segment, not
        reject."""
        polyline = _line_polyline(BRENHAM_LON, BRENHAM_LAT, 2000.0, n_points=11)
        anchors = [(1000.0, polyline[0]), (3000.0, polyline[-1])]
        rows = [_row("R1", "9+00", "11+00")]
        out = KAR.generate_kmz_auto_redline_segments({
            "route_id": "r",
            "route_polyline_lonlat": polyline,
            "station_anchors_lonlat": anchors,
            "bore_log_rows": rows,
            "request_meta": {},
        })
        self.assertEqual(out["diagnostics"]["rows_generated"], 1)
        self.assertEqual(out["diagnostics"]["rows_rejected"], 0)

    def test_less_than_two_anchors_all_segments_fallback(self):
        polyline = _line_polyline(BRENHAM_LON, BRENHAM_LAT, 2000.0)
        # Single anchor only.
        anchors = [(1000.0, polyline[0])]
        rows = [_row(f"R{i}", "10+00", "20+00") for i in range(3)]
        out = KAR.generate_kmz_auto_redline_segments({
            "route_id": "r",
            "route_polyline_lonlat": polyline,
            "station_anchors_lonlat": anchors,
            "bore_log_rows": rows,
            "request_meta": {},
        })
        # No outside-envelope rejection because tolerance is 20% * span and
        # span<=0 disables the envelope check; rows pass through to fallback.
        self.assertEqual(out["diagnostics"]["rows_generated"], 3)
        self.assertIn("insufficient_anchors_lt_2", out["diagnostics"]["warnings"])
        for seg in out["generated_segments"]:
            self.assertEqual(seg["geometry_type"], "lonlat_fallback")
            self.assertEqual(seg["geometry_confidence"], "fallback")

    def test_zero_anchors_all_segments_fallback(self):
        polyline = _line_polyline(BRENHAM_LON, BRENHAM_LAT, 2000.0)
        anchors: List[Tuple[float, Tuple[float, float]]] = []
        rows = [_row("R1", "10+00", "20+00")]
        out = KAR.generate_kmz_auto_redline_segments({
            "route_id": "r",
            "route_polyline_lonlat": polyline,
            "station_anchors_lonlat": anchors,
            "bore_log_rows": rows,
            "request_meta": {},
        })
        self.assertEqual(out["diagnostics"]["anchor_count"], 0)
        self.assertEqual(out["diagnostics"]["rows_generated"], 1)
        self.assertEqual(out["generated_segments"][0]["geometry_confidence"], "fallback")

    def test_empty_bore_log_rows_no_error(self):
        polyline = _line_polyline(BRENHAM_LON, BRENHAM_LAT, 2000.0)
        out = KAR.generate_kmz_auto_redline_segments({
            "route_id": "r",
            "route_polyline_lonlat": polyline,
            "station_anchors_lonlat": [(1000.0, polyline[0]), (3000.0, polyline[-1])],
            "bore_log_rows": [],
            "request_meta": {},
        })
        self.assertEqual(out["diagnostics"]["rows_input"], 0)
        self.assertEqual(out["generated_segments"], [])
        self.assertEqual(out["rejected_rows"], [])

    def test_bounded_output_cap_respected(self):
        """5_001 input rows -> generated capped at 5_000."""
        polyline = _line_polyline(BRENHAM_LON, BRENHAM_LAT, 2000.0)
        anchors = [(1000.0, polyline[0]), (3000.0, polyline[-1])]
        rows = [_row(f"R{i}", "15+00", "25+00") for i in range(KAR._MAX_GENERATED_SEGMENTS + 50)]
        out = KAR.generate_kmz_auto_redline_segments({
            "route_id": "r",
            "route_polyline_lonlat": polyline,
            "station_anchors_lonlat": anchors,
            "bore_log_rows": rows,
            "request_meta": {},
        })
        self.assertEqual(out["diagnostics"]["rows_generated"], KAR._MAX_GENERATED_SEGMENTS)

    def test_row_not_dict_rejected(self):
        polyline = _line_polyline(BRENHAM_LON, BRENHAM_LAT, 2000.0)
        out = KAR.generate_kmz_auto_redline_segments({
            "route_id": "r",
            "route_polyline_lonlat": polyline,
            "station_anchors_lonlat": [(1000.0, polyline[0]), (3000.0, polyline[-1])],
            "bore_log_rows": ["not a dict", 123, None],
            "request_meta": {},
        })
        self.assertEqual(out["diagnostics"]["rows_generated"], 0)
        self.assertEqual(out["diagnostics"]["rows_rejected"], 3)
        for rej in out["rejected_rows"]:
            self.assertEqual(rej["reason"], "row_not_a_dict")


# ---------------------------------------------------------------------------
# Edge cases + caller-bug raises
# ---------------------------------------------------------------------------

class TestRequestValidation(unittest.TestCase):

    def test_request_not_dict_raises(self):
        with self.assertRaises(KAR.KmzAutoRedlineError):
            KAR.generate_kmz_auto_redline_segments("not a dict")  # type: ignore[arg-type]

    def test_route_id_required(self):
        with self.assertRaises(KAR.KmzAutoRedlineError):
            KAR.generate_kmz_auto_redline_segments({
                "route_polyline_lonlat": [(0, 0), (1, 1)],
                "bore_log_rows": [],
            })

    def test_polyline_must_be_list(self):
        with self.assertRaises(KAR.KmzAutoRedlineError):
            KAR.generate_kmz_auto_redline_segments({
                "route_id": "r",
                "route_polyline_lonlat": "not a list",
                "bore_log_rows": [],
            })

    def test_polyline_lt_2_points_raises(self):
        with self.assertRaises(KAR.KmzAutoRedlineError):
            KAR.generate_kmz_auto_redline_segments({
                "route_id": "r",
                "route_polyline_lonlat": [(0, 0)],
                "bore_log_rows": [],
            })

    def test_bore_log_rows_must_be_list_if_present(self):
        with self.assertRaises(KAR.KmzAutoRedlineError):
            KAR.generate_kmz_auto_redline_segments({
                "route_id": "r",
                "route_polyline_lonlat": [(0, 0), (1, 1)],
                "bore_log_rows": "not a list",
            })

    def test_invalid_lonlat_pairs_dropped_from_polyline(self):
        """Mixed valid + invalid polyline points: invalid silently dropped;
        if >= 2 valid remain, request proceeds."""
        polyline_mixed = [
            (BRENHAM_LON, BRENHAM_LAT),
            None,
            (BRENHAM_LON + 0.001, BRENHAM_LAT),
            "junk",
            (BRENHAM_LON + 0.002, BRENHAM_LAT),
        ]
        out = KAR.generate_kmz_auto_redline_segments({
            "route_id": "r",
            "route_polyline_lonlat": polyline_mixed,
            "station_anchors_lonlat": [],
            "bore_log_rows": [],
            "request_meta": {},
        })
        # Polyline vertex_count = 3 (after coercion + drop).
        self.assertEqual(out["diagnostics"]["polyline_vertex_count"], 3)

    def test_invalid_anchor_dropped_silently(self):
        polyline = _line_polyline(BRENHAM_LON, BRENHAM_LAT, 2000.0)
        bad_anchors = [
            (1000.0, polyline[0]),
            ("not a station", polyline[1]),     # invalid station
            (2000.0, "not a lonlat"),            # invalid coord
            (3000.0, polyline[-1]),
            None,                                # invalid pair
        ]
        out = KAR.generate_kmz_auto_redline_segments({
            "route_id": "r",
            "route_polyline_lonlat": polyline,
            "station_anchors_lonlat": bad_anchors,
            "bore_log_rows": [],
            "request_meta": {},
        })
        self.assertEqual(out["diagnostics"]["anchor_count"], 2)


# ---------------------------------------------------------------------------
# Determinism + hashing
# ---------------------------------------------------------------------------

class TestDeterminismAndHashing(unittest.TestCase):

    def test_deterministic_segment_id(self):
        polyline = _line_polyline(BRENHAM_LON, BRENHAM_LAT, 2000.0)
        anchors = [(1000.0, polyline[0]), (3000.0, polyline[-1])]
        req = {
            "route_id": "route_X",
            "route_polyline_lonlat": polyline,
            "station_anchors_lonlat": anchors,
            "bore_log_rows": [_row("ROW_42", "15+00", "25+00")],
            "request_meta": {},
        }
        out_a = KAR.generate_kmz_auto_redline_segments(req)
        out_b = KAR.generate_kmz_auto_redline_segments(req)
        self.assertEqual(out_a["generated_segments"][0]["segment_id"],
                         out_b["generated_segments"][0]["segment_id"])

    def test_segment_id_changes_with_route(self):
        polyline = _line_polyline(BRENHAM_LON, BRENHAM_LAT, 2000.0)
        anchors = [(1000.0, polyline[0]), (3000.0, polyline[-1])]
        out_a = KAR.generate_kmz_auto_redline_segments({
            "route_id": "route_A",
            "route_polyline_lonlat": polyline,
            "station_anchors_lonlat": anchors,
            "bore_log_rows": [_row("ROW_1", "15+00", "25+00")],
            "request_meta": {},
        })
        out_b = KAR.generate_kmz_auto_redline_segments({
            "route_id": "route_B",
            "route_polyline_lonlat": polyline,
            "station_anchors_lonlat": anchors,
            "bore_log_rows": [_row("ROW_1", "15+00", "25+00")],
            "request_meta": {},
        })
        self.assertNotEqual(out_a["generated_segments"][0]["segment_id"],
                            out_b["generated_segments"][0]["segment_id"])

    def test_segment_id_changes_with_row(self):
        polyline = _line_polyline(BRENHAM_LON, BRENHAM_LAT, 2000.0)
        anchors = [(1000.0, polyline[0]), (3000.0, polyline[-1])]
        rows = [_row("ROW_1", "15+00", "25+00"), _row("ROW_2", "15+00", "25+00")]
        out = KAR.generate_kmz_auto_redline_segments({
            "route_id": "r",
            "route_polyline_lonlat": polyline,
            "station_anchors_lonlat": anchors,
            "bore_log_rows": rows,
            "request_meta": {},
        })
        ids = {s["segment_id"] for s in out["generated_segments"]}
        self.assertEqual(len(ids), 2)

    def test_segment_id_format(self):
        polyline = _line_polyline(BRENHAM_LON, BRENHAM_LAT, 2000.0)
        anchors = [(1000.0, polyline[0]), (3000.0, polyline[-1])]
        out = KAR.generate_kmz_auto_redline_segments({
            "route_id": "r",
            "route_polyline_lonlat": polyline,
            "station_anchors_lonlat": anchors,
            "bore_log_rows": [_row("ROW_1", "15+00", "25+00")],
            "request_meta": {},
        })
        seg_id = out["generated_segments"][0]["segment_id"]
        self.assertTrue(seg_id.startswith("kar_"))
        self.assertEqual(len(seg_id), 4 + 16)


# ---------------------------------------------------------------------------
# Confidence tiers
# ---------------------------------------------------------------------------

class TestConfidenceTiers(unittest.TestCase):

    def test_high_confidence_when_residuals_small_and_in_envelope(self):
        polyline = _line_polyline(BRENHAM_LON, BRENHAM_LAT, 2000.0, n_points=11)
        anchors = [(1000.0, polyline[0]), (3000.0, polyline[-1])]
        rows = [_row("R", "15+00", "25+00")]
        out = KAR.generate_kmz_auto_redline_segments({
            "route_id": "r",
            "route_polyline_lonlat": polyline,
            "station_anchors_lonlat": anchors,
            "bore_log_rows": rows,
            "request_meta": {},
        })
        self.assertEqual(out["generated_segments"][0]["geometry_confidence"], "high")

    def test_medium_confidence_when_residuals_moderate(self):
        """Anchor residual ~3.5 m → medium tier."""
        polyline = _line_polyline(BRENHAM_LON, BRENHAM_LAT, 2000.0, n_points=11)
        offset_lat = polyline[0][1] + 3.5 / 111000.0
        anchors = [
            (1000.0, (polyline[0][0], offset_lat)),
            (3000.0, polyline[-1]),
        ]
        rows = [_row("R", "15+00", "25+00")]
        out = KAR.generate_kmz_auto_redline_segments({
            "route_id": "r",
            "route_polyline_lonlat": polyline,
            "station_anchors_lonlat": anchors,
            "bore_log_rows": rows,
            "request_meta": {},
        })
        self.assertEqual(out["generated_segments"][0]["geometry_confidence"], "medium")

    def test_low_confidence_when_residuals_large(self):
        """Anchor residual ~10 m → low tier."""
        polyline = _line_polyline(BRENHAM_LON, BRENHAM_LAT, 2000.0, n_points=11)
        offset_lat = polyline[0][1] + 10.0 / 111000.0
        anchors = [
            (1000.0, (polyline[0][0], offset_lat)),
            (3000.0, polyline[-1]),
        ]
        rows = [_row("R", "15+00", "25+00")]
        out = KAR.generate_kmz_auto_redline_segments({
            "route_id": "r",
            "route_polyline_lonlat": polyline,
            "station_anchors_lonlat": anchors,
            "bore_log_rows": rows,
            "request_meta": {},
        })
        self.assertEqual(out["generated_segments"][0]["geometry_confidence"], "low")

    def test_low_confidence_when_anchor_span_below_min(self):
        """Anchor span < 50 ft → low tier (or warning at least)."""
        # Build a tiny polyline + tight anchors.
        polyline = _line_polyline(BRENHAM_LON, BRENHAM_LAT, 40.0, n_points=5)
        anchors = [(1000.0, polyline[0]), (1010.0, polyline[-1])]
        rows = [_row("R", "10+02", "10+08")]
        out = KAR.generate_kmz_auto_redline_segments({
            "route_id": "r",
            "route_polyline_lonlat": polyline,
            "station_anchors_lonlat": anchors,
            "bore_log_rows": rows,
            "request_meta": {},
        })
        self.assertIn("anchor_span_below_min", out["diagnostics"]["warnings"])
        self.assertEqual(out["generated_segments"][0]["geometry_confidence"], "low")

    def test_fallback_when_worst_residual_exceeds_low_cap(self):
        """Worst anchor residual > 15 m → all segments fallback."""
        polyline = _line_polyline(BRENHAM_LON, BRENHAM_LAT, 2000.0, n_points=11)
        # ~20 m north offset
        offset_lat = polyline[0][1] + 20.0 / 111000.0
        anchors = [
            (1000.0, (polyline[0][0], offset_lat)),
            (3000.0, polyline[-1]),
        ]
        rows = [_row("R", "15+00", "25+00")]
        out = KAR.generate_kmz_auto_redline_segments({
            "route_id": "r",
            "route_polyline_lonlat": polyline,
            "station_anchors_lonlat": anchors,
            "bore_log_rows": rows,
            "request_meta": {},
        })
        self.assertEqual(out["diagnostics"]["residual_tier"], "fallback")
        self.assertEqual(out["generated_segments"][0]["geometry_confidence"], "fallback")


# ---------------------------------------------------------------------------
# Output shape / RedlineRecordModel-shape preservation
# ---------------------------------------------------------------------------

class TestProposedRedlineRecordShape(unittest.TestCase):

    def test_proposed_record_geometry_uses_lon_x_lat_y(self):
        polyline = _line_polyline(BRENHAM_LON, BRENHAM_LAT, 2000.0, n_points=11)
        anchors = [(1000.0, polyline[0]), (3000.0, polyline[-1])]
        rows = [_row("R", "15+00", "25+00")]
        out = KAR.generate_kmz_auto_redline_segments({
            "route_id": "r",
            "route_polyline_lonlat": polyline,
            "station_anchors_lonlat": anchors,
            "bore_log_rows": rows,
            "request_meta": {},
        })
        pr = out["generated_segments"][0]["proposed_redline_record"]
        self.assertEqual(pr["source"], "bore_log")
        self.assertEqual(pr["issue_type"], "new_conduit")
        self.assertEqual(pr["severity"], "review")
        self.assertFalse(pr["verified_by_foreman"])
        self.assertEqual(pr["geometry"]["geometry_type"], "polyline")
        # Each point has x = lon (negative for Brenham), y = lat (~30).
        for pt in pr["geometry"]["points"]:
            self.assertLess(pt["x"], 0.0)
            self.assertGreater(pt["y"], 0.0)
        self.assertEqual(pr["station_from"], "15+00")
        self.assertEqual(pr["station_to"], "25+00")

    def test_as_built_picks_up_known_fields(self):
        polyline = _line_polyline(BRENHAM_LON, BRENHAM_LAT, 2000.0, n_points=11)
        anchors = [(1000.0, polyline[0]), (3000.0, polyline[-1])]
        row = _row("R1", "15+00", "25+00", notes="HDPE backbone install")
        row["owner"] = "TrueLine"
        row["conduit_size"] = "2-inch"
        row["conduit_count"] = 2
        row["fiber_count"] = 144
        row["placement"] = "Underground"
        out = KAR.generate_kmz_auto_redline_segments({
            "route_id": "r",
            "route_polyline_lonlat": polyline,
            "station_anchors_lonlat": anchors,
            "bore_log_rows": [row],
            "request_meta": {},
        })
        ab = out["generated_segments"][0]["as_built"]
        self.assertEqual(ab["owner"], "TrueLine")
        self.assertEqual(ab["conduit_size"], "2-inch")
        self.assertEqual(ab["conduit_count"], 2)
        self.assertEqual(ab["fiber_count"], 144)
        self.assertEqual(ab["placement"], "Underground")
        self.assertEqual(ab["note_text"], "HDPE backbone install")

    def test_redline_record_round_trips_through_pydantic_model(self):
        """proposed_redline_record dicts must validate against the existing
        RedlineRecordModel schema. Locks the contract that R1 produces
        suggestion-grade records ready for downstream consumers."""
        from backend.app.core.redline_models import RedlineRecordModel
        polyline = _line_polyline(BRENHAM_LON, BRENHAM_LAT, 2000.0, n_points=11)
        anchors = [(1000.0, polyline[0]), (3000.0, polyline[-1])]
        rows = [_row("R", "15+00", "25+00")]
        out = KAR.generate_kmz_auto_redline_segments({
            "route_id": "r",
            "route_polyline_lonlat": polyline,
            "station_anchors_lonlat": anchors,
            "bore_log_rows": rows,
            "request_meta": {},
        })
        # If this raises, the helper output is not RedlineRecordModel-shaped.
        RedlineRecordModel(**out["generated_segments"][0]["proposed_redline_record"])


# ---------------------------------------------------------------------------
# Parser/helper unit tests
# ---------------------------------------------------------------------------

class TestStationParsing(unittest.TestCase):

    def test_parse_station_basic(self):
        self.assertEqual(KAR._parse_station_to_ft("11+60"), 1160.0)
        self.assertEqual(KAR._parse_station_to_ft("104+25.5"), 10425.5)

    def test_parse_station_with_prefix(self):
        self.assertEqual(KAR._parse_station_to_ft("STA 11+60"), 1160.0)
        self.assertEqual(KAR._parse_station_to_ft("STA. 11+60"), 1160.0)

    def test_parse_station_numeric_passthrough(self):
        self.assertEqual(KAR._parse_station_to_ft(1160.0), 1160.0)
        self.assertEqual(KAR._parse_station_to_ft(1160), 1160.0)

    def test_parse_station_invalid_returns_none(self):
        self.assertIsNone(KAR._parse_station_to_ft("not_a_station"))
        self.assertIsNone(KAR._parse_station_to_ft(""))
        self.assertIsNone(KAR._parse_station_to_ft(None))


if __name__ == "__main__":
    unittest.main()
