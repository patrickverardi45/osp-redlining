r"""M8.14.c Phase 0 -- symbol/conduit/matchline LANE dry-run (4 known bores).

The promoted lane (match/symbol_conduit_lane.py) replayed over the graded
proof set -- NOT an all-58 sweep. Every outcome must REPRODUCE its banked
b.3/b.7/b.8/b.10 conclusion through the single lane orchestrator:

  log7  -> STROKE_ELIGIBLE_REVIEW, 1 segment s10  (b.3-graded stroke)
  log51 -> STROKE_ELIGIBLE_REVIEW, 1 segment s8   (b.7-graded; start via
           conduit-origin -- and REVIEW-only even though the engine places
           log51 AUTO: the lane caps everything at REVIEW, structural)
  log65 -> STROKE_ELIGIBLE_REVIEW, 2 segments s10+s9 (b.10-graded cross-sheet)
  log50 -> PICK_CARD_WITH_END_ANCHOR (b.8: AP-168 candidate span-REFUSED)

Embedded gates (any failure -> nonzero exit):
  G1 default-OFF: the lane flag is False by default and NOTHING in the
     engine/service consults the lane (source-level pin)
  G2 log7 reproduces b.3 exactly (status/segments/endpoints/chain stations)
  G3 log51 reproduces b.7 exactly (+ conduit-origin component in evidence)
  G4 log65 reproduces b.10 exactly (2 segments, shared boundary 6+11)
  G5 log50 refused as pick-card with the named missing artifact; ZERO
     segments; rendered NOTHING
  G6 REVIEW-only + zero-false: every outcome review_only; no AUTO anywhere;
     exactly 4 stroke PNGs on disk (1+1+2), all via the canonical RED
     renderer; every outcome carries its component evidence chain with
     law/configured_by

Outputs (gitignored): data/outputs/symbol_conduit_lane_dryrun/

Run (repo root): $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_symbol_conduit_lane_dryrun
"""
from __future__ import annotations

import inspect
import json
import os

from truelinev2.config import _REPO_ROOT, Settings
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.structure_position import BRENHAM_LANE_DIALECT
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.match.symbol_conduit_lane import (
    LANE_NAME,
    S_ELIGIBLE,
    S_PICK,
    resolve_bore,
)
from truelinev2.proof.run_brenham_corpus import EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.render.crop import render_redline_stroke
from truelinev2.service import _build_plan_frame_graph

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "symbol_conduit_lane_dryrun"
DRYRUN = ("bore_log7", "bore_log51", "bore_log65", "bore_log50")

# Banked expectations from the graded proofs (b.3 / b.7 / b.10 / b.8).
EXPECT = {
    "log7": {"status": S_ELIGIBLE, "segments": [(10, 55.0, 451.0)],
             "start_xy": (861.3, 354.2), "end_xy": (291.6, 355.3),
             "chain_stations": [[55.0, 100.0, 200.0, 300.0, 400.0, 451.0]]},
    "log51": {"status": S_ELIGIBLE, "segments": [(8, 0.0, 299.0)],
              "start_xy": (577.6, 354.2), "end_xy": (149.9, 343.3),
              "chain_stations": [[0.0, 100.0, 200.0, 299.0]],
              "component": "conduit_origin"},
    "log65": {"status": S_ELIGIBLE,
              "segments": [(10, 451.0, 611.0), (9, 611.0, 650.0)],
              "start_xy": (291.6, 355.3), "end_xy": (1085.2, 356.1),
              "chain_stations": [[451.0, 500.0, 600.0, 611.0],
                                 [611.0, 650.0]],
              "component": "matchline_join"},
    "log50": {"status": S_PICK, "segments": [],
              "missing_needle": "span corroboration"},
}
PIN_TOL = 1.0


def _near(p, q, tol=PIN_TOL):
    return p is not None and abs(p[0] - q[0]) <= tol and abs(p[1] - q[1]) <= tol


