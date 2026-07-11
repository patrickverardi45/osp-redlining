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
   fields, is REQUIRED). Precisely (fix-wave-2 H1 — this is NOT a blanket "any mistyped field → 422" claim):
   a **missing** required field, or a field whose value Pydantic cannot COERCE to the declared type at all
   (e.g. `page_number: "abc"`), is a **framework-standard HTTP 422** — never reaches product code at all. A
   value Pydantic's (lax-mode) coercion CAN convert (e.g. `page_number: "5"` → `int` `5`, or
   `confirmed: "true"` → `bool` `True`) is silently coerced and proceeds as if the caller had sent the coerced
   type — it does NOT 422. This is FastAPI/Pydantic's own behavior, unconditional, and applies identically
   whether or not `route_adoption` is present.

   **Non-finite `control_points` (micro-round correction — the prior "non-finite → 422" example was FALSE):**
   Pydantic's `float` fields coerce the strings `"NaN"` / `"Infinity"` (and `math.nan` / `math.inf` themselves)
   WITHOUT raising — there is no 422 here. Non-finite control points are instead refused DOWNSTREAM, by three
   separate, real guarantees, each living in a different place for a different reason: (a) the PROPOSAL
   endpoint's own finiteness check, `_require_finite_control_points`
   (`truelinev2/api/source_route_proposal_routes.py:102-109`), returns `400` before any join/geometry code
   runs; (b) the pure geometry module's own point coercion, `_coerce_point`
   (`truelinev2/contracts/source_route_adoption.py:228-237`), raises on a non-finite value, which
   `derive_route_geometry` maps to the named `MALFORMED_CONTROL_POINTS` refusal
   (`truelinev2/contracts/source_route_adoption.py:438`); (c) the canonical-JSON hasher,
   `canonical_json_bytes` / `_normalize_number` (`truelinev2/contracts/source_route_adoption.py:186-191,206-210`,
   `allow_nan=False`), refuses to hash a non-finite number at all. At CREATE time specifically, a fourth,
   incidental guarantee also applies, stated precisely (micro-round correction — the prior "NEVER passes the
   list equality" phrasing overclaimed): the echo-vs-create `control_points` EQUALITY comparison
   (`truelinev2/api/product_pipeline_routes.py:1560`, `echo_points != create_points`) compares
   freshly-materialized `(p.x, p.y)` float scalars. Over the real JSON API a `NaN` control point cannot match
   here — each request-body parse materializes its OWN distinct float objects, and scalar `NaN != NaN`
   (IEEE754) always holds, so the request lands on `409 ROUTE_ADOPTION_CONTROL_MISMATCH`. In the narrower
   in-process corner where the IDENTICAL Python object instance is reused for the SAME `NaN` value in both
   the echo and the create request (only reachable via direct Python construction, never a real JSON
   request), Python's container equality short-circuits on object identity, so the comparison CAN pass
   despite the `NaN`. The request is then still refused by re-derivation's finiteness/malformed-controls
   check (`derive_route_geometry` → `_coerce_point`, `truelinev2/contracts/source_route_adoption.py:228-237`),
   so non-finite geometry can never be adopted — the refusal CODE in that corner is the nested
   `MALFORMED_CONTROL_POINTS` derivation refusal (via `409 ROUTE_ADOPTION_NO_LONGER_DEFENSIBLE`) rather than
   `ROUTE_ADOPTION_CONTROL_MISMATCH`.
2. **Resource resolution (existing 404/403/409 conventions, BEFORE any adoption-SEMANTIC validation).**
   Unconditionally, for EVERY request (`route_adoption` present or not): the `source_anchor_id` must not
   already exist (409 conflict); the `job_id` (+ tenant) must resolve (404, incl. cross-tenant isolation); the
   `plan_upload_id` + `page_number` must resolve to real page bounds (404).

   **When `route_adoption` is present**, two MORE things happen, in this order, inside that branch — stated
   plainly (micro-round correction; no code was moved to write this):
   - **First, a plain FEATURE-GATE check** — `400 ROUTE_ADOPTION_INVALID` if the three-way adoption flag
     isn't enabled. This is NOT a resource check (it reads server configuration, not a store record) and it
     runs BEFORE the two adoption-specific resource checks below — it always fires first if the feature is
     off, even for a request that also has a missing plan/RBL.
   - **Then, two more resource checks**: the `plan_upload_id` must additionally name a real `PLAN_PDF` upload
     on the job (404); and — fix-wave-2 H1 — the create request's OWN `reviewed_bore_log_id` must resolve to
     a real reviewed bore-log (404, via the SAME existing `_to_http` contract-error mapping every other
     resource check in this list uses).

   **Owner-approved divergence (deliberate, not a bug — read before assuming symmetry with the legacy path):**
   a `route_adoption` request explicitly NAMES the reviewed bore log as one of the RESOURCES the adoption is
   scoped to (alongside the plan and the job) — so a missing one is an honest 404, resolved BEFORE any
   adoption semantics run, exactly like a missing plan upload. The LEGACY no-adoption create path
   (`route_adoption` absent) does **NOT** 404 on a missing `reviewed_bore_log_id` — it keeps its ORIGINAL,
   unmodified evaluator design: `contracts/source_anchor.py::_evaluate_renderability` (lines 178-190) treats
   an absent RBL as a NAMED RENDERABILITY BLOCKER (`REVIEWED_BORE_LOG_NOT_FOUND`), and `create_source_anchor`
   still STORES the record — with `status = STATUS_REJECTED` rather than raising anything. Both are honest:
   the adoption path is REFERENCING a resource it needs to re-derive geometry against (no record can be
   created without it — a 404 IS the truth); the legacy path is RECORDING a review-context observation about
   a submitted redline that may reference a not-yet-existing or since-removed RBL (a stored REJECTED record,
   naming why, IS the truth there). This range does not change either behavior — see the closing round's
   scope note.
3. **Adoption-specific SEMANTIC validation** (only once (1) and (2) have both passed, and only when
   `route_adoption` is present): `_rederive_route_adoption` runs its OWN internal order (the table below) over
   the ALREADY-RESOLVED RBL — step 0 of THAT table (`ROUTE_ADOPTION_INVALID` for a well-typed-but-semantically-
   invalid adoption: `confirmed != true`, a malformed `proposal_hash` string, or a control-point COUNT that
   mismatches, as opposed to a MISSING field, which tier 1 already caught) is therefore always reached AFTER
   every resource in tier 2 has resolved. Row IDENTITY (does the row exist ON the already-resolved RBL) and
   eligibility stay SEMANTIC here (`ROUTE_ADOPTION_SCOPE_MISMATCH` / the nested
   `ROUTE_ADOPTION_NO_LONGER_DEFENSIBLE` refusal), never a resource 404 — only the RBL's own EXISTENCE is a
   tier-2 resource concern.

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

Test-locked at the REAL ASGI request boundary (`test_source_route_adoption_api.py`, fix-wave-2 G3/H1): a missing
echo field → 422; `confirmed: false` with otherwise-valid resources → 400 with an EXACT `ROUTE_ADOPTION_INVALID`
leading token; a nonexistent plan + a malformed `route_adoption` body → 404 (resource-first, never the 400 the
malformed body would otherwise produce); a valid job + valid plan but a NONEXISTENT `reviewed_bore_log_id`
(both the `confirmed=true` and `confirmed=false` variants of an otherwise well-shaped adoption body) → 404
(never 400 `ROUTE_ADOPTION_INVALID`, never 409 `ROUTE_ADOPTION_SCOPE_MISMATCH`).

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
| `render/station_dots.py` | **None at the time of this Phase-2 landing.** (Mission 8 ADDENDUM below adds an optional, additive `marks` parameter, `marks=None` byte-identical.) | `compute_station_dots(control_points, ...)` already interpolates along whatever polyline it is given; an adopted N-point path rides the same interpolation. |
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

---

## Mission 8 — manual N-point polyline / honest representative fallback (`manual_route`)

**Design authority**: `.foreman/scratch/m8/design.md` (mission + scout facts + base design) +
`.foreman/scratch/m8/design-final.md` (Sol adversarial-review amendments — SUPERSEDES `design.md` wherever
they differ; binds the exact 21-code vocabulary, the 4 error codes, and the schema/publisher/closeout/README
amendments this section documents as SHIPPED).

**Motivation**: source-route adoption (above) is stateless and can honestly refuse (`ROUTE_EVIDENCE_NOT_READY`
and the rest of the 21-code taxonomy). Before this mission, a refused search left the customer with an
UNLABELED 2-point straight fallback chord that rendered across houses/aerial imagery looking like a finished
engineered route — the exact customer-visible defect the owner flagged from a real production package.
`manual_route` closes it: the
operator either explicitly accepts an honestly-labeled "representative straight segment", or adds/moves/
removes bend points into a manual polyline, and must EXPLICITLY confirm before anything is stored.

### Flag — `TL2_SOURCE_ANCHOR_MANUAL_ROUTE_OPTIN`

Default OFF. `Settings.source_anchor_manual_route_optin: bool = False`. **Independent** of the three-way
`source_route_adoption_api_optin` gate above — manual confirmation needs no readiness spine / observer
backbone at all, so it is checked on its own. Both may be enabled together; a single create request may
never carry both `route_adoption` and `manual_route` regardless of either flag's state (see "Mutual
exclusion" below).

**OFF is byte-identical**: with the flag OFF, a request that carries the optional `manual_route` block is
refused `400 MANUAL_ROUTE_NOT_ENABLED` before any manual-route validation/derivation runs; a BLOCKLESS
request (the overwhelming common case) follows the EXISTING unchanged v1/v2 create path verbatim regardless
of this flag's value — same record bytes, same response bytes (test-locked byte-for-byte:
`test_blockless_create_is_byte_identical_flag_off_vs_on`). `contracts.source_route_adoption` is imported
ONLY, and lazily, for the `reported_route_search` taxonomy check (see below) — a request that clears every
earlier gate but omits `reported_route_search`, or one refused before reaching that check, never imports it
(subprocess-isolated: `test_flag_off_never_imports_the_route_adoption_module`).

