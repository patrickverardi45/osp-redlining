# Public Cold-Corpus Harvest — Checkpoint (read-only)

Continued-94 (2026-06-30). A read-only harvest of public construction / HDD / utility plan PDFs driven through
the cold-package validation intake path (`harness/package_validation.py`). Purpose: inventory real-world plan
DIALECT GRAMMARS (grouped generically, never by customer/project/place) and map what the current read-only
observer stack can and cannot bind — to inform later, separately-approved extractor gates.

**NAME-FREE:** this committed doc names NO customer / project / person / place. The named source inventory and
per-candidate URLs live ONLY in the gitignored `data/outputs/truelinev2/cold_packages/` drop-zone (NEVER
committed): `_DIALECT_DISCOVERY_REPORT.md` + per-package `_harvest.json`.

## Method
Four parallel read-only research agents gathered verified direct-PDF URLs across public-source categories
(state pipeline e-filing portals, city/county utility permit portals, DOT fiber/conduit plan sets, municipal
water/sewer bid packages). Each candidate was downloaded to a gitignored `public-cold-NNN/uploads/plan.pdf`,
text-extracted, run through the **UNMODIFIED** `select_dialect`, and classified RECOGNIZED / COLD_CANDIDATE /
UNUSABLE. Cold candidates with a clean, source-visible bore span were packaged (name-free `package.json` +
minimal `bore-log.xlsx` transcribed from printed stations ONLY — no invented values) and run through the
read-only validation. No engine / observer / dialect / placement / AUTO change; nothing downloaded was committed.

## Results (cumulative, candidates 001–035)
- Downloaded as real PDF: **35** (all gitignored, none committed)
- RECOGNIZED by existing named dialects: **10**
- COLD / non-recognized (`select_dialect is None` + station evidence): **14**
- UNUSABLE (no text layer / no station evidence): **11**
- Fully package-validated: **3**

### Validated packages
| package | select_dialect | eligibility | observer |
|---------|----------------|-------------|----------|
| `public-cold-001` | recognized | `INELIGIBLE_RECOGNIZED_WORK_CORPUS` | not run (gate reject) — control |
| `public-cold-002` | None | `ELIGIBLE_FRESH_NONRECOGNIZED` | ran; endpoints UNBOUND, RIVAL_RUNS, LOOSE → abstain |
| `public-cold-011` | None | `ELIGIBLE_FRESH_NONRECOGNIZED` | both termini BOUND via `PRINTED_STA_CALLOUT`; geometry `NO_STATION_AXIS` |

`public-cold-011` is the **FIRST real-plan endpoint bind** in the arc (`PRINTED_STA_CALLOUT` on a printed
`Sta. X to Y` handhole-to-handhole span). Every eligible run carries `class_verified=False` +
`CLASS_VERIFICATION_MISSING`; no placement / promotion; **no generalization claimed; G4/AUTO stays blocked.**

## Dialect grammar families (generic categories)
**RECOGNIZED (already handled by named detectors; correctly rejected as cold proof):**
- `DIRECTIONAL BORE` phrase grammar (caught by the named directional-bore detector)
- `STA a+bb TO STA c+dd` span grammar (caught by the named station-span detector)
- Both are COMMON across real public plans; the detectors are pure-grammar, so they recognize ANY third-party
  plan using the phrasing (correct for the cold gate — if recognized, it is not "cold").

**COLD (`select_dialect` None) — candidate families to potentially learn later:**
- **B1 Pipeline HDD plan-profile** — `HDD ENTRY/EXIT` + standalone `STA. N+NN`, `HDD HORZ/PIPE LENGTH`,
  pilot/reamed/as-built variants. Endpoints are POINTS (no plan-view structure) → binders do not bind.
  **Largest cold family.**
- **B2 County/municipal buried-fiber** — `Sta. X to Y` handhole-to-handhole spans + `Start/End NNN' bore` +
  handhole legend (lowercase "to" → NOT the STA-TO-STA trigger). **Binds via `PRINTED_STA_CALLOUT`.**
- **B3 OSP fiber permit (plan-view)** — `STA N+NN - <ft>' BCF` + `BORE / BORE PIT` + `VAULT / HANDHOLE /
  PULLBOX`; multiple short bores between vaults.
- **B4 Municipal water-main HDD** — `NEW n" HDD … / NNN LF OF HDD / Match Line Station`; length-based callouts.
- **B5 Airport / utility duct** — `STA N+NN.N, <ft>' LT/RT` offset point stations along a baseline.

**UNUSABLE (~31%):** scanned permit sheets, figure-only design reports, spec-heavy bid sets → no extractable
text → require an OCR / raster ingestion stage before the text-based engine can read them.

## Observer capability (can the current stack bind termini?)
- `PRINTED_STA_CALLOUT` binder: **WORKS** on a real cold plan (cold-011 bound both ends).
- Structure-label / leader-trace binders: **did not fire** on the real plans tested (HDD entry/exit points carry
  no recognized structure grammar / no extracted leader geometry).
- Generic geometry observer: ran on cold-002 (`RIVAL_RUNS`) but `NO_STATION_AXIS` on cold-011 → axis fitting is
  inconsistent across plan types.
- `class_verified` **always False** (no generic class table) → G4/AUTO blocked regardless.

## Recommended next gates (read-only; NO AUTO; each separately owner-approved before implementation)
1. **Generic station-axis fitting across diverse sheets** — cold-011 bound endpoints but geometry hit
   `NO_STATION_AXIS`; a robust generic axis fitter unlocks geometry verification (B2/B4).
2. **HDD entry/exit POINT-station binder** — binds B1, the largest cold family (endpoints are points, not
   structures).
3. **OCR / raster ingestion (later)** — to rescue the ~31% no-text plans.

Until an approved extractor gate runs, this remains an INVENTORY + PATTERN MAP only: no engine / dialect change,
no placement, no AUTO. Named specifics in the gitignored report.
