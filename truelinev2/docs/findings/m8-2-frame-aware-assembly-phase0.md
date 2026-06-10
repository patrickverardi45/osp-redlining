# M8.2 Phase 0 — frame-aware assembly diagnosis (read-only)

**Status:** PHASE 0 DIAGNOSIS — read-only. **No engine/test/adapter change. No production. No deploy. Nothing implemented.**
**Date:** 2026-06-09 · **Branch:** `feat/truelinev2` (isolated) · **HEAD at diagnosis:** `da63f27`
**Type:** diagnosis + design-intent + safety gate + visibility plan for the named M8.1 successor (frame-aware chain assembly).
**Outcome (preview):** **NEEDS MORE EVIDENCE** — the abstraction is justified, but implementation is gated on one more *read-only* proof (uniqueness + zero-placement-change on real data). See §Recommendation.

> Builds on [[m8-1-anchored-continuation-rejected]] (why raw-station continuation was rejected) and
> [[run-segment-hierarchy-doctrine]] + [[m8-run-segment-foundation]] (the run/segment model this would use).

---

## Executive summary

The v2 matcher links plan callouts into chains by **raw absolute station number**, blind to the fact
that each plan sheet carries its **own local `0+00` station frame** that resets at matchlines. A
matchline equation such as `MATCHLINE STA 3+23 / 0+69 - SEE SHEET 17` means *sheet 5 STA 3+23 ≡ sheet 17
STA 0+69* (a 254 ft frame translation) — but the current linker instead joins `sheet 17 STA 0+69 →
sheet 5 STA 0+69` purely because the numbers match. That is a coincidence, not a continuation, and it
can assemble a **physically wrong run**.

M8.2's job is to make chain assembly **frame-aware**: parse the matchline equations into a generic
**frame graph**, translate every segment's stations into a common frame *before* testing contiguity, and
only then assemble — gated by a **unique anchor** and **consistent run identity**, abstaining otherwise.
The run/segment foundation (`schema/hierarchy.py` + `match/assembly.py`, shipped `da63f27`) already
provides the output shape (segments → composed run) and the evidence types (`FRAME_EQUATION_RESET`,
`MATCHLINE_CONTINUITY`). What is missing is (a) **frame-equation extraction** and (b) a **frame-aware
chain builder**. This doc diagnoses the gap and defines the safety gate; it implements nothing.

---

## 1. Where the current matcher links callouts / stations / sheets / bore evidence

| Step | Location | What it does |
|---|---|---|
| Extract callouts per print-sheet | [engine.py:27-30](../../match/engine.py) | iterates `bore.sheet_refs`, calls `dialect.extract_callouts(plan, sheet, offset)` |
| Build candidate chains | [chains.py:13-32](../../match/chains.py) | start = callout with `abs(from_ft - bore_start_ft) ≤ 8.0`; link = `abs(last.to_ft - c.from_ft) ≤ 2.0` and `c.to_ft > last.to_ft` |
| Score a chain | [score.py:9-26](../../match/score.py) | `chain_start = chain[0].from_ft`, `chain_end = chain[-1].to_ft`, summed footage, sheet set, `multi_sheet` flag |
| Tier the result | [decide.py:29-68](../../match/decide.py) | acceptability + penalty ranking; `MATCHLINE_PAGE_FLIP` caveat if `multi_sheet`; ≥2 co-equal → abstain |

The bore↔plan join key is **`bore.sheet_refs`** (which sheets to read) plus **station/footage matching**
inside those sheets. Chains are the only cross-sheet construct.

## 2. Station scoping — global, not frame-scoped

**Stations are treated globally.** `Callout.from_ft`/`to_ft` ([models.py:31-46](../../schema/models.py))
are absolute feet from `parse_station("STA a")` with **no sheet/frame tag**. `build_chains`
([chains.py:24-28](../../match/chains.py)) iterates **all** callouts regardless of sheet and links on raw
`to_ft ≈ from_ft`. So two callouts in different sheets' *local* frames that happen to share a raw number
(`0+69` on sheet 17 and `0+69` on sheet 5) link as if contiguous. There is **no per-sheet frame**, and
**no translation** of one sheet's stationing into another's.

