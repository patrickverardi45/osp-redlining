"""Phase 1M — KMZ engineering fidelity audit lock-down suite.

14 tests for ``_compute_kmz_fidelity_audit`` and ``get_kmz_fidelity_audit``,
added in Phase 1M.

ISOLATION STRATEGY
------------------
Tests call ``_compute_kmz_fidelity_audit`` directly with synthetic in-memory
dicts.  ``get_kmz_fidelity_audit`` is tested by monkeypatching ``main.STATE``
with controlled values.  No real KMZ file I/O.  The real STATE is restored
in ``tearDown``.

IF A TEST FAILS after a legitimate Phase 1M change:
  1. Confirm the change is intentional.
  2. Update the relevant constant or assertion below.
  3. Add a comment explaining why.
  DO NOT "fix to green" without understanding the failure.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional

_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import main  # noqa: E402

# ---------------------------------------------------------------------------
# Exact top-level key set — schema lock.
# ---------------------------------------------------------------------------
EXPECTED_TOP_KEYS: frozenset = frozenset(
    {
        "schema_version",
        "generated_at",
        "window",
        "style_fidelity",
        "folder_fidelity",
        "extended_data_fidelity",
        "geometry_fidelity",
        "render_simplification",
        "stability_note",
    }
)

_STABILITY_NOTE_PREFIX = "kmz-fidelity-audit-1 describes engineering fidelity gaps"


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _sem_feature(
    style_url: str = "#myStyle",
    folder_path: Optional[List[str]] = None,
    extended_data: Optional[Dict[str, str]] = None,
    geometry_type: str = "LineString",
    style_resolved: Optional[Dict[str, Any]] = None,
    multigeometry_children: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    return {
        "feature_id": "semantic_1",
        "placemark_id": None,
        "placemark_name": "Test Placemark",
        "description": "desc",
        "description_raw": "<b>desc</b>",
        "folder_path": folder_path if folder_path is not None else ["Root", "Sub"],
        "folder_path_str": " / ".join(folder_path or ["Root", "Sub"]),
        "geometry_type": geometry_type,
        "style_url": style_url,
        "extended_data": extended_data or {},
        "coords_hint": None,
        "classification": "route_segment",
        "confidence": "low",
        "classification_reason": "test",
        "source_filename": "test.kmz",
        "chainage_ft": None,
        "chainage_source": None,
        "sequence_number": None,
        "sequence_kind": None,
        "full_geometry": None,
        "multigeometry_children": multigeometry_children if multigeometry_children is not None else [],
        "style_resolved": style_resolved,
        "lifecycle": None,
        "classification_debug": {},
    }


def _sem_ingest(features: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build a minimal semantic ingest dict from a list of features."""
    return {
        "features": features,
        "index": {
            "by_classification": {},
            "by_geometry_type": {},
            "style_url_count": {},
            "extended_data_keys": {},
            "anchor_catalog": [],
        },
    }


def _ref_ingest(
    line_count: int = 2,
    polygon_count: int = 0,
    point_count: int = 0,
) -> Dict[str, Any]:
    """Build a minimal reference ingest dict."""
    lines = [
        {
            "feature_id": f"line_{i}",
            "name": f"Feature {i}",
            "folder_path": "Root / Sub",
            "role": "other",
            "coords": [[39.0, -98.0], [39.1, -98.1]],
            "stroke": "#10b981",
            "stroke_width": 3,
            "length_ft": 500.0,
        }
        for i in range(line_count)
    ]
    polys = [
        {
            "feature_id": f"poly_{i}",
            "name": f"Poly {i}",
            "folder_path": "Root",
            "role": "other",
            "coords": [[39.0, -98.0], [39.1, -98.0], [39.1, -98.1], [39.0, -98.0]],
            "fill": "#22c55e",
            "fill_opacity": 0.16,
            "stroke": "#22c55e",
            "stroke_width": 2,
        }
        for i in range(polygon_count)
    ]
    points = [
        {
            "feature_id": f"point_{i}",
            "name": f"Point {i}",
            "folder_path": "Root",
            "role": "other",
            "lat": 39.0,
            "lon": -98.0,
        }
        for i in range(point_count)
    ]
    return {
        "line_features": lines,
        "polygon_features": polys,
        "point_features": points,
    }


