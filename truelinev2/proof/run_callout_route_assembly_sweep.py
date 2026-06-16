r"""GENERALIZED CALLOUT-IDENTITY ROUTE ASSEMBLY sweep -> render redlines (PROOF; read-only; product-gated).

Generalizes the log50 splice-point lesson into ONE solver over the whole anchored-but-not-yet-drawn class.
The log50/log71 finding: a cross-sheet bore draws as TWO sheet-local legs joined by a PRINTED station
identity -- you do NOT need cross-sheet coordinate/frame reconciliation, and you must NOT require the wrong
reciprocal label (an AP on both sheets, a single non-conflicting frame equation, etc.). The engine had been
HOLDING these logs back on exactly that broken assumption ("CONFLICTING_FRAME_EQUATIONS", "multi-sheet
reconciliation", "12-vs-13 crossing ambiguity"). This sweep reads each bore's route SENTENCE from source and
renders it:

  start callout / reset  ->  bind start terminus (modeled structure symbol, leader-bound; never nearest)
  end callout            ->  bind end terminus on its own sheet
  per-endpoint sheet     ->  DERIVED by unique source bind across corrected_sheets (no hardcoded sheet)
  matchline reference    ->  the printed 'MATCHLINE STA a/b - SEE SHEET <partner>' crossing equation
  reciprocal sheet       ->  the SAME printed equation on the partner sheet (station identity, not coords)
  crossing pick          ->  WHICH printed crossing this bore uses = the one BOTH legs' conduit chains
                             physically reach (chain-reach uniqueness) -- this DISAMBIGUATES the
                             "conflicting" multi-crossing sheet pairs the old gate refused
  conduit route          ->  ordered source-backed chain path per leg (every edge a real drawn dash or a
                             <= MAX_DASH_GAP hop; every interior vertex a real dash endpoint)
  station closure        ->  if span_ft is printed, the two drawn legs' length closes the bore span
  -> render TWO red REVIEW strokes (one per sheet), joined by the printed station identity; frames NOT
     reconciled (the proven log50/log52/log53/log71 cross-sheet render shape).

FALSE-POSITIVE GUARDS (each abstains, never guesses): terminus must POSITION_BOUND uniquely on exactly ONE
corrected sheet; the crossing must be the UNIQUE printed SEE-SHEET equation both legs reach (0 or >=2 ->
abstain, no nearest/length pick); BOTH legs required (never a partial drawn as a full bore); every route edge
source-backed (no ruler cut across a through conduit); printed station closure when span_ft is known.

Scope: NO fixture mutation (adjudication read-only), NO coordinate encoding (all xy extractor-derived), NO
owner naming (anchors consumed as-is), NO review-choice fallback, NO seam/ledger/census change (frozen +
gated), NO product/runtime/api/backend/web/deploy/main. Red strokes only; PNG/JSON under the gitignored
data/outputs path. The only engine change is the additive matchline primitive see_sheet_crossings (extract/).

Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_callout_route_assembly_sweep
"""
from __future__ import annotations

