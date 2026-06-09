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
  status?: string | null; // drawn | abstained_* (additive; review reasons)
  reason?: string | null; // per-segment abstain reason (additive)
}

// Cross-sheet seam-stitch evidence (default-OFF TRUELINE_CROSS_SHEET_SEAM_STITCH).
// `resolved` true means all four anchors resolved and BOTH per-sheet segments rendered.
export interface PdfFirstCrossSheetSeamStitch {
  resolved?: boolean;
  segments?: PdfFirstSeamSegment[];
  machine_resolved_anchors?: number;
  owner_verified_anchors?: number;
  reason?: string | null; // stitch-level abstain reason (additive)
  discriminators?: Array<{ name?: string; ok?: boolean; detail?: string | null }>; // additive
}

// Evidence-only geometry block (page-space; NO map/world coords). Present only when
// TRUELINE_AP_ANCHORED_GEOMETRY (+ stacked flags) is ON.
export interface PdfFirstGeo {
  geometry_status?: string | null;
  pdf_path_trace?: PdfFirstOverlay | null;
  pdf_redline?: PdfFirstOverlay | null;
  // Coord-free chainage frame metadata. `multi_sheet` flags a bore that crosses a
  // matchline (the trace is the sheet-local portion only). NO world coords.
  frame?: {
    multi_sheet?: boolean;
    page?: number | null;
    chainage_start_ft?: number | null; // additive (review reasons)
    chainage_end_ft?: number | null; // additive
    axis?: string | null; // additive
    eqs_used?: string[]; // additive — station equations applied (e.g. "STA 4+57=0+00")
  } | null;
  // Cross-sheet (matchline-seam) run rendered as two per-sheet segments. Additive;
  // present only when TRUELINE_CROSS_SHEET_SEAM_STITCH is ON + the stitch resolved.
  cross_sheet_seam_stitch?: PdfFirstCrossSheetSeamStitch | null;
  // Owner-reviewed matchline / station-frame resolver evidence (additive; present
  // when TRUELINE_MATCHLINE_FRAME_RESOLVER lifted this bore). Extra keys ignored.
  matchline_resolution?:
    | ({ status?: string | null; class?: string | null; sheets?: number[]; boc_ft?: number | null; hh_hh_ft?: number | null } & Record<string, unknown>)
    | null;
  // Physical-handhole anchor resolution (additive): real CAD structure symbol vs
  // text-label fallback. Extra keys ignored.
  physical_anchor?: ({ resolved?: boolean; reason?: string | null } & Record<string, unknown>) | null;
}

// Operator-facing "why it drew / why it abstained" record (schema
// pdf-first-review-reason-1). Additive + read-only: the backend builds it from
// the already-computed geo evidence; it NEVER changes any draw/abstain decision.
export interface ReviewReasonDiscriminator {
  name?: string;
  ok?: boolean;
  detail?: string | null;
}
export interface ReviewReason {
  schema_version?: string;
  code?: string;
  message?: string;
  discriminators?: ReviewReasonDiscriminator[];
  missing?: string[];
  evidence?: {
    geometry_status?: string | null;
    station_frame?: {
      chainage_start_ft?: number | null;
      chainage_end_ft?: number | null;
      axis?: string | null;
      eqs_used?: string[];
      multi_sheet?: boolean;
    } | null;
    matchline?: {
      status?: string | null;
      class?: string | null;
      sheets?: number[];
      hh_hh_ft?: number | null;
    } | null;
    physical_anchor?: { resolved?: boolean; reason?: string | null } | null;
    boc_ft?: number | null;
  } & Record<string, unknown>;
}

// Source-lineage evidence (Slice 1a.1) — present on a card ONLY when the backend
// runs with TRUELINE_SOURCE_LINEAGE_EVIDENCE=1. Additive + read-only: labels which
// source/original bore log a split child came from; NEVER affects draw/overlay.
export interface PdfFirstSourceLineage {
  schema_version?: string;
  source_log_id?: string | null;
  parent_kind?: "daily_bundle" | "continuous_run" | "uncertain" | string;
  review_status?: "locked" | "manual_review_pending" | string;
  parent_view?: string | null;
  child_segment_id?: string | null;
  safe_standalone?: "true" | "false" | "uncertain" | string;
  closeout_scope?: "child" | "parent_run" | "hold" | string;
  parent_ownership_label?: string | null;
  segment_draw_scope?: { drawable?: boolean; scope_note?: string | null } | null;
  owner_questions?: string[];
  scope_note?: string | null;
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
  // Additive (Monday hardening): present when the backend could summarize the
  // card's geo evidence. Absent otherwise. Read-only; never affects rendering of
  // the overlay/placement.
  review_reason?: ReviewReason | null;
  source_lineage?: PdfFirstSourceLineage;
}

export interface PdfFirstFailSafeCard {
  log_ids?: string[];
  tier?: string;
  reason?: string;
  candidates?: unknown[];
  render_artifact_ref?: string[] | string | null;
  source_lineage?: PdfFirstSourceLineage;
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
  /**
   * Phase-1 lazy heavy-evidence: true ONLY when the initial metadata-first build deferred the
   * heavy renders (path_trace_overlay + seam_stitch). The FE reads it to show a "generating" state
   * instead of misreading an absent overlay as abstain/failure. Absent on the full envelope (after
   * the background continuation overwrites the cache) and absent entirely when the flag is OFF.
   */
  heavy_evidence_pending?: boolean;
}

// A+B+C gate (session-level preseed status). Mirrors the backend STATE["mrq_preseed"]
// block surfaced on /api/current-state and the /api/match-review-queue "preparing"
// response. status vocabulary: scheduled | building | ready | skipped:<reason> | failed:<type>.
export interface MrqPreseedStatus {
  status: string;
  logs?: number;
  rows?: number;
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
  // A+B+C gate: true while the background preseed is still warming this session's cache —
  // the backend returns this FAST instead of paying the cold build (prevents the 504).
  preparing?: boolean;
  mrq_preseed?: MrqPreseedStatus;
}
