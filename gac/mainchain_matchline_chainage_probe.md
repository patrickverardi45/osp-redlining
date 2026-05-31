# Target #22 — Matchline-Equation Chainage Extraction Probe (bore_log16, bore_log43) — READ-ONLY

**Question:** does the existing Brenham source contain enough matchline/local-station
information to convert `absolute station → sheet/local station → corridor position +
direction` for the two `main_chain_absolute_stationing_no_anchor` logs?

**VERDICT: PARTIAL — the matchline-equation chainage graph is ALREADY EXTRACTED and
present, but it has a precisely-named missing edge: a *station↔geometry anchor* (a
KMZ-locatable named structure at an absolute station in the 4000–5950 ft range) plus a
direction datum. bore_log16/43 do NOT move closer to PROVEN — the missing edge is data
*absent from the files*, not un-extracted.**

> Read-only. No redline placed, no geometry moved, no flag, no engine/STATE change.
> Probe: `scripts/mainchain_matchline_chainage_probe.py` → `.out`. In-repo artifacts only.

---

## 1. The decisive correction to Target #21

Target #21 §5.1 named *"matchline-equation chainage extraction from the CAD/DWG plan"* as
the **load-bearing missing piece**. **That is wrong, and this probe proves it:** the
matchline-equation network is **already extracted** and lives in
[backend/app/core/brenham_plan_sheet_graph.py](backend/app/core/brenham_plan_sheet_graph.py)
(schema `brenham-plan-sheet-graph-1`):

- `_BOUNDARY_STA_FT` — the proven `MATCHLINE STA a+bb = SEE SHEET X` equations (the SAME
  station value extracted on both adjacent sheets): main chain **1625 → 2018 → 2411 →
  2671 → 3064 → 3393 ft** (sheets 3→9), plus Niebuhr/Glenda clusters.
- `_MATCHLINE_EDGES` — the `SEE SHEET X` corridor connectivity.
- `_SHEET_WINDOW_FT` — per-sheet extracted STA callout windows.

So the matchline equations are **NOT the blocker.** The real blocker is the one Target #21
listed as §5.2/§5.3 (a per-bore start-structure datum / an on-corridor stationed KMZ
reference) — and this probe shows *why* it is irreducible.

## 2. Extracted corridor graph (verbatim from the probe)

| corridor (connected component) | extent_ft |
|---|---|
| [2, 17, 20, 21] | (0, 3701) |
| **[3, 4, 5, 6, 7, 8, 9, 23, 24]** (main chain) | (0, **4401**) |
| **[10, 12, 13, 14]** | (0, **4533**) |
| [18, 22] | (0, 1222) |
| [25, 29] | (0, 1930) |
| [26, 27, 28] | (0, 2795) |

- **MAX extracted boundary STA = 3393 ft.** **MAX of ALL run-endpoint table stations =
  4533 ft.** **MAX *named-AP* station = 3810 ft** (AP-155, sheet 9).
- Sheet membership: 7/8/9 → main-chain corridor; **sheet 10 → a *separate* corridor
  {10,12,13,14}**; sheet 11 → isolated singleton. (So bore_log16's prints 8/9/10 straddle
  two independent chainage axes.)

## 3. Graph verdict on the two logs

| bore | prints | sta | graph status | note |
|---|---|---|---|---|
| **bore_log16** | 8,9,10 | 5100–5950 | **station_print_disjoint** | station range outside ALL sheet windows AND ALL corridor extents (max 4533); spans 2 corridors |
| **bore_log43** | 10 | 4000–5919 | within_corridor* | *only by low-end overlap: corridor extent (0,4533); the bore's upper half **4533–5919 (~1386 ft) is beyond the extracted chainage** |

Both `sta_max > max_boundary 3393`. bore_log43's `within_corridor` is a partial-overlap
artifact — its terminus (5919) still exceeds the corridor's extracted extent.

## 4. The load-bearing test — station↔geometry anchor (probe §C)

The matchline graph is **STATION-SPACE ONLY (zero lat/lon)** — by design (its docstring:
"the Brenham KMZ has zero station anchors"). The *only* bridge from an absolute station to
a KMZ position is a **named AP** in `BRENHAM_PH5_RUN_ENDPOINTS`.

- **C1 — self-validation on the proven anchor (bore_log7):** station **451 (sheet 10) →
  table row `(10, 451.0, "ap", 163)` → AP-163 → route_469.** Reproduced **True**. The
  station→named-structure→KMZ mechanism works exactly where bore_log7 was proven.
