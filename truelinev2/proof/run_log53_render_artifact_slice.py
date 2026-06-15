r"""OWNER-PACKET-2 -- log53 RENDER ARTIFACT slice (contained proof artifact).

Draws the log53 redline on the actual PDF pages so Patrick can VISUALLY inspect whether v2
renders it correctly. log53 ONLY; two SHEET-LOCAL segments (no stroke across the page break):

  sheet 5: NEXTLINK HH start -> 24+11 matchline boundary
  sheet 6: 24+11 matchline boundary -> 26+38 FLOWER POT

All endpoints are RE-DERIVED from source here (resolve_nextlink_hh_callout for the start,
extend_dash_to_boundary for each 24+11 boundary, resolve_structure_position flower_pot for the
end) -- no hardcoded/invented coordinates -- and gated against the previously-proven values. The
stroke FOLLOWS THE DRAWN ROUTE: it is the BORE - LATERAL conduit corridor (down-sampled, anchored
at the two proven endpoints), so every vertex is a real source dash endpoint or a proven anchor.

Red TrueLine stroke only (render.crop.REDLINE_STROKE_RGB), REVIEW-style (dashed). Per Patrick's
doctrine this is a source-backed REVIEW/proof artifact, not broad production output. PNG artifacts
are written under the gitignored data/outputs path and are NOT committed.

Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_log53_render_artifact_slice
"""
from __future__ import annotations

import json
import math
import os

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.conduit_topology import connected_chain, dash_endpoints, symbol_footprint
from truelinev2.extract.matchline_join import extend_dash_to_boundary, matchline_bboxes, nearest_gap
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.structure_position import (
    BRENHAM_CONDUIT_LAYERS,
    BRENHAM_LATERAL_CONDUIT_LAYERS,
    BRENHAM_STRUCTURE_LAYERS,
    POSITION_BOUND,
    resolve_nextlink_hh_callout,
    resolve_structure_position,
)
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.proof.run_brenham_corpus import EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.render.crop import REDLINE_STROKE_RGB, render_redline_stroke

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "log53_render_artifact"
import re
_CONDUIT_LAYERS = set(BRENHAM_CONDUIT_LAYERS.values()) | set(BRENHAM_LATERAL_CONDUIT_LAYERS.values())
# proven sheet-local geometry (the render is gated to match these within tolerance)
PROVEN = {
    "s5_start": (680.3, 441.0), "s5_boundary": (667.43, 84.24),
    "s6_boundary": (667.39, 554.4), "s6_pot": (663.9, 227.0),
}
MATCH_TOL = 4.0   # re-derived endpoints must match the proven values within this


def order_route(start_xy, end_xy, corridor_pts, step=35.0):
    """Build a route polyline start -> MAINLINE-hugging spine -> end, ordered by descending
    y (start is the higher-y anchor). Within each y-band the vertex NEAREST the straight
    start->end spine is chosen, so the route follows the mainline conduit and REJECTS lateral
    /pothole/driveway stubs that veer off the corridor (the OWNER-PACKET-2 sheet-5 jog fix).
    Pure: every vertex is a passed-in real corridor point; no coordinate is invented; the
    proven endpoints are never moved."""
    sx, sy = start_xy
    ex, ey = end_xy

    def spine_x(y):
        if ey == sy:
            return sx
        return sx + (ex - sx) * ((y - sy) / (ey - sy))

    interior = sorted({(round(p[0], 2), round(p[1], 2)) for p in corridor_pts
                       if ey + 2 < p[1] < sy - 2}, key=lambda p: -p[1])
    spine, band, band_top = [], [], None

    def flush():
        if band:  # nearest to the spine; ties -> highest y (deterministic)
            spine.append(min(band, key=lambda p: (abs(p[0] - spine_x(p[1])), -p[1])))

    for p in interior:
        if band_top is None or (band_top - p[1]) < step:
            band_top = band_top if band_top is not None else p[1]
            band.append(p)
        else:
            flush()
            band, band_top = [p], p[1]
    flush()
    return [tuple(start_xy)] + spine + [tuple(end_xy)]


