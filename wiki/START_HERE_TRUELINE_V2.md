# START HERE — TrueLine v2 Canonical Bootstrap

> Single source of current working truth. Read THIS file first, in full — it is small on purpose.
> Snapshot below is current as of **2026-06-19 (continued 37 — redline-manifest engine→website CONTRACT pipeline COMPLETE, Phases 2A–2I; NO render-truth change; frontier 50/58)**. For the absolute-latest
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
  (log3/log44 added assertions to the existing sweep e2e — no new test). Callout-sweep e2e **31 passed / 1 skipped**.
- Isolated track: monolith / Render / Vercel UNTOUCHED; nothing merged or deployed.

## HEAD / remote state (verify with `git` before trusting this snapshot)
- Last RENDER commit: **`c19b565`** (log3 wired + DRAWN, 49→50/58 — UNCHANGED). Local HEAD = **`81f3cd3`**
  (continued-37 redline-manifest CONTRACT pipeline complete; pushed → `origin/feat/truelinev2` = `81f3cd3`). Continued-37
  12-commit proof/contract lineage on the continued-36 save `744d88c`: `a0a490f`→`505a9a2`→`bccfdc8`→`4c11722`→`f7a616b`→`c0498d4`→`06c734a`→`f7988ab`→`cbeb9be`→`aaa8952`→`9ed6c98`→`81f3cd3` (NO render-truth change).
  ARCHIVE (recovery): branch/tag `archive-v2-continued-35-superseded-scratch` = **`d8508b9`** (superseded `backend/tl_core/**` + 14 proof slices). `origin/main`: **`068a279`** (untouched).

## Latest — continued 37 (2026-06-19): redline-manifest engine→website CONTRACT pipeline COMPLETE (Phases 2A–2I); NO render-truth change; frontier 50/58
**continued 37 — 12-commit proof/CONTRACT arc; NO engine/renderer/fixture/anchor/corpus/census/parent-model/flag change;
frontier UNCHANGED 50/58; render commit stays `c19b565`; HEAD `81f3cd3`.** Built + proved the entire engine→website
redline-manifest pipeline, all generated artifacts GITIGNORED under `data/outputs/` (NONE committed): schema-pinned
`truelinev2/contracts/redline_manifest.schema.json` + a 50/58 example (2A `a0a490f`) → static manifest-driven mock UI
(`505a9a2`) → artifact **publisher** (real sha256/bytes, `mock_example:false`; `bccfdc8`) → existing-artifact inspection
(2A.5 `4c11722`) → **2B STOP** (`f7a616b`: a unified all-50 render is impossible without a solver change — the callout
sweep hardcodes the ALREADY_DRAWN skip; refused partial-37-as-50) → **2C** canonical render registry re-renders the 13
ALREADY_DRAWN through their existing lanes (`c0498d4`; resolves 2B WITHOUT a solver change; 13/13, log50 incl, log7 PARTIAL)
→ **2D** first REAL all-50 manifest (`06c734a`; 83 artifacts/50.5 MB, 58/50/1/7) → **2E** published-bundle contract
(`f7988ab`; static-serving safe, checksum-verified, bundle index) → **2F** one-command pipeline runner (`cbeb9be`; + fixed
a latent zero-bucket reconciliation false-rejection) → **2G/2H** render benchmarks (`aaa8952`/`9ed6c98`: 13=52.2 s,
37=299.6 s; full refresh ~5.9 min, render-bound) → **2I** adapter-neutral durable bundle store (`81f3cd3`; immutable
content-keyed `bundles/<id>/` + `store_index.json` `latest_valid` + retention + `WEBSITE_READ_CONTRACT`; real bundle stored
`brenham-c19b565-ddfffff7cbe7`, store VALID). ~63 targeted contract tests (61 pass + 2 jsonschema-optional skips).
`B-DATA-LOG48-ADJ-1` unchanged. The full local contract+storage chain is complete + benchmarked; the next step crosses into
website/backend wiring (gated). Detail: [[current-sprint]] / [[log]] continued 37.

