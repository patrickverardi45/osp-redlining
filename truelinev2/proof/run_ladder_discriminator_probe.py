r"""M8.18 -- per-ladder tick-clustering discriminator for the
STRUCTURE_IDENTITY_BINDING_REQUIRED blocker (log8 / log32 / log42).

A proof-first investigation (the lane is NOT changed -- these three bores stay
STRUCTURE_IDENTITY_BINDING_REQUIRED, the already-honest state). It establishes,
with gates, the smallest correct discriminator AND the precise reason no safe
stroke can be placed yet:

  1. PER-LADDER CLUSTERING fixes the M8.16 corroboration basis. The old
     ``ladder_scale_for_band`` sampled a y-band at the boundary crossing; that
     band is EMPTY for log8 (horizontal matchline far from any tick) and
     MULTI-MODAL for log42 (two perpendicular ladders crossing the vertical
     matchline). ``cluster_ladders`` instead separates the ticks into coherent
     drawn ladders and derives ONE consistent sheet scale (1.44 pt/ft on every
     relevant sheet -- 18/2/9/10), giving the discriminator a real basis.

  2. DESIGN-PATH-LENGTH DISCRIMINATION beats straight-line distance. The drawn
     route LENGTH from a candidate start to the boundary (``walk_design_path``,
     the M8.14.c.2 law) corroborated against footage x scale at the banked
     ``DESIGN_LENGTH_REL_TOL`` uniquely separates the start where chord
     distance could not:
       * log42 -> 0 traceable survivors (the dense sheet-2 network exhausts
         the design-path search -- no candidate has a uniquely traceable route)
       * log8  -> EXACTLY ONE survivor (a NEXTLINK port HH; drawn route ~266pt
         vs 176ft x 1.44 = 253pt)
       * log32 -> EXACTLY ONE survivor -- the SAME structure (cross-bore
         collision: two sibling drop bores corroborate one port HH)

  3. ZERO SAFE CONVERSION, named precisely. Even binding log8/log32's unique
     survivor and threading the chain boundary, the BANKED b.9 cross-sheet
     join (``cross_sheet_join_verdict``, untouched) REFUSES both on implied-
     scale disagreement -- the END-sheet drop routes curve, so the chord-based
     structure->matchline scale does not close at the 5% join tolerance
     (log8 1.36 vs 1.18; log32 1.35 vs 1.42). The blocker has SHIFTED from
     start-structure identity (now essentially resolved by path-length) to the
     cross-sheet JOIN GEOMETRY: a path-length-based join is the named next
     capability. The per-bore start collision (log8 == log32 survivor) is the
     second named artifact.

Embedded gates (any failure -> nonzero exit):
  G1 the three bores still resolve to STRUCTURE_IDENTITY_BINDING_REQUIRED
     (the production lane is unchanged; this proof places nothing)
  G2 per-ladder clustering derives a coherent scale on each far sheet where
     the M8.16 band could not (empty for log8's matchline / multi-modal for
     log42's) -- the discriminator gains a real basis
  G3 design-path-length discrimination: log42 -> 0 traceable survivors;
     log8 -> exactly 1; log32 -> exactly 1
  G4 cross-bore collision pinned: log8's and log32's unique survivors are the
     SAME structure -- start identity is not unique to ONE bore
  G5 zero-false: the banked b.9 join REFUSES log8 + log32 even with the
     survivor bound and the chain boundary threaded -- no stroke is placed
  G6 no artifact rendered; the three bores carry no segments

Outputs (gitignored): data/outputs/ladder_discriminator_probe/

Run (repo root): $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_ladder_discriminator_probe
"""
from __future__ import annotations

import json
import math
import os
from typing import List, Optional, Tuple

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.conduit_topology import (
    connected_chain,
    symbol_footprint,
)
from truelinev2.extract.design_path import (
    DESIGN_LENGTH_REL_TOL,
    TRACED,
    conduit_pieces,
    path_length,
    walk_design_path,
)
from truelinev2.extract.ladder_cluster import cluster_ladders, coherent_ladder_scale
from truelinev2.extract.matchline_join import (
    assemble_callout_chain,
    cross_sheet_join_verdict,
    extend_dash_to_boundary,
    matchline_bboxes,
    nearest_gap,
    run_callouts_ending_at,
    run_callouts_starting_at,
)
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.structure_position import BRENHAM_LANE_DIALECT, cluster_symbols
from truelinev2.extract.tick_path import route_ladder_ticks
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.match.symbol_conduit_lane import (
    S_STRUCTURE_REQUIRED,
    _sheet_no,
    resolve_bore,
)
from truelinev2.proof.run_brenham_corpus import PDF, enumerate_corpus
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.match.frames import _build_plan_frame_graph

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "ladder_discriminator_probe"
LSET = ("BORE - PORT", "BORE - VACANT PIPE")   # the log8/32/42 run classes

