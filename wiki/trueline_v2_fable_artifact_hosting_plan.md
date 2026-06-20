# TrueLine v2 — Fable Staging Artifact-Hosting Plan

> Canonical planning doc. Lane `TRUELINE_V2_FABLE_VERCEL_STAGING_ARTIFACT_HOSTING`, recorded 2026-06-19.
> **Planning only — no `vercel`, no deploy, no env/domain change, no PNGs committed, no app-code change, no schema change.**
> Related: [`trueline_v2_fable_vercel_staging_plan.md`](trueline_v2_fable_vercel_staging_plan.md) ·
> [`ui/fable_v2_ui_bones.md`](ui/fable_v2_ui_bones.md) · [`trueline_v2_redline_manifest_contract.md`](trueline_v2_redline_manifest_contract.md).

## Goal

Let Fable staging (`https://trueline-web-experience.vercel.app/`) serve the **83 final redline PNGs** so that
setting **`NEXT_PUBLIC_TL2_REDLINE_MANIFEST_SERVED=1`** renders strokes — **without** committing the ~49 MB PNG
pile to GitHub. Staging is currently manifest/status-only (`served: false`); the manifest panel + adapter already
support served mode, so this is purely an artifact-delivery problem.

## 1. Recommended option for this staging milestone

**Storage = GitHub Release asset (Option 1) + Delivery = Vercel build-time prebuild fetch/copy (Option 2).**

Publish the bundle's `artifacts/` tree as **one immutable archive** attached to a **GitHub Release** (out of git
history), then a **Vercel prebuild step** downloads + verifies + extracts it into `public/redline-bundle/<id>/` at
build time. Backend serving (Option 3) is the later production path (P5), not needed now.

- **Primary (zero new service, zero secret if the repo is public):** GitHub Release asset on
  `patrickverardi45/trueline-web-experience`, tagged by bundle id.
- **Documented alternative (if the repo is private, or you prefer Vercel-native / a step toward production):**
  **Vercel Blob** (one store + a `BLOB_READ_WRITE_TOKEN`), or S3/R2. The delivery half (prebuild fetch → `public/`)
  is **identical** regardless of backend, so the storage choice is swappable behind one `TL2_REDLINE_BUNDLE_URL`.

## 2. Why it is safest

- **No git bloat / no PNGs in history** — release assets (and Blob/R2) live outside the tree; `public/redline-bundle/`
  stays gitignored.
- **No app-code or schema change** — the adapter already maps `manifestPath → /redline-bundle/<id>/<path>` at runtime
  (`v2RedlineManifest.ts:242`); the panel lazy-loads on expand. Only a prebuild script + two env vars are new.
- **Immutable + verifiable** — the bundle id `brenham-c19b565-ddfffff7cbe7` is content-keyed; the committed
  `redline_manifest.v1.json` carries a **sha256 per artifact**, so the prebuild can verify every PNG and fail the build
  on any mismatch/missing file (no silent wrong-bundle).
- **No new paid service / minimal secret** — a public GitHub Release needs no token; only the private/Blob path adds one.
- **Fully reversible** — unset the flag / drop the prebuild → back to availability-only, no data loss (see §7).
- **Honors all hard constraints** — no `vercel`, no deploy, no domain, no `osp-redlining`, no engine/render/placement
  truth, no manifest-schema change.

## 3. Exact artifact source path (on disk now)

Durable store (the bundle the website read contract resolves to via `store_index.json → latest_valid`), gitignored
under `data/outputs/`:

```
C:\Nova\projects\TrueLine\TrueLine_Beta\data\outputs\redline_manifest_publish\
  durable_store_proof\store\bundles\brenham-c19b565-ddfffff7cbe7\
    artifacts\<logId>\<file>.png      ← 83 PNGs, 49 MB   (THIS is what to archive)
    redline_manifest.json             (= committed fixture redline_manifest.v1.json)
    _published_bundle_index.json
    _store_bundle_meta.json
```

Example PNGs: `artifacts/log10/log10_s15_redline_stroke.png`, `artifacts/log11/log11_s5_redline_stroke.png`.
**Only the `artifacts/` subtree needs hosting** (the manifest/index already ship as committed fixtures).

## 4. Expected public URL / path shape the Fable UI consumes

The adapter builds, per artifact, `url = /redline-bundle/<bundleId>/<manifestPath>` (served mode only). So Next must
serve, from `public/`:

