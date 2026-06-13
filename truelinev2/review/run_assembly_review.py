r"""M9.4.1 -- RUN-ASSEMBLY review card: a standalone, schema-versioned review surface
for a typed SHARED-TERMINAL-NODE evidence item (match.run_assembly).

Mirrors the M8.20 §7 group card (review/group_review.py): it is NOT the per-bore
M8.10/M8.11 reviewer contracts and is NOT wired into resolve_bore / the sweep / the
reviewer service -- so no per-bore status, census, card count, or contract changes.
It lets a reviewer see a bore-to-bore junction as ONE review item -- an END bore's
terminus and the bore that departs it -- WITHOUT corrupting per-bore placement truth:

  * REVIEW-only by construction (there is no AUTO branch); the only label is
    ``SUGGESTION_NOT_PLACEMENT``; the action CONFIRMS/REJECTS the run-assembly
    relationship, never places;
  * the card carries NO geometry and NO strokes (no such field exists; the validator
    forbids any geometry key) -- a shared terminal node is not a drawn redline;
  * a DROP_BRANCH item is explicitly typed as a fiber-drop LATERAL, never a
    continuation -- so a reviewer is never led to read a drop as the trunk;
  * only the two SHARED-TERMINAL evidence dispositions build a card (a typed blocker
    -- competing / contradiction / unmodeled -- yields NO card).

Validation IS the contract (pydantic, fail-closed). No engine wiring, no UI, no
geometry, no rendering. This module holds zero plan-set literals (drift-guarded).
"""
from __future__ import annotations

from typing import List, Optional, Sequence

from pydantic import BaseModel, ConfigDict, model_validator

from truelinev2.match import run_assembly as RA

RUN_ASSEMBLY_SCHEMA_VERSION = "truelinev2-run-assembly-review-1"
# the frozen suggestion label (mirrors the canonical SUGGESTION_NOT_PLACEMENT used by
# the M8.10/M8.20 review surfaces -- a card never places).
SUGGESTION_LABEL = "SUGGESTION_NOT_PLACEMENT"
HUMAN_ACTION = "CONFIRM_OR_REJECT_RUN_ASSEMBLY"
# the two review continuation classes a card may carry
CONTINUATION_CANDIDATE = "RUN_CONTINUATION_CANDIDATE"
DROP_BRANCH = "JUNCTION_DROP_BRANCH"
# map a core evidence disposition -> the card's continuation class
_DISPOSITION_TO_CONTINUATION = {
    RA.RUN_ASSEMBLY_REVIEW_CANDIDATE: CONTINUATION_CANDIDATE,
    RA.JUNCTION_DROP_BRANCH: DROP_BRANCH,
}
# geometry / stroke keys that may NEVER appear anywhere in a card.
_FORBIDDEN_GEOMETRY = ("segments", "stroke_points", "stroke_rgb", "walk_points",
                       "boundary_xy", "lon", "lat", "geometry")


