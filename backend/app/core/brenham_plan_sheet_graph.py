"""Brenham Plan Sheet Station Graph — diagnostic evidence (Brenham PH5 only).

Pure helper that models the Brenham detailed-plan-sheet matchline/station
system and evaluates a bore-log group's (print, station-range) against it.
This is the Brenham-native location-truth layer that lives in the PDF plan
sheets (NOT the KMZ — Brenham KMZ has zero station anchors, per the R2a
probe).

**DIAGNOSTIC / OBSERVATION ONLY.** This module never mutates routing state,
never invokes the matching engine, never changes route scoring / selection /
rendering, and never feeds the print-filter or candidate pool. It produces an
evidence dict the caller may write to shadow telemetry or surface in operator
review.

Every seed value traces to extracted PDF matchline evidence from
``Brenham - Phase 5_07-15-25.pdf`` (43 pages). Nothing is fabricated:

  * Sheet ↔ page offset 13 (sheet N = PDF page N+13) — validated by the
    SEE SHEET chain on sheets 3–9.
  * Matchline SEE SHEET edges — extracted "SEE SHEET X" references per sheet.
  * Boundary matchline STA values — the SAME "MATCHLINE STA a+bb - SEE SHEET X"
    value appears on both adjacent sheets (proven for the main chain 3–9 and
    the Niebuhr / Glenda clusters).
  * Per-sheet station windows — extracted STA callout ranges (APPROXIMATE;
    callouts mix multiple corridors on some sheets — used for diagnostic
    context only, not as authoritative extents).

Stationing is MIXED: continuous within each matchline-connected corridor,
independent axis per corridor, and some sheets carry multiple corridors.
The unit of continuous stationing is therefore the CORRIDOR (a connected
component over matchline edges), not the sheet and not the whole job.

Schema version: ``brenham-plan-sheet-graph-1``.

DO NOT IMPORT FROM main.py. DO NOT TOUCH STATE. Brenham-only — do NOT apply
to ODOT or Victoria corpora.
"""

from __future__ import annotations

import re
from typing import Any, Dict, FrozenSet, List, Optional, Sequence, Tuple


SCHEMA_VERSION = "brenham-plan-sheet-graph-1"

# Sheet N is rendered on PDF page N + PAGE_OFFSET in the 07-15-25 design set.
# Validated by the SEE SHEET chain: sheet 4 (page 17) references SEE SHEET 3
# and 5; sheet 5 (page 18) references 4 and 6; etc.
PAGE_OFFSET = 13
SHEET_MIN = 1
SHEET_MAX = 30

# Matchline SEE SHEET edges (undirected). Extracted "SEE SHEET X" references
# from each detailed sheet's text. Connected components over these edges are
# the corridors.
_MATCHLINE_EDGES: Tuple[Tuple[int, int], ...] = (
    (2, 21),
    (3, 4), (3, 23),
    (4, 5),
    (5, 6),
    (6, 7),
    (7, 8),
    (8, 9),
    (10, 12), (10, 13),
    (13, 14),
    (17, 20), (17, 21),
    (18, 22),
    (23, 24),
    (25, 29),
    (26, 27), (27, 28),
)

