# CLAUDE.md — TrueLine / FieldRoute (TrueLine_Beta)

Read me first, act second. This repo holds TWO products: the frozen v1 monolith (`backend/`,
`web/`) and the REAL product, **TrueLine v2** (`truelinev2/` — Python engine + flag-gated FastAPI).
All active work is v2, on branch `feat/truelinev2`. `origin/main` is ~407 commits stale — never
base work on it.

- **PROJECT.md** — architecture, data flow, design decisions, critical paths (read for context).
- **GAPS.md** — known weaknesses ranked by severity, each with a scoped fix (read before "improving" anything).
- **`wiki/START_HERE_TRUELINE_V2.md`** — the CANONICAL current state (HEAD, frontier, staging, next
  gates). Bumped at `/save-session`. **Always verify its claims against `git` and the live system —
  snapshots go stale.**

## Session bootstrap

1. Read `wiki/START_HERE_TRUELINE_V2.md` in full (or run `/start-session`).
2. If you need the very latest: top ~35 lines of `C:/Nova/knowledge/TrueLine-Wiki/wiki/hot.md` —
   NEVER full-read the vault logs (hundreds of KB).
3. Verify: `git log --oneline -3`, `git status`, and (if staging matters) the supervisor `-Status`.

## Commands that matter (Windows / PowerShell)

```powershell
# Python: ALWAYS the repo-root venv (3.11.9) + PYTHONPATH. backend\venv is BROKEN — never use it.
$env:PYTHONPATH = "."

# Full v2 suite (needs gitignored fixtures under data\; expect ~2332 pass / 4 skip on the owner box;
# fixture-dependent tests skip elsewhere):
.\venv\Scripts\python.exe -m pytest truelinev2/tests -q

# CI-equivalent targeted subset (no big fixtures) — the exact file list lives in
# .github/workflows/backend-checks.yml:
.\venv\Scripts\python.exe -m pytest truelinev2/tests/test_product_pipeline_api.py truelinev2/tests/test_product_workflow.py -q   # (etc.)

# Run the v2 API locally (all product surfaces are default-OFF — opt in explicitly):
$env:TL2_PRODUCT_PIPELINE_API_OPTIN = "1"
.\venv\Scripts\python.exe -m uvicorn truelinev2.api.app:create_app --factory --host 127.0.0.1 --port 8100

# Smoke a product endpoint (identity = dev stand-in headers):
curl -s -H "X-TL-Tenant: <tenant>" -H "X-TL-Session: <label>" http://127.0.0.1:8100/v2/product/jobs

# Legacy v1 (reference only, rarely): backend -> uvicorn main:app --reload ; web/ -> npm run dev
```

**Staging** (live: `staging.fieldroute.io` behind Cloudflare Access; supervisor at
`data/outputs/truelinev2/staging_smoke/ops/staging-supervisor.ps1`):

```powershell
powershell -ExecutionPolicy Bypass -NoProfile -File <supervisor> -Status   # report only (expect 200/200/302)
powershell -ExecutionPolicy Bypass -NoProfile -File <supervisor> -Once     # heal (safe bounce step)
# NEVER -Restart casually: it kills backend + web + cloudflared together.
# Safe backend-only bounce: kill ONLY the :8100 listener PID, then -Once.
```

- The supervisor sets the served store root (`$StoreRoot` → `TL2_PRODUCT_STORE_ROOT`) and the live
  TL2_* flags. Env changes go THERE (durable), not in ad-hoc shells.
- Staging smokes: use fresh `tmp-*` job ids, and DELETE them afterward
  (`POST /v2/product/jobs/<id>/delete`). Never write to real/curated jobs.

## Conventions this codebase actually follows

- **Default-OFF flags for every new surface.** New behavior/env: `TL2_*` in
  `truelinev2/config.py::Settings.from_env`, documented "OFF is byte-identical", mounted
  conditionally in `api/app.py`. Enabled nowhere until the owner opts in.
- **Contracts pattern** (`truelinev2/contracts/`): pure modules, one JSON record per concern with a
  `record_format` version string (`trueline-<thing>-1`), tenant+job-scoped paths, inline `audit`
  arrays, `Decimal` money (ROUND_HALF_UP, canonical strings). Additive evolution only.
- **Errors:** contract exceptions map via `_to_http` (404 not-found / 409 state-conflict / 400 bad
  input). Refusals name a SPECIFIC reason code (`BORE_LOG_FORMAT_UNRECOGNIZED`, …). Never leak
  absolute paths in details. Honest `None`/absence over fabricated zeros or defaults.
- **Naming (HARD RULE):** no customer/person/place/demo names in reusable code, routes, env,
  schema, tests, or doc headings — real names are runtime data only. Customer-facing UI never says
  "demo". Job ids/labels in seeds and tests stay generic.
- **Red Stroke Law:** drawn overlays are ONLY `REDLINE_STROKE_RGB` red
  (`truelinev2/render/crop.py`); never recolor source PDF evidence.
- **Doctrine:** REVIEW ≠ AUTO ≠ final; abstain honestly instead of guessing; zero-false beats
  coverage; no AI/runtime-API calls in the production truth path; banked human review grades are
  never overridden.
- **Comments/docstrings** are dense and explanatory (why + guarantees) — match that register.

