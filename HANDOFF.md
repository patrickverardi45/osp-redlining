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

## Verification

- Tests: `581 passed`.
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

0. Expose the parallel GROUP reviewer service through an authorized API/bundle
   transport. Keep the separate schema additive and leave the per-bore
   M8.10/M8.11 bundle byte-identical. Opus lane.
1. Decide whether any eventual UI should consume that transport. This remains
   separate from the engine service milestone and does not authorize geometry.
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
