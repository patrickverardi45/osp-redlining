// web/src/lib/types/matchReviewQueue.ts
//
// Read-only frontend mirror of the /api/match-review-queue response shape
// (KMZ Matching Trust Slice B + C1 + Plan Sheet Graph precision evidence).
// The backend `match_review_queue.py` + `brenham_plan_sheet_graph.py` own the
// canonical schema; this only types the fields the UI reads. Extra runtime
// fields are ignored.

export type PlanSheetGraphStatus =
  | "station_print_disjoint"
  | "external_packet_mismatch_possible"
  | "unknown";

export type PlanSheetGraphActionability = "high" | "data_quality";

// Present ONLY on actionable rows (backend gates it behind the default-OFF
// flag TRUELINE_MRQ_PLAN_SHEET_GRAPH_EVIDENCE and excludes the noisy statuses
// within_corridor / multi_corridor_span). Schema: plan-sheet-graph-evidence-1.
export interface PlanSheetGraphEvidence {
  schema_version?: string;
  status: PlanSheetGraphStatus;
  actionability: PlanSheetGraphActionability;
  reasons?: string[];
  prints?: number[];
  sheets?: number[];
  corridors?: number[][];
  station_range?: [number, number] | null;
  index_streets?: string[];
  notes_streets?: string[];
}

// Read-only projection of the backend `evidence_summary` (KMZ Matching Trust
// Slice B). Surfaces the PDF print-index dimension: print/sheet tokens, the
// expected route set the print/sheet index maps those prints to, street hints,
// and notes streets. The backend owns the canonical shape; the UI reads a
// subset (extra runtime fields like evidence_resolver_tag are ignored).
export interface MatchReviewEvidenceSummary {
  print_tokens?: string[];
  print_sheet_index_source?: string | null;
  filter_applied?: boolean;
  street_hints?: string[];
  allowed_route_ids?: string[];
  notes_streets?: string[];
  // Present (truthy object) when the matcher flagged a notes-vs-index street
  // mismatch; null/absent otherwise. The UI only reads its presence.
  location_evidence_mismatch?: Record<string, unknown> | null;
}

// One of the top-3 scored route alternates for a group (read-only projection).
export interface MatchReviewAlternate {
  route_id: string | null;
  route_name: string | null;
  score: number | null;
  route_length_ft: number | null;
  was_selected: boolean;
}

export interface MatchReviewRow {
  source_file: string | null;
  group_id: string | null;
  status: string;
  priority: string;
  selected_route_id: string | null;
  selected_route_name: string | null;
  render_allowed: boolean | null;
  abstain_reason?: string | null;
  ambiguity_resolution_status?: string | null;
  evidence_summary?: MatchReviewEvidenceSummary;
  top_3_alternates?: MatchReviewAlternate[];
  plan_sheet_graph_evidence?: PlanSheetGraphEvidence;
}

// ── PDF-first engine evidence (Day-4f) ─────────────────────────────────────
// Present ONLY when the backend runs the deterministic PDF-first engine
// (TRUELINE_PDF_FIRST_ENGINE=1) and real inputs resolve. The adapter
// `pdf_first_adapter.py` owns the canonical shape; the UI reads a subset.
// Schema: pdf-first-evidence-1. Crop images are not served in-browser yet —
// render_artifact_ref is a server-side path for now (next: artifact serving).
export interface PdfFirstStationRange {
  start?: string | null;
  end?: string | null;
}

// A pdf_path_trace / pdf_redline overlay block — present per-card only when the
// stacked render flags are ON. `artifact_name` is a BASENAME: fetch the page-space
// overlay PNG via GET /api/pdf-first-evidence/{session_id}/artifact?name=<artifact_name>
// (the backend re-roots it under the owned session dir; no absolute path is exposed).
export interface PdfFirstOverlay {
  trace_status?: string | null; // pdf_path_trace only: PDF_PATH_TRACE_*
  artifact_name?: string | null; // basename of the rendered overlay PNG
  artifact_refs?: string[];
  path_basis?: string | null; // pdf_path_trace only
}

