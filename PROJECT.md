# PROJECT.md — TrueLine / FieldRoute

> One-time deep knowledge transfer, written 2026-07-07 from a full exploration of the repo plus a
> live staging audit. Companion files: **GAPS.md** (honest weakness audit) and **CLAUDE.md**
> (operational rules for AI sessions). The *current working state* of the project is NOT this file —
> it is `wiki/START_HERE_TRUELINE_V2.md`, bumped every session. This file is the durable narrative.

## 1. What this is, in plain language

TrueLine (customer-facing product name: **FieldRoute**) is a platform for **OSP (outside-plant)
telecom construction closeout**. When a contractor directional-bores fiber conduit under streets,
they must hand the network owner an **as-built "redline"**: the construction plan PDF marked up in
red showing where each bore actually went, tied to the crew's handwritten **bore logs** (station
ranges like `1+00 → 3+00`, depths, conduit sizes), plus footage-based pricing and evidence photos.

Today that markup is done by hand. This product ingests the customer's package (plan PDF, bore-log
spreadsheet/PDF, KMZ route, photos), lets a human confirm the bore-log rows, **draws the red
strokes on the correct plan sheets deterministically**, and assembles a downloadable closeout
package (redline PNGs + manifest + closeout PDF + operator-entered pricing).

Users: the owner (an OSP operations person, not a professional developer) runs it for his own
closeout work; a first external customer tester is being onboarded on staging. It is
pre-production, single-operator, behind Cloudflare Access.

## 2. One repo, two generations — plus satellite repos

This repo (`TrueLine_Beta`) contains **two products**:

| Generation | Where | Status |
|---|---|---|
| **v1 monolith** | `backend/` (FastAPI, ~119 app files, own tests + broken `backend/venv`), `web/` (Next.js UI, own `node_modules`), root `node_modules/`+`.next/`+`.vercel/` remnants | **Frozen legacy / specification only.** No commits since ~June 2026. Its auth will be replaced by an external provider; its KMZ/map behavior is the reference for v2 parity. Never deleted yet ("don't wipe the old tree until the engine split"). |
| **v2 product** | `truelinev2/` (Python package: engine + product API) | **The real product.** All active work. Branch `feat/truelinev2`; `origin/main` is ~407 commits stale (v1-era) — a fresh clone's default checkout is the wrong world. |

Satellite repos (separate git repos, same machine):

| Repo | Path | Role |
|---|---|---|
| FieldRoute web | `C:\Nova\projects\trueline-web-experience` | The customer web UI (Next.js). Talks to this repo's `/v2/product` API with `X-TL-Tenant` headers. Its production build **is what staging serves** — never `npm run build` in that checkout while staging is live (it overwrites the served `.next`). |
| Field mobile | `C:\Nova\projects\trueline-field-mobile` | Expo SDK 56 field-crew app ("FieldRoute Capture", temp name). Local-only, no git remote yet. |
| Knowledge vault | `C:\Nova\knowledge\TrueLine-Wiki` | Obsidian wiki: session-by-session history (`hot.md`, `current-sprint.md`, `log.md`). No remote; stage only touched files. |

In-repo `wiki/` holds the canonical bootstrap `START_HERE_TRUELINE_V2.md` plus engine design
records (`m8_*.md`, `m9_*.md`, doctrine).

## 3. Tech stack and why

- **Python 3.11 + FastAPI + uvicorn** (`truelinev2/`): the engine is pure-Python determinism; FastAPI
  is a thin, flag-gated serving shell. Pins in `truelinev2/requirements.txt` are exact for the web
  stack (`fastapi==0.136.1`, `starlette==1.0.0`, `uvicorn==0.47.0`, `pydantic==2.13.4`) because CI
  route-mounting behavior diverged across versions; loose pins for `PyMuPDF>=1.23`, `openpyxl`,
  `Pillow`, `pytest`.
- **PyMuPDF (fitz)** — the only PDF engine; wrapped once in `truelinev2/ingest/pdf.py` (`PlanPdf`).
  Chosen for exact text+vector extraction and rasterization; the whole product is **PDF-first**
  (pixel-space truth before any geospatial/KMZ export).
- **No database for the product store.** Customer state is **JSON records on disk** under
  `data/outputs/truelinev2/<root>/customer_projects/<tenant>/processing_jobs/<job>/` — one file per
  contract record, audit arrays inline. Chosen for inspectability, diffability, and zero infra. A
  small SQLite (`store/db.py`) exists only for the internal review store.
