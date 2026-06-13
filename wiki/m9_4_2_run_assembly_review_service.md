# M9.4.2: RUN-ASSEMBLY review service surface (additive parallel service; UNWIRED)

Status: **SHIPPED (reviewer-service SURFACE; UNWIRED / unconsumed; per-bore bundle
byte-identical); adversarially audited (6 lenses, 0 findings); zero bores moved; zero
product-bucket movement.** Wires the already-shipped M9.4.1 run-assembly cards into a
bounded reviewer-service surface, following the M8.20 `GroupReviewService` precedent.
The M8.10/M8.11 per-bore bundle, statuses, census, and lanes are UNCHANGED.

Service: `truelinev2/review/run_assembly_review_service.py` `RunAssemblyReviewService`
Proof: `truelinev2/proof/run_run_assembly_review_service_proof.py` (G1–G10 PASS)
Tests: `truelinev2/tests/test_run_assembly_review_service.py` (offline; synthetic + posture)

## The surface (shipped)

`RunAssemblyReviewService(*, corpus_dir, plan_pdf_path, bore_log_paths, kmz_model,
terminus_profile, source_contradiction_bores=(), sheet_offset=13).generate()` →
`List[RunAssemblyReviewCard]`.

It composes the shipped M9.4.1 product-layer pipeline:

  `TA.attribute_bore` (M9.3.1) → `extract_run_assembly` (M9.4.1) → `build_run_assembly_cards` (M9.4.1)

returning one card per SHARED-TERMINAL evidence item (a typed blocker yields no card),
in deterministic `(end_bore, start_bore)` order. Unparseable bore sources are ignored
(they cannot attribute a terminus and stay represented by the per-bore bundle).

**Deliberately SEPARATE from `ReviewerBundleService.generate`** — exactly as M8.20's
`GroupReviewService` is separate from the per-bore bundle. The service adds NOTHING to
the M8.11 bundle; it surfaces the run-assembly cards through a parallel service under
their own schema (`truelinev2-run-assembly-review-1`).

**CONVENTION-AGNOSTIC:** the module holds zero plan-set literals (drift-guard-enforced;
`review/` is in CORE_DIRS). The KMZ model, the terminus profile, and the banked
source-contradiction set are all INJECTED by the caller — mirroring how
`GroupReviewService` takes its `lane_dialect`.

## Result (all-58, live — the exact 3 cards)

- `log10` END → `log27` START @ AP-152 = **`RUN_ASSEMBLY_REVIEW_CANDIDATE`**
- `log72` END → `log39` START @ AP-117 = **`RUN_ASSEMBLY_REVIEW_CANDIDATE`**
- `log7` END → `log65` START @ AP-163 = **`JUNCTION_DROP_BRANCH`** (log65 stays a drop
  because its own departing source prints `FOR FIBER DROP`; non-promotable).

Each card is REVIEW/evidence-only (label frozen `SUGGESTION_NOT_PLACEMENT`, no geometry,
no strokes, no AUTO), and carries the M9.4.1 frame-scoped `competing_departures == 1`.

## Additive-only (proof G1/G6 — live, not tautology)

- **G1**: the per-bore `generate(default_baseline)` bundle is BYTE-IDENTICAL before/after
  the run-assembly service runs (`before.model_dump_json() == after.model_dump_json()`).
- **G6**: the banked per-bore default counts (`14/10/32/2 = 24`, 58 payloads) AND the
  fullest-safe lanes (`30/16/6/4/2`) are unchanged — recomputed live inside the bundle
  pydantic validator from the actual `run_match`-derived payloads, not echoed constants.
- **G7**: the run-assembly schema is DISJOINT from the M8.10/M8.11/M8.15/M8.20 schemas.

`review/reviewer_service.py` (the per-bore bundle) is NOT modified — byte-identical at
source. The only modified existing file is `test_terminus_attribution.py`: its composer
skip-set adds `run_assembly_review_service.py` (the service legitimately imports
`terminus_attribution` to call `attribute_bore`), exactly as M9.4.1 added `run_assembly.py`;
the placement-path assertion is preserved, not weakened.

## UNWIRED + posture

The service is **unconsumed** — no `resolve_bore` / sweep / `run_match` / engine /
reviewer-service / UI imports it, and it imports no placement decider and no
`_build_plan_frame_graph` (it is strictly LESS wired than its M8.20 precedent, which
DOES import `resolve_bore` + the frame graph). No render / PNG / segment / AUTO /
placement / bucket change; zero bores moved. Full v2 suite **759 passed**;
convention / import-isolation / global-state / red-stroke guards green.

## Frame-scoped limitation preserved (not hidden)

The service performs NO cross-sheet / M9.2 frame-graph expansion. Each bore is given
ONLY its own sheets (`lines_by_id[bore_id] = {s: plan.lines(s, offset) for s in bore.sheet_refs}`)
— exactly the per-bore frame the M9.4.1 core's `physical_departure_count` consumes. The
cards carry the frame-scoped `competing_departures` verbatim; the named cross-sheet
lateral limitation stays the M9.2 frame-graph-gated open target (proof G9).

## Adversarial audit

6 refutation lenses (additive-only, no bucket movement, no placement-path import, no
overclaim, frame-scoped-limitation preserved, correctness). **0 confirmed defects** —
every lens refuted with file:line evidence and an independent live re-run of the per-bore
bundle (reproduced the exact banked 24/58 + 30/16/6/4/2). The service is a thin additive
composition of already-audited M9.4.1 components following the proven M8.20 precedent.

## Surface claim (no overclaim)

A reviewer-service SURFACE that emits the run-assembly cards — NOT product-ready beyond
that: no UI, no API/transport, no placement, no bucket change, no cross-sheet/M9.2
expansion. Any UI/API transport for these cards is a separate, authorized milestone.

## Next step

A UI/API transport for the cards (separate, authorized milestone — not started). The
cross-sheet competing-lateral enumeration remains the M9.2 frame-graph-gated target (the
named M9.4.1 limitation). Owner source re-reads remain required for log46 (PDF↔KMZ) and
log44 (325′) before any continuity touching those bores.
