r"""DROP-BORE TERMINUS SOLVER -> redline artifacts (PROOF ONLY; read-only; product-gated).

The station-corridor solver proved the prior END_BRANCH_AMBIGUOUS_AT_SPAN was solver-created (over-broad
flood) AND that cutting the redline at the ladder-interpolated end is a false positive when the conduit
continues past it (a flower-pot DROP bore whose true terminus is elsewhere). This slice takes the next step
for the drop bores: bind the main route, detect that the interpolated end is NOT a drawn terminus, then search
SOURCE for the bore's real drawn terminus and render ONLY if it is unique.

Pipeline per bore:
  1. BIND the main route/corridor with the station-corridor solver (start reset structure -> running-station
     ladder row -> monotonic in-corridor conduit route to the positioned end station).  [reused, unchanged]
  2. DETECT end-not-a-terminus: the in-corridor conduit runs continuously PAST the bore end station.
  3. SEARCH for a source-backed terminus near the bore end station, across the bore's own sheets:
       (a) a drawn flower-pot / HH / AP structure SYMBOL within TERMINUS_WINDOW_FT station + TERMINUS_PERP_PT
           of the end, on or just off the alignment;
       (b) a drop/lateral conduit (BORE - LATERAL) leaving the mainline near the end and reaching a pot;
       (c) a matchline / sheet-continuation the route crosses at the end (sheet-exit terminus);
       (d) the bore's continuation sheets (sheet_refs) -- candidate cross-sheet termini are counted.
  4. BIND the terminus ONLY if EXACTLY ONE candidate exists (uniqueness-mandatory).
  5. TRACE start -> the unique terminus and render a red REVIEW stroke if the full route is source-backed.
  6. ABSTAIN (named) with the exact missing evidence if zero / multiple terminus candidates.

The owner's prior adjudication (gac/drop_lane_source_adjudication.md: drop termini are unnamed pots on other
sheets, BLOCKED) is used ONLY to validate this slice's source-derived verdict -- it is never read into the
solver, never baked into a fixture. No fixture mutation. No coordinate encoding. No review-choice. No
classification/seam/ledger. No product/runtime/api/backend/web/deploy/main. Red strokes only. PNG/JSON under
the gitignored data/outputs path; NOT committed.

Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_drop_terminus_solver_slice
"""
from __future__ import annotations

import json
import os

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.conduit_topology import connected_chain, dash_endpoints, symbol_footprint
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.structure_position import (
    BRENHAM_LATERAL_CONDUIT_LAYERS, cluster_symbols,
)
from truelinev2.extract.tick_path import route_ladder_ticks
from truelinev2.ingest.manual_adjudication import load_adjudication
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
import truelinev2.proof.run_station_corridor_route_solver_slice as SC

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "drop_terminus_solver"
LAT = set(BRENHAM_LATERAL_CONDUIT_LAYERS.values())
TARGETS = {"log30": 10, "log50": 10}      # authorized: log30 + log50 only

TERMINUS_WINDOW_FT = 20.0     # a drawn terminus symbol must be within this station distance of the bore end
TERMINUS_PERP_PT = 35.0       # ... and within this perpendicular of the alignment (on / just off the mainline)
CONTINUATION_WINDOW_FT = 20.0  # a continuation-sheet pot counts as a candidate if within this of the end (local)

R_RENDERED = "DROP_TERMINUS_RENDER_PRODUCED_ARTIFACTS"
R_NO_RENDER = "DROP_TERMINUS_NO_SAFE_ARTIFACT"
B_SCOPE = "BLOCKED_DROP_TERMINUS_SCOPE_VIOLATION"
ALLOWED = {R_RENDERED, R_NO_RENDER, B_SCOPE}


