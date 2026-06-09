# M6 — Grade & Classify (Brenham): the zero-false gate + confirmed gap buckets

**Date:** 2026-06-09 · **Branch:** `feat/truelinev2` (isolated)
**Type:** proof / grading / diagnostic ONLY. **No engine/adapter/core change.** No production, no merge, no deploy.
**Gates:** 46 tests pass (incl. 3 drift guards) · import-isolation PASS · no-convention-leakage green (core stayed Brenham-free).
**Harness:** `truelinev2/proof/run_brenham_diagnostic.py` (reuses shipped extract/chain/score/tolerances read-only). Outputs (gitignored): `data/outputs/truelinev2/m6_brenham_diag/`.

## Mechanical root cause (proven, not guessed)
`match/chains.py:build_chains` requires a callout whose **absolute** `from_ft` ≈ the bore's **absolute** start (`±8 ft`); the bore's start is the **log's recorded min station**. So a bore logged in a local `0+00` drive-frame cannot match a callout at a high absolute station even when footage is unique — it abstains `NO_AUTHORED_BOX_MATCH`. The diagnostic reproduces this per log (`start_candidates_abs`, `footage_candidates`, `best_chain` deltas).

## 1. Zero-false gate — RESULT: PASS (0 confirmed false placements; count stays 18)
All 18 placements graded against the plan (full chains for multi-sheet, not just the first crop):

| Confidence | How verified | Logs |
|---|---|---|
| **High** (exact absolute single-callout match, `absmatch=True`) | callout's absolute span == bore's | `log14, log49(R), log51, log55(R), log56(R), log60` |
| **High** (chain anchored at a *specific* high station — not `0+00`) | non-coincidental start | `log2 (12+22), log3 (12+66), log4 (15+13), log39 (10+03), log65 (4+51)` |
| **Med-high** (`0+00`-anchored *unique, station-contiguous, matchline-linked* chain) | full chain reviewed; footage-exact + unique (AUTO = no tie) | `log8, log32, log42, log50, log57, log62, log30(R)` |

- `log57 [8,10,13]` — the one genuinely flagged case — **resolves to correct**: a unique contiguous Allyne-Ln run (`0+00→1+62→1+62→3+98→…→4+13`, footage-exact) linked by `SEE SHEET 10` / `MATCHLINE STA 1+60/1+62`.
- **Honest caveat:** the 7 med-high `0+00`-anchored chains are confirmed *unique + footage-exact on the log's own print-sheets*, but not field-ground-truth-confirmed. None show any evidence of being wrong; none are false. `(R)` = REVIEW (human-gated by design).

## 2–4. Confirmed per-log classification (the 40 non-placed)

| Class | n | Logs | Fix location |
|---|---|---|---|
| **adapter/parser gap** | 2 | `log37, log38` (`no parseable stations`) | **adapter-local** (`ingest/borelog_brenham.py`) — classifiable without fixing ✓ |
| **generic matching gap — Bucket 3** (footage-unique, no abs-start) | 5 | `log10, log19, log23, log25, log61` | **generic core** (translation-invariant footage match) |
| **generic matching gap — Bucket 2** (multi-drive + matchline) | 11 | `log9, log11, log12, log15, log16, log43, log52, log67, log68, log69, log71` | **generic core** (matchline-aware assembly) — **but 8 also have `startC=0`** → need Bucket-3 translation-invariance first; only `log11, log12, log71` are clean "chain-starts-but-short" bridges |
| **honest abstain** (≥2 footage candidates / tied — engine correctly refuses to guess) | 17 | `log5, log6, log31, log36, log45, log46, log47, log48, log53, log54, log58, log59, log63, log64, log66, log70, log72` | **do-not-fix** (zero-false working); a principled tiebreaker is risky |
| **bad/ambiguous source — needs data** | 5 | `log7, log27, log29, log41, log44` | **needs-data/Bucket 4** (no footage match on print-sheets) |

`log48` is the proof that zero-false works: a chain with deltas `0.0/1.0/0.0` (near-perfect) **abstained on a tie** rather than guess.

## The honest coverage-ceiling finding
Only **~16 of 38** abstains are generic-fixable (11 Bucket-2 + 5 Bucket-3, and 8 of those overlap). **22 of 38** are **honest-abstain (17) or needs-data (5)** — placing them would require a guess (tiebreaker) or missing KMZ/AP data. So **v2 will not reach the old engine's ~34–36 on PDF-only without copying the old guessy/overfit machinery — which improve-not-mirror + zero-false forbid.** The old engine's higher count came partly from exactly that machinery. v2's lower, honest number is the *correct* behavior.

## 5. M7 recommendation

**Build first: translation-invariant unique-footage matching (Bucket 3).**
- **Why first:** cleanest, most-deterministic generic abstraction — the diagnostic already proves *exactly one* footage candidate for each; uniqueness-gated → zero-false-safe; yields conservative **REVIEW** placements (footage-confirmed, station-frame-uncertain → human gates). And it's the **foundation** the 8 `startC=0` Bucket-2 logs also need before any matchline work helps them. Bigger-by-count is Bucket 2 (11), but its clean subset is only 3; Bucket 3 unlocks 5 clean cases **and** is prerequisite for 8 of Bucket 2 — so it's the right first move.
- **Target logs:** `log10, log19, log23, log25, log61` (5).
- **Expected movement:** **18 → ~23 (+5, as REVIEW)**. No AUTO (absolute frame unconfirmed → conservative).
- **v2-native design (convention-agnostic):** a core match mode that, when no absolute-start chain exists, places on a callout **iff exactly one** callout on the bore's print-sheets matches the footage within tolerance **and** no other is within tolerance (hard uniqueness gate); ≥2 or 0 → abstain. Lives in `match/`; the dialect supplies callouts only. Does **not** copy any old override.
- **Proof bar before commit:** the 5 place as REVIEW and grade **correct** vs plan; uniqueness gate test-locked (inject a 2nd candidate → abstains); **zero false**; existing 18 placements **byte-identical**; 46 tests + import-iso + 3 guards green.
- **Stop conditions:** ≥2 footage candidates → abstain (never guess); if the fix tempts a Brenham special-case in core → stop (core-purity); any false placement → stop + finding.

**Build second: matchline-aware chain assembly (Bucket 2, M8)** — extends M7; targets the clean bridges (`log11, log12, log71`) then the `startC=0` set once translation-invariance exists. Deterministic-bridge-only (unique `SEE SHEET n` continuation), uniqueness-gated.

**Do-not-build:** the 17 honest-abstains and 5 needs-data — they correctly abstain.
