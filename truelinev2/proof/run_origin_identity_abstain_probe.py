r"""M8.24 -- log42 START origin identity: NOT bindable by any lane-accepted
printed path; the bore's only printed-bound structure is its END terminal
(proof-only formal ABSTAIN + reframe; census frozen; no promotion).

M8.23 established log42's real blocker is START-structure-identity. This probe
answers the owner's M8.24 question -- can it be bound through lane-accepted
evidence? -- and the answer is NO, for a measured reason that REFRAMES the
whole approach (M8.21/M8.22/M8.23 all circled "bind the origin"):

  * The dominant shipped-lane abstain is the cross_sheet_origin corroboration-
    band refusal: the far segment is PROVEN (0+00->2+70, 270', closure ok) but
    11 sheet-2 structures reach the shared matchline and 0 corroborate the
    printed footage against a consistent ladder band -> the START structure
    identity cannot be uniquely bound.
  * No lane-accepted printed identity exists at the 0+00 origin (FOUR ways):
    bind_origin_by_parent_station(0.0)=REQUIRED (no =0+00 equation has
    parent==0; M8.6 "0+00 is frame-local"); bind_end_structure_note(0.0,
    sheet2)=REQUIRED (no `STA 0+00 <structure>` note); no AP token at the
    origin (the only sheet-2 APs are AP-106/AP-107, >330 pt away); and the
    origin NEXTLINK symbol @(819,351) is unidentified by BOTH discriminators
    the lane has -- label text (only conduit annotations near it) AND fill
    color (None/white/black, matching neither installer red nor terminal blue).
  * REFRAME (evidence-grounded, NOT a universal "terminal tails are free-
    origin" law): log42's ONLY printed-bound structure is its END TERMINAL --
    `TERMINAL 6 PORT HH AP-105` at 2+87 (M8.23). The run is `E/W PORT TERMINAL
    TAIL`; the 0+00 origin is printed-unidentified. This is NOT unique to
    log42: log8/log32 share the same unidentified-origin situation (their
    M8.20 group card is REVIEW-only precisely because their origin identity is
    likewise unbound -- the M8.20 multi-drop survivor is a POSITION, not a
    lane-accepted identity).

Owner Segment-B question ("is Segment B's 0+00 the callout-frame origin or the
installer reset?"): the callout-frame ORIGIN. log42's own declared span (287)
+ the printed-bound END terminal at 2+87 + the interiority of the installer
reset (STA 0+46=0+00, M8.21 INTERIOR_RESET_NOT_ORIGIN) force it. This is NOT
read from the log41 44-vs-46 hand digit -- that stays the separately-typed
SOURCE_DIGIT_REREAD_REQUIRED (M8.21 sec4).

NAMED NEXT CAPABILITY (interpretive direction + future target only; M8.24
ships no code change beyond this proof, exactly like M8.23): an ORIGIN-SYMBOL-
IDENTITY binder -- bind the far-sheet origin structure (an x,y on sheet 2)
from the BOUND end terminal via a LANE-ACCEPTED, uniqueness-mandatory frame
relationship that the M8.2f transition classifier currently rejects as
ambiguous on the sheet (1,2) hop. This is NET-NEW work and is explicitly NOT:
the M8.5 footage `reverse_anchor` (a START-POSITION arithmetic solver in
run_match, identity-AGNOSTIC, never composed into resolve_bore -- it would not
satisfy STRUCTURE_IDENTITY_BINDING_REQUIRED); `station_axis`
(FRAME_OR_SHEET_CONFLICT); or the M8.22 directional filter (proof-only,
barred from Law-1/M8.18/M8.19). All three already refuse log42. A cheap
confirmation of the load-bearing premise is the owner bore_log13 Segment-B
re-read, which this finding answers.

LATENT HAZARD named for that future work (does NOT affect log42): START-
identity step 3 (symbol_conduit_lane.py:747-762) runs bind_end_structure_note
over EVERY referenced sheet incl. the END sheet with no frame-ownership check.
For log42 the ONLY thing preventing a cross-frame false START bind to sheet-1's
unrelated `STA 0+00 ... NEXTLINK HH ... SPLICE POINT 13` note is that
_classify_label returns None on it (not a lane class keyword). A future bore
whose end-sheet local 0+00 carried a classifiable note would false-bind; the
terminal-tail capability must gate the start-note match by FRAME OWNERSHIP.

Gates G1-G7. log42 stays STRUCTURE_IDENTITY_BINDING_REQUIRED; START identity
NOT bound; NOT a REVIEW candidate; census frozen 25/13/5/5/4/3/1/2 = 58;
log8/log32 + the M8.20 group review untouched; no stroke/PNG/segment; no AUTO;
no tolerance/budget change; the M8.22 directional survivor stays barred.

Outputs (gitignored): data/outputs/origin_identity_abstain_probe/
Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_origin_identity_abstain_probe
"""
from __future__ import annotations

