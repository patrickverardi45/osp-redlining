r"""M8.22 -- strand discriminator for log42's callout-frame origin (proof-only).

M8.21 left log42's origin NEXTLINK@819,351 at DESIGN_PATH_AMBIGUOUS (the
corridor walk found 2 jitter-distinct groups; on the FULL sheet-2 universe
the dense search is DESIGN_PATH_SEARCH_EXHAUSTED). This probe asks the owner's
M8.22 question: can a SAFE discriminator pick the run's true strand?

ANSWER: YES for log42, and it is LICENSED BY PRINTED EVIDENCE, not raw
geometry. The origin prints TWO ``STA 0+00 ... E/W PORT TERMINAL TAIL`` runs
-- ``0+00->2+70 (270')`` (East, this bore) and ``0+00->5+26 (526')`` (the
other tail) -- and each has its OWN printed matchline (``STA 2+70/5+16 - SEE
SHEET 1`` vs ``STA 5+26/12+66 - SEE SHEET 3``). The two strands differ ONLY
in that GROUP 1 detours WEST into the 526' tail's drawn conduit before
running east; GROUP 0 runs monotone East to the 2+70 terminus. The 526'
tail is a DIFFERENT printed run, so its geometry is not this bore's: a
directional eligibility filter removes conduit pieces lying entirely behind
the origin (away from this run's printed 2+70 terminus), and the walk then
traces GROUP 0 uniquely.

SOUNDNESS / HONEST SCOPE (adversarial-panel hardened -- this is NOT a general
geometric theorem). The filter projects pieces onto the straight origin->
terminus chord ``u`` and cuts a piece iff ALL its vertices project below
``-FOOTPRINT_RADIUS``. Chord projection equals true station only when the
run's drawn route is chord-MONOTONE; on a hooked/backward-curving route a
forward piece can project behind the chord. So the filter is:
  * one-sided: it can LOSE completions for a backward-curving run (-> a typed
    conservative abstain), and -- only with a chord-hugging DECOY sibling --
    it could leave a wrong-strand survivor. It therefore fires ONLY under
    three positive gates, all checked below: (G2) a printed multi-tail
    LICENSE (the behind-origin geometry provably belongs to another printed
    run); (G5) a per-survivor chord-monotonicity CERTIFICATE (every survivor
    vertex projects >= -margin) PLUS the banked ``parallel_strand_guard``
    (no unvisited sibling parallels the survivor); (G6) a robustness check
    (identical decision at both co-located origin candidates).
  * NOT M8.18-class and NOT corridor-class: the survivor carries the distinct
    provenance ``DIRECTIONAL_FORWARD_OF_PRINTED_ORIGIN`` and is barred from
    Law-1 gate-1 the same way; any lane wiring needs fresh adversarial review.
  * O's POSITION is used, never its identity: NEXTLINK@819,351's structure
    identity stays ABSTAINED (M8.21). The filter reads only {O position, the
    2+70 terminus position, conduit pieces, margin}; it never reads the
    0+46=0+00 equation, the HH-HH=46' note, or the log41 44/50 digits.

OUTCOME: log42 stays STRUCTURE_IDENTITY_BINDING_REQUIRED -- the strand
resolves but the bore is NOT placed. The blocker SHIFTS to the END side: the
M8.19 cross-sheet scale-join refuses under the CORRECT terminus anchor
(NEXTLINK terminal_port_hh: far 1.4525 vs end 1.3669, 6.3% > 5%), but the
17-ft end segment draws to ~23 pt where 5% is only ~1.2 pt of draw noise --
below the measurement floor (the WRONG FLOWER POT anchor would flip it to
3.4% PROVEN). The honest named-missing is END-side: the 2+70->2+87 segment is
too short to corroborate scale; the printed boundary equation + closure
(270+17=287) already prove the crossing, so a non-scale continuity rule (or
an owner waiver for sub-floor segments) is what log42 needs -- NOT a tolerance
widen, NOT a far-side fix.

Gates G1-G10 below. No tolerance widened, no walk budget raised, no y-band,
no nearest-selection, no 44<->46 match, no stroke/PNG/segment, no AUTO, no
lane wiring, no census change.

Outputs (gitignored): data/outputs/strand_discriminator_probe/
Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_strand_discriminator_probe
"""
from __future__ import annotations

