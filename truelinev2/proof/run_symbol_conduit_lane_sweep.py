r"""M8.14.c Phase 1 -- all-58 REVIEW-only lane census (dry-run / reporting).

Runs the default-OFF ``symbol_conduit_matchline`` lane over every production
bore and emits an honest classification census. This is a REPORTING gate:
the lane stays UNWIRED from engine/service; nothing is placed; the only
rendered artifacts are REVIEW strokes for bores the lane finds eligible
(visual-grading deliverables, NOT confirmed placements).

Honesty rules baked into the report:
  * STROKE_ELIGIBLE_REVIEW means every lane gate passed -- it does NOT mean
    human-graded. Old-geometry grades remain recorded separately; all four
    eligible design-path strokes are now graded PASS.
  * Bores whose SOURCE fails to parse are typed (the banked log37/38 adapter
    gap), never silently dropped and never counted as lane faults.
  * No status is ever AUTO (structural -- the lane has no AUTO).

Embedded gates (any failure -> nonzero exit):
  G1 all 58 bores enumerated; each yields a typed outcome (no crash)
  G2 census counts match the banked Phase-1 distribution exactly (drift -> loud)
  G3 graded bores under the adherence law: log51/log65 eligible (design-path
     geometry graded PASS); log7 abstains typed (parallel strands)
  G4 log50 stays PICK_CARD_WITH_END_ANCHOR
  G5 REVIEW-only + zero-false: every outcome review_only, no AUTO anywhere
  G6 exactly one REVIEW stroke PNG per eligible segment (canonical red); no
     PNG for any abstained/pick-card/error bore (structural)
  G7 the source-error bores are exactly {log37, log38} and typed as the banked
     adapter gap, not a lane fault

Outputs (gitignored): data/outputs/symbol_conduit_lane_sweep/

Run (repo root): $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_symbol_conduit_lane_sweep
"""
from __future__ import annotations

import collections
import json
import os
import re
from typing import Dict, List, Optional

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.structure_position import BRENHAM_LANE_DIALECT
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.match.symbol_conduit_lane import (
    LANE_NAME,
    S_CROSS_SHEET,
    S_DESIGN,
    S_ELIGIBLE,
    S_END_ONLY,
    S_END_POSITION,
    S_PICK,
    S_STRUCTURE_REQUIRED,
    S_UNPRINTED,
    resolve_bore,
)
from truelinev2.proof.run_brenham_corpus import EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.render.crop import render_redline_stroke
from truelinev2.service import _build_plan_frame_graph

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "symbol_conduit_lane_sweep"
S_SOURCE_ERR = "BORE_SOURCE_UNPARSEABLE"   # banked adapter gap, NOT a lane fault
GRADED = {"log7", "log51", "log65"}        # b.3 / b.7 / b.10 graded under the
                                           # OLD tick-chord geometry
# Patrick 2026-06-11: all four eligible DESIGN-PATH strokes graded PASS --
# route adherence formally ACCEPTED; their route geometry must not change.
DESIGN_GRADED = {"log25", "log51", "log59", "log65"}

# Banked census (M8.14.c.2 design-path adherence law applied; drift fails G2
# loudly so any change is examined, never silently absorbed). log7 moved
# STROKE_ELIGIBLE -> DESIGN_PATH_NOT_TRACEABLE: its conduit environment
# carries 4 physically distinct drawn strands and the lane never picks one
# (the law's typed cost; named missing = a strand discriminator).
EXPECT_CENSUS = {
    S_UNPRINTED: 25,
    S_CROSS_SHEET: 16,
    S_PICK: 5,
    S_END_POSITION: 5,
    S_ELIGIBLE: 4,
    S_DESIGN: 1,
    S_SOURCE_ERR: 2,
}
EXPECT_ELIGIBLE = {"log25", "log51", "log59", "log65"}
EXPECT_SOURCE_ERR = {"log37", "log38"}


def _num(p) -> int:
    m = re.search(r"(\d+)", p.stem)
    return int(m.group(1)) if m else 0