### Wire contract (snake_case, additive on the EXISTING `SourceAnchorCreate` body)

```json
{"manual_route": {
  "confirmed": true,
  "representative_status": "MANUAL_POLYLINE_CONFIRMED" | "REPRESENTATIVE_STRAIGHT_ACCEPTED",
  "reported_route_search": {"code": "<one of 21>", "upstream_reason_code": "<^[A-Z][A-Z0-9_]{0,63}$>" | null}
}}
```

`reported_route_search` is OPTIONAL and, when present, is **client-attested session metadata, NEVER
server-verified** — it echoes the route-search refusal the operator's OWN session received before deciding
to confirm a manual/representative route. It has ZERO effect on geometry, render, billing, tier, or
acceptance; it exists purely so the closeout record can honestly say "the operator's session reported
refusal X" (never "the server verified refusal X"). This is the SAME trust posture as a free-text notes
field, made vocabulary-bound rather than free text.

### Validation (order, code-first 400 details unless noted)

1. **Mutual exclusion** — `manual_route` AND `route_adoption` both present → `400
   MANUAL_ROUTE_PROVENANCE_CONFLICT`. Validated BEFORE either provenance branch runs, and fires regardless of
   either flag's state (a request this malformed is refused on shape, not on feature availability).
2. **Flag gate** — `manual_route` present + flag OFF → `400 MANUAL_ROUTE_NOT_ENABLED`.
3. **`confirmed` literal** — `confirmed != true` (well-typed `false`) → `400 MANUAL_ROUTE_INVALID`. A
   **missing** `confirmed` (or any other required field) is FastAPI's own framework-standard `422` — never
   reaches product code (same 400-vs-422 convention as `route_adoption`, proven at the real ASGI boundary:
   `test_confirmed_missing_is_422_via_real_endpoint`).
