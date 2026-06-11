r"""M8.14.b.3 -- log7 SYMBOL-ANCHORED stroke proof (visual grading required).

The b.2 chain bound log7's endpoints to DRAWN structure symbols (label box ->
leader -> symbol cluster). This slice feeds those symbol positions to the
UNCHANGED M8.14 tick-path solver as anchor ticks at the bore's start/end
stations: seeds/uniqueness/scale-consistency/branching all reuse the shipped
solver -- no solver edit, no renderer edit, no tail smoothing (the discarded
r3 dash-band approach stays discarded; interior points are clean LADDER ticks
only).

Anchoring law: an anchor tick exists ONLY for a POSITION_BOUND b.2 verdict.
Label centroids are never positions; rival symbols are never anchors.

Embedded gates (any failure -> nonzero exit, no force-green):
  G1 placement + identity + position bindings reproduce (log7 REVIEW /
     REVERSE_ENDPOINT_ANCHOR / sheet 10; start symbol (861.3,354.2); end
     symbol (291.6,355.3))
  G2 anchored tick path: TICK_PATH_READY, exactly ONE stroke; first/last
     stroke points EQUAL the resolved symbol positions; interior points are
     clean ladder ticks strictly inside the span
  G3 rival safety: no stroke VERTEX within RIVAL_MIN_SEP of the 2+22 / 2+72
     rival HH symbols; rival stations never appear in the chain
  G4 label-offset safety: stroke endpoints sit >= LABEL_MIN_SEP from the
     identity LABEL word centers (the stroke ends at symbols, not text)
  G5 scale honesty: hop scales tight + symbol-pair scale corroborates the
     ladder scale (reported exactly)
  G6 exactly ONE proof PNG on disk (dashed REVIEW stroke, endpoint symbol
     markers, greyed rival symbols) -- for Patrick's visual grading

Outputs (gitignored): data/outputs/symbol_anchored_stroke_proof/

Run (repo root): $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_symbol_anchored_stroke_proof
"""
from __future__ import annotations

import json
import math
import os
import re
from typing import Optional, Sequence, Tuple

from PIL import ImageDraw

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.structure_anchor import (
    BOUND,
    bind_end_structure_note,
    bind_origin_by_parent_station,
)
from truelinev2.extract.structure_position import (
    BRENHAM_STRUCTURE_LAYERS,
    POSITION_BOUND,
    StructurePositionVerdict,
    corroborate_pair_scale,
    resolve_structure_position,
)
from truelinev2.extract.station_axis import parse_tick
from truelinev2.extract.tick_path import (
    READY,
    Tick,
    TickPathVerdict,
    route_ladder_ticks,
    solve_tick_path,
)
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.match.collision_gate import collect_all_sheet_equations
from truelinev2.match.engine import run_match
from truelinev2.match.reverse_anchor import ReverseAnchorContext
from truelinev2.match.station_axis_interval import StationAxisContext
from truelinev2.match.transition_classifier import conflict_sheet_pairs
from truelinev2.proof.run_brenham_corpus import EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.proof.station_equation_ownership import extract_reset_origins
from truelinev2.service import _build_plan_frame_graph

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "symbol_anchored_stroke_proof"
SHEET = 10
EXPECT_START_XY = (861.3, 354.2)
EXPECT_END_XY = (291.6, 355.3)
PIN_TOL = 6.0
RIVAL_MIN_SEP = 25.0   # stroke vertices vs rival symbol centers
LABEL_MIN_SEP = 20.0   # stroke endpoints vs identity label WORD centers
_EQ_TOKEN = re.compile(r"\d+\+\d+=0\+00")
_AP_TOKEN = re.compile(r"AP-\d+")


# --- pure helpers (offline-testable) ----------------------------------------------------

def anchor_ticks_from_verdicts(start_v: StructurePositionVerdict,
                               end_v: StructurePositionVerdict,
                               start_ft: float, end_ft: float
                               ) -> Tuple[Optional[Tuple[Tick, Tick]], Optional[str]]:
    """Anchor ticks exist ONLY for POSITION_BOUND verdicts -- any other verdict
    refuses with the named relationship (never anchor to a label or a guess)."""
    for v in (start_v, end_v):
        if v.result != POSITION_BOUND or v.symbol_xy is None:
            return None, (f"endpoint {v.label_text!r} is {v.result}, not "
                          f"{POSITION_BOUND} -- a stroke may not be anchored to "
                          f"an unresolved position; "
                          f"{v.named_missing_relationship or 'no symbol'}")
    return (Tick(start_ft, start_v.symbol_xy[0], start_v.symbol_xy[1]),
            Tick(end_ft, end_v.symbol_xy[0], end_v.symbol_xy[1])), None


