r"""OWNER-PACKET-2 -- log53 matchline boundary TERMINATION slice (PROOF ONLY).

Now that the start NEXTLINK HH is bound and the BORE - LATERAL chain reaches the matchline
band, this answers ONE question: can log53's source-backed conduit chain terminate at a
DETERMINISTIC sheet-5 boundary point on the unique 24+11 matchline seam?

Method (existing seams only; composes prior proven slices -- NO new core code):
  1. re-bind the start via resolve_nextlink_hh_callout -> start symbol;
  2. build the conduit chain (base | BORE - LATERAL coverage) from the start footprint;
  3. identify the unique sheet-5 24+11 matchline (label '24+11/...' -> nearest MATCHLINE
     line, label + line uniqueness gated);
  4. confirm the chain REACHES the matchline (nearest dash endpoint <= MAX_DASH_GAP);
  5. resolve the boundary point with the PROVEN matchline_join.extend_dash_to_boundary
     (terminal dash extended along its OWN drawn direction to the matchline centerline,
     capped at the dash-gap constant -- the same law graded for log65);
  6. corroborate the point lies ON the matchline line AND on the route alignment column
     (nearest clean route-ladder tick x) -- guards against a stray lateral crossing;
  7. cross-sheet (sheet 6) identity is reported via translate_between_sheets; if None it is
     EXPLICITLY DEFERRED -> BOUNDARY_POINT_RESOLVED_SHEET5_ONLY (no frame overreach here).

No renderer output, no stroke, no PNG/PDF artifact, no broad frame solving, no invented
coordinates, no screenshot pixels, no dialect change. Proof-only; artifacts gitignored.
Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_log53_matchline_boundary_termination_slice
"""
from __future__ import annotations

import json
import math
import os
import re

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.conduit_topology import (
    MAX_DASH_GAP,
    connected_chain,
    dash_endpoints,
    symbol_footprint,
)
from truelinev2.extract.matchline_join import (
    extend_dash_to_boundary,
    matchline_bboxes,
    nearest_gap,
)
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.structure_position import (
    BRENHAM_CONDUIT_LAYERS,
    BRENHAM_LATERAL_CONDUIT_LAYERS,
    POSITION_BOUND,
    resolve_nextlink_hh_callout,
)
from truelinev2.extract.tick_path import route_ladder_ticks
from truelinev2.ingest.manual_adjudication import (
    activation_summary,
    apply_adjudications,
    load_adjudication,
    parent_run_duplicate_check,
)
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.match.frames import _build_plan_frame_graph, translate_between_sheets
from truelinev2.proof.run_brenham_corpus import EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "log53_matchline_boundary_termination_slice"
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / \
    "final_engine_truth_table.json"
CALLOUT_LAYER, SYMBOL_LAYER, MATCHLINE_LAYER = "ANNOTATION", "NEXTLINK", "MATCHLINE"
ON_LINE_MARGIN = 4.0      # boundary point must sit on the matchline line (+/- margin)
ALIGN_TOL = 20.0          # boundary x must sit on the route-ladder alignment column
FROZEN_BUCKETS = {"DRAWABLE_REVIEW": 31, "HUMAN_ADJUSTABLE_REVIEW": 6,
                  "OUT_OF_CLASS": 1, "PICK_CARD_REVIEW": 17, "SOURCE_OR_KMZ_REQUIRED": 3}
ABSTAIN_4 = ("log5", "log31", "log38", "log43")

R_RESOLVED = "BOUNDARY_POINT_RESOLVED"
R_RESOLVED_S5 = "BOUNDARY_POINT_RESOLVED_SHEET5_ONLY"
R_STOPS = "BLOCKED_CHAIN_STOPS_BEFORE_MATCHLINE"
R_INTERSECT_AMBIG = "BLOCKED_CHAIN_MATCHLINE_INTERSECTION_AMBIGUOUS"
R_NOT_ON_CHAIN = "BLOCKED_BOUNDARY_POINT_NOT_ON_CHAIN"
R_FRAME = "BLOCKED_FRAME_CONTESTED_MATCHLINE"
R_LABEL_NOT_UNIQUE = "BLOCKED_MATCHLINE_LABEL_NOT_UNIQUE"
R_LINE_NOT_UNIQUE = "BLOCKED_MATCHLINE_LINE_NOT_UNIQUE"
R_NO_SAFE = "BLOCKED_NO_SAFE_BOUNDARY_POINT"
ALLOWED = {R_RESOLVED, R_RESOLVED_S5, R_STOPS, R_INTERSECT_AMBIG, R_NOT_ON_CHAIN,
           R_FRAME, R_LABEL_NOT_UNIQUE, R_LINE_NOT_UNIQUE, R_NO_SAFE}


