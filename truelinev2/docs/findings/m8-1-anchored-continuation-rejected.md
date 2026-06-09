# M8.1 — Anchored continuation REJECTED (Phase 0 read-only proof)

**Date:** 2026-06-09 · **Branch:** `feat/truelinev2` (isolated)
**Type:** negative finding from a read-only Phase 0 proof. **No code/test/engine change. No production. No deploy.**
**Outcome:** **REJECT / REDESIGN.** Do **not** implement anchored continuation as scoped in the M8.1 packet.
**Evidence:** read-only probe (callouts, matchline equations, `build_chains` output) over `log11`, `log12`, `log71`. Probe lives outside the repo (`C:\Temp\…`), retained for reference; nothing in the repo was modified.

## Verdict
Anchored continuation ("extend a chain that starts at the bore's absolute start across a unique matchline") is **not deterministic** on any of the three target logs. The Phase 0 proof disproved the design *before* any implementation — exactly its purpose.

## Why the Phase 0 proof disproved the scoped design

### 1. `startC > 0` was anchor **ambiguity**, not a clean anchor
M8a sub-classed `log11/log12/log71` as "anchored" because `build_chains` produced a chain starting at the bore's absolute start (`start_delta ≤ 8`). The probe shows `startC` is the **count of candidate callouts at the bore's start station**, not a unique anchor:
- `log11`: **9** callouts begin at `0+00` (s5×2, s17×7) → 9-way ambiguous.
- `log71`: **7** callouts begin at `0+00` (s23×4, s24×3) → 7-way ambiguous.
- `log12`: 1 — but see §below, it isn't a continuation case.

A unique anchor would be `startC == 1`. Multi-anchor cases cannot be deterministically placed by extension alone.

### 2. The current `build_chains` is **frame-blind**
`match/chains.py` links callouts by raw **absolute** station contiguity (`last.to_ft ≈ next.from_ft ± link_tol`), across any sheets, **ignoring matchline frame equations**. Brenham (and ODOT) sheets carry **per-drive local frames** that reset at matchlines, so cross-sheet links by raw station number are **coincidences, not continuations**.

### 3. Raw station-number linking across a matchline reset can build **physically wrong chains**
Matchline equations encode a **frame translation**, e.g. `s5: MATCHLINE STA 3+23/0+69 - SEE SHEET 17` ⇒ **s5 STA 3+23 = s17 STA 0+69** (offset **254 ft**). The frame-blind linker instead joins `s17 0+69 → s5 0+69` (same number, wrong frame). Result: an assembled chain that is not a real run.

## Per-log evidence

### `log11` (span 650, `0+00→6+50`, refs [5,17]) — **frame-confused assembly**
- Best chain hops **s17→s5→s17**: `s17[0+00→0+69] → s5[0+69→3+25] → s17[3+23→3+91] → s17[3+91→4+57] → s17[4+57→6+30]` (summed 632; `end_d 20`).
- Conduit **changes** mid-chain (`1-1.25" HDPE` → `2-1.25" HDPE`) → **different runs**, not one.
- 9 ambiguous `0+00` anchors; the cross-sheet link violates the `3+23/0+69` frame equation. **NOT UNIQUE → abstain (correct).**

### `log12` (span 542, `5+50→10+92`, refs [3]) — **same-sheet gap, not continuation**
- The whole run is on **sheet 3**: `5+43→7+77 (234') → 7+77→9+30 (153') → [gap 9+30→9+38 = 8 ft] → 9+38→10+92 (154')` = **541 ft, ending exactly at the bore end `10+92`**.
- The blocker is an **8-ft intra-sheet gap** exceeding `link_tol`, with **no matchline involved**. Conduit also mixes `HDPE / VACANT / HDPE` (run-identity caveat).
- **Mis-bucketed by M6's "BUCKET2 matchline" hint.** Needs a *different* capability (same-sheet gap-bridging with run-identity gating) → **not M8.1.**

### `log71` (span 695, `0+00→6+95`, refs [23,24], old-engine GT-validated) — **needs AP/KMZ/source context**
- Best chain `s24[0+00→5+45] (545')`, 150 ft short. Tail sheet s24 has **three** exits (`SEE SHEET 23` ×2, `SEE SHEET 25`).
- The conduit-consistent continuation `s24 5+45 → s23[5+45→9+38] (393')` gives `938`, **overshooting 695 by 243**; no `~150'` continuation closes it.
- 7 ambiguous `0+00` anchors. The old engine placed it with **AP-terminal + KMZ** evidence the PDF-footage matcher lacks. **NOT UNIQUE / out of PDF-only scope → abstain (correct).** This is the M6 *needs-data* lane.

