r"""M8.4 -- OFF vs ON sweep for the default-OFF frame-aware continuation retry.

Runs the REAL engine over the 58-log corpus twice (OFF: no graph; ON: the SAFE
HIGH/unique/conflict-free frame graph injected as ``continuation_graph``) and
reports the EXACT changed set with full safety checks.

PASS requires ALL of:
  * OFF distribution == AUTO_SELECT=14 REVIEW=9 ABSTAIN=33 ERROR=2 PLACED=23
  * zero currently-PLACED logs change in any way (status/reason/sheets)
  * zero promotions toward AUTO anywhere
  * every ON-only placement (if any) is REVIEW with the FRAME_TRANSLATED_CONTINUATION caveat
The expected-set question (is it exactly log9/15/16?) is ANSWERED by the data, not
forced: the report states the empirical set and explains any difference from the
prediction. Strict (M8.2d blanket) semantics are untouched -- this retry is additive
(raw OR safe-translated links), fires only where the default would ABSTAIN without
ambiguity, and never produces AUTO.

Run (repo root): $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_frame_aware_continuation_optin
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from truelinev2.config import Settings, _REPO_ROOT
from truelinev2.extract.registry import select_dialect
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.match.engine import run_match
from truelinev2.proof.run_brenham_corpus import CORPUS_DIR, EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.service import _build_plan_frame_graph

OUT_JSON = _REPO_ROOT / "data" / "outputs" / "frame_aware_continuation_optin.json"
OUT_MD = _REPO_ROOT / "data" / "outputs" / "frame_aware_continuation_optin.md"

EXPECTED_OFF = {"AUTO_SELECT": 14, "REVIEW": 9, "ABSTAIN": 33, "ERROR": 2, "PLACED": 23}
PREDICTED_SET = ["log9", "log15", "log16"]  # the investigation's capability-#2 estimate
PLACED = ("AUTO_SELECT", "REVIEW")
_RANK = {"ABSTAIN": 0, "ERROR": 0, "REVIEW": 1, "AUTO_SELECT": 2}


def _counts(statuses: List[str]) -> Dict[str, int]:
    c = {k: statuses.count(k) for k in ("AUTO_SELECT", "REVIEW", "ABSTAIN", "ERROR")}
    c["PLACED"] = c["AUTO_SELECT"] + c["REVIEW"]
    return c


def main() -> int:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    if not os.path.isfile(PDF) or not os.path.isdir(CORPUS_DIR):
        print("[m8.4] STOP: inputs missing")
        return 2
    corpus = enumerate_corpus(CORPUS_DIR)
    if len(corpus) != EXPECTED_COUNT:
        print(f"[m8.4] STOP: corpus drift ({len(corpus)})")
        return 3

    settings = Settings.for_proof()
    assert settings.frame_continuation_optin is False, "for_proof() must keep the flag OFF"
    plan = PlanPdf(PDF)
    dialect = select_dialect(plan)
    offset = dialect.calibrate(plan, settings.sheet_offset)
    graph = _build_plan_frame_graph(plan, offset)

    rows: List[Dict[str, Any]] = []
    for p in corpus:
        try:
            bore = load_borelog(str(p))
        except Exception as e:
            rows.append({"bore_id": p.stem.replace("bore_log", "log"),
                         "off": "ERROR", "on": "ERROR", "error": f"{type(e).__name__}"})
            continue
        off = run_match(bore, plan, dialect, offset)
        on = run_match(bore, plan, dialect, offset, continuation_graph=graph)
        rows.append({
            "bore_id": bore.bore_id, "sheet_refs": list(bore.sheet_refs),
            "off": off.status.value, "on": on.status.value,
            "off_reason": off.reason, "on_reason": on.reason,
            "off_sheets": list(off.sheets), "on_sheets": list(on.sheets),
            "on_caveats": list(on.caveats),
            "changed": (off.status != on.status or off.reason != on.reason
                        or list(off.sheets) != list(on.sheets)),
        })
    plan.close()

    off_counts = _counts([r["off"] for r in rows])
    on_counts = _counts([r["on"] for r in rows])
    changed = [r for r in rows if r.get("changed")]
    placed_changed = [r for r in changed if r["off"] in PLACED]
    newly_placed = [r for r in changed if r["off"] not in PLACED and r["on"] in PLACED]
    promotions = [r for r in rows if _RANK.get(r["on"], 0) > _RANK.get(r["off"], 0)
                  and r["on"] == "AUTO_SELECT"]
    bad_new = [r for r in newly_placed
               if r["on"] != "REVIEW" or "FRAME_TRANSLATED_CONTINUATION" not in r["on_caveats"]]
    empirical_set = sorted(r["bore_id"] for r in changed)

    checks = {
        "off_matches_default": off_counts == EXPECTED_OFF,
        "zero_placed_logs_changed": not placed_changed,
        "zero_auto_promotions": not promotions,
        "all_new_placements_review_gated": not bad_new,
    }
    verdict = "PASS" if all(checks.values()) else "FAILURE"
    set_answer = ("EMPTY -- the predicted log9/15/16 set is REFUTED: those logs have no "
                  "callout within start tolerance of the bore start (startC=0), so no chain "
                  "ever STARTS; additive translated LINKING cannot reach a bore whose real "
                  "blocker is the START ANCHOR. The next missing relationship for that class "
                  "is anchor/frame binding, not linking."
                  if not changed else
                  f"{empirical_set} (predicted {PREDICTED_SET})")

    report = {
        "milestone": "truelinev2 M8.4 -- frame-aware continuation opt-in OFF vs ON sweep",
        "flag": "TL2_FRAME_AWARE_CONTINUATION_OPTIN (Settings.frame_continuation_optin, default OFF)",
        "frame_graph": {"safe_edges": len(graph.edges), "refused_conflicts": len(graph.conflicts)},
        "off_counts": off_counts, "expected_off": EXPECTED_OFF,
        "on_counts": on_counts,
        "changed": [{r['bore_id']: (r['off'], r['on'])} for r in changed],
        "empirical_changed_set": empirical_set,
        "predicted_set": PREDICTED_SET,
        "set_answer": set_answer,
        "placed_logs_changed": [r["bore_id"] for r in placed_changed],
        "newly_placed": [{r["bore_id"]: r["on"]} for r in newly_placed],
        "auto_promotions": [r["bore_id"] for r in promotions],
        "checks": checks, "verdict": verdict,
        "rows": rows,
    }
    OUT_JSON.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    L = ["# M8.4 -- frame-aware continuation opt-in (OFF vs ON)", "",
         f"- safe edges: {len(graph.edges)} · refused conflicts: {len(graph.conflicts)}",
         f"- OFF: {off_counts} (expected {EXPECTED_OFF})",
         f"- ON : {on_counts}",
         f"- empirical changed set: **{empirical_set or 'EMPTY'}** (predicted {PREDICTED_SET})",
         f"- answer: {set_answer}",
         f"- placed-log changes: {[r['bore_id'] for r in placed_changed] or 'NONE'} · "
         f"promotions: {[r['bore_id'] for r in promotions] or 'NONE'}",
         f"- checks: {checks}", "",
         f"## VERDICT: {verdict}"]
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")

    print(f"[m8.4] edges={len(graph.edges)} conflicts={len(graph.conflicts)}")
    print(f"[m8.4] OFF {off_counts}")
    print(f"[m8.4] ON  {on_counts}")
    print(f"[m8.4] changed set: {empirical_set or 'EMPTY'} (predicted {PREDICTED_SET})")
    print(f"[m8.4] checks={checks}")
    print(f"[m8.4] VERDICT: {verdict}")
    print(f"[m8.4] report -> {OUT_MD}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
