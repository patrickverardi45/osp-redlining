r"""M8.14.b.5 Phase 0 -- log51 START-structure identity evidence probe (sheet 8).

Read-only evidence discovery. Answers: does the PDF print enough to identify
log51's start structure (its local 0+00)? Verdict: **NO -- typed pick-card**,
and the negative is banked with EVIDENCE, not doctrine alone:

  * IDENTITY NOT PRINTED. Sheet 8 has ZERO ``=0+00`` reset equations; the only
    ``0+00`` text is log51's own run callout (``STA 0+00 TO STA 2+99 DIR. BORE
    (299') 1-1.25" VACANT HDPE FOR FIBER DROP``), which names no start
    structure; no ``STA 0+00 <structure>`` note exists.
  * THE DRAWN CANDIDATE EXISTS BUT IS METRICALLY AMBIGUOUS. The bore's own
    local ladder (1+00, 2+00 clean ticks + the b.4-bound end pot at 2+99)
    extrapolates 0+00 to a point where TWO separately-labeled structures sit
    CO-LOCATED ~3 pt apart: the AP-154 TERMINAL 6 PORT HH (printed ``STA 3+66
    ... AP-154 SPLICE LOC 35``, parent frame) and an 11"x11"x12" FLOWER POT.
    Metric identity binding is therefore ambiguous BY CONSTRUCTION -- the
    banked log7 wrong-HH trap shape, now pinned with live rivals.

Typed outcome: ``PICK_CARD_WITH_END_ANCHOR`` -- the reviewer pick-card offers
the two co-located candidates; the END stays position-bound (b.4). Named
missing artifact (verbatim, the b.4 banked string): **printed start-structure
identity evidence for log51 local 0+00 on sheet 8**. Named future lane (the A
path, general not one-off): an **origin-conduit topology discriminator** --
trace the drop-bore's own vector path (BORE - PORT / BORE - PATH layers) to
the structure it physically leaves, a drawn relationship, not a metric one.

No stroke, no placement, no engine wiring. Gates pin the negative exactly;
if a future plan edition prints the origin, G1 FAILS LOUDLY and the lane
reopens. Outputs (gitignored): data/outputs/log51_start_evidence_probe/

Run (repo root): $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_log51_start_evidence_probe
"""
from __future__ import annotations

import json
import math
import os
from typing import Dict, List, Sequence, Tuple

from PIL import ImageDraw

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.structure_anchor import REQUIRED, bind_origin_by_parent_station
from truelinev2.extract.structure_position import (
    BRENHAM_STRUCTURE_LAYERS,
    POSITION_BOUND,
    SymbolCluster,
    cluster_symbols,
    find_leaders,
    resolve_structure_position,
)
from truelinev2.extract.tick_path import route_ladder_ticks
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.proof.run_brenham_corpus import EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.proof.station_equation_ownership import extract_reset_origins

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "log51_start_evidence_probe"
SHEET = 8
ORIGIN_TOL = 10.0      # extrapolated-origin -> candidate symbol (probe metric)
BAND = (320.0, 380.0)  # the log51 route y-band (probe-verified)
PICK_CARD = "PICK_CARD_WITH_END_ANCHOR"
LANE_READY = "PRINTED_ORIGIN_AVAILABLE"
MISSING_ARTIFACT = ("printed start-structure identity evidence for log51 "
                    "local 0+00 on sheet 8")
FUTURE_LANE = ("origin-conduit topology discriminator: trace the drop bore's "
               "own vector path (BORE - PORT / BORE - PATH layers) to the "
               "structure it physically leaves -- a drawn relationship, never "
               "a metric one")


# --- pure helpers (offline-testable) ----------------------------------------------------

def extrapolate_origin(frame_points: Sequence[Tuple[float, float, float]]
                       ) -> Tuple[float, float]:
    """Linear extrapolation of the local-frame origin (station 0) from >= 2
    same-frame positioned stations [(ft, x, y), ...]. Probe heuristic ONLY --
    its output may locate candidates, never bind identity."""
    pts = sorted(frame_points)
    (f0, x0, y0), (f1, x1, y1) = pts[0], pts[-1]
    t = (0.0 - f0) / (f1 - f0)
    return (x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)