## What remains valuable
- **Matchline equations are deterministically parseable and convention-generic.** `MATCHLINE STA a/b - SEE SHEET T` cleanly yields a frame translation (`sheetₛ STA a = sheet_T STA b`). The continuation **evidence** is real and reusable (ODOT carries matchlines too). The parseability gate did **not** trip — the failure was uniqueness and run-identity, not parsing.

## Correct next abstraction (design only; not authorized)
- **Frame-aware chain assembly:** parse the `a/b` equations and build chains in a **translated** frame so cross-sheet contiguity is *physically* meaningful — a correctness improvement to `build_chains`, broader than "extend a tail." It must be proven first on a case with a **unique** anchor (`startC == 1`) and consistent run-identity.
- **Source / run modeling must precede implementation:** anchor disambiguation (multiple `0+00` starts) and run-identity threading (conduit type, corridor/street continuity) need a model **before** any multi-anchor placement. `log71`-class logs likely need AP-terminal/KMZ evidence (a separate lane). `log12` splits off to same-sheet gap-bridging.

## Evidence-target backlog (doctrine-compliant next-evidence paths)

Per the v2 evidence-seeking doctrine — *a completed project package contains the placement information; an abstain is an **unmodeled relationship**, not "impossible."* Each rejected log carries its precise next-evidence path below. Zero-false holds: **none place until the column-4 proof exists.**

| Log | 1. Missing relationship | 2. Likely artifact in the completed package | 3. Generic capability needed | 4. Safe-placement proof required | 5. What would be unsafe |
|---|---|---|---|---|---|
| **log11** | which frame-anchored physical run the local-`0+00` bore is (9 candidate anchors) | matchline equations (frame translation — already parseable) + original/combined bore log or split-segment grouping + run-identity (conduit/corridor continuity) | frame-aware chain assembly + run-identity threading + anchor disambiguation | a **unique**, frame-translated, conduit-consistent run covering the bore span | placing on any of the 9 ambiguous `0+00` anchors without disambiguation |
| **log12** | that two same-sheet callouts separated by an **8-ft un-callouted gap** are one physical run | the plan sheet's gap region (an un-extracted short segment / vector continuity) + the bore-log station rows across the gap | same-sheet gap-bridging gated by run-identity + station continuity | the gap is real continuity **and** conduit-consistent end-to-end | bridging across the mid-run `HDPE → VACANT → HDPE` change without identity evidence |
| **log71** | which **AP-terminal / route** the bore anchors to (old engine used it; GT-validated ⇒ an answer exists) | KMZ route geometry + AP/terminal structure + the human redline answer key | structure-anchor placement + KMZ/geo route ingestion (a future geo lane) | a **unique** AP/terminal anchor with route geometry matching the bore span | PDF-footage-only placement among the 7 anchors, which overshoots |

These are **named targets, not dead ends**: the relationship is assumed present in the completed package; v2 simply has not yet modeled station-frames / run-grouping / structure-anchors / route-geometry. Each becomes a future read-only Phase 0 proof before any code.

## Hard constraints carried forward
- **Do NOT implement anchored continuation.**
- **Do NOT widen tolerances** to force these placements.
- **Do NOT hardcode sheet maps** or any packet-specific continuation table (that is the old `CURRENT_PACKET_PRINT_SHEET_INDEX` hack).
- **Do NOT port old-engine implementations** (AP resolvers, route overrides, terminal-tail) — model the generic capability instead.
- Zero-false remains paramount: these logs correctly abstain today; keep them abstaining until a *deterministic, run-identity-checked* abstraction exists.

## Status
Coverage unchanged at **23/58**. No placement moved. This finding banks the rejection and redirects the next continuation work toward frame-aware assembly + source/run modeling, each to be re-proven by a fresh read-only Phase 0 before any code.

Related: [[m6-grade-classify]] (bucket classification this corrects), the M8a continuation audit, and the M8.1 scope packet (both superseded by this rejection).
