# Target #25 — AP / Structure-Index Shadow (default-OFF, read-only) — built

**Mission:** pre-join the structure-SIDE facts the Brenham corpus DOES contain into one
deterministic, reusable per-AP index, so the instant a future bore→AP (or bore→structure)
clue appears it resolves to geometry without re-mining the corpus. **It places nothing and
proves nothing about bore↔structure** — Target #24 settled that the join key is absent; this
only assembles the half we already have.

**VERDICT: BUILT — 64-AP index, all 64 geometry-anchor-ready. Pure helper + reusable JSON
artifact, isolated in `scripts/` (no engine import, no flag, no production behavior).**

> Read-only. No placement, no geometry moved, no STATE/flag/engine change. The pure builder
> never feeds resolve / selection / scoring / placement. Lives entirely in `scripts/`.

---

## 1. Index schema (`ap-structure-index-1`, deliverable 1)

Per AP (keyed by AP number), every field sourced from an existing file — never invented:

| field | meaning | source |
|---|---|---|
| `fs_page` | Fiber-Schematic page the AP is documented on | Fieldwire punch-list `AP-NNN .FS NN` register |
| `wp_page` | Work-Package page | Fieldwire `AP-NNN .WP NN` register |
| `station_ft` | DIR.BORE run-terminus station | `BRENHAM_PH5_RUN_ENDPOINTS` (named-AP rows) |
| `print_sheet` | plan sheet that run terminus is on | `BRENHAM_PH5_RUN_ENDPOINTS` |
| `latlon` | Terminal Port Handhole lat/lon | design KMZ point node (numeric name in a "Terminal Port" folder) |
| `kmz_feature_id` / `kmz_folder` | the KMZ node identity | design KMZ |
| `tail_route` | unique Terminal Tail route ending at the AP | `resolve_terminal_tail_route_for_ap` (endpoint-match, no run-length → adjacency only) |
| `coverage` / `sources` | per-field presence + contributing sources | derived |
| `geometry_anchor_ready` | has a KMZ lat/lon (the load-bearing field for resolution) | derived |
| `complete_all_fields` | fs ∧ station ∧ latlon ∧ tail | derived |

`build_ap_structure_index(...)` is a **pure function** (inputs → dict, deterministic, never
raises); the tail resolver is injected so the helper carries no engine import.

## 2. Source coverage table (deliverable 2)

| relation | coverage | note |
|---|---|---|
| **AP universe** | **64** | all KMZ Terminal Port Handhole nodes |
| AP → `.FS` page (Fieldwire) | **63 / 64** | one AP absent from the Fieldwire register |
| AP → station (plan run-end) | **10 / 64** | only the sheet-8–12 DIR.BORE run-terminus APs |
| AP → lat/lon (KMZ node) | **64 / 64** | every AP is geometry-anchor-ready |
| AP → terminal-tail route | **48 / 64** | unique endpoint-matching Terminal Tail |
| **geometry-anchor-ready** | **64 / 64** | a future bore→AP clue resolves to geometry for ANY AP |
| **all four fields** | **8 / 64** | APs 154, 156, 157, 164, 165, 166, 167, 168 |

## 3. Exact gaps — APs by field combination (deliverable 3)

| fields present | # APs | what's missing |
|---|---|---|
| fs + kmz_node + tail | 39 | station (not a plan run terminus) |
| fs + kmz_node + tail + **station** | **8** | nothing — fully populated (154/156/157/164/165/166/167/168) |
| fs + kmz_node | 15 | station + tail |
| fs + kmz_node + station | 1 | tail — **AP-155** (the high-station 3810 AP; no unique tail) |
| kmz_node + tail + station | 1 | `.FS` — the one AP absent from the Fieldwire register |

**Key takeaway:** lat/lon coverage is **total (64/64)** — the index can geolocate any AP the
moment something points a bore at it. Station coverage is sparse (10/64) because only plan
run-terminus APs carry a station; that's expected and is exactly the bore↔structure gap
Target #24 named (and which this index does NOT pretend to close).

## 4. Helper + probe output (deliverable 4)

- Pure helper: `scripts/ap_structure_index.py::build_ap_structure_index` (no I/O, deterministic).
- Reusable artifact: `scripts/ap_structure_index.json` (the 64-AP index — the thing future
  clues consult instead of re-mining the corpus).
- Coverage dump: `scripts/ap_structure_index.out`.
- Self-test: `python scripts/ap_structure_index.py selftest` → `SELFTEST_OK` (determinism,
  schema, abstain-when-no-node, terminal-port-only filtering, tail-free placement-safety).

Sample record (verbatim):
```json
"157": {"ap":157,"fs_page":8,"wp_page":null,"station_ft":413.0,"print_sheet":8,
        "latlon":[30.15819526755925,-96.38598520451443],
        "kmz_feature_id":"point_567","kmz_folder":"Nodes / Terminal Port Handhole",
        "tail_route":"route_465","coverage":{"fs":true,"station":true,"latlon":true,"tail":true},
        "geometry_anchor_ready":true,"complete_all_fields":true}
```

## 5. Safety posture

- **Placement-free:** the tail field uses endpoint-match only (no run-length), so it is an
  *adjacency* fact, not a placement; nothing here moves or proposes a redline.
- **Isolated / default-OFF by construction:** the module lives in `scripts/`, is never
  imported by the engine, wires no flag, and touches no STATE — there is no production path to
  turn on. It is dormant infrastructure, exactly per the Target #24 closing recommendation.
- **No bore↔structure claim:** the index is the structure half only; it does NOT assert any
  bore is placeable (Target #24 invariant respected).

## 6. Next unlock

The index makes **every one of the 64 APs instantly geometry-resolvable**. The single
remaining edge is unchanged: **bore → AP** (or bore → `.FS`/structure). The moment ONE such
clue arrives — a `.FS` page set, an OCR/structure field on a bore log, or a future corpus that
names a bore's AP — that bore resolves to lat/lon (+ tail route, + station, + `.FS` page)
through this index with zero re-mining. This is the catcher waiting for that edge; building
the placement step is gated on the edge existing (DO-NOT-WIDEN / no-overbuild). Proven lane
unchanged (bore_log7 → route_469); all production flags default-OFF.

## 7. Files read
- `BRENHAM_PH5_RUN_ENDPOINTS`, `resolve_terminal_tail_route_for_ap` ([pdf_ap_route_resolver.py](backend/app/core/pdf_ap_route_resolver.py)) — read.
- `_build_kmz_reference` ([main.py:1537](backend/main.py#L1537)) on the design-identical KMZ fixture — read.
- `backend/uploads/project_route_context/brenham-phase-5.json` (route_catalog) — read.
- `BRENHAM_PHASE_5_New_report_…03-23.pdf` (Fieldwire AP→.FS/.WP register) — read.
- Prior: Targets #20 (KMZ taxonomy), #22 (station anchor), #24 (corpus join-key absence).
