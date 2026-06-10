# M8.2k — reset-vs-continuous collision rule (PROOF-ONLY proposal)

**Status:** PROOF ONLY — a rule *proposal* simulated against banked evidence. **Not wired into
`decide.py` / `run_match` / default placement. No engine import in the proof. No activation. No
default behavior change. No production. No deploy.**
**Date:** 2026-06-10 · **Branch:** `feat/truelinev2` (isolated) · **HEAD at proof:** `4acb969`
**Files:** `proof/reset_collision_rule.py` (pure rule) + `proof/run_reset_collision_rule_proof.py`
(simulation) + `tests/test_reset_collision_rule_proof.py` (13 tests).
**Outputs:** `data/outputs/reset_collision_rule_proof.{json,md}` (gitignored).
**Verdict:** **`PROOF_ONLY_READY_FOR_OPT_IN_TEST`** — with a demote-only expected effect that is an
explicit owner decision (see §Honest impact).

> Uses Patrick's banked M8.2j grades ([[m8-2j-reset-collision-human-grades|ledger]], commit
> `4acb969`) as *evidence only*. Upstream state unchanged: M8.2d **NOT_SAFE**, M8.2f
> **NEEDS_MORE_EVIDENCE**, M8.2g/h banked, default **23/58**.

## The proposed rule (precedence, safety-first)

1. **R3/R5 — parent-run/segment ambiguity outranks everything:** context unresolved, or the
   segment ends at an access structure (flower pot / HH / terminal) *with competing continuation
   evidence* → `abstain_required`. An on-crossing reset equation alone is NOT enough to override
   parent-run/segment ambiguity.
2. **R2 — precision conflict:** the on-crossing equation has close competing readings (log57's
   `3+98` vs `3+93`, ≤10 ft band) → `precision_conflict_manual_review`. Never auto-pick a side.
3. **R1 — confirmed reset:** the on-crossing equation is visually confirmed AND the far-side
   continuation matches the reset station → `reset_equation_confirmed`.
4. **R4 — continuous never silently wins:** an exact continuous box match alone is NOT enough to
   override an on-crossing reset equation; unconfirmed collision → `still_unknown_manual_review`.
5. **R0 — scope:** no on-crossing reset equation → `continuous_station_stands` (the rule does not
   dispute the default).
6. **R6 — invariant:** **no classification may auto-promote anything** (`may_auto_promote` is
   constant `False`, test-pinned); the simulation is demote-only by construction. Even
   `reset_equation_confirmed` places nothing — re-chaining through the equation stays gated behind
   a future default-OFF flag + an M8.2d-style zero-regression proof.

## Proof results (real run)

| Case | Patrick's grade | Rule classification | Correct | Default | Simulated if consulted |
|---|---|---|---|---|---|
| log42 `[1,2]` | `reset_equation_confirmed` | `reset_equation_confirmed` | ✅ | AUTO_SELECT | **REVIEW** |
| log57 `[8,10,13]` | `precision_conflict_manual_review` | `precision_conflict_manual_review` | ✅ | AUTO_SELECT | **REVIEW** |
| log65 `[9,10]` | `abstain_required` | `abstain_required` | ✅ | AUTO_SELECT | **ABSTAIN** |

- **Classified correctly: 3/3.** **Auto-promotions: 0** (invariant holds over every class).
- The rule fires ONLY on these three collisions — M8.2g/h established they are the *only*
  on-crossing reset-vs-continuous collisions in the 58-log corpus — so the other 20 placed logs
  (and all 35 non-placed) are untouched by construction.

## Honest impact: it does NOT preserve all 23 — by design

**`preserves_all_23_default_placements = False.`** All three graded logs are currently
**AUTO_SELECT via the exact continuous chains that Patrick's grades now dispute.** If a future
flag consulted the rule: AUTO 14→11, REVIEW 9→11, ABSTAIN 33→34, **placed 23→22**, promotions 0.
That is the zero-false posture working as intended: human evidence says these three continuous
chains are wrong-chained / unresolved, so keeping them AUTO would preserve *coverage built on
disputed chains*. Demote-only is the safety direction — the rule cannot create a false placement;
it can only withdraw potentially-false ones. **Reducing AUTO coverage is still an owner decision**
— flag-gated, default-OFF, explicit approval required before any engine wiring.

## M8.2d relationship

**Does this resolve the M8.2d 23→15 regression risk? No.** That risk came from *blanket* frame
translation treating every cross-sheet link as needing a frame edge (breaking 8 genuinely
continuous runs). This rule activates **no** translation and leaves M8.2d **NOT_SAFE** for blanket
opt-in. What it adds is the narrow, evidence-gated middle path M8.2f called for: collision-scoped,
human-graded, demote-only.

## Safe for future opt-in testing?

**Yes, as a test** — expected effect is exactly: log42 AUTO→REVIEW, log57 AUTO→REVIEW, log65
AUTO→ABSTAIN, zero promotions, zero changes elsewhere (verified expectation for the future opt-in
run). Anything beyond that observed in the opt-in test = stop and bank the negative.

## Gates this proof was run under

Default sweep exactly `AUTO_SELECT=14 REVIEW=9 ABSTAIN=33 ERROR=2 PLACED=23` (unchanged); M8.2d
still NOT_SAFE; M8.2f still NEEDS_MORE_EVIDENCE; M8.2g/h consistent with banked outputs; M8.2j
validator `ALL_GRADED_PENDING_ZERO_REGRESSION_PROOF`; full v2 suite + drift guards + import
isolation green. The proof script imports **zero** engine modules (only the ledger reader, the
pure rule, and the gitignored sweep artifact).

## Next gate (not authorized by this doc)

A default-OFF, flag-gated **opt-in test** wiring the rule as a *gate* (demote-only) on the three
collision cases, re-validated by the full M8.2d-style zero-regression proof: the 20 untouched
placements byte-identical, exactly the three expected demotions, nothing promoted. Requires
explicit owner approval. Separately: resolving log57's exact matchline station and log65's
parent-run context are the named evidence targets that could upgrade those grades.

Related: [[m8-2j-reset-collision-human-grades]] (ledger), the M8.2i doctrine,
[[m8-2-frame-aware-assembly-phase0]], [[run-segment-hierarchy-doctrine]].
