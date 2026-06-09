"""Build the v2 Match-Review payload from a bore + placement."""
from __future__ import annotations

from collections import Counter
from typing import List, Tuple

from truelinev2.context import RequestContext
from truelinev2.schema.models import Bore, Placement, ReviewItem, ReviewPayload


def build_review_payload(ctx: RequestContext,
                         results: List[Tuple[Bore, Placement]]) -> ReviewPayload:
    items = [ReviewItem(bore=b, placement=p) for (b, p) in results]
    counts = Counter(it.placement.status.value for it in items)
    return ReviewPayload(
        session_id=ctx.session_id,
        item_count=len(items),
        counts_by_status=dict(counts),
        items=items,
    )
