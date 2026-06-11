r"""M8.15 -- DESIGN-STROKE reviewer cards (the lane->reviewer payload bridge).

Maps ``symbol_conduit_matchline`` lane outcomes into reviewer-ready card
records. A SEPARATE contract from the banked M8.10 lanes (schema
``truelinev2-reviewer-lanes-1`` stays untouched -- its version pins, closed
lane/action table, and bundle validators are never widened): design-stroke
cards carry what the M8.10 payloads deliberately do not -- the GRADED stroke
GEOMETRY (verbatim from the lane, never invented, never mutated) plus the
component evidence chain and the visual-artifact reference names.

Doctrine preserved (validator-enforced, not advisory):
  * REVIEW-only: no card kind, field, or value can claim AUTO.
  * DESIGN_STROKE_REVIEW cards exist ONLY for lane-eligible bores: segments
    required (>= 2 points each), the design_path TRACED component must be in
    the evidence chain, and the grade provenance is a closed class
    (PASS_ACCEPTED only when the injected accepted-grades record says so;
    UNGRADED otherwise -- a card can never claim a grade nobody gave).
  * DESIGN_PICK_CARD cards are SUGGESTIONS: the label is the SAME frozen
    ``SUGGESTION_NOT_PLACEMENT`` literal (imported, never restated), stroke
    geometry is FORBIDDEN on them (a suggestion can never masquerade as a
    placed stroke), and the named missing artifact rides along.
  * No numeric confidence anywhere (closed classes only, house law).
  * The builder is pure: lane outcomes are read, never written; cards are
    frozen models.

The bridge is UNWIRED: nothing in match/, the engine, or ReviewerBundleService
imports this module -- consumption is proof-runner-only until activation is
authorized.
"""
from __future__ import annotations

from typing import Dict, List, Mapping, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, model_validator

from truelinev2.match.symbol_conduit_lane import (
    LANE_NAME,
    S_ELIGIBLE,
    S_PICK,
    LaneOutcome,
)
from truelinev2.review.reviewer_payloads import SUGGESTION_LABEL

CARD_SCHEMA_VERSION = "truelinev2-design-stroke-card-1"
CARD_MODE = "REVIEW_ONLY"

KIND_STROKE = "DESIGN_STROKE_REVIEW"
KIND_PICK = "DESIGN_PICK_CARD"
CARD_KINDS = (KIND_STROKE, KIND_PICK)

GRADE_ACCEPTED = "PASS_ACCEPTED"   # the owner's banked design-path PASS
GRADE_UNGRADED = "UNGRADED"        # lane-eligible, no banked grade yet
GRADE_CLASSES = (GRADE_ACCEPTED, GRADE_UNGRADED)

NOT_CARDABLE = "NOT_CARDABLE"      # typed refusal for non-card lane statuses


def artifact_ref(bore_id: str, sheet: int) -> str:
    """The lane sweep's stroke-PNG naming convention, as a reference NAME
    (cards reference artifacts; they never embed binaries)."""
    return f"{bore_id}_lane_s{int(sheet)}_redline_stroke.png"


class CardSegment(BaseModel):
    """One stroke segment, VERBATIM from the lane (same rounding, same
    order). Geometry is carried, never created or edited here."""
    model_config = ConfigDict(frozen=True)
    sheet: int
    start_ft: float
    end_ft: float
    stroke_points: Tuple[Tuple[float, float], ...] = Field(min_length=2)


class EvidenceLink(BaseModel):
    """One lane evidence-chain entry, carried verbatim."""
    model_config = ConfigDict(frozen=True)
    component: str
    result: str
    detail: str
    law: str
    configured_by: str


class DesignStrokeCard(BaseModel):
    """One reviewer card. REVIEW-only by construction; suggestion cards can
    never carry stroke geometry; stroke cards can never claim an ungiven
    grade."""
    model_config = ConfigDict(frozen=True)
    card_schema_version: str = CARD_SCHEMA_VERSION
    mode: str = CARD_MODE
    lane: str = LANE_NAME
    bore_id: str
    kind: str
    lane_status: str
    design_grade: Optional[str] = None
    segments: Tuple[CardSegment, ...] = ()
    artifact_refs: Tuple[str, ...] = ()
    evidence_chain: Tuple[EvidenceLink, ...] = Field(min_length=1)
    suggestion_label: Optional[str] = None
    pick_candidate: Optional[str] = None
    pick_candidate_xy: Optional[Tuple[float, float]] = None
    end_anchor_xy: Optional[Tuple[float, float]] = None
    named_missing: Optional[str] = None

    @model_validator(mode="after")
    def _card_contract(self) -> "DesignStrokeCard":
        if self.card_schema_version != CARD_SCHEMA_VERSION:
            raise ValueError("card schema version is pinned")
        if self.mode != CARD_MODE or "AUTO" in self.kind or "AUTO" in self.lane_status:
            raise ValueError("design-stroke cards are REVIEW-only; AUTO can "
                             "never be claimed")
        if self.kind == KIND_STROKE:
            if not self.segments:
                raise ValueError("a stroke card without stroke segments is a "
                                 "fake placement")
            if self.design_grade not in GRADE_CLASSES:
                raise ValueError("design_grade must be a closed class "
                                 f"{GRADE_CLASSES}")
            if not any(e.component == "design_path" and e.result == "TRACED"
                       for e in self.evidence_chain):
                raise ValueError("a stroke card requires the design_path "
                                 "TRACED evidence component")
            if self.lane_status != S_ELIGIBLE:
                raise ValueError("stroke cards exist only for lane-eligible "
                                 "outcomes")
            if len(self.artifact_refs) != len(self.segments):
                raise ValueError("one artifact reference per stroke segment")
        elif self.kind == KIND_PICK:
            if self.segments or self.artifact_refs:
                raise ValueError("a suggestion card can NEVER carry stroke "
                                 "geometry or stroke artifacts -- suggestions "
                                 "do not masquerade as placements")
            if self.suggestion_label != SUGGESTION_LABEL:
                raise ValueError("the suggestion label is frozen")
            if not (self.pick_candidate and self.end_anchor_xy
                    and self.named_missing):
                raise ValueError("a pick card requires its candidate, the "
                                 "bound end anchor, and the named missing "
                                 "artifact")
            if self.design_grade is not None:
                raise ValueError("suggestions carry no design grade")
        else:
            raise ValueError(f"unknown card kind {self.kind!r}")
        return self