# (bore, far sheet, end sheet, start raw, end raw, end-structure layer + near xy)
TARGETS = [
    ("log8", 18, 22, "0+00", "3+90", "FLOWER POT", (309.3, 392.0)),
    ("log32", 18, 22, "0+00", "2+13", "FLOWER POT", (287.3, 191.2)),
    ("log42", 2, 1, "0+00", "2+87", "NEXTLINK", (84.6, 419.4)),
]


def _far_segment(plan, off, far, end, start_raw, end_raw):
    """(boundary_raw, seg_far_ft, seg_end_ft) via the chain law, else direct."""
    ec = [(r, f) for r, f, _ in run_callouts_ending_at(plan.lines(end, off), end_raw)
          if f is not None and r != start_raw]
    boundary_raw, seg_end = ec[0]
    ch = assemble_callout_chain(plan.lines(far, off), start_raw, boundary_raw)
    if ch["result"] == "CALLOUT_CHAIN_UNIQUE":
        return boundary_raw, ch["footage"], seg_end
    direct = [f for r, f, _ in run_callouts_starting_at(plan.lines(far, off), start_raw)
              if f is not None and r == boundary_raw]
    return boundary_raw, direct[0], seg_end


def _discriminate(plan, off, dialect, far, end, boundary_raw, seg_far, scale):
    """Design-path-length survivors among far-sheet structures reaching the
    matchline: each candidate's drawn route length must corroborate
    footage x scale within the banked DESIGN_LENGTH_REL_TOL. Returns the list
    of (label, xy, path_len)."""
    drawings = plan.line_items(far, off)
    g = _build_plan_frame_graph(plan, off)
    edge = next(e for e in g.edges
                if {_sheet_no(e.from_frame), _sheet_no(e.to_frame)} == {far, end}
                and boundary_raw in (e.a_raw, e.b_raw))
    eqt = edge.source.split(None, 1)[-1]
    eqxy = next(((w["xc"], w["yc"]) for w in plan.words(far, off)
                 if w["text"] == eqt), None)
    ml = min(matchline_bboxes(drawings, dialect.matchline_layer),
             key=lambda bb: nearest_gap([eqxy], bb))
    conduit = [x for x in drawings if x["layer"] in LSET]
    pieces = conduit_pieces(drawings, dialect.path_layers)
    exp = seg_far * scale
    survivors = []
    for lay in sorted({v[1] for v in dialect.structure_layers.values()}):
        for c in cluster_symbols(drawings, lay):
            bb = symbol_footprint(drawings, lay, (c.x, c.y))
            if not bb:
                continue
            chain = connected_chain(conduit, bb)
            bnd = extend_dash_to_boundary(chain, ml) if chain else None
            if bnd is None:
                continue
            xy = ((bb[0] + bb[2]) / 2.0, (bb[1] + bb[3]) / 2.0)
            walk = walk_design_path(pieces, xy, bnd)
            if walk["result"] != TRACED:
                continue
            plen = path_length(walk["stroke_points"])
            if exp > 0 and abs(plen - exp) / exp <= DESIGN_LENGTH_REL_TOL:
                survivors.append((f"{lay}@{c.x:.0f},{c.y:.0f}", xy, round(plen, 1)))
    return survivors, ml