The only frame-adjacent logic is shallow and does not help assembly:
- [`sheet_map.derive_offset`](../../extract/sheet_map.py) parses `SEE SHEET N` tokens to vote a single
  global **page offset** (page calibration) — not per-sheet frames, not the `a/b` equation values.
  (Brenham's `calibrate` ([brenham.py:77-78](../../extract/brenham.py)) even returns a fixed offset.)
- [`decide.py:64-65`](../../match/decide.py) raises `MATCHLINE_PAGE_FLIP` as a **caveat** when a chain is
  multi-sheet — it knows the chain crossed sheets but never checks the frame equation.

## 3. Evidence / artifacts that carry frame information

| Artifact | Carries | Captured today? |
|---|---|---|
| `Bore.sheet_refs` ([models.py:21](../../schema/models.py)) | which sheets a bore spans | ✅ yes |
| `Callout.sheet` / `.page` | sheet membership of each callout | ✅ yes |
| Matchline `SEE SHEET N` tokens | sheet adjacency (which sheet continues where) | ⚠️ partially — offset vote ([sheet_map.py](../../extract/sheet_map.py)) + diagnostic links ([run_brenham_diagnostic.py:42-49](../../proof/run_brenham_diagnostic.py)) |
| **Matchline equation `STA a / b - SEE SHEET T`** (the frame translation `(S,a) ≡ (T,b)`) | the actual frame reset offset between two sheets | ❌ **not parsed into any model** — present in PDF text only |
| `PlanPdf.lines/words/text_by_index` ([pdf.py:35-58](../../ingest/pdf.py)) | the raw text where the equation lives | ✅ reachable (the raw material) |
| `PlanPdf.vector_segments` ([pdf.py:60-81](../../ingest/pdf.py)) | drawn-path geometry per CAD layer | ✅ reachable (future drawn-path-continuity evidence) |

**The load-bearing gap:** the matchline *equation values* (`a` and `b`) are never extracted. M8.1's
external probe parsed them and confirmed they are deterministic and convention-generic; nothing in the
repo does so yet.

## 4. log11 diagnosis (the canonical frame-blind failure)

log11: span **650** (`0+00 → 6+50`), `sheet_refs = [5, 17]`. Evidence (M8.1 read-only probe, consistent
with the code mechanics above):

- **Anchor is ambiguous, not unique.** **9** callouts begin at `0+00` (s5×2, s17×7) → `build_chains`
  spawns 9 start chains. A safe anchor needs exactly one (`startC == 1`).
- **The best raw-station chain crosses a matchline reset wrongly:**
  `s17[0+00→0+69] → s5[0+69→3+25] → s17[3+23→3+91] → s17[3+91→4+57] → s17[4+57→6+30]` (sum 632, end-delta 20).
  The `s17 0+69 → s5 0+69` hop links equal **numbers** across sheets, violating the real equation
  **s5 STA 3+23 ≡ s17 STA 0+69** (offset 254 ft). The chain is not a physical run.
- **Run identity breaks mid-chain:** conduit changes `1-1.25" HDPE → 2-1.25" HDPE` → these are *different
  runs*, not one.

**What the engine does today:** the wrong chain's end-delta (20) exceeds `review_end` (8), and the 9
co-equal `0+00` anchors trip `GE_2_COEQUAL_CANDIDATES_NO_TIEBREAKER` — so log11 **correctly abstains
today**. But it abstains *incidentally* (tolerance / co-equal), not because the engine understands
frames. The latent danger: a different log whose frame-blind cross-reset chain happens to sum within
tolerance with a single raw anchor could be **auto-placed on a physically wrong run**. log11 is the
illustration that raw-station linking *can* build wrong chains; frame-awareness converts the incidental
abstain into a principled one and closes the latent false-placement risk.

## 5. Relationship to the run/segment foundation (`da63f27`)

A frame-aware assembler is a direct consumer of the foundation — it needs **no new output model**:

| Foundation piece | Role in M8.2 |
|---|---|
| `BoreSegment` (+ `frame`, `station_start_ft/end_ft`) | each frame-scoped callout/range becomes a segment tagged with its sheet frame |
| `SegmentGeometry.frame` ([hierarchy.py](../../schema/hierarchy.py)) | placed per-segment geometry, frame-tagged |
| `ContiguityEvidenceKind.FRAME_EQUATION_RESET` / `MATCHLINE_CONTINUITY` (STRONG) | the evidence kinds a cross-sheet join must carry |
| `prove_contiguity` ([assembly.py](../../match/assembly.py)) | gates assembly on ≥1 STRONG join — a parsed equation, not proximity |
| `assemble_run_geometry` (rejects mixed frames) | composes proven segments; already refuses to compose across mismatched `frame`s |
| `BoreRun` + `decompose_run_geometry` | the inspectable, reversible run — no overlapping parent line |

The foundation's mixed-frame rejection is the seam where frame-translation must happen *before*
composition: segments are translated into one common frame, then composed.

## 6. Proposed generic frame abstraction (justified)

The failure is real and generic (ODOT plans carry matchlines too), so the abstraction is justified:

- **Frame** — a local station origin. Today implicitly "the sheet"; model it as a `frame_id`
  (e.g. per sheet, later per drive). A station value is meaningful only *within* a frame.
- **FrameEquation** — a parsed matchline equation `(sheet_S, a) ≡ (sheet_T, b)` ⇒ a pairwise translation
  `offset(S→T) = a − b`. Generic grammar: `STA a / b … SEE SHEET T` (text values, parsed per dialect;
  the resulting equation object is convention-agnostic).
- **FrameGraph** — the set of FrameEquations as a graph over frames. Translating a station from frame A to
  frame B = summing offsets along the path A→…→B. Contiguity is then tested **in a common frame**: two
  segments are contiguous iff, *after translation*, their endpoints meet — never by raw number equality.
- **Frame-scoped station** — `(frame_id, local_ft)` replacing/augmenting today's bare `from_ft`/`to_ft`
  for cross-sheet reasoning.

This is convention-agnostic: "frames + pairwise equations → translate → then test contiguity." No
Brenham/ODOT specifics enter the core; only the *parser* (which reads convention text) lives in a dialect.

## 7. Evidence that would prove a SAFE frame-aware chain

A chain may assemble into a run only when **all** hold (else abstain → segments stay separate):

1. **Unique anchor** — exactly one segment at the bore's true start in the correct frame (`startC == 1`),
   not N ambiguous `0+00`s.
2. **Parsed matchline equation per cross-sheet join** — a real `(S,a) ≡ (T,b)` translation
   (`FRAME_EQUATION_RESET` / `MATCHLINE_CONTINUITY`, STRONG), with a **reciprocal** pair where available;
   abstain if a sheet tail has multiple exits (the log71 multi-exit case).
3. **Consistent run identity** across every join — conduit type / corridor unchanged (reject the log11
   `HDPE→…` change).
4. **Span closure in the translated common frame** — the composed run covers the bore span end-to-end with
   endpoint/footage deltas within the **existing** tolerances ([decide.py:14-17](../../match/decide.py)),
   **not widened**.
5. **No competing equal assembly** — 0 or ≥2 valid frame-aware chains → abstain (never guess).

## 8. What remains unsafe / forbidden

- Raw-station cross-frame linking as a placement basis (today's frame-blindness).
- Placing on any of multiple ambiguous anchors without disambiguation.
- Bridging across a conduit / run-identity change.
- **Widening tolerances** to force span closure.
- **Hardcoding sheet maps** or any packet-specific continuation table (the old
  `CURRENT_PACKET_PRINT_SHEET_INDEX` hack).
- **Porting old-engine** AP/route/terminal-tail logic — model the generic capability instead.
- log71-class placement (needs AP/KMZ/geo evidence — a *separate* lane, not frame equations).
- Promoting any current ABSTAIN to REVIEW/AUTO during diagnosis or proving.

## 9. Future implementation file map (when/if approved — NOT now)

| Likely change | File | Note |
|---|---|---|
| New: frame model | `truelinev2/schema/frames.py` *(new)* | `Frame`, `FrameEquation`, `FrameGraph` — generic core types |
| New: matchline-equation parser | `truelinev2/extract/matchline.py` *(new)* | parse `STA a/b - SEE SHEET T` → `FrameEquation` (grammar per dialect; output generic) |
| Optional dialect hook | `truelinev2/extract/base.py` | additive optional `extract_frame_equations(...)` on the Protocol |
| Per-dialect equation extraction | `truelinev2/extract/brenham.py`, `extract/odot.py` | implement the parser hook |
| New: frame-aware chain builder | `truelinev2/match/frame_chains.py` *(new)* | translate-then-link; leave `match/chains.py` intact initially |
| Frame-aware assembly entry | `truelinev2/match/assembly.py` | consume equations + segments → `BoreRun` (extends existing pure fns) |
| Possibly: frame tag on callouts | `truelinev2/schema/models.py` | additive `frame`/`frame_id` field (back-compatible) |
| New tests | `truelinev2/tests/test_frame_*.py` *(new)* | parser + translate + frame-aware chain + zero-placement-change |
| Read-only proof harness | `truelinev2/proof/run_frame_aware_probe.py` *(new)* | the §Recommendation proof |

## 10. Files that MUST remain untouched

- All `backend/`, `web/`, production, `main`, Render/Vercel — always.
- No old-engine imports (`app`/`main`/`redline_pdf_first`/`tl_core`/`backend`); drift guards stay green.
- **During Phase 0 / proving: everything** — this is documentation only.
- Even in future impl: keep `match/engine.py` placement decisions and `decide.py` tolerances unchanged
  until the frame-aware path is proven; no convention strings in core; no foundation regression.

---

## V2 review/debug visibility plan

**Goal:** let Patrick see and test v2's segment/run truth **without touching production UI** (`web/`), reusing
the established v2 pattern: a **read-only proof harness → JSON artifact (+ PNG crops)** under a local outputs
directory (exactly how [`proof/run_brenham_diagnostic.py`](../../proof/run_brenham_diagnostic.py) already
writes `m6_diagnostic.json` + chain crops to `data/outputs/truelinev2/...`).

**How v2 exposes segment/run truth before any production UI:**
1. **CLI proof harness → JSON artifact (primary, build first).** A read-only script (`proof/`) that runs the
   corpus and emits, per bore, the full frame-aware record (fields below). JSON is the source of truth.
2. **Local static HTML report (secondary, cheap, high-value).** A generator that renders the JSON into one
   self-contained `.html` under `data/outputs/...` — per-bore: the crop PNG(s), chain table, frame
   equations, run composition, and PASS/ABSTAIN with reasons. Opened directly in a browser; **not served by
   `web/`**, no framework, no routing.
3. **PNG/“overlay” (later, gated on geometry existing).** Extend [`render/crop.py`](../../render/crop.py) to
   draw the **segments** of a placed run on the sheet raster — segment-by-segment, **never** a parent line —
   so the no-overlap rule is visually obvious. Deferred until the assembler produces plan-space geometry.

The existing thin local v2 API (`truelinev2/api`, serving `/v2/review` + `/v2/artifact/...`, tenant-scoped)
remains available for ad-hoc inspection but is **not** the deliverable here and is **not** production `web/`.

**Minimum output that lets Patrick verify each fact (one JSON record per bore, mirrored in the HTML):**

| Must verify | Minimum field(s) |
|---|---|
| start endpoint | `chain[0]` frame-scoped `from_sta` + (later) geometry start point |
| end endpoint | `chain[-1]` frame-scoped `to_sta` + (later) geometry end point |
| sheet/frame relationship | each segment's `sheet` + `frame_id`; the translation applied |
| matchline equation | parsed `(sheet_S, a) ≡ (sheet_T, b)` + offset, per join |
| segment chain | ordered `BoreSegment`s (frame-scoped stations, conduit) |
| assembled run | `BoreRun.geometry` (composed points) + `decompose_run_geometry` back to children |
| abstain reason | `decide` / `prove_contiguity` reason string |
| evidence allowed/blocked | `ContiguityResult` per-join `JoinVerdict` (kinds, strongest, proven) |
| no duplicate overlapping parent | explicit check: `run.points == concat(child points)` and `Σ(count−1)+1 == len(points)`; HTML shows the run drawn segment-by-segment |

**What NOT to build yet (premature UI polish):** a production React/Next component in `web/`; an interactive
pan/zoom map viewer; an operator approve/reject queue or any write-back/persistence path; styling/theming/
branding; auth or multi-tenant UI; live/WebSocket updates. These belong to the eventual production UI lane.

**How it stays isolated from production `web/`:** all output is local files under `data/outputs/truelinev2/...`
(non-tracked working area) produced by `truelinev2/proof/` scripts; the optional viewer is the existing
local-only `truelinev2/api` (separate from `backend/` and `web/`). Import-isolation + drift guards keep v2
from importing old-app code. Nothing in this plan touches `web/`, `backend/`, main, or any deploy.

---

## Non-goals

- No engine, matcher, extractor, adapter, schema, test, or production change in this Phase 0.
- No frame-equation parser, frame-aware chain builder, or visibility harness *implemented* here (designed only).
- No coverage change; no ABSTAIN→REVIEW/AUTO; no tolerance change; coverage stays **23/58**.
- No KMZ/geo/AP lane (that is log71-class, separate).
- No production UI / `web/` work.

## Recommendation: NEEDS MORE EVIDENCE (one read-only proof before any code)

The abstraction is **justified and correct in direction**, but per v2 doctrine ("every abstraction
re-proven by a fresh read-only Phase 0 before code") implementation is **gated** on a targeted read-only
proof — a new `proof/run_frame_aware_probe.py` — that must demonstrate, on the real corpus, **all** of:

1. The matchline equation `STA a / b - SEE SHEET T` is **parseable generically** across the corpus sheets
   (not just log11's), yielding a consistent frame graph.
2. Frame translation + unique-anchor (`startC == 1`) + run-identity gating produces a **unique, physically
   coherent** chain for **≥1 currently-abstaining log** *without widening tolerances*.
3. Applying the frame-aware path **changes no current placement** (the 23/58 set is byte-identical;
   AUTO/REVIEW set unchanged) — it only converts incidental abstains into principled ones and/or adds new
   *gated* placements that pass zero-false grading.

**Decision rule:** if the probe shows a unique, run-identity-checked win with zero placement regression →
proceed to implement per §9 (still default-safe, abstain-first). If it shows ambiguity or any regression →
**do not implement**; bank the negative (as M8.1 did) and keep the segments abstaining. Until that probe
runs and is reviewed: **do not implement M8.2.**

Related: [[m8-1-anchored-continuation-rejected]], [[run-segment-hierarchy-doctrine]],
[[m8-run-segment-foundation]], [[m6-grade-classify]].
