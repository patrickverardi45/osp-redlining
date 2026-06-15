r"""OWNER-PACKET-2 -- log71 RENDER ARTIFACT slice (contained proof artifact; log71-only).

Draws log71's redline on the real sheet 24 + sheet 23 PDF pages so Patrick can VISUALLY inspect it,
mirroring the controlled log53 render-artifact style: log71-only, TWO SHEET-LOCAL legs (no stroke
across the page break, no cross-sheet reconciliation):

  sheet 24 (START leg):  NEXTLINK HH start (STA 7+50=0+00)  ->  STA 5+45 matchline
  sheet 23 (END leg):    STA 5+45 matchline                 ->  FLOWER POT end (STA 6+95)

Every endpoint is RE-DERIVED from source here via the SAME proven primitives the two-leg source-bind
slice used (resolve_nextlink_hh_callout for the start, resolve_structure_position for the flower pot,
the scout's chain-reach locate_matchline_boundary for each 5+45 boundary) -- no hardcoded display-only
coordinate -- and gated against the proven source-bind values. The 5+45 matchline is consumed as
ROUTE CONTEXT (the between-leg crossing, located per-sheet in its OWN frame), never an endpoint.

The strokes FOLLOW THE DRAWN ROUTE. Sheet 24 is NOT a straight corridor (the source-bind proved the
direct band bends), so its route is the ordered source-backed CHAIN PATH from the NEXTLINK HH to the
5+45 matchline -- the shortest path through the bound conduit chain's drawn dashes (left along the
top, then up the left side), rejecting the dead-end branches off the HH junction; it is gated to be
meaningfully longer than the straight diagonal so a straight shortcut can never pass. Sheet 23 is a
clean continuous vertical corridor and orders the same way. Every route vertex is a real drawn dash
endpoint or a proven anchor; no coordinate is invented.

Red TrueLine stroke only (render.crop.REDLINE_STROKE_RGB), REVIEW-style (dashed). Source PDF/CAD
evidence colors are never touched; only TrueLine's own drawn REVIEW stroke is governed -- and it is
red. Source-backed REVIEW/proof artifact, NOT a broad renderer and NOT wired into product/UI/API. PNG
+ JSON are written under the gitignored data/outputs path and are NOT committed. No cross-sheet frame
solve. Census stays frozen.

Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_log71_render_artifact_slice
"""
from __future__ import annotations

