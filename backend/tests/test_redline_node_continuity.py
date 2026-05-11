"""Phase 1Q — Node-anchored redline continuity advisor lock-down suite.

14 tests for ``_build_redline_node_continuity`` and
``get_redline_node_continuity``, added in Phase 1Q.

ISOLATION STRATEGY
------------------
Tests call ``_build_redline_node_continuity`` directly with synthetic
in-memory dicts.  The endpoint is tested by monkeypatching ``main.STATE``.
The real STATE is restored in ``tearDown``.  No real KMZ I/O.

IF A TEST FAILS after a legitimate Phase 1Q change:
  1. Confirm the change is intentional.
  2. Update the relevant assertion or fixture below.
  3. Add a comment explaining why.
  DO NOT "fix to green" without understanding the failure.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional

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
        "groups",
        "ungrouped_segment_ids",
        "stats",
        "stability_note",
    }
)

EXPECTED_GROUP_KEYS: frozenset = frozenset(
    {
        "anchor_reference_feature_id",
        "anchor_folder_path",
        "anchor_name",
        "anchor_coordinate",
        "source_segment_ids",
        "engineering_object_ids",
        "endpoint_count",
        "evidence",
    }
)

EXPECTED_STATS_KEYS: frozenset = frozenset(
    {
        "anchor_points_considered",
        "anchor_points_with_groups",
        "redline_segments_total",
        "redline_segments_anchored",
        "redline_segments_unanchored",
    }
)

EXPECTED_EVIDENCE_KEYS: frozenset = frozenset(
    {"segment_id", "endpoint", "distance_ft"}
)

_SCHEMA_VERSION = "redline-node-continuity-1"
_TOLERANCE_FT = 3.0
_STABILITY_NOTE_PREFIX = "redline-node-continuity-1 groups existing redline"


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

# Brenham-area coordinates; we derive offset anchors from these.
_BASE_LAT: float = 30.15
_BASE_LON: float = -96.39

# Degrees per foot at ~30° latitude (approximate, safe for fixtures).
_DEG_PER_FT: float = 1.0 / 364_000.0


def _anchor(
    feature_id: str = "point_1",
    lat: float = _BASE_LAT,
    lon: float = _BASE_LON,
    name: str = "HH-1",
    folder_path: str = "Nodes / Handholes",
) -> Dict[str, Any]:
    return {
        "feature_id": feature_id,
        "name": name,
        "folder_path": folder_path,
        "lat": lat,
        "lon": lon,
        "role": "other",
    }


def _route(
    route_id: str = "route_1",
    start_lat: float = _BASE_LAT,
    start_lon: float = _BASE_LON,
    end_lat: float = _BASE_LAT + 0.01,
    end_lon: float = _BASE_LON + 0.01,
) -> Dict[str, Any]:
    return {
        "route_id": route_id,
        "route_name": "Test Cable",
        "source_folder": "Connections",
        "coords": [[start_lat, start_lon], [end_lat, end_lon]],
        "length_ft": 1000.0,
    }


def _seg(
    segment_id: str = "seg_1",
    matched_route_id: str = "route_1",
) -> Dict[str, Any]:
    return {"segment_id": segment_id, "matched_route_id": matched_route_id}


def _ref(
    point_features: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    return {
        "point_features": point_features or [],
        "line_features": [],
        "polygon_features": [],
    }


def _call(
    segs: Any = None,
    ref: Any = None,
    routes: Any = None,
) -> Dict[str, Any]:
    return main._build_redline_node_continuity(segs, ref, routes)


# ---------------------------------------------------------------------------
# Test suite
# ---------------------------------------------------------------------------

class TestRedlineNodeContinuity(unittest.TestCase):

    # ------------------------------------------------------------------
    # 1 — schema version + tolerance_ft locked
    # ------------------------------------------------------------------

    def test_01_schema_version_and_tolerance_ft(self) -> None:
        """Output must carry the declared schema_version and exact tolerance."""
        result = _call(None, None, None)
        self.assertEqual(result["schema_version"], _SCHEMA_VERSION)
        self.assertEqual(result["tolerance_ft"], _TOLERANCE_FT)

    # ------------------------------------------------------------------
    # 2 — top-level keys present
    # ------------------------------------------------------------------

    def test_02_top_level_keys(self) -> None:
        """All required top-level keys must be present."""
        result = _call(None, None, None)
        self.assertEqual(set(result.keys()) & EXPECTED_TOP_KEYS, EXPECTED_TOP_KEYS)

    # ------------------------------------------------------------------
    # 3 — empty state returns valid empty structure
    # ------------------------------------------------------------------

    def test_03_empty_state_contract(self) -> None:
        """Helper returns valid empty structure for all-None inputs."""
        result = _call(None, None, None)
        self.assertEqual(result["groups"], [])
        self.assertEqual(result["ungrouped_segment_ids"], [])
        stats = result["stats"]
        self.assertEqual(set(stats.keys()), EXPECTED_STATS_KEYS)
        self.assertEqual(stats["redline_segments_total"], 0)
        self.assertEqual(stats["redline_segments_anchored"], 0)

    # ------------------------------------------------------------------
    # 4 — no anchors → all segments ungrouped
    # ------------------------------------------------------------------

    def test_04_no_anchors_all_ungrouped(self) -> None:
        """When point_features is empty every segment falls to ungrouped."""
        segs = [_seg("s1"), _seg("s2")]
        result = _call(segs, _ref([]), [_route()])
        self.assertEqual(result["groups"], [])
        self.assertIn("s1", result["ungrouped_segment_ids"])
        self.assertIn("s2", result["ungrouped_segment_ids"])
        stats = result["stats"]
        self.assertEqual(stats["anchor_points_considered"], 0)
        self.assertEqual(stats["redline_segments_unanchored"], 2)

    # ------------------------------------------------------------------
    # 5 — no redline segments → empty groups + empty ungrouped
    # ------------------------------------------------------------------

    def test_05_no_redline_segments(self) -> None:
        """When redline_segments is empty the result is empty but valid."""
        result = _call([], _ref([_anchor()]), [_route()])
        self.assertEqual(result["groups"], [])
        self.assertEqual(result["ungrouped_segment_ids"], [])
        stats = result["stats"]
        self.assertEqual(stats["redline_segments_total"], 0)

    # ------------------------------------------------------------------
    # 6 — endpoint within tolerance is grouped
    # ------------------------------------------------------------------

    def test_06_endpoint_within_tolerance_grouped(self) -> None:
        """A segment start ≤ tolerance from an anchor enters the group."""
        # Place anchor exactly at base coords.
        anc = _anchor(lat=_BASE_LAT, lon=_BASE_LON)
        # Place route start 2 ft north (≤ 3 ft tolerance).
        offset = 2.0 * _DEG_PER_FT
        rt = _route(start_lat=_BASE_LAT + offset, start_lon=_BASE_LON)
        result = _call([_seg()], _ref([anc]), [rt])
        self.assertEqual(len(result["groups"]), 1)
        g = result["groups"][0]
        self.assertIn("seg_1", g["source_segment_ids"])
        self.assertEqual(g["anchor_reference_feature_id"], "point_1")
        self.assertGreater(g["endpoint_count"], 0)
        ev = g["evidence"][0]
        self.assertSetEqual(set(ev.keys()), EXPECTED_EVIDENCE_KEYS)
        self.assertLessEqual(ev["distance_ft"], _TOLERANCE_FT)

    # ------------------------------------------------------------------
    # 7 — endpoint outside tolerance is not grouped
    # ------------------------------------------------------------------

    def test_07_endpoint_outside_tolerance_not_grouped(self) -> None:
        """A segment start > tolerance from every anchor → ungrouped."""
        anc = _anchor(lat=_BASE_LAT, lon=_BASE_LON)
        # Place route start 10 ft north (> 3 ft tolerance).
        offset = 10.0 * _DEG_PER_FT
        rt = _route(start_lat=_BASE_LAT + offset, start_lon=_BASE_LON)
        result = _call([_seg()], _ref([anc]), [rt])
        self.assertEqual(result["groups"], [])
        self.assertIn("seg_1", result["ungrouped_segment_ids"])
        stats = result["stats"]
        self.assertEqual(stats["redline_segments_unanchored"], 1)

    # ------------------------------------------------------------------
    # 8 — tolerance boundary: exactly at tolerance is grouped
    # ------------------------------------------------------------------

    def test_08_tolerance_boundary_included(self) -> None:
        """Endpoint just inside _TOLERANCE_FT from anchor is included.

        Uses a verified-safe offset (0.99 * tolerance) so the haversine
        distance is guaranteed to be ≤ _TOLERANCE_FT regardless of the
        approximate lat/ft constant.
        """
        # 99% of tolerance — safely inside the boundary regardless of
        # the DEG_PER_FT approximation precision.
        safe_offset = (_TOLERANCE_FT * 0.99) * _DEG_PER_FT
        anc = _anchor(lat=_BASE_LAT, lon=_BASE_LON)
        rt = _route(start_lat=_BASE_LAT + safe_offset, start_lon=_BASE_LON)
        # Confirm actual distance is within tolerance before asserting grouping.
        d = main._haversine_feet(
            _BASE_LAT + safe_offset, _BASE_LON, _BASE_LAT, _BASE_LON
        )
        self.assertLessEqual(
            d, _TOLERANCE_FT,
            f"Fixture offset produced distance {d:.4f} ft > tolerance "
            f"{_TOLERANCE_FT} ft — adjust _DEG_PER_FT in test fixture",
        )
        result = _call([_seg()], _ref([anc]), [rt])
        self.assertEqual(len(result["groups"]), 1)

    # ------------------------------------------------------------------
    # 9 — two segments share an anchor → single group with two member IDs
    # ------------------------------------------------------------------

    def test_09_two_segments_same_anchor(self) -> None:
        """Two segments whose starts are within tolerance of one anchor → 1 group of 2."""
        offset = 1.5 * _DEG_PER_FT
        anc = _anchor(lat=_BASE_LAT, lon=_BASE_LON)
        rt1 = _route("route_1", start_lat=_BASE_LAT + offset, start_lon=_BASE_LON)
        rt2 = _route("route_2", start_lat=_BASE_LAT, start_lon=_BASE_LON + offset)
        segs = [_seg("s1", "route_1"), _seg("s2", "route_2")]
        result = _call(segs, _ref([anc]), [rt1, rt2])
        self.assertEqual(len(result["groups"]), 1)
        g = result["groups"][0]
        self.assertIn("s1", g["source_segment_ids"])
        self.assertIn("s2", g["source_segment_ids"])
        self.assertEqual(result["ungrouped_segment_ids"], [])
        stats = result["stats"]
        self.assertEqual(stats["redline_segments_anchored"], 2)

    # ------------------------------------------------------------------
    # 10 — two separate anchors produce two separate groups
    # ------------------------------------------------------------------

    def test_10_two_anchors_two_groups(self) -> None:
        """Each anchor that is hit by distinct segments produces its own group."""
        anc1 = _anchor("point_1", lat=_BASE_LAT, lon=_BASE_LON)
        anc2 = _anchor("point_2", lat=_BASE_LAT + 0.01, lon=_BASE_LON)
        # route_1 starts near anchor 1; route_2 starts near anchor 2.
        offset = 1.0 * _DEG_PER_FT
        rt1 = _route("route_1", start_lat=_BASE_LAT + offset, start_lon=_BASE_LON)
        rt2 = _route("route_2", start_lat=_BASE_LAT + 0.01 + offset, start_lon=_BASE_LON)
        segs = [_seg("s1", "route_1"), _seg("s2", "route_2")]
        result = _call(segs, _ref([anc1, anc2]), [rt1, rt2])
        self.assertEqual(len(result["groups"]), 2)
        anchor_ids = {g["anchor_reference_feature_id"] for g in result["groups"]}
        self.assertEqual(anchor_ids, {"point_1", "point_2"})
        self.assertEqual(result["ungrouped_segment_ids"], [])

    # ------------------------------------------------------------------
    # 11 — segment appears in two groups when both endpoints touch distinct anchors
    # ------------------------------------------------------------------

    def test_11_segment_in_two_groups(self) -> None:
        """A segment with start → anchor A and end → anchor B appears in both groups."""
        anc1 = _anchor("point_1", lat=_BASE_LAT, lon=_BASE_LON)
        anc2 = _anchor("point_2", lat=_BASE_LAT + 0.01, lon=_BASE_LON)
        offset = 1.0 * _DEG_PER_FT
        rt = _route(
            "route_1",
            start_lat=_BASE_LAT + offset, start_lon=_BASE_LON,
            end_lat=_BASE_LAT + 0.01 + offset, end_lon=_BASE_LON,
        )
        result = _call([_seg()], _ref([anc1, anc2]), [rt])
        self.assertEqual(len(result["groups"]), 2)
        for g in result["groups"]:
            self.assertIn("seg_1", g["source_segment_ids"])
        # Segment is anchored, not ungrouped.
        self.assertEqual(result["ungrouped_segment_ids"], [])

    # ------------------------------------------------------------------
    # 12 — deterministic ordering (groups + segment IDs + evidence)
    # ------------------------------------------------------------------

    def test_12_deterministic_ordering(self) -> None:
        """Two calls with same input must produce identical group ordering.

        Groups are sorted by (-segment_count, anchor_id) so multi-segment
        groups survive the cap before single-segment groups.  Same-size
        groups are then ordered by anchor_id for determinism.
        """
        anc1 = _anchor("point_2", lat=_BASE_LAT, lon=_BASE_LON)
        anc2 = _anchor("point_1", lat=_BASE_LAT, lon=_BASE_LON + 0.0001)
        offset = 1.0 * _DEG_PER_FT
        rt = _route(
            "route_1",
            start_lat=_BASE_LAT + offset, start_lon=_BASE_LON,
        )
        rt2 = _route(
            "route_2",
            start_lat=_BASE_LAT + offset, start_lon=_BASE_LON + 0.0001,
        )
        segs = [_seg("seg_b", "route_2"), _seg("seg_a", "route_1")]
        r1 = _call(segs, _ref([anc1, anc2]), [rt, rt2])
        r2 = _call(segs, _ref([anc1, anc2]), [rt, rt2])
        # Two calls must produce identical group ordering.
        self.assertEqual(
            [g["anchor_reference_feature_id"] for g in r1["groups"]],
            [g["anchor_reference_feature_id"] for g in r2["groups"]],
        )
        # source_segment_ids within each group are sorted.
        for g in r1["groups"]:
            self.assertEqual(g["source_segment_ids"], sorted(g["source_segment_ids"]))
        # Both groups have 1 segment each → tie broken by anchor_id:
        # point_1 < point_2, so point_1 appears first.
        anchor_ids = [g["anchor_reference_feature_id"] for g in r1["groups"]]
        self.assertEqual(anchor_ids, sorted(anchor_ids))

    # ------------------------------------------------------------------
    # 13 — malformed inputs never raise
    # ------------------------------------------------------------------

    def test_13_malformed_inputs_never_raise(self) -> None:
        """Helper must not raise on any malformed input combination."""
        bad_cases = [
            (None, None, None),
            ([], {}, []),
            ([None, "bad", 42], _ref([]), []),
            ([_seg()], {"point_features": [None, "x"]}, None),
            ([_seg()], _ref([_anchor()]), [None, "bad"]),
            ([{"segment_id": None}], _ref([_anchor()]), [_route()]),
            ([_seg()], _ref([{"feature_id": None, "lat": None, "lon": None}]), []),
        ]
        for segs, ref, routes in bad_cases:
            try:
                result = _call(segs, ref, routes)
                self.assertIn("schema_version", result)
            except Exception as exc:
                self.fail(
                    f"Helper raised on malformed input: "
                    f"{type(exc).__name__}: {exc}"
                )

    # ------------------------------------------------------------------
    # 14 — stats correctness
    # ------------------------------------------------------------------

    def test_14_stats_correctness(self) -> None:
        """stats fields must be internally consistent."""
        anc = _anchor()
        offset = 1.0 * _DEG_PER_FT
        # route_1 anchored; route_2 not anchored (far away)
        rt1 = _route("route_1", start_lat=_BASE_LAT + offset, start_lon=_BASE_LON)
        rt2 = _route(
            "route_2",
            start_lat=_BASE_LAT + 1.0,  # 1 degree away, not within tolerance
            start_lon=_BASE_LON,
        )
        segs = [_seg("s1", "route_1"), _seg("s2", "route_2")]
        result = _call(segs, _ref([anc]), [rt1, rt2])
        stats = result["stats"]
        self.assertEqual(stats["anchor_points_considered"], 1)
        self.assertEqual(stats["redline_segments_total"], 2)
        self.assertEqual(
            stats["redline_segments_anchored"]
            + stats["redline_segments_unanchored"],
            stats["redline_segments_total"],
        )
        self.assertEqual(stats["anchor_points_with_groups"], len(result["groups"]))

    # ------------------------------------------------------------------
    # 15 — group schema keys present
    # ------------------------------------------------------------------

    def test_15_group_schema_keys(self) -> None:
        """Every emitted group must contain exactly the documented keys."""
        anc = _anchor()
        offset = 1.0 * _DEG_PER_FT
        rt = _route(start_lat=_BASE_LAT + offset, start_lon=_BASE_LON)
        result = _call([_seg()], _ref([anc]), [rt])
        self.assertEqual(len(result["groups"]), 1)
        g = result["groups"][0]
        self.assertTrue(
            EXPECTED_GROUP_KEYS.issubset(set(g.keys())),
            f"Missing keys: {EXPECTED_GROUP_KEYS - set(g.keys())}",
        )

    # ------------------------------------------------------------------
    # 16 — stability_note prefix lock
    # ------------------------------------------------------------------

    def test_16_stability_note_prefix(self) -> None:
        """stability_note must start with the expected prefix."""
        result = _call(None, None, None)
        note = result.get("stability_note", "")
        self.assertTrue(
            note.startswith(_STABILITY_NOTE_PREFIX),
            f"Expected prefix: {_STABILITY_NOTE_PREFIX!r}\nGot: {note!r}",
        )

    # ------------------------------------------------------------------
    # 17 — AST regression: operational helpers do not reference node advisor
    # ------------------------------------------------------------------

    def test_17_operational_helpers_do_not_reference_node_advisor(self) -> None:
        """No operational matching/scoring/billing helper references the node advisor.

        Reads main.py source at the AST level and asserts that the functions
        responsible for route selection, scoring, and operational workflows
        do NOT reference ``redline_node_continuity``.
        """
        import ast
        import inspect

        FORBIDDEN_CALLERS = [
            "_score_group",
            "_run_group_match",
            "_set_active_route",
            "_append_bore_log_row",
            "_choose_default_route",
        ]
        FORBIDDEN_TOKEN = "redline_node_continuity"

        source = inspect.getsource(main)
        try:
            tree = ast.parse(source)
        except SyntaxError:
            self.fail("main.py failed to parse as AST in regression test 17")

        # Collect line numbers of all references to the advisor key.
        advisor_lines: set = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value == FORBIDDEN_TOKEN:
                advisor_lines.add(node.lineno)
            elif isinstance(node, ast.Name) and node.id == FORBIDDEN_TOKEN:
                advisor_lines.add(node.lineno)

        for func_node in ast.walk(tree):
            if not isinstance(func_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if func_node.name not in FORBIDDEN_CALLERS:
                continue
            func_start = func_node.lineno
            func_end = max(
                (getattr(n, "lineno", func_start) for n in ast.walk(func_node)),
                default=func_start,
            )
            for adv_line in advisor_lines:
                if func_start <= adv_line <= func_end:
                    self.fail(
                        f"Regression: {func_node.name!r} references "
                        f"{FORBIDDEN_TOKEN!r} at line {adv_line}. "
                        f"This violates TOPOLOGY_SIDECAR_USAGE_POLICY.md. "
                        f"A policy review is required before proceeding."
                    )


if __name__ == "__main__":
    unittest.main()
