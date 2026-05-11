"""Phase 1S — Bore-log redline endpoint validator lock-down suite.

17 tests for ``_build_redline_endpoint_validation`` and
``get_redline_endpoint_validation``, added in Phase 1S.

ISOLATION STRATEGY
------------------
Tests call ``_build_redline_endpoint_validation`` directly with synthetic
in-memory dicts.  The HTTP endpoint is tested by monkeypatching ``main.STATE``.
The real STATE is restored in ``tearDown``.  No real KMZ I/O.  No network calls.

IF A TEST FAILS after a legitimate Phase 1S change:
  1. Confirm the change is intentional.
  2. Update the relevant assertion or fixture below.
  3. Add a comment explaining why.
  DO NOT "fix to green" without understanding the failure.
"""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List

_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import main  # noqa: E402

# ---------------------------------------------------------------------------
# Schema lock constants
# ---------------------------------------------------------------------------
EXPECTED_TOP_KEYS: frozenset = frozenset(
    {
        "schema_version",
        "tolerance_ft",
        "near_band_ft",
        "endpoints",
        "summary",
        "stability_note",
    }
)

EXPECTED_ENDPOINT_KEYS: frozenset = frozenset(
    {
        "segment_id",
        "route_id",
        "endpoint",
        "coordinate",
        "nearest_anchor_id",
        "nearest_anchor_name",
        "distance_ft",
        "classification",
    }
)

EXPECTED_SUMMARY_KEYS: frozenset = frozenset(
    {
        "total_endpoints",
        "anchored_count",
        "near_count",
        "orphan_count",
        "no_anchors_in_kmz_count",
        "anchored_pct",
        "by_route",
        "flagged_segments",
    }
)

VALID_CLASSIFICATIONS = frozenset(
    {"anchored", "near", "orphan", "no_anchors_in_kmz"}
)

_SCHEMA_VERSION = "redline-endpoint-validation-1"
_TOLERANCE_FT = 3.0
_NEAR_BAND_FT = 10.0
_STABILITY_NOTE_PREFIX = "redline-endpoint-validation-1 classifies each redline"

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

# Brenham-area base coordinates.
_BASE_LAT: float = 30.15
_BASE_LON: float = -96.39

# Approximate degrees per foot at ~30° latitude.
_DEG_PER_FT: float = 1.0 / 364_000.0


def _anchor(
    feature_id: str = "point_1",
    lat: float = _BASE_LAT,
    lon: float = _BASE_LON,
    name: str = "HH-1",
) -> Dict[str, Any]:
    return {
        "feature_id": feature_id,
        "name": name,
        "lat": lat,
        "lon": lon,
        "role": "other",
    }


def _reference(*anchors: Dict[str, Any]) -> Dict[str, Any]:
    return {"point_features": list(anchors)}


def _route(
    route_id: str = "route_1",
    start_lat: float = _BASE_LAT,
    start_lon: float = _BASE_LON,
    end_lat: float = _BASE_LAT + 0.001,
    end_lon: float = _BASE_LON + 0.001,
) -> Dict[str, Any]:
    return {
        "route_id": route_id,
        "route_name": "Test Cable",
        "coords": [[start_lat, start_lon], [end_lat, end_lon]],
        "length_ft": 1000.0,
    }


def _segment(
    segment_id: str = "seg_1",
    matched_route_id: str = "route_1",
) -> Dict[str, Any]:
    return {
        "segment_id": segment_id,
        "matched_route_id": matched_route_id,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBuildRedlineEndpointValidationEmpty(unittest.TestCase):
    """Tests for empty / missing input conditions."""

    def test_01_none_inputs_return_valid_schema(self):
        result = main._build_redline_endpoint_validation(None, None, None)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["schema_version"], _SCHEMA_VERSION)
        self.assertEqual(result["endpoints"], [])
        self.assertEqual(result["summary"]["total_endpoints"], 0)
        self.assertIsNone(result["summary"]["anchored_pct"])

    def test_02_empty_list_inputs_return_valid_schema(self):
        result = main._build_redline_endpoint_validation([], {}, [])
        self.assertIsInstance(result, dict)
        self.assertEqual(result["endpoints"], [])
        self.assertEqual(result["summary"]["total_endpoints"], 0)

    def test_03_no_anchors_classifies_as_no_anchors_in_kmz(self):
        """Segments exist but reference has no point_features → no_anchors_in_kmz."""
        segs = [_segment("seg_a", "route_1")]
        catalog = [_route("route_1")]
        ref = {"point_features": []}
        result = main._build_redline_endpoint_validation(segs, ref, catalog)
        for ep in result["endpoints"]:
            self.assertEqual(ep["classification"], "no_anchors_in_kmz")
            self.assertIsNone(ep["nearest_anchor_id"])
            self.assertIsNone(ep["distance_ft"])
        self.assertEqual(result["summary"]["anchored_count"], 0)
        self.assertEqual(result["summary"]["no_anchors_in_kmz_count"], len(result["endpoints"]))


