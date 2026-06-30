"""Read-only TERMINUS-COORDINATE + 2-D endpoint-tightness OBSERVER (the next pre-AUTO evidence layer).

The continued-89 observer proved branch-uniqueness + station-x endpoint tightness against the adversarial
harness, but flagged a residual: a source-bound terminus carries a STATION, not the drawn structure
coordinate, so a run that reaches the right station-x at the WRONG y (a parallel band, an off-band structure)
still read TIGHT. This layer closes that — when honestly derivable — by exposing:

  * ``TERMINUS_DRAWN_COORDINATE`` — the drawn (x, y) of a source-bound terminus, derived ONLY from existing
    drawn geometry (``PlanPdf.vector_segments``): a COMPACT drawn shape (a symbol/marker — not a long run line,
    not a baseline, not a tick) sitting at the bound station's projected x. Uniqueness-mandatory: 0 ->
    ``NO_DRAWN_COORDINATE``, >=2 -> ``AMBIGUOUS_DRAWN_COORDINATE``, not source-bound -> ``NOT_SOURCE_BOUND``.
    A coordinate is NEVER guessed; the label-text anchor (printed offset above the line) is NOT used.
  * ``ENDPOINT_TO_TERMINUS_2D_TIGHTNESS`` — the 2-D distance from the run's terminal (x, y) to that drawn
    coordinate. ``UNMEASURABLE`` whenever the coordinate is not derivable (never promotes from a guess).

It keeps and composes the prior ``BRANCH_PATH_UNIQUENESS`` + ``ENDPOINT_TO_RUN_COORDINATE_TIGHTNESS``
(``run_geometry_observer``) so one observation carries all FOUR diagnostics.

Honest scope (reported, never overstated):
  * This is COLD-LANE, GEOMETRY-ONLY symbol detection: a compact drawn shape at the bound station. It is NOT
    class-verified. The named-dialect, class-verified analog is ``extract/structure_position.py``
    (``resolve_structure_position`` — label -> leader -> symbol -> fill-class check), which REQUIRES a CAD
    layer table + class fill colors the generic/cold lane does not have. So this observer's coordinate is
    weaker evidence (a shape at the station), reported with provenance ``COMPACT_SYMBOL_AT_STATION``.
  * NO AUTO, NO promotion, NO ``_cap_review``/placement/status/render change. A future, separately-authorized
    gate may CONSULT it. Pure read of existing geometry; mutates nothing; imports no placement/contract code.
  * NOT proof of real generalization: no eligible fresh non-recognized package exists in the repo (only the
    recognized work corpus + synthetic fixtures), so this proves the signals against the ADVERSARIAL HARNESS
    only. ``observe_package_terminus_geometry`` is the read-only validation PATH a future real package runs
    through — it does not claim generalization.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from truelinev2.extract.generic_geometry import GenericGeometryDialect
from truelinev2.extract.run_geometry_observer import (
    BRANCH_PATH_UNIQUENESS,
    BRANCH_UNIQUE,
    ENDPOINT_TO_RUN_COORDINATE_TIGHTNESS,
    TIGHTNESS_TIGHT,
    observe_run_geometry,
    spanning_run_terminals,
)
from truelinev2.ingest.pdf import PlanPdf

# --- The two named diagnostics this layer adds. --------------------------------------------------------- #
TERMINUS_DRAWN_COORDINATE = "TERMINUS_DRAWN_COORDINATE"
ENDPOINT_TO_TERMINUS_2D_TIGHTNESS = "ENDPOINT_TO_TERMINUS_2D_TIGHTNESS"

# terminus-drawn-coordinate results (uniqueness-mandatory; a coordinate is never guessed)
DRAWN_COORDINATE_BOUND = "DRAWN_COORDINATE_BOUND"        # exactly one compact drawn shape at the bound station
NO_DRAWN_COORDINATE = "NO_DRAWN_COORDINATE"              # source-bound, but no drawn shape sits at the station
AMBIGUOUS_DRAWN_COORDINATE = "AMBIGUOUS_DRAWN_COORDINATE"  # >=2 compact shapes at the station -> never chosen
NOT_SOURCE_BOUND = "NOT_SOURCE_BOUND"                    # endpoint has no printed identity -> no coordinate to seek

# coordinate provenance (honest: geometry-only, NOT class-verified)
COMPACT_SYMBOL_AT_STATION = "COMPACT_SYMBOL_AT_STATION"

# 2-D tightness verdicts
TIGHTNESS_2D_TIGHT = "TIGHT"
TIGHTNESS_2D_LOOSE = "LOOSE"
TIGHTNESS_2D_UNMEASURABLE = "UNMEASURABLE"

# Geometry constants (display pts; the synthetic harness axis is ~1 ft/pt).
_SYMBOL_MIN_DIM = 3.0       # a symbol has area in BOTH dims -> excludes thin run lines, baselines, station ticks
_SYMBOL_MAX_DIM = 25.0      # a symbol is compact -> excludes long runs and large title/legend boxes
_STATION_X_TOL = 12.0       # a symbol's centroid-x must be this close to the bound station's projected x
_TIGHT_2D_TOL = 15.0        # run-terminal -> terminus-coordinate 2-D gap above which the endpoint is LOOSE


@dataclass(frozen=True)
class TerminusCoordinate:
    """The drawn coordinate (or honest refusal) for one source-bound endpoint."""
    result: str
    xy: Optional[Tuple[float, float]] = None
    provenance: Optional[str] = None
    detail: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Endpoint2DTightness:
    verdict: str
    gap: Optional[float] = None
    detail: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TerminusCoordinateObservation:
    """All four diagnostics for one bore, read-only. ``two_d_verified`` is True ONLY when branch is unique,
    station-x is tight, AND both endpoints are 2-D tight to a derived drawn coordinate — never from a guess."""
    branch_uniqueness: str
    endpoint_to_run_x_tightness: str
    start_coordinate: TerminusCoordinate
    end_coordinate: TerminusCoordinate
    start_2d: Endpoint2DTightness
    end_2d: Endpoint2DTightness
    would_reject: bool
    two_d_verified: bool
    reject_signals: Tuple[str, ...]
    notes: Tuple[str, ...]
    detail: Dict[str, Any] = field(default_factory=dict)


_NOTES = (
    "TERMINUS_DRAWN_COORDINATE is cold-lane GEOMETRY-ONLY (a compact drawn shape at the bound station); it is "
    "NOT class-verified. The class-verified analog is structure_position.resolve_structure_position, which "
    "needs a CAD layer table + class fill colors the generic/cold lane does not have",
    "2-D tightness uses a derived drawn coordinate or reports UNMEASURABLE — a missing coordinate never promotes",
    "single-sheet drawn geometry only; cross-sheet continuation is out of scope",
    "validated against the adversarial harness only; no eligible fresh non-recognized package exists in the repo "
    "(only the recognized work corpus + synthetic fixtures) so this is NOT proof of real generalization",
)


def _compact_symbols(shapes: Sequence[Dict[str, Any]],
                     *, min_dim: float = _SYMBOL_MIN_DIM, max_dim: float = _SYMBOL_MAX_DIM
                     ) -> List[Dict[str, Any]]:
    """Drawn shapes that look like a SYMBOL/marker: compact in BOTH dims (a long run line / baseline has ~0 in
    one dim; a station tick is a thin vertical line; a title/legend box is too big). Geometry only — no layer,
    no fill, no class. ``shapes`` is ``PlanPdf.vector_segments`` output (or equivalent dicts with x0/y0/x1/y1)."""
    out: List[Dict[str, Any]] = []
    for s in shapes:
        w = float(s["x1"]) - float(s["x0"])
        h = float(s["y1"]) - float(s["y0"])
        if min(w, h) >= min_dim and max(w, h) <= max_dim:
            out.append(s)
    return out


def derive_terminus_drawn_coordinate(shapes: Sequence[Dict[str, Any]], station_x: Optional[float],
                                     *, source_bound: bool, x_tol: float = _STATION_X_TOL,
                                     min_dim: float = _SYMBOL_MIN_DIM, max_dim: float = _SYMBOL_MAX_DIM
                                     ) -> TerminusCoordinate:
    """The drawn (x, y) of a source-bound terminus, from existing drawn geometry, uniqueness-mandatory.

    Returns ``NOT_SOURCE_BOUND`` when the endpoint has no printed identity (no coordinate to seek);
    ``NO_DRAWN_COORDINATE`` when no compact drawn shape sits at the bound station's x; ``AMBIGUOUS_DRAWN_COORDINATE``
    when >= 2 do (never chosen between); else ``DRAWN_COORDINATE_BOUND`` with the unique shape's centroid (xc, yc).
    Never invents a coordinate."""
    if not source_bound or station_x is None:
        return TerminusCoordinate(NOT_SOURCE_BOUND, detail={"station_x": station_x, "source_bound": source_bound})
    near = [s for s in _compact_symbols(shapes, min_dim=min_dim, max_dim=max_dim)
            if abs(float(s["xc"]) - float(station_x)) <= x_tol]
    if not near:
        return TerminusCoordinate(NO_DRAWN_COORDINATE,
                                  detail={"station_x": round(float(station_x), 2), "candidates": 0})
    if len(near) > 1:
        return TerminusCoordinate(
            AMBIGUOUS_DRAWN_COORDINATE,
            detail={"station_x": round(float(station_x), 2), "candidates": len(near),
                    "candidate_xys": [[round(float(s["xc"]), 1), round(float(s["yc"]), 1)] for s in near]})
    s = near[0]
    return TerminusCoordinate(DRAWN_COORDINATE_BOUND, xy=(float(s["xc"]), float(s["yc"])),
                              provenance=COMPACT_SYMBOL_AT_STATION,
                              detail={"station_x": round(float(station_x), 2)})


def endpoint_2d_tightness(run_terminal_xy: Optional[Tuple[float, float]], terminus_xy: Optional[Tuple[float, float]],
                          *, tol: float = _TIGHT_2D_TOL) -> Endpoint2DTightness:
    """2-D distance from the run's terminal to the terminus drawn coordinate. ``UNMEASURABLE`` when either is
    absent (no run terminal, or no derived coordinate) — never a guessed pass/fail."""
    if run_terminal_xy is None or terminus_xy is None:
        return Endpoint2DTightness(TIGHTNESS_2D_UNMEASURABLE)
    gap = math.hypot(run_terminal_xy[0] - terminus_xy[0], run_terminal_xy[1] - terminus_xy[1])
    return Endpoint2DTightness(TIGHTNESS_2D_TIGHT if gap <= tol else TIGHTNESS_2D_LOOSE,
                               gap=round(float(gap), 2), detail={"tol": tol})


def _inside_any(midpoint: Tuple[float, float], boxes: Sequence[Tuple[float, float, float, float]],
                pad: float = 2.0) -> bool:
    mx, my = midpoint
    for x0, y0, x1, y1 in boxes:
        if x0 - pad <= mx <= x1 + pad and y0 - pad <= my <= y1 + pad:
            return True
    return False


def observe_terminus_coordinates_core(shapes: Sequence[Dict[str, Any]], segments: Sequence[Dict[str, Any]],
                                      start_x: Optional[float], end_x: Optional[float],
                                      *, start_source_bound: bool, end_source_bound: bool,
                                      tight_tol: float = _TIGHT_2D_TOL, **run_kwargs: Any
                                      ) -> TerminusCoordinateObservation:
    """Pure core (no PlanPdf/dialect): compose branch + station-x (from ``observe_run_geometry``) with the 2-D
    terminus-coordinate layer over explicit ``shapes`` (vector_segments-style) + ``segments`` (band-segment-style).

    The run graph EXCLUDES detected compact symbols (the run is linework minus markers) so a drawn symbol at an
    endpoint does not weld into the run and falsely read as a fork."""
    symbols = _compact_symbols(shapes)
    sym_boxes = [(float(s["x0"]), float(s["y0"]), float(s["x1"]), float(s["y1"])) for s in symbols]
    run_segs = [s for s in segments
                if not (s.get("a") and s.get("b")
                        and _inside_any(((float(s["a"][0]) + float(s["b"][0])) / 2.0,
                                         (float(s["a"][1]) + float(s["b"][1])) / 2.0), sym_boxes))]

    base = observe_run_geometry(run_segs, start_x, end_x, **run_kwargs)
    terminals = (spanning_run_terminals(run_segs, start_x, end_x)
                 if (start_x is not None and end_x is not None) else None)
    start_term = terminals[0] if terminals else None
    end_term = terminals[1] if terminals else None

    start_coord = derive_terminus_drawn_coordinate(symbols, start_x, source_bound=start_source_bound)
    end_coord = derive_terminus_drawn_coordinate(symbols, end_x, source_bound=end_source_bound)
    start_2d = endpoint_2d_tightness(start_term, start_coord.xy, tol=tight_tol)
    end_2d = endpoint_2d_tightness(end_term, end_coord.xy, tol=tight_tol)

    reject_signals = list(base.reject_signals)              # prior BRANCH_PATH_UNIQUENESS + station-x tightness
    if TIGHTNESS_2D_LOOSE in (start_2d.verdict, end_2d.verdict):
        reject_signals.append(ENDPOINT_TO_TERMINUS_2D_TIGHTNESS)
    would_reject = bool(reject_signals)
    two_d_verified = (base.branch_uniqueness == BRANCH_UNIQUE
                      and base.endpoint_tightness == TIGHTNESS_TIGHT
                      and start_2d.verdict == TIGHTNESS_2D_TIGHT
                      and end_2d.verdict == TIGHTNESS_2D_TIGHT)

    return TerminusCoordinateObservation(
        branch_uniqueness=base.branch_uniqueness,
        endpoint_to_run_x_tightness=base.endpoint_tightness,
        start_coordinate=start_coord, end_coordinate=end_coord,
        start_2d=start_2d, end_2d=end_2d,
        would_reject=would_reject, two_d_verified=two_d_verified,
        reject_signals=tuple(reject_signals), notes=_NOTES,
        detail={"compact_symbols": len(symbols), "run_segments_used": len(run_segs),
                "start_terminal": [round(v, 1) for v in start_term] if start_term else None,
                "end_terminal": [round(v, 1) for v in end_term] if end_term else None,
                "run_detail": base.detail})


def observe_terminus_coordinates(plan: PlanPdf, dialect: GenericGeometryDialect, sheet: int,
                                 start_ft: float, end_ft: float, *, start_source_bound: bool,
                                 end_source_bound: bool, offset: int = 0, **kwargs: Any
                                 ) -> Optional[TerminusCoordinateObservation]:
    """Read-only adapter over a dialect that has already run ``extract_callouts`` on ``sheet``. Projects the
    bore stations to display-x via the fitted axis, reads the drawn shapes (``plan.vector_segments``) + the
    retained band segments (``dialect.band_segments_for``), and runs the core. Returns ``None`` if the sheet has
    no trustworthy station axis. Reads only; mutates nothing."""
    axis = dialect.axis_for(sheet)
    if axis is None:
        return None
    sx = axis.x_at(float(start_ft))
    ex = axis.x_at(float(end_ft))
    if sx is None or ex is None:
        return None
    return observe_terminus_coordinates_core(
        plan.vector_segments(sheet, offset), dialect.band_segments_for(sheet), sx, ex,
        start_source_bound=start_source_bound, end_source_bound=end_source_bound, **kwargs)


def observe_package_terminus_geometry(plan_path: str, sheet: int, start_ft: float, end_ft: float,
                                      *, start_source_bound: bool, end_source_bound: bool, offset: int = 0,
                                      **kwargs: Any) -> Optional[TerminusCoordinateObservation]:
    """The read-only VALIDATION-HARNESS PATH for a future real/fresh package: open the plan, run the generic
    dialect's ``extract_callouts`` read-only, and observe all four diagnostics for one bore. No eligible fresh
    non-recognized package exists in the repo today, so this PATH exists for future packages and claims no
    generalization. Opens + closes the PDF; writes nothing; runs no placement/render."""
    plan = PlanPdf(str(plan_path))
    try:
        dialect = GenericGeometryDialect()
        dialect.extract_callouts(plan, sheet, offset)
        return observe_terminus_coordinates(
            plan, dialect, sheet, start_ft, end_ft,
            start_source_bound=start_source_bound, end_source_bound=end_source_bound,
            offset=offset, **kwargs)
    finally:
        plan.close()
