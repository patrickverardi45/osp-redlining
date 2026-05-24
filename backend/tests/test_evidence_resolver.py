"""Tests for backend/app/core/evidence_resolver.py.

Pure unit tests against the decision logic + packet shape contract.
The resolver is ADVISORY — these tests verify the decision tag and
evidence packet are produced correctly; they do not verify any
placement-modifying behavior because the resolver does not modify
placement in this sprint.
"""

from __future__ import annotations

import copy
import os

os.environ.setdefault("TRUELINE_JWT_SECRET", "resolver-test-secret")
os.environ.setdefault("TRUELINE_AUTH_JWT_SECRET", "resolver-test-auth-secret")
os.environ.setdefault("TRUELINE_ALLOWED_ORIGINS", "http://localhost:3000")

from backend.app.core.evidence_resolver import (
    DECISION_ABSTAIN_CONFLICT,
    DECISION_ABSTAIN_INSUFFICIENT_EVIDENCE,
    DECISION_PLACE_CONFIDENTLY,
    DECISION_PLACE_WITH_CAUTION,
    resolve_evidence_for_group,
)


def _group_rows(notes: str = "", print_token: str = "1", source_file: str = "test.xlsx", crew: str = "crew_a", date: str = "2026-01-01") -> list:
    return [
        {"station": "0+00", "station_ft": 0.0, "depth_ft": 5.0, "boc_ft": 4.0, "date": date, "crew": crew, "print": print_token, "notes": notes, "source_file": source_file},
        {"station": "1+00", "station_ft": 100.0, "depth_ft": 5.0, "boc_ft": 4.0, "date": date, "crew": crew, "print": print_token, "notes": notes, "source_file": source_file},
    ]


def _normalized_group() -> dict:
    return {"group_id": "group_1", "span_ft": 100.0}


def _filter_meta(allowed=("route_478",), hints=("E STONE ST",)) -> dict:
    return {
        "applied": True,
        "mode": "print_to_street_extraction",
        "print_tokens": ["1"],
        "sheet_numbers": [1],
        "street_hints": list(hints),
        "allowed_route_ids": list(allowed),
        "reason": "test",
    }


def _ranking(route_id: str = "route_478", score: float = 0.5) -> dict:
    return {"route_id": route_id, "route_name": "Test Route", "score": score, "route_length_ft": 1000.0}


def _mismatch() -> dict:
    return {
        "notes_streets": ["CHERI LN"],
        "filter_streets": ["E STONE ST"],
        "severity": "REVIEW",
        "source": "bore_log_notes_vs_print_filter",
    }


def _ace_result(route_id: str = "route_trunk") -> dict:
    return {
        "source": "kmz_point_to_linestring_proximity",
        "notes_streets": ["LAWNDALE AVE"],
        "discovered_route_ids": [route_id],
        "selected_candidate_route_id": route_id,
        "evidence": {
            "point_count": 17,
            "coverage_count": 14,
            "coverage_ratio": 0.82,
            "distance_threshold_ft": 100.0,
            "nearest_distance_ft": 39.2,
            "route_name": "Underground Cable",
            "source_folder": "Connections / underground cable",
        },
    }


def test_decision_place_confidently_when_strong_ranking_no_mismatch() -> None:
    p = resolve_evidence_for_group(
        _group_rows(),
        _normalized_group(),
        _filter_meta(),
        [_ranking("route_478", 0.80), _ranking("route_500", 0.50)],
        location_evidence_mismatch=None,
        auto_candidate_expansion=None,
    )
    assert p["decision"] == DECISION_PLACE_CONFIDENTLY


def test_decision_place_with_caution_when_top1_top2_within_clean_margin() -> None:
    p = resolve_evidence_for_group(
        _group_rows(),
        _normalized_group(),
        _filter_meta(),
        [_ranking("route_478", 0.50), _ranking("route_500", 0.48)],
        location_evidence_mismatch=None,
        auto_candidate_expansion=None,
    )
    assert p["decision"] == DECISION_PLACE_WITH_CAUTION
    assert "top_2_scores_within_clean_margin" in p["conflicts"]


def test_decision_abstain_conflict_when_mismatch_and_no_expansion() -> None:
    p = resolve_evidence_for_group(
        _group_rows(notes="CHERI LN"),
        _normalized_group(),
        _filter_meta(),
        [_ranking("route_478", 0.50)],
        location_evidence_mismatch=_mismatch(),
        auto_candidate_expansion=None,
    )
    assert p["decision"] == DECISION_ABSTAIN_CONFLICT
    assert "notes_streets_disjoint_from_print_hint_streets" in p["conflicts"]


