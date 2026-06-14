r"""OWNER-PACKET-2 -- log53 matchline reverse chain-trace slice (PROOF ONLY).

Patrick's question: the FORWARD start-label bind failed (BLOCKED_LOCATOR_NOT_AVAILABLE).
Can the engine instead start from the END / matchline side and walk BACKWARD along
source conduit geometry toward the beginning NEXTLINK HH -- using existing seams?

Method (existing seams only; nothing wired into production):
  1. reproduce the sheet-5 matchline seam identification (the 24+11/4+37/1+92 label ->
     nearest drawn MATCHLINE line, uniqueness-checked) -- the b.9 label->line law;
  2. REVERSE SEED: find conduit dashes (modeled conduit layers) that touch the matchline
     within MAX_DASH_GAP, then keep ONLY those tied to log53's 24+11 ALIGNMENT (within
     MAX_DASH_GAP of the 24+11 matchline label -- the alignment locator). 0 -> NO_SEED;
     >=2 -> AMBIGUOUS_BRANCH; exactly 1 -> a unique source-backed reverse seed;
  3. WALK BACKWARD: connected_chain from that seed over the conduit layers, then take the
     chain endpoint farthest from the matchline as the backward terminus;
  4. compare the backward terminus to log53's START area (the lowest clean route-ladder
     tick -- the bore-start seed region) and to a NEXTLINK symbol footprint there.

Typed result (a refusal is a valid answer; success is never forced):
  REVERSE_CHAIN_REACHES_NEXTLINK_HH_CANDIDATE / ..._REACHES_START_AREA_BUT_NOT_STRUCTURE_BOUND
  / ..._NO_SEED_AT_MATCHLINE / ..._STOPS_BEFORE_START / ..._AMBIGUOUS_BRANCH
  / ..._FRAME_CONTESTED / ..._SOURCE_GEOMETRY_DISCONTINUOUS / ..._BLOCKED_NO_SAFE_TARGET

No production placement, no renderer output, no stroke, no PNG, no dialect wiring, no
invented coordinates, no nearest-snap into a structure. Proof-only; artifacts gitignored.
Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_log53_matchline_reverse_chain_trace_slice
"""
from __future__ import annotations

import json
import math
import os
import re

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.conduit_topology import (
    MAX_DASH_GAP,
    bbox_gap,
    connected_chain,
    dash_endpoints,
    symbol_footprint,
)
from truelinev2.extract.matchline_join import matchline_bboxes, nearest_gap
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.structure_position import BRENHAM_CONDUIT_LAYERS
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

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "log53_matchline_reverse_chain_trace_slice"
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / \
    "final_engine_truth_table.json"
MATCHLINE_LAYER = "MATCHLINE"
NEXTLINK_SYMBOL_LAYER = "NEXTLINK"
FROZEN_BUCKETS = {"DRAWABLE_REVIEW": 31, "HUMAN_ADJUSTABLE_REVIEW": 6,
                  "OUT_OF_CLASS": 1, "PICK_CARD_REVIEW": 17, "SOURCE_OR_KMZ_REQUIRED": 3}
ABSTAIN_4 = ("log5", "log31", "log38", "log43")
START_AREA_TOL = MAX_DASH_GAP   # source-pinned; never widened

R_REACHES_NEXTLINK = "REVERSE_CHAIN_REACHES_NEXTLINK_HH_CANDIDATE"
R_REACHES_START = "REVERSE_CHAIN_REACHES_START_AREA_BUT_NOT_STRUCTURE_BOUND"
R_NO_SEED = "REVERSE_CHAIN_NO_SEED_AT_MATCHLINE"
R_STOPS = "REVERSE_CHAIN_STOPS_BEFORE_START"
R_AMBIG = "REVERSE_CHAIN_AMBIGUOUS_BRANCH"
R_FRAME = "REVERSE_CHAIN_FRAME_CONTESTED"
R_DISCONT = "REVERSE_CHAIN_SOURCE_GEOMETRY_DISCONTINUOUS"
R_NO_TARGET = "REVERSE_CHAIN_BLOCKED_NO_SAFE_TARGET"
ALLOWED = {R_REACHES_NEXTLINK, R_REACHES_START, R_NO_SEED, R_STOPS, R_AMBIG,
           R_FRAME, R_DISCONT, R_NO_TARGET}


def _seg_bbox(d) -> tuple:
    return (d["x0"], d["y0"], d["x1"], d["y1"])


