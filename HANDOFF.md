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

### M8.20 §7 - GROUP review card (standalone schema, REVIEW-only)

- New files (proof-only; per-bore contracts/census UNCHANGED):
  - `truelinev2/review/group_review.py` -- schema
    **`truelinev2-shared-alignment-group-review-1`** (`SharedAlignmentGroupCard`
    + `GroupMember` + `build_group_review_card`)
  - `truelinev2/proof/run_shared_alignment_group_review_proof.py` (G1-G8 PASS)
  - `truelinev2/tests/test_shared_alignment_group_review.py` (10)
- A proven Law-1 multi-drop becomes ONE REVIEW group item: members
  `{log8, log32}`, origin `NEXTLINK@378,409`, boundaries `{1+76, 1+77}`. It is a
  STANDALONE schema (NOT the per-bore M8.10/M8.11 payloads -- a group is
  multi-bore; per-bore `ReviewerPayload` carries one `bore_id`).
- REVIEW-only by construction: `auto=False`, frozen `SUGGESTION_NOT_PLACEMENT`,
  action `CONFIRM_OR_REJECT_MULTI_DROP_GROUPING`, `has_geometry=False` /
  `has_strokes=False` + a geometry-key walker -> no coordinates/segments/strokes.
- Each member carries its UNCHANGED per-bore status (validator REFUSES any
  non-blocked status) -> the card never overwrites per-bore truth. Only a
  `V_REVIEW` verdict builds a card (REJECTED/NOT_APPLICABLE -> None); log42 is
  never a member (no survivor -> no claim).
- NOT wired into `resolve_bore`/sweep/reviewer-service/per-bore contracts;
  M8.10 (30/16/.../2), M8.11, M8.15, and the all-58 census re-proven unchanged.
- The real service and additive API/bundle transport follow below. Consumer/UI
  adoption remains separate; no geometry milestone is authorized here.

### M8.20 GROUP REVIEW real service output

- Added `truelinev2/review/group_review_service.py::GroupReviewService`.
- The real service path composes shipped product modules only:
  `extract_group_claims -> shared_alignment_verdict -> build_group_review_card`.
- Emits exactly one `truelinev2-shared-alignment-group-review-1` card for
  `{log8, log32}`, origin `NEXTLINK@378,409`, boundaries `{1+76, 1+77}`.
- `ReviewerBundleService.generate(mode)` is untouched and byte-identical
  before/after group generation; per-bore statuses/census/contracts unchanged.
- log8/log32 remain `STRUCTURE_IDENTITY_BINDING_REQUIRED`; log42 is excluded.
- No proof imports, AUTO, geometry, strokes, segments, PNGs, or KMZ work.
- The additive API/bundle transport is implemented below; consumer/UI adoption
  remains separately authorized.

### M8.20 GROUP REVIEW additive API/bundle transport

- `GET /v2/reviewer/bundle?mode=default_baseline` now includes a separate,
  schema-pinned `group_review` section generated by `GroupReviewService`.
- The nested canonical per-bore `bundle` remains byte-identical.
- The live section contains exactly one REVIEW-only card for `{log8, log32}` at
  `NEXTLINK@378,409`, boundaries `{1+76, 1+77}`.
- log8/log32 stay `STRUCTURE_IDENTITY_BINDING_REQUIRED`; log42 is excluded.
- Strict transport validation forbids AUTO, geometry, strokes, segments, PNGs,
  label/schema drift, and extra card fields.
- Reviewer API mounting remains default-OFF under `TL2_REVIEWER_API_OPTIN`.
- Remaining: consumer/UI adoption is separately authorized; no writeback or
  geometry milestone is included.

### M8.21 - log42 split-log / corridor-pruned trace / frame ownership

- New files (proof-only; lane/sweep/contracts/census UNCHANGED):
  - `truelinev2/extract/corridor_prune.py` -- the M8.20-named corridor
    capability: the existing length law as a piece filter (banked constants
    only, budget and jump cap untouched; proof-consumed, UNWIRED)
  - `truelinev2/proof/run_split_log_corridor_probe.py` (G1-G9 PASS)
  - `truelinev2/tests/test_corridor_prune.py` +
    `test_split_log_corridor_probe.py` (27)
  - `wiki/m8_21_split_log_corridor.md` (the adjudication)
- The owner's printed parent chain is VERIFIED: 270' + 17' (PORT TERMINAL
  TAIL) + 232' (VACANT, class-distinct ADJACENT, claimed by no corpus bore);
  270+17 = 287 = log42 exactly; 519 is arithmetic, never printed.
