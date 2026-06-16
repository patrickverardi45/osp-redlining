r"""LOG50 SPLICE-POINT-46 CALLOUT ROUTE ASSEMBLY -> full redline (PROOF ONLY; read-only; product-gated).

The missing source relationship for log50, supplied by the owner-pointed callouts: the bore's identity bridges
the two sheets NOT by AP-168 (which prints only on sheet 11) but by the SPLICE 46 callout pair --
``PROP. SPLICE POINT 46`` on sheet 10 (the STA 45+33=0+00 NEXTLINK HH that IS the splice enclosure) <->
``AP-168 SPLICE LOC 46`` on sheet 11 (the STA 1+89 port HH served by that splice). The correct start is the
splice-point-46 NEXTLINK HH (STA 45+33=0+00), NOT the STA 0+55 installer HH the station-corridor solver wrongly
chose. Anchoring at that UNIQUE start and tracing FORWARD to the matchline (instead of backward from the
ambiguous matchline) resolves the sheet-10 origin ambiguity.

Full source-backed route (all four links printed/drawn):
  sheet 10 :  SPLICE POINT 46 NEXTLINK HH @ STA 45+33=0+00 (local 0+00)  --BORE-PORT-->  MATCHLINE STA 1+39   (139')
  matchline:  STA 1+39 sheet 10  ==  STA 1+39 sheet 11  (continuous station, printed both sides)
  sheet 11 :  MATCHLINE STA 1+39  --BORE-PORT-->  AP-168 PORT HH @ STA 1+89 (SPLICE LOC 46)   (50')
  sheet 11 :  STA 1+89  --BORE-VACANT (DROP)-->  FLOWER POT @ STA 5+14                          (325')
  closure  :  139 + 50 + 325 = 514 ft = the bore span

Renders TWO sheet-local red REVIEW strokes (the log53/log71 cross-sheet pattern: legs joined by the printed
station identity at STA 1+39; cross-sheet coordinate translation is not invented). Each leg's drawn length
matches its printed station delta; every route vertex is a real drawn dash endpoint. The bridge is source-
backed by PROP. SPLICE POINT 46 / AP-168 SPLICE LOC 46 / MATCHLINE STA 1+39 / the printed run callouts.

No AP-168 required on sheet 10. No mainline-ruler cut (the end is the drawn FLOWER POT). Not the sheet-11 leg
alone (both legs drawn). 0+00->1+39 not omitted (it IS the sheet-10 leg). No nearest/length picking (the splice-
46 bridge + the matchline crossing select the route). No fixture mutation. No coordinate encoding. No owner
naming. No review-choice. No classification/seam/ledger. No product/runtime/api/backend/web/deploy/main. Red
strokes only. PNG/JSON under the gitignored data/outputs path.

Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_log50_splice46_route_assembly_slice
"""
from __future__ import annotations

import json
import math
import os

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.conduit_topology import MAX_DASH_GAP, connected_chain, dash_endpoints, symbol_footprint
from truelinev2.extract.matchline_join import extend_dash_to_boundary, matchline_bboxes
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.structure_position import (
    BRENHAM_CONDUIT_LAYERS, BRENHAM_STRUCTURE_LAYERS, POSITION_BOUND, cluster_symbols,
    resolve_nextlink_hh_callout, resolve_structure_position,
)
from truelinev2.ingest.manual_adjudication import (
    activation_summary, apply_adjudications, load_adjudication, parent_run_duplicate_check,
)
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.proof.run_brenham_corpus import EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_log59_render_artifact_slice import (
    interior_vertices_are_dash_endpoints, route_edges_source_backed,
)
from truelinev2.proof.run_log71_render_artifact_slice import order_chain_route, route_length
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.render.crop import REDLINE_STROKE_RGB, render_redline_stroke
from truelinev2.stations import parse_station

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "log50_splice46_route_assembly"
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / "final_engine_truth_table.json"
FROZEN_BUCKETS = {"DRAWABLE_REVIEW": 31, "HUMAN_ADJUSTABLE_REVIEW": 6,
                  "OUT_OF_CLASS": 1, "PICK_CARD_REVIEW": 17, "SOURCE_OR_KMZ_REQUIRED": 3}
ABSTAIN_4 = ("log5", "log31", "log38", "log43")
PORT = BRENHAM_CONDUIT_LAYERS["TERMINAL TAIL"]       # BORE - PORT (terminal tail)
VAC = BRENHAM_CONDUIT_LAYERS["VACANT HDPE"]          # BORE - VACANT PIPE (drop)
SCALE = 1.44                                          # Brenham drawn pts/ft
LEN_REL_TOL = 0.08                                    # each leg's drawn length vs printed station delta

