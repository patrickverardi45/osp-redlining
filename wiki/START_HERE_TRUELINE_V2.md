# START HERE — TrueLine v2 / FieldRoute Bootstrap (tight)

> Single source of current working truth. Last save-session 2026-07-02 (continued-114) after the **field-evidence photo-thumbnail STAGING ACTIVATION** — thumbnails are now LIVE on staging and owner VISUAL-CONFIRMED (no code change this arc; docs-only bump).
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

## Repo states (verified 2026-07-02)

| Repo | Branch | HEAD | vs remote | Tree |
|---|---|---|---|---|
| `C:\Nova\projects\TrueLine\TrueLine_Beta` (backend/engine) | `feat/truelinev2` | capability **`9baa98a`** (photo byte-serving) + doc bumps → this save | **PUSHED** to `origin/feat/truelinev2` (0/0); `origin/main` `068a279` UNTOUCHED | clean (untracked proof PNGs only) |
| `C:\Nova\projects\trueline-web-experience` (FieldRoute web) | `main` @ **`0f85d85`** (local == origin) | photo-thumbnails slice **MERGED via PR #7** (merge commit `0f85d85`, contains `3927071`); prior arc via PR #6; merged branches `feat/field-evidence-photo-thumbnails` + `feat/hector-preflight` **DELETED** (local + origin, continued-114); `feat/review-readiness-panel` (PR #5) kept | web `origin/main` **`0f85d85`** | clean (untracked `.next.prev-*` rollbacks incl. `.next.prev-prethumbs`) |
| `C:\Nova\projects\trueline-field-mobile` (field app) | `master` | `4ac00a8` | **NO remote at all** — local-only (owner-gated) | clean |
| `C:\Nova\knowledge\TrueLine-Wiki` (vault) | — | continued-114 save | no remote; large pre-existing drift | stage ONLY touched files, never `git add -A` |

