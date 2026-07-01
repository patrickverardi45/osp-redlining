# Source-Completeness & REVIEW-Redline Readiness — the intake traffic controller (read-only)

> Companion to [`COLD_PACKAGE_VALIDATION_INTAKE.md`](COLD_PACKAGE_VALIDATION_INTAKE.md) (the *eligibility*
> gate) and [`COLD_PACKAGE_REDLINE_ARCHITECTURE.md`](COLD_PACKAGE_REDLINE_ARCHITECTURE.md) (the evidence
> pipeline). This document specifies the **read-only classification layer** that answers one product question:
> **“Is this uploaded package ready for REVIEW-redline generation, and if not, exactly why — and what is the
> single next productive step?”**
>
> Module: `truelinev2/harness/review_readiness.py` · Tests: `truelinev2/tests/test_review_readiness.py`

---

## The product rule

- **FieldRoute can draw from complete source packages.**
- **FieldRoute must refuse incomplete packages.**
- **A plan-only package is not enough when no source file confirms the bore/span start and end stations.**

This is not a limitation dressed up as a feature. It is the safety contract behind the ALL-REDLINES standard and
DO-NOT-WIDEN: we never draw a wrong redline, and we never *invent* a bore span the source did not state. When a
package is incomplete, the honest, productive answer is to name the missing source and the next step — not to
guess, and not to ask a human to place geometry from vibes.

## What this layer is (and is NOT)

It is a **traffic controller**, not a diagnostic dead-end. Given the read-only Track B stage evidence for a
package, it routes to exactly one readiness status and attaches an actionable `recommended_next_input`. It is the
gate that prepares the pipeline for **automatic source-span extraction** and future REVIEW redlines once complete
packages arrive.

It **draws nothing, places nothing, promotes nothing.** It touches no renderer, no placement, no `_cap_review`,
no AUTO, no product runtime, no recognized-corpus proof, no fixtures, no coordinates, and no named detectors. It
only *reads* evidence the read-only observers already produce. `draws_anything` and `performs_placement` are
always `False`.

## The pipeline it controls

```
uploaded files
  → identify whether a bore/span source exists            (SPAN_SOURCE stage)
  → extract source-confirmed span rows when present         (a FUTURE extractor plugs in at the SPAN_SOURCE seam)
  → bind start / end stations to drawn anchors              (ANCHOR stage — G-a′ evidence)
  → verify the route between the two anchors                (ROUTE stage — G-b / G-b‴ evidence)
  → mark REVIEW readiness                                   (READY)
```

The classifier performs **none** of these steps. It reads their evidence (already computed by the read-only
observers) and reports where the package stands. A future automatic bore/span source extractor plugs in at the
**SPAN_SOURCE seam**: it will populate `SpanSourceEvidence.source_confirmed_span_count`; the classifier only
reads that count.

## The status ladder (strict precedence — the first match wins)

| # | Status | Meaning | Next step (`recommended_next_input`) |
|---|--------|---------|--------------------------------------|
| 1 | `PACKAGE_RECOGNIZED_CONTROL` | A named dialect / the recognized-corpus registry already handles the plan: the deterministic **control lane**, out of the cold REVIEW pipeline. **Not a failure.** | *(none — not a cold-lane package)* |
| 2 | `PACKAGE_UNUSABLE_OCR_REQUIRED` | No extractable text layer. Nothing can be read yet. | `OCR_OR_RASTER_INGESTION` |
| 3 | `KEEP_BLOCKED` | An **owner / adversarial terminal reclassification** of this package (e.g. two independent structural blockers). Do not spend another gate on it. | `NEW_PACKAGE_OR_OWNER_GATE_APPROVAL` |
| 4 | `MISSING_BORE_SPAN_SOURCE` | No bore-span source **file** (bore log / bore schedule) is present and the plan alone confirms no span. **Plan-only is not enough.** | `BORE_LOG_OR_BORE_SCHEDULE_NAMING_ONE_SPAN` |
| 5 | `NO_SOURCE_CONFIRMED_SPAN` | A span source **was inspected** but no span could be source-confirmed (no two stations tied as one bore with a start and an end). | `BORE_LOG_OR_BORE_SCHEDULE_NAMING_ONE_SPAN` |
| 6 | `SPAN_SOURCE_FOUND` | A source-confirmed span exists; downstream binding not yet fully verified. | `RUN_ANCHOR_AND_ROUTE_GATES` |
| 7 | `ANCHOR_BLOCKED` | Span found, but a start / end station does not bind to a **unique drawn anchor**. | `OFF_ROUTE_LABEL_BINDER_OR_ROUTE_ATTACHED_ANCHORS` |
| 8 | `ROUTE_BLOCKED` | Span found + anchors bound, but the route between them is not verifiable. | `ROUTE_CONTINUITY_GATE` |
| 9 | `READY_FOR_REVIEW_REDLINE` | Span found + both endpoints anchored + route verified. Ready to **generate** a REVIEW redline downstream. *(This gate still draws nothing.)* | *(none — hand off to the REVIEW generator)* |

