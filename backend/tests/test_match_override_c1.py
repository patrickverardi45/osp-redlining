"""KMZ Matching Trust Slice C1 — operator override persistence tests.

Covers the pure helpers + endpoint write/list/clear flow + audit JSONL write.
Locks the C1-record-only contract:
- override is persisted to STATE["match_overrides"]
- audit row appended to MATCH_OVERRIDES_AUDIT_PATH
- selected_route_id / render_allowed / render_block_reasons UNCHANGED
- no apply seam (C2 explicitly not implemented)
"""

from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from typing import Any, Dict, List

os.environ.setdefault("TRUELINE_JWT_SECRET", "match-override-c1-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "match-override-c1-auth-test-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend import main as M
from backend.app.core import match_override as MO


def _route(rid: str, length_ft: float = 500.0) -> Dict[str, Any]:
    return {
        "route_id": rid,
        "route_name": rid,
        "route_role": "underground_cable",
        "source_folder": "Brenham",
        "length_ft": length_ft,
        "coords": [[-96.4, 30.2], [-96.4, 30.3]],
    }


def _diag(group_id: str, source_file: str, selected: str = "route_478") -> Dict[str, Any]:
    return {
        "source_file": source_file,
        "group_id": group_id,
        "stopped_at": None,
        "selected_route_id": selected,
        "selected_route_name": "Mansfield",
        "render_allowed": True,
        "render_block_reasons": [],
        "strict_top5": [
            {"route_id": selected, "route_name": selected, "score": 0.82, "route_length_ft": 500.0},
            {"route_id": "route_476", "route_name": "E Stone St", "score": 0.71, "route_length_ft": 480.0},
        ],
    }


class TestValidatePayload(unittest.TestCase):
    """Pure validation helper."""

    def setUp(self) -> None:
        self.diag = [_diag("g_a", "bore_log1.xlsx"), _diag("g_b", "bore_log2.xlsx")]
        self.catalog = [_route("route_476"), _route("route_478")]

    def test_happy_path(self):
        norm = MO.validate_override_payload(
            {"group_id": "g_a", "override_route_id": "route_476", "reason": "field confirmed"},
            self.diag, self.catalog,
        )
        self.assertEqual(norm["group_id"], "g_a")
        self.assertEqual(norm["override_route_id"], "route_476")
        self.assertEqual(norm["reason"], "field confirmed")

    def test_empty_reason_rejected(self):
        with self.assertRaises(MO.OverrideValidationError) as ctx:
            MO.validate_override_payload(
                {"group_id": "g_a", "override_route_id": "route_476", "reason": "   "},
                self.diag, self.catalog,
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("reason", str(ctx.exception))

    def test_missing_group_id_rejected(self):
        with self.assertRaises(MO.OverrideValidationError):
            MO.validate_override_payload(
                {"override_route_id": "route_476", "reason": "x"},
                self.diag, self.catalog,
            )

    def test_unknown_group_id_rejected(self):
        with self.assertRaises(MO.OverrideValidationError) as ctx:
            MO.validate_override_payload(
                {"group_id": "g_missing", "override_route_id": "route_476", "reason": "x"},
                self.diag, self.catalog,
            )
        self.assertIn("pipeline_diag", str(ctx.exception))

    def test_unknown_route_id_rejected(self):
        with self.assertRaises(MO.OverrideValidationError) as ctx:
            MO.validate_override_payload(
                {"group_id": "g_a", "override_route_id": "route_PHANTOM", "reason": "x"},
                self.diag, self.catalog,
            )
        self.assertIn("route_catalog", str(ctx.exception))

    def test_null_route_id_accepted_as_force_abstain(self):
        norm = MO.validate_override_payload(
            {"group_id": "g_a", "override_route_id": None, "reason": "no good fit"},
            self.diag, self.catalog,
        )
        self.assertIsNone(norm["override_route_id"])

    def test_empty_string_route_id_treated_as_null(self):
        norm = MO.validate_override_payload(
            {"group_id": "g_a", "override_route_id": "", "reason": "no good fit"},
            self.diag, self.catalog,
        )
        self.assertIsNone(norm["override_route_id"])


class TestBuildRecord(unittest.TestCase):
    def test_record_shape(self):
        record = MO.build_override_record(
            {"group_id": "g_a", "override_route_id": "route_476", "reason": "x"},
            tenant_id="t1", session_id="s1", operator_email="op@x.com",
        )
        self.assertEqual(record["schema_version"], "match-override-1")
        self.assertEqual(record["status"], "active")
        self.assertEqual(record["group_id"], "g_a")
        self.assertEqual(record["override_route_id"], "route_476")
        self.assertEqual(record["tenant_id"], "t1")
        self.assertEqual(record["session_id"], "s1")
        self.assertEqual(record["operator_email"], "op@x.com")
        self.assertTrue(record["emit_id"])
        self.assertIsNone(record["supersedes_emit_id"])

    def test_idempotent_retry_detection(self):
        record = MO.build_override_record(
            {"group_id": "g_a", "override_route_id": "route_476", "reason": "x"},
            tenant_id="t1", session_id="s1", operator_email=None,
        )
        # Same payload again → idempotent.
        self.assertTrue(MO.is_idempotent_retry(
            record, {"group_id": "g_a", "override_route_id": "route_476", "reason": "x"}
        ))
        # Different reason → not idempotent.
        self.assertFalse(MO.is_idempotent_retry(
            record, {"group_id": "g_a", "override_route_id": "route_476", "reason": "y"}
        ))
        # Different route → not idempotent.
        self.assertFalse(MO.is_idempotent_retry(
            record, {"group_id": "g_a", "override_route_id": "route_478", "reason": "x"}
        ))


class TestSnapshotEngineSelection(unittest.TestCase):
    def test_basic_snapshot(self):
        diag = [_diag("g_a", "bore_log1.xlsx", selected="route_478")]
        snap = MO.snapshot_engine_selection(diag, "g_a")
        self.assertEqual(snap["selected_route_id"], "route_478")
        self.assertEqual(len(snap["top_3_alternates"]), 2)

    def test_missing_group_returns_empty(self):
        diag = [_diag("g_a", "bore_log1.xlsx")]
        self.assertEqual(MO.snapshot_engine_selection(diag, "g_missing"), {})


class TestAuditEventBuilder(unittest.TestCase):
    def test_event_schema(self):
        record = MO.build_override_record(
            {"group_id": "g_a", "override_route_id": "route_476", "reason": "x"},
            tenant_id="t1", session_id="s1", operator_email=None,
        )
        ev = MO.build_audit_event("create", record)
        self.assertEqual(ev["schema_version"], "match-override-audit-1")
        self.assertEqual(ev["event"], "create")
        self.assertEqual(ev["group_id"], "g_a")
        self.assertEqual(ev["override_route_id"], "route_476")

    def test_invalid_event_coerced(self):
        record = {"emit_id": "x"}
        ev = MO.build_audit_event("garbage", record)
        self.assertEqual(ev["event"], "create")


class TestAuditAppend(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.gettempdir()) / f"c1_audit_{uuid.uuid4().hex}.jsonl"

    def tearDown(self) -> None:
        if self.tmp.exists():
            self.tmp.unlink()

    def test_append_writes_jsonl(self):
        ev = {"schema_version": "match-override-audit-1", "event": "create"}
        ok = MO.append_audit_event(ev, target_path=self.tmp)
        self.assertTrue(ok)
        line = self.tmp.read_text(encoding="utf-8").strip()
        parsed = json.loads(line)
        self.assertEqual(parsed["event"], "create")

    def test_append_returns_false_on_bad_input(self):
        self.assertFalse(MO.append_audit_event(None, target_path=self.tmp))  # type: ignore[arg-type]
        self.assertFalse(MO.append_audit_event({}, target_path=None))


class TestClassifyForListing(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = [_route("route_476"), _route("route_478")]

    def test_active_listed(self):
        state = {
            "g_a": {"group_id": "g_a", "override_route_id": "route_476",
                    "status": "active"},
        }
        active, orphaned = MO.classify_overrides_for_listing(state, self.catalog)
        self.assertEqual(len(active), 1)
        self.assertEqual(len(orphaned), 0)

    def test_orphan_detection(self):
        # Override route no longer in catalog → orphaned.
        state = {
            "g_a": {"group_id": "g_a", "override_route_id": "route_GONE",
                    "status": "active"},
        }
        active, orphaned = MO.classify_overrides_for_listing(state, self.catalog)
        self.assertEqual(len(active), 0)
        self.assertEqual(len(orphaned), 1)
        self.assertEqual(orphaned[0]["status"], "orphaned")

    def test_force_abstain_never_orphaned(self):
        state = {
            "g_a": {"group_id": "g_a", "override_route_id": None,
                    "status": "active"},
        }
        active, orphaned = MO.classify_overrides_for_listing(state, self.catalog)
        self.assertEqual(len(active), 1)
        self.assertEqual(len(orphaned), 0)

    def test_cleared_excluded(self):
        state = {
            "g_a": {"group_id": "g_a", "override_route_id": "route_476",
                    "status": "cleared"},
        }
        active, orphaned = MO.classify_overrides_for_listing(state, self.catalog)
        self.assertEqual(active, [])
        self.assertEqual(orphaned, [])

    def test_does_not_mutate_input(self):
        state = {
            "g_a": {"group_id": "g_a", "override_route_id": "route_GONE",
                    "status": "active"},
        }
        snap = copy.deepcopy(state)
        MO.classify_overrides_for_listing(state, self.catalog)
        self.assertEqual(state, snap)


class TestEndpointBehavior(unittest.TestCase):
    """End-to-end through the FastAPI test client. Verifies STATE writes,
    audit JSONL writes, validation, supersede behavior, clear behavior,
    and that pipeline_diag rows remain unchanged."""

    def setUp(self) -> None:
        self._saved_state = copy.deepcopy(dict(M.STATE))
        self._saved_sessions = copy.deepcopy(dict(M._SESSIONS))
        self._sid = f"c1_test_{uuid.uuid4().hex[:12]}"
        # Redirect the audit JSONL to a scratch file so the dev uploads dir
        # is not touched.
        self._tmp_audit = Path(tempfile.gettempdir()) / f"c1_endpoint_{uuid.uuid4().hex}.jsonl"
        self._orig_audit_path = M.MATCH_OVERRIDES_AUDIT_PATH
        M.MATCH_OVERRIDES_AUDIT_PATH = self._tmp_audit

        # Seed STATE with pipeline_diag + route_catalog visible to _session_scope.
        # We bypass the FastAPI client and call endpoint functions directly so
        # we don't have to spin up uvicorn. Tenant/_session_scope still apply.
        with M._SESSION_LOCK:
            M._SESSIONS[self._sid] = {
                **M._default_session_state(),
                "pipeline_diag": [_diag("g_a", "bore_log1.xlsx", selected="route_478"),
                                  _diag("g_b", "bore_log2.xlsx", selected="route_476")],
                "route_catalog": [_route("route_476"), _route("route_478")],
            }

    def tearDown(self) -> None:
        M.MATCH_OVERRIDES_AUDIT_PATH = self._orig_audit_path
        if self._tmp_audit.exists():
            self._tmp_audit.unlink()
        with M._SESSION_LOCK:
            M._SESSIONS.clear()
            M._SESSIONS.update(self._saved_sessions)
        M.STATE.clear()
        M.STATE.update(self._saved_state)

    def _post(self, body: Dict[str, Any]):
        # Direct function call. `request` parameter is unused by the handler
        # in this path; pass a sentinel None.
        return M.match_review_queue_override_post(body, None)  # type: ignore[arg-type]

    def _list(self, session_id: str):
        return M.match_review_queue_overrides_get(session_id)

    def _delete(self, session_id: str, group_id: str):
        return M.match_review_queue_override_delete(session_id, group_id)

    def test_post_happy_path(self):
        resp = self._post({
            "session_id": self._sid,
            "group_id": "g_a",
            "override_route_id": "route_476",
            "reason": "operator confirmed field route",
        })
        self.assertEqual(resp.status_code, 201)
        payload = json.loads(resp.body)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["override"]["status"], "active")
        self.assertEqual(payload["override"]["group_id"], "g_a")
        self.assertEqual(payload["override"]["override_route_id"], "route_476")
        # Engine snapshot captured.
        self.assertEqual(
            payload["engine_selection_at_write"]["selected_route_id"], "route_478"
        )
        # Audit JSONL appended.
        self.assertTrue(self._tmp_audit.exists())
        lines = self._tmp_audit.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 1)
        audit = json.loads(lines[0])
        self.assertEqual(audit["event"], "create")
        self.assertEqual(audit["group_id"], "g_a")

    def test_post_empty_reason_rejected(self):
        resp = self._post({
            "session_id": self._sid,
            "group_id": "g_a",
            "override_route_id": "route_476",
            "reason": "",
        })
        self.assertEqual(resp.status_code, 400)

    def test_post_unknown_group_id_rejected(self):
        resp = self._post({
            "session_id": self._sid,
            "group_id": "g_NOPE",
            "override_route_id": "route_476",
            "reason": "x",
        })
        self.assertEqual(resp.status_code, 400)

    def test_post_unknown_route_id_rejected(self):
        resp = self._post({
            "session_id": self._sid,
            "group_id": "g_a",
            "override_route_id": "route_PHANTOM",
            "reason": "x",
        })
        self.assertEqual(resp.status_code, 400)

    def test_post_force_abstain_accepted(self):
        resp = self._post({
            "session_id": self._sid,
            "group_id": "g_a",
            "override_route_id": None,
            "reason": "field re-investigation needed",
        })
        self.assertEqual(resp.status_code, 201)
        payload = json.loads(resp.body)
        self.assertIsNone(payload["override"]["override_route_id"])

    def test_supersede_chain(self):
        # First write.
        r1 = self._post({
            "session_id": self._sid,
            "group_id": "g_a",
            "override_route_id": "route_476",
            "reason": "first decision",
        })
        emit1 = json.loads(r1.body)["override"]["emit_id"]
        # Second write on same group — supersedes.
        r2 = self._post({
            "session_id": self._sid,
            "group_id": "g_a",
            "override_route_id": "route_478",
            "reason": "second decision",
        })
        emit2 = json.loads(r2.body)["override"]["emit_id"]
        self.assertNotEqual(emit1, emit2)
        self.assertEqual(json.loads(r2.body)["override"]["supersedes_emit_id"], emit1)
        # Audit log has 3 rows: create + supersede + create.
        lines = self._tmp_audit.read_text(encoding="utf-8").strip().splitlines()
        events = [json.loads(line)["event"] for line in lines]
        self.assertEqual(events, ["create", "supersede", "create"])

    def test_idempotent_retry(self):
        # Same payload twice → second is no-op.
        body = {
            "session_id": self._sid,
            "group_id": "g_a",
            "override_route_id": "route_476",
            "reason": "x",
        }
        r1 = self._post(body)
        r2 = self._post(body)
        self.assertEqual(r2.status_code, 200)
        self.assertTrue(json.loads(r2.body).get("idempotent"))
        # Audit log: create + no_op_idempotent.
        lines = self._tmp_audit.read_text(encoding="utf-8").strip().splitlines()
        events = [json.loads(line)["event"] for line in lines]
        self.assertEqual(events, ["create", "no_op_idempotent"])

    def test_get_lists_active(self):
        self._post({
            "session_id": self._sid,
            "group_id": "g_a",
            "override_route_id": "route_476",
            "reason": "x",
        })
        resp = self._list(self._sid)
        self.assertEqual(resp.status_code, 200)
        payload = json.loads(resp.body)
        self.assertEqual(payload["override_count"], 1)
        self.assertEqual(len(payload["active_overrides"]), 1)
        self.assertEqual(payload["active_overrides"][0]["group_id"], "g_a")

    def test_delete_clears_override(self):
        self._post({
            "session_id": self._sid,
            "group_id": "g_a",
            "override_route_id": "route_476",
            "reason": "x",
        })
        resp = self._delete(self._sid, "g_a")
        self.assertEqual(resp.status_code, 200)
        # Cleared override is excluded from the active+orphan listing.
        list_resp = self._list(self._sid)
        self.assertEqual(json.loads(list_resp.body)["override_count"], 0)
        # Audit log: create + clear.
        lines = self._tmp_audit.read_text(encoding="utf-8").strip().splitlines()
        events = [json.loads(line)["event"] for line in lines]
        self.assertEqual(events, ["create", "clear"])

    def test_delete_unknown_group_returns_404(self):
        resp = self._delete(self._sid, "g_PHANTOM")
        self.assertEqual(resp.status_code, 404)

    def test_pipeline_diag_unchanged_after_writes(self):
        # Capture diag before, write a few overrides, capture after.
        with M._SESSION_LOCK:
            diag_before = copy.deepcopy(M._SESSIONS[self._sid]["pipeline_diag"])
        self._post({
            "session_id": self._sid, "group_id": "g_a",
            "override_route_id": "route_476", "reason": "x",
        })
        self._post({
            "session_id": self._sid, "group_id": "g_b",
            "override_route_id": None, "reason": "force-abstain",
        })
        with M._SESSION_LOCK:
            diag_after = M._SESSIONS[self._sid]["pipeline_diag"]
        # No mutation. C1 is record-only — pipeline_diag rows untouched.
        self.assertEqual(diag_before, diag_after)
        # Specifically: selected_route_id / render_allowed / render_block_reasons
        # all unchanged on every row.
        for before, after in zip(diag_before, diag_after):
            self.assertEqual(
                before["selected_route_id"], after["selected_route_id"]
            )
            self.assertEqual(
                before["render_allowed"], after["render_allowed"]
            )
            self.assertEqual(
                before["render_block_reasons"], after["render_block_reasons"]
            )


class TestNoApplySeam(unittest.TestCase):
    """Prove Slice C2 is NOT present: the rebuild function does not consult
    STATE["match_overrides"] and the codebase has no apply-seam helper.
    """

    def test_rebuild_path_does_not_reference_match_overrides(self):
        # Read the source of `_rebuild_field_data_outputs` and assert it
        # does not contain a `match_overrides` STATE access (would indicate
        # a Slice C2 apply seam).
        import inspect
        src = inspect.getsource(M._rebuild_field_data_outputs)
        self.assertNotIn("match_overrides", src,
                          "Slice C1 must NOT add an apply seam in _rebuild_field_data_outputs")

    def test_no_apply_seam_helper_exists(self):
        # No public helper named `apply_match_override` etc. on the M module
        # or the match_override core module.
        self.assertFalse(hasattr(M, "apply_match_override"))
        self.assertFalse(hasattr(M, "_apply_match_override"))
        self.assertFalse(hasattr(MO, "apply_override"))
        self.assertFalse(hasattr(MO, "apply_overrides"))


if __name__ == "__main__":
    unittest.main()
