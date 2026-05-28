"""KMZ Hardening Stage R2a — kmz_anchor_builder.py unit tests.

Four test classes:

* Suite A — Anchor extraction math (projection + sort + cap + multi-anchor)
* Suite B — Rejection paths (no chainage, wrong classification, out-of-range,
  dedupe, missing coord, non-Point geometry)
* Suite D — Confidence rules (per-anchor + per-route grading)
* Edge cases — caller-bug raises + deterministic output

Pure helper tests. No backend.main import. No STATE. No I/O.
"""

from __future__ import annotations

import math
import unittest
from typing import Any, Dict, List, Tuple

from backend.app.core import kmz_anchor_builder as KAB


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

# Brenham-area horizontal route at constant latitude.
BRENHAM_LAT = 30.16
BRENHAM_LON = -96.39

_FT_PER_DEG_LON_BRENHAM = math.cos(math.radians(BRENHAM_LAT)) * KAB._FT_PER_DEGREE_LAT


def _lon_offset_for_ft(ft: float) -> float:
    return ft / _FT_PER_DEG_LON_BRENHAM


def _route_polyline_lonlat(length_ft: float = 2000.0, n_points: int = 5) -> List[Tuple[float, float]]:
    """East-pointing polyline at constant latitude, supplied in canonical
    (lon, lat) shape (matches R1's contract and the per-helper docstring)."""
    if n_points < 2:
        n_points = 2
    out: List[Tuple[float, float]] = []
    for i in range(n_points):
        f = i / (n_points - 1)
        out.append((BRENHAM_LON + _lon_offset_for_ft(length_ft * f), BRENHAM_LAT))
    return out


def _semantic_point_feature(
    feature_id: str,
    *,
    station_ft: float,
    lon_offset_ft: float = 0.0,
    lat_offset_m: float = 0.0,
    classification: str = "station_label",
    confidence: str = "high",
    chainage_source: str = "name",
) -> Dict[str, Any]:
    """Build a synthetic kmz_semantic feature mirroring the real shape.

    full_geometry.coord is stored as [lat, lon] (matches
    `_kmz_semantic_extract_full_geometry`). Helper's `_coerce_lonlat_pair`
    swaps to (lon, lat) on consumption.
    """
    lon = BRENHAM_LON + _lon_offset_for_ft(lon_offset_ft)
    lat = BRENHAM_LAT + (lat_offset_m / 111000.0)
    return {
        "feature_id": feature_id,
        "placemark_name": f"STA {int(station_ft // 100)}+{int(station_ft % 100):02d}",
        "description": "",
        "folder_path_str": "Stations",
        "geometry_type": "Point",
        "classification": classification,
        "confidence": confidence,
        "chainage_ft": station_ft,
        "chainage_source": chainage_source,
        "full_geometry": {"kind": "Point", "coord": [lat, lon]},
    }


def _semantic_line_feature(feature_id: str, chainage_ft: float = 1000.0) -> Dict[str, Any]:
    return {
        "feature_id": feature_id,
        "placemark_name": "Some line",
        "description": "",
        "folder_path_str": "Lines",
        "geometry_type": "LineString",
        "classification": "route_segment",
        "confidence": "medium",
        "chainage_ft": chainage_ft,
        "chainage_source": "name",
        "full_geometry": {"kind": "LineString", "coords": [[BRENHAM_LAT, BRENHAM_LON]]},
    }


# ---------------------------------------------------------------------------
# Suite A — Anchor extraction math
# ---------------------------------------------------------------------------

