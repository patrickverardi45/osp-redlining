# TrueLine v2 Session Handoff

**Saved:** 2026-06-12
**Branch:** `feat/truelinev2`
**Pushed engine HEAD:** `972b83449e1bf8ab00def945e5120dc9918f3bd9`
**Verified tests:** `484 passed`

## Guardrails

- Do not merge or deploy.
- Do not touch production `main`.
- Keep all new engine work on `feat/truelinev2`.
- Preserve existing untracked files.

## Shipped State

### M8.15 - reviewer cards and static demo

- The lane-outcome -> reviewer-card bridge is pushed.
- The static reviewer demo sidecar exposes exactly 9 design-stroke cards:
  - 4 `DESIGN_STROKE_REVIEW`
  - 5 `DESIGN_PICK_CARD`
- Stroke cards preserve the lane's evidence-backed geometry and artifact
  references.
- Pick cards remain `SUGGESTION_NOT_PLACEMENT` and carry no stroke geometry
  or image.

### M8.16 - cross-sheet continuation law

- The cross-sheet continuation resolver probe/law is pushed.
- All 16 banked cross-sheet bores were attempted.
- Zero converted to strokes under the current printed evidence.
- This is the banked evidence-backed honest negative: every refusal is typed
  and names the missing relationship.

### M8.17 - segmented far-sheet callout chains

- Segmented far-sheet callout-chain assembly is pushed for `log8` and `log32`.
- Neither bore converted to a stroke.
- Both advanced from `CROSS_SHEET_CONTINUATION_REQUIRED` to
  `STRUCTURE_IDENTITY_BINDING_REQUIRED`.
- Their far-sheet chains are now proven:
  - `log8`: `0+00 -> 1+10 -> 1+76`; `110 + 66 = 176`, plus the `214`-foot
    end segment gives `390` feet total.
  - `log32`: `0+00 -> 1+30 -> 1+77`; `130 + 47 = 177`, plus the `36`-foot
    end segment gives `213` feet total.
- The remaining blocker shared by `log8`, `log32`, and `log42` is
  start-structure identity / per-ladder tick clustering.

### M8.18 - proof-only ladder discriminator seam

- M8.18 is pushed at engine HEAD `b7410a5`.
- Added the proof-only ladder discriminator seam:
  - `truelinev2/extract/ladder_cluster.py`
  - `truelinev2/proof/run_ladder_discriminator_probe.py`
  - `truelinev2/tests/test_ladder_cluster.py`
- The seam is not wired into a placement lane. No strokes were placed.
  No lane wiring was added.
- The all-58 sweep census is unchanged: `13 cross-sheet / 3 structure-required`.
  There is no census change or accepted-log drift.
- `log42` has 0 traceable survivors.
- `log8` and `log32` narrow to the same port HH `NEXTLINK@378,409`, creating a
  cross-bore collision.
- The banked b.9 join refuses `log8` and `log32` on implied-scale because their
  curved end-sheet routes fail the 5% gate.
- The blocker has shifted from start identity to cross-sheet join geometry.

### M8.19 - path-length cross-sheet join Phase 0/1

- M8.19 is pushed at engine HEAD `972b834`.
- Added the proof-only path-length cross-sheet join probe:
  - `truelinev2/proof/run_path_length_join_probe.py`
  - `truelinev2/tests/test_path_length_join.py`
- No lane wiring. No strokes placed.
- The all-58 sweep census is unchanged: `13 cross-sheet / 3 structure-required`.
  There is no census change.
- The current b.9 join failure for `log8` and `log32` is caused by
  chord/implied-scale measurement on curved routes.
- Path-length measurement using `walk_design_path` + `path_length`, with
  the unchanged `cross_sheet_join_verdict` and unchanged 5% tolerance, proves:
  - `log8`: `1.508` vs `1.554`
  - `log32`: `1.499` vs `1.441`
  - `log65` remains proven both ways.
- The remaining blocker is adjudication, not geometry:
  - `log8` and `log32` both bind the same port HH `NEXTLINK@378,409`.
  - The owner must decide/confirm whether this is a valid
    multi-drop/shared-origin terminal.
  - If it is not confirmed, the next capability is a per-bore discriminator
    using intermediate chain stations `1+10` vs `1+30`.

### M8.20 - shared-origin adjudication by extraction

- Added the proof-only shared-origin adjudication probe (G1-G6 PASS):
  - `truelinev2/proof/run_shared_origin_adjudication_probe.py`
  - `truelinev2/tests/test_shared_origin_adjudication.py`
  - `wiki/m8_20_adjudication.md` (the formal adjudication + law specs)
- No lane wiring. No strokes. Census unchanged. All three bores stay
  `STRUCTURE_IDENTITY_BINDING_REQUIRED`.
- EXTRACTED (not inferred): `log8`/`log32` are TWO DISTINCT PRINTED RUNS
  (chains `0+00->1+10->1+76` vs `0+00->1+30->1+77`, both closure-proven,
  each printing `E/W PORT TERMINAL TAIL` + its own `1-1.25"` conduit) over
  ONE drawn alignment (walk dev 0.0 pt; piece Jaccard 1.0; the load-bearing
  independent fact: boundary gap 0.0 pt from two DIFFERENT printed
  equations). "False collision" is REFUTED; placement stays gated on the
  M8.20 Law 1 multi-drop spec (separately authorized implementation).
- The intermediate-station discriminator (`1+10` vs `1+30`) is REJECTED as
  an identity law: it discriminates runs (already proven), not origins —
  there is no second drawn route to bind.
