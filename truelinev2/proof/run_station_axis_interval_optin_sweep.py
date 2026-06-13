r"""M8.8 -- OFF vs ON sweep for the default-OFF station-axis interval retry.

Four legs over the 58-log corpus:
  OFF            -- no contexts (the byte-identical corrected-source default)
  AXIS           -- station-axis context only (TL2_STATION_AXIS_INTERVAL_OPTIN)
  AXIS+M85       -- station-axis + reverse-endpoint contexts (the 30-placed ceiling)
  AXIS+M85+COLL  -- plus the reset-collision gate (composition)

PASS requires ALL of:
  * OFF == the corrected-source baseline (AUTO 14 / REVIEW 10 / ABSTAIN 32 / ERROR 2)
  * AXIS-alone changed set == the M8.7 proof's READY set {log15,log16,log27,log45,log72}
    (log27 is axis-READY too; with M8.5 also on, the reverse retry takes it first)
  * the AXIS increment OVER M8.5-ON == exactly {log15,log16,log45,log72} -> 30 placed
  * zero placed-log changes, zero AUTO promotions
  * every axis placement is REVIEW with reason STATION_AXIS_INTERVAL_PATH

Run (repo root): $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_station_axis_interval_optin_sweep
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from truelinev2.config import Settings, _REPO_ROOT
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.station_axis import parse_tick
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
from truelinev2.match.station_axis_interval import StationAxisContext
from truelinev2.match.transition_classifier import conflict_sheet_pairs
from truelinev2.proof.run_brenham_corpus import CORPUS_DIR, EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.match.frames import _build_plan_frame_graph

OUT_JSON = _REPO_ROOT / "data" / "outputs" / "station_axis_interval_optin_sweep.json"
OUT_MD = _REPO_ROOT / "data" / "outputs" / "station_axis_interval_optin_sweep.md"

# Corrected-source baseline 2026-06-10 (see run_reverse_endpoint_anchor_proof).
EXPECTED_OFF = {"AUTO_SELECT": 14, "REVIEW": 10, "ABSTAIN": 32, "ERROR": 2, "PLACED": 24}
PREDICTED_AXIS_ALONE = ["log15", "log16", "log27", "log45", "log72"]  # M8.7 READY set
PREDICTED_INCREMENT_OVER_M85 = ["log15", "log16", "log45", "log72"]   # log27 -> M8.5
PLACED = ("AUTO_SELECT", "REVIEW")
_RANK = {"ABSTAIN": 0, "ERROR": 0, "REVIEW": 1, "AUTO_SELECT": 2}


def _counts(statuses: List[str]) -> Dict[str, int]:
    c = {k: statuses.count(k) for k in ("AUTO_SELECT", "REVIEW", "ABSTAIN", "ERROR")}
    c["PLACED"] = c["AUTO_SELECT"] + c["REVIEW"]
    return c


def main() -> int:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    if not os.path.isfile(PDF) or not os.path.isdir(CORPUS_DIR):
        print("[m8.8] STOP: inputs missing")
        return 2
    corpus = enumerate_corpus(CORPUS_DIR)
    if len(corpus) != EXPECTED_COUNT:
        print(f"[m8.8] STOP: corpus drift ({len(corpus)})")
        return 3
    settings = Settings.for_proof()
    assert settings.station_axis_interval_optin is False, "for_proof() must keep the flag OFF"
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
            rows.append({"bore_id": p.stem.replace("bore_log", "log"), "off": "ERROR",
                         "axis": "ERROR", "axis_m85": "ERROR", "axis_m85_coll": "ERROR",
                         "error": f"{type(e).__name__}"})
            continue
        axis_sheets = sorted({x for r in bore.sheet_refs for x in (r - 1, r, r + 1) if x >= 1})
        axis_ctx = StationAxisContext(
            ticks_by_sheet={s: tuple(t for t in (parse_tick(w["text"])
                                                 for w in plan.words(s, offset))
                                     if t is not None) for s in axis_sheets},
            callouts=tuple(c for s in axis_sheets
                           for c in dialect.extract_callouts(plan, s, offset)))
        rev_ctx = ReverseAnchorContext(
            graph=graph, conflicts=conflicts, equations_by_sheet=eq_all)
        gate = CollisionGate(
            equations_by_sheet=collect_equations(plan, offset, bore.sheet_refs),
            human_grades=load_human_grades())
        off = run_match(bore, plan, dialect, offset)
        ax = run_match(bore, plan, dialect, offset, station_axis=axis_ctx)
        am = run_match(bore, plan, dialect, offset, station_axis=axis_ctx,
                       reverse_anchor=rev_ctx)
        amc = run_match(bore, plan, dialect, offset, station_axis=axis_ctx,
                        reverse_anchor=rev_ctx, collision_gate=gate)
        rows.append({
            "bore_id": bore.bore_id,
            "off": off.status.value, "axis": ax.status.value,
            "axis_m85": am.status.value, "axis_m85_coll": amc.status.value,
            "off_reason": off.reason, "axis_reason": ax.reason,
            "axis_m85_reason": am.reason,
            "axis_sheets": list(ax.sheets), "axis_caveats": list(ax.caveats),
            "axis_changed": (off.status != ax.status or off.reason != ax.reason
                             or list(off.sheets) != list(ax.sheets)),
        })
    plan.close()

    off_counts = _counts([r["off"] for r in rows])
    ax_counts = _counts([r["axis"] for r in rows])
    am_counts = _counts([r["axis_m85"] for r in rows])
    amc_counts = _counts([r["axis_m85_coll"] for r in rows])
    changed = [r for r in rows if r.get("axis_changed")]
    placed_changed = [r for r in changed if r["off"] in PLACED]
    newly_placed = [r for r in changed if r["off"] not in PLACED and r["axis"] in PLACED]
    promotions = [r for r in rows
                  if _RANK.get(r["axis"], 0) > _RANK.get(r["off"], 0) and r["axis"] == "AUTO_SELECT"]
    bad_new = [r for r in newly_placed
               if r["axis"] != "REVIEW" or r["axis_reason"] != "STATION_AXIS_INTERVAL_PATH"
               or "STATION_AXIS_INTERVAL_PATH" not in r["axis_caveats"]]
    empirical_axis = sorted(r["bore_id"] for r in changed)
    # the increment over M8.5: logs REVIEW in axis_m85 with the AXIS reason
    increment = sorted(r["bore_id"] for r in rows
                       if r["axis_m85"] == "REVIEW"
                       and r.get("axis_m85_reason") == "STATION_AXIS_INTERVAL_PATH")

    checks = {
        "off_matches_default": off_counts == EXPECTED_OFF,
        "axis_alone_set_matches_m87_proof": empirical_axis == sorted(PREDICTED_AXIS_ALONE),
        "increment_over_m85_matches": increment == sorted(PREDICTED_INCREMENT_OVER_M85),
        # 24 baseline + {log7,log27} via the reverse retry (runs first) + the
        # axis increment {log15,log16,log45,log72} = 30 distinct placements.
        # (29 was the pre-sweep estimate that assumed M8.8-alone would not also
        # cover log27 -- it does, per the M8.7 proof; no log places twice.)
        "combined_ceiling_30": am_counts["PLACED"] == 30,
        "zero_placed_logs_changed": not placed_changed,
        "zero_auto_promotions": not promotions,
        "all_new_placements_review_axis_reason": not bad_new,
    }
    verdict = "PASS" if all(checks.values()) else "FAILURE"

    report = {
        "milestone": "truelinev2 M8.8 -- station-axis interval opt-in OFF vs ON sweep",
        "flag": "TL2_STATION_AXIS_INTERVAL_OPTIN (Settings.station_axis_interval_optin, default OFF)",
        "off_counts": off_counts, "expected_off": EXPECTED_OFF,
        "axis_counts": ax_counts, "axis_m85_counts": am_counts,
        "axis_m85_coll_counts": amc_counts,
        "empirical_axis_alone_set": empirical_axis,
        "predicted_axis_alone": sorted(PREDICTED_AXIS_ALONE),
        "increment_over_m85": increment,
        "predicted_increment": sorted(PREDICTED_INCREMENT_OVER_M85),
        "placed_logs_changed": [r["bore_id"] for r in placed_changed],
        "auto_promotions": [r["bore_id"] for r in promotions],
        "checks": checks, "verdict": verdict, "rows": rows,
    }
    OUT_JSON.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    L = ["# M8.8 -- station-axis interval opt-in sweep", "",
         f"- OFF          : {off_counts} (expected {EXPECTED_OFF})",
         f"- AXIS ON      : {ax_counts}",
         f"- AXIS+M85     : {am_counts}",
         f"- AXIS+M85+COLL: {amc_counts}",
         f"- axis-alone changed set: **{empirical_axis}** (M8.7 proof predicted "
         f"{sorted(PREDICTED_AXIS_ALONE)})",
         f"- increment over M8.5: **{increment}** (predicted "
         f"{sorted(PREDICTED_INCREMENT_OVER_M85)}; log27 dedups to the M8.5 reverse retry)",
         f"- checks: {checks}", "",
         f"## VERDICT: {verdict}"]
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")

    print(f"[m8.8] OFF           {off_counts}")
    print(f"[m8.8] AXIS ON       {ax_counts}")
    print(f"[m8.8] AXIS+M85      {am_counts}")
    print(f"[m8.8] AXIS+M85+COLL {amc_counts}")
    print(f"[m8.8] axis-alone changed: {empirical_axis}")
    print(f"[m8.8] increment over M8.5: {increment}")
    print(f"[m8.8] checks={checks}")
    print(f"[m8.8] VERDICT: {verdict}")
    print(f"[m8.8] report -> {OUT_MD}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
