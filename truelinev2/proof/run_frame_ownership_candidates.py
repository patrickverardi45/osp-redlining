r"""M8.9 -- frame-ownership classification over the remaining abstain class.

Proof-only (nothing wired): reproduces the corrected baseline AND the combined
M8.5+M8.8 30-placed state as embedded gates, isolates the bores that STILL
abstain with FRAME_OR_SHEET_CONFLICT under the M8.7 solver, and classifies each
into the product-doctrine lanes (READY / pick-card suggestion / human-adjustable
redline / source review / unsafe-named) using M8.6 structure origins + M8.7 tick
ladders + print scope + HH-HH notes.

Run (repo root): $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_frame_ownership_candidates
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
from truelinev2.match.collision_gate import collect_equations
from truelinev2.match.engine import run_match
from truelinev2.match.reverse_anchor import ReverseAnchorContext
from truelinev2.match.station_axis_interval import StationAxisContext, prove_interval_path
from truelinev2.match.transition_classifier import conflict_sheet_pairs
from truelinev2.proof.frame_ownership_candidates import classify_frame_ownership
from truelinev2.proof.run_brenham_corpus import CORPUS_DIR, EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.station_equation_ownership import extract_reset_origins, parse_hh_distances
from truelinev2.service import _build_plan_frame_graph

OUT_JSON = _REPO_ROOT / "data" / "outputs" / "frame_ownership_candidates.json"
OUT_MD = _REPO_ROOT / "data" / "outputs" / "frame_ownership_candidates.md"

EXPECTED_OFF = {"AUTO_SELECT": 14, "REVIEW": 10, "ABSTAIN": 32, "ERROR": 2, "PLACED": 24}
EXPECTED_COMBINED_PLACED = 30


def main() -> int:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    if not os.path.isfile(PDF) or not os.path.isdir(CORPUS_DIR):
        print("[m8.9] STOP: inputs missing")
        return 2
    corpus = enumerate_corpus(CORPUS_DIR)
    if len(corpus) != EXPECTED_COUNT:
        print(f"[m8.9] STOP: corpus drift ({len(corpus)})")
        return 3
    settings = Settings.for_proof()
    plan = PlanPdf(PDF)
    dialect = select_dialect(plan)
    offset = dialect.calibrate(plan, settings.sheet_offset)
    graph = _build_plan_frame_graph(plan, offset)
    conflicts = conflict_sheet_pairs(graph)

    # --- gates: default baseline + combined M8.5+M8.8 30-placed ---------------
    off_statuses, combined = [], []
    remaining: List[Any] = []   # bores still ABSTAIN under combined flags
    for p in corpus:
        try:
            bore = load_borelog(str(p))
        except Exception:
            off_statuses.append("ERROR")
            combined.append("ERROR")
            continue
        axis_sheets = sorted({x for r in bore.sheet_refs for x in (r - 1, r, r + 1) if x >= 1})
        axis_ctx = StationAxisContext(
            ticks_by_sheet={s: tuple(t for t in (parse_tick(w["text"])
                                                 for w in plan.words(s, offset))
                                     if t is not None) for s in axis_sheets},
            callouts=tuple(c for s in axis_sheets
                           for c in dialect.extract_callouts(plan, s, offset)))
        rev_ctx = ReverseAnchorContext(
            graph=graph, conflicts=conflicts,
            equations_by_sheet=collect_equations(plan, offset, bore.sheet_refs))
        off_statuses.append(run_match(bore, plan, dialect, offset).status.value)
        both = run_match(bore, plan, dialect, offset, reverse_anchor=rev_ctx,
                         station_axis=axis_ctx)
        combined.append(both.status.value)
        if both.status.value == "ABSTAIN":
            remaining.append((bore, axis_ctx))
    off_counts = {k: off_statuses.count(k) for k in ("AUTO_SELECT", "REVIEW", "ABSTAIN", "ERROR")}
    off_counts["PLACED"] = off_counts["AUTO_SELECT"] + off_counts["REVIEW"]
    combined_placed = combined.count("AUTO_SELECT") + combined.count("REVIEW")
    if off_counts != EXPECTED_OFF or combined_placed != EXPECTED_COMBINED_PLACED:
        print(f"[m8.9] STOP: gate drift off={off_counts} combined_placed={combined_placed}")
        plan.close()
        return 4

    # --- isolate the FRAME_OR_SHEET_CONFLICT class, then classify -------------
    rows: List[Dict[str, Any]] = []
    for bore, ctx in remaining:
        m87 = prove_interval_path(
            bore_id=bore.bore_id, bore_start_ft=bore.station_start_ft,
            bore_end_ft=bore.station_end_ft, span_ft=bore.span_ft,
            ticks_by_sheet=dict(ctx.ticks_by_sheet), callouts=list(ctx.callouts),
            sheet_refs=list(bore.sheet_refs))
        if m87["result"] != "FRAME_OR_SHEET_CONFLICT":
            rows.append({"bore_id": bore.bore_id, "result": "OUT_OF_CLASS",
                         "m87_verdict": m87["result"]})
            continue
        sheets = sorted(ctx.ticks_by_sheet)
        origins = []
        hh_by_sheet = {}
        for s in sheets:
            lines = plan.lines(s, offset)
            origins.extend(extract_reset_origins(lines, s))
            notes = parse_hh_distances(" ".join(lines))
            if notes:
                hh_by_sheet[s] = notes
        verdict = classify_frame_ownership(
            bore_id=bore.bore_id, bore_start_ft=bore.station_start_ft,
            bore_end_ft=bore.station_end_ft, span_ft=bore.span_ft,
            ticks_by_sheet=dict(ctx.ticks_by_sheet), callouts=list(ctx.callouts),
            origins=origins, hh_notes_by_sheet=hh_by_sheet,
            sheet_refs=list(bore.sheet_refs),
            equations_by_sheet=collect_equations(plan, offset, sheets))
        rows.append(verdict)
    plan.close()

    by_verdict: Dict[str, List[str]] = {}
    for r in rows:
        by_verdict.setdefault(str(r["result"]), []).append(str(r["bore_id"]))

    report = {
        "milestone": "truelinev2 M8.9 -- frame ownership for local-frame bores (proof-only)",
        "default_sweep_reproduced": off_counts, "expected_off": EXPECTED_OFF,
        "combined_m85_m88_placed": combined_placed,
        "verdict_index": {k: sorted(v) for k, v in sorted(by_verdict.items())},
        "auto_promotions_possible": False,
        "rows": rows,
    }
    OUT_JSON.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    L = ["# M8.9 -- frame ownership candidates", "",
         f"- default baseline: {off_counts} (gate ok); combined M8.5+M8.8 placed: "
         f"{combined_placed} (gate ok)",
         f"- verdicts: " + ", ".join(f"{k}={len(v)}" for k, v in sorted(by_verdict.items())), ""]
    for r in rows:
        nm = r.get("named_missing_relationship", "")
        L.append(f"- {r['bore_id']}: **{r['result']}**"
                 + (f" -- {nm}" if nm else "")
                 + (f" [frames: {r.get('supported_frames')}]" if "supported_frames" in r else ""))
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")

    print(f"[m8.9] default {off_counts} (gate ok); combined placed {combined_placed} (gate ok)")
    print(f"[m8.9] classified {len(rows)} remaining abstains: "
          + ", ".join(f"{k}={len(v)}" for k, v in sorted(by_verdict.items())))
    for k, v in sorted(by_verdict.items()):
        print(f"[m8.9]   {k}: {sorted(v)}")
    print(f"[m8.9] report -> {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