def stroke_endpoint_fidelity(verdict: TickPathVerdict,
                             start_xy: Tuple[float, float],
                             end_xy: Tuple[float, float], tol: float = 0.1) -> bool:
    """The trimmed stroke must START and END exactly at the anchor symbols
    (anchor stations equal the span bounds, so interpolation lands ON them)."""
    if verdict.result != READY or not verdict.stroke_points:
        return False
    (sx, sy), (ex, ey) = verdict.stroke_points[0], verdict.stroke_points[-1]
    return (math.hypot(sx - start_xy[0], sy - start_xy[1]) <= tol
            and math.hypot(ex - end_xy[0], ey - end_xy[1]) <= tol)


def rival_vertex_safety(stroke_points: Sequence[Tuple[float, float]],
                        rival_xys: Sequence[Tuple[float, float]],
                        min_sep: float = RIVAL_MIN_SEP) -> dict:
    """No stroke VERTEX may sit at a rival symbol -- rivals are never anchors
    and never interior points. Reports the worst separation exactly."""
    worst = None
    for p in stroke_points:
        for r in rival_xys:
            d = math.hypot(p[0] - r[0], p[1] - r[1])
            if worst is None or d < worst:
                worst = d
    return {"min_vertex_to_rival_pt": (round(worst, 1) if worst is not None else None),
            "min_sep_required": min_sep,
            "safe": worst is None or worst >= min_sep}


def label_offset_safety(endpoints: Sequence[Tuple[float, float]],
                        label_word_xys: Sequence[Tuple[float, float]],
                        min_sep: float = LABEL_MIN_SEP) -> dict:
    """Stroke ENDPOINTS must sit away from the identity label words -- ending a
    stroke at leader-offset text is the exact r3-class failure this lane bans."""
    worst = None
    for p in endpoints:
        for w in label_word_xys:
            d = math.hypot(p[0] - w[0], p[1] - w[1])
            if worst is None or d < worst:
                worst = d
    return {"min_endpoint_to_label_pt": (round(worst, 1) if worst is not None else None),
            "min_sep_required": min_sep,
            "safe": worst is None or worst >= min_sep}


# --- rendering (proof-local; canonical renderer untouched) ------------------------------

def _dashed(draw, p0, p1, color, width: int, dash: float = 16.0, gap: float = 10.0):
    (x0, y0), (x1, y1) = p0, p1
    dist = math.hypot(x1 - x0, y1 - y0) or 1.0
    ux, uy = (x1 - x0) / dist, (y1 - y0) / dist
    n = 0.0
    while n < dist:
        a = (x0 + ux * n, y0 + uy * n)
        b = (x0 + ux * min(n + dash, dist), y0 + uy * min(n + dash, dist))
        draw.line([a, b], fill=color, width=width)
        n += dash + gap


def _render_png(plan: PlanPdf, offset: int, stroke, start_xy, end_xy,
                rival_xys) -> Optional[str]:
    xs = [p[0] for p in stroke] + [r[0] for r in rival_xys]
    ys = [p[1] for p in stroke] + [r[1] for r in rival_xys]
    rendered = plan.render_clip(SHEET, offset, [min(xs), min(ys), max(xs), max(ys)],
                                zoom=2.0, pad=90.0)
    if rendered is None:
        return None
    img, cx0, cy0 = rendered
    draw = ImageDraw.Draw(img)
    z = 2.0

    def px(p):
        return ((p[0] - cx0) * z, (p[1] - cy0) * z)

    red, grey, white = (220, 25, 25), (110, 110, 110), (255, 255, 255)
    for r in rival_xys:  # rival HH symbols: greyed, never selected
        x, y = px(r)
        draw.ellipse([x - 11, y - 11, x + 11, y + 11], outline=grey, width=3)
        draw.line([x - 15, y, x + 15, y], fill=grey, width=2)
    ppts = [px(p) for p in stroke]
    for a, b in zip(ppts, ppts[1:]):  # dashed = REVIEW convention
        _dashed(draw, a, b, red, width=6)
    for cx, cy in ppts[1:-1]:  # interior ladder ticks: small circles
        draw.ellipse([cx - 8, cy - 8, cx + 8, cy + 8], outline=white, width=5)
        draw.ellipse([cx - 8, cy - 8, cx + 8, cy + 8], outline=red, width=3)
    for p, color in ((start_xy, red), (end_xy, (30, 90, 200))):
        x, y = px(p)  # endpoint = DRAWN structure symbol: double ring + cross
        draw.ellipse([x - 14, y - 14, x + 14, y + 14], outline=white, width=8)
        draw.ellipse([x - 14, y - 14, x + 14, y + 14], outline=color, width=4)
        draw.line([x - 20, y, x + 20, y], fill=color, width=3)
        draw.line([x, y - 20, x, y + 20], fill=color, width=3)
    cap = ("log7 · REVIEW (dashed) · SYMBOL-ANCHORED stroke: endpoints = drawn "
           "structure symbols (red ring = 0+55 INSTALLER HH, blue ring = AP-163 "
           "PORT HH), interior = clean route-ladder ticks 1+00..4+00; grey = "
           "rival HH symbols, never selected; labels are never positions")
    draw.rectangle([0, 0, img.width, 30], fill=white)
    draw.text((8, 8), cap[:210], fill=(20, 20, 20))
    os.makedirs(OUT_DIR, exist_ok=True)
    path = str(OUT_DIR / "log7_s10_symbol_anchored_stroke.png")
    img.save(path)
    return path


