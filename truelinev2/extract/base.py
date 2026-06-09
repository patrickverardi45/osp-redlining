"""The PlanDialect seam — the ONLY convention-specific layer in v2.

A dialect (a) detects whether it applies to a plan, (b) calibrates the
sheet<->page mapping, (c) declares a match_mode the convention-agnostic matcher
uses, and (d) turns plan pages into canonical Callouts. Everything downstream is
convention-agnostic, so a new plan convention is a new dialect, not an engine fork.
"""
from __future__ import annotations

from typing import List, Protocol, runtime_checkable

from truelinev2.ingest.pdf import PlanPdf
from truelinev2.schema.models import Callout


@runtime_checkable
class PlanDialect(Protocol):
    name: str
    match_mode: str  # "footage" (span+endpoint match) | "containment" (point-in-span)

    def detect(self, plan: PlanPdf) -> bool:
        """Does this dialect recognize the plan? (offset-independent scan.)"""
        ...

    def calibrate(self, plan: PlanPdf, default_offset: int) -> int:
        """Derive the sheet->page offset (page index = sheet + offset - 1)."""
        ...

    def extract_callouts(self, plan: PlanPdf, sheet: int, offset: int) -> List[Callout]:
        ...