class TestEndpointClassification(unittest.TestCase):
    """Classification boundary tests."""

    def _run_single(
        self,
        offset_ft: float,
        anchor_lat: float = _BASE_LAT,
        anchor_lon: float = _BASE_LON,
    ) -> Dict[str, Any]:
        """Build a minimal result for one segment whose START is offset_ft
        from the anchor along latitude."""
        ep_lat = anchor_lat + offset_ft * _DEG_PER_FT
        ep_lon = anchor_lon
        segs = [_segment("seg_1", "route_1")]
        catalog = [_route("route_1", start_lat=ep_lat, start_lon=ep_lon)]
        ref = _reference(_anchor("anc_1", anchor_lat, anchor_lon))
        return main._build_redline_endpoint_validation(segs, ref, catalog)

    def test_04_exactly_within_tolerance_is_anchored(self):
        """Endpoint at 0.99 × tolerance → anchored."""
        r = self._run_single(0.99 * _TOLERANCE_FT)
        eps = [e for e in r["endpoints"] if e["endpoint"] == "start"]
        self.assertEqual(len(eps), 1)
        self.assertEqual(eps[0]["classification"], "anchored")

    def test_05_just_beyond_tolerance_is_near(self):
        """Endpoint at 1.5 × tolerance (inside near band) → near."""
        r = self._run_single(1.5 * _TOLERANCE_FT)
        eps = [e for e in r["endpoints"] if e["endpoint"] == "start"]
        self.assertEqual(len(eps), 1)
        self.assertEqual(eps[0]["classification"], "near")

    def test_06_exactly_at_near_band_is_near(self):
        """Endpoint at 0.99 × near band → near (not orphan)."""
        r = self._run_single(0.99 * _NEAR_BAND_FT)
        eps = [e for e in r["endpoints"] if e["endpoint"] == "start"]
        self.assertEqual(len(eps), 1)
        self.assertEqual(eps[0]["classification"], "near")

    def test_07_beyond_near_band_is_orphan(self):
        """Endpoint at 1.5 × near band → orphan."""
        r = self._run_single(1.5 * _NEAR_BAND_FT)
        eps = [e for e in r["endpoints"] if e["endpoint"] == "start"]
        self.assertEqual(len(eps), 1)
        self.assertEqual(eps[0]["classification"], "orphan")


