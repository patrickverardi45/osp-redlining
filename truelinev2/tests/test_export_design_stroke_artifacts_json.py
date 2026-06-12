"""Offline contract tests for the refs-only design-stroke artifact export."""
from __future__ import annotations

import copy

import pytest

from truelinev2.match.symbol_conduit_lane import LANE_NAME, S_ELIGIBLE
from truelinev2.proof.export_design_stroke_artifacts_json import (
    EXPORT_SCHEMA_VERSION,
    build_export,
    validate_export,
)
from truelinev2.review.design_stroke_cards import (
    GRADE_ACCEPTED,
    GRADE_UNGRADED,
    KIND_STROKE,
    CardSegment,
    DesignStrokeCard,
    DesignStrokeCardPacket,
    EvidenceLink,
)

SOURCE_HEAD = "667ccb78dd2bd80b5f97910b44a7e124898ff110"


def _card(
    bore_id: str,
    grade: str = GRADE_ACCEPTED,
    sheets: tuple[int, ...] = (8,),
) -> DesignStrokeCard:
    segments = tuple(
        CardSegment(
            sheet=sheet,
            start_ft=100.0,
            end_ft=200.0,
            stroke_points=((1.0, 2.0), (3.0, 4.0)),
        )
        for sheet in sheets
    )
    return DesignStrokeCard(
        bore_id=bore_id,
        kind=KIND_STROKE,
        lane_status=S_ELIGIBLE,
        design_grade=grade,
        segments=segments,
        artifact_refs=tuple(
            f"{bore_id}_lane_s{sheet}_redline_stroke.png" for sheet in sheets
        ),
        evidence_chain=(
            EvidenceLink(
                component="design_path",
                result="TRACED",
                detail="synthetic",
                law="test law",
                configured_by="test",
            ),
        ),
    )


def _packet() -> DesignStrokeCardPacket:
    accepted = _card("log51")
    ungraded = _card("log99", grade=GRADE_UNGRADED)
    return DesignStrokeCardPacket(
        kind_counts={KIND_STROKE: 2},
        accepted_grades={"log51": "PASS"},
        cards=(accepted, ungraded),
    )


def test_export_contains_only_graded_pass_artifact_references():
    export = build_export(_packet(), SOURCE_HEAD)

    assert export == {
        "export_schema_version": EXPORT_SCHEMA_VERSION,
        "source": {
            "engine": "truelinev2",
            "source_git_head": SOURCE_HEAD,
            "card_contract": "truelinev2-design-stroke-card-1",
            "lane": LANE_NAME,
            "served": False,
        },
        "artifacts": [
            {
                "source_bore_id": "log51",
                "lane_status": S_ELIGIBLE,
                "design_grade": GRADE_ACCEPTED,
                "sheets": [8],
                "artifact_refs": ["log51_lane_s8_redline_stroke.png"],
            }
        ],
    }
    assert "segments" not in str(export)
    assert "stroke_points" not in str(export)


def test_export_preserves_sheet_to_filename_pairing():
    card = _card("log65", sheets=(10, 9))
    packet = DesignStrokeCardPacket(
        kind_counts={KIND_STROKE: 1},
        accepted_grades={"log65": "PASS"},
        cards=(card,),
    )

    row = build_export(packet, SOURCE_HEAD)["artifacts"][0]

    assert row["sheets"] == [10, 9]
    assert row["artifact_refs"] == [
        "log65_lane_s10_redline_stroke.png",
        "log65_lane_s9_redline_stroke.png",
    ]


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda export: export["artifacts"][0].update(
                {"segments": [{"stroke_points": [[1, 2], [3, 4]]}]}
            ),
            "artifact fields drift",
        ),
        (
            lambda export: export["artifacts"][0]["artifact_refs"].__setitem__(
                0, "../log51.png"
            ),
            "bare filename",
        ),
        (
            lambda export: export["artifacts"][0]["artifact_refs"].__setitem__(
                0, r"C:\proof\log51.png"
            ),
            "bare filename",
        ),
        (
            lambda export: export["artifacts"][0]["artifact_refs"].__setitem__(
                0, "https://example.test/log51.png"
            ),
            "bare filename",
        ),
        (
            lambda export: export["source"].update({"served": True}),
            "must not be served",
        ),
    ],
)
def test_export_rejects_geometry_paths_urls_and_serving(mutation, message):
    export = build_export(_packet(), SOURCE_HEAD)
    mutation(export)

    with pytest.raises(ValueError, match=message):
        validate_export(export)


def test_export_rejects_binary_payload_and_non_pass_rows():
    export = build_export(_packet(), SOURCE_HEAD)

    binary = copy.deepcopy(export)
    binary["artifacts"][0]["artifact_refs"][0] = b"\x89PNG"
    with pytest.raises(ValueError, match="bare filename"):
        validate_export(binary)

    ungraded = copy.deepcopy(export)
    ungraded["artifacts"][0]["design_grade"] = GRADE_UNGRADED
    with pytest.raises(ValueError, match="only graded-PASS"):
        validate_export(ungraded)
