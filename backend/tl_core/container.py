"""Dependency container — the wired singletons for one app instance.

Built once in :func:`tl_core.app.create_app` and stashed on ``app.state``; routes
pull it via a FastAPI dependency. Keeps construction explicit (no module globals).
"""
from __future__ import annotations

from dataclasses import dataclass

from .config import Settings
from .ports.artifacts import ArtifactStore
from .services.match_review_service import MatchReviewService
from .services.redline_service import RedlineService


@dataclass(frozen=True)
class AppContainer:
    settings: Settings
    store: ArtifactStore
    redline: RedlineService
    mrq: MatchReviewService
