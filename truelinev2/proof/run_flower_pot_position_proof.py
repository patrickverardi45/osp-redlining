r"""M8.14.b.4 -- log51 END flower-pot structure-position proof (sheet 8).

Extends the b.2 chain to the FLOWER POT class: the printed end identity
``STA 2+99 11"X11"X12" FLOWER POT`` (M8.14.b.1 BOUND) resolves to the DRAWN
flower-pot symbol via its own label box -> leader -> symbol cluster. The
station text ``2+99`` is NOT sheet-unique (a run callout prints it too), so
this is the first use of context disambiguation: the label box must also
contain the FLOWER + POT words. Position binding ONLY -- log51's start stays
the banked STRUCTURE_IDENTITY_BINDING_REQUIRED abstain, so NO stroke is
attempted or rendered (anchoring needs BOTH endpoints; that rule is a gate
here, not a regret).

Embedded gates (any failure -> nonzero exit, no force-green):
  G1 log51 identity bindings reproduce (b.1): end 2+99 FLOWER POT BOUND;
     start REQUIRED (banked abstain, named)
  G2 end position resolves: POSITION_BOUND on the FLOWER POT symbol layer,
     probe-pinned near (149.9, 343.3), black class fill present
  G3 the run-callout ``2+99`` token is never the locator: the chosen label
     word sits in the note box (~(122.9, 307.6)), far from the callout token
     (~(362.9, 284.1)); without context the solver still abstains (b.2
     contract regression-pinned live)
  G4 rival pin: the adjacent ``STA 2+34 FLOWER POT`` note resolves to its OWN
     symbol (~(244.2, 345.1)), >= RIVAL_MIN_SEP from log51's end symbol
  G5 stroke refusal: anchor_ticks_from_verdicts REFUSES log51 (start is not
     POSITION_BOUND) with the named missing relationship -- no stroke PNG may
     exist, structurally
  G6 exactly ONE proof PNG (position evidence only: label box, leader, bound
     symbol, greyed rival, crossed-out callout token) -- for visual grading

Outputs (gitignored): data/outputs/flower_pot_position_proof/

Run (repo root): $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_flower_pot_position_proof
"""
from __future__ import annotations

import json
import math
import os

from PIL import ImageDraw

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.registry import select_dialect
from truelinev2.extract.structure_anchor import (
    BOUND,
    REQUIRED,
    bind_end_structure_note,
    bind_origin_by_parent_station,
)
from truelinev2.extract.structure_position import (
    BRENHAM_STRUCTURE_LAYERS,
    LABEL_WORD_NOT_UNIQUE,
    POSITION_BOUND,
    resolve_structure_position,
)
from truelinev2.ingest.normalize import load_borelog
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.proof.run_brenham_corpus import EXPECTED_COUNT, PDF, enumerate_corpus
from truelinev2.proof.run_reviewer_service_contract import resolve_corpus
from truelinev2.proof.run_symbol_anchored_stroke_proof import anchor_ticks_from_verdicts
from truelinev2.proof.station_equation_ownership import extract_reset_origins

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "flower_pot_position_proof"
SHEET = 8
EXPECT_END_XY = (149.9, 343.3)      # probe-pinned drawn flower-pot symbol
EXPECT_NOTE_WORD_XY = (122.9, 307.6)  # the 2+99 token INSIDE the note box
CALLOUT_WORD_XY = (362.9, 284.1)      # the run-callout 2+99 token (never used)
EXPECT_RIVAL_XY = (244.2, 345.1)      # the 2+34 flower pot's own symbol
PIN_TOL = 6.0
RIVAL_MIN_SEP = 50.0
CONTEXT = ("FLOWER", "POT")


def _near(a, b, tol=PIN_TOL) -> bool:
    return a is not None and math.hypot(a[0] - b[0], a[1] - b[1]) <= tol


