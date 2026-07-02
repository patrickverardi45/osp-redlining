# START HERE — TrueLine v2 / FieldRoute Bootstrap (tight)

> Single source of current working truth, compressed 2026-07-01 after **continued 111**.
> Full session history: vault `wiki/log.md` + this file's own git history (pre-compression append-log version at commit `9c4ab33`).
> Verify against `git` before trusting any snapshot. Bump this file at `/save-session` — keep it TIGHT: update sections in place, do not re-grow an append-log.

## Doctrine

- **v2-forward.** v1 = legacy/reference only (including its auth). The product is the `truelinev2/` engine → `redline_manifest` bundle → FieldRoute web (`trueline-web-experience`) + field mobile. PDF redlines are source truth before KMZ.
- **Evidence-seeking.** A completed package CONTAINS the info. Abstain = an unmodeled relationship — an interim safety state and a named engineering target, never a manual fallback, never "done". Zero-false beats coverage.
- **Product lanes.** The engine need not auto-place 100%: abstains classify into product lanes (pick-card suggestions, human-adjustable REVIEW redlines). Banked human grades are never overridden.
- **REVIEW ≠ AUTO ≠ final.** Drawing-capable REVIEW candidates gate STRICTLY on `READY_FOR_REVIEW_REDLINE`. G-e / final AUTO is owner-gated and NOT started.
- **Improve, don't mirror.** Reproduce v1's correct behavior, never its bad design; if parity demands bad design, stop and propose v2-native.
- **Red Stroke Law.** Every drawn overlay is red (canonical `REDLINE_STROKE_RGB`, test-locked). Never recolor source PDF evidence.
- **Generic naming + no demo language.** No customer/project/person/demo/location names in reusable code, routes, env, schema, tests, docs headings — real names are runtime data only. Never show "demo" (or raw `demo-*` ids outside Diagnostics) in customer-facing UI.

## Repo states (verified 2026-07-01)

| Repo | Branch | HEAD | vs remote | Tree |
|---|---|---|---|---|
| `C:\Nova\projects\TrueLine\TrueLine_Beta` (backend/engine) | `feat/truelinev2` | this compression commit (child of `9c4ab33` = continued-111 bump; run `git log -1` for the hash) | **7 ahead / 0 behind** `origin/feat/truelinev2`; `origin/main` `068a279` UNTOUCHED | clean (untracked proof PNGs only) |
| `C:\Nova\projects\trueline-web-experience` (FieldRoute web) | `feat/hector-preflight` | `8b02722` | branch has **no upstream** (unpushed); **5 ahead** of web `origin/main` `1a2f822` (untouched) | clean (untracked `.next.prev-*` rollbacks) |
| `C:\Nova\projects\trueline-field-mobile` (field app) | `master` | `a2d9d77` | **NO remote at all** | clean |
| `C:\Nova\knowledge\TrueLine-Wiki` (vault) | — | `650f888` (continued-111 save) | no remote; large pre-existing drift | stage ONLY touched files, never `git add -A` |

Engine truth: full v2 suite **2278 pass / 4 skip**; `DETERMINISTIC_AUTO=49`, deterministic **50/58**, cold matrix **11/11** — unchanged all session. Web PR **#5** (`feat/review-readiness-panel` @ `f16d88c` → web main) is **OPEN/unmerged**, but its commit is already contained in `feat/hector-preflight`.

## Unpushed commits

