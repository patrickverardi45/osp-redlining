# START HERE — TrueLine v2 Canonical Bootstrap

> Single source of current working truth. Read THIS file first, in full — it is small on purpose.
> Snapshot below is current as of **2026-06-21 (continued 45 — kmz_export geometry-safety contract landed (pixel-only manifests BLOCKED, never fake coords, +10 tests); spine upload→review→handoff→export-safety; HEAD `2f70e22`; NO render-truth change; frontier 50/58)**. For the absolute-latest
> state, read ONLY the top ~35 lines of `C:/Nova/knowledge/TrueLine-Wiki/wiki/hot.md` — never the whole file.
> **Do NOT load history/archive files** (`log.md`, `current-sprint.md`, full `hot.md`) unless explicitly
> asked or investigating a specific historical decision.

## Product goal
Deterministic auto-placement of **ALL** redlines from the source files. Manual operator placement is NOT
the product. **Product gate = actual DRAWN red strokes on the PDFs** — classification / "placed for
review" buckets are not progress until they become drawn strokes.
- **ALL-REDLINES standard** (non-negotiable): place every redline from source; abstention is only an
  interim safety state + a *named* missing-source target, never a manual fallback or "done".
- **DO-NOT-WIDEN** (coexists): never place a wrong redline. Drive abstentions to zero by EXTRACTING the
  missing source relationship — not by guessing, and not by asking a human to decide from vibes.
- Identity-only bridges, NEVER invented coordinates. Every drawn stroke is red (canonical red-stroke law).

## Repo / branch state
- Repo: `C:/Nova/projects/TrueLine/TrueLine_Beta`  ·  Branch: `feat/truelinev2`
- Product lives in `truelinev2/` (clean-room, zero old-app imports). v2 suite: **1392 passed / 2 skipped**
  (log3/log44 added assertions to the existing sweep e2e — no new test). Callout-sweep e2e **31 passed / 1 skipped**.
- Isolated track: monolith / Render / Vercel UNTOUCHED; nothing merged or deployed.

## HEAD / remote state (verify with `git` before trusting this snapshot)
- Last RENDER commit: **`c19b565`** (log3 wired + DRAWN, 49→50/58 — UNCHANGED). Local HEAD = **`2f70e22`**
  (continued-45; kmz_export geometry-safety — `contracts: add kmz export geometry-safety contract`, 3 files/+493, pushed → `origin/feat/truelinev2` = `2f70e22`; tree clean). Prior: continued-44 handoff `2013879`; continued-43 gate `6048ef1`; continued-42 Slice 1 `2193a0e`; continued-41 `a4bf2a5` (docs/audit). Continued-41 engine-repo arc (7 commits on the continued-40 save `021561c`):
  `b9fd9cf` (staging URL) → `09fc469` (artifact-hosting plan) → `e886de2` (hosting IMPL recorded) → `377536d` (Cedar Ridge→Brenham relabel) → `5211102` (mock-shell→proof-viewer) → `2a559bd` (artifact-fetch env-debug) → `a4bf2a5` (v1 salvage audit + v2 pipeline contract). NO engine/render-truth change.
  Fable web (SEPARATE `trueline-web-experience` repo): `main` `51dcbf7`→**`16c7095`** (`3ab0c80` prebuild fetch → `85682bb` relabel → `f753b1a` proof-viewer shell → `16c7095` build-chain+diagnostic); default branch = `main`; LIVE at `https://trueline-web-experience.vercel.app/`.
  Prior saves: continued-40 `a4b8590`/`021561c` (staging standup); continued-39 `16295d4` (P4 plan + Fable clean main); continued-38 `bdbc3b1` (Phase 2J + Fable UI preserve/retire + repo-arch + remote-init P1).
  ARCHIVE (recovery): branch/tag `archive-v2-continued-35-superseded-scratch` = **`d8508b9`** (superseded `backend/tl_core/**` + 14 proof slices). `origin/main`: **`068a279`** (untouched).

## Latest — continued 45 (2026-06-21): kmz_export geometry-safety contract landed (pixel-only manifests BLOCKED, never fake coords); NO render-truth change; frontier 50/58
**continued 45 — the FOURTH permanent product-pipeline slice (KMZ/KML geometry safety); NO engine/renderer/fixture/anchor/corpus/census/parent-model/placement/flag change; frontier UNCHANGED 50/58; render commit stays `c19b565`; engine HEAD `2f70e22`; v2 suite 1550 passed / 4 skipped.**
- **KMZ export geometry-safety LANDED (lane `TRUELINE_PRODUCT_KMZ_EXPORT_GEOMETRY_SAFETY`, HEAD/origin `2f70e22`).** Commit `2f70e22` `contracts: add kmz export geometry-safety contract` (3 files / +493; staged explicitly, NO `git add -A`; pushed, HEAD = origin = `2f70e22`, tree clean). One GENERIC, contract-only, pure-stdlib module + its test + the +1-line guard extension. **Decisive finding:** the v2 redline manifest has NO geospatial basis (only `source_sheets`/`span` stations/`closure` footage/PNG `artifacts`; schema `additionalProperties:false`), so every REAL manifest classifies `UNSUPPORTED_PIXEL_ONLY` and the export is BLOCKED — the system abstains rather than fake coordinates.
  - `truelinev2/contracts/kmz_export.py` — geometry-basis classifier (`GEOSPATIAL_COORDINATES`/`GEOREFERENCED_SHEET`/`UNSUPPORTED_PIXEL_ONLY`; NEVER treats stations/sheets/pixels as geospatial), a named blocker taxonomy (10 codes incl. `MISSING_MANIFEST_SLOT`/`UNTRUSTED_HANDOFF`/`MANIFEST_NOT_RESOLVABLE`/`UNSUPPORTED_PIXEL_ONLY`/`AMBIGUOUS_CRS`/`COORDINATE_UNCERTAINTY`/`SOURCE_CONFLICT`), a deterministic red-styled KML builder (text + traceability ExtendedData; KMZ = interface descriptor only, no binary), and `evaluate_export` — READ-ONLY over the job's trusted `redline_manifest` + `artifact_bundle` slots (resolves + sha256-verifies the durably-stored manifest), returns an export record (EXPORTABLE/BLOCKED). Persists nothing; never touches `export_package`; never reads `job["uploads"]`.
  - Tests: `test_kmz_export_geometry_safety_contract.py` (10); the generic no-specific-names guard extended to all 7 pipeline modules (+1 line). Verify: targeted 10 ✓; prior pipeline + published-bundle contracts + repo-wide guards ✓ (96 in one run); **full v2 suite 1550 passed / 4 skipped** (delta exactly +10 vs the committed 1540/4 baseline). NO artifacts committed (tmp_path; `data/`+`outputs/` gitignored); NO generated `.kmz`/`.kml`; NO deploy; NO mobile; NO engine/render/fixture/coordinate change; `origin/main` `068a279` untouched.

