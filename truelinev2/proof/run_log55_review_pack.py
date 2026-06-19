r"""LOG55 owner-review contact sheet (read-only; NO red stroke; helper-color annotations only).

log55 = single-sheet drop on sheet 17, ~169'. The NEW drop_terminus_symbol_bind primitive WOULD render it,
but the START is a 5-way ambiguous 0+00: sheet 17 prints five reset HHs (2+05/1+45/4+57/3+91/0+56=0+00).
Of the five, ONLY STA 4+57=0+00 INSTALLER HH produces a UNIQUE drop-terminus that closes the span (a flower-
pot symbol at 173.8' vs span 169'); the others do not bind or reach no terminus. So the SOURCE uniquely
indicates 4+57 -- but because the 0+00 is 5-way ambiguous, owner confirmation is requested before render.
Output gitignored.

Run: $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_log55_review_pack
"""
from __future__ import annotations
import os
from PIL import Image, ImageDraw, ImageFont
from truelinev2.config import _REPO_ROOT
from truelinev2.extract.registry import select_dialect
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.proof.run_brenham_corpus import PDF

OUT = _REPO_ROOT / "data" / "outputs" / "log55_review_pack"
GREEN, ORANGE, CYAN, MAGENTA, GREY = (0, 170, 60), (255, 140, 0), (0, 175, 220), (210, 0, 170), (130, 130, 130)


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


def annotated(plan, off, sheet, specs, zoom=2.0, pad=90):
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
    f = font(20)
    ly = 8
    for (bx, label, color) in found:
        x0, y0 = (bx[0] - ox) * zoom, (bx[1] - oy) * zoom
        x1, y1 = (bx[2] - ox) * zoom, (bx[3] - oy) * zoom
        m = 13
        d.ellipse((x0 - m, y0 - m, x1 + m, y1 + m), outline=color, width=6)
        d.rectangle((6, ly - 3, 20, ly + 16), fill=color)
        ly = _tb(d, (26, ly), label, f) + 3
    return img


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for s in OUT.glob("*.png"):
        s.unlink()
    plan = PlanPdf(PDF)
    try:
        off = select_dialect(plan).calibrate(plan, 13)
        img = annotated(plan, off, 17, [
            ("4+57=0+00", "START (SOURCE-INDICATED): STA 4+57=0+00 INSTALLER HH -- the ONLY reset whose drop reaches a unique flower pot at 169' (173.8' drawn)", GREEN),
            ("2+05=0+00", "other 0+00 reset (2+05) -- no unique drop terminus", GREY),
            ("1+45=0+00", "other 0+00 reset (1+45) -- no flower pot at 169'", GREY),
            ("3+91=0+00", "other 0+00 reset (3+91)", GREY),
            ("0+56=0+00", "other 0+00 reset (0+56) -- no flower pot at 169'", GREY),
        ], zoom=1.7)
        if img is None:
            img = annotated(plan, off, 17, [("4+57=0+00", "START candidate: 4+57 INSTALLER HH", GREEN)], zoom=1.7)
        f = font(21)
        d = ImageDraw.Draw(img)
        _tb(d, (26, img.height - 58), "END = unique flower-pot SYMBOL reached at 173.8' (closes 169'); confirm START = 4+57 INSTALLER HH?", f, bg=(0, 110, 40))
        out = OUT / "log55_contact_sheet.png"
        img.save(str(out))
        print(f"[log55-review] {out}  ({os.path.getsize(out)} bytes)")
    finally:
        plan.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
