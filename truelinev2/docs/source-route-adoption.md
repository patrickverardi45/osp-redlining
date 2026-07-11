# Source-route adoption (Phase 2, T31 + fix-wave W-B-FIX)

> **Fix-wave note**: this doc was revised after a blind-verification pass (Sol T38) found nine gaps against the
> pinned spec — epsilon-weakened geometry rules, an eager module import, a missing row-evidence hash, a
> reachable-but-untested `CONTROL_MISMATCH` code, and undisclosed temp-directory writes. All nine are fixed and
> test-locked; this revision reflects the SHIPPED (fixed) behavior, not the original T31 landing.
>
> **Fix-wave-2 note (T39 re-verification)**: a second pass found test-fidelity gaps (a coarse `5e-7` connector
> lock, a real-fixture same-segment test that only clicked segment endpoints, canonicalized-dict byte-identity,
> a `0.05`pt station-dot tolerance, a v1-vs-v2 equality test that never called closeout/export) and two real
> behaviors — the temp-workdir hardening check ran before its own cleanup `try`, and the endpoint-ordering
> table above needed to document resource-first + framework 422 as the TRUE (already-correct) shipped order,
> not merely as claimed. All are fixed/documented and test-locked (see the "Tests" section's fix-wave-2 G1–G9
> pointers); the `_patch_bent_geometry` test-local synthetic-geometry helper is DELETED in favor of a real,
> additive, non-collinear multi-bend QA scenario (G8/G9 below).

A source-backed, server-owned alternative to the two-click manual redline: given a verified
`READY_FOR_REVIEW_REDLINE` observer backbone (the SAME route the readiness spine already verifies for the
REVIEW-candidate lane) and exactly two HUMAN clicks on the same page, the server *projects* those clicks onto
the backbone, *clips* the backbone between the projections, and returns a *proposal* — a stateless, content-
addressed, human-reviewable route the operator may then *adopt* at create time. It never invents geometry:
every accepted point is either a human click or a vertex/projection taken directly from the observer-exposed
backbone. It is stricter than "every READY route" — a hypothesized gap-bridge reconnection, an ambiguous
projection, or a control beyond the drawn extent all refuse rather than guess.

**Design authority**: `.foreman/scratch/sol-p2-spec-out.md` (T31, pinned Q1–Q9) + the foreman ticket's P1–P11
pins, which WIN over spec ambiguity. This doc summarizes the SHIPPED behavior; the spec is the design record.

## Flag — `TL2_SOURCE_ROUTE_ADOPTION_API_OPTIN`

Default OFF. `Settings.source_route_adoption_api_optin: bool = False`.

Mounted (the proposal router) ONLY when **all three** are True:
`product_pipeline_api_optin AND product_readiness_api_optin AND source_route_adoption_api_optin`.

Adoption-at-create (the `route_adoption` extension on the EXISTING `POST /v2/product/jobs/{job_id}/source-anchors`)
checks the SAME three settings when `route_adoption` is present in the request; with any of them OFF, the
request is refused `400 ROUTE_ADOPTION_INVALID: source-route adoption is not enabled` **without importing or
running any readiness/hash/projection code**.

**OFF is byte-identical**: with the new flag OFF (or with the flag ON but `route_adoption` absent from the
request), `SourceAnchorCreate` follows the EXISTING unchanged v1 path verbatim — same record bytes, same
renderer inputs, same manifest/closeout/billing/export/photos/station-dots (test-locked byte-for-byte, not just
field-presence — see `test_flag_off_and_on_without_adoption_produce_byte_identical_records`). The ENTIRE
`contracts.source_route_adoption` module (derivation functions AND its `RouteAdoptionError` exception classes)
and `harness.product_readiness_bridge.run_job_route_readiness_raw` are imported LAZILY, inside the
`route_adoption` branch of `create_source_anchor_route` only — **never at module import time, not even the
exception classes** (fix-wave F6: the original landing eagerly imported the exception classes at module scope
so `_to_http`'s isinstance dispatch could reference them; `product_pipeline_routes.py` now maps a
`RouteAdoptionError` by reading its `.code` string attribute — duck typing — so it needs zero reference to the
module at all with the flag off). Verified by
`test_source_route_adoption_api.py::test_flag_off_never_imports_the_adoption_module`, a FRESH-subprocess
`sys.modules` probe (in-process would be contaminated by other test modules' own module-scope imports of
`contracts.source_route_adoption` at pytest collection time).

