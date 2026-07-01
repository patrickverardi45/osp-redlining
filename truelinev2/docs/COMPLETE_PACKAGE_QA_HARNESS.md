# Generic Complete-Package QA Harness — product QA for the complete-package workflow (read-only)

> Module: `truelinev2/harness/complete_package_qa.py` · Tests: `truelinev2/tests/test_complete_package_qa.py`.
> Exercises the full read-only readiness spine documented in
> [`SOURCE_COMPLETENESS_REVIEW_READINESS.md`](SOURCE_COMPLETENESS_REVIEW_READINESS.md),
> [`SOURCE_SPAN_EXTRACTOR.md`](SOURCE_SPAN_EXTRACTOR.md),
> [`SOURCE_BACKED_ENDPOINT_BINDING.md`](SOURCE_BACKED_ENDPOINT_BINDING.md), and
> [`SOURCE_BACKED_ROUTE_VERIFICATION.md`](SOURCE_BACKED_ROUTE_VERIFICATION.md).

## This is product QA, NOT cold validation

This harness is **not** a cold-corpus proof and must never be described as one. It is **product QA for the
complete-package workflow**: a permanent, generic, name-free **synthetic** "complete package" — shaped like the
kind of complete package a real operator will eventually upload — that lets us verify the whole read-only
FieldRoute spine end to end **without needing any private / customer files**. The plan and bore-log fixtures are
generated deterministically into a caller-supplied directory (a temp dir in tests) and are never committed.

## What it verifies

It builds a package and runs it through the **same** modules the product uses — it composes them verbatim via
`route_verification.run_package_route_readiness`, hard-coding **no** final status (every status is computed by the
real observers):

```
uploaded / source package
  → source-span extractor   (span_extractor.extract_spans_from_folder)     finds span rows
  → endpoint binder         (endpoint_binding.bind_extraction_endpoints)   binds start/end stations
  → route verifier          (route_verification.verify_extraction_routes)  verifies / refuses the drawn run
  → readiness adapter        (readiness_adapter.run_readiness_with_spans)  reports the readiness status
```

## The scenarios (`SCENARIOS`)

| Scenario | Package | Expected readiness | Stage |
|---|---|---|---|
| `complete_ready` | plan (labels + clean route) + bore-log with one source-confirmed span | **`READY_FOR_REVIEW_REDLINE`** | READY |
| `plan_only` | plan only — no bore-log / span-source file | `MISSING_BORE_SPAN_SOURCE` | SPAN_SOURCE |
| `source_no_confirmed_span` | plan + a bore-log table with only a station column — standalone stations, no start/end columns, no bore tie | `NO_SOURCE_CONFIRMED_SPAN` | SPAN_SOURCE |
| `span_labels_missing` | source span confirmed, but the plan's labels do not match the span's stations | `ANCHOR_BLOCKED` | ANCHOR |
| `span_anchors_off_route` | source span + labels, but the route has no terminus at the labels (off-route) | `ANCHOR_BLOCKED` | ANCHOR |
| `span_anchors_route_blocked` | source span + bound anchors, but the drawn route is **forked** / not unique | `ROUTE_BLOCKED` | ROUTE |
| `span_anchors_route_broken` | source span + bound anchors, but the drawn route is **broken** (a wide central gap) — no single run | `ROUTE_BLOCKED` | ROUTE |

The required **positive** case is `complete_ready`; the six **refusal** cases each fail at their correct stage
(the last two are structurally distinct `ROUTE_BLOCKED` paths — a midpoint lateral vs a colinear gap).

## Modular seams

1. **Fixture builder** — `build_complete_package(dir, *, name, labels, route_shape, bore_csv, with_kml)` (+
   `build_plan_pdf`): a deterministic generic plan PDF (station labels + route linework whose termini sit on the
   real word-centres, read from a probe), a bore-log CSV span source, an optional inert route KML, and a name-free
   `package.json`. Route shapes: `clean` (unique run), `passing` (off-route), `forked` / `broken` (no unique run),
   `none`.
2. **Expected manifest** — `QAScenario` + `SCENARIOS`: the build spec + the expected readiness outputs per
   scenario (status, stage, ready, and optionally span-confirmed / any-bound / any-route-ready).
3. **Pipeline runner** — `run_qa_scenario` / `run_all_scenarios`: build the package, drive the real spine, return a
   `QAResult`.
4. **Scenario assertions** — `check_scenario(result, scenario)` → `(ok, mismatches)`, comparing the computed output
   against the expected manifest (reusable outside pytest).
5. **Documentation** — this file.

## UI-facing metadata (`QAResult.ui_summary()`)

For later clickable-dots / detail-drawer work, the summary exposes, per package: the **extracted span rows**
(station start/end, footage, source file / page / kind, confidence, **source citation**, and start/end structure
**only when the source table itself provided them**), the per-span **anchor bindings** (status, evidence method,
observer-exposed `xy`, refusal), the per-span **route verification** (route-ready + the per-observer status
breakdown + refusal), and the **readiness status** / stage / recommended next input.

**No fake depth / BOC.** The readiness spine models neither depth nor BOC, so the summary never fabricates them;
start/end structure appear only when the synthetic source table carries the columns.

## The optional route KML

`with_kml=True` adds a generic `GIS_ROUTE` `route.kml` upload. Because a `.kml` / `GIS_ROUTE` upload is **not** a
span-source kind or extension, the read-only readiness spine provably **ignores** it — a test asserts the readiness
status is identical with and without the KML. No parser / render change is made; KMZ/KML consumption remains the
separate workspace-map lane.

## Guardrails

Read-only, harness-only. No drawing, no REVIEW / redline / route stroke, no G-e, no AUTO, no renderer, no
placement / status behavior change, no `_cap_review`, no web / staging / backend runtime, no fixture mutation of
the committed corpus, no `origin/main`. Invents no station / bore row / endpoint coordinate / route geometry /
source relationship. `select_dialect` untouched; no private / customer files; no committed PNG / proof artifacts.
Name-free (guard covers the module + doc + test). Imports nothing from render / placement / api / store /
contracts / match / web / product runtime (a test asserts this).

## How to run (read-only)

```
PYTHONPATH=. venv/Scripts/python.exe -m pytest truelinev2/tests/test_complete_package_qa.py -q

# harness-only diagnostic CLI (writes fixtures into a scratch dir, draws nothing):
PYTHONPATH=. venv/Scripts/python.exe -m truelinev2.harness.complete_package_qa <scratch_dir>
```
