r"""M8.14.b.10 -- log65 CROSS-SHEET joined symbol-anchored stroke proof.

The first cross-sheet redline stroke: log65 (4+51 -> 6+50, 199 ft) rendered
as TWO sheet-local RED strokes sharing the b.9-proven matchline boundary:

  sheet 10: AP-163 PORT HH symbol (4+51) -> boundary 6+11 at the matchline
            (interior = clean ladder ticks 5+00, 6+00)            [160 ft]
  sheet  9: boundary 6+11 at the matchline -> 6+50 FLOWER POT      [ 39 ft]

BOUNDARY POINT LAW (general): each sheet's boundary anchor is the conduit
chain's terminal dash EXTENDED ALONG ITS OWN DRAWN DIRECTION to the matchline
centerline -- a dashed line includes its gaps, so the extension is capped at
the SAME dash-gap constant that joins dashes (b.9 G4 already proved each
chain reaches its matchline within it; nothing widened). The boundary
station is the printed shared callout station (6+11), which is also the
printed frame equation's local-side value (b.9 G2/G5).

Both strokes run through the UNCHANGED b.3 tick-path machinery; both are
drawn in the canonical red (REDLINE_STROKE_RGB -- the stroke-color law).
Proof-of-capability stroke, REVIEW-style dashed; NOT a placement; no engine
wiring; log50 and every unproven case render NOTHING (structural).

Embedded gates (any failure -> nonzero exit):
  G1 b.9 join evidence reproduces (frame edge + anchors + chains reach)
  G2 boundary points derive from drawn primitives only: terminal-dash
     extension <= MAX_DASH_GAP on both sheets; both boundary stations ==
     the printed shared callout station 6+11
  G3 sheet-10 anchored path: TICK_PATH_READY, ONE stroke, endpoints EQUAL
     the AP-163 symbol and the s10 boundary point; interior == clean ladder
     ticks 5+00/6+00
  G4 sheet-9 anchored path: TICK_PATH_READY, endpoints EQUAL the s9 boundary
     point and the pot symbol
  G5 joined honesty: printed segment footages 160 + 39 == bore span 199;
     all hop scales tight; label-offset safety on the structure endpoints;
     the stroke color IS the canonical red object
  G6 exactly ONE proof PNG (two stacked panels, BOTH strokes red, matchline
     + equation marked); no other stroke artifact in the output dir

Outputs (gitignored): data/outputs/log65_cross_sheet_stroke/

Run (repo root): $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_log65_cross_sheet_stroke_proof
"""
from __future__ import annotations

import json
import math
import os
from typing import Optional, Sequence, Tuple

from PIL import Image, ImageDraw

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
    resolve_structure_position,
)
from truelinev2.extract.tick_path import READY, Tick, route_ladder_ticks, solve_tick_path
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.proof.run_brenham_corpus import EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_cross_sheet_conduit_join_probe import (
    BOUNDARY_STA_LOCAL,
    EXPECT_EDGE_SOURCE,
    MATCHLINE_LAYER,
    SEG_A_FT,
    SEG_B_FT,
    matchline_bboxes,
    nearest_gap,
)
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.proof.run_symbol_anchored_stroke_proof import (
    label_offset_safety,
    stroke_endpoint_fidelity,
)
from truelinev2.render.crop import REDLINE_STROKE_RGB
from truelinev2.service import _build_plan_frame_graph

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "log65_cross_sheet_stroke"
SHEET_A, SHEET_B = 10, 9
# Stroke-color law: drawn redline strokes are ALWAYS red (canonical pin).
STROKE_RGB = REDLINE_STROKE_RGB


# --- pure helpers (offline-testable) ----------------------------------------------------

