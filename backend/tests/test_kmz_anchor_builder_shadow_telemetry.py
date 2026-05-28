"""KMZ Hardening Stage R2a — shadow-telemetry writer + flag-gate tests.

Verifies:
  - row schema + bounded sizes
  - append succeeds + creates file
  - flag default OFF
  - emission seam in main is a no-op when flag OFF (no file written, no
    STATE mutation, no pipeline_diag mutation)
  - emission seam writes one row per (route_id) when flag ON
  - R2a output is NOT consumed by R1 seam (R1 still emits anchor_count=0)
  - Stage A `print_sheet_index_source` value space UNCHANGED with R2a flag ON
  - rebuild path source contains the R2a seam call
"""

from __future__ import annotations

import copy
import json
import math
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from typing import Any, Dict, List, Tuple

os.environ.setdefault("TRUELINE_JWT_SECRET", "stage-r2a-shadow-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "stage-r2a-shadow-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend import main as M
from backend.app.core import kmz_anchor_builder as KAB
from backend.app.core import kmz_anchor_builder_shadow_telemetry as TEL

_R2A_FLAG_ENV = "TRUELINE_KMZ_STAGE_R2A_ANCHOR_BUILDER_SHADOW"
_R1_FLAG_ENV = "TRUELINE_KMZ_STAGE_R1_AUTO_REDLINE_SHADOW"


def _clear_flags() -> None:
    os.environ.pop(_R2A_FLAG_ENV, None)
    os.environ.pop(_R1_FLAG_ENV, None)


def _set_r2a_flag(value: str) -> None:
    os.environ[_R2A_FLAG_ENV] = value


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
                "input_feature_count": 0,
                "anchor_count": 0,
                "anchor_span_ft": 0.0,
                "perp_distance_m_stats": {"min": 0.0, "median": 0.0, "max": 0.0},
                "classification_tally": {},
                "confidence_tally": {"high": 0, "medium": 0, "low": 0},
                "rejection_reasons": {},
                "route_confidence": "abstain",
                "polyline_total_length_ft": 1234.0,
                "polyline_vertex_count": 5,
                "warnings": [],
            },
            anchor_records=[],
        )
        self.assertEqual(row["schema_version"], TEL.SCHEMA_VERSION)
        self.assertEqual(row["schema_version"], "kmz-stage-r2a-shadow-1")

    def test_required_fields_present(self):
        row = TEL.build_row(
            session_id="s", plan_id="p", route_id="r",
            request_meta={}, diagnostics={
                "input_feature_count": 100, "anchor_count": 5,
                "anchor_span_ft": 1500.0,
                "perp_distance_m_stats": {"min": 0.3, "median": 1.2, "max": 8.7},
                "classification_tally": {"station_label": 4, "handhole": 1},
                "confidence_tally": {"high": 4, "medium": 1, "low": 0},
                "rejection_reasons": {"non_point_geometry": 90, "no_chainage": 5},
                "route_confidence": "high",
                "polyline_total_length_ft": 2000.0,
                "polyline_vertex_count": 11,
                "warnings": [],
                "candidate_count_pre_proximity_filter": 6,
                "candidate_count_post_proximity_filter": 5,
                "candidate_count_post_dedupe": 5,
            },
        )
        required = {
            "schema_version", "decided_at", "emit_id",
            "session_id", "plan_id", "route_id", "request_meta",
            "input_feature_count",
            "candidate_count_pre_proximity_filter",
            "candidate_count_post_proximity_filter",
            "candidate_count_post_dedupe",
            "anchor_count", "anchor_span_ft", "perp_distance_m_stats",
            "classification_tally", "confidence_tally",
            "rejection_reasons", "route_confidence",
            "polyline_total_length_ft", "polyline_vertex_count",
            "warnings", "anchor_preview", "parameters_version",
        }
        self.assertTrue(required.issubset(set(row.keys())))

    def test_confidence_tally_normalization(self):
        row = TEL.build_row(
            session_id="s", plan_id="p", route_id="r", request_meta={},
            diagnostics={"confidence_tally": {"high": 7}},
        )
        self.assertEqual(row["confidence_tally"], {"high": 7, "medium": 0, "low": 0})

    def test_anchor_preview_bounded(self):
        records = [
            {"station_ft": float(i), "lon": -96.39, "lat": 30.16, "perp_distance_m": 0.5,
             "classification": "station_label", "anchor_confidence": "high"}
            for i in range(50)
        ]
        row = TEL.build_row(
            session_id="s", plan_id="p", route_id="r", request_meta={},
            diagnostics={}, anchor_records=records,
        )
        self.assertLessEqual(len(row["anchor_preview"]), TEL._MAX_ANCHOR_PREVIEW)

    def test_handles_missing_diagnostics_gracefully(self):
        row = TEL.build_row(
            session_id="s", plan_id="p", route_id="r",
            request_meta={}, diagnostics={},
        )
        self.assertEqual(row["anchor_count"], 0)
        self.assertEqual(row["input_feature_count"], 0)
        self.assertEqual(row["route_confidence"], "abstain")

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

    def test_append_creates_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "kmz_stage_r2a_shadow.jsonl"
            row = TEL.build_row(
                session_id="s", plan_id="p", route_id="r",
                request_meta={}, diagnostics={"anchor_count": 0},
            )
            self.assertTrue(TEL.append_shadow_row(row, target_path=target))
            self.assertTrue(target.exists())
            lines = target.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            parsed = json.loads(lines[0])
            self.assertEqual(parsed["schema_version"], TEL.SCHEMA_VERSION)

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
        _clear_flags()

    def tearDown(self):
        _clear_flags()

    def test_flag_default_off(self):
        self.assertFalse(M._trueline_kmz_stage_r2a_anchor_builder_shadow_enabled())

    def test_flag_off_explicit_zero(self):
        _set_r2a_flag("0")
        self.assertFalse(M._trueline_kmz_stage_r2a_anchor_builder_shadow_enabled())

    def test_flag_off_explicit_empty(self):
        _set_r2a_flag("")
        self.assertFalse(M._trueline_kmz_stage_r2a_anchor_builder_shadow_enabled())

    def test_flag_on_values(self):
        for v in ("1", "true", "yes", "on", "TRUE", "On"):
            _set_r2a_flag(v)
            self.assertTrue(M._trueline_kmz_stage_r2a_anchor_builder_shadow_enabled(),
                            f"flag should be ON for value {v!r}")


