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
  /** Fiber / structure id for fiber_pull labeling (optional; bore HDD rows omit). */
  business_id?: string | null;
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

/**
 * Phase 1A — additive KMZ/KML semantic feature.
 *
 * Each feature corresponds to a single KML <Placemark>. The shape preserves
 * the engineering intelligence that route extraction discards: raw name,
 * description, folder hierarchy, geometry kind, styleUrl, and ExtendedData.
 *
 * Rendering is NOT the source of truth — consumers may use these fields or
 * ignore them. The `classification` is heuristic and additive only; the
 * upstream `role` field on line/polygon/point features is unrelated.
 */
export type SemanticKmzClassification =
  | "handhole"
  | "station_label"
  | "reel"
  | "structure_marker"
  | "route_segment"
  | "boundary_polygon"
  | "annotation"
  | "unknown";

export type SemanticKmzConfidence = "high" | "medium" | "low";

export type SemanticKmzGeometryType =
  | "Point"
  | "LineString"
  | "Polygon"
  | "MultiGeometry"
  | "Other";

/** Phase B — full geometry payloads. Excluded for MultiGeometry placemarks
 *  (use multigeometry_children for those). */
export type SemanticKmzFullGeometry =
  | { kind: "Point"; coord: [number, number] }
  | { kind: "LineString"; coords: Array<[number, number]> }
  | {
      kind: "Polygon";
      outer: Array<[number, number]>;
      inner?: Array<Array<[number, number]>>;
    };

/** Phase B — direct child geometries enumerated for MultiGeometry placemarks. */
export type SemanticKmzMultiGeometryChild = {
  kind: "Point" | "LineString" | "Polygon";
  coord_hint: [number, number] | null;
};

/** Phase C — resolved <Style>/<StyleMap> properties. All fields optional. */
export type SemanticKmzResolvedStyle = {
  line_color?: string;       // "#3b82f6"
  line_width?: number;
  poly_fill?: string;
  icon_href?: string;
  label_color?: string;
};

/** Phase C — lifecycle hint. label is one of a known set; null when no
 *  signal matched. */
export type SemanticKmzLifecycle = {
  label: "existing" | "proposed" | "asbuilt" | "decommissioned" | "survey";
  confidence: SemanticKmzConfidence;
  reason: string;
};

/** Additive read-only explainability metadata produced alongside each
 *  classification. Never affects the classification result itself. */
export type SemanticKmzClassificationDebug = {
  /** Which kind(s) of signal triggered the classification.
   *  Values: "name_regex" | "description_regex" | "extended_data_key"
   *        | "name_contains" | "folder_hint" | "style_url_hint" | "geometry_type" */
  matched_by: string[];
  /** The actual text tokens/strings that matched (regex capture group,
   *  ExtendedData key name, or substring keyword). */
  matched_tokens: string[];
  /** Which input fields were consulted.
   *  Values: "placemark_name" | "placemark_description" | "folder_path"
   *        | "style_url" | "extended_data" | "geometry_type" */
  heuristic_sources: string[];
  /** Which geometry node provided the representative coordinate hint.
   *  "Point" | "LineString" | "Polygon" | null when coords_hint is null. */
  coordinate_source: "Point" | "LineString" | "Polygon" | null;
};

export type SemanticKmzFeature = {
  feature_id: string;
  /** Phase 1B — KML <Placemark id="..."> attribute when present, null
   *  otherwise. Combine with source_filename for cross-file joins. */
  placemark_id?: string | null;
  placemark_name: string;
  /** HTML stripped + whitespace collapsed. */
  description: string;
  /** Verbatim KML <description> text, including any HTML the source used. */
  description_raw: string;
  folder_path: string[];
  folder_path_str: string;
  geometry_type: SemanticKmzGeometryType;
  style_url: string;
  /** Flat key/value map from <ExtendedData><Data> and <SchemaData><SimpleData>. */
  extended_data: Record<string, string>;
  /** Best-effort representative [lat, lon]; null when no geometry was found. */
  coords_hint: [number, number] | null;
  classification: SemanticKmzClassification;
  confidence: SemanticKmzConfidence;
  /** Short string describing which signal triggered the classification. */
  classification_reason: string;
  /** Phase 1B — name of the source KMZ/KML this feature came from. Useful
   *  when a project ingests multiple design files. */
  source_filename?: string;
  /** Phase A — chainage (in feet) parsed from "STA NN+NN" tokens.
   *  null when no chainage token was present. */
  chainage_ft?: number | null;
  chainage_source?: "name" | "description" | null;
  /** Phase A — sequence number parsed from classification-specific tokens
   *  ("HH-12" → 12 when classification === "handhole"). null otherwise. */
  sequence_number?: number | null;
  sequence_kind?:
    | "handhole"
    | "manhole"
    | "reel"
    | "structure"
    | null;
  /** Phase B — full geometry payload for non-MultiGeometry placemarks.
   *  null for MultiGeometry; see multigeometry_children. */
  full_geometry?: SemanticKmzFullGeometry | null;
  multigeometry_children?: SemanticKmzMultiGeometryChild[];
  /** Phase C — style resolved against the document-level <Style>/<StyleMap>
   *  table. null when style_url is empty or unresolved. */
  style_resolved?: SemanticKmzResolvedStyle | null;
  lifecycle?: SemanticKmzLifecycle | null;
  /** Additive read-only explainability metadata. Present from parser_version
   *  "semantic-1" onward. Never affects classification, scoring, or rendering. */
  classification_debug?: SemanticKmzClassificationDebug | null;
};

