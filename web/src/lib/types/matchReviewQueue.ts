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
