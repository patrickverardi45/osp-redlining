# Target #21 — Main-Chain High-Station Adjudication (bore_log16, bore_log43) — READ-ONLY

**Question:** do PDF/KMZ/bore-log files contain the ABSOLUTE-STATIONING ANCHOR needed to place
these two main-chain high-station logs, or is a specific artifact missing?

**VERDICT: BLOCKED for both** (`main_chain_absolute_stationing_no_anchor`). Unlike bore_log7, the
occupied backbones are length-plausible, so this is **not** a route-class conflict — it is a genuine
**no-anchor** block: nothing in the files pins WHERE along the corridor (and in which direction) the
absolute chainage 4000–5950 sits. The occupancy is therefore *unproven*, not provably wrong.

> Read-only. No redline placed, no geometry moved, no flag flipped, no engine/STATE change.
> All numbers below are from `scripts/mainchain_adjudication_probe.py` → `.out` (fixture KMZ,
> md5-identical to design KMZ) — verbatim, not from memory.

---

## 1. Bore-log facts (verbatim from the probe)

| field | bore_log16 | bore_log43 |
|---|---|---|
| print tokens | **8, 9, 10** | **10** |
| station min/max | **5100 → 5950** (span 850) | **4000 → 5919** (span 1919; only 8 rows, sparse) |
| rows | 19 | 8 (4000,4050,4100,4150,4250,4300,4586,5919) |
| crew / date | tx1-1 / 2025-12-11 | tx1-1 / 2025-12-12 |
| notes | "59+19 … bottom-most row … endpoint between 59+00 and 59+50" | "Segment A split from bore_log17 … 59+19 may continue prior day's bore_log16 work … Print 18 covers col2 0+00..3+25" |
| DrillPathFrame | BLOCKED · main_chain_high_station · main_chain_absolute_stationing_no_anchor | same |
| engine occupies today (print-index) | **route_478** (+route_477) | **route_477** |

The notes confirm these are **two segments of one continuous main-chain bore** recorded in
**absolute chainage** (bore_log43's 59+19 "continues prior day's bore_log16"; bore_log16's 59+19 is
its endpoint). Crew tx1-1, consecutive days.

---

## 2. PDF plan evidence

- **The print sheets ARE covered** by the run-endpoint table (table sheets = 8–14; bore_log16 prints
  8/9/10, bore_log43 prints 10). So sheet coverage is **not** the blocker.
- **The bore stations exceed every catalogued run terminus.** Table station range = **136 → 4533 ft**;
  bore ends are **5950** and **5919** — both **ABOVE 4533**. No run terminus within ±25 ft of either
  end. The deterministic anchor that proved bore_log7 (a `DIR.BORE` run ending at an AP terminal) has
  **no entry** at these stations.
- **Stationing frames differ:** the bores use continuous **absolute chainage** (thousands); the plan
  is **per-drive local `0+00`** stitched by **matchline equations** (the table itself carries matchline
  markers, e.g. sheet 8 @ 3393, sheet 9 @ 3890). No **global chainage origin** has been extracted to
  convert absolute station → (sheet, local station) → lat/lon.

## 3. KMZ evidence

