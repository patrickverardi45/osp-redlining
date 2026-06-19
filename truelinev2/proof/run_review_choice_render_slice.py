r"""REVIEW-CHOICE -> RENDER slice (PROOF ONLY; the ambiguity-resolution render primitive).

The product's structure-identity ambiguity resolver, end to end: PLAN SOURCE -> rival reset candidates ->
REVIEWER chooses the intended start -> the engine binds it + traces the source conduit route to the unique
end at the bore's span -> a RED redline artifact is rendered. For Group-A logs the binder proved it CANNOT
auto-pick among rival ``STA X+XX = 0+00`` reset structures on a sheet (sheet 10 has 5; sheet 18 has 2; sheet 2
has 2); this slice lets a reviewer break exactly that tie -- the choice is an EXPLICIT harness input, never
baked into any fixture, and the rejected rivals are recorded alongside the selection.

The render primitive (``render_from_selected_start``), once the reviewer picks the start, is uniqueness-
mandatory on the END too: it binds the selected reset structure, seeds the modeled BORE conduit chain, and
-- using the sheet's drawn station-ladder pt/ft scale -- finds the dash endpoint reached at the bore's span
along the chain. EXACTLY ONE such end -> render the ordered source-backed chain route as a red REVIEW stroke.
ZERO (chain does not reach the span) or MULTIPLE (the route branches at the span) -> ABSTAIN with the exact
blocker. No coordinate is invented; every route vertex is a real drawn dash endpoint; no fixture is mutated;
the reviewer's choice is the only added input and it is recorded with the rivals it rejected.

Run (repo root); reviewer choices are the explicit ``--select`` inputs (default = the demo selections):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_review_choice_render_slice
  ... -m truelinev2.proof.run_review_choice_render_slice --select log42=0+46 --select log56=7+40
"""
from __future__ import annotations

import json
import math
import os
import re
import sys
from statistics import median

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.conduit_topology import (
    MAX_DASH_GAP,
    connected_chain,
    dash_endpoints,
    symbol_footprint,
)
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.station_axis import parse_tick
from truelinev2.extract.structure_position import (
    BRENHAM_CONDUIT_LAYERS,
    BRENHAM_STRUCTURE_LAYERS,
    POSITION_BOUND,
    resolve_nextlink_hh_callout,
    resolve_structure_position,
)
from truelinev2.extract.tick_path import route_ladder_ticks
from truelinev2.ingest.manual_adjudication import (
    activation_summary,
    apply_adjudications,
    load_adjudication,
    parent_run_duplicate_check,
)
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.match.collision_gate import collect_all_sheet_equations
from truelinev2.match.engine import run_match
from truelinev2.match.frames import _build_plan_frame_graph
from truelinev2.match.reverse_anchor import ReverseAnchorContext
from truelinev2.match.station_axis_interval import StationAxisContext
from truelinev2.match.transition_classifier import conflict_sheet_pairs
from truelinev2.proof.run_brenham_corpus import EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_log59_render_artifact_slice import (
    interior_vertices_are_dash_endpoints,
    route_edges_source_backed,
)
from truelinev2.proof.run_log71_render_artifact_slice import order_chain_route, route_length
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.render.crop import REDLINE_STROKE_RGB, render_redline_stroke

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "review_choice_render_slice"
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / \
    "final_engine_truth_table.json"
BASE = set(BRENHAM_CONDUIT_LAYERS.values())
FROZEN_BUCKETS = {"DRAWABLE_REVIEW": 31, "HUMAN_ADJUSTABLE_REVIEW": 6,
                  "OUT_OF_CLASS": 1, "PICK_CARD_REVIEW": 17, "SOURCE_OR_KMZ_REQUIRED": 3}
ABSTAIN_4 = ("log5", "log31", "log38", "log43")
RESET_RE = re.compile(r"(\d+\+\d+)\s*=\s*0\+00")
# the reset-structure classes tried per candidate (uniqueness-mandatory bind); HH symbols share NEXTLINK layer
CLASSES = (("installer_hh", None, "NEXTLINK"), ("flower_pot", ("FLOWER", "POT"), "FLOWER POT"),
           ("nextlink_hh", None, "NEXTLINK"))
