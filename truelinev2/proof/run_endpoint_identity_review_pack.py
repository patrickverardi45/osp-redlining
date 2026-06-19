r"""GATE #2 ENDPOINT-IDENTITY VISUAL REVIEW PACK (read-only; NO red stroke; helper-color annotations only).

Builds annotated contact sheets so the owner can confirm the missing endpoint identities for the
highest-potential remaining endpoint-identity logs. NO red is used (no confirmed redline drawn here);
diagnostic circles/labels use HELPER colors only. NO stroke, NO census/corpus change. Output under
gitignored data/outputs/endpoint_identity_review_pack/.

Run: $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_endpoint_identity_review_pack
"""
from __future__ import annotations
import os
from PIL import Image, ImageDraw, ImageFont
from truelinev2.config import _REPO_ROOT
from truelinev2.extract.registry import select_dialect
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.proof.run_brenham_corpus import PDF

OUT = _REPO_ROOT / "data" / "outputs" / "endpoint_identity_review_pack"
GREEN, ORANGE, CYAN, MAGENTA, LIME, RED_X = (0, 170, 60), (255, 140, 0), (0, 175, 220), (210, 0, 170), (80, 210, 40), (200, 40, 40)


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


def contact(panels, title, out_path, panel_w=920):
    f, cf = font(30), font(21)
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


# (name, out_filename, title, [(sheet, [(query,label,color)...], panel_caption), ...])
CANDS = [
    ("log2", "log2_contact_sheet.png",
     "LOG2 (OWNER-CONFIRM #1, SOURCE-COMPLETE) -- 18->19 mainline; legs 616'+233'=849'; END=AP-148 6-PORT HH", [
        (18, [("12+22=0+00", "START: STA 12+22=0+00 NEXTLINK HH / PROP SPLICE POINT 34 (owner-confirmed = log32 origin)", GREEN),
              ("MATCHLINE STA 18+38", "JOIN: MATCHLINE STA 18+38 -> SEE SHEET 19  (leg 12+22->18+38 = 616')", CYAN)],
         "sheet 18 -- START 12+22 NEXTLINK HH; mainline runs 616' to the 18+38 matchline"),
        (19, [("MATCHLINE STA 18+38", "JOIN (reciprocal): MATCHLINE STA 18+38 -> SEE SHEET 18", CYAN),
              ("AP-148", "END: STA 20+71 TERMINAL 6-PORT HH / AP-148 SPLICE LOC 34 (Niebuhr St; leg 18+38->20+71 = 233')", MAGENTA)],
         "sheet 19 -- END 20+71 TERMINAL 6-PORT HH (AP-148); 233' past the 18+38 matchline. 616+233=849=span"),
     ]),
    ("log42", "log42_contact_sheet.png",
     "LOG42 -- 0+00 NEXTLINK HH (splice pt 13) -> 2+87 TERMINAL 6-PORT HH AP-105  (both PRINTED; 287')", [
        (1, [("SPLICE POINT", "START: STA 0+00 EXIST. PROP. SPLICE POINT 13 / NEXTLINK HH (30x48x36 vault -- 'unmodeled' splice class)", GREEN),
             ("AP-105", "END: STA 2+87 TERMINAL 6-PORT HH / AP-105 SPLICE LOC 25", MAGENTA),
             ("MATCHLINE STA 2+70", "MATCHLINE STA 2+70/5+16 -> SEE SHEET 2 (run mostly on sheet 1)", CYAN)],
         "sheet 1 -- both endpoints printed; owner: confirm the 0+00 splice-vault start + AP-105 end"),
     ]),
    ("log8", "log8_contact_sheet.png",
     "LOG8 -- END clear (3+90 FLOWER POT); START = which 0+00 origin?  (closes 176+214=390')", [
        (18, [("STA 0+00 TO STA 1+65", "START CANDIDATE A: STA 0+00 TO 1+65 (165') near INSTALLER HH 0+57", ORANGE),
              ("STA 0+00 TO STA 1+10", "START CANDIDATE B: STA 0+00 TO 1+10 (110') near 12+93 INSTALLER HH / AP-147", LIME),
              ("MATCHLINE STA 1+77/1+76", "JOIN: MATCHLINE STA 1+77/1+76 -> SEE SHEET 22", CYAN)],
         "sheet 18 -- which 0+00 drop origin? (owner pick)"),
        (22, [("3+90", "END: STA 3+90 FLOWER POT 11x11x12 (Hickory Ln)", GREEN),
              ("MATCHLINE STA 1+77/1+76", "JOIN (reciprocal): MATCHLINE STA 1+77/1+76 -> SEE SHEET 18", CYAN)],
         "sheet 22 -- END 3+90 FLOWER POT; 214' past the 1+76 matchline"),
     ]),
    ("log56", "log56_contact_sheet.png",
     "LOG56 -- 0+00 drop -> 2+76 FLOWER POT (276'); START = 0+46 INSTALLER HH or 7+40 NEXTLINK HH?", [
        (2, [("0+46=0+00", "START CANDIDATE A: STA 0+46=0+00 INSTALLER HH", ORANGE),
             ("7+40=0+00", "START CANDIDATE B: STA 7+40=0+00 NEXTLINK HH / PROP SPLICE POINT 25", LIME)],
         "sheet 2 -- which 0+00 origin feeds the 276' drop to the 2+76 FLOWER POT? (owner pick)"),
     ]),
    ("log16", "log16_contact_sheet.png",
     "LOG16 (DEFER? probable FIBER BACKBONE) -- END 39+79 INSTALLER HH; START 31+00 by CHAPPELL (48ct fiber)", [
        (8, [("31+00", "START? STA 31+00 (sheet 8, Chappell St) -- near 48ct FIBER + 2-1.25\" conduit + matchline to s7", RED_X)],
         "sheet 8 -- START 31+00: is this the 2-1.25\" FIBER BACKBONE (Gate #1), not a drop?"),
        (10, [("39+79", "END: STA 39+79 INSTALLER HH 13x24x24 (Allyne St)", GREEN)],
         "sheet 10 -- END 39+79 INSTALLER HH"),
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
                if im is None and specs:
                    im = annotated(plan, off, sheet, [specs[0]])
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
