r"""M9.3.1 -- TerminusProfile: the injected convention for the terminus-attribution
extractor (match/terminus_attribution.py).

The universal core holds ZERO plan-set literals; everything plan-set-specific lives
HERE, in extract/ (the convention seam). A new company onboards by building its own
TerminusProfile instance (+ a graded specimen). The core duck-types this object --
it reads the fields below and never imports a literal.

This dataclass aggregates the grammars/keywords already proven by the shipped
laws: the structure-note keyword set + station grammar (M8.14.b.1 structure_anchor),
the structure-class keyword table (M8.14.c lane dialect), and the AP / splice / join
grammar + terminal class (M9.0/M9.1 KMZ dialect). Keeping it a single object makes
the injection surface explicit and one-line-auditable.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Tuple

from truelinev2.extract.kmz import BRENHAM_KMZ_DIALECT
from truelinev2.extract.structure_position import BRENHAM_LANE_DIALECT


@dataclass(frozen=True)
class TerminusProfile:
    """Everything the terminus-attribution core needs, injected. Neutral fields --
    no field is plan-set-specific by name; the VALUES carry the convention."""
    # structure-note frame grammar
    station_line_re: str            # group(1) == the station token (e.g. "7+30")
    run_callout_marker: str         # a run-callout line marker (resets the note frame)
    equation_marker: str            # an equation line marker (resets the note frame)
    note_window: int                # lines after the STA line that belong to the frame
    note_keywords: Tuple[str, ...]  # a structure note must carry one of these
    # structure classification: (class, keywords) -- first match wins
    class_keywords: Tuple[Tuple[str, Tuple[str, ...]], ...]
    terminal_class: str             # the class that owns an AP+splice terminus identity
    # identifier grammars
    ap_token: str                   # group(1) == the AP id token
    splice_token: str               # WHOLE splice-loc token (no group -> full match)
    pair_re: str                    # one-line AP+splice pair: group(1)=AP, group(2)=splice
    # AP id TYPE: how the matched AP token becomes a comparable id, consistent with
    # the KMZ side (M9.1 doctrine: AP keys must be a consistent comparable type
    # across both sources). A digit-AP plan set uses ``int``; a zone/alpha-AP plan
    # set (e.g. "A12") supplies ``str``/a normaliser so the id is NOT coerced to int.
    ap_cast: Callable[[str], object] = int
    # run-assembly drop-marker grammar (M9.4.1): the printed token(s) that mark a
    # departing run callout as a fiber-drop / lateral OFF the terminus -- a branch,
    # NEVER the trunk continuing. Injected here so the convention-agnostic run-
    # assembly core (match/run_assembly.py) holds no plan-set drop literal. Empty
    # tuple == this plan set declares no drop grammar (every departure reads as a
    # non-drop run; the core never invents a drop marker).
    drop_markers: Tuple[str, ...] = ()


# Reference profile (the shipped proof specimen). Lives in extract/ -- the only place
# plan-set vocabulary is permitted. The note keywords mirror the M8.14.b.1
# structure-note grammar; class keywords + terminal class + AP/splice grammar reuse
# the shipped lane / KMZ dialects so the extractor and the M9.1 join speak the same
# identifier language.
BRENHAM_TERMINUS_PROFILE = TerminusProfile(
    station_line_re=r"^STA\s+(\d{1,3}\+\d{2})\b",
    run_callout_marker="TO STA",
    equation_marker="=",
    note_window=4,
    note_keywords=("FLOWER POT", "INSTALLER HH", "PORT HH", "NEXTLINK HH",
                   "SPLICE", "TERMINAL"),
    class_keywords=BRENHAM_LANE_DIALECT.class_keywords,
    terminal_class=BRENHAM_KMZ_DIALECT.terminal_class,     # "terminal_port_hh"
    ap_token=BRENHAM_KMZ_DIALECT.ap_token,                 # r"AP\s*-?\s*(\d+)"
    splice_token=r"SPLICE\s*LOC\s*\d+",
    pair_re=r"AP-?\s?(\d+)\s+SPLICE\s*LOC\s*(\d+)",
    ap_cast=int,                                           # digit AP ids; matches the KMZ int APs
    drop_markers=("FOR FIBER DROP",),                      # M9.4.1: the Brenham printed drop-lateral marker
)
