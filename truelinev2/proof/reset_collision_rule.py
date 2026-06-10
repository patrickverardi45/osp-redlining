"""M8.2k -- PROOF-ONLY reset-vs-continuous collision rule (proposal).

A pure decision function over collision evidence, derived from Patrick's banked
M8.2j grades. It is NOT wired into ``decide.py`` / ``run_match`` / default
placement and imports NOTHING from the engine. It exists so the proposed rule can
be stated precisely, tested, and simulated against the banked default results
BEFORE any flag-gated engine work is authorized.

The proposed rule (precedence is safety-first, top wins):

  R3/R5. Parent-run/segment context unresolved, or the segment ends at an access
         structure (flower pot / HH / terminal) with competing continuation
         evidence -> ABSTAIN_REQUIRED. An on-crossing reset equation alone is NOT
         enough to override parent-run/segment ambiguity.
  R2.    The on-crossing reset equation has close competing readings (log57's
         3+98 vs 3+93, within the precision band) -> PRECISION_CONFLICT_MANUAL_REVIEW.
  R1.    An on-crossing reset equation is visually confirmed AND the far-side
         continuation matches the reset station -> RESET_EQUATION_CONFIRMED.
  R4.    An on-crossing reset equation is present but NOT confirmed: an exact
         continuous box match alone is NOT enough to override it ->
         STILL_UNKNOWN_MANUAL_REVIEW (never silently trust the continuous read).
  R0.    No on-crossing reset equation -> CONTINUOUS_STATION_STANDS (outside this
         rule's collision scope; the default continuous link is not disputed).

  R6 (invariant). NO classification of this rule may auto-promote ANYTHING:
     ``may_auto_promote(...)`` is False for every class by construction, and the
     simulation can only DEMOTE a disputed AUTO placement (AUTO->REVIEW/ABSTAIN)
     or leave a result unchanged -- it can never move any result toward AUTO.

Even RESET_EQUATION_CONFIRMED does not place anything: it is evidence that the
default's continuous chain is WRONG-CHAINED; re-routing through the equation stays
gated behind a future default-OFF flag plus an M8.2d-style zero-regression proof.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

# log57's two readings (3+98 vs 3+93) are 5 ft apart; the banked M8.2h precision
# band is 10 ft (run_transition_visual_targets.CONFLICT_PRECISION_FT -- duplicated
# here as a constant so this module imports nothing that imports the engine).
PRECISION_CONFLICT_FT = 10.0


class RuleClass(str, Enum):
    RESET_EQUATION_CONFIRMED = "reset_equation_confirmed"
    PRECISION_CONFLICT_MANUAL_REVIEW = "precision_conflict_manual_review"
    ABSTAIN_REQUIRED = "abstain_required"
    STILL_UNKNOWN_MANUAL_REVIEW = "still_unknown_manual_review"
    CONTINUOUS_STATION_STANDS = "continuous_station_stands"


@dataclass(frozen=True)
class CollisionEvidence:
    """Evidence for ONE on-crossing reset-vs-continuous collision case."""
    case_id: str
    # the collision itself
    on_crossing_reset_equation: bool          # a parsed equation references/sits at the crossing
    exact_continuous_box_match: bool          # the default chain matches continuously, deltas ~0
    # R1 inputs
    equation_visually_confirmed: bool = False  # human (Patrick) confirmed the eq applies here
    far_side_matches_reset_station: bool = False  # far-sheet continuation starts at the eq's other side
    # R2 inputs
    competing_equation_readings: bool = False  # >=2 near-identical readings of the same matchline
    readings_spread_ft: Optional[float] = None
    # R3/R5 inputs
    parent_run_context_unresolved: bool = False  # run/segment child; physical continuation unconfirmed
    ends_at_access_structure: bool = False       # flower pot / HH / terminal at the segment end
    competing_continuation_evidence: bool = False  # another continuation candidate exists
    # corroborating only (never load-bearing)
    conduit_changes_across_crossing: Optional[bool] = None


@dataclass(frozen=True)
class RuleResult:
    case_id: str
    classification: RuleClass
    reason: str

    @property
    def blocks_auto(self) -> bool:
        """True when the rule forbids trusting the default AUTO chain as-is."""
        return self.classification is not RuleClass.CONTINUOUS_STATION_STANDS

    def to_dict(self) -> dict:
        return {"case_id": self.case_id, "classification": self.classification.value,
                "blocks_auto": self.blocks_auto, "may_auto_promote": may_auto_promote(self.classification),
                "reason": self.reason}


def may_auto_promote(classification: RuleClass) -> bool:  # noqa: ARG001 (uniform signature)
    """R6 invariant: NO classification of this rule may promote anything to AUTO
    (or place anything). Constant False BY CONSTRUCTION -- test-pinned."""
    return False


def classify_collision(ev: CollisionEvidence) -> RuleResult:
    """Apply the proposed rule to one collision's evidence. Pure; no IO."""
    def out(klass: RuleClass, reason: str) -> RuleResult:
        return RuleResult(case_id=ev.case_id, classification=klass, reason=reason)

    if not ev.on_crossing_reset_equation:
        return out(RuleClass.CONTINUOUS_STATION_STANDS,
                   "no on-crossing reset equation: the collision rule does not apply; "
                   "the default continuous link is not disputed by this rule")

    # R3/R5 -- parent-run/segment ambiguity outranks the equation (an on-crossing
    # reset equation alone is not enough to override it).
    if ev.parent_run_context_unresolved or (
            ev.ends_at_access_structure and ev.competing_continuation_evidence):
        return out(RuleClass.ABSTAIN_REQUIRED,
                   "parent-run/segment context unresolved (or segment ends at an access "
                   "structure with competing continuation evidence): neither continuous nor "
                   "reset may be chosen automatically")

    # R2 -- near-identical competing readings of the matchline = extraction precision
    # conflict; the exact station is unknown, so never auto-pick a side.
    if ev.competing_equation_readings and (
            ev.readings_spread_ft is None or ev.readings_spread_ft <= PRECISION_CONFLICT_FT):
        return out(RuleClass.PRECISION_CONFLICT_MANUAL_REVIEW,
                   "the reset equation has close competing readings (one matchline read "
                   "slightly apart): resolve the exact station before any use; never auto-place")

    # R1 -- confirmed reset: the equation is visually confirmed at the crossing AND the
    # far-side continuation matches the reset station.
    if ev.equation_visually_confirmed and ev.far_side_matches_reset_station:
        return out(RuleClass.RESET_EQUATION_CONFIRMED,
                   "on-crossing reset equation visually confirmed and the far-side "
                   "continuation matches the reset station: treat as reset/equation, not raw "
                   "continuous station (re-chaining stays gated behind a zero-regression proof)")

    # R4 -- an exact continuous box match alone is NOT enough to override an
    # on-crossing reset equation; unconfirmed collision stays with a human.
    return out(RuleClass.STILL_UNKNOWN_MANUAL_REVIEW,
               "an on-crossing reset equation is present but unconfirmed: an exact continuous "
               "box match alone cannot override it; manual review required")


def simulate_default_status(default_status: str, result: RuleResult) -> str:
    """What the default status WOULD become if the rule were consulted as a gate.
    Demote-only by construction: a disputed AUTO drops to REVIEW/ABSTAIN; nothing
    ever moves toward AUTO; non-collision results are untouched."""
    if not result.blocks_auto:
        return default_status
    if default_status == "AUTO_SELECT":
        return ("ABSTAIN" if result.classification is RuleClass.ABSTAIN_REQUIRED else "REVIEW")
    if default_status == "REVIEW" and result.classification is RuleClass.ABSTAIN_REQUIRED:
        return "ABSTAIN"
    return default_status  # ABSTAIN/ERROR never promoted; REVIEW never promoted
