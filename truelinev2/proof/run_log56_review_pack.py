r"""LOG56 owner-review contact sheet (read-only; NO red stroke; helper-color annotations only).

log56 = single-sheet drop on sheet 2 (Stone St area), ~270', down to a FLOWER POT. The conduit IS a real
1-1.25" drop (traceable in BASE_CONDUIT), and the 0+46 INSTALLER HH chain reaches a UNIQUE flower-pot symbol
at ~267ft. Two open items keep it from a clean deterministic render:
  (1) END = a SYMBOL-ONLY flower pot -- it has NO bindable station label (2+70/2+76 -> no bind; nearest
      printed station '2+52' is 37pt off), so no shipped hook binds it (end_hh_symbol_bind is HH-layer only);
      a new flower-pot-end-symbol bind would be needed.
  (2) START = the 0+46=0+00 INSTALLER HH (co-located with the '0+00 TO 2+70' PORT TERMINAL TAIL drop) is the
      likely origin, but the 7+40=0+00 NEXTLINK HH / SPLICE POINT 25 also resets to 0+00 nearby.
Owner review requested. Output gitignored.

Run: $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_log56_review_pack
"""
from __future__ import annotations
import os
from PIL import Image, ImageDraw, ImageFont
from truelinev2.config import _REPO_ROOT
from truelinev2.extract.registry import select_dialect
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.proof.run_brenham_corpus import PDF

OUT = _REPO_ROOT / "data" / "outputs" / "log56_review_pack"
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


def annotated(plan, off, sheet, specs, zoom=2.3, pad=90):
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


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for s in OUT.glob("*.png"):
        s.unlink()
    plan = PlanPdf(PDF)
    try:
        off = select_dialect(plan).calibrate(plan, 13)
        img = annotated(plan, off, 2, [
            ("0+46=0+00", "START CANDIDATE A (likely): STA 0+46=0+00 INSTALLER HH -- the '0+00 TO 2+70' drop origin", GREEN),
            ("7+40=0+00", "START CANDIDATE B: STA 7+40=0+00 NEXTLINK HH / SPLICE POINT 25 (the area splice)", ORANGE),
            ("STA 0+00 TO STA 2+70", "DROP: STA 0+00 TO STA 2+70 (270') 1-1.25\" PORT TERMINAL TAIL -> FLOWER POT", CYAN),
        ], zoom=2.0)
        if img is None:
            img = annotated(plan, off, 2, [("0+46=0+00", "CAND A: 0+46 INSTALLER HH", GREEN),
                                           ("7+40=0+00", "CAND B: 7+40 NEXTLINK HH", ORANGE)], zoom=2.0)
        # banner about the end
        f = font(22)
        d = ImageDraw.Draw(img)
        _tb(d, (26, img.height - 60), "END = symbol-only FLOWER POT at ~270' (no bindable station label; nearest '2+52' 37pt off)", f, bg=(150, 20, 20))
        out = OUT / "log56_contact_sheet.png"
        img.save(str(out))
        print(f"[log56-review] {out}  ({os.path.getsize(out)} bytes)")
    finally:
        plan.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
