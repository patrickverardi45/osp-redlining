# TrueLine v2 Session Handoff

**Saved:** 2026-06-13
**Branch:** `feat/truelinev2`
**Pushed engine HEAD:** `2b3f6c9` (M9.5 cross-sheet feasibility, proof-only); advanced by
this M9.6 run-assembly API-transport commit (additive, default-OFF, read-only). The
intervening M9.2→M9.5 milestones are recorded in `wiki/current-sprint.md` + the
`wiki/m9_*.md` docs.
**Verified tests:** `797 passed`

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

### M8.24 - log42 START origin identity NOT bindable (ABSTAIN + reframe)

- New files (proof-only; SAFE ABSTAIN; census frozen; NO promotion):
  - `truelinev2/proof/run_origin_identity_abstain_probe.py` (G1-G7 PASS)
  - `truelinev2/tests/test_origin_identity_abstain_probe.py` (6)
  - `wiki/m8_24_origin_identity_abstain.md`
- ANSWER to "can START origin identity be bound through lane-accepted
  evidence?": NO. The dominant shipped-lane abstain is the cross_sheet_origin
  corroboration-band refusal (11 sheet-2 structures reach the matchline, 0
  corroborate). The 0+00 origin is printed-UNIDENTIFIED four ways:
  bind_origin_by_parent_station(0.0)=REQUIRED (no =0+00 parent==0),
  bind_end_structure_note(0.0,sheet2)=REQUIRED, no AP at the origin
  (AP-106/107 are 338/370 pt away), and the origin NEXTLINK symbol is
  unidentified by BOTH label AND fill (None/white/black, neither installer-red
  nor terminal-blue).
- REFRAME (4-lens panel, all SOUND, 0 blocking): log42's only printed-bound
  structure is its END terminal (6 PORT HH AP-105 @2+87). NOT a universal
  "terminal tails are free-origin" law -- log8/log32 share the unidentified-
  origin situation (their M8.20 card is REVIEW-only for the same reason). The
  "bind the origin" approach M8.21/22/23 circled is the wrong frame.
- Owner Segment-B answer: Segment B's 0+00 = the callout-frame ORIGIN (span
  287=270+17 + bound END terminal + interior installer reset), NOT the
  installer reset, NOT from the log41 44/46 digit (separate
  SOURCE_DIGIT_REREAD_REQUIRED).
- Named NEXT capability: an ORIGIN-SYMBOL-IDENTITY binder (far-sheet origin
  structure from the bound END terminal via a lane-accepted frame relation the
  M8.2f classifier rejects on the (1,2) hop). Explicitly NOT M8.5 reverse_anchor
  (footage START-position, identity-agnostic), NOT station_axis, NOT the M8.22
  directional filter (all 3 already refuse). Latent cross-frame false-bind
  hazard named (sheet-1 STA 0+00 SPLICE note saved only by _classify_label=None
  -> a future frame-ownership gate). Census frozen; log8/log32 + M8.20 untouched.

### M8.25 - bore_log17 family (log43/log44) CLOSED as both abstaining

- New files (proof-only; SAFE CLOSURE-ABSTAIN; census frozen; NO promotion):
  - `truelinev2/proof/run_log17_family_abstain_probe.py` (G1-G7 PASS)
  - `truelinev2/tests/test_log17_family_abstain_probe.py` (6)
  - `wiki/m8_25_log17_family_abstain.md`
