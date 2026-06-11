r"""M8.14.b.2 -- structure symbol POSITION proof (log7; visual grading required).

Resolves the DRAWN symbol positions for log7's identity-bound endpoints via the
label-box -> leader-line -> symbol-cluster chain (extract/structure_position).
Labels are leader-offset; nothing here ever treats a label centroid as a
position. No stroke change -- anchoring the log7 stroke is M8.14.b.3.

Embedded gates (any failure -> nonzero exit, no force-green):
  G1 identity bindings reproduce (M8.14.b.1): start = STA 0+55=0+00 INSTALLER
     HH (rivals 2+22/2+72 not selected); end = 4+51 AP-163 terminal note
  G2 start POSITION_BOUND: unique red INSTALLER-HH symbol at the leader tip,
     probe-pinned near (861.3, 354.2)
  G3 end POSITION_BOUND: unique blue PORT-HH symbol at the leader tip,
     probe-pinned near (291.6, 355.3)
  G4 rival pins: the 2+22=0+00 / 2+72=0+00 installer-HH labels resolve to
     their OWN symbols, each far from log7's start symbol -- the banked
     wrong-HH trap stays structurally unreachable
  G5 ladder-scale corroboration: resolved symbol-pair distance over the bore
     span agrees with the sheet-10 clean-ladder pts/ft scale (re-derived live
     from the shipped tick-path solver, not hardcoded)
  G6 exactly ONE proof PNG on disk showing label boxes, leaders, resolved
     symbol points, and rival symbols (greyed) -- for Patrick's visual grading

Outputs (gitignored): data/outputs/structure_position_proof/

Run (repo root): $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_structure_position_proof
"""
from __future__ import annotations

import json
import math
import os
import re

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
    corroborate_pair_scale,
    resolve_structure_position,
)
from truelinev2.extract.tick_path import READY, route_ladder_ticks, solve_tick_path
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.proof.run_brenham_corpus import EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.proof.station_equation_ownership import extract_reset_origins

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "structure_position_proof"
SHEET = 10
# Probe-pinned expected symbol positions (2026-06-10 sheet-10 vector probe).
EXPECT_START_XY = (861.3, 354.2)
EXPECT_END_XY = (291.6, 355.3)
PIN_TOL = 6.0           # resolved symbol vs probe pin
RIVAL_MIN_SEP = 50.0    # rival installer-HH symbols must sit far from log7's
_EQ_TOKEN = re.compile(r"\d+\+\d+=0\+00")
_AP_TOKEN = re.compile(r"AP-\d+")


def _near(a, b, tol=PIN_TOL) -> bool:
    return a is not None and math.hypot(a[0] - b[0], a[1] - b[1]) <= tol


