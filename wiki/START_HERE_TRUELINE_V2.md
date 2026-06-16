# START HERE — TrueLine v2 Canonical Bootstrap

> Single source of current working truth. Read THIS file first, in full — it is small on purpose.
> Snapshot below is current as of **2026-06-16 (continued 23)**. For the absolute-latest state, read
> ONLY the top ~35 lines of `C:/Nova/knowledge/TrueLine-Wiki/wiki/hot.md` — never the whole file.
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
- Product lives in `truelinev2/` (clean-room, zero old-app imports). v2 suite: **1342 passed**.
- Isolated track: monolith / Render / Vercel UNTOUCHED; nothing merged or deployed.

## HEAD / remote state (verify with `git` before trusting this snapshot)
- Local HEAD: **`b72f033`** — NOT pushed (awaiting push authorization).
- `origin/feat/truelinev2`: `0300afa`  ·  `origin/main`: **`068a279`** (untouched).

## Latest shipped (local) — continued 23
**`b72f033`** — first new full redline of the arc: **log50** rendered via the **SPLICE-POINT-46
cross-sheet route assembly** (+256; adversarially verified; the render is a gitignored PROOF artifact,
NOT a census placement — log50 stays an abstain in the engine census).
- **The unlock:** the cross-sheet identity bridge is the splice-46 callout pair —
  `PROP. SPLICE POINT 46` (sheet 10, the `STA 45+33=0+00` NEXTLINK HH) ↔ `AP-168 SPLICE LOC 46`
  (sheet 11); NOT AP-168 on sheet 10 (absent there).
- Drawn as two source-backed sheet-local legs joined by the printed station identity `STA 1+39`
  (139' sheet-10 leg + 375' sheet-11 leg = 514' = span; drawn lengths match printed deltas ~0.07%).
- Invariants held: census FROZEN (flag-OFF 31/6/1/17/3, flag-ON 22/1/4); `TRUELINE_MANUAL_ADJUDICATIONS`
  default-OFF; seam `ELIGIBLE_EXEMPLARS` == 5; no fixture / coordinate / owner-naming change.

## Current redline frontier
**13/58 drawn** (12 full + 1 partial). 13 logs anchored; held-back = 8.

## Current next gates (each separately authorized; NONE started)
1. PUSH `b72f033`.
2. Generalize the splice-point-bridge primitive to other `PROP. SPLICE POINT N` ↔ `SPLICE LOC N` drops.
3. Remaining blocked classes await NEW source (georeferenced PDF / more named control points / printed
   origin tags).

## Current known blockers (each a NAMED missing source piece, NOT a solver limitation)
- **Flower-pot drops** — unnamed/identity-less KMZ pots (log30/5/48/65).
- **Cross-sheet origin-ambiguous** — shared `0+00` / AP only on far sheet / <4 georeference control points.
- **Cross-sheet closure-unverifiable** — log9 (+91 reset), log23 (no 8↔15 matchline).
- **Shared drawn alignment** — log8/32/42/56.

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