**KMZ SAFETY INVARIANTS:** current real v2 manifests have NO geospatial basis → classify `UNSUPPORTED_PIXEL_ONLY` → export BLOCKED with named reasons (never fake coords); uploaded GIS_ROUTE/KMZ/KML is NEVER treated as approved output (and `evaluate_export` never reads uploads); NO route-snap / nearest-line / station-guess / PDF-bounds / KMZ-bounds as truth; `evaluate_export` is read-only over the two trusted slots; `export_package` untouched; synthetic geospatial geometry exists ONLY in tests/future-path fixtures (proves the path for when the engine emits verified coords — the manifest schema is NOT modified here).

**PERMANENT SPINE now includes export safety:** `upload_pipeline → reviewed_bore_log → manifest_handoff → kmz_export safety evaluation`. Pipeline state: artifact serving DONE (served:true, continued-42) · upload/job foundation `2193a0e` · reviewed bore-log gate `6048ef1` · manifest handoff `2013879` · KMZ geometry-safety `2f70e22`; NO backend/web/UI/AI-OCR-provider/engine execution wired yet. RULE (memory `generic-naming-reusable-code`): reusable identifiers stay generic; real names only runtime data / historical audit docs.

**Next recommended lane (separately authorized; NOT started):** `closeout_review` ONE-status model (§5 — a single persisted `closeout_review.status` per job, server-authoritative + audited; all readiness UI renders it; no client flag overrides; a server-side gate checklist evaluated once + stored; LOCKED/APPROVED permission-gated; durable lock). Alternates: `billing_summary` server-computed (§6) or the `export_package` stored/versioned/reproducible packet (§8). Detail: [[current-sprint]] / [[log]] continued 45.

### Prior — continued 44 (2026-06-21): manifest_handoff engine-output attachment landed (validate→durably store→attach to job slots); NO render-truth change; frontier 50/58
**continued 44 — the THIRD permanent product-pipeline slice (engine-output handoff); NO engine/renderer/fixture/anchor/corpus/census/parent-model/placement/flag change; frontier UNCHANGED 50/58; render commit stays `c19b565`; engine HEAD `2013879`; v2 suite 1540 passed / 4 skipped.**
- **Manifest handoff LANDED (lane `TRUELINE_PRODUCT_MANIFEST_HANDOFF`, HEAD/origin `2013879`).** Commit `2013879` `contracts: add manifest handoff engine-output attachment` (3 files / +467; staged explicitly, NO `git add -A`; pushed, HEAD = origin = `2013879`, tree clean). One GENERIC, contract-only, pure-stdlib module + its test + the +1-line guard extension. NOT engine execution / render / export — the engine output bundle is a GIVEN input; ALL validation + durable storage REUSES existing machinery (no new validator):
  - `truelinev2/contracts/manifest_handoff.py` — records an engine-output handoff and, gated, validates + durably stores the engine output bundle and attaches content-addressed refs to the job's output slots. State machine `ATTEMPTED → SUCCEEDED | FAILED | REJECTED` (all terminal; re-finalize raises `HandoffStateError`). `record_handoff_attempt` (verifies job + reviewed_bore_log exist/in-scope; opaque `engine_run_status`; rejects duplicate `engine_run_id`). `finalize_handoff` = gate (`reviewed_bore_log.is_engine_ready`) → REJECTED on fail; else `store_bundle` into the job-scoped `bundle_store/` (validates via `admission_errors` + content-keys + copies) → FAILED on `BundleRejectedError`; else build `redline_manifest` + `artifact_bundle` attachments (bundle_id / manifest_sha256 / counts / `validation_status:"VALIDATED"`) + `set_output_slot` (reused as-is). Stored at `…/processing_jobs/<job>/handoffs/<engine_run_id>/_manifest_handoff.json`; durable bundle at `…/bundle_store/bundles/<bundle_id>/`.
  - Tests: `test_manifest_handoff_contract.py` (12); the generic no-specific-names guard extended to all 6 pipeline modules (+1 line). Verify: targeted 12 ✓; Slice 1 + reviewed-bore-log gate + published-bundle contracts + repo-wide guards ✓ (84 in one run); **full v2 suite 1540 passed / 4 skipped** (delta exactly +12 vs the committed 1528/4 baseline). NO artifacts committed (tmp_path; `data/`+`outputs/` gitignored); NO deploy; NO mobile; NO engine/render/fixture/coordinate change; `origin/main` `068a279` untouched.

**HANDOFF INVARIANTS:** reviewed_bore_log must be engine-ready before finalize; the engine output bundle must validate through the existing published-bundle machinery; the validated bundle is durably stored via `store_bundle`; output slots are attached ONLY after validation/storage succeeds; `REJECTED`/`FAILED` leave slots UNTOUCHED; success attaches ONLY `redline_manifest` + `artifact_bundle` (`export_package` untouched); terminal handoffs are immutable; the term "engine" = the TrueLine placement engine only (never AI/OCR/extraction). No engine execution / render / KMZ / backend / UI in this lane.

**PERMANENT CORE SPINE now exists:** `upload_pipeline → reviewed_bore_log → manifest_handoff → redline_manifest/artifact_bundle slots`. Pipeline state: artifact serving DONE (served:true, continued-42) · upload/job foundation `2193a0e` · reviewed bore-log gate `6048ef1` · manifest handoff `2013879`; NO backend/web/UI/AI-OCR-provider/engine execution wired yet. RULE (memory `generic-naming-reusable-code`): reusable identifiers stay generic; real names only runtime data / historical audit docs.

**Next recommended lane (separately authorized; NOT started):** `kmz_export` geometry-safety contract (approved-manifest geometry only, CRS header `EPSG:4326`/WGS84, per-coordinate `source`+`confidence`, abstain-not-fake, export is a checksummed `artifact_bundle` member; contract §7). Alternates: `closeout_review` ONE-status model (§5) or the `export_package` stored/versioned/reproducible packet (§8). Detail: [[current-sprint]] / [[log]] continued 44.

