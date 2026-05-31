# Active Context (load this FIRST — keeps /start-session cheap)

> Compact session bootstrap. Read this before hot.md/current-sprint/log/current-bugs.
> Those big logs are historical truth — open them only when a specific question needs them.

## Repo state
- Branch: `pdf-ap-route-shadow`
- `origin/main` = `42f58f6` (local HEAD tracks it)
- Tree: tracked clean; untracked diagnostics live in `scripts/` (offline probes, *_replay.py, bore_log7_*).

## Mission (non-negotiable)
Deterministic auto-placement of **ALL** redlines from source files. Manual placement is NOT the product.
**DO-NOT-WIDEN**: never place a wrong redline. Abstention = interim safety state + a *named* extraction
target. Drive abstentions to zero by EXTRACTING the missing relationship from the source files — not by
guessing, and **not by asking a human to decide from vibes**. Human review is FINAL AUDIT ONLY; the
PDFs/maps/KMZ/bore-logs are the authority.

## Last shipped
- **Target #14 `20cb32f`** — `TRUELINE_TERMINAL_TAIL_PLACEMENT` (default-OFF). First redline-moving
  proof: bore_log7 moves route_477 → route_469 when ON; only bore_log7 changes; counts + trust ledger
  (34/30/0/0/5) identical OFF and ON; adversarial SAFE.
- **Target #15 `42f58f6`** — docs-only GAC review packet `gac/bore_log7_ground_truth_review.md`.

## Active flags — ALL default-OFF, NONE flipped on Render
`TRUELINE_TERMINAL_TAIL_PLACEMENT` (requires `TRUELINE_TERMINUS_TYPE_SHADOW`), `TRUELINE_TERMINUS_TYPE_SHADOW`,
`TRUELINE_MRQ_PLACEMENT_PROOF`, `TRUELINE_BACKBONE_CHAIN_SHADOW`, `TRUELINE_PDF_AP_TOPOLOGY_V2`,
`TRUELINE_PDF_AP_EXTRACT_V2`, `TRUELINE_MRQ_PLAN_SHEET_GRAPH_EVIDENCE`.

## Forbidden lanes (this mission)
Do NOT: widen `TRUELINE_TERMINAL_TAIL_PLACEMENT`; flip any Render flag; clean Render storage (unless
uploads are actively blocked); drift into auth, UI, broad PDF interpreter, KMZ Stage B3, densification
near-ties, or screenshot-tooling plumbing.

## Exact next redline action
**bore_log7 = ADJUDICATED: route_469 PROVEN from source** (PDF sheet 10 + KMZ + bore_log7.xlsx triangulate;
route_477 is a hardcoded-print-index artifact, ≥363 ft from AP-163; no extraction gap). Full proof:
`gac/bore_log7_route_adjudication.md`.
- Next (operator-side, NOT this session): final-audit the proof, then flip `TRUELINE_TERMINAL_TAIL_PLACEMENT`
  (+ `TRUELINE_TERMINUS_TYPE_SHADOW`) on Render — engine path already shipped (Target #14), no code change.
- Next engineering lane (same deterministic method): the flower-pot DROP lane (bore_log5/30/48/50/65) —
  prove each terminates at its flower-pot node (run→endpoint table already has the termini) and place on
  its drop geometry, scoped + default-OFF, DO-NOT-WIDEN intact.

## Render disk caution
`/data` can fill → upload/session/audit failures. If uploads fail, operator runs `df -h /data` BEFORE
blaming code (B-WS-12 OOM fingerprint = bore-log upload 502 `<!DOCTYPE html>`). If tight: inspect/backup/
compact ONLY `session_store.db`. NEVER touch `auth.db`, `station_photos`, `engineering_plans`; never
blind-delete `session_store.db`. Storage is a pit stop, not the mission.

## Chrome / visual QA status
Claude-in-Chrome: intermittently NOT connected (`list_connected_browsers` → `[]`). Playwright: no Chrome
binary installed. Claude Preview: WORKS for local HTML (used for the bore_log7 satellite map at
`scripts/bore_log7_placement_map.html`). Visual proof SUPPORTS deterministic evidence; it never replaces it.

## Context budget rules
- No 193k bootstrap. Don't read full hot.md/current-sprint/log/current-bugs unless required.
- Trust commit/wiki summaries as history unless current code contradicts them.
- Before any broad expansion state: (1) question it answers, (2) files/sections, (3) why narrower is
  insufficient, (4) stop condition.
- Subagents: narrow lane each; report exactly what was read; no duplicate broad rereads.