def project_station(frame_points: Sequence[Tuple[float, float, float]],
                    xy: Tuple[float, float]) -> Tuple[float, float]:
    """(implied station ft, perpendicular offset pt) of a point against the
    local frame's axis (the line through the outermost frame points). The
    along-frame station is the honest probe metric -- a raw Euclidean distance
    to an extrapolated point conflates station error with the known
    label/text-row perpendicular offset (symbols sit ON the route line; tick
    text sits a fixed offset beside it -- observed on sheets 8 and 10)."""
    pts = sorted(frame_points)
    (f0, x0, y0), (f1, x1, y1) = pts[0], pts[-1]
    dx, dy = x1 - x0, y1 - y0
    den = dx * dx + dy * dy
    t = ((xy[0] - x0) * dx + (xy[1] - y0) * dy) / den
    perp = math.hypot(xy[0] - (x0 + t * dx), xy[1] - (y0 + t * dy))
    return (f0 + t * (f1 - f0), perp)


def colocated_candidates(clusters_by_layer: Dict[str, Sequence[SymbolCluster]],
                         frame_points: Sequence[Tuple[float, float, float]],
                         station_tol_ft: float = 10.0,
                         perp_tol_pt: float = 20.0) -> List[dict]:
    """Every structure-symbol cluster whose ALONG-FRAME implied station is at
    the origin (|station| <= tol) within the route corridor (perp offset in
    the text-row band) -- each is a RIVAL; >= 2 proves metric ambiguity."""
    out = []
    for layer, clusters in sorted(clusters_by_layer.items()):
        for c in clusters:
            sta, perp = project_station(frame_points, (c.x, c.y))
            if abs(sta) <= station_tol_ft and perp <= perp_tol_pt:
                out.append({"layer": layer, "x": round(c.x, 1), "y": round(c.y, 1),
                            "implied_station_ft": round(sta, 1),
                            "perp_offset_pt": round(perp, 1)})
    return out


def classify_start_evidence(printed_origin_count: int,
                            colocated: Sequence[dict]) -> dict:
    """Typed Phase 0 outcome. A printed origin reopens the resolver lane; any
    metric-only candidate set (even a single one) stays a pick-card -- identity
    is never bound by extrapolated position."""
    if printed_origin_count > 0:
        return {"outcome": LANE_READY,
                "reason": "a printed =0+00 origin exists; run the b.1/b.2 chain"}
    return {"outcome": PICK_CARD,
            "reason": (f"no printed origin; {len(colocated)} drawn candidate(s) "
                       f"at the extrapolated origin -- metric identity binding "
                       f"is {'ambiguous (>=2 rivals)' if len(colocated) >= 2 else 'forbidden (no printed relationship)'}"),
            "named_missing_artifact": MISSING_ARTIFACT,
            "future_lane": FUTURE_LANE}


def _render_png(plan: PlanPdf, offset: int, end_xy, ticks_band, origin_xy,
                candidates, ap_box, ap_leader) -> str | None:
    xs = [end_xy[0], origin_xy[0]] + [t[1] for t in ticks_band] + [ap_box[0], ap_box[2]]
    ys = [end_xy[1], origin_xy[1]] + [t[2] for t in ticks_band] + [ap_box[1], ap_box[3]]
    rendered = plan.render_clip(SHEET, offset, [min(xs), min(ys), max(xs), max(ys)],
                                zoom=2.5, pad=60.0)
    if rendered is None:
        return None
    img, cx0, cy0 = rendered
    draw = ImageDraw.Draw(img)
    z = 2.5

    def px(p):
        return ((p[0] - cx0) * z, (p[1] - cy0) * z)

    grey, green, orange = (110, 110, 110), (20, 140, 60), (235, 130, 20)
    x, y = px(end_xy)  # b.4-bound end pot: green ring (the proven anchor)
    draw.ellipse([x - 12, y - 12, x + 12, y + 12], outline=(255, 255, 255), width=6)
    draw.ellipse([x - 12, y - 12, x + 12, y + 12], outline=green, width=4)
    for _, tx, ty in ticks_band:  # local ladder ticks
        tx, ty = px((tx, ty))
        draw.ellipse([tx - 7, ty - 7, tx + 7, ty + 7], outline=(220, 25, 25), width=3)
    ox, oy = px(origin_xy)  # extrapolated origin: grey QUESTION ring, dashed feel
    for r in (16, 22):
        draw.ellipse([ox - r, oy - r, ox + r, oy + r], outline=grey, width=2)
    draw.text((ox + 26, oy - 10), "0+00? (2 rivals)", fill=grey)
    for c in candidates:  # the co-located rival structures
        rx, ry = px((c["x"], c["y"]))
        draw.ellipse([rx - 9, ry - 9, rx + 9, ry + 9], outline=orange, width=3)
    (bx0, by0), (bx1, by1) = px((ap_box[0], ap_box[1])), px((ap_box[2], ap_box[3]))
    draw.rectangle([bx0 - 3, by0 - 3, bx1 + 3, by1 + 3], outline=grey, width=3)
    draw.line([px((ap_leader[0], ap_leader[1])), px((ap_leader[2], ap_leader[3]))],
              fill=orange, width=3)
    cap = ("log51 s8 START evidence probe -- NOT A PLACEMENT: green = b.4-bound "
           "end pot 2+99; red = local ladder 1+00/2+00; grey rings = ladder-"
           "extrapolated 0+00 with TWO co-located rival structures (orange: "
           "AP-154 PORT HH + flower pot, 3 pt apart); no printed =0+00 exists "
           "-> reviewer pick-card; identity is never metric-bound")
    draw.rectangle([0, 0, img.width, 30], fill=(255, 255, 255))
    draw.text((8, 8), cap[:230], fill=(20, 20, 20))
    os.makedirs(OUT_DIR, exist_ok=True)
    path = str(OUT_DIR / "log51_s8_start_evidence_probe.png")
    img.save(path)
    return path


