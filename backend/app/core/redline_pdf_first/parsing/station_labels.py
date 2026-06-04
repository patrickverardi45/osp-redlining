"""Rotation-safe authored STATION-TICK label extraction (page-space).

Finds authored ``N+NN`` station labels on a plan page with de-rotated positions,
using the existing rotation-safe text primitives (no OCR). These are the
surveyor's stationing printed along the bored line — authored identity that lets
the dash-chain tracer corroborate which reconstructed run is a given bore (the
labels' VALUES must match the bore's authored station range).

Pure read; never raises. ``fitz`` stays in ``pdf/`` (we go through ``text_extract``).
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from ..pdf import text_extract

# A bare station token: 0+00, 12+22, 4+16.5 (NOT "STA 1+40 TO STA ..."; bare ticks).
_STA_WORD = re.compile(r"^(\d{1,3})\+(\d{2}(?:\.\d+)?)$")


def parse_station_word(text: str) -> Optional[float]:
    """``'12+22'`` -> ``1222.0`` ft; ``None`` if not a bare station token."""
    m = _STA_WORD.match((text or "").strip())
    if not m:
        return None
    return int(m.group(1)) * 100.0 + float(m.group(2))


def extract_station_labels(page) -> List[Dict[str, Any]]:
    """Authored station-tick labels with de-rotated page-space centers.

    Each: ``{value_ft, text, bbox_display, center:[x,y]}``. Page-space only.
    """
    out: List[Dict[str, Any]] = []
    try:
        words = text_extract.extract_words(page)
    except Exception:
        return out
    for w in words:
        v = parse_station_word(w.get("text"))
        if v is None:
            continue
        b = w.get("bbox_display")
        if not b or len(b) != 4:
            continue
        out.append({
            "value_ft": v,
            "text": (w.get("text") or "").strip(),
            "bbox_display": list(b),
            "center": [(b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0],
        })
    return out
