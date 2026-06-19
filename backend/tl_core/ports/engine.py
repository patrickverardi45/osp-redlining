"""Port: the redline engine.

tl_core depends on THIS protocol, not on the concrete reused package, so the
engine stays swappable and import-isolated.
"""
from __future__ import annotations

from typing import Protocol

from ..domain.redline import RedlineResult


class RedlineEnginePort(Protocol):
    def run(self, bore_log_path: str, plan_pdf_path: str) -> RedlineResult:
        """Run selection + crop render for one bore log against one plan PDF.

        Must NEVER raise into the caller (mirrors the engine's own no-raise
        contract): failures come back as a :class:`RedlineResult` with
        ``status == "ERROR"`` and a populated ``warnings`` list.
        """
        ...