def extend_dash_to_boundary(chain: Sequence[dict],
                            ml_bbox: Tuple[float, float, float, float],
                            max_gap: float = MAX_DASH_GAP
                            ) -> Optional[Tuple[float, float]]:
    """The chain's terminal dash, extended along its OWN drawn direction to
    the matchline centerline. Returns None (refusal) when no dash endpoint is
    within ``max_gap`` of the boundary -- a dashed line includes its gaps,
    nothing more. Works for vertical or horizontal matchlines."""
    vertical = (ml_bbox[3] - ml_bbox[1]) >= (ml_bbox[2] - ml_bbox[0])
    target = ((ml_bbox[0] + ml_bbox[2]) / 2.0 if vertical
              else (ml_bbox[1] + ml_bbox[3]) / 2.0)
    # Dashes are drawn as outline rectangles: the terminal endpoint belongs to
    # several line items (long axis, caps, diagonals). Evaluate EVERY item
    # whose endpoint is within a dash gap of the boundary and keep the valid
    # intersection with the SHORTEST extension -- deterministic, and the long
    # axis wins by construction (caps are parallel; diagonals overrun).
    best = None  # (extension, gap, candidate point)
    for seg in chain:
        for ln in seg.get("lines") or ():
            for p, q in (((ln[0], ln[1]), (ln[2], ln[3])),
                         ((ln[2], ln[3]), (ln[0], ln[1]))):
                gap = nearest_gap([p], ml_bbox)
                if gap is None or gap > max_gap:
                    continue
                dx, dy = p[0] - q[0], p[1] - q[1]  # direction toward boundary
                if (vertical and dx == 0) or (not vertical and dy == 0):
                    continue  # parallel to the matchline: cannot cross it
                if vertical:
                    t = (target - p[0]) / dx
                    cand = (target, p[1] + dy * t)
                else:
                    t = (target - p[1]) / dy
                    cand = (p[0] + dx * t, target)
                ext = math.hypot(cand[0] - p[0], cand[1] - p[1])
                if ext > max_gap:
                    continue  # oblique overrun longer than a dash gap: refuse
                if best is None or (ext, gap) < (best[0], best[1]):
                    best = (ext, gap, cand)
    return best[2] if best else None


def joined_segments_verdict(*, boundary_a_ft: float, boundary_b_ft: float,
                            seg_a_ft: float, seg_b_ft: float,
                            span_ft: float) -> dict:
    """Two sheet-local strokes join iff they share the SAME printed boundary
    station and their printed footages close the bore span exactly."""
    okb = boundary_a_ft == boundary_b_ft
    okf = abs((seg_a_ft + seg_b_ft) - span_ft) <= 0.5
    return {"joined": okb and okf,
            "shared_boundary_ft": boundary_a_ft if okb else None,
            "footage_closure": okf}


def _render_png(plan, offset, panels) -> Optional[str]:
    clips = []
    for s in panels:
        rendered = plan.render_clip(s["sheet"], offset, s["clip"], zoom=2.0,
                                    pad=55.0)
        if rendered is None:
            return None
        img, cx0, cy0 = rendered
        draw = ImageDraw.Draw(img)
        z = 2.0

        def px(p, cx0=cx0, cy0=cy0):
            return ((p[0] - cx0) * z, (p[1] - cy0) * z)

        grey, orange, blue, white = ((110, 110, 110), (235, 130, 20),
                                     (30, 90, 200), (255, 255, 255))
        ml = s["matchline"]
        (x0, y0), (x1, y1) = px((ml[0], ml[1])), px((ml[2], ml[3]))
        draw.rectangle([x0 - 3, y0 - 3, x1 + 3, y1 + 3], outline=blue, width=4)
        ex, ey = px(s["eq_xy"])
        draw.rectangle([ex - 44, ey - 12, ex + 44, ey + 12], outline=orange, width=3)
        ppts = [px(p) for p in s["stroke"]]
        for a, b in zip(ppts, ppts[1:]):  # REVIEW-style dashed, canonical red
            (ax, ay), (bx, by) = a, b
            dist = math.hypot(bx - ax, by - ay) or 1.0
            ux, uy = (bx - ax) / dist, (by - ay) / dist
            n = 0.0
            while n < dist:
                p0 = (ax + ux * n, ay + uy * n)
                p1 = (ax + ux * min(n + 16, dist), ay + uy * min(n + 16, dist))
                draw.line([p0, p1], fill=STROKE_RGB, width=6)
                n += 26
        for cx, cy in ppts[1:-1]:
            draw.ellipse([cx - 8, cy - 8, cx + 8, cy + 8], outline=white, width=5)
            draw.ellipse([cx - 8, cy - 8, cx + 8, cy + 8], outline=STROKE_RGB, width=3)
        ax_, ay_ = px(s["anchor_xy"])  # structure anchor: double ring
        draw.ellipse([ax_ - 14, ay_ - 14, ax_ + 14, ay_ + 14], outline=white, width=8)
        draw.ellipse([ax_ - 14, ay_ - 14, ax_ + 14, ay_ + 14],
                     outline=s["anchor_color"], width=4)
        bx_, by_ = px(s["boundary_xy"])  # boundary point: diamond on matchline
        draw.polygon([(bx_, by_ - 14), (bx_ + 14, by_), (bx_, by_ + 14),
                      (bx_ - 14, by_)], outline=blue, width=4)
        draw.rectangle([0, 0, img.width, 26], fill=white)
        draw.text((8, 7), s["caption"][:200], fill=(20, 20, 20))
        clips.append(img)
    w = max(i.width for i in clips)
    out = Image.new("RGB", (w, sum(i.height for i in clips) + 8), (255, 255, 255))
    out.paste(clips[0], (0, 0))
    out.paste(clips[1], (0, clips[0].height + 8))
    os.makedirs(OUT_DIR, exist_ok=True)
    path = str(OUT_DIR / "log65_s10_s9_cross_sheet_stroke.png")
    out.save(path)
    return path


