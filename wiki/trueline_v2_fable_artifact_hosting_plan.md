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

## Next lane

**`TRUELINE_V2_FABLE_STAGING_ARTIFACT_HOSTING_IMPL`** — execute §6 in the Fable repo (coding lane): add the prebuild
fetch script + archive upload, then set the two env vars in Vercel and redeploy. No production/domain change; the agent
does not run `vercel` (env + redeploy are owner dashboard actions).
