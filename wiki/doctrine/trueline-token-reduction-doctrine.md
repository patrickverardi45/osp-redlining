# TrueLine Token-Reduction Doctrine

Purpose: stop future Claude Code sessions from burning tokens on stale full bootstraps
and stop asking permission for safe routine repo commands.

This doctrine is the source of truth for the project-local skill
`.claude/skills/trueline-redline-engine/SKILL.md`. Keep them in sync.

## Why this exists

`/start-session` loads the full external Obsidian wiki bootstrap
(`hot.md` + `index.md` + `current-sprint.md` + `current-bugs.md`). Those files are
large (hundreds of KB), frequently stale, and almost never all needed for a focused
redline-engine task. Sessions were re-reading them, trusting their stale commit SHAs,
and then re-deriving state that `git` already knows authoritatively.

## Operating principles

1. **Lean entry point.** Start from the repo-local `wiki/active-context.md`, not the
   full wiki bootstrap. Only escalate to `hot.md` / `current-sprint.md` /
   `current-bugs.md` if a specific pointer must be read or updated.
2. **Git is truth; summaries are hints.** Before trusting any narrative SHA, verify with
   `git rev-parse --short HEAD` and `git rev-parse --short origin/main`. A wiki summary
   can lag reality by several commits.
3. **Deltas only.** Read the smallest slice that answers the question — `git show`,
   `git diff`, `sed -n`, `rg`. Do not re-read whole files you already touched.
4. **Redline-engine focus only.** No drift into Render/auth/UI/screenshots/broad PDF/
   KMZ Stage B3/densification/router setup.
5. **Routine commands are pre-approved; mutations are not.** Safe read-only and
   compile/lint/build commands run without a prompt; anything destructive or
   out-of-repo asks first.

## Current repo edge (update when it moves)

- `origin/main = 88c6573`
- branch = `pdf-ap-route-shadow`
- Targets #18 (DrillPathFrame shadow layer), #19 (bucket review), #20 (DROP-lane
  flower-pot identity), #21 (main-chain high-station adjudication), #22 (matchline
  chainage probe) all pushed.
- Target #22 pushed: proved the main-chain high-station blocker is **data-absence, not
  extraction** (the matchline-equation network is already extracted; the station↔geometry
  anchor for 4000–5950 ft is absent across all provided Brenham sources). bore_log16/43
  remain BLOCKED until a high-station anchor, the `.FS` drive-decomposition sheet, or a
  bore-log start-structure/direction field is provided.

## Guardrails

No app/engine/backend/web changes, no tests authored, no agents, no dependency
installs, no env/secrets edits, no destructive commands, no `/start-session` as a
reflex. Token discipline: deltas only.