def main() -> int:
    corpus_dir, how = resolve_corpus()
    print(f"[m8.14b5p0] corpus dir : {corpus_dir}  ({how})")
    if not os.path.isfile(PDF) or not os.path.isdir(corpus_dir):
        print("[m8.14b5p0] STOP: inputs missing")
        return 2
    corpus = {p.stem: p for p in enumerate_corpus(corpus_dir)}
    if len(corpus) != EXPECTED_COUNT:
        print(f"[m8.14b5p0] STOP: corpus drift ({len(corpus)})")
        return 3
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.png"):
        stale.unlink()

    plan = PlanPdf(PDF)
    ok = True
    try:
        dialect = select_dialect(plan)
        offset = dialect.calibrate(plan, 13)
        bore = load_borelog(str(corpus["bore_log51"]))
        lines = plan.lines(SHEET, offset)

        # G1 identity stays unprinted: zero reset origins; the only 0+00 text is
        # the bore's own run callout; the b.1 binding remains REQUIRED.
        origins = extract_reset_origins(lines, SHEET)
        zero_lines = [ln.strip() for ln in lines if "0+00" in ln]
        start_id = bind_origin_by_parent_station(bore.station_start_ft, origins)
        g1 = (origins == [] and zero_lines == ["STA 0+00 TO STA 2+99"]
              and start_id.result == REQUIRED)
        print(f"[m8.14b5p0] {'PASS' if g1 else 'FAIL'}  G1 identity unprinted: "
              f"origins={len(origins)} zero_lines={zero_lines} "
              f"binding={start_id.result}")
        ok &= g1

        # G2 the local ladder frame is real and extrapolates to a candidate
        end_pos = resolve_structure_position(
            label_text="2+99", structure_class="flower_pot",
            words=plan.words(SHEET, offset), drawings=plan.line_items(SHEET, offset),
            layer_table=BRENHAM_STRUCTURE_LAYERS, context_texts=("FLOWER", "POT"))
        ticks, _ = route_ladder_ticks(plan, SHEET, offset)
        band = sorted([(t.station_ft, t.x, t.y) for t in ticks
                       if BAND[0] < t.y < BAND[1]])
        frame = band + [(bore.station_end_ft, end_pos.symbol_xy[0],
                         end_pos.symbol_xy[1])]
        origin_xy = extrapolate_origin(frame)
        g2 = (end_pos.result == POSITION_BOUND
              and [s for s, _, _ in band] == [100.0, 200.0]
              and 560.0 <= origin_xy[0] <= 600.0)
        print(f"[m8.14b5p0] {'PASS' if g2 else 'FAIL'}  G2 ladder frame: "
              f"band={band} origin~({origin_xy[0]:.1f},{origin_xy[1]:.1f})")
        ok &= g2

        # G3 EXACTLY TWO rival structures co-located at the extrapolated origin
        drawings = plan.line_items(SHEET, offset)
        clusters = {lay: cluster_symbols(drawings, lay)
                    for lay in ("NEXTLINK", "FLOWER POT")}
        rivals = colocated_candidates(clusters, frame)
        g3 = (len(rivals) == 2
              and {r["layer"] for r in rivals} == {"NEXTLINK", "FLOWER POT"})
        print(f"[m8.14b5p0] {'PASS' if g3 else 'FAIL'}  G3 metric ambiguity "
              f"pinned: rivals={rivals}")
        ok &= g3

        # G4 the HH candidate's printed identity exists and is leader-bound
        # (reverse leader: the AP-154 box's leader tip lands on the NEXTLINK
        # cluster) -- the future lane's target relationship, named exactly.
        words = plan.words(SHEET, offset)
        hh = next(r for r in rivals if r["layer"] == "NEXTLINK")
        ap_box = ap_leader = None
        for d in drawings:
            if (d["layer"] != "PORT HH - TEXT"
                    or d["x1"] - d["x0"] < 10 or d["y1"] - d["y0"] < 6):
                continue
            box = (d["x0"], d["y0"], d["x1"], d["y1"])
            inner = [w["text"] for w in words
                     if box[0] <= w["xc"] <= box[2] and box[1] <= w["yc"] <= box[3]]
            if "AP-154" not in inner:
                continue
            for ld in find_leaders(drawings, "PORT HH - TEXT", box):
                if math.hypot(ld[2] - hh["x"], ld[3] - hh["y"]) <= ORIGIN_TOL:
                    ap_box, ap_leader = box, ld
        g4 = ap_box is not None
        print(f"[m8.14b5p0] {'PASS' if g4 else 'FAIL'}  G4 HH candidate is the "
              f"printed AP-154 (leader-bound): box={ap_box}")
        ok &= g4

        # G5 typed outcome banked
        verdict = classify_start_evidence(len(origins), rivals)
        g5 = (verdict["outcome"] == PICK_CARD
              and verdict["named_missing_artifact"] == MISSING_ARTIFACT)
        print(f"[m8.14b5p0] {'PASS' if g5 else 'FAIL'}  G5 typed outcome: "
              f"{verdict['outcome']} -- {verdict['reason']}")
        ok &= g5

        png = _render_png(plan, offset, end_pos.symbol_xy, band, origin_xy,
                          rivals, ap_box, ap_leader) if g4 else None
        pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
        g6 = png is not None and len(pngs) == 1 and "stroke" not in pngs[0]
        print(f"[m8.14b5p0] {'PASS' if g6 else 'FAIL'}  G6 exactly one probe PNG "
              f"(no stroke artifact): {pngs}")
        ok &= g6

        report = {
            "milestone": ("truelinev2 M8.14.b.5 Phase 0 -- log51 start-structure "
                          "identity evidence probe (negative banked with rivals)"),
            "corpus_dir_used": corpus_dir, "corpus_resolution": how,
            "plan_pdf": PDF, "verdict": "PASS" if ok else "FAILURE",
            "honesty": ("read-only probe; extrapolation located candidates but "
                        "binds nothing; two co-located rival structures make "
                        "metric identity binding ambiguous by construction (the "
                        "log7 trap shape, live-pinned); end anchor stays b.4-"
                        "bound; no stroke exists"),
            "identity_evidence": {"reset_origins": len(origins),
                                  "zero_lines": zero_lines,
                                  "binding": start_id.result,
                                  "callout_names_no_start_structure": True},
            "local_frame": {"band_ticks": band,
                            "end_anchor": list(end_pos.symbol_xy),
                            "extrapolated_origin": [round(v, 1) for v in origin_xy]},
            "colocated_rivals": rivals,
            "hh_candidate_printed_identity": {
                "label": "STA 3+66 PLACE 13\"X24\"X24\" TERMINAL 6 PORT AP-154 "
                         "SPLICE LOC 35 (parent frame)",
                "box": list(ap_box) if ap_box else None},
            "typed_outcome": verdict,
            "png": png,
        }
        (OUT_DIR / "log51_start_evidence_probe.json").write_text(
            json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"[m8.14b5p0] verdict: {report['verdict']}")
        print(f"[m8.14b5p0] typed outcome: {verdict['outcome']}")
        print(f"[m8.14b5p0] VISUAL FILE for Patrick: {png}")
        print(f"[m8.14b5p0] report -> {OUT_DIR / 'log51_start_evidence_probe.json'}")
    finally:
        plan.close()
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
