# Active Context (load this FIRST — keeps /start-session cheap)

> Compact session bootstrap. Read this before hot.md/current-sprint/log/current-bugs.
> Those big logs are historical truth — open them only when a specific question needs them.

## Repo state
- Branch: `pdf-ap-route-shadow`
- `origin/main` = `f0fbcc8` (local HEAD tracks it; Targets #18/#19/#20/#21 pushed). Target #22 probe/docs pushed on top.
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
**bore_log7 = ADJUDICATED + SHIPPED-as-shadow.** route_469 PROVEN from source (`gac/bore_log7_route_adjudication.md`);
DrillPathFrame proof layer shipped default-OFF (Target #18 `93434cd`, `TRUELINE_DRILL_PATH_FRAME_SHADOW`).
Operator-side next (NOT this session): final-audit, then flip `TRUELINE_TERMINAL_TAIL_PLACEMENT`
(+`TRUELINE_TERMINUS_TYPE_SHADOW`) on Render — engine path already shipped, no code change.

**DROP lane (bore_log5/30/48/50/65) = BLOCKED, fully diagnosed (Target #20).** No unique drop-identity
key exists in the files: flower-pot KMZ nodes are vacant/identity-less (no name/SCID/address), drop routes
carry only "Connection Type", each pot touches 2–6 drop routes, PDF flower-pot callouts carry no unit id.
NEW finding: the KMZ `<description>` HTML (parser currently DROPS it) carries House Address + AP Number +
Terminal-Port-HH AP Number — rich, but does NOT bind vacant flower pots. Missing artifact (any one closes it):
flower-pot SCID/address in KMZ, OR the `.FS` drive-decomposition sheet, OR a served-address column in the
bore xlsx. Helper `resolve_flowerpot_drop_identity(...)` is DESIGNED (abstain-until-key), not built. Full:
`gac/drop_lane_flowerpot_identity.md`. DO-NOT-WIDEN: drops abstain until a key arrives.

DrillPathFrame bucket review (Target #19, `gac/drill_frame_bucket_review.md`): 1 PROVEN (bore_log7), 13
BLOCKED; overlap detector = 58 unproven_overlap pairs (print-index stacks 11 logs on route_477, 3 on route_478).

**MAIN-CHAIN lane (bore_log16/43) = BLOCKED, PARTIAL probe (Target #22).** Corrects Target #21 §5.1: the
matchline-equation network is ALREADY EXTRACTED (`brenham_plan_sheet_graph.py` — boundary STA equations
1625→3393, SEE-SHEET corridor graph), so it is NOT the missing piece. Real blocker = a **station↔geometry
anchor** at the bores' high stations (4000–5950): the graph is station-space only (zero lat/lon); the only
station→KMZ bridge is a named AP in `BRENHAM_PH5_RUN_ENDPOINTS`, whose max named-AP station is 3810 (max of
ALL table stations 4533) — far below the bore ends 5919/5950, so NO anchor exists. Self-validation: the
mechanism reproduces bore_log7 (sta 451→AP-163→route_469) but finds NONE near 5919/5950. Missing artifact
(absent, not un-extracted): one high-station named/identified structure that is also a KMZ node + a direction
datum (or the `.FS` sheet, or a start-structure xlsx column). Full: `gac/mainchain_matchline_chainage_probe.md`.
DO-NOT-WIDEN: bore_log16/43 abstain until an anchor arrives.

**REMAINING route_480 logs (57, 29/31/46/47/58) = BLOCKED, 0/6 provable (Target #23).** bore_log57 =
multi_drive_terminus_ambiguous (END 413 hits AP-157 sheet-8 AND a sheet-13 matchline@398; spans 2 corridors;
print mapping flagged uncertain). bore_log29/31/46/47/58 = no_run_terminus_match (continuous multi-drive bores;
END station hits no DIR.BORE run terminus within 15 ft; bore_log46's 534=AP-161 LABEL not a run terminus →
excluded). Missing artifact (all 6) = the **`.FS` Fiber-Schematic / drive-decomposition sheet** (absent from all
3 PDFs; re-confirmed by #22 sweep) OR a per-bore terminus/direction field. Full: `gac/route480_remaining_proof_sweep.md`.
**Bucket closeout: all 14 route_480 logs classified — 1 PROVEN (bore_log7), 13 BLOCKED on 3 acquisition artifacts
(flower-pot identity key / high-station anchor+direction / `.FS` drive-decomposition). No bucket log is provable
from current files.** DO-NOT-WIDEN intact.

**EXISTING-CORPUS HUNT (Target #24) — relationship NOT FOUND, full-inventory proof.** Reopened the "ask for files"
conclusion and searched the COMPLETE corpus (not just 3 PDFs): 6 source classes — **71 bore xlsx** (incl. 13
pre-split originals, all 0 non-standard columns), the **80-pg Fieldwire punch-list** (holds a **63-entry `AP→.FS`
page register** + `AP→.WP` + item/date, but **0 bore_log mentions, 0 AP↔STA lines**; the `.FS` PAGES themselves are
absent — only references), the **539-route context JSON** (pure geometry, 0 structure tokens), the design KMZ
(flower pots id-less, Target #20), and TrueLine's own golden fixtures. **Bore lineage (station/crew/date/print) and
structure lineage (AP/.FS/.WP/SCID) share NO join key in ANY file** — the single missing edge is `bore↔AP/structure`.
0/13 blocked logs gain an extractable relationship. No code target extracts these from current files. Full:
`gac/target24_existing_corpus_artifact_hunt.md`. DO-NOT-WIDEN intact.

**AP/STRUCTURE-INDEX SHADOW (Target #25) — BUILT, read-only, placement-free.** Pre-joined the structure-SIDE facts
we DO have into a deterministic reusable per-AP index (`scripts/ap_structure_index.py` pure helper +
`scripts/ap_structure_index.json` artifact; isolated in scripts/, no engine import, no flag). Coverage over **64 APs**:
lat/lon **64/64** (every AP geometry-anchor-ready), `.FS` page 63/64, terminal-tail route 48/64, station 10/64, all-four
**8/64** (154/156/157/164/165/166/167/168). Places NOTHING and makes no bore↔structure claim (Target #24 invariant
respected) — it's the catcher so the instant ONE bore→AP/structure clue arrives, that bore resolves to lat/lon (+tail
+station+.FS) with zero re-mining. Self-test `python scripts/ap_structure_index.py selftest` → SELFTEST_OK. Full:
`gac/target25_structure_index_shadow.md`. Next unlock still gated on the single bore→AP edge. DO-NOT-WIDEN intact.

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
