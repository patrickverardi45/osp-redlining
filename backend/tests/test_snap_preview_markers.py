"""Phase 1V — Endpoint-Only Snap Preview Markers lock-down suite.

26 tests for ``_build_snap_preview_markers`` and
``get_snap_preview_markers``, added in Phase 1V.

ISOLATION STRATEGY
------------------
Tests call ``_build_snap_preview_markers`` directly with synthetic
in-memory dicts that mirror the Phase 1T output shape.  HTTP endpoint
behaviour is tested by monkeypatching ``main.STATE`` and
``main.SNAP_REVIEW_EVENTS_PATH``.  No real KMZ I/O.  No network calls.

REGRESSION ASSERTION
--------------------
test_26 verifies via AST analysis that operational helpers do not
reference snap preview marker functions.  If that test fails after a
code change, investigate before proceeding.

IF A TEST FAILS after a legitimate Phase 1V change:
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
# Schema lock — exact key set produced by _build_snap_preview_markers.
# ---------------------------------------------------------------------------
EXPECTED_TOP_KEYS: frozenset = frozenset(
    {
        "schema_version",
        "generated_at",
        "markers",
        "summary",
        "stability_note",
    }
)

EXPECTED_MARKER_KEYS: frozenset = frozenset(
    {
        "marker_id",
        "segment_id",
        "endpoint",
        "current_coordinate",
        "candidate_coordinate",
        "candidate_anchor_id",
        "candidate_anchor_name",
        "snap_delta_ft",
        "classification",
        "current_decision",
        "presentation_role",
    }
)

EXPECTED_SUMMARY_KEYS: frozenset = frozenset(
    {
        "total_markers",
        "near_markers",
        "orphan_markers",
        "with_decision",
        "without_decision",
    }
)

# Forbidden fields per Phase 1V architecture decision.
FORBIDDEN_MARKER_FIELDS: frozenset = frozenset(
    {
        "confidence",
        "score",
        "probability",
        "weight",
        "priority",
        "recommended_geometry",
        "preview_line",
        "polyline",
    }
)

# ---------------------------------------------------------------------------
# Brenham-style fixture (mirrors Phase 1T-RealData verified output).
# ---------------------------------------------------------------------------
def _make_recommendation(
    seg: str,
    ep: str,
    route_id: str,
    classification: str = "near",
    delta: float = 5.5,
    anchor_id: Optional[str] = None,
    anchor_name: Optional[str] = None,
    candidate_lon: float = -96.4002,
    candidate_lat: float = 30.1502,
) -> Dict[str, Any]:
    return {
        "segment_id": seg,
        "endpoint": ep,
        "route_id": route_id,
        "current_coordinate": [candidate_lon - 0.0001, candidate_lat - 0.0001],
        "current_distance_ft": delta,
        "candidate_anchor_id": anchor_id or f"anchor_{seg}_{ep}",
        "candidate_anchor_name": anchor_name,
        "candidate_coordinate": [candidate_lon, candidate_lat],
        "snap_delta_ft": delta,
        "classification": classification,
    }


def _brenham_19_recommendations() -> List[Dict[str, Any]]:
    """Build a fixture of 19 recommendations matching Brenham real-data shape:
    16 'near' + 3 'orphan'; route_35/459/476 each contribute 2."""
    recs: List[Dict[str, Any]] = []
    # Routes 35, 459, 476 each contribute 2 near recommendations (start + end).
    for rid in ["route_35", "route_459", "route_476"]:
        for ep, delta in [("start", 5.3), ("end", 8.7)]:
            recs.append(
                _make_recommendation(
                    seg=f"{rid}_seg_0",
                    ep=ep,
                    route_id=rid,
                    classification="near",
                    delta=delta,
                    anchor_name=f"HH-{rid[-3:]}-{ep[0].upper()}",
                )
            )
    # 10 more near recommendations across other routes.
    for i in range(10):
        recs.append(
            _make_recommendation(
                seg=f"route_other_{i}_seg_0",
                ep="start",
                route_id=f"route_other_{i}",
                classification="near",
                delta=5.0 + (i * 0.3),
                candidate_lon=-96.4100 - (i * 0.001),
                candidate_lat=30.1600 + (i * 0.001),
            )
        )
    # 3 orphan recommendations.
    for i in range(3):
        recs.append(
            _make_recommendation(
                seg=f"route_orphan_{i}_seg_0",
                ep="start",
                route_id=f"route_orphan_{i}",
                classification="orphan",
                delta=55.0 + (i * 5.0),
                candidate_lon=-96.5000 - (i * 0.01),
                candidate_lat=30.2000 + (i * 0.01),
            )
        )
    return recs


def _make_snap_state(recs: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    r = recs if recs is not None else _brenham_19_recommendations()
    return {
        "schema_version": "endpoint-snap-recommendation-1",
        "recommendations": r,
        "summary": {
            "total_recommendations": len(r),
            "near_recommendations": sum(1 for x in r if x.get("classification") == "near"),
            "orphan_recommendations": sum(1 for x in r if x.get("classification") == "orphan"),
        },
    }


def _expected_marker_id(seg: str, ep: str) -> str:
    return hashlib.sha1(f"{seg}|{ep}".encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Test suite
# ---------------------------------------------------------------------------


class TestSnapPreviewMarkers(unittest.TestCase):
    """Lock-down suite for Phase 1V snap-preview-marker derivation."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._orig_events_path = main.SNAP_REVIEW_EVENTS_PATH
        self._orig_state = dict(main.STATE)
        main.SNAP_REVIEW_EVENTS_PATH = Path(self._tmpdir.name) / "snap_review_events.jsonl"
        main.STATE["endpoint_snap_recommendations"] = _make_snap_state()

    def tearDown(self) -> None:
        main.SNAP_REVIEW_EVENTS_PATH = self._orig_events_path
        main.STATE.clear()
        main.STATE.update(self._orig_state)
        self._tmpdir.cleanup()

    # ------------------------------------------------------------------
    # 01 — schema lock: top-level keys
    # ------------------------------------------------------------------

    def test_01_schema_top_level_keys(self) -> None:
        result = main._build_snap_preview_markers(_make_snap_state())
        self.assertEqual(set(result.keys()), EXPECTED_TOP_KEYS)
        self.assertEqual(result["schema_version"], "snap-preview-marker-1")

    # ------------------------------------------------------------------
    # 02 — schema lock: marker keys
    # ------------------------------------------------------------------

    def test_02_marker_key_set(self) -> None:
        result = main._build_snap_preview_markers(_make_snap_state())
        for marker in result["markers"]:
            self.assertEqual(set(marker.keys()), EXPECTED_MARKER_KEYS)

    # ------------------------------------------------------------------
    # 03 — schema lock: summary keys
    # ------------------------------------------------------------------

    def test_03_summary_key_set(self) -> None:
        result = main._build_snap_preview_markers(_make_snap_state())
        self.assertEqual(set(result["summary"].keys()), EXPECTED_SUMMARY_KEYS)

    # ------------------------------------------------------------------
    # 04 — forbidden field absence
    # ------------------------------------------------------------------

    def test_04_forbidden_fields_absent(self) -> None:
        result = main._build_snap_preview_markers(_make_snap_state())
        for marker in result["markers"]:
            for forbidden in FORBIDDEN_MARKER_FIELDS:
                self.assertNotIn(
                    forbidden,
                    marker,
                    f"Forbidden field '{forbidden}' present in marker",
                )

    # ------------------------------------------------------------------
    # 05 — deterministic marker_id
    # ------------------------------------------------------------------

    def test_05_deterministic_marker_id(self) -> None:
        recs = [_make_recommendation("route_35_seg_0", "start", "route_35")]
        result = main._build_snap_preview_markers({"recommendations": recs})
        self.assertEqual(len(result["markers"]), 1)
        self.assertEqual(
            result["markers"][0]["marker_id"],
            _expected_marker_id("route_35_seg_0", "start"),
        )

    # ------------------------------------------------------------------
    # 06 — marker_id is 16 hex chars
    # ------------------------------------------------------------------

    def test_06_marker_id_length(self) -> None:
        result = main._build_snap_preview_markers(_make_snap_state())
        for marker in result["markers"]:
            self.assertEqual(len(marker["marker_id"]), 16)
            int(marker["marker_id"], 16)  # must be valid hex

    # ------------------------------------------------------------------
    # 07 — marker count == recommendation count
    # ------------------------------------------------------------------

    def test_07_marker_count_matches_recommendations(self) -> None:
        snap_state = _make_snap_state()
        result = main._build_snap_preview_markers(snap_state)
        self.assertEqual(len(result["markers"]), len(snap_state["recommendations"]))
        self.assertEqual(result["summary"]["total_markers"], 19)

    # ------------------------------------------------------------------
    # 08 — byte-identical candidate_coordinate
    # ------------------------------------------------------------------

    def test_08_candidate_coordinate_byte_identical(self) -> None:
        snap_state = _make_snap_state()
        result = main._build_snap_preview_markers(snap_state)
        for rec, marker in zip(snap_state["recommendations"], result["markers"]):
            self.assertEqual(
                marker["candidate_coordinate"],
                rec["candidate_coordinate"],
                "marker.candidate_coordinate diverged from recommendation",
            )

    # ------------------------------------------------------------------
    # 09 — byte-identical current_coordinate
    # ------------------------------------------------------------------

    def test_09_current_coordinate_byte_identical(self) -> None:
        snap_state = _make_snap_state()
        result = main._build_snap_preview_markers(snap_state)
        for rec, marker in zip(snap_state["recommendations"], result["markers"]):
            self.assertEqual(
                marker["current_coordinate"],
                rec["current_coordinate"],
            )

    # ------------------------------------------------------------------
    # 10 — classification preserved exactly
    # ------------------------------------------------------------------

    def test_10_classification_preserved(self) -> None:
        snap_state = _make_snap_state()
        result = main._build_snap_preview_markers(snap_state)
        for rec, marker in zip(snap_state["recommendations"], result["markers"]):
            self.assertEqual(marker["classification"], rec["classification"])

    # ------------------------------------------------------------------
    # 11 — presentation_role is always "ghost_marker"
    # ------------------------------------------------------------------

    def test_11_presentation_role_fixed(self) -> None:
        result = main._build_snap_preview_markers(_make_snap_state())
        for marker in result["markers"]:
            self.assertEqual(marker["presentation_role"], "ghost_marker")

    # ------------------------------------------------------------------
    # 12 — current_decision: None when no events exist
    # ------------------------------------------------------------------

    def test_12_decision_none_without_events(self) -> None:
        result = main._build_snap_preview_markers(_make_snap_state())
        for marker in result["markers"]:
            self.assertIsNone(marker["current_decision"])
        self.assertEqual(result["summary"]["with_decision"], 0)
        self.assertEqual(result["summary"]["without_decision"], 19)

    # ------------------------------------------------------------------
    # 13 — current_decision: approved propagates from events
    # ------------------------------------------------------------------

    def test_13_decision_approved_from_events(self) -> None:
        # Record an approval for route_35_seg_0|start
        main._append_snap_review_event(
            segment_id="route_35_seg_0",
            endpoint_label="start",
            decision="approved",
            recommendation_snapshot={},
            operator_id="op",
            session_id=None,
        )
        decisions = main._resolve_current_snap_review_decisions()
        result = main._build_snap_preview_markers(_make_snap_state(), decisions=decisions)
        approved_markers = [
            m for m in result["markers"] if m["current_decision"] == "approved"
        ]
        self.assertEqual(len(approved_markers), 1)
        self.assertEqual(approved_markers[0]["segment_id"], "route_35_seg_0")
        self.assertEqual(approved_markers[0]["endpoint"], "start")

    # ------------------------------------------------------------------
    # 14 — current_decision: revoked → None
    # ------------------------------------------------------------------

    def test_14_decision_revoked_clears(self) -> None:
        for decision in ["approved", "revoked"]:
            main._append_snap_review_event(
                segment_id="route_35_seg_0",
                endpoint_label="start",
                decision=decision,
                recommendation_snapshot={},
                operator_id="op",
                session_id=None,
            )
        decisions = main._resolve_current_snap_review_decisions()
        result = main._build_snap_preview_markers(_make_snap_state(), decisions=decisions)
        marker = next(
            m for m in result["markers"]
            if m["segment_id"] == "route_35_seg_0" and m["endpoint"] == "start"
        )
        self.assertIsNone(marker["current_decision"])
        self.assertEqual(result["summary"]["with_decision"], 0)

    # ------------------------------------------------------------------
    # 15 — empty recommendations → empty result
    # ------------------------------------------------------------------

    def test_15_empty_recommendations(self) -> None:
        result = main._build_snap_preview_markers({"recommendations": []})
        self.assertEqual(result["markers"], [])
        self.assertEqual(result["summary"]["total_markers"], 0)
        self.assertEqual(result["schema_version"], "snap-preview-marker-1")

    # ------------------------------------------------------------------
    # 16 — None input → empty result, no raise
    # ------------------------------------------------------------------

    def test_16_none_input_safe(self) -> None:
        result = main._build_snap_preview_markers(None)
        self.assertEqual(result["markers"], [])
        self.assertEqual(result["summary"]["total_markers"], 0)

    # ------------------------------------------------------------------
    # 17 — malformed recommendations skip silently
    # ------------------------------------------------------------------

    def test_17_malformed_recommendations_skipped(self) -> None:
        bad_recs = [
            None,
            "not a dict",
            {},
            {"segment_id": "", "endpoint": "start", "classification": "near"},
            {"segment_id": "x", "endpoint": "middle", "classification": "near"},
            {"segment_id": "x", "endpoint": "start", "classification": "unknown"},
            _make_recommendation("good_seg", "start", "route"),
        ]
        result = main._build_snap_preview_markers({"recommendations": bad_recs})
        self.assertEqual(len(result["markers"]), 1)
        self.assertEqual(result["markers"][0]["segment_id"], "good_seg")

    # ------------------------------------------------------------------
    # 18 — non-dict snap_recommendations argument → empty
    # ------------------------------------------------------------------

    def test_18_non_dict_argument_safe(self) -> None:
        for bad in ["string", 42, [], None]:
            result = main._build_snap_preview_markers(bad)  # type: ignore[arg-type]
            self.assertEqual(result["markers"], [])

    # ------------------------------------------------------------------
    # 19 — input recommendations dict not mutated
    # ------------------------------------------------------------------

    def test_19_input_not_mutated(self) -> None:
        snap_state = _make_snap_state()
        before_sha = hashlib.sha256(
            json.dumps(snap_state, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        main._build_snap_preview_markers(snap_state)
        after_sha = hashlib.sha256(
            json.dumps(snap_state, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        self.assertEqual(before_sha, after_sha)

    # ------------------------------------------------------------------
    # 20 — STATE unchanged after endpoint call
    # ------------------------------------------------------------------

    def test_20_state_unchanged_after_endpoint(self) -> None:
        before_sha = hashlib.sha256(
            json.dumps(
                main.STATE.get("endpoint_snap_recommendations"),
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        main.STATE["redline_segments"] = [{"id": "x", "coords": [[0, 0], [1, 1]]}]
        before_redline_sha = hashlib.sha256(
            json.dumps(
                main.STATE.get("redline_segments"),
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()

        main.get_snap_preview_markers()

        after_sha = hashlib.sha256(
            json.dumps(
                main.STATE.get("endpoint_snap_recommendations"),
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        after_redline_sha = hashlib.sha256(
            json.dumps(
                main.STATE.get("redline_segments"),
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        self.assertEqual(before_sha, after_sha)
        self.assertEqual(before_redline_sha, after_redline_sha)

    # ==================================================================
    # Brenham smoke tests (use the 19-recommendation Brenham fixture)
    # ==================================================================

    # ------------------------------------------------------------------
    # 21 — Brenham: total_markers == 19
    # ------------------------------------------------------------------

    def test_21_brenham_total_markers_19(self) -> None:
        result = main._build_snap_preview_markers(_make_snap_state())
        self.assertEqual(result["summary"]["total_markers"], 19)

    # ------------------------------------------------------------------
    # 22 — Brenham: 16 near + 3 orphan
    # ------------------------------------------------------------------

    def test_22_brenham_near_orphan_split(self) -> None:
        result = main._build_snap_preview_markers(_make_snap_state())
        self.assertEqual(result["summary"]["near_markers"], 16)
        self.assertEqual(result["summary"]["orphan_markers"], 3)

    # ------------------------------------------------------------------
    # 23 — Brenham: route_35/459/476 each produce 2 markers
    # ------------------------------------------------------------------

    def test_23_brenham_specific_routes_two_markers_each(self) -> None:
        result = main._build_snap_preview_markers(_make_snap_state())
        for rid in ["route_35", "route_459", "route_476"]:
            seg = f"{rid}_seg_0"
            count = sum(1 for m in result["markers"] if m["segment_id"] == seg)
            self.assertEqual(count, 2, f"expected 2 markers for {seg}, got {count}")

    # ------------------------------------------------------------------
    # 24 — Brenham: marker coords match recommendation source
    # ------------------------------------------------------------------

    def test_24_brenham_marker_coords_match_source(self) -> None:
        snap_state = _make_snap_state()
        result = main._build_snap_preview_markers(snap_state)
        rec_index: Dict[str, Dict[str, Any]] = {
            f"{r['segment_id']}|{r['endpoint']}": r
            for r in snap_state["recommendations"]
        }
        for marker in result["markers"]:
            key = f"{marker['segment_id']}|{marker['endpoint']}"
            source = rec_index[key]
            self.assertEqual(marker["candidate_coordinate"], source["candidate_coordinate"])
            self.assertEqual(marker["candidate_anchor_id"], source["candidate_anchor_id"])

    # ------------------------------------------------------------------
    # 25 — Brenham: approve+revoke flow visible at marker level
    # ------------------------------------------------------------------

    def test_25_brenham_approve_then_revoke_flow(self) -> None:
        # Approve route_35 start
        main._append_snap_review_event(
            segment_id="route_35_seg_0",
            endpoint_label="start",
            decision="approved",
            recommendation_snapshot={},
            operator_id="office",
            session_id=None,
        )
        decisions = main._resolve_current_snap_review_decisions()
        result = main._build_snap_preview_markers(_make_snap_state(), decisions=decisions)
        approved = [
            m for m in result["markers"]
            if m["segment_id"] == "route_35_seg_0" and m["endpoint"] == "start"
        ][0]
        self.assertEqual(approved["current_decision"], "approved")

        # Revoke
        main._append_snap_review_event(
            segment_id="route_35_seg_0",
            endpoint_label="start",
            decision="revoked",
            recommendation_snapshot={},
            operator_id="office",
            session_id=None,
        )
        decisions2 = main._resolve_current_snap_review_decisions()
        result2 = main._build_snap_preview_markers(_make_snap_state(), decisions=decisions2)
        revoked = [
            m for m in result2["markers"]
            if m["segment_id"] == "route_35_seg_0" and m["endpoint"] == "start"
        ][0]
        self.assertIsNone(revoked["current_decision"])

    # ==================================================================
    # AST regression — operational helpers must not reference markers
    # ==================================================================

    # ------------------------------------------------------------------
    # 26 — AST: operational helpers do not reference snap preview markers
    # ------------------------------------------------------------------

    def test_26_ast_operational_helpers_do_not_reference_markers(self) -> None:
        """Verify operational helpers contain no reference to Phase 1V
        snap-preview-marker functions or schema strings.

        Markers are diagnostic-only; operational helpers must remain
        oblivious to them.
        """
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
            }
        )

        FORBIDDEN_REFERENCES = frozenset(
            {
                "_build_snap_preview_markers",
                "snap-preview-marker-1",
                "ghost_marker",
                "_SNAP_PREVIEW_MARKER_STABILITY_NOTE",
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
                if name and any(forbidden in name for forbidden in FORBIDDEN_REFERENCES):
                    violations.append(f"{node.name} references '{name}'")

        self.assertEqual(
            violations,
            [],
            f"Operational helpers reference snap preview markers: {violations}",
        )


if __name__ == "__main__":
    unittest.main()