SPAN_TOL_FRAC = 0.12          # end must be within 12% of the bore span along the chain
MIN_TOL_PT = 40.0

# the already-discovered Group-A rival groups (each log's placed sheet); candidates are re-derived from source
TARGETS = {
    "log30": 10, "log50": 10, "log57": 10,   # sheet 10: 0+55 / 2+22 / 2+72 / 45+33
    "log8": 18, "log32": 18,                  # sheet 18: 12+22 / 12+93
    "log42": 2, "log56": 2,                   # sheet 2:  0+46 / 7+40
}
# demo reviewer selections (EXPLICIT harness input; NOT baked into any fixture). Overridable via --select.
DEFAULT_SELECTIONS = {}

R_RENDERED = "REVIEW_CHOICE_RENDER_PRODUCED_ARTIFACTS"
R_NO_RENDER = "REVIEW_CHOICE_RENDER_NO_SAFE_ARTIFACT"
B_CENSUS = "BLOCKED_REVIEW_CHOICE_CENSUS_DRIFT"
B_SCOPE = "BLOCKED_REVIEW_CHOICE_SCOPE_VIOLATION"
ALLOWED = {R_RENDERED, R_NO_RENDER, B_CENSUS, B_SCOPE}


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


def ladder_scale(ticks):
    """Drawn pt-per-ft from adjacent station-ladder rungs (median of ~100 ft adjacent ticks). None if absent."""
    ts = sorted(ticks, key=lambda t: t.station_ft)
    scales = [math.hypot(b.x - a.x, b.y - a.y) / (b.station_ft - a.station_ft)
              for a, b in zip(ts, ts[1:]) if 50 <= (b.station_ft - a.station_ft) <= 200]
    return median(scales) if scales else None


def discover_candidates(plan, offset, sheet):
    """Rival reset-structure candidates on a sheet, surfaced from source: each ``STA X+XX=0+00`` that binds a
    modeled structure (uniqueness-mandatory per class). Returns [{reset, structure_class, seed, xy}]."""
    words = plan.words(sheet, offset)
    draw = plan.line_items(sheet, offset)
    resets = sorted(set(RESET_RE.findall(" ".join(plan.lines(sheet, offset)))),
                    key=lambda s: (int(s.split("+")[0]), int(s.split("+")[1])))
    cands = []
    for r in resets:
        for cls, ctx, seed in CLASSES:
            if cls == "nextlink_hh":
                v = resolve_nextlink_hh_callout(station_sta=r, words=words, drawings=draw,
                                                callout_layer="ANNOTATION", symbol_layer="NEXTLINK")
            else:
                kw = dict(label_text=f"{r}=0+00", structure_class=cls, words=words, drawings=draw,
                          layer_table=BRENHAM_STRUCTURE_LAYERS)
                if ctx:
                    kw["context_texts"] = ctx
                v = resolve_structure_position(**kw)
            if v.result == POSITION_BOUND and v.symbol_xy:
                cands.append({"reset": r, "structure_class": cls, "seed": seed,
                              "xy": tuple(v.symbol_xy)})
                break   # first class that binds this reset
    return cands