# ---------------------------------------------------------------------------
# Emission seam — flag OFF byte identity + flag ON write behavior
# ---------------------------------------------------------------------------

BRENHAM_LAT = 30.16
BRENHAM_LON = -96.39
_FT_PER_DEG_LON_BRENHAM = math.cos(math.radians(BRENHAM_LAT)) * KAB._FT_PER_DEGREE_LAT


def _route_coords_latlon(length_ft: float = 2000.0, n: int = 5) -> List[List[float]]:
    """Build the route catalog `coords` field shape: [[lat, lon], ...]."""
    return [
        [BRENHAM_LAT, BRENHAM_LON + (length_ft * i / (n - 1)) / _FT_PER_DEG_LON_BRENHAM]
        for i in range(n)
    ]


def _fake_route(route_id: str, length_ft: float = 2000.0) -> Dict[str, Any]:
    return {
        "route_id": route_id,
        "route_name": "Test Route",
        "length_ft": length_ft,
        "coords": _route_coords_latlon(length_ft),
    }


def _fake_diag_entry(group_id: str, route_id: str, source_file: str = "bore_log_t.xlsx") -> Dict[str, Any]:
    return {
        "group_id": group_id,
        "source_file": source_file,
        "selected_route_id": route_id,
        "selected_route_name": "Test Route",
        "render_allowed": True,
        "render_block_reasons": [],
        "stopped_at": None,
    }


def _fake_semantic_features(n_anchors: int = 2) -> List[Dict[str, Any]]:
    """Build a small kmz_semantic.features list with chainage-bearing Points."""
    out: List[Dict[str, Any]] = []
    for i in range(n_anchors):
        station_ft = 1000.0 + i * 500.0
        # Lay anchors evenly along the route's east-west span.
        lon = BRENHAM_LON + (station_ft - 1000.0) / _FT_PER_DEG_LON_BRENHAM
        # Note: full_geometry.coord is [lat, lon] per _kmz_semantic_extract_full_geometry.
        out.append({
            "feature_id": f"semantic_{i}",
            "placemark_name": f"STA {int(station_ft // 100)}+{int(station_ft % 100):02d}",
            "description": "",
            "geometry_type": "Point",
            "classification": "station_label",
            "confidence": "high",
            "chainage_ft": station_ft,
            "chainage_source": "name",
            "full_geometry": {"kind": "Point", "coord": [BRENHAM_LAT, lon]},
        })
    return out


