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

    # Optional error observability — a no-op unless a DSN + sentry-sdk are configured; never raises.
    from truelinev2.api.observability import init_observability
    init_observability(settings)

    app = FastAPI(title="TrueLine v2", version=__version__)
    # Product API audit log (append-only JSONL; best-effort, never breaks a request). Added FIRST so it is the
    # INNERMOST middleware and records the true product-route status (including a destructive-gate 403). Only
    # when the product API is mounted; records request METADATA only (never bodies/tokens/cookies).
    if settings.product_pipeline_api_optin:
        from truelinev2.api.audit import ProductAuditMiddleware

        audit_path = settings.product_audit_log_path or (
            settings.product_store_root.parent / "audit" / "product_api_audit.jsonl")
        app.add_middleware(ProductAuditMiddleware, log_path=audit_path)
    # Rate-limit guardrail (DEFAULT OFF). Added BEFORE CORS so it is the inner layer: an over-limit 429 still
    # flows back out through CORSMiddleware and carries the CORS headers a browser needs. Health is exempt.
    if settings.rate_limit_optin:
        from truelinev2.api.rate_limit import FixedWindowRateLimiter, RateLimitMiddleware

        app.add_middleware(
            RateLimitMiddleware,
            limiter=FixedWindowRateLimiter(settings.rate_limit_per_minute, 60),
            exempt_paths=("/v2/health",),
        )
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
    if settings.run_assembly_api_optin:
        from truelinev2.api.run_assembly_routes import router as run_assembly_router

        app.include_router(run_assembly_router)
    if settings.product_pipeline_api_optin:
        from truelinev2.api.product_pipeline_routes import router as product_pipeline_router

        app.include_router(product_pipeline_router)
    if settings.product_readiness_api_optin:
        from truelinev2.api.product_readiness_routes import router as product_readiness_router

        app.include_router(product_readiness_router)
    if settings.field_evidence_api_optin:
        from truelinev2.api.field_evidence_routes import router as field_evidence_router

        app.include_router(field_evidence_router)
    return app