4. **Count↔status consistency** — exactly 2 `control_points` requires `REPRESENTATIVE_STRAIGHT_ACCEPTED`;
   `>= 3` requires `MANUAL_POLYLINE_CONFIRMED`; a mismatch (in EITHER direction, including a count `< 2`, for
   which no status is ever valid) → `400 MANUAL_ROUTE_STATUS_MISMATCH`. No non-collinearity test, no count
   ceiling — matches `route_adoption`'s own "no maximum, only a floor" discipline
   (`contracts/source_anchor.py::MIN_CONTROL_POINTS`).
5. **Zero-total-length rejection** — a manual polyline whose control points sum to zero total arc length
   (e.g. two or more identical points) → `400 MANUAL_ROUTE_INVALID`, even when the count↔status rule would
   otherwise "match" (an all-identical 2-point submission is really a single point, not a representative
   segment).
6. **`reported_route_search` taxonomy** (only when present) — `code` must be one of the EXACT 21 codes the
   `POST .../source-route-proposals` endpoint can actually return over HTTP 200: `ALL_REFUSAL_CODES -
   {MALFORMED_CONTROL_POINTS}` (the five create-time `ROUTE_ADOPTION_*` exception codes are never members of
   `ALL_REFUSAL_CODES` to begin with — a SEPARATE vocabulary — so no further subtraction is needed).
   `MALFORMED_CONTROL_POINTS` itself is a REAL code the derivation module defines, but the proposal endpoint
   400s before it can ever be RETURNED as a refusal payload, so it is rejected here too. An unrecognized code
   → `400 MANUAL_ROUTE_INVALID`. Cross-field invariant: `code == ROUTE_EVIDENCE_NOT_READY` REQUIRES a non-null
   `upstream_reason_code` matching `^[A-Z][A-Z0-9_]{0,63}$` (open vocabulary upstream, shape-bound only); ANY
   OTHER code REQUIRES `upstream_reason_code` to be null/absent. Either direction violated → `400
   MANUAL_ROUTE_INVALID`. This is the ONLY validation step that imports `contracts.source_route_adoption`
   (lazily, `api/product_pipeline_routes.py::_validate_reported_route_search`).

