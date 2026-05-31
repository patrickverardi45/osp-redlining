# Target #24 — Existing-Corpus Source-Artifact Hunt — READ-ONLY

**Mandate:** do NOT conclude "ask for new files" until the bore→drive→structure relationship
is proven absent from the **complete** provided corpus — not just the 3 plan PDFs. The prior
acquisition-packet conclusion was reopened and re-tested against every source class.

**VERDICT: RELATIONSHIP NOT FOUND in the complete existing corpus.** The bore-log lineage and
the structure lineage share **no common join key in any provided file**. This is now proven
across **6 source classes / 71 bore xlsx / the 80-page Fieldwire punch-list / a 539-route
context JSON / the design KMZ / TrueLine's own golden fixtures** — a strict superset of "the
3 PDFs." The prior conclusion holds, but is upgraded from a 3-PDF claim to a full-inventory
proof, and it newly **locates and quantifies the `.FS` references** that motivated the hunt.

> Read-only. No placement, no engine/STATE change, no flag. Probe:
> `scripts/corpus_artifact_hunt.py` → `.out` (parses the Fieldwire PDF directly; self-contained).

---

## 1. Complete inventory of Brenham PH5 sources searched (deliverable 1)

| # | source class | what's here | bore-side id? | structure-side id? |
|---|---|---|---|---|
| 1 | **Bore logs (xlsx)** | **71 files** — 58 active + **13 pre-split originals** in `combined_originals_DO_NOT_IMPORT/` (incl. bore_log18/24, the sources of the blocked splits 46/47/57/58) | YES (`bore_logN`) | **NO** |
| 2 | **Plan PDFs (3)** | `Brenham - Phase 5_07-15-25.pdf` (43-pg plan set), `BRENHAM PH5 - 18-02-2026.pdf` (4 pg), `…New_report…03-23.pdf` (80-pg Fieldwire) | NO | YES (AP / flower pot) |
| 3 | **Fieldwire punch-list** (class-2 9MB PDF, examined separately) | item-no / AP / `.FS` page / `.WP` page / verifier / date | **NO** | YES (AP / `.FS`) |
| 4 | **Route-context JSON** | `backend/uploads/project_route_context/brenham-phase-5.json` — **539 routes** | NO | **NO** |
| 5 | **Design KMZ** | `backend/tests/fixtures/brenham_phase5_source_truth.kmz` (md5-identical to design) | NO | partial (AP/house; flower pots id-less) |
| 6 | **Golden/signal JSON fixtures** | `backend/tests/fixtures/engineering_plans/brenham/*.json` (plan_inputs, extracted_signals, normalized_groups, rankings_input, ambiguity_*) | — | — (TrueLine's own derived outputs, no new source) |

## 2. Exact `.FS` / drive / schematic references found (deliverables 2 & 3)

**The `.FS` references DO exist — in the Fieldwire punch-list PDF — but as a PAGE POINTER,
not the schematic content:**
- **63 `AP-NNN .FS NN` register entries** parsed directly from the PDF, e.g.
  `AP-105 .FS 1`, `AP-108 .FS 3`, `AP-146 .FS 18`, `AP-158 .FS 13`. This maps **each AP →
  the Fiber-Schematic PAGE NUMBER it is documented on.**
- Parallel `AP-NNN .WP NN` (work-package) + item-number + verifier + date rows (the punch-list).
- **0 `bore_log` mentions** anywhere in the 80 pages.
- **0 lines** where an AP is co-located with a `STA n+nn` (no station↔AP tie in the punch-list).

**Is the `.FS`-equivalent artifact already present under another name/embedded form? NO.**
The corpus contains the **reference** (`AP → .FS page N`) but **not the `.FS` PAGES
themselves** — the per-AP fiber schematic that would carry the drive→structure decomposition
is not embedded in any of the 3 PDFs, the KMZ, or the JSON. It is *pointed at*, not *present*.

## 3. Join-key matrix — why the relationship can't be assembled (deliverable 5)

```
source class            bore_id?  structure_id?   station<->structure?   bore<->structure?
bore xlsx (71)            YES        NO             local 0+00 only        NO
plan PDFs (3 sheets)      NO         YES (AP/FP)    per-drive 0+00         NO  (no bore id)
Fieldwire punch-list      NO         YES (AP/.FS)   NO                     NO  (no bore id)
route_catalog JSON        NO         NO             NO                     NO
design KMZ                NO         partial (AP)   NO                     NO
golden JSON fixtures      NO         NO             NO                     NO
```

- **Bore side (class 1):** all 71 xlsx — including the pre-split originals — carry ONLY
  `station/depth/boc/date/crew/print/notes`. **`NON-STANDARD columns = NONE`.** Splitting did
  not lose a structure field; the originals never had one.
- **Structure side (classes 2/3/5):** APs, flower pots, `.FS`/`.WP` pages exist — but never
  carry a bore-log id, and (plan PDFs) station is per-drive `0+00`, not a global chainage.
- **Route JSON (class 4):** pure geometry — `route_id/route_name/source_folder/coords/length_ft/
  point_count/route_role`. **0** occurrences of station/scid/flower/splice/drive/`.FS`.

**The two lineages share no key.** There is no `bore_logN → AP-NNN` (or `→ .FS page`, `→ drive`,
`→ flower-pot SCID`) link in ANY provided file. The missing edge is singular and consistent:
**bore ↔ structure**.

## 4. Per blocked group — can an existing-corpus relationship be extracted? (deliverable 4)

| group | logs | existing-corpus relationship? | why not |
|---|---|---|---|
| DROP / flower-pot | 5,30,48,50,65 | **NO** | flower pots are id-less in the KMZ (Scid empty 157/158); no PDF/xlsx field binds a drop bore to a specific pot |
| main-chain high-station | 16,43 | **NO** (per Target #22) | no station↔geometry anchor in 4000–5950 ft; stations exceed every extracted/registered structure station |
| multi-drive / no-terminus | 57,29,31,46,47,58 | **NO** | bores are continuous multi-drive; no `.FS` decomposition present; the AP→`.FS`-page register can't bind without a bore→AP link |

0/13 blocked logs gain an extractable relationship from the existing corpus.

## 5. Honest delta vs the prior acquisition packet

The Target #23 packet said "the `.FS` sheet is absent — request it." Target #24 **reopened and
hardened** that: it (a) expanded the search from 3 PDFs to the full 6-class corpus, (b) found
the `.FS` data that IS present (the 63-entry AP→page register) and proved it is a *pointer to
absent pages*, (c) confirmed the bore xlsx never carried a structure column even at source, and
(d) confirmed the 539-route context JSON adds no structure key. The conclusion is unchanged but
now **inventory-complete**: the relationship is genuinely not encoded anywhere we were given.

## 6. Next coding target

**There is no code change that extracts these redlines from the current corpus** — the
bore↔structure join key is absent from every source, so any resolver would abstain on 100% of
inputs (same as Targets #20/#22/#23). The single missing edge is now pinned to **one field**:
a `bore_log → AP/structure` (or `→ .FS page`) link, OR the **`.FS` schematic pages** themselves
(the corpus already holds the `AP → .FS-page` index and `AP → lat/lon` via KMZ and `AP → station`
via the plan — only the bore→AP hop is missing). The defensible forward step is therefore NOT a
placement helper but, if desired, a default-OFF **structure-index shadow** assembling the
existing `AP → .FS-page / station / lat/lon` cross-reference so it is ready the moment a bore→AP
link arrives — built, but inert, until that one edge exists. No such helper is shipped here
(it would place nothing today; building it now would be premature per DO-NOT-WIDEN/no-overbuild).

## 7. Files read / searched
- 71 bore xlsx (active + `combined_originals_DO_NOT_IMPORT/`); `BRENHAM_PHASE_5_New_report_…03-23.pdf`
  (80 pg, parsed for the AP→`.FS`/`.WP` register); `brenham-phase-5.json` (539-route context);
  `brenham_phase5_source_truth.kmz` (via Target #20 findings); `engineering_plans/brenham/*.json`
  golden fixtures; prior reports (#20/#22/#23) + Target #8 Fieldwire forensics.
- Probe: `scripts/corpus_artifact_hunt.py` → `.out`.
