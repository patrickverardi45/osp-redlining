# TrueLine v2 — Fable Vercel Staging Plan (P4)

> Canonical planning doc. Lane `TRUELINE_V2_FABLE_VERCEL_STAGING_PLAN`, recorded 2026-06-19 (continued 38/39).
> **Planning only — no deploy, no `vercel`, no project link, no `.vercel/`, no env/domain change, no code change.**
> Related: [`trueline_v2_legacy_extraction_and_repo_architecture_plan.md`](trueline_v2_legacy_extraction_and_repo_architecture_plan.md) (P4) ·
> [`ui/fable_v2_ui_bones.md`](ui/fable_v2_ui_bones.md) · [`trueline_v2_redline_manifest_contract.md`](trueline_v2_redline_manifest_contract.md).
> Memory: `v2-forward-legacy-extraction-direction`.

## Purpose

Stand up a **new, separate** Vercel staging project for the preserved **Fable v2 web app**
(`trueline-web-experience`), read-only and mock — **not** a production swap. The live v1 `osp-redlining`
Vercel project, its domain, and the Render backend are **untouched and retired last**, only after v2 UI +
backend parity (architecture-plan P8). This doc is the plan + the future execution checklist; it executes
nothing that touches Vercel.

## Verified repo states (read-only, at record time)

| Repo | Path | Branch | HEAD | Remote / tracking | Tree |
|---|---|---|---|---|---|
| Engine/contract | `C:\Nova\projects\TrueLine\TrueLine_Beta` (GitHub `osp-redlining`) | `feat/truelinev2` | `bdbc3b1` | `origin/feat=bdbc3b1`, `origin/main=068a279` | clean |
| **Fable web** | `C:\Nova\projects\trueline-web-experience` | `feat/2k-static-bundle-adapter` | `51dcbf7` | `origin = https://github.com/patrickverardi45/trueline-web-experience`; upstream `origin/feat/2k-static-bundle-adapter` | clean |
| Fable mobile | `C:\Nova\projects\trueline-field-mobile` | `master` | `c61b2c3` | — | clean (untouched) |

- Fable web preservation tag `fable-v2-ui-bones-2026-06-19 → 7e3b392` intact; remote currently holds **only**
  `feat/2k-static-bundle-adapter` (no old branches pushed); **`.vercel/` absent** (not currently linked).

## Recommended Vercel project slug

**`trueline-web-staging`** → `trueline-web-staging.vercel.app`. Clean, on-brand, unambiguously *staging* +
*web* (vs mobile), fully disjoint from `osp-redlining`. Alternatives: `trueline-staging`,
`trueline-web-experience-staging`. **Never** reuse `osp-redlining`.

## Branch strategy

- **Initial:** point the staging project's production branch at **`feat/2k-static-bundle-adapter`** — the only
  pushed branch, Phase-2K visually-accepted, carries the static manifest adapter.
- **Recommended clean `main` step (git-only, safe):** create **`main`** from `51dcbf7`, push it, then set it as
  the **GitHub default** and the Vercel **Production branch**; feature branches become preview deploys. Removes
  the "feature-branch-as-default" smell before the project accretes deploy history. Pushing `main` does **not**
  auto-change the GitHub default — that is a manual repo-settings change (or `gh repo edit --default-branch main`).

## Build settings

| Setting | Value | Evidence |
|---|---|---|
| Framework preset | **Next.js** (Vercel zero-config auto-detect) | `next@16.2.9`, `next.config.ts` |
| Router / React | **App Router**, React 19.2.4 | `src/app/`, deps |
| Install command | **`npm install`** (or `npm ci`) — npm auto-detected | `package-lock.json` (no pnpm/yarn lock) |
| Build command | **`next build`** (`npm run build`) — Vercel default | `package.json` scripts |
| Output behavior | **Default serverful Next build** (`.next/`) — **not** static export (`next.config.ts` has no `output:'export'`); Vercel manages the output dir | `next.config.ts` (empty config) |
| Root directory | repo root `./` | layout |
| Node version | **Unpinned** (no `engines`, no `.nvmrc`/`.node-version`) → **set Node 20.x or 22.x** in Vercel project settings (Next 16 needs Node ≥ 20.9) | `package.json`, root listing |

No `vercel.json` / `.vercelignore` needed for the baseline.

## Environment-variable plan

