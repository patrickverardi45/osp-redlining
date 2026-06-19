"""tl_core — clean-room, strangler-style rebuild of the TrueLine redline surface.

Lives ALONGSIDE the original ``backend/main.py`` + ``backend/app/**`` (both left
untouched and read-only). Nothing in this package imports or mutates ``main.py``.

Design stance (see the mapping audit, 2026-06-09):
  * REUSE-BY-IMPORT the proven, decoupled PDF-first engine
    (``app/core/redline_pdf_first``) behind a clean port — it is verified free of
    coupling to global ``STATE`` / ``main`` / ``_session_scope`` / FastAPI.
  * RE-ARCHITECT only the audited-weak seams: global mutable ``STATE`` ->
    explicit request-scoped context + scoped store; opt-in tenant ownership ->
    fail-closed isolation; monolith inline routes -> thin routers; unescaped
    HTML sinks -> output encoding; client-path file serving -> traversal-safe
    artifact store.
"""
from __future__ import annotations

__all__ = ["__version__"]
__version__ = "0.1.0"
