"""PDF Plan Mode Step 2B — trace CRUD endpoint + helper tests.

Targets:
- ``get_engineering_plan_trace`` (GET)
- ``put_engineering_plan_trace`` (PUT)
- ``delete_engineering_plan_trace`` (DELETE)
- helper module ``app.core.pdf_plan_trace_store``

Mirrors the pattern of test_pdf_plan_index_endpoint.py / test_eng_plan_
page_image_endpoint.py: env defaults at module top, raw-index mock
returns a realistic plan record, temp tree for disk I/O.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

os.environ.setdefault("TRUELINE_JWT_SECRET", "pdf-plan-trace-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "pdf-plan-trace-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend import main as M  # noqa: E402
from backend.app.core import pdf_plan_trace_store as TS  # noqa: E402

_FLAG = "TRUELINE_PLAN_OVERLAY_IMAGE"


def _make_plan_record(plan_id: str, session_id: str, target: Path) -> Dict[str, Any]:
    # PUT/DELETE check closeout-lock via _is_closeout_locked() which reads
    # STATE — under the _session_scope we mock both. A pdf must exist on
    # disk to satisfy the file-not-found 404 path in case future tests
    # exercise it; here we just need the index lookup to succeed.
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_bytes(b"%PDF-1.4\nfake-bytes-for-test\n")
    return {
        "plan_id": plan_id,
        "session_id": session_id,
        "original_filename": target.name,
        "stored_filename": target.name,
        "stored_path": str(target),
        "file_type": "application/pdf",
        "size_bytes": target.stat().st_size,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }


def _read_body(response: Any) -> Dict[str, Any]:
    body = response.body
    if isinstance(body, (bytes, bytearray)):
        return json.loads(body.decode("utf-8"))
    return json.loads(body)


class _BaseTraceEndpointTest(unittest.TestCase):
    SESSION_ID = "sess_test_pdfplantrace"
    PLAN_ID = "abc123def456pdfplan2b"
    PAGE_INDEX = 0

    def setUp(self) -> None:
        self._saved_flag = os.environ.pop(_FLAG, None)
        self._tmp_root = Path(tempfile.mkdtemp(prefix="pdf_plan_trace_"))
        self._uploads_dir = self._tmp_root / "uploads"
        self._eng_root = self._uploads_dir / "engineering_plans"
        self._sess_folder = self._eng_root / self.SESSION_ID
        self._sess_folder.mkdir(parents=True, exist_ok=True)
        self._pdf_path = self._sess_folder / "test_plan.pdf"
        self._plan = _make_plan_record(self.PLAN_ID, self.SESSION_ID, self._pdf_path)

        self._patches: List[Any] = []
        self._patches.append(patch.object(M, "_resolve_session_id", return_value=self.SESSION_ID))
        self._patches.append(patch.object(M, "_require_tenant_owns_session", return_value=None))
        self._patches.append(patch.object(
            M, "_load_engineering_plan_index", return_value={"plans": [self._plan]}
        ))
        self._patches.append(patch.object(M, "ENGINEERING_PLAN_ROOT", self._eng_root))
        # _is_closeout_locked must return False so PUT/DELETE proceed.
        self._patches.append(patch.object(M, "_is_closeout_locked", return_value=False))
        # _session_scope is a context manager — patch it with a real cm.
        from contextlib import contextmanager

        @contextmanager
        def _noop_scope(sid: str):
            yield sid

        self._patches.append(patch.object(M, "_session_scope", _noop_scope))

        for p in self._patches:
            p.start()
        os.environ[_FLAG] = "1"

    def tearDown(self) -> None:
        for p in self._patches:
            try:
                p.stop()
            except RuntimeError:
                pass
        if self._saved_flag is None:
            os.environ.pop(_FLAG, None)
        else:
            os.environ[_FLAG] = self._saved_flag
        for p in sorted(self._tmp_root.rglob("*"), reverse=True):
            try:
                if p.is_file():
                    p.unlink()
                else:
                    p.rmdir()
            except OSError:
                pass
        try:
            self._tmp_root.rmdir()
        except OSError:
            pass

    def _get(self, **kwargs: Any) -> Any:
        defaults = {
            "plan_id": self.PLAN_ID,
            "page_index": self.PAGE_INDEX,
            "session_id": self.SESSION_ID,
            "request": None,
        }
        defaults.update(kwargs)
        return asyncio.run(M.get_engineering_plan_trace(**defaults))

    def _put(self, payload: Dict[str, Any], **kwargs: Any) -> Any:
        defaults: Dict[str, Any] = {
            "plan_id": self.PLAN_ID,
            "page_index": self.PAGE_INDEX,
            "session_id": self.SESSION_ID,
            "payload": payload,
            "request": None,
        }
        defaults.update(kwargs)
        return asyncio.run(M.put_engineering_plan_trace(**defaults))

    def _delete(self, **kwargs: Any) -> Any:
        defaults = {
            "plan_id": self.PLAN_ID,
            "page_index": self.PAGE_INDEX,
            "session_id": self.SESSION_ID,
            "request": None,
        }
        defaults.update(kwargs)
        return asyncio.run(M.delete_engineering_plan_trace(**defaults))


def _sample_payload(num_points: int = 4, with_anchor: bool = True) -> Dict[str, Any]:
    points = [[100.0 + i * 50.0, 200.0 + i * 20.0] for i in range(num_points)]
    payload: Dict[str, Any] = {
        "page_dpi": 96,
        "page_size_px": [1700, 1100],
        "points": points,
    }
    if with_anchor:
        payload["anchors"] = [
            {"label": "11+60", "point": [100.0, 200.0]},
            {"label": "STA 14+20", "point": [200.0, 240.0]},
        ]
    return payload


# ───────────────────────────────────────────────────────────────────────────
# Endpoint behavior
# ───────────────────────────────────────────────────────────────────────────


class T1_FlagOff(_BaseTraceEndpointTest):
    def test_get_returns_404_when_flag_off(self) -> None:
        os.environ.pop(_FLAG, None)
        response = self._get()
        self.assertEqual(response.status_code, 404)

    def test_put_returns_404_when_flag_off(self) -> None:
        os.environ.pop(_FLAG, None)
        response = self._put(_sample_payload())
        self.assertEqual(response.status_code, 404)

    def test_delete_returns_404_when_flag_off(self) -> None:
        os.environ.pop(_FLAG, None)
        response = self._delete()
        self.assertEqual(response.status_code, 404)


class T2_GetNoTrace(_BaseTraceEndpointTest):
    def test_get_returns_404_when_no_trace_saved(self) -> None:
        response = self._get()
        self.assertEqual(response.status_code, 404)
        body = _read_body(response)
        self.assertIn("no trace saved", (body.get("error") or "").lower())


class T3_PutThenGetThenDelete(_BaseTraceEndpointTest):
    def test_full_cycle(self) -> None:
        # PUT: save a fresh trace
        put_response = self._put(_sample_payload())
        self.assertEqual(put_response.status_code, 200)
        put_body = _read_body(put_response)
        self.assertTrue(put_body.get("success"))
        trace = put_body.get("trace")
        self.assertIsNotNone(trace)
        self.assertEqual(trace.get("schema_version"), "pdf-plan-trace-1")
        self.assertEqual(trace.get("plan_id"), self.PLAN_ID)
        self.assertEqual(trace.get("session_id"), self.SESSION_ID)
        self.assertEqual(trace.get("page_index"), self.PAGE_INDEX)
        self.assertEqual(len(trace.get("points") or []), 4)
        self.assertEqual(len(trace.get("anchors") or []), 2)
        # Station normalization
        first_anchor = trace["anchors"][0]
        self.assertEqual(first_anchor.get("label"), "11+60")
        self.assertEqual(first_anchor.get("station_ft"), 1160.0)
        second_anchor = trace["anchors"][1]
        # "STA 14+20" -> 1420.0
        self.assertEqual(second_anchor.get("station_ft"), 1420.0)

        # GET: retrieve the same trace
        get_response = self._get()
        self.assertEqual(get_response.status_code, 200)
        get_body = _read_body(get_response)
        self.assertEqual(get_body.get("trace", {}).get("schema_version"), "pdf-plan-trace-1")
        self.assertEqual(len(get_body["trace"]["points"]), 4)

        # DELETE: remove the trace
        del_response = self._delete()
        self.assertEqual(del_response.status_code, 200)
        del_body = _read_body(del_response)
        self.assertTrue(del_body.get("removed"))

        # GET: should now 404 again
        get2 = self._get()
        self.assertEqual(get2.status_code, 404)


class T4_PutValidation(_BaseTraceEndpointTest):
    def test_put_rejects_payload_with_one_point(self) -> None:
        payload = _sample_payload(num_points=1)
        response = self._put(payload)
        self.assertEqual(response.status_code, 400)
        body = _read_body(response)
        self.assertIn("invalid trace payload", (body.get("error") or "").lower())

    def test_put_rejects_missing_page_size_px(self) -> None:
        payload = _sample_payload()
        payload.pop("page_size_px", None)
        response = self._put(payload)
        self.assertEqual(response.status_code, 400)

    def test_put_rejects_out_of_range_coords(self) -> None:
        payload = _sample_payload()
        payload["points"] = [[100.0, 200.0], [-5.0, 300.0]]  # negative x
        response = self._put(payload)
        self.assertEqual(response.status_code, 400)

    def test_put_rejects_unparseable_station(self) -> None:
        payload = _sample_payload(with_anchor=False)
        payload["anchors"] = [{"label": "not a station", "point": [100.0, 200.0]}]
        response = self._put(payload)
        self.assertEqual(response.status_code, 400)

    def test_put_rejects_too_many_anchors(self) -> None:
        payload = _sample_payload(with_anchor=False)
        payload["anchors"] = [
            {"label": f"{i}+00", "point": [100.0 + i, 200.0]}
            for i in range(60)  # cap is 50
        ]
        response = self._put(payload)
        self.assertEqual(response.status_code, 400)


class T5_DeleteIdempotent(_BaseTraceEndpointTest):
    def test_delete_when_nothing_saved_returns_200_with_removed_false(self) -> None:
        response = self._delete()
        self.assertEqual(response.status_code, 200)
        body = _read_body(response)
        self.assertFalse(body.get("removed"))


class T6_NegativePageIndex(_BaseTraceEndpointTest):
    def test_get_rejects_negative_page_index(self) -> None:
        response = self._get(page_index=-1)
        self.assertEqual(response.status_code, 400)

    def test_put_rejects_negative_page_index(self) -> None:
        response = self._put(_sample_payload(), page_index=-1)
        self.assertEqual(response.status_code, 400)

    def test_delete_rejects_negative_page_index(self) -> None:
        response = self._delete(page_index=-1)
        self.assertEqual(response.status_code, 400)


class T7_StableTraceIdAcrossSaves(_BaseTraceEndpointTest):
    def test_trace_id_stable_across_resaves(self) -> None:
        r1 = self._put(_sample_payload(num_points=3))
        r2 = self._put(_sample_payload(num_points=5))
        t1 = _read_body(r1)["trace"]
        t2 = _read_body(r2)["trace"]
        self.assertEqual(t1["trace_id"], t2["trace_id"])
        # created_at preserved across re-save
        self.assertEqual(t1["created_at"], t2["created_at"])
        # updated_at refreshed
        self.assertGreaterEqual(t2["updated_at"], t1["updated_at"])
        # New point count reflected
        self.assertEqual(len(t1["points"]), 3)
        self.assertEqual(len(t2["points"]), 5)


class T8_MultiPageIsolation(_BaseTraceEndpointTest):
    def test_traces_for_different_pages_are_independent(self) -> None:
        r0 = self._put(_sample_payload(num_points=2), page_index=0)
        self.assertEqual(r0.status_code, 200)
        r1 = self._put(_sample_payload(num_points=3), page_index=1)
        self.assertEqual(r1.status_code, 200)
        t0 = _read_body(r0)["trace"]
        t1 = _read_body(r1)["trace"]
        # Different trace_ids per page
        self.assertNotEqual(t0["trace_id"], t1["trace_id"])
        # Each page independently retrievable
        g0 = _read_body(self._get(page_index=0))
        g1 = _read_body(self._get(page_index=1))
        self.assertEqual(len(g0["trace"]["points"]), 2)
        self.assertEqual(len(g1["trace"]["points"]), 3)
        # Deleting one leaves the other
        self._delete(page_index=0)
        g0_after = self._get(page_index=0)
        self.assertEqual(g0_after.status_code, 404)
        g1_after = self._get(page_index=1)
        self.assertEqual(g1_after.status_code, 200)


# ───────────────────────────────────────────────────────────────────────────
# Helper-module direct tests (station label parsing + path safety)
# ───────────────────────────────────────────────────────────────────────────


class T9_StationLabelParsing(unittest.TestCase):
    def test_standard_plus_format(self) -> None:
        self.assertEqual(TS.parse_station_label_to_ft("11+60"), 1160.0)
        self.assertEqual(TS.parse_station_label_to_ft("0+00"), 0.0)
        self.assertEqual(TS.parse_station_label_to_ft("123+45"), 12345.0)

    def test_with_sta_prefix(self) -> None:
        self.assertEqual(TS.parse_station_label_to_ft("STA 11+60"), 1160.0)
        self.assertEqual(TS.parse_station_label_to_ft("sta 14+20"), 1420.0)
        self.assertEqual(TS.parse_station_label_to_ft("STA  11+60"), 1160.0)

    def test_fractional_remainder(self) -> None:
        self.assertEqual(TS.parse_station_label_to_ft("11+60.5"), 1160.5)

    def test_raw_feet_fallback(self) -> None:
        self.assertEqual(TS.parse_station_label_to_ft("1160"), 1160.0)
        self.assertEqual(TS.parse_station_label_to_ft("0"), 0.0)

    def test_unparseable_raises(self) -> None:
        with self.assertRaises(TS.PdfPlanTraceStoreError):
            TS.parse_station_label_to_ft("hello")
        with self.assertRaises(TS.PdfPlanTraceStoreError):
            TS.parse_station_label_to_ft("")

    def test_format_round_trip(self) -> None:
        self.assertEqual(TS.format_station_ft_to_label(1160.0), "11+60")
        self.assertEqual(TS.format_station_ft_to_label(0.0), "0+00")
        self.assertEqual(TS.format_station_ft_to_label(12345.0), "123+45")
        # Fractional
        self.assertIn("+", TS.format_station_ft_to_label(1160.5))


class T10_PathSafety(unittest.TestCase):
    def test_rejects_traversal_in_session_id(self) -> None:
        eng_root = Path(tempfile.mkdtemp(prefix="pdf_plan_trace_safety_"))
        try:
            with self.assertRaises(TS.PdfPlanTraceStoreError):
                TS.trace_file_path(eng_root, "../escape", "plan", 0)
            with self.assertRaises(TS.PdfPlanTraceStoreError):
                TS.trace_file_path(eng_root, "good", "../escape", 0)
        finally:
            eng_root.rmdir()

    def test_rejects_negative_page_index(self) -> None:
        eng_root = Path(tempfile.mkdtemp(prefix="pdf_plan_trace_safety_"))
        try:
            with self.assertRaises(TS.PdfPlanTraceStoreError):
                TS.trace_file_path(eng_root, "sess", "plan", -1)
        finally:
            eng_root.rmdir()


if __name__ == "__main__":
    unittest.main()
