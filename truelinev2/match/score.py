"""Score a candidate chain against the bore span. Convention-agnostic."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

from truelinev2.match.frames import translate_between_sheets
from truelinev2.schema.models import Callout

if TYPE_CHECKING:  # type-only: FrameGraph is used only in annotations.
    from truelinev2.schema.frames import FrameGraph

# A cross-frame chain whose far endpoint cannot be translated into the anchor frame is
# UNSCOREABLE: this sentinel end_delta is far beyond any review tolerance, so decide()
# rejects it (no placement) WITHOUT any change to decide.py.
_UNSCOREABLE_DELTA = 1.0e9


def _chain_end_ft(chain: List[Callout], frame_graph: "Optional[FrameGraph]") -> Optional[float]:
    """The chain's far endpoint in the ANCHOR frame (``chain[0]``'s sheet). frame_graph
    None or a single-sheet chain -> raw ``chain[-1].to_ft`` (M7). Cross-frame: translate
    the last callout's ``to_ft`` into the first callout's frame through a SAFE edge;
    **None** when not translatable (cross-frame-incoherent -> must not place)."""
    last_ft = chain[-1].to_ft
    if frame_graph is None or chain[-1].sheet == chain[0].sheet:
        return last_ft
    return translate_between_sheets(frame_graph, chain[-1].sheet, chain[0].sheet, last_ft)


def score_chain(chain: List[Callout], bore_start_ft: float, bore_end_ft: float,
                span_ft: float, *,
                frame_graph: Optional["FrameGraph"] = None) -> Dict[str, Any]:
    # M8.2c Step 2: ``frame_graph`` is consulted ONLY for the far endpoint of a CROSS-sheet
    # chain (via ``_chain_end_ft``). frame_graph=None (the default for every real caller) ->
    # raw-feet deltas, byte-identical to M7. start_delta stays anchored at chain[0] (raw).
    chain_start = chain[0].from_ft
    chain_end = _chain_end_ft(chain, frame_graph)
    summed = round(sum(c.footage for c in chain), 2)
    sheets = sorted({c.sheet for c in chain})
    return {
        "summed_ft": summed,
        "start_delta": round(abs(chain_start - bore_start_ft), 2),
        "end_delta": (round(abs(chain_end - bore_end_ft), 2)
                      if chain_end is not None else _UNSCOREABLE_DELTA),
        "foot_delta": round(abs(summed - span_ft), 2),
        "vacant": sum(1 for c in chain if c.vacant),
        "sheets": sheets,
        "multi_sheet": len(sheets) > 1,
        "n_boxes": len(chain),
        "chain_from": chain[0].from_sta,
        "chain_to": chain[-1].to_sta,
    }
