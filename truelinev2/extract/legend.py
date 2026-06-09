"""Generic legend/key-block detection (layout + standard-vocabulary based).

A plan legend is a vertically-stacked, regularly-spaced column of standard
utility line-type labels (WATER, STORM DRAIN, SANITARY SEWER, GAS, BURIED
ELECTRIC, CATV, FIBER, CONDUIT, ...). We detect it STRUCTURALLY — a left-aligned
column of >= N distinct such terms — and TIGHTEN to the densest contiguous run so
scattered crossing-utility labels on a plan/profile sheet don't inflate the box.
Not by matching the word "legend"; not by hardcoding coordinates.
"""
from __future__ import annotations

import statistics
from typing import Any, Dict, List, Optional

LEGEND_VOCAB = {
    "WATER", "SEWER", "DRAIN", "GAS", "ELECTRIC", "TELEPHONE", "TEL", "CATV",
    "FIBER", "CONDUIT", "STORM", "SANITARY", "BURIED", "OVERHEAD", "PLOW",
}


def _norm(t: str) -> str:
    return (t or "").strip().upper()


def detect_legend_block(words: List[Dict[str, Any]], min_distinct: int = 4,
                        x_band: float = 90.0, min_height: float = 20.0
                        ) -> Optional[List[float]]:
    """Return [x0,y0,x1,y1] of a detected legend column, or None."""
    markers = [w for w in words if _norm(w["text"]) in LEGEND_VOCAB]
    if len({_norm(w["text"]) for w in markers}) < min_distinct:
        return None
    medx = statistics.median([w["x0"] for w in markers])
    col = [w for w in markers if abs(w["x0"] - medx) <= x_band]
    if len({_norm(w["text"]) for w in col}) < min_distinct:
        col = markers

    # Tighten to the densest contiguous vertical run (a legend key is regularly
    # spaced; stray crossing-utility labels are far in y and get dropped).
    col = sorted(col, key=lambda w: w["yc"])
    if len(col) >= 3:
        gaps = [col[i + 1]["yc"] - col[i]["yc"] for i in range(len(col) - 1)]
        med_gap = statistics.median(gaps) if gaps else 0.0
        thresh = max(2.5 * med_gap, 40.0)
        best_s, best_e, s = 0, 0, 0
        for i in range(len(gaps)):
            if gaps[i] > thresh:
                if i - s > best_e - best_s:
                    best_s, best_e = s, i
                s = i + 1
        if (len(gaps) - s) > (best_e - best_s):
            best_s, best_e = s, len(gaps)
        run = col[best_s:best_e + 1]
        if len({_norm(w["text"]) for w in run}) >= min_distinct:
            col = run

    x0 = min(w["x0"] for w in col)
    y0 = min(w["y0"] for w in col)
    x1 = max(w["x1"] for w in col)
    y1 = max(w["y1"] for w in col)
    if (y1 - y0) < min_height:
        return None
    return [x0, y0, x1, y1]


def point_in_bbox(x: float, y: float, bbox: List[float], pad: float = 0.0,
                  pad_x_right: float = 0.0) -> bool:
    return (bbox[0] - pad) <= x <= (bbox[2] + pad + pad_x_right) and \
           (bbox[1] - pad) <= y <= (bbox[3] + pad)
