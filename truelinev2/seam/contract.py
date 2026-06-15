r"""Coordinate-free exemplar -> pipeline SEAM contract (PURE; no PDF / render / product imports).

Formalizes the normalized payload the exemplar-pipeline seam scout (444beb5) proposed into a typed,
reusable internal schema for the FIVE eligible exemplars only:

  log53 -- two_sheet_matchline_endpoint                       (STA 24+11 modeled AS a matchline endpoint)
  log64 -- single_sheet_structure_to_structure
  log71 -- two_sheet_structure_to_structure_route_context     (STA 5+45 is route context, NOT an endpoint)
  log59 -- single_sheet_structure_to_structure                (ordered_chain_path: direct corridor discontinuous)
  log66 -- single_sheet_structure_to_structure                (installer_hh -> nextlink_hh; ordered_chain_path)

The payload carries endpoint IDENTITY + BOUNDARY semantics + route MODE + source-evidence DESCRIPTORS.
It is deliberately COORDINATE-FREE: it never carries a position, and never reconciles two sheet
frames -- the deterministic engine still computes every coordinate from PDF primitives downstream
(exactly as the source-bind + render proofs do). Downstream proofs consume this contract later.

This module does NOT wire into product/runtime, render anything, batch-place anything, aggregate
parent/child runs, resolve a representative route, or solve a cross-sheet frame. Eligibility never
expands silently here: ``build_seam_payload`` REFUSES any log that is not one of the proven eligible
exemplars with committed endpoint_anchors. log59 then log66 were each added only after their
owner-confirmed sheet (corrected_sheets) + source-bind + render proofs all passed (no silent promotion).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Tuple


class BoundaryKind(str, Enum):
    STRUCTURE_TERMINUS = "structure_terminus"
    MATCHLINE_CONTINUATION = "matchline_continuation"        # a MODELED matchline endpoint (log53)
    MATCHLINE_ROUTE_CONTEXT = "matchline_route_context"      # intermediate route context (log71 5+45)


class RenderMode(str, Enum):
    CONTINUOUS_CORRIDOR = "continuous_corridor"
    ORDERED_CHAIN_PATH = "ordered_chain_path"                # follows a drawn BEND (log71 sheet 24)


class SeamShape(str, Enum):
    SINGLE_SHEET_STRUCTURE_TO_STRUCTURE = "single_sheet_structure_to_structure"
    TWO_SHEET_MATCHLINE_ENDPOINT = "two_sheet_matchline_endpoint"
    TWO_SHEET_STRUCTURE_TO_STRUCTURE_ROUTE_CONTEXT = "two_sheet_structure_to_structure_route_context"


ELIGIBLE_EXEMPLARS: Tuple[str, ...] = ("log53", "log64", "log71", "log59", "log66")

# Coordinate-style keys the seam payload must NEVER carry (it is identity/contract only).
_COORD_KEYS = frozenset({
    "x", "y", "z", "xc", "yc", "x0", "y0", "x1", "y1", "xy", "cx", "cy", "lat", "lon", "lng",
    "coord", "coords", "coordinate", "coordinates", "px", "py", "point", "points", "symbol_xy",
    "anchor_xy", "stroke", "stroke_points", "geometry", "geom", "symbol_x", "symbol_y",
    "vertices", "route_vertices",
})


@dataclass(frozen=True)
class LegBoundary:
    """One end of a sheet-local leg. Coordinate-free: identity + boundary semantics only."""
    role: str                                       # "start" | "end" | "matchline" | "continuation_terminus"
    boundary_kind: BoundaryKind
    station: Optional[str] = None
    structure_class: Optional[str] = None
    structure_label: Optional[str] = None
    clarity: Optional[str] = None
    from_endpoint_anchor: bool = False
    source_binder: Optional[str] = None
    provenance: Optional[str] = None


@dataclass(frozen=True)
class SourceEvidence:
    conduit: str = "base_conduit_chain"
    terminus_binders: Tuple[str, ...] = ()


@dataclass(frozen=True)
class RouteContext:
    matchline_station: str
    role: str                                       # "modeled_matchline_endpoint" | "between_leg_crossing_route_context"


@dataclass(frozen=True)
class SeamLeg:
    sheet: int
    start_anchor: LegBoundary
    end_anchor: LegBoundary
    route_context: Optional[RouteContext]
    render_mode: RenderMode
    source_evidence: SourceEvidence


@dataclass(frozen=True)
class SeamPayload:
    bore_id: str
    shape: SeamShape
    review_status: Optional[str]
    eligible: bool
    abstain_reason: Optional[str]
    sheets: Tuple[int, ...]
    legs: Tuple[SeamLeg, ...]
    matchline_stations: Tuple[str, ...]
    cross_sheet_join: Optional[str]
    cross_sheet_coordinate_reconciliation: bool

    def to_dict(self) -> dict:
        """Coordinate-free serialized form (enums -> their string value; tuples -> lists)."""
        return _serialize(self)


# Proven exemplar topology -- the parts NOT carried by endpoint_anchors: per-leg (sheet, render_mode)
# and the matchline split station. Boundary KINDS are READ from the committed endpoint_anchors at
# build time (so the matchline-endpoint-vs-route-context distinction is derived, never hardcoded).
# render_mode is what each committed source-bind + render proof established: a leg whose direct
# corridor is discontinuous (direct_corridor_continuous == False) -> ordered_chain_path (log71 sheet
# 24 bends; log59 sheet 21's direct corridor has a 35.64 pt gap > MAX_DASH_GAP); every other proven
# leg is a continuous corridor. log59 + log66 share log64's SINGLE_SHEET shape but their OWN ordered
# route mode (log66 is installer_hh -> nextlink_hh; sheet 10's direct corridor has a 36.36 pt gap).
_AnchorRef = Tuple[str, ...]
EXEMPLAR_TOPOLOGY: Dict[str, dict] = {
    "log64": {"shape": SeamShape.SINGLE_SHEET_STRUCTURE_TO_STRUCTURE, "sheets": (21,),
              "legs": ((21, ("anchor", "start"), ("anchor", "end"), RenderMode.CONTINUOUS_CORRIDOR),)},
    "log53": {"shape": SeamShape.TWO_SHEET_MATCHLINE_ENDPOINT, "sheets": (5, 6),
              "legs": ((5, ("anchor", "start"), ("matchline", "24+11"), RenderMode.CONTINUOUS_CORRIDOR),
                       (6, ("matchline", "24+11"), ("continuation", "26+38"), RenderMode.CONTINUOUS_CORRIDOR))},
    "log71": {"shape": SeamShape.TWO_SHEET_STRUCTURE_TO_STRUCTURE_ROUTE_CONTEXT, "sheets": (24, 23),
              "legs": ((24, ("anchor", "start"), ("matchline", "5+45"), RenderMode.ORDERED_CHAIN_PATH),
                       (23, ("matchline", "5+45"), ("anchor", "end"), RenderMode.CONTINUOUS_CORRIDOR))},
    "log59": {"shape": SeamShape.SINGLE_SHEET_STRUCTURE_TO_STRUCTURE, "sheets": (21,),
              "legs": ((21, ("anchor", "start"), ("anchor", "end"), RenderMode.ORDERED_CHAIN_PATH),)},
    "log66": {"shape": SeamShape.SINGLE_SHEET_STRUCTURE_TO_STRUCTURE, "sheets": (10,),
              "legs": ((10, ("anchor", "start"), ("anchor", "end"), RenderMode.ORDERED_CHAIN_PATH),)},
}


def _serialize(value):
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return {f: _serialize(getattr(value, f)) for f in value.__dataclass_fields__}
    if isinstance(value, (list, tuple)):
        return [_serialize(v) for v in value]
    return value


def is_coordinate_free(obj) -> bool:
    """True when no dict key anywhere in ``obj`` is a coordinate-style key. The seam contract carries
    identity/semantics only; positions are computed downstream by the deterministic engine."""
    if isinstance(obj, dict):
        if {str(k).lower() for k in obj} & _COORD_KEYS:
            return False
        return all(is_coordinate_free(v) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        return all(is_coordinate_free(v) for v in obj)
    return True


def _terminus_binder(structure_class: Optional[str]) -> Optional[str]:
    if structure_class == "nextlink_hh":
        return "nextlink_hh_callout_locator"
    if structure_class:
        return "structure_position_label_leader_symbol"
    return None


def _resolve_boundary(ref: _AnchorRef, anchors: dict) -> LegBoundary:
    """Resolve a topology leg-boundary ref into a coordinate-free LegBoundary. ``('anchor', which)``
    reads the committed endpoint anchor (kind = its boundary_kind); ``('matchline', sta)`` is a
    MODELED matchline endpoint IFF an anchor carries boundary_kind matchline_continuation at that
    station (log53), else route context (log71 5+45); ``('continuation', sta)`` is the far structure
    terminus named by an anchor's continues_as (re-derived at render). Invents no coordinate."""
    kind_ref = ref[0]
    arg = ref[1] if len(ref) > 1 else None
    if kind_ref == "anchor":
        a = anchors.get(arg) or {}
        return LegBoundary(role=arg, boundary_kind=BoundaryKind(a.get("boundary_kind")),
                           station=a.get("station"), structure_class=a.get("structure_class"),
                           structure_label=a.get("structure_label"), clarity=a.get("clarity"),
                           from_endpoint_anchor=True,
                           source_binder=_terminus_binder(a.get("structure_class")))
    if kind_ref == "matchline":
        modeled = any((anchors.get(w) or {}).get("boundary_kind") == "matchline_continuation"
                      and (anchors.get(w) or {}).get("station") == arg for w in ("start", "end"))
        return LegBoundary(
            role="matchline",
            boundary_kind=(BoundaryKind.MATCHLINE_CONTINUATION if modeled
                           else BoundaryKind.MATCHLINE_ROUTE_CONTEXT),
            station=arg, from_endpoint_anchor=modeled,
            source_binder="locate_matchline_boundary_chain_reach")
    # continuation terminus (named by endpoint_anchors.end.continues_as; class re-derived at render)
    return LegBoundary(role="continuation_terminus", boundary_kind=BoundaryKind.STRUCTURE_TERMINUS,
                       station=arg, structure_class="flower_pot", structure_label="FLOWER POT",
                       from_endpoint_anchor=False,
                       source_binder="structure_position_label_leader_symbol",
                       provenance="endpoint_anchor.continues_as + render re-derivation")