def _join_refuses(plan, off, dialect, far, end, boundary_raw, seg_far, seg_end,
                  start_xy, start_layer, end_layer, end_near, ml):
    """Bind the survivor + threaded chain boundary and run the banked b.9 join;
    return (verdict, scale_far, scale_end)."""
    g = _build_plan_frame_graph(plan, off)
    edge = next(e for e in g.edges
                if {_sheet_no(e.from_frame), _sheet_no(e.to_frame)} == {far, end}
                and boundary_raw in (e.a_raw, e.b_raw))
    eqt = edge.source.split(None, 1)[-1]
    dr_end = plan.line_items(end, off)
    ec = min(cluster_symbols(dr_end, end_layer),
             key=lambda c: math.hypot(c.x - end_near[0], c.y - end_near[1]))
    end_xy = (ec.x, ec.y)
    # the bore span is the chain-PROVEN closure (seg_far + seg_end); pass it so
    # the join's footage-closure clause PASSES and the refusal is genuinely the
    # implied-scale clause -- the real geometric blocker, not a sentinel.
    span_ft = seg_far + seg_end
    sides = {}
    for sheet, axy, alay, seg in ((far, start_xy, start_layer, seg_far),
                                  (end, end_xy, end_layer, seg_end)):
        dr = plan.line_items(sheet, off)
        eqxy = next(((w["xc"], w["yc"]) for w in plan.words(sheet, off)
                     if w["text"] == eqt), None)
        ml_s = min(matchline_bboxes(dr, dialect.matchline_layer),
                   key=lambda bb: nearest_gap([eqxy], bb))
        fp = symbol_footprint(dr, alay, axy)
        chain = connected_chain([x for x in dr if x["layer"] in LSET], fp) if fp else []
        bnd = extend_dash_to_boundary(chain, ml_s) if chain else None
        dist = nearest_gap([axy], ml_s)
        sides[sheet] = {"bnd": bnd, "scale": (dist / seg if seg and bnd else None)}
    sa, sb = sides[far]["scale"], sides[end]["scale"]
    jv = cross_sheet_join_verdict(
        equation_edge=True, eq_at_matchline_a=True, eq_at_matchline_b=True,
        chain_a_reaches=sides[far]["bnd"] is not None,
        chain_b_reaches=sides[end]["bnd"] is not None,
        seg_a_ft=seg_far, seg_b_ft=seg_end,
        span_ft=span_ft, scale_a=sa, scale_b=sb)
    return jv["verdict"], sa, sb, jv.get("named_missing", "")


