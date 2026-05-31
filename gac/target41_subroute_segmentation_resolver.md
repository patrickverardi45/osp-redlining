# Target #41 — sub-route segmentation resolver (no `.FS`), default-OFF, read-only

**Mission:** determine, from delivered geometry alone, which 413 ft portion of the 741.7 ft route_465
tail bore_log57 occupies — last/first/middle, or impossible/competing — without `.FS` and without
guessing.

**VERDICT: `NOT_UNIQUE_COMPETING_SEGMENTS`.** The route geometry gives a *definitive* answer to the
segmentation question, and that answer is that bore_log57's 413 ft does **not** correspond to a
proof-grade drive ending at AP-157. route_465 runs **AP-157 (offset 0) ↔ SPLICE LOC 45 (offset
741.7)**, with a **Flower Pot (~289)** and **Installer HH (~690)** between. Two readings compete and
nothing in the delivered files discriminates them:
- **Terminus reading** — "last 413 ft ending at AP-157" — ends at the proven AP terminus but **starts
  in OPEN SPACE** (offset 413 → nearest node ~35 ft; no pit). Bores start at a structure, so this is
  geometrically implausible.
- **Structure reading** — the only ~413 ft *structure-to-structure* segment is **Flower Pot →
  Installer HH (~401 ft)**, which does **NOT** reach AP-157.

No segment is simultaneously length-matched, structure-to-structure anchored, **and** ending at the
AP terminus → not placeable. The control **bore_log7 → PLACEABLE_SEGMENT_PROVEN** (route_469 ~459 ft
≈ bore ~451 ft is the *whole* route, both ends real structures: AP-163 + SPLICE LOC 46). No placement
created; bore_log7 lane + 9 endpoints untouched.

> Read-only; `scripts/` only; no `.FS`; no flag/STATE/geometry/placement.
> Resolver `scripts/target41_subroute_segmentation_resolver.py` (+ `target41_signal_dump.py`) →
> `.json`/`.out`. Self-test `SELFTEST_OK` (control proof-grade).

---

## 1. Evidence rules + weights (proof-grade segment gates)

A candidate sub-segment of length ≈ bore length is **proof-grade** only if ALL hold (the bore_log7
shape — a pit-to-pit drill whose terminus end is the proven AP):

| gate | meaning |
|---|---|
| **G_len** | segment length within 10% of the bore length |
| **G_anchor** | BOTH endpoints sit on a real KMZ structure (≤20 ft) — a bore drills pit-to-pit, not from open space |
| **G_term** | one endpoint is the proven AP terminus (≤12 ft) |

Verdict: PLACEABLE if exactly one distinct segment passes all three; NOT_UNIQUE if ≥2 distinct
proof segments, **or** an anchored-but-non-terminus segment competes with a terminus-but-open-start
segment; else HARD_BLOCKED.

## 2. route_465 structural anchors + candidate segments (machine output)

```
route_465 total 741.7 ft, oriented from AP-157 (offset 0):
  anchors: AP-157 @0 (Terminal Port HH) · Flower Pot @288.7 · Installer HH @690.0 · SPLICE LOC 45 @741.7
candidates (len ~ 413 ft):
  structure_to_structure  off 288.7->690.0  len 401.3  both_anchored=Y  ends_at_terminus=N
  structure_to_structure  off 288.7->741.7  len 453.0  both_anchored=Y  ends_at_terminus=N
  terminus_anchored       off 413.0->0.0    len 413.0  both_anchored=N (start open, nearest node 35.3 ft)  ends_at_terminus=Y
  => proof-grade (all three gates): NONE  => NOT_UNIQUE_COMPETING_SEGMENTS
```

Direct answers to the mission's four options:
- **last 413 ft ending at AP-157** — terminus ✓ but start = open space ✗ (no pit) → not proof-grade.
- **first 413 ft from the opposite end** — its END lands 259 ft from AP-157 → does not end at the terminus.
- **middle 413 ft** — neither end at AP-157, and only Flower Pot→Installer HH (~401 ft) is anchored,
  which doesn't reach the terminus.
- **competing with another segment** — **this is the actual answer**: terminus-reading vs
  structure-reading compete with no discriminator.

## 3. Why this is a real advance (and what it corrects)

#39 bound the terminus to AP-157 by a **station-value** match (bore END 413 == AP-157's run-end 413).
#41 shows the **geometry does not support a placeable 413 ft drive ending at AP-157**: there is no
structure at the 413-ft point, and the nearest structure-to-structure run of that length
(Flower Pot→Installer HH) doesn't touch AP-157. So the 413↔AP-157 coincidence is **not** placement-grade
geometry. This is the honest, geometry-grounded reason placement stays blocked — stronger than #38/#39.

## 4. Missing discriminator (exact, narrow — not `.FS`-wide)

```
missing = a per-bore START-structure (which pit/handhole the drill began at)
why     = the END is the only anchored end; with the START structure known, the 413ft drive is fixed
          and placeable. Equivalent: confirmation of whether the END is AP-157 (terminus reading) or
          the bore is the Flower Pot->Installer HH run (structure reading).
note    = this is a single field, NOT the whole .FS sheet; a start-structure column on the bore log
          would resolve it. No delivered file carries it (re-confirmed #23/#24/#38/#40).
```

## 5. Validation

- `py_compile` OK; resolver `SELFTEST_OK`.
- **Control bore_log7 → PLACEABLE_SEGMENT_PROVEN**: route_469 whole-route segment (AP-163 ↔ SPLICE
  LOC 46), both ends structures, ends at the AP terminus — re-derives the proven #14 placement via the
  segmentation logic. Not degraded.
- 9 endpoints + `BRENHAM_PH5_RUN_ENDPOINTS` are read-only inputs; no placement/flag/STATE/geometry change.

## 6. Verdict + machine-readable

```json
{
  "bore_log57": {"verdict": "NOT_UNIQUE_COMPETING_SEGMENTS", "bore_len": 413.0, "route_total_ft": 741.7,
    "competing": ["terminus_anchored_open_start (ends AP-157, start open space)",
                  "flower_pot->installer_hh ~401ft (anchored, does not reach AP-157)"]},
  "bore_log7_control": "PLACEABLE_SEGMENT_PROVEN",
  "missing_discriminator": "per_bore_start_structure"
}
```

## 7. Next (auto)

#42: apply the whole-route/uniquely-constrained-segment test across **all** bores to find any with a
route length ≈ bore length (the bore_log7 shape) or a uniquely-anchored proof-grade segment — the one
pattern that *is* placeable. Validate against bore_log7, commit, push. DO-NOT-WIDEN intact; flags
default-OFF.

## 8. Files

- New: `scripts/target41_subroute_segmentation_resolver.py` (+ `.json`/`.out`),
  `scripts/target41_signal_dump.py`; this report.
- Read: KMZ route catalog + point features, `BRENHAM_PH5_RUN_ENDPOINTS`, bore_log57/7 xlsx.