```
public/redline-bundle/brenham-c19b565-ddfffff7cbe7/artifacts/<logId>/<file>.png
  → served at  /redline-bundle/brenham-c19b565-ddfffff7cbe7/artifacts/<logId>/<file>.png
  → live:      https://trueline-web-experience.vercel.app/redline-bundle/brenham-c19b565-ddfffff7cbe7/artifacts/log10/log10_s15_redline_stroke.png
```

The prebuild must reproduce **exactly** that `public/redline-bundle/<id>/artifacts/...` layout (same as the existing
`scripts/export-redline-bundle.mjs`).

## 5. Does `redline_manifest.v1.json` need URL rewriting?

**No.** The manifest keeps the safe **relative** path `artifacts/<log>/<file>.png`; the adapter prepends
`/redline-bundle/<bundleId>/` at runtime (`v2RedlineManifest.ts:242`), and the `ARTIFACT_PATH` regex
(`/^artifacts\/[a-z0-9_]+\/[a-z0-9_]+\.png$/`) already constrains it. The committed fixture is correct as-is — **no
schema change, no manifest edit, no per-URL rewrite**. The only requirement is that the PNGs physically exist at the
matching `public/` paths at build time.

## 6. Exact implementation steps for the next coding lane

*(Coding lane — NOT executed here.)*

0. **Determine repo visibility** of `patrickverardi45/trueline-web-experience` → public ⇒ GitHub Release (no secret);
   private ⇒ Vercel Blob or a build-time `GITHUB_TOKEN`.
