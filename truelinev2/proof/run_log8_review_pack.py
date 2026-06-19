r"""LOG8 owner-review contact sheet (read-only; NO red stroke; helper-color annotations only).

log8 = cross-sheet drop 18->22, 0+00 -> STA 3+90 FLOWER POT (390', Hickory Ln), via the 1+77/1+76 matchline.
The END is clear; the START is a NON-UNIQUE 0+00 origin and NO printed discriminator uniquely selects it
(two reset HHs both close: 12+22 NEXTLINK 426' loose, 12+93 INSTALLER 384.6' tight; no clean HH-HH
decomposition to 390). Owner picks the origin. Output gitignored.

Run: $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_log8_review_pack
"""
from __future__ import annotations
import os
from PIL import Image, ImageDraw, ImageFont
from truelinev2.config import _REPO_ROOT
from truelinev2.extract.registry import select_dialect
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.proof.run_brenham_corpus import PDF

OUT = _REPO_ROOT / "data" / "outputs" / "log8_review_pack"
GREEN, ORANGE, CYAN, MAGENTA, LIME = (0, 170, 60), (255, 140, 0), (0, 175, 220), (210, 0, 170), (80, 210, 40)


def font(sz):
    for p in (r"C:\Windows\Fonts\arialbd.ttf", "arialbd.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(p, sz)
        except Exception:
            pass
    return ImageFont.load_default()


def _tb(d, xy, text, f, bg=(20, 20, 20)):
    x, y = xy
    try:
        b = d.textbbox((x, y), text, font=f)
    except Exception:
        b = (x, y, x + 9 * len(text), y + 18)
    d.rectangle((b[0] - 5, b[1] - 3, b[2] + 5, b[3] + 3), fill=bg)
    d.text((x, y), text, font=f, fill=(255, 255, 255))
    return b[3] + 6


def annotated(plan, off, sheet, specs, zoom=2.3, pad=80):
    boxes, found = [], []
    for q, label, color in specs:
        hits = plan.search(sheet, off, q)
        if hits:
            boxes.append(hits[0]); found.append((hits[0], label, color))
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
    f = font(21)
    ly = 8
    for (bx, label, color) in found:
        x0, y0 = (bx[0] - ox) * zoom, (bx[1] - oy) * zoom
        x1, y1 = (bx[2] - ox) * zoom, (bx[3] - oy) * zoom
        m = 14
        d.ellipse((x0 - m, y0 - m, x1 + m, y1 + m), outline=color, width=6)
        d.rectangle((6, ly - 3, 20, ly + 16), fill=color)
        ly = _tb(d, (26, ly), label, f) + 3
    return img


def contact(panels, title, out_path, panel_w=940):
    f, cf = font(29), font(21)
    scaled = [(im.resize((panel_w, int(im.height * panel_w / im.width))), cap) for im, cap in panels if im]
    cap_h, title_h = 34, 48
    total = title_h + sum(im.height + cap_h for im, _ in scaled) + 12 * (len(scaled) + 1)
    canvas = Image.new("RGB", (panel_w + 24, total), (255, 255, 255))
    d = ImageDraw.Draw(canvas)
    d.rectangle((0, 0, canvas.width, title_h), fill=(10, 10, 10))
    d.text((12, 8), title, font=f, fill=(255, 255, 255))
    y = title_h + 12
    for im, cap in scaled:
        d.rectangle((12, y, 12 + panel_w, y + cap_h), fill=(45, 45, 45))
        d.text((18, y + 6), cap, font=cf, fill=(255, 255, 255))
        canvas.paste(im, (12, y + cap_h)); y += cap_h + im.height + 12
    canvas.save(str(out_path))
    return out_path


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for s in OUT.glob("*.png"):
        s.unlink()
    plan = PlanPdf(PDF)
    try:
        off = select_dialect(plan).calibrate(plan, 13)
        p18 = annotated(plan, off, 18, [
            ("12+22=0+00", "START CANDIDATE A: STA 12+22=0+00 NEXTLINK HH / SPLICE POINT 34  (route 426' -- LOOSE 9% closure; = log32's origin)", ORANGE),
            ("12+93=0+00", "START CANDIDATE B: STA 12+93=0+00 INSTALLER HH  (route 384.6' -- TIGHT 1.4% closure)", LIME),
            ("MATCHLINE STA 1+77", "MATCHLINE STA 1+77/1+76 -> SEE SHEET 22  (the cross-sheet join)", CYAN),
        ])
        if p18 is None:
            p18 = annotated(plan, off, 18, [("12+22=0+00", "CAND A: 12+22 NEXTLINK HH", ORANGE),
                                            ("12+93=0+00", "CAND B: 12+93 INSTALLER HH", LIME)])
        p22 = annotated(plan, off, 22, [
            ("3+90", "END (CLEAR): STA 3+90 FLOWER POT 11x11x12 (Hickory Ln); 1-1.25\" drop, 214' from the matchline", GREEN),
            ("MATCHLINE STA 1+77", "MATCHLINE STA 1+77/1+76 -> SEE SHEET 18 (reciprocal)", CYAN),
        ])
        if p22 is None:
            p22 = annotated(plan, off, 22, [("3+90", "END: STA 3+90 FLOWER POT", GREEN)])
        panels = [(p18, "sheet 18 -- WHICH 0+00 origin? A=12+22 NEXTLINK (426', loose) vs B=12+93 INSTALLER (384.6', tight); both close"),
                  (p22, "sheet 22 -- END is clear: STA 3+90 FLOWER POT, Hickory Ln")]
        out = contact(panels, "LOG8 OWNER REVIEW -- cross-sheet drop 18->22 (390'); END clear, START 0+00 ambiguous (pick A or B)",
                      OUT / "log8_contact_sheet.png")
        print(f"[log8-review] {out}  ({os.path.getsize(out)} bytes)")
    finally:
        plan.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
