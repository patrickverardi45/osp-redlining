r"""LOG61 / LOG48 / LOG70 VISUAL REVIEW PACK builder (read-only; renders NO redline; investigation only).

Builds annotated review PNGs for owner viewing:
  1. log61_correct_sheet5_ap137.png      -- sheet 5 cul-de-sac, START 2+43 HH + AP-137 LEFT + matchline + 4+37
  2. log61_correct_sheet6_4_50.png       -- sheet 6, 4+37->4+50 (13') + 4+50 FLOWER POT terminus
  3. log61_wrong_ap138_side.png          -- AP-138 RIGHT branch + 2+01 FLOWER POT (WRONG side)
  4. log61_review_contact_sheet.png      -- 1+2+3 combined
  5. log48_review_contact_sheet.png      -- the COMMITTED sheet10+sheet12 red strokes (Woodson / 5+07)
  6. log70_review_contact_sheet.png      -- the COMMITTED sheet17+sheet20 red strokes (4+54 / Eledra / 2+15)

Diagnostic circles/arrows/text use HELPER colors; the only RED is the already-committed redline strokes
(reused as-is from the assembly-sweep output). No stroke placed, no census/corpus change. Output gitignored.

Run: $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_log61_review_pack
"""
from __future__ import annotations
import os
from PIL import Image, ImageDraw, ImageFont
from truelinev2.config import _REPO_ROOT
from truelinev2.extract.registry import select_dialect
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.proof.run_brenham_corpus import PDF

OUT = _REPO_ROOT / "data" / "outputs" / "log61_review_pack"
SWEEP = _REPO_ROOT / "data" / "outputs" / "callout_route_assembly_sweep"
GREEN, LIME, ORANGE, CYAN, MAGENTA = (0, 170, 60), (80, 210, 40), (255, 140, 0), (0, 175, 220), (210, 0, 170)


def font(sz, bold=True):
    for name in (("arialbd.ttf", "arial.ttf") if bold else ("arial.ttf",)):
        for p in (rf"C:\Windows\Fonts\{name}", name):
            try:
                return ImageFont.truetype(p, sz)
            except Exception:
                pass
    return ImageFont.load_default()


def _text_box(d, xy, text, f, fill=(255, 255, 255), bg=(0, 0, 0)):
    x, y = xy
    try:
        b = d.textbbox((x, y), text, font=f)
    except Exception:
        b = (x, y, x + 8 * len(text), y + 16)
    d.rectangle((b[0] - 5, b[1] - 3, b[2] + 5, b[3] + 3), fill=bg)
    d.text((x, y), text, font=f, fill=fill)
    return b[3] + 6


def annotated(plan, off, sheet, specs, zoom=2.4, pad=46):
    """specs: list of (query, label, color). Search each, union their bboxes, clip, draw circles + labels."""
    boxes, found = [], []
    for q, label, color in specs:
        hits = plan.search(sheet, off, q)
        if hits:
            boxes.append(hits[0])
            found.append((hits[0], label, color))
    if not boxes:
        return None
    ux0 = min(b[0] for b in boxes); uy0 = min(b[1] for b in boxes)
    ux1 = max(b[2] for b in boxes); uy1 = max(b[3] for b in boxes)
    res = plan.render_clip(sheet, off, [ux0, uy0, ux1, uy1], zoom=zoom, pad=pad)
    if not res:
        return None
    img, ox, oy = res
    img = img.convert("RGB")
    d = ImageDraw.Draw(img)
    f = font(20)
    # legend stack (top-left) keeps labels readable regardless of where the token sits
    ly = 8
    for (bx, label, color) in found:
        cx0, cy0 = (bx[0] - ox) * zoom, (bx[1] - oy) * zoom
        cx1, cy1 = (bx[2] - ox) * zoom, (bx[3] - oy) * zoom
        m = 12
        d.ellipse((cx0 - m, cy0 - m, cx1 + m, cy1 + m), outline=color, width=5)
        # connector dot
        d.ellipse(((cx0 + cx1) / 2 - 4, (cy0 + cy1) / 2 - 4, (cx0 + cx1) / 2 + 4, (cy0 + cy1) / 2 + 4), fill=color)
        d.rectangle((6, ly - 3, 18, ly + 15), fill=color)
        ly = _text_box(d, (24, ly), label, f, fill=(255, 255, 255), bg=(20, 20, 20)) + 2
    return img


