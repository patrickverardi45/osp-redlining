r"""M8.14.b.7 -- log51 SYMBOL-ANCHORED stroke proof (sheet 8; visual grading).

The second symbol-anchored stroke, drawn from the full b.2->b.6 evidence
chain with the b.3 machinery UNCHANGED:

  START = AP-154 TERMINAL 6 PORT HH symbol. Authority: the b.6 conduit
          topology discriminator (the bore's own drawn VACANT-HDPE chain
          terminates inside the HH footprint, ZERO endpoints in the rival
          pot). Independently corroborated: the b.2 label-box->leader chain
          for the printed ``AP-154`` label resolves the SAME symbol -- two
          separate drawn-evidence paths, one answer (gated, not assumed).
  END   = the b.4-bound 2+99 flower-pot symbol.
  INTERIOR = the sheet-8 clean route ladder (1+00, 2+00) through the
          unchanged M8.14 tick-path solver (uniqueness/scale/branch safety).

log51 is an AUTO placement -> SOLID red stroke (the b.3 render convention).

Embedded gates (any failure -> nonzero exit):
  G1 evidence chain reproduces: placement AUTO_SELECT/[8]; b.4 end bound at
     pin; b.6 discriminator CONDUIT_ORIGIN_BOUND -> ap154_port_hh; b.2
     AP-154 resolution agrees with the conduit winner (<= 1 pt)
  G2 anchored path: TICK_PATH_READY, ONE stroke, endpoints EQUAL the symbol
     anchors, interior == clean ladder ticks
  G3 rival safety: the stroke STARTS on the HH, not the 3-pt-away rival pot
     (binary: start == HH within 0.1, distance to rival pot >= 2.5); the
     2+34 pot stays >= RIVAL_MIN_SEP from every vertex
  G4 label-offset safety: endpoints >= LABEL_MIN_SEP from the AP-154 label
     word and the 2+99 note word (labels are never positions)
  G5 scale honesty: hop scales tight; symbol-pair scale corroborates
  G6 exactly ONE stroke PNG (solid AUTO stroke, anchors ringed, interior
     ticks, rival pots greyed) -- for Patrick's visual grading

Outputs (gitignored): data/outputs/log51_symbol_anchored_stroke/

Run (repo root): $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_log51_symbol_anchored_stroke_proof
"""
from __future__ import annotations

import json
import math
import os

from PIL import ImageDraw

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.structure_position import (
    BRENHAM_STRUCTURE_LAYERS,
    POSITION_BOUND,
    cluster_symbols,
    corroborate_pair_scale,
    resolve_structure_position,
)
from truelinev2.extract.tick_path import READY, route_ladder_ticks, solve_tick_path
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.match.engine import run_match
from truelinev2.proof.run_brenham_corpus import EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_log51_start_evidence_probe import BAND, colocated_candidates
from truelinev2.proof.run_origin_conduit_topology_probe import (
    BRENHAM_CONDUIT_LAYERS,
    ORIGIN_BOUND,
    dash_endpoints,
    discriminate_origin,
    symbol_footprint,
)
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.proof.run_symbol_anchored_stroke_proof import (
    LABEL_MIN_SEP,
    RIVAL_MIN_SEP,
    anchor_ticks_from_verdicts,
    label_offset_safety,
    rival_vertex_safety,
    stroke_endpoint_fidelity,
)

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "log51_symbol_anchored_stroke"
SHEET = 8
EXPECT_START_XY = (577.6, 354.2)   # b.6 conduit winner (AP-154 HH)
EXPECT_END_XY = (149.9, 343.3)     # b.4-bound end pot
RIVAL_START_POT = (574.6, 354.3)   # the 3-pt rival -- never the anchor
RIVAL_234_POT = (244.2, 345.1)     # the b.4 rival pot down the corridor
PIN_TOL = 6.0
START_NOT_RIVAL_MIN = 2.5          # binary start-vs-rival separation floor


def _near(a, b, tol=PIN_TOL) -> bool:
    return a is not None and math.hypot(a[0] - b[0], a[1] - b[1]) <= tol


