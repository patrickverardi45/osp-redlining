r"""M8.20 section 7 -- GROUP review contract for a PROVEN SHARED_ALIGNMENT_MULTI_DROP.

A standalone, schema-versioned review surface. It is NOT the per-bore M8.10/
M8.11 reviewer contracts and is NOT wired into ``resolve_bore`` / the sweep /
the reviewer service -- so no per-bore status, census, card count, or contract
changes. It lets a reviewer see a proven Law-1 multi-drop (``match.shared_alignment``)
as ONE group item -- N bores sharing one origin -- without corrupting per-bore
placement truth:

  * REVIEW-only by construction (there is no AUTO branch); the only label is
    ``SUGGESTION_NOT_PLACEMENT``; the group action is to CONFIRM/REJECT the
    grouping, never to place;
  * the card carries NO geometry and NO strokes (no such fields exist, and the
    validator forbids any geometry key) -- a proven shared alignment is not a
    drawn redline;
  * every member carries its UNCHANGED per-bore blocked status verbatim, so the
    card can never overwrite per-bore truth: the bores stay blocked per-bore
    until a human confirms the group;
  * only a ``V_REVIEW`` Law-1 verdict can build a card (REJECTED / NOT_APPLICABLE
    -> no card); a bore with no survivor (e.g. log42) never produces a claim and
    so can never become a member.

Validation IS the contract (pydantic, fail-closed). No engine wiring, no UI, no
geometry, no rendering.
"""
from __future__ import annotations

from typing import Mapping, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, Field, model_validator

from truelinev2.match.shared_alignment import (
    LAW_NAME,
    MODE,
    SUGGESTION_LABEL,
    V_REVIEW,
    BoreClaim,
)

GROUP_SCHEMA_VERSION = "truelinev2-shared-alignment-group-review-1"
GROUP_LANE = V_REVIEW                       # "SHARED_ALIGNMENT_MULTI_DROP_REVIEW"
GROUP_HUMAN_ACTION = "CONFIRM_OR_REJECT_MULTI_DROP_GROUPING"
# A member's per-bore truth MUST remain this blocked status -- never overwritten.
MEMBER_BLOCKED_STATUS = "STRUCTURE_IDENTITY_BINDING_REQUIRED"
# Geometry / stroke keys that may NEVER appear anywhere in a group card.
_FORBIDDEN_GEOMETRY = ("segments", "stroke_points", "stroke_rgb", "walk_points",
                       "boundary_xy")


def _assert_no_geometry(value, path: str = "$") -> None:
    """Walk the serialized card; any geometry/stroke key fails closed."""
    if isinstance(value, dict):
        for key, child in value.items():
            if key in _FORBIDDEN_GEOMETRY:
                raise ValueError(f"geometry/stroke key {key!r} at {path}")
            _assert_no_geometry(child, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _assert_no_geometry(child, f"{path}[{index}]")


class GroupMember(BaseModel):
    """One bore in the group: its printed-run identity evidence (boundary +
    chain) and its UNCHANGED per-bore blocked status. Never geometry, never a
    placement."""
    model_config = ConfigDict(frozen=True)
    bore_id: str
    boundary_raw: str                                    # this run's matchline station
    per_bore_status: str                                 # the bore's UNCHANGED blocked status
    chain_hops: Tuple[Tuple[str, str, float], ...] = Field(min_length=1)
    conduit_evidence_count: int = Field(ge=1)
    origin_multiport: bool

    @model_validator(mode="after")
    def _member_contract(self) -> "GroupMember":
        if self.per_bore_status != MEMBER_BLOCKED_STATUS:
            raise ValueError(
                "a group member's per-bore status MUST stay the blocked "
                f"{MEMBER_BLOCKED_STATUS} -- the group card never overwrites "
                "per-bore truth")
        if not self.origin_multiport:
            raise ValueError("a member must print a multi-port-capable origin class")
        return self


class SharedAlignmentGroupCard(BaseModel):
    """A proven shared-alignment multi-drop, surfaced as ONE REVIEW group item."""
    model_config = ConfigDict(frozen=True)
    schema_version: str = GROUP_SCHEMA_VERSION
    group_lane: str = GROUP_LANE
    law: str = LAW_NAME
    mode: str = MODE
    review_only: bool = True
    auto: bool = False
    has_geometry: bool = False
    has_strokes: bool = False
    label: str = SUGGESTION_LABEL
    human_action: str = GROUP_HUMAN_ACTION
    shared_origin: str
    boundaries: Tuple[str, ...] = Field(min_length=2)
    members: Tuple[GroupMember, ...] = Field(min_length=2)
    detail: str

    @model_validator(mode="after")
    def _group_contract(self) -> "SharedAlignmentGroupCard":
        if self.schema_version != GROUP_SCHEMA_VERSION:
            raise ValueError("group schema version is pinned")
        if self.group_lane != GROUP_LANE or self.law != LAW_NAME:
            raise ValueError("group lane / law are pinned")
        if (self.mode != MODE or self.review_only is not True
                or self.auto is not False):
            raise ValueError("the group card is REVIEW-only; AUTO can never be "
                             "claimed")
        if self.has_geometry or self.has_strokes:
            raise ValueError("a shared-alignment group card carries NO geometry "
                             "and NO strokes")
        if self.label != SUGGESTION_LABEL:
            raise ValueError("the suggestion label is frozen")
        if self.human_action != GROUP_HUMAN_ACTION:
            raise ValueError("the group action confirms/rejects the GROUPING, "
                             "never places")
        if not self.shared_origin:
            raise ValueError("the shared origin structure must be named")
        ids = [m.bore_id for m in self.members]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate bore in the group")
        member_boundaries = sorted(m.boundary_raw for m in self.members)
        if len(set(member_boundaries)) != len(member_boundaries):
            raise ValueError("two members claim the same boundary -- not "
                             "distinct printed runs")
        if sorted(self.boundaries) != member_boundaries:
            raise ValueError("the card boundaries must be exactly the members' "
                             "distinct boundary stations (claim bijection)")
        _assert_no_geometry(self.model_dump())
        return self


def build_group_review_card(
        verdict: Mapping, claims: Sequence[BoreClaim],
        per_bore_statuses: Mapping[str, str]
) -> Optional[SharedAlignmentGroupCard]:
    """Consume a Law-1 verdict + its claims + the live per-bore statuses -> a
    group card, or ``None``.

    ONLY a ``V_REVIEW`` verdict yields a card; a ``REJECTED`` / ``NOT_APPLICABLE``
    verdict returns ``None`` so a non-proven group is never surfaced. PURE: it
    reads the proof outputs, never re-runs the lane, never writes engine state.
    The per-bore statuses are carried VERBATIM (the member validator refuses any
    status that is not the blocked one -- the card cannot overwrite per-bore
    truth even if mis-fed).
    """
    if verdict.get("verdict") != V_REVIEW:
        return None
    by_id = {c.bore_id: c for c in claims}
    if sorted(by_id) != sorted(verdict["bores"]):
        raise ValueError("verdict bores and supplied claims disagree")
    members = tuple(
        GroupMember(
            bore_id=c.bore_id,
            boundary_raw=c.boundary_raw,
            per_bore_status=per_bore_statuses[c.bore_id],
            chain_hops=c.chain_hops,
            conduit_evidence_count=c.conduit_count,
            origin_multiport=c.origin_multiport)
        for c in sorted(by_id.values(), key=lambda c: c.bore_id))
    return SharedAlignmentGroupCard(
        shared_origin=verdict["shared_origin"],
        boundaries=tuple(sorted(verdict["boundaries"])),
        members=members,
        detail=verdict["detail"])
