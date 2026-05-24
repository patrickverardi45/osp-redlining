"""Candidate Matrix V1 tests."""

from __future__ import annotations

import copy
import os
import unittest
import uuid
from typing import Any, Dict, List, Tuple

os.environ.setdefault("TRUELINE_JWT_SECRET", "matrix-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "matrix-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend import main as M
from backend.app.core.candidate_matrix import (
    SCHEMA_VERSION,
    build_expanded_candidate_pool,
)
from backend.app.core.rebuild_scope import RebuildScope

MATRIX_ENV = "TRUELINE_EXPANDED_CANDIDATE_MATRIX"
ABSTAIN_ENV = "TRUELINE_ABSTAIN_ON_ROUTE_COLLISION"
V2_ENV = "TRUELINE_ROUTE_COLLISION_ALTERNATE_SEARCH"


def _route(route_id: str, *,
           route_name: str = "Synth Route",
           source_folder: str = "Backbone",
           route_role: str = "underground_cable",
           length_ft: float = 300.0,
           coords: Tuple[Tuple[float, float], ...] = ((-96.40, 30.155), (-96.399, 30.155))) -> Dict[str, Any]:
    return {
        "route_id": route_id,
        "route_name": route_name,
        "source_folder": source_folder,
        "route_role": route_role,
        "length_ft": length_ft,
        "coords": [list(c) for c in coords],
        "point_count": len(coords),
    }


def _ranking(route_id: str, score: float = 0.40) -> Dict[str, Any]:
    return {"route_id": route_id, "route_name": f"{route_id} name",
            "score": score, "route_length_ft": 300.0}


class TestCandidateMatrixPure(unittest.TestCase):
    """Pure-function tests with synthetic catalogs."""

    def test_schema_version_attached(self) -> None:
        out = build_expanded_candidate_pool(
            source_file="x.xlsx", base_rankings=[], base_filter_meta={},
            route_catalog=[], address_points=[], notes_streets=[],
            span_ft=100.0, print_sheet_index={},
        )
        assert out["matrix"]["schema"] == SCHEMA_VERSION
        assert out["matrix"]["source_file"] == "x.xlsx"

    def test_empty_inputs_yield_zero_expansion(self) -> None:
        out = build_expanded_candidate_pool(
            source_file="x.xlsx", base_rankings=[], base_filter_meta={},
            route_catalog=[], address_points=[], notes_streets=[],
            span_ft=100.0, print_sheet_index={},
        )
        assert out["additional_route_ids"] == []
        assert out["matrix"]["expanded_candidate_count"] == 0

    def test_source_2_admits_routes_within_proximity(self) -> None:
        catalog = [
            _route("route_A", coords=((-96.4000, 30.155), (-96.3990, 30.155)),
                   length_ft=300.0),
            _route("route_B", coords=((-96.4000, 30.15513), (-96.3990, 30.15513)),
                   length_ft=300.0),
        ]
        out = build_expanded_candidate_pool(
            source_file="x.xlsx",
            base_rankings=[_ranking("route_A")],
            base_filter_meta={"sheet_numbers": []},
            route_catalog=catalog, address_points=[], notes_streets=[],
            span_ft=300.0, print_sheet_index={},
            geometry_proximity_ft=200.0,
        )
        assert "route_B" in out["additional_route_ids"]
        assert "route_B" in out["matrix"]["candidate_sources"]["geometry_proximity_to_top"]

    def test_source_2_rejects_distant_routes(self) -> None:
        catalog = [
            _route("route_A", source_folder="A_folder", route_role="role_A",
                   coords=((-96.40, 30.155), (-96.399, 30.155)),
                   length_ft=300.0),
            _route("route_C", source_folder="C_folder", route_role="role_C",
                   coords=((-96.40, 30.165), (-96.399, 30.165)),
                   length_ft=300.0),
        ]
        out = build_expanded_candidate_pool(
            source_file="x.xlsx",
            base_rankings=[_ranking("route_A")],
            base_filter_meta={"sheet_numbers": []},
            route_catalog=catalog, address_points=[], notes_streets=[],
            span_ft=300.0, print_sheet_index={},
            geometry_proximity_ft=200.0, fallback_proximity_ft=200.0,
        )
        assert "route_C" not in out["additional_route_ids"]
        reject_reasons = {(r["route_id"], r["reason"])
                          for r in out["rejected_candidates"]}
        assert any(rid == "route_C" and "proximity" in reason
                   for rid, reason in reject_reasons)

    def test_source_3_skipped_when_no_notes_streets(self) -> None:
        catalog = [_route("route_A"), _route("route_B")]
        out = build_expanded_candidate_pool(
            source_file="x.xlsx",
            base_rankings=[_ranking("route_A")],
            base_filter_meta={}, route_catalog=catalog,
            address_points=[], notes_streets=[],
            span_ft=300.0, print_sheet_index={},
        )
        assert out["matrix"]["candidate_sources"]["kmz_point_address"] == []

    def test_source_4_admits_same_source_folder(self) -> None:
        catalog = [
            _route("route_A", source_folder="Backbone / NorthSubA",
                   coords=((-96.40, 30.155), (-96.399, 30.155)), length_ft=300.0),
            _route("route_B", source_folder="Backbone / NorthSubA",
                   coords=((-96.50, 30.155), (-96.499, 30.155)), length_ft=300.0),
        ]
        out = build_expanded_candidate_pool(
            source_file="x.xlsx",
            base_rankings=[_ranking("route_A")],
            base_filter_meta={}, route_catalog=catalog,
            address_points=[], notes_streets=[],
            span_ft=300.0, print_sheet_index={},
            geometry_proximity_ft=100.0,
        )
        assert "route_B" in out["additional_route_ids"]
        assert "route_B" in out["matrix"]["candidate_sources"]["same_source_folder_or_role"]

    def test_source_4_role_match_requires_proximity(self) -> None:
        catalog = [
            _route("route_A", source_folder="Folder1", route_role="underground_cable",
                   coords=((-96.40, 30.155), (-96.399, 30.155)), length_ft=300.0),
            _route("route_C", source_folder="Folder2", route_role="underground_cable",
                   coords=((-96.50, 30.155), (-96.499, 30.155)), length_ft=300.0),
        ]
        out = build_expanded_candidate_pool(
            source_file="x.xlsx",
            base_rankings=[_ranking("route_A")],
            base_filter_meta={}, route_catalog=catalog,
            address_points=[], notes_streets=[],
            span_ft=300.0, print_sheet_index={},
            geometry_proximity_ft=200.0,
            fallback_proximity_ft=200.0,
        )
        assert "route_C" not in out["additional_route_ids"]
        reasons = {(r["route_id"], r["reason"]) for r in out["rejected_candidates"]}
        assert any(rid == "route_C" and "role_match_but_outside_proximity" in reason
                   for rid, reason in reasons)

    def test_source_5_admits_routes_from_adjacent_prints(self) -> None:
        catalog = [
            _route("route_A", source_folder="A", route_role="role_A",
                   coords=((-96.40, 30.155), (-96.399, 30.155))),
            _route("route_B", source_folder="B", route_role="role_B",
                   coords=((-96.50, 30.155), (-96.499, 30.155))),
            _route("route_C", source_folder="C", route_role="role_C",
                   coords=((-96.30, 30.155), (-96.299, 30.155))),
        ]
        psi = {
            "23": {"sheet": 23, "streets": ["X"], "route_ids": ["route_A"]},
            "22": {"sheet": 22, "streets": ["Y"], "route_ids": ["route_B"]},
            "24": {"sheet": 24, "streets": ["Z"], "route_ids": ["route_C"]},
        }
        out = build_expanded_candidate_pool(
            source_file="x.xlsx",
            base_rankings=[_ranking("route_A")],
            base_filter_meta={"sheet_numbers": [23]},
            route_catalog=catalog, address_points=[], notes_streets=[],
            span_ft=300.0, print_sheet_index=psi,
            adjacent_print_radius=1,
            geometry_proximity_ft=10.0,
            fallback_proximity_ft=10.0,
        )
        assert "route_B" in out["matrix"]["candidate_sources"]["adjacent_print_or_sheet"]
        assert "route_C" in out["matrix"]["candidate_sources"]["adjacent_print_or_sheet"]

    def test_source_5_skips_when_no_sheet_numbers(self) -> None:
        catalog = [_route("route_A"), _route("route_B")]
        psi = {"23": {"sheet": 23, "streets": ["X"], "route_ids": ["route_B"]}}
        out = build_expanded_candidate_pool(
            source_file="x.xlsx", base_rankings=[_ranking("route_A")],
            base_filter_meta={"sheet_numbers": []},
            route_catalog=catalog, address_points=[], notes_streets=[],
            span_ft=300.0, print_sheet_index=psi,
            geometry_proximity_ft=10.0,
        )
        assert out["matrix"]["candidate_sources"]["adjacent_print_or_sheet"] == []

    def test_length_gate_rejects_undersized_routes(self) -> None:
        catalog = [
            _route("route_A", coords=((-96.40, 30.155), (-96.399, 30.155)), length_ft=1000.0),
            _route("route_B", coords=((-96.40, 30.15513), (-96.399, 30.15513)), length_ft=10.0),
        ]
        out = build_expanded_candidate_pool(
            source_file="x.xlsx",
            base_rankings=[_ranking("route_A")],
            base_filter_meta={}, route_catalog=catalog,
            address_points=[], notes_streets=[],
            span_ft=300.0, print_sheet_index={},
            min_route_length_ratio=0.30, max_route_length_ratio=5.00,
            geometry_proximity_ft=200.0,
        )
        assert "route_B" not in out["additional_route_ids"]
        rejects = {(r["route_id"], r["reason"]) for r in out["rejected_candidates"]}
        assert any(rid == "route_B" and "length_below" in reason
                   for rid, reason in rejects)

    def test_length_gate_rejects_oversized_routes(self) -> None:
        catalog = [
            _route("route_A", coords=((-96.40, 30.155), (-96.399, 30.155)), length_ft=300.0),
            _route("route_B", coords=((-96.40, 30.15513), (-96.399, 30.15513)), length_ft=5000.0),
        ]
        out = build_expanded_candidate_pool(
            source_file="x.xlsx",
            base_rankings=[_ranking("route_A")],
            base_filter_meta={}, route_catalog=catalog,
            address_points=[], notes_streets=[],
            span_ft=300.0, print_sheet_index={},
            min_route_length_ratio=0.30, max_route_length_ratio=5.00,
            geometry_proximity_ft=200.0,
        )
        assert "route_B" not in out["additional_route_ids"]
        rejects = {(r["route_id"], r["reason"]) for r in out["rejected_candidates"]}
        assert any(rid == "route_B" and "length_above" in reason
                   for rid, reason in rejects)

    def test_max_total_candidates_caps_additional(self) -> None:
        coords_at = lambda lat: ((-96.40, lat), (-96.399, lat))
        catalog = [_route("route_A", coords=coords_at(30.155), length_ft=300.0)]
        for i in range(20):
            catalog.append(_route(f"route_{i+10}", length_ft=300.0,
                                  coords=coords_at(30.155 + 0.0001 * (i + 1))))
        out = build_expanded_candidate_pool(
            source_file="x.xlsx",
            base_rankings=[_ranking("route_A")],
            base_filter_meta={}, route_catalog=catalog,
            address_points=[], notes_streets=[],
            span_ft=300.0, print_sheet_index={},
            max_total_candidates=5,
            geometry_proximity_ft=10000.0,
        )
        assert len(out["additional_route_ids"]) == 4
        cap_rejects = [r for r in out["rejected_candidates"]
                       if r.get("source") == "_cap"]
        assert len(cap_rejects) > 0

    def test_route_admitted_by_multiple_sources_attribution_list(self) -> None:
        catalog = [
            _route("route_A", coords=((-96.40, 30.155), (-96.399, 30.155)), length_ft=300.0),
            _route("route_B", coords=((-96.40, 30.15513), (-96.399, 30.15513)), length_ft=300.0),
        ]
        psi = {
            "23": {"sheet": 23, "streets": [], "route_ids": ["route_A"]},
            "24": {"sheet": 24, "streets": [], "route_ids": ["route_B"]},
        }
        out = build_expanded_candidate_pool(
            source_file="x.xlsx",
            base_rankings=[_ranking("route_A")],
            base_filter_meta={"sheet_numbers": [23]},
            route_catalog=catalog, address_points=[], notes_streets=[],
            span_ft=300.0, print_sheet_index=psi,
            geometry_proximity_ft=200.0, adjacent_print_radius=1,
        )
        sources_for_B = out["attribution_by_route_id"].get("route_B") or []
        assert "geometry_proximity_to_top" in sources_for_B
        assert "adjacent_print_or_sheet" in sources_for_B

    def test_does_not_mutate_inputs(self) -> None:
        catalog = [_route("route_A"), _route("route_B")]
        base_rankings = [_ranking("route_A")]
        base_filter_meta = {"sheet_numbers": [1]}
        psi = {"1": {"sheet": 1, "streets": [], "route_ids": ["route_A"]}}
        catalog_snap = copy.deepcopy(catalog)
        rankings_snap = copy.deepcopy(base_rankings)
        filter_snap = copy.deepcopy(base_filter_meta)
        psi_snap = copy.deepcopy(psi)
        build_expanded_candidate_pool(
            source_file="x.xlsx", base_rankings=base_rankings,
            base_filter_meta=base_filter_meta, route_catalog=catalog,
            address_points=[], notes_streets=[],
            span_ft=300.0, print_sheet_index=psi,
        )
        assert catalog == catalog_snap
        assert base_rankings == rankings_snap
        assert base_filter_meta == filter_snap
        assert psi == psi_snap


class TestCandidateMatrixWiring(unittest.TestCase):
    """Env-gated integration tests against the rebuild loop."""

    def setUp(self) -> None:
        self._saved_state = copy.deepcopy(dict(M.STATE))
        self._saved = {k: os.environ.pop(k, None) for k in (
            MATRIX_ENV, V2_ENV, ABSTAIN_ENV,
        )}
        self._session_id = f"mtx_{uuid.uuid4().hex[:12]}"

    def tearDown(self) -> None:
        M.STATE.clear()
        M.STATE.update(self._saved_state)
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _seed(self, rows: List[Dict[str, Any]], catalog: List[Dict[str, Any]]) -> None:
        M.STATE.clear()
        M.STATE.update({
            "committed_rows": list(rows),
            "route_catalog": list(catalog),
            "address_points": [],
            "_session_id_hint": self._session_id,
            "engineering_plans": [],
        })

    def test_matrix_env_off_no_candidate_matrix_diag_emitted(self) -> None:
        os.environ[ABSTAIN_ENV] = "1"
        os.environ[V2_ENV] = "1"
        self._seed([], [])
        M._rebuild_field_data_outputs(scope=RebuildScope.FULL)
        diag = (M.STATE.get("pipeline_diag") or [])
        for entry in diag:
            assert "candidate_matrix" not in entry

    def test_matrix_env_on_alone_without_v2_does_nothing(self) -> None:
        os.environ[MATRIX_ENV] = "1"
        self._seed([], [])
        M._rebuild_field_data_outputs(scope=RebuildScope.FULL)
        diag = (M.STATE.get("pipeline_diag") or [])
        for entry in diag:
            assert "candidate_matrix" not in entry


if __name__ == "__main__":
    unittest.main()
