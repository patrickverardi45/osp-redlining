r"""Read-only printed MATCHLINE BOUNDARY-STATION binder (terminus source type ``MATCHLINE_BOUNDARY_STATION``).

A bore endpoint may land on a printed matchline/boundary station — the station where the bore crosses between
two plan sheets. This binder reuses the SAME printed evidence the engine's cross-sheet continuity check uses
(``matchline_join.see_sheet_crossings`` for ``<MATCH...> STA <n> - SEE SHEET <m>`` equations) and binds an
endpoint ONLY on the strict BILATERAL tier: both adjacent referenced sheets print the SAME boundary station,
inside the bore span. That is exactly the engine's CONFIRMED tier (``MATCHLINE_CONTINUATION_CONFIRMED_REVIEW``);
a UNILATERAL / one-sided matchline is the engine's UNVERIFIED tier and is REFUSED here (never source-bound).

Discipline (matches the structure-note and station-callout binders): bind by EXACT station identity only (never
proximity), refuse rival/ambiguous boundary equations (never coin-flip), and only consider sheet pairs that are
BOTH referenced by the bore (a boundary to an unreferenced sheet is a sheet mismatch and does not bind).

Pure / name-free: the boundary keyword is injected (no convention default); no engine, no render, no placement.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from truelinev2.extract.matchline_join import see_sheet_crossings
from truelinev2.stations import feet_to_station, parse_station

MATCHLINE_BOUND = "MATCHLINE_BOUND"
MATCHLINE_AMBIGUOUS = "MATCHLINE_AMBIGUOUS"
MATCHLINE_NONE = "MATCHLINE_NONE"

# The injected drawn-boundary keyword (mirrors uploaded_corpus_engine_handoff._MATCHLINE_KEYWORD); this binder
# holds no convention default of its own — the caller passes the plan-set's boundary label word.
DEFAULT_KEYWORD = "MATCH"


@dataclass(frozen=True)
class BoundaryEvidence:
    station_ft: float
    station_sta: str
    pair: Tuple[int, int]            # the (lower, higher) sheet pair that BILATERALLY prints it
    source_a: str                    # verbatim equation line on the lower sheet
    source_b: str                    # verbatim equation line on the higher sheet


@dataclass(frozen=True)
class MatchlineBinding:
    result: str                      # MATCHLINE_BOUND | MATCHLINE_AMBIGUOUS | MATCHLINE_NONE
    station: Optional[str] = None
    text: Optional[str] = None       # verbatim matchline equation (lower sheet) when BOUND
    pair: Optional[Tuple[int, int]] = None
    candidates: int = 0


def _equation_line(lines: Sequence[str], station_sta: str, partner: int, keyword: str) -> Optional[str]:
    """The verbatim printed matchline equation line on a sheet that carries ``keyword`` + this station + a
    ``SEE SHEET <partner>`` reference."""
    kw = keyword.upper()
    for ln in lines:
        u = ln.upper()
        if kw in u and station_sta in ln and "SEE" in u and ("SHEET %d" % partner in u or "SHEET%d" % partner in u):
            return ln.strip()
    # fall back to any line carrying the keyword + station (the SEE-SHEET partner was matched upstream)
    for ln in lines:
        if keyword.upper() in ln.upper() and station_sta in ln:
            return ln.strip()
    return None


def bilateral_boundaries(sheet_lines: Dict[int, Sequence[str]], sheets: Sequence[int],
                         lo_ft: float, hi_ft: float, keyword: str = DEFAULT_KEYWORD) -> List[BoundaryEvidence]:
    """Every BILATERAL printed boundary station across the bore's ADJACENT referenced sheet pairs: a station
    printed by BOTH sheets' matchline SEE-SHEET equations and falling inside the bore span. Unilateral (one
    side only) and out-of-span stations are excluded. Read-only; reuses ``see_sheet_crossings``."""
    ordered = sorted({int(s) for s in sheets})
    out: List[BoundaryEvidence] = []
    for a, b in zip(ordered, ordered[1:]):
        la, lb = sheet_lines.get(a, []), sheet_lines.get(b, [])
        cross_ab = see_sheet_crossings(la, b, keyword)        # a -> b equations
        cross_ba = see_sheet_crossings(lb, a, keyword)        # b -> a equations (must reciprocate)
        sta_a = {parse_station(s) for tup in cross_ab for s in tup if parse_station(s) is not None}
        sta_b = {parse_station(s) for tup in cross_ba for s in tup if parse_station(s) is not None}
        for ft in sorted(sta_a & sta_b):                      # bilateral: printed by BOTH sheets
            if not (lo_ft - 1.0 <= ft <= hi_ft + 1.0):
                continue
            sta = feet_to_station(ft)
            src_a = _equation_line(la, sta, b, keyword)
            src_b = _equation_line(lb, sta, a, keyword)
            out.append(BoundaryEvidence(ft, sta, (a, b), src_a or "", src_b or ""))
    return out


def bind_endpoint_matchline(endpoint_sta: str, boundaries: Sequence[BoundaryEvidence]) -> MatchlineBinding:
    """Bind ONE endpoint by EXACT station identity to a BILATERAL boundary. Exactly one distinct boundary ->
    BOUND; two or more rival boundaries at the station -> AMBIGUOUS (never coin-flipped); none -> NONE."""
    matches = [bd for bd in boundaries if bd.station_sta == endpoint_sta]
    # distinct rival boundaries = distinct (pair, source) — a single boundary printed once is unique.
    distinct = {(bd.pair, bd.source_a, bd.source_b) for bd in matches}
    if len(distinct) == 1:
        bd = matches[0]
        return MatchlineBinding(MATCHLINE_BOUND, endpoint_sta, bd.source_a or bd.source_b, bd.pair, 1)
    if len(distinct) >= 2:
        return MatchlineBinding(MATCHLINE_AMBIGUOUS, endpoint_sta, None, None, len(distinct))
    return MatchlineBinding(MATCHLINE_NONE)
