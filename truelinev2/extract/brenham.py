"""Brenham plan dialect.

Grammar: an authored ``STA A TO STA B`` label paired with a ``DIR. BORE (NNN')``
footage by the exact-footage check (NNN == B - A). ``pair_from_lines`` is pure
(testable without a PDF); ``BrenhamDialect`` adds page bbox via text search.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from truelinev2.ingest.pdf import PlanPdf
from truelinev2.schema.models import Callout
from truelinev2.stations import parse_station

_STA2STA = re.compile(r"STA\s+(\d+\+\d+(?:\.\d+)?)\s+TO\s+STA\s+(\d+\+\d+(?:\.\d+)?)", re.I)
_DIRBORE = re.compile(r"DIR\.?\s*BORE\s*\(\s*(\d+(?:\.\d+)?)\s*'?\s*\)\s*(.*)", re.I)
_FOOT_TOL = 1.0


def _is_vacant(conduit: str) -> bool:
    return "VACANT" in (conduit or "").upper()


def pair_from_lines(lines: List[str]) -> List[Dict[str, Any]]:
    """Pure: pair STA-TO-STA labels with DIR.BORE footages across a page's lines."""
    sta_labels: List[Dict[str, Any]] = []
    bores: List[Dict[str, Any]] = []
    for ln in lines:
        ms = _STA2STA.search(ln)
        if ms:
            f0, f1 = parse_station(ms.group(1)), parse_station(ms.group(2))
            if f0 is not None and f1 is not None and f1 > f0:
                sta_labels.append({"text": ln.strip(), "from_sta": ms.group(1),
                                   "to_sta": ms.group(2), "from_ft": f0, "to_ft": f1,
                                   "delta": round(f1 - f0, 2)})
        mb = _DIRBORE.search(ln)
        if mb:
            conduit = mb.group(2).strip()
            bores.append({"footage": float(mb.group(1)), "conduit": conduit,
                          "vacant": _is_vacant(conduit)})

    out: List[Dict[str, Any]] = []
    used = [False] * len(bores)
    for lab in sta_labels:
        mi = None
        for i, b in enumerate(bores):
            if not used[i] and abs(b["footage"] - lab["delta"]) <= _FOOT_TOL:
                mi = i
                break
        conduit = bores[mi]["conduit"] if mi is not None else None
        vacant = bores[mi]["vacant"] if mi is not None else False
        if mi is not None:
            used[mi] = True
        text = lab["text"]
        if conduit:
            text = (f"STA {lab['from_sta']} TO STA {lab['to_sta']} "
                    f"DIR. BORE ({int(round(lab['delta']))}') {conduit}")
        out.append({
            "from_sta": lab["from_sta"], "to_sta": lab["to_sta"],
            "from_ft": lab["from_ft"], "to_ft": lab["to_ft"], "footage": lab["delta"],
            "conduit": conduit, "vacant": vacant, "footage_verified": mi is not None,
            "text": text,
        })
    return out


class BrenhamDialect:
    name = "brenham"

    def detect(self, plan: PlanPdf, sheets: List[int], offset: int) -> bool:
        for s in sheets:
            for ln in plan.lines(s, offset):
                if _DIRBORE.search(ln) or _STA2STA.search(ln):
                    return True
        return False

    def extract_callouts(self, plan: PlanPdf, sheet: int, offset: int) -> List[Callout]:
        paired = pair_from_lines(plan.lines(sheet, offset))
        callouts: List[Callout] = []
        for p in paired:
            bbox = None
            hits = plan.search(sheet, offset, f"STA {p['from_sta']} TO STA {p['to_sta']}")
            if hits:
                bbox = hits[0]
            callouts.append(Callout(
                sheet=sheet, page=sheet + offset, from_sta=p["from_sta"], to_sta=p["to_sta"],
                from_ft=p["from_ft"], to_ft=p["to_ft"], footage=p["footage"],
                conduit=p["conduit"], vacant=p["vacant"], footage_verified=p["footage_verified"],
                text=p["text"], bbox=bbox, dialect="brenham"))
        return callouts
