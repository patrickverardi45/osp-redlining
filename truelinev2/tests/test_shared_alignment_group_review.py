"""Offline contract tests for the M8.20 section-7 GROUP review card.

Validation IS the contract: a proven SHARED_ALIGNMENT_MULTI_DROP becomes one
REVIEW group item that references its member bores, the shared origin, and the
distinct printed boundaries -- carrying NO geometry, NO AUTO, and every member's
UNCHANGED per-bore blocked status. A non-proven verdict yields no card. The
group module is never wired into the per-bore pipeline.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from truelinev2.match.shared_alignment import (
    LAW_NAME,
    MODE,
    SUGGESTION_LABEL,
    V_NOT_APPLICABLE,
    V_REJECTED,
    V_REVIEW,
    BoreClaim,
)
from truelinev2.review.group_review import (
    GROUP_HUMAN_ACTION,
    GROUP_LANE,
    GROUP_SCHEMA_VERSION,
    MEMBER_BLOCKED_STATUS,
    GroupMember,
    SharedAlignmentGroupCard,
    _assert_no_geometry,
    build_group_review_card,
)

H8 = (("0+00", "1+10", 110.0), ("1+10", "1+76", 66.0))
H32 = (("0+00", "1+30", 130.0), ("1+30", "1+77", 47.0))
STAT = {"log8": MEMBER_BLOCKED_STATUS, "log32": MEMBER_BLOCKED_STATUS}


def _claim(bid: str, boundary: str, hops) -> BoreClaim:
    return BoreClaim(
        bore_id=bid, survivor_id="NEXTLINK@1,1", boundary_raw=boundary,
        chain_unique=True, join_proven=True, chain_hops=hops,
        walk_points=((0.0, 0.0), (1.0, 0.0)), boundary_xy=(1.0, 0.0),
        conduit_count=2, origin_multiport=True)


def _verdict(**kw):
    base = dict(verdict=V_REVIEW, law=LAW_NAME, mode=MODE,
                shared_origin="NEXTLINK@1,1", bores=["log32", "log8"],
                boundaries=["1+76", "1+77"], review_only=True, auto=False,
                label=SUGGESTION_LABEL,
                detail="two distinct printed runs over one drawn alignment")
    base.update(kw)
    return base


def _claims():
    return [_claim("log8", "1+76", H8), _claim("log32", "1+77", H32)]


def _member(bid="log8", boundary="1+76", hops=H8, **kw):
    base = dict(per_bore_status=MEMBER_BLOCKED_STATUS, chain_hops=hops,
                conduit_evidence_count=2, origin_multiport=True)
    base.update(kw)
    return GroupMember(bore_id=bid, boundary_raw=boundary, **base)


def test_proven_verdict_builds_a_review_group_card():
    card = build_group_review_card(_verdict(), _claims(), STAT)
    assert card is not None
    assert card.schema_version == GROUP_SCHEMA_VERSION
    assert card.group_lane == GROUP_LANE == V_REVIEW
    assert card.law == LAW_NAME and card.mode == "REVIEW_ONLY"
    assert card.review_only is True and card.auto is False
    assert card.has_geometry is False and card.has_strokes is False
    assert card.label == SUGGESTION_LABEL
    assert card.human_action == GROUP_HUMAN_ACTION
    assert card.shared_origin == "NEXTLINK@1,1"
    assert sorted(card.boundaries) == ["1+76", "1+77"]
    assert sorted(m.bore_id for m in card.members) == ["log32", "log8"]
    assert all(m.per_bore_status == MEMBER_BLOCKED_STATUS for m in card.members)


def test_non_proven_verdicts_build_no_card():
    for v in (V_REJECTED, V_NOT_APPLICABLE):
        assert build_group_review_card(_verdict(verdict=v), _claims(), STAT) is None


def test_build_rejects_verdict_claim_mismatch():
    with pytest.raises(ValueError, match="disagree"):
        build_group_review_card(_verdict(bores=["log8", "log99"]), _claims(), STAT)


def test_member_status_must_stay_blocked():
    # The card can never carry an overwritten (placed) per-bore status.
    with pytest.raises(ValidationError, match="blocked"):
        _member(per_bore_status="STROKE_ELIGIBLE_REVIEW")
    with pytest.raises(ValueError, match="blocked"):
        build_group_review_card(
            _verdict(), _claims(),
            {"log8": "STROKE_ELIGIBLE_REVIEW", "log32": MEMBER_BLOCKED_STATUS})


def test_card_is_review_only_no_auto():
    with pytest.raises(ValidationError, match="AUTO can never be claimed"):
        SharedAlignmentGroupCard(
            shared_origin="X@1,1", boundaries=("1+76", "1+77"),
            members=(_member("log8", "1+76", H8), _member("log32", "1+77", H32)),
            detail="d", auto=True)
    with pytest.raises(ValidationError, match="AUTO can never be claimed"):
        SharedAlignmentGroupCard(
            shared_origin="X@1,1", boundaries=("1+76", "1+77"),
            members=(_member("log8", "1+76", H8), _member("log32", "1+77", H32)),
            detail="d", review_only=False)


def test_card_carries_no_geometry_or_strokes():
    for flag in ("has_geometry", "has_strokes"):
        with pytest.raises(ValidationError, match="NO geometry"):
            SharedAlignmentGroupCard(
                shared_origin="X@1,1", boundaries=("1+76", "1+77"),
                members=(_member("log8", "1+76", H8),
                         _member("log32", "1+77", H32)),
                detail="d", **{flag: True})
    # The geometry walker rejects any smuggled geometry key.
    with pytest.raises(ValueError, match="geometry/stroke key"):
        _assert_no_geometry({"members": [{"stroke_points": [[1, 2]]}]})
    with pytest.raises(ValueError, match="geometry/stroke key"):
        _assert_no_geometry({"segments": []})


def test_frozen_label_action_and_schema():
    with pytest.raises(ValidationError, match="suggestion label is frozen"):
        SharedAlignmentGroupCard(
            shared_origin="X@1,1", boundaries=("1+76", "1+77"),
            members=(_member("log8", "1+76", H8), _member("log32", "1+77", H32)),
            detail="d", label="PLACEMENT")
    with pytest.raises(ValidationError, match="confirms/rejects the GROUPING"):
        SharedAlignmentGroupCard(
            shared_origin="X@1,1", boundaries=("1+76", "1+77"),
            members=(_member("log8", "1+76", H8), _member("log32", "1+77", H32)),
            detail="d", human_action="PLACE")
    with pytest.raises(ValidationError, match="schema version is pinned"):
        SharedAlignmentGroupCard(
            shared_origin="X@1,1", boundaries=("1+76", "1+77"),
            members=(_member("log8", "1+76", H8), _member("log32", "1+77", H32)),
            detail="d", schema_version="other-1")


def test_group_requires_at_least_two_distinct_members_and_boundaries():
    with pytest.raises(ValidationError):  # min_length=2 on members + boundaries
        SharedAlignmentGroupCard(
            shared_origin="X@1,1", boundaries=("1+76",),
            members=(_member("log8", "1+76", H8),), detail="d")
    # duplicate bore
    with pytest.raises(ValidationError, match="duplicate bore"):
        SharedAlignmentGroupCard(
            shared_origin="X@1,1", boundaries=("1+76", "1+77"),
            members=(_member("log8", "1+76", H8), _member("log8", "1+77", H32)),
            detail="d")
    # two members claiming the same boundary -> not distinct printed runs
    with pytest.raises(ValidationError, match="distinct printed runs"):
        SharedAlignmentGroupCard(
            shared_origin="X@1,1", boundaries=("1+76", "1+76"),
            members=(_member("log8", "1+76", H8), _member("log32", "1+76", H32)),
            detail="d")


def test_card_boundaries_must_equal_member_boundaries_bijection():
    with pytest.raises(ValidationError, match="claim bijection"):
        SharedAlignmentGroupCard(
            shared_origin="X@1,1", boundaries=("1+76", "9+99"),
            members=(_member("log8", "1+76", H8), _member("log32", "1+77", H32)),
            detail="d")


def test_group_module_not_wired_into_per_bore_pipeline():
    pkg = Path(__file__).resolve().parents[1]
    for rel in ("match/symbol_conduit_lane.py",
                "proof/run_symbol_conduit_lane_sweep.py",
                "review/reviewer_service.py",
                "review/reviewer_payloads.py",
                "review/design_stroke_cards.py"):
        src = (pkg / rel).read_text(encoding="utf-8")
        assert "group_review" not in src, rel
    # The group module stays pure: it never imports a proof module.
    law_src = (pkg / "review" / "group_review.py").read_text(encoding="utf-8")
    assert "truelinev2.proof" not in law_src and ".proof." not in law_src