// One per-sheet segment of a cross-sheet (matchline-seam) run. The backend renders a
// cross-sheet bore as TWO page-space overlays (never one continuous cross-page line);
// `artifact_name` is a BASENAME fetched through the same gated artifact route as the
// primary overlay. Present only when TRUELINE_CROSS_SHEET_SEAM_STITCH is ON + resolved.
export interface PdfFirstSeamSegment {
  sheet?: number | null;
  from?: string | null;
  to?: string | null;
  artifact_name?: string | null; // basename of the per-sheet seam-stitch PNG
  // Per-segment draw DECISION + machine-readable abstain evidence. The canonical payload
  // surfaces these; this mirror previously dropped them. `status` is e.g. "drawn" |
  // "abstained_pending_evidence_fusion" | "abstained_requires_path_evidence". When
  // abstained, `artifact_name` is null (NO fake geometry) and `reason` explains why.
  status?: string | null;
  reason?: string | null;
  discriminators?: Record<string, unknown> | null; // D13 evidence-fusion discriminators
}

// Cross-sheet seam-stitch evidence (default-OFF TRUELINE_CROSS_SHEET_SEAM_STITCH).
// `resolved` true means all four anchors resolved and BOTH per-sheet segments rendered.
export interface PdfFirstCrossSheetSeamStitch {
  resolved?: boolean;
  segments?: PdfFirstSeamSegment[];
  machine_resolved_anchors?: number;
  owner_verified_anchors?: number;
  // Additive evidence the canonical payload carries (read-only; previously dropped):
  run_id?: string | null;
  reason?: string | null;
  owner_seam_reason?: string | null;
  // Per-anchor resolution map, e.g. { sheet17_start_hh: {source, resolved, reason, xy}, ... }.
  // Any page-space `xy` inside is EVIDENCE only — never a world/map coordinate.
  anchors?: Record<string, unknown> | null;
}

// One page-space EVIDENCE anchor (AP/HH/structure) resolved on the plan. NOTE: `coord`
// is PAGE-SPACE [x,y] at the rendered DPI — NOT lat/lon and NEVER a map join key. Bridge
// joins must use `id`/`kind` (identity), per the PDF↔KMZ bridge doctrine.
export interface PdfFirstGeoAnchor {
  kind?: string | null;   // e.g. "AP" | "HH" | "SPLICE"
  id?: string | null;     // e.g. "AP-120" — identity join key (normalize TYPE:number for KMZ)
  sheet?: number | null;
  sta?: string | null;
  coord?: [number, number] | null; // PAGE-SPACE evidence only — never world coords
  chainage_ft?: number | null;
  pxdist?: number | null;
  source?: string | null;
  provenance?: string | null;
}

// Drawn structure-to-structure connector (single-sheet crossing, e.g. log66). `anchor` is
// PAGE-SPACE [x,y] evidence, not a map coordinate. Canonical payload field; previously dropped.
export interface PdfFirstStructConnector {
  resolved?: boolean;
  anchor?: [number, number] | null; // PAGE-SPACE evidence only
  source?: string | null;           // e.g. "physical_anchor" | "text_anchor"
  artifact_name?: string | null;
  reason?: string | null;
}

// Coord-free chainage frame metadata. NO world coords. Superset of the prior inline shape
// (back-compatible: existing readers of `multi_sheet`/`page` still work).
export interface PdfFirstFrame {
  multi_sheet?: boolean;
  sheet?: number | null;
  page?: number | null;
  datum_ft?: number | null;
  chainage_start_ft?: number | null;
  chainage_end_ft?: number | null;
  axis?: string | null;
  eqs_used?: string[];
  caveat?: string | null;
  note?: string | null;
}

