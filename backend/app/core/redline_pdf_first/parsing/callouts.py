"""Authored DIR. BORE callout extraction from a plan page.

Uses the rotation-safe ``pdf.text_extract`` primitives (no ``fitz`` import here).
Pairs an authored ``STA A TO STA B`` label with a ``DIR. BORE (NNN')`` footage by
the exact-footage check (NNN == B-A), which also recovers the conduit signature.
No Brenham-specific constants.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from ..pdf import text_extract
from . import station as st

_STA2STA = re.compile(r"STA\s+(\d+\+\d+(?:\.\d+)?)\s+TO\s+STA\s+(\d+\+\d+(?:\.\d+)?)", re.I)
_DIRBORE = re.compile(r"DIR\.?\s*BORE\s*\(\s*(\d+(?:\.\d+)?)\s*'?\s*\)\s*(.*)", re.I)
_FOOT_PAIR_TOL = 1.0  # NNN must equal the station delta (within rounding)


def _is_vacant(conduit: str) -> bool:
    return "VACANT" in (conduit or "").upper()


def extract_callouts(page, sheet: int, sheet_offset: int = 13) -> List[Dict[str, Any]]:
    """Return authored callouts on ``page`` as dicts (display-space; bbox lazy)."""
    lines = text_extract.extract_lines(page)

    sta_labels: List[Dict[str, Any]] = []
    for ln in lines:
        m = _STA2STA.search(ln)
        if not m:
            continue
        f0, f1 = st.parse_station(m.group(1)), st.parse_station(m.group(2))
        if f0 is None or f1 is None or f1 <= f0:
            continue
        sta_labels.append({
            "text": ln.strip(), "from_sta": m.group(1), "to_sta": m.group(2),
            "from_ft": f0, "to_ft": f1, "delta": round(f1 - f0, 2),
        })

    bores: List[Dict[str, Any]] = []
    for ln in lines:
        m = _DIRBORE.search(ln)
        if not m:
            continue
        conduit = m.group(2).strip()
        bores.append({"footage": float(m.group(1)), "conduit": conduit, "vacant": _is_vacant(conduit)})

    out: List[Dict[str, Any]] = []
    used = [False] * len(bores)
    for lab in sta_labels:
        match_i = None
        for i, b in enumerate(bores):
            if not used[i] and abs(b["footage"] - lab["delta"]) <= _FOOT_PAIR_TOL:
                match_i = i
                break
        conduit = bores[match_i]["conduit"] if match_i is not None else None
        vacant = bores[match_i]["vacant"] if match_i is not None else False
        if match_i is not None:
            used[match_i] = True
        text = lab["text"]
        if conduit:
            text = f"STA {lab['from_sta']} TO STA {lab['to_sta']} DIR. BORE ({int(round(lab['delta']))}') {conduit}"
        out.append({
            "sheet": sheet, "page": sheet + sheet_offset,
            "from_sta": lab["from_sta"], "to_sta": lab["to_sta"],
            "from_ft": lab["from_ft"], "to_ft": lab["to_ft"], "footage": lab["delta"],
            "footage_verified": match_i is not None, "conduit": conduit, "vacant": vacant,
            "text": text, "bbox_display": None,
        })
    return out


def attach_bbox(page, callout: Dict[str, Any]) -> Dict[str, Any]:
    """Populate ``callout['bbox_display']`` from the de-rotated STA-label search."""
    q = f"STA {callout['from_sta']} TO STA {callout['to_sta']}"
    hits = text_extract.search_callout(page, q)
    if hits:
        callout["bbox_display"] = hits[0]["bbox_display"]
    return callout
