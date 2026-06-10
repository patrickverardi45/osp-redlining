"""M8.2j -- pure tests for the reset-collision grading-ledger validator (no PDF, no engine).

Locks: the bundled ledger is all-ungraded -> HUMAN_GRADING_REQUIRED; a grade is valid only with
full provenance; illegal/missing/extra targets -> INVALID_LEDGER; and a ledger NEVER resolves
placement (resolved_for_placement is always False).
"""
from __future__ import annotations

from truelinev2.proof.run_reset_collision_grade_report import (
    ALLOWED_GRADES,
    EXPECTED_IDS,
    load_ledger,
    validate_ledger,
)


def _t(tid, grade="ungraded", reviewer="", date="", rationale="", confidence=""):
    return {"id": tid, "sheets": [1, 2], "crossing_station": "2+70",
            "competing_equations": ["STA 2+70/5+16"], "crops": ["c.png"],
            "human_question": "q", "evidence_summary": "e", "grade": grade,
            "reviewer": reviewer, "date": date, "rationale": rationale, "confidence": confidence}


def _ledger(*targets):
    return {"targets": list(targets)}


def _graded(tid, grade="continuous_station_confirmed"):
    return _t(tid, grade, reviewer="Patrick", date="2026-06-10", rationale="read crop", confidence="high")


def test_allowed_grades_are_exactly_the_five():
    assert set(ALLOWED_GRADES) == {
        "continuous_station_confirmed", "reset_equation_confirmed",
        "precision_conflict_manual_review", "still_unknown_manual_review", "abstain_required"}


def test_bundled_committed_ledger_is_human_grading_required():
    r = validate_ledger(load_ledger())
    assert r["verdict"] == "HUMAN_GRADING_REQUIRED"
    assert r["complete"] is False and r["resolved_for_placement"] is False
    assert [p["id"] for p in r["per_target"]] == list(EXPECTED_IDS)
    assert all(p["status"] == "ungraded" for p in r["per_target"])


def test_in_memory_all_ungraded():
    r = validate_ledger(_ledger(_t("log42"), _t("log57"), _t("log65")))
    assert r["verdict"] == "HUMAN_GRADING_REQUIRED" and r["counts"]["ungraded"] == 3


def test_one_graded_is_partial():
    r = validate_ledger(_ledger(_graded("log42"), _t("log57"), _t("log65")))
    assert r["verdict"] == "PARTIALLY_GRADED_HUMAN_GRADING_REQUIRED"
    assert r["counts"]["graded"] == 1 and r["resolved_for_placement"] is False


def test_all_graded_with_provenance_is_pending_proof_not_resolved():
    r = validate_ledger(_ledger(_graded("log42"), _graded("log57"),
                                _graded("log65", "reset_equation_confirmed")))
    assert r["verdict"] == "ALL_GRADED_PENDING_ZERO_REGRESSION_PROOF"
    assert r["complete"] is True
    assert r["resolved_for_placement"] is False   # never resolves placement


def test_graded_without_provenance_is_invalid():
    bad = _t("log42", "continuous_station_confirmed")  # provenance blank
    r = validate_ledger(_ledger(bad, _t("log57"), _t("log65")))
    assert r["verdict"] == "INVALID_LEDGER"
    p = next(x for x in r["per_target"] if x["id"] == "log42")
    assert p["status"] == "invalid" and any("provenance" in i for i in p["issues"])


def test_illegal_grade_is_invalid():
    r = validate_ledger(_ledger(_t("log42", "looks_continuous_to_me"), _t("log57"), _t("log65")))
    assert r["verdict"] == "INVALID_LEDGER"


def test_missing_target_is_invalid():
    r = validate_ledger(_ledger(_t("log42"), _t("log57")))  # log65 absent
    assert r["verdict"] == "INVALID_LEDGER"
    assert next(x for x in r["per_target"] if x["id"] == "log65")["status"] == "missing"


def test_extra_target_is_invalid():
    r = validate_ledger(_ledger(_t("log42"), _t("log57"), _t("log65"), _t("log99")))
    assert r["verdict"] == "INVALID_LEDGER" and "log99" in r["extra_ids"]


def test_resolved_for_placement_is_always_false():
    for led in (_ledger(_t("log42"), _t("log57"), _t("log65")),
                _ledger(_graded("log42"), _graded("log57"), _graded("log65")),
                _ledger(_t("log42", "bogus"), _t("log57"), _t("log65"))):
        assert validate_ledger(led)["resolved_for_placement"] is False
