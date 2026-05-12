# TrueLine Sprint Handoff

**Date:** 2026-05-12  
**Branch (worktree):** `claude/hungry-mendel-a3e10e`  
**Main repo:** `C:\Nova\projects\TrueLine\TrueLine_Beta`

---

## Current Goal

Migrate TrueLine from its pilot-token-only auth model to a real email/password + company/tenant auth system — without breaking any existing runtime behavior at any step.

This session completed **Phase 0**: the database foundation (schema + seed CLI). Phases 1–4 remain.

---

## Phases Overview

| Phase | Description | Status |
|-------|-------------|--------|
| 0 | SQLite schema + bootstrap seed CLI | **Done (uncommitted)** |
| 1 | `/auth/login` route, bcrypt hashing, JWT issuance | Not started |
| 2 | Refresh token endpoint, token rotation | Not started |
| 3 | Frontend login page, token storage, AuthGuard integration | Not started |
| 4 | Company admin UI, user invite flow | Not started |

---

## Current State

### Uncommitted changes in main repo

These changes exist on disk but have **not been committed**:

| File | Change |
|------|--------|
| `web/src/app/projects/[projectId]/page.tsx` | Threads `kmzSemantic` state + `onKmzSemanticChange` callback |
| `web/src/components/ModernHeroMap.tsx` | Receives `kmzSemantic` prop; observability fetch now triggers on semantic data, not layer toggle |
| `web/src/components/RedlineMap.tsx` | Export error surfacing (`engExportError` state + inline banner); `onKmzSemanticChange` prop bridge |
| `backend/app/db.py` | **New file** — auth SQLite schema + helper functions |
| `backend/scripts/bootstrap_auth.py` | **New file** — idempotent seed CLI |

### Worktree state

The worktree (`hungry-mendel-a3e10e`) is **35 commits behind `origin/main`** and has one local modification:
- `web/src/app/projects/page.tsx` — dashboard blank-by-default fix (localStorage project list)

This worktree fix needs to be reconciled with `main`. The same fix was also applied directly to the main repo file at `C:\Nova\projects\TrueLine\TrueLine_Beta\web\src\app\projects\page.tsx` and committed as `c8e2ec7`.

---

## Files Being Worked On

```
backend/
  app/
    auth.py               — pilot JWT auth (read-only reference; unchanged)
    db.py                 — NEW: Phase 0 auth schema + helpers
  scripts/
    issue_pilot_token.py  — existing pilot token CLI (unchanged)
    bootstrap_auth.py     — NEW: Phase 0 seed CLI

web/src/
  app/
    projects/page.tsx                     — dashboard (fixed: blank + localStorage)
    projects/[projectId]/page.tsx         — workspace page (kmzSemantic state threading)
  components/
    RedlineMap.tsx        — main workspace component (export error + semantic bridge)
    ModernHeroMap.tsx     — Leaflet map (semantic prop; proactive observability fetch)
```

---

## What Changed This Session

### 1. Dashboard — blank by default (committed: `c8e2ec7`)
- **Before:** 4 hardcoded seeded project cards (`brenham-phase-5`, etc.) always rendered
- **After:** Dashboard reads from `localStorage["trueline_projects"]`; starts empty; inline `+ New Project` form creates entries with `generateSlug()` + auto-push to `/projects/{slug}`

### 2. Export Engineering KMZ error surfacing (uncommitted)
- **Before:** `handleExportEngineeringKml` silently returned on `!res.ok` (likely 401) — button appeared to do nothing
- **After:** `engExportError` state renders an inline red banner with actionable message; 401 specifically hints "Ensure your pilot token is set"

### 3. KMZ semantic render-bridge (uncommitted)
- **Before:** `ModernHeroMap` only received `kmz_reference` geometry. The observability render-payload fetch was gated behind a UI layer toggle AND silently failed on JWT 401 after Sprint F5 locked `localhost_router`.
- **After:** `state.kmz_semantic` flows `RedlineMap → ProjectPage → ModernHeroMap` via callback prop bridge. The observability fetch now fires proactively whenever `kmzSemantic` is non-null, independent of any UI toggle.

