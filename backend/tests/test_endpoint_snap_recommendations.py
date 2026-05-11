"""Phase 1T — Deterministic Endpoint Snap Recommendations lock-down suite.

20 tests for ``_build_endpoint_snap_recommendations`` and
``get_endpoint_snap_recommendations``, added in Phase 1T.

ISOLATION STRATEGY
------------------
Tests call ``_build_endpoint_snap_recommendations`` directly with synthetic
in-memory dicts built from Phase 1S validator output fixtures.
The HTTP endpoint is tested by monkeypatching ``main.STATE``.
No real KMZ I/O.  No network calls.

IF A TEST FAILS after a legitimate Phase 1T change:
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
        "recommendations",
        "summary",
        "stability_note",
    }
)

EXPECTED_REC_KEYS: frozenset = frozenset(
    {
        "segment_id",
        "route_id",
        "endpoint",
        "current_coordinate",
        "current_distance_ft",
        "candidate_anchor_id",
        "candidate_anchor_name",
        "candidate_coordinate",
        "snap_delta_ft",
        "classification",
    }
)

EXPECTED_SUMMARY_KEYS: frozenset = frozenset(
    {
        "total_recommendations",
        "near_recommendations",
        "orphan_recommendations",
    }
)

_SCHEMA_VERSION = "endpoint-snap-recommendation-1"
_TOLERANCE_FT = 3.0
_NEAR_BAND_FT = 10.0
_STABILITY_NOTE_PREFIX = "endpoint-snap-recommendation-1 lists candidate"

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------
_BASE_LAT: float = 30.15
_BASE_LON: float = -96.39


def _anchor(
    feature_id: str = "anc_1",
    lat: float = _BASE_LAT,
    lon: float = _BASE_LON,
    name: str = "HH-1",
) -> Dict[str, Any]:
    return {"feature_id": feature_id, "name": name, "lat": lat, "lon": lon}


def _reference(*anchors: Dict[str, Any]) -> Dict[str, Any]:
    return {"point_features": list(anchors)}


def _ep_record(
    segment_id: str = "seg_1",
    route_id: str = "route_1",
    endpoint: str = "start",
    classification: str = "near",
    distance_ft: float = 5.0,
    nearest_anchor_id: str = "anc_1",
    lon: float = _BASE_LON + 0.0001,
    lat: float = _BASE_LAT,
) -> Dict[str, Any]:
    return {
        "segment_id": segment_id,
        "route_id": route_id,
        "endpoint": endpoint,
        "coordinate": [lon, lat],
        "nearest_anchor_id": nearest_anchor_id,
        "nearest_anchor_name": "HH-1",
        "distance_ft": distance_ft,
        "classification": classification,
    }


def _validation(endpoints: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Minimal validation result wrapping a list of endpoint records."""
    return {
        "schema_version": "redline-endpoint-validation-1",
        "tolerance_ft": _TOLERANCE_FT,
        "near_band_ft": _NEAR_BAND_FT,
        "endpoints": endpoints,
        "summary": {},
        "stability_note": "test",
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBuildSnapRecommendationsEmpty(unittest.TestCase):
    """Empty / missing input conditions."""

    def test_01_none_inputs_return_valid_schema(self):
        result = main._build_endpoint_snap_recommendations(None, None)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["schema_version"], _SCHEMA_VERSION)
        self.assertEqual(result["recommendations"], [])
        self.assertEqual(result["summary"]["total_recommendations"], 0)

    def test_02_empty_endpoints_list_returns_empty(self):
        result = main._build_endpoint_snap_recommendations(
            _validation([]), _reference(_anchor())
        )
        self.assertEqual(result["recommendations"], [])
        self.assertEqual(result["summary"]["total_recommendations"], 0)

    def test_03_anchored_endpoints_produce_zero_recommendations(self):
        eps = [_ep_record(classification="anchored", distance_ft=1.0)]
        result = main._build_endpoint_snap_recommendations(
            _validation(eps), _reference(_anchor())
        )
        self.assertEqual(result["recommendations"], [])
        self.assertEqual(result["summary"]["total_recommendations"], 0)

    def test_04_no_anchors_in_kmz_endpoints_produce_zero_recommendations(self):
        eps = [_ep_record(classification="no_anchors_in_kmz", nearest_anchor_id="")]
        result = main._build_endpoint_snap_recommendations(
            _validation(eps), _reference(_anchor())
        )
        self.assertEqual(result["recommendations"], [])


