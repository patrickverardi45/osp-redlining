"""Location-Mismatch V4 rescue tests.

Two test classes:

  1. TestLocationMismatchRescuePure — pure unit tests against the
     allowlist + relaxed-gate logic. No STATE, no rebuild loop.

  2. TestLocationMismatchRescueWiring — env-gated integration tests
     against the rebuild loop with synthetic catalog + address points.
     Empty corpus is used to verify the env-OFF + env-ON-no-data
     scenarios do not crash and stamp no V4 diagnostic.
"""

from __future__ import annotations

import copy
import os
import unittest
import uuid
from typing import Any, Dict, List, Optional

os.environ.setdefault("TRUELINE_JWT_SECRET", "v4-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "v4-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend import main as M
from backend.app.core.location_mismatch_rescue import (
    _LAWNDALE_ALLOWLIST,
    _matches_lawndale_allowlist,
    attempt_location_mismatch_rescue,
)
from backend.app.core.rebuild_scope import RebuildScope

RESCUE_ENV = "TRUELINE_LOCATION_MISMATCH_MATRIX_RESCUE"
LOC_ABSTAIN_ENV = "TRUELINE_ABSTAIN_ON_LOCATION_MISMATCH"
AUTO_EXP_ENV = "TRUELINE_AUTO_CANDIDATE_EXPANSION"


# ── Fixture builders ─────────────────────────────────────────────────────


def _route(route_id: str, *, route_name: str = "Trunk", score_hint: float = 0.18,
           length_ft: float = 4500.0) -> Dict[str, Any]:
    return {
        "route_id": route_id, "route_name": route_name,
        "source_folder": "Backbone", "route_role": "underground_cable",
        "length_ft": length_ft, "point_count": 4,
        "coords": [[-96.40, 30.155], [-96.395, 30.155],
                   [-96.39, 30.155], [-96.385, 30.155]],
        "_score_hint": score_hint,
    }


def _ranking(route_id: str, score: float = 0.42) -> Dict[str, Any]:
    return {"route_id": route_id, "route_name": f"{route_id} name",
            "score": score, "route_length_ft": 300.0}


def _stub_discover(*, discovered: List[str], evidence: Optional[Dict[str, Any]] = None):
    def _f(notes_streets, address_points, route_catalog):
        return {
            "discovered_route_ids": list(discovered),
            "source": "stub",
            "evidence": evidence or {},
        }
    return _f


def _stub_discover_none():
    def _f(notes_streets, address_points, route_catalog):
        return None
    return _f


def _stub_score(score: float = 0.18, route_name: str = "Lawndale Trunk"):
    def _f(group_rows, route):
        return {
            "route_id": route.get("route_id"),
            "route_name": route_name,
            "route_role": route.get("route_role"),
            "source_folder": route.get("source_folder"),
            "score": score,
            "route_length_ft": route.get("length_ft"),
            "expected_span_ft": 300.0,
            "length_gap_ft": 200.0,
            "reason": "stub",
        }
    return _f


def _stub_find_route(catalog: List[Dict[str, Any]]):
    by_id = {str(r.get("route_id")): r for r in catalog}
    def _f(rid):
        return by_id.get(str(rid))
    return _f


class TestLocationMismatchRescuePure(unittest.TestCase):
    """Pure function tests — no STATE, no rebuild loop."""

    # ── Allowlist gate ────────────────────────────────────────────────

    def test_lawndale_allowlist_constants(self) -> None:
        # Test #4 — HUISACHE alone must NOT be in allowlist
        assert "HUISACHE" not in _LAWNDALE_ALLOWLIST
        # Test #3 — CHERI must NOT be in allowlist
        assert "CHERI LN" not in _LAWNDALE_ALLOWLIST
        # LAWNDALE family must be
        assert "LAWNDALE" in _LAWNDALE_ALLOWLIST
        assert "LAWNDALE AVE" in _LAWNDALE_ALLOWLIST
        assert "LAWNDALE AVENUE" in _LAWNDALE_ALLOWLIST

    def test_matches_lawndale_case_insensitive(self) -> None:
        assert _matches_lawndale_allowlist(["lawndale ave"]) is True
        assert _matches_lawndale_allowlist(["Lawndale Avenue"]) is True
        assert _matches_lawndale_allowlist(["LAWNDALE  AVE"]) is True  # extra spaces collapse
        assert _matches_lawndale_allowlist(["CHERI LN"]) is False
        assert _matches_lawndale_allowlist(["HUISACHE"]) is False
        assert _matches_lawndale_allowlist([]) is False

    # ── Test #3 — CHERI still abstains ────────────────────────────────

    def test_cheri_returns_skipped_not_lawndale(self) -> None:
        catalog = [_route("route_X")]
        out = attempt_location_mismatch_rescue(
            notes_streets=["CHERI LN"], filter_streets=["POST OAK CT"],
            current_rankings=[_ranking("route_X", score=0.42)],
            route_catalog=catalog, address_points=[], group_rows=[],
            discover_callback=_stub_discover(discovered=["route_LAWN"]),
            score_callback=_stub_score(0.50),
            find_route_callback=_stub_find_route(catalog),
        )
        assert out["outcome"] == "skipped_not_lawndale"
        assert out["rescued"] is False
        assert out["selected_route_id"] is None

    # ── Test #4 — HUISACHE alone still abstains ───────────────────────

    def test_huisache_alone_returns_skipped_not_lawndale(self) -> None:
        catalog = [_route("route_X")]
        out = attempt_location_mismatch_rescue(
            notes_streets=["HUISACHE"], filter_streets=["CARLEE DR"],
            current_rankings=[_ranking("route_X", score=0.42)],
            route_catalog=catalog, address_points=[], group_rows=[],
            discover_callback=_stub_discover(discovered=["route_LAWN"]),
            score_callback=_stub_score(0.50),
            find_route_callback=_stub_find_route(catalog),
        )
        assert out["outcome"] == "skipped_not_lawndale"
        assert out["rescued"] is False

    # ── Test #2 — LAWNDALE rescued under absolute gate ────────────────

    def test_lawndale_rescued_absolute_gate(self) -> None:
        # Discovered score 0.18; absolute floor 0.15 → PASS
        catalog = [_route("route_LAWN")]
        out = attempt_location_mismatch_rescue(
            notes_streets=["LAWNDALE AVE"], filter_streets=["CARLEE DR"],
            current_rankings=[_ranking("route_OLD", score=0.42)],
            route_catalog=catalog, address_points=[{"x": 1}],
            group_rows=[],
            discover_callback=_stub_discover(discovered=["route_LAWN"]),
            score_callback=_stub_score(0.18),
            find_route_callback=_stub_find_route(catalog),
            min_absolute_score=0.15,
            score_ratio_fallback=0.60,
        )
        assert out["outcome"] == "rescued"
        assert out["rescued"] is True
        assert out["selected_route_id"] == "route_LAWN"
        assert out["selected_score"] == 0.18
        assert out["absolute_gate_passes"] is True
        assert out["scored_full"] is not None
        assert out["reason"] == "lawndale_allowlist_absolute_gate_pass"

    def test_lawndale_with_huisache_rescued(self) -> None:
        catalog = [_route("route_LAWN")]
        out = attempt_location_mismatch_rescue(
            notes_streets=["LAWNDALE AVE", "HUISACHE"],
            filter_streets=["CARLEE DR"],
            current_rankings=[_ranking("route_OLD", score=0.42)],
            route_catalog=catalog, address_points=[{"x": 1}],
            group_rows=[],
            discover_callback=_stub_discover(discovered=["route_LAWN"]),
            score_callback=_stub_score(0.20),
            find_route_callback=_stub_find_route(catalog),
        )
        assert out["outcome"] == "rescued"
        assert out["selected_route_id"] == "route_LAWN"

    # ── Ratio gate ────────────────────────────────────────────────────

    def test_ratio_gate_passes_when_absolute_fails(self) -> None:
        # Discovered 0.10, top 0.15, ratio 0.10 / 0.15 = 0.667 >= 0.60 → PASS
        # Absolute 0.10 < 0.15 → FAIL absolute
        catalog = [_route("route_LAWN")]
        out = attempt_location_mismatch_rescue(
            notes_streets=["LAWNDALE AVE"], filter_streets=["X"],
            current_rankings=[_ranking("route_OLD", score=0.15)],
            route_catalog=catalog, address_points=[{"x": 1}],
            group_rows=[],
            discover_callback=_stub_discover(discovered=["route_LAWN"]),
            score_callback=_stub_score(0.10),
            find_route_callback=_stub_find_route(catalog),
        )
        assert out["outcome"] == "rescued"
        assert out["absolute_gate_passes"] is False
        assert out["ratio_gate_passes"] is True
        assert out["reason"] == "lawndale_allowlist_ratio_gate_pass"

    # ── Reject paths ──────────────────────────────────────────────────

    def test_lawndale_rejected_when_no_discovery(self) -> None:
        catalog = [_route("route_LAWN")]
        out = attempt_location_mismatch_rescue(
            notes_streets=["LAWNDALE AVE"], filter_streets=["X"],
            current_rankings=[_ranking("route_OLD", score=0.42)],
            route_catalog=catalog, address_points=[],
            group_rows=[],
            discover_callback=_stub_discover_none(),
            score_callback=_stub_score(0.50),
            find_route_callback=_stub_find_route(catalog),
        )
        assert out["outcome"] == "rejected_no_discovery"
        assert out["rescued"] is False

    def test_lawndale_rejected_when_route_missing_from_catalog(self) -> None:
        # Discovery returns route_GHOST but catalog has no such route
        catalog: List[Dict[str, Any]] = []
        out = attempt_location_mismatch_rescue(
            notes_streets=["LAWNDALE AVE"], filter_streets=["X"],
            current_rankings=[_ranking("route_OLD", score=0.42)],
            route_catalog=catalog, address_points=[{"x": 1}],
            group_rows=[],
            discover_callback=_stub_discover(discovered=["route_GHOST"]),
            score_callback=_stub_score(0.50),
            find_route_callback=_stub_find_route(catalog),
        )
        assert out["outcome"] == "rejected_no_route_in_catalog"
        assert out["rescued"] is False

    def test_lawndale_rejected_when_below_both_gates(self) -> None:
        # Discovered 0.05, top 0.50 → absolute fails (0.05<0.15), ratio fails (0.05/0.50=0.10<0.60)
        catalog = [_route("route_LAWN")]
        out = attempt_location_mismatch_rescue(
            notes_streets=["LAWNDALE AVE"], filter_streets=["X"],
            current_rankings=[_ranking("route_OLD", score=0.50)],
            route_catalog=catalog, address_points=[{"x": 1}],
            group_rows=[],
            discover_callback=_stub_discover(discovered=["route_LAWN"]),
            score_callback=_stub_score(0.05),
            find_route_callback=_stub_find_route(catalog),
        )
        assert out["outcome"] == "rejected_below_gate"
        assert out["rescued"] is False
        assert out["absolute_gate_passes"] is False
        assert out["ratio_gate_passes"] is False
        assert out["best_discovered_score"] == 0.05

    # ── Diagnostic payload shape ──────────────────────────────────────

    def test_rescued_diag_includes_all_required_fields(self) -> None:
        catalog = [_route("route_LAWN", route_name="Underground Cable Trunk")]
        out = attempt_location_mismatch_rescue(
            notes_streets=["LAWNDALE AVE"], filter_streets=["CARLEE DR"],
            current_rankings=[_ranking("route_OLD", score=0.42)],
            route_catalog=catalog, address_points=[{"x": 1}],
            group_rows=[],
            discover_callback=_stub_discover(
                discovered=["route_LAWN"],
                evidence={"coverage_ratio": 0.65, "point_count": 17},
            ),
            score_callback=_stub_score(0.18, route_name="Underground Cable Trunk"),
            find_route_callback=_stub_find_route(catalog),
        )
        for key in ("notes_streets", "original_filter_streets",
                    "original_top_route_id", "original_top_score",
                    "selected_route_id", "selected_route_name", "selected_score",
                    "evidence_source", "rescue_allowlist", "discovered_route_ids",
                    "best_discovered_score", "thresholds", "reason",
                    "scored_full", "discovery_evidence"):
            assert key in out, f"missing key: {key}"
        assert out["evidence_source"] == "kmz_point_address"
        assert out["rescue_allowlist"] == "LAWNDALE"
        assert out["discovery_evidence"]["coverage_ratio"] == 0.65

    # ── Purity ────────────────────────────────────────────────────────

    def test_does_not_mutate_inputs(self) -> None:
        catalog = [_route("route_LAWN")]
        notes = ["LAWNDALE AVE"]
        filters = ["CARLEE DR"]
        rankings = [_ranking("route_OLD", score=0.42)]
        catalog_snap = copy.deepcopy(catalog)
        notes_snap = copy.deepcopy(notes)
        filters_snap = copy.deepcopy(filters)
        rankings_snap = copy.deepcopy(rankings)
        attempt_location_mismatch_rescue(
            notes_streets=notes, filter_streets=filters,
            current_rankings=rankings, route_catalog=catalog,
            address_points=[{"x": 1}], group_rows=[],
            discover_callback=_stub_discover(discovered=["route_LAWN"]),
            score_callback=_stub_score(0.18),
            find_route_callback=_stub_find_route(catalog),
        )
        assert catalog == catalog_snap
        assert notes == notes_snap
        assert filters == filters_snap
        assert rankings == rankings_snap


class TestLocationMismatchRescueWiring(unittest.TestCase):
    """Env-gated integration tests against the rebuild loop."""

    def setUp(self) -> None:
        self._saved_state = copy.deepcopy(dict(M.STATE))
        self._saved = {
            k: os.environ.pop(k, None)
            for k in (RESCUE_ENV, LOC_ABSTAIN_ENV, AUTO_EXP_ENV)
        }
        self._session_id = f"v4_{uuid.uuid4().hex[:12]}"

    def tearDown(self) -> None:
        M.STATE.clear()
        M.STATE.update(self._saved_state)
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _seed_empty(self) -> None:
        M.STATE.clear()
        M.STATE.update({
            "committed_rows": [],
            "route_catalog": [],
            "address_points": [],
            "_session_id_hint": self._session_id,
            "engineering_plans": [],
        })

    # Test #1 — Env OFF preserves current behavior (no V4 diag)
    def test_env_off_no_v4_diagnostic_emitted(self) -> None:
        # All upstream flags ON to reach the V4 seam, but RESCUE_ENV unset.
        os.environ[LOC_ABSTAIN_ENV] = "1"
        os.environ[AUTO_EXP_ENV] = "1"
        self._seed_empty()
        M._rebuild_field_data_outputs(scope=RebuildScope.FULL)
        diag = M.STATE.get("pipeline_diag") or []
        for entry in diag:
            assert "location_mismatch_rescue_selected" not in entry
            assert "location_mismatch_rescue_rejected" not in entry

    # Test #5 — Non-location-mismatch path is unaffected
    def test_groups_without_location_mismatch_have_no_v4_diag(self) -> None:
        os.environ[RESCUE_ENV] = "1"
        os.environ[LOC_ABSTAIN_ENV] = "1"
        self._seed_empty()
        M._rebuild_field_data_outputs(scope=RebuildScope.FULL)
        diag = M.STATE.get("pipeline_diag") or []
        # Empty corpus → zero pipeline_diag entries → no V4 stamps anywhere
        for entry in diag:
            assert "location_mismatch_rescue_selected" not in entry


if __name__ == "__main__":
    unittest.main()
