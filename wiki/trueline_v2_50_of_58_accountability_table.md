# TrueLine v2 — 58-Log Accountability Table (50/58 drawn)

> **READ-ONLY LEDGER.** This is an accounting of the current status of every bore log — not a
> rescue attempt. No engine/renderer/fixture/anchor/corpus/census mutation. No redline generated.
> No commit/push/deploy. Generated 2026-06-19 (continued-34 arc).

## Provenance / state at time of ledger

| Field | Value |
|---|---|
| Branch | `feat/truelinev2` |
| Local HEAD | `94d42ad` (continued-34 docs save) |
| Render commit | `c19b565` (log3 wired + drawn) |
| `origin/feat/truelinev2` | `94d42ad` (pushed; 0 ahead / 0 behind) |
| `origin/main` | `068a279` (untouched) |
| Deploy | none |
| Drawn frontier | **50 / 58** |

## How "drawn" was determined (authoritative source)

The parent model's `placement_status` field is **NOT** the drawn truth — it lags the gated sweep
renders (e.g. `log3`, `log42`, `log44`, `log30` all read `BLOCKED_OR_UNATTEMPTED`/`HELD` in
`parent_source_model.json` yet are drawn). The authoritative drawn set is the union of two constants
in `truelinev2/proof/run_callout_route_assembly_sweep.py`, asserted by
`truelinev2/tests/test_callout_route_assembly_sweep.py`:

- `ALREADY_DRAWN` (13) — drawn in prior render lanes before the callout-route-assembly sweep.
- `NEW_TARGETS` (37) — drawn by the current callout-route-assembly sweep.
- `DUPLICATE_OF_DRAWN = ()` — empty.

**Frontier = `ALREADY_DRAWN` ∪ `NEW_TARGETS` = 13 + 37 = 50.** The rendered-PNG artifacts in
`truelinev2/render/` are produced only under the env-gated heavy e2e (`TL2_TRY_DRAW_E2E=1`), so the
PNGs on disk are not the census of record; the constants above are.

## Bucket summary (reconciles to 58)

| Bucket | Count | Logs |
|---|---|---|
| `DRAWN_REDLINE` | **50** | all logs except the 8 below |
| `COVERED_BY_EXISTING_REDLINE` | **1** | log14 (covered by drawn log10) |
| `OWNER_LOCKED_ABSTAIN` | **4** | log5, log31, log38, log43 |
| `SOURCE_GAP_BLOCKED` | **2** | log15, log16 |
| `MISSING_SOURCE_SHEET_BLOCKED` | **1** | log57 |
| **TOTAL** | **58** | 50 + 1 + 4 + 2 + 1 = 58 ✓ |

- Drawn count: **50**
- Covered (accounted, no new stroke): **1**
- Genuinely-open non-drawn (named blockers): **7** (4 owner-locked + 2 source-gap + 1 missing-sheet)

## Master table — all 58 logs

Sorted by log id. `parent` = original handwritten bore-log family (`parent_source_model.json`).
Spans/sheets are the corpus `truth_span` / `truth_sheets`. Drawn-lane mechanism is in the next
section; blocker detail for the 8 non-drawn is below that.

