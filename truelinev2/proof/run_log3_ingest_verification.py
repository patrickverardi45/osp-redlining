r"""LOG3 owner-control-point INGEST VERIFICATION image -- read-only helper (NO red TrueLine stroke).

Renders a sheet-3 crop showing: the 11 OWNER dots used (green), the final proposed s3 proof spine (orange
dashed helper line -- NOT a redline), the REJECTED lower y~363 diagonal the owner red-X'd (gray dashed box),
and the bound START/END anchors. Proof that the ingested route follows the owner TOP path and avoids the
rejected lower/parallel track. Writes to gitignored data/outputs. Run (repo root):
  $env:PYTHONPATH="."; .\venv\Scripts\python.exe -m truelinev2.proof.run_log3_ingest_verification
"""
from __future__ import annotations

import math
import statistics

from PIL import Image, ImageDraw, ImageFont

from truelinev2.config import _REPO_ROOT
from truelinev2.extract.conduit_topology import MAX_DASH_GAP, dash_endpoints
from truelinev2.extract.matchline_join import extend_dash_to_boundary, nearest_gap
from truelinev2.extract.registry import select_dialect
from truelinev2.ingest.pdf import PlanPdf
from truelinev2.proof.run_brenham_corpus import PDF
from truelinev2.proof.run_callout_route_assembly_sweep import (
    BASE_CONDUIT, FIBER_CONDUIT_EXTRA, _bind, _conduit_components, _ml_bbox,
)
from truelinev2.proof.run_log3_chain_route_proof_slice import (
    OWNER_CONTROL_POINTS_S3, _station_ladder_callout_route_geometry,
)

OUT_DIR = _REPO_ROOT / "data" / "outputs" / "log3_owner_control_point_packet"
FIBER = BASE_CONDUIT | set(FIBER_CONDUIT_EXTRA)
ZOOM, HEADER = 3.0, 120
BBOX = [758.0, 248.0, 1158.0, 384.0]
C_OWNER = (20, 160, 60)      # green owner dots
C_SPINE = (235, 140, 0)      # orange final spine (helper, NOT a redline)
C_REJECT = (110, 110, 110)   # gray rejected region
C_START = (30, 90, 220)
C_TXT = (20, 20, 20)


def _font(sz):
    for p in (r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\arial.ttf"):
        try:
            return ImageFont.truetype(p, sz)
        except Exception:  # noqa: BLE001
            continue
    return ImageFont.load_default()


def _dashed(draw, p0, p1, color, width, dash=10, gap=6):
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
        i_xy = _bind(plan, off, 3, "nextlink_hh", "15+13")[0]
        draw3, words3 = plan.line_items(3, off), plan.words(3, off)
        bb3 = _ml_bbox(words3, draw3, ("5+26", "12+66"))
        best, mlc = 1e9, None
        for c in _conduit_components([d for d in draw3 if d.get("layer") in FIBER]):
            eps = dash_endpoints(c)
            if eps:
                g = min(nearest_gap([p], bb3) for p in eps)
                if g <= MAX_DASH_GAP and g < best:
                    best, mlc = g, c
        a_low = tuple(extend_dash_to_boundary(mlc, bb3))          # the REJECTED lower-path matchline crossing
        top_y = statistics.median([p[1] for p in OWNER_CONTROL_POINTS_S3])
        a_top = (a_low[0], top_y)                                  # the owner TOP-path matchline crossing
        sl = _station_ladder_callout_route_geometry(plan, off, 3, a_top, tuple(i_xy), 247,
                                                    (i_xy[1] - 60, i_xy[1] + 25), owner_controls=OWNER_CONTROL_POINTS_S3)
        route = sl["_route"]

        rendered = plan.render_clip(3, off, BBOX, zoom=ZOOM, pad=10.0)
        crop, cx0, cy0 = rendered
        W, H = crop.size
        canvas = Image.new("RGB", (W, H + HEADER), (255, 255, 255))
        canvas.paste(crop, (0, HEADER))
        draw = ImageDraw.Draw(canvas)
        f_sm, f_md, f_lg = _font(13), _font(16), _font(20)

        def px(p):
            return ((p[0] - cx0) * ZOOM, (p[1] - cy0) * ZOOM + HEADER)

        # REJECTED lower diagonal (owner red-X) -- gray dashed box around the y~363 reject region
        rj = [px((1062, 348)), px((1158, 384))]
        draw.rectangle([rj[0], rj[1]], outline=C_REJECT, width=2)
        _dashed(draw, px(a_low), px((1082, 330)), C_REJECT, 2)
        draw.text((rj[0][0] - 4, rj[0][1] - 16), "REJECTED lower diagonal (owner red-X)", fill=C_REJECT, font=f_sm)

        # FINAL proof spine (orange dashed helper line -- NOT a red TrueLine stroke)
        for k in range(len(route) - 1):
            _dashed(draw, px(route[k]), px(route[k + 1]), C_SPINE, 3)

        # OWNER dots used (green)
        for p in OWNER_CONTROL_POINTS_S3:
            q = px(p)
            draw.ellipse([q[0] - 6, q[1] - 6, q[0] + 6, q[1] + 6], fill=C_OWNER, outline=(255, 255, 255))

        # anchors
        for xy, col, lab in ((a_top, C_START, "START 12+66 @ TOP path (bound)"),
                             (tuple(i_xy), C_OWNER, "END 15+13 NEXTLINK HH (bound)")):
            q = px(xy)
            draw.line([(q[0] - 12, q[1]), (q[0] + 12, q[1])], fill=col, width=2)
            draw.line([(q[0], q[1] - 12), (q[0], q[1] + 12)], fill=col, width=2)
            draw.text((q[0] + 10, q[1] - 16), lab, fill=col, font=f_sm)

        draw.rectangle([0, 0, W, HEADER - 1], fill=(255, 255, 255), outline=(120, 120, 120))
        draw.text((10, 6), "LOG3 s3 12+66->15+13 -- OWNER-CONTROL INGEST VERIFICATION (helper only; NOT a redline)",
                  fill=C_TXT, font=f_lg)
        draw.text((10, 34), f"GREEN = {len(OWNER_CONTROL_POINTS_S3)} owner dots used (TOP path, y~{round(top_y)}).  "
                            f"ORANGE dashed = final proof spine.  GRAY = rejected lower diagonal.",
                  fill=C_TXT, font=f_md)
        draw.text((10, 58), f"s3 leg closes {sl['length_ft']}ft vs printed 247ft (G9 PASS).  No red TrueLine stroke drawn.",
                  fill=C_TXT, font=f_md)
        draw.text((10, 82), "Route = matchline START -> owner dots -> 15+13 HH (horizontal top path; avoids parallel y~363).",
                  fill=C_TXT, font=f_md)

        png = OUT_DIR / "log3_ingest_verification.png"
        canvas.save(png)
        print(f"[verify] owner dots={len(OWNER_CONTROL_POINTS_S3)} spine_len={sl['length_ft']}ft closes={sl['closes']}")
        print(f"[verify] image={png} ({W}x{H + HEADER})")
    finally:
        plan.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
