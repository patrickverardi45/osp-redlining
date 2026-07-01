# Source-Backed Endpoint Binding (MVP) — the ANCHOR stage (read-only)

> Module: `truelinev2/harness/endpoint_binding.py` · Tests: `truelinev2/tests/test_endpoint_binding.py`.
> Consumes the extracted span rows from
> [`SOURCE_SPAN_EXTRACTOR.md`](SOURCE_SPAN_EXTRACTOR.md) and feeds the `AnchorEvidence` seam of
> [`SOURCE_COMPLETENESS_REVIEW_READINESS.md`](SOURCE_COMPLETENESS_REVIEW_READINESS.md). It does **not** draw.

## What this stage is

After a package reaches `SPAN_SOURCE_FOUND` (a source file confirmed a bore span), this stage attempts to bind
each span's **start/end station** to a drawn anchor on the plan, using the existing read-only Track B observers
**verbatim**:

- **G-a** `printed_station_locator.observe_plan_view_endpoints_for_path` → the printed station-**label** status.
- **G-a′** `plan_view_anchor_resolver.resolve_plan_view_anchor_for_path` → the source-backed **anchor** (route
  terminus / structure symbol / leader tip / proximity symbol), or an honest refusal. G-a′ never snaps to the
  nearest passing line.

It is **endpoint binding only** — not route validation, not the G-e REVIEW stroke. It invents no coordinate: any
`(x, y)` on a binding is exactly what the anchor observer exposed.

## Output

`EndpointBinding` per span row: `span_id`, `start_station`, `end_station`, `start/end_label_status`,
`start/end_anchor_status`, `start/end_anchor_method` (evidence type), `start/end_anchor_xy` (observer-exposed
coordinate or None), `bound` (both endpoints resolved), and a `refusal` reason otherwise
(`NO_PLAN_FOR_BINDING` / `LABEL_NOT_LOCATED` / `ANCHOR_NOT_RESOLVED` / `UNREADABLE_PLAN` / `STATION_UNPARSEABLE`).
`EndpointBindingReport` collects the per-span bindings; `PackageAnchorReadiness` bundles the readiness report +
extraction + bindings.

## Readiness transitions (via `run_package_anchor_readiness`)

`anchor_evidence_for_package` reduces the bindings to the `ReviewReadinessEvidence.anchor` seam:

- **anchors resolved** (a span's both endpoints bind) → classifier stays `SPAN_SOURCE_FOUND` at the **ANCHOR**
  stage (anchor-ready; route pending).
- **plan present but no binding resolves** → `ANCHOR_BLOCKED`.
- **no plan / no span to bind** → anchor left unevaluated → stays `SPAN_SOURCE_FOUND` (needs a plan) or the
  upstream span verdict (`MISSING_BORE_SPAN_SOURCE` / `NO_SOURCE_CONFIRMED_SPAN`).
- an owner-`KEEP_BLOCKED` package (e.g. the 011 family) short-circuits before the anchor stage and never becomes
  draw-ready.

## Guardrails

Read-only, harness-only. No AUTO, no REVIEW stroke, no route validation, no renderer, no placement/status, no
`_cap_review`, no web/staging/backend runtime, no fixture mutation, no `origin/main`. Invents no station / bore
row / endpoint coordinate / route geometry / source relationship. `select_dialect` untouched; no
recognized/customer corpus used as cold proof; no private/gitignored source files committed. The observer PASS
status sets are test-locked against the real G-a/G-a′ constants. Imports nothing from
render/placement/api/store/contracts/web/product runtime (a test asserts this).

## How to run (read-only)

```
PYTHONPATH=. venv/Scripts/python.exe -m pytest truelinev2/tests/test_endpoint_binding.py -q
```
