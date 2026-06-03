"""PDF-first Match Review evidence cache.

Disk-resident, signature-keyed cache for the PDF-first evidence envelope that
`/api/match-review-queue` attaches as ``pdf_first_evidence`` when the PDF-first
engine flag stack is ON. The endpoint currently re-runs the full PDF-first
engine + re-rasterizes every crop/overlay on EVERY request; this module lets
the endpoint skip that regeneration when nothing that affects the evidence has
changed.

Design contract (mirrors ``plan_topology_cache.py`` style):

- Pure utility: no imports from backend.main, no STATE access, no engine
  invocation, no env-var ENFORCEMENT (the kill-switch helper is a query
  function only; the endpoint decides policy). The endpoint owns the master
  ``TRUELINE_MRQ_EVIDENCE_CACHE`` flag gate; this module only provides the
  signature + read/write primitives and the disable kill switch.
- Cache file layout: ``<uploads_dir>/pdf_first_cards/<safe_session_id>/_evidence_cache.json``
  i.e. it lives INSIDE the same per-session cards dir that holds the overlay/crop
  PNGs the envelope references. (The endpoint passes a session_id already
  sanitized with its ``_safe_filename`` helper.)
- Cache key: SHA256 over canonicalized (session_id, plan_set_signature, a
  STABLE projection of the evidence-affecting committed_rows fields, the active
  PDF-first flag stack, SCHEMA_VERSION). A new bore-log upload (rows change) OR
  any flag-stack change MUST change the signature.
- Read-side validates schema + signature AND that every overlay/crop PNG
  basename referenced in the cached envelope still exists on disk in the cards
  dir; a missing artifact is treated as a miss so the endpoint regenerates.
- Atomic write via os.replace; tmp file uses a per-call uuid suffix.
- Schema-versioned; read-side treats schema mismatch as a miss.
- Never raises: cache_read returns None on ANY error; cache_write is
  best-effort and logs (never raises).

CLEANUP POLICY: ``_evidence_cache.json`` is fully regenerable and safe to
delete at any time. It lives under ``pdf_first_cards/<sid>/`` alongside the
PNGs, so any existing ``rm -rf pdf_first_cards/*`` cleanup also clears it.
A signature change (new upload or flag change) auto-invalidates it, so there
is never stale evidence after new uploads.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence


SCHEMA_VERSION: str = "pdf-first-evidence-cache-1"
CACHE_DIRNAME: str = "pdf_first_cards"
CACHE_FILENAME: str = "_evidence_cache.json"
KILL_SWITCH_ENV: str = "TRUELINE_MRQ_EVIDENCE_CACHE_DISABLE"

# The active PDF-first flag stack (memory: trueline-pdf-first-resolver-live-demo).
# These six env vars are the ONLY runtime inputs (besides the rows + plan set)
# that change the evidence envelope, so a change to ANY of them must change the
# signature. Order is fixed so the canonical projection is stable.
FLAG_STACK_ENV_VARS: Sequence[str] = (
    "TRUELINE_PDF_FIRST_ENGINE",
    "TRUELINE_AP_ANCHORED_GEOMETRY",
    "TRUELINE_PDF_REDLINE_RENDER",
    "TRUELINE_PDF_PATH_TRACE",
    "TRUELINE_PDF_PATH_TRACE_DASH_CHAIN",
    "TRUELINE_MATCHLINE_FRAME_RESOLVER",
)

# Committed-row fields that actually affect the evidence output. Sourced from the
# engine's row consumer (redline_pdf_first/parsing/borelog_reader.py), which is
# the only place rows are read: source_file (grouping/identity) + station / print
# / depth_ft / boc_ft / notes / date / crew. Volatile / display-only row fields
# (ids, timestamps, UI flags, scores, etc.) are deliberately EXCLUDED so cosmetic
# row churn does not invalidate the cache.
_EVIDENCE_ROW_FIELDS: Sequence[str] = (
    "source_file",
    "station",
    "print",
    "depth_ft",
    "boc_ft",
    "notes",
    "date",
    "crew",
)

_logger = logging.getLogger(__name__)


def kill_switch_active() -> bool:
    """True iff ``TRUELINE_MRQ_EVIDENCE_CACHE_DISABLE`` is set to a truthy value.

    Truthy (case-insensitive, whitespace-stripped): '1', 'true', 'yes', 'on'.
    Falsy (default): unset, empty, '0', 'false', anything else.

    The cache module does NOT enforce policy beyond honoring this disable switch
    inside its own read/write helpers (mirrors plan_topology_cache). When active,
    cache_read always misses and cache_write always no-ops, so the endpoint
    transparently falls back to regeneration.
    """
    raw = os.environ.get(KILL_SWITCH_ENV, "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _safe_session_id(session_id: Any) -> str:
    """Mirror the endpoint's ``_safe_filename`` sanitizer (strip only).

    The endpoint already sanitizes the session_id with ``_safe_filename`` when it
    builds the cards dir, and passes that sanitized value here; applying the same
    strip keeps ``cache_path`` consistent if called with a raw value in tests.
    """
    try:
        return str(session_id or "").strip()
    except Exception:
        return ""


def _flag_stack_projection() -> Dict[str, str]:
    """Canonical snapshot of the active PDF-first flag stack.

    Each flag is normalized (str -> strip -> lower) so '1' and ' 1 ' collapse but
    'on' and '0' stay distinct, matching how the adapter/engine read them. Read at
    call time, never captured at import (the endpoint may toggle per process)."""
    return {
        name: str(os.environ.get(name, "")).strip().lower()
        for name in FLAG_STACK_ENV_VARS
    }


def _project_committed_rows(
    committed_rows: Optional[Sequence[Mapping[str, Any]]],
) -> List[List[Any]]:
    """Project committed_rows down to the evidence-affecting fields, in order.

    Row order is preserved (the engine groups by ``source_file`` first-seen and
    consumes station/print/etc. positionally within a group), and each row is
    reduced to a fixed-length list of its evidence fields coerced to ``str`` (or
    ``None``). Non-Mapping rows are skipped (mirrors the adapter/engine, which
    ignore them). This is the load-bearing sensitivity surface of the signature:
    any change to these fields on any row changes the projection."""
    out: List[List[Any]] = []
    for row in committed_rows or []:
        if not isinstance(row, Mapping):
            continue
        projected: List[Any] = []
        for field in _EVIDENCE_ROW_FIELDS:
            val = row.get(field)
            projected.append(None if val is None else str(val))
        out.append(projected)
    return out


def compute_signature(
    session_id: str,
    plan_set_signature: str,
    committed_rows: Optional[Sequence[Mapping[str, Any]]],
    flag_stack: Optional[Mapping[str, Any]] = None,
) -> str:
    """Deterministic SHA256 over the inputs that determine the evidence envelope.

    Inputs (the EXACT signature surface):
      - ``session_id`` (the per-session cards dir is part of the identity),
      - ``plan_set_signature`` (from ``plan_topology_cache.derive_plan_set_signature`` —
        captures plan_id / stored_filename / size_bytes / uploaded_at of the plan
        set, so a re-uploaded/changed plan PDF changes the signature),
      - a canonical projection of the evidence-affecting committed_rows fields
        (``source_file`` + station/print/depth_ft/boc_ft/notes/date/crew, in row
        order) — a NEW bore-log upload (rows added/changed) changes this,
      - the active PDF-first flag stack (the six env vars in ``FLAG_STACK_ENV_VARS``;
        ``flag_stack`` overridable for tests, else read live) — any flag change
        changes the signature, AND
      - ``SCHEMA_VERSION``.

    Same inputs -> same digest (stable, sorted JSON; no wall-clock, no dict-order
    dependence). Pure; no env enforcement (reads the live flag stack only to
    snapshot it, which is part of the signature contract)."""
    stack = (
        {k: str(v) for k, v in dict(flag_stack).items()}
        if flag_stack is not None
        else _flag_stack_projection()
    )
    material = {
        "schema_version": SCHEMA_VERSION,
        "session_id": _safe_session_id(session_id),
        "plan_set_signature": str(plan_set_signature or ""),
        "committed_rows": _project_committed_rows(committed_rows),
        "flag_stack": stack,
    }
    blob = json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def cache_path(uploads_dir: Any, session_id: str) -> Path:
    """Return the canonical cache file path for a session.

    Layout: ``<uploads_dir>/pdf_first_cards/<safe_session_id>/_evidence_cache.json``
    — i.e. inside the same per-session cards dir the endpoint writes overlay/crop
    PNGs to. Does NOT create the directory; cache_write does that on first write."""
    return (
        Path(uploads_dir)
        / CACHE_DIRNAME
        / _safe_session_id(session_id)
        / CACHE_FILENAME
    )


def _iter_png_basenames(value: Any) -> List[str]:
    """Recursively collect every ``*.png`` string value in the envelope.

    The adapter reduces ALL artifact refs (crop ``render_artifact_ref`` +
    overlay ``artifact_refs`` / ``artifact_name``) to BASENAMES before they enter
    the envelope, so any string ending in ``.png`` is an overlay/crop basename
    that must still exist in the cards dir for the cached envelope to be servable.
    Walking recursively (rather than hard-coding known keys) keeps the existence
    check robust to envelope-shape changes. Returns de-duplicated basenames."""
    found: List[str] = []

    def _walk(node: Any) -> None:
        if isinstance(node, str):
            if node.lower().endswith(".png"):
                found.append(os.path.basename(node))
        elif isinstance(node, Mapping):
            for v in node.values():
                _walk(v)
        elif isinstance(node, (list, tuple)):
            for v in node:
                _walk(v)

    _walk(value)
    # Preserve first-seen order while de-duplicating.
    seen: set = set()
    out: List[str] = []
    for name in found:
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


def cache_read(cache_file: Path, signature: str) -> Optional[Dict[str, Any]]:
    """Return the cached evidence envelope iff it is a valid, current hit; else None.

    Returns the envelope ONLY when ALL hold:
      - the kill switch is not active,
      - the cache file exists, reads, and parses as a JSON object,
      - ``schema_version`` matches ``SCHEMA_VERSION``,
      - ``signature`` matches the supplied ``signature``, AND
      - every overlay/crop PNG basename referenced in the cached envelope still
        exists in the cards dir (the cache file's parent dir).

    Any other condition -> None (the endpoint then regenerates). Pure: no side
    effects on miss; never deletes or rewrites the file. NEVER raises."""
    try:
        if kill_switch_active():
            return None  # MISS_DISABLED

        cache_file = Path(cache_file)
        if not cache_file.exists():
            return None  # MISS_ABSENT

        try:
            body = cache_file.read_text(encoding="utf-8")
        except OSError:
            _logger.warning("pdf-first evidence cache read failed: %s", cache_file)
            return None  # MISS_IO

        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, ValueError):
            _logger.warning("pdf-first evidence cache corrupt JSON: %s", cache_file)
            return None  # MISS_CORRUPT

        if not isinstance(payload, dict):
            return None  # MISS_INVALID
        if payload.get("schema_version") != SCHEMA_VERSION:
            return None  # MISS_SCHEMA
        if payload.get("signature") != signature:
            return None  # MISS_STALE

        envelope = payload.get("envelope")
        if not isinstance(envelope, dict):
            return None  # MISS_INVALID

        # Every referenced PNG basename must still exist on disk in the cards dir,
        # else a partially-cleaned cards dir would serve broken images.
        cards_dir = cache_file.parent
        for basename in _iter_png_basenames(envelope):
            try:
                if not (cards_dir / basename).exists():
                    return None  # MISS_ARTIFACT_GONE
            except OSError:
                return None  # MISS_IO

        return envelope
    except Exception:  # never raise out of the cache read
        _logger.warning("pdf-first evidence cache read error: %s", cache_file, exc_info=True)
        return None


def cache_write(cache_file: Path, signature: str, envelope: Mapping[str, Any]) -> bool:
    """Atomically persist ``envelope`` + ``signature`` to ``cache_file``.

    Best-effort: creates the parent dir as needed, writes a tmp file with a
    per-call uuid suffix, then ``os.replace``-s it into place. Returns True on a
    successful write, False otherwise (kill switch active, serialization failure,
    or OSError). NEVER raises — a cache-write failure must not affect the
    endpoint response (it just means the next load regenerates)."""
    try:
        if kill_switch_active():
            return False

        cache_file = Path(cache_file)
        payload: Dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "signature": signature,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "envelope": envelope,
        }

        try:
            body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError):
            _logger.warning("pdf-first evidence cache: envelope not serializable; skip write")
            return False

        body_bytes = body.encode("utf-8")
        tmp_path: Optional[Path] = None
        try:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = cache_file.with_name(f"{cache_file.name}.tmp.{uuid.uuid4().hex}")
            tmp_path.write_bytes(body_bytes)
            os.replace(str(tmp_path), str(cache_file))
        except OSError:
            _logger.warning("pdf-first evidence cache write failed: %s", cache_file)
            if tmp_path is not None:
                try:
                    if tmp_path.exists():
                        tmp_path.unlink()
                except OSError:
                    pass
            return False

        return True
    except Exception:  # never raise out of the cache write
        _logger.warning("pdf-first evidence cache write error: %s", cache_file, exc_info=True)
        return False