| log | parent | role | span | sheet(s) | bucket | drawn lane / blocker |
|---|---|---|---|---|---|---|
| log2 | bore_log2 | standalone | 12+22→20+71 | 18,19 | DRAWN_REDLINE | cross-sheet mainline (partner-sheet boundary + end-symbol) |
| log3 | bore_log3 | standalone | 12+63→21+63 | 3,4,5 | DRAWN_REDLINE | **owner-confirmed GEOMETRY (human-adjustable lane)** |
| log4 | bore_log4 | standalone | 15+13→21+63 | 3,4,5 | DRAWN_REDLINE | fiber-MAIN N-leg (first fiber render) |
| log5 | bore_log5 | standalone | 2+65→5+00 | 12 | OWNER_LOCKED_ABSTAIN | `must_remain_abstained` / `ABSTAIN_NO_SAFE_SOURCE` |
| log6 | bore_log6 | standalone | 0+00→2+43 | 5,17,21 | DRAWN_REDLINE | cross-sheet through-continuity (off-sheet start) |
| log7 | bore_log7 | standalone | 0+55→4+51 | 10 | DRAWN_REDLINE | prior render lane (ALREADY_DRAWN) |
| log8 | bore_log8 | standalone | 0+00→3+90 | 18,22 | DRAWN_REDLINE | cross-sheet drop (standard 2-leg; distinct from log32) |
| log9 | bore_log9 | standalone | 4+94→11+69 | 14 | DRAWN_REDLINE | owner-direction-corrected (combined-label matchline) |
| log10 | bore_log10 | standalone | 0+58→7+30 | 15 | DRAWN_REDLINE | owner-reviewed clean promotion (cross-sheet) |
| log11 | bore_log11 | standalone | 0+00→6+50 | 5,17 | DRAWN_REDLINE | cross-sheet 2-leg |
| log12 | bore_log12 | standalone | 5+50→10+92 | 3 | DRAWN_REDLINE | cross-sheet 2-leg (AP-terminus end, AP-121) |
| log14 | bore_log14 | standalone | 0+00→4+18 | 7 | COVERED_BY_EXISTING_REDLINE | duplicate of drawn log10 — no separate stroke |
| log15 | bore_log15 | standalone | 24+07→31+00 | 6,7,8 | SOURCE_GAP_BLOCKED | unprinted ruler-cut head-end (→ sheet-5+) |
| log16 | bore_log16 | standalone | 31+00→39+79 | 8,9,10 | SOURCE_GAP_BLOCKED | unprinted ruler-cut head-end (log15 continuation) |
| log19 | bore_log19 | standalone | 4+94→11+50 | 14 | DRAWN_REDLINE | cross-sheet drop-terminus |
| log23 | bore_log23 | standalone | 2+36→5+57 | 8 | DRAWN_REDLINE | owner-direction-corrected (combined-label matchline) |
| log25 | bore_log25 | standalone | 3+14→6+63 | 21 | DRAWN_REDLINE | prior render lane (ALREADY_DRAWN) |
| log27 | bore_log27 | standalone | 7+30→13+55 | 15,16 | DRAWN_REDLINE | cross-sheet (matchline-typo + end-symbol bind) |
| log29 | bore_log29 | standalone | 0+00→4+15 | 10 | DRAWN_REDLINE | cross-sheet 2-leg (source-derived class) |
| log30 | bore_log30 | standalone | 0+00→5+00 | 10,12 | DRAWN_REDLINE | cross-sheet drop-terminus (parallel-crossing chain-reach) |
| log31 | bore_log31 | standalone | 0+00→2+60 | 10 | OWNER_LOCKED_ABSTAIN | `must_remain_abstained` / `ABSTAIN_NO_SAFE_SOURCE` |
| log32 | bore_log32 | standalone | 0+00→2+13 | 18,22 | DRAWN_REDLINE | cross-sheet drop (printed-distance origin discriminator) |
| log36 | bore_log36 | standalone | 0+56→1+45 | 17 | DRAWN_REDLINE | single-sheet (sheet source-derived) |
| log37 | bore_log37 | standalone | 3+50→4+08 | 23 | DRAWN_REDLINE | owner-reviewed clean promotion (single-sheet) |
| log38 | bore_log38 | standalone | 0+62→16+21 | 25,27 | OWNER_LOCKED_ABSTAIN | `must_remain_abstained` / `ABSTAIN_NO_SAFE_SOURCE` |
| log39 | bore_log39 | standalone | 10+00→14+41 | 25 | DRAWN_REDLINE | owner-reviewed clean promotion (cross-sheet) |
| log41 | bore_log13 | child (Seg A) | 0+00→0+44 | 1,2 | DRAWN_REDLINE | reset-to-reset single-sheet across-street |
| log42 | bore_log13 | child (Seg B) | 0+00→2+87 | 1,2 | DRAWN_REDLINE | owner-corrected end AP-105 (sibling-shared-trunk) |
| log43 | bore_log17 | child (Seg A) | 40+00→59+19 | 10 | OWNER_LOCKED_ABSTAIN | `must_remain_abstained` / `ABSTAIN_NO_SAFE_SOURCE` |
| log44 | bore_log17 | child (Seg B) | 0+00→3+25 | 18→[10,13]* | DRAWN_REDLINE | owner-corrected footage-tick (Woodson; sheet remap) |
| log45 | bore_log18 | child (Seg A) | 43+56→44+89 | 10 | DRAWN_REDLINE | prior render lane (ALREADY_DRAWN) |
| log46 | bore_log18 | child (Seg B) | 0+00→5+34 | 10,13,14 | DRAWN_REDLINE | N-leg 3-sheet (through-continuity unique) |
| log47 | bore_log18 | child (Seg C) | 3+25→4+94 | 10–15 | DRAWN_REDLINE | cross-sheet 2-leg |
| log48 | bore_log20 | child (Seg A) | 0+00→5+09 | 10,12* | DRAWN_REDLINE | owner-confirmed plan route (corrupted-adj override) |
| log49 | bore_log20 | child (Seg B) | 44+89→45+33 | 10 | DRAWN_REDLINE | single-sheet (start-label-context bind) |
| log50 | bore_log20 | child (Seg C) | 0+00→5+14 | 10,11 | DRAWN_REDLINE | prior render lane (ALREADY_DRAWN) |
| log51 | bore_log21 | child (Seg A) | 0+00→2+99 | 8 | DRAWN_REDLINE | prior render lane (ALREADY_DRAWN) |
| log52 | bore_log21 | child (Seg B) | 0+98→4+50 | 7,8,9 | DRAWN_REDLINE | prior render lane (ALREADY_DRAWN) |
| log53 | bore_log22 | child (Seg A) | 21+45→24+11 | 5,6 | DRAWN_REDLINE | prior render lane (ALREADY_DRAWN) |
| log54 | bore_log22 | child (Seg B) | 0+00→3+14 | 2,5,6,17,21 | DRAWN_REDLINE | cross-sheet 2-leg (source-derived class) |
| log55 | bore_log22 | child (Seg C) | 0+00→1+69 | 17 | DRAWN_REDLINE | drop-terminus symbol bind (sheet 17) |
| log56 | bore_log22 | child (Seg D) | 0+00→2+76 | 2 | DRAWN_REDLINE | drop-terminus symbol bind (sheet 2) |
| log57 | bore_log24 | child (Seg A) | 0+00→4+13 | 8,10,13 | MISSING_SOURCE_SHEET_BLOCKED | `.FS` drive-decomposition sheet absent |
| log58 | bore_log24 | child (Seg B) | 0+00→2+36 | 8,10,13 | DRAWN_REDLINE | cross-sheet 2-leg |
| log59 | bore_log26 | child (Seg A) | 2+76→4+46 | 21 | DRAWN_REDLINE | prior render lane (ALREADY_DRAWN) |
| log60 | bore_log26 | child (Seg B) | 0+00→1+13 | 15 | DRAWN_REDLINE | clean single-sheet drop |
| log61 | bore_log26 | child (Seg C) | 2+43→4+50 | 6 | DRAWN_REDLINE | bundled-matchline selector (AP-137 left branch) |
| log62 | bore_log26 | child (Seg D) | 0+00→2+01 | 5,6 | DRAWN_REDLINE | bundled-matchline selector (AP-138 right branch) |
| log63 | bore_log28 | child (Seg A) | 0+00→0+56 | 5,17,21 | DRAWN_REDLINE | HH-HH distance-annotation bridge |
| log64 | bore_log28 | child (Seg B) | 0+00→1+00 | 5,17,21 | DRAWN_REDLINE | prior render lane (ALREADY_DRAWN) |
| log65 | bore_log33 | child (Seg A) | 4+51→6+50 | 9,10 | DRAWN_REDLINE | prior render lane (ALREADY_DRAWN) |
| log66 | bore_log33 | child (Seg B) | 0+00→0+55 | 10 | DRAWN_REDLINE | prior render lane (ALREADY_DRAWN) |
| log67 | bore_log34 | child (Seg A) | 0+00→4+14 | 17,19,20 | DRAWN_REDLINE | cross-sheet 2-leg |
| log68 | bore_log34 | child (Seg B) | 4+54→7+21 | 17,19,20 | DRAWN_REDLINE | matchline-terminus (single leg, AP-144 start) |
| log69 | bore_log35 | child (Seg A) | 0+00→4+54 | 17,19,20 | DRAWN_REDLINE | prior render lane (ALREADY_DRAWN) |
| log70 | bore_log35 | child (Seg B) | 0+00→2+15 | 17,19,20 | DRAWN_REDLINE | owner-confirmed plan route (L-turn up Eledra) |
| log71 | bore_log40 | child (Seg A) | 0+00→6+95 | 23,24 | DRAWN_REDLINE | prior render lane (ALREADY_DRAWN) |
| log72 | bore_log40 | child (Seg B) | 7+50→10+00 | 24 | DRAWN_REDLINE | owner-reviewed clean promotion (single-sheet) |

