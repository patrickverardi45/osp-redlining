"""The PlanDialect seam — the ONLY convention-specific layer in v2.

A dialect turns a plan page's authored text into canonical Callouts. Everything
downstream (chains/score/decide/render) is convention-agnostic, so a new plan
convention is a new dialect, not an engine fork.
"""
from __future__ import annotations

from typing import List, Protocol, runtime_checkable

from truelinev2.ingest.pdf import PlanPdf
from truelinev2.schema.models import Callout


@runtime_checkable
class PlanDialect(Protocol):
    name: str

    def detect(self, plan: PlanPdf, sheets: List[int], offset: int) -> bool:
        ...

    def extract_callouts(self, plan: PlanPdf, sheet: int, offset: int) -> List[Callout]:
        ...
