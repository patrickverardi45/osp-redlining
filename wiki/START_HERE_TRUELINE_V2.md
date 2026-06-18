# START HERE — TrueLine v2 Canonical Bootstrap

> Single source of current working truth. Read THIS file first, in full — it is small on purpose.
> Snapshot below is current as of **2026-06-18 (continued 30 + log15/16 run-group)**. For the absolute-latest
> state, read ONLY the top ~35 lines of `C:/Nova/knowledge/TrueLine-Wiki/wiki/hot.md` — never the whole file.
> **Do NOT load history/archive files** (`log.md`, `current-sprint.md`, full `hot.md`) unless explicitly
> asked or investigating a specific historical decision.

## Product goal
Deterministic auto-placement of **ALL** redlines from the source files. Manual operator placement is NOT
the product. **Product gate = actual DRAWN red strokes on the PDFs** — classification / "placed for
review" buckets are not progress until they become drawn strokes.
- **ALL-REDLINES standard** (non-negotiable): place every redline from source; abstention is only an
  interim safety state + a *named* missing-source target, never a manual fallback or "done".
- **DO-NOT-WIDEN** (coexists): never place a wrong redline. Drive abstentions to zero by EXTRACTING the
  missing source relationship — not by guessing, and not by asking a human to decide from vibes.
- Identity-only bridges, NEVER invented coordinates. Every drawn stroke is red (canonical red-stroke law).

## Repo / branch state
- Repo: `C:/Nova/projects/TrueLine/TrueLine_Beta`  ·  Branch: `feat/truelinev2`
- Product lives in `truelinev2/` (clean-room, zero old-app imports). v2 suite: **1384 passed** (1376 prior
  + 8 new run-group tests; 2 e2e skipped). This session ran the focused guard subset (50 passed, 1 skipped).
- Isolated track: monolith / Render / Vercel UNTOUCHED; nothing merged or deployed.

## HEAD / remote state (verify with `git` before trusting this snapshot)
- Local HEAD: **`79d2e6e`** — pushed. `origin/feat/truelinev2`: **`79d2e6e`**  ·  `origin/main`: **`068a279`** (untouched).

