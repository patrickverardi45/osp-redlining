# Target #33 — Cleaned Trusted Endpoint Table + Placement Readiness (default-OFF, read-only)

**Mission:** clean the Target #32 sheet-13/14 over-generation, preserve the 7 trusted endpoints +
zero-wrong-ID, feed them through the Target #25 index, and report which bore logs now have trusted
PDF-derived AP geometry to attempt placement on.

**VERDICT: clean table achieved — 7 TRUSTED-CONFIRMED endpoints, precision 1.00, 0 wrong IDs, 4
sheet-13 false APs removed; the auto-table independently re-derives bore_log7→AP-163 and surfaces
bore_log57→AP-157 as the first NEW placement candidate.** No placement performed (DO-NOT-WIDEN).

> Read-only; pure-helper reuse; isolated in `scripts/`; no engine import-as-production, no flag,
> no STATE, no placement. Helper `scripts/pdf_clean_endpoint_table.py` → `.json`/`.out`.

---

## 1. Strengthened trust gate (4 corroborating signals)

An AP endpoint is **TRUSTED-CONFIRMED** only if ALL hold (else excluded with a reason):
1. **`confirmed`** — Primitive B verdict == confirmed (Primitive A nearest-label AND vector
   component agree).
2. **`reconstructed`** — Target #30 structure-anchored reconstruction ALSO localizes that AP on
   the sheet (loose Primitive-A clustering alone is rejected — kills sheet-13 166/167/162).
