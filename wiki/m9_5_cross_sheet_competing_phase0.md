# M9.5 Phase 0: CROSS_SHEET_COMPETING — frame-graph feasibility (FEASIBLE, zero corpus yield)

Status: **PROOF-ONLY / READ-ONLY; no extractor/core/service shipped; zero bores moved;
adversarially audited (5 refutation lenses; every real finding converted to a measured
gate pre-commit).** Decides whether the M9.4.1/M9.4.2 FRAME-SCOPED competing-departure
limitation can be SAFELY lifted using the SHIPPED frame-equation/matchline graph
(`match.frames`). The M8.27 census, product lanes, M8.11 lanes, and M9.0–M9.4.2 results
are untouched. The M9.4.1/M9.4.2 frame-scoped competing guard stays exactly as shipped.

Runner: `truelinev2/proof/run_cross_sheet_competing_phase0.py` (G1–G14 PASS)
Tests: `truelinev2/tests/test_cross_sheet_competing_phase0.py` (19; offline pure + posture)
Report (gitignored, regenerable):
`data/outputs/cross_sheet_competing_phase0/cross_sheet_competing_phase0.json`

## The question (the M9.4.1 named limitation)

M9.4.1's competing guard counts the physical run-callout departures printed WITHIN the
terminal's own frame (the END bore's sheets). A matchline-adjacent lateral drawn SOLELY
on a far sheet is not enumerated, because a station token is frame-local (the M9.2 trap:
the same local station number recurs in every sheet's stationing — a corpus-wide scan
would false-positive). **Can the frame-equation graph identify FRAME-EQUIVALENT sheets
strongly enough to enumerate cross-sheet departures by FRAME-PROVEN station translation
— never raw-number equality, never proximity?**

## The safe mechanism (what "frame-proven" means)

`match.frames` builds SAFE edges ONLY from a matchline frame equation (`STA a / b` or
`STA a = b`) carrying EXACTLY ONE `SEE SHEET N` link AND a matchline marker (HIGH
confidence), de-conflicted by offset. `translate_between_sheets()` maps a station (ft)
from one sheet's frame into another's THROUGH that exact offset, or returns `None`
(abstain — never a raw fallback). So **sheet 24 STA 10+00 maps to sheet 25 STA 2+58**
(NOT sheet 25 STA 10+00): a repeated local station number on an unrelated frame
translates to a DIFFERENT physical station, or does not translate at all. That is the
M9.2-trap avoidance. The proof composes BOTH single-hop and a full **multi-hop**
component reach (a chain of HIGH-confidence safe edges, abstaining on any
offset-inconsistent node), so the proof-of-zero covers the WHOLE frame-reachable
component, not just directly-adjacent sheets.

## Result — the three bore-to-bore junction terminals

| terminal | END→START | anchor sheet | single-hop reach | multi-hop component | EXACT cross-sheet departures |
|---|---|---|---|---|---|
| AP-152 | log10→log27 | 15 | — (isolated) | — (isolated) | n/a (unreachable) |
| AP-117 | log72→log39 | 24 | {25} | {25,26,27,28} | **0** (single + multi) |
| AP-163 | log7→log65 | 10 | {9,12,13} | {7,8,9,12,13,14} | **0** (single + multi) |

Safe frame graph: **15 HIGH-confidence safe edges, 3 conflicts** (the 3 conflicts —
13↔8, 17↔20, 25↔29 — touch no terminal anchor and are already dropped from safe edges).

- **AP-152** — the terminal note sits on sheet 15, an ISOLATED node in the safe graph.
  Its only matchline equation (`STA 4+02/4+16`) is **MULTI-linked** (SEE SHEET 7 AND 14
  → MEDIUM, builds NO safe edge — it is suppressed, not absent). Both the anchor sheet 15
  AND the departing bore log27's other sheet 16 are isolated. log10's other sheet 7 has
  edges, but the node is not on sheet 7. **Frame graph insufficient for this terminal.**
- **AP-117** — frame-equivalence PROVEN (24↔25, and the component {25,26,27,28}). EXACT
  cross-sheet departures = 0 across the whole component. The lone diagnostic near-miss
  (sheet 25 `STA 2+61 TO STA 4+73`) begins EXACTLY at the matchline partner station 2+61
  (the b-side of the edge equation `STA 10+03/2+61`), 3 ft past the node, on the START
  bore log39's OWN sheet [24,25] — the matchline-crossing **continuation** callout, not a
  NEW foreign competitor (counting it would need a forbidden 3 ft proximity tolerance).
  *(It is in fact UNCOUNTED by the M9.4.1 in-frame guard, which counts 0 run callouts at
  AP-117; competing_departures==1 comes solely from the one JUNCTION_ORIGIN bore.)*
- **AP-163** — frame-equivalence PROVEN (10↔9/12/13, component {7,8,9,12,13,14}). EXACT
  cross-sheet departures = 0 across the whole component, no near-miss anywhere. log65
  stays a JUNCTION_DROP_BRANCH (its `FOR FIBER DROP` marker is on its own start callout,
  unaffected by any cross-sheet analysis).

## The six required proof questions

