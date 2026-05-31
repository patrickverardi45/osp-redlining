# Target #23 — Remaining route_480 Bucket Review (deterministic verdict table) — READ-ONLY

**Scope:** the 6 still-unproven route_480-bucket logs (bore_log57; bore_log29/31/46/47/58).
**Verdict: 0 PROVEN · 0 PARTIAL · 6 BLOCKED.** No remaining log can be proven from existing
source evidence; each has a named missing artifact.

This is the goal-schema review of the deterministic sweep already shipped at
`scripts/route480_remaining_proof_sweep.py` → `.out` (commit `de6b7b0`); see also the long
form `gac/route480_remaining_proof_sweep.md`. Read-only — no placement, no flag, no engine
change. Evidence below is verbatim from the probe (in-repo run-endpoint table +
`brenham_plan_sheet_graph` matchline graph + read-only bore xlsx; TOL = 15 ft).

## Method (three lanes, one deterministic probe)

The three goal lanes are encoded in one probe rather than spawned as agents — the proof gate
is a table lookup, so determinism beats parallel narration:
- **L1 bore facts** — prints, station min/max/span, rows, notes/crew (real xlsx).
- **L2 PDF/run graph** — every `BRENHAM_PH5_RUN_ENDPOINTS` terminus within 15 ft of the bore
  END on its print sheets, + matchline-graph corridor membership/extent.
- **L3 KMZ/route** — a KMZ route binding is reachable ONLY if L2 yields a UNIQUE, unambiguous
  named-AP terminus (the bore_log7 mechanism).

**Proof gate (adversarial):** PROVABLE requires exactly ONE named-AP terminus within tol AND
no competing terminus (named or unnamed matchline/splice) AND a single corridor AND a
non-flagged print mapping. A bare named-AP hit is insufficient — a co-located matchline or a
multi-corridor span makes the END frame-ambiguous.

## Deterministic verdict table

| source_file | current blocker | source evidence found | PROVEN/PARTIAL/BLOCKED | exact missing relationship | next action |
|---|---|---|---|---|---|
| **bore_log57.xlsx** | multi_drive_terminus_ambiguous | prints 8,10,13; sta 0–413; END 413 hits **AP-157@413 (sh8)** AND **matchline@398 (sh13)**; spans corridors {3..9} & {10,12,13,14}; notes: split from bore_log24, "print mapping uncertain" | **BLOCKED** | `.FS` drive-decomposition (which drive/terminus the bore ends at) + print-mapping disambiguation | acquire `.FS` sheet; do not bind to AP-157 (matchline competes) |
| **bore_log29.xlsx** | no_run_terminus_match | prints 10,12; sta 0–415; END 415 hits NO run terminus ≤15 ft (sh10/12 termini at 136/140/189/350/355/451/507/510/514); corridor {10,12,13,14} | **BLOCKED** | `.FS` drive-decomposition OR a per-bore terminus-structure field | acquire `.FS`/terminus field |
| **bore_log31.xlsx** | no_run_terminus_match | prints 10,12; sta 0–260; END 260 hits NO run terminus ≤15 ft; corridor {10,12,13,14} | **BLOCKED** | `.FS` drive-decomposition OR a per-bore terminus-structure field | acquire `.FS`/terminus field |
| **bore_log46.xlsx** | no_run_terminus_match | prints 10,13,14; sta 0–534; END 534 = **AP-161 LABEL, not a run terminus → excluded** (Target #10 anti-artifact rule); split of bore_log18 | **BLOCKED** | `.FS` drive-decomposition OR a per-bore terminus-structure field | acquire `.FS`/terminus field |
| **bore_log47.xlsx** | no_run_terminus_match | prints 10,13,14; sta 325–494 (span 169); END 494 hits NO run terminus ≤15 ft; split of bore_log18 | **BLOCKED** | `.FS` drive-decomposition OR a per-bore terminus-structure field | acquire `.FS`/terminus field |
| **bore_log58.xlsx** | no_run_terminus_match | prints 8,10,13; sta 0–256; END 256 hits NO run terminus ≤15 ft; spans 2 corridors; split of bore_log24 | **BLOCKED** | `.FS` drive-decomposition OR a per-bore terminus-structure field | acquire `.FS`/terminus field |

## Why none are PROVEN/PARTIAL

- **bore_log57** has a named terminus (AP-157) but it is NOT unique: a sheet-13 matchline at
  398 sits within tol of the same END (413), the bore crosses two independent chainage
  corridors, and its own notes flag the print mapping as uncertain. The 413 terminus cannot
  be bound to AP-157 vs the matchline without a drive decomposition → ambiguous, not partial.
- **bore_log29/31/46/47/58** are continuous multi-drive bores (local 0+00 frames; 4 of 5
  start at 0) whose END hits no single `DIR.BORE` run terminus. bore_log46's 534 coincides
  only with the AP-161 *label* (not a run end), correctly rejected.

## Exact missing relationship (uniform, named, proven-absent)

The **`.FS` Fiber-Schematic / drive-decomposition sheet** mapping each multi-drive bore's
station sub-ranges → drive → terminating structure. It is referenced by the Fieldwire
register (`AP-155 .FS 9`, `AP-168 .FS 11`, Target #8) but is **ABSENT from all 3 Brenham
PDFs** (re-confirmed by the Target #22 corpus sweep: no `*fiber*`/`*schematic*`/`.FS` file in
the wiki tree). Equivalently, a per-bore terminus/AP/direction column on the bore xlsx would
resolve it — the xlsx carries only station/depth/boc/date/crew/print/notes.

## Bucket closeout (durable)

All 14 route_480-bucket logs are now classified — 1 PROVEN (bore_log7 → route_469), 13
BLOCKED on exactly 3 acquisition artifacts: flower-pot identity key (DROP ×5, Target #20),
high-station anchor + direction (main-chain ×2, Target #22), `.FS` drive-decomposition
(multi-drive ×6, this target). **No route_480 log is provable from the current files.**

## Next blocker

Acquire the **`.FS` drive-decomposition sheet** for Brenham PH5 — the single highest-leverage
artifact (unblocks these 6 plus the DROP lane's multi-drive ambiguity). No code helper falls
out until it exists (a shadow would abstain on 100% of inputs, per Targets #20/#22).
DO-NOT-WIDEN intact; proven lane unchanged; all flags default-OFF.
