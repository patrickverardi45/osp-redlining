"""M8.2l -- reset-vs-continuous collision gate (default-OFF opt-in).

The M8.2k proof-only rule, re-homed into core and wired as an OPTIONAL, demote-only
gate the engine consults ONLY when a caller injects one (``run_match(...,
collision_gate=...)``). No gate (the default) -> byte-identical default behavior.

What the gate does, per placed footage-mode chain:
  1. RUNTIME-DETECT an on-crossing reset-vs-continuous collision: a cross-sheet
     transition in the winning chain where a parsed matchline frame equation on that
     sheet pair references the crossing station. No collision -> placement returned
     UNCHANGED (the only way the other 55 logs can ever be touched is if they grow a
     real on-crossing collision -- M8.2g/h proved exactly three exist today).
  2. Build the M8.2k CollisionEvidence: runtime-derivable fields (on-crossing,
     exact continuous match, competing precision readings, far-side reset-station
     continuation) plus the HUMAN evidence from the banked M8.2j grading ledger
     (visual confirmation / parent-run ambiguity are human facts, not derivable).
  3. Classify with the M8.2k rule and apply ``simulate_default_status``:
     DEMOTE-ONLY. Nothing is ever promoted toward AUTO (R6, enforced again here).

A human grade of ``continuous_station_confirmed`` resolves the collision in favor
of the continuous read -> placement unchanged. An UNGRADED collision is handled by
the rule's R4 (continuous never silently wins) -> manual review.

This module does NOT activate frame translation (``frame_graph`` stays None in the
default and opt-in paths alike); M8.2d's blanket opt-in remains NOT_SAFE and is not
re-attempted here. No convention names; no global mutable state; pure except the
explicit ledger-file reader.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Mapping, Optional, Sequence, Tuple

from truelinev2.config import _REPO_ROOT
from truelinev2.match.frames import (
    build_frame_edges,
    build_frame_graph,
    frame_for_sheet,
    parse_frame_equations,
)
from truelinev2.match.transition_classifier import (
    classify_callout_transition,
    conflict_sheet_pairs,
)
from truelinev2.schema.models import Placement, PlacementStatus

if TYPE_CHECKING:
    from truelinev2.ingest.pdf import PlanPdf
    from truelinev2.schema.frames import FrameEquation
    from truelinev2.schema.models import Callout

# A collision exists only where the transition itself is DISPUTED -- the M8.2f
# classifier judges it ambiguous / conflict / missing_evidence against the SAFE
# frame graph (the banked M8.2g/h definition). A clean transition (continuous /
# same-sheet / reconciled reset) is NEVER gated, even if some equation elsewhere
# on the sheet pair happens to mention the crossing station.
_DIRTY = ("ambiguous", "conflict", "missing_evidence")

# log57's two readings (3+98 vs 3+93) are 5 ft apart; the banked M8.2h precision
# band is 10 ft. One matchline read twice within this band = a precision conflict.
PRECISION_CONFLICT_FT = 10.0

# The banked M8.2j human grading ledger (evidence intake; committed).
DEFAULT_LEDGER_PATH = (_REPO_ROOT / "truelinev2" / "docs" / "review"
                       / "m8-2j-reset-collision-human-grades.json")

# Demote-only status rank: a gated placement may only move DOWN this scale.
_STATUS_RANK = {"ABSTAIN": 0, "ERROR": 0, "REVIEW": 1, "AUTO_SELECT": 2}


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
    on_crossing_reset_equation: bool
    exact_continuous_box_match: bool
    equation_visually_confirmed: bool = False
    far_side_matches_reset_station: bool = False
    competing_equation_readings: bool = False
    readings_spread_ft: Optional[float] = None
    parent_run_context_unresolved: bool = False
    ends_at_access_structure: bool = False
    competing_continuation_evidence: bool = False
    conduit_changes_across_crossing: Optional[bool] = None


@dataclass(frozen=True)
class RuleResult:
    case_id: str
    classification: RuleClass
    reason: str

    @property
    def blocks_auto(self) -> bool:
        return self.classification is not RuleClass.CONTINUOUS_STATION_STANDS

    def to_dict(self) -> dict:
        return {"case_id": self.case_id, "classification": self.classification.value,
                "blocks_auto": self.blocks_auto,
                "may_auto_promote": may_auto_promote(self.classification),
                "reason": self.reason}


def may_auto_promote(classification: RuleClass) -> bool:  # noqa: ARG001 (uniform signature)
    """R6 invariant: NO classification of this rule may promote anything to AUTO
    (or place anything). Constant False BY CONSTRUCTION -- test-pinned."""
    return False


def classify_collision(ev: CollisionEvidence) -> RuleResult:
    """The M8.2k rule. Precedence is safety-first (R3/R5 > R2 > R1 > R4); see the
    M8.2k milestone doc for the full statement. Pure; no IO."""
    def out(klass: RuleClass, reason: str) -> RuleResult:
        return RuleResult(case_id=ev.case_id, classification=klass, reason=reason)

    if not ev.on_crossing_reset_equation:
        return out(RuleClass.CONTINUOUS_STATION_STANDS,
                   "no on-crossing reset equation: the collision rule does not apply; "
                   "the default continuous link is not disputed by this rule")
    if ev.parent_run_context_unresolved or (
            ev.ends_at_access_structure and ev.competing_continuation_evidence):
        return out(RuleClass.ABSTAIN_REQUIRED,
                   "parent-run/segment context unresolved (or segment ends at an access "
                   "structure with competing continuation evidence): neither continuous nor "
                   "reset may be chosen automatically")
    if ev.competing_equation_readings and (
            ev.readings_spread_ft is None or ev.readings_spread_ft <= PRECISION_CONFLICT_FT):
        return out(RuleClass.PRECISION_CONFLICT_MANUAL_REVIEW,
                   "the reset equation has close competing readings (one matchline read "
                   "slightly apart): resolve the exact station before any use; never auto-place")
    if ev.equation_visually_confirmed and ev.far_side_matches_reset_station:
        return out(RuleClass.RESET_EQUATION_CONFIRMED,
                   "on-crossing reset equation visually confirmed and the far-side "
                   "continuation matches the reset station: treat as reset/equation, not raw "
                   "continuous station (re-chaining stays gated behind a zero-regression proof)")
    return out(RuleClass.STILL_UNKNOWN_MANUAL_REVIEW,
               "an on-crossing reset equation is present but unconfirmed: an exact continuous "
               "box match alone cannot override it; manual review required")


def simulate_default_status(default_status: str, result: RuleResult) -> str:
    """Demote-only mapping. A disputed AUTO drops to REVIEW/ABSTAIN; nothing ever
    moves toward AUTO; non-collision results are untouched."""
    if not result.blocks_auto:
        return default_status
    if default_status == "AUTO_SELECT":
        return ("ABSTAIN" if result.classification is RuleClass.ABSTAIN_REQUIRED else "REVIEW")
    if default_status == "REVIEW" and result.classification is RuleClass.ABSTAIN_REQUIRED:
        return "ABSTAIN"
    return default_status


# --- human evidence (banked M8.2j ledger) -------------------------------------

def load_human_grades(path: Path = DEFAULT_LEDGER_PATH) -> Dict[str, str]:
    """``{bore_id: grade}`` from the committed M8.2j grading ledger. Missing or
    unreadable ledger -> empty mapping (the rule then runs on runtime evidence only,
    where R4 keeps every unconfirmed collision at manual review -- safe-by-default)."""
    try:
        ledger = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(t.get("id")): str(t.get("grade", ""))
            for t in ledger.get("targets", []) if isinstance(t, dict)}


def _human_fields(grade: Optional[str]) -> Dict[str, bool]:
    """Translate a banked human grade into the rule's human-only evidence fields.
    ``reset_equation_confirmed`` = the human visually confirmed the equation applies;
    ``abstain_required`` = the human marked parent-run/segment context unresolved.
    Other grades / ungraded add NO human fields (runtime evidence + R4 decide)."""
    if grade == "reset_equation_confirmed":
        return {"equation_visually_confirmed": True}
    if grade == "abstain_required":
        return {"parent_run_context_unresolved": True}
    return {}


# --- runtime collision detection ------------------------------------------------

def collect_equations(plan: "PlanPdf", offset: int,
                      sheets: Sequence[int]) -> Dict[int, Tuple["FrameEquation", ...]]:
    """Parse the frame equations on each given sheet's page text (read-only)."""
    out: Dict[int, Tuple["FrameEquation", ...]] = {}
    for s in dict.fromkeys(int(x) for x in sheets):
        idx = plan.page_index(s, offset)
        if not (0 <= idx < plan.page_count):
            out[s] = ()
            continue
        text = " ".join(ln for ln in plan.text_by_index(idx).splitlines() if ln.strip())
        out[s] = tuple(parse_frame_equations(text))
    return out


