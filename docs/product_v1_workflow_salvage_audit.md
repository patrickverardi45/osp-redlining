# Product v1 Workflow — Salvage Audit

> Lane `TRUELINE_PRODUCT_V1_WORKFLOW_SALVAGE_AUDIT`, recorded 2026-06-20. **Read-only audit of the v1
> monolith** (`backend/`, `web/`, `extractor/` in this repo). Extraction + architecture only — NO v1
> behavior change, NO rebuild, NO migration. v1 is **reference**; the v2 engine owns placement truth.
> Companion: [`product_v2_permanent_pipeline_contract.md`](product_v2_permanent_pipeline_contract.md).
>
> **Naming rule honored:** this doc cites real v1 file paths (an audit must name what it audits), but every
> v2 recommendation/contract uses **generic product terms only** (`customer_project`, `upload_pipeline`,
> `processing_job`, `redline_manifest`, `artifact_bundle`, `export_package`, `closeout_review`,
> `billing_summary`, `kmz_export`, `review_queue`, …). Where v1 hardcodes a customer/project name into
> reusable code, that is flagged as a **`DO NOT COPY`** item.

## How to read this

Every discovered v1 behavior is classified as exactly one of:

| Class | Meaning |
|---|---|
| `SALVAGE_AS_PRODUCT_FLOW` | The *workflow/concept* is sound; re-realize v2-native (do not port code). |
| `SALVAGE_AS_UI_PATTERN` | The *UI/interaction pattern* is good; reuse as a design reference. |
| `SALVAGE_AS_EXPORT_PATTERN` | The *export structure/sections* are good; reuse the shape, not the plumbing. |
| `REFERENCE_ONLY_UNSAFE_GEOMETRY` | Worked on screen but geometrically unsafe (snapped/guessed coords). Study, never reuse for truth. |
| `REPLACE_WITH_V2_ENGINE_CONTRACT` | v1 did this wrong/absent; v2 must own it via a clean contract. |
| `DELETE_OR_IGNORE` | Dead, global-state, or actively harmful; do not carry forward. |

## Salvage classification table