### Refusal-order note (TRUTHFUL, mirrors the route_adoption ordering above)

Duplicate-anchor / job / page-bounds resolution (the SAME preamble every create request runs — 409 on a
pre-existing id, 404 on a missing job) happens BEFORE the mutual-exclusion or flag checks — never after. This
is stated plainly because it would be easy to assume "flag check first": it is not; resource resolution is
first, exactly like the pre-existing `route_adoption` ordering
(`product_pipeline_routes.py:1690` vs the mutual-exclusion/flag checks that follow it).

### Server-authored record block (`create_source_anchor_v2`, `manual_route` mode)

```json
{"record_format": "trueline-source-anchor-2", "geometry_basis": "HUMAN_CLICKED_POLYLINE",
 "confirmation_state": "HUMAN_REVIEWED",
 "manual_route": {
   "representative_status": "...", "intermediate_point_count": 2,
   "human_control_points": {"start": {"x":..,"y":..}, "end": {"x":..,"y":..}, "intermediate": [...]},
   "reported_route_search": {"code": "...", "upstream_reason_code": null} ,
   "confirmed_by": "<ctx.session_id>", "confirmed_at": "<UTC iso>"
 }}
```

`human_control_points` is derived from the SAME normalized point list stored in `control_points`
(`_normalize_points`'s own float conversion) — never from a separate raw echo, so "exact" means numerically
unchanged after that normalization, never raw JSON bytes. Audit gains one entry, `"manual_route_confirmed"`.
`create_source_anchor_v2` now accepts two MUTUALLY EXCLUSIVE optional modes, `route_adoption` / `manual_route`
— exactly one required; the `route_adoption` branch's record construction is BYTE-FOR-BYTE UNCHANGED (values
AND key order) from before this mission.

### Readers (Q4/Q9 — split by ACTUAL provenance block, never a bare truthy `geometry_basis`)

A manual v2 record ALSO carries `geometry_basis` now (`HUMAN_CLICKED_POLYLINE`), so every reader that used to
treat truthy `geometry_basis` as "this is an adopted record" was corrected to branch on the record's ACTUAL
block instead:

| Consumer | Behavior |
|---|---|
| `contracts/source_anchor.py::build_source_anchor_manifest` | Emits `geometry_basis`/`confirmation_state`/`render_control_points` whenever present, THEN emits `route_adoption` only if the record's OWN `route_adoption` is non-null, `manual_route` only if the record's OWN `manual_route` is non-null — never synthesizes a null-filled `route_adoption` for a manual record. |
| `contracts/redline_manifest.schema.json` | `geometry_basis` enum gains `HUMAN_CLICKED_POLYLINE`; a new whitelisted `manual_route` object (schema stays CLOSED — `additionalProperties:false`). |
| `contracts/redline_manifest_publisher.py::reconciliation_errors` | Gains four semantic checks per log: both `route_adoption` AND `manual_route` present → error; `route_adoption` present but `geometry_basis != OBSERVER_BACKBONE_HUMAN_ADOPTED` → error; `manual_route` present but `geometry_basis != HUMAN_CLICKED_POLYLINE` → error; `geometry_basis` present but its matching block is absent → error. |
| `contracts/closeout_pdf.py` (Artifact Detail, §5) | Branches on `log.get("route_adoption") is not None` (adoption wording, BYTE-UNCHANGED) vs `log.get("manual_route") is not None` (new: representative-status wording + confirming session + `"reported route-search refusal: <CODE>"` (+ upstream) when present) — NEVER on `geometry_basis` truthiness. |
| `contracts/export_bundle.py` README | The unconditional "the engine's ... never invented" sentence is FALSE for a manual record; branched to an honest "reviewer's OWN confirmed control points" sentence ONLY when the manifest carries ANY `manual_route` block. v1 + adoption-only exports stay byte-identical. |

### Tests

`truelinev2/tests/test_source_anchor_manual_route.py` (new; added to the CI targeted list): settings default/
env, blockless byte-identity flag OFF vs ON (stored-file + response bytes), flag-off 400, happy paths (2-point
representative + 4-point manual polyline, exact server-authored block shape + audit action), `row_ids` 0..many
(unlike adoption's exactly-one rule), `confirmed` false/missing (400 vs 422), count↔status mismatch both
directions, zero-length rejection (2-point and N-point), the full `reported_route_search` taxonomy (accepted
code, `ROUTE_EVIDENCE_NOT_READY` cross-field both directions, unknown code, `MALFORMED_CONTROL_POINTS`,
a `ROUTE_ADOPTION_*` code), the flag-off subprocess import-isolation proof, mutual-exclusion (including with
both flags off), manifest split-emission + schema validation, four publisher reconciliation-error unit tests
+ one clean-pass unit test, closeout wording (manual polyline / representative straight / v1+adoption
unaffected), ZIP README honesty (manual vs v1 byte-unchanged), station dots riding a manual 4-point polyline
(exact `<= 1e-9` on-polyline distance + `xy_display == round(exact, 2)`, mirroring the adoption suite's own
rigor), and tenant isolation.

## Mission 8 ADDENDUM — evidence-bound station marks (owner's STATION-DOT CONTRACT)

**Design authority**: `.foreman/scratch/m8/design-dots.md` (BINDING, supersedes `design.md`/`design-final.md`
where they touch station dots). Owner's clarification: a source-anchor's station dots represent the BORE
LOG'S OWN station sequence, bound to evidence — never a generic 50' geometric ladder invented over a log
that recorded something else. Applies to EVERY source-anchor render, manual and adoption alike (one honest
contract; the reader-survey row for `render/station_dots.py` above is superseded by this section).

### New pure contract: `contracts/station_marks.py`

`build_station_marks(row_effective, *, footage, start_station, end_station, interval_ft=50.0) ->
(marks, basis, warnings)`. No I/O, no `render/`/engine/dialect/match imports — reuses only
`truelinev2.stations`' parse/format helpers. Decides, per reviewed row, which dots to place:

- **`STATION_SERIES`** (a usable recorded series of > 2 readings): marks are EXACTLY the recorded stations
  (irregular intervals and a < 50' final interval included by construction), every one `SOURCE_RECORDED`,
  each carrying that reading's own depth/BOC + `station_evidence` (verbatim/status/confidence). No derived
  fill ever mixes into a genuinely recorded series.
- **`SERIES_ENDPOINTS_WITH_DERIVED_FILL`** (a usable recorded series of exactly 2 readings — start/end/
  total-only logs, e.g. the WP23 shape): the two recorded endpoints (`SOURCE_RECORDED`, with values +
  evidence) plus interior every-50' fill dots tagged `DERIVED_INTERVAL` (arithmetic station label, no depth/
  BOC/notes/evidence — derivation is honestly marked, never presented as recorded).
- **`SPAN_ENDPOINTS`** (no recorded series at all — the ordinary generic TABLE_IMPORT row, or a recorded
  series rejected as unusable): the row's own recorded start/end station text (`SOURCE_RECORDED`, no
  per-station depth/BOC — the row's bore-level values are not station readings) plus the same tagged
  interior fill.

A recorded series is rejected (falls through to `SPAN_ENDPOINTS`, named in `warnings`) when it fails any of:
every reading parses (else `STATION_SERIES_UNPARSEABLE`), strictly ascending (else
`STATION_SERIES_NOT_ASCENDING`), first/last match the row's own effective start/end station (else
`STATION_SERIES_ENDPOINT_MISMATCH`), and the recorded span matches the row's own effective footage (else
`STATION_SERIES_FOOTAGE_MISMATCH`). The approved span always remains the truth — a violation never invents
or partially-trusts a series, it falls through cleanly.

