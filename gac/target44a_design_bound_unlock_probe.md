# Target #44a — Design-Bound-Unlock Probe (READ-ONLY)

**Objective:** prove or disprove the rewrite audit's central claim that the "1 bore placeable"
ceiling is caused mainly by the engine MODEL (single-route pick + station clamp + AP-terminus-only
anchoring), not by missing source data. Method: run **three model-fix unlock paths** against every
currently-blocked bore, **delivered corpus only**, bore_log7 as control.

**VERDICT: the audit's "mostly design-bound" claim is REFUTED for *deterministic placement*. The
ceiling is DATA-BOUND.** Fixing the model adds **0 new placeable bores**. Two bores gain *partial*
corridor evidence (a real, previously-unused signal) but neither becomes placeable. Control
bore_log7 stayed PLACEABLE (hard gate held).

> Read-only. No redline placed, no geometry moved, no flag wired, no production/STATE change, no
> office override, no missing-file request. Probe: `scripts/target44a_design_bound_unlock_probe.py`
> → `.json` / `.out`. Reuses shipped helpers (`build_backbone_corridor_chain`,
> `resolve_terminal_tail_route_for_ap`, route catalog/KMZ builders, confirmed endpoint table);
> no new matching math. Self-test: control placeable ✓.

---

## Result table (17 bores tested)

| bore | end_ap | smax | path1 interior | path2 street→corridor | path3 corridor-chain | verdict |
|---|---|---|---|---|---|---|
| **bore_log7** (CONTROL) | 163 | 451 | none | — | route_469 tail 459≈451 | **PLACEABLE_BY_NEW_MODEL** |
| bore_log71 | — | 695 | none | **LAWNDALE AVE → route_477 (unique, 17 addr nodes)** | no end-AP | **PARTIAL_EVIDENCE_ONLY** |
| bore_log72 | — | 1000 | none | **LAWNDALE AVE → route_477 (unique)** | no end-AP | **PARTIAL_EVIDENCE_ONLY** |
| bore_log39 | — | 1441 | none | CHERI LN → not in KMZ | no end-AP | STILL_BLOCKED |
| bore_log57 | 157 | 413 | none | — | route_465 tail 741≠413 | STILL_BLOCKED |
| bore_log5 | — | 500 | none | — | no end-AP | STILL_BLOCKED |
| bore_log30 | — | 500 | none | — | no end-AP | STILL_BLOCKED |
| bore_log48 | — | 509 | none | — | no end-AP | STILL_BLOCKED |
| bore_log50 | — | 514 | none | — | no end-AP | STILL_BLOCKED |
| bore_log65 | — | 650 | none | — | no end-AP | STILL_BLOCKED |
| bore_log16 | — | 5950 | none | — | no end-AP | STILL_BLOCKED |
| bore_log43 | — | 5919 | none | — | no end-AP | STILL_BLOCKED |
| bore_log29 | — | 415 | none | — | no end-AP | STILL_BLOCKED |
| bore_log31 | — | 260 | none | — | no end-AP | STILL_BLOCKED |
| bore_log46 | — | 534 | none | — | no end-AP | STILL_BLOCKED |
| bore_log47 | — | 494 | none | — | no end-AP | STILL_BLOCKED |
| bore_log58 | — | 256 | none | — | no end-AP | STILL_BLOCKED |

**PLACEABLE_BY_NEW_MODEL = {bore_log7} only. NEW beyond control = NONE. PARTIAL = {bore_log71, bore_log72}.
STILL_BLOCKED = 14.**

---

## Path-by-path findings

### PATH 1 — interior-structure anchoring → **NO signal exists on the bore side**
Tested whether a bore's interior rows carry an anchor beyond the terminus: (a) a per-row structure
field (none — confirmed again: bore xlsx is 7 columns), (b) an interior **pit signature** (a local
depth minimum at an interior station = an entry/exit pothole) that aligns to a structure offset on
the candidate route. **Result: 0/17 bores have any interior depth-minimum signal** (`no_interior_signal`
for every bore, including bore_log57). The bore depth column is too uniform/sparse to mark interior
pits, and there is no per-row structure column. So interior-structure anchoring — the audit's most
promising untried method for bore_log57 — **has no input data in the delivered files**. This is the
single biggest correction to the audit: the method isn't blocked by the engine, it's blocked by the
absence of interior structure/pit data in the bore logs.

### PATH 2 — notes street-name → KMZ address → **REAL but only corridor-level (PARTIAL)**
The un-mined seam the audit flagged is genuine: **bore_log71 and bore_log72 both note "LAWNDALE AVE",
which matches "Lawndale Avenue" in the KMZ (17 address nodes), and those nodes sit within 60 ft of
exactly one underground-cable corridor — route_477 (unique).** This is a deterministic *corridor*
binding from delivered files that no prior target used. **But it does not make them placeable:** a
street pins *which corridor*, not *where along it* the bore starts/ends or its direction — bore_log71
(695 ft) and bore_log72 (1000 ft) could sit anywhere on route_477. bore_log39's "CHERI LN" is **not a
KMZ street** (closest is none of the 29 KMZ streets) → no corridor. Verdict: PARTIAL_EVIDENCE_ONLY for
71/72 (corridor known, position unknown); no placement.

