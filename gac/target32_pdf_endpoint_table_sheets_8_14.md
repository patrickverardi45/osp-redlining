# Target #32 — PDF Run-Endpoint Table, Sheets 8–14 (default-OFF, read-only)

**Mission:** scale the A→B extraction chain across the full detailed-plan band (sheets 8–14),
exclude matchline/SEE-SHEET from trust, grade against `BRENHAM_PH5_RUN_ENDPOINTS` with
precision/recall + a hard zero-wrong-ID policy, feed recovered APs through the Target #25 index,
and make ONE bounded cross-sheet attempt at STA 136 → AP-166.

**VERDICT: the chain SCALES cleanly on the AP-terminal sheets — 7/10 hand endpoints recovered
across sheets 8–12 at 100% precision and ZERO wrong IDs.** Boundary sheets 13–14 over-generate
(named limitation). AP-166 correctly abstained and stopped (no loop).

> Read-only; pure-helper reuse (A/B/#30/#31); isolated in `scripts/`; no engine import-as-
> production, no flag, no STATE, no placement. Driver `scripts/pdf_endpoint_table_8_14.py` →
> `.json`/`.out`.

---

## 1. Sheets processed & trust rule

Sheets **8, 9, 10, 11, 12, 13, 14** (pdf pages 21–27). An AP endpoint is **trusted** iff
Primitive B verdict == `confirmed` (Primitive A nearest-label AND vector-component agree) AND its
station is not a matchline/SEE-SHEET station. Everything else is review/abstain.

## 2. Grade vs `BRENHAM_PH5_RUN_ENDPOINTS` (AP rows)

```
hand AP rows = 10 ; trusted = 12
TRUE POSITIVES (7) = (8,366,154) (8,387,156) (8,413,157) (10,140,165) (10,451,163) (11,189,168) (12,350,167)
WRONG IDs      (0) = []                       <- zero-wrong-ID policy PRESERVED
EXTRA/REVIEW   (5) = (13,160,151) (13,359,160) (13,389,166) (13,390,167) (13,398,162)
MISSES         (3) = (9,3810,155) (10,136,166) (12,355,164)
```

| scope | TP | extra | miss | precision | recall | wrong-id |
|---|---|---|---|---|---|---|
| **AP-terminal sheets 8–12** | **7** | **0** | 3 | **1.00** | **0.70** | **0** |
| boundary sheets 13–14 (hand has 0 AP rows) | 0 | 5 | — | — | — | 0 |
| overall 8–14 | 7 | 5 | 3 | 0.58 | 0.70 | 0 |

**The honest precision story:** on the sheets that actually carry AP terminals (8–12), precision
is **1.00** with **0 wrong IDs**. The 5 "extras" are all on sheet 13 — a matchline/boundary sheet
with **zero** hand AP rows — where the extractor reads matchline/cross-reference numbers
(3 of the 5 sit at known sheet-13 matchline stations 389/390/398) as APs. The matchline
label-proximity filter is **insufficient on 13/14**; those rows are **not trusted-clean** and are
quarantined as `boundary_sheet_overgeneration`.

## 3. Misses (machine-readable, all honest abstains — none guessed)

- **(9,3810,155):** high-station AP (3810) — the structure is far from any local 0+00 callout;
  the nearest-label/component chain doesn't bind it (related to the main-chain high-station class,
  Target #22). Abstain.
- **(10,136,166):** the Target #31 unbridgeable case (hatch gap, no DIR.BORE label, separate
  components). Abstain — see §5.
- **(12,355,164):** AP-164 @ STA 355 sits ~5 ft from AP-167 @ STA 350 (both trusted-region);
  component contamination between the adjacent pair → AP-164 not uniquely confirmed. Abstain (the
  adjacent AP-167 IS recovered, so no wrong-ID — the chain abstains rather than mis-bind).

## 4. Target #25 index — geometry-ready confirmation

**7/7 trusted APs are geometry-anchor-ready** (lat/lon present in the Target #25 index):
154, 156, 157, 165, 163, 168, 167. So every geometry-provable endpoint this target recovered is
immediately resolvable to coordinates the instant a bore binds to it.

## 5. Bounded AP-166 cross-sheet attempt (one shot, then stop)

Sheet 10's matchline-connected corridor = {10, 12, 13, 14}. The only trusted `…→166` row anywhere
is `(13,389,166)` — but **STA 389 is a matchline station on sheet 13**, so it is **rejected as a
boundary-sheet false positive**. There is **no matchline boundary equation** linking sheet 10 to
{12,13,14} at STA 136, so no deterministic STA-136 → AP-166 continuation exists.

**Result: (10,136,166) NOT RECOVERED — abstained and STOPPED** (per the one-bounded-attempt rule;
no AP-166 loop). This is consistent with Target #31: the 136→166 run is simply not rendered as a
followable polyline, on sheet 10 or across a matchline.

## 6. Safety posture

- **Zero wrong IDs** across all 7 sheets — the load-bearing policy holds.
- **No degradation:** the Target #27/#28/#30/#31 trusted cases (451→163, 413→157, 366→154,
  387→156, 140→165) are all present in the TP set.
- **No guessing:** every miss/extra/abstain carries a reason; boundary-sheet over-generation is
  flagged, not trusted; AP-166 abstains and stops.
- **Placement-free / read-only:** `scripts/` only, no engine import, no flag, no STATE.
- Self-test `python scripts/pdf_endpoint_table_8_14.py selftest` → `SELFTEST_OK`.

## 7. Verdict + next target

The extraction chain **scales to a reusable, geometry-derived run-endpoint table** with 100%
precision / 0 wrong-IDs on the AP-terminal sheets — 7 endpoints auto-recovered and confirmed
geometry-ready. Next:
1. **Strengthen matchline/boundary exclusion** beyond label proximity — use the
   `brenham_plan_sheet_graph` boundary-STA equations + SEE-SHEET text to mask boundary sheets
   (13/14) so they stop injecting false APs (lifts overall precision 0.58 → 1.00).
2. **Adjacent-AP disambiguation** for the (12,355,164) class (two APs within ~5 ft) via tighter
   per-structure component scoping.
3. The recovered 7-endpoint table is ready to feed the Target #25 index as auto-derived
   structure-side truth (replacing hand transcription for those rows).
Still placement-free; DO-NOT-WIDEN intact.

## 8. Files read
- `Brenham - Phase 5_07-15-25.pdf` sheets 8–14 (text/chars/lines/curves; read-only).
- `scripts/pdf_run_endpoint_extractor.py` (A), `pdf_leader_run_following.py` (B),
  `pdf_ap_glyph_reconstruct.py` (#30), `pdf_component_bridge.py` (#31) — reused pure.
- `BRENHAM_PH5_RUN_ENDPOINTS` + `brenham_plan_sheet_graph` ([backend/app/core](backend/app/core)).
- `scripts/ap_structure_index.json` (Target #25). Driver → `scripts/pdf_endpoint_table_8_14.{json,out}`.
