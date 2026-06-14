# Parent / Child Print-Sheet Assignment — Phase 0 (PARENT-CHILD-RECON-2)

**Branch:** `feat/truelinev2` · **Engine HEAD:** `a7858f7` → this commit · **Date:** 2026-06-13
**Type:** engine/data — Part A (tiny ingest fix, default-OFF opt-in) + Part B (read-only assignment audit)
**Scope:** no UI · no web · no deploy · no cleanup · no product movement in the default census

---

## Executive summary

Two deliverables, both grounded in the PARENT-CHILD-RECON-1 finding that the
remaining unresolved logs are dominated by **parent/child segmentation with an
unrecorded per-column print/sheet assignment**:

**Part A — the `STA ` station-label ingest fix (proven isolated, shipped DEFAULT-OFF).**
log37/log38 were never "missing source"; their stations are present but stored as
`STA 3+50`, `STA 0+62`, … and the shared `parse_station` rejects the `STA ` prefix.
The fix is a narrow, pure normalization wired into the Brenham reader behind a
**default-OFF opt-in** (`read_brenham_borelog(..., normalize_station_label=False)`).
Default OFF is byte-identical — the frozen census and every baseline proof are
untouched. Opted in, **exactly log37/log38 change and nothing else** (proven), and
existing engine law then decides: **log37 → PLACED_REVIEW (drawable), log38 →
OUT_OF_CLASS** (a more-specific abstain) — no promotion is forced.

**Part B — per-column print/sheet assignment audit (read-only, no new solver).**
For the 13 split families' **33 child segments**, classifying each over EXISTING
evidence (shared `Print #`, child station range, the shipped M8.7 station-axis
verdicts, the M8.27 lane) — never proximity, column-order, or length:

| classification | n | meaning |
|---|--:|---|
| `ASSIGNABLE_EXACTLY_ONE_PRINT_FRAME` | **13** | engine already places it (sheet pinned) |
| `UNASSIGNABLE_SHARED_PRINT_AMBIGUITY` | **11** | raw end recurs across frames; the one shared `Print #` never recorded the column → **the deterministic extraction target** |
| `CONFLICTING_SOURCE_EVIDENCE` | **3** | proven path lives on a sheet the field print doesn't list (field-print vs plan-sheet) |
| `REVIEW_BY_DESIGN` | **3** | a genuine printed fork (two real parallel runs / banked grade) |
| `NEEDS_HUMAN_OCR_REREAD` | **2** | source-quality / illegible-or-isolated station |
| `PARENT_RUN_MULTI_SHEET_REQUIRED` | **1** | needs a missing sheet / matchline equation |

**13 of 33 children are already assignable**; **11 are the core "recover the
per-column print" lever** (a future deterministic data extraction, named below);
the rest are genuine source/fork questions.

---

## Part A — the `STA ` station-label ingest fix

### Current behavior (proven)
- `parse_station("STA 3+50")` → `None`; `parse_station("3+50")` → `350.0`. The
  shared parser is anchored at `^\s*(\d+)` so a leading label defeats it.
- A corpus scan confirms the `STA ` prefix is **isolated to log37/log38** (2 + 4
  cells); every other station cell is bare. So the fix can only ever affect those two.

### The fix (smallest safe, default-OFF opt-in)
- New pure helper `truelinev2/stations.strip_station_label`: strips a leading
  `STA` / `STA.` / `STA:` + whitespace **only when a station number follows**;
  leaves bare stations and non-station text (`nope`, `STATION 3+50`) unchanged.
  **No fuzzy OCR correction.** The shared `parse_station` is **unchanged** (zero
  blast radius on `match/frames`, `extract`, proofs).
- `read_brenham_borelog(path, *, normalize_station_label=False)` (threaded through
  `load_borelog`) applies it **only when opted in**. Default OFF = byte-identical.

### Before / after (opt-in OFF vs ON) — proven to affect only log37/log38
Proof `truelinev2/proof/run_station_label_optin_sweep.py` (G1–G5 PASS):
- **OFF (default):** log37/log38 still raise "no parseable stations"; the other 56
  bores load identically. The whole frozen census is preserved.
- **ON:** the OFF→ON changed set is **exactly `{log37, log38}`**; the other 56 are
  byte-identical. Recovered stations: log37 `3+50→4+08` (sheet 23); log38
  `0+62→16+21` (sheets 25, 27).
- **Engine law then decides** (no forced promotion), measured via the full
  reviewer pipeline (M8.27 with the opt-in):

