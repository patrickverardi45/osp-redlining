"""Phase 1W — Reviewed Snapped Geometry Preview Layer lock-down suite.

33 tests for ``_build_reviewed_snap_preview`` and
``get_reviewed_snap_preview``.

ISOLATION STRATEGY
------------------
Tests call ``_build_reviewed_snap_preview`` directly with synthetic
in-memory dicts built to mirror operational STATE.  HTTP endpoint
behaviour is tested by monkeypatching ``main.STATE`` and
``main.SNAP_REVIEW_EVENTS_PATH``.  No real KMZ I/O.  No network calls.

Segment ``coords`` are in native [lat, lon] format (matching operational
pipeline).  Preview geometry is expected in GeoJSON [lon, lat] format.

REGRESSION ASSERTION
--------------------
test_33 verifies via AST analysis that operational helpers contain no
reference to the Phase 1W schema string, presentation_role, or builder.

IF A TEST FAILS after a legitimate Phase 1W change:
  1. Confirm the change is intentional.
  2. Update the relevant assertion or fixture below.
  3. Add a comment explaining why.
  DO NOT "fix to green" without understanding the failure.
"""

from __future__ import annotations

import ast
import hashlib
import json
import sys
import tempfile
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
    {"schema_version", "generated_at", "previews", "summary", "stability_note"}
)

EXPECTED_PREVIEW_KEYS: frozenset = frozenset(
    {
        "preview_id",
        "source_segment_id",
        "preview_geometry",
        "endpoint_substitutions",
        "operational_segment_checksum",
        "presentation_role",
    }
)

EXPECTED_GEOMETRY_KEYS: frozenset = frozenset({"type", "coordinates"})

EXPECTED_SUBSTITUTION_KEYS: frozenset = frozenset(
    {
        "approved_event_id",
        "recommendation_key",
        "original_coordinate",
        "substituted_coordinate",
        "candidate_anchor_id",
    }
)

EXPECTED_SUMMARY_KEYS: frozenset = frozenset(
    {
        "total_previews",
        "previews_with_start_only",
        "previews_with_end_only",
        "previews_with_both",
        "stale_previews",
    }
)

