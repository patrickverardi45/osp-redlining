"""PDF reader — v2's own thin wrapper over PyMuPDF (fitz). The only module that
imports fitz. Exposes text lines, callout search, and clip rasterization.

Rotation-safe: ``search`` returns DISPLAY-space rects (raw text coords mapped
through ``page.rotation_matrix``) so they line up with what ``get_pixmap``
renders. Brenham plan pages are rotated 270deg; using raw coords as a clip would
land the crop in the wrong place. No selection/matching logic here.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

import fitz  # PyMuPDF — standard PDF engine (infrastructure, not TrueLine code)
from PIL import Image


class PlanPdf:
    def __init__(self, path: str):
        self.path = path
        self._doc = fitz.open(path)

    @property
    def page_count(self) -> int:
        return self._doc.page_count

    def page_index(self, sheet: int, offset: int) -> int:
        """0-based page index for a 1-based plan sheet: page = sheet + offset - 1."""
        return int(sheet) + int(offset) - 1

    def _page(self, sheet: int, offset: int):
        idx = self.page_index(sheet, offset)
        if not (0 <= idx < self.page_count):
            return None
        return self._doc[idx]

    def page_rotation(self, sheet: int, offset: int) -> int:
        page = self._page(sheet, offset)
        return int(page.rotation or 0) if page is not None else 0

    def lines(self, sheet: int, offset: int) -> List[str]:
        page = self._page(sheet, offset)
        if page is None:
            return []
        return [ln for ln in page.get_text("text").splitlines() if ln.strip()]

    def search(self, sheet: int, offset: int, text: str) -> List[List[float]]:
        """Locate authored text; return DISPLAY-space [x0,y0,x1,y1] rects (rotation
        applied so they match the rendered pixmap)."""
        page = self._page(sheet, offset)
        if page is None:
            return []
        hits = page.search_for(text) or page.search_for(text.replace("'", "’"))
        out: List[List[float]] = []
        for r in (hits or []):
            d = fitz.Rect(r) * page.rotation_matrix  # raw -> display
            d.normalize()
            out.append([float(d.x0), float(d.y0), float(d.x1), float(d.y1)])
        return out

    def render_clip(self, sheet: int, offset: int, bbox_display: List[float],
                    zoom: float = 3.5, pad: float = 160.0
                    ) -> Optional[Tuple[Image.Image, float, float]]:
        """Rasterize the padded region around a DISPLAY-space bbox. Returns
        (PIL image, clip_x0, clip_y0) so the caller can position overlays."""
        page = self._page(sheet, offset)
        if page is None or not bbox_display:
            return None
        x0, y0, x1, y1 = [float(v) for v in bbox_display]
        clip = fitz.Rect(x0 - pad, y0 - pad, x1 + pad, y1 + pad) & page.rect
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip,
                              colorspace=fitz.csRGB, alpha=False)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        return img, float(clip.x0), float(clip.y0)

    def close(self) -> None:
        self._doc.close()
