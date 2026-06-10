r"""M8.14.b.1 -- structure IDENTITY binding (pure; identity only, no position).

Binds a bore endpoint to its owning STRUCTURE by printed identity evidence --
never by metric/nearest fit (the banked trap: ladder-extrapolation consistency
selects the WRONG installer HH for log7, 2+22=0+00 over the true 0+55=0+00).

Two deterministic identity keys:
  * START: exact value equality ``bore.station_start_ft ==
    StructureOrigin.parent_station_ft`` -- the bore log's own start station
    NAMES its frame-origin structure (log7: 55.0 == STA 0+55=0+00 INSTALLER
    HH, unique among the sheet's five origins). No tolerance exists here.
  * END: a structure NOTE line ``STA <end> <structure...>`` -- note grammar
    excludes ``STA a TO STA b`` run callouts and ``=0+00`` equations, and the
    note must carry a known structure keyword on its own/following lines.

Uniqueness mandatory: 0 or >= 2 candidates -> named abstain
(STRUCTURE_IDENTITY_BINDING_REQUIRED). Position resolution (symbol layers,
leader geometry) is deliberately NOT here -- that is M8.14.b.2, gated on the
r3 lesson (never draw to leader-offset labels). No v1 import; no rendering.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from truelinev2.proof.station_equation_ownership import StructureOrigin
from truelinev2.stations import feet_to_station

BOUND = "STRUCTURE_IDENTITY_BOUND"
REQUIRED = "STRUCTURE_IDENTITY_BINDING_REQUIRED"

_STRUCTURE_WORDS = ("FLOWER POT", "INSTALLER HH", "PORT HH", "NEXTLINK HH",
                    "SPLICE", "TERMINAL")
_STA_LINE = re.compile(r"^STA\s+(\d{1,3}\+\d{2})\b")


@dataclass(frozen=True)
class OriginBinding:
    result: str
    bore_start_ft: float
    origin: Optional[StructureOrigin] = None
    rival_parent_stations: Tuple[float, ...] = ()
    named_missing_relationship: Optional[str] = None


@dataclass(frozen=True)
class EndNoteBinding:
    result: str
    end_station: str
    note_line: Optional[str] = None
    structure_label: Optional[str] = None
    candidates: int = 0
    named_missing_relationship: Optional[str] = None


def bind_origin_by_parent_station(bore_start_ft: float,
                                  origins: Sequence[StructureOrigin]
                                  ) -> OriginBinding:
    """EXACT equality only -- a near-miss is not an identity. 0/>=2 -> abstain."""
    matches = [o for o in origins if o.parent_station_ft == bore_start_ft]
    others = tuple(sorted(o.parent_station_ft for o in origins
                          if o.parent_station_ft != bore_start_ft))
    if len(matches) == 1:
        return OriginBinding(result=BOUND, bore_start_ft=bore_start_ft,
                             origin=matches[0], rival_parent_stations=others)
    if not matches:
        named = (f"no printed =0+00 equation's parent station equals the bore "
                 f"start {bore_start_ft} ft (sheet origins: {others or 'none'}); "
                 f"the start structure is implicit/unprinted -- identity cannot "
                 f"be bound from this sheet's text; guessing is forbidden")
    else:
        named = (f"{len(matches)} =0+00 equations share parent station "
                 f"{bore_start_ft} ft -- identity is ambiguous; never chosen "
                 f"between")
    return OriginBinding(result=REQUIRED, bore_start_ft=bore_start_ft,
                         rival_parent_stations=others,
                         named_missing_relationship=named)


def _note_candidates(end_sta: str, lines: Sequence[str]) -> List[Tuple[str, str]]:
    """(note_line, structure_label) for structure-note lines at ``end_sta``.
    Grammar: the line opens ``STA <end_sta>`` and is neither a run callout
    (``... TO STA ...``) nor an equation (``=0+00``); the structure keyword may
    sit on the same line or the following lines up to the next ``STA`` line."""
    out: List[Tuple[str, str]] = []
    for i, ln in enumerate(lines):
        m = _STA_LINE.match(ln.strip())
        if not m or m.group(1) != end_sta:
            continue
        if "TO STA" in ln or "=" in ln:
            continue
        label_parts = [ln.strip()[len(f"STA {end_sta}"):].strip()]
        for nxt in lines[i + 1:i + 5]:
            if _STA_LINE.match(nxt.strip()):
                break
            label_parts.append(nxt.strip())
        label = " ".join(p for p in label_parts if p)
        if any(w in label.upper() for w in _STRUCTURE_WORDS):
            out.append((ln.strip(), label))
    return out


def bind_end_structure_note(end_ft: float, lines: Sequence[str]) -> EndNoteBinding:
    end_sta = feet_to_station(end_ft)
    cands = _note_candidates(end_sta, lines)
    if len(cands) == 1:
        return EndNoteBinding(result=BOUND, end_station=end_sta,
                              note_line=cands[0][0], structure_label=cands[0][1],
                              candidates=1)
    if not cands:
        named = (f"no structure note 'STA {end_sta} <structure>' exists on the "
                 f"sheet (run callouts and =0+00 equations excluded by grammar); "
                 f"the end structure identity cannot be bound from this sheet's "
                 f"text")
    else:
        named = (f"{len(cands)} structure notes share STA {end_sta} -- identity "
                 f"is ambiguous; never chosen between")
    return EndNoteBinding(result=REQUIRED, end_station=end_sta,
                          candidates=len(cands),
                          named_missing_relationship=named)
