# Runbook — Local / internal product-staging wiring

Run the **backend product API + the real seed `product_store` + the web in product mode** together
locally, and see the real seed job in the web UI **without any mock fallback**.

This is the "make the real thing runnable" gate for the active direction *finish the end-to-end product
workflow + retire mock/demo/stub runtime behavior*. It is **read-only and local-only**: no deploy, no
production, no `origin/main`, no auth. P5 auth/role is PAUSED and is not part of this path.

The **official proof surface for this lane is the web home page `/`.** See the `/redlines` warning below.

---

## 0. What this proves (and does not)

Proves the current system can run, end-to-end, on **one real drawn log** (the committed `log3` render):

```
backend seed product_store  ->  backend /v2/product API  ->  web product mode
   ->  dashboard KPIs + v2 job-status (closeout / billing / export / KMZ safety) + artifact metadata
```

It does **not** claim the unified all-50 bundle, run the engine/renderer, run OCR, produce KMZ
coordinates, or generate any export file. The seed is a generically-named single-log subset
(frontier `1/1`) published through the real contract chain (real sha256/bytes, `mock_example:false`).

---

## 1. Backend repo / path / branch assumptions

| Item | Value |
| --- | --- |
| Repo | `C:\Nova\projects\TrueLine\TrueLine_Beta` |
| Branch | `feat/truelinev2` |
| Python | repo-root venv `\.venv\Scripts\python.exe` (**3.11.9**) |

> Use the **repo-root** venv. Do **not** use `backend\venv` (broken trap). The product API is
> default-OFF; nothing in this runbook touches the old (`backend/**`) app, the renderer, fixtures,
> anchors, coordinates, or `origin/main`.

---

## 2. Backend prerequisites

- Repo-root venv present, with FastAPI + uvicorn installed (verify once):
  ```powershell
  .\venv\Scripts\python.exe -c "import fastapi, uvicorn; print(fastapi.__version__, uvicorn.__version__)"
  ```
- `PYTHONPATH=.` set from the repo root so `truelinev2.api.app` imports.
- The real `log3` render artifacts must exist on disk (the seed aborts without them):
  - `data\outputs\callout_route_assembly_sweep\log3_s2_redline_stroke.png`
  - `data\outputs\callout_route_assembly_sweep\log3_s3_redline_stroke.png`

---

## 3. Generate (or refresh) the real seed product_store

From the repo root:

```powershell
cd C:\Nova\projects\TrueLine\TrueLine_Beta
$env:PYTHONPATH = "."
.\venv\Scripts\python.exe -m truelinev2.proof.run_product_workflow_seed
```

Re-runnable: it deletes and rebuilds **only** the gitignored seed store. Expected tail:

```
manifest handoff:  SUCCEEDED -> bundle seed-project-c19b565-<hash>
kmz safety:        BLOCKED (UNSUPPORTED_PIXEL_ONLY)
closeout:          READY_FOR_APPROVAL (hard_blockers=0, ...)
billing:           COMPUTED  base_total=3122.50 USD
export package:    READY  ...
seed product-store (gitignored): ...\data\outputs\truelinev2\product_store_seed
```

---

## 4. Exact product store root

```
C:\Nova\projects\TrueLine\TrueLine_Beta\data\outputs\truelinev2\product_store_seed
```

> **This is the single most important wiring detail.** The seed writes to `…\product_store_seed`,
> but the API's default `TL2_PRODUCT_STORE_ROOT` is `…\product_store` (no `_seed`). If you do not
> override it, every job read returns **404** because the API is pointed at an empty default store.

---

## 5. Backend env + uvicorn command

In the **same** terminal (so `PYTHONPATH` is still set):

```powershell
$env:PYTHONPATH                     = "."
$env:TL2_ALLOWED_ORIGINS            = "http://localhost:3000,http://127.0.0.1:3000"
$env:TL2_PRODUCT_PIPELINE_API_OPTIN = "1"
$env:TL2_PRODUCT_STORE_ROOT         = "C:\Nova\projects\TrueLine\TrueLine_Beta\data\outputs\truelinev2\product_store_seed"

.\venv\Scripts\python.exe -m uvicorn truelinev2.api.app:create_app --factory --host 127.0.0.1 --port 8100
```

Notes:

