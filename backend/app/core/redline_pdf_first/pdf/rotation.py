"""Real PyMuPDF rotation / display-coordinate helpers.

Purpose: convert a page's RAW (pre-rotation) text coordinates — what
``get_text`` / ``search_for`` return — into DISPLAY (post-rotation) coordinates
that match what is rendered. This is the fix for the 270deg "callout absent
from the text layer" class of bug (Path-12 root cause): without applying
``page.rotation_matrix`` a station-band filter drops/mislocates authored callouts.

No Brenham-specific constants. ``fitz`` is imported here (allowed: pdf/ only).
"""
from __future__ import annotations

from typing import List, Tuple

import fitz  # PyMuPDF — permitted ONLY inside engine.redline_pdf_first.pdf


def get_page_rotation(page: "fitz.Page") -> int:
    """Page rotation in degrees (0, 90, 180, 270)."""
    return int(page.rotation or 0)


def rotation_matrix(page: "fitz.Page") -> "fitz.Matrix":
    """Matrix mapping RAW (un-rotated) coords -> DISPLAYED coords."""
    return page.rotation_matrix


def derotation_matrix(page: "fitz.Page") -> "fitz.Matrix":
    """Inverse: DISPLAYED coords -> RAW coords."""
    return page.derotation_matrix


def display_size(page: "fitz.Page") -> Tuple[float, float]:
    """(width, height) of the page AS DISPLAYED (rotation applied)."""
    r = page.rect
    return (float(r.width), float(r.height))


def _as_rect(rect_like) -> "fitz.Rect":
    if isinstance(rect_like, fitz.Rect):
        return rect_like
    return fitz.Rect(float(rect_like[0]), float(rect_like[1]),
                     float(rect_like[2]), float(rect_like[3]))


def to_display_rect(raw_rect, page: "fitz.Page") -> List[float]:
    """Transform a RAW-space rect into DISPLAY space; return [x0,y0,x1,y1]."""
    r = fitz.Rect(_as_rect(raw_rect) * rotation_matrix(page))
    r.normalize()
    return [float(r.x0), float(r.y0), float(r.x1), float(r.y1)]


def to_raw_rect(display_rect, page: "fitz.Page") -> List[float]:
    """Inverse of :func:`to_display_rect`: DISPLAY-space rect -> RAW [x0,y0,x1,y1]."""
    r = fitz.Rect(_as_rect(display_rect) * derotation_matrix(page))
    r.normalize()
    return [float(r.x0), float(r.y0), float(r.x1), float(r.y1)]


def to_display_point(raw_point, page: "fitz.Page") -> List[float]:
    """Transform a single RAW-space point into DISPLAY space; return ``[x, y]``.

    Point analog of :func:`to_display_rect`, using the SAME ``rotation_matrix`` so
    vector-layer vertices (``page.get_drawings()`` returns RAW coords) de-rotate
    identically to text bboxes. Essential for rotation-safe (270deg) path tracing.
    """
    p = fitz.Point(float(raw_point[0]), float(raw_point[1])) * rotation_matrix(page)
    return [float(p.x), float(p.y)]