R_RENDERED = "LOG50_FULL_REDLINE_RENDERED"
R_BLOCKED = "LOG50_SPLICE46_BLOCKED"
B_SCOPE = "BLOCKED_SPLICE46_SCOPE_VIOLATION"
ALLOWED = {R_RENDERED, R_BLOCKED, B_SCOPE}


def _census_frozen(doc) -> bool:
    if not TRUTH.is_file():
        return False
    baseline = {r["bore_id"]: dict(r) for r in json.loads(TRUTH.read_text(encoding="utf-8"))["rows"]}
    off = apply_adjudications(baseline, enabled=False)
    on = apply_adjudications(baseline, enabled=True, doc=doc)
    summ = activation_summary(on)
    buckets = {}
    for r in off.values():
        buckets[r["completion_bucket"]] = buckets.get(r["completion_bucket"], 0) + 1
    return (off is baseline and buckets == FROZEN_BUCKETS
            and summ["manual_review_drawable"] == 22 and summ["manual_source_verification"] == 1
            and summ["manual_abstain"] == 4
            and on["log44"]["adjudication"]["drawable_status"] == "non_drawable"
            and all(on[l]["adjudication"]["drawable_status"] == "abstain" for l in ABSTAIN_4)
            and not parent_run_duplicate_check(doc))