def test_decision_abstain_insufficient_when_no_rankings() -> None:
    p = resolve_evidence_for_group(
        _group_rows(),
        _normalized_group(),
        _filter_meta(allowed=()),
        rankings=[],
        location_evidence_mismatch=None,
        auto_candidate_expansion=None,
    )
    assert p["decision"] == DECISION_ABSTAIN_INSUFFICIENT_EVIDENCE
    assert "no_ranking_candidates_after_filter" in p["conflicts"]


def test_decision_abstain_insufficient_when_top1_below_floor() -> None:
    p = resolve_evidence_for_group(
        _group_rows(),
        _normalized_group(),
        _filter_meta(),
        [_ranking("route_478", 0.10)],
        location_evidence_mismatch=None,
        auto_candidate_expansion=None,
    )
    assert p["decision"] == DECISION_ABSTAIN_INSUFFICIENT_EVIDENCE


def test_decision_place_confidently_when_expansion_rescues_mismatch() -> None:
    p = resolve_evidence_for_group(
        _group_rows(notes="LAWNDALE AVE"),
        _normalized_group(),
        _filter_meta(allowed=("route_trunk", "route_478")),
        [_ranking("route_trunk", 0.55), _ranking("route_478", 0.20)],
        location_evidence_mismatch={
            "notes_streets": ["LAWNDALE AVE"],
            "filter_streets": ["E STONE ST"],
            "severity": "REVIEW",
            "source": "bore_log_notes_vs_print_filter",
        },
        auto_candidate_expansion=_ace_result("route_trunk"),
    )
    assert p["decision"] == DECISION_PLACE_CONFIDENTLY
    assert len(p["kmz_point_address_candidates"]) == 1
    assert p["kmz_point_address_candidates"][0]["route_id"] == "route_trunk"


def test_packet_carries_required_fields() -> None:
    p = resolve_evidence_for_group(
        _group_rows(notes="some notes", source_file="bore_log42.xlsx", crew="crew_x", date="2026-02-15"),
        _normalized_group(),
        _filter_meta(),
        [_ranking()],
        location_evidence_mismatch=None,
        auto_candidate_expansion=None,
    )
    required = {
        "source_file", "notes_streets", "print_refs", "station_range",
        "date_values", "crew_values", "print_hint_route_ids",
        "print_hint_street_hints", "kmz_route_candidates",
        "kmz_point_address_candidates", "pdf_evidence",
        "sequence_evidence", "coverage_evidence", "conflicts",
        "confidence", "decision", "decision_basis",
    }
    assert required.issubset(p.keys())
    assert p["source_file"] == "bore_log42.xlsx"
    assert p["crew_values"] == ["crew_x"]
    assert p["date_values"] == ["2026-02-15"]


def test_station_range_computed_correctly() -> None:
    p = resolve_evidence_for_group(
        _group_rows(),
        _normalized_group(),
        _filter_meta(),
        [_ranking()],
        location_evidence_mismatch=None,
        auto_candidate_expansion=None,
    )
    sr = p["station_range"]
    assert sr["min_ft"] == 0.0
    assert sr["max_ft"] == 100.0
    assert sr["span_ft"] == 100.0
    assert sr["row_count"] == 2


def test_confidence_is_bounded_zero_to_one() -> None:
    for score in (0.0, 0.10, 0.50, 0.90, 1.0):
        p = resolve_evidence_for_group(
            _group_rows(),
            _normalized_group(),
            _filter_meta(),
            [_ranking("a", score)],
            location_evidence_mismatch=None,
            auto_candidate_expansion=None,
        )
        assert 0.0 <= p["confidence"] <= 1.0


def test_confidence_collapses_to_near_zero_under_mismatch_without_expansion() -> None:
    p = resolve_evidence_for_group(
        _group_rows(notes="CHERI LN"),
        _normalized_group(),
        _filter_meta(),
        [_ranking("route_478", 0.80)],
        location_evidence_mismatch=_mismatch(),
        auto_candidate_expansion=None,
    )
    p_clean = resolve_evidence_for_group(
        _group_rows(),
        _normalized_group(),
        _filter_meta(),
        [_ranking("route_478", 0.80)],
        location_evidence_mismatch=None,
        auto_candidate_expansion=None,
    )
    assert p["confidence"] < p_clean["confidence"]


def test_resolver_does_not_mutate_inputs() -> None:
    rows = _group_rows()
    ng = _normalized_group()
    fm = _filter_meta()
    rk = [_ranking()]
    rows_snap = copy.deepcopy(rows)
    ng_snap = copy.deepcopy(ng)
    fm_snap = copy.deepcopy(fm)
    rk_snap = copy.deepcopy(rk)
    _ = resolve_evidence_for_group(rows, ng, fm, rk, None, None)
    assert rows == rows_snap
    assert ng == ng_snap
    assert fm == fm_snap
    assert rk == rk_snap
