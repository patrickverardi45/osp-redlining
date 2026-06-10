"""M8.2k -- pure tests for the PROOF-ONLY reset-collision rule (no PDF, no engine).

Locks the proposed rule's behavior:
  * the three banked, graded cases classify exactly as Patrick graded them;
  * R6: NO classification may auto-promote (constant False, all classes);
  * R4: an exact continuous box match alone never overrides an on-crossing reset;
  * R5: an on-crossing reset alone never overrides parent-run/segment ambiguity;
  * simulation is demote-only -- nothing ever moves toward AUTO.
"""
from __future__ import annotations

from truelinev2.proof.reset_collision_rule import (
    CollisionEvidence,
    RuleClass,
    classify_collision,
    may_auto_promote,
    simulate_default_status,
)
from truelinev2.proof.run_reset_collision_rule_proof import EVIDENCE


def _ev(case_id="x", **kw):
    base = dict(on_crossing_reset_equation=True, exact_continuous_box_match=True)
    base.update(kw)
    return CollisionEvidence(case_id=case_id, **base)


# --- the three banked graded cases ------------------------------------------------

def test_banked_fixtures_match_patricks_grades():
    expected = {
        "log42": RuleClass.RESET_EQUATION_CONFIRMED,
        "log57": RuleClass.PRECISION_CONFLICT_MANUAL_REVIEW,
        "log65": RuleClass.ABSTAIN_REQUIRED,
    }
    got = {ev.case_id: classify_collision(ev).classification for ev in EVIDENCE}
    assert got == expected


def test_log42_style_confirmed_reset():
    r = classify_collision(_ev(equation_visually_confirmed=True,
                               far_side_matches_reset_station=True))
    assert r.classification is RuleClass.RESET_EQUATION_CONFIRMED
    assert r.blocks_auto is True  # the continuous AUTO chain is disputed


def test_log57_style_precision_conflict():
    r = classify_collision(_ev(competing_equation_readings=True, readings_spread_ft=5.0))
    assert r.classification is RuleClass.PRECISION_CONFLICT_MANUAL_REVIEW


def test_log65_style_parent_run_ambiguity_abstains():
    r = classify_collision(_ev(parent_run_context_unresolved=True,
                               ends_at_access_structure=True,
                               competing_continuation_evidence=True))
    assert r.classification is RuleClass.ABSTAIN_REQUIRED


# --- the user-specified safety properties ------------------------------------------

def test_R4_continuous_match_alone_never_overrides_on_crossing_reset():
    # on-crossing eq present, NOT confirmed, exact continuous match present:
    # continuous must NOT silently win -> manual review.
    r = classify_collision(_ev())
    assert r.classification is RuleClass.STILL_UNKNOWN_MANUAL_REVIEW
    assert r.blocks_auto is True


def test_R5_reset_equation_never_overrides_parent_run_ambiguity():
    # even a visually CONFIRMED equation does not outrank unresolved parent-run context
    r = classify_collision(_ev(equation_visually_confirmed=True,
                               far_side_matches_reset_station=True,
                               parent_run_context_unresolved=True))
    assert r.classification is RuleClass.ABSTAIN_REQUIRED


def test_R6_no_class_may_auto_promote():
    assert all(may_auto_promote(k) is False for k in RuleClass)


def test_no_collision_continuous_stands():
    r = classify_collision(_ev(on_crossing_reset_equation=False))
    assert r.classification is RuleClass.CONTINUOUS_STATION_STANDS
    assert r.blocks_auto is False


def test_structure_end_without_competing_evidence_is_not_abstain():
    # ends at a structure but NO competing continuation -> falls through (R4 manual here)
    r = classify_collision(_ev(ends_at_access_structure=True))
    assert r.classification is RuleClass.STILL_UNKNOWN_MANUAL_REVIEW


def test_wide_spread_is_not_a_precision_conflict():
    # readings far apart are NOT one matchline read twice; falls through to R4/R1
    r = classify_collision(_ev(competing_equation_readings=True, readings_spread_ft=500.0))
    assert r.classification is RuleClass.STILL_UNKNOWN_MANUAL_REVIEW


# --- simulation: demote-only, never toward AUTO -------------------------------------

def test_simulation_demotes_disputed_auto():
    reset = classify_collision(_ev(equation_visually_confirmed=True,
                                   far_side_matches_reset_station=True))
    abstain = classify_collision(_ev(parent_run_context_unresolved=True))
    assert simulate_default_status("AUTO_SELECT", reset) == "REVIEW"
    assert simulate_default_status("AUTO_SELECT", abstain) == "ABSTAIN"


def test_simulation_never_promotes():
    for ev in (_ev(), _ev(on_crossing_reset_equation=False),
               _ev(equation_visually_confirmed=True, far_side_matches_reset_station=True),
               _ev(parent_run_context_unresolved=True)):
        r = classify_collision(ev)
        assert simulate_default_status("ABSTAIN", r) in ("ABSTAIN",)
        assert simulate_default_status("REVIEW", r) in ("REVIEW", "ABSTAIN")  # never AUTO
        assert simulate_default_status("ERROR", r) == "ERROR"


def test_simulation_leaves_non_collision_untouched():
    r = classify_collision(_ev(on_crossing_reset_equation=False))
    for s in ("AUTO_SELECT", "REVIEW", "ABSTAIN", "ERROR"):
        assert simulate_default_status(s, r) == s
