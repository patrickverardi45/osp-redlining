"""Redline run endpoint — execute the PDF-first chain for one bore + plan.

PROOF/DEV affordance: this milestone accepts explicit server-side input paths so
the end-to-end chain can be exercised without the upload subsystem. It is bounded
(must be an existing ``.xlsx`` bore + ``.pdf`` plan) and is NOT mounted into the
monolith. Production resolves inputs by a tenant-scoped upload id instead of a
raw path (milestone 2); the response contract below does not change when it does.
"""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..container import AppContainer
from ..context import RequestContext
from .deps import get_container, get_context

router = APIRouter()


class RunRequest(BaseModel):
    bore_log_path: str
    plan_pdf_path: str


def _require_input(path: str, suffix: str, label: str) -> str:
    if not path or not os.path.isfile(path) or not path.lower().endswith(suffix):
        raise HTTPException(status_code=400,
                            detail=f"invalid {label}: must be an existing {suffix} file")
    return path


@router.post("/v2/redline/run")
def run_redline(
    req: RunRequest,
    ctx: RequestContext = Depends(get_context),
    container: AppContainer = Depends(get_container),
) -> dict:
    bore = _require_input(req.bore_log_path, ".xlsx", "bore_log_path")
    pdf = _require_input(req.plan_pdf_path, ".pdf", "plan_pdf_path")
    outcome = container.redline.run_for_bore(ctx, bore, pdf)
    return container.mrq.build_payload(ctx, outcome)