| # | v1 behavior | v1 location | Class | One-line verdict |
|---|---|---|---|---|
| 1a | Accept PDF plan / bore-log CSV+PDF / KMZ+KML + job form metadata | `backend/app/api/upload.py`, `kmz_upload.py`, `bore_rows.py` | `SALVAGE_AS_PRODUCT_FLOW` | Right inputs; rebuild project-scoped + persisted. |
| 1b | Global `CURRENT_ROUTE` + single `bore_rows.csv` + local `UPLOAD_DIR` | `pipeline_state.py`, `upload.py:12` | `DELETE_OR_IGNORE` | Global mutable state; concurrent uploads clobber. |
| 1c | No tenant/project isolation, no auth on upload | (absence) | `REPLACE_WITH_V2_ENGINE_CONTRACT` | v2 must scope every route by `customer_project`. |
| 1d | Bore-log OCR (Tesseract, 4 image variants, per-field configs) | `services/bore_log_service.py` | `SALVAGE_AS_PRODUCT_FLOW` | Keep extraction; gate output behind review (untrusted). |
| 1e | `infer_station_sequence()` guesses missing stations from neighbors | `bore_log_service.py:262` | `REFERENCE_ONLY_UNSAFE_GEOMETRY` | Never auto-guess into truth; surface as a review suggestion. |
| 1f | Deterministic plan parser (regex + `pdfplumber`, safe-fail) | `services/engineering_plan_parser.py` | `SALVAGE_AS_PRODUCT_FLOW` | Clean extraction core; reuse the *concept*. |
| 1g | `build_segments()` = contiguous OCR rows → segments, no bore-ID grouping | `bore_log_service.py:294` | `REPLACE_WITH_V2_ENGINE_CONTRACT` | v2 must group multi-bore logs + review BEFORE placement. |
| 7a | Match Review Queue = pure observation of `pipeline_diag`, status/priority classes | `core/match_review_queue.py` | `SALVAGE_AS_PRODUCT_FLOW` + `SALVAGE_AS_UI_PATTERN` | Excellent read-only review pattern; keep. |
| 7b | Multi-axis evidence kept separate (route-index / plan-graph / location-mismatch) | `match_review_queue.py`, `trust_ledger.py` | `SALVAGE_AS_UI_PATTERN` | Never merge orthogonal signals; keep. |
| 7c | Evidence-resolver advisory decision tags (`PLACE_CONFIDENTLY` …) | `core/evidence_resolver.py` | `SALVAGE_AS_PRODUCT_FLOW` | Advisory-only is correct doctrine; keep. |
| 7d | No override/approval persistence (review is read-only, nothing is saved) | (absence; `match_override.py` unwired) | `REPLACE_WITH_V2_ENGINE_CONTRACT` | v2 needs a durable approval/override record + audit. |
| 7e | Trust Ledger honest verdicts (`proven` / `abstained` / `missing_proof`) | `core/trust_ledger.py` | `SALVAGE_AS_UI_PATTERN` | Honest degradation; keep. |
| 2a | Leaflet WGS84 map, KMZ context layer, color/width/dash styling | `web/.../ModernHeroMap.tsx`, `RedlineMap.tsx` | `SALVAGE_AS_UI_PATTERN` | Good proof-viewer UI; reuse as design reference. |
| 2b | Stations **snapped** to KMZ polylines (perpendicular projection), no ground-truth, no residual warning | `ModernHeroMap.tsx` `snapLatLonToKmzPolylines` | `REFERENCE_ONLY_UNSAFE_GEOMETRY` | Snaps to possibly-wrong geometry silently. |
| 2c | PDF page overlay georeferenced to **KMZ bounding box** | `ModernHeroMap.tsx:1231` | `REFERENCE_ONLY_UNSAFE_GEOMETRY` | Inherits KMZ offset/skew; not survey-grade. |
| 2d | Redline segments = `matched_route.coords` clipped by station→distance | `backend/main.py:6658` `_build_redline_segments_for_group` | `REPLACE_WITH_V2_ENGINE_CONTRACT` | Route-snapped, not engine-approved geometry. |
| 3a | "KMZ export" = JSON **render payload of the uploaded KMZ semantic features** (not a KMZ file, not approved redlines) | `backend/main.py:19116` `_build_kmz_render_payload`, `/api/engineering-kmz-payload` | `REFERENCE_ONLY_UNSAFE_GEOMETRY` + `REPLACE_WITH_V2_ENGINE_CONTRACT` | Re-exports the *input*; can be 100 m+ off. |
| 3b | KMZ semantic parse (folder/classification/chainage/lifecycle/style) | `core/kmz_parser.py`, `kmz_extractor.py`, `_build_kmz_semantic` | `SALVAGE_AS_PRODUCT_FLOW` | Good *input* parsing; never the export source. |
| 3c | Chainage regex-extracted from KML description text, no confidence in export | `main.py` `_kmz_semantic_extract_chainage` | `REFERENCE_ONLY_UNSAFE_GEOMETRY` | Guessed chainage exported as if ground-truth. |
| 3d | Auto-redline **R1 = SUGGESTION-GRADE ONLY, never exported** | `core/kmz_auto_redline.py` | `SALVAGE_AS_PRODUCT_FLOW` | The "suggestion-only until re-authorized" policy is correct v2 doctrine. |
| 3e | Anchor-builder confidence bands (high/med/low by perp distance) | `core/kmz_anchor_builder.py` | `SALVAGE_AS_PRODUCT_FLOW` | Keep the confidence concept; must reach the export. |
| 3f | No CRS/datum/projection metadata in any export | `_build_kmz_render_payload` | `REPLACE_WITH_V2_ENGINE_CONTRACT` | Every coordinate export must declare `EPSG:4326`/WGS84. |
| 4a | 8-gate closeout checklist (design/field/plans/decisions/photos/notes/status) | `web/.../CloseoutPacket.tsx:144` | `SALVAGE_AS_UI_PATTERN` | Sound gate model; keep. |
| 4b | Closeout lock/unlock, permission-gated (admin/manager) | `backend/main.py:23165/23208` | `SALVAGE_AS_PRODUCT_FLOW` | Keep the concept; persist + audit it. |
| 4c | **THREE disagreeing readiness signals** (panel counts / Nova diagnostics / `billingApproved` client flag) | `CloseoutReadinessPanel.tsx`, `buildNovaSummary.ts`, `CloseoutPacket.tsx` | `DELETE_OR_IGNORE` | The core defect: panels disagree; replace with one status model. |
| 4d | Lock state in in-memory `STATE.closeout_lock` (lost on restart), no audit trail | `backend/main.py` | `DELETE_OR_IGNORE` | Ephemeral, unauditable. |
| 5a | Billing = client-computed props (`footage × rate + exceptions`); `billing.py` is a placeholder | `CloseoutPacket.tsx:62`, `backend/app/api/billing.py` | `REPLACE_WITH_V2_ENGINE_CONTRACT` | No authoritative backend `billing_summary`. |
| 5b | Itemized exception model (label / amount / notes) | `office/CloseoutContentSummaryPanel.tsx` | `SALVAGE_AS_PRODUCT_FLOW` | Good line-item shape; keep. |
| 6a | Closeout packet = 8-section HTML, inline photos, browser print-to-PDF | `CloseoutPacket.tsx` `buildPrintHtml`/`handlePrint` | `SALVAGE_AS_EXPORT_PATTERN` | Keep the section structure; produce a reproducible server artifact. |
| 6b | No stored artifact / blob URLs / no versioning / `document.write` popup | `CloseoutPacket.tsx` | `DELETE_OR_IGNORE` | Ephemeral, fragile, unauditable export path. |
| X | Customer/project-name **hardcoded core modules** (e.g. `brenham_plan_sheet_graph.py`, "…PH5 fixture") | `backend/app/core/*`, web fixtures | `REPLACE_WITH_V2_ENGINE_CONTRACT` | v2 reusable code must be generic + `customer_project`-parameterized. |
| Y | v1 auth (JWT / pilot-token / TOFU) | `backend/app/auth*.py` | `REFERENCE_ONLY_UNSAFE_GEOMETRY`→reference-only | External provider replaces it; keep only the *tenant-isolation requirement*. |

