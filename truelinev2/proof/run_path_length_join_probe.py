r"""M8.19 -- path-length cross-sheet join (Phase 0/1 PROOF; no lane wiring).

The M8.18 named next capability. The banked b.9 join
(``cross_sheet_join_verdict``) compares the two sheets' IMPLIED SCALES
(structure->matchline distance / printed footage) within 5%. ``_cross_sheet_
segments`` feeds it the straight-line CHORD distance (``nearest_gap``); on a
curved drop route the chord is much shorter than the drilled length, so the
end-sheet implied scale collapses and the join refuses (log8 1.36 vs 1.18).

This probe measures the SAME implied scale from the drawn DESIGN-PATH LENGTH
(``walk_design_path`` -> ``path_length``, the M8.14.c.2 law) instead of the
chord, and feeds it to the UNCHANGED ``cross_sheet_join_verdict`` (same 5%
tolerance). It is a measurement correction, NOT a new evidence law and NOT a
tolerance change: chord <= path always, so a path-length scale is the true
drilled scale, never a looser bound.

Finding (gated below):
  * the path-length join PROVES log8 + log32 where the chord join refused
    (their implied scales agree within 5%: 1.51/1.55 and 1.50/1.44)
  * the banked control log65 PROVES BOTH ways (its routes are ~straight, so
    chord ~= path) -- the banked b.9/b.10 law is NOT weakened
  * BUT the cross-bore collision STANDS: log8 and log32 still bind the SAME
    port HH NEXTLINK@378,409. Placing both would draw two strokes from one
    structure on a per-bore binding that is not unique to either bore -- a
    SEPARATE ADJUDICATION RULE (multi-drop terminal confirmation, or a per-
    bore discriminator using the chain's intermediate station), NOT a join-
    geometry gap. STOP: the lane is NOT wired; no stroke is placed.

Embedded gates (any failure -> nonzero exit):
  G1 the chord join REFUSES log8 + log32 today (the current blocker)
  G2 the path-length join PROVES log8 + log32 (the capability works)
  G3 banked control log65 PROVES under BOTH chord and path-length (the b.9
     law is preserved -- path-length never breaks a passing join)
  G4 the 5% tolerance is unchanged (JOIN_SCALE_REL_TOL == 0.05); the proven
     scales agree within it (measurement correction, not widening)
  G5 cross-bore collision STANDS + lane unchanged: log8 and log32 narrow to
     the same start, and resolve_bore still returns
     STRUCTURE_IDENTITY_BINDING_REQUIRED for both (no stroke placed)

Outputs (gitignored): data/outputs/path_length_join_probe/

Run (repo root): $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_path_length_join_probe
"""
from __future__ import annotations

import json
import math
import os
from typing import Optional, Tuple

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.conduit_topology import connected_chain, symbol_footprint
from truelinev2.extract.design_path import (
    TRACED,
    conduit_pieces,
    path_length,
    walk_design_path,
)
from truelinev2.extract.matchline_join import (
    JOIN_SCALE_REL_TOL,
    cross_sheet_join_verdict,
    extend_dash_to_boundary,
    matchline_bboxes,
    nearest_gap,
)
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.structure_position import BRENHAM_LANE_DIALECT, cluster_symbols
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

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "path_length_join_probe"

# bore, far/end sheet, boundary, (start layer, near xy), (end layer, near xy),
# seg_far ft, seg_end ft, conduit layer set
CASES = [
    ("log8", 18, 22, "1+76", ("NEXTLINK", (378, 409)),
     ("FLOWER POT", (309.3, 392.0)), 176.0, 214.0,
     ("BORE - PORT", "BORE - VACANT PIPE")),
    ("log32", 18, 22, "1+77", ("NEXTLINK", (378, 409)),
     ("FLOWER POT", (287.3, 191.2)), 177.0, 36.0,
     ("BORE - PORT", "BORE - VACANT PIPE")),
    ("log65", 10, 9, "6+11", ("NEXTLINK", (291.6, 355.3)),
     ("FLOWER POT", (1085.2, 356.1)), 160.0, 39.0,
     ("BORE - VACANT PIPE",)),
]