- Corridor results: log42's 13 candidates all die/survive with POSITIVE
  typed certificates (8 chord-infeasible / 1 out-of-tolerance / 2 finished
  AMBIGUOUS / 1 no-chain / 1 corridor survivor); log8/log32 controls
  byte-identical pruned vs unpruned. Corridor uniqueness is a DIFFERENT
  certificate class (LENGTH_ADMISSIBLE_CORRIDOR) -- Law 1 does not accept
  it; provenance-tagged on every record.
- Adversarial 5-lens panel pre-implementation: the naive "survivor = origin"
  claim was REFUTED by the completeness critic and the refutation is now
  G7-proven: the equation-bound 13"X24"X24" INSTALLER HH (corridor survivor
  NEXTLINK@818,419) is the printed INTERIOR reset at callout-frame 0+46
  (M8.6 interior case; path = footage-46 within 0.5%). New frame-ownership
  law shipped in the probe (unique interior-tick ladder placing the printed
  boundary; y-band selection forbidden).
- log42 stays STRUCTURE_IDENTITY_BINDING_REQUIRED with a SHARPER named
  target: strand discriminator at the callout-frame origin NEXTLINK@819,351
  (DESIGN_PATH_AMBIGUOUS, 4 paths / 2 groups) + owner source re-reads.
- log41: typed SOURCE_DIGIT_REREAD_REQUIRED conflict enumeration
  ({0+44, 0+50, printed 0+46}; no preferred reading -- validator-enforced);
  owner re-read of source photo 2025-12-03_212755 - Jimenez.

### M8.22 - log42 strand discriminator at the callout-frame origin

- New files (proof-only; lane/census/grades/tolerances/budget UNCHANGED):
  - `truelinev2/proof/run_strand_discriminator_probe.py` (G1-G10 PASS)
  - `truelinev2/tests/test_strand_discriminator_probe.py` (11)
  - `wiki/m8_22_strand_discriminator.md`
