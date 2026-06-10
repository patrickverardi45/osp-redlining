r"""M8.10 -- reviewer-output contract for every product lane (contract/proof only).

Product doctrine (Patrick, 2026-06-10): the app does not need 100% auto-placement.
Every bore reaches the reviewer in exactly one LANE, each with a defined payload
shape and a defined human action:

  PLACED_REVIEW                  -- auto/REVIEW placements: approve / reject / edit
  PICK_CARD_ROUTE_SUGGESTION     -- labeled candidate routes: pick one / reject all / draw
  HUMAN_ADJUSTABLE_LENGTH_REDLINE-- footage-certain draggable redline: drag/snap/confirm
  OUT_OF_CLASS                   -- a different named solver owns it next
  SOURCE_REVIEW_REQUIRED         -- the bore log's own data needs fixing first
  UNSAFE_ABSTAIN                 -- no safe lane; the named missing relationship stands

Confirmed PDF redlines become SOURCE TRUTH; KMZ renders only after confirmation.

Contract rules enforced BY THE MODELS (pydantic validation is the contract):
  * suggestions are never placements -- every candidate carries the literal
    SUGGESTION_NOT_PLACEMENT label, frozen;
  * no numeric confidence anywhere -- confidence is a closed CLASS enum;
  * no invented geometry -- evidence is text/station math already proven by the
    engine and the M8.5-M8.9 solvers;
  * lane-specific required fields fail validation if absent (a pick-card without
    candidates, an adjustable lane without a redline spec, etc.).
No engine wiring, no UI, no backend/web/main."""
from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator

SCHEMA_VERSION = "truelinev2-reviewer-lanes-1"
SUGGESTION_LABEL = "SUGGESTION_NOT_PLACEMENT"


class ReviewerLane(str, Enum):
    PLACED_REVIEW = "PLACED_REVIEW"
    PICK_CARD_ROUTE_SUGGESTION = "PICK_CARD_ROUTE_SUGGESTION"
    HUMAN_ADJUSTABLE_LENGTH_REDLINE = "HUMAN_ADJUSTABLE_LENGTH_REDLINE"
    OUT_OF_CLASS = "OUT_OF_CLASS"
    SOURCE_REVIEW_REQUIRED = "SOURCE_REVIEW_REQUIRED"
    UNSAFE_ABSTAIN = "UNSAFE_ABSTAIN"


class ConfidenceClass(str, Enum):
    """Closed confidence CLASSES -- deliberately no numeric score exists in this
    contract (a fake percentage invites fake trust)."""
    AUTO_EXACT_MATCH = "AUTO_EXACT_MATCH"          # engine AUTO_SELECT
    REVIEW_CAVEATED = "REVIEW_CAVEATED"            # default-path REVIEW
    REVIEW_OPTIN_SOLVER = "REVIEW_OPTIN_SOLVER"    # M8.5/M8.8-class opt-in REVIEW


class HumanAction(str, Enum):
    APPROVE_REJECT_EDIT = "APPROVE_REJECT_EDIT"
    PICK_ONE_REJECT_ALL_OR_DRAW = "PICK_ONE_REJECT_ALL_OR_DRAW"
    DRAG_SNAP_CONFIRM_OR_DRAW = "DRAG_SNAP_CONFIRM_OR_DRAW"
    ROUTE_TO_NAMED_SOLVER = "ROUTE_TO_NAMED_SOLVER"
    FIX_SOURCE_DATA = "FIX_SOURCE_DATA"
    NONE_BLOCKED = "NONE_BLOCKED"


_LANE_ACTION = {
    ReviewerLane.PLACED_REVIEW: HumanAction.APPROVE_REJECT_EDIT,
    ReviewerLane.PICK_CARD_ROUTE_SUGGESTION: HumanAction.PICK_ONE_REJECT_ALL_OR_DRAW,
    ReviewerLane.HUMAN_ADJUSTABLE_LENGTH_REDLINE: HumanAction.DRAG_SNAP_CONFIRM_OR_DRAW,
    ReviewerLane.OUT_OF_CLASS: HumanAction.ROUTE_TO_NAMED_SOLVER,
    ReviewerLane.SOURCE_REVIEW_REQUIRED: HumanAction.FIX_SOURCE_DATA,
    ReviewerLane.UNSAFE_ABSTAIN: HumanAction.NONE_BLOCKED,
}


class RouteCandidate(BaseModel):
    """One pick-card route SUGGESTION -- never a placement."""
    candidate_id: str
    sheets: List[int]
    start_sta: Optional[str] = None
    end_sta: Optional[str] = None
    station_math: str                      # e.g. "31+00 - 693 ft -> 24+07"
    footage_check: str                     # e.g. "chain coverage contains 693 ft span"
    evidence_summary: str
    why_not_auto_placed: str
    missing_relationship_to_promote: str
    label: str = SUGGESTION_LABEL

    @model_validator(mode="after")
    def _label_frozen(self) -> "RouteCandidate":
        if self.label != SUGGESTION_LABEL:
            raise ValueError("candidates are suggestions, never placements")
        return self


