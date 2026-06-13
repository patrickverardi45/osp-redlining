# M8.20 Adjudication: Shared Origin / Start Collision (log8 / log32 / log42)

Status: **ADJUDICATED BY EXTRACTION — placement remains gated.** Proof-only;
the lane is unchanged; all three bores stay
`STRUCTURE_IDENTITY_BINDING_REQUIRED`; zero strokes; zero census change.

Probe: `truelinev2/proof/run_shared_origin_adjudication_probe.py` (G1–G6 PASS)
Report: `data/outputs/shared_origin_adjudication_probe/shared_origin_adjudication_probe.json`
Tests: `truelinev2/tests/test_shared_origin_adjudication.py`

## 1. What the extraction proved (facts, not inference)

The M8.18/M8.19 shorthand "log8 and log32 collide on `NEXTLINK@378,409`"
under-described the evidence. The M8.20 probe RETAINED the walked geometry
that earlier probes discarded and measured:

| Fact | Measured value | Gate |
|---|---|---|
| Walk-vs-walk max cross-deviation (log8 vs log32, sheet 18) | **0.0 pt** (≤ `JITTER_EQUIV_TOL` 4.0) | G3 |
| Visited-piece Jaccard | **1.0** | G3 |
| Matchline boundary-point gap | **0.0 pt** | G3 |
| Printed chains | log8 `0+00→1+10→1+76` (110+66) vs log32 `0+00→1+30→1+77` (130+47) — **distinct hops, distinct boundary stations, both closure-proven** | G4 |
| Printed origin class (both chains, hop 1, verbatim) | **`E/W PORT TERMINAL TAIL`** | G4 notes |
| Printed per-run conduit (both chains, every hop) | **`1-1.25"`** (depth ranges `24-36" MIN. DEPTH` excluded by grammar) | G4 |
| log42 rival deaths (sheet 2, 13 candidates) | **12 × `DESIGN_PATH_SEARCH_EXHAUSTED`** (several with ≥1 complete path found; 3 candidates explode to 68 found paths), **1 × `NO_CONDUIT_CHAIN_TO_MATCHLINE`** | G5 |

**Finding:** log8 and log32 are TWO DISTINCT PRINTED RUNS over ONE drawn
alignment from ONE shared origin structure. The plan draws shared alignments
once and enumerates the runs in print. This is a SHARED-ALIGNMENT duo, not a
wrong-candidate selection.

**Honesty note (comparison construction — adversarially verified):** once
both bores independently select the same survivor structure, the two walks
share inputs (same footprint midpoint, same pieces, coincident `bnd`), so
the 0.0 pt deviation and 1.0 Jaccard are a DETERMINISTIC REPLAY, not
independent measurements. The LOAD-BEARING independent clause is the
**boundary-point gap of 0.0 pt**: two DIFFERENT printed equations (`1+76`
vs `1+77`) independently resolve to one physical matchline point — the
DIVERGENT counterfactual was live (different equations selecting different
matchlines/chains would have produced distinct walks). Together with the
per-bore expected lengths (253.4 / 254.9 pt) corroborating the same 265.7 pt
walk, "one drawn alignment" is now a regression-pinned fact. The chain notes
and the per-candidate taxonomy are the genuinely new extracted evidence.

## 2. Law 1 — valid shared-origin / multi-drop terminal: SPECIFIED

A future, separately authorized `SHARED_ALIGNMENT_MULTI_DROP` evidence law
may bind N > 1 bores to one origin structure iff ALL of:

1. **Per-bore gates unchanged.** Each bore independently passes the existing
   chain: M8.17 uniqueness-mandatory callout chain with per-hop closure
   (0.5 ft, unchanged); M8.18-class single design-path survivor at
   `DESIGN_LENGTH_REL_TOL` (unchanged); M8.19 path-length join at
   `JOIN_SCALE_REL_TOL` 0.05 (unchanged). No gate is weakened for the group.
   (M8.21 vocabulary note: "M8.18-class survivor" means FULL-UNIVERSE
   survivorship from a finished unpruned search; the M8.21 corridor's
   `LENGTH_ADMISSIBLE_CORRIDOR` certificates are a DIFFERENT class this
   gate does not accept — see `wiki/m8_21_split_log_corridor.md` §2.)
