"""Build candidate segment chains from authored callouts.

A chain is a sequence of authored callouts c1..ck where c1 starts near the bore
start and each c(i+1) continues where c(i) ended (same-frame matchline link). This
yields single-box and multi-sheet footage-sum candidates. Endpoint/footage scoring
and tier are decided downstream. No coordinate-snapping.
"""
from __future__ import annotations

from typing import Any, Dict, List

LINK_TOL = 2.0   # c(i).to == c(i+1).from (same-frame matchline rounding)


def build_chains(callouts: List[Dict[str, Any]], bore_start_ft: float,
                 bore_end_ft: float, start_tol: float = 8.0, max_depth: int = 6) -> List[List[Dict[str, Any]]]:
    chains: List[List[Dict[str, Any]]] = []
    starts = [c for c in callouts if abs(c["from_ft"] - bore_start_ft) <= start_tol]

    def extend(chain: List[Dict[str, Any]], ids: set):
        chains.append(list(chain))  # every prefix is a candidate (covers single-box)
        if len(chain) >= max_depth:
            return
        last = chain[-1]
        for c in callouts:
            if id(c) in ids:
                continue
            if abs(last["to_ft"] - c["from_ft"]) <= LINK_TOL and c["to_ft"] > last["to_ft"]:
                extend(chain + [c], ids | {id(c)})

    for s in starts:
        extend([s], {id(s)})
    return chains
