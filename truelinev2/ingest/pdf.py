"""PDF reader — v2's own thin wrapper over PyMuPDF (fitz). The only module that
imports fitz. Rotation-safe: text + vector coords are mapped raw->display via
``page.rotation_matrix`` so they line up with what ``get_pixmap`` renders.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

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
        return int(sheet) + int(offset) - 1

    def _page(self, sheet: int, offset: int):
        idx = self.page_index(sheet, offset)
        if not (0 <= idx < self.page_count):
            return None
        return self._doc[idx]

    def page_rotation(self, sheet: int, offset: int) -> int:
        page = self._page(sheet, offset)
        return int(page.rotation or 0) if page is not None else 0

    def page_bounds_display(self, sheet: int, offset: int
                            ) -> Optional[Tuple[float, float, float, float]]:
        """DISPLAY-space bounding rectangle of a page (x0, y0, x1, y1), rotation-mapped exactly the way
        text/vector coords are (so it lines up with stroke/render coordinates), or None if the page index
        is out of range. Read-only geometry — opens NO pixmap, rasterizes nothing. Lets a caller validate
        that supplied display-space points actually fall on the page."""
        page = self._page(sheet, offset)
        if page is None:
            return None
        rot = page.rotation_matrix
        r = page.rect
        corners = [fitz.Point(r.x0, r.y0) * rot, fitz.Point(r.x1, r.y0) * rot,
                   fitz.Point(r.x1, r.y1) * rot, fitz.Point(r.x0, r.y1) * rot]
        xs = [p.x for p in corners]
        ys = [p.y for p in corners]
        return (float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys)))

    def render_page_png(self, sheet: int, offset: int, *, zoom: float = 2.0) -> Optional[bytes]:
        """Full-page PNG raster of ONE page (the uploaded plan AS-IS — NO overlay, NO redline drawn), as
        in-memory bytes for browser display + human source-anchor capture. Returns None if the page index
        is out of range. Writes nothing to disk. The pixmap covers the page's display-space rect scaled by
        ``zoom``, so a raster pixel maps linearly back onto ``page_bounds_display`` for click capture."""
        page = self._page(sheet, offset)
        if page is None:
            return None
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), colorspace=fitz.csRGB, alpha=False)
        return pix.tobytes("png")

    def text_by_index(self, idx: int) -> str:
        if not (0 <= idx < self.page_count):
            return ""
        return self._doc[idx].get_text("text")

    def lines(self, sheet: int, offset: int) -> List[str]:
        page = self._page(sheet, offset)
        if page is None:
            return []
        return [ln for ln in page.get_text("text").splitlines() if ln.strip()]

    def words(self, sheet: int, offset: int) -> List[Dict[str, Any]]:
        page = self._page(sheet, offset)
        if page is None:
            return []
        rot = page.rotation_matrix
        out: List[Dict[str, Any]] = []
        for w in page.get_text("words"):
            d = fitz.Rect(float(w[0]), float(w[1]), float(w[2]), float(w[3])) * rot
            d.normalize()
            # "block" = PyMuPDF text-block id (M8.14: drawn route-tick LADDERS
            # group into all-tick blocks; callout/note station tokens share
            # blocks with alphabetic words -- the clean-tick classifier key)
            out.append({"text": w[4], "x0": float(d.x0), "y0": float(d.y0),
                        "x1": float(d.x1), "y1": float(d.y1),
                        "xc": float((d.x0 + d.x1) / 2.0), "yc": float((d.y0 + d.y1) / 2.0),
                        "block": int(w[5])})
        return out

    def vector_segments(self, sheet: int, offset: int) -> List[Dict[str, Any]]:
        """Every vector drawing path as a DISPLAY-space bbox + its CAD layer name.
        Used by positional dialects to isolate geometry by layer (e.g. a proposed
        directional-bore layer) instead of guessing by style."""
        page = self._page(sheet, offset)
        if page is None:
            return []
        rot = page.rotation_matrix
        out: List[Dict[str, Any]] = []
        for d in page.get_drawings():
            r = d.get("rect")
            if r is None:
                continue
            corners = [fitz.Point(r.x0, r.y0) * rot, fitz.Point(r.x1, r.y0) * rot,
                       fitz.Point(r.x1, r.y1) * rot, fitz.Point(r.x0, r.y1) * rot]
            xs = [p.x for p in corners]
            ys = [p.y for p in corners]
            out.append({"layer": d.get("layer"), "x0": min(xs), "y0": min(ys),
                        "x1": max(xs), "y1": max(ys),
                        "xc": (min(xs) + max(xs)) / 2.0, "yc": (min(ys) + max(ys)) / 2.0,
                        "width": float(d.get("width") or 0.0)})
        return out

    def line_items(self, sheet: int, offset: int) -> List[Dict[str, Any]]:
        """Per-drawing vector DETAIL (M8.14.b.2 public-API seam): CAD layer, draw
        type, fill/stroke color, DISPLAY-space bbox, and every straight-line item
        mapped to display space (rects contribute their 4 edges). Lets the
        structure-position solver trace LEADER LINES from a label box to the
        drawn symbol instead of trusting leader-offset label text. Curves are
        ignored deliberately -- leaders and label boxes are straight-line work."""
        page = self._page(sheet, offset)
        if page is None:
            return []
        rot = page.rotation_matrix

        def pt(p) -> Tuple[float, float]:
            q = fitz.Point(p) * rot
            return (float(q.x), float(q.y))

        out: List[Dict[str, Any]] = []
        for d in page.get_drawings():
            r = d.get("rect")
            if r is None:
                continue
            corners = [fitz.Point(r.x0, r.y0) * rot, fitz.Point(r.x1, r.y0) * rot,
                       fitz.Point(r.x1, r.y1) * rot, fitz.Point(r.x0, r.y1) * rot]
            xs = [p.x for p in corners]
            ys = [p.y for p in corners]
            lines: List[Tuple[float, float, float, float]] = []
            for it in d.get("items") or ():
                if it[0] == "l":
                    (ax, ay), (bx, by) = pt(it[1]), pt(it[2])
                    lines.append((ax, ay, bx, by))
                elif it[0] == "re":
                    rr = it[1]
                    cs = [pt((rr.x0, rr.y0)), pt((rr.x1, rr.y0)),
                          pt((rr.x1, rr.y1)), pt((rr.x0, rr.y1))]
                    for a, b in zip(cs, cs[1:] + cs[:1]):
                        lines.append((a[0], a[1], b[0], b[1]))
            out.append({"layer": d.get("layer"), "type": d.get("type"),
                        "fill": d.get("fill"), "color": d.get("color"),
                        "x0": min(xs), "y0": min(ys), "x1": max(xs), "y1": max(ys),
                        "xc": (min(xs) + max(xs)) / 2.0,
                        "yc": (min(ys) + max(ys)) / 2.0,
                        "lines": lines})
        return out

    def search(self, sheet: int, offset: int, text: str) -> List[List[float]]:
        page = self._page(sheet, offset)
        if page is None:
            return []
        hits = page.search_for(text) or page.search_for(text.replace("'", "’"))
        out: List[List[float]] = []
        for r in (hits or []):
            d = fitz.Rect(r) * page.rotation_matrix
            d.normalize()
            out.append([float(d.x0), float(d.y0), float(d.x1), float(d.y1)])
        return out

    def render_clip(self, sheet: int, offset: int, bbox_display: List[float],
                    zoom: float = 3.5, pad: float = 160.0
                    ) -> Optional[Tuple[Image.Image, float, float]]:
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
