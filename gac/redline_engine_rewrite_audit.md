# Redline Engine Rewrite Audit

**Date:** 2026-05-31 · **Branch:** `pdf-ap-route-shadow` · **Type:** strict architecture audit (no implementation)
**Method:** 4 parallel read-only audit agents (engine flow / missed-source / extractor reliability / matching
architecture) + orchestrator synthesis. Every claim is cited to file:line or a reproduced command. Prior
"missing data" conclusions were re-audited against raw bytes, not accepted.

---

## 1. Current repo / HEAD / status

- **HEAD = `927ed43` = `origin/main`** (ahead 0 / behind 0). `active-context.md` header pins `ba6c155`;
  `927ed43` is the newer "pin header" commit on top — consistent with the prompt's "927ed43 or newer".
- Branch `pdf-ap-route-shadow`. **Tracked tree clean**; untracked = `scripts/*` offline probes + a few
  `gac/*.md` + dotfiles. No engine/backend/web file is dirty.
- Recent line: #37 (extractor fix) → #38–#42 (placeability sweeps) → #43 (office-input seam, owner-rejected).

---

## 2. Existing engine map: inputs → extraction → matching → placement → output

Production rebuild = `_rebuild_field_data_outputs` ([backend/main.py:11890](backend/main.py)):

1. **Inputs** — KMZ design + bore-log `.xlsx` + engineering PDFs land in module-level `STATE` (dict).
2. **Extraction** —
   - `_build_route_catalog` ([main.py:3105](backend/main.py)) → routes `{route_id, coords, source_folder, length_ft}`.
   - `_build_kmz_reference` ([main.py:3330](backend/main.py)) → `point_features[]` — **drops `<description>` HTML** (House AP#/Address, Terminal-HH AP# live there; lossy, see §4).
   - `_read_bore_log_rows` ([main.py:5562](backend/main.py)) → 7 columns only `{station,depth,boc,date,crew,print,notes}`.
3. **Matching** — `_candidate_rankings_for_group_v2` ([main.py:11532](backend/main.py)) constrains candidate routes via the **hardcoded** `CURRENT_PACKET_PRINT_SHEET_INDEX` ([main.py:861-904](backend/main.py)) (print→streets→route_ids) + proximity/street/span scoring.
4. **Placement** — `_build_station_points_for_group` ([main.py:6587](backend/main.py)) maps each station onto **ONE** `matched_route.coords`; `_map_station_to_route_distance` ([main.py:6499](backend/main.py)) **clamps** `max(0, min(mapped, route_total_ft))` (no scaling, no multi-segment); `_build_redline_segments_for_group` emits polylines.
5. **Arbitration** — stacked Anti-Collapse V2 / Collision Window / Candidate Matrix / LAWNDALE passes.
6. **Isolated override** — `_apply_terminal_tail_placement_override` ([main.py:11650](backend/main.py), called :13235) re-renders exactly one source_file (bore_log7) post-rebuild, default-OFF.
7. **Output** — `STATE["station_points"]` + `STATE["redline_segments"]` → session store → map UI + `/api/match-review-queue`. Diagnostic shadow attaches at checkpoints J/K/L (`pdf_ap_route_shadow`, `terminus_type`, `drill_path_frame`), all default-OFF.

**Central structural finding:** the entire #14–#43 deterministic body (resolver, DrillPathFrame, extractor,
terminal-tail anchor, structure index) is a **disjoint shadow annex** — default-OFF, `scripts/`-only, zero
`backend/` imports of it (Agents 1+3 confirmed). Production placement still runs purely on the hardcoded
print index + single-route-clamp builders. Flag-OFF behavior is byte-identical (trust_ledger 34/30/0/0/5).

---

## 3. Proven-good components (PRESERVE)