### `render/station_dots.py` — additive-only

`compute_station_dots`/`stroke_polyline_with_dots` gain an optional `marks` parameter (the render/ fence is
lifted ONLY on these two functions, by explicit owner instruction). `marks=None` is the EXACT pre-addendum
behavior (locked byte-identity test). With `marks`, positions use the SAME arclen/`_point_at` math + 2-
decimal `xy_display` contract, but at the marks' own footage-along values; each dot gains `origin` (always)
and `station_evidence` (when the mark carries one); `station`/`depth`/`boc`/`notes` come from the MARK
(`depth`/`boc`/`notes` present ONLY when that mark actually carries them); bore-level `date`/`crew`/`print`/
`bore_log_id` still attach to every dot from the row's `info`, as before.

### `render/source_anchor_render.py` + manifest

`_dots_for_anchor` resolves the row's effective start/end/footage (the SAME raw < normalized <
review.corrected_values layering `resolve_bore_fields` already uses) and calls `build_station_marks`, for
ALL source-anchor renders (manual and adoption). The manifest log entry gains additive `station_marks_basis`
(one of the three enums above, or `null` when the anchor has no dots at all) and `station_marks_warnings`
(named codes, `[]` when none) — both default-empty/absent-tolerant so a caller that never supplies them
(incl. every pre-addendum manifest) stays valid.

### Schema

`redline_manifest.schema.json`: `station_dots[*].origin` is now REQUIRED (enum `SOURCE_RECORDED` |
`DERIVED_INTERVAL`); `station_dots[*].station_evidence` is an optional closed object
(`verbatim`/`status`/`confidence`); log-level `station_marks_basis` (nullable enum) and
`station_marks_warnings` (string array) are additive, optional properties. Every object stays closed.

### Tests

`truelinev2/tests/test_station_marks.py` (new; pure unit coverage of all three bases + irregular intervals +
a short final interval + varying per-entry depth/BOC + all four named unusable-series fallbacks + the
corrected-values precedence path). `test_station_dots.py` gains the `marks=None` byte-identity locks for
both functions plus marks-path placement/tagging tests. `test_source_anchor_render_contract.py` gains render-
integration coverage for the WP23 shape, a >= 4-reading irregular series with an exact short final interval,
and a footage-only position-equality lock (dot positions bit-for-bit unchanged from the pre-addendum
`dot_marks` ladder) — plus a schema-admission update to `test_build_manifest_carries_station_dots_
additively_and_validates` (origin now required) and a deliberate lock update to
`test_render_places_station_dots_with_bore_info` (a footage-only row's dots no longer carry per-station
depth/BOC/notes — see that test's docstring for the owner-contract citation).
`test_source_route_adoption_api.py::test_adopted_record_station_dots_ride_the_n_point_path` gains an
`origin`-tag assertion and now doubles as the adoption-lane position-equality lock.