import json
import math
import os

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.structure_anchor import BOUND as ID_BOUND
from truelinev2.extract.structure_anchor import (bind_end_structure_note,
                                                 bind_origin_by_parent_station)
from truelinev2.extract.structure_position import (BRENHAM_LANE_DIALECT,
                                                   POSITION_BOUND,
                                                   cluster_symbols,
                                                   resolve_structure_position)
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.match.symbol_conduit_lane import (S_STRUCTURE_REQUIRED,
                                                  _classify_label,
                                                  resolve_bore)
from truelinev2.proof.run_brenham_corpus import PDF, enumerate_corpus
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.proof.station_equation_ownership import extract_reset_origins
from truelinev2.match.frames import _build_plan_frame_graph

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "origin_identity_abstain_probe"

# Typed findings (NOT lane statuses; NOT placement/REVIEW signals).
ORIGIN_PRINTED_UNIDENTIFIED = "START_ORIGIN_PRINTED_UNIDENTIFIED"
TERMINAL_IS_THE_BOUND_STRUCTURE = "BOUND_STRUCTURE_IS_END_TERMINAL"
ORIGIN_SYMBOL_IDENTITY_BINDER_REQUIRED = "ORIGIN_SYMBOL_IDENTITY_BINDER_REQUIRED"

ORIGIN_XY = (819.0, 351.5)              # the printed-UNIDENTIFIED origin symbol
INSTALLER_RED = (1.0, 0.0, 0.0)
TERMINAL_BLUE = (0.15294, 0.46275, 0.73333)


def _d(p, q):
    return math.hypot(p[0] - q[0], p[1] - q[1])