## File / route / component map (per capability)

**1. Upload** — `backend/app/api/{upload.py, kmz_upload.py, bore_rows.py}`; `backend/app/services/{engineering_plan_parser.py, bore_log_service.py, bore_csv_loader.py}`; `backend/app/core/pipeline_state.py`; web `web/src/app/jobs/{page.tsx, inbox/page.tsx, [jobId]/page.tsx}`. Routes are mostly in `backend/main.py` + the `app/api/*` routers.

**2. Map / hero-map** — `web/src/components/{ModernHeroMap.tsx, RedlineMap.tsx}`; `web/src/lib/map/*`; `backend/app/core/{plan_overlay.py, plan_page_renderer.py, kmz_parser.py}`; redline geometry built in `backend/main.py:6658`.

**3. KMZ/KML export** — `backend/main.py:19116` (`_build_kmz_render_payload`) + `:19599` (`/api/engineering-kmz-payload`); `backend/app/core/{kmz_auto_redline.py, kmz_anchor_builder.py, kmz_stage_b2_streets.py, kmz_extractor.py, kmz_parser.py}`; `backend/app/api/{kmz_upload.py, kmz_debug.py}`.

**4. Closeout review** — web `web/src/components/office/{CloseoutReadinessPanel.tsx, CloseoutContentSummaryPanel.tsx, SelectedSubmissionReviewPanel.tsx, OfficeMapReviewPanel.tsx}` + `web/src/components/CloseoutPacket.tsx` + `web/src/lib/nova/buildNovaSummary.ts`; backend `backend/main.py` closeout `lock`/`unlock` routes.

**5. Cost / billing** — `backend/app/api/billing.py` (placeholder); cost props in `CloseoutPacket.tsx`; readiness in `buildNovaSummary.ts`.

**6. Print / save / share** — `CloseoutPacket.tsx` (`buildPrintHtml`, `handlePrint`); `/api/nova-overrides` (review decisions). No server-side export route.

**7. Trust / evidence / review** — `backend/app/core/{match_review_queue.py, mrq_evidence_cache.py, evidence_resolver.py, notes_street_evidence.py, trust_ledger.py}`; web `web/src/app/{match-review/page.tsx, trust-ledger/page.tsx}`, `web/src/components/{MatchReviewQueuePanel.tsx, MatchReviewEvidence.tsx}`, `web/src/lib/types/matchReviewQueue.ts`, `web/src/lib/office/sessionReview.ts`.