def _ml_at_x(drawings, x_target):
    """The drawn matchline whose vertical line is at x_target (sheet 10's STA 1+39 is the right edge x~1141)."""
    return next((bb for bb in matchline_bboxes(drawings, "MATCHLINE")
                 if abs((bb[0] + bb[2]) / 2 - x_target) < 5), None)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.png"):
        stale.unlink()
    doc = load_adjudication()
    ev, gates, rendered = {}, [("G0 engine census frozen (OFF 31/6/1/17/3, ON 22/1/4, log44+abstains held)",
                                _census_frozen(doc), None)], []
    if not os.path.isfile(PDF):
        return _emit(gates, B_SCOPE, ev, rendered)
    corpus = {p.stem: p for p in enumerate_corpus(resolve_corpus()[0])}
    gates.append(("G1 plan PDF + corpus present", os.path.isfile(PDF) and len(corpus) == EXPECTED_COUNT, None))

    plan = PlanPdf(PDF)
    try:
        off = select_dialect(plan).calibrate(plan, 13)
        bore = load_borelog(str(corpus["bore_log50"]))
        ev["span_ft"] = bore.span_ft

        # source identity bridge: PROP. SPLICE POINT 46 (sheet 10) <-> AP-168 SPLICE LOC 46 (sheet 11)
        s10_point46 = sum(1 for ln in plan.lines(10, off) if "SPLICE POINT 46" in ln.upper())
        s11_ap168_loc46 = sum(1 for ln in plan.lines(11, off)
                              if "AP-168" in ln.upper() and "SPLICE LOC 46" in ln.upper())
        bridge_ok = s10_point46 == 1 and s11_ap168_loc46 == 1
        ev["splice46_bridge"] = {"sheet10_PROP_SPLICE_POINT_46": s10_point46,
                                 "sheet11_AP168_SPLICE_LOC_46": s11_ap168_loc46, "bridge_source_backed": bridge_ok}
        gates.append(("G2 splice-46 bridge source-backed (PROP. SPLICE POINT 46 s10 <-> AP-168 SPLICE LOC 46 s11)",
                      bridge_ok, f"s10={s10_point46} s11={s11_ap168_loc46}"))

        # SHEET-10 leg: STA 45+33=0+00 splice-point-46 NEXTLINK HH -> MATCHLINE STA 1+39 (local 0+00->1+39 = 139')
        dr10 = plan.line_items(10, off)
        sv = resolve_nextlink_hh_callout(station_sta="45+33", words=plan.words(10, off), drawings=dr10,
                                         callout_layer="ANNOTATION", symbol_layer="NEXTLINK")
        start = tuple(sv.symbol_xy) if sv.result == POSITION_BOUND else None
        ml10 = _ml_at_x(dr10, 1141)   # sheet-10 STA 1+39 - SEE SHEET 11 is the right vertical edge
        ch10 = connected_chain([x for x in dr10 if x["layer"] == PORT], symbol_footprint(dr10, "NEXTLINK", start)) if start else []
        b10 = extend_dash_to_boundary(ch10, ml10) if (ch10 and ml10) else None
        rt10 = order_chain_route(ch10, start, b10) if b10 else None
        tail139 = (parse_station("1+39") - parse_station("0+00")) * SCALE
        s10_ok = bool(rt10 and len(rt10) >= 3 and rt10[0] == tuple(start) and route_edges_source_backed(rt10, ch10)
                      and interior_vertices_are_dash_endpoints(rt10, ch10)
                      and abs(route_length(rt10) - tail139) <= LEN_REL_TOL * tail139)
        ev["sheet10_leg"] = {"start_xy": [round(v, 1) for v in start] if start else None,
                             "start_bind": sv.result, "matchline_boundary": [round(v, 1) for v in b10] if b10 else None,
                             "route_vertices": len(rt10) if rt10 else 0,
                             "route_len_pt": round(route_length(rt10), 1) if rt10 else None,
                             "expected_pt_139ft": round(tail139, 1), "source_backed": s10_ok}
        gates.append(("G3 sheet-10 leg: splice-46 NEXTLINK HH @45+33 -> matchline 1+39, source-backed, ~139'",
                      s10_ok, None))

        # SHEET-11 leg: MATCHLINE STA 1+39 -> AP-168 PORT HH @1+89 -> FLOWER POT @5+14 (50'+325' = 375')
        dr11 = plan.line_items(11, off)
        pv = resolve_structure_position(label_text="5+14", structure_class="flower_pot", words=plan.words(11, off),
                                        drawings=dr11, layer_table=BRENHAM_STRUCTURE_LAYERS,
                                        context_texts=("FLOWER", "POT"))
        pot = tuple(pv.symbol_xy) if pv.result == POSITION_BOUND else None
        ch11 = connected_chain([x for x in dr11 if x["layer"] in (PORT, VAC)],
                               symbol_footprint(dr11, "FLOWER POT", pot)) if pot else []
        b11 = None
        for bb in matchline_bboxes(dr11, "MATCHLINE"):
            bx = extend_dash_to_boundary(ch11, bb)
            if bx:
                b11 = bx
        rt11 = order_chain_route(ch11, b11, pot) if b11 else None
        # the AP-168 PORT HH symbol, DERIVED from source: the NEXTLINK cluster nearest the printed 'AP-168'
        # label on sheet 11 (no hardcoded coordinate). The sheet-11 leg must thread it (tail/drop junction).
        ap168_lbl = next((w for w in plan.words(11, off) if "AP-168" in w["text"].upper()), None)
        nl11 = cluster_symbols(dr11, "NEXTLINK")
        ap168_hh = (min(nl11, key=lambda c: math.hypot(c.x - ap168_lbl["xc"], c.y - ap168_lbl["yc"]))
                    if (ap168_lbl and nl11) else None)
        ap168_hh = (ap168_hh.x, ap168_hh.y) if ap168_hh is not None else None
        through_ap168 = bool(rt11 and ap168_hh
                             and min(math.hypot(ap168_hh[0] - v[0], ap168_hh[1] - v[1]) for v in rt11) <= MAX_DASH_GAP)
        leg375 = (parse_station("5+14") - parse_station("1+39")) * SCALE
        s11_ok = bool(rt11 and len(rt11) >= 3 and rt11[-1] == tuple(pot) and route_edges_source_backed(rt11, ch11)
                      and interior_vertices_are_dash_endpoints(rt11, ch11) and through_ap168
                      and abs(route_length(rt11) - leg375) <= LEN_REL_TOL * leg375)
        ev["sheet11_leg"] = {"matchline_boundary": [round(v, 1) for v in b11] if b11 else None,
                             "pot_xy": [round(v, 1) for v in pot] if pot else None,
                             "ap168_hh_xy_source_derived": [round(v, 1) for v in ap168_hh] if ap168_hh else None,
                             "through_ap168_hh": through_ap168, "route_vertices": len(rt11) if rt11 else 0,
                             "route_len_pt": round(route_length(rt11), 1) if rt11 else None,
                             "expected_pt_375ft": round(leg375, 1), "source_backed": s11_ok}
        gates.append(("G4 sheet-11 leg: matchline 1+39 -> AP-168 HH @1+89 -> FLOWER POT @5+14, source-backed, ~375'",
                      s11_ok, None))

        # matchline continuous-station + closure
        ml_both = (any("1+39" in ln and "SHEET 11" in ln.upper() for ln in plan.lines(10, off) if "MATCHLINE" in ln.upper())
                   and any("1+39" in ln and "SHEET 10" in ln.upper() for ln in plan.lines(11, off) if "MATCHLINE" in ln.upper()))
        closure = abs(139.0 + 375.0 - bore.span_ft) <= 0.5
        ev["matchline_join"] = {"sta_1+39_both_sheets": ml_both, "closure_139+375": 139.0 + 375.0,
                                "span_ft": bore.span_ft, "closes": closure}
        gates.append(("G5 continuous-station matchline 1+39 (both sheets) + closure 139+375==514", ml_both and closure, None))

        full_ok = bridge_ok and s10_ok and s11_ok and ml_both and closure
        if full_ok:
            png10 = render_redline_stroke(
                plan, "log50", 10, off, rt10, status="REVIEW",
                reason=("log50 sheet-10 leg: SPLICE POINT 46 NEXTLINK HH @ STA 45+33=0+00 (local 0+00) -> "
                        "MATCHLINE STA 1+39 (139'); BORE-PORT terminal tail. Bridge: PROP. SPLICE POINT 46 <-> "
                        "AP-168 SPLICE LOC 46 (sheet 11). Full bore 0+00->5+14 continues on sheet 11."),
                out_dir=str(OUT_DIR), mandatory_points=[start, b10], pad=150.0)
            png11 = render_redline_stroke(
                plan, "log50", 11, off, rt11, status="REVIEW",
                reason=("log50 sheet-11 leg: MATCHLINE STA 1+39 -> AP-168 PORT HH @ STA 1+89 (SPLICE LOC 46) -> "
                        "FLOWER POT @ STA 5+14 (375'). Full bore = 139'+375' = 514' = span; joined to sheet 10 "
                        "by the STA 1+39 station identity."),
                out_dir=str(OUT_DIR), mandatory_points=[b11, ap168_hh, pot], pad=150.0)
            if png10 and png11 and os.path.isfile(png10) and os.path.isfile(png11):
                rendered = [("log50_s10", png10), ("log50_s11", png11)]
                ev["result"] = "FULL_REDLINE_RENDERED_TWO_LEGS"
                ev["artifacts"] = [os.path.basename(png10), os.path.basename(png11)]
            else:
                ev["result"] = "RENDER_RETURNED_NO_PNG"
        else:
            ev["result"] = R_BLOCKED
            ev["missing"] = "; ".join(n for n, x, _ in gates if not x)
    finally:
        plan.close()

    gates.append(("G6 BOTH sheet legs rendered (full bore; never the sheet-11 leg alone)", len(rendered) == 2, None))
    result = R_RENDERED if len(rendered) == 2 else R_BLOCKED
    return _emit(gates, result, ev, rendered)