## Latest shipped (pushed) — continued 30 (2026-06-18)
TWO pushed commits this arc. **`79d2e6e`** (latest) banks the **log15/log16 run-group + Candidate-A REVIEW card**
(gated proof — frontier UNCHANGED 45/58; NO render / auto-place / census impact); **`b4b597d`** drew **log49**
(44→45). Census FROZEN throughout.
- **`79d2e6e` — log15/log16 RUN-GROUP review proof (no render).** Three proof arcs concluded:
  - **LOG16 fiber proof = NOT a clean case** (`gac/log16_fiber_proof_result.md`): START `31+00` is UNPRINTED
    (a ruler-cut, nearest structure 209 pt — same as log15); END `39+79` binds uniquely → `installer_hh`
    (188,422) sheet 10; the generic-`BORE` blob is ONLY the sheet-9 middle leg (run is cross-sheet 8/9/10).
    Re-triaged OUT of fiber → fiber lane shrinks **4 → 3** (log42 + log3/log4); junction-bridge NOT built
    (log16 never exercised it); NO clean single-sheet fiber proof case remains.
  - **Continuation trace** (`gac/log15_log16_continuation_trace_result.md` + owner contact sheet): log15+log16
    are interior drive/accounting segments on ONE continuous 2-1.25" 288ct fiber MAIN — SPLICE 35 NEXTLINK HH
    @ 28+73 → `31+00` cut → s9 blob → installer HH @ 39+79 → SPLICE 46 NEXTLINK HH @ 45+33 → (the RENDERED
    log48/log50 → flower pots). No standalone deterministic render eligibility.
  - **Resegmentation decision** (`gac/log15_log16_resegmentation_decision.md`): **Candidate A = SPLICE 35 @
    28+73 → installer HH @ 39+79** (1106' = log15 tail 227' + log16 879'), BOTH endpoints source-bound; the
    upstream **466' (24+07→28+73) PARKED** pending sheet-5+ source; ZERO overlap with bore_log20/log49/48/50
    (end 3979 < 4483); HUMAN-REVIEW lane, NOT deterministic frontier.
  - **Shipped (3 files):** a run-group SIDECAR + a gated REVIEW-card slice + 8 tests. NO `parent_source_model`
    mutation (`run_group_id` is metadata the census gate never reads). Doctrine: drive/accounting span ≠
    printed source-bound run span; no fake endpoints at unprinted cuts; ALL-REDLINES = drawn + named-parked.
- **`b4b597d` — log49 (44→45)** via the deterministic `start_label_context` hook (owner Candidate A
  source-bound through the INSTALLER HH callout context+leader; B rejected by source; END 45+33 NEXTLINK HH;
  parent-model `adj_corrected_span` closes the printed 50'). Full detail: [[current-sprint]]/[[log]] continued 30.
- Invariants every commit: census FROZEN (flag-OFF 31/6/1/17/3, flag-ON 22/1/4); `TRUELINE_MANUAL_ADJUDICATIONS`
  default-OFF; no corpus/fixture mutation; NO census rebaseline; NO new production flag; red strokes.

## Current redline frontier
**45/58 drawn** (unchanged — `79d2e6e` is a gated REVIEW proof, not a render). Remaining **13**. Lanes refined:
- **Fiber-backbone** shrank to **3** (log42 + log3/log4); log16 proven NOT a clean single-sheet case; no clean
  proof target remains.
- **log15/log16 → run-group / human-review lane** (Candidate-A review card built; parked upstream 466').
- Plus source-gap / `.FS` acquisition, and stored-anchor repair.

## Current next gates (each separately authorized; NONE started)
1. **log15/log16 run-group** — author/consume the human-review SURFACE for Candidate A (SPLICE 35 @ 28+73 →
   installer HH @ 39+79); OR open the **sheet-5+ head-end trace** to unblock the parked 466' upstream remainder.
   (Run-group metadata is a gated SIDECAR today; canonical promotion = a `run_build_parent_source_model` builder
   change + model rebuild + census re-verify.)
2. **FIBER-BACKBONE** — lane is now **log42 / log3 / log4** (log16 disproven as a clean case). Needs a NEW proof
   target with both endpoints printed AND on one generic-`BORE` blob sheet (none of the surveyed bores qualifies
   as-is); log42 also needs owner frame-resolution. The corridor core exists proof-only; junction-bridge NOT built.
3. Source-gap / `.FS` acquisition (log57 multi-drive + log5/31/38/43/44/14) — needs owner source / the absent
   `.FS` drive-decomposition sheet.
4. Repair stored anchors (log48 `5+14`, log70 `1+45`) under a census re-baseline.

## Current known blockers (each a NAMED missing piece, NOT a generic solver limitation)
- **log15/log16 run-group** — interior drive segments on a continuous spliced fiber main; NOT standalone-renderable
  (`31+00` / `24+07` are unprinted cuts). Candidate-A review card built (`79d2e6e`); needs owner review + the
  **sheet-5+ head-end** to bound/draw the parked 466' (24+07→28+73, continues via `MATCHLINE 24+11 → sheet 5`).
- **Fiber-backbone runs (log42/log3/log4)** — the 2-1.25" fiber conduit is on the generic `BORE` layer outside
  `BASE_CONDUIT`; the corridor core exists proof-only; needs a clean proof target (log16 disproven) + (log42)
  owner frame-resolution.
- **Source-gap (log5/31/38/43 ABSTAIN, log44 NEEDS_SOURCE_VERIFICATION, log14 continuation; log57 + log29/31/46/47/58
  multi-drive)** — no safe plan-side route; needs owner source / the `.FS` drive-decomposition sheet (proven absent).
- **Stored-anchor debt** — log48 (corrupted `5+14`) + log70 (superseded `1+45`) render via the override, but the
  stored fixture values are still wrong; repair under a census re-baseline. (B-DATA-LOG48-ADJ-1.)
- (RESOLVED continued 30: log49 rendered `b4b597d`. log16 fiber proof = NOT a case; log15/log16 = run-group
  review lane `79d2e6e`; continuation traced to SPLICE 46; fiber lane 4→3.)

## Forbidden areas (this and every wiki/session-hygiene session)
Do NOT touch: engine code, renderer, fixtures / anchors / coordinates, backend, web, product runtime,
`origin/main`, or deploy. No new production flag; no fixture mutation; no invented coordinates; no owner
naming where the solver can bind from source. All changes surgical, reversible, minimal-blast-radius.

## Where archived detail lives (load ON DEMAND only — never as default bootstrap)
- `C:/Nova/knowledge/TrueLine-Wiki/wiki/hot.md` — current-state arc (read TOP ~35 lines only for latest).
- `…/wiki/current-sprint.md` — per-session rollups (detailed saves).
- `…/wiki/log.md` — full chronological archive.
- `…/wiki/bugs/current-bugs.md` — open bugs by ID (file:line cited).
- `…/wiki/index.md` — section map + on-demand doc index.
- `gac/*.md` (repo) — per-target source-adjudication packets.
- `wiki/active-context.md` (repo) — deeper historical engine context (pre-continued-23; see its banner).

## Bootstrap rule
Read this file first. Read the TOP section of `hot.md` only if you need the very latest. **Do NOT
full-read `log.md`, `current-sprint.md`, or `hot.md`** unless explicitly asked or tracing a specific
historical decision. Trust this snapshot + the latest commit as current truth; verify against `git` if
in doubt. When you `/save-session`, also bump the snapshot block above so this file stays canonical.