def _corridor_pts(draw, seed_xy, seed_layer, x_center, y_lo, y_hi, half=28.0):
    fp = symbol_footprint(draw, seed_layer, tuple(seed_xy))
    chain = connected_chain([x for x in draw if x.get("layer") in _CONDUIT_LAYERS], fp) if fp else []
    return [p for p in dash_endpoints(chain)
            if abs(p[0] - x_center) <= half and (y_lo - 5) <= p[1] <= (y_hi + 5)]


def _matchline_bbox(words, draw, sta_prefix):
    tok = next((w for w in words if re.match(rf"^{re.escape(sta_prefix)}/", str(w.get("text", "")))), None)
    mls = matchline_bboxes(draw, "MATCHLINE")
    if not tok or not mls:
        return None
    return min(mls, key=lambda bb: nearest_gap([(tok["xc"], tok["yc"])], bb))


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.png"):
        stale.unlink()

    gates = []
    if not os.path.isfile(PDF):
        print("[log53-render] STOP: PDF missing"); return 2
    corpus_dir, _ = resolve_corpus()
    corpus = {p.stem: p for p in enumerate_corpus(corpus_dir)} if os.path.isdir(corpus_dir) else {}
    gates.append(("G1 plan PDF + corpus present",
                  os.path.isfile(PDF) and len(corpus) == EXPECTED_COUNT, len(corpus)))

    plan = PlanPdf(PDF)
    artifacts, endpoints = [], {}
    try:
        dialect = select_dialect(plan)
        offset = dialect.calibrate(plan, 13)

        # ---- sheet 5: re-derive start (NEXTLINK HH) + 24+11 boundary -------------
        w5, d5 = plan.words(5, offset), plan.line_items(5, offset)
        sv = resolve_nextlink_hh_callout(station_sta="21+63", words=w5, drawings=d5,
                                         callout_layer="ANNOTATION", symbol_layer="NEXTLINK")
        s5_start = tuple(sv.symbol_xy) if sv.symbol_xy else None
        ml5 = _matchline_bbox(w5, d5, "24+11")
        fp5 = symbol_footprint(d5, "NEXTLINK", s5_start) if s5_start else None
        chain5 = connected_chain([x for x in d5 if x.get("layer") in _CONDUIT_LAYERS], fp5) if fp5 else []
        s5_bnd = extend_dash_to_boundary(chain5, ml5) if (chain5 and ml5) else None

        # ---- sheet 6: re-derive 26+38 FLOWER POT + 24+11 boundary ---------------
        w6, d6 = plan.words(6, offset), plan.line_items(6, offset)
        pv = resolve_structure_position(label_text="26+38", structure_class="flower_pot",
                                        words=w6, drawings=d6, layer_table=BRENHAM_STRUCTURE_LAYERS,
                                        context_texts=("FLOWER", "POT"))
        s6_pot = tuple(pv.symbol_xy) if (pv.result == POSITION_BOUND and pv.symbol_xy) else None
        ml6 = _matchline_bbox(w6, d6, "24+11")
        fp6 = symbol_footprint(d6, "FLOWER POT", s6_pot) if s6_pot else None
        chain6 = connected_chain([x for x in d6 if x.get("layer") in _CONDUIT_LAYERS], fp6) if fp6 else []
        s6_bnd = extend_dash_to_boundary(chain6, ml6) if (chain6 and ml6) else None

        endpoints = {"s5_start": s5_start, "s5_boundary": s5_bnd,
                     "s6_boundary": s6_bnd, "s6_pot": s6_pot}

        # G2: every endpoint re-derived from source and matches the proven value
        def near(a, key):
            b = PROVEN[key]
            return a is not None and math.hypot(a[0] - b[0], a[1] - b[1]) <= MATCH_TOL
        g2 = all(near(endpoints[k], k) for k in PROVEN)
        gates.append(("G2 endpoints re-derived from source match proven (<= 4 pt)", g2,
                      {k: ([round(c, 2) for c in v] if v else None) for k, v in endpoints.items()}))
        if not g2:
            return _emit(gates, "BLOCKED_NO_SAFE_STROKE_GEOMETRY", artifacts, endpoints)

        # ---- build sheet-local route strokes (follow the drawn conduit corridor) --
        route5 = order_route(s5_start, s5_bnd,
                             _corridor_pts(d5, s5_start, "NEXTLINK", round((s5_start[0] + s5_bnd[0]) / 2, 1),
                                           s5_bnd[1], s5_start[1]))
        route6 = order_route(s6_bnd, s6_pot,
                             _corridor_pts(d6, s6_pot, "FLOWER POT", round((s6_bnd[0] + s6_pot[0]) / 2, 1),
                                           s6_pot[1], s6_bnd[1]))
        gates.append(("G3 sheet-local strokes have >= 2 vertices (no cross-page join)",
                      len(route5) >= 2 and len(route6) >= 2, {"s5_vertices": len(route5), "s6_vertices": len(route6)}))

        p5 = render_redline_stroke(
            plan, "log53", 5, offset, route5, status="REVIEW",
            reason="OWNER-PACKET-2 source-backed: NEXTLINK HH start -> 24+11 matchline boundary",
            out_dir=str(OUT_DIR), mandatory_points=[s5_start, s5_bnd], pad=170.0)
        p6 = render_redline_stroke(
            plan, "log53", 6, offset, route6, status="REVIEW",
            reason="OWNER-PACKET-2 source-backed: 24+11 matchline boundary -> 26+38 FLOWER POT",
            out_dir=str(OUT_DIR), mandatory_points=[s6_bnd, s6_pot], pad=170.0)
        artifacts = [p for p in (p5, p6) if p]
        gates.append(("G4 two sheet-local PNG artifacts rendered (red REVIEW stroke)",
                      p5 is not None and p6 is not None and len(artifacts) == 2, artifacts))
    finally:
        plan.close()

    pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
    g5 = (len(pngs) == 2 and all(n.startswith("log53_") for n in pngs)
          and any("_s5_" in n for n in pngs) and any("_s6_" in n for n in pngs))
    gates.append(("G5 exactly 2 log53 PNGs (s5 + s6); no other logs", g5, pngs))
    gates.append(("G6 canonical red stroke color", REDLINE_STROKE_RGB == (220, 25, 25), list(REDLINE_STROKE_RGB)))
    result = "LOG53_RENDER_ARTIFACT_CREATED" if all(x for _, x, _ in gates) else "BLOCKED_NO_SAFE_STROKE_GEOMETRY"
    return _emit(gates, result, artifacts, endpoints)


