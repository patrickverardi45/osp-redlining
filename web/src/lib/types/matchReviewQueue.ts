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

export interface MatchReviewQueueResponse {
  success?: boolean;
  session_id?: string;
  schema_version?: string;
  row_count?: number;
  counts_by_status?: Record<string, number>;
  counts_by_priority?: Record<string, number>;
  rows?: MatchReviewRow[];
}
