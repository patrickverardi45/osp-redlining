# KMZ Topology Sidecar — Usage Policy

**STATE key:** `kmz_topology_sidecar`  
**Schema version:** `kmz-topology-sidecar-1`  
**Phase:** 1O  
**Status:** Read-only, upload-scoped, diagnostic only

---

## What this sidecar is

`kmz_topology_sidecar` is a best-effort topology lineage bridge between the
**semantic ingest** (`kmz_semantic`) and the **operational render ingest**
(`kmz_reference`).  It records per-reference-feature join keys that allow
engineering topology information to be recovered for future diagnostic or
opt-in operational use.

It is built once per `upload_design` call, immediately after both
`kmz_reference` and `kmz_semantic` are populated.  It is upload-scoped and
ephemeral — it is replaced on each new upload and cleared on workspace reset.

---

## What each sidecar entry contains

Each entry in `entries[]` carries exactly seven fields:

| Field | Type | Purpose |
|---|---|---|
| `reference_feature_id` | string | Join key into `kmz_reference` |
| `semantic_feature_id` | string \| null | Join key into `kmz_semantic` (null on miss) |
| `placemark_id` | string \| null | KML `<Placemark id="...">` attribute when present |
| `folder_path` | array of strings \| null | Structured folder hierarchy from semantic ingest |
| `multigeometry_group_id` | string \| null | Groups fragments from the same MultiGeometry placemark |
| `document_order` | integer \| null | 1-based position of the matched semantic feature |
| `style_url` | string \| null | Verbatim KML `<styleUrl>` from the matched semantic feature |

Join quality is best-effort by `(placemark_name, folder_path_str)`.
Duplicate names in the same folder → first occurrence wins.
Unmatched reference features → all semantic-derived fields are null.

---

## STRICT USAGE RULES

### 1. Operational code MUST NOT depend on this sidecar

No code path in the following systems may read `kmz_topology_sidecar` or
fail if it is missing (`None`), empty, or malformed:

- Route extraction (`_build_route_catalog`, `_choose_default_route`)
- Rendering (`_build_kmz_reference`, `_kmz_reference_lite`)
- Route matching and scoring (`_score_group`, `_run_group_match`, `_set_active_route`)
- Redline construction (`_rebuild_field_data_outputs`, `redline_segments`)
- Bore log alignment (`_append_bore_log_row`)
- Walk session event handling
- Billing artifact generation
- Closeout packet generation

### 2. Renderer MUST NOT consume this sidecar

The operational map renders from `kmz_reference` only.  The sidecar
records lineage to `kmz_semantic`; it does not modify or enrich
`kmz_reference` features.  No map component, no route line, no polygon
style, and no point marker may be derived from sidecar data.

### 3. Sidecar is NOT matching authority

`multigeometry_group_id` and `style_url` are engineering lineage hints.
They must never override matching scores, route selection, or the
`selected_route_match` result.

### 4. Sidecar is NOT a scoring input

No scoring function (`_score_group`, semantic shadow, or any candidate
scoring path) may use sidecar fields as scoring signals without an explicit,
independently reviewed, phase-gated change to this policy document.

### 5. No topology inference

The sidecar records observed relationships only.  No code may use the
sidecar to infer unobserved relationships (e.g., "these two lines are
probably the same cable because they share a multigeometry_group_id").
Inference from sidecar data requires a separate, explicit implementation
phase.

### 6. No graph reconstruction

The sidecar is a flat join table.  It has no edges, no traversal API,
and no topology engine.  No code may treat it as a graph or query it
transitively.

### 7. No persistence

`kmz_topology_sidecar` is STATE-only.  It must never be written to disk,
included in JSONL streams, or transmitted to billing or closeout artifacts.

### 8. Absence must never be an error

Any consumer that reads `kmz_topology_sidecar` MUST handle `None`,
missing entries, and empty `entries[]` gracefully.  A missing sidecar
is not a data quality problem — it means no upload has occurred or the
sidecar build failed non-fatally.

---

## Allowed uses (diagnostic only, opt-in)

Future phases may opt in to using sidecar data for the following
**diagnostic-only** purposes after explicit policy review:

- Frontend engineering fidelity diagnostics panel (display only, no render)
- Bore-log alignment audit (display which MultiGeometry group the bore candidate belongs to)
- Engineering grouping visualization in the diagnostics panel

Each such use must:
1. Be explicitly flagged as opt-in in code comments.
2. Degrade gracefully to the existing behavior when the sidecar is absent.
3. Never change matching scores, route selection, or redline output.

---

## Mutation rules

This sidecar is **read-only after build**.

- Built once per upload in `upload_design`.
- Cleared on `_reset_workspace_state`.
- Never patched, appended, or modified by downstream code.
- No endpoint exists to write, patch, or delete sidecar entries.

---

*Last reviewed: Phase 1O. Next review required before any operational use.*
