"""PHASE-2 SOURCE-ROUTE ADOPTION — pure derivation (contract-only; no I/O, no fitz/PlanPdf import).

Per the pinned design authority (T31, ``.foreman/scratch/sol-p2-spec-out.md`` Q1-Q9): given a source-backed,
READY_FOR_REVIEW_REDLINE observer backbone (``RouteVerification.route_geometry`` — ordered ``{"a": (x,y), "b":
(x,y)}`` segments in PDF display-space) and exactly two HUMAN control points marked on the same page, this module
projects the human controls onto the backbone, clips the backbone between the projections, and derives a
server-owned RENDER polyline that keeps the human's exact clicks as termini while inheriting every source bend
in between. It invents no geometry: every accepted point is either a human click or a vertex/projection taken
directly from the observer-exposed backbone.

Every operation here is a PURE FUNCTION over its explicit inputs (no store, no PlanPdf, no fitz, no readiness
spine, no network). The caller (the proposal API route / the source-anchor create-time re-derivation) is
responsible for supplying the observer backbone segments, the inherited ``reach_tol`` (read from
``RouteVerification.detail["isolation"]["detail"]["reach_tol"]`` — NEVER hardcoded here), and the scope/hash
inputs. Nothing here writes a file, renders a stroke, or promotes AUTO/placement/status.

Refusal taxonomy (Q3 + the foreman P2 pins): every refusal is a NAMED code with a plain-English, path-free
message — never a generic exception string leaked to the client. A refusal never returns proposal geometry or a
hash. Degenerate geometry refuses (``BACKBONE_*``, projection/tolerance/ambiguity/extent/order codes,
``ZERO_LENGTH_PROPOSAL``); join-level mismatches refuse with their own named codes (``ROW_NOT_ENGINE_ELIGIBLE``,
``ROW_SOURCE_UPLOAD_MISMATCH``, ``ROW_SPAN_MISMATCH``, ``CROSS_PAGE_CANDIDATE``, ``MULTIPLE_READY_CANDIDATES``);
an upstream readiness spine that is not READY refuses as ``ROUTE_EVIDENCE_NOT_READY`` with the spine's own status
carried as ``upstream_reason_code`` (never invented). Create-time re-derivation failures (Q4) are separate named
exceptions (``ROUTE_ADOPTION_INVALID`` 400; ``ROUTE_ADOPTION_CONTROL_MISMATCH`` / ``ROUTE_ADOPTION_STALE`` /
``ROUTE_ADOPTION_NO_LONGER_DEFENSIBLE`` / ``ROUTE_ADOPTION_SCOPE_MISMATCH`` 409) mapped by the API's ``_to_http``
convention, detail string LEADING with the code token.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

ALGORITHM_VERSION = "route-adoption-1"
COORDINATE_SPACE = "pdf_display_space"
GEOMETRY_BASIS = "OBSERVER_BACKBONE_HUMAN_ADOPTED"
GEOMETRY_SOURCE = "READY_FOR_REVIEW_REDLINE_OBSERVER_BACKBONE"
CONFIRMATION_STATE = "HUMAN_REVIEWED"
CONNECTOR_WARNING = "HUMAN_CONTROL_TO_BACKBONE_CONNECTOR"

_PROPOSAL_ID_PREFIX = "rap-"
_HASH_PREFIX = "sha256:"
# Fix-wave F1/F2/F3/F4 (blind-verification FAIL): every GEOMETRIC proximity/contiguity/tolerance/dedup/
# connector rule is EXACT — no epsilon. `_TIE_EPS` is the ONLY remaining tolerance in this module and it
# exists SOLELY to group multiple independently-computed candidate distances that are the SAME real number
# (two segments meeting at a shared vertex necessarily produce point-identical projections whose floating
# `math.hypot` results can differ in the last bit) into one tie set for `_resolve_projection`'s tie-vs-
# ambiguous decision — it is never used to treat two DIFFERENT physical locations as equal, never used for
# backbone contiguity, never used for the reach_tol boundary, never used for dedup, and never used to decide
# whether a human click coincides with its projection.
_TIE_EPS = 1e-9

# --- Q3 geometry / connectivity refusal codes -------------------------------------------------------------- #
BACKBONE_EMPTY = "BACKBONE_EMPTY"
BACKBONE_MALFORMED = "BACKBONE_MALFORMED"
BACKBONE_DISCONTINUOUS = "BACKBONE_DISCONTINUOUS"
BACKBONE_CONTAINS_HYPOTHETICAL_GAP_BRIDGE = "BACKBONE_CONTAINS_HYPOTHETICAL_GAP_BRIDGE"
SOURCE_TOLERANCE_UNAVAILABLE = "SOURCE_TOLERANCE_UNAVAILABLE"
START_CONTROL_OUTSIDE_TOLERANCE = "START_CONTROL_OUTSIDE_TOLERANCE"
END_CONTROL_OUTSIDE_TOLERANCE = "END_CONTROL_OUTSIDE_TOLERANCE"
AMBIGUOUS_START_PROJECTION = "AMBIGUOUS_START_PROJECTION"
AMBIGUOUS_END_PROJECTION = "AMBIGUOUS_END_PROJECTION"
START_CONTROL_BEYOND_BACKBONE_EXTENT = "START_CONTROL_BEYOND_BACKBONE_EXTENT"
END_CONTROL_BEYOND_BACKBONE_EXTENT = "END_CONTROL_BEYOND_BACKBONE_EXTENT"
CONTROL_PROJECTIONS_COINCIDE = "CONTROL_PROJECTIONS_COINCIDE"
CONTROL_ORDER_REVERSED = "CONTROL_ORDER_REVERSED"
CONTROLS_ON_SAME_BACKBONE_SEGMENT = "CONTROLS_ON_SAME_BACKBONE_SEGMENT"
ZERO_LENGTH_PROPOSAL = "ZERO_LENGTH_PROPOSAL"
CROSS_PAGE_CANDIDATE = "CROSS_PAGE_CANDIDATE"
MULTIPLE_READY_CANDIDATES = "MULTIPLE_READY_CANDIDATES"

# --- Q2 join-level refusal codes (foreman P2) -------------------------------------------------------------- #
ROUTE_EVIDENCE_NOT_READY = "ROUTE_EVIDENCE_NOT_READY"     # two-level: upstream_reason_code carries the spine status
ROW_NOT_ENGINE_ELIGIBLE = "ROW_NOT_ENGINE_ELIGIBLE"
ROW_SOURCE_UPLOAD_MISMATCH = "ROW_SOURCE_UPLOAD_MISMATCH"
ROW_SPAN_MISMATCH = "ROW_SPAN_MISMATCH"

# --- Q1 malformed-request refusal (400, before any derivation runs) ----------------------------------------- #
MALFORMED_CONTROL_POINTS = "MALFORMED_CONTROL_POINTS"

ALL_REFUSAL_CODES = frozenset({
    BACKBONE_EMPTY, BACKBONE_MALFORMED, BACKBONE_DISCONTINUOUS,
    BACKBONE_CONTAINS_HYPOTHETICAL_GAP_BRIDGE, SOURCE_TOLERANCE_UNAVAILABLE,
    START_CONTROL_OUTSIDE_TOLERANCE, END_CONTROL_OUTSIDE_TOLERANCE,
    AMBIGUOUS_START_PROJECTION, AMBIGUOUS_END_PROJECTION,
    START_CONTROL_BEYOND_BACKBONE_EXTENT, END_CONTROL_BEYOND_BACKBONE_EXTENT,
    CONTROL_PROJECTIONS_COINCIDE, CONTROL_ORDER_REVERSED, CONTROLS_ON_SAME_BACKBONE_SEGMENT,
    ZERO_LENGTH_PROPOSAL, CROSS_PAGE_CANDIDATE, MULTIPLE_READY_CANDIDATES,
    ROUTE_EVIDENCE_NOT_READY, ROW_NOT_ENGINE_ELIGIBLE, ROW_SOURCE_UPLOAD_MISMATCH, ROW_SPAN_MISMATCH,
    MALFORMED_CONTROL_POINTS,
})

# --- Q4 create-time adoption exceptions (mapped by the API's _to_http; code LEADS the detail string) -------- #
_ADOPTION_INVALID = "ROUTE_ADOPTION_INVALID"
_ADOPTION_CONTROL_MISMATCH = "ROUTE_ADOPTION_CONTROL_MISMATCH"
_ADOPTION_STALE = "ROUTE_ADOPTION_STALE"
_ADOPTION_NO_LONGER_DEFENSIBLE = "ROUTE_ADOPTION_NO_LONGER_DEFENSIBLE"
_ADOPTION_SCOPE_MISMATCH = "ROUTE_ADOPTION_SCOPE_MISMATCH"


class RouteAdoptionError(ValueError):
    """Base for every create-time route-adoption re-derivation failure. ``code`` LEADS ``str(exc)`` (the repo's
    code-first detail-string convention) so ``detail.split(":", 1)[0] == code``."""
    code = _ADOPTION_INVALID

    def __init__(self, message: str):
        super().__init__("%s: %s" % (self.code, message))
        self.message = message


class RouteAdoptionInvalidError(RouteAdoptionError):
    """400 — malformed hash / confirmed != true / control_points count != 2 when route_adoption is present."""
    code = _ADOPTION_INVALID


class RouteAdoptionControlMismatchError(RouteAdoptionError):
    """409 — the submitted control_points differ from the proposal-bound controls."""
    code = _ADOPTION_CONTROL_MISMATCH


class RouteAdoptionStaleError(RouteAdoptionError):
    """409 — the current re-derived hash differs from the submitted proposal_hash."""
    code = _ADOPTION_STALE


class RouteAdoptionNoLongerDefensibleError(RouteAdoptionError):
    """409 — the current re-derivation now refuses (the nested current refusal code is in the message)."""
    code = _ADOPTION_NO_LONGER_DEFENSIBLE


class RouteAdoptionScopeMismatchError(RouteAdoptionError):
    """409 — plan/RBL/page/row identity in the create request differs from the proposal's bound scope."""
    code = _ADOPTION_SCOPE_MISMATCH