2. **Measured shared alignment.** All N retained walks are pairwise
   jitter-equivalent (≤ `JITTER_EQUIV_TOL`, structural weld-contact scale,
   never loosened) AND boundary points coincide within the same band. If any
   pair is divergent, the law does not apply (distinct drawn drops are not a
   collision; each proceeds under existing per-bore law).
3. **Distinct printed runs.** N uniqueness-mandatory chains with pairwise
   different hop sets AND pairwise different boundary stations, each
   footage-closed. The plan itself must enumerate N runs.
4. **Positive printed multi-run evidence.** Every claiming chain carries its
   own printed conduit statement (here `1-1.25"` per hop) and the printed
   origin-class token names a multi-port-capable origin (here
   `E/W PORT TERMINAL TAIL`). Absence for ANY claimant → ALL abstain.
   PRE-LAW CLOSE ITEM: the M8.20 token extraction is descriptive — its
   grammar must be hardened before any law consumes it (depth ranges not
   followed by `MIN` would false-positive; fraction notation `1-1/4"` is
   missed).
5. **Claim bijection.** Every printed chain from the origin's `0+00` to a
   boundary on that matchline is claimed by exactly one corpus bore; an
   unclaimed printed chain or a doubly-claimed chain → ALL abstain
   (the shared-survivor fact alone is never proof — selection is necessary,
   not sufficient).
6. **Outcome.** REVIEW-only, never AUTO; detection is corpus-level (the lane
   `resolve_bore` is per-bore by design — the collision detector lives in
   the orchestrator above it, which already receives machine-readable
   rivals/survivors).

## 3. Law 2 — false-collision rejection: SPECIFIED

Rejection is **pairwise at the shared structure** (never corpus-wide).
Bores sharing a survivor are BOTH refused (typed, named-missing, status
unchanged) when any Law-1 gate fails: divergent walks with identical
survivor claims; non-distinct printed chains; missing per-run conduit
statements; claim-bijection failure. The refusal names the exact failed
gate as the missing artifact. The shared-survivor fact alone neither
rejects nor proves.

## 4. Law 3 — intermediate-station discriminator: REJECTED as an identity law

`1+10` vs `1+30` already discriminate the printed RUNS (M8.17 chains — G4),
and each chain is bound to its bore through the end-sheet reciprocal callout
ending at that bore's own printed end station (`3+90` vs `2+13`), so
run-identity is not in question. They CANNOT discriminate the ORIGIN: the
measured geometry shows exactly one drawn alignment, so there is no second
drawn route for the stations to bind to. Using them to assign different
origins would invent identity — forbidden. The discriminator question is
dissolved by measurement, not answered.

## 5. log42 — separate formal abstain (sharpened)

log42 never bound `NEXTLINK@378,409` and is untouched by Laws 1–3. Its
blocker is now named at per-candidate resolution: 12 of 13 sheet-2 rivals
die by `DESIGN_PATH_SEARCH_EXHAUSTED` (paths exist — up to 68 complete
traversals found — but uniqueness cannot be certified within
`MAX_WALK_EXPANSIONS`), 1 by `NO_CONDUIT_CHAIN_TO_MATCHLINE`.

**Named missing extraction target:** a corridor-pruned / junction-bounded
unique-trace capability for dense conduit networks. A budget raise alone is
NOT the target — with 68 complete paths found, an exhaustive search would
land in `DESIGN_PATH_AMBIGUOUS`, and distinct geometry is never tiebroken.

## Owner-supplied log42 correction after M8.20

log42 is not part of the log8/log32 shared-origin collision. Patrick's owner
evidence indicates that the original handwritten bore log is split into two
table blocks but describes one physical run/segment context: block 1 is
`0+00 -> 0+44`, and block 2 is `0+00 -> 2+87`.

The likely printed parent chain is `0+00 -> 2+70` (270 ft),
`2+70 -> 2+87` (17 ft), and `2+87 -> 5+19` (232 ft), totaling 519 ft from
`0+00 -> 5+19`. This suggests parent/child segments and a possibly implicit
or missing 17 ft bridge, not separate unrelated bores.