def main() -> int:
    corpus_dir, how = resolve_corpus()
    print(f"[m8.18] corpus dir : {corpus_dir}  ({how})")
    if not os.path.isfile(PDF) or not os.path.isdir(corpus_dir):
        print("[m8.18] STOP: inputs missing")
        return 2
    corpus = {p.stem: p for p in enumerate_corpus(corpus_dir)}
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    plan = PlanPdf(PDF)
    ok = True
    rows = []
    try:
        dialect = select_dialect(plan)
        off = dialect.calibrate(plan, 13)
        graph = _build_plan_frame_graph(plan, off)

        # G1 -- the production lane is unchanged (all three stay abstain).
        statuses = {}
        for bid, *_ in TARGETS:
            out = resolve_bore(plan, load_borelog(str(corpus[f"bore_{bid}"])),
                               off, BRENHAM_LANE_DIALECT, frame_graph=graph)
            statuses[bid] = out.status
        g1 = all(s == S_STRUCTURE_REQUIRED for s in statuses.values())
        print(f"[m8.18] {'PASS' if g1 else 'FAIL'}  G1 lane unchanged "
              f"(all STRUCTURE_IDENTITY_BINDING_REQUIRED): {statuses}")
        ok &= g1

        survivors_by = {}
        scales_by = {}
        for bid, far, end, sr, er, end_lay, end_near in TARGETS:
            boundary_raw, seg_far, seg_end = _far_segment(plan, off, far, end, sr, er)
            ticks, _ = route_ladder_ticks(plan, far, off)
            ladders = cluster_ladders(ticks)
            scale = coherent_ladder_scale(ladders)
            scales_by[bid] = scale
            surv, ml = _discriminate(plan, off, BRENHAM_LANE_DIALECT, far, end,
                                     boundary_raw, seg_far, scale or 1.44)
            survivors_by[bid] = surv
            join = None
            if len(surv) == 1:
                join = _join_refuses(
                    plan, off, BRENHAM_LANE_DIALECT, far, end, boundary_raw,
                    seg_far, seg_end, surv[0][1], "NEXTLINK", end_lay,
                    end_near, ml)
            rows.append({
                "bore_id": bid, "far_sheet": far, "end_sheet": end,
                "boundary": boundary_raw, "seg_far_ft": seg_far,
                "seg_end_ft": seg_end, "lane_status": statuses[bid],
                "ladders": [{"len": l.length, "scale": round(l.scale, 3),
                             "span": list(l.station_span)} for l in ladders],
                "coherent_scale": scale,
                "survivors": [{"id": s[0], "path_len": s[2]} for s in surv],
                "join_verdict": (join[0] if join else None),
                "join_scales": ([round(join[1], 3) if join[1] else None,
                                 round(join[2], 3) if join[2] else None]
                                if join else None),
                "join_refusal_reason": (join[3] if join else None),
            })

        # G2 coherent scale where the M8.16 band could not corroborate
        g2 = all(scales_by[b] is not None for b in ("log8", "log32", "log42"))
        print(f"[m8.18] {'PASS' if g2 else 'FAIL'}  G2 per-ladder coherent "
              f"scale derived: {scales_by}")
        ok &= g2

        # G3 path-length discrimination counts
        n = {b: len(survivors_by[b]) for b in survivors_by}
        g3 = n["log42"] == 0 and n["log8"] == 1 and n["log32"] == 1
        print(f"[m8.18] {'PASS' if g3 else 'FAIL'}  G3 design-path-length "
              f"survivors: log8={n['log8']}, log32={n['log32']}, "
              f"log42={n['log42']} (expect 1/1/0)")
        ok &= g3

        # G4 cross-bore collision
        g4 = (n["log8"] == 1 and n["log32"] == 1
              and survivors_by["log8"][0][0] == survivors_by["log32"][0][0])
        same = survivors_by["log8"][0][0] if g4 else None
        print(f"[m8.18] {'PASS' if g4 else 'FAIL'}  G4 cross-bore collision: "
              f"log8 & log32 both bind {same!r} (start not unique to one bore)")
        ok &= g4

        # G5 the banked b.9 join refuses both, GENUINELY on implied-scale (the
        # footage closure PASSES -- span = chain-proven seg_far+seg_end) -> the
        # refusal is the real curved-route geometry, not a footage sentinel
        r8 = next(r for r in rows if r["bore_id"] == "log8")
        r32 = next(r for r in rows if r["bore_id"] == "log32")
        g5 = all(
            r["join_verdict"] == "CROSS_SHEET_CONTINUATION_NOT_PROVEN"
            and "implied-scale agreement" in (r["join_refusal_reason"] or "")
            and "footage closure" not in (r["join_refusal_reason"] or "")
            for r in (r8, r32))
        print(f"[m8.18] {'PASS' if g5 else 'FAIL'}  G5 banked b.9 join REFUSES "
              f"the bound survivor on IMPLIED-SCALE (footage closes), no "
              f"stroke: log8 {r8['join_scales']} / log32 {r32['join_scales']}: "
              f"{r8['join_refusal_reason']}")
        ok &= g5

        # G6 nothing rendered
        g6 = not list(OUT_DIR.glob("*.png"))
        print(f"[m8.18] {'PASS' if g6 else 'FAIL'}  G6 no artifact rendered")
        ok &= g6

        report = {
            "milestone": ("truelinev2 M8.18 -- per-ladder tick-clustering "
                          "discriminator (proof-first; HONEST NEGATIVE -- the "
                          "start narrows but the banked cross-sheet join "
                          "refuses; zero strokes, lane unchanged)"),
            "corpus_dir_used": corpus_dir, "corpus_resolution": how,
            "plan_pdf": PDF, "verdict": "PASS" if ok else "FAILURE",
            "discriminator_law": (
                "cluster_ladders separates interleaved ticks into coherent "
                "drawn ladders (adjacent-station hops, scale-consistent); "
                "coherent_ladder_scale derives one sheet scale or abstains; "
                "the drawn design-path LENGTH from each reaching candidate to "
                "the boundary corroborates footage x scale within the banked "
                "DESIGN_LENGTH_REL_TOL; uniqueness-mandatory"),
            "named_missing_artifacts": {
                "log8/log32": ("a PATH-LENGTH-based cross-sheet join (the "
                               "banked b.9 join checks the chord structure->"
                               "matchline scale, which the curved end-sheet "
                               "drop routes fail at 5%); AND a per-bore start "
                               "discriminator -- log8 and log32 corroborate "
                               "the SAME port HH"),
                "log42": ("a uniquely traceable drawn design path through the "
                          "dense sheet-2 conduit network (0 candidates trace "
                          "within the design-path search budget)"),
            },
            "bores": rows,
        }
        (OUT_DIR / "ladder_discriminator_probe.json").write_text(
            json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"[m8.18] verdict: {report['verdict']}")
        print(f"[m8.18] report -> {OUT_DIR / 'ladder_discriminator_probe.json'}")
    finally:
        plan.close()
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
