# Run / Segment Hierarchy — core data-model doctrine

**Status:** DOCTRINE / FINDING — concept clarification only. **No engine code. No tests. No adapters. No production. No deploy.**
**Date:** 2026-06-09 · **Branch:** `feat/truelinev2` (isolated; not merged to main)
**Type:** core-model doctrine banked ahead of M8.2. Establishes the **source → run → segment → evidence** hierarchy the matcher and renderer must respect.
**Outcome:** ADOPT as a v2 invariant. This document changes **no behavior**; it constrains the *design* of future assembly + rendering work.

> This bank exists because the core model was clarified: **a bore-log row is usually a SEGMENT, not a whole physical run.** Earlier v2 work implicitly treated one log/row as one placeable thing. That is wrong in the general case and is the conceptual root under the M8.1 rejection — see [[m8-1-anchored-continuation-rejected]].

---

## 1. Executive summary

TrueLine v2 must model a **hierarchy**, not a flat list of placeable rows:

> **Project → Package / Plan Set → Run → Segment → Evidence**

A **segment** is the smallest independently-provable piece of geometry (usually one bore-log row, or a sub-range of one). A **run** is the real, continuous physical bore path a crew drilled. A single run is frequently recorded as **several segments** — multiple bore-log rows, often on the **same source page**, that are child pieces of one continuous drill.

The engine's job, in order:

1. **Place each segment's geometry first**, using its own evidence, with honest abstain (zero-false).
2. **Then assemble** proven, *contiguity-proven* segments into a run.
3. A run is the **composition** of its child segment geometries — an aggregate, **not** a second redline drawn over the top of them.
4. **Render** the run as `segment → segment → segment` (one connected polyline), **never** as the segments *plus* an overlapping parent line spanning the whole run.

Segment evidence stays **inspectable** at all times (QA, closeout, footage, billing, audit). If segments are placed but contiguity is **not** proven, they stay **separate / REVIEW** — assembly is gated on evidence exactly like placement is. This is the [[doctrine/redline-completeness-standard|ALL-REDLINES]] + DO-NOT-WIDEN posture applied to *assembly*: never fabricate a run, the same way we never fabricate a placement.

---

## 2. Definitions

| Term | Definition |
|---|---|
| **Source page / package** | An input artifact: one plan sheet (PDF page) or the bundle of sheets/logs/KMZ for a job. It is *where evidence comes from*, **not** a level of the geometry hierarchy. Multiple segments and even multiple runs can appear on one source page; one run can also span multiple source pages (matchline continuation). |
| **Bore-log row** | One row of the ingested bore log (station range + depth/BOC + date + crew + print/sheet ref + notes). The data origin of (usually) **one segment**. A row is *evidence about a segment*, not a guarantee of a whole run. |
| **Segment** | The smallest independently-placeable unit of redline geometry — typically one bore-log row (or a proven sub-range of one). A segment is placed from its own evidence and is **always individually inspectable**. It is the leaf the renderer actually draws. |
| **Run** | The continuous physical bore path a crew drilled end-to-end — the real-world thing. A run is an **aggregate of contiguous child segments**, identified only when contiguity is *proven*. A run is a logical/compositional parent, **not** a separately-digitized line. |
| **Segment geometry** | The concrete placed geometry of one segment (plan-space and/or geo coordinates for that piece), with its evidence chain attached. |
| **Run geometry** | The **ordered composition** of its child segment geometries (`seg₁ ⧺ seg₂ ⧺ … ⧺ segₙ`). It introduces **no new vertices** beyond those of its segments and **adds no overlapping span**. Run geometry is *derived from* segment geometry; it is never an independent draw. |

---

## 3. Correct hierarchy

```
Project
└── Package / Plan Set            (source pages + logs + KMZ for the job)
    └── Run                       (one continuous physical bore path)
        └── Segment               (one placeable piece — usually one bore-log row)
            └── Evidence          (callout, footage, endpoints, matchline eq,
                                    structure id, BOC, date/crew, source page)
```

Key relationships:

- A **Run** has 1..n **Segments**. A single-segment run is the degenerate (and common) case.
- A **Segment** belongs to **at most one** Run. Until contiguity is proven, it belongs to **no** run (it stands alone / REVIEW).
- **Evidence** attaches at the **segment** level. Contiguity evidence (matchline equations, shared endpoints, etc.) is *relational* evidence that links two segments — it is recorded as part of the assembly decision, and it does not erase the per-segment evidence.
- **Source page / package** is an *input dimension*, orthogonal to the Run→Segment axis. Do not conflate "same page" with "same run" (see §7).

---

## 4. Segment placement rule

**Place segments first, independently, from evidence — with honest abstain.**