### PATH 3 — corridor-chain geometry (drop one-route+clamp) → **does NOT lift the ceiling**
Tested whether blocked bores map to a multi-route corridor chain long enough to hold them. **Only bores
whose END binds a confirmed AP endpoint even reach this path** (bore_log7, bore_log57) — the other 12
route_480 bores have `no_end_ap_anchor` (their END station is a flower-pot/matchline, not a confirmed AP,
re-confirming #20/#23). For the two that do bind: bore_log7's tail route_469 (459 ft) ≈ bore (451 ft) →
whole-route placeable (control, expected). bore_log57's tail route_465 is 741 ft vs bore 413 ft → the
chain/route does not length-match; corridor-chaining cannot pick which 413 ft sub-path without the start
datum #41 already named. **So the corridor-chain model change places nothing new** — it correctly
represents bore_log7 (already placeable) and cannot resolve bore_log57's sub-segment ambiguity.

---

## Why this refutes the audit's "design-bound" framing

The audit reasoned that the single-route clamp and AP-terminus-only anchoring were *suppressing*
placeable bores. This probe lifted all three model restrictions and measured the result: **the bores
do not become placeable, because the bore SIDE lacks the inputs each unlocked method needs** —
- corridor-chain needs an END anchor → 12/14 blocked bores have no confirmed-AP END;
- interior anchoring needs interior structure/pit data → 0 bores have it;
- street→corridor gives only a corridor, never a position → at best PARTIAL.

The one genuinely data-bound exception the audit conceded (flower-pot drops, unnamed nodes) is joined by
the rest: the missing edge is uniformly a **per-bore start/terminus/position datum**, absent from every
delivered file. The model fixes are still *worth doing* (they're prerequisites that turn the data into
placements once it arrives), but they are **not sufficient** — the prior #38–#42 "only bore_log7 from
delivered files" conclusion stands, now re-confirmed against the model-fix hypothesis itself.

**Honest correction to the audit (gac/redline_engine_rewrite_audit.md §5/§12):** the claim "fixing the
model is likely to place more than one bore from the same files" is **false as tested**. The ceiling is
data-bound; the rewrite case rests on *generalization + maintainability + removing the Brenham hardcode*,
**not** on unlocking more Brenham placements. Section "first target #44a" did its job: it cheaply
prevented a rewrite justified on a wrong premise.

---

## Promotability of the one new signal (PATH 2 corridor binding)

The street→corridor join (bore_log71/72 → route_477) is **deterministic and promotable as
corridor-level evidence** — e.g. to constrain candidate routes or flag a mismatch — but **NOT as
placement** (no position/direction). It is the same "narrows, doesn't place" tier as the existing
DrillPathFrame BLOCKED evidence. If promoted later it must stay observation-only until a start datum
arrives; placing on it would be guessing a position along a 2758 ft corridor = wrong-redline risk.

---

## Verdicts (deliverable format)

- **PLACEABLE_BY_NEW_MODEL:** bore_log7 (control only).
- **PARTIAL_EVIDENCE_ONLY:** bore_log71, bore_log72 (street→route_477 corridor; position unpinned).
- **STILL_BLOCKED:** bore_log39, 5, 30, 48, 50, 65, 16, 43, 57, 29, 31, 46, 47, 58 (14).

Hard gates: bore_log7 PLACEABLE ✓; no production/flag/STATE/geometry change ✓; no manual placement ✓;
all three paths tested before any "data-bound" conclusion ✓.

## Next
- The rewrite (audit §9) remains justified on **generalization/maintainability/de-hardcoding**, not on
  unlocking Brenham placements — proceed to #44b (consolidate extractor behind a default-OFF flag) when
  authorized.
- The street→corridor seam is a candidate **corridor-evidence** shadow (not placement). Low priority.
- The deterministic-placement ceiling from delivered files stays {bore_log7}; the residual unlock is a
  per-bore start/terminus datum (`.FS` or a start-structure field) — a source acquisition, now confirmed
  necessary even after model fixes.

## Files read
- `scripts/target44a_design_bound_unlock_probe.py` → `.json`/`.out` (the probe + full per-bore evidence).
- Reused: `pdf_clean_endpoint_table.json` (9 confirmed endpoints), `target41`/`target42` (prior segment
  logic), `ap_structure_index` (structure-side facts), KMZ raw `<description>` addresses, route catalog.
- Engine (no change): `build_backbone_corridor_chain`, `resolve_terminal_tail_route_for_ap`,
  `_build_route_catalog`, `_build_kmz_reference`.