class TestSuiteAExtractionMath(unittest.TestCase):

    def test_single_high_confidence_anchor_on_route(self):
        polyline = _route_polyline_lonlat(2000.0, 11)
        features = [
            _semantic_point_feature("semantic_1", station_ft=1000.0, lon_offset_ft=0.0),
        ]
        out = KAB.generate_kmz_station_anchors({
            "route_id": "route_T",
            "route_polyline_lonlat": polyline,
            "kmz_semantic_features": features,
            "request_meta": {"session_id": "s1"},
        })
        self.assertEqual(out["schema_version"], "kmz-anchor-builder-1")
        self.assertEqual(out["route_id"], "route_T")
        self.assertEqual(out["diagnostics"]["anchor_count"], 1)
        self.assertEqual(out["diagnostics"]["candidate_count_post_proximity_filter"], 1)
        self.assertEqual(len(out["station_anchors_lonlat"]), 1)
        # Returned tuple shape: (station_ft, (lon, lat))
        station_ft, (lon, lat) = out["station_anchors_lonlat"][0]
        self.assertEqual(station_ft, 1000.0)
        self.assertLess(lon, 0.0)
        self.assertGreater(lat, 0.0)

    def test_multi_anchor_sorted_by_station_ft(self):
        polyline = _route_polyline_lonlat(2000.0, 11)
        features = [
            _semantic_point_feature("semantic_3", station_ft=2500.0, lon_offset_ft=1500.0),
            _semantic_point_feature("semantic_1", station_ft=1000.0, lon_offset_ft=0.0),
            _semantic_point_feature("semantic_2", station_ft=1800.0, lon_offset_ft=800.0),
        ]
        out = KAB.generate_kmz_station_anchors({
            "route_id": "r",
            "route_polyline_lonlat": polyline,
            "kmz_semantic_features": features,
            "request_meta": {},
        })
        self.assertEqual(out["diagnostics"]["anchor_count"], 3)
        # Verify ascending station_ft order
        stations = [a[0] for a in out["station_anchors_lonlat"]]
        self.assertEqual(stations, [1000.0, 1800.0, 2500.0])

    def test_projection_identity_anchor_on_polyline_vertex(self):
        """An anchor exactly at a polyline vertex projects with perp ≈ 0."""
        polyline = _route_polyline_lonlat(2000.0, 11)
        features = [
            _semantic_point_feature("semantic_1", station_ft=1000.0, lon_offset_ft=1000.0),
        ]
        out = KAB.generate_kmz_station_anchors({
            "route_id": "r",
            "route_polyline_lonlat": polyline,
            "kmz_semantic_features": features,
            "request_meta": {},
        })
        rec = out["anchor_records"][0]
        self.assertLess(rec["perp_distance_m"], 0.5)

    def test_proximity_filter_rejects_far_anchor(self):
        """Anchor 200 m north of route → exceeds _MAX_PROXIMITY_M (100 m)."""
        polyline = _route_polyline_lonlat(2000.0, 11)
        features = [
            _semantic_point_feature(
                "semantic_far",
                station_ft=1000.0,
                lat_offset_m=200.0,
            ),
        ]
        out = KAB.generate_kmz_station_anchors({
            "route_id": "r",
            "route_polyline_lonlat": polyline,
            "kmz_semantic_features": features,
            "request_meta": {},
        })
        self.assertEqual(out["diagnostics"]["anchor_count"], 0)
        self.assertEqual(out["diagnostics"]["candidate_count_pre_proximity_filter"], 1)
        self.assertEqual(out["diagnostics"]["candidate_count_post_proximity_filter"], 0)
        self.assertIn("perp_distance_exceeds_cap", out["diagnostics"]["rejection_reasons"])

    def test_proximity_filter_accepts_near_anchor(self):
        """Anchor 50 m north of route — under the 100 m cap; accepted."""
        polyline = _route_polyline_lonlat(2000.0, 11)
        features = [
            _semantic_point_feature(
                "semantic_near",
                station_ft=1000.0,
                lat_offset_m=50.0,
            ),
        ]
        out = KAB.generate_kmz_station_anchors({
            "route_id": "r",
            "route_polyline_lonlat": polyline,
            "kmz_semantic_features": features,
            "request_meta": {},
        })
        self.assertEqual(out["diagnostics"]["anchor_count"], 1)

    def test_anchor_cap_respected(self):
        """N+50 features → output capped at _MAX_ANCHORS_PER_ROUTE."""
        n_input = KAB._MAX_ANCHORS_PER_ROUTE + 50
        polyline = _route_polyline_lonlat(5000.0, 51)
        features = [
            _semantic_point_feature(
                f"semantic_{i:03d}",
                station_ft=1000.0 + i * 10.0,
                lon_offset_ft=(i * 10.0) % 5000.0,
            )
            for i in range(n_input)
        ]
        out = KAB.generate_kmz_station_anchors({
            "route_id": "r",
            "route_polyline_lonlat": polyline,
            "kmz_semantic_features": features,
            "request_meta": {},
        })
        self.assertEqual(out["diagnostics"]["anchor_count"], KAB._MAX_ANCHORS_PER_ROUTE)

    def test_polyline_total_length_in_diagnostics(self):
        polyline = _route_polyline_lonlat(2000.0, 11)
        out = KAB.generate_kmz_station_anchors({
            "route_id": "r",
            "route_polyline_lonlat": polyline,
            "kmz_semantic_features": [],
            "request_meta": {},
        })
        self.assertAlmostEqual(out["diagnostics"]["polyline_total_length_ft"], 2000.0, delta=10.0)
        self.assertEqual(out["diagnostics"]["polyline_vertex_count"], 11)

    def test_hemisphere_coercion_accepts_lat_lon_input(self):
        """Polyline supplied as [[lat, lon], ...] should be auto-swapped
        to (lon, lat) via hemisphere disambiguation."""
        # Build the same Brenham polyline but in [lat, lon] shape.
        polyline_canonical = _route_polyline_lonlat(2000.0, 5)
        polyline_latlon = [[lat, lon] for (lon, lat) in polyline_canonical]
        features = [
            _semantic_point_feature("semantic_1", station_ft=1000.0, lon_offset_ft=1000.0),
        ]
        out_can = KAB.generate_kmz_station_anchors({
            "route_id": "r",
            "route_polyline_lonlat": polyline_canonical,
            "kmz_semantic_features": features,
            "request_meta": {},
        })
        out_lat = KAB.generate_kmz_station_anchors({
            "route_id": "r",
            "route_polyline_lonlat": polyline_latlon,
            "kmz_semantic_features": features,
            "request_meta": {},
        })
        # Both shapes should produce identical anchor projections.
        self.assertEqual(out_can["diagnostics"]["polyline_total_length_ft"],
                         out_lat["diagnostics"]["polyline_total_length_ft"])
        self.assertEqual(out_can["station_anchors_lonlat"], out_lat["station_anchors_lonlat"])