def matchline_crossing_dashes(drawings, ml_bbox, conduit_layers, max_gap=MAX_DASH_GAP):
    """Conduit-layer dashes whose bbox is within ``max_gap`` of the matchline line."""
    mld = {"x0": ml_bbox[0], "y0": ml_bbox[1], "x1": ml_bbox[2], "y1": ml_bbox[3]}
    return [d for d in drawings if d.get("layer") in conduit_layers
            and bbox_gap(d, mld) <= max_gap]


def alignment_seeds(crossing, label_xy, max_gap=MAX_DASH_GAP):
    """Crossing dashes tied to THIS alignment: within ``max_gap`` of the matchline
    label (the printed locator for the 24+11 alignment). Avoids picking another
    bore's crossing -- no nearest-by-default; a dash must be at the labeled crossing."""
    return [d for d in crossing
            if nearest_gap([label_xy], _seg_bbox(d)) <= max_gap]


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.png"):
        stale.unlink()  # no stroke/render lane: a PNG must never exist

    doc = load_adjudication()
    truth = json.loads(TRUTH.read_text(encoding="utf-8"))
    baseline = {r["bore_id"]: dict(r) for r in truth["rows"]}
    off_rows = apply_adjudications(baseline, enabled=False)
    on_rows = apply_adjudications(baseline, enabled=True, doc=doc)
    summ = activation_summary(on_rows)
    rec = {r["log_id"]: r for r in doc["logs"]}
    end_a = (rec["log53"].get("endpoint_anchors") or {}).get("end") or {}

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
                  and summ["manual_abstain"] == 4,
                  {k: summ[k] for k in ("manual_review_drawable", "manual_source_verification",
                                        "manual_abstain")}))
    gates.append(("G3 endpoint_anchors.end consumed (matchline_continuation @ 24+11 -> s6)",
                  end_a.get("boundary_kind") == "matchline_continuation"
                  and end_a.get("station") == "24+11" and end_a.get("continues_to_sheet") == 6, end_a))
    gates.append(("G4 log44 blocked / abstains held / no dup",
                  on_rows["log44"]["adjudication"]["drawable_status"] == "non_drawable"
                  and all(on_rows[l]["adjudication"]["drawable_status"] == "abstain" for l in ABSTAIN_4)
                  and not parent_run_duplicate_check(doc), None))

    result = R_NO_TARGET
    ev = {}
    if not os.path.isfile(PDF):
        gates.append(("G5 plan PDF present", False, f"missing {PDF}"))
        return _emit(gates, result, ev)
    corpus_dir, _ = resolve_corpus()
    corpus = {p.stem: p for p in enumerate_corpus(corpus_dir)} if os.path.isdir(corpus_dir) else {}
    gates.append(("G5 plan PDF + corpus present",
                  os.path.isfile(PDF) and len(corpus) == EXPECTED_COUNT,
                  {"pdf": os.path.isfile(PDF), "corpus": len(corpus)}))

    conduit_layers = set(BRENHAM_CONDUIT_LAYERS.values())
    plan = PlanPdf(PDF)
    try:
        dialect = select_dialect(plan)
        offset = dialect.calibrate(plan, 13)
        words = plan.words(5, offset)
        drawings = plan.line_items(5, offset)

        # (1) matchline seam identification (label -> unique drawn line)
        tok = next((w for w in words if re.match(r"^24\+11/", str(w.get("text", "")))), None)
        all_ml = matchline_bboxes(drawings, MATCHLINE_LAYER)
        if tok is None or not all_ml:
            result = R_NO_SEED
            ev["why"] = "matchline label token or drawn MATCHLINE line not found on sheet 5"
            return _emit(gates, result, ev)
        label_xy = (tok["xc"], tok["yc"])
        ml_bbox = min(all_ml, key=lambda bb: nearest_gap([label_xy], bb))
        gaps = sorted(nearest_gap([label_xy], bb) for bb in all_ml)
        ml_unique = len(gaps) == 1 or (gaps[1] - gaps[0]) > 25.0
        ev["matchline_label"] = tok["text"]
        ev["matchline_unique"] = ml_unique

        # (2) reverse seed search
        crossing = matchline_crossing_dashes(drawings, ml_bbox, conduit_layers)
        seeds = alignment_seeds(crossing, label_xy)
        ev["crossing_dashes_total"] = len(crossing)
        ev["crossing_dash_xc"] = sorted(round(d["xc"], 1) for d in crossing)
        ev["alignment_label_x"] = round(label_xy[0], 1)
        ev["alignment_seeds_at_24+11"] = len(seeds)

        # frame relationship (informational; reverse trace stays on sheet 5)
        graph = _build_plan_frame_graph(plan, offset)
        ev["translate_s5_to_s6_at_2411"] = translate_between_sheets(graph, 5, 6, 2411.0)

        if not ml_unique:
            result = R_AMBIG
            ev["why"] = "the 24+11 matchline line is not uniquely identifiable"
        elif len(seeds) == 0:
            result = R_NO_SEED
            ev["why"] = (
                f"no conduit dash on the modeled conduit layers {sorted(conduit_layers)} "
                f"sits at the 24+11 ALIGNMENT crossing (0 within MAX_DASH_GAP of the "
                f"24+11 label x={round(label_xy[0],1)}). The {len(crossing)} dashes that DO "
                f"touch the matchline are at x={ev['crossing_dash_xc']} -- other bores' "
                f"crossings; tying one to log53 would be a forbidden proximity guess. There "
                f"is no source-backed reverse seed for log53 at the matchline.")
        elif len(seeds) >= 2:
            result = R_AMBIG
            ev["why"] = (f"{len(seeds)} conduit dashes sit at the 24+11 alignment crossing -- "
                         f"the reverse seed is not unique; never tiebroken")
        else:
            # (3) unique seed -> walk backward
            seed_bbox = _seg_bbox(seeds[0])
            conduit_segs = [d for d in drawings if d.get("layer") in conduit_layers]
            chain = connected_chain(conduit_segs, seed_bbox)
            eps = dash_endpoints(chain)
            ev["chain_segments"] = len(chain)
            if len(chain) <= 1 or not eps:
                result = R_DISCONT
                ev["why"] = "the seeded conduit chain has no connected continuation (discontinuous)"
            else:
                far = max(eps, key=lambda p: nearest_gap([p], ml_bbox))
                ticks, _ = route_ladder_ticks(plan, 5, offset)
                start_tick = min(ticks, key=lambda t: t.station_ft) if ticks else None
                if start_tick is None:
                    result = R_NO_TARGET
                    ev["why"] = "no clean route-ladder tick to anchor the start area"
                else:
                    gap_start = math.hypot(far[0] - start_tick.x, far[1] - start_tick.y)
                    ev["backward_terminus"] = [round(far[0], 1), round(far[1], 1)]
                    ev["start_area_tick"] = [start_tick.station_ft, round(start_tick.x, 1),
                                             round(start_tick.y, 1)]
                    ev["gap_to_start_area_pt"] = round(gap_start, 1)
                    if gap_start > START_AREA_TOL:
                        result = R_STOPS
                        ev["why"] = (f"reverse chain terminates {round(gap_start,1)} pt from the "
                                     f"start-area ladder tick (> {START_AREA_TOL}) -- stops before start")
                    else:
                        nl = symbol_footprint(drawings, NEXTLINK_SYMBOL_LAYER, far)
                        result = R_REACHES_NEXTLINK if nl else R_REACHES_START
                        ev["nextlink_symbol_at_terminus"] = bool(nl)
    finally:
        plan.close()

    return _emit(gates, result, ev)


