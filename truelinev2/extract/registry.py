"""Dialect registry + detection. M1 registers Brenham; M2 will add ODOT."""
from __future__ import annotations

from typing import List, Optional

from truelinev2.extract.base import PlanDialect
from truelinev2.extract.brenham import BrenhamDialect
from truelinev2.ingest.pdf import PlanPdf

_DIALECTS: List[PlanDialect] = [BrenhamDialect()]


def select_dialect(plan: PlanPdf, sheets: List[int], offset: int) -> Optional[PlanDialect]:
    for d in _DIALECTS:
        if d.detect(plan, sheets, offset):
            return d
    return None
