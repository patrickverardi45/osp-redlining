"""Phase 1O — KMZ topology sidecar lock-down suite.

14 tests for ``_build_kmz_topology_sidecar`` and ``get_kmz_topology_sidecar``,
added in Phase 1O.

ISOLATION STRATEGY
------------------
Tests call ``_build_kmz_topology_sidecar`` directly with synthetic in-memory
dicts.  ``get_kmz_topology_sidecar`` is tested by monkeypatching ``main.STATE``
with controlled values.  No real KMZ file I/O.  The real STATE is restored
in ``tearDown``.

IF A TEST FAILS after a legitimate Phase 1O change:
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
# Exact top-level key set — schema lock (endpoint adds "generated_at").
# ---------------------------------------------------------------------------
EXPECTED_TOP_KEYS_HELPER: frozenset = frozenset(
    {
        "schema_version",
        "entry_count",
        "entries",
        "join_stats",
        "stability_note",
    }
)

EXPECTED_ENTRY_KEYS: frozenset = frozenset(
    {
        "reference_feature_id",
        "semantic_feature_id",
        "placemark_id",
        "folder_path",
        "multigeometry_group_id",
        "document_order",
        "style_url",
    }
)

EXPECTED_JOIN_STAT_KEYS: frozenset = frozenset(
    {
        "total_reference_features",
        "matched_count",
        "unmatched_count",
        "multigeometry_group_count",
    }
)

_STABILITY_NOTE_PREFIX = "kmz-topology-sidecar-1 records best-effort topology"


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _sem_feature(
    placemark_name: str = "Cable Run 1",
    folder_path: Optional[List[str]] = None,
    folder_path_str: str = "",
    geometry_type: str = "LineString",
    style_url: str = "#myStyle",
    placemark_id: Optional[str] = None,
    feature_id: str = "semantic_1",
) -> Dict[str, Any]:
    return {
        "feature_id": feature_id,
        "placemark_id": placemark_id,
        "placemark_name": placemark_name,
        "folder_path": folder_path if folder_path is not None else ["Root", "Sub"],
        "folder_path_str": folder_path_str or "Root / Sub",
        "geometry_type": geometry_type,
        "style_url": style_url,
        "extended_data": {},
        "classification": "route_segment",
        "confidence": "low",
    }


def _sem_ingest(features: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {"features": features, "index": {}}


def _ref_line(
    name: str = "Cable Run 1",
    folder_path: str = "Root / Sub",
    feature_id: str = "line_1",
) -> Dict[str, Any]:
    return {
        "feature_id": feature_id,
        "name": name,
        "folder_path": folder_path,
        "role": "other",
        "coords": [[39.0, -98.0], [39.1, -98.1]],
        "stroke": "#10b981",
        "stroke_width": 3,
        "length_ft": 500.0,
    }


def _ref_point(
    name: str = "HH-001",
    folder_path: str = "Root",
    feature_id: str = "point_2",
) -> Dict[str, Any]:
    return {
        "feature_id": feature_id,
        "name": name,
        "folder_path": folder_path,
        "role": "other",
        "lat": 39.0,
        "lon": -98.0,
    }


def _ref_ingest(
    lines: Optional[List[Dict[str, Any]]] = None,
    polys: Optional[List[Dict[str, Any]]] = None,
    points: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    return {
        "line_features": lines or [],
        "polygon_features": polys or [],
        "point_features": points or [],
    }


def _call_helper(
    semantic: Optional[Dict[str, Any]],
    reference: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    return main._build_kmz_topology_sidecar(semantic, reference)


def _endpoint_sidecar() -> Dict[str, Any]:
    response = main.get_kmz_topology_sidecar()
    return json.loads(response.body)


# ---------------------------------------------------------------------------
# Test suite
# ---------------------------------------------------------------------------

class TestKmzTopologySidecar(unittest.TestCase):
    """Lock-down suite for Phase 1O KMZ topology sidecar."""

    def setUp(self) -> None:
        self._orig_sidecar = main.STATE.get("kmz_topology_sidecar")

    def tearDown(self) -> None:
        main.STATE["kmz_topology_sidecar"] = self._orig_sidecar

    # ------------------------------------------------------------------
    # 01 — both inputs None → valid empty skeleton
    # ------------------------------------------------------------------

    def test_01_both_none_returns_skeleton(self) -> None:
        """Both inputs None → empty skeleton with correct schema_version."""
        result = _call_helper(None, None)
        self.assertEqual(result["schema_version"], "kmz-topology-sidecar-1")
        self.assertEqual(result["entry_count"], 0)
        self.assertEqual(result["entries"], [])
        self.assertEqual(result["join_stats"]["total_reference_features"], 0)

    # ------------------------------------------------------------------
    # 02 — endpoint schema lock: top-level key set
    # ------------------------------------------------------------------

    def test_02_endpoint_schema_lock(self) -> None:
        """Endpoint must return exactly the documented top-level keys."""
        main.STATE["kmz_topology_sidecar"] = None
        result = _endpoint_sidecar()
        # Endpoint adds "generated_at" to the helper keys.
        expected = EXPECTED_TOP_KEYS_HELPER | {"generated_at"}
        self.assertEqual(frozenset(result.keys()), expected)

    # ------------------------------------------------------------------
    # 03 — each entry has exactly the 7 documented fields
    # ------------------------------------------------------------------

    def test_03_entry_key_set(self) -> None:
        """Every entry must have exactly the 7 documented fields."""
        sem = _sem_ingest([_sem_feature()])
        ref = _ref_ingest(lines=[_ref_line()])
        result = _call_helper(sem, ref)
        self.assertEqual(result["entry_count"], 1)
        entry = result["entries"][0]
        self.assertEqual(frozenset(entry.keys()), EXPECTED_ENTRY_KEYS)

    # ------------------------------------------------------------------
    # 04 — folder_path is preserved as array
    # ------------------------------------------------------------------

    def test_04_folder_path_preserved_as_array(self) -> None:
        """folder_path in sidecar entry must be a list, not a string."""
        sem = _sem_ingest([
            _sem_feature(folder_path=["Root", "Sub", "L3"], folder_path_str="Root / Sub / L3")
        ])
        ref = _ref_ingest(lines=[_ref_line(folder_path="Root / Sub / L3")])
        result = _call_helper(sem, ref)
        self.assertEqual(result["entry_count"], 1)
        fp = result["entries"][0]["folder_path"]
        self.assertIsInstance(fp, list)
        self.assertEqual(fp, ["Root", "Sub", "L3"])

    # ------------------------------------------------------------------
    # 05 — MultiGeometry group ID assigned to all matched fragments
    # ------------------------------------------------------------------

    def test_05_multigeometry_group_id(self) -> None:
        """Multiple reference features from a MultiGeometry placemark get same group_id."""
        sem_f = _sem_feature(
            placemark_name="Trunk Duct",
            folder_path_str="Zone1",
            geometry_type="MultiGeometry",
            feature_id="semantic_1",
        )
        sem_f["folder_path"] = ["Zone1"]
        sem = _sem_ingest([sem_f])
        ref = _ref_ingest(lines=[
            _ref_line(name="Trunk Duct", folder_path="Zone1", feature_id="line_1"),
            _ref_line(name="Trunk Duct", folder_path="Zone1", feature_id="line_2"),
        ])
        result = _call_helper(sem, ref)
        self.assertEqual(result["entry_count"], 2)
        gids = {e["multigeometry_group_id"] for e in result["entries"]}
        self.assertEqual(gids, {"semantic_1"})
        self.assertEqual(result["join_stats"]["multigeometry_group_count"], 1)

    # ------------------------------------------------------------------
    # 06 — non-MultiGeometry features have multigeometry_group_id = None
    # ------------------------------------------------------------------

    def test_06_non_multigeometry_group_id_is_none(self) -> None:
        """LineString features must have multigeometry_group_id = None."""
        sem = _sem_ingest([_sem_feature(geometry_type="LineString")])
        ref = _ref_ingest(lines=[_ref_line()])
        result = _call_helper(sem, ref)
        self.assertIsNone(result["entries"][0]["multigeometry_group_id"])

    # ------------------------------------------------------------------
    # 07 — document_order is monotonically correct
    # ------------------------------------------------------------------

    def test_07_document_order_monotonic(self) -> None:
        """document_order reflects 1-based position in semantic.features list."""
        sf1 = _sem_feature(placemark_name="A", folder_path_str="F1", feature_id="semantic_1")
        sf1["folder_path"] = ["F1"]
        sf2 = _sem_feature(placemark_name="B", folder_path_str="F2", feature_id="semantic_2")
        sf2["folder_path"] = ["F2"]
        sem = _sem_ingest([sf1, sf2])
        ref = _ref_ingest(lines=[
            _ref_line(name="A", folder_path="F1", feature_id="line_1"),
            _ref_line(name="B", folder_path="F2", feature_id="line_2"),
        ])
        result = _call_helper(sem, ref)
        orders = {e["reference_feature_id"]: e["document_order"] for e in result["entries"]}
        self.assertEqual(orders["line_1"], 1)
        self.assertEqual(orders["line_2"], 2)

    # ------------------------------------------------------------------
    # 08 — placemark_id passthrough when present
    # ------------------------------------------------------------------

    def test_08_placemark_id_passthrough(self) -> None:
        """placemark_id from semantic feature passes through to entry."""
        sem = _sem_ingest([
            _sem_feature(placemark_id="PLM-007", feature_id="semantic_1")
        ])
        ref = _ref_ingest(lines=[_ref_line()])
        result = _call_helper(sem, ref)
        self.assertEqual(result["entries"][0]["placemark_id"], "PLM-007")

    # ------------------------------------------------------------------
    # 09 — placemark_id is None when not set in semantic
    # ------------------------------------------------------------------

    def test_09_placemark_id_none_when_absent(self) -> None:
        """placemark_id is None when semantic feature has no placemark_id."""
        sem = _sem_ingest([_sem_feature(placemark_id=None)])
        ref = _ref_ingest(lines=[_ref_line()])
        result = _call_helper(sem, ref)
        self.assertIsNone(result["entries"][0]["placemark_id"])

    # ------------------------------------------------------------------
    # 10 — unmatched reference features have None for all semantic fields
    # ------------------------------------------------------------------

    def test_10_unmatched_reference_features_safe(self) -> None:
        """Reference features with no semantic match have all semantic fields as None."""
        sem = _sem_ingest([_sem_feature(placemark_name="SomeOtherName")])
        ref = _ref_ingest(lines=[_ref_line(name="NoMatchHere", folder_path="")])
        result = _call_helper(sem, ref)
        self.assertEqual(result["entry_count"], 1)
        e = result["entries"][0]
        self.assertIsNone(e["semantic_feature_id"])
        self.assertIsNone(e["placemark_id"])
        self.assertIsNone(e["folder_path"])
        self.assertIsNone(e["multigeometry_group_id"])
        self.assertIsNone(e["document_order"])
        self.assertIsNone(e["style_url"])
        self.assertEqual(result["join_stats"]["unmatched_count"], 1)
        self.assertEqual(result["join_stats"]["matched_count"], 0)

    # ------------------------------------------------------------------
    # 11 — join_stats counts correct
    # ------------------------------------------------------------------

    def test_11_join_stats_counts(self) -> None:
        """join_stats: matched + unmatched == total_reference_features."""
        sf = _sem_feature(placemark_name="Match", folder_path_str="F1")
        sf["folder_path"] = ["F1"]
        sem = _sem_ingest([sf])
        ref = _ref_ingest(lines=[
            _ref_line(name="Match", folder_path="F1", feature_id="line_1"),
            _ref_line(name="NoMatch", folder_path="F2", feature_id="line_2"),
        ])
        result = _call_helper(sem, ref)
        js = result["join_stats"]
        self.assertEqual(js["total_reference_features"], 2)
        self.assertEqual(js["matched_count"], 1)
        self.assertEqual(js["unmatched_count"], 1)
        self.assertEqual(js["matched_count"] + js["unmatched_count"], js["total_reference_features"])

    # ------------------------------------------------------------------
    # 12 — malformed inputs never raise
    # ------------------------------------------------------------------

    def test_12_malformed_inputs_never_raise(self) -> None:
        """Helper must not raise on any malformed input."""
        bad_cases: list = [
            (None, None),
            ({}, {}),
            ({"features": None}, {"line_features": None}),
            ({"features": [None, "str", 42]}, _ref_ingest()),
            (_sem_ingest([_sem_feature()]), {"line_features": [None, "bad", 42]}),
        ]
        for sem, ref in bad_cases:
            try:
                result = _call_helper(sem, ref)
                self.assertIn("schema_version", result)
            except Exception as exc:
                self.fail(f"Helper raised on malformed input: {type(exc).__name__}: {exc}")

    # ------------------------------------------------------------------
    # 13 — stability_note prefix lock
    # ------------------------------------------------------------------

    def test_13_stability_note_prefix(self) -> None:
        """stability_note must start with the expected prefix."""
        result = _call_helper(None, None)
        note = result.get("stability_note", "")
        self.assertTrue(
            note.startswith(_STABILITY_NOTE_PREFIX),
            f"stability_note does not match expected prefix.\n"
            f"Expected prefix: {_STABILITY_NOTE_PREFIX!r}\nGot: {note!r}",
        )

    # ------------------------------------------------------------------
    # 14 — regression: no operational helpers reference kmz_topology_sidecar
    # ------------------------------------------------------------------

    def test_14_operational_helpers_do_not_reference_sidecar(self) -> None:
        """No operational matching/scoring/redline helpers must reference kmz_topology_sidecar.

        This test reads main.py source and asserts that the functions
        responsible for route selection, scoring, and redline construction
        do NOT call or reference the sidecar key.

        If this test fails, a policy review is required before proceeding.
        """
        import ast
        import inspect

        # Functions that are strictly forbidden from touching the sidecar.
        # NOTE: _rebuild_field_data_outputs is intentionally excluded from this
        # list because Phase 1P legitimately reads kmz_topology_sidecar at the
        # very end of that function — AFTER all operational STATE writes are
        # complete — solely to pass it to _build_redline_topology_continuity.
        # This is a documented, policy-compliant use: the sidecar read cannot
        # influence matching, scoring, or route activation decisions because it
        # occurs after they are all final.  See TOPOLOGY_SIDECAR_USAGE_POLICY.md.
        FORBIDDEN_CALLERS = [
            "_score_group",
            "_run_group_match",
            "_set_active_route",
            "_append_bore_log_row",
            "_choose_default_route",
        ]
        FORBIDDEN_TOKEN = "kmz_topology_sidecar"

        source = inspect.getsource(main)
        try:
            tree = ast.parse(source)
        except SyntaxError:
            self.fail("main.py failed to parse as AST in regression test 14")

        # Collect line numbers of all references to the sidecar key.
        sidecar_lines: set = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value == FORBIDDEN_TOKEN:
                sidecar_lines.add(node.lineno)
            elif isinstance(node, ast.Name) and node.id == FORBIDDEN_TOKEN:
                sidecar_lines.add(node.lineno)

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
            for sidecar_line in sidecar_lines:
                if func_start <= sidecar_line <= func_end:
                    self.fail(
                        f"Regression: {func_node.name!r} references "
                        f"{FORBIDDEN_TOKEN!r} at line {sidecar_line}. "
                        f"This violates TOPOLOGY_SIDECAR_USAGE_POLICY.md. "
                        f"A policy review is required before any operational use of the sidecar."
                    )


if __name__ == "__main__":
    unittest.main()
