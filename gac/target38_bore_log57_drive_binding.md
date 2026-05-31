# Target #38 — bore_log57 bore→drive binding: final adjudication (default-OFF, read-only)

**Mission (auto-continued from #37):** with the endpoint table now at 9 trusted, drive toward
*placement* by resolving the bore→drive binding that blocks bore_log57 (whose AP side — STA 413 →
AP-157 → route_465 — is geometry-ready). Exhaust every repo-local deterministic signal; place if
provable, else declare the exact hard blocker.

**VERDICT: `HARD_BLOCKED`.** Every repo-local disambiguation signal was tested and none binds
bore_log57's END to a single drive/corridor without guessing. The structure side is now even
cleaner — the sheet-13 "@398" competitor is a **MATCHLINE** (a sheet-continuation boundary, not a
physical terminus a bore can end at), so **AP-157 is the sole confirmed real-structure terminus**
near the END. But the bore→drive binding remains unresolved, and the only artifact that could
resolve it — the `.FS` drive-decomposition sheet — is **proven absent (Targets #23/#24) with no
extraction path**. Placing on AP-157 anyway would risk a wrong redline a whole corridor away.
**bore_log57 abstains (DO-NOT-WIDEN). bore_log7 control remains PLACEABLE.**

> Read-only; pure-helper reuse; `scripts/` only; no flag/STATE/geometry/placement.
> Probe `scripts/target38_bore_log57_drive_binding.py` → `.json`/`.out`. Self-test `SELFTEST_OK`.

---

## 1. Signals tested (all repo-local, no guessing)

| signal | bore_log57 | bore_log7 (control) |
|---|---|---|
| **S1** per-row print binds END to one sheet | **NO** — every row carries the uniform union `8,10,13` (empirically dumped; no per-row drive signal) | yes — single sheet `10` |
| **S2** single matchline-graph corridor | **NO** — spans `[3,4,5,6,7,8,9,23,24]` (sheet 8 / AP-157) AND `[10,12,13,14]` | yes — `[10,12,13,14]` |
| **S3** exactly one confirmed REAL-structure terminus near END | yes — `(8, 413, AP-157)`; the `(13, 398)` competitor is a **matchline, not a terminus** | yes — `(10, 451, AP-163)` |
| **S4** single `0+00→END` drive to the AP | **NO** — multi-drive (Targets #9/#10); 413 is a run-end *value*, not a single 0→413 drive | n/a (proven placement) |

**Placement requires** S2 (single corridor) ∧ S3 (one real terminus) ∧ (S1 per-row bind ∨ S4
single-drive). bore_log57 passes S3 only → **HARD_BLOCKED**. bore_log7 passes S1∧S2∧S3 → PLACEABLE.

## 2. Matchline reclassification (a refinement, not a fix)

Target #34's third blocker was a "competing_unnamed_terminus" — the sheet-13 `@398`. This probe
reclassifies it correctly: `(13, 398)` is typed **matchline** in `BRENHAM_PH5_RUN_ENDPOINTS`. A
matchline is where the *drawing* continues to the next sheet — **not** a physical structure a bore
can terminate at. A bore ends at a handhole/flower-pot/splice. So the matchline is **not** a
competing terminus; AP-157 is the unique real-structure terminus near bore_log57's END. This
*removes* one of #34's three blockers — but does **not** make the bore placeable, because the
remaining blockers (multi-corridor span + uniform-union print + uncertain print + multi-drive END)
still prevent a no-guess binding of the END to AP-157's corridor.

## 3. Missing artifact — proven absent, no extraction path

Per the goal's standard ("do not claim missing data unless exact artifact absence is proven and no
extraction path exists"):

1. **`.FS` Fiber-Schematic / drive-decomposition sheet** — the only artifact mapping a multi-drive
   bore's station sub-ranges → drive → terminating structure. **ABSENT** from all 3 Brenham PDFs and
   the full corpus (Target #23 per-log sweep + Target #24 full-inventory hunt over 71 xlsx + the
   80-pg Fieldwire register + 539-route JSON + KMZ + golden fixtures). The Fieldwire register
   *references* `.FS` pages (`AP-155 .FS 9`) but the pages themselves are not delivered.
2. **Per-bore terminus/direction field** — the bore xlsx carries only station/depth/boc/date/crew/
   print/notes (Target #23). Re-verified here: the only print field is the **uniform union**
   `8,10,13` on every row — it does not bind a drive.
3. **PDF bore→run link** — the PDFs contain **no bore_log id anywhere** (Targets #8/#24), so the
   plan sheets cannot say which physical bore drilled the AP-157 run.

No repo-local analysis, code, or test can supply this binding. Any binding would be a guess, and a
wrong guess places bore_log57's redline an entire corridor away from its true path. → **HARD_BLOCKED.**

## 4. Placement frontier (honest status)

The PDF-derived placement lane is now characterized end-to-end:

| bore | AP side | bore→drive | placement |
|---|---|---|---|
| **bore_log7** | AP-163 → route_469 (ready) | single corridor, single drive, unique terminus | **PLACEABLE** (shipped default-OFF, Target #14) |
| **bore_log57** | AP-157 → route_465 (ready) | multi-corridor, multi-drive, uniform-union print | **HARD_BLOCKED** (.FS absent) |
| other 12 route_480 logs | drops / main-chain / multi-drive | — | BLOCKED on proven-absent artifacts (#20/#22/#23) |

No bore's `(print, end-station)` matches the two newly-confirmed endpoints (AP-155@3810, AP-164@355),
so #37's recall gain added **zero** new placement candidates (and zero wrong-redline exposure). The
PDF-AP independent placement lane yields exactly **one** deterministically placeable bore (bore_log7);
expanding to more requires the `.FS` sheet.

## 5. Validation

- `py_compile` OK; probe `SELFTEST_OK` (control bore_log7 PLACEABLE; target bore_log57 HARD_BLOCKED).
- bore_log7 lane + the 9 confirmed endpoints untouched; no flag/STATE/geometry/placement change.

## 6. Verdict + machine-readable blocker

```json
{
  "bore_log57_classification": "HARD_BLOCKED",
  "ap_side": "STA413 -> AP-157 -> route_465 (geometry-ready)",
  "machine_reason": "bore_to_drive_binding_unresolved: per_row_print_uniform_union_no_signal + multi_corridor_span + print_mapping_uncertain + end_is_multi_drive",
  "missing_artifact": ".FS drive-decomposition sheet (proven absent #23/#24; no extraction path)",
  "control_bore_log7": "PLACEABLE"
}
```

This is a **hard blocker that no repo-local analysis, code, or test can resolve** — the FINISH-MODE
stop condition. The single artifact that unblocks bore_log57 (and the 6 multi-drive route_480 logs)
is the `.FS` Fiber-Schematic / drive-decomposition sheet, which must be acquired (it exists — the
Fieldwire register references it — but was not delivered in the packet).

## 7. Files

- Read: `scripts/pdf_clean_endpoint_table.json` (#37, 9 confirmed), `BRENHAM_PH5_RUN_ENDPOINTS`,
  `brenham_plan_sheet_graph.py`, bore_log57 xlsx (read-only, per-row).
- Wrote: `scripts/target38_bore_log57_drive_binding.py` + `.json` + `.out`; this report.