import heapq
import json
import math
import os

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.conduit_topology import (
    MAX_DASH_GAP,
    connected_chain,
    symbol_footprint,
)
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.structure_position import (
    BRENHAM_CONDUIT_LAYERS,
    BRENHAM_STRUCTURE_LAYERS,
    POSITION_BOUND,
    resolve_nextlink_hh_callout,
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
from truelinev2.proof.run_log71_sheet_local_bind_scout import (
    END_FP_LABEL,
    INSTALLER_SYMBOL_LAYER,
    MATCHLINE_STA,
    SHEET_END,
    SHEET_START,
    START_STA,
    locate_matchline_boundary,
)
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.render.crop import REDLINE_STROKE_RGB, render_redline_stroke

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "log71_render_artifact"
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / \
    "final_engine_truth_table.json"
BASE_CONDUIT = set(BRENHAM_CONDUIT_LAYERS.values())   # BORE - VACANT PIPE / BORE - PORT
FROZEN_BUCKETS = {"DRAWABLE_REVIEW": 31, "HUMAN_ADJUSTABLE_REVIEW": 6,
                  "OUT_OF_CLASS": 1, "PICK_CARD_REVIEW": 17, "SOURCE_OR_KMZ_REQUIRED": 3}
ABSTAIN_4 = ("log5", "log31", "log38", "log43")
# proven source-bind values (extractor-derived in 2aa7192; the render is gated to match these)
PROVEN = {"s24_start": (777.24, 300.84), "s24_matchline": (198.71, 84.24),
          "s23_matchline": (198.72, 649.44), "s23_pot": (195.51, 434.24)}
MATCH_TOL = 4.0
# sheet 24 bends: its source route must be meaningfully longer than the straight diagonal, so a
# straight-diagonal shortcut can never satisfy the gate (measured ~1.27x at 2aa7192).
BEND_MIN_RATIO = 1.10

R_CREATED = "LOG71_RENDER_ARTIFACT_CREATED"
B_ENDPOINT = "BLOCKED_LOG71_RENDER_ENDPOINT_MISMATCH"
B_MATCHLINE = "BLOCKED_LOG71_RENDER_MATCHLINE_NOT_LOCATED"
B_START_ROUTE = "BLOCKED_LOG71_RENDER_START_ROUTE_NOT_SOURCE_BACKED"
B_END_ROUTE = "BLOCKED_LOG71_RENDER_END_ROUTE_NOT_SOURCE_BACKED"
B_FAILED = "BLOCKED_LOG71_RENDER_ARTIFACT_FAILED"
ALLOWED = {R_CREATED, B_ENDPOINT, B_MATCHLINE, B_START_ROUTE, B_END_ROUTE, B_FAILED}


def route_length(route) -> float:
    return sum(math.hypot(route[i + 1][0] - route[i][0], route[i + 1][1] - route[i][1])
               for i in range(len(route) - 1))


def order_chain_route(chain, start_xy, end_xy, max_gap: float = MAX_DASH_GAP):
    """Ordered source-backed route along the drawn conduit ``chain`` from ``start_xy`` to ``end_xy``,
    as the shortest path through the chain's dash graph: nodes are dash endpoints (plus the two
    anchors), edges are each drawn dash (its own two endpoints, any length) and every dash-gap hop
    <= ``max_gap``. This FOLLOWS THE DRAWN BEND (sheet 24 turns left-then-up from the NEXTLINK HH to
    the 5+45 matchline) and rejects the dead-end branches off the HH junction -- never a straight
    diagonal shortcut. Pure: every interior vertex is a real drawn dash endpoint and the two ends are
    the passed-in proven anchors; no coordinate is invented. Returns [] when the chain's drawn dashes
    do not connect the two anchors."""
    def rnd(p):
        return (round(p[0], 1), round(p[1], 1))

    s_n, e_n = rnd(start_xy), rnd(end_xy)
    lines = [((ln[0], ln[1]), (ln[2], ln[3])) for seg in chain for ln in (seg.get("lines") or ())]
    nodes = {s_n, e_n}
    for a, b in lines:
        nodes.add(rnd(a))
        nodes.add(rnd(b))
    nodes = list(nodes)
    idx = {p: i for i, p in enumerate(nodes)}
    adj = [dict() for _ in nodes]

    def edge(i, j, w):
        if i != j and (j not in adj[i] or w < adj[i][j]):
            adj[i][j] = w
            adj[j][i] = w

    for a, b in lines:   # each drawn dash connects its OWN two endpoints, any length
        edge(idx[rnd(a)], idx[rnd(b)], math.hypot(a[0] - b[0], a[1] - b[1]))
    n = len(nodes)
    for i in range(n):   # dash-gap hops <= max_gap (a dashed line includes its gaps)
        for j in range(i + 1, n):
            dd = math.hypot(nodes[i][0] - nodes[j][0], nodes[i][1] - nodes[j][1])
            if dd <= max_gap:
                edge(i, j, dd)

    src, dst = idx[s_n], idx[e_n]
    dist = [math.inf] * n
    prev = [-1] * n
    dist[src] = 0.0
    pq = [(0.0, src)]
    while pq:
        dc, u = heapq.heappop(pq)
        if dc > dist[u]:
            continue
        if u == dst:
            break
        for v, w in adj[u].items():
            if dc + w < dist[v]:
                dist[v] = dc + w
                prev[v] = u
                heapq.heappush(pq, (dist[v], v))
    if dist[dst] == math.inf:
        return []
    path, v = [], dst
    while v != -1:
        path.append(nodes[v])
        v = prev[v]
    path.reverse()
    # anchor the exact proven endpoints (the node rounding is sub-0.1); interior stays real dashes
    path[0], path[-1] = tuple(start_xy), tuple(end_xy)
    return path


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
    ea = (rec.get("log71") or {}).get("endpoint_anchors") or {}
    start_a, end_a = ea.get("start") or {}, ea.get("end") or {}
    end_note_up = str(end_a.get("owner_note_text") or "").upper()
    gates, ev = [], {"sheets": [SHEET_START, SHEET_END]}

    gates.append(("G0 engine census frozen (OFF 31/6/1/17/3, ON 22/1/4, log44+abstains held)",
                  _census_frozen(doc), None))
    # preserve behavior: log53 + log64 encoded anchors untouched
    l53s = (rec["log53"].get("endpoint_anchors") or {}).get("start") or {}
    l64s = (rec["log64"].get("endpoint_anchors") or {}).get("start") or {}
    l64e = (rec["log64"].get("endpoint_anchors") or {}).get("end") or {}
    gates.append(("G0b log53 + log64 encoded anchors unchanged (behavior preserved)",
                  l53s.get("structure_class") == "nextlink_hh"
                  and l64s.get("structure_class") == "installer_hh" and l64s.get("station") == "3+69"
                  and l64e.get("structure_class") == "flower_pot" and l64e.get("station") == "1+00", None))
    # consume the encoded log71 identity; 5+45 stays route context (no third anchor)
    gates.append(("G1 log71 anchors consumed (nextlink_hh @7+50 s24 -> flower_pot @6+95 s23)",
                  start_a.get("structure_class") == "nextlink_hh" and start_a.get("station") == START_STA
                  and end_a.get("structure_class") == "flower_pot" and end_a.get("station") == END_FP_LABEL,
                  {"start": start_a.get("station"), "end": end_a.get("station")}))
    gates.append(("G2 5+45 matchline = route context not endpoint (no 3rd anchor; preserved in end note)",
                  set(ea) <= {"start", "end"} and MATCHLINE_STA in end_note_up
                  and start_a.get("station") != MATCHLINE_STA and end_a.get("station") != MATCHLINE_STA,
                  {"anchor_keys": sorted(ea)}))

    if not os.path.isfile(PDF):
        gates.append(("G3 plan PDF present", False, f"missing {PDF}"))
        return _emit(gates, B_FAILED, ev, [])
    corpus_dir, _ = resolve_corpus()
    corpus = {p.stem: p for p in enumerate_corpus(corpus_dir)} if os.path.isdir(corpus_dir) else {}
    gates.append(("G3 plan PDF + corpus present",
                  os.path.isfile(PDF) and len(corpus) == EXPECTED_COUNT,
                  {"pdf": os.path.isfile(PDF), "corpus": len(corpus)}))

    plan = PlanPdf(PDF)
    artifacts = []
    result = B_FAILED
    try:
        dialect = select_dialect(plan)
        offset = dialect.calibrate(plan, 13)

        # ---- sheet 24: re-derive NEXTLINK HH start + 5+45 matchline boundary ------
        ws, ds = plan.words(SHEET_START, offset), plan.line_items(SHEET_START, offset)
        nv = resolve_nextlink_hh_callout(station_sta=START_STA, words=ws, drawings=ds,
                                         callout_layer="ANNOTATION", symbol_layer="NEXTLINK")
        s24_start = tuple(nv.symbol_xy) if (nv.result == POSITION_BOUND and nv.symbol_xy) else None
        fp24 = symbol_footprint(ds, INSTALLER_SYMBOL_LAYER, s24_start) if s24_start else None
        chain24 = connected_chain([x for x in ds if x.get("layer") in BASE_CONDUIT], fp24) if fp24 else []
        bnd24, reach24, uniq24 = (locate_matchline_boundary(ws, ds, MATCHLINE_STA, chain24)
                                  if chain24 else (None, None, False))

        # ---- sheet 23: re-derive FLOWER POT end + 5+45 matchline boundary ---------
        we, de = plan.words(SHEET_END, offset), plan.line_items(SHEET_END, offset)
        pv = resolve_structure_position(label_text=END_FP_LABEL, structure_class="flower_pot",
                                        words=we, drawings=de, layer_table=BRENHAM_STRUCTURE_LAYERS,
                                        context_texts=("FLOWER", "POT"))
        s23_pot = tuple(pv.symbol_xy) if (pv.result == POSITION_BOUND and pv.symbol_xy) else None
        fp23 = symbol_footprint(de, "FLOWER POT", s23_pot) if s23_pot else None
        chain23 = connected_chain([x for x in de if x.get("layer") in BASE_CONDUIT], fp23) if fp23 else []
        bnd23, reach23, uniq23 = (locate_matchline_boundary(we, de, MATCHLINE_STA, chain23)
                                  if chain23 else (None, None, False))

        ev["s24_start"] = [round(c, 2) for c in s24_start] if s24_start else None
        ev["s24_matchline"] = [round(c, 2) for c in bnd24] if bnd24 else None
        ev["s23_pot"] = [round(c, 2) for c in s23_pot] if s23_pot else None
        ev["s23_matchline"] = [round(c, 2) for c in bnd23] if bnd23 else None

        def near(a, key):
            b = PROVEN[key]
            return a is not None and math.hypot(a[0] - b[0], a[1] - b[1]) <= MATCH_TOL

        termini_ok = near(s24_start, "s24_start") and near(s23_pot, "s23_pot")
        gates.append(("G4 termini re-derived from source match the proven bind (HH s24 + flower pot s23)",
                      termini_ok, {"s24_start": ev["s24_start"], "s23_pot": ev["s23_pot"]}))
        if not termini_ok:
            return _emit(gates, B_ENDPOINT, ev, artifacts)

        matchlines_ok = (bnd24 is not None and uniq24 and near(bnd24, "s24_matchline")
                         and bnd23 is not None and uniq23 and near(bnd23, "s23_matchline"))
        gates.append(("G5 5+45 matchline re-derived per-sheet via chain-reach (route context, not endpoint)",
                      matchlines_ok, {"s24_matchline": ev["s24_matchline"], "s23_matchline": ev["s23_matchline"]}))
        if not matchlines_ok:
            return _emit(gates, B_MATCHLINE, ev, artifacts)
        s24_start, bnd24 = tuple(s24_start), tuple(bnd24)
        s23_pot, bnd23 = tuple(s23_pot), tuple(bnd23)

        # ---- sheet 24 route: ordered source-backed chain path (bends; no shortcut) -
        route24 = order_chain_route(chain24, s24_start, bnd24)
        straight24 = math.hypot(s24_start[0] - bnd24[0], s24_start[1] - bnd24[1])
        len24 = route_length(route24)
        ev["s24_route_vertices"] = len(route24)
        ev["s24_route_len"] = round(len24, 1)
        ev["s24_straight_len"] = round(straight24, 1)
        ev["s24_bend_ratio"] = round(len24 / straight24, 3) if straight24 else None
        s24_route_ok = (len(route24) >= 3 and straight24 > 0
                        and len24 >= straight24 * BEND_MIN_RATIO)
        gates.append(("G6 sheet 24 route is the ordered source-backed chain path (bends; not a straight diagonal)",
                      s24_route_ok, {"vertices": len(route24), "bend_ratio": ev["s24_bend_ratio"]}))
        if not s24_route_ok:
            return _emit(gates, B_START_ROUTE, ev, artifacts)

        # ---- sheet 23 route: source-backed continuous vertical corridor -----------
        route23 = order_chain_route(chain23, bnd23, s23_pot)
        ev["s23_route_vertices"] = len(route23)
        ev["s23_route_len"] = round(route_length(route23), 1)
        s23_route_ok = len(route23) >= 2
        gates.append(("G7 sheet 23 route is the source-backed corridor (5+45 matchline -> flower pot)",
                      s23_route_ok, {"vertices": len(route23)}))
        if not s23_route_ok:
            return _emit(gates, B_END_ROUTE, ev, artifacts)

        # ---- render the two SEPARATE sheet-local red REVIEW strokes ---------------
        p24 = render_redline_stroke(
            plan, "log71", SHEET_START, offset, route24, status="REVIEW",
            reason="OWNER-PACKET-2 source-backed: NEXTLINK HH 7+50=0+00 -> 5+45 matchline (bends; ordered chain path)",
            out_dir=str(OUT_DIR), mandatory_points=[s24_start, bnd24], pad=170.0)
        p23 = render_redline_stroke(
            plan, "log71", SHEET_END, offset, route23, status="REVIEW",
            reason="OWNER-PACKET-2 source-backed: 5+45 matchline -> STA 6+95 FLOWER POT (continuous vertical corridor)",
            out_dir=str(OUT_DIR), mandatory_points=[bnd23, s23_pot], pad=170.0)
        artifacts = [p for p in (p24, p23) if p]
        gates.append(("G8 two SEPARATE sheet-local PNGs rendered (s24 + s23; red REVIEW stroke)",
                      p24 is not None and p23 is not None and len(artifacts) == 2, artifacts))
        if not (p24 and p23):
            return _emit(gates, B_FAILED, ev, artifacts)

        # ---- no cross-sheet reconciliation: distinct per-sheet matchline frames ----
        no_cross = (ev["s24_matchline"] != ev["s23_matchline"] and SHEET_START != SHEET_END)
        gates.append(("G9 two legs rendered in SEPARATE frames; per-sheet 5+45 points not reconciled",
                      no_cross, {"s24_matchline": ev["s24_matchline"], "s23_matchline": ev["s23_matchline"]}))
        result = R_CREATED
    finally:
        plan.close()

    return _emit(gates, result, ev, artifacts)


def _emit(gates, result, ev, artifacts) -> int:
    pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
    expected = ["log71_s23_redline_stroke.png", "log71_s24_redline_stroke.png"]
    gates.append(("G10 exactly two log71 PNGs (s24 + s23); log71-only, sheet-local",
                  pngs == expected, pngs))
    gates.append(("G11 canonical red stroke color", REDLINE_STROKE_RGB == (220, 25, 25),
                  list(REDLINE_STROKE_RGB)))
    gates.append(("G12 result in allowed enum", result in ALLOWED, result))
    created = result == R_CREATED
    all_pass = all(x for _, x, _ in gates) and created
    report = {
        "milestone": "OWNER-PACKET-2 -- log71 render artifact (contained proof; visual inspection)",
        "verdict": "PASS" if all_pass else "FAIL",
        "result": result, "target": "log71 ONLY", "sheets": [SHEET_START, SHEET_END],
        "legs": {
            "sheet_24_start": {"from": "NEXTLINK HH STA 7+50=0+00", "to": "STA 5+45 matchline",
                               "start_xy": ev.get("s24_start"), "matchline_xy": ev.get("s24_matchline"),
                               "route_vertices": ev.get("s24_route_vertices"),
                               "route_len": ev.get("s24_route_len"), "straight_len": ev.get("s24_straight_len"),
                               "bend_ratio": ev.get("s24_bend_ratio"), "bends_not_straight_diagonal": True},
            "sheet_23_end": {"from": "STA 5+45 matchline", "to": "FLOWER POT STA 6+95",
                             "matchline_xy": ev.get("s23_matchline"), "pot_xy": ev.get("s23_pot"),
                             "route_vertices": ev.get("s23_route_vertices"),
                             "route_len": ev.get("s23_route_len"), "continuous_vertical_corridor": True},
        },
        "artifacts": artifacts,
        "red_stroke_rgb": list(REDLINE_STROKE_RGB),
        "matchline_5_45": "route context located per-sheet by chain-reach (not an endpoint identity)",
        "sheet_local_only": True, "log71_only": True, "drawn_across_page_break": False,
        "no_cross_sheet": True, "no_cross_sheet_reconciliation": True,
        "coords_are_extractor_derived": True, "no_invented_coordinates": True,
        "no_screenshot_pixels": True, "broad_renderer": False, "product_wired": False,
        "source_corridor_layers": sorted(BASE_CONDUIT),
        "next_slice": ("cross-sheet frame JOIN for log71 (one printed 5+45 matchline equation typeset at "
                       "both boundaries + footage closure) to relate the two sheet-local legs -- a later, "
                       "separately-authorized step; still no broad renderer / no product wiring."),
        "evidence": ev,
        "gates": [{"name": n, "pass": bool(x), "detail": d} for n, x, d in gates],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "log71_render_artifact.json").write_text(json.dumps(report, indent=2, default=str),
                                                        encoding="utf-8")
    print(f"[log71-render] result: {result}")
    for k in ("s24_start", "s24_matchline", "s24_route_vertices", "s24_route_len", "s24_straight_len",
              "s24_bend_ratio", "s23_matchline", "s23_pot", "s23_route_vertices", "s23_route_len"):
        if k in ev:
            print(f"[log71-render]   {k}: {ev[k]}")
    for a in artifacts:
        print(f"[log71-render]   ARTIFACT: {a}")
    for n, x, _ in gates:
        print(f"[log71-render] {'PASS' if x else 'FAIL'}  {n}")
    print(f"[log71-render] VERDICT: {'PASS' if all_pass else 'FAIL'}  (report: {OUT_DIR})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
