"""FastAPI application factory for tl_core.

Composition root: build settings -> wire engine + store + services into an
:class:`AppContainer` -> mount thin routers. Fail-closed CORS (no wildcard, no
implicit default) mirrors the monolith's hardened behavior.

Run standalone on a separate port (does not collide with the monolith on 8000):
  $env:TRUELINE_ALLOWED_ORIGINS = "http://localhost:3000"
  $env:PYTHONPATH = "backend"
  .\venv\Scripts\python.exe -m uvicorn tl_core.app:app --host 127.0.0.1 --port 8099
"""
from __future__ import annotations

from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .adapters.artifact_fs import FilesystemArtifactStore
from .adapters.engine_pdf_first import PdfFirstEngine
from .config import Settings
from .container import AppContainer
from .api import artifact_routes, health, redline_routes
from .services.match_review_service import MatchReviewService
from .services.redline_service import RedlineService


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    settings = settings or Settings.from_env()
    if not settings.allowed_origins:
        # Fail closed: never start with an unconfigured/wildcard CORS policy.
        raise RuntimeError(
            "TRUELINE_ALLOWED_ORIGINS must be set (fail-closed; wildcard not permitted)")

    app = FastAPI(title="tl_core — TrueLine clean-room redline service",
                  version=__version__)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    engine = PdfFirstEngine(engine_root=settings.engine_root,
                            sheet_offset=settings.sheet_offset,
                            render_crops=settings.render_crops)
    store = FilesystemArtifactStore(root=settings.artifact_root)
    app.state.tl = AppContainer(
        settings=settings,
        store=store,
        redline=RedlineService(engine=engine, artifacts=store),
        mrq=MatchReviewService(),
    )

    app.include_router(health.router)
    app.include_router(artifact_routes.router)
    app.include_router(redline_routes.router)
    return app


# Module-level ASGI app for `uvicorn tl_core.app:app` (production: env-driven).
# Guarded so importing this module for create_app() in tests/proof never trips
# the fail-closed CORS assert.
try:
    app = create_app()
except Exception:  # pragma: no cover - only when env is unset (e.g. test import)
    app = None