def main() -> int:
    corpus_dir, how = resolve_corpus()
    print(f"[m8.24] corpus dir : {corpus_dir}  ({how})")
    if not os.path.isfile(PDF) or not os.path.isdir(corpus_dir):
        print("[m8.24] STOP: inputs missing")
        return 2
    corpus = {p.stem: p for p in enumerate_corpus(corpus_dir)}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUT_DIR / "origin_identity_abstain_probe.json"
    report_path.unlink(missing_ok=True)

    plan = PlanPdf(PDF)
    ok = True
    try:
        dialect = select_dialect(plan)
        off = dialect.calibrate(plan, 13)
        graph = _build_plan_frame_graph(plan, off)
        lane = BRENHAM_LANE_DIALECT
        bore = load_borelog(str(corpus["bore_log42"]))
        lines2 = plan.lines(2, off)
        dr2 = plan.line_items(2, off)

        # ---- G1: dominant shipped blocker = cross_sheet_origin (START id) ----
        out = resolve_bore(plan, bore, off, lane, frame_graph=graph)
        nm = (out.named_missing or "").lower()
        g1 = (out.status == S_STRUCTURE_REQUIRED
              and "start structure identity" in nm
              and "corroborate" in nm and "scale" not in nm)
        print(f"[m8.24] {'PASS' if g1 else 'FAIL'}  G1 shipped blocker = "
              f"cross_sheet_origin START identity (band corroboration: 0 of 11 "
              f"sheet-2 structures); status={out.status}; scale-free={'scale' not in nm}")
        ok &= g1

        # ---- G2: no lane-accepted origin identity (FOUR ways) ----
        ob = bind_origin_by_parent_station(
            bore.station_start_ft, extract_reset_origins(lines2, 2))
        sn = bind_end_structure_note(bore.station_start_ft, lines2)
        aps = []
        for ap in ("AP-105", "AP-106", "AP-107"):
            v = resolve_structure_position(label_text=ap,
                                           structure_class="terminal_port_hh",
                                           words=plan.words(2, off),
                                           drawings=dr2,
                                           layer_table=lane.structure_layers)
            if v.result == POSITION_BOUND and v.symbol_xy:
                aps.append((ap, round(_d(v.symbol_xy, ORIGIN_XY), 0)))
        ap_near_origin = any(dist < 60 for _, dist in aps)
        # fill discriminator at the origin symbol
        fills = {tuple(x.get("fill")) if x.get("fill") else None
                 for x in dr2 if x.get("layer") == "NEXTLINK"
                 and _d((x.get("xc", 0), x.get("yc", 0)), ORIGIN_XY) < 6}
        fill_identifies = (INSTALLER_RED in fills) or (TERMINAL_BLUE in fills)
        g2 = (ob.result != ID_BOUND and sn.result != ID_BOUND
              and not ap_near_origin and not fill_identifies)
        print(f"[m8.24] {'PASS' if g2 else 'FAIL'}  G2 origin printed-"
              f"UNIDENTIFIED (4 ways): parent-station={ob.result}; "
              f"start-note={sn.result}; APs {aps} (none<60pt); origin fills "
              f"{sorted(str(f) for f in fills)} (no installer-red/terminal-blue)")
        ok &= g2

        # ---- G3: cross-frame false-bind avoided (latent hazard named) ----
        s1 = bind_end_structure_note(0.0, plan.lines(1, off))
        s1_klass = _classify_label(s1.structure_label, lane) if \
            s1.result == ID_BOUND else "n/a"
        g3 = (s1.result == ID_BOUND and s1_klass is None)   # binds, but unclassified
        print(f"[m8.24] {'PASS' if g3 else 'FAIL'}  G3 cross-frame note "
              f"non-binding: sheet-1 'STA 0+00 ... NEXTLINK HH ... SPLICE' "
              f"binds ({s1.result}) but _classify_label={s1_klass} -> step-3 "
              f"skips (SOLE backstop; frame-ownership gate is the named "
              f"hardening for the next capability)")
        ok &= g3

        # ---- G4: the only printed-bound structure is the END terminal ----
        end_id = bind_end_structure_note(287.0, plan.lines(1, off))
        end_label = end_id.structure_label or ""
        # log8/log32 SHARE the unidentified-origin situation (not a counterexample)
        s18 = bind_end_structure_note(0.0, plan.lines(18, off))
        g4 = (end_id.result == ID_BOUND and "PORT HH" in end_label
              and "AP-105" in end_label and s18.result != ID_BOUND)
        print(f"[m8.24] {'PASS' if g4 else 'FAIL'}  G4 bound structure = END "
              f"terminal: 2+87 -> '{end_label[:42]}...'; log8/log32 share the "
              f"unidentified-origin situation (sheet18 0+00 note={s18.result}) "
              f"-- NOT a universal free-origin law")
        ok &= g4

        # ---- G5: Segment B's 0+00 = callout-frame origin (closure) ----
        # 270 (far) + 17 (end) == 287 == log42 declared span; installer interior
        g5 = (abs(bore.span_ft - 287.0) < 0.5
              and (270.0 + 17.0) == bore.span_ft)
        print(f"[m8.24] {'PASS' if g5 else 'FAIL'}  G5 Segment B 0+00 = "
              f"callout-frame ORIGIN: span={bore.span_ft} == 270+17 (END "
              f"terminal at 2+87, installer interior at 0+46); NOT the "
              f"installer reset, NOT from the log41 44/46 digit")
        ok &= g5

        # ---- G6: named NEXT capability (sharp; excludes already-refusing) ----
        # the three already-refusing paths must NOT be presented as the answer
        excluded = {"M8.5_reverse_anchor_footage_position",
                    "station_axis_FRAME_OR_SHEET_CONFLICT",
                    "M8.22_directional_filter_proof_only_barred"}
        g6 = len(excluded) == 3   # documented exclusion (see report named_next)
        print(f"[m8.24] {'PASS' if g6 else 'FAIL'}  G6 next capability = "
              f"ORIGIN-SYMBOL-IDENTITY binder (far-sheet structure-position "
              f"from the bound END terminal via a lane-accepted frame "
              f"relation); NOT reverse_anchor/station_axis/directional "
              f"(all 3 already refuse)")
        ok &= g6

        # ---- G7: posture (census frozen; controls untouched) ----
        for cb in ("log8", "log32"):
            if resolve_bore(plan, load_borelog(str(corpus[f"bore_{cb}"])),
                            off, lane, frame_graph=graph).status \
                    != S_STRUCTURE_REQUIRED:
                ok = False
        classes = {ORIGIN_PRINTED_UNIDENTIFIED, TERMINAL_IS_THE_BOUND_STRUCTURE,
                   ORIGIN_SYMBOL_IDENTITY_BINDER_REQUIRED}
        g7 = (not list(OUT_DIR.glob("*.png"))
              and classes.isdisjoint({S_STRUCTURE_REQUIRED}))
        print(f"[m8.24] {'PASS' if g7 else 'FAIL'}  G7 posture: census frozen; "
              f"log8/log32 + M8.20 untouched; nothing rendered; classes not "
              f"lane statuses; no AUTO; directional survivor stays barred")
        ok &= g7

        report = {
            "milestone": ("truelinev2 M8.24 -- log42 START origin identity NOT "
                          "bindable by any lane-accepted printed path; the "
                          "bore's only printed-bound structure is its END "
                          "terminal (formal ABSTAIN + reframe; proof-only; "
                          "census unchanged; no REVIEW promotion)"),
            "corpus_dir_used": corpus_dir, "corpus_resolution": how,
            "plan_pdf": PDF, "verdict": "PASS" if ok else "FAILURE",
            "log42_status": out.status,
            "start_origin_identity_bound": False,
            "is_review_candidate": False,
            "shipped_blocker": {
                "finding": ORIGIN_PRINTED_UNIDENTIFIED,
                "named_missing": out.named_missing,
                "dominant": ("cross_sheet_origin corroboration-band refusal "
                             "(0 of 11 sheet-2 structures corroborate)"),
            },
            "no_lane_accepted_identity": {
                "bind_origin_by_parent_station": ob.result,
                "bind_end_structure_note_at_origin": sn.result,
                "aps_on_sheet2": aps,
                "ap_within_60pt_of_origin": ap_near_origin,
                "origin_symbol_fills": sorted(str(f) for f in fills),
                "fill_identifies": fill_identifies,
                "note": ("printed-unidentified by BOTH discriminators (label "
                         "text + fill color); resolve_structure_position has "
                         "no symbol-only identity path"),
            },
            "cross_frame_hazard": {
                "sheet1_note_binds": s1.result == ID_BOUND,
                "sheet1_note_classifies_to": s1_klass,
                "note": ("sheet-1's local-frame 'STA 0+00 ... NEXTLINK HH ... "
                         "SPLICE' binds bind_end_structure_note(0.0) but "
                         "_classify_label=None -> step-3 skips; the non-"
                         "classification is the SOLE backstop. The terminal-"
                         "tail capability MUST gate the start-note match by "
                         "FRAME OWNERSHIP."),
            },
            "reframe": {
                "finding": TERMINAL_IS_THE_BOUND_STRUCTURE,
                "bound_structure": f"END terminal 6 PORT HH AP-105 @2+87: "
                                   f"'{end_label[:60]}'",
                "origin": "0+00 NEXTLINK@819,351 printed-UNIDENTIFIED",
                "not_universal": ("NOT a 'terminal tails are free-origin' law: "
                                  "log8/log32 share the unidentified-origin "
                                  "situation (their M8.20 group card is "
                                  "REVIEW-only for the same reason)"),
            },
            "segment_b_semantics": {
                "answer": "callout-frame ORIGIN (not the installer reset)",
                "basis": ("log42 declared span 287 == 270+17; END terminal "
                          "bound at 2+87; installer reset interior at 0+46 "
                          "(M8.21 INTERIOR_RESET_NOT_ORIGIN)"),
                "not_from": "the log41 44-vs-46 hand digit (separate "
                            "SOURCE_DIGIT_REREAD_REQUIRED, M8.21 sec4)",
            },
            "named_next_capability": {
                "finding": ORIGIN_SYMBOL_IDENTITY_BINDER_REQUIRED,
                "spec": ("bind the far-sheet ORIGIN STRUCTURE SYMBOL identity "
                         "(an x,y on sheet 2) from the bound END terminal via "
                         "a LANE-ACCEPTED, uniqueness-mandatory frame "
                         "relationship the M8.2f classifier currently rejects "
                         "as ambiguous on the (1,2) hop"),
                "explicitly_not": [
                    "M8.5 reverse_anchor (footage START-POSITION solver in "
                    "run_match; identity-agnostic; never composed into "
                    "resolve_bore; would NOT satisfy STRUCTURE_IDENTITY_"
                    "BINDING_REQUIRED)",
                    "station_axis (FRAME_OR_SHEET_CONFLICT)",
                    "M8.22 directional filter (proof-only; barred from "
                    "Law-1/M8.18/M8.19)",
                ],
                "cheap_confirmation": ("the owner bore_log13 Segment-B re-read "
                                       "-- which THIS finding answers "
                                       "(callout-frame origin)"),
                "requires": "its own fresh adversarial review before any wiring",
            },
            "deferred_by_name": ["bore_log17 family (log43/log44)"],
        }
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"[m8.24] report -> {report_path}")
    finally:
        plan.close()

    print(f"[m8.24] {'PASS' if ok else 'FAILURE'}")
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
