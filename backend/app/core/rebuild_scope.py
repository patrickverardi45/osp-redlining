"""Rebuild scope vocabulary for _rebuild_field_data_outputs().

RI.1 — declarative enum only. No control flow consumes this value yet.
Defined in advance of RI.2/RI.4 to give future call site migrations a
stable, reviewable seam.

Scope semantics are documented in the rebuild-isolation umbrella design.
"""
from __future__ import annotations

from enum import Enum


class RebuildScope(str, Enum):
    """Declared scope of a rebuild pass.

    RI.1 accepts but does not branch on this value. The seam exists so
    that RI.2 (plan topology cache) and RI.4 (bore-log migration) can
    land surgically without re-threading every call site.

    Behavior contracts (effective from later milestones):

    - FULL          (RI.3): full rebuild; plan topology computed/cached as needed.
    - ROWS_ONLY     (RI.4): skips fresh PDF parse; uses cached topology or empty.
    - METADATA_ONLY (future): sentinel — caller should not invoke rebuild at all.
    - RESET         (future): sentinel — RESET is handled by _reset_workspace_state.
    """

    FULL = "full"
    ROWS_ONLY = "rows_only"
    METADATA_ONLY = "metadata_only"
    RESET = "reset"
