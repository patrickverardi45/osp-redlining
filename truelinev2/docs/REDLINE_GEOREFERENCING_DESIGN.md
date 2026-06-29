# Redline → Google Earth georeferencing — design (C2)

> Status: **DESIGN ONLY (not built).** This documents the honest path from today's pixel-only redlines to
> real, georeferenced redline overlays in Google Earth — and exactly what must be true before we draw a
> single coordinate. Nothing here fabricates coordinates. Authored alongside the Owner-Mode simplification +
> Google-Earth export pass (Part C). The shippable-today piece (C1) is separate and already implemented.

## What ships today (C1 — implemented, honest)
- **Open route in Google Earth (.kmz)** — `GET /v2/product/jobs/{job}/gis-route/download` streams a real
  KMZ built from the operator's **uploaded** GIS_ROUTE (real WGS84 lines/points/polygon + verbatim
  names/street labels). It is the uploaded **design route**, clearly labelled — *not* redline output.
- **Source-backed street names** — `gis_route` reads each placemark's `<description>` and surfaces a
  `source_label` (e.g. "East Stone Street") **verbatim** when the file states one, `null` otherwise. Never
  geocoded, never synthesized.
- **Redlines are honestly flagged pixel-only** — the route KMZ contains **no** redline geometry, and the
  redline-KMZ authority (`kmz_export.evaluate_export`) still returns `BLOCKED[UNSUPPORTED_PIXEL_ONLY]`.

## The gap (verified in code)
A redline is a polyline in **PDF display points** the whole way through:
- `extract/generic_geometry.py` emits `[x, y]` page points from a fitted `StationAxis` (station-feet ↔
  page-x **within a page**, never world coords).
- `render/crop.render_redline_stroke` rasterizes those points onto a PDF-page PNG (`FINAL_REDLINE_PNG`).
- `redline_manifest.schema.json` carries **no** lat/lon, **no** CRS, **no** `geometry` — only station-string
  spans, footage, source sheets, and the PNG path+sha.

So `kmz_export.classify_geometry_basis → UNSUPPORTED_PIXEL_ONLY` and the export is (correctly) blocked.

**Key leverage:** the KMZ machinery is already built and waiting. `kmz_export.extract_exportable_features`
already consumes a per-feature `geometry` block `{crs:"EPSG:4326", datum, units, kind, coordinates,
source, confidence}`, `build_kml`/`build_kmz_bytes` already emit + pack it, and `validate_kmz_bytes` already
checks Google-Earth validity. **The only missing primitive is producing + persisting that geometry block from
a trustworthy PDF-page→world transform.** Once it exists, the export lights up with zero new faking.

## What true georeferencing requires
1. **A PDF-page → WGS84 transform, per plan sheet.** At minimum 2–3 control points pairing page coordinates
   `(x, y in points)` with real `(lat, lon)`, fitted to an affine/Helmert transform, so any redline vertex
   pixel projects to a coordinate. Today nothing maps page space to the globe.
2. **Control points sourced honestly (never guessed).** In priority order:
   - **(a) Cross-source structure identity** — match a structure the PDF labels (an AP id / splice-loc /
     handhole token the dialect already extracts) to the **same** structure's WGS84 point in the uploaded
     GIS_ROUTE KMZ. The dialect already models AP/splice tokens + a `terminal_class` join, and `gis_route`
     already parses the KMZ points — so this can yield real page↔world pairs from data we already have. **This
     is the most promising path** (no new field capture, no new survey data).
   - **(b) Printed survey/grid ticks** — state-plane or lat/lon grid ticks printed on the sheet with known
     coordinates, or a sheet-corner registration.
   - **(c) FIELD_GPS** — redline vertices captured in the field (mobile app) are real WGS84 directly,
     bypassing the PDF transform entirely. Cleanest data, but requires field capture.
3. **A georeferenced station axis (optional refinement).** Tie the fitted `StationAxis` to real-world
   distance/bearing along the corridor so station spans resolve to coordinates, instead of only page-x.
4. **Persist a per-feature `geometry` block** into the manifest (`logs[].geometry`, EPSG:4326, `source ∈
   {ENGINE_REVIEWED, HUMAN_OVERRIDE, FIELD_GPS}`, `confidence ∈ {HIGH, MEDIUM}`). This is an **additive**
   schema field — recognized manifests without it stay byte-identical; `classify_geometry_basis` only flips to
   `GEOSPATIAL_COORDINATES` when **every** drawn log carries it.
5. **A transform-quality / uncertainty gate.** A low-quality fit must **block**, not emit wrong coordinates —
   reusing the existing named codes (`AMBIGUOUS_CRS`, `COORDINATE_UNCERTAINTY`, `SOURCE_CONFLICT`,
   `GEOREFERENCE_NOT_RESOLVED`). Abstain-on-doubt is the law here, same as placement.

## Honesty rules (non-negotiable)
- **Never fake coordinates.** No bbox-as-transform, no snap-to-route, no proportional fallback (the v1
  anti-patterns the salvage audit rejected).
- **Abstain when uncertain.** A redline with no trustworthy transform stays pixel-only and the KMZ stays
  blocked — exactly today's behavior, surfaced honestly.
- `kmz_export.evaluate_export` remains the single redline-KMZ authority; the route export (C1) is a separate,
  clearly-labelled lane and must never be presented as redline output.

## Phased plan (each separately gated; none started)
- **G0 — control-point spike (read-only).** On the recognized corpus, attempt cross-source identity
  (PDF structure tokens ↔ KMZ WGS84 points). Measure how many sheets get ≥3 confident pairs. Decision gate:
  is (a) viable, or do we need (b)/(c)? **Pure diagnostic, no schema/render change.**
- **G1 — per-sheet transform + quality gate.** Fit the affine transform from confident control points; emit a
  per-sheet transform-quality score; block below threshold. No manifest change yet (shadow/diagnostic).
- **G2 — emit + persist the `geometry` block** (additive schema field) behind a default-OFF flag; recognized
  manifests stay byte-identical until a sheet genuinely earns coordinates.
- **G3 — export lights up.** `evaluate_export` now returns `EXPORTABLE` for georeferenced logs via the
  **existing** builder/packer/validator — the redline KMZ opens in Google Earth, red strokes on the map,
  with no faking. Pixel-only logs still block honestly (mixed packages export what's earned, flag the rest).

## Open questions for the owner
- Is cross-source identity (G0 path a) acceptable as the coordinate source, or is field-GPS capture required
  before we draw redlines on a real map?
- Per-sheet transform quality threshold — what residual error is "good enough" vs. block?
- Mixed packages: export the georeferenced subset + honestly omit the rest, or all-or-nothing per package?
