"""Evidence-bound station marks -- the owner's STATION-DOT CONTRACT (Mission 8 ADDENDUM,
``.foreman/scratch/m8/design-dots.md``, BINDING; supersedes design.md/design-final.md where they touch
station dots).

Owner's clarification (verbatim intent): the dots along a human-confirmed redline represent the BORE
LOG'S OWN station sequence, bound to evidence -- never a generic 50-ft geometric ladder invented over a
log that recorded something else. This module is the PURE contract that decides, for one reviewed row,
WHICH dots to place and how to tag them; ``render/station_dots.py::compute_station_dots`` (additive
``marks`` parameter) turns that decision into on-polyline positions.

No I/O. No imports from ``render/`` or any engine/dialect/match module -- reuses ONLY
``truelinev2.stations``' station parse/format helpers (``parse_station`` / ``feet_to_station`` /
``strip_station_label``), the SAME primitives ``render/station_dots.py`` and
``contracts/handwritten_extraction.py`` already use. The raw < normalized < review.corrected_values
effective-row merge this module needs (to reach ``station_readings``) is REIMPLEMENTED LOCALLY as one
small, documented fold -- the SAME precedence ``render.station_dots.resolve_bore_fields``,
``contracts.source_route_adoption.row_effective_stations`` and ``contracts.closeout_pdf`` already apply,
each via their OWN local copy (a pure contracts module must not import ``render/``, and importing across
sibling contracts modules for a ~6-line fold would be a needless coupling this codebase has already
decided against three times over).

Mark = {"footage_along": float, "origin": SOURCE_RECORDED|DERIVED_INTERVAL, "station": str|None,
        "depth": str|None, "boc": str|None, "notes": str|None,
        "station_evidence": {"verbatim":.., "status":.., "confidence":..}|None}

``build_station_marks`` returns ``(marks, basis, warnings)``:
  * ``marks`` is ``None`` ONLY when even the footage-only fallback cannot be honestly built (fail-closed;
    the caller passes ``marks=None`` straight into ``compute_station_dots``, which then reproduces its
    pre-addendum default behavior byte-for-byte -- the fail-closed path and the "no addendum" path are
    the SAME code path by construction).
  * ``basis`` is one of ``STATION_SERIES`` / ``SERIES_ENDPOINTS_WITH_DERIVED_FILL`` / ``SPAN_ENDPOINTS``.
  * ``warnings`` names WHY a recorded series (when one existed) was rejected as unusable -- never why a
    row simply never had one (that is the ordinary, unremarkable ``SPAN_ENDPOINTS`` case).
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from truelinev2.stations import feet_to_station, parse_station, strip_station_label

# Mark.origin vocabulary.
SOURCE_RECORDED = "SOURCE_RECORDED"
DERIVED_INTERVAL = "DERIVED_INTERVAL"

# build_station_marks basis vocabulary.
BASIS_STATION_SERIES = "STATION_SERIES"
BASIS_SERIES_ENDPOINTS_WITH_DERIVED_FILL = "SERIES_ENDPOINTS_WITH_DERIVED_FILL"
BASIS_SPAN_ENDPOINTS = "SPAN_ENDPOINTS"

# Named series-unusable warning codes (owner clause 6: a violation never invents a series -- it falls
# through to the approved span, honestly named WHY).
WARN_UNPARSEABLE = "STATION_SERIES_UNPARSEABLE"
WARN_NOT_ASCENDING = "STATION_SERIES_NOT_ASCENDING"
WARN_ENDPOINT_MISMATCH = "STATION_SERIES_ENDPOINT_MISMATCH"
WARN_FOOTAGE_MISMATCH = "STATION_SERIES_FOOTAGE_MISMATCH"
# Fix-wave F2 (blind-verify note 2): distinct from WARN_ENDPOINT_MISMATCH -- that code asserts a proven
# INEQUALITY between two parseable values. When the ROW's own effective start/end station text itself
# fails to parse, no such comparison was ever made; naming it ENDPOINT_MISMATCH would overstate what was
# proven. This code names the actual, narrower fact: the row's own recorded endpoints are unreadable.
WARN_ROW_ENDPOINTS_UNPARSEABLE = "STATION_SERIES_ROW_ENDPOINTS_UNPARSEABLE"

DEFAULT_INTERVAL_FT = 50.0

# "Exact within the station grammar's resolution": feet_to_station formats to 2dp, so two independently
# derived footage values that ought to agree are compared at a tolerance well under one-hundredth of a
# foot -- tight enough to catch a genuine mismatch, loose enough to absorb float noise from repeated
# parse/format round-trips.
_FT_EPS = 0.005

_NORM_RE = re.compile(r"[^a-z0-9]+")


def _norm_key(k: Any) -> str:
    return _NORM_RE.sub("_", str(k).strip().lower()).strip("_")


def _effective_station_readings(row_effective: Optional[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
    """``station_readings`` off a reviewed row's layered dict, by precedence raw < normalized <
    review.corrected_values (human CORRECTED wins last) -- mirrors
    ``render.station_dots.resolve_bore_fields`` / ``contracts.source_route_adoption.row_effective_stations``
    / ``contracts.closeout_pdf``'s SAME fold, reimplemented locally here (see module docstring). ``None``
    when absent or not a list (a generic TABLE_IMPORT row carries no series at all -- the ordinary case)."""
    merged: Dict[str, Any] = {}
    row_effective = row_effective or {}
    for layer in (row_effective.get("raw"), row_effective.get("normalized"),
                  (row_effective.get("review") or {}).get("corrected_values")):
        if isinstance(layer, dict):
            for k, v in layer.items():
                merged[_norm_key(k)] = v
    readings = merged.get("station_readings")
    return list(readings) if isinstance(readings, list) else None


def _cell_value(cell: Any) -> Any:
    return cell.get("value") if isinstance(cell, dict) else None


def _cell_str(cell: Any) -> Optional[str]:
    v = _cell_value(cell)
    return None if v in (None, "") else str(v)


def _station_feet(cell: Any) -> Optional[float]:
    """A usable station-cell reading: accepts a numeric value directly, or a station-notation string
    (optionally ``STA``-prefixed) -- mirrors ``contracts.handwritten_extraction._parse_station_feet``'s
    acceptance rule (this module reuses the SAME two stations.py primitives, not a new grammar)."""
    v = _cell_value(cell)
    if v is None:
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    return parse_station(strip_station_label(str(v)))


def _station_evidence(cell: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(cell, dict):
        return None
    return {"verbatim": cell.get("verbatim"), "status": cell.get("status"), "confidence": cell.get("confidence")}


def _as_str(v: Any) -> Optional[str]:
    return None if v in (None, "") else str(v)


def _interior_footages(footage: float, interval_ft: float) -> List[float]:
    """Footage-along values STRICTLY inside the span (excludes 0 and ``footage`` -- those are the
    recorded endpoints, added separately, tagged SOURCE_RECORDED). Mirrors
    ``render.station_dots.dot_marks``'s own strictly-inside loop/epsilon exactly, so a derived-fill dot
    set lands on the IDENTICAL footage-along values the pre-addendum default ladder would have used for
    the same footage/interval (this is what keeps a footage-only row's dot POSITIONS unchanged)."""
    out: List[float] = []
    m = interval_ft
    while m < footage - 1e-9:
        out.append(round(m, 6))
        m += interval_ft
    return out


def _derived_mark(fa: float, start_ft: Optional[float]) -> Dict[str, Any]:
    station = feet_to_station(start_ft + fa) if start_ft is not None else None
    return {"footage_along": round(fa, 2), "origin": DERIVED_INTERVAL, "station": station,
            "depth": None, "boc": None, "notes": None, "station_evidence": None}


def _validate_series(readings: List[Dict[str, Any]], start_station: Optional[str],
                     end_station: Optional[str], footage: Optional[float]
                     ) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
    """Owner's series-usability contract. Returns ``(readings, None)`` when usable, else
    ``(None, <named warning>)`` -- NEVER guesses; a violation falls through to the footage-only span
    treatment (the approved span remains the truth, owner clause 6)."""
    feet: List[float] = []
    for entry in readings:
        # Fix-wave B1 (Sol xhigh verification): the row is UNTRUSTED input -- a malformed entry (None, a
        # bare string/number, anything not a cell-bearing dict) must fall back honestly, never raise.
        if not isinstance(entry, dict):
            return None, WARN_UNPARSEABLE
        f = _station_feet(entry.get("station"))
        if f is None:
            return None, WARN_UNPARSEABLE
        feet.append(f)
    for a, b in zip(feet, feet[1:]):
        if not (b > a):
            return None, WARN_NOT_ASCENDING
    eff_start_ft = parse_station(start_station) if start_station else None
    eff_end_ft = parse_station(end_station) if end_station else None
    if eff_start_ft is None or eff_end_ft is None:
        # The row's OWN recorded start/end station text doesn't parse -- nothing was actually compared,
        # so this is NOT a proven mismatch (see WARN_ROW_ENDPOINTS_UNPARSEABLE's docstring).
        return None, WARN_ROW_ENDPOINTS_UNPARSEABLE
    if abs(feet[0] - eff_start_ft) > _FT_EPS or abs(feet[-1] - eff_end_ft) > _FT_EPS:
        return None, WARN_ENDPOINT_MISMATCH
    if footage is None:
        return None, WARN_FOOTAGE_MISMATCH
    if abs((feet[-1] - feet[0]) - float(footage)) > _FT_EPS:
        return None, WARN_FOOTAGE_MISMATCH
    return readings, None


def _series_marks(readings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """len > 2 usable series -> EXACTLY the recorded stations, no derived fill (owner clause 5: never
    mix a generic sequence into a genuinely recorded one). Handles irregular intervals and a < 50 ft
    final interval BY CONSTRUCTION -- there is no interval math here at all, only the recorded readings."""
    base_ft = _station_feet(readings[0].get("station"))
    marks = []
    for entry in readings:
        sta_cell = entry.get("station")
        f = _station_feet(sta_cell)
        marks.append({
            "footage_along": round(f - base_ft, 2),
            "origin": SOURCE_RECORDED,
            "station": _cell_str(sta_cell),
            "depth": _cell_str(entry.get("depth_ft")),
            "boc": _cell_str(entry.get("boc_ft")),
            # Fix-wave B3 (Sol xhigh verification): read THIS entry's OWN "notes" cell, the SAME
            # cell-value pattern as depth_ft/boc_ft -- honestly None when this reading carries no note
            # (never the row-level notes value, which is a DIFFERENT, bore-scoped fact -- see
            # render/source_anchor_render.py's info["notes"], attached separately and never here).
            "notes": _cell_str(entry.get("notes")),
            "station_evidence": _station_evidence(sta_cell),
        })
    return marks


def _endpoint_mark(reading: Dict[str, Any], footage_along: float) -> Dict[str, Any]:
    sta_cell = reading.get("station")
    return {
        "footage_along": round(footage_along, 2), "origin": SOURCE_RECORDED,
        "station": _cell_str(sta_cell), "depth": _cell_str(reading.get("depth_ft")),
        "boc": _cell_str(reading.get("boc_ft")),
        "notes": _cell_str(reading.get("notes")),          # fix-wave B3: this entry's OWN note cell only
        "station_evidence": _station_evidence(sta_cell),
    }


def _endpoints_with_fill(readings: List[Dict[str, Any]], footage: float,
                         interval_ft: float) -> List[Dict[str, Any]]:
    """len == 2 (start/end/total-only log, the WP23 class): recorded endpoints w/ per-entry values +
    evidence, PLUS derived interior fill (owner clause 4: derivation permitted only when the log records
    just start/end/total footage; every derived dot is explicitly tagged, never presented as recorded)."""
    start_ft = _station_feet(readings[0].get("station"))
    marks = [_endpoint_mark(readings[0], 0.0)]
    for fa in _interior_footages(footage, interval_ft):
        marks.append(_derived_mark(fa, start_ft))
    marks.append(_endpoint_mark(readings[-1], footage))
    return marks


def _span_endpoints_with_fill(start_station: Optional[str], end_station: Optional[str],
                              footage: Optional[float], interval_ft: float
                              ) -> Optional[List[Dict[str, Any]]]:
    """NO SERIES (generic TABLE_IMPORT rows): the log's recorded span endpoints (station = recorded
    start/end station strings; depth/boc NOT attached per-station -- the row's bore-level values are not
    station readings) + derived interior fill. Fails closed (returns ``None``) only when even the span
    itself cannot be honestly placed (non-positive/absent footage)."""
    if footage is None or footage <= 0:
        return None
    start_ft = parse_station(start_station) if start_station else None
    marks = [{"footage_along": 0.0, "origin": SOURCE_RECORDED, "station": _as_str(start_station),
             "depth": None, "boc": None, "notes": None, "station_evidence": None}]
    for fa in _interior_footages(footage, interval_ft):
        marks.append(_derived_mark(fa, start_ft))
    marks.append({"footage_along": round(float(footage), 2), "origin": SOURCE_RECORDED,
                 "station": _as_str(end_station), "depth": None, "boc": None, "notes": None,
                 "station_evidence": None})
    return marks


def build_station_marks(row_effective: Optional[Dict[str, Any]], *, footage: Optional[float],
                        start_station: Optional[str], end_station: Optional[str],
                        interval_ft: float = DEFAULT_INTERVAL_FT
                        ) -> Tuple[Optional[List[Dict[str, Any]]], str, List[str]]:
    """Decide the evidence-bound dot sequence for one reviewed row. ``row_effective`` is the row's own
    layered dict (raw/normalized/review.corrected_values -- the SAME shape
    ``render.station_dots.resolve_bore_fields`` reads); ``footage``/``start_station``/``end_station`` are
    the row's EFFECTIVE (already-resolved, same precedence) values, supplied by the caller so this module
    never re-derives them under a different alias table. Returns ``(marks, basis, warnings)`` -- see the
    module docstring for the full contract."""
    warnings: List[str] = []
    readings = _effective_station_readings(row_effective)
    if readings is not None and len(readings) >= 2:
        usable, warning = _validate_series(readings, start_station, end_station, footage)
        if usable is None:
            warnings.append(warning)
        elif len(usable) > 2:
            return _series_marks(usable), BASIS_STATION_SERIES, warnings
        else:
            marks = _endpoints_with_fill(usable, footage, interval_ft)
            return marks, BASIS_SERIES_ENDPOINTS_WITH_DERIVED_FILL, warnings
    marks = _span_endpoints_with_fill(start_station, end_station, footage, interval_ft)
    return marks, BASIS_SPAN_ENDPOINTS, warnings