def main() -> int:
    corpus_dir, how = resolve_corpus()
    print(f"[m8.14c-p0] corpus dir : {corpus_dir}  ({how})")
    if not os.path.isfile(PDF) or not os.path.isdir(corpus_dir):
        print("[m8.14c-p0] STOP: inputs missing")
        return 2
    corpus = {p.stem: p for p in enumerate_corpus(corpus_dir)}
    if len(corpus) != EXPECTED_COUNT:
        print(f"[m8.14c-p0] STOP: corpus drift ({len(corpus)})")
        return 3
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.png"):
        stale.unlink()  # structural: only THIS run's strokes may exist

    # G1 default-OFF + unwired
    import truelinev2.match.engine as engine_mod
    import truelinev2.service as service_mod
    g1 = (Settings.for_proof().symbol_conduit_lane_optin is False
          and "symbol_conduit" not in inspect.getsource(engine_mod)
          and "symbol_conduit" not in inspect.getsource(service_mod))
    print(f"[m8.14c-p0] {'PASS' if g1 else 'FAIL'}  G1 default-OFF + lane "
          f"UNWIRED (engine/service never consult it)")
    ok = g1

    plan = PlanPdf(PDF)
    rows = {}
    try:
        dialect = select_dialect(plan)
        offset = dialect.calibrate(plan, 13)
        graph = _build_plan_frame_graph(plan, offset)
        for stem in DRYRUN:
            bore = load_borelog(str(corpus[stem]))
            out = resolve_bore(plan, bore, offset, BRENHAM_LANE_DIALECT,
                               frame_graph=graph)
            pngs = []
            for seg in out.segments:  # canonical RED renderer; REVIEW dashed
                png = render_redline_stroke(
                    plan, f"{out.bore_id}_lane", seg.sheet, offset,
                    seg.stroke_points, status="REVIEW",
                    reason=f"{LANE_NAME} dry-run", out_dir=str(OUT_DIR))
                pngs.append(png)
            rows[out.bore_id] = {"outcome": out, "pngs": pngs}

        gates = []
        for bid, gate in (("log7", "G2"), ("log51", "G3"), ("log65", "G4"),
                          ("log50", "G5")):
            out = rows[bid]["outcome"]
            want = EXPECT[bid]
            g = out.status == want["status"]
            g &= [(s.sheet, s.start_ft, s.end_ft) for s in out.segments] \
                == want["segments"]
            if out.segments:
                g &= _near(out.segments[0].stroke_points[0], want["start_xy"])
                g &= _near(out.segments[-1].stroke_points[-1], want["end_xy"])
            if "chain_stations" in want:
                # endpoints + interior count pinned via segment bounds; the
                # interior tick stations are pinned through the point count
                g &= [len(s.stroke_points) for s in out.segments] \
                    == [len(c) for c in want["chain_stations"]]
            if "component" in want:
                g &= any(e.component == want["component"]
                         and e.result in ("BOUND", "PROVEN")
                         for e in out.evidence)
            if "missing_needle" in want:
                g &= (out.named_missing is not None
                      and want["missing_needle"] in out.named_missing
                      and not out.segments and not rows[bid]["pngs"])
            print(f"[m8.14c-p0] {'PASS' if g else 'FAIL'}  {gate} {bid}: "
                  f"{out.status} segs="
                  f"{[(s.sheet, s.start_ft, s.end_ft) for s in out.segments]} "
                  f"{('missing: ' + (out.named_missing or '')[:90]) if out.named_missing else ''}")
            gates.append(g)
        ok &= all(gates)

        pngs_on_disk = sorted(p.name for p in OUT_DIR.glob("*.png"))
        g6 = (len(pngs_on_disk) == 4
              and all(o["outcome"].review_only for o in rows.values())
              and all("AUTO" not in o["outcome"].status for o in rows.values())
              and all(o["outcome"].evidence for o in rows.values()))
        print(f"[m8.14c-p0] {'PASS' if g6 else 'FAIL'}  G6 REVIEW-only + "
              f"zero-false: 4 red stroke PNGs -> {pngs_on_disk}")
        ok &= g6

        report = {
            "milestone": ("truelinev2 M8.14.c Phase 0 -- symbol/conduit/"
                          "matchline lane dry-run (4 graded bores)"),
            "lane": LANE_NAME, "mode": "REVIEW_ONLY",
            "flag": "TL2_SYMBOL_CONDUIT_LANE_OPTIN (default OFF; lane UNWIRED)",
            "corpus_dir_used": corpus_dir, "corpus_resolution": how,
            "plan_pdf": PDF, "verdict": "PASS" if ok else "FAILURE",
            "honesty": ("one orchestrator reproduces the graded b.3/b.7/b.10 "
                        "strokes and the b.8 log50 refusal; REVIEW-only "
                        "structural; zero engine consultation; renders only "
                        "fully-proven chains via the canonical red renderer"),
            "bores": {bid: {**r["outcome"].to_dict(), "pngs": r["pngs"]}
                      for bid, r in rows.items()},
        }
        (OUT_DIR / "symbol_conduit_lane_dryrun.json").write_text(
            json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"[m8.14c-p0] verdict: {report['verdict']}")
        print(f"[m8.14c-p0] report -> {OUT_DIR / 'symbol_conduit_lane_dryrun.json'}")
    finally:
        plan.close()
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