class AdjustableRedlineSpec(BaseModel):
    """A reviewer-draggable redline object: the footage is certain, the frame/
    path is not. The reviewer places it; the engine snaps/traces afterward."""
    length_ft: float = Field(gt=0)
    initial_sheet_range: List[int]
    draggable: bool = True
    rotatable: bool = True
    snap_to_path: bool = True
    multi_page: bool = True
    engine_cleanup_after_confirmation: bool = True


class ReviewerPayload(BaseModel):
    """The single per-bore reviewer contract object. Lane-specific requirements
    are VALIDATED, not documented-and-hoped."""
    schema_version: str = SCHEMA_VERSION
    bore_id: str
    lane: ReviewerLane
    human_action: HumanAction
    reason_code: str
    sheets: List[int] = Field(default_factory=list)
    station_start_sta: Optional[str] = None
    station_end_sta: Optional[str] = None
    station_start_ft: Optional[float] = None
    station_end_ft: Optional[float] = None
    footage_ft: Optional[float] = None
    confidence_class: Optional[ConfidenceClass] = None
    evidence_summary: Optional[str] = None
    caveats: List[str] = Field(default_factory=list)
    candidates: List[RouteCandidate] = Field(default_factory=list)
    redline_spec: Optional[AdjustableRedlineSpec] = None
    next_named_solver: Optional[str] = None
    suspect_values: Optional[dict] = None
    named_missing_relationship: Optional[str] = None

    @model_validator(mode="after")
    def _lane_contract(self) -> "ReviewerPayload":
        if self.human_action is not _LANE_ACTION[self.lane]:
            raise ValueError(f"lane {self.lane} requires action {_LANE_ACTION[self.lane]}")
        if self.lane is ReviewerLane.PLACED_REVIEW:
            if self.confidence_class is None:
                raise ValueError("placed lane requires a confidence CLASS")
            if not self.evidence_summary:
                raise ValueError("placed lane requires an evidence summary")
            if self.footage_ft is None or self.station_start_ft is None:
                raise ValueError("placed lane requires stations + footage in feet")
        if self.lane is ReviewerLane.PICK_CARD_ROUTE_SUGGESTION and not self.candidates:
            raise ValueError("pick-card lane requires >= 1 labeled candidate")
        if self.lane is ReviewerLane.HUMAN_ADJUSTABLE_LENGTH_REDLINE:
            if self.redline_spec is None:
                raise ValueError("adjustable lane requires a redline spec")
            if self.named_missing_relationship is None:
                raise ValueError("adjustable lane must say why ownership is not unique")
        if self.lane is ReviewerLane.OUT_OF_CLASS and not self.next_named_solver:
            raise ValueError("out-of-class lane must name the next solver")
        if self.lane is ReviewerLane.SOURCE_REVIEW_REQUIRED and self.suspect_values is None:
            raise ValueError("source-review lane must cite the suspect values")
        if self.lane is ReviewerLane.UNSAFE_ABSTAIN and not self.named_missing_relationship:
            raise ValueError("unsafe lane must carry the named missing relationship")
        if self.lane is not ReviewerLane.PLACED_REVIEW and self.confidence_class is not None:
            raise ValueError("confidence classes exist only for the placed lane")
        return self


# --- builders: engine / M8.9 outputs -> contract payloads ---------------------------

def payload_from_placement(bore, placement) -> ReviewerPayload:
    """PLACED_REVIEW from an engine Placement (AUTO or REVIEW)."""
    conf = (ConfidenceClass.AUTO_EXACT_MATCH if placement.status.value == "AUTO_SELECT"
            else ConfidenceClass.REVIEW_OPTIN_SOLVER
            if placement.reason in ("REVERSE_ENDPOINT_ANCHOR", "STATION_AXIS_INTERVAL_PATH",
                                    "FRAME_TRANSLATED_CONTINUATION")
            else ConfidenceClass.REVIEW_CAVEATED)
    return ReviewerPayload(
        bore_id=bore.bore_id, lane=ReviewerLane.PLACED_REVIEW,
        human_action=HumanAction.APPROVE_REJECT_EDIT,
        reason_code=placement.reason, sheets=list(placement.sheets),
        station_start_sta=bore.station_start, station_end_sta=bore.station_end,
        station_start_ft=bore.station_start_ft, station_end_ft=bore.station_end_ft,
        footage_ft=bore.span_ft, confidence_class=conf,
        evidence_summary="; ".join(c.text for c in placement.matched_callouts) or
                         placement.station_span or "engine placement",
        caveats=list(placement.caveats))