- `log42` sharpened: 13 sheet-2 rivals = 12 `DESIGN_PATH_SEARCH_EXHAUSTED`
  (up to 68 complete paths found; uniqueness uncertifiable) + 1 no-chain.
  Named target: corridor-pruned/junction-bounded unique tracing — a budget
  raise alone would land in `DESIGN_PATH_AMBIGUOUS`.
- Adversarial 3-lens review pre-commit: no blocking findings; hardenings
  landed (pinned G5 taxonomy, TARGETS<->borelog sync assert, edge-uniqueness
  assert, stale-report deletion, replay-honesty wording).

### M8.20 Law 1 - SHARED_ALIGNMENT_MULTI_DROP implemented proof-first

- New files (proof-only; lane/sweep/contracts UNCHANGED):
  - `truelinev2/match/shared_alignment.py` (the pure corpus-level law)
  - `truelinev2/proof/run_shared_alignment_law_probe.py` (G1-G8 PASS)
  - `truelinev2/tests/test_shared_alignment_law.py` (12) +
    `truelinev2/tests/test_conduit_evidence.py` (8)
  - `extract/matchline_join.py` += `parse_conduit_evidence` /
    `chain_conduit_evidence` (Phase-1 grammar hardening)
- Law 1 PROVES `log8`+`log32` -> `SHARED_ALIGNMENT_MULTI_DROP_REVIEW` on
  `NEXTLINK@378,409`, boundaries `{1+76,1+77}`; bijection universe is REAL
  (exactly the two claimed runs); REVIEW-only (`SUGGESTION_NOT_PLACEMENT`,
  auto=False). `log42` never enters (0 survivors -> one bore -> NOT_APPLICABLE).
- Law 2: every positive gate removed -> typed, named pairwise rejection.
  Law 3: intermediate stations only prove distinctness, never split the origin.
- Phase 1 grammar: conduit tokens must be MATERIAL-bound; depth/cover ranges
  (`24-36" MIN. DEPTH` / `DEPTH` / `COVER`) yield no conduit evidence.
- Phase 3: lane/card eligibility NOT flipped (architecture cannot represent a
  corpus-level pairwise multi-drop honestly per-bore; M8.18/M8.19 are not wired
  into `resolve_bore`). Smallest extension NAMED in `wiki/m8_20_adjudication.md`
  §7 (corpus extraction pass + GROUP review card in M8.10/M8.11). All three
  bores stay `STRUCTURE_IDENTITY_BINDING_REQUIRED`; census unchanged.
- No tolerance widened (`JITTER_EQUIV_TOL` reused, tripwire-pinned). No stroke,
  card, grade, or PNG produced. Accepted grades (log25/51/59/65) re-proven.

## Verification

- Tests: `559 passed`.
- M8.20 Law 1 (SHARED_ALIGNMENT_MULTI_DROP) probe G1-G8: PASS.
- M8.20 shared-origin adjudication probe G1-G6: PASS.
- M8.19 path-length cross-sheet join probe G1-G5: PASS.
- M8.18 ladder discriminator probe G1-G6: PASS.
- M8.16/M8.17 continuation probe G1-G7: PASS.
- All-58 sweep G1-G7: PASS; census `25/13/5/5/4/3/1/2 = 58`.
- Design-path adherence: PASS.
- M8.15 cards: PASS.
- M8.10/M8.11: PASS.
- b.9/b.10: PASS.
- Demo artifact: PASS.

## Remaining Blocker Classes

1. `log8`/`log32` shared-origin: Law 1 `SHARED_ALIGNMENT_MULTI_DROP` is now
   IMPLEMENTED + PROVEN proof-first (REVIEW-only, all gates incl. claim
   bijection + hardened conduit grammar). Remaining gate: the §7 payload/card
   extension (corpus extraction pass wiring M8.18/M8.19 + a GROUP review card
   in the M8.10/M8.11 contracts) to SURFACE the REVIEW -- a separately
   authorized milestone. The per-bore lane stays pure (no flip).
2. Uniquely traceable design path through the dense network for `log42`:
   named target is corridor-pruned/junction-bounded unique tracing (12 of 13
   rivals die by search exhaustion with up to 68 complete paths; a budget
   raise alone lands in AMBIGUOUS and is NOT the target).
3. No printed matchline equation:
   `log10`, `log14`, `log61`, `log62`, `log67`, `log68`, `log70`.
   Owner decision required: geo/KMZ corroboration or reviewer pick-cards.
4. Lower-yield printed-evidence gaps:
   `log12`, `log46`, `log60`, `log64`, `log71`, `log72`.

## Recommended Next Lane After Reset

1. Owner decision to SURFACE Law 1: authorize the §7 extension -- a corpus-
   level extraction pass (M8.18 discriminator + M8.19 join, OUTSIDE the
   per-bore lane) feeding `shared_alignment_verdict`, plus a GROUP REVIEW card
   in the M8.10/M8.11 contracts. Opus lane, proof-first, contract-pinned; it
   adds a review surface and never flips the per-bore census.
2. Then (and only after the reviewer confirms a multi-drop) any geometry is a
   further, separate milestone -- two redlines sharing their far-sheet
   alignment; red stroke law unchanged.
3. `log42` needs a Fable lane only when parent-child split-log reconciliation
   + corridor-pruned unique tracing is prioritized; it is NOT unblocked by
   Law 1 (it never enters the law).

## Session Sizing

Fable 5 UltraCode jobs should be split or begin with a 100% token window.
Opus lanes are generally okay, but their scope should still stay tight.

## Current Boundary

No merge, deployment, production-main change, or new engine work is part of
this session save.