- `create_app` **fails closed** and raises if `TL2_ALLOWED_ORIGINS` is unset (no wildcard). Expected.
- `TL2_PRODUCT_PIPELINE_API_OPTIN=1` mounts the `/v2/product` router. Default OFF.
- `TL2_PRODUCT_BILLING_COST_RULES` is **not needed** here: the seed already computed and persisted
  billing, and the web only *reads* `GET /billing`. (That env var powers only `POST /billing/compute`,
  which the web never calls in this read-only path.)

---

## 6. Web repo / path assumptions

| Item | Value |
| --- | --- |
| Repo | `C:\Nova\projects\trueline-web-experience` |
| Branch | `main` |

---

## 7. Web env + command

In a **second** terminal:

```powershell
cd C:\Nova\projects\trueline-web-experience
$env:NEXT_PUBLIC_TL2_PRODUCT_API = "1"
$env:NEXT_PUBLIC_TL2_API_BASE    = "http://127.0.0.1:8100"
$env:NEXT_PUBLIC_TL2_TENANT      = "seed-project"
$env:NEXT_PUBLIC_TL2_JOB_ID      = "seed-job-1"

npm run dev
```

- All four `NEXT_PUBLIC_TL2_*` are **mandatory** in product mode; the live client throws a clear config
  error if any is missing (it never silently uses mock data).
- `npm run dev` serves on `http://localhost:3000`.
- Keep host/port consistent: backend bind `127.0.0.1:8100` ↔ `NEXT_PUBLIC_TL2_API_BASE=http://127.0.0.1:8100`.
- The web sends backend **dev stand-in** identity headers `X-TL-Tenant: seed-project` and
  `X-TL-Session: web-readonly`. These are **not auth** — just the local stand-in the backend expects.

---

## 8. Expected tenant / job

| Field | Value |
| --- | --- |
| tenant / customer_project | `seed-project` |
| processing job | `seed-job-1` |

The tenant comes from the verified `X-TL-Tenant` header (`customer_project_id == tenant`), never from the
URL path or request body. A wrong tenant/job yields **404** (tenant isolation), and a missing session
header yields **401**.

---

## 9. Browser verification (proof surface = home `/`)

Open `http://localhost:3000/`. Expect the **real seed subset**, not the offline fixture:

KPIs:

| KPI | Expected |
| --- | --- |
| Bore logs (frontier) | `1` (frontier `1/1`) |
| Drawn redlines | `1` |
| Covered | `0` |
| Blocked | `0` |

Durable redline manifest card: bundle `seed-project-c19b565-<hash>`, **2 final redline artifacts**.

v2 job-status strip (server-authoritative):

| Surface | Expected |
| --- | --- |
| Closeout | `READY_FOR_APPROVAL` |
| Billing | `COMPUTED` (· `3122.50 USD`) |
| Export package | `READY` |
| KMZ export | `unavailable (UNSUPPORTED_PIXEL_ONLY)` |

---

## 10. API / curl verification checklist

PowerShell uses `curl.exe` (plain `curl` is an alias). Identity headers are required:

```powershell
$H = @('-H','X-TL-Tenant: seed-project','-H','X-TL-Session: web-readonly')

curl.exe -s @H http://127.0.0.1:8100/v2/product/project
curl.exe -s @H http://127.0.0.1:8100/v2/product/jobs/seed-job-1
curl.exe -s @H http://127.0.0.1:8100/v2/product/jobs/seed-job-1/redline-manifest
curl.exe -s @H http://127.0.0.1:8100/v2/product/jobs/seed-job-1/artifacts
curl.exe -s @H http://127.0.0.1:8100/v2/product/jobs/seed-job-1/closeout
curl.exe -s @H http://127.0.0.1:8100/v2/product/jobs/seed-job-1/billing
curl.exe -s @H http://127.0.0.1:8100/v2/product/jobs/seed-job-1/export-package
curl.exe -s @H http://127.0.0.1:8100/v2/product/jobs/seed-job-1/kmz-export
```

Expected (abbreviated):

| Endpoint | Expect |
| --- | --- |
| `/v2/product/project` | project record for `seed-project` |
| `/v2/product/jobs/seed-job-1` | job record, status `PLACED` |
| `…/redline-manifest` | `summary_counts` `{ total_logs: 1, drawn: 1, covered: 0, blocked: 0 }` |
| `…/artifacts` | `bundle_id` + 2 `FINAL_REDLINE_PNG` refs |
| `…/closeout` | `status: READY_FOR_APPROVAL` |
| `…/billing` | `status: COMPUTED`, `view.final_total: "3122.50"` |
| `…/export-package` | `status: READY` |
| `…/kmz-export` | `status: BLOCKED`, blocker `UNSUPPORTED_PIXEL_ONLY` |