def _render_proof_png(plan: PlanPdf, offset: int, verdicts: dict,
                      rivals: dict) -> str | None:
    """One PNG: grey label boxes, orange leaders, red/blue resolved symbol
    points, grey rival symbols. Visual-grading artifact only."""
    bound = [v for v in verdicts.values() if v.symbol_xy]
    if not bound:
        return None
    xs, ys = [], []
    for v in bound:
        xs += [v.label_box[0], v.label_box[2], v.symbol_xy[0]]
        ys += [v.label_box[1], v.label_box[3], v.symbol_xy[1]]
    rendered = plan.render_clip(SHEET, offset, [min(xs), min(ys), max(xs), max(ys)],
                                zoom=2.0, pad=70.0)
    if rendered is None:
        return None
    img, cx0, cy0 = rendered
    draw = ImageDraw.Draw(img)
    z = 2.0

    def px(p):
        return ((p[0] - cx0) * z, (p[1] - cy0) * z)

    grey, orange = (110, 110, 110), (235, 130, 20)
    for rv in rivals.values():  # rival symbols: greyed, never-selected
        if rv.symbol_xy:
            x, y = px(rv.symbol_xy)
            draw.ellipse([x - 10, y - 10, x + 10, y + 10], outline=grey, width=3)
            draw.line([x - 14, y, x + 14, y], fill=grey, width=2)
    for key, color in (("start", (220, 25, 25)), ("end", (30, 90, 200))):
        v = verdicts[key]
        b = v.label_box
        (bx0, by0), (bx1, by1) = px((b[0], b[1])), px((b[2], b[3]))
        draw.rectangle([bx0 - 3, by0 - 3, bx1 + 3, by1 + 3], outline=grey, width=3)
        draw.line([px((v.leader[0], v.leader[1])), px((v.leader[2], v.leader[3]))],
                  fill=orange, width=4)
        x, y = px(v.symbol_xy)
        draw.ellipse([x - 12, y - 12, x + 12, y + 12], outline=(255, 255, 255), width=7)
        draw.ellipse([x - 12, y - 12, x + 12, y + 12], outline=color, width=4)
        draw.line([x - 18, y, x + 18, y], fill=color, width=2)
        draw.line([x, y - 18, x, y + 18], fill=color, width=2)
    cap = ("log7 s10 structure POSITIONS: grey box = identity label, orange = its "
           "leader line, red/blue circle = resolved DRAWN symbol (start HH / end "
           "AP-163), grey circles = rival HH symbols (never selected); labels are "
           "never positions")
    draw.rectangle([0, 0, img.width, 30], fill=(255, 255, 255))
    draw.text((8, 8), cap[:200], fill=(20, 20, 20))
    os.makedirs(OUT_DIR, exist_ok=True)
    path = str(OUT_DIR / "log7_s10_structure_positions.png")
    img.save(path)
    return path


