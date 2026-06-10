r"""M8.14.a-r2 -- first honest route-following redline stroke (clean-ladder proof).

The product deliverable, drawn for the first time from clean evidence: a red
stroke along the design route between the bore-log start and end stations,
derived ONLY from v2 placement truth + clean positioned route-ladder ticks
(all-tick text blocks; callout/note station tokens excluded -- the M8.14.a
zig-zag lesson). v1 donated rendering STYLE only; no v1 import, no v1
placement copied.

Targets (the r2 decision -- do not force what needs the bigger solver):
  log45 -- REVIEW (M8.8 station-axis), sheet 10, 43+50 -> 44+89: the ONLY
           single-sheet placed bore whose span is covered by clean drawn
           ladder ticks alone -> MUST render a DASHED red stroke.
  log51 -- AUTO, sheet 8, 0+00 -> 2+99: start is a local-frame origin owned
           by an UNPRINTED/implicit structure -> MUST abstain
           STRUCTURE_IDENTITY_BINDING_REQUIRED (banked, not failed).
  log7  -- REVIEW (M8.5), sheet 10, 0+55 -> 4+51: three rival =0+00 installer
           HHs; metric gates can bind the WRONG one -> MUST abstain
           STRUCTURE_IDENTITY_BINDING_REQUIRED (banked, not failed).

Embedded gates (any failure -> nonzero exit, no force-green):
  G1 placements reproduce (log45 REVIEW/STATION_AXIS_INTERVAL_PATH/[10];
     log51 AUTO/[8]; log7 REVIEW/REVERSE_ENDPOINT_ANCHOR/[10])
  G2 clean-tick classification counts reported per sheet (raw / excluded
     callout+note tokens / clean ladder ticks)
  G3 log45: TICK_PATH_READY, exactly one stroke, endpoints bracketed +
     interpolated from the ladder, and NO stroke point inside ANY extracted
     callout bbox (belt-and-braces on top of the block classifier)
  G4 log51 + log7: STRUCTURE_IDENTITY_BINDING_REQUIRED with named relationship
  G5 log45 PNG rendered (dashed REVIEW) + resolves; output dir contains
     EXACTLY ONE stroke PNG (abstains/suggestions never render -- structural)

Outputs (gitignored): data/outputs/redline_stroke_proof/ -- the log45 PNG is
for Patrick's VISUAL GRADING against the plan before any wider rollout.

Run (repo root): $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_redline_stroke_proof
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.station_axis import parse_tick
from truelinev2.extract.tick_path import (
    READY,
    STRUCTURE_REQUIRED,
    route_ladder_ticks,
    solve_tick_path,
)
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.match.collision_gate import collect_all_sheet_equations
from truelinev2.match.engine import run_match
from truelinev2.match.reverse_anchor import ReverseAnchorContext
from truelinev2.match.station_axis_interval import StationAxisContext
from truelinev2.match.transition_classifier import conflict_sheet_pairs
from truelinev2.proof.run_brenham_corpus import EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.render.crop import render_redline_stroke
from truelinev2.service import _build_plan_frame_graph

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "redline_stroke_proof"

# (bore stem, want status, want reason, want sheet, want tick-path result)
TARGETS = (
    ("bore_log45", "REVIEW", "STATION_AXIS_INTERVAL_PATH", 10, READY),
    ("bore_log51", "AUTO_SELECT", None, 8, STRUCTURE_REQUIRED),
    ("bore_log7", "REVIEW", "REVERSE_ENDPOINT_ANCHOR", 10, STRUCTURE_REQUIRED),
)


def _inside(pt, bbox, m: float = 4.0) -> bool:
    return (bbox and bbox[0] - m <= pt[0] <= bbox[2] + m
            and bbox[1] - m <= pt[1] <= bbox[3] + m)


def main() -> int:
    corpus_dir, how = resolve_corpus()
    print(f"[m8.14a-r2] corpus dir : {corpus_dir}  ({how})")
    if not os.path.isfile(PDF) or not os.path.isdir(corpus_dir):
        print("[m8.14a-r2] STOP: inputs missing")
        return 2
    corpus = {p.stem: p for p in enumerate_corpus(corpus_dir)}
    if len(corpus) != EXPECTED_COUNT:
        print(f"[m8.14a-r2] STOP: corpus drift ({len(corpus)})")
        return 3
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.png"):
        stale.unlink()  # structural G5: only THIS run's strokes may exist

    plan = PlanPdf(PDF)
    rows: List[Dict] = []
    ok = True
    try:
        dialect = select_dialect(plan)
        offset = dialect.calibrate(plan, 13)
        graph = _build_plan_frame_graph(plan, offset)
        rev_ctx = ReverseAnchorContext(
            graph=graph, conflicts=conflict_sheet_pairs(graph),
            equations_by_sheet=collect_all_sheet_equations(plan, offset))
        for stem, want_status, want_reason, want_sheet, want_result in TARGETS:
            bore = load_borelog(str(corpus[stem]))
            axis_sheets = sorted({x for r in bore.sheet_refs
                                  for x in (r - 1, r, r + 1) if x >= 1})
            axis_ctx = StationAxisContext(
                ticks_by_sheet={s: tuple(t for t in (parse_tick(w["text"])
                                                     for w in plan.words(s, offset))
                                         if t is not None) for s in axis_sheets},
                callouts=tuple(c for s in axis_sheets
                               for c in dialect.extract_callouts(plan, s, offset)))
            pl = run_match(bore, plan, dialect, offset,
                           reverse_anchor=rev_ctx, station_axis=axis_ctx)
            g1 = (pl.status.value == want_status
                  and (want_reason is None or pl.reason == want_reason)
                  and pl.sheets == [want_sheet])
            print(f"[m8.14a-r2] {'PASS' if g1 else 'FAIL'}  G1 {bore.bore_id}: "
                  f"{pl.status.value}/{pl.reason} sheets={pl.sheets}")
            ok &= g1

            ticks, counts = route_ladder_ticks(plan, want_sheet, offset)
            print(f"[m8.14a-r2] G2 {bore.bore_id} s{want_sheet} tick counts: "
                  f"raw={counts['raw_tick_tokens']} "
                  f"excluded_text={counts['excluded_text_tokens']} "
                  f"clean_ladder={counts['clean_ladder_ticks']}")
            verdict = solve_tick_path(
                bore_id=bore.bore_id, sheet=want_sheet,
                start_ft=bore.station_start_ft, end_ft=bore.station_end_ft,
                ticks=ticks)
            g34 = verdict.result == want_result
            print(f"[m8.14a-r2] {'PASS' if g34 else 'FAIL'}  "
                  f"{'G3' if want_result == READY else 'G4'} {bore.bore_id}: "
                  f"{verdict.result} (want {want_result}) "
                  f"endpoint={verdict.endpoint_type}")
            if verdict.named_missing_relationship:
                print(f"[m8.14a-r2]      named: "
                      f"{verdict.named_missing_relationship[:150]}")
            ok &= g34

            png = None
            if verdict.result == READY and g34:
                callout_boxes = [c.bbox for c in
                                 dialect.extract_callouts(plan, want_sheet, offset)
                                 if c.bbox]
                polluted = [p for p in verdict.stroke_points
                            if any(_inside(p, b) for b in callout_boxes)]
                g3b = not polluted and verdict.strokes_found == 1
                print(f"[m8.14a-r2] {'PASS' if g3b else 'FAIL'}  G3 {bore.bore_id}: "
                      f"unique stroke, {len(verdict.stroke_points)} points, "
                      f"callout-contained points={len(polluted)}, "
                      f"chain={[(t.station_ft, round(t.x), round(t.y)) for t in verdict.chain]}, "
                      f"scales={[round(s, 2) for s in verdict.hop_scales]}")
                ok &= g3b
                png = render_redline_stroke(
                    plan, bore.bore_id, want_sheet, offset, verdict.stroke_points,
                    status=pl.status.value, reason=pl.reason, out_dir=str(OUT_DIR),
                    evidence_bboxes=[c.bbox for c in pl.matched_callouts if c.bbox])
                g5 = png is not None and Path(png).is_file()
                print(f"[m8.14a-r2] {'PASS' if g5 else 'FAIL'}  G5 {bore.bore_id}: {png}")
                ok &= g5
            rows.append({
                "bore_id": bore.bore_id, "status": pl.status.value,
                "reason": pl.reason, "sheet": want_sheet,
                "span": f"{bore.station_start}->{bore.station_end}",
                "stroke_style": ("dashed (REVIEW)" if pl.status.value == "REVIEW"
                                 else "solid (AUTO)") if png else "none (abstained)",
                "tick_counts": counts, "tick_path": verdict.to_dict(), "png": png,
            })
    finally:
        plan.close()

    pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
    expected_pngs = sum(1 for t in TARGETS if t[4] == READY)
    g5b = len(pngs) == expected_pngs
    print(f"[m8.14a-r2] {'PASS' if g5b else 'FAIL'}  G5 structural: exactly "
          f"{expected_pngs} stroke PNG on disk -> {pngs} "
          f"(abstains/suggestions never render)")
    ok &= g5b

    report = {
        "milestone": ("truelinev2 M8.14.a-r2 -- first honest route-following "
                      "redline stroke (clean-ladder proof; visual grading required)"),
        "corpus_dir_used": corpus_dir, "corpus_resolution": how, "plan_pdf": PDF,
        "verdict": "PASS" if ok else "FAILURE",
        "honesty": ("stroke geometry = v2 placement + clean route-ladder ticks "
                    "(all-tick blocks; callout/note tokens excluded); "
                    "route-following at station-tick resolution; structure-owned "
                    "endpoints ABSTAIN pending the structure-identity binding "
                    "solver; v1 donated style only"),
        "targets": rows,
    }
    (OUT_DIR / "redline_stroke_proof.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[m8.14a-r2] verdict: {report['verdict']}")
    print("[m8.14a-r2] VISUAL GRADING FILE for Patrick:")
    for r in rows:
        if r["png"]:
            print(f"[m8.14a-r2]   {r['bore_id']:>6} {r['stroke_style']:<16} -> {r['png']}")
    print(f"[m8.14a-r2] report -> {OUT_DIR / 'redline_stroke_proof.json'}")
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
