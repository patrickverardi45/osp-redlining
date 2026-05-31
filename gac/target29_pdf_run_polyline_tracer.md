# Target #29 — Primitive C: Gated DIR.BORE Run-Polyline Tracer + Matchline Exclusion (read-only)

**Mission:** follow a run's vector geometry to a FAR-END AP that nearest-label (Primitive A) and
structure-component (Primitive B) cannot reach — specifically test sheet 10 STA 136 → AP-166 —
plus add matchline-label exclusion and run-role classification. Strict no-guessing.

**VERDICT: AP-166 NOT recovered — and provably so, not by giving up.** The far-end AP-166 is
PRESENT on sheet 10 (page-concat V2 reads ids 163/165/166; the `"166"` substring exists) but does
**not** form a positioned digit cluster — its glyphs scramble, so there is **no geometry target to
trace to**. Tracing to it would mean reading the scrambled glyph as a human does = guessing. The
tracer therefore ABSTAINS with a machine-readable reason. All Target #27/#28 trusted cases are
preserved; the false positive stays rejected.

> Read-only. Pure helpers; isolated in `scripts/`; no engine import-as-production, no flag, no
> STATE, no placement. Helper `scripts/pdf_run_polyline_tracer.py` → `.json`/`.out`.

---

## 1. Why a far-end run trace can't recover AP-166 (the empirical core)

| signal | result |
|---|---|
| page-concat V2 AP ids on sheet 10 | `163, 165, 166` (166 IS on the page) |
| `"166"` substring in concat text | present |
| **positioned `166` digit cluster** | **NONE** — glyphs do not reassemble into a localizable token |
| ⇒ trace target for STA 1+36 | **does not exist as geometry** |

A run tracer can only follow vector components to a *positioned* structure token. AP-166 has no
positioned token, so the tracer returns
`target_ap_166_not_spatially_localizable_glyph_scramble` — a precise, honest abstain. This is the
correct outcome under "if a run cannot be followed as one safe component, abstain."

## 2. Validation vs `BRENHAM_PH5_RUN_ENDPOINTS` (sheets 8 & 10, AP rows)

```
[PASS] keep (10,451,163)        # geometry-confirmed (Primitive B), preserved
[PASS] keep (8,413,157)         # geometry-confirmed, preserved
(10,136,166) -> NOT RECOVERED   # reason: target_ap_166_not_spatially_localizable_glyph_scramble
(8,308,110)  -> REVIEW/REJECTED # B verdict unconfirmed_review (no valid AP in its component)

TRUSTED (B-confirmed, matchline-excluded) = (8,366,154) (8,387,156) (8,413,157) (10,140,165) (10,451,163)
REPRODUCED vs hand                         = same 5  (100% precision, 0 wrong AP ids)
```

No Target #27/#28 trusted case is degraded; precision and the gate are unchanged.

## 3. Run-role classification (deliverable 3)

`classify_callout` labels each STA callout deterministically:
`run_start` (STA 0+00), `matchline` (callout adjacent to a MATCHLINE label), `run_end`
(localizable AP in structure component), `run_end_unresolved_ap` (terminal structure, AP not
localizable — e.g. STA 1+36), `unrelated_or_tick`. This is what distinguishes a real run-end from
a run-start, a matchline, or a stray nearby label.

## 4. Matchline-label exclusion (deliverable 2) — honest scope

Implemented as a **conservative geometric signal**: a STA callout within 36 px of a `MATCHLINE`
label is treated as a matchline station and excluded from AP trust. On sheets 8 & 10 this caught
**0** stations at the safe tolerance — because the four `MATCHLINE` words are **sheet-edge
annotations** (y≈76 / 659), not co-located with each matchline station (139/160/162/166/167/190/
191/611). A looser radius (70 px) false-positived a real AP run-end (STA 1+36 sits ~67 px below a
top-edge label), so it was tightened to 36 px to avoid degrading a hand row.

**Net effect on trust:** the matchline review-candidates Target #28 surfaced (STA 162 / STA 3890 →
spurious APs) are **already excluded from the trusted set** by the *confirmed-only* gate (they were
`recovered` review candidates, never `confirmed`). So matchline candidates do not enter trust. The
geometric label-proximity exclusion is a secondary net; **robust matchline-station identification
should use the SEE-SHEET equation text or the cross-sheet shared-STA boundary signal already
encoded in `brenham_plan_sheet_graph._BOUNDARY_STA_FT`** — named as next work, not bolted on here
without validation.

## 5. Machine-readable reasons (deliverable 6)

Tracer reasons: `no_vector_nodes_at_callout`, `target_ap_<n>_not_spatially_localizable_glyph_scramble`,
`no_far_ap_in_run_component`, `branch_multiple_far_ap_<list>`, `single_far_ap_in_component`.
Verdicts carried per row in `pdf_run_polyline_tracer.json` alongside A/B verdicts.

## 6. Safety posture

- **No degradation:** trusted set identical to Target #28 (5 rows, 100% precision); gate PASS.
- **No guessing:** the headline miss abstains with a geometry reason; no AP id invented.
- **Placement-free / read-only:** lives in `scripts/`, no engine import, no flag, no STATE.
- Self-test `python scripts/pdf_run_polyline_tracer.py selftest` → `SELFTEST_OK` (matchline
  derivation, run-role classification, glyph-scramble abstain).

## 7. Verdict + next target

The PDF-extraction chain has reached the **glyph-localizability floor**: the remaining far-end APs
(AP-166 class) are present but not positioned-recoverable by char clustering. Next:
1. **Positioned AP-glyph reconstruction** — extend the Target #1 char-stream V2 to recover scrambled
   AP numbers *with positions* (cluster the individual chars of a scrambled "166" by their bbox even
   when reading order is broken), giving the tracer a target. This is the precise unlock for the
   136→166 class.
2. **Matchline via SEE-SHEET / boundary-STA** signal (not label proximity).
3. Extend sheets 8/10 → 8–14 once (1)/(2) land, then feed the trusted table into the Target #25 index.
Still placement-free; DO-NOT-WIDEN intact.

## 8. Files read
- `Brenham - Phase 5_07-15-25.pdf` sheets 8 & 10 (`page.lines`/`curves`/`chars`/words; read-only).
- `scripts/pdf_run_endpoint_extractor.py` (Prim A), `scripts/pdf_leader_run_following.py` (Prim B) — reused pure.
- `BRENHAM_PH5_RUN_ENDPOINTS` + `extract_ap_ids_v2` ([pdf_ap_route_resolver.py](backend/app/core/pdf_ap_route_resolver.py)).
- Target #26/#27/#28 reports. Helper: `scripts/pdf_run_polyline_tracer.py` → `.json`/`.out`.
