# PDF↔KMZ Bridge Doctrine

How a PDF-derived redline is allowed to relate to the KMZ / Hero map. This is a **safety
contract**, not a feature spec. It exists so we can connect the engineering PDF to the world map
*without* drawing a wrong line. Read this before touching anything that joins PDF evidence to map
geometry.

## The five rules

1. **PDF path XY is evidence, not map geometry.**
   The page-space `[x,y]` we extract from a plan sheet (traces, `geo_anchors[].coord`, seam-crossing
   points) describes *where something is on the paper*, at the sheet's DPI. It is proof of what the
   PDF says. It is **never** a map coordinate and must never be drawn on the Hero map.

2. **KMZ lat/lon is map geometry, not proof of PDF intent.**
   The KMZ gives us real-world routes and structures (`lonlat` / `[lat,lon]`). That tells us *where
   things are in the world* — but a nearby KMZ line is **not** evidence that a given PDF redline
   belongs to it. Proximity is not proof.

3. **The bridge joins by IDENTITY first.**
   A PDF redline is linked to a KMZ feature / map route only through shared identity:
   **AP / HH / structure IDs** (D5: PDF `AP-120` = KMZ TermPortHH `120`), the **source log / `log_id`**,
   and **station / matchline evidence**. The join is an *exact* identity match — never a
   nearest-geometry guess, and **never a raw coordinate comparison**.

4. **If identity/evidence does not prove the join, the bridge ABSTAINS.**
   No identity target → `status="abstain"` with a machine-readable `abstain_reason` and **no path**.
   A wrong bridge is worse than no bridge (the same doctrine as the redline selector, D13).

5. **The Hero map renders only from PROVEN bridge candidates — later.**
   Today nothing draws. When map rendering is eventually built, it consumes only
   `status="candidate"` bridge objects that already passed identity + evidence checks. Abstained or
   blocked candidates are never drawn.

## Why coordinates are banned from the join
`kmz_xref.ap_map[#].lonlat` is `[lon,lat]` (strings); the KMZ render payload is `[lat,lon]` (floats)
— a **confirmed coordinate-order inversion**. Any code that joins on raw coordinates can silently
transpose a redline. The bridge sidesteps this entire bug class by joining on **IDs**, not numbers.

## What exists today (inert / read-only)
- **Schema + validator:** `backend/app/core/pdf_redline_bridge.py` →
  `pdf_redline_bridge_candidate` (`pdf-redline-bridge-candidate-1`). Draw-free; rejects any
  world/geometry key; enforces abstain-first; requires a world identity target for a live candidate.
- **Builder (default-OFF, wired to nothing):** `backend/app/core/pdf_redline_bridge_builder.py`
  maps `pdf_first_evidence` + a caller-supplied KMZ identity index → candidates by identity only.
  Gate: `TRUELINE_PDF_KMZ_BRIDGE_BUILDER` (for a future call site).
- **Tests:** `backend/tests/test_pdf_redline_bridge_contract.py`,
  `backend/tests/test_pdf_redline_bridge_builder.py`.

## Candidate status semantics
| status | meaning | drawn? |
|---|---|---|
| `candidate` | identity target resolved (KMZ feature and/or map route) | only later, after review |
| `abstain` | identity/evidence insufficient — carries `abstain_reason`, no path | never |
| `blocked` | missing input (session / log / plan id) — carries `blockers` | never |

**Nothing in this lane renders.** The bridge produces data; drawing on the Hero map is a separate,
explicitly-gated step that comes only after candidates are reviewed and proven.