def _call_helper(
    semantic: Optional[Dict[str, Any]],
    reference: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    return main._compute_kmz_fidelity_audit(semantic, reference)


def _endpoint_audit() -> Dict[str, Any]:
    response = main.get_kmz_fidelity_audit()
    return json.loads(response.body)


# ---------------------------------------------------------------------------
# Test suite
# ---------------------------------------------------------------------------

class TestKmzFidelityAudit(unittest.TestCase):
    """Lock-down suite for Phase 1M KMZ engineering fidelity audit."""

    def setUp(self) -> None:
        self._orig_kmz_semantic = main.STATE.get("kmz_semantic")
        self._orig_kmz_reference = main.STATE.get("kmz_reference")

    def tearDown(self) -> None:
        main.STATE["kmz_semantic"] = self._orig_kmz_semantic
        main.STATE["kmz_reference"] = self._orig_kmz_reference

    # ------------------------------------------------------------------
    # 01 — both inputs None → valid empty skeleton
    # ------------------------------------------------------------------

    def test_01_both_none_returns_skeleton(self) -> None:
        """Both inputs None → valid skeleton, has_semantic_ingest=False."""
        result = _call_helper(None, None)
        self.assertEqual(result["schema_version"], "kmz-fidelity-audit-1")
        self.assertFalse(result["window"]["has_semantic_ingest"])
        self.assertFalse(result["window"]["has_reference_ingest"])
        self.assertEqual(result["window"]["semantic_feature_count"], 0)

    # ------------------------------------------------------------------
    # 02 — endpoint top-level schema lock
    # ------------------------------------------------------------------

    def test_02_endpoint_schema_lock(self) -> None:
        """Endpoint must return exactly the documented top-level keys."""
        main.STATE["kmz_semantic"] = None
        main.STATE["kmz_reference"] = None
        result = _endpoint_audit()
        self.assertEqual(frozenset(result.keys()), EXPECTED_TOP_KEYS)

    # ------------------------------------------------------------------
    # 03 — style fidelity: style_urls counted correctly
    # ------------------------------------------------------------------

    def test_03_style_url_count(self) -> None:
        """unique_style_urls_in_semantic counts distinct non-empty style_urls."""
        features = [
            _sem_feature(style_url="#styleA"),
            _sem_feature(style_url="#styleA"),  # duplicate
            _sem_feature(style_url="#styleB"),
            _sem_feature(style_url=""),           # empty — not counted
        ]
        result = _call_helper(_sem_ingest(features), _ref_ingest())
        self.assertEqual(result["style_fidelity"]["unique_style_urls_in_semantic"], 2)

    # ------------------------------------------------------------------
    # 04 — style fidelity: preservation rate is 0.0 when style_urls exist
    # ------------------------------------------------------------------

    def test_04_style_preservation_rate_zero(self) -> None:
        """style_url_preservation_rate is 0.0 when style_urls exist in semantic."""
        features = [_sem_feature(style_url="#myStyle")]
        result = _call_helper(_sem_ingest(features), _ref_ingest())
        rate = result["style_fidelity"]["style_url_preservation_rate"]
        self.assertIsNotNone(rate)
        self.assertAlmostEqual(rate, 0.0, places=4)

    # ------------------------------------------------------------------
    # 05 — style fidelity: preservation rate is None when no style_urls
    # ------------------------------------------------------------------

    def test_05_style_preservation_rate_null_when_none(self) -> None:
        """style_url_preservation_rate is None when no style_urls in semantic."""
        features = [_sem_feature(style_url="")]
        result = _call_helper(_sem_ingest(features), _ref_ingest())
        self.assertIsNone(result["style_fidelity"]["style_url_preservation_rate"])

    # ------------------------------------------------------------------
    # 06 — style fidelity: icon_href counted from style_resolved
    # ------------------------------------------------------------------

    def test_06_icon_href_count(self) -> None:
        """features_with_icon_href counts features where style_resolved has icon_href."""
        features = [
            _sem_feature(style_resolved={"icon_href": "files/splice.png"}),
            _sem_feature(style_resolved={"line_color": "#ff0000"}),  # no icon
            _sem_feature(style_resolved=None),
        ]
        result = _call_helper(_sem_ingest(features), _ref_ingest())
        self.assertEqual(result["style_fidelity"]["features_with_icon_href"], 1)

    # ------------------------------------------------------------------
    # 07 — folder fidelity: max and avg depth correct
    # ------------------------------------------------------------------

    def test_07_folder_depth_metrics(self) -> None:
        """max/avg folder depth computed from folder_path arrays."""
        features = [
            _sem_feature(folder_path=["Root"]),              # depth 1
            _sem_feature(folder_path=["Root", "Sub"]),       # depth 2
            _sem_feature(folder_path=["Root", "Sub", "L3"]), # depth 3
        ]
        result = _call_helper(_sem_ingest(features), _ref_ingest())
        ff = result["folder_fidelity"]
        self.assertEqual(ff["max_folder_depth"], 3)
        # avg = (1+2+3)/3 = 2.0
        self.assertAlmostEqual(ff["avg_folder_depth"], 2.0, places=2)
        self.assertEqual(ff["features_with_multi_level_path"], 2)
        self.assertEqual(ff["features_with_single_level_path"], 1)

    # ------------------------------------------------------------------
    # 08 — folder fidelity: hierarchy_preservation_rate is 0.0
    # ------------------------------------------------------------------

    def test_08_hierarchy_preservation_rate_zero(self) -> None:
        """hierarchy_preservation_rate is 0.0 when multi-level paths exist."""
        features = [_sem_feature(folder_path=["Root", "Sub", "L3"])]
        result = _call_helper(_sem_ingest(features), _ref_ingest())
        rate = result["folder_fidelity"]["hierarchy_preservation_rate"]
        self.assertIsNotNone(rate)
        self.assertAlmostEqual(rate, 0.0, places=4)

    # ------------------------------------------------------------------
    # 09 — ExtendedData fidelity: key counts and top keys
    # ------------------------------------------------------------------

    def test_09_extended_data_counts(self) -> None:
        """unique_key_count and total_value_count reflect all features."""
        features = [
            _sem_feature(extended_data={"cable_count": "24", "fiber_type": "SM"}),
            _sem_feature(extended_data={"cable_count": "48"}),
        ]
        result = _call_helper(_sem_ingest(features), _ref_ingest())
        ed = result["extended_data_fidelity"]
        self.assertEqual(ed["unique_key_count"], 2)
        self.assertEqual(ed["total_value_count"], 3)
        keys_in_top = [k["key"] for k in ed["top_keys"]]
        self.assertIn("cable_count", keys_in_top)

    # ------------------------------------------------------------------
    # 10 — ExtendedData fidelity: preservation_rate is 0.0 when keys exist
    # ------------------------------------------------------------------

    def test_10_extended_data_preservation_rate_zero(self) -> None:
        """preservation_rate is 0.0 when ExtendedData keys exist in semantic."""
        features = [_sem_feature(extended_data={"key1": "val1"})]
        result = _call_helper(_sem_ingest(features), _ref_ingest())
        rate = result["extended_data_fidelity"]["preservation_rate"]
        self.assertIsNotNone(rate)
        self.assertAlmostEqual(rate, 0.0, places=4)

    # ------------------------------------------------------------------
    # 11 — MultiGeometry counts
    # ------------------------------------------------------------------

    def test_11_multigeometry_counts(self) -> None:
        """multigeometry_placemark_count and child count computed correctly."""
        features = [
            _sem_feature(
                geometry_type="MultiGeometry",
                multigeometry_children=[{"type": "LineString"}, {"type": "Point"}],
            ),
            _sem_feature(
                geometry_type="MultiGeometry",
                multigeometry_children=[{"type": "Polygon"}],
            ),
            _sem_feature(geometry_type="LineString"),
        ]
        result = _call_helper(_sem_ingest(features), _ref_ingest())
        gf = result["geometry_fidelity"]
        self.assertEqual(gf["multigeometry_placemark_count"], 2)
        self.assertEqual(gf["multigeometry_child_count"], 3)

    # ------------------------------------------------------------------
    # 12 — render simplification: dropped fields non-empty
    # ------------------------------------------------------------------

    def test_12_dropped_fields_non_empty(self) -> None:
        """fields_in_semantic_not_in_reference is non-empty and includes known fields."""
        result = _call_helper(_sem_ingest([_sem_feature()]), _ref_ingest())
        rs = result["render_simplification"]
        self.assertGreater(rs["dropped_field_count"], 0)
        dropped = set(rs["fields_in_semantic_not_in_reference"])
        # These semantic fields are definitively absent from reference line features
        for expected_drop in ["style_url", "extended_data", "description_raw", "style_resolved"]:
            self.assertIn(expected_drop, dropped, f"Expected {expected_drop!r} in dropped fields")

    # ------------------------------------------------------------------
    # 13 — malformed inputs are tolerated; helper never raises
    # ------------------------------------------------------------------

    def test_13_malformed_inputs_never_raise(self) -> None:
        """Helper must not raise on malformed semantic or reference inputs."""
        bad_cases: list = [
            (None, None),
            ({}, {}),
            ({"features": None}, {"line_features": None}),
            ({"features": [None, "not a dict", 42]}, _ref_ingest()),
            (_sem_ingest([_sem_feature(folder_path=None)]), _ref_ingest()),  # type: ignore[arg-type]
        ]
        for sem, ref in bad_cases:
            try:
                result = _call_helper(sem, ref)
                self.assertIn("schema_version", result)
            except Exception as exc:
                self.fail(f"Helper raised on malformed input: {type(exc).__name__}: {exc}")

    # ------------------------------------------------------------------
    # 14 — stability_note presence and prefix lock
    # ------------------------------------------------------------------

    def test_14_stability_note_prefix(self) -> None:
        """stability_note must be present and start with expected prefix."""
        result = _call_helper(None, None)
        note = result.get("stability_note", "")
        self.assertTrue(
            note.startswith(_STABILITY_NOTE_PREFIX),
            f"stability_note does not start with expected prefix.\n"
            f"Expected: {_STABILITY_NOTE_PREFIX!r}\nGot: {note!r}",
        )


if __name__ == "__main__":
    unittest.main()