def _emit(gates, result, ev) -> int:
    gates.append(("G6 result in allowed enum", result in ALLOWED, result))
    pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
    gates.append(("G7 zero PNG / zero stroke (no render lane)", len(pngs) == 0, {"pngs": pngs}))
    success = result in (R_REACHES_NEXTLINK, R_REACHES_START)
    gates.append(("G8 no placement/coords emitted unless a real terminus was reached",
                  success or "backward_terminus" not in ev, None))
    all_pass = all(x for _, x, _ in gates)
    report = {
        "milestone": "OWNER-PACKET-2 -- log53 matchline reverse chain-trace slice (proof only)",
        "verdict": "PASS" if all_pass else "FAIL",
        "target": "log53", "sheet": 5,
        "question": ("can a source-backed reverse conduit-chain seed be created at the 24+11 "
                     "matchline and walked backward toward the start NEXTLINK HH?"),
        "reverse_chain_result": result,
        "evidence": ev,
        "no_coordinates_invented": True,
        "no_fallback": True,
        "dialect_wired": False,
        "gates": [{"name": n, "pass": bool(x), "detail": d} for n, x, d in gates],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "log53_matchline_reverse_chain_trace_slice.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[log53-rev] reverse_chain_result: {result}")
    if ev.get("why"):
        print(f"[log53-rev] why: {ev['why'][:200]}")
    for n, x, _ in gates:
        print(f"[log53-rev] {'PASS' if x else 'FAIL'}  {n}")
    print(f"[log53-rev] VERDICT: {'PASS' if all_pass else 'FAIL'}  (report: {OUT_DIR})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
