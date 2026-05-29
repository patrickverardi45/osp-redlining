// web/src/lib/types/trustLedger.ts
//
// Read-only frontend mirror of the GET /api/trust-ledger response shape
// (KMZ Automatic Redline Placement — Trust Ledger, schema "trust-ledger-1").
// The backend `app/core/trust_ledger.py` + the trust_ledger_endpoint in
// `main.py` own the canonical schema; this only types the fields the UI reads.
// Extra runtime fields are ignored. Default-OFF on the backend behind
// TRUELINE_TRUST_LEDGER — when OFF the endpoint returns {success:false,
// enabled:false, detail}. This is observation-only: no matching/scoring/
// selection/render data is mutated anywhere in this surface.

export type ProofStatus = "proven" | "abstained" | "missing_proof";

// Route-index verdict — selected route vs the print/sheet index allowed set.
// ORTHOGONAL to the PSG warning; the two are never merged.
export type RouteIndexVerdict = "consistent" | "suspect" | "not_proven";

export interface RouteIndexEvidence {
  selected_route_id: string | null;
  allowed_route_ids: string[];
  print_tokens: string[];
  verdict: RouteIndexVerdict;
}

// Brenham Plan Sheet Graph warning (SEPARATE signal — bore-log notes streets
// vs the print sheet's streets). Present only when an actionable status applies.
export interface TrustLedgerPsgWarning {
  status: string | null;
  actionability: string | null;
}

export interface TrustLedgerGeometrySummary {
  route_length_ft: number | null;
  route_in_catalog: boolean | null;
  geometry_basis: string;
  min_station_ft: number | null;
  max_station_ft: number | null;
}

export interface TrustLedgerCandidateTop {
  route_id: string | null;
  score: number | null;
  score_breakdown?: Record<string, unknown>;
}

export interface TrustLedgerCandidateSummary {
  selected_combined_score: number | null;
  selected_in_rankings: boolean;
  has_rescue_reason: boolean;
  top: TrustLedgerCandidateTop[];
}

export interface TrustLedgerMappingSummary {
  mode: string | null;
  anchor_offset_ft: number | null;
  anchored_start_ft: number | null;
  anchored_end_ft: number | null;
  mapping_present: boolean;
}

export interface TrustLedgerRow {
  source_file: string | null;
  group_id: string | null;
  group_idx: number | null;
  selected_route_id: string | null;
  selected_route_name: string | null;
  render_allowed: boolean | null;
  proof_status: ProofStatus;
  evidence_chain_complete: boolean;
  missing_links: string[];
  abstain_reason: string | null;
  // GROUP 1 — route-index evidence (print-token -> route consistency).
  route_index_evidence: RouteIndexEvidence;
  // GROUP 2 — PSG warning (SEPARATE; orthogonal to route-index). null when none.
  psg_warning: TrustLedgerPsgWarning | null;
  // GROUP 3 — geometry / station evidence.
  geometry_summary: TrustLedgerGeometrySummary;
  // GROUP 4 — candidate / anchor evidence.
  candidate_summary: TrustLedgerCandidateSummary;
  mapping_summary: TrustLedgerMappingSummary;
  selected_anchor_reasons: string[];
}

export interface TrustLedgerCounts {
  proven: number;
  abstained: number;
  missing_proof: number;
}

export interface TrustLedgerCoverageSanitySummary {
  schema_version: string | null;
  placed_group_count: number | null;
  abstained_group_count: number | null;
  total_groups: number | null;
  same_route_anchor_collision_count: number | null;
  same_route_window_decision_count: number | null;
}

export interface TrustLedgerResponse {
  success?: boolean;
  // false on the disabled response (flag OFF). true when the ledger ran.
  enabled?: boolean;
  session_id?: string;
  // Present on the disabled response.
  detail?: string;
  schema_version?: string;
  row_count?: number;
  counts?: TrustLedgerCounts;
  // == counts.missing_proof — the "silent placement" class, surfaced honestly.
  silent_placement_count?: number;
  psg_warning_count?: number;
  coverage_sanity_summary?: TrustLedgerCoverageSanitySummary | null;
  rows?: TrustLedgerRow[];
}
