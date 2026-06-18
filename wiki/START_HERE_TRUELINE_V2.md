# START HERE — TrueLine v2 Canonical Bootstrap

> Single source of current working truth. Read THIS file first, in full — it is small on purpose.
> Snapshot below is current as of **2026-06-18 (continued 31 — log30 + log4 + log42 rendered, 48/58)**. For the absolute-latest
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
- Product lives in `truelinev2/` (clean-room, zero old-app imports). v2 suite: **1392 passed** (1384 prior
  + 8 across the 3 new render lanes; 2 e2e skipped). Callout-sweep e2e **32 passed**.
- Isolated track: monolith / Render / Vercel UNTOUCHED; nothing merged or deployed.

## HEAD / remote state (verify with `git` before trusting this snapshot)
- Local HEAD: **`62ee0da`** — pushed. `origin/feat/truelinev2`: **`62ee0da`**  ·  `origin/main`: **`068a279`** (untouched).

## Latest shipped (pushed) — continued 31 (2026-06-18)
THREE render commits this arc — frontier **45 → 48/58** (three actual drawn red strokes). Lineage
`79d2e6e` → `a8b2d31` → `f75c5c6` → **`62ee0da`** (pushed → `origin/feat/truelinev2` = `62ee0da`). Census
FROZEN every commit; each new primitive is a GATED per-log opt-in field in the proof sweep's route record →
all prior renders BYTE-IDENTICAL (md5-verified); global `BASE_CONDUIT` and `MAX_DASH_GAP` untouched. The only
two files changed across all three commits: `truelinev2/proof/run_callout_route_assembly_sweep.py` + its test.
- **`a8b2d31` — log30 (45→46), Ledbetter parallel run.** Standalone bore_log30 (0+00→5+00, s10/12) = the
  parallel "1+91/1+92 Ledbetter run" distinct from drawn log48 (Woodson 1+90/1+90→5+07; 219-258 ft apart).
  Gated `parallel_crossing_by_chain_reach`: pick the crossing BOTH legs' conduit chains REACH + per-leg
  station-delta closure (selects 2+22=0+00 INSTALLER HH start over the parallel 2+72). End 5+10 FLOWER POT.
- **`f75c5c6` — log4 (46→47), FIRST fiber-MAIN render.** 2-1.25" fiber, 15+13→21+63 (650'), N-leg s3→s4→s5;
  both endpoints printed NEXTLINK HHs. Gated `fiber_conduit_candidate_set` (adds generic `BORE - PATH` for THIS
  log only — global `BASE_CONDUIT` UNTOUCHED) + `nleg_matchline_identity_join` (SEE-SHEET identity join for the
  single-run x-offset-frame case). drawn 647.6' closes 650'; no overlap with drawn s3/4/5 bores.
- **`62ee0da` — log42 (47→48), owner-corrected terminal + sibling-trunk gate.** Owner visual review CORRECTED
  the end: STA 2+87 = TERMINAL 6 PORT HH (AP-105 SPLICE LOC 25), NOT a pothole. End binds by the AP-105 id;
  start 7+40=0+00 NEXTLINK HH uniquely closure-selected (sibling log41's 0+46 fails). Cross-sheet via 2+70/5+16;
  277.7' closes 287'. Shares ~34.7' ORIGIN TRUNK with drawn sibling log41 then diverges → NARROW gated
  `sibling_shared_origin_trunk_ok` (same parent + origin + capped + divergent; the log14/log10 full-duplicate
  shape is REJECTED, test-locked). NOT a general overlap waiver.
- Invariants every commit: census FROZEN (flag-OFF 31/6/1/17/3, flag-ON 22/1/4); `TRUELINE_MANUAL_ADJUDICATIONS`
  default-OFF; no corpus/`parent_source_model`/fixture mutation; NO census rebaseline; NO new production flag; red strokes.

## Current redline frontier
**48/58 drawn** (+log30 +log4 +log42 this arc). Remaining **10**: log3, log5, log14, log15, log16, log31, log38,
log43, log44, log57 — **all owner/source-gated** (no safe deterministic auto-draw left without owner input):
- **Owner-adjudication (duplicate / contains-a-drawn-sibling):** log14 (route = drawn log10, 0.0 ft), log3
  (contains drawn log4 + start 12+63 unprinted).
- **Owner source-verification:** log44 (source-location conflict — corpus print 18 vs the sheet-13 Woodson trace
  / sheet-10 chain; close — would render like log42 once the sheet+start are confirmed).
- **Owner-locked ABSTAIN:** log5, log31, log38, log43 (`must_remain_abstained`).
- **Source-gap:** log15/log16 (unprinted ruler-cuts → sheet-5+ head-end), log57 (`.FS` drive sheet, absent).

## Current next gates (each separately authorized; NONE started)
1. **Owner-adjudication** on log14 (distinct vs log10 duplicate) and log3 (distinct vs duplicate-of-log4 + a
   source-bound start at 12+63). Pure adjudications — no new source needed for the decision.
2. **Owner source-verification** on log44: is it the sheet-13 Woodson run (AP-158 TERMINAL 6 PORT HH → 3+23
   FLOWER POT), i.e. is corpus "print 18" a mapping error, and what is the exact start? One answer → renders.
3. **Owner-locked abstains** log5/31/38/43 — owner must lift the abstain + supply safe source.
4. **Source-gap** log15/log16 (sheet-5+ head-end for the unprinted cuts) + log57 (`.FS` drive-decomposition sheet).

## Current known blockers (each a NAMED missing piece, NOT a generic solver limitation)
- **log14** — its source route coincides 0.0 ft with the already-drawn log10 (different parents, SAME s7 conduit,
  same 4+16 SEE-SHEET-15 matchline) → DO-NOT-WIDEN duplicate; owner-adjudication (distinct vs duplicate).
- **log3** — different parent from log4 but geographically CONTAINS the drawn log4 (shared 15+13→21+63); start
  `12+63` unprinted (`12+66` is a non-structure run-start); 2-intermediate-sheet N-leg unsupported → owner-adjudication + start source.
- **log44** — source-location conflict across sheets 18/13/10 (corpus print 18 has no matching run; the AP-158
  terminal + 3+23 flower-pot trace is on sheet 13; the 43+36 chain is on sheet 10) → owner source-verification.
- **Owner-locked abstains** log5/31/38/43 (`must_remain_abstained`); **source-gap** log15/16 (unprinted cuts) + log57 (`.FS`).
- **Stored-anchor debt** — log48 (corrupted `5+14`) + log70 (superseded `1+45`) render via the override, but the
  stored fixture values are still wrong; repair under a census re-baseline. (B-DATA-LOG48-ADJ-1.)
- (RESOLVED continued 31: log30/log4/log42 rendered `a8b2d31`/`f75c5c6`/`62ee0da`; fiber-MAIN render path proven
  (gated `fiber_conduit_candidate_set` + `nleg_matchline_identity_join`); sibling-shared-trunk gate added; log42
  end re-identified as the AP-105 terminal, not a pothole.)

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
