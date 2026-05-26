"""Engineering plan overlay payload envelope builder.

VO.1a backend half of the PDF Visual Overlay sprint.

Authoritative design contract:
    wiki/sprints/visual-overlay/vo-0-design-packet.md §3
Authoritative implementation plan:
    wiki/sprints/visual-overlay/vo-1a-implementation-plan.md

Public surface (one function):

    build_engineering_plan_overlay_envelope(session_id: str) -> Dict[str, Any]

Returned envelope shape (payload-schema "engineering-plan-overlay-1"):

    {
      "schema": "engineering-plan-overlay-1",
      "topology_source": <str — see behavior matrix below>,
      "plan_set_signature": <str | None>,
      "generated_at": <ISO-8601 UTC>,
      "sheets": [...],
      "pdfs": [...],
      "pages": [...]
    }

Behavior matrix:

    TRUELINE_PLAN_PDF_PARSE != "1" (default production) →
        empty envelope, topology_source = "bypassed_flag_off"
    Parse flag on, session_id empty / main module unresolvable →
        empty envelope, topology_source = "bypassed_flag_off"
    Parse flag on, no PDFs uploaded for this session →
        empty envelope, topology_source = "bypassed_other_scope"
    Parse flag on, cache absent / corrupt / schema mismatch / signature stale →
        empty envelope, topology_source = "rows_only_cache_miss_empty"
    Parse flag on, cache hit with matching signature →
        populated envelope, topology_source = "cache_hit"

PURE-READ contract:
    - Never invokes the PDF parser.
    - Never writes the topology cache.
    - Never mutates STATE.
    - Never raises; on any internal exception returns an empty envelope.
    - Single env-var read (TRUELINE_PLAN_PDF_PARSE).
    - Filesystem I/O limited to the cache file READ via
      plan_topology_cache.cache_read_full.

Tenant scoping inherited from main._resolve_engineering_plan_pdf_paths and
main._load_engineering_plan_index_for_session.  This module does not
introduce a new tenant surface.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List

from app.core import plan_topology_cache


_SCHEMA_VERSION: str = "engineering-plan-overlay-1"


def _empty_envelope(topology_source: str, generated_at: str) -> Dict[str, Any]:
    """Return a fresh empty envelope with the given topology_source."""
    return {
        "schema": _SCHEMA_VERSION,
        "topology_source": topology_source,
        "plan_set_signature": None,
        "generated_at": generated_at,
        "sheets": [],
        "pdfs": [],
        "pages": [],
    }


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _resolve_main_module() -> Any:
    """Look up the imported main module via sys.modules so that test
    monkey-patches on main.<name> and production callers resolve to the
    same callable.  Tries both the package-qualified name (used by the
    pytest runner: ``from backend import main as M``) and the bare name
    (used when main is run as the uvicorn entry).

    Returns None when no candidate is in sys.modules — in which case the
    envelope builder falls back to the empty envelope path.  This keeps
    the helper safe to import in contexts where main is not loaded.
    """
    return (
        sys.modules.get("backend.main")
        or sys.modules.get("main")
        or sys.modules.get("__main__")
    )


def build_engineering_plan_overlay_envelope(session_id: str) -> Dict[str, Any]:
    """Build the ``engineering_plan_overlay`` envelope for a session.

    See module docstring for the full behavior matrix.  Never raises.
    """
    _generated_at = datetime.now(timezone.utc).isoformat()

    try:
        # Gate 1: parse flag off → bypassed_flag_off (default production).
        if (
            os.environ.get("TRUELINE_PLAN_PDF_PARSE", "").strip().lower()
            not in {"1", "true", "yes", "on"}
        ):
            return _empty_envelope("bypassed_flag_off", _generated_at)

        sid = str(session_id or "").strip()
        if not sid:
            return _empty_envelope("bypassed_flag_off", _generated_at)

        _main = _resolve_main_module()
        if _main is None:
            return _empty_envelope("bypassed_flag_off", _generated_at)

        # UPLOADS_DIR is resolved via the imported main module rather than
        # via a direct import so monkey-patched test environments see the
        # same constant the production rebuild path uses.
        uploads_dir = getattr(_main, "UPLOADS_DIR", None)
        if uploads_dir is None:
            return _empty_envelope("bypassed_flag_off", _generated_at)

        try:
            paths = _main._resolve_engineering_plan_pdf_paths(sid)
        except Exception:
            paths = []
        try:
            plans_metadata = _main._load_engineering_plan_index_for_session(sid)
        except Exception:
            plans_metadata = []

        if not paths:
            # Parse flag on but no PDFs uploaded for this session.
            return _empty_envelope("bypassed_other_scope", _generated_at)

        cache_file = plan_topology_cache.resolve_cache_file(sid, uploads_dir)
        full = plan_topology_cache.cache_read_full(cache_file)
        expected_signature = plan_topology_cache.derive_plan_set_signature(
            plans_metadata or []
        )

        if full is None:
            # Cache absent / corrupt / schema mismatch.
            return _empty_envelope("rows_only_cache_miss_empty", _generated_at)

        cache_signature = full.get("plan_set_signature")
        if cache_signature != expected_signature:
            # Stale cache; matches the rebuild's MISS_STALE handling.
            return _empty_envelope("rows_only_cache_miss_empty", _generated_at)

        topology = full.get("topology") or {}
        pdf_outcomes = full.get("pdf_outcomes") or []
        per_page_outcomes = full.get("per_page_outcomes") or []

        plans_by_index: Dict[int, Dict[str, Any]] = {}
        for idx, plan in enumerate(plans_metadata or []):
            plans_by_index[idx] = plan if isinstance(plan, dict) else {}

        # sheets[] — derived from topology dict (sheet_number → sheet_meta).
        sheets: List[Dict[str, Any]] = []
        if isinstance(topology, dict):
            for sheet_key, sheet_meta in topology.items():
                try:
                    sheet_number = int(sheet_key)
                except (TypeError, ValueError):
                    continue
                if not isinstance(sheet_meta, dict):
                    continue
                _confidence = sheet_meta.get("confidence")
                if _confidence is None:
                    _confidence_val: Any = None
                else:
                    try:
                        _confidence_val = float(_confidence)
                    except (TypeError, ValueError):
                        _confidence_val = None
                sheets.append({
                    "sheet_number": sheet_number,
                    "anchor_station_ft": _safe_float(sheet_meta.get("anchor_station_ft")),
                    "span_ft": _safe_float(sheet_meta.get("span_ft")),
                    "source_pdf_index": _safe_int(sheet_meta.get("source_pdf_index")),
                    "source_page_index": _safe_int(sheet_meta.get("source_page_index")),
                    "confidence": _confidence_val,
                })
        sheets.sort(
            key=lambda s: (
                s["sheet_number"],
                s["source_pdf_index"],
                s["source_page_index"],
            )
        )

        # pdfs[] — from pdf_outcomes, joined with plans_metadata via pdf_index.
        pdfs: List[Dict[str, Any]] = []
        for outcome in pdf_outcomes:
            if not isinstance(outcome, dict):
                continue
            pdf_idx = _safe_int(outcome.get("pdf_index"))
            plan = plans_by_index.get(pdf_idx, {})
            pdfs.append({
                "pdf_index": pdf_idx,
                "plan_id": str(plan.get("plan_id") or ""),
                "original_filename": str(plan.get("original_filename") or ""),
                "page_count": _safe_int(outcome.get("page_count")),
                "pages_ok": _safe_int(outcome.get("pages_ok")),
                "pages_timeout": _safe_int(outcome.get("pages_timeout")),
                "pages_error": _safe_int(outcome.get("pages_error")),
                "pages_skipped": _safe_int(outcome.get("pages_skipped")),
                "total_matchlines": _safe_int(outcome.get("total_matchlines")),
                "total_callouts": _safe_int(outcome.get("total_callouts")),
                "bounded_by": outcome.get("bounded_by"),
                "elapsed_ms": _safe_int(outcome.get("elapsed_ms")),
            })

        # pages[] — from per_page_outcomes (status / text_len / error).
        pages: List[Dict[str, Any]] = []
        for page_out in per_page_outcomes:
            if not isinstance(page_out, dict):
                continue
            pages.append({
                "pdf_index": _safe_int(page_out.get("pdf_index")),
                "page_index": _safe_int(page_out.get("page_index")),
                "status": str(page_out.get("status") or "ok"),
                "text_len": _safe_int(page_out.get("text_len")),
                "error": page_out.get("error"),
            })

        # plan_set_signature surfaced as the short prefix for operator
        # debug only; matches the rebuild's log convention.
        sig_short = (
            expected_signature[:16]
            if isinstance(expected_signature, str) and expected_signature
            else None
        )

        return {
            "schema": _SCHEMA_VERSION,
            "topology_source": "cache_hit",
            "plan_set_signature": sig_short,
            "generated_at": _generated_at,
            "sheets": sheets,
            "pdfs": pdfs,
            "pages": pages,
        }
    except Exception:
        # Pure-read helper contract: never raise.  Fall back to empty
        # envelope with the conservative "bypassed_flag_off" classification.
        return _empty_envelope("bypassed_flag_off", _generated_at)