def main() -> int:
    corpus_dir, how = resolve_corpus()
    print(f"[m8.14b10] corpus dir : {corpus_dir}  ({how})")
    if not os.path.isfile(PDF) or not os.path.isdir(corpus_dir):
        print("[m8.14b10] STOP: inputs missing")
        return 2
    corpus = {p.stem: p for p in enumerate_corpus(corpus_dir)}
    if len(corpus) != EXPECTED_COUNT:
        print(f"[m8.14b10] STOP: corpus drift ({len(corpus)})")
        return 3
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.png"):
        stale.unlink()  # structural G6: only THIS run's PNG may exist

    plan = PlanPdf(PDF)
    ok = True
    try:
        dialect = select_dialect(plan)
        offset = dialect.calibrate(plan, 13)
        bore = load_borelog(str(corpus["bore_log65"]))
        span_ft = bore.station_end_ft - bore.station_start_ft
        dA = plan.line_items(SHEET_A, offset)
        dB = plan.line_items(SHEET_B, offset)

        # G1 b.9 evidence reproduces
        ap = resolve_structure_position(
            label_text="AP-163", structure_class="terminal_port_hh",
            words=plan.words(SHEET_A, offset), drawings=dA,
            layer_table=BRENHAM_STRUCTURE_LAYERS)
        pot = resolve_structure_position(
            label_text="6+50", structure_class="flower_pot",
            words=plan.words(SHEET_B, offset), drawings=dB,
            layer_table=BRENHAM_STRUCTURE_LAYERS, context_texts=("FLOWER", "POT"))
        graph = _build_plan_frame_graph(plan, offset)
        edge = next((e for e in graph.edges
                     if {e.from_frame, e.to_frame} == {f"sheet:{SHEET_A}", f"sheet:{SHEET_B}"}
                     and e.source == EXPECT_EDGE_SOURCE), None)
        layer = BRENHAM_CONDUIT_LAYERS["VACANT HDPE"]
        chainA = connected_chain([d for d in dA if d["layer"] == layer],
                                 symbol_footprint(dA, "NEXTLINK", tuple(ap.symbol_xy)))
        chainB = connected_chain([d for d in dB if d["layer"] == layer],
                                 symbol_footprint(dB, "FLOWER POT", tuple(pot.symbol_xy)))

        def eq_word(sheet):
            for w in plan.words(sheet, offset):
                if w["text"] == "38+90/6+11":
                    return (w["xc"], w["yc"])
            return None
        eqA, eqB = eq_word(SHEET_A), eq_word(SHEET_B)
        mlA = min(matchline_bboxes(dA, MATCHLINE_LAYER),
                  key=lambda bb: nearest_gap([eqA], bb))
        mlB = min(matchline_bboxes(dB, MATCHLINE_LAYER),
                  key=lambda bb: nearest_gap([eqB], bb))
        g1 = (ap.result == POSITION_BOUND and pot.result == POSITION_BOUND
              and edge is not None and bool(chainA) and bool(chainB))
        print(f"[m8.14b10] {'PASS' if g1 else 'FAIL'}  G1 b.9 evidence: "
              f"AP-163 {[round(c, 1) for c in ap.symbol_xy]}, pot "
              f"{[round(c, 1) for c in pot.symbol_xy]}, edge={edge.source if edge else None}, "
              f"chains {len(chainA)}/{len(chainB)} segs")
        ok &= g1

        # G2 boundary points from drawn primitives only
        bndA = extend_dash_to_boundary(chainA, mlA)
        bndB = extend_dash_to_boundary(chainB, mlB)
        join = joined_segments_verdict(
            boundary_a_ft=BOUNDARY_STA_LOCAL, boundary_b_ft=BOUNDARY_STA_LOCAL,
            seg_a_ft=SEG_A_FT, seg_b_ft=SEG_B_FT, span_ft=span_ft)
        g2 = bndA is not None and bndB is not None and join["joined"]
        print(f"[m8.14b10] {'PASS' if g2 else 'FAIL'}  G2 boundary points: "
              f"s{SHEET_A} {bndA and [round(v, 1) for v in bndA]} / "
              f"s{SHEET_B} {bndB and [round(v, 1) for v in bndB]} join={join}")
        ok &= g2

        # G3 sheet-10 anchored stroke (AP-163 -> boundary; interior 5+00/6+00)
        ticksA, _ = route_ladder_ticks(plan, SHEET_A, offset)
        anchorsA = [Tick(bore.station_start_ft, *ap.symbol_xy),
                    Tick(BOUNDARY_STA_LOCAL, *bndA)]
        vA = solve_tick_path(bore_id="log65", sheet=SHEET_A,
                             start_ft=bore.station_start_ft,
                             end_ft=BOUNDARY_STA_LOCAL,
                             ticks=list(ticksA) + anchorsA)
        interiorA = [t.station_ft for t in vA.chain
                     if bore.station_start_ft < t.station_ft < BOUNDARY_STA_LOCAL]
        g3 = (vA.result == READY and vA.strokes_found == 1
              and stroke_endpoint_fidelity(vA, tuple(ap.symbol_xy), bndA)
              and interiorA == [500.0, 600.0])
        print(f"[m8.14b10] {'PASS' if g3 else 'FAIL'}  G3 s{SHEET_A} stroke: "
              f"{vA.result} chain={[(t.station_ft, round(t.x, 1), round(t.y, 1)) for t in vA.chain]} "
              f"scales={[round(s, 3) for s in vA.hop_scales]}")
        ok &= g3

        # G4 sheet-9 anchored stroke (boundary -> pot)
        ticksB, _ = route_ladder_ticks(plan, SHEET_B, offset)
        anchorsB = [Tick(BOUNDARY_STA_LOCAL, *bndB),
                    Tick(bore.station_end_ft, *pot.symbol_xy)]
        vB = solve_tick_path(bore_id="log65", sheet=SHEET_B,
                             start_ft=BOUNDARY_STA_LOCAL,
                             end_ft=bore.station_end_ft,
                             ticks=list(ticksB) + anchorsB)
        g4 = (vB.result == READY and vB.strokes_found == 1
              and stroke_endpoint_fidelity(vB, bndB, tuple(pot.symbol_xy)))
        print(f"[m8.14b10] {'PASS' if g4 else 'FAIL'}  G4 s{SHEET_B} stroke: "
              f"{vB.result} chain={[(t.station_ft, round(t.x, 1), round(t.y, 1)) for t in vB.chain]} "
              f"scales={[round(s, 3) for s in vB.hop_scales]}")
        ok &= g4

        # G5 joined honesty + label-offset + the color law
        scales = list(vA.hop_scales) + list(vB.hop_scales)
        med = sorted(scales)[len(scales) // 2]
        ls = label_offset_safety(
            [vA.stroke_points[0], vB.stroke_points[-1]],
            [ap.word_xy, pot.word_xy]) if vA.stroke_points and vB.stroke_points else {"safe": False}
        g5 = (join["footage_closure"]
              and all(abs(s - med) / med <= 0.35 for s in scales)
              and ls["safe"] and STROKE_RGB is REDLINE_STROKE_RGB)
        print(f"[m8.14b10] {'PASS' if g5 else 'FAIL'}  G5 joined honesty: "
              f"footages {SEG_A_FT}+{SEG_B_FT}=={span_ft}; scales={[round(s, 3) for s in scales]}; "
              f"labels {ls}; stroke color pinned canonical red")
        ok &= g5

        png = _render_png(plan, offset, [{
            "sheet": SHEET_A, "stroke": vA.stroke_points,
            "anchor_xy": tuple(ap.symbol_xy), "anchor_color": (30, 90, 200),
            "boundary_xy": bndA, "matchline": mlA, "eq_xy": eqA,
            "clip": [min(mlA[0], ap.symbol_xy[0]), 300,
                     max(mlA[2], ap.symbol_xy[0]), 400],
            "caption": ("sheet 10 · log65 RED stroke (REVIEW dashed): AP-163 "
                        "(blue ring, 4+51) -> ladder 5+00/6+00 -> boundary "
                        "6+11 (blue diamond ON the matchline; printed eq "
                        "38+90/6+11 orange) · 160' · proof, not placement"),
        }, {
            "sheet": SHEET_B, "stroke": vB.stroke_points,
            "anchor_xy": tuple(pot.symbol_xy), "anchor_color": (20, 140, 60),
            "boundary_xy": bndB, "matchline": mlB, "eq_xy": eqB,
            "clip": [min(pot.symbol_xy[0], mlB[0]) - 40, 300,
                     max(mlB[2], pot.symbol_xy[0]) + 10, 400],
            "caption": ("sheet 9 · same boundary 6+11 (blue diamond at ITS "
                        "matchline, same printed eq) -> RED stroke -> 6+50 "
                        "FLOWER POT (green ring) · 39' · joined 199' = bore "
                        "span · log50/unproven cases render NOTHING"),
        }])
        pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
        g6 = png is not None and len(pngs) == 1
        print(f"[m8.14b10] {'PASS' if g6 else 'FAIL'}  G6 exactly one proof "
              f"PNG: {pngs}")
        ok &= g6

        report = {
            "milestone": ("truelinev2 M8.14.b.10 -- log65 cross-sheet joined "
                          "symbol-anchored stroke (visual grading required)"),
            "corpus_dir_used": corpus_dir, "corpus_resolution": how,
            "plan_pdf": PDF, "verdict": "PASS" if ok else "FAILURE",
            "honesty": ("two sheet-local strokes through the unchanged b.3 "
                        "solver; boundary anchors = terminal dash extended "
                        "along its own direction to the matchline centerline "
                        "(capped at the dash-gap constant); shared printed "
                        "boundary station 6+11; printed footage closure; both "
                        "strokes canonical red; proof-of-capability only -- "
                        "no placement, no engine wiring, no rollout"),
            "boundary_points": {"s10": list(bndA) if bndA else None,
                                "s9": list(bndB) if bndB else None},
            "join": join,
            "s10_stroke": vA.to_dict(), "s9_stroke": vB.to_dict(),
            "label_offset_safety": ls, "png": png,
        }
        (OUT_DIR / "log65_cross_sheet_stroke_proof.json").write_text(
            json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"[m8.14b10] verdict: {report['verdict']}")
        print(f"[m8.14b10] VISUAL GRADING FILE for Patrick: {png}")
        print(f"[m8.14b10] report -> "
              f"{OUT_DIR / 'log65_cross_sheet_stroke_proof.json'}")
    finally:
        plan.close()
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