| Component | file:line | Why trustworthy |
|---|---|---|
| `_build_route_catalog`, `_build_kmz_reference` | main.py:3105 / 3330 | Deterministic KMZ→geometry; fixture-tested; reused everywhere. (Fix the `<description>` drop — don't rewrite.) |
| `resolve_terminal_tail_route_for_ap` | pdf_ap_route_resolver.py:1014 | Pure; unique-or-abstain (None on 0/≥2); the bore_log7 win. |
| `build_drill_path_frame` / `detect_frame_overlaps` | pdf_ap_route_resolver.py | Correct proof-object abstraction; PROVEN/BLOCKED + named gap; abstains safely; surfaces `unproven_overlap` honestly. |
| `classify_terminus_type` | pdf_ap_route_resolver.py:1069 | Deterministic; anti-artifact (rejects AP *label* without a run terminus). |
| `build_backbone_corridor_chain` / `build_route_adjacency` | pdf_ap_route_resolver.py:791 / 562 | Can assemble multi-route chains (the bridge a V2 placement core needs) — GOOD but currently UNUSED by builders. |
| `_apply_terminal_tail_placement_override` | main.py:11650 | Isolated, default-OFF, single-source_file, byte-identical when off — the correct integration seam pattern. |
| PDF extractor primitives A/B/C + glyph-recon + clean-table | scripts/pdf_*.py | Multi-primitive corroboration + intersection trust gate that abstains on disagreement; **0 wrong-id verified** (§5). Algorithms are V2-grade; only the constants are overfit. |
| **bore_log7 → route_469** placement | shipped #14 (`20cb32f`) | The one fully-proven placement; whole-route, both ends anchored (AP-163 + SPLICE 46). |
| **9 confirmed endpoints** | `scripts/pdf_clean_endpoint_table.py` | precision 1.00 / recall 0.90 / wrong-id 0 — **reproduced** this audit (§5). *Caveat:* this is an **ensemble-tier** number (3 independent signals must agree); raw Primitive A alone mints wrong ids (8:308→110, 11:189→139) that Primitive B's geometry strips, and the same chain is **precision 0.60 across sheets 8–14** (boundary sheets 13–14). Honest, but the headline is the agreement-gate's result, not any single primitive's. |

---

## 4. Suspect / brittle components (REWRITE)

| Component | file:line | Defect |
|---|---|---|
| `CURRENT_PACKET_PRINT_SHEET_INDEX` | main.py:861-904 | **The load-bearing production matching prior is a hardcoded Brenham table** (print→street→route_ids). Zero generalization; not evidence-driven. #1 architectural debt. |
| `_candidate_rankings_for_group_v2` | main.py:11532 | Large multi-pass scorer depending on the hardcoded index + street hints; brittle. |
| `_map_station_to_route_distance` + `_build_station_points_for_group` | main.py:6499 / 6587 | **Single-route clamp** — no scaling, no chain-cumulative chainage, no physical anchor. Cannot represent sub-route or multi-segment placement. The concrete design ceiling on ">1 placeable" (§5). |
| Collision/anti-collapse stack | multiple named layers | Accretion reconciling the same overlap problem repeatedly — a symptom of a weak primary matcher; likely collapses once matching is anchor-based. |
| `_build_kmz_reference` `<description>` drop | main.py:3330 | Data-loss: discards AP#/Address HTML the structure side needs. Repair (extend), not rewrite. |
| Extractor *packaging + calibration* (not algorithms) | scripts/pdf_*.py (15+ files) | Script rot + **~12 hand-measured pixel constants tuned to Brenham DPI** (the load-bearing one: `AP_TERMINAL_ANCHOR_TOL=18px`, wedged between two specific Brenham measurements 6px/42px) + `PAGE_OFFSET=13` hardcoded (regressive vs the resolver's title-block sheet reader) + valid-AP set = the Brenham KMZ ids. Off-corpus failure mode is **abstain, not wrong-id** (verified) — so it degrades safely but won't transfer without scale-normalization. Consolidate + parameterize. |
| Global STATE substrate | main.py:498 / single `_SESSION_LOCK` / full-dict SQLite per request | Single module-global `STATE` + one lock + whole-dict JSON-to-SQLite on every request. Fine for single-tenant beta; **not a multi-tenant production substrate** (serialized engine, fat writes). Out of scope for the redline rewrite but flagged. |

---

## 5. Evidence that prior blockers are valid or invalid

**Re-audited, not accepted. The prior "missing data" verdict was partly an extraction failure and partly real
— and prior targets sometimes conflated the two. Corrected:**

- **Structure-side STA↔structure extraction = WAS bad-architecture, now FIXED (invalid as a permanent blocker).**
  The relationship was in the PDF vector/text layer all along; the linear text-order extractor missed it. The
  #26–#37 primitives extract it. Agent 3 independently **reproduced** the claim by running the chain:
  `pdf_run_endpoint_extractor.py selftest` → SELFTEST_OK; `pdf_ap_glyph_reconstruct.py selftest` → SELFTEST_OK;
  `pdf_clean_endpoint_table.py` → **9 confirmed, wrong-id 0**; `target37_validation.py` → ADDED only
  {(9,3810,155),(12,355,164),(13,245,158→review)}, REMOVED [], CHANGED-ID []. **precision 1.00 / recall 0.90 /
  wrong-id 0 is TRUE and reproducible** (measured vs the literal-quote-verified `BRENHAM_PH5_RUN_ENDPOINTS`).
- **bore→AP/structure + per-bore start = GENUINELY MISSING DATA (valid blocker).** Agent 2 dumped the raw
  bore xlsx (every cell/sheet/comment/hidden col/defined name across 71 workbooks incl. 13 pre-split originals):
  exactly 7 columns, **no start/launch/pit/entry/origin/AP/address/drive field anywhere** — confirmed NOT a
  reader bug. The 80-pg Fieldwire register holds `AP→.FS`/`AP→.WP` but **0 bore_log ids, 0 AP↔STA co-located
  lines**; the `.FS` pages themselves are absent (only referenced). KMZ flower pots are id-less (raw-XML
  re-verified). **The `bore_logN → structure/start` edge exists in no delivered artifact.**
- **bore_log57 = genuine geometric ambiguity, not a probe gap (valid blocker).** Terminus is uniquely AP-157
  (STA 413, route_465 sole tail within tol). But 413ft on the 741ft tail ending at AP-157 would START at
  offset ~329 = **open space** (nearest node ~35ft, no pit); the only ~413ft structure-to-structure segment
  (Flower Pot→Installer HH) doesn't reach AP-157. Two irreconcilable readings, no in-file discriminator
  (Agent 4 read `target41` closely; agrees no untried representation manufactures a start that isn't in the
  geometry).
- **"Only bore_log7 placeable" — PROVEN but SCOPED, and PREDOMINANTLY DESIGN-BOUND (key correction).**
  True for the new deterministic terminal-tail/anchor method; NOT "only bore_log7 is drawn" (production
  places 34/64 groups today via the hardcoded index+clamp, unproven-but-present, #19 flags them
  `unproven_overlap`). The new method proved exactly one (bore_log7) and abstains on the rest. **But Agent 4's
  architecture evidence overturns the framing that this ceiling is mostly data-bound — it is mostly
  DESIGN-bound**, three ways: (a) **single-route clamp** cannot REPRESENT a corridor-chain bore even though
  `build_backbone_corridor_chain` already proves route_480→479→475 is a deterministic 3024 ft simple chain —
  the largest blocked bucket is blocked by the geometry model, not the data; (b) **AP-terminus-only anchoring**
  — the only provable shape is "ends at an AP with a unique length-matched tail," which excludes most bores by
  construction; (c) **a tiny hand-transcribed endpoint table** — a bore can only "bind a confirmed endpoint"
  if its END is one of ~40 transcribed rows, a coverage artifact, not a property of the KMZ/PDF. The
  **genuinely data-bound residue is narrow**: the flower-pot drops (KMZ flower-pot nodes are all unnamed →
  no identity bridge, §6) and the per-bore *start* datum for multi-drive logs. bore_log57's block is real
  under the current conservative tolerances **and route-segment-enumeration** — but interior-structure
  anchoring (matching a bore's *intermediate* stations to named handholes/splices, not just its terminus to an
  AP) was NEVER tried, so "no method resolves bore_log57" is **not established** — only "no terminus-only
  method does." This is the single biggest correction to the prior #38–#42 narrative.

---

## 6. Missed-source audit: searched vs not searched

Agent 2 swept every channel to the raw-byte level. Result per channel:

| Channel | Searched? | Carries a bore→start/structure signal? |
|---|---|---|
| Original bore-log formatting (71 xlsx incl. originals) | YES (every cell/sheet/comment/hidden/defined-name) | **NO** — 7 columns only |
| Scanned/handwritten logs | N/A — none delivered (logs are digital xlsx) | — |
| PDF visual layout | YES (#26–#37; vector+text) | Structure endpoints YES (extractable); bore id **NO** |
| KMZ descriptions/folders/styles | YES (raw `<description>`/`<ExtendedData>`/`<Style>`) | Structure AP#/Address YES; per-flower-pot id / bore ref **NO** |
| Fieldwire/register (80-pg) | YES | `AP→.FS/.WP` YES; bore id / AP↔STA **NO**; `.FS` pages absent |
| Filenames / sheet labels | YES | print token only (→corridor) |
| Station math / print sequencing | YES (#22/#32) | corridor + endpoint; start **NO** |
| Neighboring bore chains (`notes` lineage) | YES | bore→bore ("split/continues from bore_logN") only — never bore→structure |
| Route topology (KMZ adjacency) | YES (#5/#28) | geometry; not bore identity |

**One genuinely un-mined seam found (correction to "nothing missed"):** the bore xlsx **`notes` lineage
column** carries, for a few logs, a **free-text street name** — `bore_log39: "CHERI LN"`, `bore_log71:
"LAWNDALE AVE & HUISACHE"`, `bore_log72: "LAWNDALE AVE"` — and the KMZ House/AP `<description>` tables carry
**full street Addresses**. That is a latent **street → KMZ-address geocode join** no prior target consumed.
It is weak (only ~3 bores carry a street; free-text; street≠unique-structure) and will not supply the
bore→AP edge for multi-drive logs, but it is a real corpus-internal signal worth a targeted probe before
asserting "only bore_log7." Everything else on the bore side is genuinely absent: raw-byte sweep of 71
workbooks (incl. 13 pre-split parents, e.g. bore_log57←bore_log24) found no hidden sheet/column/comment/
custom-XML/defined-name, no start/launch/pit/entry/origin/AP/drive field; the `.FS` decomposition pages are
absent (Fieldwire only *references* `FS` labels); KMZ flower pots are id-less (raw-XML re-verified). The
bore→drive edge for multi-corridor logs is information-theoretically absent, not hidden in a representation.

---

## 7. Rewrite recommendation

**PARTIAL REWRITE — promote the proven deterministic shadow core to replace the brittle production core;
add one new placement primitive (chain-cumulative chainage). NOT a full from-scratch V2; NOT surgical-only.**

- **NOT surgical-repair-only:** the production core (`CURRENT_PACKET_PRINT_SHEET_INDEX` + single-route clamp)
  is fundamentally Brenham-hardcoded and structurally cannot represent sub-route placement. Patching it
  perpetuates a non-generalizing engine. The owner's own goal (extract from files, don't hardcode/type)
  is incompatible with keeping the hardcoded index as the matching truth.
- **NOT full-V2-from-scratch:** the hard part is already built and proven — the DrillPathFrame proof object,
  the terminal-tail anchor, the extractor primitives (0 wrong-id), `build_backbone_corridor_chain`. Throwing
  them away to rebuild would discard the only verified deterministic assets. Full rewrite also risks the
  catastrophic-wrong-redline failure mode the product forbids.
- **PARTIAL REWRITE = the disjoint proven core becomes the production core**, behind default-OFF flags,
  validated to reproduce bore_log7 + the 34/30 trust ledger, plus a new builder that lifts the single-route
  clamp. This is the smallest change that removes the Brenham hardcode AND breaks the design ceiling while
  preserving every proven asset and the DO-NOT-WIDEN safety contract.

---

## 8. Proposed V2 architecture

A **structure-graph anchored placement engine** (replaces print-index-guess + station-clamp):

```
INGEST            KMZ + bore xlsx + PDF (unchanged parsers; FIX _build_kmz_reference to keep <description>)
   │
STRUCTURE INDEX   per-AP {lat/lon, .FS, tail route, station} — promote scripts/ap_structure_index.py
   │              (Target #25) into backend, packet-sourced (no Brenham hardcode)
   │
ENDPOINT EXTRACT  one parameterized module from scripts/pdf_* primitives A/B/C + glyph-recon +
   │              intersection trust gate. Output: confirmed run-endpoint table (STA→structure), abstain-on-doubt.
   │              Constants parameterized by sheet DPI; valid-AP set sourced from the packet KMZ.
   │
DERIVE PRINT→ROUTE  replace CURRENT_PACKET_PRINT_SHEET_INDEX with a DERIVED print→corridor map from the
   │              extracted endpoints + KMZ topology (the hardcode becomes a test oracle, not runtime truth).
   │
DRILL-PATH FRAME  per bore: build_drill_path_frame → PROVEN (unique terminus ∧ proof-grade segment ∧
   │              length-match ∧ direction) or BLOCKED(named gap). Already built; this is the decision core.
   │
PLACEMENT CORE    NEW builder: chain-cumulative chainage over build_backbone_corridor_chain segments +
   │              physical structure anchor + direction datum (replaces single-route clamp). Represents
   │              whole-route AND sub-route placement.
   │
OVERRIDE SEAM     isolated post-rebuild pass per source_file (the proven _apply_terminal_tail pattern),
   │              default-OFF flag per lane.
   │
OUTPUT            station_points + redline_segments (unchanged shape) + per-bore proof/abstain in _diag.
```

Invariants carried forward: abstain-on-doubt (wrong redline = catastrophic); flag-gated; flag-OFF
byte-identical; every abstention is a *named* extraction/acquisition target.

---

## 9. Migration plan (preserves bore_log7 + 9 endpoints)

Phased, each step default-OFF + reproduces the trust ledger before the next:

1. **Lock the baseline.** Snapshot trust_ledger 34/30/0/0/5 and the 9-endpoint table as regression oracles.
   Consolidate `scripts/pdf_*` into `backend/app/core/endpoint_extractor.py` (parameterized constants;
   packet-sourced AP set) **behind a default-OFF flag**; gate: byte-identical endpoint table + selftests.
2. **Promote the structure index** (`ap_structure_index.py` → backend), packet-sourced; gate: 9 endpoints →
   lat/lon unchanged.
3. **Derive print→route** from extracted endpoints; run it in SHADOW alongside `CURRENT_PACKET_PRINT_SHEET_INDEX`;
   gate: derived map == hardcoded map on Brenham (the hardcode demoted to oracle). Only after parity, flip the
   default.
4. **New chain-cumulative placement builder** behind a flag; gate: **reproduces bore_log7 → route_469 exactly**
   (same start/end lat/lon as `bore_log7_before_after.py`) AND the 34/30 ledger; whole-route case first.
5. **Sub-route placement** enabled only for bores with a proof-grade segment (DrillPathFrame PROVEN). Blocked
   bores stay abstained (DO-NOT-WIDEN). Before declaring bore_log57 unsolvable, try the two untried methods
   Agent 4 named — **interior-structure anchoring** (match the bore's intermediate stations to named
   handholes/splices, not just its terminus) and the **`notes` street→KMZ-address geocode** (§6) — these may
   add placements from the *same* files; only after they're exhausted is bore_log57 truly start-datum-blocked.
6. **Decommission** the collision stack incrementally as the anchor-based matcher removes the overlaps it
   existed to fix; each removal gated by the ledger.

Preservation guarantees: bore_log7 is a numbered regression gate at steps 4–6; the 9 endpoints are the gate at
steps 1–2; no step ships until flag-OFF is byte-identical and flag-ON reproduces the proven cases.

---

## 10. First implementation target after audit

**Consolidate the extractor into one parameterized backend module behind a default-OFF flag, gated to
byte-identically reproduce the 9-endpoint table + all selftests** (migration step 1). Rationale: it is the
lowest-risk, highest-leverage move — it turns the strongest proven asset (the 0-wrong-id extractor) from
rotting `scripts/` into a maintainable, packet-generalizable foundation without touching production placement,
and it is the prerequisite for steps 2–4. No placement behavior changes; pure packaging + parameterization
under a flag.

*(Note: this is a target proposal. No implementation is performed in this audit.)*

---

## 11. Risks and rollback plan

| Risk | Mitigation / rollback |
|---|---|
| Wrong redline (catastrophic) | Every phase default-OFF; abstain-on-doubt preserved; bore_log7 + 9-endpoint + 34/30 ledger are hard regression gates; flag-OFF byte-identical → instant rollback by flag. |
| Derived print→route diverges from hardcode on Brenham | Run in shadow first; require exact parity before demoting the hardcode; keep the hardcode as a fallback oracle, not deleted. |
| Extractor constants don't generalize to non-Brenham | Parameterize by DPI + packet AP set; conservative gates degrade to **low recall, not wrong-id** (Agent 3 verified the failure mode is abstain). |
| New builder regresses existing placements | Gate on the full trust ledger; whole-route case (bore_log7) before sub-route; incremental flag per lane. |
| Script rot causes false confidence | Replace evolutionary `scripts/` with one versioned module + fixture tests (step 1). |
| Owner expects all bores placed | **Honest framing (below):** the residual blocked bores are blocked by genuinely-absent source data, not code; the fix is a one-time data-acquisition, not engineering. |

**Rollback:** every change is flag-gated and flag-OFF byte-identical; reverting = flipping the flag off.
No production default changes until parity + reproduction gates pass.

---

## 12. Final verdict

**PARTIAL REWRITE.** The engine's placement ceiling is **predominantly bad-architecture, not missing data** —
and the prior #38–#42 "missing data / only bore_log7" narrative over-attributed to the data what is mostly a
design limit. The correct replacement core is already built in the shadow annex and has never been promoted.

- The **production core is brittle and should be replaced**: a hardcoded Brenham print→route table
  (`CURRENT_PACKET_PRINT_SHEET_INDEX`) + a single-route-clamp placement builder + a stack of hand-tuned
  magic-constant scorers/rescue ladders (`** 2.35`, `0.42/0.18`, four stacked location-mismatch rescues).
  This is demo-fitted, non-generalizing debt; the owner's "extract from files, don't hardcode" mandate
  requires removing it.
- The **deterministic shadow core is proven-good and should be promoted**: DrillPathFrame, the terminal-tail
  anchor, the extractor primitives (precision 1.00/recall 0.90/wrong-id 0 at the ensemble tier — reproduced
  this audit), the structure index, `build_backbone_corridor_chain`. V2-grade; only constants are
  Brenham-overfit, packaging is rotted.
- **The placement ceiling is mostly DESIGN-bound (corrected):** the single-route clamp cannot represent the
  corridor-chain that the shadow already proves deterministic; AP-terminus-only anchoring excludes most bores
  by construction; the endpoint table is a tiny hand transcription. Fixing the *model* (chain-cumulative
  chainage + interior-structure anchoring) is likely to place more than one bore from the **same delivered
  files** — this is the central, testable claim the next phase must validate, and it inverts the prior
  conclusion that new files are the only unlock.
- **The genuinely data-bound residue is narrow:** (a) unnamed KMZ flower-pot nodes (a KMZ-source defect, not
  a matching defect) and (b) the per-bore *start* datum for multi-drive bores like bore_log57 — and even (b)
  must first survive the two untried methods (interior-structure anchoring, `notes`→address geocode) before
  it's declared a hard acquisition need.
- **The structure-side extraction blocker is invalid going forward** — it was an extraction failure, now solved
  (reproduced). Honesty note: "precision 1.00" is an ensemble-agreement result, not a single-primitive one.

Recommended path: execute the §9 migration (start at §10) to promote the proven core to production behind flags,
preserving bore_log7 + the 9 endpoints + the 34/30 ledger as regression gates, DO-NOT-WIDEN throughout. **Before
any data-acquisition ask, run the design-bound unlocks (corridor-chain placement + interior-structure anchoring
+ `notes`→address geocode) to measure how many bores the SAME files actually place** — the prior "only bore_log7"
ceiling is not trustworthy until those are tried. Treat per-bore start-structure / `.FS` acquisition as the
*residual* need for what remains after, not the primary blocker.

---

### Appendix — audit provenance
- Agent 1 (engine flow): read `backend/main.py` (700-760, 861-904, 3105-3400, 5562, 6499-6720, 11532-11910,
  12000-12090, 13235, 7775-7820, 11650-11770) + `pdf_ap_route_resolver.py`.
- Agent 2 (missed-source): raw-byte sweep of 71 bore xlsx, 3 PDFs, KMZ raw XML, Fieldwire register, context JSON
  (temp probe created + deleted).
- Agent 3 (extractor): read 8 `scripts/pdf_*`/`target37` files + ran 4 selftests/validations via `venv`.
- Agent 4 (matching): read resolver placement/frame fns + `target39/41/42/43` resolvers.
- Agent 5 (rewrite/migration): orchestrator synthesis of 1–4 (this report).
- All read-only. No engine/backend/web/STATE/flag/production change. No placement performed.
