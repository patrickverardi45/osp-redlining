"""Offline contract tests for the static v2 -> web reviewer bundle export."""
from __future__ import annotations

import copy

import pytest

from truelinev2.proof.export_reviewer_bundle_json import (
    EXPORT_SCHEMA_VERSION,
    build_export,
    validate_export,
)
from truelinev2.review.group_review import (
    GROUP_SCHEMA_VERSION,
    GroupMember,
    SharedAlignmentGroupCard,
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


def _group_card() -> SharedAlignmentGroupCard:
    return SharedAlignmentGroupCard(
        shared_origin="NEXTLINK@378,409",
        boundaries=("1+76", "1+77"),
        members=(
            GroupMember(
                bore_id="log8",
                boundary_raw="1+76",
                per_bore_status="STRUCTURE_IDENTITY_BINDING_REQUIRED",
                chain_hops=(("0+00", "1+10", 110.0), ("1+10", "1+76", 66.0)),
                conduit_evidence_count=2,
                origin_multiport=True,
            ),
            GroupMember(
                bore_id="log32",
                boundary_raw="1+77",
                per_bore_status="STRUCTURE_IDENTITY_BINDING_REQUIRED",
                chain_hops=(("0+00", "1+30", 130.0), ("1+30", "1+77", 47.0)),
                conduit_evidence_count=2,
                origin_multiport=True,
            ),
        ),
        detail="two distinct printed runs share one proven origin",
    )


def test_export_wraps_canonical_default_bundle_verbatim():
    bundle = _bundle()
    canonical = bundle.model_dump(mode="json")

    export = build_export(bundle, SOURCE_HEAD, group_cards=[_group_card()])

    assert export["export_schema_version"] == EXPORT_SCHEMA_VERSION
    assert export["source"]["source_git_head"] == SOURCE_HEAD
    assert export["source"]["run_mode"] == "default_baseline"
    assert export["bundle"] == canonical
    assert bundle.model_dump(mode="json") == canonical
    assert export["group_review"]["schema_version"] == GROUP_SCHEMA_VERSION
    assert export["group_review"]["service"] == "GroupReviewService"
    assert len(export["group_review"]["cards"]) == 1


def test_export_preserves_closed_confidence_and_suggestion_label():
    export = build_export(_bundle(), SOURCE_HEAD, group_cards=[_group_card()])
    payloads = export["bundle"]["payloads"]
    group = export["group_review"]["cards"][0]

    assert payloads[0]["confidence_class"] == "AUTO_EXACT_MATCH"
    assert payloads[1]["candidates"][0]["label"] == SUGGESTION_LABEL
    assert group["label"] == SUGGESTION_LABEL
    assert group["mode"] == "REVIEW_ONLY"
    assert group["auto"] is False
    assert "segments" not in str(export)
    assert "stroke_points" not in str(export)


def test_export_rejects_truth_or_geometry_drift():
    export = build_export(_bundle(), SOURCE_HEAD, group_cards=[_group_card()])

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

    group_geometry = copy.deepcopy(export)
    group_geometry["group_review"]["cards"][0]["segments"] = []
    with pytest.raises(ValueError, match="geometry/artifact"):
        validate_export(group_geometry)

    group_png = copy.deepcopy(export)
    group_png["group_review"]["cards"][0]["detail"] = "proof.png"
    with pytest.raises(ValueError, match="PNG reference"):
        validate_export(group_png)


def test_export_rejects_nonbaseline_mode_claim():
    export = build_export(_bundle(), SOURCE_HEAD, group_cards=[_group_card()])
    export["source"]["run_mode"] = ReviewRunMode.FULLEST_SAFE_REVIEW.value
    with pytest.raises(ValueError, match="default_baseline"):
        validate_export(export)


def test_group_review_section_is_strict_and_separate():
    export = build_export(_bundle(), SOURCE_HEAD, group_cards=[_group_card()])
    group = export["group_review"]
    card = group["cards"][0]

    assert sorted(member["bore_id"] for member in card["members"]) == [
        "log32",
        "log8",
    ]
    assert card["shared_origin"] == "NEXTLINK@378,409"
    assert sorted(card["boundaries"]) == ["1+76", "1+77"]
    assert all(
        member["per_bore_status"] == "STRUCTURE_IDENTITY_BINDING_REQUIRED"
        for member in card["members"]
    )
    assert "log42" not in str(group)

    extra = copy.deepcopy(export)
    extra["group_review"]["cards"][0]["placement"] = True
    with pytest.raises(ValueError, match="fields drift"):
        validate_export(extra)

    missing = copy.deepcopy(export)
    del missing["group_review"]
    with pytest.raises(ValueError, match="group_review"):
        validate_export(missing)