# ---------------------------------------------------------------------------
# Suite B — Rejection paths
# ---------------------------------------------------------------------------

class TestSuiteBRejectionPaths(unittest.TestCase):

    def test_empty_kmz_semantic_features_returns_no_anchors_with_warning(self):
        polyline = _route_polyline_lonlat(2000.0)
        out = KAB.generate_kmz_station_anchors({
            "route_id": "r",
            "route_polyline_lonlat": polyline,
            "kmz_semantic_features": [],
            "request_meta": {},
        })
        self.assertEqual(out["diagnostics"]["anchor_count"], 0)
        self.assertEqual(out["station_anchors_lonlat"], [])
        self.assertIn("kmz_semantic_unavailable", out["diagnostics"]["warnings"])
        self.assertEqual(out["diagnostics"]["route_confidence"], "abstain")

    def test_non_point_geometry_rejected(self):
        polyline = _route_polyline_lonlat(2000.0)
        features = [
            _semantic_line_feature("semantic_line_1"),
            {
                "feature_id": "semantic_poly_1",
                "geometry_type": "Polygon",
                "chainage_ft": 1000.0,
                "classification": "boundary_polygon",
                "confidence": "low",
            },
        ]
        out = KAB.generate_kmz_station_anchors({
            "route_id": "r",
            "route_polyline_lonlat": polyline,
            "kmz_semantic_features": features,
            "request_meta": {},
        })
        self.assertEqual(out["diagnostics"]["anchor_count"], 0)
        self.assertGreaterEqual(out["diagnostics"]["rejection_reasons"].get("non_point_geometry", 0), 2)

    def test_no_chainage_rejected(self):
        polyline = _route_polyline_lonlat(2000.0)
        feature = _semantic_point_feature("semantic_1", station_ft=1000.0)
        feature["chainage_ft"] = None
        out = KAB.generate_kmz_station_anchors({
            "route_id": "r",
            "route_polyline_lonlat": polyline,
            "kmz_semantic_features": [feature],
            "request_meta": {},
        })
        self.assertEqual(out["diagnostics"]["anchor_count"], 0)
        self.assertEqual(out["diagnostics"]["rejection_reasons"].get("no_chainage"), 1)

    def test_non_numeric_chainage_rejected(self):
        polyline = _route_polyline_lonlat(2000.0)
        feature = _semantic_point_feature("semantic_1", station_ft=1000.0)
        feature["chainage_ft"] = "not a number"
        out = KAB.generate_kmz_station_anchors({
            "route_id": "r",
            "route_polyline_lonlat": polyline,
            "kmz_semantic_features": [feature],
            "request_meta": {},
        })
        self.assertEqual(out["diagnostics"]["anchor_count"], 0)
        self.assertEqual(out["diagnostics"]["rejection_reasons"].get("chainage_not_numeric"), 1)

    def test_classification_not_anchor_kind_rejected(self):
        polyline = _route_polyline_lonlat(2000.0)
        feature = _semantic_point_feature(
            "semantic_annot",
            station_ft=1000.0,
            classification="annotation",
        )
        out = KAB.generate_kmz_station_anchors({
            "route_id": "r",
            "route_polyline_lonlat": polyline,
            "kmz_semantic_features": [feature],
            "request_meta": {},
        })
        self.assertEqual(out["diagnostics"]["anchor_count"], 0)
        self.assertEqual(out["diagnostics"]["rejection_reasons"].get("classification_not_anchor_kind"), 1)

    def test_chainage_out_of_range_rejected(self):
        polyline = _route_polyline_lonlat(2000.0)
        f_neg = _semantic_point_feature("semantic_neg", station_ft=-50.0)
        f_huge = _semantic_point_feature("semantic_huge", station_ft=2_000_000.0)
        out = KAB.generate_kmz_station_anchors({
            "route_id": "r",
            "route_polyline_lonlat": polyline,
            "kmz_semantic_features": [f_neg, f_huge],
            "request_meta": {},
        })
        self.assertEqual(out["diagnostics"]["anchor_count"], 0)
        self.assertEqual(out["diagnostics"]["rejection_reasons"].get("chainage_out_of_range"), 2)

    def test_duplicate_station_ft_dedupes_keeping_smaller_perp(self):
        polyline = _route_polyline_lonlat(2000.0, 11)
        # Two anchors at station_ft=1000; one on-route, one 50 m off.
        f_on = _semantic_point_feature(
            "semantic_on_route", station_ft=1000.0, lon_offset_ft=1000.0
        )
        f_off = _semantic_point_feature(
            "semantic_off_route", station_ft=1000.0, lon_offset_ft=1000.0, lat_offset_m=50.0
        )
        out = KAB.generate_kmz_station_anchors({
            "route_id": "r",
            "route_polyline_lonlat": polyline,
            "kmz_semantic_features": [f_off, f_on],
            "request_meta": {},
        })
        self.assertEqual(out["diagnostics"]["anchor_count"], 1)
        # Kept anchor must be the on-route one (smaller perp_distance).
        self.assertEqual(out["anchor_records"][0]["source_feature_id"], "semantic_on_route")
        # Loser must show up in rejected_features.
        rejection_ids = {r["source_feature_id"] for r in out["rejected_features"]}
        self.assertIn("semantic_off_route", rejection_ids)
        self.assertEqual(out["diagnostics"]["rejection_reasons"].get("duplicate_station_ft"), 1)

    def test_missing_point_coord_rejected(self):
        polyline = _route_polyline_lonlat(2000.0)
        feature = {
            "feature_id": "semantic_missing_coord",
            "geometry_type": "Point",
            "classification": "station_label",
            "confidence": "high",
            "chainage_ft": 1000.0,
            "chainage_source": "name",
            "full_geometry": None,   # no coords
        }
        out = KAB.generate_kmz_station_anchors({
            "route_id": "r",
            "route_polyline_lonlat": polyline,
            "kmz_semantic_features": [feature],
            "request_meta": {},
        })
        self.assertEqual(out["diagnostics"]["anchor_count"], 0)
        self.assertEqual(out["diagnostics"]["rejection_reasons"].get("missing_point_coord"), 1)

    def test_feature_not_a_dict_rejected(self):
        polyline = _route_polyline_lonlat(2000.0)
        out = KAB.generate_kmz_station_anchors({
            "route_id": "r",
            "route_polyline_lonlat": polyline,
            "kmz_semantic_features": ["not a dict", 42, None],
            "request_meta": {},
        })
        self.assertEqual(out["diagnostics"]["rejection_reasons"].get("feature_not_a_dict"), 3)


