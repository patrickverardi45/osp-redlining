"""Rotation-safe crop + highlight rendering (pdf/ — ``fitz`` permitted here).

Given a callout's de-rotated ``bbox_display`` (display space), render a PNG crop of
the surrounding plan region with a highlight box drawn around the callout. This is
the evidence-card artifact for the WORKSPACE_PLAN_EVIDENCE_PANEL — NOT a world-map
overlay. PIL is used for the overlay (allowed; only ``fitz`` is boundary-restricted).
"""
from __future__ import annotations

import os
from typing import List, Optional

import fitz  # permitted only inside engine.redline_pdf_first.pdf
from PIL import Image, ImageDraw


def render_highlight_crop(page: "fitz.Page", bbox_display: List[float], out_path: str,
                          zoom: float = 3.5, pad: float = 190.0,
                          caption: Optional[str] = None) -> Optional[str]:
    """Render a highlighted crop around ``bbox_display`` (display coords). Returns the path."""
    if not bbox_display or len(bbox_display) != 4:
        return None
    x0, y0, x1, y1 = [float(v) for v in bbox_display]
    clip = fitz.Rect(x0 - pad, y0 - pad, x1 + pad, y1 + pad) & page.rect
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip,
                          colorspace=fitz.csRGB, alpha=False)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    d = ImageDraw.Draw(img)
    px0 = (x0 - clip.x0) * zoom
    py0 = (y0 - clip.y0) * zoom
    px1 = (x1 - clip.x0) * zoom
    py1 = (y1 - clip.y0) * zoom
    p = 11
    for w, c in ((9, (255, 255, 255)), (5, (220, 25, 25))):
        d.rectangle([px0 - p, py0 - p, px1 + p, py1 + p], outline=c, width=w)
    if caption:
        d.rectangle([0, 0, img.width, 34], fill=(255, 255, 255))
        d.text((8, 8), caption[:120], fill=(0, 0, 0))
    parent = os.path.dirname(out_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    img.save(out_path)
    return out_path


def _dashed_line(d, p0, p1, color, width=4, dash=16, gap=10):
    import math
    (x0, y0), (x1, y1) = p0, p1
    dx, dy = x1 - x0, y1 - y0
    dist = math.hypot(dx, dy) or 1.0
    ux, uy = dx / dist, dy / dist
    n = 0.0
    while n < dist:
        a = (x0 + ux * n, y0 + uy * n)
        b = (x0 + ux * min(n + dash, dist), y0 + uy * min(n + dash, dist))
        d.line([a, b], fill=color, width=width)
        n += dash + gap


def render_redline_overlay(page: "fitz.Page", elements: List[dict],
                           connector_points_display: List[List[float]], out_path: str,
                           zoom: float = 3.0, pad: float = 130.0,
                           caption: Optional[str] = None,
                           accent=(230, 140, 20), dashed: bool = True,
                           grey=(110, 110, 110)) -> Optional[str]:
    """Render a de-rotated overlay PNG: highlight each authored element bbox and
    draw the connector (DASHED for review candidates, SOLID for AP_ANCHORED) in
    ``accent`` through the ordered centroids. Display-space input only — no
    world/KMZ coords. Returns the path."""
    boxes = [e["bbox_display"] for e in elements if e.get("bbox_display") and len(e["bbox_display"]) == 4]
    if not boxes:
        return None
    xs = [b[0] for b in boxes] + [b[2] for b in boxes] + [p[0] for p in (connector_points_display or [])]
    ys = [b[1] for b in boxes] + [b[3] for b in boxes] + [p[1] for p in (connector_points_display or [])]
    clip = fitz.Rect(min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad) & page.rect
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip, colorspace=fitz.csRGB, alpha=False)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    d = ImageDraw.Draw(img)

    def to_px(x, y):
        return ((x - clip.x0) * zoom, (y - clip.y0) * zoom)

    for e in elements:
        b = e.get("bbox_display")
        if not b or len(b) != 4:
            continue
        col = grey if e.get("role") == "callout" else accent
        x0, y0 = to_px(b[0], b[1])
        x1, y1 = to_px(b[2], b[3])
        d.rectangle([x0 - 7, y0 - 7, x1 + 7, y1 + 7], outline=col, width=4)

    # connector + round markers (dashed=review, solid=anchored)
    pts = [to_px(x, y) for x, y in (connector_points_display or [])]
    for i in range(len(pts) - 1):
        if dashed:
            _dashed_line(d, pts[i], pts[i + 1], accent, width=5)
        else:
            d.line([pts[i], pts[i + 1]], fill=accent, width=5)
    for (cx, cy) in pts:
        d.ellipse([cx - 9, cy - 9, cx + 9, cy + 9], outline=(255, 255, 255), width=6)
        d.ellipse([cx - 9, cy - 9, cx + 9, cy + 9], outline=accent, width=3)

    if caption:
        d.rectangle([0, 0, img.width, 34], fill=(245, 248, 240) if not dashed else (255, 245, 230))
        d.text((8, 8), caption[:150], fill=(30, 110, 30) if not dashed else (150, 75, 0))
    parent = os.path.dirname(out_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    img.save(out_path)
    return out_path
