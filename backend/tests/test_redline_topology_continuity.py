"""Phase 1P — Redline topology continuity advisor lock-down suite.

14 tests for ``_build_redline_topology_continuity`` and
``get_redline_topology_continuity``, added in Phase 1P.

ISOLATION STRATEGY
------------------
Tests call ``_build_redline_topology_continuity`` directly with synthetic
in-memory dicts.  The endpoint is tested by monkeypatching ``main.STATE``.
The real STATE is restored in ``tearDown``.  No real KMZ I/O.

IF A TEST FAILS after a legitimate Phase 1P change:
  1. Confirm the change is intentional.
  2. Update the relevant assertion or fixture below.
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
# Schema lock constants
# ---------------------------------------------------------------------------
EXPECTED_TOP_KEYS_HELPER: frozenset = frozenset(
    {"schema_version", "groups", "ungrouped_segment_ids", "stability_note"}
)

EXPECTED_GROUP_KEYS: frozenset = frozenset(
    {"engineering_object_id", "signal", "source_segment_ids", "evidence"}
)

EXPECTED_EVIDENCE_KEYS: frozenset = frozenset(
    {"shared_group_id", "fragment_count"}
)

_STABILITY_NOTE_PREFIX = "redline-topology-continuity-1 groups existing redline"


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _redline_seg(
    segment_id: str = "route_1_redline_1_P1",
    matched_route_id: str = "route_1",
) -> Dict[str, Any]:
    return {
        "segment_id": segment_id,
        "matched_route_id": matched_route_id,
        "route_id": matched_route_id,
        "start_ft": 0.0,
        "end_ft": 500.0,
        "length_ft": 500.0,
    }


def _route_entry(
    route_id: str = "route_1",
    route_name: str = "Cable Run A",
    source_folder: str = "Zone1",
) -> Dict[str, Any]:
    return {
        "route_id": route_id,
        "route_name": route_name,
        "name": route_name,
        "source_folder": source_folder,
        "length_ft": 1000.0,
    }


def _ref_line(
    feature_id: str = "line_1",
    name: str = "Cable Run A",
    folder_path: str = "Zone1",
) -> Dict[str, Any]:
    return {
        "feature_id": feature_id,
        "name": name,
        "folder_path": folder_path,
        "role": "other",
        "coords": [[39.0, -98.0], [39.1, -98.1]],
        "stroke": "#10b981",
        "stroke_width": 3,
        "length_ft": 1000.0,
    }


def _ref_ingest(lines: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    return {"line_features": lines or [], "polygon_features": [], "point_features": []}


def _sidecar_entry(
    reference_feature_id: str = "line_1",
    multigeometry_group_id: Optional[str] = "semantic_1",
) -> Dict[str, Any]:
    return {
        "reference_feature_id": reference_feature_id,
        "semantic_feature_id": "semantic_1",
        "placemark_id": None,
        "folder_path": ["Zone1"],
        "multigeometry_group_id": multigeometry_group_id,
        "document_order": 1,
        "style_url": "#myStyle",
    }


def _sidecar(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "schema_version": "kmz-topology-sidecar-1",
        "entry_count": len(entries),
        "entries": entries,
        "join_stats": {
            "total_reference_features": len(entries),
            "matched_count": len(entries),
            "unmatched_count": 0,
            "multigeometry_group_count": 1,
        },
    }


def _call_helper(
    segs: Optional[List[Dict[str, Any]]],
    sc: Optional[Dict[str, Any]],
    routes: Optional[List[Dict[str, Any]]],
    ref: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    return main._build_redline_topology_continuity(segs, sc, routes, ref)


def _endpoint_result() -> Dict[str, Any]:
    response = main.get_redline_topology_continuity()
    return json.loads(response.body)


# ---------------------------------------------------------------------------
# Full join fixture: 3 redline segments from MultiGeometry placemark.
# route_1, route_2, route_3 all come from a MultiGeometry semantic_1.
# route_4 comes from a different placemark with no multigeometry_group_id.
# ---------------------------------------------------------------------------

def _full_join_fixture() -> tuple:
    """Returns (segs, sidecar, routes, ref_ingest) for a 3-fragment MultiGeometry test."""
    segs = [
        _redline_seg("seg_1", "route_1"),
        _redline_seg("seg_2", "route_2"),
        _redline_seg("seg_3", "route_3"),
        _redline_seg("seg_4", "route_4"),  # different placemark
    ]
    # All three routes come from line_features whose reference_feature_ids
    # map to the same multigeometry_group_id.
    sc = _sidecar([
        _sidecar_entry("line_1", "semantic_1"),
        _sidecar_entry("line_2", "semantic_1"),
        _sidecar_entry("line_3", "semantic_1"),
        _sidecar_entry("line_4", None),  # route_4 — no group
    ])
    # route_1,2,3 each have route_name = "Trunk Duct" but different folders
    # to simulate 3 fragments. Use same folder for simplicity.
    routes = [
        _route_entry("route_1", "Trunk Duct", "F1"),
        _route_entry("route_2", "Trunk Duct", "F1"),  # duplicate name+folder
        _route_entry("route_3", "Trunk Duct", "F1"),  # same
        _route_entry("route_4", "Other Cable", "F2"),
    ]
    ref = _ref_ingest([
        _ref_line("line_1", "Trunk Duct", "F1"),
        _ref_line("line_2", "Trunk Duct", "F1"),
        _ref_line("line_3", "Trunk Duct", "F1"),
        _ref_line("line_4", "Other Cable", "F2"),
    ])
    return segs, sc, routes, ref


# ---------------------------------------------------------------------------
# Test suite
# ---------------------------------------------------------------------------

class TestRedlineTopologyContinuity(unittest.TestCase):
    """Lock-down suite for Phase 1P redline topology continuity advisor."""

    def setUp(self) -> None:
        self._orig_rtc = main.STATE.get("redline_topology_continuity")
        self._orig_segs = main.STATE.get("redline_segments")

    def tearDown(self) -> None:
        main.STATE["redline_topology_continuity"] = self._orig_rtc
        main.STATE["redline_segments"] = self._orig_segs

    # ------------------------------------------------------------------
    # 01 — empty sidecar → all segments ungrouped
    # ------------------------------------------------------------------

    def test_01_empty_sidecar_all_ungrouped(self) -> None:
        """Empty sidecar → groups=[], all segment_ids in ungrouped_segment_ids."""
        segs = [_redline_seg("seg_1", "route_1"), _redline_seg("seg_2", "route_2")]
        result = _call_helper(segs, None, None, None)
        self.assertEqual(result["groups"], [])
        self.assertIn("seg_1", result["ungrouped_segment_ids"])
        self.assertIn("seg_2", result["ungrouped_segment_ids"])

    # ------------------------------------------------------------------
    # 02 — empty redlines → empty result
    # ------------------------------------------------------------------

    def test_02_empty_redlines_empty_result(self) -> None:
        """Empty redline_segments → groups=[], ungrouped_segment_ids=[]."""
        result = _call_helper([], _sidecar([_sidecar_entry()]), [], _ref_ingest())
        self.assertEqual(result["groups"], [])
        self.assertEqual(result["ungrouped_segment_ids"], [])

    # ------------------------------------------------------------------
    # 03 — schema lock: top-level key set
    # ------------------------------------------------------------------

    def test_03_schema_lock_top_level_keys(self) -> None:
        """Helper must return exactly the documented top-level keys."""
        result = _call_helper(None, None, None, None)
        self.assertEqual(frozenset(result.keys()), EXPECTED_TOP_KEYS_HELPER)

    # ------------------------------------------------------------------
    # 04 — schema lock: endpoint adds generated_at
    # ------------------------------------------------------------------

    def test_04_endpoint_schema_lock(self) -> None:
        """Endpoint must return exactly the documented top-level keys + generated_at."""
        main.STATE["redline_topology_continuity"] = None
        result = _endpoint_result()
        expected = EXPECTED_TOP_KEYS_HELPER | {"generated_at"}
        self.assertEqual(frozenset(result.keys()), expected)

    # ------------------------------------------------------------------
    # 05 — MultiGeometry grouping correctness (3 fragments → 1 group)
    # ------------------------------------------------------------------

    def test_05_multigeometry_grouping_correct(self) -> None:
        """3 route segments sharing a multigeometry_group_id are grouped together."""
        # Simplified fixture: 3 routes → same line_feature (same name+folder),
        # which maps to the same multigeometry_group_id.
        segs = [
            _redline_seg("seg_1", "route_1"),
            _redline_seg("seg_2", "route_2"),
            _redline_seg("seg_3", "route_3"),
        ]
        sc = _sidecar([_sidecar_entry("line_1", "semantic_1")])
        routes = [
            _route_entry("route_1", "Cable A", "F1"),
            _route_entry("route_2", "Cable A", "F1"),
            _route_entry("route_3", "Cable A", "F1"),
        ]
        ref = _ref_ingest([_ref_line("line_1", "Cable A", "F1")])
        result = _call_helper(segs, sc, routes, ref)
        self.assertEqual(len(result["groups"]), 1)
        grp = result["groups"][0]
        self.assertEqual(grp["engineering_object_id"], "semantic_1")
        self.assertEqual(grp["signal"], "multigeometry_group")
        self.assertCountEqual(grp["source_segment_ids"], ["seg_1", "seg_2", "seg_3"])
        self.assertEqual(grp["evidence"]["fragment_count"], 3)

    # ------------------------------------------------------------------
    # 06 — group entry key set
    # ------------------------------------------------------------------

    def test_06_group_entry_key_set(self) -> None:
        """Each group entry must have exactly the documented fields."""
        segs = [_redline_seg("seg_1", "route_1")]
        sc = _sidecar([_sidecar_entry("line_1", "semantic_1")])
        routes = [_route_entry("route_1", "Cable A", "F1")]
        ref = _ref_ingest([_ref_line("line_1", "Cable A", "F1")])
        result = _call_helper(segs, sc, routes, ref)
        self.assertEqual(len(result["groups"]), 1)
        grp = result["groups"][0]
        self.assertEqual(frozenset(grp.keys()), EXPECTED_GROUP_KEYS)
        self.assertEqual(frozenset(grp["evidence"].keys()), EXPECTED_EVIDENCE_KEYS)

    # ------------------------------------------------------------------
    # 07 — ungrouped fallback: segments with no MultiGeometry group
    # ------------------------------------------------------------------

    def test_07_ungrouped_fallback(self) -> None:
        """Segments from routes with no multigeometry_group_id → ungrouped."""
        segs = [_redline_seg("seg_1", "route_1"), _redline_seg("seg_2", "route_2")]
        sc = _sidecar([_sidecar_entry("line_1", None)])  # no group
        routes = [_route_entry("route_1"), _route_entry("route_2")]
        ref = _ref_ingest([_ref_line("line_1")])
        result = _call_helper(segs, sc, routes, ref)
        self.assertEqual(result["groups"], [])
        self.assertCountEqual(result["ungrouped_segment_ids"], ["seg_1", "seg_2"])

    # ------------------------------------------------------------------
    # 08 — deterministic ordering: groups sorted by engineering_object_id
    # ------------------------------------------------------------------

    def test_08_groups_sorted_deterministically(self) -> None:
        """Groups must be sorted by engineering_object_id regardless of input order."""
        segs = [
            _redline_seg("seg_1", "route_1"),
            _redline_seg("seg_2", "route_2"),
        ]
        sc = _sidecar([
            _sidecar_entry("line_1", "semantic_9"),  # would sort last
            _sidecar_entry("line_2", "semantic_2"),  # would sort first
        ])
        routes = [
            _route_entry("route_1", "Cable Z", "F1"),
            _route_entry("route_2", "Cable M", "F2"),
        ]
        ref = _ref_ingest([
            _ref_line("line_1", "Cable Z", "F1"),
            _ref_line("line_2", "Cable M", "F2"),
        ])
        result = _call_helper(segs, sc, routes, ref)
        group_ids = [g["engineering_object_id"] for g in result["groups"]]
        self.assertEqual(group_ids, sorted(group_ids))

    # ------------------------------------------------------------------
    # 09 — segment_ids within groups are sorted deterministically
    # ------------------------------------------------------------------

    def test_09_segment_ids_within_group_sorted(self) -> None:
        """source_segment_ids within each group must be sorted."""
        segs = [
            _redline_seg("seg_z", "route_1"),
            _redline_seg("seg_a", "route_2"),
            _redline_seg("seg_m", "route_3"),
        ]
        sc = _sidecar([
            _sidecar_entry("line_1", "semantic_1"),
        ])
        routes = [
            _route_entry("route_1", "Cable A", "F1"),
            _route_entry("route_2", "Cable A", "F1"),
            _route_entry("route_3", "Cable A", "F1"),
        ]
        ref = _ref_ingest([_ref_line("line_1", "Cable A", "F1")])
        result = _call_helper(segs, sc, routes, ref)
        self.assertEqual(len(result["groups"]), 1)
        ids = result["groups"][0]["source_segment_ids"]
        self.assertEqual(ids, sorted(ids))

    # ------------------------------------------------------------------
    # 10 — no mutation of redline_segments
    # ------------------------------------------------------------------

    def test_10_no_mutation_of_redline_segments(self) -> None:
        """Helper must not mutate the redline_segments list or any segment dict."""
        segs = [_redline_seg("seg_1", "route_1"), _redline_seg("seg_2", "route_2")]
        original_segs = [dict(s) for s in segs]
        sc = _sidecar([_sidecar_entry("line_1", "semantic_1")])
        routes = [_route_entry("route_1"), _route_entry("route_2")]
        ref = _ref_ingest([_ref_line("line_1")])
        _call_helper(segs, sc, routes, ref)
        # Verify the list wasn't modified.
        self.assertEqual(len(segs), len(original_segs))
        for i, (orig, current) in enumerate(zip(original_segs, segs)):
            self.assertEqual(orig, current, f"Segment {i} was mutated")

    # ------------------------------------------------------------------
    # 11 — graceful partial sidecar match
    # ------------------------------------------------------------------

    def test_11_graceful_partial_sidecar_match(self) -> None:
        """When sidecar covers only some routes, unmatched segments go to ungrouped."""
        segs = [
            _redline_seg("seg_1", "route_1"),  # matched
            _redline_seg("seg_2", "route_99"),  # no sidecar entry
        ]
        sc = _sidecar([_sidecar_entry("line_1", "semantic_1")])
        routes = [_route_entry("route_1"), _route_entry("route_99", "OtherCable", "FX")]
        ref = _ref_ingest([_ref_line("line_1"), _ref_line("line_99", "OtherCable", "FX")])
        result = _call_helper(segs, sc, routes, ref)
        grouped_ids = {sid for g in result["groups"] for sid in g["source_segment_ids"]}
        self.assertIn("seg_1", grouped_ids)
        self.assertIn("seg_2", result["ungrouped_segment_ids"])

    # ------------------------------------------------------------------
    # 12 — malformed inputs never raise
    # ------------------------------------------------------------------

    def test_12_malformed_inputs_never_raise(self) -> None:
        """Helper must not raise on any malformed input combination."""
        bad_cases: list = [
            (None, None, None, None),
            ([], {}, [], {}),
            ([None, "bad", 42], _sidecar([]), [], {}),
            ([_redline_seg()], {"entries": [None, "x"]}, None, None),
            ([_redline_seg()], _sidecar([_sidecar_entry()]), [None, "bad"], None),
        ]
        for segs, sc, routes, ref in bad_cases:
            try:
                result = _call_helper(segs, sc, routes, ref)
                self.assertIn("schema_version", result)
            except Exception as exc:
                self.fail(f"Helper raised on malformed input: {type(exc).__name__}: {exc}")

    # ------------------------------------------------------------------
    # 13 — stability_note prefix lock
    # ------------------------------------------------------------------

    def test_13_stability_note_prefix(self) -> None:
        """stability_note must start with the expected prefix."""
        result = _call_helper(None, None, None, None)
        note = result.get("stability_note", "")
        self.assertTrue(
            note.startswith(_STABILITY_NOTE_PREFIX),
            f"Expected prefix: {_STABILITY_NOTE_PREFIX!r}\nGot: {note!r}",
        )

    # ------------------------------------------------------------------
    # 14 — AST regression: operational helpers do not reference continuity advisor
    # ------------------------------------------------------------------

    def test_14_operational_helpers_do_not_reference_continuity_advisor(self) -> None:
        """No operational matching/scoring/redline/billing helper references the advisor.

        Reads main.py source at the AST level and asserts that the functions
        responsible for route selection, scoring, and operational workflows
        do NOT read ``redline_topology_continuity``.

        If this test fails, a policy review is required before proceeding.
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
        FORBIDDEN_TOKEN = "redline_topology_continuity"

        source = inspect.getsource(main)
        try:
            tree = ast.parse(source)
        except SyntaxError:
            self.fail("main.py failed to parse as AST in regression test 14")

        # Collect line numbers of all references to the advisor key.
        advisor_lines: set = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value == FORBIDDEN_TOKEN:
                advisor_lines.add(node.lineno)
            elif isinstance(node, ast.Name) and node.id == FORBIDDEN_TOKEN:
                advisor_lines.add(node.lineno)

        # Find the line ranges of each forbidden function.
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
                        f"A policy review is required before any operational use."
                    )


if __name__ == "__main__":
    unittest.main()