The engine must treat this as a future parent/child split-log reconciliation
problem, paired with corridor-pruned unique tracing, not as justification for
raising the walk budget. This owner evidence changes no placement: no stroke
is added, and the all-58 census is unchanged.

**Future Fable lane: log42 parent-child split-log reconciliation and
corridor-pruned unique tracing.**

## 7. Law 1 implemented proof-first (REVIEW-only), lane NOT flipped

Law 1 is now IMPLEMENTED as a pure corpus-level decision and PROVEN; no
per-bore lane status, card, stroke, grade, tolerance, or census changed.

**Phase 1 -- conduit-token grammar hardened** (`extract/matchline_join.py`
`parse_conduit_evidence` / `chain_conduit_evidence`, dialect-injected
materials): a conduit statement is recognized ONLY when a count-size token is
POSITIVELY bound to a conduit material word; depth/cover ranges (`24-36" MIN.
DEPTH`, `... DEPTH`, `... COVER`) yield zero conduit evidence; fraction/mixed
notation is captured (presence is the gate). 8 tests.

**Phase 2 -- the law** (`match/shared_alignment.py` `shared_alignment_verdict`,
imported only by proof + tests): the seven gates, Law 2 typed pairwise
rejection, Law 3 encoded by absence (intermediate stations only PROVE
distinctness, never split the origin). Proof `proof/run_shared_alignment_law_probe.py`
G1-G8 PASS: Law 1 PROVES log8+log32 -> `SHARED_ALIGNMENT_MULTI_DROP_REVIEW`
on `NEXTLINK@378,409`, boundaries `{1+76, 1+77}`; the bijection universe is
REAL (exactly the two claimed runs); log42 never enters (0 survivors ->
no claim; one bore -> NOT_APPLICABLE); every positive gate removed yields a
typed, named pairwise rejection. Gate 2 reuses `JITTER_EQUIV_TOL` verbatim
(tripwire-pinned to the engine's own `_cross_deviation`). 12 tests.

**Phase 3 -- lane/card eligibility NOT changed; minimal extension reported.**
The existing architecture cannot honestly flip log8/log32 to REVIEW
eligibility:
  * the per-bore lane refuses them at `len(reaching) > 1` (band corroboration,
    0 survivors) and NEVER narrows to the single survivor -- the M8.18
    discriminator + M8.19 join that produce Law 1's preconditions are
    proof-only, not wired into `resolve_bore`;
  * Law 1 is inherently corpus-level + pairwise; a per-bore status cannot
    carry "this bore shares its origin with log32" without the orchestrator
    (§2.6). Flipping would require wiring M8.18/M8.19 into the per-bore path
    (out of scope, census-risking, accepted-log-risking) and would break
    per-bore purity.
So log8/log32/log42 remain `STRUCTURE_IDENTITY_BINDING_REQUIRED`; the census
is unchanged.

**Smallest required extension (for a future, separately authorized milestone):**
1. a corpus-level extraction pass (NOT the per-bore lane) that runs the M8.18
   discriminator + M8.19 join to emit per-bore `BoreClaim`s for cross-sheet
   collision bores;
2. that pass calls `shared_alignment_verdict` (this law);
3. a NEW schema-versioned GROUP review card in the M8.10/M8.11 contracts -- a
   `SHARED_ALIGNMENT_MULTI_DROP_REVIEW` card that references the member bores,
   the shared origin, and per-run boundaries; frozen `SUGGESTION_NOT_PLACEMENT`;
   it ADDS a review surface and never flips the per-bore placement/census.

### §7 -- IMPLEMENTED: standalone GROUP review card (REVIEW-only)

The extension is now IMPLEMENTED proof-first as a STANDALONE schema-versioned
contract -- NOT by overloading the per-bore M8.10/M8.11 payloads (a group item
is structurally multi-bore; the per-bore `ReviewerPayload` carries one
`bore_id`). New schema **`truelinev2-shared-alignment-group-review-1`**
(`truelinev2/review/group_review.py`):
  * `SharedAlignmentGroupCard` + `GroupMember`, pydantic, validation-is-contract;
  * `group_lane == SHARED_ALIGNMENT_MULTI_DROP_REVIEW`, `mode REVIEW_ONLY`,
    `auto=False`, label frozen `SUGGESTION_NOT_PLACEMENT`, action
    `CONFIRM_OR_REJECT_MULTI_DROP_GROUPING`;
  * `has_geometry=False` / `has_strokes=False` and a geometry-key walker -- the
    card carries NO coordinates, NO segments, NO strokes;
  * every `GroupMember` carries its UNCHANGED per-bore blocked status verbatim
    (the validator REFUSES any non-blocked status) -- the card cannot overwrite
    per-bore truth; `boundaries == members' distinct boundaries` (bijection);
  * `build_group_review_card(verdict, claims, statuses)` returns a card ONLY for
    a `V_REVIEW` verdict (REJECTED / NOT_APPLICABLE -> `None`).
The corpus/group extraction pass is `proof/run_shared_alignment_group_review_proof.py`
(G1-G8 PASS): it runs the M8.18/M8.19/Law-1 extraction OUTSIDE the per-bore
lane and builds the card -- members `{log8, log32}`, origin `NEXTLINK@378,409`,
boundaries `{1+76, 1+77}`, all three bores still
`STRUCTURE_IDENTITY_BINDING_REQUIRED`, log42 not a member. The module is NOT
imported by `resolve_bore` / the sweep / the reviewer service / the per-bore
contracts; the all-58 census and the M8.10/M8.11/M8.15 counts are unchanged
(re-proven). 10 contract tests.

WHY it does not flip per-bore truth: the group card is a SEPARATE review
surface keyed on the GROUP, not the bore. It records each member's per-bore
status as read-only data and is validated to be the blocked status; it never
writes engine state, never produces a placement/segment/stroke, and is not
wired into any per-bore producer. The bores stay blocked per-bore until a
human confirms the grouping.

### Real reviewer service output -- IMPLEMENTED

`truelinev2/review/group_review_service.py::GroupReviewService.generate`
now composes the shipped product-layer path
`extract_group_claims -> shared_alignment_verdict -> build_group_review_card`
and emits the standalone GROUP schema from a real reviewer service surface.
It remains parallel to `ReviewerBundleService.generate(mode)`: the per-bore
bundle method is untouched and is byte-identical before/after group generation.

The service emits exactly one card for `{log8, log32}` at
`NEXTLINK@378,409`, boundaries `{1+76, 1+77}`. Both members carry unchanged
`STRUCTURE_IDENTITY_BINDING_REQUIRED`; log42 produces no claim and is excluded.
No proof imports, geometry, stroke, segment, PNG, AUTO, status, census, or
per-bore contract change is introduced.

The additive API/bundle transport is implemented below. Any eventual UI remains
separately authorized; no geometry/stroke milestone is part of this.

### Additive reviewer API/bundle transport -- IMPLEMENTED

The existing validated reviewer export returned by
`GET /v2/reviewer/bundle?mode=default_baseline` now carries a separate
`group_review` section. Its `schema_version` is
`truelinev2-shared-alignment-group-review-1`; its cards come from the real
`GroupReviewService`. The canonical per-bore `bundle` object is serialized
verbatim and remains byte-identical.

The live transport contains one REVIEW-only card for `{log8, log32}` at
`NEXTLINK@378,409`, boundaries `{1+76, 1+77}`. Both per-bore statuses remain
`STRUCTURE_IDENTITY_BINDING_REQUIRED`; log42 is excluded. Transport validation
rejects AUTO, geometry, stroke, segment, PNG, schema, label, or extra-field
drift. The API remains local-only, read-only, and default-OFF.

REMAINING (separately authorized): any consumer/UI adoption. No placement,
writeback, geometry, or production activation is authorized by this transport.

## 6. Boundary

No per-bore lane wiring, no stroke, no per-bore card/grade change, no tolerance
change, and no per-bore status/census change shipped with this milestone. Law 1
and the §7 GROUP card are implemented + proven PROOF-FIRST (consumed by their
proof runners + tests, never by `resolve_bore`/sweep/reviewer-service). The
GROUP card is a standalone REVIEW surface that never overwrites per-bore truth;
surfacing it through the shipped service and any geometry remain separate,
explicitly authorized milestones. All three bores remain typed abstains.
