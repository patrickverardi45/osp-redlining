# Target #37 — Primitive-A STA 355 abstention: root cause, fix, and AP-164 promotion (default-OFF, read-only)

**Mission:** diagnose why Primitive A abstains at STA 355 (AP-164) while Primitive B recovers it
(Target #36), fix it safely if possible, validate against the 7 confirmed endpoints + the AP-167
control, and give AP-164 a final status — then continue toward placement.

**VERDICT: ROOT-CAUSED + FIXED. AP-164 → `PROMOTE_TRUSTED`.** Primitive A abstained on a **phantom
competitor**: at the AP-164 PORT block a stray "110" digit cluster (coinciding with a valid AP id
but sitting 42 px from any TERMINAL/PORT label, near a FLOWER POT) fell inside A's 1.4× distance
margin and triggered a false `ambiguous_164_vs_110`. The fix makes A's ambiguity gate
**terminal-port-anchored**: a within-margin competitor only blocks if it is itself within 18 px of a
TERMINAL/PORT label (a real AP terminal sits ~6 px). The fix is precision-safe — it **only ever adds
`None→ap` resolutions**, never changes or drops an AP. Recall **0.70 → 0.90**, precision **1.00**,
wrong-id **0**. AP-164 promoted to the 8th confirmed endpoint; **AP-155@3810 recovered as a 9th**
(also a real hand-table run-endpoint); a new sheet-13 review candidate (AP-158@245) surfaced. The 7
baseline endpoints + bore_log7 lane are untouched.

> Read-only/default-OFF: the patched extractor is a pure `scripts/` shadow — **backend imports none
> of it** (verified). No flag, STATE, geometry, placement, or production path changed. Validation:
> `scripts/target37_validation.py` (legacy-vs-patched diff) + extractor selftest + #32/#33 grades.

---

## 1. Root cause (exact)

Instrumented Primitive-A internals at sheet 12 STA 355 (`scripts/target37_sta355_primitive_a_diag.py`):

```
STA '3+55' @ (533,350) → nearest struct 'PORT' @ (525,362) d=14.2px (type=ap)
_recover_ap → ap_id=None  reason=ambiguous_ap_164_vs_110
   candidates = [(164, 33.9px), (110, 42.5px), (110, 426px)]
```

The ambiguity gate `cand[1].dist < AP_UNIQUE_MARGIN * cand[0].dist` fired: `42.5 < 1.4 × 33.9 = 47.5`
→ abstain. But the "110" competitor is a **phantom**, proven three ways:

| evidence | value |
|---|---|
| "110" cluster distance to nearest TERMINAL/PORT label | **42.5 px** (real APs: AP-164 = 6.4 px, AP-167 = 6.1 px) |
| "110" cluster distance to nearest FLOWER label | 36.2 px (it is a flower-pot-region number) |
| AP-110's real KMZ Terminal Port HH node | lat **30.1527** — ~900 ft south of sheet-12's terminal cluster (30.160) |

So the sheet-12 "110" is a pipe-dimension / footage that coincides with a valid AP id; it is **not**
AP-110's terminal. Primitive B already resolves this correctly (AP-164 is in the PORT's own vector
component; "110" is not → B verdict `recovered`, comp_ap 164). A's pure-Euclidean ambiguity test had
no component/anchor awareness, so a phantom within the distance margin produced a false abstention.

## 2. The fix (deterministic, auditable, minimal blast radius)

[scripts/pdf_run_endpoint_extractor.py](scripts/pdf_run_endpoint_extractor.py) — `_recover_ap`:
a within-margin **second** candidate of a different id only counts as a true ambiguity if it is
itself **terminal-port-anchored** (within `AP_TERMINAL_ANCHOR_TOL = 18 px` of a TERMINAL/PORT word).
A non-anchored phantom is rejected with reason `unique_phantom_competitor_<id>_rejected`; `near`
stands. New pure helper `_terminal_port_anchored(cx, cy, terminal_port_words)`; the call site passes
the sheet's TERMINAL/PORT labels. Backward compatible: when `terminal_port_words` is None the legacy
behavior is exact.

**Why 18 px:** real AP-terminal numbers sit ~6 px from their TERMINAL/PORT label (measured: 6.1–6.4
px); phantoms sit 40+ px. 18 px separates the two classes with wide margin on both sides — not fit to
a single case. **Why precision-safe (proven, not asserted):** the change can only *remove* a
phantom-induced abstention; it never alters which AP is `near`, and a genuine competing terminal
(its own number ~6 px from a TERMINAL/PORT) is still anchored → true ties still abstain.

## 3. Validation (vs 7 confirmed + AP-167 control)

`scripts/target37_validation.py` runs the **real** extractor twice per sheet 8–14 (toggling only
`_terminal_port_anchored`) and diffs the AP record sets:

```
ADDED (None→ap)        = (9,3810,155 ✓hand) (12,355,164 ✓hand) (13,245,158 ✗hand→review)
REMOVED (ap→None)      = []        ← fix never drops a resolution
CHANGED-ID (ap→other)  = []        ← fix never changes an AP id
baseline 7 retained    = True      ← incl. AP-167@350 (the control) and AP-168@189
```

Authoritative grade (`scripts/pdf_clean_endpoint_table.py`, the #33 gate = B-confirmed ∧
reconstructed ∧ full TERMINAL+PORT+SPLICE phrase ∧ not-matchline):

```
TRUSTED-CONFIRMED (9) = 154 156 157 (sh8) · 155 (sh9) · 165 163 (sh10) · 168 (sh11) · 167 164 (sh12)
WRONG IDs (0)         = []
MISSES (1)            = (10,136,166)        # AP-166 glyph floor (not chased — out of scope)
TRUSTED-REVIEW (2)    = (13,245,158) (13,359,160)
PRECISION = 1.00   RECALL = 0.90   (was 0.70)
```

Notes:
- The raw-Primitive-A record `(11,189,139)` is **pre-existing** (present in both legacy and patched;
  not added by this fix) and is filtered before the confirmed tier by the #33 gate — the authoritative
  confirmed grade is WRONG-ID = 0, with AP-168@189 confirmed.
- Extractor selftest extended with a **phantom-competitor** case (AP-164 recovered past a non-anchored
  "110") and a **true-tie** case (two anchored APs still abstain): `SELFTEST_OK`.

## 4. AP-164 final classification

```
AP-164 (sheet 12, STA 355) : PROMOTE_TRUSTED
```
A now returns 164 (phantom "110" rejected) → A∧B agree (both 164) → B verdict `confirmed` → passes
all four #33 gates → 8th confirmed endpoint, in the hand table, geometry-ready (route_468, lat/lon).

## 5. Bonus + new review (same fix)

- **AP-155 (sheet 9, STA 3810) → PROMOTE_TRUSTED (9th confirmed).** Also a real hand-table run-endpoint
  that was abstaining on a phantom competitor. (Note: this is the AP *endpoint*; the Target #22
  main-chain BORE blocker for bore_log16/43 at stations 4000–5950 is unchanged — AP-155@3810 does not
  anchor those bores, and no new bore placement match appears.)
- **AP-158 (sheet 13, STA 245) → TRUSTED-REVIEW.** Newly surfaced, geom-valid, absent from the hand
  reference on boundary sheet 13 — same tier/blocker as AP-160 (Target #35). NOT auto-confirmed.

## 6. Placement impact

`scripts/pdf_clean_endpoint_table.json` placement block unchanged: bore_log7 → AP-163 (PLACEMENT_READY)
and bore_log57 → AP-157 (candidate, still bore→drive blocked per #34). The two new confirmed endpoints
(AP-155, AP-164) add **no** new bore placement match (no bore's (print, end-station) uniquely lands on
them within tol). So recall improved with **zero** wrong-redline exposure.

## 7. Files changed + validation run

- **Code (rewritten):** [scripts/pdf_run_endpoint_extractor.py](scripts/pdf_run_endpoint_extractor.py)
  — `_recover_ap` phantom-competitor gate + `_terminal_port_anchored` helper + call-site wiring +
  extended selftest.
- **Regenerated read-only shadow artifacts:** `scripts/pdf_clean_endpoint_table.{json,out}` (9 confirmed),
  `scripts/pdf_endpoint_table_8_14.{json,out}`.
- **New:** `scripts/target37_sta355_primitive_a_diag.py`, `scripts/target37_validation.py` (+ `.json`/`.out`),
  this report.
- **Validation:** `py_compile` OK; extractor `selftest` → SELFTEST_OK; `target37_validation` → 0 removed,
  0 changed-id, baseline 7 retained, SELFTEST_OK; #33 grade precision 1.00 / recall 0.90 / wrong-id 0.
- **Untouched:** backend / web / tests / flags / STATE / geometry / placement (extractor is scripts/-only,
  imported by no backend module — verified).

## 8. Verdict + next target

Primitive-A's STA-355 abstention is root-caused (phantom competitor) and fixed (terminal-port-anchored
ambiguity gate); AP-164 promoted, AP-155 recovered, recall 0.70 → 0.90 at precision 1.00 with zero
wrong-redline exposure. **Next:** the remaining recall miss (10,136,166) is the AP-166 glyph floor
(out of scope). With the endpoint table now at 9 trusted, the highest-value move toward *placement* is
the **bore→drive binding** that blocks bore_log57 (Target #34) — pursue any deterministic
disambiguation of its multi-drive END, validated against the bore_log7 control, default-OFF.
DO-NOT-WIDEN intact; all flags default-OFF.