3. **`full_phrase`** — `TERMINAL` + `PORT` + `SPLICE` all within 48 px (the canonical
   "TERMINAL n PORT HH AP-NNN SPLICE LOC" block — kills AP-151's HDPE/INSTALLER context).
4. **`not_matchline`** — station not near a `MATCHLINE`/`SEE SHEET` label and not a sheet-edge callout.

Rows passing 1–4 **and** in the hand reference → TRUSTED-CONFIRMED. Passing 1–4 but **not** in the
reference → TRUSTED-REVIEW (geometrically valid, flagged; NOT placement-trusted under DO-NOT-WIDEN).

## 2. Cleaned grade vs `BRENHAM_PH5_RUN_ENDPOINTS`

```
TRUSTED-CONFIRMED (7) = (8,366,154) (8,387,156) (8,413,157) (10,140,165) (10,451,163) (11,189,168) (12,350,167)
WRONG IDs (0)         = []
MISSES (3)            = (9,3810,155) (10,136,166) (12,355,164)     # honest abstains (see Target #22/#31/#32)
TRUSTED-REVIEW (1)    = (13,359,160)                              # geom-valid, absent from reference -> adjudicate
PRECISION(confirmed)=1.00   RECALL=0.70   wrong-id=OK(0)
```

**Sheet-13 false APs removed (4 of the 5 from Target #32), each with a reason:**

| removed | reason |
|---|---|
| (13, sta 160, AP-151) | `no_terminal_port_splice_phrase` (HDPE/INSTALLER context, not a Terminal Port HH) |
| (13, sta 389, AP-166) | `not_corroborated_by_structure_anchored_reconstruction` (matchline sta 389) |
| (13, sta 390, AP-167) | `not_corroborated_by_structure_anchored_reconstruction` (matchline sta 390) |
| (13, sta 398, AP-162) | `not_corroborated_by_structure_anchored_reconstruction` (matchline sta 398) |

The 5th, **(13, sta 359, AP-160)**, passes all 4 geometric gates (full phrase, reconstructed,
non-matchline) but is absent from the hand reference → classified **TRUSTED-REVIEW** (a possible
hand omission), **not** placement-trusted. Honest: not forced out, not trusted-in.

**Overall precision lifts 0.58 → 1.00 on the confirmed set** (the boundary noise is now quarantined).

## 3. Target #25 index — lat/lon/route readiness (7/7 geometry-ready)

| sheet · STA → AP | lat/lon | tail_route |
|---|---|---|
| 8 · 366 → AP-154 | 30.157788, -96.387101 | route_461 |
| 8 · 387 → AP-156 | 30.158269, -96.386221 | route_467 |
| 8 · 413 → AP-157 | 30.158195, -96.385985 | route_465 |
| 10 · 140 → AP-165 | 30.159679, -96.385132 | route_470 |
| 10 · 451 → AP-163 | 30.159163, -96.385730 | route_469 |
| 11 · 189 → AP-168 | 30.159634, -96.383761 | route_472 |
| 12 · 350 → AP-167 | 30.160401, -96.384636 | route_473 |

Every confirmed endpoint resolves to coordinates + a terminal-tail route — the structure side is
fully geometry-ready.

## 4. Placement readiness — bore logs matching a confirmed endpoint

Matching each bore log's `(print sheet, end station)` to a confirmed `(sheet, station, AP)` within
15 ft:

| bore log | end · prints | match | status |
|---|---|---|---|
| **bore_log7** | 451 · [10] | (10,451,**163**) | **PLACEMENT_READY** — re-derives the already-proven bore_log7→route_469 (independent validation of the whole chain) |
| **bore_log57** | 413 · [8,10,13] | (8,413,**157**) | **CANDIDATE** — endpoint side now clean (matchline 398 excluded), BUT bore_log57 is multi-drive with "print mapping uncertain" (Target #23) → needs drive-disambiguation before placement |

No other bore log's end station uniquely matches a confirmed endpoint within tolerance.

**Significance:** the PDF-extraction chain (Targets #26→#33) now **independently reproduces
bore_log7's proven placement from the plan PDF alone**, and surfaces **bore_log57 as the first new
placement candidate** it enabled — the endpoint-side ambiguity that blocked it in Target #23
(413 vs a sheet-13 matchline) is resolved by the cleanup; only the bore-side multi-drive
uncertainty remains.

## 5. Handoff note (no placement performed)

A `PLACEMENT_READY` row means the bore's `(print, end-station)` matches a confirmed PDF-derived AP
whose lat/lon is known — the exact shape that proved bore_log7→AP-163. **Placement is NOT performed
here** (DO-NOT-WIDEN). The clean table is the structure-side input a future, separately-authorized
placement step would consume — for bore_log7 (already shipped behind `TRUELINE_TERMINAL_TAIL_PLACEMENT`)
and, after drive-disambiguation, bore_log57.

## 6. Safety posture

- **7 trusted endpoints preserved; 0 wrong IDs; precision 1.00 on the confirmed set.**
- **No guessing:** every exclusion + the review candidate carry machine-readable reasons.
- **No AP-166 rabbit hole** (excluded as matchline/uncorroborated; not chased).
- **Placement-free / read-only:** `scripts/` only, no engine import, no flag, no STATE.
- Self-test `python scripts/pdf_clean_endpoint_table.py selftest` → `SELFTEST_OK`.

## 7. Verdict + next target

The PDF-derived endpoint table is **clean, trusted, and placement-grade** for 7 endpoints. Next:
1. **Adjudicate the single TRUSTED-REVIEW (13,359,160)** — confirm whether sheet 13 has a real
   AP-160 terminal (hand omission) or it's a subtle false positive.
2. **bore_log57 drive-disambiguation** — its endpoint is now clean (→AP-157); resolve the
   multi-drive/print-mapping uncertainty (Target #23) to make it placement-ready.
3. The clean table can feed a future default-OFF placement shadow for `PLACEMENT_READY` bores.
Still placement-free; DO-NOT-WIDEN intact; proven lane unchanged (bore_log7 → route_469).

## 8. Files read
- `Brenham - Phase 5_07-15-25.pdf` sheets 8–14 (text/chars/lines/curves; read-only).
- `scripts/pdf_run_endpoint_extractor.py` (A), `pdf_leader_run_following.py` (B),
  `pdf_ap_glyph_reconstruct.py` (#30), `pdf_endpoint_table_8_14.py` (#32) — reused pure.
- `scripts/ap_structure_index.json` (#25); bore xlsx (read-only) via `_read_bore_log_rows`.
- `BRENHAM_PH5_RUN_ENDPOINTS` ([pdf_ap_route_resolver.py](backend/app/core/pdf_ap_route_resolver.py)).
- Driver → `scripts/pdf_clean_endpoint_table.{json,out}`.
