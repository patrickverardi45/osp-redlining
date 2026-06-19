r"""LOG3 OWNER CONTROL-POINT PACKET -- read-only helper contact sheet (NO TrueLine red stroke; NO render of a
redline; NO commit/census/fixture/corpus mutation).

Generates a sheet-3 source-PDF crop around the printed `STA 12+66 TO STA 15+13 (247')` run with HELPER-COLOR
overlays so the owner can supply a few precise control points (in source/PDF coordinate space) for the two
under-sampled gaps the station-ladder proof measured. Draws:
  - the bound START (12+66 matchline boundary, BLUE) and END (15+13 NEXTLINK HH, GREEN) -- already bound
  - the printed callout location (CYAN)
  - the measured printed-control SPINE (ORANGE dashed -- a HELPER line, NOT a red TrueLine stroke)
  - the UNDER-SAMPLED GAPS to mark through (YELLOW), with numbered click-targets
  - the PARALLEL y~363 track to AVOID (PURPLE "AVOID")
  - a PDF-coordinate GRID (gray) for direct read-off
plus a JSON sidecar carrying the EXACT pixel<->PDF transform (so owner-marked pixels convert deterministically,
never inferred) and a markdown instruction sheet.

Colors are deliberately NOT REDLINE_STROKE_RGB (220,25,25). Nothing here is a placement. Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_log3_owner_control_point_packet
"""
from __future__ import annotations

import json
import math

from PIL import Image, ImageDraw, ImageFont

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.conduit_topology import MAX_DASH_GAP, dash_endpoints
from truelinev2.extract.matchline_join import extend_dash_to_boundary, nearest_gap
from truelinev2.extract.registry import select_dialect
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.proof.run_brenham_corpus import PDF
from truelinev2.proof.run_callout_route_assembly_sweep import (
    FIBER_CONDUIT_EXTRA, SCALE, _bind, _conduit_components, _ml_bbox,
)
from truelinev2.proof.run_callout_route_assembly_sweep import BASE_CONDUIT
from truelinev2.proof.run_log3_chain_route_proof_slice import (
    CONTROL_GAP_CAP, _station_ladder_callout_route_geometry,
)

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "log3_owner_control_point_packet"
FIBER = BASE_CONDUIT | set(FIBER_CONDUIT_EXTRA)
ZOOM = 3.0
HEADER_PX = 150
BBOX = [758.0, 248.0, 1158.0, 384.0]      # s3 corridor around the 12+66->15+13 run (PDF display coords)
# HELPER colors (NONE is the red REDLINE_STROKE_RGB (220,25,25)):
C_START = (30, 90, 220)        # blue
C_END = (20, 160, 60)          # green
C_CALLOUT = (0, 165, 200)      # cyan
C_SPINE = (235, 140, 0)        # orange (dashed helper line)
C_GAP = (240, 200, 0)          # amber/yellow
C_AVOID = (160, 30, 200)       # purple
C_GRID = (180, 180, 180)       # light gray
C_TXT = (20, 20, 20)


