"""PDF Plan Mode Step 3A — manual station segment CRUD tests.

Targets:
  - ``get_engineering_plan_segments`` (GET)
  - ``post_engineering_plan_segment`` (POST)
  - ``delete_engineering_plan_segment`` (DELETE)
  - helper module ``app.core.pdf_plan_segment_store``

The POST endpoint requires a saved trace with >= 2 anchors before
allowing segment creation; the fixture builds a real trace on disk so
the precondition path is exercised end-to-end.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

os.environ.setdefault("TRUELINE_JWT_SECRET", "pdf-plan-segments-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "pdf-plan-segments-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend import main as M  # noqa: E402
from backend.app.core import pdf_plan_segment_store as SS  # noqa: E402
from backend.app.core import pdf_plan_trace_store as TS  # noqa: E402

_FLAG = "TRUELINE_PLAN_OVERLAY_IMAGE"


def _make_plan_record(plan_id: str, session_id: str, target: Path) -> Dict[str, Any]:
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


def _seed_trace_with_anchors(
    eng_root: Path,
    session_id: str,
    plan_id: str,
    page_index: int,
) -> Dict[str, Any]:
    """Helper to create a saved trace with two valid station anchors so
    the POST endpoint's precondition is satisfied."""
    payload = {
        "page_dpi": 96,
        "page_size_px": [1700, 1100],
        "points": [[100.0, 200.0], [400.0, 200.0], [700.0, 200.0]],
        "anchors": [
            {"label": "0+00", "point": [100.0, 200.0]},
            {"label": "10+00", "point": [700.0, 200.0]},
        ],
    }
    return TS.save_trace(eng_root, session_id, plan_id, page_index, payload)


class _BaseSegmentEndpointTest(unittest.TestCase):
    SESSION_ID = "sess_test_pdfplansegments"
    PLAN_ID = "abc123def456pdfplan3a"
    PAGE_INDEX = 0

    def setUp(self) -> None:
        self._saved_flag = os.environ.pop(_FLAG, None)
        self._tmp_root = Path(tempfile.mkdtemp(prefix="pdf_plan_segments_"))
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
        self._patches.append(patch.object(M, "_is_closeout_locked", return_value=False))

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
        return asyncio.run(M.get_engineering_plan_segments(**defaults))

    def _post(self, payload: Dict[str, Any], **kwargs: Any) -> Any:
        defaults: Dict[str, Any] = {
            "plan_id": self.PLAN_ID,
            "page_index": self.PAGE_INDEX,
            "session_id": self.SESSION_ID,
            "payload": payload,
            "request": None,
        }
        defaults.update(kwargs)
        return asyncio.run(M.post_engineering_plan_segment(**defaults))

    def _delete(self, segment_id: str, **kwargs: Any) -> Any:
        defaults: Dict[str, Any] = {
            "plan_id": self.PLAN_ID,
            "segment_id": segment_id,
            "page_index": self.PAGE_INDEX,
            "session_id": self.SESSION_ID,
            "request": None,
        }
        defaults.update(kwargs)
        return asyncio.run(M.delete_engineering_plan_segment(**defaults))


# ───────────────────────────────────────────────────────────────────────────
# Endpoint behavior
# ───────────────────────────────────────────────────────────────────────────


class T1_FlagOff(_BaseSegmentEndpointTest):
    def test_get_returns_404_when_flag_off(self) -> None:
        os.environ.pop(_FLAG, None)
        self.assertEqual(self._get().status_code, 404)

    def test_post_returns_404_when_flag_off(self) -> None:
        os.environ.pop(_FLAG, None)
        self.assertEqual(self._post({"label": "x", "start_label": "0+00", "end_label": "10+00"}).status_code, 404)

    def test_delete_returns_404_when_flag_off(self) -> None:
        os.environ.pop(_FLAG, None)
        self.assertEqual(self._delete("none").status_code, 404)


class T2_GetEmptyEnvelope(_BaseSegmentEndpointTest):
    def test_get_returns_empty_envelope_when_no_segments(self) -> None:
        # No trace required for GET; empty envelope returned.
        resp = self._get()
        self.assertEqual(resp.status_code, 200)
        body = _read_body(resp)
        env = body.get("envelope") or {}
        self.assertEqual(env.get("schema_version"), "pdf-plan-segments-1")
        self.assertEqual(env.get("segments"), [])


class T3_PostRequiresTrace(_BaseSegmentEndpointTest):
    def test_post_409_when_no_trace_yet(self) -> None:
        resp = self._post({"label": "Bore A", "start_label": "11+60", "end_label": "14+20"})
        self.assertEqual(resp.status_code, 409)
        body = _read_body(resp)
        self.assertIn("no trace", (body.get("error") or "").lower())

    def test_post_409_when_trace_has_no_anchors(self) -> None:
        # Save a trace with NO anchors.
        TS.save_trace(
            self._eng_root,
            self.SESSION_ID,
            self.PLAN_ID,
            self.PAGE_INDEX,
            {
                "page_dpi": 96,
                "page_size_px": [1700, 1100],
                "points": [[100.0, 200.0], [400.0, 200.0]],
                "anchors": [],
            },
        )
        resp = self._post({"label": "Bore A", "start_label": "11+60", "end_label": "14+20"})
        self.assertEqual(resp.status_code, 409)
        body = _read_body(resp)
        self.assertIn("station anchors", (body.get("error") or "").lower())