// Evidence-only geometry block (page-space; NO map/world coords). Present only when
// TRUELINE_AP_ANCHORED_GEOMETRY (+ stacked flags) is ON.
export interface PdfFirstGeo {
  geometry_status?: string | null;
  pdf_path_trace?: PdfFirstOverlay | null;
  pdf_redline?: PdfFirstOverlay | null;
  // Expanded coord-free chainage frame (now includes datum/chainage/axis/eqs). NO world coords.
  frame?: PdfFirstFrame | null;
  // Cross-sheet (matchline-seam) run rendered as two per-sheet segments. Additive;
  // present only when TRUELINE_CROSS_SHEET_SEAM_STITCH is ON + the stitch resolved.
  cross_sheet_seam_stitch?: PdfFirstCrossSheetSeamStitch | null;
  // EXACT page-space evidence anchors (AP/HH/structure IDENTITY + page coords). Canonical
  // payload carries these; surfaced here for the bridge/identity layer (read-only).
  geo_anchors?: PdfFirstGeoAnchor[];
  // Single-sheet structure connector (e.g. log66). Canonical payload field; previously dropped.
  struct_connector?: PdfFirstStructConnector | null;
  // Matchline/station-frame resolution summary (resolver consult). Opaque read-only object.
  matchline_resolution?: Record<string, unknown> | null;
  // Narrative evidence trail (human-readable strings from the engine/resolver).
  evidence_trail?: string[] | null;
  // RESERVED contract slot — back-of-curb offset (feet). The backend does NOT yet emit this
  // as a first-class field (today BOC appears only in evidence_trail/caveat text); typed here
  // so the bridge layer can consume it once the backend surfaces it. May be absent.
  boc_ft?: number | null;
}

export interface PdfFirstCard {
  log_ids?: string[];
  segment_id?: string | null;
  tier?: string;
  surface?: string;
  print?: string | null;
  sheets?: number[];
  station_range?: PdfFirstStationRange;
  footage?: number | null;
  conduit?: string | null;
  end_structures?: string[];
  evidence?: string[];
  caveat?: { code?: string; text?: string } | null;
  render_artifact_ref?: string[] | string | null;
  geo?: PdfFirstGeo | null;
  // RESERVED contract slot — numeric confidence in [0,1] for the placement/evidence. Does
  // NOT exist in the backend payload yet (`tier` is the current proxy); typed here so the
  // bridge layer can consume a confidence once the backend computes one. May be absent.
  confidence?: number | null;
}

export interface PdfFirstFailSafeCard {
  log_ids?: string[];
  tier?: string;
  reason?: string;
  candidates?: unknown[];
  render_artifact_ref?: string[] | string | null;
}

export interface PdfFirstGroup {
  group_id?: string | null;
  log_ids?: string[];
  tier?: string | null;
  kind?: string | null;
  caveat?: { code?: string; text?: string } | null;
  signals?: { false_overlaps?: number } & Record<string, unknown>;
}

export interface PdfFirstEvidence {
  schema_version?: string;
  status?: string;
  render_target?: string;
  source?: { input?: string; logs?: string[]; plan_pdf?: string } & Record<string, unknown>;
  counts_by_tier?: Record<string, number>;
  counts_by_surface?: { placements?: number; review_items?: number; fail_safe?: number };
  placements?: PdfFirstCard[];
  review_items?: PdfFirstCard[];
  fail_safe?: PdfFirstFailSafeCard[];
  groups?: PdfFirstGroup[];
  warnings?: string[];
  // Resolver consult summary — present only when TRUELINE_MATCHLINE_FRAME_RESOLVER is ON.
  // Read-only evidence (counts + owner-reviewed correction provenance); no map geometry.
  resolver?: {
    flag?: string;
    consult_active?: boolean;
    resolved_count?: number;
    corrections_applied?: Array<Record<string, unknown>>;
  } | null;
}

export interface MatchReviewQueueResponse {
  success?: boolean;
  session_id?: string;
  schema_version?: string;
  row_count?: number;
  counts_by_status?: Record<string, number>;
  counts_by_priority?: Record<string, number>;
  rows?: MatchReviewRow[];
  // Additive, present only when the PDF-first engine ran (flag ON + real inputs).
  pdf_first_evidence?: PdfFirstEvidence;
}
