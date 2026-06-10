"""M8.2k reset-vs-continuous collision rule -- re-export shim.

M8.2l re-homed the pure rule into core (``truelinev2/match/collision_gate.py``) so
the default-OFF opt-in gate can consult it without the core importing ``proof/``.
This module keeps the M8.2k import surface stable: the M8.2k proof script and tests
import the rule from here, and the rule's behavior is byte-identical (same types,
same precedence R3/R5 > R2 > R1 > R4, same R6 never-promote invariant, same
demote-only simulation).
"""
from __future__ import annotations

from truelinev2.match.collision_gate import (  # noqa: F401 (re-exports)
    PRECISION_CONFLICT_FT,
    CollisionEvidence,
    RuleClass,
    RuleResult,
    classify_collision,
    may_auto_promote,
    simulate_default_status,
)

__all__ = [
    "PRECISION_CONFLICT_FT",
    "CollisionEvidence",
    "RuleClass",
    "RuleResult",
    "classify_collision",
    "may_auto_promote",
    "simulate_default_status",
]
