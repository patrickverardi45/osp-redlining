r"""REMAINING-LOG ENDPOINT VISUAL REVIEW PACK (read-only; renders NO redline; helper-color annotations only).

Builds annotated contact sheets so the owner can identify missing endpoints/resets for the highest-potential
remaining (non-rendered) logs: log32 (ambiguous origin A/B), log30 (1+90 family), and the best
endpoint-identity-needed logs (log49, log27, log19). NO red is used (no confirmed redline here). NO stroke,
NO census/corpus change. Output under gitignored data/outputs/remaining_endpoint_review/.

Run: $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_remaining_endpoint_review
"""
from __future__ import annotations
import os
from PIL import Image, ImageDraw, ImageFont
from truelinev2.config import _REPO_ROOT
from truelinev2.extract.registry import select_dialect
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.proof.run_brenham_corpus import PDF

OUT = _REPO_ROOT / "data" / "outputs" / "remaining_endpoint_review"
GREEN, ORANGE, CYAN, MAGENTA = (0, 170, 60), (255, 140, 0), (0, 175, 220), (210, 0, 170)


def font(sz):
    for p in (rf"C:\Windows\Fonts\arialbd.ttf", "arialbd.ttf", "arial.ttf"):
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


def annotated(plan, off, sheet, specs, zoom=2.4, pad=70):
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


def contact(panels, title, out_path, panel_w=900):
    f, cf = font(32), font(22)
    scaled = [(im.resize((panel_w, int(im.height * panel_w / im.width))), cap) for im, cap in panels if im]
    cap_h, title_h = 34, 50
    total = title_h + sum(im.height + cap_h for im, _ in scaled) + 12 * (len(scaled) + 1)
    canvas = Image.new("RGB", (panel_w + 24, total), (255, 255, 255))
    d = ImageDraw.Draw(canvas)
    d.rectangle((0, 0, canvas.width, title_h), fill=(10, 10, 10))
    d.text((12, 9), title, font=f, fill=(255, 255, 255))
    y = title_h + 12
    for im, cap in scaled:
        d.rectangle((12, y, 12 + panel_w, y + cap_h), fill=(45, 45, 45))
        d.text((18, y + 6), cap, font=cf, fill=(255, 255, 255))
        canvas.paste(im, (12, y + cap_h)); y += cap_h + im.height + 12
    canvas.save(str(out_path))
    return out_path


# (name, out_filename, title, [(sheet, [(query,label,color)...], panel_caption), ...])
CANDS = [
    ("log32", "log32_contact_sheet.png",
     "LOG32 -- AMBIGUOUS ORIGIN: pick CANDIDATE A (12+22 ~207.2') or B (12+93 ~210.5')", [
        (18, [("12+22=0+00", "CANDIDATE A: STA 12+22=0+00 NEXTLINK HH  (route ~207.2')", GREEN),
              ("12+93=0+00", "CANDIDATE B: STA 12+93=0+00 INSTALLER HH  (route ~210.5')", ORANGE),
              ("SEE SHEET 22", "MATCHLINE STA 1+77 -> SEE SHEET 22", CYAN)],
         "sheet 18 -- which reset HH feeds the log32 drop?"),
        (22, [("STA 2+13", "END: STA 2+13 FLOWER POT", MAGENTA),
              ("SEE SHEET 18", "MATCHLINE STA 1+76 -> SEE SHEET 18", CYAN)],
         "sheet 22 -- log32 end: STA 2+13 FLOWER POT"),
     ]),
    ("log30", "log30_contact_sheet.png",
     "LOG30 (0+00->5+00, sheets 10/12, 1+90 family) -- identify START + END", [
        (10, [("SEE SHEET 12", "MATCHLINE 1+90/1+90 & 1+91/1+92 -> SEE SHEET 12", CYAN),
              ("SPLICE POINT", "plausible START: a PROP. SPLICE POINT / reset HH (0+00)", GREEN)],
         "sheet 10 -- log30 start? (0+00 origin: which structure?)"),
        (12, [("SEE SHEET 10", "reciprocal MATCHLINE -> SEE SHEET 10", CYAN),
              ("5+07", "plausible END near 5+00: a FLOWER POT (5+07 / 5+10 present)", MAGENTA)],
         "sheet 12 -- log30 end? (5+00: which flower pot?)"),
     ]),
    ("log49", "log49_contact_sheet.png",
     "LOG49 (44' single-sheet, sheet 10) -- END binds @45+33 HH; START 44+89 unidentified", [
        (10, [("45+33", "END (binds): STA 45+33=0+00 NEXTLINK HH / SPLICE POINT 46", GREEN),
              ("44+83", "START? STA 44+89 origin area (44+83 nearby) -- identify the structure", ORANGE)],
         "sheet 10 -- identify the log49 START at ~44+89"),
     ]),
    ("log27", "log27_contact_sheet.png",
     "LOG27 (sheets 15/16) -- START binds @7+30 PORT HH; END 13+55 unidentified", [
        (15, [("7+30", "START (binds): TERMINAL PORT HH @ STA 7+30", GREEN)],
         "sheet 15 -- log27 start @ 7+30 PORT HH"),
        (16, [("13+55", "END? STA 13+55 area -- identify the structure", ORANGE)],
         "sheet 16 -- log27 end @ ~13+55"),
     ]),
    ("log19", "log19_contact_sheet.png",
     "LOG19 (single-sheet 14, 656') -- START binds @4+94 INSTALLER HH; END 11+50 unidentified", [
        (14, [("4+94", "START (binds): STA 4+94 INSTALLER HH", GREEN),
              ("INSTALLER HH", "the 656' run heads to STA 11+50 (END unlabeled -- locate it on sheet 14)", ORANGE)],
         "sheet 14 -- log19 START @4+94; locate the 11+50 END"),
     ]),
]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for s in OUT.glob("*.png"):
        s.unlink()
    plan = PlanPdf(PDF)
    paths = {}
    try:
        off = select_dialect(plan).calibrate(plan, 13)
        for name, fn, title, panels in CANDS:
            imgs = []
            for sheet, specs, cap in panels:
                im = annotated(plan, off, sheet, specs)
                if im is None:  # fallback: crop the whole sheet area around the first query token loosely
                    im = annotated(plan, off, sheet, [specs[0]]) if specs else None
                if im is not None:
                    imgs.append((im, cap))
            p = contact(imgs, title, OUT / fn) if imgs else None
            paths[name] = p
    finally:
        plan.close()
    for k, v in paths.items():
        print(f"[review] {k}: {v}  ({os.path.getsize(v) if v else 0} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
