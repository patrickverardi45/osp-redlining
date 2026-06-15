r"""OWNER-PACKET-2 -- log64 RENDER ARTIFACT slice (contained proof artifact; log64-only).

Draws log64's redline on the real sheet-21 PDF so Patrick can VISUALLY inspect it, mirroring the
controlled log53 render-artifact style but log64-only and single-sheet. ONE sheet-local red REVIEW
stroke:

  sheet 21: installer HH start (STA 3+69=0+00) -> FLOWER POT end (STA 1+00), 100' DIR. BORE

Every endpoint is RE-DERIVED from source here via the SAME proven primitives the log64 source-bind
slice used (resolve_structure_position for both termini) -- no hardcoded/invented coordinate -- and
gated against the proven bind values. The stroke FOLLOWS THE DRAWN ROUTE: the BORE - VACANT PIPE /
BORE - PORT corridor (down-sampled, anchored at the two proven endpoints), so every vertex is a real
source dash endpoint or a proven anchor. order_route is reused from the log53 render slice; the
source-bind laws (start label, callout grammar, corridor continuity) are reused from the log64
source-bind slice -- this proof builds on them, it does not re-invent them.

Red TrueLine stroke only (render.crop.REDLINE_STROKE_RGB), REVIEW-style (dashed). Source-backed
REVIEW/proof artifact, NOT a broad renderer and NOT wired into product/UI/API. PNG + JSON are written
under the gitignored data/outputs path and are NOT committed.

Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_log64_render_artifact_slice
"""
from __future__ import annotations

import json
import math
import os

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.conduit_topology import connected_chain, dash_endpoints, symbol_footprint
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.structure_position import (
    BRENHAM_CONDUIT_LAYERS,
    BRENHAM_STRUCTURE_LAYERS,
    POSITION_BOUND,
    resolve_structure_position,
)
from truelinev2.ingest.manual_adjudication import (
    activation_summary,
    apply_adjudications,
    load_adjudication,
    parent_run_duplicate_check,
)
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.proof.run_brenham_corpus import EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_log53_render_artifact_slice import order_route
from truelinev2.proof.run_log64_sheet21_source_bind_slice import (
    CORRIDOR_HALF,
    _FOOTAGE_RE,
    _SEG_RE,
    corridor_is_continuous,
    start_label_text,
)
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.render.crop import REDLINE_STROKE_RGB, render_redline_stroke

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "log64_render_artifact"
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / \
    "final_engine_truth_table.json"
SHEET = 21
INSTALLER_SYMBOL_LAYER = "NEXTLINK"   # installer_hh shares the NEXTLINK symbol layer (dialect)
FROZEN_BUCKETS = {"DRAWABLE_REVIEW": 31, "HUMAN_ADJUSTABLE_REVIEW": 6,
                  "OUT_OF_CLASS": 1, "PICK_CARD_REVIEW": 17, "SOURCE_OR_KMZ_REQUIRED": 3}
ABSTAIN_4 = ("log5", "log31", "log38", "log43")
# proven sheet-21 binds (extractor-derived in 16b9914; the render is gated to match these)
PROVEN = {"start": (252.31, 389.34), "end": (254.29, 534.07)}
MATCH_TOL = 4.0
_BASE_CONDUIT = set(BRENHAM_CONDUIT_LAYERS.values())   # BORE - VACANT PIPE / BORE - PORT

R_CREATED = "LOG64_RENDER_ARTIFACT_CREATED"
B_NO_CORRIDOR = "BLOCKED_LOG64_RENDER_NO_SOURCE_CORRIDOR"
B_AMBIGUOUS = "BLOCKED_LOG64_RENDER_ROUTE_AMBIGUOUS"
B_ENDPOINT = "BLOCKED_LOG64_RENDER_ENDPOINT_MISSING"
B_FAILED = "BLOCKED_LOG64_RENDER_ARTIFACT_FAILED"
ALLOWED = {R_CREATED, B_NO_CORRIDOR, B_AMBIGUOUS, B_ENDPOINT, B_FAILED}


def corridor_points(chain_eps, s_xy, e_xy, half: float = CORRIDOR_HALF):
    """Real conduit dash endpoints (x, y) inside the direct start->end corridor band (x within
    ``half`` of the centerline, y between the endpoints). Pure; invents nothing."""
    xc = (s_xy[0] + e_xy[0]) / 2.0
    ylo, yhi = min(s_xy[1], e_xy[1]), max(s_xy[1], e_xy[1])
    return [(round(p[0], 2), round(p[1], 2)) for p in chain_eps
            if abs(p[0] - xc) <= half and (ylo - 5) <= p[1] <= (yhi + 5)]


