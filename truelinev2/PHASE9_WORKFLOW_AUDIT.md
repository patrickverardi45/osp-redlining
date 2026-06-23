# Phase 9 — Full Product Workflow Audit + Integration (working notes)

Goal: make the product workflow actually run end-to-end against the PROVEN redline capability —
recognized deterministic package → real committed PNGs → closeout → export → (KMZ where honest) —
not a demo shell. Owned execution; no micro-questions.

## Architecture map — three redline paths (required order)

| Path | Contract | Input identity | Output | Provenance |
|---|---|---|---|---|
| **A. Recognized deterministic** | `recognized_corpus_handoff.py` | uploaded PLAN_PDF sha256 ∈ registry corpus AND engine-ready reviewed-bore-log's BORE_LOG sha256 → drawn `log_id` with committed PNG in `data/outputs/callout_route_assembly_sweep/` | serves EXISTING committed PNG(s) (render `c19b565`) as job-local bundle | `DETERMINISTIC_AUTO` / `DETERMINISTIC_RECOGNIZED_CORPUS` |
| **B. Uploaded supported REVIEW** | `uploaded_corpus_engine_handoff.py` + `review_acceptance.py` | uploaded plan + reviewed bore-log; engine `select_dialect`+`run_match` (default mode) places a drawable candidate | renders real `FINAL_REDLINE_PNG`; human accept/reject | `OWNER_CONFIRMED_HUMAN_ADJUSTABLE` → `ENGINE_GENERATED_HUMAN_ACCEPTED_REVIEW` (never AUTO) |
| **C. Unsupported / insufficient** | — | not recognized AND engine abstains / no dialect | nothing rendered; ABSTAIN with SPECIFIC reasons (recognized blockers + engine's own reason) | n/a — accept BLOCKED |

**Phase 8C disconnect:** the workspace `Generate` called ONLY path B (`review-candidates/generate`).
Path A was reachable only from the guided `?job=` demo, and the registry covered only `log8`.
So Patrick's `bore_log9` upload (a DRAWN deterministic log, PNGs `log9_s7`/`log9_s14` exist) hit
path B's default-mode `run_match` → `NO_AUTHORED_BOX_MATCH_FOR_BORE_SPAN` → ABSTAIN. **Disconnect, not honest abstain.**

## The fix (this phase)
1. **`product_workflow.py` (NEW orchestrator)** — `run_product_redline(...)`: try A (recognized) → else B
   (REVIEW/AUTO via generate_review_candidate) → else C (merged-reason ABSTAIN). Advance job lifecycle to
   PLACED after a successful render. `assemble_closeout_package(...)`: PLACED→CLOSEOUT_REVIEW, evaluate
   closeout, evaluate kmz, assemble export_package; unified summary. Reuses existing contracts read-only.
2. **Registry expansion (deployment DATA only)** — `data/recognized_corpus_registry.json`: add all **37
   PNG-reachable** drawn-log bore-log sha256 → log_id (incl. `log9`). 13 ALREADY_DRAWN logs not in the sweep
   dir → not serveable today (handoff-glob limit; documented, not faked).
3. **KMZ** — add a REAL binary `.kmz` writer (zip{doc.kml}) + structural validator + download route to the
   `kmz_export` lane. Product redline KMZ stays honest: pixel-only → `BLOCKED[UNSUPPORTED_PIXEL_ONLY]`,
   export OMITS with `KMZ_NOT_INCLUDED`. Prove the writer is Google-Earth-valid on REAL coordinates (from the
   uploaded design KMZ via `extract/kmz.py`) in a test; never inject coords into the redline truth path.
4. **Web** — workspace shows the 3 paths distinctly (recognized card BEFORE REVIEW); add closeout/export/KMZ
   panel + missing client fns (closeout evaluate/get, export assemble/get, kmz get+download, transition).
   Scrub the stray `Hector` comment (`ProductIntake.tsx:401`). Guided Hector demo untouched.

## Hard constraints / do-not-break
- Engine / renderer / fixtures / anchors / coordinates / `origin/main` / deploy: untouched.
- Frontier-lock + census tests MUST stay green: `test_all_redlines_closure_ledger.py` (58 ledger / 36 placed),
  `test_callout_route_assembly_sweep.py` (engine_census_frozen, no_fixture_mutation), frontier-lock 50/58.
- No fake AUTO, no fake PNGs, no invented coordinates, no manual source-anchor UI in product.
- Recognized registry stays gitignored (carries a real display_name); only generic ids cross the API.

## Backend route spine (ALL already exist in `api/product_pipeline_routes.py`)
project/jobs CRUD+transition · uploads · reviewed-bore-log gate · manifest-handoff · artifacts list/serve ·
recognized-corpus-handoff GET+/render · uploaded-corpus-engine-handoff GET+/render · review-candidates
generate/list/get/accept/reject · kmz-export GET · closeout evaluate+GET · billing compute+GET ·
export-package assemble+GET. Missing = the 3-path orchestrator + KMZ binary/download.

## Lifecycle / closeout facts
CREATED→UPLOADING→EXTRACTING→AWAITING_REVIEW→PLACING→PLACED→CLOSEOUT_REVIEW→CLOSED (linear; +→FAILED).
Slot-set & finalize_handoff do NOT transition — orchestrator must walk to PLACED. Clean closeout
auto-evaluates READY_FOR_APPROVAL (no privileged approve needed); export reaches READY. FINAL needs the
privileged closeout APPROVE (Slice-4 omits it → deferred to P5 auth). Billing cost-rules file absent →
billing is a non-blocking warning (export tolerates it).
