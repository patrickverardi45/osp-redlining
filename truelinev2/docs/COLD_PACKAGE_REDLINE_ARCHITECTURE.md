# Cold-Package Redline Extraction — Architecture & Roadmap (read-only first)

Senior-engineering plan to make the engine draw correct redlines from REAL cold / non-recognized uploaded
packages. Derived from the public cold-corpus harvest (`PUBLIC_COLD_CORPUS_HARVEST.md` + the gitignored
`data/outputs/truelinev2/cold_packages/_DIALECT_DISCOVERY_REPORT.md`). Name-free: dialect families and grammars
only, never customer/project/place. Every stage below is read-only and evidence-gated; AUTO is the last gate and
stays blocked until a class-verification + proof battery exists.

## The evidence pipeline (plan PDF + bore log → drawn redline)
1. **Recognition gate** — `select_dialect`. Recognized grammar → handled by the named lane (NOT cold proof).
   Unrecognized → cold lane. (DONE; never weakened.)
2. **Endpoint IDENTITY binding** — bind each bore endpoint to a printed source token (station callout /
   structure label / matchline equation). Output: which station each endpoint IS, or a named missing-evidence
   blocker. (PARTIAL.)
3. **Endpoint 2-D POSITION resolution** — turn the bound identity into an (x,y) on the sheet. Two models:
   - *profile sheets*: linear `station = a*x + b` axis → `axis.x_at` (DONE for profile).
   - *plan-view sheets*: the route meanders, so NO linear axis exists; the position is carried by the printed
     LABEL (and, when present, a leader to a structure symbol). ← **THIS GATE.**
4. **Drawn-run reconstruction + verification** — find the drawn run between the two resolved positions and check
   it is THE bore (branch-uniqueness, endpoint tightness, 2-D). (PARTIAL; axis-coupled today.)
5. **REVIEW candidate** — emit a human-adjustable redline stroke between verified endpoints. First actual cold
   redline; always REVIEW, never silent.
6. **AUTO** — only after generic class verification + a negative-battery proof + owner approval. (BLOCKED.)

## Current state mapped to the pipeline
- (1) DONE. (2) PARTIAL — `PRINTED_STA_CALLOUT` binder works on a real plan (proof: cold-011 bound both ends);
  structure-label + matchline binders exist; HDD entry/exit POINT binder MISSING (the largest cold family is
  unbound). (3) GAP — the 2-D resolver is axis-coupled: `observe_terminus_coordinates` projects via
  `axis.x_at` and returns `None`/`NO_STATION_AXIS` on plan-view sheets. (4) PARTIAL — branch/tightness +
  2-D observers exist but project through the axis. (5) the named/generic REVIEW lane exists; cold REVIEW
  emission not built. (6) BLOCKED (`class_verified` always False — correct).

## Per dialect family (generic)
- **B1 Pipeline HDD plan-profile** (largest cold family): endpoints are `HDD ENTRY/EXIT` POINTS, not structures
  → needs a **point-station binder** (stage 2). Linear axis already works (stage 3) — geometry runs but abstains
  on rival runs (proof: cold-002).
- **B2 County/municipal buried-fiber** (`Sta. X to Y` handhole spans): identity binds via `PRINTED_STA_CALLOUT`
  (stage 2 ✓); needs the **plan-view 2-D locator** (stage 3 ← THIS GATE) then **2-D run reconstruction**
  (stage 4). Proof: cold-011.
- **B3 OSP fiber permit (plan-view)** (`VAULT/HANDHOLE/PULLBOX` + `STA N+NN - <ft>' BCF` + `BORE/BORE PIT`):
  needs **structure-symbol binders** + leader-trace (stages 2-3) + per-segment bore extraction between
  consecutive structures.
- **B4 Municipal water-main HDD** (`NNN LF OF HDD` + `Match Line Station`): length-based — needs a
  **length+anchor span resolver** (stage 2) before stage 3.
- **B5 Airport / utility duct** (`STA N+NN.N, <ft>' LT/RT`): offset-station binder (stages 2-3).
- **Scanned / no-text** (~31% of real plans): needs an **OCR / raster ingestion** stage BEFORE stage 1.
- **Recognized grammars**: stay rejected as cold proof (`select_dialect`); never used to claim generalization.

## What must remain abstain / REVIEW (non-negotiable)
Any endpoint not source-bound; ambiguous evidence (fork / rival runs / duplicate label / conflicting source); no
drawn run over the span; no class verification. These ABSTAIN or stay REVIEW. Identity-only binding; never an
invented coordinate, station, or bore value. A located/bound endpoint proves identity + position, NOT that the
drawn line between two endpoints is the bore — that requires stage 4.

