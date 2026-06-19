"""Liveness endpoint."""
from __future__ import annotations

from fastapi import APIRouter

from .. import __version__

router = APIRouter()


@router.get("/v2/health")
def health() -> dict:
    return {"status": "ok", "service": "tl_core", "version": __version__}
