# Target #39 — alternate bore→drive resolver (no `.FS`), default-OFF, read-only

**Mission:** stop treating the `.FS` drive-decomposition sheet as the only path. Build a deterministic
constraint resolver that infers bore→drive binding from **delivered** corpus signals, enumerate every
candidate terminus for bore_log57, score each with explicit evidence, and decide whether AP-157 →
route_465 is uniquely dominant and proof-grade.

**VERDICT: `HARD_BLOCKED_NO_DISCRIMINATOR` — but with a real advance.** The alternate resolver
**uniquely resolves bore_log57's TERMINUS to AP-157** (no `.FS` needed) — an advance over #38, which
could not even confirm the terminus. What remains blocked is the **placement geometry**: the unique
tail to AP-157 (route_465) is **741.7 ft** but the bore is **413 ft** (ratio 1.80), so the bore is a
*sub-segment* of the tail with an unknown start offset, and its prints span a second corridor that
route_465 cannot represent. Placing it would require two unprovable assumptions → wrong-redline risk.
**No placement created. The control bore_log7 re-derives PLACEABLE via this independent resolver
(all gates), proving calibration; the 9 endpoints and bore_log7 lane are untouched.**

> Read-only; `scripts/` only; no `.FS` dependency; no flag/STATE/geometry/placement.
> Resolver `scripts/target39_alternate_bore_drive_resolver.py` (+ `target39_signal_dump.py`) →
> `.json`/`.out`. Self-test `SELFTEST_OK` (control PLACEABLE).

---

## 1. Signals used (all delivered-corpus, no `.FS`)

