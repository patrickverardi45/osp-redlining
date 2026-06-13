# M9.8 Phase 0: STRUCTURE-IDENTITY BINDER feasibility (FEASIBLE, yield 1 = control; 0 product yield)

Status: **PROOF-ONLY / READ-ONLY; no extractor/core/service shipped; no wiring; zero bores
moved; adversarially audited (5→4-lens panel; SOUND, the few precision findings converted
to measured gates pre-commit).** Answers the engine-completion map's question: can the
shipped M9.3.1 endpoint-attribution primitive be generalized into a per-candidate-SHEET
discriminator that REDUCES review-only state (pick-card / human-adjustable) WITHOUT guessing?
The M8.27 census, product lanes, and M9.0–M9.5 results are untouched.

Runner: `truelinev2/proof/run_structure_identity_binder_phase0.py` (G1–G11 + G10b PASS)
Tests: `truelinev2/tests/test_structure_identity_binder_phase0.py` (14; offline pure + posture)
Report (gitignored): `data/outputs/structure_identity_binder_phase0/structure_identity_binder_phase0.json`

## The binder (zero-false; reuses the SHIPPED M9.3.1 primitives unchanged)

For a review-only bore, enumerate its CANDIDATE FRAMES (the M8.9 `candidate_frames` — the
sheet-local tick clusters whose drawn axis contains the bore END). For **each candidate
SHEET separately**, run `TA.detect_endpoint_note` + `TA.attribute_endpoint` at the bore END
station. A sheet carries a TERMINAL IDENTITY iff that single-sheet attribution returns
`ENDPOINT_ATTRIBUTED` (terminal class `terminal_port_hh` + FULL_PAIR AP+splice; partials →
`NO_AP_SPLICE_PAIR`, wrong class → `NON_TERMINAL_ENDPOINT`). **BIND iff EXACTLY ONE candidate
sheet carries a terminal identity**; 0 → ABSTAIN; ≥2 → ABSTAIN (fork); PDF↔KMZ contradiction
→ ABSTAIN (source contradiction). **Never** proximity, length/footage, nearest-of-N, AP-only,
or splice-only — the bind signal is printed terminal-class FULL_PAIR identity on one sheet,
nothing else.

This STRENGTHENS M9.3.1's union scan (which reads the bore's sheets together and first-binds)
by evaluating each candidate sheet independently and refusing unless the identity is on
exactly one — catching a cross-sheet ≥2-identity fork the union scan would mask
(synthetic-verified; no such fork occurs in this corpus, **G10b**).

## Result (the 11 candidates)

| candidate | bucket | candidate frames | terminal identities | verdict |
|---|---|---|---|---|
| **log12** (positive control) | HUMAN_ADJUSTABLE | {2,3} | sheet 3: AP-121 SPLICE LOC 28 | **BIND@s3** |
| log5/11/36/59/66 (parallel-run) | PICK_CARD | various | none | ABSTAIN_NO_TERMINAL_IDENTITY |
| log6/41/58/63/64 (multi-frame) | PICK_CARD | various | none | ABSTAIN_NO_TERMINAL_IDENTITY |

**Yield N = 1**, and that 1 is the positive control. `product_yield = 0` (no bore promoted,
no bucket moved): log12's bound frame (sheet 3) carries **2 holding intervals**, so a residual
**within-frame interval fork** remains — the frame-identity bind does NOT alone promote log12
to PLACED; it stays HUMAN_ADJUSTABLE. The 10 pick-cards print no terminal AP+splice at their
end (the M8.26 honest-negative wall); none is in the 7 M9.3.1 clean-END set. For the 5
parallel-run pick-cards the real fork is WITHIN-frame (≥2 holding intervals) — a per-frame
binder is structurally incapable of resolving a within-frame interval fork even given an
identity (it resolves WHICH sheet, never WHICH interval).

## Verdict — `STRUCTURE_IDENTITY_BINDER_FEASIBLE_YIELD_1`

The binder is a sound, zero-false frame/terminal-identity discriminator (proven on log12),
so the token is FEASIBLE_YIELD_1 (not HONEST_NEGATIVE — a safe bind genuinely exists). But
the corpus yield is ONLY the positive control, it is a frame fact (not a placement), and 0
NEW review bores resolve → effectively another honest-negative for broad review reduction,
consistent with M9.5 / M8.26. **Engine headroom on the current printed evidence is
near-exhausted**; further yield requires owner source re-reads / new printed coverage, not a
new solver.

## Proof questions (answered)

1. Per-sheet identity binder defined WITHOUT touching placement code — yes (proof-only). 2.
Reproduces the log12 control — yes (BIND@s3, live, not hardcoded; G5). 3. Pick-cards with
exactly-one terminal identity — **0 of 10** (G6). 4. Remaining forks/abstains — all 10
abstain (no terminal identity; parallel-run real fork is within-frame). 5. Any
proximity/length/nearest/AP-only/splice-only bind — none (G2/G4, tamper-probed). 6. Alters
the 30 placed bores — no (G7). 7. Preserves all M8.27 buckets — yes (G8). 8. Measured yield N
— yes, N=1, product_yield 0 (G10/G11).

## Adversarial audit (4 refutation lenses)

Verdict + zero-false + log12-not-hardcoded + posture all **confirmed sound** (live-reproduced;
tampering refuted every wrong bind path). The precision findings were converted pre-commit:
the "per-frame" claim sharpened to "per-candidate-SHEET (lossless here, gated G10b: no sheet
hosts >1 tick cluster)"; the parallel-run abstain reason now names the within-frame interval
fork; the "strengthens M9.3.1" claim marked synthetic-verified; an explicit `product_yield: 0`
field added beside `yield_N`; and the G9 posture scan extended to `_bore_candidate_frames`
(while the G2 forbidden-token scan stays scoped to the bind decision, since the harness
legitimately calls the shipped `parse_hh_distances`).

## Posture

Proof-only / read-only: full v2 suite **811 passed** (797 baseline + 14 new); guards green;
M8.27 + M9.3.1 + M9.4.1 + M9.4.2 + M9.5 proofs re-confirmed PASS. ZERO tracked-file edits to
`match/`/`schema/` (shared core) or any placement/reviewer-service module; no AUTO, no
geometry/strokes/PNG, no product-bucket movement, zero bores moved; no owner-source
assumption; no UI/API/deploy. The binder is UNWIRED (proof-only); the 30 placements and the
M8.27 completion buckets are unchanged.

## Next step

No engine wiring in this milestone. The named forward levers remain owner-side (source
re-reads / new printed coverage for the pick/adjustable ends; the M8.26 wall) — NOT a new
engine solver. If log12's residual within-frame interval fork is later resolved AND a
separately-authorized wiring step is approved, the frame-identity fact could promote log12;
the 10 pick-cards stay owner-source/coverage-gated.
