# Parent / Child Bore-Log Reconciliation Audit (PARENT-CHILD-RECON-1)

**Branch:** `feat/truelinev2` · **Engine HEAD:** `24ea530` (= `5f077fe` + the docs-only OWNER-PACKET-1) · **Date:** 2026-06-13
**Type:** read-only engine/data diagnosis · no placement movement · no UI · no deploy
**Primary source:** the owner-supplied `Brenham_TX_Bore_Logs.zip` (original handwritten field bore logs)

---

## Executive summary

The owner's hypothesis is **confirmed and stronger than stated**: the remaining
unresolved logs are, in the majority, **not isolated source problems — they are
parent/child run-segmentation artifacts** from the original handwritten bore
logs, compounded by a specific, recurring OCR gap.

Three findings, each proven deterministically from the source (nothing invented):

1. **There are exactly 13 split "parent" families** — one per handwritten field
   sheet that carried **multiple data columns** — and they are **exactly the 13
   canonical numbering gaps** (`bore_log13/17/18/20/21/22/24/26/28/33/34/35/40`).
   Each parent sheet's columns were split into separate `bore_logN.xlsx` child
   files. The parent→child lineage is **recorded in the xlsx `notes` column,
   which the engine deliberately ignores** (run-segment-hierarchy doctrine, M8.25).
2. **34 of 58 children carry an OCR `NEEDS REVIEW` flag**, and the dominant flag
   (28 of 58) is **"print mapping uncertain."** Every multi-column field sheet
   has **one shared `Print #` field for the whole sheet** (e.g. `10,13,14`),
   so the **per-column sheet assignment was never recorded** — the structuring
   step preserved the full print list on every child. This unresolved per-column
   print/sheet assignment is the structural root under the engine's
   `FRAME_OR_SHEET_CONFLICT` / off-print abstains.
3. **`log37`/`log38` are not "missing source" at all** — their stations are fully
   present but stored as `STA 3+50`, `STA 0+62`, … (a `STA ` prefix the engine's
   `parse_station` rejects, so the reader raises "no parseable stations"). This is
   an **OCR / ingest-format artifact**, not an absent source.

**Consequence:** OWNER-PACKET-1 (the owner-source re-read packet) **should be
rewritten.** Most of its "owner source re-read" asks are really **per-column
print/sheet reconciliation** (a data/segmentation task) or a small OCR/ingest
fix — not plan-evidence voids. The one genuine plan contradiction it named
(`log46` splice 35 vs 45) is real but is **plan-only (PDF vs KMZ) and is *not*
the thing blocking `log46` placement** — the blocker is the parent/child print
ambiguity.

This audit moves no bore, changes no bucket, and writes no engine logic.

---

## 1. Original source files found / missing

