"""TrueLine session-state data layer (extracted from ``main.py``, cleanup PR-2).

INVARIANT (load-bearing): ``STATE`` and ``_SESSIONS`` are module-level
singletons that are ONLY mutated in place — ``STATE.clear()`` /
``STATE.update(...)`` / ``STATE[key] = value`` and ``_SESSIONS[sid] = ...`` —
and are NEVER rebound. ``main.py`` and (later) routers bind these names via
``from app.state import STATE, _SESSIONS, ...``; because nothing ever reassigns
them, every importer shares the one live object. Do NOT write ``STATE = {...}``
or ``_SESSIONS = {...}`` anywhere — that forks the alias and silently breaks
session and tenant isolation.

This module imports the standard library ONLY. It MUST NEVER import
``backend.main`` (or ``main``): the dependency direction is strictly
``main -> app.state`` and ``routers -> app.state``.
"""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

# Live, request-scoped session buffer. ``_session_scope`` (which stays in
# ``main.py``) clears and repopulates this dict per request; it is mutated in
# place and never rebound. Moved verbatim from main.py.
STATE: Dict[str, Any] = {
    "route_name": None,
    "route_id": None,
    "route_coords": [],
    "route_length_ft": 0.0,
    "route_catalog": [],
    "map_points": [],
    "committed_rows": [],
    "station_points": [],
    "redline_segments": [],
    "loaded_field_data_files": 0,
    "latest_structured_file": None,
    "station_mapping_mode": None,
    "station_mapping_min_ft": None,
    "station_mapping_max_ft": None,
    "station_mapping_range_ft": None,
    "selected_route_match": None,
    "route_match_candidates": [],
    "verification_summary": {},
    "kmz_reference": {
        "folder_summary": [],
        "line_role_summary": [],
        "point_role_summary": [],
        "line_layers": [],
        "explicit_redline_layers": [],
        "visual_reference": {},
        "line_features": [],
        "polygon_features": [],
        "point_features": [],
    },
    # Phase 1O — topology lineage bridge. Upload-scoped, read-only, diagnostic.
    # Never consumed by renderer, matching, scoring, redline, or billing.
    "kmz_topology_sidecar": None,
    # Phase 1P — redline continuity advisor. Post-redline, read-only, advisory.
    # Never consumed by matcher, scorer, route activation, billing, or closeout.
    "redline_topology_continuity": None,
    # Phase 1Q — node-anchored redline continuity advisor. Post-redline, read-only, advisory.
    # Groups redline segments whose endpoints coincide with KMZ point features (handholes/nodes).
    # Never consumed by matcher, scorer, route activation, billing, or closeout.
    "redline_node_continuity": None,
    # Phase 1S — bore-log redline endpoint validator. Post-redline, read-only, advisory.
    # Classifies each redline endpoint as anchored/near/orphan/no_anchors_in_kmz.
    # Never consumed by matcher, scorer, route activation, geometry, billing, or closeout.
    "redline_endpoint_validation": None,
    # Phase 1T — deterministic endpoint snap recommendations. Post-validator, read-only, advisory.
    # Metadata-only "what-the-snap-would-look-like" for near/orphan endpoints.
    # Never consumed by matcher, scorer, route activation, geometry, billing, or closeout.
    "endpoint_snap_recommendations": None,
    "bug_reports": [],
    "matching_debug": [],
}


def _default_session_state() -> Dict[str, Any]:
    # ─── Private beta session metadata foundation ─────────────────────────────
    # Lightweight metadata for session tracking. Preserves all existing behavior.
    now = datetime.now(timezone.utc).isoformat()
    return {
        "route_name": None,
        "route_id": None,
        "route_coords": [],
        "route_length_ft": 0.0,
        "route_catalog": [],
        "address_points": [],
        "map_points": [],
        "committed_rows": [],
        "station_points": [],
        "redline_segments": [],
        "loaded_field_data_files": 0,
        "latest_structured_file": None,
        "station_mapping_mode": None,
        "station_mapping_min_ft": None,
        "station_mapping_max_ft": None,
        "station_mapping_range_ft": None,
        "selected_route_match": None,
        "route_match_candidates": [],
        "verification_summary": {},
        "kmz_reference": {
            "folder_summary": [],
            "line_role_summary": [],
            "point_role_summary": [],
            "line_layers": [],
            "explicit_redline_layers": [],
            "visual_reference": {},
            "line_features": [],
            "polygon_features": [],
            "point_features": [],
        },
        "kmz_topology_sidecar": None,
        "redline_topology_continuity": None,
        "redline_node_continuity": None,
        "redline_endpoint_validation": None,
        "endpoint_snap_recommendations": None,
        "bug_reports": [],
        "matching_debug": [],
        "engineering_plans": [],
        "engineering_plan_signals": [],
        # KMZ Matching Trust Slice C1 — operator override map; record-only.
        "match_overrides": {},
        "walk_active": False,
        "walk_meta": {},
        "walk_breadcrumbs": [],
        "walk_station_events": [],
        "closeout_lock": {
            "is_locked": False,
            "locked_by": None,
            "locked_at": None,
        },
        "closeout_locked": False,
        "closeout_locked_by": None,
        "closeout_locked_at": None,
        # Private beta session metadata
        "company_id": None,
        "workspace_label": None,
        "created_at": now,
        "updated_at": now,
        # Sprint J tenant ownership
        "tenant_id": None,
        "tenant_bound_at": None,
        # KMZ Matching Trust Slice C1 — operator override map keyed by group_id.
        # Default empty. Slice C1 records overrides only; Slice C2 will apply.
        "match_overrides": {},
    }


_SESSIONS: Dict[str, Dict[str, Any]] = {}
_SESSION_LOCK = threading.RLock()


def _resolve_session_id(value: Any) -> str:
    candidate = str(value or "").strip()
    if candidate:
        return candidate
    return uuid.uuid4().hex
