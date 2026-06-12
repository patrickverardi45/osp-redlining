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

## 6. Boundary

No lane wiring, no stroke, no card, no grade change, no tolerance change,
no status change shipped with this adjudication. Implementing Law 1/2 is a
separate, explicitly authorized milestone; until then all three bores remain
typed abstains.
