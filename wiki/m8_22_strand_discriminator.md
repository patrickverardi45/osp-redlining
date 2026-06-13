# M8.22 Adjudication: log42 Strand Discriminator at the Callout-Frame Origin

Status: **STRAND RESOLVED — log42 still NOT placed; blocker shifts to the END
side.** Proof-only; lane/census/grades/tolerances/budget unchanged; zero
strokes. log42 stays `STRUCTURE_IDENTITY_BINDING_REQUIRED`.

Probe: `truelinev2/proof/run_strand_discriminator_probe.py` (G1–G10 PASS)
Tests: `truelinev2/tests/test_strand_discriminator_probe.py` (11)
Report: `data/outputs/strand_discriminator_probe/strand_discriminator_probe.json`

## 1. The question and the answer

M8.21 left log42's origin `NEXTLINK@819,351` at `DESIGN_PATH_AMBIGUOUS`
(2 jitter-distinct strands; on the full sheet-2 universe the dense search is
`DESIGN_PATH_SEARCH_EXHAUSTED`). **Can a safe discriminator pick the run's
true strand? YES — and it is licensed by PRINTED evidence, not raw geometry.**

The two strands differ ONLY in that GROUP 1 detours WEST (~35 pt behind the
origin) before running east; GROUP 0 runs monotone East to the 2+70 terminus
(272.3 ft = +0.9% vs printed 270' = ~46' drop + ~224' east). The westward
detour is into the **526' West tail** — a DISTINCT printed run: the origin
prints TWO `STA 0+00 … E/W PORT TERMINAL TAIL` callouts (`→2+70 (270')` East
and `→5+26 (526')`), each with its OWN matchline (`STA 2+70/5+16 → SH1` vs
`STA 5+26/12+66 → SH3`). The West tail's conduit is not this bore's.

## 2. The directional law (probe-local; adversarially hardened)

A piece is INELIGIBLE iff all its vertices project below `-FOOTPRINT_RADIUS`
on the origin→terminus chord (entirely behind the printed origin = station
< 0 for this run). Remove ineligible pieces, walk UNCHANGED. Directional-only
on the full 39-piece universe → 12 kept → `DESIGN_PATH_TRACED`, GROUP 0
uniquely. Length is NEVER consulted; no y-band; no nearest-selection.

**This is NOT a general geometric theorem** (chord projection equals station
only for a chord-monotone route; the codebase already refuted projection-
ordering at `design_path.py:9-11`). It fires ONLY under three positive gates:

- **G2 printed multi-tail LICENSE** — the behind-origin geometry provably
  belongs to another printed run (the 526' West tail with its own matchline).
- **G5 per-survivor CERTIFICATE** — every survivor vertex projects `>= -margin`
  (measured min 0.0) AND the banked `parallel_strand_guard` is clear (0
  forward sibling strands).
- **G6 ROBUSTNESS** — identical cut set + a valid survivor at BOTH co-located
  origin candidates (`NEXTLINK@819,351` 0+00 and the installer `@818,419`
  0+46), so the strand decision is invariant to the unresolved origin identity.

Honest scope: one-sided — it can LOSE completions for a backward-curving run
(→ conservative `NOT_CONNECTED` abstain, test-pinned) and NEVER creates a
false survivor under the gates. The survivor carries provenance
`DIRECTIONAL_FORWARD_OF_PRINTED_ORIGIN` — NOT M8.18 full-universe, NOT
corridor-class; Law-1 gate-1 does not accept it. The filter reads O/T
POSITIONS only; `NEXTLINK@819,351`'s structure identity stays ABSTAINED, and
the filter never reads the `0+46=0+00` equation, the `HH-HH=46'` note, or the
log41 44/50 digits. Controls log8/log32 are byte-identical under the filter.

## 3. log42 is still NOT placed — the blocker shifts to the END side

Even with the strand resolved, the M8.19 cross-sheet scale-join refuses under
the CORRECT terminus anchor (`NEXTLINK terminal_port_hh`, matching the printed
`PORT TERMINAL TAIL`): far 1.4525 vs end 1.3669 = 6.3% > 5%. But the
`2+70→2+87` end segment is only 17 ft, drawing to ~24.5 pt where **5% is just
~1.2 pt of draw noise** — below the scale-measurement floor. Proof it is
unmeasurable noise rather than a real far/end disagreement: the WRONG
`FLOWER POT` anchor (3 pt away, excluded by `_ANCHOR_MATCH_TOL`) would flip
the join to 3.4% PROVEN.

**Named missing (END-side, NOT a tolerance widen, NOT the far strand):** the
printed boundary equation `STA 2+70/5+16` + closure `270+17=287` ALREADY prove
the crossing; log42 needs a NON-SCALE cross-sheet continuity corroboration for
sub-floor end segments (or an owner waiver of scale-agreement below the
measurement floor).

## 4. Effect of the owner `0+00–0+44` re-read

None on this milestone. The directional law uses only drawn geometry +
positions; it never consults the log41 digit or the printed 46. The 44-vs-46
discrepancy remains the separately-typed `SOURCE_DIGIT_REREAD_REQUIRED`
(M8.21 §4); M8.22 neither uses nor resolves it.

## 5. Boundary & next

Proof-only; no lane wiring, no stroke, no card, no census change, no AUTO;
log8/log32 and the M8.20 group review untouched (re-proven). Next safest step:
the END-side short-segment scale corroboration (above) — log42 is meaningfully
closer (origin reconstructed, strand resolved to the full 270') but re-blocked
on END-segment scale unmeasurability. Deferred by name: the bore_log17 family
(log43/log44).