def main() -> int:
    corpus_dir, how = resolve_corpus()
    print(f"[m8.14b2] corpus dir : {corpus_dir}  ({how})")
    if not os.path.isfile(PDF) or not os.path.isdir(corpus_dir):
        print("[m8.14b2] STOP: inputs missing")
        return 2
    corpus = {p.stem: p for p in enumerate_corpus(corpus_dir)}
    if len(corpus) != EXPECTED_COUNT:
        print(f"[m8.14b2] STOP: corpus drift ({len(corpus)})")
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
        lines = plan.lines(SHEET, offset)
        origins = extract_reset_origins(lines, SHEET)
        start_id = bind_origin_by_parent_station(bore.station_start_ft, origins)
        end_id = bind_end_structure_note(bore.station_end_ft, lines)

        g1 = (start_id.result == BOUND
              and start_id.origin.source_line == "STA 0+55=0+00"
              and "INSTALLER HH" in (start_id.origin.structure_label or "")
              and {222.0, 272.0} <= set(start_id.rival_parent_stations)
              and end_id.result == BOUND
              and "AP-163" in (end_id.structure_label or ""))
        print(f"[m8.14b2] {'PASS' if g1 else 'FAIL'}  G1 identity bindings "
              f"reproduce: start={start_id.origin.source_line if start_id.origin else None} "
              f"end_note={end_id.note_line}")
        ok &= g1

        words = plan.words(SHEET, offset)
        drawings = plan.line_items(SHEET, offset)
        start_label = _EQ_TOKEN.search(
            start_id.origin.source_line.replace(" ", "")).group(0)
        end_label = _AP_TOKEN.search(end_id.structure_label).group(0)
        verdicts = {
            "start": resolve_structure_position(
                label_text=start_label, structure_class="installer_hh",
                words=words, drawings=drawings,
                layer_table=BRENHAM_STRUCTURE_LAYERS),
            "end": resolve_structure_position(
                label_text=end_label, structure_class="terminal_port_hh",
                words=words, drawings=drawings,
                layer_table=BRENHAM_STRUCTURE_LAYERS),
        }
        for key, expect, gate in (("start", EXPECT_START_XY, "G2"),
                                  ("end", EXPECT_END_XY, "G3")):
            v = verdicts[key]
            g = v.result == POSITION_BOUND and _near(v.symbol_xy, expect)
            print(f"[m8.14b2] {'PASS' if g else 'FAIL'}  {gate} {key} "
                  f"{v.label_text!r}: {v.result} symbol="
                  f"{[round(c, 1) for c in v.symbol_xy] if v.symbol_xy else None} "
                  f"(pin {expect} tol {PIN_TOL})")
            ok &= g

        rivals = {
            raw: resolve_structure_position(
                label_text=raw, structure_class="installer_hh",
                words=words, drawings=drawings,
                layer_table=BRENHAM_STRUCTURE_LAYERS)
            for raw in ("2+22=0+00", "2+72=0+00")
        }
        start_xy = verdicts["start"].symbol_xy
        g4 = all(rv.result == POSITION_BOUND and start_xy is not None
                 and math.hypot(rv.symbol_xy[0] - start_xy[0],
                                rv.symbol_xy[1] - start_xy[1]) >= RIVAL_MIN_SEP
                 for rv in rivals.values())
        for raw, rv in rivals.items():
            sep = (round(math.hypot(rv.symbol_xy[0] - start_xy[0],
                                    rv.symbol_xy[1] - start_xy[1]), 1)
                   if rv.symbol_xy and start_xy else None)
            print(f"[m8.14b2]       rival {raw}: {rv.result} symbol="
                  f"{[round(c, 1) for c in rv.symbol_xy] if rv.symbol_xy else None} "
                  f"sep_from_log7_start={sep}")
        print(f"[m8.14b2] {'PASS' if g4 else 'FAIL'}  G4 rivals resolve to their "
              f"OWN symbols, all >= {RIVAL_MIN_SEP} pt from log7's start")
        ok &= g4

        ticks, _ = route_ladder_ticks(plan, SHEET, offset)
        ladder = solve_tick_path(bore_id="log45_scale_ref", sheet=SHEET,
                                 start_ft=4350.0, end_ft=4489.0, ticks=ticks)
        scale_med = (sorted(ladder.hop_scales)[len(ladder.hop_scales) // 2]
                     if ladder.hop_scales else 0.0)
        corr = (corroborate_pair_scale(start_xy, verdicts["end"].symbol_xy,
                                       bore.station_end_ft - bore.station_start_ft,
                                       scale_med)
                if start_xy and verdicts["end"].symbol_xy else {"consistent": False})
        g5 = ladder.result == READY and corr["consistent"]
        print(f"[m8.14b2] {'PASS' if g5 else 'FAIL'}  G5 ladder-scale "
              f"corroboration: {corr}")
        ok &= g5

        png = _render_proof_png(plan, offset, verdicts, rivals)
        pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
        g6 = png is not None and len(pngs) == 1
        print(f"[m8.14b2] {'PASS' if g6 else 'FAIL'}  G6 exactly one proof PNG: "
              f"{pngs}")
        ok &= g6

        report = {
            "milestone": ("truelinev2 M8.14.b.2 -- structure symbol position "
                          "proof (log7; leader-traced; visual grading required)"),
            "corpus_dir_used": corpus_dir, "corpus_resolution": how,
            "plan_pdf": PDF, "verdict": "PASS" if ok else "FAILURE",
            "honesty": ("positions come from the label box's OWN leader line to "
                        "the drawn symbol cluster, class-color checked, "
                        "uniqueness-mandatory at every hop; label centroids are "
                        "never positions; no stroke change in this slice"),
            "identity": {"start": start_id.origin.to_dict() if start_id.origin else None,
                         "end_note": end_id.note_line,
                         "end_structure": end_id.structure_label},
            "positions": {k: v.to_dict() for k, v in verdicts.items()},
            "rival_pins": {k: v.to_dict() for k, v in rivals.items()},
            "ladder_scale_corroboration": corr,
            "png": png,
        }
        (OUT_DIR / "structure_position_proof.json").write_text(
            json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"[m8.14b2] verdict: {report['verdict']}")
        print(f"[m8.14b2] VISUAL GRADING FILE for Patrick: {png}")
        print(f"[m8.14b2] report -> {OUT_DIR / 'structure_position_proof.json'}")
    finally:
        plan.close()
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
