"""STATION / FOOTAGE DOTS along a human-confirmed redline (PURE; no engine/dialect/match/sweep/PDF import).

The simple V1 workflow: once a customer draws a two-point (or multi-bend) redline from control points, the app
drops interval dots along it — every 50' by default, plus the final endpoint even when it is not on a 50'
boundary — and each dot is clickable, carrying that bore's log info. This module computes those dots.

It is deliberately geometry-only and schema-agnostic:
  * SELF-CALIBRATING SCALE. It never uses a dialect's drawn pts/ft; the scale is the reviewed row's own
    footage divided by the drawn polyline's total display-space length (ft-per-pt for THIS redline). A dot at
    footage F sits at arc-length ``F / footage * total_length`` along the polyline — honest to the two things
    the human actually asserted (the endpoints they clicked and the footage on the bore-log row).
  * STATION IS DERIVED, NEVER INVENTED. A dot's station label is ``start_station + footage_along`` only when
    the start station parses; otherwise ``station`` is None but ``footage_along`` is always present.
  * NO PLACEMENT. It infers no geometry beyond interpolating along the human's own polyline; it solves no
    stations against the plan, matches nothing, and imports nothing from the engine / dialects / renderer /
    match / sweep. Degenerate input (< 2 points, zero-length polyline, non-positive footage) -> no dots.

Provenance on every dot is HUMAN_CONFIRMED_CONTROL_POINTS (never AUTO, never the deterministic frontier).

ADDENDUM (Mission 8, owner's STATION-DOT CONTRACT, ``.foreman/scratch/m8/design-dots.md``, BINDING): by
EXPLICIT owner instruction, the render/ fence is lifted -- ADDITIVELY ONLY -- on exactly two functions
below, ``compute_station_dots`` and ``stroke_polyline_with_dots``, to accept an optional ``marks``
parameter (a list of evidence-bound dot definitions built by ``contracts/station_marks.py``). ``marks``
defaults to ``None``, in which case both functions reproduce their PRE-ADDENDUM behavior byte-for-byte
(covered by a locked identity test) -- every other function in this module is untouched.
"""
from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from truelinev2.stations import feet_to_station, parse_station

PROVENANCE_HUMAN = "HUMAN_CONFIRMED_CONTROL_POINTS"   # == source_anchor.PROVENANCE (test-locked)
DEFAULT_INTERVAL_FT = 50.0
_COINCIDENT_EPS_PT = 0.5                              # merge a dot onto a coincident vertex within this gap
_NUM_RE = re.compile(r"[-+]?\d*\.?\d+")

# Case-insensitive field aliases for pulling canonical bore-log values off a free-form reviewed row. The row
# stores values as free-form keys across raw / normalized / corrected layers (no fixed column schema yet), so
# we resolve by a small alias set. These are DATA keys, not code identities — no customer/name tokens.
_FIELD_ALIASES: Dict[str, Tuple[str, ...]] = {
    "footage": ("footage", "footage_ft", "ft", "feet", "length", "bore_footage"),
    "start_station": ("start_station", "start", "start_sta", "from_station", "sta_start", "s"),
    # depth_min_ft/boc_min_ft are the generic-extractor + strict-reader keys (borelog_rows.py) for the
    # SAME depth/BOC values manual rows spell "depth"/"boc"; depth_ft/boc_ft are the Phase-1 handwritten-
    # extraction tier's SpanProposal keys (contracts/handwritten_extraction.py) for the identical concept —
    # alias all of them so a source-backed reading from ANY lane resolves identically on this dot's info
    # payload (never invented when absent). Appended LAST (existing keys take precedence on a row that
    # somehow carries more than one spelling — never a behavior change for any row already resolving today).
    "depth": ("depth", "bore_depth", "depth_min_ft", "depth_ft"),
    "boc": ("boc", "bottom_of_conduit", "boc_min_ft", "boc_ft"),
    "date": ("date", "bore_date", "install_date"),
    "crew": ("crew", "crew_name"),
    "print": ("print", "print_raw", "print_no", "print_number", "print_num", "sheet_print"),
    "notes": ("notes", "note", "comment", "comments"),
    "bore_log_id": ("bore_id", "bore_log_id", "bore", "id"),
}
_INFO_KEYS = ("depth", "boc", "date", "crew", "print", "notes", "bore_log_id")


