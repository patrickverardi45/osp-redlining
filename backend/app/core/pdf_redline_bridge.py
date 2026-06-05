"""Read-only PDF↔KMZ bridge CANDIDATE contract — schema + validator + builder.

A ``pdf_redline_bridge_candidate`` is a deterministic, draw-FREE join object that links a
PDF-first redline (page-space evidence) to a Hero/Leaflet map route + KMZ feature by IDENTITY,
never by raw coordinates. It is the closeout/consultant handoff record: "this PDF redline
corresponds to that world route, with this evidence — or it abstains, with a reason."

DESIGN INVARIANTS (enforced by :func:`validate_bridge_candidate`):
  * **Identity join, not coordinate join (D5).** The world side is referenced by ID only
    (``map_candidate_route_id`` / ``kmz_candidate_feature_id``); the candidate NEVER stores
    lat/lon. This sidesteps the confirmed ``kmz_xref`` [lon,lat]-vs-render-payload [lat,lon]
    coordinate-order inversion — a class of bug that can only bite code that carries raw coords.
  * **Abstain-first; a wrong bridge is worse than none (D13).** ``status == "abstain"`` REQUIRES
    a machine-readable ``abstain_reason`` AND forbids any drawn path (``pdf_path_xy`` must be
    empty) — the bridge layer mirrors the redline layer's no-fake-geometry doctrine.
  * **Draw-free.** This object renders nothing. ``pdf_path_xy`` (if present) is PAGE-SPACE
    [x,y] EVIDENCE only — there is no world geometry, no Leaflet segment, no PNG here.

This module is INERT: it is not imported by ``main.py`` and wired to no endpoint. It defines a
contract and is unit-tested in isolation. Pure stdlib; no fitz / engine / network.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

BRIDGE_SCHEMA_VERSION = "pdf-redline-bridge-candidate-1"

# Lifecycle of a candidate. "candidate": a join target was found. "abstain": evidence did not
# uniquely resolve a world route (carry the reason). "blocked": an input/dependency was missing.
STATUSES: Tuple[str, ...] = ("candidate", "abstain", "blocked")

# Keys that must ALWAYS be present (value may be None where noted) so downstream closeout can
# rely on the shape without per-field hasattr guards.
REQUIRED_FIELDS: Tuple[str, ...] = (
    "schema_version", "session_id", "log_id", "pdf_plan_id", "sheet", "page",
    "station_start", "station_end", "structure_start", "structure_end",
    "pdf_path_xy", "evidence_refs", "map_candidate_route_id", "kmz_candidate_feature_id",
    "status", "confidence", "blockers", "abstain_reason", "created_from_flags",
)

# World-coordinate keys that MUST NOT appear — the candidate joins by identity, never by coords.
_FORBIDDEN_WORLD_KEYS: Tuple[str, ...] = (
    "lat", "lon", "latlng", "latlon", "lonlat", "coord", "coords", "geometry",
    "world_xy", "segments", "polyline",
)

# ── canonical identity (the ONE key format shared by the adapter + the builder) ────────────────
# A bridge join is by IDENTITY, never coordinates. Identity normalizes to ``KIND-NUMBER`` (e.g.
# ``AP-120``) so the PDF side ("AP-120", "AP 120") and the KMZ side (ap_map key "120" + kind hint,
# "TermPortHH 120") resolve to the SAME key. Encoding the KIND avoids bare-number collisions
# (an AP-120 and an HH-120 must NOT match).
_KIND_CODES: Dict[str, str] = {"ap": "AP", "hh": "HH", "splice": "SPLICE"}


def parse_identity(value: Any, *, kind_hint: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    """Parse a structure label/id into ``(kind, number)`` from identity TOKENS only.

    Recognizes AP / TermPortHH (-> ``ap``), HANDHOLE / ``HH`` (-> ``hh``), SPLICE (-> ``splice``);
    a bare number adopts ``kind_hint`` (e.g. the ap_map context). Returns ``(kind, None)`` when no
    number is present, ``(None, None)`` for empty input. NEVER inspects coordinates."""
    s = str(value or "").strip().upper()
    if not s:
        return (None, None)
    if "SPLICE" in s:
        kind: Optional[str] = "splice"
    elif "TERMPORT" in s or "TERMINAL PORT" in s or "TPHH" in s:
        kind = "ap"
    elif re.match(r"^AP[\s\-_]*\d", s):
        kind = "ap"
    elif "HANDHOLE" in s or re.search(r"\bHH\b", s):
        kind = "hh"
    else:
        kind = kind_hint
    m = re.search(r"(\d+)", s)
    return (kind, (m.group(1) if m else None))


def canonical_identity_key(value: Any, *, kind_hint: Optional[str] = None) -> Optional[str]:
    """Canonical ``KIND-NUMBER`` identity key (e.g. ``AP-120``), or None when no kind+number
    resolves. Pure string identity — no geometry, no coordinates."""
    kind, number = parse_identity(value, kind_hint=kind_hint)
    if not kind or not number:
        return None
    code = _KIND_CODES.get(kind)
    return ("%s-%s" % (code, number)) if code else None


def make_bridge_candidate(
    *,
    session_id: Optional[str],
    log_id: Optional[str],
    pdf_plan_id: Optional[str] = None,
    sheet: Optional[int] = None,
    page: Optional[int] = None,
    station_start: Optional[str] = None,
    station_end: Optional[str] = None,
    structure_start: Optional[str] = None,
    structure_end: Optional[str] = None,
    pdf_path_xy: Optional[Sequence[Sequence[float]]] = None,
    evidence_refs: Optional[Sequence[str]] = None,
    map_candidate_route_id: Optional[str] = None,
    kmz_candidate_feature_id: Optional[str] = None,
    status: Optional[str] = None,
    confidence: Optional[float] = None,
    blockers: Optional[Sequence[str]] = None,
    abstain_reason: Optional[str] = None,
    created_from_flags: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Assemble a fully-shaped bridge candidate (all REQUIRED_FIELDS present).

    ``status`` is derived when not given: ``blocked`` if there is no session/log/plan identity,
    ``candidate`` when a world join target (route or KMZ feature) is present, else ``abstain``.
    Pure: builds a dict, renders nothing.
    """
    blockers = list(blockers or [])
    has_target = bool(map_candidate_route_id or kmz_candidate_feature_id)
    if status is None:
        if not (session_id and log_id and pdf_plan_id):
            status = "blocked"
        elif has_target:
            status = "candidate"
        else:
            status = "abstain"
            abstain_reason = abstain_reason or "no_world_join_target_resolved"
    return {
        "schema_version": BRIDGE_SCHEMA_VERSION,
        "session_id": session_id,
        "log_id": log_id,
        "pdf_plan_id": pdf_plan_id,
        "sheet": sheet,
        "page": page,
        "station_start": station_start,
        "station_end": station_end,
        "structure_start": structure_start,
        "structure_end": structure_end,
        # PAGE-SPACE evidence only ([x,y] at native DPI); never world coords. Empty on abstain.
        "pdf_path_xy": [list(p) for p in (pdf_path_xy or [])],
        "evidence_refs": list(evidence_refs or []),
        "map_candidate_route_id": map_candidate_route_id,
        "kmz_candidate_feature_id": kmz_candidate_feature_id,
        "status": status,
        "confidence": confidence,
        "blockers": blockers,
        "abstain_reason": abstain_reason,
        "created_from_flags": list(created_from_flags or []),
    }


