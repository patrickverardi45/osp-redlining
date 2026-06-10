# Run/Segment Hierarchy — foundation (model + assembly)

**Status:** SHIPPED (foundation only). **No production. No deploy. Nothing merged to main.**
**Date:** 2026-06-09 · **Branch:** `feat/truelinev2` (isolated)
**Type:** foundational model + pure-function work — the data/model/assembly layer that
stops the engine treating every bore-log row as an isolated whole run.
**Coverage:** **unchanged at 23/58.** This milestone moves **no placement** and converts
**no abstain** — by design.

> Implements the doctrine in [[run-segment-hierarchy-doctrine]]. This is the precursor to
> **M8.2 frame-aware assembly**, not M8.2 itself.

## What this is (and is not)

This is **foundational model work only**:

- It adds the **types** and **pure functions** for representing a run as a composition of
  child segments, and for proving/composing that relationship safely.
- It does **not** wire run/segment into the matcher, the review payload, or rendering.
- It does **not** increase coverage, change any disposition, or alter any tolerance.
- **Segment placement remains entirely separate from run assembly** — exactly as the
  doctrine requires (place segments first; assemble only when contiguity is proven).

No existing file was modified. The work is four new files; the engine, deciders, adapters,
review payload, store, api, and all of `backend/`/`web/` are untouched.

## Why now (the gap it closes)

Phase 0 inspection confirmed v2 had **no segment/run distinction**: `run_match`
([match/engine.py](../../match/engine.py)) returns exactly **one `Placement` per bore**, and
there was **no coordinate/polyline geometry type** anywhere (only evidence-crop bboxes).
That flat "one row = one whole run" shape is the conceptual root under the M8.1 rejection
([[m8-1-anchored-continuation-rejected]]). This foundation introduces the missing hierarchy
so future work composes runs from segments instead of redrawing them.

## What shipped

### A — domain types (`truelinev2/schema/hierarchy.py`)
`SegmentId`, `RunId`, `SourceContextId` (identity newtypes); `Point`, `SegmentGeometry`,
`RunGeometry` (frame-tagged, coordinate-agnostic geometry); `SegmentEvidenceRef`,
`RunAssemblyEvidence`, `ContiguityEvidenceKind`, `EvidenceStrength` (evidence); `BoreSegment`,
`BoreRun` (the hierarchy aggregates); plus `JoinVerdict`/`ContiguityResult` (proving results).
`RunGeometry` carries `segment_point_counts` so a run is always **decomposable back to its
child segments** (reversibility is mandatory for QA/closeout/billing/audit).

### B — `assemble_run_geometry(...)` (`truelinev2/match/assembly.py`)
Pure composition of ordered, proven segment geometries into **one run polyline**: it
concatenates child points and de-duplicates each shared join vertex — **introducing no new
vertices and no overlapping span**. It never synthesizes an independent global start→end
line. A gap, an overlap, an **independent parent geometry** (e.g. an `A→D` line appended over
`A→B→C→D` children), or a **mixed coordinate frame** is rejected with `RunAssemblyError`.
`decompose_run_geometry(...)` reverses a composition to its exact children.

### C — `prove_contiguity(...)` (`truelinev2/match/assembly.py`)
Pure validator: a chain may assemble only when **every** consecutive join carries **explicit
evidence** including **≥1 STRONG** kind (doctrine §8 strength map: shared-endpoint /
same-structure / frame-equation-reset / matchline-continuity = STRONG; drawn-path /
BOC-callout = MEDIUM; date/crew/source-page context = WEAK). **Proximity is not an evidence
kind**, so nearness can never prove a join. `assemble_run(...)` ties prove→compose and returns
`None` (segments stay separate / REVIEW) on any unplaced segment or unproven join.

### D — tests (`truelinev2/tests/test_run_segment_hierarchy.py`)
Three segments compose into one run; the run is a composition (decomposes to the exact
children), not a redraw; segment evidence survives into the run; unproven contiguity blocks
assembly; nearby endpoints alone are insufficient; an overlapping parent geometry is rejected
and an independent `A→D` line is impossible by construction; existing **M7** deciders + engine
paths are unchanged; and the **import-isolation** guard still passes with the new modules.

## Invariants held

- **Zero behavior change.** No existing file touched; matcher/deciders byte-identical;
  coverage 23/58 unchanged; no disposition or tolerance altered.
- **Drift guards green.** No convention names in core; no global mutable state (module-level
  maps are UPPER_CASE constants); zero old-app imports.
- **No production / main / Render / Vercel touch.** Nothing merged or deployed.

## How this informs M8.2 (frame-aware assembly)

M8.2 will build chains in a **frame-translated** coordinate (parsing matchline `a/b`
equations) and emit **`BoreRun`s composed of placed `BoreSegment`s** via exactly these
functions — proving a unique anchor + consistent run-identity first, abstaining to separate
segments otherwise, and rendering `segment → segment → segment` with **no parent over-draw**.
This foundation is M8.2's output contract; M8.2 still begins with its own read-only Phase 0
proof before any matcher change.

Related: [[run-segment-hierarchy-doctrine]], [[m8-1-anchored-continuation-rejected]],
[[m6-grade-classify]], [[v2-redline-workflow-vision]].
