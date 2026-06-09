"""Thin routers — logic lives in the service. Artifact serving is tenant-scoped
and traversal-safe; the URL carries only the basename."""
from __future__ import annotations

import json
import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from truelinev2 import __version__
from truelinev2.api.container import Container
from truelinev2.api.deps import get_container, get_context
from truelinev2.context import IsolationError, RequestContext

router = APIRouter()


@router.get("/v2/health")
def health() -> dict:
    return {"status": "ok", "service": "truelinev2", "version": __version__}


class RunRequest(BaseModel):
    bore_log_path: str
    plan_pdf_path: str


def _require(path: str, suffix: str, label: str) -> str:
    if not path or not os.path.isfile(path) or not path.lower().endswith(suffix):
        raise HTTPException(status_code=400, detail=f"invalid {label}: existing {suffix} required")
    return path


@router.post("/v2/redline/run")
def run_redline(req: RunRequest, ctx: RequestContext = Depends(get_context),
                c: Container = Depends(get_container)) -> dict:
    bore = _require(req.bore_log_path, ".xlsx", "bore_log_path")
    pdf = _require(req.plan_pdf_path, ".pdf", "plan_pdf_path")
    payload = c.service.run(ctx, bore, pdf)
    return payload.model_dump(mode="json")


@router.get("/v2/review")
def get_review(ctx: RequestContext = Depends(get_context),
               c: Container = Depends(get_container)) -> JSONResponse:
    stored = c.db.get_review(ctx)
    if stored is None:
        raise HTTPException(status_code=404, detail="no review for this session")
    return JSONResponse(json.loads(stored))


@router.get("/v2/artifact/{name}")
def get_artifact(name: str, ctx: RequestContext = Depends(get_context),
                 c: Container = Depends(get_container)) -> FileResponse:
    try:
        path = c.artifacts.resolve(ctx, name)
    except IsolationError:
        raise HTTPException(status_code=400, detail="invalid artifact name")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="artifact not found")
    return FileResponse(str(path), media_type="image/png")
