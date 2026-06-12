"""Offline contract tests for the static v2 -> web reviewer bundle export."""
from __future__ import annotations

import copy

import pytest

from truelinev2.proof.export_reviewer_bundle_json import (
    EXPORT_SCHEMA_VERSION,
    build_export,
    validate_export,
)
from truelinev2.review.reviewer_payloads import (
    ConfidenceClass,
    HumanAction,
    ReviewerLane,
    ReviewerPayload,
    RouteCandidate,
    SUGGESTION_LABEL,
)
from truelinev2.review.reviewer_service import (
    MODE_FLAGS,
    CorpusSource,
    ReviewerBundle,
    ReviewRunMode,
)

SOURCE_HEAD = "1fa3d6f5e9102ac6db40e2f58222a12bc2ae1c36"


def _bundle() -> ReviewerBundle:
    placed = ReviewerPayload(
        bore_id="log1",
        lane=ReviewerLane.PLACED_REVIEW,
        human_action=HumanAction.APPROVE_REJECT_EDIT,
        reason_code="EXACT_BOX_FOOTAGE_AND_ENDPOINTS",
        sheets=[10],
        station_start_sta="0+00",
        station_end_sta="4+15",
        station_start_ft=0.0,
        station_end_ft=415.0,
        footage_ft=415.0,
        confidence_class=ConfidenceClass.AUTO_EXACT_MATCH,
        evidence_summary="STA 0+00 TO STA 4+15",
    )
    suggestion = ReviewerPayload(
        bore_id="log2",
        lane=ReviewerLane.PICK_CARD_ROUTE_SUGGESTION,
        human_action=HumanAction.PICK_ONE_REJECT_ALL_OR_DRAW,
        reason_code="FRAME_OWNERSHIP_NOT_UNIQUE",
        sheets=[11],
        candidates=[
            RouteCandidate(
                candidate_id="log2-frame-s11-0",
                sheets=[11],
                station_math="10+00 - 100 ft -> 9+00",
                footage_check="chain contains 100 ft",
                evidence_summary="frame candidate",
                why_not_auto_placed="frame ownership is not unique",
                missing_relationship_to_promote="unique frame ownership",
            )
        ],
    )
    return ReviewerBundle(
        project_id="test-project",
        run_mode=ReviewRunMode.DEFAULT_BASELINE,
        flag_state=MODE_FLAGS[ReviewRunMode.DEFAULT_BASELINE],
        status_counts={
            "AUTO_SELECT": 1,
            "REVIEW": 0,
            "ABSTAIN": 1,
            "ERROR": 0,
            "PLACED": 1,
        },
        lane_counts={
            ReviewerLane.PLACED_REVIEW.value: 1,
            ReviewerLane.PICK_CARD_ROUTE_SUGGESTION.value: 1,
        },
        payloads=[placed, suggestion],
        source=CorpusSource(
            corpus_dir="X:/corpus",
            plan_pdf_path="X:/plan.pdf",
            sheet_offset=13,
            bore_log_count=2,
            bore_log_files=["bore_log1.xlsx", "bore_log2.xlsx"],
        ),
    )


def test_export_wraps_canonical_default_bundle_verbatim():
    bundle = _bundle()
    canonical = bundle.model_dump(mode="json")

    export = build_export(bundle, SOURCE_HEAD)

    assert export["export_schema_version"] == EXPORT_SCHEMA_VERSION
    assert export["source"]["source_git_head"] == SOURCE_HEAD
    assert export["source"]["run_mode"] == "default_baseline"
    assert export["bundle"] == canonical
    assert bundle.model_dump(mode="json") == canonical


def test_export_preserves_closed_confidence_and_suggestion_label():
    export = build_export(_bundle(), SOURCE_HEAD)
    payloads = export["bundle"]["payloads"]

    assert payloads[0]["confidence_class"] == "AUTO_EXACT_MATCH"
    assert payloads[1]["candidates"][0]["label"] == SUGGESTION_LABEL
    assert "segments" not in str(export)
    assert "stroke_points" not in str(export)


def test_export_rejects_truth_or_geometry_drift():
    export = build_export(_bundle(), SOURCE_HEAD)

    bad_label = copy.deepcopy(export)
    bad_label["bundle"]["payloads"][1]["candidates"][0]["label"] = "PLACEMENT"
    with pytest.raises(ValueError, match="suggestion label drift"):
        validate_export(bad_label)

    numeric_confidence = copy.deepcopy(export)
    numeric_confidence["bundle"]["payloads"][0]["confidence_class"] = 0.99
    with pytest.raises(ValueError, match="numeric confidence"):
        validate_export(numeric_confidence)

    geometry = copy.deepcopy(export)
    geometry["bundle"]["payloads"][0]["segments"] = [{"stroke_points": [[1, 2]]}]
    with pytest.raises(ValueError, match="geometry/artifact"):
        validate_export(geometry)


def test_export_rejects_nonbaseline_mode_claim():
    export = build_export(_bundle(), SOURCE_HEAD)
    export["source"]["run_mode"] = ReviewRunMode.FULLEST_SAFE_REVIEW.value
    with pytest.raises(ValueError, match="default_baseline"):
        validate_export(export)