def _font(sz):
    for p in (r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\arial.ttf"):
        try:
            return ImageFont.truetype(p, sz)
        except Exception:  # noqa: BLE001
            continue
    return ImageFont.load_default()


def _dashed(draw, p0, p1, color, width, dash=9, gap=6):
    d = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
    if d < 1:
        return
    ux, uy = (p1[0] - p0[0]) / d, (p1[1] - p0[1]) / d
    t = 0.0
    while t < d:
        a = (p0[0] + ux * t, p0[1] + uy * t)
        b = (p0[0] + ux * min(t + dash, d), p0[1] + uy * min(t + dash, d))
        draw.line([a, b], fill=color, width=width)
        t += dash + gap


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    plan = PlanPdf(PDF)
    try:
        off = select_dialect(plan).calibrate(plan, 13)
        # --- bound anchors ---
        i_xy = _bind(plan, off, 3, "nextlink_hh", "15+13")[0]            # END (bound)
        draw3, words3 = plan.line_items(3, off), plan.words(3, off)
        bb3 = _ml_bbox(words3, draw3, ("5+26", "12+66"))
        conduit3 = [d for d in draw3 if d.get("layer") in FIBER]
        best, mlc = 1e9, None
        for c in _conduit_components(conduit3):
            eps = dash_endpoints(c)
            if eps:
                g = min(nearest_gap([p], bb3) for p in eps)
                if g <= MAX_DASH_GAP and g < best:
                    best, mlc = g, c
        a_xy = tuple(extend_dash_to_boundary(mlc, bb3)) if mlc is not None else None    # START (bound matchline)
        # --- measured spine + under-sampled gaps ---
        y_lo, y_hi = i_xy[1] - 60.0, i_xy[1] + 25.0
        sl = _station_ladder_callout_route_geometry(plan, off, 3, a_xy, tuple(i_xy), 247, (y_lo, y_hi))
        route = sl.get("_route") or [tuple(a_xy), tuple(i_xy)]
        gaps = []
        for k in range(len(route) - 1):
            d_ft = math.hypot(route[k + 1][0] - route[k][0], route[k + 1][1] - route[k][1]) / SCALE
            if d_ft > CONTROL_GAP_CAP:
                gaps.append({"i": k, "a": route[k], "b": route[k + 1], "ft": round(d_ft, 1)})
        # --- callout location (footage token) ---
        cap_hits = plan.search(3, off, "247")
        callout_xy = ((cap_hits[0][0] + cap_hits[0][2]) / 2, (cap_hits[0][1] + cap_hits[0][3]) / 2) if cap_hits else None

        # --- rasterize the corridor ---
        rendered = plan.render_clip(3, off, BBOX, zoom=ZOOM, pad=10.0)
        if rendered is None:
            print("[packet] render_clip returned None -- bbox empty?")
            return 1
        crop, cx0, cy0 = rendered
        W, H = crop.size
        canvas = Image.new("RGB", (W, H + HEADER_PX), (255, 255, 255))
        canvas.paste(crop, (0, HEADER_PX))
        draw = ImageDraw.Draw(canvas)

        def px(p):
            return ((p[0] - cx0) * ZOOM, (p[1] - cy0) * ZOOM + HEADER_PX)

        # --- PDF coordinate grid (read-off) ---
        f_sm, f_md, f_lg = _font(13), _font(16), _font(20)
        x0p, y0p, x1p, y1p = BBOX
        gx = int(x0p // 50 * 50)
        while gx <= x1p:
            a, b = px((gx, y0p)), px((gx, y1p))
            draw.line([a, b], fill=C_GRID, width=1)
            draw.text((a[0] + 2, HEADER_PX + 2), f"x={gx}", fill=C_GRID, font=f_sm)
            gx += 50
        gy = int(y0p // 25 * 25)
        while gy <= y1p:
            a, b = px((x0p, gy)), px((x1p, gy))
            draw.line([a, b], fill=C_GRID, width=1)
            draw.text((2, a[1] + 1), f"y={gy}", fill=C_GRID, font=f_sm)
            gy += 25

        # --- AVOID: parallel y~363 track (mid-run) ---
        av = [px((895, 352)), px((1085, 374))]
        draw.rectangle([av[0], av[1]], outline=C_AVOID, width=3)
        draw.text((av[0][0] + 3, av[0][1] - 18), "AVOID parallel track (y~363)", fill=C_AVOID, font=f_md)

        # --- measured spine (ORANGE dashed helper line; NOT a red stroke) ---
        for k in range(len(route) - 1):
            _dashed(draw, px(route[k]), px(route[k + 1]), C_SPINE, 2)
        draw.text((px(route[len(route) // 2])[0], px(route[len(route) // 2])[1] - 16),
                  "measured spine (helper, not a redline)", fill=C_SPINE, font=f_sm)

        # --- under-sampled GAPS + numbered click-targets ---
        tnum = 0
        for gi, g in enumerate(gaps, 1):
            ga, gb = px(g["a"]), px(g["b"])
            draw.line([ga, gb], fill=C_GAP, width=7)
            draw.line([ga, gb], fill=C_AVOID, width=1)  # thin overlay for contrast
            mid = ((ga[0] + gb[0]) / 2, (ga[1] + gb[1]) / 2)
            draw.text((mid[0] - 10, mid[1] + 6), f"GAP {gi}  ({g['ft']}ft) -- mark here", fill=(150, 110, 0), font=f_md)
            n = 3 if gi == 1 else 2
            for t in range(1, n + 1):
                frac = t / (n + 1)
                cp = (ga[0] + (gb[0] - ga[0]) * frac, ga[1] + (gb[1] - ga[1]) * frac)
                tnum += 1
                draw.ellipse([cp[0] - 7, cp[1] - 7, cp[0] + 7, cp[1] + 7], outline=C_GAP, width=2)
                draw.text((cp[0] - 4, cp[1] - 7), str(tnum), fill=(150, 110, 0), font=f_sm)

        # --- bound endpoints (do NOT mark) ---
        for xy, col, lab in ((a_xy, C_START, "START 12+66 (bound -- DO NOT mark)"),
                             (tuple(i_xy), C_END, "END 15+13 NEXTLINK HH (bound -- DO NOT mark)")):
            p = px(xy)
            draw.ellipse([p[0] - 9, p[1] - 9, p[0] + 9, p[1] + 9], outline=col, width=3)
            draw.line([(p[0] - 13, p[1]), (p[0] + 13, p[1])], fill=col, width=2)
            draw.line([(p[0], p[1] - 13), (p[0], p[1] + 13)], fill=col, width=2)
            draw.text((p[0] + 12, p[1] - 6), lab, fill=col, font=f_sm)
        if callout_xy:
            cp = px(callout_xy)
            draw.rectangle([cp[0] - 26, cp[1] - 11, cp[0] + 26, cp[1] + 11], outline=C_CALLOUT, width=2)
            draw.text((cp[0] - 26, cp[1] - 26), "callout (247')", fill=C_CALLOUT, font=f_sm)

        # --- header instructions ---
        draw.rectangle([0, 0, W, HEADER_PX - 1], fill=(255, 255, 255), outline=(120, 120, 120))
        draw.text((10, 6), "LOG3  s3  STA 12+66 -> STA 15+13  (247')  -- OWNER CONTROL-POINT PACKET (helper only; not a redline)",
                  fill=C_TXT, font=f_lg)
        lines = [
            "Mark 3-6 points along the INTENDED BORE CENTERLINE through the YELLOW gaps ONLY (numbered targets 1..N are suggestions).",
            "DO NOT mark the endpoints (START/END already bind).   DO NOT mark inside the PURPLE 'AVOID' parallel track.",
            "Read coordinates off the gray PDF grid (x=.., y=..), OR annotate this image with dots and return it -- only your explicit dots are used.",
            f"Spine measured {sl.get('length_ft')}ft vs printed 247ft; your points in GAP 1 (descent) + GAP 2 (mid-run) pull it onto the true bore so it closes.",
        ]
        for j, ln in enumerate(lines):
            draw.text((10, 34 + j * 26), ln, fill=C_TXT, font=f_md)

        png = OUT_DIR / "log3_owner_control_point_packet.png"
        canvas.save(png)

        # --- JSON sidecar: EXACT transform (owner pixels -> PDF coords) + features ---
        sidecar = {
            "sheet": 3, "callout": "STA 12+66 TO STA 15+13 (247')", "units": "PDF display points",
            "pixel_to_pdf": {"formula": "pdf_x = px/zoom + clip_x0 ; pdf_y = py/zoom + clip_y0",
                             "zoom": ZOOM, "clip_x0": round(cx0, 3), "clip_y0": round(cy0, 3),
                             "header_px": HEADER_PX, "note": "subtract header_px from py BEFORE converting (map starts below the header)",
                             "image_w": W, "image_h": H + HEADER_PX},
            "bound_anchors_do_not_mark": {"start_12+66_matchline": [round(a_xy[0], 1), round(a_xy[1], 1)],
                                          "end_15+13_nextlink_hh": [round(i_xy[0], 1), round(i_xy[1], 1)]},
            "measured_spine_pdf": [[round(p[0], 1), round(p[1], 1)] for p in route],
            "under_sampled_gaps": [{"gap": gi, "ft": g["ft"],
                                    "from": [round(g["a"][0], 1), round(g["a"][1], 1)],
                                    "to": [round(g["b"][0], 1), round(g["b"][1], 1)]}
                                   for gi, g in enumerate(gaps, 1)],
            "avoid_parallel_track_y_approx": 363,
            "owner_marks_schema": {"return": "list of {gap, pdf_x, pdf_y} OR annotated PNG dots",
                                   "rule": "ONLY explicit owner marks become control points; the route is never freely inferred"},
            "closure_target_ft": 247, "closure_rel_tol": 0.10,
        }
        (OUT_DIR / "log3_owner_control_point_packet.json").write_text(
            json.dumps(sidecar, indent=2), encoding="utf-8")

        md = OUT_DIR / "log3_owner_control_point_instructions.md"
        md.write_text(
            "# LOG3 owner control-point packet (s3 STA 12+66 -> STA 15+13, 247')\n\n"
            "**This is a helper contact sheet, NOT a redline.** The TrueLine stroke is not drawn here.\n\n"
            "## What to do\n"
            "1. Look at `log3_owner_control_point_packet.png`.\n"
            "2. Mark **3-6 points** along the **intended bore centerline**, but **only inside the yellow GAP segments** "
            "(GAP 1 = matchline descent, GAP 2 = mid-run). Numbered targets 1..N are suggested spots.\n"
            "3. **Do NOT** mark the START (blue) or END (green) -- they already bind.\n"
            "4. **Do NOT** mark inside the purple **AVOID** box (the parallel y~363 fiber track).\n\n"
            "## How to give coordinates (either way)\n"
            "- **A. Read off the grid:** each point's `x=..`, `y=..` from the gray PDF grid, returned as a list.\n"
            "- **B. Annotate the image:** drop dots on the PNG and return it; only your explicit dots are extracted "
            "(via `pixel_to_pdf` in the JSON) -- the route is never freely inferred.\n\n"
            "## Why\n"
            f"The measured printed-control spine is **{sl.get('length_ft')}ft** vs the printed **247ft** "
            "because the two gaps are under-sampled and get bridged straight. Your few points pull the spine onto "
            "the true bore so it closes to 247' -- then the proof's G9 passes and only the upstream 250' draws "
            "(downstream stays covered by log4).\n",
            encoding="utf-8")

        print(f"[packet] START 12+66 = {[round(a_xy[0],1),round(a_xy[1],1)]}  END 15+13 = {[round(i_xy[0],1),round(i_xy[1],1)]}")
        print(f"[packet] spine pts={len(route)} len={sl.get('length_ft')}ft  under-sampled gaps={len(gaps)} "
              f"{[g['ft'] for g in gaps]}ft")
        print(f"[packet] image={png}  ({W}x{H+HEADER_PX})")
        print(f"[packet] sidecar={OUT_DIR / 'log3_owner_control_point_packet.json'}")
        print(f"[packet] instructions={md}")
    finally:
        plan.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
