"""Wired singletons for one app instance (no module globals)."""
from __future__ import annotations

from dataclasses import dataclass

from truelinev2.config import Settings
from truelinev2.service import RedlineService
from truelinev2.store.artifacts import ArtifactStore
from truelinev2.store.db import ReviewStore


@dataclass(frozen=True)
class Container:
    settings: Settings
    artifacts: ArtifactStore
    db: ReviewStore
    service: RedlineService