def payload_from_frame_ownership(bore, verdict: dict) -> ReviewerPayload:
    """PICK_CARD / ADJUSTABLE / SOURCE_REVIEW / UNSAFE from an M8.9 verdict."""
    result = verdict["result"]
    common = dict(
        bore_id=bore.bore_id, station_start_sta=bore.station_start,
        station_end_sta=bore.station_end, station_start_ft=bore.station_start_ft,
        station_end_ft=bore.station_end_ft, footage_ft=bore.span_ft,
        named_missing_relationship=verdict.get("named_missing_relationship"))
    if result == "PICK_CARD_ROUTE_SUGGESTION":
        cands = []
        for i, s in enumerate(verdict.get("suggestions", [])):
            cands.append(RouteCandidate(
                candidate_id=f"{bore.bore_id}-frame-s{s['sheet']}-{i}",
                sheets=[s["sheet"]],
                station_math=(f"{bore.station_end} - {bore.span_ft} ft -> "
                              f"{bore.station_start}"),
                footage_check=(f"frame cluster {s['cluster']} walk_complete="
                               f"{s['walk_complete']} reached={s.get('reached_ft')}"),
                evidence_summary="; ".join(s.get("chain", [])) or "frame candidate",
                why_not_auto_placed=verdict.get("named_missing_relationship", ""),
                missing_relationship_to_promote=verdict.get(
                    "named_missing_relationship", "frame ownership evidence")))
        return ReviewerPayload(
            lane=ReviewerLane.PICK_CARD_ROUTE_SUGGESTION,
            human_action=HumanAction.PICK_ONE_REJECT_ALL_OR_DRAW,
            reason_code="FRAME_OWNERSHIP_NOT_UNIQUE", candidates=cands,
            sheets=sorted({sh for c in cands for sh in c.sheets}), **common)
    if result == "HUMAN_ADJUSTABLE_LENGTH_REDLINE":
        ro = verdict.get("redline_object", {})
        return ReviewerPayload(
            lane=ReviewerLane.HUMAN_ADJUSTABLE_LENGTH_REDLINE,
            human_action=HumanAction.DRAG_SNAP_CONFIRM_OR_DRAW,
            reason_code="FOOTAGE_CERTAIN_FRAME_NOT_UNIQUE",
            sheets=list(ro.get("likely_sheet_range", [])),
            redline_spec=AdjustableRedlineSpec(
                length_ft=ro.get("footage_ft", bore.span_ft),
                initial_sheet_range=list(ro.get("likely_sheet_range",
                                                bore.sheet_refs))), **common)
    if result == "SOURCE_REVIEW_REQUIRED":
        return ReviewerPayload(
            lane=ReviewerLane.SOURCE_REVIEW_REQUIRED,
            human_action=HumanAction.FIX_SOURCE_DATA,
            reason_code="BORE_LOG_VALUES_INCONSISTENT",
            suspect_values=verdict.get("suspect_values", {}), **common)
    return ReviewerPayload(
        lane=ReviewerLane.UNSAFE_ABSTAIN, human_action=HumanAction.NONE_BLOCKED,
        reason_code="NO_UNIQUE_FRAME_OWNERSHIP", **common)


def payload_out_of_class(bore, m87_verdict: str, next_solver: str,
                         named: Optional[str] = None) -> ReviewerPayload:
    return ReviewerPayload(
        bore_id=bore.bore_id, lane=ReviewerLane.OUT_OF_CLASS,
        human_action=HumanAction.ROUTE_TO_NAMED_SOLVER,
        reason_code=f"M87_{m87_verdict}",
        # M8.12.b: the bore's own referenced sheets ARE known here -- carry them
        # so the routed solver / reviewer UI knows where to look (was []).
        sheets=list(bore.sheet_refs),
        station_start_sta=bore.station_start, station_end_sta=bore.station_end,
        station_start_ft=bore.station_start_ft, station_end_ft=bore.station_end_ft,
        footage_ft=bore.span_ft, next_named_solver=next_solver,
        named_missing_relationship=named)


def payload_source_error(bore_id: str, error: str) -> ReviewerPayload:
    """SOURCE_REVIEW for ingest-error logs (no parseable stations)."""
    return ReviewerPayload(
        bore_id=bore_id, lane=ReviewerLane.SOURCE_REVIEW_REQUIRED,
        human_action=HumanAction.FIX_SOURCE_DATA,
        reason_code="INGEST_ERROR",
        suspect_values={"error": error,
                        "fix": "adapter station-format fix or source correction"},
        named_missing_relationship="bore log has no parseable stations")