def _assert_no_geometry(value, path: str = "$") -> None:
    """Walk the serialized card; any geometry/stroke key fails closed."""
    if isinstance(value, dict):
        for key, child in value.items():
            if key in _FORBIDDEN_GEOMETRY and child is not None:
                raise ValueError(f"geometry/stroke key {key!r} carrying a value at {path}")
            _assert_no_geometry(child, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _assert_no_geometry(child, f"{path}[{index}]")


class RunAssemblyReviewCard(BaseModel):
    """A bore-to-bore junction surfaced as ONE REVIEW item. REVIEW/evidence-only;
    no geometry, no strokes, no AUTO; per-bore truth untouched."""
    model_config = ConfigDict(frozen=True)
    schema_version: str = RUN_ASSEMBLY_SCHEMA_VERSION
    relation: str = RA.RELATION_SHARED_TERMINAL
    end_bore: str
    start_bore: str
    terminal_ap: object
    splice_loc: Optional[str]
    end_station: Optional[str]
    start_station: Optional[str]
    continuation_class: str
    departure_run_class: str
    competing_departures: int
    review_only: bool = True
    auto: bool = False
    has_geometry: bool = False
    has_strokes: bool = False
    terminal_is_end_of_feed: bool = True
    label: str = SUGGESTION_LABEL
    human_action: str = HUMAN_ACTION
    detail: str

    @model_validator(mode="after")
    def _card_contract(self) -> "RunAssemblyReviewCard":
        if self.schema_version != RUN_ASSEMBLY_SCHEMA_VERSION:
            raise ValueError("run-assembly card schema version is pinned")
        if self.relation != RA.RELATION_SHARED_TERMINAL:
            raise ValueError("the card relation is the SHARED-TERMINAL fact; pinned")
        if (self.review_only is not True or self.auto is not False):
            raise ValueError("the run-assembly card is REVIEW-only; AUTO can never be "
                             "claimed")
        if self.has_geometry or self.has_strokes:
            raise ValueError("a run-assembly card carries NO geometry and NO strokes")
        if self.label != SUGGESTION_LABEL:
            raise ValueError("the suggestion label is frozen -- a card never places")
        if self.human_action != HUMAN_ACTION:
            raise ValueError("the action confirms/rejects the run assembly, never places")
        if self.continuation_class not in (CONTINUATION_CANDIDATE, DROP_BRANCH):
            raise ValueError("continuation_class must be a CANDIDATE or a DROP_BRANCH")
        if self.end_bore == self.start_bore:
            raise ValueError("a run-assembly card is bore-to-bore (a self-junction is "
                             "never a card)")
        # a DROP_BRANCH must be a positively-detected drop -- never a silent
        # continuation; a CANDIDATE must NOT be a drop.
        if self.continuation_class == DROP_BRANCH \
                and self.departure_run_class != RA.DEP_DROP:
            raise ValueError("a DROP_BRANCH card must carry a positively-detected drop "
                             "departure (departure_run_class == 'drop')")
        if self.continuation_class == CONTINUATION_CANDIDATE \
                and self.departure_run_class == RA.DEP_DROP:
            raise ValueError("a drop departure can never be a continuation CANDIDATE")
        if not self.terminal_is_end_of_feed:
            raise ValueError("a terminal is END-of-feed by the M9.3.1 direction law")
        _assert_no_geometry(self.model_dump())
        return self


def build_run_assembly_cards(
        evidence_items: Sequence[RA.RunAssemblyEvidence]
) -> List[RunAssemblyReviewCard]:
    """Consume the run-assembly extractor's typed evidence -> REVIEW cards, ONE per
    SHARED-TERMINAL evidence item. A typed BLOCKER (competing / contradiction /
    unmodeled / self-junction) yields NO card -- a non-evidence relation is never
    surfaced. PURE: it reads the typed facts, re-runs no law, writes no engine state.
    For a DROP_BRANCH the card is explicitly a fiber-drop lateral, never a trunk."""
    cards: List[RunAssemblyReviewCard] = []
    for e in evidence_items:
        cont = _DISPOSITION_TO_CONTINUATION.get(e.disposition)
        if cont is None:                       # a typed blocker -> not surfaced
            continue
        kind = ("a fiber-drop lateral OFF the terminus (NOT the trunk continuing)"
                if cont == DROP_BRANCH else
                "a candidate run continuation (the reviewer commits the run)")
        cards.append(RunAssemblyReviewCard(
            end_bore=e.end_bore, start_bore=e.start_bore, terminal_ap=e.terminal_ap,
            splice_loc=e.splice_loc, end_station=e.end_station,
            start_station=e.start_station, continuation_class=cont,
            departure_run_class=e.departure_run_class,
            competing_departures=e.competing_departures,
            detail=(f"{e.end_bore} END terminates at terminal AP {e.terminal_ap} "
                    f"({e.splice_loc}); {e.start_bore} departs the SAME terminal -- "
                    f"{kind}.")))
    return cards