export type SemanticKmzIndex = {
  feature_count: number;
  truncated: boolean;
  by_classification: Record<string, number>;
  by_geometry_type: Record<string, number>;
  by_folder: Record<string, number>;
  by_confidence: Record<string, number>;
  style_url_count: Record<string, number>;
  extended_data_keys: string[];
  /** Phase 1B — top 10 folder paths by feature count, sorted desc by count
   *  then asc by name. */
  top_folders?: Array<{ folder_path_str: string; count: number }>;
  /** Phase 1B — top 10 styleUrls by feature count, same sort order. */
  top_style_urls?: Array<{ style_url: string; count: number }>;
  /** Phase 1B — bounded sample feature_ids per classification (max 5
   *  per category). Look up details in `features[]` by feature_id. */
  classification_samples?: Partial<Record<SemanticKmzClassification, string[]>>;
  /** Phase 1B — distinct source filenames present in this semantic
   *  ingestion (currently always one entry, but plumbed for future
   *  multi-KMZ ingestion). */
  source_filenames?: string[];
  /** Phase 1B — caps used by the parser, surfaced for diagnostics UX. */
  feature_cap?: number;
  sample_cap?: number;
  /** Phase A/B/C — counts of features for which deterministic extractions
   *  produced a non-null value. Read by the diagnostics panel. */
  features_with_chainage?: number;
  features_with_sequence?: number;
  features_with_full_geometry?: number;
  features_with_resolved_style?: number;
  /** Phase C — number of <Style id="…"> blocks (after StyleMap resolution)
   *  parsed from the document. */
  styles_resolved_count?: number;
  /** Phase C — bucketed lifecycle counts. */
  by_lifecycle?: Record<string, number>;
  top_lifecycle?: Array<{ label: string; count: number }>;
  /** Phase C — top resolved <LineStyle><color> values across all features.
   *  Useful for spotting "this color = role X" conventions in real KMZs. */
  top_resolved_line_colors?: Array<{ color: string; count: number }>;
  /** Phase A/B/C — read-only candidate anchor catalog. The redline engine
   *  MAY consume this in a future phase; today it is purely diagnostic. */
  anchor_catalog?: Array<{
    feature_id: string;
    classification: SemanticKmzClassification;
    sequence_number?: number | null;
    sequence_kind?: string | null;
    chainage_ft?: number | null;
    coord: [number, number];
    confidence: SemanticKmzConfidence;
    folder_path_str: string;
    lifecycle?: string | null;
  }>;
  anchor_catalog_truncated?: boolean;
  anchor_cap?: number;
  /** Skipped-placemark observability (additive). 0 when every placemark
   *  parsed successfully. Present from parser_version "semantic-1" onward. */
  skipped_placemark_count?: number;
  skipped_placemark_samples?: Array<{
    placemark_index_in_doc: number;
    error_kind: string;
    message: string;
  }>;
  /** Style resolution health — additive diagnostic. Never affects matching or
   *  rendering. Counts derived from the KML document's Style/StyleMap elements
   *  and the placemark-referenced styleUrls. */
  style_resolution?: {
    ids_declared: number;
    ids_referenced: number;
    ids_referenced_unresolved: number;
    stylemap_count: number;
    stylemap_unresolved_count: number;
    /** Always 0 in semantic-1; cycle detection not yet tracked per-run. */
    stylemap_cycle_count: number;
  };
  /** Unresolved styleUrl strings referenced by placemarks, capped at 25. */
  missing_style_urls?: string[];
};