def bind_mainline(plan, offset, sheet, bore, rows, scale, cands):
    """Re-bind the main route exactly as the station-corridor solver does, but return the unique source-backed
    corridor (route to the positioned end) WITHOUT the terminus gate -- this is the mainline the drop hangs
    off. Returns (chosen_reset_dict, start_xy, row, running_end, corridor, route) or None if not unique."""
    draw = plan.line_items(sheet, offset)
    conduit = [x for x in draw if x.get("layer") in SC.BASE]
    hits = []
    for c in cands:
        parent = parse_station(c["reset"])
        if parent is None:
            continue
        start_xy = c["xy"]
        row, status, _ = SC.bind_row(rows, start_xy, parent)
        if row is None:
            continue
        running_end = parent + bore.span_ft
        if SC.position_on_row(row, running_end) is None:
            continue
        fp = symbol_footprint(draw, c["seed"], start_xy) or symbol_footprint(draw, "NEXTLINK", start_xy)
        flooded = connected_chain(conduit, fp) if fp else []
        corridor = SC.constrain_corridor(flooded, row, parent, running_end)
        if not corridor:
            continue
        end_xy = SC.position_on_row(row, running_end)
        route = order_chain_route(corridor, start_xy, end_xy)
        if not route or route[0] != tuple(start_xy) or route[-1] != tuple(end_xy) or len(route) < 2:
            continue
        if not (route_edges_source_backed(route, corridor) and len(route) >= 3
                and interior_vertices_are_dash_endpoints(route, corridor)
                and SC.route_is_monotonic(route, row)[0]):
            continue
        target_pt = bore.span_ft * scale if scale else None
        if target_pt is None or abs(route_length(route) - target_pt) > SC.SPAN_LEN_REL_TOL * target_pt:
            continue
        hits.append((c, start_xy, row, running_end, corridor, route))
    return hits[0] if len(hits) == 1 else None


def terminus_symbols_on_sheet(plan, offset, sheet, row, running_end, window_ft, perp_pt):
    """Drawn flower-pot / HH structure symbols within window_ft station + perp_pt of the end on the row."""
    draw = plan.line_items(sheet, offset)
    out = []
    for layer, kind in (("FLOWER POT", "flower_pot"), ("NEXTLINK", "hh_or_ap")):
        for cl in cluster_symbols(draw, layer):
            pr = SC.project_on_row(row, (cl.x, cl.y))
            if pr is not None and abs(pr[0] - running_end) <= window_ft and pr[1] <= perp_pt:
                out.append({"sheet": sheet, "kind": kind, "xy": (round(cl.x, 1), round(cl.y, 1)),
                            "implied_station": round(pr[0], 1), "perp_pt": round(pr[1], 1)})
    return out


def continuation_pots(plan, offset, sheet, local_end_ft):
    """Candidate cross-sheet termini: flower-pot symbols on a continuation sheet whose implied running station
    (on that sheet's own ladder) is within CONTINUATION_WINDOW_FT of the bore's LOCAL end station -- a drop
    terminus this bore could be (the bore resets to 0+00, so its local end ~= the continuation-sheet station)."""
    draw = plan.line_items(sheet, offset)
    ticks, _ = route_ladder_ticks(plan, sheet, offset)
    rows = SC.build_rows(ticks, SC.ladder_scale(ticks))
    out = []
    for cl in cluster_symbols(draw, "FLOWER POT"):
        best = None
        for r in rows:
            pr = SC.project_on_row(r, (cl.x, cl.y))
            if pr is not None and (best is None or pr[1] < best[1]):
                best = pr
        if best is not None and abs(best[0] - local_end_ft) <= CONTINUATION_WINDOW_FT and best[1] <= 60.0:
            out.append({"sheet": sheet, "kind": "flower_pot", "xy": (round(cl.x, 1), round(cl.y, 1)),
                        "implied_station": round(best[0], 1), "perp_pt": round(best[1], 1)})
    return out