\* `log44` corpus "print 18" was owner-verified as a sheet mis-map → drawn sheets [10,13]. `log48`
drawn route is sheets [10,12] (its corpus context lists [10,11,12]); see stored-anchor debt note.

> Note on numbering: log ids are not 1..58 contiguous. Split-family parents (`bore_log13/17/18/20/21/22/24/26/28/33/34/35/40`)
> renumbered their children into the log41..log72 range, so `log1, log13, log17, log18, log20, log21,
> log22, log24, log26, log28, log33, log34, log35, log40` do not exist as child log ids. The 58 child
> ids above are the complete census (26 standalone parents + 32 split-family children = 58).

## Drawn-50 roster by source (cross-check)

**`ALREADY_DRAWN` (13)** — prior render lanes:
`log7, log25, log45, log50, log51, log52, log53, log59, log64, log65, log66, log69, log71`

**`NEW_TARGETS` (37)** — current callout-route-assembly sweep:
`log2, log3, log4, log6, log8, log9, log10, log11, log12, log19, log23, log27, log29, log30, log32,
log36, log37, log39, log41, log42, log44, log46, log47, log48, log49, log54, log55, log56, log58,
log60, log61, log62, log63, log67, log68, log70, log72`

13 + 37 = **50**, with no element in both sets and none equal to any of the 8 non-drawn → no double count.