| bore | OFF (frozen) | ON (opt-in) | bucket |
|---|---|---|---|
| **log37** | `SOURCE_REVIEW_REQUIRED` / `BORE_SOURCE_UNPARSEABLE` | **`PLACED_REVIEW`** | `SOURCE_REVIEW_REQUIRED` → **`DRAWABLE_REVIEW`** (can draw) |
| **log38** | `SOURCE_REVIEW_REQUIRED` / `BORE_SOURCE_UNPARSEABLE` | **`OUT_OF_CLASS`** (`END_POSITION_UNRESOLVED`) | `SOURCE_REVIEW_REQUIRED` → **`OUT_OF_CLASS`** |

Census delta under the opt-in (ONLY these two move): `SOURCE_REVIEW_REQUIRED 2→0`,
`PLACED_REVIEW 30→31`, `OUT_OF_CLASS 4→5`; default-baseline `PLACED 24→25`,
`ERROR 2→0`. **A per-bore diff of the full 58-row truth table confirms exactly two
rows changed — log37 and log38.**

### Why default-OFF (not flipped live)
~15 baseline proofs freeze the corrected-source census (`…ERROR 2…` /
`BORE_SOURCE_UNPARSEABLE 2`). Flipping the fix live would ripple `ERROR 2→0`
through all of them — broad drift. Per v2 doctrine (every behavior change is a
default-OFF opt-in; M8.5/M8.8 precedent), the fix ships **dormant + proven**;
activation (flipping the default + updating those baselines to the corrected
census) is a **named, separately-authorized step** — not taken here.

---

## Part B — per-column print/sheet assignment (the 13 families)

Read-only proof `truelinev2/proof/run_parent_child_print_assignment_phase0.py`
(G1–G4 PASS). Evidence per child: shared `Print #`, child station range, the
**shipped M8.7 station-axis verdict** (the sheet(s) the proven path lives on +
rival frames + the off-print check), and the M8.27 lane. Forbidden signals
(proximity, nearest-of-N, length-only, column-order, "probably sheet X", invented
OCR) are **never** used; a shared `Print # 10,13,14` is never treated as a
per-column assignment without proof.