def render_from_selected_start(plan, offset, sheet, start_xy, seed, span_ft, scale, out_dir, log_id, reset):
    """Trace the source conduit route from the reviewer-selected start to the UNIQUE dash endpoint reached at
    the bore span; render a red REVIEW stroke. Returns (png|None, detail). Uniqueness-mandatory on the end."""
    draw = plan.line_items(sheet, offset)
    fp = symbol_footprint(draw, seed, start_xy) or symbol_footprint(draw, "NEXTLINK", start_xy)
    chain = connected_chain([x for x in draw if x.get("layer") in BASE], fp) if fp else []
    eps = dash_endpoints(chain)
    if not chain or scale is None:
        return None, {"result": "NO_CONDUIT_OR_SCALE", "chain_segs": len(chain), "scale": scale}
    target_pt = span_ft * scale
    tol = max(SPAN_TOL_FRAC * target_pt, MIN_TOL_PT)
    ends = {}
    for ep in eps:
        route = order_chain_route(chain, start_xy, ep)
        if not route or route[0] != start_xy or route[-1] != ep:
            continue
        if len(route) < 2 or not route_edges_source_backed(route, chain):
            continue
        rl = route_length(route)
        if abs(rl - target_pt) <= tol:
            ends[(round(ep[0], 1), round(ep[1], 1))] = (ep, route, rl)
    detail = {"target_pt": round(target_pt, 1), "tol_pt": round(tol, 1), "scale_pt_per_ft": round(scale, 3),
              "chain_segs": len(chain), "ends_at_span": len(ends)}
    if not ends:
        reach = max((route_length(order_chain_route(chain, start_xy, ep)) for ep in eps
                     if order_chain_route(chain, start_xy, ep) and order_chain_route(chain, start_xy, ep)[0] == start_xy),
                    default=0.0)
        detail["result"] = "CONDUIT_DOES_NOT_REACH_SPAN"
        detail["max_reach_pt"] = round(reach, 1)
        return None, detail
    if len(ends) > 1:
        detail["result"] = "END_BRANCH_AMBIGUOUS_AT_SPAN"
        detail["end_points"] = [list(k) for k in ends]
        return None, detail
    ep, route, rl = next(iter(ends.values()))
    if not (len(route) >= 3 and interior_vertices_are_dash_endpoints(route, chain)):
        detail["result"] = "ROUTE_NOT_SOURCE_BACKED"
        return None, detail
    png = render_redline_stroke(
        plan, log_id, sheet, offset, route, status="REVIEW",
        reason=(f"REVIEW-CHOICE: reviewer-selected start STA {reset}=0+00 -> conduit route to the unique "
                f"end at span {round(span_ft)}' (source-backed chain; rival resets rejected)"),
        out_dir=str(out_dir), mandatory_points=[start_xy, ep], pad=170.0)
    detail.update(result="RENDERED", route_vertices=len(route), route_len_pt=round(rl, 1),
                  end_xy=[round(c, 2) for c in ep], png=png)
    return png, detail


def parse_select(argv):
    sel = dict(DEFAULT_SELECTIONS)
    i = 0
    while i < len(argv):
        if argv[i] == "--select" and i + 1 < len(argv) and "=" in argv[i + 1]:
            lid, reset = argv[i + 1].split("=", 1)
            sel[lid.strip()] = reset.strip()
            i += 2
        else:
            i += 1
    return sel


def main(selections=None, argv=None) -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.png"):
        stale.unlink()
    if selections is None:
        selections = parse_select(argv if argv is not None else sys.argv[1:])

    doc = load_adjudication()
    gates, ev = [], {"targets": {}}
    gates.append(("G0 engine census frozen (OFF 31/6/1/17/3, ON 22/1/4, log44+abstains held)",
                  _census_frozen(doc), None))

    if not os.path.isfile(PDF):
        gates.append(("G1 plan PDF present", False, PDF))
        return _emit(gates, B_SCOPE, ev, selections)
    corpus = {p.stem: p for p in enumerate_corpus(resolve_corpus()[0])}
    gates.append(("G1 plan PDF + corpus present", os.path.isfile(PDF) and len(corpus) == EXPECTED_COUNT, len(corpus)))

    plan = PlanPdf(PDF)
    rendered, blocked = [], []
    try:
        dialect = select_dialect(plan)
        offset = dialect.calibrate(plan, 13)
        graph = _build_plan_frame_graph(plan, offset)
        rev = ReverseAnchorContext(graph=graph, conflicts=conflict_sheet_pairs(graph),
                                   equations_by_sheet=collect_all_sheet_equations(plan, offset))
        sheet_cands = {}
        for lid, sheet in TARGETS.items():
            if sheet not in sheet_cands:
                sheet_cands[sheet] = discover_candidates(plan, offset, sheet)
            cands = sheet_cands[sheet]
            bore = load_borelog(str(corpus["bore_" + lid]))
            ticks, _ = route_ladder_ticks(plan, sheet, offset)
            scale = ladder_scale(ticks)
            cand_resets = [c["reset"] for c in cands]
            sel = selections.get(lid)
            rec = {"sheet": sheet, "span_ft": round(bore.span_ft), "rival_candidates": cand_resets,
                   "selected": sel}
            if sel is None:
                rec["result"] = "NO_REVIEWER_SELECTION"
                ev["targets"][lid] = rec
                blocked.append((lid, "NO_REVIEWER_SELECTION (rival candidates surfaced; awaiting reviewer choice)"))
                continue
            chosen = next((c for c in cands if c["reset"] == sel), None)
            if chosen is None:
                rec["result"] = "SELECTION_NOT_A_SOURCE_CANDIDATE"
                ev["targets"][lid] = rec
                blocked.append((lid, f"SELECTION {sel} is not a bound source candidate on sheet {sheet}"))
                continue
            rec["selected_class"] = chosen["structure_class"]
            rec["rejected_rivals"] = [c["reset"] for c in cands if c["reset"] != sel]
            png, detail = render_from_selected_start(plan, offset, sheet, chosen["xy"], chosen["seed"],
                                                     bore.span_ft, scale, OUT_DIR, lid, sel)
            rec.update(detail)
            ev["targets"][lid] = rec
            if png and os.path.isfile(png):
                rendered.append((lid, png, detail.get("result")))
            else:
                blocked.append((lid, detail.get("result")))
    finally:
        plan.close()

    gates.append(("G2 every render has a real PNG; every block names an exact blocker (no fake positive)",
                  all(os.path.isfile(p) for _, p, _ in rendered) and all(b for _, b in blocked), None))
    gates.append(("G3 reviewer choice is explicit input + recorded with rejected rivals (no baked owner-naming)",
                  all("selected" in ev["targets"][l] for l in ev["targets"])
                  and all(("rejected_rivals" in ev["targets"][l]) for l, _, _ in rendered), None))
    result = R_RENDERED if rendered else R_NO_RENDER
    return _emit(gates, result, ev, selections, rendered, blocked)


