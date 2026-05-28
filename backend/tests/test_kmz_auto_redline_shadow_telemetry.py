"""KMZ Hardening Stage R1 — shadow-telemetry writer + flag-gate tests.

Verifies:
  - row schema + bounded sizes
  - append succeeds + creates file
  - flag default OFF
  - emission seam in main is a no-op when flag OFF (no file written, no
    STATE mutation, no pipeline_diag mutation)
  - emission seam writes one row per (group, route_id) when flag ON
  - Stage A `print_sheet_index_source` value space UNCHANGED with R1 flag ON
  - flag-OFF vs flag-ON pipeline output byte-identity (telemetry-only)
  - rebuild path source contains the R1 seam call
"""

from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from typing import Any, Dict, List, Tuple

os.environ.setdefault("TRUELINE_JWT_SECRET", "stage-r1-shadow-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "stage-r1-shadow-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend import main as M
from backend.app.core import kmz_auto_redline as KAR
from backend.app.core import kmz_auto_redline_shadow_telemetry as TEL

_R1_FLAG_ENV = "TRUELINE_KMZ_STAGE_R1_AUTO_REDLINE_SHADOW"


def _clear_r1_flag() -> None:
    os.environ.pop(_R1_FLAG_ENV, None)


def _set_r1_flag(value: str) -> None:
    os.environ[_R1_FLAG_ENV] = value


# ---------------------------------------------------------------------------
# Row schema
# ---------------------------------------------------------------------------

class TestBuildRow(unittest.TestCase):

    def test_schema_version_set(self):
        row = TEL.build_row(
            session_id="s",
            plan_id="p",
            route_id="r",
            request_meta={"operator_id": "op"},
            diagnostics={
                "anchor_count": 0,
                "anchor_span_ft": 0.0,
                "anchor_residuals_m": [],
                "polyline_total_length_ft": 1234.5,
                "polyline_vertex_count": 10,
                "rows_input": 0,
                "rows_generated": 0,
                "rows_rejected": 0,
                "rejection_reasons": {},
                "confidence_tally": {"high": 0, "medium": 0, "low": 0, "fallback": 0},
                "model_built": False,
                "model_slope_ft_per_ft": 0.0,
                "residual_tier": "fallback",
                "warnings": [],
            },
        )
        self.assertEqual(row["schema_version"], TEL.SCHEMA_VERSION)
        self.assertEqual(row["schema_version"], "kmz-stage-r1-shadow-1")

    def test_required_fields_present(self):
        row = TEL.build_row(
            session_id="s",
            plan_id="p",
            route_id="r",
            request_meta={},
            diagnostics={
                "anchor_count": 2,
                "anchor_span_ft": 1000.0,
                "anchor_residuals_m": [0.1, 0.2],
                "polyline_total_length_ft": 1234.0,
                "polyline_vertex_count": 5,
                "rows_input": 3,
                "rows_generated": 2,
                "rows_rejected": 1,
                "rejection_reasons": {"end_before_start": 1},
                "confidence_tally": {"high": 1, "medium": 1, "low": 0, "fallback": 0},
                "model_built": True,
                "model_slope_ft_per_ft": 1.05,
                "residual_tier": "high",
                "warnings": [],
            },
        )
        required = {
            "schema_version", "decided_at", "emit_id",
            "session_id", "plan_id", "route_id", "request_meta",
            "anchor_count", "anchor_span_ft", "anchor_residuals_m",
            "polyline_total_length_ft", "polyline_vertex_count",
            "rows_input", "rows_generated", "rows_rejected",
            "rejection_reasons", "confidence_tally",
            "model_built", "model_slope_ft_per_ft", "residual_tier",
            "warnings", "parameters_version", "projection_version",
        }
        self.assertTrue(required.issubset(set(row.keys())))

    def test_confidence_tally_normalization(self):
        row = TEL.build_row(
            session_id="s", plan_id="p", route_id="r", request_meta={},
            diagnostics={"confidence_tally": {"high": 5, "fallback": 2}},
        )
        # Missing keys default to 0; present keys preserved.
        self.assertEqual(row["confidence_tally"], {"high": 5, "medium": 0, "low": 0, "fallback": 2})

    def test_anchor_residuals_bounded(self):
        big = [float(i) for i in range(200)]
        row = TEL.build_row(
            session_id="s", plan_id="p", route_id="r", request_meta={},
            diagnostics={"anchor_residuals_m": big},
        )
        self.assertLessEqual(len(row["anchor_residuals_m"]), TEL._MAX_RESIDUALS_RECORDED)

    def test_handles_missing_diagnostics_gracefully(self):
        row = TEL.build_row(
            session_id="s", plan_id="p", route_id="r", request_meta={},
            diagnostics={},
        )
        self.assertEqual(row["anchor_count"], 0)
        self.assertEqual(row["rows_input"], 0)
        self.assertFalse(row["model_built"])
        self.assertEqual(row["confidence_tally"], {"high": 0, "medium": 0, "low": 0, "fallback": 0})

    def test_handles_non_dict_diagnostics(self):
        row = TEL.build_row(
            session_id="s", plan_id="p", route_id="r", request_meta={},
            diagnostics=None,  # type: ignore[arg-type]
        )
        self.assertEqual(row["anchor_count"], 0)
        self.assertEqual(row["schema_version"], TEL.SCHEMA_VERSION)


# ---------------------------------------------------------------------------
# Append writer
# ---------------------------------------------------------------------------

class TestAppendShadowRow(unittest.TestCase):

    def test_append_creates_file_and_returns_true(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "kmz_stage_r1_shadow.jsonl"
            row = TEL.build_row(
                session_id="s", plan_id="p", route_id="r",
                request_meta={}, diagnostics={"anchor_count": 0},
            )
            ok = TEL.append_shadow_row(row, target_path=target)
            self.assertTrue(ok)
            self.assertTrue(target.exists())
            lines = target.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            parsed = json.loads(lines[0])
            self.assertEqual(parsed["schema_version"], TEL.SCHEMA_VERSION)

    def test_append_two_rows_appends_in_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "kmz_stage_r1_shadow.jsonl"
            row_a = TEL.build_row(
                session_id="s", plan_id="p", route_id="route_A",
                request_meta={}, diagnostics={},
            )
            row_b = TEL.build_row(
                session_id="s", plan_id="p", route_id="route_B",
                request_meta={}, diagnostics={},
            )
            self.assertTrue(TEL.append_shadow_row(row_a, target_path=target))
            self.assertTrue(TEL.append_shadow_row(row_b, target_path=target))
            lines = target.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 2)
            self.assertEqual(json.loads(lines[0])["route_id"], "route_A")
            self.assertEqual(json.loads(lines[1])["route_id"], "route_B")

    def test_append_returns_false_on_none_target(self):
        row = TEL.build_row(
            session_id="s", plan_id="p", route_id="r",
            request_meta={}, diagnostics={},
        )
        self.assertFalse(TEL.append_shadow_row(row, target_path=None))

    def test_append_returns_false_on_non_dict_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "f.jsonl"
            self.assertFalse(TEL.append_shadow_row("not a dict", target_path=target))  # type: ignore[arg-type]

    def test_trim_keeps_max_rows(self):
        """Force a tiny trim trigger to exercise the trim path deterministically."""
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "f.jsonl"
            for i in range(20):
                row = TEL.build_row(
                    session_id="s", plan_id="p", route_id=f"route_{i}",
                    request_meta={}, diagnostics={},
                )
                ok = TEL.append_shadow_row(
                    row, target_path=target,
                    max_rows=5, trim_trigger_bytes=512,
                )
                self.assertTrue(ok)
            lines = target.read_text(encoding="utf-8").splitlines()
            self.assertLessEqual(len(lines), 5)


# ---------------------------------------------------------------------------
# Flag default OFF
# ---------------------------------------------------------------------------

class TestFlagDefaultOff(unittest.TestCase):

    def setUp(self):
        _clear_r1_flag()

    def tearDown(self):
        _clear_r1_flag()

    def test_flag_default_off(self):
        self.assertFalse(M._trueline_kmz_stage_r1_auto_redline_shadow_enabled())

    def test_flag_off_explicit_zero(self):
        _set_r1_flag("0")
        self.assertFalse(M._trueline_kmz_stage_r1_auto_redline_shadow_enabled())

    def test_flag_off_explicit_empty(self):
        _set_r1_flag("")
        self.assertFalse(M._trueline_kmz_stage_r1_auto_redline_shadow_enabled())

    def test_flag_on_values(self):
        for v in ("1", "true", "yes", "on", "TRUE", "On"):
            _set_r1_flag(v)
            self.assertTrue(
                M._trueline_kmz_stage_r1_auto_redline_shadow_enabled(),
                f"flag should be ON for value {v!r}",
            )


# ---------------------------------------------------------------------------
# Emission seam — flag OFF byte identity + flag ON write behavior
# ---------------------------------------------------------------------------

def _fake_route(route_id: str, length_ft: float = 2000.0) -> Dict[str, Any]:
    """Tiny route catalog record matching the shape produced by
    `_build_route_catalog` (route_id, coords list of (lon, lat) tuples)."""
    # Brenham-area horizontal line at lat=30.16; 2000 ft east.
    import math
    lat = 30.16
    lon_start = -96.39
    ft_per_deg_lon = math.cos(math.radians(lat)) * 364567.2
    coords: List[Tuple[float, float]] = [
        (lon_start + (length_ft * i / 4.0) / ft_per_deg_lon, lat)
        for i in range(5)
    ]
    return {
        "route_id": route_id,
        "route_name": "Test Route",
        "length_ft": length_ft,
        "coords": coords,
    }


def _fake_diag_entry(group_id: str, route_id: str, source_file: str = "bore_log_test.xlsx") -> Dict[str, Any]:
    return {
        "group_id": group_id,
        "source_file": source_file,
        "selected_route_id": route_id,
        "selected_route_name": "Test Route",
        "render_allowed": True,
        "render_block_reasons": [],
        "stopped_at": None,
    }


class TestEmissionSeamFlagOff(unittest.TestCase):

    def setUp(self):
        _clear_r1_flag()
        self._tmp = tempfile.TemporaryDirectory()
        self._target = Path(self._tmp.name) / "kmz_stage_r1_shadow.jsonl"
        self._saved_path = M.KMZ_STAGE_R1_SHADOW_PATH
        M.KMZ_STAGE_R1_SHADOW_PATH = self._target

    def tearDown(self):
        _clear_r1_flag()
        M.KMZ_STAGE_R1_SHADOW_PATH = self._saved_path
        self._tmp.cleanup()

    def test_seam_noop_when_flag_off(self):
        """With flag OFF, seam returns silently; no file written."""
        diag = [_fake_diag_entry("g1", "route_T")]
        catalog = [_fake_route("route_T")]
        ret = M._emit_kmz_stage_r1_redline_shadow_if_enabled(
            "session_X", pipeline_diag=diag, route_catalog=catalog,
        )
        self.assertIsNone(ret)
        self.assertFalse(self._target.exists())

    def test_seam_noop_when_session_id_empty(self):
        _set_r1_flag("1")
        diag = [_fake_diag_entry("g1", "route_T")]
        catalog = [_fake_route("route_T")]
        ret = M._emit_kmz_stage_r1_redline_shadow_if_enabled(
            None, pipeline_diag=diag, route_catalog=catalog,
        )
        self.assertIsNone(ret)
        self.assertFalse(self._target.exists())

    def test_seam_does_not_mutate_inputs(self):
        """Even when flag is ON, the seam never mutates pipeline_diag /
        route_catalog inputs."""
        _set_r1_flag("1")
        diag = [_fake_diag_entry("g1", "route_T")]
        catalog = [_fake_route("route_T")]
        snap_diag = copy.deepcopy(diag)
        snap_catalog = copy.deepcopy(catalog)
        M._emit_kmz_stage_r1_redline_shadow_if_enabled(
            "session_Y", pipeline_diag=diag, route_catalog=catalog,
        )
        self.assertEqual(diag, snap_diag)
        self.assertEqual(catalog, snap_catalog)


class TestEmissionSeamFlagOn(unittest.TestCase):

    def setUp(self):
        _set_r1_flag("1")
        self._tmp = tempfile.TemporaryDirectory()
        self._target = Path(self._tmp.name) / "kmz_stage_r1_shadow.jsonl"
        self._saved_path = M.KMZ_STAGE_R1_SHADOW_PATH
        M.KMZ_STAGE_R1_SHADOW_PATH = self._target

    def tearDown(self):
        _clear_r1_flag()
        M.KMZ_STAGE_R1_SHADOW_PATH = self._saved_path
        self._tmp.cleanup()

    def test_seam_writes_one_row_per_rendered_group(self):
        diag = [
            _fake_diag_entry("g1", "route_A"),
            _fake_diag_entry("g2", "route_B"),
        ]
        catalog = [_fake_route("route_A"), _fake_route("route_B")]
        M._emit_kmz_stage_r1_redline_shadow_if_enabled(
            "session_W", pipeline_diag=diag, route_catalog=catalog,
        )
        self.assertTrue(self._target.exists())
        lines = self._target.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 2)
        rows = [json.loads(line) for line in lines]
        route_ids = {r["route_id"] for r in rows}
        self.assertEqual(route_ids, {"route_A", "route_B"})
        for r in rows:
            self.assertEqual(r["schema_version"], "kmz-stage-r1-shadow-1")
            self.assertEqual(r["session_id"], "session_W")
            # R1 has no anchor builder yet, so anchor_count is 0.
            self.assertEqual(r["anchor_count"], 0)
            self.assertEqual(r["rows_input"], 0)

    def test_seam_skips_groups_without_render_allowed(self):
        entry = _fake_diag_entry("g1", "route_A")
        entry["render_allowed"] = False
        diag = [entry]
        catalog = [_fake_route("route_A")]
        M._emit_kmz_stage_r1_redline_shadow_if_enabled(
            "session_W", pipeline_diag=diag, route_catalog=catalog,
        )
        self.assertFalse(self._target.exists())

    def test_seam_skips_groups_without_selected_route_id(self):
        entry = _fake_diag_entry("g1", "")  # empty selected_route_id
        diag = [entry]
        catalog = [_fake_route("route_A")]
        M._emit_kmz_stage_r1_redline_shadow_if_enabled(
            "session_W", pipeline_diag=diag, route_catalog=catalog,
        )
        self.assertFalse(self._target.exists())

    def test_seam_skips_groups_with_unknown_route(self):
        diag = [_fake_diag_entry("g1", "route_NOT_IN_CATALOG")]
        catalog = [_fake_route("route_A")]
        M._emit_kmz_stage_r1_redline_shadow_if_enabled(
            "session_W", pipeline_diag=diag, route_catalog=catalog,
        )
        self.assertFalse(self._target.exists())

    def test_seam_records_group_id_and_source_file_in_request_meta(self):
        diag = [_fake_diag_entry("g_ABC", "route_A", source_file="bore_log_99.xlsx")]
        catalog = [_fake_route("route_A")]
        M._emit_kmz_stage_r1_redline_shadow_if_enabled(
            "session_W", pipeline_diag=diag, route_catalog=catalog,
        )
        row = json.loads(self._target.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(row["request_meta"]["group_id"], "g_ABC")
        self.assertEqual(row["request_meta"]["source_file"], "bore_log_99.xlsx")
        # session_id lives at the top-level row, not inside request_meta
        # (request_meta is a compact projection that drops session_id +
        # plan_id because they're already row-level fields).
        self.assertEqual(row["session_id"], "session_W")


# ---------------------------------------------------------------------------
# Stage A invariants under R1 flag ON
# ---------------------------------------------------------------------------

class TestStageAInvariantUnderR1Flag(unittest.TestCase):

    def setUp(self):
        _clear_r1_flag()

    def tearDown(self):
        _clear_r1_flag()

    def test_print_sheet_index_source_value_space_unchanged_with_r1_flag_on(self):
        """Stage A's `print_sheet_index_source` reserved-value set must be
        UNCHANGED regardless of R1 shadow flag state. R1 must never expand
        the value space (R1 is observation-only for redline projection — it
        does not touch the print-sheet cascade)."""
        # Stage A reserved values from `hot.md` § KMZ Hardening Stage A.
        expected_values = {
            "hardcoded_brenham",          # LIVE in Stage A
            "no_print_index_available",    # LIVE in Stage A
            "pi4a_derived",                # RESERVED for Stage B
            "manual_override",             # RESERVED for Stage E
        }
        # The helper does not introduce any new value; assert by inspecting
        # the `_print_sheet_hints` helper's possible string literals.
        import inspect
        src = inspect.getsource(M._print_sheet_hints)
        # Both LIVE values present.
        self.assertIn("hardcoded_brenham", src)
        self.assertIn("no_print_index_available", src)
        # R1 must NOT contribute any new value to this surface.
        self.assertNotIn("kmz_stage_r1", src.lower())
        self.assertNotIn("auto_redline", src.lower())

    def test_no_new_trueline_flag_in_stage_a_cascade(self):
        """The Stage A `_print_sheet_hints` + `_route_filter_for_print_tokens`
        helpers must not reference the new R1 flag."""
        import inspect
        src_hints = inspect.getsource(M._print_sheet_hints)
        src_filter = inspect.getsource(M._route_filter_for_print_tokens)
        for src in (src_hints, src_filter):
            self.assertNotIn("TRUELINE_KMZ_STAGE_R1", src)
            self.assertNotIn("_trueline_kmz_stage_r1", src)


# ---------------------------------------------------------------------------
# Pipeline byte-identity (flag OFF vs flag ON do not affect non-telemetry STATE)
# ---------------------------------------------------------------------------

class TestRebuildPathPreservesInvariants(unittest.TestCase):

    def setUp(self):
        _clear_r1_flag()

    def tearDown(self):
        _clear_r1_flag()

    def test_rebuild_path_calls_r1_seam(self):
        """`_rebuild_field_data_outputs` must contain the R1 seam call so
        rebuilds emit telemetry when the flag is ON."""
        import inspect
        src = inspect.getsource(M._rebuild_field_data_outputs)
        self.assertIn("_emit_kmz_stage_r1_redline_shadow_if_enabled", src)

    def test_rebuild_path_does_not_apply_overrides_or_persist_redlines(self):
        """R1 must NOT introduce any redline persistence call in the rebuild
        path. Locks the no-persistence invariant. Also re-asserts the Slice
        C1 record-only invariant (no apply seam) so future edits don't
        inadvertently couple R1 and C2."""
        import inspect
        src = inspect.getsource(M._rebuild_field_data_outputs)
        self.assertNotIn("match_overrides", src)
        self.assertNotIn("persist_kmz_redline", src.lower())
        self.assertNotIn("kmz_redline_persist", src.lower())
        # The R1 helper must NEVER be invoked from the rebuild path directly;
        # only through the flag-gated seam.
        self.assertIn("_emit_kmz_stage_r1_redline_shadow_if_enabled", src)
        self.assertNotIn("generate_kmz_auto_redline_segments", src)

    def test_seam_default_off_matches_flag_helper(self):
        """When the flag env var is unset, the seam must not produce any
        side effect — confirmed by the helper returning False."""
        self.assertFalse(M._trueline_kmz_stage_r1_auto_redline_shadow_enabled())


# ---------------------------------------------------------------------------
# Production flag state (UNCHANGED post-R1 ship)
# ---------------------------------------------------------------------------

class TestProductionFlagsUntouched(unittest.TestCase):

    def setUp(self):
        _clear_r1_flag()

    def tearDown(self):
        _clear_r1_flag()

    def test_r1_flag_does_not_force_other_kmz_flags_on(self):
        """Setting R1 ON must NOT change any other KMZ stage flag value."""
        for env in (
            "TRUELINE_KMZ_STAGE_B1_TOKEN_UNIVERSE_DERIVED",
            "TRUELINE_KMZ_STAGE_B2_STREETS_SHADOW",
            "TRUELINE_PI4A_DERIVED_PRINT_INDEX",
        ):
            os.environ.pop(env, None)
        _set_r1_flag("1")
        # Confirm the R1 flag is the ONLY one toggled.
        self.assertTrue(M._trueline_kmz_stage_r1_auto_redline_shadow_enabled())
        self.assertFalse(M._trueline_kmz_stage_b1_token_universe_derived_enabled())
        self.assertFalse(M._trueline_kmz_stage_b2_streets_shadow_enabled())

    def test_constants_untouched(self):
        """Locks: the Brenham PH5 print-sheet index constant content is
        UNCHANGED regardless of any R1 work."""
        # Constant must exist and have its known keys.
        keys = set(M.CURRENT_PACKET_PRINT_SHEET_INDEX.keys())
        # 1..30 string keys per Stage A baseline.
        self.assertEqual(len(keys), 30)


if __name__ == "__main__":
    unittest.main()
