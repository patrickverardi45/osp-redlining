"""Score a candidate chain against the bore-log span (authored evidence only)."""
from __future__ import annotations

from typing import Any, Dict, List


def score_chain(chain: List[Dict[str, Any]], bore_start_ft: float,
                bore_end_ft: float, span_ft: float) -> Dict[str, Any]:
    chain_start = chain[0]["from_ft"]
    chain_end = chain[-1]["to_ft"]
    summed = round(sum(c["footage"] for c in chain), 2)
    sheets = sorted({c["sheet"] for c in chain})
    return {
        "summed_ft": summed,
        "start_delta": round(abs(chain_start - bore_start_ft), 2),
        "end_delta": round(abs(chain_end - bore_end_ft), 2),
        "foot_delta": round(abs(summed - span_ft), 2),
        "vacant": sum(1 for c in chain if c.get("vacant")),
        "sheets": sheets,
        "multi_sheet": len(sheets) > 1,
        "n_boxes": len(chain),
        "all_verified": all(c.get("footage_verified") for c in chain),
        "chain_from": chain[0]["from_sta"],
        "chain_to": chain[-1]["to_sta"],
    }