def _render_png(plan: PlanPdf, offset: int, v, rival) -> str | None:
    if not v.symbol_xy:
        return None
    xs = [v.label_box[0], v.label_box[2], v.symbol_xy[0], CALLOUT_WORD_XY[0]]
    ys = [v.label_box[1], v.label_box[3], v.symbol_xy[1], CALLOUT_WORD_XY[1]]
    if rival.symbol_xy:
        xs.append(rival.symbol_xy[0])
        ys.append(rival.symbol_xy[1])
    rendered = plan.render_clip(SHEET, offset, [min(xs), min(ys), max(xs), max(ys)],
                                zoom=2.5, pad=70.0)
    if rendered is None:
        return None
    img, cx0, cy0 = rendered
    draw = ImageDraw.Draw(img)
    z = 2.5

    def px(p):
        return ((p[0] - cx0) * z, (p[1] - cy0) * z)

    grey, green, orange = (110, 110, 110), (20, 140, 60), (235, 130, 20)
    if rival.symbol_xy:  # rival 2+34 flower pot: greyed, never selected
        x, y = px(rival.symbol_xy)
        draw.ellipse([x - 11, y - 11, x + 11, y + 11], outline=grey, width=3)
        draw.line([x - 15, y, x + 15, y], fill=grey, width=2)
    # the run-callout 2+99 token: crossed out (never a locator)
    x, y = px(CALLOUT_WORD_XY)
    draw.line([x - 12, y - 12, x + 12, y + 12], fill=grey, width=3)
    draw.line([x - 12, y + 12, x + 12, y - 12], fill=grey, width=3)
    # label box + leader + bound symbol
    b = v.label_box
    (bx0, by0), (bx1, by1) = px((b[0], b[1])), px((b[2], b[3]))
    draw.rectangle([bx0 - 3, by0 - 3, bx1 + 3, by1 + 3], outline=grey, width=3)
    draw.line([px((v.leader[0], v.leader[1])), px((v.leader[2], v.leader[3]))],
              fill=orange, width=4)
    x, y = px(v.symbol_xy)
    draw.ellipse([x - 13, y - 13, x + 13, y + 13], outline=(255, 255, 255), width=7)
    draw.ellipse([x - 13, y - 13, x + 13, y + 13], outline=green, width=4)
    draw.line([x - 19, y, x + 19, y], fill=green, width=3)
    draw.line([x, y - 19, x, y + 19], fill=green, width=3)
    cap = ("log51 s8 END position: grey box = printed STA 2+99 FLOWER POT note, "
           "orange = its leader, green ring = resolved DRAWN flower-pot symbol; "
           "grey circle = rival 2+34 flower pot (never selected); grey X = the "
           "run-callout 2+99 token (never a locator); NO stroke -- start identity "
           "still unbound (banked abstain)")
    draw.rectangle([0, 0, img.width, 30], fill=(255, 255, 255))
    draw.text((8, 8), cap[:220], fill=(20, 20, 20))
    os.makedirs(OUT_DIR, exist_ok=True)
    path = str(OUT_DIR / "log51_s8_flower_pot_position.png")
    img.save(path)
    return path


