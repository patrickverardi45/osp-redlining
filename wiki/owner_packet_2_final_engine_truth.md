# OWNER-PACKET-2 — Manual Adjudication Truth (supersedes the "11 of 11 owner-source-required" conclusion)

**Branch:** `feat/truelinev2` · **Engine HEAD:** `9c37835` · **Date:** 2026-06-14
**Status:** manual-adjudication ingestion + final engine-truth packet · documentation/report + a narrow, additive, UNWIRED ingest seam · no UI · no API transport · no deploy · no engine re-run · frozen M8.27 census untouched
**Supersedes:** the prior version of this file (which reported RECON-3 `ZERO_YIELD_OWNER_SOURCE_REQUIRED` / "11 of 11 owner-source-required") **and** [OWNER-PACKET-1](owner_source_reread_packet.md).

> **Headline correction.** Owner manual source review of the full 27-log problem set proved the earlier "owner-source-required / zero-yield" conclusion **materially wrong for this dataset**. The blockers were **OCR and resolver misses on source the owner already has** — not missing source. Of the 27 problem logs: **23 are recoverable / correct-as-drawn**, **4 are valid abstains**, **0 are active unknowns**, and **0 of the 11 shared-print children remain owner-source-required**.
>
> **This was not the engine solving it automatically.** Manual correction exposed OCR/print misreads, dropped station-reset semantics, un-walked matchlines, and parent/child column-splits. Those corrections are now captured as **structured evidence the deterministic v2 engine can consume and re-run**. Wiring them into the engine (so the census actually moves) is a separately-authorized **activation** step — not done in this lane.

---

## 0. Why the prior conclusion was wrong (and what RECON-3 actually got right)

RECON-3 correctly found that the engine could not deterministically assign the 11 shared-print children to one sheet/frame **from the OCR'd data as ingested**. Its error was the *implication* that this was a standing external-source gap. Manual review showed the missing facts were **already present in the source documents** and only needed an owner OCR/resolver re-read:

| lever exposed by manual review | examples |
|---|---|
| **Station OCR misread** | log47 `3+25`→`3+23`; log58 `2+56`→`2+36`; log53 `21+45`→`21+63`; log11 `6+50`→`6+30`; log29 `4+15`→`4+45` |
| **Print OCR misread** | log67/68/69/70 print `19,20`→`17,20` (the `7` read as `9`); log52 `8,9`→`8,7` |
| **Missing print page** | log12 (sheets 23→24→3 once the dropped page is included) |
| **Station-reset segment boundary** (`STA X+XX = 0+00`) | log6, log46, log48, log54, log66, log71 — a reset is a segment boundary, not a global start |
| **Matchline continuation not walked** | log46 (10→13→14), log54 (17/21), log71 (23→24), log12 |
| **HH-HH annotation** | log63 (56'), log58 (236'), log70 (215'), log59 (170'), log66 (55'), log36 (89') |
| **Direct bore callout** | log64 (`STA 0+00 TO 1+00 DIR. BORE (100')`), log53 (`248'`), log68 (`176'`) |
| **Leader line label→structure** | log47, log54, log64 (flower pot / installer HH endpoints) |
| **Original handwritten parent/child columns** | log6/log63/log64 are three columns of one sheet, not one long bore |

**Doctrine learned (documented, not over-built into a solver):** `STA X+XX = 0+00` is a segment boundary; a shared `Print #` is often a sheet-span **set**, not a per-column owner; matchlines must be walked across the sheet set before declaring owner-source-required; HH-HH / direct-bore callouts / label-leader lines are strong segment+endpoint evidence; **AI/OCR output is untrusted until owner-reviewed**.

---

## 1. Provenance

| milestone | commit | result |
|---|---|---|
| OWNER-PACKET-1 | `24ea530` | provisional owner re-read packet (superseded) |
| RECON-1 | `a7858f7` | 13 split families = the 13 numbering gaps; 34/58 children OCR-flagged; root cause = unrecorded per-column print |
| RECON-2 | `eb5740c` | `STA ` ingest fix (default-OFF) + per-column print audit of the 33 children (11 `UNASSIGNABLE_SHARED_PRINT_AMBIGUITY`) |
| RECON-2A | `9c37835` | activated `STA ` normalization; log37→placeable, log38→out-of-class |
| RECON-3 (scout) | — | engine cannot place the 11 from OCR'd data alone → `ZERO_YIELD` (correct re: engine; **over-classified** the blocker) |
| **OWNER-PACKET-2 (this lane)** | uncommitted | **owner manual review → 23 recoverable / 4 abstain / 0 owner-source-required**, captured as a structured correction artifact + screenshot evidence index + an additive UNWIRED ingest seam |

All work stayed on `feat/truelinev2`; `origin/main` untouched `068a279`; nothing merged or deployed.

---

## 2. Final engine completion census (corrected)

