r"""M8.5 -- OFF vs ON sweep for the default-OFF reverse endpoint anchor retry.

Runs the REAL engine over the 58-log corpus three ways:
  OFF       -- no reverse context (the byte-identical default)
  REV       -- reverse-anchor context injected (TL2_REVERSE_ENDPOINT_ANCHOR_OPTIN)
  REV+COLL  -- reverse + the M8.2l reset-collision gate (composition check)

PASS requires ALL of:
  * OFF distribution == AUTO_SELECT=14 REVIEW=9 ABSTAIN=33 ERROR=2 PLACED=23
  * zero currently-PLACED logs change in any way (status/reason/sheets)
  * zero promotions toward AUTO anywhere
  * every ON-only placement is REVIEW with reason REVERSE_ENDPOINT_ANCHOR
  * REV+COLL == the M8.2l demotions (log42/57/65) + the REV additions, independently
    composed (no interference either direction)
The changed-set question is ANSWERED by the data, not forced: the proof predicted
{log5, log7, log27, log36, log45}; the report states the empirical set.

Run (repo root): $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_reverse_endpoint_optin_sweep
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from truelinev2.config import Settings, _REPO_ROOT
from truelinev2.extract.registry import select_dialect
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.match.collision_gate import (
    CollisionGate,
    collect_all_sheet_equations,
    collect_equations,
    load_human_grades,
)
from truelinev2.match.engine import run_match
from truelinev2.match.reverse_anchor import ReverseAnchorContext
from truelinev2.match.transition_classifier import conflict_sheet_pairs
from truelinev2.proof.run_brenham_corpus import CORPUS_DIR, EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.service import _build_plan_frame_graph

OUT_JSON = _REPO_ROOT / "data" / "outputs" / "reverse_endpoint_optin_sweep.json"
OUT_MD = _REPO_ROOT / "data" / "outputs" / "reverse_endpoint_optin_sweep.md"

# Corrected-source baseline 2026-06-10 (bore_log9/15/16 station OCR fixed;
# log9 places REVIEW via the M7 unique-footage fallback): default 23 -> 24.
EXPECTED_OFF = {"AUTO_SELECT": 14, "REVIEW": 10, "ABSTAIN": 32, "ERROR": 2, "PLACED": 24}
# The M8.5 proof's READY set AFTER the adversarial-review guards (reset-boundary
# mask killed log36; near-rival guard pick-carded log5; frame-coherence demoted
# log45) and the corrected-source replay. log7 + log27 are held-out-corroborated.
PREDICTED_SET = ["log27", "log7"]
COLLISION_SET = {"log42": "REVIEW", "log57": "REVIEW", "log65": "ABSTAIN"}  # banked M8.2l
PLACED = ("AUTO_SELECT", "REVIEW")
_RANK = {"ABSTAIN": 0, "ERROR": 0, "REVIEW": 1, "AUTO_SELECT": 2}


def _counts(statuses: List[str]) -> Dict[str, int]:
    c = {k: statuses.count(k) for k in ("AUTO_SELECT", "REVIEW", "ABSTAIN", "ERROR")}
    c["PLACED"] = c["AUTO_SELECT"] + c["REVIEW"]
    return c


def main() -> int:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    if not os.path.isfile(PDF) or not os.path.isdir(CORPUS_DIR):
        print("[m8.5-sweep] STOP: inputs missing")
        return 2
    corpus = enumerate_corpus(CORPUS_DIR)
    if len(corpus) != EXPECTED_COUNT:
        print(f"[m8.5-sweep] STOP: corpus drift ({len(corpus)})")
        return 3

    settings = Settings.for_proof()
    assert settings.reverse_endpoint_optin is False, "for_proof() must keep the flag OFF"
    plan = PlanPdf(PDF)
    dialect = select_dialect(plan)
    offset = dialect.calibrate(plan, settings.sheet_offset)
    graph = _build_plan_frame_graph(plan, offset)
    conflicts = conflict_sheet_pairs(graph)
    # M8.12: canonical ALL-SHEETS reverse-anchor equation universe (far-side
    # matchline masking; the banked log62 divergence). Collision gate stays
    # per-bore -- its banked construction, consistent everywhere.
    eq_all = collect_all_sheet_equations(plan, offset)

    rows: List[Dict[str, Any]] = []
    for p in corpus:
        try:
            bore = load_borelog(str(p))
        except Exception as e:
            rows.append({"bore_id": p.stem.replace("bore_log", "log"),
                         "off": "ERROR", "rev": "ERROR", "rev_coll": "ERROR",
                         "error": f"{type(e).__name__}"})
            continue
        ctx = ReverseAnchorContext(
            graph=graph, conflicts=conflicts, equations_by_sheet=eq_all)
        gate = CollisionGate(
            equations_by_sheet=collect_equations(plan, offset, bore.sheet_refs),
            human_grades=load_human_grades())
        off = run_match(bore, plan, dialect, offset)
        rev = run_match(bore, plan, dialect, offset, reverse_anchor=ctx)
        rev_coll = run_match(bore, plan, dialect, offset, reverse_anchor=ctx,
                             collision_gate=gate)
        rows.append({
            "bore_id": bore.bore_id,
            "off": off.status.value, "rev": rev.status.value,
            "rev_coll": rev_coll.status.value,
            "off_reason": off.reason, "rev_reason": rev.reason,
            "rev_coll_reason": rev_coll.reason,
            "off_sheets": list(off.sheets), "rev_sheets": list(rev.sheets),
            "rev_caveats": list(rev.caveats),
            "changed": (off.status != rev.status or off.reason != rev.reason
                        or list(off.sheets) != list(rev.sheets)),
        })
    plan.close()

    off_counts = _counts([r["off"] for r in rows])
    rev_counts = _counts([r["rev"] for r in rows])
    rc_counts = _counts([r["rev_coll"] for r in rows])
    changed = [r for r in rows if r.get("changed")]
    placed_changed = [r for r in changed if r["off"] in PLACED]
    newly_placed = [r for r in changed if r["off"] not in PLACED and r["rev"] in PLACED]
    promotions = [r for r in rows
                  if _RANK.get(r["rev"], 0) > _RANK.get(r["off"], 0) and r["rev"] == "AUTO_SELECT"]
    bad_new = [r for r in newly_placed
               if r["rev"] != "REVIEW" or r["rev_reason"] != "REVERSE_ENDPOINT_ANCHOR"
               or "REVERSE_ENDPOINT_ANCHOR" not in r["rev_caveats"]]
    empirical_set = sorted(r["bore_id"] for r in changed)

    # composition: REV+COLL must equal the independent effects, per log.
    compose_bad = []
    for r in rows:
        expected = COLLISION_SET.get(r["bore_id"], r["rev"])
        if r["rev_coll"] != expected:
            compose_bad.append({r["bore_id"]: (r["rev"], r["rev_coll"], expected)})

    checks = {
        "off_matches_default": off_counts == EXPECTED_OFF,
        "zero_placed_logs_changed": not placed_changed,
        "zero_auto_promotions": not promotions,
        "all_new_placements_review_reverse_reason": not bad_new,
        "collision_gate_composes_independently": not compose_bad,
    }
    verdict = "PASS" if all(checks.values()) else "FAILURE"

    report = {
        "milestone": "truelinev2 M8.5 -- reverse endpoint anchor opt-in OFF vs ON sweep",
        "flag": "TL2_REVERSE_ENDPOINT_ANCHOR_OPTIN (Settings.reverse_endpoint_optin, default OFF)",
        "off_counts": off_counts, "expected_off": EXPECTED_OFF,
        "rev_counts": rev_counts, "rev_coll_counts": rc_counts,
        "empirical_changed_set": empirical_set, "predicted_set": sorted(PREDICTED_SET),
        "set_matches_prediction": empirical_set == sorted(PREDICTED_SET),
        "newly_placed": [{r["bore_id"]: (r["rev"], r["rev_reason"])} for r in newly_placed],
        "placed_logs_changed": [r["bore_id"] for r in placed_changed],
        "auto_promotions": [r["bore_id"] for r in promotions],
        "composition_mismatches": compose_bad,
        "checks": checks, "verdict": verdict,
        "rows": rows,
    }
    OUT_JSON.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    L = ["# M8.5 -- reverse endpoint anchor opt-in (OFF vs ON vs ON+collision)", "",
         f"- OFF      : {off_counts} (expected {EXPECTED_OFF})",
         f"- REV ON   : {rev_counts}",
         f"- REV+COLL : {rc_counts}",
         f"- empirical changed set: **{empirical_set or 'EMPTY'}** "
         f"(predicted {sorted(PREDICTED_SET)}; match={empirical_set == sorted(PREDICTED_SET)})",
         f"- newly placed: {[list(d.keys())[0] for d in report['newly_placed']] or 'NONE'} · "
         f"placed-log changes: {report['placed_logs_changed'] or 'NONE'} · "
         f"promotions: {report['auto_promotions'] or 'NONE'}",
         f"- checks: {checks}", "",
         f"## VERDICT: {verdict}"]
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")

    print(f"[m8.5-sweep] OFF      {off_counts}")
    print(f"[m8.5-sweep] REV ON   {rev_counts}")
    print(f"[m8.5-sweep] REV+COLL {rc_counts}")
    print(f"[m8.5-sweep] changed set: {empirical_set or 'EMPTY'} "
          f"(predicted {sorted(PREDICTED_SET)})")
    print(f"[m8.5-sweep] checks={checks}")
    print(f"[m8.5-sweep] VERDICT: {verdict}")
    print(f"[m8.5-sweep] report -> {OUT_MD}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