# ---------------------------------------------------------------------------
# Suite D — Confidence rules
# ---------------------------------------------------------------------------

class TestSuiteDConfidenceRules(unittest.TestCase):

    def test_high_confidence_per_anchor(self):
        polyline = _route_polyline_lonlat(2000.0, 11)
        # On-route, station_label, name source, semantic high → high anchor
        feature = _semantic_point_feature(
            "semantic_hi",
            station_ft=1000.0,
            lon_offset_ft=1000.0,
            classification="station_label",
            confidence="high",
            chainage_source="name",
        )
        out = KAB.generate_kmz_station_anchors({
            "route_id": "r",
            "route_polyline_lonlat": polyline,
            "kmz_semantic_features": [feature],
            "request_meta": {},
        })
        self.assertEqual(out["anchor_records"][0]["anchor_confidence"], "high")

    def test_medium_confidence_per_anchor_on_structure_marker(self):
        polyline = _route_polyline_lonlat(2000.0, 11)
        # structure_marker is anchor-eligible but never reaches "high" tier.
        feature = _semantic_point_feature(
            "semantic_str",
            station_ft=1000.0,
            lon_offset_ft=1000.0,
            classification="structure_marker",
            confidence="medium",
            chainage_source="name",
        )
        out = KAB.generate_kmz_station_anchors({
            "route_id": "r",
            "route_polyline_lonlat": polyline,
            "kmz_semantic_features": [feature],
            "request_meta": {},
        })
        self.assertEqual(out["anchor_records"][0]["anchor_confidence"], "medium")

    def test_low_confidence_when_chainage_from_description(self):
        polyline = _route_polyline_lonlat(2000.0, 11)
        feature = _semantic_point_feature(
            "semantic_lo",
            station_ft=1000.0,
            lon_offset_ft=1000.0,
            classification="station_label",
            confidence="high",
            chainage_source="description",  # not "name"
        )
        out = KAB.generate_kmz_station_anchors({
            "route_id": "r",
            "route_polyline_lonlat": polyline,
            "kmz_semantic_features": [feature],
            "request_meta": {},
        })
        # Loses HIGH tier (chainage_source not "name"); medium per §4.5 since
        # classification is anchor-kind + perp_m ≤ 25 m.
        self.assertEqual(out["anchor_records"][0]["anchor_confidence"], "medium")

    def test_low_confidence_when_perp_large(self):
        polyline = _route_polyline_lonlat(2000.0, 11)
        # 40 m off-route exceeds the medium cap (25 m) but is under 100 m.
        feature = _semantic_point_feature(
            "semantic_lo2",
            station_ft=1000.0,
            lon_offset_ft=1000.0,
            lat_offset_m=40.0,
            classification="station_label",
            confidence="high",
        )
        out = KAB.generate_kmz_station_anchors({
            "route_id": "r",
            "route_polyline_lonlat": polyline,
            "kmz_semantic_features": [feature],
            "request_meta": {},
        })
        self.assertEqual(out["anchor_records"][0]["anchor_confidence"], "low")

    def test_route_confidence_high_with_two_high_anchors(self):
        polyline = _route_polyline_lonlat(2000.0, 11)
        # Anchors at 1000 + 3000 → span 2000 ft (well over 200 ft cap).
        # Wait — polyline is 2000 ft total, so put anchors at station_ft=1000 + 1500 covering distance 0 → 1000 ft → ON-route + on-route.
        feature_a = _semantic_point_feature("a", station_ft=1000.0, lon_offset_ft=0.0)
        feature_b = _semantic_point_feature("b", station_ft=2500.0, lon_offset_ft=1500.0)
        feature_c = _semantic_point_feature("c", station_ft=2000.0, lon_offset_ft=1000.0)
        out = KAB.generate_kmz_station_anchors({
            "route_id": "r",
            "route_polyline_lonlat": polyline,
            "kmz_semantic_features": [feature_a, feature_b, feature_c],
            "request_meta": {},
        })
        self.assertEqual(out["diagnostics"]["route_confidence"], "high")
        self.assertEqual(out["diagnostics"]["confidence_tally"]["high"], 3)

    def test_route_confidence_medium_when_only_two_medium_anchors(self):
        polyline = _route_polyline_lonlat(2000.0, 11)
        feature_a = _semantic_point_feature(
            "a", station_ft=1000.0, lon_offset_ft=0.0,
            classification="structure_marker", confidence="medium",
        )
        feature_b = _semantic_point_feature(
            "b", station_ft=1500.0, lon_offset_ft=500.0,
            classification="structure_marker", confidence="medium",
        )
        out = KAB.generate_kmz_station_anchors({
            "route_id": "r",
            "route_polyline_lonlat": polyline,
            "kmz_semantic_features": [feature_a, feature_b],
            "request_meta": {},
        })
        self.assertEqual(out["diagnostics"]["route_confidence"], "medium")

    def test_route_confidence_abstain_when_zero_anchors(self):
        polyline = _route_polyline_lonlat(2000.0, 11)
        out = KAB.generate_kmz_station_anchors({
            "route_id": "r",
            "route_polyline_lonlat": polyline,
            "kmz_semantic_features": [],
            "request_meta": {},
        })
        self.assertEqual(out["diagnostics"]["route_confidence"], "abstain")

    def test_route_confidence_low_when_only_one_anchor(self):
        polyline = _route_polyline_lonlat(2000.0, 11)
        feature = _semantic_point_feature("only", station_ft=1000.0, lon_offset_ft=1000.0)
        out = KAB.generate_kmz_station_anchors({
            "route_id": "r",
            "route_polyline_lonlat": polyline,
            "kmz_semantic_features": [feature],
            "request_meta": {},
        })
        self.assertEqual(out["diagnostics"]["route_confidence"], "low")
        self.assertIn("only_one_anchor", out["diagnostics"]["warnings"])

    def test_route_confidence_low_when_anchor_span_below_min(self):
        polyline = _route_polyline_lonlat(2000.0, 11)
        feature_a = _semantic_point_feature("a", station_ft=1000.0, lon_offset_ft=500.0)
        feature_b = _semantic_point_feature("b", station_ft=1020.0, lon_offset_ft=520.0)
        out = KAB.generate_kmz_station_anchors({
            "route_id": "r",
            "route_polyline_lonlat": polyline,
            "kmz_semantic_features": [feature_a, feature_b],
            "request_meta": {},
        })
        # span = 20 ft, below the 50 ft medium threshold → low.
        self.assertEqual(out["diagnostics"]["route_confidence"], "low")
        self.assertIn("anchor_span_below_min", out["diagnostics"]["warnings"])


