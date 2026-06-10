r"""M8.2j -- read-only VALIDATION/REPORT for the reset-vs-continuous human grading ledger.

It ONLY validates the ledger (truelinev2/docs/review/m8-2j-reset-collision-human-grades.json):
that exactly the three M8.2h targets are present, each has the required fields, every grade is
legal, and any recorded grade carries full provenance (reviewer/date/rationale/confidence). It
emits a completeness verdict.

It is NOT an engine pass: it imports NOTHING from match/decide/engine/run_match, feeds nothing
into placement, changes no matching behavior, and NEVER marks a target "resolved" -- even a fully
graded ledger stays gated behind a future zero-regression proof. Outputs go to gitignored
data/outputs/ only.

Run (repo root): $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_reset_collision_grade_report
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from truelinev2.config import _REPO_ROOT

LEDGER_PATH = _REPO_ROOT / "truelinev2" / "docs" / "review" / "m8-2j-reset-collision-human-grades.json"

ALLOWED_GRADES = (
    "continuous_station_confirmed",
    "reset_equation_confirmed",
    "precision_conflict_manual_review",
    "still_unknown_manual_review",
    "abstain_required",
)
UNGRADED = "ungraded"
EXPECTED_IDS = ("log42", "log57", "log65")
REQUIRED_FIELDS = (
    "id", "sheets", "crossing_station", "competing_equations", "crops",
    "human_question", "evidence_summary", "grade", "reviewer", "date", "rationale", "confidence",
)
PROVENANCE_FIELDS = ("reviewer", "date", "rationale", "confidence")


def validate_ledger(ledger: Dict[str, Any]) -> Dict[str, Any]:
    """Pure validation. Returns a verdict + per-target status. Never mutates placement, never
    marks a target resolved. A grade is valid ONLY if it is legal AND (if not ``ungraded``) every
    provenance field is filled."""
    targets = ledger.get("targets") or []
    by_id = {t.get("id"): t for t in targets if isinstance(t, dict)}

    per_target: List[Dict[str, Any]] = []
    for tid in EXPECTED_IDS:
        t = by_id.get(tid)
        if t is None:
            per_target.append({"id": tid, "grade": None, "status": "missing",
                               "issues": ["target absent from ledger"]})
            continue
        issues: List[str] = []
        missing_fields = [f for f in REQUIRED_FIELDS if f not in t]
        if missing_fields:
            issues.append("missing fields: " + ", ".join(missing_fields))
        grade = t.get("grade", "")
        legal = grade == UNGRADED or grade in ALLOWED_GRADES
        if not legal:
            issues.append(f"illegal grade: {grade!r}")
        if missing_fields or not legal:
            status = "invalid"
        elif grade == UNGRADED:
            status = "ungraded"
        else:
            missing_prov = [f for f in PROVENANCE_FIELDS if not str(t.get(f, "")).strip()]
            if missing_prov:
                status = "invalid"
                issues.append("graded but missing provenance: " + ", ".join(missing_prov))
            else:
                status = "graded"
        per_target.append({"id": tid, "grade": grade, "status": status, "issues": issues})

    extra_ids = sorted(i for i in by_id if i not in EXPECTED_IDS)
    n_invalid = sum(1 for p in per_target if p["status"] in ("invalid", "missing"))
    n_graded = sum(1 for p in per_target if p["status"] == "graded")
    n_ungraded = sum(1 for p in per_target if p["status"] == "ungraded")

    if extra_ids:
        n_invalid += 1
    if n_invalid:
        verdict = "INVALID_LEDGER"
    elif n_graded == 0:
        verdict = "HUMAN_GRADING_REQUIRED"
    elif n_graded < len(EXPECTED_IDS):
        verdict = "PARTIALLY_GRADED_HUMAN_GRADING_REQUIRED"
    else:
        verdict = "ALL_GRADED_PENDING_ZERO_REGRESSION_PROOF"

    return {
        "verdict": verdict,
        "complete": verdict == "ALL_GRADED_PENDING_ZERO_REGRESSION_PROOF",
        "resolved_for_placement": False,   # invariant: a ledger never resolves placement
        "counts": {"graded": n_graded, "ungraded": n_ungraded, "invalid": n_invalid},
        "extra_ids": extra_ids,
        "per_target": per_target,
        "allowed_grades": list(ALLOWED_GRADES),
        "expected_ids": list(EXPECTED_IDS),
    }


def load_ledger() -> Dict[str, Any]:
    return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))


def _render_md(result: Dict[str, Any]) -> str:
    lines = [
        "# M8.2j reset-collision human grading ledger -- validation report",
        "",
        f"## VERDICT: {result['verdict']}",
        f"- complete (all graded w/ provenance): **{result['complete']}**",
        f"- resolved_for_placement: **{result['resolved_for_placement']}** (always false -- a ledger "
        "never resolves placement; a future zero-regression proof is required)",
        f"- counts: {result['counts']}",
        (f"- UNEXPECTED extra target ids: {result['extra_ids']}" if result["extra_ids"] else ""),
        "",
        "## Per target",
    ]
    for p in result["per_target"]:
        suffix = ("  issues: " + "; ".join(p["issues"])) if p.get("issues") else ""
        lines.append(f"- **{p['id']}**: grade=`{p['grade']}` status=**{p['status']}**{suffix}")
    lines += [
        "",
        "## Meaning",
        "- `HUMAN_GRADING_REQUIRED` -- nothing graded yet; Patrick must grade the M8.2h crops.",
        "- `PARTIALLY_GRADED_HUMAN_GRADING_REQUIRED` -- some graded; grading not finished.",
        "- `ALL_GRADED_PENDING_ZERO_REGRESSION_PROOF` -- all graded WITH provenance, but still NOT "
        "usable for auto-placement until a flag-gated rule passes an M8.2d zero-regression proof.",
        "- `INVALID_LEDGER` -- a missing target, illegal grade, missing field, or a grade without "
        "full provenance. Fix the ledger JSON.",
        "",
        "_Read-only. No engine/classifier/default change; frame translation INACTIVE; no placement "
        "uses these grades._",
    ]
    return "\n".join(l for l in lines if l is not None) + "\n"


def main() -> int:
    out_dir = _REPO_ROOT / "data" / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "reset_collision_grade_report.json"
    md_path = out_dir / "reset_collision_grade_report.md"

    if not LEDGER_PATH.is_file():
        report = {"verdict": "INVALID_LEDGER", "error": f"ledger not found: {LEDGER_PATH}"}
        json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"[m8.2j] STOP: ledger not found at {LEDGER_PATH}")
        return 1
    try:
        ledger = load_ledger()
    except Exception as e:
        report = {"verdict": "INVALID_LEDGER", "error": f"{type(e).__name__}: {e}"}
        json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"[m8.2j] STOP: ledger is not valid JSON: {e}")
        return 1

    result = validate_ledger(ledger)
    report = {"milestone": "truelinev2 M8.2j -- reset-collision human grading ledger validation",
              "read_only": True, "feeds_placement": False, "ledger": str(LEDGER_PATH), **result}
    json_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    md_path.write_text(_render_md(result), encoding="utf-8")

    print(f"[m8.2j] VERDICT: {result['verdict']}  counts={result['counts']}  "
          f"resolved_for_placement={result['resolved_for_placement']}")
    for p in result["per_target"]:
        print(f"[m8.2j]   {p['id']}: {p['status']} (grade={p['grade']})")
    print(f"[m8.2j] report -> {md_path}")
    return 1 if result["verdict"] == "INVALID_LEDGER" else 0


if __name__ == "__main__":
    raise SystemExit(main())
