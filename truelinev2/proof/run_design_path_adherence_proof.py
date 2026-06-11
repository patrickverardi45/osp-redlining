r"""M8.14.c.2 -- design-path adherence proof (the graded-FAIL correction).

Patrick's correction (2026-06-11): the log25/log59 lane strokes were graded
FAIL -- the red stroke CHORDED between station ticks instead of following the
drawn design/conduit line (log25's drawn route detours through an HH and
follows a curved street; the chord cut both). THE LAW: a redline follows the
drawn design line; ticks constrain progress but never replace route geometry;
when the design path cannot be traced uniquely, the stroke abstains -- a
chord is never drawn across a drawn route.

This proof pins the correction on the failing bores:

  G1 the lane reproduces both bores STROKE_ELIGIBLE_REVIEW with the
     design_path component TRACED (anchor-seeded walk, welded pieces,
     jitter-equivalence, length + tick gates)
  G2 CHORD REGRESSION (the graded failure, made permanent): the OLD
     tick-chord stroke deviates >= CHORD_FAIL_PT from the traced design path
     for log25 (the curve + detour) -- and the NEW stroke max-deviates from
     the drawn conduit pieces by <= PATH_FIT_PT (it IS the drawn line)
  G3 log25's stroke follows the DRAWN ROUTE structure: a vertex within
     JOINT_PT of the detour structure HH(252.3,389.3); a vertex within
     JOINT_PT of the curve bottom (562.7,446.4); class handoff at
     HH(424.7,379.2) is on the path
  G4 endpoint evidence conclusions UNALTERED: both strokes start/end exactly
     on the b-series anchors
  G5 the law's honest cost is typed: log7's conduit environment carries 4
     physically distinct drawn strands (max dev 12.7 pt) -> the lane now
     abstains DESIGN_PATH_NOT_TRACEABLE for log7 (named missing: a strand
     discriminator); a chord is no longer drawn there
  G6 exactly TWO corrected stroke PNGs (canonical red, REVIEW dashed) --
     banked visual-grade artifacts

Outputs (gitignored): data/outputs/design_path_adherence/

Run (repo root): $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_design_path_adherence_proof
"""
from __future__ import annotations

import json
import math
import os

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.design_path import (
    conduit_pieces,
    point_to_polyline,
)
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.structure_position import BRENHAM_LANE_DIALECT
from truelinev2.extract.tick_path import READY, Tick, route_ladder_ticks, solve_tick_path
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.match.symbol_conduit_lane import (
    S_DESIGN,
    S_ELIGIBLE,
    resolve_bore,
)
from truelinev2.proof.run_brenham_corpus import EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.render.crop import render_redline_stroke
from truelinev2.service import _build_plan_frame_graph

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "design_path_adherence"
CHORD_FAIL_PT = 20.0   # the chord must measurably CUT the drawn route (log25)
PATH_FIT_PT = 4.0      # the new stroke must BE the drawn line (sub-dash scale)
JOINT_PT = 6.0         # drawn-route landmarks the stroke must pass through
DETOUR_HH = (252.3, 389.3)
HANDOFF_HH = (424.7, 379.2)
CURVE_BOTTOM = (562.7, 446.4)

# BANKED VISUAL GRADES (Patrick, 2026-06-11): the corrected design-path
# strokes for log25, log51, log59, and log65 were re-graded PASS for
# design-line adherence / curved route tracing -- the redline follows the
# actual drawn route and the route GEOMETRY must not change. (The later
# marker-density thinning is a render-legibility rule only; geometry/payloads
# untouched.)
PATRICK_DESIGN_GRADES = {
    "log25": "PASS",
    "log51": "PASS",
    "log59": "PASS",
    "log65": "PASS",
}