# ---------------------------------------------------------------------------
# Edge cases — caller-bug raises + deterministic output
# ---------------------------------------------------------------------------

class TestRequestValidation(unittest.TestCase):

    def test_request_not_dict_raises(self):
        with self.assertRaises(KAB.KmzAnchorBuilderError):
            KAB.generate_kmz_station_anchors("not a dict")  # type: ignore[arg-type]

    def test_route_id_required(self):
        with self.assertRaises(KAB.KmzAnchorBuilderError):
            KAB.generate_kmz_station_anchors({
                "route_polyline_lonlat": [(0, 0), (1, 1)],
                "kmz_semantic_features": [],
            })

    def test_polyline_must_be_list(self):
        with self.assertRaises(KAB.KmzAnchorBuilderError):
            KAB.generate_kmz_station_anchors({
                "route_id": "r",
                "route_polyline_lonlat": "not a list",
                "kmz_semantic_features": [],
            })

    def test_polyline_lt_2_points_raises(self):
        with self.assertRaises(KAB.KmzAnchorBuilderError):
            KAB.generate_kmz_station_anchors({
                "route_id": "r",
                "route_polyline_lonlat": [(0, 0)],
                "kmz_semantic_features": [],
            })

    def test_semantic_features_must_be_list_if_present(self):
        with self.assertRaises(KAB.KmzAnchorBuilderError):
            KAB.generate_kmz_station_anchors({
                "route_id": "r",
                "route_polyline_lonlat": [(0, 0), (1, 1)],
                "kmz_semantic_features": "not a list",
            })

    def test_semantic_features_absent_treated_as_empty(self):
        out = KAB.generate_kmz_station_anchors({
            "route_id": "r",
            "route_polyline_lonlat": _route_polyline_lonlat(2000.0),
            "request_meta": {},
        })
        self.assertEqual(out["diagnostics"]["anchor_count"], 0)


