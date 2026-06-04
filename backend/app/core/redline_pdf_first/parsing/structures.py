"""Named-structure extraction (AP / Splice / HH / Flower Pot / terminal).

Generic regex over the page text — NO hardcoded AP lists as core logic. Uses the
rotation-safe ``pdf`` primitives; can filter structures near a callout's bbox so a
selected box gets only its local structures.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from ..pdf import text_extract

_PATTERNS = [
    (re.compile(r"AP-?\d+", re.I), "AP"),
    (re.compile(r"SPLICE(?:\s+(?:POINT|LOC))?\s*\d*", re.I), "SPLICE"),
    (re.compile(r"INSTALLER\s+HH", re.I), "INSTALLER_HH"),
    (re.compile(r"FLOWER\s*POT", re.I), "FLOWER_POT"),
    (re.compile(r"\d+\s*-?\s*PORT(?:\s+TERMINAL)?", re.I), "PORT_TERMINAL"),
]


def extract_structures(page) -> List[Dict[str, Any]]:
    """Deduped structure tokens found anywhere on the page."""
    out: List[Dict[str, Any]] = []
    seen = set()
    for ln in text_extract.extract_lines(page):
        for rx, kind in _PATTERNS:
            for m in rx.findall(ln):
                t = m.strip()
                if (kind, t) in seen:
                    continue
                seen.add((kind, t))
                out.append({"kind": kind, "text": t})
    return out


def structures_near(page, bbox_display, tokens: List[Dict[str, Any]],
                    radius: float = 240.0) -> List[str]:
    """Structure texts whose search bbox is within ``radius`` (display units) of
    ``bbox_display``. Prefers the meaningful anchors (AP/SPLICE first)."""
    if not bbox_display:
        return []
    cx = (bbox_display[0] + bbox_display[2]) / 2.0
    cy = (bbox_display[1] + bbox_display[3]) / 2.0
    near: List[str] = []
    for t in tokens:
        if t["kind"] not in ("AP", "SPLICE", "INSTALLER_HH", "FLOWER_POT"):
            continue
        for h in text_extract.search_callout(page, t["text"]):
            b = h["bbox_display"]
            bx = (b[0] + b[2]) / 2.0
            by = (b[1] + b[3]) / 2.0
            if abs(bx - cx) <= radius and abs(by - cy) <= radius:
                if t["text"] not in near:
                    near.append(t["text"])
                break
    return near