- Each segment is matched and placed on its **own** evidence (footage match, endpoint match, callout, frame-resolved station range). This is the existing v2 matcher behavior (AUTO_SELECT / REVIEW / ABSTAIN), unchanged.
- A segment that cannot be uniquely, safely placed **abstains** — it is **not** rescued by appeal to a sibling segment or a hoped-for run. Zero-false applies at the segment level first.
- Tolerances are **not widened** to make a segment "fit" a run narrative. (DO-NOT-WIDEN.)
- The segment's evidence chain is recorded and remains queryable regardless of whether the segment is later assembled into a run.

Segment placement is a **precondition** for run assembly: you cannot assemble what is not yet placed. A run is never used as a back-door to place a segment that could not stand on its own evidence.

---

## 5. Run assembly rule

**Assemble a run only from segments whose placement is proven AND whose contiguity is proven.**

A run is formed by joining segments into an ordered chain when **both** hold:

1. **Every member segment is already placed** (proven, not abstaining).
2. **Contiguity between consecutive members is proven** by evidence from §8 — shared endpoint, same structure, frame-equation reset, matchline/sheet continuity, drawn path continuity, BOC/callout corroboration, or date/crew/source-page context — **and** run-identity is consistent (e.g. conduit type / corridor does not silently change across the join).

If segment placement is proven but contiguity is **not** proven → **keep the segments separate / REVIEW.** Do not assemble. An un-assembled set of placed segments is a valid, honest state — the geometry is still correct and inspectable; only the *grouping* is withheld.

The assembled run is the **composition** of its segments' geometries in physical order. Assembly:

- introduces **no new geometry** — it references the existing segment geometries;
- records the **contiguity evidence** that justified each join;
- is **reversible** — the run can be decomposed back into its segments at any time (QA/audit must always be able to do this);
- **abstains on ambiguity** — if there are ≥2 equally-plausible ways to chain the segments, or an anchor is ambiguous (cf. the M8.1 `startC > 1` multi-anchor case), assembly does not occur.

Improve-don't-mirror: this is a **generic** capability. No packet-specific run table, no `CURRENT_PACKET_PRINT_SHEET_INDEX`-style hardcode, no ported old-engine override decides contiguity.

---

## 6. Rendering rule — no duplicate overlapping parent redline

**Render a run as its segments, in sequence — never the segments plus an overlapping whole-run line.**

Given a run composed of segments `A→B`, `B→C`, `C→D`:

- ✅ **Correct:** draw `A→B`, then `B→C`, then `C→D` — three connected segments that visually and logically form one continuous run `A…D`.
- ❌ **Wrong:** draw `A→B`, `B→C`, `C→D` **and also** draw a separate `A→D` line on top. That parent line is duplicate, overlapping geometry — it double-draws the corridor, corrupts any length/footage summed from rendered geometry, and creates a redline with no single owning segment for QA.

The run is a *view/aggregate* over its segments, not an additional drawn entity. The renderer's drawable primitive is the **segment**. "Run" is how segments are grouped, ordered, and labeled — it is not a separate stroke.

Corollary: footage and length for a run are obtained by **summing the segment geometries** (de-duplicated by construction because there is no overlapping parent), never by measuring an independent parent line.

---

## 7. Safety rule — proximity and convenient numbers are NOT contiguity

**Never join segments merely because station numbers are convenient or endpoints are nearby.**

This is the assembly-side restatement of zero-false, and it is the exact trap the M8.1 proof exposed:

- **Convenient station coincidence is not continuity.** Plan sheets use **per-drive local frames that reset at matchlines** (`STA a = STA b` equations). Two segments sharing a raw station *number* across a frame boundary are almost certainly **not** contiguous — the frame-blind link is a coincidence, not a join. (M8.1: a frame-blind chain hopped `s17→s5→s17` and even changed conduit type mid-chain — physically impossible as one run.)
- **Spatial nearness is not continuity.** Endpoints within a few feet do **not** prove the same physical run — drops, tails, and adjacent runs routinely pass within ~1–1.5 ft. Node/structure **identity** (folder + name + type), not proximity, is authoritative.
- **Same source page is not the same run.** Multiple distinct runs commonly share one sheet; one run commonly spans several sheets. Page membership is a weak hint, never a join.
- **A guessed join is worse than two honest segments.** When contiguity is unproven or ambiguous (≥2 plausible chains, ambiguous anchor, conduit/identity change across the seam), **abstain from assembly** and keep the segments separate. A non-assembled set of correctly-placed segments is safe; a wrongly-merged run is a false redline.

---

## 8. Evidence that can prove contiguity

A join between two consecutive segments may be asserted only on positive evidence. Stronger evidence is preferred; weak signals corroborate but do not, alone, prove a join.