FORBIDDEN_PREVIEW_FIELDS: frozenset = frozenset(
    {
        "confidence",
        "score",
        "probability",
        "weight",
        "priority",
        "apply",
        "commit",
        "recommended",
        "final",
        "authoritative",
    }
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
# Segment coords are in native [lat, lon] format (as produced by route clipping).
# Three vertices: start, middle, end.
_SEG_COORDS_LAT_LON: List[List[float]] = [
    [30.1501, -96.4001],  # start
    [30.1510, -96.4010],  # middle (must stay byte-identical)
    [30.1520, -96.4020],  # end
]

# Candidate coordinates in [lon, lat] (GeoJSON / recommendations format).
_CAND_START_LON_LAT = [-96.4002, 30.1502]
_CAND_END_LON_LAT = [-96.4021, 30.1521]


def _make_segment(
    seg_id: str = "route_35_seg_0",
    coords: Optional[List[List[float]]] = None,
    route_id: str = "route_35",
) -> Dict[str, Any]:
    return {
        "segment_id": seg_id,
        "route_id": route_id,
        "matched_route_id": route_id,
        "coords": coords if coords is not None else [list(c) for c in _SEG_COORDS_LAT_LON],
    }


def _make_recommendation(
    seg_id: str = "route_35_seg_0",
    endpoint: str = "start",
    candidate_coord: Optional[List[float]] = None,
    anchor_id: str = "anchor_35_a",
    classification: str = "near",
) -> Dict[str, Any]:
    cand = candidate_coord or (
        _CAND_START_LON_LAT if endpoint == "start" else _CAND_END_LON_LAT
    )
    return {
        "segment_id": seg_id,
        "endpoint": endpoint,
        "route_id": seg_id.split("_seg_")[0],
        "current_coordinate": [-96.3999, 30.1499],
        "current_distance_ft": 5.3,
        "candidate_anchor_id": anchor_id,
        "candidate_anchor_name": f"HH-{anchor_id}",
        "candidate_coordinate": list(cand),
        "snap_delta_ft": 5.3,
        "classification": classification,
    }


def _make_snap_state(recs: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    r = recs if recs is not None else [
        _make_recommendation("route_35_seg_0", "start"),
        _make_recommendation("route_35_seg_0", "end"),
    ]
    return {
        "schema_version": "endpoint-snap-recommendation-1",
        "recommendations": r,
        "summary": {"total_recommendations": len(r)},
    }


def _inject_approval(seg_id: str, endpoint: str, decision: str = "approved") -> str:
    """Write an event to the monkeypatched SNAP_REVIEW_EVENTS_PATH."""
    # We need a live recommendation in STATE for POST validation; use _append directly.
    eid = main._append_snap_review_event(
        segment_id=seg_id,
        endpoint_label=endpoint,
        decision=decision,
        recommendation_snapshot={},
        operator_id="test",
        session_id=None,
    )
    return eid


def _sha256_coords(coords: List[List[float]]) -> str:
    return hashlib.sha256(
        json.dumps(coords, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


# ---------------------------------------------------------------------------
# Test suite
# ---------------------------------------------------------------------------


class TestReviewedSnapPreview(unittest.TestCase):
    """Lock-down suite for Phase 1W reviewed snap preview geometry."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._orig_events_path = main.SNAP_REVIEW_EVENTS_PATH
        self._orig_state = dict(main.STATE)

        main.SNAP_REVIEW_EVENTS_PATH = Path(self._tmpdir.name) / "snap_review_events.jsonl"

        # Default STATE: one segment with two recommendations.
        main.STATE["redline_segments"] = [_make_segment()]
        main.STATE["endpoint_snap_recommendations"] = _make_snap_state()

    def tearDown(self) -> None:
        main.SNAP_REVIEW_EVENTS_PATH = self._orig_events_path
        main.STATE.clear()
        main.STATE.update(self._orig_state)
        self._tmpdir.cleanup()

    # =========================================================================
    # Schema & Determinism
    # =========================================================================

    def test_01_schema_top_level_keys(self) -> None:
        segs = [_make_segment()]
        recs = _make_snap_state()
        result = main._build_reviewed_snap_preview(segs, recs)
        self.assertEqual(set(result.keys()), EXPECTED_TOP_KEYS)
        self.assertEqual(result["schema_version"], "reviewed-snap-preview-1")

    def test_02_preview_key_set(self) -> None:
        eid = _inject_approval("route_35_seg_0", "start")
        decisions = main._resolve_current_snap_review_decisions()
        result = main._build_reviewed_snap_preview(
            [_make_segment()], _make_snap_state(), decisions=decisions
        )
        self.assertEqual(len(result["previews"]), 1)
        self.assertEqual(set(result["previews"][0].keys()), EXPECTED_PREVIEW_KEYS)

    def test_03_geometry_key_set(self) -> None:
        _inject_approval("route_35_seg_0", "start")
        decisions = main._resolve_current_snap_review_decisions()
        result = main._build_reviewed_snap_preview(
            [_make_segment()], _make_snap_state(), decisions=decisions
        )
        geom = result["previews"][0]["preview_geometry"]
        self.assertEqual(set(geom.keys()), EXPECTED_GEOMETRY_KEYS)
        self.assertEqual(geom["type"], "LineString")

    def test_04_substitution_key_set(self) -> None:
        _inject_approval("route_35_seg_0", "start")
        decisions = main._resolve_current_snap_review_decisions()
        result = main._build_reviewed_snap_preview(
            [_make_segment()], _make_snap_state(), decisions=decisions
        )
        sub_start = result["previews"][0]["endpoint_substitutions"]["start"]
        self.assertIsNotNone(sub_start)
        self.assertEqual(set(sub_start.keys()), EXPECTED_SUBSTITUTION_KEYS)

    def test_05_summary_key_set(self) -> None:
        result = main._build_reviewed_snap_preview([_make_segment()], _make_snap_state())
        self.assertEqual(set(result["summary"].keys()), EXPECTED_SUMMARY_KEYS)

    def test_06_forbidden_fields_absent(self) -> None:
        _inject_approval("route_35_seg_0", "start")
        decisions = main._resolve_current_snap_review_decisions()
        result = main._build_reviewed_snap_preview(
            [_make_segment()], _make_snap_state(), decisions=decisions
        )
        for preview in result["previews"]:
            for forbidden in FORBIDDEN_PREVIEW_FIELDS:
                self.assertNotIn(forbidden, preview)

    def test_07_presentation_role_fixed(self) -> None:
        _inject_approval("route_35_seg_0", "start")
        decisions = main._resolve_current_snap_review_decisions()
        result = main._build_reviewed_snap_preview(
            [_make_segment()], _make_snap_state(), decisions=decisions
        )
        for p in result["previews"]:
            self.assertEqual(p["presentation_role"], "preview_polyline")

    def test_08_deterministic_preview_id(self) -> None:
        eid = _inject_approval("route_35_seg_0", "start")
        decisions = main._resolve_current_snap_review_decisions()
        r1 = main._build_reviewed_snap_preview(
            [_make_segment()], _make_snap_state(), decisions=decisions
        )
        r2 = main._build_reviewed_snap_preview(
            [_make_segment()], _make_snap_state(), decisions=decisions
        )
        self.assertEqual(r1["previews"][0]["preview_id"], r2["previews"][0]["preview_id"])
        self.assertEqual(len(r1["previews"][0]["preview_id"]), 16)

    # =========================================================================
    # Geometric Integrity
    # =========================================================================

    def test_09_coordinate_count_preserved(self) -> None:
        for ep in ["start", "end"]:
            _inject_approval("route_35_seg_0", ep)
        decisions = main._resolve_current_snap_review_decisions()
        result = main._build_reviewed_snap_preview(
            [_make_segment()], _make_snap_state(), decisions=decisions
        )
        self.assertEqual(len(result["previews"]), 1)
        self.assertEqual(
            len(result["previews"][0]["preview_geometry"]["coordinates"]),
            len(_SEG_COORDS_LAT_LON),
        )

    def test_10_non_endpoint_coordinates_byte_identical(self) -> None:
        for ep in ["start", "end"]:
            _inject_approval("route_35_seg_0", ep)
        decisions = main._resolve_current_snap_review_decisions()
        result = main._build_reviewed_snap_preview(
            [_make_segment()], _make_snap_state(), decisions=decisions
        )
        preview_coords = result["previews"][0]["preview_geometry"]["coordinates"]
        # Middle coordinate (index 1) must be byte-identical to operational.
        # Operational [lat, lon] → GeoJSON [lon, lat] for comparison.
        expected_middle = [_SEG_COORDS_LAT_LON[1][1], _SEG_COORDS_LAT_LON[1][0]]
        self.assertEqual(preview_coords[1], expected_middle)

    def test_11_substituted_start_byte_identical_to_candidate(self) -> None:
        _inject_approval("route_35_seg_0", "start")
        decisions = main._resolve_current_snap_review_decisions()
        result = main._build_reviewed_snap_preview(
            [_make_segment()], _make_snap_state(), decisions=decisions
        )
        preview_coords = result["previews"][0]["preview_geometry"]["coordinates"]
        self.assertEqual(preview_coords[0], _CAND_START_LON_LAT)

    def test_12_substituted_end_byte_identical_to_candidate(self) -> None:
        _inject_approval("route_35_seg_0", "end")
        decisions = main._resolve_current_snap_review_decisions()
        result = main._build_reviewed_snap_preview(
            [_make_segment()], _make_snap_state(), decisions=decisions
        )
        preview_coords = result["previews"][0]["preview_geometry"]["coordinates"]
        self.assertEqual(preview_coords[-1], _CAND_END_LON_LAT)

    def test_13_checksum_correctness(self) -> None:
        _inject_approval("route_35_seg_0", "start")
        decisions = main._resolve_current_snap_review_decisions()
        result = main._build_reviewed_snap_preview(
            [_make_segment()], _make_snap_state(), decisions=decisions
        )
        expected = _sha256_coords([list(c) for c in _SEG_COORDS_LAT_LON])
        self.assertEqual(result["previews"][0]["operational_segment_checksum"], expected)

    def test_14_two_vertex_segment_correct(self) -> None:
        two_pt = [[30.15, -96.40], [30.16, -96.41]]
        seg = _make_segment(coords=two_pt)
        _inject_approval("route_35_seg_0", "start")
        decisions = main._resolve_current_snap_review_decisions()
        result = main._build_reviewed_snap_preview(
            [seg], _make_snap_state(), decisions=decisions
        )
        coords = result["previews"][0]["preview_geometry"]["coordinates"]
        self.assertEqual(len(coords), 2)
        self.assertEqual(coords[0], _CAND_START_LON_LAT)
        # End unchanged (only start approved).
        self.assertEqual(coords[-1], [two_pt[1][1], two_pt[1][0]])

    # =========================================================================
    # Approval Gating
    # =========================================================================

    def test_15_no_preview_without_approval(self) -> None:
        result = main._build_reviewed_snap_preview(
            [_make_segment()], _make_snap_state()
        )
        self.assertEqual(result["previews"], [])
        self.assertEqual(result["summary"]["total_previews"], 0)

    def test_16_approved_start_only(self) -> None:
        _inject_approval("route_35_seg_0", "start")
        decisions = main._resolve_current_snap_review_decisions()
        result = main._build_reviewed_snap_preview(
            [_make_segment()], _make_snap_state(), decisions=decisions
        )
        self.assertEqual(len(result["previews"]), 1)
        subs = result["previews"][0]["endpoint_substitutions"]
        self.assertIsNotNone(subs["start"])
        self.assertIsNone(subs["end"])
        self.assertEqual(result["summary"]["previews_with_start_only"], 1)
        self.assertEqual(result["summary"]["previews_with_both"], 0)

    def test_17_approved_end_only(self) -> None:
        _inject_approval("route_35_seg_0", "end")
        decisions = main._resolve_current_snap_review_decisions()
        result = main._build_reviewed_snap_preview(
            [_make_segment()], _make_snap_state(), decisions=decisions
        )
        subs = result["previews"][0]["endpoint_substitutions"]
        self.assertIsNone(subs["start"])
        self.assertIsNotNone(subs["end"])
        self.assertEqual(result["summary"]["previews_with_end_only"], 1)

    def test_18_approved_both_endpoints(self) -> None:
        for ep in ["start", "end"]:
            _inject_approval("route_35_seg_0", ep)
        decisions = main._resolve_current_snap_review_decisions()
        result = main._build_reviewed_snap_preview(
            [_make_segment()], _make_snap_state(), decisions=decisions
        )
        subs = result["previews"][0]["endpoint_substitutions"]
        self.assertIsNotNone(subs["start"])
        self.assertIsNotNone(subs["end"])
        self.assertEqual(result["summary"]["previews_with_both"], 1)

    def test_19_rejected_event_ignored(self) -> None:
        _inject_approval("route_35_seg_0", "start", decision="rejected")
        decisions = main._resolve_current_snap_review_decisions()
        result = main._build_reviewed_snap_preview(
            [_make_segment()], _make_snap_state(), decisions=decisions
        )
        self.assertEqual(result["previews"], [])

    def test_20_revoked_removes_substitution(self) -> None:
        _inject_approval("route_35_seg_0", "start")
        _inject_approval("route_35_seg_0", "start", decision="revoked")
        decisions = main._resolve_current_snap_review_decisions()
        result = main._build_reviewed_snap_preview(
            [_make_segment()], _make_snap_state(), decisions=decisions
        )
        # Revoke clears approval → no preview.
        self.assertEqual(result["previews"], [])

    def test_21_revoke_downgrades_both_to_end_only(self) -> None:
        for ep in ["start", "end"]:
            _inject_approval("route_35_seg_0", ep)
        _inject_approval("route_35_seg_0", "start", decision="revoked")
        decisions = main._resolve_current_snap_review_decisions()
        result = main._build_reviewed_snap_preview(
            [_make_segment()], _make_snap_state(), decisions=decisions
        )
        self.assertEqual(len(result["previews"]), 1)
        subs = result["previews"][0]["endpoint_substitutions"]
        self.assertIsNone(subs["start"])
        self.assertIsNotNone(subs["end"])
        self.assertEqual(result["summary"]["previews_with_end_only"], 1)

    def test_22_stale_approval_counted_not_rendered(self) -> None:
        _inject_approval("nonexistent_seg", "start")
        decisions = main._resolve_current_snap_review_decisions()
        # No segment with that id.
        result = main._build_reviewed_snap_preview(
            [_make_segment()], _make_snap_state(), decisions=decisions
        )
        self.assertEqual(result["previews"], [])
        self.assertGreaterEqual(result["summary"]["stale_previews"], 1)

    # =========================================================================
    # Operational Isolation
    # =========================================================================

    def test_23_redline_segments_checksum_unchanged(self) -> None:
        _inject_approval("route_35_seg_0", "start")
        segs = [_make_segment()]
        before = hashlib.sha256(
            json.dumps(segs, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        decisions = main._resolve_current_snap_review_decisions()
        main._build_reviewed_snap_preview(segs, _make_snap_state(), decisions=decisions)
        after = hashlib.sha256(
            json.dumps(segs, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        self.assertEqual(before, after)

    def test_24_snap_recommendations_checksum_unchanged(self) -> None:
        _inject_approval("route_35_seg_0", "start")
        snap = _make_snap_state()
        before = hashlib.sha256(
            json.dumps(snap, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        decisions = main._resolve_current_snap_review_decisions()
        main._build_reviewed_snap_preview([_make_segment()], snap, decisions=decisions)
        after = hashlib.sha256(
            json.dumps(snap, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        self.assertEqual(before, after)

    def test_25_state_unchanged_after_endpoint_call(self) -> None:
        _inject_approval("route_35_seg_0", "start")
        main.STATE["route_catalog"] = [{"route_id": "route_35", "coords": []}]
        before_recs = hashlib.sha256(
            json.dumps(main.STATE.get("endpoint_snap_recommendations"),
                       sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        before_segs = hashlib.sha256(
            json.dumps(main.STATE.get("redline_segments"),
                       sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        before_cat = hashlib.sha256(
            json.dumps(main.STATE.get("route_catalog"),
                       sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        main.get_reviewed_snap_preview()
        self.assertEqual(before_recs, hashlib.sha256(
            json.dumps(main.STATE.get("endpoint_snap_recommendations"),
                       sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest())
        self.assertEqual(before_segs, hashlib.sha256(
            json.dumps(main.STATE.get("redline_segments"),
                       sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest())
        self.assertEqual(before_cat, hashlib.sha256(
            json.dumps(main.STATE.get("route_catalog"),
                       sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest())

    # =========================================================================
    # Failure Tolerance
    # =========================================================================

    def test_26_empty_segments_safe(self) -> None:
        result = main._build_reviewed_snap_preview([], _make_snap_state())
        self.assertEqual(result["previews"], [])

    def test_27_none_inputs_safe(self) -> None:
        result = main._build_reviewed_snap_preview(None, None)
        self.assertEqual(result["previews"], [])
        self.assertEqual(result["schema_version"], "reviewed-snap-preview-1")

    def test_28_malformed_segments_safe(self) -> None:
        for bad in [None, "string", 42, {}, []]:
            result = main._build_reviewed_snap_preview(bad, _make_snap_state())  # type: ignore[arg-type]
            self.assertEqual(result["previews"], [])

    def test_29_segment_with_bad_coords_counts_stale(self) -> None:
        bad_seg = _make_segment(coords=[[1]])  # one coord, malformed
        _inject_approval("route_35_seg_0", "start")
        decisions = main._resolve_current_snap_review_decisions()
        result = main._build_reviewed_snap_preview(
            [bad_seg], _make_snap_state(), decisions=decisions
        )
        self.assertEqual(result["previews"], [])

    # =========================================================================
    # Brenham Smoke Tests
    # =========================================================================

    def test_30_brenham_approve_start_only_one_preview(self) -> None:
        _inject_approval("route_35_seg_0", "start")
        decisions = main._resolve_current_snap_review_decisions()
        result = main._build_reviewed_snap_preview(
            [_make_segment()], _make_snap_state(), decisions=decisions
        )
        self.assertEqual(len(result["previews"]), 1)
        subs = result["previews"][0]["endpoint_substitutions"]
        self.assertIsNotNone(subs["start"])
        self.assertIsNone(subs["end"])

    def test_31_brenham_approve_both_one_preview_both_substituted(self) -> None:
        for ep in ["start", "end"]:
            _inject_approval("route_35_seg_0", ep)
        decisions = main._resolve_current_snap_review_decisions()
        result = main._build_reviewed_snap_preview(
            [_make_segment()], _make_snap_state(), decisions=decisions
        )
        self.assertEqual(len(result["previews"]), 1)
        subs = result["previews"][0]["endpoint_substitutions"]
        self.assertIsNotNone(subs["start"])
        self.assertIsNotNone(subs["end"])
        coords = result["previews"][0]["preview_geometry"]["coordinates"]
        self.assertEqual(len(coords), len(_SEG_COORDS_LAT_LON))

    def test_32_brenham_three_routes_three_previews(self) -> None:
        segs = []
        recs = []
        for rid in ["route_35", "route_459", "route_476"]:
            seg_id = f"{rid}_seg_0"
            segs.append(_make_segment(seg_id=seg_id, route_id=rid))
            recs.append(_make_recommendation(seg_id, "start",
                                              anchor_id=f"anchor_{rid}"))
            recs.append(_make_recommendation(seg_id, "end",
                                              anchor_id=f"anchor_{rid}_end"))
            _inject_approval(seg_id, "start")
        decisions = main._resolve_current_snap_review_decisions()
        snap = _make_snap_state(recs=recs)
        result = main._build_reviewed_snap_preview(segs, snap, decisions=decisions)
        self.assertEqual(result["summary"]["total_previews"], 3)
        self.assertEqual(result["summary"]["previews_with_start_only"], 3)

    # =========================================================================
    # AST Regression
    # =========================================================================

    def test_33_ast_operational_helpers_do_not_reference_preview(self) -> None:
        src = (_BACKEND_DIR / "main.py").read_text(encoding="utf-8")
        tree = ast.parse(src)

        OPERATIONAL_HELPERS = frozenset(
            {
                "_rebuild_field_data_outputs",
                "_build_redline_node_continuity",
                "_build_redline_topology_continuity",
                "_build_kmz_topology_sidecar",
                "_build_redline_endpoint_validation",
                "_build_endpoint_snap_recommendations",
                "_build_kmz_semantic",
                "_build_kmz_reference",
                "_build_snap_preview_markers",
            }
        )

        FORBIDDEN_REFERENCES = frozenset(
            {
                "_build_reviewed_snap_preview",
                "reviewed-snap-preview-1",
                "preview_polyline",
                "_REVIEWED_SNAP_PREVIEW_STABILITY_NOTE",
            }
        )

        violations: List[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name not in OPERATIONAL_HELPERS:
                continue
            for child in ast.walk(node):
                name: Optional[str] = None
                if isinstance(child, ast.Name):
                    name = child.id
                elif isinstance(child, ast.Attribute):
                    name = child.attr
                elif isinstance(child, ast.Constant) and isinstance(child.value, str):
                    name = child.value
                if name and any(f in name for f in FORBIDDEN_REFERENCES):
                    violations.append(f"{node.name} references '{name}'")

        self.assertEqual(
            violations, [],
            f"Operational helpers reference Phase 1W: {violations}",
        )


if __name__ == "__main__":
    unittest.main()
