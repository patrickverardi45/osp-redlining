"""Frozen EngineResult contract for the PDF-first redline engine (Day 1).

The FIELD NAMES here are the stable contract the future TrueLine adapter binds
to. Pure data + JSON serialization — NO ``fitz``, NO TrueLine imports.

Engine-level ``status`` vs per-item ``tier``:
  * ``status`` (engine-level): OK | FAIL_SAFE_GLOBAL | ERROR
  * ``tier`` (per item):       AUTO_SELECT | AUTO_PLACED_REQUIRES_APPROVAL |
                               SHARED_SEGMENT_REVIEW | MULTI_LOG_SEGMENT_REVIEW |
                               CONTINUATION_REVIEW | FAIL_SAFE
``render_target`` (Friday active = evidence_card): evidence_card | route_polyline | debug_overlay
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

CONTRACT_VERSION = "pdf_first.contract.1"
ENGINE_VERSION = "pdf_first.engine.0.1.0-day1"

# --- engine-level status -----------------------------------------------------
STATUS_OK = "OK"
STATUS_FAIL_SAFE_GLOBAL = "FAIL_SAFE_GLOBAL"
STATUS_ERROR = "ERROR"
ENGINE_STATUSES = frozenset({STATUS_OK, STATUS_FAIL_SAFE_GLOBAL, STATUS_ERROR})

# --- per-item tiers (the Day-1 "required statuses") --------------------------
TIER_AUTO_SELECT = "AUTO_SELECT"
TIER_AUTO_PLACED_REQUIRES_APPROVAL = "AUTO_PLACED_REQUIRES_APPROVAL"
TIER_SHARED_SEGMENT_REVIEW = "SHARED_SEGMENT_REVIEW"
TIER_MULTI_LOG_SEGMENT_REVIEW = "MULTI_LOG_SEGMENT_REVIEW"
TIER_CONTINUATION_REVIEW = "CONTINUATION_REVIEW"
TIER_FAIL_SAFE = "FAIL_SAFE"

VALID_TIERS = frozenset({
    TIER_AUTO_SELECT,
    TIER_AUTO_PLACED_REQUIRES_APPROVAL,
    TIER_SHARED_SEGMENT_REVIEW,
    TIER_MULTI_LOG_SEGMENT_REVIEW,
    TIER_CONTINUATION_REVIEW,
    TIER_FAIL_SAFE,
})

REVIEW_TIERS = frozenset({
    TIER_AUTO_PLACED_REQUIRES_APPROVAL,
    TIER_SHARED_SEGMENT_REVIEW,
    TIER_MULTI_LOG_SEGMENT_REVIEW,
    TIER_CONTINUATION_REVIEW,
})

# Union of every required status/tier NAME from the Day-1 spec (incl. ERROR).
ALL_STATUSES = frozenset(VALID_TIERS | {STATUS_ERROR})

# --- render targets ----------------------------------------------------------
RENDER_TARGET_EVIDENCE_CARD = "evidence_card"
RENDER_TARGET_ROUTE_POLYLINE = "route_polyline"
RENDER_TARGET_DEBUG_OVERLAY = "debug_overlay"
RENDER_TARGETS = frozenset({
    RENDER_TARGET_EVIDENCE_CARD,
    RENDER_TARGET_ROUTE_POLYLINE,
    RENDER_TARGET_DEBUG_OVERLAY,
})
RENDER_TARGET_DEFAULT = RENDER_TARGET_EVIDENCE_CARD  # Friday active target


# --- value objects -----------------------------------------------------------
@dataclass
class StationSpan:
    start: str
    end: str


@dataclass
class Caveat:
    code: str
    text: str


@dataclass
class Callout:
    text: str
    kind: str                                  # DIR_BORE | STRUCTURE | MATCHLINE
    sheet: Optional[int] = None
    page: Optional[int] = None                 # 1-based page = sheet + 13
    station_span: Optional[StationSpan] = None
    footage: Optional[float] = None
    conduit: Optional[str] = None
    bbox_display: Optional[List[float]] = None  # de-rotated [x0,y0,x1,y1]
    visually_verified: bool = False


@dataclass
class Evidence:
    funnel_path: List[str] = field(default_factory=list)
    matched_on: List[str] = field(default_factory=list)
    footage_check: Optional[Dict[str, float]] = None   # {authored, bore_log, delta}
    tiebreaker: Optional[str] = None
    matchline_seams: List[Dict[str, Any]] = field(default_factory=list)
    callout_ids: List[str] = field(default_factory=list)
    notes: Optional[str] = None


# --- Phase-2 Slice A/B: identity-anchored placement contract ----------------
# Slice A carried the GEOMETRY-FREE placement intent (absolute authored station
# feet + authored route key). Slice B (AP/structure-anchored geometry) lets a
# deterministic IDENTITY binder additionally attach a COORD-FREE chainage
# ``frame`` plus ``geo_anchors`` derived from EXACT AP/SPLICE_LOC joins against
# the RESOLVED KMZ anchor tables (anchors.json / sheet_station_model.json).
# The engine still binds NO route (``route_binding`` stays None) and performs NO
# coordinate-snapping / route-scoring / nearest-route / station-scaling / raw
# promotion. ``geo_anchors`` carry the verbatim surveyed coord of an EXACT,
# single-coordinate RESOLVED anchor only; they are review-panel EVIDENCE, never
# a map-draw surface (render_target stays evidence_card).
GEOMETRY_STATUS_NEEDS_IDENTITY_BINDING = "NEEDS_IDENTITY_BINDING"  # default: binder not run
GEOMETRY_STATUS_FRAME_ONLY = "FRAME_ONLY"                          # frame computed, no exact anchor
GEOMETRY_STATUS_AP_ANCHORED = "AP_ANCHORED"                        # >=1 exact RESOLVED anchor tie
GEOMETRY_STATUS_FAIL_SAFE_IDENTITY = "FAIL_SAFE_IDENTITY"          # ambiguous/missing -> not placed
# Fiber-drop enrichment of FRAME_ONLY: authored PDF-space drop/terminal evidence
# (exact STA-labelled flower pots + terminal cluster). REVIEW-grade, NOT anchored,
# NOT promoted, NOT map-ready. The flower-pot/terminal end has no exact KMZ
# identity, so it never reaches AP_ANCHORED / AUTO. Carries placement.drop_terminal.
GEOMETRY_STATUS_FRAME_WITH_DROP_TERMINAL_CANDIDATE = "FRAME_WITH_DROP_TERMINAL_CANDIDATE"
VALID_GEOMETRY_STATUSES = frozenset({
    GEOMETRY_STATUS_NEEDS_IDENTITY_BINDING,
    GEOMETRY_STATUS_FRAME_ONLY,
    GEOMETRY_STATUS_AP_ANCHORED,
    GEOMETRY_STATUS_FAIL_SAFE_IDENTITY,
    GEOMETRY_STATUS_FRAME_WITH_DROP_TERMINAL_CANDIDATE,
})

# geo_anchor provenance source. RESOLVED = present verbatim in anchors.json (this
# slice). PROMOTED (raw-KMZ promotion) is a SEPARATE, not-yet-implemented rule and
# is explicitly REJECTED by this contract's validator.
GEO_ANCHOR_SOURCE_RESOLVED = "RESOLVED"

# --- PDF bore-path trace (page-space authored run highlight) -----------------
# Traces the ACTUAL authored drawn run for a bore (page-space vector vertices),
# bound to the bore by AUTHORED IDENTITY only — never proximity. SEPARATE from
# pdf_redline so flag-OFF stays byte-identical. Carries NO lon/lat/KMZ/route_id.
PDF_PATH_TRACE_READY = "PDF_PATH_TRACE_READY"        # 1 authored-identity-bound run
PDF_PATH_TRACE_REVIEW = "PDF_PATH_TRACE_REVIEW"      # >=2 bound runs / no discriminator
PDF_PATH_TRACE_BLOCKED = "PDF_PATH_TRACE_BLOCKED"    # no bound run -> abstain (safe)
# Dash-chain reconstruction (the bored run is a dashed family, not a single polyline):
# a chain reconstructed from one authored stroke family, bound by authored LAYER
# (BORE-family) + callout corridor + station-tick corroboration.
PDF_PATH_TRACE_READY_DASH_CHAINED = "PDF_PATH_TRACE_READY_DASH_CHAINED"    # unique, fully bracketed
PDF_PATH_TRACE_REVIEW_DASH_CHAINED = "PDF_PATH_TRACE_REVIEW_DASH_CHAINED"  # bound + caveat (the bar)
VALID_PDF_PATH_TRACE_STATUSES = frozenset({
    PDF_PATH_TRACE_READY, PDF_PATH_TRACE_REVIEW, PDF_PATH_TRACE_BLOCKED,
    PDF_PATH_TRACE_READY_DASH_CHAINED, PDF_PATH_TRACE_REVIEW_DASH_CHAINED,
})
# Statuses that carry a DRAWN reconstructed/traced path (require path_points_display).
PDF_PATH_TRACE_DRAWING_STATUSES = frozenset({
    PDF_PATH_TRACE_READY, PDF_PATH_TRACE_READY_DASH_CHAINED, PDF_PATH_TRACE_REVIEW_DASH_CHAINED,
})
PDF_PATH_TRACE_RENDER_TARGET = "pdf_plan_overlay"    # backend QA overlay, NOT the world map

# Map/world keys that must NEVER appear anywhere inside a pdf_path_trace block.
_PDF_TRACE_FORBIDDEN_KEYS = frozenset({
    "coord", "coords", "lat", "lon", "lng", "latlon", "lat_lon", "map_points",
    "route_polyline", "route_id", "station_points", "info_boxes", "kmz",
})


def _scan_forbidden_keys(obj: Any) -> set:
    """Recursively collect any forbidden geo/map KEY NAMES present in ``obj``."""
    found: set = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in _PDF_TRACE_FORBIDDEN_KEYS:
                found.add(k)
            found |= _scan_forbidden_keys(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            found |= _scan_forbidden_keys(v)
    return found


def _validate_pdf_path_trace(segment_id: str, p: "Placement") -> List[str]:
    """Contract guarantees for a populated ``pdf_path_trace`` block: valid status,
    page-space-only (no geo/map keys), READY carries 2-float points, BLOCKED does
    not, and the trace is only valid on an anchored / drop-terminal placement."""
    out: List[str] = []
    t = p.pdf_path_trace
    if not isinstance(t, dict):
        return [f"segment {segment_id} pdf_path_trace must be a dict"]
    if p.geometry_status not in (GEOMETRY_STATUS_AP_ANCHORED,
                                 GEOMETRY_STATUS_FRAME_WITH_DROP_TERMINAL_CANDIDATE):
        out.append(f"segment {segment_id} pdf_path_trace only valid on AP_ANCHORED "
                   "or a drop-terminal candidate")
    status = t.get("trace_status")
    if status not in VALID_PDF_PATH_TRACE_STATUSES:
        out.append(f"segment {segment_id} invalid pdf_path_trace.trace_status {status!r}")
    if t.get("render_target") not in (PDF_PATH_TRACE_RENDER_TARGET, RENDER_TARGET_EVIDENCE_CARD):
        out.append(f"segment {segment_id} pdf_path_trace.render_target must be "
                   f"{PDF_PATH_TRACE_RENDER_TARGET}|{RENDER_TARGET_EVIDENCE_CARD}")
    bad = _scan_forbidden_keys(t)
    if bad:
        out.append(f"segment {segment_id} pdf_path_trace carries forbidden geo/map keys "
                   f"{sorted(bad)} (page-space only)")
    pts = t.get("path_points_display") or []
    if status in PDF_PATH_TRACE_DRAWING_STATUSES and not pts:
        out.append(f"segment {segment_id} {status} pdf_path_trace requires path_points_display")
    if status == PDF_PATH_TRACE_BLOCKED and pts:
        out.append(f"segment {segment_id} BLOCKED pdf_path_trace must not carry path_points_display")
    for pt in pts:
        if not (isinstance(pt, (list, tuple)) and len(pt) == 2
                and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in pt)):
            out.append(f"segment {segment_id} pdf_path_trace point is not a 2-float "
                       f"page coord: {pt!r}")
            break
    return out


@dataclass
class StationSpanFt:
    start: float
    end: float


@dataclass
class RouteKey:
    print_tokens: List[str] = field(default_factory=list)
    sheets: List[int] = field(default_factory=list)


@dataclass
class GeoAnchor:
    """One EXACT-identity coord tie, copied VERBATIM from a RESOLVED anchor —
    never derived, snapped, scored, or interpolated. ``coord`` is ``[lon, lat]``."""
    kind: str                          # AP | SPLICE_LOC
    id: str                            # e.g. "151" | "LOC34"
    sheet: int
    sta: Optional[float]               # authored station (feet) of the matched occurrence
    coord: List[float]                 # [lon, lat] verbatim from anchors.json
    chainage_ft: Optional[float] = None
    pxdist: Optional[float] = None
    source: str = GEO_ANCHOR_SOURCE_RESOLVED
    provenance: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Frame:
    """COORD-FREE chainage frame for a selected sheet. ``chainage = STA - datum``
    (datum from sheet_station_model clusters; subtraction only — no scaling)."""
    sheet: int
    page: Optional[int] = None
    datum_ft: float = 0.0
    chainage_start_ft: Optional[float] = None
    chainage_end_ft: Optional[float] = None
    axis: Dict[str, Any] = field(default_factory=dict)   # {vmin, vmax, clusters}
    eqs_used: List[str] = field(default_factory=list)
    multi_sheet: bool = False
    caveat: Optional[str] = None        # e.g. MATCHLINE_FRAME
    note: Optional[str] = None


@dataclass
class Placement:
    placement_segment_id: str
    station_span_ft: StationSpanFt
    footage_ft: Optional[float] = None
    route_key: RouteKey = field(default_factory=RouteKey)
    geometry_status: str = GEOMETRY_STATUS_NEEDS_IDENTITY_BINDING
    route_binding: Optional[Any] = None       # engine NEVER binds a route
    frame: Optional[Frame] = None             # coord-free chainage frame (binder-populated)
    geo_anchors: List[GeoAnchor] = field(default_factory=list)   # EXACT RESOLVED ties only
    evidence_trail: Optional[Dict[str, Any]] = None
    # Fiber-drop authored PDF-space evidence (review-grade; no coords, no KMZ, no
    # promotion). Present only with FRAME_WITH_DROP_TERMINAL_CANDIDATE.
    drop_terminal: Optional[Dict[str, Any]] = None
    # PDF-space redline overlay spec (de-rotated page coords / bbox_display only —
    # NEVER lon/lat or KMZ). Populated at RENDER time behind the draw flag; default
    # None keeps flag-OFF byte-identical. render_target stays evidence_card.
    pdf_redline: Optional[Dict[str, Any]] = None
    # PDF bore-path trace: the ACTUAL authored drawn run highlighted in de-rotated
    # PAGE space (vector vertices), identity-bound — never proximity. SEPARATE from
    # pdf_redline; default None keeps flag-OFF byte-identical. NO lon/lat/KMZ/route_id.
    pdf_path_trace: Optional[Dict[str, Any]] = None


@dataclass
class SelectedSegment:
    segment_id: str
    log_ids: List[str]
    tier: str
    print: Optional[str] = None
    sheets: List[int] = field(default_factory=list)
    station_span: Optional[StationSpan] = None
    footage: Optional[float] = None
    end_structures: List[str] = field(default_factory=list)
    conduit: Optional[str] = None
    callouts: List[Callout] = field(default_factory=list)
    evidence: Optional[Evidence] = None
    render_target: str = RENDER_TARGET_DEFAULT
    group_id: Optional[str] = None
    caveat: Optional[Caveat] = None
    requires_approval: bool = False
    placement: Optional[Placement] = None


@dataclass
class FailSafeItem:
    log_ids: List[str]
    reason: str
    tier: str = TIER_FAIL_SAFE
    candidates: List[Dict[str, Any]] = field(default_factory=list)
    render_target: Optional[str] = None        # nothing is placed
    evidence: Optional[Evidence] = None


@dataclass
class RenderArtifact:
    artifact_id: str
    segment_id: Optional[str]
    render_target: str
    kind: str                                  # e.g. "evidence_card"
    ref: Optional[str] = None                  # path to a crop PNG (Day-1: None)
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EngineResult:
    job_id: str
    status: str
    engine_version: str = ENGINE_VERSION
    contract_version: str = CONTRACT_VERSION
    render_target: str = RENDER_TARGET_DEFAULT
    source: Dict[str, Any] = field(default_factory=dict)
    selected_segments: List[SelectedSegment] = field(default_factory=list)
    review_items: List[SelectedSegment] = field(default_factory=list)
    fail_safe_items: List[FailSafeItem] = field(default_factory=list)
    render_artifacts: List[RenderArtifact] = field(default_factory=list)
    evidence: Dict[str, Any] = field(default_factory=dict)   # run-level provenance
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=False)

    def validate(self) -> List[str]:
        """Return a list of contract problems (empty == valid)."""
        problems: List[str] = []
        if self.status not in ENGINE_STATUSES:
            problems.append(f"invalid engine status: {self.status!r}")
        if self.render_target not in RENDER_TARGETS:
            problems.append(f"invalid engine render_target: {self.render_target!r}")
        for seg in list(self.selected_segments) + list(self.review_items):
            if seg.tier not in VALID_TIERS:
                problems.append(f"invalid tier on {seg.segment_id}: {seg.tier!r}")
            if seg.render_target not in RENDER_TARGETS:
                problems.append(f"invalid render_target on {seg.segment_id}: {seg.render_target!r}")
            if not seg.log_ids:
                problems.append(f"segment {seg.segment_id} missing log_ids")
            if seg.placement is not None:
                p = seg.placement
                if p.route_binding is not None:
                    problems.append(
                        f"segment {seg.segment_id} placement.route_binding must be null "
                        "(engine never binds routes)")
                if p.geometry_status not in VALID_GEOMETRY_STATUSES:
                    problems.append(
                        f"segment {seg.segment_id} invalid geometry_status {p.geometry_status!r}")
                if p.geometry_status == GEOMETRY_STATUS_AP_ANCHORED and not p.geo_anchors:
                    problems.append(
                        f"segment {seg.segment_id} AP_ANCHORED requires >=1 geo_anchor")
                if (p.geometry_status in (GEOMETRY_STATUS_NEEDS_IDENTITY_BINDING,
                                          GEOMETRY_STATUS_FAIL_SAFE_IDENTITY,
                                          GEOMETRY_STATUS_FRAME_WITH_DROP_TERMINAL_CANDIDATE)
                        and p.geo_anchors):
                    problems.append(
                        f"segment {seg.segment_id} geo_anchors present without an anchored status")
                if (p.geometry_status == GEOMETRY_STATUS_FRAME_WITH_DROP_TERMINAL_CANDIDATE
                        and not p.drop_terminal):
                    problems.append(
                        f"segment {seg.segment_id} FRAME_WITH_DROP_TERMINAL_CANDIDATE requires "
                        "a drop_terminal block")
                if p.pdf_redline is not None:
                    rt = p.pdf_redline.get("render_target") if isinstance(p.pdf_redline, dict) else None
                    if rt not in ("evidence_card", "debug_plan_overlay"):
                        problems.append(
                            f"segment {seg.segment_id} pdf_redline.render_target must be "
                            "evidence_card|debug_plan_overlay")
                    if p.geometry_status not in (GEOMETRY_STATUS_FRAME_WITH_DROP_TERMINAL_CANDIDATE,
                                                 GEOMETRY_STATUS_AP_ANCHORED):
                        problems.append(
                            f"segment {seg.segment_id} pdf_redline only valid on AP_ANCHORED "
                            "or a drop-terminal candidate")
                if p.pdf_path_trace is not None:
                    problems.extend(_validate_pdf_path_trace(seg.segment_id, p))
                for ga in p.geo_anchors:
                    if ga.source != GEO_ANCHOR_SOURCE_RESOLVED:
                        problems.append(
                            f"segment {seg.segment_id} geo_anchor {ga.id} source must be RESOLVED "
                            f"(no promotion), got {ga.source!r}")
                    if not ga.provenance:
                        problems.append(
                            f"segment {seg.segment_id} geo_anchor {ga.id} missing provenance")
                    if not (isinstance(ga.coord, list) and len(ga.coord) == 2):
                        problems.append(
                            f"segment {seg.segment_id} geo_anchor {ga.id} coord must be [lon,lat]")
        for seg in self.review_items:
            if seg.tier not in REVIEW_TIERS:
                problems.append(f"review_item {seg.segment_id} has non-review tier {seg.tier!r}")
        for fs in self.fail_safe_items:
            if fs.tier != TIER_FAIL_SAFE:
                problems.append(f"fail_safe_item tier must be FAIL_SAFE, got {fs.tier!r}")
            if not fs.log_ids:
                problems.append("fail_safe_item missing log_ids")
        return problems

    def is_valid(self) -> bool:
        return not self.validate()


def error_result(job_id: str, message: str,
                 source: Optional[Dict[str, Any]] = None) -> EngineResult:
    """Build an ERROR-status result instead of raising to the caller."""
    return EngineResult(
        job_id=job_id,
        status=STATUS_ERROR,
        source=source or {},
        evidence={"error": message},
        warnings=[f"engine error: {message}"],
    )
