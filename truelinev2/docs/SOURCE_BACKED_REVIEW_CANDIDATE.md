# Source-Backed REVIEW Candidate (MVP) — the first drawing-capable slice (read-only spine + REVIEW overlay)

> Module: `truelinev2/harness/review_candidate.py` · Tests: `truelinev2/tests/test_review_candidate.py`.
> Consumes the completed readiness spine
> ([`SOURCE_COMPLETENESS_REVIEW_READINESS.md`](SOURCE_COMPLETENESS_REVIEW_READINESS.md) →
> [`SOURCE_SPAN_EXTRACTOR.md`](SOURCE_SPAN_EXTRACTOR.md) →
> [`SOURCE_BACKED_ENDPOINT_BINDING.md`](SOURCE_BACKED_ENDPOINT_BINDING.md) →
> [`SOURCE_BACKED_ROUTE_VERIFICATION.md`](SOURCE_BACKED_ROUTE_VERIFICATION.md)) and is exercised by the
> [`COMPLETE_PACKAGE_QA_HARNESS.md`](COMPLETE_PACKAGE_QA_HARNESS.md) (product QA, **not** cold validation).

## What this stage is

This is the **first slice that can draw.** After the readiness spine returns exactly `READY_FOR_REVIEW_REDLINE`
(source-confirmed span + both endpoints source-anchored + route verified), it produces a **human-reviewable REVIEW
CANDIDATE** — a candidate redline overlay plus its full source evidence chain.

It is **NOT AUTO. NOT final placement. NOT a status promotion.** `is_auto` / `is_final_placement` / `is_promotion`
on the candidate and `performs_auto` / `performs_placement` / `promotes_status` on the report are **always False**.
It is a candidate for a human to accept or reject downstream; the readiness classifier is untouched and still
`draws_anything == False`.

## The strict gate

A candidate is produced **only** when `readiness.report.status == READY_FOR_REVIEW_REDLINE`. Every other status —
`MISSING_BORE_SPAN_SOURCE`, `NO_SOURCE_CONFIRMED_SPAN`, `ANCHOR_BLOCKED`, `ROUTE_BLOCKED`, `SPAN_SOURCE_FOUND`,
`PACKAGE_RECOGNIZED_CONTROL`, `PACKAGE_UNUSABLE_OCR_REQUIRED`, `KEEP_BLOCKED` — is a **refusal**: `candidate_status
= REVIEW_CANDIDATE_REFUSED`, **zero** candidates, **no** artifact, with a named `refusal_reason`.

## Source-backed geometry only

Every visual element comes from **observer-exposed** geometry, never invented:

- the two endpoints are the **bound anchor coordinates** (G-a′ source-backed anchors — route terminus / structure
  symbol / leader tip);
- the drawn run is the **verified main-run backbone** (`RouteVerification.route_geometry`, the G-b‴
  `discriminate_main_run` `main_run_segments`), exposed as REVIEW evidence when `route_ready`.

## Output (`ReviewCandidate` / `ReviewCandidateReport`)

`ReviewCandidate`: `span_id`, `start_station` / `end_station`, `source_file` / `source_citation` / `source_kind` /
`confidence`, `start/end_anchor_summary` (status + method + observer-exposed `xy`), `route_summary` (route-ready +
the per-observer status breakdown + segment count), `route_geometry`, `candidate_status`
(`REVIEW_CANDIDATE_READY`), `artifact_before` / `artifact_after` (overlay PNG paths when generated),
`stroke_rgb`, and an `evidence_chain` (the ordered reasons the candidate was allowed). `ReviewCandidateReport`
bundles the readiness status, candidate status, the (0 or 1) candidates, the refusal reason, and the safety flags.

## The visual (Red Stroke Law)

When a caller supplies an `artifact_dir`, `render_review_candidate_overlay` writes two PNGs with a self-contained
`fitz` raster (NOT the product renderer):

- **before** — the plan page as-is (no overlay);
- **after** — the plan page + a **RED** stroke along the verified backbone.

The RED is `REVIEW_STROKE_RGB = (220, 25, 25)`, **test-locked** to the canonical `render.crop.REDLINE_STROKE_RGB`
(the module itself imports nothing from `render`). The stroke is drawn in DISPLAY space via the page's inverse
rotation so it lines up with the observer coordinates; the source PDF is never recolored (the stroke is an
overlay). Artifacts are written only into the caller-supplied directory and are **never committed**.

## Guardrails

Read-only wrt the product; the ONLY thing it draws is the REVIEW candidate overlay into a caller dir. No AUTO, no
final placement, no status promotion, no `_cap_review`, no renderer change, no web / staging / backend runtime, no
`origin/main`, no committed private files or large artifacts. Invents no station / bore row / anchor / endpoint /
route geometry / source relationship (uses only observer-exposed geometry). `select_dialect` untouched; G4/AUTO
unchanged and still blocked. Imports nothing from render / placement / api / store / contracts / match / web (a
test asserts this). Name-free (guard covers the module + doc + test).

## How to run (read-only + REVIEW candidate overlay only)

```
PYTHONPATH=. venv/Scripts/python.exe -m pytest truelinev2/tests/test_review_candidate.py -q

# harness-only CLI: build a REVIEW candidate for a package, writing before/after overlays into a scratch dir:
PYTHONPATH=. venv/Scripts/python.exe -m truelinev2.harness.review_candidate <package_dir> <artifact_dir>
```
