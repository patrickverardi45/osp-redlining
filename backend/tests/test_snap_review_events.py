"""Phase 1U — Operator-Approved Snap Review Events lock-down suite.

30 tests for ``_append_snap_review_event``, ``_resolve_current_snap_review_decisions``,
``_snap_recommendation_sha256``, ``post_snap_review_event``,
``get_snap_review_events``, and ``get_snap_review_events_current``.

ISOLATION STRATEGY
------------------
Each test runs in an isolated ``tempfile.TemporaryDirectory``.
``main.SNAP_REVIEW_EVENTS_PATH`` and ``main.SNAP_REVIEW_EVENTS_MAX_ROWS`` are
monkeypatched in ``setUp`` and restored in ``tearDown``.
``main.STATE`` is monkeypatched where needed and restored after.
The real ``data/operational_logs/snap_review_events.jsonl`` is never touched.

REGRESSION ASSERTION
--------------------
test_30 verifies via AST analysis that operational helpers (scoring, matching,
geometry, endpoint validation, route catalog builders) do not reference
snap review event functions or the JSONL path.  If that test fails after a
code change, investigate before proceeding.

IF A TEST FAILS after a legitimate Phase 1U change:
  1. Confirm the change is intentional.
  2. Update the relevant constant or assertion below.
  3. Add a comment explaining why.
  DO NOT "fix to green" without understanding the failure.
"""

from __future__ import annotations

import ast
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
# Schema lock — exact keys emitted by _append_snap_review_event.
# Any change here means the schema changed — update with a comment.
# ---------------------------------------------------------------------------
EXPECTED_EVENT_KEYS: frozenset = frozenset(
    {
        "schema_version",
        "event_id",
        "created_at",
        "recommendation_key",
        "recommendation_snapshot",
        "input_sha256",
        "decision",
        "operator_id",
        "session_id",
    }
)

EXPECTED_REC_KEY_KEYS: frozenset = frozenset({"segment_id", "endpoint"})

EXPECTED_SNAPSHOT_KEYS: frozenset = frozenset(
    {
        "route_id",
        "current_coordinate",
        "current_distance_ft",
        "candidate_anchor_id",
        "candidate_anchor_name",
        "candidate_coordinate",
        "snap_delta_ft",
        "classification",
    }
)

VALID_DECISIONS: frozenset = frozenset({"approved", "rejected", "revoked"})

# ---------------------------------------------------------------------------
# Brenham-style fixture recommendation (mirrors Phase 1T output shape).
# ---------------------------------------------------------------------------
BRENHAM_RECS: List[Dict[str, Any]] = [
    {
        "segment_id": "route_35_seg_0",
        "endpoint": "start",
        "route_id": "route_35",
        "current_coordinate": [-96.4001, 30.1501],
        "current_distance_ft": 5.3,
        "candidate_anchor_id": "anchor_35_a",
        "candidate_anchor_name": "HH-35-A",
        "candidate_coordinate": [-96.4002, 30.1502],
        "snap_delta_ft": 5.3,
        "classification": "near",
    },
    {
        "segment_id": "route_35_seg_0",
        "endpoint": "end",
        "route_id": "route_35",
        "current_coordinate": [-96.4005, 30.1505],
        "current_distance_ft": 6.1,
        "candidate_anchor_id": "anchor_35_b",
        "candidate_anchor_name": "HH-35-B",
        "candidate_coordinate": [-96.4006, 30.1506],
        "snap_delta_ft": 6.1,
        "classification": "near",
    },
    {
        "segment_id": "route_459_seg_0",
        "endpoint": "start",
        "route_id": "route_459",
        "current_coordinate": [-96.4101, 30.1601],
        "current_distance_ft": 7.8,
        "candidate_anchor_id": "anchor_459_a",
        "candidate_anchor_name": "HH-459-A",
        "candidate_coordinate": [-96.4102, 30.1602],
        "snap_delta_ft": 7.8,
        "classification": "near",
    },
    {
        "segment_id": "route_459_seg_0",
        "endpoint": "end",
        "route_id": "route_459",
        "current_coordinate": [-96.4105, 30.1605],
        "current_distance_ft": 8.2,
        "candidate_anchor_id": "anchor_459_b",
        "candidate_anchor_name": None,
        "candidate_coordinate": [-96.4106, 30.1606],
        "snap_delta_ft": 8.2,
        "classification": "near",
    },
    {
        "segment_id": "route_476_seg_0",
        "endpoint": "start",
        "route_id": "route_476",
        "current_coordinate": [-96.4201, 30.1701],
        "current_distance_ft": 9.1,
        "candidate_anchor_id": "anchor_476_a",
        "candidate_anchor_name": "HH-476-A",
        "candidate_coordinate": [-96.4202, 30.1702],
        "snap_delta_ft": 9.1,
        "classification": "near",
    },
    {
        "segment_id": "route_476_seg_0",
        "endpoint": "end",
        "route_id": "route_476",
        "current_coordinate": [-96.4205, 30.1705],
        "current_distance_ft": 9.8,
        "candidate_anchor_id": "anchor_476_b",
        "candidate_anchor_name": "HH-476-B",
        "candidate_coordinate": [-96.4206, 30.1706],
        "snap_delta_ft": 9.8,
        "classification": "near",
    },
    {
        "segment_id": "route_99_seg_0",
        "endpoint": "start",
        "route_id": "route_99",
        "current_coordinate": [-96.5000, 30.2000],
        "current_distance_ft": 55.3,
        "candidate_anchor_id": "anchor_99_a",
        "candidate_anchor_name": "HH-99-A",
        "candidate_coordinate": [-96.5010, 30.2010],
        "snap_delta_ft": 55.3,
        "classification": "orphan",
    },
]


