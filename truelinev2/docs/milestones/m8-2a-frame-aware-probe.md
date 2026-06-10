# M8.2a — frame-aware probe (read-only proof)

**Status:** PROOF / PROBE — read-only. **No engine/matcher/adapter change. No placement moved. No production. No deploy.**
**Date:** 2026-06-09 · **Branch:** `feat/truelinev2` (isolated) · **HEAD at probe:** `47b1ac9`
**Type:** the read-only evidence step the [[m8-2-frame-aware-assembly-phase0]] recommendation gated M8.2 on.
**Script:** `truelinev2/proof/run_frame_aware_probe.py` (+ pure-helper tests `tests/test_frame_aware_probe.py`).
**Outputs:** `data/outputs/frame_aware_probe.json` + `data/outputs/frame_aware_probe.md` (gitignored).
**Conclusion:** **IMPLEMENTABLE** (for the log11-class cross-sheet case) — with a bounded, named ambiguity set the future implementation must gate per-equation.

> This probe answers the Phase 0 gate question: *are the matchline/station-frame equations actually
> extractable from the real PDF text, and do they explain (and fix) the frame-blind link?* They are, and
> they do — for log11 uniquely and consistently. It also measures where the corpus-wide signal is ambiguous.

## What ran (read-only)

A new `proof/` script scanned the real Brenham plan PDF (`NEXTLINK - Brenham - Phase 5`, 43 pages) for
station-pair equations (`STA a = b` / `STA a / b`), associated each with nearby `SEE SHEET N` + `MATCH LINE`
context, built candidate frame edges, and focused on log11. It **invokes no placement path**
(`placement_paths_invoked = false`): it uses only `PlanPdf.text_by_index`, `stations.parse_station`,
`ingest.normalize.load_borelog`, and `PlanDialect.extract_callouts` (all read-only), and writes only under
`data/outputs/`. No engine/matcher/adapter file was touched.

## Headline results

| Metric | Value |
|---|---|
| PDF pages scanned | **43** |
| Candidate equations found | **83** |
| Parseable (both stations → feet) | **83 / 83** (0 unparseable) |
| Candidate frame edges (cross-sheet, **unique** link) | **24** |
| Equations with ≥2 sheet links (ambiguous association) | 26 (excluded from edges — conservative) |
| Cross-sheet offset conflicts | **2** pairs |

The equation grammar is reliably extractable from text — the parse rate is 83/83, and equations cleanly
separate into **cross-sheet matchline translations** (carry a `SEE SHEET`), **local frame resets**
(`STA n+nn = 0+00`), and unassociated station equations.

## log11 — the canonical frame-blind case (resolved on real data)

- `sheet_refs = [5, 17]`, span `0+00 → 6+50` (650 ft).
- **The exact frame equation is extracted, uniquely and at HIGH confidence:**
  > **sheet 5 STA 3+23  ≡  sheet 17 STA 0+69   (offset 254 ft)**
- **safe translated relationship extractable: TRUE.** **explains why raw `0+69 → 0+69` is unsafe: TRUE** —
  the 254 ft offset proves sheet 17's `0+69` maps to sheet 5's `3+23`, *not* sheet 5's `0+69`. The current
  frame-blind linker ([chains.py:27](../../match/chains.py)) would join the equal numbers and build a
  physically wrong run; the equation is exactly what a frame-aware builder needs to refuse that.
- **Anchor ambiguity corroborated:** zero-start (`~0+00`) callout counts are **sheet 5 = 2, sheet 17 = 7
  → 9 total**, matching the M8.1 finding's "9 ambiguous `0+00` anchors" precisely. So a frame-aware builder
  must *also* gate on a unique anchor (`startC == 1`), not just the equation.

## Ambiguity surfaced (the bound on safe scope)

Reported honestly so the implementation gates for it rather than assuming the whole corpus is clean:

- **26 equations have ≥2 nearby `SEE SHEET` links** — association is not unique (often a title block citing
  both neighbors). These are **excluded from the edge set**; an implementation must abstain or disambiguate.
- **2 sheet pairs have conflicting offsets:** `8–13` (85 vs 90 ft — minor, ~5 ft) and **`17–20` (1 vs 504 ft
  — major)**. A conflict means two equations disagree on a pair's translation → that pair is unsafe to use
  until disambiguated. (log11's `5–17` pair is **not** among the conflicts.)
- Many LOW-confidence `frame_reset` equations (`STA 7+40 = 0+00`, `STA 15+13 = 0+00`) — real local-frame
  reset markers, useful but not cross-sheet translations on their own.

## Why the conclusion is IMPLEMENTABLE (scoped)

For the **log11-class cross-sheet continuation**, all three Phase 0 gates are now evidenced on real data:
the equation is extractable (HIGH, unique, no conflict on `5–17`), it explains/fixes the unsafe raw link
(254 ft offset), and the residual anchor ambiguity is measured (9) so it can be gated. That is sufficient
to *begin* implementation — **abstain-first, per-equation-confidence-gated** — not to place broadly.

The corpus-wide ambiguity (26 multi-link, 2 conflicts) is **not** a blocker; it is the **scope boundary**:
the assembler must consume only **HIGH-confidence, unique, conflict-free** edges and abstain on the rest —
exactly the zero-false posture. No tolerances are widened; no current placement is implied to change.

## Verification that placement is unchanged

- The probe imports/calls **no** placement path (`run_match` / `RedlineService` / builders / store writes);
  `placement_paths_invoked = false` is asserted in the report.
- No engine/matcher/decider/schema/adapter file was edited (forbidden set untouched).
- The full v2 suite (which exercises placement, incl. M7 + corpus harness) remains green; coverage stays
  **23/58**. The probe is additive proof, not a behavior change.

## Recommendation → next milestone

**Proceed to M8.2 implementation** per the [[m8-2-frame-aware-assembly-phase0]] file map, scoped to the
proven-safe slice:

1. Model `Frame` / `FrameEquation` / `FrameGraph` in `schema/frames.py` (generic core types).
2. A matchline-equation extractor in `extract/matchline.py` (this probe's parser, hardened) producing
   generic `FrameEquation`s, **with the confidence + uniqueness + conflict gates this probe defines**.
3. A frame-aware chain builder in `match/frame_chains.py` that translates into a common frame before
   linking, consuming only HIGH-confidence/unique/conflict-free edges, gated by **unique anchor**
   (`startC == 1`) + **run-identity consistency**, abstaining otherwise.
4. Re-prove on the corpus with **zero change to the current 23/58 placements** before anything is wired
   into the live matcher.

If the implementation's own re-proof shows any placement regression or unresolved ambiguity on a target log,
bank the negative and keep those segments abstaining — same discipline as M8.1.

Related: [[m8-2-frame-aware-assembly-phase0]], [[run-segment-hierarchy-doctrine]],
[[m8-run-segment-foundation]], [[m8-1-anchored-continuation-rejected]].
