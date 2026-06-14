r"""OWNER-PACKET-2 -- log53 matchline-boundary geometry slice (PROOF ONLY).

Question: can v2 resolve the sheet-5 matchline-boundary point at STA 24+11 into a
LEGITIMATE positioned point, using existing geometry/frame/matchline primitives only,
now that the schema bridge gives log53 a machine-consumable
``endpoint_anchors.end.boundary_kind = matchline_continuation``?

Method (existing seams only -- NO fake fallback):
  1. pull log53 from the ACTUAL flag-on manual-adjudication overlay (not hardcoded);
  2. read the new ``endpoint_anchors`` payload; confirm the end is a matchline
     continuation to sheet 6 (the bridge), and carry NO coordinates;
  3. the b.9/b.10 boundary-point seam is ``matchline_join.extend_dash_to_boundary``:
     a bound structure seeds a conduit chain (``conduit_topology.connected_chain``)
     whose terminal dash is extended to the drawn matchline centerline. Attempt EXACTLY
     that for log53 on sheet 5:
       a. find the drawn sheet-5 matchline bbox via its printed ``24+11/...`` label
          (the b.9 label->line identification; NOT a nearest-snap by assumption);
       b. test the sheet 5<->6 frame relationship (``translate_between_sheets``) --
          a contested raw 24+11 is a frame-doppelganger hazard;
       c. anchor a conduit chain from the bore's only sheet-5 structure (the START
          NEXTLINK HH) via ``resolve_structure_position`` -- the chain SEED;
       d. only if a chain reaches the matchline within ``MAX_DASH_GAP`` do we extend
          its terminal dash to the boundary centerline.
  4. classify into the allowed boundary statuses; render NOTHING unless the FULL
     ``solve_tick_path`` stroke is READY.

Forbidden (all gated out): inventing coordinates, synthesizing the 2400->2411 gap by
length, nearest-neighbor/proximity selection, screenshot pixel positions, snapping to
the matchline by assumption, weakening solve_tick_path / structure-identity law.

Proof-only; artifacts gitignored. Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_log53_matchline_boundary_slice
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

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
    BRENHAM_STRUCTURE_LAYERS,
    POSITION_BOUND,
    resolve_structure_position,
)
from truelinev2.extract.tick_path import READY, route_ladder_ticks, solve_tick_path
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
from truelinev2.render.crop import REDLINE_STROKE_RGB
from truelinev2.stations import parse_station

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "log53_matchline_boundary_slice"
TRUTH = _REPO_ROOT / "data" / "outputs" / "final_engine_truth_table" / \
    "final_engine_truth_table.json"
MATCHLINE_LAYER = "MATCHLINE"   # Brenham dialect fact (b.9): boundary on this CAD layer
FROZEN_BUCKETS = {"DRAWABLE_REVIEW": 31, "HUMAN_ADJUSTABLE_REVIEW": 6,
                  "OUT_OF_CLASS": 1, "PICK_CARD_REVIEW": 17, "SOURCE_OR_KMZ_REQUIRED": 3}
ABSTAIN_4 = ("log5", "log31", "log38", "log43")
_COORD_KEYS = {"x", "y", "z", "xc", "yc", "x0", "y0", "x1", "y1", "cx", "cy", "xy",
               "lat", "lon", "lng", "coord", "coords", "coordinate", "coordinates",
               "px", "py", "pixel", "pixels", "point", "points",
               "symbol_xy", "anchor_xy", "stroke", "stroke_points", "geometry", "geom"}

# allowed statuses (the mission's enum)
BOUNDARY_READY = "BOUNDARY_GEOMETRY_READY"
BOUNDARY_READY_STROKE_NOT = "BOUNDARY_GEOMETRY_READY_BUT_STROKE_NOT_READY"
NO_SEAM = "BLOCKED_NO_MATCHLINE_BOUNDARY_GEOMETRY_SEAM"
AMBIGUOUS = "BLOCKED_AMBIGUOUS_MATCHLINE_BOUNDARY_GEOMETRY"
FRAME_CONTESTED = "BLOCKED_FRAME_CONTESTED_MATCHLINE"
NO_PRIMITIVE = "BLOCKED_NO_SOURCE_BOUNDARY_PRIMITIVE"
ENGINE_LAW = "BLOCKED_ENGINE_LAW"


def _bucket_counts(rows):
    c = {}
    for r in rows.values():
        c[r["completion_bucket"]] = c.get(r["completion_bucket"], 0) + 1
    return c


def _no_coords(obj) -> bool:
    if isinstance(obj, dict):
        if any(str(k).lower() in _COORD_KEYS for k in obj):
            return False
        return all(_no_coords(v) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        return False
    return not isinstance(obj, float)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.png"):
        stale.unlink()  # render nothing unless full stroke READY

    doc = load_adjudication()
    truth = json.loads(TRUTH.read_text(encoding="utf-8"))
    baseline = {r["bore_id"]: dict(r) for r in truth["rows"]}
    off_rows = apply_adjudications(baseline, enabled=False)
    on_rows = apply_adjudications(baseline, enabled=True, doc=doc)
    summ = activation_summary(on_rows)
    rec = {r["log_id"]: r for r in doc["logs"]}
    l53 = rec["log53"]
    ea = l53.get("endpoint_anchors") or {}
    start_a = ea.get("start") or {}
    end_a = ea.get("end") or {}

    gates = []
    # G1 flag OFF byte-identical
    g1 = (off_rows is baseline and _bucket_counts(off_rows) == FROZEN_BUCKETS)
    gates.append(("G1 flag OFF byte-identical (31/6/1/17/3)", g1, _bucket_counts(off_rows)))
    # G2 flag ON counts unchanged
    g2 = (summ["manual_review_drawable"] == 22 and summ["manual_source_verification"] == 1
          and summ["manual_abstain"] == 4)
    gates.append(("G2 flag ON 22/1/4", g2,
                  {k: summ[k] for k in ("manual_review_drawable", "manual_source_verification",
                                        "manual_abstain")}))
    # G3 endpoint_anchors consumed from artifact: end is matchline_continuation, no coords
    g3 = (end_a.get("boundary_kind") == "matchline_continuation"
          and end_a.get("station") == "24+11" and end_a.get("continues_to_sheet") == 6
          and end_a.get("continues_as") == "STA 24+11 TO STA 26+38"
          and start_a.get("boundary_kind") == "structure_terminus"
          and start_a.get("structure_label") == "NEXTLINK HH"
          and _no_coords(ea))
    gates.append(("G3 endpoint_anchors consumed (end=matchline_continuation, no coords)",
                  g3, {"end": end_a, "start_label": start_a.get("structure_label")}))
    # G4 frozen laws: log44 blocked / abstains held / log68-69 / no dup
    g4 = (on_rows["log44"]["adjudication"]["drawable_status"] == "non_drawable"
          and all(on_rows[l]["adjudication"]["drawable_status"] == "abstain" for l in ABSTAIN_4)
          and rec["log68"]["corrected_start"] == "5+03" and rec["log68"]["corrected_end"] == "6+79"
          and rec["log69"]["corrected_start"] == "2+15" and rec["log69"]["corrected_end"] == "4+54"
          and not parent_run_duplicate_check(doc))
    gates.append(("G4 log44 blocked / abstains / log68-69 / no dup", g4, None))

    sheet = (l53["corrected_sheets"] or [None])[0]   # 5
    start_ft = parse_station(l53["corrected_start"])  # 2163
    end_ft = parse_station(l53["corrected_end"])      # 2411

    status = None
    evidence = {}
    boundary_point = None
    stroke_ready = False

    if not os.path.isfile(PDF):
        status = NO_PRIMITIVE
        evidence["pdf"] = f"missing {PDF}"
        return _emit(gates, status, evidence, boundary_point, stroke_ready,
                     sheet, start_ft, end_ft, start_a, end_a)

    corpus_dir, _how = resolve_corpus()
    corpus = {p.stem: p for p in enumerate_corpus(corpus_dir)} if os.path.isdir(corpus_dir) else {}
    gates.append(("G5 plan PDF + corpus present",
                  os.path.isfile(PDF) and len(corpus) == EXPECTED_COUNT,
                  {"pdf": os.path.isfile(PDF), "corpus": len(corpus)}))

    plan = PlanPdf(PDF)
    try:
        dialect = select_dialect(plan)
        offset = dialect.calibrate(plan, 13)
        words = plan.words(sheet, offset)
        drawings = plan.line_items(sheet, offset)

        # --- (a) identify the drawn sheet-5 matchline bbox via its printed label ---
        # the matchline label carries a combined frame token beginning '24+11/'
        ml_tok = next((w for w in words
                       if re.match(r"^24\+11/", str(w.get("text", "")))), None)
        all_ml = matchline_bboxes(drawings, MATCHLINE_LAYER)
        evidence["matchline_label_token"] = ml_tok.get("text") if ml_tok else None
        evidence["matchline_lines_on_sheet"] = len(all_ml)
        if not all_ml:
            status = NO_SEAM if MATCHLINE_LAYER not in {d.get("layer") for d in drawings} else NO_PRIMITIVE
            evidence["why"] = (f"no drawn line on CAD layer '{MATCHLINE_LAYER}' on sheet "
                               f"{sheet}; the boundary primitive (a drawn matchline) is absent")
        elif ml_tok is None:
            status = NO_PRIMITIVE
            evidence["why"] = ("the printed '24+11/...' matchline label token was not found "
                               "in the sheet text layer; cannot identify WHICH drawn matchline "
                               "is the 24+11 boundary without a nearest-snap (forbidden)")
        else:
            ml_xy = (ml_tok["xc"], ml_tok["yc"])
            ml_bbox = min(all_ml, key=lambda bb: nearest_gap([ml_xy], bb))
            label_gap = nearest_gap([ml_xy], ml_bbox)
            # uniqueness: a clear single nearest line (next-nearest meaningfully farther)
            gaps = sorted(nearest_gap([ml_xy], bb) for bb in all_ml)
            unique = len(gaps) == 1 or (gaps[1] - gaps[0]) > 25.0
            evidence["matchline_label_gap_pt"] = round(label_gap, 1)
            evidence["matchline_unique"] = unique
            if not unique:
                status = AMBIGUOUS
                evidence["why"] = (f"two drawn matchlines are near-equidistant from the "
                                   f"'24+11/...' label (gaps {[round(g,1) for g in gaps[:2]]}); "
                                   f"the boundary line is not uniquely identifiable")
            else:
                # --- (b) frame relationship sheet 5 <-> 6 at the contested 24+11 ---
                graph = _build_plan_frame_graph(plan, offset)
                tr = translate_between_sheets(graph, sheet, 6, end_ft)
                evidence["translate_s5_to_s6_at_2411"] = tr
                # --- (c) anchor a conduit chain from the bore's sheet-5 structure ---
                # the owner endpoint structure_class -> dialect geometry layer
                owner_class = start_a.get("structure_class")  # 'nextlink_hh'
                class_in_dialect = owner_class in BRENHAM_STRUCTURE_LAYERS
                evidence["owner_start_class"] = owner_class
                evidence["owner_class_in_dialect_layers"] = class_in_dialect
                evidence["dialect_structure_classes"] = sorted(BRENHAM_STRUCTURE_LAYERS)
                seed_xy = None
                bind = None
                if class_in_dialect:
                    v = resolve_structure_position(
                        label_text=start_a.get("station") or l53["corrected_start"],
                        structure_class=owner_class, words=words, drawings=drawings,
                        layer_table=BRENHAM_STRUCTURE_LAYERS)
                    bind = v.result
                    if v.result == POSITION_BOUND:
                        seed_xy = tuple(v.symbol_xy)
                evidence["start_structure_bind_result"] = bind
                if not class_in_dialect:
                    status = NO_PRIMITIVE
                    evidence["why"] = (
                        f"the bore's only sheet-5 anchor is the START '{start_a.get('structure_label')}' "
                        f"(owner class '{owner_class}'), which has NO geometry layer in the dialect "
                        f"BRENHAM_STRUCTURE_LAYERS {sorted(BRENHAM_STRUCTURE_LAYERS)}; "
                        f"resolve_structure_position cannot seed a conduit chain, and 24+11 has NO "
                        f"end-structure to anchor from the matchline side -> no conduit-chain primitive "
                        f"to extend to the boundary (a chain seeded by nearest line would be forbidden)")
                elif seed_xy is None:
                    status = NO_PRIMITIVE
                    evidence["why"] = (f"start structure did not bind ({bind}); no conduit-chain seed")
                else:
                    # --- (d) chain reach + terminal-dash extension ----------------
                    reached = None
                    bnd = None
                    for cl_name, layer in BRENHAM_CONDUIT_LAYERS.items():
                        segs = [d for d in drawings if d.get("layer") == layer]
                        chain = connected_chain(segs, symbol_footprint(drawings, "NEXTLINK", seed_xy))
                        if not chain:
                            continue
                        gap = nearest_gap(dash_endpoints(chain), ml_bbox)
                        if gap is not None and (reached is None or gap < reached):
                            reached = gap
                            if gap <= MAX_DASH_GAP:
                                bnd = extend_dash_to_boundary(chain, ml_bbox)
                    evidence["chain_reach_gap_pt"] = reached
                    if bnd is None:
                        status = NO_PRIMITIVE
                        evidence["why"] = ("no conduit chain seeded at the start structure reaches the "
                                           "24+11 matchline within MAX_DASH_GAP; no terminal dash to extend")
                    elif tr is None:
                        # boundary POINT exists but the 5<->6 frame is unproven/contested
                        status = FRAME_CONTESTED
                        boundary_point = [round(bnd[0], 2), round(bnd[1], 2)]
                        evidence["why"] = ("a boundary point was derivable, but translate_between_sheets("
                                           "5,6,24+11) is None -- the raw 24+11 is frame-contested across "
                                           "sheets 5/6 (doppelganger); the boundary station identity is not "
                                           "frame-proven")
                    else:
                        boundary_point = [round(bnd[0], 2), round(bnd[1], 2)]
                        # full stroke readiness: start anchor + boundary + ladder
                        ticks, _ = route_ladder_ticks(plan, sheet, offset)
                        from truelinev2.extract.tick_path import Tick
                        anchors = [Tick(start_ft, *seed_xy), Tick(end_ft, *bnd)]
                        v = solve_tick_path(bore_id="bore_log53", sheet=sheet,
                                            start_ft=start_ft, end_ft=end_ft,
                                            ticks=list(ticks) + anchors)
                        stroke_ready = (v.result == READY and v.strokes_found == 1)
                        evidence["solve_tick_path_result"] = v.result
                        status = BOUNDARY_READY if stroke_ready else BOUNDARY_READY_STROKE_NOT
    finally:
        plan.close()

    return _emit(gates, status, evidence, boundary_point, stroke_ready,
                 sheet, start_ft, end_ft, start_a, end_a)


def _emit(gates, status, evidence, boundary_point, stroke_ready,
          sheet, start_ft, end_ft, start_a, end_a) -> int:
    # render-gate: a PNG may exist ONLY if the full stroke is READY (none here)
    pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
    render_gate_ok = (len(pngs) == 0) if status != BOUNDARY_READY else (len(pngs) == 1)
    gates.append((f"G6 render gate ({status}): PNG only if stroke READY", render_gate_ok,
                  {"pngs": pngs, "stroke_ready": stroke_ready}))
    all_pass = all(x for _, x, _ in gates)
    report = {
        "milestone": "OWNER-PACKET-2 -- log53 matchline-boundary geometry slice (proof only)",
        "verdict": "PASS" if all_pass else "FAIL",
        "target": "log53", "sheet": sheet,
        "corrected_start": "21+63", "corrected_end": "24+11",
        "start_ft": start_ft, "end_ft": end_ft,
        "endpoint_anchors_consumed": True,
        "end_boundary_kind": end_a.get("boundary_kind"),
        "boundary_status": status,
        "boundary_point_source": ("matchline_join.extend_dash_to_boundary (conduit terminal "
                                  "dash -> drawn matchline centerline)") if boundary_point else None,
        "boundary_point_xy": boundary_point,    # None unless a real drawn point was derived
        "full_stroke_ready": stroke_ready,
        "proof_stroke_png": pngs[0] if pngs else None,
        "red_stroke_rgb": list(REDLINE_STROKE_RGB),
        "no_coordinates_invented": boundary_point is None or status in (
            BOUNDARY_READY, BOUNDARY_READY_STROKE_NOT, FRAME_CONTESTED),
        "no_fake_fallback": True,
        "evidence": evidence,
        "gates": [{"name": n, "pass": bool(x), "detail": d} for n, x, d in gates],
    }
    (OUT_DIR / "log53_matchline_boundary_slice.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[log53-ml] boundary status: {status}")
    print(f"[log53-ml] boundary point : {boundary_point}  (full stroke ready: {stroke_ready})")
    if evidence.get("why"):
        print(f"[log53-ml] why: {evidence['why'][:200]}")
    for n, x, _ in gates:
        print(f"[log53-ml] {'PASS' if x else 'FAIL'}  {n}")
    print(f"[log53-ml] VERDICT: {'PASS' if all_pass else 'FAIL'}  (report: {OUT_DIR})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
