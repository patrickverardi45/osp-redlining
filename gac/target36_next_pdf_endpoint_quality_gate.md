# Target #36 — next PDF endpoint-quality gate: the AP-164 adjacent-pair "miss" (default-OFF, read-only)

**Mission (auto-continued from Target #35):** pick the next safest pure structure-side
endpoint-quality improvement from the Target #32/#33/#34 outputs and adjudicate it. The chosen gate
is the **only non-AP-166 extraction-quality recall gap that is a REAL hand-table run-endpoint**:
`(sheet 12, STA 355, AP-164)`, recorded in Target #32 as "adjacent-pair contamination."

**VERDICT: `HARD_MISS_NEEDS_GUESS` — but the cause is precisely diagnosed and the #32 label is
CORRECTED.** AP-164 is **not** a label-adjacency collision (its on-sheet label is **489 px** from
AP-167's, not adjacent). It is a **Primitive-B `recovered`-only candidate**: a real, geometry-ready
hand-table run-endpoint that Primitive B found in the structure's vector component (full
TERMINAL+PORT+SPLICE phrase, role `run_end`, reconstructed), but **Primitive A abstained**
(`A_ap=None`) at STA 355 — so the **A∧B agreement that defines the `confirmed` tier is absent by
design**. It is therefore correctly excluded from the 7 placement-grade endpoints. It is **not**
recoverable under a no-widen structure-side gate without either a validated A-side fix or an
authorized trust-tier change. No promotion; precision stays 1.00; the 7 confirmed + bore_log7 lane
are untouched.

> Read-only diagnostic; pure-helper reuse (Primitive A/B/C + #30 reconstruction + #25 index);
> isolated in `scripts/`; no engine import-as-production, no flag, no STATE, no placement, no
> extractor rewrite. Probe `scripts/target36_ap164_adjacent_pair_gate.py` → `.json`/`.out`.
> Self-test `SELFTEST_OK`. Control: AP-167 @ 350 stays `confirmed`.

---

## 1. Why this gate (selection rationale)

The AP-terminal grade (Target #32/#33) is precision 1.00, recall 0.70, with three misses:

| miss | nature | actionable structure-side? |
|---|---|---|
| `(9, 3810, 155)` | high-station; **data-absence** (Target #22) — no station↔geometry anchor above 3810 | no (acquisition artifact) |
| `(10, 136, 166)` | AP-166 glyph/geometry floor | **forbidden to chase this session** |
| `(12, 355, 164)` | "adjacent-pair contamination" — a **real hand-table run-endpoint** the extractor missed | **yes — chosen** |

AP-164 is the lone safe, high-value target: it is in `BRENHAM_PH5_RUN_ENDPOINTS`, geometry-ready in
the #25 index (route_468, lat/lon), and recovering it would be a true-positive recall gain (0.70 →
0.80) — not a widening. No AP-166, no placement, no bore dependency.

## 2. Diagnosis (what the geometry actually shows)

| signal | STA 350 (AP-167, confirmed) | STA 355 (AP-164, miss) |
|---|---|---|
| Primitive A nearest-label | `A_ap = 167` | **`A_ap = None` (ABSTAINED)** |
| Primitive B leader verdict | `confirmed` | **`recovered`** (comp_ap = 164) |
| Primitive C run-role | `run_end` | `run_end` |
| Target #30 reconstructed | yes | yes |
| full TERMINAL+PORT+SPLICE phrase | yes | **yes** |
| reconstructed centroid | (980.6, 361.3) | (491.4, 368.5) |

**Centroid separation = 489 px.** The two AP labels are nowhere near each other on the sheet — the
"5 ft apart" in the #32 note is the **station-value** proximity (350 vs 355), not label adjacency.
So the #32 "adjacent-pair contamination" characterization is **incorrect**; this corrects it.

**Real mechanism:** Primitive A (positioned STA callout → nearest valid-AP digit cluster, excluding
the station's own value, abstain on tie/beyond-tol) returned **None** for STA 355 — an abstention.
Primitive B's component analysis independently recovered AP-164. Because A and B do not *agree*, the
leader verdict is `recovered`, not `confirmed`. The Target #33 gate admits only `confirmed`
(`verdict != "confirmed": continue`) — so AP-164 is excluded **by the trust design**, not by a bug.

## 3. Final classification

```
classification : HARD_MISS_NEEDS_GUESS   (precisely: PrimitiveB_recovered_only — not promotable
                                          under the current confirmed gate without a trust-tier
                                          change or a validated Primitive-A fix)
```

## 4. Machine-readable reason

```json
{
  "pair": {"confirmed": {"sta": 350, "ap": 167}, "miss": {"sta": 355, "ap": 164}},
  "classification": "HARD_MISS_NEEDS_GUESS",
  "machine_reason": "ap164_is_a_PrimitiveB_recovered_only_candidate; A_side_abstained_no_A_B_agreement(A_ap=None,B_verdict=recovered); NOT a label-adjacency collision (centroids 489px apart); confirmed-tier absence is by design",
  "evidence": {
    "ap164_in_hand_table": true, "ap164_geometry_ready": true,
    "ap164_A_ap_at_355": null, "ap164_B_verdict_at_355": "recovered",
    "ap164_reconstructed": true, "ap164_full_phrase": true, "ap164_not_matchline": true,
    "centroid_separation_px": 489.3, "b_recovered_only": true, "labels_far_apart": true
  },
  "control_ok": true,
  "recovery_paths_out_of_scope": [
    "a VALIDATED Primitive-A fix at STA 355 (diagnose why A abstained — tie / beyond-tol nearest cluster)",
    "an AUTHORIZED decision to admit Primitive-B 'recovered' endpoints into the placement-grade set (a trust-tier change)"
  ]
}
```

## 5. Recovery paths (named, both out of scope for a no-widen gate)

AP-164 is genuinely recoverable in principle — it is a real run-endpoint — but **neither path is a
guess and neither is a no-widen structure-side change**:
1. **Validated Primitive-A fix.** Diagnose why A abstained at STA 355 (likely the nearest valid-AP
   cluster was beyond tolerance or tied) and fix it so A independently lands AP-164 → A∧B agree →
   `confirmed`. This is an extractor change and must be validated against the 7 confirmed (no
   regression) + ground truth — out of scope for this gate, and "No broad extraction rewrite."
2. **Authorized B-recovered tier.** Decide to admit `recovered` (B-only) endpoints into the
   placement-grade set. That relaxes the confirmed-tier trust contract and requires explicit
   authorization — not something a no-widen gate may do unilaterally.

Until one is taken, AP-164 stays a **documented B-recovered review** — exactly analogous to AP-160
(Target #35): real, geometrically strong, but short of the placement-grade bar by one independent
corroboration. No promotion artifact updated.

## 6. Validation + non-regression

- `python -m py_compile scripts/target36_ap164_adjacent_pair_gate.py` → `PY_COMPILE_OK`.
- Probe run → `HARD_MISS_NEEDS_GUESS`; `SELFTEST_OK`.
- **Control:** AP-167 @ 350 re-validated `A_ap=167, B_verdict=confirmed` (`control_ok=True`) — the
  confirmed endpoint sharing this region is not degraded.
- No change to `BRENHAM_PH5_RUN_ENDPOINTS`, the confirmed set, or any flag/STATE/geometry.

## 7. Verdict + next target

The next-safest endpoint-quality gate is adjudicated: AP-164's "miss" is a **Primitive-B
recovered-only** state (A abstained), **not** an adjacent-pair collision (#32 label corrected). It
stays out of the placement-grade set under DO-NOT-WIDEN; the two named recovery paths are recorded
for a future authorized session. Recall stays 0.70 honestly; precision 1.00; 7 confirmed +
bore_log7 untouched.

**Next (when re-authorized):** a focused Primitive-A abstention diagnosis at STA 355 (path 1) — the
single, bounded extractor question that would safely lift AP-164 to `confirmed` and recall to 0.80,
validated against the 7 confirmed. Pure structure-side; still no placement.

## 8. Files

- Read: `scripts/pdf_endpoint_table_8_14.out` (#32), `scripts/pdf_clean_endpoint_table.json` (#33),
  `scripts/ap_structure_index.json` (#25), `BRENHAM_PH5_RUN_ENDPOINTS`
  ([pdf_ap_route_resolver.py:1001](backend/app/core/pdf_ap_route_resolver.py#L1001)), Primitives
  A/B/C + `pdf_ap_glyph_reconstruct.py` (#30); `Brenham - Phase 5_07-15-25.pdf` sheet 12 (read-only).
- Wrote: `scripts/target36_ap164_adjacent_pair_gate.py` + `.json` + `.out`; this report.