def _on_line(pt, bbox, m=ON_LINE_MARGIN):
    return (bbox[0] - m <= pt[0] <= bbox[2] + m and bbox[1] - m <= pt[1] <= bbox[3] + m)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.png"):
        stale.unlink()  # no render/stroke lane: a PNG must never exist

    doc = load_adjudication()
    truth = json.loads(TRUTH.read_text(encoding="utf-8"))
    baseline = {r["bore_id"]: dict(r) for r in truth["rows"]}
    off_rows = apply_adjudications(baseline, enabled=False)
    on_rows = apply_adjudications(baseline, enabled=True, doc=doc)
    summ = activation_summary(on_rows)
    rec = {r["log_id"]: r for r in doc["logs"]}
    end_a = (rec["log53"].get("endpoint_anchors") or {}).get("end") or {}
    start_a = (rec["log53"].get("endpoint_anchors") or {}).get("start") or {}

    def buckets(rows):
        c = {}
        for r in rows.values():
            c[r["completion_bucket"]] = c.get(r["completion_bucket"], 0) + 1
        return c

    gates = []
    gates.append(("G1 flag OFF byte-identical (31/6/1/17/3)",
                  off_rows is baseline and buckets(off_rows) == FROZEN_BUCKETS, buckets(off_rows)))
    gates.append(("G2 flag ON 22/1/4",
                  summ["manual_review_drawable"] == 22 and summ["manual_source_verification"] == 1
                  and summ["manual_abstain"] == 4, None))
    gates.append(("G3 endpoint_anchors.end consumed (matchline_continuation @ 24+11)",
                  end_a.get("boundary_kind") == "matchline_continuation"
                  and end_a.get("station") == "24+11", end_a))
    gates.append(("G4 log44 blocked / abstains held / no dup",
                  on_rows["log44"]["adjudication"]["drawable_status"] == "non_drawable"
                  and all(on_rows[l]["adjudication"]["drawable_status"] == "abstain" for l in ABSTAIN_4)
                  and not parent_run_duplicate_check(doc), None))

    result = R_NO_SAFE
    ev = {}
    if not os.path.isfile(PDF):
        gates.append(("G5 plan PDF present", False, f"missing {PDF}"))
        return _emit(gates, result, ev)
    corpus_dir, _ = resolve_corpus()
    corpus = {p.stem: p for p in enumerate_corpus(corpus_dir)} if os.path.isdir(corpus_dir) else {}
    gates.append(("G5 plan PDF + corpus present",
                  os.path.isfile(PDF) and len(corpus) == EXPECTED_COUNT,
                  {"pdf": os.path.isfile(PDF), "corpus": len(corpus)}))

    conduit_layers = set(BRENHAM_CONDUIT_LAYERS.values()) | set(BRENHAM_LATERAL_CONDUIT_LAYERS.values())
    plan = PlanPdf(PDF)
    try:
        dialect = select_dialect(plan)
        offset = dialect.calibrate(plan, 13)
        words = plan.words(5, offset)
        draw = plan.line_items(5, offset)

        v = resolve_nextlink_hh_callout(station_sta=start_a.get("station"), words=words,
                                        drawings=draw, callout_layer=CALLOUT_LAYER,
                                        symbol_layer=SYMBOL_LAYER)
        ev["start_bind_result"] = v.result
        if v.result != POSITION_BOUND or not v.symbol_xy:
            result = R_NO_SAFE
            ev["why"] = "start symbol did not re-bind; cannot anchor a conduit chain"
            return _emit(gates, result, ev)
        start = tuple(v.symbol_xy)
        ev["bound_start_symbol"] = [round(c, 1) for c in start]
        fp = symbol_footprint(draw, SYMBOL_LAYER, start)
        chain = connected_chain([x for x in draw if x.get("layer") in conduit_layers], fp)
        ev["chain_segs"] = len(chain)

        # unique 24+11 matchline label + line
        tok = next((w for w in words if re.match(r"^24\+11/", str(w.get("text", "")))), None)
        all_ml = matchline_bboxes(draw, MATCHLINE_LAYER)
        if tok is None:
            result = R_LABEL_NOT_UNIQUE
            ev["why"] = "no '24+11/...' matchline label token on sheet 5"
            return _emit(gates, result, ev)
        label_xy = (tok["xc"], tok["yc"])
        toks = [w for w in words if re.match(r"^24\+11/", str(w.get("text", "")))]
        if len(toks) != 1:
            result = R_LABEL_NOT_UNIQUE
            ev["why"] = f"{len(toks)} '24+11/...' matchline label tokens -- not unique"
            return _emit(gates, result, ev)
        ev["matchline_label"] = tok["text"]
        if not all_ml:
            result = R_LINE_NOT_UNIQUE
            ev["why"] = "no drawn MATCHLINE line on sheet 5"
            return _emit(gates, result, ev)
        mlb = min(all_ml, key=lambda bb: nearest_gap([label_xy], bb))
        gaps = sorted(nearest_gap([label_xy], bb) for bb in all_ml)
        if not (len(gaps) == 1 or (gaps[1] - gaps[0]) > 25.0):
            result = R_LINE_NOT_UNIQUE
            ev["why"] = "two MATCHLINE lines are near-equidistant from the 24+11 label"
            return _emit(gates, result, ev)
        ev["matchline_bbox"] = [round(c, 1) for c in mlb]

        # chain reaches the matchline?
        eps = dash_endpoints(chain)
        reach = min((nearest_gap([p], mlb) for p in eps), default=None)
        ev["chain_to_matchline_gap_pt"] = round(reach, 2) if reach is not None else None
        if reach is None or reach > MAX_DASH_GAP:
            result = R_STOPS
            ev["why"] = (f"chain nearest endpoint is {ev['chain_to_matchline_gap_pt']} pt from the "
                         f"24+11 matchline (> MAX_DASH_GAP {MAX_DASH_GAP}) -- stops before it")
            return _emit(gates, result, ev)

        # resolve the boundary point (proven law)
        bnd = extend_dash_to_boundary(chain, mlb)
        if bnd is None:
            result = R_NOT_ON_CHAIN
            ev["why"] = ("no terminal chain dash extends to the matchline centerline within the "
                         "dash-gap cap -- no boundary point lies on the chain")
            return _emit(gates, result, ev)
        ev["boundary_point"] = [round(bnd[0], 2), round(bnd[1], 2)]

        # corroborate: ON the matchline line, AND on the route-ladder alignment column
        on_line = _on_line(bnd, mlb)
        ticks, _ = route_ladder_ticks(plan, 5, offset)
        align_gap = min((abs(bnd[0] - t.x) for t in ticks), default=None)
        ev["boundary_on_matchline_line"] = on_line
        ev["boundary_to_alignment_x_gap_pt"] = round(align_gap, 1) if align_gap is not None else None
        if not on_line:
            result = R_NO_SAFE
            ev["why"] = "extended boundary point does not lie on the matchline line bbox"
            return _emit(gates, result, ev)
        if align_gap is None or align_gap > ALIGN_TOL:
            result = R_INTERSECT_AMBIG
            ev["why"] = (f"boundary point x is {ev['boundary_to_alignment_x_gap_pt']} pt from the "
                         f"nearest route-ladder alignment tick (> {ALIGN_TOL}) -- the crossing may "
                         f"be a lateral, not the route; ambiguous")
            return _emit(gates, result, ev)

        # cross-sheet identity (sheet 6) -- deferred if unresolved
        graph = _build_plan_frame_graph(plan, offset)
        tr = translate_between_sheets(graph, 5, 6, 2411.0)
        ev["translate_s5_to_s6_at_2411"] = tr
        ev["cross_sheet"] = "translated" if tr is not None else "deferred (frame-contested)"
        result = R_RESOLVED if tr is not None else R_RESOLVED_S5
    finally:
        plan.close()

    return _emit(gates, result, ev)