# Boundary matchline STA (feet) where the SAME value appears on BOTH adjacent
# sheets (proven shared boundary, i.e. the corridor is continuous across the
# matchline at this station). Keyed by the unordered sheet pair.
_BOUNDARY_STA_FT: Dict[FrozenSet[int], float] = {
    frozenset((3, 4)): 1625.0,    # "MATCHLINE STA 16+25 - SEE SHEET 4/3"
    frozenset((4, 5)): 2018.0,    # "STA 20+18 - SEE SHEET 5/4"
    frozenset((5, 6)): 2411.0,    # "STA 24+11 - SEE SHEET 6/5"
    frozenset((6, 7)): 2671.0,    # "STA 26+71 - SEE SHEET 7/6"
    frozenset((7, 8)): 3064.0,    # "STA 30+64 - SEE SHEET 8/7"
    frozenset((8, 9)): 3393.0,    # "STA 33+93 - SEE SHEET 9/8"
    frozenset((17, 20)): 182.0,   # "STA 1+82 - SEE SHEET 20/17" (Niebuhr, local)
    frozenset((17, 21)): 161.0,   # "STA 1+61 - SEE SHEET 21/17" (Niebuhr, local)
    frozenset((2, 21)): 163.0,    # "STA 1+63 - SEE SHEET 2"     (Niebuhr, local)
    frozenset((25, 29)): 36.0,    # "STA 0+36 - SEE SHEET 29/25" (Glenda, low)
    frozenset((26, 27)): 2105.0,  # "STA 21+05 - SEE SHEET 27/26" (Glenda, high)
    frozenset((27, 28)): 218.0,   # "STA 2+18 - SEE SHEET 28/27"  (Glenda, low)
}

# Per-sheet extracted station window [lo_ft, hi_ft] from STA callout scan.
# APPROXIMATE — some sheets mix multiple corridors so the window is a loose
# envelope. Sheet 19 (page 32) is image-only with no parseable callouts and
# is intentionally absent. Used for diagnostic context + per-sheet window
# checks, never as an authoritative corridor extent.
_SHEET_WINDOW_FT: Dict[int, Tuple[float, float]] = {
    1: (0.0, 519.0), 2: (0.0, 1266.0), 3: (0.0, 1625.0), 4: (1625.0, 2018.0),
    5: (0.0, 2411.0), 6: (192.0, 2671.0), 7: (0.0, 4401.0), 8: (0.0, 3393.0),
    9: (611.0, 3890.0), 10: (0.0, 4533.0), 11: (139.0, 514.0), 12: (190.0, 507.0),
    13: (160.0, 398.0), 14: (389.0, 1044.0), 15: (402.0, 1166.0), 16: (1284.0, 1355.0),
    17: (0.0, 3701.0), 18: (0.0, 1222.0), 20: (175.0, 721.0), 21: (0.0, 663.0),
    22: (176.0, 390.0), 23: (0.0, 938.0), 24: (0.0, 1003.0), 25: (0.0, 1930.0),
    26: (231.0, 2130.0), 27: (0.0, 2795.0), 28: (160.0, 832.0), 29: (36.0, 603.0),
    30: (1189.0, 1482.0),
}

# Diagnostic status values.
STATUS_WITHIN_CORRIDOR = "within_corridor"
STATUS_OUTSIDE_CORRIDOR_EXTENT = "outside_corridor_extent"
STATUS_MULTI_CORRIDOR_SPAN = "multi_corridor_span"
STATUS_STATION_PRINT_DISJOINT = "station_print_disjoint"
STATUS_EXTERNAL_PACKET_MISMATCH = "external_packet_mismatch_possible"
STATUS_UNKNOWN = "unknown"

_STATION_RE = re.compile(r"^\s*(?:STA\.?\s*)?(\d{1,3})\+(\d{2}(?:\.\d+)?)\s*$", re.IGNORECASE)
_FT_DECIMALS = 3


# ── small helpers ───────────────────────────────────────────────────────────

def _r(v: Any) -> float:
    try:
        return round(float(v), _FT_DECIMALS)
    except (TypeError, ValueError):
        return 0.0


def parse_station_label(label: Any) -> Optional[float]:
    """Parse a station label like ``"16+25"`` or ``"STA 16+25"`` to feet
    (1625.0). Returns None on unparseable input. Pure, never raises."""
    if label is None:
        return None
    if isinstance(label, (int, float)):
        try:
            f = float(label)
            return f if f == f else None  # reject NaN
        except (TypeError, ValueError):
            return None
    if not isinstance(label, str):
        return None
    m = _STATION_RE.match(label)
    if not m:
        return None
    try:
        return float(m.group(1)) * 100.0 + float(m.group(2))
    except (TypeError, ValueError):
        return None


