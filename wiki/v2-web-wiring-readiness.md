# v2 to Web Wiring Readiness

**Status:** local-only, read-only handoff implemented; production wiring is not authorized.
**Date:** 2026-06-12
**V2 HEAD:** `50af293` on `feat/truelinev2`
**Web HEAD:** `cdc3289` on `codex/v2-reviewer-bundle-adapter`

## Current Implementation

The local demo now supports two validated read paths:

1. **Fixture-default web path**
   - The web app consumes checked-in reviewer and design-stroke manifests.
   - The Brenham demo fixture provides 58 bore-to-run identity matches.
   - Slice 2b proof PNGs are available through the web app's gitignored
     `public/engine-artifacts/<source-sha>/` tree.
   - Images remain lazy: no proof PNG is requested until the artifact panel is
     expanded.

2. **Opt-in live reviewer API path**
   - V2 exposes a context-free reviewer router only when
     `TL2_REVIEWER_API_OPTIN=1`.
   - The web uses it only when `NEXT_PUBLIC_TL2_API_BASE` is set.
   - Unset web env continues to use the fixture path.
   - Live fetch or validation failures are loud; there is no silent fixture
     fallback after live mode is selected.

## Local Reviewer API

The flag-gated router implements GET only:

- `GET /v2/reviewer/bundle?mode=default_baseline`
- `GET /v2/reviewer/design-stroke/manifest`
- `GET /v2/reviewer/design-stroke/asset/{name}`

V2 settings:

- `TL2_REVIEWER_API_OPTIN=0` by default, so all reviewer routes are absent and
  return 404.
- `TL2_DESIGN_STROKE_DIR` defaults to
  `data/outputs/symbol_conduit_lane_sweep`.

The bundle route accepts only `default_baseline`, validates the existing
reviewer export, and memoizes it in app state. The manifest route reuses the
served-manifest validator with API-relative asset URLs. The asset route accepts
only approved bare PNG filenames and preserves basename, traversal, containment,
and missing-file guards.

The reviewer router intentionally has no tenant/session dependency, auth
implementation, database write, or mutation method. This is a local handoff,
not a production security boundary.

## Shipped Slices

- **Slice 1:** validated static M8.11 reviewer bundle and strict web adapter.
- **Slice 2a:** engine-generated refs-only design-stroke manifest.
- **Slice 2b:** explicit static copy of the five approved proof PNGs plus
  lazy served-image viewing.
- **Brenham mapping scaffold:** 58 local fixture runs keyed by exact
  `boreLogRef.refId == sourceBoreId`; Cedar Ridge runs are never used.
- **Live handoff:** opt-in V2 GET routes and opt-in web live reads.

## Truth And Safety Invariants

The handoff does not change engine proof logic, grades, or reviewer semantics.

- `PLACED_REVIEW`, suggestions, source review, named-solver blocks, and unsafe
  abstains remain distinct.
- `SUGGESTION_NOT_PLACEMENT` is preserved verbatim.
- Confidence remains a closed class, never a numeric score.
- Reviewer JSON forbids `segments`, `stroke_points`, and artifact refs.
- Design-stroke manifests contain approved filenames and URLs only; no geometry
  or binaries ride in JSON.
- Asset access is GET-only and constrained to the approved manifest set.
- No reviewer action writes back to V2.
- No shared web/mobile contract was changed.

## Explicitly Not Production Ready

The current handoff is not production wiring. It has no:

- authentication or authorization implementation;
- tenant ownership model;
- durable object storage or production artifact lifecycle;
- production corpus provisioning and cache invalidation policy;
- reviewer decision/writeback doctrine;
- POST, PUT, PATCH, or DELETE reviewer endpoint;
- geometry overlay or PDF-to-web coordinate transform;
- deployment configuration.

## Remaining Production Gates

1. Define authentication and tenant isolation before exposing reviewer routes
   beyond local use.
2. Move artifacts to durable managed storage with authorized, expiring access.
3. Define production corpus availability, regeneration, cache invalidation, and
   source-SHA lifecycle.
4. Specify reviewer writeback semantics without converting suggestions or
   abstains into placements.
5. Establish deployment, CORS, observability, and failure-handling policy.
6. Authorize and loss-check a coordinate transform before any geometry overlay.

Until those gates are resolved, keep both the V2 reviewer router and web live
reads opt-in and local-only.