| parent | child | shared print | station range | current lane | proven sheet(s) | rivals | classification |
|---|---|---|---|---|---|---|---|
| 13 | log41 | 1,2 | 0+00→0+44 | PICK_CARD | — | — | NEEDS_HUMAN_OCR_REREAD (end `0+44`/`0+50` unclear) |
| 13 | log42 | 1,2 | 0+00→2+87 | PLACED | placed | — | ASSIGNABLE |
| 17 | log43 | 10 | 40+00→59+19 | OUT_OF_CLASS | — | — | NEEDS_HUMAN_OCR_REREAD (1386′ void; isolated 59+19) |
| 17 | log44 | 18 | 0+00→3+25 | OUT_OF_CLASS | **17** | — | CONFLICTING (run drawn on sheet 17, field print 18) |
| **18** | log45 | 10,13,14 | 43+56→44+89 | PLACED | placed | — | ASSIGNABLE |
| **18** | **log46** | **10,13,14** | **0+00→5+34** | PICK_CARD | 10,13,14 | 15 | **UNASSIGNABLE_SHARED_PRINT_AMBIGUITY** |
| **18** | log47 | 10,13,14 | 3+25→4+94 | PICK_CARD | 10,13,14 | 10,11,12,15 | UNASSIGNABLE_SHARED_PRINT_AMBIGUITY |
| 20 | log48 | 10,11,12 | 0+00→5+09 | PICK_CARD | — | 11,12 | REVIEW_BY_DESIGN (two parallel runs) |
| 20 | log49 | 10,11,12 | 44+89→45+33 | PLACED | placed | — | ASSIGNABLE |
| 20 | log50 | 10,11,12 | 0+00→5+14 | PLACED | placed | — | ASSIGNABLE |
| 21 | log51 | 8,9 | 0+00→2+99 | PLACED | placed | — | ASSIGNABLE |
| 21 | **log52** | 8,9 | 0+98→4+50 | HUMAN_ADJUSTABLE | 8/9 | **10** | UNASSIGNABLE_SHARED_PRINT_AMBIGUITY |
| 22 | log53 | 5,6,17,21,2 | 21+45→24+11 | PICK_CARD | — | 6 | UNASSIGNABLE_SHARED_PRINT_AMBIGUITY |
| 22 | log54 | 5,6,17,21,2 | 0+00→3+14 | HUMAN_ADJUSTABLE | **1** | 2,5,7,17,20,21,22 | CONFLICTING (run on sheet 1, off the 5-print list) |
| 22 | log55 | 5,6,17,21,2 | 1+69→0+00 | PLACED | placed | — | ASSIGNABLE |
| 22 | log56 | 5,6,17,21,2 | 0+00→2+76 | PLACED | placed | — | ASSIGNABLE |
| 24 | log57 | 8,10,13 | 0+00→4+13 | PLACED | placed | — | ASSIGNABLE |
| 24 | log58 | 8,10,13 | 0+00→2+36 | PICK_CARD | — | 7,10,11,12 | UNASSIGNABLE_SHARED_PRINT_AMBIGUITY |
| 26 | log59 | 21,15,6,5 | 2+76→4+46 | PICK_CARD | — | 6,14,15 | REVIEW_BY_DESIGN (parallel runs) |
| 26 | log60 | 21,15,6,5 | 0+00→1+13 | PLACED | placed | — | ASSIGNABLE |
| 26 | log61 | 21,15,6,5 | 2+43→4+50 | PLACED | placed | — | ASSIGNABLE |
| 26 | log62 | 21,15,6,5 | 0+00→2+01 | PLACED | placed | — | ASSIGNABLE |
| 28 | log6 | 5,17,21 | 0+00→2+43 | PICK_CARD | — | 17,20,21,22 | UNASSIGNABLE_SHARED_PRINT_AMBIGUITY |
| 28 | log63 | 5,17,21 | 0+00→0+56 | PICK_CARD | — | 17,18,21 | UNASSIGNABLE_SHARED_PRINT_AMBIGUITY |
| 28 | log64 | 5,17,21 | 0+00→1+00 | PICK_CARD | — | 17,18,21 | UNASSIGNABLE_SHARED_PRINT_AMBIGUITY |
| 33 | log65 | 9,10 | 4+51→6+50 | PLACED | placed | — | ASSIGNABLE |
| 33 | log66 | 9,10 | 0+00→0+55 | PICK_CARD | — | 10 | REVIEW_BY_DESIGN (parallel runs) |
| 34 | **log67** | 19,20 | 0+00→4+14 | HUMAN_ADJUSTABLE | 20 | **21** | UNASSIGNABLE_SHARED_PRINT_AMBIGUITY |
| 34 | **log68** | 19,20 | 4+54→7+21 | OUT_OF_CLASS | — | — | PARENT_RUN_MULTI_SHEET_REQUIRED (no matchline eq) |
| 35 | **log69** | 19,20 | 0+00→4+54 | HUMAN_ADJUSTABLE | **21** | — | CONFLICTING (path on sheet 21, field print 19,20) |
| 35 | **log70** | 19,20 | 0+00→2+15 | HUMAN_ADJUSTABLE | 20 | **21** | UNASSIGNABLE_SHARED_PRINT_AMBIGUITY |
| 40 | log71 | 23,24 | 0+00→6+95 | PICK_CARD | — | 24 | UNASSIGNABLE_SHARED_PRINT_AMBIGUITY |
| 40 | log72 | 23,24 | 7+50→10+00 | PLACED | placed | — | ASSIGNABLE |

(`proven sheet(s)` = the M8.7 ladder's `sheets_crossed`; `—` = the engine abstained
before a single ladder, so no proven sheet exists yet.)

---

## Special focus cases

### 1 — log46 / original bore_log18 (col2)
**Can col2 be assigned to sheet 10, 13, or 14?** **No — not without guessing.**
The proven station-axis path touches sheets {10,13,14}; the raw end `5+34` also
falls in a rival frame on **sheet 15**; the field sheet carries **one shared
`Print #: 10,13,14`** for all three columns, so which sheet col2 owns is
**unrecorded**. → `UNASSIGNABLE_SHARED_PRINT_AMBIGUITY`. The decision was made
**without** the splice value (gate G2). **The splice `35` (PDF) vs `45` (KMZ)
remains a separate, plan-only contradiction** — the bore log has no splice field,
so it neither causes nor resolves it, and it is *not* log46's assignment blocker.