Both flags are **build-time `NEXT_PUBLIC_*`** (inlined at build → set **before** the build; a change requires a
rebuild). `NEXT_PUBLIC_TL2_REDLINE_MANIFEST` gates the panel (`src/app/redlines/page.tsx:42`);
`NEXT_PUBLIC_TL2_REDLINE_MANIFEST_SERVED` gates PNG serving (`src/lib/api/client.ts:40`).

| Var | Staging value | Why |
|---|---|---|
| `NEXT_PUBLIC_TL2_REDLINE_MANIFEST` | **`1` (ON)** | Panel renders from the **committed** fixture `src/lib/api/fixtures/redline_manifest.v1.json` — no images needed; shows the real 50/58 manifest/status. |
| `NEXT_PUBLIC_TL2_REDLINE_MANIFEST_SERVED` | **unset / `0` (OFF)** | PNGs live under gitignored `public/redline-bundle/` → not in the Vercel build → ON would request undeployed images. Panel degrades gracefully to "filenames only" (`RedlineManifestPanel.tsx:102`). |
| `TL2_REDLINE_STORE` | **do not set** | Build-time-only input to the local `export:redline-bundle` script; irrelevant on Vercel. |

## Artifact / PNG staging plan

`scripts/export-redline-bundle.mjs` writes **committed fixtures** (`redline_store_index.v1.json` +
`redline_manifest.v1.json`, byte-identical to the durable bundle) **and** copies `FINAL_REDLINE_PNG`s into
**gitignored** `public/redline-bundle/<id>/`. `.gitignore` confirms `/public/redline-bundle/` +
`/public/engine-artifacts/` are never committed.

- **Do NOT commit the ~50 MB PNGs** (would bloat the repo + couple UI git history to render output).
- **Near-term (recommended): manifest/status-only.** Panel ON, SERVED OFF — zero new infra, already supported
  by the committed fixture ("availability-only mode").
- **Later:** publish the durable bundle to **object/static storage** (the engine's `published_bundle_store` is
  adapter-neutral by design), then a **Vercel prebuild step** fetches the PNGs into `public/redline-bundle/` and
  flips `SERVED=1`. Defer to P5-adjacent work.

## First staging objective

A live **read-only Fable shell** on `trueline-web-staging.vercel.app` proving: the repo **builds** on Vercel,
routes **render**, and `/redlines` shows the **committed 50/58 manifest/status** (no inline PNGs). **Out of
scope:** live render, upload flow, client data, backend/API, any domain swap. Mock/read-only only.

## Risks / blockers

1. **GitHub default = feature branch only** (`feat/2k-static-bundle-adapter` is the sole pushed branch) → do the
   clean-`main` step before deploy history accrues.
2. **Artifact PNGs gitignored** → not in the build → run availability-only (SERVED off); no strokes on staging.
3. **Pre-existing ESLint finding in `src/app/packet/SummaryRail.tsx`** → Next 16 decoupled ESLint from
   `next build`, so it should **not** fail the Vercel build; a **TypeScript** error *would*. Settle with a local
   `npm run build` preflight.
4. **No backend/API yet** → backend-dependent surfaces are mock; nothing to wire.
5. **Read-only preview only** — Fable is not a production replacement; do not attach a real/product domain.
6. **`osp-redlining` remains live** — keep the staging project, slug, and domain fully separate; no swap.
7. Node unpinned → pin 20.x/22.x in Vercel. `NEXT_PUBLIC_*` are build-time → set before first build.
8. The committed manifest fixture is a **snapshot** of bundle `brenham-c19b565-ddfffff7cbe7` (render commit
   `c19b565`) → staging reflects that snapshot until a fresh export is committed; it won't auto-track the engine.

## Exact future execution checklist (DO NOT EXECUTE here)