### Prior — continued 43 (2026-06-21): reviewed_bore_log engine-eligibility GATE landed (extracted_row + reviewed_bore_log); NO render-truth change; frontier 50/58
**continued 43 — the SECOND permanent product-pipeline slice (the EXTRACTING→PLACING review gate); NO engine/renderer/fixture/anchor/corpus/census/parent-model/placement/flag change; frontier UNCHANGED 50/58; render commit stays `c19b565`; engine HEAD `6048ef1`; v2 suite 1528 passed / 4 skipped.**
- **Reviewed bore-log gate LANDED (lane `TRUELINE_PRODUCT_REVIEWED_BORE_LOG_GATE`, HEAD/origin `6048ef1`).** Commit `6048ef1` `contracts: add reviewed bore-log engine-eligibility gate` (5 files / +783; staged explicitly, NO `git add -A`; pushed, HEAD = origin = `6048ef1`, tree clean). Two GENERIC, contract-only, pure-stdlib modules + the mandatory EXTRACTING→PLACING gate (contract §3):
  - `truelinev2/contracts/extracted_row.py` — the UNTRUSTED `extracted_row` + per-row review state (UNREVIEWED/CONFIRMED/CORRECTED/REJECTED/NEEDS_CLARIFICATION; CORRECTED needs corrected_values; REJECTED/NEEDS_CLARIFICATION need a reason; re-review allowed + audited). Row-level helpers are REVIEW-only (`row_review_passes`/`row_review_blocks_engine`) — a row ALONE is never engine-eligible. Generic extraction metadata: `extraction_method` ∈ {OCR, TEXT_PARSE, TABLE_IMPORT, MANUAL_ENTRY} + opaque `extractor_name` (no `engine` field; "engine" = the placement engine).
  - `truelinev2/contracts/reviewed_bore_log.py` — the aggregate gate attached to a `processing_job` + a BORE_LOG upload: extracted_rows + `segment_group`s (relation SEPARATE_BORE/SAME_RUN_SEGMENTS/AMBIGUOUS; grouping_status PENDING/CONFIRMED/SOURCE_CONFLICT), durable JSON under the job scope, aggregate + per-row + per-group audit, a pure `review_queue` view, and the DERIVED eligibility gate. `row_engine_eligible(rbl, row_id)` = review passed AND the row resolves into EXACTLY ONE confirmed, non-ambiguous, non-conflicting group; `is_engine_ready(rbl)` = ≥1 row AND every non-rejected row eligible (empty → never ready).
  - Tests: `test_extracted_row_review_contract.py` (10) + `test_reviewed_bore_log_gate_contract.py` (13); the generic no-specific-names guard extended to all 5 pipeline modules (+2 lines). Verify: targeted 23 ✓; Slice 1 + repo-wide guards ✓; **full v2 suite 1528 passed / 4 skipped** (delta exactly +23 vs the committed 1505/4 baseline). NO artifacts committed (tmp_path; `data/`+`outputs/` gitignored); NO deploy; NO mobile; NO engine/render/fixture/coordinate change; `origin/main` `068a279` untouched.