- **Next.js (separate repo) for web**, **Expo for mobile** — contract-first: both consume the same
  tenant-scoped JSON API; the web bakes its tenant at build time.
- **Windows-native ops**: staging is this dev box — `uvicorn :8100` + `next start :3000` (loopback
  only) exposed via a **cloudflared tunnel** to `staging.fieldroute.io` / `api-staging.fieldroute.io`,
  gated by **Cloudflare Access** (one-time-PIN). A PowerShell **supervisor**
  (`data/outputs/truelinev2/staging_smoke/ops/staging-supervisor.ps1`, scheduled task) heals all
  three processes; it is also where the served store root and TL2_* env flags are set durably.
- **pytest** everywhere; the deterministic corpus is the regression backbone (see §6).

## 4. Architecture

### 4.1 The v2 package (`truelinev2/`)

```
schema/      canonical pydantic models (Bore, Callout, Placement, frames, hierarchy)
ingest/      PlanPdf (rotation-safe fitz wrapper), bore-log normalizers (flat-table, VeroFy),
             sheet_label_index (title-block "N OF M" → real PDF page)
extract/     THE DIALECT SEAM. PlanDialect base + registry.select_dialect (line 19) picks the
             convention-specific extractor (two named dialects + a name-free generic-geometry
             fallback). ~30 observer modules: callout/matchline/structure/stroke anchors, termini,
             station axes, tick ladders, route isolation, corridor pruning, KMZ import.
match/       convention-agnostic matcher: engine.run_match (line 57) → chains → score → decide.
             Honest abstain with named reasons; collision gates; shared-alignment fusion;
             run-assembly (cross-sheet legs joined by printed SEE-SHEET equations).
render/      crop.py — clip-bounded evidence crops; REDLINE_STROKE_RGB=(220,25,25) at line 23
             (test-locked "Red Stroke Law"); caption band default ON (diagnostics) and OFF for
             product handoff. source_anchor_render.py — human-clicked control-point renders.
contracts/   the PRODUCT layer (~25 modules): processing_job lifecycle, uploads, reviewed_bore_log
             (the human review gate), source_anchor, recognized_corpus_handoff (load_registry,
             sha256-keyed replay), uploaded_corpus_engine_handoff (_cap_review, line 172),
             review_acceptance (generate_review_candidate, line 231), product_workflow
             (export_gate, line 226), closeout_review/closeout_pdf/export_package, job_pricing
             (station math), billing_summary, kmz_export, gis_route, field_evidence.
harness/     read-only cold-package readiness spine: review_readiness classifier → span_extractor
             → endpoint_binding → route_verification → review_candidate (drawing-capable, gated
             STRICTLY on READY_FOR_REVIEW_REDLINE).
api/         thin FastAPI: app factory (fail-closed CORS), container (wired singletons), deps
             (X-TL-Tenant/X-TL-Session → RequestContext, 401 via IsolationError), route modules
             all mounted ONLY behind default-OFF TL2_* flags (see config.py).
security/    fail-closed tenant isolation + output sanitization. context.py binds tenant+session.
proof/       ~170 run_*.py proof scripts — the per-bore/per-capability evidence harnesses that
             built the deterministic frontier. Additive; never product-critical at runtime.
tests/       215 test files (~2,330 cases). Full suite needs gitignored fixtures under data/.
docs/        design docs (readiness spine, G4 terminus, georeferencing design, council reports,
             production-ops baseline).
```

### 4.2 A customer job's data flow