- The occupied backbones are **real, length-plausible** underground-cable lines (not 131 ft fragments):
  **route_477 = 2758.9 ft**, **route_478 = 1224.5 ft**. bore_log16 span 850 ft fits route_478;
  bore_log43 span 1919 ft fits route_477 lengthwise. **So length is not the blocker** (this is the key
  difference from bore_log7's route_469-vs-route_477 case).
- **But neither occupancy is anchorable or proven:** `build_backbone_corridor_chain` returns
  **`no_connected_backbone_chain`** for both route_477 and route_478 (each is a standalone underground
  segment, not extended by a shared-vertex chain), and there is **no AP / splice / stationed node at the
  bore's end station** to pin position + direction along the corridor.
- No KMZ structure supplies an absolute-chainage tick the bore's 4000–5950 frame could anchor to.

---

## 4. Verdict per bore

| bore | verdict | why |
|---|---|---|
| **bore_log16** | **BLOCKED** (no-anchor) | sheets in table but end 5950 > table max 4533 → no run terminus; absolute↔local frame unconverted; no end-structure to pin position/direction. Occupies route_478 (length-fits, but unproven). |
| **bore_log43** | **BLOCKED** (no-anchor) | end 5919 > 4533 → no run terminus; same frame gap; sparse/NEEDS-REVIEW rows. Occupies route_477 (length-fits, but unproven). |

**Three independent gates, any one sufficient:**
1. **No run-terminus anchor** — bore stations (5919/5950) exceed the table max (4533); no terminus there.
2. **Absolute↔local frame** — bore = continuous absolute chainage; plan = per-drive local 0+00 +
   matchline equations; no extracted conversion.
3. **No position/direction datum** — corridor length fits but nothing pins which end is the start or
   where along route_477/478 the bore sits.

Not a route-class CONFLICT (the bore_log7 case). The occupied backbone is plausibly correct by length;
it is simply **unproven** — so the DrillPathFrame overlap rule correctly flags bore_log16 (with
bore_log57/58 on route_478) and bore_log43 (with the route_477 group) as `unproven_overlap`.

---

## 5. Exact missing relationship (named)

An **absolute-station → corridor-position + direction datum** for the occupied main line. Any ONE:

1. **Matchline-equation chainage extraction** from the CAD/DWG plan (the `STA a = 0+00` equation
   network — named un-extracted in Target #8). Converts absolute chainage → plan/corridor position; the
   load-bearing piece.
2. **A per-bore start-structure + direction datum** (e.g. "bore_log16 Segment B starts at splice/AP X
   heading toward Y") pinning one end to a named KMZ node — collapses the absolute frame to a known
   point. Absent from the bore xlsx (only station/depth/boc/date/crew/print/notes).
3. **An on-corridor stationed reference in the KMZ** (a chainage tick along route_477/478) — absent.

Distinct from the DROP lane's gap: DROP needed *node identity* (which flower pot); main-chain needs
*absolute-chainage geolocation + direction* along a known-length corridor. A flower-pot SCID would not
help here; a matchline-equation extraction would.

---

## 6. Legacy assumption (deliverable 5)

The print-index occupancy here is **length-plausible** (route_477 2758 ft, route_478 1224 ft vs spans
1919/850), so this is **not** the egregious bore_log7 case (a 131 ft sliver / wrong route class). The
real, named issue is softer: **the print-index asserts a corridor without proving anchor/position/
direction**, so the DrillPathFrame layer reports the occupancy as `unproven_overlap` (shared with other
bores on the same backbone). Named, not fixed — resolving it needs the §5 datum + re-authorization.

*(Process note: an earlier draft of this file mis-stated these logs as print 7/15 → route_476 / E Stone
St with a branched corridor. That was wrong — corrected here against the probe output. Target #19's
overlap stats, including bore_log16 on route_478 and the 58-pair total, are CORRECT and were left
intact.)*

---

## 7. Next redline action
- **Acquire the §5.1 matchline-equation chainage extraction** (or §5.2 per-bore start-structure datum),
  then a main-chain placement could anchor absolute station → corridor position + direction — proven
  before any placement, as bore_log7 was.
- Until then bore_log16/43 **abstain** (correct). The one proven placement lane remains
  **bore_log7 → route_469**. DROP lane stays blocked on its own (different) key.
- **Do not** place main-chain logs without the anchor datum. DO-NOT-WIDEN intact.

## 8. Files read
- `scripts/mainchain_adjudication_probe.py` → `.out` (bore facts, frames, table coverage, chains — all
  numbers above are verbatim).
- Engine (no change): `CURRENT_PACKET_PRINT_SHEET_INDEX` (8/9/10→route_478+477; 10→route_477),
  `BRENHAM_PH5_RUN_ENDPOINTS` (sheets 8–14, max station 4533), `build_backbone_corridor_chain`
  (route_477/478 → no_connected_backbone_chain), `build_drill_path_frame`.
