"""M9.6 -- local-only, flag-gated, read-only RUN-ASSEMBLY review-card transport route.

Context-free by design (mirrors api/reviewer_routes.py): no tenant/session dependency,
no database, no writes, no engine activation, no placement path. It only exposes the
validated M9.4.2 RunAssemblyReviewService cards through the M9.6 transport envelope
(truelinev2-web-run-assembly-export-1). The cards keep their own M9.4.1 schema; this
route never moves a product bucket, renders an artifact, or mutates the per-bore bundle.

Mounted by create_app ONLY when settings.run_assembly_api_optin is True (default OFF).
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

from truelinev2.proof.export_run_assembly_cards_json import (
    generate_export as generate_run_assembly_export,
    validate_export as validate_run_assembly_export,
)

router = APIRouter(prefix="/v2/reviewer")

_CACHE = "tl2_run_assembly_cards_export"


def _service_unavailable(exc: Exception) -> HTTPException:
    return HTTPException(status_code=503,
                        detail=f"run-assembly cards unavailable: {type(exc).__name__}")


def _export(request: Request) -> Dict[str, Any]:
    cached = getattr(request.app.state, _CACHE, None)
    try:
        if cached is None:
            cached = generate_run_assembly_export()
            validate_run_assembly_export(cached)
            setattr(request.app.state, _CACHE, cached)
        else:
            # re-validate the cached envelope on every call (cache-poisoning safety);
            # corruption maps to 503, not a raw 500.
            validate_run_assembly_export(cached)
    except (FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
        raise _service_unavailable(exc) from exc
    return cached


@router.get("/run-assembly")
def get_run_assembly_cards(request: Request) -> Dict[str, Any]:
    """The validated, read-only RUN-ASSEMBLY review-card transport envelope."""
    return _export(request)
