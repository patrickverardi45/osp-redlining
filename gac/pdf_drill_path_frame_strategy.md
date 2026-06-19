# Target #17 — PDF-Defined DrillPathFrame: Extraction Strategy (DESIGN NOTE)

**Status:** design only. No code, no flag, no placement, nothing moved. This note defines the next
engine abstraction and names the next coding target (Target #18). It does **not** implement it.

## 0. Doctrine

Redlines go where the **engineering plans** say they go. The engine must *extract* the
PDF ↔ KMZ ↔ bore-log relationship and prove it, rather than (a) ask a human to guess, or
(b) blindly trust the legacy `CURRENT_PACKET_PRINT_SHEET_INDEX` route_id rules.

Two source-proven facts from this session motivate the abstraction:

- **bore_log7 → route_469 (PROVEN).** PDF sheet 10 `STA 0+00→4+51 DIR. BORE (451') … E/W PORT
  TERMINAL TAIL … TERMINAL 6 PORT HH AP-163`; bore_log7 has print 10, station max 451; KMZ AP-163 is a
  *numerically named* node and route_469 is the unique length-matched Terminal Tail ending 0.5 ft from
  it. route_477 was **engine policy** (print-index + backbone-only rule), not source evidence.
  (`gac/bore_log7_route_adjudication.md`.)
- **DROP lane (bore_log5/30/48/50/65) → BLOCKED.** PDF proves a flower-pot terminus for each, but the
  KMZ's 158 flower-pot nodes are all unnamed → no station→node bridge → not bindable.
  (`gac/drop_lane_source_adjudication.md`.)

The difference between PROVEN and BLOCKED is entirely about whether a **unique anchor identity** exists.
A `DrillPathFrame` makes that the explicit, testable unit of work.

## 1. The DrillPathFrame model

One frame per bore-log placement question. A pure value object (dict/dataclass), assembled read-only
from the three sources already loaded by the rebuild. Fields:

| field | meaning | source |
|---|---|---|
| `source_file` | e.g. `bore_log7` | bore-log xlsx |
| `print_tokens` / `sheets` | e.g. `["10"]` → sheet 10 | xlsx `print` col |
| `station_min_ft` / `station_max_ft` | e.g. 55 → 451 | xlsx stations |
| `run_text` | literal PDF run, e.g. `STA 0+00→4+51 DIR. BORE (451')` | PDF / `BRENHAM_PH5_RUN_ENDPOINTS` |
| `structure_type` | `ap` · `terminal_tail` · `flower_pot` · `splice` · `handhole` · `matchline` · `main_chain` · `unknown` | PDF run→endpoint table |
| `terminus_class` | reuse `classify_terminus_type` → `backbone_ap_bore` / `flower_pot_drop` / `main_chain_high_station` / `multi_drive_unknown` / `unknown_insufficient` | resolver |
| `start_anchor` / `end_anchor` | `{kind, id, lat, lon}` when extractable (e.g. end = AP-163 node) | KMZ node identity |
| `kmz_geometry` | `{route_id, length_ft, endpoint_gap_ft}` or a route chain, or `null` | KMZ catalog |
| `station_direction` | which station maps to which anchor end (e.g. station 451 = AP-163 end) | run label + anchor |
| `proof` | `PROVEN` / `BLOCKED` / `RECLASSIFY` | derived |
| `confidence` | `high` / `med` / `low` | derived |
| `abstain_reason` | exact named gap when not `PROVEN` (e.g. `flowerpot_node_identity`) | derived |
| `evidence` | the literal quotes / ids / distances behind the verdict | all three |

A frame is **bindable (PROVEN)** iff: (1) the PDF gives a unique run terminus at the bore's end
station, (2) that terminus has a **unique KMZ node identity**, and (3) a unique length-matched KMZ route
attaches to it. Anything short of all three → `BLOCKED` with a named `abstain_reason`.

## 2. Worked example — PROVEN frame (bore_log7)

```
DrillPathFrame(
  source_file      = "bore_log7",
  sheets           = [10],
  station_min_ft   = 55,   station_max_ft = 451,
  run_text         = "STA 0+00 TO 4+51 DIR. BORE (451') — E/W PORT TERMINAL TAIL → TERMINAL 6 PORT HH AP-163",
  structure_type   = "terminal_tail",
  terminus_class   = "backbone_ap_bore",          # classify_terminus_type, high-confidence
  start_anchor     = { kind:"open", id:null,   lat:30.1594514, lon:-96.3844975 },  # station 55
  end_anchor       = { kind:"ap",   id:"163",  lat:30.1591628, lon:-96.3857298 },  # station 451 == AP-163 node
  kmz_geometry     = { route_id:"route_469", folder:"Connections / Terminal Tail",
                       length_ft:459.2, endpoint_gap_ft:0.5 },
  station_direction= "station_max(451)=end_anchor(AP-163); stations increase toward AP-163",
  proof            = "PROVEN",  confidence = "high",  abstain_reason = null,
  evidence         = { pdf:"sheet10 451' unique run -> AP-163", kmz:"AP-163 named node; route_469 unique len-match",
                       legacy_conflict:"print-index says route_477 (E Tom Green backbone), >=363 ft from AP-163 — refuted" }
)
```

This is exactly what `resolve_terminal_tail_route_for_ap` + `classify_terminus_type` already compute; the
frame is the **named container** that records *why*, plus the legacy-conflict note.

## 3. Worked example — BLOCKED frame pattern (DROP lane)

```
DrillPathFrame(
  source_file      = "bore_log50",
  sheets           = [10,11,12],
  station_min_ft   = 0,   station_max_ft = 514,
  run_text         = "… STA ~5+14 → 11\"x11\"x12\" FLOWER POT (VACANT HDPE FIBER DROP)",
  structure_type   = "flower_pot",
  terminus_class   = "flower_pot_drop",           # classify_terminus_type, high-confidence
  start_anchor     = null,
  end_anchor       = { kind:"flower_pot", id:null, lat:null, lon:null },   # <-- the gap
  kmz_geometry     = null,
  station_direction= null,
  proof            = "BLOCKED",  confidence = "med",
  abstain_reason   = "flowerpot_node_identity",   # PDF proves a flower-pot terminus, but all 158 KMZ
                                                  # flower pots are UNNAMED -> cannot select WHICH pot /
                                                  # which of 480 drop routes; bore log carries no key
  evidence         = { pdf:"sheet11 514 + sheet12 507/510 flower_pot (non-unique on PDF too)",
                       kmz:"158 unnamed Flower Pot nodes; 480 Vacant Pipe/House Drop routes, none station-keyed" }
)
```

Same shape for bore_log5/30/48/50 (`abstain_reason=flowerpot_node_identity`, several also
`flowerpot_terminus_nonunique_on_pdf`). bore_log65 is PDF-unique (sheet 9 @ 650) but still
`flowerpot_node_identity`. The frame turns each abstention into a **named, fixable extraction target**
(the missing parent-AP/structure key on KMZ flower-pot nodes or drop routes).

## 4. How frames prevent bad overlaps (the bore_log43 symptom)

The user observed bore_log7 visually overlapping bore_log43. **Not investigated as a side quest** — it
is the motivating symptom for one rule:

> **Frame-segment ownership:** a redline may occupy KMZ geometry only where its *own* DrillPathFrame
> proves that geometry. Two logs may share/overlap a segment **only if both frames independently prove
> that shared segment** (same proven run/route). Otherwise an overlap is a *diagnostic*: at least one
> frame is mis-bound or one log is on a legacy route_id it can't prove.

Applied: bore_log7's frame proves `route_469` (the AP-163 terminal tail, off the backbone). bore_log43's
frame is `main_chain_high_station` (stations 4000–5919) on the backbone corridor. **Correctly extracted
frames place them on different geometry** — the overlap exists today only because flag-OFF forces
bore_log7 onto the `route_477` backbone near bore_log43, a placement bore_log7's frame does **not**
prove. So the DrillPathFrame layer should emit an **overlap diagnostic**: for any pair of
candidate/placed geometries overlapping beyond tolerance, assert each owns its overlap via its frame;
flag the pair if not. This is observation-only — it explains overlaps, it does not move anything.

## 5. Where it sits (reuse, no new engine surface)

The layer is **pure + read-only**, beside the existing default-OFF shadow surfaces (the
`terminus_type` shadow and the `backbone_via_topology` / `backbone_corridor_chain` shadow attach
pattern). It **reuses** what already ships — it invents no new matching math:

- `classify_terminus_type(...)` → `terminus_class` + `structure_type`.
- `resolve_terminal_tail_route_for_ap(...)` → AP-anchored terminal-tail binding.
- `BRENHAM_PH5_RUN_ENDPOINTS` (resolver) → run text / termini per sheet.
- `terminal_nodes_from_point_features(...)` + KMZ `point_features` (`{feature_id,name,folder_path,role,lat,lon}`) → node identity.
- `build_route_adjacency(...)` / `TOPOLOGY_EPSILON_FT` → route chains + the overlap test.

It never calls builders / route selection / scoring / geometry, never mutates `STATE` or
`CURRENT_PACKET_PRINT_SHEET_INDEX`.

## 6. Next coding target — Target #18 (pure, read-only, default-OFF)

**Ship `extract_drill_path_frames(...)` as a pure proof layer.**

- New pure function (in `pdf_ap_route_resolver.py` or a sibling `drill_path_frame.py`):
  `extract_drill_path_frames(bore_rows_by_source, point_features, route_catalog, *, run_endpoints=BRENHAM_PH5_RUN_ENDPOINTS) -> list[DrillPathFrame]`.
  Deterministic, order-independent, never raises; emits one frame per source with `proof`/`abstain_reason`.
- Plus a pure `detect_frame_overlaps(frames, route_catalog) -> list[overlap_diag]` for §4.
- New default-OFF flag **`TRUELINE_DRILL_PATH_FRAME_SHADOW`**. When ON, attach read-only
  `pdf_ap_route_shadow["drill_path_frame"]` (and `["frame_overlaps"]`) — **OBSERVATION ONLY**.
  Flag-OFF byte-identical (key absent, not null).
- **Validation gates (required before commit):** flag-OFF byte-identical; `trust_ledger_replay`
  **34/30/0/0/5** flag-OFF AND flag-ON; new tests assert (a) bore_log7 frame = `PROVEN` route_469
  station-451=AP-163, (b) the 5 drops = `BLOCKED / flowerpot_node_identity`, (c) the overlap detector
  flags bore_log7(OFF route_477) vs bore_log43 as `not_owned_by_frame`. Adversarial pass.

This layer **decides nothing and places nothing** — it makes the per-log proof (or the exact gap) a
first-class, test-locked artifact, so future placement work consumes proven frames instead of
re-deriving evidence ad hoc.

## 7. Guardrails (this target)
No placement code. Do not widen `TRUELINE_TERMINAL_TAIL_PLACEMENT`. Do not flip Render flags. No
drift into Render cleanup, auth, UI, screenshots, broad PDF work, KMZ Stage B3, or densification.
DO-NOT-WIDEN intact. bore_log7 vs bore_log43 overlap stays a *symptom/diagnostic*, not a sprint.

## 8. Files referenced
- `gac/bore_log7_route_adjudication.md`, `gac/drop_lane_source_adjudication.md` (this session's proofs).
- Engine (reuse, no change): `classify_terminus_type`, `resolve_terminal_tail_route_for_ap`,
  `BRENHAM_PH5_RUN_ENDPOINTS`, `terminal_nodes_from_point_features`, `build_route_adjacency`
  ([backend/app/core/pdf_ap_route_resolver.py](backend/app/core/pdf_ap_route_resolver.py)).
- Probes (untracked): `scripts/bore_log7_placement_diag.py`, `scripts/drop_lane_adjudication.py`.