class TestSummaryCorrectness(unittest.TestCase):
    """Summary counts, anchored_pct, flagged_segments."""

    def _build(self) -> Dict[str, Any]:
        """2 routes × 2 endpoints each = 4 endpoints total.
        route_1: anchored/anchored  → not flagged
        route_2: anchored/orphan    → flagged
        """
        anchor_a = _anchor("a_1", _BASE_LAT, _BASE_LON, "A-1")
        anchor_b = _anchor("a_2", _BASE_LAT + 0.001, _BASE_LON + 0.001, "A-2")

        # route_1 start and end both land on anchors
        r1_start_lat = _BASE_LAT
        r1_start_lon = _BASE_LON
        r1_end_lat = _BASE_LAT + 0.001
        r1_end_lon = _BASE_LON + 0.001

        # route_2 start lands on anchor_a, end is far away (orphan)
        r2_start_lat = _BASE_LAT
        r2_start_lon = _BASE_LON
        r2_end_lat = _BASE_LAT + 0.5   # ~182 ft away → orphan
        r2_end_lon = _BASE_LON

        segs = [_segment("seg_1", "route_1"), _segment("seg_2", "route_2")]
        catalog = [
            _route("route_1", r1_start_lat, r1_start_lon, r1_end_lat, r1_end_lon),
            _route("route_2", r2_start_lat, r2_start_lon, r2_end_lat, r2_end_lon),
        ]
        ref = _reference(anchor_a, anchor_b)
        return main._build_redline_endpoint_validation(segs, ref, catalog)

    def test_08_total_endpoints_correct(self):
        r = self._build()
        self.assertEqual(r["summary"]["total_endpoints"], 4)

    def test_09_anchored_count_and_pct_correct(self):
        r = self._build()
        s = r["summary"]
        # 3 anchored (route_1 start+end, route_2 start), 1 orphan
        self.assertEqual(s["anchored_count"], 3)
        self.assertEqual(s["orphan_count"], 1)
        self.assertAlmostEqual(s["anchored_pct"], 0.75, places=3)

    def test_10_flagged_segments_correct(self):
        r = self._build()
        flagged = r["summary"]["flagged_segments"]
        self.assertIn("seg_2", flagged)
        self.assertNotIn("seg_1", flagged)

    def test_11_by_route_correct(self):
        r = self._build()
        by_route = r["summary"]["by_route"]
        self.assertIn("route_1", by_route)
        self.assertIn("route_2", by_route)
        r1 = by_route["route_1"]
        r2 = by_route["route_2"]
        self.assertEqual(r1["anchored"], 2)
        self.assertEqual(r1["orphan"], 0)
        self.assertEqual(r2["anchored"], 1)
        self.assertEqual(r2["orphan"], 1)


class TestSchemaLock(unittest.TestCase):
    """Exact schema key assertions."""

    def setUp(self):
        self.result = main._build_redline_endpoint_validation(
            [_segment("seg_1", "route_1")],
            _reference(_anchor()),
            [_route()],
        )

    def test_12_top_level_keys(self):
        self.assertEqual(frozenset(self.result.keys()), EXPECTED_TOP_KEYS)

    def test_13_endpoint_record_keys(self):
        for ep in self.result["endpoints"]:
            self.assertEqual(frozenset(ep.keys()), EXPECTED_ENDPOINT_KEYS)

    def test_14_summary_keys(self):
        self.assertEqual(
            frozenset(self.result["summary"].keys()), EXPECTED_SUMMARY_KEYS
        )

    def test_15_schema_version_and_tolerances(self):
        self.assertEqual(self.result["schema_version"], _SCHEMA_VERSION)
        self.assertEqual(self.result["tolerance_ft"], _TOLERANCE_FT)
        self.assertEqual(self.result["near_band_ft"], _NEAR_BAND_FT)

    def test_16_stability_note_present(self):
        self.assertTrue(
            self.result["stability_note"].startswith(_STABILITY_NOTE_PREFIX)
        )

    def test_17_valid_classifications(self):
        for ep in self.result["endpoints"]:
            self.assertIn(ep["classification"], VALID_CLASSIFICATIONS)


class TestMalformedInputs(unittest.TestCase):
    """Malformed/garbage inputs must never raise."""

    def test_18_garbage_segments_never_raise(self):
        try:
            result = main._build_redline_endpoint_validation(
                "not_a_list",  # type: ignore[arg-type]
                None,
                None,
            )
            self.assertIsInstance(result, dict)
        except Exception as exc:  # pragma: no cover
            self.fail(f"Raised unexpectedly: {exc}")

    def test_19_missing_coords_silently_skipped(self):
        segs = [{"segment_id": "seg_x", "matched_route_id": "route_x"}]
        catalog = [{"route_id": "route_x", "coords": []}]
        ref = _reference(_anchor())
        result = main._build_redline_endpoint_validation(segs, ref, catalog)
        self.assertEqual(result["summary"]["total_endpoints"], 0)

    def test_20_anchor_with_missing_lat_lon_skipped(self):
        segs = [_segment()]
        catalog = [_route()]
        bad_ref = {
            "point_features": [
                {"feature_id": "bad_1"},  # no lat/lon
                _anchor("good_1"),
            ]
        }
        result = main._build_redline_endpoint_validation(segs, bad_ref, catalog)
        for ep in result["endpoints"]:
            self.assertIn(
                ep["classification"], VALID_CLASSIFICATIONS
            )


