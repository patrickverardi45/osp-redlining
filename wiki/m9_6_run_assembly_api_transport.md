# M9.6: RUN-ASSEMBLY review-card read-only API/transport contract (bounded, default-OFF)

Status: **SHIPPED (additive transport surface; default-OFF; read-only; UNWIRED from the
placement path); adversarially audited (3 low-severity findings converted to fixes +
gates pre-commit).** Exposes the already-shipped M9.4.2 `RunAssemblyReviewService.generate()`
cards through a bounded v2 API transport WITHOUT changing engine placement, the per-bore
reviewer bundle, any product bucket, UI, or deploy. The M8.27 census, product lanes,
M8.11 lanes, M9.4.1/M9.4.2 cards, and the M9.5 frame-scoped result are all untouched.

New flag: `Settings.run_assembly_api_optin` (env `TL2_RUN_ASSEMBLY_API_OPTIN`, default OFF)
Export: `truelinev2/proof/export_run_assembly_cards_json.py` (`generate_export`/`build_export`/`validate_export`)
Route: `truelinev2/api/run_assembly_routes.py` (`GET /v2/reviewer/run-assembly`, context-free)
Mount: `truelinev2/api/app.py` (one gated `include_router` block, mirroring `reviewer_api_optin`)
Proof: `truelinev2/proof/run_run_assembly_api_contract.py` (G1–G12 PASS)
Tests: `truelinev2/tests/test_run_assembly_api.py` (19 offline; mount gating + envelope contract)

## What it is

A read-only transport SURFACE, NOT product readiness. It follows the EXISTING v2
reviewer-API pattern (`api/reviewer_routes.py` + `proof/export_reviewer_bundle_json.py`):
a proof-side `generate_export()` wraps the service output in a validated envelope
(`truelinev2-web-run-assembly-export-1`), consumed by a context-free GET route that
caches on `app.state` and 503s when inputs are missing. The cards keep their own M9.4.1
schema (`truelinev2-run-assembly-review-1`) — the envelope is a transport wrapper, never
a new product bucket. The route mounts ONLY when the new default-OFF flag is enabled,
independent of `reviewer_api_optin`.

## The transport CONSUMES the service (it reimplements nothing)

`generate_export()` builds `RunAssemblyReviewService` (injecting the KMZ model, the
`BRENHAM_TERMINUS_PROFILE`, and the banked `log44` source-contradiction set — all in
`proof/`, the literal-permitted layer) and calls `.generate()` verbatim. It never
re-runs `extract_run_assembly` / `build_run_assembly_cards`, never touches the per-bore
bundle, never calls `resolve_bore`/`run_match`/sweep/render. **G12 byte-compares the
envelope cards (full dict, every field) against a direct `service.generate()` call** — the
transport is provably verbatim.

## Emitted cards (exactly the M9.4.2 cards, unchanged)

- `log10` END → `log27` START @ AP-152 = **RUN_CONTINUATION_CANDIDATE**
- `log72` END → `log39` START @ AP-117 = **RUN_CONTINUATION_CANDIDATE**
- `log7` END → `log65` START @ AP-163 = **JUNCTION_DROP_BRANCH** (`log65` departs as a
  drop because its source prints `FOR FIBER DROP`; `departure_run_class == 'drop'`)

Every card: `label = SUGGESTION_NOT_PLACEMENT`, `auto = False`, `has_geometry/has_strokes
= False`, `competing_departures == 1` (the M9.5 frame-scoped guarantee, carried verbatim).

## The contract is fail-closed (validation IS the contract)

`validate_export` rejects, fail-closed: envelope-schema drift; a non-full-SHA
`source_git_head`; service/card-schema drift; any extra top-level or source key (strict
allowlists — a smuggled `lane_counts`/bucket key is rejected); any geometry/stroke/bucket
key anywhere (incl. nested in the `Any`-typed `terminal_ap`); a `.png` token as a string
VALUE *or* a dict KEY; suggestion-label drift; and each card is re-validated through the
M9.4.1 `RunAssemblyReviewCard` contract + a `model_dump` round-trip (an extra/unknown card
field fails the round-trip; a `DROP_BRANCH` without a `'drop'` departure is rejected).