### Prior — continued 36 (2026-06-19): repo-hygiene arc COMPLETE (101→0 untracked); NO render; frontier 50/58
**continued 36 — pure repo-hygiene + provenance; NO engine/render/census change; frontier UNCHANGED 50/58; render commit
stays `c19b565`; HEAD `e3df509`.** The continued-35 inventory found 101 untracked files; this arc drove it to **0** without
losing anything. Feat lineage (on the continued-35 save `69dd876`): **`f5dbed1`** committed the evidence trail (7 `gac/*.md`
source-adjudication packets + `run_review_candidate_reasoning_sweep.py`); **`c0e6680`** committed 4 Group-A evidence slices
(KMZ↔PDF georeference ×2, the ambiguity-resolution render primitive, the `gac/log44`-cited owner-source packet); **`e3df509`**
relocated the token-reduction doctrine to `wiki/doctrine/`. A pushed **ARCHIVE** branch+tag `archive-v2-continued-35-superseded-scratch`
= **`d8508b9`** preserves the superseded `backend/tl_core/**` (35) + 14 ambiguous proof slices, which were then removed from the
working tree (step 4C); 26 scratch probes + `probe_err.txt` were deleted (step 5); the old-app `RECOVERED_BASELINE_98d108a.md`
note was deleted (owner decision; recoverable via tag `recovered-pdf-first-overlay-98d108a` + branch `backup-live-lp-chain-6eaade3`).
**`backend/tl_core` is now ARCHIVE-ONLY** (a superseded reuse-by-import wrapper, never imported by v2); the `git add -A` landmine is
DEFUSED; **repo hygiene is COMPLETE (untracked = 0)**. NO code/renderer/fixture/census/flag change. Detail: [[current-sprint]] / [[log]] continued 36.

### Prior — continued 35 (2026-06-19): accountability ledger + website-readiness audit + repo-hygiene (NO render; frontier 50/58)
**continued 35 — docs + repo-hygiene checkpoint; NO engine/render/census change; frontier UNCHANGED 50/58; render commit
stays `c19b565`.** Four commits on `feat/truelinev2` (HEAD **`8ea66bc`**): **`b083b76`** added
`wiki/trueline_v2_50_of_58_accountability_table.md` — the 58-log ledger (**50 DRAWN / 1 COVERED log14←log10 / 4
OWNER_LOCKED_ABSTAIN log5·31·38·43 / 2 SOURCE_GAP log15·16 / 1 MISSING_SOURCE_SHEET log57**; drawn set = sweep
`ALREADY_DRAWN`∪`NEW_TARGETS`; `placement_status` proven STALE → never the drawn census). **`15e00f7`** added
`wiki/trueline_v2_engine_website_readiness_audit.md`: the engine is **accountability-complete but NOT 58/58
drawn-complete and NOT website-ready** — the gap is a CONTRACT boundary (no machine-readable `redline_manifest.json`;
no clean parameterized runner — proof-script-driven + Brenham-hardcoded, seam exemplar-only log53/64/71, API default-OFF
review-card transport; artifacts gitignored/on-demand; runtime unbenchmarked; stale `placement_status`; proof≠final),
with 5 status + 6 provenance enums (**log3 preserved OWNER_CONFIRMED_HUMAN_ADJUSTABLE, not AUTO**) + the two-truth-axes
warning. **`6f2e4a5`** (repo-hygiene fix 1) tracked the load-bearing
`truelinev2/proof/run_station_corridor_route_solver_slice.py` (imported by TRACKED `run_log15_log16_run_group_review_slice.py:37`
+ `test_log15_log16_run_group_review.py:79` → clone/CI fix; targeted test 8 passed). **`8ea66bc`** (repo-hygiene fix 2)
added `.gitignore` rules `.agents/` + `skills-lock.json` (untracked 100→86). NO code/renderer/fixture/census/flag change.
Safe website work NOW = contract-first mock UI vs the manifest schema; no live wiring. Detail: [[current-sprint]] /
[[log]] continued 35.

### Prior — continued 34 (2026-06-19): log3 WIRED + DRAWN (49→50)
**continued 34 — log3 owner-confirmed / HUMAN-ADJUSTABLE GEOMETRY render.** Frontier **49 → 50/58** (log3 = 50th
drawn). Lineage `069e70d` (continued-33 save) → **`683825c`** (log3 owner-control ingest PROOF, 16/16, read-only)
→ **`c19b565`** (log3 sweep WIRING, DRAWN). The s3 `12+66→15+13` conduit is too FRAGMENTED to auto-trace
(`DESIGN_PATH_NOT_CONNECTED`); the owner confirmed the route + dotted the TOP path → 11 owner control points
DIFF-ingested → the s3 leg is the STRAIGHT segment between two source-bound endpoints (matchline crossing @ owner
top-y 296.5 → `15+13 NEXTLINK HH`), control-point-verified (maxdev 1.3pt), closing 247.7'. Renders 2 red strokes
(s2 `12+63 FLOWER POT` stub 2.8' + s3 247') via gated opt-ins `printed_run_callout_chain_route` +
`owner_confirmed_geometry`; new content = upstream **250'**, downstream `15+13→21+63` (650') COVERED by drawn log4
(gated `covered_by_drawn_children` parent-gate exception), 0 overlap. **FIRST owner-GEOMETRY render** — Patrick
classified it the **HUMAN-ADJUSTABLE lane** (NOT deterministic AUTO), reconciling with "never invented
coordinates / manual placement is not the [AUTO] product". All **64 prior PNGs BYTE-IDENTICAL** (md5 stash-baseline
diff); census FROZEN (`doc`); `parent_source_model`/fixtures UNTOUCHED; v2 1392/2-skip; e2e PASS. Doctrine:
fragmented conduit + parallel tracks → owner picks the track + confirms straightness → straight segment between
BOUND endpoints (minimal, not freehand); DIFF-vs-baseline ingests owner packets (only explicit marks). Detail:
[[current-sprint]] / [[log]] continued 34.