class T4_FullCrudCycle(_BaseSegmentEndpointTest):
    def setUp(self) -> None:
        super().setUp()
        _seed_trace_with_anchors(
            self._eng_root, self.SESSION_ID, self.PLAN_ID, self.PAGE_INDEX
        )

    def test_post_get_delete_cycle(self) -> None:
        # POST: add a segment by label
        post_resp = self._post({
            "label": "Bore 1",
            "start_label": "1+50",
            "end_label": "8+50",
            "notes": "test bore",
        })
        self.assertEqual(post_resp.status_code, 200)
        body = _read_body(post_resp)
        env = body["envelope"]
        self.assertEqual(env["schema_version"], "pdf-plan-segments-1")
        self.assertEqual(len(env["segments"]), 1)
        seg = env["segments"][0]
        self.assertEqual(seg["label"], "Bore 1")
        self.assertEqual(seg["start_label"], "1+50")
        self.assertEqual(seg["end_label"], "8+50")
        self.assertEqual(seg["start_station_ft"], 150.0)
        self.assertEqual(seg["end_station_ft"], 850.0)
        self.assertEqual(seg["notes"], "test bore")
        seg_id = seg["segment_id"]
        self.assertEqual(env.get("trace_id"), TS._generate_trace_id(self.PLAN_ID, self.SESSION_ID, self.PAGE_INDEX))

        # GET: retrieve segments
        get_resp = self._get()
        self.assertEqual(get_resp.status_code, 200)
        get_body = _read_body(get_resp)
        self.assertEqual(len(get_body["envelope"]["segments"]), 1)

        # POST a second segment with raw station_ft numbers
        post2 = self._post({
            "label": "Bore 2",
            "start_station_ft": 200.0,
            "end_station_ft": 500.0,
        })
        self.assertEqual(post2.status_code, 200)
        body2 = _read_body(post2)
        self.assertEqual(len(body2["envelope"]["segments"]), 2)
        seg2 = body2["envelope"]["segments"][1]
        # Auto-derived labels from station_ft
        self.assertEqual(seg2["start_label"], "2+00")
        self.assertEqual(seg2["end_label"], "5+00")

        # DELETE the first segment
        del_resp = self._delete(seg_id)
        self.assertEqual(del_resp.status_code, 200)
        del_body = _read_body(del_resp)
        self.assertTrue(del_body["removed"])
        self.assertEqual(len(del_body["envelope"]["segments"]), 1)
        self.assertEqual(del_body["envelope"]["segments"][0]["label"], "Bore 2")

        # DELETE the second segment — empty list, file removed
        del2 = self._delete(body2["envelope"]["segments"][1]["segment_id"])
        self.assertEqual(del2.status_code, 200)
        self.assertEqual(_read_body(del2)["envelope"]["segments"], [])

        # GET now returns the empty envelope again
        final_get = self._get()
        self.assertEqual(final_get.status_code, 200)
        self.assertEqual(_read_body(final_get)["envelope"]["segments"], [])


class T5_PostValidation(_BaseSegmentEndpointTest):
    def setUp(self) -> None:
        super().setUp()
        _seed_trace_with_anchors(
            self._eng_root, self.SESSION_ID, self.PLAN_ID, self.PAGE_INDEX
        )

    def test_missing_label_400(self) -> None:
        resp = self._post({"start_label": "1+00", "end_label": "2+00"})
        self.assertEqual(resp.status_code, 400)

    def test_missing_both_start_fields_400(self) -> None:
        resp = self._post({"label": "x", "end_label": "2+00"})
        self.assertEqual(resp.status_code, 400)

    def test_unparseable_station_400(self) -> None:
        resp = self._post({"label": "x", "start_label": "garbage", "end_label": "2+00"})
        self.assertEqual(resp.status_code, 400)

    def test_duplicate_segment_rejected(self) -> None:
        first = self._post({"label": "dup", "start_label": "1+00", "end_label": "2+00"})
        self.assertEqual(first.status_code, 200)
        second = self._post({"label": "dup", "start_label": "1+00", "end_label": "2+00"})
        self.assertEqual(second.status_code, 400)


class T6_DeleteIdempotent(_BaseSegmentEndpointTest):
    def test_delete_unknown_segment_id_returns_removed_false(self) -> None:
        resp = self._delete("does_not_exist")
        self.assertEqual(resp.status_code, 200)
        body = _read_body(resp)
        self.assertFalse(body["removed"])


class T7_NegativePageIndex(_BaseSegmentEndpointTest):
    def test_get_rejects_negative_page_index(self) -> None:
        self.assertEqual(self._get(page_index=-1).status_code, 400)

    def test_post_rejects_negative_page_index(self) -> None:
        resp = self._post(
            {"label": "x", "start_label": "0+00", "end_label": "1+00"},
            page_index=-1,
        )
        self.assertEqual(resp.status_code, 400)

    def test_delete_rejects_negative_page_index(self) -> None:
        self.assertEqual(self._delete("any", page_index=-1).status_code, 400)