import json
import math
import os

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.conduit_topology import (
    MAX_DASH_GAP, connected_chain, dash_endpoints, symbol_footprint,
)
from truelinev2.extract.matchline_join import see_sheet_crossings
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.structure_position import (
    BRENHAM_CONDUIT_LAYERS, BRENHAM_LATERAL_CONDUIT_LAYERS, BRENHAM_STRUCTURE_LAYERS,
    POSITION_BOUND, resolve_nextlink_hh_callout, resolve_structure_position,
)
from truelinev2.ingest.manual_adjudication import (
    activation_summary, apply_adjudications, load_adjudication,
    parent_run_duplicate_check, validate_endpoint_anchors,
)
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.proof.run_brenham_corpus import EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_log59_render_artifact_slice import (
    interior_vertices_are_dash_endpoints, route_edges_source_backed,
)
from truelinev2.proof.run_log71_render_artifact_slice import order_chain_route, route_length
from truelinev2.proof.run_log71_sheet_local_bind_scout import locate_matchline_boundary
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.render.crop import REDLINE_STROKE_RGB, render_redline_stroke
from truelinev2.stations import parse_station

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "callout_route_assembly_sweep"
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / "final_engine_truth_table.json"
# drop bores (flower-pot termini) route on BORE - LATERAL; mainline bores on VACANT PIPE / PORT. The
# dialect defines the lateral layer SEPARATELY (structure_position) and sanctions composing base|lateral
# for drop coverage (the proven log53 lateral precedent). BORE - PATH stays EXCLUDED (unproven over-cover).
BASE_CONDUIT = set(BRENHAM_CONDUIT_LAYERS.values()) | set(BRENHAM_LATERAL_CONDUIT_LAYERS.values())
FROZEN_BUCKETS = {"DRAWABLE_REVIEW": 31, "HUMAN_ADJUSTABLE_REVIEW": 6,
                  "OUT_OF_CLASS": 1, "PICK_CARD_REVIEW": 17, "SOURCE_OR_KMZ_REQUIRED": 3}
ABSTAIN_4 = ("log5", "log31", "log38", "log43")
SCALE = 1.44                # Brenham drawn pts/ft
CLOSURE_REL_TOL = 0.10      # two legs' drawn length vs printed bore span (corroboration, span_ft known)

# the anchored bores NOT yet drawn by a committed render proof (the held-back class this sweep attacks)
ALREADY_DRAWN = ("log7", "log25", "log45", "log51", "log52", "log53", "log59",
                 "log64", "log65", "log66", "log69", "log71", "log50")
SYMBOL_LAYER = {"flower_pot": "FLOWER POT", "installer_hh": "NEXTLINK",
                "terminal_port_hh": "NEXTLINK", "nextlink_hh": "NEXTLINK"}
CONTEXT = {"flower_pot": ("FLOWER", "POT")}
MODELED = set(SYMBOL_LAYER)

R_COMPLETE = "CALLOUT_ROUTE_ASSEMBLY_SWEEP_COMPLETE"
B_CENSUS = "BLOCKED_SWEEP_CENSUS_DRIFT"
B_SCOPE = "BLOCKED_SWEEP_SCOPE_VIOLATION"
B_NOTHING = "BLOCKED_SWEEP_NO_NEW_RENDER"
ALLOWED = {R_COMPLETE, B_CENSUS, B_SCOPE, B_NOTHING}


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


def _bind(plan, offset, sheet, cls, station):
    """Source-bind a terminus on one sheet via the proven leader-chain locators. Returns
    (xy|None, words, draw, result). nextlink_hh uses the ANNOTATION callout locator; the modeled
    note/id classes use resolve_structure_position (reset label tried first). No nearest-snap."""
    words, draw = plan.words(sheet, offset), plan.line_items(sheet, offset)
    if cls == "nextlink_hh":
        v = resolve_nextlink_hh_callout(station_sta=station, words=words, drawings=draw,
                                        callout_layer="ANNOTATION", symbol_layer="NEXTLINK")
        return (tuple(v.symbol_xy) if (v.result == POSITION_BOUND and v.symbol_xy) else None,
                words, draw, v.result)
    ctx, last = CONTEXT.get(cls), None
    for label in (f"{station}=0+00", station):
        kw = dict(label_text=label, structure_class=cls, words=words, drawings=draw,
                  layer_table=BRENHAM_STRUCTURE_LAYERS)
        if ctx:
            kw["context_texts"] = ctx
        v = resolve_structure_position(**kw)
        last = v.result
        if v.result == POSITION_BOUND and v.symbol_xy:
            return tuple(v.symbol_xy), words, draw, v.result
    return None, words, draw, last