### 2 — log43 / log44 / original bore_log17
The split DID give these per-column prints (col1→10, col2→18). So neither is a
shared-print case; each has a distinct, genuine issue:
- **log43** (`40+00→59+19`, print 10) → `NEEDS_HUMAN_OCR_REREAD`. The `59+19` sits
  isolated at the top of the column above an ascending `40+00→45+86` run with a
  `43+00→45+86` gap (missed rows); the engine finds no tick within 1386′ of
  `59+19`. Whether `59+19` belongs to this segment (vs a continuation of the prior
  day's bore) is a **segment-interpretation / OCR re-read** question — **not
  invented here**; the corrected station range must come from the owner/source.
- **log44** (`0+00→3+25`, print 18) → `CONFLICTING_SOURCE_EVIDENCE`. The 325′ field
  run is clear, but the engine's proven path is on **sheet 17**, not the field
  print 18, and the span matches no plan print-18 run → field-print vs plan-sheet.

### 3 — log52 / log67 / log69 / log70 (the "sheets 19/20/21" group)
The packet framing is reconciled against engine evidence:
- **log52** — rival frame is **sheet 10**, *not* 21 (`UNASSIGNABLE_SHARED_PRINT_AMBIGUITY`);
  it belongs to family `bore_log21` (print 8,9). The OWNER-PACKET-1 nuance holds.
- **log69** — the **canonical off-print**: proven path entirely on **sheet 21**
  while the field print says **19,20** → `CONFLICTING_SOURCE_EVIDENCE`.
- **log67 / log70** — proven path on **sheet 20** (in-list) with **sheet 21** as a
  rival frame → `UNASSIGNABLE_SHARED_PRINT_AMBIGUITY` (not off-print).
So the "19/20/21" issue is real for log69 (off-print) and is a sheet-21 *rival*
ambiguity for log67/log70; log52 is unrelated to sheet 21.

### 4 — log37 / log38 (after Part A)
With the opt-in OFF (default) they remain `SOURCE_REVIEW_REQUIRED`. With the opt-in
ON, **log37 becomes review-ready/placeable (`PLACED_REVIEW`, DRAWABLE)** and
**log38 a more-specific `OUT_OF_CLASS`** — they are no longer "source review
required (unparseable)"; the only remaining step is authorizing the opt-in's
activation.

---

## What this means / recommended next milestone

- **The deterministic extraction target is the 11 `UNASSIGNABLE_SHARED_PRINT_AMBIGUITY`
  children** (log46, log47, log52, log53, log58, log6, log63, log64, log67, log70,
  log71). For each, the missing fact is the **per-column print/sheet assignment**
  that the field crew recorded only as one shared `Print #`. Recovering it (from the
  handwritten column + the plan's drawn run location) would let the engine pin the
  frame deterministically instead of abstaining. **Named, NOT started:
  PARENT-CHILD-RECON-3 — per-column print derivation** (read/derive, proof-first,
  zero-false; no proximity/order).
- **3 `CONFLICTING_SOURCE_EVIDENCE`** (log44 sheet 17, log54 sheet 1, log69 sheet 21)
  are field-print-vs-plan-sheet questions for the owner — the field source is
  legible; it disagrees with where the plan draws the run.
- **3 `REVIEW_BY_DESIGN`** (log48, log59, log66) are genuine printed forks — human
  decisions, not data gaps.
- **2 `NEEDS_HUMAN_OCR_REREAD`** (log41, log43) need an owner/source re-read of the
  station value itself.
- **1 `PARENT_RUN_MULTI_SHEET_REQUIRED`** (log68) needs the missing sheet's ticks or
  a matchline equation.
- **Part A activation** (flip the `normalize_station_label` default + update the ~15
  frozen baselines to the corrected census) is the smallest standalone follow-up.

This sharpens OWNER-PACKET-1 further: its log37/log38 ask is satisfied by the Part A
opt-in (no owner re-read needed), and the bulk of its "owner plan re-read" items are
the **per-column print recovery** named above, not plan-evidence voids.

---

## Verification & posture

- Part A opt-in proof `run_station_label_optin_sweep` **G1–G5 PASS**; tests
  `tests/test_station_label_normalization.py` (default-OFF byte-identical; opt-in
  parses STA; bare/junk unchanged; `parse_station` itself unchanged).
- Part B proof `run_parent_child_print_assignment_phase0` **G1–G4 PASS** (every
  child classified; log46 splice-independent; log52 rival 10 / log69 off-print 21;
  no forbidden evidence in any rationale).
- **M8.27 truth-table proof: PASS** at the default-OFF state (census frozen
  `25/13/5/5/4/3/1/2 = 58`; lanes 30/16/6/4/2; **no bucket moved in the default**).
- **PARENT-CHILD-RECON-1 proof: PASS** (family map unchanged).
- **Full v2 suite: 842 passed** (811 baseline + 31 new); import-isolation /
  convention / global-state guards green.
- **M9.8 not contradicted** — unchanged at default-OFF; this lane sharpens *which*
  missing context (per-column print assignment + OCR format) the binder lacked.
- **Posture:** the only behavior touch is the **default-OFF** opt-in; `parse_station`
  unchanged; shared core (`match`/`schema`) untouched; no proximity/nearest/length
  used; no OCR correction invented; no product-bucket movement in the default
  census; no AUTO/geometry/strokes/PNG; no UI/API/web/deploy/main/v1; no cleanup.
