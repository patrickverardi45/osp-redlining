"""Render a highlighted, clip-bounded evidence crop for a matched callout.

The plan region around the callout's DISPLAY-space bbox is rasterized (via
PlanPdf, rotation-safe) and the callout is outlined. The highlight is positioned
from the actual clip origin (the clip may be trimmed at the page edge). v2's own
renderer — no old-engine code.
"""
from __future__ import annotations

import os
from typing import Optional

from PIL import ImageDraw

from truelinev2.ingest.pdf import PlanPdf
from truelinev2.schema.models import Callout

# TrueLine overlay stroke color LAW (Patrick, 2026-06-11): every drawn
# redline/stroke/bore-path overlay is RED -- regardless of source conduit
# layer color, AUTO/REVIEW status, sheet, or proof type. Source PDF evidence
# is never recolored; only TrueLine's own drawn strokes are governed. All
# stroke renderers must reference THIS constant (test-locked).
REDLINE_STROKE_RGB = (220, 25, 25)


def _safe(name: str) -> str:
    return name.replace("+", "p").replace(" ", "_").replace("/", "-")


def _dashed(draw: "ImageDraw.ImageDraw", p0, p1, color, width: int,
            dash: float = 16.0, gap: float = 10.0) -> None:
    """Dashed segment (REVIEW-stroke convention; own implementation -- the v1
    overlay renderer donates STYLE only, never code)."""
    import math
    (x0, y0), (x1, y1) = p0, p1
    dist = math.hypot(x1 - x0, y1 - y0) or 1.0
    ux, uy = (x1 - x0) / dist, (y1 - y0) / dist
    n = 0.0
    while n < dist:
        a = (x0 + ux * n, y0 + uy * n)
        b = (x0 + ux * min(n + dash, dist), y0 + uy * min(n + dash, dist))
        draw.line([a, b], fill=color, width=width)
        n += dash + gap


def render_redline_stroke(plan: PlanPdf, bore_id: str, sheet: int, offset: int,
                          stroke_points, *, status: str, reason: str,
                          out_dir: str, evidence_bboxes=(), zoom: float = 2.0,
                          pad: float = 130.0) -> Optional[str]:
    """The M8.14 REDLINE STROKE overlay: a red polyline along the winning tick
    path (route-following at station-tick resolution) with circle markers,
    SOLID for AUTO placements / DASHED for REVIEW placements, grey boxes for
    matched-callout SUPPORTING EVIDENCE only (never called redlines), and a
    caption band naming the bore / status / reason. Refuses to draw without a
    real path (< 2 points) -- abstains never render."""
    pts = [tuple(p) for p in (stroke_points or ())]
    if len(pts) < 2:
        return None
    xs = [p[0] for p in pts] + [b[0] for b in evidence_bboxes] + [b[2] for b in evidence_bboxes]
    ys = [p[1] for p in pts] + [b[1] for b in evidence_bboxes] + [b[3] for b in evidence_bboxes]
    bbox = [min(xs), min(ys), max(xs), max(ys)]
    rendered = plan.render_clip(sheet, offset, bbox, zoom=zoom, pad=pad)
    if rendered is None:
        return None
    img, clip_x0, clip_y0 = rendered
    draw = ImageDraw.Draw(img)

    def px(p):
        return ((p[0] - clip_x0) * zoom, (p[1] - clip_y0) * zoom)

    grey = (110, 110, 110)
    red = REDLINE_STROKE_RGB
    for b in evidence_bboxes:  # supporting evidence highlights only
        (x0, y0), (x1, y1) = px((b[0], b[1])), px((b[2], b[3]))
        draw.rectangle([x0 - 6, y0 - 6, x1 + 6, y1 + 6], outline=grey, width=3)
    solid = status == "AUTO_SELECT"
    ppts = [px(p) for p in pts]
    for a, b in zip(ppts, ppts[1:]):
        if solid:
            draw.line([a, b], fill=red, width=6)
        else:
            _dashed(draw, a, b, red, width=6)
    for cx, cy in ppts:  # circle markers at every path point
        draw.ellipse([cx - 9, cy - 9, cx + 9, cy + 9], outline=(255, 255, 255), width=6)
        draw.ellipse([cx - 9, cy - 9, cx + 9, cy + 9], outline=red, width=3)

    cap = (f"{bore_id} · {status} ({'solid=auto' if solid else 'dashed=review'}) · "
           f"{reason} · redline stroke: route-following at station-tick resolution · "
           f"grey boxes = supporting callout evidence")
    draw.rectangle([0, 0, img.width, 30], fill=(255, 255, 255))
    draw.text((8, 8), cap[:180], fill=(20, 20, 20))

    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, _safe(f"{bore_id}_s{sheet}_redline_stroke.png"))
    img.save(path)
    return path


def render_sheet_context(plan: PlanPdf, sheet: int, offset: int, out_dir: str,
                         zoom: float = 1.0) -> Optional[str]:
    """Full-sheet CONTEXT render (no highlights) -- reuses ``render_clip`` with a
    page-sized clip (``render_clip`` intersects the clip with ``page.rect``).
    Review/demo context only; never placement evidence."""
    rendered = plan.render_clip(sheet, offset, [0.0, 0.0, 1e7, 1e7], zoom=zoom, pad=0.0)
    if rendered is None:
        return None
    img, _, _ = rendered
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"sheet_{int(sheet)}.png")
    img.save(path)
    return path


def render_evidence_crop(plan: PlanPdf, bore_id: str, callout: Callout, out_dir: str,
                         offset: int, zoom: float = 3.5, pad: float = 160.0) -> Optional[str]:
    if not callout.bbox:
        return None
    rendered = plan.render_clip(callout.sheet, offset, callout.bbox, zoom=zoom, pad=pad)
    if rendered is None:
        return None
    img, clip_x0, clip_y0 = rendered
    draw = ImageDraw.Draw(img)
    b = callout.bbox
    px0 = (b[0] - clip_x0) * zoom
    py0 = (b[1] - clip_y0) * zoom
    px1 = (b[2] - clip_x0) * zoom
    py1 = (b[3] - clip_y0) * zoom
    inset = 10
    # white halo then red box, so the highlight reads on any background
    for width, color in ((9, (255, 255, 255)), (5, (220, 25, 25))):
        draw.rectangle([px0 - inset, py0 - inset, px1 + inset, py1 + inset],
                       outline=color, width=width)
    os.makedirs(out_dir, exist_ok=True)
    fn = _safe(f"{bore_id}_s{callout.sheet}_{callout.from_sta}-{callout.to_sta}.png")
    path = os.path.join(out_dir, fn)
    img.save(path)
    return path