## API surface

### `POST /v2/product/jobs/{job_id}/source-route-proposals`

Read-only-by-effect: runs no renderer, writes no readiness result, creates no artifact, changes no job state.
Request: `{plan_upload_id, reviewed_bore_log_id, row_id, page_number, control_points: [start, end]}`.

Join order (server-side, never trusting client-declared identity beyond IDs):

1. Load tenant/job (404/403 on miss/cross-tenant).
2. Load the selected plan upload (404 if not a `PLAN_PDF` in this job) + the selected reviewed_bore_log (404).
3. Require the row to be engine-eligible (`ROW_NOT_ENGINE_ELIGIBLE` REFUSAL otherwise).
4. Require the row's `source_upload_id` to equal the reviewed_bore_log's own `source_upload_id`
   (`ROW_SOURCE_UPLOAD_MISMATCH`).
5. Run the UNCHANGED readiness spine (`run_package_route_readiness`), FILTERED to *only* the selected plan +
   BORE_LOG uploads (never the job's full upload set), artifact-free, no store write.
6. Non-READY spine status → the two-level taxonomy: `refusal.code = "ROUTE_EVIDENCE_NOT_READY"`,
   `refusal.upstream_reason_code = <the spine's own status>` (verbatim, never invented).
7. Require exactly one route-ready verification (`MULTIPLE_READY_CANDIDATES` otherwise).
8. Require the candidate span's stations to equal the row's EFFECTIVE stations (raw < normalized <
   `review.corrected_values` precedence, `truelinev2.stations.parse_station` comparison) — `ROW_SPAN_MISMATCH`.
9. Require the resolved PDF page to equal the request's `page_number` — `CROSS_PAGE_CANDIDATE`.
10. Project the two human controls onto the verified backbone (pure; see "Geometry" below).

Response is **HTTP 200 on both outcomes** — a defensible "no proposal" is an expected search result:

```json
{"outcome": "PROPOSAL", "proposal": {...}}
{"outcome": "REFUSAL", "refusal": {"code": "...", "message": "...", "upstream_reason_code": null, "warnings": []}}
```

Malformed request identity / non-finite controls / a control count != 2 is `HTTP 400`.

### `POST /v2/product/jobs/{job_id}/source-anchors` (existing endpoint, extended)

`SourceAnchorCreate` gains one optional field, `route_adoption`. Fix-wave **F7** extended it beyond the
original `{proposal_hash, confirmed}` pair into a full ECHO of the proposal binding the client claims to
adopt:

```json
{"proposal_hash": "sha256:...", "confirmed": true,
 "plan_upload_id": "up-...", "reviewed_bore_log_id": "rbl-main", "row_id": "row-1", "page_number": 20,
 "control_points": [{"x": 101.25, "y": 220.5}, {"x": 487.75, "y": 391.0}]}
```

The echo is a **client CLAIM used only to REFINE which refusal code a mismatch produces** — it is NEVER
trusted to grant adoption. The create request's OWN top-level fields (`plan_upload_id` /
`reviewed_bore_log_id` / `row_ids[0]` / `page_number` / `control_points`) are ALWAYS the source of truth for
what gets re-derived and stored; the server **re-derives** the SAME join + projection from those OWN fields
(never trusting the client's prior proposal call or its echo), and the full re-derived-hash comparison against
`route_adoption.proposal_hash` remains the **SOLE grant gate** — nothing the echo claims can cause adoption
without the hash matching.

### Refusal ORDER at the endpoint boundary (fix-wave-2 G3 — FOREMAN RULING, amended)

The ORDER a real HTTP request to `POST /v2/product/jobs/{job_id}/source-anchors` is actually evaluated in —
three tiers, in this sequence, EVERY request:

1. **Request-SHAPE validation (framework, before any route code runs).** FastAPI/Pydantic parses + validates
   the JSON body against `SourceAnchorCreate` (and, when `route_adoption` is present, against the NESTED
   `RouteAdoptionIn` model — every one of its seven fields, including the five identity/control-point ECHO
   fields, is REQUIRED). A missing or mistyped field anywhere in the body — including a missing
   `route_adoption.page_number` — never reaches product code at all: it is a **framework-standard HTTP 422**,
   not a code-first 400. This is FastAPI's own behavior, unconditional, and applies identically whether or not
   `route_adoption` is present.
2. **Resource resolution (existing 404/403/409 conventions, BEFORE any adoption validation).** In this order:
   the `source_anchor_id` must not already exist (409 conflict); the `job_id` (+ tenant) must resolve (404, incl.
   cross-tenant isolation); the `plan_upload_id` + `page_number` must resolve to real page bounds (404). This
   happens for EVERY request — `route_adoption` present or not — and happens even when the submitted
   `route_adoption` body is itself malformed or semantically invalid: a nonexistent `plan_upload_id` combined
   with `confirmed: false` returns **404**, never `400 ROUTE_ADOPTION_INVALID`.
3. **Adoption-specific validation** (only once (1) and (2) have both passed, and only when `route_adoption` is
   present): the flag-gate check (400 `ROUTE_ADOPTION_INVALID` if the three-way flag isn't enabled), then the
   `route_adoption`-present `plan_upload_id` must name a real `PLAN_PDF` upload on the job (404), then
   `_rederive_route_adoption` runs its OWN internal order (the table below) — step 0 of THAT table
   (`ROUTE_ADOPTION_INVALID` for a well-typed-but-semantically-invalid adoption: `confirmed != true`, a
   malformed `proposal_hash` string, or a control-point COUNT that mismatches, as opposed to a MISSING field,
   which tier 1 already caught) is therefore always reached AFTER every resource in tier 2 has resolved.

Create-time failures WITHIN tier 3 (repo `_to_http` convention: the code LEADS the `detail` string, e.g.
`"ROUTE_ADOPTION_STALE: ..."`, never an object detail — asserted by exact `detail.split(":")[0] == code`
equality in the tests, never `startswith`), checked in this ORDER:

| # | Condition | HTTP | Code |
|---|---|---|---|
| 0 | `control_points` count != 2 (create request OR echo), `confirmed != true`, or a malformed `proposal_hash` string | 400 | `ROUTE_ADOPTION_INVALID` |
| — | `row_ids` doesn't contain exactly one id, or `group_id` is set (route adoption is single-row-scoped) | 409 | `ROUTE_ADOPTION_SCOPE_MISMATCH` |
| 1 | Echo identity tuple (`plan_upload_id`/`reviewed_bore_log_id`/`row_id`/`page_number`) != the create request's OWN identity tuple | 409 | `ROUTE_ADOPTION_SCOPE_MISMATCH` |
| 2 | Echo `control_points` != the create request's OWN `control_points` | 409 | `ROUTE_ADOPTION_CONTROL_MISMATCH` |
| 3 | Current re-derivation itself refuses (any Q2/Q3 code) | 409 | `ROUTE_ADOPTION_NO_LONGER_DEFENSIBLE` (nested current refusal code + message in the detail) |
| 4 | Current re-derived hash differs from the submitted `proposal_hash` | 409 | `ROUTE_ADOPTION_STALE` |

`ROUTE_ADOPTION_CONTROL_MISMATCH` is reachable in this implementation (fix-wave F7 — see step 2 above); the
prior landing's "reserved, not raised" limitation is resolved.

Test-locked at the REAL ASGI request boundary (`test_source_route_adoption_api.py`, fix-wave-2 G3): a missing
echo field → 422; `confirmed: false` with otherwise-valid resources → 400 with an EXACT `ROUTE_ADOPTION_INVALID`
leading token; a nonexistent plan + a malformed `route_adoption` body → 404 (resource-first, never the 400 the
malformed body would otherwise produce).

On success the stored record is `record_format = "trueline-source-anchor-2"`; `control_points` holds the
SERVER-DERIVED render polyline (so the EXISTING renderer / station-dot call path consumes it unmodified — see
"Reader survey" below); the exact human clicks + source candidate geometry live separately under
`route_adoption` (never described as human-clicked).

## Geometry (pure, `contracts/source_route_adoption.py`)

No I/O, no fitz/PlanPdf import. Given the observer backbone (`RouteVerification.route_geometry` — ordered
`{"a": (x,y), "b": (x,y)}` segments) and the inherited `reach_tol` (read from
`RouteVerification.detail["isolation"]["detail"]["reach_tol"]` — **never hardcoded**):

> **Fix-wave F1/F2/F3/F4**: every geometric proximity/contiguity/tolerance/dedup/connector/same-segment rule
> below is EXACT — no epsilon anywhere. The only remaining tolerance in the module (`_TIE_EPS = 1e-9`) exists
> solely to group multiple independently-computed candidate distances that are the SAME real number (float
> `hypot` last-bit noise at a shared vertex) into one tie set — it never treats two different physical
> locations as equal.

1. **Backbone ordering/contiguity**: convert segments to an ordered point chain; every `segments[i].b` must
   equal `segments[i+1].a` **EXACTLY** (after `-0.0` → `0.0` normalization ONLY — no proximity epsilon) or
   refuse `BACKBONE_DISCONTINUOUS`. A gap as small as `1e-7` is a DIFFERENT point, full stop; two backbones
   differing only by an undrawn sub-`1e-6` gap can never hash identically (the old `1e-6` weld would have
   silently collapsed them to the same point chain).
2. **Gap-bridge gate**: `gap_bridge_status == "ROUTE_GAPS_BRIDGED"` refuses
   `BACKBONE_CONTAINS_HYPOTHETICAL_GAP_BRIDGE` (a bridge is a continuity HYPOTHESIS, never a drawn stroke).
3. **Tolerance**: missing/non-finite/non-positive `reach_tol` refuses `SOURCE_TOLERANCE_UNAVAILABLE`.
4. **Projection**: each human control projects (clamped `t ∈ [0,1]`) onto every backbone segment; the nearest
   wins. A distance TIE across segments with the SAME chainage (a shared vertex) is accepted deterministically
   (lowest segment index); a tie at DIFFERENT chainages refuses `AMBIGUOUS_START_PROJECTION` /
   `AMBIGUOUS_END_PROJECTION`. Acceptance is **`distance <= reach_tol`, EXACT, no epsilon** —
   `math.nextafter(reach_tol, +inf)` at that distance refuses `START_CONTROL_OUTSIDE_TOLERANCE` /
   `END_CONTROL_OUTSIDE_TOLERANCE`. An unclamped projection parameter before the first segment or past the last
   refuses `START_CONTROL_BEYOND_BACKBONE_EXTENT` / `END_CONTROL_BEYOND_BACKBONE_EXTENT`.
5. **Control-pair classification** (`classify_control_pair`, directly unit-tested): both controls on the same
   backbone segment → `CONTROLS_ON_SAME_BACKBONE_SEGMENT`, **UNCONDITIONALLY — including a genuinely
   single-segment backbone** (fix-wave F4: the prior "exempt when the backbone has only one segment" rule is
   REMOVED; a straight sub-segment of a single straight segment proposes nothing over the honest manual
   straight line, so a one-segment READY backbone can never produce a source-backed proposal — only a
   multi-segment backbone with a real bend can). Checked BEFORE the coincide check. Equal chainage (exact) →
   `CONTROL_PROJECTIONS_COINCIDE`; start chainage > end chainage → `CONTROL_ORDER_REVERSED`.
6. **Clip**: `[start_projection] + every original vertex with chainage STRICTLY (exact) between start/end +
   [end_projection]` — no simplification, densification, or invented bend.
7. **Render polyline**: `[human_start] + clip + [human_end]`, consecutive EXACT duplicates removed (fix-wave
   F3: no proximity dedup — a near-but-not-identical point is NEVER silently collapsed). A nonzero connector
   (human click ≠ its projection, exact comparison) is recorded as the `HUMAN_CONTROL_TO_BACKBONE_CONNECTOR`
   warning, and BOTH the human click and its projection are stored as distinct points — the operator's exact
   click is NEVER silently snapped to its projection.
8. Zero-length clip or render (exact `== 0.0`) → `ZERO_LENGTH_PROPOSAL`.

## Hashing (Q4 + fix-wave F5)

Two hashes, both `sha256:<64-hex>` over sorted-key, compact-separator, finite-numbers-only canonical JSON
(`-0.0` normalizes to `0.0`; a non-finite number raises rather than hashing silently):

- `candidate_route_hash` — the SOURCE geometry only (algorithm version, plan/span/readiness identity, tolerance,
  full backbone, clipped candidate route) — independent of the human clicks; detects when the underlying
  observer evidence changed.
- `proposal_hash` — everything `candidate_route_hash` covers PLUS the scope (tenant/job/plan/rbl/row/page), the
  exact two human controls, both projections, and the final render polyline. This is the hash the client
  round-trips through `route_adoption.proposal_hash`; a mismatch on re-derivation is `ROUTE_ADOPTION_STALE`.

Both hashes fold in `span_source.row_evidence_hash` (fix-wave F5, `row_evidence_hash()`): a canonical hash of
the selected row's **FULL effective merged values** — the SAME `raw < normalized < review.corrected_values`
precedence `row_effective_stations` uses, but every field, not just stations. Correcting ANY reviewed value on
the row (e.g. depth, with stations left untouched) between proposal generation and create therefore changes
the hash and invalidates the proposal (`ROUTE_ADOPTION_STALE` on create), closing the gap where a station-only
comparison would have silently adopted geometry bound to stale row evidence.

`proposal_id = "rap-" + proposal_hash_hex[:24]`.

## Temp-directory disclosure (fix-wave F8)

`harness.product_readiness_bridge.run_job_route_readiness_raw` (the raw readiness seam both the proposal
endpoint and create-time re-derivation call) materializes the selected upload BYTES (hardlinked or copied) into
a real `tempfile.mkdtemp(prefix="tl2_route_adoption_")` directory under the OS temp root for the duration of
one call, and deletes it in a `finally` block. This is a KNOWN, ACCEPTED trade-off of the stateless design (Q4:
"avoids a new mutable record and stale cleanup, but repeats the readiness computation"), not a silently hidden
one: a process kill between creation and cleanup can leave that directory behind on disk (crash residue) until
OS temp-cleanup reclaims it.

Both call sites now pass `store_root=<the product store root>` (additive keyword; `None` preserves prior
behavior byte-identically for any other caller). With `store_root` supplied, the function **asserts at
creation** that the resolved temp work directory is NOT under the store root, and raises
`UnsafeTempWorkdirError` rather than proceeding if it is — proving the transient write can never be confused
with, or become reachable through, the durable store tree (test-locked in
`test_source_route_adoption_bridge.py`).

> **Fix-wave-2 G4**: the assertion runs INSIDE the `try`/`finally` (immediately after `mkdtemp`, before any
> other work), never before it — so an unsafe-workdir refusal still reaches the `finally` cleanup and removes
> the just-created directory. A process temp root that is itself misconfigured to sit under the store root
> (not a crash — an ordinary refusal path) therefore still leaves **zero residue**, test-locked by rooting the
> process temp dir inside the store (`monkeypatch.setattr(tempfile, "tempdir", ...)`) and asserting both the
> named refusal and an unchanged store tree afterward.

## Known limitation — none remaining for `ROUTE_ADOPTION_CONTROL_MISMATCH`

Resolved by fix-wave F7: the create request's `route_adoption` block now carries a full ECHO of the proposal
binding (`plan_upload_id` / `reviewed_bore_log_id` / `row_id` / `page_number` / `control_points`), which lets
the server distinguish "the echoed control_points disagree with what's actually being created" (409
`ROUTE_ADOPTION_CONTROL_MISMATCH`) from "the underlying evidence changed since the proposal" (409
`ROUTE_ADOPTION_STALE`, still the sole grant-gate signal) BEFORE re-derivation runs. The echo is a client CLAIM
used only to select the refusal code — the full hash comparison against `proposal_hash` remains the only path
to a successful adoption, regardless of what the echo says.

## Reader survey (P5) — every consumer of a source-anchor record

| Consumer | Change | Why it needed none / what changed |
|---|---|---|
| `render/source_anchor_render.py` | **None.** | Reads `sa.get("control_points", [])` generically — no `record_format` check. A v2 record's server-derived N-point polyline flows through the EXISTING renderer unmodified. |
| `render/station_dots.py` | **None.** | `compute_station_dots(control_points, ...)` already interpolates along whatever polyline it is given; an adopted N-point path rides the same interpolation. |
| `contracts/source_anchor.py::build_source_anchor_manifest` | **Additive.** | Emits `geometry_basis` / `confirmation_state` / `render_control_points` / `route_adoption` on a log entry ONLY when the underlying record carries `geometry_basis` (i.e. is v2); a manual record's log is byte-identical to before. |
| `contracts/redline_manifest.schema.json` | **Additive.** | The four keys above added under `properties` (never `required`) so `additionalProperties:false` still accepts legacy manifests that omit them. |
| `contracts/closeout_pdf.py` (Artifact Detail, §5) | **Additive.** | "Geometry: source-backed observer backbone — HUMAN_REVIEWED adoption" + source sheet/page + proposal hash + warnings, emitted ONLY when `log.get("geometry_basis")` is present; absent fields → the existing path/output is untouched. |
| `api/product_pipeline_routes.py` GET `/source-anchors[/{id}]` | **None.** | Returns the stored record verbatim (v1 or v2) — no shape assumption. |
| Closeout acceptance policy / AUTO placement policy | **Untouched (hard fence).** | Adoption is REVIEW evidence with explicit human confirmation, same as a manual anchor; it never counts toward the deterministic frontier and never overrides a banked human grade. |

## Refusal-code inventory

**Q3 geometry/connectivity** (pure, `contracts/source_route_adoption.py`): `BACKBONE_EMPTY`,
`BACKBONE_MALFORMED`, `BACKBONE_DISCONTINUOUS`, `BACKBONE_CONTAINS_HYPOTHETICAL_GAP_BRIDGE`,
`SOURCE_TOLERANCE_UNAVAILABLE`, `START_CONTROL_OUTSIDE_TOLERANCE`, `END_CONTROL_OUTSIDE_TOLERANCE`,
`AMBIGUOUS_START_PROJECTION`, `AMBIGUOUS_END_PROJECTION`, `START_CONTROL_BEYOND_BACKBONE_EXTENT`,
`END_CONTROL_BEYOND_BACKBONE_EXTENT`, `CONTROL_PROJECTIONS_COINCIDE`, `CONTROL_ORDER_REVERSED`,
`CONTROLS_ON_SAME_BACKBONE_SEGMENT`, `ZERO_LENGTH_PROPOSAL`, `CROSS_PAGE_CANDIDATE`,
`MULTIPLE_READY_CANDIDATES`, `MALFORMED_CONTROL_POINTS`.

**Q2 join-level** (foreman P2): `ROUTE_EVIDENCE_NOT_READY` (carries `upstream_reason_code`),
`ROW_NOT_ENGINE_ELIGIBLE`, `ROW_SOURCE_UPLOAD_MISMATCH`, `ROW_SPAN_MISMATCH`.

**Q4 create-time** (`RouteAdoptionError` subclasses): `ROUTE_ADOPTION_INVALID` (400),
`ROUTE_ADOPTION_CONTROL_MISMATCH` / `ROUTE_ADOPTION_STALE` / `ROUTE_ADOPTION_NO_LONGER_DEFENSIBLE` /
`ROUTE_ADOPTION_SCOPE_MISMATCH` (409, each).

## Tests

`truelinev2/tests/test_source_route_adoption_geometry.py` (pure module, every refusal code + hash stability/
sensitivity + exact-tolerance/exact-contiguity/unconditional-same-segment locks, incl. the fix-wave-2 G1
adversarial `5e-7` connector lock), `test_source_route_adoption_bridge.py` (additive bridge params,
byte-identity + filtering + the F8 temp-workdir-outside-store-root proof, incl. the fix-wave-2 G4
process-temp-dir-inside-store no-residue proof), `test_source_route_adoption_api.py` (end-to-end: mounting,
flag OFF/ON RAW STORED-FILE-BYTES + RAW HTTP-RESPONSE-BYTES identity (fix-wave-2 G5), a fresh-subprocess
`sys.modules` import-isolation proof, proposal happy-path + refusals against REAL source-backed geometry read
off the fixture-free `complete_package_qa` spine — including a real single-segment backbone proving the F4
same-segment refusal end-to-end with BOTH the segment's own endpoints AND two MID-SEGMENT interior controls
(fix-wave-2 G2) — adoption round-trip, stale/invalid/scope-mismatch/control-mismatch/no-longer-defensible
(including the F5 row-evidence-hash staleness case), the fix-wave-2 G3 amended endpoint-ordering proofs at the
REAL ASGI request boundary (422 for a missing echo field, exact-split-token 400/409 codes, resource-first 404),
tenant isolation, manifest/closeout/on-polyline station-dot flow-through (fix-wave-2 G6: `<= 1e-9` true
on-polyline distance against an independently-recomputed exact point), and a v1-manual-vs-v2-adopted
output-equality proof for identical geometry that ALSO calls the real closeout-PDF-build and
export/bundle-assembly paths for both records (fix-wave-2 G7)).

**Fix-wave-2 G8/G9 (Item-10 ruling)**: a real single-segment READY backbone (the `complete_ready` QA fixture —
a straight terminus-to-terminus run) ALWAYS refuses `CONTROLS_ON_SAME_BACKBONE_SEGMENT` under fix-wave F4; the
happy-path / reader-survey tests that need a genuinely successful multi-segment adoption now bind to a NEW,
ADDITIVE `harness.complete_package_qa` scenario, `"bent_ready"` (`ROUTE_BENT` route shape) — a genuinely
non-collinear, real, UNPATCHED 3-segment / 2-bend observer backbone reaching `READY_FOR_REVIEW_REDLINE` through
the UNMODIFIED spine, exactly like `complete_ready` but with real preserved bends. The prior test-local
`_patch_bent_geometry` helper (which split the real single-segment backbone into two SYNTHETIC collinear
segments after the fact) is DELETED: it manufactured exactly the segment boundary needed to flip the real
fixture's refusal into a success, so it could not prove adoption against the unmodified spine. All 7
pre-existing `complete_package_qa` scenarios (including `complete_ready` itself) are unchanged — `bent_ready` is
purely additive.