def collect_all_sheet_equations(plan: "PlanPdf",
                                offset: int) -> Dict[int, Tuple["FrameEquation", ...]]:
    """M8.12: the CANONICAL reverse-anchor equation universe -- EVERY sheet's
    equations, so ``reverse_anchor.matchline_mask`` sees matchlines authored on
    the FAR side of a pair (outside a bore's own ``sheet_refs``). A per-bore
    universe UNDER-MASKS (the banked log62 divergence: a far-side-authored
    matchline left a 9-ft vacant run unmasked as anchor evidence). All
    ``ReverseAnchorContext`` constructions must use this builder."""
    return collect_equations(plan, offset, range(1, plan.page_count - offset + 1))


def _pair_equations(equations_by_sheet: Mapping[int, Sequence["FrameEquation"]],
                    a_sheet: int, b_sheet: int) -> List["FrameEquation"]:
    """Equations parsed on either sheet of the pair that LINK the other sheet."""
    out: List["FrameEquation"] = []
    for s, other in ((a_sheet, b_sheet), (b_sheet, a_sheet)):
        for eq in equations_by_sheet.get(s, ()):
            if other in eq.linked_frames:
                out.append(eq)
    return out


def _precision_conflict(pair_eqs: Sequence["FrameEquation"]) -> Tuple[bool, Optional[float]]:
    """log57-style: >=2 readings of one matchline (a shared station side) whose
    offsets disagree within the precision band."""
    if len(pair_eqs) < 2:
        return False, None
    a_raws = [e.a.raw for e in pair_eqs]
    b_raws = [e.b.raw for e in pair_eqs]
    shared = (len(set(a_raws)) < len(a_raws)) or (len(set(b_raws)) < len(b_raws))
    offs = [e.offset_ft for e in pair_eqs]
    spread = round(max(offs) - min(offs), 2)
    return (shared and 0.0 < spread <= PRECISION_CONFLICT_FT), spread