def _xy(p) -> Tuple[float, float]:
    """Accept a control point as {"x":..,"y":..} or a 2-tuple; return (x, y) floats."""
    if isinstance(p, dict):
        return float(p["x"]), float(p["y"])
    return float(p[0]), float(p[1])


def _cumulative(pts: Sequence[Tuple[float, float]]) -> List[float]:
    """Cumulative arc-length (display pts) at each vertex; ``cum[-1]`` is the total polyline length."""
    cum = [0.0]
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        cum.append(cum[-1] + math.hypot(bx - ax, by - ay))
    return cum


def _point_at(pts: Sequence[Tuple[float, float]], cum: Sequence[float], target: float
              ) -> Tuple[float, float]:
    """Linear-interpolated (x, y) at arc-length ``target`` along the polyline (clamped to the endpoints)."""
    total = cum[-1]
    if target <= 0:
        return pts[0]
    if target >= total:
        return pts[-1]
    for i in range(len(pts) - 1):
        if cum[i] <= target <= cum[i + 1]:
            seg = cum[i + 1] - cum[i]
            t = 0.0 if seg <= 0 else (target - cum[i]) / seg
            (ax, ay), (bx, by) = pts[i], pts[i + 1]
            return (ax + t * (bx - ax), ay + t * (by - ay))
    return pts[-1]


def dot_marks(footage: float, interval_ft: float = DEFAULT_INTERVAL_FT) -> List[float]:
    """Footage-along marks: the START (0), every ``interval_ft`` strictly inside the run, then the final
    endpoint (footage) ALWAYS — each included exactly once (an exact multiple like 150' is not duplicated;
    the start is not duplicated by the first interval). Empty for footage <= 0."""
    if footage is None or footage <= 0 or interval_ft <= 0:
        return []
    marks: List[float] = [0.0]          # the clickable start point / start station
    m = interval_ft
    while m < footage - 1e-9:            # strictly inside -> the endpoint is added once, below
        marks.append(round(m, 6))
        m += interval_ft
    marks.append(round(float(footage), 6))
    return marks


def _arclen_dots(control_points, footage: float, interval_ft: float
                 ) -> List[Tuple[float, float, Tuple[float, float]]]:
    """(footage_along, arc_length_pt, xy) per mark, self-calibrated by footage/total-length. [] if degenerate."""
    try:
        pts = [_xy(p) for p in (control_points or [])]
    except (KeyError, TypeError, ValueError):
        return []
    if len(pts) < 2 or footage is None or footage <= 0:
        return []
    cum = _cumulative(pts)
    total = cum[-1]
    if total <= 0:
        return []
    out = []
    for fa in dot_marks(footage, interval_ft):
        target_pt = (fa / float(footage)) * total          # ft-along -> pt-along (self-calibrated scale)
        out.append((fa, target_pt, _point_at(pts, cum, target_pt)))
    return out


def _arclen_at(control_points, footage: float, footages: Sequence[float]
               ) -> List[Tuple[float, float, Tuple[float, float]]]:
    """(footage_along, arc_length_pt, xy) at each GIVEN footage-along value -- the ``marks``-path
    counterpart of ``_arclen_dots`` (which derives its own footage list via ``dot_marks``). SAME
    self-calibrated footage/total-length scale + SAME degenerate guards; [] if degenerate. Addendum-only
    helper (see module docstring); does not change ``_arclen_dots``/``dot_marks``/``_point_at``."""
    try:
        pts = [_xy(p) for p in (control_points or [])]
    except (KeyError, TypeError, ValueError):
        return []
    if len(pts) < 2 or footage is None or footage <= 0:
        return []
    cum = _cumulative(pts)
    total = cum[-1]
    if total <= 0:
        return []
    out = []
    for fa in footages:
        target_pt = (fa / float(footage)) * total
        out.append((fa, target_pt, _point_at(pts, cum, target_pt)))
    return out


