"""Disk cache for rendered PDF page PNG images (VO.2a).

Sibling utility to ``plan_topology_cache.py``.  Pure utility: no STATE
access, no env enforcement (caller decides policy), no main-module
dependency, no parser invocation.

Cache layout::

    <uploads_dir>/engineering_plans/<safe_session_id>/_page_cache/
        {safe_plan_id}_{page_index}_{dpi}.png

The session folder is owned by the upload handler (already created via
``_ensure_engineering_plan_storage`` + ``ENGINEERING_PLAN_ROOT /
_safe_filename(session_id)``).  Callers pass the resolved
``session_folder`` to ``resolve_cache_file`` so this module does not
need to import ``main._safe_filename``.

Filename is deterministic and content-addressed: ``plan_id`` is a
SHA256-derived 24-char hex per the upload handler at
``backend/main.py:18224``, so identical (plan_id, page_index, dpi)
inputs always map to the same cache file.  When a plan is deleted +
re-uploaded, the new plan_id is different — old cache files become
orphans and are not served (the route handler's plan-lookup step
would fail to match an absent plan_id).

Atomic write via tmp file + ``os.replace`` mirrors the
``plan_topology_cache.cache_write`` convention.
"""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import Optional


CACHE_SUBDIRNAME: str = "_page_cache"

_logger = logging.getLogger(__name__)


def _safe_path_segment(value: str) -> str:
    """Collapse anything not in [A-Za-z0-9_.-] to '_'.

    Defense in depth — ``plan_id`` is already a 24-char hex string by
    construction, but we never trust an external string to be safe for
    a filesystem path segment.  Mirrors the contract of
    ``backend/main.py:_safe_filename`` without importing it.
    """
    out_chars = []
    for ch in str(value):
        if ch.isalnum() or ch in ("_", ".", "-"):
            out_chars.append(ch)
        else:
            out_chars.append("_")
    return "".join(out_chars) or "_"


def resolve_cache_file(
    session_folder: Path,
    plan_id: str,
    page_index: int,
    dpi: int,
) -> Path:
    """Return the canonical cache file path for one rendered page.

    Args:
        session_folder: the session-scoped engineering-plan storage
                        folder (must already be ``_safe_filename``-
                        normalized by the caller; main.py owns that
                        normalization step).  Layout under it:
                        ``<session_folder>/_page_cache/<file>``.
        plan_id:        the plan identifier from the upload index.
                        Sanitized defensively even though it is already
                        a SHA256 hex prefix.
        page_index:     0-based.
        dpi:            render DPI used to produce the cache file.

    Returns:
        Path to the cache file.  Does NOT create the directory;
        ``cache_write`` does that on first write.
    """
    safe_pid = _safe_path_segment(plan_id)
    return (
        Path(session_folder)
        / CACHE_SUBDIRNAME
        / f"{safe_pid}_{int(page_index)}_{int(dpi)}.png"
    )


def cache_read(cache_file: Path) -> Optional[Path]:
    """Return ``cache_file`` if it exists and is a regular file; else None.

    Pure read: no side effects on miss.  Never raises.
    """
    try:
        if cache_file.is_file():
            return cache_file
    except OSError:
        return None
    return None


def cache_write(cache_file: Path, png_bytes: bytes) -> bool:
    """Atomically persist PNG bytes to ``cache_file``.

    Creates the parent directory as needed.  Writes via tmp file +
    ``os.replace`` so a partially-written file is never visible at
    ``cache_file``.

    Returns:
        True on success.
        False on any OSError; the caller may serve the in-memory bytes
        as a fallback.  Never raises.
    """
    tmp_path: Optional[Path] = None
    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = cache_file.with_name(
            f"{cache_file.name}.tmp.{uuid.uuid4().hex}"
        )
        tmp_path.write_bytes(png_bytes)
        os.replace(str(tmp_path), str(cache_file))
        return True
    except OSError as e:
        _logger.warning(
            "plan page image cache write failed: %s (%s)",
            cache_file,
            e,
        )
        if tmp_path is not None:
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except OSError:
                pass
        return False