## Future gates toward actual drawn redlines (each separately owner-approved)
- **G-a (DONE `78730d5`): plan-view printed-station 2-D locator.** Resolve a bound station to its 2-D position
  via the printed label — no axis. Read-only; strict refusal.
- **G-b (DONE, read-only): 2-D drawn-run verification** between two located anchors — `observe_run_between_anchors`
  classifies the drawn linework into `PLAN_VIEW_RUN_CONNECTED` vs `NO_DRAWN_RUN` / `BROKEN_RUN` /
  `MULTIPLE_PLAUSIBLE_RUNS` / `FORKED_RUN` / `ENDPOINT_NOT_TIGHT` / `UNMEASURABLE`; strict refusal, never draws.
  **Finding on the proof case:** it REFUSES — the located LABEL anchors are 16–40 pt OFF the drawn route and the
  linework has no CAD layer to isolate the route from grid/border/annotation, so a unique connecting run cannot
  be verified (`NO_DRAWN_RUN`→`ENDPOINT_NOT_TIGHT`→`MULTIPLE_PLAUSIBLE_RUNS` as the reach tolerance widens). This
  surfaces two prerequisite gates before stage-4 can verify on real plan-view sheets:
  - **G-a′ (DONE, read-only): plan-view anchor resolver** (`extract/plan_view_anchor_resolver.py`) — upgrade a
    located label to a SOURCE-BACKED anchor in strict priority: leader-traced symbol → leader tip → unique
    nearby symbol → unique route terminus; refuse (`AMBIGUOUS_ANCHOR` / `LABEL_ONLY_NO_ANCHOR` /
    `NO_SUPPORTED_ANCHOR` / `UNMEASURABLE`) on any ambiguity, and NEVER snap to the nearest passing line.
    Reuses the proven `leader_symbol_trace` chain; `class_verified` always False. **Finding on the proof case:**
    it REFUSES (`AMBIGUOUS_ANCHOR`) — both station labels are buried in the permit's grid/table boxes
    (`AMBIGUOUS_LEADER`: each word framed by 3 drawings) with no clean leader/symbol and the route offset, so no
    stronger anchor resolves and G-b cannot improve. This makes **G-b′ the remaining blocker** for this drawing
    style.
  - **G-b′ (DONE, read-only): route-layer isolation** (`extract/plan_view_route_isolator.py`) — separate
    route-like linework from grid/border/table/label-box/leader/annotation linework between two source-supported
    anchors (no CAD layer in the cold lane), then reuse G-b's `observe_run_between_anchors` VERBATIM on the
    isolated set and the full set and compare them to flag a span that exists only through grid/border artifacts:
    `ROUTE_LINEWORK_ISOLATED` (one SIMPLE anchor-to-anchor path, no stub/tail) vs `NO_ROUTE_LINEWORK` /
    `GRID_OR_BORDER_ONLY` / `MULTIPLE_ROUTE_CANDIDATES` / `ROUTE_ENDPOINT_NOT_TIGHT` / `ROUTE_LAYER_AMBIGUOUS` /
    `UNMEASURABLE`; refusal-first (never strips cycles, never snaps); `class_verified` always False.
    **Finding on the proof case:** it excludes the grid boxes (8) + word-attached leader/tick segments (~400) and
    isolates ~118 route segments, IMPROVING the diagnosis from raw grid-polluted `MULTIPLE_PLAUSIBLE_RUNS` to the
    more precise `ROUTE_LAYER_AMBIGUOUS` — but still REFUSES: the printed-label anchors are ~16–41 pt off the
    drawn route and the route region still forks (laterals in un-layered linework). The isolated route segments
    are the read-only input the NEXT gate consumes.
  - **G-b″ (DONE, read-only): isolated-route → anchor composition** (`extract/isolated_route_anchor.py`) — bind
    each printed station label to a UNIQUE drawn route TERMINUS (a degree-1 run end) from G-b′'s isolated linework
    (never the nearest point on a passing line, never a grid/box line), then re-verify the run between the two
    improved anchors via G-b′: `ISOLATED_ROUTE_ANCHOR_RESOLVED` vs `ISOLATED_ROUTE_ANCHOR_AMBIGUOUS` /
    `ISOLATED_ROUTE_ANCHOR_NOT_TIGHT` / `NO_ISOLATED_ROUTE_ANCHOR` / `ROUTE_ISOLATION_REQUIRED` /
    `ROUTE_STILL_AMBIGUOUS` / `UNMEASURABLE`; refusal-first; `class_verified` always False.
    **Finding on the proof case:** labels still locate + the route still isolates, but stronger anchors DON'T
    resolve — there are MULTIPLE route termini near each label (2–6 as the search radius widens), i.e. laterals /
    service drops drawn in the same un-layered linework. Honest refusal.
  - **G-b‴ (DONE, read-only): route-vs-lateral discriminator** (`extract/route_main_run.py`) — over the isolated
    route segments, find the single connected component reaching BOTH labels, require it ACYCLIC (a cycle/mesh →
    `ROUTE_TOPOLOGY_UNSAFE`), take the backbone = longest terminus-near-A → terminus-near-B path, and declare a
    main run only when every off-backbone branch is short RELATIVE to the backbone AND the labels sit at the
    backbone ends: `MAIN_ROUTE_DISCRIMINATED` vs `MULTIPLE_MAIN_ROUTE_CANDIDATES` / `ROUTE_LATERAL_AMBIGUOUS` /
    `NO_MAIN_ROUTE` / `MAIN_ROUTE_ENDPOINT_NOT_TIGHT` / `ROUTE_TOPOLOGY_UNSAFE` / `UNMEASURABLE`. Topology +
    relative length only; never an absolute-distance guess, never a snap; `class_verified` always False.
    **Finding on the proof case:** the main run CANNOT be discriminated — the isolated route is FRAGMENTED into 43
    disconnected components with no connected spine between the stations (radius 30 → `NO_MAIN_ROUTE`, 43
    components / 0 spanning). This is a route-CONTINUITY problem, not a lateral problem.
  - **G-b⁗ (DONE, read-only): route-continuity / dash-gap bridge** (`extract/route_gap_bridge.py`) — reconnect
    colinear route fragments across SMALL gaps only between degree-1 endpoints that are close + near-colinear +
    directionally consistent + different-component + a UNIQUE MUTUAL choice; refuse on ambiguous / too-wide /
    non-colinear / loop-closing / unsupported bridges: `ROUTE_GAPS_BRIDGED` / `NO_ROUTE_GAPS` vs
    `ROUTE_GAP_AMBIGUOUS` / `ROUTE_GAP_TOO_WIDE` / `ROUTE_GAP_NOT_COLINEAR` / `ROUTE_BRIDGE_TOPOLOGY_UNSAFE` /
    `ROUTE_BRIDGE_NOT_SUPPORTED`. Runs BEFORE G-b‴; bridge segments are in-memory continuity hypotheses (flagged
    `"bridge": True`), never strokes; `class_verified` always False.
    **Finding on the proof case:** the conservative default REFUSES (`ROUTE_GAP_TOO_WIDE`); a wide setting adds 6
    safe colinear bridges (43→37 components) but the route stays fragmented, so G-b‴ still finds no spine — the
    fragmentation is STRUCTURAL, beyond conservative dash-gap bridging.
  - **Fragmentation diagnostic (DONE, read-only): investigation, not a placement gate**
    (`extract/route_fragment_diagnostic.py`) — `diagnose_route_fragmentation(...)` measures component breakdown,
    gap taxonomy, G-b′ over-exclusion, curvature, vector density (raster proxy), and main-run reachability, and
    recommends ONE next gate (`READY_FOR_DISCRIMINATION` / `GB_PRIME_EXCLUSION_TUNING` / `CURVE_AWARE_BRIDGE` /
    `ROUTE_FRAGMENT_RECOVERY` / `RASTER_OCR_LANE` / `KEEP_BLOCKED` / `UNMEASURABLE`); reclassifies/bridges/draws
    nothing; `class_verified` always False.
    **Finding on the proof case:** over-exclusion 0, curvature 0, 552 dense vectors (not raster); recommendation
    `ROUTE_FRAGMENT_RECOVERY` (12 colinear connectors just beyond the safe window) — BUT `near_start=0` /
    `main_candidates=0`: the printed labels sit OFF the drawn route. Two independent blockers.
  - **cold-011 = ADVERSARIAL `KEEP_BLOCKED`** (structural fragmentation + off-route labels). Kept as a regression
    case, NOT deleted; no further algorithmic gate is spent on it unless the same blocker recurs on a better
    package or the owner approves. The first cold REVIEW redline should be pursued on a better second package.
  - **Second real cold-package validation (DONE, read-only): lead candidate = `public-cold-009` (B3 OSP);
    decision `PACKAGE_009_NEEDS_BORE_LOG`.** An anchorability probe across the packaged + cold candidates found:
    001 recognized (odot, ineligible); 002 (B1 HDD) + 011 (B2 fiber) resolve 0 route-attached anchors (all
    `AMBIGUOUS_ANCHOR` — labels in callout tables/points off the route); **`public-cold-009` is the ONLY probed
    cold package where G-a′ binds real drawn anchors** — STA 08+00 → `ANCHOR_RESOLVED_TO_SYMBOL` (proximity vault
    symbol), STA 07+62 → `ANCHOR_RESOLVED_TO_ROUTE_ENDPOINT` (route terminus). BUT a name-redacted source scan of
    009 found ZERO printed text tying two stations as one bore (0 two-station lines / 0 station+BORE-footage / 0
    station+structure); the page-2 stations are bare stationing-ruler ticks; BORE/VAULT are page-1 legend entries.
    Per DO-NOT-INVENT, no span is source-confirmed → **`PACKAGE_009_NEEDS_BORE_LOG`** (anchors exist; span identity
    missing). NEXT: obtain 009's bore log / a B3 package that ships a bore log (per-bore sheet/start_ft/end_ft),
    then run the chain end-to-end — the shortest path to a first cold REVIEW redline with NO new algorithm.