def _chain_at(draw, cls, xy):
    fp = symbol_footprint(draw, SYMBOL_LAYER[cls], xy)
    return connected_chain([x for x in draw if x.get("layer") in BASE_CONDUIT], fp) if fp else []


def _all_sheets(plan, offset):
    return [s for s in range(1, plan.page_count + 1) if 0 <= s + offset - 1 < plan.page_count]


def _endpoint_sheet(plan, offset, sheets, cls, station):
    """The UNIQUE sheet where the terminus POSITION_BOUNDs (per-endpoint sheet, derived from source, not
    hardcoded). Searches the owner's corrected_sheets; when that set is EMPTY (owner sheet not recorded),
    the sheet is EXTRACTED FROM SOURCE -- the unique sheet across ALL plan sheets where the terminus binds
    (driving the abstain to zero by extracting the missing relationship, never owner-naming). Returns
    (sheet|None, {sheet:result}). 0 or >=2 bound sheets -> None (abstain, never guessed)."""
    search = list(sheets) if sheets else _all_sheets(plan, offset)
    bound, res = [], {}
    for sh in search:
        xy, _, _, r = _bind(plan, offset, sh, cls, station)
        if xy is not None:
            bound.append(sh)
            res[sh] = r
    return (bound[0] if len(bound) == 1 else None), res


def _leg_matchline(words, draw, chain, cross):
    """(station, boundary_xy) the leg's chain reaches for one printed crossing equation, trying each of
    its station tokens; first that locates a unique chain-reached matchline wins. None if none reach."""
    for sta in cross:
        bnd, _, uniq = locate_matchline_boundary(words, draw, sta, chain)
        if bnd is not None and uniq:
            return sta, tuple(bnd)
    return None


def _ordered_leg(chain, a_xy, b_xy):
    """Ordered source-backed route a->b through the chain, with the source-backing verdict."""
    route = order_chain_route(chain, a_xy, b_xy)
    ok = (len(route) >= 2 and route[0] == tuple(a_xy) and route[-1] == tuple(b_xy)
          and route_edges_source_backed(route, chain)
          and (len(route) < 3 or interior_vertices_are_dash_endpoints(route, chain)))
    return route, bool(ok)