def _render_png(plan, offset, stroke, start_xy, end_xy) -> str | None:
    xs = [p[0] for p in stroke] + [RIVAL_234_POT[0]]
    ys = [p[1] for p in stroke] + [RIVAL_234_POT[1]]
    rendered = plan.render_clip(SHEET, offset, [min(xs), min(ys), max(xs), max(ys)],
                                zoom=2.5, pad=80.0)
    if rendered is None:
        return None
    img, cx0, cy0 = rendered
    draw = ImageDraw.Draw(img)
    z = 2.5

    def px(p):
        return ((p[0] - cx0) * z, (p[1] - cy0) * z)

    red, grey, white = (220, 25, 25), (110, 110, 110), (255, 255, 255)
    green, orange = (20, 140, 60), (235, 130, 20)
    for r in (RIVAL_START_POT, RIVAL_234_POT):  # rival pots: greyed
        x, y = px(r)
        draw.ellipse([x - 10, y - 10, x + 10, y + 10], outline=grey, width=3)
        draw.line([x - 14, y, x + 14, y], fill=grey, width=2)
    ppts = [px(p) for p in stroke]
    for a, b in zip(ppts, ppts[1:]):  # SOLID = AUTO convention
        draw.line([a, b], fill=red, width=6)
    for cx, cy in ppts[1:-1]:
        draw.ellipse([cx - 8, cy - 8, cx + 8, cy + 8], outline=white, width=5)
        draw.ellipse([cx - 8, cy - 8, cx + 8, cy + 8], outline=red, width=3)
    for p, color in ((start_xy, orange), (end_xy, green)):
        x, y = px(p)
        draw.ellipse([x - 14, y - 14, x + 14, y + 14], outline=white, width=8)
        draw.ellipse([x - 14, y - 14, x + 14, y + 14], outline=color, width=4)
        draw.line([x - 20, y, x + 20, y], fill=color, width=3)
        draw.line([x, y - 20, x, y + 20], fill=color, width=3)
    cap = ("log51 · AUTO (solid) · SYMBOL-ANCHORED stroke: orange ring = start "
           "at the AP-154 PORT HH symbol (b.6 conduit-topology authority + b.2 "
           "leader corroboration), green ring = end at the b.4-bound 2+99 "
           "flower pot, interior = clean ladder 1+00/2+00; grey = rival pots, "
           "never selected; labels are never positions")
    draw.rectangle([0, 0, img.width, 30], fill=white)
    draw.text((8, 8), cap[:230], fill=(20, 20, 20))
    os.makedirs(OUT_DIR, exist_ok=True)
    path = str(OUT_DIR / "log51_s8_symbol_anchored_stroke.png")
    img.save(path)
    return path


