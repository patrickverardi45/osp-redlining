
from __future__ import annotations

import hashlib
import io
import json
import logging
import math
import os
import re
import shutil
import sqlite3
import threading
import time
import uuid
import zipfile
import xml.etree.ElementTree as ET
from urllib.parse import quote
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

import boto3
import pandas as pd
from fastapi import APIRouter, Body, Depends, FastAPI, File, Form, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from app.auth import get_current_tenant
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

BASE_DIR = Path(__file__).resolve().parent
BASE_UPLOAD_DIR = os.getenv("OSP_UPLOAD_DIR") or str(BASE_DIR / "uploads")
UPLOADS_DIR = Path(BASE_UPLOAD_DIR)
os.makedirs(UPLOADS_DIR, exist_ok=True)

# ─── Private beta security scaffolding ─────────────────────────────────────
# Environment variables for upcoming authentication and token validation.
# No auth enforcement yet — these are read but not enforced.
TRUELINE_API_TOKEN = os.getenv("TRUELINE_API_TOKEN", "").strip()
TRUELINE_OBS_TOKEN = os.getenv("TRUELINE_OBS_TOKEN", "").strip()
_ALLOWED_ORIGINS_RAW = os.getenv("TRUELINE_ALLOWED_ORIGINS", "").strip()
# Parse CSV list; fallback to ["*"] if not provided or empty.
if _ALLOWED_ORIGINS_RAW:
    TRUELINE_ALLOWED_ORIGINS = [origin.strip() for origin in _ALLOWED_ORIGINS_RAW.split(",") if origin.strip()]
else:
    TRUELINE_ALLOWED_ORIGINS = ["*"]
PROJECT_ROUTE_CONTEXT_DIR = UPLOADS_DIR / "project_route_context"
os.makedirs(PROJECT_ROUTE_CONTEXT_DIR, exist_ok=True)
# ─── Private beta persistence foundation ──────────────────────────────────
# Minimal SQLite persistence for session durability. Preserves all existing
# in-memory behavior; adds disk fallback for session recovery.
SESSION_DB_PATH = UPLOADS_DIR / "session_store.db"
REQUEST_AUDIT_PATH = UPLOADS_DIR / "request_audit.jsonl"

# ─── Private beta request audit foundation ─────────────────────────────────
# Append-only JSONL of lightweight request traces. Failures are non-fatal.

def _init_session_db():
    """Initialize SQLite database and sessions table if not exists."""
    try:
        with sqlite3.connect(SESSION_DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    session_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.commit()
    except Exception as e:
        logging.warning(f"Failed to initialize session DB: {e}")

def _persist_session(session_id: str, session_data: Dict[str, Any]):
    """Persist session snapshot to SQLite. Never blocks operational flow."""
    try:
        session_json = json.dumps(session_data)
        updated_at = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(SESSION_DB_PATH) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO sessions (session_id, session_json, updated_at)
                VALUES (?, ?, ?)
            """, (session_id, session_json, updated_at))
            conn.commit()
    except Exception as e:
        logging.warning(f"Failed to persist session {session_id}: {e}")

def _load_persisted_session(session_id: str) -> Optional[Dict[str, Any]]:
    """Load session from SQLite if available. Returns None on failure."""
    try:
        with sqlite3.connect(SESSION_DB_PATH) as conn:
            cursor = conn.execute("""
                SELECT session_json FROM sessions WHERE session_id = ?
            """, (session_id,))
            row = cursor.fetchone()
            if row:
                return json.loads(row[0])
    except Exception as e:
        logging.warning(f"Failed to load persisted session {session_id}: {e}")
    return None


def _get_session_tenant_id(session_id: str) -> Optional[str]:
    """Read the tenant_id stamp from the persisted session record.
    Returns None if the session is unknown or unbound."""
    sid = str(session_id or "").strip()
    if not sid:
        return None
    record = _load_persisted_session(sid)
    if not isinstance(record, dict):
        return None
    value = record.get("tenant_id")
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


# Initialize DB on module load.
_init_session_db()

# Phase 1D — append-only ingestion ledger (JSONL, read-only API).
INGESTION_LEDGER_PATH = UPLOADS_DIR / "ingestion_ledger.jsonl"
INGESTION_LEDGER_MAX_ROWS = 500

# Phase 1F — append-only match audit (JSONL, read-only API).
MATCH_AUDIT_PATH = UPLOADS_DIR / "match_audit.jsonl"
MATCH_AUDIT_MAX_ROWS = 2000

# Phase 1G — per-group match audit v2 (JSONL, read-only API).
MATCH_AUDIT_GROUPS_PATH = UPLOADS_DIR / "match_audit_groups.jsonl"
MATCH_AUDIT_GROUPS_MAX_ROWS = 5000

# Phase 1H-A — per-group shadow-compare log (JSONL, read-only API).
MATCH_SHADOW_COMPARE_PATH = UPLOADS_DIR / "match_shadow_compare.jsonl"
MATCH_SHADOW_COMPARE_MAX_ROWS = 5000

# Phase 1K — append-only review-label telemetry (JSONL, observability-only).
# Labels are human-review telemetry ONLY.  They never influence matching,
# scoring, rendering, or any operational system.  See LABEL_USAGE_POLICY.md.
REVIEW_LABELS_PATH = UPLOADS_DIR / "review_labels.jsonl"
REVIEW_LABELS_MAX_ROWS = 5000

# Phase 1U — append-only snap-review-event telemetry (JSONL, observability-only).
# Events are operator review decisions ONLY.  They never influence geometry,
# matching, scoring, rendering, billing, or any operational system.
_SNAP_REVIEW_EVENTS_DIR = BASE_DIR / "data" / "operational_logs"
_SNAP_REVIEW_EVENTS_DIR.mkdir(parents=True, exist_ok=True)
SNAP_REVIEW_EVENTS_PATH = _SNAP_REVIEW_EVENTS_DIR / "snap_review_events.jsonl"
SNAP_REVIEW_EVENTS_MAX_ROWS = 5000
_SNAP_REVIEW_VALID_DECISIONS: frozenset = frozenset({"approved", "rejected", "revoked"})

app = FastAPI(title="OSP Redlining Mapping Layer")

# APIRouter security grouping — auth dependency applied at router level in the auth sprint.
# protected_router: all routes that handle tenant data (requires get_current_tenant later).
# localhost_router: debug endpoints already gated by _is_localhost_request (no auth dep).
protected_router = APIRouter(dependencies=[Depends(get_current_tenant)])
localhost_router = APIRouter()
app.include_router(protected_router)
app.include_router(localhost_router)

app.mount("/uploads", StaticFiles(directory=BASE_UPLOAD_DIR), name="uploads")

# ─── Private beta security scaffolding: CORS with env-sourced origin list ───
# Uses TRUELINE_ALLOWED_ORIGINS if provided; defaults to ["*"] for backward compat.
app.add_middleware(
    CORSMiddleware,
    allow_origins=TRUELINE_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Private beta observability protection ──────────────────────────────────
# Lightweight middleware to protect /api/debug and /api/observability routes
# with bearer token validation when TRUELINE_OBS_TOKEN is set. If token env var
# is empty, all protection is bypassed (backward compat, current behavior).
class ObservabilityTokenMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Only enforce token check on observability/debug routes.
        if request.url.path.startswith(("/api/debug", "/api/observability")):
            # Token enforcement is opt-in: if env var is empty, skip validation.
            if TRUELINE_OBS_TOKEN:
                auth_header = request.headers.get("Authorization", "").strip()
                expected_token = f"Bearer {TRUELINE_OBS_TOKEN}"
                if auth_header != expected_token:
                    return JSONResponse(
                        status_code=401,
                        content={"detail": "Invalid or missing observability token"},
                    )
        response = await call_next(request)
        return response

app.add_middleware(ObservabilityTokenMiddleware)

# ─── Private beta request audit middleware ─────────────────────────────────
# Minimal request correlation logging. Appends one JSON object per line to
# `uploads/request_audit.jsonl`. Do NOT log bodies or auth tokens. Failures
# are non-fatal and must not break request handling.
class RequestAuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        request_id = uuid.uuid4().hex
        timestamp = datetime.now(timezone.utc).isoformat()
        session_id = request.query_params.get("session_id")
        status_code = None
        try:
            response = await call_next(request)
            status_code = getattr(response, "status_code", None)
            return response
        finally:
            try:
                duration_ms = int((time.perf_counter() - start) * 1000)
                record = {
                    "timestamp": timestamp,
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "session_id": session_id,
                    "duration_ms": duration_ms,
                    "status_code": status_code,
                }
                try:
                    with open(str(REQUEST_AUDIT_PATH), "a", encoding="utf-8") as _fh:
                        _fh.write(json.dumps(record, separators=(",", ":")) + "\n")
                except Exception:
                    logging.warning("Failed to write request audit record")
            except Exception:
                # Protect request flow from any unexpected error in logging
                pass

app.add_middleware(RequestAuditMiddleware)

KML_NS = {
    "kml": "http://www.opengis.net/kml/2.2",
    "gx": "http://www.google.com/kml/ext/2.2",
}

MAX_BUG_REPORTS = 200

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


def _clear_engineering_plan_storage_for_session(session_id: str) -> None:
    """Remove engineering plan files and index rows for this session only.

    The global index.json holds records for multiple sessions; workspace reset
    must not delete other sessions' evidence on disk.
    """
    sid = str(session_id or "").strip()
    if not sid:
        return
    try:
        session_folder = ENGINEERING_PLAN_ROOT / _safe_filename(sid)
        if session_folder.is_dir():
            shutil.rmtree(session_folder)
        index_data = _load_engineering_plan_index()
        plans = index_data.get("plans")
        if not isinstance(plans, list):
            plans = []
        index_data["plans"] = [
            r for r in plans if str(r.get("session_id") or "").strip() != sid
        ]
        _save_engineering_plan_index(index_data)
    except Exception:
        pass  # non-fatal: workspace state still resets if disk cleanup fails


def _reset_workspace_state() -> None:
    # Clear this session's engineering plan evidence only (see _clear_engineering_plan_storage_for_session).
    _clear_engineering_plan_storage_for_session(str(STATE.get("_session_id_hint") or ""))
    # Clear persisted Nova override decisions for this session.
    _clear_nova_overrides_for_session(STATE.get("_session_id_hint", ""))
    preserved_bug_reports = list(STATE.get("bug_reports", []) or [])
    STATE.clear()
    STATE.update(
        {
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
            "kmz_topology_sidecar": None,
            "redline_topology_continuity": None,
            "redline_node_continuity": None,
            "redline_endpoint_validation": None,
            "endpoint_snap_recommendations": None,
            "bug_reports": preserved_bug_reports,
            "matching_debug": [],
            "engineering_plans": [],
            "engineering_plan_signals": [],
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
        }
    )


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
    }


_SESSIONS: Dict[str, Dict[str, Any]] = {}
_SESSION_LOCK = threading.RLock()


def _resolve_session_id(value: Any) -> str:
    candidate = str(value or "").strip()
    if candidate:
        return candidate
    return uuid.uuid4().hex


def _get_session(session_id: str) -> Dict[str, Any]:
    with _SESSION_LOCK:
        session = _SESSIONS.get(session_id)
        if session is None:
            # Try loading from persistence first.
            session = _load_persisted_session(session_id)
            if session is None:
                session = _default_session_state()
            _SESSIONS[session_id] = session
        return session


class _session_scope:
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id

    def __enter__(self) -> str:
        _SESSION_LOCK.acquire()
        session = _get_session(self.session_id)
        STATE.clear()
        STATE.update(session)
        STATE["_session_id_hint"] = self.session_id
        return self.session_id

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        try:
            # Update metadata before saving.
            STATE["updated_at"] = datetime.now(timezone.utc).isoformat()
            _SESSIONS[self.session_id] = dict(STATE)
            # Persist latest snapshot to disk.
            _persist_session(self.session_id, dict(STATE))
        finally:
            _SESSION_LOCK.release()


CLOSEOUT_LOCKED_MESSAGE = "Closeout is locked"


def _normalize_closeout_lock(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return {"is_locked": False, "locked_by": None, "locked_at": None}
    return {
        "is_locked": bool(raw.get("is_locked")),
        "locked_by": raw.get("locked_by"),
        "locked_at": raw.get("locked_at"),
    }


def _is_closeout_locked() -> bool:
    return bool(_closeout_flat_fields().get("closeout_locked"))


def _closeout_flat_fields() -> Dict[str, Any]:
    lock = _normalize_closeout_lock(STATE.get("closeout_lock"))
    if any(k in STATE for k in ("closeout_locked", "closeout_locked_by", "closeout_locked_at")):
        if "closeout_locked" in STATE:
            lock["is_locked"] = bool(STATE.get("closeout_locked"))
        if "closeout_locked_by" in STATE and STATE.get("closeout_locked_by") is not None:
            lock["locked_by"] = STATE.get("closeout_locked_by")
        if "closeout_locked_at" in STATE and STATE.get("closeout_locked_at") is not None:
            lock["locked_at"] = STATE.get("closeout_locked_at")
    return {
        "closeout_locked": bool(lock.get("is_locked")),
        "closeout_locked_by": lock.get("locked_by"),
        "closeout_locked_at": lock.get("locked_at"),
    }


def _set_closeout_lock_state(is_locked: bool, locked_by: Optional[str], locked_at: Optional[str]) -> Dict[str, Any]:
    lock = {
        "is_locked": bool(is_locked),
        "locked_by": locked_by,
        "locked_at": locked_at,
    }
    STATE["closeout_lock"] = lock
    STATE["closeout_locked"] = bool(is_locked)
    STATE["closeout_locked_by"] = locked_by
    STATE["closeout_locked_at"] = locked_at
    return lock


def _json_closeout_locked_response() -> JSONResponse:
    return JSONResponse(
        status_code=403,
        content={
            "success": False,
            "error": CLOSEOUT_LOCKED_MESSAGE,
            "closeout_lock": _normalize_closeout_lock(STATE.get("closeout_lock")),
            "session_id": str(STATE.get("_session_id_hint") or ""),
            **_closeout_flat_fields(),
        },
    )


CURRENT_PACKET_PRINT_SHEET_INDEX: Dict[str, Dict[str, Any]] = {
    # Calibrated from the detailed engineering sheets in the 07-15-25 Brenham Phase 5 design set.
    # The new Fieldwire report becomes useful starting at its page 24 because that is where the
    # embedded engineering plan pages begin showing street-level route geometry, matchlines, and
    # sheet continuity. We use those plan sheets as the print-to-street truth layer.
    #
    # Route-id calibration against the current KMZ underground-cable lines:
    # route_476 -> E Stone St corridor
    # route_477 -> E Tom Green St corridor
    # route_478 -> E Mansfield St corridor
    # route_479 / route_480 -> Niebuhr St corridor
    # route_475 -> Glenda Blvd corridor
    "1": {"sheet": 1, "streets": ["E STONE ST"], "route_ids": ["route_476"]},
    "2": {"sheet": 2, "streets": ["E STONE ST"], "route_ids": ["route_476"]},
    "3": {"sheet": 3, "streets": ["E STONE ST"], "route_ids": ["route_476"]},
    "4": {"sheet": 4, "streets": ["E STONE ST", "NIEBUHR ST"], "route_ids": ["route_476", "route_479"]},
    "5": {"sheet": 5, "streets": ["NIEBUHR ST"], "route_ids": ["route_479", "route_480"]},
    "6": {"sheet": 6, "streets": ["NIEBUHR ST"], "route_ids": ["route_479", "route_480"]},
    # For the paired 7,15 bore-log context the design truth is the E Stone St corridor.
    "7": {"sheet": 7, "streets": ["E STONE ST"], "route_ids": ["route_476"]},
    "8": {"sheet": 8, "streets": ["E MANSFIELD ST"], "route_ids": ["route_478"]},
    "9": {"sheet": 9, "streets": ["E TOM GREEN ST"], "route_ids": ["route_477"]},
    "10": {"sheet": 10, "streets": ["E TOM GREEN ST"], "route_ids": ["route_477"]},
    "11": {"sheet": 11, "streets": ["E TOM GREEN ST"], "route_ids": ["route_477"]},
    "12": {"sheet": 12, "streets": ["E TOM GREEN ST"], "route_ids": ["route_477"]},
    "13": {"sheet": 13, "streets": ["E TOM GREEN ST", "BRUCE ST"], "route_ids": ["route_477"]},
    "14": {"sheet": 14, "streets": ["E MANSFIELD ST"], "route_ids": ["route_478"]},
    "15": {"sheet": 15, "streets": ["E STONE ST"], "route_ids": ["route_476"]},
    "16": {"sheet": 16, "streets": ["NIEBUHR ST"], "route_ids": ["route_479", "route_480"]},
    "17": {"sheet": 17, "streets": ["NIEBUHR ST"], "route_ids": ["route_479", "route_480"]},
    "18": {"sheet": 18, "streets": ["NIEBUHR ST", "E TOM GREEN ST"], "route_ids": ["route_477", "route_479", "route_480"]},
    "19": {"sheet": 19, "streets": ["NIEBUHR ST"], "route_ids": ["route_479", "route_480"]},
    "20": {"sheet": 20, "streets": ["NIEBUHR ST"], "route_ids": ["route_479", "route_480"]},
    "21": {"sheet": 21, "streets": ["NIEBUHR ST"], "route_ids": ["route_479", "route_480"]},
    "22": {"sheet": 22, "streets": ["NIEBUHR ST", "E TOM GREEN ST"], "route_ids": ["route_477", "route_479", "route_480"]},
    "23": {"sheet": 23, "streets": ["CARLEE DR"], "route_ids": ["route_478"]},
    "24": {"sheet": 24, "streets": ["POST OAK CT"], "route_ids": ["route_478"]},
    "25": {"sheet": 25, "streets": ["GLENDA BLVD"], "route_ids": ["route_475"]},
    "26": {"sheet": 26, "streets": ["GLENDA BLVD"], "route_ids": ["route_475"]},
    "27": {"sheet": 27, "streets": ["GLENDA BLVD"], "route_ids": ["route_475"]},
    "28": {"sheet": 28, "streets": ["GLENDA BLVD"], "route_ids": ["route_475"]},
    "29": {"sheet": 29, "streets": ["GLENDA BLVD"], "route_ids": ["route_475"]},
    "30": {"sheet": 30, "streets": ["E STONE ST"], "route_ids": ["route_476"]},
}

def _print_sheet_hints(print_tokens: Sequence[str]) -> Dict[str, Any]:
    tokens = [str(token).strip() for token in print_tokens if str(token).strip()]
    streets: List[str] = []
    sheet_numbers: List[int] = []
    route_ids: List[str] = []

    for token in tokens:
        entry = CURRENT_PACKET_PRINT_SHEET_INDEX.get(token)
        if not entry:
            continue
        sheet = entry.get("sheet")
        if isinstance(sheet, int) and sheet not in sheet_numbers:
            sheet_numbers.append(sheet)
        for street in entry.get("streets", []) or []:
            if street not in streets:
                streets.append(street)
        for route_id in entry.get("route_ids", []) or []:
            if route_id not in route_ids:
                route_ids.append(route_id)

    return {
        "print_tokens": tokens,
        "sheet_numbers": sheet_numbers,
        "street_hints": streets,
        "allowed_route_ids": route_ids,
    }




def _store_bug_report(report: Dict[str, Any]) -> Dict[str, Any]:
    reports = STATE.setdefault("bug_reports", [])
    fingerprint = str(report.get("fingerprint") or "").strip()
    if fingerprint:
        for existing in reports:
            if str(existing.get("fingerprint") or "").strip() == fingerprint:
                existing["count"] = int(existing.get("count") or 1) + 1
                existing["timestamp"] = report.get("timestamp") or existing.get("timestamp")
                if report.get("details") is not None:
                    existing["details"] = report.get("details")
                if report.get("context") is not None:
                    existing["context"] = report.get("context")
                return existing
    reports.insert(0, dict(report))
    del reports[MAX_BUG_REPORTS:]
    return report

def _ok(**kwargs: Any) -> JSONResponse:
    return JSONResponse({"success": True, **kwargs})


def _err(message: str, status_code: int = 200, **kwargs: Any) -> JSONResponse:
    return JSONResponse({"success": False, "error": message, **kwargs}, status_code=status_code)


def _safe_filename(value: Any) -> str:
    try:
        return str(value or "").strip()
    except Exception:
        return ""


def _haversine_feet(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r_m = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r_m * c * 3.28084


def _route_length_ft(coords: Sequence[Sequence[float]]) -> float:
    total = 0.0
    for i in range(1, len(coords)):
        total += _haversine_feet(
            float(coords[i - 1][0]),
            float(coords[i - 1][1]),
            float(coords[i][0]),
            float(coords[i][1]),
        )
    return total

def _route_bbox(coords: Sequence[Sequence[float]]) -> Optional[Dict[str, float]]:
    if not coords:
        return None
    lats = [float(pt[0]) for pt in coords if len(pt) >= 2]
    lons = [float(pt[1]) for pt in coords if len(pt) >= 2]
    if not lats or not lons:
        return None
    return {
        "min_lat": min(lats),
        "max_lat": max(lats),
        "min_lon": min(lons),
        "max_lon": max(lons),
    }


def _route_centroid(coords: Sequence[Sequence[float]]) -> Optional[Tuple[float, float]]:
    if not coords:
        return None
    pts = [(float(pt[0]), float(pt[1])) for pt in coords if len(pt) >= 2]
    if not pts:
        return None
    lat = sum(pt[0] for pt in pts) / len(pts)
    lon = sum(pt[1] for pt in pts) / len(pts)
    return (lat, lon)


def _bbox_contains_with_buffer(
    outer_bbox: Optional[Dict[str, float]],
    inner_bbox: Optional[Dict[str, float]],
    lat_buffer_deg: float,
    lon_buffer_deg: float,
) -> bool:
    if not outer_bbox or not inner_bbox:
        return True
    return (
        inner_bbox["max_lat"] >= outer_bbox["min_lat"] - lat_buffer_deg
        and inner_bbox["min_lat"] <= outer_bbox["max_lat"] + lat_buffer_deg
        and inner_bbox["max_lon"] >= outer_bbox["min_lon"] - lon_buffer_deg
        and inner_bbox["min_lon"] <= outer_bbox["max_lon"] + lon_buffer_deg
    )



def _build_route_chainage(coords: Sequence[Sequence[float]]) -> List[float]:
    if not coords:
        return []
    chainage = [0.0]
    running = 0.0
    for idx in range(1, len(coords)):
        prev = coords[idx - 1]
        curr = coords[idx]
        if len(prev) < 2 or len(curr) < 2:
            chainage.append(running)
            continue
        running += _haversine_feet(float(prev[0]), float(prev[1]), float(curr[0]), float(curr[1]))
        chainage.append(running)
    return chainage





def _densify_route_coords(coords: Sequence[Sequence[float]], step_ft: float = 60.0) -> List[List[float]]:
    if not coords:
        return []
    cleaned = _dedupe_consecutive(coords)
    if len(cleaned) < 2:
        return [list(cleaned[0])] if cleaned else []

    chainage = _build_route_chainage(cleaned)
    total_ft = float(chainage[-1] or 0.0)
    if total_ft <= 0.0:
        return cleaned

    step = max(15.0, float(step_ft))
    densified: List[List[float]] = [list(cleaned[0])]
    distance_ft = step
    while distance_ft < total_ft - 1e-6:
        interpolated = _interpolate_point_on_route(cleaned, chainage, distance_ft)
        if interpolated:
            point = [float(interpolated["lat"]), float(interpolated["lon"])]
            if abs(densified[-1][0] - point[0]) > 1e-9 or abs(densified[-1][1] - point[1]) > 1e-9:
                densified.append(point)
        distance_ft += step

    end_point = [float(cleaned[-1][0]), float(cleaned[-1][1])]
    if abs(densified[-1][0] - end_point[0]) > 1e-9 or abs(densified[-1][1] - end_point[1]) > 1e-9:
        densified.append(end_point)

    return densified

def _virtual_segment_chunks(chainage: Sequence[float], target_virtual_ft: float = 60.0) -> List[int]:
    if not chainage or len(chainage) < 2:
        return [1]
    chunks: List[int] = []
    for idx in range(1, len(chainage)):
        seg_len = max(0.0, float(chainage[idx]) - float(chainage[idx - 1]))
        chunk_count = max(1, int(math.ceil(seg_len / max(1.0, float(target_virtual_ft)))))
        chunks.append(chunk_count)
    return chunks


def _route_segment_denominator(route_coords: Sequence[Sequence[float]], chainage: Optional[Sequence[float]] = None) -> int:
    active_chainage = list(chainage) if chainage is not None else _build_route_chainage(route_coords)
    chunks = _virtual_segment_chunks(active_chainage)
    return max(1, sum(chunks))


def _virtualize_segment_index(chainage: Sequence[float], actual_segment_index: int, ratio: float) -> Dict[str, Any]:
    chunks = _virtual_segment_chunks(chainage)
    if not chunks:
        return {
            "virtual_segment_index": 0,
            "virtual_segment_ratio": max(0.0, min(1.0, float(ratio))),
            "virtual_segment_count": 1,
        }

    actual_index = max(0, min(int(actual_segment_index), len(chunks) - 1))
    bounded_ratio = max(0.0, min(1.0, float(ratio)))
    chunk_count = max(1, int(chunks[actual_index]))
    chunk_position = min(chunk_count - 1, int(math.floor(bounded_ratio * chunk_count)))
    local_start = chunk_position / chunk_count
    local_ratio_span = 1.0 / chunk_count
    local_ratio = 0.0 if local_ratio_span <= 0.0 else (bounded_ratio - local_start) / local_ratio_span
    local_ratio = max(0.0, min(1.0, local_ratio))
    virtual_index = sum(chunks[:actual_index]) + chunk_position

    return {
        "virtual_segment_index": int(virtual_index),
        "virtual_segment_ratio": float(local_ratio),
        "virtual_segment_count": int(sum(chunks)),
    }


def _interpolate_point_on_route(coords: Sequence[Sequence[float]], chainage: Sequence[float], target_ft: float) -> Optional[Dict[str, Any]]:
    if not coords or not chainage or len(coords) != len(chainage):
        return None
    if len(coords) == 1:
        return {
            "lat": float(coords[0][0]),
            "lon": float(coords[0][1]),
            "segment_index": 0,
            "segment_ratio": 0.0,
            "actual_segment_index": 0,
            "actual_segment_ratio": 0.0,
            "virtual_segment_count": 1,
            "target_ft": round(float(target_ft), 2),
        }

    total_ft = float(chainage[-1] or 0.0)
    target = max(0.0, min(float(target_ft), total_ft))

    for idx in range(1, len(chainage)):
        start_ft = float(chainage[idx - 1])
        end_ft = float(chainage[idx])
        if target <= end_ft or idx == len(chainage) - 1:
            start_pt = coords[idx - 1]
            end_pt = coords[idx]
            span = max(end_ft - start_ft, 1e-9)
            ratio = max(0.0, min(1.0, (target - start_ft) / span))
            lat = float(start_pt[0]) + (float(end_pt[0]) - float(start_pt[0])) * ratio
            lon = float(start_pt[1]) + (float(end_pt[1]) - float(start_pt[1])) * ratio
            virtual_meta = _virtualize_segment_index(chainage, idx - 1, ratio)
            return {
                "lat": lat,
                "lon": lon,
                "segment_index": int(virtual_meta["virtual_segment_index"]),
                "segment_ratio": float(virtual_meta["virtual_segment_ratio"]),
                "actual_segment_index": idx - 1,
                "actual_segment_ratio": ratio,
                "virtual_segment_count": int(virtual_meta["virtual_segment_count"]),
                "target_ft": round(target, 2),
            }

    last = coords[-1]
    last_actual_index = max(0, len(coords) - 2)
    virtual_meta = _virtualize_segment_index(chainage, last_actual_index, 1.0)
    return {
        "lat": float(last[0]),
        "lon": float(last[1]),
        "segment_index": int(virtual_meta["virtual_segment_index"]),
        "segment_ratio": float(virtual_meta["virtual_segment_ratio"]),
        "actual_segment_index": last_actual_index,
        "actual_segment_ratio": 1.0,
        "virtual_segment_count": int(virtual_meta["virtual_segment_count"]),
        "target_ft": round(target, 2),
    }


def _generate_segment_windows(route_coords: Sequence[Sequence[float]], span_ft: float) -> List[Dict[str, Any]]:
    chainage = _build_route_chainage(route_coords)
    if not chainage:
        return []

    total_ft = float(chainage[-1] or 0.0)
    if total_ft <= 0.0:
        return []

    span = max(1.0, float(span_ft or 0.0))
    if total_ft <= span:
        return [{
            "start_ft": 0.0,
            "end_ft": total_ft,
            "window_type": "full_route_window",
            "chainage": chainage,
        }]

    windows = []
    seen = set()

    def add_window(start_ft: float, end_ft: float, window_type: str) -> None:
        start_val = max(0.0, min(float(start_ft), total_ft))
        end_val = max(start_val, min(float(end_ft), total_ft))
        key = (round(start_val, 2), round(end_val, 2), window_type)
        if key in seen:
            return
        seen.add(key)
        windows.append({
            "start_ft": round(start_val, 2),
            "end_ft": round(end_val, 2),
            "window_type": window_type,
            "chainage": chainage,
        })

    coarse_step = max(10.0, min(40.0, span / 8.0))
    fine_step = max(5.0, min(20.0, span / 16.0))

    current = 0.0
    while current + span <= total_ft + 1e-6:
        add_window(current, current + span, "coarse_window")
        current += coarse_step

    current = 0.0
    while current + span <= total_ft + 1e-6:
        add_window(current, current + span, "fine_window")
        current += fine_step

    add_window(0.0, span, "origin_window")
    add_window(max(0.0, total_ft - span), total_ft, "tail_window")
    add_window(max(0.0, (total_ft - span) / 2.0), min(total_ft, (total_ft - span) / 2.0 + span), "mid_window")

    for vertex_ft in chainage:
        add_window(vertex_ft, vertex_ft + span, "vertex_forward")
        add_window(vertex_ft - span, vertex_ft, "vertex_backward")

    return windows


def _score_segment_window(
    route_coords: Sequence[Sequence[float]],
    normalized_group: Dict[str, Any],
    window: Dict[str, Any],
) -> Dict[str, Any]:
    chainage = window.get("chainage") or _build_route_chainage(route_coords)
    if not chainage:
        return {
            "window_score": 0.0,
            "window_reasons": ["no_chainage"],
            "window_profile": {"projected_points": []},
            "mapping": _resolve_station_mapping(normalized_group.get("station_rows") or [], 0.0),
        }

    start_ft = float(window.get("start_ft") or 0.0)
    end_ft = float(window.get("end_ft") or start_ft)
    span_ft = max(1.0, float(normalized_group.get("span_ft") or 0.0))
    segment_length_ft = max(0.0, end_ft - start_ft)

    mapping = _resolve_station_mapping(normalized_group.get("station_rows") or [], float(chainage[-1]))
    mapping["anchor_offset_ft"] = round(start_ft, 2)
    mapping["anchored_start_ft"] = round(start_ft, 2)
    mapping["anchored_end_ft"] = round(end_ft, 2)
    mapping["anchor_strategy"] = "true_sliding_window_segment_scorer"

    projected_points = []
    covered_segments = []
    min_station = float(normalized_group.get("min_station_ft") or 0.0)

    for row in normalized_group.get("station_rows") or []:
        station_ft = float(row.get("station_ft") or 0.0)
        relative_ft = max(0.0, station_ft - min_station)
        route_ft = start_ft + relative_ft
        projected = _interpolate_point_on_route(route_coords, chainage, route_ft)
        if not projected:
            continue
        covered_segments.append(int(projected["segment_index"]))
        projected_points.append({
            "station_ft": round(station_ft, 2),
            "route_ft": round(route_ft, 2),
            "lat": round(float(projected["lat"]), 8),
            "lon": round(float(projected["lon"]), 8),
            "segment_index": int(projected["segment_index"]),
            "segment_ratio": round(float(projected["segment_ratio"]), 4),
            "actual_segment_index": int(projected.get("actual_segment_index", projected["segment_index"])),
            "actual_segment_ratio": round(float(projected.get("actual_segment_ratio", projected["segment_ratio"])), 4),
            "virtual_segment_count": int(projected.get("virtual_segment_count", 1)),
        })

    exact_span_fit = max(0.0, 1.0 - (abs(segment_length_ft - span_ft) / max(span_ft, 1.0)))
    segment_diversity = min(1.0, len(set(covered_segments)) / max(1, _route_segment_denominator(route_coords, chainage)))
    edge_clearance = min(start_ft, max(0.0, float(chainage[-1]) - end_ft)) / max(span_ft, 1.0)
    edge_fit = min(1.0, edge_clearance)

    shape_bonus = 0.08 if len(route_coords) >= 4 else 0.0

    window_score = exact_span_fit * 0.6 + segment_diversity * 0.2 + edge_fit * 0.12 + shape_bonus
    window_score = max(0.0, min(1.0, window_score))

    mapping["anchor_basis"] = {
        "window_type": window.get("window_type"),
        "window_start_ft": round(start_ft, 2),
        "window_end_ft": round(end_ft, 2),
        "segment_length_ft": round(segment_length_ft, 2),
        "exact_span_fit": round(exact_span_fit, 6),
        "segment_diversity": round(segment_diversity, 6),
        "edge_fit": round(edge_fit, 6),
    }

    return {
        "window_score": round(window_score, 6),
        "window_reasons": [
            f"segment_length_ft={round(segment_length_ft, 2)} vs span_ft={round(span_ft, 2)}",
            f"exact_span_fit={round(exact_span_fit, 4)}",
            f"segment_diversity={round(segment_diversity, 4)}",
            f"edge_fit={round(edge_fit, 4)}",
        ],
        "window_profile": {
            "window_type": window.get("window_type"),
            "start_ft": round(start_ft, 2),
            "end_ft": round(end_ft, 2),
            "segment_length_ft": round(segment_length_ft, 2),
            "projected_points": projected_points[:25],
            "unique_segments_covered": len(set(covered_segments)),
            "score_components": {
                "exact_span_fit": round(exact_span_fit, 6),
                "segment_diversity": round(segment_diversity, 6),
                "edge_fit": round(edge_fit, 6),
                "shape_bonus": round(shape_bonus, 6),
            },
        },
        "mapping": mapping,
    }


def _infer_group_spatial_context(normalized_group: Dict[str, Any]) -> Dict[str, Any]:
    inferred_points: List[Tuple[float, float]] = []

    for row in normalized_group.get("rows") or []:
        lat = row.get("lat")
        lon = row.get("lon")
        if lat is None or lon is None:
            continue
        try:
            inferred_points.append((float(lat), float(lon)))
        except Exception:
            continue

    if not inferred_points:
        return {
            "has_spatial_context": False,
            "point_count": 0,
            "bbox": None,
            "centroid": None,
            "lat_buffer_deg": 0.0,
            "lon_buffer_deg": 0.0,
        }

    lats = [pt[0] for pt in inferred_points]
    lons = [pt[1] for pt in inferred_points]
    bbox = {
        "min_lat": min(lats),
        "max_lat": max(lats),
        "min_lon": min(lons),
        "max_lon": max(lons),
    }
    centroid = (sum(lats) / len(lats), sum(lons) / len(lons))

    lat_span = max(0.0, bbox["max_lat"] - bbox["min_lat"])
    lon_span = max(0.0, bbox["max_lon"] - bbox["min_lon"])

    # About 150 ft minimum buffer, plus some extra slack for sparse field capture.
    lat_buffer_deg = max(0.00042, lat_span * 0.75)
    lon_buffer_deg = max(0.00052, lon_span * 0.75)

    return {
        "has_spatial_context": True,
        "point_count": len(inferred_points),
        "bbox": bbox,
        "centroid": centroid,
        "lat_buffer_deg": lat_buffer_deg,
        "lon_buffer_deg": lon_buffer_deg,
    }



def _normalize_station_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip().upper()
    if not text:
        return None
    if "+" in text:
        left, right = text.split("+", 1)
        left = "".join(ch for ch in left if ch.isdigit())
        right = "".join(ch for ch in right if ch.isdigit())
        if not left or not right:
            return None
        return f"{int(left)}+{int(right):02d}"
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        return None
    # Numeric zero (0, 0.0, "0", "00", "0.0", etc.) is the start station
    # 0+00. Without this guard the < 3-digit rule below drops it and the
    # bore-log start row never enters the system.
    if int(digits) == 0:
        return "0+00"
    if len(digits) < 3:
        return None
    return f"{int(digits[:-2])}+{int(digits[-2:]):02d}"


def _station_to_feet(value: Any) -> Optional[float]:
    normalized = _normalize_station_text(value)
    if not normalized:
        return None
    left, right = normalized.split("+", 1)
    return float(int(left) * 100 + int(right))


def _parse_coordinate_text(text: str) -> List[List[float]]:
    coords: List[List[float]] = []
    for raw in (text or "").strip().split():
        parts = raw.split(",")
        if len(parts) < 2:
            continue
        try:
            lon = float(parts[0])
            lat = float(parts[1])
        except Exception:
            continue
        coords.append([lat, lon])
    return coords


def _extract_kml_bytes(file_bytes: bytes, filename: str) -> bytes:
    lower = _safe_filename(filename).lower()
    if lower.endswith(".kml"):
        return file_bytes
    if lower.endswith(".kmz"):
        with zipfile.ZipFile(io.BytesIO(file_bytes), "r") as zf:
            kml_names = [name for name in zf.namelist() if name.lower().endswith(".kml")]
            if not kml_names:
                raise ValueError("No KML file found inside KMZ.")
            preferred = next((name for name in kml_names if name.lower().endswith("doc.kml")), kml_names[0])
            return zf.read(preferred)
    raise ValueError("Design upload must be .kmz or .kml")


def _dedupe_consecutive(coords: Sequence[Sequence[float]]) -> List[List[float]]:
    cleaned: List[List[float]] = []
    for pt in coords:
        lat = float(pt[0])
        lon = float(pt[1])
        if not cleaned or abs(cleaned[-1][0] - lat) > 1e-9 or abs(cleaned[-1][1] - lon) > 1e-9:
            cleaned.append([lat, lon])
    return cleaned


def _parent_map(root: ET.Element) -> Dict[int, ET.Element]:
    result: Dict[int, ET.Element] = {}
    for elem in root.iter():
        for child in elem:
            result[id(child)] = elem
    return result


def _folder_path(elem: ET.Element, parent_map: Dict[int, ET.Element]) -> List[str]:
    names: List[str] = []
    current = elem
    while id(current) in parent_map:
        current = parent_map[id(current)]
        tag = current.tag.split("}")[-1]
        if tag in {"Folder", "Document"}:
            name = (current.findtext("kml:name", default="", namespaces=KML_NS) or "").strip()
            if name:
                names.append(name)
    names.reverse()
    return names




def _infer_route_role(role_hint: str) -> str:
    role = "other"
    if "backbone" in role_hint:
        role = "backbone"
    elif "terminal" in role_hint and "tail" in role_hint:
        role = "terminal_tail"
    elif "house" in role_hint and "drop" in role_hint:
        role = "house_drop"
    elif "vacant" in role_hint:
        role = "vacant_pipe"
    elif "underground" in role_hint and "cable" in role_hint:
        role = "underground_cable"
    return role


def _polyline_color_for_role(role: str) -> str:
    palette = {
        "underground_cable": "#3b82f6",
        "terminal_tail": "#f59e0b",
        "backbone": "#22c55e",
        "house_drop": "#eab308",
        "vacant_pipe": "#84cc16",
        "other": "#10b981",
    }
    return palette.get(str(role or "other"), "#10b981")


def _polygon_style_for_role(role: str) -> Dict[str, Any]:
    if role == "underground_cable":
        return {"fill": "#22c55e", "fill_opacity": 0.24, "stroke": "#22c55e", "stroke_width": 2}
    if role == "terminal_tail":
        return {"fill": "#f59e0b", "fill_opacity": 0.12, "stroke": "#f59e0b", "stroke_width": 2}
    if role == "backbone":
        return {"fill": "#38bdf8", "fill_opacity": 0.10, "stroke": "#38bdf8", "stroke_width": 2}
    return {"fill": "#22c55e", "fill_opacity": 0.16, "stroke": "#22c55e", "stroke_width": 2}


def _extract_point_coords(text: str) -> Optional[List[float]]:
    coords = _parse_coordinate_text(text or "")
    if not coords:
        return None
    return [float(coords[0][0]), float(coords[0][1])]


def _build_kmz_reference(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    kml_bytes = _extract_kml_bytes(file_bytes, filename)
    root = ET.fromstring(kml_bytes)
    parent_map = _parent_map(root)

    line_features: List[Dict[str, Any]] = []
    polygon_features: List[Dict[str, Any]] = []
    point_features: List[Dict[str, Any]] = []
    folder_summary: Dict[str, int] = {}
    line_role_summary: Dict[str, int] = {}
    point_role_summary: Dict[str, int] = {}

    feature_counter = 0

    for placemark in root.findall(".//kml:Placemark", KML_NS):
        placemark_name = (placemark.findtext("kml:name", default="", namespaces=KML_NS) or "").strip() or "Unnamed Feature"
        folder_names = _folder_path(placemark, parent_map)
        folder_path = " / ".join(folder_names[1:]) if len(folder_names) > 1 else (folder_names[0] if folder_names else "")
        role_hint = f"{folder_path} {placemark_name}".strip().lower()
        role = _infer_route_role(role_hint)

        folder_summary[folder_path or "root"] = folder_summary.get(folder_path or "root", 0) + 1

        line_nodes = placemark.findall(".//kml:LineString/kml:coordinates", KML_NS)
        for node in line_nodes:
            coords = _dedupe_consecutive(_parse_coordinate_text(node.text or ""))
            if len(coords) < 2:
                continue
            feature_counter += 1
            line_features.append(
                {
                    "feature_id": f"line_{feature_counter}",
                    "name": placemark_name,
                    "folder_path": folder_path,
                    "role": role,
                    "coords": coords,
                    "stroke": _polyline_color_for_role(role),
                    "stroke_width": 4 if role == "underground_cable" else 3,
                    "length_ft": round(_route_length_ft(coords), 2),
                }
            )
            line_role_summary[role] = line_role_summary.get(role, 0) + 1

        polygon_nodes = placemark.findall(".//kml:Polygon", KML_NS)
        for poly in polygon_nodes:
            outer = poly.find(".//kml:outerBoundaryIs/kml:LinearRing/kml:coordinates", KML_NS)
            if outer is None:
                continue
            coords = _dedupe_consecutive(_parse_coordinate_text(outer.text or ""))
            if len(coords) < 3:
                continue
            feature_counter += 1
            style = _polygon_style_for_role(role)
            polygon_features.append(
                {
                    "feature_id": f"polygon_{feature_counter}",
                    "name": placemark_name,
                    "folder_path": folder_path,
                    "role": role,
                    "coords": coords,
                    **style,
                }
            )

        point_nodes = placemark.findall(".//kml:Point/kml:coordinates", KML_NS)
        for point_node in point_nodes:
            point = _extract_point_coords(point_node.text or "")
            if not point:
                continue
            feature_counter += 1
            point_features.append(
                {
                    "feature_id": f"point_{feature_counter}",
                    "name": placemark_name,
                    "folder_path": folder_path,
                    "role": role,
                    "lat": point[0],
                    "lon": point[1],
                }
            )
            point_role_summary[role] = point_role_summary.get(role, 0) + 1

    line_layers = [
        {
            "layer_id": f"role::{role}",
            "label": role.replace("_", " ").title(),
            "role": role,
            "feature_count": count,
            "stroke": _polyline_color_for_role(role),
        }
        for role, count in sorted(line_role_summary.items(), key=lambda item: (-item[1], item[0]))
    ]

    visual_reference = {
        "design_bbox_hint": {},
        "has_polygons": bool(polygon_features),
        "has_lines": bool(line_features),
        "line_feature_count": len(line_features),
        "polygon_feature_count": len(polygon_features),
        "point_feature_count": len(point_features),
    }

    return {
        "folder_summary": [
            {"folder_path": folder, "feature_count": count}
            for folder, count in sorted(folder_summary.items(), key=lambda item: (-item[1], item[0]))
        ],
        "line_role_summary": [
            {"role": role, "feature_count": count}
            for role, count in sorted(line_role_summary.items(), key=lambda item: (-item[1], item[0]))
        ],
        "point_role_summary": [
            {"role": role, "feature_count": count}
            for role, count in sorted(point_role_summary.items(), key=lambda item: (-item[1], item[0]))
        ],
        "line_layers": line_layers,
        "explicit_redline_layers": [],
        "visual_reference": visual_reference,
        "line_features": line_features,
        "polygon_features": polygon_features,
        "point_features": point_features,
    }

# ---------------------------------------------------------------------------
# Phase 1A — KMZ semantic feature layer (ADDITIVE)
#
# This module is a parallel pass over the KML/KMZ. It does NOT modify the
# outputs produced by _build_kmz_reference or _build_route_catalog. Its sole
# purpose is to preserve the engineering intelligence that Google Earth/KML
# files carry and that the existing route-extraction path discards: raw
# placemark names, descriptions, folder hierarchy, geometry kind, styleUrl,
# and ExtendedData. A lightweight heuristic classifier emits a soft label
# ("classification" + "confidence" + "classification_reason") so downstream
# UIs can prefer or filter without the parser ever claiming absolute truth.
#
# Architectural rule observed: rendering is NOT the source of truth. The
# parser produces semantic features; consumers may use them or ignore them.
# Failure of this module never breaks upload, route extraction, or rendering
# — _build_kmz_semantic returns None on any error and the caller no-ops.
# ---------------------------------------------------------------------------

# Hard cap to defend against pathological KMLs. Files larger than this are
# parsed up to the cap; the index records the truncation.
_KMZ_SEMANTIC_FEATURE_CAP = 50000
# Bounded anchor catalog (Phase 1B+). Same defence-in-depth pattern as the
# feature cap; the full features[] is the source of truth.
_KMZ_SEMANTIC_ANCHOR_CAP = 5000
# Per-classification sample cap (Phase 1B diagnostics). Bounded so the index
# stays small regardless of the underlying feature count.
_KMZ_SEMANTIC_SAMPLE_CAP = 5
# Top-N cap for folder + styleUrl popularity lists in the index.
_KMZ_SEMANTIC_TOP_N = 10

_KMZ_SEMANTIC_HTML_RE = re.compile(r"<[^>]+>")
_KMZ_SEMANTIC_WS_RE = re.compile(r"\s+")
_KMZ_SEMANTIC_STATION_RE = re.compile(r"\b\d{1,5}\+\d{1,3}\b")
_KMZ_SEMANTIC_HANDHOLE_RE = re.compile(r"(?<![A-Za-z])(HH|MH)\s*[-_#:]?\s*\d", re.IGNORECASE)
_KMZ_SEMANTIC_REEL_RE = re.compile(r"\b(reel|R\d{2,})\b", re.IGNORECASE)


def _kmz_semantic_clean_text(value: Any) -> str:
    """Strip HTML tags from a KML description and collapse whitespace.

    KML descriptions frequently embed HTML (Google Earth balloons). We keep
    the text content for downstream display but never try to faithfully
    render the HTML — UI layers may decide to render the raw description
    instead by reading description_raw if needed.
    """
    if value is None:
        return ""
    text = str(value)
    if not text:
        return ""
    text = _KMZ_SEMANTIC_HTML_RE.sub(" ", text)
    text = _KMZ_SEMANTIC_WS_RE.sub(" ", text).strip()
    return text


def _kmz_semantic_extended_data(placemark: ET.Element) -> Dict[str, str]:
    """Read <ExtendedData><Data name="X"><value>Y</value></Data></ExtendedData>
    plus <SchemaData><SimpleData name="X">Y</SimpleData></SchemaData>.

    Returns a flat dict of string keys to string values. Duplicate keys are
    overwritten by the last occurrence (KML rarely repeats Data names within
    a Placemark, and consumers should treat this as a best-effort map).
    """
    out: Dict[str, str] = {}
    ext = placemark.find("kml:ExtendedData", KML_NS)
    if ext is None:
        return out
    for data in ext.findall("kml:Data", KML_NS):
        name = (data.get("name") or "").strip()
        if not name:
            continue
        value_node = data.find("kml:value", KML_NS)
        value = (value_node.text or "").strip() if value_node is not None else ""
        out[name] = value
    for schema in ext.findall("kml:SchemaData", KML_NS):
        for simple in schema.findall("kml:SimpleData", KML_NS):
            name = (simple.get("name") or "").strip()
            if not name:
                continue
            out[name] = (simple.text or "").strip()
    return out


def _kmz_semantic_geometry_type(placemark: ET.Element) -> str:
    """Classify a placemark's geometry by inspecting its child geometry tags.

    Returns one of: 'Point', 'LineString', 'Polygon', 'MultiGeometry',
    'Other'. MultiGeometry takes precedence when multiple geometry kinds
    coexist inside a single Placemark.
    """
    if placemark.find("kml:MultiGeometry", KML_NS) is not None:
        return "MultiGeometry"
    if placemark.find(".//kml:LineString", KML_NS) is not None:
        return "LineString"
    if placemark.find(".//kml:Polygon", KML_NS) is not None:
        return "Polygon"
    if placemark.find(".//kml:Point", KML_NS) is not None:
        return "Point"
    return "Other"


def _kmz_semantic_first_coord(placemark: ET.Element) -> Optional[List[float]]:
    """Best-effort representative [lat, lon] for indexing without duplicating
    the full geometry. Prefers Point coords, then the first vertex of any
    LineString or Polygon outer ring."""
    point_node = placemark.find(".//kml:Point/kml:coordinates", KML_NS)
    if point_node is not None and point_node.text:
        coord = _extract_point_coords(point_node.text)
        if coord:
            return coord
    line_node = placemark.find(".//kml:LineString/kml:coordinates", KML_NS)
    if line_node is not None and line_node.text:
        coords = _parse_coordinate_text(line_node.text)
        if coords:
            return coords[0]
    poly_node = placemark.find(
        ".//kml:Polygon/kml:outerBoundaryIs/kml:LinearRing/kml:coordinates",
        KML_NS,
    )
    if poly_node is not None and poly_node.text:
        coords = _parse_coordinate_text(poly_node.text)
        if coords:
            return coords[0]
    return None


def _kmz_semantic_classify(
    name: str,
    description_clean: str,
    folder_path_str: str,
    geometry_type: str,
    style_url: str,
    extended_data: Dict[str, str],
) -> Tuple[str, str, str, Dict[str, Any]]:
    """Heuristic classifier. Returns (classification, confidence, reason, classification_debug).

    Confidence levels:
      - "high"   regex match on a structured token (HH-12, station 17+50, R204)
      - "medium" folder name or ExtendedData key signal
      - "low"    loose substring word fragment

    The classifier never overrides the upstream `role` field; both layers
    coexist on different feature populations.

    classification_debug is additive read-only metadata exposing which signals
    fired. It never influences the classification result.
    """
    name_l = (name or "").lower()
    folder_l = (folder_path_str or "").lower()
    style_l = (style_url or "").lower()
    desc_l = (description_clean or "").lower()
    ext_keys_l = {k.lower(): v for k, v in (extended_data or {}).items()}

    # Highest-confidence: regex hits on structured engineering tokens.
    _mn = _KMZ_SEMANTIC_HANDHOLE_RE.search(name)
    _md = _KMZ_SEMANTIC_HANDHOLE_RE.search(description_clean)
    if _mn or _md:
        _by, _toks, _srcs = [], [], []
        if _mn:
            _by.append("name_regex"); _toks.append(_mn.group(0)); _srcs.append("placemark_name")
        if _md:
            _by.append("description_regex"); _toks.append(_md.group(0)); _srcs.append("placemark_description")
        return ("handhole", "high", "name/description matches HH/MH structured token",
                {"matched_by": _by, "matched_tokens": _toks, "heuristic_sources": _srcs})
    _mn = _KMZ_SEMANTIC_STATION_RE.search(name)
    _md = _KMZ_SEMANTIC_STATION_RE.search(description_clean)
    if _mn or _md:
        _by, _toks, _srcs = [], [], []
        if _mn:
            _by.append("name_regex"); _toks.append(_mn.group(0)); _srcs.append("placemark_name")
        if _md:
            _by.append("description_regex"); _toks.append(_md.group(0)); _srcs.append("placemark_description")
        return ("station_label", "high", "name/description matches NN+NN chainage token",
                {"matched_by": _by, "matched_tokens": _toks, "heuristic_sources": _srcs})
    _mn = _KMZ_SEMANTIC_REEL_RE.search(name)
    _md = _KMZ_SEMANTIC_REEL_RE.search(description_clean)
    if _mn or _md:
        _by, _toks, _srcs = [], [], []
        if _mn:
            _by.append("name_regex"); _toks.append(_mn.group(0)); _srcs.append("placemark_name")
        if _md:
            _by.append("description_regex"); _toks.append(_md.group(0)); _srcs.append("placemark_description")
        return ("reel", "high", "name/description matches reel/Rxxx token",
                {"matched_by": _by, "matched_tokens": _toks, "heuristic_sources": _srcs})

    # ExtendedData key signal (medium confidence — schemas vary by vendor).
    for key in ext_keys_l:
        _dbg: Dict[str, Any] = {"matched_by": ["extended_data_key"], "matched_tokens": [key], "heuristic_sources": ["extended_data"]}
        if "handhole" in key or key == "hh":
            return ("handhole", "medium", f"ExtendedData key '{key}'", _dbg)
        if "station" in key:
            return ("station_label", "medium", f"ExtendedData key '{key}'", _dbg)
        if "reel" in key:
            return ("reel", "medium", f"ExtendedData key '{key}'", _dbg)
        if "splice" in key or "vault" in key or "pole" in key or "pedestal" in key or "cabinet" in key:
            return ("structure_marker", "medium", f"ExtendedData key '{key}'", _dbg)

    # Structure markers via name/folder substring on point features.
    structure_tokens = ("splice", "vault", "pedestal", "cabinet", "node", "pole", "tower")
    if geometry_type == "Point":
        for tok in structure_tokens:
            _by, _srcs = ["geometry_type"], ["geometry_type"]
            if tok in name_l:
                _by.append("name_contains"); _srcs.append("placemark_name")
            if tok in folder_l:
                _by.append("folder_hint"); _srcs.append("folder_path")
            if tok in style_l:
                _by.append("style_url_hint"); _srcs.append("style_url")
            if len(_by) > 1:  # at least one non-geometry signal matched
                return ("structure_marker", "medium", f"name/folder/style mentions '{tok}'",
                        {"matched_by": _by, "matched_tokens": [tok], "heuristic_sources": _srcs})

    # Geometry-type defaults.
    if geometry_type == "LineString":
        for tok in ("backbone", "feeder", "cable", "route", "lateral", "trunk"):
            _by, _srcs = ["geometry_type"], ["geometry_type"]
            if tok in folder_l:
                _by.append("folder_hint"); _srcs.append("folder_path")
            if tok in name_l:
                _by.append("name_contains"); _srcs.append("placemark_name")
            if len(_by) > 1:
                return ("route_segment", "medium", f"line in folder/name mentions '{tok}'",
                        {"matched_by": _by, "matched_tokens": [tok], "heuristic_sources": _srcs})
        return ("route_segment", "low", "LineString without role keyword",
                {"matched_by": ["geometry_type"], "matched_tokens": ["LineString"], "heuristic_sources": ["geometry_type"]})
    if geometry_type == "Polygon":
        for tok in ("boundary", "service", "easement", "rofw", "rou"):
            _by, _srcs = ["geometry_type"], ["geometry_type"]
            if tok in folder_l:
                _by.append("folder_hint"); _srcs.append("folder_path")
            if tok in name_l:
                _by.append("name_contains"); _srcs.append("placemark_name")
            if len(_by) > 1:
                return ("boundary_polygon", "medium", f"polygon in folder/name mentions '{tok}'",
                        {"matched_by": _by, "matched_tokens": [tok], "heuristic_sources": _srcs})
        return ("boundary_polygon", "low", "Polygon without semantic keyword",
                {"matched_by": ["geometry_type"], "matched_tokens": ["Polygon"], "heuristic_sources": ["geometry_type"]})
    if geometry_type == "Point":
        _srcs = ["geometry_type"]
        if name_l:
            _srcs.append("placemark_name")
        if desc_l:
            _srcs.append("placemark_description")
        if name_l or desc_l:
            return ("annotation", "low", "Point with descriptive text",
                    {"matched_by": ["geometry_type"], "matched_tokens": ["Point"], "heuristic_sources": _srcs})
        return ("unknown", "low", "Point without descriptive text",
                {"matched_by": ["geometry_type"], "matched_tokens": ["Point"], "heuristic_sources": ["geometry_type"]})

    return ("unknown", "low", "no signal matched",
            {"matched_by": [], "matched_tokens": [], "heuristic_sources": []})


# ---------------------------------------------------------------------------
# Phase A — deterministic numeric extraction from placemark text.
# All inputs are placemark name + description; outputs are (value, source).
# Source is one of "name" | "description" | None so the consumer (the future
# redline engine) can audit which field a number came from.
# ---------------------------------------------------------------------------

# Chainage like "STA 17+50", "00+45", "123+25.5". Major chainage in stations,
# minor in feet within the station. Result is feet: 17+50 = 1750.0 ft.
_KMZ_SEMANTIC_CHAINAGE_VALUE_RE = re.compile(
    r"\b(\d{1,5})\s*\+\s*(\d{1,3}(?:\.\d+)?)\b"
)

# Sequence-number patterns. Each regex is tied to a specific classification so
# we never claim a sequence on a placemark that wasn't classified that way.
_KMZ_SEMANTIC_SEQ_RES: Dict[str, List[Tuple[Any, str]]] = {
    "handhole": [
        (re.compile(r"(?<![A-Za-z])HH\s*[-_#:]?\s*(\d{1,5})\b", re.IGNORECASE), "handhole"),
        (re.compile(r"(?<![A-Za-z])MH\s*[-_#:]?\s*(\d{1,5})\b", re.IGNORECASE), "manhole"),
    ],
    "reel": [
        (re.compile(r"\bREEL\s*[-_#:]?\s*(\d{1,5})\b", re.IGNORECASE), "reel"),
        # R<digits> with at least 2 digits to disambiguate from "R 1" (route).
        (re.compile(r"\bR\s*[-_#:]?\s*(\d{2,5})\b"), "reel"),
    ],
    "structure_marker": [
        (re.compile(r"\bSP(?:LICE)?\s*[-_#:]?\s*(\d{1,5})\b", re.IGNORECASE), "structure"),
        (re.compile(r"\b(?:VLT|VAULT)\s*[-_#:]?\s*(\d{1,5})\b", re.IGNORECASE), "structure"),
        (re.compile(r"\b(?:CAB|CABINET)\s*[-_#:]?\s*(\d{1,5})\b", re.IGNORECASE), "structure"),
        (re.compile(r"\b(?:NODE|N)\s*[-_#:]?\s*(\d{2,5})\b"), "structure"),
    ],
}


def _kmz_semantic_extract_chainage(
    name: str, description: str
) -> Tuple[Optional[float], Optional[str]]:
    """Returns (chainage_ft, source) — source is 'name', 'description', or None.

    Deterministic: prefers a hit in name over description; first match within
    each source wins. Never throws on malformed input.
    """
    for source_label, source_text in (("name", name or ""), ("description", description or "")):
        match = _KMZ_SEMANTIC_CHAINAGE_VALUE_RE.search(source_text)
        if not match:
            continue
        try:
            major = int(match.group(1))
            minor = float(match.group(2))
        except (TypeError, ValueError):
            continue
        return (float(major) * 100.0 + minor, source_label)
    return (None, None)


def _kmz_semantic_extract_sequence(
    classification: str, name: str, description: str
) -> Tuple[Optional[int], Optional[str]]:
    """Returns (sequence_number, sequence_kind). Tied to classification: a
    handhole classification only attempts handhole/manhole patterns; a reel
    classification only attempts reel patterns. Prevents claiming sequences
    from unrelated names.
    """
    patterns = _KMZ_SEMANTIC_SEQ_RES.get(classification or "")
    if not patterns:
        return (None, None)
    for source_text in (name or "", description or ""):
        for pattern, kind in patterns:
            match = pattern.search(source_text)
            if not match:
                continue
            try:
                value = int(match.group(1))
            except (TypeError, ValueError):
                continue
            return (value, kind)
    return (None, None)


# ---------------------------------------------------------------------------
# Phase B — full geometry extraction (LineString / Polygon / Point) and
# MultiGeometry child enumeration. Reuses existing _parse_coordinate_text and
# _dedupe_consecutive helpers; never modifies them.
# ---------------------------------------------------------------------------


def _kmz_semantic_extract_full_geometry(
    placemark: ET.Element,
) -> Optional[Dict[str, Any]]:
    """Extract the placemark's full geometry as a structured dict.

    Returns one of:
        {"kind": "LineString", "coords": [[lat,lon], ...]}
        {"kind": "Polygon", "outer": [...], "inner": [[...], ...]}     # inner optional
        {"kind": "Point", "coord": [lat, lon]}
        None — when the placemark is a MultiGeometry or has no usable geometry.

    MultiGeometry is intentionally excluded here; consumers should call
    _kmz_semantic_extract_multigeometry_children for those.
    """
    if placemark.find("kml:MultiGeometry", KML_NS) is not None:
        return None

    line_node = placemark.find(".//kml:LineString/kml:coordinates", KML_NS)
    if line_node is not None and line_node.text:
        coords = _dedupe_consecutive(_parse_coordinate_text(line_node.text))
        if len(coords) >= 2:
            return {"kind": "LineString", "coords": coords}

    poly = placemark.find(".//kml:Polygon", KML_NS)
    if poly is not None:
        outer_node = poly.find(
            ".//kml:outerBoundaryIs/kml:LinearRing/kml:coordinates", KML_NS
        )
        if outer_node is not None and outer_node.text:
            outer = _dedupe_consecutive(_parse_coordinate_text(outer_node.text))
            if len(outer) >= 3:
                inner_rings: List[List[List[float]]] = []
                for inner_node in poly.findall(
                    ".//kml:innerBoundaryIs/kml:LinearRing/kml:coordinates", KML_NS
                ):
                    if inner_node.text:
                        ring = _dedupe_consecutive(_parse_coordinate_text(inner_node.text))
                        if len(ring) >= 3:
                            inner_rings.append(ring)
                result: Dict[str, Any] = {"kind": "Polygon", "outer": outer}
                if inner_rings:
                    result["inner"] = inner_rings
                return result

    point_node = placemark.find(".//kml:Point/kml:coordinates", KML_NS)
    if point_node is not None and point_node.text:
        coord = _extract_point_coords(point_node.text)
        if coord:
            return {"kind": "Point", "coord": coord}

    return None


def _kmz_semantic_extract_multigeometry_children(
    placemark: ET.Element,
) -> List[Dict[str, Any]]:
    """For MultiGeometry placemarks, enumerate direct geometry children.

    Each entry contains:
      - Point:      {"kind": "Point",      "coord_hint": [lat,lon]}
      - LineString: {"kind": "LineString", "coord_hint": [lat,lon], "coords": [[lat,lon],...]}
      - Polygon:    {"kind": "Polygon",    "coord_hint": [lat,lon], "outer": [[lat,lon],...],
                                           "inner": [[[lat,lon],...], ...]}

    Phase 2B additive: LineString now includes full ``coords``; Polygon now
    includes full ``outer`` and ``inner`` rings.  The ``coord_hint`` field is
    preserved unchanged for backwards compatibility with any existing consumer.
    """
    out: List[Dict[str, Any]] = []
    multi = placemark.find("kml:MultiGeometry", KML_NS)
    if multi is None:
        return out

    for child in list(multi):
        tag = child.tag.split("}")[-1] if isinstance(child.tag, str) else ""
        try:
            if tag == "Point":
                coord_node = child.find("kml:coordinates", KML_NS)
                if coord_node is not None and coord_node.text:
                    coord = _extract_point_coords(coord_node.text)
                    if coord:
                        out.append({"kind": "Point", "coord_hint": coord})
            elif tag == "LineString":
                coord_node = child.find("kml:coordinates", KML_NS)
                if coord_node is not None and coord_node.text:
                    coords = _dedupe_consecutive(_parse_coordinate_text(coord_node.text))
                    if coords:
                        entry: Dict[str, Any] = {
                            "kind": "LineString",
                            "coord_hint": coords[0],
                        }
                        if len(coords) >= 2:
                            entry["coords"] = coords
                        out.append(entry)
            elif tag == "Polygon":
                poly_outer_node = child.find(
                    ".//kml:outerBoundaryIs/kml:LinearRing/kml:coordinates", KML_NS
                )
                if poly_outer_node is not None and poly_outer_node.text:
                    outer = _dedupe_consecutive(_parse_coordinate_text(poly_outer_node.text))
                    if outer:
                        poly_entry: Dict[str, Any] = {
                            "kind": "Polygon",
                            "coord_hint": outer[0],
                        }
                        if len(outer) >= 3:
                            poly_entry["outer"] = outer
                            inner_rings: List[List[List[float]]] = []
                            for inner_node in child.findall(
                                ".//kml:innerBoundaryIs/kml:LinearRing/kml:coordinates", KML_NS
                            ):
                                if inner_node.text:
                                    ring = _dedupe_consecutive(_parse_coordinate_text(inner_node.text))
                                    if len(ring) >= 3:
                                        inner_rings.append(ring)
                            if inner_rings:
                                poly_entry["inner"] = inner_rings
                        out.append(poly_entry)
        except Exception:
            # Per-child robustness: malformed inner geometry never aborts.
            continue
    return out


# ---------------------------------------------------------------------------
# Phase C — Style + StyleMap resolution at the document level (one pass per
# upload), and lifecycle hint extraction from folder + name.
# ---------------------------------------------------------------------------


def _kmz_semantic_kml_color_to_hex(value: Any) -> Optional[str]:
    """KML colors are aabbggrr (alpha-blue-green-red, 8 hex chars). Convert
    to standard #rrggbb (alpha dropped). 6-char (rrggbb) input also accepted.
    Returns None for malformed input.
    """
    if value is None:
        return None
    raw = str(value).strip().lower()
    if not raw:
        return None
    if not all(ch in "0123456789abcdef" for ch in raw):
        return None
    if len(raw) == 8:
        rr = raw[6:8]
        gg = raw[4:6]
        bb = raw[2:4]
        return f"#{rr}{gg}{bb}"
    if len(raw) == 6:
        return f"#{raw}"
    return None


def _kmz_semantic_extract_style_props(style_elem: ET.Element) -> Dict[str, Any]:
    """Extract the structured style props we care about for redline-engine
    hints. Missing fields are simply absent in the returned dict.
    """
    props: Dict[str, Any] = {}

    line = style_elem.find("kml:LineStyle", KML_NS)
    if line is not None:
        color_node = line.find("kml:color", KML_NS)
        if color_node is not None and color_node.text:
            color = _kmz_semantic_kml_color_to_hex(color_node.text)
            if color:
                props["line_color"] = color
        width_node = line.find("kml:width", KML_NS)
        if width_node is not None and width_node.text:
            try:
                props["line_width"] = float(width_node.text.strip())
            except (TypeError, ValueError):
                pass

    poly = style_elem.find("kml:PolyStyle", KML_NS)
    if poly is not None:
        color_node = poly.find("kml:color", KML_NS)
        if color_node is not None and color_node.text:
            color = _kmz_semantic_kml_color_to_hex(color_node.text)
            if color:
                props["poly_fill"] = color

    icon = style_elem.find("kml:IconStyle", KML_NS)
    if icon is not None:
        href_node = icon.find(".//kml:Icon/kml:href", KML_NS)
        if href_node is not None and href_node.text:
            href = href_node.text.strip()
            if href:
                props["icon_href"] = href

    label = style_elem.find("kml:LabelStyle", KML_NS)
    if label is not None:
        color_node = label.find("kml:color", KML_NS)
        if color_node is not None and color_node.text:
            color = _kmz_semantic_kml_color_to_hex(color_node.text)
            if color:
                props["label_color"] = color

    return props


def _kmz_semantic_parse_styles(root: ET.Element) -> Dict[str, Dict[str, Any]]:
    """Parse all <Style id="…"> blocks and resolve <StyleMap id="…"> aliases
    by their "normal" key. Returns dict mapping style id (without leading '#')
    to resolved props. Bounded recursion (StyleMap referencing another
    StyleMap is treated as unresolved at depth > 4).

    Deterministic: iterates root in document order, sorts merged keys
    deterministically when outputs are summarized.
    """
    raw_styles: Dict[str, Dict[str, Any]] = {}
    for style in root.findall(".//kml:Style", KML_NS):
        sid = (style.get("id") or "").strip()
        if not sid:
            continue
        try:
            raw_styles[sid] = _kmz_semantic_extract_style_props(style)
        except Exception:
            continue

    # Resolve <StyleMap> aliases by their "normal" pair, capped at depth 4.
    stylemap_target: Dict[str, str] = {}
    for stylemap in root.findall(".//kml:StyleMap", KML_NS):
        sid = (stylemap.get("id") or "").strip()
        if not sid:
            continue
        for pair in stylemap.findall("kml:Pair", KML_NS):
            key_node = pair.find("kml:key", KML_NS)
            if key_node is None or (key_node.text or "").strip() != "normal":
                continue
            url_node = pair.find("kml:styleUrl", KML_NS)
            if url_node is None or not url_node.text:
                continue
            target = url_node.text.strip().lstrip("#")
            if target:
                stylemap_target[sid] = target
            break

    resolved: Dict[str, Dict[str, Any]] = dict(raw_styles)
    for sid, target in stylemap_target.items():
        seen: List[str] = [sid]
        cur = target
        depth = 0
        while cur in stylemap_target and depth < 4:
            if cur in seen:
                cur = ""
                break
            seen.append(cur)
            cur = stylemap_target[cur]
            depth += 1
        if cur and cur in raw_styles:
            resolved[sid] = raw_styles[cur]
    return resolved


def _kmz_semantic_lookup_style(
    style_url: str, resolved_styles: Dict[str, Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """Resolve a placemark's <styleUrl> against the doc-level style table.
    Returns None when no entry exists or the styleUrl is empty."""
    if not style_url:
        return None
    key = style_url.strip()
    if not key:
        return None
    if key.startswith("#"):
        key = key[1:]
    if not key:
        return None
    return resolved_styles.get(key)


# Lifecycle patterns for redline-scope filtering. Order is high-precedence
# first ("asbuilt" beats "as built"-substring of "as-built backbone").
_KMZ_SEMANTIC_LIFECYCLE_PATTERNS: List[Tuple[str, Any]] = [
    ("asbuilt", re.compile(r"\bas[\s\-_]?built\b", re.IGNORECASE)),
    ("decommissioned", re.compile(r"\b(?:decommiss(?:ion(?:ed)?)?|abandoned|removed)\b", re.IGNORECASE)),
    ("proposed", re.compile(r"\bproposed\b", re.IGNORECASE)),
    ("survey", re.compile(r"\bsurvey(?:ed)?\b", re.IGNORECASE)),
    ("existing", re.compile(r"\bexisting\b", re.IGNORECASE)),
]


def _kmz_semantic_extract_lifecycle(
    folder_path_str: str, name: str
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Return (label, confidence, reason) or (None, None, None).

    Confidence:
      - "high"   when an entire folder segment matches the pattern (folder
                 named exactly "As-Built" / "Proposed" / etc.).
      - "medium" when the pattern matches anywhere in the folder path string.
      - "low"    when the pattern only matches in the placemark name.

    Deterministic: patterns iterated in fixed order; first hit wins.
    """
    folder = folder_path_str or ""
    name_s = name or ""

    folder_segments = [seg.strip() for seg in folder.split("/") if seg.strip()]
    for label, pattern in _KMZ_SEMANTIC_LIFECYCLE_PATTERNS:
        for seg in folder_segments:
            if pattern.search(seg) and len(seg) <= len(label) + 6:
                return (label, "high", f"folder segment matches '{label}'")

    for label, pattern in _KMZ_SEMANTIC_LIFECYCLE_PATTERNS:
        if pattern.search(folder):
            return (label, "medium", f"folder path mentions '{label}'")

    for label, pattern in _KMZ_SEMANTIC_LIFECYCLE_PATTERNS:
        if pattern.search(name_s):
            return (label, "low", f"placemark name mentions '{label}'")

    return (None, None, None)


def _build_kmz_semantic(file_bytes: bytes, filename: str) -> Optional[Dict[str, Any]]:
    """Build the semantic_features list and semantic_index summary.

    Never raises. Returns None on any parse error so the caller can store
    None and proceed. Output schema:

        {
          "parser_version": "semantic-1",
          "features": [SemanticFeature, ...],
          "index": {
            "feature_count": int,
            "truncated": bool,
            "by_classification": {label: count},
            "by_geometry_type": {type: count},
            "by_folder": {folder_path_str: count},
            "by_confidence": {confidence: count},
            "style_url_count": {style_url: count},
            "extended_data_keys": [keys...],
          },
        }
    """
    # [KMZ_SEM_TRACE] entry — uses print() so it always reaches the uvicorn
    # console regardless of logging configuration. Remove these prints once
    # the kmz_semantic visibility issue is diagnosed.
    print(
        f"[KMZ_SEM_TRACE] _build_kmz_semantic ENTER filename={filename!r} "
        f"bytes_len={len(file_bytes) if file_bytes else 0}",
        flush=True,
    )
    try:
        kml_bytes = _extract_kml_bytes(file_bytes, filename)
        root = ET.fromstring(kml_bytes)
    except Exception as exc:
        import traceback as _kmz_sem_top_tb

        print(
            f"[KMZ_SEM_TRACE] _build_kmz_semantic EARLY_RETURN=None "
            f"reason=kml_extract_or_parse filename={filename!r} "
            f"exc={type(exc).__name__}: {exc}",
            flush=True,
        )
        _kmz_sem_top_tb.print_exc()
        return None

    try:
        parent_map = _parent_map(root)
    except Exception:
        parent_map = {}

    # Phase C — resolve all <Style> / <StyleMap> blocks once at the top of
    # the document. Bounded by KML schema; per-placemark lookup is O(1).
    try:
        resolved_styles = _kmz_semantic_parse_styles(root)
    except Exception:
        resolved_styles = {}

    features: List[Dict[str, Any]] = []
    by_classification: Dict[str, int] = {}
    by_geometry_type: Dict[str, int] = {}
    by_folder: Dict[str, int] = {}
    by_confidence: Dict[str, int] = {}
    style_url_count: Dict[str, int] = {}
    extended_data_keys: Dict[str, int] = {}
    by_lifecycle: Dict[str, int] = {}
    by_resolved_line_color: Dict[str, int] = {}
    features_with_chainage = 0
    features_with_sequence = 0
    features_with_full_geometry = 0
    features_with_resolved_style = 0
    # Phase 1B diagnostics — bounded sample lists per classification so the
    # index stays small even on huge KMZs. Each list holds up to
    # _KMZ_SEMANTIC_SAMPLE_CAP feature_ids; consumers join back to features[]
    # for full detail.
    classification_samples: Dict[str, List[str]] = {}
    # Phase 1B traceability — emit the source filename so multi-KMZ
    # ingestion later can identify which file each feature came from.
    safe_source_filename = (str(filename or "").strip() or "design.kmz")

    truncated = False
    counter = 0
    skipped_placemark_count = 0
    skipped_placemark_samples: List[Dict[str, Any]] = []
    warnings: List[str] = []
    _MAX_WARNINGS = 200
    _MAX_SKIPPED_SAMPLES = 10

    for placemark in root.findall(".//kml:Placemark", KML_NS):
        counter += 1
        if counter > _KMZ_SEMANTIC_FEATURE_CAP:
            truncated = True
            break
        try:
            placemark_id = (placemark.get("id") or "").strip() or None
            placemark_name = (
                placemark.findtext("kml:name", default="", namespaces=KML_NS) or ""
            ).strip()
            description_raw = placemark.findtext("kml:description", default="", namespaces=KML_NS) or ""
            description_clean = _kmz_semantic_clean_text(description_raw)
            folder_names = _folder_path(placemark, parent_map) if parent_map else []
            folder_path_str = " / ".join(folder_names[1:]) if len(folder_names) > 1 else (folder_names[0] if folder_names else "")
            style_url = (placemark.findtext("kml:styleUrl", default="", namespaces=KML_NS) or "").strip()
            extended_data = _kmz_semantic_extended_data(placemark)
            geometry_type = _kmz_semantic_geometry_type(placemark)
            coords_hint = _kmz_semantic_first_coord(placemark)
            # Derive coordinate_source for classification_debug: mirrors the
            # node-priority order in _kmz_semantic_first_coord without re-parsing.
            _coord_source: Optional[str] = None
            if coords_hint is not None:
                if placemark.find(".//kml:Point/kml:coordinates", KML_NS) is not None:
                    _coord_source = "Point"
                elif placemark.find(".//kml:LineString/kml:coordinates", KML_NS) is not None:
                    _coord_source = "LineString"
                elif placemark.find(".//kml:Polygon/kml:outerBoundaryIs/kml:LinearRing/kml:coordinates", KML_NS) is not None:
                    _coord_source = "Polygon"
            classification, confidence, reason, classification_debug = _kmz_semantic_classify(
                placemark_name,
                description_clean,
                folder_path_str,
                geometry_type,
                style_url,
                extended_data,
            )
            classification_debug["coordinate_source"] = _coord_source
            # Phase A — deterministic numeric extraction.
            chainage_ft, chainage_source = _kmz_semantic_extract_chainage(
                placemark_name, description_clean
            )
            sequence_number, sequence_kind = _kmz_semantic_extract_sequence(
                classification, placemark_name, description_clean
            )
            # Phase B — full geometry + MultiGeometry children.
            full_geometry = _kmz_semantic_extract_full_geometry(placemark)
            multigeometry_children = (
                _kmz_semantic_extract_multigeometry_children(placemark)
                if geometry_type == "MultiGeometry"
                else []
            )
            # Phase C — style resolution + lifecycle hint.
            style_resolved = _kmz_semantic_lookup_style(style_url, resolved_styles)
            lifecycle_label, lifecycle_conf, lifecycle_reason = (
                _kmz_semantic_extract_lifecycle(folder_path_str, placemark_name)
            )
        except Exception as _sem_exc:
            # Per-placemark robustness: skip the offender, never crash the pass.
            skipped_placemark_count += 1
            _error_kind = type(_sem_exc).__name__
            _message = str(_sem_exc)[:200]
            if len(warnings) < _MAX_WARNINGS:
                warnings.append(
                    f"placemark {counter} ({_error_kind}): {_message}"
                )
            if len(skipped_placemark_samples) < _MAX_SKIPPED_SAMPLES:
                skipped_placemark_samples.append(
                    {
                        "placemark_index_in_doc": counter,
                        "error_kind": _error_kind,
                        "message": _message,
                    }
                )
            continue

        feature_id = f"semantic_{counter}"
        feature: Dict[str, Any] = {
            "feature_id": feature_id,
            # Phase 1B — capture <Placemark id="..."> attribute when present.
            # None when the source KML omits the attribute (typical for
            # Google Earth-authored files). Combine with source_filename for
            # cross-file joins.
            "placemark_id": placemark_id,
            "placemark_name": placemark_name,
            "description": description_clean,
            "description_raw": description_raw,
            "folder_path": folder_names,
            "folder_path_str": folder_path_str,
            "geometry_type": geometry_type,
            "style_url": style_url,
            "extended_data": extended_data,
            "coords_hint": coords_hint,
            "classification": classification,
            "confidence": confidence,
            "classification_reason": reason,
            # Phase 1B traceability — which KMZ/KML this feature came from.
            "source_filename": safe_source_filename,
            # Phase A — numeric extractions. None when no token matched.
            "chainage_ft": chainage_ft,
            "chainage_source": chainage_source,
            "sequence_number": sequence_number,
            "sequence_kind": sequence_kind,
            # Phase B — geometry. full_geometry is None for MultiGeometry;
            # multigeometry_children is empty list for non-Multi.
            "full_geometry": full_geometry,
            "multigeometry_children": multigeometry_children,
            # Phase C — style resolution + lifecycle. style_resolved is None
            # when no <Style id> matched. lifecycle is None when no token hit.
            "style_resolved": style_resolved,
            "lifecycle": (
                {
                    "label": lifecycle_label,
                    "confidence": lifecycle_conf,
                    "reason": lifecycle_reason,
                }
                if lifecycle_label
                else None
            ),
            # Additive explainability metadata. Read-only; never affects
            # classification result, scoring, or matching behavior.
            "classification_debug": classification_debug,
        }
        features.append(feature)

        by_classification[classification] = by_classification.get(classification, 0) + 1
        by_geometry_type[geometry_type] = by_geometry_type.get(geometry_type, 0) + 1
        bucket = folder_path_str or "(root)"
        by_folder[bucket] = by_folder.get(bucket, 0) + 1
        by_confidence[confidence] = by_confidence.get(confidence, 0) + 1
        if style_url:
            style_url_count[style_url] = style_url_count.get(style_url, 0) + 1
        for key in extended_data.keys():
            extended_data_keys[key] = extended_data_keys.get(key, 0) + 1
        # Phase 1B — collect bounded per-classification samples for diagnostics.
        sample_list = classification_samples.setdefault(classification, [])
        if len(sample_list) < _KMZ_SEMANTIC_SAMPLE_CAP:
            sample_list.append(feature_id)
        # Phase A/B/C — running counters for the diagnostics panel.
        if chainage_ft is not None:
            features_with_chainage += 1
        if sequence_number is not None:
            features_with_sequence += 1
        if full_geometry is not None:
            features_with_full_geometry += 1
        if style_resolved:
            features_with_resolved_style += 1
            line_color = style_resolved.get("line_color")
            if isinstance(line_color, str) and line_color:
                by_resolved_line_color[line_color] = (
                    by_resolved_line_color.get(line_color, 0) + 1
                )
        if lifecycle_label:
            by_lifecycle[lifecycle_label] = by_lifecycle.get(lifecycle_label, 0) + 1

    # Phase 1B — pre-compute Top-N popularity lists so the frontend
    # diagnostics panel doesn't have to sort big dicts on every render.
    # Sort by count desc, then key asc for deterministic ordering.
    def _top_n_pairs(counts: Dict[str, int], n: int) -> List[Dict[str, Any]]:
        ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        return [{"key": key, "count": count} for key, count in ranked[:n]]

    top_folders_pairs = _top_n_pairs(by_folder, _KMZ_SEMANTIC_TOP_N)
    top_style_urls_pairs = _top_n_pairs(style_url_count, _KMZ_SEMANTIC_TOP_N)
    # Re-shape "key" → friendly field names to match the public contract.
    top_folders = [
        {"folder_path_str": entry["key"], "count": entry["count"]}
        for entry in top_folders_pairs
    ]
    top_style_urls = [
        {"style_url": entry["key"], "count": entry["count"]}
        for entry in top_style_urls_pairs
    ]

    # Phase A/B/C — additional Top-N lists for the diagnostics panel.
    top_lifecycle = [
        {"label": entry["key"], "count": entry["count"]}
        for entry in _top_n_pairs(by_lifecycle, _KMZ_SEMANTIC_TOP_N)
    ]
    top_resolved_line_colors = [
        {"color": entry["key"], "count": entry["count"]}
        for entry in _top_n_pairs(by_resolved_line_color, _KMZ_SEMANTIC_TOP_N)
    ]

    # Phase A/B/C — anchor catalog. Read-only candidate set the future redline
    # engine MAY consume. Today this is purely diagnostic. Sorted
    # deterministically; capped at _KMZ_SEMANTIC_ANCHOR_CAP.
    _ANCHOR_KINDS = {"handhole", "station_label", "reel", "structure_marker"}
    _ACCEPTED_CONFIDENCE = {"high", "medium"}
    anchor_entries: List[Dict[str, Any]] = []
    for feature in features:
        if feature["classification"] not in _ANCHOR_KINDS:
            continue
        if feature["confidence"] not in _ACCEPTED_CONFIDENCE:
            continue
        coord = feature.get("coords_hint")
        if (
            not isinstance(coord, list)
            or len(coord) < 2
            or not isinstance(coord[0], (int, float))
            or not isinstance(coord[1], (int, float))
        ):
            continue
        anchor_entries.append(
            {
                "feature_id": feature["feature_id"],
                "classification": feature["classification"],
                "sequence_number": feature.get("sequence_number"),
                "sequence_kind": feature.get("sequence_kind"),
                "chainage_ft": feature.get("chainage_ft"),
                "coord": [float(coord[0]), float(coord[1])],
                "confidence": feature["confidence"],
                "folder_path_str": feature["folder_path_str"],
                "lifecycle": (feature.get("lifecycle") or {}).get("label"),
            }
        )

    def _anchor_sort_key(entry: Dict[str, Any]) -> Tuple[Any, ...]:
        """Sort anchors deterministically. NaN/inf chainage or invalid sequence
        must not crash sort() (Python raises when comparing NaN to NaN)."""
        seq = entry.get("sequence_number")
        chain = entry.get("chainage_ft")
        seq_i = 10**9
        if isinstance(seq, int) and not isinstance(seq, bool):
            seq_i = seq
        elif isinstance(seq, bool):
            seq_i = int(seq)
        elif isinstance(seq, float):
            if math.isfinite(seq):
                try:
                    seq_i = int(seq)
                except (ValueError, OverflowError):
                    seq_i = 10**9
        chain_sort = float("inf")
        if isinstance(chain, (int, float)) and not isinstance(chain, bool):
            c = float(chain)
            if math.isfinite(c):
                chain_sort = c
        return (
            entry.get("folder_path_str") or "",
            seq_i,
            chain_sort,
            entry.get("feature_id") or "",
        )

    try:
        anchor_entries.sort(key=_anchor_sort_key)
    except (TypeError, ValueError) as exc:
        logging.getLogger(__name__).warning(
            "anchor catalog sort failed (%s); using feature_id fallback order",
            exc,
            exc_info=True,
        )
        anchor_entries.sort(key=lambda e: str(e.get("feature_id") or ""))
    anchor_truncated = len(anchor_entries) > _KMZ_SEMANTIC_ANCHOR_CAP
    if anchor_truncated:
        anchor_entries = anchor_entries[:_KMZ_SEMANTIC_ANCHOR_CAP]

    # ---------------------------------------------------------------------------
    # Style resolution health — additive diagnostic only. Never alters resolved_styles,
    # style_resolved on features, or any classification. Counts are derived from
    # the already-parsed root element and the resolved_styles dict produced above.
    # ---------------------------------------------------------------------------
    _style_health: Dict[str, Any] = {
        "ids_declared": 0,
        "ids_referenced": 0,
        "ids_referenced_unresolved": 0,
        "stylemap_count": 0,
        "stylemap_unresolved_count": 0,
        # Cycle detection is not tracked per-run (the resolution loop in
        # _kmz_semantic_parse_styles breaks out silently when a cycle is found).
        # Returning 0 rather than guessing; a future pass can instrument it.
        "stylemap_cycle_count": 0,
    }
    _missing_style_urls: List[str] = []
    try:
        _ids_declared = sum(
            1 for _s in root.findall(".//kml:Style", KML_NS)
            if (_s.get("id") or "").strip()
        )
        _stylemap_all = [
            _sm for _sm in root.findall(".//kml:StyleMap", KML_NS)
            if (_sm.get("id") or "").strip()
        ]
        _stylemap_count = len(_stylemap_all)
        # A StyleMap is "unresolved" when its id is absent from resolved_styles.
        _stylemap_unresolved = sum(
            1 for _sm in _stylemap_all
            if (_sm.get("id") or "").strip() not in resolved_styles
        )
        # Placemark-referenced style_urls: strip leading '#' for lookup.
        _referenced_normalized = {k.lstrip("#") for k in style_url_count if k}
        _ids_referenced = len(_referenced_normalized)
        # Unresolved: referenced keys absent from resolved_styles.
        _unresolved_keys = sorted(
            k for k in _referenced_normalized if k and k not in resolved_styles
        )
        _ids_referenced_unresolved = len(_unresolved_keys)
        _missing_style_urls = _unresolved_keys[:25]
        _style_health = {
            "ids_declared": _ids_declared,
            "ids_referenced": _ids_referenced,
            "ids_referenced_unresolved": _ids_referenced_unresolved,
            "stylemap_count": _stylemap_count,
            "stylemap_unresolved_count": _stylemap_unresolved,
            "stylemap_cycle_count": 0,
        }
    except Exception:
        pass  # non-fatal; _style_health stays at zero defaults

    index = {
        "feature_count": len(features),
        "truncated": truncated,
        "by_classification": by_classification,
        "by_geometry_type": by_geometry_type,
        "by_folder": by_folder,
        "by_confidence": by_confidence,
        "style_url_count": style_url_count,
        "extended_data_keys": sorted(extended_data_keys.keys()),
        # Phase 1B additive diagnostic fields.
        "top_folders": top_folders,
        "top_style_urls": top_style_urls,
        "classification_samples": classification_samples,
        "source_filenames": [safe_source_filename] if features else [],
        "feature_cap": _KMZ_SEMANTIC_FEATURE_CAP,
        "sample_cap": _KMZ_SEMANTIC_SAMPLE_CAP,
        # Phase A/B/C additive diagnostic fields. All bounded; safe on wire.
        "by_lifecycle": by_lifecycle,
        "top_lifecycle": top_lifecycle,
        "top_resolved_line_colors": top_resolved_line_colors,
        "features_with_chainage": features_with_chainage,
        "features_with_sequence": features_with_sequence,
        "features_with_full_geometry": features_with_full_geometry,
        "features_with_resolved_style": features_with_resolved_style,
        "styles_resolved_count": len(resolved_styles),
        "anchor_catalog": anchor_entries,
        "anchor_catalog_truncated": anchor_truncated,
        "anchor_cap": _KMZ_SEMANTIC_ANCHOR_CAP,
        # Skipped-placemark observability fields (additive, never removes data).
        "skipped_placemark_count": skipped_placemark_count,
        "skipped_placemark_samples": skipped_placemark_samples,
        # Style resolution health (additive, diagnostic only).
        "style_resolution": _style_health,
        "missing_style_urls": _missing_style_urls,
    }

    print(
        f"[KMZ_SEM_TRACE] _build_kmz_semantic RETURN filename={filename!r} "
        f"feature_count={len(features)} anchor_count={len(anchor_entries)} "
        f"styles_resolved={len(resolved_styles)} truncated={truncated} "
        f"skipped={skipped_placemark_count} warnings={len(warnings)}",
        flush=True,
    )
    return {
        "parser_version": "semantic-1",
        "features": features,
        "index": index,
        "warnings": warnings,
    }


def _append_ingestion_ledger_entry(
    file_bytes: bytes,
    filename: str,
    semantic_payload: Optional[Dict[str, Any]],
) -> None:
    """Phase 1D — append one JSONL row per KMZ semantic ingestion.

    Never raises; a warning is logged on I/O failure. Does not mutate STATE.
    If ``semantic_payload`` is None (parse failed), all semantic-derived
    fields are written as their zero/False defaults so a row is always
    persisted.
    """
    import hashlib as _hashlib
    from datetime import timezone as _tz

    try:
        input_sha256 = _hashlib.sha256(file_bytes).hexdigest()

        _idx: Dict[str, Any] = {}
        _anchors: list = []
        _warnings: list = []
        _features: list = []
        _parser_version: Optional[str] = None

        if isinstance(semantic_payload, dict):
            _parser_version = semantic_payload.get("parser_version")
            _idx = semantic_payload.get("index") or {}
            _features = semantic_payload.get("features") or []
            _warnings = semantic_payload.get("warnings") or []
            _anchors = _idx.get("anchor_catalog") or []

        _sr: Dict[str, Any] = _idx.get("style_resolution") or {}

        row: Dict[str, Any] = {
            "ingested_at": datetime.now(_tz.utc).isoformat(),
            "filename": Path(filename).name[:200],
            "input_sha256": input_sha256,
            "parser_version": _parser_version,
            "feature_count": len(_features),
            "anchor_count": len(_anchors),
            "skipped_placemark_count": int(_idx.get("skipped_placemark_count") or 0),
            "warnings_count": len(_warnings),
            "truncated": bool(_idx.get("truncated", False)),
            "anchor_catalog_truncated": bool(_idx.get("anchor_catalog_truncated", False)),
            "styles_resolved_count": int(_idx.get("styles_resolved_count") or 0),
            "ids_referenced_unresolved": int(_sr.get("ids_referenced_unresolved") or 0),
            "stylemap_unresolved_count": int(_sr.get("stylemap_unresolved_count") or 0),
        }

        # Append row to JSONL file.
        with open(INGESTION_LEDGER_PATH, "a", encoding="utf-8") as _fh:
            _fh.write(json.dumps(row, separators=(",", ":")) + "\n")

        # Trim to most recent INGESTION_LEDGER_MAX_ROWS rows if exceeded.
        with open(INGESTION_LEDGER_PATH, "r", encoding="utf-8") as _fh:
            _lines = _fh.readlines()

        if len(_lines) > INGESTION_LEDGER_MAX_ROWS:
            _lines = _lines[-INGESTION_LEDGER_MAX_ROWS:]
            with open(INGESTION_LEDGER_PATH, "w", encoding="utf-8") as _fh:
                _fh.writelines(_lines)

    except Exception as _led_exc:  # pragma: no cover
        print(
            f"[INGESTION_LEDGER] WARNING: failed to append ledger entry: "
            f"{type(_led_exc).__name__}: {_led_exc}",
            flush=True,
        )


def _append_match_audit_entry(
    event: str,
    route: Optional[Dict[str, Any]],
    previous_route_id: Optional[Any],
) -> None:
    """Phase 1F — append one JSONL row per active-route transition.

    Never raises; a warning is logged on I/O failure. Pure read of STATE
    (no mutations). Mirrors ``_append_ingestion_ledger_entry`` structure.
    """
    from datetime import timezone as _tz

    try:
        _route_id: Optional[str] = None
        _route_name: Optional[str] = None
        _route_length_ft: Optional[float] = None

        if isinstance(route, dict):
            _rid = route.get("route_id")
            _route_id = str(_rid) if _rid is not None else None
            _rname = route.get("route_name") or route.get("name")
            _route_name = str(_rname) if _rname is not None else None
            try:
                _route_length_ft = float(route.get("length_ft") or 0.0) or None
            except (TypeError, ValueError):
                _route_length_ft = None

        _prev = str(previous_route_id) if previous_route_id is not None else None
        _session = STATE.get("_session_id_hint")
        _sha = STATE.get("last_kmz_input_sha256")
        _catalog_size = len(STATE.get("route_catalog") or [])

        row: Dict[str, Any] = {
            "decided_at": datetime.now(_tz.utc).isoformat(),
            "event": event,
            "session_id_hint": str(_session) if _session is not None else None,
            "route_id": _route_id,
            "route_name": _route_name,
            "route_length_ft": _route_length_ft,
            "previous_route_id": _prev,
            "route_catalog_size": _catalog_size,
            "input_sha256": str(_sha) if _sha is not None else None,
        }

        with open(MATCH_AUDIT_PATH, "a", encoding="utf-8") as _fh:
            _fh.write(json.dumps(row, separators=(",", ":")) + "\n")

        with open(MATCH_AUDIT_PATH, "r", encoding="utf-8") as _fh:
            _lines = _fh.readlines()

        if len(_lines) > MATCH_AUDIT_MAX_ROWS:
            _lines = _lines[-MATCH_AUDIT_MAX_ROWS:]
            with open(MATCH_AUDIT_PATH, "w", encoding="utf-8") as _fh:
                _fh.writelines(_lines)

    except Exception as _aud_exc:  # pragma: no cover
        print(
            f"[MATCH_AUDIT] WARNING: failed to append audit entry: "
            f"{type(_aud_exc).__name__}: {_aud_exc}",
            flush=True,
        )


def _append_match_audit_v2_entries(
    group_matches: List[Dict[str, Any]],
) -> None:
    """Phase 1G — append one JSONL row per group_match per matching pass.

    Schema version: "match-audit-2".  Never raises; logs a warning on any
    I/O failure.  Pure read of STATE — no mutations.

    One ``match_pass_id`` (uuid4) is generated per call and stamped on every
    row so consumers can reconstruct all groups from a single matching pass.
    ``_build_semantic_match_shadow()`` is called once per call (not per group)
    to derive the presence-only ``semantic_shadow_available`` bool; if it
    raises for any reason the value defaults to False.
    """
    import uuid as _uuid
    from datetime import timezone as _tz

    try:
        _pass_id = str(_uuid.uuid4())
        _decided_at = datetime.now(_tz.utc).isoformat()
        _session = STATE.get("_session_id_hint")
        _sha = STATE.get("last_kmz_input_sha256")

        # Shadow presence check — once per pass, never propagates exceptions.
        try:
            _shadow = _build_semantic_match_shadow()
            _shadow_available = _shadow is not None
        except Exception:
            _shadow_available = False

        rows: List[str] = []

        for _match in (group_matches or []):
            if not isinstance(_match, dict):
                continue

            _validation: Dict[str, Any] = _match.get("validation") or {}
            _render_gate: Dict[str, Any] = _validation.get("render_gate") or {}
            _selected_hyp: Dict[str, Any] = _match.get("selected_hypothesis") or {}
            _all_rankings: List[Any] = _match.get("candidate_rankings") or []

            # anchor_reasons: first 5, each capped at 200 chars.
            _raw_anchor_reasons: List[Any] = _selected_hyp.get("anchor_reasons") or []
            _anchor_reasons: List[str] = [
                str(r)[:200]
                for r in _raw_anchor_reasons[:5]
                if r is not None
            ]

            # candidate_rankings_top3: first 3, narrow projection.
            _top3: List[Dict[str, Any]] = []
            for _r in _all_rankings[:3]:
                if not isinstance(_r, dict):
                    continue
                try:
                    _r_len = float(_r.get("route_length_ft") or 0.0) or None
                except (TypeError, ValueError):
                    _r_len = None
                try:
                    _r_exp = float(_r.get("expected_span_ft") or 0.0) or None
                except (TypeError, ValueError):
                    _r_exp = None
                try:
                    _r_gap = float(_r.get("length_gap_ft") or 0.0)
                except (TypeError, ValueError):
                    _r_gap = None
                try:
                    _r_score = float(_r.get("score") or 0.0) or None
                except (TypeError, ValueError):
                    _r_score = None
                _r_rid = _r.get("route_id")
                _r_rname = _r.get("route_name")
                _r_rrole = _r.get("route_role")
                _top3.append(
                    {
                        "route_id": str(_r_rid) if _r_rid is not None else None,
                        "route_name": str(_r_rname) if _r_rname is not None else None,
                        "route_role": str(_r_rrole) if _r_rrole is not None else None,
                        "route_length_ft": _r_len,
                        "expected_span_ft": _r_exp,
                        "length_gap_ft": _r_gap,
                        "score": _r_score,
                    }
                )

            # Numeric fields — safe conversion.
            try:
                _conf: Optional[float] = float(_match.get("confidence") or 0.0) or None
            except (TypeError, ValueError):
                _conf = None
            try:
                _exp_span: Optional[float] = float(_match.get("expected_span_ft") or 0.0) or None
            except (TypeError, ValueError):
                _exp_span = None
            try:
                _len_gap: Optional[float] = float(_match.get("length_gap_ft") or 0.0)
            except (TypeError, ValueError):
                _len_gap = None

            # final_decision: already a string in group_match, truncated for safety.
            _fd = _match.get("final_decision")
            _final_decision: Optional[str] = str(_fd)[:500] if _fd is not None else None

            _rid = _match.get("route_id")
            _rname = _match.get("route_name")
            _rrole = _match.get("route_role")
            _clabel = _match.get("confidence_label")
            _vs = _validation.get("validation_status")
            _rm = _render_gate.get("mode")
            _gid = _match.get("group_id")
            _sf = _match.get("source_file")
            _pt = _match.get("print")

            row: Dict[str, Any] = {
                "schema_version": "match-audit-2",
                "decided_at": _decided_at,
                "match_pass_id": _pass_id,
                "session_id_hint": str(_session) if _session is not None else None,
                "input_sha256": str(_sha) if _sha is not None else None,
                "group_id": str(_gid) if _gid is not None else None,
                "source_file": str(_sf) if _sf is not None else None,
                "print": str(_pt) if _pt is not None else None,
                "winning_route_id": str(_rid) if _rid is not None else None,
                "winning_route_name": str(_rname) if _rname is not None else None,
                "winning_route_role": str(_rrole) if _rrole is not None else None,
                "confidence": _conf,
                "confidence_label": str(_clabel) if _clabel is not None else None,
                "final_decision": _final_decision,
                "expected_span_ft": _exp_span,
                "length_gap_ft": _len_gap,
                "validation_status": str(_vs) if _vs is not None else None,
                "render_allowed": bool(_match.get("render_allowed")),
                "render_mode": str(_rm) if _rm is not None else None,
                "render_block_reasons": [
                    str(r) for r in (list(_match.get("render_block_reasons") or [])[:10])
                ],
                "rendered_station_point_count": int(
                    _match.get("rendered_station_point_count") or 0
                ),
                "rendered_redline_segment_count": int(
                    _match.get("rendered_redline_segment_count") or 0
                ),
                "anchor_reasons": _anchor_reasons,
                "candidate_rankings_top3": _top3,
                "candidate_rankings_total_count": len(_all_rankings),
                "semantic_shadow_available": bool(_shadow_available),
            }

            rows.append(json.dumps(row, separators=(",", ":")) + "\n")

        if not rows:
            return

        # Append all rows from this pass atomically (one open per pass).
        with open(MATCH_AUDIT_GROUPS_PATH, "a", encoding="utf-8") as _fh:
            _fh.writelines(rows)

        # Tail-truncate to cap.
        with open(MATCH_AUDIT_GROUPS_PATH, "r", encoding="utf-8") as _fh:
            _all_lines = _fh.readlines()

        if len(_all_lines) > MATCH_AUDIT_GROUPS_MAX_ROWS:
            _all_lines = _all_lines[-MATCH_AUDIT_GROUPS_MAX_ROWS:]
            with open(MATCH_AUDIT_GROUPS_PATH, "w", encoding="utf-8") as _fh:
                _fh.writelines(_all_lines)

    except Exception as _v2_exc:  # pragma: no cover
        print(
            f"[MATCH_AUDIT_V2] WARNING: failed to append v2 audit entries: "
            f"{type(_v2_exc).__name__}: {_v2_exc}",
            flush=True,
        )


def _append_match_shadow_compare_entries(
    group_matches: List[Dict[str, Any]],
) -> None:
    """Phase 1H-A — persist one shadow-compare row per group_match per pass.

    Schema version: "match-shadow-1".  Never raises; logs a warning on any
    I/O failure.  Pure read of STATE — no mutations.

    Calls ``_build_semantic_match_shadow()`` once per pass to obtain
    group-level disagreement data.  If the shadow is unavailable (returns
    None) or raises, every row is still written with ``had_shadow_payload=False``
    and all ``semantic_*`` fields nulled — guaranteeing a row-per-group
    invariant for replay analytics.

    The ``operational_winner_*`` fields are sourced from ``group_matches``
    (the production pipeline output), NOT from the shadow payload.
    """
    import uuid as _uuid_sc
    from datetime import timezone as _tz_sc

    try:
        _pass_id_sc = str(_uuid_sc.uuid4())
        _decided_at_sc = datetime.now(_tz_sc.utc).isoformat()
        _session_sc = STATE.get("_session_id_hint")
        _sha_sc = STATE.get("last_kmz_input_sha256")

        # Call shadow generator once per pass — never propagates exceptions.
        _shadow_payload_sc: Optional[Dict[str, Any]] = None
        _had_shadow_sc: bool = False
        _shadow_version_sc: Optional[str] = None
        try:
            _shadow_payload_sc = _build_semantic_match_shadow()
            _had_shadow_sc = isinstance(_shadow_payload_sc, dict)
            if _had_shadow_sc:
                _shadow_version_sc = _shadow_payload_sc.get("version")  # type: ignore[union-attr]
        except Exception:
            _shadow_payload_sc = None
            _had_shadow_sc = False

        # Build a group_id → shadow group entry index for O(1) lookup when
        # shadow is available.  Shadow iterates the same group_matches list,
        # so group_index is the stable join key.
        _shadow_groups_sc: List[Dict[str, Any]] = (
            _shadow_payload_sc.get("groups") or []  # type: ignore[union-attr]
            if _had_shadow_sc
            else []
        )

        rows_sc: List[str] = []

        for _gi_sc, _match_sc in enumerate(group_matches or []):
            if not isinstance(_match_sc, dict):
                continue

            # Operational winner fields — from production pipeline output.
            _op_rid = _match_sc.get("route_id")
            _op_rname = _match_sc.get("route_name")
            try:
                _op_conf: Optional[float] = (
                    float(_match_sc.get("confidence") or 0.0) or None
                )
            except (TypeError, ValueError):
                _op_conf = None

            _gid_sc = _match_sc.get("group_id")

            # Shadow fields — from shadow payload keyed by group_index.
            if _had_shadow_sc and _gi_sc < len(_shadow_groups_sc):
                _sg = _shadow_groups_sc[_gi_sc]
                if isinstance(_sg, dict):
                    _sem_rid = _sg.get("semantic_best_route_id")
                    _sem_rname = _sg.get("semantic_best_route_name")
                    try:
                        _sem_score: Optional[float] = (
                            float(_sg.get("semantic_best_score") or 0.0) or None
                        )
                    except (TypeError, ValueError):
                        _sem_score = None
                    _agreement = _sg.get("agreement")
                    try:
                        _anch_op: int = int(_sg.get("anchors_near_selected_route") or 0)
                    except (TypeError, ValueError):
                        _anch_op = 0
                    try:
                        _anch_sem: int = int(
                            _sg.get("anchors_near_semantic_best_route") or 0
                        )
                    except (TypeError, ValueError):
                        _anch_sem = 0
                    _contrib_ids: List[str] = [
                        str(x)
                        for x in (list(_sg.get("contributing_anchor_ids") or [])[:10])
                    ]
                    _expl_raw = _sg.get("explanation")
                    _explanation: Optional[str] = (
                        str(_expl_raw)[:500] if _expl_raw is not None else None
                    )
                else:
                    # Shadow group entry was not a dict — treat as unavailable.
                    _sem_rid = None
                    _sem_rname = None
                    _sem_score = None
                    _agreement = None
                    _anch_op = 0
                    _anch_sem = 0
                    _contrib_ids = []
                    _explanation = None
            else:
                # Shadow unavailable for this group.
                _sem_rid = None
                _sem_rname = None
                _sem_score = None
                _agreement = None
                _anch_op = 0
                _anch_sem = 0
                _contrib_ids = []
                _explanation = None

            row_sc: Dict[str, Any] = {
                "schema_version": "match-shadow-1",
                "decided_at": _decided_at_sc,
                "match_pass_id": _pass_id_sc,
                "session_id_hint": str(_session_sc) if _session_sc is not None else None,
                "input_sha256": str(_sha_sc) if _sha_sc is not None else None,
                "shadow_version": str(_shadow_version_sc) if _shadow_version_sc is not None else None,
                "had_shadow_payload": _had_shadow_sc,
                "group_id": str(_gid_sc) if _gid_sc is not None else None,
                "group_index": _gi_sc,
                "operational_winner_route_id": str(_op_rid) if _op_rid is not None else None,
                "operational_winner_route_name": str(_op_rname) if _op_rname is not None else None,
                "operational_confidence": _op_conf,
                "semantic_winner_route_id": str(_sem_rid) if _sem_rid is not None else None,
                "semantic_winner_route_name": str(_sem_rname) if _sem_rname is not None else None,
                "semantic_winner_score": _sem_score,
                "agreement": _agreement,
                "anchors_near_operational_winner": _anch_op,
                "anchors_near_semantic_winner": _anch_sem,
                "contributing_anchor_ids": _contrib_ids,
                "shadow_explanation": _explanation,
            }

            rows_sc.append(json.dumps(row_sc, separators=(",", ":")) + "\n")

        if not rows_sc:
            return

        # Append all rows from this pass atomically.
        with open(MATCH_SHADOW_COMPARE_PATH, "a", encoding="utf-8") as _fh_sc:
            _fh_sc.writelines(rows_sc)

        # Tail-truncate to cap.
        with open(MATCH_SHADOW_COMPARE_PATH, "r", encoding="utf-8") as _fh_sc:
            _all_lines_sc = _fh_sc.readlines()

        if len(_all_lines_sc) > MATCH_SHADOW_COMPARE_MAX_ROWS:
            _all_lines_sc = _all_lines_sc[-MATCH_SHADOW_COMPARE_MAX_ROWS:]
            with open(MATCH_SHADOW_COMPARE_PATH, "w", encoding="utf-8") as _fh_sc:
                _fh_sc.writelines(_all_lines_sc)

    except Exception as _sc_exc:  # pragma: no cover
        print(
            f"[MATCH_SHADOW] WARNING: failed to append shadow-compare entries: "
            f"{type(_sc_exc).__name__}: {_sc_exc}",
            flush=True,
        )


def _compute_match_shadow_summary(
    rows: List[Dict[str, Any]],
    group_by: str,
) -> Dict[str, Any]:
    """Phase 1H-B-I — pure-function summary analytics over match-shadow-1 rows.

    Takes the already-parsed row list (most-recent-first from the endpoint)
    and a ``group_by`` string ("none" or "input_sha256").  Returns the
    ``match-shadow-summary-1`` dict (9 keys; endpoint adds ``computed_at``).

    Never raises — wraps entire computation in try/except and returns an
    empty skeleton on any failure.

    Only the 6 approved metric families are computed; no per-classification,
    per-route-role, per-folder, or per-style metrics are included.
    """
    _MIN_RATE = 10           # global minimum sample size before rates are emitted
    _MIN_RATE_SHA = 5        # per-SHA minimum sample size
    _TOP_PASS_CAP = 10       # leaderboard cap
    _BY_SHA_CAP = 50         # per-SHA rollup array cap

    _STABILITY_NOTE = (
        "match-shadow-summary-1 metrics are PROVISIONAL until at least 2 distinct "
        "input_sha256 values have each contributed at least 100 groups in the "
        "window. Per-classification (handhole / splice / structure / segment) "
        "and per-route-role rates require Phase 1H-C; the absence of those "
        "fields in this response does not indicate missing data."
    )

    def _empty_summary() -> Dict[str, Any]:
        return {
            "schema_version": "match-shadow-summary-1",
            "window": {
                "rows_read": 0,
                "match_pass_count": 0,
                "unique_input_sha256_count": 0,
                "earliest_decided_at": None,
                "latest_decided_at": None,
            },
            "shadow_availability": {
                "sample_size": 0,
                "rows_with_shadow_payload": 0,
                "shadow_availability_rate": None,
            },
            "agreement": {
                "sample_size": 0,
                "agree_count": 0,
                "disagree_count": 0,
                "inconclusive_count": 0,
                "agree_rate": None,
                "disagree_rate": None,
                "inconclusive_rate": None,
            },
            "anchor_participation": {
                "sample_size": 0,
                "groups_with_anchors_near_op": 0,
                "groups_with_anchors_near_sem": 0,
                "rate_anchors_near_op": None,
                "rate_anchors_near_sem": None,
                "avg_anchors_near_op": None,
                "avg_anchors_near_sem": None,
            },
            "top_disagreement_passes": [],
            "by_input_sha256": [],
            "guards": {
                "min_samples_for_rate": _MIN_RATE,
                "min_samples_for_rate_per_sha": _MIN_RATE_SHA,
                "rate_below_threshold_returns_null": True,
            },
            "stability_note": _STABILITY_NOTE,
        }

    try:
        if not rows:
            return _empty_summary()

        # ── Family 1: window ─────────────────────────────────────────────────
        _pass_ids: set = set()
        _shas: set = set()
        _decided_ats: List[str] = []

        for _r in rows:
            if not isinstance(_r, dict):
                continue
            _pid = _r.get("match_pass_id")
            if _pid is not None:
                _pass_ids.add(str(_pid))
            _sha = _r.get("input_sha256")
            if _sha is not None:
                _shas.add(str(_sha))
            _dat = _r.get("decided_at")
            if _dat is not None:
                _decided_ats.append(str(_dat))

        _n_rows = sum(1 for _r in rows if isinstance(_r, dict))
        _unique_sha_count = len(_shas)

        _window: Dict[str, Any] = {
            "rows_read": _n_rows,
            "match_pass_count": len(_pass_ids),
            "unique_input_sha256_count": _unique_sha_count,
            "earliest_decided_at": min(_decided_ats) if _decided_ats else None,
            "latest_decided_at": max(_decided_ats) if _decided_ats else None,
        }

        # ── Family 2: shadow_availability ───────────────────────────────────
        _n_with_shadow = sum(
            1 for _r in rows
            if isinstance(_r, dict) and _r.get("had_shadow_payload") is True
        )
        _shadow_avail_rate: Optional[float] = (
            round(_n_with_shadow / _n_rows, 4)
            if _n_rows >= _MIN_RATE
            else None
        )
        _shadow_availability: Dict[str, Any] = {
            "sample_size": _n_rows,
            "rows_with_shadow_payload": _n_with_shadow,
            "shadow_availability_rate": _shadow_avail_rate,
        }

        # ── Shared: shadow-gated rows ────────────────────────────────────────
        _shadow_rows = [
            _r for _r in rows
            if isinstance(_r, dict) and _r.get("had_shadow_payload") is True
        ]
        _n_shadow = len(_shadow_rows)

        # ── Family 3: agreement ──────────────────────────────────────────────
        _agree = sum(1 for _r in _shadow_rows if _r.get("agreement") is True)
        _disagree = sum(1 for _r in _shadow_rows if _r.get("agreement") is False)
        _inconclusive = sum(1 for _r in _shadow_rows if _r.get("agreement") is None)

        if _n_shadow >= _MIN_RATE:
            _agree_rate: Optional[float] = round(_agree / _n_shadow, 4)
            _disagree_rate: Optional[float] = round(_disagree / _n_shadow, 4)
            _inconcl_rate: Optional[float] = round(_inconclusive / _n_shadow, 4)
        else:
            _agree_rate = _disagree_rate = _inconcl_rate = None

        _agreement: Dict[str, Any] = {
            "sample_size": _n_shadow,
            "agree_count": _agree,
            "disagree_count": _disagree,
            "inconclusive_count": _inconclusive,
            "agree_rate": _agree_rate,
            "disagree_rate": _disagree_rate,
            "inconclusive_rate": _inconcl_rate,
        }

        # ── Family 4: anchor_participation ───────────────────────────────────
        _n_anch_op = 0
        _n_anch_sem = 0
        _sum_anch_op = 0
        _sum_anch_sem = 0

        for _r in _shadow_rows:
            try:
                _a_op = int(_r.get("anchors_near_operational_winner") or 0)
            except (TypeError, ValueError):
                _a_op = 0
            try:
                _a_sem = int(_r.get("anchors_near_semantic_winner") or 0)
            except (TypeError, ValueError):
                _a_sem = 0
            if _a_op > 0:
                _n_anch_op += 1
            if _a_sem > 0:
                _n_anch_sem += 1
            _sum_anch_op += _a_op
            _sum_anch_sem += _a_sem

        if _n_shadow >= _MIN_RATE:
            _rate_op: Optional[float] = round(_n_anch_op / _n_shadow, 4)
            _rate_sem: Optional[float] = round(_n_anch_sem / _n_shadow, 4)
            _avg_op: Optional[float] = round(_sum_anch_op / _n_shadow, 2)
            _avg_sem: Optional[float] = round(_sum_anch_sem / _n_shadow, 2)
        else:
            _rate_op = _rate_sem = _avg_op = _avg_sem = None

        _anchor_participation: Dict[str, Any] = {
            "sample_size": _n_shadow,
            "groups_with_anchors_near_op": _n_anch_op,
            "groups_with_anchors_near_sem": _n_anch_sem,
            "rate_anchors_near_op": _rate_op,
            "rate_anchors_near_sem": _rate_sem,
            "avg_anchors_near_op": _avg_op,
            "avg_anchors_near_sem": _avg_sem,
        }

        # ── Family 5: top_disagreement_passes ────────────────────────────────
        _pass_bucket_dis: Dict[str, int] = {}
        _pass_bucket_tot: Dict[str, int] = {}
        _pass_bucket_dats: Dict[str, List[str]] = {}
        _pass_bucket_sha: Dict[str, Optional[str]] = {}

        for _r in rows:
            if not isinstance(_r, dict):
                continue
            _pid_s = _r.get("match_pass_id")
            if _pid_s is None:
                continue
            _pid_s = str(_pid_s)
            _pass_bucket_tot[_pid_s] = _pass_bucket_tot.get(_pid_s, 0) + 1
            _dat_s = _r.get("decided_at")
            if _dat_s is not None:
                _pass_bucket_dats.setdefault(_pid_s, []).append(str(_dat_s))
            if _pass_bucket_sha.get(_pid_s) is None:
                _sha_s = _r.get("input_sha256")
                if _sha_s is not None:
                    _pass_bucket_sha[_pid_s] = str(_sha_s)
            if _r.get("had_shadow_payload") is True and _r.get("agreement") is False:
                _pass_bucket_dis[_pid_s] = _pass_bucket_dis.get(_pid_s, 0) + 1

        _leaderboard: List[Dict[str, Any]] = []
        for _pid_s, _tot in _pass_bucket_tot.items():
            _dis = _pass_bucket_dis.get(_pid_s, 0)
            if _dis == 0:
                continue
            _dats_for_pass = _pass_bucket_dats.get(_pid_s) or []
            _leaderboard.append(
                {
                    "match_pass_id": _pid_s,
                    "decided_at": min(_dats_for_pass) if _dats_for_pass else None,
                    "input_sha256": _pass_bucket_sha.get(_pid_s),
                    "disagree_count": _dis,
                    "group_count": _tot,
                }
            )
        _leaderboard.sort(
            key=lambda _e: (-_e["disagree_count"], -_e["group_count"], _e["match_pass_id"])
        )
        _top_passes = _leaderboard[:_TOP_PASS_CAP]

        # ── Family 6: by_input_sha256 ────────────────────────────────────────
        _sha_tot: Dict[str, int] = {}
        _sha_shadow: Dict[str, int] = {}
        _sha_agree: Dict[str, int] = {}
        _sha_disagree: Dict[str, int] = {}
        _sha_inconclusive: Dict[str, int] = {}
        _sha_n_op: Dict[str, int] = {}
        _sha_n_sem: Dict[str, int] = {}

        for _r in rows:
            if not isinstance(_r, dict):
                continue
            _sha_k = _r.get("input_sha256")
            if _sha_k is None:
                continue
            _sha_k = str(_sha_k)
            _sha_tot[_sha_k] = _sha_tot.get(_sha_k, 0) + 1
            if _r.get("had_shadow_payload") is True:
                _sha_shadow[_sha_k] = _sha_shadow.get(_sha_k, 0) + 1
                _ag = _r.get("agreement")
                if _ag is True:
                    _sha_agree[_sha_k] = _sha_agree.get(_sha_k, 0) + 1
                elif _ag is False:
                    _sha_disagree[_sha_k] = _sha_disagree.get(_sha_k, 0) + 1
                else:
                    _sha_inconclusive[_sha_k] = _sha_inconclusive.get(_sha_k, 0) + 1
                try:
                    _sa_op = int(_r.get("anchors_near_operational_winner") or 0)
                except (TypeError, ValueError):
                    _sa_op = 0
                try:
                    _sa_sem = int(_r.get("anchors_near_semantic_winner") or 0)
                except (TypeError, ValueError):
                    _sa_sem = 0
                if _sa_op > 0:
                    _sha_n_op[_sha_k] = _sha_n_op.get(_sha_k, 0) + 1
                if _sa_sem > 0:
                    _sha_n_sem[_sha_k] = _sha_n_sem.get(_sha_k, 0) + 1

        _by_sha: List[Dict[str, Any]] = []
        for _sha_k, _sha_total in _sha_tot.items():
            _n_shad = _sha_shadow.get(_sha_k, 0)
            # shadow_availability_rate guarded by total rows for this SHA
            _s_avail = (
                round(_n_shad / _sha_total, 4)
                if _sha_total >= _MIN_RATE_SHA
                else None
            )
            # Agreement + anchor rates guarded by shadow-available rows for this SHA
            if _n_shad >= _MIN_RATE_SHA:
                _s_agree = round(_sha_agree.get(_sha_k, 0) / _n_shad, 4)
                _s_dis = round(_sha_disagree.get(_sha_k, 0) / _n_shad, 4)
                _s_inc = round(_sha_inconclusive.get(_sha_k, 0) / _n_shad, 4)
                _s_op = round(_sha_n_op.get(_sha_k, 0) / _n_shad, 4)
                _s_sem = round(_sha_n_sem.get(_sha_k, 0) / _n_shad, 4)
            else:
                _s_agree = _s_dis = _s_inc = _s_op = _s_sem = None
            _by_sha.append(
                {
                    "input_sha256": _sha_k,
                    "rows_in_window": _sha_total,
                    "shadow_availability_rate": _s_avail,
                    "agree_rate": _s_agree,
                    "disagree_rate": _s_dis,
                    "inconclusive_rate": _s_inc,
                    "rate_anchors_near_op": _s_op,
                    "rate_anchors_near_sem": _s_sem,
                    "sample_size": _n_shad,
                }
            )
        _by_sha.sort(key=lambda _e: (-_e["rows_in_window"], _e["input_sha256"]))
        _by_sha = _by_sha[:_BY_SHA_CAP]

        # Conditionally populate: only when explicitly requested or ≥2 SHAs present.
        _emit_by_sha = (
            group_by == "input_sha256" or _unique_sha_count >= 2
        )
        _by_sha_out = _by_sha if _emit_by_sha else []

        return {
            "schema_version": "match-shadow-summary-1",
            "window": _window,
            "shadow_availability": _shadow_availability,
            "agreement": _agreement,
            "anchor_participation": _anchor_participation,
            "top_disagreement_passes": _top_passes,
            "by_input_sha256": _by_sha_out,
            "guards": {
                "min_samples_for_rate": _MIN_RATE,
                "min_samples_for_rate_per_sha": _MIN_RATE_SHA,
                "rate_below_threshold_returns_null": True,
            },
            "stability_note": _STABILITY_NOTE,
        }

    except Exception as _sum_exc:  # pragma: no cover
        print(
            f"[MATCH_SHADOW_SUMMARY] WARNING: failed to compute summary: "
            f"{type(_sum_exc).__name__}: {_sum_exc}",
            flush=True,
        )
        return _empty_summary()


def _build_route_catalog(file_bytes: bytes, filename: str) -> List[Dict[str, Any]]:
    kml_bytes = _extract_kml_bytes(file_bytes, filename)
    root = ET.fromstring(kml_bytes)
    parent_map = _parent_map(root)

    routes: List[Dict[str, Any]] = []
    route_counter = 0

    for placemark in root.findall(".//kml:Placemark", KML_NS):
        placemark_name = (placemark.findtext("kml:name", default="", namespaces=KML_NS) or "").strip() or "Unnamed Route"
        folder_names = _folder_path(placemark, parent_map)
        source_folder = " / ".join(folder_names[1:]) if len(folder_names) > 1 else (folder_names[0] if folder_names else "")
        role_hint = f"{source_folder} {placemark_name}".strip().lower()

        for node in placemark.findall(".//kml:LineString/kml:coordinates", KML_NS):
            raw_coords = _dedupe_consecutive(_parse_coordinate_text(node.text or ""))
            if len(raw_coords) < 2:
                continue

            coords = _densify_route_coords(raw_coords)
            route_counter += 1
            route_length_ft = round(_route_length_ft(coords), 2)
            role = _infer_route_role(role_hint)

            routes.append(
                {
                    "route_id": f"route_{route_counter}",
                    "route_name": placemark_name,
                    "name": placemark_name,
                    "source_folder": source_folder,
                    "coords": coords,
                    "length_ft": route_length_ft,
                    "point_count": len(coords),
                    "route_role": role,
                }
            )

    if not routes:
        raise ValueError("No valid LineString routes found in design file.")

    routes.sort(key=lambda route: (-float(route.get("length_ft", 0.0) or 0.0), route.get("route_name", "")))
    return routes


def _choose_default_route(route_catalog: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    if not route_catalog:
        raise ValueError("Route catalog is empty.")
    return max(route_catalog, key=lambda route: float(route.get("length_ft", 0.0) or 0.0))


def _find_route_by_id(route_id: Any) -> Optional[Dict[str, Any]]:
    target = str(route_id or "").strip()
    for route in STATE.get("route_catalog", []) or []:
        if str(route.get("route_id", "")).strip() == target:
            return route
    return None


def _set_active_route(route: Optional[Dict[str, Any]]) -> None:
    _prev_id = STATE.get("route_id")  # Phase 1F: capture before any STATE write
    if not route:
        STATE["route_id"] = None
        STATE["route_name"] = None
        STATE["route_coords"] = []
        STATE["route_length_ft"] = 0.0
        STATE["map_points"] = []
        _append_match_audit_entry(event="active_route_cleared", route=None, previous_route_id=_prev_id)
        return

    STATE["route_id"] = route.get("route_id")
    STATE["route_name"] = route.get("route_name") or route.get("name")
    STATE["route_coords"] = route.get("coords", []) or []
    STATE["route_length_ft"] = float(route.get("length_ft", 0.0) or 0.0)
    STATE["map_points"] = route.get("coords", []) or []
    _append_match_audit_entry(event="active_route_set", route=route, previous_route_id=_prev_id)


def _route_chainage(coords: Sequence[Sequence[float]]) -> List[float]:
    chainage = [0.0]
    for i in range(1, len(coords)):
        chainage.append(
            chainage[-1]
            + _haversine_feet(
                float(coords[i - 1][0]),
                float(coords[i - 1][1]),
                float(coords[i][0]),
                float(coords[i][1]),
            )
        )
    return chainage


def _latlon_to_local_xy_feet(lat: float, lon: float, lat0: float, lon0: float) -> Tuple[float, float]:
    lat_scale = 364000.0
    lon_scale = 364000.0 * math.cos(math.radians(lat0))
    x = (lon - lon0) * lon_scale
    y = (lat - lat0) * lat_scale
    return x, y


def _project_point_to_segment_ft(
    point_xy: Tuple[float, float],
    start_xy: Tuple[float, float],
    end_xy: Tuple[float, float],
) -> Tuple[float, float, Tuple[float, float]]:
    px, py = point_xy
    ax, ay = start_xy
    bx, by = end_xy
    dx = bx - ax
    dy = by - ay
    seg_len_sq = dx * dx + dy * dy
    if seg_len_sq <= 1e-9:
        dist = math.hypot(px - ax, py - ay)
        return 0.0, dist, (ax, ay)
    t = ((px - ax) * dx + (py - ay) * dy) / seg_len_sq
    t = max(0.0, min(1.0, t))
    qx = ax + t * dx
    qy = ay + t * dy
    dist = math.hypot(px - qx, py - qy)
    return t, dist, (qx, qy)


def _route_segment_bearings(route_coords: Sequence[Sequence[float]]) -> List[float]:
    if len(route_coords) < 2:
        return []
    lat0 = float(route_coords[0][0])
    lon0 = float(route_coords[0][1])
    pts = [_latlon_to_local_xy_feet(float(lat), float(lon), lat0, lon0) for lat, lon in route_coords]
    bearings: List[float] = []
    for i in range(1, len(pts)):
        dx = pts[i][0] - pts[i - 1][0]
        dy = pts[i][1] - pts[i - 1][1]
        bearings.append(math.atan2(dy, dx))
    return bearings


def _bearing_delta_degrees(a: float, b: float) -> float:
    delta = abs(math.degrees(b - a))
    while delta > 180.0:
        delta = abs(delta - 360.0)
    return delta


def _project_chainage_to_route(route_coords: Sequence[Sequence[float]], chainage: Sequence[float], distance_ft: float) -> Dict[str, Any]:
    if not route_coords:
        return {"segment_index": 0, "segment_ratio": 0.0, "actual_segment_index": 0, "actual_segment_ratio": 0.0, "virtual_segment_count": 1, "lat": 0.0, "lon": 0.0}
    d = max(0.0, min(float(distance_ft), float(chainage[-1])))
    if len(route_coords) == 1:
        return {"segment_index": 0, "segment_ratio": 0.0, "actual_segment_index": 0, "actual_segment_ratio": 0.0, "virtual_segment_count": 1, "lat": float(route_coords[0][0]), "lon": float(route_coords[0][1])}
    for idx in range(1, len(chainage)):
        seg_start = float(chainage[idx - 1])
        seg_end = float(chainage[idx])
        if d <= seg_end or idx == len(chainage) - 1:
            seg_len = max(seg_end - seg_start, 1e-9)
            ratio = (d - seg_start) / seg_len
            lat, lon = _interpolate_point(route_coords[idx - 1], route_coords[idx], ratio)
            virtual_meta = _virtualize_segment_index(chainage, idx - 1, ratio)
            return {
                "segment_index": int(virtual_meta["virtual_segment_index"]),
                "segment_ratio": float(virtual_meta["virtual_segment_ratio"]),
                "actual_segment_index": idx - 1,
                "actual_segment_ratio": ratio,
                "virtual_segment_count": int(virtual_meta["virtual_segment_count"]),
                "lat": float(lat),
                "lon": float(lon),
            }
    lat, lon = route_coords[-1]
    last_actual_index = max(0, len(route_coords) - 2)
    virtual_meta = _virtualize_segment_index(chainage, last_actual_index, 1.0)
    return {"segment_index": int(virtual_meta["virtual_segment_index"]), "segment_ratio": float(virtual_meta["virtual_segment_ratio"]), "actual_segment_index": last_actual_index, "actual_segment_ratio": 1.0, "virtual_segment_count": int(virtual_meta["virtual_segment_count"]), "lat": float(lat), "lon": float(lon)}

def _route_shape_signature(route_coords: Sequence[Sequence[float]], chainage: Sequence[float]) -> Dict[str, Any]:
    bearings = _route_segment_bearings(route_coords)
    bend_positions: List[float] = []
    bend_strengths: List[float] = []
    for i in range(1, len(bearings)):
        delta = _bearing_delta_degrees(bearings[i - 1], bearings[i])
        if delta >= 12.0:
            bend_positions.append(float(chainage[i]))
            bend_strengths.append(delta)
    return {
        "bend_positions": bend_positions,
        "bend_strengths": bend_strengths,
    }


def _interpolate_point(a: Sequence[float], b: Sequence[float], ratio: float) -> List[float]:
    ratio = max(0.0, min(1.0, float(ratio)))
    return [
        float(a[0]) + (float(b[0]) - float(a[0])) * ratio,
        float(a[1]) + (float(b[1]) - float(a[1])) * ratio,
    ]


def _point_at_distance(route_coords: Sequence[Sequence[float]], chainage: Sequence[float], distance_ft: float) -> List[float]:
    if not route_coords:
        raise ValueError("Route is empty.")
    if len(route_coords) == 1:
        return [float(route_coords[0][0]), float(route_coords[0][1])]

    d = max(0.0, min(float(distance_ft), float(chainage[-1])))
    for idx in range(1, len(chainage)):
        seg_start = float(chainage[idx - 1])
        seg_end = float(chainage[idx])
        if d <= seg_end or idx == len(chainage) - 1:
            seg_len = max(seg_end - seg_start, 1e-9)
            ratio = (d - seg_start) / seg_len
            return _interpolate_point(route_coords[idx - 1], route_coords[idx], ratio)

    last = route_coords[-1]
    return [float(last[0]), float(last[1])]


def _clip_route_segment(route_coords: Sequence[Sequence[float]], start_ft: float, end_ft: float) -> List[List[float]]:
    if len(route_coords) < 2:
        return []
    chainage = _route_chainage(route_coords)
    total = float(chainage[-1])
    start_d = max(0.0, min(float(start_ft), total))
    end_d = max(0.0, min(float(end_ft), total))
    if end_d <= start_d:
        return []

    segment = [_point_at_distance(route_coords, chainage, start_d)]
    for idx in range(1, len(chainage) - 1):
        current_d = float(chainage[idx])
        if start_d < current_d < end_d:
            segment.append([float(route_coords[idx][0]), float(route_coords[idx][1])])
    segment.append(_point_at_distance(route_coords, chainage, end_d))

    cleaned: List[List[float]] = []
    for pt in segment:
        if not cleaned or abs(cleaned[-1][0] - pt[0]) > 1e-9 or abs(cleaned[-1][1] - pt[1]) > 1e-9:
            cleaned.append(pt)
    return cleaned if len(cleaned) >= 2 else []





def _station_offsets_from_rows(rows: Sequence[Dict[str, Any]]) -> List[float]:
    station_values = [float(row.get("station_ft")) for row in rows if row.get("station_ft") is not None]
    if not station_values:
        return []
    origin = min(station_values)
    return [max(0.0, float(value) - origin) for value in station_values]


def _distance_to_nearest(target_ft: float, candidates_ft: Sequence[float]) -> float:
    if not candidates_ft:
        return float("inf")
    return min(abs(float(target_ft) - float(candidate)) for candidate in candidates_ft)


def _candidate_anchor_starts(
    route_coords: Sequence[Sequence[float]],
    route_total_ft: float,
    span_ft: float,
    mapping: Dict[str, Any],
    rows: Sequence[Dict[str, Any]],
) -> List[float]:
    if route_total_ft <= 0.0:
        return [0.0]

    usable_span = max(0.0, min(float(span_ft or 0.0), float(route_total_ft)))
    max_start = max(0.0, float(route_total_ft) - usable_span)
    chainage = _route_chainage(route_coords) if route_coords else [0.0]
    station_offsets = _station_offsets_from_rows(rows)

    candidates = {0.0, round(max_start, 2)}
    if max_start > 0.0:
        candidates.add(round(max_start / 2.0, 2))

    min_station = mapping.get("min_station_ft")
    max_station = mapping.get("max_station_ft")
    if min_station is not None and max_station is not None:
        min_station = float(min_station)
        max_station = float(max_station)
        if 0.0 <= min_station <= route_total_ft and 0.0 <= max_station <= route_total_ft and max_station > min_station:
            candidates.add(round(max(0.0, min(min_station, max_start)), 2))

    probe_offsets = {0.0}
    if station_offsets:
        probe_offsets.update(station_offsets)
        probe_offsets.add(round(station_offsets[-1] / 2.0, 2))
        if len(station_offsets) >= 3:
            probe_offsets.add(round(station_offsets[len(station_offsets) // 2], 2))

    # Vertex-aligned probes
    for vertex_ft in chainage:
        for offset_ft in probe_offsets:
            start_ft = max(0.0, min(float(vertex_ft) - float(offset_ft), max_start))
            candidates.add(round(start_ft, 2))

    # Segment interior probes at quarter points to support real projection-based anchoring.
    for idx in range(1, len(chainage)):
        seg_start = float(chainage[idx - 1])
        seg_end = float(chainage[idx])
        for frac in (0.25, 0.5, 0.75):
            probe_chain = seg_start + (seg_end - seg_start) * frac
            for offset_ft in probe_offsets:
                start_ft = max(0.0, min(probe_chain - float(offset_ft), max_start))
                candidates.add(round(start_ft, 2))

    if max_start > 0.0:
        step = max(8.0, min(25.0, usable_span / 10.0 if usable_span > 0.0 else route_total_ft / 30.0))
        probe = 0.0
        while probe <= max_start + 1e-9:
            candidates.add(round(min(probe, max_start), 2))
            probe += step

    return sorted(candidates)


def _anchor_profile_for_start(
    route_coords: Sequence[Sequence[float]],
    route_total_ft: float,
    span_ft: float,
    start_ft: float,
    rows: Sequence[Dict[str, Any]],
    mapping: Dict[str, Any],
) -> Dict[str, Any]:
    usable_span = max(0.0, min(float(span_ft or 0.0), float(route_total_ft)))
    max_start = max(0.0, float(route_total_ft) - usable_span)
    start_ft = max(0.0, min(float(start_ft), max_start))
    end_ft = max(0.0, min(start_ft + usable_span, float(route_total_ft)))

    chainage = _route_chainage(route_coords)
    station_offsets = _station_offsets_from_rows(rows)
    mapped_positions = [max(0.0, min(start_ft + offset, route_total_ft)) for offset in station_offsets]

    projected_points = [_project_chainage_to_route(route_coords, chainage, pos) for pos in mapped_positions]
    segment_indices = [int(p["segment_index"]) for p in projected_points]
    segment_ratios = [float(p["segment_ratio"]) for p in projected_points]

    distinct_segment_count = len(set(segment_indices))
    row_count = max(len(rows), 1)

    edge_clearance_ft = min(start_ft, max(0.0, route_total_ft - end_ft))
    start_vertex_distance = _distance_to_nearest(start_ft, list(chainage))
    end_vertex_distance = _distance_to_nearest(end_ft, list(chainage))

    segment_balance = 0.0
    if projected_points:
        interior_hits = sum(1 for r in segment_ratios if 0.08 <= r <= 0.92)
        segment_balance = interior_hits / len(projected_points)

    segment_steps: List[int] = []
    for i in range(1, len(segment_indices)):
        segment_steps.append(abs(segment_indices[i] - segment_indices[i - 1]))
    max_segment_jump = max(segment_steps) if segment_steps else 0
    jump_penalty = min(1.0, max_segment_jump / 3.0) if max_segment_jump > 0 else 0.0

    shape_sig = _route_shape_signature(route_coords, chainage)
    bend_positions = list(shape_sig["bend_positions"])
    bend_strengths = list(shape_sig["bend_strengths"])
    window_bend_strength = 0.0
    covered_bends = 0
    for pos, strength in zip(bend_positions, bend_strengths):
        if start_ft <= pos <= end_ft:
            covered_bends += 1
            window_bend_strength += float(strength)
    bend_density = 0.0
    if usable_span > 0.0:
        bend_density = min(1.0, window_bend_strength / max(35.0, usable_span * 0.18))

    endpoint_alignment = 0.0
    if projected_points:
        endpoint_alignment = 1.0 - min(1.0, ((start_vertex_distance + end_vertex_distance) / max(30.0, usable_span * 0.15)) / 2.0)

    return {
        "start_ft": round(start_ft, 2),
        "end_ft": round(end_ft, 2),
        "mapped_positions": [round(value, 2) for value in mapped_positions],
        "projected_points": [
            {
                "segment_index": int(point["segment_index"]),
                "segment_ratio": round(float(point["segment_ratio"]), 4),
                "actual_segment_index": int(point.get("actual_segment_index", point["segment_index"])),
                "actual_segment_ratio": round(float(point.get("actual_segment_ratio", point["segment_ratio"])), 4),
                "virtual_segment_count": int(point.get("virtual_segment_count", 1)),
                "lat": round(float(point["lat"]), 8),
                "lon": round(float(point["lon"]), 8),
            }
            for point in projected_points
        ],
        "segment_indices": segment_indices,
        "segment_ratios": [round(v, 4) for v in segment_ratios],
        "start_vertex_distance_ft": round(start_vertex_distance if math.isfinite(start_vertex_distance) else 999999.0, 2),
        "end_vertex_distance_ft": round(end_vertex_distance if math.isfinite(end_vertex_distance) else 999999.0, 2),
        "edge_clearance_ft": round(edge_clearance_ft, 2),
        "distinct_segment_count": distinct_segment_count,
        "row_count": row_count,
        "segment_balance_fit": round(segment_balance, 6),
        "max_segment_jump": int(max_segment_jump),
        "jump_penalty": round(jump_penalty, 6),
        "covered_bends": int(covered_bends),
        "bend_density_fit": round(bend_density, 6),
        "endpoint_alignment_fit": round(max(0.0, endpoint_alignment), 6),
    }


def _score_anchor_start(
    start_ft: float,
    route_coords: Sequence[Sequence[float]],
    route_total_ft: float,
    span_ft: float,
    mapping: Dict[str, Any],
    ranking: Dict[str, Any],
    rows: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    usable_span = max(0.0, min(float(span_ft or 0.0), float(route_total_ft)))
    route_score = float(ranking.get("score", 0.0) or 0.0)
    profile = _anchor_profile_for_start(route_coords, route_total_ft, span_ft, start_ft, rows, mapping)

    start_ft = float(profile["start_ft"])
    end_ft = float(profile["end_ft"])

    span_fit = 1.0
    if span_ft > 0.0 and route_total_ft > 0.0:
        span_fit = min(span_ft, route_total_ft) / max(span_ft, route_total_ft)

    route_length_fit = 0.0
    if route_total_ft > 0.0 and span_ft > 0.0:
        relative_gap = abs(route_total_ft - span_ft) / max(span_ft, 1.0)
        route_length_fit = max(0.0, 1.0 - relative_gap)

    endpoint_alignment_fit = float(profile.get("endpoint_alignment_fit", 0.0) or 0.0)
    segment_balance_fit = float(profile.get("segment_balance_fit", 0.0) or 0.0)
    bend_density_fit = float(profile.get("bend_density_fit", 0.0) or 0.0)
    edge_clearance_ft = float(profile["edge_clearance_ft"])
    if route_total_ft <= usable_span + 1.0:
        edge_fit = 1.0
    else:
        edge_fit = min(1.0, edge_clearance_ft / max(35.0, usable_span * 0.12))

    jump_penalty = float(profile.get("jump_penalty", 0.0) or 0.0)

    anchor_method = "projection_window_search"
    anchor_reasons: List[str] = []
    absolute_station_fit = 0.0

    min_station = mapping.get("min_station_ft")
    max_station = mapping.get("max_station_ft")
    if min_station is not None and max_station is not None:
        min_station = float(min_station)
        max_station = float(max_station)
        if 0.0 <= min_station <= route_total_ft and 0.0 <= max_station <= route_total_ft and max_station > min_station:
            expected_start = min_station
            expected_end = max_station
            tolerance = max(20.0, usable_span * 0.08)
            start_fit = max(0.0, 1.0 - (abs(start_ft - expected_start) / tolerance))
            end_fit = max(0.0, 1.0 - (abs(end_ft - expected_end) / tolerance))
            absolute_station_fit = (start_fit + end_fit) / 2.0
            if absolute_station_fit >= 0.85:
                anchor_method = "absolute_station_projection"
                anchor_reasons.append("Absolute station feet aligned closely with the projected route window.")

    anchor_fit = (
        0.30 * endpoint_alignment_fit
        + 0.25 * segment_balance_fit
        + 0.15 * bend_density_fit
        + 0.15 * edge_fit
        + 0.15 * absolute_station_fit
    )

    subsection_score = (
        0.35 * span_fit
        + 0.25 * route_length_fit
        + 0.40 * anchor_fit
        - 0.18 * jump_penalty
    )
    subsection_score = max(0.0, min(1.0, subsection_score))

    combined_score = max(0.0, min(1.0, (0.55 * route_score) + (0.45 * subsection_score)))

    if not anchor_reasons:
        anchor_reasons.extend(
            [
                f"Projected station offsets across {int(profile.get('distinct_segment_count', 0) or 0)} route segment(s).",
                f"Segment-balance fit {round(segment_balance_fit, 3)} and endpoint-alignment fit {round(endpoint_alignment_fit, 3)} drove anchor selection.",
            ]
        )
        if bend_density_fit > 0.0:
            anchor_reasons.append(f"Window bend-density fit {round(bend_density_fit, 3)} favored geometry that matched the bore span shape.")
        if jump_penalty > 0.0:
            anchor_reasons.append(f"Large segment jumps were penalized ({round(jump_penalty, 3)}).")

    return {
        "start_ft": round(start_ft, 2),
        "end_ft": round(end_ft, 2),
        "anchor_fit": round(anchor_fit, 6),
        "anchor_method": anchor_method,
        "anchor_reasons": anchor_reasons,
        "subsection_score": round(subsection_score, 6),
        "combined_score": round(combined_score, 6),
        "score_components": {
            "route_score": round(route_score, 6),
            "span_fit": round(span_fit, 6),
            "route_length_fit": round(route_length_fit, 6),
            "endpoint_alignment_fit": round(endpoint_alignment_fit, 6),
            "segment_balance_fit": round(segment_balance_fit, 6),
            "bend_density_fit": round(bend_density_fit, 6),
            "edge_fit": round(edge_fit, 6),
            "absolute_station_fit": round(absolute_station_fit, 6),
            "jump_penalty": round(jump_penalty, 6),
        },
        "anchor_profile": profile,
    }
def _coerce_float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except Exception:
        text = "".join(ch for ch in str(value) if ch.isdigit() or ch in ".-")
        if not text:
            return None
        try:
            return float(text)
        except Exception:
            return None


def _read_bore_log_rows(file_bytes: bytes, filename: str) -> List[Dict[str, Any]]:
    df = pd.read_excel(io.BytesIO(file_bytes))
    df.columns = [str(col).strip().lower() for col in df.columns]

    required = {"station", "depth", "boc"}
    if not required.issubset(set(df.columns)):
        raise ValueError(f"{filename} must contain columns: station, depth, boc")

    rows: List[Dict[str, Any]] = []
    for _, rec in df.iterrows():
        station_text = _normalize_station_text(rec.get("station"))
        station_ft = _station_to_feet(station_text)
        if station_ft is None:
            continue
        rows.append(
            {
                "station": station_text,
                "station_ft": float(station_ft),
                "depth_ft": _coerce_float(rec.get("depth")),
                "boc_ft": _coerce_float(rec.get("boc")),
                "date": str(rec.get("date") or "").strip(),
                "crew": str(rec.get("crew") or "").strip(),
                "print": str(rec.get("print") or "").strip(),
                "notes": str(rec.get("notes") or "").strip(),
                "source_file": _safe_filename(filename),
            }
        )

    rows.sort(key=lambda r: float(r["station_ft"]))
    return rows


def _group_rows_for_matching(rows: Sequence[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    if not rows:
        return []

    def _normalized_text(value: Any) -> str:
        return str(value or "").strip()

    def _group_key(row: Dict[str, Any]) -> Tuple[str, Tuple[str, ...]]:
        source_file = _normalized_text(row.get("source_file"))
        print_tokens = tuple(sorted(_parse_print_tokens(row.get("print"))))
        return source_file, print_tokens

    def _step_history(group: Sequence[Dict[str, Any]]) -> List[float]:
        steps: List[float] = []
        for idx in range(1, len(group)):
            prev_ft = group[idx - 1].get("station_ft")
            curr_ft = group[idx].get("station_ft")
            if prev_ft is None or curr_ft is None:
                continue
            delta = float(curr_ft) - float(prev_ft)
            if delta > 0.0:
                steps.append(delta)
        return steps

    def _median_step(group: Sequence[Dict[str, Any]]) -> float:
        steps = sorted(_step_history(group))
        if not steps:
            return 50.0
        mid = len(steps) // 2
        if len(steps) % 2 == 1:
            return float(steps[mid])
        return float((steps[mid - 1] + steps[mid]) / 2.0)

    def _is_new_group(previous: Dict[str, Any], current: Dict[str, Any], active_group: Sequence[Dict[str, Any]]) -> bool:
        if _group_key(previous) != _group_key(current):
            return True

        prev_station = previous.get("station_ft")
        curr_station = current.get("station_ft")
        if prev_station is None or curr_station is None:
            return True

        station_delta = float(curr_station) - float(prev_station)
        if station_delta <= 0.0:
            return True

        previous_crew = _normalized_text(previous.get("crew"))
        current_crew = _normalized_text(current.get("crew"))
        if previous_crew and current_crew and previous_crew != current_crew:
            return True

        previous_date = _normalized_text(previous.get("date"))
        current_date = _normalized_text(current.get("date"))
        if previous_date and current_date and previous_date != current_date:
            return True

        median_step = _median_step(active_group)
        max_expected_gap = max(150.0, median_step * 3.5)
        if station_delta > max_expected_gap:
            return True

        return False

    sorted_rows = sorted(
        [dict(row) for row in rows],
        key=lambda row: (
            _normalized_text(row.get("source_file")),
            tuple(sorted(_parse_print_tokens(row.get("print")))),
            float(row.get("station_ft") or 0.0),
            _normalized_text(row.get("date")),
            _normalized_text(row.get("crew")),
        ),
    )

    groups: List[List[Dict[str, Any]]] = []
    current_group: List[Dict[str, Any]] = [sorted_rows[0]]

    for row in sorted_rows[1:]:
        previous = current_group[-1]
        if _is_new_group(previous, row, current_group):
            groups.append(current_group)
            current_group = [row]
        else:
            current_group.append(row)

    groups.append(current_group)
    return groups


def _infer_expected_roles(group_rows: Sequence[Dict[str, Any]], expected_length_ft: float) -> List[str]:
    notes_blob = " ".join(str(row.get("notes") or "") for row in group_rows).lower()
    source_blob = " ".join(
        [
            str(group_rows[0].get("source_file") or ""),
            str(group_rows[0].get("print") or ""),
            notes_blob,
        ]
    ).lower()

    expected: List[str] = []
    if "vacant" in source_blob:
        expected.append("vacant_pipe")
    if "drop" in source_blob and "house" in source_blob:
        expected.append("house_drop")
    if "tail" in source_blob:
        expected.append("terminal_tail")
    if "backbone" in source_blob:
        expected.append("backbone")
    if "cable" in source_blob or "fiber" in source_blob:
        expected.append("underground_cable")

    if expected_length_ft <= 160:
        expected.extend(["house_drop", "vacant_pipe", "terminal_tail"])
    elif expected_length_ft <= 1200:
        expected.extend(["terminal_tail", "underground_cable", "vacant_pipe"])
    else:
        expected.extend(["underground_cable", "backbone", "terminal_tail"])

    seen = set()
    ordered: List[str] = []
    for item in expected:
        if item not in seen:
            ordered.append(item)
            seen.add(item)
    return ordered


def _route_type_bonus(route_role: str, expected_roles: Sequence[str]) -> float:
    normalized = str(route_role or "other").strip().lower()
    if not expected_roles:
        return 0.0
    if normalized == expected_roles[0]:
        return 0.18
    if normalized in expected_roles[:2]:
        return 0.10
    if normalized in expected_roles:
        return 0.04
    return 0.0




def _parse_print_tokens(value: Any) -> List[str]:
    raw = str(value or "").strip()
    if not raw:
        return []
    parts = [part.strip() for part in raw.replace(";", ",").split(",")]
    return [part for part in parts if part]


def _collect_group_print_tokens(group_rows: Sequence[Dict[str, Any]]) -> List[str]:
    seen: List[str] = []
    for row in group_rows:
        for token in _parse_print_tokens(row.get("print")):
            if token not in seen:
                seen.append(token)
    return seen



def _route_filter_for_print_tokens(print_tokens: Sequence[str], route_catalog: Sequence[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    if not print_tokens:
        return list(route_catalog), {
            "applied": False,
            "mode": "none",
            "print_tokens": [],
            "sheet_numbers": [],
            "street_hints": [],
            "allowed_route_ids": [],
            "reason": "No print tokens were present on the bore-log group.",
        }

    hint_meta = _print_sheet_hints(print_tokens)
    allowed_route_ids = list(hint_meta.get("allowed_route_ids") or [])
    street_hints = list(hint_meta.get("street_hints") or [])
    sheet_numbers = list(hint_meta.get("sheet_numbers") or [])

    if not allowed_route_ids:
        return list(route_catalog), {
            "applied": False,
            "mode": "none",
            "print_tokens": list(print_tokens),
            "sheet_numbers": sheet_numbers,
            "street_hints": street_hints,
            "allowed_route_ids": [],
            "reason": "No print-to-street extraction hints were available for this print set.",
        }

    allowed_set = set(allowed_route_ids)
    filtered = [route for route in route_catalog if str(route.get("route_id") or "") in allowed_set]

    if not filtered:
        return list(route_catalog), {
            "applied": False,
            "mode": "print_to_street_extraction",
            "print_tokens": list(print_tokens),
            "sheet_numbers": sheet_numbers,
            "street_hints": street_hints,
            "allowed_route_ids": allowed_route_ids,
            "reason": "Print-to-street extraction resolved to route ids, but none were present in the current KMZ catalog.",
        }

    return filtered, {
        "applied": True,
        "mode": "print_to_street_extraction",
        "print_tokens": list(print_tokens),
        "sheet_numbers": sheet_numbers,
        "street_hints": street_hints,
        "allowed_route_ids": allowed_route_ids,
        "reason": "Candidate routes were narrowed by print-to-street extraction calibrated from the detailed engineering sheets.",
    }


def _decorate_route_id_disambiguation(
    plausible_routes: Sequence[Dict[str, Any]],
    span_ft: float,
    filter_meta: Dict[str, Any],
) -> List[Dict[str, Any]]:
    decorated: List[Dict[str, Any]] = [dict(route) for route in plausible_routes]
    if not decorated:
        return decorated

    allowed_route_ids = [str(value or "").strip() for value in (filter_meta.get("allowed_route_ids") or []) if str(value or "").strip()]
    allowed_route_id_set = set(allowed_route_ids)

    family_map: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for route in decorated:
        family_key = (
            str(route.get("route_name") or "").strip().lower(),
            str(route.get("route_role") or "").strip().lower(),
        )
        family_map.setdefault(family_key, []).append(route)

    for family_routes in family_map.values():
        if not family_routes:
            continue

        best_length_gap = min(abs(float(route.get("length_ft", 0.0) or 0.0) - float(span_ft or 0.0)) for route in family_routes)
        best_spatial_hint = max(float(route.get("_spatial_hint_score", 0.0) or 0.0) for route in family_routes)
        shortest_length = min(float(route.get("length_ft", 0.0) or 0.0) for route in family_routes)
        longest_length = max(float(route.get("length_ft", 0.0) or 0.0) for route in family_routes)

        for route in family_routes:
            route_length_ft = float(route.get("length_ft", 0.0) or 0.0)
            length_gap = abs(route_length_ft - float(span_ft or 0.0))
            spatial_hint = float(route.get("_spatial_hint_score", 0.0) or 0.0)
            route_id = str(route.get("route_id") or "").strip()

            exact_allowed_bonus = 0.0
            if len(allowed_route_id_set) == 1 and route_id in allowed_route_id_set:
                exact_allowed_bonus = 0.14

            family_length_bonus = 0.0
            if len(family_routes) > 1 and best_length_gap >= 0.0:
                tolerance_ft = max(60.0, float(span_ft or 0.0) * 0.20)
                family_length_bonus = max(0.0, 1.0 - ((length_gap - best_length_gap) / tolerance_ft)) * 0.10

            family_spatial_bonus = 0.0
            if len(family_routes) > 1 and best_spatial_hint > 0.0:
                family_spatial_bonus = max(0.0, min(spatial_hint, best_spatial_hint) / best_spatial_hint) * 0.05

            corridor_fit_bonus = 0.0
            if len(family_routes) > 1 and longest_length > shortest_length and float(span_ft or 0.0) > 0.0:
                # Prefer the corridor whose total length is proportionally closest to the bore span
                relative_fit = min(route_length_ft, float(span_ft)) / max(route_length_ft, float(span_ft))
                corridor_fit_bonus = max(0.0, min(1.0, relative_fit)) * 0.04

            total_bonus = exact_allowed_bonus + family_length_bonus + family_spatial_bonus + corridor_fit_bonus
            route["_route_id_disambiguation_bonus"] = round(total_bonus, 6)
            route["_route_id_disambiguation_meta"] = {
                "family_size": len(family_routes),
                "best_length_gap_ft": round(best_length_gap, 2),
                "route_length_gap_ft": round(length_gap, 2),
                "exact_allowed_bonus": round(exact_allowed_bonus, 6),
                "family_length_bonus": round(family_length_bonus, 6),
                "family_spatial_bonus": round(family_spatial_bonus, 6),
                "corridor_fit_bonus": round(corridor_fit_bonus, 6),
            }

    return decorated

def _score_route_for_group(group_rows: Sequence[Dict[str, Any]], route: Dict[str, Any]) -> Dict[str, Any]:
    start_ft = float(group_rows[0].get("station_ft") or 0.0)
    end_ft = float(group_rows[-1].get("station_ft") or start_ft)
    expected_length_ft = max(0.0, end_ft - start_ft)

    route_length_ft = float(route.get("length_ft", 0.0) or 0.0)
    length_gap = abs(route_length_ft - expected_length_ft)

    if expected_length_ft <= 0.0 or route_length_ft <= 0.0:
        closeness_ratio = 0.0
        length_score = 0.0
        oversize_penalty = 0.0
    else:
        shorter = min(expected_length_ft, route_length_ft)
        longer = max(expected_length_ft, route_length_ft)
        closeness_ratio = shorter / longer

        # Make route length fit the dominant signal.
        # Exact or near-exact routes should rise hard.
        # Oversized routes should get hit much harder than before.
        length_score = closeness_ratio ** 2.35

        if route_length_ft > expected_length_ft:
            oversize_ratio = route_length_ft / max(expected_length_ft, 1.0)
            oversize_penalty = min(0.42, max(0.0, (oversize_ratio - 1.0) * 0.18))
        else:
            oversize_penalty = 0.0

        length_score = max(0.0, length_score - oversize_penalty)

    expected_roles = _infer_expected_roles(group_rows, expected_length_ft)
    type_bonus = _route_type_bonus(str(route.get("route_role") or ""), expected_roles)

    point_count = float(route.get("point_count", 0) or 0)
    geometry_bonus = 0.02 if point_count >= 3 else 0.0

    score = round(min(1.0, length_score + type_bonus + geometry_bonus), 6)
    reason_parts = [
        f"Expected span {round(expected_length_ft, 2)} ft vs route length {round(route_length_ft, 2)} ft",
        f"Length closeness ratio {round(closeness_ratio, 4)}",
        f"Route role {route.get('route_role', 'other')}",
    ]
    if route_length_ft > expected_length_ft and expected_length_ft > 0.0:
        reason_parts.append("Oversized route was penalized to avoid loose span matches.")
    if expected_roles:
        reason_parts.append(f"Expected roles {', '.join(expected_roles)}")

    return {
        "route_id": route.get("route_id"),
        "route_name": route.get("route_name"),
        "source_folder": route.get("source_folder"),
        "route_role": route.get("route_role"),
        "route_length_ft": round(route_length_ft, 2),
        "expected_span_ft": round(expected_length_ft, 2),
        "length_gap_ft": round(length_gap, 2),
        "score": score,
        "reason": " | ".join(reason_parts),
    }


def _normalize_bore_group(group_rows: Sequence[Dict[str, Any]], group_idx: int) -> Dict[str, Any]:
    rows = [dict(row) for row in group_rows]
    station_values = [float(row["station_ft"]) for row in rows if row.get("station_ft") is not None]
    warnings: List[str] = []
    if not station_values:
        warnings.append("No normalized station values were available for this bore-log group.")
    monotonic_breaks = 0
    duplicate_count = 0
    for idx in range(1, len(station_values)):
        if station_values[idx] < station_values[idx - 1]:
            monotonic_breaks += 1
        if abs(station_values[idx] - station_values[idx - 1]) < 1e-9:
            duplicate_count += 1
    if monotonic_breaks:
        warnings.append(f"Station order contains {monotonic_breaks} non-monotonic break(s).")
    if duplicate_count:
        warnings.append(f"Station order contains {duplicate_count} duplicate station value(s).")

    min_station = min(station_values) if station_values else None
    max_station = max(station_values) if station_values else None
    span_ft = (max_station - min_station) if (min_station is not None and max_station is not None) else None

    # Derive evidence_layer_id: stable hash of source_file + print_tokens + date.
    # Groups sharing a layer can merge; groups with different layers must stay separate.
    _el_source = str(rows[0].get("source_file") or "").strip().lower() if rows else ""
    _el_print = "|".join(sorted(_collect_group_print_tokens(rows)))
    _el_date = str(rows[0].get("date") or "").strip().lower() if rows else ""
    _el_raw = f"{_el_source}|{_el_print}|{_el_date}"
    evidence_layer_id = hashlib.sha256(_el_raw.encode()).hexdigest()[:16]

    return {
        "group_id": f"group_{group_idx + 1}",
        "group_index": group_idx,
        "source_file": str(rows[0].get("source_file") or "") if rows else "",
        "print_tokens": list(_collect_group_print_tokens(rows)),
        "row_count": len(rows),
        "min_station_ft": round(float(min_station), 2) if min_station is not None else None,
        "max_station_ft": round(float(max_station), 2) if max_station is not None else None,
        "span_ft": round(float(span_ft), 2) if span_ft is not None else None,
        "station_rows": [dict(row) for row in rows],
        "normalization_warnings": warnings,
        "evidence_layer_id": evidence_layer_id,
        "evidence_layer_source_file": str(rows[0].get("source_file") or "") if rows else "",
        "evidence_layer_date": str(rows[0].get("date") or "") if rows else "",
    }


def _build_candidate_pool_for_group(normalized_group: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    route_catalog = STATE.get("route_catalog", []) or []
    if not route_catalog:
        raise ValueError("No route catalog loaded.")

    print_tokens = list(normalized_group.get("print_tokens") or [])
    filtered_routes, filter_meta = _route_filter_for_print_tokens(print_tokens, route_catalog)
    span_ft = float(normalized_group.get("span_ft") or 0.0)
    source_file = str(normalized_group.get("source_file") or "").lower()
    spatial_context = _infer_group_spatial_context(normalized_group)

    plausible_routes: List[Dict[str, Any]] = []
    rejected_length_routes: List[Dict[str, Any]] = []

    for route in filtered_routes:
        route_length_ft = float(route.get("length_ft", 0.0) or 0.0)
        deferred_oversized_reason = None

        if span_ft > 0.0 and route_length_ft > 0.0:
            min_allowed_ft = span_ft * 0.70
            max_allowed_ft = span_ft * 3.50

            if route_length_ft < min_allowed_ft:
                rejected_length_routes.append({
                    "route_id": route.get("route_id"),
                    "route_name": route.get("route_name"),
                    "route_length_ft": round(route_length_ft, 2),
                    "reason": f"undersized_hard_gate_lt_{round(min_allowed_ft, 2)}",
                })
                continue

            if route_length_ft > max_allowed_ft:
                # Oversized corridors can still contain a valid anchored subsection.
                # Keep them in the candidate pool and let subsection anchoring +
                # downstream validation decide whether the match is truly usable.
                deferred_oversized_reason = f"oversized_hard_gate_gt_{round(max_allowed_ft, 2)}"
            else:
                deferred_oversized_reason = None

        plausible_route = dict(route)
        route_tokens = f"{plausible_route.get('route_name', '')} {plausible_route.get('source_folder', '')}".lower()
        name_hint_score = 0.0
        if source_file and route_tokens:
            for token in [tok for tok in source_file.replace('-', ' ').replace('_', ' ').split() if len(tok) >= 4]:
                if token in route_tokens:
                    name_hint_score += 0.03

        route_coords = plausible_route.get("coords") or []
        route_bbox = _route_bbox(route_coords)
        route_centroid = _route_centroid(route_coords)

        spatial_filter = {
            "applied": False,
            "passed": True,
            "reason": "no_spatial_context",
            "centroid_distance_ft": None,
        }

        spatial_hint_score = 0.0
        if spatial_context.get("has_spatial_context"):
            spatial_filter["applied"] = True
            passes_bbox = _bbox_contains_with_buffer(
                spatial_context.get("bbox"),
                route_bbox,
                float(spatial_context.get("lat_buffer_deg") or 0.0),
                float(spatial_context.get("lon_buffer_deg") or 0.0),
            )

            centroid_distance_ft = None
            if route_centroid and spatial_context.get("centroid"):
                centroid_distance_ft = _haversine_feet(
                    float(route_centroid[0]),
                    float(route_centroid[1]),
                    float(spatial_context["centroid"][0]),
                    float(spatial_context["centroid"][1]),
                )
                spatial_filter["centroid_distance_ft"] = round(centroid_distance_ft, 2)

            if not passes_bbox:
                if centroid_distance_ft is None or centroid_distance_ft > 700.0:
                    continue
                spatial_filter["passed"] = True
                spatial_filter["reason"] = "centroid_fallback"
            else:
                spatial_filter["reason"] = "bbox_overlap"

            if centroid_distance_ft is not None:
                spatial_hint_score = max(0.0, 1.0 - (centroid_distance_ft / 900.0)) * 0.18

        plausible_route["_name_hint_score"] = round(min(name_hint_score, 0.12), 3)
        plausible_route["_spatial_hint_score"] = round(spatial_hint_score, 6)
        plausible_route["_spatial_filter"] = spatial_filter
        plausible_route["_hard_length_gate"] = {
            "applied": span_ft > 0.0 and route_length_ft > 0.0,
            "min_allowed_ft": round(span_ft * 0.70, 2) if span_ft > 0.0 else None,
            "max_allowed_ft": round(span_ft * 3.50, 2) if span_ft > 0.0 else None,
            "passed": deferred_oversized_reason is None,
            "deferred_to_subsection_anchor": deferred_oversized_reason is not None,
            "reason": deferred_oversized_reason,
        }
        plausible_routes.append(plausible_route)

    if not plausible_routes:
        plausible_routes = [dict(route) for route in filtered_routes]
        for route in plausible_routes:
            route["_name_hint_score"] = 0.0
            route["_spatial_hint_score"] = 0.0
            route["_spatial_filter"] = {
                "applied": False,
                "passed": True,
                "reason": "fallback_no_plausible_routes",
                "centroid_distance_ft": None,
            }
            route["_hard_length_gate"] = {
                "applied": False,
                "min_allowed_ft": None,
                "max_allowed_ft": None,
                "passed": True,
            }

    plausible_routes = _decorate_route_id_disambiguation(plausible_routes, span_ft, filter_meta)

    filter_meta = dict(filter_meta or {})
    filter_meta["spatial_context"] = spatial_context
    filter_meta["hard_length_gate"] = {
        "applied": span_ft > 0.0,
        "span_ft": round(span_ft, 2),
        "min_allowed_ft": round(span_ft * 0.70, 2) if span_ft > 0.0 else None,
        "max_allowed_ft": round(span_ft * 1.80, 2) if span_ft > 0.0 else None,
        "rejected_count": len(rejected_length_routes),
        "rejected_sample": rejected_length_routes[:25],
    }

    plausible_routes.sort(
        key=lambda route: (
            abs(float(route.get("length_ft", 0.0) or 0.0) - span_ft),
            -float(route.get("_spatial_hint_score", 0.0) or 0.0),
            -float(route.get("_name_hint_score", 0.0) or 0.0),
            float(route.get("length_ft", 0.0) or 0.0),
        )
    )

    return plausible_routes, filter_meta


def _score_route_candidate(group_rows: Sequence[Dict[str, Any]], route: Dict[str, Any], filter_meta: Dict[str, Any], normalized_group: Dict[str, Any]) -> Dict[str, Any]:
    base = _score_route_for_group(group_rows, route)
    route_role = str(route.get("route_role") or "other")
    print_bonus = 0.10 if filter_meta.get("applied") and str(route.get("route_id") or "") in set(filter_meta.get("allowed_route_ids") or []) else 0.0
    route_length_ft = float(route.get("length_ft", 0.0) or 0.0)
    span_ft = float(normalized_group.get("span_ft") or 0.0)

    subsection_plausibility = 0.0
    exact_length_bonus = 0.0
    oversize_penalty = 0.0
    if span_ft > 0.0 and route_length_ft > 0.0:
        ratio = min(span_ft, route_length_ft) / max(span_ft, route_length_ft)
        subsection_plausibility = max(0.0, min(1.0, ratio)) * 0.08

        relative_gap = abs(route_length_ft - span_ft) / max(span_ft, 1.0)
        exact_length_bonus = max(0.0, 1.0 - relative_gap) * 0.16

        if route_length_ft > span_ft:
            oversize_ratio = route_length_ft / max(span_ft, 1.0)
            oversize_penalty = min(0.30, max(0.0, (oversize_ratio - 1.15) * 0.10))

    role_score = 0.04 if route_role in {"underground_cable", "backbone", "terminal_tail"} else 0.0
    name_hint = float(route.get("_name_hint_score", 0.0) or 0.0)
    spatial_hint = float(route.get("_spatial_hint_score", 0.0) or 0.0)
    route_id_disambiguation_bonus = float(route.get("_route_id_disambiguation_bonus", 0.0) or 0.0)

    total_score = (
        float(base.get("score", 0.0) or 0.0)
        + print_bonus
        + subsection_plausibility
        + exact_length_bonus
        + role_score
        + name_hint
        + spatial_hint
        + route_id_disambiguation_bonus
        - oversize_penalty
    )
    total_score = min(1.0, max(0.0, total_score))

    return {
        **base,
        "score": round(total_score, 6),
        "score_breakdown": {
            "base_score": round(float(base.get("score", 0.0) or 0.0), 6),
            "print_bonus": round(print_bonus, 6),
            "subsection_plausibility": round(subsection_plausibility, 6),
            "exact_length_bonus": round(exact_length_bonus, 6),
            "oversize_penalty": round(oversize_penalty, 6),
            "role_score": round(role_score, 6),
            "name_hint_score": round(name_hint, 6),
            "spatial_hint_score": round(spatial_hint, 6),
            "route_id_disambiguation_bonus": round(route_id_disambiguation_bonus, 6),
        },
        "route_id_disambiguation_meta": dict(route.get("_route_id_disambiguation_meta") or {}),
    }


def _candidate_rankings_for_group_v2(group_rows: Sequence[Dict[str, Any]], normalized_group: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any], List[Dict[str, Any]]]:
    candidate_routes, filter_meta = _build_candidate_pool_for_group(normalized_group)
    rankings = [_score_route_candidate(group_rows, route, filter_meta, normalized_group) for route in candidate_routes]
    rankings.sort(key=lambda item: (-float(item.get("score", 0.0) or 0.0), float(item.get("length_gap_ft", 0.0) or 0.0), float(item.get("route_length_ft", 0.0) or 0.0), str(item.get("route_name", ""))))
    return rankings[:8], filter_meta, rankings


def _route_sheet_sequence(route_id: Any) -> List[int]:
    target = str(route_id or "").strip()
    if not target:
        return []
    sheets: List[int] = []
    for token, entry in CURRENT_PACKET_PRINT_SHEET_INDEX.items():
        route_ids = [str(value or "").strip() for value in (entry.get("route_ids") or [])]
        if target not in route_ids:
            continue
        sheet = entry.get("sheet")
        if isinstance(sheet, int) and sheet not in sheets:
            sheets.append(sheet)
    sheets.sort()
    return sheets


def _print_aware_window_bias(route_id: Any, filter_meta: Dict[str, Any], start_ft: float, end_ft: float, route_total_ft: float) -> Dict[str, Any]:
    route_id_text = str(route_id or "").strip()
    sheet_numbers = [int(value) for value in (filter_meta.get("sheet_numbers") or []) if str(value).strip().isdigit()]
    allowed_route_ids = [str(value or "").strip() for value in (filter_meta.get("allowed_route_ids") or []) if str(value or "").strip()]
    if not route_id_text or route_total_ft <= 0.0 or not sheet_numbers:
        return {"bonus": 0.0, "applied": False, "reason": "no_print_sheet_numbers"}
    if allowed_route_ids and route_id_text not in set(allowed_route_ids):
        return {"bonus": 0.0, "applied": False, "reason": "route_not_in_allowed_set"}

    route_sheets = _route_sheet_sequence(route_id_text)
    if not route_sheets:
        return {"bonus": 0.0, "applied": False, "reason": "no_route_sheet_sequence"}

    preferred_fractions: List[float] = []
    if len(route_sheets) == 1:
        preferred_fractions = [0.5]
    else:
        denom = max(1, len(route_sheets) - 1)
        for sheet in sheet_numbers:
            nearest_index = min(range(len(route_sheets)), key=lambda idx: abs(route_sheets[idx] - sheet))
            preferred_fractions.append(nearest_index / denom)
    if not preferred_fractions:
        return {"bonus": 0.0, "applied": False, "reason": "no_preferred_fractions"}

    window_center_ft = max(0.0, min((float(start_ft) + float(end_ft)) / 2.0, float(route_total_ft)))
    window_fraction = window_center_ft / max(float(route_total_ft), 1.0)
    distance = min(abs(window_fraction - fraction) for fraction in preferred_fractions)
    tolerance = 0.18
    normalized_fit = max(0.0, 1.0 - (distance / tolerance))
    bonus = normalized_fit * 0.12
    return {
        "bonus": round(bonus, 6),
        "applied": True,
        "reason": "print_sheet_fraction_bias",
        "window_fraction": round(window_fraction, 6),
        "preferred_fractions": [round(value, 6) for value in preferred_fractions],
        "fraction_distance": round(distance, 6),
        "route_sheets": route_sheets,
    }


def _anchor_route_subsection(route: Dict[str, Any], normalized_group: Dict[str, Any], ranking: Dict[str, Any], filter_meta: Dict[str, Any]) -> Dict[str, Any]:
    route_coords = route.get("coords", []) or []
    route_total_ft = _route_length_ft(route_coords) if route_coords else 0.0
    span_ft = float(normalized_group.get("span_ft") or 0.0)

    if route_total_ft <= 0.0:
        return {
            "route_id": route.get("route_id"),
            "route_name": route.get("route_name"),
            "route_score": float(ranking.get("score", 0.0) or 0.0),
            "subsection_start_ft": 0.0,
            "subsection_end_ft": 0.0,
            "subsection_score": 0.0,
            "combined_score": round(float(ranking.get("score", 0.0) or 0.0), 6),
            "anchor_method": "invalid_route_geometry",
            "anchor_reasons": ["Route geometry length was zero."],
            "mapping": _resolve_station_mapping(normalized_group.get("station_rows") or [], 0.0),
            "score_breakdown": dict(ranking.get("score_breakdown") or {}),
        }

    windows = _generate_segment_windows(route_coords, span_ft)
    if not windows:
        fallback_mapping = _resolve_station_mapping(normalized_group.get("station_rows") or [], route_total_ft)
        return {
            "route_id": route.get("route_id"),
            "route_name": route.get("route_name"),
            "route_score": round(float(ranking.get("score", 0.0) or 0.0), 6),
            "subsection_start_ft": 0.0,
            "subsection_end_ft": round(min(route_total_ft, span_ft or route_total_ft), 2),
            "subsection_score": 0.0,
            "combined_score": round(float(ranking.get("score", 0.0) or 0.0), 6),
            "anchor_method": "no_segment_windows",
            "anchor_reasons": ["No sliding-window segment hypotheses were generated."],
            "mapping": fallback_mapping,
            "score_breakdown": dict(ranking.get("score_breakdown") or {}),
        }

    scored_windows = []
    for window in windows:
        scored = {
            **window,
            **_score_segment_window(route_coords, normalized_group, window),
        }
        bias_meta = _print_aware_window_bias(route.get("route_id"), filter_meta, float(window.get("start_ft") or 0.0), float(window.get("end_ft") or 0.0), float(route_total_ft))
        print_bias_bonus = float(bias_meta.get("bonus", 0.0) or 0.0)
        scored["print_aware_window_bias"] = bias_meta
        scored["window_score_base"] = round(float(scored.get("window_score", 0.0) or 0.0), 6)
        scored["window_score"] = round(min(1.0, max(0.0, float(scored.get("window_score", 0.0) or 0.0) + print_bias_bonus)), 6)
        scored_windows.append(scored)

    scored_windows.sort(
        key=lambda item: (
            -float(item.get("window_score", 0.0) or 0.0),
            -float((item.get("print_aware_window_bias") or {}).get("bonus", 0.0) or 0.0),
            abs(float(item.get("end_ft", 0.0) or 0.0) - float(item.get("start_ft", 0.0) or 0.0) - span_ft),
            float(item.get("start_ft", 0.0) or 0.0),
        )
    )
    best_window = scored_windows[0]

    mapping = dict(best_window.get("mapping") or {})
    anchor_reasons = list(best_window.get("window_reasons") or [])
    if filter_meta.get("applied"):
        anchor_reasons.append("Print-aware filtering narrowed the route family before sliding-window segment scoring.")
    else:
        anchor_reasons.append("No print-aware narrowing was available, so sliding-window scoring relied on KMZ route geometry and span fit.")

    mapping["anchor_strategy"] = "true_sliding_window_segment_scorer"
    mapping["anchor_basis"] = {
        **dict(mapping.get("anchor_basis") or {}),
        "print_tokens": list(normalized_group.get("print_tokens") or []),
        "filter_applied": bool(filter_meta.get("applied")),
        "route_total_ft": round(float(route_total_ft), 2),
        "group_span_ft": round(float(span_ft), 2),
        "segment_window_count": len(scored_windows),
        "segment_window_preview": [
            {
                "start_ft": round(float(item.get("start_ft", 0.0) or 0.0), 2),
                "end_ft": round(float(item.get("end_ft", 0.0) or 0.0), 2),
                "window_type": item.get("window_type"),
                "window_score": round(float(item.get("window_score", 0.0) or 0.0), 6),
            }
            for item in scored_windows[:12]
        ],
    }

    combined_score = min(
        1.0,
        float(ranking.get("score", 0.0) or 0.0) + float(best_window.get("window_score", 0.0) or 0.0) * 0.35,
    )

    return {
        "route_id": route.get("route_id"),
        "route_name": route.get("route_name"),
        "route_score": round(float(ranking.get("score", 0.0) or 0.0), 6),
        "subsection_start_ft": round(float(best_window.get("start_ft", 0.0) or 0.0), 2),
        "subsection_end_ft": round(float(best_window.get("end_ft", 0.0) or 0.0), 2),
        "subsection_score": round(float(best_window.get("window_score", 0.0) or 0.0), 6),
        "combined_score": round(combined_score, 6),
        "anchor_method": "true_sliding_window_segment_scorer",
        "anchor_reasons": anchor_reasons,
        "anchor_profile": dict(best_window.get("window_profile") or {}),
        "mapping": mapping,
        "score_breakdown": dict(ranking.get("score_breakdown") or {}),
    }


def _build_validation_checks(
    normalized_group: Dict[str, Any],
    anchored_hypotheses: Sequence[Dict[str, Any]],
    mapping: Dict[str, Any],
    mapped_station_points: Sequence[Dict[str, Any]],
    matched_route: Dict[str, Any],
) -> Dict[str, Any]:
    checks: List[Dict[str, Any]] = []

    if anchored_hypotheses:
        best = anchored_hypotheses[0]
        second = anchored_hypotheses[1] if len(anchored_hypotheses) > 1 else None
        gap = float(best.get("combined_score", 0.0) or 0.0) - float(second.get("combined_score", 0.0) or 0.0) if second else 1.0
        status = "pass"
        message = f"Top candidate score gap is {round(gap, 4)}."
        if gap < 0.02:
            status = "fail"
            message = f"Top two anchored candidates are nearly tied with a score gap of {round(gap, 4)}."
        elif gap < 0.05:
            status = "warn"
            message = f"Top two anchored candidates are close with a score gap of {round(gap, 4)}."
        checks.append({"check": "route_ambiguity", "status": status, "message": message})

    mapped_values = [float(point.get("mapped_station_ft") or 0.0) for point in mapped_station_points if point.get("mapped_station_ft") is not None]
    monotonic_status = "pass"
    monotonic_message = "Mapped stations are strictly increasing."
    for idx in range(1, len(mapped_values)):
        if mapped_values[idx] <= mapped_values[idx - 1]:
            monotonic_status = "fail"
            monotonic_message = "Mapped station feet are not strictly increasing."
            break
    checks.append({"check": "mapped_station_monotonicity", "status": monotonic_status, "message": monotonic_message})

    source_values = [float(row.get("station_ft") or 0.0) for row in normalized_group.get("station_rows") or [] if row.get("station_ft") is not None]
    source_span = (max(source_values) - min(source_values)) if len(source_values) >= 2 else 0.0
    mapped_span = (mapped_values[-1] - mapped_values[0]) if len(mapped_values) >= 2 else 0.0
    span_status = "pass"
    span_message = "Mapped span is consistent with source station span."
    if source_span > 0.0:
        span_ratio = abs(mapped_span - source_span) / source_span
        if span_ratio > 0.35:
            span_status = "fail"
            span_message = f"Mapped span deviates from source span by {round(span_ratio * 100.0, 2)}%."
        elif span_ratio > 0.15:
            span_status = "warn"
            span_message = f"Mapped span deviates from source span by {round(span_ratio * 100.0, 2)}%."
    checks.append({"check": "span_integrity", "status": span_status, "message": span_message})

    spacing_ratios: List[float] = []
    for idx in range(1, min(len(source_values), len(mapped_values))):
        src_delta = source_values[idx] - source_values[idx - 1]
        mapped_delta = mapped_values[idx] - mapped_values[idx - 1]
        if src_delta > 0.0:
            spacing_ratios.append(mapped_delta / src_delta)
    spacing_status = "pass"
    spacing_message = "Mapped station spacing tracks source station spacing."
    if spacing_ratios:
        min_ratio = min(spacing_ratios)
        max_ratio = max(spacing_ratios)
        if min_ratio < 0.50 or max_ratio > 1.75:
            spacing_status = "fail"
            spacing_message = f"Mapped station spacing is distorted (ratio range {round(min_ratio, 3)} to {round(max_ratio, 3)})."
        elif min_ratio < 0.80 or max_ratio > 1.25:
            spacing_status = "warn"
            spacing_message = f"Mapped station spacing is somewhat distorted (ratio range {round(min_ratio, 3)} to {round(max_ratio, 3)})."
    checks.append({"check": "spacing_distortion", "status": spacing_status, "message": spacing_message})

    route_total_ft = float(matched_route.get("length_ft", 0.0) or 0.0)
    edge_status = "pass"
    edge_message = "Mapped stations are not clamped to the route edges."
    if mapped_values and route_total_ft > 0.0:
        near_start = sum(1 for value in mapped_values if value <= 5.0)
        near_end = sum(1 for value in mapped_values if abs(route_total_ft - value) <= 5.0)
        if near_start >= 2 or near_end >= 2:
            edge_status = "warn"
            edge_message = "Multiple mapped stations fall very close to the route start or end, which may indicate an anchor issue."
    checks.append({"check": "edge_clamp", "status": edge_status, "message": edge_message})

    anchor_strategy = str(mapping.get("anchor_strategy") or "")
    anchor_status = "pass"
    anchor_message = f"Anchor strategy used: {anchor_strategy or 'unspecified'}."
    if anchor_strategy in {"group_relative_origin", "full_route_fallback", "none", ""}:
        anchor_status = "warn"
        anchor_message = f"Anchor strategy '{anchor_strategy or 'unspecified'}' is still a fallback-style anchor and should be treated cautiously."
    elif anchor_strategy == "balanced_span_search":
        anchor_status = "warn"
        anchor_message = "Anchor strategy 'balanced_span_search' is an inferred subsection anchor. Better than route-origin fallback, but still not absolute proof."
    elif anchor_strategy == "absolute_station_window":
        anchor_status = "pass"
        anchor_message = "Anchor strategy 'absolute_station_window' aligned the bore span to a plausible absolute station window on the selected route."
    checks.append({"check": "anchor_confidence", "status": anchor_status, "message": anchor_message})

    overall = "pass"
    if any(check["status"] == "fail" for check in checks):
        overall = "fail"
    elif any(check["status"] == "warn" for check in checks):
        overall = "warn"

    probable_failure_class = None
    failed_or_warned = {check["check"]: check["status"] for check in checks if check["status"] in {"warn", "fail"}}
    if failed_or_warned.get("route_ambiguity") == "fail":
        probable_failure_class = "AMBIGUOUS_MATCH"
    elif failed_or_warned.get("mapped_station_monotonicity") == "fail":
        probable_failure_class = "STATION_NORMALIZATION_ISSUE"
    elif failed_or_warned.get("anchor_confidence") in {"warn", "fail"}:
        probable_failure_class = "BAD_ANCHOR"
    elif failed_or_warned.get("spacing_distortion") == "fail":
        probable_failure_class = "RIGHT_ROUTE_WRONG_SCALING"
    elif failed_or_warned.get("span_integrity") == "fail":
        probable_failure_class = "RIGHT_ROUTE_WRONG_POSITION"

    confidence_label = "HIGH"
    if overall == "fail":
        confidence_label = "LOW"
    elif overall == "warn":
        confidence_label = "MEDIUM"

    return {
        "validation_status": overall,
        "confidence_label": confidence_label,
        "probable_failure_class": probable_failure_class,
        "checks": checks,
    }


def _build_matching_debug_record(
    normalized_group: Dict[str, Any],
    filter_meta: Dict[str, Any],
    rankings: Sequence[Dict[str, Any]],
    anchored_hypotheses: Sequence[Dict[str, Any]],
    selected_hypothesis: Dict[str, Any],
    validation: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "group_id": normalized_group.get("group_id"),
        "source_file": normalized_group.get("source_file"),
        "normalized_group": normalized_group,
        "print_filter": dict(filter_meta),
        "candidate_routes": list(rankings),
        "anchored_hypotheses": list(anchored_hypotheses),
        "selected_hypothesis": dict(selected_hypothesis),
        "validation": dict(validation),
    }



def _candidate_is_billable(
    validation: Dict[str, Any],
    hypothesis: Dict[str, Any],
    normalized_group: Dict[str, Any],
) -> Tuple[bool, List[str]]:
    reasons: List[str] = []
    checks = {str(check.get("check") or ""): str(check.get("status") or "") for check in validation.get("checks") or []}

    for required_check in ("mapped_station_monotonicity", "span_integrity", "spacing_distortion"):
        if checks.get(required_check) != "pass":
            reasons.append(f"{required_check}={checks.get(required_check) or 'missing'}")

    if checks.get("edge_clamp") == "fail":
        reasons.append("edge_clamp=fail")

    profile = dict(hypothesis.get("anchor_profile") or {})
    segment_length_ft = float(profile.get("segment_length_ft") or 0.0)
    source_span_ft = float(normalized_group.get("span_ft") or 0.0)
    if source_span_ft > 0.0:
        coverage_ratio = segment_length_ft / source_span_ft
        if coverage_ratio < 0.90:
            reasons.append(f"segment_coverage_ratio={round(coverage_ratio, 4)}")

    projected_points = list(profile.get("projected_points") or [])
    if projected_points:
        unique_projected = {
            (round(float(point.get("lat") or 0.0), 7), round(float(point.get("lon") or 0.0), 7))
            for point in projected_points
        }
        if len(unique_projected) < max(3, int(len(projected_points) * 0.65)):
            reasons.append("projected_points_clamped")

    return (len(reasons) == 0, reasons)


def _authoritative_selection_bundle(
    selected_hypothesis: Dict[str, Any],
    matched_route: Dict[str, Any],
    selected_ranking: Dict[str, Any],
    mapping: Dict[str, Any],
    evaluated_hypotheses: Sequence[Dict[str, Any]],
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any], str]:
    selected_copy = dict(selected_hypothesis or {})
    matched_route_copy = dict(matched_route or {})
    ranking_copy = dict(selected_ranking or {})
    mapping_copy = dict(mapping or {})

    consensus_gate = dict(selected_copy.get("route_consensus_gate") or {})
    authoritative_route_id = str(consensus_gate.get("consensus_route_id") or selected_copy.get("route_id") or "").strip()
    if not authoritative_route_id:
        authoritative_route_id = str(matched_route_copy.get("route_id") or "").strip()

    authoritative_bundle: Optional[Dict[str, Any]] = None
    for item in evaluated_hypotheses or []:
        hypothesis = dict(item.get("hypothesis") or {})
        item_route_id = str(hypothesis.get("route_id") or "").strip()
        commit_meta = dict(hypothesis.get("authoritative_route_commit") or {})
        committed = bool(commit_meta.get("committed"))
        if item_route_id and item_route_id == authoritative_route_id and (committed or authoritative_route_id):
            authoritative_bundle = dict(item)
            break

    if authoritative_bundle:
        selected_copy = dict(authoritative_bundle.get("hypothesis") or selected_copy)
        matched_route_copy = dict(authoritative_bundle.get("matched_route") or matched_route_copy)
        ranking_copy = dict(authoritative_bundle.get("ranking") or ranking_copy)
        mapping_copy = dict(authoritative_bundle.get("mapping") or mapping_copy)

    selected_copy["authoritative_route_id"] = authoritative_route_id or None
    mapping_copy["authoritative_route_id"] = authoritative_route_id or None
    if authoritative_route_id:
        matched_route_copy["route_id"] = authoritative_route_id
        ranking_copy["route_id"] = authoritative_route_id

    return selected_copy, matched_route_copy, ranking_copy, mapping_copy, authoritative_route_id


def _select_best_hypothesis_with_gate(
    group: Sequence[Dict[str, Any]],
    normalized_group: Dict[str, Any],
    rankings: Sequence[Dict[str, Any]],
    filter_meta: Dict[str, Any],
    anchored_hypotheses: Sequence[Dict[str, Any]],
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any], List[Dict[str, Any]]]:
    evaluated: List[Dict[str, Any]] = []

    for hypothesis in anchored_hypotheses:
        route_id = str(hypothesis.get("route_id") or "")
        matched_route = _find_route_by_id(route_id)
        if not matched_route:
            continue

        ranking = next((item for item in rankings if str(item.get("route_id") or "") == route_id), {})
        mapping = dict(hypothesis.get("mapping") or _resolve_station_mapping(group, float(matched_route.get("length_ft", 0.0) or 0.0)))
        station_points, mapping = _build_station_points_for_group(group, matched_route, rankings, filter_meta, mapping)
        validation = _build_validation_checks(normalized_group, anchored_hypotheses, mapping, station_points, matched_route)
        is_billable, gate_reasons = _candidate_is_billable(validation, hypothesis, normalized_group)

        enriched = dict(hypothesis)
        enriched["route_length_ft"] = round(float(matched_route.get("length_ft", 0.0) or 0.0), 2)
        enriched["mapping"] = mapping
        enriched["preselection_validation"] = dict(validation)
        enriched["billable_candidate"] = bool(is_billable)
        enriched["billable_gate_reasons"] = list(gate_reasons)

        evaluated.append({
            "hypothesis": enriched,
            "matched_route": dict(matched_route),
            "ranking": dict(ranking),
            "mapping": dict(mapping),
            "validation": dict(validation),
            "is_billable": bool(is_billable),
            "gate_reasons": list(gate_reasons),
        })

    if not evaluated:
        raise ValueError("No anchored hypotheses could be evaluated.")

    evaluated = _apply_physical_feasibility_gate(evaluated, normalized_group)
    evaluated = _apply_segment_fit_gate(evaluated)
    evaluated = _apply_boundary_exactness_gate(evaluated, normalized_group)
    evaluated = _apply_continuity_gate(evaluated)
    evaluated = _apply_chain_gate(evaluated, normalized_group)
    evaluated = _apply_node_resolution_gate(evaluated, normalized_group)
    evaluated = _apply_route_uniqueness_gate(evaluated)
    evaluated = _apply_route_consensus_gate(evaluated, rankings, anchored_hypotheses)
    evaluated = _apply_geometry_lock_gate(evaluated)

    authoritative_candidates: List[Dict[str, Any]] = []
    for item in evaluated:
        item_copy = dict(item)
        hypothesis_copy = dict(item_copy.get("hypothesis") or {})
        consensus_gate = dict(hypothesis_copy.get("route_consensus_gate") or {})
        consensus_route_id = str(consensus_gate.get("consensus_route_id") or "").strip()
        route_id = str(hypothesis_copy.get("route_id") or "").strip()
        is_authoritative = bool(consensus_route_id) and route_id == consensus_route_id
        hypothesis_copy["authoritative_route_commit"] = {
            "committed": is_authoritative,
            "reason": "route_consensus_authoritative_commit" if is_authoritative else "not_consensus_route",
            "consensus_route_id": consensus_route_id or None,
        }
        item_copy["hypothesis"] = hypothesis_copy
        if is_authoritative:
            authoritative_candidates.append(item_copy)

    if authoritative_candidates:
        authoritative_candidates.sort(
            key=lambda item: (
                0 if item["is_billable"] else 1,
                -float(item["hypothesis"].get("route_score", 0.0) or 0.0),
                -float(item["hypothesis"].get("combined_score", 0.0) or 0.0),
                -float(item["hypothesis"].get("subsection_score", 0.0) or 0.0),
                str(item["hypothesis"].get("route_name", "")),
            )
        )
        authoritative_route_id = str((authoritative_candidates[0].get("hypothesis") or {}).get("route_id") or "").strip()
        resorted: List[Dict[str, Any]] = []
        for item in evaluated:
            item_copy = dict(item)
            hypothesis_copy = dict(item_copy.get("hypothesis") or {})
            route_id = str(hypothesis_copy.get("route_id") or "").strip()
            commit_meta = dict(hypothesis_copy.get("authoritative_route_commit") or {})
            commit_meta["committed"] = route_id == authoritative_route_id
            commit_meta["reason"] = "route_consensus_authoritative_commit" if route_id == authoritative_route_id else "authoritative_route_commit_superseded"
            commit_meta["consensus_route_id"] = authoritative_route_id or None
            hypothesis_copy["authoritative_route_commit"] = commit_meta
            item_copy["hypothesis"] = hypothesis_copy
            resorted.append(item_copy)
        evaluated = sorted(
            resorted,
            key=lambda item: (
                0 if bool((item.get("hypothesis") or {}).get("authoritative_route_commit", {}).get("committed")) else 1,
                0 if item["is_billable"] else 1,
                -float(item["hypothesis"].get("route_score", 0.0) or 0.0),
                -float(item["hypothesis"].get("combined_score", 0.0) or 0.0),
                -float(item["hypothesis"].get("subsection_score", 0.0) or 0.0),
                str(item["hypothesis"].get("route_name", "")),
            )
        )
    else:
        evaluated.sort(
            key=lambda item: (
                0 if item["is_billable"] else 1,
                -float(item["hypothesis"].get("subsection_score", 0.0) or 0.0),
                -float(item["hypothesis"].get("combined_score", 0.0) or 0.0),
                -float(item["hypothesis"].get("route_score", 0.0) or 0.0),
                str(item["hypothesis"].get("route_name", "")),
            )
        )

    winner = evaluated[0]
    return (
        dict(winner["hypothesis"]),
        dict(winner["matched_route"]),
        dict(winner["ranking"]),
        dict(winner["mapping"]),
        evaluated,
    )



def _apply_route_uniqueness_gate(
    evaluated: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    billable_items = [dict(item) for item in evaluated if bool(item.get("is_billable"))]
    if not billable_items:
        return [dict(item) for item in evaluated]

    billable_items.sort(
        key=lambda item: (
            -float(item.get("hypothesis", {}).get("subsection_score", 0.0) or 0.0),
            -float(item.get("hypothesis", {}).get("combined_score", 0.0) or 0.0),
            -float(item.get("hypothesis", {}).get("route_score", 0.0) or 0.0),
            str(item.get("hypothesis", {}).get("route_id", "")),
        )
    )

    winner = billable_items[0]
    winner_hypothesis = dict(winner.get("hypothesis") or {})
    winner_subsection = float(winner_hypothesis.get("subsection_score", 0.0) or 0.0)
    winner_combined = float(winner_hypothesis.get("combined_score", 0.0) or 0.0)

    competing_billable = []
    for other in billable_items[1:]:
        other_hypothesis = dict(other.get("hypothesis") or {})
        other_subsection = float(other_hypothesis.get("subsection_score", 0.0) or 0.0)
        other_combined = float(other_hypothesis.get("combined_score", 0.0) or 0.0)

        subsection_gap = winner_subsection - other_subsection
        combined_gap = winner_combined - other_combined

        if subsection_gap < 0.08 or combined_gap < 0.06:
            competing_billable.append({
                "route_id": other_hypothesis.get("route_id"),
                "route_name": other_hypothesis.get("route_name"),
                "subsection_score": round(other_subsection, 6),
                "combined_score": round(other_combined, 6),
                "subsection_gap_vs_winner": round(subsection_gap, 6),
                "combined_gap_vs_winner": round(combined_gap, 6),
            })

    if not competing_billable:
        winner_hypothesis["route_uniqueness_gate"] = {
            "passed": True,
            "reason": "single_clear_billable_candidate",
            "competing_billable_candidates": [],
        }
        winner["hypothesis"] = winner_hypothesis

        updated = []
        winner_route_id = str(winner_hypothesis.get("route_id") or "")
        for item in evaluated:
            item_copy = dict(item)
            hypothesis_copy = dict(item_copy.get("hypothesis") or {})
            if str(hypothesis_copy.get("route_id") or "") == winner_route_id:
                hypothesis_copy["route_uniqueness_gate"] = dict(winner_hypothesis["route_uniqueness_gate"])
            item_copy["hypothesis"] = hypothesis_copy
            updated.append(item_copy)
        return updated

    updated: List[Dict[str, Any]] = []
    competing_ids = {str(item.get("route_id") or "") for item in competing_billable}
    winner_route_id = str(winner_hypothesis.get("route_id") or "")

    for item in evaluated:
        item_copy = dict(item)
        hypothesis_copy = dict(item_copy.get("hypothesis") or {})
        route_id = str(hypothesis_copy.get("route_id") or "")
        if route_id == winner_route_id:
            hypothesis_copy["billable_candidate"] = False
            reasons = list(hypothesis_copy.get("billable_gate_reasons") or [])
            reasons.append("route_uniqueness_failed_winner")
            hypothesis_copy["billable_gate_reasons"] = reasons
            hypothesis_copy["route_uniqueness_gate"] = {
                "passed": False,
                "reason": "multiple_billable_routes",
                "competing_billable_candidates": list(competing_billable),
            }
            item_copy["is_billable"] = False
            item_copy["gate_reasons"] = list(reasons)
        elif route_id in competing_ids:
            hypothesis_copy["billable_candidate"] = False
            reasons = list(hypothesis_copy.get("billable_gate_reasons") or [])
            reasons.append("route_uniqueness_failed_competitor")
            hypothesis_copy["billable_gate_reasons"] = reasons
            hypothesis_copy["route_uniqueness_gate"] = {
                "passed": False,
                "reason": "multiple_billable_routes",
                "competing_billable_candidates": list(competing_billable),
            }
            item_copy["is_billable"] = False
            item_copy["gate_reasons"] = list(reasons)
        item_copy["hypothesis"] = hypothesis_copy
        updated.append(item_copy)

    return updated



def _point_to_segment_distance_feet(
    point_lat: float,
    point_lon: float,
    a_lat: float,
    a_lon: float,
    b_lat: float,
    b_lon: float,
) -> float:
    # Local planar approximation is good enough at this scale.
    mean_lat = math.radians((point_lat + a_lat + b_lat) / 3.0)
    feet_per_deg_lat = 364000.0
    feet_per_deg_lon = 364000.0 * max(0.2, math.cos(mean_lat))

    px = point_lon * feet_per_deg_lon
    py = point_lat * feet_per_deg_lat
    ax = a_lon * feet_per_deg_lon
    ay = a_lat * feet_per_deg_lat
    bx = b_lon * feet_per_deg_lon
    by = b_lat * feet_per_deg_lat

    abx = bx - ax
    aby = by - ay
    apx = px - ax
    apy = py - ay
    denom = abx * abx + aby * aby
    if denom <= 1e-9:
        dx = px - ax
        dy = py - ay
        return math.sqrt(dx * dx + dy * dy)

    t = max(0.0, min(1.0, (apx * abx + apy * aby) / denom))
    cx = ax + abx * t
    cy = ay + aby * t
    dx = px - cx
    dy = py - cy
    return math.sqrt(dx * dx + dy * dy)


def _point_to_route_distance_feet(point_lat: float, point_lon: float, route_coords: Sequence[Sequence[float]]) -> float:
    if not route_coords:
        return float("inf")
    if len(route_coords) == 1:
        only = route_coords[0]
        return _haversine_feet(point_lat, point_lon, float(only[0]), float(only[1]))

    best = float("inf")
    for idx in range(1, len(route_coords)):
        a = route_coords[idx - 1]
        b = route_coords[idx]
        if len(a) < 2 or len(b) < 2:
            continue
        dist = _point_to_segment_distance_feet(
            point_lat,
            point_lon,
            float(a[0]),
            float(a[1]),
            float(b[0]),
            float(b[1]),
        )
        if dist < best:
            best = dist
    return best


def _apply_route_consensus_gate(
    evaluated: Sequence[Dict[str, Any]],
    rankings: Sequence[Dict[str, Any]],
    anchored_hypotheses: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    top_ranked_route_id = str((rankings[0] or {}).get("route_id") or "") if rankings else ""
    top_anchored_route_id = str((anchored_hypotheses[0] or {}).get("route_id") or "") if anchored_hypotheses else ""

    consensus_route_id = ""
    if top_ranked_route_id and top_ranked_route_id == top_anchored_route_id:
        consensus_route_id = top_ranked_route_id

    if not consensus_route_id:
        return [dict(item) for item in evaluated]

    top_ranked_score = float((rankings[0] or {}).get("score", 0.0) or 0.0) if rankings else 0.0
    second_ranked_score = float((rankings[1] or {}).get("score", 0.0) or 0.0) if len(rankings) > 1 else 0.0
    ranked_gap = top_ranked_score - second_ranked_score

    top_anchored_score = float((anchored_hypotheses[0] or {}).get("combined_score", 0.0) or 0.0) if anchored_hypotheses else 0.0
    second_anchored_score = float((anchored_hypotheses[1] or {}).get("combined_score", 0.0) or 0.0) if len(anchored_hypotheses) > 1 else 0.0
    anchored_gap = top_anchored_score - second_anchored_score

    if ranked_gap < 0.03 and anchored_gap < 0.03:
        return [dict(item) for item in evaluated]

    updated: List[Dict[str, Any]] = []
    for item in evaluated:
        item_copy = dict(item)
        hypothesis_copy = dict(item_copy.get("hypothesis") or {})
        route_id = str(hypothesis_copy.get("route_id") or "")

        consensus_gate = {
            "passed": route_id == consensus_route_id,
            "reason": "top_ranked_and_top_anchored_route_agree",
            "consensus_route_id": consensus_route_id,
            "top_ranked_route_id": top_ranked_route_id,
            "top_anchored_route_id": top_anchored_route_id,
            "ranked_gap": round(ranked_gap, 6),
            "anchored_gap": round(anchored_gap, 6),
        }

        if bool(item_copy.get("is_billable")) and route_id != consensus_route_id:
            reasons = list(hypothesis_copy.get("billable_gate_reasons") or [])
            reasons.append("route_consensus_failed")
            hypothesis_copy["billable_candidate"] = False
            hypothesis_copy["billable_gate_reasons"] = reasons
            item_copy["is_billable"] = False
            item_copy["gate_reasons"] = list(reasons)

        hypothesis_copy["route_consensus_gate"] = consensus_gate
        item_copy["hypothesis"] = hypothesis_copy
        updated.append(item_copy)

    return updated


def _apply_geometry_lock_gate(
    evaluated: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    winner_candidates = [dict(item) for item in evaluated if bool(item.get("is_billable"))]
    if not winner_candidates:
        return [dict(item) for item in evaluated]

    winner_candidates.sort(
        key=lambda item: (
            -float(item.get("hypothesis", {}).get("subsection_score", 0.0) or 0.0),
            -float(item.get("hypothesis", {}).get("combined_score", 0.0) or 0.0),
            str(item.get("hypothesis", {}).get("route_id", "")),
        )
    )
    winner = winner_candidates[0]
    winner_hypothesis = dict(winner.get("hypothesis") or {})
    winner_route_id = str(winner_hypothesis.get("route_id") or "")
    winner_points = list((winner_hypothesis.get("anchor_profile") or {}).get("projected_points") or [])

    if len(winner_points) < 3:
        winner_hypothesis["geometry_lock_gate"] = {
            "passed": False,
            "reason": "insufficient_projected_points",
            "competing_parallel_routes": [],
        }
        winner_hypothesis["billable_candidate"] = False
        reasons = list(winner_hypothesis.get("billable_gate_reasons") or [])
        reasons.append("geometry_lock_insufficient_points")
        winner_hypothesis["billable_gate_reasons"] = reasons

        updated = []
        for item in evaluated:
            item_copy = dict(item)
            hypothesis_copy = dict(item_copy.get("hypothesis") or {})
            if str(hypothesis_copy.get("route_id") or "") == winner_route_id:
                hypothesis_copy.update(winner_hypothesis)
                item_copy["hypothesis"] = hypothesis_copy
                item_copy["is_billable"] = False
                item_copy["gate_reasons"] = list(reasons)
            updated.append(item_copy)
        return updated

    parallel_conflicts = []
    for other in winner_candidates[1:]:
        other_hypothesis = dict(other.get("hypothesis") or {})
        other_route = dict(other.get("matched_route") or {})
        other_coords = list(other_route.get("coords") or [])
        if not other_coords:
            continue

        distances = []
        for pt in winner_points:
            lat = float(pt.get("lat") or 0.0)
            lon = float(pt.get("lon") or 0.0)
            distances.append(_point_to_route_distance_feet(lat, lon, other_coords))

        if not distances:
            continue

        avg_dist = sum(distances) / len(distances)
        max_dist = max(distances)
        near_count = sum(1 for d in distances if d <= 18.0)
        near_ratio = near_count / max(1, len(distances))

        if near_ratio >= 0.75 and avg_dist <= 15.0 and max_dist <= 28.0:
            parallel_conflicts.append({
                "route_id": other_hypothesis.get("route_id"),
                "route_name": other_hypothesis.get("route_name"),
                "avg_distance_ft": round(avg_dist, 3),
                "max_distance_ft": round(max_dist, 3),
                "near_ratio": round(near_ratio, 4),
                "subsection_score": round(float(other_hypothesis.get("subsection_score", 0.0) or 0.0), 6),
                "combined_score": round(float(other_hypothesis.get("combined_score", 0.0) or 0.0), 6),
            })

    updated = []
    if parallel_conflicts:
        winner_hypothesis["geometry_lock_gate"] = {
            "passed": False,
            "reason": "parallel_route_conflict",
            "competing_parallel_routes": parallel_conflicts,
        }
        winner_hypothesis["billable_candidate"] = False
        reasons = list(winner_hypothesis.get("billable_gate_reasons") or [])
        reasons.append("geometry_lock_parallel_conflict")
        winner_hypothesis["billable_gate_reasons"] = reasons

        for item in evaluated:
            item_copy = dict(item)
            hypothesis_copy = dict(item_copy.get("hypothesis") or {})
            if str(hypothesis_copy.get("route_id") or "") == winner_route_id:
                hypothesis_copy.update(winner_hypothesis)
                item_copy["hypothesis"] = hypothesis_copy
                item_copy["is_billable"] = False
                item_copy["gate_reasons"] = list(reasons)
            updated.append(item_copy)
        return updated

    winner_hypothesis["geometry_lock_gate"] = {
        "passed": True,
        "reason": "no_parallel_route_conflict_detected",
        "competing_parallel_routes": [],
    }

    for item in evaluated:
        item_copy = dict(item)
        hypothesis_copy = dict(item_copy.get("hypothesis") or {})
        if str(hypothesis_copy.get("route_id") or "") == winner_route_id:
            hypothesis_copy["geometry_lock_gate"] = dict(winner_hypothesis["geometry_lock_gate"])
        item_copy["hypothesis"] = hypothesis_copy
        updated.append(item_copy)

    return updated



def _apply_physical_feasibility_gate(
    evaluated: Sequence[Dict[str, Any]],
    normalized_group: Dict[str, Any],
) -> List[Dict[str, Any]]:
    source_span_ft = float(normalized_group.get("span_ft") or 0.0)
    min_span_ratio = 0.85
    max_span_ratio = 3.50

    if source_span_ft <= 0.0:
        return [dict(item) for item in evaluated]

    min_valid_ft = source_span_ft * min_span_ratio
    max_valid_ft = source_span_ft * max_span_ratio

    updated: List[Dict[str, Any]] = []
    for item in evaluated:
        item_copy = dict(item)
        hypothesis = dict(item_copy.get("hypothesis") or {})
        matched_route = dict(item_copy.get("matched_route") or {})
        route_length_ft = float(matched_route.get("length_ft") or hypothesis.get("route_length_ft") or 0.0)

        gate = {
            "passed": True,
            "reason": "within_physical_span_bounds",
            "route_length_ft": round(route_length_ft, 2),
            "source_span_ft": round(source_span_ft, 2),
            "min_valid_ft": round(min_valid_ft, 2),
            "max_valid_ft": round(max_valid_ft, 2),
            "min_span_ratio": min_span_ratio,
            "max_span_ratio": max_span_ratio,
        }

        reasons = list(hypothesis.get("billable_gate_reasons") or [])

        if route_length_ft < min_valid_ft:
            gate["passed"] = False
            gate["reason"] = "route_too_short_for_bore_span"
            reasons.append("physical_feasibility_route_too_short")
            hypothesis["billable_candidate"] = False
            item_copy["is_billable"] = False
            item_copy["gate_reasons"] = reasons

        elif route_length_ft > max_valid_ft:
            gate["passed"] = False
            gate["reason"] = "route_too_long_for_bore_span"
            reasons.append("physical_feasibility_route_too_long")
            hypothesis["billable_candidate"] = False
            item_copy["is_billable"] = False
            item_copy["gate_reasons"] = reasons

        hypothesis["billable_gate_reasons"] = reasons
        hypothesis["physical_feasibility_gate"] = gate
        item_copy["hypothesis"] = hypothesis
        updated.append(item_copy)

    return updated



def _apply_segment_fit_gate(
    evaluated: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    updated: List[Dict[str, Any]] = []

    for item in evaluated:
        item_copy = dict(item)
        hypothesis = dict(item_copy.get("hypothesis") or {})
        profile = dict(hypothesis.get("anchor_profile") or {})
        projected_points = list(profile.get("projected_points") or [])

        gate = {
            "passed": True,
            "reason": "segment_fit_valid",
            "min_point_count": 4,
            "min_unique_segment_ratio": 0.20,
            "min_route_progress_ft": 250.0,
            "max_segment_jump": 2,
            "details": {},
        }

        reasons = list(hypothesis.get("billable_gate_reasons") or [])

        if len(projected_points) < 4:
            gate["passed"] = False
            gate["reason"] = "insufficient_projected_points"
            reasons.append("segment_fit_insufficient_points")
            hypothesis["billable_candidate"] = False
            item_copy["is_billable"] = False
            item_copy["gate_reasons"] = reasons
        else:
            route_fts = [float(point.get("route_ft") or 0.0) for point in projected_points]
            segment_indices = [int(point.get("segment_index") or 0) for point in projected_points]
            actual_segment_indices = [int(point.get("actual_segment_index", point.get("segment_index") or 0)) for point in projected_points]
            virtual_segment_count = max(1, max(int(point.get("virtual_segment_count") or 1) for point in projected_points))

            route_progress_ft = max(route_fts) - min(route_fts) if route_fts else 0.0
            unique_segments = len(set(segment_indices))
            unique_actual_segments = len(set(actual_segment_indices))
            segment_ratio = unique_segments / max(1, len(projected_points) - 1)
            route_coverage_ratio = unique_segments / max(1, virtual_segment_count)

            segment_jumps = [
                abs(segment_indices[idx] - segment_indices[idx - 1])
                for idx in range(1, len(segment_indices))
            ]
            max_segment_jump = max(segment_jumps) if segment_jumps else 0

            monotonic_forward = all(
                route_fts[idx] > route_fts[idx - 1]
                for idx in range(1, len(route_fts))
            )

            gate["details"] = {
                "projected_point_count": len(projected_points),
                "route_progress_ft": round(route_progress_ft, 2),
                "unique_segments": unique_segments,
                "unique_actual_segments": unique_actual_segments,
                "virtual_segment_count": int(virtual_segment_count),
                "unique_segment_ratio": round(segment_ratio, 4),
                "route_coverage_ratio": round(route_coverage_ratio, 4),
                "max_segment_jump": int(max_segment_jump),
                "monotonic_forward": bool(monotonic_forward),
            }

            if not monotonic_forward:
                gate["passed"] = False
                gate["reason"] = "non_monotonic_route_progress"
                reasons.append("segment_fit_non_monotonic_route_progress")
            elif route_progress_ft < gate["min_route_progress_ft"]:
                gate["passed"] = False
                gate["reason"] = "insufficient_route_progress"
                reasons.append("segment_fit_insufficient_route_progress")
            elif unique_actual_segments <= 1 and virtual_segment_count <= 1:
                gate["passed"] = True
                gate["reason"] = "single_segment_route_geometry"
            elif segment_ratio < gate["min_unique_segment_ratio"] and route_coverage_ratio < gate["min_unique_segment_ratio"]:
                gate["passed"] = False
                gate["reason"] = "low_unique_segment_ratio"
                reasons.append("segment_fit_low_unique_segment_ratio")
            elif max_segment_jump > gate["max_segment_jump"]:
                gate["passed"] = False
                gate["reason"] = "segment_jump_too_large"
                reasons.append("segment_fit_segment_jump_too_large")

            if not gate["passed"]:
                hypothesis["billable_candidate"] = False
                item_copy["is_billable"] = False
                item_copy["gate_reasons"] = reasons

        hypothesis["billable_gate_reasons"] = reasons
        hypothesis["segment_fit_gate"] = gate
        item_copy["hypothesis"] = hypothesis
        updated.append(item_copy)

    return updated



def _apply_boundary_exactness_gate(
    evaluated: Sequence[Dict[str, Any]],
    normalized_group: Dict[str, Any],
) -> List[Dict[str, Any]]:
    updated: List[Dict[str, Any]] = []
    source_span_ft = float(normalized_group.get("span_ft") or 0.0)
    span_tolerance_ft = 10.0
    endpoint_tolerance_ft = 10.0
    allowed_boundary_overrun_ft = 5.0

    for item in evaluated:
        item_copy = dict(item)
        hypothesis = dict(item_copy.get("hypothesis") or {})
        profile = dict(hypothesis.get("anchor_profile") or {})
        projected_points = list(profile.get("projected_points") or [])

        gate = {
            "passed": True,
            "reason": "boundary_exactness_valid",
            "source_span_ft": round(source_span_ft, 2),
            "span_tolerance_ft": span_tolerance_ft,
            "endpoint_tolerance_ft": endpoint_tolerance_ft,
            "allowed_boundary_overrun_ft": allowed_boundary_overrun_ft,
            "details": {},
        }

        reasons = list(hypothesis.get("billable_gate_reasons") or [])

        if len(projected_points) < 2 or source_span_ft <= 0.0:
            gate["passed"] = False
            gate["reason"] = "insufficient_boundary_points"
            reasons.append("boundary_exactness_insufficient_points")
            hypothesis["billable_candidate"] = False
            item_copy["is_billable"] = False
            item_copy["gate_reasons"] = reasons
        else:
            route_fts = [float(point.get("route_ft") or 0.0) for point in projected_points]
            station_fts = [float(point.get("station_ft") or 0.0) for point in projected_points]

            projected_start_ft = min(route_fts)
            projected_end_ft = max(route_fts)
            projected_span_ft = projected_end_ft - projected_start_ft

            source_start_ft = min(station_fts)
            source_end_ft = max(station_fts)

            expected_start_ft = float(hypothesis.get("subsection_start_ft") or 0.0)
            expected_end_ft = float(hypothesis.get("subsection_end_ft") or expected_start_ft)

            start_alignment_error_ft = abs(route_fts[0] - expected_start_ft)
            end_alignment_error_ft = abs(route_fts[-1] - expected_end_ft)
            span_error_ft = abs(projected_span_ft - source_span_ft)

            lower_bound = expected_start_ft - allowed_boundary_overrun_ft
            upper_bound = expected_end_ft + allowed_boundary_overrun_ft
            out_of_bounds_count = sum(
                1 for value in route_fts
                if value < lower_bound or value > upper_bound
            )

            gate["details"] = {
                "source_start_ft": round(source_start_ft, 2),
                "source_end_ft": round(source_end_ft, 2),
                "expected_start_ft": round(expected_start_ft, 2),
                "expected_end_ft": round(expected_end_ft, 2),
                "projected_start_ft": round(projected_start_ft, 2),
                "projected_end_ft": round(projected_end_ft, 2),
                "projected_span_ft": round(projected_span_ft, 2),
                "span_error_ft": round(span_error_ft, 2),
                "start_alignment_error_ft": round(start_alignment_error_ft, 2),
                "end_alignment_error_ft": round(end_alignment_error_ft, 2),
                "out_of_bounds_count": int(out_of_bounds_count),
            }

            if span_error_ft > span_tolerance_ft:
                gate["passed"] = False
                gate["reason"] = "projected_span_out_of_tolerance"
                reasons.append("boundary_exactness_span_out_of_tolerance")
            elif start_alignment_error_ft > endpoint_tolerance_ft:
                gate["passed"] = False
                gate["reason"] = "start_boundary_out_of_tolerance"
                reasons.append("boundary_exactness_start_out_of_tolerance")
            elif end_alignment_error_ft > endpoint_tolerance_ft:
                gate["passed"] = False
                gate["reason"] = "end_boundary_out_of_tolerance"
                reasons.append("boundary_exactness_end_out_of_tolerance")
            elif out_of_bounds_count > 0:
                gate["passed"] = False
                gate["reason"] = "projected_points_outside_segment_bounds"
                reasons.append("boundary_exactness_points_outside_bounds")

            if not gate["passed"]:
                hypothesis["billable_candidate"] = False
                item_copy["is_billable"] = False
                item_copy["gate_reasons"] = reasons

        hypothesis["billable_gate_reasons"] = reasons
        hypothesis["boundary_exactness_gate"] = gate
        item_copy["hypothesis"] = hypothesis
        updated.append(item_copy)

    return updated



def _apply_continuity_gate(
    evaluated: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    updated: List[Dict[str, Any]] = []

    for item in evaluated:
        item_copy = dict(item)
        hypothesis = dict(item_copy.get("hypothesis") or {})
        profile = dict(hypothesis.get("anchor_profile") or {})
        projected_points = list(profile.get("projected_points") or [])

        gate = {
            "passed": True,
            "reason": "continuity_valid",
            "max_gap_ft": 80.0,
            "min_gap_ft": 5.0,
            "max_repeat_ratio": 0.20,
            "max_gap_ratio": 1.75,
            "details": {},
        }

        reasons = list(hypothesis.get("billable_gate_reasons") or [])

        if len(projected_points) < 3:
            gate["passed"] = False
            gate["reason"] = "insufficient_points_for_continuity"
            reasons.append("continuity_insufficient_points")
            hypothesis["billable_candidate"] = False
            item_copy["is_billable"] = False
            item_copy["gate_reasons"] = reasons
        else:
            route_fts = [float(point.get("route_ft") or 0.0) for point in projected_points]
            station_fts = [float(point.get("station_ft") or 0.0) for point in projected_points]

            route_steps = [
                route_fts[idx] - route_fts[idx - 1]
                for idx in range(1, len(route_fts))
            ]
            station_steps = [
                station_fts[idx] - station_fts[idx - 1]
                for idx in range(1, len(station_fts))
            ]

            positive_route_steps = [step for step in route_steps if step > 0]
            positive_station_steps = [step for step in station_steps if step > 0]

            max_route_gap = max(positive_route_steps) if positive_route_steps else 0.0
            min_route_gap = min(positive_route_steps) if positive_route_steps else 0.0
            zero_or_repeat_steps = sum(1 for step in route_steps if step <= 0.01)
            repeat_ratio = zero_or_repeat_steps / max(1, len(route_steps))

            gap_ratios = []
            for r_step, s_step in zip(route_steps, station_steps):
                if s_step > 0:
                    gap_ratios.append(r_step / s_step)

            max_gap_ratio = max(gap_ratios) if gap_ratios else 0.0
            min_gap_ratio = min(gap_ratios) if gap_ratios else 0.0

            overlap_count = sum(1 for step in route_steps if step < -0.01)

            gate["details"] = {
                "projected_point_count": len(projected_points),
                "max_route_gap_ft": round(max_route_gap, 2),
                "min_route_gap_ft": round(min_route_gap, 2),
                "repeat_ratio": round(repeat_ratio, 4),
                "max_gap_ratio": round(max_gap_ratio, 4),
                "min_gap_ratio": round(min_gap_ratio, 4),
                "overlap_count": int(overlap_count),
                "route_steps_preview": [round(v, 2) for v in route_steps[:12]],
                "station_steps_preview": [round(v, 2) for v in station_steps[:12]],
            }

            if overlap_count > 0:
                gate["passed"] = False
                gate["reason"] = "route_overlap_detected"
                reasons.append("continuity_route_overlap_detected")
            elif repeat_ratio > gate["max_repeat_ratio"]:
                gate["passed"] = False
                gate["reason"] = "too_many_repeated_steps"
                reasons.append("continuity_too_many_repeated_steps")
            elif max_route_gap > gate["max_gap_ft"]:
                gate["passed"] = False
                gate["reason"] = "route_gap_too_large"
                reasons.append("continuity_route_gap_too_large")
            elif positive_route_steps and min_route_gap < gate["min_gap_ft"]:
                gate["passed"] = False
                gate["reason"] = "route_gap_too_small"
                reasons.append("continuity_route_gap_too_small")
            elif gap_ratios and max_gap_ratio > gate["max_gap_ratio"]:
                gate["passed"] = False
                gate["reason"] = "route_station_gap_ratio_too_large"
                reasons.append("continuity_route_station_gap_ratio_too_large")
            elif gap_ratios and min_gap_ratio < 0.25:
                gate["passed"] = False
                gate["reason"] = "route_station_gap_ratio_too_small"
                reasons.append("continuity_route_station_gap_ratio_too_small")

            if not gate["passed"]:
                hypothesis["billable_candidate"] = False
                item_copy["is_billable"] = False
                item_copy["gate_reasons"] = reasons

        hypothesis["billable_gate_reasons"] = reasons
        hypothesis["continuity_gate"] = gate
        item_copy["hypothesis"] = hypothesis
        updated.append(item_copy)

    return updated



def _endpoint_distance_feet(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    return _haversine_feet(float(a_lat), float(a_lon), float(b_lat), float(b_lon))


def _build_route_endpoint_index(route_catalog: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    index: Dict[str, Dict[str, Any]] = {}
    for route in route_catalog or []:
        route_id = str(route.get("route_id") or "")
        coords = list(route.get("coords") or [])
        if not route_id or len(coords) < 2:
            continue
        start = coords[0]
        end = coords[-1]
        index[route_id] = {
            "start_lat": float(start[0]),
            "start_lon": float(start[1]),
            "end_lat": float(end[0]),
            "end_lon": float(end[1]),
        }
    return index


def _infer_chain_neighbors(
    hypothesis: Dict[str, Any],
    route_catalog: Sequence[Dict[str, Any]],
    max_link_distance_ft: float = 3.0,
) -> Dict[str, Any]:
    route_id = str(hypothesis.get("route_id") or "")
    endpoint_index = _build_route_endpoint_index(route_catalog)
    current = endpoint_index.get(route_id)
    if not current:
        return {
            "upstream_candidates": [],
            "downstream_candidates": [],
            "closest_upstream_ft": None,
            "closest_downstream_ft": None,
        }

    upstream = []
    downstream = []

    for other_route_id, other in endpoint_index.items():
        if other_route_id == route_id:
            continue

        upstream_ft = _endpoint_distance_feet(
            current["start_lat"], current["start_lon"],
            other["end_lat"], other["end_lon"],
        )
        downstream_ft = _endpoint_distance_feet(
            current["end_lat"], current["end_lon"],
            other["start_lat"], other["start_lon"],
        )

        if upstream_ft <= max_link_distance_ft:
            upstream.append({
                "route_id": other_route_id,
                "distance_ft": round(upstream_ft, 3),
            })
        if downstream_ft <= max_link_distance_ft:
            downstream.append({
                "route_id": other_route_id,
                "distance_ft": round(downstream_ft, 3),
            })

    upstream.sort(key=lambda item: (float(item["distance_ft"]), str(item["route_id"])))
    downstream.sort(key=lambda item: (float(item["distance_ft"]), str(item["route_id"])))

    return {
        "upstream_candidates": upstream[:10],
        "downstream_candidates": downstream[:10],
        "closest_upstream_ft": upstream[0]["distance_ft"] if upstream else None,
        "closest_downstream_ft": downstream[0]["distance_ft"] if downstream else None,
    }



def _route_catalog_lookup(route_catalog: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {
        str(route.get("route_id") or ""): dict(route)
        for route in (route_catalog or [])
        if str(route.get("route_id") or "")
    }


def _apply_chain_gate(
    evaluated: Sequence[Dict[str, Any]],
    normalized_group: Dict[str, Any],
) -> List[Dict[str, Any]]:
    route_catalog = STATE.get("route_catalog", []) or []
    route_lookup = _route_catalog_lookup(route_catalog)
    updated: List[Dict[str, Any]] = []

    valid_transitions = {
        "underground_cable": {"underground_cable", "backbone", "terminal_tail"},
        "backbone": {"underground_cable"},
        "terminal_tail": {"underground_cable"},
    }

    for item in evaluated:
        item_copy = dict(item)
        hypothesis = dict(item_copy.get("hypothesis") or {})
        matched_route = dict(item_copy.get("matched_route") or {})
        profile = dict(hypothesis.get("anchor_profile") or {})
        projected_points = list(profile.get("projected_points") or [])
        route_id = str(hypothesis.get("route_id") or "")

        gate = {
            "passed": True,
            "reason": "chain_valid",
            "max_link_distance_ft": 3.0,
            "max_chain_ambiguity_count": 1,
            "details": {},
        }

        reasons = list(hypothesis.get("billable_gate_reasons") or [])
        neighbors = _infer_chain_neighbors(hypothesis, route_catalog, max_link_distance_ft=gate["max_link_distance_ft"])

        route_role = str(matched_route.get("route_role") or "")
        source_span_ft = float(normalized_group.get("span_ft") or 0.0)
        subsection_start_ft = float(hypothesis.get("subsection_start_ft") or 0.0)
        subsection_end_ft = float(hypothesis.get("subsection_end_ft") or subsection_start_ft)
        route_length_ft = float(matched_route.get("length_ft") or hypothesis.get("route_length_ft") or 0.0)

        near_route_start = subsection_start_ft <= 15.0
        near_route_end = (route_length_ft - subsection_end_ft) <= 15.0 if route_length_ft > 0 else False

        upstream_candidates = list(neighbors.get("upstream_candidates") or [])
        downstream_candidates = list(neighbors.get("downstream_candidates") or [])
        chain_ambiguity_count = len(upstream_candidates) + len(downstream_candidates)

        gate["details"] = {
            "route_role": route_role,
            "route_length_ft": round(route_length_ft, 2),
            "source_span_ft": round(source_span_ft, 2),
            "subsection_start_ft": round(subsection_start_ft, 2),
            "subsection_end_ft": round(subsection_end_ft, 2),
            "near_route_start": bool(near_route_start),
            "near_route_end": bool(near_route_end),
            "closest_upstream_ft": neighbors["closest_upstream_ft"],
            "closest_downstream_ft": neighbors["closest_downstream_ft"],
            "upstream_candidates": upstream_candidates,
            "downstream_candidates": downstream_candidates,
            "chain_ambiguity_count": int(chain_ambiguity_count),
            "projected_point_count": len(projected_points),
            "bidirectional_checks": [],
            "type_checks": [],
        }

        if near_route_start or near_route_end:
            if len(projected_points) < 3:
                gate["passed"] = False
                gate["reason"] = "insufficient_points_for_chain_validation"
                reasons.append("chain_insufficient_points")
            elif chain_ambiguity_count > gate["max_chain_ambiguity_count"]:
                gate["passed"] = False
                gate["reason"] = "multiple_possible_chain_links"
                reasons.append("chain_not_unique")
            elif near_route_start and not upstream_candidates:
                gate["passed"] = False
                gate["reason"] = "missing_upstream_chain_link"
                reasons.append("chain_missing_upstream_link")
            elif near_route_end and not downstream_candidates:
                gate["passed"] = False
                gate["reason"] = "missing_downstream_chain_link"
                reasons.append("chain_missing_downstream_link")

            if gate["passed"] and near_route_start:
                for up in upstream_candidates:
                    neighbor_id = str(up.get("route_id") or "")
                    reverse = _infer_chain_neighbors(
                        {"route_id": neighbor_id},
                        route_catalog,
                        max_link_distance_ft=gate["max_link_distance_ft"],
                    )
                    reverse_down = [str(r.get("route_id") or "") for r in (reverse.get("downstream_candidates") or [])]
                    bidirectional_ok = route_id in reverse_down
                    gate["details"]["bidirectional_checks"].append({
                        "direction": "upstream",
                        "neighbor_route_id": neighbor_id,
                        "reverse_contains_current": bidirectional_ok,
                    })
                    if not bidirectional_ok:
                        gate["passed"] = False
                        gate["reason"] = "chain_not_bidirectional"
                        reasons.append("chain_break_in_topology")
                        break

                    neighbor_route = route_lookup.get(neighbor_id, {})
                    neighbor_role = str(neighbor_route.get("route_role") or "")
                    type_ok = neighbor_role in valid_transitions.get(route_role, set())
                    gate["details"]["type_checks"].append({
                        "direction": "upstream",
                        "neighbor_route_id": neighbor_id,
                        "neighbor_role": neighbor_role,
                        "type_ok": type_ok,
                    })
                    if not type_ok:
                        gate["passed"] = False
                        gate["reason"] = "invalid_chain_type_transition"
                        reasons.append("chain_invalid_topology_type")
                        break

            if gate["passed"] and near_route_end:
                for down in downstream_candidates:
                    neighbor_id = str(down.get("route_id") or "")
                    reverse = _infer_chain_neighbors(
                        {"route_id": neighbor_id},
                        route_catalog,
                        max_link_distance_ft=gate["max_link_distance_ft"],
                    )
                    reverse_up = [str(r.get("route_id") or "") for r in (reverse.get("upstream_candidates") or [])]
                    bidirectional_ok = route_id in reverse_up
                    gate["details"]["bidirectional_checks"].append({
                        "direction": "downstream",
                        "neighbor_route_id": neighbor_id,
                        "reverse_contains_current": bidirectional_ok,
                    })
                    if not bidirectional_ok:
                        gate["passed"] = False
                        gate["reason"] = "chain_not_bidirectional"
                        reasons.append("chain_break_in_topology")
                        break

                    neighbor_route = route_lookup.get(neighbor_id, {})
                    neighbor_role = str(neighbor_route.get("route_role") or "")
                    type_ok = neighbor_role in valid_transitions.get(route_role, set())
                    gate["details"]["type_checks"].append({
                        "direction": "downstream",
                        "neighbor_route_id": neighbor_id,
                        "neighbor_role": neighbor_role,
                        "type_ok": type_ok,
                    })
                    if not type_ok:
                        gate["passed"] = False
                        gate["reason"] = "invalid_chain_type_transition"
                        reasons.append("chain_invalid_topology_type")
                        break

        if not gate["passed"]:
            hypothesis["billable_candidate"] = False
            item_copy["is_billable"] = False
            item_copy["gate_reasons"] = reasons

        hypothesis["billable_gate_reasons"] = reasons
        hypothesis["chain_gate"] = gate
        item_copy["hypothesis"] = hypothesis
        updated.append(item_copy)

    return updated



def _bearing_degrees(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    lat1 = math.radians(float(a_lat))
    lat2 = math.radians(float(b_lat))
    dlon = math.radians(float(b_lon) - float(a_lon))
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    bearing = math.degrees(math.atan2(y, x))
    return (bearing + 360.0) % 360.0


def _angle_difference_degrees(a: float, b: float) -> float:
    diff = abs(float(a) - float(b)) % 360.0
    return min(diff, 360.0 - diff)


def _route_terminal_bearings(route: Dict[str, Any]) -> Dict[str, Optional[float]]:
    coords = list(route.get("coords") or [])
    if len(coords) < 2:
        return {
            "start_outbound_bearing_deg": None,
            "end_inbound_bearing_deg": None,
        }

    start_a = coords[0]
    start_b = coords[1]
    end_a = coords[-2]
    end_b = coords[-1]

    return {
        "start_outbound_bearing_deg": _bearing_degrees(float(start_a[0]), float(start_a[1]), float(start_b[0]), float(start_b[1])),
        "end_inbound_bearing_deg": _bearing_degrees(float(end_a[0]), float(end_a[1]), float(end_b[0]), float(end_b[1])),
    }


def _resolve_node_candidates(
    current_route: Dict[str, Any],
    current_role: str,
    candidate_list: Sequence[Dict[str, Any]],
    direction: str,
    route_lookup: Dict[str, Dict[str, Any]],
    valid_transitions: Dict[str, set],
) -> Dict[str, Any]:
    current_bearings = _route_terminal_bearings(current_route)
    if direction == "upstream":
        current_reference = current_bearings.get("start_outbound_bearing_deg")
    else:
        current_reference = current_bearings.get("end_inbound_bearing_deg")

    scored = []
    for candidate in candidate_list or []:
        candidate_id = str(candidate.get("route_id") or "")
        neighbor_route = dict(route_lookup.get(candidate_id) or {})
        if not neighbor_route:
            continue

        neighbor_role = str(neighbor_route.get("route_role") or "")
        type_ok = neighbor_role in valid_transitions.get(current_role, set())

        neighbor_bearings = _route_terminal_bearings(neighbor_route)
        if direction == "upstream":
            neighbor_reference = neighbor_bearings.get("end_inbound_bearing_deg")
        else:
            neighbor_reference = neighbor_bearings.get("start_outbound_bearing_deg")

        if current_reference is None or neighbor_reference is None:
            angle_diff = 999.0
        else:
            angle_diff = _angle_difference_degrees(float(current_reference), float(neighbor_reference))

        distance_ft = float(candidate.get("distance_ft") or 0.0)
        score = angle_diff + distance_ft * 2.0 + (0.0 if type_ok else 1000.0)

        scored.append({
            "route_id": candidate_id,
            "route_name": neighbor_route.get("route_name"),
            "route_role": neighbor_role,
            "distance_ft": round(distance_ft, 3),
            "angle_diff_deg": round(angle_diff, 3),
            "type_ok": bool(type_ok),
            "node_score": round(score, 3),
        })

    scored.sort(key=lambda item: (float(item["node_score"]), float(item["distance_ft"]), str(item["route_id"])))

    if not scored:
        return {
            "selected": None,
            "resolved": [],
            "resolution_status": "no_candidates",
            "ambiguity": False,
            "ambiguity_reason": None,
        }

    best = scored[0]
    second = scored[1] if len(scored) > 1 else None

    ambiguity = False
    ambiguity_reason = None
    if not best["type_ok"]:
        ambiguity = True
        ambiguity_reason = "best_candidate_has_invalid_transition"
    elif second is not None:
        node_gap = float(second["node_score"]) - float(best["node_score"])
        angle_gap = float(second["angle_diff_deg"]) - float(best["angle_diff_deg"])
        if node_gap < 12.0 or angle_gap < 10.0:
            ambiguity = True
            ambiguity_reason = "multiple_directionally_plausible_neighbors"

    return {
        "selected": best,
        "resolved": scored[:10],
        "resolution_status": "resolved" if not ambiguity else "ambiguous",
        "ambiguity": ambiguity,
        "ambiguity_reason": ambiguity_reason,
    }


def _apply_node_resolution_gate(
    evaluated: Sequence[Dict[str, Any]],
    normalized_group: Dict[str, Any],
) -> List[Dict[str, Any]]:
    route_catalog = STATE.get("route_catalog", []) or []
    route_lookup = _route_catalog_lookup(route_catalog)
    updated: List[Dict[str, Any]] = []

    valid_transitions = {
        "underground_cable": {"underground_cable", "backbone", "terminal_tail"},
        "backbone": {"underground_cable"},
        "terminal_tail": {"underground_cable"},
    }

    for item in evaluated:
        item_copy = dict(item)
        hypothesis = dict(item_copy.get("hypothesis") or {})
        matched_route = dict(item_copy.get("matched_route") or {})
        chain_gate = dict(hypothesis.get("chain_gate") or {})
        route_role = str(matched_route.get("route_role") or "")
        subsection_start_ft = float(hypothesis.get("subsection_start_ft") or 0.0)
        subsection_end_ft = float(hypothesis.get("subsection_end_ft") or subsection_start_ft)
        route_length_ft = float(matched_route.get("length_ft") or hypothesis.get("route_length_ft") or 0.0)

        near_route_start = subsection_start_ft <= 15.0
        near_route_end = (route_length_ft - subsection_end_ft) <= 15.0 if route_length_ft > 0 else False

        gate = {
            "passed": True,
            "reason": "node_resolution_valid",
            "details": {
                "near_route_start": bool(near_route_start),
                "near_route_end": bool(near_route_end),
                "upstream_resolution": None,
                "downstream_resolution": None,
            },
        }

        reasons = list(hypothesis.get("billable_gate_reasons") or [])

        if chain_gate.get("passed") is False:
            gate["passed"] = False
            gate["reason"] = "chain_gate_failed_first"
            reasons.append("node_resolution_blocked_by_chain_failure")
        else:
            if near_route_start:
                upstream_candidates = list(((chain_gate.get("details") or {}).get("upstream_candidates")) or [])
                upstream_resolution = _resolve_node_candidates(
                    matched_route,
                    route_role,
                    upstream_candidates,
                    "upstream",
                    route_lookup,
                    valid_transitions,
                )
                gate["details"]["upstream_resolution"] = upstream_resolution
                if upstream_resolution.get("ambiguity"):
                    gate["passed"] = False
                    gate["reason"] = "upstream_node_ambiguous"
                    reasons.append("node_resolution_upstream_ambiguous")
                elif upstream_resolution.get("selected") is None:
                    gate["passed"] = False
                    gate["reason"] = "upstream_node_unresolved"
                    reasons.append("node_resolution_upstream_unresolved")

            if gate["passed"] and near_route_end:
                downstream_candidates = list(((chain_gate.get("details") or {}).get("downstream_candidates")) or [])
                downstream_resolution = _resolve_node_candidates(
                    matched_route,
                    route_role,
                    downstream_candidates,
                    "downstream",
                    route_lookup,
                    valid_transitions,
                )
                gate["details"]["downstream_resolution"] = downstream_resolution
                if downstream_resolution.get("ambiguity"):
                    gate["passed"] = False
                    gate["reason"] = "downstream_node_ambiguous"
                    reasons.append("node_resolution_downstream_ambiguous")
                elif downstream_resolution.get("selected") is None:
                    gate["passed"] = False
                    gate["reason"] = "downstream_node_unresolved"
                    reasons.append("node_resolution_downstream_unresolved")

        if not gate["passed"]:
            hypothesis["billable_candidate"] = False
            item_copy["is_billable"] = False
            item_copy["gate_reasons"] = reasons

        hypothesis["billable_gate_reasons"] = reasons
        hypothesis["node_resolution_gate"] = gate
        item_copy["hypothesis"] = hypothesis
        updated.append(item_copy)

    return updated


def _candidate_rankings_for_group(group_rows: Sequence[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    normalized_group = _normalize_bore_group(group_rows, 0)
    rankings, filter_meta, _ = _candidate_rankings_for_group_v2(group_rows, normalized_group)
    return rankings[:5], filter_meta


def _select_route_for_group(group_rows: Sequence[Dict[str, Any]]) -> Tuple[Dict[str, Any], List[Dict[str, Any]], Dict[str, Any]]:
    rankings, filter_meta = _candidate_rankings_for_group(group_rows)
    best = rankings[0]
    matched_route = _find_route_by_id(best.get("route_id"))
    if not matched_route:
        raise ValueError("Matched route could not be resolved.")

    return matched_route, rankings, filter_meta


def _resolve_station_mapping(rows: Sequence[Dict[str, Any]], route_total_ft: float) -> Dict[str, Any]:
    station_values = [float(row["station_ft"]) for row in rows if row.get("station_ft") is not None]
    if not station_values:
        return {
            "mode": "absolute",
            "min_station_ft": None,
            "max_station_ft": None,
            "station_range_ft": None,
            "anchor_offset_ft": 0.0,
            "anchored_start_ft": None,
            "anchored_end_ft": None,
        }

    min_station = min(station_values)
    max_station = max(station_values)
    station_range = max_station - min_station

    if route_total_ft <= 0 or station_range <= 0:
        mode = "absolute"
    else:
        mode = "group_relative"

    return {
        "mode": mode,
        "min_station_ft": round(min_station, 2),
        "max_station_ft": round(max_station, 2),
        "station_range_ft": round(station_range, 2),
        "anchor_offset_ft": 0.0,
        "anchored_start_ft": 0.0 if mode == "group_relative" else round(min_station, 2),
        "anchored_end_ft": round(station_range, 2) if mode == "group_relative" else round(max_station, 2),
    }


def _map_station_to_route_distance(station_ft: float, route_total_ft: float, mapping: Dict[str, Any]) -> float:
    if route_total_ft <= 0:
        return 0.0

    mode = str(mapping.get("mode") or "absolute")
    anchor_offset_ft = float(mapping.get("anchor_offset_ft") or 0.0)

    if mode == "group_relative":
        min_station = float(mapping.get("min_station_ft") or 0.0)
        mapped = anchor_offset_ft + max(0.0, float(station_ft) - min_station)
        return max(0.0, min(mapped, route_total_ft))

    mapped = float(station_ft) + anchor_offset_ft
    return max(0.0, min(mapped, route_total_ft))


def _print_order_key(group_rows: Sequence[Dict[str, Any]], filter_meta: Dict[str, Any]) -> Tuple[int, str, str]:
    sheet_numbers = [int(value) for value in (filter_meta.get("sheet_numbers") or []) if str(value).strip().isdigit()]
    print_tokens = [str(token).strip() for token in _collect_group_print_tokens(group_rows) if str(token).strip()]
    numeric_tokens = [int(token) for token in print_tokens if token.isdigit()]

    if sheet_numbers:
        sheet_order = min(sheet_numbers)
    elif numeric_tokens:
        sheet_order = min(numeric_tokens)
    else:
        sheet_order = 10**9

    source_file = str(group_rows[0].get("source_file") or "").strip().lower()
    first_station = str(group_rows[0].get("station") or "").strip()
    return sheet_order, source_file, first_station


def _sheet_anchor_key(group_rows: Sequence[Dict[str, Any]], filter_meta: Dict[str, Any]) -> str:
    sheet_numbers = [int(value) for value in (filter_meta.get("sheet_numbers") or []) if str(value).strip().isdigit()]
    if sheet_numbers:
        return f"sheet::{min(sheet_numbers)}"

    print_tokens = [str(token).strip() for token in _collect_group_print_tokens(group_rows) if str(token).strip()]
    numeric_tokens = [int(token) for token in print_tokens if token.isdigit()]
    if numeric_tokens:
        return f"sheet::{min(numeric_tokens)}"

    if print_tokens:
        return f"print::{sorted(print_tokens)[0]}"

    return "fallback::unknown"


def _apply_non_overlapping_group_anchors(
    prepared_groups: Sequence[Dict[str, Any]],
    route_total_ft: float,
) -> Dict[int, Dict[str, Any]]:
    adjusted_mappings: Dict[int, Dict[str, Any]] = {}
    for item in prepared_groups:
        group_idx = int(item["group_idx"])
        mapping = dict(item["mapping"])
        group_rows = item["group"]
        mapping["anchor_offset_ft"] = 0.0
        mapping["anchor_strategy"] = "true_station_position_no_fabrication"
        mapping["anchor_basis"] = {
            "source_file": str(group_rows[0].get("source_file") or ""),
            "print_tokens": list(_collect_group_print_tokens(group_rows)),
            "sheet_numbers": list(item["filter_meta"].get("sheet_numbers") or []),
            "route_total_ft": round(float(route_total_ft or 0.0), 2),
        }
        if str(mapping.get("mode") or "") == "group_relative":
            station_range_ft = max(0.0, float(mapping.get("station_range_ft") or 0.0))
            mapping["anchored_start_ft"] = 0.0
            mapping["anchored_end_ft"] = round(station_range_ft, 2)
        else:
            mapping["anchored_start_ft"] = mapping.get("min_station_ft")
            mapping["anchored_end_ft"] = mapping.get("max_station_ft")
        adjusted_mappings[group_idx] = mapping
    return adjusted_mappings

def _confidence_from_rankings(mapping_mode: str, rankings: Sequence[Dict[str, Any]]) -> Tuple[str, str]:
    top = float(rankings[0].get("score", 0.0)) if rankings else 0.0
    second = float(rankings[1].get("score", 0.0)) if len(rankings) > 1 else 0.0
    margin = top - second

    if top >= 0.90 and margin >= 0.14:
        return "MEDIUM", "Best candidate selected by independent route scoring with a clear lead over alternate paths."
    if top >= 0.78 and margin >= 0.07:
        return "MEDIUM", "Best candidate selected by independent route scoring, but competing paths remain plausible."
    return "LOW", "Candidate route was selected independently, but the score spread is still too narrow for high trust."


def _build_station_points_for_group(
    rows: Sequence[Dict[str, Any]],
    matched_route: Dict[str, Any],
    rankings: Sequence[Dict[str, Any]],
    filter_meta: Dict[str, Any],
    mapping_override: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    route_coords = matched_route.get("coords", []) or []
    if len(route_coords) < 2:
        return [], {
            "mode": "absolute",
            "min_station_ft": None,
            "max_station_ft": None,
            "station_range_ft": None,
        }

    chainage = _route_chainage(route_coords)
    total = float(chainage[-1])
    mapping = dict(mapping_override or _resolve_station_mapping(rows, total))
    confidence, reason = _confidence_from_rankings(str(mapping.get("mode") or "absolute"), rankings)

    points: List[Dict[str, Any]] = []
    for idx, row in enumerate(rows):
        mapped_ft = _map_station_to_route_distance(float(row["station_ft"]), total, mapping)
        lat, lon = _point_at_distance(route_coords, chainage, mapped_ft)
        role = "station"
        if idx == 0:
            role = "start"
        elif idx == len(rows) - 1:
            role = "end"

        points.append(
            {
                "station": row["station"],
                "station_ft": float(row["station_ft"]),
                "mapped_station_ft": round(mapped_ft, 2),
                "lat": round(float(lat), 8),
                "lon": round(float(lon), 8),
                "depth_ft": row.get("depth_ft"),
                "boc_ft": row.get("boc_ft"),
                "notes": row.get("notes", ""),
                "date": row.get("date", ""),
                "crew": row.get("crew", ""),
                "print": row.get("print", ""),
                "job": row.get("source_file", ""),
                "source_file": row.get("source_file", ""),
                "point_role": role,
                "route_id": matched_route.get("route_id"),
                "matched_route_id": matched_route.get("route_id"),
                "matched_route_name": matched_route.get("route_name"),
                "verification": {
                    "entity_type": "station",
                    "confidence": confidence,
                    "reason": reason,
                    "route_selection_method": "independent_candidate_scoring",
                    "mapping_mode": mapping.get("mode"),
                    "anchor_type": "print_filtered_route_pool" if filter_meta.get("applied") else ("print_included_in_group_scoring" if str(row.get("print") or "").strip() else "station_range_group_scoring"),
                    "print_present": bool(str(row.get("print") or "").strip()),
                    "route_name": matched_route.get("route_name", ""),
                    "route_length_ft": round(total, 2),
                    "source_file": str(row.get("source_file") or ""),
                    "print": str(row.get("print") or ""),
                    "candidate_rankings": list(rankings),
                    "print_filter": dict(filter_meta),
                },
            }
        )

    return points, mapping


def _build_redline_segments_for_group(
    rows: Sequence[Dict[str, Any]],
    matched_route: Dict[str, Any],
    rankings: Sequence[Dict[str, Any]],
    mapping: Dict[str, Any],
    filter_meta: Dict[str, Any],
) -> List[Dict[str, Any]]:
    route_coords = matched_route.get("coords", []) or []
    if len(route_coords) < 2 or len(rows) < 2:
        return []

    chainage = _route_chainage(route_coords)
    total = float(chainage[-1])
    confidence, reason = _confidence_from_rankings(str(mapping.get("mode") or "absolute"), rankings)

    # Compute evidence_layer_id using the full row set — mirrors _bore_log_summary_from_rows()
    # so the layer toggle key is consistent between bore_log_summary and redline_segments.
    _seg_src = str(rows[0].get("source_file") if rows else "").strip().lower()
    _seg_print_tokens = sorted({t for r in rows for t in _parse_print_tokens(r.get("print"))})
    _seg_dates = sorted({str(r.get("date") or "").strip() for r in rows if str(r.get("date") or "").strip()})
    _seg_print = "|".join(_seg_print_tokens)
    _seg_date = _seg_dates[0].lower() if _seg_dates else ""
    _seg_layer_raw = f"{_seg_src}|{_seg_print}|{_seg_date}"
    _group_evidence_layer_id = hashlib.sha256(_seg_layer_raw.encode()).hexdigest()[:16]

    segments: List[Dict[str, Any]] = []
    for idx in range(len(rows) - 1):
        start_row = rows[idx]
        end_row = rows[idx + 1]

        start_ft = _map_station_to_route_distance(float(start_row["station_ft"]), total, mapping)
        end_ft = _map_station_to_route_distance(float(end_row["station_ft"]), total, mapping)
        if end_ft <= start_ft:
            continue

        coords = _clip_route_segment(route_coords, start_ft, end_ft)
        if len(coords) < 2:
            continue

        segments.append(
            {
                "segment_id": f"{matched_route.get('route_id', 'route')}_redline_{idx + 1}_{str(start_row.get('print') or 'no_print').replace(' ', '_')}",
                "row_index": idx + 1,
                "start_station": start_row["station"],
                "end_station": end_row["station"],
                "source_start_ft": round(float(start_row["station_ft"]), 2),
                "source_end_ft": round(float(end_row["station_ft"]), 2),
                "start_ft": round(start_ft, 2),
                "end_ft": round(end_ft, 2),
                "length_ft": round(end_ft - start_ft, 2),
                "depth_ft": start_row.get("depth_ft"),
                "boc_ft": start_row.get("boc_ft"),
                "notes": start_row.get("notes", ""),
                "date": start_row.get("date", ""),
                "crew": start_row.get("crew", ""),
                "print": start_row.get("print", ""),
                "print_numbers": start_row.get("print", ""),
                "source_file": start_row.get("source_file", ""),
                "evidence_layer_id": _group_evidence_layer_id,
                "coords": coords,
                "route_id": matched_route.get("route_id"),
                "route_name": matched_route.get("route_name"),
                "matched_route_id": matched_route.get("route_id"),
                "matched_route_name": matched_route.get("route_name"),
                "verification": {
                    "entity_type": "redline",
                    "confidence": confidence,
                    "reason": reason,
                    "route_selection_method": "independent_candidate_scoring",
                    "mapping_mode": mapping.get("mode"),
                    "anchor_type": "ambiguous_print_fallback" if filter_meta.get("ambiguous_print_fallback") else ("print_filtered_route_pool" if filter_meta.get("applied") else ("print_included_in_group_scoring" if str(start_row.get("print") or "").strip() else "station_range_group_scoring")),
                    "print_present": bool(str(start_row.get("print") or "").strip()),
                    "route_name": matched_route.get("route_name", ""),
                    "route_length_ft": round(total, 2),
                    "source_file": str(start_row.get("source_file") or ""),
                    "print": str(start_row.get("print") or ""),
                    "mapped_start_ft": round(start_ft, 2),
                    "mapped_end_ft": round(end_ft, 2),
                    "source_start_station": start_row["station"],
                    "source_end_station": end_row["station"],
                    "candidate_rankings": list(rankings),
                    "print_filter": dict(filter_meta),
                },
            }
        )

    return segments


def _group_render_is_allowed(validation: Dict[str, Any], selected_hypothesis: Dict[str, Any]) -> Tuple[bool, List[str]]:
    hard_block_reasons: List[str] = []
    soft_block_reasons: List[str] = []

    def _collect(target: List[str], values: Sequence[Any]) -> None:
        for value in values:
            text = str(value or "").strip()
            if text:
                target.append(text)

    validation_status = str(validation.get("validation_status") or "").strip().lower()
    if validation_status == "fail":
        hard_block_reasons.append("validation_status:fail")

    for gate_name in (
        "route_uniqueness_gate",
        "geometry_lock_gate",
        "chain_gate",
        "node_resolution_gate",
    ):
        gate = dict(validation.get(gate_name) or {})
        if gate and gate.get("passed") is False:
            hard_block_reasons.append(f"{gate_name}:{gate.get('reason') or 'failed'}")

    billing_gate = dict(validation.get("billing_gate") or {})
    _collect(soft_block_reasons, billing_gate.get("gate_reasons") or [])

    # Preview-safe render behavior:
    # keep stations/redlines visible on the map when only soft quality heuristics fail,
    # but preserve those failures in block_reasons so the match is still clearly non-billable.
    for gate_name in (
        "physical_feasibility_gate",
        "segment_fit_gate",
        "boundary_exactness_gate",
        "continuity_gate",
    ):
        gate = dict(validation.get(gate_name) or {})
        if gate and gate.get("passed") is False:
            soft_block_reasons.append(f"{gate_name}:{gate.get('reason') or 'failed'}")

    _collect(soft_block_reasons, selected_hypothesis.get("billable_gate_reasons") or [])

    render_allowed = len(hard_block_reasons) == 0
    reasons = hard_block_reasons if hard_block_reasons else soft_block_reasons

    deduped: List[str] = []
    seen = set()
    for reason in reasons:
        if reason not in seen:
            deduped.append(reason)
            seen.add(reason)

    return (render_allowed, deduped)


def _chain_ambiguity_preview_safe(validation: Dict[str, Any], selected_hypothesis: Dict[str, Any]) -> Tuple[bool, List[str]]:
    chain_gate = dict(validation.get("chain_gate") or {})
    node_gate = dict(validation.get("node_resolution_gate") or {})
    route_consensus_gate = dict(selected_hypothesis.get("route_consensus_gate") or {})
    authoritative_commit = dict(selected_hypothesis.get("authoritative_route_commit") or {})
    physical_gate = dict(validation.get("physical_feasibility_gate") or {})
    continuity_gate = dict(validation.get("continuity_gate") or {})
    segment_fit_gate = dict(validation.get("segment_fit_gate") or {})
    boundary_gate = dict(validation.get("boundary_exactness_gate") or {})

    if str(validation.get("validation_status") or "").strip().lower() != "pass":
        return (False, [])
    if not bool(chain_gate):
        return (False, [])
    if bool(chain_gate.get("passed", True)):
        return (False, [])
    if str(chain_gate.get("reason") or "") != "multiple_possible_chain_links":
        return (False, [])
    if not bool(node_gate) or bool(node_gate.get("passed", True)):
        return (False, [])
    if str(node_gate.get("reason") or "") != "chain_gate_failed_first":
        return (False, [])
    if not bool(physical_gate.get("passed", True)):
        return (False, [])
    if not bool(continuity_gate.get("passed", True)):
        return (False, [])
    if not bool(segment_fit_gate.get("passed", True)):
        return (False, [])
    if not bool(boundary_gate.get("passed", True)):
        return (False, [])

    details = dict(chain_gate.get("details") or {})
    near_route_start = bool(details.get("near_route_start"))
    near_route_end = bool(details.get("near_route_end"))
    if not near_route_start and not near_route_end:
        return (False, [])

    authoritative_route_id = str(
        selected_hypothesis.get("authoritative_route_id")
        or authoritative_commit.get("consensus_route_id")
        or route_consensus_gate.get("consensus_route_id")
        or ""
    ).strip()
    if not authoritative_route_id:
        return (False, [])
    consensus_route_id = str(route_consensus_gate.get("consensus_route_id") or authoritative_route_id).strip()
    if consensus_route_id and consensus_route_id != authoritative_route_id:
        return (False, [])
    if authoritative_commit and not bool(authoritative_commit.get("committed", False)):
        return (False, [])

    preview_reasons = [
        "chain_gate:multiple_possible_chain_links",
        "node_resolution_gate:chain_gate_failed_first",
        "endpoint_chain_ambiguity_preview_only",
    ]
    return (True, preview_reasons)



def _window_overlap_ft(start_a: Any, end_a: Any, start_b: Any, end_b: Any) -> float:
    try:
        a0 = float(start_a or 0.0)
        a1 = float(end_a or 0.0)
        b0 = float(start_b or 0.0)
        b1 = float(end_b or 0.0)
    except Exception:
        return 0.0
    left = max(min(a0, a1), min(b0, b1))
    right = min(max(a0, a1), max(b0, b1))
    return max(0.0, right - left)


def _print_zone_distance(current_sheets: Sequence[int], prior_sheets: Sequence[int]) -> Optional[int]:
    current_vals = [int(value) for value in current_sheets if str(value).strip().isdigit()]
    prior_vals = [int(value) for value in prior_sheets if str(value).strip().isdigit()]
    if not current_vals or not prior_vals:
        return None
    return min(abs(curr - prev) for curr in current_vals for prev in prior_vals)


def _same_print_zone(current_filter_meta: Dict[str, Any], prior_filter_meta: Dict[str, Any]) -> Dict[str, Any]:
    current_sheets = [int(value) for value in (current_filter_meta.get('sheet_numbers') or []) if str(value).strip().isdigit()]
    prior_sheets = [int(value) for value in (prior_filter_meta.get('sheet_numbers') or []) if str(value).strip().isdigit()]
    current_streets = {str(value or '').strip().upper() for value in (current_filter_meta.get('street_hints') or []) if str(value or '').strip()}
    prior_streets = {str(value or '').strip().upper() for value in (prior_filter_meta.get('street_hints') or []) if str(value or '').strip()}

    sheet_distance = _print_zone_distance(current_sheets, prior_sheets)
    shared_streets = sorted(current_streets & prior_streets)
    same_zone = False
    reason = 'no_print_zone_evidence'

    if sheet_distance is not None and sheet_distance <= 1:
        same_zone = True
        reason = 'adjacent_or_same_sheet'
    elif shared_streets and sheet_distance is not None and sheet_distance <= 2:
        same_zone = True
        reason = 'shared_street_and_near_sheet'
    elif shared_streets and not current_sheets and not prior_sheets:
        same_zone = True
        reason = 'shared_street_only'

    return {
        'same_zone': same_zone,
        'reason': reason,
        'sheet_distance': sheet_distance,
        'shared_streets': shared_streets,
        'current_sheets': current_sheets,
        'prior_sheets': prior_sheets,
    }


def _apply_within_route_anchor_separation(
    selected_hypothesis: Dict[str, Any],
    matched_route: Dict[str, Any],
    selected_ranking: Dict[str, Any],
    mapping: Dict[str, Any],
    evaluated_hypotheses: Sequence[Dict[str, Any]],
    rendered_matches: Sequence[Dict[str, Any]],
    normalized_group: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    route_id = str(matched_route.get("route_id") or "")
    current_group_id = str(normalized_group.get("group_id") or "")
    current_filter_meta = _print_sheet_hints(normalized_group.get("print_tokens") or [])
    current_start = float(selected_hypothesis.get("subsection_start_ft", 0.0) or 0.0)
    current_end = float(selected_hypothesis.get("subsection_end_ft", 0.0) or 0.0)
    current_span = max(1.0, abs(current_end - current_start))
    current_center = (current_start + current_end) / 2.0

    def _overlap_conflicts_for_window(window_start: float, window_end: float) -> List[Dict[str, Any]]:
        window_span = max(1.0, abs(window_end - window_start))
        window_center = (window_start + window_end) / 2.0
        conflicts: List[Dict[str, Any]] = []
        for prior in rendered_matches:
            if str(prior.get("route_id") or "") != route_id:
                continue
            if current_group_id and str(prior.get("group_id") or "") == current_group_id:
                continue
            # Groups from different evidence layers are separate construction events —
            # spatial overlap between them is intentional and not a conflict.
            _wra_prior_layer = str((prior.get("_normalized_group") or {}).get("evidence_layer_id") or "").strip()
            _wra_current_layer = str(normalized_group.get("evidence_layer_id") or "").strip()
            if _wra_current_layer and _wra_prior_layer and _wra_current_layer != _wra_prior_layer:
                continue

            prior_hypothesis = dict(prior.get("selected_hypothesis") or {})
            prior_start = float(prior_hypothesis.get("subsection_start_ft", 0.0) or 0.0)
            prior_end = float(prior_hypothesis.get("subsection_end_ft", 0.0) or 0.0)
            prior_span = max(1.0, abs(prior_end - prior_start))
            prior_center = (prior_start + prior_end) / 2.0
            prior_filter_meta = dict(prior.get("print_filter") or {})
            print_zone_meta = _same_print_zone(current_filter_meta, prior_filter_meta)

            overlap_ft = _window_overlap_ft(window_start, window_end, prior_start, prior_end)
            overlap_ratio = overlap_ft / max(1.0, min(window_span, prior_span))
            center_gap_ft = abs(window_center - prior_center)
            span_similarity = min(window_span, prior_span) / max(window_span, prior_span)

            hard_overlap_tolerance_ft = 5.0
            if overlap_ft > hard_overlap_tolerance_ft:
                conflicts.append({
                    "source_file": str(prior.get("source_file") or ""),
                    "route_id": route_id,
                    "overlap_ft": round(overlap_ft, 2),
                    "overlap_ratio": round(overlap_ratio, 6),
                    "center_gap_ft": round(center_gap_ft, 2),
                    "prior_start_ft": round(prior_start, 2),
                    "prior_end_ft": round(prior_end, 2),
                    "print_zone_same": bool(print_zone_meta.get("same_zone")),
                    "print_zone_reason": str(print_zone_meta.get("reason") or ""),
                    "sheet_distance": print_zone_meta.get("sheet_distance"),
                    "shared_streets": list(print_zone_meta.get("shared_streets") or []),
                })
        return conflicts

    overlap_conflicts = _overlap_conflicts_for_window(current_start, current_end)

    route_coords = matched_route.get("coords", []) or []
    route_total_ft = float(matched_route.get("length_ft", 0.0) or 0.0)

    if not overlap_conflicts:
        # Edge-clamped full-span windows on short corridors can appear "conflict free"
        # while still being poor ownership candidates for review. When the chosen window
        # nearly consumes the entire route, prefer a near-equal interior alternative if one exists.
        edge_escape_candidates: List[Dict[str, Any]] = []
        if route_coords and route_total_ft > 0.0 and current_span > 0.0:
            route_consumption_ratio = current_span / max(route_total_ft, 1.0)
            edge_locked = current_start <= 12.0 or (route_total_ft - current_end) <= 12.0
            if route_consumption_ratio >= 0.94 and edge_locked:
                windows = _generate_segment_windows(route_coords, float(normalized_group.get("span_ft") or 0.0))
                current_subsection_score = float(selected_hypothesis.get("subsection_score", 0.0) or 0.0)
                for window in windows:
                    alt_start = float(window.get("start_ft", 0.0) or 0.0)
                    alt_end = float(window.get("end_ft", 0.0) or 0.0)
                    if abs(alt_start - current_start) < 1e-6 and abs(alt_end - current_end) < 1e-6:
                        continue
                    scored = {
                        **window,
                        **_score_segment_window(route_coords, normalized_group, window),
                    }
                    bias_meta = _print_aware_window_bias(route_id, current_filter_meta, alt_start, alt_end, route_total_ft)
                    print_bias_bonus = float(bias_meta.get("bonus", 0.0) or 0.0)
                    scored["print_aware_window_bias"] = bias_meta
                    scored["window_score_base"] = round(float(scored.get("window_score", 0.0) or 0.0), 6)
                    scored["window_score"] = round(min(1.0, max(0.0, float(scored.get("window_score", 0.0) or 0.0) + print_bias_bonus)), 6)
                    alt_score = float(scored.get("window_score", 0.0) or 0.0)
                    alt_edge_clearance = min(alt_start, max(0.0, route_total_ft - alt_end))
                    if alt_edge_clearance <= 4.0:
                        continue
                    if alt_score + 0.03 < current_subsection_score:
                        continue
                    edge_escape_candidates.append(scored)
        if edge_escape_candidates:
            edge_escape_candidates.sort(
                key=lambda item: (
                    -min(float(item.get("start_ft", 0.0) or 0.0), max(0.0, route_total_ft - float(item.get("end_ft", 0.0) or 0.0))),
                    -float(item.get("window_score", 0.0) or 0.0),
                    abs(((float(item.get("start_ft", 0.0) or 0.0) + float(item.get("end_ft", 0.0) or 0.0)) / 2.0) - current_center),
                    float(item.get("start_ft", 0.0) or 0.0),
                )
            )
            best_window = edge_escape_candidates[0]
            alt_mapping = dict(best_window.get("mapping") or mapping or {})
            alt_mapping["anchor_strategy"] = "true_sliding_window_segment_scorer"
            alt_mapping["anchor_basis"] = {
                **dict(alt_mapping.get("anchor_basis") or {}),
                "print_tokens": list(normalized_group.get("print_tokens") or []),
                "filter_applied": bool(current_filter_meta.get("applied")),
                "route_total_ft": round(route_total_ft, 2),
                "group_span_ft": round(float(normalized_group.get("span_ft") or 0.0), 2),
                "segment_window_count": len(edge_escape_candidates),
                "segment_window_preview": [
                    {
                        "start_ft": round(float(item.get("start_ft", 0.0) or 0.0), 2),
                        "end_ft": round(float(item.get("end_ft", 0.0) or 0.0), 2),
                        "window_type": item.get("window_type"),
                        "window_score": round(float(item.get("window_score", 0.0) or 0.0), 6),
                    }
                    for item in edge_escape_candidates[:12]
                ],
            }
            alt_hypothesis = dict(selected_hypothesis)
            alt_hypothesis["subsection_start_ft"] = round(float(best_window.get("start_ft", 0.0) or 0.0), 2)
            alt_hypothesis["subsection_end_ft"] = round(float(best_window.get("end_ft", 0.0) or 0.0), 2)
            alt_hypothesis["subsection_score"] = round(float(best_window.get("window_score", 0.0) or 0.0), 6)
            alt_hypothesis["combined_score"] = round(
                min(1.0, float(selected_ranking.get("score", 0.0) or 0.0) + float(best_window.get("window_score", 0.0) or 0.0) * 0.35),
                6,
            )
            alt_hypothesis["anchor_method"] = "true_sliding_window_segment_scorer"
            alt_reasons = list(best_window.get("window_reasons") or [])
            if current_filter_meta.get("applied"):
                alt_reasons.append("Print-aware filtering narrowed the route family before sliding-window segment scoring.")
            alt_reasons.append("Edge-clamped full-span anchor was nudged inward to improve within-route ownership stability.")
            alt_hypothesis["anchor_reasons"] = alt_reasons
            alt_hypothesis["anchor_profile"] = dict(best_window.get("window_profile") or {})
            alt_hypothesis["mapping"] = alt_mapping
            gate = {
                "passed": True,
                "reason": "edge_locked_window_reselected_inward",
                "conflicts": [],
                "reselected": True,
                "reselected_route_id": route_id,
                "reselected_subsection_start_ft": round(float(best_window.get("start_ft", 0.0) or 0.0), 2),
                "reselected_subsection_end_ft": round(float(best_window.get("end_ft", 0.0) or 0.0), 2),
                "mode": "edge_escape_same_route",
            }
            alt_hypothesis["within_route_anchor_separation_gate"] = gate
            return alt_hypothesis, matched_route, selected_ranking, alt_mapping, gate

        gate = {
            "passed": True,
            "reason": "no_within_route_overlap_conflict",
            "conflicts": [],
            "reselected": False,
        }
        selected_hypothesis = dict(selected_hypothesis)
        selected_hypothesis["within_route_anchor_separation_gate"] = gate
        return selected_hypothesis, matched_route, selected_ranking, mapping, gate
    same_route_candidates: List[Dict[str, Any]] = []
    if route_coords and route_total_ft > 0.0:
        windows = _generate_segment_windows(route_coords, float(normalized_group.get("span_ft") or 0.0))
        for window in windows:
            alt_start = float(window.get("start_ft", 0.0) or 0.0)
            alt_end = float(window.get("end_ft", 0.0) or 0.0)
            if abs(alt_start - current_start) < 1e-6 and abs(alt_end - current_end) < 1e-6:
                continue
            scored = {
                **window,
                **_score_segment_window(route_coords, normalized_group, window),
            }
            bias_meta = _print_aware_window_bias(route_id, current_filter_meta, alt_start, alt_end, route_total_ft)
            print_bias_bonus = float(bias_meta.get("bonus", 0.0) or 0.0)
            scored["print_aware_window_bias"] = bias_meta
            scored["window_score_base"] = round(float(scored.get("window_score", 0.0) or 0.0), 6)
            scored["window_score"] = round(min(1.0, max(0.0, float(scored.get("window_score", 0.0) or 0.0) + print_bias_bonus)), 6)
            conflicts = _overlap_conflicts_for_window(alt_start, alt_end)
            if conflicts:
                continue
            same_route_candidates.append(scored)

    if same_route_candidates:
        same_route_candidates.sort(
            key=lambda item: (
                -float(item.get("window_score", 0.0) or 0.0),
                -float((item.get("print_aware_window_bias") or {}).get("bonus", 0.0) or 0.0),
                abs(float(item.get("end_ft", 0.0) or 0.0) - float(item.get("start_ft", 0.0) or 0.0) - current_span),
                abs(((float(item.get("start_ft", 0.0) or 0.0) + float(item.get("end_ft", 0.0) or 0.0)) / 2.0) - current_center),
                float(item.get("start_ft", 0.0) or 0.0),
            )
        )
        best_window = same_route_candidates[0]
        alt_mapping = dict(best_window.get("mapping") or mapping or {})
        alt_mapping["anchor_strategy"] = "true_sliding_window_segment_scorer"
        alt_mapping["anchor_basis"] = {
            **dict(alt_mapping.get("anchor_basis") or {}),
            "print_tokens": list(normalized_group.get("print_tokens") or []),
            "filter_applied": bool(current_filter_meta.get("applied")),
            "route_total_ft": round(route_total_ft, 2),
            "group_span_ft": round(float(normalized_group.get("span_ft") or 0.0), 2),
            "segment_window_count": len(same_route_candidates),
            "segment_window_preview": [
                {
                    "start_ft": round(float(item.get("start_ft", 0.0) or 0.0), 2),
                    "end_ft": round(float(item.get("end_ft", 0.0) or 0.0), 2),
                    "window_type": item.get("window_type"),
                    "window_score": round(float(item.get("window_score", 0.0) or 0.0), 6),
                }
                for item in same_route_candidates[:12]
            ],
        }
        alt_hypothesis = dict(selected_hypothesis)
        alt_hypothesis["subsection_start_ft"] = round(float(best_window.get("start_ft", 0.0) or 0.0), 2)
        alt_hypothesis["subsection_end_ft"] = round(float(best_window.get("end_ft", 0.0) or 0.0), 2)
        alt_hypothesis["subsection_score"] = round(float(best_window.get("window_score", 0.0) or 0.0), 6)
        alt_hypothesis["combined_score"] = round(
            min(
                1.0,
                float(selected_ranking.get("score", 0.0) or 0.0) + float(best_window.get("window_score", 0.0) or 0.0) * 0.35,
            ),
            6,
        )
        alt_hypothesis["anchor_method"] = "true_sliding_window_segment_scorer"
        alt_reasons = list(best_window.get("window_reasons") or [])
        if current_filter_meta.get("applied"):
            alt_reasons.append("Print-aware filtering narrowed the route family before sliding-window segment scoring.")
        alt_reasons.append("Within-route anchor reselection avoided overlap with an already rendered same-corridor group.")
        alt_hypothesis["anchor_reasons"] = alt_reasons
        alt_hypothesis["anchor_profile"] = dict(best_window.get("window_profile") or {})
        alt_hypothesis["mapping"] = alt_mapping

        gate = {
            "passed": True,
            "reason": "reselected_to_non_overlapping_subsection_same_route",
            "conflicts": overlap_conflicts,
            "reselected": True,
            "reselected_route_id": route_id,
            "reselected_subsection_start_ft": round(float(best_window.get("start_ft", 0.0) or 0.0), 2),
            "reselected_subsection_end_ft": round(float(best_window.get("end_ft", 0.0) or 0.0), 2),
            "mode": "within_route_batch_anchor_coordination",
        }
        alt_hypothesis["within_route_anchor_separation_gate"] = gate
        return alt_hypothesis, matched_route, selected_ranking, alt_mapping, gate

    for item in evaluated_hypotheses:
        hypothesis = dict(item.get("hypothesis") or {})
        alt_route = dict(item.get("matched_route") or {})
        alt_ranking = dict(item.get("ranking") or {})
        alt_mapping = dict(item.get("mapping") or {})
        if not hypothesis or not alt_route:
            continue
        if str(hypothesis.get("route_id") or "") != route_id:
            gate = {
                "passed": True,
                "reason": "reselected_to_non_conflicting_route",
                "conflicts": overlap_conflicts,
                "reselected": True,
                "reselected_route_id": str(hypothesis.get("route_id") or ""),
            }
            hypothesis["within_route_anchor_separation_gate"] = gate
            return hypothesis, alt_route, alt_ranking, alt_mapping, gate

        alt_start = float(hypothesis.get("subsection_start_ft", 0.0) or 0.0)
        alt_end = float(hypothesis.get("subsection_end_ft", 0.0) or 0.0)
        if _overlap_conflicts_for_window(alt_start, alt_end):
            continue

        gate = {
            "passed": True,
            "reason": "reselected_to_non_overlapping_subsection",
            "conflicts": overlap_conflicts,
            "reselected": True,
            "reselected_route_id": str(hypothesis.get("route_id") or ""),
            "reselected_subsection_start_ft": round(alt_start, 2),
            "reselected_subsection_end_ft": round(alt_end, 2),
            "mode": "print_zone_overlap_suppression",
        }
        hypothesis["within_route_anchor_separation_gate"] = gate
        return hypothesis, alt_route, alt_ranking, alt_mapping, gate

    gate = {
        "passed": False,
        "reason": "within_route_overlap_conflict_no_safe_alternative",
        "conflicts": overlap_conflicts,
        "reselected": False,
        "mode": "within_route_batch_anchor_coordination",
    }
    selected_hypothesis = dict(selected_hypothesis)
    selected_hypothesis["within_route_anchor_separation_gate"] = gate
    return selected_hypothesis, matched_route, selected_ranking, mapping, gate



def _batch_conflict_meta(current: Dict[str, Any], prior: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not bool(current.get("render_allowed")) or not bool(prior.get("render_allowed")):
        return None
    if str(current.get("route_id") or "") != str(prior.get("route_id") or ""):
        return None
    if str(current.get("group_id") or "") and str(current.get("group_id") or "") == str(prior.get("group_id") or ""):
        return None

    # Evidence layer check: groups from different evidence layers represent separate
    # construction events and must never be treated as conflicting duplicates.
    _bc_current_layer = str((current.get("_normalized_group") or {}).get("evidence_layer_id") or "").strip()
    _bc_prior_layer = str((prior.get("_normalized_group") or {}).get("evidence_layer_id") or "").strip()
    if _bc_current_layer and _bc_prior_layer and _bc_current_layer != _bc_prior_layer:
        return None

    current_hypothesis = dict(current.get("selected_hypothesis") or {})
    prior_hypothesis = dict(prior.get("selected_hypothesis") or {})
    current_start = float(current_hypothesis.get("subsection_start_ft", 0.0) or 0.0)
    current_end = float(current_hypothesis.get("subsection_end_ft", 0.0) or 0.0)
    prior_start = float(prior_hypothesis.get("subsection_start_ft", 0.0) or 0.0)
    prior_end = float(prior_hypothesis.get("subsection_end_ft", 0.0) or 0.0)
    current_span = max(1.0, abs(current_end - current_start))
    prior_span = max(1.0, abs(prior_end - prior_start))
    overlap_ft = _window_overlap_ft(current_start, current_end, prior_start, prior_end)
    if overlap_ft <= 0.0:
        return None

    current_filter_meta = dict(current.get("print_filter") or {})
    prior_filter_meta = dict(prior.get("print_filter") or {})
    print_zone_meta = _same_print_zone(current_filter_meta, prior_filter_meta)
    overlap_ratio = overlap_ft / max(1.0, min(current_span, prior_span))
    current_center = (current_start + current_end) / 2.0
    prior_center = (prior_start + prior_end) / 2.0
    center_gap_ft = abs(current_center - prior_center)
    span_similarity = min(current_span, prior_span) / max(current_span, prior_span)

    # Keep true duplicate / materially overlapping windows blocked, but do not let
    # tiny or edge-adjacent subsection nibbling kill otherwise distinct same-route groups.
    hard_overlap_tolerance_ft = min(30.0, max(5.0, min(current_span, prior_span) * 0.06))
    if overlap_ft <= hard_overlap_tolerance_ft:
        return None

    material_overlap = overlap_ratio >= 0.12
    near_duplicate_window = center_gap_ft <= max(25.0, min(current_span, prior_span) * 0.10)
    if not material_overlap and not near_duplicate_window:
        return None

    return {
        "route_id": str(current.get("route_id") or ""),
        "overlap_ft": round(overlap_ft, 2),
        "overlap_ratio": round(overlap_ratio, 6),
        "center_gap_ft": round(center_gap_ft, 2),
        "span_similarity": round(span_similarity, 6),
        "hard_overlap_tolerance_ft": round(hard_overlap_tolerance_ft, 2),
        "material_overlap": bool(material_overlap),
        "near_duplicate_window": bool(near_duplicate_window),
        "print_zone_same": bool(print_zone_meta.get("same_zone")),
        "print_zone_reason": str(print_zone_meta.get("reason") or ""),
        "sheet_distance": print_zone_meta.get("sheet_distance"),
        "shared_streets": list(print_zone_meta.get("shared_streets") or []),
    }

def _apply_batch_level_conflict_resolution(group_matches: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Hard no-overlap ownership engine.

    Single uploads remain unchanged.
    For batches, rendered groups are processed in deterministic priority order and each later
    same-route group must either re-anchor to a non-overlapping subsection or be blocked.
    """
    final_matches = [dict(match) for match in group_matches]
    rendered = [match for match in final_matches if bool(match.get("render_allowed"))]
    if len(rendered) <= 1:
        for match in final_matches:
            validation = dict(match.get("validation") or {})
            validation.setdefault(
                "batch_conflict_resolution_gate",
                {
                    "passed": True,
                    "reason": "single_or_zero_rendered_group",
                    "conflicts": [],
                    "mode": "hard_no_overlap_single_safe",
                },
            )
            match["validation"] = validation
        return final_matches

    rendered.sort(
        key=lambda item: (
            -float((item.get("selected_hypothesis") or {}).get("combined_score", 0.0) or 0.0),
            -float(item.get("confidence", 0.0) or 0.0),
            -float((item.get("selected_hypothesis") or {}).get("subsection_score", 0.0) or 0.0),
            -float(item.get("expected_span_ft", 0.0) or 0.0),
            str(item.get("source_file") or ""),
        )
    )

    accepted: List[Dict[str, Any]] = []
    updated_by_group: Dict[str, Dict[str, Any]] = {}

    for candidate in rendered:
        updated = dict(candidate)
        group_id = str(updated.get("group_id") or "")
        validation = dict(updated.get("validation") or {})
        rankings = list(updated.get("candidate_rankings") or [])
        selected_hypothesis = dict(updated.get("selected_hypothesis") or {})
        matched_route = dict(updated.get("_matched_route") or {})
        mapping = dict(updated.get("mapping") or {})
        normalized_group = dict(updated.get("_normalized_group") or {})
        evaluated_hypotheses = list(updated.get("_evaluated_hypotheses") or [])

        selected_ranking = next(
            (dict(item) for item in rankings if str(item.get("route_id") or "") == str(selected_hypothesis.get("route_id") or "")),
            dict(rankings[0]) if rankings else {},
        )

        if accepted and matched_route and normalized_group:
            selected_hypothesis, matched_route, selected_ranking, mapping, within_gate = _apply_within_route_anchor_separation(
                selected_hypothesis,
                matched_route,
                selected_ranking,
                mapping,
                evaluated_hypotheses,
                accepted,
                normalized_group,
            )
            validation["within_route_anchor_separation_gate"] = dict(within_gate)

            group_rows = list(normalized_group.get("station_rows") or [])
            group_station_points, mapping = _build_station_points_for_group(
                group_rows,
                matched_route,
                rankings,
                dict(updated.get("print_filter") or {}),
                mapping_override=mapping,
            )
            group_redline_segments = _build_redline_segments_for_group(
                group_rows,
                matched_route,
                rankings,
                mapping,
                dict(updated.get("print_filter") or {}),
            )
            updated["group_station_points"] = list(group_station_points)
            updated["group_redline_segments"] = list(group_redline_segments)
            updated["mapping"] = dict(mapping)
            updated["selected_hypothesis"] = dict(selected_hypothesis)
            updated["route_id"] = matched_route.get("route_id")
            updated["route_name"] = matched_route.get("route_name")
            updated["source_folder"] = matched_route.get("source_folder")
            updated["route_role"] = matched_route.get("route_role")

        candidate_conflicts = []
        for prior in accepted:
            conflict = _batch_conflict_meta(updated, prior)
            if conflict:
                candidate_conflicts.append({
                    **conflict,
                    "conflicts_with_source_file": str(prior.get("source_file") or ""),
                })

        group_station_points = list(updated.get("group_station_points") or [])
        group_redline_segments = list(updated.get("group_redline_segments") or [])
        has_built_geometry = bool(group_station_points) or bool(group_redline_segments)

        hard_conflicts = []
        salvageable_conflicts = []
        for conflict in candidate_conflicts:
            overlap_ratio = float(conflict.get("overlap_ratio", 0.0) or 0.0)
            overlap_ft = float(conflict.get("overlap_ft", 0.0) or 0.0)
            tolerance_ft = float(conflict.get("hard_overlap_tolerance_ft", 0.0) or 0.0)
            span_similarity = float(conflict.get("span_similarity", 0.0) or 0.0)
            near_duplicate_window = bool(conflict.get("near_duplicate_window"))

            true_duplicate = (
                near_duplicate_window
                or (overlap_ratio >= 0.5 and span_similarity >= 0.7)
                or overlap_ft >= max(80.0, tolerance_ft * 3.0)
            )
            if true_duplicate:
                hard_conflicts.append({**conflict, "true_duplicate": True})
            else:
                salvageable_conflicts.append({**conflict, "true_duplicate": False})

        if candidate_conflicts and (not has_built_geometry or hard_conflicts):
            updated["render_allowed"] = False
            validation["batch_conflict_resolution_gate"] = {
                "passed": False,
                "reason": "hard_no_overlap_conflict_no_safe_alternative",
                "conflicts": hard_conflicts or candidate_conflicts,
                "salvageable_conflicts": salvageable_conflicts,
                "mode": "hard_no_overlap_authoritative",
            }
            render_block_reasons = [reason for reason in list(updated.get("render_block_reasons") or []) if str(reason)]
            if "batch_level_conflict_resolution" not in render_block_reasons:
                render_block_reasons.append("batch_level_conflict_resolution")
            updated["render_block_reasons"] = render_block_reasons
            validation["render_gate"] = {
                "render_allowed": False,
                "block_reasons": list(render_block_reasons),
                "mode": "hard_no_overlap_authoritative",
            }
            updated["rendered_station_point_count"] = 0
            updated["rendered_redline_segment_count"] = 0
        else:
            updated["render_allowed"] = True
            updated["rendered_station_point_count"] = len(group_station_points)
            updated["rendered_redline_segment_count"] = len(group_redline_segments)
            validation["batch_conflict_resolution_gate"] = {
                "passed": True,
                "reason": "owned_non_overlapping_subsection" if not candidate_conflicts else "salvaged_distinct_subsection_with_geometry",
                "conflicts": [],
                "salvageable_conflicts": salvageable_conflicts,
                "mode": "hard_no_overlap_authoritative",
            }
            validation["render_gate"] = {
                "render_allowed": True,
                "block_reasons": [
                    reason
                    for reason in list((validation.get("render_gate") or {}).get("block_reasons") or [])
                    if str(reason) != "batch_level_conflict_resolution"
                ],
                "mode": "hard_no_overlap_authoritative",
            }
            accepted.append(updated)

        updated["validation"] = validation
        updated_by_group[group_id] = updated

    merged: List[Dict[str, Any]] = []
    for match in final_matches:
        group_id = str(match.get("group_id") or "")
        if group_id in updated_by_group:
            merged.append(updated_by_group[group_id])
        else:
            validation = dict(match.get("validation") or {})
            validation.setdefault(
                "batch_conflict_resolution_gate",
                {
                    "passed": True,
                    "reason": "not_render_eligible_before_batch_pass",
                    "conflicts": [],
                    "mode": "hard_no_overlap_authoritative",
                },
            )
            match["validation"] = validation
            merged.append(match)

    return merged




def _resolve_batch_route_ownership(group_matches: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ordered_matches = [dict(match) for match in group_matches]
    assigned_by_route: Dict[str, List[Dict[str, Any]]] = {}
    resolved_matches: List[Dict[str, Any]] = []

    for match in ordered_matches:
        route_id = str(match.get("route_id") or "")
        selected_hypothesis = dict(match.get("selected_hypothesis") or {})
        matched_route = dict(match.get("_matched_route") or {})
        selected_ranking = dict(match.get("score_breakdown") or {})
        mapping = dict(match.get("mapping") or {})
        normalized_group = dict(match.get("_normalized_group") or {})
        evaluated_hypotheses = list(match.get("_evaluated_hypotheses") or [])
        prior_assigned = list(assigned_by_route.get(route_id, []))

        if route_id and normalized_group and evaluated_hypotheses:
            selected_hypothesis, matched_route, _selected_ranking_unused, mapping, within_gate = _apply_within_route_anchor_separation(
                selected_hypothesis,
                matched_route,
                selected_ranking,
                mapping,
                evaluated_hypotheses,
                prior_assigned,
                normalized_group,
            )
            selected_hypothesis, matched_route, _selected_ranking_unused, mapping, authoritative_route_id = _authoritative_selection_bundle(
                selected_hypothesis,
                matched_route,
                selected_ranking,
                mapping,
                evaluated_hypotheses,
            )

            group_rows = list(normalized_group.get("station_rows") or [])
            candidate_rankings = list(match.get("candidate_rankings") or [])
            filter_meta = dict(match.get("print_filter") or {})
            group_station_points, mapping = _build_station_points_for_group(group_rows, matched_route, candidate_rankings, filter_meta, mapping)
            group_redline_segments = _build_redline_segments_for_group(group_rows, matched_route, candidate_rankings, mapping, filter_meta)

            if authoritative_route_id:
                for point in group_station_points:
                    point["route_id"] = authoritative_route_id
                    point["matched_route_id"] = authoritative_route_id
                    point["matched_route_name"] = matched_route.get("route_name")
                for segment in group_redline_segments:
                    segment["route_id"] = authoritative_route_id
                    segment["matched_route_id"] = authoritative_route_id
                    segment["route_name"] = matched_route.get("route_name")
                    segment["matched_route_name"] = matched_route.get("route_name")

            validation = dict(match.get("validation") or {})
            validation["within_route_anchor_separation_gate"] = dict(selected_hypothesis.get("within_route_anchor_separation_gate") or within_gate)
            validation["batch_conflict_resolution_gate"] = {
                "passed": bool((selected_hypothesis.get("within_route_anchor_separation_gate") or within_gate or {}).get("passed", True)),
                "reason": str((selected_hypothesis.get("within_route_anchor_separation_gate") or within_gate or {}).get("reason") or "owned_non_overlapping_subsection"),
                "conflicts": list((selected_hypothesis.get("within_route_anchor_separation_gate") or within_gate or {}).get("conflicts") or []),
                "mode": "hard_no_overlap_authoritative",
            }
            validation["render_gate"] = {
                "render_allowed": True,
                "block_reasons": [],
                "mode": "hard_no_overlap_authoritative",
            }

            match["selected_hypothesis"] = dict(selected_hypothesis)
            match["mapping"] = dict(mapping)
            match["validation"] = validation
            match["group_station_points"] = list(group_station_points)
            match["group_redline_segments"] = list(group_redline_segments)
            match["render_allowed"] = True
            match["render_block_reasons"] = []
            match["rendered_station_point_count"] = len(group_station_points)
            match["rendered_redline_segment_count"] = len(group_redline_segments)
            match["route_id"] = matched_route.get("route_id")
            match["route_name"] = matched_route.get("route_name")
            match["source_folder"] = matched_route.get("source_folder")

        resolved_matches.append(match)
        if route_id and bool(match.get("render_allowed")):
            assigned_by_route.setdefault(route_id, []).append(match)

    return resolved_matches

def _is_ambiguous_print_group(normalized_group: Dict[str, Any]) -> bool:
    """Returns True when a bore-log group carries 3+ distinct print tokens.
    Broad print spans make strict print-to-route filtering unreliable, so these
    groups are eligible for the geometry-proximity fallback pass."""
    return len(list(normalized_group.get("print_tokens") or [])) >= 3


def _fallback_rankings_geometry_only(
    group_rows: Sequence[Dict[str, Any]],
    normalized_group: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], List[Dict[str, Any]]]:
    """Geometry-proximity fallback for groups whose print hints are too broad.
    Strips print_tokens so _build_candidate_pool_for_group uses the full route
    catalog and relies on spatial/span scoring only.  The returned filter_meta
    carries ambiguous_print_fallback=True so downstream code can mark segments.
    Does NOT modify normalized_group (the original evidence_layer_id is preserved)."""
    fallback_group = dict(normalized_group)
    fallback_group["print_tokens"] = []          # bypass print filter — geometry only
    rankings, filter_meta, all_rankings = _candidate_rankings_for_group_v2(group_rows, fallback_group)
    filter_meta = dict(filter_meta)
    filter_meta["ambiguous_print_fallback"] = True
    filter_meta["original_print_tokens"] = list(normalized_group.get("print_tokens") or [])
    filter_meta["fallback_reason"] = "ambiguous_print_hints_geometry_only"
    return rankings, filter_meta, all_rankings


# ---------------------------------------------------------------------------
# Engineering Plan Signal Extraction — Phase 1
# Parses structured metadata/signals from uploaded engineering plan records
# using only filename text and fields already stored at upload time.
# No OCR, no external services, no PDF content parsing.
# Signals are stored in STATE["engineering_plan_signals"] for Phase 2 use.
# ---------------------------------------------------------------------------

# ── Pattern constants (compiled once at import time) ─────────────────────────

# Explicit print/sheet markers in filenames
_EP_PRINT_PATS: List[re.Pattern] = [
    re.compile(r'\bprint[.\-_ ]?(\d{1,2})\b', re.IGNORECASE),   # Print3, print-2
    re.compile(r'\bsht[.\-_ ]?(\d{1,2})\b',   re.IGNORECASE),   # Sht04, sht_3
    re.compile(r'\bsheet[.\-_ ]?(\d{1,2})\b', re.IGNORECASE),   # Sheet04, sheet 3
    re.compile(r'\b[pP][.\-_](\d{1,2})\b'),                      # P-3, P_02
    re.compile(r'\b[sS][.\-_](\d{1,2})\b'),                      # S-12, s_4
]

# Phase / document-type keywords → canonical label
_EP_PHASE_PATS: List[Tuple[str, re.Pattern]] = [
    ("phase_{n}",    re.compile(r'\bphase[.\-_ ]?(\d+)\b',    re.IGNORECASE)),
    ("permit",       re.compile(r'\bpermit\b',                  re.IGNORECASE)),
    ("construction", re.compile(r'\bconstruction\b',            re.IGNORECASE)),
    ("redline",      re.compile(r'\bredlines?\b',               re.IGNORECASE)),
    ("asbuilt",      re.compile(r'\bas[.\-_]?built\b',          re.IGNORECASE)),
    ("revision",     re.compile(r'\brevisions?\b',              re.IGNORECASE)),
    ("preliminary",  re.compile(r'\bpreliminary\b',             re.IGNORECASE)),
    ("final",        re.compile(r'\bfinal\b',                   re.IGNORECASE)),
    ("approved",     re.compile(r'\bapproved\b',                re.IGNORECASE)),
    ("draft",        re.compile(r'\bdraft\b',                   re.IGNORECASE)),
]

# Route / infrastructure-type keywords
_EP_ROUTE_KEYWORDS: List[str] = [
    "underground", "ug", "aerial", "ohg", "ohp", "bore", "boring",
    "trench", "trenching", "fiber", "fibre", "mainline", "lateral",
    "backbone", "drop", "conduit", "duct", "cable", "osp",
    "splice", "splicing", "riser", "vault", "handhole",
]

# Date patterns: (compiled, is_ymd_order)
_EP_DATE_PATS: List[Tuple[re.Pattern, bool]] = [
    (re.compile(r'(\d{4})[.\-_/](\d{2})[.\-_/](\d{2})'), True),   # 2024-01-15
    (re.compile(r'(\d{2})[.\-_/](\d{2})[.\-_/](\d{4})'), False),  # 01-15-2024
]

# Revision marker
_EP_REVISION_RE: re.Pattern = re.compile(
    r'\brev(?:ision)?[.\-_ ]?([a-zA-Z0-9]{1,3})\b', re.IGNORECASE
)

# Tokens to discard from raw text (file-extension fragments, stop words)
_EP_NOISE_TOKENS: set = {
    "", "pdf", "png", "jpg", "jpeg", "tif", "tiff", "dwg", "dxf",
    "the", "and", "for", "of", "to", "a", "an", "in", "on", "at",
    "by", "be", "is", "it", "as",
}


def _extract_engineering_plan_signals(plan: Dict[str, Any]) -> Dict[str, Any]:
    """Extract structured signals from a single engineering plan record.

    Inputs used:
      - original_filename    (primary text source)
      - plan_date            (user-supplied date — highest priority)
      - print_numbers        (user-supplied — highest priority for print tokens)
      - sheet_numbers        (user-supplied — secondary print tokens)
      - street_hints         (user-supplied route context)
      - notes                (user-supplied free text)

    Returns a signal dict with keys:
      plan_id, source_file, print_tokens, route_hints, phase_hints,
      date, revision, raw_text_tokens
    """
    plan_id = str(plan.get("plan_id") or "").strip()
    source_file = str(plan.get("original_filename") or "").strip()

    # Strip file extension and normalise separators to spaces for scanning
    fname_stem = re.sub(r'\.[^.]+$', '', source_file)
    fname_scan = fname_stem  # keep original casing for pattern matching

    # Aggregate all available text for phase/route keyword scanning
    extra_text = " ".join(filter(None, [
        str(plan.get("street_hints") or ""),
        str(plan.get("notes") or ""),
    ]))
    full_scan = f"{fname_scan} {extra_text}"

    # ── 1. Print / sheet tokens ───────────────────────────────────────────────
    print_tokens: List[str] = []

    # User-provided fields are highest-priority — process first
    for field in ("print_numbers", "sheet_numbers"):
        raw = str(plan.get(field) or "").strip()
        if raw:
            for tok in _parse_print_tokens(raw):
                if tok not in print_tokens:
                    print_tokens.append(tok)

    # Explicit patterns in filename (only add tokens not already from metadata)
    for pat in _EP_PRINT_PATS:
        for m in pat.finditer(fname_scan):
            raw_num = m.group(1).lstrip("0") or "0"
            try:
                num_val = int(raw_num)
            except ValueError:
                continue
            if 1 <= num_val <= 30:
                tok = str(num_val)
                if tok not in print_tokens:
                    print_tokens.append(tok)

    # Last resort: bare 1–2-digit numbers from filename when nothing else matched
    if not print_tokens:
        for m in re.finditer(r'\b(\d{1,2})\b', fname_scan):
            raw_num = m.group(1).lstrip("0") or "0"
            try:
                num_val = int(raw_num)
            except ValueError:
                continue
            if 1 <= num_val <= 30:
                tok = str(num_val)
                if tok not in print_tokens:
                    print_tokens.append(tok)

    # Sort numerically for stable output
    print_tokens = sorted(set(print_tokens), key=lambda x: int(x))

    # ── 2. Phase / document-type hints ───────────────────────────────────────
    phase_hints: List[str] = []
    for label, pat in _EP_PHASE_PATS:
        m = pat.search(full_scan)
        if m:
            if "{n}" in label:
                resolved = label.replace("{n}", m.group(1))
            else:
                resolved = label
            if resolved not in phase_hints:
                phase_hints.append(resolved)

    # ── 3. Route / infrastructure hints ──────────────────────────────────────
    route_hints: List[str] = []
    full_lower = full_scan.lower()
    for kw in _EP_ROUTE_KEYWORDS:
        if re.search(r'\b' + re.escape(kw) + r'\b', full_lower):
            if kw not in route_hints:
                route_hints.append(kw)

    # Preserve street_hints verbatim as a route context hint (truncated)
    street_raw = str(plan.get("street_hints") or "").strip()
    if street_raw:
        route_hints.append(f"street:{street_raw[:80]}")

    # ── 4. Date and revision ──────────────────────────────────────────────────
    extracted_date: Optional[str] = None
    extracted_revision: Optional[str] = None

    # plan_date field is highest-priority (user-confirmed)
    plan_date_raw = str(plan.get("plan_date") or "").strip()
    if plan_date_raw:
        extracted_date = plan_date_raw[:10]

    # Fall back to scanning the filename for date patterns
    if not extracted_date:
        for dpat, is_ymd in _EP_DATE_PATS:
            m = dpat.search(fname_scan)
            if m:
                g = m.groups()
                try:
                    if is_ymd:
                        candidate = f"{g[0]}-{g[1]}-{g[2]}"
                    else:
                        candidate = f"{g[2]}-{g[0]}-{g[1]}"
                    datetime.strptime(candidate, "%Y-%m-%d")  # validate
                    extracted_date = candidate
                    break
                except Exception:
                    continue

    # Revision token
    rev_m = _EP_REVISION_RE.search(fname_scan)
    if rev_m:
        extracted_revision = f"rev_{rev_m.group(1).lower()}"

    # ── 5. Raw text tokens ────────────────────────────────────────────────────
    all_text = f"{fname_stem} {extra_text}"
    token_parts = re.split(r'[^a-z0-9]+', all_text.lower())
    raw_text_tokens: List[str] = sorted({
        p for p in token_parts
        if p and p not in _EP_NOISE_TOKENS and len(p) >= 2
    })[:60]  # cap to keep output bounded

    return {
        "plan_id": plan_id,
        "source_file": source_file,
        "print_tokens": print_tokens,
        "route_hints": route_hints,
        "phase_hints": phase_hints,
        "date": extracted_date,
        "revision": extracted_revision,
        "raw_text_tokens": raw_text_tokens,
    }


def _build_engineering_plan_signals_for_session(session_id: str) -> List[Dict[str, Any]]:
    """Load all engineering plans for a session and extract signals from each.
    Non-fatal — returns [] on any error."""
    if not session_id:
        return []
    try:
        plans = _load_engineering_plan_index_for_session(session_id)
        return [_extract_engineering_plan_signals(p) for p in plans]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Phase 3 — Ambiguity classification using plan signals
# Diagnostic-only. Never changes selected_route_id or render_allowed.
# ---------------------------------------------------------------------------

# Render-block / gate reasons that indicate a chain/route ambiguity Phase 3 can assess.
_PHASE3_AMBIGUOUS_REASONS: frozenset = frozenset({
    "multiple_possible_chain_links",
    "chain_gate:multiple_possible_chain_links",
    "route_uniqueness_gate:multiple_billable_routes",
    "node_resolution_gate:chain_gate_failed_first",
})


def _classify_group_ambiguity(
    render_block_reasons: List[str],
    normalized_group: Dict[str, Any],
    validation: Dict[str, Any],
    matched_route: Dict[str, Any],
    plan_signals: List[Dict[str, Any]],
) -> Tuple[str, Dict[str, Any]]:
    """Classify the ambiguity status of a bore-log group using plan signals.

    Returns (status, meta) where status is one of:
      "not_ambiguous"           — no target chain/route-uniqueness reasons present
      "not_applicable"          — ambiguous but no matched route to evaluate
      "not_enough_plan_evidence"— ambiguous, but plan signals can't resolve it
      "still_review_required"   — ambiguous, plan exists but doesn't confirm selection
      "resolved_by_plan_signal" — plan's numeric tokens clearly confirm selected route

    NEVER changes render_allowed, render_block_reasons, selected_route_id, or
    any gate state. Purely diagnostic.
    """
    # ── 1. Detect target ambiguity reasons ───────────────────────────────────
    block_reasons: List[str] = list(render_block_reasons or [])
    detected: List[str] = [r for r in block_reasons if r in _PHASE3_AMBIGUOUS_REASONS]

    # Also check validation gates directly — groups that were rescued by the
    # ambiguous-chain render override still carry the chain failure in validation
    # but their render_block_reasons may have been partially stripped.
    chain_gate = dict((validation or {}).get("chain_gate") or {})
    chain_gate_reason = str(chain_gate.get("reason") or "")
    if (chain_gate_reason in _PHASE3_AMBIGUOUS_REASONS
            and chain_gate_reason not in detected
            and chain_gate.get("passed") is False):
        detected.append(chain_gate_reason)

    ru_gate = dict((validation or {}).get("route_uniqueness_gate") or {})
    ru_gate_reason = str(ru_gate.get("reason") or "")
    if (ru_gate_reason in _PHASE3_AMBIGUOUS_REASONS
            and ru_gate_reason not in detected
            and ru_gate.get("passed") is False):
        detected.append(ru_gate_reason)

    if not detected:
        return "not_ambiguous", {
            "ambiguous_reasons_detected": [],
            "plan_signal_used": False,
            "reason": "no_target_ambiguity_reasons_present",
        }

    # ── 2. Need a selected route to compare against ──────────────────────────
    selected_route_id = str((matched_route or {}).get("route_id") or "").strip()
    if not selected_route_id:
        return "not_applicable", {
            "ambiguous_reasons_detected": detected,
            "plan_signal_used": False,
            "reason": "no_selected_route_available",
            "matched_plan_id": None,
            "matched_plan_name": None,
            "matched_tokens": [],
            "candidate_route_ids_considered": [],
            "selected_route_id_before": None,
            "selected_route_id_after": None,
            "route_changed": False,
            "confidence_note": "cannot_evaluate_without_selected_route",
        }

    # ── 3. Require numeric print tokens in the group ──────────────────────────
    numeric_group_tokens: set = {
        str(t) for t in (normalized_group.get("print_tokens") or [])
        if str(t).isdigit()
    }

    _no_evidence_base: Dict[str, Any] = {
        "ambiguous_reasons_detected": detected,
        "plan_signal_used": False,
        "matched_plan_id": None,
        "matched_plan_name": None,
        "matched_tokens": [],
        "candidate_route_ids_considered": [],
        "selected_route_id_before": selected_route_id,
        "selected_route_id_after": selected_route_id,
        "route_changed": False,
    }

    if not plan_signals:
        return "not_enough_plan_evidence", {
            **_no_evidence_base,
            "reason": "no_plan_signals_uploaded",
            "confidence_note": "upload_engineering_plans_to_enable_resolution",
        }

    if not numeric_group_tokens:
        return "not_enough_plan_evidence", {
            **_no_evidence_base,
            "reason": "no_numeric_print_tokens_in_group",
            "confidence_note": "group_has_no_numeric_tokens_to_match_plans",
        }

    # ── 4. Find best plan with numeric token overlap → route hint ─────────────
    best_plan_id:     Optional[str] = None
    best_plan_name:   Optional[str] = None
    best_matched_toks: List[str] = []
    best_hint_routes:  List[str] = []

    for signal in plan_signals:
        plan_id = str(signal.get("plan_id") or "").strip()
        if not plan_id:
            continue

        plan_print = {str(t) for t in (signal.get("print_tokens") or [])}
        plan_raw   = {str(t) for t in (signal.get("raw_text_tokens") or [])}
        numeric_plan_toks: set = {t for t in (plan_print | plan_raw) if t.isdigit()}

        overlap = numeric_group_tokens & numeric_plan_toks
        if not overlap:
            continue

        # Resolve overlap tokens to route_ids via the print index.
        hint_route_ids: List[str] = []
        for token in sorted(overlap):
            entry = CURRENT_PACKET_PRINT_SHEET_INDEX.get(token)
            if entry:
                for rid in (entry.get("route_ids") or []):
                    if rid not in hint_route_ids:
                        hint_route_ids.append(rid)

        if not hint_route_ids:
            continue  # tokens overlapped but don't resolve to any known route

        if len(overlap) > len(best_matched_toks):
            best_plan_id    = plan_id
            best_plan_name  = str(signal.get("source_file") or "")
            best_matched_toks = sorted(overlap)
            best_hint_routes  = hint_route_ids

    if not best_plan_id:
        return "not_enough_plan_evidence", {
            **_no_evidence_base,
            "reason": "numeric_overlap_found_but_no_plan_resolves_to_route",
            "confidence_note": "plan_tokens_do_not_map_to_known_route_ids",
        }

    # ── 5. Classify: does the plan confirm the selected route? ────────────────
    plan_supports_selected = selected_route_id in best_hint_routes
    single_hint_route      = len(best_hint_routes) == 1

    meta: Dict[str, Any] = {
        "ambiguous_reasons_detected":    detected,
        "plan_signal_used":              True,
        "matched_plan_id":               best_plan_id,
        "matched_plan_name":             best_plan_name,
        "matched_tokens":                best_matched_toks,
        "candidate_route_ids_considered": best_hint_routes,
        "selected_route_id_before":      selected_route_id,
        "selected_route_id_after":       selected_route_id,  # Phase 3: never changes route
        "route_changed":                 False,
    }

    if plan_supports_selected:
        if single_hint_route:
            confidence_note = "plan_uniquely_confirms_selected_route"
        else:
            confidence_note = "plan_supports_selected_route_among_multiple_candidates"
        return "resolved_by_plan_signal", {
            **meta,
            "confidence_note": confidence_note,
            "reason": "plan_numeric_tokens_confirm_selected_route",
        }
    else:
        return "still_review_required", {
            **meta,
            "confidence_note": "plan_tokens_point_to_different_route_than_selected",
            "reason": "plan_does_not_confirm_selected_route_manual_review_needed",
        }


# ---------------------------------------------------------------------------
# Plan-aware ranking bias — Phase 2
# Controlled, numeric-only, capped at +0.03 per entry.
# Reorder gate: only allowed when top-2 gap ≤ 0.10 before bias.
# Consumes already-extracted plan_signals (not raw plan records).
# Never removes candidates. Never touches validation/render gates.
# ---------------------------------------------------------------------------

_PLAN_BIAS_MAX_BOOST: float = 0.03     # hard cap per ranking entry
_PLAN_BIAS_REORDER_GAP: float = 0.10  # max top-2 gap that permits reorder


def _plan_aware_ranking_boost(
    rankings: List[Dict[str, Any]],
    normalized_group: Dict[str, Any],
    plan_signals: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Phase 2 controlled plan-aware ranking bias.

    Eligibility rules:
      - Overlap must be on STRICTLY NUMERIC tokens only (e.g. "18", "3").
        Non-numeric words (phase, brenham, report, etc.) are ignored entirely.
      - Overlap must appear in plan print_tokens OR plan raw_text_tokens.
      - Route hint is resolved via CURRENT_PACKET_PRINT_SHEET_INDEX for each
        overlapping token; only routes in the hint set receive a boost.

    Scoring rules:
      - Boost per entry = min(_PLAN_BIAS_MAX_BOOST, len(overlap) * 0.01).
        So 1 shared token → +0.01, 2 → +0.02, 3+ → capped at +0.03.
      - original_score and plan_adjusted_score are both written to the entry.
      - combined_score / score are updated with the boosted value.

    Reorder gate:
      - Re-sort is only applied when top-2 gap ≤ _PLAN_BIAS_REORDER_GAP before bias.
      - If only one candidate exists, diagnostics are still recorded but ordering
        is irrelevant and re-sort is skipped.

    Returns (rankings_possibly_reordered, plan_bias_meta).
    plan_bias_meta.applied is True only when at least one entry received a boost.
    """
    _no_plans_meta: Dict[str, Any] = {
        "applied": False,
        "plans_checked": len(plan_signals),
        "reason_if_not_applied": "no_rankings_or_no_plan_signals",
    }
    if not rankings or not plan_signals:
        return rankings, _no_plans_meta

    # ── Numeric token filter ─────────────────────────────────────────────────
    group_print_tokens: set = {str(t) for t in (normalized_group.get("print_tokens") or [])}
    numeric_group_tokens: set = {t for t in group_print_tokens if t.isdigit()}

    if not numeric_group_tokens:
        return rankings, {
            "applied": False,
            "plans_checked": len(plan_signals),
            "reason_if_not_applied": "no_numeric_print_tokens_in_group",
            "group_print_tokens": sorted(group_print_tokens),
        }

    # ── Build per-plan association map ────────────────────────────────────────
    # plan_id -> (matched_numeric_tokens, hint_route_ids)
    plan_assoc: Dict[str, Tuple[set, List[str]]] = {}

    for signal in plan_signals:
        plan_id = str(signal.get("plan_id") or "").strip()
        if not plan_id:
            continue

        # Candidate token pool: plan print_tokens UNION raw_text_tokens,
        # filtered to strictly numeric values.
        plan_print = {str(t) for t in (signal.get("print_tokens") or [])}
        plan_raw   = {str(t) for t in (signal.get("raw_text_tokens") or [])}
        numeric_plan_tokens: set = {t for t in (plan_print | plan_raw) if t.isdigit()}

        overlap = numeric_group_tokens & numeric_plan_tokens
        if not overlap:
            continue  # no numeric overlap → skip this plan

        # Resolve route_ids for each overlapping token via the print index.
        hint_route_ids: List[str] = []
        for token in sorted(overlap):
            entry = CURRENT_PACKET_PRINT_SHEET_INDEX.get(token)
            if entry:
                for rid in (entry.get("route_ids") or []):
                    if rid not in hint_route_ids:
                        hint_route_ids.append(rid)

        if not hint_route_ids:
            continue  # tokens matched but don't resolve to any known route

        plan_assoc[plan_id] = (overlap, hint_route_ids)

    if not plan_assoc:
        return rankings, {
            "applied": False,
            "plans_checked": len(plan_signals),
            "reason_if_not_applied": "no_numeric_token_overlap_resolves_to_route",
            "group_numeric_tokens": sorted(numeric_group_tokens),
        }

    # ── Gap gate: measure top-2 spread before any boost ──────────────────────
    top_score    = float(rankings[0].get("combined_score") or rankings[0].get("score") or 0.0)
    second_score = float(rankings[1].get("combined_score") or rankings[1].get("score") or 0.0) \
                   if len(rankings) > 1 else top_score
    gap_before_bias  = round(top_score - second_score, 6)
    allowed_to_reorder = len(rankings) > 1 and gap_before_bias <= _PLAN_BIAS_REORDER_GAP

    # ── Collect best-plan metadata for diagnostics ────────────────────────────
    all_matched_tokens: set = set()
    best_plan_id:   Optional[str] = None
    best_plan_name: Optional[str] = None
    best_overlap_count = 0

    for pid, (overlap_toks, _) in plan_assoc.items():
        all_matched_tokens |= overlap_toks
        if len(overlap_toks) > best_overlap_count:
            best_overlap_count = len(overlap_toks)
            best_plan_id = pid
            for sig in plan_signals:
                if str(sig.get("plan_id") or "") == pid:
                    best_plan_name = str(sig.get("source_file") or "")
                    break

    # ── Apply boost ───────────────────────────────────────────────────────────
    boosted: List[Dict[str, Any]] = []
    any_boosted = False

    for ranking in rankings:
        ranking = dict(ranking)
        route_id = str(ranking.get("route_id") or "").strip()

        route_boost = 0.0
        entry_boost_reasons: List[str] = []

        for pid, (overlap_toks, hint_route_ids) in plan_assoc.items():
            if route_id in hint_route_ids:
                # +0.01 per overlapping numeric token, capped at _PLAN_BIAS_MAX_BOOST
                candidate_boost = round(
                    min(_PLAN_BIAS_MAX_BOOST, len(overlap_toks) * 0.01), 6
                )
                if candidate_boost > route_boost:
                    route_boost = candidate_boost
                    entry_boost_reasons.append(
                        f"plan:{pid[:8]}|tokens:{sorted(overlap_toks)}"
                        f"|boost:+{candidate_boost:.3f}"
                    )

        if route_boost > 0:
            old_score = float(ranking.get("combined_score") or ranking.get("score") or 0.0)
            new_score = round(min(1.0, old_score + route_boost), 6)
            ranking["original_score"]      = round(old_score, 6)
            ranking["plan_adjusted_score"] = new_score
            ranking["combined_score"]      = new_score
            ranking["score"]               = new_score
            ranking["plan_bias"] = {
                "applied": True,
                "boost":   round(route_boost, 6),
                "reasons": entry_boost_reasons,
            }
            any_boosted = True
        else:
            ranking.setdefault("plan_bias", {"applied": False})

        boosted.append(ranking)

    # ── Conditional re-sort ───────────────────────────────────────────────────
    if allowed_to_reorder and any_boosted:
        boosted.sort(key=lambda item: (
            -float(item.get("combined_score") or item.get("score") or 0.0),
            float(item.get("length_gap_ft") or 0.0),
            float(item.get("route_length_ft") or 0.0),
            str(item.get("route_name") or ""),
        ))

    return boosted, {
        "applied":              any_boosted,
        "best_plan_id":         best_plan_id,
        "best_plan_name":       best_plan_name,
        "matched_tokens":       sorted(all_matched_tokens),
        "association_reasons":  [f"numeric_print_overlap:{sorted(all_matched_tokens)}"],
        "plans_checked":        len(plan_signals),
        "plans_associated":     len(plan_assoc),
        "max_boost":            _PLAN_BIAS_MAX_BOOST,
        "allowed_to_reorder":   allowed_to_reorder,
        "top_score_gap_before_bias": gap_before_bias,
        "reason_if_not_applied": None if any_boosted else "no_ranking_matched_hint_route_ids",
    }


def _rebuild_field_data_outputs() -> None:
    rows = STATE.get("committed_rows", []) or []
    groups = _group_rows_for_matching(rows)

    # Load engineering plans once for the whole rebuild pass.
    # Used by _plan_aware_ranking_boost — non-fatal if unavailable.
    _session_id_hint = str(STATE.get("_session_id_hint") or "").strip()
    _eng_plans_for_session: List[Dict[str, Any]] = []
    try:
        if _session_id_hint:
            _eng_plans_for_session = _load_engineering_plan_index_for_session(_session_id_hint)
    except Exception:
        _eng_plans_for_session = []

    # Extract and store structured plan signals in STATE for Phase 2 access.
    # This is Phase 1 only — signals are NOT yet used in scoring.
    try:
        _plan_signals = [_extract_engineering_plan_signals(p) for p in _eng_plans_for_session]
    except Exception:
        _plan_signals = []
    STATE["engineering_plan_signals"] = _plan_signals

    group_matches: List[Dict[str, Any]] = []
    matching_debug: List[Dict[str, Any]] = []
    # Per-group pipeline diagnostics — written unconditionally so dropped groups are visible.
    pipeline_diag: List[Dict[str, Any]] = []

    for group_idx, group in enumerate(groups):
        normalized_group = _normalize_bore_group(group, group_idx)

        # ── Diagnostic checkpoint A: group normalisation ───────────────────────
        _diag: Dict[str, Any] = {
            "group_idx": group_idx,
            "source_file": normalized_group.get("source_file"),
            "row_count": normalized_group.get("row_count"),
            "min_station_ft": normalized_group.get("min_station_ft"),
            "max_station_ft": normalized_group.get("max_station_ft"),
            "span_ft": normalized_group.get("span_ft"),
            "print_tokens": list(normalized_group.get("print_tokens") or []),
            "evidence_layer_id": normalized_group.get("evidence_layer_id"),
            # filled in below
            "strict_allowed_route_ids": None,
            "catalog_size": len(STATE.get("route_catalog", []) or []),
            "strict_candidate_count_after_filter": None,
            "strict_candidate_count_after_span_gate": None,
            "strict_top5": [],
            "strict_rankings_empty": None,
            "ambiguous_fallback_triggered": False,
            "fallback_candidate_count": None,
            "fallback_top5": [],
            "fallback_rankings_empty": None,
            "anchored_hypotheses_count": None,
            "stopped_at": None,
            "selected_route_id": None,
            "selected_route_name": None,
            "segments_builder_called": False,
            "segments_returned": None,
            "segments_zero_reason": None,
            "render_allowed": None,
            "render_block_reasons": [],
            "plan_bias_applied": False,
            "plan_bias_meta": None,
            "ambiguity_resolution_status": "not_applicable",
            "ambiguity_resolution_meta": None,
        }

        # ── Diagnostic checkpoint B: strict candidate rankings ─────────────────
        rankings, filter_meta, _all_rankings = _candidate_rankings_for_group_v2(group, normalized_group)
        _diag["strict_allowed_route_ids"] = list(filter_meta.get("allowed_route_ids") or [])
        _diag["strict_candidate_count_after_filter"] = len(list(filter_meta.get("allowed_route_ids") or [])) or None
        _diag["strict_candidate_count_after_span_gate"] = len(rankings)
        _diag["strict_rankings_empty"] = len(rankings) == 0
        _diag["strict_top5"] = [
            {"route_id": r.get("route_id"), "route_name": r.get("route_name"),
             "score": round(float(r.get("score", 0.0) or 0.0), 4),
             "route_length_ft": round(float(r.get("route_length_ft", 0.0) or 0.0), 1)}
            for r in rankings[:5]
        ]

        # Fallback pass 1: no candidates survived strict print filtering.
        # If the group spans 3+ prints, retry with geometry proximity only.
        # Groups that already produced rankings are untouched.
        _ambiguous_fallback_used = False
        if not rankings and _is_ambiguous_print_group(normalized_group):
            rankings, filter_meta, _all_rankings = _fallback_rankings_geometry_only(group, normalized_group)
            _ambiguous_fallback_used = bool(rankings)
            # ── Diagnostic checkpoint C: fallback pass 1 ──────────────────────
            _diag["ambiguous_fallback_triggered"] = True
            _diag["fallback_candidate_count"] = len(rankings)
            _diag["fallback_rankings_empty"] = len(rankings) == 0
            _diag["fallback_top5"] = [
                {"route_id": r.get("route_id"), "route_name": r.get("route_name"),
                 "score": round(float(r.get("score", 0.0) or 0.0), 4),
                 "route_length_ft": round(float(r.get("route_length_ft", 0.0) or 0.0), 1)}
                for r in rankings[:5]
            ]

        if not rankings:
            _diag["stopped_at"] = "no_rankings_after_all_passes"
            pipeline_diag.append(_diag)
            continue

        # ── Phase 2: plan-aware ranking boost (pre-anchor pass 1) ────────────
        # Uses already-extracted plan signals (numeric tokens only, cap +0.03).
        # Reorder only if top-2 gap ≤ 0.10 before bias.
        if _plan_signals:
            rankings, _pb_meta = _plan_aware_ranking_boost(rankings, normalized_group, _plan_signals)
            if _pb_meta.get("applied"):
                _diag["plan_bias_applied"] = True
                _diag["plan_bias_meta"] = _pb_meta
            else:
                _diag["plan_bias_meta"] = _pb_meta  # always record diagnostics even when not applied

        anchored_hypotheses: List[Dict[str, Any]] = []
        for ranking in rankings[:3]:
            matched_route = _find_route_by_id(ranking.get("route_id"))
            if not matched_route:
                continue
            anchored_hypotheses.append(_anchor_route_subsection(matched_route, normalized_group, ranking, filter_meta))

        anchored_hypotheses.sort(key=lambda item: (-float(item.get("combined_score", 0.0) or 0.0), -float(item.get("route_score", 0.0) or 0.0), str(item.get("route_name", ""))))

        # Fallback pass 2: candidates existed but none anchored successfully.
        # Only triggers if the geometry-only pass was not already attempted.
        if not anchored_hypotheses and not _ambiguous_fallback_used and _is_ambiguous_print_group(normalized_group):
            rankings, filter_meta, _all_rankings = _fallback_rankings_geometry_only(group, normalized_group)
            _ambiguous_fallback_used = bool(rankings)
            # ── Diagnostic checkpoint D: fallback pass 2 ──────────────────────
            _diag["ambiguous_fallback_triggered"] = True
            _diag["fallback_candidate_count"] = len(rankings)
            _diag["fallback_rankings_empty"] = len(rankings) == 0
            _diag["fallback_top5"] = [
                {"route_id": r.get("route_id"), "route_name": r.get("route_name"),
                 "score": round(float(r.get("score", 0.0) or 0.0), 4),
                 "route_length_ft": round(float(r.get("route_length_ft", 0.0) or 0.0), 1)}
                for r in rankings[:5]
            ]
            # ── Phase 2: plan-aware boost also applied to fallback pass 2 ──────
            if _plan_signals:
                rankings, _pb_meta2 = _plan_aware_ranking_boost(rankings, normalized_group, _plan_signals)
                if _pb_meta2.get("applied") and not _diag.get("plan_bias_applied"):
                    _diag["plan_bias_applied"] = True
                    _diag["plan_bias_meta"] = _pb_meta2
            for ranking in rankings[:3]:
                matched_route = _find_route_by_id(ranking.get("route_id"))
                if not matched_route:
                    continue
                anchored_hypotheses.append(_anchor_route_subsection(matched_route, normalized_group, ranking, filter_meta))
            anchored_hypotheses.sort(key=lambda item: (-float(item.get("combined_score", 0.0) or 0.0), -float(item.get("route_score", 0.0) or 0.0), str(item.get("route_name", ""))))

        _diag["anchored_hypotheses_count"] = len(anchored_hypotheses)

        if not anchored_hypotheses:
            _diag["stopped_at"] = "no_anchored_hypotheses"
            pipeline_diag.append(_diag)
            continue

        selected_hypothesis, matched_route, selected_ranking, mapping, evaluated_hypotheses = _select_best_hypothesis_with_gate(
            group,
            normalized_group,
            rankings,
            filter_meta,
            anchored_hypotheses,
        )

        rendered_matches_so_far = [match for match in group_matches if bool(match.get("render_allowed"))]
        selected_hypothesis, matched_route, selected_ranking, mapping, within_route_anchor_separation_gate = _apply_within_route_anchor_separation(
            selected_hypothesis,
            matched_route,
            selected_ranking,
            mapping,
            evaluated_hypotheses,
            rendered_matches_so_far,
            normalized_group,
        )
        selected_hypothesis, matched_route, selected_ranking, mapping, authoritative_route_id = _authoritative_selection_bundle(
            selected_hypothesis,
            matched_route,
            selected_ranking,
            mapping,
            evaluated_hypotheses,
        )

        # ── Diagnostic checkpoint E: selected route ────────────────────────────
        _diag["selected_route_id"] = matched_route.get("route_id") if matched_route else None
        _diag["selected_route_name"] = matched_route.get("route_name") if matched_route else None
        _diag["selected_route_length_ft"] = round(float((matched_route or {}).get("length_ft") or 0.0), 1)

        group_station_points, mapping = _build_station_points_for_group(group, matched_route, rankings, filter_meta, mapping)
        _diag["segments_builder_called"] = True
        group_redline_segments = _build_redline_segments_for_group(group, matched_route, rankings, mapping, filter_meta)
        _diag["segments_returned"] = len(group_redline_segments)
        if len(group_redline_segments) == 0:
            route_coords = (matched_route or {}).get("coords") or []
            if len(route_coords) < 2:
                _diag["segments_zero_reason"] = f"route_coords_lt_2 (got {len(route_coords)})"
            elif len(group) < 2:
                _diag["segments_zero_reason"] = f"group_rows_lt_2 (got {len(group)})"
            else:
                _diag["segments_zero_reason"] = "all_row_pairs_skipped_end_lte_start_or_clip_lt_2_coords"

        if authoritative_route_id:
            filtered_station_points: List[Dict[str, Any]] = []
            for point in group_station_points:
                point_copy = dict(point)
                point_copy["route_id"] = authoritative_route_id
                point_copy["matched_route_id"] = authoritative_route_id
                point_copy["matched_route_name"] = matched_route.get("route_name")
                verification = dict(point_copy.get("verification") or {})
                verification["authoritative_route_id"] = authoritative_route_id
                point_copy["verification"] = verification
                if str(point_copy.get("route_id") or "").strip() == authoritative_route_id:
                    filtered_station_points.append(point_copy)
            group_station_points = filtered_station_points

            filtered_redline_segments: List[Dict[str, Any]] = []
            for segment in group_redline_segments:
                segment_copy = dict(segment)
                segment_copy["route_id"] = authoritative_route_id
                segment_copy["matched_route_id"] = authoritative_route_id
                segment_copy["route_name"] = matched_route.get("route_name")
                segment_copy["matched_route_name"] = matched_route.get("route_name")
                verification = dict(segment_copy.get("verification") or {})
                verification["authoritative_route_id"] = authoritative_route_id
                segment_copy["verification"] = verification
                if str(segment_copy.get("route_id") or "").strip() == authoritative_route_id:
                    filtered_redline_segments.append(segment_copy)
            group_redline_segments = filtered_redline_segments
        validation = _build_validation_checks(normalized_group, anchored_hypotheses, mapping, group_station_points, matched_route)
        validation["billing_gate"] = {
            "billable_candidate": bool(selected_hypothesis.get("billable_candidate")),
            "gate_reasons": list(selected_hypothesis.get("billable_gate_reasons") or []),
            "mode": "deterministic_pass_fail_gate",
        }
        validation["route_uniqueness_gate"] = dict(selected_hypothesis.get("route_uniqueness_gate") or {
            "passed": True,
            "reason": "no_uniqueness_conflict_detected",
            "competing_billable_candidates": [],
        })
        validation["geometry_lock_gate"] = dict(selected_hypothesis.get("geometry_lock_gate") or {
            "passed": True,
            "reason": "no_parallel_route_conflict_detected",
            "competing_parallel_routes": [],
        })
        validation["physical_feasibility_gate"] = dict(selected_hypothesis.get("physical_feasibility_gate") or {
            "passed": True,
            "reason": "within_physical_span_bounds",
        })
        validation["segment_fit_gate"] = dict(selected_hypothesis.get("segment_fit_gate") or {
            "passed": True,
            "reason": "segment_fit_valid",
            "details": {},
        })
        validation["boundary_exactness_gate"] = dict(selected_hypothesis.get("boundary_exactness_gate") or {
            "passed": True,
            "reason": "boundary_exactness_valid",
            "details": {},
        })
        validation["continuity_gate"] = dict(selected_hypothesis.get("continuity_gate") or {
            "passed": True,
            "reason": "continuity_valid",
            "details": {},
        })
        validation["chain_gate"] = dict(selected_hypothesis.get("chain_gate") or {
            "passed": True,
            "reason": "chain_valid",
            "details": {},
        })
        validation["node_resolution_gate"] = dict(selected_hypothesis.get("node_resolution_gate") or {
            "passed": True,
            "reason": "node_resolution_valid",
            "details": {},
        })
        validation["within_route_anchor_separation_gate"] = dict(selected_hypothesis.get("within_route_anchor_separation_gate") or within_route_anchor_separation_gate or {
            "passed": True,
            "reason": "no_within_route_overlap_conflict",
            "conflicts": [],
            "reselected": False,
        })

        anchored_hypotheses = [dict(item["hypothesis"]) for item in evaluated_hypotheses]
        render_allowed, render_block_reasons = _group_render_is_allowed(validation, selected_hypothesis)

        # Context-stable preview-safe render policy:
        # A valid per-group placement should stay visible regardless of whether the same bore log
        # arrives alone or beside other nearby logs in a batch. Foremen verify before billing, so
        # the backend must prioritize the right corridor / right segment / right direction and keep
        # sane reconstructions visible instead of killing them at the final gate.
        has_route = bool(matched_route and matched_route.get("route_id"))
        has_station_points = len(group_station_points) > 0
        has_redline_segments = len(group_redline_segments) > 0
        has_geometry_output = has_station_points and has_redline_segments
        within_route_gate = dict(validation.get("within_route_anchor_separation_gate") or {})
        physical_gate = dict(validation.get("physical_feasibility_gate") or {})
        continuity_gate = dict(validation.get("continuity_gate") or {})
        segment_fit_gate = dict(validation.get("segment_fit_gate") or {})
        chain_gate = dict(validation.get("chain_gate") or {})
        chain_preview_safe, chain_preview_reasons = _chain_ambiguity_preview_safe(validation, selected_hypothesis)

        hard_fail_reasons = []
        if has_route is False:
            hard_fail_reasons.append("no_matched_route")
        if has_geometry_output is False:
            hard_fail_reasons.append("no_geometry_output")
        if not bool(chain_gate.get("passed", True)) and not chain_preview_safe:
            hard_fail_reasons.append(str(chain_gate.get("reason") or "chain_gate_failed"))

        preview_reasons = []
        if chain_preview_safe:
            preview_reasons.extend(chain_preview_reasons)
        if not bool(physical_gate.get("passed", True)):
            preview_reasons.append(str(physical_gate.get("reason") or "physical_feasibility_warn"))
        if not bool(within_route_gate.get("passed", True)):
            preview_reasons.append(str(within_route_gate.get("reason") or "within_route_anchor_overlap_conflict"))
        if not bool(continuity_gate.get("passed", True)):
            preview_reasons.append(str(continuity_gate.get("reason") or "continuity_gate_warn"))
        if not bool(segment_fit_gate.get("passed", True)):
            preview_reasons.append(str(segment_fit_gate.get("reason") or "segment_fit_gate_warn"))

        if hard_fail_reasons:
            render_allowed = False
            render_block_reasons = list(render_block_reasons) + hard_fail_reasons
            render_mode = "deterministic_hard_block_only"
        else:
            render_allowed = True
            render_block_reasons = [
                reason
                for reason in list(render_block_reasons)
                if str(reason) not in {
                    "within_route_anchor_overlap_conflict",
                    "batch_level_conflict_resolution",
                    "chain_gate:multiple_possible_chain_links",
                    "node_resolution_gate:chain_gate_failed_first",
                    "multiple_possible_chain_links",
                    "chain_gate_failed_first",
                }
            ]
            render_mode = "context_stable_preview_safe"
            if preview_reasons:
                validation["preview_review_gate"] = {
                    "passed": True,
                    "reason": "rendered_for_foreman_verification",
                    "review_reasons": preview_reasons,
                    "mode": "context_stable_preview_safe",
                }
            else:
                validation["preview_review_gate"] = {
                    "passed": True,
                    "reason": "clean_render_candidate",
                    "review_reasons": [],
                    "mode": "context_stable_preview_safe",
                }

        # ── Ambiguous-chain low-confidence review rescue ───────────────────────
        # When segments were successfully built but the ONLY reasons blocking
        # render are chain-ambiguity (multiple_possible_chain_links + its
        # downstream node_resolution_gate and validation_status:fail), override
        # to render as REVIEW REQUIRED / LOW CONFIDENCE instead of dropping the
        # group entirely.  The segments appear on the map so the foreman can
        # visually verify; they are NOT suppressed from billing (same behaviour
        # as the existing context_stable_preview_safe soft-block path).
        _AMBIGUOUS_CHAIN_REASONS: set = {
            "multiple_possible_chain_links",
            "chain_gate:multiple_possible_chain_links",
            "node_resolution_gate:chain_gate_failed_first",
            "chain_gate_failed_first",
            "validation_status:fail",
        }
        if (
            not render_allowed
            and has_geometry_output
            and str(chain_gate.get("reason") or "") == "multiple_possible_chain_links"
            and len(render_block_reasons) > 0
            and all(str(r) in _AMBIGUOUS_CHAIN_REASONS for r in render_block_reasons)
        ):
            render_allowed = True
            render_mode = "ambiguous_chain_review_required"
            validation["review_required"] = True
            validation["confidence_override"] = "low"
            validation["review_reason"] = "ambiguous_chain_rendered_for_review"
            validation["preview_review_gate"] = {
                "passed": True,
                "reason": "ambiguous_chain_rendered_for_review",
                "review_reasons": list(render_block_reasons),
                "mode": "ambiguous_chain_review_required",
            }
            # render_block_reasons intentionally preserved so callers can see
            # exactly why this group is flagged as low-confidence.

        validation["render_gate"] = {
            "render_allowed": bool(render_allowed),
            "block_reasons": list(render_block_reasons),
            "mode": render_mode,
        }

        for point in group_station_points:
            point.setdefault("verification", {})
            point["verification"]["validation"] = validation
        for segment in group_redline_segments:
            segment.setdefault("verification", {})
            segment["verification"]["validation"] = validation

        group_matches.append(
            {
                "group_id": normalized_group.get("group_id"),
                "route_id": matched_route.get("route_id"),
                "route_name": matched_route.get("route_name"),
                "source_folder": matched_route.get("source_folder"),
                "confidence": round(float(selected_hypothesis.get("combined_score", 0.0) or 0.0), 3),
                "confidence_label": validation.get("confidence_label"),
                "final_decision": "; ".join(reason for reason in (selected_hypothesis.get("anchor_reasons") or []) if reason) or selected_ranking.get("reason"),
                "route_role": matched_route.get("route_role"),
                "expected_span_ft": selected_ranking.get("expected_span_ft"),
                "length_gap_ft": selected_ranking.get("length_gap_ft"),
                "print": str(group[0].get("print") or ""),
                "source_file": str(group[0].get("source_file") or ""),
                "print_filter": dict(filter_meta),
                "candidate_rankings": list(rankings),
                "mapping": dict(mapping),
                "validation": dict(validation),
                "selected_hypothesis": dict(selected_hypothesis),
                "score_breakdown": dict(selected_ranking.get("score_breakdown") or {}),
                "render_allowed": bool(render_allowed),
                "render_block_reasons": list(render_block_reasons),
                "rendered_station_point_count": len(group_station_points) if render_allowed else 0,
                "rendered_redline_segment_count": len(group_redline_segments) if render_allowed else 0,
                "group_station_points": list(group_station_points),
                "group_redline_segments": list(group_redline_segments),
                "_normalized_group": dict(normalized_group),
                "_matched_route": dict(matched_route),
                "_evaluated_hypotheses": list(evaluated_hypotheses),
            }
        )

        matching_debug.append(_build_matching_debug_record(normalized_group, filter_meta, rankings, anchored_hypotheses, selected_hypothesis, validation))

        # ── Diagnostic checkpoint F: render outcome ────────────────────────────
        _diag["render_allowed"] = bool(render_allowed)
        _diag["render_block_reasons"] = list(render_block_reasons)
        _diag["stopped_at"] = None if bool(render_allowed) else "render_gate_blocked"

        # ── Diagnostic checkpoint G: Phase 3 ambiguity classification ──────────
        _amb_status, _amb_meta = _classify_group_ambiguity(
            render_block_reasons, normalized_group, validation, matched_route, _plan_signals
        )
        _diag["ambiguity_resolution_status"] = _amb_status
        _diag["ambiguity_resolution_meta"] = _amb_meta

        pipeline_diag.append(_diag)

    STATE["pipeline_diag"] = pipeline_diag

    group_matches = _apply_batch_level_conflict_resolution(group_matches)
    all_station_points = []
    all_redline_segments = []
    mapping_modes = []
    for match in group_matches:
        if bool(match.get("render_allowed")):
            all_station_points.extend(list(match.get("group_station_points") or []))
            all_redline_segments.extend(list(match.get("group_redline_segments") or []))
            mapping_modes.append(str((match.get("mapping") or {}).get("mode") or "absolute"))

    # propagate batch gate into matching_debug for consistency
    gate_by_group = {
        str(match.get("group_id") or ""): dict((match.get("validation") or {}).get("batch_conflict_resolution_gate") or {})
        for match in group_matches
    }
    for record in matching_debug:
        group_id = str(record.get("group_id") or "")
        if group_id in gate_by_group:
            record_validation = dict(record.get("validation") or {})
            record_validation["batch_conflict_resolution_gate"] = gate_by_group[group_id]
            record["validation"] = record_validation
            if not bool(gate_by_group[group_id].get("passed", True)):
                selected = dict(record.get("selected_hypothesis") or {})
                selected["batch_conflict_resolution_gate"] = gate_by_group[group_id]
                record["selected_hypothesis"] = selected

    STATE["station_points"] = all_station_points
    STATE["redline_segments"] = list(all_redline_segments)
    STATE["station_mapping_mode"] = ",".join(sorted(set(mapping_modes))) if mapping_modes else None
    STATE["station_mapping_min_ft"] = None
    STATE["station_mapping_max_ft"] = None
    STATE["station_mapping_range_ft"] = None
    STATE["matching_debug"] = matching_debug

    rendered_matches = [match for match in group_matches if bool(match.get("render_allowed"))]

    unique_route_ids = []
    for match in rendered_matches:
        route_id = match.get("route_id")
        if route_id and route_id not in unique_route_ids:
            unique_route_ids.append(route_id)

    selected_rendered_match = None
    if rendered_matches:
        selected_rendered_match = sorted(
            rendered_matches,
            key=lambda match: (
                0 if bool(((match.get("selected_hypothesis") or {}).get("authoritative_route_commit") or {}).get("committed")) else 1,
                -int(match.get("rendered_station_point_count") or 0),
                -float(match.get("confidence") or 0.0),
                str(match.get("group_id") or ""),
            ),
        )[0]

    if len(unique_route_ids) == 1:
        matched_route = _find_route_by_id(unique_route_ids[0])
        if matched_route:
            _set_active_route(matched_route)
        STATE["selected_route_match"] = selected_rendered_match
    else:
        STATE["selected_route_match"] = None

    STATE["route_match_candidates"] = group_matches
    # Phase 1G — per-group match audit (additive, never raises).
    _append_match_audit_v2_entries(group_matches)
    # Phase 1H-A — shadow-compare audit (additive, never raises).
    _append_match_shadow_compare_entries(group_matches)
    warn_count = sum(1 for record in matching_debug if str(record.get("validation", {}).get("validation_status") or "") == "warn")
    fail_count = sum(1 for record in matching_debug if str(record.get("validation", {}).get("validation_status") or "") == "fail")
    blocked_count = sum(1 for match in group_matches if not bool(match.get("render_allowed")))
    STATE["verification_summary"] = {
        "status": "independent_route_matching_active" if group_matches else "awaiting_bore_logs",
        "version": "v4",
        "route_selection_method": "candidate_pool_plus_anchored_hypothesis_validation_with_final_render_gate",
        "route_selection_reason": "Each bore-log group now flows through normalization, candidate-pool scoring, anchored hypothesis selection, post-match validation, and a final deterministic render gate before stations and redlines are accepted onto the map.",
        "group_count": len(group_matches),
        "unique_matched_routes": len(unique_route_ids),
        "rendered_group_count": len(rendered_matches),
        "blocked_group_count": blocked_count,
        "warn_count": warn_count,
        "fail_count": fail_count,
    }
    # Phase 1P — rebuild the redline topology continuity advisor after each
    # operational rebuild.  Additive, isolated.  Failure here MUST NOT break
    # any operational path.  Reads redline_segments (already written above) +
    # kmz_topology_sidecar.  Never writes back to any operational STATE key.
    try:
        STATE["redline_topology_continuity"] = _build_redline_topology_continuity(
            STATE.get("redline_segments"),
            STATE.get("kmz_topology_sidecar"),
            STATE.get("route_catalog"),
            STATE.get("kmz_reference"),
        )
    except Exception as _rtc_exc:
        STATE["redline_topology_continuity"] = None
        print(
            f"[REDLINE_TOPOLOGY_CONTINUITY] WARNING: advisor build failed: "
            f"{type(_rtc_exc).__name__}: {_rtc_exc}",
            flush=True,
        )
    # Phase 1Q — rebuild the node-anchored continuity advisor after each
    # operational rebuild.  Additive, isolated.  Failure here MUST NOT break
    # any operational path.  Reads redline_segments + kmz_reference +
    # route_catalog (all already written above).  Never writes back to any
    # operational STATE key.
    try:
        STATE["redline_node_continuity"] = _build_redline_node_continuity(
            STATE.get("redline_segments"),
            STATE.get("kmz_reference"),
            STATE.get("route_catalog"),
        )
    except Exception as _rnc_exc:
        STATE["redline_node_continuity"] = None
        print(
            f"[REDLINE_NODE_CONTINUITY] WARNING: advisor build failed: "
            f"{type(_rnc_exc).__name__}: {_rnc_exc}",
            flush=True,
        )
    # Phase 1S — rebuild the bore-log redline endpoint validator after each
    # operational rebuild.  Additive, isolated.  Failure here MUST NOT break
    # any operational path.  Reads redline_segments + kmz_reference +
    # route_catalog.  Never writes back to any operational STATE key.
    try:
        STATE["redline_endpoint_validation"] = _build_redline_endpoint_validation(
            STATE.get("redline_segments"),
            STATE.get("kmz_reference"),
            STATE.get("route_catalog"),
        )
    except Exception as _rev_exc:
        STATE["redline_endpoint_validation"] = None
        print(
            f"[REDLINE_ENDPOINT_VALIDATION] WARNING: validator build failed: "
            f"{type(_rev_exc).__name__}: {_rev_exc}",
            flush=True,
        )
    # Phase 1T — build deterministic endpoint snap recommendations after the
    # Phase 1S validator completes.  Additive, isolated.  Failure here MUST
    # NOT break any operational path.  Reads redline_endpoint_validation +
    # kmz_reference only.  Never writes to any operational STATE key.
    try:
        STATE["endpoint_snap_recommendations"] = _build_endpoint_snap_recommendations(
            STATE.get("redline_endpoint_validation"),
            STATE.get("kmz_reference"),
        )
    except Exception as _snap_exc:
        STATE["endpoint_snap_recommendations"] = None
        print(
            f"[ENDPOINT_SNAP_RECOMMENDATIONS] WARNING: builder failed: "
            f"{type(_snap_exc).__name__}: {_snap_exc}",
            flush=True,
        )


def _kmz_reference_lite() -> Dict[str, Any]:
    kmz_reference = STATE.get("kmz_reference", {}) or {}
    visual_reference = dict(kmz_reference.get("visual_reference", {}) or {})
    return {
        "folder_summary": kmz_reference.get("folder_summary", []) or [],
        "line_role_summary": kmz_reference.get("line_role_summary", []) or [],
        "point_role_summary": kmz_reference.get("point_role_summary", []) or [],
        "line_layers": kmz_reference.get("line_layers", []) or [],
        "explicit_redline_layers": kmz_reference.get("explicit_redline_layers", []) or [],
        "visual_reference": visual_reference,
        # Keep actual KMZ render geometry in the lightweight payload because the frontend map
        # depends on these arrays to draw the design. The heavy debug objects stay excluded.
        "line_features": kmz_reference.get("line_features", []) or [],
        "polygon_features": kmz_reference.get("polygon_features", []) or [],
        "point_features": kmz_reference.get("point_features", []) or [],
        "line_feature_count": len(kmz_reference.get("line_features", []) or []),
        "polygon_feature_count": len(kmz_reference.get("polygon_features", []) or []),
        "point_feature_count": len(kmz_reference.get("point_features", []) or []),
    }


def _compact_group_payload_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    validation = dict(entry.get("validation") or {})
    route_consensus_gate = dict(validation.get("route_consensus_gate") or {})
    preview_review_gate = dict(validation.get("preview_review_gate") or {})
    render_gate = dict(validation.get("render_gate") or {})
    return {
        "group_id": entry.get("group_id"),
        "source_file": entry.get("source_file"),
        "print": entry.get("print"),
        "row_count": int(entry.get("row_count", 0) or 0),
        "min_station_ft": entry.get("min_station_ft"),
        "max_station_ft": entry.get("max_station_ft"),
        "selected_route_id": entry.get("route_id") or (entry.get("selected_hypothesis") or {}).get("route_id"),
        "selected_route_name": entry.get("route_name") or (entry.get("selected_hypothesis") or {}).get("route_name"),
        "render_allowed": bool(entry.get("render_allowed")),
        "rendered_station_point_count": int(entry.get("rendered_station_point_count", 0) or 0),
        "rendered_redline_segment_count": int(entry.get("rendered_redline_segment_count", 0) or 0),
        "validation_status": validation.get("validation_status"),
        "confidence_label": validation.get("confidence_label"),
        "route_consensus_gate": {
            "passed": route_consensus_gate.get("passed"),
            "reason": route_consensus_gate.get("reason"),
            "consensus_route_id": route_consensus_gate.get("consensus_route_id"),
        },
        "authoritative_route_id": (entry.get("mapping") or {}).get("authoritative_route_id")
            or (entry.get("selected_hypothesis") or {}).get("authoritative_route_id")
            or (entry.get("selected_hypothesis") or {}).get("mapping", {}).get("authoritative_route_id"),
        "preview_review_gate_reason": preview_review_gate.get("reason"),
        "render_gate_block_reasons": list(render_gate.get("block_reasons") or []),
    }


def _grouping_summary_from_rows(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    groups = _group_rows_for_matching(rows)
    summaries: List[Dict[str, Any]] = []
    for idx, group in enumerate(groups):
        station_values = [float(row.get("station_ft") or 0.0) for row in group if row.get("station_ft") is not None]
        summaries.append(
            {
                "group_id": f"group_{idx + 1}",
                "source_file": str(group[0].get("source_file") or "") if group else "",
                "print": ",".join(_collect_group_print_tokens(group)),
                "row_count": len(group),
                "min_station_ft": round(min(station_values), 2) if station_values else None,
                "max_station_ft": round(max(station_values), 2) if station_values else None,
            }
        )
    return summaries


def _selected_route_match_summary(match: Any) -> Dict[str, Any]:
    if not isinstance(match, dict):
        return {}

    candidate_rankings = match.get("candidate_rankings") or []
    preview_rankings: List[Dict[str, Any]] = []
    for item in candidate_rankings[:3]:
        if not isinstance(item, dict):
            continue
        preview_rankings.append(
            {
                "route_id": item.get("route_id"),
                "route_name": item.get("route_name"),
                "route_role": item.get("route_role"),
                "route_length_ft": item.get("route_length_ft"),
                "expected_span_ft": item.get("expected_span_ft"),
                "length_gap_ft": item.get("length_gap_ft"),
                "score": item.get("score"),
            }
        )

    return {
        "route_name": match.get("route_name"),
        "route_role": match.get("route_role"),
        "confidence_label": match.get("confidence_label"),
        "final_decision": match.get("final_decision"),
        "expected_span_ft": match.get("expected_span_ft"),
        "length_gap_ft": match.get("length_gap_ft"),
        "print": match.get("print"),
        "print_filter": match.get("print_filter") if isinstance(match.get("print_filter"), dict) else {},
        "candidate_rankings_preview": preview_rankings,
    }


def _segment_overlap_ft(a: Dict[str, Any], b: Dict[str, Any]) -> float:
    try:
        a_start = float(a.get("start_ft") or 0.0)
        a_end = float(a.get("end_ft") or 0.0)
        b_start = float(b.get("start_ft") or 0.0)
        b_end = float(b.get("end_ft") or 0.0)
    except Exception:
        return 0.0
    if a_end < a_start:
        a_start, a_end = a_end, a_start
    if b_end < b_start:
        b_start, b_end = b_end, b_start
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def _segment_length(seg: Dict[str, Any]) -> float:
    try:
        start_ft = float(seg.get("start_ft") or 0.0)
        end_ft = float(seg.get("end_ft") or 0.0)
    except Exception:
        return 0.0
    if end_ft < start_ft:
        start_ft, end_ft = end_ft, start_ft
    return max(0.0, end_ft - start_ft)


def _classify_overlap(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    overlap_ft = _segment_overlap_ft(a, b)
    a_length = _segment_length(a)
    b_length = _segment_length(b)
    denom = max(min(a_length, b_length), 1e-9)
    overlap_ratio = overlap_ft / denom if overlap_ft > 0.0 else 0.0
    # evidence_layer_id takes priority: if both segments have a layer id and they differ,
    # they are never the same provenance regardless of source_file/crew/date.
    _a_layer = str(a.get("evidence_layer_id") or "").strip()
    _b_layer = str(b.get("evidence_layer_id") or "").strip()
    _layers_differ = bool(_a_layer and _b_layer and _a_layer != _b_layer)
    same_provenance = (
        not _layers_differ
        and str(a.get("source_file") or "").strip() == str(b.get("source_file") or "").strip()
        and str(a.get("crew") or "").strip() == str(b.get("crew") or "").strip()
        and str(a.get("date") or "").strip() == str(b.get("date") or "").strip()
    )
    if same_provenance and overlap_ratio > 0.85:
        overlap_type = "drop_duplicate"
    elif same_provenance and overlap_ratio > 0.5:
        overlap_type = "trim_partial"
    elif overlap_ft > 0.0:
        overlap_type = "minor_overlap_keep"
    else:
        overlap_type = "no_overlap"
    return {
        "overlap_ft": round(overlap_ft, 2),
        "overlap_ratio": round(overlap_ratio, 6),
        "same_provenance": bool(same_provenance),
        "classification": overlap_type,
    }


def _subtract_overlap(seg: Dict[str, Any], existing: Dict[str, Any]) -> List[Dict[str, Any]]:
    overlap_ft = _segment_overlap_ft(seg, existing)
    if overlap_ft <= 0.0:
        return [dict(seg)]

    try:
        seg_start = float(seg.get("start_ft") or 0.0)
        seg_end = float(seg.get("end_ft") or 0.0)
        existing_start = float(existing.get("start_ft") or 0.0)
        existing_end = float(existing.get("end_ft") or 0.0)
    except Exception:
        return [dict(seg)]

    if seg_end < seg_start:
        seg_start, seg_end = seg_end, seg_start
    if existing_end < existing_start:
        existing_start, existing_end = existing_end, existing_start

    remainders: List[Tuple[float, float]] = []
    if seg_start < existing_start:
        remainders.append((seg_start, min(seg_end, existing_start)))
    if seg_end > existing_end:
        remainders.append((max(seg_start, existing_end), seg_end))

    route_id = str(seg.get("route_id") or seg.get("matched_route_id") or "").strip()
    route = _find_route_by_id(route_id)
    route_coords = list((route or {}).get("coords") or seg.get("coords") or [])

    trimmed: List[Dict[str, Any]] = []
    part_index = 1
    for part_start, part_end in remainders:
        if part_end - part_start <= 0.01:
            continue
        part_seg = dict(seg)
        part_seg["start_ft"] = round(part_start, 2)
        part_seg["end_ft"] = round(part_end, 2)
        part_seg["length_ft"] = round(part_end - part_start, 2)
        if route_coords:
            clipped = _clip_route_segment(route_coords, part_start, part_end)
            if len(clipped) >= 2:
                part_seg["coords"] = clipped
        part_seg["segment_id"] = f"{str(seg.get('segment_id') or 'segment')}__trim_{part_index}"
        trimmed.append(part_seg)
        part_index += 1
    return trimmed


def _deduplicate_segments(segments: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    route_rank: Dict[str, int] = {
        str(route.get("route_id") or "").strip(): idx
        for idx, route in enumerate(STATE.get("route_catalog", []) or [])
    }

    ordered = sorted(
        [dict(seg) for seg in (segments or [])],
        key=lambda seg: (
            route_rank.get(str(seg.get("route_id") or seg.get("matched_route_id") or "").strip(), 10**9),
            str(seg.get("route_id") or seg.get("matched_route_id") or "").strip(),
            float(seg.get("start_ft") or 0.0),
            float(seg.get("end_ft") or 0.0),
            str(seg.get("source_file") or ""),
            str(seg.get("crew") or ""),
            str(seg.get("date") or ""),
            int(seg.get("row_index") or 0),
            str(seg.get("segment_id") or ""),
        ),
    )

    accepted: List[Dict[str, Any]] = []
    for segment in ordered:
        current_parts = [dict(segment)]
        for existing in accepted:
            existing_route_id = str(existing.get("route_id") or existing.get("matched_route_id") or "").strip()
            next_parts: List[Dict[str, Any]] = []
            for part in current_parts:
                part_route_id = str(part.get("route_id") or part.get("matched_route_id") or "").strip()
                if not part_route_id or part_route_id != existing_route_id:
                    next_parts.append(part)
                    continue
                overlap_meta = _classify_overlap(part, existing)
                classification = str(overlap_meta.get("classification") or "")
                if classification == "drop_duplicate":
                    continue
                if classification == "trim_partial":
                    next_parts.extend(_subtract_overlap(part, existing))
                    continue
                next_parts.append(part)
            current_parts = next_parts
            if not current_parts:
                break
        accepted.extend(current_parts)
    return accepted


def _merge_route_intervals(intervals: Sequence[Tuple[float, float]], tolerance_ft: float = 0.01) -> List[Tuple[float, float]]:
    cleaned: List[Tuple[float, float]] = []
    for start_ft, end_ft in intervals:
        try:
            start_val = float(start_ft)
            end_val = float(end_ft)
        except Exception:
            continue
        if end_val < start_val:
            start_val, end_val = end_val, start_val
        if end_val - start_val <= 0.0:
            continue
        cleaned.append((start_val, end_val))
    if not cleaned:
        return []
    cleaned.sort(key=lambda item: (item[0], item[1]))
    merged: List[Tuple[float, float]] = [cleaned[0]]
    merge_tolerance = max(0.0, float(tolerance_ft or 0.0))
    for start_val, end_val in cleaned[1:]:
        prev_start, prev_end = merged[-1]
        if start_val <= prev_end + merge_tolerance:
            merged[-1] = (prev_start, max(prev_end, end_val))
        else:
            merged.append((start_val, end_val))
    return merged


def _unique_coverage_summary(redline_segments: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    route_segments: Dict[str, List[Tuple[float, float]]] = {}
    route_names: Dict[str, str] = {}
    raw_length_ft = 0.0
    tolerance_ft = 5.0

    for segment in redline_segments or []:
        route_id = str(segment.get('route_id') or segment.get('matched_route_id') or '').strip()
        if not route_id:
            continue
        try:
            start_val = float(segment.get('start_ft'))
            end_val = float(segment.get('end_ft'))
        except Exception:
            continue
        if end_val < start_val:
            start_val, end_val = end_val, start_val
        segment_length_ft = max(0.0, end_val - start_val)
        if segment_length_ft <= 0.0:
            continue

        interval = (start_val, end_val)
        route_segments.setdefault(route_id, []).append(interval)
        route_names[route_id] = str(segment.get('route_name') or segment.get('matched_route_name') or route_id)
        raw_length_ft += segment_length_ft

    routes: List[Dict[str, Any]] = []
    total_interval_count = 0
    total_merged_interval_count = 0
    total_unique_length_ft = 0.0

    for route_id in sorted(route_segments.keys()):
        intervals = sorted(route_segments.get(route_id, []), key=lambda item: (item[0], item[1]))
        total_interval_count += len(intervals)

        merged_intervals = _merge_route_intervals(intervals, tolerance_ft=tolerance_ft)
        total_merged_interval_count += len(merged_intervals)
        route_unique_length_ft = sum(max(0.0, end_val - start_val) for start_val, end_val in merged_intervals)
        total_unique_length_ft += route_unique_length_ft

        routes.append(
            {
                'route_id': route_id,
                'route_name': route_names.get(route_id, route_id),
                'merged_intervals': [
                    {
                        'start_ft': round(start_val, 2),
                        'end_ft': round(end_val, 2),
                        'length_ft': round(max(0.0, end_val - start_val), 2),
                    }
                    for start_val, end_val in merged_intervals
                ],
                'unique_length_ft': round(route_unique_length_ft, 2),
            }
        )

    unique_length_ft = round(total_unique_length_ft, 2)
    raw_length_ft = round(raw_length_ft, 2)
    deduped_overlap_ft = round(max(0.0, raw_length_ft - unique_length_ft), 2)

    return {
        'raw_length_ft': raw_length_ft,
        'unique_length_ft': unique_length_ft,
        'deduped_overlap_ft': deduped_overlap_ft,
        'route_interval_count': total_interval_count,
        'route_merged_interval_count': total_merged_interval_count,
        'routes': routes,
    }


def _coverage_runtime_verification(redline_segments: Sequence[Dict[str, Any]], coverage_summary: Dict[str, Any]) -> Dict[str, Any]:
    raw_length_ft = round(float(coverage_summary.get('raw_length_ft', 0.0) or 0.0), 2)
    unique_length_ft = round(float(coverage_summary.get('unique_length_ft', 0.0) or 0.0), 2)
    overlap_removed_ft = round(max(0.0, raw_length_ft - unique_length_ft), 2)
    return {
        'module_file': str(Path(__file__).resolve()),
        'coverage_function_mode': 'merged_unique_intervals',
        'coverage_function_marker': 'RUNTIME_VERIFY_MERGED_UNIQUE_V5',
        'coverage_source_segment_count': len(redline_segments or []),
        'coverage_source_interval_count': int(coverage_summary.get('route_interval_count', 0) or 0),
        'coverage_raw_length_ft': raw_length_ft,
        'coverage_unique_length_ft': unique_length_ft,
        'coverage_overlap_removed_ft': overlap_removed_ft,
    }


def _bore_log_summary_from_rows(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One record per uploaded bore log file — no merging across files.
    Preserves all bore log identities for the UI's Bore Log Summary view."""
    by_file: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows or []:
        source_file = str(row.get("source_file") or "").strip()
        if not source_file:
            continue
        by_file.setdefault(source_file, []).append(row)

    session_id = str(STATE.get("_session_id_hint") or "").strip()
    eng_plans: List[Dict[str, Any]] = []
    try:
        if session_id:
            eng_plans = _load_engineering_plan_index_for_session(session_id)
    except Exception:
        eng_plans = []

    summary: List[Dict[str, Any]] = []
    for source_file in sorted(by_file.keys()):
        file_rows = by_file[source_file]
        station_values = [float(r["station_ft"]) for r in file_rows if r.get("station_ft") is not None]
        dates = sorted({str(r.get("date") or "").strip() for r in file_rows if str(r.get("date") or "").strip()})
        print_tokens = sorted({
            token
            for r in file_rows
            for token in _parse_print_tokens(r.get("print"))
        })
        crews = sorted({str(r.get("crew") or "").strip() for r in file_rows if str(r.get("crew") or "").strip()})

        _el_src = source_file.strip().lower()
        _el_print = "|".join(print_tokens)
        _el_date = dates[0].lower() if dates else ""
        evidence_layer_id = hashlib.sha256(f"{_el_src}|{_el_print}|{_el_date}".encode()).hexdigest()[:16]

        # Lightweight engineering plan association — match by plan_date proximity (same date prefix)
        eng_plan_ref: Optional[str] = None
        eng_plan_date: Optional[str] = None
        if eng_plans and dates:
            for plan in eng_plans:
                plan_date = str(plan.get("plan_date") or "").strip()
                if not plan_date:
                    continue
                for bore_date in dates:
                    if plan_date[:10] == bore_date[:10]:
                        eng_plan_ref = str(plan.get("original_filename") or "")
                        eng_plan_date = plan_date
                        break
                if eng_plan_ref:
                    break

        summary.append({
            "source_file": source_file,
            "row_count": len(file_rows),
            "min_station_ft": round(min(station_values), 2) if station_values else None,
            "max_station_ft": round(max(station_values), 2) if station_values else None,
            "span_ft": round(max(station_values) - min(station_values), 2) if len(station_values) >= 2 else None,
            "dates": dates,
            "print_tokens": print_tokens,
            "crews": crews,
            "evidence_layer_id": evidence_layer_id,
            "engineering_plan_ref": eng_plan_ref,
            "engineering_plan_date": eng_plan_date,
        })
    return summary


def _total_design_length_ft(route_catalog: Sequence[Dict[str, Any]]) -> float:
    total_ft = 0.0
    seen_route_ids = set()
    for route in route_catalog or []:
        route_id = str(route.get('route_id') or '').strip()
        if not route_id or route_id in seen_route_ids:
            continue
        seen_route_ids.add(route_id)
        total_ft += max(0.0, float(route.get('length_ft', 0.0) or 0.0))
    return round(total_ft, 2)


# ---------------------------------------------------------------------------
# Phase 1C — SHADOW-MODE semantic-assisted matching diagnostics.
#
# This module is purely read-only over STATE. It runs AFTER existing route
# matching has completed; it does NOT replace, override, or alter any of:
#   * STATE["selected_route_match"]
#   * STATE["route_match_candidates"]
#   * STATE["station_points"]
#   * STATE["redline_segments"]
#   * any candidate_rankings score
#   * any redline_segment coords
#
# It scores each candidate route against the anchor_catalog to produce a
# parallel "semantic best" route per bore-log group, plus an agreement flag
# and explainability strings. Output goes into kmz_semantic_match_shadow on
# the summary payload. Frontends that ignore the field continue working.
#
# Computation cost: O(groups × candidate_routes × anchors × route_segments).
# For typical projects (≤ 50 groups × 20 candidates × 200 anchors × 100
# segments) that is ~20M tiny ops, well under 100 ms. No caching today; a
# cache can be added later if measurements demand it.
# ---------------------------------------------------------------------------

# Shadow-mode scoring weights. Numbers are intentionally conservative; their
# only job here is to identify a "semantic best" route deterministically.
# When/if the matching engine ever consumes this signal, weights will be
# re-tuned with corpus data.
_SEMANTIC_SHADOW_CONFIDENCE_WEIGHT = {"high": 1.0, "medium": 0.4, "low": 0.0}
_SEMANTIC_SHADOW_CLASSIFICATION_WEIGHT = {
    "handhole": 1.0,
    "station_label": 0.85,
    "structure_marker": 0.70,
    "reel": 0.30,
}
# Proximity envelope: anchors within 3 ft of a polyline contribute full
# weight; weight tapers linearly to 0 at 25 ft; anchors farther than 25 ft
# do not contribute. Matches the architecture design.
_SEMANTIC_SHADOW_NEAR_FT = 3.0
_SEMANTIC_SHADOW_FAR_FT = 25.0
# Bounded contributors per route to keep the shadow payload small.
_SEMANTIC_SHADOW_CONTRIBUTORS_PER_ROUTE = 10
# Bounded ranked routes per group in the diagnostic output.
_SEMANTIC_SHADOW_RANKED_ROUTES_PER_GROUP = 10


def _semantic_proximity_weight(distance_ft: float) -> float:
    """Linear taper from 1.0 at NEAR_FT to 0.0 at FAR_FT. Deterministic."""
    if distance_ft <= _SEMANTIC_SHADOW_NEAR_FT:
        return 1.0
    if distance_ft >= _SEMANTIC_SHADOW_FAR_FT:
        return 0.0
    span = _SEMANTIC_SHADOW_FAR_FT - _SEMANTIC_SHADOW_NEAR_FT
    return 1.0 - (distance_ft - _SEMANTIC_SHADOW_NEAR_FT) / span


def _semantic_min_distance_to_polyline_ft(
    lat: float, lon: float, polyline: Sequence[Sequence[float]]
) -> Optional[float]:
    """Minimum distance in feet from (lat, lon) to a [lat, lon] polyline.

    Per-segment closest-point is computed in planar lat/lon (acceptable bias
    at OSP scales — typically a few feet at most), then the actual distance
    is computed by haversine to the closest planar point. The asymmetry
    between lat and lon "feet" only affects the position of the closest
    point on a segment, not the final distance value.

    Returns None for malformed inputs (no segments, non-finite coords).
    """
    if not polyline or len(polyline) < 2:
        return None
    if not (math.isfinite(lat) and math.isfinite(lon)):
        return None
    best = float("inf")
    for i in range(len(polyline) - 1):
        a = polyline[i]
        b = polyline[i + 1]
        if not a or not b or len(a) < 2 or len(b) < 2:
            continue
        try:
            alat = float(a[0])
            alon = float(a[1])
            blat = float(b[0])
            blon = float(b[1])
        except (TypeError, ValueError):
            continue
        dlat = blat - alat
        dlon = blon - alon
        seg_len2 = dlat * dlat + dlon * dlon
        if seg_len2 < 1e-20:
            continue
        t = ((lat - alat) * dlat + (lon - alon) * dlon) / seg_len2
        if t < 0.0:
            t = 0.0
        elif t > 1.0:
            t = 1.0
        clat = alat + t * dlat
        clon = alon + t * dlon
        d = _haversine_feet(lat, lon, clat, clon)
        if d < best:
            best = d
    if not math.isfinite(best):
        return None
    return best


def _build_semantic_match_shadow() -> Optional[Dict[str, Any]]:
    """Compute the shadow-mode semantic-assisted match diagnostics payload.

    Pure read of STATE. Returns None when:
      - kmz_semantic is absent
      - anchor_catalog is empty
      - route_match_candidates is empty
      - route_catalog is empty
      - no usable anchors survive filtering

    The payload is purely informational. Consumers (the diagnostics panel)
    treat it as advisory; the matching engine continues to ignore it.
    """
    semantic = STATE.get("kmz_semantic") or None
    if not isinstance(semantic, dict):
        return None
    index = semantic.get("index") or {}
    if not isinstance(index, dict):
        return None
    anchor_catalog = index.get("anchor_catalog") or []
    if not isinstance(anchor_catalog, list) or not anchor_catalog:
        return None

    route_match_candidates = STATE.get("route_match_candidates") or []
    if not isinstance(route_match_candidates, list) or not route_match_candidates:
        return None

    route_catalog = STATE.get("route_catalog") or []
    if not isinstance(route_catalog, list) or not route_catalog:
        return None
    routes_by_id: Dict[str, Dict[str, Any]] = {}
    for route in route_catalog:
        if isinstance(route, dict):
            rid = str(route.get("route_id") or "").strip()
            if rid:
                routes_by_id[rid] = route

    # Pre-filter anchors. Only confidence levels that carry weight; only
    # finite coords. Catalog already excludes "low", but defend anyway.
    accepted_anchors: List[Dict[str, Any]] = []
    for anchor in anchor_catalog:
        if not isinstance(anchor, dict):
            continue
        coord = anchor.get("coord")
        if not isinstance(coord, list) or len(coord) < 2:
            continue
        try:
            alat = float(coord[0])
            alon = float(coord[1])
        except (TypeError, ValueError):
            continue
        if not (math.isfinite(alat) and math.isfinite(alon)):
            continue
        confidence = anchor.get("confidence")
        if not isinstance(confidence, str):
            continue
        if _SEMANTIC_SHADOW_CONFIDENCE_WEIGHT.get(confidence, 0.0) <= 0:
            continue
        classification = str(anchor.get("classification") or "")
        if _SEMANTIC_SHADOW_CLASSIFICATION_WEIGHT.get(classification, 0.0) <= 0:
            continue
        accepted_anchors.append(
            {
                "feature_id": str(anchor.get("feature_id") or ""),
                "lat": alat,
                "lon": alon,
                "classification": classification,
                "confidence": confidence,
            }
        )
    if not accepted_anchors:
        return None

    groups_payload: List[Dict[str, Any]] = []
    groups_total = 0
    groups_in_agreement = 0
    groups_in_disagreement = 0
    groups_with_no_anchors = 0

    for group_index, match in enumerate(route_match_candidates):
        if not isinstance(match, dict):
            continue
        rankings = match.get("candidate_rankings") or []
        if not isinstance(rankings, list) or not rankings:
            continue
        groups_total += 1
        existing_first = rankings[0] if isinstance(rankings[0], dict) else {}
        existing_route_id = str(existing_first.get("route_id") or "").strip()
        existing_route_name = str(existing_first.get("route_name") or "").strip()
        try:
            existing_score = float(existing_first.get("score") or 0.0)
        except (TypeError, ValueError):
            existing_score = 0.0

        per_route_results: List[Dict[str, Any]] = []
        for ranking in rankings:
            if not isinstance(ranking, dict):
                continue
            rid = str(ranking.get("route_id") or "").strip()
            if not rid:
                continue
            route = routes_by_id.get(rid)
            if not route:
                continue
            polyline = route.get("coords") or []
            if not polyline or len(polyline) < 2:
                continue

            anchor_count = 0
            score_total = 0.0
            contributors: List[Dict[str, Any]] = []
            for anchor in accepted_anchors:
                d = _semantic_min_distance_to_polyline_ft(
                    anchor["lat"], anchor["lon"], polyline
                )
                if d is None:
                    continue
                if d >= _SEMANTIC_SHADOW_FAR_FT:
                    continue
                conf_w = _SEMANTIC_SHADOW_CONFIDENCE_WEIGHT.get(
                    anchor["confidence"], 0.0
                )
                cls_w = _SEMANTIC_SHADOW_CLASSIFICATION_WEIGHT.get(
                    anchor["classification"], 0.0
                )
                prox_w = _semantic_proximity_weight(d)
                contribution = conf_w * cls_w * prox_w
                if contribution <= 0:
                    continue
                anchor_count += 1
                score_total += contribution
                contributors.append(
                    {
                        "feature_id": anchor["feature_id"],
                        "classification": anchor["classification"],
                        "confidence": anchor["confidence"],
                        "distance_ft": round(d, 2),
                        "contribution": round(contribution, 4),
                    }
                )
            contributors.sort(
                key=lambda c: (
                    -float(c["contribution"]),
                    float(c["distance_ft"]),
                    str(c["feature_id"]),
                )
            )
            per_route_results.append(
                {
                    "route_id": rid,
                    "route_name": str(ranking.get("route_name") or "").strip(),
                    "anchor_count": anchor_count,
                    "semantic_score": round(score_total, 4),
                    "contributors": contributors[
                        :_SEMANTIC_SHADOW_CONTRIBUTORS_PER_ROUTE
                    ],
                }
            )

        if not per_route_results:
            groups_with_no_anchors += 1
            groups_payload.append(
                {
                    "group_id": str(match.get("group_id") or f"group_{group_index}"),
                    "group_index": group_index,
                    "existing_selected_route_id": existing_route_id,
                    "existing_selected_route_name": existing_route_name,
                    "existing_score": round(existing_score, 4),
                    "semantic_best_route_id": None,
                    "semantic_best_route_name": None,
                    "semantic_best_score": 0.0,
                    "agreement": None,
                    "anchors_near_selected_route": 0,
                    "anchors_near_semantic_best_route": 0,
                    "contributing_anchor_ids": [],
                    "explanation": "No anchors within 25 ft of any candidate route in this group.",
                    "ranked_routes": [],
                }
            )
            continue

        per_route_results.sort(
            key=lambda r: (
                -float(r["semantic_score"]),
                str(r["route_id"]),
            )
        )
        best = per_route_results[0]
        existing_row = next(
            (r for r in per_route_results if r["route_id"] == existing_route_id),
            None,
        )
        anchors_near_selected = (
            int(existing_row["anchor_count"]) if existing_row else 0
        )
        anchors_near_best = int(best["anchor_count"])

        agreement: Optional[bool]
        if best["semantic_score"] <= 0:
            agreement = None
            explanation = "No anchor contributions on any candidate route."
            groups_with_no_anchors += 1
        elif best["route_id"] == existing_route_id:
            agreement = True
            groups_in_agreement += 1
            explanation = (
                f"Semantic agrees: {anchors_near_best} anchor(s) within "
                f"{int(_SEMANTIC_SHADOW_FAR_FT)} ft of selected route "
                f"'{existing_route_name or existing_route_id}'."
            )
        else:
            agreement = False
            groups_in_disagreement += 1
            existing_sem_score = (
                float(existing_row["semantic_score"]) if existing_row else 0.0
            )
            explanation = (
                f"Semantic prefers '{best['route_name'] or best['route_id']}' "
                f"({anchors_near_best} anchors near, score "
                f"{best['semantic_score']}) over current selection "
                f"'{existing_route_name or existing_route_id}' "
                f"({anchors_near_selected} anchors near, score "
                f"{round(existing_sem_score, 4)})."
            )

        contributing_anchor_ids = [
            str(c["feature_id"]) for c in best.get("contributors", [])
        ]

        groups_payload.append(
            {
                "group_id": str(match.get("group_id") or f"group_{group_index}"),
                "group_index": group_index,
                "existing_selected_route_id": existing_route_id,
                "existing_selected_route_name": existing_route_name,
                "existing_score": round(existing_score, 4),
                "semantic_best_route_id": best["route_id"],
                "semantic_best_route_name": best["route_name"],
                "semantic_best_score": float(best["semantic_score"]),
                "agreement": agreement,
                "anchors_near_selected_route": anchors_near_selected,
                "anchors_near_semantic_best_route": anchors_near_best,
                "contributing_anchor_ids": contributing_anchor_ids,
                "explanation": explanation,
                "ranked_routes": [
                    {
                        "route_id": str(r["route_id"]),
                        "route_name": str(r["route_name"]),
                        "anchor_count": int(r["anchor_count"]),
                        "semantic_score": float(r["semantic_score"]),
                    }
                    for r in per_route_results[
                        :_SEMANTIC_SHADOW_RANKED_ROUTES_PER_GROUP
                    ]
                ],
            }
        )

    return {
        "version": "shadow-1",
        "summary": {
            "groups_total": groups_total,
            "groups_in_agreement": groups_in_agreement,
            "groups_in_disagreement": groups_in_disagreement,
            "groups_with_no_anchors": groups_with_no_anchors,
            "anchors_considered": len(accepted_anchors),
            "weights": {
                "confidence": _SEMANTIC_SHADOW_CONFIDENCE_WEIGHT,
                "classification": _SEMANTIC_SHADOW_CLASSIFICATION_WEIGHT,
                "proximity_near_ft": _SEMANTIC_SHADOW_NEAR_FT,
                "proximity_far_ft": _SEMANTIC_SHADOW_FAR_FT,
            },
        },
        "groups": groups_payload,
    }


def _summary_payload(include_debug: bool = False) -> Dict[str, Any]:
    route_id = STATE.get("route_id")
    route_coords = STATE.get("route_coords", []) or []
    route_length_ft = float(STATE.get("route_length_ft", 0.0) or 0.0)
    redline_segments = STATE.get("redline_segments", []) or []
    station_points = STATE.get("station_points", []) or []
    active_route_id = str(route_id or "").strip()
    active_route_station_points = [
        point
        for point in station_points
        if str(point.get("route_id") or point.get("matched_route_id") or "").strip() == active_route_id
    ] if active_route_id else []
    active_route_redline_segments = [
        segment
        for segment in redline_segments
        if str(segment.get("route_id") or segment.get("matched_route_id") or "").strip() == active_route_id
    ] if active_route_id else []
    route_catalog = STATE.get("route_catalog", []) or []
    matching_debug = STATE.get("matching_debug", []) or []
    route_match_candidates = STATE.get("route_match_candidates", []) or []
    committed_rows = STATE.get("committed_rows", []) or []
    grouped_rows_summary = _grouping_summary_from_rows(committed_rows)
    compact_group_summaries = [_compact_group_payload_entry(entry) for entry in route_match_candidates]
    rendered_group_count = sum(1 for entry in compact_group_summaries if entry.get("render_allowed"))
    blocked_group_count = max(0, len(compact_group_summaries) - rendered_group_count)

    coverage_basis_segments = redline_segments
    coverage_summary = _unique_coverage_summary(redline_segments)
    active_route_coverage_summary = _unique_coverage_summary(active_route_redline_segments)

    coverage_route_ids = {
        str(route_entry.get("route_id") or "").strip()
        for route_entry in (coverage_summary.get("routes") or [])
        if str(route_entry.get("route_id") or "").strip()
    }
    if coverage_route_ids:
        total_design_length_ft = sum(
            float(route_entry.get("length_ft", 0.0) or 0.0)
            for route_entry in route_catalog
            if str(route_entry.get("route_id") or "").strip() in coverage_route_ids
        )
    else:
        total_design_length_ft = route_length_ft if route_length_ft > 0.0 else _total_design_length_ft(route_catalog)

    covered_length_ft = float(coverage_summary.get("unique_length_ft", 0.0) or 0.0)
    completion_pct = round((covered_length_ft / total_design_length_ft) * 100.0, 2) if total_design_length_ft > 0 else 0.0
    active_route_covered_length_ft = float(active_route_coverage_summary.get("unique_length_ft", 0.0) or 0.0)
    active_route_completion_pct = round((active_route_covered_length_ft / route_length_ft) * 100.0, 2) if route_length_ft > 0 else 0.0
    merged_segment_count_for_coverage = int(coverage_summary.get("route_merged_interval_count", 0) or 0)
    raw_segment_count_for_coverage = len(redline_segments)
    runtime_verification = _coverage_runtime_verification(redline_segments, coverage_summary)
    active_route_runtime_verification = _coverage_runtime_verification(active_route_redline_segments, active_route_coverage_summary)

    verification_summary = STATE.get("verification_summary", {}) or {}
    selected_route_match_summary = _selected_route_match_summary(STATE.get("selected_route_match"))

    # Geotagged station photos scoped to the current session only.
    # Phase 1: active session_id is the only filter — no cross-session exposure.
    _photo_session = str(STATE.get("_session_id_hint") or "").strip()
    photo_points: list = []
    if _photo_session:
        for _prec in (_load_station_photo_index().get("photos") or []):
            if not _station_photo_record_matches_session(_prec, _photo_session):
                continue
            try:
                _orig_lat = float(_prec.get("lat") or "")
                _orig_lon = float(_prec.get("lon") or "")
            except (ValueError, TypeError):
                continue
            if not (float("-inf") < _orig_lat < float("inf") and float("-inf") < _orig_lon < float("inf")):
                continue
            _adj_lat = _office_float_or_none(_prec.get("adjusted_lat"))
            _adj_lon = _office_float_or_none(_prec.get("adjusted_lon"))
            _is_adjusted = _adj_lat is not None and _adj_lon is not None
            _display_lat = _adj_lat if _is_adjusted else _orig_lat
            _display_lon = _adj_lon if _is_adjusted else _orig_lon
            photo_points.append({
                "id": str(_prec.get("photo_id") or ""),
                "source_type": "station_photo",
                "lat": _display_lat,
                "lon": _display_lon,
                "thumbnail_url": _station_photo_record_public_url(_prec),
                "original_url": _station_photo_record_public_url(_prec),
                "filename": str(_prec.get("original_filename") or ""),
                "station_label": str(_prec.get("station_label") or ""),
                "session_id": str(_prec.get("session_id") or ""),
                "uploaded_at": str(_prec.get("uploaded_at") or ""),
                "note": _prec.get("note"),
                "original_lat": _orig_lat,
                "original_lon": _orig_lon,
                "adjusted_lat": _adj_lat,
                "adjusted_lon": _adj_lon,
                "adjusted_at": str(_prec.get("adjusted_at") or "") or None,
                "is_adjusted": _is_adjusted,
            })

    if include_debug:
        payload = {
            "route_name": STATE.get("route_name"),
            "suggested_route_id": STATE.get("route_id"),
            "selected_route_id": STATE.get("route_id"),
            "selected_route_name": STATE.get("route_name"),
            "loaded_field_data_files": int(STATE.get("loaded_field_data_files", 0) or 0),
            "latest_structured_file": STATE.get("latest_structured_file"),
            "group_count": len(grouped_rows_summary),
            "rendered_group_count": rendered_group_count,
            "blocked_group_count": blocked_group_count,
            "station_points_count": len(station_points),
            "redline_segments_count": len(redline_segments),
            "total_row_count": len(committed_rows),
            "total_length_ft": total_design_length_ft,
            "covered_length_ft": covered_length_ft,
            "completion_pct": completion_pct,
            "station_mapping_mode": STATE.get("station_mapping_mode"),
            "station_mapping_min_ft": STATE.get("station_mapping_min_ft"),
            "station_mapping_max_ft": STATE.get("station_mapping_max_ft"),
            "station_mapping_range_ft": STATE.get("station_mapping_range_ft"),
            "verification_summary": verification_summary,
            "bug_report_count": len(STATE.get("bug_reports", []) or []),
            "recent_bug_reports": (STATE.get("bug_reports", []) or [])[:10],
            "billing": {
                "material_rate_per_ft": 3.5,
                "splicing_rate_per_ft": 1.5,
                "footage_ft": covered_length_ft,
                "material_total": round(covered_length_ft * 3.5, 2),
                "splicing_total": round(covered_length_ft * 1.5, 2),
                "grand_total": round((covered_length_ft * 3.5) + (covered_length_ft * 1.5), 2),
            },
            "counts": {
                "route_catalog": len(route_catalog),
                "route_match_candidates": len(route_match_candidates),
                "matching_debug": len(matching_debug),
                "station_points": len(station_points),
                "redline_segments": len(redline_segments),
            },
            "grouping_summary": grouped_rows_summary,
            "group_summaries": compact_group_summaries,
            "kmz_reference": _kmz_reference_lite(),
            "selected_route_match": STATE.get("selected_route_match"),
            "route_coords": route_coords,
            "map_points": route_coords,
            "committed_rows": committed_rows,
            "station_points": station_points,
            "redline_segments": redline_segments,
            "coverage_summary": coverage_summary,
            "active_route_coverage_summary": active_route_coverage_summary,
            "coverage_debug": {
                "coverage_basis": "all_final_redline_segments",
                "selected_route_length_ft": route_length_ft,
                "summary_total_length_ft": total_design_length_ft,
                "raw_final_redline_segment_count": raw_segment_count_for_coverage,
                "merged_segment_count": merged_segment_count_for_coverage,
            },
            "runtime_verification": runtime_verification,
            "active_route_runtime_verification": active_route_runtime_verification,
            "route_catalog": route_catalog,
            "route_match_candidates": route_match_candidates,
            "group_outputs": route_match_candidates,
            "matching_debug": matching_debug,
            "kmz_reference_full": STATE.get("kmz_reference", {}) or {},
            # Phase 1A additive semantic layer. None when no KMZ has been
            # uploaded or when the additive parse failed; consumers must
            # treat the absence as "no semantic data".
            "kmz_semantic": STATE.get("kmz_semantic") or None,
            # Phase 1C — SHADOW MODE diagnostics. Pure read of STATE; never
            # alters matching, station_points, redline_segments, or
            # selected_route_match. None when prerequisites missing.
            "kmz_semantic_match_shadow": _build_semantic_match_shadow(),
            "engineering_plans": _load_engineering_plan_index_for_session(STATE.get("_session_id_hint", "")),
            "bore_log_summary": _bore_log_summary_from_rows(committed_rows),
            "photo_points": photo_points,
            "closeout_lock": _normalize_closeout_lock(STATE.get("closeout_lock")),
            **_closeout_flat_fields(),
        }
        return payload

    return {
        "route_id": route_id,
        "suggested_route_id": route_id,
        "selected_route_id": route_id,
        "route_name": STATE.get("route_name"),
        "selected_route_name": STATE.get("route_name"),
        "route_length_ft": route_length_ft,
        "route_coords": route_coords,
        "map_points": route_coords,
        "kmz_reference": _kmz_reference_lite(),
        "loaded_field_data_files": int(STATE.get("loaded_field_data_files", 0) or 0),
        "latest_structured_file": STATE.get("latest_structured_file"),
        "group_count": len(grouped_rows_summary),
        "rendered_group_count": rendered_group_count,
        "blocked_group_count": blocked_group_count,
        "station_points_count": len(station_points),
        "redline_segments_count": len(redline_segments),
        "station_points": station_points,
        "redline_segments": redline_segments,
        "active_route_station_points_count": len(active_route_station_points),
        "active_route_redline_segments_count": len(active_route_redline_segments),
        "active_route_station_points": active_route_station_points,
        "active_route_redline_segments": active_route_redline_segments,
        "total_row_count": len(committed_rows),
        "total_length_ft": total_design_length_ft,
        "covered_length_ft": covered_length_ft,
        "completion_pct": completion_pct,
        "active_route_covered_length_ft": active_route_covered_length_ft,
        "active_route_completion_pct": active_route_completion_pct,
        "billing": {
            "material_rate_per_ft": 3.5,
            "splicing_rate_per_ft": 1.5,
            "footage_ft": covered_length_ft,
            "material_total": round(covered_length_ft * 3.5, 2),
            "splicing_total": round(covered_length_ft * 1.5, 2),
            "grand_total": round((covered_length_ft * 3.5) + (covered_length_ft * 1.5), 2),
        },
        "coverage_debug": {
            "coverage_basis": "all_final_redline_segments",
            "selected_route_length_ft": route_length_ft,
            "summary_total_length_ft": total_design_length_ft,
            "raw_final_redline_segment_count": raw_segment_count_for_coverage,
            "merged_segment_count": merged_segment_count_for_coverage,
        },
        "station_mapping_mode": STATE.get("station_mapping_mode"),
        "station_mapping_min_ft": STATE.get("station_mapping_min_ft"),
        "station_mapping_max_ft": STATE.get("station_mapping_max_ft"),
        "station_mapping_range_ft": STATE.get("station_mapping_range_ft"),
        "selected_route_match": selected_route_match_summary,
        "verification_summary": {
            "status": verification_summary.get("status"),
            "version": verification_summary.get("version"),
            "route_selection_method": verification_summary.get("route_selection_method"),
            "route_selection_reason": verification_summary.get("route_selection_reason"),
            "group_count": verification_summary.get("group_count"),
            "unique_matched_routes": verification_summary.get("unique_matched_routes"),
            "rendered_group_count": verification_summary.get("rendered_group_count"),
            "blocked_group_count": verification_summary.get("blocked_group_count"),
            "warn_count": verification_summary.get("warn_count"),
            "fail_count": verification_summary.get("fail_count"),
        },
        "bug_report_count": len(STATE.get("bug_reports", []) or []),
        "matching_debug_count": len(matching_debug),
        "route_match_candidate_count": len(route_match_candidates),
        "runtime_verification": runtime_verification,
        "active_route_runtime_verification": active_route_runtime_verification,
        "engineering_plans": _load_engineering_plan_index_for_session(STATE.get("_session_id_hint", "")),
        "bore_log_summary": _bore_log_summary_from_rows(committed_rows),
        "photo_points": photo_points,
        # Phase 1A additive semantic layer. None when no KMZ has been
        # uploaded or when the additive parse failed; consumers must treat
        # the absence as "no semantic data".
        "kmz_semantic": STATE.get("kmz_semantic") or None,
        # Phase 1C — SHADOW MODE diagnostics. Read-only, additive.
        "kmz_semantic_match_shadow": _build_semantic_match_shadow(),
        "closeout_lock": _normalize_closeout_lock(STATE.get("closeout_lock")),
        **_closeout_flat_fields(),
    }


@protected_router.post("/api/upload-design")
async def upload_design(
    file: UploadFile = File(...),
    session_id: Optional[str] = Form(None),
    project_id: Optional[str] = Form(None),
) -> JSONResponse:
    resolved_session_id = _resolve_session_id(session_id)
    print(
        f"[KMZ_SEM_TRACE] upload_design enter form_session_id={session_id!r} "
        f"resolved_session_id={resolved_session_id}",
        flush=True,
    )
    try:
        file_bytes = await file.read()
        with _session_scope(resolved_session_id):
            if _is_closeout_locked():
                return _json_closeout_locked_response()
            route_catalog = _build_route_catalog(file_bytes, file.filename or "design.kmz")
            STATE["route_catalog"] = route_catalog
            STATE["kmz_reference"] = _build_kmz_reference(file_bytes, file.filename or "design.kmz")
            # Phase 1A: additive semantic layer. Computed alongside the
            # existing kmz_reference; any failure here MUST NOT break the
            # upload, route extraction, or rendering — _build_kmz_semantic
            # returns None on error and STATE["kmz_semantic"] simply stays
            # None, which downstream consumers treat as "no semantic data
            # available".
            try:
                print(
                    f"[KMZ_SEM_TRACE] upload_design calling _build_kmz_semantic "
                    f"STATE_hint={STATE.get('_session_id_hint')}",
                    flush=True,
                )
                semantic = _build_kmz_semantic(file_bytes, file.filename or "design.kmz")
                STATE["kmz_semantic"] = semantic
                _fc = (
                    len(semantic["features"])
                    if semantic and isinstance(semantic.get("features"), list)
                    else None
                )
                print(
                    f"[KMZ_SEM_TRACE] upload_design assigned kmz_semantic "
                    f"is_none={semantic is None} feature_count={_fc} "
                    f"STATE_hint={STATE.get('_session_id_hint')} "
                    f"matches_resolved={str(STATE.get('_session_id_hint')) == str(resolved_session_id)}",
                    flush=True,
                )
            except Exception as _kmz_sem_exc:
                import traceback as _kmz_sem_tb

                print(
                    f"[KMZ_SEM_TRACE] upload_design _build_kmz_semantic RAISED: "
                    f"{type(_kmz_sem_exc).__name__}: {_kmz_sem_exc}",
                    flush=True,
                )
                _kmz_sem_tb.print_exc()
                STATE["kmz_semantic"] = None

            # Phase 1D — ledger entry. Runs regardless of parse success/failure.
            # Uses STATE.get("kmz_semantic") so the None path is also recorded.
            _append_ingestion_ledger_entry(
                file_bytes,
                file.filename or "design.kmz",
                STATE.get("kmz_semantic"),
            )
            # Phase 1F — stash SHA so _append_match_audit_entry can link the
            # subsequent active_route_set row to this ingestion ledger entry.
            STATE["last_kmz_input_sha256"] = hashlib.sha256(file_bytes).hexdigest()
            # Phase 1O — build topology lineage sidecar. Additive, isolated.
            # Failure here MUST NOT break upload, routing, or rendering.
            try:
                STATE["kmz_topology_sidecar"] = _build_kmz_topology_sidecar(
                    STATE.get("kmz_semantic"),
                    STATE.get("kmz_reference"),
                )
            except Exception as _sidecar_exc:
                STATE["kmz_topology_sidecar"] = None
                print(
                    f"[KMZ_TOPOLOGY_SIDECAR] WARNING: sidecar build failed: "
                    f"{type(_sidecar_exc).__name__}: {_sidecar_exc}",
                    flush=True,
                )

            default_route = _choose_default_route(route_catalog)
            _set_active_route(default_route)

            rebuild_warning: Optional[str] = None

            if STATE.get("committed_rows"):
                try:
                    _rebuild_field_data_outputs()
                except Exception as rebuild_exc:
                    STATE["station_points"] = []
                    STATE["redline_segments"] = []
                    STATE["selected_route_match"] = None
                    STATE["route_match_candidates"] = []
                    STATE["matching_debug"] = []
                    STATE["verification_summary"] = {
                        "status": "kmz_loaded_rebuild_pending",
                        "version": "v2",
                        "route_selection_method": "independent_candidate_scoring_per_group",
                        "route_selection_reason": "KMZ loaded successfully, but existing bore-log data needs to be re-uploaded after route rebuild failed.",
                        "group_count": 0,
                        "unique_matched_routes": 0,
                    }
                    rebuild_warning = f"KMZ uploaded, but previous bore-log overlays were cleared because rebuild failed: {rebuild_exc}"
            else:
                STATE["station_points"] = []
                STATE["redline_segments"] = []
                STATE["selected_route_match"] = None
                STATE["route_match_candidates"] = []
                STATE["matching_debug"] = []
                STATE["verification_summary"] = {
                    "status": "awaiting_bore_logs",
                    "version": "v2",
                    "route_selection_method": "independent_candidate_scoring_per_group",
                    "route_selection_reason": "KMZ candidate routes loaded. Bore-log matching will happen independently per group after field data upload.",
                    "group_count": 0,
                    "unique_matched_routes": 0,
                }

            walk_project_id = _normalize_walk_project_id(project_id)
            if walk_project_id:
                try:
                    _save_project_route_context(
                        walk_project_id,
                        list(STATE.get("route_catalog", []) or []),
                    )
                except Exception:
                    pass

            payload = _summary_payload()
            if rebuild_warning:
                payload["warning"] = rebuild_warning
                payload["message"] = "Design uploaded successfully with previous overlays cleared."
                return _ok(session_id=resolved_session_id, **payload)

            return _ok(session_id=resolved_session_id, message="Design uploaded successfully", **payload)
    except Exception as exc:
        return _err(str(exc), session_id=resolved_session_id)


@protected_router.post("/api/select-active-route")
async def select_active_route(
    route_id: str = Form(...),
    session_id: Optional[str] = Form(None),
) -> JSONResponse:
    resolved_session_id = _resolve_session_id(session_id)
    try:
        with _session_scope(resolved_session_id):
            if _is_closeout_locked():
                return _json_closeout_locked_response()
            matched_route = _find_route_by_id(route_id)
            if not matched_route:
                return _err("Route not found.", status_code=404, session_id=resolved_session_id)

            _set_active_route(matched_route)
            return _ok(session_id=resolved_session_id, message="Active route updated", **_summary_payload())
    except Exception as exc:
        return _err(str(exc), session_id=resolved_session_id)


@protected_router.post("/api/upload-structured-bore-files")
async def upload_structured_bore_files(
    files: List[UploadFile] = File(...),
    session_id: Optional[str] = Form(None),
) -> JSONResponse:
    resolved_session_id = _resolve_session_id(session_id)
    try:
        prepared_files: List[Tuple[str, bytes]] = []
        latest_name: Optional[str] = None
        for file in files:
            file_bytes = await file.read()
            latest_name = file.filename or "structured_file"
            prepared_files.append((latest_name, file_bytes))

        with _session_scope(resolved_session_id):
            if _is_closeout_locked():
                return _json_closeout_locked_response()
            existing_rows = list(STATE.get("committed_rows", []) or [])
            existing_by_file: Dict[str, List[Dict[str, Any]]] = {}
            for row in existing_rows:
                source_file = str(row.get("source_file") or "").strip()
                if not source_file:
                    continue
                existing_by_file.setdefault(source_file, []).append(row)

            for filename, file_bytes in prepared_files:
                existing_by_file[filename] = _read_bore_log_rows(file_bytes, filename)

            merged_rows: List[Dict[str, Any]] = []
            for source_file in sorted(existing_by_file.keys()):
                merged_rows.extend(existing_by_file[source_file])

            STATE["committed_rows"] = merged_rows
            STATE["loaded_field_data_files"] = len(existing_by_file)
            STATE["latest_structured_file"] = latest_name

            _rebuild_field_data_outputs()
            return _ok(session_id=resolved_session_id, message="Bore logs uploaded successfully", **_summary_payload())
    except Exception as exc:
        return _err(str(exc), session_id=resolved_session_id)



@protected_router.post("/api/reset-state")
def reset_state(session_id: Optional[str] = None) -> JSONResponse:
    resolved_session_id = _resolve_session_id(session_id)
    with _session_scope(resolved_session_id):
        if _is_closeout_locked():
            return _json_closeout_locked_response()
        _reset_workspace_state()
        return _ok(session_id=resolved_session_id, message="Workspace reset successfully", **_summary_payload())


@protected_router.get("/api/current-state")
def current_state(session_id: Optional[str] = None) -> JSONResponse:
    resolved_session_id = _resolve_session_id(session_id)
    print(
        f"[KMZ_SEM_TRACE] current-state query session_id={session_id!r} "
        f"resolved_session_id={resolved_session_id} "
        f"(if query was empty/omitted, resolved is a NEW uuid each request)",
        flush=True,
    )
    with _session_scope(resolved_session_id):
        _sem = STATE.get("kmz_semantic")
        _fc = (
            len(_sem["features"])
            if isinstance(_sem, dict) and isinstance(_sem.get("features"), list)
            else None
        )
        print(
            f"[KMZ_SEM_TRACE] current-state inside scope "
            f"kmz_semantic_is_none={_sem is None} feature_count={_fc} "
            f"STATE_hint={STATE.get('_session_id_hint')} "
            f"matches_resolved={str(STATE.get('_session_id_hint')) == str(resolved_session_id)}",
            flush=True,
        )
        return _ok(session_id=resolved_session_id, **_summary_payload(include_debug=False))


@localhost_router.get("/api/debug-state")
def debug_state(session_id: Optional[str] = None) -> JSONResponse:
    # Private beta isolation: require explicit session_id
    sid = str(session_id or "").strip()
    if not sid:
        return JSONResponse(status_code=400, content={"error": "session_id is required"})
    with _session_scope(sid):
        return _ok(session_id=sid, **_summary_payload(include_debug=True))


@localhost_router.get("/api/debug/pipeline-diag")
def debug_pipeline_diag(session_id: Optional[str] = None, source_file: Optional[str] = None) -> JSONResponse:
    """Read-only diagnostic endpoint.  Returns per-group pipeline traces written by
    _rebuild_field_data_outputs, plus extracted engineering plan signals (Phase 1).
    - Pass session_id= to read a specific session (same behaviour as /api/current-state).
    - Use source_file= to filter pipeline_diag to a single source file.
    Engineering plan signals are always returned unfiltered."""
    # Private beta isolation: require explicit session_id
    sid = str(session_id or "").strip()
    if not sid:
        return JSONResponse(status_code=400, content={"error": "session_id is required"})
    # Exact-session path — identical to how every other endpoint works.
    with _session_scope(sid):
        diag: List[Dict[str, Any]] = list(STATE.get("pipeline_diag") or [])
        # Read plan signals from STATE if already extracted; otherwise derive fresh.
        plan_signals: List[Dict[str, Any]] = list(STATE.get("engineering_plan_signals") or [])
        if not plan_signals:
            plan_signals = _build_engineering_plan_signals_for_session(sid)
    if source_file:
        diag = [d for d in diag if str(d.get("source_file") or "").lower() == source_file.lower()]
    return JSONResponse(content={
        "success": True,
        "session_id": sid,
        "pipeline_diag": diag,
        "engineering_plan_signal_count": len(plan_signals),
        "engineering_plan_signals": plan_signals,
    })


@protected_router.post("/api/report-bug")
def report_bug(payload: Dict[str, Any] = Body(...), session_id: Optional[str] = None) -> JSONResponse:
    body_session_id = payload.get("session_id") if isinstance(payload, dict) else None
    resolved_session_id = _resolve_session_id(session_id or body_session_id)
    with _session_scope(resolved_session_id):
        if _is_closeout_locked():
            return _json_closeout_locked_response()
        bug_reports = list(STATE.get("bug_reports", []) or [])
        entry = {
            "id": str(payload.get("id") or ""),
            "timestamp": str(payload.get("timestamp") or ""),
            "level": str(payload.get("level") or "info"),
            "category": str(payload.get("category") or "ui"),
            "message": str(payload.get("message") or ""),
            "details": payload.get("details") if isinstance(payload.get("details"), dict) else {},
        }
        bug_reports.insert(0, entry)
        STATE["bug_reports"] = bug_reports[:200]
        return _ok(session_id=resolved_session_id, message="Bug report captured", bug_report_count=len(STATE["bug_reports"]))


@protected_router.get("/api/bug-reports")
def get_bug_reports(session_id: Optional[str] = None) -> JSONResponse:
    resolved_session_id = _resolve_session_id(session_id)
    with _session_scope(resolved_session_id):
        return _ok(session_id=resolved_session_id, bug_reports=STATE.get("bug_reports", []) or [])


@localhost_router.get("/api/observability/ingestion-ledger")
def get_ingestion_ledger(limit: int = 25) -> JSONResponse:
    """Phase 1D — read-only view of the most recent ingestion ledger rows.

    Query param: ``limit`` (default 25, max 100). Returns rows in reverse
    chronological order (most recent first). A missing or corrupt ledger file
    returns ``{"entries": []}``.
    """
    limit = max(1, min(limit, 100))
    try:
        if not INGESTION_LEDGER_PATH.exists():
            return JSONResponse({"entries": []})
        with open(INGESTION_LEDGER_PATH, "r", encoding="utf-8") as _fh:
            raw_lines = _fh.readlines()
        entries: List[Dict[str, Any]] = []
        for line in reversed(raw_lines):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
            if len(entries) >= limit:
                break
        return JSONResponse({"entries": entries})
    except Exception as _led_read_exc:
        print(
            f"[INGESTION_LEDGER] WARNING: failed to read ledger: "
            f"{type(_led_read_exc).__name__}: {_led_read_exc}",
            flush=True,
        )
        return JSONResponse({"entries": []})


@localhost_router.get("/api/observability/match-audit")
def get_match_audit(limit: int = 25) -> JSONResponse:
    """Phase 1F — read-only view of the most recent match audit rows.

    Query param: ``limit`` (default 25, max 200). Returns rows in reverse
    chronological order (most recent first). A missing or corrupt audit file
    returns ``{"entries": []}``.
    """
    limit = max(1, min(limit, 200))
    try:
        if not MATCH_AUDIT_PATH.exists():
            return JSONResponse({"entries": []})
        with open(MATCH_AUDIT_PATH, "r", encoding="utf-8") as _fh:
            raw_lines = _fh.readlines()
        entries: List[Dict[str, Any]] = []
        for line in reversed(raw_lines):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
            if len(entries) >= limit:
                break
        return JSONResponse({"entries": entries})
    except Exception as _aud_read_exc:
        print(
            f"[MATCH_AUDIT] WARNING: failed to read audit: "
            f"{type(_aud_read_exc).__name__}: {_aud_read_exc}",
            flush=True,
        )
        return JSONResponse({"entries": []})


@localhost_router.get("/api/observability/match-audit-groups")
def get_match_audit_groups(limit: int = 50) -> JSONResponse:
    """Phase 1G — read-only view of the most recent per-group match audit rows.

    Schema version: "match-audit-2".  Query param: ``limit`` (default 50,
    max 500). Returns rows in reverse chronological order (most recent first).
    A missing or corrupt file returns ``{"entries": []}``.
    """
    limit = max(1, min(limit, 500))
    try:
        if not MATCH_AUDIT_GROUPS_PATH.exists():
            return JSONResponse({"entries": []})
        with open(MATCH_AUDIT_GROUPS_PATH, "r", encoding="utf-8") as _fh:
            raw_lines = _fh.readlines()
        entries: List[Dict[str, Any]] = []
        for line in reversed(raw_lines):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
            if len(entries) >= limit:
                break
        return JSONResponse({"entries": entries})
    except Exception as _v2_read_exc:
        print(
            f"[MATCH_AUDIT_V2] WARNING: failed to read audit groups: "
            f"{type(_v2_read_exc).__name__}: {_v2_read_exc}",
            flush=True,
        )
        return JSONResponse({"entries": []})


# ─── Private beta session observability ────────────────────────────────────
# Lightweight read-only endpoint for inspecting persisted session metadata.
# Protected by observability middleware; returns summaries only.
@localhost_router.get("/api/observability/sessions")
def get_sessions_observability(limit: int = 50) -> JSONResponse:
    """Private beta — read-only view of persisted session metadata summaries.

    Query param: ``limit`` (default 50, max 500). Returns sessions in reverse
    chronological order (most recently updated first). Malformed sessions are
    safely skipped. Returns lightweight summaries only.
    """
    limit = max(1, min(limit, 500))
    try:
        with sqlite3.connect(SESSION_DB_PATH) as conn:
            cursor = conn.execute("""
                SELECT session_id, session_json, updated_at
                FROM sessions
                ORDER BY updated_at DESC
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
        summaries = []
        for row in rows:
            session_id, session_json, updated_at = row
            try:
                session_data = json.loads(session_json)
                company_id = session_data.get("company_id")
                workspace_label = session_data.get("workspace_label")
                created_at = session_data.get("created_at")
                route_catalog = session_data.get("route_catalog", [])
                route_count = len(route_catalog) if isinstance(route_catalog, list) else 0
                summaries.append({
                    "session_id": session_id,
                    "company_id": company_id,
                    "workspace_label": workspace_label,
                    "created_at": created_at,
                    "updated_at": updated_at,
                    "route_count": route_count,
                })
            except (json.JSONDecodeError, KeyError, TypeError):
                # Safely skip malformed sessions
                continue
        return JSONResponse({"sessions": summaries})
    except Exception as e:
        logging.warning(f"Failed to read sessions observability: {e}")
        return JSONResponse({"sessions": []})


# ─── Private beta session labeling ─────────────────────────────────────────
# Protected internal endpoint to label persisted sessions with metadata.
# Updates only company_id, workspace_label, and updated_at.
@localhost_router.post("/api/observability/session-label")
def post_session_label(body: Dict[str, Any]) -> JSONResponse:
    """Private beta — update session metadata labels.

    Request body: {"session_id": "...", "company_id": "...", "workspace_label": "..."}
    Updates persisted session with new labels and current timestamp.
    If session exists in memory, updates there too. Returns updated metadata.
    """
    session_id = body.get("session_id")
    if not session_id or not isinstance(session_id, str):
        return JSONResponse(status_code=400, content={"error": "Valid session_id required"})
    
    company_id = body.get("company_id")
    workspace_label = body.get("workspace_label")
    
    try:
        # Load existing session from DB
        existing = _load_persisted_session(session_id)
        if existing is None:
            return JSONResponse(status_code=404, content={"error": "Session not found"})
        
        # Update only metadata fields
        existing["company_id"] = company_id
        existing["workspace_label"] = workspace_label
        existing["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        # Save back to DB
        _persist_session(session_id, existing)
        
        # If in memory, update there too
        with _SESSION_LOCK:
            if session_id in _SESSIONS:
                _SESSIONS[session_id]["company_id"] = company_id
                _SESSIONS[session_id]["workspace_label"] = workspace_label
                _SESSIONS[session_id]["updated_at"] = existing["updated_at"]
        
        return JSONResponse({
            "success": True,
            "session_id": session_id,
            "company_id": company_id,
            "workspace_label": workspace_label,
            "updated_at": existing["updated_at"]
        })
    except Exception as e:
        logging.warning(f"Failed to label session {session_id}: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal error"})


@localhost_router.get("/api/observability/request-audit")
def get_request_audit(limit: int = 100, session_id: Optional[str] = None) -> JSONResponse:
    """private beta request audit observability

    Read-only view of recent request audit records written to
    `uploads/request_audit.jsonl`. Protected by observability middleware.

    Query params: limit (default 100, max 500), session_id (optional filter).
    Returns newest-first records. Malformed JSON lines are skipped.
    """
    limit = max(1, min(limit or 100, 500))
    try:
        if not REQUEST_AUDIT_PATH.exists():
            return JSONResponse({"records": []})
        with open(REQUEST_AUDIT_PATH, "r", encoding="utf-8") as _fh:
            raw_lines = _fh.readlines()
        records: List[Dict[str, Any]] = []
        for line in reversed(raw_lines):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            # Filter by session_id if provided
            if session_id:
                if str(rec.get("session_id") or "") != str(session_id):
                    continue
            records.append(rec)
            if len(records) >= limit:
                break
        return JSONResponse({"records": records})
    except Exception as e:
        logging.warning(f"Failed to read request audit: {e}")
        return JSONResponse({"records": []})


@localhost_router.get("/api/observability/match-shadow-compare")
def get_match_shadow_compare(limit: int = 50) -> JSONResponse:
    """Phase 1H-A — read-only view of the most recent shadow-compare rows.

    Schema version: "match-shadow-1".  Query param: ``limit`` (default 50,
    max 500). Returns rows in reverse chronological order (most recent first).
    A missing or corrupt file returns ``{"entries": []}``.
    """
    limit = max(1, min(limit, 500))
    try:
        if not MATCH_SHADOW_COMPARE_PATH.exists():
            return JSONResponse({"entries": []})
        with open(MATCH_SHADOW_COMPARE_PATH, "r", encoding="utf-8") as _fh_sc:
            raw_lines_sc = _fh_sc.readlines()
        entries_sc: List[Dict[str, Any]] = []
        for line in reversed(raw_lines_sc):
            line = line.strip()
            if not line:
                continue
            try:
                entries_sc.append(json.loads(line))
            except json.JSONDecodeError:
                continue
            if len(entries_sc) >= limit:
                break
        return JSONResponse({"entries": entries_sc})
    except Exception as _sc_read_exc:
        print(
            f"[MATCH_SHADOW] WARNING: failed to read shadow-compare file: "
            f"{type(_sc_read_exc).__name__}: {_sc_read_exc}",
            flush=True,
        )
        return JSONResponse({"entries": []})


@localhost_router.get("/api/observability/match-shadow-summary")
def get_match_shadow_summary(
    limit: int = 500,
    group_by: str = "none",
) -> JSONResponse:
    """Phase 1H-B-I — on-the-fly summary analytics over match-shadow-1 rows.

    Schema version: "match-shadow-summary-1".

    Query params:
      ``limit``    — rows to scan (default 500, max 5000, min 1).
      ``group_by`` — "none" (default) or "input_sha256".
                    Any other value is silently coerced to "none".

    Always returns HTTP 200.  A missing or unreadable file returns an empty
    summary skeleton.  Reads ``MATCH_SHADOW_COMPARE_PATH`` only; no writes.
    """
    from datetime import timezone as _tz_sum

    _computed_at = datetime.now(_tz_sum.utc).isoformat()
    _limit = max(1, min(limit, 5000))
    _group_by = group_by if group_by in ("none", "input_sha256") else "none"

    try:
        _rows_sum: List[Dict[str, Any]] = []
        if MATCH_SHADOW_COMPARE_PATH.exists():
            with open(MATCH_SHADOW_COMPARE_PATH, "r", encoding="utf-8") as _fh_sum:
                _raw_sum = _fh_sum.readlines()
            for _line in reversed(_raw_sum):
                _line = _line.strip()
                if not _line:
                    continue
                try:
                    _rows_sum.append(json.loads(_line))
                except json.JSONDecodeError:
                    continue
                if len(_rows_sum) >= _limit:
                    break

        _summary = _compute_match_shadow_summary(_rows_sum, _group_by)
        _summary["computed_at"] = _computed_at
        return JSONResponse(_summary)

    except Exception as _sum_read_exc:
        print(
            f"[MATCH_SHADOW_SUMMARY] WARNING: failed to build summary: "
            f"{type(_sum_read_exc).__name__}: {_sum_read_exc}",
            flush=True,
        )
        _empty = _compute_match_shadow_summary([], "none")
        _empty["computed_at"] = _computed_at
        return JSONResponse(_empty)


# ---------------------------------------------------------------------------
# Phase 1I-A — Semantic disagreement drilldown
# ---------------------------------------------------------------------------


def _compute_match_shadow_disagreements(
    rows: List[Dict[str, Any]],
    min_review_priority: str,
) -> Dict[str, Any]:
    """Phase 1I-A — on-the-fly disagreement taxonomy over match-shadow-1 rows.

    Schema version: "match-shadow-disagreements-1".

    Pure function.  Takes a list of parsed match-shadow-1 row dicts
    (most-recent-first) and a min_review_priority filter string.
    Returns a 5-key dict; the calling endpoint adds ``computed_at``,
    ``window``, and ``guards`` for 8 total top-level keys.
    NEVER raises.
    """
    # All constants are local — no new module-level names.
    _DOMINANT_THRESHOLD: int = 3
    _THIN_TOTAL_THRESHOLD: int = 2
    _APPROVED_LABELS: List[str] = sorted([
        "DOMINANT_SHADOW_SUPPORT",
        "MODEST_SHADOW_SUPPORT",
        "COMPETING_SUPPORT",
        "THIN_EVIDENCE",
        "NO_CONTRIBUTORS_LISTED",
    ])
    _PRIORITY_ORDER: Dict[str, int] = {"elevated": 2, "standard": 1, "low": 0}
    _STABILITY_NOTE: str = (
        "match-shadow-disagreements-1 labels describe disagreement EVIDENCE "
        "STRENGTH ONLY.  They are not claims about correctness of the "
        "operational winner or the semantic winner.  Review priority is "
        "PROVISIONAL until at least 3 distinct telecom KMZs have generated "
        "shadow rows AND operator annotations exist.  Read-only, additive, "
        "diagnostic only."
    )

    def _empty_skeleton() -> Dict[str, Any]:
        return {
            "schema_version": "match-shadow-disagreements-1",
            "filters": {"min_review_priority": min_review_priority},
            "taxonomy": {
                "totals_by_priority": {"elevated": 0, "standard": 0, "low": 0},
                "totals_by_kind": {lbl: 0 for lbl in _APPROVED_LABELS},
                "approved_labels": _APPROVED_LABELS,
            },
            "entries": [],
            "stability_note": _STABILITY_NOTE,
        }

    try:
        _mrp: str = (
            min_review_priority
            if min_review_priority in _PRIORITY_ORDER
            else "standard"
        )
        _min_rank: int = _PRIORITY_ORDER[_mrp]

        entries: List[Dict[str, Any]] = []
        totals_by_priority: Dict[str, int] = {"elevated": 0, "standard": 0, "low": 0}
        totals_by_kind: Dict[str, int] = {lbl: 0 for lbl in _APPROVED_LABELS}

        for _row in rows:
            if not isinstance(_row, dict):
                continue

            # Hard filters — keep only genuine shadow disagreements.
            if _row.get("had_shadow_payload") is not True:
                continue
            if _row.get("agreement") is not False:
                continue
            _op_id = _row.get("operational_winner_route_id")
            _sem_id = _row.get("semantic_winner_route_id")
            # Defensive: skip rows where both IDs are identical (should not
            # occur when agreement=False, but guard anyway).
            if _op_id and _sem_id and _op_id == _sem_id:
                continue

            # Classification inputs.
            try:
                _anch_op = int(_row.get("anchors_near_operational_winner") or 0)
                _anch_sem = int(_row.get("anchors_near_semantic_winner") or 0)
            except (TypeError, ValueError):
                _anch_op, _anch_sem = 0, 0
            _contrib_ids = _row.get("contributing_anchor_ids") or []
            _contrib_count = (
                len(_contrib_ids) if isinstance(_contrib_ids, list) else 0
            )

            # Multi-label classification.
            _labels: List[str] = []
            if _anch_op == 0 and _anch_sem >= _DOMINANT_THRESHOLD:
                _labels.append("DOMINANT_SHADOW_SUPPORT")
            if _anch_op == 0 and 1 <= _anch_sem <= 2:
                _labels.append("MODEST_SHADOW_SUPPORT")
            if _anch_op >= 1 and _anch_sem >= 1:
                _labels.append("COMPETING_SUPPORT")
            if (_anch_op + _anch_sem) <= _THIN_TOTAL_THRESHOLD:
                _labels.append("THIN_EVIDENCE")
            if _contrib_count == 0 and _anch_sem > 0:
                _labels.append("NO_CONTRIBUTORS_LISTED")

            # Priority assignment.
            _reasons: List[str]
            if (
                "DOMINANT_SHADOW_SUPPORT" in _labels
                and "THIN_EVIDENCE" not in _labels
                and "NO_CONTRIBUTORS_LISTED" not in _labels
            ):
                _priority = "elevated"
                _reasons = [
                    "dominant_shadow_support",
                    "non_thin_evidence",
                    "contributors_listed",
                ]
            elif (
                (
                    "COMPETING_SUPPORT" in _labels
                    or "MODEST_SHADOW_SUPPORT" in _labels
                )
                and "THIN_EVIDENCE" not in _labels
            ):
                _priority = "standard"
                _reasons = ["competing_or_modest_support", "non_thin_evidence"]
            elif "THIN_EVIDENCE" in _labels and len(_labels) == 1:
                _priority = "low"
                _reasons = ["thin_evidence_only"]
            else:
                _priority = "low"
                _reasons = ["default_low"]

            # Tally by kind and priority (counts reflect ALL disagreements
            # before the min_priority filter is applied, so the taxonomy
            # section is always a full picture of the window).
            for _lbl in _labels:
                if _lbl in totals_by_kind:
                    totals_by_kind[_lbl] += 1
            totals_by_priority[_priority] += 1

            # Apply min_review_priority filter for the entries list only.
            if _PRIORITY_ORDER.get(_priority, 0) < _min_rank:
                continue

            entries.append(
                {
                    "decided_at":                     _row.get("decided_at"),
                    "match_pass_id":                  _row.get("match_pass_id"),
                    "input_sha256":                   _row.get("input_sha256"),
                    "group_id":                       _row.get("group_id"),
                    "operational_winner_route_id":    _op_id,
                    "operational_winner_route_name":  _row.get(
                        "operational_winner_route_name"
                    ),
                    "semantic_winner_route_id":       _sem_id,
                    "semantic_winner_route_name":     _row.get(
                        "semantic_winner_route_name"
                    ),
                    "anchors_near_operational_winner": _anch_op,
                    "anchors_near_semantic_winner":    _anch_sem,
                    "contributing_anchor_count":       _contrib_count,
                    "shadow_explanation":             _row.get("shadow_explanation"),
                    "disagreement_kind":              _labels,
                    "review_priority":                _priority,
                    "review_priority_reasons":        _reasons,
                }
            )

        return {
            "schema_version": "match-shadow-disagreements-1",
            "filters": {"min_review_priority": _mrp},
            "taxonomy": {
                "totals_by_priority": totals_by_priority,
                "totals_by_kind": totals_by_kind,
                "approved_labels": _APPROVED_LABELS,
            },
            "entries": entries,
            "stability_note": _STABILITY_NOTE,
        }

    except Exception:
        return _empty_skeleton()


@localhost_router.get("/api/observability/match-shadow-disagreements")
def get_match_shadow_disagreements(
    limit: int = 500,
    min_review_priority: str = "standard",
) -> JSONResponse:
    """Phase 1I-A — on-the-fly disagreement drilldown over match-shadow-1 rows.

    Schema version: "match-shadow-disagreements-1".

    Query params:
      ``limit``               — rows to scan (default 500, max 5000, min 1).
      ``min_review_priority`` — "elevated" | "standard" (default) | "low".
                               Any other value is silently coerced to "standard".

    Always returns HTTP 200.  A missing or unreadable file returns an empty
    skeleton.  Reads MATCH_SHADOW_COMPARE_PATH only; no writes.

    Top-level response keys (exactly 8):
      schema_version, computed_at, window, filters, taxonomy,
      entries, guards, stability_note.
    """
    from datetime import timezone as _tz_dis

    _computed_at_dis = datetime.now(_tz_dis.utc).isoformat()
    _limit_dis = max(1, min(limit, 5000))
    _mrp_dis = (
        min_review_priority
        if min_review_priority in ("elevated", "standard", "low")
        else "standard"
    )

    try:
        _rows_dis: List[Dict[str, Any]] = []
        _pass_ids_dis: set = set()
        _sha_ids_dis: set = set()
        _earliest_dis: Optional[str] = None
        _latest_dis: Optional[str] = None

        if MATCH_SHADOW_COMPARE_PATH.exists():
            with open(MATCH_SHADOW_COMPARE_PATH, "r", encoding="utf-8") as _fh_dis:
                _raw_dis = _fh_dis.readlines()
            for _line_dis in reversed(_raw_dis):
                _line_dis = _line_dis.strip()
                if not _line_dis:
                    continue
                try:
                    _r_dis = json.loads(_line_dis)
                except json.JSONDecodeError:
                    continue
                _rows_dis.append(_r_dis)
                _pid_dis = _r_dis.get("match_pass_id")
                if _pid_dis:
                    _pass_ids_dis.add(_pid_dis)
                _sha_dis = _r_dis.get("input_sha256")
                if _sha_dis:
                    _sha_ids_dis.add(_sha_dis)
                _ts_dis = _r_dis.get("decided_at")
                if isinstance(_ts_dis, str) and _ts_dis:
                    if _earliest_dis is None or _ts_dis < _earliest_dis:
                        _earliest_dis = _ts_dis
                    if _latest_dis is None or _ts_dis > _latest_dis:
                        _latest_dis = _ts_dis
                if len(_rows_dis) >= _limit_dis:
                    break

        _result_dis = _compute_match_shadow_disagreements(_rows_dis, _mrp_dis)
        _result_dis["computed_at"] = _computed_at_dis
        _result_dis["window"] = {
            "rows_read": len(_rows_dis),
            "match_pass_count": len(_pass_ids_dis),
            "unique_input_sha256_count": len(_sha_ids_dis),
            "earliest_decided_at": _earliest_dis,
            "latest_decided_at": _latest_dis,
        }
        _result_dis["guards"] = {"min_review_priority_default": "standard"}
        return JSONResponse(_result_dis)

    except Exception as _dis_exc:
        print(
            f"[MATCH_SHADOW_DISAGREEMENTS] WARNING: failed to build drilldown: "
            f"{type(_dis_exc).__name__}: {_dis_exc}",
            flush=True,
        )
        _empty_dis = _compute_match_shadow_disagreements([], "standard")
        _empty_dis["computed_at"] = _computed_at_dis
        _empty_dis["window"] = {
            "rows_read": 0,
            "match_pass_count": 0,
            "unique_input_sha256_count": 0,
            "earliest_decided_at": None,
            "latest_decided_at": None,
        }
        _empty_dis["guards"] = {"min_review_priority_default": "standard"}
        return JSONResponse(_empty_dis)


# ---------------------------------------------------------------------------
# Phase 1L — Review-label analytics (compute-on-read, no writes, no state)
# ---------------------------------------------------------------------------


def _compute_review_label_summary(
    label_rows: List[Dict[str, Any]],
    shadow_rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Phase 1L — compute review-label analytics over existing telemetry streams.

    Pure function.  Never raises.  Reads ``label_rows`` (raw rows from
    ``review_labels.jsonl`` in file order) and ``shadow_rows`` (raw rows from
    ``match_shadow_compare.jsonl`` in any order).

    Returns a structured analytics dict.

    WORDING DISCIPLINE: All metrics describe review telemetry patterns only.
    No accuracy, correctness, confidence, or operational guidance language.
    No threshold adjustments.  No route ranking.  No recommendations.
    """
    _MIN_SAMPLES: int = 3
    _STABILITY_NOTE: str = (
        "review-label-summary-1 describes review telemetry patterns only.  "
        "Rates and coverage figures are observational.  They do not reflect "
        "correctness of any routing decision and must not be used to adjust "
        "thresholds, promote routes, or alter any operational behavior.  "
        "Read-only, additive, diagnostic only.  See LABEL_USAGE_POLICY.md."
    )

    def _safe_rate(numerator: int, denominator: int) -> Optional[float]:
        if denominator < _MIN_SAMPLES:
            return None
        return round(numerator / denominator, 4)

    def _empty_skeleton() -> Dict[str, Any]:
        return {
            "schema_version": "review-label-summary-1",
            "window": {
                "label_events_read": 0,
                "shadow_rows_read": 0,
                "resolved_labels": 0,
                "disagreements_in_window": 0,
            },
            "total_review_labels": 0,
            "resolved_label_counts": {"useful_catch": 0, "noise": 0, "unclear": 0},
            "useful_catch_rate_by_review_priority": {
                p: {"labeled": 0, "useful_catch": 0, "rate": None}
                for p in ("elevated", "standard", "low")
            },
            "useful_catch_rate_by_disagreement_kind": [],
            "label_coverage_by_review_priority": {
                p: {"total_disagreements": 0, "labeled": 0, "coverage_rate": None}
                for p in ("elevated", "standard", "low")
            },
            "top_input_sha256_by_noise_rate": [],
            "stability_note": _STABILITY_NOTE,
        }

    try:
        # ------------------------------------------------------------------
        # Step 1: Latest-wins label resolution (oldest → newest = file order).
        # Key: (match_pass_id, group_id) → full event dict.
        # Tombstoned entries are excluded from the resolved set.
        # ------------------------------------------------------------------
        _resolved_map_s: Dict[Any, Dict[str, Any]] = {}
        for _ev_s in label_rows:
            if not isinstance(_ev_s, dict):
                continue
            _k_s = (_ev_s.get("match_pass_id"), _ev_s.get("group_id"))
            _resolved_map_s[_k_s] = _ev_s

        _resolved_s: List[Dict[str, Any]] = [
            _ev_s
            for _ev_s in _resolved_map_s.values()
            if not _ev_s.get("tombstone", False)
        ]

        # ------------------------------------------------------------------
        # Step 2: Raw counts
        # ------------------------------------------------------------------
        total_review_labels_s = len(label_rows)
        resolved_label_counts_s: Dict[str, int] = {
            "useful_catch": 0,
            "noise": 0,
            "unclear": 0,
        }
        for _ev_s in _resolved_s:
            _lbl_s = _ev_s.get("label")
            if _lbl_s in resolved_label_counts_s:
                resolved_label_counts_s[_lbl_s] += 1

        # ------------------------------------------------------------------
        # Step 3: All disagreements from shadow rows.
        # Use min_review_priority="low" so the entries list includes everything.
        # ------------------------------------------------------------------
        _dis_result_s = _compute_match_shadow_disagreements(shadow_rows, "low")
        _dis_entries_s: List[Dict[str, Any]] = _dis_result_s.get("entries") or []
        _dis_taxonomy_s = _dis_result_s.get("taxonomy") or {}
        _totals_by_pri_s: Dict[str, int] = _dis_taxonomy_s.get(
            "totals_by_priority"
        ) or {"elevated": 0, "standard": 0, "low": 0}
        total_disagreements_s = sum(_totals_by_pri_s.values())

        # Build lookup: (match_pass_id, group_id) → disagreement entry.
        _dis_lkp_s: Dict[Any, Dict[str, Any]] = {}
        for _de_s in _dis_entries_s:
            _dk_s = (_de_s.get("match_pass_id"), _de_s.get("group_id"))
            _dis_lkp_s[_dk_s] = _de_s

        # ------------------------------------------------------------------
        # Step 4: Cross-reference labels → disagreement context
        # ------------------------------------------------------------------
        _pri_labeled_s: Dict[str, int] = {"elevated": 0, "standard": 0, "low": 0}
        _pri_useful_s: Dict[str, int] = {"elevated": 0, "standard": 0, "low": 0}
        _kind_labeled_s: Dict[str, int] = {}
        _kind_useful_s: Dict[str, int] = {}
        _sha_labeled_s: Dict[str, int] = {}
        _sha_noise_s: Dict[str, int] = {}

        for _ev_s in _resolved_s:
            _mpid_s = _ev_s.get("match_pass_id")
            _gid_s = _ev_s.get("group_id")
            _lbl_s = _ev_s.get("label")
            _sha_s = _ev_s.get("input_sha256")

            if _sha_s:
                _sha_labeled_s[_sha_s] = _sha_labeled_s.get(_sha_s, 0) + 1
                if _lbl_s == "noise":
                    _sha_noise_s[_sha_s] = _sha_noise_s.get(_sha_s, 0) + 1

            _de_s = _dis_lkp_s.get((_mpid_s, _gid_s))
            if _de_s is None:
                continue

            _dpri_s = _de_s.get("review_priority")
            _dkinds_s: List[str] = _de_s.get("disagreement_kind") or []

            if _dpri_s in _pri_labeled_s:
                _pri_labeled_s[_dpri_s] += 1
                if _lbl_s == "useful_catch":
                    _pri_useful_s[_dpri_s] += 1

            for _k_s in _dkinds_s:
                _kind_labeled_s[_k_s] = _kind_labeled_s.get(_k_s, 0) + 1
                if _lbl_s == "useful_catch":
                    _kind_useful_s[_k_s] = _kind_useful_s.get(_k_s, 0) + 1

        # ------------------------------------------------------------------
        # Step 5: Build output metrics
        # ------------------------------------------------------------------
        useful_catch_rate_by_priority_s = {
            p: {
                "labeled": _pri_labeled_s.get(p, 0),
                "useful_catch": _pri_useful_s.get(p, 0),
                "rate": _safe_rate(_pri_useful_s.get(p, 0), _pri_labeled_s.get(p, 0)),
            }
            for p in ("elevated", "standard", "low")
        }

        useful_catch_rate_by_kind_s = sorted(
            [
                {
                    "kind": k,
                    "labeled": _kind_labeled_s[k],
                    "useful_catch": _kind_useful_s.get(k, 0),
                    "rate": _safe_rate(_kind_useful_s.get(k, 0), _kind_labeled_s[k]),
                }
                for k in _kind_labeled_s
            ],
            key=lambda x: (-x["labeled"], x["kind"]),
        )

        label_coverage_by_priority_s = {
            p: {
                "total_disagreements": _totals_by_pri_s.get(p, 0),
                "labeled": _pri_labeled_s.get(p, 0),
                "coverage_rate": (
                    _safe_rate(
                        _pri_labeled_s.get(p, 0),
                        _totals_by_pri_s.get(p, 0),
                    )
                    if _totals_by_pri_s.get(p, 0) >= _MIN_SAMPLES
                    else None
                ),
            }
            for p in ("elevated", "standard", "low")
        }

        _sha_rows_s = [
            {
                "input_sha256": sha_v,
                "total_labeled": cnt_v,
                "noise": _sha_noise_s.get(sha_v, 0),
                "noise_rate": _safe_rate(_sha_noise_s.get(sha_v, 0), cnt_v),
            }
            for sha_v, cnt_v in _sha_labeled_s.items()
            if cnt_v >= _MIN_SAMPLES
        ]
        top_sha_by_noise_s = sorted(
            _sha_rows_s,
            key=lambda x: (-(x["noise_rate"] or 0.0), -x["total_labeled"], x["input_sha256"]),
        )[:5]

        return {
            "schema_version": "review-label-summary-1",
            "window": {
                "label_events_read": len(label_rows),
                "shadow_rows_read": len(shadow_rows),
                "resolved_labels": len(_resolved_s),
                "disagreements_in_window": total_disagreements_s,
            },
            "total_review_labels": total_review_labels_s,
            "resolved_label_counts": resolved_label_counts_s,
            "useful_catch_rate_by_review_priority": useful_catch_rate_by_priority_s,
            "useful_catch_rate_by_disagreement_kind": useful_catch_rate_by_kind_s,
            "label_coverage_by_review_priority": label_coverage_by_priority_s,
            "top_input_sha256_by_noise_rate": top_sha_by_noise_s,
            "stability_note": _STABILITY_NOTE,
        }

    except Exception:
        return _empty_skeleton()


@localhost_router.get("/api/observability/review-label-summary")
def get_review_label_summary() -> JSONResponse:
    """Phase 1L — compute-on-read analytics over review-label and shadow-compare streams.

    Schema version: "review-label-summary-1".

    Reads both ``REVIEW_LABELS_PATH`` and ``MATCH_SHADOW_COMPARE_PATH``.
    Computes:
      - resolved_label_counts
      - useful_catch_rate_by_review_priority
      - useful_catch_rate_by_disagreement_kind
      - label_coverage_by_review_priority
      - top_input_sha256_by_noise_rate

    Always returns HTTP 200.  Missing files → empty skeleton.
    No writes.  No state mutations.  No operational side effects.

    WORDING: All metrics are review telemetry patterns only.  No accuracy,
    correctness, confidence, or recommendation language.
    """
    from datetime import timezone as _tz_rls

    _generated_at_rls = datetime.now(_tz_rls.utc).isoformat()

    try:
        _label_rows_rls: List[Dict[str, Any]] = []
        if REVIEW_LABELS_PATH.exists():
            with open(REVIEW_LABELS_PATH, "r", encoding="utf-8") as _fh_rls:
                for _line_rls in _fh_rls:
                    _line_rls = _line_rls.strip()
                    if not _line_rls:
                        continue
                    try:
                        _label_rows_rls.append(json.loads(_line_rls))
                    except json.JSONDecodeError:
                        continue

        _shadow_rows_rls: List[Dict[str, Any]] = []
        if MATCH_SHADOW_COMPARE_PATH.exists():
            with open(MATCH_SHADOW_COMPARE_PATH, "r", encoding="utf-8") as _fh_rls:
                for _line_rls in _fh_rls:
                    _line_rls = _line_rls.strip()
                    if not _line_rls:
                        continue
                    try:
                        _shadow_rows_rls.append(json.loads(_line_rls))
                    except json.JSONDecodeError:
                        continue

        _result_rls = _compute_review_label_summary(_label_rows_rls, _shadow_rows_rls)
        _result_rls["generated_at"] = _generated_at_rls
        return JSONResponse(_result_rls)

    except Exception as _rls_exc:
        print(
            f"[REVIEW_LABEL_SUMMARY] WARNING: failed to compute summary: "
            f"{type(_rls_exc).__name__}: {_rls_exc}",
            flush=True,
        )
        _empty_rls = _compute_review_label_summary([], [])
        _empty_rls["generated_at"] = _generated_at_rls
        return JSONResponse(_empty_rls)


# ---------------------------------------------------------------------------
# Phase 1M — KMZ Engineering Fidelity Audit (compute-on-read, no writes)
# ---------------------------------------------------------------------------

# Semantic feature fields — full set from _build_kmz_semantic.
# Used to compute the "dropped fields" list against reference ingest fields.
_SEMANTIC_FEATURE_FIELD_NAMES: List[str] = sorted([
    "feature_id", "placemark_id", "placemark_name", "description",
    "description_raw", "folder_path", "folder_path_str", "geometry_type",
    "style_url", "extended_data", "coords_hint", "classification",
    "confidence", "classification_reason", "source_filename",
    "chainage_ft", "chainage_source", "sequence_number", "sequence_kind",
    "full_geometry", "multigeometry_children", "style_resolved", "lifecycle",
    "classification_debug",
])

# Reference line-feature fields — from _build_kmz_reference line_features.
_REFERENCE_LINE_FIELD_NAMES: List[str] = sorted([
    "feature_id", "name", "folder_path", "role", "coords",
    "stroke", "stroke_width", "length_ft",
])

_FIDELITY_STABILITY_NOTE: str = (
    "kmz-fidelity-audit-1 describes engineering fidelity gaps between the "
    "semantic ingest and the operational render ingest.  Preservation rates "
    "reflect which fields and semantics are available in semantic parsing but "
    "absent from the render pipeline.  No operational guidance.  Read-only, "
    "additive, diagnostic only."
)


def _compute_kmz_fidelity_audit(
    semantic: Optional[Dict[str, Any]],
    reference: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Phase 1M — compute engineering fidelity gap between semantic and render ingest.

    Pure function.  Never raises.  Compares ``semantic`` (output of
    ``_build_kmz_semantic``) against ``reference`` (output of
    ``_build_kmz_reference``).

    Returns a structured audit dict with six categories:
      style_fidelity, folder_fidelity, extended_data_fidelity,
      geometry_fidelity, render_simplification, window.

    WORDING DISCIPLINE: Uses "fidelity", "preservation", "topology".
    No accuracy, correctness, confidence, or operational guidance language.
    """

    def _safe_rate(numerator: int, denominator: int) -> Optional[float]:
        if denominator <= 0:
            return None
        return round(numerator / denominator, 4)

    def _empty_audit() -> Dict[str, Any]:
        return {
            "schema_version": "kmz-fidelity-audit-1",
            "window": {
                "semantic_feature_count": 0,
                "reference_line_count": 0,
                "reference_polygon_count": 0,
                "reference_point_count": 0,
                "has_semantic_ingest": False,
                "has_reference_ingest": False,
            },
            "style_fidelity": {
                "unique_style_urls_in_semantic": 0,
                "features_with_resolved_style_props": 0,
                "features_with_kml_line_color": 0,
                "features_with_kml_poly_fill": 0,
                "features_with_icon_href": 0,
                "reference_feature_has_style_url": False,
                "style_url_preservation_rate": None,
            },
            "folder_fidelity": {
                "max_folder_depth": 0,
                "avg_folder_depth": None,
                "features_with_multi_level_path": 0,
                "features_with_single_level_path": 0,
                "reference_folder_is_flat_string": True,
                "hierarchy_preservation_rate": None,
            },
            "extended_data_fidelity": {
                "unique_key_count": 0,
                "total_value_count": 0,
                "reference_has_extended_data_field": False,
                "top_keys": [],
                "preservation_rate": None,
            },
            "geometry_fidelity": {
                "multigeometry_placemark_count": 0,
                "multigeometry_child_count": 0,
                "reference_preserves_parent_placemark_identity": False,
                "exploded_into_flat_geometries": True,
            },
            "render_simplification": {
                "semantic_field_count": len(_SEMANTIC_FEATURE_FIELD_NAMES),
                "reference_line_field_count": len(_REFERENCE_LINE_FIELD_NAMES),
                "fields_in_semantic_not_in_reference": [],
                "dropped_field_count": 0,
            },
            "stability_note": _FIDELITY_STABILITY_NOTE,
        }

    try:
        _sem_features: List[Dict[str, Any]] = []
        _sem_index: Dict[str, Any] = {}
        _has_sem = False
        if isinstance(semantic, dict):
            _sem_features = semantic.get("features") or []
            if not isinstance(_sem_features, list):
                _sem_features = []
            _sem_index = semantic.get("index") or {}
            _has_sem = True

        _ref: Dict[str, Any] = reference if isinstance(reference, dict) else {}
        _ref_lines: List[Dict[str, Any]] = _ref.get("line_features") or []
        _ref_polys: List[Dict[str, Any]] = _ref.get("polygon_features") or []
        _ref_points: List[Dict[str, Any]] = _ref.get("point_features") or []
        _has_ref = bool(_ref_lines or _ref_polys or _ref_points)

        # ------------------------------------------------------------------
        # A. Style fidelity
        # ------------------------------------------------------------------
        _unique_style_urls: set = set()
        _resolved_style_count = 0
        _kml_line_color_count = 0
        _kml_poly_fill_count = 0
        _icon_href_count = 0

        for _f_fa in _sem_features:
            if not isinstance(_f_fa, dict):
                continue
            _su = _f_fa.get("style_url")
            if _su and isinstance(_su, str) and _su.strip():
                _unique_style_urls.add(_su.strip())
            _sr = _f_fa.get("style_resolved")
            if isinstance(_sr, dict):
                _resolved_style_count += 1
                if _sr.get("line_color"):
                    _kml_line_color_count += 1
                if _sr.get("poly_fill"):
                    _kml_poly_fill_count += 1
                if _sr.get("icon_href"):
                    _icon_href_count += 1

        _n_style_urls = len(_unique_style_urls)

        # ------------------------------------------------------------------
        # B. Folder hierarchy fidelity
        # ------------------------------------------------------------------
        _folder_depths: List[int] = []
        _multi_level_count = 0
        _single_level_count = 0

        for _f_fa in _sem_features:
            if not isinstance(_f_fa, dict):
                continue
            _fp = _f_fa.get("folder_path")
            if isinstance(_fp, list):
                _depth = len(_fp)
                _folder_depths.append(_depth)
                if _depth > 1:
                    _multi_level_count += 1
                elif _depth == 1:
                    _single_level_count += 1

        _max_depth = max(_folder_depths) if _folder_depths else 0
        _avg_depth: Optional[float] = (
            round(sum(_folder_depths) / len(_folder_depths), 3)
            if _folder_depths
            else None
        )

        # ------------------------------------------------------------------
        # C. ExtendedData fidelity
        # ------------------------------------------------------------------
        _ed_key_counts: Dict[str, int] = {}
        _ed_total_values = 0

        for _f_fa in _sem_features:
            if not isinstance(_f_fa, dict):
                continue
            _ed = _f_fa.get("extended_data")
            if isinstance(_ed, dict):
                for _k in _ed.keys():
                    _ed_key_counts[_k] = _ed_key_counts.get(_k, 0) + 1
                    _ed_total_values += 1

        _top_ed_keys = sorted(
            [{"key": k, "count": v} for k, v in _ed_key_counts.items()],
            key=lambda x: (-x["count"], x["key"]),
        )[:5]

        # ------------------------------------------------------------------
        # D. MultiGeometry fidelity
        # ------------------------------------------------------------------
        _multi_geo_count = 0
        _multi_child_count = 0

        for _f_fa in _sem_features:
            if not isinstance(_f_fa, dict):
                continue
            if _f_fa.get("geometry_type") == "MultiGeometry":
                _multi_geo_count += 1
                _children = _f_fa.get("multigeometry_children")
                if isinstance(_children, list):
                    _multi_child_count += len(_children)

        # ------------------------------------------------------------------
        # E. Render simplification
        # ------------------------------------------------------------------
        _sem_field_set = set(_SEMANTIC_FEATURE_FIELD_NAMES)
        _ref_field_set = set(_REFERENCE_LINE_FIELD_NAMES)
        _dropped = sorted(_sem_field_set - _ref_field_set)

        return {
            "schema_version": "kmz-fidelity-audit-1",
            "window": {
                "semantic_feature_count": len(_sem_features),
                "reference_line_count": len(_ref_lines),
                "reference_polygon_count": len(_ref_polys),
                "reference_point_count": len(_ref_points),
                "has_semantic_ingest": _has_sem,
                "has_reference_ingest": _has_ref,
            },
            "style_fidelity": {
                "unique_style_urls_in_semantic": _n_style_urls,
                "features_with_resolved_style_props": _resolved_style_count,
                "features_with_kml_line_color": _kml_line_color_count,
                "features_with_kml_poly_fill": _kml_poly_fill_count,
                "features_with_icon_href": _icon_href_count,
                "reference_feature_has_style_url": False,
                "style_url_preservation_rate": _safe_rate(0, _n_style_urls),
            },
            "folder_fidelity": {
                "max_folder_depth": _max_depth,
                "avg_folder_depth": _avg_depth,
                "features_with_multi_level_path": _multi_level_count,
                "features_with_single_level_path": _single_level_count,
                "reference_folder_is_flat_string": True,
                "hierarchy_preservation_rate": (
                    _safe_rate(0, _multi_level_count)
                    if _multi_level_count > 0
                    else None
                ),
            },
            "extended_data_fidelity": {
                "unique_key_count": len(_ed_key_counts),
                "total_value_count": _ed_total_values,
                "reference_has_extended_data_field": False,
                "top_keys": _top_ed_keys,
                "preservation_rate": _safe_rate(0, len(_ed_key_counts)),
            },
            "geometry_fidelity": {
                "multigeometry_placemark_count": _multi_geo_count,
                "multigeometry_child_count": _multi_child_count,
                "reference_preserves_parent_placemark_identity": False,
                "exploded_into_flat_geometries": True,
            },
            "render_simplification": {
                "semantic_field_count": len(_SEMANTIC_FEATURE_FIELD_NAMES),
                "reference_line_field_count": len(_REFERENCE_LINE_FIELD_NAMES),
                "fields_in_semantic_not_in_reference": _dropped,
                "dropped_field_count": len(_dropped),
            },
            "stability_note": _FIDELITY_STABILITY_NOTE,
        }

    except Exception:
        return _empty_audit()


@localhost_router.get("/api/observability/kmz-fidelity-audit")
def get_kmz_fidelity_audit() -> JSONResponse:
    """Phase 1M — KMZ engineering fidelity audit (compute-on-read, no writes).

    Schema version: "kmz-fidelity-audit-1".

    Reads STATE["kmz_semantic"] and STATE["kmz_reference"] directly.
    Computes six fidelity categories:
      style_fidelity, folder_fidelity, extended_data_fidelity,
      geometry_fidelity, render_simplification, window.

    Always returns HTTP 200.  Missing STATE entries → empty skeleton.
    No writes.  No state mutations.  No operational side effects.

    WORDING: All metrics describe engineering topology fidelity gaps.
    No accuracy, correctness, confidence, or operational guidance language.
    """
    from datetime import timezone as _tz_fa

    _generated_at_fa = datetime.now(_tz_fa.utc).isoformat()
    try:
        _result_fa = _compute_kmz_fidelity_audit(
            STATE.get("kmz_semantic"),
            STATE.get("kmz_reference"),
        )
        _result_fa["generated_at"] = _generated_at_fa
        return JSONResponse(_result_fa)
    except Exception as _fa_exc:
        print(
            f"[KMZ_FIDELITY_AUDIT] WARNING: failed to compute audit: "
            f"{type(_fa_exc).__name__}: {_fa_exc}",
            flush=True,
        )
        _empty_fa = _compute_kmz_fidelity_audit(None, None)
        _empty_fa["generated_at"] = _generated_at_fa
        return JSONResponse(_empty_fa)


# ---------------------------------------------------------------------------
# Phase 1O — KMZ Topology Sidecar (upload-scoped, read-only, diagnostic)
#
# USAGE POLICY (see TOPOLOGY_SIDECAR_USAGE_POLICY.md for full text):
#   • No operational code path may depend on this sidecar being present.
#   • Renderer, matcher, scorer, redline, billing, closeout: DO NOT read this.
#   • This sidecar is diagnostic lineage data ONLY.
#   • Absence or error must never break any operational path.
# ---------------------------------------------------------------------------

_TOPOLOGY_SIDECAR_STABILITY_NOTE: str = (
    "kmz-topology-sidecar-1 records best-effort topology lineage from the "
    "KMZ semantic ingest to the operational reference ingest.  Joins are by "
    "(placemark_name, folder_path_str) and are not guaranteed unique.  "
    "Read-only, upload-scoped, diagnostic only.  "
    "No renderer, matcher, scorer, redline, billing, or closeout path may "
    "depend on this sidecar.  Absence must never cause operational failure."
)


def _build_kmz_topology_sidecar(
    semantic: Optional[Dict[str, Any]],
    reference: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Phase 1O — build the topology lineage bridge sidecar.

    Pure function.  Never raises.  Joins ``semantic`` (output of
    ``_build_kmz_semantic``) against ``reference`` (output of
    ``_build_kmz_reference``) by ``(placemark_name, folder_path_str)``.

    Returns a structured dict with:
      ``entries``: list of per-reference-feature topology lineage records.

    Each entry carries exactly:
      reference_feature_id, semantic_feature_id, placemark_id,
      folder_path (array), multigeometry_group_id, document_order, style_url.

    Join semantics:
      • Key is ``(name, folder_path)`` from reference matched against
        ``(placemark_name, folder_path_str)`` from semantic.
      • First match wins when duplicates exist.
      • Unmatched reference features get None for all semantic-derived fields.
      • MultiGeometry semantic features give all their matched reference
        fragments the same ``multigeometry_group_id`` (= semantic_feature_id).

    WORDING: Fidelity, topology, lineage.  No accuracy/correctness language.
    """

    def _empty_sidecar() -> Dict[str, Any]:
        return {
            "schema_version": "kmz-topology-sidecar-1",
            "entry_count": 0,
            "entries": [],
            "join_stats": {
                "total_reference_features": 0,
                "matched_count": 0,
                "unmatched_count": 0,
                "multigeometry_group_count": 0,
            },
            "stability_note": _TOPOLOGY_SIDECAR_STABILITY_NOTE,
        }

    try:
        # ------------------------------------------------------------------ #
        # 1. Index semantic features by (placemark_name, folder_path_str).
        #    First-occurrence wins to handle duplicate names safely.
        # ------------------------------------------------------------------ #
        _sem_features: List[Dict[str, Any]] = []
        if isinstance(semantic, dict):
            _raw = semantic.get("features")
            if isinstance(_raw, list):
                _sem_features = _raw

        # Build lookup: (name, folder_str) → (document_order, feature_dict)
        # document_order is 1-based position in semantic.features.
        _sem_index: Dict[tuple, tuple] = {}
        for _doc_pos, _sf in enumerate(_sem_features, start=1):
            if not isinstance(_sf, dict):
                continue
            _name = (_sf.get("placemark_name") or "").strip()
            _fstr = (_sf.get("folder_path_str") or "").strip()
            _key = (_name, _fstr)
            if _key not in _sem_index:
                _sem_index[_key] = (_doc_pos, _sf)

        # ------------------------------------------------------------------ #
        # 2. Iterate all reference features in flat order.
        # ------------------------------------------------------------------ #
        _ref: Dict[str, Any] = reference if isinstance(reference, dict) else {}
        _all_ref: List[Dict[str, Any]] = []
        for _bucket in ("line_features", "polygon_features", "point_features"):
            _bucket_list = _ref.get(_bucket)
            if isinstance(_bucket_list, list):
                for _rf in _bucket_list:
                    if isinstance(_rf, dict):
                        _all_ref.append(_rf)

        # ------------------------------------------------------------------ #
        # 3. Build entries.
        # ------------------------------------------------------------------ #
        _entries: List[Dict[str, Any]] = []
        _matched = 0
        _multi_group_ids: set = set()

        for _rf in _all_ref:
            _ref_id = _rf.get("feature_id") or ""
            _ref_name = (_rf.get("name") or "").strip()
            _ref_fstr = (_rf.get("folder_path") or "").strip()
            _join_key = (_ref_name, _ref_fstr)

            _sem_match: Optional[Dict[str, Any]] = None
            _doc_order: Optional[int] = None

            # Primary join: name + folder_path_str
            _hit = _sem_index.get(_join_key)
            if _hit is None and _ref_fstr:
                # Fallback: name-only join when folder_path_str differs slightly
                _hit = _sem_index.get((_ref_name, ""))
            if _hit is None and _ref_name:
                # Last-resort: scan for name-only match (bounded, first found)
                for (_n, _f), (_d, _s) in _sem_index.items():
                    if _n == _ref_name:
                        _hit = (_d, _s)
                        break

            if _hit is not None:
                _doc_order, _sem_match = _hit
                _matched += 1

            # Extract semantic-derived fields (all None on miss).
            if _sem_match is not None:
                _sem_fid: Optional[str] = _sem_match.get("feature_id")
                _placemark_id: Optional[str] = _sem_match.get("placemark_id")
                _folder_path_arr: Optional[List[str]] = (
                    _sem_match.get("folder_path")
                    if isinstance(_sem_match.get("folder_path"), list)
                    else None
                )
                _style_url: Optional[str] = _sem_match.get("style_url") or None
                _is_multi = _sem_match.get("geometry_type") == "MultiGeometry"
                _multi_gid: Optional[str] = _sem_fid if _is_multi else None
                if _multi_gid:
                    _multi_group_ids.add(_multi_gid)
            else:
                _sem_fid = None
                _placemark_id = None
                _folder_path_arr = None
                _style_url = None
                _multi_gid = None

            _entries.append(
                {
                    "reference_feature_id": _ref_id,
                    "semantic_feature_id": _sem_fid,
                    "placemark_id": _placemark_id,
                    "folder_path": _folder_path_arr,
                    "multigeometry_group_id": _multi_gid,
                    "document_order": _doc_order,
                    "style_url": _style_url,
                }
            )

        _total = len(_entries)
        return {
            "schema_version": "kmz-topology-sidecar-1",
            "entry_count": _total,
            "entries": _entries,
            "join_stats": {
                "total_reference_features": _total,
                "matched_count": _matched,
                "unmatched_count": _total - _matched,
                "multigeometry_group_count": len(_multi_group_ids),
            },
            "stability_note": _TOPOLOGY_SIDECAR_STABILITY_NOTE,
        }

    except Exception:
        return _empty_sidecar()


# ---------------------------------------------------------------------------
# Phase 1P — Redline Topology Continuity Advisor
#
# USAGE POLICY (see TOPOLOGY_SIDECAR_USAGE_POLICY.md for full context):
#   • This advisor is POST-REDLINE only. It reads completed redline_segments.
#   • It NEVER writes to redline_segments, kmz_reference, kmz_semantic,
#     kmz_topology_sidecar, matching state, scoring state, or route activation.
#   • Absence or empty output must never cause operational failure.
#   • Matcher, scorer, route activator, billing, closeout: DO NOT read this.
# ---------------------------------------------------------------------------

_REDLINE_CONTINUITY_STABILITY_NOTE: str = (
    "redline-topology-continuity-1 groups existing redline segments by "
    "shared MultiGeometry engineering object identity recovered from the "
    "KMZ topology sidecar.  Grouping is advisory only.  "
    "Existing redline_segments are completely unchanged.  "
    "No matcher, scorer, route activation, billing, or closeout path may "
    "depend on this structure.  Absence must never cause operational failure."
)

# Hard cap on advisory groups to defend against pathological inputs.
_REDLINE_CONTINUITY_MAX_GROUPS = 500

# ---------------------------------------------------------------------------
# Phase 1Q — Node-anchored redline continuity advisor constants.
# ---------------------------------------------------------------------------
# USAGE POLICY (see TOPOLOGY_SIDECAR_USAGE_POLICY.md for full context):
#   • Advisory only.  Post-redline enrichment.  Never operational.
#   • Matcher, scorer, route activator, billing, closeout: DO NOT read this.
#   • Tolerance is fixed.  Never adaptive.  Never config-driven.
#   • Absence or empty output must never cause operational failure.
# ---------------------------------------------------------------------------

_NODE_CONTINUITY_TOLERANCE_FT: float = 3.0
_NODE_CONTINUITY_MAX_GROUPS: int = 500
# Phase 1S — endpoint validator band constants.  Fixed.  Never adaptive.
# Phase 1T — snap recommendation stability note.
_SNAP_RECOMMENDATION_STABILITY_NOTE: str = (
    "endpoint-snap-recommendation-1 lists candidate anchor coordinates for "
    "redline endpoints classified as 'near' or 'orphan' by the Phase 1S "
    "validator.  Each candidate_coordinate is the exact location of the "
    "nearest KMZ point feature already identified by the validator — no new "
    "geometry is computed.  snap_delta_ft equals current_distance_ft by "
    "construction.  These records are review aids only.  No geometry, "
    "matching, scoring, route activation, billing, or closeout path may "
    "depend on this structure.  Absence must never cause operational failure."
)
_NEAR_ENDPOINT_BAND_FT: float = 10.0
_ENDPOINT_VALIDATION_STABILITY_NOTE: str = (
    "redline-endpoint-validation-1 classifies each redline segment endpoint "
    "by distance to the nearest KMZ point feature (handhole/node).  "
    f"'anchored': distance <= {_NODE_CONTINUITY_TOLERANCE_FT:.1f} ft.  "
    f"'near': {_NODE_CONTINUITY_TOLERANCE_FT:.1f} ft < distance <= {_NEAR_ENDPOINT_BAND_FT:.1f} ft.  "
    "'orphan': distance > "
    f"{_NEAR_ENDPOINT_BAND_FT:.1f} ft.  "
    "'no_anchors_in_kmz': no point features present.  "
    "Classification is advisory only.  No geometry, scoring, matching, route "
    "activation, billing, or closeout path may depend on this structure.  "
    "Absence must never cause operational failure."
)
_NODE_CONTINUITY_STABILITY_NOTE: str = (
    "redline-node-continuity-1 groups existing redline segments by "
    "engineering anchor coincidence: endpoints within "
    f"{_NODE_CONTINUITY_TOLERANCE_FT:.1f} ft of a KMZ point feature "
    "(handhole/node) are placed in that anchor's advisory group.  "
    "Grouping is advisory only.  Tolerance is fixed and non-adaptive.  "
    "No redline_segments, routes, scores, or operational outputs are "
    "modified.  No matcher, scorer, route activator, billing, or closeout "
    "path may depend on this structure.  Absence must never cause failure."
)


def _build_redline_topology_continuity(
    redline_segments: Optional[List[Dict[str, Any]]],
    topology_sidecar: Optional[Dict[str, Any]],
    route_catalog: Optional[List[Dict[str, Any]]],
    reference: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Phase 1P — build the redline topology continuity advisory structure.

    Pure function.  Never raises.  Reads from its arguments only; writes
    nothing.

    JOIN CHAIN (all best-effort, first-match-wins on duplicates):
      redline_segment.matched_route_id
        → route_catalog[route_id].route_name + source_folder
        → kmz_reference.line_features[name + folder_path].feature_id
        → topology_sidecar.entries[reference_feature_id].multigeometry_group_id

    Segments that share a non-None multigeometry_group_id are placed in the
    same advisory group.  All unmatched or ungroupable segments are listed in
    ``ungrouped_segment_ids``.

    SIGNAL: multigeometry_group ONLY.  No folder lineage, style, order, or
    classification inference.

    OUTPUT GUARDRAILS:
      • redline_segments is NEVER mutated.
      • Groups are sorted deterministically by engineering_object_id.
      • segment_ids within groups are sorted deterministically.
      • Groups are capped at _REDLINE_CONTINUITY_MAX_GROUPS.
    """

    def _empty_result(all_ids: List[str]) -> Dict[str, Any]:
        return {
            "schema_version": "redline-topology-continuity-1",
            "groups": [],
            "ungrouped_segment_ids": sorted(all_ids),
            "stability_note": _REDLINE_CONTINUITY_STABILITY_NOTE,
        }

    try:
        _segs: List[Dict[str, Any]] = []
        if isinstance(redline_segments, list):
            for _s in redline_segments:
                if isinstance(_s, dict):
                    _segs.append(_s)

        _all_seg_ids = [
            str(_s.get("segment_id") or "")
            for _s in _segs
            if (_s.get("segment_id") or "")
        ]

        if not _segs:
            return _empty_result([])

        # ------------------------------------------------------------------ #
        # 1. Build ref_feature_id → multigeometry_group_id from sidecar.
        # ------------------------------------------------------------------ #
        _ref_id_to_group: Dict[str, str] = {}
        if isinstance(topology_sidecar, dict):
            _entries = topology_sidecar.get("entries") or []
            if isinstance(_entries, list):
                for _entry in _entries:
                    if not isinstance(_entry, dict):
                        continue
                    _gid = _entry.get("multigeometry_group_id")
                    _rid = _entry.get("reference_feature_id")
                    if _gid and _rid:
                        _ref_id_to_group[str(_rid)] = str(_gid)

        if not _ref_id_to_group:
            return _empty_result(_all_seg_ids)

        # ------------------------------------------------------------------ #
        # 2. Build (name, folder_str) → reference_feature_id from line_features.
        # ------------------------------------------------------------------ #
        _name_folder_to_ref_id: Dict[tuple, str] = {}
        if isinstance(reference, dict):
            _line_feats = reference.get("line_features") or []
            if isinstance(_line_feats, list):
                for _lf in _line_feats:
                    if not isinstance(_lf, dict):
                        continue
                    _lname = (_lf.get("name") or "").strip()
                    _lfolder = (_lf.get("folder_path") or "").strip()
                    _lfid = _lf.get("feature_id") or ""
                    if _lfid:
                        _key = (_lname, _lfolder)
                        if _key not in _name_folder_to_ref_id:
                            _name_folder_to_ref_id[_key] = str(_lfid)

        # ------------------------------------------------------------------ #
        # 3. Build route_id → multigeometry_group_id via route_catalog join.
        # ------------------------------------------------------------------ #
        _route_id_to_group: Dict[str, str] = {}
        if isinstance(route_catalog, list):
            for _route in route_catalog:
                if not isinstance(_route, dict):
                    continue
                _rid = _route.get("route_id") or ""
                if not _rid:
                    continue
                _rname = (_route.get("route_name") or _route.get("name") or "").strip()
                _rfolder = (_route.get("source_folder") or "").strip()
                # Primary join: (name, folder_str)
                _ref_fid = _name_folder_to_ref_id.get((_rname, _rfolder))
                if _ref_fid is None and _rfolder:
                    # Fallback: name-only
                    _ref_fid = _name_folder_to_ref_id.get((_rname, ""))
                if _ref_fid is None and _rname:
                    # Last-resort: scan for name-only
                    for (_n, _f), _fid in _name_folder_to_ref_id.items():
                        if _n == _rname:
                            _ref_fid = _fid
                            break
                if _ref_fid:
                    _grp = _ref_id_to_group.get(_ref_fid)
                    if _grp:
                        _route_id_to_group[str(_rid)] = _grp

        # ------------------------------------------------------------------ #
        # 4. Group segments by multigeometry_group_id.
        # ------------------------------------------------------------------ #
        _group_to_seg_ids: Dict[str, List[str]] = {}
        _ungrouped: List[str] = []

        for _seg in _segs:
            _seg_id = str(_seg.get("segment_id") or "")
            if not _seg_id:
                continue
            _route_id = str(_seg.get("matched_route_id") or _seg.get("route_id") or "")
            _grp = _route_id_to_group.get(_route_id) if _route_id else None
            if _grp:
                _group_to_seg_ids.setdefault(_grp, []).append(_seg_id)
            else:
                _ungrouped.append(_seg_id)

        # ------------------------------------------------------------------ #
        # 5. Build output groups (only groups with ≥ 2 members are meaningful
        #    continuity groups; include single-member groups for completeness).
        # ------------------------------------------------------------------ #
        _groups: List[Dict[str, Any]] = []
        for _gid in sorted(_group_to_seg_ids.keys()):
            _member_ids = sorted(_group_to_seg_ids[_gid])
            _groups.append(
                {
                    "engineering_object_id": _gid,
                    "signal": "multigeometry_group",
                    "source_segment_ids": _member_ids,
                    "evidence": {
                        "shared_group_id": _gid,
                        "fragment_count": len(_member_ids),
                    },
                }
            )
            if len(_groups) >= _REDLINE_CONTINUITY_MAX_GROUPS:
                break

        return {
            "schema_version": "redline-topology-continuity-1",
            "groups": _groups,
            "ungrouped_segment_ids": sorted(_ungrouped),
            "stability_note": _REDLINE_CONTINUITY_STABILITY_NOTE,
        }

    except Exception:
        _fallback_ids = []
        try:
            if isinstance(redline_segments, list):
                for _s in redline_segments:
                    if isinstance(_s, dict):
                        _sid = str(_s.get("segment_id") or "")
                        if _sid:
                            _fallback_ids.append(_sid)
        except Exception:
            pass
        return _empty_result(_fallback_ids)


@localhost_router.get("/api/observability/redline-topology-continuity")
def get_redline_topology_continuity() -> JSONResponse:
    """Phase 1P — redline topology continuity advisor (read-only, post-redline).

    Schema version: "redline-topology-continuity-1".

    Returns STATE["redline_topology_continuity"] directly if populated, or
    computes it on-the-fly from current STATE when the stored value is None.

    Always returns HTTP 200.  No writes.  No state mutations.
    No operational side effects.

    USAGE POLICY: See TOPOLOGY_SIDECAR_USAGE_POLICY.md.
    No operational consumer (matcher, scorer, route activator, billing,
    closeout) may depend on this endpoint being non-empty.
    """
    from datetime import timezone as _tz_rtc

    _generated_at_rtc = datetime.now(_tz_rtc.utc).isoformat()
    try:
        _stored = STATE.get("redline_topology_continuity")
        if isinstance(_stored, dict):
            _result = dict(_stored)
        else:
            # Compute on-the-fly when not yet built (no bore logs uploaded yet).
            _result = _build_redline_topology_continuity(
                STATE.get("redline_segments"),
                STATE.get("kmz_topology_sidecar"),
                STATE.get("route_catalog"),
                STATE.get("kmz_reference"),
            )
        _result["generated_at"] = _generated_at_rtc
        return JSONResponse(_result)
    except Exception as _rtc_exc:
        print(
            f"[REDLINE_TOPOLOGY_CONTINUITY] WARNING: failed to serve advisor: "
            f"{type(_rtc_exc).__name__}: {_rtc_exc}",
            flush=True,
        )
        _empty = _build_redline_topology_continuity(None, None, None, None)
        _empty["generated_at"] = _generated_at_rtc
        return JSONResponse(_empty)


# ---------------------------------------------------------------------------
# Phase 1Q — Node-anchored redline continuity advisor
# ---------------------------------------------------------------------------


def _build_redline_node_continuity(
    redline_segments: Optional[List[Dict[str, Any]]],
    reference: Optional[Dict[str, Any]],
    route_catalog: Optional[List[Dict[str, Any]]],
) -> Dict[str, Any]:
    """Phase 1Q — build the node-anchored redline continuity advisory structure.

    Pure function.  Never raises.  Reads from its arguments only; writes
    nothing.

    ALGORITHM:
      For each redline segment:
        1. Resolve its route from route_catalog to get endpoint coordinates.
        2. Test both endpoints (start = coords[0], end = coords[-1]) against
           every point feature in kmz_reference.
        3. If distance <= _NODE_CONTINUITY_TOLERANCE_FT, assign the
           segment+endpoint to that anchor's advisory group.
      A segment is ``ungrouped`` only if NEITHER endpoint falls within
      tolerance of any anchor.  A segment may appear in more than one group
      (start → anchor A, end → anchor B).

    SIGNAL: endpoint-to-anchor coincidence ONLY.
      No folder lineage.  No style inference.  No transitive chaining.
      No nearest-neighbour fallback.

    OUTPUT GUARDRAILS:
      • redline_segments is NEVER mutated.
      • Groups are emitted only for anchors that have ≥ 1 endpoint.
      • Groups are sorted deterministically by anchor_reference_feature_id.
      • source_segment_ids within groups are sorted deterministically.
      • Groups are capped at _NODE_CONTINUITY_MAX_GROUPS.
    """

    def _empty_result(all_ids: List[str]) -> Dict[str, Any]:
        return {
            "schema_version": "redline-node-continuity-1",
            "tolerance_ft": _NODE_CONTINUITY_TOLERANCE_FT,
            "groups": [],
            "ungrouped_segment_ids": sorted(all_ids),
            "stats": {
                "anchor_points_considered": 0,
                "anchor_points_with_groups": 0,
                "redline_segments_total": len(all_ids),
                "redline_segments_anchored": 0,
                "redline_segments_unanchored": len(all_ids),
            },
            "stability_note": _NODE_CONTINUITY_STABILITY_NOTE,
        }

    try:
        # ------------------------------------------------------------------ #
        # 0. Coerce + validate inputs.
        # ------------------------------------------------------------------ #
        _segs: List[Dict[str, Any]] = []
        if isinstance(redline_segments, list):
            for _s in redline_segments:
                if isinstance(_s, dict):
                    _segs.append(_s)

        _all_seg_ids = [
            str(_s.get("segment_id") or "")
            for _s in _segs
            if (_s.get("segment_id") or "")
        ]

        if not _segs:
            return _empty_result([])

        # ------------------------------------------------------------------ #
        # 1. Build anchor index: point_feature_id → anchor dict.
        # ------------------------------------------------------------------ #
        _anchors: List[Dict[str, Any]] = []
        if isinstance(reference, dict):
            _pt_feats = reference.get("point_features") or []
            if isinstance(_pt_feats, list):
                for _pf in _pt_feats:
                    if not isinstance(_pf, dict):
                        continue
                    _lat = _pf.get("lat")
                    _lon = _pf.get("lon")
                    _fid = _pf.get("feature_id") or ""
                    if _fid and isinstance(_lat, (int, float)) and isinstance(_lon, (int, float)):
                        _anchors.append(
                            {
                                "feature_id": str(_fid),
                                "name": (_pf.get("name") or "").strip() or "Unnamed Feature",
                                "folder_path": _pf.get("folder_path"),
                                "lat": float(_lat),
                                "lon": float(_lon),
                            }
                        )

        _anchor_count = len(_anchors)
        if not _anchors:
            return _empty_result(_all_seg_ids)

        # ------------------------------------------------------------------ #
        # 2. Build route_id → route dict (coords + name).
        # ------------------------------------------------------------------ #
        _route_by_id: Dict[str, Dict[str, Any]] = {}
        if isinstance(route_catalog, list):
            for _rc in route_catalog:
                if not isinstance(_rc, dict):
                    continue
                _rid = _rc.get("route_id") or ""
                if _rid:
                    _route_by_id[str(_rid)] = _rc

        # ------------------------------------------------------------------ #
        # 3. For each segment resolve endpoints and test against anchors.
        #    anchor_id → {seg_id → list[(endpoint_label, distance_ft)]}
        # ------------------------------------------------------------------ #
        # anchor_id → {seg_id: [(endpoint_label, distance_ft), ...]}
        _anchor_hits: Dict[str, Dict[str, List[tuple]]] = {}
        # seg_id → route_id (for engineering_object_ids in output)
        _seg_route_id: Dict[str, str] = {}
        # set of seg_ids that have at least one anchor match
        _anchored_seg_ids: set = set()

        for _seg in _segs:
            _seg_id = str(_seg.get("segment_id") or "")
            if not _seg_id:
                continue
            _route_id = str(
                _seg.get("matched_route_id") or _seg.get("route_id") or ""
            )
            _seg_route_id[_seg_id] = _route_id

            _route = _route_by_id.get(_route_id) if _route_id else None
            if not _route:
                continue

            _coords = _route.get("coords") or []
            if not isinstance(_coords, list) or len(_coords) < 1:
                continue

            # Extract start and end endpoints; guard against degenerate routes.
            _endpoints: List[tuple] = []
            _c0 = _coords[0]
            if isinstance(_c0, (list, tuple)) and len(_c0) >= 2:
                _endpoints.append(("start", float(_c0[0]), float(_c0[1])))
            _c1 = _coords[-1]
            if isinstance(_c1, (list, tuple)) and len(_c1) >= 2:
                # Only add end if it is distinct from start (non-trivial route).
                if len(_coords) > 1:
                    _endpoints.append(("end", float(_c1[0]), float(_c1[1])))

            for _ep_label, _ep_lat, _ep_lon in _endpoints:
                for _anc in _anchors:
                    try:
                        _d = _haversine_feet(
                            _ep_lat, _ep_lon, _anc["lat"], _anc["lon"]
                        )
                    except Exception:
                        continue
                    if _d <= _NODE_CONTINUITY_TOLERANCE_FT:
                        _aid = _anc["feature_id"]
                        if _aid not in _anchor_hits:
                            _anchor_hits[_aid] = {}
                        _anchor_hits[_aid].setdefault(_seg_id, []).append(
                            (_ep_label, round(_d, 3))
                        )
                        _anchored_seg_ids.add(_seg_id)

        # ------------------------------------------------------------------ #
        # 4. Build ungrouped list.
        # ------------------------------------------------------------------ #
        _ungrouped = sorted(
            sid for sid in _all_seg_ids if sid not in _anchored_seg_ids
        )

        # ------------------------------------------------------------------ #
        # 5. Build output groups.
        #
        # Sort key: (-segment_count, anchor_id) so that the cap only drops
        # single-segment groups when multi-segment groups fit within the cap.
        # Without this, lexicographic sort on anchor_id causes IDs like
        # "point_59" to sort AFTER "point_499", silently dropping multi-
        # segment groups (4-9 cables converging at a handhole) while
        # preserving single-segment entries that are less useful as
        # continuity evidence.  Determinism is preserved within each tier.
        # ------------------------------------------------------------------ #
        _groups: List[Dict[str, Any]] = []
        _sorted_anchor_ids = sorted(
            _anchor_hits.keys(),
            key=lambda _k: (-len(_anchor_hits[_k]), _k),
        )
        for _aid in _sorted_anchor_ids:
            _seg_map = _anchor_hits[_aid]
            if not _seg_map:
                continue

            # Find anchor metadata.
            _anc_meta = next(
                (a for a in _anchors if a["feature_id"] == _aid), None
            )
            if not _anc_meta:
                continue

            _src_seg_ids = sorted(_seg_map.keys())
            _eng_obj_ids = sorted(
                {_seg_route_id.get(sid, "") for sid in _src_seg_ids} - {""}
            )
            _evidence = []
            for _sid in _src_seg_ids:
                for _ep_label, _dist in _seg_map[_sid]:
                    _evidence.append(
                        {
                            "segment_id": _sid,
                            "endpoint": _ep_label,
                            "distance_ft": _dist,
                        }
                    )
            # Sort evidence deterministically.
            _evidence.sort(key=lambda x: (x["segment_id"], x["endpoint"]))

            _groups.append(
                {
                    "anchor_reference_feature_id": _aid,
                    "anchor_folder_path": _anc_meta.get("folder_path"),
                    "anchor_name": _anc_meta["name"],
                    "anchor_coordinate": [
                        _anc_meta["lon"],
                        _anc_meta["lat"],
                    ],
                    "source_segment_ids": _src_seg_ids,
                    "engineering_object_ids": _eng_obj_ids,
                    "endpoint_count": len(_evidence),
                    "evidence": _evidence,
                }
            )
            if len(_groups) >= _NODE_CONTINUITY_MAX_GROUPS:
                break

        _anchored_total = len(_anchored_seg_ids)
        return {
            "schema_version": "redline-node-continuity-1",
            "tolerance_ft": _NODE_CONTINUITY_TOLERANCE_FT,
            "groups": _groups,
            "ungrouped_segment_ids": _ungrouped,
            "stats": {
                "anchor_points_considered": _anchor_count,
                "anchor_points_with_groups": len(_groups),
                "redline_segments_total": len(_all_seg_ids),
                "redline_segments_anchored": _anchored_total,
                "redline_segments_unanchored": len(_all_seg_ids) - _anchored_total,
            },
            "stability_note": _NODE_CONTINUITY_STABILITY_NOTE,
        }

    except Exception:
        _fallback_ids: List[str] = []
        try:
            if isinstance(redline_segments, list):
                for _s in redline_segments:
                    if isinstance(_s, dict):
                        _sid = str(_s.get("segment_id") or "")
                        if _sid:
                            _fallback_ids.append(_sid)
        except Exception:
            pass
        return _empty_result(_fallback_ids)


@localhost_router.get("/api/observability/redline-node-continuity")
def get_redline_node_continuity() -> JSONResponse:
    """Phase 1Q — node-anchored redline continuity advisor (read-only, post-redline).

    Schema version: "redline-node-continuity-1".

    Returns STATE["redline_node_continuity"] directly if populated, or
    computes it on-the-fly from current STATE when the stored value is None.

    Groups redline segments whose endpoints fall within
    _NODE_CONTINUITY_TOLERANCE_FT of a KMZ point feature (handhole/node).

    Always returns HTTP 200.  No writes.  No state mutations.
    No operational side effects.

    USAGE POLICY: See TOPOLOGY_SIDECAR_USAGE_POLICY.md.
    No operational consumer (matcher, scorer, route activator, billing,
    closeout) may depend on this endpoint being non-empty.
    """
    from datetime import timezone as _tz_rnc

    _generated_at_rnc = datetime.now(_tz_rnc.utc).isoformat()
    try:
        _stored = STATE.get("redline_node_continuity")
        if isinstance(_stored, dict):
            _result = dict(_stored)
        else:
            _result = _build_redline_node_continuity(
                STATE.get("redline_segments"),
                STATE.get("kmz_reference"),
                STATE.get("route_catalog"),
            )
        _result["generated_at"] = _generated_at_rnc
        return JSONResponse(_result)
    except Exception as _rnc_exc:
        print(
            f"[REDLINE_NODE_CONTINUITY] WARNING: failed to serve advisor: "
            f"{type(_rnc_exc).__name__}: {_rnc_exc}",
            flush=True,
        )
        _empty = _build_redline_node_continuity(None, None, None)
        _empty["generated_at"] = _generated_at_rnc
        return JSONResponse(_empty)


# ---------------------------------------------------------------------------
# Phase 1S — Bore-log Redline Endpoint Validator
# ---------------------------------------------------------------------------


def _build_redline_endpoint_validation(
    redline_segments: Optional[List[Dict[str, Any]]],
    reference: Optional[Dict[str, Any]],
    route_catalog: Optional[List[Dict[str, Any]]],
) -> Dict[str, Any]:
    """Phase 1S — bore-log redline endpoint validator.

    Pure function.  Never raises.  Reads from its arguments only; writes
    nothing.

    For every redline segment endpoint (start = coords[0], end = coords[-1]),
    finds the nearest KMZ point feature anchor and classifies:
      - anchored          : distance <= _NODE_CONTINUITY_TOLERANCE_FT (3.0 ft)
      - near              : _NODE_CONTINUITY_TOLERANCE_FT < distance <= _NEAR_ENDPOINT_BAND_FT (10.0 ft)
      - orphan            : distance > _NEAR_ENDPOINT_BAND_FT
      - no_anchors_in_kmz : no point features present in kmz_reference

    OUTPUT GUARDRAILS:
      • redline_segments is NEVER mutated.
      • Geometry is NEVER modified.
      • Scores, routes, and all operational STATE are untouched.
      • No sorting or cap — every endpoint is recorded.
    """

    def _empty_result() -> Dict[str, Any]:
        return {
            "schema_version": "redline-endpoint-validation-1",
            "tolerance_ft": _NODE_CONTINUITY_TOLERANCE_FT,
            "near_band_ft": _NEAR_ENDPOINT_BAND_FT,
            "endpoints": [],
            "summary": {
                "total_endpoints": 0,
                "anchored_count": 0,
                "near_count": 0,
                "orphan_count": 0,
                "no_anchors_in_kmz_count": 0,
                "anchored_pct": None,
                "by_route": {},
                "flagged_segments": [],
            },
            "stability_note": _ENDPOINT_VALIDATION_STABILITY_NOTE,
        }

    try:
        # ------------------------------------------------------------------ #
        # 0. Coerce inputs.
        # ------------------------------------------------------------------ #
        _segs: List[Dict[str, Any]] = []
        if isinstance(redline_segments, list):
            for _s in redline_segments:
                if isinstance(_s, dict):
                    _segs.append(_s)

        if not _segs:
            return _empty_result()

        # ------------------------------------------------------------------ #
        # 1. Build anchor list and "no anchors" sentinel.
        # ------------------------------------------------------------------ #
        _anchors: List[Dict[str, Any]] = []
        if isinstance(reference, dict):
            _pt_feats = reference.get("point_features") or []
            if isinstance(_pt_feats, list):
                for _pf in _pt_feats:
                    if not isinstance(_pf, dict):
                        continue
                    _lat = _pf.get("lat")
                    _lon = _pf.get("lon")
                    _fid = _pf.get("feature_id") or ""
                    if (
                        _fid
                        and isinstance(_lat, (int, float))
                        and isinstance(_lon, (int, float))
                    ):
                        _anchors.append(
                            {
                                "feature_id": str(_fid),
                                "name": (
                                    (_pf.get("name") or "").strip()
                                    or "Unnamed Feature"
                                ),
                                "lat": float(_lat),
                                "lon": float(_lon),
                            }
                        )

        _no_anchors = len(_anchors) == 0

        # ------------------------------------------------------------------ #
        # 2. Build route_id → route dict for coordinate resolution.
        # ------------------------------------------------------------------ #
        _route_by_id: Dict[str, Dict[str, Any]] = {}
        if isinstance(route_catalog, list):
            for _rc in route_catalog:
                if not isinstance(_rc, dict):
                    continue
                _rid = _rc.get("route_id") or ""
                if _rid:
                    _route_by_id[str(_rid)] = _rc

        # ------------------------------------------------------------------ #
        # 3. Process each segment, classify each endpoint.
        # ------------------------------------------------------------------ #
        _endpoint_records: List[Dict[str, Any]] = []
        _by_route: Dict[str, Dict[str, int]] = {}
        _flagged: set = set()

        for _seg in _segs:
            _seg_id = str(_seg.get("segment_id") or "")
            if not _seg_id:
                continue
            _route_id = str(
                _seg.get("matched_route_id") or _seg.get("route_id") or ""
            )
            _route = _route_by_id.get(_route_id) if _route_id else None

            _coords = _route.get("coords") or [] if _route else []
            if not isinstance(_coords, list) or len(_coords) < 1:
                continue

            # Build endpoint list: start (always), end (only if route > 1 pt).
            _ep_defs: List[tuple] = []
            _c0 = _coords[0]
            if isinstance(_c0, (list, tuple)) and len(_c0) >= 2:
                _ep_defs.append(("start", float(_c0[0]), float(_c0[1])))
            if len(_coords) > 1:
                _c1 = _coords[-1]
                if isinstance(_c1, (list, tuple)) and len(_c1) >= 2:
                    _ep_defs.append(("end", float(_c1[0]), float(_c1[1])))

            for _ep_label, _ep_lat, _ep_lon in _ep_defs:
                if _no_anchors:
                    _cls = "no_anchors_in_kmz"
                    _nearest_id: Optional[str] = None
                    _nearest_name: Optional[str] = None
                    _dist_ft: Optional[float] = None
                else:
                    _best_d: Optional[float] = None
                    _best_anc: Optional[Dict[str, Any]] = None
                    for _anc in _anchors:
                        try:
                            _d = _haversine_feet(
                                _ep_lat, _ep_lon,
                                _anc["lat"], _anc["lon"],
                            )
                        except Exception:
                            continue
                        if _best_d is None or _d < _best_d:
                            _best_d = _d
                            _best_anc = _anc

                    if _best_d is None:
                        _cls = "no_anchors_in_kmz"
                        _nearest_id = None
                        _nearest_name = None
                        _dist_ft = None
                    elif _best_d <= _NODE_CONTINUITY_TOLERANCE_FT:
                        _cls = "anchored"
                        _nearest_id = _best_anc["feature_id"]  # type: ignore[index]
                        _nearest_name = _best_anc["name"]  # type: ignore[index]
                        _dist_ft = round(_best_d, 3)
                    elif _best_d <= _NEAR_ENDPOINT_BAND_FT:
                        _cls = "near"
                        _nearest_id = _best_anc["feature_id"]  # type: ignore[index]
                        _nearest_name = _best_anc["name"]  # type: ignore[index]
                        _dist_ft = round(_best_d, 3)
                    else:
                        _cls = "orphan"
                        _nearest_id = _best_anc["feature_id"]  # type: ignore[index]
                        _nearest_name = _best_anc["name"]  # type: ignore[index]
                        _dist_ft = round(_best_d, 3)

                _endpoint_records.append(
                    {
                        "segment_id": _seg_id,
                        "route_id": _route_id or None,
                        "endpoint": _ep_label,
                        "coordinate": [_ep_lon, _ep_lat],
                        "nearest_anchor_id": _nearest_id,
                        "nearest_anchor_name": _nearest_name,
                        "distance_ft": _dist_ft,
                        "classification": _cls,
                    }
                )

                # Accumulate by_route.
                if _route_id:
                    if _route_id not in _by_route:
                        _by_route[_route_id] = {
                            "anchored": 0, "near": 0, "orphan": 0,
                            "no_anchors_in_kmz": 0,
                        }
                    _by_route[_route_id][_cls] = _by_route[_route_id].get(_cls, 0) + 1

                # Flag segments with any non-anchored endpoint.
                if _cls != "anchored":
                    _flagged.add(_seg_id)

        # ------------------------------------------------------------------ #
        # 4. Build summary.
        # ------------------------------------------------------------------ #
        _total = len(_endpoint_records)
        _anchored_n = sum(1 for r in _endpoint_records if r["classification"] == "anchored")
        _near_n = sum(1 for r in _endpoint_records if r["classification"] == "near")
        _orphan_n = sum(1 for r in _endpoint_records if r["classification"] == "orphan")
        _no_anc_n = sum(1 for r in _endpoint_records if r["classification"] == "no_anchors_in_kmz")
        _anchored_pct = round(_anchored_n / _total, 4) if _total > 0 else None

        return {
            "schema_version": "redline-endpoint-validation-1",
            "tolerance_ft": _NODE_CONTINUITY_TOLERANCE_FT,
            "near_band_ft": _NEAR_ENDPOINT_BAND_FT,
            "endpoints": _endpoint_records,
            "summary": {
                "total_endpoints": _total,
                "anchored_count": _anchored_n,
                "near_count": _near_n,
                "orphan_count": _orphan_n,
                "no_anchors_in_kmz_count": _no_anc_n,
                "anchored_pct": _anchored_pct,
                "by_route": _by_route,
                "flagged_segments": sorted(_flagged),
            },
            "stability_note": _ENDPOINT_VALIDATION_STABILITY_NOTE,
        }

    except Exception:
        return _empty_result()


@localhost_router.get("/api/observability/redline-endpoint-validation")
def get_redline_endpoint_validation() -> JSONResponse:
    """Phase 1S — bore-log redline endpoint validator (read-only, post-redline).

    Schema version: "redline-endpoint-validation-1".

    Classifies each redline segment endpoint (start/end) as:
    anchored / near / orphan / no_anchors_in_kmz based on haversine distance
    to the nearest KMZ point feature.

    Returns STATE["redline_endpoint_validation"] directly if populated, or
    computes on-the-fly from current STATE.

    Always returns HTTP 200.  No writes.  No state mutations.
    No operational side effects.

    USAGE POLICY: See TOPOLOGY_SIDECAR_USAGE_POLICY.md.
    No operational consumer (matcher, scorer, route activator, geometry,
    billing, closeout) may depend on this endpoint being non-empty.
    """
    from datetime import timezone as _tz_rev

    _generated_at_rev = datetime.now(_tz_rev.utc).isoformat()
    try:
        _stored = STATE.get("redline_endpoint_validation")
        if isinstance(_stored, dict):
            _result = dict(_stored)
        else:
            _result = _build_redline_endpoint_validation(
                STATE.get("redline_segments"),
                STATE.get("kmz_reference"),
                STATE.get("route_catalog"),
            )
        _result["generated_at"] = _generated_at_rev
        return JSONResponse(_result)
    except Exception as _rev_exc:
        print(
            f"[REDLINE_ENDPOINT_VALIDATION] WARNING: failed to serve validator: "
            f"{type(_rev_exc).__name__}: {_rev_exc}",
            flush=True,
        )
        _empty = _build_redline_endpoint_validation(None, None, None)
        _empty["generated_at"] = _generated_at_rev
        return JSONResponse(_empty)


# ---------------------------------------------------------------------------
# Phase 1T — Deterministic Endpoint Snap Recommendations
# ---------------------------------------------------------------------------


def _build_endpoint_snap_recommendations(
    endpoint_validation: Optional[Dict[str, Any]],
    reference: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Phase 1T — deterministic endpoint snap recommendations.

    Pure function.  Never raises.  Reads from its arguments only; writes
    nothing.

    Consumes the already-computed Phase 1S ``endpoint_validation`` result
    and the ``kmz_reference`` anchor list.  Produces one recommendation for
    every endpoint classified as ``near`` or ``orphan``.  Anchored and
    ``no_anchors_in_kmz`` endpoints produce **no** recommendation.

    ``candidate_coordinate`` is the exact ``[lon, lat]`` of the nearest
    anchor already identified by the Phase 1S validator — no new geometric
    computation is performed.  ``snap_delta_ft`` equals
    ``current_distance_ft`` by construction.

    OUTPUT GUARDRAILS:
      • redline_segments is NEVER read or mutated.
      • No geometry is computed or modified.
      • Matching, scoring, routing, billing, closeout are untouched.
      • No persistence.  No JSONL.
    """

    def _empty_result() -> Dict[str, Any]:
        return {
            "schema_version": "endpoint-snap-recommendation-1",
            "tolerance_ft": _NODE_CONTINUITY_TOLERANCE_FT,
            "near_band_ft": _NEAR_ENDPOINT_BAND_FT,
            "recommendations": [],
            "summary": {
                "total_recommendations": 0,
                "near_recommendations": 0,
                "orphan_recommendations": 0,
            },
            "stability_note": _SNAP_RECOMMENDATION_STABILITY_NOTE,
        }

    try:
        # ------------------------------------------------------------------ #
        # 0. Guard: need a valid validation result with endpoints.
        # ------------------------------------------------------------------ #
        if not isinstance(endpoint_validation, dict):
            return _empty_result()
        _ep_records = endpoint_validation.get("endpoints")
        if not isinstance(_ep_records, list) or not _ep_records:
            return _empty_result()

        # ------------------------------------------------------------------ #
        # 1. Build anchor lookup: feature_id → {lat, lon, name}.
        # ------------------------------------------------------------------ #
        _anchor_by_id: Dict[str, Dict[str, Any]] = {}
        if isinstance(reference, dict):
            _pt_feats = reference.get("point_features") or []
            if isinstance(_pt_feats, list):
                for _pf in _pt_feats:
                    if not isinstance(_pf, dict):
                        continue
                    _fid = _pf.get("feature_id") or ""
                    _lat = _pf.get("lat")
                    _lon = _pf.get("lon")
                    if (
                        _fid
                        and isinstance(_lat, (int, float))
                        and isinstance(_lon, (int, float))
                    ):
                        _anchor_by_id[str(_fid)] = {
                            "lat": float(_lat),
                            "lon": float(_lon),
                            "name": (
                                (_pf.get("name") or "").strip()
                                or "Unnamed Feature"
                            ),
                        }

        # ------------------------------------------------------------------ #
        # 2. Build recommendations for near/orphan endpoints only.
        # ------------------------------------------------------------------ #
        _recommendations: List[Dict[str, Any]] = []
        _near_n = 0
        _orphan_n = 0

        for _ep in _ep_records:
            if not isinstance(_ep, dict):
                continue
            _cls = _ep.get("classification") or ""
            if _cls not in ("near", "orphan"):
                continue  # anchored and no_anchors_in_kmz → no recommendation

            _seg_id = str(_ep.get("segment_id") or "")
            if not _seg_id:
                continue

            _anc_id = _ep.get("nearest_anchor_id") or ""
            if not _anc_id:
                continue  # no anchor identified → cannot produce a candidate

            _dist = _ep.get("distance_ft")
            if not isinstance(_dist, (int, float)):
                continue

            _anc = _anchor_by_id.get(str(_anc_id))
            if _anc is None:
                # Anchor not resolvable from reference; skip rather than guess.
                continue

            _recommendations.append(
                {
                    "segment_id": _seg_id,
                    "route_id": _ep.get("route_id"),
                    "endpoint": _ep.get("endpoint") or "",
                    "current_coordinate": _ep.get("coordinate") or [None, None],
                    "current_distance_ft": round(float(_dist), 3),
                    "candidate_anchor_id": str(_anc_id),
                    "candidate_anchor_name": _anc["name"],
                    "candidate_coordinate": [_anc["lon"], _anc["lat"]],
                    "snap_delta_ft": round(float(_dist), 3),
                    "classification": _cls,
                }
            )

            if _cls == "near":
                _near_n += 1
            else:
                _orphan_n += 1

        return {
            "schema_version": "endpoint-snap-recommendation-1",
            "tolerance_ft": _NODE_CONTINUITY_TOLERANCE_FT,
            "near_band_ft": _NEAR_ENDPOINT_BAND_FT,
            "recommendations": _recommendations,
            "summary": {
                "total_recommendations": len(_recommendations),
                "near_recommendations": _near_n,
                "orphan_recommendations": _orphan_n,
            },
            "stability_note": _SNAP_RECOMMENDATION_STABILITY_NOTE,
        }

    except Exception:
        return _empty_result()


@localhost_router.get("/api/observability/endpoint-snap-recommendations")
def get_endpoint_snap_recommendations() -> JSONResponse:
    """Phase 1T — endpoint snap recommendations (read-only, post-validator).

    Schema version: "endpoint-snap-recommendation-1".

    For each redline endpoint classified as 'near' or 'orphan' by the Phase
    1S validator, returns the candidate anchor coordinate — the exact location
    of the nearest KMZ point feature already identified by the validator.
    No new geometry is computed.

    Returns STATE["endpoint_snap_recommendations"] if populated, or
    computes on-the-fly from current STATE.

    Always returns HTTP 200.  No writes.  No state mutations.
    No operational side effects.

    USAGE POLICY: See TOPOLOGY_SIDECAR_USAGE_POLICY.md.
    No operational consumer may depend on this endpoint being non-empty.
    """
    from datetime import timezone as _tz_snap

    _generated_at_snap = datetime.now(_tz_snap.utc).isoformat()
    try:
        _stored = STATE.get("endpoint_snap_recommendations")
        if isinstance(_stored, dict):
            _result = dict(_stored)
        else:
            _result = _build_endpoint_snap_recommendations(
                STATE.get("redline_endpoint_validation"),
                STATE.get("kmz_reference"),
            )
        _result["generated_at"] = _generated_at_snap
        return JSONResponse(_result)
    except Exception as _snap_exc:
        print(
            f"[ENDPOINT_SNAP_RECOMMENDATIONS] WARNING: failed to serve: "
            f"{type(_snap_exc).__name__}: {_snap_exc}",
            flush=True,
        )
        _empty = _build_endpoint_snap_recommendations(None, None)
        _empty["generated_at"] = _generated_at_snap
        return JSONResponse(_empty)


# ---------------------------------------------------------------------------
# Phase 1U — Operator-Approved Snap Review Events
# ---------------------------------------------------------------------------


def _snap_recommendation_sha256(snapshot: Dict[str, Any]) -> str:
    """Compute a deterministic sha256 hex-digest for a recommendation snapshot.

    Snapshot is serialised with sorted keys, compact separators, then hashed.
    Pure function — no side effects.
    """
    _raw = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(_raw.encode("utf-8")).hexdigest()


def _append_snap_review_event(
    segment_id: str,
    endpoint_label: str,
    decision: str,
    recommendation_snapshot: Dict[str, Any],
    operator_id: str,
    session_id: Optional[str],
) -> str:
    """Phase 1U — append one snap-review-event to the JSONL log.

    Returns the generated event_id.

    ISOLATION GUARANTEE: This function only writes to ``SNAP_REVIEW_EVENTS_PATH``.
    It NEVER reads or writes to any matching, scoring, geometry, billing, or
    operational system.
    """
    from datetime import timezone as _tz_sre

    _event_id_sre = str(uuid.uuid4())
    try:
        _snapshot = dict(recommendation_snapshot) if isinstance(recommendation_snapshot, dict) else {}
        _sha = _snap_recommendation_sha256(_snapshot)
        _row_sre: Dict[str, Any] = {
            "schema_version": "snap-review-event-1",
            "event_id": _event_id_sre,
            "created_at": datetime.now(_tz_sre.utc).isoformat(),
            "recommendation_key": {
                "segment_id": str(segment_id),
                "endpoint": str(endpoint_label),
            },
            "recommendation_snapshot": _snapshot,
            "input_sha256": _sha,
            "decision": str(decision),
            "operator_id": str(operator_id)[:200] if operator_id else "anonymous",
            "session_id": str(session_id) if session_id else None,
        }

        with open(SNAP_REVIEW_EVENTS_PATH, "a", encoding="utf-8") as _fh_sre:
            _fh_sre.write(json.dumps(_row_sre, separators=(",", ":")) + "\n")

        # Tail-truncate to cap — same pattern as other observability appenders.
        with open(SNAP_REVIEW_EVENTS_PATH, "r", encoding="utf-8") as _fh_sre:
            _all_sre = _fh_sre.readlines()
        if len(_all_sre) > SNAP_REVIEW_EVENTS_MAX_ROWS:
            _all_sre = _all_sre[-SNAP_REVIEW_EVENTS_MAX_ROWS:]
            with open(SNAP_REVIEW_EVENTS_PATH, "w", encoding="utf-8") as _fh_sre:
                _fh_sre.writelines(_all_sre)

    except Exception as _sre_exc:
        print(
            f"[SNAP_REVIEW_EVENTS] WARNING: failed to append event: "
            f"{type(_sre_exc).__name__}: {_sre_exc}",
            flush=True,
        )
    return _event_id_sre


def _resolve_current_snap_review_decisions(
    segment_id: Optional[str] = None,
    endpoint_label: Optional[str] = None,
) -> Dict[str, Optional[Dict[str, Any]]]:
    """Phase 1U — latest-wins resolution of snap review decisions.

    Returns a dict keyed by ``"<segment_id>|<endpoint>"`` strings.  For each
    key, the value is the most-recent non-revoked event dict, or ``None`` if
    the most-recent event is a revoke (revoked clears the decision).

    If ``segment_id`` and ``endpoint_label`` are both provided, the result
    is scoped to that single key.  Otherwise all keys present in the file
    are returned.

    Pure computation over the JSONL file.  No writes.  Never raises.
    """
    _result: Dict[str, Optional[Dict[str, Any]]] = {}
    try:
        if not SNAP_REVIEW_EVENTS_PATH.exists():
            return _result
        with open(SNAP_REVIEW_EVENTS_PATH, "r", encoding="utf-8") as _fh_sre:
            _lines_sre = _fh_sre.readlines()

        # Scoped filter if requested.
        _filter_key: Optional[str] = None
        if segment_id and endpoint_label:
            _filter_key = f"{segment_id}|{endpoint_label}"

        # Oldest → newest; last write wins.
        for _line_sre in _lines_sre:
            _line_sre = _line_sre.strip()
            if not _line_sre:
                continue
            try:
                _ev_sre = json.loads(_line_sre)
            except json.JSONDecodeError:
                continue
            _key_sre = _ev_sre.get("recommendation_key") or {}
            _seg = _key_sre.get("segment_id") or ""
            _ep = _key_sre.get("endpoint") or ""
            _composite = f"{_seg}|{_ep}"
            if _filter_key and _composite != _filter_key:
                continue
            _decision_sre = _ev_sre.get("decision") or ""
            if _decision_sre == "revoked":
                _result[_composite] = None  # revoke clears the current decision
            else:
                _result[_composite] = _ev_sre
    except Exception as _sre_read_exc:
        print(
            f"[SNAP_REVIEW_EVENTS] WARNING: failed to resolve decisions: "
            f"{type(_sre_read_exc).__name__}: {_sre_read_exc}",
            flush=True,
        )
    return _result


@localhost_router.post("/api/observability/snap-review-events")
def post_snap_review_event(
    body: Dict[str, Any] = Body(default_factory=dict),
    session_id: Optional[str] = None,
) -> JSONResponse:
    """Phase 1U — append a snap-review-event (operator review telemetry only).

    Schema version: "snap-review-event-1".

    Required body keys:
      segment_id — str (must match a live recommendation in STATE)
      endpoint   — "start" | "end"
      decision   — "approved" | "rejected" | "revoked"

    Optional body keys:
      operator_id — str identifier for the reviewer (truncated to 200 chars)

    Rejects (returns {"accepted": false}) if:
      - decision not in valid set
      - segment_id + endpoint not found in current STATE recommendations
      - closeout is locked for this session

    Returns {"accepted": true, "event_id": str} on success.
    Always HTTP 200.  No operational side effects.
    """
    if _is_closeout_locked():
        return JSONResponse({"accepted": False, "error": "closeout_locked"})

    if not isinstance(body, dict):
        return JSONResponse({"accepted": False, "error": "invalid_body"})

    _decision_sre = str(body.get("decision") or "").strip()
    if _decision_sre not in _SNAP_REVIEW_VALID_DECISIONS:
        return JSONResponse({"accepted": False, "error": "invalid_decision"})

    _seg_sre = str(body.get("segment_id") or "").strip()
    _ep_sre = str(body.get("endpoint") or "").strip()
    if not _seg_sre or _ep_sre not in ("start", "end"):
        return JSONResponse({"accepted": False, "error": "invalid_key"})

    # Look up live recommendation snapshot — reject stale keys.
    _snap_state = STATE.get("endpoint_snap_recommendations")
    _recs_sre: List[Dict[str, Any]] = []
    if isinstance(_snap_state, dict):
        _recs_sre = _snap_state.get("recommendations") or []
    _live_rec: Optional[Dict[str, Any]] = None
    for _r_sre in _recs_sre:
        if (
            isinstance(_r_sre, dict)
            and str(_r_sre.get("segment_id") or "") == _seg_sre
            and str(_r_sre.get("endpoint") or "") == _ep_sre
        ):
            _live_rec = _r_sre
            break

    if _live_rec is None:
        return JSONResponse({"accepted": False, "error": "recommendation_not_found"})

    # Build snapshot with exactly the fields defined by the schema.
    _snapshot_sre: Dict[str, Any] = {
        "route_id": _live_rec.get("route_id"),
        "current_coordinate": _live_rec.get("current_coordinate"),
        "current_distance_ft": _live_rec.get("current_distance_ft"),
        "candidate_anchor_id": _live_rec.get("candidate_anchor_id"),
        "candidate_anchor_name": _live_rec.get("candidate_anchor_name"),
        "candidate_coordinate": _live_rec.get("candidate_coordinate"),
        "snap_delta_ft": _live_rec.get("snap_delta_ft"),
        "classification": _live_rec.get("classification"),
    }
    _operator_sre = str(body.get("operator_id") or "anonymous")[:200]
    _sid_sre = str(session_id).strip() if session_id else None

    _event_id_sre = _append_snap_review_event(
        segment_id=_seg_sre,
        endpoint_label=_ep_sre,
        decision=_decision_sre,
        recommendation_snapshot=_snapshot_sre,
        operator_id=_operator_sre,
        session_id=_sid_sre,
    )
    return JSONResponse({"accepted": True, "event_id": _event_id_sre, "decision": _decision_sre})


@localhost_router.get("/api/observability/snap-review-events")
def get_snap_review_events(
    limit: int = 100,
    decision: Optional[str] = None,
) -> JSONResponse:
    """Phase 1U — newest-first event log of all snap-review-events.

    Query params:
      limit    — int, default 100, max 1000, min 1
      decision — optional filter: "approved" | "rejected" | "revoked"

    Also returns a summary block:
      total_events, approved_count, rejected_count, revoked_count,
      reviewed_recommendation_count, unreviewed_recommendation_count.

    Always HTTP 200.  Missing or corrupt file → empty results.
    Read-only: no writes.
    """
    _limit_sre = max(1, min(limit, 1000))
    _dec_filter = str(decision).strip() if decision else None
    try:
        _events_sre: List[Dict[str, Any]] = []
        _all_sre: List[Dict[str, Any]] = []

        if SNAP_REVIEW_EVENTS_PATH.exists():
            with open(SNAP_REVIEW_EVENTS_PATH, "r", encoding="utf-8") as _fh_sre:
                _raw_sre = _fh_sre.readlines()
            for _line_sre in reversed(_raw_sre):
                _line_sre = _line_sre.strip()
                if not _line_sre:
                    continue
                try:
                    _ev_sre = json.loads(_line_sre)
                except json.JSONDecodeError:
                    continue
                _all_sre.append(_ev_sre)
                if _dec_filter and _ev_sre.get("decision") != _dec_filter:
                    continue
                if len(_events_sre) < _limit_sre:
                    _events_sre.append(_ev_sre)

        # Compute summary from full (unfiltered) list.
        _approved_n = sum(1 for e in _all_sre if e.get("decision") == "approved")
        _rejected_n = sum(1 for e in _all_sre if e.get("decision") == "rejected")
        _revoked_n = sum(1 for e in _all_sre if e.get("decision") == "revoked")
        # Reviewed keys = keys that have any event; unreviewed = current recs minus reviewed.
        _all_keys_sre: set = set()
        for _ev_sre in _all_sre:
            _k_sre = _ev_sre.get("recommendation_key") or {}
            _seg_k = _k_sre.get("segment_id") or ""
            _ep_k = _k_sre.get("endpoint") or ""
            if _seg_k and _ep_k:
                _all_keys_sre.add(f"{_seg_k}|{_ep_k}")
        _reviewed_n = len(_all_keys_sre)

        _snap_recs_sre = STATE.get("endpoint_snap_recommendations") or {}
        _total_recs_sre = len(_snap_recs_sre.get("recommendations") or []) if isinstance(_snap_recs_sre, dict) else 0
        _unreviewed_n = max(0, _total_recs_sre - _reviewed_n)

        return JSONResponse(
            {
                "events": _events_sre,
                "summary": {
                    "total_events": len(_all_sre),
                    "approved_count": _approved_n,
                    "rejected_count": _rejected_n,
                    "revoked_count": _revoked_n,
                    "reviewed_recommendation_count": _reviewed_n,
                    "unreviewed_recommendation_count": _unreviewed_n,
                },
            }
        )
    except Exception as _sre_get_exc:
        print(
            f"[SNAP_REVIEW_EVENTS] WARNING: failed to read events: "
            f"{type(_sre_get_exc).__name__}: {_sre_get_exc}",
            flush=True,
        )
        return JSONResponse({"events": [], "summary": {}})


@localhost_router.get("/api/observability/snap-review-events/current")
def get_snap_review_events_current(
    segment_id: str = Query(""),
    endpoint: str = Query(""),
) -> JSONResponse:
    """Phase 1U — latest-wins resolved decision for a single recommendation key.

    Query params: segment_id (str), endpoint ("start" | "end").
    Returns {"current": <event> | null}.
    - null means no decision, or the most-recent event was a revoke.
    Always HTTP 200.  Read-only.
    """
    _seg_sre = str(segment_id).strip()
    _ep_sre = str(endpoint).strip()
    if not _seg_sre or _ep_sre not in ("start", "end"):
        return JSONResponse({"current": None})
    try:
        _resolved = _resolve_current_snap_review_decisions(_seg_sre, _ep_sre)
        _key = f"{_seg_sre}|{_ep_sre}"
        return JSONResponse({"current": _resolved.get(_key)})
    except Exception as _sre_cur_exc:
        print(
            f"[SNAP_REVIEW_EVENTS] WARNING: failed to resolve current: "
            f"{type(_sre_cur_exc).__name__}: {_sre_cur_exc}",
            flush=True,
        )
        return JSONResponse({"current": None})


# ---------------------------------------------------------------------------
# Phase 1V — Endpoint-Only Snap Preview Markers (read-only, diagnostic-only)
# ---------------------------------------------------------------------------

_SNAP_PREVIEW_MARKER_STABILITY_NOTE = (
    "Snap preview markers are advisory review aids only. Each marker derives "
    "from existing endpoint snap recommendations and existing operator review "
    "events. No new geometry is computed. The operational redline layer is "
    "never modified."
)


def _build_snap_preview_markers(
    snap_recommendations: Optional[Dict[str, Any]],
    decisions: Optional[Dict[str, Optional[Dict[str, Any]]]] = None,
) -> Dict[str, Any]:
    """Phase 1V — derive a list of ghost-marker records from existing
    endpoint snap recommendations.

    Pure function.  Never raises.  Never mutates inputs.

    Each marker's ``candidate_coordinate`` is byte-identical to the
    corresponding recommendation's ``candidate_coordinate``.  No interpolation,
    no geometry math, no route reconstruction.

    ``decisions`` is the optional output of
    ``_resolve_current_snap_review_decisions()``.  When omitted, the marker's
    ``current_decision`` is always ``None``.

    Returns a schema-locked dict; never None.
    """
    from datetime import timezone as _tz_mk

    _generated_at_mk = datetime.now(_tz_mk.utc).isoformat()
    _empty_mk: Dict[str, Any] = {
        "schema_version": "snap-preview-marker-1",
        "generated_at": _generated_at_mk,
        "markers": [],
        "summary": {
            "total_markers": 0,
            "near_markers": 0,
            "orphan_markers": 0,
            "with_decision": 0,
            "without_decision": 0,
        },
        "stability_note": _SNAP_PREVIEW_MARKER_STABILITY_NOTE,
    }

    try:
        if not isinstance(snap_recommendations, dict):
            return _empty_mk
        _recs_mk = snap_recommendations.get("recommendations")
        if not isinstance(_recs_mk, list):
            return _empty_mk

        _decisions_mk: Dict[str, Optional[Dict[str, Any]]] = (
            decisions if isinstance(decisions, dict) else {}
        )

        _markers_mk: List[Dict[str, Any]] = []
        _near_n = 0
        _orphan_n = 0
        _with_dec_n = 0
        _without_dec_n = 0

        for _rec_mk in _recs_mk:
            if not isinstance(_rec_mk, dict):
                continue
            _seg_mk = _rec_mk.get("segment_id")
            _ep_mk = _rec_mk.get("endpoint")
            if not isinstance(_seg_mk, str) or not _seg_mk:
                continue
            if _ep_mk not in ("start", "end"):
                continue

            _classification_mk = _rec_mk.get("classification")
            if _classification_mk not in ("near", "orphan"):
                continue

            # Deterministic marker_id: sha1(segment_id|endpoint)[:16]
            _key_mk = f"{_seg_mk}|{_ep_mk}"
            _marker_id_mk = hashlib.sha1(_key_mk.encode("utf-8")).hexdigest()[:16]

            # Decision lookup — revoked → None.
            _dec_event_mk = _decisions_mk.get(_key_mk)
            _current_decision_mk: Optional[str] = None
            if isinstance(_dec_event_mk, dict):
                _decval = _dec_event_mk.get("decision")
                if _decval in ("approved", "rejected"):
                    _current_decision_mk = _decval

            if _current_decision_mk is not None:
                _with_dec_n += 1
            else:
                _without_dec_n += 1

            if _classification_mk == "near":
                _near_n += 1
            elif _classification_mk == "orphan":
                _orphan_n += 1

            _markers_mk.append(
                {
                    "marker_id": _marker_id_mk,
                    "segment_id": _seg_mk,
                    "endpoint": _ep_mk,
                    "current_coordinate": _rec_mk.get("current_coordinate"),
                    "candidate_coordinate": _rec_mk.get("candidate_coordinate"),
                    "candidate_anchor_id": _rec_mk.get("candidate_anchor_id"),
                    "candidate_anchor_name": _rec_mk.get("candidate_anchor_name"),
                    "snap_delta_ft": _rec_mk.get("snap_delta_ft"),
                    "classification": _classification_mk,
                    "current_decision": _current_decision_mk,
                    "presentation_role": "ghost_marker",
                }
            )

        return {
            "schema_version": "snap-preview-marker-1",
            "generated_at": _generated_at_mk,
            "markers": _markers_mk,
            "summary": {
                "total_markers": len(_markers_mk),
                "near_markers": _near_n,
                "orphan_markers": _orphan_n,
                "with_decision": _with_dec_n,
                "without_decision": _without_dec_n,
            },
            "stability_note": _SNAP_PREVIEW_MARKER_STABILITY_NOTE,
        }

    except Exception as _mk_exc:  # pragma: no cover
        print(
            f"[SNAP_PREVIEW_MARKERS] WARNING: failed to build markers: "
            f"{type(_mk_exc).__name__}: {_mk_exc}",
            flush=True,
        )
        return _empty_mk


@localhost_router.get("/api/observability/snap-preview-markers")
def get_snap_preview_markers() -> JSONResponse:
    """Phase 1V — endpoint-only snap preview markers (read-only, diagnostic).

    Schema version: "snap-preview-marker-1".

    Computes on-the-fly from STATE["endpoint_snap_recommendations"] and
    the latest-wins resolution of Phase 1U review events.  No persistence.
    No mutation of any STATE key.  No new geometry.

    Always returns HTTP 200.

    USAGE POLICY:
    Markers are advisory review aids only.  They MUST NOT be rendered into
    the operational map layer; they live exclusively in the diagnostics
    panel.  No operational consumer may depend on this endpoint being
    non-empty.
    """
    try:
        _snap_state_mk = STATE.get("endpoint_snap_recommendations")
        _decisions_mk = _resolve_current_snap_review_decisions()
        _result_mk = _build_snap_preview_markers(
            snap_recommendations=_snap_state_mk if isinstance(_snap_state_mk, dict) else None,
            decisions=_decisions_mk,
        )
        return JSONResponse(_result_mk)
    except Exception as _mk_endpoint_exc:  # pragma: no cover
        print(
            f"[SNAP_PREVIEW_MARKERS] WARNING: endpoint failed: "
            f"{type(_mk_endpoint_exc).__name__}: {_mk_endpoint_exc}",
            flush=True,
        )
        from datetime import timezone as _tz_mk_err
        return JSONResponse(
            {
                "schema_version": "snap-preview-marker-1",
                "generated_at": datetime.now(_tz_mk_err.utc).isoformat(),
                "markers": [],
                "summary": {
                    "total_markers": 0,
                    "near_markers": 0,
                    "orphan_markers": 0,
                    "with_decision": 0,
                    "without_decision": 0,
                },
                "stability_note": _SNAP_PREVIEW_MARKER_STABILITY_NOTE,
            }
        )


# ---------------------------------------------------------------------------
# Phase 1W — Reviewed Snapped Geometry Preview Layer (read-only, diagnostic)
# ---------------------------------------------------------------------------

_REVIEWED_SNAP_PREVIEW_STABILITY_NOTE = (
    "Reviewed snap preview geometry is advisory only. Each preview is a "
    "clone of the operational redline segment with ONLY approved endpoint "
    "coordinate(s) substituted. Intermediate vertices are byte-identical to "
    "the operational source. The operational redline layer is never modified."
)

_REVIEWED_SNAP_PREVIEW_FORBIDDEN_FIELDS: frozenset = frozenset(
    {"confidence", "score", "probability", "weight", "priority",
     "apply", "commit", "recommended", "final", "authoritative"}
)


def _build_reviewed_snap_preview(
    redline_segments: Optional[List[Dict[str, Any]]],
    snap_recommendations: Optional[Dict[str, Any]],
    decisions: Optional[Dict[str, Optional[Dict[str, Any]]]] = None,
) -> Dict[str, Any]:
    """Phase 1W — build preview geometry for segments with approved endpoint
    substitutions.

    Pure function.  Never raises.  Never mutates inputs.

    For each operational redline segment that has at least one APPROVED review
    event, produces a preview record containing:
      - A cloned coordinate array in GeoJSON [lon, lat] order.
      - Endpoint coordinate(s) replaced ONLY at indices backed by an approved
        Phase 1U event.
      - A substitution lineage tying each replacement to the originating event
        and recommendation.
      - A sha256 checksum of the operational segment's original coordinates.

    HARD GUARANTEES:
      - len(preview.coordinates) == len(original segment coordinates).
      - Intermediate coordinates are byte-identical to the operational source.
      - Substituted coordinates are byte-identical to candidate_coordinate from
        the matching recommendation.
      - No preview is emitted without at least one approved event.
      - Rejected / revoked / unreviewed recommendations produce no substitution.
      - No geometry recomputation.
      - Inputs are never mutated.
    """
    from datetime import timezone as _tz_pr

    _generated_at_pr = datetime.now(_tz_pr.utc).isoformat()
    _empty_pr: Dict[str, Any] = {
        "schema_version": "reviewed-snap-preview-1",
        "generated_at": _generated_at_pr,
        "previews": [],
        "summary": {
            "total_previews": 0,
            "previews_with_start_only": 0,
            "previews_with_end_only": 0,
            "previews_with_both": 0,
            "stale_previews": 0,
        },
        "stability_note": _REVIEWED_SNAP_PREVIEW_STABILITY_NOTE,
    }

    try:
        # ------------------------------------------------------------------ #
        # 0. Coerce inputs.
        # ------------------------------------------------------------------ #
        _segs_pr: List[Dict[str, Any]] = []
        if isinstance(redline_segments, list):
            for _s in redline_segments:
                if isinstance(_s, dict):
                    _segs_pr.append(_s)

        _recs_pr: List[Dict[str, Any]] = []
        if isinstance(snap_recommendations, dict):
            _recs_list = snap_recommendations.get("recommendations")
            if isinstance(_recs_list, list):
                _recs_pr = [r for r in _recs_list if isinstance(r, dict)]

        _decisions_pr: Dict[str, Optional[Dict[str, Any]]] = (
            decisions if isinstance(decisions, dict) else {}
        )

        if not _segs_pr:
            return _empty_pr

        # ------------------------------------------------------------------ #
        # 1. Index: segment_id → segment (first occurrence wins).
        # ------------------------------------------------------------------ #
        _seg_index: Dict[str, Dict[str, Any]] = {}
        for _s in _segs_pr:
            _sid = str(_s.get("segment_id") or "")
            if _sid and _sid not in _seg_index:
                _seg_index[_sid] = _s

        # ------------------------------------------------------------------ #
        # 2. Index: (segment_id, endpoint) → recommendation.
        # ------------------------------------------------------------------ #
        _rec_index: Dict[str, Dict[str, Any]] = {}
        for _r in _recs_pr:
            _rsid = str(_r.get("segment_id") or "")
            _rep = str(_r.get("endpoint") or "")
            if _rsid and _rep in ("start", "end"):
                _rec_index[f"{_rsid}|{_rep}"] = _r

        # ------------------------------------------------------------------ #
        # 3. Collect all segment_ids that have at least one approved decision.
        # ------------------------------------------------------------------ #
        _approved_by_seg: Dict[str, Dict[str, Dict[str, Any]]] = {}
        # _decisions_pr keys are "<segment_id>|<endpoint>".
        for _dk, _dev in _decisions_pr.items():
            if not isinstance(_dev, dict):
                continue  # revoked or None → skip
            if _dev.get("decision") != "approved":
                continue
            _parts = _dk.split("|", 1)
            if len(_parts) != 2:
                continue
            _dsid, _dep = _parts[0], _parts[1]
            if _dep not in ("start", "end"):
                continue
            if _dsid not in _approved_by_seg:
                _approved_by_seg[_dsid] = {}
            _approved_by_seg[_dsid][_dep] = _dev

        if not _approved_by_seg:
            return _empty_pr

        # ------------------------------------------------------------------ #
        # 4. Build preview records.
        # ------------------------------------------------------------------ #
        _previews_pr: List[Dict[str, Any]] = []
        _start_only_n = 0
        _end_only_n = 0
        _both_n = 0
        _stale_n = 0

        # Deterministic order.
        for _psid in sorted(_approved_by_seg.keys()):
            _pep_map = _approved_by_seg[_psid]  # {"start": ev, ...}

            # Stale check: segment must exist in redline_segments.
            _seg_pr = _seg_index.get(_psid)
            if _seg_pr is None:
                _stale_n += 1
                continue

            # Get operational coords (native [lat, lon] from route clipping).
            _raw_coords = _seg_pr.get("coords")
            if not isinstance(_raw_coords, list) or len(_raw_coords) < 2:
                _stale_n += 1
                continue

            # Validate coord entries.
            _valid_coords: List[List[float]] = []
            for _c in _raw_coords:
                if isinstance(_c, (list, tuple)) and len(_c) >= 2:
                    try:
                        _valid_coords.append([float(_c[0]), float(_c[1])])
                    except (TypeError, ValueError):
                        _stale_n += 1
                        _valid_coords = []
                        break
                else:
                    _stale_n += 1
                    _valid_coords = []
                    break

            if len(_valid_coords) < 2:
                _stale_n += 1
                continue

            # Compute operational checksum over native coords before any clone.
            _op_checksum = hashlib.sha256(
                json.dumps(_valid_coords, separators=(",", ":")).encode("utf-8")
            ).hexdigest()

            # Convert to [lon, lat] for GeoJSON preview_geometry.
            # Native format is [lat, lon], so swap indices.
            _preview_coords: List[List[float]] = [
                [_c[1], _c[0]] for _c in _valid_coords
            ]

            # Build endpoint substitutions.
            _sub_start: Optional[Dict[str, Any]] = None
            _sub_end: Optional[Dict[str, Any]] = None

            for _ep_label in ("start", "end"):
                _ev_pr = _pep_map.get(_ep_label)
                if _ev_pr is None:
                    continue  # not approved for this endpoint
                _rec_pr = _rec_index.get(f"{_psid}|{_ep_label}")
                if _rec_pr is None:
                    _stale_n += 1
                    continue  # recommendation no longer present → stale
                _cand_coord = _rec_pr.get("candidate_coordinate")
                if (
                    not isinstance(_cand_coord, (list, tuple))
                    or len(_cand_coord) < 2
                ):
                    _stale_n += 1
                    continue
                try:
                    _cand_lon = float(_cand_coord[0])
                    _cand_lat = float(_cand_coord[1])
                except (TypeError, ValueError):
                    _stale_n += 1
                    continue

                _coord_idx = 0 if _ep_label == "start" else -1
                _orig_coord = list(_preview_coords[_coord_idx])  # snapshot [lon, lat]

                # Substitute endpoint with candidate coordinate (byte-identical).
                _preview_coords[_coord_idx] = [_cand_lon, _cand_lat]

                _ev_id_pr = str(_ev_pr.get("event_id") or "")
                _sub = {
                    "approved_event_id": _ev_id_pr,
                    "recommendation_key": {
                        "segment_id": _psid,
                        "endpoint": _ep_label,
                    },
                    "original_coordinate": _orig_coord,
                    "substituted_coordinate": [_cand_lon, _cand_lat],
                    "candidate_anchor_id": str(_rec_pr.get("candidate_anchor_id") or ""),
                }
                if _ep_label == "start":
                    _sub_start = _sub
                else:
                    _sub_end = _sub

            # Require at least one actual substitution.
            if _sub_start is None and _sub_end is None:
                _stale_n += 1
                continue

            # Coordinate count must be preserved exactly.
            assert len(_preview_coords) == len(_valid_coords)  # internal invariant

            # Deterministic preview_id.
            _start_eid = _sub_start["approved_event_id"] if _sub_start else ""
            _end_eid = _sub_end["approved_event_id"] if _sub_end else ""
            _pid_input = f"{_psid}|{_start_eid}|{_end_eid}"
            _preview_id = hashlib.sha1(_pid_input.encode("utf-8")).hexdigest()[:16]

            _previews_pr.append(
                {
                    "preview_id": _preview_id,
                    "source_segment_id": _psid,
                    "preview_geometry": {
                        "type": "LineString",
                        "coordinates": _preview_coords,
                    },
                    "endpoint_substitutions": {
                        "start": _sub_start,
                        "end": _sub_end,
                    },
                    "operational_segment_checksum": _op_checksum,
                    "presentation_role": "preview_polyline",
                }
            )

            if _sub_start and _sub_end:
                _both_n += 1
            elif _sub_start:
                _start_only_n += 1
            else:
                _end_only_n += 1

        return {
            "schema_version": "reviewed-snap-preview-1",
            "generated_at": _generated_at_pr,
            "previews": _previews_pr,
            "summary": {
                "total_previews": len(_previews_pr),
                "previews_with_start_only": _start_only_n,
                "previews_with_end_only": _end_only_n,
                "previews_with_both": _both_n,
                "stale_previews": _stale_n,
            },
            "stability_note": _REVIEWED_SNAP_PREVIEW_STABILITY_NOTE,
        }

    except Exception as _pr_exc:  # pragma: no cover
        print(
            f"[REVIEWED_SNAP_PREVIEW] WARNING: failed to build previews: "
            f"{type(_pr_exc).__name__}: {_pr_exc}",
            flush=True,
        )
        return _empty_pr


# ---------------------------------------------------------------------------
# Phase 2A — KMZ Engineering Render Payload (read-only, compute-on-read)
# ---------------------------------------------------------------------------

_KMZ_RENDER_PAYLOAD_SCHEMA = "kmz-render-payload-3"
_KMZ_RENDER_MAX_POINTS: int = 4000
_KMZ_RENDER_MAX_LINES: int = 1500
_KMZ_RENDER_MAX_POLYGONS: int = 500
_KMZ_RENDER_MAX_VERTICES_PER_LINE: int = 200
_KMZ_RENDER_MAX_NAME_LEN: int = 80
_KMZ_RENDER_MAX_SUMMARY_LEN: int = 120
_KMZ_RENDER_MAX_FOLDER_DEPTH: int = 4
_KMZ_RENDER_DEFAULT_COLOR: str = "#4a9eff"

# Classifications that map to specific glyphs on the map.
_KMZ_RENDER_GLYPH_MAP: Dict[str, str] = {
    "handhole": "circle",
    "node": "circle",
    "splice": "square",
    "splice_enclosure": "square",
    "reel": "diamond",
    "slack_loop": "diamond",
    "structure_marker": "circle",  # Phase 2B V2.1 — splice/HH/service structures
}

# Lifecycle labels that suggest a dashed rendering.
_KMZ_RENDER_DASH_LIFECYCLES: frozenset = frozenset(
    {"proposed", "decommissioned", "survey"}
)

# Forbidden: these fields must never appear in the render payload because
# they are observability-internal or operational pipeline fields.
_KMZ_RENDER_PAYLOAD_FORBIDDEN_FIELDS: frozenset = frozenset(
    {
        "redline_segments",
        "route_catalog",
        "match_pass_id",
        "snap_review_events",
        "endpoint_snap_recommendations",
    }
)


def _build_kmz_render_payload(
    kmz_semantic: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Derive a capped, pre-styled render payload from *kmz_semantic*.

    Phase 2B V2 — pure, never raises, never mutates the input.
    Schema version: "kmz-render-payload-2".

    Adds per-feature fields: description, extended_data, chainage_ft,
    sequence_number, sequence_kind, lifecycle (full struct).
    Adds polygon inner rings.
    Fixes per-type truncation flags.
    Consumes full MultiGeometry LineString coords and Polygon outer/inner rings.

    Output shape:
        {
          "schema_version": "kmz-render-payload-2",
          "generated_at": str,
          "render_caps": {max_points, max_lines, max_polygons, max_vertices_per_line},
          "points":    [KmzRenderPoint, ...],
          "lines":     [KmzRenderLine, ...],
          "polygons":  [KmzRenderPolygon, ...],
          "categories":[KmzRenderCategory, ...],
          "summary":   KmzRenderSummary,
        }

    Caps: 4 000 points, 1 500 lines, 500 polygons, 200 vertices/line.
    Text: names ≤ 80 chars, descriptions ≤ 200 chars, folder depth ≤ 4.

    USAGE POLICY:
    This payload is advisory / rendering-only.  It MUST NOT influence
    matching, scoring, billing, closeout, or any operational pipeline.
    The payload is derived entirely from STATE["kmz_semantic"] and carries
    no write path.
    """
    from datetime import timezone as _tz_rp

    _generated_at = datetime.now(_tz_rp.utc).isoformat()

    _empty: Dict[str, Any] = {
        "schema_version": _KMZ_RENDER_PAYLOAD_SCHEMA,
        "generated_at": _generated_at,
        "render_caps": {
            "max_points": _KMZ_RENDER_MAX_POINTS,
            "max_lines": _KMZ_RENDER_MAX_LINES,
            "max_polygons": _KMZ_RENDER_MAX_POLYGONS,
            "max_vertices_per_line": _KMZ_RENDER_MAX_VERTICES_PER_LINE,
        },
        "points": [],
        "lines": [],
        "polygons": [],
        "categories": [],
        "summary": {
            "total_points": 0,
            "total_lines": 0,
            "total_polygons": 0,
            "points_truncated": False,
            "lines_truncated": False,
            "polygons_truncated": False,
            "source_feature_count": 0,
        },
    }

    # ── inner helpers (scoped) ───────────────────────────────────────────────

    def _cap_coords(raw: Any) -> List[List[float]]:
        """Validate and cap a coordinate list to max_vertices_per_line."""
        out_c: List[List[float]] = []
        if not isinstance(raw, list):
            return out_c
        for _v in raw[: _KMZ_RENDER_MAX_VERTICES_PER_LINE]:
            if isinstance(_v, (list, tuple)) and len(_v) >= 2:
                try:
                    out_c.append([float(_v[0]), float(_v[1])])
                except (TypeError, ValueError):
                    pass
        return out_c

    def _cap_inner_rings(raw: Any) -> List[List[List[float]]]:
        """Validate and cap a list of inner rings."""
        out_r: List[List[List[float]]] = []
        if not isinstance(raw, list):
            return out_r
        for _ring in raw:
            _ring_safe = _cap_coords(_ring)
            if len(_ring_safe) >= 3:
                out_r.append(_ring_safe)
        return out_r

    def _make_lifecycle(raw: Any) -> Optional[Dict[str, str]]:
        """Return a full lifecycle struct {label, confidence, reason} or None."""
        if not isinstance(raw, dict):
            return None
        _lbl = str(raw.get("label") or "").strip()
        if not _lbl:
            return None
        return {
            "label": _lbl,
            "confidence": str(raw.get("confidence") or ""),
            "reason": str(raw.get("reason") or ""),
        }

    def _make_extended_data(raw: Any) -> Dict[str, str]:
        """Return first 32 key-value pairs, values truncated to 80 chars."""
        if not isinstance(raw, dict):
            return {}
        _out_ed: Dict[str, str] = {}
        for _k, _v in list(raw.items())[:32]:
            _out_ed[str(_k)] = str(_v)[:80]
        return _out_ed

    def _common_fields(feat: Dict[str, Any]) -> Dict[str, Any]:
        """Fields shared by every point, line, and polygon record."""
        _desc = str(feat.get("description") or "")[:200]
        _desc_raw = str(feat.get("description_raw") or "")[:4096]
        _ext = _make_extended_data(feat.get("extended_data"))
        _ch = feat.get("chainage_ft")
        _seq_num = feat.get("sequence_number")
        _seq_kind = feat.get("sequence_kind")
        _lc = _make_lifecycle(feat.get("lifecycle"))
        # Phase 2I — icon/style fidelity fields
        _style_url = str(feat.get("style_url") or "")
        _style_res = feat.get("style_resolved")
        _icon_href = str(_style_res.get("icon_href") or "") if isinstance(_style_res, dict) else ""
        return {
            "description": _desc,
            "description_raw": _desc_raw,
            "extended_data": _ext,
            "chainage_ft": float(_ch) if isinstance(_ch, (int, float)) and _ch is not None else None,
            "sequence_number": str(_seq_num) if _seq_num is not None else None,
            "sequence_kind": str(_seq_kind) if _seq_kind is not None else None,
            "lifecycle": _lc,
            "style_url": _style_url,
            "icon_href": _icon_href,
        }

    # ── main iteration ───────────────────────────────────────────────────────

    try:
        if not isinstance(kmz_semantic, dict):
            return _empty

        features = kmz_semantic.get("features")
        if not isinstance(features, list) or not features:
            return _empty

        points: List[Dict[str, Any]] = []
        lines: List[Dict[str, Any]] = []
        polygons: List[Dict[str, Any]] = []
        # category counters: classification -> {point, line, polygon}
        cat_counts: Dict[str, Dict[str, int]] = {}
        # Phase 2B — per-type cap flags (fixed truncation bug)
        _points_capped = False
        _lines_capped = False
        _polygons_capped = False

        source_feature_count = 0

        for _feat in features:
            if not isinstance(_feat, dict):
                continue
            source_feature_count += 1

            _fid = str(_feat.get("feature_id") or "")
            _cls = str(_feat.get("classification") or "unknown")
            _raw_name = _feat.get("placemark_name") or ""
            _name = str(_raw_name)[:_KMZ_RENDER_MAX_NAME_LEN]

            # folder_path: list of strings, depth-capped
            _raw_fp = _feat.get("folder_path")
            if isinstance(_raw_fp, list):
                _folder_path: List[str] = [
                    str(p) for p in _raw_fp[: _KMZ_RENDER_MAX_FOLDER_DEPTH]
                ]
            else:
                _folder_path = []

            # Style resolution
            _style = _feat.get("style_resolved")
            if not isinstance(_style, dict):
                _style = {}

            _line_color = _style.get("line_color")
            _poly_fill = _style.get("poly_fill")
            _line_width_raw = _style.get("line_width")
            try:
                _line_width = min(float(_line_width_raw), 3.0) if _line_width_raw is not None else 2.0
            except (TypeError, ValueError):
                _line_width = 2.0

            # Lifecycle → dash hint + full struct
            _lifecycle_raw = _feat.get("lifecycle")
            _lifecycle_label = ""
            if isinstance(_lifecycle_raw, dict):
                _lifecycle_label = str(_lifecycle_raw.get("label") or "")
            _dash = _lifecycle_label in _KMZ_RENDER_DASH_LIFECYCLES

            # Icon glyph
            _icon_glyph = _KMZ_RENDER_GLYPH_MAP.get(_cls, "ring")

            # Category counter
            if _cls not in cat_counts:
                cat_counts[_cls] = {"point": 0, "line": 0, "polygon": 0}

            # Shared Tier-1 metadata fields (Phase 2B)
            _common = _common_fields(_feat)

            # Geometry dispatch
            _geom = _feat.get("full_geometry")
            if not isinstance(_geom, dict):
                # MultiGeometry — walk children
                _children = _feat.get("multigeometry_children")
                if isinstance(_children, list):
                    for _child in _children:
                        if not isinstance(_child, dict):
                            continue
                        _ckind = _child.get("kind")
                        if _ckind == "Point":
                            if len(points) >= _KMZ_RENDER_MAX_POINTS:
                                _points_capped = True
                                continue
                            _ch_coord = _child.get("coord_hint")
                            if not isinstance(_ch_coord, (list, tuple)) or len(_ch_coord) < 2:
                                continue
                            try:
                                _ch_lat = float(_ch_coord[0])
                                _ch_lon = float(_ch_coord[1])
                            except (TypeError, ValueError):
                                continue
                            points.append(
                                {
                                    "feature_id": f"{_fid}_pt",
                                    "coord": [_ch_lat, _ch_lon],
                                    "classification": _cls,
                                    "name": _name,
                                    "icon_glyph": _icon_glyph,
                                    "color": _line_color or _KMZ_RENDER_DEFAULT_COLOR,
                                    "folder_path": _folder_path,
                                    **_common,
                                }
                            )
                            cat_counts[_cls]["point"] += 1
                        elif _ckind == "LineString":
                            if len(lines) >= _KMZ_RENDER_MAX_LINES:
                                _lines_capped = True
                                continue
                            # Phase 2B: prefer full coords; fall back to coord_hint-only skip
                            _ch_coords = _child.get("coords")
                            if not isinstance(_ch_coords, list):
                                # Pre-2B child: no full coords available
                                continue
                            _capped = _cap_coords(_ch_coords)
                            if len(_capped) < 2:
                                continue
                            lines.append(
                                {
                                    "feature_id": f"{_fid}_ls",
                                    "coords": _capped,
                                    "classification": _cls,
                                    "name": _name,
                                    "color": _line_color or _KMZ_RENDER_DEFAULT_COLOR,
                                    "width": _line_width,
                                    "dash": _dash,
                                    "folder_path": _folder_path,
                                    **_common,
                                }
                            )
                            cat_counts[_cls]["line"] += 1
                        elif _ckind == "Polygon":
                            if len(polygons) >= _KMZ_RENDER_MAX_POLYGONS:
                                _polygons_capped = True
                                continue
                            # Phase 2B: prefer full outer; fall back to skip
                            _ch_outer = _child.get("outer")
                            if not isinstance(_ch_outer, list):
                                continue
                            _ch_outer_safe = _cap_coords(_ch_outer)
                            if len(_ch_outer_safe) < 3:
                                continue
                            _ch_inner = _cap_inner_rings(_child.get("inner"))
                            polygons.append(
                                {
                                    "feature_id": f"{_fid}_pg",
                                    "outer": _ch_outer_safe,
                                    "inner": _ch_inner,
                                    "classification": _cls,
                                    "name": _name,
                                    "fill_color": _poly_fill or _line_color or _KMZ_RENDER_DEFAULT_COLOR,
                                    "folder_path": _folder_path,
                                    **_common,
                                }
                            )
                            cat_counts[_cls]["polygon"] += 1
                continue

            _geom_kind = _geom.get("kind")

            if _geom_kind == "Point":
                if len(points) >= _KMZ_RENDER_MAX_POINTS:
                    _points_capped = True
                    continue
                _pt_coord = _geom.get("coord")
                if not isinstance(_pt_coord, (list, tuple)) or len(_pt_coord) < 2:
                    continue
                try:
                    _pt_lat = float(_pt_coord[0])
                    _pt_lon = float(_pt_coord[1])
                except (TypeError, ValueError):
                    continue
                points.append(
                    {
                        "feature_id": _fid,
                        "coord": [_pt_lat, _pt_lon],
                        "classification": _cls,
                        "name": _name,
                        "icon_glyph": _icon_glyph,
                        "color": _line_color or _KMZ_RENDER_DEFAULT_COLOR,
                        "folder_path": _folder_path,
                        **_common,
                    }
                )
                cat_counts[_cls]["point"] += 1

            elif _geom_kind == "LineString":
                if len(lines) >= _KMZ_RENDER_MAX_LINES:
                    _lines_capped = True
                    continue
                _ls_coords = _geom.get("coords")
                if not isinstance(_ls_coords, list) or len(_ls_coords) < 2:
                    continue
                _ls_capped = _cap_coords(_ls_coords)
                if len(_ls_capped) < 2:
                    continue
                lines.append(
                    {
                        "feature_id": _fid,
                        "coords": _ls_capped,
                        "classification": _cls,
                        "name": _name,
                        "color": _line_color or _KMZ_RENDER_DEFAULT_COLOR,
                        "width": _line_width,
                        "dash": _dash,
                        "folder_path": _folder_path,
                        **_common,
                    }
                )
                cat_counts[_cls]["line"] += 1

            elif _geom_kind == "Polygon":
                if len(polygons) >= _KMZ_RENDER_MAX_POLYGONS:
                    _polygons_capped = True
                    continue
                _pg_outer = _geom.get("outer")
                if not isinstance(_pg_outer, list) or len(_pg_outer) < 3:
                    continue
                _pg_outer_safe = _cap_coords(_pg_outer)
                if len(_pg_outer_safe) < 3:
                    continue
                # Phase 2B: extract inner rings for donut-hole rendering
                _pg_inner = _cap_inner_rings(_geom.get("inner"))
                polygons.append(
                    {
                        "feature_id": _fid,
                        "outer": _pg_outer_safe,
                        "inner": _pg_inner,
                        "classification": _cls,
                        "name": _name,
                        "fill_color": _poly_fill or _line_color or _KMZ_RENDER_DEFAULT_COLOR,
                        "folder_path": _folder_path,
                        **_common,
                    }
                )
                cat_counts[_cls]["polygon"] += 1

        # Build categories list sorted by total desc then classification asc
        categories: List[Dict[str, Any]] = []
        for _clas, _cnts in sorted(
            cat_counts.items(),
            key=lambda _kv: (-((_kv[1]["point"] + _kv[1]["line"] + _kv[1]["polygon"])), _kv[0]),
        ):
            _tot = _cnts["point"] + _cnts["line"] + _cnts["polygon"]
            if _tot == 0:
                continue
            categories.append(
                {
                    "classification": _clas,
                    "point_count": _cnts["point"],
                    "line_count": _cnts["line"],
                    "polygon_count": _cnts["polygon"],
                    "total": _tot,
                }
            )

        return {
            "schema_version": _KMZ_RENDER_PAYLOAD_SCHEMA,
            "generated_at": _generated_at,
            "render_caps": {
                "max_points": _KMZ_RENDER_MAX_POINTS,
                "max_lines": _KMZ_RENDER_MAX_LINES,
                "max_polygons": _KMZ_RENDER_MAX_POLYGONS,
                "max_vertices_per_line": _KMZ_RENDER_MAX_VERTICES_PER_LINE,
            },
            "points": points,
            "lines": lines,
            "polygons": polygons,
            "categories": categories,
            "summary": {
                "total_points": len(points),
                "total_lines": len(lines),
                "total_polygons": len(polygons),
                "points_truncated": _points_capped,
                "lines_truncated": _lines_capped,
                "polygons_truncated": _polygons_capped,
                "source_feature_count": source_feature_count,
            },
        }

    except Exception as _rp_exc:
        print(
            f"[KMZ_RENDER_PAYLOAD] WARNING: _build_kmz_render_payload failed: "
            f"{type(_rp_exc).__name__}: {_rp_exc}",
            flush=True,
        )
        return _empty


@localhost_router.get("/api/observability/kmz-render-payload")
def get_kmz_render_payload() -> JSONResponse:
    """Phase 2A — KMZ engineering render payload (read-only, compute-on-read).

    Schema version: "kmz-render-payload-1".

    Reads STATE["kmz_semantic"] and derives a capped, pre-styled payload
    for the frontend map KMZ context layer.

    No STATE writes.  No persistence.  No operational side effects.
    Always returns HTTP 200.

    USAGE POLICY:
    The render payload is advisory / display-only.  It MUST NOT influence
    matching, scoring, billing, closeout, or any operational pipeline.
    No operational consumer may depend on this endpoint being non-empty.
    """
    try:
        _sem = STATE.get("kmz_semantic")
        _result_rp = _build_kmz_render_payload(
            _sem if isinstance(_sem, dict) else None
        )
        return JSONResponse(_result_rp)
    except Exception as _rp_ep_exc:  # pragma: no cover
        print(
            f"[KMZ_RENDER_PAYLOAD] WARNING: endpoint failed: "
            f"{type(_rp_ep_exc).__name__}: {_rp_ep_exc}",
            flush=True,
        )
        from datetime import timezone as _tz_rp_err
        return JSONResponse(
            {
                "schema_version": _KMZ_RENDER_PAYLOAD_SCHEMA,
                "generated_at": datetime.now(_tz_rp_err.utc).isoformat(),
                "render_caps": {
                    "max_points": _KMZ_RENDER_MAX_POINTS,
                    "max_lines": _KMZ_RENDER_MAX_LINES,
                    "max_polygons": _KMZ_RENDER_MAX_POLYGONS,
                    "max_vertices_per_line": _KMZ_RENDER_MAX_VERTICES_PER_LINE,
                },
                "points": [],
                "lines": [],
                "polygons": [],
                "categories": [],
                "summary": {
                    "total_points": 0,
                    "total_lines": 0,
                    "total_polygons": 0,
                    "points_truncated": False,
                    "lines_truncated": False,
                    "polygons_truncated": False,
                    "source_feature_count": 0,
                },
            }
        )


@localhost_router.get("/api/observability/reviewed-snap-preview")
def get_reviewed_snap_preview() -> JSONResponse:
    """Phase 1W — reviewed snapped geometry preview (read-only, diagnostic).

    Schema version: "reviewed-snap-preview-1".

    Computes on-the-fly from:
      - STATE["redline_segments"]
      - STATE["endpoint_snap_recommendations"]
      - Phase 1U review event log (via _resolve_current_snap_review_decisions)

    No persistence.  No mutation of any STATE key.  No new geometry
    computation.  Endpoint coordinates are substituted from existing
    approved recommendations ONLY.

    Always returns HTTP 200.

    USAGE POLICY:
    Preview geometry is advisory only.  It MUST NOT be rendered into the
    operational map layer; it lives exclusively in the diagnostics panel.
    No operational consumer may depend on this endpoint being non-empty.
    """
    try:
        _segs_state = STATE.get("redline_segments")
        _recs_state = STATE.get("endpoint_snap_recommendations")
        _decisions_state = _resolve_current_snap_review_decisions()
        _result_pr = _build_reviewed_snap_preview(
            redline_segments=_segs_state if isinstance(_segs_state, list) else None,
            snap_recommendations=_recs_state if isinstance(_recs_state, dict) else None,
            decisions=_decisions_state,
        )
        return JSONResponse(_result_pr)
    except Exception as _pr_ep_exc:  # pragma: no cover
        print(
            f"[REVIEWED_SNAP_PREVIEW] WARNING: endpoint failed: "
            f"{type(_pr_ep_exc).__name__}: {_pr_ep_exc}",
            flush=True,
        )
        from datetime import timezone as _tz_pr_err
        return JSONResponse(
            {
                "schema_version": "reviewed-snap-preview-1",
                "generated_at": datetime.now(_tz_pr_err.utc).isoformat(),
                "previews": [],
                "summary": {
                    "total_previews": 0,
                    "previews_with_start_only": 0,
                    "previews_with_end_only": 0,
                    "previews_with_both": 0,
                    "stale_previews": 0,
                },
                "stability_note": _REVIEWED_SNAP_PREVIEW_STABILITY_NOTE,
            }
        )


@localhost_router.get("/api/observability/kmz-topology-sidecar")
def get_kmz_topology_sidecar() -> JSONResponse:
    """Phase 1O — KMZ topology sidecar (read-only, upload-scoped, diagnostic).

    Schema version: "kmz-topology-sidecar-1".

    Reads STATE["kmz_topology_sidecar"] directly.
    Returns the pre-built sidecar from the most recent upload_design call.
    If no upload has occurred, returns the empty skeleton.

    Always returns HTTP 200.  No writes.  No state mutations.
    No operational side effects.

    USAGE POLICY: See TOPOLOGY_SIDECAR_USAGE_POLICY.md.
    No operational consumer may depend on this endpoint being non-empty.
    """
    from datetime import timezone as _tz_sidecar

    _generated_at_sc = datetime.now(_tz_sidecar.utc).isoformat()
    try:
        _sidecar = STATE.get("kmz_topology_sidecar")
        if not isinstance(_sidecar, dict):
            # No upload yet or sidecar was cleared.
            _sidecar = _build_kmz_topology_sidecar(None, None)
        _result = dict(_sidecar)
        _result["generated_at"] = _generated_at_sc
        return JSONResponse(_result)
    except Exception as _sc_exc:
        print(
            f"[KMZ_TOPOLOGY_SIDECAR] WARNING: failed to serve sidecar: "
            f"{type(_sc_exc).__name__}: {_sc_exc}",
            flush=True,
        )
        _empty = _build_kmz_topology_sidecar(None, None)
        _empty["generated_at"] = _generated_at_sc
        return JSONResponse(_empty)


# ---------------------------------------------------------------------------
# Phase 1K — Ground Truth Review Labels (observability-only telemetry)
# ---------------------------------------------------------------------------

_REVIEW_LABEL_VALID_SET = frozenset({"useful_catch", "noise", "unclear", "cleared"})


def _append_review_label(
    match_pass_id: str,
    group_id: Optional[str],
    input_sha256: Optional[str],
    label: str,
    previous_label: Optional[str] = None,
    reviewer_hint: Optional[str] = None,
    note: Optional[str] = None,
    tombstone: bool = False,
) -> None:
    """Phase 1K — append one review-label telemetry event.

    Schema version: "review-label-1".  Mirrors ``_append_match_shadow_compare_entries``
    structure: append-only, tail-truncates at cap, never raises, prints warning
    on failure only.

    ISOLATION GUARANTEE: This function only writes to ``REVIEW_LABELS_PATH``.
    It NEVER reads or writes to any matching, scoring, or rendering subsystem.
    See ``LABEL_USAGE_POLICY.md``.
    """
    from datetime import timezone as _tz_rl

    try:
        row_rl: Dict[str, Any] = {
            "schema_version": "review-label-1",
            "labeled_at": datetime.now(_tz_rl.utc).isoformat(),
            "match_pass_id": str(match_pass_id) if match_pass_id else None,
            "group_id": str(group_id) if group_id is not None else None,
            "input_sha256": str(input_sha256) if input_sha256 is not None else None,
            "label": label,
            "previous_label": str(previous_label) if previous_label is not None else None,
            "reviewer_hint": str(reviewer_hint)[:200] if reviewer_hint is not None else None,
            "note": str(note)[:500] if note is not None else None,
            "tombstone": bool(tombstone),
        }

        with open(REVIEW_LABELS_PATH, "a", encoding="utf-8") as _fh_rl:
            _fh_rl.write(json.dumps(row_rl, separators=(",", ":")) + "\n")

        # Tail-truncate to cap — same pattern as other observability appenders.
        with open(REVIEW_LABELS_PATH, "r", encoding="utf-8") as _fh_rl:
            _all_lines_rl = _fh_rl.readlines()

        if len(_all_lines_rl) > REVIEW_LABELS_MAX_ROWS:
            _all_lines_rl = _all_lines_rl[-REVIEW_LABELS_MAX_ROWS:]
            with open(REVIEW_LABELS_PATH, "w", encoding="utf-8") as _fh_rl:
                _fh_rl.writelines(_all_lines_rl)

    except Exception as _rl_exc:  # pragma: no cover
        print(
            f"[REVIEW_LABELS] WARNING: failed to append review label: "
            f"{type(_rl_exc).__name__}: {_rl_exc}",
            flush=True,
        )


@localhost_router.post("/api/observability/review-labels")
def post_review_label(body: Dict[str, Any] = Body(default_factory=dict)) -> JSONResponse:
    """Phase 1K — append a review-label event (observability telemetry only).

    Schema version: "review-label-1".

    Accepted body keys:
      match_pass_id  — str (required, non-empty)
      group_id       — str | null
      input_sha256   — str | null
      label          — "useful_catch" | "noise" | "unclear" | "cleared"
      previous_label — str | null
      reviewer_hint  — str | null
      note           — str | null
      tombstone      — bool (default false)

    Always returns HTTP 200.
    Invalid or missing label → silent no-op, returns {"accepted": false, "label": null}.
    Missing or empty match_pass_id → silent no-op.
    No operational side effects of any kind.
    """
    if not isinstance(body, dict):
        return JSONResponse({"accepted": False, "label": None})

    label_rl = body.get("label")
    if label_rl not in _REVIEW_LABEL_VALID_SET:
        return JSONResponse({"accepted": False, "label": None})

    match_pass_id_rl = body.get("match_pass_id")
    if not match_pass_id_rl or not str(match_pass_id_rl).strip():
        return JSONResponse({"accepted": False, "label": None})

    _append_review_label(
        match_pass_id=str(match_pass_id_rl).strip(),
        group_id=body.get("group_id"),
        input_sha256=body.get("input_sha256"),
        label=str(label_rl),
        previous_label=body.get("previous_label"),
        reviewer_hint=body.get("reviewer_hint"),
        note=body.get("note"),
        tombstone=bool(body.get("tombstone", False)),
    )
    return JSONResponse({"accepted": True, "label": label_rl})


@localhost_router.get("/api/observability/review-labels")
def get_review_labels(limit: int = 100) -> JSONResponse:
    """Phase 1K — newest-first event log of all review-label events.

    Query param: ``limit`` (default 100, max 1000, min 1).
    Always returns HTTP 200.  Missing or corrupt file → {"events": []}.
    Read-only: no writes.
    """
    _limit_rl = max(1, min(limit, 1000))
    try:
        if not REVIEW_LABELS_PATH.exists():
            return JSONResponse({"events": []})
        with open(REVIEW_LABELS_PATH, "r", encoding="utf-8") as _fh_rl:
            _raw_rl = _fh_rl.readlines()
        _events_rl: List[Dict[str, Any]] = []
        for _line_rl in reversed(_raw_rl):
            _line_rl = _line_rl.strip()
            if not _line_rl:
                continue
            try:
                _events_rl.append(json.loads(_line_rl))
            except json.JSONDecodeError:
                continue
            if len(_events_rl) >= _limit_rl:
                break
        return JSONResponse({"events": _events_rl})
    except Exception as _rl_read_exc:
        print(
            f"[REVIEW_LABELS] WARNING: failed to read review-labels file: "
            f"{type(_rl_read_exc).__name__}: {_rl_read_exc}",
            flush=True,
        )
        return JSONResponse({"events": []})


@localhost_router.get("/api/observability/review-labels/current")
def get_review_labels_current(match_pass_id: str = Query("")) -> JSONResponse:
    """Phase 1K — latest-wins resolved labels for a given match_pass_id.

    Reads the full label log and returns the most-recent label per
    ``(match_pass_id, group_id)`` key.  Tombstoned entries are excluded from
    the result but still consume the "latest" slot (a tombstone clears a label).

    Query param: ``match_pass_id`` (required non-empty str).
    Always returns HTTP 200.  Missing file or empty match_pass_id → {"resolved": []}.
    Read-only: no writes.
    """
    _mpid_rl = str(match_pass_id).strip()
    if not _mpid_rl:
        return JSONResponse({"resolved": []})
    try:
        if not REVIEW_LABELS_PATH.exists():
            return JSONResponse({"resolved": []})
        with open(REVIEW_LABELS_PATH, "r", encoding="utf-8") as _fh_rl:
            _raw_rl = _fh_rl.readlines()

        # Collect all events for this pass in file order (oldest → newest).
        _events_for_pass_rl: List[Dict[str, Any]] = []
        for _line_rl in _raw_rl:
            _line_rl = _line_rl.strip()
            if not _line_rl:
                continue
            try:
                _ev_rl = json.loads(_line_rl)
            except json.JSONDecodeError:
                continue
            if _ev_rl.get("match_pass_id") == _mpid_rl:
                _events_for_pass_rl.append(_ev_rl)

        # Latest-write-wins per group_id (None is a valid key).
        _resolved_map_rl: Dict[Optional[str], Dict[str, Any]] = {}
        for _ev_rl in _events_for_pass_rl:
            _gid_key: Optional[str] = _ev_rl.get("group_id")
            _resolved_map_rl[_gid_key] = _ev_rl

        # Tombstoned entries are excluded from the visible result.
        _resolved_rl: List[Dict[str, Any]] = [
            {
                "group_id": _ev_rl.get("group_id"),
                "label": _ev_rl.get("label"),
                "labeled_at": _ev_rl.get("labeled_at"),
                "reviewer_hint": _ev_rl.get("reviewer_hint"),
                "note": _ev_rl.get("note"),
            }
            for _ev_rl in _resolved_map_rl.values()
            if not _ev_rl.get("tombstone", False)
        ]
        return JSONResponse({"resolved": _resolved_rl})

    except Exception as _rl_cur_exc:
        print(
            f"[REVIEW_LABELS] WARNING: failed to resolve current labels: "
            f"{type(_rl_cur_exc).__name__}: {_rl_cur_exc}",
            flush=True,
        )
        return JSONResponse({"resolved": []})


STATION_PHOTO_ROOT = UPLOADS_DIR / "station_photos"
STATION_PHOTO_INDEX_PATH = STATION_PHOTO_ROOT / "index.json"
STATION_PHOTO_MAX_FILES_PER_UPLOAD = 10
STATION_PHOTO_STORAGE = str(os.getenv("STATION_PHOTO_STORAGE") or "local").strip().lower()
S3_ENDPOINT_URL = str(os.getenv("S3_ENDPOINT_URL") or "").strip()
S3_REGION = str(os.getenv("S3_REGION") or "").strip() or "auto"
S3_BUCKET = str(os.getenv("S3_BUCKET") or "").strip()
S3_ACCESS_KEY_ID = str(os.getenv("S3_ACCESS_KEY_ID") or "").strip()
S3_SECRET_ACCESS_KEY = str(os.getenv("S3_SECRET_ACCESS_KEY") or "").strip()
S3_PUBLIC_BASE_URL = str(os.getenv("S3_PUBLIC_BASE_URL") or "").strip().rstrip("/")
_station_photo_s3_client: Optional[Any] = None


def _station_photo_use_s3() -> bool:
    return STATION_PHOTO_STORAGE == "s3"


def _station_photo_s3_required_missing() -> List[str]:
    missing: List[str] = []
    if not S3_ENDPOINT_URL:
        missing.append("S3_ENDPOINT_URL")
    if not S3_BUCKET:
        missing.append("S3_BUCKET")
    if not S3_ACCESS_KEY_ID:
        missing.append("S3_ACCESS_KEY_ID")
    if not S3_SECRET_ACCESS_KEY:
        missing.append("S3_SECRET_ACCESS_KEY")
    return missing


def _station_photo_get_s3_client():
    global _station_photo_s3_client
    if _station_photo_s3_client is not None:
        return _station_photo_s3_client

    missing = _station_photo_s3_required_missing()
    if missing:
        raise RuntimeError(f"Missing S3 config: {', '.join(missing)}")

    _station_photo_s3_client = boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT_URL,
        region_name=S3_REGION,
        aws_access_key_id=S3_ACCESS_KEY_ID,
        aws_secret_access_key=S3_SECRET_ACCESS_KEY,
    )
    return _station_photo_s3_client


def _station_photo_public_url_for_key(object_key: str) -> str:
    if S3_PUBLIC_BASE_URL:
        return f"{S3_PUBLIC_BASE_URL}/{quote(object_key)}"
    if not S3_ENDPOINT_URL or not S3_BUCKET:
        return ""
    return f"{S3_ENDPOINT_URL.rstrip('/')}/{S3_BUCKET}/{quote(object_key)}"


def _station_photo_record_public_url(record: Dict[str, Any]) -> Optional[str]:
    photo_id = str(record.get("photo_id") or "").strip()
    if photo_id:
        session_id = str(record.get("session_id") or "").strip()
        suffix = f"?session_id={quote(session_id)}" if session_id else ""
        return f"/api/station-photos/file/{photo_id}{suffix}"
    return None


def _station_photo_record_is_valid(record: Dict[str, Any]) -> bool:
    if str(record.get("public_url") or "").strip():
        return True
    stored_path = str(record.get("stored_path") or "").strip()
    return bool(stored_path and os.path.exists(stored_path))


def _ensure_station_photo_storage() -> None:
    STATION_PHOTO_ROOT.mkdir(parents=True, exist_ok=True)
    if not STATION_PHOTO_INDEX_PATH.exists():
        STATION_PHOTO_INDEX_PATH.write_text(json.dumps({"photos": []}, indent=2), encoding="utf-8")


def _load_station_photo_index() -> Dict[str, Any]:
    _ensure_station_photo_storage()
    try:
        data = json.loads(STATION_PHOTO_INDEX_PATH.read_text(encoding="utf-8"))
    except Exception:
        data = {"photos": []}
    if not isinstance(data, dict):
        data = {"photos": []}
    photos = data.get("photos")
    if not isinstance(photos, list):
        data["photos"] = []
    return data


def _save_station_photo_index(index_data: Dict[str, Any]) -> None:
    _ensure_station_photo_storage()
    temp_path = STATION_PHOTO_INDEX_PATH.with_suffix(".tmp")
    temp_path.write_text(json.dumps(index_data, indent=2), encoding="utf-8")
    temp_path.replace(STATION_PHOTO_INDEX_PATH)


def _safe_photo_name(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "file"
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in raw)
    cleaned = cleaned.strip("._")
    return cleaned or "file"


def _station_photo_identity_raw(
    route_name: Any,
    source_file: Any,
    station_label: Any,
    mapped_station_ft: Any,
    lat: Any,
    lon: Any,
) -> str:
    key_parts = [
        str(route_name or "").strip(),
        str(source_file or "").strip(),
        str(station_label or "").strip(),
        str(mapped_station_ft or "").strip(),
        str(lat or "").strip(),
        str(lon or "").strip(),
    ]
    return "|".join(key_parts)


def _station_photo_identity_hash(raw_identity: Any, session_id: Optional[str] = None) -> str:
    raw = str(raw_identity or "").strip()
    if not raw:
        return ""
    scoped_raw = f"{str(session_id or '').strip()}|{raw}" if session_id else raw
    return hashlib.sha256(scoped_raw.encode("utf-8")).hexdigest()


def _station_photo_record_matches_session(record: Dict[str, Any], session_id: str) -> bool:
    return str(record.get("session_id") or "").strip() == str(session_id or "").strip()


def _station_photo_folder(station_identity_hash: str) -> Path:
    return STATION_PHOTO_ROOT / station_identity_hash


def _station_photo_public_record(record: Dict[str, Any]) -> Dict[str, Any]:
    photo_id = str(record.get("photo_id") or "").strip()
    session_id = str(record.get("session_id") or "").strip()
    session_query = f"?session_id={quote(session_id)}" if session_id else ""
    adjusted_lat = _office_float_or_none(record.get("adjusted_lat"))
    adjusted_lon = _office_float_or_none(record.get("adjusted_lon"))
    is_adjusted = adjusted_lat is not None and adjusted_lon is not None
    return {
        "photo_id": photo_id,
        "session_id": session_id,
        "station_identity": str(record.get("station_identity") or ""),
        "station_summary": str(record.get("station_summary") or ""),
        "original_filename": str(record.get("original_filename") or ""),
        "stored_filename": str(record.get("stored_filename") or ""),
        "content_type": str(record.get("content_type") or ""),
        "uploaded_at": str(record.get("uploaded_at") or ""),
        "relative_url": f"/api/station-photos/file/{photo_id}{session_query}",
        "public_url": str(record.get("public_url") or ""),
        "original_lat": _office_float_or_none(record.get("lat")),
        "original_lon": _office_float_or_none(record.get("lon")),
        "adjusted_lat": adjusted_lat,
        "adjusted_lon": adjusted_lon,
        "adjusted_at": str(record.get("adjusted_at") or "") or None,
        "is_adjusted": is_adjusted,
    }


@protected_router.get("/api/station-photos")
async def get_station_photos(station_identity: str, session_id: Optional[str] = None) -> JSONResponse:
    resolved_session_id = _resolve_session_id(session_id)
    station_identity_raw = str(station_identity or "").strip()
    if not station_identity_raw:
        return _err("station_identity is required.", session_id=resolved_session_id)
    station_identity_hash = _station_photo_identity_hash(station_identity_raw, resolved_session_id)
    index_data = _load_station_photo_index()
    matches = [
        _station_photo_public_record(record)
        for record in index_data.get("photos", [])
        if _station_photo_record_matches_session(record, resolved_session_id)
        and str(record.get("station_identity_hash") or "").strip() == station_identity_hash
    ]
    matches.sort(key=lambda item: str(item.get("uploaded_at") or ""), reverse=True)
    return _ok(
        session_id=resolved_session_id,
        photos=matches,
        station_identity=station_identity_raw,
        station_identity_hash=station_identity_hash,
    )


@protected_router.post("/api/station-photos/upload")
async def upload_station_photos(
    station_identity: str = Form(...),
    session_id: Optional[str] = Form(None),
    station_summary: str = Form(""),
    route_name: str = Form(""),
    source_file: str = Form(""),
    station_label: str = Form(""),
    mapped_station_ft: str = Form(""),
    lat: str = Form(""),
    lon: str = Form(""),
    files: List[UploadFile] = File(...),
) -> JSONResponse:
    resolved_session_id = _resolve_session_id(session_id)
    station_identity_raw = str(station_identity or "").strip()
    if not station_identity_raw:
        return _err("station_identity is required.", session_id=resolved_session_id)

    expected_identity_raw = _station_photo_identity_raw(
        route_name, source_file, station_label, mapped_station_ft, lat, lon
    )
    if station_identity_raw != expected_identity_raw:
        return _err("Selected station identity did not match the upload payload.", session_id=resolved_session_id)

    station_identity_hash = _station_photo_identity_hash(station_identity_raw, resolved_session_id)

    upload_files = list(files or [])
    if not upload_files:
        return _err("At least one image file is required.", session_id=resolved_session_id)
    if len(upload_files) > STATION_PHOTO_MAX_FILES_PER_UPLOAD:
        return _err(f"Upload up to {STATION_PHOTO_MAX_FILES_PER_UPLOAD} files at a time.", session_id=resolved_session_id)

    with _session_scope(resolved_session_id):
        if _is_closeout_locked():
            return _json_closeout_locked_response()

    _ensure_station_photo_storage()
    station_folder = _station_photo_folder(station_identity_hash)
    if not _station_photo_use_s3():
        station_folder.mkdir(parents=True, exist_ok=True)

    index_data = _load_station_photo_index()
    photo_records: List[Dict[str, Any]] = index_data.setdefault("photos", [])

    created: List[Dict[str, Any]] = []
    for upload in upload_files:
        original_filename = _safe_photo_name(upload.filename or "image")
        content_type = str(upload.content_type or "").strip().lower()
        if content_type and not content_type.startswith("image/"):
            return _err(f"{original_filename} is not an image upload.")

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        extension = Path(original_filename).suffix or ""
        photo_id = hashlib.sha256(
            f"{station_identity_hash}|{original_filename}|{timestamp}".encode("utf-8")
        ).hexdigest()[:24]
        stored_filename = f"{timestamp}_{photo_id}{extension}"
        stored_path = station_folder / stored_filename
        object_key = f"station_photos/{station_identity_hash}/{stored_filename}"
        public_url = ""

        file_bytes = await upload.read()
        if _station_photo_use_s3():
            s3 = _station_photo_get_s3_client()
            put_kwargs: Dict[str, Any] = {
                "Bucket": S3_BUCKET,
                "Key": object_key,
                "Body": file_bytes,
            }
            if content_type:
                put_kwargs["ContentType"] = content_type
            s3.put_object(**put_kwargs)
            public_url = _station_photo_public_url_for_key(object_key)
        else:
            with open(stored_path, "wb") as handle:
                handle.write(file_bytes)

        record = {
            "photo_id": photo_id,
            "session_id": resolved_session_id,
            "station_identity": station_identity_raw,
            "station_identity_hash": station_identity_hash,
            "station_summary": str(station_summary or "").strip(),
            "route_name": str(route_name or "").strip(),
            "source_file": str(source_file or "").strip(),
            "station_label": str(station_label or "").strip(),
            "mapped_station_ft": str(mapped_station_ft or "").strip(),
            "lat": str(lat or "").strip(),
            "lon": str(lon or "").strip(),
            "original_filename": original_filename,
            "stored_filename": stored_filename,
            "stored_path": str(stored_path) if not _station_photo_use_s3() else "",
            "object_key": object_key if _station_photo_use_s3() else "",
            "public_url": public_url,
            "storage": "s3" if _station_photo_use_s3() else "local",
            "content_type": content_type,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }
        photo_records.append(record)
        created.append(_station_photo_public_record(record))

    _save_station_photo_index(index_data)
    return _ok(
        session_id=resolved_session_id,
        message=f"Uploaded {len(created)} station photo{'s' if len(created) != 1 else ''}.",
        station_identity=station_identity_raw,
        station_identity_hash=station_identity_hash,
        photos=created,
    )


@protected_router.get("/api/station-photos/file/{photo_id}")
async def get_station_photo_file(photo_id: str, session_id: Optional[str] = None):
    resolved_session_id = _resolve_session_id(session_id)
    target = str(photo_id or "").strip()
    if not target:
        return _err("photo_id is required.", session_id=resolved_session_id)
    index_data = _load_station_photo_index()
    for record in index_data.get("photos", []):
        if str(record.get("photo_id") or "").strip() != target:
            continue
        if not _station_photo_record_matches_session(record, resolved_session_id):
            continue
        public_url = str(record.get("public_url") or "").strip()
        if public_url:
            return RedirectResponse(url=public_url, status_code=307)
        stored_path = str(record.get("stored_path") or "").strip()
        if not stored_path or not os.path.exists(stored_path):
            return _err("Photo file was not found.", status_code=404, session_id=resolved_session_id)
        content_type = str(record.get("content_type") or "").strip() or None
        return FileResponse(
            stored_path,
            media_type=content_type,
            filename=str(record.get("original_filename") or os.path.basename(stored_path)),
        )
    return _err("Photo file was not found.", status_code=404, session_id=resolved_session_id)


@protected_router.post("/api/station-photos/{photo_id}/adjust")
async def adjust_station_photo(
    photo_id: str,
    payload: Dict[str, Any] = Body(...),
    session_id: Optional[str] = None,
) -> JSONResponse:
    resolved_session_id = _resolve_session_id(session_id)
    target = str(photo_id or "").strip()
    if not target:
        return _err("photo_id is required.", session_id=resolved_session_id)

    adjusted_lat_raw = payload.get("adjusted_lat")
    adjusted_lon_raw = payload.get("adjusted_lon")

    clear_adjustment = adjusted_lat_raw is None and adjusted_lon_raw is None
    if not clear_adjustment:
        if adjusted_lat_raw is None or adjusted_lon_raw is None:
            return _err(
                "adjusted_lat and adjusted_lon must both be numbers or both be null.",
                session_id=resolved_session_id,
            )
        try:
            adjusted_lat = float(adjusted_lat_raw)
            adjusted_lon = float(adjusted_lon_raw)
        except (TypeError, ValueError):
            return _err(
                "adjusted_lat and adjusted_lon must be valid numbers.",
                session_id=resolved_session_id,
            )
        if not (-90.0 <= adjusted_lat <= 90.0):
            return _err("adjusted_lat must be between -90 and 90.", session_id=resolved_session_id)
        if not (-180.0 <= adjusted_lon <= 180.0):
            return _err("adjusted_lon must be between -180 and 180.", session_id=resolved_session_id)

    with _session_scope(resolved_session_id):
        if _is_closeout_locked():
            return _json_closeout_locked_response()

    index_data = _load_station_photo_index()
    records = index_data.get("photos")
    if not isinstance(records, list):
        return _err("Photo index is malformed.", status_code=500, session_id=resolved_session_id)

    updated_record: Optional[Dict[str, Any]] = None
    for record in records:
        if not isinstance(record, dict):
            continue
        if str(record.get("photo_id") or "").strip() != target:
            continue
        if not _station_photo_record_matches_session(record, resolved_session_id):
            continue
        if clear_adjustment:
            record.pop("adjusted_lat", None)
            record.pop("adjusted_lon", None)
            record.pop("adjusted_at", None)
        else:
            record["adjusted_lat"] = adjusted_lat
            record["adjusted_lon"] = adjusted_lon
            record["adjusted_at"] = datetime.now(timezone.utc).isoformat()
        updated_record = record
        break

    if not updated_record:
        return _err("Photo was not found.", status_code=404, session_id=resolved_session_id)

    _save_station_photo_index(index_data)
    return _ok(
        session_id=resolved_session_id,
        message="Photo adjustment updated.",
        photo=_station_photo_public_record(updated_record),
    )


# ---------------------------------------------------------------------------
# Engineering Plan Evidence Upload
# Scoped by session_id. Stores PDF/PNG/JPG/JPEG files as job evidence.
# Does NOT affect route matching or redline decisions (V1 — evidence layer only).
# ---------------------------------------------------------------------------

ENGINEERING_PLAN_ROOT = UPLOADS_DIR / "engineering_plans"
ENGINEERING_PLAN_INDEX_PATH = ENGINEERING_PLAN_ROOT / "index.json"

NOVA_OVERRIDES_ROOT = UPLOADS_DIR / "nova_overrides"
NOVA_OVERRIDES_INDEX_PATH = NOVA_OVERRIDES_ROOT / "index.json"
ENGINEERING_PLAN_ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}
ENGINEERING_PLAN_MAX_FILES_PER_UPLOAD = 20


# ── Nova override persistence helpers ────────────────────────────────────────

def _ensure_nova_overrides_storage() -> None:
    NOVA_OVERRIDES_ROOT.mkdir(parents=True, exist_ok=True)
    if not NOVA_OVERRIDES_INDEX_PATH.exists():
        NOVA_OVERRIDES_INDEX_PATH.write_text(json.dumps({"overrides": []}, indent=2), encoding="utf-8")


def _load_nova_overrides_index() -> Dict[str, Any]:
    _ensure_nova_overrides_storage()
    try:
        data = json.loads(NOVA_OVERRIDES_INDEX_PATH.read_text(encoding="utf-8"))
    except Exception:
        data = {"overrides": []}
    if not isinstance(data.get("overrides"), list):
        data["overrides"] = []
    return data


def _save_nova_overrides_index(data: Dict[str, Any]) -> None:
    _ensure_nova_overrides_storage()
    temp_path = NOVA_OVERRIDES_INDEX_PATH.with_suffix(".tmp")
    temp_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    temp_path.replace(NOVA_OVERRIDES_INDEX_PATH)


def _clear_nova_overrides_for_session(session_id: str) -> None:
    """Remove all Nova override records belonging to session_id. Non-fatal."""
    if not str(session_id or "").strip():
        return
    try:
        data = _load_nova_overrides_index()
        sid = str(session_id).strip()
        data["overrides"] = [
            r for r in data["overrides"]
            if str(r.get("session_id") or "").strip() != sid
        ]
        _save_nova_overrides_index(data)
    except Exception:
        pass  # non-fatal — workspace state resets even if disk cleanup fails


# ── Engineering plan storage helpers ────────────────────────────��────────────

def _ensure_engineering_plan_storage() -> None:
    ENGINEERING_PLAN_ROOT.mkdir(parents=True, exist_ok=True)
    if not ENGINEERING_PLAN_INDEX_PATH.exists():
        ENGINEERING_PLAN_INDEX_PATH.write_text(json.dumps({"plans": []}, indent=2), encoding="utf-8")


def _load_engineering_plan_index() -> Dict[str, Any]:
    _ensure_engineering_plan_storage()
    try:
        data = json.loads(ENGINEERING_PLAN_INDEX_PATH.read_text(encoding="utf-8"))
    except Exception:
        data = {"plans": []}
    plans = data.get("plans")
    if not isinstance(plans, list):
        data["plans"] = []
    return data


def _save_engineering_plan_index(index_data: Dict[str, Any]) -> None:
    _ensure_engineering_plan_storage()
    temp_path = ENGINEERING_PLAN_INDEX_PATH.with_suffix(".tmp")
    temp_path.write_text(json.dumps(index_data, indent=2), encoding="utf-8")
    temp_path.replace(ENGINEERING_PLAN_INDEX_PATH)


def _engineering_plan_record_matches_session(record: Dict[str, Any], session_id: str) -> bool:
    return str(record.get("session_id") or "").strip() == str(session_id or "").strip()


def _engineering_plan_public_record(record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "plan_id": record.get("plan_id"),
        "session_id": record.get("session_id"),
        "original_filename": record.get("original_filename"),
        "stored_filename": record.get("stored_filename"),
        "file_type": record.get("file_type"),
        "size_bytes": record.get("size_bytes"),
        "uploaded_at": record.get("uploaded_at"),
        "plan_date": record.get("plan_date"),
        "print_numbers": record.get("print_numbers"),
        "sheet_numbers": record.get("sheet_numbers"),
        "street_hints": record.get("street_hints"),
        "notes": record.get("notes"),
    }


def _load_engineering_plan_index_for_session(session_id: str) -> List[Dict[str, Any]]:
    if not session_id:
        return []
    try:
        index_data = _load_engineering_plan_index()
        return [
            _engineering_plan_public_record(r)
            for r in index_data.get("plans", [])
            if _engineering_plan_record_matches_session(r, session_id)
        ]
    except Exception:
        return []


@protected_router.post("/api/upload-engineering-plans")
async def upload_engineering_plans(
    files: List[UploadFile] = File(...),
    session_id: Optional[str] = Form(None),
    plan_date: Optional[str] = Form(None),
    print_numbers: Optional[str] = Form(None),
    sheet_numbers: Optional[str] = Form(None),
    street_hints: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
) -> JSONResponse:
    resolved_session_id = _resolve_session_id(session_id)

    if not files:
        return _err("At least one file is required.", session_id=resolved_session_id)
    if len(files) > ENGINEERING_PLAN_MAX_FILES_PER_UPLOAD:
        return _err(
            f"Upload up to {ENGINEERING_PLAN_MAX_FILES_PER_UPLOAD} files at a time.",
            session_id=resolved_session_id,
        )

    with _session_scope(resolved_session_id):
        if _is_closeout_locked():
            return _json_closeout_locked_response()

    _ensure_engineering_plan_storage()
    session_folder = ENGINEERING_PLAN_ROOT / _safe_filename(resolved_session_id)
    session_folder.mkdir(parents=True, exist_ok=True)

    index_data = _load_engineering_plan_index()
    plan_records: List[Dict[str, Any]] = index_data.setdefault("plans", [])

    created: List[Dict[str, Any]] = []
    timestamp = int(datetime.utcnow().timestamp() * 1000)

    for upload in files:
        original_filename = _safe_filename(upload.filename or "plan")
        extension = Path(original_filename).suffix.lower()

        if extension not in ENGINEERING_PLAN_ALLOWED_EXTENSIONS:
            continue  # skip unsupported files silently

        file_bytes = await upload.read()
        size_bytes = len(file_bytes)

        plan_id = hashlib.sha256(
            f"{resolved_session_id}|{original_filename}|{timestamp}|{size_bytes}".encode()
        ).hexdigest()[:24]

        stored_filename = f"{timestamp}_{plan_id}{extension}"
        stored_path = session_folder / stored_filename
        stored_path.write_bytes(file_bytes)

        mime_map = {
            ".pdf": "application/pdf",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
        }

        record: Dict[str, Any] = {
            "plan_id": plan_id,
            "session_id": resolved_session_id,
            "original_filename": original_filename,
            "stored_filename": stored_filename,
            "stored_path": str(stored_path),
            "file_type": mime_map.get(extension, "application/octet-stream"),
            "size_bytes": size_bytes,
            "uploaded_at": datetime.utcnow().isoformat() + "Z",
            "plan_date": (plan_date or "").strip() or None,
            "print_numbers": (print_numbers or "").strip() or None,
            "sheet_numbers": (sheet_numbers or "").strip() or None,
            "street_hints": (street_hints or "").strip() or None,
            "notes": (notes or "").strip() or None,
        }
        plan_records.append(record)
        created.append(_engineering_plan_public_record(record))

    _save_engineering_plan_index(index_data)

    # If bore logs are already loaded for this session, rebuild the pipeline so
    # plan signals and plan-aware bias/ambiguity classification reflect the new plans.
    # Non-fatal: a rebuild failure leaves bore log data intact.
    with _session_scope(resolved_session_id):
        if STATE.get("committed_rows"):
            try:
                _rebuild_field_data_outputs()
            except Exception:
                pass  # non-fatal — committed_rows and redline data remain unchanged

    all_session_plans = _load_engineering_plan_index_for_session(resolved_session_id)

    return _ok(
        session_id=resolved_session_id,
        message=f"Uploaded {len(created)} engineering plan file{'s' if len(created) != 1 else ''}.",
        uploaded=created,
        engineering_plans=all_session_plans,
    )


@protected_router.get("/api/engineering-plans")
async def get_engineering_plans(session_id: Optional[str] = None) -> JSONResponse:
    resolved_session_id = _resolve_session_id(session_id)
    plans = _load_engineering_plan_index_for_session(resolved_session_id)
    return _ok(session_id=resolved_session_id, engineering_plans=plans)


# ── Nova override decision endpoints ─────────────────────────────────────────

@protected_router.get("/api/nova-overrides")
def get_nova_overrides(session_id: Optional[str] = None) -> JSONResponse:
    """Return all persisted Nova QA override decisions for this session."""
    resolved_session_id = _resolve_session_id(session_id)
    if not str(session_id or "").strip():
        # No session provided — return empty rather than minting a new session.
        return JSONResponse(content={"success": True, "session_id": None, "overrides": []})
    try:
        data = _load_nova_overrides_index()
        sid = resolved_session_id.strip()
        session_overrides = [
            r for r in data.get("overrides", [])
            if str(r.get("session_id") or "").strip() == sid
        ]
    except Exception:
        session_overrides = []
    return JSONResponse(content={
        "success": True,
        "session_id": resolved_session_id,
        "overrides": session_overrides,
    })


@protected_router.post("/api/nova-overrides")
def save_nova_override(
    payload: Dict[str, Any] = Body(...),
    session_id: Optional[str] = None,
) -> JSONResponse:
    """Upsert one Nova QA override decision (matched by id + session_id)."""
    body_session_id = payload.get("session_id") if isinstance(payload, dict) else None
    resolved_session_id = _resolve_session_id(session_id or body_session_id)

    with _session_scope(resolved_session_id):
        if _is_closeout_locked():
            return _json_closeout_locked_response()

    issue_key = str(payload.get("issue_key") or "").strip()
    decision  = str(payload.get("decision") or "").strip()
    reason    = str(payload.get("reason") or "").strip()

    if not issue_key:
        return _err("issue_key is required.", session_id=resolved_session_id)
    if not decision:
        return _err("decision is required.", session_id=resolved_session_id)
    if not reason:
        return _err("reason is required.", session_id=resolved_session_id)
    if decision not in ("Reviewed", "Accepted Override", "Needs Rework"):
        return _err(f"Invalid decision value: {decision!r}.", session_id=resolved_session_id)

    record: Dict[str, Any] = {
        "id":          str(payload.get("id") or issue_key),
        "session_id":  resolved_session_id,
        "source_file": str(payload.get("source_file") or ""),
        "group_idx":   payload.get("group_idx"),
        "issue_key":   issue_key,
        "decision":    decision,
        "reason":      reason,
        "created_by":  str(payload.get("created_by") or "unknown"),
        "role":        str(payload.get("role") or ""),
        "created_at":  str(payload.get("created_at") or ""),
    }

    try:
        data = _load_nova_overrides_index()
        overrides = data.get("overrides", [])
        upserted = False
        for i, r in enumerate(overrides):
            if (
                str(r.get("id") or "") == record["id"]
                and str(r.get("session_id") or "").strip() == resolved_session_id.strip()
            ):
                overrides[i] = record
                upserted = True
                break
        if not upserted:
            overrides.append(record)
        data["overrides"] = overrides
        _save_nova_overrides_index(data)
    except Exception as exc:
        return _err(f"Failed to persist override: {exc}", session_id=resolved_session_id)

    return JSONResponse(content={
        "success": True,
        "session_id": resolved_session_id,
        "override": record,
    })


@protected_router.delete("/api/nova-overrides/{issue_id}")
def delete_nova_override(
    issue_id: str,
    session_id: Optional[str] = None,
) -> JSONResponse:
    """Remove one Nova override by id, scoped to the caller's session."""
    resolved_session_id = _resolve_session_id(session_id)
    with _session_scope(resolved_session_id):
        if _is_closeout_locked():
            return _json_closeout_locked_response()
    try:
        data = _load_nova_overrides_index()
        before = len(data.get("overrides", []))
        data["overrides"] = [
            r for r in data.get("overrides", [])
            if not (
                str(r.get("id") or "") == issue_id
                and str(r.get("session_id") or "").strip() == resolved_session_id.strip()
            )
        ]
        _save_nova_overrides_index(data)
        removed = before - len(data["overrides"])
    except Exception as exc:
        return _err(f"Failed to delete override: {exc}", session_id=resolved_session_id)
    return JSONResponse(content={
        "success": True,
        "session_id": resolved_session_id,
        "removed": removed,
    })


def _closeout_lock_user_from_payload(payload: Any) -> str:
    if not isinstance(payload, dict):
        return "unknown"
    u = str(payload.get("user") or payload.get("locked_by") or "").strip()
    return u or "unknown"


def _closeout_unlock_role_from_payload(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("role") or "").strip()


@protected_router.post("/api/closeout/lock")
@protected_router.post("/closeout/lock")
@protected_router.post("/api/jobs/{job_id}/lock-closeout")
def api_closeout_lock(
    job_id: Optional[str] = None,
    payload: Dict[str, Any] = Body(default_factory=dict),
    session_id: Optional[str] = None,
) -> JSONResponse:
    body_sid = payload.get("session_id") if isinstance(payload, dict) else None
    resolved = _resolve_session_id(session_id or body_sid)
    user = _closeout_lock_user_from_payload(payload)
    with _session_scope(resolved):
        cur = _normalize_closeout_lock(STATE.get("closeout_lock"))
        if cur.get("is_locked"):
            _set_closeout_lock_state(
                True,
                cur.get("locked_by"),
                cur.get("locked_at"),
            )
            return JSONResponse(
                content={
                    "success": True,
                    "message": "Already locked",
                    "session_id": resolved,
                    "closeout_lock": cur,
                    **_closeout_flat_fields(),
                }
            )
        nxt = _set_closeout_lock_state(
            True,
            user,
            datetime.now(timezone.utc).isoformat(),
        )
        return JSONResponse(
            content={
                "success": True,
                "session_id": resolved,
                "closeout_lock": nxt,
                **_closeout_flat_fields(),
            }
        )


@protected_router.post("/api/closeout/unlock")
@protected_router.post("/closeout/unlock")
@protected_router.post("/api/jobs/{job_id}/unlock-closeout")
def api_closeout_unlock(
    job_id: Optional[str] = None,
    payload: Dict[str, Any] = Body(default_factory=dict),
    session_id: Optional[str] = None,
) -> JSONResponse:
    body_sid = payload.get("session_id") if isinstance(payload, dict) else None
    resolved = _resolve_session_id(session_id or body_sid)
    role = _closeout_unlock_role_from_payload(payload).lower()
    if role not in ("admin", "manager"):
        return JSONResponse(
            status_code=403,
            content={
                "success": False,
                "error": "Only admin or manager can unlock closeout.",
                "session_id": resolved,
            },
        )
    with _session_scope(resolved):
        unlocked = _set_closeout_lock_state(False, None, None)
        return JSONResponse(
            content={
                "success": True,
                "session_id": resolved,
                "closeout_lock": unlocked,
                **_closeout_flat_fields(),
            }
        )


# ── Nova Chat — deterministic read-only copilot ───────────────────────────────
# Answers questions about the current job using session STATE + persisted overrides.
# Phase 3.1: conversational context + natural prose answers + vague follow-up resolution.
# No external API calls. No STATE mutation. No file writes.

def _nc_short_file(source_file: str) -> str:
    """Return just the filename portion of a source_file path."""
    name = str(source_file or "")
    for sep in ("/", "\\"):
        if sep in name:
            name = name.rsplit(sep, 1)[-1]
    return name or str(source_file or "unknown")


def _nc_intent(question: str) -> str:
    """
    Classify the question into one of six intents.
    Priority order: source_file > override > plan > next_action > blocked_readiness > general.
    """
    q = question.lower()

    # Source-file specific: match bore_log patterns or bare filenames mentioned.
    if re.search(r"bore[_\s\-]?log[_\s\-]?\d+|bore_log\w+|[a-z0-9_]+\.(?:csv|xlsx|xls)", q):
        return "source_file"

    if any(k in q for k in [
        "override", "overridden", "overrode", "reviewed", "rework",
        "decision", "accepted override", "approve", "approved",
    ]):
        return "override"

    if any(k in q for k in ["plan", "engineering plan", "design plan", "sheet", "signal"]):
        return "plan"

    if any(k in q for k in [
        "next", "what to do", "what do i", "what should", "what need",
        "action", "step", "before billing", "before closeout",
    ]):
        return "next_action"

    if any(k in q for k in [
        "block", "billing", "bill", "ready", "readiness", "closeout",
        "why", "stop", "prevent", "issue", "problem", "can i", "status",
        "what is wrong", "what's wrong",
    ]):
        return "blocked_readiness"

    return "general"


def _nc_is_vague_followup(question: str) -> bool:
    """
    Detect if the question is a vague follow-up that needs recent context to resolve.
    Returns True for phrases like "what does that mean?", "how do I fix it?", "is that bad?"
    """
    q = question.lower().strip().rstrip("?.")

    VAGUE_PATTERNS = [
        "what does that mean", "what does this mean", "what do you mean",
        "what does it mean",
        "how do i fix it", "how do i fix that", "how to fix it", "how to fix that",
        "how do i resolve it", "how do i resolve that",
        "how do i deal with it", "how do i deal with that",
        "what do i do about it", "what do i do about that",
        "what do i do", "what should i do",
        "is that bad", "is this bad", "should i worry", "how bad is that",
        "explain that", "explain this", "explain it",
        "can you explain", "tell me more", "more detail", "can you elaborate",
        "what now", "and then what", "what next",
        "why is that", "why does that happen", "what causes that",
    ]
    for pattern in VAGUE_PATTERNS:
        if pattern in q:
            return True

    # Short questions (< 35 chars) containing vague pronouns but no specific filename
    if len(q) < 35 and any(p in q.split() for p in ["that", "this", "it", "those", "these"]):
        if not re.search(r"bore[_\s\-]?log[_\s\-]?\d+|[a-z0-9_]+\.(?:csv|xlsx|xls)", q):
            return True

    return False


def _nc_infer_context(
    recent_messages: List[Dict[str, Any]],
    pipeline_diag: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Extract conversational context from recent chat history.
    Returns {"source_file": str|None, "last_intent": str|None}.
    Scans messages most-recent-first so the latest reference wins.
    """
    all_short = list(dict.fromkeys(
        _nc_short_file(d.get("source_file") or "")
        for d in pipeline_diag
        if d.get("source_file")
    ))

    source_file: Optional[str] = None
    last_intent: Optional[str] = None

    for msg in reversed(recent_messages):
        content = str(msg.get("content") or "").lower()
        role    = str(msg.get("role") or "")

        # Extract a referenced source file from either role's message.
        if not source_file and all_short:
            for fname in all_short:
                fname_key    = re.sub(r"[_\-\s]", "", fname.lower()).replace(".csv", "").replace(".xlsx", "")
                content_key  = re.sub(r"[_\-\s]", "", content)
                if fname_key and fname_key in content_key:
                    source_file = fname
                    break
            if not source_file:
                m = re.search(r"bore[_\s\-]?log[_\s\-]?(\d+)", content)
                if m:
                    num = m.group(1)
                    for fname in all_short:
                        if num in fname:
                            source_file = fname
                            break

        # Extract last intent from the most recent user message.
        if not last_intent and role == "user":
            candidate = _nc_intent(content)
            if candidate != "general":
                last_intent = candidate

    return {"source_file": source_file, "last_intent": last_intent}


def _nc_blocked_answer(
    pipeline_diag: List[Dict[str, Any]],
    overrides: List[Dict[str, Any]],
) -> str:
    stopped     = [d for d in pipeline_diag
                   if d.get("stopped_at") and d.get("stopped_at") != "render_gate_blocked"]
    blocked     = [d for d in pipeline_diag if not d.get("render_allowed", True)]
    render_only = [d for d in blocked if d not in stopped]
    rendered    = [d for d in pipeline_diag if d.get("render_allowed") is True]
    rework      = [o for o in overrides if o.get("decision") == "Needs Rework"]

    if not pipeline_diag:
        return "Upload a KMZ and structured bore logs to generate job intelligence."

    if not stopped and not blocked and not rework:
        return (
            f"No blocking issues — {len(rendered)} group(s) rendered successfully. "
            "This job is ready for closeout review. "
            "Verify billing footage and exceptions before closing out."
        )

    problem_files = list(dict.fromkeys(
        _nc_short_file(d.get("source_file") or "")
        for d in stopped + blocked
    ))
    n_files = len(problem_files)
    n_groups = len(stopped) + len(render_only)

    opening = (
        f"This job isn't ready for billing review. "
        f"{n_groups} group(s) across {n_files} file(s) didn't complete routing."
    )

    details: List[str] = []
    _STOP_MAP = {
        "no_rankings_after_all_passes":
            "no matching route was found — station points may not align with any route in the KMZ",
        "no_anchored_hypotheses":
            "route alignment couldn't be confirmed — station spacing didn't match any candidate",
    }
    for d in (stopped + render_only)[:5]:
        f        = _nc_short_file(d.get("source_file") or "")
        sa       = d.get("stopped_at") or ""
        blk_rsns = list(d.get("render_block_reasons") or [])
        if sa and sa != "render_gate_blocked":
            msg = _STOP_MAP.get(sa) or f"stopped at '{sa}'"
            details.append(f"• {f}: {msg}.")
        elif blk_rsns:
            details.append(f"• {f}: blocked — {blk_rsns[0]}.")
        else:
            details.append(f"• {f}: blocked at render gate.")

    rework_note = ""
    if rework:
        rework_note = (
            f"\n{len(rework)} item(s) also marked 'Needs Rework' by a reviewer, "
            "which keeps them blocked until addressed."
        )

    closing = (
        "To move forward, either fix the bore log data and re-upload, "
        "or record override decisions in the Nova panel for each blocked item."
    )

    return opening + "\n\n" + "\n".join(details) + rework_note + "\n\n" + closing


def _nc_next_action_answer(
    pipeline_diag: List[Dict[str, Any]],
    overrides: List[Dict[str, Any]],
    plan_signals: List[Dict[str, Any]],
) -> str:
    stopped      = [d for d in pipeline_diag
                    if d.get("stopped_at") and d.get("stopped_at") != "render_gate_blocked"]
    blocked      = [d for d in pipeline_diag if not d.get("render_allowed", True) and d not in stopped]
    needs_review = [d for d in pipeline_diag
                    if d.get("ambiguity_resolution_status") in
                    ("still_review_required", "not_enough_plan_evidence")]
    rework       = [o for o in overrides if o.get("decision") == "Needs Rework"]

    if not pipeline_diag:
        return "Upload a KMZ and structured bore logs first, then upload bore log files to see job intelligence."

    actions: List[str] = []
    for d in stopped[:3]:
        f = _nc_short_file(d.get("source_file") or "")
        actions.append(
            f"Resolve the pipeline failure on {f} — confirm the station range aligns with a defined route in the KMZ."
        )
    for d in blocked[:3]:
        f       = _nc_short_file(d.get("source_file") or "")
        reasons = list(d.get("render_block_reasons") or [])
        hint    = f" ({reasons[0]})" if reasons else ""
        actions.append(f"Clear the render block on {f}{hint}.")
    for o in rework[:2]:
        f = _nc_short_file(o.get("source_file") or "")
        actions.append(f"Rework {f} — {o.get('reason') or 'see override record'}.")
    for d in needs_review[:2]:
        f      = _nc_short_file(d.get("source_file") or "")
        status = d.get("ambiguity_resolution_status") or ""
        if status == "still_review_required":
            actions.append(
                f"Resolve the ambiguity for {f} — upload an engineering plan or manually confirm the route."
            )
        elif status == "not_enough_plan_evidence":
            actions.append(f"Upload a matching engineering plan for {f} to resolve routing ambiguity.")

    if not actions:
        rendered_count = len([d for d in pipeline_diag if d.get("render_allowed") is True])
        return (
            f"No blocking actions — {rendered_count} group(s) rendered successfully. "
            "Verify billing footage and exceptions, then proceed to closeout review."
        )

    lines = ["Here's what needs to happen before this job can move forward.", ""]
    for a in actions[:5]:
        lines.append(f"• {a}")
    return "\n".join(lines)


def _nc_match_source_file(
    question_or_name: str,
    pipeline_diag: List[Dict[str, Any]],
) -> Tuple[Optional[str], List[Dict[str, Any]]]:
    """
    Find a source file in pipeline_diag that matches the given text.
    Returns (matched_filename, matched_groups) or (None, []).
    """
    q = question_or_name.lower()
    all_short = list(dict.fromkeys(
        _nc_short_file(d.get("source_file") or "")
        for d in pipeline_diag
        if d.get("source_file")
    ))

    matched_file: Optional[str] = None
    for fname in all_short:
        fname_key = re.sub(r"[_\-\s]", "", fname.lower()).replace(".csv", "").replace(".xlsx", "")
        q_key     = re.sub(r"[_\-\s]", "", q)
        if fname_key and fname_key in q_key:
            matched_file = fname
            break

    if not matched_file:
        m = re.search(r"bore[_\s\-]?log[_\s\-]?(\d+)", q)
        if m:
            num = m.group(1)
            for fname in all_short:
                if num in fname:
                    matched_file = fname
                    break

    if not matched_file:
        return None, []

    matched_groups = [
        d for d in pipeline_diag
        if _nc_short_file(d.get("source_file") or "").lower() == matched_file.lower()
    ]
    return matched_file, matched_groups


def _nc_source_file_answer(
    question: str,
    pipeline_diag: List[Dict[str, Any]],
    overrides: List[Dict[str, Any]],
) -> str:
    matched_file, matched_groups = _nc_match_source_file(question, pipeline_diag)

    if not matched_file or not matched_groups:
        all_short = list(dict.fromkeys(
            _nc_short_file(d.get("source_file") or "")
            for d in pipeline_diag if d.get("source_file")
        ))
        if all_short:
            return (
                "I couldn't find a matching file. "
                f"Available files: {', '.join(all_short[:8])}. "
                "Try asking about one by name."
            )
        return "Upload structured bore logs to get per-file job intelligence."

    all_ok    = [d for d in matched_groups
                 if d.get("render_allowed") is True and (d.get("segments_returned") is None or d.get("segments_returned") > 0)]
    stopped   = [d for d in matched_groups
                 if d.get("stopped_at") and d.get("stopped_at") != "render_gate_blocked"]
    blk_only  = [d for d in matched_groups if d.get("render_allowed") is False and d not in stopped]
    n_total   = len(matched_groups)
    n_ok      = len(all_ok)

    # Conversational opening
    if n_ok == n_total:
        opening = f"{matched_file} looks good — all {n_total} group(s) rendered successfully."
        if any(d.get("plan_bias_applied") for d in matched_groups):
            opening += " An engineering plan was used to help route one or more groups."
    elif n_ok == 0:
        opening = (
            f"{matched_file} has {n_total} group(s), but none of them produced map geometry. "
            "The file is currently fully blocked."
        )
    else:
        opening = (
            f"{matched_file} has {n_total} group(s). "
            f"{n_ok} rendered successfully, but {n_total - n_ok} had issues."
        )

    parts: List[str] = [opening]

    # Per-problem-group detail (prose, not bullets)
    _STOP_MAP = {
        "no_rankings_after_all_passes": (
            "no matching route was found. "
            "This usually means the station range doesn't align with any route in the KMZ design."
        ),
        "no_anchored_hypotheses": (
            "route alignment couldn't be confirmed. "
            "The engine couldn't find a confident match for the station spacing."
        ),
        "render_gate_blocked": "the render gate blocked it after routing.",
    }

    for d in (stopped + blk_only)[:3]:
        sa        = d.get("stopped_at") or ""
        row_count = d.get("row_count") or "?"
        blk_rsns  = list(d.get("render_block_reasons") or [])
        ambig     = d.get("ambiguity_resolution_status") or ""
        ambig_m   = d.get("ambiguity_resolution_meta") or {}
        plan_bias = d.get("plan_bias_applied", False)
        gidx      = d.get("group_idx", "?")

        if sa and sa != "render_gate_blocked":
            msg = _STOP_MAP.get(sa) or f"stopped at '{sa}'."
            detail = f"Group {gidx} ({row_count} rows) stopped because {msg}"
        elif blk_rsns:
            detail = f"Group {gidx} ({row_count} rows) was blocked — {blk_rsns[0]}."
        else:
            detail = f"Group {gidx} ({row_count} rows) was blocked at the render gate."

        if plan_bias:
            pb   = d.get("plan_bias_meta") or {}
            brid = pb.get("boosted_route_id") or "?"
            detail += f" An engineering plan boosted routing toward {brid}."
        if ambig == "still_review_required":
            detail += f" Route ambiguity still needs manual review. {ambig_m.get('reason') or ''}".rstrip()
        elif ambig == "not_enough_plan_evidence":
            detail += " Not enough plan evidence to auto-resolve — upload a matching engineering plan."
        elif ambig == "resolved_by_plan_signal":
            detail += " Ambiguity was resolved by a plan signal."

        parts.append(detail)

    # Overrides
    file_ovrs = [
        o for o in overrides
        if _nc_short_file(o.get("source_file") or "").lower() == matched_file.lower()
    ]
    for o in file_ovrs:
        decision = o.get("decision") or ""
        reason   = o.get("reason") or ""
        by       = o.get("created_by") or "a reviewer"
        role     = o.get("role") or ""
        label    = f"{by} ({role})" if role else by
        ovr      = f"A '{decision}' override was recorded by {label}"
        if reason:
            ovr += f" — their note: \"{reason}.\""
        ovr += " The original engine issue is still present; this is a human decision, not a technical fix."
        parts.append(ovr)

    # Action guidance for problem groups
    if stopped or blk_only:
        g         = (stopped + blk_only)[0]
        sa        = g.get("stopped_at") or ""
        blk_rsns  = list(g.get("render_block_reasons") or [])
        act_lines = ["What to do next:", ""]

        if sa == "no_rankings_after_all_passes":
            act_lines += [
                "• Check whether the station range overlaps a defined route in the KMZ.",
                "• Upload a matching engineering plan — it gives the engine additional route evidence.",
                "• If the data is acceptable as-is, record an override in the Nova panel with a reason.",
            ]
        elif sa == "no_anchored_hypotheses":
            act_lines += [
                "• Verify the station spacing is sequential and covers enough distance to confirm a route.",
                "• Upload an engineering plan for this section if one exists.",
                "• Record an override if this group is known to be acceptable.",
            ]
        elif blk_rsns:
            act_lines += [
                f"• Review the render block reason: {blk_rsns[0]}.",
                "• Check whether another group is already using this route segment.",
                "• Record an override with a reason if the data is correct and acceptable.",
            ]
        else:
            act_lines += [
                "• Review the pipeline data for this group.",
                "• Correct the bore log and re-upload if the data is wrong.",
                "• Record an override if the issue is known and acceptable.",
            ]

        parts.append("\n".join(act_lines))

    return "\n\n".join(parts)


# ── Follow-up answer sub-functions (Phase 3.1) ────────────────────────────────

def _nc_followup_explain(
    source_file: str,
    file_groups: List[Dict[str, Any]],
    file_overrides: List[Dict[str, Any]],
) -> str:
    """Plain-English explanation of what the issue with source_file actually means."""
    stopped  = [g for g in file_groups
                if g.get("stopped_at") and g.get("stopped_at") != "render_gate_blocked"]
    blk_only = [g for g in file_groups if g.get("render_allowed") is False and g not in stopped]

    if not stopped and not blk_only:
        return (
            f"There's actually nothing wrong with {source_file} — "
            "all its groups rendered successfully. Nothing needs explaining here."
        )

    parts: List[str] = []
    g = (stopped + blk_only)[0]
    sa        = g.get("stopped_at") or ""
    row_count = g.get("row_count") or "?"
    blk_rsns  = list(g.get("render_block_reasons") or [])

    if sa == "no_rankings_after_all_passes":
        parts.append(
            f"{source_file} has a group ({row_count} rows) that couldn't be matched to a route. "
            "The pipeline searched every available route candidate and none were close enough to the "
            "station points in that group. In practical terms, this means no drill segment was drawn "
            "for it — it won't appear on the map and won't contribute to the billing footage."
        )
    elif sa == "no_anchored_hypotheses":
        parts.append(
            f"{source_file} has a group ({row_count} rows) where route alignment couldn't be confirmed. "
            "The engine found some candidates but couldn't confidently align the station spacing to any of them. "
            "Without that confirmation, no geometry is produced for this group."
        )
    elif blk_rsns:
        parts.append(
            f"{source_file} has a group ({row_count} rows) that was blocked by: {blk_rsns[0]}. "
            "The pipeline found a route candidate but it failed a quality check before the final geometry was written."
        )
    else:
        parts.append(
            f"{source_file} has a group ({row_count} rows) that didn't make it through the pipeline. "
            "Without completing routing, no map geometry or billing footage is produced for it."
        )

    if file_overrides:
        o        = file_overrides[0]
        decision = o.get("decision") or ""
        by       = o.get("created_by") or "a reviewer"
        role     = o.get("role") or ""
        reason   = o.get("reason") or ""
        label    = f"{by} ({role})" if role else by
        parts.append(
            f"Note: this issue has been recorded as '{decision}' by {label}"
            + (f" — their note: \"{reason}.\"" if reason else ".")
            + " The engine finding is still there; that's a human decision, not a fix."
        )

    return "\n\n".join(parts)


def _nc_followup_fix(
    source_file: str,
    file_groups: List[Dict[str, Any]],
    file_overrides: List[Dict[str, Any]],
) -> str:
    """Practical fix steps for the issue with source_file."""
    stopped  = [g for g in file_groups
                if g.get("stopped_at") and g.get("stopped_at") != "render_gate_blocked"]
    blk_only = [g for g in file_groups if g.get("render_allowed") is False and g not in stopped]

    if not stopped and not blk_only:
        return (
            f"Nothing needs fixing for {source_file} — all groups rendered successfully."
        )

    g = (stopped + blk_only)[0]
    sa       = g.get("stopped_at") or ""
    blk_rsns = list(g.get("render_block_reasons") or [])

    bullets: List[str] = []
    if sa == "no_rankings_after_all_passes":
        bullets = [
            f"Check that {source_file}'s station range actually overlaps one of the defined routes in the KMZ.",
            "Confirm the print tokens in the file match the correct sheet numbers — a mismatch blocks route filtering.",
            "Upload an engineering plan PDF for this section — it gives the engine additional route evidence that often breaks the tie.",
            "If the data is correct and the group is acceptable, use 'Resolve / Override' in the Nova panel to document why.",
        ]
    elif sa == "no_anchored_hypotheses":
        bullets = [
            f"Check the station spacing in {source_file} — rows should have consistent, sequential station values.",
            "Make sure the group covers enough distance (at least 2 rows with valid, distinct stations).",
            "Upload an engineering plan if one exists — it can anchor the hypothesis even when spacing is marginal.",
            "Record an override in Nova if this group is known to be acceptable.",
        ]
    elif blk_rsns:
        bullets = [
            f"Review the render block reason: {blk_rsns[0]}.",
            "Check whether another group from this file or another file is already mapped to the same route segment.",
            "If this bore is valid and the overlap is acceptable, record an override in Nova with a clear reason.",
        ]
    else:
        bullets = [
            f"Review the pipeline data for {source_file}.",
            "Correct the bore log file and re-upload if the data is wrong.",
            "Record an override in Nova if the issue is known and acceptable.",
        ]

    if file_overrides:
        bullets.append("An override is already on file — review its reason and update if needed.")

    lines = [f"Here's what to try for {source_file}:", ""]
    for b in bullets:
        lines.append(f"• {b}")
    lines.append("")
    lines.append(
        "Either correct the source data or use 'Resolve / Override' to document the decision. "
        "The original engine finding stays on record either way."
    )
    return "\n".join(lines)


def _nc_followup_severity(
    source_file: str,
    file_groups: List[Dict[str, Any]],
    file_overrides: List[Dict[str, Any]],
) -> str:
    """Assess how serious the issue is for source_file."""
    stopped  = [g for g in file_groups
                if g.get("stopped_at") and g.get("stopped_at") != "render_gate_blocked"]
    blk_only = [g for g in file_groups if g.get("render_allowed") is False and g not in stopped]
    all_ok   = [g for g in file_groups
                if g.get("render_allowed") is True and
                (g.get("segments_returned") is None or g.get("segments_returned") > 0)]
    n_issue  = len(stopped) + len(blk_only)
    n_ok     = len(all_ok)
    n_total  = len(file_groups)

    if not stopped and not blk_only:
        return f"No — {source_file} is fine. All {n_total} group(s) rendered without issues."

    if n_ok == 0:
        severity = (
            f"Yes, this is significant. None of the groups in {source_file} rendered successfully. "
            "This file contributes no geometry to the map and no footage to billing right now."
        )
    elif n_issue == 1:
        severity = (
            f"It depends on what that group represents. {source_file} has {n_ok} group(s) that rendered fine, "
            f"but 1 group with an issue. If that group covers real field work, "
            "it won't be counted in billing. If it's a minor or incidental group, the impact may be small."
        )
    else:
        severity = (
            f"Yes, this needs attention. {source_file} has {n_issue} groups with issues out of {n_total} total — "
            "a significant portion of this file isn't generating geometry."
        )

    parts = [severity]

    if file_overrides:
        o        = file_overrides[0]
        decision = o.get("decision") or ""
        parts.append(
            f"A '{decision}' override is already on file for this, "
            "but the engine issue is still present — the override is a human note, not a fix."
        )
    else:
        parts.append("No override has been recorded for this file yet.")

    return "\n\n".join(parts)


def _nc_followup_answer(
    question: str,
    source_file: str,
    pipeline_diag: List[Dict[str, Any]],
    overrides: List[Dict[str, Any]],
) -> str:
    """
    Answer a vague follow-up in context of the last-discussed source file.
    Routes to explain / fix / severity based on follow-up type.
    """
    q = question.lower()

    file_groups = [
        d for d in pipeline_diag
        if _nc_short_file(d.get("source_file") or "").lower() == source_file.lower()
    ]
    file_ovrs = [
        o for o in overrides
        if _nc_short_file(o.get("source_file") or "").lower() == source_file.lower()
    ]

    if not file_groups:
        return (
            f"I don't have group data for {source_file} in this session. "
            "Try asking about it directly by name."
        )

    is_fix      = any(k in q for k in ["fix", "resolve", "do about", "do i do", "should i do", "deal with"])
    is_severity = any(k in q for k in ["bad", "worry", "serious", "concern", "matter", "how bad"])

    if is_fix:
        return _nc_followup_fix(source_file, file_groups, file_ovrs)
    if is_severity:
        return _nc_followup_severity(source_file, file_groups, file_ovrs)
    return _nc_followup_explain(source_file, file_groups, file_ovrs)


def _nc_override_answer(
    overrides: List[Dict[str, Any]],
    pipeline_diag: List[Dict[str, Any]],
) -> str:
    if not overrides:
        if not pipeline_diag:
            return (
                "No override decisions recorded yet. "
                "Upload job data first, then use 'Resolve / Override' in the Nova panel to record decisions."
            )
        return (
            "No overrides have been recorded for this session. "
            "To create one, expand a QA flag in the Nova panel and click 'Resolve / Override'."
        )

    n      = len(overrides)
    rework = [o for o in overrides if o.get("decision") == "Needs Rework"]

    opening = (
        f"{n} override decision{'s have' if n > 1 else ' has'} been recorded. "
        "Keep in mind these are human decisions — the original engine findings remain on record."
    )

    lines: List[str] = [opening, ""]
    for o in overrides:
        f        = _nc_short_file(o.get("source_file") or "")
        decision = o.get("decision") or "?"
        reason   = o.get("reason") or ""
        by       = o.get("created_by") or "reviewer"
        role     = o.get("role") or ""
        ts       = o.get("created_at") or ""
        label    = f"{by} ({role})" if role else by
        line     = f"• {f or 'unknown file'}: {decision} (by {label})"
        if reason:
            line += f" — \"{reason}\""
        lines.append(line)

    if rework:
        lines.append(
            f"\n{len(rework)} item(s) marked 'Needs Rework' block billing until resolved."
        )

    return "\n".join(lines)


def _nc_plan_answer(
    plan_signals: List[Dict[str, Any]],
    pipeline_diag: List[Dict[str, Any]],
) -> str:
    if not plan_signals:
        if not pipeline_diag:
            return (
                "Upload a KMZ and bore logs first, then upload engineering plan PDFs "
                "to enable plan-assisted routing."
            )
        return (
            "No engineering plan signals have been detected yet. "
            "Upload engineering plan PDFs via the 'Upload Engineering Plan' option. "
            "Plans help resolve ambiguous bore log routing by providing route and print-sheet evidence."
        )

    bias_groups    = [d for d in pipeline_diag if d.get("plan_bias_applied")]
    ambig_resolved = [
        d for d in pipeline_diag
        if d.get("ambiguity_resolution_status") == "resolved_by_plan_signal"
    ]

    plan_files = list(dict.fromkeys(
        _nc_short_file(s.get("source_file") or s.get("plan_id") or "")
        for s in plan_signals
        if s.get("source_file") or s.get("plan_id")
    ))

    n       = len(plan_signals)
    opening = f"Yes — {n} engineering plan signal{'s are' if n > 1 else ' is'} loaded."
    if plan_files:
        opening += f" Plan file{'s' if len(plan_files) > 1 else ''}: {', '.join(plan_files[:6])}."

    parts: List[str] = [opening]

    if bias_groups:
        bias_lines = [f"Plan bias was applied to {len(bias_groups)} routing group(s):"]
        for d in bias_groups[:4]:
            f    = _nc_short_file(d.get("source_file") or "")
            pb   = d.get("plan_bias_meta") or {}
            brid = pb.get("boosted_route_id") or "?"
            bias_lines.append(f"  • {f}: routing boosted toward {brid}")
        parts.append("\n".join(bias_lines))

    if ambig_resolved:
        parts.append(
            f"Plan signals resolved ambiguity in {len(ambig_resolved)} group(s) "
            "that would otherwise have needed manual review."
        )

    if not bias_groups and not ambig_resolved:
        parts.append(
            "The plans were loaded but didn't directly affect routing for any groups in this run."
        )

    return "\n\n".join(parts)


def _nc_general_answer(
    pipeline_diag: List[Dict[str, Any]],
    plan_signals: List[Dict[str, Any]],
    overrides: List[Dict[str, Any]],
) -> str:
    if not pipeline_diag and not plan_signals and not overrides:
        return "Upload a KMZ and structured bore logs to generate job intelligence."

    total         = len(pipeline_diag)
    rendered      = len([d for d in pipeline_diag if d.get("render_allowed") is True])
    blocked_count = len([d for d in pipeline_diag if not d.get("render_allowed", True)])
    stopped_count = len([
        d for d in pipeline_diag
        if d.get("stopped_at") and d.get("stopped_at") != "render_gate_blocked"
    ])
    rework_count  = len([o for o in overrides if o.get("decision") == "Needs Rework"])
    review_count  = len(overrides) - rework_count

    if blocked_count > 0 or stopped_count > 0:
        opening = (
            f"This job has {total} group(s) — {rendered} rendered successfully, "
            f"{blocked_count} are blocked, and {stopped_count} stopped early in the pipeline."
        )
    else:
        opening = f"This job has {total} group(s) — all {rendered} rendered successfully."

    parts: List[str] = [opening]

    extras: List[str] = []
    if plan_signals:
        extras.append(f"{len(plan_signals)} engineering plan signal(s) loaded and active.")
    if overrides:
        extras.append(f"{review_count} override decision(s) reviewed, {rework_count} need rework.")
    if extras:
        parts.append(" ".join(extras))

    if blocked_count > 0 or stopped_count > 0:
        parts.append(
            "Ask 'Why is this job blocked?' or 'What should I do next?' for specific guidance."
        )
    else:
        parts.append("Verify billing footage and exceptions, then proceed to closeout review.")

    return "\n\n".join(parts)


def _nova_deterministic_answer(
    question: str,
    pipeline_diag: List[Dict[str, Any]],
    plan_signals: List[Dict[str, Any]],
    overrides: List[Dict[str, Any]],
    recent_context: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Deterministic, read-only Nova answer builder.
    Phase 3.1: accepts recent_context for vague follow-up resolution.
    No external API calls. Grounded entirely in current session state.
    """
    if not question.strip():
        return "Please enter a question to ask Nova."

    if not pipeline_diag and not plan_signals and not overrides:
        return "Upload a KMZ and structured bore logs to generate job intelligence."

    ctx = recent_context or {}

    # ── Vague follow-up resolution ────────────────────────────────────────────
    if _nc_is_vague_followup(question):
        ctx_file   = ctx.get("source_file")
        ctx_intent = ctx.get("last_intent")

        if ctx_file:
            return _nc_followup_answer(question, ctx_file, pipeline_diag, overrides)

        # No file context — try to route to general intent from context
        q = question.lower()
        if ctx_intent in ("blocked_readiness",) or any(k in q for k in ["fix", "resolve", "do"]):
            return _nc_next_action_answer(pipeline_diag, overrides, plan_signals)
        if ctx_intent == "next_action":
            return _nc_next_action_answer(pipeline_diag, overrides, plan_signals)

        return (
            "I'm not sure which item you're referring to. "
            "Try asking about a specific bore log by name, or use: "
            "'Why is this job blocked?', 'What should I do next?', or 'Which items were overridden?'"
        )

    # ── Normal intent routing ──────────────────────────────────────────────────
    intent = _nc_intent(question)

    if intent == "source_file":
        return _nc_source_file_answer(question, pipeline_diag, overrides)
    if intent == "override":
        return _nc_override_answer(overrides, pipeline_diag)
    if intent == "plan":
        return _nc_plan_answer(plan_signals, pipeline_diag)
    if intent == "next_action":
        return _nc_next_action_answer(pipeline_diag, overrides, plan_signals)
    if intent == "blocked_readiness":
        return _nc_blocked_answer(pipeline_diag, overrides)
    return _nc_general_answer(pipeline_diag, plan_signals, overrides)


@protected_router.post("/api/nova-chat")
def nova_chat(
    payload: Dict[str, Any] = Body(...),
    session_id: Optional[str] = None,
) -> JSONResponse:
    """
    Read-only Nova copilot (Phase 3.1).
    Deterministic answers using session STATE + persisted overrides.
    Accepts recent_messages for conversational context.
    Does NOT mutate STATE, overrides, or any job data.
    """
    body_session_id = payload.get("session_id") if isinstance(payload, dict) else None
    resolved_session_id = _resolve_session_id(session_id or body_session_id)
    question = str(payload.get("question") or "").strip()

    if not question:
        return _err("question is required.", session_id=resolved_session_id)
    if len(question) > 2000:
        return _err("question is too long (max 2000 characters).", session_id=resolved_session_id)

    # Extract recent chat history for conversational context (max 6 messages).
    raw_recent = payload.get("recent_messages") if isinstance(payload, dict) else None
    recent_messages: List[Dict[str, Any]] = (
        [
            {"role": str(m.get("role") or ""), "content": str(m.get("content") or "")}
            for m in (raw_recent or [])
            if isinstance(m, dict)
        ][-6:]
    )

    # Read session state — read-only. We exit _session_scope without mutating STATE.
    with _session_scope(resolved_session_id):
        pipeline_diag: List[Dict[str, Any]] = list(STATE.get("pipeline_diag") or [])
        plan_signals: List[Dict[str, Any]]  = list(STATE.get("engineering_plan_signals") or [])

    # Load persisted overrides for this session.
    try:
        overrides_data    = _load_nova_overrides_index()
        sid               = resolved_session_id.strip()
        session_overrides: List[Dict[str, Any]] = [
            r for r in overrides_data.get("overrides", [])
            if str(r.get("session_id") or "").strip() == sid
        ]
    except Exception:
        session_overrides = []

    # Infer conversational context from recent history.
    recent_context = _nc_infer_context(recent_messages, pipeline_diag)

    answer = _nova_deterministic_answer(
        question, pipeline_diag, plan_signals, session_overrides, recent_context
    )

    return JSONResponse(content={
        "success": True,
        "session_id": resolved_session_id,
        "answer": answer,
        "used_context": {
            "has_pipeline_diag":             bool(pipeline_diag),
            "pipeline_group_count":          len(pipeline_diag),
            "engineering_plan_signal_count": len(plan_signals),
            "override_count":                len(session_overrides),
            "context_file":                  recent_context.get("source_file"),
            "context_intent":                recent_context.get("last_intent"),
        },
    })


# ---------------------------------------------------------------------------
# Walk connectivity test endpoint (temporary, no persistence).
# Added as a minimal self-contained block at the bottom of the file so nothing
# above this line is modified. Remove this section once the real walk module ships.
# ---------------------------------------------------------------------------

import logging as _walk_test_logging
from typing import Any as _WalkTestAny, Dict as _WalkTestDict

_walk_test_logger = _walk_test_logging.getLogger("walk.test_event")
if not _walk_test_logger.handlers:
    _walk_test_handler = _walk_test_logging.StreamHandler()
    _walk_test_handler.setFormatter(
        _walk_test_logging.Formatter("%(asctime)s [%(name)s] %(message)s")
    )
    _walk_test_logger.addHandler(_walk_test_handler)
    _walk_test_logger.setLevel(_walk_test_logging.INFO)
    _walk_test_logger.propagate = False


@protected_router.post("/api/walk/test-event")
def walk_test_event(payload: _WalkTestDict[str, _WalkTestAny] = Body(default={})) -> JSONResponse:
    """
    Connectivity probe for the mobile walk app.

    Accepts any JSON body, logs it to stdout/server logs, and returns
    {"success": true}. No persistence. No session bookkeeping. Do not depend
    on this endpoint for anything beyond smoke-testing the network path.
    """
    try:
        _walk_test_logger.info("walk test event received: %s", json.dumps(payload, default=str))
    except Exception:
        _walk_test_logger.info("walk test event received (unserializable payload)")
    return _ok(received=payload)


# ---------------------------------------------------------------------------
# Phase 2A walk endpoints: start / breadcrumbs / station-events / end.
# Session-scoped. Append-only writes into walk_breadcrumbs, walk_station_events, walk_meta.
# Send Home is intentionally not implemented here yet.
# ---------------------------------------------------------------------------

WALK_BREADCRUMB_CAP = 50000
WALK_ACCURACY_HARD_LIMIT_M = 1000.0


def _walk_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _walk_clean_breadcrumb(point: Any) -> Optional[Dict[str, Any]]:
    """Validate and normalize a single breadcrumb point. Returns None if the
    point is unusable. Used by /api/walk/breadcrumbs to defend the stored
    list against malformed client payloads."""
    if not isinstance(point, dict):
        return None
    try:
        lat = float(point.get("lat"))
        lon = float(point.get("lon"))
    except (TypeError, ValueError):
        return None
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        return None
    accuracy_raw = point.get("accuracy_m")
    accuracy_m: Optional[float]
    try:
        accuracy_m = float(accuracy_raw) if accuracy_raw is not None else None
    except (TypeError, ValueError):
        accuracy_m = None
    if accuracy_m is not None and accuracy_m > WALK_ACCURACY_HARD_LIMIT_M:
        # Anything worse than 1km is almost certainly garbage from a desktop
        # geo-IP lookup; the client should be filtering tighter than this
        # already, but defend in depth.
        return None
    ts_raw = point.get("ts")
    ts = str(ts_raw).strip() if ts_raw is not None else ""
    cleaned: Dict[str, Any] = {
        "lat": lat,
        "lon": lon,
        "ts": ts or _walk_iso_now(),
    }
    if accuracy_m is not None:
        cleaned["accuracy_m"] = accuracy_m
    return cleaned


def _walk_clean_station_event(ev: Any) -> Optional[Dict[str, Any]]:
    """Validate/normalize one station event from /api/walk/station-events."""
    if not isinstance(ev, dict):
        return None
    station_number = str(ev.get("station_number") or "").strip()
    if not station_number:
        return None
    try:
        depth_ft = float(ev.get("depth_ft"))
        boc_ft = float(ev.get("boc_ft"))
        lat = float(ev.get("lat"))
        lon = float(ev.get("lon"))
    except (TypeError, ValueError):
        return None
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        return None
    accuracy_raw = ev.get("accuracy_m")
    accuracy_m: Optional[float]
    try:
        accuracy_m = float(accuracy_raw) if accuracy_raw is not None else None
    except (TypeError, ValueError):
        accuracy_m = None
    if accuracy_m is not None and accuracy_m > WALK_ACCURACY_HARD_LIMIT_M:
        return None
    ts_raw = ev.get("ts")
    if isinstance(ts_raw, bool):
        ts_ms = int(time.time() * 1000)
    elif isinstance(ts_raw, (int, float)):
        fv = float(ts_raw)
        if math.isnan(fv) or math.isinf(fv):
            ts_ms = int(time.time() * 1000)
        else:
            ts_ms = int(fv)
    elif isinstance(ts_raw, str) and ts_raw.strip():
        try:
            ts_ms = int(datetime.fromisoformat(ts_raw.replace("Z", "+00:00")).timestamp() * 1000)
        except Exception:
            ts_ms = int(time.time() * 1000)
    else:
        ts_ms = int(time.time() * 1000)
    cleaned: Dict[str, Any] = {
        "station_number": station_number,
        "depth_ft": depth_ft,
        "boc_ft": boc_ft,
        "lat": lat,
        "lon": lon,
        "ts": ts_ms,
    }
    if accuracy_m is not None:
        cleaned["accuracy_m"] = accuracy_m
    # walk-v2 additive passthroughs. Optional. Server never invents these.
    client_uuid_raw = ev.get("client_uuid")
    if isinstance(client_uuid_raw, str):
        cu = client_uuid_raw.strip()
        if cu and len(cu) <= 128:
            cleaned["client_uuid"] = cu
    note_raw = ev.get("note")
    if isinstance(note_raw, str):
        note = note_raw.strip()
        if note:
            cleaned["note"] = note[:500]
    crew_raw = ev.get("crew")
    if isinstance(crew_raw, str):
        crew = crew_raw.strip()
        if crew:
            cleaned["crew"] = crew[:120]
    return cleaned


@protected_router.post("/api/walk/start")
def walk_start(payload: Dict[str, Any] = Body(default={})) -> JSONResponse:
    body_session_id = payload.get("session_id") if isinstance(payload, dict) else None
    resolved_session_id = _resolve_session_id(body_session_id)
    try:
        with _session_scope(resolved_session_id):
            if _is_closeout_locked():
                return _json_closeout_locked_response()
            meta = {
                "job_id": str(payload.get("job_id") or "").strip(),
                "job_label": str(payload.get("job_label") or "").strip(),
                "crew": str(payload.get("crew") or "").strip(),
                "date": str(payload.get("date") or "").strip(),
                "section": str(payload.get("section") or "").strip(),
                "started_at": _walk_iso_now(),
            }
            STATE["walk_active"] = True
            STATE["walk_meta"] = meta
            # Per spec: clear/start the breadcrumb list at the beginning of a
            # walk. Station events are NOT cleared here — they are managed by
            # a separate Phase 2B endpoint.
            STATE["walk_breadcrumbs"] = []
            return _ok(
                session_id=resolved_session_id,
                walk_active=True,
                walk_meta=meta,
            )
    except Exception as exc:
        return _err(str(exc), session_id=resolved_session_id)


@protected_router.post("/api/walk/breadcrumbs")
def walk_breadcrumbs(payload: Dict[str, Any] = Body(default={})) -> JSONResponse:
    body_session_id = payload.get("session_id") if isinstance(payload, dict) else None
    resolved_session_id = _resolve_session_id(body_session_id)
    try:
        raw_points = payload.get("points") if isinstance(payload, dict) else None
        incoming = list(raw_points) if isinstance(raw_points, list) else []
        with _session_scope(resolved_session_id):
            if _is_closeout_locked():
                return _json_closeout_locked_response()
            if not bool(STATE.get("walk_active")):
                # Walk not active — accept but discard. Returning an error
                # would force the client into an awkward retry loop on race
                # conditions around End Walk; silent drop is friendlier.
                return _ok(
                    session_id=resolved_session_id,
                    walk_active=False,
                    accepted=0,
                    breadcrumb_count=len(STATE.get("walk_breadcrumbs") or []),
                    truncated=False,
                )
            existing = list(STATE.get("walk_breadcrumbs") or [])
            accepted = 0
            for raw_point in incoming:
                cleaned = _walk_clean_breadcrumb(raw_point)
                if cleaned is None:
                    continue
                existing.append(cleaned)
                accepted += 1
            truncated = False
            if len(existing) > WALK_BREADCRUMB_CAP:
                # Drop oldest first so the most recent walk activity survives.
                existing = existing[-WALK_BREADCRUMB_CAP:]
                truncated = True
            STATE["walk_breadcrumbs"] = existing
            return _ok(
                session_id=resolved_session_id,
                walk_active=True,
                accepted=accepted,
                breadcrumb_count=len(existing),
                truncated=truncated,
            )
    except Exception as exc:
        return _err(str(exc), session_id=resolved_session_id)


@protected_router.post("/api/walk/station-events")
def walk_station_events(payload: Dict[str, Any] = Body(default={})) -> JSONResponse:
    body_session_id = payload.get("session_id") if isinstance(payload, dict) else None
    resolved_session_id = _resolve_session_id(body_session_id)
    try:
        raw_events = payload.get("events") if isinstance(payload, dict) else None
        incoming = list(raw_events) if isinstance(raw_events, list) else []
        with _session_scope(resolved_session_id):
            if _is_closeout_locked():
                return _json_closeout_locked_response()
            existing = list(STATE.get("walk_station_events") or [])
            seen_client_uuids = {
                str(ev.get("client_uuid"))
                for ev in existing
                if isinstance(ev, dict) and ev.get("client_uuid")
            }
            for raw_ev in incoming:
                cleaned = _walk_clean_station_event(raw_ev)
                if cleaned is None:
                    continue
                cu = cleaned.get("client_uuid")
                if cu and cu in seen_client_uuids:
                    # walk-v2 retry of an already-saved station: silently skip.
                    continue
                if cu:
                    seen_client_uuids.add(cu)
                existing.append(cleaned)
            STATE["walk_station_events"] = existing
            # Persist incrementally so the office sees stations immediately and
            # data survives a backend restart before walk_end is called.
            # Non-fatal: disk failure must never block this response.
            try:
                _save_walk_submission(
                    session_id=resolved_session_id,
                    meta=dict(STATE.get("walk_meta") or {}),
                    breadcrumbs=list(STATE.get("walk_breadcrumbs") or []),
                    station_events=existing,
                )
            except Exception:
                pass
            return JSONResponse({"ok": True, "count": len(existing)})
    except Exception as exc:
        return _err(str(exc), session_id=resolved_session_id)


@protected_router.post("/api/walk/end")
def walk_end(payload: Dict[str, Any] = Body(default={})) -> JSONResponse:
    body_session_id = payload.get("session_id") if isinstance(payload, dict) else None
    resolved_session_id = _resolve_session_id(body_session_id)
    try:
        with _session_scope(resolved_session_id):
            if _is_closeout_locked():
                return _json_closeout_locked_response()
            STATE["walk_active"] = False
            meta = dict(STATE.get("walk_meta") or {})
            meta["ended_at"] = _walk_iso_now()
            STATE["walk_meta"] = meta
            breadcrumb_count = len(STATE.get("walk_breadcrumbs") or [])
            station_event_count = len(STATE.get("walk_station_events") or [])
            # Persist to disk so the office can see this submission across devices.
            # Wrapped in its own try/except: a disk failure must never block the
            # walk end response — the in-memory session is the authoritative store.
            try:
                _save_walk_submission(
                    session_id=resolved_session_id,
                    meta=meta,
                    breadcrumbs=list(STATE.get("walk_breadcrumbs") or []),
                    station_events=list(STATE.get("walk_station_events") or []),
                )
                print("WALK SUBMISSION SAVED", resolved_session_id)
            except Exception as e:
                print("WALK SUBMISSION FAILED", str(e))
            return _ok(
                session_id=resolved_session_id,
                walk_active=False,
                breadcrumb_count=breadcrumb_count,
                station_event_count=station_event_count,
                walk_meta=meta,
            )
    except Exception as exc:
        return _err(str(exc), session_id=resolved_session_id)


def _routes_payload_from_catalog(route_catalog: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    routes: List[Dict[str, Any]] = []
    for route in route_catalog or []:
        coords = route.get("coords") or []
        geometry = {
            "type": "LineString",
            "coordinates": [[float(pt[1]), float(pt[0])] for pt in coords if len(pt) >= 2],
        }
        routes.append(
            {
                "id": str(route.get("route_id") or ""),
                "route_name": str(route.get("route_name") or route.get("name") or "Unnamed Route"),
                "length_ft": float(route.get("length_ft") or 0.0),
                "segment_count": max(0, len(coords) - 1),
                "geometry": geometry,
            }
        )

    return routes


def _normalize_walk_project_id(value: Optional[str]) -> Optional[str]:
    raw = str(value or "").strip()
    if not raw or len(raw) > 128:
        return None
    if not re.fullmatch(r"[a-zA-Z0-9._-]+", raw):
        return None
    return raw


def _project_route_context_path(project_id: str) -> Path:
    return PROJECT_ROUTE_CONTEXT_DIR / f"{project_id}.json"


def _save_project_route_context(project_id: str, route_catalog: List[Dict[str, Any]]) -> None:
    path = _project_route_context_path(project_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "version": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "route_catalog": route_catalog,
    }
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")


def _load_project_route_context_doc(project_id: str) -> Optional[Dict[str, Any]]:
    path = _project_route_context_path(project_id)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else None
    except Exception:
        return None


def _load_latest_project_route_context_doc() -> Optional[Dict[str, Any]]:
    """V1 PROJECTS->JOBS bridge.

    Walk currently runs against jobs (e.g. TEST-001) which have no route of
    their own; KMZ uploads land under a project_id (e.g. brenham-phase-5).
    When the walk asks for route-context for a job/project that has no route
    file, fall back to the most recently uploaded KMZ across all projects so
    field crews can still see a route. Read-only — never mutates project data,
    never alters the upload flow, never edits session state.
    """
    try:
        if not PROJECT_ROUTE_CONTEXT_DIR.is_dir():
            return None
        candidates = [p for p in PROJECT_ROUTE_CONTEXT_DIR.glob("*.json") if p.is_file()]
    except Exception:
        return None
    if not candidates:
        return None
    try:
        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    except Exception:
        return None
    for path in candidates:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(raw, dict) and isinstance(raw.get("route_catalog"), list):
            return raw
    return None


@protected_router.get("/api/walk/route-context")
def get_walk_route_context(projectId: Optional[str] = Query(None)) -> Dict[str, Any]:
    normalized = _normalize_walk_project_id(projectId)
    doc: Optional[Dict[str, Any]] = None
    source = "project"
    if normalized:
        doc = _load_project_route_context_doc(normalized)
    if not doc:
        # V1 PROJECTS->JOBS bridge: jobs in /walk don't carry their own KMZ,
        # so fall back to the most recently uploaded project route. Preserves
        # prior empty-response behavior when no KMZ has ever been uploaded.
        doc = _load_latest_project_route_context_doc()
        source = "latest_project_fallback" if doc else "project"
    if not doc:
        return {"routes": [], "route_count": 0}
    catalog = doc.get("route_catalog")
    if not isinstance(catalog, list):
        return {"routes": [], "route_count": 0}
    routes = _routes_payload_from_catalog(catalog)
    return {"routes": routes, "route_count": len(routes), "source": source}


# ---------------------------------------------------------------------------
# Walk submission disk persistence.
# Completed walks are written to uploads/walk_submissions/<session_id>.json
# and enumerated via uploads/walk_submissions/index.json so the office can
# see field submissions across devices without sharing a browser session.
# Pattern mirrors reviewer_exceptions storage already in use.
# ---------------------------------------------------------------------------

WALK_SUBMISSIONS_DIR = UPLOADS_DIR / "walk_submissions"
WALK_SUBMISSIONS_INDEX_PATH = WALK_SUBMISSIONS_DIR / "index.json"


def _ensure_walk_submissions_storage() -> None:
    WALK_SUBMISSIONS_DIR.mkdir(parents=True, exist_ok=True)
    if not WALK_SUBMISSIONS_INDEX_PATH.exists():
        WALK_SUBMISSIONS_INDEX_PATH.write_text(
            json.dumps({"submissions": []}, indent=2),
            encoding="utf-8",
        )


def _load_walk_submissions_index() -> Dict[str, Any]:
    _ensure_walk_submissions_storage()
    try:
        data = json.loads(WALK_SUBMISSIONS_INDEX_PATH.read_text(encoding="utf-8"))
    except Exception:
        data = {"submissions": []}
    if not isinstance(data, dict):
        data = {"submissions": []}
    if not isinstance(data.get("submissions"), list):
        data["submissions"] = []
    return data


def _save_walk_submissions_index(data: Dict[str, Any]) -> None:
    _ensure_walk_submissions_storage()
    tmp = WALK_SUBMISSIONS_INDEX_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(WALK_SUBMISSIONS_INDEX_PATH)


def _walk_submission_sid(session_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", str(session_id or "").strip())[:80]


def _save_walk_submission(
    session_id: str,
    meta: Dict[str, Any],
    breadcrumbs: List[Dict[str, Any]],
    station_events: List[Dict[str, Any]],
) -> None:
    sid = str(session_id or "").strip()
    if not sid:
        return
    _ensure_walk_submissions_storage()
    job_id = str(meta.get("job_id") or "").strip() or "test-job"
    ended_at = str(meta.get("ended_at") or _walk_iso_now())

    track_coords = [
        [float(pt["lon"]), float(pt["lat"])]
        for pt in breadcrumbs
        if isinstance(pt, dict)
        and pt.get("lat") is not None
        and pt.get("lon") is not None
    ]
    track_geometry: Optional[Dict[str, Any]] = (
        {"type": "LineString", "coordinates": track_coords}
        if len(track_coords) >= 2
        else None
    )

    doc = {
        "session_id": sid,
        "job_id": job_id,
        "walk_meta": meta,
        "walk_breadcrumbs": breadcrumbs,
        "walk_station_events": station_events,
        "ended_at": ended_at,
        "station_count": len(station_events),
        "breadcrumb_count": len(breadcrumbs),
        "track_geometry": track_geometry,
    }
    safe_sid = _walk_submission_sid(sid)
    doc_path = WALK_SUBMISSIONS_DIR / f"{safe_sid}.json"
    tmp = doc_path.with_suffix(".tmp")
    target_path = doc_path
    print("WRITING FILE:", target_path)
    tmp.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    tmp.replace(doc_path)

    summary = {
        "session_id": sid,
        "job_id": job_id,
        "ended_at": ended_at,
        "station_count": len(station_events),
        "breadcrumb_count": len(breadcrumbs),
        "crew": str(meta.get("crew") or ""),
        "date": str(meta.get("date") or ""),
        "section": str(meta.get("section") or ""),
        "filename": f"{safe_sid}.json",
    }
    idx = _load_walk_submissions_index()
    subs = [s for s in idx["submissions"] if str(s.get("session_id") or "") != sid]
    subs.append(summary)
    subs.sort(key=lambda s: str(s.get("ended_at") or ""), reverse=True)
    idx["submissions"] = subs
    _save_walk_submissions_index(idx)


def _load_walk_submission_doc(filename: str) -> Optional[Dict[str, Any]]:
    path = WALK_SUBMISSIONS_DIR / filename
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else None
    except Exception:
        return None


def _load_walk_submissions_for_job(job_id: str) -> List[Dict[str, Any]]:
    """Return all walk submission summaries for a job, most recent first.
    'test-job' or empty job_id returns all submissions (V1 single-job behaviour)."""
    safe_jid = str(job_id or "").strip()
    idx = _load_walk_submissions_index()
    subs = idx.get("submissions") or []
    if safe_jid and safe_jid != "test-job":
        subs = [s for s in subs if str(s.get("job_id") or "") == safe_jid]
    # Hide archived submissions from office inbox / aggregates (index only; JSON files untouched).
    subs = [s for s in subs if isinstance(s, dict) and not str(s.get("archived_at") or "").strip()]
    return list(subs)


@protected_router.post("/api/walk-sessions/{session_id}/archive")
def archive_walk_session(session_id: str) -> JSONResponse:
    """Mark a walk submission as archived (index-only). Does not delete JSON or photos."""
    sid = str(session_id or "").strip()
    if not sid:
        return JSONResponse({"ok": False, "error": "session_id is required"}, status_code=400)
    archived_at = datetime.now(timezone.utc).isoformat()
    idx = _load_walk_submissions_index()
    subs_raw = idx.get("submissions")
    if not isinstance(subs_raw, list):
        subs_raw = []
    found = False
    for entry in subs_raw:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("session_id") or "").strip() != sid:
            continue
        entry["archived_at"] = archived_at
        found = True
        break
    if not found:
        return JSONResponse(
            {"ok": False, "error": "session not found in walk submissions index"},
            status_code=404,
        )
    idx["submissions"] = subs_raw
    _save_walk_submissions_index(idx)
    return JSONResponse({"ok": True, "session_id": sid, "archived_at": archived_at}, status_code=200)


@localhost_router.get("/api/debug/walk-submissions")
def debug_walk_submissions_readonly() -> Dict[str, Any]:
    """TEMPORARY: inspect disk walk submissions on deploy (e.g. Render). Read-only."""
    try:
        dir_exists = WALK_SUBMISSIONS_DIR.is_dir()
        files: List[str] = []
        if dir_exists:
            files = sorted(
                p.name for p in WALK_SUBMISSIONS_DIR.iterdir() if p.is_file()
            )
        index_contents: Any = []
        count = 0
        if WALK_SUBMISSIONS_INDEX_PATH.is_file():
            raw = json.loads(WALK_SUBMISSIONS_INDEX_PATH.read_text(encoding="utf-8"))
            index_contents = raw
            if isinstance(raw, dict) and isinstance(raw.get("submissions"), list):
                count = len(raw["submissions"])
            elif isinstance(raw, list):
                count = len(raw)
        return {
            "count": count,
            "index": index_contents,
            "dir_exists": dir_exists,
            "files": files,
        }
    except Exception as e:
        return {
            "count": 0,
            "index": [],
            "dir_exists": False,
            "files": [],
            "error": str(e),
        }


# ---------------------------------------------------------------------------
# MVP bore-log read endpoint.
# Surfaces a walk session's saved station events as structured bore-log rows,
# joined to the per-station photo count. Read-only: does not mutate session
# state, walk submissions, or the photo index. Reuses existing helpers
# (_walk_submission_sid, _load_walk_submission_doc, _load_station_photo_index,
# _normalize_station_text, _station_to_feet) — no new persistence path.
# ---------------------------------------------------------------------------


def _walk_bore_log_iso_from_ts(ts_value: Any) -> Optional[str]:
    """Convert a station-event timestamp (ms epoch int, ISO string, or other)
    into an ISO-8601 UTC string. Returns None when the value is unusable."""
    if ts_value is None:
        return None
    if isinstance(ts_value, bool):
        return None
    if isinstance(ts_value, (int, float)):
        try:
            fv = float(ts_value)
        except (TypeError, ValueError):
            return None
        if math.isnan(fv) or math.isinf(fv):
            return None
        # Walk-v2 / walk send millisecond epoch ints; tolerate seconds too.
        seconds = fv / 1000.0 if fv > 1e11 else fv
        try:
            return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(ts_value, str):
        text = ts_value.strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return text
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    return None


@protected_router.get("/api/walk-sessions/{session_id}/bore-log")
def get_walk_session_bore_log(session_id: str) -> List[Dict[str, Any]]:
    """MVP: walk session → structured bore-log rows.

    Pure read; never mutates session state, walk submissions, or photo index.
    Does not synthesize stations the field crew never saved.
    """
    sid = str(session_id or "").strip()
    if not sid:
        return []

    safe_sid = _walk_submission_sid(sid)
    if not safe_sid:
        return []

    doc = _load_walk_submission_doc(f"{safe_sid}.json")
    if not isinstance(doc, dict):
        return []

    raw_events = doc.get("walk_station_events")
    if not isinstance(raw_events, list):
        return []

    # Build per-station-label photo counts scoped to this session in one pass
    # over the photo index, so we don't re-scan per station.
    photo_counts_by_label: Dict[str, int] = {}
    try:
        photo_index = _load_station_photo_index()
    except Exception:
        photo_index = {"photos": []}
    for record in (photo_index.get("photos") or []):
        if not isinstance(record, dict):
            continue
        if str(record.get("session_id") or "").strip() != sid:
            continue
        label = str(record.get("station_label") or "").strip()
        if not label:
            continue
        photo_counts_by_label[label] = photo_counts_by_label.get(label, 0) + 1

    rows: List[Dict[str, Any]] = []
    for ev in raw_events:
        if not isinstance(ev, dict):
            continue
        station_label = str(ev.get("station_number") or "").strip()
        if not station_label:
            continue
        station_ft = _station_to_feet(station_label)
        if station_ft is None:
            # Spec: skip rows without a resolvable station_ft.
            continue

        depth_raw = ev.get("depth_ft")
        depth_ft: Optional[float]
        try:
            depth_ft = float(depth_raw) if depth_raw is not None else None
        except (TypeError, ValueError):
            depth_ft = None

        boc_raw = ev.get("boc_ft")
        boc_ft: Optional[float]
        try:
            boc_ft = float(boc_raw) if boc_raw is not None else None
        except (TypeError, ValueError):
            boc_ft = None

        notes = str(ev.get("note") or "").strip()
        timestamp_iso = _walk_bore_log_iso_from_ts(ev.get("ts"))

        rows.append({
            "station": station_label,
            "station_ft": float(station_ft),
            "depth_ft": depth_ft,
            "boc_ft": boc_ft,
            "notes": notes,
            "photo_count": int(photo_counts_by_label.get(station_label, 0)),
            "timestamp": timestamp_iso,
        })

    rows.sort(key=lambda r: float(r.get("station_ft") or 0.0))
    return rows


# ---------------------------------------------------------------------------
# Temporary office dashboard endpoints.
# Added as a minimal self-contained block at the bottom of the file so nothing
# above this line is modified. Remove or replace this section once the real
# jobs/session/station persistence layer ships.
# ---------------------------------------------------------------------------

def _office_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _office_routes_payload() -> List[Dict[str, Any]]:
    return _routes_payload_from_catalog(STATE.get("route_catalog", []) or [])


def _office_field_session_ids_for_job(job_id: str) -> set[str]:
    """session_id values from persisted walk submissions for this job (field walks)."""
    out: set[str] = set()
    try:
        subs = _load_walk_submissions_for_job(job_id)
    except Exception:
        return out
    for sub in subs:
        if not isinstance(sub, dict):
            continue
        sid = str(sub.get("session_id") or "").strip()
        if sid:
            out.add(sid)
    return out


def _office_disk_session_photo_aggregate(field_session_id: str) -> Tuple[int, Optional[str]]:
    """Count + latest file URL for station photos tied to a field walk session_id."""
    sid = str(field_session_id or "").strip()
    if not sid:
        return 0, None
    try:
        index_data = _load_station_photo_index()
    except Exception:
        return 0, None
    raw = index_data.get("photos") if isinstance(index_data, dict) else None
    records: List[Dict[str, Any]] = [
        r for r in (raw or []) if isinstance(r, dict)
    ]
    matching = [
        r
        for r in records
        if _station_photo_record_matches_session(r, sid)
        and _station_photo_record_is_valid(r)
    ]
    if not matching:
        return 0, None
    matching.sort(
        key=lambda rec: str(rec.get("uploaded_at") or ""),
        reverse=True,
    )
    return len(matching), _station_photo_record_public_url(matching[0])


def _office_disk_walk_station_list(job_id: str) -> List[Dict[str, Any]]:
    """Stations from all persisted walk submissions for this job (each row tagged with session_id)."""
    stations: List[Dict[str, Any]] = []
    try:
        disk_submissions = _load_walk_submissions_for_job(job_id)
    except Exception:
        return stations
    if not disk_submissions:
        return stations
    next_i = 1
    for sub in disk_submissions:
        if not isinstance(sub, dict):
            continue
        try:
            doc = _load_walk_submission_doc(str(sub.get("filename") or ""))
        except Exception:
            continue
        if not doc:
            continue
        fsid = str(doc.get("session_id") or sub.get("session_id") or "").strip()
        walk_events = doc.get("walk_station_events") or []
        if not isinstance(walk_events, list):
            continue
        for ev in walk_events[:50]:
            if not isinstance(ev, dict):
                continue
            try:
                lat = float(ev.get("lat") or ev.get("latitude") or 0.0)
                lon = float(ev.get("lon") or ev.get("longitude") or 0.0)
            except (TypeError, ValueError):
                continue
            row: Dict[str, Any] = {
                "id": f"{job_id}-walk-station-{next_i}",
                "station_number": str(ev.get("station_number") or f"{next_i}+00"),
                "depth_ft": ev.get("depth_ft"),
                "boc_ft": ev.get("boc_ft"),
                "latitude": lat,
                "longitude": lon,
                "review_status": "auto_ok",
            }
            if fsid:
                row["session_id"] = fsid
            stations.append(row)
            next_i += 1
    return stations


def _office_sessions_payload(job_id: str, session_id: str) -> List[Dict[str, Any]]:
    # Temporary mocked session derived from current route presence so the office
    # UI can render with believable data before the real walk/session backend is ready.
    routes = _office_routes_payload()
    track_geometry = None
    latest_photo_url: Optional[str] = None
    photo_count = 0

    stations = _office_stations_payload(job_id, routes)
    station_identity_hashes: set[str] = set()

    default_route_name = str(STATE.get("route_name") or (routes[0].get("route_name") if routes else "") or "").strip()

    for station in stations:
        identity_raw = _station_photo_identity_raw(
            default_route_name,
            station.get("source_file"),
            station.get("station_number"),
            station.get("mapped_station_ft"),
            station.get("latitude"),
            station.get("longitude"),
        )
        identity_hash = _station_photo_identity_hash(identity_raw, session_id)
        if identity_hash:
            station_identity_hashes.add(identity_hash)

    for point in list(STATE.get("station_points") or []):
        identity_raw = _station_photo_identity_raw(
            point.get("route_name") or default_route_name,
            point.get("source_file"),
            point.get("station") or point.get("station_label"),
            point.get("mapped_station_ft"),
            point.get("lat"),
            point.get("lon"),
        )
        identity_hash = _station_photo_identity_hash(identity_raw, session_id)
        if identity_hash:
            station_identity_hashes.add(identity_hash)

    station_photo_index = _load_station_photo_index()
    station_photo_records = list(station_photo_index.get("photos") or [])
    valid_photo_records = [
        record
        for record in station_photo_records
        if _station_photo_record_matches_session(record, session_id)
        and str(record.get("station_identity_hash") or "").strip()
        and str(record.get("stored_filename") or "").strip()
        and _station_photo_record_is_valid(record)
    ]

    matched_photo_records = [
        record
        for record in valid_photo_records
        if str(record.get("station_identity_hash") or "").strip() in station_identity_hashes
    ]

    # V1 office proof fallback stays within the active anonymous browser session.
    selected_photo_records = matched_photo_records if matched_photo_records else valid_photo_records
    photo_count = len(selected_photo_records)

    if selected_photo_records:
        sorted_photos = sorted(
            selected_photo_records,
            key=lambda record: str(record.get("uploaded_at") or ""),
            reverse=True,
        )
        newest = sorted_photos[0]
        latest_photo_url = _station_photo_record_public_url(newest)

    if routes and routes[0].get("geometry", {}).get("coordinates"):
        coords = routes[0]["geometry"]["coordinates"]
        track_geometry = {"type": "LineString", "coordinates": coords[: min(len(coords), 8)]}

    # Real field submissions from disk — visible across all devices regardless of
    # which KMZ (if any) the office browser has loaded in its own session.
    disk_submissions = _load_walk_submissions_for_job(job_id)
    disk_sessions: List[Dict[str, Any]] = []
    for sub in disk_submissions:
        doc = _load_walk_submission_doc(str(sub.get("filename") or ""))
        sub_track = (doc.get("track_geometry") if doc else None) or sub.get("track_geometry")
        fsid = str(sub.get("session_id") or "").strip() or f"{job_id}-disk-session"
        p_count, p_latest = _office_disk_session_photo_aggregate(fsid)
        disk_sessions.append({
            "id": fsid,
            "crew_name": str(sub.get("crew") or "Field Crew"),
            "status": "ended",
            "started_at": str(sub.get("ended_at") or _office_iso_now()),
            "ended_at": str(sub.get("ended_at") or _office_iso_now()),
            "station_count": int(sub.get("station_count") or 0),
            "photo_count": p_count,
            "latest_photo_url": p_latest,
            "track_point_count": len(sub_track.get("coordinates", [])) if isinstance(sub_track, dict) else 0,
            "track_geometry": sub_track,
        })
    if disk_sessions:
        return disk_sessions

    # Fallback: mocked session from the office browser's own in-memory state.
    # Only shown when no real field submissions exist yet so existing behaviour
    # is preserved for sessions that pre-date disk persistence.
    if not routes:
        return []
    station_count = len(STATE.get("station_points") or []) or 3
    return [
        {
            "id": f"{job_id}-session-1",
            "crew_name": "Crew A",
            "status": "ended",
            "started_at": _office_iso_now(),
            "ended_at": _office_iso_now(),
            "station_count": station_count,
            "photo_count": photo_count,
            "latest_photo_url": latest_photo_url,
            "track_point_count": len(track_geometry.get("coordinates", [])) if track_geometry else 0,
            "track_geometry": track_geometry,
        }
    ]


def _office_stations_payload(job_id: str, routes: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    station_points = list(STATE.get("station_points") or [])
    stations: List[Dict[str, Any]] = []

    # Load persisted walk events once — used both for label override in the
    # station_points branch and as the primary fallback when station_points is empty.
    walk_extra = _office_disk_walk_station_list(job_id)

    if station_points:
        # Build coord-keyed lookup of real field station_numbers from disk walk events
        # so station_points rows lacking real labels get the field-entered value instead
        # of a synthetic placeholder.
        disk_label_by_coord = {}
        for _we in walk_extra:
            try:
                _wlat = round(float(_we.get("latitude") or 0.0), 4)
                _wlon = round(float(_we.get("longitude") or 0.0), 4)
            except (TypeError, ValueError):
                continue
            _wsn = str(_we.get("station_number") or "").strip()
            if _wsn and (_wlat, _wlon) != (0.0, 0.0):
                disk_label_by_coord[(_wlat, _wlon)] = _wsn

        for idx, point in enumerate(station_points[:10], start=1):
            pt_lat = float(point.get("lat") or 0.0)
            pt_lon = float(point.get("lon") or 0.0)
            # Prefer: office-entered label → matching disk walk label → neutral placeholder
            label = (
                str(point.get("station") or point.get("station_label") or "").strip()
                or disk_label_by_coord.get((round(pt_lat, 4), round(pt_lon, 4)), "")
                or "—"
            )
            stations.append(
                {
                    "id": str(point.get("station_id") or f"{job_id}-station-{idx}"),
                    "station_number": label,
                    "depth_ft": point.get("depth_ft"),
                    "boc_ft": point.get("boc_ft"),
                    "latitude": pt_lat,
                    "longitude": pt_lon,
                    "review_status": str(point.get("review_status") or "auto_ok"),
                }
            )
        if walk_extra:
            seen = {
                (
                    str(s.get("station_number") or ""),
                    round(float(s.get("latitude") or 0.0), 4),
                    round(float(s.get("longitude") or 0.0), 4),
                )
                for s in stations
            }
            next_i = len(stations) + 1
            for w in walk_extra:
                key = (
                    str(w.get("station_number") or ""),
                    round(float(w.get("latitude") or 0.0), 4),
                    round(float(w.get("longitude") or 0.0), 4),
                )
                if key in seen:
                    continue
                seen.add(key)
                row = dict(w)
                row["id"] = f"{job_id}-walk-station-{next_i}"
                next_i += 1
                stations.append(row)
        return stations

    # Walk-submission fallback: use station_events from the most recent persisted
    # field walk when the office session has no committed station_points of its own.
    for idx, ev_row in enumerate(walk_extra, start=1):
        row = dict(ev_row)
        row["id"] = f"{job_id}-walk-station-{idx}"
        stations.append(row)
    if stations:
        return stations

    # Coord-fallback: synthesise placeholder stations from route geometry so
    # the UI has something to render before any field data arrives.
    if routes:
        coords = routes[0].get("geometry", {}).get("coordinates") or []
        for idx, coord in enumerate(coords[:3], start=1):
            stations.append(
                {
                    "id": f"{job_id}-station-{idx}",
                    "station_number": f"route point {idx}",
                    "depth_ft": 4.0 + idx * 0.5,
                    "boc_ft": 2.0,
                    "latitude": float(coord[1]),
                    "longitude": float(coord[0]),
                    "review_status": "auto_ok" if idx < 3 else "needs_review",
                }
            )
    return stations


def _office_photos_payload(
    job_id: str,
    stations: Sequence[Dict[str, Any]],
    office_session_id: str = "",
) -> List[Dict[str, Any]]:
    """Photos from station_photos index scoped to this job's field sessions + office session."""
    try:
        index_data = _load_station_photo_index()
    except Exception:
        index_data = {"photos": []}
    raw = index_data.get("photos") if isinstance(index_data, dict) else None
    if not isinstance(raw, list):
        raw = []
    records: List[Dict[str, Any]] = [r for r in raw if isinstance(r, dict)]

    scope_ids: set[str] = set(_office_field_session_ids_for_job(job_id))
    osid = str(office_session_id or "").strip()
    if osid:
        scope_ids.add(osid)

    if not scope_ids:
        return []

    stations_list = list(stations) if stations else []
    keyed: List[Tuple[str, Dict[str, Any]]] = []

    for record in records:
        rid = str(record.get("session_id") or "").strip()
        if not rid or rid not in scope_ids:
            continue
        if not _station_photo_record_is_valid(record):
            continue
        photo_id = str(record.get("photo_id") or "").strip()
        if not photo_id:
            continue
        try:
            original_lat = float(str(record.get("lat") or "").strip() or 0)
            original_lon = float(str(record.get("lon") or "").strip() or 0)
        except (TypeError, ValueError):
            original_lat, original_lon = 0.0, 0.0
        adjusted_lat = _office_float_or_none(record.get("adjusted_lat"))
        adjusted_lon = _office_float_or_none(record.get("adjusted_lon"))
        is_adjusted = adjusted_lat is not None and adjusted_lon is not None
        lat_val = adjusted_lat if is_adjusted else original_lat
        lon_val = adjusted_lon if is_adjusted else original_lon
        thumb = _station_photo_record_public_url(record)
        station_id_match: Optional[str] = None
        slabel = str(record.get("station_label") or "").strip()
        if slabel:
            for st in stations_list:
                if str(st.get("station_number") or "").strip() == slabel:
                    sid_m = st.get("id")
                    station_id_match = str(sid_m) if sid_m is not None else None
                    break
        photo_obj: Dict[str, Any] = {
            "id": photo_id,
            "station_id": station_id_match,
            "latitude": lat_val,
            "longitude": lon_val,
            "original_lat": original_lat,
            "original_lon": original_lon,
            "adjusted_lat": adjusted_lat,
            "adjusted_lon": adjusted_lon,
            "adjusted_at": str(record.get("adjusted_at") or "") or None,
            "is_adjusted": is_adjusted,
            "thumbnail_url": thumb,
            "session_id": rid,
            "uploaded_at": str(record.get("uploaded_at") or ""),
            "station_label": slabel,
        }
        note_val = str(record.get("note") or "").strip()
        if note_val:
            photo_obj["note"] = note_val
        keyed.append((str(record.get("uploaded_at") or ""), photo_obj))

    keyed.sort(key=lambda x: x[0], reverse=True)
    return [item[1] for item in keyed]


REVIEWER_EXCEPTION_ROOT = UPLOADS_DIR / "reviewer_exceptions"
REVIEWER_EXCEPTION_INDEX_PATH = REVIEWER_EXCEPTION_ROOT / "index.json"
REVIEWER_EXCEPTION_SEVERITIES = {"low", "medium", "high", "critical"}


def _ensure_reviewer_exception_storage() -> None:
    REVIEWER_EXCEPTION_ROOT.mkdir(parents=True, exist_ok=True)
    if not REVIEWER_EXCEPTION_INDEX_PATH.exists():
        REVIEWER_EXCEPTION_INDEX_PATH.write_text(
            json.dumps({"exceptions": []}, indent=2),
            encoding="utf-8",
        )


def _load_reviewer_exception_index() -> Dict[str, Any]:
    _ensure_reviewer_exception_storage()
    try:
        data = json.loads(REVIEWER_EXCEPTION_INDEX_PATH.read_text(encoding="utf-8"))
    except Exception:
        data = {"exceptions": []}
    if not isinstance(data, dict):
        data = {"exceptions": []}
    if not isinstance(data.get("exceptions"), list):
        data["exceptions"] = []
    return data


def _save_reviewer_exception_index(data: Dict[str, Any]) -> None:
    _ensure_reviewer_exception_storage()
    temp_path = REVIEWER_EXCEPTION_INDEX_PATH.with_suffix(".tmp")
    temp_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    temp_path.replace(REVIEWER_EXCEPTION_INDEX_PATH)


def _office_float_or_none(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _office_public_exception_record(record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(record.get("id") or ""),
        "exception_type": str(record.get("exception_type") or "reviewer_qa_issue"),
        "severity": str(record.get("severity") or "medium"),
        "status": str(record.get("status") or "open"),
        "description": str(record.get("description") or ""),
        "latitude": record.get("latitude"),
        "longitude": record.get("longitude"),
        "job_id": str(record.get("job_id") or ""),
        "session_id": str(record.get("session_id") or ""),
        "source": str(record.get("source") or "office_review"),
        "created_at": str(record.get("created_at") or ""),
    }


def _office_reviewer_exceptions_payload(job_id: str) -> List[Dict[str, Any]]:
    safe_job_id = str(job_id or "").strip()
    if not safe_job_id:
        return []
    data = _load_reviewer_exception_index()
    matches = [
        _office_public_exception_record(record)
        for record in data.get("exceptions", [])
        if str(record.get("job_id") or "").strip() == safe_job_id
    ]
    matches.sort(key=lambda item: str(item.get("created_at") or ""))
    return matches


def _office_exceptions_payload(job_id: str, stations: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    for station in stations:
        if str(station.get("review_status") or "") == "needs_review":
            return [
                {
                    "id": f"{job_id}-exception-1",
                    "exception_type": "station_needs_review",
                    "severity": "medium",
                    "status": "open",
                    "description": f"Station {station.get('station_number')} needs review.",
                    "latitude": station.get("latitude"),
                    "longitude": station.get("longitude"),
                }
            ]
    return []


def _office_artifacts_payload(job_id: str) -> List[Dict[str, Any]]:
    return [
        {
            "id": f"{job_id}-artifact-closeout-1",
            "artifact_type": "closeout_pdf",
            "version_number": 1,
            "generation_status": "complete",
            "file_url": None,
            "created_at": _office_iso_now(),
        },
        {
            "id": f"{job_id}-artifact-qa-1",
            "artifact_type": "qa_summary_pdf",
            "version_number": 1,
            "generation_status": "queued",
            "file_url": None,
            "created_at": _office_iso_now(),
        },
    ]


@app.get("/jobs")
def get_jobs(session_id: Optional[str] = None) -> List[Dict[str, Any]]:
    resolved_session_id = _resolve_session_id(session_id)
    with _session_scope(resolved_session_id):
        routes = _office_routes_payload()
        stations = _office_stations_payload("test-job", routes)
        exceptions = _office_exceptions_payload("test-job", stations)
        exceptions.extend(_office_reviewer_exceptions_payload("test-job"))
        sessions = _office_sessions_payload("test-job", resolved_session_id)
        return [
            {
                "id": "test-job",
                "job_code": "TEST-001",
                "job_name": "Test Job",
                "status": "in_progress",
                "route_count": len(routes),
                "session_count": len(sessions),
                "exception_count": len(exceptions),
                "last_sync_at": _office_iso_now(),
            }
        ]


@protected_router.post("/jobs/{job_id}/exceptions")
def create_job_exception(job_id: str, payload: Dict[str, Any] = Body(...)) -> JSONResponse:
    safe_job_id = str(job_id or "").strip()
    if not safe_job_id:
        return _err("job_id is required.", status_code=400)
    if not isinstance(payload, dict):
        return _err("JSON body is required.", status_code=400)

    session_id = str(payload.get("session_id") or "").strip()
    description = str(payload.get("description") or "").strip()
    severity = str(payload.get("severity") or "medium").strip().lower()
    if not session_id:
        return _err("session_id is required.", status_code=400)
    if not description:
        return _err("description is required.", status_code=400)
    if severity not in REVIEWER_EXCEPTION_SEVERITIES:
        return _err("severity must be low, medium, high, or critical.", status_code=400)

    resolved_scope = _resolve_session_id(session_id)
    with _session_scope(resolved_scope):
        if _is_closeout_locked():
            return _json_closeout_locked_response()

    record = {
        "id": f"{safe_job_id}-reviewer-exception-{uuid.uuid4().hex[:12]}",
        "exception_type": "reviewer_qa_issue",
        "severity": severity,
        "status": "open",
        "description": description[:1000],
        "latitude": _office_float_or_none(payload.get("latitude")),
        "longitude": _office_float_or_none(payload.get("longitude")),
        "job_id": safe_job_id,
        "session_id": session_id,
        "source": "office_review",
        "created_at": _office_iso_now(),
    }

    try:
        data = _load_reviewer_exception_index()
        data["exceptions"].append(record)
        _save_reviewer_exception_index(data)
    except Exception as exc:
        return _err(f"Failed to persist reviewer exception: {exc}", status_code=500)

    return JSONResponse(content=_office_public_exception_record(record), status_code=201)


@app.get("/jobs/{job_id}")
def get_job_by_id(job_id: str, session_id: Optional[str] = None) -> Dict[str, Any]:
    resolved_session_id = _resolve_session_id(session_id)
    with _session_scope(resolved_session_id):
        safe_job_id = str(job_id or "test-job").strip() or "test-job"
        routes = _office_routes_payload()
        sessions = _office_sessions_payload(safe_job_id, resolved_session_id)
        stations = _office_stations_payload(safe_job_id, routes)
        photos = _office_photos_payload(safe_job_id, stations, resolved_session_id)
        exceptions = _office_exceptions_payload(safe_job_id, stations)
        exceptions.extend(_office_reviewer_exceptions_payload(safe_job_id))
        artifacts = _office_artifacts_payload(safe_job_id)

        return {
            "id": safe_job_id,
            "job_code": "TEST-001",
            "job_name": "Test Job",
            "status": "in_progress",
            "routes": routes,
            "sessions": sessions,
            "stations": stations,
            "photos": photos,
            "exceptions": exceptions,
            "artifacts": artifacts,
            **_closeout_flat_fields(),
        }


# ---------------------------------------------------------------------------
# Read-only V1 engineered-path endpoint.
# Surgical, reversible: this entire block can be deleted to revert.
# Reads-only — does not mutate session state, GPS breadcrumbs, or any storage.
# Uses a lazy import to avoid any circular-import risk with the
# app.services.engineered_segments module (which itself lazy-imports main).
# ---------------------------------------------------------------------------

import logging as _engineered_segments_logging

_engineered_segments_logger = _engineered_segments_logging.getLogger("engineered_segments")


@protected_router.get("/api/engineered-segments")
def get_engineered_segments(session_id: Optional[str] = Query(None)) -> Dict[str, Any]:
    sid = str(session_id or "").strip()
    if not sid:
        return {"session_id": "", "segments": []}
    try:
        from app.services.engineered_segments import build_engineered_segments
        segments = build_engineered_segments(sid)
    except Exception as exc:
        _engineered_segments_logger.exception(
            "engineered_segments_failed for session_id=%s: %s", sid, exc
        )
        return {
            "session_id": sid,
            "segments": [],
            "error": "engineered_segments_failed",
        }
    if not isinstance(segments, list):
        segments = []
    return {"session_id": sid, "segments": segments}