def build_route(s_xy, e_xy, corridor_pts, step: float = 35.0):
    """Route polyline oriented START -> END (installer HH -> flower pot), as documented.
    order_route requires the higher-y anchor FIRST, and log64's start (installer HH) sits BELOW
    its end (flower pot), so call it higher-y-first and then re-orient the result to start->end.
    Every interior vertex is a real corridor point (order_route guarantees it); re-orientation
    only flips vertex ORDER, never a coordinate (the drawn stroke is undirected regardless)."""
    hi, lo = (s_xy, e_xy) if s_xy[1] >= e_xy[1] else (e_xy, s_xy)
    route = order_route(hi, lo, corridor_pts, step=step)
    return route if route and route[0] == s_xy else route[::-1]


def _census_frozen(doc) -> bool:
    if not TRUTH.is_file():
        return False
    truth = json.loads(TRUTH.read_text(encoding="utf-8"))
    baseline = {r["bore_id"]: dict(r) for r in truth["rows"]}
    off_rows = apply_adjudications(baseline, enabled=False)
    on_rows = apply_adjudications(baseline, enabled=True, doc=doc)
    summ = activation_summary(on_rows)
    buckets = {}
    for r in off_rows.values():
        buckets[r["completion_bucket"]] = buckets.get(r["completion_bucket"], 0) + 1
    return (off_rows is baseline and buckets == FROZEN_BUCKETS
            and summ["manual_review_drawable"] == 22 and summ["manual_source_verification"] == 1
            and summ["manual_abstain"] == 4
            and on_rows["log44"]["adjudication"]["drawable_status"] == "non_drawable"
            and all(on_rows[l]["adjudication"]["drawable_status"] == "abstain" for l in ABSTAIN_4)
            and not parent_run_duplicate_check(doc))


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.png"):
        stale.unlink()

    doc = load_adjudication()
    rec = {r["log_id"]: r for r in doc["logs"]}
    ea = (rec.get("log64") or {}).get("endpoint_anchors") or {}
    start_a, end_a = ea.get("start") or {}, ea.get("end") or {}
    gates, ev = [], {"sheet": SHEET}

    gates.append(("G0 engine census frozen (OFF 31/6/1/17/3, ON 22/1/4, log44+abstains held)",
                  _census_frozen(doc), None))
    # preserve behavior: log53 + log64 anchors untouched
    l53s = (rec["log53"].get("endpoint_anchors") or {}).get("start") or {}
    gates.append(("G0b log53 + log64 encoded anchors unchanged (behavior preserved)",
                  l53s.get("structure_class") == "nextlink_hh"
                  and start_a.get("structure_class") == "installer_hh" and start_a.get("station") == "3+69"
                  and end_a.get("structure_class") == "flower_pot" and end_a.get("station") == "1+00", None))

    if not os.path.isfile(PDF):
        gates.append(("G1 plan PDF present", False, f"missing {PDF}"))
        return _emit(gates, B_FAILED, ev, [])
    corpus_dir, _ = resolve_corpus()
    corpus = {p.stem: p for p in enumerate_corpus(corpus_dir)} if os.path.isdir(corpus_dir) else {}
    gates.append(("G1 plan PDF + corpus present",
                  os.path.isfile(PDF) and len(corpus) == EXPECTED_COUNT, len(corpus)))

    plan = PlanPdf(PDF)
    artifacts = []
    result = B_FAILED
    try:
        dialect = select_dialect(plan)
        offset = dialect.calibrate(plan, 13)
        words = plan.words(SHEET, offset)
        draw = plan.line_items(SHEET, offset)
        lines = plan.lines(SHEET, offset)

        # ---- re-derive both endpoints from source (the proven binds) -------------
        sv = resolve_structure_position(label_text=start_label_text(start_a),
                                        structure_class="installer_hh", words=words, drawings=draw,
                                        layer_table=BRENHAM_STRUCTURE_LAYERS)
        pv = resolve_structure_position(label_text=end_a.get("station"), structure_class="flower_pot",
                                        words=words, drawings=draw, layer_table=BRENHAM_STRUCTURE_LAYERS,
                                        context_texts=("FLOWER", "POT"))
        s_xy = tuple(sv.symbol_xy) if (sv.result == POSITION_BOUND and sv.symbol_xy) else None
        e_xy = tuple(pv.symbol_xy) if (pv.result == POSITION_BOUND and pv.symbol_xy) else None
        ev["start_symbol_xy"] = [round(c, 2) for c in s_xy] if s_xy else None
        ev["end_symbol_xy"] = [round(c, 2) for c in e_xy] if e_xy else None

        def near(a, key):
            b = PROVEN[key]
            return a is not None and math.hypot(a[0] - b[0], a[1] - b[1]) <= MATCH_TOL
        endpoints_ok = near(s_xy, "start") and near(e_xy, "end")
        gates.append(("G2 both endpoints re-derived from source match the proven bind (<= 4 pt)",
                      endpoints_ok, {"start": ev["start_symbol_xy"], "end": ev["end_symbol_xy"]}))
        if not endpoints_ok:
            return _emit(gates, B_ENDPOINT, ev, artifacts)

        # ---- callout present + unique (route clarity) ----------------------------
        seg = [ln for ln in lines if _SEG_RE.search(ln)]
        foot = [ln for ln in lines if _FOOTAGE_RE.search(ln)]
        ev["callout_segment_lines"] = seg[:3]
        callout_ok = len(seg) == 1 and len(foot) >= 1
        gates.append(("G3 owner 0+00->1+00 / 100' callout present + unique", callout_ok,
                      {"seg": len(seg), "footage": len(foot)}))
        if not callout_ok:
            return _emit(gates, B_AMBIGUOUS, ev, artifacts)

        # ---- source corridor: continuous BORE - VACANT PIPE / PORT chain ---------
        fp = symbol_footprint(draw, INSTALLER_SYMBOL_LAYER, s_xy)
        chain = connected_chain([x for x in draw if x.get("layer") in _BASE_CONDUIT], fp) if fp else []
        eps = dash_endpoints(chain)
        cpts = corridor_points(eps, s_xy, e_xy)
        ylo, yhi = min(s_xy[1], e_xy[1]), max(s_xy[1], e_xy[1])
        band_ys = sorted({p[1] for p in cpts})
        continuous = bool(chain) and corridor_is_continuous(band_ys, ylo, yhi)
        ev["chain_segs"] = len(chain)
        ev["corridor_band_points"] = len(cpts)
        ev["corridor_continuous"] = continuous
        gates.append(("G4 source corridor (BORE - VACANT PIPE/PORT) continuous between endpoints",
                      continuous, {"band_pts": len(cpts)}))
        if not continuous:
            return _emit(gates, B_NO_CORRIDOR, ev, artifacts)

        # ---- build the route + render the red REVIEW stroke ----------------------
        route = build_route(s_xy, e_xy, cpts, step=35.0)
        ev["route_vertices"] = len(route)
        # follows the corridor, not a straight-line fake: needs >= 1 interior corridor vertex
        gates.append(("G5 stroke follows corridor (>= 1 source interior vertex; no straight-line fake)",
                      len(route) >= 3, {"vertices": len(route)}))
        if len(route) < 3:
            return _emit(gates, B_NO_CORRIDOR, ev, artifacts)

        png = render_redline_stroke(
            plan, "log64", SHEET, offset, route, status="REVIEW",
            reason="OWNER-PACKET-2 source-backed: installer HH 3+69=0+00 -> 1+00 FLOWER POT (100' DIR. BORE, BORE - VACANT PIPE corridor)",
            out_dir=str(OUT_DIR), mandatory_points=[s_xy, e_xy], pad=170.0)
        artifacts = [png] if png else []
        gates.append(("G6 PNG artifact rendered (red REVIEW stroke)",
                      png is not None and os.path.isfile(png), png))
        if not (png and os.path.isfile(png)):
            return _emit(gates, B_FAILED, ev, artifacts)
        result = R_CREATED
    finally:
        plan.close()

    return _emit(gates, result, ev, artifacts)


