"""PDF Extraction E1 — raw text + vector primitive extraction.

Deterministic, auditable per-page extraction of two primitive layers from
an engineering PDF using PyMuPDF (``fitz``):

1. text_blocks — every text-layer block with its bounding box, font, size,
                 color, and the block index assigned by PyMuPDF.
2. vector_paths — every vector drawing (lines, curves, rects, polygons)
                 with its point operators, stroke color/width, fill color,
                 and bounding box.

This is the **raw primitives** layer of the extraction-first pivot.
Downstream layers (label detection, route candidate detection, matchline
detection, station-tick detection) consume this output as input.  This
module makes NO classification decisions and emits NO suggestions — only
the raw primitives extracted from the PDF.

Hard contracts (mirrors ``pdf_plan_index.py`` doctrine):

* Pure helper.  No STATE, no env reads, no main-module imports, no
  caching at this layer (caller manages disk cache).
* PyMuPDF (``import fitz``) imported LAZILY so test envs without PyMuPDF
  can still import this module; absence surfaces as ``PdfExtractionError``
  which the route handler converts to 500.
* No OCR.  Text comes from the PDF text layer only.  If the layer is
  empty for a page, ``text_layer_available`` is False; downstream code
  must label this as a raster page rather than claim "no text".
* Output is **primitive-grade**, not authoritative.  No interpretation,
  no classification, no inference — just the bytes PyMuPDF returns,
  normalized to a deterministic JSON shape.
* Deterministic: same PDF bytes + same page_index → byte-identical JSON
  output (modulo wall-clock timestamps which the caller adds).
* Bounded (per page):
    - text_blocks  capped at _TEXT_BLOCKS_CAP (default 5000)
    - vector_paths capped at _VECTOR_PATHS_CAP (default 10000)
    - per-block text length capped at _BLOCK_TEXT_CAP (default 4000)
    - per-path points capped at _PATH_POINTS_CAP (default 2000)
    - if any cap is hit, the corresponding ``*_truncated`` flag is True
      so downstream code can flag the page for operator review
* Coordinate system: PDF native units (points = 1/72 inch).  Origin is
  top-left after PyMuPDF's default y-axis flip; bboxes are (x0, y0, x1, y1)
  with y0 < y1.  Floats rounded to 3 decimal places for stable output.
* No AI/LLM calls.  Pure regex + PyMuPDF geometry only.
* No subprocess bounding in v1.  Step 2A's in-process PyMuPDF call site
  has been stable in production since 2026-05-26; if a pathological PDF
  surfaces here, follow the PE.2/PE.4 subprocess pattern in a v2 ship.

Schema version: pdf-extraction-raw-1.

Authoritative design: pivot reset plan, §3 "New extraction-first
architecture" (2026-05-26).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, Final, List, Optional, Tuple


SCHEMA_VERSION: Final[str] = "pdf-extraction-raw-1"

# Per-page caps.  These match the operational budget for a single
# engineering plan_sheet page; if a real Kelly PDF exceeds them, the
# truncation flag surfaces in the response so the operator notices.
_TEXT_BLOCKS_CAP: Final[int] = 5000
_VECTOR_PATHS_CAP: Final[int] = 10000
_BLOCK_TEXT_CAP: Final[int] = 4000
_PATH_POINTS_CAP: Final[int] = 2000

# Float precision.  3 decimals = ~0.001 PDF points = ~0.0003 inches,
# well below any meaningful drawing resolution.  Stable across PyMuPDF
# versions because Python's round() is half-to-even on binary doubles.
_FLOAT_DECIMALS: Final[int] = 3


class PdfExtractionError(Exception):
    """Raised on missing PyMuPDF, missing file, or PDF open failure."""


# ---------------------------------------------------------------------------
# Coercion helpers (deterministic, stable across runs)
# ---------------------------------------------------------------------------

def _r(v: Any) -> float:
    """Round a numeric to _FLOAT_DECIMALS.  Returns 0.0 on non-numeric."""
    try:
        return round(float(v), _FLOAT_DECIMALS)
    except (TypeError, ValueError):
        return 0.0


def _bbox_from_seq(seq: Any) -> List[float]:
    """Coerce a 4-tuple/list/Rect to [x0, y0, x1, y1] floats."""
    try:
        return [_r(seq[0]), _r(seq[1]), _r(seq[2]), _r(seq[3])]
    except (TypeError, IndexError):
        return [0.0, 0.0, 0.0, 0.0]


def _color_to_hex(color: Any) -> Optional[str]:
    """Convert a PyMuPDF color (float tuple in [0,1]^3 or [0,1]^4, or int
    sRGB) to ``#RRGGBB`` lowercase hex.  Returns None for transparent /
    unspecified / malformed colors.

    PyMuPDF returns:
      - text span color as a 24-bit int sRGB (e.g. 0xFF0000 == red)
      - drawing stroke/fill as a 3-float tuple normalized to [0, 1]
    """
    if color is None:
        return None
    if isinstance(color, int):
        if color < 0 or color > 0xFFFFFF:
            return None
        return f"#{color:06x}"
    if isinstance(color, (tuple, list)):
        if len(color) < 3:
            return None
        try:
            r = max(0, min(255, int(round(float(color[0]) * 255))))
            g = max(0, min(255, int(round(float(color[1]) * 255))))
            b = max(0, min(255, int(round(float(color[2]) * 255))))
        except (TypeError, ValueError):
            return None
        return f"#{r:02x}{g:02x}{b:02x}"
    return None


def _path_items_hash(items: List[Any]) -> str:
    """Stable short hash of a vector path's items list for tie-breaking
    deterministic sort order when bbox is identical."""
    h = hashlib.sha1()
    for it in items:
        h.update(repr(it).encode("utf-8"))
    return h.hexdigest()[:12]


def _clamp_text(s: str, cap: int) -> str:
    if len(s) <= cap:
        return s
    return s[:cap]


# ---------------------------------------------------------------------------
# Text block extraction
# ---------------------------------------------------------------------------

def _extract_text_blocks(page: Any) -> Tuple[List[Dict[str, Any]], bool, bool]:
    """Return (blocks, text_layer_available, truncated).

    ``blocks`` is a deterministic-ordered list of dicts; each block flattens
    PyMuPDF's nested block/line/span structure into one record per
    block (top-level) plus aggregated text.  Spans are NOT preserved
    individually in v1 — that level of detail is deferred to E2 if a
    detection rule needs span-level font/style differentiation.
    """
    try:
        td = page.get_text("dict")
    except Exception:
        return [], False, False
    if not isinstance(td, dict):
        return [], False, False
    raw_blocks = td.get("blocks") or []

    out: List[Dict[str, Any]] = []
    text_layer_available = False
    truncated = False

    for b in raw_blocks:
        if len(out) >= _TEXT_BLOCKS_CAP:
            truncated = True
            break
        if not isinstance(b, dict):
            continue
        # PyMuPDF block type: 0 == text, 1 == image.  Image blocks have no
        # textual content; skip them in the text layer.
        if int(b.get("type", -1)) != 0:
            continue

        # Aggregate span text + capture representative font/size/color from
        # the first span of the first line (good-enough for v1; full span
        # detail deferred to E2).
        lines = b.get("lines") or []
        if not lines:
            continue
        text_parts: List[str] = []
        rep_font: Optional[str] = None
        rep_size: Optional[float] = None
        rep_color: Optional[str] = None

        for line in lines:
            if not isinstance(line, dict):
                continue
            spans = line.get("spans") or []
            line_text_parts: List[str] = []
            for sp in spans:
                if not isinstance(sp, dict):
                    continue
                t = sp.get("text")
                if isinstance(t, str) and t:
                    line_text_parts.append(t)
                    if rep_font is None:
                        f = sp.get("font")
                        if isinstance(f, str) and f:
                            rep_font = f
                        sz = sp.get("size")
                        if isinstance(sz, (int, float)):
                            rep_size = _r(sz)
                        rep_color = _color_to_hex(sp.get("color"))
            if line_text_parts:
                text_parts.append(" ".join(line_text_parts))

        text = "\n".join(text_parts).strip()
        if not text:
            continue
        text_layer_available = True

        bbox = _bbox_from_seq(b.get("bbox") or (0, 0, 0, 0))
        block_no = b.get("number")
        try:
            block_no_int = int(block_no) if block_no is not None else len(out)
        except (TypeError, ValueError):
            block_no_int = len(out)

        out.append({
            "text": _clamp_text(text, _BLOCK_TEXT_CAP),
            "bbox": bbox,
            "font": rep_font,
            "size": rep_size,
            "color": rep_color,
            "block_no": block_no_int,
        })

    # Deterministic ordering: top-to-bottom, then left-to-right, then by
    # block_no for stable tie-break.  Sort key is rounded to 1 decimal
    # place so micro-jitter in PyMuPDF version updates doesn't reshuffle.
    out.sort(key=lambda r: (
        round(r["bbox"][1], 1),
        round(r["bbox"][0], 1),
        r["block_no"],
    ))
    return out, text_layer_available, truncated


# ---------------------------------------------------------------------------
# Vector path extraction
# ---------------------------------------------------------------------------

def _normalize_path_items(items: Any) -> Tuple[List[List[Any]], bool]:
    """PyMuPDF item shapes:
        ("l", Point, Point)              — line from p1 to p2
        ("c", Point, Point, Point, Point) — bezier curve
        ("re", Rect, int_orientation)    — rectangle
        ("qu", Quad)                     — quadrilateral
    Each Point is a fitz.Point or a (x, y) tuple; Rect is (x0,y0,x1,y1).

    Returns (normalized_items, truncated) where each item is a JSON-safe
    list ``[op, *coord_lists]`` and a points cap prevents pathological
    paths (e.g. raster-as-vector traces) from inflating the response.
    """
    out: List[List[Any]] = []
    truncated = False
    point_count = 0

    def _pt(p: Any) -> List[float]:
        try:
            return [_r(p[0]), _r(p[1])]
        except (TypeError, IndexError):
            try:
                return [_r(getattr(p, "x", 0)), _r(getattr(p, "y", 0))]
            except Exception:
                return [0.0, 0.0]

    if not items:
        return out, False

    for it in items:
        if not isinstance(it, (tuple, list)) or len(it) < 1:
            continue
        op = it[0]
        if not isinstance(op, str):
            continue
        if point_count >= _PATH_POINTS_CAP:
            truncated = True
            break
        try:
            if op == "l" and len(it) >= 3:
                out.append([op, _pt(it[1]), _pt(it[2])])
                point_count += 2
            elif op == "c" and len(it) >= 5:
                out.append([op, _pt(it[1]), _pt(it[2]), _pt(it[3]), _pt(it[4])])
                point_count += 4
            elif op == "re" and len(it) >= 2:
                rect = _bbox_from_seq(it[1])
                orient = 0
                if len(it) >= 3:
                    try:
                        orient = int(it[2])
                    except (TypeError, ValueError):
                        orient = 0
                out.append([op, rect, orient])
                point_count += 4
            elif op == "qu" and len(it) >= 2:
                # Quad has 4 points; PyMuPDF Quad exposes ul/ur/ll/lr or
                # is indexable as 4 points.
                q = it[1]
                try:
                    pts = [_pt(q[i]) for i in range(4)]
                except Exception:
                    pts = [[0.0, 0.0]] * 4
                out.append([op, *pts])
                point_count += 4
            else:
                # Unknown op — preserve op + rest as flat coercion best-effort.
                out.append([op] + [_pt(p) for p in it[1:5]])
                point_count += min(4, max(0, len(it) - 1))
        except Exception:
            continue

    return out, truncated


def _extract_vector_paths(page: Any) -> Tuple[List[Dict[str, Any]], bool]:
    """Return (paths, truncated).

    Each path record:
        {
          "items":  [...],           # normalized op list
          "stroke_color": "#rrggbb",  # or null
          "stroke_width": float,      # or null
          "fill_color":   "#rrggbb",  # or null
          "rule":        "stroke"|"fill"|"both"|"unknown",
          "bbox":        [x0,y0,x1,y1],
          "items_hash":  "abc123...", # deterministic tie-break
        }
    """
    try:
        raw = page.get_drawings() or []
    except Exception:
        return [], False
    if not isinstance(raw, list):
        return [], False

    out: List[Dict[str, Any]] = []
    truncated = False

    for d in raw:
        if len(out) >= _VECTOR_PATHS_CAP:
            truncated = True
            break
        if not isinstance(d, dict):
            continue

        items_raw = d.get("items") or []
        items, items_truncated = _normalize_path_items(items_raw)
        if not items:
            continue
        if items_truncated:
            # Per-path truncation rolls up to page-level truncation flag.
            truncated = True

        stroke_color = _color_to_hex(d.get("color"))
        fill_color = _color_to_hex(d.get("fill"))
        stroke_width = d.get("width")
        try:
            stroke_width_f = _r(stroke_width) if stroke_width is not None else None
        except Exception:
            stroke_width_f = None

        # PyMuPDF "type" key is one of "s" (stroke), "f" (fill), "fs"
        # (both), "c" (clip).  Translate to readable form.
        ptype = d.get("type")
        if ptype == "s":
            rule = "stroke"
        elif ptype == "f":
            rule = "fill"
        elif ptype == "fs":
            rule = "both"
        elif ptype == "c":
            rule = "clip"
        else:
            rule = "unknown"

        rect = d.get("rect")
        if rect is None:
            # Compute bbox from items if PyMuPDF didn't supply one.
            xs: List[float] = []
            ys: List[float] = []
            for it in items:
                for p in it[1:]:
                    if isinstance(p, list) and len(p) == 2:
                        xs.append(p[0])
                        ys.append(p[1])
                    elif isinstance(p, list) and len(p) == 4:
                        # rect from "re" op
                        xs.extend([p[0], p[2]])
                        ys.extend([p[1], p[3]])
            if xs and ys:
                bbox = [_r(min(xs)), _r(min(ys)), _r(max(xs)), _r(max(ys))]
            else:
                bbox = [0.0, 0.0, 0.0, 0.0]
        else:
            bbox = _bbox_from_seq(rect)

        out.append({
            "items": items,
            "stroke_color": stroke_color,
            "stroke_width": stroke_width_f,
            "fill_color": fill_color,
            "rule": rule,
            "bbox": bbox,
            "items_hash": _path_items_hash(items),
        })

    # Deterministic order: top-to-bottom (y0), then left-to-right (x0),
    # then items_hash for stable tie-break on overlapping paths.
    out.sort(key=lambda r: (
        round(r["bbox"][1], 1),
        round(r["bbox"][0], 1),
        r["items_hash"],
    ))
    return out, truncated


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------

def extract_page_raw(pdf_path: Path, page_index: int) -> Dict[str, Any]:
    """Extract raw text + vector primitives for ONE page of a PDF.

    Args:
        pdf_path:    path to source PDF (must exist + be readable).
        page_index:  0-indexed page within the PDF.

    Returns:
        Dict matching schema ``pdf-extraction-raw-1``:
            {
              "schema_version": "pdf-extraction-raw-1",
              "page_index": int,
              "page_number": int (1-indexed),
              "page_size_px": [W, H] (PDF points; native unit),
              "page_rotation": int (0, 90, 180, 270),
              "text_blocks": [ ... ],
              "text_blocks_truncated": bool,
              "vector_paths": [ ... ],
              "vector_paths_truncated": bool,
              "text_layer_available": bool,
              "extraction_caps": {
                "text_blocks_cap":  int,
                "vector_paths_cap": int,
                "block_text_cap":   int,
                "path_points_cap":  int,
              },
              "page_load_error": Optional[str],
            }

    Raises:
        PdfExtractionError on missing file, missing PyMuPDF, or PDF open
        failure.  Per-page exceptions (load_page / get_text / get_drawings)
        are caught and reported in ``page_load_error`` so a single bad
        page does not raise — the response surfaces the error in-band.
    """
    if not isinstance(pdf_path, Path):
        pdf_path = Path(pdf_path)
    if not pdf_path.is_file():
        raise PdfExtractionError(f"PDF not found: {pdf_path}")

    try:
        import fitz  # PyMuPDF
    except ImportError as e:
        raise PdfExtractionError(f"PyMuPDF unavailable: {e}") from e

    try:
        doc = fitz.open(str(pdf_path))
    except Exception as e:
        raise PdfExtractionError(
            f"failed to open PDF: {type(e).__name__}: {e}"
        ) from e

    try:
        page_count = int(getattr(doc, "page_count", 0) or 0)
        if page_index < 0 or page_index >= page_count:
            return _empty_page_record(
                page_index=page_index,
                page_size_px=[0.0, 0.0],
                page_rotation=0,
                page_load_error=(
                    f"page_index {page_index} out of range "
                    f"(pdf has {page_count} pages)"
                ),
            )

        try:
            page = doc.load_page(page_index)
        except Exception as e:
            return _empty_page_record(
                page_index=page_index,
                page_size_px=[0.0, 0.0],
                page_rotation=0,
                page_load_error=f"load_page failed: {type(e).__name__}: {e}",
            )

        try:
            rect = page.rect
            page_size_px = [_r(rect.width), _r(rect.height)]
        except Exception:
            page_size_px = [0.0, 0.0]
        try:
            page_rotation = int(getattr(page, "rotation", 0) or 0)
        except Exception:
            page_rotation = 0

        text_blocks, text_layer_available, text_truncated = _extract_text_blocks(page)
        vector_paths, vector_truncated = _extract_vector_paths(page)

        return {
            "schema_version": SCHEMA_VERSION,
            "page_index": page_index,
            "page_number": page_index + 1,
            "page_size_px": page_size_px,
            "page_rotation": page_rotation,
            "text_blocks": text_blocks,
            "text_blocks_truncated": text_truncated,
            "vector_paths": vector_paths,
            "vector_paths_truncated": vector_truncated,
            "text_layer_available": text_layer_available,
            "extraction_caps": {
                "text_blocks_cap":  _TEXT_BLOCKS_CAP,
                "vector_paths_cap": _VECTOR_PATHS_CAP,
                "block_text_cap":   _BLOCK_TEXT_CAP,
                "path_points_cap":  _PATH_POINTS_CAP,
            },
            "page_load_error": None,
        }
    finally:
        try:
            doc.close()
        except Exception:
            pass


def _empty_page_record(
    *,
    page_index: int,
    page_size_px: List[float],
    page_rotation: int,
    page_load_error: Optional[str],
) -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "page_index": page_index,
        "page_number": page_index + 1,
        "page_size_px": page_size_px,
        "page_rotation": page_rotation,
        "text_blocks": [],
        "text_blocks_truncated": False,
        "vector_paths": [],
        "vector_paths_truncated": False,
        "text_layer_available": False,
        "extraction_caps": {
            "text_blocks_cap":  _TEXT_BLOCKS_CAP,
            "vector_paths_cap": _VECTOR_PATHS_CAP,
            "block_text_cap":   _BLOCK_TEXT_CAP,
            "path_points_cap":  _PATH_POINTS_CAP,
        },
        "page_load_error": page_load_error,
    }