def _evidence_summary(out) -> Dict[str, Optional[str]]:
    """Compact start/end evidence + the lane component that stopped/succeeded."""
    by = {e.component: e for e in out.evidence}
    end = by.get("end_identity")
    end_pos = by.get("structure_position")
    start = by.get("start_identity") or by.get("conduit_origin")
    last = out.evidence[-1] if out.evidence else None
    return {
        "end_identity": (end.detail if end else None),
        "end_position": (end_pos.detail if end_pos else None),
        "start_evidence": (f"{start.component}/{start.result}: {start.detail}"
                           if start else None),
        "stopped_or_succeeded_at": (f"{last.component}/{last.result}"
                                    if last else None),
    }


def _markdown(census: Dict[str, int], rows: List[dict]) -> str:
    order = [S_ELIGIBLE, S_PICK, S_DESIGN, S_STRUCTURE_REQUIRED, S_CROSS_SHEET,
             S_END_POSITION, S_UNPRINTED, S_SOURCE_ERR]
    lines = ["# M8.14.c Phase 1 -- symbol_conduit_matchline all-58 census", "",
             f"Total bores: {sum(census.values())}  ·  lane: {LANE_NAME}  ·  "
             f"mode: REVIEW-only  ·  default-OFF (unwired)", "",
             "| count | classification |", "|---:|---|"]
    for k in order:
        if census.get(k):
            lines.append(f"| {census[k]} | `{k}` |")
    elig = [r for r in rows if r["status"] == S_ELIGIBLE]
    accepted = [r["bore_id"] for r in elig if r["bore_id"] in DESIGN_GRADED]
    pending = [r["bore_id"] for r in elig if r["bore_id"] not in DESIGN_GRADED]
    picks = [r["bore_id"] for r in rows if r["status"] == S_PICK]
    lines += [
        "", "## Stroke-eligible (REVIEW-only; design-path adherence law)",
        f"- design-path geometry GRADED PASS (route adherence ACCEPTED "
        f"2026-06-11): {', '.join(sorted(accepted, key=lambda s: int(s[3:]))) or 'none'}",
        f"- design-path geometry awaiting re-grade (old chord grades do not "
        f"transfer): {', '.join(sorted(pending, key=lambda s: int(s[3:]))) or 'none'}",
        "", "## Pick-card candidates (end-anchored, start refused)",
        f"- {', '.join(sorted(picks, key=lambda s: int(s[3:]))) or 'none'}",
        "", "## Common blockers",
        f"- `{S_UNPRINTED}` ({census.get(S_UNPRINTED, 0)}): end-structure note "
        f"not printed on any referenced sheet (no end anchor can exist)",
        f"- `{S_CROSS_SHEET}` ({census.get(S_CROSS_SHEET, 0)}): conduit run "
        f"exits the sheet or the matchline join is unproven -- needs the b.9 "
        f"cross-sheet join evidence",
        f"- `{S_END_POSITION}` ({census.get(S_END_POSITION, 0)}): end note "
        f"printed but its symbol could not be uniquely leader-traced",
        f"- `{S_DESIGN}` ({census.get(S_DESIGN, 0)}): drawn conduit present "
        f"but not uniquely traceable (log7: 4 physically distinct parallel "
        f"strands; named missing = a strand discriminator); a chord is never "
        f"drawn across a drawn route",
        f"- `{S_SOURCE_ERR}` ({census.get(S_SOURCE_ERR, 0)}): banked log37/38 "
        f"adapter station-format gap (NOT a lane fault)",
        "", "## Recommended next gate",
        "- Design-path grading debt is zero: all 4 eligible strokes are "
        "accepted. Reviewer-card payload integration remains outside this "
        "grade-banking change.",
        "- Targeted resolver expansions, by yield: cross-sheet continuation "
        "(16) via the b.9/b.10 matchline graph; the log7-class strand "
        "discriminator (re-unlocks its design-path stroke).",
    ]
    return "\n".join(lines)


