"""Score a candidate chain against the bore span. Convention-agnostic."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

from truelinev2.schema.models import Callout

if TYPE_CHECKING:  # M8.2c Step 1: type-only; no runtime import (import graph unchanged).
    from truelinev2.schema.frames import FrameGraph


def score_chain(chain: List[Callout], bore_start_ft: float, bore_end_ft: float,
                span_ft: float, *,
                frame_graph: Optional["FrameGraph"] = None) -> Dict[str, Any]:
    # M8.2c Step 1: ``frame_graph`` is accepted but NEVER consulted yet (inert
    # plumbing). With None/OFF the raw-feet deltas below are byte-identical to M7.
    chain_start = chain[0].from_ft
    chain_end = chain[-1].to_ft
    summed = round(sum(c.footage for c in chain), 2)
    sheets = sorted({c.sheet for c in chain})
    return {
        "summed_ft": summed,
        "start_delta": round(abs(chain_start - bore_start_ft), 2),
        "end_delta": round(abs(chain_end - bore_end_ft), 2),
        "foot_delta": round(abs(summed - span_ft), 2),
        "vacant": sum(1 for c in chain if c.vacant),
        "sheets": sheets,
        "multi_sheet": len(sheets) > 1,
        "n_boxes": len(chain),
        "chain_from": chain[0].from_sta,
        "chain_to": chain[-1].to_sta,
    }