## The seven proof questions

1. **Pattern to follow:** the existing reviewer-API pattern — proof-side export envelope
   (`export_reviewer_bundle_json`) consumed by a flag-gated, context-free GET router
   (`reviewer_routes`) mounted under a default-OFF `Settings` flag.
2. **Read-only without mutating the bundle?** Yes — per-bore `ReviewerBundleService`
   bundle is byte-identical before/after the export (G8); the export builds its own
   `PlanPdf` and closes it; no shared mutable state.
3. **Default flag safely OFF?** Yes — `run_assembly_api_optin` defaults False in
   `Settings`/`from_env`/`for_proof`; `create_app(OFF)` mounts no route; the import is
   lazy inside the gated block; the two opt-in flags are independent (all 4 combinations
   verified).
4. **Output matches M9.4.2 exactly?** Yes — G2 (the 3 cards) + G12 (full-dict verbatim vs
   a direct `service.generate()`).
5. **log65 stays DROP_BRANCH?** Yes (G3) — positively detected drop, hard-coupled in the
   M9.4.1 card validator and re-checked by `validate_export`.
6. **Any placement/AUTO/geometry/render/UI/deploy path?** No (G5/G9/G11) — read-only;
   no PNG; no placement/render call; no UI/deploy; zero bores moved.
7. **M9.5 preserved (no core widen / no cross-sheet)?** Yes (G9) — `competing_departures
   == 1` on all cards; the route + export reference no cross-sheet / frame-graph /
   placement symbols.

## Adversarial audit (5 refutation lenses) — every finding fixed + gated pre-commit

Additive/posture, default-OFF/security, fail-closed contract, no-overclaim, exact-cards/
M9.5/completeness. The milestone was **confirmed sound** — no lens refuted the core claims
(additive-only diff: `config.py` +6, `app.py` +4, 4 new files; zero core/review/service
changes; default-OFF; no auth regression; no overclaim; exact cards; M9.5 preserved). Three
low-severity findings were converted to fixes + measured gates:

- **PNG guard asymmetry** — `validate_export` checked `.png` on string values but not dict
  keys (latent, since `terminal_ap` is always scalar). Fixed: key-side `.png` check;
  pinned by G5 `png_as_dict_key` + a test.
- **Poisoned-cache → 500** — the per-call cache re-validation sat outside the 503 handler
  (faithful to the existing `reviewer_routes` seam, not a regression). Fixed in the new
  route: corruption now maps to 503; pinned by `test_route_poisoned_cache_is_503`.
- **No verbatim gate** — G2 checked only 4 fields vs a literal. Added **G12**: full-dict
  byte-equality vs a direct `service.generate()`.

**Recorded, NOT a defect (out of scope):** importing the route transitively loads
`truelinev2.render` into `sys.modules` via the shared `proof.run_brenham_corpus →
service → render.crop` chain — but render is never executed and the EXISTING
`reviewer_routes` has the identical chain, so M9.6 introduces no new posture regression.
Removing that import-time coupling is a pre-existing cleanup, explicitly out of scope for
this no-refactor milestone.

## Posture

Read-only / additive: full v2 suite **797 passed** (794 baseline + 3 new); guards green;
M9.4.2 + M9.5 proofs re-confirmed PASS. Tracked diff is exactly `config.py` (+6) and
`app.py` (+4); 4 new files in `api/`/`proof/`/`tests/`; ZERO changes to `match/` or
`schema/` (shared core untouched). No frontend/Vercel/UI, no Render/Vercel deploy, no
main/v1/production, no placement-path wiring, no AUTO, no geometry/strokes/PNG, no
product-bucket movement, no reviewer-bundle mutation, no cross-sheet / M9.2 widen.

## Next step (separate, authorization-gated; NOT begun)

A frontend/Vercel UI that renders these cards is a separate, authorized milestone — not
begun here, no deploy. The cards remain a read-only, default-OFF transport surface.