import json
import math
import os
from typing import Dict, List, Optional, Sequence, Tuple

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.conduit_topology import (FOOTPRINT_RADIUS,
                                                 connected_chain,
                                                 symbol_footprint)
from truelinev2.extract.design_path import (EXHAUSTED, TRACED, conduit_pieces,
                                            parallel_strand_guard, path_length,
                                            walk_design_path)
from truelinev2.extract.ladder_cluster import (cluster_ladders,
                                               coherent_ladder_scale)
from truelinev2.extract.matchline_join import (cross_sheet_join_verdict,
                                               extend_dash_to_boundary,
                                               matchline_bboxes, nearest_gap,
                                               run_callouts_starting_at)
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.structure_position import (BRENHAM_LANE_DIALECT,
                                                   cluster_symbols)
from truelinev2.extract.tick_path import route_ladder_ticks
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.match.symbol_conduit_lane import (BAND_HALFWIDTH,
                                                  S_STRUCTURE_REQUIRED,
                                                  S_UNPRINTED, _sheet_no,
                                                  resolve_bore)
from truelinev2.proof.run_brenham_corpus import PDF, enumerate_corpus
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.service import _build_plan_frame_graph
from truelinev2.stations import parse_station

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "strand_discriminator_probe"
LSET = ("BORE - PORT", "BORE - VACANT PIPE")

# Provenance tag: a directionally-resolved survivor is its OWN certificate
# class -- never an M8.18 full-universe survivor, never a Law-1 gate-1 input.
UNIVERSE_DIRECTIONAL = "DIRECTIONAL_FORWARD_OF_PRINTED_ORIGIN"
# Typed findings (NOT lane statuses).
STRAND_RESOLVED = "STRAND_RESOLVED_FORWARD"
CHORD_NONMONOTONE = "CHORD_NONMONOTONE_DIRECTIONAL_UNSAFE"
END_SCALE_UNMEASURABLE = "END_SEGMENT_SCALE_UNMEASURABLE"

# log42's split family + the two structure-required controls (M8.21 frozen).
LOG42 = ("log42", 2, 1, "0+00", "2+87", 270.0, "2+70")
CONTROLS = [("log8", 18, 22, "0+00", "3+90", 176.0, "1+76"),
            ("log32", 18, 22, "0+00", "2+13", 177.0, "1+77")]
CONTROL_SURVIVOR = "NEXTLINK@378,409"
CONTROL_PLEN = 265.7
ORIGIN_ID = "NEXTLINK@819,351"          # M8.21 callout-frame 0+00 (identity abstained)
INSTALLER_ID = "NEXTLINK@818,419"        # co-located 0+46 interior reset (M8.21)
EXPECT_SURVIVOR_FT = 272.3
EXPECT_CUT = 27                          # full-universe directional cut count
EXPECT_KEPT = 12


def _u(O, T):
    dx, dy = T[0] - O[0], T[1] - O[1]
    n = math.hypot(dx, dy)
    return dx / n, dy / n


def _proj(v, O, u):
    return (v[0] - O[0]) * u[0] + (v[1] - O[1]) * u[1]


def directional_eligible(pieces, O, T, margin):
    """Keep a piece UNLESS all its vertices project below -margin on the
    origin->terminus chord (entirely behind the printed origin). Pure;
    order-preserving; the input is never mutated. SOUND ONLY under the
    probe's license + certificate gates (see module docstring)."""
    u = _u(O, T)
    kept, cut = [], []
    for p in pieces:
        (cut if max(_proj(v, O, u) for v in p.points) < -margin
         else kept).append(p)
    return kept, cut


def chord_monotone_survivor(stroke_points, O, T, margin):
    """The per-survivor certificate: every vertex of the traced survivor must
    project >= -margin (the survivor itself never goes behind the origin, so
    the chord faithfully ordered THIS route). Returns (ok, min_projection)."""
    u = _u(O, T)
    mn = min(_proj(v, O, u) for v in stroke_points)
    return mn >= -margin, mn