# ============================================================================================================ #
# Result contracts.
# ============================================================================================================ #
@dataclass(frozen=True)
class RouteAdoptionRefusal:
    code: str
    message: str
    upstream_reason_code: Optional[str] = None
    warnings: Tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message,
                "upstream_reason_code": self.upstream_reason_code, "warnings": list(self.warnings)}


@dataclass(frozen=True)
class RouteProposal:
    proposal_id: str
    proposal_hash: str
    candidate_route_hash: str
    coordinate_space: str
    geometry_basis: str
    confirmation_required: bool
    source: Dict[str, Any]
    readiness: Dict[str, Any]
    human_control_points: Tuple[Dict[str, float], ...]
    candidate_route_points: Tuple[Dict[str, float], ...]
    proposed_render_points: Tuple[Dict[str, float], ...]
    connectivity: Dict[str, Any]
    warnings: Tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "proposal_id": self.proposal_id, "proposal_hash": self.proposal_hash,
            "candidate_route_hash": self.candidate_route_hash, "coordinate_space": self.coordinate_space,
            "geometry_basis": self.geometry_basis, "confirmation_required": self.confirmation_required,
            "source": dict(self.source), "readiness": dict(self.readiness),
            "human_control_points": [dict(p) for p in self.human_control_points],
            "candidate_route_points": [dict(p) for p in self.candidate_route_points],
            "proposed_render_points": [dict(p) for p in self.proposed_render_points],
            "connectivity": dict(self.connectivity), "warnings": list(self.warnings),
        }


