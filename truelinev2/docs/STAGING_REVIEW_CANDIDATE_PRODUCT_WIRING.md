# Staging REVIEW-candidate product wiring

Wire the shipped, read-only source-backed **readiness / REVIEW-candidate spine** onto the product upload/job store,
so a staging user can upload a complete package and see honest results instead of developer-only harness output.

This is **staging product usability only**. It is **not AUTO, not public launch, not final placement, and not a
status promotion.** The only drawing it can ever do is a REVIEW candidate overlay, and only through the shipped
gate.

---

## What it is / is not

- **Is:** run the shipped spine — source-span extraction -> endpoint binding -> route verification -> readiness
  classification -> `review_candidate` — on a job's uploaded files, and return an honest, product-safe result
  (extracted span rows, per-endpoint anchor status, route status, readiness status, blocker reason when refused,
  and a REVIEW candidate overlay **only** when readiness is exactly `READY_FOR_REVIEW_REDLINE`).
- **Is not:** AUTO, final placement, a status promotion, `_cap_review`, a renderer rewrite, a `select_dialect`
  change, a job lifecycle transition, or an output-slot writer. It sets no `redline_manifest` / `artifact_bundle` /
  `export_package` slot and advances no job status.
- **Distinct** from the existing Phase-6 `/review-candidates/*` lane (the uploaded-corpus ENGINE handoff). This lane
  is the **source-backed readiness spine**; it is namespaced under `/review-readiness` to avoid any conflation.

---

## Enablement (default OFF)

The drawing-capable readiness lane is mounted only when the owner explicitly enables it:

| Env var | Default | Effect |
| --- | --- | --- |
| `TL2_PRODUCT_READINESS_API_OPTIN` | `0` (OFF) | `1` mounts the `/v2/product/.../review-readiness*` routes. |
| `TL2_PRODUCT_PIPELINE_API_OPTIN` | `0` (OFF) | `1` mounts the base `/v2/product` project/job/upload routes (needed to create a job + register uploads). |

Both are independent, default-OFF flags. Staging enables both. Identity is the verified `X-TL-Tenant` slug
(`customer_project_id == ctx.tenant.value`) — never the URL path or a request body.

---

## Endpoints (all tenant + job scoped)

| Method + path | Purpose |
| --- | --- |
| `POST /v2/product/jobs/{job_id}/review-readiness/run?plan_sheet=1` | Run the spine on the job's uploads; persist + return the product-safe result. Draws a REVIEW candidate overlay **only** when `READY_FOR_REVIEW_REDLINE`. |
| `GET /v2/product/jobs/{job_id}/review-readiness` | Read the last persisted result (404 if never run). |
| `GET /v2/product/jobs/{job_id}/review-readiness/artifacts/{path}` | Serve one persisted REVIEW-candidate PNG (path-safe; `.png` only; traversal refused). |

`plan_sheet` (query, default `1`) is the plan page the spine binds/verifies on. Single-sheet per run is the spine's
current limitation (a bore that spans construction sheets is a later concern).

### Result shape (product-safe, UI-ready)

```jsonc
{
  "is_review_candidate": true, "performs_auto": false, "performs_placement": false, "promotes_status": false,
  "readiness_status": "READY_FOR_REVIEW_REDLINE",   // or a refusal status (below)
  "stage": "READY", "ready": true, "recommended_next_input": "...",
  "draws_anything": false,                           // the read-only classifier draws nothing
  "review_candidate_status": "REVIEW_CANDIDATE_READY",   // or REVIEW_CANDIDATE_REFUSED
  "generated_visual": true, "refusal_reason": null,
  "candidate": { "span_id": "...", "start_station": "...", "end_station": "...",
                 "source_file": "<basename>", "source_citation": "...", "confidence": "...",
                 "route_summary": { ... }, "route_geometry": [ ... ],
                 "artifact_before": "/v2/product/jobs/<job>/review-readiness/artifacts/<name>_before.png",
                 "artifact_after":  "/v2/product/jobs/<job>/review-readiness/artifacts/<name>_after.png",
                 "stroke_rgb": [220, 25, 25], "evidence_chain": [ ... ],
                 "is_auto": false, "is_final_placement": false, "is_promotion": false },
  "artifacts": [ { "role": "before", "filename": "...", "url": "..." },
                 { "role": "after",  "filename": "...", "url": "..." } ],
  "span_rows": [ ... ], "anchor_bindings": [ ... ], "route_verifications": [ ... ],
  "notice": "REVIEW candidate — human-reviewable; NOT AUTO, NOT final placement, NOT a status promotion"
}
```