def compute_station_dots(control_points, *, footage, start_station: Optional[str] = None,
                         interval_ft: float = DEFAULT_INTERVAL_FT, info: Optional[Dict[str, Any]] = None,
                         marks: Optional[List[Dict[str, Any]]] = None
                         ) -> List[Dict[str, Any]]:
    """Clickable dot payloads along the human polyline. Returns [] safely on degenerate input (< 2 points,
    zero-length polyline, non-positive footage). ``station`` is derived only when ``start_station`` parses.

    ADDENDUM: when ``marks`` is ``None`` this is the EXACT pre-addendum behavior (locked byte-identity).
    When ``marks`` is provided (a list built by ``contracts/station_marks.py``), each dot's position comes
    from the SAME arclen/``_point_at`` math + 2-decimal ``xy_display`` contract, but at the MARK's own
    ``footage_along`` (never the generic 50' ladder), and its ``station``/``depth``/``boc``/``notes``/
    ``station_evidence`` come from the MARK (not from ``info``) -- ``depth``/``boc``/``notes`` are
    included ONLY when that mark actually carries them (a SOURCE_RECORDED mark with recorded values;
    DERIVED_INTERVAL fill never invents them). Bore-level ``date``/``crew``/``print``/``bore_log_id``
    (from ``info``) and ``provenance`` are still attached to EVERY dot either way."""
    info = info or {}
    if marks is None:
        start_ft = parse_station(start_station) if start_station else None
        dots = []
        for i, (fa, _pt, (x, y)) in enumerate(_arclen_dots(control_points, footage, interval_ft)):
            station = feet_to_station(start_ft + fa) if start_ft is not None else None
            dots.append({
                "index": i,
                "footage_along": round(fa, 2),
                "station": station,
                "xy_display": {"x": round(float(x), 2), "y": round(float(y), 2)},
                "depth": info.get("depth"),
                "boc": info.get("boc"),
                "date": info.get("date"),
                "crew": info.get("crew"),
                "print": info.get("print"),
                "notes": info.get("notes"),
                "bore_log_id": info.get("bore_log_id"),
                "provenance": PROVENANCE_HUMAN,
            })
        return dots

    footages = [float(m.get("footage_along", 0.0)) for m in marks]
    dots = []
    for i, (mark, (fa, _pt, (x, y))) in enumerate(zip(marks, _arclen_at(control_points, footage, footages))):
        dot = {
            "index": i,
            "footage_along": round(fa, 2),
            "station": mark.get("station"),
            "xy_display": {"x": round(float(x), 2), "y": round(float(y), 2)},
            "origin": mark.get("origin"),
            "date": info.get("date"),
            "crew": info.get("crew"),
            "print": info.get("print"),
            "bore_log_id": info.get("bore_log_id"),
            "provenance": PROVENANCE_HUMAN,
        }
        if mark.get("depth") is not None:
            dot["depth"] = mark["depth"]
        if mark.get("boc") is not None:
            dot["boc"] = mark["boc"]
        if mark.get("notes") is not None:
            dot["notes"] = mark["notes"]
        if mark.get("station_evidence") is not None:
            dot["station_evidence"] = mark["station_evidence"]
        dots.append(dot)
    return dots