### What “a source-confirmed span” means

Two stations tied together as **one bore** by independent printed/source proof — a bore-log / bore-schedule row
carrying `sheet` + `start_ft` + `end_ft`, a printed `Sta X to Y` span callout, or a matchline-boundary
continuation. **Bare stationing ticks and resolved anchors alone are not a source-confirmed span.** This is the
exact distinction that separates a drawable package from a plan-only one.

### `MISSING_BORE_SPAN_SOURCE` vs `NO_SOURCE_CONFIRMED_SPAN`

Both mean “no drawable span yet,” but they are different and separately actionable:

- **`MISSING_BORE_SPAN_SOURCE`** — no span-carrying source **file** was provided, and the plan alone confirms no
  span. The dominant, actionable verdict: *upload a bore log / bore schedule.*
- **`NO_SOURCE_CONFIRMED_SPAN`** — a span source *was* present and inspected (a file, or the plan’s printed-span
  layer) but nothing confirmed. The report surfaces `NO_SOURCE_CONFIRMED_SPAN` as a contributing reason whenever
  a source was inspected, even if the primary verdict is `MISSING_BORE_SPAN_SOURCE`.

## Doctrine: the classifier never decides to give up

`KEEP_BLOCKED` is an **owner / adversarial decision**, never an autonomous “give up.” Consistent with the
ALL-REDLINES standard (abstention is only an interim safety state with a named target), the classifier:

- honors an explicit owner/adversarial `keep_blocked` reclassification and reports `KEEP_BLOCKED`; and
- computes a `double_structural_block` **advisory** (a package independently blocked at **both** the anchor and
  route stages) that *justifies* an owner `KEEP_BLOCKED` reclassification via `keep_blocked_candidate` — but it
  **never promotes a package to `KEEP_BLOCKED` on its own.** A double-blocked package classifies by stage
  (`ANCHOR_BLOCKED` first) with the advisory raised.

## The four public cold-package findings, as classifications

These reproduce the Track B evidence established in continued 94–102. (Package ids are anonymized runtime data.)

| Package | Track B finding | Readiness status | Why |
|---------|-----------------|------------------|-----|
| `public-cold-001` | recognized by a named dialect | `PACKAGE_RECOGNIZED_CONTROL` | deterministic control lane, not the cold pipeline |
| `public-cold-002` | HDD-profile; 0 route-attached anchors resolve (all `AMBIGUOUS_ANCHOR`) | `ANCHOR_BLOCKED` | span present, but no endpoint binds to a unique drawn anchor |
| `public-cold-009` | route-attached anchors **do** bind, but zero printed text ties two stations as one bore + no companion bore log | `MISSING_BORE_SPAN_SOURCE` (contributing: `NO_SOURCE_CONFIRMED_SPAN`) | plan-only; no source file confirms the span — **the blocker is upstream of the anchors** |
| `public-cold-011` | fragmented route **and** off-route labels — two independent structural blockers | `KEEP_BLOCKED` | owner/adversarial terminal reclassification (continued-101) |