| Evidence | What it proves | Strength / caveat |
|---|---|---|
| **Shared endpoint** | Segment A's end coordinate **is** segment B's start (same point, by *identity* not just proximity) | Strong when it is the same digitized vertex / structure node; weak if "endpoints are merely close" (see §7). |
| **Same physical structure** | Both segments terminate at / pass through the **same identified structure** (handhole, AP terminal, splice, flower pot) by folder+name identity | Strong; identity is authoritative over proximity. |
| **Station / frame equation reset** | A matchline equation `sheetₛ STA a = sheet_T STA b` translates A's frame into B's, making the join *physically* contiguous in a common frame | Strong **and generic** — the equations are deterministically parseable (M8.1). This is the load-bearing evidence for frame-aware assembly. |
| **Matchline / sheet continuity** | A `MATCHLINE STA … — SEE SHEET T` reciprocal pair links the tail of one sheet's run to the head of the next | Strong when the reciprocal pair is unambiguous; abstain if a tail has multiple exits. |
| **Drawn path continuity** | The plan's drawn (vector) path runs continuously across the seam (incl. short un-callouted gaps that are visibly one path) | Medium; requires real geometric continuity, not an inferred bridge over a conduit/identity change (cf. M8.1 `log12` 8-ft gap with `HDPE→VACANT→HDPE`). |
| **BOC / callout corroboration** | Bore-on-center / `DIR. BORE (NNN')` callouts on both sides corroborate the run's footage and identity across the seam | Medium; corroborates an otherwise-proven join, does not create one. |
| **Date / crew / source-page context** | Same crew, contiguous dates, sequential rows on one source page, or split-note lineage ("continues from prior bore", "Segment A split from bore_logN") | Weak/contextual — **ordering and grouping hints only**, never a standalone join. Date is *drill order*, not corridor order (M8). |

**Rule of combination:** a join needs at least one **strong** piece of physical evidence (shared structure-identity endpoint, frame-equation, or unambiguous matchline pair). Medium/weak evidence may corroborate but cannot substitute. Run-identity consistency (conduit type / corridor) is checked on every join.

---

## 9. Non-goals

This document is **doctrine only**. Explicitly out of scope here:

- **No implementation** — no run/segment assembly code is written or scheduled by this doc.
- **No matcher changes** — `match/` (incl. `build_chains`) is untouched; behavior is byte-identical.
- **No adapters** — no dialect/extractor (`extract/…`, Brenham/ODOT adapters) is added or modified.
- **No tests** — no test files added or changed.
- **No production changes** — no flags, no `backend/`, no `web/`, no deploy, nothing merged to main.
- **No coverage change** — corpus remains at the measured **23/58**; no placement moves; no abstain is converted.

The hard constraints from [[m8-1-anchored-continuation-rejected]] carry forward unchanged (no anchored-continuation impl, no tolerance widening, no packet-specific hardcodes, no old-engine ports).

---

## 10. How this informs future M8.2 (frame-aware assembly)

M8.2 (the named successor to the rejected M8.1) is **frame-aware chain assembly + source/run modeling**. This doctrine is its conceptual contract:

1. **It defines the output shape.** M8.2 produces **runs as compositions of placed segments**, not extended single-row placements. The unit of placement stays the **segment**; the unit M8.2 adds is the *proven run grouping over segments*.
2. **It names the load-bearing evidence.** Assembly joins are built in a **translated (frame-aware) coordinate** using §8 evidence — chiefly the parseable matchline `a/b` equations — so cross-sheet contiguity is *physically* meaningful instead of a raw-number coincidence. This is the direct fix for the M8.1 frame-blindness.
3. **It sets the safety gate.** M8.2 must **prove a unique anchor** (`startC == 1`) and **consistent run-identity** before assembling, and **abstain to separate segments** otherwise (§5, §7). The M8.1 multi-anchor cases (`log11` 9-way, `log71` 7-way) remain correctly un-assembled until disambiguated.
4. **It mandates non-overlapping rendering.** Whatever M8.2 assembles must render `segment → segment → segment` with **no parent over-draw** (§6), preserving footage/billing integrity.
5. **It preserves inspectability.** M8.2 assembly must be **reversible to its segments** and must keep each segment's evidence chain intact for QA/closeout/billing/audit (§2, §5).
6. **It must be re-proven first.** Per v2 doctrine, M8.2 begins with a fresh **read-only Phase 0 proof** on a case with a unique anchor and consistent identity — no code until the proof holds.

Sibling targets remain separated by this model: `log12`-class is **same-sheet gap-bridging** (a segment-continuity question, not a frame-equation one); `log71`-class needs **structure-anchor + KMZ/geo** evidence (a separate geo lane). The hierarchy here applies to all three but each draws on different §8 evidence.

---

## Status

Doctrine banked. No behavior changed; coverage unchanged at **23/58**. This document constrains the design of M8.2 and all future assembly/rendering work; it does not authorize any of it.

Related: [[m8-1-anchored-continuation-rejected]] (the rejection this generalizes), [[m6-grade-classify]] (continuation/footage-unique buckets this re-frames as segment-vs-run), [[v2-redline-workflow-vision]] (Concept 2 overlay drawing — must obey §6), and the v2 evidence-seeking + improve-don't-mirror doctrine (memory).
