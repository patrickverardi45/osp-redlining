# M9.4 Phase 0: gated REVIEW-only run-assembly lane — feasibility (POSITIVE, with a drop correction)

Status: **PROOF-ONLY / READ-ONLY; no lane shipped; adversarially audited (drop
overclaim + self-junction gap fixed pre-commit); zero bores moved.** Answers whether
the 3 M9.3/M9.3.1 junction-origin facts can safely support a REVIEW-only
run-assembly continuity-EVIDENCE lane. The M8.27 census, product lanes, and
M9.0/M9.1/M9.2/M9.3/M9.3.1 results are untouched.

Proof: `truelinev2/proof/run_run_assembly_phase0.py` (G1–G10 PASS)
Tests: `truelinev2/tests/test_run_assembly_phase0.py` (12; offline pure law + posture)
Report (gitignored, regenerable):
`data/outputs/run_assembly_phase0/run_assembly_phase0.json`

## The question + the safety law

When a bore END terminal and another bore's START junction-origin share the SAME
AP+splice terminal fact, can the engine emit a typed run-assembly evidence item —
without moving a product bucket, drawing a stroke, or marking AUTO? Yes, as a
**SHARED-TERMINAL-NODE fact**, under an 8-condition law (consuming M9.3.1 facts):
(0) bore-to-bore only — a self-junction is refused; (1) END ownership clean+unique
(one terminal → one bore END); (2) START is `JUNCTION_ORIGIN`, never ownership
(END-direction law); (3) same normalized terminal fact (AP+splice); (4) M9.1
two-field join corroborates (END join BOUND); (5) no PDF↔KMZ / source contradiction;
(6) no competing JUNCTION_ORIGIN departure; (7) EVIDENCE-only. Then the **departing
bore's printed run class** types the item.

## What the evidence IS (and is NOT)

A **shared-terminal-node FACT**: the END bore terminates at terminal T (end-of-feed),
the START bore departs T (directional END→START). It is **NOT** a stationing
continuation, **NOT** a geometric route, and **NOT** a product-bucket change. The
reviewer — never this proof — commits a run.

## Result (the 3 junctions)

| END bore | START bore | terminal | departure class | disposition |
|---|---|---|---|---|
| log10 | log27 | AP-152 | undetermined | `RUN_ASSEMBLY_REVIEW_CANDIDATE` |
| log72 | log39 | AP-117 | undetermined | `RUN_ASSEMBLY_REVIEW_CANDIDATE` |
| log7  | log65 | AP-163 | **drop** | `JUNCTION_DROP_BRANCH` |

- **2 shared-terminal-node REVIEW candidates** (log10→log27, log72→log39): a
  trunk-vs-drop classification the **reviewer** makes; the proof asserts only the
  shared-terminal fact (no continuity claim).
- **1 fiber-drop branch** (log7→log65): the audit's correction. log65's departing
  runs print **"FOR FIBER DROP"** (160′+39′=199′ = log65's span) — a lateral off
  log7's end-of-feed terminus, **not** the trunk continuing. Positively detected via
  the printed drop marker.
- The 7 clean END anchors, the M9.3.1 census (7/3/1/1/44), and the one-terminal-per-END
  uniqueness invariant are unchanged. Direction END→START confirmed (END owners arrive
  at their high station; STARTs depart). log46/log44 contradictions blocked (neither is
  a junction bore). M9.2 no-equation negative intact (none of the 6 is a junction bore).

## Adversarial audit (3 lenses) — caught + fixed pre-commit

- **(major) drop overclaim:** the first draft emitted all 3 uniformly as
  `END_TO_START_TERMINAL_CONTINUITY`, but log65 is a fiber drop. Fixed: re-typed the
  relation to a neutral `END_START_SHARED_TERMINAL` fact; positively-detected drops →
  `JUNCTION_DROP_BRANCH`; the rest → `RUN_ASSEMBLY_REVIEW_CANDIDATE` with
  `departure_run_class` recorded. **Trunk is NOT positively asserted** (absence of a
  drop marker ≠ trunk) — the reviewer classifies; robust per-bore run-class is a named
  M9.4.1 capability.
- **(major) self-junction gap:** `start_bore == end_bore` passed all gates. Fixed: an
  explicit `SELF_JUNCTION_REFUSED` gate (condition 0) + test.
- **(minor)** relation renamed off "CONTINUITY"; caveat flags (`review_only`,
  `evidence_only`, `affects_product_disposition=False`) carried in the candidate
  summary; None-owner message split ("no unique END owner"); `terminal_is_end_of_feed`
  recorded; the competing-guard limitation (counts only JUNCTION_ORIGIN departures,
  not physical drop laterals) documented as an M9.4.1 target. The evidence-only /
  contracts lens confirmed sound (additive-only; M8.11 lanes 30/16/6/4/2; guards green).

## Ship recommendation — DEFER to M9.4.1

Phase 0 proves the boundary; it ships no lane (matches M9.3→M9.3.1). M9.4.1 would
ship a convention-agnostic core over the M9.3.1 typed facts: inject the drop-marker
grammar; enumerate ALL physical departures at a terminal (not only JUNCTION_ORIGIN
starts) for the competing guard; emit the evidence as a NEW review item (like the
M8.20 group card), **never** a per-bore bucket change; UNWIRED until a separate,
justified step.

## Named evidence targets

1. **M9.4.1** — convention-agnostic core run-assembly module; profile-injected
   drop-marker grammar; physical-departure enumerator for the competing guard.
2. A reviewer-service surface for the continuity evidence (separate, justified
   milestone; a NEW review item, never a per-bore bucket change).
3. Owner source re-reads for log46 (PDF↔KMZ) + log44 (source) before any continuity
   touching those bores.