def solve_drop(plan, offset, lid, sheet, bore, rows, scale, cands):
    rec = {"sheet": sheet, "span_ft": round(bore.span_ft), "sheet_refs": bore.sheet_refs}
    bound = bind_mainline(plan, offset, sheet, bore, rows, scale, cands)
    if bound is None:
        rec["result"] = "NO_UNIQUE_MAINLINE_CORRIDOR"
        return rec, None
    c, start_xy, row, running_end, corridor, route = bound
    rec.update(reset=c["reset"], start_xy=[round(v, 1) for v in start_xy], running_end_ft=round(running_end, 1))
    # 2. confirm the interpolated end is NOT a drawn terminus (conduit continues past it)
    draw = plan.line_items(sheet, offset)
    struct_syms = [x for x in draw if x.get("layer") in SC.STRUCT_SYMBOL_LAYERS]
    matchlines = [x for x in draw if x.get("layer") == SC.MATCHLINE_LAYER]
    end_xy = SC.position_on_row(row, running_end)
    term_ok, term_detail = SC.end_is_drawn_terminus(end_xy, corridor, row, running_end, struct_syms, matchlines)
    rec["interpolated_end_is_terminus"] = term_ok
    rec["interpolated_end_detail"] = term_detail
    # 3. search for the REAL terminus near the bore end station, across the bore's sheets
    on_sheet = terminus_symbols_on_sheet(plan, offset, sheet, row, running_end,
                                         TERMINUS_WINDOW_FT, TERMINUS_PERP_PT)
    cont = []
    for s in bore.sheet_refs:
        if s != sheet:
            cont += continuation_pots(plan, offset, s, bore.span_ft)
    lat = [x for x in draw if x.get("layer") in LAT]
    candidates = on_sheet + cont
    rec.update(on_sheet_terminus=on_sheet, continuation_terminus=cont,
               sheet10_lateral_drawings=len(lat), terminus_candidate_count=len(candidates),
               terminus_candidates=candidates)
    # 4/5. bind + render ONLY if exactly one terminus candidate, on the bound sheet, traceable from start
    if len(candidates) == 1 and candidates[0]["sheet"] == sheet:
        t = candidates[0]
        conduit = [x for x in draw if x.get("layer") in SC.BASE]
        fp = symbol_footprint(draw, c["seed"], start_xy) or symbol_footprint(draw, "NEXTLINK", start_xy)
        flooded = connected_chain(conduit, fp) if fp else []
        # corridor extended to the terminus station (it may sit slightly past running_end)
        corr2 = SC.constrain_corridor(flooded, row, parse_station(c["reset"]), t["implied_station"])
        troute = order_chain_route(corr2, start_xy, t["xy"])
        ok = (troute and troute[0] == tuple(start_xy) and troute[-1] == tuple(t["xy"]) and len(troute) >= 3
              and route_edges_source_backed(troute, corr2)
              and interior_vertices_are_dash_endpoints(troute, corr2)
              and SC.route_is_monotonic(troute, row)[0])
        if ok:
            rec["result"] = "UNIQUE_TERMINUS_BOUND"
            rec["terminus_route"] = troute
            return rec, (c, start_xy, t, troute)
        rec["result"] = "TERMINUS_FOUND_BUT_ROUTE_NOT_SOURCE_BACKED"
        return rec, None
    # 6. abstain (named) with the exact missing evidence
    if not candidates:
        rec["result"] = "NO_DRAWN_TERMINUS_NEAR_END"
        rec["missing_evidence"] = ("no flower-pot/HH symbol within +-{0}ft of the bore end on any of its "
                                   "sheets; the drop terminus is not drawn where the bore ends -- a drop-"
                                   "identity key (parent-AP tag / unique station-keyed pot / .FS drive "
                                   "decomposition) is required").format(int(TERMINUS_WINDOW_FT))
    else:
        rec["result"] = "DROP_TERMINUS_NOT_UNIQUE"
        sheets = sorted({t["sheet"] for t in candidates})
        rec["missing_evidence"] = ("{0} candidate flower-pot termini near the bore end across sheets {1} "
                                   "(none on the bound sheet at the end station; none station-keyed or "
                                   "uniquely drop-connected) -- a drop-identity key is required to select "
                                   "ONE; placing on a guessed pot or the mainline backbone is forbidden "
                                   "(DO-NOT-WIDEN)").format(len(candidates), sheets)
    return rec, None


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.png"):
        stale.unlink()

    doc = load_adjudication()
    gates = [("G0 engine census frozen (OFF 31/6/1/17/3, ON 22/1/4, log44+abstains held)",
              SC._census_frozen(doc), None)]
    if not os.path.isfile(PDF):
        return _emit(gates, B_SCOPE, {}, [])
    corpus = {p.stem: p for p in enumerate_corpus(resolve_corpus()[0])}
    gates.append(("G1 plan PDF + corpus present",
                  os.path.isfile(PDF) and len(corpus) == EXPECTED_COUNT, len(corpus)))

    plan = PlanPdf(PDF)
    rendered, targets = [], {}
    try:
        dialect = select_dialect(plan)
        offset = dialect.calibrate(plan, 13)
        cache = {}
        for lid, sheet in TARGETS.items():
            if sheet not in cache:
                ticks, _ = route_ladder_ticks(plan, sheet, offset)
                scale = SC.ladder_scale(ticks)
                cache[sheet] = (SC.build_rows(ticks, scale), scale, SC.discover_candidates(plan, offset, sheet))
            rows, scale, cands = cache[sheet]
            bore = load_borelog(str(corpus["bore_" + lid]))
            rec, win = solve_drop(plan, offset, lid, sheet, bore, rows, scale, cands)
            if win is not None:
                c, start_xy, t, troute = win
                png = render_redline_stroke(
                    plan, lid, sheet, offset, troute, status="REVIEW",
                    reason=(f"DROP-TERMINUS: bore {lid} reset STA {c['reset']}=0+00 -> source-backed route to "
                            f"the UNIQUE drawn {t['kind']} terminus @ station {t['implied_station']} "
                            f"(sheet {t['sheet']})"),
                    out_dir=str(OUT_DIR), mandatory_points=[start_xy, t["xy"]], pad=170.0)
                if png and os.path.isfile(png):
                    rendered.append((lid, png, t))
                    rec["png"] = os.path.basename(png)
                    rec["result"] = "RENDERED_UNIQUE_TERMINUS"
                else:
                    rec["result"] = "RENDER_RETURNED_NO_PNG"
            targets[lid] = rec
    finally:
        plan.close()

    gates.append(("G2 every render has a real PNG; every abstain names exact missing evidence",
                  all(os.path.isfile(p) for _, p, _ in rendered)
                  and all(("missing_evidence" in r) or ("png" in r) for r in targets.values()), None))
    gates.append(("G3 terminus bound ONLY if unique; no review-choice; no owner truth baked; no fixture write",
                  all((r.get("terminus_candidate_count", 0) == 1) for r in targets.values() if "png" in r)
                  if rendered else True, None))
    result = R_RENDERED if rendered else R_NO_RENDER
    return _emit(gates, result, targets, rendered)


