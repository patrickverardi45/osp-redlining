# Target #19 — DrillPathFrame Review of the route_480 Bucket (READ-ONLY)

Ran the shipped Target #18 layer (`build_drill_path_frame` + `detect_frame_overlaps`) over all
14 route_480-bucket bore logs on the real fixture KMZ (md5-identical to the Brenham design KMZ).
**No placement, no flag flip, no STATE/engine change.** Probe: `scripts/drill_frame_bucket_review.py`.

## 1. Frame table (14 logs)

| source_file | terminus_class | proof | conf | route / anchor | abstain_reason / legacy |
|---|---|---|---|---|---|
| **bore_log7** | backbone_ap_bore | **PROVEN** | high | **route_469** @ AP-163, gap 0.51 ft | legacy=route_477 **CONFLICT** |
| bore_log5 | flower_pot_drop | BLOCKED | med | flower_pot (unnamed) | flowerpot_node_identity |
| bore_log30 | flower_pot_drop | BLOCKED | med | flower_pot (unnamed) | flowerpot_node_identity |
| bore_log48 | flower_pot_drop | BLOCKED | med | flower_pot (unnamed) | flowerpot_node_identity |
| bore_log50 | flower_pot_drop | BLOCKED | med | flower_pot (unnamed) | flowerpot_node_identity |
| bore_log65 | flower_pot_drop | BLOCKED | med | flower_pot (unnamed) | flowerpot_node_identity |
| bore_log16 | main_chain_high_station | BLOCKED | med | — | main_chain_absolute_stationing_no_anchor |
| bore_log43 | main_chain_high_station | BLOCKED | med | — | main_chain_absolute_stationing_no_anchor |
| bore_log57 | multi_drive_unknown | BLOCKED | low | — | multi_drive_terminus_ambiguous |
| bore_log29 | unknown_insufficient | BLOCKED | low | — | no_run_terminus_match |
| bore_log31 | unknown_insufficient | BLOCKED | low | — | no_run_terminus_match |
| bore_log46 | unknown_insufficient | BLOCKED | low | — | no_run_terminus_match |
| bore_log47 | unknown_insufficient | BLOCKED | low | — | no_run_terminus_match |
| bore_log58 | unknown_insufficient | BLOCKED | low | — | no_run_terminus_match |

## 2. Grouped result

- **PROVEN (1):** bore_log7 → route_469 (terminal tail to AP-163). The ONLY frame with a unique
  KMZ anchor + length-matched route. Already shipped behind `TRUELINE_TERMINAL_TAIL_PLACEMENT`
  (Target #14, default-OFF) and source-adjudicated (Target #16 / `d4a7a2f`).
- **BLOCKED — flowerpot_node_identity (5):** bore_log5/30/48/50/65. PDF proves a flower-pot
  terminus; all 158 KMZ flower-pot nodes are unnamed and the bore logs carry no structure key →
  no station→node bridge.
- **BLOCKED — main_chain_absolute_stationing_no_anchor (2):** bore_log16/43. Stations are absolute
  main-chain (4000–5950), not a local 0+00 drive; no single AP/pot terminus to anchor on.
- **BLOCKED — multi_drive_terminus_ambiguous (1):** bore_log57. End station matches both an AP and a
  matchline run-end → not a single bindable terminus.
- **BLOCKED — no_run_terminus_match (5):** bore_log29/31/46/47/58. Continuous multi-drive bores whose
  end station hits no DIR.BORE run terminus within tolerance.

## 3. Overlap diagnostic (occupied = legacy print-index route, all flags OFF)

`detect_frame_overlaps` returns **58 pairs, ALL `unproven_overlap`** — and that count is *exactly*
right, audited two ways:
- Occupied routes today: **route_477 holds 11 logs**, **route_478 holds 3 logs** (the print-index maps
  print 10→route_477, print 8→route_478 etc.). C(11,2)+C(3,2) = 55+3 = **58**. Matches.
- Isolated unit check: 5 synthetic logs on one route → 10 = C(5,2). Matches.

**Every one of the 58 is `not_owned_by_frame` for BOTH logs** — i.e. the legacy print-index is stacking
many distinct bores onto the same one or two corridors, and not a single one of those occupancies is
proven by the bore's own DrillPathFrame. The lone proven frame (bore_log7→route_469) is *not* route_477,
so its current route_477 occupancy is itself flagged. **This is the quantified statement of the
bad-overlap problem: 13 of 14 bucket logs have no proof for where they are drawn, and the print index
collapses them onto shared geometry.** (Observation only — nothing was changed.)

## 4. Next redline target + why

**Decision: B — implement the `flowerpot_node_identity` extraction (the DROP lane), NOT another
one-log placement.**

Reasoning against the other options:
- **A (another one-log proof slice):** there is no second PROVEN frame to ship. bore_log7 is the only
  one, and it is already shipped + adjudicated. Nothing to add.
- **C (main_chain_high_station, bore_log16/43):** blocked on absolute-stationing anchoring — a harder,
  separate problem (needs a chain-cumulative chainage datum), and only 2 logs.
- **D (bad abstraction):** none exposed. The frame layer behaved correctly across all 14; the overlap
  count reconciles exactly; no legacy code is wrong here — the print-index stacking is a *symptom* the
  frame layer correctly flags, not a bug to rewrite under this target.
- **B (DROP lane):** the **largest single blocked group (5 logs)** AND the one whose missing relationship
  is **exactly named and smallest**: a flower-pot/drop **identity key**. This is the highest-leverage,
  most-deterministic next step.

## 5. Exact missing relationship (the named extraction target)

A **drop-identity key** binding each drop bore to ONE specific KMZ drop structure. Smallest viable form,
in priority:
1. **Parent-AP / address tag on KMZ flower-pot nodes (or on Vacant Pipe / House Drop routes).** The KMZ
   already names APs numerically; the drop layer is the unnamed gap. A tag like "flower pot off AP-163"
   (or the served street address, which the PDF *does* print per drop, e.g. "1009 E TOM GREEN ST") would
   let a drop bore on sheet N bind to the unique pot/route under its AP.
2. **`.FS` Fiber-Schematic / drive-decomposition sheet** (named absent in Targets #8–#10) mapping each
   bore's station sub-ranges → drive/structure.
3. **A drop-id / address column in the bore-log xlsx** (currently absent).

**Until a key exists, the 5 drops correctly abstain.** DO-NOT-WIDEN: do not place them on a guessed pot
or on the route_477/route_480 backbone. The next *coding* step would be a default-OFF SHADOW that, given
key (1), resolves the unique drop route per drop bore — same pure/read-only pattern as Target #18, proven
before any placement.

## 6. Files read
- `scripts/drill_frame_bucket_review.py` → `scripts/drill_frame_bucket_review.out` (the 14-frame run + 58-overlap dump).
- Engine (no change): `build_drill_path_frame`, `extract_drill_path_frames`, `detect_frame_overlaps`,
  `build_route_adjacency`, `CURRENT_PACKET_PRINT_SHEET_INDEX` (print 10→route_477).
- Overlap count audited against C(11,2)+C(3,2)=58 and an isolated C(5,2)=10 unit check.

## 7. Recommendation (stop point)
Proceed to **Target #20 = DROP-lane drop-identity SHADOW** (default-OFF, read-only), gated on obtaining
key (1) — a parent-AP/address tag for KMZ flower-pot nodes or drop routes. No placement until that key
exists and a frame proves the unique drop route, exactly as bore_log7 was proven. No engine change this
target.