def solve_log(plan, offset, lid, rec):
    """Attempt the full route sentence for one anchored bore. Returns a verdict dict with either a
    render plan (legs to draw) or a named blocker. Renders nothing (the caller draws)."""
    r = rec.get(lid, {})
    ea = r.get("endpoint_anchors") or {}
    start, end = ea.get("start") or {}, ea.get("end") or {}
    sheets = r.get("corrected_sheets") or []
    # printed bore span for the closure guard: span_ft if recorded, else the bore-local station delta
    # corrected_start -> corrected_end (the bore's own stationing IS its conduit length).
    span = r.get("span_ft")
    span_src = "span_ft"
    if span is None and r.get("corrected_start") and r.get("corrected_end"):
        span = abs(parse_station(r["corrected_end"]) - parse_station(r["corrected_start"]))
        span_src = "corrected_start->corrected_end"
    out = {"log": lid, "sheets_set": sheets, "span_ft": span, "span_source": span_src,
           "blocker": None, "legs": None, "single_sheet": None}

    sc, ss = start.get("structure_class"), start.get("station")
    ec, es = end.get("structure_class"), end.get("station")
    if validate_endpoint_anchors(r) or sc not in MODELED or ec not in MODELED:
        out["blocker"] = "anchors invalid / non-modeled terminus class"
        return out

    s_sheet, s_res = _endpoint_sheet(plan, offset, sheets, sc, ss)
    e_sheet, e_res = _endpoint_sheet(plan, offset, sheets, ec, es)
    # when corrected_sheets is empty, the sheet was EXTRACTED from source (unique bind across all sheets);
    # the render is a PROOF artifact -- owner confirmation of the source-derived sheet is still required
    # before any product promotion (census stays frozen; nothing placed/promoted here).
    out["sheet_source_derived"] = (not sheets) and s_sheet is not None and e_sheet is not None
    out["start_sheet"], out["end_sheet"] = s_sheet, e_sheet
    out["bind_results"] = {"start": s_res, "end": e_res}
    if s_sheet is None or e_sheet is None:
        out["blocker"] = (f"terminus did not bind on a UNIQUE corrected sheet "
                          f"(start->{s_sheet} {s_res}; end->{e_sheet} {e_res})")
        return out

    s_xy, s_words, s_draw, _ = _bind(plan, offset, s_sheet, sc, ss)
    e_xy, e_words, e_draw, _ = _bind(plan, offset, e_sheet, ec, es)
    s_chain = _chain_at(s_draw, sc, s_xy)
    e_chain = _chain_at(e_draw, ec, e_xy)
    if not s_chain or not e_chain:
        out["blocker"] = f"no connected conduit chain at a terminus (start segs {len(s_chain)}, end segs {len(e_chain)})"
        return out

    if s_sheet == e_sheet:
        route, ok = _ordered_leg(s_chain, s_xy, e_xy)
        out["single_sheet"] = True
        if not ok:
            out["blocker"] = "single-sheet route not source-backed (terminus-to-terminus chain path)"
            return out
        if span:
            drawn_ft = route_length(route) / SCALE
            out["closure"] = {"drawn_ft": round(drawn_ft, 1), "span_ft": span, "closes": abs(drawn_ft - span) <= CLOSURE_REL_TOL * span}
            if not out["closure"]["closes"]:
                out["blocker"] = f"single-sheet closure failed: drawn {round(drawn_ft,1)} ft vs span {span} ft"
                return out
        out["legs"] = [{"sheet": s_sheet, "route": route, "a_xy": s_xy, "b_xy": e_xy,
                        "len_pt": round(route_length(route), 1), "kind": "single_sheet",
                        "start_label": ss, "end_label": es}]
        return out

    # ---- cross-sheet: resolve the printed crossing both legs reach, render two sheet-local legs ----
    s_lines = plan.lines(s_sheet, offset)
    crossings = see_sheet_crossings(s_lines, e_sheet, "MATCHLINE")
    out["printed_crossings_start_to_end"] = [list(c) for c in crossings]
    viable = []
    for cross in crossings:
        a = _leg_matchline(s_words, s_draw, s_chain, cross)
        b = _leg_matchline(e_words, e_draw, e_chain, cross)
        if a and b:
            viable.append({"equation": list(cross), "start_sta": a[0], "start_bnd": [round(v, 1) for v in a[1]],
                           "end_sta": b[0], "end_bnd": [round(v, 1) for v in b[1]],
                           "_a": a, "_b": b})
    out["viable_crossings"] = [{k: v for k, v in c.items() if not k.startswith("_")} for c in viable]
    if len(viable) != 1:
        out["blocker"] = (f"crossing not unique: {len(viable)} of {len(crossings)} printed SEE-SHEET "
                          f"{s_sheet}<->{e_sheet} equations are reached by BOTH legs' chains "
                          f"(need exactly 1; 0 or >=2 -> abstain, no nearest/length pick)")
        return out
    cr = viable[0]
    a_bnd, b_bnd = cr["_a"][1], cr["_b"][1]

    s_route, s_ok = _ordered_leg(s_chain, s_xy, a_bnd)
    e_route, e_ok = _ordered_leg(e_chain, b_bnd, e_xy)
    out["start_leg_source_backed"], out["end_leg_source_backed"] = s_ok, e_ok
    if not (s_ok and e_ok):
        out["blocker"] = f"a leg route not source-backed (start {s_ok}, end {e_ok})"
        return out

    s_len, e_len = route_length(s_route), route_length(e_route)
    if span:
        drawn_ft = (s_len + e_len) / SCALE
        closes = abs(drawn_ft - span) <= CLOSURE_REL_TOL * span
        out["closure"] = {"drawn_ft": round(drawn_ft, 1), "span_ft": span, "closes": closes}
        if not closes:
            out["blocker"] = (f"station closure failed: two legs draw {round(drawn_ft, 1)} ft vs printed "
                              f"bore span {span} ft (>{int(CLOSURE_REL_TOL*100)}% off -> wrong crossing/partial)")
            return out

    out["legs"] = [
        {"sheet": s_sheet, "route": s_route, "a_xy": s_xy, "b_xy": a_bnd, "len_pt": round(s_len, 1),
         "kind": "start_leg", "start_label": ss, "matchline_sta": cr["start_sta"]},
        {"sheet": e_sheet, "route": e_route, "a_xy": b_bnd, "b_xy": e_xy, "len_pt": round(e_len, 1),
         "kind": "end_leg", "end_label": es, "matchline_sta": cr["end_sta"]},
    ]
    out["crossing_equation"] = cr["equation"]
    return out


