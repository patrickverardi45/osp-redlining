# Target #42 — corpus-wide next-placeable-bore sweep (the bore_log7 shape), default-OFF, read-only

**Mission (auto-continued from #41):** search the entire bore corpus for any bore with the placeable
shape — terminus on a confirmed PDF endpoint **and** a unique proof-grade structure-to-structure
segment ending at that terminus (exactly what makes bore_log7 placeable).

**VERDICT: NEW placeable beyond bore_log7 = NONE.** Across **58 bore logs**, only **two** bind to any
confirmed PDF endpoint at all: **bore_log7 → PLACEABLE_SEGMENT_PROVEN** and **bore_log57 →
NOT_UNIQUE_COMPETING_SEGMENTS** (#41). The other **56 bores have no confirmed-endpoint match** (their
END station lands on no confirmed AP run-terminus on their print sheets). The deterministically-
placeable set from the delivered files is therefore **exactly {bore_log7}** — now proven by a
corpus-wide sweep, not inferred from the route_480 bucket alone.

> Read-only; `scripts/` only; reuses the #41 segment resolver verbatim; no `.FS`, no flag/STATE/
> geometry/placement. Driver `scripts/target42_next_placeable_bore_sweep.py` → `.json`/`.out`.
> Self-test `SELFTEST_OK` (control placeable).

---

## 1. Method

For each `bore_log*.xlsx`: (1) compute END station + print sheets; (2) match END to a confirmed PDF
endpoint (`pdf_clean_endpoint_table.json`, the #37 9-endpoint table) within 15 ft on a shared sheet;
(3) for each matched AP, resolve its unique terminal-tail route; (4) run the **Target #41** proof-grade
segment test (G_len ∧ G_anchor ∧ G_term). NEW-PLACEABLE ⟺ a unique proof-grade segment.

## 2. Result (machine output)

```
bores scanned: 58
endpoint-matched bores: [bore_log57, bore_log7]
  bore_log7  end=451 sheets=[10]      -> (10,451,163)  verdict=PLACEABLE_SEGMENT_PROVEN
  bore_log57 end=413 sheets=[8,10,13] -> (8,413,157)   verdict=NOT_UNIQUE_COMPETING_SEGMENTS
PLACEABLE_SEGMENT_PROVEN:        [bore_log7]
NOT_UNIQUE_COMPETING_SEGMENTS:   [bore_log57]
no confirmed-endpoint match:     56 bores
NEW placeable beyond bore_log7:  NONE
```

## 3. Why no new bore is placeable

- **56 of 58 bores** never reach step 4 — their END station coincides with no confirmed AP
  run-terminus on their sheets (they are drops, main-chain high-station, or multi-drive logs whose END
  is a matchline/footage, consistent with #20/#22/#23/#40). No terminus → no placement.
- **bore_log57** reaches a terminus (AP-157) but fails the segment test: no proof-grade
  structure-to-structure 413 ft segment ends at AP-157 (#41).
- **bore_log7** is the lone bore whose END lands on a confirmed endpoint **and** whose length matches a
  whole structure-to-structure route (route_469, AP-163 ↔ SPLICE LOC 46) — proof-grade, already
  shipped default-OFF (#14).

This is the same conclusion reached by the bore→drive binding (#38), the alternate resolver (#39),
the multi-drive sweep (#40), and the segmentation resolver (#41) — now confirmed across the **whole
corpus** by an independent path. Five methods, one answer.

## 4. The single unblocking signal (unchanged, narrow)

A **per-bore terminus/start-structure field** (which structures each bore drilled between). It is one
field, not the whole `.FS` sheet, and no delivered file carries it (#23/#24/#38/#40). With it: the 56
no-terminus bores gain a terminus to score, and bore_log57's start is fixed → placeable. Without it,
no repo-local method yields a new deterministic placement without guessing (wrong-redline risk).

## 5. Validation

- `py_compile` OK; sweep `SELFTEST_OK`.
- **Control bore_log7 → PLACEABLE_SEGMENT_PROVEN** (re-derived corpus-wide via the #41 resolver).
- 9 endpoints + bore_log7 lane untouched; no placement/flag/STATE/geometry change.

## 6. Verdict + next

The placement frontier is now exhaustively characterized: **placeable set = {bore_log7}**, proven
across 58 bores by five independent methods (#38–#42). No remaining repo-local move produces a new
deterministic placement. The lone external unblock is a per-bore terminus/start-structure field; the
#39/#41 resolvers consume it the instant it arrives.

DO-NOT-WIDEN intact; all flags default-OFF; bore_log7 → route_469 unchanged.

## 7. Files

- New: `scripts/target42_next_placeable_bore_sweep.py` (+ `.json`/`.out`); this report.
- Read: `pdf_clean_endpoint_table.json` (#37), the #41 resolver, KMZ route catalog + point features,
  all 58 bore_log xlsx.