`public-cold-009` is the important case: it has route-attached anchors, so it is tempting to treat as “almost
ready.” It is not. **No source file confirms the bore span**, so the honest verdict is `MISSING_BORE_SPAN_SOURCE`
and the next step is “provide a bore log / bore schedule naming one span (`sheet` + `start_ft` + `end_ft`).” This
is the canonical `PACKAGE_009_NEEDS_BORE_LOG` decision, expressed as a product status.

## Evidence inputs (what a caller assembles)

`ReviewReadinessEvidence` is opaque, read-only data — no name, no coordinate, no stroke:

- `plan_readable` — the plan has an extractable text layer (`False` ⇒ OCR needed).
- `recognized` — a named dialect or the recognized-corpus registry matches the plan.
- `keep_blocked` (+ `keep_blocked_reason`) — an owner/adversarial terminal reclassification.
- `span: SpanSourceEvidence` — `bore_span_source_files`, `plan_span_layer_inspected`,
  `source_confirmed_span_count`.
- `anchor: AnchorEvidence` — per-endpoint G-a′ status strings (`None` when not evaluated).
- `route: RouteEvidence` — the G-b / G-b‴ route status string (`None` when not evaluated).

The classifier’s PASS status sets are **test-locked** against the real observer constants
(`test_pass_status_sets_match_the_real_observers`), so an observer vocabulary change cannot silently desync the
traffic controller.

## End-to-end runner (the adapter)

The classifier is hand-fed evidence; the **adapter** turns it into a package → readiness report pipeline, kept in
four cleanly separated seams:

1. **package discovery / input loading** — `truelinev2/harness/readiness_source.py`: `discover_package(folder)`
   (reuses the manifest loader) and `resolve_case_dir(case_id, cold_packages_root)` (a case reference under an
   **injected** root — no hardcoded path or name). It reads any recorded read-only observer outputs from a
   name-free `observer_findings.json` beside `package.json` — the *“observer outputs where already available.”*
2. **observer evidence normalization** — `truelinev2/harness/readiness_adapter.py`: `evidence_from_findings(...)`
   (pure transform of recorded findings) and `evidence_from_live_observers(...)` (the fresh-package seam — lazily
   reads recognition + readability from the plan today; richer live span/anchor/route normalization is wired here
   as real complete packages arrive). The live seam imports **only** the read-only dialect selector + plan reader.
3. **readiness classification** — `classify_review_readiness(...)`.
4. **report serialization** — `format_readiness(...)`.

Composers: `run_readiness_for_folder(folder)` and `run_readiness_for_case(case_id, cold_packages_root)`. The
adapter is read-only and harness-only — it draws nothing, places nothing, promotes nothing, and imports nothing
from renderer / placement / backend / web / product runtime. `KEEP_BLOCKED` is produced only from an explicit
owner/adversarial marker in the recorded findings, never derived autonomously. The four canonical cases reproduce
end-to-end from folders (`test_readiness_adapter.py`).

## How to run (read-only)

```
# from the repo root, repo-root venv + PYTHONPATH (never backend/venv):
PYTHONPATH=. venv/Scripts/python.exe -m pytest truelinev2/tests/test_review_readiness.py -q

# harness-only diagnostic CLI over a JSON evidence file (writes nothing, draws nothing):
PYTHONPATH=. venv/Scripts/python.exe -m truelinev2.harness.review_readiness <evidence.json>

# end-to-end over a package folder (reads a recorded observer_findings.json; --live for a fresh plan):
PYTHONPATH=. venv/Scripts/python.exe -m truelinev2.harness.readiness_adapter <package_dir> [--live]
PYTHONPATH=. venv/Scripts/python.exe -m pytest truelinev2/tests/test_readiness_adapter.py -q
```

## Explicit limits

- No stroke, no REVIEW candidate, no placement, no promotion, no AUTO. `draws_anything` /
  `performs_placement` are always `False`.
- Readiness is not eligibility (see `COLD_PACKAGE_VALIDATION_INTAKE.md`) and it is not AUTO. A
  `READY_FOR_REVIEW_REDLINE` verdict means “ready to *generate* a REVIEW candidate downstream,” not “placed,” and
  never “DETERMINISTIC_AUTO.”
- The classifier is generic and name-free; real project/customer names appear only as runtime data ids.
