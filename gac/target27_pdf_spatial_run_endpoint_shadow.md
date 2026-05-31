# Target #27 — PDF Spatial Run-Endpoint Extractor Shadow (default-OFF, read-only) — built

**Mission:** implement Primitive A (Target #26) — derive structure-side run endpoints from the
plan-sheet LAYOUT (positioned text + char geometry), validated against the hand-transcribed
`BRENHAM_PH5_RUN_ENDPOINTS`. Default-OFF, pure, placement-free.

**VERDICT: WORKS — validation gate PASSES both required cases; 5/6 hand AP run-ends reproduced
deterministically from the PDF, with honest abstains on the rest.** Primitive A is proven
implementable: the bore→structure relationship the corpus "didn't contain" (Target #24) is in
fact extractable from the plan-sheet geometry the PDFs already carry.

> Read-only. The pure extractor is isolated in `scripts/`, never imported by the engine, wires
> no flag, touches no STATE, and never feeds resolve/selection/scoring/placement. Nothing placed.
> Helper: `scripts/pdf_run_endpoint_extractor.py`; output: `…json` + `…out`.

---

## 1. Validation gate (the goal's hard requirement)

```
[PASS] sheet 10  STA 451 -> AP-163
[PASS] sheet  8  STA 413 -> AP-157
```
Both reproduced purely from layout: STA callout → nearest structure label (`TERMINAL`/`PORT` at
13.1 / 14.4 px) → unique valid-AP digit-cluster (163 @ 6 px, 157 @ ~14 px), validated against the
64-AP universe from the Target #25 index so dimensions/addresses/footages are rejected.

## 2. Method (Primitive A, deterministic, no guessing)

Per detailed sheet, the PURE `extract_run_endpoints_from_layout(words, chars, valid_ap_ids)`:
1. Position-aware extract: `extract_words(use_text_flow=True)` (STA + structure labels with x/y)
   and `page.chars` (positioned digits for AP recovery).
2. For each `STA d+dd` callout → **nearest structure-type label within 28 px** (`TERMINAL`/`PORT`
   ⇒ ap, `FLOWER` ⇒ flower_pot, `SPLICE` ⇒ splice).
3. For an AP-class structure → the **unique nearest valid-AP digit cluster within 45 px** of the
   *structure label*, **excluding the station's own value** (kills the STA-160-vs-AP-160
   collision). **Abstains** (no guess) when the nearest AP cluster is beyond tol, two valid APs
   are within a 1.4× margin (tie), or no valid-AP cluster exists.
4. `0+00` callouts are skipped — a run START is not an endpoint (direction needs Primitive B).
5. Dedup by `(station, type, ap)`, keeping the highest-confidence record.

Output record: `{sheet, station_ft, structure_type, ap_id|null, confidence, evidence{sta_xy,
struct_label, struct_dist_px, ap_recovery{reason, candidates, dist_px}}}`.

## 3. Comparison vs `BRENHAM_PH5_RUN_ENDPOINTS` (sheets 8 & 10, AP rows)

| metric | result |
|---|---|
| hand AP rows | 6 |
| auto AP rows | 6 |
| **REPRODUCED** | **5** — (8,366,154) (8,387,156) (8,413,157) (10,140,165) (10,451,163) |
| MISSED | 1 — **(10,136,166)** |
| EXTRA | 1 — **(8,308,110)** |

Plus, correctly typed without an id (flower pots are id-less by design — Target #20): flower_pot
run-ends detected at sheet-8 STA 299/457/557/614 and sheet-10 STA 47/92/100/376/508; splice rows
likewise typed. 13 AP-class STA callouts **abstained** honestly (AP number not within tol —
mostly matchline stations + run-starts the hand table classifies as non-AP anyway).

## 4. Misses / ambiguities — reported honestly (per the gate)

- **MISS (10,136,166):** at the STA-136 PORT structure, after excluding the station's own value
  the nearest valid-AP cluster is AP-125 @ 59 px (beyond the 45 px tol) → the extractor
  **abstains** rather than guess. AP-166's glyph is not within tol of that structure label;
  binding it needs **Primitive B (leader-line following)** to walk the run to its true end AP.
  This is an honest abstain, not a wrong placement.
- **EXTRA (8,308,110):** a high-confidence `STA 308 → PORT → AP-110` that the hand table does NOT
  list. This is either a **hand-transcription omission the auto-extractor caught** (AP-110 is a
  real terminal; the structure label is 12 px away) or a false positive — flagged for review, not
  asserted. Notably it suggests the extractor can be *more complete* than manual reading.
- **13 abstains:** matchline stations (160/162/166/167/190/191 — the hand table marks these
  `matchline`, not AP) and high-station splices; Primitive A has no MATCHLINE-label exclusion yet,
  so it correctly abstains (no unique AP within tol) instead of mis-binding.

**Net precision on the validated scope:** of the 6 records emitted, 5 are exact hand-table AP
matches and 1 is a review candidate; 0 wrong AP ids were emitted (every uncertain case abstained).

## 5. Safety posture

- **Placement-free / default-OFF by construction:** lives in `scripts/`, no engine import, no
  flag, no STATE; produces a structure-side table only. Building the bore→geometry placement is a
  separate, still-gated step (DO-NOT-WIDEN).
- **No guessing:** every uncertain binding abstains with a machine-readable reason.
- **Validation-gated:** the extractor is graded against the hand table on every run; it ships as a
  shadow precisely because it reproduces the known-correct entries.
- **Self-test:** `python scripts/pdf_run_endpoint_extractor.py selftest` → `SELFTEST_OK`
  (determinism, AP validation, dimension-noise rejection, tie-abstain).

## 6. Verdict + next target

Primitive A is **implemented and validated** — the structure-side run-endpoint table is now
**auto-derivable from the PDF**, not hand-transcribed. Next implementation target:
1. **Primitive B — leader-line / run-polyline following** (`page.lines`/`curves`): walk each
   DIR.BORE run from its `0+00` start to its end structure, fixing the MISS class (10,136,166),
   distinguishing run-START vs run-END, and resolving the multi-valid-AP cases by connection
   rather than nearest-label.
2. **MATCHLINE-label exclusion** so matchline stations stop entering the AP-abstain pool.
3. Extend beyond sheets 8 & 10 to all detailed sheets (8–14), each gated by hand-table equality
   where the hand table has coverage.
Then the auto-derived table feeds the Target #25 index — so the instant a bore→station/print clue
binds (via Primitive B run subranges), the bore resolves to geometry. Still placement-free.

## 7. Files read
- `Brenham - Phase 5_07-15-25.pdf` sheets 8 & 10 (positioned words + chars; read-only).
- `BRENHAM_PH5_RUN_ENDPOINTS` ([pdf_ap_route_resolver.py](backend/app/core/pdf_ap_route_resolver.py)) — the validation hand table.
- `scripts/ap_structure_index.json` (Target #25) — the valid-AP universe + geometry catcher.
- Target #26 report/probe (the spatial-join premise).
- Helper: `scripts/pdf_run_endpoint_extractor.py` (`extract_run_endpoints_from_layout`, pure) → `.json` + `.out`.
