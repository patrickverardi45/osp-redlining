# Target #34 — bore_log57 PDF-derived placement candidate (default-OFF, read-only)

**Mission:** the first trusted PDF-derived redline *placement attempt beyond bore_log7*. Using ONLY
the Target #33 clean endpoint table (7 trusted endpoints, precision 1.00, 0 wrong IDs) + the
Target #25 AP/structure index + existing route geometry, determine whether **bore_log57 → AP-157**
can be safely auto-placed as a redline **without guessing**.

**VERDICT: bore_log57 is NOT safely placeable yet — ABSTAIN.** The *structure side* (AP-157 →
route_465, lat/lon) is clean and geometry-ready; the Target #33 cleanup did resolve the
endpoint-side ambiguity. But the *bore-side drive-disambiguation* is unresolved on **three
independent, machine-readable counts**, so binding bore_log57's END to AP-157 (rather than the
co-located sheet-13 corridor) would be a guess → wrong-redline risk. No placement performed; no
override created (an override would have to guess). **bore_log7 control re-verified PLACEMENT_READY
→ route_469 — not degraded.**

> Read-only. Pure-helper reuse; isolated in `scripts/`; no engine import-as-production, no flag,
> no STATE, no geometry write, no placement. Adjudicator
> `scripts/target34_bore_log57_placement_candidate.py` → `.json`/`.out`. Self-test `SELFTEST_OK`.

---

## 1. Placement-readiness gate (the bore_log7 proof shape)

A bore is `PLACEMENT_READY` only if **all four** hold (else `ABSTAIN` with the failing gate IDs):