def main() -> int:
    corpus_dir, how = resolve_corpus()
    print(f"[m8.14c2] corpus dir : {corpus_dir}  ({how})")
    if not os.path.isfile(PDF) or not os.path.isdir(corpus_dir):
        print("[m8.14c2] STOP: inputs missing")
        return 2
    corpus = {p.stem: p for p in enumerate_corpus(corpus_dir)}
    if len(corpus) != EXPECTED_COUNT:
        print(f"[m8.14c2] STOP: corpus drift ({len(corpus)})")
        return 3
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.png"):
        stale.unlink()

    plan = PlanPdf(PDF)
    ok = True
    try:
        dialect = select_dialect(plan)
        offset = dialect.calibrate(plan, 13)
        graph = _build_plan_frame_graph(plan, offset)

        outs = {}
        for stem in ("bore_log25", "bore_log51", "bore_log59", "bore_log65",
                     "bore_log7"):
            bore = load_borelog(str(corpus[stem]))
            outs[bore.bore_id] = (bore, resolve_bore(
                plan, bore, offset, BRENHAM_LANE_DIALECT, frame_graph=graph))

        # G1 both failing bores now trace
        g1 = True
        for bid in ("log25", "log59"):
            out = outs[bid][1]
            traced = any(e.component == "design_path" and e.result == "TRACED"
                         and "design path TRACED" in e.detail
                         for e in out.evidence)
            g1 &= out.status == S_ELIGIBLE and traced and len(out.segments) == 1
            print(f"[m8.14c2] {'PASS' if out.status == S_ELIGIBLE and traced else 'FAIL'}"
                  f"  G1 {bid}: {out.status}, "
                  f"{len(out.segments[0].stroke_points) if out.segments else 0} "
                  f"stroke points")
        ok &= g1

        # G2 chord regression on log25: old chord cut the route; new stroke IS it
        bore25, out25 = outs["log25"]
        seg25 = out25.segments[0]
        new_pts = list(seg25.stroke_points)
        ticks, _ = route_ladder_ticks(plan, seg25.sheet, offset)
        anchors = [Tick(bore25.station_start_ft, *new_pts[0]),
                   Tick(bore25.station_end_ft, *new_pts[-1])]
        chord_v = solve_tick_path(bore_id="log25_chord", sheet=seg25.sheet,
                                  start_ft=bore25.station_start_ft,
                                  end_ft=bore25.station_end_ft,
                                  ticks=list(ticks) + anchors)
        chord_pts = list(chord_v.stroke_points) if chord_v.result == READY else []
        # the graded failure: the chord SEGMENTS cut the drawn route -- measure
        # how far the route's vertices sit from the chord polyline
        chord_dev = max(point_to_polyline(p, chord_pts) for p in new_pts) \
            if chord_pts else None
        pieces = conduit_pieces(plan.line_items(seg25.sheet, offset),
                                BRENHAM_LANE_DIALECT.path_layers)
        # honest fit: every interior stroke vertex within PATH_FIT_PT of SOME piece
        interior = new_pts[1:-1]
        fits = [min(point_to_polyline(v, list(pc.points)) for pc in pieces)
                for v in interior]
        fit_max = round(max(fits), 1) if fits else 0.0
        g2 = (chord_dev is not None and chord_dev >= CHORD_FAIL_PT
              and fit_max <= PATH_FIT_PT)
        print(f"[m8.14c2] {'PASS' if g2 else 'FAIL'}  G2 chord regression: old "
              f"chord deviates {round(chord_dev, 1) if chord_dev else None} pt "
              f">= {CHORD_FAIL_PT} from the traced path; new stroke fits the "
              f"drawn pieces within {fit_max} pt <= {PATH_FIT_PT}")
        ok &= g2

        # G3 drawn-route structure landmarks on the log25 stroke
        def near_vertex(lm):
            return min(math.hypot(v[0] - lm[0], v[1] - lm[1]) for v in new_pts)
        d_detour, d_handoff, d_curve = (near_vertex(DETOUR_HH),
                                        near_vertex(HANDOFF_HH),
                                        near_vertex(CURVE_BOTTOM))
        g3 = (d_detour <= JOINT_PT and d_handoff <= JOINT_PT
              and d_curve <= JOINT_PT)
        print(f"[m8.14c2] {'PASS' if g3 else 'FAIL'}  G3 log25 follows the "
              f"drawn route: detour HH {round(d_detour, 1)} pt, class-handoff "
              f"HH {round(d_handoff, 1)} pt, curve bottom {round(d_curve, 1)} "
              f"pt (all <= {JOINT_PT})")
        ok &= g3

        # G4 endpoint conclusions unaltered
        bore59, out59 = outs["log59"]
        seg59 = out59.segments[0]
        g4 = (math.hypot(new_pts[0][0] - 178.2, new_pts[0][1] - 360.0) <= 1.0
              and math.hypot(new_pts[-1][0] - 623.1, new_pts[-1][1] - 417.4) <= 1.0
              and math.hypot(seg59.stroke_points[-1][0] - 492.5,
                             seg59.stroke_points[-1][1] - 311.6) <= 1.0)
        print(f"[m8.14c2] {'PASS' if g4 else 'FAIL'}  G4 endpoints unaltered: "
              f"log25 {new_pts[0]}->{new_pts[-1]}; log59 end "
              f"{seg59.stroke_points[-1]}")
        ok &= g4

        # G5 the law's honest cost: log7 abstains on real parallel strands
        out7 = outs["log7"][1]
        g5 = (out7.status == S_DESIGN and not out7.segments
              and "strand discriminator" in (out7.named_missing or ""))
        print(f"[m8.14c2] {'PASS' if g5 else 'FAIL'}  G5 log7 typed abstain: "
              f"{out7.status} -- {(out7.named_missing or '')[:110]}")
        ok &= g5

        # G6 graded artifacts (canonical red, REVIEW dashed). Structure
        # landmarks keep their marker rings through curve thinning.
        landmarks = {"log25": (DETOUR_HH, HANDOFF_HH), "log59": ()}
        pngs = []
        for bid in ("log25", "log59"):
            seg = outs[bid][1].segments[0]
            pngs.append(render_redline_stroke(
                plan, f"{bid}_design_path", seg.sheet, offset,
                seg.stroke_points, status="REVIEW",
                reason="design-path adherence (M8.14.c.2; graded PASS)",
                out_dir=str(OUT_DIR), mandatory_points=landmarks[bid]))
        on_disk = sorted(p.name for p in OUT_DIR.glob("*.png"))
        g6 = all(pngs) and len(on_disk) == 2
        print(f"[m8.14c2] {'PASS' if g6 else 'FAIL'}  G6 exactly two corrected "
              f"PNGs: {on_disk}")
        ok &= g6

        # G7 the banked grades are formal: all four eligible bores carry a
        # PATRICK PASS for design-line adherence and reproduce eligible.
        g7 = (set(PATRICK_DESIGN_GRADES)
              == {"log25", "log51", "log59", "log65"}
              and all(v == "PASS" for v in PATRICK_DESIGN_GRADES.values())
              and all(outs[b][1].status == S_ELIGIBLE
                      for b in PATRICK_DESIGN_GRADES))
        print(f"[m8.14c2] {'PASS' if g7 else 'FAIL'}  G7 banked grades formal: "
              f"{PATRICK_DESIGN_GRADES} (route geometry is ACCEPTED and must "
              f"not change)")
        ok &= g7

        report = {
            "milestone": ("truelinev2 M8.14.c.2 -- design-path adherence "
                          "(graded-FAIL correction; all four eligible design "
                          "paths GRADED PASS 2026-06-11)"),
            "patrick_design_grades": PATRICK_DESIGN_GRADES,
            "corpus_dir_used": corpus_dir, "corpus_resolution": how,
            "plan_pdf": PDF, "verdict": "PASS" if ok else "FAILURE",
            "honesty": ("strokes now FOLLOW the drawn conduit route (welded-"
                        "piece walk, jitter-equivalence, length + tick gates); "
                        "ticks constrain, never define geometry; chords only "
                        "with a straightness certificate; log7's parallel-"
                        "strand environment abstains honestly (the law's cost "
                        "is typed, not hidden); endpoints/evidence unaltered"),
            "log25": outs["log25"][1].to_dict(),
            "log59": outs["log59"][1].to_dict(),
            "log7_abstain": outs["log7"][1].to_dict(),
            "chord_deviation_pt": chord_dev, "path_fit_pt": fit_max,
            "pngs": pngs,
        }
        (OUT_DIR / "design_path_adherence_proof.json").write_text(
            json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"[m8.14c2] verdict: {report['verdict']}")
        for p in pngs:
            print(f"[m8.14c2] BANKED GRADE FILE: {p}")
    finally:
        plan.close()
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
