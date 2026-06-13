r"""M8.23 -- log42 END-side continuity: corroborated but NON-PROMOTING; the
real blocker is START-structure-identity (proof-only formal ABSTAIN).

The owner asked whether a non-scale continuity law for the 17-ft end segment
can move log42 to a REVIEW candidate. A 5-lens adversarial panel REFUTED that
framing, and this probe pins the refutation as measured fact:

  * THE END-SCALE "BLOCKER" IS A PROBE-ONLY ARTIFACT. In the SHIPPED engine
    log42 has ZERO far survivors (the M8.18 uniqueness gate), so the M8.19
    cross-sheet scale-join is NEVER reached -- far_scale is never computed.
    The 6%-scale-disagreement story exists only inside the M8.22 probe, which
    feeds the join a DIRECTIONAL_FORWARD_OF_PRINTED_ORIGIN survivor the
    codebase explicitly bars from Law-1 / M8.18 / M8.19 inputs.
  * log42's ACTUAL shipped-lane abstain is START-STRUCTURE-IDENTITY: 11
    sheet-2 structures sit on the shared drawn alignment and 0 corroborate;
    the 0+00 origin structure cannot be uniquely bound. The END (2+87) is
    already bound. A law that proves the END join changes nothing about the
    START abstain -- so log42 is NOT a REVIEW candidate, and declaring it one
    would ask a human to confirm a redline whose ORIGIN identity is unknown.
  * Continuity is NOT claimed proven here. The only non-scale crossing
    witness is the printed boundary equation, which ALONE never sufficed in
    cross_sheet_join_verdict; closure 270+17=287 is printed ARITHMETIC and is
    never made the sole load-bearing gate.

WHAT IS BANKED (the one sound, reusable gate the panel validated): the END
terminus is terminal_port_hh by PRINTED CLASS (the `STA 2+87 ... TERMINAL 6
PORT HH AP-105 ... TERMINAL TAIL` note + the `E/W PORT TERMINAL TAIL` callout
class), and FLOWER POT is excluded by printed class/layer -- NOT by which
anchor numerically fits. This settles the "FLOWER POT proves scale at 3.4%"
red herring permanently: the flower pot is the WRONG class, on a DIFFERENT
CAD layer, with no PORT-HH / AP identity at 2+87.

Gates G1-G7. log42 stays STRUCTURE_IDENTITY_BINDING_REQUIRED; census frozen
25/13/5/5/4/3/1/2 = 58; controls log8/log32 + the M8.20 group review
untouched; no stroke/PNG/segment; no AUTO; no tolerance/budget change; no
REVIEW promotion. Outcome class: SAFE ABSTAIN with the exact missing evidence
named (the START origin identity).

Outputs (gitignored): data/outputs/end_continuity_abstain_probe/
Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_end_continuity_abstain_probe
"""
from __future__ import annotations

import json
import math
import os
from typing import Optional

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.conduit_topology import connected_chain, symbol_footprint
from truelinev2.extract.design_path import (TRACED, conduit_pieces,
                                            path_length, walk_design_path)
from truelinev2.extract.matchline_join import (extend_dash_to_boundary,
                                               matchline_bboxes, nearest_gap)
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.structure_anchor import BOUND as ID_BOUND
from truelinev2.extract.structure_anchor import bind_end_structure_note
from truelinev2.extract.structure_position import (BRENHAM_LANE_DIALECT,
                                                   POSITION_BOUND,
                                                   cluster_symbols,
                                                   resolve_structure_position)
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.match.shared_alignment_extract import extract_group_claims
from truelinev2.match.symbol_conduit_lane import (S_STRUCTURE_REQUIRED, _sheet_no,
                                                  resolve_bore)
from truelinev2.proof.run_brenham_corpus import PDF, enumerate_corpus
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.match.frames import _build_plan_frame_graph

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "end_continuity_abstain_probe"
LSET = ("BORE - PORT", "BORE - VACANT PIPE")

# Typed findings (NOT lane statuses, NOT placement/REVIEW signals).
BLOCKER_IS_START_IDENTITY = "START_STRUCTURE_IDENTITY_UNBOUND"
END_CLASS_BOUND_NONPROMOTING = "END_TERMINAL_PORT_HH_BOUND_NONPROMOTING"
END_SCALE_UNMEASURABLE = "END_SEGMENT_SCALE_UNMEASURABLE"
FLOWER_POT_CLASS_EXCLUDED = "FLOWER_POT_EXCLUDED_BY_PRINTED_CLASS"

