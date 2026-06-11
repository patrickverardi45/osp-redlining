"""M8.15 -- tests pinning the design-stroke card bridge (synthetic; no PDF).

Locks: stroke cards require segments + the design_path TRACED evidence and a
closed grade class backed by provenance; suggestion cards carry the frozen
SUGGESTION_NOT_PLACEMENT label and can NEVER carry stroke geometry (the
masquerade test); no card can claim AUTO; packets recompute counts, reject
duplicates, and reject unbacked accepted-grade claims; the builder is pure
(outcomes never mutated); artifact refs follow the lane sweep naming; the
M8.10/M8.11 contracts are untouched (schema strings distinct)."""
from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from truelinev2.match.symbol_conduit_lane import (
    ComponentReport,
    LaneOutcome,
    S_CROSS_SHEET,
    S_ELIGIBLE,
    S_PICK,
    StrokeSegment,
)
from truelinev2.review.design_stroke_cards import (
    CARD_SCHEMA_VERSION,
    GRADE_ACCEPTED,
    GRADE_UNGRADED,
    KIND_PICK,
    KIND_STROKE,
    DesignStrokeCard,
    DesignStrokeCardPacket,
    artifact_ref,
    build_card_packet,
    card_from_outcome,
)
from truelinev2.review.reviewer_payloads import SCHEMA_VERSION, SUGGESTION_LABEL


def _ev(component="design_path", result="TRACED", detail="design path TRACED"):
    return ComponentReport(component, result, detail)


def _eligible(bid="logA"):
    seg = StrokeSegment(sheet=8, start_ft=0.0, end_ft=299.0,
                        stroke_points=((577.6, 354.2), (436.0, 359.5),
                                       (149.9, 343.3)))
    return LaneOutcome(bore_id=bid, status=S_ELIGIBLE, segments=(seg,),
                       evidence=(_ev("tick_path", "READY", "ok"), _ev()))


def _pick(bid="logB"):
    return LaneOutcome(bore_id=bid, status=S_PICK,
                       evidence=(_ev("conduit_origin", "REFUSED", "span"),),
                       named_missing="span corroboration refused the candidate",
                       detail={"candidate": "SYM@134,352",
                               "candidate_xy": [134.0, 352.0],
                               "end_anchor": [601.9, 351.9]})


def test_eligible_maps_to_accepted_stroke_card_with_provenance():
    card, refusal = card_from_outcome(_eligible(), {"logA": "PASS"})
    assert refusal is None and card.kind == KIND_STROKE
    assert card.design_grade == GRADE_ACCEPTED
    assert card.artifact_refs == ("logA_lane_s8_redline_stroke.png",)
    assert card.segments[0].stroke_points[0] == (577.6, 354.2)


def test_ungiven_grade_is_never_claimed():
    card, _ = card_from_outcome(_eligible(), {})
    assert card.design_grade == GRADE_UNGRADED


def test_pick_maps_to_frozen_suggestion_without_geometry():
    card, refusal = card_from_outcome(_pick(), {})
    assert refusal is None and card.kind == KIND_PICK
    assert card.suggestion_label == SUGGESTION_LABEL
    assert card.segments == () and card.artifact_refs == ()
    assert card.pick_candidate and card.end_anchor_xy and card.named_missing


def test_suggestion_card_with_geometry_is_rejected():
    base, _ = card_from_outcome(_pick(), {})
    stroke, _ = card_from_outcome(_eligible(), {"logA": "PASS"})
    with pytest.raises(ValidationError):
        DesignStrokeCard(**{**base.model_dump(),
                            "segments": stroke.model_dump()["segments"]})


def test_stroke_card_requires_traced_evidence_and_segments():
    out = LaneOutcome(bore_id="logC", status=S_ELIGIBLE,
                      segments=_eligible().segments,
                      evidence=(_ev("tick_path", "READY", "ok"),))  # no TRACED
    with pytest.raises(ValidationError):
        card_from_outcome(out, {})
    stroke, _ = card_from_outcome(_eligible(), {})
    with pytest.raises(ValidationError):
        DesignStrokeCard(**{**stroke.model_dump(), "segments": ()})


def test_auto_can_never_be_claimed():
    stroke, _ = card_from_outcome(_eligible(), {})
    with pytest.raises(ValidationError):
        DesignStrokeCard(**{**stroke.model_dump(),
                            "lane_status": "AUTO_SELECT"})


def test_packet_recounts_dedupes_and_rejects_unbacked_claims():
    a, _ = card_from_outcome(_eligible("logA"), {"logA": "PASS"})
    b, _ = card_from_outcome(_pick("logB"), {})
    packet, refusals = build_card_packet(
        [_eligible("logA"), _pick("logB")], {"logA": "PASS"})
    assert packet.kind_counts == {KIND_STROKE: 1, KIND_PICK: 1}
    assert not refusals
    with pytest.raises(ValidationError):  # duplicate bore_id
        DesignStrokeCardPacket(kind_counts={KIND_STROKE: 2},
                               accepted_grades={"logA": "PASS"},
                               cards=(a, a))
    with pytest.raises(ValidationError):  # count drift
        DesignStrokeCardPacket(kind_counts={KIND_STROKE: 5},
                               accepted_grades={"logA": "PASS"}, cards=(a,))
    with pytest.raises(ValidationError):  # accepted claim without provenance
        DesignStrokeCardPacket(kind_counts={KIND_STROKE: 1},
                               accepted_grades={}, cards=(a,))


def test_non_card_statuses_refuse_typed():
    out = LaneOutcome(bore_id="logD", status=S_CROSS_SHEET,
                      evidence=(_ev("matchline_join", "REFUSED", "no eq"),),
                      named_missing="printed matchline equation")
    card, refusal = card_from_outcome(out, {})
    assert card is None and "NOT_CARDABLE" in refusal
    assert "all-58 integration" in refusal


def test_builder_is_pure_outcomes_never_mutated():
    out = _eligible()
    snapshot = json.dumps(out.to_dict(), sort_keys=True)
    card_from_outcome(out, {"logA": "PASS"})
    build_card_packet([out], {"logA": "PASS"})
    assert json.dumps(out.to_dict(), sort_keys=True) == snapshot


def test_schemas_are_distinct_and_pinned():
    assert CARD_SCHEMA_VERSION == "truelinev2-design-stroke-card-1"
    assert CARD_SCHEMA_VERSION != SCHEMA_VERSION  # M8.10 contract untouched
    with pytest.raises(ValidationError):
        stroke, _ = card_from_outcome(_eligible(), {})
        DesignStrokeCard(**{**stroke.model_dump(),
                            "card_schema_version": "something-else"})


def test_artifact_ref_naming_matches_the_lane_sweep():
    assert artifact_ref("log65", 10) == "log65_lane_s10_redline_stroke.png"
