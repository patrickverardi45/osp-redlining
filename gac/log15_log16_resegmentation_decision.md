# RUN_ASSEMBLY_RESEGMENTATION_DECISION — LOG15/LOG16 (DESIGN/PROOF ONLY)

**Status:** design/proof only. No render, no placement wiring, no engine commit, no flag, no fixture/census
change, nothing placed. Branch `feat/truelinev2` @ `b4b597d`. Chooses the DO-NOT-WIDEN-safe path (Option #1
from `gac/log15_log16_continuation_trace_result.md`): re-segment to printed source anchors; footage-positioned
drive starts are NOT authorized. Source-grounded by the continuation trace + the parent-source model.

> Headline: log15/log16 are **drilling-drive accounting rows on one continuous spliced 2-1.25" 288ct fiber
> MAIN**, not standalone strokes. The fix is a **run-group parent object** (the model already has the
> `run_group_id` seam) that holds the drive rows as CHILD EVIDENCE and renders the run between PRINTED
> structure anchors via a **human-review lane**. The one clean, non-overlapping, both-ends-printed sub-run
> is **Candidate A: SPLICE 35 @ 28+73 → installer HH @ 39+79 (1106' = log15-tail 227' + log16 879')**. The
> upstream remainder (24+07→28+73 = 466') stays **parked pending sheet-5+ source**. **Deterministic render
> NOW: NO. Human-review lane: YES.** No new geometry primitive; reuse the cross-sheet route-assembly solver
> + the structure binders.

---

## RUN_ASSEMBLY_RESEGMENTATION_DECISION — LOG15/LOG16

- **Proposed parent/run model.** Introduce ONE **continuous-run object** (`run_group_id`, e.g.
  `run_chappell_hill_main_28+73_45+33`) spanning the printed fiber main. The parent-source model ALREADY
  carries `run_group_id` (today `bore_log15`/`bore_log16`/`bore_log20` each sit in their own group). The
  re-segmentation = give **bore_log15 + bore_log16 a SHARED run_group_id**, with documented downstream
  continuity into the existing **bore_log20** split family at SPLICE 46. The run object's RENDER unit is the
  printed structure-bounded run; the bore-log rows are child drive evidence under it.

- **Child segment mapping.** Within the run group:
  - `log15` (24+07→31+00, 693', sheets 6/7/8) → **child drive evidence**. SPLIT by the printed SPLICE 35 at
    28+73 into: an UPSTREAM remainder 24+07→28+73 (466', → sheet 5+, **PARKED**) and a downstream tail
    28+73→31+00 (227', inside Candidate A).
  - `log16` (31+00→39+79, 879', sheets 8/9/10) → **child drive evidence**, fully inside Candidate A.
  - (downstream, already modeled) `bore_log20` children `log49`/`log48`/`log50` (44+83 → SPLICE 46 → flower
    pots 5+07/5+14) → unchanged; the run continues into them past SPLICE 46.

- **Printed anchor candidates** (running ft; all source-bound structures from the trace census):
  - SPLICE 35 / NEXTLINK HH @ **28+73** (sheet 7) · interior NEXTLINK HH @ 35+43, 38+10 (sheet 9) ·
    installer HH @ **39+79** (sheet 10, log16 END) · installer HH @ **44+83** (sheet 10, log49 START) ·
    SPLICE 46 / NEXTLINK HH @ **45+33** (sheet 10).

- **Candidate pairings compared.**
  | pairing | length | maps to | overlap w/ rendered | ALL-REDLINES | verdict |
  |---|---|---|---|---|---|
  | **A. SPLICE35 28+73 → HH 39+79** | **1106'** | log15-tail 227' + log16 879' | **none** (ends 504' before bore_log20 @44+83) | under-covers by the 466' parked-upstream only | **RECOMMENDED** |
  | B. SPLICE35 28+73 → SPLICE46 45+33 | 1660' | + interim 504' + **log49 50'** | **OVERLAPS log49** (rendered) → duplicate stroke | over+under | rejected (duplicate) |
  | C. HH 39+79 → SPLICE46 45+33 | 554' | downstream interim + log49 | overlaps log49 | n/a (not log15/16) | rejected (wrong segment) |
  | D. SPLICE35 28+73 → HH 44+83 | 1610' | A + unaccounted 39+79→44+83 504' | none | bundles a 504' stretch not in log15/16 | not preferred |

- **Recommended anchor pairing.** **Candidate A — SPLICE 35 @ 28+73 → installer HH @ 39+79.** Both endpoints
  are printed structures; the conduit is continuously traceable across the 30+64/33+93/38+90 matchlines (the
  existing cross-sheet route-assembly primitive); it does NOT overlap any rendered child; and its length
  (1106') reconciles exactly to log15-tail (227') + log16 (879'). The only deficit is the 466' upstream
  remainder, which is a SEPARATE run segment (sheet 5+), not part of this stroke.

- **Why 31+00 is forbidden as endpoint.** 31+00 is an UNPRINTED ruler-point on a through-alignment (nearest
  structure 209 pt; no structure within 90 pt; sits between matchlines 30+64 and 33+93). Anchoring a stroke
  there = a footage-positioned interior point on continuous conduit, which trips the `end_is_drawn_terminus`
  / ruler-cut rejection law (the overtrace/drop false positive). It is a drive-accounting boundary, not a
  structure. Forbidden.

- **How 39+79 should be treated.** As a **legitimate printed terminus for a redline** (installer HH, binds
  uniquely at 188,422) — even though the physical main continues past it. A redline may END at a printed HH;
  that is not a fake endpoint. So 39+79 is Candidate A's downstream anchor AND log16's recorded drive end.
  It is NOT a backbone terminus (the run continues to SPLICE 46), so it does not "close the backbone" — it
  closes this sub-run.

- **Relationship to log49/log48/log50.** They are the **downstream split-family `bore_log20`** (44+83 →
  SPLICE 46 → flower pots), the continuation of the SAME main past SPLICE 46. log50 RENDERED; log48 HELD;
  log49 rendered via the continued-30 hook. Candidate A stops at 39+79, **504' upstream of bore_log20's
  44+83 start → zero overlap**. The run-group links them by continuity but the strokes never coincide.

- **Duplicate-redline risk.** **NONE for Candidate A** (bounded at 39+79 < 44+83). Candidates B/C WOULD
  duplicate log49 (the 44+83→45+33 stretch) → rejected. The doctrine below makes the duplicate-guard
  explicit so no future widening re-introduces it.

- **ALL-REDLINES accounting impact.** Candidate A draws log16 in full (879') + log15's printed-anchored tail
  (227'). The remaining 466' of log15 (24+07→28+73) is **PARKED as a NAMED source-required item** (sheet-5+
  head-end), NOT silently dropped — ALL-REDLINES is preserved as "drawn + named-parked = 100%", never
  "dropped". The drive-accounting totals (693'/879') are retained as child metadata and reconciled to the
  drawn run length.

- **Deterministic render eligibility now:** **NO.** Re-segmenting across the 31+00 bore-log boundary and
  choosing SPLICE 35 as the upstream cut is an owner ACCOUNTING decision, not a source-derivable fact (the
  source gives the conduit + the structures, but not "draw these two drive-rows as one structure-bounded
  stroke"). It must be owner-reviewed.

- **Human-review lane needed:** **YES.** This is the correct home: a review card presenting the run group,
  Candidate A (recommended) with both anchors source-bound + the cross-sheet route, the parked-upstream
  named, and the duplicate-guard vs bore_log20 — for owner approval. (Same family as the review-candidate /
  owner-promotion lanes.)

- **Sheet-5+ source still needed:** **YES** — to bound and eventually draw the upstream remainder
  (24+07→28+73 = 466', continuing onto sheet 5 via MATCHLINE 24+11). Independent parked item.

- **Required implementation slice (LATER, only if authorized).**
  1. **Run-group metadata** (parent_source_model.json — METADATA, not census): set a shared `run_group_id`
     on bore_log15 + bore_log16; record `interior_segmentation_cuts = [31+00, …]` and
     `run_boundaries = [SPLICE35@28+73, HH@39+79, SPLICE46@45+33]` (printed anchors); note downstream
     continuity into bore_log20. Source-derived from the matchline/splice continuity already traced.
  2. **A human-review render-card slice** (proof → review card, gated; NO auto-place) that proposes the
     Candidate-A stroke: endpoints via the existing structure binders; conduit via the existing cross-sheet
     route-assembly / matchline-join primitive (NO new geometry, NO BORE→BASE_CONDUIT, NO MAX_DASH_GAP
     change); a duplicate-guard asserting the stroke ends ≤ 39+79 < bore_log20 @ 44+83; the parked-upstream
     emitted as a named SOURCE_REQUIRED item.
  3. **Accounting reconciliation**: drive spans retained as child evidence; drawn run length corroborates;
     parked remainder named. No census re-baseline (the run object is metadata; the census buckets are
     unchanged until a stroke is owner-approved).

- **Tests needed (LATER).** run_group_id is source-derived (matchline+splice continuity), not invented;
  31+00/24+07 NEVER appear as stroke endpoints (assert endpoints ∈ printed structures); Candidate-A stroke
  does NOT overlap bore_log20 (downstream end < 44+83); parked-upstream is explicitly named (ALL-REDLINES
  accounting); census FROZEN (OFF 31/6/1/17/3, ON 22/1/4) + flag-OFF byte-identical; no corpus mutation; the
  parent-model edit is metadata-only (no completion-bucket change); red strokes only; no PNG-as-redline in
  the proof.

- **Files changed.** NONE (design only). New untracked scratch: this packet. (The continuation-trace probes
  + contact sheet from the prior step remain the source evidence.)

- **Commit.** NONE. **Push.** NONE.

- **Recommendation.**
  1. **Adopt the run-group + accounting doctrine**: drive/accounting span (bore-log row) ≠ printed
     source-bound run span (what's drawn); no fake endpoints at unprinted cuts; no duplicate over rendered
     children; ALL-REDLINES = drawn + named-parked.
  2. **Re-file log15/log16 as CHILD EVIDENCE under one run-group**, NOT standalone strokes.
  3. **Render via a HUMAN-REVIEW lane, Candidate A (SPLICE 35 @ 28+73 → installer HH @ 39+79)** — the only
     non-overlapping, both-ends-printed sub-run — with the 466' upstream PARKED pending sheet-5+ source.
  4. **Hold for explicit authorization** before implementing the run-group metadata + the review-card slice.
     Nothing is rendered or wired until the owner approves the card.

---

## Guardrails honored
Design/proof only. No render, no placement wiring, no footage-positioned drive start, 31+00 never an
endpoint. No BORE→BASE_CONDUIT, no MAX_DASH_GAP/budget/tolerance change, no corpus mutation, no census
rebaseline, no flag, no deploy, no `origin/main`, no backend/web/runtime touch, no unrelated-file cleanup,
no junction_bridge. The proposed parent-model edit is METADATA (run_group_id), gated and reversible, and is
NOT performed here. Reversible (one untracked packet).