def banner(img, text, bar=(0, 120, 40)):
    f = font(30)
    d = ImageDraw.Draw(img)
    try:
        h = d.textbbox((0, 0), text, font=f)[3] + 16
    except Exception:
        h = 42
    out = Image.new("RGB", (img.width, img.height + h), (255, 255, 255))
    out.paste(img, (0, h))
    d2 = ImageDraw.Draw(out)
    d2.rectangle((0, 0, out.width, h), fill=bar)
    d2.text((12, 8), text, font=f, fill=(255, 255, 255))
    return out


def contact(panels, title, out_path, panel_w=760, bar=(30, 30, 30)):
    """panels: list of (PIL.Image, caption). Stack vertically, each scaled to panel_w, with a caption bar."""
    f, cf = font(34), font(22)
    scaled = []
    for img, cap in panels:
        w, h = img.size
        nh = int(h * panel_w / w)
        scaled.append((img.resize((panel_w, nh)), cap, nh))
    cap_h = 34
    title_h = 52
    total_h = title_h + sum(nh + cap_h for _, _, nh in scaled) + 12 * (len(scaled) + 1)
    canvas = Image.new("RGB", (panel_w + 24, total_h), (255, 255, 255))
    d = ImageDraw.Draw(canvas)
    d.rectangle((0, 0, canvas.width, title_h), fill=(10, 10, 10))
    d.text((12, 10), title, font=f, fill=(255, 255, 255))
    y = title_h + 12
    for img, cap, nh in scaled:
        d.rectangle((12, y, 12 + panel_w, y + cap_h), fill=bar)
        d.text((18, y + 5), cap, font=cf, fill=(255, 255, 255))
        canvas.paste(img, (12, y + cap_h))
        y += cap_h + nh + 12
    canvas.save(str(out_path))
    return out_path


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for s in OUT.glob("*.png"):
        s.unlink()
    plan = PlanPdf(PDF)
    paths = {}
    try:
        off = select_dialect(plan).calibrate(plan, 13)

        # 1) sheet 5 -- correct AP-137 / LEFT branch
        img1 = annotated(plan, off, 5, [
            ("2+43", "STA 2+43 INSTALLER HH = START", GREEN),
            ("AP-137", "AP-137 = LEFT branch (CORRECT side)", LIME),
            ("24+11/4+37/1+92", "bundled MATCHLINE 24+11/4+37/1+92 -> SEE SHEET 6", ORANGE),
            ("STA 3+25 TO STA 4+37", "left branch crosses at 4+37 (CORRECT crossing)", CYAN),
        ])
        if img1 is None:
            img1 = annotated(plan, off, 5, [("2+43", "STA 2+43 INSTALLER HH", GREEN),
                                            ("AP-137", "AP-137 LEFT (CORRECT)", LIME)])
        img1 = banner(img1, "CORRECT LOG61 SIDE: AP-137 / LEFT BRANCH", bar=(0, 120, 40))
        p1 = OUT / "log61_correct_sheet5_ap137.png"; img1.save(str(p1)); paths["s5"] = p1

        # 2) sheet 6 -- correct terminus 4+50
        img2 = annotated(plan, off, 6, [
            ("STA 4+37 TO STA 4+50", "STA 4+37 TO 4+50 (13' fiber drop)", CYAN),
            ("STA 4+50", "STA 4+50 FLOWER POT = CORRECT TERMINUS", GREEN),
        ], zoom=2.6)
        if img2 is None:
            img2 = annotated(plan, off, 6, [("4+50", "STA 4+50 FLOWER POT", GREEN)], zoom=2.6)
        img2 = banner(img2, "CORRECT LOG61 TERMINUS  (STA 4+50 FLOWER POT, sheet 6)", bar=(0, 120, 40))
        p2 = OUT / "log61_correct_sheet6_4_50.png"; img2.save(str(p2)); paths["s6"] = p2

        # 3) WRONG side -- AP-138 right (sheet 5) + 2+01 flower pot (sheet 6)
        w5 = annotated(plan, off, 5, [("AP-138", "AP-138 = RIGHT branch (WRONG side)", MAGENTA)], zoom=2.4)
        w6 = annotated(plan, off, 6, [("2+01", "STA 2+01 FLOWER POT = WRONG terminus", MAGENTA)], zoom=2.6)
        wrong_panels = [(w5, "sheet 5 -- AP-138 RIGHT branch"), (w6, "sheet 6 -- STA 2+01 FLOWER POT")]
        wrong_panels = [(im, c) for im, c in wrong_panels if im is not None]
        img3 = contact(wrong_panels, "WRONG SIDE -- DO NOT DRAW FOR LOG61  (AP-138 / 2+01, ~250.7' overshoot)",
                       OUT / "_tmp_wrong.png", panel_w=760, bar=(120, 0, 80))
        img3 = Image.open(str(img3))
        p3 = OUT / "log61_wrong_ap138_side.png"; img3.save(str(p3)); paths["wrong"] = p3
        (OUT / "_tmp_wrong.png").unlink(missing_ok=True)

        # 4) log61 contact sheet
        p4 = contact([(Image.open(str(p1)), "1. CORRECT side: AP-137 / LEFT (sheet 5)"),
                      (Image.open(str(p2)), "2. CORRECT terminus: STA 4+50 FLOWER POT (sheet 6)"),
                      (Image.open(str(p3)), "3. WRONG side: AP-138 / STA 2+01 -- do not draw")],
                     "LOG61 REVIEW -- Ruth Circle cul-de-sac (NOT rendered; awaiting solver support)",
                     OUT / "log61_review_contact_sheet.png", panel_w=820)
        paths["contact61"] = p4

        # 5) log48 contact (committed red strokes)
        p5 = contact([(Image.open(str(SWEEP / "log48_s10_redline_stroke.png")), "sheet 10 -- reset HH 45+33=0+00 up Woodson Ln to 1+90 matchline"),
                      (Image.open(str(SWEEP / "log48_s12_redline_stroke.png")), "sheet 12 -- 1+90 matchline through 8-PORT HH AP-167 to STA 5+07 FLOWER POT")],
                     "LOG48 RENDERED CORRECTLY -- WOODSON LN / 5+07  (red = TrueLine redline)",
                     OUT / "log48_review_contact_sheet.png", panel_w=820, bar=(150, 20, 20))
        paths["contact48"] = p5

        # 6) log70 contact (committed red strokes)
        p6 = contact([(Image.open(str(SWEEP / "log70_s17_redline_stroke.png")), "sheet 17 -- START 4+54 INSTALLER HH up Eledra St (175') to 1+75 matchline"),
                      (Image.open(str(SWEEP / "log70_s20_redline_stroke.png")), "sheet 20 -- 1+75 matchline to STA 2+15 FLOWER POT (40'); HH-HH=215'")],
                     "LOG70 RENDERED CORRECTLY -- START 4+54 / ELEDRA / 2+15  (red = TrueLine redline)",
                     OUT / "log70_review_contact_sheet.png", panel_w=820, bar=(150, 20, 20))
        paths["contact70"] = p6
    finally:
        plan.close()
    for k, v in paths.items():
        print(f"[review-pack] {k}: {v}  ({os.path.getsize(v)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
