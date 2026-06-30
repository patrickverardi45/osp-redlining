r"""Read-only printed STATION-CALLOUT binder (terminus source type ``PRINTED_STA_CALLOUT``).

A printed run callout brackets a bore by its STATION RANGE, e.g. ``BORE 11+75 TO 13+25`` or ``11+75 - 13+25``.
This binder reads such callouts from a plan page's text and binds a bore endpoint ONLY by EXACT station
identity (a callout whose low station equals the bore start binds the START; whose high station equals the
bore end binds the END). It NEVER binds by proximity, NEVER coin-flips between rivals, and NEVER reads a bare
single station (which carries no span/endpoint identity).

COLD-LANE SAFETY (critical): this binder must NOT read the NAMED-dialect grammars, so a cold/generic fixture
never becomes a recognized-corpus fixture. It therefore SKIPS any line carrying:
  * ``... TO STA ...`` — the Brenham run-callout grammar (``BrenhamDialect.detect`` fires on ``STA a TO STA b``);
  * ``DIR. BORE`` / ``DIR BORE`` — the Brenham footage grammar;
  * ``DIRECTIONAL BORE`` — the ODOT trigger.
The accepted grammar uses NO per-station ``STA`` prefix and excludes ``THRU``/``THROUGH`` (which appear in
benign "ALIGNMENT 10+00 thru 16+00" extent titles) — so the binder's own grammar can never trigger a named
dialect. Pure / name-free: no customer/project/location literal; no engine, no render, no placement.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Sequence

from truelinev2.stations import feet_to_station, parse_station

CALLOUT_BOUND = "CALLOUT_BOUND"
CALLOUT_AMBIGUOUS = "CALLOUT_AMBIGUOUS"
CALLOUT_NONE = "CALLOUT_NONE"

_STA = r"\d{1,3}\+\d{2}(?:\.\d+)?"
# A station RANGE: two stations joined by TO or a dash (en/em/hyphen). NO 'STA' prefix (that is the named
# Brenham grammar) and NO 'THRU'/'THROUGH' (those mark benign alignment-extent titles, not bore callouts).
_SPAN_RE = re.compile(r"(%s)\s*(?:TO|[-‒–—])\s*(%s)" % (_STA, _STA), re.I)
# Named-dialect markers this binder must never read (keeps a cold fixture cold).
_NAMED_RUN_RE = re.compile(r"TO\s+STA", re.I)
_NAMED_DIRBORE_RE = re.compile(r"DIR\.?\s*BORE", re.I)
_NAMED_DIRECTIONAL = "DIRECTIONAL BORE"


@dataclass(frozen=True)
class SpanCallout:
    from_ft: float       # the LOW station (feet)
    from_sta: str        # the LOW station label, e.g. "11+75"
    to_ft: float         # the HIGH station (feet)
    to_sta: str          # the HIGH station label, e.g. "13+25"
    text: str            # verbatim printed line


@dataclass(frozen=True)
class CalloutBinding:
    result: str                      # CALLOUT_BOUND | CALLOUT_AMBIGUOUS | CALLOUT_NONE
    station: Optional[str] = None
    text: Optional[str] = None       # verbatim callout line when BOUND
    candidates: int = 0


def _is_named_line(s: str) -> bool:
    u = s.upper()
    return bool(_NAMED_RUN_RE.search(s) or _NAMED_DIRBORE_RE.search(s) or _NAMED_DIRECTIONAL in u)


def span_callouts(lines: Sequence[str]) -> List[SpanCallout]:
    """Every name-free station-range callout on the page (named-dialect lines skipped). A reversed range is
    normalized to (low, high); a degenerate same-station range is ignored (not a span)."""
    out: List[SpanCallout] = []
    for ln in lines:
        s = ln.strip()
        if not s or _is_named_line(s):
            continue
        m = _SPAN_RE.search(s)
        if not m:
            continue
        a, b = parse_station(m.group(1)), parse_station(m.group(2))
        if a is None or b is None or a == b:
            continue
        lo, hi = (a, b) if a < b else (b, a)
        out.append(SpanCallout(lo, feet_to_station(lo), hi, feet_to_station(hi), s))
    return out


def bind_endpoint_callout(which: str, endpoint_sta: str, spans: Sequence[SpanCallout]) -> CalloutBinding:
    """Bind ONE endpoint by EXACT station identity to a span callout: START matches a callout's LOW station,
    END matches a callout's HIGH station. Exactly one match -> BOUND; two or more -> AMBIGUOUS (never
    coin-flipped); none -> NONE."""
    if which == "START":
        matches = [c for c in spans if c.from_sta == endpoint_sta]
    else:
        matches = [c for c in spans if c.to_sta == endpoint_sta]
    if len(matches) == 1:
        return CalloutBinding(CALLOUT_BOUND, endpoint_sta, matches[0].text, 1)
    if len(matches) >= 2:
        return CalloutBinding(CALLOUT_AMBIGUOUS, endpoint_sta, None, len(matches))
    return CalloutBinding(CALLOUT_NONE)


def anchored_disagreement(which: str, endpoint_sta: str, other_sta: str,
                          spans: Sequence[SpanCallout]) -> Optional[str]:
    """Detect a printed span callout ANCHORED to the bore's OTHER endpoint (exact match) whose THIS-endpoint
    station DISAGREES with ``endpoint_sta`` — the source-conflict signal. Returns the disagreeing printed
    station, else None. (Only meaningful when another printed source also binds this endpoint.)"""
    if which == "END":
        anchored = [c for c in spans if c.from_sta == other_sta and c.to_sta != endpoint_sta]
        return anchored[0].to_sta if anchored else None
    anchored = [c for c in spans if c.to_sta == other_sta and c.from_sta != endpoint_sta]
    return anchored[0].from_sta if anchored else None
