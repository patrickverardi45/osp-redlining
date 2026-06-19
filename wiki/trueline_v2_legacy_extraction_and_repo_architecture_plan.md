# TrueLine v2 — Legacy Extraction & Repo Architecture Plan

> Canonical forward-architecture plan. Lane `TRUELINE_V2_LEGACY_EXTRACTION_AND_REPO_ARCHITECTURE_PLAN`,
> recorded 2026-06-19. Planning/docs only — no code, no deploy, no repo teardown implied.
> Related: [`trueline_v2_engine_website_readiness_audit.md`](trueline_v2_engine_website_readiness_audit.md) ·
> [`trueline_v2_redline_manifest_contract.md`](trueline_v2_redline_manifest_contract.md) ·
> [`ui/fable_v2_ui_bones.md`](ui/fable_v2_ui_bones.md). Memory: `v2-forward-legacy-extraction-direction`.

## Stance (owner-confirmed reframe)

**v2 is the product. v1 is a legacy prototype — a reference spec and an algorithm parts-bin, NOT
sacred architecture.** v1 was the prototype; the v2 engine was built from its lessons (mirror correct
**behavior**, not bad design).

- **v2 product = the v2 engine (`truelinev2/`) + the `redline_manifest` durable-bundle contract + the
  Fable UI** (`trueline-web-experience` web, `trueline-field-mobile` mobile).
- **PDF-first redlines are truth before KMZ.** KMZ is an output/overlay + a georeference input, not the
  primary truth source.
- **v1 auth is reference-only.** Future auth/security uses an external, already-established security
  provider, so v1's JWT/pilot-token/TOFU implementation is **not** a blocker and **not** carried
  forward — only the *tenant-isolation requirement* (cross-tenant 403) survives as a requirement.
- v1 is **not** preserved because it is the live monolith. It keeps running only for **client
  continuity** until v2 reaches parity, then it is retired **last**.

**The one surviving hard caution:** `truelinev2/` (the v2 engine, ~432 files) currently lives **inside**
`TrueLine_Beta` (= GitHub `osp-redlining`). **Never wipe/reset that repo until the engine is
intentionally split out** — doing so would lose the engine. Keep all changes path-scoped (the
`git add -A` landmine).

## What "v1" is

`C:\Nova\projects\TrueLine\TrueLine_Beta` = GitHub repo **`osp-redlining`**, which is two things at once:
- `origin/main` = the **v1 full-stack monolith** (`backend/` FastAPI on Render, ~25k-LOC `main.py`;
  `web/` Next.js on Vercel; `extractor/`; deploy config) — **live in production**
  (`osp-redlining.vercel.app` + `osp-redlining-backend.onrender.com` + S3 + JWT).
- `feat/truelinev2` = that same monolith **plus the v2 engine** (`truelinev2/`).

The Fable app (`trueline-web-experience`) is a separate, **frontend-only** repo (mock API, no backend),
already branded "TrueLine" and clean of the `osp-redlining` slug.

## Legacy keeper / discard table

**Keep** — as v2 product requirements and/or clean reusable cores (re-realized v2-native, **not** ported):

| v1 piece | v1 location | Carry forward as | Lands in |
|---|---|---|---|
| KMZ export / geometry | `backend/app/core/kmz_auto_redline.py`, `kmz_anchor_builder.py`, `kmz_stage_b2_streets.py` | Requirement + reusable geometry core (KMZ = output/overlay + georef input) | v2 backend (export service) |
| Closeout packet + readiness | `backend/main.py` lock/unlock routes; `web/.../office/CloseoutReadinessPanel*` | Product requirement (lock state, readiness checklist, packet contents) | v2 backend + Fable (Closeout/Packet shells exist) |
| Upload→parse→MRQ flow | `backend/app/api/upload.py`, `services/engineering_plan_parser.py` (3,191 LOC), `bore_log_service.py` | Concept (tenant-scoped session, async warm, parse→queue) + clean parser extraction | v2 backend |
| PDF serving | `backend/app/core/pdf_extraction_*`, `plan_page_renderer.py`, plan-image routes | Serving concept (plan page images, extraction endpoints) — engine supersedes redline truth | v2 backend (serving) + engine (truth) |
| Data/route concepts | session STATE schema, MRQ projection, override model, `engineered_segments`, `/current-state` | Contract concepts for the v2 API surface | v2 backend contracts |
| Deploy/env lessons | `RUNBOOK.md`, `.vercelignore`, required-secret startup, Render persistent disk, exact-origin CORS, S3 artifacts, **no-CI gap** | Infra requirements doc for v2 | v2 infra docs / new backend |

**Discard / reference-only** — not product direction:

| v1 piece | v1 location | Verdict | Why |
|---|---|---|---|
| Old UI (`web/`) | `web/src/**` (14 pages) | Discard as direction; reference for parity + map components | Fable is the v2 UI; `RedlineMap`/`ModernHeroMap` kept only as design reference |
| Old auth/security | `backend/app/auth*.py`, `db.py`, `protected_router`, TOFU | Reference-only | External provider replaces it; keep only the tenant-isolation *requirement*, not the impl |
| Monolith glue | `backend/main.py` (~25k LOC), in-memory STATE coupling, route wiring | Discard | The architectural lesson is "don't"; v2 is modular |
| KMZ-first product direction | KMZ-as-primary-truth assumptions | Discard where it conflicts | v2 is PDF-first (redlines are truth before KMZ) |
| Streamlit frontend | `archive/frontend_streamlit/**` | Discard | Dead prototype |
| Generated / junk | `_junk_check/**`, smoke reports | Discard | Regenerable artifacts |
| `osp-redlining` brand/slug | deploy config + 3 v1 files (`web/.../jobs/page.tsx`, `projects/page.tsx`, `RedlineMap.tsx` export filename) | Retire **last** | Product is "TrueLine"; slug is v1 deploy only |

Nothing is hard-discard-now. The only "archive-when-replaced" is the v1 *frontend*, and only after Fable
reaches backend-wired parity.

## Future repo architecture

**Now (transitional monorepo):** `TrueLine_Beta` (`osp-redlining`) holds both v1 legacy (`backend/`,
`web/`) and the v2 engine (`truelinev2/`) + `wiki/`.

**Target end-state (intentional split, late):**

| Repo | Role | Status |
|---|---|---|
| `trueline-web-experience` (Fable) | **v2 UI** (web) | exists, local-only → give it a remote (next) |
| `trueline-field-mobile` | v2 mobile | exists (preserved) |
| v2 engine (`truelinev2/`) | redline engine + `redline_manifest` contract → durable bundle | **stays in `TrueLine_Beta` until an intentional split** (e.g. `trueline-engine`) |
| v2 backend/API (later) | serves the durable bundle + salvaged capabilities with **external auth** | new clean repo or clean extraction from v1 keepers — not a port |
| v1 (`backend/`+`web/` on `origin/main`) | legacy: kept running for continuity, mined for keepers | **retired last**, after parity + engine split |

`TrueLine_Beta` persists as the engine home through the transition; v1 code inside it is frozen/reference,
not extended.

## Migration phases (P0–P8)

- **P0 — Preserve (safety net):** tags + bundles for all repos/branches. *(Mostly done: Fable
  preservation tags + bundles, Phase-2K bundle, v2 archive tag. Gap: snapshot v1 `origin/main` + deploy
  config.)*
- **P1 — Establish the v2 UI repo:** `TRUELINE_V2_FABLE_REMOTE_INIT` — give Fable a remote. Additive,
  zero risk to v1. **← immediate next action.**
- **P2 — Keep the v2 engine stable:** continue engine work in `TrueLine_Beta`; **no split yet**.
- **P3 — Document backend keepers as v2 interfaces:** read-only mining of v1 → capability specs
  (export / closeout / upload / PDF-serving) + the v2 API contract surface. Extract clean cores, not glue.
- **P4 — Wire Fable → durable bundle:** extend the Phase-2J/2K read-only static consumption; stand up a
  **new** Vercel project on a fresh slug (staging, mock/read-only). v1's Vercel project untouched.
- **P5 — Build the v2 backend/API:** new/clean repo, **external auth**, serving the bundle + keepers.
- **P6 — Parity:** v2 UI + backend run in parallel with v1.
- **P7 — Intentional engine split:** `truelinev2/` → its own repo, once stable and the backend consumes
  it via a clean interface.
- **P8 — Retire v1 last:** new domain on the v2 project, retire the `osp-redlining` public route,
  decommission v1 backend, archive v1 content. **Brand/domain retired only after parity.**

## Risks

1. **Repo entanglement** — `truelinev2/` lives in `TrueLine_Beta`; a careless wipe/`git add -A` loses
   the engine. Mitigate: path-scoped changes; split (P7) before any v1 teardown.
2. **Porting bad design** — re-importing monolith glue. Mitigate: extract requirements + clean cores only.
3. **Auth-seam mismatch** — building the v2 backend around v1's JWT/TOFU instead of the external
   provider's contract. Mitigate: design the auth seam to the external provider; v1 auth is reference.
4. **Data continuity** — real client data in v1 (`session_store.db`, S3, Render `/data/uploads`).
   Mitigate: a coexistence/migration plan before v1 retirement.
5. **Premature decommission** — v1 still serves clients. Mitigate: parity-before-retire; no domain swap
   before P6.
6. **Scope under-estimation** — the v2 backend re-realizes ~26k LOC of v1 capability cleanly; the big
   lift. Mitigate: phase it (P3 specs → P5 build).

## Immediate next action

**`TRUELINE_V2_FABLE_REMOTE_INIT`** — establish the Fable repo on its own remote so it becomes the
official v2 UI repo. Unblocks P4 (new Vercel project) and is fully additive / zero risk to v1. Needs one
input: a destination GitHub repo URL for `trueline-web-experience`; then
`git remote add origin <url>` + `git push -u origin feat/2k-static-bundle-adapter`, with no touch to
`osp-redlining` / Vercel / Render / deploy.

## Brand/domain note

The product is already branded **"TrueLine"** on-screen; `osp-redlining` is only the v1 deploy slug
(`osp-redlining.vercel.app`) + repo name + a few v1 files. The rebrand is an **infra/domain move** (a new
Vercel project + domain for the already-clean Fable UI), and the old `osp-redlining` brand/domain is
retired **last — only after v2 UI + backend parity** (P8), never before.