**SAFETY INVARIANTS (the gate's contract):** raw AI/OCR/table/manual rows are UNTRUSTED; no raw row is engine-eligible by default; row review alone is NOT enough (grouping required); grouping must be RESOLVED before eligibility; eligibility is DERIVED ONLY (never stored as mutable truth — no `engine_eligible`/`engine_ready` in persisted JSON); rejected / ambiguous / source-conflict / unreviewed / ungrouped / multi-group-drift rows all block placement; extraction metadata uses generic extractor fields (never placement-engine terminology).

**Pipeline state:** artifact serving DONE (served:true, continued-42) · upload/job foundation `2193a0e` · reviewed bore-log gate `6048ef1`; NO backend/web/UI/AI-OCR-provider/engine execution wired yet. RULE (memory `generic-naming-reusable-code`): reusable identifiers stay generic; real names only runtime data / historical audit docs.

**Next recommended lane (separately authorized; NOT started):** plan the next permanent product slice — candidate `manifest_handoff` (the v2 engine `redline_manifest` → durable, checksummed `artifact_bundle` handoff producer; downstream read-only, resolve by path+sha256, never infer status from filenames; contract §4), or alternate `kmz_export` geometry-safety contract (approved-manifest geometry only, CRS header, per-coordinate source+confidence, abstain-not-fake; contract §7). Detail: [[current-sprint]] / [[log]] continued 43.

### Prior — continued 42 (2026-06-20): Fable artifact serving ACTIVATED (served:true) + Product pipeline Slice 1 LANDED (customer_project + processing_job + upload_pipeline contract); NO render-truth change; frontier 50/58
**continued 42 — owner ACTIVATED Fable artifact serving (served:true) + the FIRST permanent product-pipeline implementation slice; NO engine/renderer/fixture/anchor/corpus/census/parent-model/placement/flag change; frontier UNCHANGED 50/58; render commit stays `c19b565`; engine HEAD `2193a0e`; v2 suite 1505 passed / 4 skipped.** Two threads:
- **Artifact serving ACTIVATED (Fable web `main` `16c7095`).** The continued-41 artifact-hosting CODE is now LIVE-ACTIVE: owner uploaded the 48 MB GitHub Release asset + set Vercel `TL2_REDLINE_BUNDLE_URL` (present, len=169) + `NEXT_PUBLIC_TL2_REDLINE_MANIFEST_SERVED=1` + redeployed WITHOUT build cache. Verified build log: `served=true`; `archive 50268315 bytes; validating entries`; `OK: 83/83 FINAL_REDLINE_PNG verified -> public/redline-bundle/.../artifacts/...`. Verified live `/redlines`: `Served · lazy`, `83 FINAL_REDLINE_PNG · served: true`, bundle served from the durable artifact path. **The `…_ARTIFACT_HOSTING_VERIFY` gate is CLOSED (served:true).** (The continued-40/41 START_HERE/hot `served:false` was the pre-activation snapshot — now superseded.)
- **Product pipeline Slice 1 LANDED (engine repo `feat/truelinev2`, HEAD/origin synced `2193a0e`).** Lane `TRUELINE_PRODUCT_UPLOAD_PIPELINE_PROCESSING_JOB` — the FIRST permanent v2 product-foundation implementation. Commit `2193a0e` `contracts: add product upload pipeline job foundation` (7 files / +787; staged explicitly, NO `git add -A`; pushed, HEAD = origin = `2193a0e`, tree clean). Three GENERIC, contract-only, filesystem-shaped + adapter-neutral modules (pure stdlib; no engine/render/web/backend/AI-OCR/KMZ):
  - `truelinev2/contracts/customer_project.py` — the ISOLATION ROOT: safe-id validation, `customer_projects/<id>/` path-scoping + realpath containment guard, `assert_same_project`/`CrossProjectAccessError` (in-process 403 analog); `display_name` is opaque runtime data.
  - `truelinev2/contracts/processing_job.py` — durable JSON job record + the contract state machine (`CREATED→UPLOADING→EXTRACTING→AWAITING_REVIEW→PLACING→PLACED→CLOSEOUT_REVIEW→CLOSED`; any non-terminal→`FAILED`, reason-required); server-authoritative AUDITED transitions (from/to/at/by/reason); ONE authoritative status; durable across reload; 3 typed OUTPUT SLOTS (redline_manifest/artifact_bundle/export_package) — interface only, producers are later lanes.
  - `truelinev2/contracts/upload_pipeline.py` — accepted-kind inventory (PLAN_PDF/BORE_LOG/GIS_ROUTE + ext allowlist), `accept_upload` (kind/size validation, scoped storage, sha256, content-idempotent, intake closed after EXTRACTING). **NO extraction runs — every upload is `extraction_status:"queued"`** (AI/OCR untrusted, gated to a later lane).
  - Four targeted tests (`truelinev2/tests/`): `test_customer_project_isolation_contract.py`, `test_processing_job_lifecycle_contract.py`, `test_upload_pipeline_contract.py`, `test_no_specific_names_in_pipeline_contract.py` (NAME-FREE naming guard = operator `NAME_TOKENS` env denylist + AST identity-no-default structural invariant; proven via a runtime real-token run + a `queued` negative control + whole-word grep).
  - Verification: targeted 26 passed; repo-wide guards + bundle contracts 35 passed; **full v2 suite 1505 passed / 4 skipped** (proven delta = exactly +26 vs 1479/4 without the new files; the long-carried "1392/2-skip" was stale doc drift). NO artifacts committed (tmp_path; `data/`+`outputs/` gitignored); NO deploy; NO mobile; NO engine/render/fixture/coordinate change; `origin/main` `068a279` untouched.

**NAMING/PRODUCT RULE (hard, now memory-pinned `generic-naming-reusable-code`):** reusable code/routes/env/schema/test/component/docs-heading names must stay GENERIC — no customer/person/project/location/demo names in reusable infrastructure; real names live ONLY as runtime data or historical audit docs. Name-free naming guards (`NAME_TOKENS` env + AST identity-no-default).

**Next recommended lane (separately authorized; NOT started): `reviewed_bore_log` / extraction-review gate** — uploaded or AI/OCR-extracted bore-log rows stay UNTRUSTED until reviewed/confirmed; support multi-segment + unrelated-bore grouping BEFORE engine placement (contract §3, the mandatory `EXTRACTING → PLACING` gate that consumes only `review.status == approved` segments). Detail: [[current-sprint]] / [[log]] continued 42.

### Prior — continued 41 (2026-06-20): Fable staging LIVE as a read-only v2 proof-viewer; artifact-hosting built (owner activation pending); v1 salvage audit + v2 pipeline contract; NO render-truth change; frontier 50/58
**continued 41 — docs/audit (engine repo) + Fable-web product work (SEPARATE repo); NO engine/renderer/fixture/anchor/corpus/census/parent-model/placement/flag change; frontier UNCHANGED 50/58; render commit stays `c19b565`; engine HEAD `a4bf2a5`; v2 suite 1392/2-skip.** Three threads:
- **Artifact hosting (Fable `main` 51dcbf7→`16c7095`; engine docs `09fc469`/`e886de2`/`2a559bd`).** Built `scripts/fetch-redline-bundle.mjs` (Fable `3ab0c80`): downloads the 48 MB bundle from `TL2_REDLINE_BUNDLE_URL`, extracts to gitignored `public/redline-bundle/<id>/`, **sha256-verifies all 83 PNGs** vs the committed manifest; NO PNGs in git; archive sha256 `864c657c…`. Env-debug (`16c7095`): build = **`node scripts/fetch-redline-bundle.mjs && next build`** (prebuild lifecycle removed — wasn't firing on Vercel) + an always-on no-secret `env:` diagnostic. Locally proven (tsc/contracts/build PASS, served build 83/83, tamper fails). **No env-var mismatch** (fetch + UI both `NEXT_PUBLIC_TL2_REDLINE_MANIFEST_SERVED==='1'`).
- **Staging honesty (Fable `85682bb`→`f753b1a`; engine docs `b9fd9cf`/`377536d`/`5211102`).** URL recorded (`https://trueline-web-experience.vercel.app/`, project `trueline-web-experience`). Cedar Ridge→**`Brenham PH5 — v2 staging`**; then **mock-portfolio shell → real read-only v2 proof-viewer**: dashboard = single Brenham summary from the REAL manifest (58/50/1/7, 83 artifacts, bundle `brenham-c19b565-ddfffff7cbe7`, render `c19b565`); global banner `Read-only v2 staging · no upload/live render yet`; `/redlines` leads with the real `RedlineManifestPanel`, mock review queue collapsed+labeled `Mock UI demo queue — not engine data`.
- **v1 salvage audit (engine `a4bf2a5`, `docs/`).** `product_v1_workflow_salvage_audit.md` (7-capability read-only audit + salvage-class table + DO-NOT-COPY list) + `product_v2_permanent_pipeline_contract.md` (generic pipeline: upload → reviewed bore-log → engine placement → redline_manifest/artifact_bundle → closeout_review → billing_summary → kmz/kml export → export_package) + `probe_v1_inventory.sh` (read-only). Doctrine: engine owns placement truth; geometry from a reviewed manifest/approved override only; NO fake KMZ when coords unavailable; OCR untrusted until reviewed; multi-bore grouping before placement; reproducible exports; ONE status model; `customer_project` isolation. Generic names only (contract+probe = 0 customer tokens). Audited read-only via 3 parallel Explore agents — NO v1 behavior change.

**VERIFY status:** staging is LIVE + honest (Brenham labels, 50/58 panel correct) but **`served:false`** — artifact activation is pending the OWNER step (upload the Release asset → set Vercel `TL2_REDLINE_BUNDLE_URL` + `NEXT_PUBLIC_TL2_REDLINE_MANIFEST_SERVED=1` → **redeploy WITHOUT build cache**). `origin/main` `068a279` + `osp-redlining` + mobile (`c61b2c3`) untouched; agent ran no `vercel`/deploy. **Next: owner activates → re-run `…_ARTIFACT_HOSTING_VERIFY` for `served:true`; then (separately authorized) a v2-pipeline implementation lane (strongest first = `upload_pipeline` + `processing_job` isolation, or the `kmz_export` geometry-safety contract).** Detail: [[current-sprint]] / [[log]] continued 41.

### Prior — continued 40 (2026-06-19): Fable Vercel staging STANDUP succeeded (manifest/status-only on `main @ 51dcbf7`); NO render-truth change; frontier 50/58
**continued 40 — docs only (records a successful owner-run Vercel standup); NO engine/renderer/fixture/anchor/corpus/census/parent-model/placement/flag change; frontier UNCHANGED 50/58; render commit stays `c19b565`; engine work HEAD `a4b8590` (this docs save sits one commit above it).**
- **Fable Vercel staging STANDUP SUCCEEDED (owner-run; agent ran no `vercel`/deploy).** Fable web loads on Vercel from `patrickverardi45/trueline-web-experience`, branch **`main`**, commit **`51dcbf7`**; `/redlines` renders with the Fable UI intact + the **v2 redline manifest (durable bundle)** panel: **50/58**, bundle **`brenham-c19b565-ddfffff7cbe7`**, render/source **`c19b565`**, **83 FINAL_REDLINE_PNG**, **`served: false`** (manifest/status-only — PNG serving off + PNGs gitignored/local-only). NO live render, NO upload flow, NO client data, NO production swap; `osp-redlining` project/domain + Render/domain/env untouched.
- **Result recorded (`a4b8590`, docs-only path-scoped, pushed).** `wiki/trueline_v2_fable_vercel_staging_plan.md` gained a "Standup result — DONE" section (every observed value VERIFIED read-only against the committed fixtures `redline_manifest.v1.json` + `redline_store_index.v1.json` that a `main @ 51dcbf7` build serves) + a "Next unresolved work" list.
- **Staging URL: `https://trueline-web-experience.vercel.app/` · Vercel project: `trueline-web-experience`** (owner-provided 2026-06-19; the actual project reuses the repo name rather than the earlier-recommended slug `trueline-web-staging`).
- **Fable web repo state:** default branch **`main @ 51dcbf7`**; feature branch `feat/2k-static-bundle-adapter @ 51dcbf7` PRESERVED; tag `fable-v2-ui-bones-2026-06-19 → 7e3b392` intact.

Frontier UNCHANGED **50/58**; render commit `c19b565`; v2 suite **1392 passed / 2 skipped**. **Next lane: `TRUELINE_V2_FABLE_VERCEL_STAGING_ARTIFACT_HOSTING` (planning-first)** — host the redline PNGs WITHOUT committing the ~50 MB pile to GitHub (object/static storage, a Vercel prebuild fetch/copy, or backend static serving later), then flip `NEXT_PUBLIC_TL2_REDLINE_MANIFEST_SERVED=1` so strokes render. No production/domain change. Detail: [[current-sprint]] / [[log]] continued 40.

### Prior — continued 39 (2026-06-19): P4 staging-plan persisted + Fable branch hygiene (clean `main` is the GitHub default); NO render-truth change; frontier 50/58
**continued 39 — docs + git-hygiene only; NO engine/renderer/fixture/anchor/corpus/census/parent-model/placement/flag change; frontier UNCHANGED 50/58; render commit stays `c19b565`; engine work HEAD `16295d4` (this docs save sits one commit above it).** Two safe prep lanes after the continued-38 Fable remote-init:
- **P4 staging plan PERSISTED (`16295d4`, path-scoped, pushed → `origin/feat/truelinev2`).** `wiki/trueline_v2_fable_vercel_staging_plan.md`: recommended Vercel slug `trueline-web-staging`, repo `github.com/patrickverardi45/trueline-web-experience`, branch strategy (+ clean `main`), Next.js/npm/`next build` + default Vercel Next output + Node 20.x/22.x, env (`NEXT_PUBLIC_TL2_REDLINE_MANIFEST=1`, `…_SERVED` OFF), manifest/status-only artifact plan (no 50 MB PNGs; object-store + prebuild later), first staging objective (read-only shell, `/redlines` 50/58 manifest, no render/upload/data/domain-swap), risks, and the future execution checklist. **PLANNING ONLY — nothing on Vercel.**
- **Fable web branch hygiene DONE (separate `trueline-web-experience` repo).** Clean **`main`** created from `51dcbf7` and pushed (`* [new branch] main -> main`, upstream tracking); the **GitHub default branch is now `main`** (owner flipped it in the UI; verified live `ls-remote --symref` → `refs/heads/main`). `feat/2k-static-bundle-adapter` PRESERVED @ `51dcbf7` (not deleted / not force-pushed); tag `fable-v2-ui-bones-2026-06-19 → 7e3b392` intact; no old branches (`master`, `codex/*`) pushed; no code change. **`.vercel/` absent — not linked; no deploy/Vercel/domain/env change; `osp-redlining` / Render / `origin/main` `068a279` untouched.**

Frontier UNCHANGED **50/58**; render commit `c19b565`; v2 suite **1392 passed / 2 skipped**. **Next lane: `TRUELINE_V2_FABLE_VERCEL_STAGING_STANDUP`** — execute the staging-plan checklist (Vercel project creation is an owner dashboard action; the agent does not run `vercel`); point it at `main`. Detail: [[current-sprint]] / [[log]] continued 39.

### Prior — continued 38 (2026-06-19): bootstrap drift fixed → HEAD `e35cd26`; Phase 2J static bundle consumer + Fable UI preserve/retire + repo-architecture plan + Fable remote-init P1 DONE; NO render-truth change; frontier 50/58
**continued 38 — bootstrap re-canonicalized + website-READ-side / UI-base / architecture arc; NO engine/renderer/fixture/anchor/corpus/census/parent-model/placement/flag change; frontier UNCHANGED 50/58; render commit stays `c19b565`; HEAD `e35cd26`.** The continued-37 save left START_HERE + `hot.md` pinned at `81f3cd3` while four real commits landed after it; this save bumps the snapshot to git truth (`feat/truelinev2 @ e35cd26`, pushed; `origin/main` `068a279` untouched; clean tree) and records the arc. Lineage on the continued-37 save `0c0ff20`:
- **`841960f` — Phase 2J: read-only static bundle CONSUMER (website READ side).** `truelinev2/contracts/published_bundle_consumer.py` + proof `run_redline_manifest_static_consumer_proof.py` + contract test (+620 LOC). Consumes the durable store's `latest_valid` bundle as a pure static read (checksum + in-root path-safety verified); NO live render, NO backend, NO write path.
- **`0fd3228` — Fable UI preserve / contract mock-UI retire.** The Fable v2 repos (`trueline-web-experience` web, `trueline-field-mobile` mobile) are the AUTHORITATIVE v2 UI/design/function base; the temporary `truelinev2/contracts/mock_ui/` is SUPERSEDED → historical contract fixture only (`_DEPRECATED.md`; its fidelity test still guards manifest↔fixture). Future web integration ADAPTS Fable to the durable manifest contract — never rebuilds a new UI. Canonical: `wiki/ui/fable_v2_ui_bones.md`.
- **`eecf2ef` — legacy-extraction & repo-architecture plan (canonical).** `wiki/trueline_v2_legacy_extraction_and_repo_architecture_plan.md`: v1 = legacy prototype / reference spec / algorithm parts-bin (NOT sacred); v2 product = v2 engine (`truelinev2/`) + `redline_manifest` durable-bundle contract + Fable UI; PDF-first before KMZ; v1 auth REFERENCE-ONLY (external provider replaces it — only the tenant-isolation requirement survives); P0–P8 migration phases; the one hard caution = `truelinev2/` lives INSIDE `TrueLine_Beta` (`osp-redlining`), never wipe / `git add -A` until the intentional P7 split.
- **`e35cd26` — Fable remote-init P1 DONE (save).** `TRUELINE_V2_FABLE_REMOTE_INIT` complete: Fable web repo `origin = https://github.com/patrickverardi45/trueline-web-experience`; pushed branch `feat/2k-static-bundle-adapter @ 51dcbf7` (tracking) + tag `fable-v2-ui-bones-2026-06-19 → 7e3b392`; old local branches (`master`, `codex/*`) intentionally NOT pushed. Phase 2K (static-bundle adapter on `/redlines`, default-OFF gate `NEXT_PUBLIC_TL2_REDLINE_MANIFEST`) visually ACCEPTED + git-bundle backed up. **No deploy, no Vercel, no domain change; `osp-redlining` / Render / `origin/main` untouched.**

Frontier UNCHANGED **50/58** (log14 COVERED by log10; 7 owner/source-gated: log5/31/38/43 owner-locked abstain, log15/16 source-gap, log57 `.FS`); render commit `c19b565`; v2 suite **1392 passed / 2 skipped**. **Next lane: `TRUELINE_V2_FABLE_VERCEL_STAGING_PLAN` (P4) — PLANNING ONLY** (a NEW Fable Vercel/staging project on a fresh slug, mock/read-only; NOT a production swap, no domain move). Detail: [[current-sprint]] / [[log]] continued 38.

### Prior — continued 37 (2026-06-19): redline-manifest engine→website CONTRACT pipeline COMPLETE (Phases 2A–2I); NO render-truth change; frontier 50/58
**continued 37 — 12-commit proof/CONTRACT arc; NO engine/renderer/fixture/anchor/corpus/census/parent-model/flag change;
frontier UNCHANGED 50/58; render commit stays `c19b565`; HEAD `81f3cd3`.** Built + proved the entire engine→website
redline-manifest pipeline, all generated artifacts GITIGNORED under `data/outputs/` (NONE committed): schema-pinned
`truelinev2/contracts/redline_manifest.schema.json` + a 50/58 example (2A `a0a490f`) → static manifest-driven mock UI
(`505a9a2`) → artifact **publisher** (real sha256/bytes, `mock_example:false`; `bccfdc8`) → existing-artifact inspection
(2A.5 `4c11722`) → **2B STOP** (`f7a616b`: a unified all-50 render is impossible without a solver change — the callout
sweep hardcodes the ALREADY_DRAWN skip; refused partial-37-as-50) → **2C** canonical render registry re-renders the 13
ALREADY_DRAWN through their existing lanes (`c0498d4`; resolves 2B WITHOUT a solver change; 13/13, log50 incl, log7 PARTIAL)
→ **2D** first REAL all-50 manifest (`06c734a`; 83 artifacts/50.5 MB, 58/50/1/7) → **2E** published-bundle contract
(`f7988ab`; static-serving safe, checksum-verified, bundle index) → **2F** one-command pipeline runner (`cbeb9be`; + fixed
a latent zero-bucket reconciliation false-rejection) → **2G/2H** render benchmarks (`aaa8952`/`9ed6c98`: 13=52.2 s,
37=299.6 s; full refresh ~5.9 min, render-bound) → **2I** adapter-neutral durable bundle store (`81f3cd3`; immutable
content-keyed `bundles/<id>/` + `store_index.json` `latest_valid` + retention + `WEBSITE_READ_CONTRACT`; real bundle stored
`brenham-c19b565-ddfffff7cbe7`, store VALID). ~63 targeted contract tests (61 pass + 2 jsonschema-optional skips).
`B-DATA-LOG48-ADJ-1` unchanged. The full local contract+storage chain is complete + benchmarked; the next step crosses into
website/backend wiring (gated). Detail: [[current-sprint]] / [[log]] continued 37.

### Prior — continued 36 (2026-06-19): repo-hygiene arc COMPLETE (101→0 untracked); NO render; frontier 50/58
**continued 36 — pure repo-hygiene + provenance; NO engine/render/census change; frontier UNCHANGED 50/58; render commit
stays `c19b565`; HEAD `e3df509`.** The continued-35 inventory found 101 untracked files; this arc drove it to **0** without
losing anything. Feat lineage (on the continued-35 save `69dd876`): **`f5dbed1`** committed the evidence trail (7 `gac/*.md`
source-adjudication packets + `run_review_candidate_reasoning_sweep.py`); **`c0e6680`** committed 4 Group-A evidence slices
(KMZ↔PDF georeference ×2, the ambiguity-resolution render primitive, the `gac/log44`-cited owner-source packet); **`e3df509`**
relocated the token-reduction doctrine to `wiki/doctrine/`. A pushed **ARCHIVE** branch+tag `archive-v2-continued-35-superseded-scratch`
= **`d8508b9`** preserves the superseded `backend/tl_core/**` (35) + 14 ambiguous proof slices, which were then removed from the
working tree (step 4C); 26 scratch probes + `probe_err.txt` were deleted (step 5); the old-app `RECOVERED_BASELINE_98d108a.md`
note was deleted (owner decision; recoverable via tag `recovered-pdf-first-overlay-98d108a` + branch `backup-live-lp-chain-6eaade3`).
**`backend/tl_core` is now ARCHIVE-ONLY** (a superseded reuse-by-import wrapper, never imported by v2); the `git add -A` landmine is
DEFUSED; **repo hygiene is COMPLETE (untracked = 0)**. NO code/renderer/fixture/census/flag change. Detail: [[current-sprint]] / [[log]] continued 36.

### Prior — continued 35 (2026-06-19): accountability ledger + website-readiness audit + repo-hygiene (NO render; frontier 50/58)
**continued 35 — docs + repo-hygiene checkpoint; NO engine/render/census change; frontier UNCHANGED 50/58; render commit
stays `c19b565`.** Four commits on `feat/truelinev2` (HEAD **`8ea66bc`**): **`b083b76`** added
`wiki/trueline_v2_50_of_58_accountability_table.md` — the 58-log ledger (**50 DRAWN / 1 COVERED log14←log10 / 4
OWNER_LOCKED_ABSTAIN log5·31·38·43 / 2 SOURCE_GAP log15·16 / 1 MISSING_SOURCE_SHEET log57**; drawn set = sweep
`ALREADY_DRAWN`∪`NEW_TARGETS`; `placement_status` proven STALE → never the drawn census). **`15e00f7`** added
`wiki/trueline_v2_engine_website_readiness_audit.md`: the engine is **accountability-complete but NOT 58/58
drawn-complete and NOT website-ready** — the gap is a CONTRACT boundary (no machine-readable `redline_manifest.json`;
no clean parameterized runner — proof-script-driven + Brenham-hardcoded, seam exemplar-only log53/64/71, API default-OFF
review-card transport; artifacts gitignored/on-demand; runtime unbenchmarked; stale `placement_status`; proof≠final),
with 5 status + 6 provenance enums (**log3 preserved OWNER_CONFIRMED_HUMAN_ADJUSTABLE, not AUTO**) + the two-truth-axes
warning. **`6f2e4a5`** (repo-hygiene fix 1) tracked the load-bearing
`truelinev2/proof/run_station_corridor_route_solver_slice.py` (imported by TRACKED `run_log15_log16_run_group_review_slice.py:37`
+ `test_log15_log16_run_group_review.py:79` → clone/CI fix; targeted test 8 passed). **`8ea66bc`** (repo-hygiene fix 2)
added `.gitignore` rules `.agents/` + `skills-lock.json` (untracked 100→86). NO code/renderer/fixture/census/flag change.
Safe website work NOW = contract-first mock UI vs the manifest schema; no live wiring. Detail: [[current-sprint]] /
[[log]] continued 35.

### Prior — continued 34 (2026-06-19): log3 WIRED + DRAWN (49→50)
**continued 34 — log3 owner-confirmed / HUMAN-ADJUSTABLE GEOMETRY render.** Frontier **49 → 50/58** (log3 = 50th
drawn). Lineage `069e70d` (continued-33 save) → **`683825c`** (log3 owner-control ingest PROOF, 16/16, read-only)
→ **`c19b565`** (log3 sweep WIRING, DRAWN). The s3 `12+66→15+13` conduit is too FRAGMENTED to auto-trace
(`DESIGN_PATH_NOT_CONNECTED`); the owner confirmed the route + dotted the TOP path → 11 owner control points
DIFF-ingested → the s3 leg is the STRAIGHT segment between two source-bound endpoints (matchline crossing @ owner
top-y 296.5 → `15+13 NEXTLINK HH`), control-point-verified (maxdev 1.3pt), closing 247.7'. Renders 2 red strokes
(s2 `12+63 FLOWER POT` stub 2.8' + s3 247') via gated opt-ins `printed_run_callout_chain_route` +
`owner_confirmed_geometry`; new content = upstream **250'**, downstream `15+13→21+63` (650') COVERED by drawn log4
(gated `covered_by_drawn_children` parent-gate exception), 0 overlap. **FIRST owner-GEOMETRY render** — Patrick
classified it the **HUMAN-ADJUSTABLE lane** (NOT deterministic AUTO), reconciling with "never invented
coordinates / manual placement is not the [AUTO] product". All **64 prior PNGs BYTE-IDENTICAL** (md5 stash-baseline
diff); census FROZEN (`doc`); `parent_source_model`/fixtures UNTOUCHED; v2 1392/2-skip; e2e PASS. Doctrine:
fragmented conduit + parallel tracks → owner picks the track + confirms straightness → straight segment between
BOUND endpoints (minimal, not freehand); DIFF-vs-baseline ingests owner packets (only explicit marks). Detail:
[[current-sprint]] / [[log]] continued 34.

