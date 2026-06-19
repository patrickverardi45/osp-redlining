# Target #16 — Flower-Pot DROP Lane Source Adjudication (PROOF ONLY)

**Question:** Can each flower-pot DROP bore be **deterministically bound** from source files
(bore-log xlsx + engineering-PDF run→endpoint table + KMZ) to a **unique** flower-pot / drop geometry —
the same way bore_log7 bound to route_469?

**VERDICT: BLOCKED for all 5 — a real, named extraction gap (not a guess, not "ask a human").**
The PDF proves each bore ends at a *flower-pot* terminus (shipped `classify_terminus_type` agrees:
`flower_pot_drop` ×5), but the **flower-pot end has no unique KMZ identity**, so no specific drop
geometry is selectable. This is the structural opposite of bore_log7, where AP-163 was a *numerically
named* KMZ node giving a unique PDF-station→lat/lon bridge.

> Proof only. No placement code, no flag change, no engine/backend/web/data change, nothing placed.
> DO-NOT-WIDEN intact; `TRUELINE_TERMINAL_TAIL_PLACEMENT` not widened; no Render flags flipped.

---

## Per-bore evidence

| bore | print/sheet | station range | PDF terminus @ END (run→endpoint table) | KMZ candidate | verdict |
|---|---|---|---|---|---|
| **bore_log5** | 12 | 265 → **500** | sheet 12 flower_pot @ **507 & 510** (2 within ±15 ft) | unnamed pot; 480 drop routes, none station-keyed | BLOCKED |
| **bore_log30** | 10, 12 | 0 → **500** | sheet 12 flower_pot @ **507 & 510** (2) | unnamed pot; none station-keyed | BLOCKED |
| **bore_log48** | 10, 11, 12 | 0 → **509** | sheet 12 @ **510 & 507** + sheet 11 @ **514** (3) | unnamed pot; none station-keyed | BLOCKED |
| **bore_log50** | 10, 11, 12 | 0 → **514** | sheet 11 @ **514** + sheet 12 @ **510 & 507** (3) | unnamed pot; none station-keyed | BLOCKED |
| **bore_log65** | 9, 10 | 451 → **650** | sheet 9 flower_pot @ **650** (1, unique on PDF) | unnamed pot; none station-keyed | BLOCKED |

Shipped-classifier cross-check (`classify_terminus_type`, same `BRENHAM_PH5_RUN_ENDPOINTS` table):
all 5 → `flower_pot_drop` (high); bore_log7 → `backbone_ap_bore` (med) for contrast. Confirms the
bucket; does **not** confirm bindability.

---

## Why blocked (two stacked gaps)

**Gap A — flower-pot node identity (primary, all 5).** The KMZ has **158 flower-pot nodes, 0 of them
named** (`folder_path = "Nodes / Flower Pot"`, every `name = "Unnamed Feature"`). By contrast the 64
Terminal-Port-Handhole/AP nodes are numerically named ("163", …). bore_log7 worked *because* its run
ended at named AP-163 → unique node → unique length-matched route_469. A flower-pot terminus gives a
PDF **station** but no key that selects **which** of the 158 pots (or which of 480 Vacant-Pipe/House-Drop
routes) is this bore's. The bore-log xlsx carries no AP/structure key either (cols: station/depth/boc/
date/crew/print/notes).

**Gap B — PDF flower-pot terminus is itself non-unique (4 of 5).** On the print sheet, bore_log5/30/48/50
each have **2–3** flower-pot run-termini within ±15 ft of their end station (sheet 12 @ 507/510, sheet 11
@ 514). So even before the KMZ step, the PDF alone does not isolate a single drilled drop terminus.
(bore_log65 is the lone PDF-unique case — sheet 9 @ 650 — but still dies on Gap A.)

---

## Exact missing relationship to extract next (named)

A **drop-identity key** that ties each drop bore to ONE specific drop structure. In priority order:

1. **Parent-AP / structure tag per drop in the KMZ** — give each `Nodes / Flower Pot` (or each
   `Connections / Vacant Pipe` / `House Drop` route) the parent AP or address it hangs off. Then a drop
   bore on print sheet N off AP-x binds to the unique pot/route under AP-x. (The KMZ already names APs;
   flower pots/drop routes are the unnamed layer — this is the smallest source fix.)
2. **`.FS` Fiber-Schematic / drive-decomposition sheet** — the artifact named in Targets #8/#9/#10 as
   absent from the packet; it maps each bore's station sub-ranges → drive/structure, which would also
   supply the parent key.
3. **A drop-id column in the bore-log xlsx** — if crews recorded the served address / pot id, that is a
   direct join key (currently absent).

None of these is in the provided files. Until one exists, the 5 drops correctly **abstain** (interim
safety state + this named target) — DO-NOT-WIDEN: do not place them on a guessed pot or on the route_480
backbone.

---

## Next redline action
- **DROP lane:** acquire any ONE of the three keys above (key #1 is the smallest — a parent-AP tag on
  flower-pot nodes or drop routes in the KMZ). Re-run `scripts/drop_lane_adjudication.py` to confirm the
  bridge closes before any placement design.
- **Meanwhile:** the cleanly-proven lane remains bore_log7/route_469 (Target #14/#15 + the d4a7a2f
  adjudication) — its operator final-audit + Render flag flip is the only placement currently source-proven.

## Files read
- Source (read-only, this session): `Brenham, TX - Phase 5_Design Team.kmz` (576 point features incl.
  158 flower pots / 64 APs; 480 drop-class routes), `bore_log{5,30,48,50,65}.xlsx`.
- Engine table (no change): `BRENHAM_PH5_RUN_ENDPOINTS` + `classify_terminus_type`
  ([pdf_ap_route_resolver.py:989, :1067](backend/app/core/pdf_ap_route_resolver.py:989)).
- Probe: `scripts/drop_lane_adjudication.py` → `scripts/drop_lane_adjudication.out` (untracked diagnostics).