bore-log station range + direction · print/page set → matchline-graph corridors · AP/terminal
endpoint table (`BRENHAM_PH5_RUN_ENDPOINTS`, #37 9-endpoint) · matchline typing · KMZ terminal-tail
route geometry + **length** · sibling segments (bore_log24 → 57/58) · bore_log7 control · route_480
multi-drive cluster behavior.

## 2. Candidate enumeration + evidence weights

**Terminus score** (per real-structure run-terminus within 20 ft of the END on the bore's print sheets;
matchlines excluded — a bore cannot end at a sheet-boundary):

```
score = station_exactness (1 - |END-run_end|/20)  +  is_real_structure (1.0)
      + corridor_in_prints (1.0)                   +  has_tail_route (1.0)
```
Uniquely dominant ⟺ exactly one candidate with station_exactness ≥ 0.99 AND next candidate ≥ 0.5 below.

**bore_log57 candidates:**

| AP | sheet | STA | station_exact | tail route | tail len | score |
|---|---|---|---|---|---|---|
| **AP-157** | 8 | 413 | **1.0** | route_465 | 741.7 ft | **4.0** |

Only one real-structure terminus lands at the exact END (413). The sheet-13 `@398` is a **matchline**
(excluded). AP-156@387 (26 ft), flower_pot@457 (44 ft), AP-163@451 (38 ft, corridor B, already
bore_log7's) all fall outside 20 ft. **AP-157 is uniquely dominant** (G1 ✓).

## 3. Proof-grade placement gates (the bore_log7 shape)

| gate | bore_log57 | bore_log7 (control) |
|---|---|---|
| **G1** terminus uniquely dominant | ✓ AP-157 | ✓ AP-163 |
| **G2** tail length ≈ bore max-station (±15%) | ✗ **741.7 vs 413 (ratio 1.80)** | ✓ 459.2 vs 451 (ratio 1.02) |
| **G3** single corridor | ✗ spans `[3-9,23,24]` + `[10,12,13,14]` | ✓ `[10,12,13,14]` |
| **G4** print mapping certain | ✗ flagged uncertain | ✓ |
| **verdict** | **HARD_BLOCKED_NO_DISCRIMINATOR** | **PLACEABLE_BY_ALTERNATE_RESOLVER** |

The control independently re-derives bore_log7 → AP-163 → route_469 (the placement proven in #14) via a
*different* mechanism (terminus scorer + tail-length match), confirming the resolver is correctly
calibrated and does not degrade the proven lane.

## 4. Why bore_log57 is not proof-grade placeable

The terminus is settled (AP-157), but the **geometry** is not:
1. **Length gap (G2):** route_465 is the unique tail ending at AP-157 (endpoint 2.1 ft from the node),
   but it is 741.7 ft while the bore is 413 ft. So the bore is **not** the whole tail — it is a 413 ft
   sub-segment. Placing it as "the last 413 ft ending at AP-157" assumes the bore started **mid-tail**
   (route_465 offset ~329 ft), not at a structure — physically implausible without the drive split.
2. **Corridor span (G3):** route_465 lies entirely in corridor A (sheet 8), but the bore's prints
   include corridor B (sheets 10, 13). Either the corridor-B prints are mis-mapped, or the bore
   traverses corridor B before AP-157 — route_465 alone cannot represent a cross-corridor path.
3. **Print uncertainty (G4):** the bore's own note flags the print mapping unreliable, so neither
   reading (corridor A only vs A+B) can be trusted.

Placement would require assuming (a) the AP-157-end 413 ft sub-segment **and** (b) the corridor-B prints
are spurious — two unprovable assumptions. Under "no wrong redlines," the resolver **abstains**.

## 5. Missing discriminator (exact)

```
missing = per-drive segmentation / start-structure
purpose = (a) fix WHICH 413ft sub-segment of the 741.7ft route_465 tail the bore occupies
          (resolve the length gap), and (b) resolve which corridor path the bore takes.
candidates that would supply it (any one):
  - a per-bore START-structure field (the pit/handhole the drill began at)
  - drive segmentation (the .FS sheet — confirmed absent #23/#24, but NOT the only option)
  - a corroborating sibling decomposition (bore_log58 = Segment B shares the SAME uncertain prints
    {8,10,13} and span 256ft -> does NOT decompose; checked, no help)
```

Note this is **not** an `.FS`-only dependency: a start-structure field on the bore log, or a corrected
(certain) print mapping isolating corridor A, would also unblock it. The signal that is genuinely
absent is *where the 413 ft begins* — the terminus end is solved.

## 6. Validation (vs bore_log7 + 9 endpoints)

- `py_compile` OK; resolver `SELFTEST_OK`.
- **Control:** bore_log7 → PLACEABLE_BY_ALTERNATE_RESOLVER, re-deriving AP-163 → route_469 (proven #14)
  — not degraded.
- The 9 confirmed endpoints + `BRENHAM_PH5_RUN_ENDPOINTS` are read-only inputs; precision/recall
  untouched. No placement performed, no flag/STATE/geometry change.

## 7. Verdict + machine-readable

```json
{
  "bore_log57_verdict": "HARD_BLOCKED_NO_DISCRIMINATOR",
  "bore_log57_terminus": 157,
  "terminus_uniquely_resolved": true,
  "placement_gates": {"G1_terminus_unique": true, "G2_length_match": false,
                      "G3_single_corridor": false, "G4_print_certain": false},
  "missing_discriminator": "per_drive_segmentation_or_start_structure (resolves 741-vs-413 tail length gap + corridor-B prints)",
  "control_bore_log7": "PLACEABLE_BY_ALTERNATE_RESOLVER"
}
```

## 8. Next

Continue (#40): apply this same resolver to the 6 route_480 multi-drive logs (57 done; 29/31/46/47/58)
to enumerate their candidate termini and verdicts. The resolver is general; it will either uniquely
resolve a terminus (advance) or output competing candidates + the missing discriminator per log. No
placement unless a log passes all four gates (none expected, but the evidence — not assumption —
decides). DO-NOT-WIDEN intact; all flags default-OFF.

## 9. Files

- New: `scripts/target39_alternate_bore_drive_resolver.py` (+ `.json`/`.out`),
  `scripts/target39_signal_dump.py`; this report.
- Read: KMZ route catalog + point features (`_build_route_catalog`/`_build_kmz_reference`),
  `BRENHAM_PH5_RUN_ENDPOINTS`, `brenham_plan_sheet_graph`, `ap_structure_index.json`, bore_log57/58/7 xlsx.