@dataclass(frozen=True)
class CollisionGate:
    """Injected into ``run_match``; absent (None) = flag OFF = default behavior."""
    equations_by_sheet: Mapping[int, Tuple["FrameEquation", ...]]
    human_grades: Mapping[str, str] = field(default_factory=dict)
    link_tol: float = 2.0

    def apply(self, placement: Placement, all_callouts: Sequence["Callout"]) -> Placement:
        """Demote-only adjustment of a placed footage-mode chain. Returns the
        placement UNCHANGED unless a genuine on-crossing collision is detected."""
        if placement.status not in (PlacementStatus.AUTO_SELECT, PlacementStatus.REVIEW):
            return placement  # nothing below REVIEW is ever touched (never promoted)
        chain = list(placement.matched_callouts)
        if len(chain) < 2:
            return placement

        # 1. runtime detection (the banked M8.2g/h collision definition): a
        #    cross-sheet transition that is (a) DISPUTED by the safe frame graph
        #    (classifier-dirty) AND (b) carries an on-crossing equation that
        #    references the crossing station. Both must hold; genuinely-continuous
        #    runs (clean transitions) are never gated.
        edges = []
        for s, eqs in self.equations_by_sheet.items():
            edges.extend(build_frame_edges(list(eqs), frame_for_sheet(s)))
        graph = build_frame_graph(edges)
        conflicts = conflict_sheet_pairs(graph)

        on_crossing_eqs: List["FrameEquation"] = []
        pair_eqs_all: List["FrameEquation"] = []
        for ca, cb in zip(chain, chain[1:]):
            if ca.sheet == cb.sheet:
                continue
            t = classify_callout_transition(graph, conflicts, ca, cb,
                                            link_tol=self.link_tol)
            if t.classification.value not in _DIRTY:
                continue  # clean transition: not a collision
            pair_eqs = _pair_equations(self.equations_by_sheet, ca.sheet, cb.sheet)
            crossing = {(ca.to_sta or "").strip(), (cb.from_sta or "").strip()} - {""}
            hits = [eq for eq in pair_eqs
                    if eq.a.raw.strip() in crossing or eq.b.raw.strip() in crossing]
            if hits:
                on_crossing_eqs.extend(hits)
                pair_eqs_all.extend(pair_eqs)
        if not on_crossing_eqs:
            return placement  # no collision: the other logs stay untouched by construction

        grade = self.human_grades.get(placement.bore_id)
        if grade == "continuous_station_confirmed":
            return placement  # human resolved the collision in favor of the continuous read

        # 2. evidence (runtime + banked human fields)
        exact = all(d is not None and abs(d) <= self.link_tol
                    for d in (placement.footage_delta, placement.start_delta,
                              placement.end_delta))
        precision, spread = _precision_conflict(pair_eqs_all)
        crossing_raws = {eq.a.raw.strip() for eq in on_crossing_eqs} | {
            eq.b.raw.strip() for eq in on_crossing_eqs}
        chain_stas = {(c.from_sta or "").strip() for c in chain} | {
            (c.to_sta or "").strip() for c in chain}
        far_sides = crossing_raws - chain_stas  # the equation side(s) NOT on this chain
        far_match = any((c.from_sta or "").strip() in far_sides for c in all_callouts)
        ev = CollisionEvidence(
            case_id=placement.bore_id,
            on_crossing_reset_equation=True,
            exact_continuous_box_match=exact,
            competing_equation_readings=precision,
            readings_spread_ft=spread if precision else None,
            far_side_matches_reset_station=far_match,
            **_human_fields(grade),
        )

        # 3. classify + demote-only application
        result = classify_collision(ev)
        new_status = simulate_default_status(placement.status.value, result)
        if _STATUS_RANK[new_status] > _STATUS_RANK[placement.status.value]:
            return placement  # hard never-promote backstop (unreachable by construction)
        if new_status == placement.status.value:
            return placement
        update: Dict[str, object] = {
            "status": PlacementStatus(new_status),
            "caveats": list(placement.caveats) + ["RESET_COLLISION_GATE",
                                                  result.classification.value.upper()],
        }
        if new_status == "ABSTAIN":
            update["abstain_reason"] = result.reason
        return placement.model_copy(update=update)