1. **Frame evidence per terminal:** AP-152 isolated (multi-linked equation only); AP-117
   safe edge 24↔25 (component {25,26,27,28}); AP-163 safe edges 10↔9/12/13 (component
   {7,8,9,12,13,14}). 15 HIGH-confidence safe edges total.
2. **Distinguish same-terminal from a repeated local station?** YES. The graph never uses
   raw station equality; it translates by the exact frame offset (10+00→2+58, 4+51→37+30),
   and abstains (`None`) where no safe edge connects — never a raw fallback.
3. **Enumerate without proximity?** YES — exact frame-translated station equality only.
   The 5 ft window is DIAGNOSTIC and never gates the verdict. The synthetic G10 check
   proves the enumerator is non-vacuous: a real frame-translated competitor → 1; the
   raw-equality decoy, the 3 ft near-miss, and an isolated anchor → 0.
4. **Do the three outcomes change?** NO. 2 RUN_ASSEMBLY_REVIEW_CANDIDATE + 1
   JUNCTION_DROP_BRANCH, `competing_departures == 1` for all — unchanged through the
   shipped extractor.
5. **log65 still non-promotable?** YES — `departure_run_class == drop` →
   JUNCTION_DROP_BRANCH; independent of the cross-sheet analysis.
6. **Missing-evidence target (the one blocked terminal, AP-152):** a UNIQUELY-linked
   HIGH-confidence matchline edge connecting the AP-152 frame neighbourhood (sheets 15/16,
   both isolated) to any other sheet.

## Verdict — `SAFE_FRAME_GRAPH_EXTENSION_FEASIBLE`

A safe frame-equivalence relation EXISTS (proven for 2 of 3 terminals), so a
proximity-free, raw-equality-free cross-sheet competing-departure enumeration is
**feasible to build** (this is the task's "if a safe relation exists, emit proof facts"
branch; HONEST_NEGATIVE applies only when NO terminal frame is reachable, which is false
here; BLOCKED applies only if a junction bore carries a contradiction — none do). The
verdict is DERIVED from the gates, never hardcoded; all three verdict tokens are reachable
(`decide_verdict`, unit-tested).

**But on the current corpus it surfaces ZERO additional competing departures (single-hop
AND full multi-hop component), so it changes none of the three outcomes; AP-152's terminal
frame is unreachable.** Feasible ≠ ship-now.

## Recommendation — DEFER the core widen

The mechanism is safe and feasible, but it has ZERO demonstrated yield on the only corpus
and is partial (AP-152 unreachable). A zero-yield, partial extension is a named, justified
capability awaiting a corpus that presents a frame-linked cross-sheet competitor — never a
silent widen now. The M9.4.1/M9.4.2 frame-scoped competing guard stays exactly as shipped.

## Named scope boundaries (honest)

- **Dead-end terminals out of scope.** Only the 3 JUNCTION terminals are searched (the
  M9.4.1 guard's domain). The 4 clean END-of-feed terminals with no junction —
  AP-105/121/148/157 (log42/12/2/57) — have zero resolved departures; a terminal whose
  SOLE departure were drawn off-frame would never form a JUNCTION_ORIGIN and so would never
  reach this junction-based search. That off-frame-only dead-end case is a distinct,
  un-tested completeness question (gated/named by G13).
- **Multi-hop is a proof diagnostic.** The shipped `translate_between_sheets` is
  single-hop; the multi-hop component reach (G12, abstain-first composed offsets) is a
  proof-side robustness check showing the zero is not a single-hop artifact.

## Adversarial audit (5 refutation lenses)

Verdict, false-negative/methodology, zero-false/proximity, posture/prohibitions, and
completeness. The verdict was **confirmed sound** (no lens argued for honest-negative or
blocked on the merits; the false-negative lens independently reproduced the multi-hop
component reach by BFS and confirmed EXACT departures = 0 on every reachable sheet). Real
findings — all fixed pre-commit by converting prose into MEASURED gates:

- the "log39's already-counted departure" wording was an overclaim (the near-miss is in
  fact uncounted) → reworded to the provable matchline-boundary fact + **G6 now measures
  `at_matchline_boundary`**;
- the proof-of-zero was single-hop-scoped → added **G12 full multi-hop component zero**
  (`safe_component_offsets`, abstain-first);
- `BLOCKED_NEEDS_SOURCE_REREAD` was an unreachable token → wired via `decide_verdict`
  (junction-bore contradiction) and unit-tested across all three branches;
- the 4 dead-end clean-END terminals were unacknowledged → **G13 names the boundary**;
- the AP-152 sub-gap was imprecise → grounded in the actual multi-linked equation +
  sheet-16 isolation (**G7**).

## Posture

Read-only / proof-only: full v2 suite **778 passed** (759 baseline + 19 new); guards
(import-isolation / isolation / convention-leakage / global-state / red-stroke) green;
M9.4.1 + M9.4.2 proofs re-confirmed PASS. No core/service/UI change (`git diff` against
the prior HEAD is empty — only the two new proof + test files are added); no AUTO, no
geometry/strokes/PNG, no product-bucket movement, zero bores moved; no customer literals
in shared core (`match/`, `schema/`); no main/v1/Render/Vercel/deploy.
