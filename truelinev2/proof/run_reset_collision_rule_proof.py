r"""M8.2k -- PROOF-ONLY simulation of the reset-vs-continuous collision rule.

Applies the proposed rule (``proof/reset_collision_rule.py``) to the three banked,
human-graded M8.2j collisions and reports -- WITHOUT touching the engine -- what the
rule would classify, whether it would promote anything (never), and what would
happen to the default placements IF a future flag-gated engine pass consulted it.

ISOLATION: this script imports NO engine module (no run_match / decide / chains /
score / engine / frames / transition_classifier / adapters). Its only inputs are
the committed M8.2j grading ledger and the gitignored M5 sweep artifact (read-only,
for the banked default statuses). Default placement behavior is UNCHANGED; frame
translation stays INACTIVE; nothing is activated.

Run (repo root): $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_reset_collision_rule_proof
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from truelinev2.config import _REPO_ROOT
from truelinev2.proof.reset_collision_rule import (
    CollisionEvidence,
    RuleClass,
    classify_collision,
    may_auto_promote,
    simulate_default_status,
)
from truelinev2.proof.run_reset_collision_grade_report import load_ledger, validate_ledger

SWEEP_ARTIFACT = _REPO_ROOT / "data" / "outputs" / "truelinev2" / "m5_brenham" / "m5_brenham_coverage.json"
OUT_JSON = _REPO_ROOT / "data" / "outputs" / "reset_collision_rule_proof.json"
OUT_MD = _REPO_ROOT / "data" / "outputs" / "reset_collision_rule_proof.md"

# Default distribution the rule must be judged against (banked; re-verified by the
# external default-sweep gate every session). Corrected-source baseline 2026-06-10
# (bore_log9/15/16 station OCR fixed; log9 places via M7): 23 -> 24 placed.
EXPECTED_DEFAULT = {"AUTO_SELECT": 14, "REVIEW": 10, "ABSTAIN": 32, "ERROR": 2, "PLACED": 24}

# --- the three banked collision evidence records --------------------------------
# Every field cites its banked source: the committed M8.2j ledger (grades, evidence
# summaries, Patrick's 2026-06-10 rationales) and the M8.2h visual targets packet.
# These are the ONLY on-crossing reset-vs-continuous collisions in the 58-log corpus
# (M8.2g/M8.2h established exactly three).
EVIDENCE = [
    CollisionEvidence(
        case_id="log42",
        on_crossing_reset_equation=True,        # eq STA 2+70/5+16 references crossing 2+70 (ledger)
        exact_continuous_box_match=True,        # 270'+17'=287', deltas 0 (ledger)
        equation_visually_confirmed=True,       # Patrick 2026-06-10: reset_equation_confirmed
        far_side_matches_reset_station=True,    # s1 STA 5+16 TO 7+40 continuation (crop/rationale)
        conduit_changes_across_crossing=True,   # 1-1.25" -> 2-1.25" HDPE (rationale; corroborating)
    ),
    CollisionEvidence(
        case_id="log57",
        on_crossing_reset_equation=True,        # 3+98/3+08 and 3+93/3+08, both HIGH (ledger)
        exact_continuous_box_match=True,        # 413', deltas 0 (ledger)
        competing_equation_readings=True,       # one matchline read twice, 5 ft apart (rationale)
        readings_spread_ft=5.0,
    ),
    CollisionEvidence(
        case_id="log65",
        on_crossing_reset_equation=True,        # reciprocal STA 38+90/6+11 on-crossing (ledger)
        exact_continuous_box_match=True,        # 160'+39'=199', deltas 0 (ledger)
        parent_run_context_unresolved=True,     # run/segment child; continuation unconfirmed (rationale)
        ends_at_access_structure=True,          # ends at a flower pot (rationale)
        competing_continuation_evidence=True,   # 38+90 alternative continuation (ledger)
    ),
]


def _ledger_grades() -> Dict[str, str]:
    ledger = load_ledger()
    return {t["id"]: t["grade"] for t in ledger.get("targets", [])}


def _default_rows() -> Optional[Dict[str, Dict[str, Any]]]:
    """The banked default statuses for the whole corpus (read-only artifact)."""
    if not SWEEP_ARTIFACT.is_file():
        return None
    rows = json.loads(SWEEP_ARTIFACT.read_text(encoding="utf-8"))["rows"]
    return {r["bore_id"]: r for r in rows}


def main() -> int:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)

    ledger_result = validate_ledger(load_ledger())
    grades = _ledger_grades()
    rows = _default_rows()

    # 1. classify each banked collision and compare with Patrick's grade
    cases: List[Dict[str, Any]] = []
    correct = 0
    for ev in EVIDENCE:
        res = classify_collision(ev)
        grade = grades.get(ev.case_id, "<missing>")
        # ABSTAIN_REQUIRED etc. share names with ledger grades by design
        matches = res.classification.value == grade
        correct += int(matches)
        default_status = (rows or {}).get(ev.case_id, {}).get("status", "UNKNOWN(artifact missing)")
        simulated = (simulate_default_status(default_status, res)
                     if default_status in ("AUTO_SELECT", "REVIEW", "ABSTAIN", "ERROR") else "UNKNOWN")
        cases.append({
            "case_id": ev.case_id,
            "patrick_grade": grade,
            "rule_classification": res.classification.value,
            "classified_correctly": matches,
            "reason": res.reason,
            "may_auto_promote": may_auto_promote(res.classification),
            "default_status": default_status,
            "simulated_status_if_rule_consulted": simulated,
        })

    # 2. R6 invariant: nothing may auto-promote, under ANY classification
    auto_promotions = sum(1 for c in cases if c["may_auto_promote"])
    never_promote_all_classes = all(not may_auto_promote(k) for k in RuleClass)

    # 3. honest default-placement impact (simulation only; engine untouched)
    demotions = [c for c in cases
                 if c["default_status"] == "AUTO_SELECT"
                 and c["simulated_status_if_rule_consulted"] != "AUTO_SELECT"]
    sim_counts = dict(EXPECTED_DEFAULT)
    for c in demotions:
        sim_counts["AUTO_SELECT"] -= 1
        if c["simulated_status_if_rule_consulted"] == "REVIEW":
            sim_counts["REVIEW"] += 1
        else:
            sim_counts["ABSTAIN"] += 1
            sim_counts["PLACED"] -= 1
    preserves_all_23 = len(demotions) == 0

    verdict = ("PROOF_ONLY_READY_FOR_OPT_IN_TEST"
               if (correct == 3 and auto_promotions == 0 and never_promote_all_classes
                   and ledger_result["verdict"] == "ALL_GRADED_PENDING_ZERO_REGRESSION_PROOF")
               else "NOT_READY_MORE_EVIDENCE_REQUIRED")

    report = {
        "milestone": "truelinev2 M8.2k -- proof-only reset-vs-continuous collision rule proposal",
        "read_only": True,
        "engine_imports": [],
        "default_behavior_changed": False,
        "frame_translation_active": False,
        "ledger_verdict": ledger_result["verdict"],
        "cases": cases,
        "classified_correctly": f"{correct}/3",
        "auto_promotions": auto_promotions,
        "never_promote_invariant_all_classes": never_promote_all_classes,
        "preserves_all_23_default_placements": preserves_all_23,
        "default_impact_if_consulted": {
            "note": ("SIMULATION ONLY -- the engine was not run with the rule. The rule fires "
                     "ONLY on the three banked on-crossing collisions (M8.2g/h: exactly three "
                     "exist in the corpus); the other 20 placed logs are untouched by construction."),
            "demotions": [{c['case_id']: f"{c['default_status']} -> "
                          f"{c['simulated_status_if_rule_consulted']}"} for c in demotions],
            "simulated_distribution": sim_counts,
            "expected_default_distribution": EXPECTED_DEFAULT,
        },
        "m8_2d_regression_risk": {
            "resolves_23_to_15_risk": False,
            "note": ("The M8.2d 23->15 regression came from BLANKET frame translation treating "
                     "every cross-sheet link as needing a frame edge. This rule does NOT activate "
                     "translation and does not resolve that risk; M8.2d remains NOT_SAFE for "
                     "blanket opt-in. The rule instead bounds a narrow, human-graded collision "
                     "subset (3 logs) where the DEFAULT chain itself is now disputed evidence."),
        },
        "safe_for_future_opt_in_test": {
            "safe": verdict == "PROOF_ONLY_READY_FOR_OPT_IN_TEST",
            "expected_opt_in_effect": ("demote-only: AUTO log42->REVIEW, AUTO log57->REVIEW, "
                                       "AUTO log65->ABSTAIN; placed 23->22; zero promotions; "
                                       "zero changes to the other 55 logs"),
            "owner_decision_required": ("the opt-in test reduces AUTO coverage by 3 (zero-false "
                                        "over coverage); flag-gated, default-OFF, requires explicit "
                                        "approval before any engine wiring"),
        },
        "verdict": verdict,
    }
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines = [
        "# M8.2k -- reset-vs-continuous collision rule (PROOF-ONLY)",
        "",
        "**Read-only simulation. No engine import, no default change, no activation.**",
        "",
        f"- ledger verdict: `{ledger_result['verdict']}`",
        f"- classified correctly vs Patrick's grades: **{correct}/3**",
        f"- auto-promotions: **{auto_promotions}** (never-promote invariant over all classes: "
        f"{never_promote_all_classes})",
        f"- preserves all 23 default placements: **{preserves_all_23}**",
        "",
        "## Cases",
    ]
    for c in cases:
        lines += [f"### {c['case_id']}",
                  f"- Patrick: `{c['patrick_grade']}` | rule: `{c['rule_classification']}` "
                  f"| correct: **{c['classified_correctly']}**",
                  f"- default `{c['default_status']}` -> simulated "
                  f"`{c['simulated_status_if_rule_consulted']}` (if a future flag consulted the rule)",
                  f"- reason: {c['reason']}", ""]
    di = report["default_impact_if_consulted"]
    lines += [
        "## Default impact (simulation only)",
        f"- demotions: {di['demotions']}",
        f"- simulated distribution: {di['simulated_distribution']}",
        f"- banked default:        {di['expected_default_distribution']}",
        f"- {di['note']}",
        "",
        "## M8.2d relationship",
        f"- resolves the 23->15 blanket-translation risk: **False** -- {report['m8_2d_regression_risk']['note']}",
        "",
        "## Safe for future opt-in test?",
        f"- {report['safe_for_future_opt_in_test']['safe']}: "
        f"{report['safe_for_future_opt_in_test']['expected_opt_in_effect']}",
        f"- {report['safe_for_future_opt_in_test']['owner_decision_required']}",
        "",
        f"## VERDICT: {verdict}",
    ]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"[m8.2k] classified={correct}/3 auto_promotions={auto_promotions} "
          f"preserves_all_23={preserves_all_23} demotions={len(demotions)}")
    for c in cases:
        print(f"[m8.2k]   {c['case_id']}: grade={c['patrick_grade']} rule={c['rule_classification']} "
              f"correct={c['classified_correctly']} default={c['default_status']} "
              f"-> simulated={c['simulated_status_if_rule_consulted']}")
    print(f"[m8.2k] simulated distribution if consulted: {sim_counts} (banked: {EXPECTED_DEFAULT})")
    print(f"[m8.2k] VERDICT: {verdict}")
    print(f"[m8.2k] report -> {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
