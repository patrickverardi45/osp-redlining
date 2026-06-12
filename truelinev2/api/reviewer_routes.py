"""Local-only, flag-gated, read-only reviewer export routes.

This router is context-free by design: no tenant/session dependency, no
database, no writes, and no engine activation. It only exposes validated
reviewer-export data and manifest-approved proof PNGs.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, Set

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from truelinev2.proof.export_design_stroke_artifacts_json import (
    _ARTIFACT_FILENAME,
    generate_export as generate_design_stroke_export,
)
from truelinev2.proof.export_design_stroke_artifacts_served import (
    build_served_export,
    validate_served_export,
)
from truelinev2.proof.export_reviewer_bundle_json import (
    generate_export as generate_reviewer_bundle_export,
    validate_export as validate_reviewer_bundle_export,
)

router = APIRouter(prefix="/v2/reviewer")

_BUNDLE_CACHE = "tl2_reviewer_bundle_export"
_MANIFEST_CACHE = "tl2_design_stroke_manifest"
_APPROVED_CACHE = "tl2_design_stroke_approved_names"


def reviewer_asset_url(_sha: str, filename: str) -> str:
    """Canonical API-relative URL for one approved artifact filename."""
    return f"/v2/reviewer/design-stroke/asset/{filename}"


def _service_unavailable(label: str, exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail=f"{label} unavailable: {type(exc).__name__}",
    )


def _bundle(request: Request) -> Dict[str, Any]:
    cached = getattr(request.app.state, _BUNDLE_CACHE, None)
    if cached is None:
        try:
            cached = generate_reviewer_bundle_export()
            validate_reviewer_bundle_export(cached)
        except (FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
            raise _service_unavailable("reviewer bundle", exc) from exc
        setattr(request.app.state, _BUNDLE_CACHE, cached)
    validate_reviewer_bundle_export(cached)
    return cached


def _manifest(request: Request) -> Dict[str, Any]:
    cached = getattr(request.app.state, _MANIFEST_CACHE, None)
    if cached is None:
        try:
            base = generate_design_stroke_export()
            cached = build_served_export(base, url_for=reviewer_asset_url)
            validate_served_export(cached, url_for=reviewer_asset_url)
        except (FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
            raise _service_unavailable("design-stroke manifest", exc) from exc
        approved = {
            ref
            for artifact in cached["artifacts"]
            for ref in artifact["artifact_refs"]
        }
        setattr(request.app.state, _MANIFEST_CACHE, cached)
        setattr(request.app.state, _APPROVED_CACHE, frozenset(approved))
    validate_served_export(cached, url_for=reviewer_asset_url)
    return cached


def _approved_names(request: Request) -> Set[str]:
    _manifest(request)
    approved = getattr(request.app.state, _APPROVED_CACHE, frozenset())
    return set(approved)


@router.get("/bundle")
def get_reviewer_bundle(
    request: Request, mode: str = "default_baseline"
) -> Dict[str, Any]:
    if mode != "default_baseline":
        raise HTTPException(status_code=400, detail="only default_baseline is allowed")
    return _bundle(request)


@router.get("/design-stroke/manifest")
def get_design_stroke_manifest(request: Request) -> Dict[str, Any]:
    return _manifest(request)


@router.get("/design-stroke/asset/{name}")
def get_design_stroke_asset(request: Request, name: str) -> FileResponse:
    if (
        not _ARTIFACT_FILENAME.fullmatch(name)
        or os.path.basename(name) != name
        or "/" in name
        or "\\" in name
    ):
        raise HTTPException(status_code=400, detail="invalid artifact name")
    if name not in _approved_names(request):
        raise HTTPException(status_code=404, detail="artifact not approved")

    source_dir = Path(request.app.state.tl2.settings.design_stroke_dir).resolve()
    path = (source_dir / name).resolve()
    if path.parent != source_dir:
        raise HTTPException(status_code=400, detail="invalid artifact path")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="artifact not found")
    return FileResponse(str(path), media_type="image/png")
