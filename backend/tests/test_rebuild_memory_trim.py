"""LP.4 — ROWS_ONLY rebuild peak-memory: internal-field trim + instrumentation.

The matcher must hold every group's candidate detail through batch/collision
resolution, so peak memory grows with group count and was killing the Render
worker mid-rebuild on the 58-log Brenham run. These helpers reduce/observe that
peak WITHOUT changing redline truth:

- _trim_rebuild_internal_fields drops rebuild-INTERNAL fields (_normalized_group,
  _matched_route, _evaluated_hypotheses) that no post-rebuild consumer reads,
  freeing memory ahead of the peak and shrinking the persisted session. It must
  NOT drop map outputs / MRQ-visible fields, and must honor the keep flag.
- _rss_mb / _rebuild_log_mem are pure diagnostics and must never raise.

Run from repo root:
    python -m pytest backend/tests/test_rebuild_memory_trim.py -v
"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("TRUELINE_JWT_SECRET", "rebuild-mem-test")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "rebuild-mem-auth")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend import main as M  # noqa: E402 — after env defaults


def _sample_group_matches():
    return [
        {
            "group_id": "g1",
            "route_id": "route_1",
            "candidate_rankings": [{"route_id": "route_1", "score": 0.9}],
            "validation": {"validation_status": "pass"},
            "group_station_points": [{"x": 1}],
            "group_redline_segments": [{"a": 1}],
            "render_allowed": True,
            # heavy rebuild-internal fields:
            "_normalized_group": {"big": "x" * 1000},
            "_matched_route": {"big": "y" * 1000},
            "_evaluated_hypotheses": [{"h": "z" * 1000}],
        }
    ]


class TestTrimRebuildInternalFields(unittest.TestCase):
    def test_default_drops_internal_keeps_public(self):
        prev = os.environ.pop("TRUELINE_REBUILD_KEEP_INTERNALS", None)
        try:
            gm = _sample_group_matches()
            M._trim_rebuild_internal_fields(gm)
            m = gm[0]
            # internal scoring structures dropped
            self.assertNotIn("_normalized_group", m)
            self.assertNotIn("_matched_route", m)
            self.assertNotIn("_evaluated_hypotheses", m)
            # map outputs + MRQ-visible fields preserved
            self.assertIn("candidate_rankings", m)
            self.assertIn("validation", m)
            self.assertIn("group_station_points", m)
            self.assertIn("group_redline_segments", m)
            self.assertEqual(m["route_id"], "route_1")
            self.assertTrue(m["render_allowed"])
        finally:
            if prev is not None:
                os.environ["TRUELINE_REBUILD_KEEP_INTERNALS"] = prev

    def test_subset_fields_only(self):
        prev = os.environ.pop("TRUELINE_REBUILD_KEEP_INTERNALS", None)
        try:
            gm = _sample_group_matches()
            M._trim_rebuild_internal_fields(gm, ("_evaluated_hypotheses",))
            m = gm[0]
            self.assertNotIn("_evaluated_hypotheses", m)
            self.assertIn("_normalized_group", m)  # not requested -> retained
            self.assertIn("_matched_route", m)
        finally:
            if prev is not None:
                os.environ["TRUELINE_REBUILD_KEEP_INTERNALS"] = prev

    def test_keep_internals_flag_retains_all(self):
        prev = os.environ.get("TRUELINE_REBUILD_KEEP_INTERNALS")
        os.environ["TRUELINE_REBUILD_KEEP_INTERNALS"] = "1"
        try:
            gm = _sample_group_matches()
            M._trim_rebuild_internal_fields(gm)
            m = gm[0]
            self.assertIn("_normalized_group", m)
            self.assertIn("_matched_route", m)
            self.assertIn("_evaluated_hypotheses", m)
        finally:
            if prev is None:
                os.environ.pop("TRUELINE_REBUILD_KEEP_INTERNALS", None)
            else:
                os.environ["TRUELINE_REBUILD_KEEP_INTERNALS"] = prev


class TestRebuildMemHelpers(unittest.TestCase):
    def test_rss_mb_returns_float_or_none(self):
        v = M._rss_mb()
        self.assertTrue(v is None or isinstance(v, float))

    def test_log_mem_never_raises(self):
        # Must be safe with arbitrary context and never raise.
        M._rebuild_log_mem("test_tag", grp=0, of=58, cands=3, group_matches=12)
        M._rebuild_log_mem("bare")


if __name__ == "__main__":
    unittest.main()
