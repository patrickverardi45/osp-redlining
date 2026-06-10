# M8.2f — cross-sheet transition classifier (helper + read-only proof)

**Status:** helper module + tests + read-only proof. Default behavior UNCHANGED (23/58);
the M8.2d opt-in result is re-confirmed **NOT_SAFE**; frame translation stays **INACTIVE**.
No `decide.py` / default-`run_match` / adapter / production change. Outputs under gitignored
`data/outputs/` only. **Nothing is activated and no log is promoted.**

## Why

M8.2d's first frame opt-in treated EVERY cross-sheet link as requiring a frame edge and so
regressed 8 placed logs to ABSTAIN for zero gain (23→15). M8.2e showed the regressed runs
were continuous multi-sheet stationing the edge-rule wrongly broke, and recommended a
TRANSITION CLASSIFIER: classify each cross-sheet transition first, then choose raw continuity
vs frame translation vs abstain on evidence. M8.2f builds that classifier and proves what it
would (and would not) do on the real corpus — without wiring it into the matcher.

## What shipped (v2-only, additive)

- `truelinev2/match/transition_classifier.py` — pure, convention-agnostic classifier.
  Imports only `match/frames` (the safe-translation foundation) + schema types. No IO, no
  global mutable state, no convention names, no old-app imports. NOT imported by `decide.py`
  or `run_match`.
- `truelinev2/tests/test_transition_classifier.py` — 13 unit tests (no PDF): all six classes
  + the two safety properties.
- `truelinev2/proof/run_transition_classifier_report.py` — read-only proof over the real
  corpus; writes `data/outputs/transition_classifier_report.{md,json}`.

### Taxonomy (six classes)

| class | meaning | link? |
|---|---|---|
| `same_sheet` | not a cross-frame transition | yes |
| `continuous_station` | stationing continues across the sheet, **no** reset edge (raw gap ≈ 0) | yes (raw) |
| `reset_equation` | a **safe** frame equation/edge links the two frames and reconciles the chain | yes (translate) |
| `ambiguous` | **both** raw continuity AND a reset edge are present and **disagree**; no safe precedence | **no** |
| `missing_evidence` | neither raw continuity nor a translating edge (incl. an edge whose offset doesn't fit) | **no** |
| `conflict` | conflicting frame equations on the pair | **no** |

Precedence is safety-first: same-sheet → conflict → **safe edge consulted BEFORE raw
continuity** (so a reset can never be waved through by a coincidental raw equal-station) →
raw continuity → otherwise missing. `link_tol = 2.0 ft` (same as `chains.build_chains`).

## Proof results (real corpus; default `run_match`, frame_graph=None)

- default distribution reproduced: `AUTO_SELECT=14 REVIEW=9 ABSTAIN=33 ERROR=2` (**23/58 golden: YES**).
- frame graph: **15 safe edges, 3 conflicts** (conflicting sheet pairs `[8,13] [17,20] [25,29]`).

### The six questions

1. **Each of the 8 regressed logs preserved as `continuous_station`?** **NO — only 5/8.**
   `log2, log3, log4, log50, log62` are cleanly continuous. `log42, log57, log65` are NOT — they
   sit on parsed reset/conflict edges that disagree with their raw linking (detail below).
2. **log11 [5,17] classified `reset_equation` yet still abstains?** **YES.** The safe edge
   (offset 254 ft) makes the relationship a `reset_equation`, but `run_match` still ABSTAINs
   (`NO_AUTHORED_BOX_MATCH_FOR_BORE_SPAN`) — the edge resolves the LINK, not the anchor/box/footage.
3. **Never classifies a continuous (no-edge) transition as a reset?** **YES** (0 offenders).
4. **Never lets a reset/equation pass as continuous via raw equal-station?** **YES** (0 offenders;
   **2 ambiguous coincidences flagged** instead of silently linked).
5. **Would a classifier-gated opt-in preserve ALL 23 current placements?** **NO** — 3 offenders:
   `log42 [ambiguous]`, `log57 [reset_equation, conflict]`, `log65 [ambiguous]`.
6. **Missing evidence before a new placement is safe?** abstain backlog =
   `NO_AUTHORED_BOX_MATCH_FOR_BORE_SPAN: 32`, `GE_2_COEQUAL_CANDIDATES_NO_TIEBREAKER: 1`;
   plus, for the 3 offenders, a precedence rule or per-case grading (below).

### The 3 offenders (the substantive finding — refines M8.2e)

M8.2e's headline "all 8 regressed are continuous_station, no frame edge" was an
over-simplification: its inline classifier had no genuine `ambiguous` bucket. Under the proper
taxonomy:

| log | transition | raw_gap | translated_gap | edge_offset | class |
|---|---|---|---|---|---|
| log42 [1,2] | s2→s1 | 0 ft | 246 ft | 246 ft | **ambiguous** |
| log57 [8,10,13] | s10→s13 | 0 ft | 2 ft | 2 ft | reset_equation |
| log57 [8,10,13] | s13→s8 | 0 ft | — | — | **conflict** (pair 8,13) |
| log65 [9,10] | s10→s9 | 0 ft | 3279 ft | −3279 ft | **ambiguous** |

For log42 and log65 a parsed frame edge offsets the sheet pair by 246 ft / 3279 ft, so the raw
equal-station that currently places them is in direct tension with a reset; for log57 the chain
threads a **conflicting** equation pair (8,13). These are exactly the cases a classifier-gated
opt-in must NOT auto-resolve. Whether the raw placement is right (and the edge is a parser
artifact — the 3279 ft offset is a strong misparse candidate) or the edge is right (and the raw
placement is a false placement) is undetermined here and needs **visual grading + frame-parser
validation**.

## VERDICT for the next activation attempt: `NEEDS_MORE_EVIDENCE`

A classifier-gated opt-in is NOT yet safe to attempt: it would not preserve `log42/log57/log65`,
and 3 of the 8 "continuous" runs actually overlap parsed reset/conflict edges. This is the
honest, valuable outcome of a proof phase — the classifier surfaced real ambiguity the binary
rule hid. (The verdict is intentionally conservative; the tolerance was **not** widened and the
classifier was **not** weakened to manufacture a READY.)

## Gates (all green)

- default corpus sweep: `14/9/33/2 → PLACED=23` (exact, unchanged).
- full v2 suite: **120 passed** (107 prior + 13 new).
- drift guards (no-convention-leakage / import-isolation / no-global-state): pass.
- standalone import isolation: PASS (zero old-app imports).
- M8.2d opt-in validation: re-confirmed **NOT_SAFE** (8 placed logs change; default golden OK).

## Explicitly NOT done / NOT proven

- NOT wired into `decide.py` or `run_match`; NO default behavior change; NO placement changed.
- Frame translation remains INACTIVE; the M8.2c-Step-2 opt-in remains **NOT_SAFE**.
- NOT product readiness, NOT zero-false, NOT activation safety.

## Recommended next step (NOT started; needs explicit approval)

1. Adjudicate the 3 offenders: grade `log42/57/65` against the plan and validate the s1↔s2 (246),
   s9↔s10 (3279), s8↔s13 (conflict) edges — fix any frame-parser misparse at the source.
2. Define a safe precedence rule for the `ambiguous` (raw-continuity-vs-reset) case.
3. Only then build a classifier-gated cross-sheet link and re-run M8.2d, requiring **all 23**
   current placements preserved (zero regression) before any default activation. log11 still needs
   anchor/box/footage evidence beyond the frame edge.