def _emit(gates, result, ev) -> int:
    gates.append(("G6 result in allowed enum", result in ALLOWED, result))
    resolved = result in (R_RESOLVED, R_RESOLVED_S5)
    gates.append(("G7 boundary point present iff resolved (real extraction, no invention)",
                  (resolved and ev.get("boundary_point")) or
                  (not resolved and not ev.get("boundary_point")), ev.get("boundary_point")))
    pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
    gates.append(("G8 zero PNG / zero stroke (no render lane)", len(pngs) == 0, {"pngs": pngs}))
    all_pass = all(x for _, x, _ in gates)
    report = {
        "milestone": "OWNER-PACKET-2 -- log53 matchline boundary termination slice (proof only)",
        "verdict": "PASS" if all_pass else "FAIL",
        "target": "log53", "sheet": 5,
        "question": ("does the BORE - LATERAL chain from the bound NEXTLINK HH start terminate at a "
                     "deterministic sheet-5 boundary point on the 24+11 matchline?"),
        "boundary_termination_result": result,
        "boundary_point_source_chain_layers": sorted(
            set(BRENHAM_CONDUIT_LAYERS.values()) | set(BRENHAM_LATERAL_CONDUIT_LAYERS.values())),
        "boundary_point_law": "matchline_join.extend_dash_to_boundary (terminal dash -> matchline centerline)",
        "evidence": ev,
        "no_screenshot_pixels": True,
        "no_render": True,
        "no_invented_coordinates": True,
        "gates": [{"name": n, "pass": bool(x), "detail": d} for n, x, d in gates],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "log53_matchline_boundary_termination_slice.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[log53-term] boundary_termination_result: {result}")
    for k in ("bound_start_symbol", "chain_segs", "matchline_label", "matchline_bbox",
              "chain_to_matchline_gap_pt", "boundary_point", "boundary_on_matchline_line",
              "boundary_to_alignment_x_gap_pt", "cross_sheet"):
        if k in ev:
            print(f"[log53-term]   {k}: {ev[k]}")
    if ev.get("why"):
        print(f"[log53-term]   why: {ev['why'][:200]}")
    for n, x, _ in gates:
        print(f"[log53-term] {'PASS' if x else 'FAIL'}  {n}")
    print(f"[log53-term] VERDICT: {'PASS' if all_pass else 'FAIL'}  (report: {OUT_DIR})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