- **G-c: HDD entry/exit POINT-station binder** — binds B1 (the largest cold family).
- **G-d: structure-symbol binders for OSP** (vault / handhole / pullbox) + wire leader-trace — binds B3.
- **G-e: cold REVIEW candidate emission** — draw the human-adjustable stroke between verified endpoints. First
  real cold redline (REVIEW).
- **G-f: OCR / raster ingestion** — rescue the scanned/no-text family.
- **G-z: AUTO** — only after generic class verification + the negative battery + owner approval. Stays blocked.

## Why G-a is the chosen first gate (not generic linear-axis fitting)
The harvest's proof case `public-cold-011` bound BOTH endpoints via `PRINTED_STA_CALLOUT` but failed geometry
with `NO_STATION_AXIS`. The tempting read is "fit a better linear axis." That is the wrong fix: inspection of
the sheet shows three printed station tokens that are **non-collinear** (one sits at high-x / low-station), i.e.
a meandering PLAN-VIEW route for which a linear `station = a*x + b` axis **does not exist**. `NO_STATION_AXIS` is
therefore CORRECT, not a weak fit. A better linear fitter would only help PROFILE sheets (B1 pipeline), which
already run and are not the product domain. The product domain is plan-view OSP/fiber (B2/B3) — exactly where the
linear model fails. G-a supplies the missing primitive the axis was standing in for: resolve a bound station to
its 2-D position from the printed label directly. It is the foundation stage-4 (G-b) builds on, and it unblocks
the proof case + the product domain.

