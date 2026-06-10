"""M8.2h -- pure unit tests for the visual-target classifier (no PDF, no engine).

Locks the geometry-first verdict: an equation that references the crossing station (or sits
within the near threshold) is the matchline AT the crossing -> still_unknown when an exact box
match also collides; an equation that references other stations AND is far is a confirmed
different matchline; an unlocatable equation stays unknown; a shared-side precision spread is a
pseudo-conflict for manual review. It never fabricates a continuous/reset confirmation.
"""
from __future__ import annotations

from truelinev2.proof.run_transition_visual_targets import (
    VisualEvidence,
    Verdict,
    classify_visual,
)


def _ev(**kw) -> VisualEvidence:
    base = dict(precision_conflict=False, equation_located=True, min_reset_distance=130.0,
                near_threshold=166.0, exact_box_match=True, crossing_station_in_equation=False)
    base.update(kw)
    return VisualEvidence(**base)


def test_verdict_values_match_required_set():
    assert {v.value for v in Verdict} == {
        "continuous_station_confirmed", "reset_equation_confirmed",
        "different_matchline_confirmed", "precision_conflict_manual_review",
        "still_unknown_manual_review"}


def test_precision_conflict():
    a = classify_visual(_ev(precision_conflict=True))
    assert a.verdict is Verdict.PRECISION_CONFLICT_MANUAL_REVIEW


def test_unlocatable_equation_is_still_unknown():
    a = classify_visual(_ev(equation_located=False, min_reset_distance=None))
    assert a.verdict is Verdict.STILL_UNKNOWN_MANUAL_REVIEW


def test_crossing_station_reference_is_still_unknown_collision():
    # log42/log65 shape: the equation references the crossing station -> matchline AT the crossing.
    a = classify_visual(_ev(crossing_station_in_equation=True, min_reset_distance=400.0))
    assert a.verdict is Verdict.STILL_UNKNOWN_MANUAL_REVIEW
    assert "at this crossing" in a.rationale.lower() or "crossing station" in a.rationale.lower()


def test_near_distance_without_station_ref_is_still_unknown():
    a = classify_visual(_ev(crossing_station_in_equation=False, min_reset_distance=120.0,
                            near_threshold=166.0))
    assert a.verdict is Verdict.STILL_UNKNOWN_MANUAL_REVIEW


def test_far_and_other_stations_is_different_matchline_confirmed():
    # the one geometry-decidable outcome: reset references other stations AND is far away.
    a = classify_visual(_ev(crossing_station_in_equation=False, min_reset_distance=900.0,
                            near_threshold=166.0))
    assert a.verdict is Verdict.DIFFERENT_MATCHLINE_CONFIRMED


def test_located_but_unmeasurable_distance_is_still_unknown():
    # Located equation but no crossing-box coords to measure against -> cannot confirm a different
    # matchline; must stay unknown (and must NOT crash formatting a None distance).
    a = classify_visual(_ev(crossing_station_in_equation=False, min_reset_distance=None))
    assert a.verdict is Verdict.STILL_UNKNOWN_MANUAL_REVIEW


def test_three_real_targets():
    log42 = _ev(crossing_station_in_equation=True, min_reset_distance=135.8, near_threshold=165.9)
    log57 = _ev(precision_conflict=True, crossing_station_in_equation=True,
                min_reset_distance=147.5, near_threshold=165.9)
    log65 = _ev(crossing_station_in_equation=True, min_reset_distance=130.5, near_threshold=165.9)
    assert classify_visual(log42).verdict is Verdict.STILL_UNKNOWN_MANUAL_REVIEW
    assert classify_visual(log57).verdict is Verdict.PRECISION_CONFLICT_MANUAL_REVIEW
    assert classify_visual(log65).verdict is Verdict.STILL_UNKNOWN_MANUAL_REVIEW


def test_every_verdict_has_rationale():
    for ev in (_ev(), _ev(precision_conflict=True), _ev(equation_located=False),
               _ev(crossing_station_in_equation=True),
               _ev(min_reset_distance=900.0, near_threshold=166.0)):
        assert classify_visual(ev).rationale