### 4. Phase 0 auth foundation (uncommitted)
- **`backend/app/db.py`** — SQLite schema for `companies`, `users`, `memberships`, `projects`, `refresh_tokens`; `hash_password` / `verify_password` (SHA-256 + salt; bcrypt swap in Phase 1); `auth_db()` context manager; individual row helpers
- **`backend/scripts/bootstrap_auth.py`** — creates one company + owner user + membership binding; idempotent (second run prints `[skip]` for all rows)
- DB lives at `backend/uploads/auth.db` (overridable via `TRUELINE_AUTH_DB_PATH`)
- **Zero runtime behavior change** — nothing imports `db.py` yet

---

## Things That Failed / Problems Found

### Silent failure pattern (widespread)
Most `apiFetch` call sites use `if (!res.ok) { console.warn(...); return; }` or empty `catch {}` blocks. After Sprint F5 added `Depends(get_current_tenant)` to `localhost_router`, any unauthenticated call silently 401s with no user feedback. Export was the first one surfaced — others likely exist.

### KMZ semantic double-gate bug
The observability render-payload fetch in `ModernHeroMap` was gated on `layerKmzContext` (a UI toggle state), not on whether semantic data actually existed. The `kmz_semantic` field was never passed to `ModernHeroMap` at all — it only received `kmz_reference` geometry. Both problems were independently sufficient to break the context layer.

### Worktree vs main mismatch
Early in the session, dashboard fixes were applied to the worktree file path. The production app uses the main project path. The fix had to be re-applied to the main file. Going forward: always verify which path is active before editing.

### `bcryptpy` not in requirements
Phase 0 uses SHA-256 + salt for password hashing as a placeholder. `bcrypt` is the correct production choice but is not in `requirements.txt`. Phase 1 must add it before the login route goes live.

---

## What's Next

### Immediate (before starting Phase 1)
1. **Commit** the 5 uncommitted changes in the main repo:
   - The 3 modified web files (KMZ bridge + export error)
   - `backend/app/db.py`
   - `backend/scripts/bootstrap_auth.py`
2. **Reconcile the worktree** — it's 35 commits behind and has a redundant `projects/page.tsx` modification that was already committed to main.

### Phase 1 — Login route
- Add `bcrypt` to `requirements.txt` (and swap `hash_password` in `db.py` to use it)
- Create `POST /auth/login` on a new `auth_router` (no `Depends(get_current_tenant)` — it IS the auth entry point)
- Accept `{ email, password }`, verify against `users.password_hash`, return short-lived JWT + refresh token
- Store `refresh_token` hash in `refresh_tokens` table with `expires_at`
- Keep `localhost_router` pilot auth intact in parallel

### Phase 2 — Refresh token endpoint
- `POST /auth/refresh` — accepts refresh token, validates hash + expiry, issues new JWT + rotates refresh token

### Phase 3 — Frontend login flow
- Login page at `/login` (email + password form)
- On success: store JWT in `localStorage` (same key the existing `apiFetch` already reads)
- Update `AuthGuard.tsx` to redirect to `/login` on 401 instead of showing pilot-token paste gate
- Remove pilot paste gate UI once real login is wired

### Phase 4 — Company admin
- User invite flow (create membership for new email)
- Project ownership scoped to `company_id` (plumb through workspace page)

---

## Key Architecture Notes

- **`apiFetch`** (`web/src/lib/apiFetch.ts`) — adds `Authorization: Bearer <token>` from `localStorage["trueline_pilot_token"]`. Phase 3 will change the token key or unify the storage.
- **`get_current_tenant`** (`backend/app/auth.py`) — validates JWT, extracts `tenant_id`. Phase 1 login will issue JWTs with the same claims so this validator requires zero changes.
- **`localhost_router`** — all workspace endpoints live here, behind `Depends(get_current_tenant)`. This is correct and stays.
- **Session store** (`backend/uploads/session_store.db`) — separate SQLite file, unchanged. Auth DB is `auth.db` in the same directory.
- **`TRUELINE_JWT_SECRET`** — must be set as env var before any backend startup. The auth assert fires at module import time.
