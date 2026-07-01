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
  - **G-b‴: route-vs-lateral discriminator** — among the multiple route termini/branches near a station label,
    identify the MAIN run vs short laterals/service drops ONLY when the geometry strongly supports it (continuity,
    length, degree/topology, relation to BOTH source-bound labels + candidate termini); refuse on multiple
    plausible main runs, on a weak distance-only guess, or unsafe topology. Never snap, never a grid/box line.
    Feeds a uniquely-discriminated main run + its two termini back to G-b″/G-b′. Still pre-redline; no stroke.
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

NEXT after G-b″: **G-b‴** (route-vs-lateral discriminator). G-b″ binds a label to a unique route terminus from the
isolated linework, but on the real proof case there are MULTIPLE route termini near each station label (laterals /
service drops in the same un-layered linework), so G-b″ honestly REFUSES (`NO_ISOLATED_ROUTE_ANCHOR` /
`ISOLATED_ROUTE_ANCHOR_AMBIGUOUS`). The gating step is now to distinguish the MAIN run from short laterals — only
when continuity / length / topology / relation to both source-bound labels strongly supports one main run, and to
refuse otherwise (never a distance-only guess, never snapping). A uniquely-discriminated main run then feeds
G-b″/G-b′ for a clean anchor + run, after which a cold REVIEW stroke (G-e) can be drawn. AUTO remains blocked
throughout.