def build_seam_payload(log_id: str, record: dict) -> SeamPayload:
    """Build the coordinate-free normalized seam payload for ONE eligible exemplar from its committed
    endpoint_anchors + the proven topology. Refuses any non-eligible log and any log without committed
    endpoint_anchors -- eligibility never expands here (no silent promotion)."""
    if log_id not in ELIGIBLE_EXEMPLARS:
        raise ValueError(f"seam contract is eligibility-frozen to {ELIGIBLE_EXEMPLARS}; "
                         f"{log_id!r} is not an eligible exemplar")
    anchors = (record or {}).get("endpoint_anchors") or {}
    if not anchors:
        raise ValueError(f"{log_id!r} has no committed endpoint_anchors (eligibility requires them)")
    topo = EXEMPLAR_TOPOLOGY[log_id]
    legs = []
    for sheet, start_ref, end_ref, mode in topo["legs"]:
        start_b = _resolve_boundary(start_ref, anchors)
        end_b = _resolve_boundary(end_ref, anchors)
        matchline = next((b for b in (start_b, end_b) if b.boundary_kind in
                          (BoundaryKind.MATCHLINE_CONTINUATION, BoundaryKind.MATCHLINE_ROUTE_CONTEXT)), None)
        route_context = None
        if matchline is not None:
            route_context = RouteContext(
                matchline_station=matchline.station,
                role=("modeled_matchline_endpoint"
                      if matchline.boundary_kind == BoundaryKind.MATCHLINE_CONTINUATION
                      else "between_leg_crossing_route_context"))
        binders = tuple(sorted({b.source_binder for b in (start_b, end_b) if b.source_binder}))
        legs.append(SeamLeg(sheet=sheet, start_anchor=start_b, end_anchor=end_b,
                            route_context=route_context, render_mode=mode,
                            source_evidence=SourceEvidence(conduit="base_conduit_chain",
                                                           terminus_binders=binders)))
    matchline_stations = tuple(sorted({leg.route_context.matchline_station
                                       for leg in legs if leg.route_context}))
    return SeamPayload(
        bore_id=log_id, shape=topo["shape"], review_status=(record or {}).get("status"),
        eligible=True, abstain_reason=None, sheets=tuple(topo["sheets"]), legs=tuple(legs),
        matchline_stations=matchline_stations,
        cross_sheet_join=("deferred" if len(topo["sheets"]) > 1 else None),
        cross_sheet_coordinate_reconciliation=False)


def eligible_seam_payloads(doc: dict) -> Dict[str, SeamPayload]:
    """Seam payloads for exactly the three eligible exemplars, keyed by bore_id. Never promotes
    another log: only ``ELIGIBLE_EXEMPLARS`` are built."""
    rec = {r["log_id"]: r for r in doc["logs"]}
    return {lid: build_seam_payload(lid, rec[lid]) for lid in ELIGIBLE_EXEMPLARS}