class TestEmissionSeamFlagOff(unittest.TestCase):

    def setUp(self):
        _clear_flags()
        self._tmp = tempfile.TemporaryDirectory()
        self._target = Path(self._tmp.name) / "kmz_stage_r2a_shadow.jsonl"
        self._saved_path = M.KMZ_STAGE_R2A_SHADOW_PATH
        M.KMZ_STAGE_R2A_SHADOW_PATH = self._target

    def tearDown(self):
        _clear_flags()
        M.KMZ_STAGE_R2A_SHADOW_PATH = self._saved_path
        self._tmp.cleanup()

    def test_seam_noop_when_flag_off(self):
        diag = [_fake_diag_entry("g1", "route_A")]
        catalog = [_fake_route("route_A")]
        ret = M._emit_kmz_stage_r2a_anchor_shadow_if_enabled(
            "session_X",
            pipeline_diag=diag,
            route_catalog=catalog,
            kmz_semantic={"features": _fake_semantic_features(2)},
        )
        self.assertIsNone(ret)
        self.assertFalse(self._target.exists())

    def test_seam_noop_when_session_id_empty(self):
        _set_r2a_flag("1")
        diag = [_fake_diag_entry("g1", "route_A")]
        catalog = [_fake_route("route_A")]
        M._emit_kmz_stage_r2a_anchor_shadow_if_enabled(
            None,
            pipeline_diag=diag,
            route_catalog=catalog,
            kmz_semantic={"features": _fake_semantic_features(2)},
        )
        self.assertFalse(self._target.exists())

    def test_seam_does_not_mutate_inputs(self):
        _set_r2a_flag("1")
        diag = [_fake_diag_entry("g1", "route_A")]
        catalog = [_fake_route("route_A")]
        semantic = {"features": _fake_semantic_features(2)}
        snap_diag = copy.deepcopy(diag)
        snap_catalog = copy.deepcopy(catalog)
        snap_semantic = copy.deepcopy(semantic)
        M._emit_kmz_stage_r2a_anchor_shadow_if_enabled(
            "session_Y",
            pipeline_diag=diag, route_catalog=catalog, kmz_semantic=semantic,
        )
        self.assertEqual(diag, snap_diag)
        self.assertEqual(catalog, snap_catalog)
        self.assertEqual(semantic, snap_semantic)