## Non-drawn detail (the 8 accounted, non-DRAWN logs)

For each: exact blocker, what source/owner input unlocks it, and why it must not be drawn yet.

### `COVERED_BY_EXISTING_REDLINE` (1)

**log14** — bore_log14, span 0+00→4+18, sheet 7.
- **Blocker name:** `covered_by_existing_redline` (confirmed duplicate of drawn log10).
- **Status:** Its only bindable s7 route IS drawn log10's first leg (reset `0+58=0+00`, run `0+00→4+16`);
  the end `4+18` is unprintable and `solve_log` is BLOCKED. Adjudicated read-only in continued-33.
- **Unlock:** none required — it is **not a missing redline**. The physical bore is already on the
  plan as log10's stroke.
- **Why not drawn:** drawing it would place a **second, duplicate** stroke over log10. The
  ALL-REDLINES standard counts the relationship as already placed (effective denominator ≈ 57).

### `OWNER_LOCKED_ABSTAIN` (4)

All four carry `adj_status: ABSTAIN_NO_SAFE_SOURCE` in `parent_source_model.json` and are owner-locked
`must_remain_abstained` per START_HERE. The engine is forbidden from auto-placing them.

| log | parent | span | sheet(s) | unlock requirement | why not drawn |
|---|---|---|---|---|---|
| log5 | bore_log5 | 2+65→5+00 | 12 | owner lifts the abstain + supplies a safe, source-backed endpoint identity | owner has locked it ABSTAIN — auto-placing would violate DO-NOT-WIDEN |
| log31 | bore_log31 | 0+00→2+60 | 10 | owner lifts the abstain + supplies a safe source relationship | owner-locked ABSTAIN; no safe source to bind either end |
| log38 | bore_log38 | 0+62→16+21 | 25,27 | owner lifts the abstain + supplies safe source for the long (≈1559') run | owner-locked ABSTAIN; cross-sheet long run with no safe bind |
| log43 | bore_log17 | 40+00→59+19 | 10 | owner lifts the abstain; resolve the 43+00→45+86 gap / 59+19 continuation | owner-locked ABSTAIN; possible missed intermediate rows / prior-day continuation |

### `SOURCE_GAP_BLOCKED` (2)

| log | parent | span | sheet(s) | blocker name | unlock requirement | why not drawn |
|---|---|---|---|---|---|---|
| log15 | bore_log15 | 24+07→31+00 | 6,7,8 | unprinted ruler-cut head-end | the sheet-5+ head-end source where the cut is printed | start is an **unprinted ruler-cut** — no source coordinate to bind; guessing would invent geometry |
| log16 | bore_log16 | 31+00→39+79 | 8,9,10 | unprinted ruler-cut head-end (log15 continuation) | same sheet-5+ head-end source | downstream continuation of log15's unprinted cut — same missing-source bind |

### `MISSING_SOURCE_SHEET_BLOCKED` (1)

| log | parent | span | sheet(s) | blocker name | unlock requirement | why not drawn |
|---|---|---|---|---|---|---|
| log57 | bore_log24 | 0+00→4+13 | 8,10,13 | `.FS` drive-decomposition sheet absent | the missing `.FS` drive sheet that decomposes this drive | the source sheet that defines the route is **not present in the corpus** — nothing to extract from |

## log3 accounting (mission item 8)

- **Status:** **DRAWN** (`c19b565`, continued-34). 50th drawn bore.
- **Provenance:** **owner-confirmed / human-adjustable GEOMETRY** — the first time owner-supplied
  geometry (not just endpoint identity) entered the production render path. Classified by Patrick as
  the human-adjustable lane, **NOT deterministic AUTO**.
- **Rendered (new content):** upstream ≈250' — s2 `12+63 FLOWER POT` stub (≈2.8', source-traced) +
  s3 `12+66→15+13` (≈247', straight segment between two source-bound endpoints; matchline crossing @
  owner top-y → `15+13 NEXTLINK HH`; 11 owner control points, maxdev ≤ 1.3 pt).