class TestDeterminism(unittest.TestCase):
    """Same inputs always produce identical output."""

    def test_21_deterministic_output(self):
        segs = [_segment("seg_1", "route_1"), _segment("seg_2", "route_2")]
        catalog = [_route("route_1"), _route("route_2")]
        ref = _reference(
            _anchor("a_1", _BASE_LAT, _BASE_LON),
            _anchor("a_2", _BASE_LAT + 0.001, _BASE_LON),
        )
        r1 = main._build_redline_endpoint_validation(segs, ref, catalog)
        r2 = main._build_redline_endpoint_validation(segs, ref, catalog)
        self.assertEqual(r1["endpoints"], r2["endpoints"])
        self.assertEqual(r1["summary"], r2["summary"])


class TestASTRegressionOperationalIsolation(unittest.TestCase):
    """AST-level check: operational helpers must not reference the
    endpoint validation structure.

    Forbidden callers:
    - _rebuild_matches
    - _score_bore_groups
    - _activate_route          (or similar route activation helpers)
    - upload_design (main upload handler should only *write* to STATE key; the
      write call in _rebuild_field_data_outputs is permitted)

    We enforce that the string 'redline_endpoint_validation' does NOT appear
    inside these function bodies.
    """

    _SRC: str = Path(_BACKEND_DIR / "main.py").read_text(encoding="utf-8")

    FORBIDDEN_CALLERS = [
        "_rebuild_matches",
        "_score_bore_groups",
    ]

    def _get_func_source(self, tree: ast.AST, name: str) -> str:
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == name:
                    lines = self._SRC.splitlines()
                    start = node.lineno - 1
                    end = node.end_lineno or start
                    return "\n".join(lines[start:end])
        return ""

    def test_22_operational_helpers_do_not_reference_endpoint_validator(self):
        tree = ast.parse(self._SRC)
        for caller in self.FORBIDDEN_CALLERS:
            body = self._get_func_source(tree, caller)
            self.assertNotIn(
                "redline_endpoint_validation",
                body,
                msg=(
                    f"Operational helper '{caller}' must not reference "
                    "'redline_endpoint_validation'. "
                    "See backend/TOPOLOGY_SIDECAR_USAGE_POLICY.md."
                ),
            )


class TestBrenhamSmoke(unittest.TestCase):
    """Smoke assertions that run only when Brenham data is loaded in STATE.

    These tests are skipped in empty-state CI runs.  They validate that when
    the real Brenham KMZ + redline are present:
      - anchored_pct >= 0.95
      - flagged_segments includes expected low-confidence routes
    """

    def setUp(self):
        self._segs = main.STATE.get("redline_segments")
        self._ref = main.STATE.get("kmz_reference")
        self._catalog = main.STATE.get("route_catalog")

    @unittest.skipUnless(
        main.STATE.get("redline_segments") and main.STATE.get("kmz_reference"),
        "Brenham data not loaded — skipping smoke tests.",
    )
    def test_23_brenham_anchored_pct_at_least_95(self):
        result = main._build_redline_endpoint_validation(
            self._segs, self._ref, self._catalog
        )
        s = result["summary"]
        self.assertIsNotNone(s["anchored_pct"])
        self.assertGreaterEqual(
            s["anchored_pct"],
            0.95,
            msg=(
                f"Expected anchored_pct >= 0.95, got {s['anchored_pct']:.4f}. "
                "Review flagged segments for geometry drift."
            ),
        )

    @unittest.skipUnless(
        main.STATE.get("redline_segments") and main.STATE.get("kmz_reference"),
        "Brenham data not loaded — skipping smoke tests.",
    )
    def test_24_brenham_known_flagged_routes_present(self):
        """Routes identified during Phase 1S design as expected low-confidence."""
        result = main._build_redline_endpoint_validation(
            self._segs, self._ref, self._catalog
        )
        flagged = set(result["summary"]["flagged_segments"])
        expected_flagged = {"route_35", "route_459", "route_476"}
        missing = expected_flagged - flagged
        self.assertEqual(
            missing,
            set(),
            msg=(
                f"Expected routes {expected_flagged} to appear in flagged_segments. "
                f"Missing: {missing}. "
                "If geometry was intentionally corrected, update this list."
            ),
        )


if __name__ == "__main__":
    unittest.main()