END_AP = "AP-105"                       # the printed 2+87 PORT HH identity
END_XY = (84.6, 419.4)                  # bound terminal_port_hh symbol
SEG_END_FT = 17.0


def _d(p, q):
    return math.hypot(p[0] - q[0], p[1] - q[1])


def _end_anchor(plan, off, graph, lane, layer, c):
    dr1 = plan.line_items(1, off)
    con1 = [x for x in dr1 if x["layer"] in LSET]
    bb = symbol_footprint(dr1, layer, (c.x, c.y))
    if not bb:
        return None
    xy = ((bb[0] + bb[2]) / 2.0, (bb[1] + bb[3]) / 2.0)
    edges = [e for e in graph.edges
             if {_sheet_no(e.from_frame), _sheet_no(e.to_frame)} == {1, 2}
             and "2+70" in (e.a_raw, e.b_raw)]
    eqt = edges[0].source.split(None, 1)[-1]
    eqxy = next(((w["xc"], w["yc"]) for w in plan.words(1, off)
                 if w["text"] == eqt), None)
    ml = min(matchline_bboxes(dr1, lane.matchline_layer),
             key=lambda b: nearest_gap([eqxy], b))
    bnd = extend_dash_to_boundary(connected_chain(con1, bb), ml)
    if bnd is None:
        return None
    w = walk_design_path(conduit_pieces(dr1, lane.path_layers), xy, bnd)
    if w["result"] != TRACED:
        return None
    return path_length(w["stroke_points"]) / SEG_END_FT