def stroke_polyline_with_dots(control_points, *, footage, interval_ft: float = DEFAULT_INTERVAL_FT,
                              marks: Optional[List[Dict[str, Any]]] = None
                              ) -> List[Tuple[float, float]]:
    """The human polyline with the dot positions merged in (arc-length ordered, coincident points deduped) —
    the exact same visual path, now carrying the footage marks as vertices so the renderer's marker rings land
    on them. Falls back to the bare control points when there are no dots.

    ADDENDUM: ``marks=None`` is the EXACT pre-addendum behavior (locked byte-identity). When ``marks`` is
    provided, the merged-in vertices sit at the MARKS' own footage-along positions (the SAME positions
    ``compute_station_dots(marks=...)`` placed its dots at) instead of the generic 50' ladder -- so the
    drawn stroke's extra vertices always align with wherever the dots actually are."""
    try:
        pts = [_xy(p) for p in (control_points or [])]
    except (KeyError, TypeError, ValueError):
        return []
    if len(pts) < 2:
        return pts
    cum = _cumulative(pts)
    if cum[-1] <= 0 or footage is None or footage <= 0:
        return pts
    marked: List[Tuple[float, Tuple[float, float]]] = [(cum[i], pts[i]) for i in range(len(pts))]
    if marks is None:
        for fa, target_pt, xy in _arclen_dots(control_points, footage, interval_ft):
            marked.append((target_pt, xy))
    else:
        footages = [float(m.get("footage_along", 0.0)) for m in marks]
        for fa, target_pt, xy in _arclen_at(control_points, footage, footages):
            marked.append((target_pt, xy))
    marked.sort(key=lambda t: t[0])
    out: List[Tuple[float, float]] = []
    for _c, (x, y) in marked:
        if not out or math.hypot(x - out[-1][0], y - out[-1][1]) > _COINCIDENT_EPS_PT:
            out.append((float(x), float(y)))
    return out


def dot_xys(dots: Sequence[Dict[str, Any]]) -> List[Tuple[float, float]]:
    """The (x, y) list of a dot set (for the renderer's mandatory-point rings)."""
    return [(float(d["xy_display"]["x"]), float(d["xy_display"]["y"])) for d in dots]


# --- reviewed-row field resolution (schema-agnostic; DATA keys only, never engine/dialect) ---------------- #
def _coerce_ft(value) -> Optional[float]:
    """Coerce a footage value ("176", "176'", 176, 176.0) to float feet; None when absent/non-numeric."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    m = _NUM_RE.search(str(value))
    return float(m.group(0)) if m else None


def _as_str(value) -> Optional[str]:
    return None if value is None else str(value)


def _norm_key(k) -> str:
    """Fold a free-form column key to snake form for alias matching: lowercase, runs of non-alphanumerics ->
    one underscore, trimmed (so 'Start Station', 'Print #', 'B.O.C.' -> 'start_station', 'print', 'b_o_c')."""
    return re.sub(r"[^a-z0-9]+", "_", str(k).strip().lower()).strip("_")


def _merged_lc(row: Dict[str, Any]) -> Dict[str, Any]:
    """Effective row values by canonical key precedence: raw < normalized < corrected_values (human CORRECTED
    wins). Keys normalized (``_norm_key``) for alias matching. Reads a plain dict — no engine/schema coupling."""
    merged: Dict[str, Any] = {}
    layers = [row.get("raw"), row.get("normalized"), (row.get("review") or {}).get("corrected_values")]
    for layer in layers:
        if isinstance(layer, dict):
            for k, v in layer.items():
                merged[_norm_key(k)] = v
    return merged


def _pick(merged: Dict[str, Any], aliases: Tuple[str, ...]):
    for a in aliases:
        if a in merged and merged[a] not in (None, ""):
            return merged[a]
    return None


def resolve_bore_fields(row: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Pull canonical bore-log fields off a reviewed/extracted row (free-form key layers) for the dot payload:
    {"footage": float|None, "start_station": str|None, "info": {depth, boc, date, crew, print, notes,
    bore_log_id}}. Best-effort + None-safe; never raises on a sparse row."""
    merged = _merged_lc(row or {})
    return {
        "footage": _coerce_ft(_pick(merged, _FIELD_ALIASES["footage"])),
        "start_station": _as_str(_pick(merged, _FIELD_ALIASES["start_station"])),
        "info": {k: _as_str(_pick(merged, _FIELD_ALIASES[k])) for k in _INFO_KEYS},
    }
