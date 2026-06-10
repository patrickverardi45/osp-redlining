"""M8.10 -- tests pinning the reviewer payload contract (no PDF).

Locks: lane-specific required fields fail validation when absent; suggestions
are frozen as SUGGESTION_NOT_PLACEMENT; no numeric confidence exists anywhere;
lane->human-action mapping is fixed; builders map engine/M8.9 outputs into valid
payloads; the contract serializes to JSON. Contract/proof only -- no engine
import of this package's new module."""
from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from truelinev2.review.reviewer_payloads import (
    SUGGESTION_LABEL,
    AdjustableRedlineSpec,
    ConfidenceClass,
    HumanAction,
    ReviewerLane,
    ReviewerPayload,
    RouteCandidate,
    payload_from_frame_ownership,
    payload_from_placement,
    payload_out_of_class,
    payload_source_error,
)
from truelinev2.schema.models import Bore, Callout, Placement, PlacementStatus
from truelinev2.stations import feet_to_station


def _bore(s=0, e=415, sheets=(10,)):
    return Bore(bore_id="logT", source_file="logT.xlsx", sheet_refs=list(sheets),
                station_start=feet_to_station(s), station_end=feet_to_station(e),
                station_start_ft=s, station_end_ft=e, span_ft=round(e - s, 2))


def _candidate(**over):
    base = dict(candidate_id="logT-frame-s10-0", sheets=[10],
                station_math="4+15 - 415 ft -> 0+00",
                footage_check="coverage contains span",
                evidence_summary="s10 chain", why_not_auto_placed="2 frames",
                missing_relationship_to_promote="structure identity")
    base.update(over)
    return RouteCandidate(**base)


def test_lane_action_mapping_enforced():
    with pytest.raises(ValidationError):
        ReviewerPayload(bore_id="x", lane=ReviewerLane.PICK_CARD_ROUTE_SUGGESTION,
                        human_action=HumanAction.APPROVE_REJECT_EDIT,
                        reason_code="r", candidates=[_candidate()])


def test_pick_card_requires_candidates():
    with pytest.raises(ValidationError):
        ReviewerPayload(bore_id="x", lane=ReviewerLane.PICK_CARD_ROUTE_SUGGESTION,
                        human_action=HumanAction.PICK_ONE_REJECT_ALL_OR_DRAW,
                        reason_code="r")


def test_suggestion_label_is_frozen():
    with pytest.raises(ValidationError):
        _candidate(label="PLACEMENT")
    assert _candidate().label == SUGGESTION_LABEL


def test_placed_lane_requires_confidence_class_and_evidence():
    with pytest.raises(ValidationError):
        ReviewerPayload(bore_id="x", lane=ReviewerLane.PLACED_REVIEW,
                        human_action=HumanAction.APPROVE_REJECT_EDIT,
                        reason_code="r", footage_ft=100, station_start_ft=0)


def test_confidence_class_only_on_placed_lane():
    with pytest.raises(ValidationError):
        ReviewerPayload(bore_id="x", lane=ReviewerLane.OUT_OF_CLASS,
                        human_action=HumanAction.ROUTE_TO_NAMED_SOLVER,
                        reason_code="r", next_named_solver="s",
                        confidence_class=ConfidenceClass.REVIEW_CAVEATED)


def test_no_numeric_confidence_field_exists():
    fields = set(ReviewerPayload.model_fields)
    assert not any("score" in f or "probability" in f for f in fields)
    assert all(isinstance(v.value, str) for v in ConfidenceClass)


def test_adjustable_lane_requires_spec_and_reason():
    with pytest.raises(ValidationError):
        ReviewerPayload(bore_id="x", lane=ReviewerLane.HUMAN_ADJUSTABLE_LENGTH_REDLINE,
                        human_action=HumanAction.DRAG_SNAP_CONFIRM_OR_DRAW,
                        reason_code="r",
                        redline_spec=AdjustableRedlineSpec(
                            length_ft=415, initial_sheet_range=[10]))
    ok = ReviewerPayload(bore_id="x", lane=ReviewerLane.HUMAN_ADJUSTABLE_LENGTH_REDLINE,
                         human_action=HumanAction.DRAG_SNAP_CONFIRM_OR_DRAW,
                         reason_code="r", named_missing_relationship="2 frames",
                         redline_spec=AdjustableRedlineSpec(
                             length_ft=415, initial_sheet_range=[10]))
    assert ok.redline_spec.draggable and ok.redline_spec.snap_to_path
    assert ok.redline_spec.engine_cleanup_after_confirmation