- **Downstream `15+13→21+63` (650'):** **COVERED by the already-drawn log4** (parent/child coverage
  exception); not re-stroked. Overlap with log4 = 0 (shared `15+13` junction only).
- **Why it is geometry, not AUTO:** the s3 conduit is too fragmented to auto-trace
  (`DESIGN_PATH_NOT_CONNECTED`); the owner confirmed the track + straightness, so the engine drew the
  minimal straight segment between BOUND endpoints — not a freehand polyline, not census/AUTO.

## log14 accounting (mission item 9)

- **Status:** **COVERED by drawn log10** (`COVERED_BY_EXISTING_REDLINE`).
- **No duplicate stroke:** log14's physical route is already on the plan as log10's first leg
  (`0+58=0+00`, `0+00→4+16`). Drawing log14 would duplicate log10. Counted as covered/accounted,
  **not** as drawn and **not** as a missing-redline blocker.

## No-double-count verification (mission item 10)

- Each of the 58 child log ids appears in **exactly one** bucket (every row above has one bucket).
- **Drawn (50)** = `ALREADY_DRAWN` (13) ⊎ `NEW_TARGETS` (37); the two sets are disjoint and neither
  intersects the 8 non-drawn.
- **log14** is counted once, as `COVERED_BY_EXISTING_REDLINE` — it is **not** in the drawn 50 and
  **not** in any blocker bucket. log10 (the covering redline) is counted once, as `DRAWN_REDLINE`.
  → one physical stroke, two distinct accountability rows, no double stroke.
- **log3 / log4** are both `DRAWN_REDLINE` (distinct bores, 0' overlap, shared junction only). log3's
  downstream coverage by log4 does **not** add a stroke to log4's count — log4 is counted once.
- **Blockers (7)** remain named blockers (4 owner-locked + 2 source-gap + 1 missing-sheet); none is
  silently rolled into "drawn" or "covered".

## Validation checklist

- [x] `50 DRAWN_REDLINE`
- [x] `1 COVERED_BY_EXISTING_REDLINE` (log14)
- [x] `4 OWNER_LOCKED_ABSTAIN` (log5, log31, log38, log43)
- [x] `2 SOURCE_GAP_BLOCKED` (log15, log16)
- [x] `1 MISSING_SOURCE_SHEET_BLOCKED` (log57)
- [x] total = `58` (50 + 1 + 4 + 2 + 1)
- [x] drawn frontier remains `50/58`
- [x] log14 counted as covered, not missing
- [x] no code changes; no render artifacts changed; no census mutation
- [x] this is the only file written

## Related stored-anchor debt (informational, not a bucket)

`log48` (stored adjudication `5+14` is corrupted — carries sibling log50's value) and `log70`
(superseded `1+45`) render correctly via gated owner-confirmed overrides, but their **stored fixture
values are still wrong** and should be repaired under a future census re-baseline
(`B-DATA-LOG48-ADJ-1`). This does not change their `DRAWN_REDLINE` accounting.

---
*Sources: `truelinev2/proof/run_callout_route_assembly_sweep.py` (`ALREADY_DRAWN`, `NEW_TARGETS`,
`DUPLICATE_OF_DRAWN`), `truelinev2/tests/test_callout_route_assembly_sweep.py` (frontier assertions),
`truelinev2/ingest/parent_source/parent_source_model.json` (census, spans, sheets, `adj_status`),
`wiki/START_HERE_TRUELINE_V2.md` (continued-34 snapshot). Read-only; no engine/render/census touched.*