def sheet_to_page(sheet: int) -> Optional[int]:
    """Sheet number → PDF page (sheet N = page N+13). None if out of range."""
    try:
        s = int(sheet)
    except (TypeError, ValueError):
        return None
    if s < SHEET_MIN or s > SHEET_MAX:
        return None
    return s + PAGE_OFFSET


def _parse_prints(prints: Any) -> List[int]:
    """Coerce a prints value (list of ints, or a string like '5,6,17') into a
    sorted unique list of valid sheet integers in [1,30]."""
    out: set = set()
    items: List[Any] = []
    if isinstance(prints, (list, tuple)):
        items = list(prints)
    elif isinstance(prints, str):
        items = re.split(r"[,\s/]+", prints)
    elif isinstance(prints, (int, float)):
        items = [prints]
    for it in items:
        try:
            v = int(str(it).strip())
        except (TypeError, ValueError):
            continue
        if SHEET_MIN <= v <= SHEET_MAX:
            out.add(v)
    return sorted(out)


# ── corridor graph (connected components over matchline edges) ──────────────

def build_corridors() -> List[List[int]]:
    """Build corridor connected-components from the matchline SEE SHEET edges.

    Returns a deterministic list of corridors, each a sorted list of sheet
    numbers. Isolated sheets (no matchline edge) are NOT included as their own
    corridor here — use ``corridor_for_sheet`` which returns a singleton for
    those. Deterministic: sorted by smallest member.
    """
    adj: Dict[int, set] = {}
    for a, b in _MATCHLINE_EDGES:
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
    seen: set = set()
    corridors: List[List[int]] = []
    for node in sorted(adj.keys()):
        if node in seen:
            continue
        # BFS
        comp: set = set()
        stack = [node]
        while stack:
            cur = stack.pop()
            if cur in comp:
                continue
            comp.add(cur)
            for nb in adj.get(cur, ()):  # deterministic via sorted extend
                if nb not in comp:
                    stack.append(nb)
        seen |= comp
        corridors.append(sorted(comp))
    corridors.sort(key=lambda c: c[0] if c else 0)
    return corridors


def corridor_for_sheet(sheet: int) -> List[int]:
    """Return the sorted corridor (connected component) containing ``sheet``.
    Sheets with no matchline edge return a singleton ``[sheet]``."""
    for corridor in build_corridors():
        if sheet in corridor:
            return corridor
    return [sheet]


def corridor_extent_ft(corridor: Sequence[int]) -> Optional[Tuple[float, float]]:
    """Compute an approximate continuous station extent (lo, hi) for a corridor
    by unioning the proven boundary STA values and the per-sheet windows of its
    member sheets. Returns None when no station evidence exists for the
    corridor. Diagnostic only."""
    los: List[float] = []
    his: List[float] = []
    members = set(int(s) for s in corridor)
    for pair, sta in _BOUNDARY_STA_FT.items():
        if pair & members:
            los.append(sta)
            his.append(sta)
    for s in members:
        win = _SHEET_WINDOW_FT.get(s)
        if win:
            los.append(win[0])
            his.append(win[1])
    if not los:
        return None
    return (min(los), max(his))


# ── bore-log evaluation ─────────────────────────────────────────────────────

