# Source-Backed Route Verification (MVP) — the ROUTE stage after anchor-ready (read-only)

> Module: `truelinev2/harness/route_verification.py` · Tests: `truelinev2/tests/test_route_verification.py`.
> Consumes the bound anchors from
> [`SOURCE_BACKED_ENDPOINT_BINDING.md`](SOURCE_BACKED_ENDPOINT_BINDING.md) and feeds the `RouteEvidence` seam of
> [`SOURCE_COMPLETENESS_REVIEW_READINESS.md`](SOURCE_COMPLETENESS_REVIEW_READINESS.md). It does **not** draw.

## What this stage is

After a package reaches the **ANCHOR** stage (a source-confirmed span whose start/end stations both bind to a
source-backed drawn anchor — `SPAN_SOURCE_FOUND` at `ANCHOR`), this stage asks one read-only question per span:
**is there a UNIQUE drawn route/run between the two bound anchors?** It answers with the existing read-only Track B
route observers **verbatim**, composed in the established order `isolate → bridge → discriminate`:

- **G-b′** `plan_view_route_isolator.observe_route_isolation` → isolate route-like linework from grid / border /
  annotation between the two anchors (its internal **G-b** run status is carried through).
- **G-b⁗** `route_gap_bridge.bridge_route_gaps` → reconnect colinear route fragments across small dash gaps in the
  isolated linework (a continuity *hypothesis* between real drawn endpoints, never a stroke).
- **G-b‴** `route_main_run.discriminate_main_run` → separate the MAIN run from short laterals and confirm one
  unique backbone whose ENDS are the two anchors.

Crucially, the observers are fed the **bound anchor coordinate** from the ANCHOR stage (the source-backed G-a′
terminus / symbol / leader tip), not the raw printed-label centre. It is **route verification only** — not the G-e
REVIEW stroke, not placement, not AUTO. It invents no coordinate: any `(x, y)` it uses is exactly what the anchor
observer exposed.

## The route-ready rule (two gates, zero-false)

The route is **verified** only when **both** gates pass:

1. the tight **isolation** gate G-b′ → **`ROUTE_LINEWORK_ISOLATED`** (reach_tol 12 pt: the bound anchors are the
   ENDS of a *unique simple* isolated run, grid / border / leader excluded), and
2. the **discriminator** G-b‴ → **`MAIN_ROUTE_DISCRIMINATED`** (the sole verdict the readiness classifier accepts
   as a clean run — `review_readiness.ROUTE_PASS_STATUSES` = `{MAIN_ROUTE_DISCRIMINATED, PLAN_VIEW_RUN_CONNECTED}`).

Requiring **both** closes a radius asymmetry that would otherwise be a false-positive: the discriminator alone uses
`anchor_radius = 50 pt`, so a bound anchor sitting 13–49 pt *off* the drawn route (leader-tip / symbol anchors sit
"16–40 pt off" per the anchor resolver) would pass the discriminator even though isolation rejects it. The tight
isolation gate makes that impossible — a route the isolation gate rejected can never be route-ready. Any other
observer outcome — off-route / forked / lateral-ambiguous / multiple / broken / not-tight / topology-unsafe — is an
honest, **named** refusal that classifies as `ROUTE_BLOCKED`. This is DO-NOT-WIDEN: a conservative refusal is a
safe interim state (the named target is the `ROUTE_CONTINUITY_GATE`), never a wrong redline. The bridge (G-b⁗) and
discriminator outputs also enrich the report and can only *tighten*, never widen, the verdict.

## Output

`RouteVerification` per span row: `span_id`, `start_station`, `end_station`, `start/end_anchor_summary` (the
bound-anchor status + method + observer-exposed `xy`), the canonical `route_observer_status`, the per-observer
breakdown `route_isolation_status` (G-b′) / `route_run_status` (G-b) / `main_run_status` (G-b‴) /
`gap_bridge_status` (G-b⁗), a `route_ready` boolean, an `evaluated` boolean (True only when the observers actually
ran over bound anchors + a readable plan), and a `refusal` reason otherwise (`ANCHOR_NOT_BOUND` /
`NO_PLAN_FOR_ROUTE` / `UNREADABLE_PLAN_ROUTE`, or the observer's own reject status). `RouteVerificationReport`
collects the per-span verifications; `PackageRouteReadiness` bundles the readiness report + extraction + bindings +
route verifications.

## Readiness transitions (via `run_package_route_readiness`)

`route_evidence_for_package` reduces the verifications to the `ReviewReadinessEvidence.route` seam:

- **route verified** (a bound span's run is `MAIN_ROUTE_DISCRIMINATED`) → classifier `READY_FOR_REVIEW_REDLINE`
  (span + both endpoints anchored + route verified; this gate still draws nothing).
- **bound but the run is not verifiable** → `ROUTE_BLOCKED`.
- **no bound anchor to verify** (or no plan) → route left unevaluated (`None`) → the ANCHOR stage's verdict stands
  (`ANCHOR_BLOCKED`, or `SPAN_SOURCE_FOUND` when a plan is simply absent); route verification is **not run** for an
  unbound span.
- an owner-`KEEP_BLOCKED` package (e.g. the 011 family) short-circuits before the anchor / route stages and never
  becomes draw-ready.

`public-cold-009` with no source file stays `MISSING_BORE_SPAN_SOURCE` (the blocker is upstream of the anchors);
with an added source span it reaches the ANCHOR stage, and becomes route-ready **only if** the observers verify the
drawn run between its bound anchors.

## Guardrails

Read-only, harness-only. No AUTO, no REVIEW stroke, no route stroke, no renderer, no placement / status, no
`_cap_review`, no web / staging / backend runtime, no fixture mutation, no `origin/main`. Invents no station / bore
row / endpoint coordinate / route geometry / source relationship. `select_dialect` untouched; no
recognized/customer corpus used as cold proof; no private/gitignored source files committed. The observer route
tolerances are used **verbatim** (DO-NOT-WIDEN). The route PASS status set is test-locked against the real
observer constants. `class_verified` on every observer stays False — a verified run is REVIEW evidence, never a
placement or a drawn redline. Imports nothing from render / placement / api / store / contracts / match / web /
product runtime (a test asserts this).

## How to run (read-only)

```
PYTHONPATH=. venv/Scripts/python.exe -m pytest truelinev2/tests/test_route_verification.py -q
```
