r"""Cross-sheet transition classifier (M8.2f) -- decide, per chain transition, WHICH
kind of sheet-to-sheet relationship it is BEFORE any link is trusted, so the matcher
can later choose raw continuity vs frame translation vs abstain on EVIDENCE rather than
a blanket rule.

Background (M8.2d / M8.2e): the first frame opt-in treated EVERY cross-sheet link as
requiring a frame edge, so it broke 8 genuinely continuous multi-sheet runs (raw_gap
~= 0 ft, no frame edge) for zero gain. The cure is to classify the transition first:

  same_sheet         -- not a cross-frame transition at all
  continuous_station -- stationing continues across the sheet, no reset edge -> raw link OK
  reset_equation     -- a SAFE frame equation/edge links the two frames -> translate through it
  conflict           -- conflicting frame equations on the pair -> never translate, abstain
  missing_evidence   -- neither raw continuity nor a translating edge -> abstain
  ambiguous          -- BOTH a continuity signal and a reset signal, disagreeing, with no
                        safe precedence rule -> abstain (so a real reset can NEVER be waved
                        through by a coincidental raw equal-station)

This is a HELPER + PROOF aid ONLY. It is NOT wired into ``decide.py`` or the default
``run_match`` and it changes NO placement. It imports only the pure frame-translation
foundation (``match/frames``) and the schema types; it has no IO, no global mutable
state, no convention/customer names, and no old-app imports.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, List, Optional, Sequence, Set, Tuple

from truelinev2.match.frames import frame_for_sheet, translate_between_sheets

if TYPE_CHECKING:  # type-only: no runtime import (keeps the import graph minimal/isolated)
    from truelinev2.schema.frames import FrameGraph
    from truelinev2.schema.models import Callout

# The tolerance the chain assembler links by (match/chains.build_chains ``link_tol``).
DEFAULT_LINK_TOL = 2.0


class TransitionClass(str, Enum):
    """The kind of sheet-to-sheet relationship a chain transition expresses."""
    SAME_SHEET = "same_sheet"
    CONTINUOUS_STATION = "continuous_station"
    RESET_EQUATION = "reset_equation"
    AMBIGUOUS = "ambiguous"
    MISSING_EVIDENCE = "missing_evidence"
    CONFLICT = "conflict"


# Classes for which a link MAY be trusted (raw-continuous, same-sheet, or safely
# translated). The other three -- ambiguous / missing_evidence / conflict -- must ABSTAIN.
_LINKABLE = frozenset({
    TransitionClass.SAME_SHEET,
    TransitionClass.CONTINUOUS_STATION,
    TransitionClass.RESET_EQUATION,
})


@dataclass(frozen=True)
class TransitionEvidence:
    """The raw, classifier-neutral evidence for one transition from sheet A to sheet B.

    ``raw_gap_ft`` / ``translated_gap_ft`` are ``None`` when there are no concrete
    endpoints to measure (a relationship-level classification of two frames). ``None``
    NEVER stands in for zero -- a missing measurement cannot satisfy the ``<= link_tol``
    test, so a transition with no measurable continuity can never become ``continuous``."""
    from_sheet: int
    to_sheet: int
    same_sheet: bool
    has_safe_edge: bool
    conflict: bool
    raw_gap_ft: Optional[float] = None
    translated_gap_ft: Optional[float] = None
    edge_offset_ft: Optional[float] = None


@dataclass(frozen=True)
class TransitionResult:
    """A classified transition plus the evidence that produced it (for reporting)."""
    classification: TransitionClass
    from_sheet: int
    to_sheet: int
    same_sheet: bool
    safe_edge: bool
    conflict: bool
    raw_gap_ft: Optional[float]
    translated_gap_ft: Optional[float]
    edge_offset_ft: Optional[float]
    reason: str

    @property
    def linkable(self) -> bool:
        """True iff a link may be trusted under this classification (same-sheet,
        raw-continuous, or safely translated). ambiguous / missing / conflict -> False."""
        return self.classification in _LINKABLE

    def to_dict(self) -> dict:
        return {
            "from_sheet": self.from_sheet,
            "to_sheet": self.to_sheet,
            "classification": self.classification.value,
            "same_sheet": self.same_sheet,
            "safe_edge": self.safe_edge,
            "conflict": self.conflict,
            "raw_gap_ft": self.raw_gap_ft,
            "translated_gap_ft": self.translated_gap_ft,
            "edge_offset_ft": self.edge_offset_ft,
            "linkable": self.linkable,
            "reason": self.reason,
        }


def classify_evidence(ev: TransitionEvidence, *,
                      link_tol: float = DEFAULT_LINK_TOL) -> TransitionResult:
    """Classify one transition from its evidence. Pure: no IO, no graph access.

    Precedence is deliberate and safety-first:
      1. same sheet                              -> SAME_SHEET (no cross-frame question)
      2. conflicting frame equations             -> CONFLICT (never translate)
      3. a SAFE frame edge links the two frames  -> it is a RESET; consult it FIRST so a
         reset can never be waved through by a coincidental raw equal-station:
           - edge reconciles the endpoints       -> RESET_EQUATION
           - edge does NOT reconcile, but raw continuity is ALSO present (they disagree,
             no safe precedence rule)            -> AMBIGUOUS
           - edge does NOT reconcile, no continuity-> MISSING_EVIDENCE
           - no endpoints to test (relationship) -> RESET_EQUATION (the frames ARE reset-linked)
      4. no safe edge, raw stationing continues  -> CONTINUOUS_STATION (raw link OK)
      5. otherwise                               -> MISSING_EVIDENCE
    """
    def out(klass: TransitionClass, reason: str) -> TransitionResult:
        return TransitionResult(
            classification=klass, from_sheet=ev.from_sheet, to_sheet=ev.to_sheet,
            same_sheet=ev.same_sheet, safe_edge=ev.has_safe_edge, conflict=ev.conflict,
            raw_gap_ft=ev.raw_gap_ft, translated_gap_ft=ev.translated_gap_ft,
            edge_offset_ft=ev.edge_offset_ft, reason=reason)

    if ev.same_sheet:
        return out(TransitionClass.SAME_SHEET, "same sheet: no cross-frame transition")
    if ev.conflict:
        return out(TransitionClass.CONFLICT,
                   "conflicting frame equations on this sheet pair; refuse to translate")
    if ev.has_safe_edge:
        if ev.translated_gap_ft is not None:
            raw_continuous = ev.raw_gap_ft is not None and ev.raw_gap_ft <= link_tol
            if ev.translated_gap_ft <= link_tol:
                return out(TransitionClass.RESET_EQUATION,
                           "safe frame equation translates the link within tolerance")
            if raw_continuous:
                return out(TransitionClass.AMBIGUOUS,
                           "raw continuity and a reset equation are both present and disagree; "
                           "no safe precedence rule -> abstain")
            return out(TransitionClass.MISSING_EVIDENCE,
                       "safe edge present but its offset does not reconcile these endpoints, "
                       "and there is no raw continuity")
        return out(TransitionClass.RESET_EQUATION,
                   "safe frame equation links these two frames (relationship-level)")
    if ev.raw_gap_ft is not None and ev.raw_gap_ft <= link_tol:
        return out(TransitionClass.CONTINUOUS_STATION,
                   "raw stationing continues across the sheet with no reset edge")
    return out(TransitionClass.MISSING_EVIDENCE,
               "no safe frame edge and no raw continuity for this transition")


# --- evidence builders over the real frame graph ------------------------------------

def _sheet_of_frame(frame_id) -> Optional[int]:
    """The plan-sheet number behind a ``sheet:N`` FrameId, or None if not sheet-keyed."""
    try:
        return int(str(frame_id).split(":")[-1])
    except ValueError:
        return None


def conflict_sheet_pairs(graph: "Optional[FrameGraph]") -> Set[Tuple[int, int]]:
    """The ``(lo, hi)`` sheet pairs carrying CONFLICTING frame equations (recorded in
    ``graph.conflicts``) and therefore never translatable. Empty for ``graph=None``."""
    if graph is None:
        return set()
    pairs: Set[Tuple[int, int]] = set()
    for c in graph.conflicts:
        a, b = _sheet_of_frame(c.frame_pair[0]), _sheet_of_frame(c.frame_pair[1])
        if a is not None and b is not None:
            pairs.add((min(a, b), max(a, b)))
    return pairs


def _safe_edge_offset(graph: "Optional[FrameGraph]",
                      from_sheet: int, to_sheet: int) -> Optional[float]:
    """Signed offset (ft) of the SAFE edge translating ``from_sheet`` -> ``to_sheet``
    (``from_feet - to_feet``), or None when no safe direct edge connects the pair."""
    if graph is None:
        return None
    ff, tf = str(frame_for_sheet(from_sheet)), str(frame_for_sheet(to_sheet))
    for e in graph.edges:
        if str(e.from_frame) == ff and str(e.to_frame) == tf:
            return e.offset_ft
        if str(e.from_frame) == tf and str(e.to_frame) == ff:
            return round(-e.offset_ft, 2)
    return None


def evidence_from_callouts(graph: "Optional[FrameGraph]", conflicts: Set[Tuple[int, int]],
                           a: "Callout", b: "Callout") -> TransitionEvidence:
    """Evidence for the adjacency ``a`` (ends ``a.to_ft`` on sheet A) -> ``b`` (starts
    ``b.from_ft`` on sheet B), measured through the safe frame graph (which may be None).
    ``graph=None`` -> no edge is ever found, exactly mirroring the default raw matcher."""
    same = a.sheet == b.sheet
    raw_gap = round(abs(a.to_ft - b.from_ft), 2)
    translated = (None if (same or graph is None)
                  else translate_between_sheets(graph, b.sheet, a.sheet, b.from_ft))
    has_edge = translated is not None
    translated_gap = round(abs(a.to_ft - translated), 2) if has_edge else None
    conflict = (min(a.sheet, b.sheet), max(a.sheet, b.sheet)) in conflicts
    return TransitionEvidence(
        from_sheet=a.sheet, to_sheet=b.sheet, same_sheet=same,
        has_safe_edge=has_edge, conflict=conflict, raw_gap_ft=raw_gap,
        translated_gap_ft=translated_gap,
        edge_offset_ft=_safe_edge_offset(graph, a.sheet, b.sheet))


def evidence_from_sheets(graph: "Optional[FrameGraph]", conflicts: Set[Tuple[int, int]],
                         from_sheet: int, to_sheet: int,
                         from_ft: Optional[float] = None,
                         to_ft: Optional[float] = None) -> TransitionEvidence:
    """Relationship-level evidence between two sheets' frames (no concrete chain). With
    ``from_ft`` (end on the source sheet) and ``to_ft`` (start on the target sheet) given,
    the raw gap and the translated gap are measured; without them the relationship is
    judged from edge / conflict presence alone (used when a bore ABSTAINED so there is no
    placed chain to read transitions from)."""
    same = from_sheet == to_sheet
    raw_gap = (None if (from_ft is None or to_ft is None)
               else round(abs(from_ft - to_ft), 2))
    has_edge = (not same and graph is not None
                and translate_between_sheets(graph, to_sheet, from_sheet, 0.0) is not None)
    translated_gap = None
    if has_edge and from_ft is not None and to_ft is not None:
        translated = translate_between_sheets(graph, to_sheet, from_sheet, to_ft)
        translated_gap = round(abs(from_ft - translated), 2) if translated is not None else None
    conflict = (min(from_sheet, to_sheet), max(from_sheet, to_sheet)) in conflicts
    return TransitionEvidence(
        from_sheet=from_sheet, to_sheet=to_sheet, same_sheet=same,
        has_safe_edge=has_edge, conflict=conflict, raw_gap_ft=raw_gap,
        translated_gap_ft=translated_gap,
        edge_offset_ft=_safe_edge_offset(graph, from_sheet, to_sheet))


# --- convenience wrappers -----------------------------------------------------------

def classify_callout_transition(graph: "Optional[FrameGraph]", conflicts: Set[Tuple[int, int]],
                                a: "Callout", b: "Callout", *,
                                link_tol: float = DEFAULT_LINK_TOL) -> TransitionResult:
    """Classify a single callout adjacency ``a -> b``."""
    return classify_evidence(evidence_from_callouts(graph, conflicts, a, b), link_tol=link_tol)


def classify_sheet_relationship(graph: "Optional[FrameGraph]", conflicts: Set[Tuple[int, int]],
                                from_sheet: int, to_sheet: int, *,
                                from_ft: Optional[float] = None,
                                to_ft: Optional[float] = None,
                                link_tol: float = DEFAULT_LINK_TOL) -> TransitionResult:
    """Classify the relationship between two sheets' frames (no concrete chain needed)."""
    return classify_evidence(
        evidence_from_sheets(graph, conflicts, from_sheet, to_sheet, from_ft, to_ft),
        link_tol=link_tol)


def classify_chain(graph: "Optional[FrameGraph]", conflicts: Set[Tuple[int, int]],
                   callouts: "Sequence[Callout]", *,
                   link_tol: float = DEFAULT_LINK_TOL) -> List[TransitionResult]:
    """Classify every adjacent transition in a callout chain (same-sheet links included,
    classified ``SAME_SHEET``). Empty / length-1 chains have no transitions."""
    cs = list(callouts)
    return [classify_callout_transition(graph, conflicts, a, b, link_tol=link_tol)
            for a, b in zip(cs, cs[1:])]


def cross_sheet_transitions(results: "Sequence[TransitionResult]") -> List[TransitionResult]:
    """Just the cross-sheet transitions from a classified chain (drop SAME_SHEET)."""
    return [r for r in results if not r.same_sheet]
