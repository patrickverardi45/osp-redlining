"""Build candidate callout chains for a bore span. Convention-agnostic.

A chain starts near the bore start and each link continues where the prior ended
(matchline link). Every prefix is a candidate (covers single-box + multi-sheet).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

from truelinev2.match.frames import translate_between_sheets
from truelinev2.schema.models import Callout

if TYPE_CHECKING:  # type-only: FrameGraph is used only in annotations.
    from truelinev2.schema.frames import FrameGraph


def _linkable(last: Callout, c: Callout, link_tol: float,
              frame_graph: "Optional[FrameGraph]") -> bool:
    """Does callout ``c`` continue ``last`` within ``link_tol``?

    ``frame_graph is None`` -> raw-feet link (M7, byte-identical). With a graph a
    SAME-sheet link stays raw; a CROSS-sheet link is allowed ONLY by translating ``c``'s
    endpoints into ``last``'s frame through a SAFE frame edge -- if no safe edge connects
    the sheets the link is refused (a raw equal station across sheets is not proof)."""
    if frame_graph is None or last.sheet == c.sheet:
        return abs(last.to_ft - c.from_ft) <= link_tol and c.to_ft > last.to_ft
    c_from = translate_between_sheets(frame_graph, c.sheet, last.sheet, c.from_ft)
    c_to = translate_between_sheets(frame_graph, c.sheet, last.sheet, c.to_ft)
    if c_from is None or c_to is None:
        return False
    return abs(last.to_ft - c_from) <= link_tol and c_to > last.to_ft


def build_chains(callouts: List[Callout], bore_start_ft: float, bore_end_ft: float,
                 start_tol: float = 8.0, link_tol: float = 2.0,
                 max_depth: int = 6, *,
                 frame_graph: Optional["FrameGraph"] = None) -> List[List[Callout]]:
    # M8.2c Step 2: ``frame_graph`` is consulted ONLY for CROSS-sheet links (via
    # ``_linkable``). frame_graph=None (the default every real caller passes) -> raw-feet
    # linking, byte-identical to M7. The START match below stays raw (the start anchors
    # near 0+00 in both the bore frame and the start sheet's frame).
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
            if _linkable(last, c, link_tol, frame_graph):
                extend(chain + [c], ids | {id(c)})

    for s in starts:
        extend([s], {id(s)})
    return chains