class DesignStrokeCardPacket(BaseModel):
    """The card packet: counts recomputed, duplicates rejected, grade
    provenance carried as data (who accepted what), schema pinned."""
    model_config = ConfigDict(frozen=True)
    packet_schema_version: str = CARD_SCHEMA_VERSION
    lane: str = LANE_NAME
    mode: str = CARD_MODE
    kind_counts: Dict[str, int]
    accepted_grades: Dict[str, str]
    cards: Tuple[DesignStrokeCard, ...]

    @model_validator(mode="after")
    def _packet_contract(self) -> "DesignStrokeCardPacket":
        ids = [c.bore_id for c in self.cards]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate bore_id in card packet")
        recount: Dict[str, int] = {}
        for c in self.cards:
            recount[c.kind] = recount.get(c.kind, 0) + 1
        if recount != self.kind_counts:
            raise ValueError(f"kind_counts drift: declared {self.kind_counts} "
                             f"recomputed {recount}")
        for c in self.cards:
            if c.kind == KIND_STROKE and c.design_grade == GRADE_ACCEPTED \
                    and self.accepted_grades.get(c.bore_id) != "PASS":
                raise ValueError(f"{c.bore_id} claims an accepted grade the "
                                 f"provenance record does not carry")
        return self


def card_from_outcome(outcome: LaneOutcome,
                      accepted_grades: Mapping[str, str]):
    """LaneOutcome -> (DesignStrokeCard | None, refusal). PURE: reads the
    outcome, never writes it; geometry and evidence are carried VERBATIM.
    Non-card statuses refuse typed (their reviewer surfacing is the all-58
    integration, a separate authorized step)."""
    evidence = tuple(EvidenceLink(**e.to_dict()) for e in outcome.evidence)
    if outcome.status == S_ELIGIBLE and outcome.segments:
        grade = (GRADE_ACCEPTED
                 if accepted_grades.get(outcome.bore_id) == "PASS"
                 else GRADE_UNGRADED)
        segs = tuple(CardSegment(
            sheet=s.sheet, start_ft=s.start_ft, end_ft=s.end_ft,
            stroke_points=tuple((round(x, 1), round(y, 1))
                                for x, y in s.stroke_points))
            for s in outcome.segments)
        return DesignStrokeCard(
            bore_id=outcome.bore_id, kind=KIND_STROKE,
            lane_status=outcome.status, design_grade=grade, segments=segs,
            artifact_refs=tuple(artifact_ref(outcome.bore_id, s.sheet)
                                for s in outcome.segments),
            evidence_chain=evidence), None
    if outcome.status == S_PICK:
        cand_xy = outcome.detail.get("candidate_xy")
        anchor = outcome.detail.get("end_anchor")
        return DesignStrokeCard(
            bore_id=outcome.bore_id, kind=KIND_PICK,
            lane_status=outcome.status,
            suggestion_label=SUGGESTION_LABEL,
            pick_candidate=outcome.detail.get("candidate"),
            pick_candidate_xy=tuple(cand_xy) if cand_xy else None,
            end_anchor_xy=tuple(anchor) if anchor else None,
            named_missing=outcome.named_missing,
            evidence_chain=evidence), None
    return None, (f"{NOT_CARDABLE}: lane status {outcome.status!r} has no "
                  f"design-stroke card kind -- its reviewer surfacing belongs "
                  f"to the all-58 integration step (not yet authorized)")


def build_card_packet(outcomes, accepted_grades: Mapping[str, str]
                      ) -> Tuple[DesignStrokeCardPacket, List[str]]:
    """Cards for every cardable outcome + typed refusals for the rest."""
    cards: List[DesignStrokeCard] = []
    refusals: List[str] = []
    for out in outcomes:
        card, refusal = card_from_outcome(out, accepted_grades)
        if card is not None:
            cards.append(card)
        else:
            refusals.append(f"{out.bore_id}: {refusal}")
    counts: Dict[str, int] = {}
    for c in cards:
        counts[c.kind] = counts.get(c.kind, 0) + 1
    packet = DesignStrokeCardPacket(
        kind_counts=counts, accepted_grades=dict(accepted_grades),
        cards=tuple(cards))
    return packet, refusals