def test_source_review_and_unsafe_requirements():
    with pytest.raises(ValidationError):
        ReviewerPayload(bore_id="x", lane=ReviewerLane.SOURCE_REVIEW_REQUIRED,
                        human_action=HumanAction.FIX_SOURCE_DATA, reason_code="r")
    with pytest.raises(ValidationError):
        ReviewerPayload(bore_id="x", lane=ReviewerLane.UNSAFE_ABSTAIN,
                        human_action=HumanAction.NONE_BLOCKED, reason_code="r")


def test_builder_from_placement_auto_and_optin():
    c = Callout(sheet=10, page=10, from_sta="0+00", to_sta="4+15", from_ft=0,
                to_ft=415, footage=415, text="STA 0+00 TO STA 4+15", dialect="test")
    auto = Placement(bore_id="logT", status=PlacementStatus.AUTO_SELECT,
                     tier="AUTO_SELECT", reason="EXACT_BOX_FOOTAGE_AND_ENDPOINTS",
                     sheets=[10], matched_callouts=[c])
    p = payload_from_placement(_bore(), auto)
    assert p.lane is ReviewerLane.PLACED_REVIEW
    assert p.confidence_class is ConfidenceClass.AUTO_EXACT_MATCH
    optin = auto.model_copy(update={"status": PlacementStatus.REVIEW,
                                    "reason": "STATION_AXIS_INTERVAL_PATH"})
    p2 = payload_from_placement(_bore(), optin)
    assert p2.confidence_class is ConfidenceClass.REVIEW_OPTIN_SOLVER


def test_builder_from_frame_ownership_pick_card():
    verdict = {"result": "PICK_CARD_ROUTE_SUGGESTION",
               "named_missing_relationship": "2 frames support the span",
               "suggestions": [
                   {"sheet": 10, "cluster": (0.0, 450.0), "walk_complete": True,
                    "reached_ft": 0.0, "chain": ["s10 0->200", "s10 200->450"]},
                   {"sheet": 12, "cluster": (0.0, 450.0), "walk_complete": True,
                    "reached_ft": 0.0, "chain": ["s12 0->450"]}]}
    p = payload_from_frame_ownership(_bore(), verdict)
    assert p.lane is ReviewerLane.PICK_CARD_ROUTE_SUGGESTION
    assert len(p.candidates) == 2
    assert all(c.label == SUGGESTION_LABEL for c in p.candidates)
    assert all(c.missing_relationship_to_promote for c in p.candidates)


def test_builder_from_frame_ownership_adjustable():
    verdict = {"result": "HUMAN_ADJUSTABLE_LENGTH_REDLINE",
               "named_missing_relationship": "frames remain plausible",
               "redline_object": {"footage_ft": 415.0,
                                  "likely_sheet_range": [10, 12]}}
    p = payload_from_frame_ownership(_bore(), verdict)
    assert p.lane is ReviewerLane.HUMAN_ADJUSTABLE_LENGTH_REDLINE
    assert p.redline_spec.length_ft == 415.0
    assert p.redline_spec.initial_sheet_range == [10, 12]
    assert p.redline_spec.multi_page is True


def test_builder_out_of_class_and_source_error():
    p = payload_out_of_class(_bore(), "END_STATION_NOT_FOUND", "structure binding")
    assert p.lane is ReviewerLane.OUT_OF_CLASS
    assert p.next_named_solver == "structure binding"
    e = payload_source_error("log37", "ValueError: no parseable stations")
    assert e.lane is ReviewerLane.SOURCE_REVIEW_REQUIRED
    assert e.suspect_values["error"].startswith("ValueError")


def test_payloads_serialize_to_json():
    verdict = {"result": "HUMAN_ADJUSTABLE_LENGTH_REDLINE",
               "named_missing_relationship": "x",
               "redline_object": {"footage_ft": 415.0, "likely_sheet_range": [10]}}
    p = payload_from_frame_ownership(_bore(), verdict)
    round_tripped = json.loads(p.model_dump_json())
    assert round_tripped["lane"] == "HUMAN_ADJUSTABLE_LENGTH_REDLINE"
    assert round_tripped["schema_version"] == "truelinev2-reviewer-lanes-1"


def test_no_engine_wiring():
    import truelinev2.match.engine as eng
    assert not [m for m in dir(eng) if "reviewer" in m.lower() or "payload" in m.lower()]