class TestEmissionSeamFlagOn(unittest.TestCase):

    def setUp(self):
        _set_r2a_flag("1")
        self._tmp = tempfile.TemporaryDirectory()
        self._target = Path(self._tmp.name) / "kmz_stage_r2a_shadow.jsonl"
        self._saved_path = M.KMZ_STAGE_R2A_SHADOW_PATH
        M.KMZ_STAGE_R2A_SHADOW_PATH = self._target

    def tearDown(self):
        _clear_flags()
        M.KMZ_STAGE_R2A_SHADOW_PATH = self._saved_path
        self._tmp.cleanup()

    def test_seam_writes_one_row_per_unique_route(self):
        # Two groups on same route + one group on different route → 2 rows.
        diag = [
            _fake_diag_entry("g1", "route_A"),
            _fake_diag_entry("g2", "route_A"),
            _fake_diag_entry("g3", "route_B"),
        ]
        catalog = [_fake_route("route_A"), _fake_route("route_B")]
        semantic = {"features": _fake_semantic_features(3)}
        M._emit_kmz_stage_r2a_anchor_shadow_if_enabled(
            "session_W",
            pipeline_diag=diag, route_catalog=catalog, kmz_semantic=semantic,
        )
        self.assertTrue(self._target.exists())
        lines = self._target.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 2)
        route_ids = {json.loads(l)["route_id"] for l in lines}
        self.assertEqual(route_ids, {"route_A", "route_B"})

    def test_seam_records_anchor_count_when_features_supplied(self):
        diag = [_fake_diag_entry("g1", "route_A")]
        catalog = [_fake_route("route_A")]
        semantic = {"features": _fake_semantic_features(3)}
        M._emit_kmz_stage_r2a_anchor_shadow_if_enabled(
            "session_W",
            pipeline_diag=diag, route_catalog=catalog, kmz_semantic=semantic,
        )
        row = json.loads(self._target.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(row["anchor_count"], 3)
        self.assertEqual(row["session_id"], "session_W")
        self.assertEqual(row["route_id"], "route_A")
        self.assertIn(row["route_confidence"], {"high", "medium", "low"})

    def test_seam_records_zero_anchors_when_semantic_empty(self):
        diag = [_fake_diag_entry("g1", "route_A")]
        catalog = [_fake_route("route_A")]
        # Pass kmz_semantic=None → no features → R2a abstains.
        M._emit_kmz_stage_r2a_anchor_shadow_if_enabled(
            "session_W",
            pipeline_diag=diag, route_catalog=catalog, kmz_semantic=None,
        )
        # Even with zero anchors, the seam still emits a row recording the
        # abstain (so operator can see "tried, got nothing").
        self.assertTrue(self._target.exists())
        row = json.loads(self._target.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(row["anchor_count"], 0)
        self.assertEqual(row["route_confidence"], "abstain")
        self.assertIn("kmz_semantic_unavailable", row["warnings"])

    def test_seam_skips_groups_without_render_allowed(self):
        entry = _fake_diag_entry("g1", "route_A")
        entry["render_allowed"] = False
        M._emit_kmz_stage_r2a_anchor_shadow_if_enabled(
            "session_W",
            pipeline_diag=[entry],
            route_catalog=[_fake_route("route_A")],
            kmz_semantic={"features": _fake_semantic_features(2)},
        )
        self.assertFalse(self._target.exists())

    def test_seam_skips_groups_with_unknown_route(self):
        diag = [_fake_diag_entry("g1", "route_NOT_IN_CATALOG")]
        M._emit_kmz_stage_r2a_anchor_shadow_if_enabled(
            "session_W",
            pipeline_diag=diag,
            route_catalog=[_fake_route("route_A")],
            kmz_semantic={"features": _fake_semantic_features(2)},
        )
        self.assertFalse(self._target.exists())


# ---------------------------------------------------------------------------
# R2a does NOT wire into R1 (critical R2a invariant)
# ---------------------------------------------------------------------------

class TestR2aDoesNotWireIntoR1(unittest.TestCase):

    def setUp(self):
        _clear_flags()
        self._tmp = tempfile.TemporaryDirectory()
        self._r1_target = Path(self._tmp.name) / "kmz_stage_r1_shadow.jsonl"
        self._r2a_target = Path(self._tmp.name) / "kmz_stage_r2a_shadow.jsonl"
        self._saved_r1_path = M.KMZ_STAGE_R1_SHADOW_PATH
        self._saved_r2a_path = M.KMZ_STAGE_R2A_SHADOW_PATH
        M.KMZ_STAGE_R1_SHADOW_PATH = self._r1_target
        M.KMZ_STAGE_R2A_SHADOW_PATH = self._r2a_target

    def tearDown(self):
        _clear_flags()
        M.KMZ_STAGE_R1_SHADOW_PATH = self._saved_r1_path
        M.KMZ_STAGE_R2A_SHADOW_PATH = self._saved_r2a_path
        self._tmp.cleanup()

    def test_r1_still_emits_anchor_count_zero_when_r2a_flag_on(self):
        """Critical R2a invariant: with R1 + R2a flags BOTH ON, R1's shadow
        row must STILL record `anchor_count=0` — R2a is observation only,
        R2a output is NOT passed into R1. R2c is the future packet that
        would wire R2a output into R1."""
        _set_r1_flag("1")
        _set_r2a_flag("1")

        diag = [_fake_diag_entry("g1", "route_A")]
        catalog = [_fake_route("route_A")]
        semantic = {"features": _fake_semantic_features(3)}

        # Fire R1 seam.
        M._emit_kmz_stage_r1_redline_shadow_if_enabled(
            "session_W",
            pipeline_diag=diag, route_catalog=catalog,
        )
        # Fire R2a seam.
        M._emit_kmz_stage_r2a_anchor_shadow_if_enabled(
            "session_W",
            pipeline_diag=diag, route_catalog=catalog, kmz_semantic=semantic,
        )

        # Both telemetry files exist.
        self.assertTrue(self._r1_target.exists())
        self.assertTrue(self._r2a_target.exists())

        r1_row = json.loads(self._r1_target.read_text(encoding="utf-8").splitlines()[0])
        r2a_row = json.loads(self._r2a_target.read_text(encoding="utf-8").splitlines()[0])

        # R1's anchor_count MUST remain 0 — R2a anchors not piped in.
        self.assertEqual(r1_row["anchor_count"], 0)
        # R2a's anchor_count reflects what R2a derived independently.
        self.assertEqual(r2a_row["anchor_count"], 3)

    def test_r1_seam_source_does_not_call_r2a_helper(self):
        """Lock the no-wire-in invariant at the source level. R1's seam
        must not reference the R2a helper or its module."""
        import inspect
        src = inspect.getsource(M._emit_kmz_stage_r1_redline_shadow_if_enabled)
        self.assertNotIn("_kmz_r2a_helper", src)
        self.assertNotIn("kmz_anchor_builder", src)
        self.assertNotIn("generate_kmz_station_anchors", src)


# ---------------------------------------------------------------------------
# Stage A invariants under R2a flag ON
# ---------------------------------------------------------------------------

class TestStageAInvariantUnderR2aFlag(unittest.TestCase):

    def setUp(self):
        _clear_flags()

    def tearDown(self):
        _clear_flags()

    def test_print_sheet_index_source_value_space_unchanged(self):
        """Stage A's `print_sheet_index_source` reserved-value set must be
        UNCHANGED regardless of R2a flag state."""
        import inspect
        src = inspect.getsource(M._print_sheet_hints)
        self.assertIn("hardcoded_brenham", src)
        self.assertIn("no_print_index_available", src)
        # R2a must NOT contribute any new value here.
        self.assertNotIn("kmz_stage_r2a", src.lower())
        self.assertNotIn("anchor_builder", src.lower())

    def test_no_new_trueline_flag_in_stage_a_cascade(self):
        import inspect
        src_hints = inspect.getsource(M._print_sheet_hints)
        src_filter = inspect.getsource(M._route_filter_for_print_tokens)
        for src in (src_hints, src_filter):
            self.assertNotIn("TRUELINE_KMZ_STAGE_R2A", src)
            self.assertNotIn("_trueline_kmz_stage_r2a", src)


# ---------------------------------------------------------------------------
# Rebuild path source contains R2a seam call + does not persist
# ---------------------------------------------------------------------------

class TestRebuildPathPreservesInvariants(unittest.TestCase):

    def setUp(self):
        _clear_flags()

    def tearDown(self):
        _clear_flags()

    def test_rebuild_path_calls_r2a_seam(self):
        import inspect
        src = inspect.getsource(M._rebuild_field_data_outputs)
        self.assertIn("_emit_kmz_stage_r2a_anchor_shadow_if_enabled", src)

    def test_rebuild_path_calls_both_r1_and_r2a_seams(self):
        """Both R-series seams must be wired in the rebuild path. They are
        independent — R2a does not replace R1."""
        import inspect
        src = inspect.getsource(M._rebuild_field_data_outputs)
        self.assertIn("_emit_kmz_stage_r1_redline_shadow_if_enabled", src)
        self.assertIn("_emit_kmz_stage_r2a_anchor_shadow_if_enabled", src)

    def test_rebuild_path_does_not_persist_anchors_or_apply_to_matching(self):
        """R2a must NOT introduce any anchor persistence or apply-to-matching
        call in the rebuild path. Locks the no-persistence + no-apply
        invariants."""
        import inspect
        src = inspect.getsource(M._rebuild_field_data_outputs)
        self.assertNotIn("match_overrides", src)
        self.assertNotIn("persist_kmz_anchor", src.lower())
        self.assertNotIn("kmz_anchor_persist", src.lower())
        # R2a helper must NEVER be invoked from the rebuild path directly;
        # only through the flag-gated seam.
        self.assertIn("_emit_kmz_stage_r2a_anchor_shadow_if_enabled", src)
        self.assertNotIn("generate_kmz_station_anchors", src)

    def test_seam_default_off_matches_flag_helper(self):
        self.assertFalse(M._trueline_kmz_stage_r2a_anchor_builder_shadow_enabled())


# ---------------------------------------------------------------------------
# Production flag state (UNCHANGED post-R2a ship)
# ---------------------------------------------------------------------------

class TestProductionFlagsUntouched(unittest.TestCase):

    def setUp(self):
        _clear_flags()

    def tearDown(self):
        _clear_flags()

    def test_r2a_flag_does_not_force_other_kmz_flags_on(self):
        for env in (
            "TRUELINE_KMZ_STAGE_B1_TOKEN_UNIVERSE_DERIVED",
            "TRUELINE_KMZ_STAGE_B2_STREETS_SHADOW",
            "TRUELINE_PI4A_DERIVED_PRINT_INDEX",
            "TRUELINE_KMZ_STAGE_R1_AUTO_REDLINE_SHADOW",
        ):
            os.environ.pop(env, None)
        _set_r2a_flag("1")
        self.assertTrue(M._trueline_kmz_stage_r2a_anchor_builder_shadow_enabled())
        self.assertFalse(M._trueline_kmz_stage_b1_token_universe_derived_enabled())
        self.assertFalse(M._trueline_kmz_stage_b2_streets_shadow_enabled())
        self.assertFalse(M._trueline_kmz_stage_r1_auto_redline_shadow_enabled())

    def test_constants_untouched(self):
        keys = set(M.CURRENT_PACKET_PRINT_SHEET_INDEX.keys())
        self.assertEqual(len(keys), 30)


if __name__ == "__main__":
    unittest.main()
