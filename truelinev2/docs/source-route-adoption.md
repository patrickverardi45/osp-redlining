# Source-route adoption (Phase 2, T31)

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
renderer inputs, same manifest/closeout/billing/export/photos/station-dots. The route-adoption derivation code
(`contracts.source_route_adoption`'s `derive_route_geometry` / `build_proposal` / `check_*` /
`row_effective_stations`, and `harness.product_readiness_bridge.run_job_route_readiness_raw`) is imported
LAZILY, inside the `route_adoption` branch of `create_source_anchor_route` only — never at module import time,
never on a plain manual create.

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

`SourceAnchorCreate` gains one optional field: `route_adoption: {proposal_hash, confirmed}`. The client submits
NO candidate/render vertices — `control_points` must contain exactly the two human clicks. The server
**re-derives** the SAME join + projection from THIS request's own scope (never trusting the client's prior
proposal call), and durably persists only after the re-derived hash matches.

Create-time failures (repo `_to_http` convention: the code LEADS the `detail` string, e.g.
`"ROUTE_ADOPTION_STALE: ..."`, never an object detail):

| Condition | HTTP | Code |
|---|---|---|
| `control_points` count != 2, `confirmed != true`, or a malformed `proposal_hash` string | 400 | `ROUTE_ADOPTION_INVALID` |
| `row_ids` doesn't contain exactly one id, or `group_id` is set (route adoption is single-row-scoped) | 409 | `ROUTE_ADOPTION_SCOPE_MISMATCH` |
| Current re-derivation itself refuses (any Q2/Q3 code) | 409 | `ROUTE_ADOPTION_NO_LONGER_DEFENSIBLE` (nested current refusal code + message in the detail) |
| Current re-derived hash differs from the submitted `proposal_hash` | 409 | `ROUTE_ADOPTION_STALE` |
| *(reserved, not raised by this implementation — see "Known limitation" below)* | 409 | `ROUTE_ADOPTION_CONTROL_MISMATCH` |

On success the stored record is `record_format = "trueline-source-anchor-2"`; `control_points` holds the
SERVER-DERIVED render polyline (so the EXISTING renderer / station-dot call path consumes it unmodified — see
"Reader survey" below); the exact human clicks + source candidate geometry live separately under
`route_adoption` (never described as human-clicked).

## Geometry (pure, `contracts/source_route_adoption.py`)

No I/O, no fitz/PlanPdf import. Given the observer backbone (`RouteVerification.route_geometry` — ordered
`{"a": (x,y), "b": (x,y)}` segments) and the inherited `reach_tol` (read from
`RouteVerification.detail["isolation"]["detail"]["reach_tol"]` — **never hardcoded**):

1. **Backbone ordering/contiguity**: convert segments to an ordered point chain; every `segments[i].b` must
   equal `segments[i+1].a` (after finite-float normalization) or refuse `BACKBONE_DISCONTINUOUS`.
2. **Gap-bridge gate**: `gap_bridge_status == "ROUTE_GAPS_BRIDGED"` refuses
   `BACKBONE_CONTAINS_HYPOTHETICAL_GAP_BRIDGE` (a bridge is a continuity HYPOTHESIS, never a drawn stroke).
3. **Tolerance**: missing/non-finite/non-positive `reach_tol` refuses `SOURCE_TOLERANCE_UNAVAILABLE`.
4. **Projection**: each human control projects (clamped `t ∈ [0,1]`) onto every backbone segment; the nearest
   wins. A distance TIE across segments with the SAME chainage (a shared vertex) is accepted deterministically
   (lowest segment index); a tie at DIFFERENT chainages refuses `AMBIGUOUS_START_PROJECTION` /
   `AMBIGUOUS_END_PROJECTION`. Distance beyond `reach_tol` refuses `START_CONTROL_OUTSIDE_TOLERANCE` /
   `END_CONTROL_OUTSIDE_TOLERANCE`. An unclamped projection parameter before the first segment or past the last
   refuses `START_CONTROL_BEYOND_BACKBONE_EXTENT` / `END_CONTROL_BEYOND_BACKBONE_EXTENT`.
5. **Control-pair classification** (`classify_control_pair`, directly unit-tested): both controls on the same
   backbone segment (only meaningful when the backbone has more than one segment — a genuinely single-segment
   backbone trivially puts both on segment 0 and must NOT refuse) → `CONTROLS_ON_SAME_BACKBONE_SEGMENT`; equal
   chainage → `CONTROL_PROJECTIONS_COINCIDE`; start chainage > end chainage → `CONTROL_ORDER_REVERSED`.
6. **Clip**: `[start_projection] + every original vertex with chainage STRICTLY between start/end +
   [end_projection]` — no simplification, densification, or invented bend.
7. **Render polyline**: `[human_start] + clip + [human_end]`, consecutive exact duplicates removed. A nonzero
   connector (human click ≠ its projection) is recorded as the `HUMAN_CONTROL_TO_BACKBONE_CONNECTOR` warning —
   the operator's exact click is NEVER silently snapped.
8. Zero-length clip or render → `ZERO_LENGTH_PROPOSAL`.

## Hashing (Q4)

Two hashes, both `sha256:<64-hex>` over sorted-key, compact-separator, finite-numbers-only canonical JSON
(`-0.0` normalizes to `0.0`; a non-finite number raises rather than hashing silently):

- `candidate_route_hash` — the SOURCE geometry only (algorithm version, plan/span/readiness identity, tolerance,
  full backbone, clipped candidate route) — independent of the human clicks; detects when the underlying
  observer evidence changed.
- `proposal_hash` — everything `candidate_route_hash` covers PLUS the scope (tenant/job/plan/rbl/row/page), the
  exact two human controls, both projections, and the final render polyline. This is the hash the client
  round-trips through `route_adoption.proposal_hash`; a mismatch on re-derivation is `ROUTE_ADOPTION_STALE`.

`proposal_id = "rap-" + proposal_hash_hex[:24]`.

## Known limitation — `ROUTE_ADOPTION_CONTROL_MISMATCH`

The trust model is fully stateless (Q4: "not a new proposal store"): the client never round-trips its own
prior proposal's bound control points, only the opaque `proposal_hash`. The server therefore cannot
distinguish "the human clicked different points than the proposal was based on" from "the underlying evidence
changed since the proposal" — both manifest identically as a hash mismatch on re-derivation. This
implementation reports that single detectable condition as `ROUTE_ADOPTION_STALE`; the `RouteAdoptionControlMismatchError`
class is defined (for the taxonomy and for a future protocol extension that transmits the bound controls
separately) but is not raised by the current create-time code path. Flagged for the owner; not a hidden gap.

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
sensitivity), `test_source_route_adoption_bridge.py` (additive bridge params, byte-identity + filtering),
`test_source_route_adoption_api.py` (end-to-end: mounting, flag OFF/ON identity, proposal happy-path + refusals
against REAL source-backed geometry read off the fixture-free `complete_package_qa` spine, adoption round-trip,
stale/invalid/scope-mismatch/no-longer-defensible, tenant isolation, manifest/closeout/station-dot flow-
through).
