"""Phase 2A — KMZ Engineering Render Payload lock-down suite.

Tests for ``_build_kmz_render_payload`` and
``get_kmz_render_payload``, added in Phase 2A V1.

ISOLATION STRATEGY
------------------
Tests call ``_build_kmz_render_payload`` directly with synthetic
in-memory dicts that mirror the kmz_semantic output shape.
HTTP endpoint behaviour is tested by monkeypatching ``main.STATE``.
No real KMZ I/O.  No network calls.

REGRESSION ASSERTION
--------------------
The final test verifies via AST analysis that operational helpers do
not reference the render payload helper, schema constant, or endpoint.
If that test fails after a code change, investigate before proceeding.

IF A TEST FAILS after a legitimate Phase 2A change:
  1. Confirm the change is intentional.
  2. Update the relevant assertion or fixture below.
  3. Add a comment explaining why.
  DO NOT "fix to green" without understanding the failure.
"""

from __future__ import annotations

import ast
import copy
import hashlib
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
# Schema lock — exact key sets produced by _build_kmz_render_payload.
# ---------------------------------------------------------------------------
EXPECTED_TOP_KEYS: frozenset = frozenset(
    {
        "schema_version",
        "generated_at",
        "render_caps",
        "points",
        "lines",
        "polygons",
        "categories",
        "summary",
    }
)

EXPECTED_RENDER_CAPS_KEYS: frozenset = frozenset(
    {
        "max_points",
        "max_lines",
        "max_polygons",
        "max_vertices_per_line",
    }
)

# Phase 2B + 2I: shared Tier-1 metadata keys present on every feature record.
_META_KEYS: frozenset = frozenset(
    {
        "description",
        "description_raw",
        "extended_data",
        "chainage_ft",
        "sequence_number",
        "sequence_kind",
        "lifecycle",
        "style_url",
        "icon_href",
    }
)

EXPECTED_POINT_KEYS: frozenset = frozenset(
    {
        "feature_id",
        "coord",
        "classification",
        "name",
        "icon_glyph",
        "color",
        "folder_path",
    }
) | _META_KEYS

EXPECTED_LINE_KEYS: frozenset = frozenset(
    {
        "feature_id",
        "coords",
        "classification",
        "name",
        "color",
        "width",
        "dash",
        "folder_path",
    }
) | _META_KEYS

EXPECTED_POLYGON_KEYS: frozenset = frozenset(
    {
        "feature_id",
        "outer",
        "inner",
        "classification",
        "name",
        "fill_color",
        "folder_path",
    }
) | _META_KEYS

EXPECTED_CATEGORY_KEYS: frozenset = frozenset(
    {
        "classification",
        "point_count",
        "line_count",
        "polygon_count",
        "total",
    }
)

EXPECTED_SUMMARY_KEYS: frozenset = frozenset(
    {
        "total_points",
        "total_lines",
        "total_polygons",
        "points_truncated",
        "lines_truncated",
        "polygons_truncated",
        "source_feature_count",
    }
)