### Frozen engine product census (M8.27, HEAD `9c37835`, **unchanged by this lane**)
Source: `data/outputs/final_engine_truth_table/final_engine_truth_table.md`.

| metric | count |
|---|--:|
| total corpus | 58 |
| drawable now (`DRAWABLE_REVIEW`) | 31 |
| not-yet-drawable (the 27 problem logs) | 27 |

This lane does **not** move these numbers — it ingests the corrections that a future authorized **activation** re-run would apply.

### The 27 problem logs after manual review (the adjudication artifact)
Source: `truelinev2/ingest/manual_adjudications/brenham_2026_06_14_owner_review.json` (proof `run_manual_adjudication_ingestion`, G1–G12 PASS).

| group | n | logs |
|---|--:|---|
| **Recoverable / correct-as-drawn** | **23** | log6, log11, log12, log29, log36, log41*, log44†, log46, log47, log48, log52, log53, log54, log58, log59, log63, log64, log66, log67, log68, log69, log70, log71 |
| **Valid abstain (no safe source)** | **4** | log5, log31, log38, log43 |
| **Active unknowns** | **0** | — |
| **Shared-print owner-source-required (after review)** | **0** | — |

`*` log41 = `CORRECT_AS_DRAWN` (review-approved). `†` log44 = `NEEDS_SOURCE_VERIFICATION` (recoverable chained segment; exact end to be confirmed against the source bore row before geometry is encoded — a bounded verify, **not** an active unknown and **not** owner-source-required).

**Status breakdown:** 21 `RECOVERED` + 1 `CORRECT_AS_DRAWN` (log41) + 1 `NEEDS_SOURCE_VERIFICATION` (log44) = 23 recoverable; 4 `ABSTAIN_NO_SAFE_SOURCE`.

### Resolution-path classification
| path | engine-solvable from OCR'd data? | resolution |
|---|:-:|---|
| recoverable via OCR/print/reset/matchline/callout correction (22) | no (needed owner OCR review) | owner-reviewed structured correction → engine re-run |
| recoverable chained segment, verify exact end (log44) | no | confirm against source bore row |
| valid abstain (log5/31/38/43) | no | owner-reviewed: no safe source; stays abstained |

There are **no** logs that require **new external source the owner does not already hold**. The 4 abstains are genuine "no safe deterministic source" calls, not pending asks.

---

## 3. The 11 shared-print children — all recovered

All 11 prior `UNASSIGNABLE_SHARED_PRINT_AMBIGUITY` children are now recovered (none owner-source-required). Source: the adjudication artifact + `evidence_index_2026_06_14.json`.