class TestSnapClassification(unittest.TestCase):
    """near and orphan endpoints each produce exactly one recommendation."""

    def test_05_near_endpoint_produces_one_recommendation(self):
        eps = [_ep_record(classification="near", distance_ft=5.0)]
        result = main._build_endpoint_snap_recommendations(
            _validation(eps), _reference(_anchor())
        )
        self.assertEqual(len(result["recommendations"]), 1)
        self.assertEqual(result["recommendations"][0]["classification"], "near")
        self.assertEqual(result["summary"]["near_recommendations"], 1)
        self.assertEqual(result["summary"]["orphan_recommendations"], 0)

    def test_06_orphan_endpoint_produces_one_recommendation(self):
        eps = [_ep_record(classification="orphan", distance_ft=25.0)]
        result = main._build_endpoint_snap_recommendations(
            _validation(eps), _reference(_anchor())
        )
        self.assertEqual(len(result["recommendations"]), 1)
        self.assertEqual(result["recommendations"][0]["classification"], "orphan")
        self.assertEqual(result["summary"]["orphan_recommendations"], 1)
        self.assertEqual(result["summary"]["near_recommendations"], 0)

    def test_07_mixed_classifications_only_near_orphan_included(self):
        eps = [
            _ep_record("seg_a", classification="anchored", distance_ft=1.0),
            _ep_record("seg_b", classification="near", distance_ft=5.5),
            _ep_record("seg_c", classification="orphan", distance_ft=20.0),
            _ep_record("seg_d", classification="no_anchors_in_kmz", nearest_anchor_id=""),
        ]
        # Remove nearest_anchor_id from no_anchors record
        eps[3]["nearest_anchor_id"] = None
        result = main._build_endpoint_snap_recommendations(
            _validation(eps), _reference(_anchor())
        )
        self.assertEqual(len(result["recommendations"]), 2)
        seg_ids = {r["segment_id"] for r in result["recommendations"]}
        self.assertIn("seg_b", seg_ids)
        self.assertIn("seg_c", seg_ids)
        self.assertNotIn("seg_a", seg_ids)
        self.assertNotIn("seg_d", seg_ids)


class TestCandidateCoordinateExactness(unittest.TestCase):
    """candidate_coordinate must exactly equal the anchor lat/lon."""

    def test_08_candidate_coordinate_exact_equality(self):
        anc = _anchor("anc_1", lat=30.1500001, lon=-96.3999999)
        eps = [_ep_record(classification="near", nearest_anchor_id="anc_1")]
        result = main._build_endpoint_snap_recommendations(
            _validation(eps), _reference(anc)
        )
        rec = result["recommendations"][0]
        # candidate_coordinate is [lon, lat]
        self.assertAlmostEqual(rec["candidate_coordinate"][0], anc["lon"], places=9)
        self.assertAlmostEqual(rec["candidate_coordinate"][1], anc["lat"], places=9)

    def test_09_snap_delta_ft_equals_current_distance_ft(self):
        eps = [_ep_record(classification="near", distance_ft=7.123)]
        result = main._build_endpoint_snap_recommendations(
            _validation(eps), _reference(_anchor())
        )
        rec = result["recommendations"][0]
        self.assertEqual(rec["snap_delta_ft"], rec["current_distance_ft"])
        self.assertAlmostEqual(rec["snap_delta_ft"], 7.123, places=3)

    def test_10_candidate_anchor_id_matches_validator_nearest(self):
        anc_a = _anchor("anc_a", lat=_BASE_LAT, lon=_BASE_LON, name="HH-A")
        anc_b = _anchor("anc_b", lat=_BASE_LAT + 0.01, lon=_BASE_LON, name="HH-B")
        eps = [_ep_record(classification="near", nearest_anchor_id="anc_b")]
        result = main._build_endpoint_snap_recommendations(
            _validation(eps), _reference(anc_a, anc_b)
        )
        rec = result["recommendations"][0]
        self.assertEqual(rec["candidate_anchor_id"], "anc_b")
        self.assertEqual(rec["candidate_anchor_name"], "HH-B")


