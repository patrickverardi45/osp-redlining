"""Typed settings for TrueLine v2. No global mutable state; constructed once and
injected. Fail-closed CORS in the app factory."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

# truelinev2/config.py -> truelinev2/ -> repo root
_REPO_ROOT = Path(__file__).resolve().parent.parent
_OUT = _REPO_ROOT / "data" / "outputs" / "truelinev2"
_PRODUCT_STORE = _OUT / "product_store"
_DESIGN_STROKE_DIR = (
    _REPO_ROOT / "data" / "outputs" / "symbol_conduit_lane_sweep"
)


@dataclass(frozen=True)
class Settings:
    artifact_root: Path
    cards_dir: Path
    db_path: Path
    sheet_offset: int = 13
    render_zoom: float = 3.5
    allowed_origins: Tuple[str, ...] = ()
    # M8.2l: reset-vs-continuous collision gate. DEFAULT OFF -- the gate is consulted
    # only when this is explicitly True (opt-in test); OFF is byte-identical default.
    reset_collision_optin: bool = False
    # M8.4: frame-aware continuation retry (safe HIGH edges, abstain-fill, REVIEW-cap).
    # DEFAULT OFF -- OFF is byte-identical default behavior.
    frame_continuation_optin: bool = False
    # M8.5: reverse endpoint anchor retry (end-station backsolve, abstain-fill,
    # REVIEW-cap, uniqueness-mandatory). DEFAULT OFF -- OFF is byte-identical.
    reverse_endpoint_optin: bool = False
    # M8.8: station-axis interval containment retry (tick-ladder path-walk,
    # abstain-fill, REVIEW-cap). DEFAULT OFF -- OFF is byte-identical.
    station_axis_interval_optin: bool = False
    # M8.14.c: symbol/conduit/matchline stroke lane. DEFAULT OFF -- Phase 0
    # ships the lane UNWIRED (no engine/service consultation at all); the flag
    # exists so activation is an explicit owner decision, REVIEW-only.
    symbol_conduit_lane_optin: bool = False
    # Local-only, read-only reviewer API handoff. DEFAULT OFF: reviewer routes
    # are not mounted unless explicitly enabled.
    reviewer_api_optin: bool = False
    # M9.6: local-only, read-only RUN-ASSEMBLY review-card transport. DEFAULT OFF:
    # the run-assembly route is not mounted unless explicitly enabled. Independent of
    # reviewer_api_optin so the run-assembly surface can be enabled/inert on its own.
    run_assembly_api_optin: bool = False
    # Slice 1: local-only generic product-pipeline API (project/job foundation routes). DEFAULT OFF --
    # the /v2/product routes are not mounted unless explicitly enabled.
    product_pipeline_api_optin: bool = False
    # STAGING_REVIEW_CANDIDATE_PRODUCT_WIRING: local/staging generic source-backed readiness + REVIEW-candidate
    # routes (run the shipped read-only readiness spine on a job's uploaded files; draw a REVIEW candidate ONLY
    # when readiness == READY_FOR_REVIEW_REDLINE). DEFAULT OFF -- the drawing-capable readiness lane is not mounted
    # unless explicitly enabled by the owner. NOT AUTO, NOT final placement, NOT a status promotion. Env var:
    # TL2_PRODUCT_READINESS_API_OPTIN.
    product_readiness_api_optin: bool = False
    # FIELD-EVIDENCE WRITE CONTRACT: the mobile field app's submit-to-review seam (segment evidence
    # packages: required start/end station photo refs, problem-area photos, digital bore-log readings).
    # DEFAULT OFF -- the write routes are not mounted unless explicitly enabled by the owner. Field
    # evidence SUPPORTS review; it performs NO AUTO, NO placement, NO redline generation. Env var:
    # TL2_FIELD_EVIDENCE_API_OPTIN.
    field_evidence_api_optin: bool = False
    # UPLOADED-CORPUS AUTO cap. DEFAULT OFF: a raw engine AUTO_SELECT on a customer-uploaded package is CAPPED
    # to a high-confidence human-reviewable REVIEW candidate (requires accept/reject), so uploaded-corpus
    # AUTO/final stays OWNER-GATED and closeout/export cannot proceed without human acceptance. ON restores the
    # engine's AUTO_SELECT as a no-acceptance AUTO placement. The engine's raw verdict/reason are preserved in
    # the candidate metadata either way. Never touches engine/render/select_dialect. Env: TL2_UPLOADED_CORPUS_AUTO_OPTIN.
    uploaded_corpus_auto_optin: bool = False
    # DESTRUCTIVE product-route gate. DEFAULT OFF -> destructive product API routes (job delete today,
    # plus any future clear/reset/purge) are BLOCKED with a stable 403 unless explicitly enabled. NOT auth
    # and NO change to the tenant/session model -- a fail-closed footgun guard so an accidental or casual
    # call cannot delete customer data. Env var: TL2_ENABLE_DESTRUCTIVE_PRODUCT_ROUTES.
    enable_destructive_product_routes: bool = False
    # OWNER-PACKET-2 activation: consume the reviewed manual adjudication artifact
    # during ingest/resolution. DEFAULT OFF -- OFF is byte-identical (the frozen
    # M8.27 census is unchanged); ON overlays the reviewed corrections/abstains onto
    # the resolved truth table (review-drawable / source-verification / hard-abstain),
    # carrying reviewed corrected facts only -- never invented geometry, never a
    # forced placement. Env var: TRUELINE_MANUAL_ADJUDICATIONS.
    manual_adjudications_optin: bool = False
    # Approved design-stroke PNG source for the reviewer API asset route.
    design_stroke_dir: Path = _DESIGN_STROKE_DIR
    # Slice 1: filesystem root for the generic product-pipeline store (customer_projects/<id>/...).
    # Under the gitignored v2 outputs area; never committed.
    product_store_root: Path = _PRODUCT_STORE
    # Slice 4: deployment-provided versioned billing cost-rule set (JSON) for server-side billing
    # computation. DEFAULT None -- billing compute is unavailable until a deployment points this at a
    # rules file. Rates are deployment data, NEVER baked into code and NEVER trusted from a client request.
    product_billing_cost_rules_path: Optional[Path] = None
    # Recognized-corpus auto-handoff registry (JSON): deployment-provided set of recognized corpora (each
    # corpus's display name + exact plan/bore-log content sha256 fingerprints + a bore-log->deterministic
    # log id map). DEFAULT None -- nothing is recognized (the auto-handoff stays BLOCKED) until a deployment
    # points this at a registry file. Real corpus NAMES + fingerprints are deployment DATA, never baked in
    # code. Env var: TL2_RECOGNIZED_CORPUS_REGISTRY.
    recognized_corpus_registry_path: Optional[Path] = None
    # Product API AUDIT LOG (append-only JSONL) path. DEFAULT None -> when the product API is mounted, the
    # audit middleware resolves a default path under the gitignored store tree (<store_root>/../audit/...).
    # Set to override the location. Records request METADATA only (never bodies/tokens/cookies). The
    # middleware is added by create_app only when the product API is mounted. Env: TL2_PRODUCT_AUDIT_LOG.
    product_audit_log_path: Optional[Path] = None
    # --- Production-ops baseline: observability + rate-limit guardrail (default-off seams) --------------- #
    # Optional error observability (Sentry-style). DEFAULT None -> no-op: init_observability returns False and
    # never raises, so local/dev/CI runs are untouched. A DSN + the OPTIONAL sentry-sdk package activate it;
    # request bodies / upload contents are NEVER sent. Env: FIELDROUTE_SENTRY_DSN (or SENTRY_DSN).
    observability_dsn: Optional[str] = None
    # Deployment label for observability (e.g. "staging" / "production"). Generic — never a customer name.
    observability_environment: str = "unknown"
    observability_traces_sample_rate: float = 0.0
    # In-process fixed-window rate-limit GUARDRAIL SEAM. DEFAULT OFF -> the middleware is NOT mounted and
    # request handling is byte-identical. Conservative single-instance fallback, NOT the production limiter
    # (production belongs at the edge / Redis / a managed gateway). Sits AFTER Cloudflare Access, so it can
    # never interfere with the Access challenge. Env: TL2_RATE_LIMIT_OPTIN, TL2_RATE_LIMIT_PER_MINUTE.
    rate_limit_optin: bool = False
    rate_limit_per_minute: int = 120
    # --- Phase-1 handwritten/scanned bore-log extraction (Wave 2: extract seam + API). DEFAULT OFF -- OFF is
    # byte-identical (no image BORE_LOG uploads accepted, no third extraction tier, no fan-out/review/source
    # routes). No vendor/model name lives here or anywhere in this seam -- the provider is opaque runtime
    # data (a deployment-supplied dotted module path), never named by this file.
    handwritten_borelog_extraction_optin: bool = False
    # Hard timeout (seconds) around one page's vision-provider call (threading-based wrapper; a provider that
    # never returns cannot hang extraction forever). Env: TL2_HANDWRITTEN_BORELOG_TIMEOUT_SECONDS.
    handwritten_borelog_timeout_seconds: int = 90
    # Deployment-selected vision-provider DOTTED MODULE PATH (e.g. one of the modules under
    # extract/vision_providers/) -- extract/handwritten_borelog.py's factory imports it lazily and calls
    # its build_provider(config). Unset/unloadable/None still refuses honestly with
    # HANDWRITTEN_VISION_PROVIDER_NOT_CONFIGURED. Env: TL2_HANDWRITTEN_BORELOG_PROVIDER. See
    # docs/handwritten-vision-provider.md for the full config matrix.
    handwritten_borelog_provider: Optional[str] = None
    # Phase-2 SOURCE-ROUTE ADOPTION: the stateless, read-only-by-effect proposal endpoint
    # (POST /v2/product/jobs/{job_id}/source-route-proposals) that projects two human control points onto a
    # verified READY_FOR_REVIEW_REDLINE observer backbone + the SourceAnchorCreate.route_adoption extension.
    # DEFAULT OFF -- OFF is byte-identical: the proposal router is not mounted, source_route_adoption/the new
    # bridge helper are not imported at request time, and a normal SourceAnchorCreate (no route_adoption field)
    # follows the EXISTING unchanged v1 record path. Mounted ONLY when this AND product_pipeline_api_optin AND
    # product_readiness_api_optin are ALL True (api/app.py three-way gate). Env var:
    # TL2_SOURCE_ROUTE_ADOPTION_API_OPTIN.
    source_route_adoption_api_optin: bool = False
    # Mission 8: manual N-point polyline provenance on the EXISTING SourceAnchorCreate (the honest fallback
    # when source-route adoption refuses -- a "Representative straight segment" the operator can turn into a
    # human-adjusted bend polyline before explicitly confirming). DEFAULT OFF -- OFF is byte-identical: a
    # request that carries the optional `manual_route` block is refused 400 MANUAL_ROUTE_NOT_ENABLED before
    # any manual-route validation/derivation runs, and a blockless request (the overwhelming common case)
    # follows the EXISTING unchanged v1/v2 create path verbatim regardless of this flag's value. Independent
    # of `source_route_adoption_api_optin` (manual confirmation needs no readiness spine / observer backbone
    # at all) -- both may be enabled together; a single create request may never carry both `route_adoption`
    # and `manual_route` (mutually exclusive provenance, refused regardless of either flag). Env var:
    # TL2_SOURCE_ANCHOR_MANUAL_ROUTE_OPTIN.
    source_anchor_manual_route_optin: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        raw = os.getenv("TL2_ALLOWED_ORIGINS", "").strip()
        origins = tuple(o.strip() for o in raw.split(",") if o.strip())
        return cls(
            artifact_root=Path(os.getenv("TL2_ARTIFACT_ROOT", str(_OUT / "artifacts"))),
            cards_dir=Path(os.getenv("TL2_CARDS_DIR", str(_OUT / "_cards"))),
            db_path=Path(os.getenv("TL2_DB_PATH", str(_OUT / "truelinev2.db"))),
            sheet_offset=int(os.getenv("TL2_SHEET_OFFSET", "13")),
            allowed_origins=origins,
            reset_collision_optin=os.getenv("TL2_RESET_COLLISION_OPTIN", "0") == "1",
            frame_continuation_optin=os.getenv("TL2_FRAME_AWARE_CONTINUATION_OPTIN", "0") == "1",
            reverse_endpoint_optin=os.getenv("TL2_REVERSE_ENDPOINT_ANCHOR_OPTIN", "0") == "1",
            station_axis_interval_optin=os.getenv("TL2_STATION_AXIS_INTERVAL_OPTIN", "0") == "1",
            symbol_conduit_lane_optin=os.getenv("TL2_SYMBOL_CONDUIT_LANE_OPTIN", "0") == "1",
            reviewer_api_optin=os.getenv("TL2_REVIEWER_API_OPTIN", "0") == "1",
            run_assembly_api_optin=os.getenv("TL2_RUN_ASSEMBLY_API_OPTIN", "0") == "1",
            product_pipeline_api_optin=os.getenv("TL2_PRODUCT_PIPELINE_API_OPTIN", "0") == "1",
            product_readiness_api_optin=os.getenv("TL2_PRODUCT_READINESS_API_OPTIN", "0") == "1",
            field_evidence_api_optin=os.getenv("TL2_FIELD_EVIDENCE_API_OPTIN", "0") == "1",
            uploaded_corpus_auto_optin=os.getenv("TL2_UPLOADED_CORPUS_AUTO_OPTIN", "0") == "1",
            enable_destructive_product_routes=os.getenv("TL2_ENABLE_DESTRUCTIVE_PRODUCT_ROUTES", "0") == "1",
            manual_adjudications_optin=os.getenv("TRUELINE_MANUAL_ADJUDICATIONS", "0") == "1",
            design_stroke_dir=Path(
                os.getenv("TL2_DESIGN_STROKE_DIR", str(_DESIGN_STROKE_DIR))
            ),
            product_store_root=Path(
                os.getenv("TL2_PRODUCT_STORE_ROOT", str(_PRODUCT_STORE))
            ),
            product_billing_cost_rules_path=(
                Path(os.environ["TL2_PRODUCT_BILLING_COST_RULES"])
                if os.getenv("TL2_PRODUCT_BILLING_COST_RULES") else None
            ),
            recognized_corpus_registry_path=(
                Path(os.environ["TL2_RECOGNIZED_CORPUS_REGISTRY"])
                if os.getenv("TL2_RECOGNIZED_CORPUS_REGISTRY") else None
            ),
            product_audit_log_path=(
                Path(os.environ["TL2_PRODUCT_AUDIT_LOG"]) if os.getenv("TL2_PRODUCT_AUDIT_LOG") else None
            ),
            observability_dsn=(
                (os.getenv("FIELDROUTE_SENTRY_DSN") or os.getenv("SENTRY_DSN") or "").strip() or None
            ),
            observability_environment=os.getenv("FIELDROUTE_ENV", "unknown"),
            observability_traces_sample_rate=float(
                os.getenv("FIELDROUTE_OBSERVABILITY_TRACES_SAMPLE_RATE", "0") or "0"
            ),
            rate_limit_optin=os.getenv("TL2_RATE_LIMIT_OPTIN", "0") == "1",
            rate_limit_per_minute=int(os.getenv("TL2_RATE_LIMIT_PER_MINUTE", "120") or "120"),
            handwritten_borelog_extraction_optin=(
                os.getenv("TL2_HANDWRITTEN_BORELOG_EXTRACTION_OPTIN", "0") == "1"
            ),
            handwritten_borelog_timeout_seconds=int(
                os.getenv("TL2_HANDWRITTEN_BORELOG_TIMEOUT_SECONDS", "90") or "90"
            ),
            handwritten_borelog_provider=(
                os.getenv("TL2_HANDWRITTEN_BORELOG_PROVIDER", "").strip() or None
            ),
            source_route_adoption_api_optin=(
                os.getenv("TL2_SOURCE_ROUTE_ADOPTION_API_OPTIN", "0") == "1"
            ),
            source_anchor_manual_route_optin=(
                os.getenv("TL2_SOURCE_ANCHOR_MANUAL_ROUTE_OPTIN", "0") == "1"
            ),
        )

    @classmethod
    def for_proof(cls) -> "Settings":
        return cls(
            artifact_root=_OUT / "artifacts",
            cards_dir=_OUT / "_cards",
            db_path=_OUT / "truelinev2.db",
            sheet_offset=13,
            allowed_origins=("http://localhost:3000", "http://127.0.0.1:8100"),
            reviewer_api_optin=False,
            run_assembly_api_optin=False,
            design_stroke_dir=_DESIGN_STROKE_DIR,
        )