## Gotchas (things that look one way but aren't)

- `backend\venv` is a broken trap; only the repo-root `venv` works.
- `data/` is entirely gitignored: fixtures, product stores, the supervisor, the recognized-corpus
  registry all live there. Tests skip without fixtures; CI cannot see the render corpus.
- **Which store is live is a variable**, not a fact: `$StoreRoot` in the staging supervisor.
  Sibling roots under `data/outputs/truelinev2/` (curated demos in `council_audit/` are NOT
  served). Check the live API before believing any store claim.
- **Rotated plan pages:** product/raster paths must use `PlanPdf.page_rect_bounds`;
  `page_bounds_display` double-rotates on rotated pages and exists only for legacy text/vector
  consumers (`ingest/pdf.py`). Getting this wrong reintroduces a fixed customer bug.
- **Recognition is exact-sha256**: an edited/re-saved upload silently falls from the recognized
  deterministic lane to the live-engine lane (`data/recognized_corpus_registry.json`).
- `render/crop.py` caption band: default ON (diagnostics byte-identical); the product handoff
  passes `caption=False`. Don't flip defaults.
- Engine sheet resolution: default global `sheet_offset` (13); the product upload path passes a
  title-block `sheet_index` (`ingest/sheet_label_index.py::build_sheet_index`) instead. The
  deterministic 50/58 callers pass nothing — keep it that way.
- **The customer web UI is a SEPARATE repo** (`C:\Nova\projects\trueline-web-experience`). Web
  copy/UX changes ship THERE, never here. Never run `npm run build` in that checkout while it
  backs live staging (it serves from its `.next`; rollback snapshots exist as `.next.prev-*`).
- Root `web/`, `node_modules/`, `.next/`, `.vercel/`, `AGENTS.md`, `AI_rules.md`, `RUNBOOK.md` are
  frozen v1-era — do not follow their instructions; this file + the wiki supersede them.
- `.claude/worktrees/` = other live agent sessions; never touch.
- Mobile (`trueline-field-mobile`) is separate and local-only; LAMA (`C:\dev\lama\lama-mobile`) is
  a DIFFERENT product — never mix into TrueLine sessions.
- The knowledge vault (`C:\Nova\knowledge\TrueLine-Wiki`) has no remote and pre-existing drift:
  stage ONLY files you touched; never `git add -A`, never push it.

## Hard rules (violations are regressions, not style)

1. **Never touch without explicit owner approval:** `extract/registry.py::select_dialect`, the
   named dialect detectors (`extract/brenham.py`, `extract/odot.py`),
   `contracts/uploaded_corpus_engine_handoff.py::_cap_review`, renderer truths (`render/`),
   closeout acceptance policy, AUTO/final-placement policy (G-e is owner-gated, NOT started).
2. **Locked tripwires — re-verify after ANY engine-adjacent change:** deterministic **50/58**,
   `DETERMINISTIC_AUTO` count **49**, cold matrix **11/11**, full suite green, ALL prior proof
   PNGs byte-identical.
3. `truelinev2/tests/test_import_isolation.py` (zero old-app imports) must stay green — v2 never
   imports `backend/`, `app/`, `tl_core`, `redline_pdf_first`.
4. **origin/main untouched** (this repo AND the web repo) unless the owner says merge. Commit/push
   ONLY when the owner asks. Surgical, reversible, minimal-blast-radius changes; no broad
   refactors, no KMZ/parser/render rewrites without approval.
5. Tenant/company/project data must never bleed across tenants; keep isolation fail-closed.
6. Test before shipping; report failures verbatim; never fake success or fall back to mock data in
   live paths.
7. Curated demo jobs and owner backups are owner-gated: never mutate, move, or "clean" them.

## Key env flags (all default OFF; full list in `truelinev2/config.py`)

`TL2_PRODUCT_PIPELINE_API_OPTIN` (product routes) · `TL2_PRODUCT_READINESS_API_OPTIN` (readiness/
REVIEW-candidate lane) · `TL2_FIELD_EVIDENCE_API_OPTIN` (field-evidence writes) ·
`TL2_UPLOADED_CORPUS_AUTO_OPTIN` (unset ⇒ uploaded-corpus AUTO is capped to REVIEW — leave unset) ·
`TL2_PRODUCT_STORE_ROOT` · `TL2_RECOGNIZED_CORPUS_REGISTRY` · `TL2_ALLOWED_ORIGINS` ·
`TL2_RATE_LIMIT_OPTIN` · `TL2_PRODUCT_BILLING_COST_RULES` · `FIELDROUTE_SENTRY_DSN`/`SENTRY_DSN`.

## Where answers live

| Question | Look in |
|---|---|
| Current HEAD / frontier / staging state | `wiki/START_HERE_TRUELINE_V2.md`, then `git` + live checks |
| Architecture / why | `PROJECT.md`; `truelinev2/README.md`; `truelinev2/docs/` |
| Known issues + scoped fixes | `GAPS.md` |
| Session history / decisions | vault `wiki/hot.md` (top only), `current-sprint.md`, `log.md` (section-only reads) |
| Engine design records | `wiki/m8_*.md`, `wiki/m9_*.md`, `wiki/doctrine/` |