def validate_bridge_candidate(obj: Any) -> Tuple[bool, List[str]]:
    """Return ``(ok, errors)``. Validates shape, the status enum, abstain-first safety, the
    draw-free / identity-join invariants, and confidence range. Pure; never raises."""
    errors: List[str] = []
    if not isinstance(obj, dict):
        return False, ["candidate is not a dict"]

    for f in REQUIRED_FIELDS:
        if f not in obj:
            errors.append("missing required field: %s" % f)

    if obj.get("schema_version") != BRIDGE_SCHEMA_VERSION:
        errors.append("schema_version must be %r" % BRIDGE_SCHEMA_VERSION)

    status = obj.get("status")
    if status not in STATUSES:
        errors.append("status must be one of %r" % (STATUSES,))

    conf = obj.get("confidence")
    if conf is not None and not (isinstance(conf, (int, float)) and 0.0 <= float(conf) <= 1.0):
        errors.append("confidence must be None or a float in [0,1]")

    for list_field in ("evidence_refs", "blockers", "created_from_flags", "pdf_path_xy"):
        if list_field in obj and not isinstance(obj[list_field], list):
            errors.append("%s must be a list" % list_field)

    # Draw-free / identity-join: no world-coordinate keys may ride along.
    for k in _FORBIDDEN_WORLD_KEYS:
        if k in obj:
            errors.append("forbidden world/geometry key present: %s (bridge joins by identity)" % k)

    path = obj.get("pdf_path_xy") or []
    # Abstain-first: an abstain carries a reason and draws nothing (no fake path).
    if status == "abstain":
        if not obj.get("abstain_reason"):
            errors.append("status 'abstain' requires a non-empty abstain_reason")
        if path:
            errors.append("status 'abstain' must NOT carry a pdf_path_xy (no fake path)")
    # A live candidate must name at least one world join target (route or KMZ feature).
    if status == "candidate" and not (obj.get("map_candidate_route_id") or obj.get("kmz_candidate_feature_id")):
        errors.append("status 'candidate' requires map_candidate_route_id or kmz_candidate_feature_id")

    return (not errors), errors