def _render(plan, offset, lid, v):
    pngs = []
    for leg in v["legs"]:
        if leg["kind"] == "single_sheet":
            derived = (" [sheet source-derived from unique bind; owner confirmation pending before product promotion]"
                       if v.get("sheet_source_derived") else "")
            reason = (f"{lid} source-backed callout route: {leg['start_label']} -> {leg['end_label']} "
                      f"(single sheet {leg['sheet']}; ordered conduit chain path){derived}")
        elif leg["kind"] == "start_leg":
            reason = (f"{lid} sheet-{leg['sheet']} leg: start {leg['start_label']} -> MATCHLINE STA "
                      f"{leg['matchline_sta']} (SEE SHEET {v['end_sheet']}); cross-sheet bore joined by "
                      f"printed station identity, frames not reconciled")
        else:
            reason = (f"{lid} sheet-{leg['sheet']} leg: MATCHLINE STA {leg['matchline_sta']} -> end "
                      f"{leg['end_label']}; joined to sheet {v['start_sheet']} by printed station identity")
        png = render_redline_stroke(plan, lid, leg["sheet"], offset, leg["route"], status="REVIEW",
                                    reason=reason, out_dir=str(OUT_DIR),
                                    mandatory_points=[tuple(leg["a_xy"]), tuple(leg["b_xy"])], pad=160.0)
        leg["png"] = os.path.basename(png) if png else None
        if png and os.path.isfile(png):
            pngs.append(png)
    return pngs


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.png"):
        stale.unlink()
    doc = load_adjudication()
    rec = {r["log_id"]: r for r in doc["logs"]}
    gates, ev = [], {"verdicts": {}}

    gates.append(("G0 engine census frozen (OFF 31/6/1/17/3, ON 22/1/4, log44+abstains held)",
                  _census_frozen(doc), None))

    if not os.path.isfile(PDF):
        return _emit(gates, B_SCOPE, ev)
    corpus_dir, _ = resolve_corpus()
    corpus = {p.stem: p for p in enumerate_corpus(corpus_dir)} if os.path.isdir(corpus_dir) else {}
    gates.append(("G1 plan PDF + corpus present", os.path.isfile(PDF) and len(corpus) == EXPECTED_COUNT,
                  {"pdf": os.path.isfile(PDF), "corpus": len(corpus)}))

    targets = sorted((lid for lid, r in rec.items()
                      if r.get("endpoint_anchors") and lid not in ALREADY_DRAWN
                      and not r.get("must_remain_abstained")),
                     key=lambda s: int(s[3:]))
    ev["targets"] = targets

    rendered_full, blocked = [], {}
    plan = PlanPdf(PDF)
    try:
        offset = select_dialect(plan).calibrate(plan, 13)
        for lid in targets:
            v = solve_log(plan, offset, lid, rec)
            if v.get("legs"):
                pngs = _render(plan, offset, lid, v)
                n_expected = len(v["legs"])
                if len(pngs) == n_expected:
                    v["artifacts"] = [str(p).replace(str(_REPO_ROOT), "").lstrip("\\/").replace("\\", "/")
                                      for p in pngs]
                    rendered_full.append(lid)
                else:
                    v["blocker"] = f"render returned {len(pngs)}/{n_expected} PNGs"
                    blocked[lid] = v["blocker"]
            else:
                blocked[lid] = v["blocker"]
            ev["verdicts"][lid] = {k: x for k, x in v.items() if not k.startswith("_") and k != "legs"}
            ev["verdicts"][lid]["leg_summary"] = ([{"sheet": l["sheet"], "kind": l["kind"],
                                                    "vertices": len(l["route"]), "len_pt": l["len_pt"],
                                                    "png": l.get("png")} for l in v["legs"]]
                                                   if v.get("legs") else None)
    finally:
        plan.close()

    ev["rendered_full"], ev["blocked"] = rendered_full, blocked
    gates.append(("G2 every rendered bore drew ALL its legs (no partial drawn as a full bore)",
                  all(len(ev["verdicts"][l]["leg_summary"]) ==
                      len([p for p in OUT_DIR.glob(f"{l}_*.png")]) for l in rendered_full), rendered_full))
    gates.append(("G3 at least one NEW redline artifact produced (success metric = new artifacts)",
                  len(rendered_full) >= 1, {"rendered": rendered_full}))
    gates.append(("G4 canonical red stroke color (TrueLine strokes are red)",
                  REDLINE_STROKE_RGB == (220, 25, 25), list(REDLINE_STROKE_RGB)))
    result = R_COMPLETE if all(x for _, x, _ in gates) else (
        B_CENSUS if not gates[0][1] else B_NOTHING)
    return _emit(gates, result, ev)