### Prior — continued 33 (2026-06-18, READ-ONLY adjudication; no render)
**continued 33 — log3/log14 owner-adjudication (READ-ONLY).** No render; frontier UNCHANGED **49/58**. **log14 =
confirmed DUPLICATE of drawn log10** — its only bindable s7 route is log10's first leg (`0+58=0+00 / 0+00→4+16`);
end `4+18` unprintable; `solve_log` BLOCKED → covered_by_existing_redline, NOT a missing redline (effective
denominator ~57). **log3 = RECLASSIFIED distinct longer bore** (not a duplicate): `12+63` is printed on s2 as a
DRIVEWAY boundary (non-structure → unbindable start); `12+66` is the s2/s3 matchline; log3 shares log4's
`15+13→21+63` downstream half; nearest real origin = the 9+75 AP-106 8-port HH (288' upstream/outside span) →
moved from "owner-adjudication" to "owner span-correction + N-leg solver" blocker. Evidence packet
`gac/log3_log14_owner_adjudication.md` (committed). NO engine/render/census/fixture mutation. Doctrine: a corpus
"start" can be a driveway/matchline cut — trace the continuous-frame chain across matchlines before ruling
duplicate/dead-end. Detail: [[current-sprint]] / [[log]] continued 33.

### Prior — continued 32 (2026-06-18): log44 render (48→49)
ONE render this arc — frontier **48 → 49/58** (one actual drawn red stroke). Lineage `62ee0da` → `44597ff`
(continued-31 save) → **`7039c48`** (pushed → `origin/feat/truelinev2` = `7039c48`). Census FROZEN; both new
primitives are GATED per-log opt-ins → all **62 prior render PNGs BYTE-IDENTICAL** (md5-verified); global
`BASE_CONDUIT` / `MAX_DASH_GAP` / `parent_source_model.json` untouched. Only two files changed:
`truelinev2/proof/run_callout_route_assembly_sweep.py` + its test.
- **`7039c48` — log44 (48→49), owner-corrected Woodson run + footage-tick evidence.** bore_log17 Segment B.
  Owner SOURCE-VERIFIED the corpus "print 18" as a sheet mis-map onto the real **WOODSON LN drop on sheets
  10+13**. Cross-sheet 2-leg (the log70 shape): **STA 43+36 INSTALLER HH** (s10, = local 0+00) → down Woodson
  167' → **MATCHLINE 1+67/1+66 SEE SHEET 13** → past **AP-158 TERMINAL 8 PORT HH (STA 2+45, INTERMEDIATE)** →
  **STA 3+23 FLOWER POT** (s13); drawn 318.2' closes 323' (corpus 325'). Binds on `endpoint_anchors` alone; the
  bundled 1+67/1+66 matchline is unique by chain-reach (the parallel 1+66 RIGHT sibling excluded). TWO new
  GATED opt-ins: (1) `owner_corrected_parent_sheet_context` flips the parent gate's stale corpus sheet
  [18]→[10,13] ONLY after span-closure + anti-sibling-mixup already pass (fixture untouched); (2)
  `footage_tick_ladder_route_evidence` — NEW reusable primitive: the printed **2'/5'/7' footage-tick LADDERS**
  corroborate each leg's direction + length (abstains if a leg lacks one; NEVER sets endpoints; band 22pt <
  half the ~50' ROW spacing → belongs to THIS bore, not a parallel sibling). Overlap clean: only the shared
  3+23 FLOWER POT junction with the consecutive log47 (0' coincident; distinct parents).
- Prior arc (continued 31, `a8b2d31`/`f75c5c6`/`62ee0da`): log30 (Ledbetter parallel), log4 (FIRST fiber-MAIN),
  log42 (owner-corrected AP-105 terminal). Detail: [[current-sprint]] / [[log]] continued 31.
- Invariants this commit: census FROZEN (flag-OFF 31/6/1/17/3, flag-ON 22/1/4); `TRUELINE_MANUAL_ADJUDICATIONS`
  default-OFF; no corpus/`parent_source_model`/fixture mutation; NO census rebaseline; NO new production flag; red strokes.

## Current redline frontier
**50/58 drawn** (+log3 this arc). **log3 RESOLVED — WIRED + DRAWN** (continued-34, `c19b565`): owner-confirmed /
HUMAN-ADJUSTABLE GEOMETRY render — s2 `12+63 FLOWER POT` stub (2.8') + s3 247' STRAIGHT top-path between two bound
endpoints (matchline crossing @ owner top-y → `15+13 NEXTLINK HH`, 11-control-point-verified); downstream
`15+13→21+63` (650') covered by drawn log4. **log14** remains a confirmed DUPLICATE of drawn log10
(covered_by_existing_redline — the 8th non-drawn, NOT a missing redline). Remaining genuinely-open **7**:
log5, log15, log16, log31, log38, log43, log57 — all owner/source-gated:
- **Owner-locked ABSTAIN:** log5, log31, log38, log43 (`must_remain_abstained`).
- **Source-gap:** log15/log16 (unprinted ruler-cuts → sheet-5+ head-end), log57 (`.FS` drive sheet, absent).
- (RESOLVED continued 34: log3 WIRED + DRAWN — owner-confirmed/human-adjustable GEOMETRY, the FIRST owner-geometry
  render; gated per-log opt-ins, 64 prior PNGs byte-identical, census frozen, fixtures untouched. `c19b565`.)
- (RESOLVED continued 33: log14 = confirmed DUPLICATE of drawn log10; log3 reclassified (then wired in 34) —
  packet `gac/log3_log14_owner_adjudication.md`.)
- (RESOLVED continued 32: log44 rendered `7039c48` — owner source-verified the corpus print-18 mis-map onto the
  Woodson s10+13 run; AP-158/2+45 intermediate, STA 3+23 FLOWER POT end. The source-location conflict is closed.)

## Current next gates (each separately authorized; NONE started)
1. **`closeout_review` ONE-status model ← recommended next (separately authorized; NOT started).**
   A single persisted `closeout_review.status` per job (`OPEN → READY_FOR_REVIEW → BLOCKED → LOCKED → APPROVED`,
   server-authoritative + audited); ALL readiness UI renders THIS value — no panel-local readiness, no client flag may
   override it (v1's core defect: 3 disagreeing readiness signals). A server-side gate checklist (design loaded, reviewed
   bore logs approved, manifest present, evidence attached, …) evaluated once + stored, not recomputed per render; LOCKED/
   APPROVED are permission-gated audited transitions; lock state durable (survives restart). Contract §5. Alternates:
   `billing_summary` server-computed (§6) or the `export_package` stored/versioned/reproducible packet (§8). Builds on the
   continued-42→45 spine (HEAD `2f70e22`). Contract-first; generic names; no backend/UI/deploy.
   - **`TRUELINE_PRODUCT_KMZ_EXPORT_GEOMETRY_SAFETY` — ✅ DONE (continued-45, `2f70e22`).** `kmz_export`: pixel-only manifests
     BLOCKED with named reasons (never fake coords); read-only over trusted slots; `export_package` untouched; +10 tests. See Latest above.
   - **`TRUELINE_PRODUCT_MANIFEST_HANDOFF` — ✅ DONE (continued-44, `2013879`).** gated validate→durably store→attach slots; +12 tests.
   - **`TRUELINE_PRODUCT_REVIEWED_BORE_LOG_GATE` — ✅ DONE (continued-43, `6048ef1`).** extracted_row + reviewed_bore_log; +23 tests.
   - **`TRUELINE_PRODUCT_UPLOAD_PIPELINE_PROCESSING_JOB` — ✅ Slice 1 DONE (continued-42, `2193a0e`).**
   - **`TRUELINE_V2_FABLE_STAGING_ARTIFACT_HOSTING_VERIFY` — ✅ DONE (continued-42, `served:true`).** Fable web `main` `16c7095`.
   Later (each separately gated): billing / `export_package` → P5 v2 backend/API with EXTERNAL auth → P6 parity → P7 engine split → P8 retire v1.
2. **`TRUELINE_V2_REDLINEMANIFEST_SCHEMA_AND_RUNNER_CONTRACT`** — ✅ DONE (continued-37, Phases 2A–2I, `a0a490f`→`81f3cd3`):
   schema + 50/58 example + mock UI + publisher + unified render registry + real all-50 manifest + published-bundle contract +
   one-command pipeline runner + render-cost benchmark (full refresh ~5.9 min, render-bound) + adapter-neutral durable bundle
   store. All generated artifacts gitignored under `data/outputs/`; ~63 contract tests. Optional follow-on: a warm-engine /
   single-process unified runner to cut the ~6 min refresh.
3. **Repo hygiene** — ✅ COMPLETE (continued-36): untracked 101→0; evidence trail + Group-A committed (`f5dbed1`/`c0e6680`),
   superseded set archived at `d8508b9`, doctrine relocated (`e3df509`). The `git add -A` landmine is defused.
4. **Accountability table** — ✅ DONE (continued-35, `b083b76`); website-readiness audited (`15e00f7`).
5. **Owner-locked abstains** log5/31/38/43 + **source-gap** log15/16 + log57 — unchanged (owner/source input needed).

## Current known blockers (each a NAMED missing piece, NOT a generic solver limitation)
- **log14** — RESOLVED continued-33: its only bindable s7 route IS drawn log10's first leg (reset `0+58=0+00`,
  run `0+00→4+16`; end `4+18` unprintable, `solve_log` BLOCKED) → confirmed DUPLICATE / covered_by_existing_redline.
  Not a missing redline.
- **log3** — RESOLVED continued-34: WIRED + DRAWN (`c19b565`) as an owner-confirmed / HUMAN-ADJUSTABLE GEOMETRY
  render. The fragmented s3 conduit couldn't auto-trace (`DESIGN_PATH_NOT_CONNECTED`), so the owner confirmed the
  straight TOP path (11 control points); s2 `12+63 FLOWER POT` stub + s3 247' straight segment between bound
  endpoints; downstream `15+13→21+63` covered by drawn log4. No longer a blocker. (Was reclassified in continued-33.)
- **Owner-locked abstains** log5/31/38/43 (`must_remain_abstained`); **source-gap** log15/16 (unprinted cuts) + log57 (`.FS`).
- **Stored-anchor debt** — log48 (corrupted `5+14`) + log70 (superseded `1+45`) render via the override, but the
  stored fixture values are still wrong; repair under a census re-baseline. (B-DATA-LOG48-ADJ-1.)
- (RESOLVED continued 32: log44 rendered `7039c48` — owner source-verified the corpus print-18 mis-map onto the
  Woodson s10+13 run via two gated opt-ins (`owner_corrected_parent_sheet_context` + the reusable
  `footage_tick_ladder_route_evidence`); the source-location conflict across sheets 18/13/10 is closed.)
- (RESOLVED continued 31: log30/log4/log42 rendered `a8b2d31`/`f75c5c6`/`62ee0da`; first fiber-MAIN render path
  proven; sibling-shared-trunk gate added; log42 end re-identified as the AP-105 terminal, not a pothole.)

## Forbidden areas (this and every wiki/session-hygiene session)
Do NOT touch: engine code, renderer, fixtures / anchors / coordinates, backend, web, product runtime,
`origin/main`, or deploy. No new production flag; no fixture mutation; no invented coordinates; no owner
naming where the solver can bind from source. All changes surgical, reversible, minimal-blast-radius.

## Where archived detail lives (load ON DEMAND only — never as default bootstrap)
- `C:/Nova/knowledge/TrueLine-Wiki/wiki/hot.md` — current-state arc (read TOP ~35 lines only for latest).
- `…/wiki/current-sprint.md` — per-session rollups (detailed saves).
- `…/wiki/log.md` — full chronological archive.
- `…/wiki/bugs/current-bugs.md` — open bugs by ID (file:line cited).
- `…/wiki/index.md` — section map + on-demand doc index.
- `gac/*.md` (repo) — per-target source-adjudication packets.
- `wiki/active-context.md` (repo) — deeper historical engine context (pre-continued-23; see its banner).

## Bootstrap rule
Read this file first. Read the TOP section of `hot.md` only if you need the very latest. **Do NOT
full-read `log.md`, `current-sprint.md`, or `hot.md`** unless explicitly asked or tracing a specific
historical decision. Trust this snapshot + the latest commit as current truth; verify against `git` if
in doubt. When you `/save-session`, also bump the snapshot block above so this file stays canonical.