class TestSchemaLock(unittest.TestCase):
    """Exact schema key assertions."""

    def setUp(self):
        eps = [_ep_record(classification="near")]
        self.result = main._build_endpoint_snap_recommendations(
            _validation(eps), _reference(_anchor())
        )

    def test_11_top_level_keys(self):
        self.assertEqual(frozenset(self.result.keys()), EXPECTED_TOP_KEYS)

    def test_12_recommendation_record_keys(self):
        for rec in self.result["recommendations"]:
            self.assertEqual(frozenset(rec.keys()), EXPECTED_REC_KEYS)

    def test_13_summary_keys(self):
        self.assertEqual(
            frozenset(self.result["summary"].keys()), EXPECTED_SUMMARY_KEYS
        )

    def test_14_schema_version_and_tolerances(self):
        self.assertEqual(self.result["schema_version"], _SCHEMA_VERSION)
        self.assertEqual(self.result["tolerance_ft"], _TOLERANCE_FT)
        self.assertEqual(self.result["near_band_ft"], _NEAR_BAND_FT)

    def test_15_stability_note_present(self):
        self.assertTrue(
            self.result["stability_note"].startswith(_STABILITY_NOTE_PREFIX)
        )


class TestMalformedInputs(unittest.TestCase):
    """Malformed / garbage inputs must never raise."""

    def test_16_garbage_validation_never_raise(self):
        try:
            result = main._build_endpoint_snap_recommendations(
                "not_a_dict",  # type: ignore[arg-type]
                _reference(_anchor()),
            )
            self.assertIsInstance(result, dict)
        except Exception as exc:
            self.fail(f"Raised unexpectedly: {exc}")

    def test_17_endpoint_missing_anchor_id_skipped_gracefully(self):
        eps = [
            {
                "segment_id": "seg_1",
                "route_id": "route_1",
                "endpoint": "start",
                "coordinate": [_BASE_LON, _BASE_LAT],
                "nearest_anchor_id": None,  # no anchor
                "nearest_anchor_name": None,
                "distance_ft": 5.0,
                "classification": "near",
            }
        ]
        result = main._build_endpoint_snap_recommendations(
            _validation(eps), _reference(_anchor())
        )
        # No anchor_id → no recommendation emitted
        self.assertEqual(result["summary"]["total_recommendations"], 0)

    def test_18_unresolvable_anchor_id_skipped_gracefully(self):
        eps = [_ep_record(classification="near", nearest_anchor_id="ghost_anc")]
        result = main._build_endpoint_snap_recommendations(
            _validation(eps), _reference(_anchor("real_anc"))
        )
        # Anchor not in reference → no recommendation
        self.assertEqual(result["summary"]["total_recommendations"], 0)


class TestDeterminism(unittest.TestCase):
    """Same inputs always produce identical output."""

    def test_19_deterministic_output(self):
        eps = [
            _ep_record("seg_1", classification="near", distance_ft=5.0),
            _ep_record("seg_2", classification="orphan", distance_ft=20.0),
        ]
        ref = _reference(_anchor())
        r1 = main._build_endpoint_snap_recommendations(_validation(eps), ref)
        r2 = main._build_endpoint_snap_recommendations(_validation(eps), ref)
        self.assertEqual(r1["recommendations"], r2["recommendations"])
        self.assertEqual(r1["summary"], r2["summary"])


