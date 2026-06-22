# TrueLine v2 — independent PDF-first redline product

A clean-room reimplementation. The old app (`backend/main.py`, `backend/app/**`,
`redline_pdf_first`, `tl_core`) is **specification only** — never imported here.
v2 imports **only** standard infrastructure: PyMuPDF, openpyxl, Pillow, pydantic,
FastAPI/uvicorn, sqlite, pytest.

## Design thesis
Only plan-evidence **extraction** is convention-specific — a pluggable
`PlanDialect`. Normalization, matching, scoring, tiering, rendering, abstention,
storage, and serving are convention-agnostic. A new plan convention (e.g. ODOT)
is a new dialect, not an engine fork. (The old engine welded the Brenham grammar
into extraction, which is why ODOT returned 0 callouts.)

## Layout
```
truelinev2/
  config.py context.py stations.py service.py
  schema/models.py                  canonical pydantic models
  ingest/pdf.py                     fitz-based plan reader (the only fitz importer)
  ingest/borelog_brenham.py         flat-table xlsx -> Bore
  ingest/normalize.py               format detect (ODOT deferred to M2)
  extract/base.py brenham.py registry.py   PlanDialect seam + Brenham dialect
  match/chains.py score.py decide.py engine.py   convention-agnostic matcher (honest abstain)
  render/crop.py                    clip-bounded evidence crop (fitz raster + PIL draw)
  store/artifacts.py db.py          traversal-safe artifacts + sqlite review store
  security/isolation.py sanitize.py fail-closed ownership + output escaping
  review/payload.py                 v2 Match-Review payload
  api/app.py routes.py deps.py container.py   thin FastAPI
  proof/run_m1_brenham.py import_isolation.py
  tests/
```

## Run (repo root, root venv)
```powershell
$env:PYTHONPATH = "."
.\venv\Scripts\python.exe -m truelinev2.proof.import_isolation
.\venv\Scripts\python.exe -m truelinev2.proof.run_m1_brenham
.\venv\Scripts\python.exe -m pytest truelinev2/tests -q
# standalone API (separate port; no collision with the old app):
$env:TL2_ALLOWED_ORIGINS = "http://localhost:3000"
.\venv\Scripts\python.exe -m uvicorn truelinev2.api.app:create_app --factory --host 127.0.0.1 --port 8100
```

> Local product-staging (real seed `product_store` + web product mode): see [`docs/runbooks/product_staging_local_wiring.md`](docs/runbooks/product_staging_local_wiring.md).

## M1 status
Brenham `bore_log51` placed by v2's own pipeline: `AUTO_SELECT`, sheet 8,
`0+00->2+99`, 299' — reproduced independently, served as a real PNG over HTTP,
tenant-scoped + fail-closed.

## Deferred to M2
ODOT VeroFy Construction Log ingestion + the ODOT plan dialect (`DB-NN`
convention with disaggregated station/footage) — the generalization payoff.