1. **Make the immutable archive** from the on-disk bundle (§3): `tar -czf
   redline-bundle-brenham-c19b565-ddfffff7cbe7.tgz -C <bundle> artifacts` (≈49 MB; well under GitHub's 2 GB asset limit).
2. **Upload it** as a GitHub Release asset (tag e.g. `redline-bundle-brenham-c19b565-ddfffff7cbe7`) → stable download
   URL. *(Blob path: `vercel blob put …` → URL + token instead.)*
3. **Add `scripts/fetch-redline-bundle.mjs`** (Fable repo): read `src/lib/api/fixtures/redline_store_index.v1.json`
   (`latest_valid` = bundle id) + `redline_manifest.v1.json` (artifact `path` + `sha256`); download the archive from
   `process.env.TL2_REDLINE_BUNDLE_URL`; extract into `public/redline-bundle/<id>/artifacts/...`; **verify each PNG's
   sha256** against the manifest and that the count is 83; fail the build on any mismatch/missing/extra. Reuse the
   `ARTIFACT_PATH` safety + layout from `export-redline-bundle.mjs`.
4. **Wire it as `prebuild`** in `package.json` (`"prebuild": "node scripts/fetch-redline-bundle.mjs"`) so it runs
   before `next build`; keep `public/redline-bundle/` gitignored (already is).
5. **In the Vercel project** set `TL2_REDLINE_BUNDLE_URL=<asset URL>` and `NEXT_PUBLIC_TL2_REDLINE_MANIFEST_SERVED=1`
   (+ a read token only for the private/Blob path). Redeploy.
6. **Verify** `/redlines` → expand → 83 images load from `/redline-bundle/brenham-c19b565-ddfffff7cbe7/artifacts/...`;
   panel header reads `served: true`; build log shows the prebuild fetch + 83/83 sha256-verified.

## 7. Rollback plan

- **Instant:** unset `NEXT_PUBLIC_TL2_REDLINE_MANIFEST_SERVED` in Vercel → next deploy is availability-only (filenames),
  exactly today's working state.
- **Full:** remove the `prebuild` script + `TL2_REDLINE_BUNDLE_URL`. Nothing to revert in git history (PNGs never
  committed). Delete the Release asset / Blob independently.
- Engine truth, the committed manifest fixtures, and the on-disk durable store are untouched throughout → no data loss,
  fully reversible.

## 8. Risks / limits

- **Repo visibility** — a private repo's Release asset needs a build token; Vercel Blob sidesteps this. (Step 0.)
- **Per-build cost** — ~49 MB download + extract per deploy (seconds); 83 static files is well within Vercel limits.
  Lazy-load means the client only fetches images on panel-expand (full expand ≈ 49 MB client transfer — fine for staging).
- **Bundle staleness** — the archive is pinned to `brenham-c19b565-ddfffff7cbe7` (render `c19b565`). A re-render yields a
  new content-keyed id; the archive **and** `TL2_REDLINE_BUNDLE_URL` **and** the committed fixtures must be re-published
  together. The sha256 verification (step 3) catches a stale/mismatched bundle at build time.
- **Static-bake limit** — baking artifacts into the build is fine for one read-only reference bundle; it does **not**
  scale to many bundles / per-tenant data (that's §9 / P5).
- Raw `<img>` (not `next/image`) is intentional for static proof artifacts (already lint-suppressed in the panel).

## 9. What remains for production-grade artifact hosting

- **Object store keyed by bundle id** (S3/R2/Vercel Blob) with an index, so multiple bundles/versions coexist and the
  store's `latest_valid` pointer selects the served set — instead of one pinned Release asset.
- **Backend/API serving (P5)** by durable bundle id with auth, tenant scoping, and signed URLs — once there is real
  closeout/client data and external auth; replaces static-baking.
- **CDN caching + content-keyed cache-busting**; **automated publish** (engine `published_bundle_store` → object store →
  Fable picks up `latest_valid` in CI), removing the manual archive upload.

## Implementation status — code DONE (2026-06-19, lane `TRUELINE_V2_FABLE_STAGING_ARTIFACT_HOSTING_IMPL`)

**Fable web `main` `3ab0c80`** (pushed → `origin/main`; `feat/2k-static-bundle-adapter @ 51dcbf7` preserved, tag
`fable-v2-ui-bones-2026-06-19 → 7e3b392` intact): adds `scripts/fetch-redline-bundle.mjs` (+172), wires it as `prebuild`,
adds a `fetch:redline-bundle` convenience script, ignores `/.release-staging/`. **No PNGs / no archive committed** (3 files).

- **Archive (immutable, deterministic):** `redline-bundle-brenham-c19b565-ddfffff7cbe7.tgz` — the bundle's `artifacts/`
  tree only; **50,268,315 bytes (48 MB)**; **sha256 `864c657c7c22daf7d32e3c63b167dd56c71a2030eb6def608e392e411edc1eb0`**;
  83 PNGs; reproducible (sorted entries, fixed mtime, `gzip -n` — rebuilt-identical). Built locally at
  `trueline-web-experience/.release-staging/` (gitignored); source = the on-disk durable bundle (§3).
- **Script behavior:** no-op unless `NEXT_PUBLIC_TL2_REDLINE_MANIFEST_SERVED=1` or `--force`; reads `TL2_REDLINE_BUNDLE_URL`
  (https | file:// | local path); validates archive entries (path-escape / off-layout → fail); extracts into
  `public/redline-bundle/<bundleId>/`; verifies all 83 PNGs against the committed `redline_manifest.v1.json` sha256; fails
  loudly on missing URL, download failure, count != 83, or any sha mismatch. `tar` is driven via `-f -` (stdin) for
  Windows/Linux portability. **No manifest rewrite, no schema change** (URL is built at runtime by the adapter).
- **Local verification (all PASS):** `tsc --noEmit` · `contracts:check` · no-op path (SERVED unset, exit 0) · served
  extract+verify **83/83** · missing-URL fail · count-mismatch fail · **sha256-tamper fail** (caught
  `artifacts/log11/log11_s5_redline_stroke.png`) · `npm run build` PASS with SERVED=0 (prebuild no-op) **and** SERVED=1
  (prebuild fetch+verify 83/83 → `next build` → `/redlines` built, 83 PNGs in build input). The pre-existing lint finding
  `react-hooks/set-state-in-effect` at `src/app/packet/SummaryRail.tsx:43` is unrelated and does NOT block the Next-16 build.

### Remaining (owner / manual — agent does NOT run `vercel`, and `gh` is unavailable in the agent env)
1. **Upload the archive as a GitHub Release asset** (creates the immutable URL). Suggested tag
   `redline-bundle-brenham-c19b565-ddfffff7cbe7`. Run in the Fable repo:
   ```sh
   gh release create redline-bundle-brenham-c19b565-ddfffff7cbe7 \
     ".release-staging/redline-bundle-brenham-c19b565-ddfffff7cbe7.tgz" \
     --title "Redline bundle brenham-c19b565-ddfffff7cbe7" \
     --notes "Immutable artifacts/ tree: 83 FINAL_REDLINE_PNG, 48 MB, sha256 864c657c…"
   gh release view redline-bundle-brenham-c19b565-ddfffff7cbe7 --json assets -q '.assets[0].url'   # → TL2_REDLINE_BUNDLE_URL
   ```
   (Public repo ⇒ the asset URL is anonymously fetchable, no token. Private repo ⇒ the Vercel build also needs a read token,
   or use Vercel Blob instead.)
2. **Set Vercel env (project `trueline-web-experience`) + redeploy from the dashboard:**
   `TL2_REDLINE_BUNDLE_URL` = the asset URL from step 1; `NEXT_PUBLIC_TL2_REDLINE_MANIFEST_SERVED` = `1`.
3. **Verify after redeploy** (Next lane below).

## Next lane

**`TRUELINE_V2_FABLE_STAGING_ARTIFACT_HOSTING_VERIFY`** (after the owner uploads the release asset, sets the two env vars,
and redeploys): load `https://trueline-web-experience.vercel.app/redlines`, expand the panel, confirm the 83 stroke PNGs
render from `/redline-bundle/brenham-c19b565-ddfffff7cbe7/artifacts/...`, the header reads `served: true`, and the Vercel
build log shows `[fetch-redline-bundle] OK: 83/83`. No production/domain change; the agent does not run `vercel`.

## Env-debug patch — fetch made unconditional + diagnostics (2026-06-19)

`TRUELINE_V2_FABLE_ARTIFACT_FETCH_ENV_DEBUG` — Fable `main` **`16c7095`** (pushed; 2 files, no PNGs). Symptom: with the
owner's env set, staging still showed `served:false` and the Vercel build log had **no `[fetch-redline-bundle]` line** — the
npm **`prebuild`** lifecycle wasn't firing the script on Vercel.

- **Root cause (confirmed): NO env-var mismatch.** The fetch script (`scripts/fetch-redline-bundle.mjs`) and the UI served
  flag (`src/lib/api/client.ts:40`) BOTH gate on `NEXT_PUBLIC_TL2_REDLINE_MANIFEST_SERVED === '1'`; the adapter reads no env
  directly. The failure was the **build not invoking the fetch** (prebuild lifecycle), not the flag name.
- **Fix:** `package.json` build = **`node scripts/fetch-redline-bundle.mjs && next build`** (was `next build` + a separate
  `prebuild`); removed `prebuild` (no double-run, no lifecycle ambiguity). The fetch now runs **unconditionally** from
  `npm run build`; if served is on and the URL is missing / a sha mismatches, the `&&` short-circuits and the build **fails
  loudly** (won't deploy a broken served build).
- **Diagnostics (no secrets):** the script always prints an `env:` line — the flag value **quoted** (reveals stray
  whitespace or a wrong value like `"true"`) + `TL2_REDLINE_BUNDLE_URL=present(len=N) | <missing>` (length only, never the URL).

**Exact Vercel build-log lines to expect** (under `> node scripts/fetch-redline-bundle.mjs && next build`):
- env correctly set →
  `[fetch-redline-bundle] env: NEXT_PUBLIC_TL2_REDLINE_MANIFEST_SERVED="1" (served=true); TL2_REDLINE_BUNDLE_URL=present(len=N); force=false`
  → `[fetch-redline-bundle] archive <bytes> bytes; validating entries`
  → `[fetch-redline-bundle] OK: 83/83 FINAL_REDLINE_PNG verified -> public/redline-bundle/brenham-c19b565-ddfffff7cbe7/artifacts/...`
- SERVED not `1` → `…SERVED=<unset> (served=false); TL2_REDLINE_BUNDLE_URL=<missing>…` → `served mode OFF — skipping…`
- SERVED=`1` but URL missing → `…SERVED="1" (served=true); TL2_REDLINE_BUNDLE_URL=<missing>…` →
  `ERROR: served mode requested but TL2_REDLINE_BUNDLE_URL is not set` → **build fails**.

**Owner next step:** in Vercel, confirm `NEXT_PUBLIC_TL2_REDLINE_MANIFEST_SERVED=1` (exactly `1`, no trailing space) +
`TL2_REDLINE_BUNDLE_URL` are set for the **Production** environment, then **Redeploy WITHOUT build cache** (Deployments →
⋯ → Redeploy → uncheck "Use existing build cache") and read the build log for the `env:` + `OK: 83/83` lines, then re-run
`TRUELINE_V2_FABLE_STAGING_ARTIFACT_HOSTING_VERIFY`. Verified locally: tsc + contracts:check + `npm run build` PASS (no-op
shows `served=false`/skip; served build with the local archive shows the diagnostic + `OK: 83/83`).