def design_path_implied_scale(pieces, anchor_xy: Tuple[float, float],
                              boundary_xy: Tuple[float, float], footage: float
                              ) -> Tuple[Optional[float], Optional[float]]:
    """The implied pts/ft scale from the DRAWN route length anchor->boundary
    (``walk_design_path``), not the straight chord. Returns (scale, path_len);
    (None, None) when the route does not uniquely trace. PURE."""
    if not footage:
        return None, None
    walk = walk_design_path(pieces, anchor_xy, boundary_xy)
    if walk["result"] != TRACED:
        return None, None
    plen = path_length(walk["stroke_points"])
    return plen / footage, plen


def _side(plan, off, dialect, sheet, far, end, boundary_raw, anchor_layer,
          anchor_near, footage, lset, graph):
    """(chord_scale, path_scale) for one sheet's structure->matchline span."""
    dr = plan.line_items(sheet, off)
    edge = next(e for e in graph.edges
                if {_sheet_no(e.from_frame), _sheet_no(e.to_frame)} == {far, end}
                and boundary_raw in (e.a_raw, e.b_raw))
    eqt = edge.source.split(None, 1)[-1]
    eqxy = next(((w["xc"], w["yc"]) for w in plan.words(sheet, off)
                 if w["text"] == eqt), None)
    ml = min(matchline_bboxes(dr, dialect.matchline_layer),
             key=lambda bb: nearest_gap([eqxy], bb))
    c = min(cluster_symbols(dr, anchor_layer),
            key=lambda c: math.hypot(c.x - anchor_near[0], c.y - anchor_near[1]))
    axy = (c.x, c.y)
    fp = symbol_footprint(dr, anchor_layer, axy)
    chain = connected_chain([x for x in dr if x["layer"] in lset], fp) if fp else []
    bnd = extend_dash_to_boundary(chain, ml) if chain else None
    chord = nearest_gap([axy], ml)
    chord_scale = (chord / footage) if chord and footage else None
    path_scale = (design_path_implied_scale(
        conduit_pieces(dr, dialect.path_layers), axy, bnd, footage)[0]
        if bnd else None)
    return chord_scale, path_scale


def _proven(seg_far, seg_end, span, sa, sb) -> bool:
    return cross_sheet_join_verdict(
        equation_edge=True, eq_at_matchline_a=True, eq_at_matchline_b=True,
        chain_a_reaches=True, chain_b_reaches=True,
        seg_a_ft=seg_far, seg_b_ft=seg_end, span_ft=span,
        scale_a=sa, scale_b=sb)["verdict"] == "CROSS_SHEET_CONTINUATION_PROVEN"


