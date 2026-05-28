"""Brenham Plan Sheet Station Graph — shadow telemetry + flag-gate tests.

Covers: row schema, append, flag default OFF, seam no-op when flag OFF, seam
writes one row per group when flag ON, Stage-A invariant unchanged, and an
inspect lock proving the rebuild path makes no route scoring/selection change.
"""

from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List

os.environ.setdefault("TRUELINE_JWT_SECRET", "brenham-psg-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "brenham-psg-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend import main as M
from backend.app.core import brenham_plan_sheet_graph as G
from backend.app.core import brenham_plan_sheet_graph_shadow_telemetry as TEL

_FLAG = "TRUELINE_BRENHAM_PLAN_SHEET_GRAPH_SHADOW"


def _clear():
    os.environ.pop(_FLAG, None)


def _set(v):
    os.environ[_FLAG] = v


class TestBuildRow(unittest.TestCase):
    def test_schema_and_fields(self):
        ev = G.evaluate_bore_log(prints="5,6,17,21", station_min_ft=0, station_max_ft=243)
        row = TEL.build_row(
            session_id="s", source_file="bore_log6.xlsx", group_id="g1",
            selected_route_id="route_479", render_allowed=True, evidence=ev,
        )
        self.assertEqual(row["schema_version"], "brenham-plan-sheet-graph-shadow-1")
        for k in ("decided_at", "emit_id", "session_id", "source_file", "group_id",
                  "selected_route_id", "render_allowed", "prints", "corridors",
                  "corridor_count", "station_range", "status", "status_reasons"):
            self.assertIn(k, row)
        self.assertEqual(row["status"], G.STATUS_MULTI_CORRIDOR_SPAN)

    def test_handles_non_dict_evidence(self):
        row = TEL.build_row(
            session_id="s", source_file="f", group_id=None,
            selected_route_id=None, render_allowed=None, evidence=None,  # type: ignore[arg-type]
        )
        self.assertEqual(row["schema_version"], "brenham-plan-sheet-graph-shadow-1")
        self.assertEqual(row["status"], "unknown")


class TestAppend(unittest.TestCase):
    def test_append_creates_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "psg.jsonl"
            ev = G.evaluate_bore_log(prints="7", station_min_ft=200, station_max_ft=800)
            row = TEL.build_row(session_id="s", source_file="f", group_id="g",
                                selected_route_id="route_476", render_allowed=True, evidence=ev)
            self.assertTrue(TEL.append_shadow_row(row, target_path=target))
            lines = target.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            self.assertEqual(json.loads(lines[0])["status"], "within_corridor")

    def test_append_false_on_none_target(self):
        self.assertFalse(TEL.append_shadow_row({"x": 1}, target_path=None))

    def test_trim(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "psg.jsonl"
            # trim_trigger_bytes=1 → trim fires on every append once row count
            # exceeds max_rows, so the file converges to exactly max_rows.
            for i in range(20):
                TEL.append_shadow_row({"i": i}, target_path=target, max_rows=5, trim_trigger_bytes=1)
            self.assertLessEqual(len(target.read_text(encoding="utf-8").splitlines()), 5)


class TestFlagDefaultOff(unittest.TestCase):
    def setUp(self): _clear()
    def tearDown(self): _clear()

    def test_default_off(self):
        self.assertFalse(M._trueline_brenham_plan_sheet_graph_shadow_enabled())

    def test_on_values(self):
        for v in ("1", "true", "yes", "on", "On"):
            _set(v)
            self.assertTrue(M._trueline_brenham_plan_sheet_graph_shadow_enabled())


def _diag(group_id, source_file, route, allowed=True, lem=None):
    e = {"group_id": group_id, "source_file": source_file,
         "selected_route_id": route, "render_allowed": allowed}
    if lem is not None:
        e["location_evidence_mismatch"] = lem
    return e


def _rows(source_file, prints, stations):
    return [{"source_file": source_file, "print": prints, "station_ft": s} for s in stations]


class TestEmissionSeam(unittest.TestCase):
    def setUp(self):
        _clear()
        self._tmp = tempfile.TemporaryDirectory()
        self._target = Path(self._tmp.name) / "psg.jsonl"
        self._saved = M.BRENHAM_PLAN_SHEET_GRAPH_SHADOW_PATH
        M.BRENHAM_PLAN_SHEET_GRAPH_SHADOW_PATH = self._target

    def tearDown(self):
        _clear()
        M.BRENHAM_PLAN_SHEET_GRAPH_SHADOW_PATH = self._saved
        self._tmp.cleanup()

    def test_noop_when_flag_off(self):
        diag = [_diag("g1", "bore_log6.xlsx", "route_479")]
        rows = _rows("bore_log6.xlsx", "5,6,17,21", [0, 100, 243])
        ret = M._emit_brenham_plan_sheet_graph_shadow_if_enabled("sess", pipeline_diag=diag, committed_rows=rows)
        self.assertIsNone(ret)
        self.assertFalse(self._target.exists())

    def test_noop_when_session_empty(self):
        _set("1")
        diag = [_diag("g1", "bore_log6.xlsx", "route_479")]
        rows = _rows("bore_log6.xlsx", "5,6,17,21", [0, 243])
        M._emit_brenham_plan_sheet_graph_shadow_if_enabled(None, pipeline_diag=diag, committed_rows=rows)
        self.assertFalse(self._target.exists())

    def test_does_not_mutate_inputs(self):
        _set("1")
        diag = [_diag("g1", "bore_log6.xlsx", "route_479")]
        rows = _rows("bore_log6.xlsx", "5,6,17,21", [0, 243])
        sd, sr = copy.deepcopy(diag), copy.deepcopy(rows)
        M._emit_brenham_plan_sheet_graph_shadow_if_enabled("sess", pipeline_diag=diag, committed_rows=rows)
        self.assertEqual(diag, sd)
        self.assertEqual(rows, sr)

    def test_writes_one_row_per_group(self):
        _set("1")
        diag = [_diag("g1", "bore_log6.xlsx", "route_479"),
                _diag("g2", "bore_log9.xlsx", "route_478")]
        rows = _rows("bore_log6.xlsx", "5,6,17,21", [0, 243]) + _rows("bore_log9.xlsx", "7,14", [534, 1264])
        M._emit_brenham_plan_sheet_graph_shadow_if_enabled("sessW", pipeline_diag=diag, committed_rows=rows)
        self.assertTrue(self._target.exists())
        lines = self._target.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 2)
        by_file = {json.loads(l)["source_file"]: json.loads(l) for l in lines}
        self.assertEqual(by_file["bore_log6.xlsx"]["status"], G.STATUS_MULTI_CORRIDOR_SPAN)
        self.assertEqual(by_file["bore_log6.xlsx"]["session_id"], "sessW")

    def test_bore_log16_anomaly_surfaces(self):
        _set("1")
        diag = [_diag("g16", "bore_log16.xlsx", "route_478")]
        rows = _rows("bore_log16.xlsx", "8,9,10", [5100, 5500, 5950])
        M._emit_brenham_plan_sheet_graph_shadow_if_enabled("sessW", pipeline_diag=diag, committed_rows=rows)
        row = json.loads(self._target.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(row["status"], G.STATUS_STATION_PRINT_DISJOINT)

    def test_external_mismatch_via_diag_notes(self):
        _set("1")
        lem = {"notes_streets": ["CHERI LN"]}
        diag = [_diag("g39", "bore_log39.xlsx", "route_478", lem=lem)]
        rows = _rows("bore_log39.xlsx", "24,25", [1000, 1441])
        M._emit_brenham_plan_sheet_graph_shadow_if_enabled("sessW", pipeline_diag=diag, committed_rows=rows)
        row = json.loads(self._target.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(row["status"], G.STATUS_EXTERNAL_PACKET_MISMATCH)

    def test_skips_group_without_prints(self):
        _set("1")
        diag = [_diag("g1", "bore_logX.xlsx", "route_479")]
        rows = [{"source_file": "bore_logX.xlsx", "print": "", "station_ft": 100}]
        M._emit_brenham_plan_sheet_graph_shadow_if_enabled("sessW", pipeline_diag=diag, committed_rows=rows)
        self.assertFalse(self._target.exists())


class TestInvariants(unittest.TestCase):
    def setUp(self): _clear()
    def tearDown(self): _clear()

    def test_rebuild_path_calls_seam(self):
        import inspect
        src = inspect.getsource(M._rebuild_field_data_outputs)
        self.assertIn("_emit_brenham_plan_sheet_graph_shadow_if_enabled", src)

    def test_rebuild_path_no_scoring_change(self):
        """Lock: the seam must not introduce route scoring/selection/override
        references into the rebuild path beyond the existing ones."""
        import inspect
        src = inspect.getsource(M._rebuild_field_data_outputs)
        # No new apply/override/filter wiring from this slice.
        self.assertNotIn("match_overrides", src)
        # The PSG helper is only reachable via the flag-gated seam, never direct.
        self.assertNotIn("evaluate_bore_log", src)
        # R2a + R1 seams remain wired (slice is additive, not a replacement).
        self.assertIn("_emit_kmz_stage_r2a_anchor_shadow_if_enabled", src)
        self.assertIn("_emit_kmz_stage_r1_redline_shadow_if_enabled", src)

    def test_seam_source_no_route_mutation(self):
        """The PSG emission seam must not mutate selection/render or call the
        scoring formula. It reads diag entries via .get() only (no subscript
        assignment) and never writes STATE."""
        import inspect
        src = inspect.getsource(M._emit_brenham_plan_sheet_graph_shadow_if_enabled)
        self.assertNotIn("_score_route_candidate", src)
        # No subscript read/write on diag entries — only entry.get(...) is used,
        # so an `entry[` token would indicate a mutation/assignment path.
        self.assertNotIn("entry[", src)
        # No STATE subscript writes — only STATE.get(...) is permitted.
        self.assertNotIn("STATE[", src)

    def test_stage_a_print_sheet_index_unchanged(self):
        import inspect
        src = inspect.getsource(M._print_sheet_hints)
        self.assertIn("hardcoded_brenham", src)
        self.assertNotIn("plan_sheet_graph", src.lower())

    def test_constants_untouched(self):
        self.assertEqual(len(M.CURRENT_PACKET_PRINT_SHEET_INDEX.keys()), 30)


if __name__ == "__main__":
    unittest.main()
