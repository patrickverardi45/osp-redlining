# GAPS.md — honest weakness audit

> Written 2026-07-07 during the one-time knowledge transfer, after a full-repo exploration and a
> live staging product audit. Ordered by severity. Every entry: what / where / why it matters /
> a fix scoped small enough for a single focused session. Several fixes are **owner-gated** by
> standing project rules (default-OFF flags, no auth work without approval, no pushes) — "small"
> here means small to *implement once approved*, not permission to skip approval.

---

## CRITICAL

### 1. There is no real authentication — identity is a client-supplied header
- **What:** The entire `/v2/product` API trusts `X-TL-Tenant` / `X-TL-Session` request headers as
  identity ("DEV STAND-IN identity headers (NOT real auth)" — the code's own words). The only real
  gate is Cloudflare Access (one-time-PIN) at the staging edge. Anyone past Access — or anything on
  localhost — is a full superuser of any tenant they name, including `POST /jobs/{id}/delete`.
  The staging web bakes ONE shared tenant into its build, so every Access user shares one workspace.
- **Where:** `truelinev2/api/deps.py` (`get_context`), `truelinev2/context.py`,
  `truelinev2/security/isolation.py`; consumed by every route in
  `truelinev2/api/product_pipeline_routes.py`. Web side: `src/lib/api/*.ts` in the separate
  `trueline-web-experience` repo (`NEXT_PUBLIC_TL2_TENANT`).
- **Why it matters:** One shared secret (an Access PIN to an email) away from full read/write/delete
  of all customer data. Multi-user testing (owner + external tester) already collides in one tenant.
- **Fix (small, owner-gated — auth phase "P5" is deliberately paused, do NOT freelance a custom
  auth system):** Interim hardening only: a default-OFF `TL2_DESTRUCTIVE_OPTIN` flag that, when
  unset, returns 403 for `POST /jobs/{id}/delete` (and optionally `/transition`) so browse-level
  users cannot destroy jobs. ~30 lines + tests, no auth semantics. The real fix (mapping Cloudflare
  Access JWT identity → tenant) is the owner-gated P5 slice.

### 2. Destructive operations leave no trace, and the served store has no automated backup
- **What:** On 2026-07-06 the only real job in the served staging store was deleted by *something*
  and the deletion is unattributable: the supervisor starts uvicorn with `--log-level warning`
  (no access log), `delete_job` is an immediate recursive remove, and the only backups are manual
  ad-hoc folder copies (`staging_smoke/ops/backups/test-pre-*` — which predate the final state and
  could not restore it).
- **Where:** `data/outputs/truelinev2/staging_smoke/ops/staging-supervisor.ps1` (uvicorn launch,
  line ~84); `truelinev2/api/product_pipeline_routes.py::delete_processing_job` (~line 445);
  store contracts under `truelinev2/contracts/processing_job.py`.
- **Why it matters:** Real customer closeout data can vanish silently. Incident response is
  impossible without a request trail. This already happened once.
- **Fix (two independent small tasks):**
  1. A tiny audit middleware (default-ON, no bodies): append `ts, tenant, session, method, path,
     status` to a rotating file under the ops log dir for every `/v2/product` request. ~40 lines +
     test. (Or minimally: add `--access-log`/info level to the supervisor's uvicorn line.)
  2. A scheduled snapshot: `robocopy` the served store root to a dated folder nightly, keep N days.
     One PowerShell script + one scheduled task registration, mirroring the existing supervisor
     task pattern.

---

## HIGH

### 3. CI is blind to the product's core guarantee (the deterministic render corpus)
- **What:** The byte-identity frontier (50/58 drawn, DETERMINISTIC_AUTO count 49, cold matrix
  11/11, prior PNGs md5-identical) is only verifiable on the owner's machine: the fixtures live
  under gitignored `data/`, and `.github/workflows/backend-checks.yml` deliberately runs a 13-file
  targeted subset (~280 tests of ~2,330).
- **Where:** `.github/workflows/backend-checks.yml`; skip-guards in
  `truelinev2/tests/` (e.g. `test_callout_route_assembly_sweep.py`, `test_kmz_writer.py` skip when
  fixtures are absent).
- **Why it matters:** A regression to the engine's central promise can merge green. The single
  fixture-holding machine is a bus-factor-one verifier.
- **Fix (small):** Commit a tiny SYNTHETIC plan+bore-log fixture (generated, name-free, a few KB —
  the harness already has `harness/synth.py`) plus one hash-locked render test added to the CI
  file list. This puts *one* byte-identity canary in CI without shipping any real customer PDF.

### 4. Store writes are non-atomic and unlocked
- **What:** Product records are written with plain `path.write_text(...)` — no temp-file +
  `os.replace`, no per-job lock. A crash mid-write corrupts a record; two concurrent writers
  (web UI + a curl session — exactly how staging is used) can interleave read-modify-write and
  lose updates. The supervisor's mutex only serializes process *healing*, not store writes.
- **Where:** e.g. `truelinev2/contracts/job_pricing.py::save_job_pricing` (line ~132); the same
  pattern across `truelinev2/contracts/*.py` writers.
- **Why it matters:** The JSON store is the system of record; silent corruption/lost updates are
  worst-case failures for a closeout product.
- **Fix (small):** One helper (`contracts/_atomic.py`: write temp in same dir → `os.replace`),
  adopt it in the ~dozen writer call sites, plus a crash-simulation test. Locking can be a
  follow-up; atomicity alone removes the corruption class.

### 5. Staging is one shared tenant — the external tester and the owner collide
- **What:** The web build bakes `staging-smoke`; every Access user sees and can mutate the same
  workspace (audit finding; the approved isolation plan was superseded by the store turning up
  empty — a generic `starter-project` job is now seeded, but collision remains).
- **Where:** supervisor `$Tenant`; web repo build env; served store root
  `data/outputs/truelinev2/staging_smoke/product_store`.
- **Why it matters:** The tester can delete/alter the owner's real work (see #1/#2), and vice
  versa; test data and real data mix in one tenant.
- **Fix (small, owner-gated, already planned):** Repoint the supervisor `$StoreRoot` to a fresh
  root + reseed the starter (backend-only bounce), OR accept shared-sandbox mode until P5 auth.
  The one-line repoint + verification procedure is already written up (2026-07-06 session).

### 6. The repository's default branch is a 407-commit-stale trap
- **What:** `origin/main` = `068a279` (v1-era). All real work is on `feat/truelinev2`. Stale
  v1-era remote branches (`feature/fiber-workflow`, `feat/mrq-*`, `feat/slice1a*`,
  `feature/hero-map-modernization`) add noise.
- **Where:** GitHub repo settings; `git branch -a`.
- **Why it matters:** Any fresh clone, CI default, or new collaborator lands in the wrong world.
- **Fix (small, owner action):** Change the GitHub default branch to `feat/truelinev2` (or merge —
  owner-gated), and delete the four dead remote branches after a one-line ancestry check each.

### 7. Uploads buffer the whole file in RAM via base64 JSON before validation
- **What:** Files upload as `content_base64` in a JSON body; the server decodes the full payload in
  memory *then* validates kind/extension/size. The web caps at 75 MB client-side (~100 MB JSON after
  inflation), but the API itself accepts arbitrarily large bodies from any client.
- **Where:** `truelinev2/api/product_pipeline_routes.py::register_upload` (~line 465);
  client cap in the web repo's `ProductUploadPanel.tsx`.
- **Why it matters:** A single oversized request can exhaust memory on the one staging box
  (mitigated today only by Access + loopback binding).
- **Fix (small):** A default-ON body-size middleware (reject > ~120 MB with an honest 413 naming
  the cap) in `api/app.py`, + one test. No route changes.

---

## MEDIUM

### 8. Store-root sprawl with stranded curated demos
- **What:** 8+ sibling roots under `data/outputs/truelinev2/` (`product_store`, `staging_smoke`,
  `council_audit` — which holds the 7 curated demo jobs NOT served anywhere —
  `product_store_staging` (stale since 06-22), `general_upload_*`, probe roots…). Which root is
  live is one variable in a gitignored script. This caused real confusion: "the demos" were
  believed live while the served store held only one real job.
- **Where:** `data/outputs/truelinev2/*/product_store*`; supervisor `$StoreRoot`.
- **Why:** Operational mistakes (wrong-root reads, "missing" data, accidental seeding into the
  wrong world) are cheap to make and expensive to notice.
- **Fix (small):** A `wiki/` table of every root, its purpose, and its status (live / curated /
  stale-archive candidate), plus owner-gated deletion of the confirmed-stale roots.

### 9. The rotated-page dual-bounds API is a standing footgun
- **What:** `page_bounds_display` (double-rotates on rotated pages) coexists with the correct
  `page_rect_bounds`; only 3 product call sites were repointed (2026-07-06 fix). New code that
  picks the old method reintroduces the misplacement bug class. Pre-fix rotated-page anchors in
  any store are in the broken coordinate space with no marker distinguishing them.
- **Where:** `truelinev2/ingest/pdf.py` lines ~35 (`page_bounds_display`) and ~52
  (`page_rect_bounds`); consumers across `extract/` (legit) and product paths (must use the new).
- **Fix (small):** (a) Loud docstring warnings on both methods stating which callers belong to
  which; (b) a guard test that greps product modules (`api/`, `contracts/`) for
  `page_bounds_display` and fails on any hit; (c) optional: a one-shot script listing stored
  source anchors created before the fix date for re-marking.

### 10. Recognition-by-exact-hash silently reroutes edited files
- **What:** Any byte change to a plan/bore-log moves the job from the recognized-deterministic
  lane to the live-engine lane with no user-visible explanation of the downgrade.
- **Where:** `truelinev2/contracts/recognized_corpus_handoff.py` (`load_registry`, fingerprints);
  `data/recognized_corpus_registry.json`.
- **Why:** Users perceive "it worked yesterday, abstains today" as flakiness when it is provenance
  discipline.
- **Fix (small):** The engine-handoff/status response already carries reasons — add an explicit
  `recognition: {matched: bool, reason: NOT_IN_REGISTRY|HASH_MISMATCH…}` field (additive, behind
  the existing flag) and surface one sentence in the web copy (separate repo).

### 11. Two half-superseded agent-rules layers still sit at the root
- **What:** Root `AGENTS.md` ("OSP Redlining Agent Guide" — v1 commands, "full file replacements
  only"), `AI_rules.md` (ChatGPT-era ALL-CAPS surgical rules), `RUNBOOK.md` (v1 Render deploy),
  and `web/CLAUDE.md → web/AGENTS.md` (legacy web) coexist with the current CLAUDE.md + wiki
  doctrine. Some harnesses auto-read `AGENTS.md` and will ingest v1-era instructions
  ("backend = FastAPI backend, web = frontend app", `uvicorn main:app --reload`).
- **Where:** `AGENTS.md`, `AI_rules.md`, `RUNBOOK.md`, `HANDOFF.md`, `web/CLAUDE.md`, `web/AGENTS.md`.
- **Why:** An agent bootstrapping from the wrong file will operate on the wrong product with the
  wrong rules.
- **Fix (small, owner-gated since they're historical):** Prepend a 3-line "HISTORICAL (v1) — see
  CLAUDE.md / PROJECT.md" banner to each; do not delete.

### 12. Operator pricing vs. server billing will confuse every first-time user
- **What:** The workspace card shows provisional operator-entered dollars (disclaimed), while the
  official closeout PDF omits dollars entirely unless a server cost-rules file is configured
  (`TL2_PRODUCT_BILLING_COST_RULES` — configured nowhere). Correct by doctrine; jarring in demos
  ("where did my $3,000 go?").
- **Where:** `truelinev2/contracts/job_pricing.py` vs `contracts/billing_summary.py` /
  `closeout_pdf.py`; web `ProductOperatorPricing.tsx` (separate repo).
- **Fix (small):** One sentence on the web pricing card ("the printed closeout omits provisional
  dollars"), and/or ship a staging cost-rules JSON (owner decision on rates).

### 13. Legacy v1 + its node_modules bloat and confuse the repo
- **What:** `backend/` (incl. the broken `backend/venv`), `web/` (with node_modules), root
  `node_modules/`, `.next/`, `.vercel/`, `extractor/`, `legacy/`, `archive/` — thousands of files
  of frozen v1. Protection against cross-contamination exists
  (`truelinev2/tests/test_import_isolation.py::test_zero_old_app_imports`) and must stay green.
- **Why:** Slow tooling, wrong-file edits, new-contributor confusion. Deletion is deliberately
  deferred ("engine split" milestone).
- **Fix (small, non-destructive):** Drop a one-line `_FROZEN_V1_DO_NOT_USE.txt` marker in
  `backend/venv/` and `web/`; keep the import-isolation test in the CI list (it is not currently
  in the CI subset — add it, it needs no fixtures).

### 14. ~77 loose proof screenshots and scratch scripts pollute the repo root
- **What:** Untracked `audit-*.png`, `smoke-*.png`, `pr4-*.png`, `mobile-smoke-*.jpeg`, etc., plus
  scratch `truelinev2/proof/run_*probe*.py` and `truelinev2/docs/GENERAL_PLACEMENT_DESIGN_WIP.md`
  sitting untracked.
- **Why:** `git status` noise buries real changes; unclear what is evidence vs. junk.
- **Fix (small, owner-gated):** Move PNGs to a gitignored `proof_images/` (add one `.gitignore`
  line), and either commit or delete the untracked WIP docs/scripts after owner triage.

---

## LOW

### 15. Env-gated E2E tests never run anywhere routinely
- `TL2_TRY_DRAW_E2E=1`-gated tests plus fixture-skips mean some paths only execute when someone
  remembers. Fix: a `scripts/run-full-local-suite.ps1` convenience wrapper documented in CLAUDE.md,
  run before any engine-adjacent push.

### 16. Naming drift: TrueLine vs FieldRoute vs OSP-redlining
- Record formats say `trueline-*-1`, the product says FieldRoute, legacy says OSP redlining. Brand
  retirement is deliberately LAST; until then, keep new identifiers `trueline-*` for consistency
  with existing record formats. No action now.

### 17. Windows-only operations
- Supervisor, scheduled tasks, robocopy conventions, absolute `C:\` paths in ops scripts. Fine for
  the single-box present; portability is a future deployment concern (`production-ops-baseline.md`
  already frames managed hosting as owner-vendor-gated).

### 18. Known-unsolved engine cases are owner-locked, not forgotten
- 8 of 58 corpus bores remain undrawn by design: owner-locked ABSTAINs (log5/31/38/43),
  unprinted ruler-cut stations (log15/16), `.FS` notation (log57), duplicate-parent adjudication
  (log14). Documented in the wiki; do not "fix" these without the owner — they are evidence-gated.

### 19. Unpushed local-only work is a single-disk risk
- The web repo's precision branch (`feat/source-print-review-precision`, local-only) and the entire
  mobile repo (NO git remote) exist on one machine. Fix (owner-gated): push the branch; create the
  mobile remote once the final app name is chosen.

---

## Cross-cutting note for future sessions

The three biggest *classes* of risk here are: (1) **identity** (everything trusts a header),
(2) **single-machine truth** (fixtures, stores, unpushed branches, the only full-suite verifier),
and (3) **silent state divergence** (stale START_HERE vs live store vs git — verify against the
live system, as the 2026-07-06 store incident proved). Every fix above stays inside the standing
guardrails: default-OFF flags, additive contracts, no engine-truth changes, owner approval for
anything destructive or outward-facing.