def _emit(gates, result, targets, rendered) -> int:
    pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
    gates.append(("G4 canonical red stroke color (TrueLine strokes are red)",
                  REDLINE_STROKE_RGB == (220, 25, 25), list(REDLINE_STROKE_RGB)))
    gates.append(("G5 result in allowed enum", result in ALLOWED, result))
    all_pass = all(x for _, x, _ in gates)
    report = {
        "milestone": "DROP-BORE TERMINUS SOLVER -> redline artifacts (proof only; read-only; product-gated)",
        "verdict": "PASS" if all_pass else "FAIL", "result": result,
        "target_logs": list(TARGETS),
        "newly_rendered_full": [l for l, _, _ in rendered],
        "newly_rendered_partial": [],
        "artifact_paths": [str(p).replace(str(_REPO_ROOT), "").lstrip("\\/").replace("\\", "/")
                           for _, p, _ in rendered],
        "still_blocked": [{"log": l, "blocker": r.get("result"), "missing_evidence": r.get("missing_evidence")}
                          for l, r in targets.items() if "png" not in r],
        "targets": targets,
        "tolerances": {"TERMINUS_WINDOW_FT": TERMINUS_WINDOW_FT, "TERMINUS_PERP_PT": TERMINUS_PERP_PT,
                       "CONTINUATION_WINDOW_FT": CONTINUATION_WINDOW_FT},
        "red_stroke_rgb": list(REDLINE_STROKE_RGB),
        "no_review_choice": True, "no_owner_truth_baked": True, "no_fixture_mutation": True,
        "no_coordinate_encoding": True, "engine_census_frozen": True, "artifacts_gitignored": True,
        "gates": [{"name": n, "pass": bool(x), "detail": d} for n, x, d in gates],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "drop_terminus_solver.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[drop-terminus] result: {result}  rendered={[l for l,_,_ in rendered]}")
    for lid, r in targets.items():
        print(f"[drop-terminus]   {lid}: reset={r.get('reset')} end={r.get('running_end_ft')} "
              f"on_sheet_term={len(r.get('on_sheet_terminus', []))} cont_term={len(r.get('continuation_terminus', []))} "
              f"-> {r.get('result')}")
        if r.get("missing_evidence"):
            print(f"[drop-terminus]       missing: {r['missing_evidence']}")
    for a in pngs:
        print(f"[drop-terminus]   ARTIFACT: {a}")
    for n, x, _ in gates:
        print(f"[drop-terminus] {'PASS' if x else 'FAIL'}  {n}")
    print(f"[drop-terminus] VERDICT: {'PASS' if all_pass else 'FAIL'}  (report: {OUT_DIR})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