## What worked (keep the concept)

- **Pure-observation review** — the Match Review Queue and Trust Ledger read diagnostics with zero side effects; re-runnable, honest, multi-axis (route-index / plan-graph / location-mismatch never merged).
- **Suggestion-only geometry policy** — `kmz_auto_redline.py` explicitly refuses to persist/export auto-redlines without re-authorization. This is *exactly* the v2 doctrine.
- **Deterministic plan extraction** — the plan parser is text-only, safe-fail, provenance-tagged.
- **Closeout gate checklist + permission-gated lock** — the 8-gate model and the lock concept are good.
- **Self-contained packet** — inline photo embedding makes the printed packet portable.

## What failed / was messy (the risks)

- **Global mutable state, no isolation** — `CURRENT_ROUTE`, single `bore_rows.csv`, local `UPLOAD_DIR`; concurrent jobs race; no `customer_project` scoping; no auth on upload.
- **Untrusted OCR straight to the engine** — handwritten bore-log OCR (with neighbor-guessing) feeds matching with no review gate.
- **Multi-bore logs not segmented before placement** — grouping happens *after* matching, so operators can't validate grouping first.
- **Geometry snapped to possibly-wrong references** — stations snap to KMZ polylines; PDF overlays georeference to KMZ bounds; no residual-distance sanity warning.
- **Export re-emits the input KMZ, not approved redlines** — with regex chainage and **no CRS** → exported coordinates can be 100 m+ off and carry no confidence.
- **Status fragmentation** — three readiness evaluators disagree; a **client-provided `billingApproved` flag overrides backend status**; lock state is ephemeral and unauditable.
- **Ephemeral exports** — packet is browser-only, blob-URL-fragile, unversioned, with no stored artifact.

## Explicit "DO NOT COPY" list

1. Global in-process state (`pipeline_state.CURRENT_ROUTE`, single `bore_rows.csv`, local `UPLOAD_DIR`). Partition everything by `customer_project` + `processing_job`.
2. Unauthenticated / unscoped routes. Every route is `customer_project`-scoped and auth-gated (external provider).
3. OCR/AI output flowing to the engine without a review gate. **AI/OCR output is untrusted until reviewed.**
4. Auto-grouping multi-bore logs *after* placement. Group + review *before* engine placement.
5. Snapping geometry to KMZ/streets and treating it as truth; PDF-overlay georeference from KMZ bounds; missing residual-distance warnings.
6. Exporting the uploaded KMZ (or route-snapped geometry) as the redline export. **Export only v2-approved `redline_manifest` geometry.**
7. Coordinate exports without a CRS/datum declaration or per-coordinate `source` + `confidence`.
8. Faking geometry when real lat/long is unavailable (interpolating points along a guessed route). **If coords are unavailable, do not fake a KMZ.**
9. Multiple disagreeing readiness signals; any client-provided flag that overrides backend status; ephemeral in-memory lock state.
10. Browser-only `document.write` print as the system of record. Produce a stored, versioned, reproducible `export_package`.
11. Customer/project-name-hardcoded reusable modules (e.g. `brenham_*`). v2 reusable code is generic + parameterized.
12. v1 auth implementation (JWT/TOFU). Reference only; the external provider replaces it. Keep only the cross-tenant-403 requirement.

## v2 recommendations (summary — full contracts in the companion doc)

- One **`processing_job`** lifecycle per `customer_project`, isolated end-to-end; uploads land in a versioned `artifact_bundle` store, never global state.
- **Reviewed-bore-log** stage between OCR and placement: group → validate continuity → human review → only then the engine consumes rows. OCR provenance + confidence travel with every cell.
- Geometry truth comes **only** from a reviewed engine `redline_manifest` or an approved human override; the map is a *viewer*, snapping is *display-only* and must warn on large residuals.
- **`kmz_export` / `kml_export`** serialize the approved `redline_manifest` geometry with a CRS header and per-feature `source`+`confidence`; abstain (no fake geometry) when coords are unavailable.
- One authoritative **`closeout_review`** status model; **`billing_summary`** computed and persisted server-side; **`export_package`** is a stored, checksummed, reproducible artifact.
- Keep the **`review_queue`** pure-observation pattern but add a durable **approval/override** record with audit fields.