### Prior — continued 33 (2026-06-18, READ-ONLY adjudication; no render)
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
**50/58 drawn** (+log3 this arc). **log3 RESOLVED — WIRED + DRAWN** (continued-34, `c19b565`): owner-confirmed /
HUMAN-ADJUSTABLE GEOMETRY render — s2 `12+63 FLOWER POT` stub (2.8') + s3 247' STRAIGHT top-path between two bound
endpoints (matchline crossing @ owner top-y → `15+13 NEXTLINK HH`, 11-control-point-verified); downstream
`15+13→21+63` (650') covered by drawn log4. **log14** remains a confirmed DUPLICATE of drawn log10
(covered_by_existing_redline — the 8th non-drawn, NOT a missing redline). Remaining genuinely-open **7**:
log5, log15, log16, log31, log38, log43, log57 — all owner/source-gated:
- **Owner-locked ABSTAIN:** log5, log31, log38, log43 (`must_remain_abstained`).
- **Source-gap:** log15/log16 (unprinted ruler-cuts → sheet-5+ head-end), log57 (`.FS` drive sheet, absent).
- (RESOLVED continued 34: log3 WIRED + DRAWN — owner-confirmed/human-adjustable GEOMETRY, the FIRST owner-geometry
  render; gated per-log opt-ins, 64 prior PNGs byte-identical, census frozen, fixtures untouched. `c19b565`.)
- (RESOLVED continued 33: log14 = confirmed DUPLICATE of drawn log10; log3 reclassified (then wired in 34) —
  packet `gac/log3_log14_owner_adjudication.md`.)
- (RESOLVED continued 32: log44 rendered `7039c48` — owner source-verified the corpus print-18 mis-map onto the
  Woodson s10+13 run; AP-158/2+45 intermediate, STA 3+23 FLOWER POT end. The source-location conflict is closed.)

## Current next gates (each separately authorized; NONE started)
1. **Website / backend wiring** — read the durable store's `latest_valid` bundle (Phase 2I) + serve `redline_manifest.json`
   + artifacts statically; point the Phase-1 mock UI at a REAL served bundle as the first integration test (NO live render).
   **← recommended next**, but GATED: crosses into `web/`/`backend/` (currently forbidden — needs explicit authorization).
   Then a cloud/object-store adapter behind the store contract; then deploy. Canonical: `wiki/trueline_v2_redline_manifest_contract.md`.
2. **`TRUELINE_V2_REDLINEMANIFEST_SCHEMA_AND_RUNNER_CONTRACT`** — ✅ DONE (continued-37, Phases 2A–2I, `a0a490f`→`81f3cd3`):
   schema + 50/58 example + mock UI + publisher + unified render registry + real all-50 manifest + published-bundle contract +
   one-command pipeline runner + render-cost benchmark (full refresh ~5.9 min, render-bound) + adapter-neutral durable bundle
   store. All generated artifacts gitignored under `data/outputs/`; ~63 contract tests. Optional follow-on: a warm-engine /
   single-process unified runner to cut the ~6 min refresh.
3. **Repo hygiene** — ✅ COMPLETE (continued-36): untracked 101→0; evidence trail + Group-A committed (`f5dbed1`/`c0e6680`),
   superseded set archived at `d8508b9`, doctrine relocated (`e3df509`). The `git add -A` landmine is defused.
4. **Accountability table** — ✅ DONE (continued-35, `b083b76`); website-readiness audited (`15e00f7`).
5. **Owner-locked abstains** log5/31/38/43 + **source-gap** log15/16 + log57 — unchanged (owner/source input needed).

## Current known blockers (each a NAMED missing piece, NOT a generic solver limitation)
- **log14** — RESOLVED continued-33: its only bindable s7 route IS drawn log10's first leg (reset `0+58=0+00`,
  run `0+00→4+16`; end `4+18` unprintable, `solve_log` BLOCKED) → confirmed DUPLICATE / covered_by_existing_redline.
  Not a missing redline.
- **log3** — RESOLVED continued-34: WIRED + DRAWN (`c19b565`) as an owner-confirmed / HUMAN-ADJUSTABLE GEOMETRY
  render. The fragmented s3 conduit couldn't auto-trace (`DESIGN_PATH_NOT_CONNECTED`), so the owner confirmed the
  straight TOP path (11 control points); s2 `12+63 FLOWER POT` stub + s3 247' straight segment between bound
  endpoints; downstream `15+13→21+63` covered by drawn log4. No longer a blocker. (Was reclassified in continued-33.)
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
