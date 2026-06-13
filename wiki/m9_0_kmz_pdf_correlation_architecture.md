# M9.0: KMZ↔PDF Correlation Architecture (first geo-lane milestone)

Status: **SHIPPED (proof-only); adversarially audited.** The first cross-source
milestone. A v2 KMZ reader + a correlation architecture audit establish WHAT KMZ
evidence exists, the zero-false JOIN KEY, and per-target feasibility. **Zero
bores moved** (zero-false); the M8.27 truth table, the all-58 census, and the
M8.10/M8.11/M8.15/M8.20 contracts are untouched. v2 stays PDF-first — the KMZ
never overrides PDF/source.

Reader: `truelinev2/extract/kmz.py` (pure, **UNWIRED** — no engine consumes it)
Audit: `truelinev2/proof/run_kmz_correlation_audit.py` (G1–G7 + G2b PASS)
Tests: `truelinev2/tests/test_kmz_correlation.py` (12, offline + tracked fixture)
KMZ: `backend/tests/fixtures/brenham_phase5_source_truth.kmz` (tracked; byte-
identical to `data/uploads/Brenham, TX - Phase 5_Design Team.kmz`)

## KMZ assets — FOUND

The Brenham Phase 5 design KMZ exists and is the SAME 1116-feature set the old
monolith used. v2 previously ingested **no** KMZ; this milestone begins the geo
lane. Geo lon/lat, **no stationing**, no ExtendedData (attributes live in an HTML
`<table>` in each `<description>`).

## Feature taxonomy (folder → v2 class)

| KMZ folder | n | geom | class |
|---|--:|---|---|
| Terminal Port Handhole | 64 | Point | `terminal_port_hh` |
| Installer HH | 37 | Point | `installer_hh` |
| Splice HH | 16 | Point | `splice_hh` |
| Flower Pot | 158 | Point | `flower_pot` |
| House / Business / School | 290 / 10 / 1 | Point | drop endpoints |
| **Vacant Pipe** | **58** | LineString | `bore_vacant_pipe` (= bore count) |
| Terminal Tail | 51 | LineString | `bore_port` |
| House Drop / u-g cable / Backbone | 422 / 7 / 1 | LineString | — |

576 structure points + 539 routes. The folder taxonomy maps 1:1 to the PDF lane
dialect classes.

## The zero-false JOIN KEY (the architecture's core)

**Two-field structure-identity agreement** — not geometry, not proximity:

> PDF terminus callout **`AP-NNN SPLICE LOC MM`**  ↔  KMZ `terminal_port_hh`
> with **AP Number = NNN** AND **`Splice Loc MM`**. BOTH ids must agree.

- AP Number is unique across the **64 terminals (0 collisions corpus-wide)**.
- The splice-loc field is **load-bearing**: the same-AP `splice_hh` twin is a
  **DIFFERENT structure 28–181 m away** (control twins: AP-163 = 140 m, AP-105 =
  74 m), and the PDF never prints a "terminal/port" class keyword (every AP
  callout reads `AP-NNN SPLICE LOC MM`). So AP alone is not a point identity; the
  shared splice-loc id binds the SPLICE-labeled PDF callout to the TERMINAL role
  — **earned, not assumed**.
- PROVEN on controls: log7 (`AP-163 SPLICE LOC 46`) and log42 (`AP-105 SPLICE
  LOC 25`) each agree on **both** fields with exactly one KMZ terminal.

The 58 Vacant Pipe routes carry **no** text id/length/endpoints — a route is
reachable only via its endpoint structures (AP-keyed), never a footage/geometry
guess.

> This corrected primitive came from the M9.0 adversarial audit, which flagged an
> earlier draft that called the splice/terminal pair "co-located" and claimed a
> PDF "class keyword" the plan never prints. The two-field join replaces that
> unproven assumption with a checked cross-source agreement.

## Cross-source gate taxonomy

`KMZ_AP_STRUCTURE_JOIN` (the proven primitive) · `KMZ_ENDPOINT_BRIDGE` ·
`KMZ_MATCHLINE_SUBSTITUTE` · `KMZ_ROUTE_CORROBORATION` · `SOURCE_REVIEW_ONLY`.

## Per-target outcome (zero moved now)

| bore | M8.27 bucket | cross-source class | future REVIEW eligible? | blocker |
|---|---|---|---|---|
| log37 | SOURCE_REVIEW_REQUIRED | SOURCE_REVIEW_ONLY | no | source unparseable → no sheets/APs → no join key |
| log38 | SOURCE_REVIEW_REQUIRED | SOURCE_REVIEW_ONLY | no | source unparseable → no join key |
| log43 | SOURCE_OR_KMZ_REQUIRED | SOURCE_REVIEW_ONLY | no | end 59+19 a printed VOID (axis stops 45+33; multi-drive source); sheet-10 APs bind low-station runs |
| log44 | SOURCE_OR_KMZ_REQUIRED | KMZ_ENDPOINT_BRIDGE | **yes — after source 325′ corrected** | terminals AP-145/146/147 ARE in KMZ, but 325′ matches no print-18 run (source-vs-plan); KMZ may not override the source |
| log68 | SOURCE_OR_KMZ_REQUIRED | KMZ_MATCHLINE_SUBSTITUTE | **yes — after both endpoints AP-bind a unique route** | cross-sheet 19↔20, NO printed matchline equation; only one endpoint AP (148) confirmed |

**Future PDF↔KMZ eligible:** log44 (endpoint bridge), log68 (matchline
substitute). **Source-only:** log37, log38, log43.

## Next KMZ engine step

Ship the proven `KMZ_AP_STRUCTURE_JOIN` extractor (two-field, default-OFF), then
`KMZ_MATCHLINE_SUBSTITUTE` for the cross-sheet class — the highest-yield geo
lever: log68 **plus the 7 no-matchline-equation cross-sheet bores** (log10/14/61/
62/67/68/70), and the route-stroke geometry for the log8/log32/log42
structure-identity bores via their KMZ AP terminals (AP-105 is in the KMZ).

## Boundary

Proof-only; the KMZ reader is UNWIRED (no resolve_bore/sweep/service consumes
it). No UI/web/mobile/production/deploy/Render/Vercel; no placement-logic change;
no strokes/PNG/segments; no AUTO; no tolerance widening; KMZ never overrides PDF;
no proximity/geometry-alone identity; no family relation as placement proof.
M8.27 + census + all contracts unchanged; log8/log32/log42 + the M8.20 group
review untouched.
