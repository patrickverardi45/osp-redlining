# Production-ops baseline (backend)

The first operations-safety baseline for running the FieldRoute backend as real online software. Everything
here is a **default-off seam** — local, staging, and CI behave identically until a deployment opts in. This
is **not** the auth implementation: authentication/authorization must be a proven external system (see
"Auth", below), never hand-rolled here.

## What this adds

| Concern | Seam | Default |
|---|---|---|
| CI | `.github/workflows/backend-checks.yml` | runs on push/PR touching `truelinev2/**` |
| Error observability | `truelinev2/api/observability.py` (`init_observability`) | **off** (no DSN) |
| Rate-limit guardrail | `truelinev2/api/rate_limit.py` (`RateLimitMiddleware`) | **off** (not mounted) |

## Environment variables

Required (existing, fail-closed):

- `TL2_ALLOWED_ORIGINS` — comma-separated exact origins for CORS. The app **refuses to start** without it
  (no wildcard).

Existing default-off feature flags (`1` to enable): `TL2_PRODUCT_PIPELINE_API_OPTIN`,
`TL2_PRODUCT_READINESS_API_OPTIN`, `TL2_FIELD_EVIDENCE_API_OPTIN`, plus the engine opt-ins in `config.py`.

New, added by this baseline (all optional, safe when unset):

- `FIELDROUTE_SENTRY_DSN` (or `SENTRY_DSN`) — error-observability DSN. Unset ⇒ observability is a no-op.
- `FIELDROUTE_ENV` — deployment label reported to observability (e.g. `staging`, `production`). Generic —
  never a customer/person/place name. Default `unknown`.
- `FIELDROUTE_OBSERVABILITY_TRACES_SAMPLE_RATE` — float, default `0.0`.
- `TL2_RATE_LIMIT_OPTIN` — `1` mounts the in-process rate-limit guardrail. Default off.
- `TL2_RATE_LIMIT_PER_MINUTE` — integer window budget when the guardrail is on. Default `120`.

## Observability

`init_observability(settings)` is called by `create_app`. It is a **no-op unless a DSN is set AND the
optional `sentry-sdk` package is installed** — it never raises. `sentry-sdk` is intentionally **not** a
hard dependency in `truelinev2/requirements.txt`; a deployment that wants observability installs it and sets
the DSN. When active it is configured privacy-safe: `send_default_pii=False` and
`max_request_body_size="never"`, so request/upload bodies and tenant identity are never sent to the
provider.

## Rate-limit guardrail

`RateLimitMiddleware` is a **conservative, in-process, single-instance fixed-window limiter**, mounted only
when `TL2_RATE_LIMIT_OPTIN=1`. When off it is not in the middleware stack at all (byte-identical request
handling). It sits **behind Cloudflare Access** (which challenges at the edge before any request reaches the
backend), so it can never interfere with the Access one-time-PIN flow; an over-limit request gets a plain
`429` + `Retry-After`. It is mounted *inner* of CORS, so a `429` still carries CORS headers.

**This is a guardrail, not the production limiter.** In-process counters are per-instance and best-effort
(behind a single tunnel, requests can share one forwarded IP). Real production rate limiting belongs at the
**edge (Cloudflare)** or a **shared store (Redis) / managed API gateway**. The `FixedWindowRateLimiter` seam
is deliberately small so it can be swapped for a distributed backend without touching call sites.

## Auth (explicitly out of scope)

This slice does **not** implement authentication. The `X-TL-Tenant` / `X-TL-Session` headers are dev
stand-ins, not real auth. Production identity must be a **proven external provider / edge** — today staging
uses **Cloudflare Access**; a public production deployment needs a managed auth boundary (Cloudflare Access /
Auth0 / Clerk / equivalent) chosen by the owner. Do not build a homemade user/session/security system.

## CI

`backend-checks.yml` installs `truelinev2/requirements.txt` on Python 3.11 and runs a **targeted, reliable**
subset: API/contract, product-pipeline, field-evidence, upload, readiness, workflow, plus the new
observability + rate-limit tests. The full deterministic **render/proof** corpus (the 50/58 frontier sweeps)
is **excluded from CI** — it needs large real-PDF fixtures under `data/` (gitignored) and is slow; it is
verified locally.

Local test invocation (the `backend\venv` is a broken trap — use the **repo-root venv**):

```sh
PYTHONPATH=. venv/Scripts/python.exe -m pytest truelinev2/tests/<file>.py -q   # Windows repo-root venv (3.11.9)
```

## Staging vs production

Staging (`staging.fieldroute.io`) is Cloudflare-Access-gated with a demo store. Before any **public**
production exposure: a managed auth boundary, edge rate limiting, and an observability DSN must be in place —
none of which this in-app baseline provides on its own. It provides the **seams**; the owner picks the
**providers**.