### G-a as built (`extract/printed_station_locator.py`, read-only observer)
- `locate_printed_station(words, station_ft)` → the printed label word whose value equals the station, returning
  its display-space centre. Identity match (never nearest); refuses on zero (`NO_PRINTED_STATION_LABEL`) or
  multiple (`AMBIGUOUS_STATION_LABEL`) matches; never invents or snaps.
- `observe_plan_view_endpoints(plan, sheet, start_ft, end_ft, ...)` → locate both source-bound endpoints; an
  unbound endpoint is `NOT_SOURCE_BOUND`; reports the two 2-D anchors + their printed-label separation;
  `class_verified` ALWAYS False (never unblocks AUTO).
- Imports only the read-only `PlanPdf` reader + pure station parsing; touches NO contracts / match / render /
  api / store / placement / `_cap_review`; no axis dependency. Proven on the real cold-011 plan (both endpoints
  located in 2-D where the axis observer returned `NO_STATION_AXIS`) and by name-free synth tests including a
  non-collinear layout where a linear axis provably cannot fit.

NEXT after the diagnostic: **SECOND real cold-package validation**. The diagnostic did its job — it proved cold-011
has TWO independent blockers (structural route fragmentation + printed labels that sit OFF the drawn route,
`near_start=0` / `main_candidates=0`), ruled out over-exclusion / curvature / raster, and recommended
`ROUTE_FRAGMENT_RECOVERY` for the route spine. But cold-011 is now treated as an ADVERSARIAL `KEEP_BLOCKED`
regression case — do not keep chasing one hostile PDF. The product goal is drawing correct redlines from source
files, so the next step is to run the EXISTING evidence chain against a better second eligible fresh non-recognized
package (route-attached labels + visible route) to learn whether a first honest cold REVIEW redline (G-e) is one
gate away, or whether a different next gate (fragment recovery / off-route-label binding / OCR) is decisive there
too. Only once a connected, label-reaching, discriminated main run exists does G-e become reachable. AUTO remains
blocked throughout.