class TestDeterminism(unittest.TestCase):

    def test_byte_identical_output_on_repeat_call(self):
        polyline = _route_polyline_lonlat(2000.0, 11)
        features = [
            _semantic_point_feature("a", station_ft=1000.0, lon_offset_ft=0.0),
            _semantic_point_feature("b", station_ft=1500.0, lon_offset_ft=500.0),
            _semantic_point_feature("c", station_ft=2000.0, lon_offset_ft=1000.0),
        ]
        req = {
            "route_id": "route_X",
            "route_polyline_lonlat": polyline,
            "kmz_semantic_features": features,
            "request_meta": {"session_id": "s"},
        }
        out_a = KAB.generate_kmz_station_anchors(req)
        out_b = KAB.generate_kmz_station_anchors(req)
        self.assertEqual(out_a["station_anchors_lonlat"], out_b["station_anchors_lonlat"])
        self.assertEqual(out_a["anchor_records"], out_b["anchor_records"])
        self.assertEqual(out_a["diagnostics"], out_b["diagnostics"])

    def test_anchor_record_order_independent_of_input_order(self):
        polyline = _route_polyline_lonlat(2000.0, 11)
        a = _semantic_point_feature("z_last_id", station_ft=1000.0, lon_offset_ft=0.0)
        b = _semantic_point_feature("a_first_id", station_ft=2000.0, lon_offset_ft=1000.0)
        out_ab = KAB.generate_kmz_station_anchors({
            "route_id": "r",
            "route_polyline_lonlat": polyline,
            "kmz_semantic_features": [a, b],
            "request_meta": {},
        })
        out_ba = KAB.generate_kmz_station_anchors({
            "route_id": "r",
            "route_polyline_lonlat": polyline,
            "kmz_semantic_features": [b, a],
            "request_meta": {},
        })
        # Both inputs should sort to the same station-ft-ascending result.
        self.assertEqual(out_ab["station_anchors_lonlat"], out_ba["station_anchors_lonlat"])