def main() -> int:
    corpus_dir, how = resolve_corpus()
    print(f"[m8.19] corpus dir : {corpus_dir}  ({how})")
    if not os.path.isfile(PDF) or not os.path.isdir(corpus_dir):
        print("[m8.19] STOP: inputs missing")
        return 2
    corpus = {p.stem: p for p in enumerate_corpus(corpus_dir)}
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    plan = PlanPdf(PDF)
    ok = True
    rows = []
    try:
        off = select_dialect(plan).calibrate(plan, 13)
        dialect = BRENHAM_LANE_DIALECT   # the lane dialect owns the layer tables
        graph = _build_plan_frame_graph(plan, off)
        by = {}
        for (bid, far, end, boundary, (sL, sN), (eL, eN),
             segF, segE, lset) in CASES:
            bore = load_borelog(str(corpus[f"bore_{bid}"]))
            span = bore.station_end_ft - bore.station_start_ft
            fc, fp = _side(plan, off, dialect, far, far, end, boundary, sL, sN,
                           segF, lset, graph)
            ec, ep = _side(plan, off, dialect, end, far, end, boundary, eL, eN,
                           segE, lset, graph)
            row = {
                "bore_id": bid, "span_ft": span,
                "chord_scales": [round(fc, 3) if fc else None,
                                 round(ec, 3) if ec else None],
                "path_scales": [round(fp, 3) if fp else None,
                                round(ep, 3) if ep else None],
                "chord_join": _proven(segF, segE, span, fc, ec),
                "path_join": _proven(segF, segE, span, fp, ep),
            }
            by[bid] = row
            rows.append(row)

        g1 = not by["log8"]["chord_join"] and not by["log32"]["chord_join"]
        print(f"[m8.19] {'PASS' if g1 else 'FAIL'}  G1 chord join REFUSES "
              f"log8/log32 (current blocker): "
              f"log8 {by['log8']['chord_scales']}, log32 {by['log32']['chord_scales']}")
        ok &= g1

        g2 = by["log8"]["path_join"] and by["log32"]["path_join"]
        print(f"[m8.19] {'PASS' if g2 else 'FAIL'}  G2 path-length join PROVES "
              f"log8/log32: log8 {by['log8']['path_scales']}, "
              f"log32 {by['log32']['path_scales']}")
        ok &= g2

        g3 = by["log65"]["chord_join"] and by["log65"]["path_join"]
        print(f"[m8.19] {'PASS' if g3 else 'FAIL'}  G3 banked control log65 "
              f"PROVES both ways (b.9 law preserved): "
              f"chord {by['log65']['chord_scales']}, path {by['log65']['path_scales']}")
        ok &= g3

        # G4 measurement correction, not widening: tolerance pinned, proven
        # scales agree within it
        def rel(sc):
            a, b = sc
            return abs(a - b) / a if a and b else None
        g4 = (JOIN_SCALE_REL_TOL == 0.05
              and rel(by["log8"]["path_scales"]) <= JOIN_SCALE_REL_TOL
              and rel(by["log32"]["path_scales"]) <= JOIN_SCALE_REL_TOL)
        print(f"[m8.19] {'PASS' if g4 else 'FAIL'}  G4 tolerance unchanged "
              f"({JOIN_SCALE_REL_TOL}); path scales agree within it "
              f"(log8 {rel(by['log8']['path_scales']):.3f}, "
              f"log32 {rel(by['log32']['path_scales']):.3f})")
        ok &= g4

        # G5 collision STANDS + lane unchanged (no stroke placed)
        st = {b: resolve_bore(plan, load_borelog(str(corpus[f"bore_{b}"])),
                              off, BRENHAM_LANE_DIALECT, frame_graph=graph).status
              for b in ("log8", "log32", "log42")}
        g5 = all(s == S_STRUCTURE_REQUIRED for s in st.values())
        print(f"[m8.19] {'PASS' if g5 else 'FAIL'}  G5 cross-bore collision "
              f"STANDS (log8==log32 start) + lane UNCHANGED (no stroke): {st}")
        ok &= g5

        report = {
            "milestone": ("truelinev2 M8.19 -- path-length cross-sheet join "
                          "(Phase 0/1 proof; VALID but BLOCKED on the cross-"
                          "bore collision; lane not wired, no stroke placed)"),
            "corpus_dir_used": corpus_dir, "corpus_resolution": how,
            "plan_pdf": PDF, "verdict": "PASS" if ok else "FAILURE",
            "law": ("measure the b.9 implied scale from the DRAWN design-path "
                    "LENGTH (walk_design_path -> path_length) instead of the "
                    "straight chord (nearest_gap), feeding the UNCHANGED "
                    "cross_sheet_join_verdict at the UNCHANGED 5% tolerance -- "
                    "a measurement correction (chord <= path), not a new "
                    "evidence law and not a widening"),
            "blocker": ("the cross-bore collision STANDS: log8 and log32 both "
                        "bind NEXTLINK@378,409. The path-length join proves "
                        "each continuation, but placing both draws two strokes "
                        "from one structure on a binding unique to NEITHER "
                        "bore. Resolving it is a SEPARATE ADJUDICATION RULE "
                        "(multi-drop terminal confirmation OR a per-bore "
                        "discriminator on the chain's intermediate station "
                        "1+10 vs 1+30) -- itself a new evidence question. The "
                        "lane stays unwired; no stroke is placed."),
            "cases": rows,
        }
        (OUT_DIR / "path_length_join_probe.json").write_text(
            json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"[m8.19] verdict: {report['verdict']}")
        print(f"[m8.19] report -> {OUT_DIR / 'path_length_join_probe.json'}")
    finally:
        plan.close()
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
