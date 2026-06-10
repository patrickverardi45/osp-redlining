# M8.2g — transition evidence refinement (read-only)

**Status:** read-only evidence grading of the three M8.2f dirty transitions. NO engine /
`decide.py` / default-`run_match` / `transition_classifier` / adapter change; frame
translation stays **INACTIVE**. Default remains **23/58**, M8.2d remains **NOT_SAFE**,
M8.2f remains **NEEDS_MORE_EVIDENCE** (the classifier was not modified). Outputs under
gitignored `data/outputs/` only. **No activation, no placement change.**

## Why

M8.2f refused to preserve 3 of the 8 M8.2d-regressed placements (log42 `ambiguous`, log57
`conflict`, log65 `ambiguous`) but printed only the offsets, not WHY the edges exist. M8.2g
surfaces the **frame-equation source text + context**, the chain geometry, the default-vs-opt-in
result, and a geometric plausibility test, then grades each disputed transition.

## What shipped (v2-only, additive)

- `truelinev2/proof/run_transition_evidence_refinement.py` — read-only report; pure
  `adjudicate()` helper + evidence extraction; writes
  `data/outputs/transition_evidence_refinement.{md,json}`.
- `truelinev2/tests/test_transition_evidence_refinement.py` — 10 unit tests for the pure
  `adjudicate()` helper.

## Summary verdict (all three: `needs_manual_review`)

| target | dispute | the real evidence | recommendation |
|---|---|---|---|
| log42 [1,2] | s2→s1 `ambiguous` | exact continuous box match (270'+17'=287', Δ0); a real HIGH matchline eq `STA 2+70/5+16` (246 ft) also on the pair — likely a **different** matchline | `needs_manual_review` |
| log57 [8,10,13] | s13→s8 `conflict` | two HIGH eqs **share a side** (`…/3+08`) and differ by only **5 ft** (`3+98` vs `3+93`) — two sides of **one** matchline, not a semantic conflict; exact box match (Δ0) | `needs_manual_review` |
| log65 [9,10] | s10→s9 `ambiguous` | exact box match (160'+39'=199', Δ0); eq `STA 38+90/6+11` (3279 ft) is geometrically possible (sheets reach 4533 ft) but incompatible with a 199' continuous segment — likely a **different** matchline | `needs_manual_review` |

Key synthesis: **all three default placements are EXACT continuous box matches** (footage +
both endpoints, Δ≈0), which strongly corroborates continuity at the bore's crossing. Each
dispute therefore reduces to one question — *is the parsed reset equation AT this crossing, or
is it a different matchline on the same sheet pair?* — which text alone cannot settle. log57's
"conflict" is additionally shown to be a 5‑ft extraction-precision spread on one matchline, not a
real two-way ambiguity. None is a `parser_false_positive` (no offset exceeds the joined-sheet
station ceiling) and none is a `true_conflict_abstain`.

## Two reusable rules this pass teaches

1. **Geometric plausibility gate:** drop a frame edge whose `|offset|` exceeds the furthest
   authored station on the joined sheets — an impossible adjacent-sheet reset — before it can
   block a continuous link or fabricate a conflict. (None of these 3 tripped it, but it is the
   guard that would catch a true parser false positive.)
2. **Extraction-precision vs semantic conflict:** two equations that share a side and disagree by
   a small margin just over the 2 ft conflict tolerance are ONE imprecise matchline, not a
   conflict — either tighten extraction or set the conflict tolerance to the extraction precision.

A third, larger rule is implied: a reset equation must be **localized to the actual crossing**
before it may override an exact continuous box match elsewhere on the same sheet pair. That is
real classifier work and is deferred (NOT done here).

## Gates (all green)

- new helper tests: **10 passed**.
- full v2 suite: **130 passed** (120 prior + 10 new).
- default corpus sweep: `14/9/33/2 → PLACED=23` (exact, unchanged).
- M8.2d opt-in validation: re-confirmed **NOT_SAFE**.
- M8.2f classifier report: re-confirmed **NEEDS_MORE_EVIDENCE** (classifier untouched).
- drift guards + standalone import isolation: pass.

## What remains blocked

- All three transitions are blocked on Patrick's targeted visual grade (crops listed in the
  report) — specifically, which matchline sits at each bore's crossing.
- log11 remains separately blocked on missing anchor/box/footage evidence.
- NO classifier change and NO opt-in attempt until the three are graded and a precedence rule
  (reset-localization) is defined.

## Recommended next step (NOT started; needs explicit approval)

1. Patrick grades the 3 crops against the equation evidence in the report.
2. If any equation is mis-located/misparsed, fix the frame parser (geometric gate + precision
   handling) in a separate gated change, then re-run M8.2f and confirm the transitions clean up.
3. Only then design the reset-localization precedence rule and attempt a classifier-gated opt-in,
   re-validated by M8.2d with zero regression.