| child | parent | correction(s) | corrected facts | screenshot support |
|---|---|---|---|---|
| log6 | bore_log28 | column-split + reset + matchline | 0+00→2+43, sheet 5 | PARTIAL (021329/021552: STA 2+43, SEE SHEET 5) |
| log46 | bore_log18 | reset + matchline | 0+00→5+34, sheets 10→13→14 | PARTIAL (023351: STA 44+08=0+00, SEE SHEET 13) |
| log47 | bore_log18 | station OCR 3+25→3+23 + matchline | 3+23→4+94, sheets 10/13/14 | PARTIAL (025040: STA 3+23 flower pot, SEE SHEET 14) |
| log52 | bore_log21 | print OCR 8,9→8,7 + missing stations | 0+98→4+57, prints 8→7 | PARTIAL (031035: STA 0+98 flower pot, SEE SHEET 8) |
| log53 | bore_log22 | station OCR 21+45→21+63 + callout | 21+63→24+11 (248') | **CLEAR** (032035/032447: DIR. BORE 248') |
| log58 | bore_log24 | station OCR 2+56→2+36 + HH-HH | 0+00→2+36 (236'), sheets 10/13 | PARTIAL (034522: STA 39+79 HH, SEE SHEET 13) |
| log63 | bore_log28 | column-split + HH-HH + reset | 0+00→0+56 (56'), sheet 17 | PARTIAL (020903: HH-HH=56') |
| log64 | bore_log28 | column-split + reset + callout | 0+00→1+00 (100'), sheet 21 | **CLEAR** (021712: 3+69=0+00, DIR.BORE 100', 1+00 flower pot) |
| log67 | bore_log34 | print OCR 19,20→17,20 + reset | 0+00→4+14, sheets 17→20 | PARTIAL (035642: 1+45=0+00, SEE SHEET 20) |
| log70 | bore_log35 | print OCR 19,20→17,20 + HH-HH | 0+00→2+15 (215'), prints 17,20 | **CLEAR** (040229: HH-HH=215', STA 2+15 flower pot) |
| log71 | bore_log40 | reset + matchline | 0+00→6+95, sheets 23→24 | PARTIAL (041224/041832: STA 5+45 SEE SHEET 24, LAWNDALE) |

**Special-case integrity (proof-gated):**
- **log68 ≠ log69.** log68 = `STA 5+03 → 6+79` (176', opposite side); **`STA 4+54` is never used as log68 geometry** — it is the log69/log70 anchor. Screenshots 040454/065059 confirm log68's 176'; the STA 4+54 installer HH visible alongside is explicitly excluded.
- **log67/68/69/70 print = `17,20`**, never the OCR `19,20`.
- **log36 HH-HH = 89'** (`1+45 − 0+56 = 89'`, arithmetic-confirmed); a screenshot annotation that read `80'` is a legibility misread, not a conflict.

---

## 4. Screenshot evidence index

47 screenshots (source: `Screenshots.zip`) were indexed by a verbatim-only multi-agent visual pass, **cross-checked against the authoritative written facts** (screenshots corroborate; they never override). Binaries: gitignored `truelinev2/data/manual_adjudications/evidence/2026_06_14/<log_id>/`. Index: `truelinev2/ingest/manual_adjudications/evidence_index_2026_06_14.json`.

- **7 CLEAR**, **18 PARTIAL**, **7 AMBIGUOUS**, **15 context/none**.
- **CLEAR-supported logs:** log53, log64, log66, log68, log70.
- **No screenshot conflicts a written fact.** Two items were resolved as legibility/verify, not conflicts (log36 `80'`/`89'`; log44 `AP-161`/`AP-158`).
- **Evidence-insufficient (recorded, status unchanged):** log11 and log29 have authoritative written corrections but no isolating screenshot; this flags only the evidence reference, never the adjudication (per the screenshot-handling rule). The 4 abstains have no screenshots, as expected.

---

## 5. Parent-run aggregation — decision (report only; NOT implemented)

Parent-run aggregation = assembling a family's corrected children (e.g., bore_log18 → log45/log46/log47) into a parent-run representation.

- **Required before wiring?** No.
- **Safe to defer until after wiring?** Yes — recommended.
- **Blocked by owner-source facts?** No longer — the per-column corrections now exist for all 11 shared-print children; aggregation can compose them.
- **Safe only for already-proven child placements?** Yes — the hard guardrail.

> **Guardrail (non-negotiable):** parent-run aggregation must **not** become a placement solver. It may only compose children that are already proven/placed (or carry an owner-confirmed corrected geometry); it must never invent a missing sheet, endpoint, or per-column print, and it must **not** emit a parent-spanning redline that duplicates/overlaps its children (enforced by `parent_run_duplicate_check`, proof G9).

**Recommendation:** defer aggregation until after limited wiring; scope it to corrected/proven child geometry only; never draw parent+child duplicates.

---

## 6. Wiring recommendation

# `GO_FOR_LIMITED_WIRING_WITH_ABSTAIN_BUCKETS_VISIBLE`

- **Engine truth is stable and the problem set is now well-understood** — 31 drawable + 23 recoverable (corrections captured) + 4 genuine abstains. Nothing is an open unknown.
- **The recovered 23 are structured corrected evidence, not auto-placements** — wire a read-only review surface that shows drawable placements, the corrected/recovered review lane, and the 4 abstains as **distinct, visible buckets**; never silently auto-promote.
- **Production gates remain open** (`wiki/v2-web-wiring-readiness.md`: auth/tenant isolation, durable storage, writeback semantics, deploy/CORS, coordinate transform) → *limited*/local read-only, not production.
- **The next engine step is ACTIVATION, gated and separate** — wire the corrected stations/prints into `read_brenham_borelog` and re-run M8.27 to actually move the census (mirroring RECON-2 → RECON-2A; re-baselines ~the frozen proofs). Not done here.
- **Abstains and verify-flags stay honest** — log44 stays `NEEDS_SOURCE_VERIFICATION` until its end is confirmed; log5/31/38/43 stay abstained.

---

## 7. Artifacts & verification

- **Correction artifact (tracked):** `truelinev2/ingest/manual_adjudications/brenham_2026_06_14_owner_review.json`
- **Evidence index (tracked):** `truelinev2/ingest/manual_adjudications/evidence_index_2026_06_14.json`
- **Ingest/resolution seam (tracked, additive, UNWIRED):** `truelinev2/ingest/manual_adjudication.py`
- **Proof (tracked):** `truelinev2/proof/run_manual_adjudication_ingestion.py` — **G1–G12 PASS** (report: gitignored `data/outputs/manual_adjudication_ingestion/`)
- **Tests (tracked):** `truelinev2/tests/test_manual_adjudication.py` — **33 passed**
- **Screenshot binaries (gitignored):** `truelinev2/data/manual_adjudications/evidence/2026_06_14/`

**Boundary:** no UI, no API transport, no deploy, no engine re-run, no broad refactor, no old-app import; the frozen M8.27 product census (31 drawable) is byte-identical; import-isolation / global-state guards green. The seam is additive and consumed only by its own proof/tests until activation is authorized.
