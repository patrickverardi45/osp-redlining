# tl_core — TrueLine clean-room redline service

A strangler-style, clean-room rebuild of the TrueLine **redline → evidence →
artifact → Match-Review** surface. It lives **alongside** the original
`backend/main.py` + `backend/app/**`, which remain **untouched and read-only**.
Nothing here imports or mutates `main.py`.

## Stance (from the 2026-06-09 mapping audit)
- **Reuse-by-import** the proven, decoupled PDF-first engine
  (`app/core/redline_pdf_first`) behind a clean port. It is verified free of
  coupling to global `STATE` / `main` / `_session_scope` / FastAPI, so importing
  it (never editing it) is safe.
- **Re-architect** only the audited-weak seams:
  | Monolith weakness | tl_core replacement |
  |---|---|
  | global mutable `STATE` | explicit request-scoped `RequestContext` + scoped store |
  | opt-in tenant ownership (`if caller is None: return`) | **fail-closed** isolation, deny by default |
  | inline monolith routes | thin routers; logic in services |
  | unescaped `document.write` HTML sink (stored-XSS) | output encoding (`security/sanitize.py`) |
  | client-path file serving | **traversal-safe** artifact store (basename + containment) |
  | client-chosen session id in URL (IDOR) | identity from auth context; only the artifact basename in the URL |

## Layout
```
tl_core/
  app.py                  FastAPI factory (fail-closed CORS) + router mounts
  config.py               typed Settings (from_env / for_proof); default-OFF flags
  context.py              RequestContext + TenantId (fail-closed; slug, never UUID)
  container.py            wired singletons (engine + store + services)
  domain/redline.py       pure types: ArtifactRef, Placement, RedlineResult
  ports/                  engine.py, artifacts.py (Protocols — dependency inversion)
  adapters/
    engine_pdf_first.py   reuse-by-import of app/core/redline_pdf_first behind the port
    artifact_fs.py        tenant-scoped, traversal-safe PNG store
  security/
    isolation.py          scoped keys + assert_owns (deny by default)
    sanitize.py           escape_html for HTML sinks (anti stored-XSS)
  services/
    redline_service.py    orchestrate bore -> engine -> render -> scoped store
    match_review_service.py  assemble match-review-queue-1 payload + artifact URLs
  api/                    deps.py, health.py, artifact_routes.py, redline_routes.py
  proof/
    run_first_proof.py    real bore -> engine -> PNG -> store -> safe read (through-disk)
    run_http_proof.py     same chain proven over real HTTP (threaded uvicorn + urllib)
    compare_old_vs_new.py engine-direct vs tl_core: assert identical selection
  tests/                  fast unit tests (isolation, sanitize, store, adapter, MRQ)
```

## Run (repo root, root venv = Python 3.11.9)
```powershell
$env:PYTHONPATH = "backend"
.\venv\Scripts\python.exe -m tl_core.proof.run_first_proof     # backend chain
.\venv\Scripts\python.exe -m tl_core.proof.run_http_proof      # HTTP surface
.\venv\Scripts\python.exe -m tl_core.proof.compare_old_vs_new  # old == new
.\venv\Scripts\python.exe -m pytest backend/tl_core/tests -q   # unit tests
```
Run the service standalone on a separate port (no collision with the monolith on 8000):
```powershell
$env:TRUELINE_ALLOWED_ORIGINS = "http://localhost:3000"
$env:PYTHONPATH = "backend"
.\venv\Scripts\python.exe -m uvicorn tl_core.app:app --host 127.0.0.1 --port 8099
```
Proof inputs default to `bore_log51.xlsx` (the engine's AUTO_SELECT bore) +
the in-repo Brenham Phase-5 PDF; override with `TL_CORE_PROOF_BORE` / `TL_CORE_PROOF_PDF`.

## Proven (Milestone 1)
Real `bore_log51` + real Brenham Phase-5 plan PDF → reused engine `AUTO_SELECT`
(sheet 8, `0+00→2+99`, 299 ft) → real clip-bounded **823 KB** PNG → tenant-scoped
store → served over HTTP (`200 image/png`, bytes == disk) → `match-review-queue-1`
payload referencing the artifact URL → cross-tenant `404`, missing-identity `401`.
Reports: `data/outputs/tl_core/m1_*_report.json`.

## Not done yet (honest)
- **Visible in the real Next.js Match Review UI** — needs a router mount into
  `main.py` + a frontend change. Approval-gated (see hard rules). M1 stops at the
  served artifact + UI-compatible payload + a confirmed real PNG.
- **Real JWT verification** — identity currently arrives as `X-TL-Tenant` /
  `X-TL-Session` headers standing in for verified claims; swap the source in
  `api/deps.py` without changing downstream code.
- **Persistent scoped Store (sqlite)** replacing the monolith's global `STATE`
  more broadly (M1 uses the filesystem artifact store + in-request context).
- **Geometric redline-overlay DRAW** (flag-gated; abstains for no-coords AUTO bores).

## Revert
Delete `backend/tl_core/` and `data/outputs/tl_core/`. Nothing else on disk changes.