Identity sanity: dropping the headers → **401**; a wrong tenant or job id → **404**.

---

## 11. No-mock verification

The point of this lane is to prove there is **no silent mock fallback** in product mode:

- The dashboard shows **`1 / 1 / 0 / 0`** (real seed), **not** the offline fixture's `58 / 50 / 1 / 7`.
- DevTools → Network shows reads to **`127.0.0.1:8100/v2/product/*`** (live API), not bundled fixtures.
- **Stop the backend and reload `/`:** the job-status strip shows *"v2 job status unavailable …"* and the
  manifest read **throws** (the page errors) — it must **not** fall back to the `58/50` mock numbers.
- Optional zero-dependency contract check in the web repo: `node scripts/check-live-product-read.mjs`.

---

## 12. Honest unsupported / deferred states (expected, not bugs)

- **Artifact images are metadata-only for now** — the manifest card lists artifact count/refs; image
  bytes (header-bearing `fetch → blob`) are deferred. No PNG renders in this build.
- **The rich per-log manifest panel remains deferred** — the live view's per-log body is intentionally
  empty (it needs a read-only backend full-manifest route, not built in this lane). Totals/frontier/
  bundle/artifact-count are real.
- **KMZ export stays BLOCKED** for pixel/PDF-only geometry (`UNSUPPORTED_PIXEL_ONLY`) — the system
  abstains rather than fake coordinates.
- **Unbacked product-mode surfaces show empty / unsupported / not-found states.** Portfolio / field
  pages (`/map`, `/evidence`, `/plans`, `/closeout`, `/projects/[id]`) read mock-portfolio-shaped data
  that returns honest-empty in product mode. Empty/placeholder/not-found there is expected — there is no
  mock truth in product mode.
- The dashboard "Render / source" field may render blank; the render commit `c19b565` is embedded in the
  bundle id. Cosmetic, honest-limited.

---

## 13. `/redlines` — DO NOT USE for the product-staging proof

> **`/redlines` is NOT the product-staging proof surface. Do not use it to validate this lane.**

- `/redlines` calls the engine **reviewer** reads (`engineBundle` / `engineDesignStrokeArtifacts`), which
  are a **separate concern from product-store truth**. Because product mode sets
  `NEXT_PUBLIC_TL2_API_BASE`, those shared reviewer reads go **live** to `/v2/reviewer/*`, which is **not
  mounted** in this lane — so `/redlines` will error.
- **Do not enable the reviewer router (`TL2_REVIEWER_API_OPTIN`) as part of this lane.** The reviewer API
  reads a different data source (the engine reviewer export), is out of scope for the product path, and
  documenting/enabling it here is explicitly excluded.
- **The official proof surface for this lane is the home page `/`.** Validate there.

---

## 14. Known blockers / gaps

- **Store-root pointer (operational):** `TL2_PRODUCT_STORE_ROOT` must point at `…\product_store_seed`
  (§4). This is the most common misconfiguration; symptom is `404` on every job read.
- **`/redlines` cross-activation (by design):** see §13 — out of scope; do not enable the reviewer router.
- **Artifact images + full per-log manifest:** deferred (§12). Lighting these up is a **separate,
  separately-authorized Slice 1B** (header-bearing artifact images + a read-only backend full-manifest
  route) — **not** part of this runbook.
- **`NEXT_PUBLIC_*` timing:** for `next dev`, set the web env vars before `npm run dev`. (A production
  `next build` would inline them at build time — out of scope here.)

---

## 15. Explicit non-goals

No production deploy; no `origin/main` change; no backend or web **code** change; no auth; no privileged
closeout transitions; no reviewer router on the product path; no OCR / fake OCR; no KMZ coordinates / fake
KMZ export; no generated export files; no fake proof artifacts; no Slice 1B / artifact image loading; no
backend full-manifest route; no engine / renderer / fixture / anchor / coordinate change; no v1 backend
behavior; no mobile; no dependency change. Local, read-only, single seed job only.
