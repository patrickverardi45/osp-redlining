"""Rotation-aware PDF text-extraction primitives (Day 1).

Opens a plan PDF, inspects page rotation, and exposes text spans + authored
callout search with BOTH raw and DISPLAY-space bboxes (display via
``pdf.rotation``). Downstream selector/render consume display space only.

No selection logic lives here. ``fitz`` is imported here (allowed: pdf/ only).
"""
from __future__ import annotations

from typing import Any, Dict, List

import fitz  # PyMuPDF — permitted ONLY inside engine.redline_pdf_first.pdf

from . import rotation

DEFAULT_SHEET_OFFSET = 13  # 1-based page number = sheet + 13 (validated in Path 12)


def open_document(path: str) -> "fitz.Document":
    return fitz.open(path)


def page_index_for_sheet(sheet: int, sheet_offset: int = DEFAULT_SHEET_OFFSET) -> int:
    """0-based page index for a 1-based plan ``sheet`` (page = sheet + offset)."""
    return int(sheet) + int(sheet_offset) - 1


def get_page(doc: "fitz.Document", sheet: int,
             sheet_offset: int = DEFAULT_SHEET_OFFSET) -> "fitz.Page":
    return doc[page_index_for_sheet(sheet, sheet_offset)]


def page_info(page: "fitz.Page") -> Dict[str, Any]:
    w, h = rotation.display_size(page)
    return {
        "rotation": rotation.get_page_rotation(page),
        "display_width": w,
        "display_height": h,
    }


def extract_words(page: "fitz.Page") -> List[Dict[str, Any]]:
    """Every word with raw + de-rotated display bbox.

    PyMuPDF ``get_text("words")`` returns RAW (pre-rotation) rects; we attach a
    ``bbox_display`` via the rotation matrix so the selector never sees raw space.
    """
    out: List[Dict[str, Any]] = []
    for w in page.get_text("words"):
        # w = (x0, y0, x1, y1, text, block_no, line_no, word_no)
        raw = [float(w[0]), float(w[1]), float(w[2]), float(w[3])]
        out.append({
            "text": w[4],
            "bbox_raw": raw,
            "bbox_display": rotation.to_display_rect(raw, page),
            "block": int(w[5]), "line": int(w[6]), "word": int(w[7]),
        })
    return out


def extract_lines(page: "fitz.Page") -> List[str]:
    """Non-empty text lines (reading order) — useful for callout grammar later."""
    return [ln for ln in page.get_text("text").splitlines() if ln.strip()]


def extract_blocks(page: "fitz.Page") -> List[Dict[str, Any]]:
    """Authored text BLOCKS with raw + de-rotated display bbox.

    PyMuPDF groups stacked plan annotations (e.g. a ``STA 2+99 / 11"X11"X12" /
    FLOWER POT`` pedestal label) into a single block whose ``text`` is the upright
    label — exactly the authored unit the drop-terminal reader needs. ``fitz``
    block tuples are ``(x0, y0, x1, y1, text, block_no, block_type)``.
    """
    out: List[Dict[str, Any]] = []
    for b in page.get_text("blocks"):
        raw = [float(b[0]), float(b[1]), float(b[2]), float(b[3])]
        out.append({
            "text": b[4],
            "bbox_raw": raw,
            "bbox_display": rotation.to_display_rect(raw, page),
        })
    return out


def search_callout(page: "fitz.Page", query: str) -> List[Dict[str, Any]]:
    """Locate an authored callout string; return raw + display rects.

    Tries a curly-apostrophe variant too, since plan callouts vary
    (e.g. ``DIR. BORE (299')`` vs ``DIR. BORE (299’)``).
    """
    hits = page.search_for(query) or page.search_for(query.replace("'", "’"))
    results: List[Dict[str, Any]] = []
    for r in (hits or []):
        raw = [float(r.x0), float(r.y0), float(r.x1), float(r.y1)]
        results.append({
            "query": query,
            "bbox_raw": raw,
            "bbox_display": rotation.to_display_rect(raw, page),
        })
    return results
