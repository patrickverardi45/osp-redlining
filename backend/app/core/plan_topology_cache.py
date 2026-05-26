"""Plan topology cache module.

Disk-resident, signature-keyed cache for plan topology derived from
engineering-plan PDFs. RI.2 ships the cache as a passive utility:
nothing in the production rebuild path reads or writes the cache yet.
RI.3 (KMZ caller migration) is the first consumer; RI.4 (bore-log
migration) is the load-bearing consumer that resolves B-WS-12
structurally.

Design contract (mirrors wiki/sprints/rebuild-isolation/RI-2-topology-cache.md):

- Pure utility: no imports from backend.main, no STATE access, no
  PDF-parser invocation, no env-var enforcement (the kill-switch
  helper is a query function only; callers decide policy).
- Cache file layout: <uploads_dir>/topology_cache/<session_id>.json
- Cache key: SHA256 over canonicalized plan-set metadata
  (plan_id, stored_filename, size_bytes, uploaded_at).
- Atomic write via os.replace; tmp file uses a per-call uuid suffix.
- Hard size cap on serialized payload (MAX_TOPOLOGY_BYTES).
- Schema-versioned; read-side treats schema mismatch as a miss.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional, Sequence


SCHEMA_VERSION: str = "plan-topology-cache-2"
MAX_TOPOLOGY_BYTES: int = 5 * 1024 * 1024  # 5 MB hard cap on serialized cache payload
CACHE_DIRNAME: str = "topology_cache"
KILL_SWITCH_ENV: str = "TRUELINE_REBUILD_CACHE_DISABLE"

# PE.3 schema-bump constants — kept distinct from the active SCHEMA_VERSION
# so tests / migrations can reference v1 explicitly.
_SCHEMA_VERSION_V1: str = "plan-topology-cache-1"
_SCHEMA_VERSION_V2: str = "plan-topology-cache-2"

_logger = logging.getLogger(__name__)


class CacheWriteResult(str, Enum):
    """Structured outcome of cache_write. Telemetry-friendly; never raises."""

    WRITTEN = "written"
    REFUSED_OVERSIZE = "refused_oversize"
    REFUSED_INVALID = "refused_invalid"
    ERROR_IO = "error_io"


def resolve_cache_file(session_id: str, uploads_dir: Path) -> Path:
    """Return the canonical cache file path for a session.

    Layout: <uploads_dir>/topology_cache/<session_id>.json
    Does NOT create the directory; cache_write does that on first write.
    """
    return Path(uploads_dir) / CACHE_DIRNAME / f"{str(session_id)}.json"


def derive_plan_set_signature(plans: Sequence[Dict[str, Any]]) -> str:
    """Compute deterministic SHA256 over canonicalized plan-set metadata.

    Signature changes iff any of (plan_id, stored_filename, size_bytes,
    uploaded_at) changes on any plan, or a plan is added/removed.
    Input order does not affect the result (plans sorted by plan_id).
    Empty plan list yields the SHA256 of the empty canonical JSON array.
    """
    canonical = []
    for plan in sorted(plans or [], key=lambda p: str(p.get("plan_id") or "")):
        canonical.append({
            "plan_id":         str(plan.get("plan_id") or ""),
            "stored_filename": str(plan.get("stored_filename") or ""),
            "size_bytes":      int(plan.get("size_bytes") or 0),
            "uploaded_at":     str(plan.get("uploaded_at") or ""),
        })
    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def cache_read(
    cache_file: Path,
    current_signature: str,
) -> Optional[Dict[int, Dict[str, Any]]]:
    """Return cached topology if cache file matches current_signature; else None.

    Miss reasons (all return None; reason classification is for RI.5 telemetry):
      - MISS_ABSENT     cache file does not exist
      - MISS_IO         file read failed (OSError)
      - MISS_CORRUPT    file content is not valid JSON
      - MISS_SCHEMA     schema field mismatch
      - MISS_STALE      plan_set_signature mismatch
      - MISS_INVALID    topology field missing or malformed

    Pure: no side effects on miss. Does not delete or modify the cache file.
    """
    try:
        if not cache_file.exists():
            return None  # MISS_ABSENT
    except OSError:
        return None  # MISS_IO

    try:
        body = cache_file.read_text(encoding="utf-8")
    except OSError:
        _logger.warning("topology cache read failed: %s", cache_file)
        return None  # MISS_IO

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        _logger.warning("topology cache corrupt JSON: %s", cache_file)
        return None  # MISS_CORRUPT

    if not isinstance(payload, dict):
        return None  # MISS_INVALID

    if payload.get("schema") != SCHEMA_VERSION:
        return None  # MISS_SCHEMA

    if payload.get("plan_set_signature") != current_signature:
        return None  # MISS_STALE

    topology = payload.get("topology")
    if not isinstance(topology, dict):
        return None  # MISS_INVALID

    # JSON serializes dict int keys as strings; normalize back to ints.
    normalized: Dict[int, Dict[str, Any]] = {}
    try:
        for key, value in topology.items():
            normalized[int(key)] = value
    except (ValueError, TypeError):
        return None  # MISS_INVALID

    return normalized


def cache_read_full(cache_file: Path) -> Optional[Dict[str, Any]]:
    """VO.1a — return the full cache payload dict if readable; else None.

    Mirrors cache_read MISS classification (ABSENT / IO / CORRUPT / SCHEMA /
    INVALID) but does NOT compare plan_set_signature against an expected
    value — the caller is responsible for signature validation.  This is a
    looser contract than cache_read because VO.1a needs to surface the
    cache contents for read-only display and classify staleness via the
    envelope's topology_source field rather than treating stale as a miss.

    On hit, returns the entire on-disk payload dict including ``schema``,
    ``session_id``, ``plan_set_signature``, ``plan_count``,
    ``generated_at``, ``topology`` (with int keys normalized to match
    cache_read semantics), ``pdf_outcomes``, and ``per_page_outcomes``.

    Strictly additive: does not modify cache_read, cache_write, or any
    other public surface.  Pure read; no side effects on miss.
    """
    try:
        if not cache_file.exists():
            return None  # MISS_ABSENT
    except OSError:
        return None  # MISS_IO

    try:
        body = cache_file.read_text(encoding="utf-8")
    except OSError:
        _logger.warning("topology cache read failed: %s", cache_file)
        return None  # MISS_IO

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        _logger.warning("topology cache corrupt JSON: %s", cache_file)
        return None  # MISS_CORRUPT

    if not isinstance(payload, dict):
        return None  # MISS_INVALID

    if payload.get("schema") != SCHEMA_VERSION:
        return None  # MISS_SCHEMA

    topology = payload.get("topology")
    if not isinstance(topology, dict):
        return None  # MISS_INVALID

    # JSON serializes dict int keys as strings; normalize back to ints
    # to match cache_read's semantic contract.
    normalized: Dict[int, Dict[str, Any]] = {}
    try:
        for key, value in topology.items():
            normalized[int(key)] = value
    except (ValueError, TypeError):
        return None  # MISS_INVALID

    # Shallow copy so callers cannot accidentally mutate the in-memory
    # parse result of subsequent reads.
    result = dict(payload)
    result["topology"] = normalized
    return result


def cache_write(
    cache_file: Path,
    signature: str,
    topology: Dict[int, Dict[str, Any]],
    plan_count: int,
    compute_duration_ms: int,
    pdf_outcomes: Optional[Sequence[Dict[str, Any]]] = None,
    per_page_outcomes: Optional[Sequence[Dict[str, Any]]] = None,
) -> CacheWriteResult:
    """Atomically persist topology + signature to cache_file.

    Creates the parent directory as needed. Refuses payloads that exceed
    MAX_TOPOLOGY_BYTES. Returns a structured result on success or refusal;
    never raises (OSError is captured and returned as ERROR_IO).

    PE.3 additions (default `[]` for back-compat):
      - ``pdf_outcomes``: per-PDF aggregate outcome dicts (status, page_count,
        pages_ok/timeout/error/skipped, elapsed_ms, etc.)
      - ``per_page_outcomes``: per-page outcome dicts (pdf_index, page_index,
        status, elapsed_ms, text_len, error)

    Both fields are observational (consumed by future Visual Overlay sprint).
    The `topology` field remains the load-bearing one for current consumers.
    """
    session_id = cache_file.stem

    payload: Dict[str, Any] = {
        "schema": SCHEMA_VERSION,
        "session_id": session_id,
        "plan_set_signature": signature,
        "plan_count": int(plan_count),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by": "rebuild-isolation/v2",
        "topology_bytes": 0,
        "compute_duration_ms": int(compute_duration_ms),
        "topology": topology,
        "pdf_outcomes": list(pdf_outcomes or []),
        "per_page_outcomes": list(per_page_outcomes or []),
    }

    try:
        body = json.dumps(payload, sort_keys=True, indent=2)
        payload["topology_bytes"] = len(body.encode("utf-8"))
        body = json.dumps(payload, sort_keys=True, indent=2)
    except (TypeError, ValueError):
        return CacheWriteResult.REFUSED_INVALID

    body_bytes = body.encode("utf-8")
    if len(body_bytes) > MAX_TOPOLOGY_BYTES:
        return CacheWriteResult.REFUSED_OVERSIZE

    tmp_path: Optional[Path] = None
    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = cache_file.with_name(f"{cache_file.name}.tmp.{uuid.uuid4().hex}")
        tmp_path.write_bytes(body_bytes)
        os.replace(str(tmp_path), str(cache_file))
    except OSError:
        if tmp_path is not None:
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except OSError:
                pass
        return CacheWriteResult.ERROR_IO

    return CacheWriteResult.WRITTEN


def cache_invalidate(cache_file: Path) -> bool:
    """Delete cache_file if present. Idempotent.

    Returns True iff the file does not exist after the call (whether or
    not it existed before). Returns False only on OSError — caller may
    log and continue; signature mismatch on read provides a second line
    of defense against stale data.
    """
    try:
        if cache_file.exists():
            cache_file.unlink()
        return True
    except OSError:
        _logger.warning("topology cache invalidate failed: %s", cache_file)
        return False


def kill_switch_active() -> bool:
    """True iff TRUELINE_REBUILD_CACHE_DISABLE is set to a truthy value.

    Truthy (case-insensitive, whitespace-stripped): '1', 'true', 'yes'.
    Falsy (default): unset, empty, '0', 'false', anything else.

    The cache module itself does NOT enforce the kill switch. Callers
    query this helper before reading or writing. Keeps the cache module
    a pure utility.
    """
    raw = os.environ.get(KILL_SWITCH_ENV, "").strip().lower()
    return raw in ("1", "true", "yes")