- RESOLVED the M8.21 named target: log42's origin NEXTLINK@819,351 was
  DESIGN_PATH_AMBIGUOUS (full universe EXHAUSTED). A directional eligibility
  filter (remove conduit pieces entirely behind the printed origin on the
  origin->2+70-terminus chord) traces GROUP 0 uniquely = 272.3 ft (+0.9% vs
  printed 270' = ~46' drop + ~224' east). LICENSED by the printed two-tail
  structure (origin prints 0+00->2+70 270' AND 0+00->5+26 526', each with its
  own matchline -- the West tail is a distinct printed run, not this bore's).
- Adversarial 5-lens panel pre-commit caught that chord projection != station
  (the codebase already refuted projection-ordering, design_path.py:9-11), so
  the law is NOT shipped as a general module: it is probe-local and fires only
  under (G2) the printed multi-tail license, (G5) a per-survivor chord-
  monotonicity certificate + parallel_strand_guard, (G6) robustness at both
  co-located origins. One-sided (conservative NOT_CONNECTED for backward
  routes; never a false survivor); provenance DIRECTIONAL_FORWARD_OF_PRINTED_
  ORIGIN (not M8.18/corridor class). Controls log8/log32 byte-identical.
- log42 stays STRUCTURE_IDENTITY_BINDING_REQUIRED -- strand resolved, bore NOT
  placed. Blocker SHIFTS to the END side: the M8.19 scale-join refuses under
  the correct NEXTLINK terminal_port_hh anchor (6.3%>5%) but the 17-ft end
  segment is below the scale-measurement floor (5% = ~1.2pt draw noise; the
  wrong FLOWER POT anchor flips it to PROVEN). Named-missing = a NON-SCALE
  cross-sheet continuity corroboration for sub-floor segments (the boundary
  equation + closure 270+17=287 already prove the crossing), NOT a tolerance
  widen. Owner 0+00-0+44 re-read does not affect M8.22 (filter uses geometry
  only, never the 44/46 digit).

### M8.23 - log42 END continuity: corroborated but NON-PROMOTING (ABSTAIN)

- New files (proof-only; SAFE ABSTAIN; census frozen; NO REVIEW promotion):
  - `truelinev2/proof/run_end_continuity_abstain_probe.py` (G1-G7 PASS)
  - `truelinev2/tests/test_end_continuity_abstain_probe.py` (6)
  - `wiki/m8_23_end_continuity_abstain.md`
- The owner asked whether a non-scale END-continuity law can move log42 to a
  REVIEW candidate. A 5-lens adversarial panel REFUTED it (2 REFUTED verdicts)
  and the probe pins the refutation as measured fact:
  * the END-scale "6% disagreement" is a PROBE-ONLY artifact -- the SHIPPED
    join has 0 far survivors for log42 (extract_group_claims([log42])=0), so
    it never reaches the scale gate; the 6% story exists only via M8.22's
    Law-1-barred directional survivor.
  * log42's ACTUAL shipped-lane blocker is START-structure-identity (the 0+00
    origin can't be uniquely bound; named_missing mentions START identity, NOT
    scale). Promoting log42 to REVIEW on an END-continuity proof would be a
    FALSE REVIEW candidate (origin identity unknown). Continuity is NOT claimed
    proven (closure 270+17=287 is arithmetic, never sole load-bearing).
- BANKED (the one sound gate the panel validated): the END terminus is
  terminal_port_hh by PRINTED CLASS (bind_end_structure_note(287) -> 'TERMINAL
  6 PORT HH AP-105'; resolve_structure_position(AP-105,terminal_port_hh) ->
  BOUND @(84.6,419.4)); FLOWER POT is excluded by printed class (different CAD
  layer, no PORT-HH/AP at 2+87) -- the '3.4% PROVE' flower pot is the WRONG
  class, red herring SETTLED. Over-fire guard pinned: log32's 36' end segment
  also trips any sub-floor yet stays blocked on START (necessary-not-sufficient).
- Outcome: SAFE ABSTAIN. log42 stays STRUCTURE_IDENTITY_BINDING_REQUIRED; NOT a
  REVIEW candidate. Named missing = the START origin IDENTITY binding (strand
  discriminator at NEXTLINK@819,351 that binds identity not just position; /
  owner bore_log13 re-read). Census frozen; log8/log32 + M8.20 untouched.

## Verification

- Tests: `625 passed`.
- M8.23 END-continuity abstain probe G1-G7: PASS.
- M8.22 strand discriminator probe G1-G10: PASS.
- M8.21 split-log corridor probe G1-G9: PASS.
- M8.20 GROUP REVIEW API/bundle transport proof G1-G8: PASS.
- M8.20 real GROUP reviewer service proof G1-G8: PASS.
- M8.20 §7 GROUP review proof G1-G8: PASS.
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

1. `log8`/`log32` shared-origin: Law 1 + the §7 GROUP review card are now
   IMPLEMENTED + PROVEN proof-first (REVIEW-only standalone contract
   `truelinev2-shared-alignment-group-review-1`; members/origin/boundaries
   proven; per-bore truth + census unchanged). The parallel real service and
   additive API/bundle transport are IMPLEMENTED + PROVEN. Remaining gate:
   authorized consumer/UI adoption; production activation still requires its
   separate auth/tenant decision. The per-bore lane stays pure (no flip); no
   geometry milestone yet.
2. `log42` (CORRECTED by M8.23): the real shipped-lane blocker is
   START-STRUCTURE-IDENTITY -- the 0+00 origin (NEXTLINK@819,351) cannot be
   uniquely bound (11 co-aligned structures, 0 corroborate; identity ABSTAINED,
   DESIGN_PATH_AMBIGUOUS). M8.22's "blocker shifts to END side" was a
   PROBE-ONLY artifact: the shipped join has 0 far survivors for log42, so the
   END-scale gate is never reached. log42 is NOT a REVIEW candidate. The END
   terminus is bound terminal_port_hh by printed class (FLOWER POT excluded by
   class -- red herring settled, M8.23 G3/G4). Named target = a strand
   discriminator that BINDS the START origin IDENTITY (not just position) via
   a lane-accepted path, and/or the owner bore_log13 block-semantics re-read
   (is Segment B's 0+00 the callout-frame origin or the installer reset?).
   The equation-bound installer HH stays the INTERIOR reset at 0+46.
3. No printed matchline equation:
   `log10`, `log14`, `log61`, `log62`, `log67`, `log68`, `log70`.
   Owner decision required: geo/KMZ corroboration or reviewer pick-cards.
4. Lower-yield printed-evidence gaps:
   `log12`, `log46`, `log60`, `log64`, `log71`, `log72`.

## Recommended Next Lane After Reset

0. Expose the parallel GROUP reviewer service through an authorized API/bundle
   transport. Keep the separate schema additive and leave the per-bore
   M8.10/M8.11 bundle byte-identical. Opus lane.
1. Decide whether any eventual UI should consume that transport. This remains
   separate from the engine service milestone and does not authorize geometry.
2. Then (and only after the reviewer confirms a multi-drop) any geometry is a
   further, separate milestone -- two redlines sharing their far-sheet
   alignment; red stroke law unchanged.
3. `log42`: the parent-child split-log reconciliation + corridor lane RAN
   (M8.21). Remaining unlocks are the strand discriminator at
   `NEXTLINK@819,351` and the two owner source re-reads named in
   `wiki/m8_21_split_log_corridor.md` 5. Still NOT unblocked by Law 1.

## Session Sizing

Fable 5 UltraCode jobs should be split or begin with a 100% token window.
Opus lanes are generally okay, but their scope should still stay tight.

## Current Boundary

No merge, deployment, production-main change, or new engine work is part of
this session save.
