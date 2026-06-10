"""M8.2g -- pure unit tests for the evidence-adjudication helper (no PDF, no engine).

Locks the transparent rules the read-only report uses to grade a dirty transition:
parser_false_positive (impossible offset + exact box), extraction-precision pseudo-conflict
(shared side, small spread), true_conflict_abstain (plausible disagreement), reset_equation
(real reset, untight default), and needs_manual_review (everything undecided).
"""
from __future__ import annotations

from truelinev2.proof.run_transition_evidence_refinement import (
    AdjEvidence,
    Recommendation,
    adjudicate,
)


def _ev(**kw) -> AdjEvidence:
    base = dict(
        classification="ambiguous", conflict=False, has_safe_edge=True,
        edge_offset_ft=246.0, raw_gap_ft=0.0, translated_gap_ft=246.0,
        edge_high_confidence=True, offset_geometrically_possible=True,
        default_tight=True, n_link_equations=1,
        conflict_shared_side=False, conflict_offset_spread_ft=None)
    base.update(kw)
    return AdjEvidence(**base)


def test_recommendation_values_match_required_set():
    assert {r.value for r in Recommendation} == {
        "continuous_station_confirmed", "reset_equation_confirmed",
        "parser_false_positive", "true_conflict_abstain", "needs_manual_review"}


def test_precision_conflict_shared_side_small_spread_is_manual_review():
    # log57 shape: two HIGH eqs share a side, disagree by 5ft -> one imprecise matchline.
    a = adjudicate(_ev(classification="conflict", conflict=True, has_safe_edge=False,
                       edge_offset_ft=None, n_link_equations=2,
                       conflict_shared_side=True, conflict_offset_spread_ft=5.0))
    assert a.recommendation is Recommendation.NEEDS_MANUAL_REVIEW
    assert "one matchline" in a.rationale.lower() or "share a side" in a.rationale.lower()


def test_true_conflict_abstain_when_plausible_and_not_precision():
    a = adjudicate(_ev(classification="conflict", conflict=True, has_safe_edge=False,
                       edge_offset_ft=None, offset_geometrically_possible=True,
                       n_link_equations=2, conflict_shared_side=False,
                       conflict_offset_spread_ft=200.0))
    assert a.recommendation is Recommendation.TRUE_CONFLICT_ABSTAIN


def test_conflict_with_impossible_edge_defers_to_review():
    a = adjudicate(_ev(classification="conflict", conflict=True, has_safe_edge=False,
                       edge_offset_ft=None, offset_geometrically_possible=False,
                       n_link_equations=2, conflict_shared_side=False,
                       conflict_offset_spread_ft=400.0))
    assert a.recommendation is Recommendation.NEEDS_MANUAL_REVIEW


def test_parser_false_positive_impossible_offset_with_exact_box():
    a = adjudicate(_ev(classification="ambiguous", edge_offset_ft=9999.0,
                       offset_geometrically_possible=False, default_tight=True))
    assert a.recommendation is Recommendation.PARSER_FALSE_POSITIVE


def test_ambiguous_exact_box_with_possible_reset_is_manual_review():
    # log42 / log65 shape: exact continuous box match AND a geometrically-possible reset.
    a = adjudicate(_ev(classification="ambiguous", offset_geometrically_possible=True,
                       default_tight=True, edge_high_confidence=True))
    assert a.recommendation is Recommendation.NEEDS_MANUAL_REVIEW
    assert "exact" in a.rationale.lower()


def test_reset_equation_confirmed_when_high_conf_and_not_tight():
    a = adjudicate(_ev(classification="ambiguous", offset_geometrically_possible=True,
                       default_tight=False, edge_high_confidence=True))
    assert a.recommendation is Recommendation.RESET_EQUATION_CONFIRMED


def test_ambiguous_low_conf_not_tight_is_manual_review():
    a = adjudicate(_ev(classification="ambiguous", offset_geometrically_possible=True,
                       default_tight=False, edge_high_confidence=False))
    assert a.recommendation is Recommendation.NEEDS_MANUAL_REVIEW


def test_every_adjudication_carries_rationale_and_future_rule():
    for ev in (_ev(), _ev(classification="conflict", conflict=True, n_link_equations=2,
                          conflict_shared_side=True, conflict_offset_spread_ft=5.0)):
        a = adjudicate(ev)
        assert a.rationale and a.future_rule


def test_the_three_real_target_shapes_all_need_review():
    log42 = _ev(classification="ambiguous", edge_offset_ft=246.0,
                offset_geometrically_possible=True, default_tight=True,
                edge_high_confidence=True, n_link_equations=3)
    log57 = _ev(classification="conflict", conflict=True, has_safe_edge=False,
                edge_offset_ft=None, offset_geometrically_possible=True,
                n_link_equations=2, conflict_shared_side=True, conflict_offset_spread_ft=5.0)
    log65 = _ev(classification="ambiguous", edge_offset_ft=-3279.0,
                offset_geometrically_possible=True, default_tight=True,
                edge_high_confidence=True, n_link_equations=2)
    for ev in (log42, log57, log65):
        assert adjudicate(ev).recommendation is Recommendation.NEEDS_MANUAL_REVIEW