def _make_snap_state(recs: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Build a minimal endpoint_snap_recommendations STATE value."""
    r = recs if recs is not None else BRENHAM_RECS
    return {
        "schema_version": "endpoint-snap-recommendation-1",
        "recommendations": r,
        "summary": {
            "total_recommendations": len(r),
            "near_recommendations": sum(1 for x in r if x.get("classification") == "near"),
            "orphan_recommendations": sum(1 for x in r if x.get("classification") == "orphan"),
        },
    }


def _read_sre_rows(path: Path) -> List[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    return [json.loads(ln) for ln in text.strip().splitlines() if ln.strip()]


def _post_decision(
    body: Dict[str, Any],
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    resp = main.post_snap_review_event(body=body, session_id=session_id)
    return json.loads(resp.body)


def _get_events(limit: int = 100, decision: Optional[str] = None) -> Dict[str, Any]:
    resp = main.get_snap_review_events(limit=limit, decision=decision)
    return json.loads(resp.body)


def _get_current(segment_id: str, endpoint: str) -> Optional[Dict[str, Any]]:
    resp = main.get_snap_review_events_current(
        segment_id=segment_id, endpoint=endpoint
    )
    return json.loads(resp.body).get("current")


# ---------------------------------------------------------------------------
# Test suite
# ---------------------------------------------------------------------------


class TestSnapReviewEvents(unittest.TestCase):
    """Lock-down suite for Phase 1U snap-review-event telemetry."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._orig_path = main.SNAP_REVIEW_EVENTS_PATH
        self._orig_max_rows = main.SNAP_REVIEW_EVENTS_MAX_ROWS
        self._orig_state = dict(main.STATE)

        main.SNAP_REVIEW_EVENTS_PATH = Path(self._tmpdir.name) / "snap_review_events.jsonl"

        # Inject Brenham-style snap recommendations into STATE.
        main.STATE["endpoint_snap_recommendations"] = _make_snap_state()

    def tearDown(self) -> None:
        main.SNAP_REVIEW_EVENTS_MAX_ROWS = self._orig_max_rows
        main.SNAP_REVIEW_EVENTS_PATH = self._orig_path
        main.STATE.clear()
        main.STATE.update(self._orig_state)
        self._tmpdir.cleanup()

    # ------------------------------------------------------------------
    # 01 — append creates file with correct schema
    # ------------------------------------------------------------------

    def test_01_append_creates_file_with_schema_version(self) -> None:
        rec = BRENHAM_RECS[0]
        eid = main._append_snap_review_event(
            segment_id=rec["segment_id"],
            endpoint_label=rec["endpoint"],
            decision="approved",
            recommendation_snapshot={k: rec[k] for k in EXPECTED_SNAPSHOT_KEYS},
            operator_id="test-op",
            session_id=None,
        )
        self.assertTrue(main.SNAP_REVIEW_EVENTS_PATH.exists())
        rows = _read_sre_rows(main.SNAP_REVIEW_EVENTS_PATH)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["schema_version"], "snap-review-event-1")
        self.assertEqual(row["event_id"], eid)
        self.assertEqual(row["decision"], "approved")

    # ------------------------------------------------------------------
    # 02 — schema lock: exact key set
    # ------------------------------------------------------------------

    def test_02_schema_key_set(self) -> None:
        rec = BRENHAM_RECS[0]
        main._append_snap_review_event(
            segment_id=rec["segment_id"],
            endpoint_label=rec["endpoint"],
            decision="approved",
            recommendation_snapshot={k: rec[k] for k in EXPECTED_SNAPSHOT_KEYS},
            operator_id="test-op",
            session_id="sess-1",
        )
        rows = _read_sre_rows(main.SNAP_REVIEW_EVENTS_PATH)
        row = rows[0]
        self.assertEqual(set(row.keys()), EXPECTED_EVENT_KEYS)
        self.assertEqual(set(row["recommendation_key"].keys()), EXPECTED_REC_KEY_KEYS)
        self.assertEqual(set(row["recommendation_snapshot"].keys()), EXPECTED_SNAPSHOT_KEYS)

    # ------------------------------------------------------------------
    # 03 — append-only: multiple writes accumulate
    # ------------------------------------------------------------------

    def test_03_append_only_accumulates(self) -> None:
        for decision in ["approved", "rejected", "revoked"]:
            main._append_snap_review_event(
                segment_id="route_35_seg_0",
                endpoint_label="start",
                decision=decision,
                recommendation_snapshot={},
                operator_id="op",
                session_id=None,
            )
        rows = _read_sre_rows(main.SNAP_REVIEW_EVENTS_PATH)
        self.assertEqual(len(rows), 3)
        decisions_written = [r["decision"] for r in rows]
        self.assertEqual(decisions_written, ["approved", "rejected", "revoked"])

    # ------------------------------------------------------------------
    # 04 — deterministic input_sha256 for identical snapshot
    # ------------------------------------------------------------------

    def test_04_deterministic_sha256(self) -> None:
        snapshot = {k: BRENHAM_RECS[0][k] for k in EXPECTED_SNAPSHOT_KEYS}
        sha1 = main._snap_recommendation_sha256(snapshot)
        sha2 = main._snap_recommendation_sha256(snapshot)
        self.assertEqual(sha1, sha2)
        self.assertEqual(len(sha1), 64)  # hex sha256

    # ------------------------------------------------------------------
    # 05 — different snapshots produce different sha256
    # ------------------------------------------------------------------

    def test_05_different_snapshots_different_sha256(self) -> None:
        s1 = {k: BRENHAM_RECS[0][k] for k in EXPECTED_SNAPSHOT_KEYS}
        s2 = {k: BRENHAM_RECS[1][k] for k in EXPECTED_SNAPSHOT_KEYS}
        self.assertNotEqual(
            main._snap_recommendation_sha256(s1),
            main._snap_recommendation_sha256(s2),
        )

    # ------------------------------------------------------------------
    # 06 — sha256 stored in written row
    # ------------------------------------------------------------------

    def test_06_sha256_stored_in_row(self) -> None:
        snapshot = {k: BRENHAM_RECS[0][k] for k in EXPECTED_SNAPSHOT_KEYS}
        expected_sha = main._snap_recommendation_sha256(snapshot)
        main._append_snap_review_event(
            segment_id="route_35_seg_0",
            endpoint_label="start",
            decision="approved",
            recommendation_snapshot=snapshot,
            operator_id="op",
            session_id=None,
        )
        rows = _read_sre_rows(main.SNAP_REVIEW_EVENTS_PATH)
        self.assertEqual(rows[0]["input_sha256"], expected_sha)

    # ------------------------------------------------------------------
    # 07 — POST: stale recommendation key rejected
    # ------------------------------------------------------------------

    def test_07_post_stale_key_rejected(self) -> None:
        result = _post_decision(
            {"segment_id": "nonexistent_seg", "endpoint": "start", "decision": "approved"}
        )
        self.assertFalse(result["accepted"])
        self.assertEqual(result["error"], "recommendation_not_found")

    # ------------------------------------------------------------------
    # 08 — POST: invalid decision rejected
    # ------------------------------------------------------------------

    def test_08_post_invalid_decision_rejected(self) -> None:
        result = _post_decision(
            {
                "segment_id": "route_35_seg_0",
                "endpoint": "start",
                "decision": "approve_and_snap",  # forbidden
            }
        )
        self.assertFalse(result["accepted"])
        self.assertEqual(result["error"], "invalid_decision")

    # ------------------------------------------------------------------
    # 09 — POST: valid decision accepted and written
    # ------------------------------------------------------------------

    def test_09_post_valid_decision_written(self) -> None:
        result = _post_decision(
            {
                "segment_id": "route_35_seg_0",
                "endpoint": "start",
                "decision": "approved",
                "operator_id": "alice",
            }
        )
        self.assertTrue(result["accepted"])
        self.assertIn("event_id", result)
        self.assertEqual(result["decision"], "approved")
        self.assertTrue(main.SNAP_REVIEW_EVENTS_PATH.exists())

    # ------------------------------------------------------------------
    # 10 — POST: missing body / non-dict body never crashes
    # ------------------------------------------------------------------

    def test_10_malformed_body_never_crashes(self) -> None:
        for bad_body in [None, [], "string", 42]:
            resp = main.post_snap_review_event(body=bad_body, session_id=None)  # type: ignore[arg-type]
            data = json.loads(resp.body)
            self.assertFalse(data["accepted"])

    # ------------------------------------------------------------------
    # 11 — POST: closeout lock rejects event
    # ------------------------------------------------------------------

    def test_11_closeout_lock_rejects(self) -> None:
        orig_lock = main.STATE.get("closeout_lock")
        try:
            main.STATE["closeout_lock"] = {"is_locked": True}
            result = _post_decision(
                {"segment_id": "route_35_seg_0", "endpoint": "start", "decision": "approved"}
            )
            self.assertFalse(result["accepted"])
            self.assertEqual(result["error"], "closeout_locked")
        finally:
            if orig_lock is None:
                main.STATE.pop("closeout_lock", None)
            else:
                main.STATE["closeout_lock"] = orig_lock

    # ------------------------------------------------------------------
    # 12 — resolve: empty file returns empty dict
    # ------------------------------------------------------------------

    def test_12_resolve_empty_file(self) -> None:
        result = main._resolve_current_snap_review_decisions()
        self.assertEqual(result, {})

    # ------------------------------------------------------------------
    # 13 — resolve: latest-wins for same key
    # ------------------------------------------------------------------

    def test_13_resolve_latest_wins(self) -> None:
        seg, ep = "route_35_seg_0", "start"
        for decision in ["approved", "rejected"]:
            main._append_snap_review_event(
                segment_id=seg,
                endpoint_label=ep,
                decision=decision,
                recommendation_snapshot={},
                operator_id="op",
                session_id=None,
            )
        resolved = main._resolve_current_snap_review_decisions(seg, ep)
        key = f"{seg}|{ep}"
        self.assertIn(key, resolved)
        self.assertIsNotNone(resolved[key])
        self.assertEqual(resolved[key]["decision"], "rejected")  # type: ignore[index]

    # ------------------------------------------------------------------
    # 14 — resolve: revoke clears current decision
    # ------------------------------------------------------------------

    def test_14_revoke_clears_decision(self) -> None:
        seg, ep = "route_35_seg_0", "start"
        for decision in ["approved", "revoked"]:
            main._append_snap_review_event(
                segment_id=seg,
                endpoint_label=ep,
                decision=decision,
                recommendation_snapshot={},
                operator_id="op",
                session_id=None,
            )
        resolved = main._resolve_current_snap_review_decisions(seg, ep)
        key = f"{seg}|{ep}"
        self.assertIn(key, resolved)
        self.assertIsNone(resolved[key])  # revoke → None

    # ------------------------------------------------------------------
    # 15 — resolve: scoped to segment_id + endpoint
    # ------------------------------------------------------------------

    def test_15_resolve_scoped_to_key(self) -> None:
        for seg, ep, dec in [
            ("route_35_seg_0", "start", "approved"),
            ("route_35_seg_0", "end", "rejected"),
        ]:
            main._append_snap_review_event(
                segment_id=seg,
                endpoint_label=ep,
                decision=dec,
                recommendation_snapshot={},
                operator_id="op",
                session_id=None,
            )
        resolved = main._resolve_current_snap_review_decisions("route_35_seg_0", "start")
        self.assertEqual(len(resolved), 1)
        self.assertIn("route_35_seg_0|start", resolved)

    # ------------------------------------------------------------------
    # 16 — GET /events: empty when no file
    # ------------------------------------------------------------------

    def test_16_get_events_empty_no_file(self) -> None:
        data = _get_events()
        self.assertEqual(data["events"], [])
        self.assertIn("summary", data)

    # ------------------------------------------------------------------
    # 17 — GET /events: returns written events newest-first
    # ------------------------------------------------------------------

    def test_17_get_events_newest_first(self) -> None:
        for i, decision in enumerate(["approved", "rejected", "revoked"]):
            main._append_snap_review_event(
                segment_id=f"seg_{i}",
                endpoint_label="start",
                decision=decision,
                recommendation_snapshot={},
                operator_id="op",
                session_id=None,
            )
        data = _get_events()
        decisions = [e["decision"] for e in data["events"]]
        # Newest-first: revoked, rejected, approved
        self.assertEqual(decisions[0], "revoked")
        self.assertEqual(decisions[-1], "approved")

    # ------------------------------------------------------------------
    # 18 — GET /events: decision filter
    # ------------------------------------------------------------------

    def test_18_get_events_decision_filter(self) -> None:
        for decision in ["approved", "approved", "rejected"]:
            main._append_snap_review_event(
                segment_id="seg",
                endpoint_label="start",
                decision=decision,
                recommendation_snapshot={},
                operator_id="op",
                session_id=None,
            )
        data = _get_events(decision="approved")
        self.assertEqual(len(data["events"]), 2)
        for ev in data["events"]:
            self.assertEqual(ev["decision"], "approved")

    # ------------------------------------------------------------------
    # 19 — GET /events: summary counts correct
    # ------------------------------------------------------------------

    def test_19_get_events_summary_counts(self) -> None:
        for seg, ep, dec in [
            ("route_35_seg_0", "start", "approved"),
            ("route_35_seg_0", "end", "rejected"),
            ("route_459_seg_0", "start", "revoked"),
        ]:
            main._append_snap_review_event(
                segment_id=seg,
                endpoint_label=ep,
                decision=dec,
                recommendation_snapshot={},
                operator_id="op",
                session_id=None,
            )
        data = _get_events()
        s = data["summary"]
        self.assertEqual(s["total_events"], 3)
        self.assertEqual(s["approved_count"], 1)
        self.assertEqual(s["rejected_count"], 1)
        self.assertEqual(s["revoked_count"], 1)
        self.assertEqual(s["reviewed_recommendation_count"], 3)

    # ------------------------------------------------------------------
    # 20 — GET /events/current: no decision returns null
    # ------------------------------------------------------------------

    def test_20_get_current_no_decision(self) -> None:
        current = _get_current("route_35_seg_0", "start")
        self.assertIsNone(current)

    # ------------------------------------------------------------------
    # 21 — GET /events/current: returns latest decision
    # ------------------------------------------------------------------

    def test_21_get_current_returns_latest(self) -> None:
        _post_decision({"segment_id": "route_35_seg_0", "endpoint": "start", "decision": "approved"})
        _post_decision({"segment_id": "route_35_seg_0", "endpoint": "start", "decision": "rejected"})
        current = _get_current("route_35_seg_0", "start")
        self.assertIsNotNone(current)
        self.assertEqual(current["decision"], "rejected")  # type: ignore[index]

    # ------------------------------------------------------------------
    # 22 — GET /events/current: after revoke returns null
    # ------------------------------------------------------------------

    def test_22_get_current_after_revoke(self) -> None:
        _post_decision({"segment_id": "route_35_seg_0", "endpoint": "start", "decision": "approved"})
        _post_decision({"segment_id": "route_35_seg_0", "endpoint": "start", "decision": "revoked"})
        current = _get_current("route_35_seg_0", "start")
        self.assertIsNone(current)

    # ------------------------------------------------------------------
    # 23 — GET /events/current: invalid endpoint param returns null
    # ------------------------------------------------------------------

    def test_23_get_current_invalid_endpoint_param(self) -> None:
        resp = main.get_snap_review_events_current(segment_id="route_35_seg_0", endpoint="middle")
        data = json.loads(resp.body)
        self.assertIsNone(data["current"])

    # ------------------------------------------------------------------
    # 24 — geometry: redline_segments unchanged after events
    # ------------------------------------------------------------------

    def test_24_redline_segments_unchanged_after_events(self) -> None:
        import hashlib as _hl
        orig_segs = [{"id": "s1", "coordinates": [[0.0, 1.0], [2.0, 3.0]]}]
        main.STATE["redline_segments"] = orig_segs
        before_sha = _hl.sha256(
            json.dumps(main.STATE.get("redline_segments"), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        _post_decision({"segment_id": "route_35_seg_0", "endpoint": "start", "decision": "approved"})
        after_sha = _hl.sha256(
            json.dumps(main.STATE.get("redline_segments"), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        self.assertEqual(before_sha, after_sha, "redline_segments mutated by snap review event")

    # ------------------------------------------------------------------
    # 25 — recommendations unchanged after events
    # ------------------------------------------------------------------

    def test_25_recommendations_unchanged_after_events(self) -> None:
        import hashlib as _hl
        before_sha = _hl.sha256(
            json.dumps(main.STATE.get("endpoint_snap_recommendations"), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        _post_decision({"segment_id": "route_35_seg_0", "endpoint": "start", "decision": "approved"})
        after_sha = _hl.sha256(
            json.dumps(main.STATE.get("endpoint_snap_recommendations"), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        self.assertEqual(before_sha, after_sha, "endpoint_snap_recommendations mutated by snap review event")

    # ------------------------------------------------------------------
    # 26 — tail truncation: cap respected
    # ------------------------------------------------------------------

    def test_26_tail_truncation_respected(self) -> None:
        main.SNAP_REVIEW_EVENTS_MAX_ROWS = 5
        for i in range(8):
            main._append_snap_review_event(
                segment_id=f"seg_{i}",
                endpoint_label="start",
                decision="approved",
                recommendation_snapshot={},
                operator_id="op",
                session_id=None,
            )
        rows = _read_sre_rows(main.SNAP_REVIEW_EVENTS_PATH)
        self.assertLessEqual(len(rows), 5)

    # ==================================================================
    # Brenham smoke tests — use fixture with Brenham-style keys
    # ==================================================================

    # ------------------------------------------------------------------
    # 27 — Brenham: route_35 start approve resolves correctly
    # ------------------------------------------------------------------

    def test_27_brenham_route35_start_approve(self) -> None:
        result = _post_decision(
            {"segment_id": "route_35_seg_0", "endpoint": "start", "decision": "approved"}
        )
        self.assertTrue(result["accepted"])
        current = _get_current("route_35_seg_0", "start")
        self.assertIsNotNone(current)
        self.assertEqual(current["decision"], "approved")  # type: ignore[index]
        self.assertEqual(current["recommendation_key"]["segment_id"], "route_35_seg_0")  # type: ignore[index]
        self.assertEqual(current["recommendation_key"]["endpoint"], "start")  # type: ignore[index]

    # ------------------------------------------------------------------
    # 28 — Brenham: route_35 end reject + revoke resolves correctly
    # ------------------------------------------------------------------

    def test_28_brenham_route35_end_reject_then_revoke(self) -> None:
        _post_decision({"segment_id": "route_35_seg_0", "endpoint": "end", "decision": "rejected"})
        # Confirm rejected
        current = _get_current("route_35_seg_0", "end")
        self.assertEqual(current["decision"], "rejected")  # type: ignore[index]
        # Now revoke
        _post_decision({"segment_id": "route_35_seg_0", "endpoint": "end", "decision": "revoked"})
        current_after = _get_current("route_35_seg_0", "end")
        self.assertIsNone(current_after)

    # ------------------------------------------------------------------
    # 29 — Brenham: 6 approvals across route_35/459/476 counted correctly
    # ------------------------------------------------------------------

    def test_29_brenham_six_approvals_counted(self) -> None:
        target_segs = [
            ("route_35_seg_0", "start"),
            ("route_35_seg_0", "end"),
            ("route_459_seg_0", "start"),
            ("route_459_seg_0", "end"),
            ("route_476_seg_0", "start"),
            ("route_476_seg_0", "end"),
        ]
        for seg, ep in target_segs:
            result = _post_decision({"segment_id": seg, "endpoint": ep, "decision": "approved"})
            self.assertTrue(result["accepted"], f"approval failed for {seg}/{ep}")
        data = _get_events()
        s = data["summary"]
        self.assertEqual(s["approved_count"], 6)
        self.assertEqual(s["total_events"], 6)

    # ==================================================================
    # AST regression — operational helpers must not reference events
    # ==================================================================

    # ------------------------------------------------------------------
    # 30 — AST: operational helpers do not reference snap review events
    # ------------------------------------------------------------------

    def test_30_ast_operational_helpers_do_not_reference_snap_review_events(self) -> None:
        """Verify operational helpers contain no reference to snap-review-event
        functions or the SNAP_REVIEW_EVENTS_PATH constant.

        These helpers must remain operationally isolated from the Phase 1U
        review-event telemetry.
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
                "_append_snap_review_event",
                "_resolve_current_snap_review_decisions",
                "SNAP_REVIEW_EVENTS_PATH",
                "snap_review_events",
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
            f"Operational helpers reference snap review events: {violations}",
        )


if __name__ == "__main__":
    unittest.main()
