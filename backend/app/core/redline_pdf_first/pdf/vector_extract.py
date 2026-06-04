"""Rotation-safe VECTOR-layer extraction (``page.get_drawings``) — page-space only.

Exposes the authored vector linework as de-rotated DISPLAY-space segments AND as
path-level polylines (the authored unit PyMuPDF groups a stroked polyline into),
each with a ``source_ref`` back to the originating drawing. This is the read-only
primitive the bore-path tracer consumes.

NO selection logic, NO identity binding, NO color filtering, NO proximity here —
this module only converts ``get_drawings()`` output into page-space geometry.
``fitz`` is imported here (allowed: ``pdf/`` only); points de-rotate through
``rotation.to_display_point`` so 270deg sheets are handled like the text layer.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from . import rotation

_HORIZONTAL_TOL = 2.0  # |dy| <= this (display units) counts as a horizontal run leg


def _item_endpoints(item) -> List:
    """Raw endpoints contributed by one ``get_drawings`` item. Curves contribute
    their CHORD endpoints (verbatim authored anchor points; controls omitted)."""
    kind = item[0]
    if kind == "l":
        return [item[1], item[2]]
    if kind == "c":                       # bezier: (start, c1, c2, end)
        return [item[1], item[4]]
    if kind == "re":                      # rectangle -> closed corner loop
        r = item[1]
        return [(r.x0, r.y0), (r.x1, r.y0), (r.x1, r.y1), (r.x0, r.y1), (r.x0, r.y0)]
    if kind == "qu":                      # quad -> closed corner loop
        q = item[1]
        return [q.ul, q.ur, q.lr, q.ll, q.ul]
    return []


def _color_key(color) -> Optional[List[float]]:
    if not color:
        return None
    try:
        return [round(float(c), 4) for c in color]
    except Exception:
        return None


def extract_segments(page) -> List[Dict[str, Any]]:
    """Every authored line/curve as a de-rotated DISPLAY-space segment.

    Each: ``{p0, p1, color, width, kind, source_ref:{draw_index,item_index}}``.
    Page-space only; no world/KMZ coords. Never raises (returns what it parsed).
    """
    out: List[Dict[str, Any]] = []
    try:
        draws = page.get_drawings()
    except Exception:
        return out
    for di, d in enumerate(draws):
        colk = _color_key(d.get("color"))
        width = float(d.get("width") or 0.0)
        layer = d.get("layer")            # authored CAD layer (OCG) — authored identity
        dashes = d.get("dashes")          # authored dash pattern (e.g. "[] 0" = solid)
        for ii, it in enumerate(d.get("items", []) or []):
            if it[0] not in ("l", "c"):
                continue
            try:
                a, b = _item_endpoints(it)[:2]
                p0 = rotation.to_display_point(a, page)
                p1 = rotation.to_display_point(b, page)
            except Exception:
                continue
            out.append({
                "p0": p0, "p1": p1, "color": colk, "width": width, "kind": it[0],
                "layer": layer, "dashes": (str(dashes) if dashes is not None else None),
                "source_ref": {"draw_index": di, "item_index": ii},
            })
    return out


def extract_paths(page) -> List[Dict[str, Any]]:
    """Path-level polylines (one per ``get_drawings`` entry) in DISPLAY space.

    Each: ``{draw_index, color, width, n_items, points_display:[[x,y],...],
    bbox_display, length, horiz_length, source_ref}``. Consecutive duplicate
    vertices are collapsed. This is the authored ``run`` unit the tracer binds to.
    Page-space only. Never raises.
    """
    out: List[Dict[str, Any]] = []
    try:
        draws = page.get_drawings()
    except Exception:
        return out
    for di, d in enumerate(draws):
        colk = _color_key(d.get("color"))
        width = float(d.get("width") or 0.0)
        items = d.get("items", []) or []
        pts: List[List[float]] = []
        for it in items:
            for rp in _item_endpoints(it):
                try:
                    dp = rotation.to_display_point(rp, page)
                except Exception:
                    continue
                if not pts or abs(pts[-1][0] - dp[0]) > 1e-6 or abs(pts[-1][1] - dp[1]) > 1e-6:
                    pts.append(dp)
        if len(pts) < 2:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        length = 0.0
        horiz = 0.0
        for i in range(len(pts) - 1):
            dx = pts[i + 1][0] - pts[i][0]
            dy = pts[i + 1][1] - pts[i][1]
            seglen = math.hypot(dx, dy)
            length += seglen
            if abs(dy) <= _HORIZONTAL_TOL:
                horiz += seglen
        out.append({
            "draw_index": di, "color": colk, "width": width, "n_items": len(items),
            "layer": d.get("layer"),
            "points_display": pts,
            "bbox_display": [min(xs), min(ys), max(xs), max(ys)],
            "length": round(length, 2), "horiz_length": round(horiz, 2),
            "source_ref": {"draw_index": di, "n_items": len(items)},
        })
    return out
