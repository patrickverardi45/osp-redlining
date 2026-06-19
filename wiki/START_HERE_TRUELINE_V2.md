# START HERE — TrueLine v2 Canonical Bootstrap

> Single source of current working truth. Read THIS file first, in full — it is small on purpose.
> Snapshot below is current as of **2026-06-18 (continued 33 — log3/log14 owner-adjudication, read-only; 49/58)**. For the absolute-latest
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
- Product lives in `truelinev2/` (clean-room, zero old-app imports). v2 suite: **1392 passed / 2 skipped**
  (log44 added assertions to the existing sweep e2e — no new test). Callout-sweep e2e **31 passed / 1 skipped**.
- Isolated track: monolith / Render / Vercel UNTOUCHED; nothing merged or deployed.

## HEAD / remote state (verify with `git` before trusting this snapshot)
- Last RENDER commit: **`7039c48`** (log44, 49/58 — unchanged; continued-33 was read-only). Local HEAD = the
  continued-33 read-only adjudication+docs commit on top of save-32 `96b0143` (pushed → `origin/feat/truelinev2`).
  `origin/main`: **`068a279`** (untouched).

## Latest — continued 33 (2026-06-18, READ-ONLY adjudication; no render)
**continued 33 — log3/log14 owner-adjudication (READ-ONLY).** No render; frontier UNCHANGED **49/58**. **log14 =
confirmed DUPLICATE of drawn log10** — its only bindable s7 route is log10's first leg (`0+58=0+00 / 0+00→4+16`);
end `4+18` unprintable; `solve_log` BLOCKED → covered_by_existing_redline, NOT a missing redline (effective
denominator ~57). **log3 = RECLASSIFIED distinct longer bore** (not a duplicate): `12+63` is printed on s2 as a
DRIVEWAY boundary (non-structure → unbindable start); `12+66` is the s2/s3 matchline; log3 shares log4's
`15+13→21+63` downstream half; nearest real origin = the 9+75 AP-106 8-port HH (288' upstream/outside span) →
moved from "owner-adjudication" to "owner span-correction + N-leg solver" blocker. Evidence packet
`gac/log3_log14_owner_adjudication.md` (committed). NO engine/render/census/fixture mutation. Doctrine: a corpus
"start" can be a driveway/matchline cut — trace the continuous-frame chain across matchlines before ruling
duplicate/dead-end. Detail: [[current-sprint]] / [[log]] continued 33.

### Prior — continued 32 (2026-06-18): log44 render (48→49)
ONE render this arc — frontier **48 → 49/58** (one actual drawn red stroke). Lineage `62ee0da` → `44597ff`
(continued-31 save) → **`7039c48`** (pushed → `origin/feat/truelinev2` = `7039c48`). Census FROZEN; both new
primitives are GATED per-log opt-ins → all **62 prior render PNGs BYTE-IDENTICAL** (md5-verified); global
`BASE_CONDUIT` / `MAX_DASH_GAP` / `parent_source_model.json` untouched. Only two files changed:
`truelinev2/proof/run_callout_route_assembly_sweep.py` + its test.
- **`7039c48` — log44 (48→49), owner-corrected Woodson run + footage-tick evidence.** bore_log17 Segment B.
  Owner SOURCE-VERIFIED the corpus "print 18" as a sheet mis-map onto the real **WOODSON LN drop on sheets
  10+13**. Cross-sheet 2-leg (the log70 shape): **STA 43+36 INSTALLER HH** (s10, = local 0+00) → down Woodson
  167' → **MATCHLINE 1+67/1+66 SEE SHEET 13** → past **AP-158 TERMINAL 8 PORT HH (STA 2+45, INTERMEDIATE)** →
  **STA 3+23 FLOWER POT** (s13); drawn 318.2' closes 323' (corpus 325'). Binds on `endpoint_anchors` alone; the
  bundled 1+67/1+66 matchline is unique by chain-reach (the parallel 1+66 RIGHT sibling excluded). TWO new
  GATED opt-ins: (1) `owner_corrected_parent_sheet_context` flips the parent gate's stale corpus sheet
  [18]→[10,13] ONLY after span-closure + anti-sibling-mixup already pass (fixture untouched); (2)
  `footage_tick_ladder_route_evidence` — NEW reusable primitive: the printed **2'/5'/7' footage-tick LADDERS**
  corroborate each leg's direction + length (abstains if a leg lacks one; NEVER sets endpoints; band 22pt <
  half the ~50' ROW spacing → belongs to THIS bore, not a parallel sibling). Overlap clean: only the shared
  3+23 FLOWER POT junction with the consecutive log47 (0' coincident; distinct parents).
- Prior arc (continued 31, `a8b2d31`/`f75c5c6`/`62ee0da`): log30 (Ledbetter parallel), log4 (FIRST fiber-MAIN),
  log42 (owner-corrected AP-105 terminal). Detail: [[current-sprint]] / [[log]] continued 31.
- Invariants this commit: census FROZEN (flag-OFF 31/6/1/17/3, flag-ON 22/1/4); `TRUELINE_MANUAL_ADJUDICATIONS`
  default-OFF; no corpus/`parent_source_model`/fixture mutation; NO census rebaseline; NO new production flag; red strokes.

## Current redline frontier
**49/58 drawn** (unchanged; continued-33 was read-only). **log14 RESOLVED** as a confirmed DUPLICATE of drawn
log10 (covered_by_existing_redline — not a missing redline; effective placeable denominator ~57). Remaining
genuinely-open **8**: log3, log5, log15, log16, log31, log38, log43, log57 — all owner/source-gated:
- **Owner span-correction + N-leg solver:** log3 — distinct longer bore than drawn log4 (shares `15+13→21+63`);
  recorded start `12+63` is a printed DRIVEWAY boundary on s2 (non-structure → unbindable; `12+66` is the s2/s3
  matchline). Re-origin to the 9+75 AP-106 8-port HH needs owner authorization + s2→s5 N-leg support.
  (Reclassified continued-33 from owner-adjudication; was wrongly framed as "12+63 unprinted".)
- **Owner-locked ABSTAIN:** log5, log31, log38, log43 (`must_remain_abstained`).
- **Source-gap:** log15/log16 (unprinted ruler-cuts → sheet-5+ head-end), log57 (`.FS` drive sheet, absent).
- (RESOLVED continued 33: log14 = confirmed DUPLICATE of drawn log10; log3 reclassified to owner span-correction
  + N-leg solver — packet `gac/log3_log14_owner_adjudication.md`. Read-only lane, no render.)
- (RESOLVED continued 32: log44 rendered `7039c48` — owner source-verified the corpus print-18 mis-map onto the
  Woodson s10+13 run; AP-158/2+45 intermediate, STA 3+23 FLOWER POT end. The source-location conflict is closed.)

## Current next gates (each separately authorized; NONE started)
1. **Owner-locked abstains** log5/31/38/43 — owner must lift the abstain + supply safe source. **← recommended next lane.**
2. **Source-gap** log15/log16 (sheet-5+ head-end for the unprinted cuts) + log57 (`.FS` drive-decomposition sheet).
3. **Owner span-correction** for log3 — authorize re-origin to the 9+75 AP-106 8-port HH (changes the recorded
   span) + build s2→s5 N-leg solver support. (log14 needs no gate — resolved continued-33 as a duplicate of log10.)

## Current known blockers (each a NAMED missing piece, NOT a generic solver limitation)
- **log14** — RESOLVED continued-33: its only bindable s7 route IS drawn log10's first leg (reset `0+58=0+00`,
  run `0+00→4+16`; end `4+18` unprintable, `solve_log` BLOCKED) → confirmed DUPLICATE / covered_by_existing_redline.
  Not a missing redline.
- **log3** — RECLASSIFIED continued-33: a distinct, genuinely-longer bore than drawn log4 (shares `15+13→21+63`),
  but recorded start `12+63` is a printed DRIVEWAY boundary on s2 (non-structure → unbindable; `12+66` is the
  s2/s3 matchline, NOT a run-start). Nearest real origin = the 9+75 AP-106 8-port HH (288' upstream/outside span).
  Blocker = owner span-correction (re-origin) + s2→s5 N-leg solver. Packet `gac/log3_log14_owner_adjudication.md`.
- **Owner-locked abstains** log5/31/38/43 (`must_remain_abstained`); **source-gap** log15/16 (unprinted cuts) + log57 (`.FS`).
- **Stored-anchor debt** — log48 (corrupted `5+14`) + log70 (superseded `1+45`) render via the override, but the
  stored fixture values are still wrong; repair under a census re-baseline. (B-DATA-LOG48-ADJ-1.)
- (RESOLVED continued 32: log44 rendered `7039c48` — owner source-verified the corpus print-18 mis-map onto the
  Woodson s10+13 run via two gated opt-ins (`owner_corrected_parent_sheet_context` + the reusable
  `footage_tick_ladder_route_evidence`); the source-location conflict across sheets 18/13/10 is closed.)
- (RESOLVED continued 31: log30/log4/log42 rendered `a8b2d31`/`f75c5c6`/`62ee0da`; first fiber-MAIN render path
  proven; sibling-shared-trunk gate added; log42 end re-identified as the AP-105 terminal, not a pothole.)

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