def _emit(gates, result, ev, rendered) -> int:
    gates.append(("G7 canonical red stroke color (TrueLine strokes are red)", REDLINE_STROKE_RGB == (220, 25, 25), None))
    gates.append(("G8 result in allowed enum", result in ALLOWED, result))
    all_pass = all(x for _, x, _ in gates)
    report = {
        "milestone": "LOG50 SPLICE-POINT-46 ROUTE ASSEMBLY -> full redline (proof only; read-only)",
        "verdict": "PASS" if all_pass else "FAIL", "result": result, "target_log": "log50",
        "newly_rendered_full": ["log50"] if len(rendered) == 2 else [],
        "newly_rendered_partial": [],
        "artifact_paths": [str(p).replace(str(_REPO_ROOT), "").lstrip("\\/").replace("\\", "/") for _, p in rendered],
        "still_blocked": [] if len(rendered) == 2 else ["log50"],
        "exact_blocker": ev.get("missing"),
        "evidence": ev, "red_stroke_rgb": list(REDLINE_STROKE_RGB),
        "no_fixture_mutation": True, "no_coordinate_encoding": True, "no_owner_naming": True,
        "no_review_choice": True, "no_ap168_required_on_sheet10": True, "engine_census_frozen": True,
        "artifacts_gitignored": True,
        "gates": [{"name": n, "pass": bool(x), "detail": d} for n, x, d in gates],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "log50_splice46_route_assembly.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[splice46] result: {result}")
    for k in ("splice46_bridge", "sheet10_leg", "sheet11_leg", "matchline_join"):
        print(f"[splice46]   {k}: {ev.get(k)}")
    for nm, p in rendered:
        print(f"[splice46]   ARTIFACT: {os.path.basename(p)}")
    for n, x, _ in gates:
        print(f"[splice46] {'PASS' if x else 'FAIL'}  {n}")
    print(f"[splice46] VERDICT: {'PASS' if all_pass else 'FAIL'}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
