# Target #28 — Primitive B: PDF Leader-Line / Run-Polyline Following (default-OFF, read-only)

**Mission:** add vector-geometry (`page.lines`/`page.curves`) following to fix the Primitive A
miss/ambiguity class — without guessing and without degrading the validated PASS cases.

**VERDICT: WORKS as a geometry-VALIDATION + false-positive-REJECTION layer.** Vector
connectivity is safely followable on these sheets (NOT hatch soup — proven by feasibility
probe). Both required gate cases stay PASS and are now geometry-confirmed; the EXTRA false
positive is rejected; the MISS abstains with a precise geometry reason. No AP id was guessed.

> Read-only. Pure helpers; isolated in `scripts/`; no engine import-as-production, no flag, no
> STATE, no placement. Helper `scripts/pdf_leader_run_following.py`; feasibility probe
> `scripts/pdf_leader_connectivity_probe.py`; output `…json`/`…out`.

---

## 1. Feasibility first — is the vector layer followable? (the no-guessing gate)

A connectivity probe built a connected-component graph over all line+curve endpoints and tested
the known-good pair and the miss. Result (`pdf_leader_connectivity_probe.out`):

| pair | shared component | followable? |
|---|---|---|
| sheet 10 451→AP-163 (known good) | small isolable comp (sizes 80/74/40) | **YES** |
| sheet 10 136→AP-166 (miss) | small isolable comp (sizes 38/17/14) | YES (but resolves to AP-125, see §3) |
| sheet 8 308→AP-110 (extra) | small comp (27/2) | YES |

The page's largest component is only ~244 nodes (not a page-spanning hatch blob), and callouts
connect to their structure labels through small, specific components. **So the geometry can be
followed safely** — Primitive B is justified (not guessing).

## 2. Method (Primitive B, pure, deterministic)

For each Primitive A AP-class record:
1. `build_vector_components(lines, curves)` — union-find over snapped (2px) line/curve endpoints.
2. Find the structure label's **connected component**.
3. `ap_in_structure_component(...)` — the unique valid-AP digit cluster whose center is within
   22 px of that component (excluding the station's own value). Abstain on none / tie / collision.
4. Verdict: `confirmed` (A==B), `recovered` (A abstained, B found one), `corrected` (A≠B),
   `unconfirmed_review` (A had an AP, geometry found none), `abstain_geometry`.
5. **TRUSTED = `confirmed` only** (A and B agree). `recovered`/`corrected` are REVIEW candidates,
   never auto-asserted. Primitive B never invents a placement — it annotates A.

## 3. Targeted cases (deliverable 4) — all four resolved honestly

| target | outcome | evidence |
|---|---|---|
| **sheet 10 STA 451 → AP-163** (keep) | **PASS — confirmed** | 163 @1px in the structure's vector component |
| **sheet 8 STA 413 → AP-157** (keep) | **PASS — confirmed** | 157 @4.5px in component |
| **sheet 10 STA 136 → AP-166** (recover?) | **ABSTAIN (geometry)** | the component at STA 1+36's structure resolves to **AP-125 @6.3px, not 166**. AP-166 is the run's FAR end, not reachable as a single isolable polyline → recovering 166 would be guessing. Per the rule "recover IF supported by leader geometry" — it is **not** supported. |
| **sheet 8 STA 308 → AP-110** (classify) | **FALSE POSITIVE / REVIEW** | no valid-AP cluster lies in the STA-308 structure's component → Primitive A's nearest-label `110` is **not geometry-confirmed**. Downgraded to review. |

## 4. Validation vs `BRENHAM_PH5_RUN_ENDPOINTS` (sheets 8 & 10, AP rows)

```
[PASS] sheet 10 STA 451 -> AP-163
[PASS] sheet  8 STA 413 -> AP-157

TRUSTED (A+B agree)              = (8,366,154) (8,387,156) (8,413,157) (10,140,165) (10,451,163)
REPRODUCED vs hand              = same 5  (100% precision: every trusted row is a real hand row)
hand rows NOT trusted (abstain) = (10,136,166)
FALSE-POSITIVE / REVIEW         = (8,308,110)        # A's EXTRA, geometry did not confirm
GEOMETRY CANDIDATES (review)    = (10,136,125) (10,162,121) (10,3890,162)   # B found AP where A abstained/disagreed
```

- **Precision improved:** the TRUSTED set is 5 rows, **all 5 are correct hand entries (0 wrong)**.
  Primitive A's lone EXTRA (308→110) is now correctly quarantined as review.
- **Recall unchanged on the gate**, miss unchanged but now with a geometry-grounded reason.
- **Notable review candidate / conflict:** geometry binds STA 136 → **AP-125**, while the hand
  table says 136 → AP-166. This is surfaced for human review — NOT asserted. It suggests the
  hand entry encodes the run's far-end AP while the local structure at STA 1+36 is AP-125; a
  full run-polyline trace (a heavier primitive) would be needed to confirm, and that is not
  attempted here because it cannot be done on this geometry without guessing.

## 5. Machine-readable ambiguity reasons (deliverable 5)

Every record carries `leader_connectivity = {verdict, component_ap, reason}` with reasons:
`no_vector_nodes_near_structure`, `no_valid_ap_in_structure_component`,
`ambiguous_component_ap_<a>_vs_<b>`, `unique_in_component`. Verdicts above are deterministic.

## 6. Safety posture

- **No degradation:** Primitive B only annotates / downgrades Primitive A; the two PASS cases are
  preserved and strengthened. It never upgrades a guess into a placement.
- **No guessing:** uncertain bindings abstain with a reason; conflicting geometry candidates are
  REVIEW-only.
- **Placement-free / default-OFF by construction:** lives in `scripts/`, no engine import, no
  flag, no STATE. Self-test `python scripts/pdf_leader_run_following.py selftest` → `SELFTEST_OK`.

## 7. Verdict + next target

Primitive B is the right tool for **validation + false-positive rejection**, and it confirms the
vector layer is followable for local structure binding. It does **not** trace a full multi-drive
run to a distant AP (the 136→166 / 136→125 case) — that needs a heavier, carefully-gated
**run-polyline tracer** (follow a single bored-run curve end-to-end, distinguishing it from
hatch by length/continuity), which must itself be validation-gated to avoid guessing. Next:
1. **MATCHLINE-label exclusion** (drops the 162/3890 matchline candidates from the AP pool).
2. **Run-polyline tracer** (heavier Primitive C) for multi-drive far-end APs — gated by
   hand-table equality, abstain on any branch/ambiguity.
3. Extend sheets 8/10 → 8–14 once A+B are MATCHLINE-clean.
Then the A+B trusted table feeds the Target #25 index. Still placement-free; DO-NOT-WIDEN intact.

## 8. Files read
- `Brenham - Phase 5_07-15-25.pdf` sheets 8 & 10 (`page.lines`/`curves`/`chars`/words; read-only).
- `scripts/pdf_run_endpoint_extractor.py` (Primitive A, reused pure).
- `BRENHAM_PH5_RUN_ENDPOINTS` ([pdf_ap_route_resolver.py](backend/app/core/pdf_ap_route_resolver.py)) — validation hand table.
- Target #26/#27 reports.
- Helpers: `scripts/pdf_leader_run_following.py` (+ `pdf_leader_connectivity_probe.py`) → `.json`/`.out`.