def _emit(gates, result, artifacts, endpoints) -> int:
    all_pass = all(x for _, x, _ in gates)
    report = {
        "milestone": "OWNER-PACKET-2 -- log53 render artifact (contained proof; visual inspection)",
        "verdict": "PASS" if all_pass else "FAIL",
        "result": result, "target": "log53 ONLY",
        "endpoints": {k: ([round(c, 2) for c in v] if v else None) for k, v in endpoints.items()},
        "artifacts": artifacts,
        "red_stroke_rgb": list(REDLINE_STROKE_RGB),
        "sheet_local_only": True, "drawn_across_page_break": False,
        "no_invented_coordinates": True, "no_screenshot_pixels": True,
        "gates": [{"name": n, "pass": bool(x), "detail": d} for n, x, d in gates],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "log53_render_artifact.json").write_text(json.dumps(report, indent=2, default=str),
                                                        encoding="utf-8")
    print(f"[log53-render] result: {result}")
    for k, v in endpoints.items():
        print(f"[log53-render]   {k}: {[round(c,2) for c in v] if v else None}")
    for a in artifacts:
        print(f"[log53-render]   ARTIFACT: {a}")
    for n, x, _ in gates:
        print(f"[log53-render] {'PASS' if x else 'FAIL'}  {n}")
    print(f"[log53-render] VERDICT: {'PASS' if all_pass else 'FAIL'}  (report: {OUT_DIR})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