def main() -> int:
    corpus_dir, how = resolve_corpus()
    print(f"[m8.14b7] corpus dir : {corpus_dir}  ({how})")
    if not os.path.isfile(PDF) or not os.path.isdir(corpus_dir):
        print("[m8.14b7] STOP: inputs missing")
        return 2
    corpus = {p.stem: p for p in enumerate_corpus(corpus_dir)}
    if len(corpus) != EXPECTED_COUNT:
        print(f"[m8.14b7] STOP: corpus drift ({len(corpus)})")
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
        words = plan.words(SHEET, offset)
        drawings = plan.line_items(SHEET, offset)

        # G1 the whole evidence chain reproduces
        pl = run_match(bore, plan, dialect, offset)
        end_pos = resolve_structure_position(
            label_text="2+99", structure_class="flower_pot",
            words=words, drawings=drawings,
            layer_table=BRENHAM_STRUCTURE_LAYERS, context_texts=("FLOWER", "POT"))
        start_pos = resolve_structure_position(
            label_text="AP-154", structure_class="terminal_port_hh",
            words=words, drawings=drawings,
            layer_table=BRENHAM_STRUCTURE_LAYERS)
        ticks, counts = route_ladder_ticks(plan, SHEET, offset)
        band = sorted([(t.station_ft, t.x, t.y) for t in ticks
                       if BAND[0] < t.y < BAND[1]])
        frame = band + [(bore.station_end_ft, *end_pos.symbol_xy)]
        clusters = {lay: cluster_symbols(drawings, lay)
                    for lay in ("NEXTLINK", "FLOWER POT")}
        rivals = colocated_candidates(clusters, frame)
        hh = next(r for r in rivals if r["layer"] == "NEXTLINK")
        pot = next(r for r in rivals if r["layer"] == "FLOWER POT")
        segs = [d for d in drawings
                if d["layer"] == BRENHAM_CONDUIT_LAYERS["VACANT HDPE"]
                and BAND[0] < d["yc"] < 390 and 80 < d["xc"] < 700]
        disc = discriminate_origin(
            dash_endpoints(segs),
            {"ap154_port_hh": symbol_footprint(drawings, "NEXTLINK",
                                               (hh["x"], hh["y"])),
             "rival_flower_pot": symbol_footprint(drawings, "FLOWER POT",
                                                  (pot["x"], pot["y"]))})
        agree = (start_pos.result == POSITION_BOUND
                 and math.hypot(start_pos.symbol_xy[0] - hh["x"],
                                start_pos.symbol_xy[1] - hh["y"]) <= 1.0)
        g1 = (pl.status.value == "AUTO_SELECT" and pl.sheets == [SHEET]
              and end_pos.result == POSITION_BOUND
              and _near(end_pos.symbol_xy, EXPECT_END_XY)
              and disc["result"] == ORIGIN_BOUND
              and disc["winner"] == "ap154_port_hh"
              and agree and _near(start_pos.symbol_xy, EXPECT_START_XY))
        print(f"[m8.14b7] {'PASS' if g1 else 'FAIL'}  G1 evidence chain: "
              f"placement={pl.status.value}{pl.sheets} "
              f"end={[round(c, 1) for c in end_pos.symbol_xy] if end_pos.symbol_xy else None} "
              f"conduit={disc['winner']} b2_agrees={agree}")
        ok &= g1

        # G2 anchored path through the UNCHANGED b.3 machinery
        anchors, refusal = anchor_ticks_from_verdicts(
            start_pos, end_pos, bore.station_start_ft, bore.station_end_ft)
        if anchors is None:
            print(f"[m8.14b7] FAIL  G2 anchor refusal: {refusal}")
            ok = False
            verdict = None
        else:
            verdict = solve_tick_path(
                bore_id=bore.bore_id, sheet=SHEET,
                start_ft=bore.station_start_ft, end_ft=bore.station_end_ft,
                ticks=list(ticks) + list(anchors))
            ladder_set = {(t.station_ft, t.x, t.y) for t in ticks}
            interior = [t for t in verdict.chain
                        if bore.station_start_ft < t.station_ft < bore.station_end_ft]
            g2 = (verdict.result == READY and verdict.strokes_found == 1
                  and stroke_endpoint_fidelity(verdict, start_pos.symbol_xy,
                                               end_pos.symbol_xy)
                  and [t.station_ft for t in interior] == [100.0, 200.0]
                  and all((t.station_ft, t.x, t.y) in ladder_set for t in interior))
            print(f"[m8.14b7] {'PASS' if g2 else 'FAIL'}  G2 anchored path: "
                  f"{verdict.result} chain="
                  f"{[(t.station_ft, round(t.x, 1), round(t.y, 1)) for t in verdict.chain]} "
                  f"(ladder counts {counts})")
            ok &= g2

        if verdict is not None and verdict.stroke_points:
            sp = verdict.stroke_points[0]
            d_rival = math.hypot(sp[0] - RIVAL_START_POT[0],
                                 sp[1] - RIVAL_START_POT[1])
            rs = rival_vertex_safety(verdict.stroke_points, [RIVAL_234_POT])
            g3 = (math.hypot(sp[0] - start_pos.symbol_xy[0],
                             sp[1] - start_pos.symbol_xy[1]) <= 0.1
                  and d_rival >= START_NOT_RIVAL_MIN and rs["safe"])
            print(f"[m8.14b7] {'PASS' if g3 else 'FAIL'}  G3 rival safety: start "
                  f"on HH (rival-pot dist {round(d_rival, 1)} >= "
                  f"{START_NOT_RIVAL_MIN}); 2+34 pot {rs}")
            ok &= g3

            ls = label_offset_safety(
                [verdict.stroke_points[0], verdict.stroke_points[-1]],
                [start_pos.word_xy, end_pos.word_xy])
            g4 = ls["safe"]
            print(f"[m8.14b7] {'PASS' if g4 else 'FAIL'}  G4 label-offset "
                  f"safety: {ls} (min sep {LABEL_MIN_SEP})")
            ok &= g4

            med = sorted(verdict.hop_scales)[len(verdict.hop_scales) // 2]
            corr = corroborate_pair_scale(
                start_pos.symbol_xy, end_pos.symbol_xy,
                bore.station_end_ft - bore.station_start_ft, med)
            g5 = corr["consistent"]
            print(f"[m8.14b7] {'PASS' if g5 else 'FAIL'}  G5 scale honesty: "
                  f"hops={[round(s, 3) for s in verdict.hop_scales]} corr={corr}")
            ok &= g5

            png = _render_png(plan, offset, verdict.stroke_points,
                              start_pos.symbol_xy, end_pos.symbol_xy)
        else:
            rs = ls = corr = None
            png = None
            ok = False
        pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
        g6 = png is not None and len(pngs) == 1
        print(f"[m8.14b7] {'PASS' if g6 else 'FAIL'}  G6 exactly one stroke PNG: "
              f"{pngs}")
        ok &= g6

        report = {
            "milestone": ("truelinev2 M8.14.b.7 -- log51 symbol-anchored stroke "
                          "proof (visual grading required)"),
            "corpus_dir_used": corpus_dir, "corpus_resolution": how,
            "plan_pdf": PDF, "verdict": "PASS" if ok else "FAILURE",
            "honesty": ("start authority = b.6 conduit topology (drawn "
                        "containment), corroborated by the independent b.2 "
                        "leader chain; end = b.4 binding; interior = clean "
                        "ladder through the unchanged solver; rivals greyed, "
                        "never selected; single-bore proof, no rollout, no "
                        "engine wiring; b.2-b.6 conclusions unaltered"),
            "placement": {"status": pl.status.value, "reason": pl.reason,
                          "sheets": pl.sheets},
            "start": start_pos.to_dict(), "end": end_pos.to_dict(),
            "conduit_discrimination": disc,
            "tick_path": verdict.to_dict() if verdict else None,
            "rival_safety": rs, "label_offset_safety": ls,
            "scale_corroboration": corr, "png": png,
        }
        (OUT_DIR / "log51_symbol_anchored_stroke_proof.json").write_text(
            json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"[m8.14b7] verdict: {report['verdict']}")
        print(f"[m8.14b7] VISUAL GRADING FILE for Patrick: {png}")
        print(f"[m8.14b7] report -> "
              f"{OUT_DIR / 'log51_symbol_anchored_stroke_proof.json'}")
    finally:
        plan.close()
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
