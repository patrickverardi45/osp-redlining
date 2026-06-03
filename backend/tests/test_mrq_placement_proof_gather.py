"""GAC Sprint 1 — placement-proof main.py plumbing tests (main-level).

Covers the three main.py seams added for the slice:
- `_trueline_mrq_placement_proof_enabled` runtime flag (default OFF, read every
  call, never import-cached).
- `_placement_counts_by_source` read-only aggregation of the persisted rendered
  geometry (STATE["station_points"] / STATE["redline_segments"]) by source_file.
- The `/api/match-review-queue` endpoint wiring: flag-OFF response is
  byte-identical to pre-slice; flag-ON adds exactly one top-level
  `placement_proof` key and nothing else, and its totals reconcile to the
  seeded rendered geometry (21 pts / 19 segs) — including logs the review queue
  intentionally OMITS (cleanly-placed bore_log71/72).

Imports main.py (needs `backend/` on sys.path so the `app.*` convention
resolves, same as the production entrypoint and the replay scripts).
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "backend"))

os.environ.setdefault("TRUELINE_JWT_SECRET", "mrq-placement-proof-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "mrq-placement-proof-auth-test-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend import main as M

_FLAG = "TRUELINE_MRQ_PLACEMENT_PROOF"
_PSG_FLAG = "TRUELINE_MRQ_PLAN_SHEET_GRAPH_EVIDENCE"


class TestFlagHelper(unittest.TestCase):

    def setUp(self):
        self._saved = os.environ.get(_FLAG)
        os.environ.pop(_FLAG, None)

    def tearDown(self):
        if self._saved is None:
            os.environ.pop(_FLAG, None)
        else:
            os.environ[_FLAG] = self._saved

    def test_default_off(self):
        self.assertFalse(M._trueline_mrq_placement_proof_enabled())

    def test_on_variants(self):
        for v in ("1", "true", "TRUE", "yes", "on", " On "):
            os.environ[_FLAG] = v
            self.assertTrue(M._trueline_mrq_placement_proof_enabled(), v)

    def test_off_variants(self):
        for v in ("0", "false", "no", "off", ""):
            os.environ[_FLAG] = v
            self.assertFalse(M._trueline_mrq_placement_proof_enabled(), v)


class TestPlacementCountsBySource(unittest.TestCase):

    def test_aggregates_points_and_segments(self):
        pts = [{"source_file": "a"}, {"source_file": "a"}, {"source_file": "b"}]
        segs = [{"source_file": "a"}]
        out = M._placement_counts_by_source(pts, segs)
        self.assertEqual(out["a"], {"station_pts": 2, "segs": 1})
        self.assertEqual(out["b"], {"station_pts": 1, "segs": 0})

    def test_ignores_non_dicts_and_blank_source(self):
        pts = [{"source_file": "a"}, "junk", 7, {"no_sf": 1}]
        out = M._placement_counts_by_source(pts, [])
        self.assertEqual(out["a"]["station_pts"], 1)
        self.assertEqual(out[""]["station_pts"], 1)  # missing source_file -> ""

    def test_empty(self):
        self.assertEqual(M._placement_counts_by_source([], []), {})


class TestEndpointByteIdenticalAndAdditive(unittest.TestCase):
    """Drives the real endpoint function with a seeded STATE and a no-op
    session scope, proving flag-OFF byte-identical + flag-ON additive-only."""

    def setUp(self):
        # Save + neutralize both MRQ flags (PSG must stay OFF for an isolated test).
        self._saved_flag = os.environ.get(_FLAG)
        self._saved_psg = os.environ.get(_PSG_FLAG)
        os.environ.pop(_FLAG, None)
        os.environ.pop(_PSG_FLAG, None)
        # Bypass tenant/session gating — the endpoint only needs STATE here.
        self._saved_scope = M._session_scope
        # Match the real _session_scope signature (now accepts readonly=).
        M._session_scope = lambda sid, readonly=False: contextlib.nullcontext()
        # Snapshot + seed STATE.
        self._saved_state = dict(M.STATE)
        M.STATE.clear()
        M.STATE.update({
            "pipeline_diag": [
                # cleanly PLACED via PDF-AP — the review queue OMITS these.
                {"source_file": "bore_log71.xlsx", "group_id": "g71",
                 "selected_route_id": "route_477", "render_allowed": True,
                 "strict_allowed_route_ids": ["route_477"],
                 "pdf_ap_route_authoritative": {"applied": True,
                                                "selected_route_id": "route_477",
                                                "pdf_allowed_route_ids": ["route_477"]}},
                {"source_file": "bore_log72.xlsx", "group_id": "g72",
                 "selected_route_id": "route_477", "render_allowed": True,
                 "strict_allowed_route_ids": ["route_477"],
                 "pdf_ap_route_authoritative": {"applied": True,
                                                "selected_route_id": "route_477",
                                                "pdf_allowed_route_ids": ["route_477"]}},
                # ABSTAINED — appears in the review queue.
                {"source_file": "bore_log39.xlsx", "group_id": "g39",
                 "render_allowed": False,
                 "stopped_at": "abstained_location_evidence_mismatch"},
            ],
            # Rendered geometry: 10+11 = 21 pts, 9+10 = 19 segs (bore_log39 none).
            "station_points": (
                [{"source_file": "bore_log71.xlsx"}] * 10
                + [{"source_file": "bore_log72.xlsx"}] * 11
            ),
            "redline_segments": (
                [{"source_file": "bore_log71.xlsx"}] * 9
                + [{"source_file": "bore_log72.xlsx"}] * 10
            ),
        })

    def tearDown(self):
        M._session_scope = self._saved_scope
        M.STATE.clear()
        M.STATE.update(self._saved_state)
        for flag, saved in ((_FLAG, self._saved_flag), (_PSG_FLAG, self._saved_psg)):
            if saved is None:
                os.environ.pop(flag, None)
            else:
                os.environ[flag] = saved

    def _call(self):
        resp = M.match_review_queue_endpoint(session_id="s1")
        return json.loads(resp.body)

    def test_flag_off_has_no_placement_proof_key(self):
        body = self._call()
        self.assertNotIn("placement_proof", body)
        # the review queue surfaces only the abstained log, not the placed ones.
        queue_sources = {r.get("source_file") for r in body.get("rows", [])}
        self.assertIn("bore_log39.xlsx", queue_sources)
        self.assertNotIn("bore_log71.xlsx", queue_sources)

    def test_flag_on_is_additive_only(self):
        body_off = self._call()
        os.environ[_FLAG] = "1"
        body_on = self._call()
        # exactly one new top-level key.
        self.assertIn("placement_proof", body_on)
        stripped = {k: v for k, v in body_on.items() if k != "placement_proof"}
        self.assertEqual(stripped, body_off)

    def test_flag_on_totals_reconcile_and_capture_placed_logs(self):
        os.environ[_FLAG] = "1"
        pp = self._call()["placement_proof"]
        rows = {r["source_file"]: r for r in pp["rows"]}
        # all three logs present — including the queue-omitted placed ones.
        self.assertEqual(set(rows), {"bore_log71.xlsx", "bore_log72.xlsx", "bore_log39.xlsx"})
        self.assertEqual(rows["bore_log71.xlsx"]["evidence_source"], "pdf_ap_authoritative")
        self.assertEqual(rows["bore_log71.xlsx"]["selected_route_id"], "route_477")
        self.assertEqual(rows["bore_log72.xlsx"]["evidence_source"], "pdf_ap_authoritative")
        self.assertEqual(rows["bore_log39.xlsx"]["evidence_source"], "abstained")
        self.assertEqual(pp["totals"], {"placed_logs": 2, "abstained_logs": 1,
                                        "station_pts": 21, "segs": 19})


if __name__ == "__main__":
    unittest.main()
