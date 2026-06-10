# M8.2h — transition visual / manual review targets (read-only)

**Status:** read-only geometric/visual target extraction for the three M8.2g unresolved
transitions. NO engine / `decide.py` / `run_match` / `transition_classifier` / adapter change;
frame translation **INACTIVE**. Default **23/58**, M8.2d **NOT_SAFE**, M8.2f
**NEEDS_MORE_EVIDENCE**, M8.2g **all needs_manual_review** are all unchanged. Coordinates,
crops, and report go to gitignored `data/outputs/` only. **No activation, no placement change,
and "still unknown" is an accepted, honest outcome.**

## Why

M8.2g graded log42/log57/log65 `needs_manual_review` — each has an EXACT continuous box match
AND a competing parsed reset — and hypothesized the resets were *probably a different matchline
on the sheet pair*. M8.2h tests that geometrically: it pulls PAGE COORDINATES (display space,
via `PlanPdf.search`/`words` — the same safe reader the engine uses, no new renderer) for the
bore boxes and the competing equation, and measures how far the reset sits from the bore's
crossing.

## What shipped (v2-only, additive)

- `truelinev2/proof/run_transition_visual_targets.py` — read-only report + pure
  `classify_visual()` helper; writes `data/outputs/transition_visual_targets.{md,json}` and
  focused crops under `data/outputs/m8_2h_crops/` (reusing `PlanPdf.render_clip`).
- `truelinev2/tests/test_transition_visual_targets.py` — 9 unit tests for `classify_visual()`.

## Key finding — M8.2g's "different matchline" hypothesis is REFUTED

In all three targets the competing matchline equation **references the bore's crossing station
and sits next to the bore's crossing box** — it is the matchline **AT** this crossing, not a
distant one:

| target | crossing sta | competing equation | dist box→eq (near≤166) | verdict |
|---|---|---|---|---|
| log42 [1,2] | `2+70` | `STA 2+70 / 5+16` (246 ft, HIGH) | 136 | `still_unknown_manual_review` |
| log57 [8,10,13] | `3+98` | `STA 3+98/3+08` & `STA 3+93/3+08` (HIGH, share `3+08`, 5 ft apart) | 148 | `precision_conflict_manual_review` |
| log65 [9,10] | `6+11` | `STA 38+90 / 6+11` (3279 ft, HIGH) | 130 | `still_unknown_manual_review` |

So these are **genuine reset-vs-continuous collisions**: the exact continuous box match says
*continuous*, while a matchline equation **at the same crossing** says *reset*. Text + geometry
cannot decide which framing the boxes were authored in — that is a human call. (log57 is also the
two-sides-of-one-matchline precision case from M8.2g.) The geometry-decidable outcome
`different_matchline_confirmed` was reachable but, honestly, **not** triggered by any target.

For each target the report gives the bore start/end/crossing box coordinates, the competing
equation source text + page hits, matchline-marker counts, nearby HH/flower-pot/access/splice
labels, the box→equation distances, and a focused crop — everything Patrick needs to make the
call quickly.

## Gates (all green)

- new helper tests: **9 passed**.
- full v2 suite: **139 passed** (130 prior + 9 new).
- default corpus sweep: `14/9/33/2 → PLACED=23` (exact, unchanged).
- M8.2d opt-in: re-confirmed **NOT_SAFE**.
- M8.2f classifier: re-confirmed **NEEDS_MORE_EVIDENCE** (classifier untouched).
- M8.2g refinement: re-confirmed **all needs_manual_review** (purely additive; not altered).
- drift guards + standalone import isolation: pass.

## What remains blocked

- All three targets remain blocked on Patrick's visual grade — but now with exact coordinates +
  crops and a precise question per target ("is the on-crossing matchline a real reset, or are the
  boxes continuous and the reset belongs to a different route at that matchline?").
- These three are segment children of larger runs (per the run/segment doctrine); the real fix is
  reset-localization + frame-aware run assembly — NOT done here, separately gated.
- log11 remains separately blocked on missing anchor/box/footage evidence.

## Recommended next step (NOT started; needs explicit approval)

1. Patrick grades the 3 crossing crops against the equation coordinates in the report.
2. Decide, per target, whether the on-crossing matchline equation is the bore's real reset or
   annotates a different route — that single decision resolves each verdict.
3. Only then design the reset-localization precedence rule and attempt a classifier-gated opt-in,
   re-validated by M8.2d with zero regression.
