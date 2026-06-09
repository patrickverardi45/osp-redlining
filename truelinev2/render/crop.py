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


def _safe(name: str) -> str:
    return name.replace("+", "p").replace(" ", "_").replace("/", "-")


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
