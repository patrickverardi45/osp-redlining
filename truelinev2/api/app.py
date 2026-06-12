"""FastAPI application factory. Fail-closed CORS; no module-level app (so import
for tests/proof never trips the CORS assert)."""
from __future__ import annotations

from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from truelinev2 import __version__
from truelinev2.api.container import Container
from truelinev2.api.routes import router
from truelinev2.config import Settings
from truelinev2.service import RedlineService
from truelinev2.store.artifacts import ArtifactStore
from truelinev2.store.db import ReviewStore


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    settings = settings or Settings.from_env()
    if not settings.allowed_origins:
        raise RuntimeError("TL2_ALLOWED_ORIGINS must be set (fail-closed; no wildcard)")

    app = FastAPI(title="TrueLine v2", version=__version__)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    artifacts = ArtifactStore(settings.artifact_root)
    db = ReviewStore(settings.db_path)
    app.state.tl2 = Container(settings=settings, artifacts=artifacts, db=db,
                              service=RedlineService(settings, artifacts, db))
    app.include_router(router)
    if settings.reviewer_api_optin:
        from truelinev2.api.reviewer_routes import router as reviewer_router

        app.include_router(reviewer_router)
    return app
