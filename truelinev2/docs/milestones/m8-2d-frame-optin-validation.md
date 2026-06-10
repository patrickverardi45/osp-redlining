# M8.2d — real-corpus opt-in frame-translation validation

**Status:** read-only validation complete. **Verdict: NOT_SAFE.** Default behavior is
untouched (corpus stays 23/58); the opt-in real-graph run is a report only, never
persisted. No engine / service / `decide.py` / default-`run_match` change. No product claim.

## What was run

`truelinev2/proof/run_frame_optin_validation.py` (read-only) builds a REAL `FrameGraph`
from the plan PDF text (the M8.2a/M8.2b parser foundation) and runs the matcher TWICE per
bore — DEFAULT (`frame_graph=None`) and OPT-IN (the real graph) — by calling `run_match`
directly. It compares per-log status and writes `data/outputs/frame_optin_validation.{json,md}`.

## Result

- **Real graph:** **15 safe edges, 3 refused conflicts** (ambiguous/conflicting edges
  correctly excluded from the translatable set).
- **DEFAULT:** `AUTO_SELECT=14 REVIEW=9 ABSTAIN=33 ERROR=2 PLACED=23` — **matches the
  23/58 golden** (the validation harness reproduces the shipped behavior; `run_match`'s
  default path is unchanged).
- **OPT-IN:** `AUTO_SELECT=6 REVIEW=9 ABSTAIN=41 ERROR=2 PLACED=15` — **placed drops 23 → 15.**
- **8 currently-PLACED logs regress** (all `AUTO_SELECT → ABSTAIN`), every one a multi-sheet bore:

  | log | sheet_refs |
  |---|---|
  | log2 | 18, 19 |
  | log3 | 2, 3, 4, 5 |
  | log4 | 3, 4, 5 |
  | log42 | 1, 2 |
  | log50 | 10, 11, 12 |
  | log57 | 8, 10, 13 |
  | log62 | 5, 6, 15, 21 |
  | log65 | 9, 10 |

- **newly placed: 0 · auto promotions: 0.**

## Root cause

The M8.2c Step 2 rule is binary: same-sheet links stay raw; **cross-sheet links REQUIRE a
safe frame edge** (else no link). But these 8 bores place today via **continuous stationing
across sheets** (a multi-sheet run with NO matchline reset). Continuous transitions produce
**no frame equation**, so there is **no safe edge** — or, where an edge exists for the pair
(e.g. log57 [8,10,13], log65 [9,10] do appear among bores with a safe edge), its **offset
encodes a reset, not the ~0 continuity** the chain needs, so the translated link fails the
tolerance. Either way the cross-sheet link is refused and the chain breaks → `ABSTAIN`.

So the opt-in **removes valid raw cross-sheet links** that current placements depend on,
while gaining nothing — the exact bidirectional `decide()` regression the Step 2 Phase 0 doc
flagged (`m8-2c-step2-frame-translation-phase0.md`, "Regression risks").

## log11 (the target case)

`sheet_refs=[5,17]`, **safe frame edge present** (5↔17, offset 254), **translated link
possible = true** — yet `status_default = status_optin = ABSTAIN`, reason
`NO_AUTHORED_BOX_MATCH_FOR_BORE_SPAN`, **no promotion**. The frame edge resolves the cross-
frame LINK, but the chain still does not match log11's span within tolerance — anchor /
footage evidence is still insufficient. As designed, frame translation did **not** bypass the
honest-abstain gate, and produced **no false AUTO promotion**.

## Implications

- **Do NOT activate frame translation in the product / default path.** As-is it is NOT_SAFE
  (−8 placements, 0 gain).
- The binary same-sheet/cross-sheet rule is **too aggressive**: it must distinguish a
  **continuous** transition (raw-feet continuous, no reset → keep the raw link) from a **reset**
  transition (matchline frame equation → translate). A safe edge should *augment* linking
  (enable reset continuations) without *removing* valid continuous raw links.
- log11 additionally needs anchor/footage evidence beyond the frame edge before it could place.
- Default behavior remains correct and unchanged (23/58). This validation is the gate the
  Step 2 doc required; it has now run on the real corpus and returned **NOT_SAFE**, so the
  real-corpus opt-in must NOT be promoted to default until the linking rule is refined and
  re-validated to keep all 23 current placements.

## Guardrails honored

Read-only; no `decide.py` edit; no engine/service/default-`run_match` change; no adapter /
`schema/models` / production / `backend` / `web` / main / Render / Vercel change; outputs only
under gitignored `data/outputs/`; no tolerance widening; no ABSTAIN→REVIEW/AUTO promotion in
the default path; no Brenham logic added to core (the proof harness reads results only).