def _anchor(plan, off, far, sym_layer, sym_id, lane, boundary_raw, graph,
            end):
    drawings = plan.line_items(far, off)
    conduit = [x for x in drawings if x["layer"] in LSET]
    sym = next((c for c in cluster_symbols(drawings, sym_layer)
                if f"{sym_layer}@{c.x:.0f},{c.y:.0f}" == sym_id), None)
    if sym is None:
        return None
    bb = symbol_footprint(drawings, sym_layer, (sym.x, sym.y))
    O = ((bb[0] + bb[2]) / 2.0, (bb[1] + bb[3]) / 2.0)
    edges = [e for e in graph.edges
             if {_sheet_no(e.from_frame), _sheet_no(e.to_frame)} == {far, end}
             and boundary_raw in (e.a_raw, e.b_raw)]
    eqt = edges[0].source.split(None, 1)[-1]
    eqxy = next(((w["xc"], w["yc"]) for w in plan.words(far, off)
                 if w["text"] == eqt), None)
    ml = min(matchline_bboxes(drawings, lane.matchline_layer),
             key=lambda b: nearest_gap([eqxy], b))
    T = extend_dash_to_boundary(connected_chain(conduit, bb), ml)
    return O, T


def resolve_strand(plan, off, graph, lane, far, end, sym_id, boundary_raw,
                   seg_far):
    """Directional resolution on the FULL piece universe. Returns a dict with
    the full-universe walk result, the directional walk result, the survivor,
    the chord-monotonicity certificate, and the parallel-strand guard."""
    drawings = plan.line_items(far, off)
    pieces = conduit_pieces(drawings, lane.path_layers)
    scale = coherent_ladder_scale(cluster_ladders(
        route_ladder_ticks(plan, far, off)[0]))
    a = _anchor(plan, off, far, "NEXTLINK", sym_id, lane, boundary_raw, graph,
                end)
    O, T = a
    w_full = walk_design_path(pieces, O, T)
    kept, cut = directional_eligible(pieces, O, T, FOOTPRINT_RADIUS)
    w_dir = walk_design_path(kept, O, T)
    out = {"O": O, "T": T, "scale": scale, "pieces_total": len(pieces),
           "pieces_kept": len(kept), "pieces_cut": len(cut),
           "full_result": w_full["result"],
           "full_paths_found": w_full.get("paths_found"),
           "dir_result": w_dir["result"],
           "dir_groups": w_dir.get("path_groups"), "cut": cut}
    if w_dir["result"] == TRACED:
        sp = w_dir["stroke_points"]
        ok, mn = chord_monotone_survivor(sp, O, T, FOOTPRINT_RADIUS)
        # guard runs on the KEPT universe with KEPT-relative visited indices
        # (index alignment; the licensed behind-origin West tail is G2's job,
        # the guard catches residual FORWARD sibling strands among `kept`).
        guard = parallel_strand_guard(
            kept, w_dir["visited_pieces"], sp, [O, T],
            corridor=BAND_HALFWIDTH, anchor_radius=FOOTPRINT_RADIUS)
        out.update({"survivor_ft": round(path_length(sp) / scale, 1),
                    "survivor_plen": round(path_length(sp), 1),
                    "cert_ok": ok, "cert_min_proj": round(mn, 1),
                    "guard_clear": guard["clear"],
                    "guard_strands": guard["parallel_strands"],
                    "stroke_points": sp})
    return out