def main() -> int:
    corpus_dir, how = resolve_corpus()
    print(f"[m8.14b3] corpus dir : {corpus_dir}  ({how})")
    if not os.path.isfile(PDF) or not os.path.isdir(corpus_dir):
        print("[m8.14b3] STOP: inputs missing")
        return 2
    corpus = {p.stem: p for p in enumerate_corpus(corpus_dir)}
    if len(corpus) != EXPECTED_COUNT:
        print(f"[m8.14b3] STOP: corpus drift ({len(corpus)})")
        return 3
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.png"):
        stale.unlink()  # structural G6: only THIS run's PNG may exist

    plan = PlanPdf(PDF)
    ok = True
    try:
        dialect = select_dialect(plan)
        offset = dialect.calibrate(plan, 13)
        bore = load_borelog(str(corpus["bore_log7"]))

        # G1a placement reproduces (REVIEW via M8.5 reverse anchor, sheet 10)
        graph = _build_plan_frame_graph(plan, offset)
        rev_ctx = ReverseAnchorContext(
            graph=graph, conflicts=conflict_sheet_pairs(graph),
            equations_by_sheet=collect_all_sheet_equations(plan, offset))
        axis_sheets = sorted({x for r in bore.sheet_refs
                              for x in (r - 1, r, r + 1) if x >= 1})
        axis_ctx = StationAxisContext(
            ticks_by_sheet={s: tuple(t for t in (parse_tick(w["text"])
                                                 for w in plan.words(s, offset))
                                     if t is not None) for s in axis_sheets},
            callouts=tuple(c for s in axis_sheets
                           for c in dialect.extract_callouts(plan, s, offset)))
        pl = run_match(bore, plan, dialect, offset,
                       reverse_anchor=rev_ctx, station_axis=axis_ctx)

        # G1b identity + position bindings reproduce (b.1 + b.2)
        lines = plan.lines(SHEET, offset)
        origins = extract_reset_origins(lines, SHEET)
        start_id = bind_origin_by_parent_station(bore.station_start_ft, origins)
        end_id = bind_end_structure_note(bore.station_end_ft, lines)
        words = plan.words(SHEET, offset)
        drawings = plan.line_items(SHEET, offset)
        start_label = _EQ_TOKEN.search(
            start_id.origin.source_line.replace(" ", "")).group(0) \
            if start_id.origin else ""
        end_label = (_AP_TOKEN.search(end_id.structure_label).group(0)
                     if end_id.structure_label else "")
        start_pos = resolve_structure_position(
            label_text=start_label, structure_class="installer_hh",
            words=words, drawings=drawings, layer_table=BRENHAM_STRUCTURE_LAYERS)
        end_pos = resolve_structure_position(
            label_text=end_label, structure_class="terminal_port_hh",
            words=words, drawings=drawings, layer_table=BRENHAM_STRUCTURE_LAYERS)

        def _pin(v, p):
            return (v.result == POSITION_BOUND and v.symbol_xy
                    and math.hypot(v.symbol_xy[0] - p[0], v.symbol_xy[1] - p[1]) <= PIN_TOL)

        g1 = (pl.status.value == "REVIEW" and pl.reason == "REVERSE_ENDPOINT_ANCHOR"
              and pl.sheets == [SHEET]
              and start_id.result == BOUND and end_id.result == BOUND
              and {222.0, 272.0} <= set(start_id.rival_parent_stations)
              and _pin(start_pos, EXPECT_START_XY) and _pin(end_pos, EXPECT_END_XY))
        print(f"[m8.14b3] {'PASS' if g1 else 'FAIL'}  G1 bindings reproduce: "
              f"placement={pl.status.value}/{pl.reason} sheets={pl.sheets} "
              f"start_sym={start_pos.symbol_xy} end_sym={end_pos.symbol_xy}")
        ok &= g1

        # G2 symbol-anchored tick path through the UNCHANGED solver
        anchors, refusal = anchor_ticks_from_verdicts(
            start_pos, end_pos, bore.station_start_ft, bore.station_end_ft)
        if anchors is None:
            print(f"[m8.14b3] FAIL  G2 anchor refusal: {refusal}")
            ok = False
            verdict = None
        else:
            ticks, counts = route_ladder_ticks(plan, SHEET, offset)
            verdict = solve_tick_path(
                bore_id=bore.bore_id, sheet=SHEET,
                start_ft=bore.station_start_ft, end_ft=bore.station_end_ft,
                ticks=list(ticks) + list(anchors))
            interior = [t for t in verdict.chain
                        if bore.station_start_ft < t.station_ft < bore.station_end_ft]
            ladder_set = {(t.station_ft, t.x, t.y) for t in ticks}
            g2 = (verdict.result == READY and verdict.strokes_found == 1
                  and stroke_endpoint_fidelity(verdict, start_pos.symbol_xy,
                                               end_pos.symbol_xy)
                  and all((t.station_ft, t.x, t.y) in ladder_set for t in interior))
            print(f"[m8.14b3] {'PASS' if g2 else 'FAIL'}  G2 anchored path: "
                  f"{verdict.result} strokes={verdict.strokes_found} "
                  f"chain={[(t.station_ft, round(t.x, 1), round(t.y, 1)) for t in verdict.chain]} "
                  f"(ladder counts {counts})")
            ok &= g2

        rival_xys = [(621.2, 354.6), (548.4, 354.9)]  # b.2-resolved rival symbols
        if verdict is not None and verdict.stroke_points:
            rs = rival_vertex_safety(verdict.stroke_points, rival_xys)
            g3 = (rs["safe"]
                  and not any(t.station_ft in (222.0, 272.0) for t in verdict.chain))
            print(f"[m8.14b3] {'PASS' if g3 else 'FAIL'}  G3 rival safety: {rs}")
            ok &= g3

            label_xys = [start_pos.word_xy, end_pos.word_xy]
            ls = label_offset_safety([verdict.stroke_points[0],
                                      verdict.stroke_points[-1]], label_xys)
            g4 = ls["safe"]
            print(f"[m8.14b3] {'PASS' if g4 else 'FAIL'}  G4 label-offset safety: {ls}")
            ok &= g4

            med = sorted(verdict.hop_scales)[len(verdict.hop_scales) // 2]
            corr = corroborate_pair_scale(
                start_pos.symbol_xy, end_pos.symbol_xy,
                bore.station_end_ft - bore.station_start_ft, med)
            g5 = corr["consistent"]
            print(f"[m8.14b3] {'PASS' if g5 else 'FAIL'}  G5 scale honesty: "
                  f"hops={[round(s, 3) for s in verdict.hop_scales]} corr={corr}")
            ok &= g5

            png = _render_png(plan, offset, verdict.stroke_points,
                              start_pos.symbol_xy, end_pos.symbol_xy, rival_xys)
        else:
            rs = ls = corr = None
            png = None
            ok = False
        pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
        g6 = png is not None and len(pngs) == 1
        print(f"[m8.14b3] {'PASS' if g6 else 'FAIL'}  G6 exactly one proof PNG: {pngs}")
        ok &= g6

        report = {
            "milestone": ("truelinev2 M8.14.b.3 -- log7 symbol-anchored stroke "
                          "proof (visual grading required)"),
            "corpus_dir_used": corpus_dir, "corpus_resolution": how,
            "plan_pdf": PDF, "verdict": "PASS" if ok else "FAILURE",
            "honesty": ("stroke endpoints = b.2 leader-traced DRAWN structure "
                        "symbols; interior = clean route-ladder ticks through the "
                        "UNCHANGED M8.14 solver; rivals greyed, never selected; "
                        "labels never positions; no solver/renderer/engine change; "
                        "single-bore proof, no rollout"),
            "placement": {"status": pl.status.value, "reason": pl.reason,
                          "sheets": pl.sheets},
            "positions": {"start": start_pos.to_dict(), "end": end_pos.to_dict()},
            "tick_path": verdict.to_dict() if verdict else None,
            "rival_safety": rs, "label_offset_safety": ls,
            "scale_corroboration": corr, "png": png,
        }
        (OUT_DIR / "symbol_anchored_stroke_proof.json").write_text(
            json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"[m8.14b3] verdict: {report['verdict']}")
        print(f"[m8.14b3] VISUAL GRADING FILE for Patrick: {png}")
        print(f"[m8.14b3] report -> {OUT_DIR / 'symbol_anchored_stroke_proof.json'}")
    finally:
        plan.close()
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