def main() -> int:
    corpus_dir, how = resolve_corpus()
    print(f"[m8.14b4] corpus dir : {corpus_dir}  ({how})")
    if not os.path.isfile(PDF) or not os.path.isdir(corpus_dir):
        print("[m8.14b4] STOP: inputs missing")
        return 2
    corpus = {p.stem: p for p in enumerate_corpus(corpus_dir)}
    if len(corpus) != EXPECTED_COUNT:
        print(f"[m8.14b4] STOP: corpus drift ({len(corpus)})")
        return 3
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.png"):
        stale.unlink()  # structural G6: only THIS run's PNG may exist

    plan = PlanPdf(PDF)
    ok = True
    try:
        dialect = select_dialect(plan)
        offset = dialect.calibrate(plan, 13)
        bore = load_borelog(str(corpus["bore_log51"]))
        lines = plan.lines(SHEET, offset)
        origins = extract_reset_origins(lines, SHEET)
        start_id = bind_origin_by_parent_station(bore.station_start_ft, origins)
        end_id = bind_end_structure_note(bore.station_end_ft, lines)
        g1 = (end_id.result == BOUND
              and "FLOWER POT" in (end_id.structure_label or "").upper()
              and start_id.result == REQUIRED)
        print(f"[m8.14b4] {'PASS' if g1 else 'FAIL'}  G1 identity reproduces: "
              f"end={end_id.result} ({end_id.structure_label!r}) "
              f"start={start_id.result}")
        ok &= g1

        words = plan.words(SHEET, offset)
        drawings = plan.line_items(SHEET, offset)
        end_pos = resolve_structure_position(
            label_text=end_id.end_station, structure_class="flower_pot",
            words=words, drawings=drawings,
            layer_table=BRENHAM_STRUCTURE_LAYERS, context_texts=CONTEXT)
        g2 = (end_pos.result == POSITION_BOUND
              and _near(end_pos.symbol_xy, EXPECT_END_XY)
              and any(f == (0.0, 0.0, 0.0)
                      for f in [tuple(f) for f in
                                end_pos.detail.get("fills_found", [])]))
        print(f"[m8.14b4] {'PASS' if g2 else 'FAIL'}  G2 end position: "
              f"{end_pos.result} symbol="
              f"{[round(c, 1) for c in end_pos.symbol_xy] if end_pos.symbol_xy else None} "
              f"(pin {EXPECT_END_XY}) fills={end_pos.detail.get('fills_found')}")
        ok &= g2

        no_ctx = resolve_structure_position(
            label_text=end_id.end_station, structure_class="flower_pot",
            words=words, drawings=drawings,
            layer_table=BRENHAM_STRUCTURE_LAYERS)
        g3 = (_near(end_pos.word_xy, EXPECT_NOTE_WORD_XY)
              and not _near(end_pos.word_xy, CALLOUT_WORD_XY, tol=100.0)
              and no_ctx.result == LABEL_WORD_NOT_UNIQUE)
        print(f"[m8.14b4] {'PASS' if g3 else 'FAIL'}  G3 callout token never the "
              f"locator: word_xy={end_pos.word_xy} (note pin {EXPECT_NOTE_WORD_XY}; "
              f"callout {CALLOUT_WORD_XY} far); no-context verdict={no_ctx.result}")
        ok &= g3

        rival = resolve_structure_position(
            label_text="2+34", structure_class="flower_pot",
            words=words, drawings=drawings,
            layer_table=BRENHAM_STRUCTURE_LAYERS, context_texts=CONTEXT)
        sep = (math.hypot(rival.symbol_xy[0] - end_pos.symbol_xy[0],
                          rival.symbol_xy[1] - end_pos.symbol_xy[1])
               if rival.symbol_xy and end_pos.symbol_xy else 0.0)
        g4 = (rival.result == POSITION_BOUND
              and _near(rival.symbol_xy, EXPECT_RIVAL_XY)
              and sep >= RIVAL_MIN_SEP)
        print(f"[m8.14b4] {'PASS' if g4 else 'FAIL'}  G4 rival 2+34 binds its OWN "
              f"symbol {[round(c, 1) for c in rival.symbol_xy] if rival.symbol_xy else None} "
              f"sep={round(sep, 1)} (>= {RIVAL_MIN_SEP})")
        ok &= g4

        # G5 stroke refusal: start has no position -> anchoring REFUSES; the
        # named missing artifact is the unprinted start-structure identity.
        start_pos_unavailable = resolve_structure_position(
            label_text="__NO_PRINTED_START_IDENTITY__", structure_class="flower_pot",
            words=words, drawings=drawings,
            layer_table=BRENHAM_STRUCTURE_LAYERS)
        anchors, refusal = anchor_ticks_from_verdicts(
            start_pos_unavailable, end_pos,
            bore.station_start_ft, bore.station_end_ft)
        g5 = anchors is None and refusal is not None and "may not be anchored" in refusal
        print(f"[m8.14b4] {'PASS' if g5 else 'FAIL'}  G5 stroke refusal (start "
              f"unbound): {refusal[:140] if refusal else None}")
        ok &= g5

        png = _render_png(plan, offset, end_pos, rival)
        pngs = sorted(p.name for p in OUT_DIR.glob("*.png"))
        g6 = (png is not None and len(pngs) == 1
              and "stroke" not in pngs[0])  # position evidence only, structurally
        print(f"[m8.14b4] {'PASS' if g6 else 'FAIL'}  G6 exactly one position PNG "
              f"(no stroke artifact): {pngs}")
        ok &= g6

        report = {
            "milestone": ("truelinev2 M8.14.b.4 -- log51 end flower-pot position "
                          "proof (sheet 8; visual grading required)"),
            "corpus_dir_used": corpus_dir, "corpus_resolution": how,
            "plan_pdf": PDF, "verdict": "PASS" if ok else "FAILURE",
            "honesty": ("END position only: printed note -> label box (context-"
                        "disambiguated FLOWER+POT) -> leader -> drawn symbol, "
                        "uniqueness-mandatory; the run-callout 2+99 token is "
                        "never a locator; log51's START stays the banked "
                        "STRUCTURE_IDENTITY_BINDING_REQUIRED abstain -- no "
                        "stroke exists or may exist until it binds; the named "
                        "missing artifact is printed start-structure identity "
                        "evidence for log51's local 0+00 on sheet 8"),
            "identity": {"end_note": end_id.note_line,
                         "end_structure": end_id.structure_label,
                         "start_named": start_id.named_missing_relationship},
            "end_position": end_pos.to_dict(),
            "no_context_regression": no_ctx.to_dict(),
            "rival_pin": rival.to_dict(),
            "stroke_refusal": refusal,
            "png": png,
        }
        (OUT_DIR / "flower_pot_position_proof.json").write_text(
            json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"[m8.14b4] verdict: {report['verdict']}")
        print(f"[m8.14b4] VISUAL GRADING FILE for Patrick: {png}")
        print(f"[m8.14b4] report -> {OUT_DIR / 'flower_pot_position_proof.json'}")
    finally:
        plan.close()
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