# Forbidden: operational fields that must never appear in the render payload.
FORBIDDEN_FIELDS: frozenset = frozenset(
    {
        "redline_segments",
        "route_catalog",
        "match_pass_id",
        "snap_review_events",
        "endpoint_snap_recommendations",
    }
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_point_feature(
    idx: int = 1,
    classification: str = "handhole",
    lat: float = 30.0,
    lon: float = -96.0,
    name: str = "HH-001",
    style_resolved: Optional[Dict[str, Any]] = None,
    lifecycle: Optional[Dict[str, Any]] = None,
    folder_path: Optional[List[str]] = None,
) -> Dict[str, Any]:
    return {
        "feature_id": f"semantic_{idx}",
        "placemark_id": None,
        "placemark_name": name,
        "description": "",
        "description_raw": "",
        "folder_path": folder_path or ["Design", "Handholes"],
        "folder_path_str": "Design / Handholes",
        "geometry_type": "Point",
        "style_url": "#handhole-style",
        "extended_data": {},
        "coords_hint": [lat, lon],
        "classification": classification,
        "confidence": "high",
        "classification_reason": "test",
        "source_filename": "test.kmz",
        "chainage_ft": None,
        "chainage_source": None,
        "sequence_number": None,
        "sequence_kind": None,
        "full_geometry": {"kind": "Point", "coord": [lat, lon]},
        "multigeometry_children": [],
        "style_resolved": style_resolved,
        "lifecycle": lifecycle,
        "classification_debug": {},
    }


def _make_line_feature(
    idx: int = 2,
    classification: str = "cable_route",
    coords: Optional[List[List[float]]] = None,
    name: str = "Route A",
    style_resolved: Optional[Dict[str, Any]] = None,
    lifecycle: Optional[Dict[str, Any]] = None,
    folder_path: Optional[List[str]] = None,
) -> Dict[str, Any]:
    if coords is None:
        coords = [[30.0, -96.0], [30.001, -96.001], [30.002, -96.002]]
    return {
        "feature_id": f"semantic_{idx}",
        "placemark_id": None,
        "placemark_name": name,
        "description": "",
        "description_raw": "",
        "folder_path": folder_path or ["Design", "Routes"],
        "folder_path_str": "Design / Routes",
        "geometry_type": "LineString",
        "style_url": "#route-style",
        "extended_data": {},
        "coords_hint": coords[0] if coords else None,
        "classification": classification,
        "confidence": "high",
        "classification_reason": "test",
        "source_filename": "test.kmz",
        "chainage_ft": None,
        "chainage_source": None,
        "sequence_number": None,
        "sequence_kind": None,
        "full_geometry": {"kind": "LineString", "coords": coords},
        "multigeometry_children": [],
        "style_resolved": style_resolved,
        "lifecycle": lifecycle,
        "classification_debug": {},
    }


def _make_polygon_feature(
    idx: int = 3,
    classification: str = "work_zone",
    outer: Optional[List[List[float]]] = None,
    name: str = "Zone A",
    style_resolved: Optional[Dict[str, Any]] = None,
    lifecycle: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if outer is None:
        outer = [[30.0, -96.0], [30.001, -96.0], [30.001, -96.001], [30.0, -96.001]]
    return {
        "feature_id": f"semantic_{idx}",
        "placemark_id": None,
        "placemark_name": name,
        "description": "",
        "description_raw": "",
        "folder_path": ["Design", "Zones"],
        "folder_path_str": "Design / Zones",
        "geometry_type": "Polygon",
        "style_url": "#zone-style",
        "extended_data": {},
        "coords_hint": outer[0] if outer else None,
        "classification": classification,
        "confidence": "medium",
        "classification_reason": "test",
        "source_filename": "test.kmz",
        "chainage_ft": None,
        "chainage_source": None,
        "sequence_number": None,
        "sequence_kind": None,
        "full_geometry": {"kind": "Polygon", "outer": outer},
        "multigeometry_children": [],
        "style_resolved": style_resolved,
        "lifecycle": lifecycle,
        "classification_debug": {},
    }


def _make_kmz_semantic(features: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "parser_version": "semantic-1",
        "features": features,
        "index": {
            "feature_count": len(features),
            "truncated": False,
        },
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestKmzRenderPayloadSchema(unittest.TestCase):
    """test_01 – test_05: schema lock tests."""

    def _build(self, features: List[Dict[str, Any]]) -> Dict[str, Any]:
        return main._build_kmz_render_payload(_make_kmz_semantic(features))

    def test_01_top_level_keys(self) -> None:
        result = self._build([_make_point_feature(), _make_line_feature(), _make_polygon_feature()])
        self.assertEqual(frozenset(result.keys()), EXPECTED_TOP_KEYS)

    def test_02_render_caps_keys(self) -> None:
        result = self._build([_make_point_feature()])
        self.assertEqual(frozenset(result["render_caps"].keys()), EXPECTED_RENDER_CAPS_KEYS)

    def test_03_point_keys(self) -> None:
        result = self._build([_make_point_feature()])
        self.assertTrue(len(result["points"]) >= 1)
        self.assertEqual(frozenset(result["points"][0].keys()), EXPECTED_POINT_KEYS)

    def test_04_line_keys(self) -> None:
        result = self._build([_make_line_feature()])
        self.assertTrue(len(result["lines"]) >= 1)
        self.assertEqual(frozenset(result["lines"][0].keys()), EXPECTED_LINE_KEYS)

    def test_05_polygon_keys(self) -> None:
        result = self._build([_make_polygon_feature()])
        self.assertTrue(len(result["polygons"]) >= 1)
        self.assertEqual(frozenset(result["polygons"][0].keys()), EXPECTED_POLYGON_KEYS)

    def test_06_category_keys(self) -> None:
        result = self._build([_make_point_feature()])
        self.assertTrue(len(result["categories"]) >= 1)
        self.assertEqual(frozenset(result["categories"][0].keys()), EXPECTED_CATEGORY_KEYS)

    def test_07_summary_keys(self) -> None:
        result = self._build([_make_point_feature()])
        self.assertEqual(frozenset(result["summary"].keys()), EXPECTED_SUMMARY_KEYS)


class TestKmzRenderPayloadForbiddenFields(unittest.TestCase):
    """test_08: no forbidden operational fields in payload."""

    def test_08_no_forbidden_fields(self) -> None:
        features = [_make_point_feature(), _make_line_feature(), _make_polygon_feature()]
        result = main._build_kmz_render_payload(_make_kmz_semantic(features))
        payload_str = json.dumps(result)
        for field in FORBIDDEN_FIELDS:
            self.assertNotIn(field, payload_str, msg=f"Forbidden field '{field}' found in payload")


class TestKmzRenderPayloadEmptyInputs(unittest.TestCase):
    """test_09 – test_12: missing/empty/malformed inputs never raise."""

    def test_09_none_input_returns_empty(self) -> None:
        result = main._build_kmz_render_payload(None)
        self.assertEqual(result["schema_version"], "kmz-render-payload-3")
        self.assertEqual(result["points"], [])
        self.assertEqual(result["lines"], [])
        self.assertEqual(result["polygons"], [])
        self.assertEqual(result["categories"], [])

    def test_10_non_dict_input_returns_empty(self) -> None:
        for bad in [[], "foo", 42, True, b"bytes"]:
            result = main._build_kmz_render_payload(bad)  # type: ignore[arg-type]
            self.assertEqual(result["points"], [], msg=f"Expected empty for input {bad!r}")

    def test_11_empty_features_list(self) -> None:
        result = main._build_kmz_render_payload(_make_kmz_semantic([]))
        self.assertEqual(result["summary"]["total_points"], 0)
        self.assertEqual(result["summary"]["total_lines"], 0)
        self.assertEqual(result["summary"]["total_polygons"], 0)

    def test_12_malformed_feature_dict_never_raises(self) -> None:
        bad_features: List[Any] = [
            None,
            "string",
            42,
            {},
            {"feature_id": "x", "full_geometry": {"kind": "Point", "coord": [None, None]}},
            {"feature_id": "y", "full_geometry": {"kind": "LineString", "coords": [[30.0]]}},
            {"feature_id": "z", "full_geometry": {"kind": "Polygon", "outer": [[30.0, -96.0]]}},
        ]
        # Should not raise; result may be empty
        result = main._build_kmz_render_payload(_make_kmz_semantic(bad_features))
        self.assertIn("points", result)
        self.assertIn("lines", result)
        self.assertIn("polygons", result)


class TestKmzRenderPayloadCaps(unittest.TestCase):
    """test_13 – test_16: cap enforcement."""

    def _make_many_points(self, n: int) -> List[Dict[str, Any]]:
        return [_make_point_feature(idx=i, lat=30.0 + i * 0.001, lon=-96.0) for i in range(n)]

    def _make_many_lines(self, n: int) -> List[Dict[str, Any]]:
        return [_make_line_feature(idx=i, coords=[[30.0, -96.0 + i * 0.001], [30.001, -96.0 + i * 0.001]]) for i in range(n)]

    def _make_many_polygons(self, n: int) -> List[Dict[str, Any]]:
        outer = [[30.0, -96.0], [30.001, -96.0], [30.001, -96.001], [30.0, -96.001]]
        return [_make_polygon_feature(idx=i, outer=outer) for i in range(n)]

    def test_13_point_cap_respected(self) -> None:
        features = self._make_many_points(4050)
        result = main._build_kmz_render_payload(_make_kmz_semantic(features))
        self.assertLessEqual(len(result["points"]), main._KMZ_RENDER_MAX_POINTS)

    def test_14_line_cap_respected(self) -> None:
        features = self._make_many_lines(1550)
        result = main._build_kmz_render_payload(_make_kmz_semantic(features))
        self.assertLessEqual(len(result["lines"]), main._KMZ_RENDER_MAX_LINES)

    def test_15_polygon_cap_respected(self) -> None:
        features = self._make_many_polygons(550)
        result = main._build_kmz_render_payload(_make_kmz_semantic(features))
        self.assertLessEqual(len(result["polygons"]), main._KMZ_RENDER_MAX_POLYGONS)

    def test_16_line_vertex_cap_respected(self) -> None:
        # Build a line with more than 200 vertices
        many_verts = [[30.0 + i * 0.0001, -96.0] for i in range(300)]
        feat = _make_line_feature(idx=1, coords=many_verts)
        result = main._build_kmz_render_payload(_make_kmz_semantic([feat]))
        self.assertTrue(len(result["lines"]) >= 1)
        self.assertLessEqual(len(result["lines"][0]["coords"]), main._KMZ_RENDER_MAX_VERTICES_PER_LINE)


class TestKmzRenderPayloadColors(unittest.TestCase):
    """test_17 – test_20: color resolution and fallback."""

    def test_17_color_fallback_nonnull_for_point(self) -> None:
        feat = _make_point_feature(style_resolved=None)
        result = main._build_kmz_render_payload(_make_kmz_semantic([feat]))
        self.assertTrue(len(result["points"]) >= 1)
        color = result["points"][0]["color"]
        self.assertIsInstance(color, str)
        self.assertTrue(len(color) > 0)

    def test_18_color_fallback_nonnull_for_line(self) -> None:
        feat = _make_line_feature(style_resolved=None)
        result = main._build_kmz_render_payload(_make_kmz_semantic([feat]))
        self.assertTrue(len(result["lines"]) >= 1)
        color = result["lines"][0]["color"]
        self.assertIsInstance(color, str)
        self.assertTrue(len(color) > 0)

    def test_19_color_fallback_nonnull_for_polygon(self) -> None:
        feat = _make_polygon_feature(style_resolved=None)
        result = main._build_kmz_render_payload(_make_kmz_semantic([feat]))
        self.assertTrue(len(result["polygons"]) >= 1)
        color = result["polygons"][0]["fill_color"]
        self.assertIsInstance(color, str)
        self.assertTrue(len(color) > 0)

    def test_20_resolved_line_color_used_when_present(self) -> None:
        feat = _make_line_feature(style_resolved={"line_color": "#ff0000", "line_width": 2.5})
        result = main._build_kmz_render_payload(_make_kmz_semantic([feat]))
        self.assertEqual(result["lines"][0]["color"], "#ff0000")
        self.assertAlmostEqual(result["lines"][0]["width"], 2.5, places=3)


class TestKmzRenderPayloadGlyphs(unittest.TestCase):
    """test_21: icon_glyph mapping."""

    def test_21_icon_glyph_mapping(self) -> None:
        cases = [
            ("handhole", "circle"),
            ("node", "circle"),
            ("splice", "square"),
            ("splice_enclosure", "square"),
            ("reel", "diamond"),
            ("slack_loop", "diamond"),
            ("unknown_class", "ring"),
            ("generic", "ring"),
        ]
        for cls, expected_glyph in cases:
            feat = _make_point_feature(idx=1, classification=cls)
            result = main._build_kmz_render_payload(_make_kmz_semantic([feat]))
            if result["points"]:
                self.assertEqual(
                    result["points"][0]["icon_glyph"],
                    expected_glyph,
                    msg=f"classification={cls!r} expected glyph={expected_glyph!r}",
                )


class TestKmzRenderPayloadCategories(unittest.TestCase):
    """test_22: category generation."""

    def test_22_categories_generated_correctly(self) -> None:
        features = [
            _make_point_feature(idx=1, classification="handhole"),
            _make_point_feature(idx=2, classification="handhole"),
            _make_line_feature(idx=3, classification="cable_route"),
            _make_polygon_feature(idx=4, classification="work_zone"),
        ]
        result = main._build_kmz_render_payload(_make_kmz_semantic(features))
        cats = {c["classification"]: c for c in result["categories"]}
        self.assertIn("handhole", cats)
        self.assertEqual(cats["handhole"]["point_count"], 2)
        self.assertIn("cable_route", cats)
        self.assertEqual(cats["cable_route"]["line_count"], 1)
        self.assertIn("work_zone", cats)
        self.assertEqual(cats["work_zone"]["polygon_count"], 1)


class TestKmzRenderPayloadNoMutation(unittest.TestCase):
    """test_23: input dict is not mutated."""

    def test_23_no_mutation_of_input(self) -> None:
        features = [_make_point_feature(), _make_line_feature(), _make_polygon_feature()]
        semantic = _make_kmz_semantic(features)
        before_sha = hashlib.sha256(json.dumps(semantic, sort_keys=True).encode()).hexdigest()
        _ = main._build_kmz_render_payload(semantic)
        after_sha = hashlib.sha256(json.dumps(semantic, sort_keys=True).encode()).hexdigest()
        self.assertEqual(before_sha, after_sha, "Input kmz_semantic was mutated")


class TestKmzRenderPayloadTruncation(unittest.TestCase):
    """test_24: name and folder_path truncation."""

    def test_24_name_truncated_to_80_chars(self) -> None:
        long_name = "X" * 150
        feat = _make_point_feature(name=long_name)
        result = main._build_kmz_render_payload(_make_kmz_semantic([feat]))
        self.assertTrue(len(result["points"]) >= 1)
        self.assertLessEqual(len(result["points"][0]["name"]), main._KMZ_RENDER_MAX_NAME_LEN)

    def test_24b_folder_path_depth_capped(self) -> None:
        deep_folder = ["L1", "L2", "L3", "L4", "L5", "L6"]
        feat = _make_point_feature(folder_path=deep_folder)
        result = main._build_kmz_render_payload(_make_kmz_semantic([feat]))
        self.assertTrue(len(result["points"]) >= 1)
        self.assertLessEqual(len(result["points"][0]["folder_path"]), main._KMZ_RENDER_MAX_FOLDER_DEPTH)


class TestKmzRenderPayloadDash(unittest.TestCase):
    """test_25: dash flag from lifecycle."""

    def test_25_proposed_lifecycle_sets_dash(self) -> None:
        lifecycle = {"label": "proposed", "confidence": "medium", "reason": "folder"}
        feat = _make_line_feature(lifecycle=lifecycle)
        result = main._build_kmz_render_payload(_make_kmz_semantic([feat]))
        self.assertTrue(len(result["lines"]) >= 1)
        self.assertTrue(result["lines"][0]["dash"])

    def test_25b_no_lifecycle_no_dash(self) -> None:
        feat = _make_line_feature(lifecycle=None)
        result = main._build_kmz_render_payload(_make_kmz_semantic([feat]))
        self.assertTrue(len(result["lines"]) >= 1)
        self.assertFalse(result["lines"][0]["dash"])


class TestKmzRenderPayloadEndpointReadOnly(unittest.TestCase):
    """test_26: endpoint does not mutate STATE."""

    def test_26_endpoint_does_not_mutate_state(self) -> None:
        import hashlib
        import json

        features = [_make_point_feature(), _make_line_feature()]
        semantic = _make_kmz_semantic(features)

        orig_segs = [{"segment_id": "s1", "coords": [[30.0, -96.0], [30.1, -96.1]]}]
        orig_catalog = {"route_1": {"segments": []}}

        # Snapshot STATE before
        orig_state_backup = {
            "kmz_semantic": copy.deepcopy(semantic),
            "redline_segments": copy.deepcopy(orig_segs),
            "route_catalog": copy.deepcopy(orig_catalog),
        }

        original_state = main.STATE.copy()
        main.STATE["kmz_semantic"] = copy.deepcopy(semantic)
        main.STATE["redline_segments"] = copy.deepcopy(orig_segs)
        main.STATE["route_catalog"] = copy.deepcopy(orig_catalog)

        def sha(obj: Any) -> str:
            return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()

        seg_sha_before = sha(main.STATE["redline_segments"])
        cat_sha_before = sha(main.STATE["route_catalog"])

        # Call endpoint
        response = main.get_kmz_render_payload()
        data = json.loads(response.body)

        seg_sha_after = sha(main.STATE["redline_segments"])
        cat_sha_after = sha(main.STATE["route_catalog"])

        # Restore state
        for k, v in original_state.items():
            main.STATE[k] = v

        self.assertEqual(seg_sha_before, seg_sha_after, "redline_segments was mutated by endpoint")
        self.assertEqual(cat_sha_before, cat_sha_after, "route_catalog was mutated by endpoint")
        self.assertEqual(data["schema_version"], "kmz-render-payload-3")


class TestKmzRenderPayloadASTRegression(unittest.TestCase):
    """test_27: AST regression — operational helpers must not reference render payload."""

    def test_27_operational_helpers_do_not_reference_render_payload(self) -> None:
        """Verify that operational pipeline functions do not call or import
        _build_kmz_render_payload, the schema constant, or the endpoint path."""

        _FORBIDDEN_NAMES = frozenset(
            {
                "_build_kmz_render_payload",
                "kmz-render-payload-1",
                "kmz-render-payload-2",
                "kmz-render-payload-3",
                "kmz_render_payload",
                "get_kmz_render_payload",
            }
        )

        # Operational helper names that must remain isolated from the render payload.
        _OPERATIONAL_HELPERS = frozenset(
            {
                "_build_route_match",
                "_run_match_pass",
                "_score_group",
                "_assign_redline_segments",
                "upload_design",
                "_build_kmz_reference",
                "_build_kmz_semantic",
            }
        )

        src_path = Path(__file__).resolve().parents[1] / "main.py"
        src = src_path.read_text(encoding="utf-8")
        tree = ast.parse(src)

        # Build a dict of function_name -> set of names referenced in its body.
        func_refs: dict[str, set[str]] = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                refs: set[str] = set()
                for child in ast.walk(node):
                    if isinstance(child, ast.Name):
                        refs.add(child.id)
                    elif isinstance(child, ast.Attribute):
                        refs.add(child.attr)
                    elif isinstance(child, ast.Constant) and isinstance(child.value, str):
                        refs.add(child.value)
                func_refs[node.name] = refs

        violations: list[str] = []
        for op_fn in _OPERATIONAL_HELPERS:
            if op_fn not in func_refs:
                continue
            refs = func_refs[op_fn]
            for forbidden in _FORBIDDEN_NAMES:
                if forbidden in refs:
                    violations.append(f"{op_fn} references {forbidden!r}")

        self.assertEqual(
            violations,
            [],
            msg="Operational helpers must not reference render payload: " + "; ".join(violations),
        )


class TestKmzRenderPayloadSchemaVersion(unittest.TestCase):
    """test_28: schema_version is always 'kmz-render-payload-3'."""

    def test_28_schema_version_constant(self) -> None:
        self.assertEqual(main._KMZ_RENDER_PAYLOAD_SCHEMA, "kmz-render-payload-3")
        result = main._build_kmz_render_payload(None)
        self.assertEqual(result["schema_version"], "kmz-render-payload-3")

    def test_28b_render_caps_values_correct(self) -> None:
        result = main._build_kmz_render_payload(_make_kmz_semantic([]))
        caps = result["render_caps"]
        self.assertEqual(caps["max_points"], 4000)
        self.assertEqual(caps["max_lines"], 1500)
        self.assertEqual(caps["max_polygons"], 500)
        self.assertEqual(caps["max_vertices_per_line"], 200)


class TestKmzRenderPayloadMultiGeometry(unittest.TestCase):
    """test_29: MultiGeometry children handled — Phase 2B full coords."""

    def _make_multi_feature(self, children: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "feature_id": "semantic_99",
            "placemark_id": None,
            "placemark_name": "Cable+Node",
            "description": "Phase 2B multi",
            "folder_path": ["Design"],
            "folder_path_str": "Design",
            "geometry_type": "MultiGeometry",
            "style_url": "",
            "extended_data": {},
            "coords_hint": [30.0, -96.0],
            "classification": "handhole",
            "confidence": "high",
            "classification_reason": "test",
            "source_filename": "test.kmz",
            "chainage_ft": 150.0,
            "chainage_source": "name",
            "sequence_number": "HH-3",
            "sequence_kind": "handhole",
            "full_geometry": None,
            "multigeometry_children": children,
            "style_resolved": None,
            "lifecycle": None,
            "classification_debug": {},
        }

    def test_29_multigeometry_point_extracted(self) -> None:
        feat = self._make_multi_feature([
            {"kind": "Point", "coord_hint": [30.0, -96.0]},
        ])
        result = main._build_kmz_render_payload(_make_kmz_semantic([feat]))
        self.assertTrue(len(result["points"]) >= 1, "Expected point from MultiGeometry child")

    def test_29b_multigeometry_linestring_full_coords(self) -> None:
        """Phase 2B: LineString children must use full coords, not coord_hint."""
        full_coords = [[30.0, -96.0], [30.001, -96.001], [30.002, -96.002]]
        feat = self._make_multi_feature([
            {"kind": "LineString", "coord_hint": full_coords[0], "coords": full_coords},
        ])
        result = main._build_kmz_render_payload(_make_kmz_semantic([feat]))
        self.assertTrue(len(result["lines"]) >= 1, "Expected line from MultiGeometry child with full coords")
        self.assertEqual(len(result["lines"][0]["coords"]), 3, "Full 3-vertex coords must be preserved")

    def test_29c_multigeometry_linestring_without_full_coords_skipped(self) -> None:
        """MultiGeometry LineString without 'coords' field is skipped (pre-2B parse)."""
        feat = self._make_multi_feature([
            {"kind": "LineString", "coord_hint": [30.0, -96.0]},
        ])
        result = main._build_kmz_render_payload(_make_kmz_semantic([feat]))
        self.assertEqual(len(result["lines"]), 0, "LineString without coords must be skipped")

    def test_29d_multigeometry_polygon_full_outer(self) -> None:
        """Phase 2B: Polygon MultiGeometry children with full outer emit polygon records."""
        outer = [[30.0, -96.0], [30.001, -96.0], [30.001, -96.001], [30.0, -96.001]]
        inner = [[30.0002, -96.0002], [30.0008, -96.0002], [30.0008, -96.0008]]
        feat = self._make_multi_feature([
            {"kind": "Polygon", "coord_hint": outer[0], "outer": outer, "inner": [inner]},
        ])
        result = main._build_kmz_render_payload(_make_kmz_semantic([feat]))
        self.assertTrue(len(result["polygons"]) >= 1, "Expected polygon from MultiGeometry child with full outer")
        poly = result["polygons"][0]
        self.assertEqual(len(poly["outer"]), 4)
        self.assertTrue(len(poly["inner"]) >= 1, "Inner ring must be preserved")


class TestKmzRenderPayloadWidthCap(unittest.TestCase):
    """test_30: line width capped at 3.0."""

    def test_30_line_width_capped_at_3(self) -> None:
        feat = _make_line_feature(style_resolved={"line_color": "#ff0000", "line_width": 10.0})
        result = main._build_kmz_render_payload(_make_kmz_semantic([feat]))
        self.assertTrue(len(result["lines"]) >= 1)
        self.assertLessEqual(result["lines"][0]["width"], 3.0)


# ---------------------------------------------------------------------------
# Phase 2B: Tier-1 metadata propagation tests (tests 31–44)
# ---------------------------------------------------------------------------

class TestKmzRenderPayloadMetaFields(unittest.TestCase):
    """test_31 – test_36: Tier-1 metadata fields propagated correctly."""

    def test_31_description_propagated_to_point(self) -> None:
        feat = _make_point_feature()
        feat["description"] = "Handhole depth 36 inches, manufacturer Hubbell"
        result = main._build_kmz_render_payload(_make_kmz_semantic([feat]))
        self.assertTrue(len(result["points"]) >= 1)
        self.assertEqual(result["points"][0]["description"], "Handhole depth 36 inches, manufacturer Hubbell")

    def test_32_description_truncated_at_200_chars(self) -> None:
        long_desc = "D" * 300
        feat = _make_point_feature()
        feat["description"] = long_desc
        result = main._build_kmz_render_payload(_make_kmz_semantic([feat]))
        self.assertTrue(len(result["points"]) >= 1)
        self.assertLessEqual(len(result["points"][0]["description"]), 200)

    def test_33_extended_data_key_cap_at_32(self) -> None:
        # Phase 2I: cap raised from 8 → 32; ensure limit is enforced.
        big_ed = {f"key_{i}": f"val_{i}" for i in range(50)}
        feat = _make_line_feature()
        feat["extended_data"] = big_ed
        result = main._build_kmz_render_payload(_make_kmz_semantic([feat]))
        self.assertTrue(len(result["lines"]) >= 1)
        self.assertLessEqual(len(result["lines"][0]["extended_data"]), 32)
        self.assertGreater(len(result["lines"][0]["extended_data"]), 8,
                           "Cap is 32; 50-key dict must produce more than 8 rows")

    def test_34_extended_data_value_truncated_at_80(self) -> None:
        feat = _make_line_feature()
        feat["extended_data"] = {"depth": "X" * 200}
        result = main._build_kmz_render_payload(_make_kmz_semantic([feat]))
        self.assertTrue(len(result["lines"]) >= 1)
        for v in result["lines"][0]["extended_data"].values():
            self.assertLessEqual(len(v), 80)

    def test_35_chainage_propagated(self) -> None:
        feat = _make_point_feature()
        feat["chainage_ft"] = 1250.5
        result = main._build_kmz_render_payload(_make_kmz_semantic([feat]))
        self.assertTrue(len(result["points"]) >= 1)
        self.assertAlmostEqual(result["points"][0]["chainage_ft"], 1250.5)

    def test_36_sequence_propagated(self) -> None:
        feat = _make_point_feature()
        feat["sequence_number"] = "HH-7"
        feat["sequence_kind"] = "handhole"
        result = main._build_kmz_render_payload(_make_kmz_semantic([feat]))
        self.assertTrue(len(result["points"]) >= 1)
        self.assertEqual(result["points"][0]["sequence_number"], "HH-7")
        self.assertEqual(result["points"][0]["sequence_kind"], "handhole")

    def test_37_lifecycle_full_struct_propagated(self) -> None:
        lc = {"label": "asbuilt", "confidence": "high", "reason": "folder"}
        feat = _make_line_feature(lifecycle=lc)
        result = main._build_kmz_render_payload(_make_kmz_semantic([feat]))
        self.assertTrue(len(result["lines"]) >= 1)
        lc_out = result["lines"][0]["lifecycle"]
        self.assertIsNotNone(lc_out)
        self.assertEqual(lc_out["label"], "asbuilt")
        self.assertEqual(lc_out["confidence"], "high")
        self.assertEqual(lc_out["reason"], "folder")

    def test_38_lifecycle_none_when_missing(self) -> None:
        feat = _make_point_feature(lifecycle=None)
        result = main._build_kmz_render_payload(_make_kmz_semantic([feat]))
        self.assertTrue(len(result["points"]) >= 1)
        self.assertIsNone(result["points"][0]["lifecycle"])

    def test_39_meta_fields_on_polygon(self) -> None:
        feat = _make_polygon_feature()
        feat["description"] = "Work zone"
        feat["chainage_ft"] = 500.0
        result = main._build_kmz_render_payload(_make_kmz_semantic([feat]))
        self.assertTrue(len(result["polygons"]) >= 1)
        poly = result["polygons"][0]
        self.assertEqual(poly["description"], "Work zone")
        self.assertAlmostEqual(poly["chainage_ft"], 500.0)

    def test_40_extended_data_empty_when_missing(self) -> None:
        feat = _make_point_feature()
        feat["extended_data"] = None
        result = main._build_kmz_render_payload(_make_kmz_semantic([feat]))
        self.assertTrue(len(result["points"]) >= 1)
        self.assertEqual(result["points"][0]["extended_data"], {})


class TestKmzRenderPayloadPolygonInnerRings(unittest.TestCase):
    """test_41 – test_42: polygon inner rings exposed."""

    def test_41_polygon_inner_rings_exposed(self) -> None:
        outer = [[30.0, -96.0], [30.01, -96.0], [30.01, -96.01], [30.0, -96.01]]
        inner = [[30.002, -96.002], [30.008, -96.002], [30.008, -96.008]]
        feat = _make_polygon_feature(outer=outer)
        feat["full_geometry"] = {"kind": "Polygon", "outer": outer, "inner": [inner]}
        result = main._build_kmz_render_payload(_make_kmz_semantic([feat]))
        self.assertTrue(len(result["polygons"]) >= 1)
        poly = result["polygons"][0]
        self.assertIn("inner", poly)
        self.assertTrue(len(poly["inner"]) >= 1)
        self.assertTrue(len(poly["inner"][0]) >= 3)

    def test_42_polygon_inner_defaults_to_empty_list(self) -> None:
        feat = _make_polygon_feature()
        result = main._build_kmz_render_payload(_make_kmz_semantic([feat]))
        self.assertTrue(len(result["polygons"]) >= 1)
        self.assertEqual(result["polygons"][0]["inner"], [])


class TestKmzRenderPayloadTruncationFlagFix(unittest.TestCase):
    """test_43 – test_44: per-type truncation flag correctness (bug fix)."""

    def _make_many_typed(
        self, n_points: int = 0, n_lines: int = 0, n_polygons: int = 0
    ) -> List[Dict[str, Any]]:
        feats: List[Dict[str, Any]] = []
        for i in range(n_points):
            feats.append(_make_point_feature(idx=i, lat=30.0 + i * 0.0001, lon=-96.0))
        for i in range(n_lines):
            feats.append(_make_line_feature(idx=10000 + i, coords=[[30.0, -96.0 + i * 0.0001], [30.001, -96.0 + i * 0.0001]]))
        for i in range(n_polygons):
            outer = [[30.0, -96.0], [30.001, -96.0], [30.001, -96.001], [30.0, -96.001]]
            feats.append(_make_polygon_feature(idx=20000 + i, outer=outer))
        return feats

    def test_43_points_capped_lines_not_capped(self) -> None:
        """4001 points + 5 lines → points_truncated=True, lines_truncated=False."""
        feats = self._make_many_typed(n_points=4001, n_lines=5, n_polygons=0)
        result = main._build_kmz_render_payload(_make_kmz_semantic(feats))
        self.assertTrue(result["summary"]["points_truncated"], "points_truncated should be True")
        self.assertFalse(result["summary"]["lines_truncated"], "lines_truncated should be False")
        self.assertFalse(result["summary"]["polygons_truncated"], "polygons_truncated should be False")

    def test_44_lines_capped_points_not_capped(self) -> None:
        """5 points + 1501 lines → lines_truncated=True, points_truncated=False."""
        feats = self._make_many_typed(n_points=5, n_lines=1501, n_polygons=0)
        result = main._build_kmz_render_payload(_make_kmz_semantic(feats))
        self.assertFalse(result["summary"]["points_truncated"], "points_truncated should be False")
        self.assertTrue(result["summary"]["lines_truncated"], "lines_truncated should be True")
        self.assertFalse(result["summary"]["polygons_truncated"], "polygons_truncated should be False")


class TestKmzRenderPayloadPhase2I(unittest.TestCase):
    """test_45 – test_50: Phase 2I — icon/balloon fidelity fields."""

    def _build(self, features: List[Dict[str, Any]]) -> Dict[str, Any]:
        return main._build_kmz_render_payload(_make_kmz_semantic(features))

    # --- description_raw ---

    def test_45_description_raw_propagated_to_point(self) -> None:
        feat = _make_point_feature()
        feat["description_raw"] = "<table><tr><td>AP Number</td><td>AP-001</td></tr></table>"
        result = self._build([feat])
        self.assertTrue(len(result["points"]) >= 1)
        self.assertIn("AP-001", result["points"][0]["description_raw"])

    def test_46_description_raw_capped_at_4096_chars(self) -> None:
        feat = _make_point_feature()
        feat["description_raw"] = "X" * 9000
        result = self._build([feat])
        self.assertTrue(len(result["points"]) >= 1)
        self.assertLessEqual(len(result["points"][0]["description_raw"]), 4096)

    def test_46b_description_raw_absent_gives_empty_string(self) -> None:
        feat = _make_point_feature()
        # description_raw not set at all
        feat.pop("description_raw", None)
        result = self._build([feat])
        self.assertTrue(len(result["points"]) >= 1)
        self.assertEqual(result["points"][0]["description_raw"], "")

    def test_46c_description_raw_on_line(self) -> None:
        feat = _make_line_feature()
        feat["description_raw"] = "<b>Route notes</b>"
        result = self._build([feat])
        self.assertTrue(len(result["lines"]) >= 1)
        self.assertIn("Route notes", result["lines"][0]["description_raw"])

    def test_46d_description_raw_on_polygon(self) -> None:
        feat = _make_polygon_feature()
        feat["description_raw"] = "<p>Zone boundary</p>"
        result = self._build([feat])
        self.assertTrue(len(result["polygons"]) >= 1)
        self.assertIn("Zone boundary", result["polygons"][0]["description_raw"])

    # --- extended_data cap 32 ---

    def test_47_extended_data_32_key_cap(self) -> None:
        feat = _make_point_feature()
        feat["extended_data"] = {f"k{i}": f"v{i}" for i in range(40)}
        result = self._build([feat])
        self.assertTrue(len(result["points"]) >= 1)
        ed = result["points"][0]["extended_data"]
        self.assertLessEqual(len(ed), 32)
        self.assertGreater(len(ed), 8, "Cap is 32; should expose more than 8 keys from 40-key dict")

    # --- style_url ---

    def test_48_style_url_propagated_for_point(self) -> None:
        feat = _make_point_feature()
        feat["style_url"] = "#splice-hh-style"
        result = self._build([feat])
        self.assertTrue(len(result["points"]) >= 1)
        self.assertEqual(result["points"][0]["style_url"], "#splice-hh-style")

    def test_48b_style_url_propagated_for_line(self) -> None:
        feat = _make_line_feature()
        feat["style_url"] = "#underground-cable"
        result = self._build([feat])
        self.assertTrue(len(result["lines"]) >= 1)
        self.assertEqual(result["lines"][0]["style_url"], "#underground-cable")

    def test_48c_style_url_propagated_for_polygon(self) -> None:
        feat = _make_polygon_feature()
        feat["style_url"] = "#service-area"
        result = self._build([feat])
        self.assertTrue(len(result["polygons"]) >= 1)
        self.assertEqual(result["polygons"][0]["style_url"], "#service-area")

    def test_48d_style_url_absent_gives_empty_string(self) -> None:
        feat = _make_point_feature()
        feat["style_url"] = None
        result = self._build([feat])
        self.assertTrue(len(result["points"]) >= 1)
        self.assertEqual(result["points"][0]["style_url"], "")

    # --- icon_href ---

    def test_49_icon_href_propagated_when_style_resolved_has_it(self) -> None:
        feat = _make_point_feature(
            style_resolved={"icon_href": "files/triangle_blue.png", "line_color": "#0000ff"}
        )
        result = self._build([feat])
        self.assertTrue(len(result["points"]) >= 1)
        self.assertEqual(result["points"][0]["icon_href"], "files/triangle_blue.png")

    def test_50_icon_href_falls_back_to_empty_string_when_style_resolved_none(self) -> None:
        feat = _make_point_feature(style_resolved=None)
        result = self._build([feat])
        self.assertTrue(len(result["points"]) >= 1)
        self.assertEqual(result["points"][0]["icon_href"], "")

    def test_50b_icon_href_falls_back_when_style_resolved_has_no_icon_href(self) -> None:
        feat = _make_point_feature(style_resolved={"line_color": "#ff0000"})
        result = self._build([feat])
        self.assertTrue(len(result["points"]) >= 1)
        self.assertEqual(result["points"][0]["icon_href"], "")

    def test_50c_icon_href_on_line_defaults_to_empty(self) -> None:
        # Lines rarely carry icon_href; verify safe default.
        feat = _make_line_feature(style_resolved={"line_color": "#ff0000"})
        result = self._build([feat])
        self.assertTrue(len(result["lines"]) >= 1)
        self.assertEqual(result["lines"][0]["icon_href"], "")


if __name__ == "__main__":
    unittest.main()