The owner zip `Brenham_TX_Bore_Logs.zip` (31.6 MB) was a OneDrive placeholder;
it was copied to a non-cloud path to force hydration, then extracted (read-only)
to **`C:\Nova\datasets\trueline\brenham_handwritten\`**. It holds **41 files**:
35 `.jpeg` + 2 large `.jpg` handwritten GAC bore-log sheets (two are exact
byte-duplicates) + **4 PDFs** (digital-fill / material-selection forms:
`Brenham phase 5 WP23`, `WP25,27` — Ben Nilles; `GAC 12.2.25 MATSEL WP24,25`,
`GAC 12.3.25 MATSEL WP23,24` — Lunar Infrastructure).

The **same corpus already exists in the repo** (gitignored) at
**`data/outputs/input_files/Brenham_TX_Bore_Logs/`** (44 files — the attached zip
plus 2 earlier-date photos `2025-11-18` / `2025-11-19`). The structured corpus the
engine reads is **`C:\Nova\datasets\trueline\brenham\`** (58 `bore_log*.xlsx`,
`TL2_BRENHAM_CORPUS`). **Nothing is missing**; the zip is readable end-to-end.

Handwritten sheets are named by **capture date**, not bore-log number, so the
photo↔number mapping was recovered from each child xlsx's `notes` ("split from
bore_logN.xlsx … Source: <photo>") and verified against the photos.

---

## 2. Parent handwritten log → current child logs

Reconstructed deterministically from the `notes` column (proof gate G2) and
cross-checked against the photos. **13 families, all matching the canonical
numbering gaps.** "✓ direct" = the handwritten parent was vision-read in this
audit; "✓ vision-pass" = read by an independent automated vision pass.

| Parent (handwritten) | Source photo | Children (col order) | Shared `Print #` | Verified |
|---|---|---|---|---|
| `bore_log13` | 2025-12-03_212755 | log41 (c1), log42 (c2) | 1,2 | ✓ vision-pass |
| `bore_log17` | 2025-12-12_212851 | log43 (c1), log44 (c2) | 10,18 | ✓ direct |
| **`bore_log18`** | **2025-12-15_214828** | **log45 (c1), log46 (c2), log47 (c3)** | **10,13,14** | **✓ direct (focus)** |
| `bore_log20` | 2025-12-18_222857 | log48 (c1), log49 (c2), log50 (c3) | 10,11,12 | ✓ vision-pass |
| `bore_log21` | Documento_2026-01-16_000547_4 | log51 (c1), log52 (c2) | 8,9 | ✓ vision-pass |
| `bore_log22` | Documento_2026-01-16_000547_5 | log53, log54, log55, log56 | 5,6,17,21,2 | ✓ vision-pass |
| `bore_log24` | 2026-01-13_213036 | log57 (c1), log58 (c2) | 8,10,13 | ✓ vision-pass |
| `bore_log26` | 2026-01-27_211717 | log59, log60, log61, log62 | 21,15,6,5 | ✓ vision-pass |
| `bore_log28` | 2026-01-20_215840_1 | log6 (c1), log63 (c2), log64 (c3) | 5,17,21 | ✓ vision-pass |
| `bore_log33` | 2026-01-08_184854_2 | log65 (c1), log66 (c2) | 9,10 | ✓ vision-pass |
| `bore_log34` | 2026-01-08_184854_3 | log67 (c1), log68 (c2) | 19,20 | ✓ direct |
| `bore_log35` | 2026-01-12_211448_2 | log69 (c1+c2), log70 (c3) | 19,20 | ✓ direct |
| `bore_log40` | GAC 12.3.25 MATSEL WP23,24 (PDF) | log71 (c1), log72 (c2) | 23,24 | ✓ vision-pass |

Every owner-asserted family was confirmed (proof gate G3): `bore_log17→43/44`,
`bore_log18→45/46/47`, `bore_log22→53/54/55/56`, `bore_log24→57/58`,
`bore_log33→65/66`, `bore_log34→67/68`, `bore_log40→71/72` — plus 6 more the
owner did not enumerate.

**Cross-cutting fact (13/13 parents, unanimous):** every multi-column sheet has
**one shared `Print #` field for all columns**, and **no bore log carries any
splice field** (proof gate G7 — zero of 58). The bore log records
`station | depth | boc | date | crew | print | notes` only.

---

## 3. Unresolved logs reclassified by root cause

The task's five root-cause buckets, applied to the OWNER-PACKET-1 unresolved set
using the family map + the handwritten sheets:

### A. Parent/child segmentation — unrecorded per-column print/sheet assignment (DOMINANT)
The child is a single column split from a multi-column field sheet whose one
shared `Print #` was preserved verbatim on every child, so which sheet the column
truly belongs to is **not individually recorded**. This is the structural cause
of the `FRAME_OR_SHEET_CONFLICT` / off-print abstains.
**Logs:** `log43`, `log46`, `log47` (bore_log18); `log48` (bore_log20);
`log52` (bore_log21); `log53`, `log54` (bore_log22); `log67`, `log68`
(bore_log34); `log71` (bore_log40). All carry the "print mapping uncertain" flag.