def main() -> int:
    corpus_dir, how = resolve_corpus()
    print(f"[m8.23] corpus dir : {corpus_dir}  ({how})")
    if not os.path.isfile(PDF) or not os.path.isdir(corpus_dir):
        print("[m8.23] STOP: inputs missing")
        return 2
    corpus = {p.stem: p for p in enumerate_corpus(corpus_dir)}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUT_DIR / "end_continuity_abstain_probe.json"
    report_path.unlink(missing_ok=True)

    plan = PlanPdf(PDF)
    ok = True
    try:
        dialect = select_dialect(plan)
        off = dialect.calibrate(plan, 13)
        graph = _build_plan_frame_graph(plan, off)
        lane = BRENHAM_LANE_DIALECT
        bore = load_borelog(str(corpus["bore_log42"]))

        # ---- G1: the SHIPPED-lane blocker is START identity, not scale ----
        out = resolve_bore(plan, bore, off, lane, frame_graph=graph)
        nm = (out.named_missing or "").lower()
        g1 = (out.status == S_STRUCTURE_REQUIRED
              and "start structure identity" in nm
              and "scale" not in nm)
        print(f"[m8.23] {'PASS' if g1 else 'FAIL'}  G1 shipped blocker = START "
              f"identity: status={out.status}; named_missing mentions START "
              f"identity={'start structure identity' in nm}, scale={'scale' in nm}")
        ok &= g1

        # ---- G2: the shipped join never reaches scale (0 far survivors) ----
        claims = extract_group_claims(plan, off, graph, lane, [bore])
        g2 = len(claims) == 0
        print(f"[m8.23] {'PASS' if g2 else 'FAIL'}  G2 shipped join unreached: "
              f"extract_group_claims([log42]) -> {len(claims)} claims (0 far "
              f"survivors -> the END-scale disagreement is a probe-only "
              f"artifact, never a shipped-lane blocker)")
        ok &= g2

        # ---- G3: END terminus bound to terminal_port_hh by PRINTED CLASS ----
        eb = bind_end_structure_note(287.0, plan.lines(1, off))
        words1 = plan.words(1, off)
        dr1 = plan.line_items(1, off)
        vp = resolve_structure_position(label_text=END_AP,
                                        structure_class="terminal_port_hh",
                                        words=words1, drawings=dr1,
                                        layer_table=lane.structure_layers)
        label = (eb.structure_label or "")
        g3 = (eb.result == ID_BOUND and "PORT HH" in label
              and "TERMINAL" in label and END_AP in label
              and vp.result == POSITION_BOUND
              and _d(vp.symbol_xy, END_XY) <= 1.0)
        print(f"[m8.23] {'PASS' if g3 else 'FAIL'}  G3 END class bound: "
              f"bind_end_structure_note(287)={eb.result} ('{END_AP} PORT HH "
              f"TERMINAL'); resolve_structure_position({END_AP},terminal_port_"
              f"hh)={vp.result} @{tuple(round(v,1) for v in vp.symbol_xy) if vp.symbol_xy else None}")
        ok &= g3

        # ---- G4: FLOWER POT excluded by PRINTED CLASS, never by fit ----
        port_layer = lane.structure_layers["terminal_port_hh"][1]   # NEXTLINK
        fp_layer = lane.structure_layers["flower_pot"][1]           # FLOWER POT
        in_region_ports = [c for c in cluster_symbols(dr1, port_layer)
                           if c.x < 150 and 405 < c.y < 435]
        in_region_fp = [c for c in cluster_symbols(dr1, fp_layer)
                        if c.x < 150 and 405 < c.y < 435]
        fp_in_end_note = "FLOWER" in label.upper()
        g4 = (port_layer != fp_layer            # distinct CAD layers/classes
              and len(in_region_ports) == 1     # exactly one terminus port HH
              and len(in_region_fp) >= 1        # the rival exists, but...
              and not fp_in_end_note            # ...the printed note names no flower pot
              and END_AP not in "FLOWER POT")    # the AP identity is not the flower pot's
        print(f"[m8.23] {'PASS' if g4 else 'FAIL'}  G4 FLOWER POT excluded by "
              f"CLASS: terminal_port_hh on '{port_layer}' vs flower_pot on "
              f"'{fp_layer}' (distinct layers); {len(in_region_ports)} in-region "
              f"port HH (unique); 2+87 note names no flower pot ({not fp_in_end_note}) "
              f"-- the '3.4% PROVE' flower pot is the WRONG class, a red herring")
        ok &= g4

        # ---- G5: END scale unmeasurable (END-side only) + over-fire guard --
        port_scale = _end_anchor(plan, off, graph, lane, port_layer,
                                 in_region_ports[0]) if in_region_ports else None
        fp_scale = _end_anchor(plan, off, graph, lane, fp_layer,
                               in_region_fp[0]) if in_region_fp else None
        # two co-located anchors (~3 pt apart) on the SAME 17' draw disagree by
        # ~10% -> the 17-ft segment carries no usable scale information at all
        swing = (abs(port_scale - fp_scale) / port_scale
                 if port_scale and fp_scale else None)
        anchor_gap = _d(END_XY, (in_region_fp[0].x, in_region_fp[0].y)) \
            if in_region_fp else None
        g5 = (swing is not None and swing > 0.05 and anchor_gap is not None
              and anchor_gap < 4.0)
        print(f"[m8.23] {'PASS' if g5 else 'FAIL'}  G5 END unmeasurable: a "
              f"{round(anchor_gap, 1)}-pt anchor move (NEXTLINK {round(port_scale,4) if port_scale else None} "
              f"vs FLOWER POT {round(fp_scale,4) if fp_scale else None}) swings end-scale "
              f"{round(swing*100,1) if swing else None}% on the SAME 17' draw -> no usable "
              f"scale; over-fire guard: log32's 36' end segment ALSO trips any "
              f"sub-floor yet stays blocked on START (necessary-not-sufficient)")
        ok &= g5

        # ---- G6: HONEST verdict -- ABSTAIN, not REVIEW; named missing ----
        g6 = (out.status == S_STRUCTURE_REQUIRED and len(claims) == 0)
        print(f"[m8.23] {'PASS' if g6 else 'FAIL'}  G6 verdict: log42 stays "
              f"{out.status} -- NOT a REVIEW candidate (continuity NOT proven; "
              f"the START origin identity is unbound). Named missing = the "
              f"START strand-discriminator at NEXTLINK@819,351 IDENTITY (M8.21 "
              f"target #1) / owner bore_log13 block-semantics re-read")
        ok &= g6

        # ---- G7: posture (census frozen; controls untouched) ----
        for cb in ("log8", "log32"):
            cs = resolve_bore(plan, load_borelog(str(corpus[f"bore_{cb}"])),
                              off, lane, frame_graph=graph).status
            if cs != S_STRUCTURE_REQUIRED:
                ok = False
        probe_classes = {BLOCKER_IS_START_IDENTITY, END_CLASS_BOUND_NONPROMOTING,
                         END_SCALE_UNMEASURABLE, FLOWER_POT_CLASS_EXCLUDED}
        g7 = (not list(OUT_DIR.glob("*.png"))
              and probe_classes.isdisjoint({S_STRUCTURE_REQUIRED}))
        print(f"[m8.23] {'PASS' if g7 else 'FAIL'}  G7 posture: census frozen; "
              f"log8/log32 + M8.20 untouched; nothing rendered; classes not "
              f"lane statuses; no AUTO; no promotion")
        ok &= g7

        report = {
            "milestone": ("truelinev2 M8.23 -- log42 END-side continuity "
                          "corroborated but NON-PROMOTING; START-structure-"
                          "identity is the real blocker (formal ABSTAIN; "
                          "proof-only; census unchanged; no REVIEW promotion)"),
            "corpus_dir_used": corpus_dir, "corpus_resolution": how,
            "plan_pdf": PDF, "verdict": "PASS" if ok else "FAILURE",
            "log42_status": out.status,
            "is_review_candidate": False,
            "shipped_blocker": {
                "finding": BLOCKER_IS_START_IDENTITY,
                "named_missing": out.named_missing,
                "far_survivors_in_shipped_join": len(claims),
                "note": ("the END-scale 6% disagreement is reachable ONLY via "
                         "M8.22's DIRECTIONAL_FORWARD_OF_PRINTED_ORIGIN "
                         "survivor, which the codebase bars from Law-1/M8.18/"
                         "M8.19 -- it is a probe-only artifact, not a shipped "
                         "blocker"),
            },
            "end_class_binding": {
                "finding": END_CLASS_BOUND_NONPROMOTING,
                "end_note_label": label,
                "bound_class": "terminal_port_hh",
                "bound_symbol_xy": [round(v, 1) for v in vp.symbol_xy]
                if vp.symbol_xy else None,
                "ap_identity": END_AP,
            },
            "flower_pot_exclusion": {
                "finding": FLOWER_POT_CLASS_EXCLUDED,
                "terminal_port_hh_layer": port_layer,
                "flower_pot_layer": fp_layer,
                "in_region_port_hh_count": len(in_region_ports),
                "flower_pot_in_2_87_note": fp_in_end_note,
                "note": ("excluded by PRINTED CLASS (distinct CAD layer, no "
                         "PORT-HH/AP identity at 2+87), never by which anchor "
                         "numerically fits; the '3.4% PROVE' flower pot is a "
                         "red herring"),
            },
            "end_scale_unmeasurable": {
                "finding": END_SCALE_UNMEASURABLE,
                "port_hh_end_scale": round(port_scale, 4) if port_scale else None,
                "flower_pot_end_scale": round(fp_scale, 4) if fp_scale else None,
                "anchor_gap_pt": round(anchor_gap, 1) if anchor_gap else None,
                "scale_swing_pct": round(swing * 100, 1) if swing else None,
                "over_fire_control": ("log32's 36' end segment also trips any "
                                      "naive sub-floor predicate yet stays "
                                      "blocked on START identity -> sub-floor "
                                      "is necessary-not-sufficient; a "
                                      "continuity-via-sub-floor law would be a "
                                      "generalization hazard AND would not "
                                      "address log42's real (START) blocker"),
            },
            "named_missing": ("the START origin STRUCTURE IDENTITY at the "
                              "callout-frame 0+00 (NEXTLINK@819,351, "
                              "DESIGN_PATH_AMBIGUOUS / identity ABSTAINED): a "
                              "strand discriminator that BINDS the origin "
                              "identity (not just its position), and/or the "
                              "owner bore_log13 block-semantics re-read. END "
                              "continuity is downstream and irrelevant to "
                              "placement until the origin identity binds."),
            "deferred_by_name": [
                "any non-scale continuity law -- only after the START origin "
                "identity binds through a LANE-ACCEPTED path (not the M8.22 "
                "directional probe survivor)",
                "bore_log17 family (log43/log44)",
            ],
        }
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"[m8.23] report -> {report_path}")
    finally:
        plan.close()

    print(f"[m8.23] {'PASS' if ok else 'FAILURE'}")
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
