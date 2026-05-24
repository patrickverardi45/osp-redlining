"""Anti-Collapse V1 integration tests — env-gated rebuild-loop wiring.

When `TRUELINE_ABSTAIN_ON_ROUTE_COLLISION=1`, the rebuild loop runs the
route-collision resolver after the initial coverage_sanity, mutates the
losing groups' pipeline_diag entries + match render_allowed, drops their
station_points + redline_segments from STATE, and recomputes
coverage_sanity. Default (env unset/0): byte-identical to today.

The "real placement" tests load the Brenham PH5 KMZ fixture plus
bore_log29 + bore_log30 directly from the local Excel folder, since
production-parity diagnostics proved this pair stacks on route_477 with
~100% overlap — exactly the scenario the resolver is designed to address.
"""

from __future__ import annotations

import copy
import os
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("TRUELINE_JWT_SECRET", "ac-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "ac-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend import main as M
from backend.app.core.rebuild_scope import RebuildScope

COLLISION_ENV = "TRUELINE_ABSTAIN_ON_ROUTE_COLLISION"

KMZ_PATH = Path(__file__).resolve().parent / "fixtures" / "brenham_phase5_source_truth.kmz"
EXCEL_DIR = Path(r"C:/Users/Patrick/OneDrive/Attachments/Desktop/excel bore logs")
HAS_LOCAL_EXCELS = EXCEL_DIR.exists() and (EXCEL_DIR / "bore_log29.xlsx").exists()


def _synthetic_row(notes: str, source_file: str, print_token: str = "1",
                   station: str = "0+00", station_ft: float = 0.0) -> dict:
    return {
        "station": station, "station_ft": station_ft,
        "depth_ft": 5.0, "boc_ft": 4.0,
        "date": "2025-12-15", "crew": "tx1-4",
        "print": print_token, "notes": notes,
        "source_file": source_file,
    }


def _stub_rankings(route_id: str = "route_nonexistent", score: float = 0.20) -> tuple:
    rankings = [{"route_id": route_id, "route_name": "Stub",
                 "score": score, "route_length_ft": 100.0,
                 "expected_span_ft": 100.0, "route_role": "underground_cable"}]
    filter_meta = {"applied": True, "mode": "test", "print_tokens": ["1"],
                   "sheet_numbers": [1], "street_hints": [],
                   "allowed_route_ids": [route_id], "reason": "stub"}
    return (rankings, filter_meta, list(rankings))


def _two_unplaced_groups() -> list:
    return [
        _synthetic_row("", "bore_log_a.xlsx", station="0+00", station_ft=0.0),
        _synthetic_row("", "bore_log_a.xlsx", station="1+00", station_ft=100.0),
        _synthetic_row("", "bore_log_b.xlsx", station="0+00", station_ft=0.0),
        _synthetic_row("", "bore_log_b.xlsx", station="1+00", station_ft=100.0),
    ]


def _brenham_committed_rows(filenames: list) -> list:
    rows: list = []
    for name in filenames:
        path = EXCEL_DIR / name
        if not path.exists():
            continue
        file_bytes = path.read_bytes()
        try:
            file_rows = M._read_bore_log_rows(file_bytes, name)
        except Exception:
            continue
        for r in file_rows:
            r["source_file"] = name
        rows.extend(file_rows)
    return rows


class TestAntiCollapseV1Lightweight(unittest.TestCase):
    """Tests that don't require the Brenham fixture (env-gate behavior)."""

    def setUp(self) -> None:
        self._saved_state = copy.deepcopy(dict(M.STATE))
        self._saved = {k: os.environ.pop(k, None) for k in (COLLISION_ENV,)}
        self._session_id = f"ac_{uuid.uuid4().hex[:12]}"

    def tearDown(self) -> None:
        M.STATE.clear()
        M.STATE.update(self._saved_state)
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _reset_state(self, rows: list) -> None:
        M.STATE.clear()
        M.STATE.update({
            "committed_rows": list(rows),
            "route_catalog": [],
            "address_points": [],
            "_session_id_hint": self._session_id,
            "engineering_plans": [],
        })

    def test_env_unset_no_resolution_metadata_in_coverage_sanity(self) -> None:
        rows = _two_unplaced_groups()
        self._reset_state(rows)
        with patch.object(M, "_candidate_rankings_for_group_v2", return_value=_stub_rankings()):
            M._rebuild_field_data_outputs(scope=RebuildScope.FULL)
        cs = M.STATE.get("coverage_sanity") or {}
        assert "route_collision_resolution" not in cs

    def test_env_zero_no_resolution_metadata_in_coverage_sanity(self) -> None:
        os.environ[COLLISION_ENV] = "0"
        rows = _two_unplaced_groups()
        self._reset_state(rows)
        with patch.object(M, "_candidate_rankings_for_group_v2", return_value=_stub_rankings()):
            M._rebuild_field_data_outputs(scope=RebuildScope.FULL)
        cs = M.STATE.get("coverage_sanity") or {}
        assert "route_collision_resolution" not in cs

    def test_env_on_with_zero_placed_groups_records_noop_resolution(self) -> None:
        os.environ[COLLISION_ENV] = "1"
        # Empty corpus → no placed groups → resolver runs but applies nothing
        self._reset_state([])
        with patch.object(M, "_candidate_rankings_for_group_v2", return_value=_stub_rankings()):
            M._rebuild_field_data_outputs(scope=RebuildScope.FULL)
        cs = M.STATE.get("coverage_sanity") or {}
        rcr = cs.get("route_collision_resolution") or {}
        assert rcr.get("applied") is False
        assert rcr.get("abstained_source_files") == []


@unittest.skipUnless(HAS_LOCAL_EXCELS and KMZ_PATH.exists(),
                      "Brenham fixture + local Excel files required")
class TestAntiCollapseV1BrenhamReal(unittest.TestCase):
    """Real-placement tests using Brenham PH5 KMZ + actual bore_log29/30."""

    def setUp(self) -> None:
        self._saved_state = copy.deepcopy(dict(M.STATE))
        self._saved = {k: os.environ.pop(k, None) for k in (COLLISION_ENV,)}
        self._session_id = f"ac_brenham_{uuid.uuid4().hex[:12]}"

    def tearDown(self) -> None:
        M.STATE.clear()
        M.STATE.update(self._saved_state)
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _seed_brenham_with_files(self, filenames: list) -> None:
        kmz_bytes = KMZ_PATH.read_bytes()
        M.STATE.clear()
        M.STATE.update({
            "route_catalog": M._build_route_catalog(kmz_bytes, KMZ_PATH.name),
            "address_points": M.parse_address_points_from_kml(kmz_bytes, KMZ_PATH.name),
            "committed_rows": _brenham_committed_rows(filenames),
            "_session_id_hint": self._session_id,
            "engineering_plans": [],
        })

    def _find_diag(self, source_file: str) -> dict:
        for entry in (M.STATE.get("pipeline_diag") or []):
            if entry.get("source_file") == source_file:
                return entry
        raise AssertionError(f"No pipeline_diag entry for {source_file!r}")

    # ── A. Env OFF: both 29 + 30 placed (current production behavior) ──────

    def test_brenham_29_30_env_off_both_placed(self) -> None:
        # env unset; rebuild against real KMZ; both bore-logs should land
        # on route_477 (production parity)
        self._seed_brenham_with_files(["bore_log29.xlsx", "bore_log30.xlsx"])
        M._rebuild_field_data_outputs(scope=RebuildScope.FULL)
        d29 = self._find_diag("bore_log29.xlsx")
        d30 = self._find_diag("bore_log30.xlsx")
        assert d29.get("selected_route_id") == "route_477"
        assert d30.get("selected_route_id") == "route_477"
        assert d29.get("stopped_at") is None
        assert d30.get("stopped_at") is None
        cs = M.STATE.get("coverage_sanity") or {}
        # Collision is detected diagnostically but not resolved
        assert cs.get("same_route_anchor_collision_detected") is True
        assert "route_collision_resolution" not in cs

    # ── B. Env ON: one of {29, 30} abstains, the other keeps placement ────

    def test_brenham_29_30_env_on_one_abstained_one_kept(self) -> None:
        os.environ[COLLISION_ENV] = "1"
        self._seed_brenham_with_files(["bore_log29.xlsx", "bore_log30.xlsx"])
        M._rebuild_field_data_outputs(scope=RebuildScope.FULL)
        cs = M.STATE.get("coverage_sanity") or {}
        rcr = cs.get("route_collision_resolution") or {}
        assert rcr.get("applied") is True
        abstained = rcr.get("abstained_source_files") or []
        assert len(abstained) == 1
        assert abstained[0] in ("bore_log29.xlsx", "bore_log30.xlsx")
        kept_sf = "bore_log30.xlsx" if abstained[0] == "bore_log29.xlsx" else "bore_log29.xlsx"
        # Verify the abstained group's pipeline_diag entry
        abstained_diag = self._find_diag(abstained[0])
        assert abstained_diag.get("stopped_at") == "abstained_same_route_anchor_collision"
        reason = abstained_diag.get("abstain_reason") or {}
        assert reason.get("reason") == "same_route_anchor_collision"
        assert reason.get("route_id") == "route_477"
        assert reason.get("kept_source_file") == kept_sf
        assert "collision_source_files" in reason
        # Verify the kept group's pipeline_diag entry retains its placement
        kept_diag = self._find_diag(kept_sf)
        assert kept_diag.get("stopped_at") is None
        assert kept_diag.get("selected_route_id") == "route_477"

    # ── C. station_points / redline_segments removed for abstained group ──

    def test_brenham_29_30_env_on_abstained_segments_dropped(self) -> None:
        os.environ[COLLISION_ENV] = "1"
        self._seed_brenham_with_files(["bore_log29.xlsx", "bore_log30.xlsx"])
        M._rebuild_field_data_outputs(scope=RebuildScope.FULL)
        rcr = (M.STATE.get("coverage_sanity") or {}).get("route_collision_resolution") or {}
        abstained_set = set(rcr.get("abstained_source_files") or [])
        assert len(abstained_set) == 1
        for pt in M.STATE.get("station_points") or []:
            assert (pt.get("source_file") or "") not in abstained_set
        for seg in M.STATE.get("redline_segments") or []:
            assert (seg.get("source_file") or "") not in abstained_set

    # ── D. coverage_sanity recomputed (collision disappears post-resolution)

    def test_brenham_29_30_env_on_coverage_sanity_recomputed(self) -> None:
        os.environ[COLLISION_ENV] = "1"
        self._seed_brenham_with_files(["bore_log29.xlsx", "bore_log30.xlsx"])
        M._rebuild_field_data_outputs(scope=RebuildScope.FULL)
        cs = M.STATE.get("coverage_sanity") or {}
        # After abstaining one of the colliding groups, there's only 1
        # placed group on route_477 → no more collisions on it.
        assert cs.get("same_route_anchor_collision_detected") is False
        assert cs.get("same_route_anchor_collisions") == []
        assert cs.get("placed_group_count") == 1
        assert cs.get("abstained_group_count") == 1

    # ── E. Counts comparison: env OFF vs env ON on the same 2-file set ────

    def test_brenham_29_30_env_on_reduces_station_points(self) -> None:
        # Off
        self._seed_brenham_with_files(["bore_log29.xlsx", "bore_log30.xlsx"])
        M._rebuild_field_data_outputs(scope=RebuildScope.FULL)
        sp_off = len(M.STATE.get("station_points") or [])
        seg_off = len(M.STATE.get("redline_segments") or [])
        # On
        os.environ[COLLISION_ENV] = "1"
        self._seed_brenham_with_files(["bore_log29.xlsx", "bore_log30.xlsx"])
        M._rebuild_field_data_outputs(scope=RebuildScope.FULL)
        sp_on = len(M.STATE.get("station_points") or [])
        seg_on = len(M.STATE.get("redline_segments") or [])
        assert sp_on < sp_off, f"env ON ({sp_on}) should reduce station_points vs OFF ({sp_off})"
        assert seg_on < seg_off, f"env ON ({seg_on}) should reduce redline_segments vs OFF ({seg_off})"

    # ── F. Groups on different routes: no abstain when env ON ─────────────

    def test_brenham_groups_on_different_routes_neither_abstained_env_on(self) -> None:
        os.environ[COLLISION_ENV] = "1"
        # bore_log29 → route_477; pick a different bore-log that lands on
        # a different route (bore_log9 has different print, lands on
        # route_478 per the production-parity inspection).
        self._seed_brenham_with_files(["bore_log29.xlsx"])
        M._rebuild_field_data_outputs(scope=RebuildScope.FULL)
        cs = M.STATE.get("coverage_sanity") or {}
        rcr = cs.get("route_collision_resolution") or {}
        # Single placed group → no collisions → nothing to abstain
        assert rcr.get("applied") is False
        assert rcr.get("abstained_source_files") == []


if __name__ == "__main__":
    unittest.main()