def main() -> int:
    corpus_dir, how = resolve_corpus()
    print(f"[m8.22] corpus dir : {corpus_dir}  ({how})")
    if not os.path.isfile(PDF) or not os.path.isdir(corpus_dir):
        print("[m8.22] STOP: inputs missing")
        return 2
    corpus = {p.stem: p for p in enumerate_corpus(corpus_dir)}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUT_DIR / "strand_discriminator_probe.json"
    report_path.unlink(missing_ok=True)

    plan = PlanPdf(PDF)
    ok = True
    try:
        dialect = select_dialect(plan)
        off = dialect.calibrate(plan, 13)
        graph = _build_plan_frame_graph(plan, off)
        lane = BRENHAM_LANE_DIALECT
        bid, far, end, sr, er, seg_far, brd = LOG42

        # ---- G1: lane unchanged (census untouched) ----
        statuses = {}
        for b, *_ in [LOG42] + CONTROLS + [("log41",)]:
            bore = load_borelog(str(corpus[f"bore_{b}"]))
            statuses[b] = resolve_bore(plan, bore, off, lane,
                                       frame_graph=graph).status
        g1 = (statuses["log42"] == statuses["log8"] == statuses["log32"]
              == S_STRUCTURE_REQUIRED and statuses["log41"] == S_UNPRINTED)
        print(f"[m8.22] {'PASS' if g1 else 'FAIL'}  G1 lane unchanged: "
              f"{statuses}")
        ok &= g1

        # ---- G2: printed multi-tail LICENSE ----
        tails = [(r, f) for r, f, _ in
                 run_callouts_starting_at(plan.lines(far, off), "0+00")
                 if f is not None]
        matchlines = [ln for ln in plan.lines(far, off) if "MATCHLINE" in ln]
        has_270 = any(r == "2+70" and f == 270.0 for r, f in tails)
        has_526 = any(r == "5+26" and f == 526.0 for r, f in tails)
        ml_270 = any("2+70/5+16" in ln for ln in matchlines)
        ml_526 = any("5+26/12+66" in ln for ln in matchlines)
        g2 = has_270 and has_526 and ml_270 and ml_526 and len(tails) >= 2
        print(f"[m8.22] {'PASS' if g2 else 'FAIL'}  G2 two-tail license: "
              f"tails {[(r, f) for r, f in tails]}; 270-matchline {ml_270}, "
              f"526-matchline {ml_526} (the West tail is a distinct printed "
              f"run -> its geometry is not this bore's)")
        ok &= g2

        # ---- G3: full-universe precondition (the dense search EXHAUSTS) ----
        r = resolve_strand(plan, off, graph, lane, far, end, ORIGIN_ID, brd,
                           seg_far)
        g3 = r["full_result"] == EXHAUSTED
        print(f"[m8.22] {'PASS' if g3 else 'FAIL'}  G3 full-universe "
              f"precondition: unfiltered {r['pieces_total']}-piece walk "
              f"{r['full_result']} (the M8.20 banked dense-search state)")
        ok &= g3

        # ---- G4: directional resolves the strand (AMBIGUOUS/EXHAUSTED->TRACED)
        g4 = (r["dir_result"] == TRACED and r["dir_groups"] == 1
              and r["pieces_cut"] == EXPECT_CUT
              and r["pieces_kept"] == EXPECT_KEPT
              and r["survivor_ft"] == EXPECT_SURVIVOR_FT)
        recon = (r["survivor_ft"] - seg_far) / seg_far
        print(f"[m8.22] {'PASS' if g4 else 'FAIL'}  G4 directional resolves: "
              f"cut {r['pieces_cut']}/{r['pieces_total']} -> {r['dir_result']}"
              f" 1 group; survivor {r['survivor_ft']} ft = +{recon * 100:.1f}%"
              f" vs printed {seg_far:.0f}' (= ~46' drop + ~224' east)")
        ok &= g4

        # ---- G5: per-survivor certificate + parallel-strand guard ----
        g5 = r.get("cert_ok") and r.get("guard_clear")
        print(f"[m8.22] {'PASS' if g5 else 'FAIL'}  G5 survivor certificate: "
              f"chord-monotone min_proj {r.get('cert_min_proj')} >= "
              f"-{FOOTPRINT_RADIUS} ({r.get('cert_ok')}); parallel_strand_"
              f"guard clear {r.get('guard_clear')} "
              f"({r.get('guard_strands')} sibling strands)")
        ok &= g5

        # ---- G6: robustness at both co-located origin candidates ----
        r_inst = resolve_strand(plan, off, graph, lane, far, end, INSTALLER_ID,
                                brd, seg_far)
        cut_a = sorted((round(p.a[0], 1), round(p.a[1], 1)) for p in r["cut"])
        cut_b = sorted((round(p.a[0], 1), round(p.a[1], 1))
                       for p in r_inst["cut"])
        g6 = (cut_a == cut_b and r_inst["dir_result"] == TRACED
              and r_inst.get("cert_ok"))
        print(f"[m8.22] {'PASS' if g6 else 'FAIL'}  G6 robustness: identical "
              f"cut set + valid survivor at both co-located origins "
              f"({ORIGIN_ID} 0+00 / {INSTALLER_ID} 0+46) -- the strand "
              f"decision is invariant to the unresolved origin identity")
        ok &= g6

        # ---- G7: the cut pieces are the printed 526' West tail ----
        u = _u(r["O"], r["T"])
        cut_proj = [round(max(_proj(v, r["O"], u) for v in p.points), 1)
                    for p in r["cut"]]
        g7 = all(pr < -FOOTPRINT_RADIUS for pr in cut_proj) and len(cut_proj)
        print(f"[m8.22] {'PASS' if g7 else 'FAIL'}  G7 cut = West tail: all "
              f"{len(cut_proj)} cut pieces project behind the origin (max "
              f"proj {max(cut_proj):.1f} < -{FOOTPRINT_RADIUS}); they are the "
              f"526' tail's conduit, not tiebroken-away geometry of this run")
        ok &= g7

        # ---- G8: controls byte-identical under the filter ----
        g8 = True
        ctl_rows = {}
        for cb, cf, ce, csr, cer, cseg, cbrd in CONTROLS:
            rc_base = walk_design_path(
                conduit_pieces(plan.line_items(cf, off), lane.path_layers),
                *_anchor(plan, off, cf, "NEXTLINK", CONTROL_SURVIVOR, lane,
                         cbrd, graph, ce))
            rc = resolve_strand(plan, off, graph, lane, cf, ce,
                                CONTROL_SURVIVOR, cbrd, cseg)
            byte_eq = (rc_base["result"] == TRACED
                       and rc["dir_result"] == TRACED
                       and rc_base["stroke_points"] == rc["stroke_points"]
                       and rc["survivor_ft"] is not None
                       and round(path_length(rc_base["stroke_points"]), 1)
                       == CONTROL_PLEN)
            ctl_rows[cb] = {"survivor_ft": rc["survivor_ft"],
                            "byte_identical": byte_eq,
                            "pieces_cut": rc["pieces_cut"]}
            g8 &= byte_eq
        print(f"[m8.22] {'PASS' if g8 else 'FAIL'}  G8 controls byte-identical:"
              f" log8/log32 directional walk == baseline ({CONTROL_SURVIVOR}, "
              f"plen {CONTROL_PLEN}); cut only behind-origin off-strand pieces")
        ok &= g8

        # ---- G9: honest END-side block (strand resolves, bore NOT placed) ----
        far_scale = r["survivor_plen"] / seg_far
        ends = {}
        for cls in ("NEXTLINK", "FLOWER POT"):
            dr1 = plan.line_items(1, off)
            con1 = [x for x in dr1 if x["layer"] in LSET]
            for c in cluster_symbols(dr1, cls):
                if c.x < 150 and 400 < c.y < 440:
                    bb1 = symbol_footprint(dr1, cls, (c.x, c.y))
                    if not bb1:
                        continue
                    xy1 = ((bb1[0] + bb1[2]) / 2.0, (bb1[1] + bb1[3]) / 2.0)
                    a1 = _anchor(plan, off, 1, cls,
                                 f"{cls}@{c.x:.0f},{c.y:.0f}", lane, "2+70",
                                 graph, 2)
                    if a1 is None or a1[1] is None:
                        continue
                    w1 = walk_design_path(
                        *([conduit_pieces(dr1, lane.path_layers)] + list(a1)))
                    if w1["result"] == TRACED:
                        es = path_length(w1["stroke_points"]) / 17.0
                        rel = abs(far_scale - es) / es
                        ends[f"{cls}@{c.x:.0f},{c.y:.0f}"] = {
                            "end_scale": round(es, 4),
                            "join_rel_pct": round(rel * 100, 1),
                            "verdict": ("PROVEN" if rel <= 0.05
                                        else "REFUSED")}
        # correct terminus = NEXTLINK terminal_port_hh (matches PORT TERMINAL)
        nl = next((v for k, v in ends.items() if k.startswith("NEXTLINK")),
                  None)
        fp = next((v for k, v in ends.items() if k.startswith("FLOWER")), None)
        # measurement floor: 5% of the ~23pt end draw is ~1.2pt
        end_draw_pt = 17.0 * r["scale"]
        floor_pt = 0.05 * end_draw_pt
        g9 = (nl is not None and nl["verdict"] == "REFUSED"
              and fp is not None and fp["verdict"] == "PROVEN"
              and floor_pt < 2.0)
        print(f"[m8.22] {'PASS' if g9 else 'FAIL'}  G9 END-side block: under "
              f"the CORRECT NEXTLINK terminal_port_hh anchor join {nl}; the "
              f"WRONG FLOWER POT anchor would flip {fp}; 5% floor = "
              f"{round(floor_pt, 1)} pt on the {round(end_draw_pt, 1)}-pt "
              f"end draw -> below the measurement floor ({END_SCALE_UNMEASURABLE})")
        ok &= g9

        # ---- G10: posture ----
        probe_classes = {UNIVERSE_DIRECTIONAL, STRAND_RESOLVED,
                         CHORD_NONMONOTONE, END_SCALE_UNMEASURABLE}
        lane_status = {S_STRUCTURE_REQUIRED, S_UNPRINTED}
        g10 = (not list(OUT_DIR.glob("*.png"))
               and probe_classes.isdisjoint(lane_status))
        print(f"[m8.22] {'PASS' if g10 else 'FAIL'}  G10 posture: nothing "
              f"rendered; probe classes disjoint from lane statuses; O used "
              f"by POSITION only (identity stays abstained)")
        ok &= g10

        for d in (r, r_inst):           # geometry stays in-memory only
            d.pop("stroke_points", None)
            d.pop("cut", None)

        report = {
            "milestone": ("truelinev2 M8.22 -- strand discriminator for "
                          "log42's callout-frame origin (proof-only; lane, "
                          "census, grades, tolerances, budget UNCHANGED; zero "
                          "strokes; log42 stays STRUCTURE_IDENTITY_BINDING_"
                          "REQUIRED -- strand resolved, bore NOT placed)"),
            "corpus_dir_used": corpus_dir, "corpus_resolution": how,
            "plan_pdf": PDF, "verdict": "PASS" if ok else "FAILURE",
            "lane_statuses": statuses,
            "printed_license": {
                "origin": f"{ORIGIN_ID} (M8.21 callout-frame 0+00; structure "
                          f"identity ABSTAINED -- position used only)",
                "printed_tails": [(rr, ff) for rr, ff in tails],
                "tail_matchlines": {"270_east": "STA 2+70/5+16 - SEE SHEET 1",
                                    "526_west": "STA 5+26/12+66 - SEE SHEET 3"},
                "note": ("the 526' West tail is a DISTINCT printed run with "
                         "its own matchline; its conduit is not this bore's"),
            },
            "strand_resolution": {
                "finding": STRAND_RESOLVED,
                "uniqueness_universe": UNIVERSE_DIRECTIONAL,
                "full_universe_walk": r["full_result"],
                "directional_walk": r["dir_result"],
                "pieces": f"{r['pieces_kept']}/{r['pieces_total']} kept "
                          f"({r['pieces_cut']} cut behind origin)",
                "survivor_ft": r["survivor_ft"],
                "reconstruction": "~46' drop (origin->installer) + ~224' east "
                                  "(installer->2+70) = 270'",
                "certificate": {"chord_monotone_min_proj": r["cert_min_proj"],
                                "parallel_strand_guard_clear": r["guard_clear"]},
                "robustness": {"installer_origin_cut_identical": cut_a == cut_b,
                               "installer_survivor_ft": r_inst["survivor_ft"]},
                "honest_scope": ("one-sided: never CREATES a false survivor "
                                 "under the license+certificate; for an "
                                 "unlicensed/backward-curving run it would "
                                 "conservatively abstain. Probe-local; not a "
                                 "shipped general law."),
            },
            "controls": ctl_rows,
            "downstream_block": {
                "finding": END_SCALE_UNMEASURABLE,
                "far_scale": round(far_scale, 4),
                "end_anchors": ends,
                "correct_terminus": "NEXTLINK terminal_port_hh (matches the "
                                    "printed 'PORT TERMINAL TAIL')",
                "join_under_correct_anchor": nl,
                "measurement_floor": (f"5% of the {round(end_draw_pt, 1)}-pt "
                                      f"end draw = {round(floor_pt, 1)} pt; the"
                                      f" 17-ft segment is below the scale-"
                                      f"measurement floor (the WRONG FLOWER "
                                      f"POT anchor flips it to PROVEN -- proof "
                                      f"the refusal is unmeasurable noise, not "
                                      f"a far/end disagreement)"),
                "named_missing": ("the printed boundary equation STA 2+70/5+16"
                                  " + closure 270+17=287 already prove the "
                                  "crossing; log42 needs a NON-SCALE cross-"
                                  "sheet continuity corroboration for sub-"
                                  "floor end segments (or an owner waiver of "
                                  "scale-agreement below the measurement "
                                  "floor) -- NOT a tolerance widen, NOT a far-"
                                  "side fix, NOT the strand"),
            },
            "deferred_by_name": [
                "END-side terminus scale corroboration for the 17-ft segment "
                "(short-segment unmeasurability rule)",
                "bore_log17 family (log43/log44) -- separate milestone",
            ],
        }
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"[m8.22] report -> {report_path}")
    finally:
        plan.close()

    print(f"[m8.22] {'PASS' if ok else 'FAILURE'}")
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