```
 upload (base64 JSON, tenant header)             kinds: PLAN_PDF · BORE_LOG · GIS_ROUTE · PHOTO
        ▼
 processing_job record (status machine: CREATED → UPLOADING → EXTRACTING → AWAITING_REVIEW
        ▼                                → PLACING → PLACED → CLOSEOUT_REVIEW → …)
 reviewed_bore_log — rows extracted (strict reader first, generic span extractor fallback) as
        │            UNTRUSTED/UNREVIEWED; a HUMAN confirms/corrects each row (audit-trailed).
        │            Nothing downstream runs until rows are engine-ready.  ◄── HUMAN GATE 1
        ▼
 placement, one of three lanes (contracts/product_workflow, in order):
   1. RECOGNIZED replay — exact sha256 fingerprint match in the recognized-corpus registry →
      serve the committed deterministic render (AUTO; the only no-review lane).
   2. LIVE ENGINE — ingest → dialect extract → run_match. A clean AUTO_SELECT on a customer
      upload is CAPPED to a REVIEW candidate by default (TL2_UPLOADED_CORPUS_AUTO_OPTIN unset);
      raw engine verdict preserved as metadata.                          ◄── HUMAN GATE 2
   3. MANUAL source-anchor — human clicks ordered control points on the plan raster; rendered
      as a dashed REVIEW stroke (never invented geometry).
        ▼
 redline bundle — redline_manifest.json + FINAL_REDLINE_PNG artifacts (red strokes only)
        ▼
 review acceptance (accept / reject / correct)                            ◄── HUMAN GATE 3
        ▼
 closeout review (gate checks, honest warnings e.g. KMZ_EXPORT_BLOCKED) → READY_FOR_APPROVAL
        ▼
 export: closeout PDF + data .zip (download 409-gated until review resolved) + operator pricing
         (footage from CONFIRMED bore-log station ranges; dollars only from operator-entered
         rates, disclaimed OPERATOR_ENTERED_UNVERIFIED; server billing only if a cost-rules file
         is configured — never both confused)
```

### 4.3 Staging topology

```
 Internet ── Cloudflare Access (OTP) ── cloudflared tunnel ──┬── 127.0.0.1:3000  next start
   staging.fieldroute.io / api-staging.fieldroute.io         └── 127.0.0.1:8100  uvicorn (this repo)
 supervisor (scheduled task): staging-supervisor.ps1  -Once = heal · -Status = report
                                                      -Restart = KILLS ALL THREE (never use casually)
 served store root: $StoreRoot in the supervisor → TL2_PRODUCT_STORE_ROOT
```

## 5. Key design decisions (and why)

1. **Zero-false beats coverage.** The engine must never draw a wrong redline. Abstention is an
   honest, *named* outcome (`NO_CALLOUTS_EXTRACTED`, `BORE_LOG_FORMAT_UNRECOGNIZED`, …), treated as
   an unmodeled relationship to engineer away — never silently guessed around.
2. **No AI / runtime API in the truth path.** Every placement is deterministic and source-derived.
   LLMs build the product; they are not *in* the product.
3. **REVIEW ≠ AUTO ≠ final.** Three distinct tiers. Drawing-capable REVIEW candidates gate strictly
   on readiness; AUTO on uploaded packages is owner-gated (capped to REVIEW by default); "final" is
   a human acceptance. Banked human grades are never overridden by the engine.
4. **The dialect seam.** Only plan-evidence *extraction* is convention-specific (`PlanDialect`);
   matching/scoring/rendering/serving are convention-agnostic. A new plan convention is a new
   dialect, not an engine fork — the founding lesson from v1, which welded one grammar into
   extraction and returned 0 callouts on any other convention.
5. **Byte-identity regression discipline.** Every engine-adjacent change must leave all prior proof
   renders byte-identical (md5-compared) and the locked counts unchanged: deterministic frontier
   **50/58** bores drawn, **DETERMINISTIC_AUTO count = 49**, cold matrix **11/11**, full suite green
   (2,332 pass / 4 skip as of 2026-07-06). New behavior ships behind **default-OFF flags**
   (`truelinev2/config.py` — every `*_optin` documents "OFF is byte-identical").
6. **Recognition by content hash.** The recognized-corpus registry
   (`data/recognized_corpus_registry.json`, loaded by `contracts/recognized_corpus_handoff.py`)
   maps *exact sha256 fingerprints* to committed deterministic renders. Any edited/re-saved file is
   NOT recognized and falls to the live-engine lane — deliberate (provenance) but surprising.
7. **Tenant = directory.** Isolation is path-scoping under the verified tenant id
   (`^[a-z0-9][a-z0-9_-]{0,62}$`) with fail-closed containment re-asserts; identity itself is a dev
   stand-in header pair behind Cloudflare Access (see GAPS.md #1 — real auth is deliberately
   deferred, owner-gated).
8. **Honest UI over convenient UI.** No mock fallback in live mode, no fake $0, no invented
   defaults, refusals carry the specific reason, "the app does not guess" is stated to the
   customer. Enforced in copy constants (e.g. `REVIEW candidate — not AUTO, not final placement`).
9. **Generic naming (HARD RULE).** No customer/person/place/demo names in reusable code, routes,
   env, schema, tests, or doc headings — real names are runtime data. Customer-facing UI never says
   "demo". (The two dialect modules carry convention names by design; that seam predates the rule.)