### B. OCR / ingest-format correction
The datum exists but was stored in a form the engine can't parse.
**Logs:** `log37`, `log38` — stations present as `STA 3+50…` (the `STA ` prefix
defeats `parse_station`; the digital-fill PDF source kept the prefix the 56
handwritten logs omit). A pure ingest/parse normalization, **not a source
re-read.** (`log43`'s `43+00 → 45+86` gap is a candidate missed-rows case as well.)

### C. True missing / source-vs-plan evidence
The field log is clear but does not reconcile with the plan as drawn.
**Logs:** `log44` (a real 325′ field run on print 18 that matches no print-18 plan
run); `log69`/`log70` (handwritten `Print #` is faithfully `19,20`, but the
engine's proven drawn path is on **sheet 21** — a genuine *field-print vs
plan-sheet* discrepancy, **not** OCR). These need owner/plan reconciliation, but
the field source itself is legible and present.

### D. True contradiction (plan-only)
Two authoritative **plan** artifacts disagree; the bore log is silent.
**Log:** `log46` — PDF `AP-161 SPLICE LOC 35` vs KMZ `Splice Loc 45`. The
handwritten bore log has **no splice field at all**, so it can neither cause nor
resolve this. It is real, plan-side, and **separate from** log46's placement
blocker (which is bucket A).

### E. Review-by-design
Genuine printed fork / adjudication, not a data defect.
**Logs:** `log8`, `log32` (standalone — the M8.20 shared-alignment group card;
both already place); `log48` additionally carries a genuine M8.3a two-parallel-run
identity fork on top of its bucket-A print ambiguity.

### Standalone (not parent/child) genuine contested-frame
`log29`, `log31` — not split children; their contested-frame is a true
plan-evidence question (unchanged from OWNER-PACKET-1).

**Tally of the OWNER-PACKET-1 substantive set (~17 logs):** ~**11 are parent/child
print-mapping (A)**, 2 OCR-format (B), 3 source-vs-plan (C, of which log44 + the
log69/70 field-vs-plan), 1 plan contradiction (D, log46 splice), 2 review-by-design
(E), 2 standalone contested. **The clear majority are split-family children whose
per-column print/sheet assignment was never recorded** — exactly the owner's thesis.

> **Reliability note (do-not-invent).** The 4 parents read directly in this audit
> (bore_log17/18/34/35) matched their structured children faithfully. The 9
> parents read by the automated vision pass confirmed the **structure**
> (families, column counts, shared-`Print #`, no splice) but flagged several
> **digit-level endpoint discrepancies** (e.g. bore_log20/21/22/24/26/28). Those
> are **not asserted here as corrections** — the second pass is itself
> OCR-uncertain (it misread known fields, e.g. `Print 8,10,13` as `3,10,13`).
> They are candidate discrepancies that require a careful human source audit, and
> their very existence corroborates the pervasive-OCR-uncertainty thesis (the
> ingest flagged 34/58 for exactly this reason).

---

## 4. Focus — original `bore_log18` / current `log46`

**Handwritten sheet `2025-12-15_214828` (verified by direct read):** GAC bore log,
DATE **2025-12-15** (per the capture filename and the structured `date` column;
the handwritten DATE glyph itself is ambiguous — an independent vision pass read it
as `10/15/26`, a live example of the OCR uncertainty this audit documents),
CREW Tx1-1, Job "Brenham Ph5", a **single** `Print #: 10,13,14`, and **three data
columns** — no splice field anywhere on the form.

| Column | Stations (handwritten) | BOC | → child | Match |
|---|---|---|---|---|
| col1 | ~43+56 → 44+89 (leading digit ambiguous 43/45) | 9 | **log45** | matches; leading digit flagged in source |
| col2 | 0+00 → 5+34 (0+00,0+50,…,5+00,5+34) | 3 / 10 / 11 | **log46** | **exact** (depths 4.2–4.5, BOC 3/10/11) |
| col3 | 3+25 → 4+94 | 6 | **log47** | exact |

**The splice 35-vs-45 question — answered.** The handwritten bore log **records no
splice location** (no such field exists on the GAC form; confirmed across all 13
parents). Therefore the `SPLICE LOC 35` (PDF) vs `Splice Loc 45` (KMZ) divergence
is **purely a plan-side PDF↔KMZ contradiction** — it is **not OCR-caused** (the
bore log has no splice to mis-OCR), **not parent-context-caused** (nothing to
inherit), and **cannot be resolved from the bore log**. Which plan value is
authoritative is **still unknown** and is a plan-source question only.

**What actually blocks `log46`.** Its engine status is `FRAME_OR_SHEET_CONFLICT`
("end 5+34 has no positive evidence in its frame"; rival on sheet 15). Root cause:
`log46` is **col2 of a 3-column sheet whose single `Print #: 10,13,14` was
preserved on all three columns** — so whether col2 belongs to sheet 10, 13, or 14
was **never recorded**. That per-column print ambiguity (bucket A), **not** the
splice, is the placement blocker. `log47` (col3) shares the identical ambiguity.

---

## 5. Recommended next engine/data milestone

The dominant lever is **neither a new engine solver nor (mostly) a plan re-read**
— it is **recovering the per-column print/sheet assignment for the 13 split
families**, plus one small ingest fix. Named, **not started**, each separately
authorized:

1. **PARENT-CHILD-RECON-2 — per-column print/sheet assignment (data lane).** For
   each split family, determine which of the shared `Print #` values each column
   truly belongs to (from the handwritten sheet + the plan's drawn run location),
   and record it as a **per-segment print field** replacing the preserved full
   list. This directly feeds the `FRAME_OR_SHEET_CONFLICT` abstains. Read/derive
   only; no placement until proven; zero-false + do-not-widen preserved.
2. **Ingest-format fix for `STA `-prefixed stations (`log37`/`log38`).** Normalize
   the digital-fill station cells so `parse_station` succeeds — these stop being
   "unparseable" without any source re-read. (Tiny, separately authorized.)
3. **Plan-side splice authority (`log46`).** Keep as a genuine PDF↔KMZ owner
   question — but de-couple it from log46 placement (which is item 1).
4. **(Later, gated)** the existing run-segment-hierarchy model
   (`schema/hierarchy.py`, currently unconsumed) could *assemble* runs from the
   recovered per-column assignments — but only after item 1, and only under the
   §5/§7 contiguity gates (no proximity, no convenient-number joins).

---

## 6. Should OWNER-PACKET-1 be rewritten?

**Yes.** The owner-source packet was written before this primary-source
reconciliation and mis-attributes the dominant root cause. Specific edits:

- **Group 1 (log37/log38):** reclassify from "true missing source" → **OCR/ingest
  format fix** (stations present; `STA ` prefix). No owner re-read needed.
- **Group 3 (log46):** **split** into (a) the real placement blocker — per-column
  print/sheet assignment for bore_log18's 3 columns (parent/child, bucket A) — and
  (b) the plan-only splice 35/45 (bucket D). Today the packet names only (b),
  which is *not* the blocker.
- **Groups 4/5/6/7 children** that are split-family columns
  (log43/46/47/48/52/53/54/67/68/71): reframe from "owner plan re-read" → **parent/
  child per-column print reconciliation** (PARENT-CHILD-RECON-2). Keep the honest
  note that **log52 is a bore_log21 child (print 8,9), not a 19/20/21 case**.
- **Keep as genuine:** log44 (field-vs-plan), log69/log70 (field-print 19,20 vs
  plan-sheet 21 — confirmed *not* OCR), log29/log31 (standalone contested-frame),
  log8/log32 (review-by-design).

A rewrite is a separate, authorized step — **not performed in this audit.**

---

## 7. Verification & posture

- **Reconciliation proof** `truelinev2/proof/run_parent_child_reconciliation_audit.py`
  — **G1–G7 PASS** (58 logs; 13 families == numbering gaps; owner families
  confirmed; 34 flagged / 28 print-uncertain; log37/38 STA-prefix artifact;
  bore_log18→45/46/47 with log46=col2; 0 splice fields). Report (gitignored):
  `data/outputs/parent_child_reconciliation_audit/`.
- **M8.27 final engine truth-table proof** re-run: **PASS** — census frozen
  `25/13/5/5/4/3/1/2 = 58`; no bucket moved.
- **M9.8 not contradicted, refined:** M9.8 (`STRUCTURE_IDENTITY_BINDER_FEASIBLE_YIELD_1`,
  `product_yield = 0`, zero bores promoted) said further yield needs owner-source
  / new coverage, not a new solver. This audit sharpens *which* source context is
  missing: **per-column print/sheet assignment (segmentation) + OCR format**, not
  (mostly) new plan evidence. The binder "could not solve" because that
  segmentation/OCR context is unmodeled — consistent with, not contrary to, M9.8.
- **Posture:** read-only. No product-bucket movement; no bore placed/promoted; no
  shared-core edit; no proximity/nearest/length used to resolve anything; no OCR
  correction invented; no UI/API/web/deploy/main/v1; no cleanup/refactor. The new
  files are one wiki doc + one read-only proof script; the corpus and engine are
  unchanged.

---

## Appendix — evidence sources

- Family map + flags: `truelinev2/proof/run_parent_child_reconciliation_audit.py`
  (reads the `notes`/`station` columns the engine ignores) → report JSON.
- Directly vision-read parents: `bore_log17` (`2025-12-12_212851`), `bore_log18`
  (`2025-12-15_214828`), `bore_log34` (`2026-01-08_184854_3`), `bore_log35`
  (`2026-01-12_211448_2`).
- Per-bore status / abstain reasons (unchanged): `wiki/m8_27_final_engine_truth_table.md`,
  `data/outputs/station_axis_interval_containment.md`, `wiki/m8_25_log17_family_abstain.md`.
- Data-model doctrine: `truelinev2/docs/findings/run-segment-hierarchy-doctrine.md`,
  `truelinev2/schema/hierarchy.py`.
- Prior packet being reframed: `wiki/owner_source_reread_packet.md` (OWNER-PACKET-1).