# ============================================================================================================ #
# Canonicalization + hashing (Q4).
# ============================================================================================================ #
def _normalize_number(v: Any) -> Any:
    if isinstance(v, bool):
        return v
    if isinstance(v, float):
        if not math.isfinite(v):
            raise ValueError("non-finite number in hash input: %r" % (v,))
        return 0.0 if v == 0.0 else v          # normalize -0.0 -> 0.0
    return v


def _normalize(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _normalize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_normalize(v) for v in obj]
    if isinstance(obj, float):
        return _normalize_number(obj)
    return obj


def canonical_json_bytes(obj: Any) -> bytes:
    """Sorted-key, compact-separator, finite-numbers-only canonical JSON (Q4). ``-0.0`` normalizes to ``0.0``;
    a non-finite number raises (never silently hashed as NaN/Infinity)."""
    normalized = _normalize(obj)
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256_hex(obj: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(obj)).hexdigest()


def _hash_tag(hex_digest: str) -> str:
    return _HASH_PREFIX + hex_digest


# ============================================================================================================ #
# Point / segment coercion.
# ============================================================================================================ #
def _finite(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _coerce_point(p: Any) -> Tuple[float, float]:
    """Coerce {"x":..,"y":..} or a 2-sequence to a finite (float,float). Raises ValueError on anything else —
    the caller maps that to BACKBONE_MALFORMED / MALFORMED_CONTROL_POINTS as appropriate."""
    if isinstance(p, dict):
        x, y = p.get("x"), p.get("y")
    else:
        x, y = p[0], p[1]
    x, y = float(x), float(y)
    if not (math.isfinite(x) and math.isfinite(y)):
        raise ValueError("non-finite point")
    return (x, y)


def _pt_dict(p: Tuple[float, float]) -> Dict[str, float]:
    x, y = p
    return {"x": (0.0 if x == 0.0 else x), "y": (0.0 if y == 0.0 else y)}


def _dist(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _norm0(v: float) -> float:
    return 0.0 if v == 0.0 else v          # -0.0 -> 0.0, otherwise identity


def _exact_point_eq(a: Tuple[float, float], b: Tuple[float, float]) -> bool:
    """EXACT point equality (Fix-wave F1/F3): after ``-0.0`` normalization, bit-for-bit float equality — NO
    proximity epsilon. This is the ONLY notion of "same point" backbone contiguity, render-polyline dedup, and
    connector-warning detection use. A 5e-7 gap is a DIFFERENT point, full stop."""
    return (_norm0(a[0]), _norm0(a[1])) == (_norm0(b[0]), _norm0(b[1]))


# ============================================================================================================ #
# Backbone ordering / contiguity (Q1 + Q3).
# ============================================================================================================ #
def backbone_points_from_segments(segments: Sequence[Dict[str, Any]]
                                  ) -> Tuple[Optional[List[Tuple[float, float]]], Optional[RouteAdoptionRefusal]]:
    """Convert ordered ``{"a":(x,y), "b":(x,y)}`` segments into an ordered point chain
    ``[seg0.a, seg0.b, seg1.b, ...]``, requiring every ``segments[i].b == segments[i+1].a`` EXACTLY (after
    finite-float ``-0.0`` normalization ONLY — Fix-wave F1: no proximity epsilon; a gap as small as 5e-7 is
    ``BACKBONE_DISCONTINUOUS``, never silently welded). Returns ``(points, None)`` on success or
    ``(None, refusal)``."""
    segs = list(segments or [])
    if not segs:
        return None, RouteAdoptionRefusal(BACKBONE_EMPTY, "no backbone geometry was verified to adopt a route "
                                          "from — nothing to propose.")
    try:
        pts: List[Tuple[float, float]] = []
        prev_b: Optional[Tuple[float, float]] = None
        for i, seg in enumerate(segs):
            a = _coerce_point(seg["a"])
            b = _coerce_point(seg["b"])
            if i == 0:
                pts.append(a)
            elif not _exact_point_eq(prev_b, a):
                return None, RouteAdoptionRefusal(
                    BACKBONE_DISCONTINUOUS,
                    "the verified backbone is not one contiguous chain (a break between segment %d and %d) — "
                    "refusing rather than bridging a gap that was never drawn." % (i - 1, i))
            pts.append(b)
            prev_b = b
    except (KeyError, TypeError, ValueError, IndexError):
        return None, RouteAdoptionRefusal(BACKBONE_MALFORMED,
                                          "the verified backbone geometry is not well-formed — refusing.")
    return pts, None


def _cumulative_chainage(points: Sequence[Tuple[float, float]]) -> List[float]:
    chain = [0.0]
    for i in range(1, len(points)):
        chain.append(chain[-1] + _dist(points[i - 1], points[i]))
    return chain


@dataclass(frozen=True)
class Projection:
    segment_index: int
    t_clamped: float
    t_unclamped: float
    point: Tuple[float, float]
    distance: float
    chainage: float


def _project_onto_segment(p: Tuple[float, float], a: Tuple[float, float], b: Tuple[float, float]) -> Tuple[float, float, Tuple[float, float]]:
    dx, dy = b[0] - a[0], b[1] - a[1]
    seg_len2 = dx * dx + dy * dy
    if seg_len2 <= 0.0:
        t_un = 0.0
    else:
        t_un = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / seg_len2
    t = max(0.0, min(1.0, t_un))
    proj = (a[0] + t * dx, a[1] + t * dy)
    return t, t_un, proj


def _project_onto_backbone(p: Tuple[float, float], points: Sequence[Tuple[float, float]],
                           chainages: Sequence[float]) -> List[Projection]:
    """Every candidate projection (one per segment) with minimum distance; ties within ``_TIE_EPS`` (float-repr
    noise ONLY — see the module-level comment) are ALL returned (the caller decides shared-vertex-tie-
    acceptable vs distinct-chainage-ambiguous)."""
    n = len(points) - 1
    candidates: List[Projection] = []
    for i in range(n):
        a, b = points[i], points[i + 1]
        t, t_un, proj = _project_onto_segment(p, a, b)
        seg_chainage = chainages[i] + t * (chainages[i + 1] - chainages[i])
        candidates.append(Projection(i, t, t_un, proj, _dist(p, proj), seg_chainage))
    min_dist = min(c.distance for c in candidates)
    return [c for c in candidates if abs(c.distance - min_dist) <= _TIE_EPS]


def _resolve_projection(label: str, p: Tuple[float, float], points: Sequence[Tuple[float, float]],
                        chainages: Sequence[float], reach_tol: float, *, is_start: bool
                        ) -> Tuple[Optional[Projection], Optional[RouteAdoptionRefusal]]:
    ambiguous_code = AMBIGUOUS_START_PROJECTION if is_start else AMBIGUOUS_END_PROJECTION
    outside_code = START_CONTROL_OUTSIDE_TOLERANCE if is_start else END_CONTROL_OUTSIDE_TOLERANCE
    extent_code = START_CONTROL_BEYOND_BACKBONE_EXTENT if is_start else END_CONTROL_BEYOND_BACKBONE_EXTENT

    best = _project_onto_backbone(p, points, chainages)
    if len(best) > 1:
        chainages_seen = {round(c.chainage, 6) for c in best}
        if len(chainages_seen) > 1:
            return None, RouteAdoptionRefusal(
                ambiguous_code, "the marked %s projects equally close to two different points on the verified "
                "backbone — refusing rather than guessing which one is meant." % label)
        # a genuine shared-vertex tie (same chainage): deterministic pick, lowest segment index.
        best = [min(best, key=lambda c: c.segment_index)]
    proj = best[0]

    n = len(points) - 1
    if (proj.segment_index == 0 and proj.t_unclamped < 0.0) or \
       (proj.segment_index == n - 1 and proj.t_unclamped > 1.0):
        return None, RouteAdoptionRefusal(
            extent_code, "the marked %s falls beyond the verified backbone's drawn extent — refusing rather "
            "than extrapolating source geometry that was never drawn." % label)

    # Fix-wave F2: EXACT reach_tol boundary — dist <= reach_tol, NO epsilon. A control at exactly reach_tol
    # succeeds; math.nextafter(reach_tol, +inf) at distance refuses. No slack is granted for float noise here
    # because reach_tol is itself an observer-reported value, not independently re-derived on both sides.
    if proj.distance > reach_tol:
        return None, RouteAdoptionRefusal(
            outside_code, "the marked %s is farther from the verified observer backbone than the source "
            "observer's endpoint tolerance." % label)
    return proj, None


def classify_control_pair(start_proj, end_proj) -> Optional[RouteAdoptionRefusal]:
    """Pure comparison of two already-resolved projections (each exposing ``.segment_index`` / ``.chainage`` —
    accepts a real ``Projection`` or any duck-typed stand-in, so this comparison is directly unit-testable
    without needing to construct geometry that organically produces every case): same-segment, coincident-
    chainage, then reversed-order.

    Fix-wave F4 (blind-verification FAIL): the same-segment refusal applies UNCONDITIONALLY, including a
    backbone with only one segment total. A straight sub-segment of a single straight segment proposes NOTHING
    a human couldn't already draw with the existing honest two-click manual straight line — there is no source
    bend to preserve, so adoption offers no value and must refuse rather than manufacture a redundant
    "source-backed" straight stroke. Checked BEFORE the coincide check (both are degenerate "no route between
    them" cases; same-segment is the more specific/common one and takes precedence). ``CONTROL_ORDER_REVERSED``
    only applies once the two projections are confirmed on distinct segments at distinct chainages.

    Both the same-segment and coincide comparisons are EXACT (Fix-wave F1-F4: no epsilon) — ``segment_index``
    equality is already exact int comparison, and ``chainage`` equality below is bit-for-bit float equality."""
    if start_proj.segment_index == end_proj.segment_index:
        return RouteAdoptionRefusal(
            CONTROLS_ON_SAME_BACKBONE_SEGMENT, "both marked controls project onto the same backbone segment — "
            "a straight sub-segment proposes nothing over the honest manual straight line; there is no "
            "source-backed route between them to propose.")
    if start_proj.chainage == end_proj.chainage:
        return RouteAdoptionRefusal(
            CONTROL_PROJECTIONS_COINCIDE, "both marked controls project to the same point on the verified "
            "backbone — there is no source-backed route between them to propose.")
    if start_proj.chainage > end_proj.chainage:
        return RouteAdoptionRefusal(
            CONTROL_ORDER_REVERSED, "the marked start projects FARTHER along the verified backbone than the "
            "marked end — refusing rather than silently reversing the operator's intent.")
    return None


# ============================================================================================================ #
# End-to-end pure derivation.
# ============================================================================================================ #
def _dedup_consecutive(points: Sequence[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """Remove CONSECUTIVE EXACT duplicates only (Fix-wave F3: ``_exact_point_eq``, no epsilon) — a point that
    merely lies near its neighbor is never collapsed; only a bit-for-bit identical successor is dropped."""
    out: List[Tuple[float, float]] = []
    for p in points:
        if not out or not _exact_point_eq(out[-1], p):
            out.append(p)
    return out


def _polyline_length(points: Sequence[Tuple[float, float]]) -> float:
    return sum(_dist(points[i], points[i + 1]) for i in range(len(points) - 1))


def derive_route_geometry(*, backbone_segments: Sequence[Dict[str, Any]], gap_bridge_status: Optional[str],
                          reach_tol: Any, human_start: Any, human_end: Any
                          ) -> Tuple[Optional[dict], Optional[RouteAdoptionRefusal]]:
    """Pure geometry derivation (Q3): returns ``(geometry, None)`` on success or ``(None, refusal)``.

    ``geometry`` (on success) is a dict with keys ``backbone_points`` (the full ordered chain),
    ``candidate_route_points`` (the clip: start projection + strictly-interior vertices + end projection),
    ``proposed_render_points`` (human start + the clip + human end, consecutive duplicates removed),
    ``start_projection`` / ``end_projection`` (``Projection`` instances), ``warnings`` (tuple)."""
    try:
        human_start_pt = _coerce_point(human_start)
        human_end_pt = _coerce_point(human_end)
    except (ValueError, TypeError, KeyError, IndexError):
        return None, RouteAdoptionRefusal(MALFORMED_CONTROL_POINTS, "the two human control points are not "
                                          "well-formed finite coordinates.")

    points, refusal = backbone_points_from_segments(backbone_segments)
    if refusal is not None:
        return None, refusal

    if gap_bridge_status == "ROUTE_GAPS_BRIDGED":
        return None, RouteAdoptionRefusal(
            BACKBONE_CONTAINS_HYPOTHETICAL_GAP_BRIDGE,
            "the verified backbone includes a hypothesized gap-bridge reconnection, not a continuously drawn "
            "source stroke — refusing to adopt a continuity guess as a route.")

    if not _finite(reach_tol) or float(reach_tol) <= 0:
        return None, RouteAdoptionRefusal(
            SOURCE_TOLERANCE_UNAVAILABLE, "no finite, positive endpoint tolerance was inherited from the route "
            "verifier — refusing rather than inventing one.")
    reach_tol = float(reach_tol)

    chainages = _cumulative_chainage(points)

    start_proj, refusal = _resolve_projection("start", human_start_pt, points, chainages, reach_tol, is_start=True)
    if refusal is not None:
        return None, refusal
    end_proj, refusal = _resolve_projection("end", human_end_pt, points, chainages, reach_tol, is_start=False)
    if refusal is not None:
        return None, refusal

    refusal = classify_control_pair(start_proj, end_proj)
    if refusal is not None:
        return None, refusal

    # Fix-wave F3: chainage strictly-between selection is EXACT (no epsilon buffer) — a vertex whose chainage
    # is bit-for-bit equal to a projection's chainage is the projection point itself (not "interior"); anything
    # strictly between, however close, is a real preserved backbone vertex and is NEVER dropped.
    interior = [points[i] for i in range(len(points))
               if start_proj.chainage < chainages[i] < end_proj.chainage]
    clip = [start_proj.point] + interior + [end_proj.point]
    if _polyline_length(clip) == 0.0:
        return None, RouteAdoptionRefusal(
            ZERO_LENGTH_PROPOSAL, "the source-backed clip between the two projections has zero length — "
            "nothing to propose.")

    # Fix-wave F3 (no silent terminus snap): dedup on EXACT equality only. A nonzero human-click-to-projection
    # delta ALWAYS keeps both points AND emits HUMAN_CONTROL_TO_BACKBONE_CONNECTOR below — the stored terminus
    # is ALWAYS the exact human click, never silently replaced by its projection.
    render_raw = [human_start_pt] + clip + [human_end_pt]
    render = _dedup_consecutive(render_raw)
    if _polyline_length(render) == 0.0:
        return None, RouteAdoptionRefusal(
            ZERO_LENGTH_PROPOSAL, "the proposed render polyline has zero length — nothing to propose.")

    warnings: List[str] = []
    if not _exact_point_eq(human_start_pt, start_proj.point) or not _exact_point_eq(human_end_pt, end_proj.point):
        warnings.append(CONNECTOR_WARNING)

    return {
        "backbone_points": points,
        "candidate_route_points": clip,
        "proposed_render_points": render,
        "start_projection": start_proj,
        "end_projection": end_proj,
        "warnings": tuple(warnings),
    }, None


# ============================================================================================================ #
# Effective row stations (Q2 join step 8) — reimplemented LOCALLY (never imported from render/ or from
# ``contracts.closeout_pdf``/``contracts.reviewed_bore_adapter``) so this pure contract module stays import-free
# of both. Mirrors the SAME raw < normalized < review.corrected_values precedence + alias tolerance those
# modules already use (the repo's established "reimplement locally" convention for this exact merge).
# ============================================================================================================ #
_ROW_STATION_ALIASES = {
    "start_station": ("start_station", "start_sta", "from_station", "sta_start", "start"),
    "end_station": ("end_station", "end_sta", "to_station", "sta_end", "end"),
}


def _row_norm_key(k: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(k).strip().lower()).strip("_")


def _row_effective_merge(row: Dict[str, Any]) -> Dict[str, Any]:
    """The full merged EFFECTIVE row dict by precedence raw < normalized < review.corrected_values (human
    CORRECTED wins last) — every field, not just stations. Keys folded via ``_row_norm_key`` for alias
    matching, mirroring the SAME precedence ``row_effective_stations`` and ``contracts.closeout_pdf`` /
    ``render.station_dots`` already use."""
    merged: Dict[str, Any] = {}
    for layer in (row.get("raw"), row.get("normalized"), (row.get("review") or {}).get("corrected_values")):
        if isinstance(layer, dict):
            for k, v in layer.items():
                merged[_row_norm_key(k)] = v
    return merged


def row_effective_stations(row: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """Effective (start, end) station TEXT for one reviewed extracted_row, by precedence
    raw < normalized < review.corrected_values (human CORRECTED wins last). Either may be ``None`` when the
    row carries no recognizable station column under any of the standard synonyms."""
    merged = _row_effective_merge(row)

    def _pick(aliases: Tuple[str, ...]) -> Optional[str]:
        for a in aliases:
            if a in merged and merged[a] not in (None, ""):
                return merged[a]
        return None

    return _pick(_ROW_STATION_ALIASES["start_station"]), _pick(_ROW_STATION_ALIASES["end_station"])


def row_evidence_hash(row: Dict[str, Any]) -> str:
    """Fix-wave F5 (blind-verification FAIL — trust boundary): a canonical SHA-256 hex digest of the row's
    FULL effective merged values (the SAME raw < normalized < review.corrected_values precedence
    ``row_effective_stations`` uses, but every field — not just stations). Folded into ``span_source`` and
    therefore into BOTH the proposal hash and the candidate-route hash, so changing ANY reviewed/corrected
    value on the row (e.g. a corrected depth, with stations unchanged) between proposal generation and create
    invalidates the proposal — the create-time re-derivation produces a DIFFERENT hash and refuses
    ``ROUTE_ADOPTION_STALE`` rather than silently adopting geometry bound to stale row evidence."""
    return sha256_hex(_row_effective_merge(row))


# ============================================================================================================ #
# Join-level pure checks (Q2) — each returns a refusal or None; the caller (bridge/route) supplies the facts.
# ============================================================================================================ #
def check_row_engine_eligible(eligible: bool) -> Optional[RouteAdoptionRefusal]:
    if eligible:
        return None
    return RouteAdoptionRefusal(ROW_NOT_ENGINE_ELIGIBLE,
                                "the selected row has not passed review + confirmed grouping — it is not "
                                "engine-eligible.")


def check_row_source_upload(row_source_upload_id: Any, rbl_source_upload_id: Any) -> Optional[RouteAdoptionRefusal]:
    if row_source_upload_id == rbl_source_upload_id:
        return None
    return RouteAdoptionRefusal(ROW_SOURCE_UPLOAD_MISMATCH,
                                "the selected row's source upload does not match the reviewed bore-log's "
                                "BORE_LOG source upload.")


def check_row_span_match(row_start_ft: Optional[float], row_end_ft: Optional[float],
                         candidate_start_ft: Optional[float], candidate_end_ft: Optional[float],
                         *, tol_ft: float = 0.01) -> Optional[RouteAdoptionRefusal]:
    if row_start_ft is None or row_end_ft is None or candidate_start_ft is None or candidate_end_ft is None:
        return RouteAdoptionRefusal(ROW_SPAN_MISMATCH,
                                    "the selected row's effective stations could not be parsed against the "
                                    "READY candidate's stations.")
    if abs(row_start_ft - candidate_start_ft) > tol_ft or abs(row_end_ft - candidate_end_ft) > tol_ft:
        return RouteAdoptionRefusal(ROW_SPAN_MISMATCH,
                                    "the selected row's effective start/end stations do not match the READY "
                                    "candidate's source-confirmed span.")
    return None


def check_cross_page(request_page_number: Any, resolved_pdf_page: Any) -> Optional[RouteAdoptionRefusal]:
    if request_page_number == resolved_pdf_page:
        return None
    return RouteAdoptionRefusal(CROSS_PAGE_CANDIDATE,
                                "the requested page does not match the page the readiness spine actually "
                                "verified — refusing rather than transforming or guessing a page.")


def check_single_ready_candidate(ready_count: int) -> Optional[RouteAdoptionRefusal]:
    if ready_count <= 1:
        return None
    return RouteAdoptionRefusal(MULTIPLE_READY_CANDIDATES,
                                "more than one route-ready candidate was verified for this selection — refusing "
                                "rather than guessing which one the operator means.")


def not_ready_refusal(readiness_status: str) -> RouteAdoptionRefusal:
    """The two-level taxonomy (foreman P2): the readiness spine itself is not READY_FOR_REVIEW_REDLINE."""
    return RouteAdoptionRefusal(
        ROUTE_EVIDENCE_NOT_READY, "the source-backed readiness spine is not READY_FOR_REVIEW_REDLINE for this "
        "selection — no defensible route can be proposed yet.", upstream_reason_code=readiness_status)


# ============================================================================================================ #
# Q4 — proposal identity + full hash assembly.
# ============================================================================================================ #
def _projection_dict(proj: Projection) -> dict:
    return {"segment_index": proj.segment_index, "chainage_display_pt": proj.chainage,
            "distance_display_pt": proj.distance}


def build_proposal(*, scope: Dict[str, Any], plan_source: Dict[str, Any], span_source: Dict[str, Any],
                   readiness: Dict[str, Any], reach_tol: float, human_start: Any, human_end: Any,
                   geometry: dict, confirmed_by: Optional[str] = None) -> RouteProposal:
    """Assemble the full proposal contract (Q7 response shape) + BOTH hashes (Q4) from a successful
    ``derive_route_geometry`` result. Pure; no I/O. ``scope`` carries everything the create-time
    re-derivation must reproduce identically (tenant/job/plan/rbl/row/page identity + evidence hash)."""
    human_start_pt = _coerce_point(human_start)
    human_end_pt = _coerce_point(human_end)
    start_proj: Projection = geometry["start_projection"]
    end_proj: Projection = geometry["end_projection"]
    backbone_points = geometry["backbone_points"]
    candidate_route_points = geometry["candidate_route_points"]
    render_points = geometry["proposed_render_points"]
    warnings = geometry["warnings"]

    connectivity = {
        "why_connected": "unique ordered backbone; isolation and main-run discrimination passed",
        "projection_tolerance_display_pt": reach_tol,
        "tolerance_basis": "ROUTE_ISOLATION_REACH_TOL",
        "start_projection": _projection_dict(start_proj),
        "end_projection": _projection_dict(end_proj),
        "start_delta_display_pt": start_proj.distance,
        "end_delta_display_pt": end_proj.distance,
    }

    # candidate_route_hash: the SOURCE geometry only (independent of the human clicks) — detects when the
    # underlying observer backbone/readiness changed, separate from the full proposal (which also binds the
    # exact human controls + render polyline).
    candidate_route_input = {
        "algorithm_version": ALGORITHM_VERSION,
        "plan_source": plan_source, "span_source": span_source, "readiness": readiness,
        "reach_tol": reach_tol, "backbone_points": [_pt_dict(p) for p in backbone_points],
        "candidate_route_points": [_pt_dict(p) for p in candidate_route_points],
    }
    candidate_route_hash_hex = sha256_hex(candidate_route_input)

    proposal_input = {
        "algorithm_version": ALGORITHM_VERSION,
        "scope": scope, "plan_source": plan_source, "span_source": span_source, "readiness": readiness,
        "reach_tol": reach_tol,
        "human_control_points": [_pt_dict(human_start_pt), _pt_dict(human_end_pt)],
        "backbone_points": [_pt_dict(p) for p in backbone_points],
        "start_projection": _projection_dict(start_proj), "end_projection": _projection_dict(end_proj),
        "candidate_route_points": [_pt_dict(p) for p in candidate_route_points],
        "proposed_render_points": [_pt_dict(p) for p in render_points],
        "warnings": list(warnings),
    }
    proposal_hash_hex = sha256_hex(proposal_input)

    # Q7 response ``source`` is plan_source + span_source FLATTENED into one dict; span identity fields keep
    # their Q5 record names EXCEPT source_file/source_page, which are prefixed span_source_file/span_source_page
    # to avoid colliding with a plan-side "source" concept and to match the pinned Q7 response shape exactly.
    flattened_source = dict(plan_source)
    flattened_source["reviewed_bore_log_id"] = span_source.get("reviewed_bore_log_id")
    flattened_source["row_id"] = span_source.get("row_id")
    flattened_source["span_id"] = span_source.get("span_id")
    flattened_source["span_source_file"] = span_source.get("source_file")
    flattened_source["span_source_page"] = span_source.get("source_page")
    flattened_source["geometry_source"] = GEOMETRY_SOURCE

    return RouteProposal(
        proposal_id=_PROPOSAL_ID_PREFIX + proposal_hash_hex[:24],
        proposal_hash=_hash_tag(proposal_hash_hex),
        candidate_route_hash=_hash_tag(candidate_route_hash_hex),
        coordinate_space=COORDINATE_SPACE, geometry_basis=GEOMETRY_BASIS, confirmation_required=True,
        source=flattened_source,
        readiness=dict(readiness),
        human_control_points=(_pt_dict(human_start_pt), _pt_dict(human_end_pt)),
        candidate_route_points=tuple(_pt_dict(p) for p in candidate_route_points),
        proposed_render_points=tuple(_pt_dict(p) for p in render_points),
        connectivity=connectivity, warnings=tuple(warnings),
    )