def evaluate_bore_log(
    *,
    prints: Any,
    station_min_ft: Optional[float] = None,
    station_max_ft: Optional[float] = None,
    notes_streets: Optional[Sequence[str]] = None,
    index_streets: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Evaluate a bore-log group's prints + station range against the Brenham
    plan-sheet station graph. Pure, deterministic, never raises.

    Args:
      prints: list[int] or string like "5,6,17,21".
      station_min_ft / station_max_ft: the bore-log group's station range (ft).
      notes_streets: street names extracted from the bore-log notes (optional).
      index_streets: streets the print index associates with these prints
        (optional). When both are provided and notes_streets has a street not
        in index_streets, an external-packet mismatch is flagged.

    Returns an evidence dict (schema ``brenham-plan-sheet-graph-1``):
      {schema_version, prints, sheets, pages, corridors, corridor_count,
       corridor_extents, sheet_windows, station_range, status, status_reasons}

    Status (single primary, precedence high→low):
      external_packet_mismatch_possible
      station_print_disjoint
      outside_corridor_extent
      multi_corridor_span
      within_corridor
      unknown
    """
    sheets = _parse_prints(prints)
    pages = [sheet_to_page(s) for s in sheets]
    reasons: List[str] = []

    # Corridors spanned by the prints.
    corridor_keys: List[Tuple[int, ...]] = []
    corridor_of: Dict[int, Tuple[int, ...]] = {}
    for s in sheets:
        c = tuple(corridor_for_sheet(s))
        corridor_of[s] = c
        if c not in corridor_keys:
            corridor_keys.append(c)
    corridors = [list(c) for c in corridor_keys]
    corridor_count = len(corridor_keys)

    corridor_extents = {
        ",".join(str(x) for x in c): corridor_extent_ft(c) for c in corridor_keys
    }
    sheet_windows = {str(s): _SHEET_WINDOW_FT.get(s) for s in sheets}

    smin = station_min_ft
    smax = station_max_ft
    have_station = isinstance(smin, (int, float)) and isinstance(smax, (int, float))
    if have_station and smin > smax:
        smin, smax = smax, smin

    # External-packet mismatch (e.g. Lunar CHERI/LAWNDALE reuse Brenham print
    # numbers but reference non-Brenham streets).
    external_mismatch = False
    if notes_streets and index_streets is not None:
        ns = {str(x).strip().upper() for x in notes_streets if str(x).strip()}
        idx = {str(x).strip().upper() for x in index_streets if str(x).strip()}
        if ns and not (ns & idx):
            external_mismatch = True
            reasons.append(
                f"notes streets {sorted(ns)} disjoint from index streets {sorted(idx)}"
            )

    # Station/print disjoint: station range outside ALL of the prints' sheet
    # windows (the hard anomaly, e.g. bore_log16).
    station_print_disjoint = False
    if have_station and sheets:
        windows = [_SHEET_WINDOW_FT.get(s) for s in sheets]
        windows = [w for w in windows if w]
        if windows:
            inside_any = any(not (smax < w[0] or smin > w[1]) for w in windows)
            if not inside_any:
                station_print_disjoint = True
                reasons.append(
                    f"station {_r(smin)}-{_r(smax)} outside all sheet windows {windows}"
                )

    # Outside corridor extent: station range outside ALL spanned corridors.
    outside_corridor_extent = False
    if have_station and corridor_keys:
        extents = [corridor_extent_ft(list(c)) for c in corridor_keys]
        extents = [e for e in extents if e]
        if extents:
            inside_any = any(not (smax < e[0] or smin > e[1]) for e in extents)
            if not inside_any:
                outside_corridor_extent = True
                reasons.append(
                    f"station {_r(smin)}-{_r(smax)} outside all corridor extents {extents}"
                )

    multi_corridor_span = corridor_count > 1
    if multi_corridor_span:
        reasons.append(f"prints span {corridor_count} corridors: {corridors}")

    # Primary status precedence.
    if not sheets:
        status = STATUS_UNKNOWN
        reasons.append("no valid prints in [1,30]")
    elif external_mismatch:
        status = STATUS_EXTERNAL_PACKET_MISMATCH
    elif station_print_disjoint:
        status = STATUS_STATION_PRINT_DISJOINT
    elif outside_corridor_extent:
        status = STATUS_OUTSIDE_CORRIDOR_EXTENT
    elif multi_corridor_span:
        status = STATUS_MULTI_CORRIDOR_SPAN
    else:
        status = STATUS_WITHIN_CORRIDOR

    return {
        "schema_version": SCHEMA_VERSION,
        "prints": sheets,
        "sheets": sheets,
        "pages": pages,
        "corridors": corridors,
        "corridor_count": corridor_count,
        "corridor_extents": corridor_extents,
        "sheet_windows": sheet_windows,
        "station_range": [_r(smin), _r(smax)] if have_station else None,
        "status": status,
        "status_reasons": reasons,
    }


# ── operator-review precision filter ────────────────────────────────────────
#
# The Match Review Queue (MRQ) only wants the ACTIONABLE PSG statuses. The
# common/low-discrimination statuses (within_corridor, multi_corridor_span) and
# the precedence-masked outside_corridor_extent are intentionally EXCLUDED — the
# first real Brenham telemetry review (2026-05-28) showed multi_corridor_span on
# 57% of groups, so surfacing it would be noise, not signal.
REVIEW_EVIDENCE_SCHEMA_VERSION = "plan-sheet-graph-evidence-1"

MRQ_ACTIONABLE_STATUSES: FrozenSet[str] = frozenset({
    STATUS_STATION_PRINT_DISJOINT,
    STATUS_EXTERNAL_PACKET_MISMATCH,
    STATUS_UNKNOWN,
})


def _actionability_for(status: str) -> str:
    """Actionability label for an actionable status. Pure."""
    if status in (STATUS_STATION_PRINT_DISJOINT, STATUS_EXTERNAL_PACKET_MISMATCH):
        return "high"
    if status == STATUS_UNKNOWN:
        return "data_quality"
    return "low"


def build_review_evidence(
    *,
    prints: Any,
    station_min_ft: Optional[float] = None,
    station_max_ft: Optional[float] = None,
    notes_streets: Optional[Sequence[str]] = None,
    index_streets: Optional[Sequence[str]] = None,
) -> Optional[Dict[str, Any]]:
    """Evaluate a bore-log group and return a COMPACT operator-review evidence
    dict — but ONLY when the resulting status is actionable enough to warrant
    operator attention (see ``MRQ_ACTIONABLE_STATUSES``).

    Returns ``None`` for the common/noisy statuses (``within_corridor``,
    ``multi_corridor_span``) and for ``outside_corridor_extent`` (masked by
    precedence on real corpora). This is the precision filter that gates PSG
    evidence into the Match Review Queue.

    Pure, deterministic, never raises. DIAGNOSTIC / OBSERVATION ONLY — never
    mutates routing state, scoring, selection, or rendering. Schema version
    ``plan-sheet-graph-evidence-1``.
    """
    try:
        ev = evaluate_bore_log(
            prints=prints,
            station_min_ft=station_min_ft,
            station_max_ft=station_max_ft,
            notes_streets=notes_streets,
            index_streets=index_streets,
        )
    except Exception:
        return None
    status = ev.get("status")
    if status not in MRQ_ACTIONABLE_STATUSES:
        return None

    out: Dict[str, Any] = {
        "schema_version": REVIEW_EVIDENCE_SCHEMA_VERSION,
        "status": status,
        "actionability": _actionability_for(status),
        "reasons": list(ev.get("status_reasons") or []),
        "prints": list(ev.get("prints") or []),
        "sheets": list(ev.get("sheets") or []),
        "corridors": [list(c) for c in (ev.get("corridors") or [])],
        "station_range": ev.get("station_range"),
    }
    # Echo the streets that drove an external-packet mismatch when available.
    # Read-only: never derives new streets; only reflects what was passed in.
    if index_streets:
        idx = [str(s) for s in index_streets if str(s).strip()]
        if idx:
            out["index_streets"] = idx
    if notes_streets:
        ns = [str(s) for s in notes_streets if str(s).strip()]
        if ns:
            out["notes_streets"] = ns
    return out
