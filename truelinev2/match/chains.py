"""Build candidate callout chains for a bore span. Convention-agnostic.

A chain starts near the bore start and each link continues where the prior ended
(matchline link). Every prefix is a candidate (covers single-box + multi-sheet).
"""
from __future__ import annotations

from typing import List

from truelinev2.schema.models import Callout


def build_chains(callouts: List[Callout], bore_start_ft: float, bore_end_ft: float,
                 start_tol: float = 8.0, link_tol: float = 2.0,
                 max_depth: int = 6) -> List[List[Callout]]:
    chains: List[List[Callout]] = []
    starts = [c for c in callouts if abs(c.from_ft - bore_start_ft) <= start_tol]

    def extend(chain: List[Callout], ids: set) -> None:
        chains.append(list(chain))
        if len(chain) >= max_depth:
            return
        last = chain[-1]
        for c in callouts:
            if id(c) in ids:
                continue
            if abs(last.to_ft - c.from_ft) <= link_tol and c.to_ft > last.to_ft:
                extend(chain + [c], ids | {id(c)})

    for s in starts:
        extend([s], {id(s)})
    return chains
