"""PDF-first evidence artifact path resolution — pure, dependency-free, traversal-safe.

This module owns the SECURITY-CRITICAL containment logic for serving the engine's
already-rendered overlay PNGs (``pdf_path_trace`` / ``pdf_redline``) and evidence-card
crops back to the browser. It is kept OUT of ``main.py`` on purpose so the logic is
unit-testable WITHOUT importing the monolith (mirrors how ``main.py`` delegates plan-
page image paths to ``app.core.plan_page_image_cache``; the dual-auth smoke test
likewise avoids importing ``main``).

Invariants:
  * Pure path math + a filesystem ``isfile`` check. NO engine/translation logic, NO
    ``main`` import, NO STATE, never raises.
  * The caller is responsible for tenant-ownership of ``session_id`` (``main.py`` calls
    ``_require_tenant_owns_session`` before this). Here we ONLY guarantee the resolved
    file is provably inside *that* session's cards dir.
  * A client-supplied ``name`` is reduced to a bare basename, must end in ``.png``, is
    re-rooted under the session cards dir, and the realpath is containment-checked. A
    crafted name (``../``, absolute path, embedded separators, different drive) can
    never escape — ``_safe_filename`` in ``main.py`` only ``.strip()``s, so the real
    guard lives here.
"""
from __future__ import annotations

import os
from typing import Optional

# Per-session cards subdirectory under the uploads root. Mirrors main.py's writer:
#   UPLOADS_DIR / "pdf_first_cards" / _safe_filename(session_id)
CARDS_SUBDIR = "pdf_first_cards"


def session_cards_dir(uploads_dir: str, session_id: str) -> str:
    """Absolute realpath of a session's pdf_first_cards directory (pure; the dir need
    not exist). ``session_id`` is only ``.strip()``ed to match main.py's writer —
    containment is enforced in :func:`resolve_artifact_path`, never by this helper."""
    return os.path.realpath(
        os.path.join(str(uploads_dir), CARDS_SUBDIR, str(session_id or "").strip())
    )


def resolve_artifact_path(uploads_dir: str, session_id: str, name: str) -> Optional[str]:
    """Resolve a client-supplied artifact ``name`` to an absolute ``.png`` path that is
    PROVABLY inside ``session_id``'s cards dir, or ``None`` if it is missing, not a
    ``.png``, or would escape the directory. Never raises.

    Defense in depth:
      1. ``os.path.basename`` strips every directory component (incl. ``..`` segments,
         absolute prefixes, and ``\\``/``/`` separators on Windows).
      2. require a ``.png`` suffix.
      3. re-root under the session cards dir and require the realpath to be contained
         (``os.path.commonpath``) — catches anything basename somehow missed.
      4. require the target to be an existing regular file.
    """
    base = session_cards_dir(uploads_dir, session_id)

    artifact_name = os.path.basename(str(name or "").strip())
    if not artifact_name or not artifact_name.lower().endswith(".png"):
        return None

    candidate = os.path.realpath(os.path.join(base, artifact_name))
    try:
        if os.path.commonpath([base, candidate]) != base:
            return None
    except ValueError:
        # e.g. different drives on Windows — not contained.
        return None

    if not os.path.isfile(candidate):
        return None
    return candidate