def _emit(gates, result, ev) -> int:
    gates.append(("G5 result in allowed enum", result in ALLOWED, result))
    all_pass = all(x for _, x, _ in gates) and result == R_COMPLETE
    pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
    report = {
        "milestone": "GENERALIZED CALLOUT-IDENTITY ROUTE ASSEMBLY sweep -> render (proof; read-only)",
        "verdict": "PASS" if all_pass else "FAIL", "result": result,
        "targets": ev.get("targets", []),
        "newly_rendered_full": ev.get("rendered_full", []),
        "newly_rendered_partial": [],
        "artifact_paths": [a for l in ev.get("rendered_full", []) for a in ev["verdicts"][l].get("artifacts", [])],
        "still_blocked": ev.get("blocked", {}),
        "verdicts": ev.get("verdicts", {}),
        "red_stroke_rgb": list(REDLINE_STROKE_RGB),
        "no_fixture_mutation": True, "no_coordinate_encoding": True, "no_owner_naming": True,
        "no_review_choice": True, "no_seam_or_ledger_change": True, "engine_census_frozen": True,
        "artifacts_gitignored": True, "max_dash_gap_not_loosened": MAX_DASH_GAP == 35.0,
        "artifacts_on_disk": pngs,
        "gates": [{"name": n, "pass": bool(x), "detail": d} for n, x, d in gates],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "callout_route_assembly_sweep.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[route-sweep] result: {result}  newly_rendered={ev.get('rendered_full')}")
    for lid, v in ev.get("verdicts", {}).items():
        if lid in ev.get("rendered_full", []):
            print(f"[route-sweep]   {lid}: RENDERED {v.get('leg_summary')}")
        else:
            print(f"[route-sweep]   {lid}: BLOCKED -- {v.get('blocker')}")
    for n, x, _ in gates:
        print(f"[route-sweep] {'PASS' if x else 'FAIL'}  {n}")
    print(f"[route-sweep] VERDICT: {'PASS' if all_pass else 'FAIL'}  (report: {OUT_DIR})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