Every refusal carries `candidate: null`, `generated_visual: false`, `artifacts: []`, and a `refusal_reason`.

### Honest statuses

| Status | Meaning | Artifact |
| --- | --- | --- |
| `READY_FOR_REVIEW_REDLINE` | source-confirmed span + both endpoints anchored + a unique verified route | **one** REVIEW candidate (before/after) |
| `MISSING_BORE_SPAN_SOURCE` | no bore-log / span-table source file present (e.g. plan only) | none |
| `NO_SOURCE_CONFIRMED_SPAN` | a source file is present but no row ties two stations as one bore | none |
| `ANCHOR_BLOCKED` | a start/end station does not bind to a unique drawn anchor | none |
| `ROUTE_BLOCKED` | endpoints anchored, but the route between them is forked/broken/not unique | none |
| `NO_SPINE_INPUT` | no plan / bore-log / route upload with a stored payload to evaluate | none |

---

## Data flow (surgical)

1. Load the tenant's job (404 if missing / cross-tenant).
2. `product_readiness_bridge.run_job_readiness(uploads, job_dir, plan_sheet, artifact_dir)`:
   - materializes an **ephemeral** spine-shaped package view (`package.json` + `uploads/<safe-name>`) from the job's
     real uploaded payloads, into a temp dir that is **deleted** after the run;
   - runs `run_package_route_readiness(...)` (`allow_live=False` — pure source-completeness; never the
     recognized-CONTROL lane) then the gated `build_review_candidate(...)`;
   - returns the product-safe result; REVIEW candidate PNGs (READY only) are written into the job-scoped
     `review_readiness/` dir (under the **gitignored** product_store — never committed).
3. The route rewrites candidate artifact basenames into served URLs, persists `review_readiness/result.json`, and
   returns the result.

Uploaded filenames are sanitized before entering the view; every `source_file` echoed back is a basename, so no
absolute/temp path reaches the client.

---

## Guardrails honored

No AUTO / no final placement / no status promotion / no `_cap_review`; no `select_dialect` change; no renderer
rewrite; no mock/live mixing (the result is computed by the real observers — proven by an input-sensitivity test:
same builder, three inputs -> three different computed statuses); no dev-only manual-anchor tools in this lane (the
`/source-anchors` capture tools belong to the separate pipeline lane; enabling only the readiness lane exposes
none); no hardcoded customer/person/place names (the module + doc + test are registered in the harness name-free
guard); no private/customer files committed (all fixtures are the generic synthetic packages; artifacts land only
in the gitignored product_store); no `origin/main`.

---

## API smoke (curl)

With the backend running (product + readiness flags on) and identity headers:

```powershell
$H = @('-H','X-TL-Tenant: <tenant>','-H','X-TL-Session: web-readonly')
# create project + job + upload a plan + a bore log via /v2/product (see product_staging_local_wiring.md), then:
curl.exe -s -X POST @H "http://127.0.0.1:8100/v2/product/jobs/<job>/review-readiness/run"
curl.exe -s        @H "http://127.0.0.1:8100/v2/product/jobs/<job>/review-readiness"
# READY only:
curl.exe -s        @H "http://127.0.0.1:8100/v2/product/jobs/<job>/review-readiness/artifacts/<name>_after.png" --output after.png
```

The executable proof is `truelinev2/tests/test_product_readiness_wiring.py` (the same synthetic packages that pass
the harness spine are proven to compute identical statuses through the product path, with artifacts gated on READY).

---

## Deferred to the next slice (owner-confirmed)

The web readiness panel + Access-gated browser smoke are **deferred to a follow-up slice** in the separate
product-mode web repo (`trueline-web-experience`, the `/v2/product` consumer). This slice is backend + tests only,
kept fully inside this repo and the guardrails.
