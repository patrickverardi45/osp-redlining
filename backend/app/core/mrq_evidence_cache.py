"""Default-OFF in-process cache for the MRQ PDF-first evidence payload.

``/api/match-review-queue`` rebuilds the PDF-first evidence (open plan PDF + extract +
render overlay PNGs) on EVERY request — the dominant latency. This memoizes the per-session
payload so repeated polls return instantly and skip PNG re-render. The cached value is the
EXACT payload the builder produced (engine-truth identical) — this layer never changes
geometry, artifact names, or output semantics.

Gated default-OFF by ``TRUELINE_MRQ_EVIDENCE_CACHE``. When OFF, :func:`get_or_build` ALWAYS
calls the builder (byte-identical to the pre-cache behavior) and never reads/writes the cache.

Cache key (any change invalidates):
  * ``session_id``
  * a hash of ``committed_rows`` (canonical JSON)
  * plan-PDF identity: path + size + mtime (a re-uploaded/edited plan invalidates)
  * the PDF-first OUTPUT flags (a flag flip that changes the evidence invalidates)

In-process (Render runs a single worker for this path); bounded LRU over sessions. Pure:
no fitz, no ``main`` import. Never raises out of the cache layer (the builder may raise as
before; this wrapper does not add failure modes).
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from collections import OrderedDict
from typing import Any, Callable, Dict, Mapping, Optional, Sequence, Tuple

CACHE_FLAG = "TRUELINE_MRQ_EVIDENCE_CACHE"
_MAX_SESSIONS = 32

# PDF-first env flags whose values change the evidence OUTPUT, so a flip must invalidate.
_OUTPUT_FLAGS: Tuple[str, ...] = (
    "TRUELINE_PDF_FIRST_ENGINE",
    "TRUELINE_AP_ANCHORED_GEOMETRY",
    "TRUELINE_PDF_REDLINE_RENDER",
    "TRUELINE_PDF_PATH_TRACE",
    "TRUELINE_PDF_PATH_TRACE_DASH_CHAIN",
    "TRUELINE_MATCHLINE_FRAME_RESOLVER",
    "TRUELINE_REDLINE_STRUCT_CONNECTOR",
    "TRUELINE_PHYSICAL_ANCHOR_RESOLVER",
    "TRUELINE_CROSS_SHEET_SEAM_STITCH",
    "TRUELINE_PATH_SELECTION_EVIDENCE",
    "TRUELINE_STATION_ROLE_EVIDENCE",
    "TRUELINE_SOURCE_LINEAGE_EVIDENCE",
)

# session_id -> (key, payload). OrderedDict for LRU eviction.
_CACHE: "OrderedDict[str, Tuple[str, Dict[str, Any]]]" = OrderedDict()


def enabled() -> bool:
    """True only when the default-OFF flag is explicitly '1'."""
    return os.getenv(CACHE_FLAG, "0").strip() == "1"


def clear() -> None:
    """Drop all cached entries (used by tests; also a safe manual reset)."""
    _CACHE.clear()


def cache_key(committed_rows: Sequence[Mapping[str, Any]], plan_pdf: str) -> str:
    """Stable hash over committed_rows + plan-PDF identity + PDF-first output flags."""
    h = hashlib.sha256()
    try:
        h.update(json.dumps(list(committed_rows), sort_keys=True, default=str).encode("utf-8"))
    except Exception:
        h.update(repr(committed_rows).encode("utf-8"))
    try:
        st = os.stat(plan_pdf)
        h.update(("|pdf=%s|%d|%d" % (plan_pdf, st.st_size, int(st.st_mtime))).encode("utf-8"))
    except Exception:
        h.update(("|pdf=%s" % plan_pdf).encode("utf-8"))
    h.update(("|flags=" + ";".join("%s=%s" % (f, os.getenv(f, "0").strip())
                                   for f in _OUTPUT_FLAGS)).encode("utf-8"))
    # When source-lineage evidence is ON, fold the vendored ledger's identity into
    # the key so an owner edit to the ledger invalidates cached payloads. Gated by
    # the flag => OFF cache keys are unchanged.
    if os.getenv("TRUELINE_SOURCE_LINEAGE_EVIDENCE", "0").strip() == "1":
        try:
            from app.core import source_lineage as _sl
            _lst = os.stat(_sl._DEFAULT_LINEAGE_PATH)
            h.update(("|lineage=%d|%d" % (_lst.st_size, int(_lst.st_mtime))).encode("utf-8"))
        except Exception:
            h.update(b"|lineage=missing")
    return h.hexdigest()


def is_cached(session_id: str,
              committed_rows: Sequence[Mapping[str, Any]],
              plan_pdf: str) -> bool:
    """Read-only peek: True iff a warm entry for ``session_id`` matches the CURRENT key.

    No build, no eviction, no mutation. Used by the Match Review endpoint to decide
    whether the background preseed has already warmed THIS worker's cache. Default-OFF
    (flag off => no cache => always False). NOTE: the cache is per-process, so this
    reflects the calling worker only (single-worker deployments — see preseed notes)."""
    if not enabled():
        return False
    cached = _CACHE.get(session_id)
    return cached is not None and cached[0] == cache_key(committed_rows, plan_pdf)


def get_or_build(session_id: str,
                 committed_rows: Sequence[Mapping[str, Any]],
                 plan_pdf: str,
                 card_out_dir: Optional[str],
                 builder: Callable[..., Optional[Dict[str, Any]]],
                 observer: Optional[Callable[[Dict[str, Any]], None]] = None,
                 ) -> Optional[Dict[str, Any]]:
    """Return the cached evidence on a key match, else call
    ``builder(plan_pdf, committed_rows, card_out_dir=card_out_dir)`` and memoize the result.

    Default-OFF: when the flag is off, ALWAYS builds (current behavior) and never touches the
    cache. A falsy payload (None/empty) is never cached, so it is rebuilt next time.

    Observability (additive, behavior-NEUTRAL): if ``observer`` is given it is invoked exactly
    once per call with ``{status, session_id, build_ms, elapsed_ms, cache_key, cache_size}`` where
    ``status`` is ``"disabled" | "miss" | "hit"`` (``build_ms`` is build-only time; ``cache_key``
    is a SHORT 12-char prefix or None when disabled). The observer is wrapped so it can NEVER raise
    into the caller or affect caching. Passing no observer (the default) is byte-identical to the
    pre-observability path — cache decisions, returns, and key semantics are unchanged.
    """
    _t0 = time.perf_counter()

    def _notify(status: str, build_ms: Optional[float], key: Optional[str]) -> None:
        if observer is None:
            return
        try:
            observer({
                "status": status,
                "session_id": session_id,
                "build_ms": build_ms,
                "elapsed_ms": (time.perf_counter() - _t0) * 1000.0,
                "cache_key": (key[:12] if key else None),
                "cache_size": len(_CACHE),
            })
        except Exception:
            pass  # observability is never allowed to affect cache behavior

    if not enabled():
        _b0 = time.perf_counter()
        payload = builder(plan_pdf, committed_rows, card_out_dir=card_out_dir)
        _notify("disabled", (time.perf_counter() - _b0) * 1000.0, None)
        return payload
    key = cache_key(committed_rows, plan_pdf)
    cached = _CACHE.get(session_id)
    if cached is not None and cached[0] == key:
        _CACHE.move_to_end(session_id)
        _notify("hit", 0.0, key)
        return cached[1]
    _b0 = time.perf_counter()
    payload = builder(plan_pdf, committed_rows, card_out_dir=card_out_dir)
    _build_ms = (time.perf_counter() - _b0) * 1000.0
    if payload:
        _CACHE[session_id] = (key, payload)
        _CACHE.move_to_end(session_id)
        while len(_CACHE) > _MAX_SESSIONS:
            _CACHE.popitem(last=False)
    _notify("miss", _build_ms, key)
    return payload


def set_cached(session_id: str,
               committed_rows: Sequence[Mapping[str, Any]],
               plan_pdf: str,
               payload: Optional[Dict[str, Any]]) -> bool:
    """Overwrite the cached evidence for ``session_id`` under the SAME key
    :func:`get_or_build` uses. Used by the Phase-1 lazy heavy-evidence continuation to refresh the
    metadata-first entry with the full heavy-rendered envelope once its PNGs exist on disk. No-op
    (returns ``False``) when the cache is disabled or ``payload`` is falsy; never raises. Additive:
    nothing calls this unless lazy evidence is active, so the default path is byte-identical."""
    try:
        if not enabled() or not payload:
            return False
        key = cache_key(committed_rows, plan_pdf)
        _CACHE[session_id] = (key, payload)
        _CACHE.move_to_end(session_id)
        while len(_CACHE) > _MAX_SESSIONS:
            _CACHE.popitem(last=False)
        return True
    except Exception:
        return False