1. **Preflight** — Fable repo at `feat/2k-static-bundle-adapter @ 51dcbf7`, clean; `npm install` + **`npm run build`**
   locally to prove the production build passes (settles risk #3). Optionally `npm run contracts:check`.
2. **Decide slug** — `trueline-web-staging` (confirm available in the Vercel scope).
3. **Clean `main`** *(recommended)* — branch `main` from `51dcbf7`, push, set GitHub default + Vercel Production branch.
4. **Create the Vercel project** (dashboard) — import `github.com/patrickverardi45/trueline-web-experience`;
   **new project, do not touch `osp-redlining`**; Framework = Next.js (auto); Install/Build = defaults; Node = 20.x/22.x.
5. **Set production branch** — `feat/2k-static-bundle-adapter` (or `main` if step 3 done).
6. **Set env vars** (Preview + Production-of-this-project) — `NEXT_PUBLIC_TL2_REDLINE_MANIFEST=1`; leave
   `NEXT_PUBLIC_TL2_REDLINE_MANIFEST_SERVED` unset.
7. **Deploy preview** — trigger the first build; capture the `*.vercel.app` URL.
8. **Verify pages** — Dashboard, Hero Map, `/redlines` (50/58, "filenames only"), Plan Viewer, Closeout, Packet, etc.;
   check the build log for the SummaryRail lint finding's (non-)impact.
9. **Verify isolation** — confirm the `osp-redlining` Vercel project, domain, and Render backend are untouched;
   new project is a separate slug.
10. **Document** — record project name, URL, branch, env, Node, and bundle snapshot id into `wiki/` (next save).

## Boundaries / confirmation

This plan changes nothing on Vercel, Render, env, or any domain, and does **not** touch the live `osp-redlining`
project/domain/route. The Fable web/mobile app code and the `TrueLine_Beta` engine truth (engine/render/fixtures/
census/placement) are untouched. The only actions taken under this lane are **docs** (this file) and a **git-only**
clean-`main` branch creation in the Fable repo (separate repo; never `osp-redlining`).

## Standup result — DONE (2026-06-19)

`TRUELINE_V2_FABLE_VERCEL_STAGING_STANDUP` executed by the owner in the Vercel dashboard (the agent ran no
`vercel` / deploy / env / code action). The Fable web app is **live at
`https://trueline-web-experience.vercel.app/`** (Vercel project **`trueline-web-experience`**, owner-provided
2026-06-19 — the project reuses the repo name rather than the earlier-recommended slug `trueline-web-staging`),
from repo `patrickverardi45/trueline-web-experience`, branch **`main`**, commit **`51dcbf7`**; `/redlines` renders with the
existing Fable UI intact and the **v2 redline manifest (durable bundle)** panel showing **50/58**, bundle
**`brenham-c19b565-ddfffff7cbe7`**, render/source **`c19b565`**, **83 FINAL_REDLINE_PNG**, **`served: false`**.
This is **manifest/status-only** staging (Option D) — no live render, no upload flow, no client data, no production
swap; the old `osp-redlining` project/domain is untouched.

**Verification (agent, read-only — no `vercel`, no deploy):** every observed value reconciles with the committed
source-of-truth that a `main @ 51dcbf7` build serves —
- branch/commit: live default branch = `refs/heads/main`, `origin/main = 51dcbf7` → a Vercel project on `main` builds `51dcbf7`;
- `50/58` = `src/lib/api/fixtures/redline_manifest.v1.json` `summary.frontier`; render/source `c19b565` = its `engine.render_commit`; `mock_example: false`;
- bundle id `brenham-c19b565-ddfffff7cbe7` = `src/lib/api/fixtures/redline_store_index.v1.json` `latest_valid` (both fixtures committed → travel with `main`);
- `83 FINAL_REDLINE_PNG` = 83 artifact entries (a raw grep returns 84: 83 artifacts + 1 textual mention in `consumption_rules`);
- `served: false` because `NEXT_PUBLIC_TL2_REDLINE_MANIFEST_SERVED` is unset (no committed `.env` forces it) and the `public/redline-bundle/` PNGs are gitignored/local-only.

## Next unresolved work (each separately gated; none started)

1. **Artifact hosting for PNGs without committing 50 MB into GitHub** — publish the durable bundle's
   `FINAL_REDLINE_PNG`s to **object/static storage**, or a **Vercel prebuild fetch/copy** into `public/redline-bundle/`,
   then flip `NEXT_PUBLIC_TL2_REDLINE_MANIFEST_SERVED=1` so strokes render (the engine's `published_bundle_store` is
   adapter-neutral by design). Until then staging stays manifest/status-only.
2. **Backend / API serving** — a clean v2 backend serves the durable bundle + salvaged capabilities (architecture-plan P5).
3. **External auth / security** — v2 uses an external established provider; v1 auth is reference-only (P5).
4. **Production domain / cutover** — a real domain on the v2 project, retiring `osp-redlining` **last**, only after
   v2 UI + backend parity (P6 → P8). No domain swap before then.

## Next lane

**`TRUELINE_V2_FABLE_VERCEL_STAGING_ARTIFACT_HOSTING`** — unresolved item 1 above (object/static storage or a Vercel
prebuild fetch for the PNGs) so `…_SERVED=1` can render strokes on staging. Planning-first; no production/domain change.
The Vercel project itself stands; the agent does not run `vercel`. **Canonical plan:
[`trueline_v2_fable_artifact_hosting_plan.md`](trueline_v2_fable_artifact_hosting_plan.md)** (recommends a GitHub Release
asset + a Vercel build-time prebuild fetch into `public/redline-bundle/<id>/`; no PNGs in git, no manifest-schema change;
next coding lane `TRUELINE_V2_FABLE_STAGING_ARTIFACT_HOSTING_IMPL`). **IMPL CODE ✅ DONE (Fable `main` `3ab0c80`)** — prebuild
fetch script + sha256 verify, locally proven; remaining = owner uploads the release asset + sets Vercel `TL2_REDLINE_BUNDLE_URL`
+ `NEXT_PUBLIC_TL2_REDLINE_MANIFEST_SERVED=1` + redeploys, then `TRUELINE_V2_FABLE_STAGING_ARTIFACT_HOSTING_VERIFY`.

## Staging UX — Cedar Ridge mock framing cleared (2026-06-19)

`TRUELINE_V2_FABLE_STAGING_REMOVE_CEDAR_RIDGE_CONFUSION` — Fable `main` **`85682bb`** (pushed; 6 files, pure label swaps,
no PNGs). The staging shell read as a "Cedar Ridge FTTH" mock project even though the real v2 Brenham durable-manifest panel
is present. Relabeled the **staging-facing project identity** to **`Brenham PH5 — v2 staging`**: Topbar project selector,
flagship project name + location (`Brenham, TX`), the `/redlines` header (now `mock review queue (N) · v2 durable redline
manifest = real engine data`), the EngineReviewPanel "Cedar Ridge queue" → "mock review queue", and the packet/closeout
display names. Layout unchanged; no upload/backend wiring; the real `RedlineManifestPanel` and the prebuild artifact fetch
are untouched. Internal ids (`p-cedar-ridge`) and deep mock **street names** (`Cedar Ridge Rd` in plan-sheet titles /
playback / Hero-Map road label) are intentionally left as mock content (a street name, not the project identity). Verified:
`tsc --noEmit` + `contracts:check` + `npm run build` PASS. NO engine/render/placement change; no Vercel/env/domain change by agent.

## Staging UX — mock portfolio shell → real v2 proof-viewer (2026-06-19)

`TRUELINE_V2_FABLE_STAGING_REMOVE_MOCK_DATA_SHELL` — Fable `main` **`f753b1a`** (pushed; 3 files, +78/−172, no PNGs).
Staging still showed a mock multi-project portfolio with fake customer KPIs above the real durable-manifest panel — not
demo-safe. Converted staging into an honest, read-only **v2 proof-viewer**:
- **Dashboard (`/`)** rewritten to a single **`Brenham PH5 — v2 staging`** summary driven by the REAL committed durable
  manifest (58 logs / 50 drawn / 1 covered / 7 blocked / 83 artifacts, bundle `brenham-c19b565-ddfffff7cbe7`, render
  `c19b565`) + a "what is real vs demo" note. Removed the portfolio KPI strip (`N projects · M active · mock data`),
  multi-project cards, and the mock field-activity / open-issues sections.
- **Global shell banner** (`layout.tsx`): `Read-only v2 staging · no upload / live render yet · some panels are UI demo
  only` — labels every route at once.
- **`/redlines`** now leads with the real `RedlineManifestPanel`; the mock review queue moved into a collapsed, dashed
  **`Mock UI demo queue — not engine data`** section below the engine panels.

**Upload / live engine processing remains a future backend / job-runner lane** (NOT built here). No upload/backend wiring;
manifest schema untouched; the prebuild artifact fetch and the real durable-manifest panel are intact. Verified: `tsc` +
`contracts:check` + `npm run build` PASS. NO engine/render/placement change; no Vercel/env/domain change by agent.