10. **PDF-first before KMZ.** Pixel-space redlines are the deliverable; KMZ export is honestly
    `BLOCKED (UNSUPPORTED_PIXEL_ONLY)` until georeferencing is designed
    (`truelinev2/docs/REDLINE_GEOREFERENCING_DESIGN.md`).

## 6. Critical paths — load-bearing vs. safe

**Never touch without explicit owner approval** (regression tripwires all over the suite):
- `truelinev2/extract/registry.py::select_dialect` and the named dialect detectors
  (`extract/brenham.py`, `extract/odot.py`)
- `truelinev2/contracts/uploaded_corpus_engine_handoff.py::_cap_review` (line 172)
- Renderer truths: `truelinev2/render/` (stroke color, caption defaults, clip math)
- Closeout acceptance policy and the AUTO/final tier rules
- The locked constants in §5.5 — re-verify after ANY engine-adjacent change

**Load-bearing but extensible with care** (additive patterns established):
- `contracts/` product records — add fields/records, never mutate semantics of existing ones;
  every record carries `record_format` version strings
- `api/product_pipeline_routes.py` — add routes behind flags; error mapping via `_to_http`
- `harness/` readiness spine — additive stages only, gate strictly on classifier statuses

**Safe to change casually:**
- `truelinev2/proof/` scripts (additive evidence harnesses)
- `truelinev2/docs/`, `wiki/` (docs are living)
- Web copy/UX — but that lives in the SEPARATE web repo, never here
- Anything under `data/` (gitignored runtime data; still respect the store you're touching)

## 7. Surprises that WILL trip you up

1. **The default git branch is a trap.** `origin/main` (068a279) is v1-era, ~407 commits behind
   `feat/truelinev2`. Everything real is on `feat/truelinev2`.
2. **`backend/venv` is broken.** Use the repo-root `venv\Scripts\python.exe` (Python 3.11.9) with
   `PYTHONPATH=.` for ALL Python work, including legacy `backend/tests`.
3. **`data/` is entirely gitignored** — the deterministic fixtures, the product stores, the staging
   supervisor, and the recognized-corpus registry all live there. Tests that need fixtures skip
   when absent; CI (`.github/workflows/backend-checks.yml`) runs only a 13-file targeted subset and
   CANNOT see the render corpus.
4. **Multiple sibling store roots** under `data/outputs/truelinev2/` (`product_store` default,
   `staging_smoke` served, `council_audit` holds curated demos NOT served, `product_store_staging`
   stale, various probe roots). Which one is live is decided by `$StoreRoot` in the staging
   supervisor. Demos "existing" ≠ demos "served".
5. **Rotated plan pages have two bounds APIs.** `PlanPdf.page_rect_bounds` (line 52) is the
   raster/render basis (what humans click on); `page_bounds_display` (line 35) double-rotates on
   rotated pages and is kept ONLY for legacy text/vector consumers. Product paths must use
   `page_rect_bounds`. Source anchors created before 2026-07-06 on rotated pages are stored in the
   broken space and must be re-marked.
6. **Recognition is per-file-hash** (§5.6): editing a bore-log xlsx silently moves a job from the
   recognized lane to the live-engine lane.
7. **The web UI you see on staging is a different repo's build**, with the tenant baked in at build
   time (`NEXT_PUBLIC_TL2_TENANT`). Running `npm run build` in that checkout overwrites the LIVE
   served `.next`. There are rollback snapshots (`.next.prev-*`).
8. **Supervisor `-Restart` kills web + tunnel too.** The safe bounce is: kill only the target
   process, then `-Once`.
9. **The repo root `web/`, `node_modules/`, `.next/`, `.vercel/` are v1 leftovers** — not the
   product web app. Root `AGENTS.md` / `AI_rules.md` / `RUNBOOK.md` are v1-era agent/ops docs
   (historical; superseded by CLAUDE.md + the wiki).
10. **Institutional memory lives outside the code**: `wiki/START_HERE_TRUELINE_V2.md` (current
    truth, bumped per session) + the external vault. Snapshots go stale mid-session — verify
    against `git` and the live system before trusting any of them (this has bitten real sessions).
11. **`.claude/worktrees/` may contain other live agent sessions.** Do not touch.
12. **uvicorn runs at `--log-level warning` with no access log** — destructive API calls leave no
    trace today (see GAPS.md #2 and the 2026-07-06 store incident).
