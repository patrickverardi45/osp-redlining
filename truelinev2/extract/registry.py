"""Dialect registry + detection. Brenham (footage) + ODOT (containment).

Detection is offset-independent (scans the plan). The first dialect whose
``detect`` returns True wins; Brenham is tried first (its grammar is specific
and never matches an ODOT plan).
"""
from __future__ import annotations

from typing import List, Optional

from truelinev2.extract.base import PlanDialect
from truelinev2.extract.brenham import BrenhamDialect
from truelinev2.extract.odot import OdotDialect
from truelinev2.ingest.pdf import PlanPdf

_DIALECTS: List[PlanDialect] = [BrenhamDialect(), OdotDialect()]


def select_dialect(plan: PlanPdf) -> Optional[PlanDialect]:
    for d in _DIALECTS:
        if d.detect(plan):
            return d
    return None
