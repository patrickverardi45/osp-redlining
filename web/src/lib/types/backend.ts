// All backend-facing and shared UI types for the Redline Map workspace.
// Moved verbatim from components/RedlineMap.tsx as part of Phase 1 extraction.
// No behavior changes. Do not edit shapes here without coordinating with the FastAPI backend.

export type CandidateRanking = {
  route_id?: string;
  route_name?: string;
  source_folder?: string;
  route_role?: string;
  route_length_ft?: number;
  expected_span_ft?: number;
  length_gap_ft?: number;
  score?: number;
  reason?: string;
};

export type VerificationInfo = {
  confidence?: string;
  reason?: string;
  mapping_mode?: string;
  anchor_type?: string;
  print_present?: boolean;
  route_name?: string;
  route_length_ft?: number;
  source_file?: string;
  print?: string;
  candidate_rankings?: CandidateRanking[];
};

export type StationPoint = {
  station?: string;
  station_ft?: number;
  mapped_station_ft?: number;
  lat?: number;
  lon?: number;
  depth_ft?: number | null;
  boc_ft?: number | null;
  notes?: string;
  date?: string;
  crew?: string;
  print?: string;
  source_file?: string;
  point_role?: string;
  verification?: VerificationInfo;
};

export type RedlineSegment = {
  segment_id?: string;
  start_station?: string;
  end_station?: string;
  length_ft?: number;
  print?: string;
  source_file?: string;
  route_name?: string;
  coords?: number[][];
};

export type GroupMatch = {
  route_name?: string;
  route_role?: string;
  confidence_label?: string;
  final_decision?: string;
  expected_span_ft?: number;
  length_gap_ft?: number;
  print?: string;
  candidate_rankings?: CandidateRanking[];
  print_filter?: {
    print_tokens?: string[];
  };
};

export type KmzLineFeature = {
  feature_id?: string;
  route_id?: string;
  route_name?: string;
  source_folder?: string;
  role?: string;
  coords?: number[][];
  color?: string;
  width?: number;
  stroke?: string;
  stroke_width?: number;
};

export type KmzPolygonFeature = {
  feature_id?: string;
  name?: string;
  coords?: number[][];
  fill_color?: string;
  stroke_color?: string;
  fill?: string;
  stroke?: string;
  fill_opacity?: number;
  stroke_width?: number;
};

export type BoreLogSummaryEntry = {
  source_file: string;
  row_count: number;
  min_station_ft?: number | null;
  max_station_ft?: number | null;
  span_ft?: number | null;
  dates?: string[];
  print_tokens?: string[];
  crews?: string[];
  evidence_layer_id?: string;
  engineering_plan_ref?: string | null;
  engineering_plan_date?: string | null;
};

export type EngineeringPlan = {
  plan_id: string;
  session_id: string;
  original_filename: string;
  stored_filename: string;
  file_type: string;
  size_bytes: number;
  uploaded_at: string;
  plan_date?: string | null;
  print_numbers?: string | null;
  sheet_numbers?: string | null;
  street_hints?: string | null;
  notes?: string | null;
};

export type BackendState = {
  success?: boolean;
  session_id?: string;
  message?: string;
  warning?: string;
  error?: string;
  route_name?: string | null;
  selected_route_name?: string | null;
  selected_route_match?: GroupMatch | null;
  route_coords?: number[][];
  loaded_field_data_files?: number;
  latest_structured_file?: string | null;
  redline_segments?: RedlineSegment[];
  station_points?: StationPoint[];
  active_route_redline_segments?: RedlineSegment[];
  active_route_station_points?: StationPoint[];
  verification_summary?: {
    status?: string;
    route_selection_reason?: string;
  };
  total_length_ft?: number;
  covered_length_ft?: number;
  completion_pct?: number;
  active_route_covered_length_ft?: number;
  active_route_completion_pct?: number;
  active_route_station_points_count?: number;
  active_route_redline_segments_count?: number;
  committed_rows?: Array<Record<string, unknown>>;
  bug_report_count?: number;
  suggested_route_id?: string | null;
  station_mapping_mode?: string | null;
  kmz_reference?: {
    line_features?: KmzLineFeature[];
    polygon_features?: KmzPolygonFeature[];
  };
  engineering_plans?: EngineeringPlan[];
  bore_log_summary?: BoreLogSummaryEntry[];
};

export type StationPhoto = {
  photo_id: string;
  station_identity: string;
  station_summary: string;
  original_filename: string;
  stored_filename: string;
  content_type?: string;
  uploaded_at: string;
  relative_url: string;
};

export type ExceptionCost = {
  id: string;
  label: string;
  amount: string;
};

export type NoteTone = "neutral" | "success" | "warning" | "error";

export type Bounds = {
  minLat: number;
  maxLat: number;
  minLon: number;
  maxLon: number;
};

export type ScreenPoint = { x: number; y: number };

export type Viewport = {
  zoom: number;
  panX: number;
  panY: number;
};