- **Backend (7):** `635eddd` tenant-safe delete-job → `b43df3a` START_HERE 110 → `072fbaf` **caption gate** (diagnostic captions gated out of product redline PNGs; default True keeps diagnostics byte-identical, md5-locked) → `e78ef7a` **cold readiness census** (read-only, 35/35 public cold packages: 32× `MISSING_BORE_SPAN_SOURCE`, 2× `NO_SOURCE_CONFIRMED_SPAN`, 1× `ANCHOR_BLOCKED` = cold-011's named B2 off-route-label-binder gap; ZERO READY → zero artifacts drawn) → `9351476` **field-evidence WRITE contract** (below) → `9c4ab33` START_HERE 111 → this compression commit (`wiki: compress START_HERE for restart`).
- **Web (`feat/hector-preflight`, 5 ahead of main):** `f16d88c` PR #5 readiness panel → `a37f867` delete project/job → `fd34391` + `05531c7` v1-parity live pricing (footage × $15, source-span fallback) → `8b02722` remove dead-end showcase card.
- **Mobile (3 new; entire repo is local-only):** `bb1e6d4` branding/generic fixtures → `d0f1e83` live read-status client → `a2d9d77` segment evidence + bore readings.

## Staging state (Cloudflare, LIVE)

- Zone `fieldroute.io`; tunnel `fieldroute-api-staging` (`47f42c57…`); `staging.fieldroute.io` + `api-staging.fieldroute.io`; Access team `morning-river-d67d`, One-time-PIN, verified blocking both. Same-origin path-split.
- **Backend live on `072fbaf`** (supervisor `-Once`; temp-store real-engine E2E passed). Readiness/REVIEW-candidate spine live behind `TL2_PRODUCT_READINESS_API_OPTIN` (wiring commit `4a1c45a`, pushed). **Live `:8100` predates `9351476`** — field-evidence routes NOT mounted and flag OFF; the newer commits exist only locally, so bounce the staging backend onto a newer commit BEFORE testing field-evidence routes.
- **Web rebuilt + redeployed on `8b02722`** (landing has zero showcase refs). Env: `NEXT_PUBLIC_TL2_PRODUCT_API=1`, same-origin base, tenant; `FR_INTERNAL` proven OFF via 404 probe; rollback kept at `.next.prev-showcasefix`.
- Demo walkthrough bundle **healed** after the caption scrub's sha drift (bug `B-STG-BUNDLE-SHA-DRIFT-1`, FIXED): regenerated through the normal gated product path → bundle `staging-smoke-uploaded-corpus-engine-fe3a80381e45`, honest sha, `REVIEW_ACCEPTED`, export descriptor **pkg-2** caption-free (pkg-1 kept as immutable history). Backups: `staging_smoke/ops/backups/demo-general-upload-{heal,export-refresh}-2026-07-01/`.

## Mobile state (FieldRoute Capture — temp name)

- Expo SDK 56, managed workflow, **runs in Expo Go** (no native modules). Mock-first; env-gated READ-ONLY live client (`EXPO_PUBLIC_TL2_PRODUCT_API/_API_BASE/_TENANT[/_SESSION]`, default OFF; live REPLACES mock — never mixed; plain-English `statusCopy`, raw engine codes never render; REVIEW never AUTO/final).
- Field rules (`src/lib/fieldEvidence.ts` + `npm run evidence:check`, 21 checks): required START/END station photos are the only default-required evidence; per-problem photos demanded before completion; `BoreReading` with `offsetFt` (~50 ft NOMINAL, advisory) as the future digital-redline plot axis.
- Runtime smoke PASSED (Expo web + Playwright: 0 console errors on every screen; live env → honest-error card with zero mock rows; 5 screenshots).
- **Backend write side exists but the mobile write client does NOT:** `9351476` added `contracts/field_evidence.py` (record `trueline-field-evidence-1` per segment; DRAFT→SUBMITTED_FOR_REVIEW then LOCKED; photos count only when bound to REAL job PHOTO uploads — evidence never invented; refusal `BLOCKED_MISSING_REQUIRED_EVIDENCE` with named reasons) + `api/field_evidence_routes.py` (`GET/PUT/POST /v2/product/jobs/{id}/field-evidence[/{segment}[/submit]]`, tenant-scoped, fail-closed) behind NEW default-OFF `TL2_FIELD_EVIDENCE_API_OPTIN` — enabled NOWHERE. Doctrine test-locked: submit changes no job status/slot; `review_support_only=True`.
- Camera/GPS still gated (need native modules).

## Apple / TestFlight caution

Owner context: Patrick **HAS an active Apple Developer account** and **TestFlight installed on his iPhone**; he does **NOT have an App Store Connect API key** and does not yet know how to create one. Hard rules: **never automate Apple Developer / App Store Connect website login; never retry Apple ID/2FA — if Apple auth fails once, STOP and report.** When EAS/TestFlight time arrives, guide Patrick manually, step by step, through creating the ASC API key. Do **NOT** start EAS Build / TestFlight until (1) the mobile app is runtime-stable, (2) the final app name + bundle id are owner-approved ("FieldRoute Capture" is temp; "FieldRoute Field" REJECTED), and (3) Patrick explicitly approves. Today's distribution needs only Expo Go (QR scan); the repo also still has no remote.

## Current next choices (all owner-gated; none started)

1. **Push decisions** — backend 6-ahead; web branch push + preflight PR; PR #5 merge timing.
2. **Staging backend relaunch on `9351476`** IF field-evidence API should go live (then flip `TL2_FIELD_EVIDENCE_API_OPTIN`).
3. **Mobile WRITE client** — `fieldEvidence.ts` → the new API (mind kebab→snake problem kinds).
4. **Camera/GPS gate** + FINAL mobile app name.
5. **Cold-package EVIDENCE COLLECTION** (explicitly not code): 32 packages need a bore-log span source; cold-011 unblocks only via the owner-gated B2 off-route-label binder.
6. G-e final/AUTO remains owner-gated, NOT started. Hector v1-parity round parked.

## Guardrails

- **Never touch:** `select_dialect`, named detectors, `_cap_review`, renderer truths. AUTO/G-e BLOCKED. All prior proof/diagnostic renders stay byte-identical (caption default True).
- **Locked constants:** `DETERMINISTIC_AUTO=49`, deterministic 50/58, cold matrix 11/11, v2 suite green — re-verify after any engine-adjacent change.
- **`origin/main` untouched** in backend AND web unless the owner says merge.
- **New API surface ships behind default-OFF flags**, enabled nowhere until owner opt-in.
- **Tests:** repo-root venv (Python 3.11.9) + `PYTHONPATH` for backend tests; `backend\venv` is a broken trap.
- **Wiki vault:** stage only files you touched; never `git add -A`/push (no remote).
- **LAMA** mobile (`C:\dev\lama\lama-mobile`) is a separate product — never mix into TrueLine sessions.
- `truelinev2/` still lives INSIDE `TrueLine_Beta` — don't wipe the old tree until the engine split.
- Commit/push only when the owner asks; verify git truth before trusting any stale summary (including this file).

## Archived detail (load ON DEMAND only)

Vault (`C:/Nova/knowledge/TrueLine-Wiki/wiki/`): `hot.md` (top ~35 lines for latest), `current-sprint.md`, `log.md`, `bugs/current-bugs.md`, `index.md`. Repo: `gac/*.md` (adjudication packets), `wiki/active-context.md` (pre-continued-23 engine history). **Do NOT full-read the logs** unless tracing a specific historical decision.