def _emit(gates, result, ev, artifacts) -> int:
    pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
    gates.append(("G7 exactly one log64 sheet-21 PNG (log64-only, sheet-local)",
                  pngs == ["log64_s21_redline_stroke.png"], pngs))
    gates.append(("G8 canonical red stroke color", REDLINE_STROKE_RGB == (220, 25, 25),
                  list(REDLINE_STROKE_RGB)))
    gates.append(("G9 result in allowed enum", result in ALLOWED, result))
    created = result == R_CREATED
    all_pass = all(x for _, x, _ in gates) and created
    report = {
        "milestone": "OWNER-PACKET-2 -- log64 render artifact (contained proof; visual inspection)",
        "verdict": "PASS" if all_pass else "FAIL",
        "result": result, "target": "log64 ONLY", "sheet": SHEET,
        "endpoints": {"start": ev.get("start_symbol_xy"), "end": ev.get("end_symbol_xy")},
        "artifacts": artifacts,
        "red_stroke_rgb": list(REDLINE_STROKE_RGB),
        "sheet_local_only": True, "log64_only": True, "single_sheet": True,
        "source_corridor_layers": sorted(_BASE_CONDUIT),
        "coords_are_extractor_derived": True, "no_invented_coordinates": True,
        "no_screenshot_pixels": True, "no_cross_sheet": True,
        "broad_renderer": False, "product_wired": False,
        "evidence": ev,
        "gates": [{"name": n, "pass": bool(x), "detail": d} for n, x, d in gates],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "log64_render_artifact.json").write_text(json.dumps(report, indent=2, default=str),
                                                        encoding="utf-8")
    print(f"[log64-render] result: {result}")
    for k in ("start_symbol_xy", "end_symbol_xy", "chain_segs", "corridor_band_points",
              "corridor_continuous", "route_vertices"):
        if k in ev:
            print(f"[log64-render]   {k}: {ev[k]}")
    for a in artifacts:
        print(f"[log64-render]   ARTIFACT: {a}")
    for n, x, _ in gates:
        print(f"[log64-render] {'PASS' if x else 'FAIL'}  {n}")
    print(f"[log64-render] VERDICT: {'PASS' if all_pass else 'FAIL'}  (report: {OUT_DIR})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