Engine truth: `DETERMINISTIC_AUTO=49`, deterministic **50/58**, cold matrix **11/11** — unchanged; targeted field-evidence/upload/product-API suites **140 pass** (photo slice). **Field-evidence photo thumbnails are now LIVE on staging and owner VISUAL-CONFIRMED** (continued-114, 2026-07-02): backend `9baa98a` (MERGED to web `main` via PR **#7**, merge commit `0f85d85`) adds a tenant-scoped PHOTO read `GET /jobs/{id}/uploads/{upload_id}/photo` (mounted only under `TL2_FIELD_EVIDENCE_API_OPTIN`; PHOTO-kind allowlist + fixed image content-type + path containment; wrong-tenant/missing/non-PHOTO/unsafe → uniform 404; **pure read**, no lifecycle/slot/review/closeout/placement/AUTO change, snapshot-locked). Web thumbnails render behind **`NEXT_PUBLIC_TL2_FIELD_EVIDENCE_THUMBS`** (null uploadId never fetches; failed fetch → honest "Photo unavailable."; no mock) — **now baked ON in the staging build**. **Activation (surgical, reversible):** staging backend bounced onto working tree `7984e27` (photo route now in live OpenAPI) + staging web rebuilt from `0f85d85` with the thumbs flag ON (BUILD_ID `jKX7Gx63Jz4qlWusomVf0`; rollback snapshot `.next.prev-prethumbs` = pre-thumbs `G54G1ONBF9H4OZfZCmBz2`); cloudflared tunnel never restarted. Prior arc on web `main` via PR **#6** (`52b46c5`; PR **#5** auto-resolved/superseded). Backend `origin/main` `068a279` + mobile UNTOUCHED.

## Recent commits (backend PUSHED; web arc MERGED to main via PR #6; mobile local-only)

- **Backend `feat/truelinev2` (PUSHED `9baa98a`):** …`42e55e9` no-500 fix → `05eb4e4` START_HERE post-merge bump → **`9baa98a`** *tenant-scoped PHOTO byte-serving* (read-only `resolve_upload_file` + `GET /jobs/{id}/uploads/{upload_id}/photo` under `TL2_FIELD_EVIDENCE_API_OPTIN`; 7 tests) → this doc bump. Prior in-window: `9351476` field-evidence WRITE contract, `635eddd` delete-job, `072fbaf` caption gate, `e78ef7a` cold census.
- **Web (prior arc on `main` `52b46c5` via PR #6):** `f16d88c` readiness panel → … → `24aff38` field-evidence display → `97421db` nav → `536fb26` candidate primacy. **NEW branch `feat/field-evidence-photo-thumbnails` (PUSHED `3927071`, PR #7 OPEN):** opt-in photo thumbnails behind default-OFF `NEXT_PUBLIC_TL2_FIELD_EVIDENCE_THUMBS` (header-bearing blob fetch of the backend `9baa98a` route; null uploadId never fetches; honest "Photo unavailable."; no mock).
- **Mobile `master` (local-only):** `bb1e6d4`→`d0f1e83`→`a2d9d77` (branding/live-read/segment-evidence) → **`4ac00a8`** field-evidence WRITE client (`fieldEvidenceWrite.ts`, env-gated default-OFF, kebab→snake maps, plain-English refusals, `npm run evidence:live-write`).

## Staging state (Cloudflare, LIVE)

- Zone `fieldroute.io`; tunnel `fieldroute-api-staging` (`47f42c57…`); `staging.fieldroute.io` + `api-staging.fieldroute.io`; Access team `morning-river-d67d`, One-time-PIN, verified blocking both. Same-origin path-split.
- **Backend live on working tree `7984e27`** (bounced continued-114; supervisor `-Once`). Live flags: `TL2_PRODUCT_PIPELINE_API_OPTIN=1`, `TL2_PRODUCT_READINESS_API_OPTIN=1`, **`TL2_FIELD_EVIDENCE_API_OPTIN=1`** (durable in supervisor; **photo read route `/uploads/{upload_id}/photo` now in live OpenAPI**). Bounce = kill uvicorn + supervisor `-Once` (reloads on-disk working tree; env durable in the gitignored `staging_smoke/ops/staging-supervisor.ps1`).
- **Web rebuilt + redeployed on `0f85d85`** (env `NEXT_PUBLIC_TL2_PRODUCT_API=1` + same-origin base `https://staging.fieldroute.io` + `staging-smoke`; **`NEXT_PUBLIC_TL2_FIELD_EVIDENCE_THUMBS=1`**; `FR_INTERNAL` unset = customer mode; BUILD_ID `jKX7Gx63Jz4qlWusomVf0`; rollback `.next.prev-prethumbs`). **Field Evidence panel renders real photo thumbnails** in Redline proof (owner-confirmed); Home exposes the workspace (two cards).
- **`generic-ready-demo`:** readiness `READY_FOR_REVIEW_REDLINE` + `REVIEW_CANDIDATE_READY` → the source-backed candidate is the **primary review surface**; the strict `/workflow/redline` abstains honestly (`BORE_LOG_FORMAT_UNRECOGNIZED`, HTTP 200, controlled — no 500, no closeout claim, review-only). Job stays `CREATED`.
- **`demo-general-upload`:** `REVIEW_ACCEPTED`, closeout **READY / pkg-2**, artifact route 200 (healed bundle `…fe3a80381e45`), pricing 150 ft × $15 = $2,250.00 — unchanged. Backups: `staging_smoke/ops/backups/demo-general-upload-*-2026-07-01/`.

## Mobile state (FieldRoute Capture — temp name)

- Expo SDK 56, managed workflow, **runs in Expo Go** (no native modules). Mock-first; env-gated READ-ONLY live client (`EXPO_PUBLIC_TL2_PRODUCT_API/_API_BASE/_TENANT[/_SESSION]`, default OFF; live REPLACES mock — never mixed; plain-English `statusCopy`, raw engine codes never render; REVIEW never AUTO/final).
- Field rules (`src/lib/fieldEvidence.ts` + `npm run evidence:check`, 21 checks): required START/END station photos are the only default-required evidence; per-problem photos demanded before completion; `BoreReading` with `offsetFt` (~50 ft NOMINAL, advisory) as the future digital-redline plot axis.
- Runtime smoke PASSED (Expo web + Playwright: 0 console errors on every screen; live env → honest-error card with zero mock rows; 5 screenshots).
- **Backend write side (`9351476`):** `contracts/field_evidence.py` (record `trueline-field-evidence-1` per segment; DRAFT→SUBMITTED_FOR_REVIEW then LOCKED; photos count only when bound to REAL job PHOTO uploads — evidence never invented; refusal `BLOCKED_MISSING_REQUIRED_EVIDENCE`) + `api/field_evidence_routes.py` (tenant-scoped, fail-closed) behind `TL2_FIELD_EVIDENCE_API_OPTIN` — **LIVE on staging**. `review_support_only=True`; submit changes no job status/slot.
- **Mobile write client EXISTS (`4ac00a8`):** `src/lib/fieldEvidenceWrite.ts` mirrors the read client — env-gated default-OFF, needs an explicit `EXPO_PUBLIC_TL2_WRITE_JOB` for the ticket submit; kebab→snake problem/method/photo maps (unknowns throw); plain-English refusals; PHOTO-upload/save/submit ops; `npm run evidence:live-write` (static + live smoke). Web office-review display (`24aff38`) consumes the same records.
- **NOT yet:** on-device write (needs a LAN-reachable backend — `:8100` is loopback-only); camera/GPS (native modules gated); photo thumbnails (no upload byte-serving route yet).

## Apple / TestFlight caution

Owner context: Patrick **HAS an active Apple Developer account** and **TestFlight installed on his iPhone**; he does **NOT have an App Store Connect API key** and does not yet know how to create one. Hard rules: **never automate Apple Developer / App Store Connect website login; never retry Apple ID/2FA — if Apple auth fails once, STOP and report.** When EAS/TestFlight time arrives, guide Patrick manually, step by step, through creating the ASC API key. Do **NOT** start EAS Build / TestFlight until (1) the mobile app is runtime-stable, (2) the final app name + bundle id are owner-approved ("FieldRoute Capture" is temp; "FieldRoute Field" REJECTED), and (3) Patrick explicitly approves. Today's distribution needs only Expo Go (QR scan); the repo also still has no remote.

## Current next choices (all owner-gated; none started)

1. **STAGING PHOTO ACTIVATION — DONE + tidied** (continued-114, owner visual-confirmed): backend bounced onto `7984e27` (photo route live) + web rebuilt on `0f85d85` with `NEXT_PUBLIC_TL2_FIELD_EVIDENCE_THUMBS=1`; temp-job smoke PASSED (right-tenant 200 image/png / wrong-tenant 404 / PLAN_PDF 404 / submit `SUBMITTED_FOR_REVIEW`); owner saw the thumbnails; temp jobs deleted; store back to exactly the 3 demos with all truths intact. PR #6 (`52b46c5`) + PR #7 (`0f85d85`) MERGED to web `main`; PR #5 auto-resolved/superseded. **Merged-branch cleanup DONE:** `feat/hector-preflight` (was `536fb26`) + `feat/field-evidence-photo-thumbnails` (was `3927071`) deleted local + origin (safe `-d`, ancestry-verified); `feat/review-readiness-panel` kept. **This arc has NO remaining required work.**
2. **Mobile remote** — create later (owner decides repo name/visibility; blocked on the FINAL app name — "FieldRoute Capture" is temp, "FieldRoute Field" REJECTED). Until then mobile is local-only.
3. **On-device mobile write** — needs an owner-approved LAN bind of the staging backend (`:8100` is loopback-only); the Access-gated public edge is NOT a mobile write path (native fetch can't do OTP; a bundled token would leak).
4. **Camera/GPS** native modules; bore-reading plotting on the proof surface. (Photo byte-serving route + opt-in thumbnails = DONE + LIVE on staging.)
5. **Source-backed candidate → closeout** is deliberately NOT wired (candidate stays review-only); wiring it is a separate owner-gated slice.
6. **Cold-package EVIDENCE COLLECTION** (not code): 32 packages need a bore-log span source; cold-011 needs the owner-gated B2 off-route-label binder. G-e final/AUTO owner-gated, NOT started; Hector v1-parity parked.

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
