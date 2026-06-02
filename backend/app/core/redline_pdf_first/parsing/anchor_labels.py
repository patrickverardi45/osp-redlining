"""Rotation-safe AP/SPLICE label-position capture (authored PDF-space only).

Given a page and the bore's exact AP/SPLICE_LOC identities (from geo_anchors),
locate each label's bbox on the plan by EXACT string search. NO proximity, NO
nearest, NO KMZ/lon-lat conversion — just where the authored text is drawn.

A label may be UNIQUE (1 hit -> a clean marker), AMBIGUOUS (>1 hit -> a shared
splice referenced by several terminals; NOT disambiguated here), or ABSENT (0
hits on this sheet). The caller decides what to draw; this module only reports.
``fitz`` stays in ``pdf/`` (we go through ``text_extract``).
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ..pdf import text_extract


def query_for(kind: str, ident: str) -> Optional[str]:
    """Exact authored label string for an identity. AP -> 'AP-151';
    SPLICE_LOC 'LOC34' -> 'SPLICE LOC 34'. None if not buildable."""
    if kind == "AP":
        return f"AP-{ident}"
    if kind == "SPLICE_LOC":
        m = re.match(r"LOC\s*(\d+)$", str(ident), re.I)
        if m:
            return f"SPLICE LOC {m.group(1)}"
    return None


def capture(page, tokens: Iterable[Tuple[str, str]]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """EXACT-text label capture. ``tokens`` = iterable of ``(kind, id)``. Returns
    ``{(kind,id): {'query', 'count', 'hits':[{bbox_display,bbox_raw}]}}``. Never
    raises; an unbuildable/failed query yields count 0."""
    out: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for (kind, ident) in tokens:
        q = query_for(kind, ident)
        if not q:
            out[(kind, ident)] = {"query": None, "count": 0, "hits": []}
            continue
        try:
            hits = text_extract.search_callout(page, q) or []
        except Exception:
            hits = []
        out[(kind, ident)] = {
            "query": q,
            "count": len(hits),
            "hits": [{"bbox_display": h.get("bbox_display"), "bbox_raw": h.get("bbox_raw")}
                     for h in hits],
        }
    return out
