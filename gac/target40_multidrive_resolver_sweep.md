# Target #40 — alternate resolver sweep over the multi-drive route_480 logs (no `.FS`)

**Mission (auto-continued from #39):** apply the Target #39 alternate bore→drive resolver (delivered
signals only, no `.FS`) to the remaining multi-drive route_480 logs (29/31/46/47/58), enumerate
candidate termini per log, and report verdicts. bore_log57 (#39) + bore_log7 (control) included.

**VERDICT: 0 new placements; the resolver places nothing beyond the proven bore_log7.** All six
multi-drive logs → `HARD_BLOCKED_NO_DISCRIMINATOR`, each with explicit per-log evidence. **Five
(29/31/46/47/58) have NO real-structure terminus at their END** (the END coincides with a
matchline/footage, not a handhole) — the resolver can't even name a terminus. **bore_log57** alone
has a uniquely-resolved terminus (AP-157) but is geometry-blocked (#39). The control bore_log7 →
PLACEABLE_BY_ALTERNATE_RESOLVER (re-derives the proven AP-163 → route_469). This deterministically
answers "expand from one placement-ready case to multiple" — **not possible from the delivered
files**, proven (not assumed), with no wrong-redline risk.

> Read-only; reuses the #39 resolver verbatim; `scripts/` only; no `.FS`, no flag/STATE/geometry/
> placement. Driver `scripts/target40_multidrive_resolver_sweep.py` → `.json`/`.out`. `SELFTEST_OK`.

---

## 1. Per-log result

| log | END | sheets | candidate terminus | G1 unique | G2 len | G3 corridor | G4 print | verdict |
|---|---|---|---|---|---|---|---|---|
| bore_log29 | 415 | 10,12 | **none** | ✗ | ✗ | ✓ | ✓ | HARD_BLOCKED |
| bore_log31 | 260 | 10,12 | **none** | ✗ | ✗ | ✓ | ✓ | HARD_BLOCKED |
| bore_log46 | 534 | 10,13,14 | **none** (AP-161@534 is a label, not a run terminus) | ✗ | ✗ | ✓ | ✗ | HARD_BLOCKED |
| bore_log47 | 494 | 10,13,14 | **none** | ✗ | ✗ | ✓ | ✗ | HARD_BLOCKED |
| bore_log58 | 256 | 8,10,13 | **none** | ✗ | ✗ | ✗ | ✗ | HARD_BLOCKED |
| bore_log57 | 413 | 8,10,13 | **AP-157** (score 4.0) | ✓ | ✗ | ✗ | ✗ | HARD_BLOCKED (#39) |
| **bore_log7** (control) | 451 | 10 | **AP-163** (score 4.0) | ✓ | ✓ | ✓ | ✓ | **PLACEABLE** |

## 2. What the evidence says

- **29/31/46/47/58 — no terminus at the END.** Their END stations (415/260/534/494/256) do not land
  within tolerance of any real-structure run-terminus on their print sheets. The nearby plan features
  are matchlines (sheet boundaries) or footage callouts, not handholes. A bore physically terminates
  at a structure, so with no structure at the END the resolver cannot even name a candidate — let
  alone place. (Consistent with Target #23; bore_log46's 534 = AP-161 *label*, not a run terminus.)
- **bore_log57 — terminus resolved (AP-157), geometry blocked.** The single advance: a unique
  dominant terminus, but the tail-length gap (route_465 741.7 ft vs bore 413 ft) + multi-corridor
  span + uncertain print block proof-grade placement (full analysis in Target #39).
- **bore_log7 — PLACEABLE control.** The resolver independently re-derives the proven placement,
  confirming it is correctly calibrated and not over-eager.

## 3. Why nothing is placed (no wrong-redline risk)

Placement requires all four gates (terminus-unique ∧ tail-length-match ∧ single-corridor ∧
print-certain) — the shape that makes bore_log7 provable. No multi-drive log clears them: five lack a
terminus entirely; bore_log57 clears only the terminus gate. The resolver therefore abstains on all
six, emitting the exact failing gate(s) per log rather than guessing. **Expanding the placeable set
beyond bore_log7 is not achievable from the delivered corpus** — the resolver proves this
deterministically, which is a stronger statement than "we didn't find a way."

## 4. The single missing discriminator (corpus-wide)

For the five no-terminus logs, the END does not coincide with a handhole on the available sheets — the
missing signal is **where each multi-drive bore actually terminates** (a per-bore terminus/start
structure field, or the drive segmentation). For bore_log57 it is **which sub-segment of the tail**
(the 741-vs-413 length gap). Both reduce to the same class: **per-drive segmentation / endpoint
structure**, which is genuinely absent from every delivered file (Targets #23/#24/#38). It need not be
the `.FS` sheet specifically — a start-structure column on the bore log would also supply it — but no
delivered file carries it.

## 5. Validation

- `py_compile` OK; sweep `SELFTEST_OK` (control PLACEABLE; no log promoted past its true gate state).
- Reuses the #39 resolver unchanged; 9 endpoints + bore_log7 lane untouched; no placement/flag/STATE.

## 6. Verdict + next

The alternate-resolver lane is now exhausted across the entire multi-drive bucket: **1 terminus
advance (bore_log57 → AP-157), 0 new placements, control intact.** Combined with the blocked DROP lane
(#20), main-chain lane (#22), and the no-terminus logs here, **the deterministically-placeable set
from the delivered files is exactly one bore: bore_log7** (already shipped default-OFF, #14).

This is the genuine hard blocker: every remaining bore needs a per-drive terminus/segmentation signal
that no delivered file contains, and the resolver proves it rather than assuming it. The single
artifact that would unblock the bucket — a per-bore terminus/start-structure field (or the `.FS`
drive-decomposition sheet) — must be acquired. Until then, no further repo-local move produces a new
deterministic placement without wrong-redline risk. DO-NOT-WIDEN intact; all flags default-OFF.

## 7. Files

- New: `scripts/target40_multidrive_resolver_sweep.py` (+ `.json`/`.out`); this report.
- Read: the #39 resolver, KMZ route catalog + point features, `BRENHAM_PH5_RUN_ENDPOINTS`,
  `brenham_plan_sheet_graph`, bore_log 29/31/46/47/57/58/7 xlsx.
