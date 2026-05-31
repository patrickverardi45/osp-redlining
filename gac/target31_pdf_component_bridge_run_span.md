# Target #31 — Component-Bridge / Bored-Run Span Tracer (default-OFF, read-only)

**Mission:** recover STA 1+36 → AP-166 ONLY if a single bored-run polyline provably spans the gap
between STA 1+36's component and the (Target #30) localized AP-166 target; else abstain with a
precise reason.

**VERDICT: 136→166 NOT recovered — the bridge cannot be proven, and the geometry says so
explicitly.** The 45 px gap between STA 1+36 and AP-166 is **hatch/annotation soup** (104 curves,
7 lines, 86% short segments), carries **no DIR.BORE label**, and **no single vector component spans
both endpoints**. Bridging it would be guessing, so the tracer abstains. All Target #27/#28/#30
trusted endpoints are preserved; AP-125 does not steal STA 136; AP-110 stays rejected.

> Read-only. Pure helpers; isolated in `scripts/`; no engine import-as-production, no flag, no
> STATE, no placement. Helper `scripts/pdf_component_bridge.py` → `.json`/`.out`.

---

## 1. Method (two acceptance paths, everything else abstains)

`attempt_bridge(sta_xy, ap_xy, ap_id, uf, nodes, lines, curves, bore_labels)`:
- **`same_component_direct`** — STA and AP already share one vector component (the trusted
  Primitive B case). Accept. The tracer never degrades these.
- **`bridge_single_run`** — STA and AP are in SEPARATE components, but a single bored-run polyline
  spans the gap. Requires ALL of: a spanning component, NOT hatch soup (`curves ≤ 3×lines` and
  short-segment ratio ≤ 0.6), at least one long run segment (≥18 px), AND a DIR.BORE label in the
  gap corridor. Any failure → abstain with the specific reason(s).

AP targets come from the Target #30 reconstruction (canonical positioned AP universe), so the
tracer aims at real localized centroids (e.g. AP-166 @ [793.8, 161.4]).

## 2. Primary case — sheet 10 STA 1+36 → AP-166

```
ABSTAIN  straight=45.1px
reason: no_spanning_component;
        gap_is_hatch_soup(curves=104, lines=7, short_ratio=0.86);
        no_dir_bore_label_in_gap
```

The run that the hand table records (STA 136 → AP-166) is **not drawn as a followable polyline**
between these two points on sheet 10 — the intervening vector layer is hatch/annotation, there is
no `DIR. BORE` label in the gap, and the two endpoints live in different small components. Three
independent gates fail; recovering 166 here is impossible without guessing.

## 3. Validation vs `BRENHAM_PH5_RUN_ENDPOINTS` (sheets 8 & 10, AP rows)

| requirement | result |
|---|---|
| recover (10,136,166) | **NOT RECOVERED** — abstain (3 machine-readable reasons) |
| keep (10,451,163) trusted | **PASS** — `same_component_direct` (straight 19 px) |
| keep (8,413,157) trusted | **PASS** — `same_component_direct` (straight 44 px) |
| AP-125 not stealing STA 136 | **NO theft** — canonical AP-125 target is 206 px from STA 1+36 (the earlier "125-in-136-component" was a loose-cluster artifact); not trusted |
| (8,308,110) rejected/review | **NOT trusted** (Primitive B `unconfirmed_review`, unchanged) |

```
FINAL trusted endpoints = (8,366,154) (8,387,156) (8,413,157) (10,140,165) (10,451,163)
REPRODUCED vs hand      = same 5  (100% precision, 0 wrong)
bridged (cross-comp)    = NONE     (no unsafe bridge accepted)
```

No Target #27/#28/#30 trusted case degraded; precision unchanged.

## 4. Rejected alternatives (machine-readable)

- **AP-166 bridge:** `no_spanning_component` + `gap_is_hatch_soup(...)` + `no_dir_bore_label_in_gap`.
- **AP-125 local steal:** `no_vector_nodes_at_endpoint` (the canonical AP-125 centroid is 206 px
  away — a different AP-125 instance, not adjacent to STA 1+36). This is an *improvement* over
  Target #28's loose digit-cluster, which had spuriously scoped AP-125 into STA 136's component.
- **AP-110 (sheet 8 STA 308):** remains Primitive B `unconfirmed_review`; the bridge does not
  promote it.

## 5. Safety posture

- **No degradation:** trusted set identical to Target #28/#30 (5 rows, 100% precision); both gate
  cases accept via same-component.
- **No guessing:** the primary case abstains with three independent geometry reasons; no AP id
  invented; the accept-path is exercised (same-component) so the tracer is not vacuously abstaining.
- **Placement-free / read-only:** lives in `scripts/`, no engine import, no flag, no STATE.
- Self-test `python scripts/pdf_component_bridge.py selftest` → `SELFTEST_OK` (same-component accept,
  cross-component hatch-soup abstain with reasons).

## 6. Verdict + next target

For the **136→166 endpoint specifically, the sheet-10 vector geometry does not contain a provable
bored-run bridge** — the connecting run is not rendered as a single traceable polyline, so it is
geometry-unprovable from this sheet alone (the hand-table value stands as the reference; it is not
re-derivable without guessing here). This is an honest floor for that one endpoint, not a
missing-data claim — every other extraction primitive remains valid. Next:
1. **Cross-sheet / multi-drive run reconstruction** — the 1+36→166 drive may continue across a
   matchline onto an adjacent sheet; reconstruct the run across the matchline equation before
   declaring it unbridgeable on a single sheet.
2. **Apply the A→B→C→reconstruct→bridge chain to sheets 8–14** to auto-build the run-endpoint table
   for the (many) endpoints that ARE drawn as clean same-component bindings, feeding the Target #25
   index — capturing the geometry-provable wins while leaving the genuinely-unbridgeable ones
   abstained.
Still placement-free; DO-NOT-WIDEN intact.

## 7. Files read
- `Brenham - Phase 5_07-15-25.pdf` sheets 8 & 10 (`page.lines`/`curves`/`chars`/words; read-only).
- `scripts/pdf_run_endpoint_extractor.py` (A), `scripts/pdf_leader_run_following.py` (B),
  `scripts/pdf_ap_glyph_reconstruct.py` (Target #30 AP targets) — reused pure.
- `BRENHAM_PH5_RUN_ENDPOINTS` ([pdf_ap_route_resolver.py](backend/app/core/pdf_ap_route_resolver.py)).
- Helper: `scripts/pdf_component_bridge.py` → `.json`/`.out`.