- PREMISE CORRECTED (4-agent recon): log43 is NOT "resolved/grade A" in the
  real engine -- design_grades_accepted = {log25,51,59,65}; the lone mention is
  a not-built design mock (card body shows log51's data).
- Both abstain, DIFFERENT per-bore reasons: log43 (print 10, 40+00->59+19) =
  END_IDENTITY_UNPRINTED + OUT_OF_CLASS/M87_STATION_TICK_NOT_FOUND, a SOURCE-
  quality abstain (print-10 axis stops at 45+33; 45+33->59+19 is a printed
  void; "continues bore_log16" REFUTED, log16 ends 39+79; discontinuous multi-
  drive). log44 (print 18, 0+00->3+25, 325') = END_IDENTITY_UNPRINTED +
  OUT_OF_CLASS/M87_MULTIPLE_PATHS_PICK_CARD, a SOURCE-vs-PLAN mismatch (325'
  matches no print-18 run; chain 0+00->3+25=CALLOUT_CHAIN_NONE; end inside 2
  distinct-class intervals 503' 1-1.25 / 68' 2-1.25).
- FAMILY RULE = GROUPING-ONLY (run-segment-hierarchy S8; engine consumes no
  family/split/daily_bundle relation; each child standalone on its own printed
  evidence). NO safe family/child law places a member. Blocker is PER-BORE:
  placeable split-siblings log51/59/65 are STROKE_ELIGIBLE_REVIEW.
- Generalization: ~13 END_IDENTITY_UNPRINTED children corpus-wide, closable
  only if a printed terminal/AP-HH end-structure layer is found (a new
  adversarially-proven end-identity gate) -- not a family lever. Census frozen;
  log8/log32/log42 + M8.20 untouched.

### M8.26 - END_IDENTITY_UNPRINTED population CLOSED as honest-negative

- New files (proof-only; HONEST NEGATIVE; census frozen; NO promotion):
  - `truelinev2/proof/run_end_identity_population_probe.py` (G1-G6 PASS)
  - `truelinev2/tests/test_end_identity_population_probe.py` (6, offline)
  - `wiki/m8_26_end_identity_population_honest_negative.md`
- Enumerated the 25 END_IDENTITY_UNPRINTED bores live + dumped complete end-
  station printed evidence per referenced sheet. The named lever (a printed
  terminal/AP-HH layer the grammar excludes) DOES NOT EXIST here:
  - G3: ZERO AP-id terminals at any of the 25 ends (ending + starting callouts);
    zero AP position-chains resolve -> frame/layer ownership never proven.
  - G4: exactly ONE printed end NOTE the grammar binds = log27
    (`NEXTLINK HH PROP. SPLICE POINT`), class OUTSIDE class_keywords; the
    `NEXTLINK` symbol layer shares red/blue fills with installer_hh/
    terminal_port_hh (no discriminator), no AP id, no end tick -> class-
    ambiguous + unlocatable. (log27 already places via M8.5/M8.8 opt-ins.)
  - G5: zero clean gate candidates; the only ending-callout keyword
    (log3/log4 `PORT TERMINAL TAIL`) is a CONDUIT class, not a handhole.
- Adversarial workflow (construct->refute->synthesize): 0 gate proposals of 5
  candidate classes; 0 survived the skeptic panel. Panel live-inspection
  corroboration: log3/log4's real PORT HHs are rival AP-137/AP-138 (>=2 ->
  abstain); log5/log15/log30 nearest end-tick symbol is a FLOWER POT / 200+pt
  (wrong-class / unowned).
- Taxonomy (25): 15 pure printed void · 8 frame-reset `=0+00` ends · 5 run/
  continuation callouts · 1 unmodeled printed note (log27). 23 of 25 are
  KMZ/geo or SOURCE_REVIEW lanes; the single redline-engine lever is the
  log27 NEXTLINK class-fill disambiguation + a 13+55 station tick (clears at
  most 1 of 25; changes no redline). Census frozen; log8/log32/log42 + M8.20
  untouched.

### M8.27 - final all-58 engine truth table + completion map

- New files (proof-only; adversarially audited FAITHFUL; census frozen):
  - `truelinev2/proof/run_final_engine_truth_table.py` (G1-G15 PASS)
  - `truelinev2/tests/test_final_engine_truth_table.py` (8, offline)
  - `wiki/m8_27_final_engine_truth_table.md`
- ONE authoritative completion map joining 3 orthogonal axes per bore WITHOUT
  altering any: PRODUCT (M8.11 fullest_safe_review -> one M8.10 lane;
  authoritative), ROUTE-STROKE (symbol_conduit lane; proof-only, default-OFF,
  UNWIRED -- STROKE_ELIGIBLE is never a product placement), GROUP (M8.20 card,
  the 59th review item). completion_bucket is a pure derived UI-readiness VIEW.
- 58 vs 59 resolved: exactly 58 production logs (log2..log72, 13 numbering gaps,
  no dups); the 59th is the M8.20 group card. 58 per-bore + 1 card = 59 items.
- Buckets: DRAWABLE_REVIEW 30 / PICK_CARD_REVIEW 17 / HUMAN_ADJUSTABLE_REVIEW 6 /
  SOURCE_OR_KMZ_REQUIRED 3 / SOURCE_REVIEW_REQUIRED 2 (+ 1 GROUP_REVIEW).
  Headlines: drawable 30, review-ready 53, source/kmz/owner 5, engine-law 4
  (route-stroke doctrine ONLY -- log7/8/32/42 already place; ZERO bores product-
  blocked on engine law).
- Reconciliations gated: log8/32/42 product PLACED + stroke STRUCTURE_IDENTITY
  (log8/32 group, log42 excluded); log43/44 OUT_OF_CLASS+END_IDENTITY+
  SOURCE_OR_KMZ; END_IDENTITY 25 honest-negative; default_baseline 24 + stroke
  census unchanged; M8.10/M8.11/M8.14.c/M8.20 contracts untouched.
- Audit fix: log11 was mis-bucketed ENGINE_LAW_REQUIRED; its M8.7 verdict is
  MULTIPLE_PATHS_PICK_CARD (routing-order OUT_OF_CLASS, no source defect) ->
  re-bucketed PICK_CARD_REVIEW (review-eligible now). Gated by G15.

### M9.0 - KMZ<->PDF correlation architecture (first geo-lane milestone)

- New files (proof-only; KMZ reader UNWIRED; zero bores moved; M8.27 + census +
  contracts untouched):
  - `truelinev2/extract/kmz.py` (KMZ feature reader; pure, dialect-injected)
  - `truelinev2/proof/run_kmz_correlation_audit.py` (G1-G7 + G2b PASS)
  - `truelinev2/tests/test_kmz_correlation.py` (12)
  - `wiki/m9_0_kmz_pdf_correlation_architecture.md`
- KMZ assets FOUND: the Brenham Phase 5 design KMZ (1116 features; tracked
  fixture brenham_phase5_source_truth.kmz == data/uploads design KMZ). v2 had
  ingested no KMZ; this begins the geo lane. Geo lon/lat, NO stationing,
  attributes in <description> HTML tables.
- Taxonomy: 576 structure points + 539 routes; folders map 1:1 to PDF classes
  (terminal_port_hh 64, installer_hh 37, splice_hh 16, flower_pot 158; Vacant
  Pipe routes 58 == bore count).
- ZERO-FALSE JOIN KEY = TWO-FIELD agreement: PDF 'AP-NNN SPLICE LOC MM' <-> KMZ
  terminal_port_hh with AP Number NNN AND splice_loc MM. AP unique across 64
  terminals (0 collisions); the splice-loc field is load-bearing because the
  same-AP splice twin is 28-181m away (NOT co-located) and the PDF prints no
  terminal class keyword. PROVEN on controls log7 (AP-163/SPLICE LOC 46) +
  log42 (AP-105/SPLICE LOC 25).
- Per-target (ZERO moved): log37/38 SOURCE_REVIEW_ONLY (source unparseable, no
  join key); log43 SOURCE_REVIEW_ONLY (void end 59+19, multi-drive source);
  log44 KMZ_ENDPOINT_BRIDGE candidate (terminals in KMZ but 325' source-vs-plan
  mismatch -> after source fix); log68 KMZ_MATCHLINE_SUBSTITUTE candidate
  (cross-sheet no-equation; needs both endpoints bound). Future-eligible:
  log44, log68. Source-only: log37/38/43.
- Adversarial audit: dispositions zero-false; it CAUGHT an earlier draft that
  called the splice/terminal pair "co-located" and assumed a PDF class keyword
  the plan never prints -> replaced with the verified two-field join (G2b banks
  the twin distances). Next: ship KMZ_AP_STRUCTURE_JOIN, then
  KMZ_MATCHLINE_SUBSTITUTE for the cross-sheet class (log68 + log10/14/61/62/
  67/68/70) + route-stroke geometry for log8/32/42 via KMZ AP terminals.

### M9.1 - KMZ_AP_STRUCTURE_JOIN shipped extractor (universal core + profile)

- New/changed files (engine; UNWIRED; zero bores moved; M8.27 + M9.0 + census +
  contracts untouched):
  - `truelinev2/match/kmz_structure_join.py` (NEW; universal core, zero literals)
  - `truelinev2/extract/kmz.py` (added `terminal_class` to the KMZ profile)
  - `truelinev2/proof/run_kmz_structure_join_proof.py` (G1-G10 PASS)
  - `truelinev2/tests/test_kmz_structure_join.py` (12)
  - `wiki/m9_1_kmz_ap_structure_join.md`
- The law: join_terminal binds PDF 'AP-NNN SPLICE LOC MM' to EXACTLY ONE
  terminal-class KMZ structure carrying BOTH ids. Typed refusals for AP-only /
  splice-only / missing / ambiguous / no-terminal-class. Class-scoped (the
  same-AP splice twin 28-181m away is never bound); no coordinate read in the
  bind; uniqueness-mandatory; self-dup AP collapses to one candidate.
- Universal core / profile separation: match/ holds zero customer literals
  (drift guard); terminal_class + ap/splice grammars are injected; Brenham is
  only a profile/fixture. Proven on a SYNTHETIC non-Brenham model.
- AUDIT FIX (load-bearing): the first draft collapsed splice-loc to a trailing
  integer -> the adversarial audit demonstrated a LIVE false bind on a zone-
  prefixed profile (A-12/B-12 -> 12) and a whole-plan abstain for non-integer
  ids (Loc 5A). Fixed to whole opaque-TOKEN comparison (zone/alpha-safe);
  Brenham binding byte-identical; G10 regression locks it.
- Controls log7 (AP-163 SPLICE LOC 46) + log42 (AP-105 SPLICE LOC 25) BIND;
  corpus 64 terminals, 0 (ap,splice) collisions, self-bind bijection clean.
  UNWIRED (no placement path imports it); zero bores moved.

### M9.5 - CROSS_SHEET_COMPETING frame-graph feasibility (proof-only; FEASIBLE, zero yield)

- New files (proof-only; no core/service change; zero bores moved; M8.27 + product
  lanes + M9.0–M9.4.2 + census untouched):
  - `truelinev2/proof/run_cross_sheet_competing_phase0.py` (G1–G14 PASS)
  - `truelinev2/tests/test_cross_sheet_competing_phase0.py` (19; offline pure + posture)
  - `wiki/m9_5_cross_sheet_competing_phase0.md`
- The question: can the M9.4.1/M9.4.2 FRAME-SCOPED competing-departure limitation be
  SAFELY lifted using the SHIPPED `match.frames` graph to enumerate cross-sheet
  departures at a shared terminal — by FRAME-PROVEN station translation, never proximity,
  never raw-number equality?
- Verdict **`SAFE_FRAME_GRAPH_EXTENSION_FEASIBLE`** (derived from gates; all three
  verdict tokens reachable via `decide_verdict`): a safe frame-equivalence relation EXISTS
  (AP-117 sheet 24↔25, component {25,26,27,28}; AP-163 sheet 10↔9/12/13, component
  {7,8,9,12,13,14}). The mechanism is non-vacuous (synthetic G10: a real frame-translated
  competitor → 1; raw-equality decoy / 3 ft near-miss / isolated anchor → 0).
- BUT zero corpus yield: EXACT cross-sheet departures = 0 at all 3 terminals, single-hop
  (G5) AND full multi-hop component (G12). The three outcomes are UNCHANGED (2 candidate +
  1 drop, `competing_departures == 1`); log65 stays a drop. **Recommendation: DEFER the
  core widen** — the M9.4.1/M9.4.2 frame-scoped guard stays exactly as shipped.
- AP-152 sub-gap: terminal sheet 15 is isolated (its only matchline equation
  `STA 4+02/4+16` is MULTI-linked → MEDIUM, no edge); both sheets 15 and 16 (departing
  log27's frame) are isolated. Missing target = a UNIQUELY-linked HIGH matchline edge on
  sheets 15/16. Scope boundary (G13): the 4 clean END terminals AP-105/121/148/157 have
  no junction and are out of scope for this junction-based search.
- Adversarial 5-lens audit: verdict confirmed sound; every real finding (the
  "already-counted" overclaim, single-hop scope, dead BLOCKED token, dead-end terminals,
  AP-152 imprecision) was converted to a MEASURED gate pre-commit (G6/G12/G13/G7 +
  `decide_verdict`).

### M9.6 - RUN-ASSEMBLY review-card read-only API/transport contract (additive; default-OFF)

- New flag + files (additive transport; no core/service change; per-bore bundle byte-identical;
  zero bores moved; M8.27 + product lanes + M9.4.1/M9.4.2 cards + the M9.5 result untouched):
  - `truelinev2/config.py` (+6): `run_assembly_api_optin` (env `TL2_RUN_ASSEMBLY_API_OPTIN`),
    default OFF, in `Settings` + `from_env` + `for_proof`.
  - `truelinev2/api/app.py` (+4): one gated `include_router` block mirroring `reviewer_api_optin`.
  - `truelinev2/proof/export_run_assembly_cards_json.py` (NEW): `generate_export`/`build_export`/
    `validate_export` -- wraps `RunAssemblyReviewService.generate()` cards in the transport
    envelope `truelinev2-web-run-assembly-export-1`; fail-closed validation.
  - `truelinev2/api/run_assembly_routes.py` (NEW): context-free `GET /v2/reviewer/run-assembly`,
    consumes + (re)validates the export, memoizes on `app.state`, 503 on inputs missing or a
    poisoned cache.
  - `truelinev2/proof/run_run_assembly_api_contract.py` (NEW): G1-G12 PASS.
  - `truelinev2/tests/test_run_assembly_api.py` (NEW): 19 offline tests.
- The transport CONSUMES the service verbatim (reimplements no run-assembly logic; G12
  byte-compares the envelope cards full-dict against a direct `service.generate()`). It emits the
  EXISTING M9.4.1 card schema (`truelinev2-run-assembly-review-1`), never a new product bucket.
- Exact cards (unchanged): log10->log27 @AP-152 + log72->log39 @AP-117 (RUN_CONTINUATION_CANDIDATE)
  + log7->log65 @AP-163 (JUNCTION_DROP_BRANCH; log65 prints `FOR FIBER DROP`). `competing_departures
  == 1` on all (M9.5 frame-scoped result preserved).
- Default-OFF: `create_app(flag OFF)` mounts no route; the two opt-in flags are independent; the
  route is context-free (no auth/tenant/db/writes), mirroring the existing reviewer routes.
- Adversarial 5-lens audit: confirmed sound; 3 low-severity findings -> fixes + gates pre-commit
  (PNG-key guard asymmetry -> key-side check + G5 vector; poisoned-cache -> 503; full-dict verbatim
  gate G12). Recorded-not-a-defect: the route transitively loads `truelinev2.render` via the shared
  proof-helper chain exactly as the existing `reviewer_routes` does -- no new regression; removing
  it is out-of-scope cleanup.
- Posture: full v2 suite 797 passed (794 + 3); guards green; M9.4.2 + M9.5 proofs PASS. ZERO
  changes to `match/`/`schema/`. No frontend/Vercel/UI, no deploy, no main/v1, no placement/AUTO/
  geometry/PNG, no product-bucket movement, no reviewer-bundle mutation, no cross-sheet/M9.2 widen.
- Next: a frontend/Vercel UI rendering these cards is a SEPARATE, authorized milestone; not begun.

## Verification

- Tests: `675 passed`.
- M9.1 KMZ structure-join proof G1-G10: PASS (universal; controls bind; AP-only/
  splice-only/proximity refused; zone/alpha safe; UNWIRED; zero moves).
- M9.0 KMZ correlation audit G1-G7 + G2b: PASS (zero bores moved; reader UNWIRED).
- M8.27 final engine truth table G1-G15: PASS (audited FAITHFUL).
- M8.26 END_IDENTITY_UNPRINTED population probe G1-G6: PASS (honest negative).
- M8.25 bore_log17 family abstain probe G1-G7: PASS.
- M8.24 origin-identity abstain probe G1-G7: PASS.
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
2. `log42` (RESOLVED-TO-ABSTAIN by M8.24): the START origin identity is NOT
   bindable by any lane-accepted printed path -- the 0+00 origin is printed-
   UNIDENTIFIED four ways (no =0+00 parent==0 equation; no STA 0+00 structure
   note; no AP at the origin; the origin symbol unidentified by both label AND
   fill). log42's ONLY printed-bound structure is its END terminal (6 PORT HH
   AP-105 @2+87). The owner Segment-B question is answered: Segment B's 0+00 =
   the callout-frame ORIGIN (span 287=270+17), installer reset interior at
   0+46. NOT a REVIEW candidate. The named next capability is an ORIGIN-SYMBOL-
   IDENTITY binder (far-sheet origin structure from the bound END terminal via
   a lane-accepted frame relation) -- net-new work, NOT M8.5 reverse_anchor /
   station_axis / the M8.22 directional filter (all already refuse). The "bind
   the origin" approach M8.21/22/23 circled is the wrong frame; log42 is a
   terminal tail whose identity anchor is its END.
3. No printed matchline equation:
   `log10`, `log14`, `log61`, `log62`, `log67`, `log68`, `log70`.
   **M9.2 Phase 0 (`run_kmz_matchline_substitute_phase0`, G1–G7 PASS) resolved
   the geo/KMZ-corroboration half as an HONEST NEGATIVE.** Strict no-equation
   class is 6 bores (`log14/61/62/67/68/70`); `log10` is `NOT_IN_CLASS` (a
   printed-identity matchline path whose END binds `AP-152` → a future
   single-anchor / endpoint-bridge candidate). 0/6 bind a terminal at BOTH
   endpoints (their endpoints are non-terminal drop structures — flower pot /
   installer HH — with no AP+splice id), and the KMZ has no non-geometric
   route↔structure linkage, so `KMZ_MATCHLINE_SUBSTITUTE` is not safely
   satisfiable from current printed evidence. No extractor shipped; zero bores
   moved. Forward lever: a START/END terminus-attribution model (see
   `wiki/m9_2_kmz_matchline_substitute_phase0.md`). Remaining owner choice for
   this class: reviewer pick-cards.
   **M9.3 Phase 0 (`run_terminus_attribution_phase0`, G1–G11 PASS) built that
   forward lever as a POSITIVE proof** (see `wiki/m9_3_terminus_attribution_phase0.md`):
   the station-note-frame attribution yields **7 clean terminal-END attributions,
   each KMZ-join BOUND to a unique terminal** (log42/72/12/2/10/57/7 →
   AP-105/117/121/148/152/157/163), correctly REJECTS log68's flat-scan AP-148
   (owns STA 20+71 = log2's terminal), and surfaces a PDF↔KMZ contradiction
   (log46: PDF `AP-161 SPLICE LOC 35` vs KMZ `Splice Loc 45`). Direction rule:
   a terminal is end-of-feed, so a terminal at a START is a `JUNCTION_ORIGIN`
   (3 found: log27→log10, log39→log72, log65→log7 — bore-to-bore junctions for a
   run-assembly lane), never the START bore's identity. **Deferred to M9.3.1**
   (Phase 0 proves, does not ship); M9.3.1 must inject the note-detection
   keyword set (`structure_anchor._STRUCTURE_WORDS`, the one core literal) +
   AP/splice/station grammars, and gate the END-direction + one-terminal-per-END
   uniqueness invariant. None of the 6 no-equation bores attributes (their ends
   are non-terminal), so M9.2's negative stands.
   **M9.3.1 SHIPPED the extractor** (`match/terminus_attribution.py`, universal
   core + injected `extract/terminus_profile.py` `BRENHAM_TERMINUS_PROFILE`; proof
   `run_terminus_attribution_extract`, G1–G12 PASS; see
   `wiki/m9_3_1_terminus_attribution_extractor.md`). Convention-agnostic (zero plan
   literals; AP id type is profile-injected via `ap_cast` — proven on numeric AND
   zone/alpha-AP synthetic profiles; the M9.3.1 audit caught + fixed an AP-as-int
   coupling, parallel to the M9.1 splice-token fix). Reproduces the M9.3
   bore-disposition census + all controls (7 attributed / 3 junctions / log46
   contradiction / log68 rejection / log44 source-contradiction / 44 rejected);
   per-endpoint taxonomy refined (adds `NON_TERMINAL_ENDPOINT`). **UNWIRED/unconsumed**
   (no opt-in flag; nothing imports it); composes the M9.1 join, so two over-broad
   phase-0 unwired-guards were narrowed to the placement-path scope (matching the
   authoritative `test_kmz_structure_join` test). Full suite 717. Zero bores moved.
   **M9.4 Phase 0 (`run_run_assembly_phase0`, G1–G10 PASS) proved the gated
   REVIEW-only run-assembly lane is feasible** (see `wiki/m9_4_run_assembly_phase0.md`;
   no lane shipped — deferred to M9.4.1). The 3 junctions emit as SHARED-TERMINAL-NODE
   evidence (END→START), evidence-only, no bucket/AUTO/geometry: **2
   `RUN_ASSEMBLY_REVIEW_CANDIDATE`** (log10→log27 @AP152, log72→log39 @AP117; departure
   run class undetermined — the reviewer classifies, NO continuity asserted) + **1
   `JUNCTION_DROP_BRANCH`** (log7→log65 @AP163 — the adversarial audit caught that
   log65 is a printed `FOR FIBER DROP` lateral, 199′=span, NOT the trunk continuing).
   The audit also added a `SELF_JUNCTION_REFUSED` gate.
   **M9.4.1 SHIPPED the convention-agnostic run-assembly core + an M8.20-style review
   card** (`match/run_assembly.py`, `review/run_assembly_review.py`, schema
   `truelinev2-run-assembly-review-1`; proof `run_run_assembly_extract` G1–G11 PASS; see
   `wiki/m9_4_1_run_assembly_extractor.md`). The drop-marker grammar is now profile-
   injected (`TerminusProfile.drop_markers`; the core holds zero drop literal). The
   competing guard enumerates physical departures WITHIN the terminal's own frame (the
   END bore's sheets), beyond only JUNCTION_ORIGIN starts — on Brenham 1/terminal,
   reproducing the 3 relations exactly (2 candidates + the log7→log65 drop branch,
   non-promotable). **Named limitation (honest, pinned):** a cross-sheet lateral drawn
   outside the END bore's frame is not yet enumerated (a station token is frame-local; a
   corpus-wide scan would false-positive — the M9.2 trap) → the M9.2 frame-equation graph
   is the open target. Core is UNWIRED/unconsumed (no resolve_bore / sweep / reviewer-
   service / engine imports it). 8-lens adversarial audit: 7 sound, 1 low-severity
   overclaim ("ALL departures") corrected pre-commit. Full suite 751; zero bores moved;
   M9.3.1 census + M8.11 lanes + M9.2 negative all intact.
   **M9.4.2 SHIPPED the reviewer-service SURFACE for the run-assembly cards**
   (`review/run_assembly_review_service.py` `RunAssemblyReviewService.generate()`; proof
   `run_run_assembly_review_service_proof` G1–G10 PASS; see
   `wiki/m9_4_2_run_assembly_review_service.md`). A STANDALONE parallel service (the M8.20
   `GroupReviewService` precedent) composing `attribute_bore → extract_run_assembly →
   build_run_assembly_cards` → the exact 3 cards (log10→log27 @AP-152 + log72→log39 @AP-117
   CANDIDATE; log7→log65 @AP-163 DROP_BRANCH). REVIEW/evidence-only, frozen
   `SUGGESTION_NOT_PLACEMENT`, schema `truelinev2-run-assembly-review-1` (disjoint). The
   per-bore M8.10/M8.11 bundle is BYTE-IDENTICAL before/after (proof G1); default counts
   `14/10/32/2=24` + fullest lanes `30/16/6/4/2` unchanged (G6, live re-verification);
   `reviewer_service.py` not modified. UNWIRED (no placement-path module imports it; it
   imports no `resolve_bore`/`run_match`/frame graph — strictly LESS wired than its M8.20
   precedent). KMZ model + profile + banked source-contradiction set INJECTED (zero
   literals). Frame-scoped competing guard PRESERVED (each card `competing_departures==1`;
   no cross-sheet/M9.2 widen). 6-lens adversarial audit: 0 findings. Full suite 759; zero
   bores moved; zero product-bucket movement. NO UI/API/transport (a separate, authorized
   milestone) — the surface emits cards, nothing more.
4. Lower-yield printed-evidence gaps:
   `log12`, `log46`, `log60`, `log64`, `log71`, `log72`.
5. `END_IDENTITY_UNPRINTED` (25 bores): CLOSED as honest-negative by M8.26 --
   no zero-false terminal/AP-HH end-identity gate exists; 23 of 25 are KMZ/geo
   or SOURCE_REVIEW. The single redline-engine lever is `log27`: disambiguate
   the `NEXTLINK` symbol-layer class-fill (distinct color / printed class
   id_token / structure-id token) AND obtain a drawn axis station tick at 13+55
   on sheet 16 (currently absent). Both required; clears at most 1 of 25 and
   changes no redline (log27 already places via opt-ins).

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