export type SemanticKmz = {
  parser_version: string;
  features: SemanticKmzFeature[];
  index: SemanticKmzIndex;
  /** Additive warning strings emitted during ingestion. Each entry corresponds
   *  to one skipped placemark: "placemark N (ErrorKind): message". Empty array
   *  when every placemark parsed successfully. Capped at 200. */
  warnings?: string[];
};

/**
 * Phase 1D — IngestionLedger.
 *
 * One row per KMZ semantic ingestion, persisted to ingestion_ledger.jsonl.
 * Exposed read-only via GET /api/observability/ingestion-ledger.
 * Never affects matching, scoring, or rendering.
 */
export type IngestionLedgerEntry = {
  ingested_at: string;
  filename: string;
  input_sha256: string;
  parser_version: string | null;
  feature_count: number;
  anchor_count: number;
  skipped_placemark_count: number;
  warnings_count: number;
  truncated: boolean;
  anchor_catalog_truncated: boolean;
  styles_resolved_count: number;
  ids_referenced_unresolved: number;
  stylemap_unresolved_count: number;
};

export type IngestionLedgerResponse = {
  entries: IngestionLedgerEntry[];
};

/**
 * Phase 1C — SHADOW MODE matching diagnostics.
 *
 * Purely informational. The matching engine continues to ignore this; the
 * diagnostics panel surfaces it so engineers can audit whether the anchor
 * catalog would agree with current route selection. Never affects
 * operational behavior.
 */
export type SemanticMatchShadowGroup = {
  group_id: string;
  group_index: number;
  existing_selected_route_id: string;
  existing_selected_route_name: string;
  existing_score: number;
  semantic_best_route_id: string | null;
  semantic_best_route_name: string | null;
  semantic_best_score: number;
  /** true when semantic best == existing selected; false on disagreement;
   *  null when no anchors contributed (no signal). */
  agreement: boolean | null;
  anchors_near_selected_route: number;
  anchors_near_semantic_best_route: number;
  contributing_anchor_ids: string[];
  explanation: string;
  ranked_routes: Array<{
    route_id: string;
    route_name: string;
    anchor_count: number;
    semantic_score: number;
  }>;
};

export type SemanticMatchShadow = {
  version: string;
  summary: {
    groups_total: number;
    groups_in_agreement: number;
    groups_in_disagreement: number;
    groups_with_no_anchors: number;
    anchors_considered: number;
    weights: {
      confidence: Record<string, number>;
      classification: Record<string, number>;
      proximity_near_ft: number;
      proximity_far_ft: number;
    };
  };
  groups: SemanticMatchShadowGroup[];
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
  /** Phase 1A — additive semantic layer. null/absent until a KMZ is uploaded
   *  or when the additive parse failed; consumers must treat absence as
   *  "no semantic data available" and continue using kmz_reference for
   *  rendering. */
  kmz_semantic?: SemanticKmz | null;
  /** Phase 1C — shadow-mode matching diagnostics. Read-only, additive.
   *  null when prerequisites (anchor catalog, route_match_candidates) are
   *  missing. Never affects operational behavior. */
  kmz_semantic_match_shadow?: SemanticMatchShadow | null;
  engineering_plans?: EngineeringPlan[];
  bore_log_summary?: BoreLogSummaryEntry[];
  photo_points?: GlobalPhotoPoint[];
  closeout_locked?: boolean;
  closeout_locked_by?: string | null;
  closeout_locked_at?: string | null;
  /** When is_locked, mutating endpoints return 403 Closeout is locked */
  closeout_lock?: {
    is_locked?: boolean;
    locked_by?: string | null;
    locked_at?: string | null;
  };
};

export type GlobalPhotoPoint = {
  id: string;
  source_type: string;
  lat: number;
  lon: number;
  original_lat?: number;
  original_lon?: number;
  adjusted_lat?: number | null;
  adjusted_lon?: number | null;
  adjusted_at?: string | null;
  is_adjusted?: boolean;
  thumbnail_url: string | null;
  original_url: string | null;
  filename: string;
  station_label: string;
  session_id: string;
  uploaded_at: string;
  note?: string | null;
};

export type StationPhoto = {
  photo_id: string;
  session_id?: string;
  station_identity: string;
  station_summary: string;
  original_filename: string;
  stored_filename: string;
  content_type?: string;
  uploaded_at: string;
  relative_url: string;
  public_url?: string;
  original_lat?: number | null;
  original_lon?: number | null;
  adjusted_lat?: number | null;
  adjusted_lon?: number | null;
  adjusted_at?: string | null;
  is_adjusted?: boolean;
};

export type ExceptionCost = {
  id: string;
  label: string;
  amount: string;
  note?: string;
  station?: string;
  billing_relevant?: boolean;
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