| gate | meaning | source |
|---|---|---|
| **G1** structure_side_trusted | bore END station matches EXACTLY ONE confirmed PDF-derived AP endpoint (Target #33 clean table) within 15 ft, AND that AP is `geometry_anchor_ready` in the Target #25 index (lat/lon + terminal-tail route) | `pdf_clean_endpoint_table.json` + `ap_structure_index.json` |
| **G2** single_corridor | matchline-graph status is NOT `multi_corridor_span` | `brenham_plan_sheet_graph.evaluate_bore_log` |
| **G3** no_competing_terminus | no competing UNNAMED run terminus (matchline/splice/flower pot) within 15 ft of the END on the bore's print sheets | `BRENHAM_PH5_RUN_ENDPOINTS` |
| **G4** print_mapping_certain | the bore's own notes do NOT flag "print mapping uncertain" | bore xlsx notes |

G1 is the structure-side analogue of the shipped `resolve_terminal_tail_route_for_ap`; **G2–G4 are
the bore→drive binding** that makes the END uniquely belong to that AP's drive/corridor. A clean
structure side (G1) is **necessary but not sufficient** — exactly the gap Target #23 named.

## 2. Result (live re-derivation, TOL = 15 ft)

```
Confirmed PDF-derived endpoints (Target #33): 7 ->
  (8,366,154) (8,387,156) (8,413,157) (10,140,165) (10,451,163) (11,189,168) (12,350,167)

[bore_log57]  TARGET                                   G1=T  G2=F  G3=F  G4=F  => ABSTAIN
[bore_log7]   CONTROL (proven -> route_469)            G1=T  G2=T  G3=T  G4=T  => PLACEMENT_READY
```

## 3. bore_log57 — structure side IS ready (deliverable: exact route candidate)

| field | value | source |
|---|---|---|
| bore END station | 413 ft | bore_log57.xlsx (10 rows, sta 0–413) |
| confirmed endpoint hit (unique) | (sheet 8, sta 413, **AP-157**) | Target #33 clean table |
| AP-157 lat/lon | **30.15819527, −96.38598520** | Target #25 index |
| AP-157 terminal-tail route | **route_465** | Target #25 index |
| AP-157 KMZ folder | Nodes / Terminal Port Handhole | Target #25 index |
| coverage | fs ✓ · station ✓ · latlon ✓ · tail ✓ (complete) | Target #25 index |

**Exact route candidate for AP-157 = `route_465`** (the unique terminal-tail route at AP-157's
node). The structure side is *more* complete than the proven AP-163 (which lacks `.FS`). If a
bore→drive binding existed, this is precisely the lat/lon + route a placement step would consume.

## 4. bore_log57 — bore side is NOT disambiguated (deliverable: drive-ambiguity status)

The END (sta 413) does not uniquely belong to AP-157's drive. Three independent blockers, all
re-derived live:

1. **`competing_unnamed_terminus_within_tol`** — END 413 is within tol of BOTH the named AP-157
   run terminus (sheet 8) **and** a sheet-13 **matchline at sta 398** (|413−398| = 15). The
   Target #33 cleanup removed that matchline from the *trusted AP table*, but the matchline still
   physically exists near the END — so it remains a competing place the bore's END could fall on.
2. **`multi_corridor_span`** — bore_log57 spans **two independent chainage corridors**:
   `[3,4,5,6,7,8,9,23,24]` (via print 8, where AP-157 lives) and `[10,12,13,14]` (via prints 10/13).
   The END frame is not bound to AP-157's corridor.
3. **`print_mapping_flagged_uncertain`** — the bore's own notes: *"Segment A (col1) split from
   bore_log24.xlsx … NEEDS REVIEW: print mapping uncertain — preserved full source print
   '8,10,13'."* The print→corridor assignment that would localize the END is explicitly untrusted.

**Drive-disambiguation status: INSUFFICIENT.** The structure-side cleanup (Target #33) is
necessary but not sufficient; it cannot answer which corridor/drive bore_log57's END terminated on.

## 5. Machine-readable blocker

```json
{
  "bore": "bore_log57",
  "verdict": "ABSTAIN",
  "gates": {"G1_structure_side_trusted": true, "G2_single_corridor": false,
            "G3_no_competing_terminus": false, "G4_print_mapping_certain": false},
  "structure_side": {"resolved_ap": 157, "tail_route": "route_465",
                     "latlon": [30.15819527, -96.38598520], "geometry_ready": true},
  "blockers": ["multi_corridor_span", "competing_unnamed_terminus_within_tol",
               "print_mapping_flagged_uncertain"],
  "missing_artifact": ".FS drive-decomposition sheet OR per-bore terminus-structure/direction field"
}
```

The missing artifact is the **`.FS` Fiber-Schematic / drive-decomposition sheet** (or a per-bore
terminus/direction field) — the same artifact named in Target #23/#24, absent from all provided
Brenham sources. This is a stated abstain-with-exact-reason, **not** a reopening of the missing-data
investigation: the structure side is solved; only the bore→drive edge is missing.

## 6. Why no override was created

Deliverable #4 ("if safe, create a default-OFF placement shadow/override candidate") is **not**
triggered — bore_log57 is not safe. Any override would have to choose AP-157's corridor over the
sheet-13 corridor with no evidence = guessing, which DO-NOT-WIDEN forbids. The correct artifact is
the abstaining adjudicator (deliverable #5), which emits the blocker and stops. Unlike bore_log7
(Target #14), there is no unique, unambiguous anchor to place on.

## 7. Control: bore_log7 not degraded

bore_log7 (print [10], sta 55–451) passes **all four gates** → `PLACEMENT_READY`, re-deriving
**route_469** (single corridor `[10,12,13,14]`, unique AP-163 terminus, no competing terminus,
no uncertain-print flag). This proves the gate is correctly calibrated (it admits the one proven
case) and that this work does not touch the shipped bore_log7 lane. Hard self-assertions in the
probe fail loudly if either invariant breaks.

## 8. Safety posture

- **No placement, no override, no geometry write, no flag, no STATE, no engine import-as-production.**
- Read-only adjudication over committed trusted artifacts (`pdf_clean_endpoint_table.json`,
  `ap_structure_index.json`) + read-only bore xlsx; isolated in `scripts/`.
- **0 wrong-redline risk:** the only `PLACEMENT_READY` is the already-proven bore_log7.
- No AP-166 chase; no broadened extraction; no missing-data re-investigation.
- Self-test `python scripts/target34_bore_log57_placement_candidate.py` → `SELFTEST_OK`.

## 9. Verdict + next target

bore_log57 is the first NEW candidate the PDF-extraction chain *enabled* on the structure side, and
this target confirms that side is genuinely placement-grade (AP-157 → route_465, lat/lon known).
The remaining blocker is purely the bore→drive binding (3 machine-readable reasons), which needs the
`.FS` drive-decomposition sheet or a per-bore terminus/direction field — neither in the current
files. **bore_log57 abstains; bore_log7 unchanged.**

Next:
1. **Adjudicate the single TRUSTED-REVIEW endpoint (13, 359, AP-160)** from Target #33 (hand
   omission vs subtle false positive) — pure structure-side, no bore dependency.
2. If/when the `.FS` sheet (or a bore terminus/direction field) is acquired, this adjudicator
   resolves bore_log57 to AP-157 → route_465 with **zero re-mining** (G1 already green; the artifact
   flips G2–G4).
3. The 7-endpoint clean table remains the structure-side input for a future, separately-authorized
   default-OFF placement shadow for `PLACEMENT_READY` bores (today: only bore_log7).

DO-NOT-WIDEN intact; all flags default-OFF; proven lane unchanged (bore_log7 → route_469).

## 10. Files

- Read: `scripts/pdf_clean_endpoint_table.json` (#33), `scripts/ap_structure_index.json` (#25),
  `BRENHAM_PH5_RUN_ENDPOINTS` ([pdf_ap_route_resolver.py:989](backend/app/core/pdf_ap_route_resolver.py#L989)),
  [brenham_plan_sheet_graph.py](backend/app/core/brenham_plan_sheet_graph.py), bore_log57/bore_log7 xlsx (read-only).
- Wrote: `scripts/target34_bore_log57_placement_candidate.py` + `.json` + `.out`; this report.
