"""Read-only PLAN-VIEW station locator: resolve a bored endpoint's station to its 2-D position by the printed
station LABEL on the sheet -- NO linear station axis required. Name-free; source-evidence-derived; strict.

WHY THIS EXISTS
The existing 2-D coordinate observers (``terminus_coordinate_observer``) project a bore-log station to display-x
through a fitted LINEAR axis (``StationAxis.x_at``) and bail (``NO_STATION_AXIS``) when no such axis exists. A
linear ``station = a*x + b`` axis is a PROFILE-sheet model (the horizontal axis IS the station). A PLAN-VIEW
route (county/municipal buried-fiber, OSP fiber permit) meanders in 2-D: stations run ALONG the drawn route,
not along the sheet x-axis, so there is no linear axis and the projection cannot run. On such a sheet the
station's 2-D position is instead carried by its PRINTED LABEL (e.g. a word ``177+01`` placed at the route
point). This module reads that printed label directly: given a source-bound endpoint station, it finds the
printed station word whose value equals that station and returns its 2-D anchor -- the plan-view analog of
``axis.x_at`` that needs no axis.

SAFETY / SCOPE
- Read-only: imports only the read-only ``PlanPdf`` reader + pure station parsing. Imports NOTHING from
  contracts / match / render / api / store / placement; performs NO placement, promotion, or status change.
- Source-evidence-derived only: it returns the position of an ACTUAL printed label. It never invents a
  coordinate, never projects, never snaps to nearby geometry.
- Strict refusal: a station with no printed label -> ``NO_PRINTED_STATION_LABEL``; a station printed in two or
  more places (e.g. a plan view + a profile view on the same sheet, or a table) -> ``AMBIGUOUS_STATION_LABEL``
  (never coin-flipped). An unbound endpoint is ``NOT_SOURCE_BOUND``.
- ``class_verified`` is ALWAYS False (the cold lane has no generic CAD layer/class table) -> this never unblocks
  AUTO. Locating a label proves WHERE a station is printed, not that the drawn run between two stations is the
  bore. Verifying a drawn run between two located anchors is a separate, later gate.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from truelinev2.ingest.pdf import PlanPdf
from truelinev2.stations import parse_station, strip_station_label

# --- per-endpoint anchor statuses ----------------------------------------------------------------------- #
STATION_LABEL_LOCATED = "STATION_LABEL_LOCATED"
NO_PRINTED_STATION_LABEL = "NO_PRINTED_STATION_LABEL"
AMBIGUOUS_STATION_LABEL = "AMBIGUOUS_STATION_LABEL"
NOT_SOURCE_BOUND = "NOT_SOURCE_BOUND"

# --- package (two-endpoint) statuses -------------------------------------------------------------------- #
PLAN_VIEW_ENDPOINTS_LOCATED = "PLAN_VIEW_ENDPOINTS_LOCATED"
PLAN_VIEW_ENDPOINTS_INCOMPLETE = "PLAN_VIEW_ENDPOINTS_INCOMPLETE"

_MATCH_TOL_FT = 0.05          # a station identity match (parsed label == target), not a proximity search


@dataclass(frozen=True)
class StationLabelAnchor:
    """The 2-D anchor of ONE endpoint's printed station label, or a refusal. ``x``/``y`` are display-space
    centre coordinates (the same space as ``PlanPdf.vector_segments``), set only when ``STATION_LABEL_LOCATED``.
    ``match_count`` is how many printed labels carried this station value (0 / 1 / >=2)."""
    station_ft: float
    status: str
    x: Optional[float]
    y: Optional[float]
    text: Optional[str]
    match_count: int

    @property
    def located(self) -> bool:
        return self.status == STATION_LABEL_LOCATED


@dataclass(frozen=True)
class PlanViewEndpointObservation:
    """Read-only diagnostic for one bore's two endpoints on a plan-view sheet. Carries no placement and confers
    no status. ``label_separation`` is the 2-D distance between the two LOCATED label anchors (a printed-label
    separation, NOT a route/bore length) -- present only when both endpoints located."""
    sheet: int
    status: str
    start: StationLabelAnchor
    end: StationLabelAnchor
    label_separation: Optional[float]
    class_verified: bool          # always False

    def to_dict(self) -> dict:
        return {
            "sheet": self.sheet, "status": self.status,
            "start": self.start.__dict__, "end": self.end.__dict__,
            "label_separation": self.label_separation, "class_verified": self.class_verified,
        }


def _word_station(text: Optional[str]) -> Optional[float]:
    """Parse a word's station value, stripping an optional leading STA / STA. / STA: label. None if the word
    is not a station token."""
    return parse_station(strip_station_label(text or ""))


def locate_printed_station(words: Sequence[Dict[str, Any]], station_ft: float,
                           *, tol_ft: float = _MATCH_TOL_FT) -> StationLabelAnchor:
    """Find the printed station LABEL whose value equals ``station_ft`` and return its 2-D anchor. ``words`` is
    ``PlanPdf.words(sheet, offset)``. Identity match (within ``tol_ft`` for float noise), never nearest; refuses
    on zero or multiple matches. No axis, no projection, no geometry snap."""
    target = float(station_ft)
    matches: List[Dict[str, Any]] = []
    for w in words:
        v = _word_station(w.get("text"))
        if v is not None and abs(v - target) <= tol_ft:
            matches.append(w)
    if not matches:
        return StationLabelAnchor(target, NO_PRINTED_STATION_LABEL, None, None, None, 0)
    if len(matches) > 1:
        return StationLabelAnchor(target, AMBIGUOUS_STATION_LABEL, None, None, None, len(matches))
    w = matches[0]
    return StationLabelAnchor(target, STATION_LABEL_LOCATED, float(w["xc"]), float(w["yc"]),
                              str(w.get("text")), 1)


def observe_plan_view_endpoints(plan: PlanPdf, sheet: int, start_ft: float, end_ft: float,
                                *, start_source_bound: bool, end_source_bound: bool,
                                offset: int = 0) -> PlanViewEndpointObservation:
    """Read-only: locate BOTH source-bound endpoints' printed station labels on a plan-view sheet. An unbound
    endpoint is not searched (``NOT_SOURCE_BOUND``). No axis required; mutates nothing."""
    words = plan.words(int(sheet), int(offset))
    start = (locate_printed_station(words, start_ft) if start_source_bound
             else StationLabelAnchor(float(start_ft), NOT_SOURCE_BOUND, None, None, None, 0))
    end = (locate_printed_station(words, end_ft) if end_source_bound
           else StationLabelAnchor(float(end_ft), NOT_SOURCE_BOUND, None, None, None, 0))
    both = start.located and end.located
    sep = (round(math.hypot(start.x - end.x, start.y - end.y), 2) if both else None)
    status = PLAN_VIEW_ENDPOINTS_LOCATED if both else PLAN_VIEW_ENDPOINTS_INCOMPLETE
    return PlanViewEndpointObservation(int(sheet), status, start, end, sep, False)


def observe_plan_view_endpoints_for_path(plan_path: str, sheet: int, start_ft: float, end_ft: float,
                                         *, start_source_bound: bool, end_source_bound: bool,
                                         offset: int = 0) -> PlanViewEndpointObservation:
    """Open a plan PDF read-only and observe one bore's plan-view endpoints. Opens + closes the PDF; writes
    nothing; runs no placement/render. The read-only harness path for a future real/fresh package."""
    plan = PlanPdf(str(plan_path))
    try:
        return observe_plan_view_endpoints(
            plan, int(sheet), float(start_ft), float(end_ft),
            start_source_bound=start_source_bound, end_source_bound=end_source_bound, offset=int(offset))
    finally:
        plan.close()
