"""Derive the sheet<->page offset from a plan's own matchline tokens — NOT a
hardcoded constant. A plan-profile sheet references its two neighbors
(``MATCH LINE SEE SHEET N-1`` / ``N+1``); a page showing neighbor pair {k-1, k+1}
is sheet k, so offset = page_index - k + 1. Consensus across pages wins.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

_SHEET_TOK = re.compile(r"SHEET\s*0*(\d{1,3})", re.I)


def derive_offset(plan) -> Tuple[Optional[int], List[Dict[str, Any]]]:
    """Return (offset, evidence). offset is None if no matchline consensus."""
    votes: Dict[int, int] = {}
    evidence: List[Dict[str, Any]] = []
    for idx in range(plan.page_count):
        toks = sorted({int(m) for m in _SHEET_TOK.findall(plan.text_by_index(idx).upper())})
        for i in range(len(toks)):
            for j in range(i + 1, len(toks)):
                if toks[j] - toks[i] == 2:  # {k-1, k+1} -> this page is sheet k
                    center = (toks[i] + toks[j]) // 2
                    off = idx - center + 1
                    votes[off] = votes.get(off, 0) + 1
                    evidence.append({"page_idx": idx, "neighbors": [toks[i], toks[j]],
                                     "inferred_sheet": center, "offset": off})
    if not votes:
        return None, evidence
    best = max(votes, key=votes.get)
    return best, evidence