# ---------------------------------------------------------------------------
# R1 integration shape check (R2a output feeds directly into R1 contract)
# ---------------------------------------------------------------------------

class TestR1IntegrationShape(unittest.TestCase):

    def test_station_anchors_lonlat_round_trips_through_r1_request_shape(self):
        """R2a's `station_anchors_lonlat` output must be a valid R1 input.
        Locks the contract that R1 + R2a interoperate at the type-signature
        level. Does NOT invoke R1's emission seam — that's R2c, NOT R2a."""
        from backend.app.core import kmz_auto_redline as KAR

        polyline = _route_polyline_lonlat(2000.0, 11)
        features = [
            _semantic_point_feature("a", station_ft=1000.0, lon_offset_ft=0.0),
            _semantic_point_feature("b", station_ft=3000.0, lon_offset_ft=2000.0),
        ]
        r2a_out = KAB.generate_kmz_station_anchors({
            "route_id": "route_T",
            "route_polyline_lonlat": polyline,
            "kmz_semantic_features": features,
            "request_meta": {},
        })

        # Feed R2a output directly into R1 request shape — proves the
        # cross-module contract holds. R2c will be the production seam;
        # R2a tests only verify the type-level interop.
        r1_request = {
            "route_id": "route_T",
            "route_polyline_lonlat": polyline,
            "station_anchors_lonlat": r2a_out["station_anchors_lonlat"],
            "bore_log_rows": [{"row_id": "R1", "start_label": "15+00", "end_label": "25+00"}],
            "request_meta": {},
        }
        r1_out = KAR.generate_kmz_auto_redline_segments(r1_request)
        # With 2 R2a anchors at 1000 + 3000 ft and a row at 15+00→25+00,
        # R1 should produce a non-fallback segment.
        self.assertEqual(r1_out["diagnostics"]["anchor_count"], 2)
        seg = r1_out["generated_segments"][0]
        self.assertEqual(seg["geometry_type"], "lonlat_polyline")
        self.assertIn(seg["geometry_confidence"], {"high", "medium"})


if __name__ == "__main__":
    unittest.main()