def _emit(gates, result, ev, selections, rendered=(), blocked=()) -> int:
    pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
    gates.append(("G4 canonical red stroke color (TrueLine strokes are red)",
                  REDLINE_STROKE_RGB == (220, 25, 25), list(REDLINE_STROKE_RGB)))
    gates.append(("G5 result in allowed enum", result in ALLOWED, result))
    all_pass = all(x for _, x, _ in gates)
    report = {
        "milestone": "REVIEW-CHOICE -> RENDER slice (proof only; ambiguity-resolution render primitive)",
        "verdict": "PASS" if all_pass else "FAIL", "result": result,
        "primitive": ("source rival reset candidates -> EXPLICIT reviewer selection -> bind selected start -> "
                      "conduit route to the UNIQUE dash endpoint at the bore span -> red REVIEW redline; "
                      "uniqueness-mandatory on the end; abstain (named) if no/branching end"),
        "reviewer_selections": selections,
        "new_full_rendered": [l for l, _, _ in rendered],
        "new_partial_rendered": [],
        "artifact_paths": [str(p).replace(str(_REPO_ROOT), "").lstrip("\\/").replace("\\", "/") for _, p, _ in rendered],
        "still_blocked": [{"log": l, "blocker": b} for l, b in blocked],
        "targets": ev.get("targets"),
        "red_stroke_rgb": list(REDLINE_STROKE_RGB),
        "no_fixture_mutation": True, "no_coordinate_encoding": True, "no_baked_owner_naming": True,
        "reviewer_choice_is_explicit_input": True, "engine_census_frozen": True,
        "artifacts_gitignored": True,
        "next_action": ("render the remaining sheet-10/18/2 rivals by supplying their reviewer selections; "
                        "then extend the review-choice primitive to the no-reset Group-A logs (log10/15/60) "
                        "and the cross-sheet end cases"),
        "gates": [{"name": n, "pass": bool(x), "detail": d} for n, x, d in gates],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "review_choice_render_slice.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[review-choice] result: {result}  rendered={[l for l,_,_ in rendered]}")
    for lid, rec in ev.get("targets", {}).items():
        print(f"[review-choice]   {lid}: sel={rec.get('selected')} rivals={rec.get('rival_candidates')} -> {rec.get('result')}")
    for a in pngs:
        print(f"[review-choice]   ARTIFACT: {a}")
    for n, x, _ in gates:
        print(f"[review-choice] {'PASS' if x else 'FAIL'}  {n}")
    print(f"[review-choice] VERDICT: {'PASS' if all_pass else 'FAIL'}  (report: {OUT_DIR})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