# ───────────────────────────────────────────────────────────────────────────
# Helper-module direct tests
# ───────────────────────────────────────────────────────────────────────────


class T8_StoreNormalize(unittest.TestCase):
    def test_normalize_from_labels(self) -> None:
        out = SS.normalize_segment_payload({
            "label": "Bore A",
            "start_label": "11+60",
            "end_label": "14+20",
            "notes": "  some text  ",
        })
        self.assertEqual(out["start_station_ft"], 1160.0)
        self.assertEqual(out["end_station_ft"], 1420.0)
        self.assertEqual(out["start_label"], "11+60")
        self.assertEqual(out["end_label"], "14+20")
        self.assertEqual(out["notes"], "some text")
        self.assertIn("segment_id", out)
        self.assertIn("created_at", out)

    def test_normalize_from_explicit_ft(self) -> None:
        out = SS.normalize_segment_payload({
            "label": "Bore B",
            "start_station_ft": 1160.0,
            "end_station_ft": 1420.0,
        })
        # Auto-derived labels
        self.assertEqual(out["start_label"], "11+60")
        self.assertEqual(out["end_label"], "14+20")

    def test_label_overrides_explicit_label_when_both_present(self) -> None:
        out = SS.normalize_segment_payload({
            "label": "Override",
            "start_station_ft": 1160.0,
            "start_label": "STA 11+60",
            "end_station_ft": 1420.0,
            "end_label": "STA 14+20",
        })
        # Explicit station_ft wins; label kept as supplied (trimmed)
        self.assertEqual(out["start_station_ft"], 1160.0)
        self.assertEqual(out["start_label"], "STA 11+60")

    def test_long_notes_trimmed(self) -> None:
        out = SS.normalize_segment_payload({
            "label": "x",
            "start_label": "0+00",
            "end_label": "1+00",
            "notes": "a" * 500,
        })
        self.assertEqual(len(out["notes"]), 280)


class T9b_SourceFieldsStep3B(unittest.TestCase):
    """Step 3B — source + source_metadata fields are backward-compatible
    additions to pdf-plan-segments-1.  Existing payloads without these
    fields default to source='manual' with an empty metadata dict."""

    def test_default_source_is_manual(self) -> None:
        out = SS.normalize_segment_payload({
            "label": "Bore A",
            "start_label": "1+00",
            "end_label": "2+00",
        })
        self.assertEqual(out["source"], "manual")
        self.assertEqual(out["source_metadata"], {})

    def test_source_bore_log_row_accepted(self) -> None:
        out = SS.normalize_segment_payload({
            "label": "Bore A",
            "start_label": "16+79",
            "end_label": "19+54",
            "source": "bore_log_row",
            "source_metadata": {
                "depth": "6.0",
                "boc": "8.0",
                "crew": "Smith",
                "date": "2026-05-26",
            },
        })
        self.assertEqual(out["source"], "bore_log_row")
        self.assertEqual(out["source_metadata"]["depth"], "6.0")
        self.assertEqual(out["source_metadata"]["crew"], "Smith")

    def test_unknown_source_falls_back_to_manual(self) -> None:
        out = SS.normalize_segment_payload({
            "label": "Bore A",
            "start_label": "1+00",
            "end_label": "2+00",
            "source": "made_up_source",
        })
        self.assertEqual(out["source"], "manual")

    def test_source_metadata_keys_capped(self) -> None:
        big_md = {f"key_{i}": f"val_{i}" for i in range(30)}
        out = SS.normalize_segment_payload({
            "label": "Bore A",
            "start_label": "1+00",
            "end_label": "2+00",
            "source": "bore_log_row",
            "source_metadata": big_md,
        })
        # Capped at _SOURCE_META_KEY_COUNT_MAX (16)
        self.assertLessEqual(len(out["source_metadata"]), 16)

    def test_source_metadata_value_trimmed(self) -> None:
        long_val = "x" * 500
        out = SS.normalize_segment_payload({
            "label": "Bore A",
            "start_label": "1+00",
            "end_label": "2+00",
            "source": "bore_log_row",
            "source_metadata": {"notes_long": long_val},
        })
        # Capped at _SOURCE_META_VALUE_MAX (128)
        self.assertLessEqual(len(out["source_metadata"]["notes_long"]), 128)


class T9_PathSafety(unittest.TestCase):
    def test_traversal_rejected(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="pdf_plan_seg_path_"))
        try:
            with self.assertRaises(SS.PdfPlanSegmentStoreError):
                SS.segments_file_path(root, "../escape", "plan", 0)
            with self.assertRaises(SS.PdfPlanSegmentStoreError):
                SS.segments_file_path(root, "sess", "../escape", 0)
            with self.assertRaises(SS.PdfPlanSegmentStoreError):
                SS.segments_file_path(root, "sess", "plan", -1)
        finally:
            root.rmdir()


if __name__ == "__main__":
    unittest.main()