def main() -> int:
    corpus_dir, how = resolve_corpus()
    print(f"[m8.14c-p1] corpus dir : {corpus_dir}  ({how})")
    if not os.path.isfile(PDF) or not os.path.isdir(corpus_dir):
        print("[m8.14c-p1] STOP: inputs missing")
        return 2
    corpus = sorted(enumerate_corpus(corpus_dir), key=_num)
    if len(corpus) != EXPECTED_COUNT:
        print(f"[m8.14c-p1] STOP: corpus drift ({len(corpus)})")
        return 3
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.png"):
        stale.unlink()  # structural G6: only THIS run's strokes may exist

    plan = PlanPdf(PDF)
    rows: List[dict] = []
    ok = True
    try:
        dialect = select_dialect(plan)
        offset = dialect.calibrate(plan, 13)
        graph = _build_plan_frame_graph(plan, offset)
        for p in corpus:
            try:
                bore = load_borelog(str(p))
            except Exception as exc:  # banked adapter gap (log37/38): typed, not a crash
                rows.append({"bore_id": p.stem.replace("bore_", ""),
                             "status": S_SOURCE_ERR, "sheets": None,
                             "stroke_eligible": False, "pngs": [],
                             "named_missing": (f"bore source did not parse "
                                               f"({type(exc).__name__}: "
                                               f"{str(exc)[:80]}) -- the banked "
                                               f"adapter station-format gap; "
                                               f"NOT a lane fault"),
                             "evidence": {}, "needs_grading": False})
                continue
            out = resolve_bore(plan, bore, offset, BRENHAM_LANE_DIALECT,
                               frame_graph=graph)
            pngs = []
            if out.status == S_ELIGIBLE:
                for seg in out.segments:  # canonical RED renderer, REVIEW dashed
                    png = render_redline_stroke(
                        plan, f"{out.bore_id}_lane", seg.sheet, offset,
                        seg.stroke_points, status="REVIEW",
                        reason=f"{LANE_NAME} census", out_dir=str(OUT_DIR))
                    pngs.append(png)
            rows.append({
                "bore_id": out.bore_id, "status": out.status,
                "sheets": sorted(set(bore.sheet_refs)),
                "span": f"{bore.station_start}->{bore.station_end}",
                "stroke_eligible": out.stroke_eligible,
                "segments": [s.to_dict() for s in out.segments],
                "pick_card_candidate": out.detail.get("candidate"),
                "named_missing": out.named_missing,
                "evidence": _evidence_summary(out),
                "pngs": pngs,
                "needs_grading": (out.status == S_ELIGIBLE
                                  and out.bore_id not in DESIGN_GRADED),
                # design-path geometry: all four eligible strokes graded PASS
                # and accepted; route geometry must not change
            })

        census = collections.Counter(r["status"] for r in rows)

        # G1 every bore typed
        g1 = len(rows) == EXPECTED_COUNT and all(r["status"] for r in rows)
        print(f"[m8.14c-p1] {'PASS' if g1 else 'FAIL'}  G1 all {len(rows)} "
              f"bores typed (no crash)")
        ok &= g1

        # G2 census matches the banked distribution exactly
        g2 = dict(census) == EXPECT_CENSUS
        print(f"[m8.14c-p1] {'PASS' if g2 else 'FAIL'}  G2 census == banked: "
              f"{dict(sorted(census.items()))}")
        if not g2:
            print(f"[m8.14c-p1]      expected: {dict(sorted(EXPECT_CENSUS.items()))}")
        ok &= g2

        by_id = {r["bore_id"]: r for r in rows}
        # M8.14.c.2: log51/log65 stay eligible (design-path geometry); log7
        # abstains typed -- its conduit environment has 4 parallel strands and
        # the lane never picks one (the adherence law's documented cost).
        g3 = (by_id["log51"]["status"] == S_ELIGIBLE
              and by_id["log65"]["status"] == S_ELIGIBLE
              and by_id["log7"]["status"] == S_DESIGN)
        print(f"[m8.14c-p1] {'PASS' if g3 else 'FAIL'}  G3 graded bores under "
              f"the adherence law: {[by_id[b]['status'] for b in sorted(GRADED)]}")
        ok &= g3

        g4 = by_id["log50"]["status"] == S_PICK
        print(f"[m8.14c-p1] {'PASS' if g4 else 'FAIL'}  G4 log50 pick-card: "
              f"{by_id['log50']['status']}")
        ok &= g4

        g5 = (all(r["status"] != S_ELIGIBLE or r["stroke_eligible"] for r in rows)
              and not any("AUTO" in r["status"] for r in rows))
        print(f"[m8.14c-p1] {'PASS' if g5 else 'FAIL'}  G5 REVIEW-only + "
              f"zero-false (no AUTO anywhere)")
        ok &= g5

        eligible_ids = {r["bore_id"] for r in rows if r["status"] == S_ELIGIBLE}
        want_pngs = sum(len(r["segments"]) for r in rows
                        if r["status"] == S_ELIGIBLE)
        pngs_on_disk = sorted(p.name for p in OUT_DIR.glob("*.png"))
        png_owners = {r["bore_id"] for r in rows if r["pngs"]}
        g6 = (eligible_ids == EXPECT_ELIGIBLE
              and len(pngs_on_disk) == want_pngs
              and png_owners == eligible_ids)
        print(f"[m8.14c-p1] {'PASS' if g6 else 'FAIL'}  G6 one red PNG per "
              f"eligible segment ({want_pngs}); eligible={sorted(eligible_ids, key=lambda s: int(s[3:]))}")
        ok &= g6

        err_ids = {r["bore_id"] for r in rows if r["status"] == S_SOURCE_ERR}
        g7 = err_ids == EXPECT_SOURCE_ERR
        print(f"[m8.14c-p1] {'PASS' if g7 else 'FAIL'}  G7 source-error bores "
              f"== banked adapter gap: {sorted(err_ids)}")
        ok &= g7

        md = _markdown(dict(census), rows)
        report = {
            "milestone": ("truelinev2 M8.14.c Phase 1 -- symbol/conduit/"
                          "matchline all-58 REVIEW-only census"),
            "lane": LANE_NAME, "mode": "REVIEW_ONLY",
            "flag": "TL2_SYMBOL_CONDUIT_LANE_OPTIN (default OFF; lane UNWIRED)",
            "corpus_dir_used": corpus_dir, "corpus_resolution": how,
            "plan_pdf": PDF, "verdict": "PASS" if ok else "FAILURE",
            "honesty": ("eligible == every lane gate passed; design-path "
                        "geometry for log25/log51/log59/log65 is GRADED PASS "
                        "(route adherence formally ACCEPTED 2026-06-11; "
                        "geometry must not change); log7 abstains typed "
                        "(parallel strands); source-parse failures are typed "
                        "(banked adapter gap), never lane faults; no AUTO; "
                        "lane unwired; marker rings are curve-thinned for "
                        "legibility -- geometry/payloads untouched"),
            "census": dict(sorted(census.items())),
            "design_grades_accepted": sorted(DESIGN_GRADED,
                                             key=lambda s: int(s[3:])),
            "design_grading_debt": sum(1 for r in rows if r["needs_grading"]),
            "eligible_needs_regrade": sorted(
                (r["bore_id"] for r in rows if r["needs_grading"]),
                key=lambda s: int(s[3:])),
            "graded_under_old_geometry": sorted(GRADED),
            "summary_markdown": md,
            "bores": rows,
        }
        (OUT_DIR / "symbol_conduit_lane_sweep.json").write_text(
            json.dumps(report, indent=2, default=str), encoding="utf-8")
        print("\n" + md + "\n")
        print(f"[m8.14c-p1] verdict: {report['verdict']}")
        print(f"[m8.14c-p1] report -> {OUT_DIR / 'symbol_conduit_lane_sweep.json'}")
    finally:
        plan.close()
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