- **C2 — same mechanism on the main-chain ends:** bore_log16 end **5950 → NO named anchor
  within 25 ft**; bore_log43 end **5919 → NONE**. The mechanism finds nothing because no
  named, KMZ-locatable structure is stationed anywhere near 5919/5950 (the highest named
  AP is at 3810; the highest *anything* is an unnamed splice at 4533).

## 5. Exact missing relationship (named, and proven absent — not un-extracted)

A **station↔geometry anchor in the 4000–5950 ft range**: at least one KMZ-locatable named
structure (AP / identified splice) tied to a known absolute station on the main line,
**plus a direction datum**. With one such anchor + direction, the *already-extracted*
matchline graph would convert absolute chainage → corridor position. Without it, the high
chainage floats — the graph knows the equations but has nothing to pin them to lat/lon at
those stations.

This is distinct from the matchline equations (present) and from the DROP lane's
node-identity gap (Target #20). It is the same class of artifact Target #21 §5.2/§5.3
named; this probe confirms it is genuinely absent from the files, and that §5.1 (more
matchline extraction) would NOT help — those equations already exist and still top out at
3393/4533, far below the bores' 5919/5950 ends.

## 6. Did bore_log16/43 move closer to PROVEN?

**No.** They remain correctly **BLOCKED** (`main_chain_absolute_stationing_no_anchor`).
What changed is the *precision* of the blocker: it is **not** an extraction gap (the
matchline network is extracted) but a **data-absence gap** — no high-station anchor exists
in the provided PDF/KMZ/xlsx. DO-NOT-WIDEN intact: do not place these on the length-fitting
backbone without an anchor + direction.

## 7. Next blocker / next action

- **Acquire ONE high-station anchor** for the main line (4000–5950 ft): a named AP or an
  identified splice with a known absolute station that also exists as a KMZ node, plus a
  flow direction. Smallest viable forms: a stationed reference on the main-chain KMZ line,
  OR the `.FS` drive-decomposition sheet (also named absent in Targets #8/#20), OR a
  start-structure column in the bore xlsx.
- Until then bore_log16/43 abstain (interim safety state + this named target). The one
  proven placement lane remains **bore_log7 → route_469**.
- No code helper falls out cleanly: a shadow would abstain on 100% of inputs (no anchor to
  resolve), so none is shipped this target — consistent with the Target #20 outcome.

## 8b. Corpus-sweep hardening (continuation, `mainchain_anchor_corpus_sweep.py`)

To upgrade "anchor absent" from a *local* claim to a *corpus-wide* one, the two Brenham
PDFs NOT used by the matchline graph were swept for the exact missing edge — a `NN+NN`
station in **4000–5950 ft** co-located on a page with a named `AP-NNN` / `SPLICE`:

| PDF | pages | pages w/ high STA (4000–5950) | high-STA pages also naming AP/SPLICE |
|---|---|---|---|
| `BRENHAM PH5 - 18-02-2026.pdf` (3 extra plan sheets) | 4 | 0 | 0 |
| `BRENHAM_PHASE_5_New_report_…03-23.pdf` (Fieldwire punch-list) | 80 | 0 | 0 |

**ZERO co-location candidates.** No `.FS`/fiber-schematic/drive-decomposition file exists
anywhere in the raw intake (`find` over the whole `TrueLine-Wiki` tree). So the
station↔geometry anchor is **absent across ALL provided Brenham sources** (3 PDFs + KMZ),
confirming this is a **data-absence** block, not an extraction gap. Verdict unchanged
(PARTIAL graph / BLOCKED logs), now corpus-hardened.

## 8. Files read
- [backend/app/core/brenham_plan_sheet_graph.py](backend/app/core/brenham_plan_sheet_graph.py)
  (matchline network — read, not changed).
- `BRENHAM_PH5_RUN_ENDPOINTS` in
  [backend/app/core/pdf_ap_route_resolver.py](backend/app/core/pdf_ap_route_resolver.py:989)
  (station→structure table — read, not changed).
- `gac/mainchain_high_station_adjudication.md` (Target #21 — the bore facts cited verbatim).
- Probe: `scripts/mainchain_matchline_chainage_probe.py` → `scripts/mainchain_matchline_chainage_probe.out`.