class TestASTRegressionOperationalIsolation(unittest.TestCase):
    """AST-level check: operational helpers must not reference the snap
    recommendations structure.

    Forbidden callers (same set as Phase 1S):
    - _rebuild_matches
    - _score_bore_groups
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

    def test_20_operational_helpers_do_not_reference_snap_recommendations(self):
        tree = ast.parse(self._SRC)
        for caller in self.FORBIDDEN_CALLERS:
            body = self._get_func_source(tree, caller)
            for symbol in ("endpoint_snap_recommendations", "_build_endpoint_snap_recommendations"):
                self.assertNotIn(
                    symbol,
                    body,
                    msg=(
                        f"Operational helper '{caller}' must not reference "
                        f"'{symbol}'. "
                        "See backend/TOPOLOGY_SIDECAR_USAGE_POLICY.md."
                    ),
                )


class TestBrenhamSmoke(unittest.TestCase):
    """Smoke assertions that run only when Brenham data is loaded in STATE.

    Skipped in empty-state CI runs.  These validate that when the real
    Brenham endpoint_validation and kmz_reference are present:
      - exactly 19 recommendations (16 near + 3 orphan)
      - route_35, route_459, route_476 each produce 2 recommendations
      - all orphan routes produce orphan recommendations
      - all candidate_anchor_ids resolve to real anchors
    """

    def _get_snap(self) -> Dict[str, Any]:
        val = main.STATE.get("redline_endpoint_validation")
        ref = main.STATE.get("kmz_reference")
        return main._build_endpoint_snap_recommendations(val, ref)

    @unittest.skipUnless(
        main.STATE.get("redline_endpoint_validation") and main.STATE.get("kmz_reference"),
        "Brenham data not loaded — skipping smoke tests.",
    )
    def test_21_brenham_exactly_19_recommendations(self):
        result = self._get_snap()
        total = result["summary"]["total_recommendations"]
        self.assertEqual(
            total,
            19,
            msg=(
                f"Expected exactly 19 recommendations on Brenham data, got {total}. "
                "Check whether the endpoint validator output changed."
            ),
        )

    @unittest.skipUnless(
        main.STATE.get("redline_endpoint_validation") and main.STATE.get("kmz_reference"),
        "Brenham data not loaded — skipping smoke tests.",
    )
    def test_22_brenham_known_routes_produce_2_recommendations_each(self):
        result = self._get_snap()
        expected_2 = ["route_35", "route_459", "route_476"]
        for route_id in expected_2:
            recs = [r for r in result["recommendations"] if r["route_id"] == route_id]
            self.assertEqual(
                len(recs),
                2,
                msg=f"{route_id} should produce 2 recommendations, got {len(recs)}.",
            )

    @unittest.skipUnless(
        main.STATE.get("redline_endpoint_validation") and main.STATE.get("kmz_reference"),
        "Brenham data not loaded — skipping smoke tests.",
    )
    def test_23_brenham_all_candidate_anchor_ids_resolve(self):
        ref = main.STATE.get("kmz_reference") or {}
        pt_feats = ref.get("point_features") or []
        real_ids = {str(p["feature_id"]) for p in pt_feats if p.get("feature_id")}
        result = self._get_snap()
        for rec in result["recommendations"]:
            self.assertIn(
                rec["candidate_anchor_id"],
                real_ids,
                msg=(
                    f"candidate_anchor_id '{rec['candidate_anchor_id']}' not found "
                    "in kmz_reference point_features."
                ),
            )

    @unittest.skipUnless(
        main.STATE.get("redline_endpoint_validation") and main.STATE.get("kmz_reference"),
        "Brenham data not loaded — skipping smoke tests.",
    )
    def test_24_brenham_near_count_16_orphan_count_3(self):
        result = self._get_snap()
        s = result["summary"]
        self.assertEqual(s["near_recommendations"], 16,
                         msg=f"Expected 16 near recommendations, got {s['near_recommendations']}")
        self.assertEqual(s["orphan_recommendations"], 3,
                         msg=f"Expected 3 orphan recommendations, got {s['orphan_recommendations']}")


if __name__ == "__main__":
    unittest.main()
