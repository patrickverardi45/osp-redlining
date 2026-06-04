# redline_pdf_first — Day 1 (scratch skeleton)

Clean-room PDF-first redline engine. **Scratch only** (`C:\Nova\scratch\clean-redline-test`).
Not part of the TrueLine repo; import-isolated from `backend/main.py`.

## What Day 1 ships (REAL)
- **`contracts.py`** — frozen `EngineResult` contract (statuses, tiers, render_targets; JSON + `validate()`).
- **`pdf/rotation.py`** — real PyMuPDF rotation/display-coordinate helpers; 270° correct; no Brenham hardcoding.
- **`pdf/text_extract.py`** — rotation-aware extraction primitives (words/lines/callout search, raw + display bbox).
- **`selector/stub_selector.py`** — contract-valid STUB result for proven log51 (AUTO_SELECT, Sheet 8, `0+00→2+99`, `DIR. BORE (299')`, `render_target=evidence_card`).
- **`render/evidence_card.py`** — WORKSPACE_PLAN_EVIDENCE_PANEL payload builder (structured cards).
- **`cli.py`** — `python -m engine.redline_pdf_first.cli --stub-log log51 --out <json>`.

## Invariants (enforced by tests)
- Only `pdf/` imports `fitz`.
- No import of TrueLine `backend`/`main`.
- Nothing raises to the caller — failures become `FAIL_SAFE` / `ERROR` results.
- Friday render target = `evidence_card` (NOT `debug_overlay` / PDF-over-world; `route_polyline` = Phase 2).

## Run
```
python -m engine.redline_pdf_first.cli --stub-log log51 --out _analysis\day1_stub_engine_result.json
python -m pytest tests -q
```

## Stubbed (NOT Day 1)
Full selector funnel (Day 2) · evidence-card crop PNGs / full renderer (Day 3) ·
TrueLine adapter `backend/app/core/pdf_first_adapter.py` (Day 4, needs write authorization) ·
Leaflet `route_polyline` geometry bridge (Phase 2: authored→route_id crosswalk + absolute station frame).
